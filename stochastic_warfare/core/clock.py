"""Calendar-aware simulation clock.

All simulation time queries go through this class.  Internally everything
is UTC ``datetime``; the clock also exposes derived astronomical quantities
(Julian date, day-of-year, etc.) needed by the environment module.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone


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
    def elapsed(self) -> timedelta:
        """Wall-clock time elapsed since scenario start."""
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
        self._start = datetime.fromisoformat(state["start"])
        self._current = datetime.fromisoformat(state["current"])
        self._tick_duration = timedelta(seconds=state["tick_duration_seconds"])
        self._tick_count = state["tick_count"]


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
