"""Unit tests for HitProbabilityEngine — Pk computation with modifiers."""

from __future__ import annotations

import pytest

from stochastic_warfare.combat.ballistics import BallisticsEngine
from stochastic_warfare.combat.hit_probability import (
    HitProbabilityConfig,
    HitProbabilityEngine,
)

from .conftest import _make_ap, _make_guided_missile, _make_gun, _rng


def _make_hit_engine(seed: int = 42, **cfg_kwargs) -> HitProbabilityEngine:
    rng = _rng(seed)
    ballistics = BallisticsEngine(rng)
    config = HitProbabilityConfig(**cfg_kwargs) if cfg_kwargs else None
    return HitProbabilityEngine(ballistics, _rng(seed + 1), config=config)


class TestComputePhit:
    """Unguided hit probability computation."""

    def test_baseline_phit(self):
        eng = _make_hit_engine()
        weapon = _make_gun()
        ammo = _make_ap()
        result = eng.compute_phit(weapon, ammo, range_m=1000.0)
        assert 0.01 <= result.p_hit <= 0.99

    def test_target_motion_penalty(self):
        eng = _make_hit_engine()
        weapon = _make_gun()
        ammo = _make_ap()
        static = eng.compute_phit(weapon, ammo, range_m=1000.0, target_speed_mps=0.0)
        moving = eng.compute_phit(weapon, ammo, range_m=1000.0, target_speed_mps=15.0)
        assert moving.p_hit < static.p_hit

    def test_shooter_motion_penalty(self):
        eng = _make_hit_engine()
        weapon = _make_gun()
        ammo = _make_ap()
        halted = eng.compute_phit(weapon, ammo, range_m=1000.0, shooter_speed_mps=0.0)
        moving = eng.compute_phit(weapon, ammo, range_m=1000.0, shooter_speed_mps=10.0)
        assert moving.p_hit < halted.p_hit

    def test_visibility_affects_phit(self):
        eng = _make_hit_engine()
        weapon = _make_gun()
        ammo = _make_ap()
        clear = eng.compute_phit(weapon, ammo, range_m=1000.0, visibility=1.0)
        foggy = eng.compute_phit(weapon, ammo, range_m=1000.0, visibility=0.2)
        assert foggy.p_hit < clear.p_hit

    def test_dug_in_reduces_target_area(self):
        eng = _make_hit_engine()
        weapon = _make_gun()
        ammo = _make_ap()
        moving = eng.compute_phit(weapon, ammo, range_m=1000.0, target_posture="MOVING")
        dug_in = eng.compute_phit(weapon, ammo, range_m=1000.0, target_posture="DUG_IN")
        assert dug_in.p_hit < moving.p_hit

    def test_position_uncertainty_penalty(self):
        eng = _make_hit_engine()
        weapon = _make_gun()
        ammo = _make_ap()
        certain = eng.compute_phit(weapon, ammo, range_m=1000.0, position_uncertainty_m=0.0)
        uncertain = eng.compute_phit(weapon, ammo, range_m=1000.0, position_uncertainty_m=50.0)
        assert uncertain.p_hit < certain.p_hit

    def test_moderate_condition_floor(self):
        """Extreme penalty stacking can't push below moderate_condition_floor (3%)."""
        eng = _make_hit_engine(moderate_condition_floor=0.03)
        weapon = _make_gun(base_accuracy_mrad=10.0)  # very inaccurate
        ammo = _make_ap()
        result = eng.compute_phit(
            weapon, ammo, range_m=3000.0,
            target_speed_mps=20.0,
            shooter_speed_mps=15.0,
            visibility=0.1,
            target_posture="FORTIFIED",
            position_uncertainty_m=100.0,
        )
        assert result.p_hit >= 0.03

    def test_max_phit_clamp(self):
        eng = _make_hit_engine(max_phit=0.99)
        weapon = _make_gun(base_accuracy_mrad=0.01)  # laser-accurate
        ammo = _make_ap()
        result = eng.compute_phit(weapon, ammo, range_m=100.0, crew_skill=1.0)
        assert result.p_hit <= 0.99

    def test_terrain_cover_modifier(self):
        eng = _make_hit_engine()
        weapon = _make_gun()
        ammo = _make_ap()
        exposed = eng.compute_phit(weapon, ammo, range_m=1000.0, terrain_cover=0.0)
        covered = eng.compute_phit(weapon, ammo, range_m=1000.0, terrain_cover=0.5)
        assert covered.p_hit < exposed.p_hit

    def test_modifiers_dict_populated(self):
        eng = _make_hit_engine()
        weapon = _make_gun()
        ammo = _make_ap()
        result = eng.compute_phit(
            weapon, ammo, range_m=1000.0,
            target_speed_mps=5.0,
            visibility=0.8,
        )
        assert "base_dispersion" in result.modifiers
        assert "crew_skill" in result.modifiers


class TestComputeGuidedPk:
    """Guided munition Pk computation."""

    def test_guided_pk_at_reference(self):
        eng = _make_hit_engine()
        ammo = _make_guided_missile(pk_at_reference=0.85)
        pk = eng.compute_guided_pk(ammo, range_m=1000.0)
        assert pk == pytest.approx(0.85 * (0.5 + 0.5 * 1.0) * 1.0, abs=0.01)

    def test_countermeasure_reduces_pk(self):
        eng = _make_hit_engine()
        ammo = _make_guided_missile(pk_at_reference=0.85, countermeasure_susceptibility=0.5)
        pk_no_cm = eng.compute_guided_pk(ammo, range_m=1000.0, countermeasures=0.0)
        pk_cm = eng.compute_guided_pk(ammo, range_m=1000.0, countermeasures=0.8)
        assert pk_cm < pk_no_cm

    def test_beyond_seeker_range_degrades(self):
        eng = _make_hit_engine()
        ammo = _make_guided_missile(pk_at_reference=0.85, seeker_range_m=5000.0)
        pk_in = eng.compute_guided_pk(ammo, range_m=3000.0)
        pk_out = eng.compute_guided_pk(ammo, range_m=10000.0)
        assert pk_out < pk_in


class TestResolveHit:
    """Stochastic hit resolution."""

    def test_resolve_hit_determinism(self):
        eng1 = _make_hit_engine(seed=42)
        eng2 = _make_hit_engine(seed=42)
        # Same seed → same result
        assert eng1.resolve_hit(0.5) == eng2.resolve_hit(0.5)

    def test_state_roundtrip(self):
        eng = _make_hit_engine(seed=99)
        state = eng.get_state()
        eng2 = _make_hit_engine(seed=1)
        eng2.set_state(state)
        assert eng._rng.random() == eng2._rng.random()
