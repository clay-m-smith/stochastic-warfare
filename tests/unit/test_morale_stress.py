"""Tests for morale/stress.py — combat stress with random walk and sleep deprivation."""

from __future__ import annotations

import numpy as np
import pytest

from stochastic_warfare.morale.stress import StressConfig, StressEngine


# ── helpers ──────────────────────────────────────────────────────────


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def _engine(seed: int = 42, config: StressConfig | None = None) -> StressEngine:
    return StressEngine(_rng(seed), config)


# ── StressConfig ─────────────────────────────────────────────────────


class TestStressConfig:
    def test_defaults(self) -> None:
        cfg = StressConfig()
        assert cfg.combat_stress_rate > 0
        assert cfg.rest_recovery_rate > 0
        assert cfg.sleep_dep_threshold_hours == 24.0

    def test_custom(self) -> None:
        cfg = StressConfig(combat_stress_rate=0.05, sleep_dep_threshold_hours=20.0)
        assert cfg.combat_stress_rate == 0.05
        assert cfg.sleep_dep_threshold_hours == 20.0


# ── update_stress ────────────────────────────────────────────────────


class TestUpdateStress:
    def test_bounded_01(self) -> None:
        engine = _engine()
        stress = 0.5
        for _ in range(200):
            stress = engine.update_stress(stress, dt=1.0, combat_intensity=0.5, sleep_hours=8.0)
            assert 0.0 <= stress <= 1.0

    def test_combat_increases_stress(self) -> None:
        """Sustained combat should generally increase stress."""
        engine = _engine()
        stress = 0.1
        for _ in range(100):
            stress = engine.update_stress(stress, dt=1.0, combat_intensity=0.8, sleep_hours=8.0)
        assert stress > 0.1

    def test_rest_decreases_stress(self) -> None:
        """Rest (no combat) should generally decrease stress."""
        engine = _engine()
        stress = 0.8
        for _ in range(100):
            stress = engine.update_stress(stress, dt=1.0, combat_intensity=0.0, sleep_hours=8.0)
        assert stress < 0.8

    def test_environmental_stress(self) -> None:
        """Environmental stress should add to stress accumulation."""
        e1 = _engine(seed=1)
        stress_no_env = 0.3
        for _ in range(50):
            stress_no_env = e1.update_stress(stress_no_env, dt=1.0, combat_intensity=0.3, sleep_hours=8.0, environmental_stress=0.0)

        e2 = _engine(seed=1)
        stress_env = 0.3
        for _ in range(50):
            stress_env = e2.update_stress(stress_env, dt=1.0, combat_intensity=0.3, sleep_hours=8.0, environmental_stress=0.8)

        assert stress_env > stress_no_env

    def test_zero_dt_no_change(self) -> None:
        """With dt=0, stress should barely change (only noise from sqrt(0)=0)."""
        engine = _engine()
        stress = 0.5
        new_stress = engine.update_stress(stress, dt=0.0, combat_intensity=1.0, sleep_hours=0.0)
        assert new_stress == pytest.approx(stress, abs=0.01)

    def test_deterministic_same_seed(self) -> None:
        e1 = _engine(seed=99)
        e2 = _engine(seed=99)
        stress1, stress2 = 0.3, 0.3
        for _ in range(20):
            stress1 = e1.update_stress(stress1, dt=1.0, combat_intensity=0.5, sleep_hours=6.0)
            stress2 = e2.update_stress(stress2, dt=1.0, combat_intensity=0.5, sleep_hours=6.0)
        assert stress1 == pytest.approx(stress2)


# ── sleep_deprivation_effect ─────────────────────────────────────────


class TestSleepDeprivationEffect:
    def test_under_threshold_no_effect(self) -> None:
        engine = _engine()
        assert engine.sleep_deprivation_effect(12.0) == pytest.approx(1.0)
        assert engine.sleep_deprivation_effect(24.0) == pytest.approx(1.0)

    def test_over_threshold_degradation(self) -> None:
        engine = _engine()
        effect = engine.sleep_deprivation_effect(36.0)
        assert 0.0 < effect < 1.0

    def test_monotonically_decreasing(self) -> None:
        engine = _engine()
        prev = 1.0
        for hours in range(25, 80, 5):
            effect = engine.sleep_deprivation_effect(float(hours))
            assert effect <= prev
            prev = effect

    def test_extreme_deprivation_near_zero(self) -> None:
        engine = _engine()
        effect = engine.sleep_deprivation_effect(200.0)
        assert effect < 0.01

    def test_bounded(self) -> None:
        engine = _engine()
        for hours in [0.0, 10.0, 24.0, 48.0, 72.0, 100.0]:
            effect = engine.sleep_deprivation_effect(hours)
            assert 0.0 <= effect <= 1.0

    def test_custom_threshold(self) -> None:
        cfg = StressConfig(sleep_dep_threshold_hours=12.0)
        engine = _engine(config=cfg)
        # Should start degrading after 12 hours
        assert engine.sleep_deprivation_effect(12.0) == pytest.approx(1.0)
        assert engine.sleep_deprivation_effect(20.0) < 1.0


# ── State round-trip ─────────────────────────────────────────────────


class TestStressState:
    def test_roundtrip(self) -> None:
        engine = _engine(seed=42)
        engine.update_stress(0.3, dt=5.0, combat_intensity=0.5, sleep_hours=6.0)
        state = engine.get_state()

        engine2 = _engine(seed=0)
        engine2.set_state(state)

        v1 = engine.update_stress(0.4, dt=1.0, combat_intensity=0.3, sleep_hours=8.0)
        v2 = engine2.update_stress(0.4, dt=1.0, combat_intensity=0.3, sleep_hours=8.0)
        assert v1 == pytest.approx(v2)
