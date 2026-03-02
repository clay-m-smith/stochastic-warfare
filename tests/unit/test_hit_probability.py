"""Tests for combat/hit_probability.py."""

from __future__ import annotations

import numpy as np
import pytest

from stochastic_warfare.combat.ammunition import AmmoDefinition, WeaponDefinition
from stochastic_warfare.combat.ballistics import BallisticsEngine
from stochastic_warfare.combat.hit_probability import (
    HitProbabilityConfig,
    HitProbabilityEngine,
    HitResult,
)


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def _gun() -> WeaponDefinition:
    return WeaponDefinition(
        weapon_id="gun", display_name="Gun", category="CANNON",
        caliber_mm=120.0, muzzle_velocity_mps=1750.0,
        base_accuracy_mrad=0.2, max_range_m=4000.0,
        compatible_ammo=["ap"],
    )


def _ammo() -> AmmoDefinition:
    return AmmoDefinition(
        ammo_id="ap", display_name="AP", ammo_type="AP",
        mass_kg=8.9, diameter_mm=120.0,
    )


def _guided_ammo() -> AmmoDefinition:
    return AmmoDefinition(
        ammo_id="hellfire", display_name="Hellfire", ammo_type="GUIDED",
        guidance="LASER", pk_at_reference=0.85,
        seeker_range_m=8000.0, countermeasure_susceptibility=0.2,
    )


def _engine(seed: int = 42) -> HitProbabilityEngine:
    rng = _rng(seed)
    bal = BallisticsEngine(rng)
    return HitProbabilityEngine(bal, rng)


class TestComputePhit:
    def test_close_range_high_phit(self) -> None:
        e = _engine()
        result = e.compute_phit(_gun(), _ammo(), range_m=500.0, crew_skill=0.8)
        assert result.p_hit > 0.3

    def test_long_range_lower_phit(self) -> None:
        e = _engine()
        short = e.compute_phit(_gun(), _ammo(), range_m=500.0, crew_skill=0.5)
        long = e.compute_phit(_gun(), _ammo(), range_m=3500.0, crew_skill=0.5)
        assert long.p_hit < short.p_hit

    def test_better_crew_higher_phit(self) -> None:
        e = _engine()
        novice = e.compute_phit(_gun(), _ammo(), range_m=2000.0, crew_skill=0.1)
        expert = e.compute_phit(_gun(), _ammo(), range_m=2000.0, crew_skill=0.9)
        assert expert.p_hit > novice.p_hit

    def test_moving_target_reduces_phit(self) -> None:
        e = _engine()
        stationary = e.compute_phit(_gun(), _ammo(), range_m=2000.0, target_speed_mps=0.0)
        moving = e.compute_phit(_gun(), _ammo(), range_m=2000.0, target_speed_mps=15.0)
        assert moving.p_hit < stationary.p_hit

    def test_moving_shooter_reduces_phit(self) -> None:
        e = _engine()
        halted = e.compute_phit(_gun(), _ammo(), range_m=2000.0, shooter_speed_mps=0.0)
        moving = e.compute_phit(_gun(), _ammo(), range_m=2000.0, shooter_speed_mps=10.0)
        assert moving.p_hit < halted.p_hit

    def test_poor_visibility_reduces_phit(self) -> None:
        e = _engine()
        clear = e.compute_phit(_gun(), _ammo(), range_m=2000.0, visibility=1.0)
        foggy = e.compute_phit(_gun(), _ammo(), range_m=2000.0, visibility=0.2)
        assert foggy.p_hit < clear.p_hit

    def test_dug_in_target_reduces_phit(self) -> None:
        e = _engine()
        moving = e.compute_phit(_gun(), _ammo(), range_m=2000.0, target_posture="MOVING")
        dug_in = e.compute_phit(_gun(), _ammo(), range_m=2000.0, target_posture="DUG_IN")
        assert dug_in.p_hit < moving.p_hit

    def test_position_uncertainty_reduces_phit(self) -> None:
        e = _engine()
        certain = e.compute_phit(_gun(), _ammo(), range_m=2000.0, position_uncertainty_m=0.0)
        uncertain = e.compute_phit(_gun(), _ammo(), range_m=2000.0, position_uncertainty_m=50.0)
        assert uncertain.p_hit < certain.p_hit

    def test_degraded_weapon_reduces_phit(self) -> None:
        e = _engine()
        pristine = e.compute_phit(_gun(), _ammo(), range_m=2000.0, weapon_condition=1.0)
        worn = e.compute_phit(_gun(), _ammo(), range_m=2000.0, weapon_condition=0.3)
        assert worn.p_hit < pristine.p_hit

    def test_phit_clamped_to_bounds(self) -> None:
        e = _engine()
        result = e.compute_phit(_gun(), _ammo(), range_m=100000.0, visibility=0.01)
        assert result.p_hit >= 0.01
        assert result.p_hit <= 0.99

    def test_result_has_modifiers(self) -> None:
        e = _engine()
        result = e.compute_phit(_gun(), _ammo(), range_m=2000.0)
        assert "base_dispersion" in result.modifiers
        assert "crew_skill" in result.modifiers

    def test_larger_target_easier_to_hit(self) -> None:
        e = _engine()
        small = e.compute_phit(_gun(), _ammo(), range_m=2000.0, target_size_m2=2.0)
        large = e.compute_phit(_gun(), _ammo(), range_m=2000.0, target_size_m2=20.0)
        assert large.p_hit > small.p_hit


