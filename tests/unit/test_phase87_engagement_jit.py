"""Phase 87b: Engagement math JIT kernel tests.

Validates that JIT-extracted kernels for hit probability and penetration
produce identical results to the original engine methods.
"""

from __future__ import annotations

import math
from types import SimpleNamespace

import numpy as np
import pytest

from stochastic_warfare.combat.damage import _penetration_kernel
from stochastic_warfare.combat.hit_probability import _hit_probability_kernel


# ---------------------------------------------------------------------------
# 87b: Hit probability kernel
# ---------------------------------------------------------------------------


class TestHitProbabilityKernel:
    """Test _hit_probability_kernel matches HitProbabilityEngine.compute_phit."""

    def _compute_via_engine(self, **kwargs):
        """Run through the engine to get reference P(hit)."""
        from stochastic_warfare.combat.hit_probability import (
            HitProbabilityConfig,
            HitProbabilityEngine,
        )
        from stochastic_warfare.combat.ballistics import BallisticsEngine

        rng = np.random.default_rng(42)
        cfg = HitProbabilityConfig()
        engine = HitProbabilityEngine(BallisticsEngine(rng=rng), rng=rng, config=cfg)

        weapon = SimpleNamespace(base_accuracy_mrad=kwargs.get("base_accuracy_mrad", 1.0))
        ammo = SimpleNamespace()
        result = engine.compute_phit(
            weapon, ammo,
            range_m=kwargs.get("range_m", 1000.0),
            target_size_m2=kwargs.get("target_size_m2", 6.0),
            crew_skill=kwargs.get("crew_skill", 0.5),
            target_speed_mps=kwargs.get("target_speed_mps", 0.0),
            shooter_speed_mps=kwargs.get("shooter_speed_mps", 0.0),
            visibility=kwargs.get("visibility", 1.0),
            target_posture=kwargs.get("target_posture", "MOVING"),
            position_uncertainty_m=kwargs.get("position_uncertainty_m", 0.0),
            weapon_condition=kwargs.get("weapon_condition", 1.0),
            terrain_cover=kwargs.get("terrain_cover", 0.0),
            elevation_mod=kwargs.get("elevation_mod", 1.0),
        )
        return result.p_hit

    def _compute_via_kernel(self, **kwargs):
        """Call the JIT kernel directly with matching params."""
        from stochastic_warfare.combat.hit_probability import HitProbabilityConfig
        cfg = HitProbabilityConfig()

        posture_mods = {
            "MOVING": 1.0, "HALTED": 1.0, "DEFENSIVE": 0.85,
            "DUG_IN": 1.0 - cfg.posture_dug_in_bonus, "FORTIFIED": 0.4,
        }
        posture = kwargs.get("target_posture", "MOVING")

        return _hit_probability_kernel(
            kwargs.get("base_accuracy_mrad", 1.0),
            kwargs.get("range_m", 1000.0),
            kwargs.get("target_size_m2", 6.0),
            cfg.base_hit_fraction,
            kwargs.get("crew_skill", 0.5),
            cfg.crew_skill_weight,
            kwargs.get("target_speed_mps", 0.0),
            cfg.target_motion_penalty,
            kwargs.get("shooter_speed_mps", 0.0),
            cfg.shooter_motion_penalty,
            kwargs.get("visibility", 1.0),
            posture_mods.get(posture, 1.0),
            kwargs.get("weapon_condition", 1.0),
            kwargs.get("position_uncertainty_m", 0.0),
            cfg.uncertainty_penalty_scale,
            kwargs.get("terrain_cover", 0.0),
            kwargs.get("elevation_mod", 1.0),
            cfg.moderate_condition_floor,
            cfg.min_phit,
            cfg.max_phit,
        )

    def test_typical_engagement(self):
        params = dict(base_accuracy_mrad=1.0, range_m=1000.0, crew_skill=0.7)
        assert self._compute_via_kernel(**params) == pytest.approx(
            self._compute_via_engine(**params), abs=1e-10
        )

    def test_all_modifiers(self):
        params = dict(
            base_accuracy_mrad=2.0, range_m=2000.0, target_size_m2=8.0,
            crew_skill=0.8, target_speed_mps=15.0, shooter_speed_mps=5.0,
            visibility=0.5, target_posture="DUG_IN", weapon_condition=0.7,
            position_uncertainty_m=50.0, terrain_cover=0.3, elevation_mod=1.1,
        )
        assert self._compute_via_kernel(**params) == pytest.approx(
            self._compute_via_engine(**params), abs=1e-10
        )

    def test_zero_sigma(self):
        """When base_accuracy_mrad=0, falls back to base_hit_fraction."""
        params = dict(base_accuracy_mrad=0.0, range_m=1000.0)
        assert self._compute_via_kernel(**params) == pytest.approx(
            self._compute_via_engine(**params), abs=1e-10
        )

    def test_extreme_penalties_hit_floor(self):
        """Extreme penalties should hit moderate_condition_floor."""
        params = dict(
            base_accuracy_mrad=5.0, range_m=5000.0,
            visibility=0.1, target_speed_mps=30.0,
            shooter_speed_mps=20.0, weapon_condition=0.1,
        )
        result = self._compute_via_kernel(**params)
        assert result >= 0.03  # moderate_condition_floor

    def test_determinism(self):
        params = dict(base_accuracy_mrad=1.5, range_m=1500.0, crew_skill=0.6)
        a = self._compute_via_kernel(**params)
        b = self._compute_via_kernel(**params)
        assert a == b


