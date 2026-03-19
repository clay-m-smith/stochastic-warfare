"""Space-based ISR (Intelligence, Surveillance, Reconnaissance).

Models satellite imaging passes over the theater.  Optical satellites are
blocked by cloud cover; SAR satellites are all-weather.  Resolution
determines the smallest unit type detectable.
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
from stochastic_warfare.space.events import SatelliteOverpassEvent

logger = get_logger(__name__)

# Resolution thresholds — max sensor resolution to detect each size category
_RESOLUTION_THRESHOLD: dict[str, float] = {
    "vehicle": 0.5,   # need <0.5m to see individual vehicles
    "platoon": 2.0,   # need <2m to see platoon positions
    "company": 5.0,   # need <5m to see company formations
    "battalion": 15.0, # need <15m to see battalion area
}


class SpaceISREngine:
    """Space-based ISR overpass and reporting engine."""

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
        self._last_overpass_time: dict[str, float] = {}  # sat_id → last time
        # Phase 65: buffer ISR reports for downstream fusion
        self._recent_reports: list[dict[str, Any]] = []

    def _timestamp(self) -> datetime:
        """Get simulation timestamp from clock, or epoch fallback."""
        if self._clock is not None:
            return self._clock.current_time
        return datetime(2024, 1, 1, tzinfo=timezone.utc)

    def check_overpass(self, side: str, sim_time_s: float) -> list[SatelliteOverpassEvent]:
        """Check which ISR satellites have overpass of the theater now."""
        events: list[SatelliteOverpassEvent] = []
        isr_types = {
            int(ConstellationType.IMAGING_OPTICAL),
            int(ConstellationType.IMAGING_SAR),
            int(ConstellationType.SIGINT),
        }

        for cdef in self._cm.get_constellations_by_side(side):
            if cdef.constellation_type not in isr_types:
                continue
            visible = self._cm.visible_satellites(
                cdef.constellation_id,
                self._config.theater_lat,
                self._config.theater_lon,
                sim_time_s,
                self._config.min_elevation_deg,
            )
            for sat in visible:
                last = self._last_overpass_time.get(sat.satellite_id, -1e9)
                # Only report once per overpass (hysteresis: 60s minimum gap)
                if sim_time_s - last < 60.0:
                    continue
                self._last_overpass_time[sat.satellite_id] = sim_time_s
                evt = SatelliteOverpassEvent(
                    timestamp=self._timestamp(),
                    source=ModuleId.SPACE,
                    satellite_id=sat.satellite_id,
                    constellation_id=cdef.constellation_id,
                    side=side,
                    overpass_start=True,
                    coverage_center_x=self._config.theater_lat,
                    coverage_center_y=self._config.theater_lon,
                    coverage_radius_m=cdef.sensor_swath_km * 1000.0 / 2.0,
                    resolution_m=cdef.sensor_resolution_m,
                )
                events.append(evt)
                self._event_bus.publish(evt)
        return events

    def generate_isr_reports(
        self,
        side: str,
        targets: list[Any],
        sim_time_s: float,
        cloud_cover: float = 0.0,
    ) -> list[dict[str, Any]]:
        """Generate ISR reports from currently visible satellites.

        Parameters
        ----------
        targets : list
            Target entities with `entity_id`, `position`, `unit_type_id` attributes.
        cloud_cover : float
            Cloud cover fraction [0, 1].  Optical blocked above 0.7.

        Returns
        -------
        list[dict]
            Reports with target_id, satellite_id, resolution, delay_s.
        """
        reports: list[dict[str, Any]] = []
        isr_types = {
            int(ConstellationType.IMAGING_OPTICAL),
            int(ConstellationType.IMAGING_SAR),
        }

        for cdef in self._cm.get_constellations_by_side(side):
            if cdef.constellation_type not in isr_types:
                continue

            # Optical blocked by cloud
            if (cdef.sensor_type == "optical"
                    and self._config.cloud_cover_blocks_optical
                    and cloud_cover > 0.7):
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

            for target in targets:
                # Check resolution threshold
                unit_size = self._estimate_unit_size(target)
                threshold = _RESOLUTION_THRESHOLD.get(unit_size, 999.0)
                if cdef.sensor_resolution_m > threshold:
                    continue  # Can't resolve this target

                reports.append({
                    "target_id": getattr(target, "entity_id", str(target)),
                    "satellite_id": visible[0].satellite_id,
                    "constellation_id": cdef.constellation_id,
                    "resolution_m": cdef.sensor_resolution_m,
                    "delay_s": self._config.isr_processing_delay_s,
                    "sensor_type": cdef.sensor_type,
                    "target_position": getattr(target, "position", None),
                    "timestamp": sim_time_s,
                })

        # Phase 65: buffer reports for downstream fusion
        self._recent_reports.extend(reports)
        return reports

    def _estimate_unit_size(self, target: Any) -> str:
        """Estimate unit size category for resolution filtering."""
        # Check for personnel_count or strength attribute
        strength = getattr(target, "personnel_count", None)
        if strength is None:
            strength = getattr(target, "strength", 1)
        if strength <= 4:
            return "vehicle"
        elif strength <= 40:
            return "platoon"
        elif strength <= 200:
            return "company"
        else:
            return "battalion"

    def update(
        self,
        dt_s: float,
        sim_time_s: float,
        targets_by_side: dict[str, list[Any]] | None = None,
        cloud_cover: float = 0.0,
    ) -> None:
        """Run ISR overpass checks and generate reports."""
        for side in ("blue", "red"):
            self.check_overpass(side, sim_time_s)
            # Generate reports against opposing side's forces
            if targets_by_side:
                opposing = [s for s in targets_by_side if s != side]
                for opp in opposing:
                    self.generate_isr_reports(
                        side, targets_by_side.get(opp, []),
                        sim_time_s, cloud_cover,
                    )

    def get_recent_reports(self, *, clear: bool = True) -> list[dict[str, Any]]:
        """Return buffered ISR reports, optionally clearing the buffer."""
        reports = list(self._recent_reports)
        if clear:
            self._recent_reports.clear()
        return reports

    # ── State persistence ────────────────────────────────────────────

    def get_state(self) -> dict[str, Any]:
        return {
            "last_overpass_time": dict(self._last_overpass_time),
            "recent_reports": list(self._recent_reports),
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self._last_overpass_time = state.get("last_overpass_time", {})
        self._recent_reports = state.get("recent_reports", [])
