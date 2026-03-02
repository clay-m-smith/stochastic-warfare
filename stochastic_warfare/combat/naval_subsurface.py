"""Submarine warfare — torpedo attack, evasion, counter-torpedo.

Models torpedo engagement with wire-guided and autonomous seekers,
submarine evasion maneuvers (decoy, depth change, knuckle), and
counter-torpedo defense.  Torpedo kill probability depends on range,
guidance mode, and environmental conditions (thermocline, ambient noise).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.combat.damage import DamageEngine
from stochastic_warfare.combat.events import TorpedoEvent
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId

logger = get_logger(__name__)


class NavalSubsurfaceConfig(BaseModel):
    """Tunable parameters for submarine combat."""

    max_torpedo_range_m: float = 50_000.0
    wire_guidance_bonus: float = 0.15  # pk bonus for wire-guided
    shallow_launch_depth_m: float = 50.0  # max depth for missile launch
    decoy_effectiveness: float = 0.4
    depth_change_effectiveness: float = 0.3
    knuckle_effectiveness: float = 0.2
    counter_torpedo_base_pk: float = 0.2
    range_decay_factor: float = 0.00002  # pk degrades with range
    malfunction_probability: float = 0.05


@dataclass
class TorpedoResult:
    """Outcome of a torpedo engagement."""

    torpedo_id: str
    hit: bool
    evaded: bool = False
    decoyed: bool = False
    malfunction: bool = False
    damage_fraction: float = 0.0


@dataclass
class EvasionResult:
    """Outcome of a submarine evasion maneuver."""

    evasion_type: str  # "decoy", "depth_change", "knuckle"
    success: bool
    effectiveness: float  # 0.0–1.0 reduction in incoming pk


class NavalSubsurfaceEngine:
    """Manages submarine torpedo attacks and evasion.

    Parameters
    ----------
    damage_engine:
        For resolving torpedo damage.
    event_bus:
        For publishing torpedo events.
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
        config: NavalSubsurfaceConfig | None = None,
    ) -> None:
        self._damage = damage_engine
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or NavalSubsurfaceConfig()
        self._torpedo_count: int = 0

    def torpedo_engagement(
        self,
        sub_id: str,
        target_id: str,
        torpedo_pk: float,
        range_m: float,
        wire_guided: bool = False,
        conditions: dict[str, Any] | None = None,
        timestamp: Any = None,
    ) -> TorpedoResult:
        """Resolve a torpedo engagement.

        Parameters
        ----------
        sub_id:
            Entity ID of the attacking submarine.
        target_id:
            Entity ID of the target.
        torpedo_pk:
            Base kill probability of the torpedo.
        range_m:
            Range to target in meters.
        wire_guided:
            Whether the torpedo is wire-guided (improves pk).
        conditions:
            Environmental conditions (thermocline_depth_m, ambient_noise_db).
        timestamp:
            Simulation timestamp.
        """
        self._torpedo_count += 1
        torpedo_id = f"{sub_id}_torp_{self._torpedo_count}"

        cfg = self._config

        # Check malfunction
        if self._rng.random() < cfg.malfunction_probability:
            result = TorpedoResult(
                torpedo_id=torpedo_id, hit=False, malfunction=True,
            )
            if timestamp is not None:
                self._event_bus.publish(TorpedoEvent(
                    timestamp=timestamp, source=ModuleId.COMBAT,
                    shooter_id=sub_id, target_id=target_id,
                    torpedo_id=torpedo_id, result="malfunction",
                ))
            return result

        # Compute effective pk
        pk = torpedo_pk

        # Range degradation
        pk -= cfg.range_decay_factor * range_m

        # Wire guidance bonus
        if wire_guided:
            pk += cfg.wire_guidance_bonus

        # Environmental conditions
        if conditions:
            # Thermocline crossing degrades sonar/guidance
            thermocline = conditions.get("thermocline_depth_m", 0.0)
            if thermocline > 0:
                pk *= 0.85  # 15% penalty for thermocline crossing
            # High ambient noise degrades acoustic homing
            ambient_noise = conditions.get("ambient_noise_db", 60.0)
            if ambient_noise > 80.0:
                noise_penalty = (ambient_noise - 80.0) / 100.0
                pk -= noise_penalty

        pk = max(0.0, min(1.0, pk))

        # Resolve hit
        hit = self._rng.random() < pk

        damage = 0.0
        if hit:
            # Torpedoes are devastating — high damage per hit
            damage = 0.3 + 0.5 * self._rng.random()

        result_str = "hit" if hit else "evaded"
        result = TorpedoResult(
            torpedo_id=torpedo_id,
            hit=hit,
            evaded=not hit,
            damage_fraction=damage,
        )

        if timestamp is not None:
            self._event_bus.publish(TorpedoEvent(
                timestamp=timestamp, source=ModuleId.COMBAT,
                shooter_id=sub_id, target_id=target_id,
                torpedo_id=torpedo_id, result=result_str,
            ))

        return result

    def submarine_launched_missile(
        self,
        sub_id: str,
        launch_depth_m: float,
        missile_ammo_id: str,
    ) -> bool:
        """Attempt to launch a missile from a submarine.

        Requires the submarine to be at or above the shallow launch depth.

        Parameters
        ----------
        sub_id:
            Entity ID of the submarine.
        launch_depth_m:
            Current depth of the submarine in meters.
        missile_ammo_id:
            Ammo ID of the missile to launch.
        """
        if launch_depth_m > self._config.shallow_launch_depth_m:
            logger.debug(
                "Sub %s too deep (%.0fm) for missile launch (max %.0fm)",
                sub_id, launch_depth_m, self._config.shallow_launch_depth_m,
            )
            return False

        # Shallower depth = better launch conditions
        depth_factor = 1.0 - (launch_depth_m / self._config.shallow_launch_depth_m) * 0.2
        success = self._rng.random() < depth_factor

        logger.debug(
            "Sub %s missile launch at %.0fm depth: %s",
            sub_id, launch_depth_m, "success" if success else "failed",
        )
        return success

    def evasion_maneuver(
        self,
        sub_id: str,
        threat_bearing_deg: float,
        evasion_type: str,
    ) -> EvasionResult:
        """Execute an evasion maneuver against an incoming threat.

        Parameters
        ----------
        sub_id:
            Entity ID of the evading submarine.
        threat_bearing_deg:
            Bearing to the incoming threat (degrees from north).
        evasion_type:
            Type of evasion: "decoy", "depth_change", "knuckle".
        """
        cfg = self._config

        effectiveness_map = {
            "decoy": cfg.decoy_effectiveness,
            "depth_change": cfg.depth_change_effectiveness,
            "knuckle": cfg.knuckle_effectiveness,
        }

        base_effectiveness = effectiveness_map.get(evasion_type, 0.1)

        # Add random variation
        actual_effectiveness = base_effectiveness * (0.5 + self._rng.random())
        actual_effectiveness = min(1.0, actual_effectiveness)

        # Success means the maneuver achieves meaningful evasion
        success = actual_effectiveness > 0.2

        logger.debug(
            "Sub %s evasion (%s) against bearing %.0f°: effectiveness=%.2f",
            sub_id, evasion_type, threat_bearing_deg, actual_effectiveness,
        )

        return EvasionResult(
            evasion_type=evasion_type,
            success=success,
            effectiveness=actual_effectiveness,
        )

    def counter_torpedo(
        self,
        defender_id: str,
        incoming_pk: float,
        countermeasure_effectiveness: float,
    ) -> bool:
        """Attempt to defeat an incoming torpedo with countermeasures.

        Parameters
        ----------
        defender_id:
            Entity ID of the defending vessel.
        incoming_pk:
            Kill probability of the incoming torpedo.
        countermeasure_effectiveness:
            Effectiveness of countermeasures (0.0–1.0).
        """
        # Counter-torpedo pk combines base capability with countermeasure quality
        counter_pk = self._config.counter_torpedo_base_pk + (
            countermeasure_effectiveness * (1.0 - self._config.counter_torpedo_base_pk)
        )
        counter_pk = min(1.0, counter_pk)

        defeated = self._rng.random() < counter_pk

        logger.debug(
            "Counter-torpedo by %s: pk=%.2f, result=%s",
            defender_id, counter_pk, "defeated" if defeated else "failed",
        )
        return defeated

    def get_state(self) -> dict[str, Any]:
        return {
            "rng_state": self._rng.bit_generator.state,
            "torpedo_count": self._torpedo_count,
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self._rng.bit_generator.state = state["rng_state"]
        self._torpedo_count = state["torpedo_count"]
