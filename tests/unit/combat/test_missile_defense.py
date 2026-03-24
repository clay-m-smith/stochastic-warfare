"""Unit tests for MissileDefenseEngine — BMD, cruise defense, C-RAM, discrimination."""

from __future__ import annotations

import pytest

from stochastic_warfare.combat.missile_defense import (
    BMDResult,
    CRAMResult,
    MissileDefenseConfig,
    MissileDefenseEngine,
)
from stochastic_warfare.core.events import EventBus

from .conftest import _rng


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_engine(seed: int = 42, **cfg_kwargs) -> MissileDefenseEngine:
    bus = EventBus()
    config = MissileDefenseConfig(**cfg_kwargs) if cfg_kwargs else None
    return MissileDefenseEngine(bus, _rng(seed), config)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBMD:
    """Layered ballistic missile defense."""

    def test_bmd_cumulative_pk(self):
        """Cumulative Pk should follow 1 - product(1 - Pk_i)."""
        eng = _make_engine(seed=1)
        result = eng.engage_ballistic_missile(
            defender_pks=[0.5, 0.5, 0.5],
            missile_speed_mps=2000.0,
        )
        assert isinstance(result, BMDResult)
        assert result.layers_engaged >= 1
        # Cumulative Pk should be > any single layer
        assert result.cumulative_pk > 0.5

    def test_bmd_single_layer(self):
        eng = _make_engine(seed=2)
        result = eng.engage_ballistic_missile(
            defender_pks=[0.7],
            missile_speed_mps=2000.0,
        )
        assert result.layers_engaged == 1
        assert len(result.per_layer_pk) == 1
        assert len(result.per_layer_hit) == 1

    def test_bmd_stops_on_intercept(self):
        """Should stop firing layers after a hit."""
        # Use very high Pk to ensure hit on first layer
        eng = _make_engine(seed=10)
        result = eng.engage_ballistic_missile(
            defender_pks=[0.99, 0.99, 0.99],
            missile_speed_mps=2000.0,
        )
        if result.per_layer_hit[0]:
            assert result.layers_engaged == 1

    def test_bmd_upper_tier_speed_penalty(self):
        """Missiles above upper tier threshold should have lower effective Pk."""
        eng1 = _make_engine(seed=20)
        eng2 = _make_engine(seed=20)
        slow = eng1.engage_ballistic_missile(
            defender_pks=[0.7], missile_speed_mps=1000.0,
        )
        fast = eng2.engage_ballistic_missile(
            defender_pks=[0.7], missile_speed_mps=4000.0,
        )
        assert fast.per_layer_pk[0] < slow.per_layer_pk[0]

    def test_bmd_lower_tier_speed_penalty(self):
        """Missiles between thresholds get moderate penalty."""
        eng = _make_engine(seed=21)
        result = eng.engage_ballistic_missile(
            defender_pks=[0.7], missile_speed_mps=2000.0,
        )
        # Speed is between lower (1500) and upper (3000) thresholds
        # Penalty should be 0.9
        assert result.per_layer_pk[0] == pytest.approx(0.7 * 0.9)


class TestCruiseMissileDefense:
    """Cruise missile intercept."""

    def test_cruise_sea_skimming_penalty(self):
        """Sea-skimming should reduce Pk."""
        eng1 = _make_engine(seed=30)
        eng2 = _make_engine(seed=30)
        normal = eng1.engage_cruise_missile(0.7, 250.0, sea_skimming=False)
        skimming = eng2.engage_cruise_missile(0.7, 250.0, sea_skimming=True)
        assert skimming.effective_pk < normal.effective_pk
        assert skimming.sea_skimming is True

    def test_supersonic_difficulty(self):
        """Supersonic cruise missiles should be harder to intercept."""
        eng1 = _make_engine(seed=40)
        eng2 = _make_engine(seed=40)
        subsonic = eng1.engage_cruise_missile(0.7, 250.0)
        supersonic = eng2.engage_cruise_missile(0.7, 700.0)
        assert supersonic.effective_pk < subsonic.effective_pk

    def test_cruise_returns_correct_speed(self):
        eng = _make_engine(seed=41)
        result = eng.engage_cruise_missile(0.6, 300.0)
        assert result.missile_speed_mps == pytest.approx(300.0)


class TestCRAM:
    """Counter-rocket, artillery, mortar defense."""

    def test_cram_within_range(self):
        eng = _make_engine(seed=50)
        result = eng.engage_cram("cram1", incoming_caliber_mm=107.0, range_m=1000.0)
        assert isinstance(result, CRAMResult)
        assert result.effective_pk > 0.0
        assert result.defender_id == "cram1"

    def test_cram_beyond_max_range(self):
        eng = _make_engine(seed=51)
        result = eng.engage_cram("cram1", incoming_caliber_mm=107.0, range_m=3000.0)
        # Default max range is 2000m
        assert result.intercepted is False
        assert result.effective_pk == 0.0

    def test_cram_caliber_factor(self):
        """Larger caliber should slightly reduce Pk (more robust projectile)."""
        eng1 = _make_engine(seed=60)
        eng2 = _make_engine(seed=60)
        small = eng1.engage_cram("cram1", incoming_caliber_mm=81.0, range_m=1000.0)
        large = eng2.engage_cram("cram1", incoming_caliber_mm=155.0, range_m=1000.0)
        # 155mm > 80mm threshold, so caliber_factor kicks in
        assert large.effective_pk <= small.effective_pk

    def test_cram_close_range_bonus(self):
        """Closer range should yield higher Pk."""
        eng1 = _make_engine(seed=70)
        eng2 = _make_engine(seed=70)
        close = eng1.engage_cram("cram1", incoming_caliber_mm=107.0, range_m=200.0)
        far = eng2.engage_cram("cram1", incoming_caliber_mm=107.0, range_m=1800.0)
        assert close.effective_pk > far.effective_pk


class TestDiscrimination:
    """Warhead discrimination against decoys."""

    def test_base_discrimination(self):
        eng = _make_engine(seed=80)
        prob = eng.compute_discrimination(sensor_quality=0.5, decoy_count=0)
        assert 0.0 < prob <= 1.0

    def test_decoys_degrade_discrimination(self):
        eng = _make_engine(seed=81)
        no_decoys = eng.compute_discrimination(sensor_quality=0.5, decoy_count=0)
        many_decoys = eng.compute_discrimination(sensor_quality=0.5, decoy_count=10)
        assert many_decoys < no_decoys

    def test_better_sensors_improve_discrimination(self):
        eng = _make_engine(seed=82)
        poor = eng.compute_discrimination(sensor_quality=0.1, decoy_count=2)
        good = eng.compute_discrimination(sensor_quality=0.9, decoy_count=2)
        assert good > poor

    def test_discrimination_floor(self):
        """Discrimination should not go below 0.05."""
        eng = _make_engine(seed=83)
        prob = eng.compute_discrimination(sensor_quality=0.0, decoy_count=100)
        assert prob >= 0.05


class TestStateRoundtrip:
    """State serialization and restoration."""

    def test_state_roundtrip(self):
        eng = _make_engine(seed=90)
        eng.engage_ballistic_missile([0.5, 0.5], missile_speed_mps=2000.0)
        eng.engage_cram("cram1", range_m=1000.0)
        state = eng.get_state()

        eng2 = _make_engine(seed=999)
        eng2.set_state(state)

        assert eng2._intercepts_attempted == eng._intercepts_attempted

        r1 = eng._rng.random()
        r2 = eng2._rng.random()
        assert r1 == pytest.approx(r2)
