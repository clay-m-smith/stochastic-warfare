"""Damage resolution — penetration, blast, fragmentation, behind-armor effects.

Implements DeMarre-variant penetration for kinetic rounds, shaped-charge
penetration for HEAT, Gaussian blast attenuation, and 1/r^2 fragmentation.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.combat.ammunition import AmmoDefinition
from stochastic_warfare.combat.events import DamageEvent, HitEvent
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId

logger = get_logger(__name__)

# Constant posture protection factors (blast and fragmentation)
_POSTURE_BLAST_PROTECT: dict[str, float] = {
    "MOVING": 1.0, "HALTED": 0.9, "DEFENSIVE": 0.7,
    "DUG_IN": 0.3, "FORTIFIED": 0.1,
}
_POSTURE_FRAG_PROTECT: dict[str, float] = {
    "MOVING": 1.0, "HALTED": 0.85, "DEFENSIVE": 0.5,
    "DUG_IN": 0.15, "FORTIFIED": 0.05,
}


class DamageType(enum.IntEnum):
    """Terminal effect classification."""

    KINETIC = 0
    BLAST = 1
    FRAGMENTATION = 2
    INCENDIARY = 3
    COMBINED = 4


class DamageConfig(BaseModel):
    """Tunable parameters for damage resolution."""

    demare_exponent: float = 1.5
    spall_probability: float = 0.3
    fire_probability: float = 0.1
    ammo_cookoff_probability: float = 0.05
    min_penetration_fraction: float = 0.5
    blast_sigma_scale: float = 1.0


@dataclass
class PenetrationResult:
    """Outcome of a penetration calculation."""

    penetrated: bool
    penetration_mm: float
    armor_effective_mm: float
    margin_mm: float  # positive = overmatch, negative = stopped


@dataclass
class CasualtyResult:
    """Individual casualty from behind-armor effects."""

    member_index: int
    severity: str  # "minor", "serious", "critical", "kia"
    cause: str  # "spall", "fire", "blast_overpressure"


@dataclass
class DamageResult:
    """Complete damage outcome."""

    damage_type: DamageType
    damage_fraction: float  # 0.0–1.0 condition reduction
    penetrated: bool = False
    casualties: list[CasualtyResult] = field(default_factory=list)
    systems_damaged: list[str] = field(default_factory=list)
    fire_started: bool = False
    ammo_cookoff: bool = False


class DamageEngine:
    """Resolves terminal effects of projectile impacts.

    Parameters
    ----------
    event_bus:
        For publishing damage events.
    rng:
        PRNG generator for stochastic effects.
    config:
        Tunable damage parameters.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: DamageConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or DamageConfig()

    def compute_penetration(
        self,
        ammo: AmmoDefinition,
        armor_mm: float,
        impact_angle_deg: float = 0.0,
        range_m: float = 0.0,
    ) -> PenetrationResult:
        """Compute whether a round penetrates armor.

        Parameters
        ----------
        ammo:
            Ammunition definition with penetration data.
        armor_mm:
            Armor thickness in mm RHA.
        impact_angle_deg:
            Impact angle from normal (0 = perpendicular).
        range_m:
            Engagement range for velocity-dependent penetration.
        """
        if ammo.penetration_mm_rha <= 0:
            return PenetrationResult(
                penetrated=False, penetration_mm=0.0,
                armor_effective_mm=armor_mm, margin_mm=-armor_mm,
            )

        # Effective armor thickness (obliquity)
        angle_rad = math.radians(min(abs(impact_angle_deg), 80.0))
        cos_angle = math.cos(angle_rad)
        if cos_angle < 0.1:
            cos_angle = 0.1
        armor_eff = armor_mm / cos_angle

        # Penetration calculation
        pen_ref = ammo.penetration_mm_rha
        ammo_type_str = ammo.ammo_type.upper()

        if ammo_type_str == "HEAT":
            # HEAT: penetration independent of range (shaped charge)
            penetration = pen_ref
        elif ammo.penetration_reference_range_m > 0 and range_m > 0:
            # DeMarre variant: pen = pen_ref × (v/v_ref)^1.5
            # Approximate velocity decay: v/v_ref ≈ 1 - drag_factor * range
            decay = 1.0 - ammo.drag_coefficient * range_m / 100000.0
            decay = max(0.3, decay)
            penetration = pen_ref * decay ** self._config.demare_exponent
        else:
            penetration = pen_ref

        margin = penetration - armor_eff
        penetrated = margin > 0

        return PenetrationResult(
            penetrated=penetrated,
            penetration_mm=penetration,
            armor_effective_mm=armor_eff,
            margin_mm=margin,
        )

    def apply_behind_armor_effects(
        self,
        penetration: PenetrationResult,
        crew_count: int,
    ) -> list[CasualtyResult]:
        """Resolve behind-armor effects for a penetrating hit.

        Parameters
        ----------
        penetration:
            Result of penetration calculation.
        crew_count:
            Number of crew in the vehicle.
        """
        if not penetration.penetrated:
            return []

        casualties: list[CasualtyResult] = []
        cfg = self._config

        # Overmatch factor: more penetration → worse effects
        overmatch = penetration.margin_mm / max(
            1.0, penetration.armor_effective_mm
        )
        overmatch = min(overmatch, 3.0)

        # Spalling
        for i in range(crew_count):
            if self._rng.random() < cfg.spall_probability * (0.5 + 0.5 * overmatch):
                severity = self._resolve_severity(overmatch)
                casualties.append(CasualtyResult(
                    member_index=i, severity=severity, cause="spall",
                ))

        return casualties

    def _resolve_severity(self, overmatch: float) -> str:
        """Determine casualty severity based on overmatch factor."""
        roll = float(self._rng.random())
        # Higher overmatch → more severe
        kia_threshold = 0.1 + 0.2 * overmatch
        critical_threshold = kia_threshold + 0.2
        serious_threshold = critical_threshold + 0.3

        if roll < kia_threshold:
            return "kia"
        elif roll < critical_threshold:
            return "critical"
        elif roll < serious_threshold:
            return "serious"
        else:
            return "minor"

    def apply_blast_damage(
        self,
        ammo: AmmoDefinition,
        distance_m: float,
        posture: str = "MOVING",
    ) -> DamageResult:
        """Compute blast and fragmentation damage.

        Parameters
        ----------
        ammo:
            Ammunition with blast_radius_m and fragmentation_radius_m.
        distance_m:
            Distance from detonation point to target.
        posture:
            Target posture for protection calculation.
        """
        damage_fraction = 0.0
        casualties: list[CasualtyResult] = []

        # Blast: P_kill = exp(-distance^2 / (2 * blast_radius^2))
        if ammo.blast_radius_m > 0:
            sigma = ammo.blast_radius_m * self._config.blast_sigma_scale
            p_kill_blast = math.exp(
                -distance_m * distance_m / (2.0 * sigma * sigma)
            )
            # Posture protection
            protection = _POSTURE_BLAST_PROTECT.get(posture, 1.0)
            damage_fraction = max(damage_fraction, p_kill_blast * protection)

        # Fragmentation: 1/r^2 falloff
        if ammo.fragmentation_radius_m > 0 and distance_m < ammo.fragmentation_radius_m:
            frag_factor = 1.0 - (distance_m / ammo.fragmentation_radius_m) ** 2
            frag_protection = _POSTURE_FRAG_PROTECT.get(posture, 1.0)
            frag_damage = frag_factor * frag_protection
            damage_fraction = max(damage_fraction, frag_damage)

        return DamageResult(
            damage_type=DamageType.COMBINED if ammo.fragmentation_radius_m > 0 else DamageType.BLAST,
            damage_fraction=min(1.0, damage_fraction),
        )

    def resolve_damage(
        self,
        target_id: str,
        ammo: AmmoDefinition,
        armor_mm: float = 0.0,
        impact_angle_deg: float = 0.0,
        range_m: float = 0.0,
        distance_from_impact_m: float = 0.0,
        crew_count: int = 4,
        posture: str = "MOVING",
        timestamp: Any = None,
    ) -> DamageResult:
        """Full damage resolution: penetration + blast + behind-armor effects.

        Parameters
        ----------
        target_id:
            Entity ID of the target.
        ammo:
            Ammunition that hit.
        armor_mm:
            Target armor in mm RHA (0 for unarmored).
        impact_angle_deg:
            Impact angle from normal.
        range_m:
            Engagement range.
        distance_from_impact_m:
            Distance from detonation point (for blast/frag; 0 = direct hit).
        crew_count:
            Number of crew members.
        posture:
            Target posture.
        timestamp:
            Simulation timestamp for events.
        """
        result = DamageResult(damage_type=DamageType.COMBINED, damage_fraction=0.0)

        # Kinetic / penetration
        if armor_mm > 0 and ammo.penetration_mm_rha > 0:
            pen = self.compute_penetration(ammo, armor_mm, impact_angle_deg, range_m)
            result.penetrated = pen.penetrated

            if pen.penetrated:
                bae = self.apply_behind_armor_effects(pen, crew_count)
                result.casualties.extend(bae)
                result.damage_fraction = min(1.0, 0.3 + 0.3 * (pen.margin_mm / max(1.0, armor_mm)))

                # Fire / cookoff
                if self._rng.random() < self._config.fire_probability:
                    result.fire_started = True
                if self._rng.random() < self._config.ammo_cookoff_probability:
                    result.ammo_cookoff = True
                    result.damage_fraction = 1.0

            # Publish events
            if timestamp is not None:
                self._event_bus.publish(HitEvent(
                    timestamp=timestamp, source=ModuleId.COMBAT,
                    target_id=target_id, weapon_id="",
                    damage_type="KINETIC", penetrated=pen.penetrated,
                ))
        else:
            # Blast/frag against unarmored or soft target
            blast_result = self.apply_blast_damage(ammo, distance_from_impact_m, posture)
            result.damage_fraction = blast_result.damage_fraction
            result.damage_type = blast_result.damage_type

        if timestamp is not None and result.damage_fraction > 0:
            self._event_bus.publish(DamageEvent(
                timestamp=timestamp, source=ModuleId.COMBAT,
                target_id=target_id, damage_amount=result.damage_fraction,
                damage_type=result.damage_type.name, location="hull",
            ))

        return result

    def get_state(self) -> dict[str, Any]:
        return {"rng_state": self._rng.bit_generator.state}

    def set_state(self, state: dict[str, Any]) -> None:
        self._rng.bit_generator.state = state["rng_state"]
