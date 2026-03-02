"""Tests for combat/air_combat.py — BVR, WVR, guns air-to-air engagements."""

from __future__ import annotations

import numpy as np
import pytest

from stochastic_warfare.combat.air_combat import (
    AirCombatConfig,
    AirCombatEngine,
    AirCombatMode,
    AirCombatResult,
)
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def _engine(seed: int = 42) -> AirCombatEngine:
    return AirCombatEngine(EventBus(), _rng(seed))


def _engine_with_bus(seed: int = 42) -> tuple[AirCombatEngine, EventBus]:
    bus = EventBus()
    return AirCombatEngine(bus, _rng(seed)), bus


# ---------------------------------------------------------------------------
# AirCombatMode enum
# ---------------------------------------------------------------------------


class TestAirCombatMode:
    def test_enum_values(self) -> None:
        assert AirCombatMode.BVR == 0
        assert AirCombatMode.WVR == 1
        assert AirCombatMode.GUNS_ONLY == 2

    def test_enum_names(self) -> None:
        assert AirCombatMode.BVR.name == "BVR"
        assert AirCombatMode.GUNS_ONLY.name == "GUNS_ONLY"


# ---------------------------------------------------------------------------
# BVR engagement
# ---------------------------------------------------------------------------


class TestBVREngagement:
    def test_bvr_returns_correct_mode(self) -> None:
        e = _engine()
        result = e.bvr_engagement("a1", "t1", 40_000.0, 0.7)
        assert result.mode == AirCombatMode.BVR

    def test_bvr_records_ids(self) -> None:
        e = _engine()
        result = e.bvr_engagement("a1", "t1", 40_000.0, 0.7)
        assert result.attacker_id == "a1"
        assert result.target_id == "t1"

    def test_bvr_effective_pk_less_than_base_at_long_range(self) -> None:
        e = _engine()
        result = e.bvr_engagement("a1", "t1", 70_000.0, 0.8)
        assert result.effective_pk < result.missile_pk

    def test_bvr_effective_pk_clamped(self) -> None:
        e = _engine()
        result = e.bvr_engagement("a1", "t1", 40_000.0, 0.7)
        assert 0.01 <= result.effective_pk <= 0.99

    def test_bvr_chaff_reduces_pk(self) -> None:
        e1 = _engine(100)
        e2 = _engine(100)
        no_cm = e1.bvr_engagement("a1", "t1", 40_000.0, 0.7, "none")
        with_cm = e2.bvr_engagement("a1", "t1", 40_000.0, 0.7, "chaff")
        assert with_cm.effective_pk < no_cm.effective_pk

    def test_bvr_flare_minimal_effect_on_radar(self) -> None:
        e1 = _engine(100)
        e2 = _engine(100)
        no_cm = e1.bvr_engagement("a1", "t1", 40_000.0, 0.7, "none")
        flare = e2.bvr_engagement("a1", "t1", 40_000.0, 0.7, "flare")
        # Flare vs radar: only 5% reduction, so effective_pk should be close
        assert flare.effective_pk > no_cm.effective_pk * 0.9

    def test_bvr_closer_range_higher_pk(self) -> None:
        e1 = _engine(100)
        e2 = _engine(100)
        close = e1.bvr_engagement("a1", "t1", 15_000.0, 0.7)
        far = e2.bvr_engagement("a1", "t1", 70_000.0, 0.7)
        assert close.effective_pk > far.effective_pk


# ---------------------------------------------------------------------------
# WVR engagement
# ---------------------------------------------------------------------------


