"""Tests for combat/air_defense.py — SAM envelopes, shoot-look-shoot, threat eval."""

from __future__ import annotations

import numpy as np
import pytest

from stochastic_warfare.combat.air_defense import (
    AirDefenseConfig,
    AirDefenseEngine,
    EngagementDoctrine,
    InterceptResult,
    ThreatAssessment,
)
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def _engine(seed: int = 42) -> AirDefenseEngine:
    return AirDefenseEngine(EventBus(), _rng(seed))


def _engine_with_bus(seed: int = 42) -> tuple[AirDefenseEngine, EventBus]:
    bus = EventBus()
    return AirDefenseEngine(bus, _rng(seed)), bus


# ---------------------------------------------------------------------------
# EngagementDoctrine enum
# ---------------------------------------------------------------------------


class TestEngagementDoctrine:
    def test_enum_values(self) -> None:
        assert EngagementDoctrine.SHOOT_SHOOT == 0
        assert EngagementDoctrine.SHOOT_LOOK_SHOOT == 1
        assert EngagementDoctrine.HOLD_FIRE == 2


# ---------------------------------------------------------------------------
# Threat assessment
# ---------------------------------------------------------------------------


class TestThreatAssessment:
    def test_missile_highest_priority(self) -> None:
        e = _engine()
        missile = e.evaluate_threat("missile", 800.0, 5000.0)
        fighter = e.evaluate_threat("fighter", 300.0, 5000.0)
        assert missile.threat_score > fighter.threat_score

    def test_fighter_higher_than_transport(self) -> None:
        e = _engine()
        fighter = e.evaluate_threat("fighter", 250.0, 5000.0)
        transport = e.evaluate_threat("transport", 250.0, 5000.0)
        assert fighter.threat_score > transport.threat_score

    def test_attacking_increases_threat(self) -> None:
        e = _engine()
        passive = e.evaluate_threat("fighter", 250.0, 5000.0, is_attacking=False)
        attacking = e.evaluate_threat("fighter", 250.0, 5000.0, is_attacking=True)
        assert attacking.threat_score > passive.threat_score

    def test_faster_target_higher_threat(self) -> None:
        e = _engine()
        slow = e.evaluate_threat("fighter", 100.0, 5000.0)
        fast = e.evaluate_threat("fighter", 600.0, 5000.0)
        assert fast.threat_score > slow.threat_score

    def test_lower_altitude_higher_threat(self) -> None:
        e = _engine()
        high = e.evaluate_threat("fighter", 250.0, 15000.0)
        low = e.evaluate_threat("fighter", 250.0, 500.0)
        assert low.threat_score > high.threat_score

    def test_priority_numeric_ordering(self) -> None:
        e = _engine()
        missile = e.evaluate_threat("missile", 800.0, 2000.0, is_attacking=True)
        transport = e.evaluate_threat("transport", 100.0, 15000.0)
        assert missile.priority < transport.priority  # lower = more urgent

    def test_score_components_recorded(self) -> None:
        e = _engine()
        result = e.evaluate_threat("fighter", 250.0, 5000.0)
        assert result.type_factor > 0
        assert result.speed_factor >= 0
        assert result.altitude_factor >= 0


# ---------------------------------------------------------------------------
# Engagement envelope
# ---------------------------------------------------------------------------


