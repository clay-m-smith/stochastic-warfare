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
from stochastic_warfare.core.numba_utils import optional_jit

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# JIT-compiled hit probability kernel (Phase 87b)
# ---------------------------------------------------------------------------


@optional_jit
def _hit_probability_kernel(
    base_accuracy_mrad: float,
    range_m: float,
    target_size_m2: float,
    base_hit_fraction: float,
    crew_skill: float,
    crew_skill_weight: float,
    target_speed_mps: float,
    target_motion_penalty: float,
    shooter_speed_mps: float,
    shooter_motion_penalty: float,
    visibility: float,
    posture_mod: float,
    weapon_condition: float,
    position_uncertainty_m: float,
    uncertainty_penalty_scale: float,
    terrain_cover: float,
    elevation_mod: float,
    moderate_condition_floor: float,
    min_phit: float,
    max_phit: float,
) -> float:
    """Pure-math hit probability computation (JIT-compilable).

    Returns the final P(hit) after all modifiers and clamping.
    """
    # Base dispersion
    sigma_m = base_accuracy_mrad * 0.001 * range_m
    if sigma_m > 0.0:
        p = 1.0 - math.exp(-target_size_m2 / (2.0 * math.pi * sigma_m * sigma_m))
    else:
        p = base_hit_fraction

    # Crew skill
    p *= 0.5 + crew_skill_weight * crew_skill

    # Target motion
    if target_speed_mps > 1.0:
        motion_pen = 1.0 - target_motion_penalty * (target_speed_mps / 10.0)
        if motion_pen < 0.5:
            motion_pen = 0.5
        p *= motion_pen

    # Shooter motion
    if shooter_speed_mps > 0.5:
        shoot_pen = 1.0 - shooter_motion_penalty * (shooter_speed_mps / 10.0)
        if shoot_pen < 0.3:
            shoot_pen = 0.3
        p *= shoot_pen

    # Visibility
    p *= 0.3 + 0.7 * visibility

    # Posture
    p *= posture_mod

    # Position uncertainty
    if position_uncertainty_m > 0.0:
        unc_pen = 1.0 - uncertainty_penalty_scale * position_uncertainty_m
        if unc_pen < 0.3:
            unc_pen = 0.3
        p *= unc_pen

    # Weapon condition
    p *= 0.5 + 0.5 * weapon_condition

    # Terrain cover
    if terrain_cover > 0.0:
        p *= 1.0 - terrain_cover

    # Elevation
    if elevation_mod != 1.0:
        p *= elevation_mod

    # Moderate condition floor
    if p < moderate_condition_floor:
        p = moderate_condition_floor

    # Clamp
    if p < min_phit:
        p = min_phit
    if p > max_phit:
        p = max_phit

    return p


class HitProbabilityConfig(BaseModel):
    """Tunable parameters for hit probability computation.

    Sources:
    - Base dispersion model: area-ratio P(hit) from circular error
      probable, standard in ballistic fire control (e.g., USMC TM
      11000-15/1D "Employment of Machine Guns").
    - Crew skill: bounded [0.5, 0.8] — trained gunner ~50% base,
      expert +30% (Jane's Infantry Weapons, various editions).
    - Motion penalties: lead angle error / stabilization degradation.
      Target motion 15% per 10 m/s, shooter motion 25% per 10 m/s
      (reflects inherent difficulty of fire-on-the-move without
      modern stabilization).
    - Posture: DUG_IN 40% area reduction from FM 5-103 fighting position.
    """

    base_hit_fraction: float = 0.8
    crew_skill_weight: float = 0.3
    visibility_weight: float = 0.2
    target_motion_penalty: float = 0.15
    shooter_motion_penalty: float = 0.25
    posture_dug_in_bonus: float = 0.4
    uncertainty_penalty_scale: float = 0.01
    min_phit: float = 0.01
    max_phit: float = 0.99
    moderate_condition_floor: float = 0.03
    """Floor applied after all modifiers but before final clamp.
    Prevents extreme penalty stacking from driving Pk below 3%.
    Since 0.03 > min_phit, only matters when penalties compound."""


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
        terrain_cover: float = 0.0,
        elevation_mod: float = 1.0,
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

        posture_mod = self._posture_mods.get(target_posture, 1.0)

        p = _hit_probability_kernel(
            weapon.base_accuracy_mrad, range_m, target_size_m2,
            cfg.base_hit_fraction,
            crew_skill, cfg.crew_skill_weight,
            target_speed_mps, cfg.target_motion_penalty,
            shooter_speed_mps, cfg.shooter_motion_penalty,
            visibility, posture_mod, weapon_condition,
            position_uncertainty_m, cfg.uncertainty_penalty_scale,
            terrain_cover, elevation_mod,
            cfg.moderate_condition_floor, cfg.min_phit, cfg.max_phit,
        )

        # Build modifiers dict for diagnostics (not in JIT path)
        modifiers: dict[str, float] = {}
        sigma_m = weapon.base_accuracy_mrad * 0.001 * range_m
        if sigma_m > 0:
            modifiers["base_dispersion"] = 1.0 - math.exp(
                -target_size_m2 / (2.0 * math.pi * sigma_m * sigma_m)
            )
        else:
            modifiers["base_dispersion"] = cfg.base_hit_fraction
        modifiers["crew_skill"] = 0.5 + cfg.crew_skill_weight * crew_skill
        if target_speed_mps > 1.0:
            modifiers["target_motion"] = max(0.5, 1.0 - cfg.target_motion_penalty * (target_speed_mps / 10.0))
        if shooter_speed_mps > 0.5:
            modifiers["shooter_motion"] = max(0.3, 1.0 - cfg.shooter_motion_penalty * (shooter_speed_mps / 10.0))
        modifiers["visibility"] = 0.3 + 0.7 * visibility
        modifiers["posture"] = posture_mod
        if position_uncertainty_m > 0:
            modifiers["uncertainty"] = max(0.3, 1.0 - cfg.uncertainty_penalty_scale * position_uncertainty_m)
        modifiers["weapon_condition"] = 0.5 + 0.5 * weapon_condition
        if terrain_cover > 0:
            modifiers["terrain_cover"] = 1.0 - terrain_cover
        if elevation_mod != 1.0:
            modifiers["elevation"] = elevation_mod

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
