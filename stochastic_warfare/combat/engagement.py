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
    COASTAL_DEFENSE = 9
    AIR_LAUNCHED_ASHM = 10
    ATGM_VS_ROTARY = 11
    DEW_LASER = 12
    DEW_HPM = 13


class EngagementConfig(BaseModel):
    """Tunable parameters for engagement orchestration."""

    max_simultaneous_engagements: int = 3
    fratricide_abort_threshold: float = 0.15
    min_engagement_range_m: float = 10.0
    # ATGM vs rotary (Phase 27a)
    atgm_max_altitude_m: float = 500.0
    atgm_range_decay_factor: float = 0.0001
    # Burst fire (Phase 27b)
    enable_burst_fire: bool = False
    max_burst_size: int = 10


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


@dataclass
class BurstEngagementResult:
    """Outcome of a burst-fire engagement."""

    engaged: bool
    attacker_id: str = ""
    target_id: str = ""
    weapon_id: str = ""
    rounds_fired: int = 0
    hits: int = 0
    damage_results: list[DamageResult] = field(default_factory=list)
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

    def route_engagement(
        self,
        engagement_type: EngagementType,
        attacker_id: str,
        target_id: str,
        attacker_pos: Position,
        target_pos: Position,
        weapon: WeaponInstance,
        ammo_id: str,
        ammo_def: AmmoDefinition,
        *,
        missile_engine: Any | None = None,
        naval_surface_engine: Any | None = None,
        dew_engine: Any | None = None,
        crew_skill: float = 0.5,
        target_size_m2: float = 6.0,
        target_armor_mm: float = 0.0,
        target_speed_mps: float = 0.0,
        target_altitude_m: float = 0.0,
        timestamp: Any = None,
        current_time_s: float = 0.0,
    ) -> EngagementResult:
        """Dispatch an engagement to the appropriate handler.

        Routes DIRECT_FIRE to ``execute_engagement()``, COASTAL_DEFENSE
        and AIR_LAUNCHED_ASHM to missile launch, ATGM_VS_ROTARY to
        ``_resolve_atgm_vs_rotary()``, and returns a non-engaged result
        for unrecognised types.
        """
        if engagement_type == EngagementType.DIRECT_FIRE:
            return self.execute_engagement(
                attacker_id=attacker_id,
                target_id=target_id,
                shooter_pos=attacker_pos,
                target_pos=target_pos,
                weapon=weapon,
                ammo_id=ammo_id,
                ammo_def=ammo_def,
                crew_skill=crew_skill,
                target_size_m2=target_size_m2,
                target_armor_mm=target_armor_mm,
                target_speed_mps=target_speed_mps,
                timestamp=timestamp,
                current_time_s=current_time_s,
            )

        if engagement_type == EngagementType.COASTAL_DEFENSE:
            if missile_engine is None:
                return EngagementResult(
                    engaged=False, attacker_id=attacker_id,
                    target_id=target_id, aborted_reason="no_missile_engine",
                )
            from stochastic_warfare.combat.missiles import MissileType
            missile_engine.launch_missile(
                ammo=ammo_def,
                launch_pos=attacker_pos,
                target_pos=target_pos,
                missile_type=MissileType.COASTAL_DEFENSE_SSM,
                timestamp=timestamp,
            )
            return EngagementResult(
                engaged=True, engagement_type=engagement_type,
                attacker_id=attacker_id, target_id=target_id,
                weapon_id=weapon.weapon_id, ammo_id=ammo_id,
            )

        if engagement_type == EngagementType.AIR_LAUNCHED_ASHM:
            if missile_engine is None:
                return EngagementResult(
                    engaged=False, attacker_id=attacker_id,
                    target_id=target_id, aborted_reason="no_missile_engine",
                )
            from stochastic_warfare.combat.missiles import MissileType
            missile_engine.launch_missile(
                ammo=ammo_def,
                launch_pos=attacker_pos,
                target_pos=target_pos,
                missile_type=MissileType.CRUISE_SUBSONIC,
                timestamp=timestamp,
            )
            return EngagementResult(
                engaged=True, engagement_type=engagement_type,
                attacker_id=attacker_id, target_id=target_id,
                weapon_id=weapon.weapon_id, ammo_id=ammo_id,
            )

        if engagement_type == EngagementType.DEW_LASER:
            if dew_engine is None:
                return EngagementResult(
                    engaged=False, attacker_id=attacker_id,
                    target_id=target_id, aborted_reason="no_dew_engine",
                )
            dew_result = dew_engine.execute_laser_engagement(
                attacker_id=attacker_id,
                target_id=target_id,
                shooter_pos=attacker_pos,
                target_pos=target_pos,
                weapon=weapon,
                ammo_id=ammo_id,
                ammo_def=ammo_def,
                current_time_s=current_time_s,
                timestamp=timestamp,
            )
            return EngagementResult(
                engaged=dew_result.engaged,
                engagement_type=engagement_type,
                attacker_id=attacker_id,
                target_id=target_id,
                weapon_id=weapon.weapon_id,
                ammo_id=ammo_id,
                aborted_reason=dew_result.aborted_reason,
                range_m=dew_result.range_m,
            )

        if engagement_type == EngagementType.DEW_HPM:
            if dew_engine is None:
                return EngagementResult(
                    engaged=False, attacker_id=attacker_id,
                    target_id=target_id, aborted_reason="no_dew_engine",
                )
            dew_results = dew_engine.execute_hpm_engagement(
                attacker_id=attacker_id,
                shooter_pos=attacker_pos,
                weapon=weapon,
                ammo_id=ammo_id,
                ammo_def=ammo_def,
                targets=[(target_id, target_pos, False)],
                current_time_s=current_time_s,
                timestamp=timestamp,
            )
            first = dew_results[0] if dew_results else None
            return EngagementResult(
                engaged=first.engaged if first else False,
                engagement_type=engagement_type,
                attacker_id=attacker_id,
                target_id=target_id,
                weapon_id=weapon.weapon_id,
                ammo_id=ammo_id,
                aborted_reason=first.aborted_reason if first else "no_targets",
                range_m=first.range_m if first else 0.0,
            )

        if engagement_type == EngagementType.ATGM_VS_ROTARY:
            return self._resolve_atgm_vs_rotary(
                attacker_id=attacker_id,
                target_id=target_id,
                attacker_pos=attacker_pos,
                target_pos=target_pos,
                weapon=weapon,
                ammo_id=ammo_id,
                ammo_def=ammo_def,
                target_altitude_m=target_altitude_m,
                target_speed_mps=target_speed_mps,
                timestamp=timestamp,
            )

        # Unknown engagement type
        return EngagementResult(
            engaged=False, attacker_id=attacker_id,
            target_id=target_id, aborted_reason="unknown_engagement_type",
        )

    def _resolve_atgm_vs_rotary(
        self,
        attacker_id: str,
        target_id: str,
        attacker_pos: Position,
        target_pos: Position,
        weapon: WeaponInstance,
        ammo_id: str,
        ammo_def: AmmoDefinition,
        target_altitude_m: float = 0.0,
        target_speed_mps: float = 0.0,
        timestamp: Any = None,
    ) -> EngagementResult:
        """Resolve ATGM engagement against rotary-wing aircraft."""
        cfg = self._config
        dx = target_pos.easting - attacker_pos.easting
        dy = target_pos.northing - attacker_pos.northing
        dz = target_pos.altitude - attacker_pos.altitude
        range_m = math.sqrt(dx * dx + dy * dy + dz * dz)

        result = EngagementResult(
            engaged=False,
            engagement_type=EngagementType.ATGM_VS_ROTARY,
            attacker_id=attacker_id,
            target_id=target_id,
            weapon_id=weapon.weapon_id,
            ammo_id=ammo_id,
            range_m=range_m,
        )

        # Altitude check
        if target_altitude_m > cfg.atgm_max_altitude_m:
            result.aborted_reason = "target_too_high"
            return result

        # Range check
        if weapon.definition.max_range_m > 0 and range_m > weapon.definition.max_range_m:
            result.aborted_reason = "out_of_range"
            return result

        # Base Pk from ammo
        base_pk = ammo_def.pk_at_reference if ammo_def.pk_at_reference > 0 else 0.3

        # Range factor
        range_factor = max(0.1, 1.0 - cfg.atgm_range_decay_factor * range_m)

        # Altitude penalty (higher = harder to track)
        altitude_penalty = max(0.5, 1.0 - target_altitude_m / cfg.atgm_max_altitude_m)

        # Wire-guided bonus vs hovering target
        wire_bonus = 1.0
        if ammo_def.guidance.upper() == "WIRE" and target_speed_mps < 5.0:
            wire_bonus = 1.2

        effective_pk = base_pk * range_factor * altitude_penalty * wire_bonus
        effective_pk = max(0.01, min(0.99, effective_pk))

        result.engaged = True
        hit = float(self._rng.random()) < effective_pk

        if hit:
            result.hit_result = HitResult(p_hit=effective_pk, range_m=range_m, modifiers={}, hit=True)
        else:
            result.hit_result = HitResult(p_hit=effective_pk, range_m=range_m, modifiers={}, hit=False)

        return result

    def execute_burst_engagement(
        self,
        attacker_id: str,
        target_id: str,
        shooter_pos: Position,
        target_pos: Position,
        weapon: WeaponInstance,
        ammo_id: str,
        ammo_def: AmmoDefinition,
        burst_size: int | None = None,
        crew_skill: float = 0.5,
        target_size_m2: float = 6.0,
        target_armor_mm: float = 0.0,
        target_speed_mps: float = 0.0,
        shooter_speed_mps: float = 0.0,
        visibility: float = 1.0,
        target_posture: str = "MOVING",
        position_uncertainty_m: float = 0.0,
        current_time_s: float = 0.0,
        timestamp: Any = None,
    ) -> BurstEngagementResult:
        """Execute a burst-fire engagement (multiple rounds, single cooldown).

        Fires N rounds as independent Bernoulli trials. Resolves damage
        per hit. Consumes burst_size rounds from magazine.
        """
        dx = target_pos.easting - shooter_pos.easting
        dy = target_pos.northing - shooter_pos.northing
        dz = target_pos.altitude - shooter_pos.altitude
        range_m = math.sqrt(dx * dx + dy * dy + dz * dz)

        result = BurstEngagementResult(
            engaged=False,
            attacker_id=attacker_id,
            target_id=target_id,
            weapon_id=weapon.weapon_id,
            range_m=range_m,
        )

        # Range check
        if not self.can_engage(shooter_pos, target_pos, weapon.definition):
            result.aborted_reason = "out_of_range"
            return result

        # Fire rate limiting
        if not weapon.can_fire_timed(current_time_s):
            result.aborted_reason = "cooldown"
            return result

        # Determine burst size
        if burst_size is None:
            burst_size = weapon.definition.burst_size
        if not self._config.enable_burst_fire:
            burst_size = 1
        else:
            burst_size = min(burst_size, self._config.max_burst_size)

        # Check available ammo
        available = weapon.ammo_state.available(ammo_id)
        actual_burst = min(burst_size, available)
        if actual_burst <= 0:
            result.aborted_reason = "no_ammo"
            return result

        # Consume ammo
        for _ in range(actual_burst):
            if not weapon.fire(ammo_id):
                break

        # Record fire time (single cooldown for entire burst)
        weapon.record_fire(current_time_s)

        result.engaged = True
        result.rounds_fired = actual_burst

        # Compute Pk
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
        p_hit = hit_result.p_hit

        # Resolve each round as independent Bernoulli trial
        hits = int(self._rng.binomial(actual_burst, p_hit))
        result.hits = hits

        # Resolve damage per hit
        if hits > 0:
            impact_angle = math.degrees(math.atan2(dz, max(range_m, 1.0)))
            for _ in range(hits):
                dmg = self._damage.resolve_damage(
                    target_id=target_id,
                    ammo=ammo_def,
                    armor_mm=target_armor_mm,
                    impact_angle_deg=abs(impact_angle),
                    range_m=range_m,
                    posture=target_posture,
                    timestamp=timestamp,
                )
                result.damage_results.append(dmg)

        return result

    def get_state(self) -> dict[str, Any]:
        return {"rng_state": self._rng.bit_generator.state}

    def set_state(self, state: dict[str, Any]) -> None:
        self._rng.bit_generator.state = state["rng_state"]