class TestWVREngagement:
    def test_wvr_returns_correct_mode(self) -> None:
        e = _engine()
        result = e.wvr_engagement("a1", "t1", 3000.0, 0.7, 0.0)
        assert result.mode == AirCombatMode.WVR

    def test_wvr_rear_hemisphere_better(self) -> None:
        e1 = _engine(100)
        e2 = _engine(100)
        tail = e1.wvr_engagement("a1", "t1", 3000.0, 0.7, 0.0)
        head = e2.wvr_engagement("a1", "t1", 3000.0, 0.7, 180.0)
        # Tail-on (0 deg) should give higher Pk than head-on (180 deg)
        assert tail.effective_pk > head.effective_pk

    def test_wvr_flare_reduces_pk(self) -> None:
        e1 = _engine(100)
        e2 = _engine(100)
        no_cm = e1.wvr_engagement("a1", "t1", 3000.0, 0.7, 30.0, "none")
        with_cm = e2.wvr_engagement("a1", "t1", 3000.0, 0.7, 30.0, "flare")
        assert with_cm.effective_pk < no_cm.effective_pk

    def test_wvr_chaff_minimal_effect_on_ir(self) -> None:
        e1 = _engine(100)
        e2 = _engine(100)
        no_cm = e1.wvr_engagement("a1", "t1", 3000.0, 0.7, 30.0, "none")
        chaff = e2.wvr_engagement("a1", "t1", 3000.0, 0.7, 30.0, "chaff")
        # Chaff vs IR: only 5% reduction
        assert chaff.effective_pk > no_cm.effective_pk * 0.9

    def test_wvr_closer_range_higher_pk(self) -> None:
        e1 = _engine(100)
        e2 = _engine(100)
        close = e1.wvr_engagement("a1", "t1", 1000.0, 0.7, 30.0)
        far = e2.wvr_engagement("a1", "t1", 9000.0, 0.7, 30.0)
        assert close.effective_pk > far.effective_pk

    def test_wvr_effective_pk_clamped(self) -> None:
        e = _engine()
        result = e.wvr_engagement("a1", "t1", 3000.0, 0.7, 30.0)
        assert 0.01 <= result.effective_pk <= 0.99


# ---------------------------------------------------------------------------
# Guns engagement
# ---------------------------------------------------------------------------


class TestGunsEngagement:
    def test_guns_returns_correct_mode(self) -> None:
        e = _engine()
        result = e.guns_engagement("a1", "t1", 500.0, 0.8, 0.0)
        assert result.mode == AirCombatMode.GUNS_ONLY

    def test_guns_missile_pk_zero(self) -> None:
        e = _engine()
        result = e.guns_engagement("a1", "t1", 500.0, 0.5)
        assert result.missile_pk == 0.0

    def test_guns_higher_skill_higher_pk(self) -> None:
        e1 = _engine(100)
        e2 = _engine(100)
        novice = e1.guns_engagement("a1", "t1", 500.0, 0.1, 0.0)
        ace = e2.guns_engagement("a1", "t1", 500.0, 1.0, 0.0)
        assert ace.effective_pk > novice.effective_pk

    def test_guns_deflection_reduces_pk(self) -> None:
        e1 = _engine(100)
        e2 = _engine(100)
        straight = e1.guns_engagement("a1", "t1", 500.0, 0.5, 0.0)
        crossing = e2.guns_engagement("a1", "t1", 500.0, 0.5, 60.0)
        assert crossing.effective_pk < straight.effective_pk

    def test_guns_closer_range_higher_pk(self) -> None:
        e1 = _engine(100)
        e2 = _engine(100)
        close = e1.guns_engagement("a1", "t1", 200.0, 0.5, 0.0)
        far = e2.guns_engagement("a1", "t1", 900.0, 0.5, 0.0)
        assert close.effective_pk > far.effective_pk

    def test_guns_no_countermeasure_reduction(self) -> None:
        e = _engine()
        result = e.guns_engagement("a1", "t1", 500.0, 0.5)
        assert result.countermeasure_reduction == 0.0


# ---------------------------------------------------------------------------
# Countermeasures
# ---------------------------------------------------------------------------


