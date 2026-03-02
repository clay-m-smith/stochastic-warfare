"""Tests for combat/suppression.py."""

from __future__ import annotations

import numpy as np
import pytest

from stochastic_warfare.combat.suppression import (
    SuppressionConfig,
    SuppressionEngine,
    SuppressionLevel,
    SuppressionResult,
    UnitSuppressionState,
)
from stochastic_warfare.core.events import EventBus


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def _engine(seed: int = 42) -> SuppressionEngine:
    return SuppressionEngine(EventBus(), _rng(seed))


class TestSuppressionLevel:
    def test_enum_ordering(self) -> None:
        assert SuppressionLevel.NONE < SuppressionLevel.LIGHT
        assert SuppressionLevel.LIGHT < SuppressionLevel.MODERATE
        assert SuppressionLevel.MODERATE < SuppressionLevel.HEAVY
        assert SuppressionLevel.HEAVY < SuppressionLevel.PINNED


class TestApplyFireVolume:
    def test_fire_increases_suppression(self) -> None:
        e = _engine()
        state = UnitSuppressionState()
        result = e.apply_fire_volume(state, rounds_per_minute=120.0, caliber_mm=7.62, range_m=500.0, duration_s=5.0)
        assert result.suppression_value > 0
        assert state.value > 0

    def test_heavy_fire_high_suppression(self) -> None:
        e = _engine()
        state = UnitSuppressionState()
        e.apply_fire_volume(state, rounds_per_minute=600.0, caliber_mm=12.7, range_m=200.0, duration_s=10.0)
        e.apply_fire_volume(state, rounds_per_minute=600.0, caliber_mm=12.7, range_m=200.0, duration_s=10.0)
        assert state.value > 0.3

    def test_larger_caliber_more_suppressive(self) -> None:
        e1 = _engine(42)
        e2 = _engine(42)
        s1 = UnitSuppressionState()
        s2 = UnitSuppressionState()
        e1.apply_fire_volume(s1, rounds_per_minute=100.0, caliber_mm=5.56, range_m=500.0, duration_s=5.0)
        e2.apply_fire_volume(s2, rounds_per_minute=100.0, caliber_mm=155.0, range_m=500.0, duration_s=5.0)
        assert s2.value > s1.value

    def test_closer_range_more_suppressive(self) -> None:
        e1 = _engine(42)
        e2 = _engine(42)
        s1 = UnitSuppressionState()
        s2 = UnitSuppressionState()
        e1.apply_fire_volume(s1, rounds_per_minute=200.0, caliber_mm=7.62, range_m=200.0, duration_s=5.0)
        e2.apply_fire_volume(s2, rounds_per_minute=200.0, caliber_mm=7.62, range_m=4000.0, duration_s=5.0)
        assert s1.value > s2.value

    def test_suppression_capped_at_one(self) -> None:
        e = _engine()
        state = UnitSuppressionState()
        for _ in range(20):
            e.apply_fire_volume(state, rounds_per_minute=1000.0, caliber_mm=155.0, range_m=100.0, duration_s=60.0)
        assert state.value <= 1.0

    def test_source_direction_recorded(self) -> None:
        e = _engine()
        state = UnitSuppressionState()
        e.apply_fire_volume(state, rounds_per_minute=100.0, caliber_mm=7.62, range_m=500.0, duration_s=5.0, source_direction=1.57)
        assert state.source_direction == pytest.approx(1.57)


class TestSuppressionEffects:
    def test_none_no_penalties(self) -> None:
        e = _engine()
        effects = e.compute_suppression_effect(SuppressionLevel.NONE)
        assert effects["accuracy_penalty"] == 0.0
        assert effects["movement_speed_factor"] == 1.0

    def test_pinned_severe_penalties(self) -> None:
        e = _engine()
        effects = e.compute_suppression_effect(SuppressionLevel.PINNED)
        assert effects["accuracy_penalty"] == 0.8
        assert effects["movement_speed_factor"] == 0.0
        assert effects["morale_modifier"] == -0.5

    def test_effects_increase_with_level(self) -> None:
        e = _engine()
        light = e.compute_suppression_effect(SuppressionLevel.LIGHT)
        heavy = e.compute_suppression_effect(SuppressionLevel.HEAVY)
        assert heavy["accuracy_penalty"] > light["accuracy_penalty"]
        assert heavy["movement_speed_factor"] < light["movement_speed_factor"]


class TestDecay:
    def test_decay_reduces_suppression(self) -> None:
        e = _engine()
        state = UnitSuppressionState(value=0.5)
        e.update_suppression(state, dt=2.0)
        assert state.value < 0.5

    def test_decay_does_not_go_negative(self) -> None:
        e = _engine()
        state = UnitSuppressionState(value=0.01)
        e.update_suppression(state, dt=100.0)
        assert state.value >= 0.0

    def test_longer_time_more_decay(self) -> None:
        e1 = _engine()
        e2 = _engine()
        s1 = UnitSuppressionState(value=0.8)
        s2 = UnitSuppressionState(value=0.8)
        e1.update_suppression(s1, dt=1.0)
        e2.update_suppression(s2, dt=5.0)
        assert s2.value < s1.value


class TestSpread:
    def test_spread_to_nearby(self) -> None:
        e = _engine()
        source = UnitSuppressionState(value=0.8)
        neighbor = UnitSuppressionState(value=0.0)
        e.spread_suppression(source, [(neighbor, 20.0)])
        assert neighbor.value > 0

    def test_no_spread_beyond_max_distance(self) -> None:
        e = _engine()
        source = UnitSuppressionState(value=0.8)
        neighbor = UnitSuppressionState(value=0.0)
        e.spread_suppression(source, [(neighbor, 100.0)])
        assert neighbor.value == 0.0

    def test_spread_decreases_with_distance(self) -> None:
        e = _engine()
        source = UnitSuppressionState(value=0.8)
        near = UnitSuppressionState(value=0.0)
        far = UnitSuppressionState(value=0.0)
        e.spread_suppression(source, [(near, 10.0), (far, 40.0)])
        assert near.value > far.value


class TestUnitSuppressionState:
    def test_state_roundtrip(self) -> None:
        state = UnitSuppressionState(value=0.45, source_direction=2.1)
        saved = state.get_state()
        restored = UnitSuppressionState()
        restored.set_state(saved)
        assert restored.value == pytest.approx(0.45)
        assert restored.source_direction == pytest.approx(2.1)
