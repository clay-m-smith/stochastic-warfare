"""Calendar-aware simulation clock.

All simulation time queries go through this class.  Internally everything
is UTC ``datetime``; the clock also exposes derived astronomical quantities
(Julian date, day-of-year, etc.) needed by the environment module.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from decimal import ROUND_CEILING, Decimal
from typing import Any


_DATETIME_DOMAIN = datetime.max - datetime.min


def normalize_clock_duration_seconds(
    value: Any,
    *,
    field_name: str,
) -> float:
    """Return a positive duration exactly representable by ``timedelta``.

    Simulation cadence is stored by :class:`datetime.timedelta`, whose
    resolution and range are narrower than the positive finite IEEE-754
    floats accepted by ordinary numeric schemas.  Rejecting quantization and
    overflow here keeps authored, effective, persisted, and executed cadence
    identical.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(
            f"{field_name} must be a finite positive clock duration",
        )
    try:
        normalized = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError(
            f"{field_name} must be a finite positive clock duration",
        ) from exc
    if not math.isfinite(normalized) or normalized <= 0.0:
        raise ValueError(
            f"{field_name} must be a finite positive clock duration",
        )
    try:
        duration = timedelta(seconds=normalized)
    except OverflowError as exc:
        raise ValueError(
            f"{field_name} exceeds the simulation clock range",
        ) from exc
    represented = duration.total_seconds()
    if represented != normalized:
        raise ValueError(
            f"{field_name} must be exactly representable at microsecond "
            "simulation-clock precision",
        )
    if duration > _DATETIME_DOMAIN:
        raise ValueError(
            f"{field_name} exceeds the simulation calendar range",
        )
    return normalized


def clock_execution_horizon_end(
    *,
    start: datetime,
    scenario_duration_seconds: float,
    maximum_tick_seconds: float,
) -> datetime:
    """Return the validated final executable calendar endpoint."""
    if not isinstance(start, datetime) or start.tzinfo is None:
        raise ValueError("start must be a timezone-aware datetime")
    if (
        isinstance(scenario_duration_seconds, bool)
        or not isinstance(scenario_duration_seconds, (int, float))
        or not math.isfinite(float(scenario_duration_seconds))
        or float(scenario_duration_seconds) <= 0.0
    ):
        raise ValueError(
            "scenario_duration_seconds must be finite and positive",
        )
    maximum_tick = normalize_clock_duration_seconds(
        maximum_tick_seconds,
        field_name="maximum_tick_seconds",
    )
    try:
        duration_microseconds = int(
            (
                Decimal.from_float(float(scenario_duration_seconds))
                * Decimal(1_000_000)
            ).to_integral_value(rounding=ROUND_CEILING),
        )
        duration = timedelta(microseconds=duration_microseconds)
        tick = timedelta(seconds=maximum_tick)
        return start.astimezone(timezone.utc) + duration + tick
    except OverflowError as exc:
        raise ValueError(
            "scenario clock execution horizon exceeds the calendar range",
        ) from exc


def validate_clock_execution_horizon(
    *,
    start: datetime,
    scenario_duration_seconds: float,
    maximum_tick_seconds: float,
) -> None:
    """Reject a scenario whose final possible interval cannot be dated."""
    clock_execution_horizon_end(
        start=start,
        scenario_duration_seconds=scenario_duration_seconds,
        maximum_tick_seconds=maximum_tick_seconds,
    )


