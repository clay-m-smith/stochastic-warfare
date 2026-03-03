"""Hit probability computation with modifiers for crew, target, and conditions.

Combines ballistic dispersion with tactical modifiers (crew skill, target
motion, visibility, posture, position uncertainty) to produce a final
P(hit) for both unguided and guided engagements.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.combat.ammunition import AmmoDefinition, WeaponDefinition
from stochastic_warfare.combat.ballistics import BallisticsEngine
from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


class HitProbabilityConfig(BaseModel):
    """Tunable parameters for hit probability computation."""

    base_hit_fraction: float = 0.8
    crew_skill_weight: float = 0.3
    visibility_weight: float = 0.2
    target_motion_penalty: float = 0.15
    shooter_motion_penalty: float = 0.25
    posture_dug_in_bonus: float = 0.4
    uncertainty_penalty_scale: float = 0.01
    min_phit: float = 0.01
    max_phit: float = 0.99


@dataclass
class HitResult:
    """Result of a hit probability computation."""

    p_hit: float
    range_m: float
    modifiers: dict[str, float]
    hit: bool = False


class HitProbabilityEngine:
    """Computes probability of hit for direct fire and guided engagements.

    Parameters
    ----------
    ballistics:
        Ballistics engine for dispersion calculations.
    rng:
        PRNG generator for hit resolution.
    config:
        Tunable parameters.
    """

    def __init__(
        self,
        ballistics: BallisticsEngine,
        rng: np.random.Generator,
        config: HitProbabilityConfig | None = None,
    ) -> None:
        self._ballistics = ballistics
        self._rng = rng
        self._config = config or HitProbabilityConfig()
        self._posture_mods = {
            "MOVING": 1.0,
            "HALTED": 1.0,
            "DEFENSIVE": 0.85,
            "DUG_IN": 1.0 - self._config.posture_dug_in_bonus,
            "FORTIFIED": 0.4,
        }

    def compute_phit(
        self,
        weapon: WeaponDefinition,
        ammo: AmmoDefinition,
        range_m: float,
        target_size_m2: float = 6.0,
        crew_skill: float = 0.5,
        target_speed_mps: float = 0.0,
        shooter_speed_mps: float = 0.0,
        visibility: float = 1.0,
        target_posture: str = "MOVING",
        position_uncertainty_m: float = 0.0,
        weapon_condition: float = 1.0,
    ) -> HitResult:
        """Compute probability of hit for an unguided engagement.

        Parameters
        ----------
        weapon:
            Weapon system definition.
        ammo:
            Ammunition definition.
        range_m:
            Distance to target in meters.
        target_size_m2:
            Target presented area in m^2.
        crew_skill:
            Gunner effectiveness 0.0–1.0.
        target_speed_mps:
            Target movement speed in m/s.
        shooter_speed_mps:
            Shooter movement speed in m/s.
        visibility:
            Visibility factor 0.0–1.0 (1.0 = perfect).
        target_posture:
            "MOVING", "HALTED", "DEFENSIVE", "DUG_IN", "FORTIFIED".
        position_uncertainty_m:
            Uncertainty in target position from Kalman filter.
        weapon_condition:
            Weapon condition 0.0–1.0.
        """
        cfg = self._config
        modifiers: dict[str, float] = {}

        # Base: dispersion-based P(hit)
        # Area ratio: target area vs dispersion area at range
        sigma_m = weapon.base_accuracy_mrad * 0.001 * range_m
        if sigma_m > 0:
            # P(hit) ≈ 1 - exp(-target_area / (2π σ²))
            dispersion_phit = 1.0 - math.exp(
                -target_size_m2 / (2.0 * math.pi * sigma_m * sigma_m)
            )
        else:
            dispersion_phit = cfg.base_hit_fraction
        modifiers["base_dispersion"] = dispersion_phit

        p = dispersion_phit

        # Crew skill modifier
        skill_mod = 0.5 + cfg.crew_skill_weight * crew_skill
        p *= skill_mod
        modifiers["crew_skill"] = skill_mod

        # Target motion penalty
        if target_speed_mps > 1.0:
            motion_pen = max(0.5, 1.0 - cfg.target_motion_penalty * (target_speed_mps / 10.0))
            p *= motion_pen
            modifiers["target_motion"] = motion_pen

        # Shooter motion penalty
        if shooter_speed_mps > 0.5:
            shoot_pen = max(0.3, 1.0 - cfg.shooter_motion_penalty * (shooter_speed_mps / 10.0))
            p *= shoot_pen
            modifiers["shooter_motion"] = shoot_pen

        # Visibility
        vis_mod = 0.3 + 0.7 * visibility
        p *= vis_mod
        modifiers["visibility"] = vis_mod

        # Target posture — dug-in targets present smaller area
        posture_mod = self._posture_mods.get(target_posture, 1.0)
        p *= posture_mod
        modifiers["posture"] = posture_mod

        # Position uncertainty penalty
        if position_uncertainty_m > 0:
            unc_penalty = max(0.3, 1.0 - cfg.uncertainty_penalty_scale * position_uncertainty_m)
            p *= unc_penalty
            modifiers["uncertainty"] = unc_penalty

        # Weapon condition
        cond_mod = 0.5 + 0.5 * weapon_condition
        p *= cond_mod
        modifiers["weapon_condition"] = cond_mod

        # Clamp
        p = max(cfg.min_phit, min(cfg.max_phit, p))

        return HitResult(p_hit=p, range_m=range_m, modifiers=modifiers)

    def compute_guided_pk(
        self,
        ammo: AmmoDefinition,
        range_m: float,
        target_signature: float = 1.0,
        countermeasures: float = 0.0,
    ) -> float:
        """Compute Pk for a guided munition.

        Parameters
        ----------
        ammo:
            Guided ammo definition with pk_at_reference.
        range_m:
            Engagement range.
        target_signature:
            Target signature factor 0.0–1.0 (larger = easier to track).
        countermeasures:
            Countermeasure effectiveness 0.0–1.0.
        """
        pk_base = ammo.pk_at_reference
        if pk_base <= 0:
            return 0.0

        # Range degradation (linear falloff beyond seeker range)
        if ammo.seeker_range_m > 0 and range_m > ammo.seeker_range_m:
            range_factor = ammo.seeker_range_m / range_m
        else:
            range_factor = 1.0

        # Signature factor
        sig_factor = 0.5 + 0.5 * target_signature

        # Countermeasure reduction
        cm_factor = 1.0 - countermeasures * ammo.countermeasure_susceptibility

        pk = pk_base * range_factor * sig_factor * cm_factor
        return max(0.01, min(0.99, pk))

    def resolve_hit(self, p_hit: float) -> bool:
        """Stochastic hit resolution."""
        return float(self._rng.random()) < p_hit

    def get_state(self) -> dict[str, Any]:
        return {"rng_state": self._rng.bit_generator.state}

    def set_state(self, state: dict[str, Any]) -> None:
        self._rng.bit_generator.state = state["rng_state"]
