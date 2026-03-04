"""Constellation management, SpaceConfig, and top-level SpaceEngine.

Manages satellite constellations (GPS, GLONASS, imaging, SIGINT, early
warning, SATCOM) as collections of :class:`SatelliteState` objects.
Distributes satellites across orbital planes, propagates orbits, and
provides per-type/per-side queries.
"""

from __future__ import annotations

import enum
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.space.events import ConstellationDegradedEvent
from stochastic_warfare.space.orbits import (
    OrbitalElements,
    OrbitalMechanicsEngine,
    SatelliteState,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums & config models
# ---------------------------------------------------------------------------


class ConstellationType(enum.IntEnum):
    """Type of satellite constellation."""

    GPS = 0
    GLONASS = 1
    IMAGING_OPTICAL = 2
    IMAGING_SAR = 3
    SIGINT = 4
    EARLY_WARNING = 5
    SATCOM = 6


class ConstellationDefinition(BaseModel):
    """YAML-loaded constellation definition."""

    constellation_id: str
    display_name: str = ""
    constellation_type: int = 0  # ConstellationType value
    side: str = "blue"
    num_satellites: int = 24
    orbital_elements_template: dict[str, float] = {}
    plane_count: int = 6
    sats_per_plane: int = 4
    sensor_resolution_m: float = 0.0
    sensor_swath_km: float = 0.0
    sensor_type: str = "none"  # "optical" | "sar" | "ir" | "none"
    bandwidth_bps: float = 0.0
    detection_delay_s: float = 0.0
    detection_confidence: float = 0.0


class SpaceConfig(BaseModel):
    """Configuration for the space domain."""

    enable_space: bool = False
    theater_lat: float = 0.0
    theater_lon: float = 0.0
    min_elevation_deg: float = 5.0
    update_interval_s: float = 3600.0
    gps_sigma_range_m: float = 3.0
    ins_drift_rate_m_per_s: float = 0.514  # ~1 nmi/hr
    ins_initial_sigma_m: float = 10.0
    cloud_cover_blocks_optical: bool = True
    isr_processing_delay_s: float = 300.0
    ew_processing_delay_s: float = 60.0
    debris_fragment_mean: float = 500.0
    debris_collision_prob_per_orbit: float = 1e-6


# ---------------------------------------------------------------------------
# ConstellationManager
# ---------------------------------------------------------------------------


class ConstellationManager:
    """Manages satellite constellations — creation, propagation, queries."""

    def __init__(
        self,
        orbits: OrbitalMechanicsEngine,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: SpaceConfig | None = None,
    ) -> None:
        self._orbits = orbits
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or SpaceConfig()
        self._constellations: dict[str, ConstellationDefinition] = {}
        self._satellites: dict[str, SatelliteState] = {}
        self._constellation_sats: dict[str, list[str]] = {}
        self._sim_time_s: float = 0.0

    def add_constellation(self, definition: ConstellationDefinition) -> None:
        """Add a constellation and distribute satellites across planes."""
        cid = definition.constellation_id
        self._constellations[cid] = definition
        self._constellation_sats[cid] = []

        template = definition.orbital_elements_template
        a = template.get("semi_major_axis_m", 26_559_700.0)
        e = template.get("eccentricity", 0.0)
        inc = template.get("inclination_deg", 55.0)
        arg_pe = template.get("arg_perigee_deg", 0.0)
        base_raan = template.get("raan_deg", 0.0)

        planes = max(1, definition.plane_count)
        spp = max(1, definition.sats_per_plane)
        total = min(definition.num_satellites, planes * spp)

        idx = 0
        for p in range(planes):
            if idx >= total:
                break
            raan = (base_raan + 360.0 / planes * p) % 360.0
            for s in range(spp):
                if idx >= total:
                    break
                nu = (360.0 / spp * s) % 360.0
                sid = f"{cid}_p{p}_s{s}"
                elems = OrbitalElements(
                    semi_major_axis_m=a,
                    eccentricity=e,
                    inclination_deg=inc,
                    raan_deg=raan,
                    arg_perigee_deg=arg_pe,
                    true_anomaly_deg=nu,
                )
                sat = SatelliteState(
                    satellite_id=sid,
                    constellation_id=cid,
                    elements=elems,
                    side=definition.side,
                    current_true_anomaly_deg=nu,
                    current_raan_deg=raan,
                )
                self._satellites[sid] = sat
                self._constellation_sats[cid].append(sid)
                idx += 1

    def update(self, dt_s: float, sim_time_s: float) -> None:
        """Propagate all active satellites by *dt_s*."""
        self._sim_time_s = sim_time_s
        for sat in self._satellites.values():
            if sat.is_active:
                self._orbits.propagate(sat, dt_s)

    def visible_satellites(
        self,
        constellation_id: str,
        theater_lat: float,
        theater_lon: float,
        sim_time_s: float,
        min_elev: float = 5.0,
    ) -> list[SatelliteState]:
        """Return satellites in a constellation visible from a ground point."""
        result: list[SatelliteState] = []
        for sid in self._constellation_sats.get(constellation_id, []):
            sat = self._satellites[sid]
            if sat.is_active and self._orbits.is_visible_from(
                sat, theater_lat, theater_lon, sim_time_s, min_elev,
            ):
                result.append(sat)
        return result

    def get_constellations_by_type(
        self, ctype: ConstellationType,
    ) -> list[ConstellationDefinition]:
        """Return constellation definitions of a given type."""
        return [
            d for d in self._constellations.values()
            if d.constellation_type == int(ctype)
        ]

    def get_constellations_by_side(self, side: str) -> list[ConstellationDefinition]:
        """Return constellation definitions for a given side."""
        return [d for d in self._constellations.values() if d.side == side]

    def degrade_constellation(
        self,
        constellation_id: str,
        count: int,
        cause: str,
        timestamp: Any = None,
    ) -> list[str]:
        """Deactivate *count* active satellites from a constellation.

        Returns list of deactivated satellite IDs.
        """
        sids = self._constellation_sats.get(constellation_id, [])
        active = [sid for sid in sids if self._satellites[sid].is_active]
        prev_count = len(active)
        to_kill = min(count, len(active))

        # Deactivate from the end (arbitrary but deterministic)
        killed: list[str] = []
        for i in range(to_kill):
            sid = active[-(i + 1)]
            self._satellites[sid].is_active = False
            killed.append(sid)

        if killed and timestamp is not None:
            self._event_bus.publish(ConstellationDegradedEvent(
                timestamp=timestamp,
                source=__import__(
                    "stochastic_warfare.core.types", fromlist=["ModuleId"],
                ).ModuleId.SPACE,
                constellation_id=constellation_id,
                previous_count=prev_count,
                new_count=prev_count - len(killed),
                cause=cause,
            ))

        return killed

    def active_count(self, constellation_id: str) -> int:
        """Number of active satellites in a constellation."""
        return sum(
            1 for sid in self._constellation_sats.get(constellation_id, [])
            if self._satellites[sid].is_active
        )

    def health_fraction(self, constellation_id: str) -> float:
        """Fraction of active satellites in a constellation."""
        sids = self._constellation_sats.get(constellation_id, [])
        if not sids:
            return 0.0
        active = sum(1 for sid in sids if self._satellites[sid].is_active)
        return active / len(sids)

    def get_satellite(self, satellite_id: str) -> SatelliteState | None:
        """Look up a satellite by ID."""
        return self._satellites.get(satellite_id)

    def all_satellites(self) -> list[SatelliteState]:
        """Return all satellites."""
        return list(self._satellites.values())

    # ── State persistence ────────────────────────────────────────────

    def get_state(self) -> dict[str, Any]:
        state: dict[str, Any] = {"sim_time_s": self._sim_time_s, "satellites": {}}
        for sid, sat in self._satellites.items():
            state["satellites"][sid] = {
                "is_active": sat.is_active,
                "true_anomaly_deg": sat.current_true_anomaly_deg,
                "raan_deg": sat.current_raan_deg,
            }
        return state

    def set_state(self, state: dict[str, Any]) -> None:
        self._sim_time_s = state.get("sim_time_s", 0.0)
        for sid, sdata in state.get("satellites", {}).items():
            if sid in self._satellites:
                self._satellites[sid].is_active = sdata["is_active"]
                self._satellites[sid].current_true_anomaly_deg = sdata["true_anomaly_deg"]
                self._satellites[sid].current_raan_deg = sdata["raan_deg"]


# ---------------------------------------------------------------------------
# SpaceEngine — top-level orchestrator
# ---------------------------------------------------------------------------


class SpaceEngine:
    """Top-level orchestrator wrapping all space sub-engines.

    Each sub-engine (GPS, ISR, early warning, SATCOM, ASAT) is optional
    and set after construction.
    """

    def __init__(
        self,
        config: SpaceConfig,
        constellation_manager: ConstellationManager,
        gps_engine: Any = None,
        isr_engine: Any = None,
        early_warning_engine: Any = None,
        satcom_engine: Any = None,
        asat_engine: Any = None,
    ) -> None:
        self._config = config
        self._constellation_manager = constellation_manager
        self._gps_engine = gps_engine
        self._isr_engine = isr_engine
        self._early_warning_engine = early_warning_engine
        self._satcom_engine = satcom_engine
        self._asat_engine = asat_engine

    @property
    def constellation_manager(self) -> ConstellationManager:
        return self._constellation_manager

    @property
    def gps_engine(self) -> Any:
        return self._gps_engine

    @property
    def isr_engine(self) -> Any:
        return self._isr_engine

    @property
    def early_warning_engine(self) -> Any:
        return self._early_warning_engine

    @property
    def satcom_engine(self) -> Any:
        return self._satcom_engine

    @property
    def asat_engine(self) -> Any:
        return self._asat_engine

    def update(
        self,
        dt_s: float,
        sim_time_s: float,
        em_environment: Any = None,
        comms_engine: Any = None,
        targets_by_side: dict[str, list[Any]] | None = None,
        cloud_cover: float = 0.0,
    ) -> None:
        """Update all space sub-engines for the current tick."""
        if not self._config.enable_space:
            return

        # 1. Propagate constellations
        self._constellation_manager.update(dt_s, sim_time_s)

        # 2. GPS → drives EM environment
        if self._gps_engine is not None:
            self._gps_engine.update(dt_s, sim_time_s)
            if em_environment is not None and hasattr(em_environment, "set_constellation_accuracy"):
                # Use worst-case (max) accuracy across sides — EMEnvironment
                # is a shared state, not per-side.
                worst_accuracy = 0.0
                for side in ("blue", "red"):
                    gps_state = self._gps_engine.compute_gps_accuracy(side, sim_time_s)
                    worst_accuracy = max(worst_accuracy, gps_state.position_accuracy_m)
                em_environment.set_constellation_accuracy(worst_accuracy)

        # 3. ISR
        if self._isr_engine is not None:
            self._isr_engine.update(dt_s, sim_time_s, targets_by_side, cloud_cover)

        # 4. Early warning
        if self._early_warning_engine is not None:
            self._early_warning_engine.update(dt_s, sim_time_s)

        # 5. SATCOM → drives comms engine
        if self._satcom_engine is not None:
            self._satcom_engine.update(dt_s, sim_time_s)
            if comms_engine is not None and hasattr(comms_engine, "set_satcom_reliability"):
                for side in ("blue", "red"):
                    factor = self._satcom_engine.get_reliability_factor(side, sim_time_s)
                    comms_engine.set_satcom_reliability(factor)

        # 6. ASAT debris
        if self._asat_engine is not None:
            self._asat_engine.update(dt_s, sim_time_s)

    # ── State persistence ────────────────────────────────────────────

    def get_state(self) -> dict[str, Any]:
        state: dict[str, Any] = {}
        state["constellation_manager"] = self._constellation_manager.get_state()
        for name, eng in [
            ("gps_engine", self._gps_engine),
            ("isr_engine", self._isr_engine),
            ("early_warning_engine", self._early_warning_engine),
            ("satcom_engine", self._satcom_engine),
            ("asat_engine", self._asat_engine),
        ]:
            if eng is not None and hasattr(eng, "get_state"):
                state[name] = eng.get_state()
        return state

    def set_state(self, state: dict[str, Any]) -> None:
        if "constellation_manager" in state:
            self._constellation_manager.set_state(state["constellation_manager"])
        for name, eng in [
            ("gps_engine", self._gps_engine),
            ("isr_engine", self._isr_engine),
            ("early_warning_engine", self._early_warning_engine),
            ("satcom_engine", self._satcom_engine),
            ("asat_engine", self._asat_engine),
        ]:
            if eng is not None and name in state and hasattr(eng, "set_state"):
                eng.set_state(state[name])
