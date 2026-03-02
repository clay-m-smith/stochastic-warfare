"""Tests for combat/missile_defense.py — BMD layers, C-RAM, discrimination."""

from __future__ import annotations

import numpy as np
import pytest

from stochastic_warfare.combat.missile_defense import (
    BMDResult,
    CRAMResult,
    CruiseMissileDefenseResult,
    DefenseLayer,
    MissileDefenseConfig,
    MissileDefenseEngine,
)
from stochastic_warfare.core.events import EventBus


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def _engine(seed: int = 42) -> MissileDefenseEngine:
    return MissileDefenseEngine(EventBus(), _rng(seed))


def _engine_with_bus(seed: int = 42) -> tuple[MissileDefenseEngine, EventBus]:
    bus = EventBus()
    return MissileDefenseEngine(bus, _rng(seed)), bus


# ---------------------------------------------------------------------------
# DefenseLayer enum
# ---------------------------------------------------------------------------


class TestDefenseLayer:
    def test_enum_values(self) -> None:
        assert DefenseLayer.UPPER_TIER == 0
        assert DefenseLayer.LOWER_TIER == 1
        assert DefenseLayer.POINT_DEFENSE == 2
        assert DefenseLayer.CRAM == 3


# ---------------------------------------------------------------------------
# Ballistic missile defense
# ---------------------------------------------------------------------------