class TestCanEngageTarget:
    def test_target_in_envelope(self) -> None:
        e = _engine()
        assert e.can_engage_target(
            Position(0, 0, 0), Position(0, 30000, 10000),
            target_altitude_m=10000.0,
        ) is True

    def test_target_below_min_altitude(self) -> None:
        e = _engine()
        assert e.can_engage_target(
            Position(0, 0, 0), Position(0, 5000, 10),
            target_altitude_m=10.0,
        ) is False

    def test_target_above_max_altitude(self) -> None:
        e = _engine()
        assert e.can_engage_target(
            Position(0, 0, 0), Position(0, 5000, 30000),
            target_altitude_m=30000.0,
        ) is False

    def test_target_beyond_max_range(self) -> None:
        e = _engine()
        assert e.can_engage_target(
            Position(0, 0, 0), Position(0, 100000, 5000),
            target_altitude_m=5000.0,
        ) is False

    def test_custom_envelope_parameters(self) -> None:
        e = _engine()
        assert e.can_engage_target(
            Position(0, 0, 0), Position(0, 5000, 1000),
            target_altitude_m=1000.0,
            min_alt_m=500.0, max_alt_m=2000.0, max_range_m=10000.0,
        ) is True

    def test_uses_target_pos_altitude_if_not_specified(self) -> None:
        e = _engine()
        # target_pos altitude = 5000, within default envelope
        assert e.can_engage_target(
            Position(0, 0, 0), Position(0, 30000, 5000),
        ) is True

    def test_target_just_at_max_range(self) -> None:
        e = _engine()
        cfg = AirDefenseConfig()
        # Place target such that slant range is just within max_range
        # Ground range 70000, altitude 5000 → slant ≈ 70178 < 80000
        assert e.can_engage_target(
            Position(0, 0, 0),
            Position(0, 70000.0, 0.0),
            target_altitude_m=5000.0,
        ) is True


# ---------------------------------------------------------------------------
# Single interceptor fire
# ---------------------------------------------------------------------------


