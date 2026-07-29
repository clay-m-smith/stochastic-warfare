"""GPS dependency and navigation warfare.

Models GPS fix quality as a function of visible satellite count, computes
DOP (dilution of precision), position accuracy, INS drift during GPS denial,
and CEP scaling for GPS-guided weapons.

Key physics:
- HDOP ≈ max(1.0, 6.0 / max(visible_count - 3, 1))
- Position error: σ_pos = DOP × σ_range (σ_range ≈ 3m)
- INS drift: σ(t) = σ₀ + drift_rate × t
- Fix quality: FULL/DEGRADED/MARGINAL/DENIED by visible count
"""

from __future__ import annotations

import enum
import math
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.space.constellations import (
    ConstellationManager,
    ConstellationType,
    SpaceConfig,
)
from stochastic_warfare.space.events import GPSAccuracyChangedEvent

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums & models
# ---------------------------------------------------------------------------


class GPSFixQuality(enum.IntEnum):
    """GPS fix quality classification."""

    FULL = 0  # ≥24 visible, DOP ~1.2
    DEGRADED = 1  # 12-23 visible, DOP 2-4
    MARGINAL = 2  # 4-11 visible, DOP 4-10
    DENIED = 3  # <4 visible


class GPSState(BaseModel):
    """Snapshot of GPS fix quality for a side."""

    visible_count: int = 24
    hdop: float = 1.2
    position_accuracy_m: float = 3.6
    fix_quality: int = 0  # GPSFixQuality value


# ---------------------------------------------------------------------------
# GPSEngine
# ---------------------------------------------------------------------------


