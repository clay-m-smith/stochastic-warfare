"""Unit tests for SuppressionEngine — fire volume, decay, spreading."""

from __future__ import annotations

import pytest

from stochastic_warfare.combat.suppression import (
    SuppressionConfig,
    SuppressionEngine,
    SuppressionLevel,
    UnitSuppressionState,
)
from stochastic_warfare.core.events import EventBus

from .conftest import _rng


def _make_engine(seed: int = 42, **cfg_kwargs) -> SuppressionEngine:
    config = SuppressionConfig(**cfg_kwargs) if cfg_kwargs else None
    return SuppressionEngine(EventBus(), _rng(seed), config=config)


class TestApplyFireVolume:
    """Suppression from incoming fire."""

    def test_caliber_weight_scaling(self):
        """Larger caliber produces more suppression."""
        eng = _make_engine(seed=10)
        state_small = UnitSuppressionState()
        eng.apply_fire_volume(state_small, rounds_per_minute=60, caliber_mm=7.62,
                              range_m=500.0, duration_s=10.0)

        eng2 = _make_engine(seed=10)
        state_large = UnitSuppressionState()
        eng2.apply_fire_volume(state_large, rounds_per_minute=60, caliber_mm=30.0,
                               range_m=500.0, duration_s=10.0)
        assert state_large.value > state_small.value

    def test_volume_weight_scaling(self):
        """Higher fire rate produces more suppression."""
        eng = _make_engine(seed=10)
        state_low = UnitSuppressionState()
        eng.apply_fire_volume(state_low, rounds_per_minute=10, caliber_mm=7.62,
                              range_m=500.0, duration_s=10.0)

        eng2 = _make_engine(seed=10)
        state_high = UnitSuppressionState()
        eng2.apply_fire_volume(state_high, rounds_per_minute=600, caliber_mm=7.62,
                               range_m=500.0, duration_s=10.0)
        assert state_high.value > state_low.value

    def test_closer_range_more_suppressive(self):
        eng = _make_engine(seed=10)
        state_close = UnitSuppressionState()
        eng.apply_fire_volume(state_close, rounds_per_minute=60, caliber_mm=7.62,
                              range_m=100.0, duration_s=10.0)

        eng2 = _make_engine(seed=10)
        state_far = UnitSuppressionState()
        eng2.apply_fire_volume(state_far, rounds_per_minute=60, caliber_mm=7.62,
                               range_m=4000.0, duration_s=10.0)
        assert state_close.value > state_far.value

    def test_suppression_clamped_to_1(self):
        eng = _make_engine()
        state = UnitSuppressionState()
        # Apply massive fire volume
        for _ in range(20):
            eng.apply_fire_volume(state, rounds_per_minute=1000, caliber_mm=30.0,
                                  range_m=100.0, duration_s=60.0)
        assert state.value <= 1.0


class TestSuppressionLevels:
    """Graduated suppression effects."""

    def test_pinned_accuracy_penalty(self):
        eng = _make_engine()
        effects = eng.compute_suppression_effect(SuppressionLevel.PINNED)
        assert effects["accuracy_penalty"] == pytest.approx(0.8)
        assert effects["movement_speed_factor"] == pytest.approx(0.0)

    def test_heavy_movement_factor(self):
        eng = _make_engine()
        effects = eng.compute_suppression_effect(SuppressionLevel.HEAVY)
        assert effects["movement_speed_factor"] == pytest.approx(0.3)

    def test_none_no_effects(self):
        eng = _make_engine()
        effects = eng.compute_suppression_effect(SuppressionLevel.NONE)
        assert effects["accuracy_penalty"] == 0.0
        assert effects["movement_speed_factor"] == 1.0

    def test_level_from_threshold(self):
        eng = _make_engine(pinned_threshold=0.85, heavy_threshold=0.60)
        assert eng._level_from_value(0.90) == SuppressionLevel.PINNED
        assert eng._level_from_value(0.70) == SuppressionLevel.HEAVY
        assert eng._level_from_value(0.05) == SuppressionLevel.NONE


class TestSuppressionDecay:
    """Time-based suppression decay."""

    def test_decay_reduces_value(self):
        eng = _make_engine()
        state = UnitSuppressionState(value=0.8)
        eng.update_suppression(state, dt=5.0)
        assert state.value < 0.8

    def test_decay_never_below_zero(self):
        eng = _make_engine()
        state = UnitSuppressionState(value=0.01)
        eng.update_suppression(state, dt=1000.0)
        assert state.value >= 0.0


class TestSuppressionSpread:
    """Suppression spreading to nearby units."""

    def test_spread_within_range(self):
        eng = _make_engine(spread_max_distance_m=50.0, spread_factor=0.3)
        source = UnitSuppressionState(value=0.8)
        neighbor = UnitSuppressionState(value=0.0)
        eng.spread_suppression(source, [(neighbor, 25.0)])
        assert neighbor.value > 0.0

    def test_spread_beyond_max_distance(self):
        eng = _make_engine(spread_max_distance_m=50.0)
        source = UnitSuppressionState(value=0.8)
        neighbor = UnitSuppressionState(value=0.0)
        eng.spread_suppression(source, [(neighbor, 100.0)])
        assert neighbor.value == 0.0


class TestSuppressionState:
    def test_unit_suppression_state_roundtrip(self):
        state = UnitSuppressionState(value=0.65, source_direction=1.2)
        s = state.get_state()
        state2 = UnitSuppressionState()
        state2.set_state(s)
        assert state2.value == pytest.approx(0.65)
        assert state2.source_direction == pytest.approx(1.2)

    def test_engine_state_roundtrip(self):
        eng = _make_engine(seed=77)
        state = eng.get_state()
        eng2 = _make_engine(seed=1)
        eng2.set_state(state)
        assert eng._rng.random() == eng2._rng.random()
