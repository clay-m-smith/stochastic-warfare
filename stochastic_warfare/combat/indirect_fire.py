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

    def get_state(self) -> dict[str, Any]:
        return {"rng_state": self._rng.bit_generator.state}

    def set_state(self, state: dict[str, Any]) -> None:
        self._rng.bit_generator.state = state["rng_state"]
