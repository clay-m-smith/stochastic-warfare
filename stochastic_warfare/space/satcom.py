"""SATCOM dependency modeling.

Models military satellite communications availability and reliability as a
function of constellation health and satellite visibility windows.  Feeds
a reliability factor into the C2 communications engine.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.space.constellations import (
    ConstellationManager,
    ConstellationType,
    SpaceConfig,
)
from stochastic_warfare.space.events import SATCOMWindowEvent

logger = get_logger(__name__)


class SATCOMEngine:
    """Compute SATCOM availability and reliability from constellation health."""

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
        self._previous_available: dict[str, bool] = {}

    def _timestamp(self) -> datetime:
        """Get simulation timestamp from clock, or epoch fallback."""
        if self._clock is not None:
            return self._clock.current_time
        return datetime(2024, 1, 1, tzinfo=timezone.utc)

    def compute_satcom_availability(
        self, side: str, sim_time_s: float,
    ) -> tuple[bool, float]:
        """Check SATCOM availability for a side.

        Returns
        -------
        tuple[bool, float]
            (available, total_bandwidth_bps).
        """
        satcom_type = int(ConstellationType.SATCOM)
        total_bw = 0.0
        any_visible = False

        for cdef in self._cm.get_constellations_by_side(side):
            if cdef.constellation_type != satcom_type:
                continue
            visible = self._cm.visible_satellites(
                cdef.constellation_id,
                self._config.theater_lat,
                self._config.theater_lon,
                sim_time_s,
                self._config.min_elevation_deg,
            )
            if visible:
                any_visible = True
                # Bandwidth scales with number of visible sats
                total_bw += cdef.bandwidth_bps * len(visible)

        # If no SATCOM constellations configured, assume always available
        has_satcom = any(
            cdef.constellation_type == satcom_type
            for cdef in self._cm.get_constellations_by_side(side)
        )
        if not has_satcom:
            return (True, 1e9)

        return (any_visible, total_bw)

    def get_reliability_factor(self, side: str, sim_time_s: float) -> float:
        """Compute SATCOM reliability factor [0.0-1.0] for comms engine.

        Based on constellation health fraction of SATCOM constellations.
        """
        satcom_type = int(ConstellationType.SATCOM)
        health_sum = 0.0
        count = 0

        for cdef in self._cm.get_constellations_by_side(side):
            if cdef.constellation_type != satcom_type:
                continue
            health_sum += self._cm.health_fraction(cdef.constellation_id)
            count += 1

        if count == 0:
            return 1.0  # No SATCOM constellations → assume always available

        return health_sum / count

    def update(self, dt_s: float, sim_time_s: float) -> None:
        """Check SATCOM windows and emit events on state changes."""
        for side in ("blue", "red"):
            available, bandwidth = self.compute_satcom_availability(side, sim_time_s)
            prev = self._previous_available.get(side, available)
            if available != prev:
                # Find a representative satellite for the event
                satcom_type = int(ConstellationType.SATCOM)
                sat_id = ""
                for cdef in self._cm.get_constellations_by_side(side):
                    if cdef.constellation_type != satcom_type:
                        continue
                    visible = self._cm.visible_satellites(
                        cdef.constellation_id,
                        self._config.theater_lat,
                        self._config.theater_lon,
                        sim_time_s,
                        self._config.min_elevation_deg,
                    )
                    if visible:
                        sat_id = visible[0].satellite_id
                        break

                self._event_bus.publish(SATCOMWindowEvent(
                    timestamp=self._timestamp(),
                    source=ModuleId.SPACE,
                    side=side,
                    satellite_id=sat_id,
                    window_open=available,
                    bandwidth_bps=bandwidth,
                ))
            self._previous_available[side] = available

    # ── State persistence ────────────────────────────────────────────

    def get_state(self) -> dict[str, Any]:
        return {"previous_available": dict(self._previous_available)}

    def set_state(self, state: dict[str, Any]) -> None:
        self._previous_available = state.get("previous_available", {})
