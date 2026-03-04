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
        # Find GPS/GLONASS constellations for this side
        visible_total = 0
        gps_types = {int(ConstellationType.GPS), int(ConstellationType.GLONASS)}
        for cdef in self._cm.get_constellations_by_side(side):
            if cdef.constellation_type in gps_types:
                vis = self._cm.visible_satellites(
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
            for cdef in self._cm.get_constellations_by_side(side)
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

    def set_state(self, state: dict[str, Any]) -> None:
        self._previous_accuracy = state.get("previous_accuracy", {})
        self._denial_start = state.get("denial_start", {})