class SimulationClock:
    """Tracks simulation time and exposes calendar/astronomical queries.

    Parameters
    ----------
    start:
        Scenario start time (must be UTC).
    tick_duration:
        Duration of one simulation tick.
    """

    def __init__(self, start: datetime, tick_duration: timedelta) -> None:
        if start.tzinfo is None:
            raise ValueError("start must be timezone-aware (UTC)")
        if not isinstance(tick_duration, timedelta):
            raise TypeError("tick_duration must be a timedelta")
        normalize_clock_duration_seconds(
            tick_duration.total_seconds(),
            field_name="tick_duration",
        )
        self._start = start.astimezone(timezone.utc)
        self._current = self._start
        self._tick_duration = tick_duration
        self._tick_count = 0

    # ------------------------------------------------------------------
    # Time queries
    # ------------------------------------------------------------------

    @property
    def current_time(self) -> datetime:
        """Current simulation time (UTC)."""
        return self._current

    @property
    def start_time(self) -> datetime:
        """Scenario start time (UTC)."""
        return self._start

    @property
    def elapsed(self) -> timedelta:
        """Logical simulation time elapsed since scenario start."""
        return self._current - self._start

    @property
    def tick_count(self) -> int:
        """Number of ticks advanced so far."""
        return self._tick_count

    # ------------------------------------------------------------------
    # Calendar / astronomical queries
    # ------------------------------------------------------------------

    @property
    def julian_date(self) -> float:
        """Julian Date for the current UTC time (Meeus Ch. 7)."""
        return _to_julian_date(self._current)

    @property
    def day_of_year(self) -> int:
        """1-based day of year."""
        return self._current.timetuple().tm_yday

    @property
    def month(self) -> int:
        return self._current.month

    @property
    def year(self) -> int:
        return self._current.year

    @property
    def hour_utc(self) -> float:
        """Fractional hour of the day in UTC."""
        t = self._current
        return t.hour + t.minute / 60.0 + t.second / 3600.0

    # ------------------------------------------------------------------
    # Tick management
    # ------------------------------------------------------------------

    def advance(self) -> datetime:
        """Advance by one tick and return the new current time."""
        self._current += self._tick_duration
        self._tick_count += 1
        return self._current

    def set_tick_duration(self, duration: timedelta) -> None:
        """Change tick resolution (e.g. switching from tactical to strategic)."""
        if not isinstance(duration, timedelta):
            raise TypeError("duration must be a timedelta")
        normalize_clock_duration_seconds(
            duration.total_seconds(),
            field_name="duration",
        )
        self._tick_duration = duration

    @property
    def tick_duration(self) -> timedelta:
        return self._tick_duration

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        return {
            "start": self._start.isoformat(),
            "current": self._current.isoformat(),
            "tick_duration_seconds": self._tick_duration.total_seconds(),
            "tick_count": self._tick_count,
        }

    def set_state(self, state: dict) -> None:
        raw_start = state["start"]
        raw_current = state["current"]
        if type(raw_start) is not str or type(raw_current) is not str:
            raise ValueError("clock timestamps must be strict ISO strings")
        try:
            start = datetime.fromisoformat(raw_start)
            current = datetime.fromisoformat(raw_current)
        except ValueError as exc:
            raise ValueError("clock timestamps must be valid ISO datetimes") from exc
        if (
            start.tzinfo is None
            or start.utcoffset() is None
            or current.tzinfo is None
            or current.utcoffset() is None
        ):
            raise ValueError("clock timestamps must be timezone-aware")
        start = start.astimezone(timezone.utc)
        current = current.astimezone(timezone.utc)
        if current < start:
            raise ValueError("clock current time cannot precede its start")

        tick_duration_seconds = normalize_clock_duration_seconds(
            state["tick_duration_seconds"],
            field_name="tick_duration_seconds",
        )
        tick_count = state["tick_count"]
        if (
            isinstance(tick_count, bool)
            or not isinstance(tick_count, int)
            or tick_count < 0
        ):
            raise ValueError("clock tick_count must be a non-negative integer")

        self._start = start
        self._current = current
        self._tick_duration = timedelta(seconds=tick_duration_seconds)
        self._tick_count = tick_count


# ----------------------------------------------------------------------
# Julian Date (Meeus, *Astronomical Algorithms* Ch. 7)
# ----------------------------------------------------------------------


def _to_julian_date(dt: datetime) -> float:
    """Convert a UTC datetime to Julian Date.

    Uses the formula from Meeus Ch. 7 which is valid for all Gregorian
    calendar dates (i.e. dates after 1582-10-15).
    """
    y = dt.year
    m = dt.month
    d = dt.day

    ut = dt.hour + dt.minute / 60.0 + dt.second / 3600.0

    if m <= 2:
        y -= 1
        m += 12

    a = math.floor(y / 100)
    b = 2 - a + math.floor(a / 4)

    jd = (
        math.floor(365.25 * (y + 4716))
        + math.floor(30.6001 * (m + 1))
        + d
        + ut / 24.0
        + b
        - 1524.5
    )
    return jd
