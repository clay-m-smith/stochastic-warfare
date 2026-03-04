"""Space-based early warning — missile launch detection.

Models GEO and HEO early warning satellites that detect ballistic missile
launches via IR signature.  Provides early warning time that can improve
BMD engagement probability.

Key physics:
- GEO satellites provide hemisphere coverage (always visible from theater)
- HEO (Molniya) satellites have apogee dwell (~8 hours near apogee)
- Detection delay: constellation-specific (typically 30-90s for IR detection)
- Early warning time = missile_flight_time - detection_delay
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
from stochastic_warfare.space.events import EarlyWarningDetectionEvent

logger = get_logger(__name__)


class EarlyWarningEngine:
    """Space-based early warning for ballistic missile launches."""

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

    def _timestamp(self) -> datetime:
        """Get simulation timestamp from clock, or epoch fallback."""
        if self._clock is not None:
            return self._clock.current_time
        return datetime(2024, 1, 1, tzinfo=timezone.utc)

    def check_launch_detection(
        self,
        launch_position_x: float,
        launch_position_y: float,
        side: str,
        sim_time_s: float,
    ) -> tuple[bool, float]:
        """Check if an early warning satellite can detect a launch.

        Parameters
        ----------
        launch_position_x, launch_position_y : float
            Launch position (lat/lon or ENU — used for event reporting).
        side : str
            Defending side that owns the EW constellation.
        sim_time_s : float
            Current simulation time.

        Returns
        -------
        tuple[bool, float]
            (detected, detection_delay_s).  If not detected, delay = inf.
        """
        ew_type = int(ConstellationType.EARLY_WARNING)
        best_delay = float("inf")
        best_sat_id = ""
        best_confidence = 0.0

        for cdef in self._cm.get_constellations_by_side(side):
            if cdef.constellation_type != ew_type:
                continue

            visible = self._cm.visible_satellites(
                cdef.constellation_id,
                self._config.theater_lat,
                self._config.theater_lon,
                sim_time_s,
                self._config.min_elevation_deg,
            )
            if not visible:
                continue

            delay = cdef.detection_delay_s if cdef.detection_delay_s > 0 else 60.0
            confidence = cdef.detection_confidence if cdef.detection_confidence > 0 else 0.9

            if delay < best_delay:
                best_delay = delay
                best_sat_id = visible[0].satellite_id
                best_confidence = confidence

        if best_delay < float("inf"):
            # Publish detection event
            self._event_bus.publish(EarlyWarningDetectionEvent(
                timestamp=self._timestamp(),
                source=ModuleId.SPACE,
                satellite_id=best_sat_id,
                launch_position_x=launch_position_x,
                launch_position_y=launch_position_y,
                detection_delay_s=best_delay,
                confidence=best_confidence,
            ))
            return (True, best_delay)

        return (False, float("inf"))

    def compute_early_warning_time(
        self,
        detection_delay_s: float,
        missile_flight_time_s: float,
    ) -> float:
        """Compute usable early warning time.

        Returns max(0, flight_time - detection_delay).
        """
        return max(0.0, missile_flight_time_s - detection_delay_s)

    def update(self, dt_s: float, sim_time_s: float) -> None:
        """No periodic work — detection is event-driven via check_launch_detection."""
        pass

    # ── State persistence ────────────────────────────────────────────

    def get_state(self) -> dict[str, Any]:
        return {}

    def set_state(self, state: dict[str, Any]) -> None:
        pass