class GPSEngine:
    """Compute GPS accuracy from constellation health."""

    def __init__(
        self,
        constellation_manager: ConstellationManager,
        config: SpaceConfig,
        event_bus: EventBus,
        rng: np.random.Generator,
        clock: Any = None,
    ) -> None:
        self._cm = constellation_manager
        self._config = config
        self._event_bus = event_bus
        self._rng = rng
        self._clock = clock
        self._previous_accuracy: dict[str, float] = {}
        self._denial_start: dict[str, float] = {}  # side → sim_time when denial started

    def compute_gps_accuracy(self, side: str, sim_time_s: float) -> GPSState:
        """Compute GPS accuracy for *side* at current time."""
        return self._compute_gps_accuracy(
            self._cm,
            side,
            sim_time_s,
        )

    def _compute_gps_accuracy(
        self,
        constellation_manager: ConstellationManager,
        side: str,
        sim_time_s: float,
    ) -> GPSState:
        """Compute GPS accuracy against an explicit constellation view."""
        # Find GPS/GLONASS constellations for this side
        visible_total = 0
        gps_types = {int(ConstellationType.GPS), int(ConstellationType.GLONASS)}
        for cdef in constellation_manager.get_constellations_by_side(side):
            if cdef.constellation_type in gps_types:
                vis = constellation_manager.visible_satellites(
                    cdef.constellation_id,
                    self._config.theater_lat,
                    self._config.theater_lon,
                    sim_time_s,
                    self._config.min_elevation_deg,
                )
                visible_total += len(vis)

        # If no GPS constellations configured for this side, assume full GPS
        has_gps = any(
            cdef.constellation_type in gps_types
            for cdef in constellation_manager.get_constellations_by_side(side)
        )
        if not has_gps:
            visible_total = 24

        hdop = self._compute_hdop(visible_total)
        accuracy = hdop * self._config.gps_sigma_range_m
        quality = self._classify_fix(visible_total)

        return GPSState(
            visible_count=visible_total,
            hdop=hdop,
            position_accuracy_m=accuracy,
            fix_quality=int(quality),
        )

    def _compute_hdop(self, visible_count: int) -> float:
        """Simplified HDOP from visible satellite count."""
        if visible_count < 4:
            return 99.0  # No fix
        return max(1.0, 6.0 / max(visible_count - 3, 1))

    def _classify_fix(self, visible_count: int) -> GPSFixQuality:
        """Classify fix quality from visible count."""
        if visible_count >= 24:
            return GPSFixQuality.FULL
        elif visible_count >= 12:
            return GPSFixQuality.DEGRADED
        elif visible_count >= 4:
            return GPSFixQuality.MARGINAL
        else:
            return GPSFixQuality.DENIED

    def compute_ins_drift(self, time_since_denial_s: float) -> float:
        """Compute INS position error after GPS denial.

        σ(t) = σ₀ + drift_rate × t
        """
        return (self._config.ins_initial_sigma_m
                + self._config.ins_drift_rate_m_per_s * max(0.0, time_since_denial_s))

    def compute_cep_factor(self, gps_accuracy_m: float, guidance_type: str) -> float:
        """Compute CEP scaling factor for a weapon based on GPS accuracy.

        GPS-guided weapons scale CEP with accuracy.  INS-only weapons
        are unaffected.  Baseline is 5.0m GPS accuracy → factor 1.0.
        """
        if guidance_type not in ("gps", "gps_ins"):
            return 1.0  # Non-GPS weapons unaffected
        return max(1.0, gps_accuracy_m / 5.0)

    def _timestamp(self) -> Any:
        """Get simulation timestamp from clock, or epoch fallback."""
        if self._clock is not None:
            return self._clock.current_time
        from datetime import datetime, timezone
        return datetime(2024, 1, 1, tzinfo=timezone.utc)

    def update(self, dt_s: float, sim_time_s: float) -> None:
        """Recompute GPS state and emit events on significant changes."""
        for side in ("blue", "red"):
            state = self.compute_gps_accuracy(side, sim_time_s)
            prev = self._previous_accuracy.get(side, state.position_accuracy_m)
            # Emit event on >20% change
            if abs(state.position_accuracy_m - prev) > 0.2 * max(prev, 1.0):
                self._event_bus.publish(GPSAccuracyChangedEvent(
                    timestamp=self._timestamp(),
                    source=ModuleId.SPACE,
                    side=side,
                    previous_accuracy_m=prev,
                    new_accuracy_m=state.position_accuracy_m,
                    visible_satellites=state.visible_count,
                    dop=state.hdop,
                ))
            self._previous_accuracy[side] = state.position_accuracy_m

    # ── State persistence ────────────────────────────────────────────

    def get_state(self) -> dict[str, Any]:
        return {
            "previous_accuracy": dict(self._previous_accuracy),
            "denial_start": dict(self._denial_start),
        }

    def stage_state(
        self,
        state: dict[str, Any],
        *,
        constellation_manager: ConstellationManager,
        sim_time_s: float,
        expected_tick_count: int | None,
    ) -> dict[str, Any]:
        """Validate GPS history against the staged constellation snapshot."""
        expected_keys = {"previous_accuracy", "denial_start"}
        if set(state) != expected_keys:
            raise ValueError(
                "gps_engine state keys must be exactly "
                f"{sorted(expected_keys)!r}",
            )
        previous = state["previous_accuracy"]
        denial_start = state["denial_start"]
        if not isinstance(previous, dict):
            raise ValueError("GPS previous_accuracy must be a mapping")
        if denial_start != {}:
            raise ValueError(
                "GPS denial_start must be empty until denial tracking is "
                "implemented",
            )

        has_updated = (
            expected_tick_count > 0
            if expected_tick_count is not None
            else sim_time_s > 0.0
        )
        expected_sides = {"blue", "red"} if has_updated else set()
        if set(previous) != expected_sides:
            raise ValueError(
                "GPS previous_accuracy side topology mismatch",
            )

        staged_previous: dict[str, float] = {}
        for side in sorted(expected_sides):
            value = previous[side]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(
                    f"GPS previous_accuracy[{side!r}] must be finite",
                )
            try:
                normalized = float(value)
            except (OverflowError, ValueError) as exc:
                raise ValueError(
                    f"GPS previous_accuracy[{side!r}] must be finite",
                ) from exc
            if not math.isfinite(normalized) or normalized < 0.0:
                raise ValueError(
                    f"GPS previous_accuracy[{side!r}] must be finite and "
                    "non-negative",
                )
            expected = self._compute_gps_accuracy(
                constellation_manager,
                side,
                sim_time_s,
            ).position_accuracy_m
            if not math.isclose(
                normalized,
                expected,
                rel_tol=0.0,
                abs_tol=1.0e-12,
            ):
                raise ValueError(
                    f"GPS previous_accuracy[{side!r}] disagrees with the "
                    "staged constellation state",
                )
            staged_previous[side] = normalized

        return {
            "previous_accuracy": staged_previous,
            "denial_start": {},
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self._previous_accuracy = state.get("previous_accuracy", {})
        self._denial_start = state.get("denial_start", {})