# ---------------------------------------------------------------------------
# 87b: Penetration kernel
# ---------------------------------------------------------------------------


class TestPenetrationKernel:
    """Test _penetration_kernel matches DamageEngine.compute_penetration."""

    def test_ap_penetration(self):
        penetrated, pen, armor_eff, margin = _penetration_kernel(
            200.0, 100.0, 0.0, 1000.0, 0.3, 2000.0, 1.5, 1.0, False,
        )
        assert penetrated is True
        assert pen > 0.0
        assert margin > 0.0

    def test_heat_range_independent(self):
        """HEAT penetration should not vary with range."""
        _, pen1, _, _ = _penetration_kernel(400.0, 100.0, 0.0, 500.0, 0.3, 2000.0, 1.5, 1.0, True)
        _, pen2, _, _ = _penetration_kernel(400.0, 100.0, 0.0, 5000.0, 0.3, 2000.0, 1.5, 1.0, True)
        assert pen1 == pen2

    def test_ricochet_at_extreme_angle(self):
        penetrated, pen, _, _ = _penetration_kernel(
            200.0, 50.0, 80.0, 1000.0, 0.3, 2000.0, 1.5, 1.0, False,
        )
        assert penetrated is False
        assert pen == 0.0

    def test_zero_penetration(self):
        penetrated, pen, armor_eff, margin = _penetration_kernel(
            0.0, 100.0, 0.0, 1000.0, 0.3, 2000.0, 1.5, 1.0, False,
        )
        assert penetrated is False
        assert margin == -100.0

    def test_obliquity_increases_effective_armor(self):
        _, _, eff_0, _ = _penetration_kernel(200.0, 100.0, 0.0, 1000.0, 0.3, 2000.0, 1.5, 1.0, False)
        _, _, eff_45, _ = _penetration_kernel(200.0, 100.0, 45.0, 1000.0, 0.3, 2000.0, 1.5, 1.0, False)
        assert eff_45 > eff_0

    def test_armor_effectiveness_multiplier(self):
        """Higher effectiveness means harder to penetrate."""
        _, _, _, margin_rha = _penetration_kernel(200.0, 100.0, 0.0, 0.0, 0.3, 2000.0, 1.5, 1.0, False)
        _, _, _, margin_comp = _penetration_kernel(200.0, 100.0, 0.0, 0.0, 0.3, 2000.0, 1.5, 2.5, False)
        assert margin_rha > margin_comp