# ---------------------------------------------------------------------------
# Treaty compliance helper (Phase 24b)
# ---------------------------------------------------------------------------

# Mapping from treaty name to the minimum escalation level required
# to authorize employment of munitions prohibited under that treaty.
_TREATY_ESCALATION_LEVELS: dict[str, int] = {
    "CWC": 5,                # Chemical Weapons Convention → CHEMICAL
    "BWC": 6,                # Biological Weapons Convention → BIOLOGICAL
    "CCM": 4,                # Convention on Cluster Munitions → PROHIBITED_METHODS
    "Ottawa": 4,             # Ottawa Treaty (AP mines) → PROHIBITED_METHODS
    "Protocol III CCW": 3,   # Protocol III to CCW (incendiary) → ROE_VIOLATIONS
    "Hague": 3,              # Hague Convention (expanding bullets) → ROE_VIOLATIONS
}


def check_prohibited_compliance(
    ammo_def: AmmoDefinition,
    escalation_engine: Any | None,
) -> tuple[bool, str]:
    """Check if ammo requires escalation authorization.

    Parameters
    ----------
    ammo_def:
        Ammunition definition to check.
    escalation_engine:
        Escalation engine instance with a ``current_level`` attribute,
        or ``None`` if no escalation system is active.

    Returns
    -------
    (authorized, reason):
        ``authorized`` is True if the weapon may be employed.
        ``reason`` is an empty string when authorized, or a descriptive
        string when not.
    """
    if not ammo_def.compliance_check:
        return True, ""

    if escalation_engine is None:
        return True, "no_escalation_system"

    current_level = getattr(escalation_engine, "current_level", 0)

    for treaty in ammo_def.prohibited_under_treaties:
        required_level = _TREATY_ESCALATION_LEVELS.get(treaty)
        if required_level is not None and current_level < required_level:
            return False, f"requires_escalation_level_{required_level}_for_{treaty}"

    return True, ""
