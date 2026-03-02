"""Tests for morale/cohesion.py — unit cohesion modeling."""

from __future__ import annotations

import numpy as np
import pytest

from stochastic_warfare.morale.cohesion import CohesionConfig, CohesionEngine


# ── helpers ──────────────────────────────────────────────────────────


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def _engine(seed: int = 42, config: CohesionConfig | None = None) -> CohesionEngine:
    return CohesionEngine(_rng(seed), config)


# ── CohesionConfig ───────────────────────────────────────────────────


class TestCohesionConfig:
    def test_defaults(self) -> None:
        cfg = CohesionConfig()
        assert cfg.base_cohesion > 0
        assert cfg.personnel_weight > 0
        assert cfg.training_weight > 0

    def test_custom(self) -> None:
        cfg = CohesionConfig(base_cohesion=0.7, personnel_weight=0.5)
        assert cfg.base_cohesion == 0.7
        assert cfg.personnel_weight == 0.5


# ── compute_cohesion ─────────────────────────────────────────────────


class TestComputeCohesion:
    def test_bounded_01(self) -> None:
        engine = _engine()
        for _ in range(100):
            val = engine.compute_cohesion(
                personnel_strength=np.random.default_rng(0).random(),
                training_level=np.random.default_rng(0).random(),
                nearby_friendly_count=np.random.default_rng(0).integers(0, 10),
                leader_present=True,
                isolated=False,
            )
            assert 0.0 <= val <= 1.0

    def test_full_strength_high_cohesion(self) -> None:
        engine = _engine()
        val = engine.compute_cohesion(
            personnel_strength=1.0,
            training_level=1.0,
            nearby_friendly_count=5,
            leader_present=True,
            isolated=False,
        )
        assert val > 0.8

    def test_depleted_low_cohesion(self) -> None:
        engine = _engine()
        val = engine.compute_cohesion(
            personnel_strength=0.1,
            training_level=0.1,
            nearby_friendly_count=0,
            leader_present=False,
            isolated=True,
        )
        assert val < 0.5

    def test_personnel_strength_matters(self) -> None:
        engine = _engine(seed=1)
        low = engine.compute_cohesion(0.1, 0.5, 2, False, False)
        engine2 = _engine(seed=1)
        high = engine2.compute_cohesion(1.0, 0.5, 2, False, False)
        assert high > low

    def test_training_matters(self) -> None:
        engine = _engine(seed=1)
        low = engine.compute_cohesion(0.5, 0.1, 2, False, False)
        engine2 = _engine(seed=1)
        high = engine2.compute_cohesion(0.5, 1.0, 2, False, False)
        assert high > low

    def test_nearby_friendlies_capped(self) -> None:
        """Extra friendlies beyond 5 should not add more cohesion."""
        engine = _engine(seed=1)
        val_5 = engine.compute_cohesion(0.5, 0.5, 5, False, False)
        engine2 = _engine(seed=1)
        val_10 = engine2.compute_cohesion(0.5, 0.5, 10, False, False)
        assert val_5 == pytest.approx(val_10)

    def test_leader_bonus(self) -> None:
        engine = _engine(seed=1)
        no_leader = engine.compute_cohesion(0.5, 0.5, 2, False, False)
        engine2 = _engine(seed=1)
        with_leader = engine2.compute_cohesion(0.5, 0.5, 2, True, False)
        assert with_leader > no_leader

    def test_isolation_penalty(self) -> None:
        engine = _engine(seed=1)
        connected = engine.compute_cohesion(0.5, 0.5, 2, False, False)
        engine2 = _engine(seed=1)
        isolated = engine2.compute_cohesion(0.5, 0.5, 2, False, True)
        assert connected > isolated

    def test_deterministic_same_seed(self) -> None:
        e1 = _engine(seed=99)
        e2 = _engine(seed=99)
        v1 = e1.compute_cohesion(0.7, 0.6, 3, True, False)
        v2 = e2.compute_cohesion(0.7, 0.6, 3, True, False)
        assert v1 == pytest.approx(v2)


# ── leadership_cascade ───────────────────────────────────────────────


class TestLeadershipCascade:
    def test_no_leader_lost_zero_drop(self) -> None:
        engine = _engine()
        drop = engine.leadership_cascade("u1", leader_lost=False, subordinate_count=10)
        assert drop == 0.0

    def test_leader_lost_positive_drop(self) -> None:
        engine = _engine()
        drop = engine.leadership_cascade("u1", leader_lost=True, subordinate_count=5)
        assert drop > 0.0

    def test_more_subordinates_larger_drop(self) -> None:
        e1 = _engine(seed=1)
        drop_few = e1.leadership_cascade("u1", leader_lost=True, subordinate_count=2)
        e2 = _engine(seed=1)
        drop_many = e2.leadership_cascade("u1", leader_lost=True, subordinate_count=20)
        assert drop_many > drop_few

    def test_drop_nonnegative(self) -> None:
        engine = _engine()
        for _ in range(100):
            drop = engine.leadership_cascade("u1", leader_lost=True, subordinate_count=3)
            assert drop >= 0.0


# ── unit_history_modifier ────────────────────────────────────────────


class TestUnitHistoryModifier:
    def test_no_history_zero(self) -> None:
        engine = _engine()
        mod = engine.unit_history_modifier(combat_hours=0.0, prior_routs=0)
        assert mod == pytest.approx(0.0)

    def test_combat_experience_positive(self) -> None:
        engine = _engine()
        mod = engine.unit_history_modifier(combat_hours=100.0, prior_routs=0)
        assert mod > 0.0

    def test_prior_routs_negative(self) -> None:
        engine = _engine()
        mod = engine.unit_history_modifier(combat_hours=0.0, prior_routs=5)
        assert mod < 0.0

    def test_experience_diminishing_returns(self) -> None:
        engine = _engine()
        mod_10 = engine.unit_history_modifier(combat_hours=10.0, prior_routs=0)
        mod_1000 = engine.unit_history_modifier(combat_hours=1000.0, prior_routs=0)
        # 100x more hours should NOT produce 100x more bonus
        assert mod_1000 < 100 * mod_10
        assert mod_1000 < 1.0  # saturates below 1.0


# ── State round-trip ─────────────────────────────────────────────────


class TestCohesionState:
    def test_roundtrip(self) -> None:
        engine = _engine(seed=42)
        engine.compute_cohesion(0.5, 0.5, 2, True, False)
        state = engine.get_state()

        engine2 = _engine(seed=0)
        engine2.set_state(state)

        # After restore, should produce same outputs
        v1 = engine.compute_cohesion(0.7, 0.6, 3, False, True)
        v2 = engine2.compute_cohesion(0.7, 0.6, 3, False, True)
        assert v1 == pytest.approx(v2)
