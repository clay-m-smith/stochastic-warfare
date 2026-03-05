"""Indirect fire — tube artillery, rocket artillery, counterbattery.

Supports fire missions (adjust fire, FFE, immediate suppression, TOT),
rocket salvos with wider dispersion, guided precision (GMLRS, Excalibur),
and counterbattery back-trace.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.combat.ammunition import AmmoDefinition, WeaponDefinition
from stochastic_warfare.combat.ballistics import BallisticsEngine
from stochastic_warfare.combat.damage import DamageEngine
from stochastic_warfare.combat.events import ArtilleryFireEvent
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position

logger = get_logger(__name__)


class FireMissionType(enum.IntEnum):
    """Fire mission classification."""

    ADJUST_FIRE = 0
    FIRE_FOR_EFFECT = 1
    IMMEDIATE_SUPPRESSION = 2
    TIME_ON_TARGET = 3
    ILLUMINATION = 4
    SMOKE = 5
    COUNTERBATTERY = 6


class IndirectFireConfig(BaseModel):
    """Tunable parameters for indirect fire."""

    adjust_fire_rounds: int = 2
    ffe_cep_improvement: float = 0.5
    rocket_dispersion_multiplier: float = 2.0
    counterbattery_error_m: float = 200.0
    max_simultaneous_missions: int = 3
    # TOT synchronization (Phase 27b)
    tot_max_batteries: int = 6
    tot_time_of_flight_variation_s: float = 2.0


@dataclass
class ImpactPoint:
    """Single round impact."""

    position: Position
    ammo_id: str
    damage_fraction: float = 0.0


@dataclass
class FireMissionResult:
    """Result of a tube artillery fire mission."""

    mission_type: FireMissionType
    rounds_fired: int
    impacts: list[ImpactPoint] = field(default_factory=list)
    suppression_achieved: bool = False
    target_pos: Position = Position(0.0, 0.0, 0.0)


@dataclass
class SalvoResult:
    """Result of a rocket salvo."""

    rockets_fired: int
    impacts: list[ImpactPoint] = field(default_factory=list)
    target_pos: Position = Position(0.0, 0.0, 0.0)


@dataclass
class TOTFirePlan:
    """Time-on-target fire plan for synchronized battery fire."""

    target_pos: Position
    impact_time_s: float
    batteries: list[str] = field(default_factory=list)
    fire_times: dict[str, float] = field(default_factory=dict)
    time_of_flight: dict[str, float] = field(default_factory=dict)


class IndirectFireEngine:
    """Manages artillery and rocket fire missions.

    Parameters
    ----------
    ballistics:
        Ballistics engine for trajectory/dispersion.
    damage_engine:
        For resolving impact effects.
    event_bus:
        For publishing fire events.
    rng:
        PRNG generator.
    config:
        Tunable parameters.
    """

    def __init__(
        self,
        ballistics: BallisticsEngine,
        damage_engine: DamageEngine,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: IndirectFireConfig | None = None,
    ) -> None:
        self._ballistics = ballistics
        self._damage = damage_engine
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or IndirectFireConfig()

    def fire_mission(
        self,
        battery_id: str,
        fire_pos: Position,
        target_pos: Position,
        weapon: WeaponDefinition,
        ammo: AmmoDefinition,
        mission_type: FireMissionType,
        round_count: int,
        conditions: dict[str, Any] | None = None,
        timestamp: Any = None,
        wind_speed_mps: float = 0.0,
        wind_direction_deg: float = 0.0,
    ) -> FireMissionResult:
        """Execute a tube artillery fire mission.

        Parameters
        ----------
        battery_id:
            Entity ID of the firing battery.
        fire_pos:
            Battery position.
        target_pos:
            Target grid reference.
        weapon:
            Howitzer/mortar weapon definition.
        ammo:
            Ammo type to fire.
        mission_type:
            Type of fire mission.
        round_count:
            Number of rounds to fire.
        conditions:
            Environmental conditions.
        timestamp:
            Simulation timestamp.
        wind_speed_mps:
            Wind speed in m/s (crosswind increases dispersion).
        wind_direction_deg:
            Wind direction in degrees from north (meteorological convention).
        """
        result = FireMissionResult(
            mission_type=mission_type,
            rounds_fired=round_count,
            target_pos=target_pos,
        )

        # CEP from weapon
        cep_m = weapon.cep_m
        if ammo.guidance != "NONE" and ammo.pk_at_reference > 0:
            # Guided round: use much smaller CEP
            cep_m = max(5.0, cep_m * 0.1)

        # FFE improves accuracy (adjust fire brackets target)
        if mission_type == FireMissionType.FIRE_FOR_EFFECT:
            cep_m *= self._config.ffe_cep_improvement

        # Convert CEP to sigma: sigma = CEP / 1.1774
        sigma_m = cep_m / 1.1774 if cep_m > 0 else weapon.base_accuracy_mrad * 10.0

        # Wind increases CEP: crosswind component adds to dispersion
        if wind_speed_mps > 0:
            dx = target_pos.easting - fire_pos.easting
            dy = target_pos.northing - fire_pos.northing
            fire_range = math.sqrt(dx * dx + dy * dy)
            if fire_range > 0:
                fire_dir_deg = math.degrees(math.atan2(dx, dy)) % 360.0
                crosswind_angle_rad = math.radians(wind_direction_deg - fire_dir_deg)
                crosswind_mps = abs(wind_speed_mps * math.sin(crosswind_angle_rad))
                # Each m/s of crosswind adds ~0.5% CEP increase per km range
                wind_cep_factor = 1.0 + 0.005 * crosswind_mps * (fire_range / 1000.0)
                sigma_m *= wind_cep_factor

        for _ in range(round_count):
            offset_e = self._rng.normal(0.0, sigma_m)
            offset_n = self._rng.normal(0.0, sigma_m)
            impact_pos = Position(
                target_pos.easting + offset_e,
                target_pos.northing + offset_n,
                target_pos.altitude,
            )
            result.impacts.append(ImpactPoint(
                position=impact_pos,
                ammo_id=ammo.ammo_id,
            ))

        # Suppression: any HE fire mission with >3 rounds suppresses
        if round_count >= 3 and ammo.blast_radius_m > 0:
            result.suppression_achieved = True

        # Publish event
        if timestamp is not None:
            self._event_bus.publish(ArtilleryFireEvent(
                timestamp=timestamp, source=ModuleId.COMBAT,
                battery_id=battery_id,
                target_pos=tuple(target_pos),
                ammo_type=ammo.ammo_id,
                round_count=round_count,
            ))

        return result

    def rocket_salvo(
        self,
        launcher_id: str,
        fire_pos: Position,
        target_pos: Position,
        weapon: WeaponDefinition,
        ammo: AmmoDefinition,
        rocket_count: int,
        conditions: dict[str, Any] | None = None,
        timestamp: Any = None,
    ) -> SalvoResult:
        """Fire a rocket salvo (MLRS/HIMARS).

        Rockets have wider dispersion than tube artillery but deliver
        more firepower in a short time.
        """
        result = SalvoResult(rockets_fired=rocket_count, target_pos=target_pos)

        # Rocket dispersion: wider than tube
        if ammo.guidance != "NONE" and ammo.pk_at_reference > 0:
            # Guided rocket (GMLRS): tight CEP
            sigma_m = 5.0 / 1.1774
        else:
            # Unguided: use weapon CEP with rocket multiplier
            cep_m = weapon.cep_m * self._config.rocket_dispersion_multiplier
            sigma_m = cep_m / 1.1774 if cep_m > 0 else 100.0

        for _ in range(rocket_count):
            offset_e = self._rng.normal(0.0, sigma_m)
            offset_n = self._rng.normal(0.0, sigma_m)
            impact_pos = Position(
                target_pos.easting + offset_e,
                target_pos.northing + offset_n,
                target_pos.altitude,
            )
            result.impacts.append(ImpactPoint(
                position=impact_pos,
                ammo_id=ammo.ammo_id,
            ))

        if timestamp is not None:
            self._event_bus.publish(ArtilleryFireEvent(
                timestamp=timestamp, source=ModuleId.COMBAT,
                battery_id=launcher_id,
                target_pos=tuple(target_pos),
                ammo_type=ammo.ammo_id,
                round_count=rocket_count,
            ))

        return result

    def compute_counterbattery_solution(
        self,
        incoming_direction_rad: float,
        estimated_range_m: float,
    ) -> Position:
        """Back-trace incoming fire to estimate enemy firing position.

        Parameters
        ----------
        incoming_direction_rad:
            Direction the incoming fire came from (radians from north).
        estimated_range_m:
            Estimated range of the enemy battery.

        Returns
        -------
        Position:
            Estimated enemy battery position (with error).
        """
        error_m = self._config.counterbattery_error_m
        error_e = self._rng.normal(0.0, error_m)
        error_n = self._rng.normal(0.0, error_m)

        est_e = estimated_range_m * math.sin(incoming_direction_rad) + error_e
        est_n = estimated_range_m * math.cos(incoming_direction_rad) + error_n

        return Position(est_e, est_n, 0.0)

    def compute_tot_plan(
        self,
        target_pos: Position,
        battery_positions: dict[str, Position],
        weapon: WeaponDefinition,
        ammo: AmmoDefinition,
        desired_impact_time_s: float,
    ) -> TOTFirePlan:
        """Compute a time-on-target fire plan so all batteries impact simultaneously.

        Parameters
        ----------
        target_pos:
            Target grid reference.
        battery_positions:
            Mapping of battery_id -> Position.
        weapon:
            Weapon definition (for muzzle velocity).
        ammo:
            Ammo definition.
        desired_impact_time_s:
            Desired simultaneous impact time.
        """
        cfg = self._config
        batteries = list(battery_positions.keys())[:cfg.tot_max_batteries]
        fire_times: dict[str, float] = {}
        tof: dict[str, float] = {}

        muzzle_vel = weapon.muzzle_velocity_mps
        if muzzle_vel <= 0:
            muzzle_vel = 300.0  # fallback

        for bid in batteries:
            bpos = battery_positions[bid]
            dx = target_pos.easting - bpos.easting
            dy = target_pos.northing - bpos.northing
            range_m = math.sqrt(dx * dx + dy * dy)
            # Simplified ToF: range / muzzle_velocity (lofted trajectory ~2x)
            flight_time = (range_m / muzzle_vel) * 2.0
            # Add jitter
            jitter = self._rng.normal(0.0, cfg.tot_time_of_flight_variation_s)
            flight_time += jitter
            flight_time = max(1.0, flight_time)
            tof[bid] = flight_time
            fire_times[bid] = desired_impact_time_s - flight_time

        return TOTFirePlan(
            target_pos=target_pos,
            impact_time_s=desired_impact_time_s,
            batteries=batteries,
            fire_times=fire_times,
            time_of_flight=tof,
        )

    def execute_tot_mission(
        self,
        plan: TOTFirePlan,
        weapons: dict[str, WeaponDefinition],
        ammo: AmmoDefinition,
        rounds_per_battery: int,
        current_time_s: float,
        timestamp: Any = None,
    ) -> list[FireMissionResult]:
        """Execute batteries whose fire_time <= current_time_s.

        Parameters
        ----------
        plan:
            TOT fire plan from compute_tot_plan().
        weapons:
            Mapping of battery_id -> WeaponDefinition.
        ammo:
            Ammo definition for all batteries.
        rounds_per_battery:
            Number of rounds each battery fires.
        current_time_s:
            Current simulation time.
        timestamp:
            Simulation timestamp for events.
        """
        results: list[FireMissionResult] = []
        for bid in plan.batteries:
            if plan.fire_times[bid] <= current_time_s:
                weapon = weapons.get(bid)
                if weapon is None:
                    continue
                # Fire position not stored in plan; use (0,0,0) as placeholder
                # In practice the caller provides weapon defs keyed by battery
                result = self.fire_mission(
                    battery_id=bid,
                    fire_pos=Position(0.0, 0.0, 0.0),
                    target_pos=plan.target_pos,
                    weapon=weapon,
                    ammo=ammo,
                    mission_type=FireMissionType.TIME_ON_TARGET,
                    round_count=rounds_per_battery,
                    timestamp=timestamp,
                )
                results.append(result)
        return results

    def get_state(self) -> dict[str, Any]:
        return {"rng_state": self._rng.bit_generator.state}

    def set_state(self, state: dict[str, Any]) -> None:
        self._rng.bit_generator.state = state["rng_state"]