class TestBMD:
    def test_single_layer_intercept_possible(self) -> None:
        hits = 0
        for seed in range(50):
            e = _engine(seed)
            result = e.engage_ballistic_missile([0.7])
            if result.intercepted:
                hits += 1
        assert hits > 0

    def test_multilayer_cumulative_pk(self) -> None:
        e = _engine()
        result = e.engage_ballistic_missile([0.5, 0.5, 0.5])
        # Cumulative Pk = 1 - (1-pk1)(1-pk2)(1-pk3)
        # With speed penalty the effective pks will be < 0.5
        # but cumulative should still be > any single layer
        assert result.cumulative_pk > result.per_layer_pk[0]

    def test_cumulative_pk_formula(self) -> None:
        e = _engine()
        result = e.engage_ballistic_missile([0.4, 0.4], missile_speed_mps=1000.0)
        expected_cumul = 1.0 - (1.0 - result.per_layer_pk[0]) * (1.0 - result.per_layer_pk[1])
        assert result.cumulative_pk == pytest.approx(expected_cumul, abs=0.01)

    def test_high_speed_reduces_pk(self) -> None:
        e1 = _engine(100)
        e2 = _engine(100)
        slow = e1.engage_ballistic_missile([0.7], missile_speed_mps=1000.0)
        fast = e2.engage_ballistic_missile([0.7], missile_speed_mps=4000.0)
        assert fast.per_layer_pk[0] < slow.per_layer_pk[0]

    def test_layers_engaged_count(self) -> None:
        # With very low Pk, all layers should engage
        e = _engine(42)
        result = e.engage_ballistic_missile([0.01, 0.01, 0.01])
        # Most likely all 3 miss, so all 3 layers engaged
        assert result.layers_engaged == 3

    def test_stops_after_hit(self) -> None:
        # With very high Pk, should stop after first layer hit
        for seed in range(100):
            e = _engine(seed)
            result = e.engage_ballistic_missile([0.99, 0.99, 0.99])
            if result.per_layer_hit[0]:
                assert result.layers_engaged == 1
                break
        else:
            pytest.fail("No first-layer hit in 100 seeds with Pk=0.99")

    def test_speed_recorded(self) -> None:
        e = _engine()
        result = e.engage_ballistic_missile([0.5], missile_speed_mps=2500.0)
        assert result.missile_speed_mps == 2500.0

    def test_events_published(self) -> None:
        from datetime import datetime, timezone
        e, bus = _engine_with_bus(42)
        received: list = []
        from stochastic_warfare.core.events import Event
        bus.subscribe(Event, lambda ev: received.append(ev))

        e.engage_ballistic_missile(
            [0.5], defender_id="bmd1", missile_id="bm1",
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert len(received) == 1


# ---------------------------------------------------------------------------
# Cruise missile defense
# ---------------------------------------------------------------------------


class TestCruiseMissileDefense:
    def test_intercept_possible(self) -> None:
        hits = 0
        for seed in range(50):
            e = _engine(seed)
            result = e.engage_cruise_missile(0.7, missile_speed_mps=250.0)
            if result.hit:
                hits += 1
        assert hits > 0

    def test_sea_skimming_reduces_pk(self) -> None:
        e1 = _engine(100)
        e2 = _engine(100)
        normal = e1.engage_cruise_missile(0.7, sea_skimming=False)
        skimming = e2.engage_cruise_missile(0.7, sea_skimming=True)
        assert skimming.effective_pk < normal.effective_pk

    def test_supersonic_harder_to_intercept(self) -> None:
        e1 = _engine(100)
        e2 = _engine(100)
        subsonic = e1.engage_cruise_missile(0.7, missile_speed_mps=250.0)
        supersonic = e2.engage_cruise_missile(0.7, missile_speed_mps=900.0)
        assert supersonic.effective_pk < subsonic.effective_pk

    def test_effective_pk_clamped(self) -> None:
        e = _engine()
        result = e.engage_cruise_missile(0.7, missile_speed_mps=250.0)
        assert 0.01 <= result.effective_pk <= 0.99

    def test_sea_skimming_flag_recorded(self) -> None:
        e = _engine()
        result = e.engage_cruise_missile(0.7, sea_skimming=True)
        assert result.sea_skimming is True

    def test_events_published(self) -> None:
        from datetime import datetime, timezone
        e, bus = _engine_with_bus(42)
        received: list = []
        from stochastic_warfare.core.events import Event
        bus.subscribe(Event, lambda ev: received.append(ev))

        e.engage_cruise_missile(
            0.7, defender_id="ad1", missile_id="cm1",
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert len(received) == 1


# ---------------------------------------------------------------------------
# C-RAM
# ---------------------------------------------------------------------------


class TestCRAM:
    def test_intercept_possible(self) -> None:
        hits = 0
        for seed in range(50):
            e = _engine(seed)
            result = e.engage_cram("cram1", 107.0, 1000.0)
            if result.intercepted:
                hits += 1
        assert hits > 0

    def test_out_of_range_fails(self) -> None:
        e = _engine()
        result = e.engage_cram("cram1", 107.0, 5000.0)
        assert result.intercepted is False
        assert result.effective_pk == 0.0

    def test_closer_range_higher_pk(self) -> None:
        e1 = _engine(100)
        e2 = _engine(100)
        close = e1.engage_cram("cram1", 107.0, 500.0)
        far = e2.engage_cram("cram1", 107.0, 1800.0)
        assert close.effective_pk > far.effective_pk

    def test_records_caliber(self) -> None:
        e = _engine()
        result = e.engage_cram("cram1", 122.0, 1000.0)
        assert result.incoming_caliber_mm == 122.0

    def test_records_defender_id(self) -> None:
        e = _engine()
        result = e.engage_cram("cram_alpha", 107.0, 1000.0)
        assert result.defender_id == "cram_alpha"

    def test_effective_pk_clamped(self) -> None:
        e = _engine()
        result = e.engage_cram("cram1", 107.0, 1000.0)
        assert 0.01 <= result.effective_pk <= 0.99

    def test_events_published(self) -> None:
        from datetime import datetime, timezone
        e, bus = _engine_with_bus(42)
        received: list = []
        from stochastic_warfare.core.events import Event
        bus.subscribe(Event, lambda ev: received.append(ev))

        e.engage_cram(
            "cram1", 107.0, 1000.0,
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert len(received) == 1


# ---------------------------------------------------------------------------
# Discrimination
# ---------------------------------------------------------------------------


class TestDiscrimination:
    def test_no_decoys_high_discrimination(self) -> None:
        e = _engine()
        prob = e.compute_discrimination(sensor_quality=0.8, decoy_count=0)
        assert prob > 0.7

    def test_decoys_degrade_discrimination(self) -> None:
        e = _engine()
        no_decoys = e.compute_discrimination(sensor_quality=0.5, decoy_count=0)
        many_decoys = e.compute_discrimination(sensor_quality=0.5, decoy_count=10)
        assert many_decoys < no_decoys

    def test_better_sensors_improve_discrimination(self) -> None:
        e = _engine()
        poor = e.compute_discrimination(sensor_quality=0.1, decoy_count=3)
        good = e.compute_discrimination(sensor_quality=0.9, decoy_count=3)
        assert good > poor

    def test_discrimination_clamped(self) -> None:
        e = _engine()
        # Extreme case: bad sensors, many decoys
        prob = e.compute_discrimination(sensor_quality=0.0, decoy_count=100)
        assert prob >= 0.05
        # Best case
        prob = e.compute_discrimination(sensor_quality=1.0, decoy_count=0)
        assert prob <= 1.0


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_seed_same_bmd(self) -> None:
        e1 = _engine(42)
        e2 = _engine(42)
        r1 = e1.engage_ballistic_missile([0.5, 0.5])
        r2 = e2.engage_ballistic_missile([0.5, 0.5])
        assert r1.intercepted == r2.intercepted
        assert len(r1.per_layer_hit) == len(r2.per_layer_hit)
        for a, b in zip(r1.per_layer_hit, r2.per_layer_hit):
            assert a == b

    def test_same_seed_same_cruise(self) -> None:
        e1 = _engine(42)
        e2 = _engine(42)
        r1 = e1.engage_cruise_missile(0.6)
        r2 = e2.engage_cruise_missile(0.6)
        assert r1.effective_pk == pytest.approx(r2.effective_pk)
        assert r1.hit == r2.hit


# ---------------------------------------------------------------------------
# State roundtrip
# ---------------------------------------------------------------------------


class TestState:
    def test_state_roundtrip(self) -> None:
        e1 = _engine(42)
        e1.engage_ballistic_missile([0.5])
        saved = e1.get_state()

        e2 = _engine(99)
        e2.set_state(saved)

        r1 = e1.engage_cruise_missile(0.6)
        r2 = e2.engage_cruise_missile(0.6)
        assert r1.effective_pk == pytest.approx(r2.effective_pk)
        assert r1.hit == r2.hit

    def test_state_preserves_intercept_count(self) -> None:
        e = _engine(42)
        e.engage_ballistic_missile([0.5, 0.5])
        state = e.get_state()
        assert state["intercepts_attempted"] >= 1
