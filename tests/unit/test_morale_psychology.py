"""Tests for morale/psychology.py — psychological operations and surrender inducement."""

from __future__ import annotations

import numpy as np
import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.morale.psychology import (
    PsychologyConfig,
    PsychologyEngine,
    PsyopResult,
)


# ── helpers ──────────────────────────────────────────────────────────


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def _engine(seed: int = 42, config: PsychologyConfig | None = None) -> PsychologyEngine:
    bus = EventBus()
    return PsychologyEngine(bus, _rng(seed), config)


# ── PsychologyConfig ────────────────────────────────────────────────


class TestPsychologyConfig:
    def test_defaults(self) -> None:
        cfg = PsychologyConfig()
        assert cfg.psyop_base_effect > 0
        assert cfg.surrender_force_ratio_threshold > 0

    def test_custom(self) -> None:
        cfg = PsychologyConfig(psyop_base_effect=0.2, surrender_force_ratio_threshold=5.0)
        assert cfg.psyop_base_effect == 0.2
        assert cfg.surrender_force_ratio_threshold == 5.0


# ── apply_psyop ──────────────────────────────────────────────────────


class TestApplyPsyop:
    def test_returns_psyop_result(self) -> None:
        engine = _engine()
        result = engine.apply_psyop(target_morale_state=0, psyop_intensity=0.5, visibility=0.5)
        assert isinstance(result, PsyopResult)

    def test_surrendered_no_effect(self) -> None:
        engine = _engine()
        result = engine.apply_psyop(target_morale_state=4, psyop_intensity=1.0, visibility=1.0)
        assert result.morale_degradation == 0.0
        assert result.effective is False

    def test_higher_intensity_more_effect(self) -> None:
        e1 = _engine(seed=1)
        low = e1.apply_psyop(target_morale_state=1, psyop_intensity=0.1, visibility=0.5)
        e2 = _engine(seed=1)
        high = e2.apply_psyop(target_morale_state=1, psyop_intensity=1.0, visibility=0.5)
        assert high.morale_degradation > low.morale_degradation

    def test_worse_morale_more_susceptible(self) -> None:
        e1 = _engine(seed=1)
        steady = e1.apply_psyop(target_morale_state=0, psyop_intensity=0.5, visibility=0.5)
        e2 = _engine(seed=1)
        broken = e2.apply_psyop(target_morale_state=2, psyop_intensity=0.5, visibility=0.5)
        assert broken.morale_degradation > steady.morale_degradation

    def test_visibility_amplifies(self) -> None:
        e1 = _engine(seed=1)
        low_vis = e1.apply_psyop(target_morale_state=1, psyop_intensity=0.5, visibility=0.0)
        e2 = _engine(seed=1)
        high_vis = e2.apply_psyop(target_morale_state=1, psyop_intensity=0.5, visibility=1.0)
        assert high_vis.morale_degradation > low_vis.morale_degradation

    def test_degradation_bounded(self) -> None:
        engine = _engine()
        for _ in range(100):
            result = engine.apply_psyop(target_morale_state=3, psyop_intensity=1.0, visibility=1.0)
            assert 0.0 <= result.morale_degradation <= 1.0

    def test_psyop_result_get_state(self) -> None:
        result = PsyopResult(morale_degradation=0.15, effective=True, description="test")
        state = result.get_state()
        assert state["morale_degradation"] == 0.15
        assert state["effective"] is True


# ── surrender_inducement ─────────────────────────────────────────────


class TestSurrenderInducement:
    def test_steady_zero(self) -> None:
        engine = _engine()
        prob = engine.surrender_inducement(morale_state_int=0, force_ratio=5.0, isolation_factor=1.0)
        assert prob == 0.0

    def test_shaken_zero(self) -> None:
        engine = _engine()
        prob = engine.surrender_inducement(morale_state_int=1, force_ratio=5.0, isolation_factor=1.0)
        assert prob == 0.0

    def test_broken_nonzero(self) -> None:
        engine = _engine()
        prob = engine.surrender_inducement(morale_state_int=2, force_ratio=5.0, isolation_factor=0.5)
        assert prob > 0.0

    def test_routed_higher_than_broken(self) -> None:
        engine = _engine()
        broken = engine.surrender_inducement(morale_state_int=2, force_ratio=3.0, isolation_factor=0.5)
        routed = engine.surrender_inducement(morale_state_int=3, force_ratio=3.0, isolation_factor=0.5)
        assert routed > broken

    def test_already_surrendered(self) -> None:
        engine = _engine()
        prob = engine.surrender_inducement(morale_state_int=4, force_ratio=1.0, isolation_factor=0.0)
        assert prob == 1.0

    def test_high_force_ratio_increases(self) -> None:
        engine = _engine()
        low_ratio = engine.surrender_inducement(morale_state_int=2, force_ratio=1.0, isolation_factor=0.0)
        high_ratio = engine.surrender_inducement(morale_state_int=2, force_ratio=10.0, isolation_factor=0.0)
        assert high_ratio > low_ratio

    def test_isolation_increases(self) -> None:
        engine = _engine()
        connected = engine.surrender_inducement(morale_state_int=2, force_ratio=3.0, isolation_factor=0.0)
        isolated = engine.surrender_inducement(morale_state_int=2, force_ratio=3.0, isolation_factor=1.0)
        assert isolated > connected

    def test_bounded(self) -> None:
        engine = _engine()
        prob = engine.surrender_inducement(morale_state_int=3, force_ratio=100.0, isolation_factor=1.0)
        assert 0.0 <= prob <= 1.0


# ── compute_civilian_reaction ────────────────────────────────────────


class TestCivilianReaction:
    def test_returns_valid_string(self) -> None:
        engine = _engine()
        result = engine.compute_civilian_reaction(0.5, 0.5)
        assert result in ("cooperative", "neutral", "hostile")

    def test_supportive_low_intensity(self) -> None:
        """Supportive population + low intensity should tend cooperative."""
        results = set()
        for seed in range(50):
            engine = _engine(seed=seed)
            results.add(engine.compute_civilian_reaction(0.9, 0.1))
        assert "cooperative" in results

    def test_hostile_high_intensity(self) -> None:
        """Hostile population + high intensity should tend hostile."""
        results = set()
        for seed in range(50):
            engine = _engine(seed=seed)
            results.add(engine.compute_civilian_reaction(0.1, 0.9))
        assert "hostile" in results


# ── State round-trip ─────────────────────────────────────────────────


class TestPsychologyState:
    def test_roundtrip(self) -> None:
        engine = _engine(seed=42)
        engine.apply_psyop(1, 0.5, 0.5)
        state = engine.get_state()

        engine2 = _engine(seed=0)
        engine2.set_state(state)

        r1 = engine.apply_psyop(2, 0.3, 0.7)
        r2 = engine2.apply_psyop(2, 0.3, 0.7)
        assert r1.morale_degradation == pytest.approx(r2.morale_degradation)
