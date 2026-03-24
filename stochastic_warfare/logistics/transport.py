"""Transport engine — physical movement of supplies along routes.

Manages transport missions (convoys, airlift, rail, sealift) with
log-normal transit delays, environmental speed modifiers, and airdrop
scatter.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.logistics.consumption import EnvironmentConditions, GroundState
from stochastic_warfare.logistics.events import (
    ConvoyArrivedEvent,
    ConvoyDestroyedEvent,
    ConvoyDispatchedEvent,
)
from stochastic_warfare.logistics.supply_network import SupplyRoute, TransportMode

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# YAML-loaded transport profile
# ---------------------------------------------------------------------------


class TransportProfile(BaseModel):
    """Physical characteristics of a transport mode, loaded from YAML."""

    profile_id: str
    mode: str
    capacity_tons: float
    speed_mps: float
    vulnerability: float  # 0-1 base probability of destruction per interdiction
    weather_ceiling_m: float | None = None
    weather_visibility_m: float | None = None


class TransportProfileLoader:
    """Load and cache ``TransportProfile`` from YAML files."""

    def __init__(self, data_dir: Path | None = None) -> None:
        if data_dir is None:
            data_dir = (
                Path(__file__).resolve().parents[2]
                / "data"
                / "logistics"
                / "transport_profiles"
            )
        self._data_dir = data_dir
        self._definitions: dict[str, TransportProfile] = {}

    def load_definition(self, path: Path) -> TransportProfile:
        """Load a single YAML file and cache it."""
        import yaml

        with open(path) as f:
            data = yaml.safe_load(f)
        defn = TransportProfile.model_validate(data)
        self._definitions[defn.profile_id] = defn
        return defn

    def load_all(self) -> None:
        """Load every ``*.yaml`` file under the data directory."""
        for path in sorted(self._data_dir.rglob("*.yaml")):
            self.load_definition(path)
        logger.info("Loaded %d transport profiles", len(self._definitions))

    def get_definition(self, profile_id: str) -> TransportProfile:
        """Return a cached definition; raises ``KeyError`` if not found."""
        return self._definitions[profile_id]

    def available_profiles(self) -> list[str]:
        """Return sorted list of loaded profile IDs."""
        return sorted(self._definitions.keys())


# ---------------------------------------------------------------------------
# Transport mission
# ---------------------------------------------------------------------------


@dataclass
class TransportMission:
    """A single transport mission moving cargo along a route."""

    mission_id: str
    mode: TransportMode
    route: list[SupplyRoute]
    cargo: dict[int, dict[str, float]]  # supply_class -> {item_id -> qty}
    origin_id: str
    destination_id: str
    departure_time: float  # simulation hours
    estimated_arrival: float  # simulation hours
    progress_fraction: float = 0.0
    status: str = "IN_TRANSIT"  # IN_TRANSIT, ARRIVED, DESTROYED, DELAYED
    position: Position = Position(0.0, 0.0)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class TransportConfig(BaseModel):
    """Tuning parameters for transport engine."""

    convoy_base_speed_mps: float = 8.0
    airlift_speed_mps: float = 130.0
    rail_speed_mps: float = 15.0
    sealift_speed_mps: float = 8.0
    airdrop_accuracy_cep_m: float = 200.0
    delay_sigma: float = 0.3  # log-normal sigma for transit delay
    mud_speed_fraction: float = 0.5
    snow_speed_fraction: float = 0.7


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class TransportEngine:
    """Manage transport missions and advance them over time.

    Parameters
    ----------
    event_bus : EventBus
        Publishes ``ConvoyDispatchedEvent``, ``ConvoyArrivedEvent``,
        ``ConvoyDestroyedEvent``.
    rng : numpy.random.Generator
        Deterministic PRNG stream.
    loader : TransportProfileLoader | None
        YAML-loaded transport profiles.
    config : TransportConfig | None
        Tuning parameters.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        loader: TransportProfileLoader | None = None,
        config: TransportConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._loader = loader or TransportProfileLoader()
        self._config = config or TransportConfig()
        self._missions: dict[str, TransportMission] = {}
        self._sim_time: float = 0.0

    def dispatch(
        self,
        mission_id: str,
        mode: TransportMode,
        route: list[SupplyRoute],
        cargo: dict[int, dict[str, float]],
        origin_id: str,
        destination_id: str,
        timestamp: datetime | None = None,
    ) -> TransportMission:
        """Create and register a new transport mission."""
        # Compute base transit time from route
        base_time = sum(r.base_transit_time_hours / max(r.condition, 0.01) for r in route)
        # Apply log-normal delay
        delay_factor = self._rng.lognormal(0.0, self._config.delay_sigma)
        estimated_arrival = self._sim_time + base_time * delay_factor

        # Compute total cargo tons for event
        cargo_tons = sum(
            sum(items.values()) for items in cargo.values()
        )

        mission = TransportMission(
            mission_id=mission_id,
            mode=mode,
            route=route,
            cargo=cargo,
            origin_id=origin_id,
            destination_id=destination_id,
            departure_time=self._sim_time,
            estimated_arrival=estimated_arrival,
            position=Position(0.0, 0.0),
        )
        self._missions[mission_id] = mission

        if timestamp is not None:
            self._event_bus.publish(ConvoyDispatchedEvent(
                timestamp=timestamp,
                source=ModuleId.LOGISTICS,
                mission_id=mission_id,
                origin_id=origin_id,
                destination_id=destination_id,
                transport_mode=int(mode),
                cargo_tons=cargo_tons,
            ))

        logger.info(
            "Dispatched %s (%s) %s -> %s, ETA %.1f hrs",
            mission_id, mode.name, origin_id, destination_id,
            estimated_arrival - self._sim_time,
        )
        return mission

    def update(
        self,
        dt_hours: float,
        env: EnvironmentConditions | None = None,
        timestamp: datetime | None = None,
        escort_strength: float = 1.0,
        threat_level: float = 0.0,
    ) -> list[TransportMission]:
        """Advance all in-transit missions.  Return newly completed missions.

        Parameters
        ----------
        escort_strength:
            12b-3: Escort protection level (0.0–1.0). Higher = better protection.
        threat_level:
            12b-3: Threat level along routes (0.0–1.0). Higher = more interdiction risk.
        """
        if env is None:
            env = EnvironmentConditions()
        self._sim_time += dt_hours
        completed: list[TransportMission] = []

        for mission in list(self._missions.values()):
            if mission.status != "IN_TRANSIT":
                continue

            # Check weather cancellation for airlift
            if mission.mode == TransportMode.AIR:
                if not self._check_airlift_weather(env):
                    mission.status = "DELAYED"
                    logger.debug("Airlift %s delayed by weather", mission.mission_id)
                    continue

            # 12b-3: Per-tick interdiction roll
            if threat_level > 0.0:
                vulnerability = 0.5  # Default convoy vulnerability
                p_interdict = threat_level * vulnerability * (1.0 - escort_strength * 0.8)
                p_interdict = max(0.0, min(1.0, p_interdict)) * dt_hours
                if self._rng.random() < p_interdict:
                    self.destroy_mission(
                        mission.mission_id,
                        cause="interdiction",
                        timestamp=timestamp,
                    )
                    continue

            # Apply environmental speed modifier
            speed_factor = self._compute_speed_factor(mission.mode, env)

            # Advance progress
            total_time = mission.estimated_arrival - mission.departure_time
            if total_time > 0:
                effective_dt = dt_hours * speed_factor
                mission.progress_fraction += effective_dt / total_time
                mission.progress_fraction = min(mission.progress_fraction, 1.0)

            if mission.progress_fraction >= 1.0:
                mission.status = "ARRIVED"
                completed.append(mission)
                cargo_tons = sum(
                    sum(items.values()) for items in mission.cargo.values()
                )
                if timestamp is not None:
                    self._event_bus.publish(ConvoyArrivedEvent(
                        timestamp=timestamp,
                        source=ModuleId.LOGISTICS,
                        mission_id=mission.mission_id,
                        destination_id=mission.destination_id,
                        cargo_tons=cargo_tons,
                    ))
                logger.info("Mission %s arrived", mission.mission_id)

        return completed

    def destroy_mission(
        self,
        mission_id: str,
        position: Position | None = None,
        cause: str = "interdiction",
        timestamp: datetime | None = None,
    ) -> None:
        """Destroy a transport mission en route."""
        mission = self._missions[mission_id]
        mission.status = "DESTROYED"
        cargo_tons = sum(
            sum(items.values()) for items in mission.cargo.values()
        )
        if timestamp is not None:
            self._event_bus.publish(ConvoyDestroyedEvent(
                timestamp=timestamp,
                source=ModuleId.LOGISTICS,
                mission_id=mission.mission_id,
                position=position or Position(0.0, 0.0),
                cargo_lost_tons=cargo_tons,
                cause=cause,
            ))
        logger.info("Mission %s destroyed: %s", mission_id, cause)

    def airdrop(
        self,
        target_pos: Position,
        cargo: dict[int, dict[str, float]],
        wind_speed_mps: float = 0.0,
        wind_direction_rad: float = 0.0,
    ) -> tuple[Position, dict[int, dict[str, float]]]:
        """Compute airdrop landing position with scatter.

        Returns ``(actual_position, cargo)``.
        """
        cep = self._config.airdrop_accuracy_cep_m
        # Wind adds systematic offset
        wind_offset_e = wind_speed_mps * 10.0 * math.sin(wind_direction_rad)
        wind_offset_n = wind_speed_mps * 10.0 * math.cos(wind_direction_rad)
        # Random scatter (Rayleigh-distributed)
        sigma = cep / 1.1774  # CEP = sigma * sqrt(2*ln(2))
        scatter_e = self._rng.normal(0.0, sigma) + wind_offset_e
        scatter_n = self._rng.normal(0.0, sigma) + wind_offset_n
        actual = Position(
            target_pos.easting + scatter_e,
            target_pos.northing + scatter_n,
            target_pos.altitude,
        )
        return actual, cargo

    def get_mission(self, mission_id: str) -> TransportMission:
        """Return a mission; raises ``KeyError`` if not found."""
        return self._missions[mission_id]

    def active_missions(self) -> list[TransportMission]:
        """Return all in-transit missions."""
        return [m for m in self._missions.values() if m.status == "IN_TRANSIT"]

    def _check_airlift_weather(self, env: EnvironmentConditions) -> bool:
        """Return True if weather allows airlift operations."""
        # Default minimums: 150m ceiling, 1600m visibility
        min_visibility = 1600.0
        if env.visibility_m < min_visibility:
            return False
        return True

    def _compute_speed_factor(
        self, mode: TransportMode, env: EnvironmentConditions,
    ) -> float:
        """Compute environmental speed modifier (0-1)."""
        if mode in (TransportMode.ROAD, TransportMode.CROSS_COUNTRY):
            if env.ground_state == int(GroundState.MUD):
                return self._config.mud_speed_fraction
            if env.ground_state == int(GroundState.SNOW):
                return self._config.snow_speed_fraction
        return 1.0

    # -- State protocol --

    def get_state(self) -> dict:
        """Serialize for checkpoint."""
        return {
            "sim_time": self._sim_time,
            "missions": {
                mid: {
                    "mission_id": m.mission_id,
                    "mode": int(m.mode),
                    "cargo": m.cargo,
                    "origin_id": m.origin_id,
                    "destination_id": m.destination_id,
                    "departure_time": m.departure_time,
                    "estimated_arrival": m.estimated_arrival,
                    "progress_fraction": m.progress_fraction,
                    "status": m.status,
                    "position": list(m.position),
                    "route_ids": [r.route_id for r in m.route],
                }
                for mid, m in self._missions.items()
            },
        }

    def set_state(self, state: dict) -> None:
        """Restore from checkpoint."""
        self._sim_time = state.get("sim_time", 0.0)
        self._missions.clear()
        for mid, md in state["missions"].items():
            self._missions[mid] = TransportMission(
                mission_id=md["mission_id"],
                mode=TransportMode(md["mode"]),
                route=[],  # route objects not serialized; reconnect in sim loop
                cargo=md["cargo"],
                origin_id=md["origin_id"],
                destination_id=md["destination_id"],
                departure_time=md["departure_time"],
                estimated_arrival=md["estimated_arrival"],
                progress_fraction=md["progress_fraction"],
                status=md["status"],
                position=Position(*md["position"]),
            )
