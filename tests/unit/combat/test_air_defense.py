"""Unit tests for AirDefenseEngine — threat evaluation, engagement envelopes, SLS."""

from __future__ import annotations

import pytest

from stochastic_warfare.combat.air_defense import (
    AirDefenseConfig,
    AirDefenseEngine,
)
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position

from .conftest import _rng


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_engine(seed: int = 42, **cfg_kwargs) -> AirDefenseEngine:
    bus = EventBus()
    config = AirDefenseConfig(**cfg_kwargs) if cfg_kwargs else None
    return AirDefenseEngine(bus, _rng(seed), config)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestThreatEvaluation:
    """evaluate_threat priority and scoring."""

    def test_missile_highest_priority(self):
        eng = _make_engine(seed=1)
        threat = eng.evaluate_threat("missile", 600.0, 5000.0)
        assert threat.threat_score > 0.6
        assert threat.priority == 1

    def test_transport_lowest_priority(self):
        eng = _make_engine(seed=2)
        threat = eng.evaluate_threat("transport", 100.0, 10000.0)
        assert threat.priority >= 3

    def test_speed_factor_normalized_to_mach(self):
        eng = _make_engine(seed=3)
        slow = eng.evaluate_threat("fighter", 100.0, 5000.0)
        fast = eng.evaluate_threat("fighter", 330.0, 5000.0)
        assert fast.speed_factor > slow.speed_factor

    def test_low_altitude_more_threatening(self):
        eng = _make_engine(seed=4)
        low = eng.evaluate_threat("fighter", 250.0, 500.0)
        high = eng.evaluate_threat("fighter", 250.0, 15000.0)
        assert low.altitude_factor > high.altitude_factor

    def test_attacking_boost(self):
        eng = _make_engine(seed=5)
        passive = eng.evaluate_threat("fighter", 250.0, 5000.0, is_attacking=False)
        attacking = eng.evaluate_threat("fighter", 250.0, 5000.0, is_attacking=True)
        assert attacking.threat_score > passive.threat_score
        assert attacking.is_attacking is True


class TestEngagementEnvelope:
    """can_engage_target 3-D envelope checks."""

    def test_within_envelope(self):
        eng = _make_engine(seed=10)
        ad_pos = Position(0, 0, 0)
        target_pos = Position(30_000, 0, 5000)
        assert eng.can_engage_target(ad_pos, target_pos, target_altitude_m=5000.0)

    def test_below_min_altitude(self):
        eng = _make_engine(seed=11)
        ad_pos = Position(0, 0, 0)
        target_pos = Position(10_000, 0, 10)
        # Default min altitude is 30m
        assert not eng.can_engage_target(ad_pos, target_pos, target_altitude_m=10.0)

    def test_above_max_altitude(self):
        eng = _make_engine(seed=12)
        ad_pos = Position(0, 0, 0)
        target_pos = Position(10_000, 0, 30_000)
        # Default max altitude is 24,000m
        assert not eng.can_engage_target(ad_pos, target_pos, target_altitude_m=30_000.0)

    def test_beyond_max_range(self):
        eng = _make_engine(seed=13)
        ad_pos = Position(0, 0, 0)
        # Default max range is 80,000m; target at 100km
        target_pos = Position(100_000, 0, 5000)
        assert not eng.can_engage_target(ad_pos, target_pos, target_altitude_m=5000.0)

    def test_custom_envelope(self):
        eng = _make_engine(seed=14)
        ad_pos = Position(0, 0, 0)
        target_pos = Position(5000, 0, 200)
        assert eng.can_engage_target(
            ad_pos, target_pos, target_altitude_m=200.0,
            min_alt_m=100.0, max_alt_m=500.0, max_range_m=10_000.0,
        )


class TestFireInterceptor:
    """fire_interceptor Pk computation."""

    def test_rcs_scaling_small_target(self):
        """Small RCS target (stealth) should have lower effective Pk."""
        eng1 = _make_engine(seed=20)
        eng2 = _make_engine(seed=20)
        normal = eng1.fire_interceptor("ad1", "t1", 0.7, 30_000.0, target_rcs_m2=3.0)
        stealth = eng2.fire_interceptor("ad1", "t1", 0.7, 30_000.0, target_rcs_m2=0.1)
        assert stealth.effective_pk < normal.effective_pk

    def test_rcs_scaling_large_target(self):
        """Large RCS target should have higher effective Pk."""
        eng1 = _make_engine(seed=25)
        eng2 = _make_engine(seed=25)
        normal = eng1.fire_interceptor("ad1", "t1", 0.7, 30_000.0, target_rcs_m2=3.0)
        big = eng2.fire_interceptor("ad1", "t1", 0.7, 30_000.0, target_rcs_m2=20.0)
        assert big.effective_pk > normal.effective_pk

    def test_interceptor_returns_correct_ids(self):
        eng = _make_engine(seed=30)
        result = eng.fire_interceptor("sam1", "tgt1", 0.6, 25_000.0)
        assert result.ad_id == "sam1"
        assert result.target_id == "tgt1"
        assert result.interceptor_pk == 0.6


class TestShootLookShoot:
    """shoot_look_shoot doctrine limits salvos."""

    def test_sls_stops_on_hit(self):
        """SLS should stop firing after a hit."""
        # Use a high Pk and seed that produces a hit on first shot
        eng = _make_engine(seed=100)
        results = eng.shoot_look_shoot("ad1", "t1", 0.95, max_shots=3, range_m=10_000.0)
        # Should have at most max_shots results
        assert len(results) <= 3
        # If any hit, it should be the last result
        hits = [r for r in results if r.hit]
        if hits:
            assert results[-1].hit is True

    def test_sls_respects_max_shots(self):
        """SLS should not exceed max_shots even if all miss."""
        eng = _make_engine(seed=200)
        results = eng.shoot_look_shoot(
            "ad1", "t1", 0.01, max_shots=2, range_m=60_000.0,
        )
        assert len(results) <= 2

    def test_sls_capped_by_config(self):
        """max_sls_shots in config caps the number of shots."""
        eng = _make_engine(seed=300, max_sls_shots=2)
        results = eng.shoot_look_shoot(
            "ad1", "t1", 0.01, max_shots=5, range_m=30_000.0,
        )
        assert len(results) <= 2


class TestStateRoundtrip:
    """State serialization and restoration."""

    def test_state_roundtrip(self):
        eng = _make_engine(seed=400)
        eng.fire_interceptor("ad1", "t1", 0.7, 30_000.0)
        eng.fire_interceptor("ad1", "t2", 0.5, 40_000.0)
        state = eng.get_state()

        eng2 = _make_engine(seed=999)
        eng2.set_state(state)

        assert eng2._interceptors_fired == 2

        r1 = eng._rng.random()
        r2 = eng2._rng.random()
        assert r1 == pytest.approx(r2)