class TestFireInterceptor:
    def test_returns_intercept_result(self) -> None:
        e = _engine()
        result = e.fire_interceptor("ad1", "tgt1", 0.7, 30000.0)
        assert isinstance(result, InterceptResult)
        assert result.ad_id == "ad1"
        assert result.target_id == "tgt1"

    def test_effective_pk_clamped(self) -> None:
        e = _engine()
        result = e.fire_interceptor("ad1", "tgt1", 0.7, 30000.0)
        assert 0.01 <= result.effective_pk <= 0.99

    def test_larger_rcs_higher_pk(self) -> None:
        e1 = _engine(100)
        e2 = _engine(100)
        small = e1.fire_interceptor("ad1", "tgt1", 0.7, 30000.0, target_rcs_m2=0.5)
        large = e2.fire_interceptor("ad1", "tgt1", 0.7, 30000.0, target_rcs_m2=10.0)
        assert large.effective_pk > small.effective_pk

    def test_chaff_reduces_pk(self) -> None:
        e1 = _engine(100)
        e2 = _engine(100)
        no_cm = e1.fire_interceptor("ad1", "tgt1", 0.7, 30000.0, countermeasures="none")
        chaff = e2.fire_interceptor("ad1", "tgt1", 0.7, 30000.0, countermeasures="chaff")
        assert chaff.effective_pk < no_cm.effective_pk

    def test_ecm_reduces_pk(self) -> None:
        e1 = _engine(100)
        e2 = _engine(100)
        no_cm = e1.fire_interceptor("ad1", "tgt1", 0.7, 30000.0, countermeasures="none")
        ecm = e2.fire_interceptor("ad1", "tgt1", 0.7, 30000.0, countermeasures="ecm")
        assert ecm.effective_pk < no_cm.effective_pk

    def test_closer_range_higher_pk(self) -> None:
        e1 = _engine(100)
        e2 = _engine(100)
        close = e1.fire_interceptor("ad1", "tgt1", 0.7, 10000.0)
        far = e2.fire_interceptor("ad1", "tgt1", 0.7, 70000.0)
        assert close.effective_pk > far.effective_pk

    def test_events_published(self) -> None:
        from datetime import datetime, timezone
        e, bus = _engine_with_bus(42)
        received: list = []
        from stochastic_warfare.core.events import Event
        bus.subscribe(Event, lambda ev: received.append(ev))

        e.fire_interceptor(
            "ad1", "tgt1", 0.7, 30000.0,
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert len(received) == 1

    def test_hit_possible(self) -> None:
        hits = 0
        for seed in range(50):
            e = _engine(seed)
            result = e.fire_interceptor("ad1", "tgt1", 0.7, 20000.0)
            if result.hit:
                hits += 1
        assert hits > 0


# ---------------------------------------------------------------------------
# Shoot-look-shoot
# ---------------------------------------------------------------------------


class TestShootLookShoot:
    def test_stops_on_hit(self) -> None:
        # Find a seed where first shot hits
        for seed in range(100):
            e = _engine(seed)
            results = e.shoot_look_shoot(
                "ad1", "tgt1", 0.9, max_shots=3, range_m=10000.0,
            )
            if results[0].hit:
                assert len(results) == 1
                break
        else:
            pytest.fail("No first-shot hit in 100 seeds at Pk=0.9")

    def test_fires_multiple_on_miss(self) -> None:
        # Find a seed where first shot misses
        for seed in range(100):
            e = _engine(seed)
            results = e.shoot_look_shoot(
                "ad1", "tgt1", 0.3, max_shots=3, range_m=30000.0,
            )
            if not results[0].hit and len(results) > 1:
                assert len(results) >= 2
                break
        else:
            pytest.fail("No multi-shot sequence found in 100 seeds")

    def test_max_shots_capped_by_config(self) -> None:
        cfg = AirDefenseConfig(max_sls_shots=2)
        e = AirDefenseEngine(EventBus(), _rng(42), cfg)
        results = e.shoot_look_shoot(
            "ad1", "tgt1", 0.01, max_shots=10,  # requesting 10 but capped to 2
            range_m=30000.0,
        )
        assert len(results) <= 2

    def test_shot_numbers_sequential(self) -> None:
        e = _engine(42)
        results = e.shoot_look_shoot(
            "ad1", "tgt1", 0.01, max_shots=3, range_m=30000.0,
        )
        for i, r in enumerate(results):
            assert r.shot_number == i + 1

    def test_all_miss_returns_max_shots(self) -> None:
        # Very low Pk should result in all misses
        all_max = False
        for seed in range(50):
            e = _engine(seed)
            results = e.shoot_look_shoot(
                "ad1", "tgt1", 0.01, max_shots=3, range_m=70000.0,
            )
            if len(results) == 3 and not any(r.hit for r in results):
                all_max = True
                break
        assert all_max


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_seed_same_result(self) -> None:
        e1 = _engine(42)
        e2 = _engine(42)
        r1 = e1.fire_interceptor("ad1", "tgt1", 0.7, 30000.0)
        r2 = e2.fire_interceptor("ad1", "tgt1", 0.7, 30000.0)
        assert r1.effective_pk == pytest.approx(r2.effective_pk)
        assert r1.hit == r2.hit

    def test_sls_deterministic(self) -> None:
        e1 = _engine(42)
        e2 = _engine(42)
        r1 = e1.shoot_look_shoot("ad1", "tgt1", 0.5, 3, 30000.0)
        r2 = e2.shoot_look_shoot("ad1", "tgt1", 0.5, 3, 30000.0)
        assert len(r1) == len(r2)
        for a, b in zip(r1, r2):
            assert a.hit == b.hit


# ---------------------------------------------------------------------------
# State roundtrip
# ---------------------------------------------------------------------------


class TestState:
    def test_state_roundtrip(self) -> None:
        e1 = _engine(42)
        e1.fire_interceptor("ad1", "tgt1", 0.7, 30000.0)
        saved = e1.get_state()

        e2 = _engine(99)
        e2.set_state(saved)

        r1 = e1.fire_interceptor("ad1", "tgt2", 0.6, 20000.0)
        r2 = e2.fire_interceptor("ad1", "tgt2", 0.6, 20000.0)
        assert r1.effective_pk == pytest.approx(r2.effective_pk)
        assert r1.hit == r2.hit

    def test_state_preserves_interceptor_count(self) -> None:
        e = _engine(42)
        e.fire_interceptor("ad1", "tgt1", 0.7, 30000.0)
        state = e.get_state()
        assert state["interceptors_fired"] == 1