class TestCountermeasures:
    def test_chaff_vs_radar(self) -> None:
        e = _engine()
        reduction = e.apply_countermeasures("radar", "chaff")
        assert reduction == pytest.approx(0.3)

    def test_flare_vs_ir(self) -> None:
        e = _engine()
        reduction = e.apply_countermeasures("ir", "flare")
        assert reduction == pytest.approx(0.4)

    def test_none_no_effect(self) -> None:
        e = _engine()
        reduction = e.apply_countermeasures("radar", "none")
        assert reduction == 0.0

    def test_mismatched_chaff_vs_ir(self) -> None:
        e = _engine()
        reduction = e.apply_countermeasures("ir", "chaff")
        assert reduction == pytest.approx(0.05)

    def test_mismatched_flare_vs_radar(self) -> None:
        e = _engine()
        reduction = e.apply_countermeasures("radar", "flare")
        assert reduction == pytest.approx(0.05)


# ---------------------------------------------------------------------------
# Auto-mode selection in resolve_air_engagement
# ---------------------------------------------------------------------------


class TestResolveAirEngagement:
    def test_auto_selects_bvr_at_long_range(self) -> None:
        e = _engine()
        result = e.resolve_air_engagement(
            "a1", "t1",
            Position(0, 0, 10000), Position(0, 50000, 10000),
        )
        assert result.mode == AirCombatMode.BVR

    def test_auto_selects_wvr_at_medium_range(self) -> None:
        e = _engine()
        result = e.resolve_air_engagement(
            "a1", "t1",
            Position(0, 0, 5000), Position(0, 5000, 5000),
        )
        assert result.mode == AirCombatMode.WVR

    def test_auto_selects_guns_at_close_range(self) -> None:
        e = _engine()
        result = e.resolve_air_engagement(
            "a1", "t1",
            Position(0, 0, 5000), Position(0, 400, 5000),
        )
        assert result.mode == AirCombatMode.GUNS_ONLY

    def test_forced_mode_override(self) -> None:
        e = _engine()
        result = e.resolve_air_engagement(
            "a1", "t1",
            Position(0, 0, 5000), Position(0, 500, 5000),
            mode=AirCombatMode.WVR,
        )
        assert result.mode == AirCombatMode.WVR

    def test_events_published_with_timestamp(self) -> None:
        from datetime import datetime, timezone
        e, bus = _engine_with_bus(42)
        received: list = []
        from stochastic_warfare.core.events import Event
        bus.subscribe(Event, lambda ev: received.append(ev))

        e.resolve_air_engagement(
            "a1", "t1",
            Position(0, 0, 5000), Position(0, 50000, 5000),
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert len(received) == 1
        assert received[0].engagement_type in ("BVR", "WVR", "GUNS_ONLY")


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_seed_same_result(self) -> None:
        e1 = _engine(42)
        e2 = _engine(42)
        r1 = e1.bvr_engagement("a1", "t1", 40_000.0, 0.7)
        r2 = e2.bvr_engagement("a1", "t1", 40_000.0, 0.7)
        assert r1.effective_pk == pytest.approx(r2.effective_pk)
        assert r1.hit == r2.hit

    def test_different_seed_may_differ(self) -> None:
        results = set()
        for seed in range(50):
            e = _engine(seed)
            r = e.bvr_engagement("a1", "t1", 40_000.0, 0.7)
            results.add(r.hit)
        # With 50 trials, should see both hits and misses
        assert len(results) == 2


# ---------------------------------------------------------------------------
# State roundtrip
# ---------------------------------------------------------------------------


class TestState:
    def test_state_roundtrip(self) -> None:
        e1 = _engine(42)
        e1.bvr_engagement("a1", "t1", 40_000.0, 0.7)
        saved = e1.get_state()

        e2 = _engine(99)
        e2.set_state(saved)

        r1 = e1.bvr_engagement("a2", "t2", 30_000.0, 0.8)
        r2 = e2.bvr_engagement("a2", "t2", 30_000.0, 0.8)
        assert r1.effective_pk == pytest.approx(r2.effective_pk)
        assert r1.hit == r2.hit

    def test_state_preserves_engagement_count(self) -> None:
        e = _engine(42)
        e.resolve_air_engagement(
            "a1", "t1",
            Position(0, 0, 5000), Position(0, 50000, 5000),
        )
        state = e.get_state()
        assert state["engagements_resolved"] == 1