class TestGuidedPk:
    def test_guided_pk_at_reference(self) -> None:
        e = _engine()
        pk = e.compute_guided_pk(_guided_ammo(), range_m=5000.0)
        # Should be close to pk_at_reference (0.85) at nominal range
        assert pk > 0.5

    def test_guided_pk_degrades_beyond_seeker(self) -> None:
        e = _engine()
        in_range = e.compute_guided_pk(_guided_ammo(), range_m=5000.0)
        beyond = e.compute_guided_pk(_guided_ammo(), range_m=16000.0)
        assert beyond < in_range

    def test_countermeasures_reduce_pk(self) -> None:
        e = _engine()
        no_cm = e.compute_guided_pk(_guided_ammo(), range_m=5000.0, countermeasures=0.0)
        with_cm = e.compute_guided_pk(_guided_ammo(), range_m=5000.0, countermeasures=0.8)
        assert with_cm < no_cm

    def test_low_signature_reduces_pk(self) -> None:
        e = _engine()
        high_sig = e.compute_guided_pk(_guided_ammo(), range_m=5000.0, target_signature=1.0)
        low_sig = e.compute_guided_pk(_guided_ammo(), range_m=5000.0, target_signature=0.2)
        assert low_sig < high_sig

    def test_zero_pk_ammo(self) -> None:
        e = _engine()
        unguided = AmmoDefinition(
            ammo_id="dumb", display_name="Dumb", ammo_type="HE",
            pk_at_reference=0.0,
        )
        pk = e.compute_guided_pk(unguided, range_m=1000.0)
        assert pk == 0.0


class TestResolveHit:
    def test_resolve_hit_deterministic(self) -> None:
        e1 = _engine(42)
        e2 = _engine(42)
        assert e1.resolve_hit(0.5) == e2.resolve_hit(0.5)

    def test_high_phit_usually_hits(self) -> None:
        e = _engine(42)
        hits = sum(1 for _ in range(100) if e.resolve_hit(0.95))
        assert hits > 80

    def test_low_phit_usually_misses(self) -> None:
        e = _engine(42)
        hits = sum(1 for _ in range(100) if e.resolve_hit(0.05))
        assert hits < 20


class TestState:
    def test_state_roundtrip(self) -> None:
        e = _engine(42)
        e.resolve_hit(0.5)
        saved = e.get_state()

        e2 = _engine(99)
        e2.set_state(saved)

        assert e.resolve_hit(0.5) == e2.resolve_hit(0.5)
