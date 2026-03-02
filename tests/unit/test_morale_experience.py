"""Tests for morale/experience.py — experience progression and combat effectiveness."""

from __future__ import annotations

import numpy as np
import pytest

from stochastic_warfare.morale.experience import ExperienceConfig, ExperienceEngine


# ── helpers ──────────────────────────────────────────────────────────


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def _engine(seed: int = 42, config: ExperienceConfig | None = None) -> ExperienceEngine:
    return ExperienceEngine(_rng(seed), config)


# ── ExperienceConfig ─────────────────────────────────────────────────


class TestExperienceConfig:
    def test_defaults(self) -> None:
        cfg = ExperienceConfig()
        assert cfg.learning_rate > 0
        assert cfg.diminishing_returns_factor > 0
        assert cfg.max_combat_modifier > cfg.min_combat_modifier

    def test_custom(self) -> None:
        cfg = ExperienceConfig(learning_rate=0.05, max_combat_modifier=2.0)
        assert cfg.learning_rate == 0.05
        assert cfg.max_combat_modifier == 2.0


# ── update_experience ────────────────────────────────────────────────


class TestUpdateExperience:
    def test_nonnegative(self) -> None:
        engine = _engine()
        exp = engine.update_experience(0.0, combat_hours=1.0)
        assert exp >= 0.0

    def test_combat_increases_experience(self) -> None:
        engine = _engine()
        exp = engine.update_experience(0.0, combat_hours=10.0)
        assert exp > 0.0

    def test_zero_combat_hours_no_gain(self) -> None:
        engine = _engine()
        exp = engine.update_experience(5.0, combat_hours=0.0)
        assert exp == pytest.approx(5.0, abs=0.01)

    def test_diminishing_returns(self) -> None:
        """Experienced units gain less from the same combat hours."""
        e1 = _engine(seed=1)
        gain_green = e1.update_experience(0.0, combat_hours=10.0) - 0.0

        e2 = _engine(seed=1)
        gain_veteran = e2.update_experience(50.0, combat_hours=10.0) - 50.0

        assert gain_green > gain_veteran

    def test_accepts_override_rng(self) -> None:
        engine = _engine(seed=42)
        override_rng = _rng(seed=99)
        exp = engine.update_experience(0.0, combat_hours=5.0, rng=override_rng)
        assert exp >= 0.0

    def test_deterministic_same_seed(self) -> None:
        e1 = _engine(seed=123)
        e2 = _engine(seed=123)
        exp1 = e1.update_experience(1.0, combat_hours=5.0)
        exp2 = e2.update_experience(1.0, combat_hours=5.0)
        assert exp1 == pytest.approx(exp2)

    def test_accumulated_over_time(self) -> None:
        engine = _engine()
        exp = 0.0
        for _ in range(100):
            exp = engine.update_experience(exp, combat_hours=1.0)
        assert exp > 0.5


# ── compute_combat_modifier ──────────────────────────────────────────


class TestComputeCombatModifier:
    def test_zero_experience_minimum(self) -> None:
        engine = _engine()
        mod = engine.compute_combat_modifier(0.0, training_level=0.0)
        assert mod == pytest.approx(0.5)

    def test_high_experience_approaches_max(self) -> None:
        engine = _engine()
        mod = engine.compute_combat_modifier(100.0, training_level=1.0)
        assert mod > 1.3

    def test_bounded(self) -> None:
        engine = _engine()
        cfg = engine._config
        for exp in [0.0, 1.0, 10.0, 100.0, 1000.0]:
            for tl in [0.0, 0.5, 1.0]:
                mod = engine.compute_combat_modifier(exp, tl)
                assert cfg.min_combat_modifier <= mod <= cfg.max_combat_modifier

    def test_training_amplifies(self) -> None:
        engine = _engine()
        mod_untrained = engine.compute_combat_modifier(10.0, training_level=0.0)
        mod_trained = engine.compute_combat_modifier(10.0, training_level=1.0)
        assert mod_trained > mod_untrained

    def test_monotonic_in_experience(self) -> None:
        engine = _engine()
        prev = 0.0
        for exp in [0.0, 1.0, 5.0, 10.0, 50.0, 100.0]:
            mod = engine.compute_combat_modifier(exp, training_level=0.5)
            assert mod >= prev
            prev = mod


# ── State round-trip ─────────────────────────────────────────────────


class TestExperienceState:
    def test_roundtrip(self) -> None:
        engine = _engine(seed=42)
        engine.update_experience(0.0, combat_hours=5.0)
        state = engine.get_state()

        engine2 = _engine(seed=0)
        engine2.set_state(state)

        v1 = engine.update_experience(1.0, combat_hours=3.0)
        v2 = engine2.update_experience(1.0, combat_hours=3.0)
        assert v1 == pytest.approx(v2)
