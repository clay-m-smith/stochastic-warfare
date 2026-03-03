"""Engagement orchestrator — sequences the kill chain for direct fire.

Coordinates target selection, fratricide check, ammo consumption,
hit probability, and damage resolution.  Delegates physics to
specialized modules; each step is independently testable.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.combat.ammunition import AmmoDefinition, WeaponDefinition, WeaponInstance
from stochastic_warfare.combat.damage import DamageEngine, DamageResult
from stochastic_warfare.combat.events import AmmoExpendedEvent, EngagementEvent
from stochastic_warfare.combat.fratricide import FratricideEngine
from stochastic_warfare.combat.hit_probability import HitProbabilityEngine, HitResult
from stochastic_warfare.combat.suppression import SuppressionEngine
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position

logger = get_logger(__name__)


class EngagementType(enum.IntEnum):
    """Classification of engagement method."""

    DIRECT_FIRE = 0
    INDIRECT_FIRE = 1
    MISSILE = 2
    AIR_TO_AIR = 3
    AIR_TO_GROUND = 4
    SAM = 5
    TORPEDO = 6
    NAVAL_GUN = 7
    MINE = 8


class EngagementConfig(BaseModel):
    """Tunable parameters for engagement orchestration."""

    max_simultaneous_engagements: int = 3
    fratricide_abort_threshold: float = 0.15
    min_engagement_range_m: float = 10.0


@dataclass
class EngagementResult:
    """Outcome of a single engagement."""

    engaged: bool
    engagement_type: EngagementType = EngagementType.DIRECT_FIRE
    attacker_id: str = ""
    target_id: str = ""
    weapon_id: str = ""
    ammo_id: str = ""
    hit_result: HitResult | None = None
    damage_result: DamageResult | None = None
    aborted_reason: str = ""
    range_m: float = 0.0


class EngagementEngine:
    """Orchestrates the direct-fire kill chain.

    Parameters
    ----------
    hit_engine:
        Hit probability computation.
    damage_engine:
        Damage resolution.
    suppression_engine:
        Suppression effects.
    fratricide_engine:
        Fratricide risk assessment.
    event_bus:
        For publishing engagement events.
    rng:
        PRNG generator.
    config:
        Tunable parameters.
    """

    def __init__(
        self,
        hit_engine: HitProbabilityEngine,
        damage_engine: DamageEngine,
        suppression_engine: SuppressionEngine,
        fratricide_engine: FratricideEngine,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: EngagementConfig | None = None,
    ) -> None:
        self._hit = hit_engine
        self._damage = damage_engine
        self._suppression = suppression_engine
        self._fratricide = fratricide_engine
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or EngagementConfig()

    def can_engage(
        self,
        shooter_pos: Position,
        target_pos: Position,
        weapon: WeaponDefinition,
    ) -> bool:
        """Check if an engagement is geometrically possible.

        Parameters
        ----------
        shooter_pos:
            Shooter position.
        target_pos:
            Target position.
        weapon:
            Weapon system to use.
        """
        dx = target_pos.easting - shooter_pos.easting
        dy = target_pos.northing - shooter_pos.northing
        dz = target_pos.altitude - shooter_pos.altitude
        range_m = math.sqrt(dx * dx + dy * dy + dz * dz)

        if range_m < max(weapon.min_range_m, self._config.min_engagement_range_m):
            return False
        if range_m > weapon.max_range_m > 0:
            return False
        return True

    def select_target(
        self,
        contacts: list[dict[str, Any]],
        weapon: WeaponDefinition,
        shooter_pos: Position,
    ) -> str | None:
        """Select the best target from available contacts.

        Priority: immediate threat > high-value > closest in range.

        Parameters
        ----------
        contacts:
            List of contact dicts with keys: contact_id, position,
            threat_level, value, identification_level.
        weapon:
            Weapon system to filter by range.
        shooter_pos:
            Shooter position.
        """
        valid: list[tuple[float, str]] = []

        for contact in contacts:
            pos = contact.get("position")
            if pos is None:
                continue
            dx = pos[0] - shooter_pos.easting
            dy = pos[1] - shooter_pos.northing
            range_m = math.sqrt(dx * dx + dy * dy)

            if weapon.max_range_m > 0 and range_m > weapon.max_range_m:
                continue
            if range_m < weapon.min_range_m:
                continue

            # Priority score: threat (3x) + value (2x) - range_penalty
            threat = contact.get("threat_level", 0.5)
            value = contact.get("value", 0.5)
            score = 3.0 * threat + 2.0 * value - range_m / weapon.max_range_m
            valid.append((score, contact["contact_id"]))

        if not valid:
            return None

        valid.sort(key=lambda t: t[0], reverse=True)
        return valid[0][1]

    def execute_engagement(
        self,
        attacker_id: str,
        target_id: str,
        shooter_pos: Position,
        target_pos: Position,
        weapon: WeaponInstance,
        ammo_id: str,
        ammo_def: AmmoDefinition,
        crew_skill: float = 0.5,
        target_size_m2: float = 6.0,
        target_armor_mm: float = 0.0,
        target_speed_mps: float = 0.0,
        shooter_speed_mps: float = 0.0,
        visibility: float = 1.0,
        target_posture: str = "MOVING",
        position_uncertainty_m: float = 0.0,
        identification_level: str = "IDENTIFIED",
        identification_confidence: float = 0.95,
        target_is_friendly: bool = False,
        crew_count: int = 4,
        timestamp: Any = None,
        current_time_s: float = 0.0,
    ) -> EngagementResult:
        """Execute a complete direct-fire engagement.

        Kill chain: rate-of-fire check → fratricide check → ammo consumption →
        hit resolution → damage.
        """
        dx = target_pos.easting - shooter_pos.easting
        dy = target_pos.northing - shooter_pos.northing
        dz = target_pos.altitude - shooter_pos.altitude
        range_m = math.sqrt(dx * dx + dy * dy + dz * dz)

        result = EngagementResult(
            engaged=False,
            attacker_id=attacker_id,
            target_id=target_id,
            weapon_id=weapon.weapon_id,
            ammo_id=ammo_id,
            range_m=range_m,
        )

        # 1. Range check
        if not self.can_engage(shooter_pos, target_pos, weapon.definition):
            result.aborted_reason = "out_of_range"
            return result

        # 1b. Fire rate limiting
        if not weapon.can_fire_timed(current_time_s):
            result.aborted_reason = "cooldown"
            return result

        # 2. Fratricide check
        frat_risk = self._fratricide.check_fratricide_risk(
            identification_level=identification_level,
            confidence=identification_confidence,
            target_is_friendly=target_is_friendly,
            visibility=visibility,
        )
        if frat_risk.risk > self._config.fratricide_abort_threshold:
            # High fratricide risk — check if unit fires anyway
            if frat_risk.is_friendly:
                self._fratricide.resolve_fratricide(
                    frat_risk, attacker_id, target_id, weapon.weapon_id, timestamp,
                )
                result.aborted_reason = "fratricide_risk"
                return result

        # 3. Ammo consumption
        if not weapon.fire(ammo_id):
            result.aborted_reason = "no_ammo"
            return result

        # Record fire time for rate limiting
        weapon.record_fire(current_time_s)

        if timestamp is not None:
            self._event_bus.publish(AmmoExpendedEvent(
                timestamp=timestamp, source=ModuleId.COMBAT,
                unit_id=attacker_id, ammo_type=ammo_id, quantity=1,
            ))

        result.engaged = True

        # 4. Hit probability
        hit_result = self._hit.compute_phit(
            weapon=weapon.definition,
            ammo=ammo_def,
            range_m=range_m,
            target_size_m2=target_size_m2,
            crew_skill=crew_skill,
            target_speed_mps=target_speed_mps,
            shooter_speed_mps=shooter_speed_mps,
            visibility=visibility,
            target_posture=target_posture,
            position_uncertainty_m=position_uncertainty_m,
            weapon_condition=weapon.condition,
        )
        hit_result.hit = self._hit.resolve_hit(hit_result.p_hit)
        result.hit_result = hit_result

        # Publish engagement event
        event_result = "hit" if hit_result.hit else "miss"
        if timestamp is not None:
            self._event_bus.publish(EngagementEvent(
                timestamp=timestamp, source=ModuleId.COMBAT,
                attacker_id=attacker_id, target_id=target_id,
                weapon_id=weapon.weapon_id, ammo_type=ammo_id,
                result=event_result,
            ))

        # 5. Damage resolution (if hit)
        if hit_result.hit:
            impact_angle = math.degrees(math.atan2(dz, max(range_m, 1.0)))
            damage_result = self._damage.resolve_damage(
                target_id=target_id,
                ammo=ammo_def,
                armor_mm=target_armor_mm,
                impact_angle_deg=abs(impact_angle),
                range_m=range_m,
                crew_count=crew_count,
                posture=target_posture,
                timestamp=timestamp,
            )
            result.damage_result = damage_result

        return result

    def get_state(self) -> dict[str, Any]:
        return {"rng_state": self._rng.bit_generator.state}

    def set_state(self, state: dict[str, Any]) -> None:
        self._rng.bit_generator.state = state["rng_state"]
