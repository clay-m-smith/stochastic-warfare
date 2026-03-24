"""Missile flight modeling — TBM, cruise, coastal defense SSM.

Models kill chain phases (detect → localize → authorize → launch → flight →
terminal), flight profiles (ballistic arc, terrain-following, sea-skimming),
and kill chain latency constraints.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.combat.ammunition import AmmoDefinition
from stochastic_warfare.combat.damage import DamageEngine
from stochastic_warfare.combat.events import MissileLaunchEvent
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position

logger = get_logger(__name__)


class MissileType(enum.IntEnum):
    """Surface-to-surface missile classification."""

    TBM_SHORT = 0
    TBM_MEDIUM = 1
    TBM_INTERMEDIATE = 2
    CRUISE_SUBSONIC = 3
    CRUISE_SUPERSONIC = 4
    COASTAL_DEFENSE_SSM = 5


class KillChainPhase(enum.IntEnum):
    """Phases of the kill chain."""

    DETECT = 0
    LOCALIZE = 1
    AUTHORIZE = 2
    LAUNCH = 3
    FLIGHT = 4
    TERMINAL = 5


class MissileConfig(BaseModel):
    """Tunable parameters for missile flight."""

    tbm_short_max_range_m: float = 300_000.0
    tbm_medium_max_range_m: float = 1_000_000.0
    cruise_altitude_m: float = 50.0
    sea_skim_altitude_m: float = 5.0
    kill_chain_base_latency_s: float = 120.0


@dataclass
class FlightProfile:
    """Missile flight profile description."""

    missile_type: MissileType
    launch_pos: Position
    target_pos: Position
    max_altitude_m: float = 0.0
    cruise_altitude_m: float = 0.0
    flight_time_s: float = 0.0
    speed_mps: float = 0.0
    range_m: float = 0.0


@dataclass
class MissileFlightState:
    """Active missile in-flight state."""

    missile_id: str
    ammo_id: str
    launcher_id: str
    target_pos: Position
    current_pos: Position
    flight_profile: FlightProfile
    time_elapsed_s: float = 0.0
    phase: KillChainPhase = KillChainPhase.FLIGHT
    active: bool = True

    def get_state(self) -> dict[str, Any]:
        return {
            "missile_id": self.missile_id,
            "ammo_id": self.ammo_id,
            "launcher_id": self.launcher_id,
            "target_pos": tuple(self.target_pos),
            "current_pos": tuple(self.current_pos),
            "time_elapsed_s": self.time_elapsed_s,
            "phase": int(self.phase),
            "active": self.active,
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self.missile_id = state["missile_id"]
        self.ammo_id = state["ammo_id"]
        self.launcher_id = state["launcher_id"]
        self.target_pos = Position(*state["target_pos"])
        self.current_pos = Position(*state["current_pos"])
        self.time_elapsed_s = state["time_elapsed_s"]
        self.phase = KillChainPhase(state["phase"])
        self.active = state["active"]


@dataclass
class MissileImpactResult:
    """Result of a missile reaching its target."""

    missile_id: str
    impact_pos: Position
    hit: bool
    damage_fraction: float = 0.0


class MissileEngine:
    """Models missile launch, flight, and terminal phase.

    Parameters
    ----------
    damage_engine:
        For resolving missile impact damage.
    event_bus:
        For publishing missile events.
    rng:
        PRNG generator.
    config:
        Tunable parameters.
    """

    def __init__(
        self,
        damage_engine: DamageEngine,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: MissileConfig | None = None,
    ) -> None:
        self._damage = damage_engine
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or MissileConfig()
        self._active_missiles: list[MissileFlightState] = []

    def compute_flight_profile(
        self,
        missile_type: MissileType,
        ammo: AmmoDefinition,
        launch_pos: Position,
        target_pos: Position,
    ) -> FlightProfile:
        """Compute flight profile for a missile type.

        Parameters
        ----------
        missile_type:
            Classification of the missile.
        ammo:
            Ammo definition for speed/flight time.
        launch_pos:
            Launch position.
        target_pos:
            Target position.
        """
        dx = target_pos.easting - launch_pos.easting
        dy = target_pos.northing - launch_pos.northing
        range_m = math.sqrt(dx * dx + dy * dy)

        speed = ammo.max_speed_mps if ammo.max_speed_mps > 0 else 250.0

        if missile_type in (MissileType.TBM_SHORT, MissileType.TBM_MEDIUM,
                           MissileType.TBM_INTERMEDIATE):
            # Ballistic arc — max altitude ~ range/4 for 45° launch
            max_alt = range_m * 0.25
            cruise_alt = 0.0
            flight_time = ammo.flight_time_s if ammo.flight_time_s > 0 else range_m / speed
        elif missile_type == MissileType.CRUISE_SUPERSONIC:
            max_alt = 100.0
            cruise_alt = 100.0
            flight_time = range_m / speed
        elif missile_type == MissileType.COASTAL_DEFENSE_SSM:
            max_alt = 20.0
            cruise_alt = self._config.sea_skim_altitude_m
            flight_time = range_m / speed
        else:
            # CRUISE_SUBSONIC
            max_alt = self._config.cruise_altitude_m
            cruise_alt = self._config.cruise_altitude_m
            flight_time = ammo.flight_time_s if ammo.flight_time_s > 0 else range_m / speed

        return FlightProfile(
            missile_type=missile_type,
            launch_pos=launch_pos,
            target_pos=target_pos,
            max_altitude_m=max_alt,
            cruise_altitude_m=cruise_alt,
            flight_time_s=flight_time,
            speed_mps=speed,
            range_m=range_m,
        )

    def launch_missile(
        self,
        launcher_id: str,
        missile_id: str,
        target_pos: Position,
        launch_pos: Position,
        ammo: AmmoDefinition,
        missile_type: MissileType = MissileType.CRUISE_SUBSONIC,
        timestamp: Any = None,
    ) -> MissileFlightState:
        """Launch a missile and begin tracking its flight."""
        profile = self.compute_flight_profile(
            missile_type, ammo, launch_pos, target_pos,
        )

        state = MissileFlightState(
            missile_id=missile_id,
            ammo_id=ammo.ammo_id,
            launcher_id=launcher_id,
            target_pos=target_pos,
            current_pos=launch_pos,
            flight_profile=profile,
        )
        self._active_missiles.append(state)

        if timestamp is not None:
            self._event_bus.publish(MissileLaunchEvent(
                timestamp=timestamp, source=ModuleId.COMBAT,
                launcher_id=launcher_id, missile_id=missile_id,
                target_id="", missile_type=missile_type.name,
            ))

        return state

    def update_missiles_in_flight(
        self,
        dt: float,
        gps_accuracy_m: float = 5.0,
    ) -> list[MissileImpactResult]:
        """Advance all active missiles by *dt* seconds.

        Returns list of impact results for missiles that reach their targets.
        """
        impacts: list[MissileImpactResult] = []
        still_active: list[MissileFlightState] = []

        for missile in self._active_missiles:
            if not missile.active:
                continue

            missile.time_elapsed_s += dt
            profile = missile.flight_profile

            # Check if missile has reached target
            if missile.time_elapsed_s >= profile.flight_time_s:
                # Terminal phase — resolve impact
                # Apply CEP dispersion (GPS-guided weapons scale with accuracy)
                cep_m = 10.0 * max(1.0, gps_accuracy_m / 5.0)
                sigma_m = cep_m / 1.1774
                offset_e = self._rng.normal(0.0, sigma_m)
                offset_n = self._rng.normal(0.0, sigma_m)

                impact_pos = Position(
                    missile.target_pos.easting + offset_e,
                    missile.target_pos.northing + offset_n,
                    missile.target_pos.altitude,
                )

                # Distance from target center
                dist = math.sqrt(offset_e ** 2 + offset_n ** 2)
                hit = dist < 20.0  # Within 20m is a hit

                impacts.append(MissileImpactResult(
                    missile_id=missile.missile_id,
                    impact_pos=impact_pos,
                    hit=hit,
                    damage_fraction=0.8 if hit else 0.0,
                ))
                missile.active = False
            else:
                # Interpolate position
                frac = missile.time_elapsed_s / max(profile.flight_time_s, 1.0)
                current_e = profile.launch_pos.easting + frac * (
                    profile.target_pos.easting - profile.launch_pos.easting
                )
                current_n = profile.launch_pos.northing + frac * (
                    profile.target_pos.northing - profile.launch_pos.northing
                )
                missile.current_pos = Position(current_e, current_n, profile.cruise_altitude_m)
                still_active.append(missile)

        self._active_missiles = still_active
        return impacts

    def compute_kill_chain_latency(
        self,
        missile_type: MissileType,
        targeting_quality: float = 0.5,
    ) -> float:
        """Estimate kill chain latency from detection to launch.

        Parameters
        ----------
        missile_type:
            Type of missile (TBM has longer chain than cruise).
        targeting_quality:
            0.0–1.0 quality of targeting data.
        """
        base = self._config.kill_chain_base_latency_s

        type_factors = {
            MissileType.TBM_SHORT: 2.0,
            MissileType.TBM_MEDIUM: 3.0,
            MissileType.TBM_INTERMEDIATE: 4.0,
            MissileType.CRUISE_SUBSONIC: 1.5,
            MissileType.CRUISE_SUPERSONIC: 1.2,
            MissileType.COASTAL_DEFENSE_SSM: 1.0,
        }
        factor = type_factors.get(missile_type, 1.5)

        # Better targeting reduces latency
        quality_factor = 2.0 - targeting_quality
        return base * factor * quality_factor

    @property
    def active_missiles(self) -> list[MissileFlightState]:
        return list(self._active_missiles)

    def get_state(self) -> dict[str, Any]:
        return {
            "rng_state": self._rng.bit_generator.state,
            "active_missiles": [m.get_state() for m in self._active_missiles],
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self._rng.bit_generator.state = state["rng_state"]
        self._active_missiles = []
        for ms in state["active_missiles"]:
            m = MissileFlightState(
                missile_id="", ammo_id="", launcher_id="",
                target_pos=Position(0, 0, 0), current_pos=Position(0, 0, 0),
                flight_profile=FlightProfile(
                    missile_type=MissileType.CRUISE_SUBSONIC,
                    launch_pos=Position(0, 0, 0),
                    target_pos=Position(0, 0, 0),
                ),
            )
            m.set_state(ms)
            self._active_missiles.append(m)
