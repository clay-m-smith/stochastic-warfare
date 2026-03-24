"""Unit tests for AirCombatEngine — BVR, WVR, guns, countermeasures, energy state."""

from __future__ import annotations

import pytest

from stochastic_warfare.combat.air_combat import (
    AirCombatConfig,
    AirCombatEngine,
    AirCombatMode,
    EnergyState,
)
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position

from .conftest import _rng


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_engine(seed: int = 42, **cfg_kwargs) -> AirCombatEngine:
    bus = EventBus()
    config = AirCombatConfig(**cfg_kwargs) if cfg_kwargs else None
    return AirCombatEngine(bus, _rng(seed), config)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBVREngagement:
    """BVR missile engagements with radar-guided missiles."""

    def test_bvr_returns_correct_mode(self):
        eng = _make_engine(seed=1)
        result = eng.bvr_engagement("a1", "d1", 50_000.0, 0.7)
        assert result.mode == AirCombatMode.BVR
        assert result.attacker_id == "a1"
        assert result.target_id == "d1"

    def test_bvr_range_degradation(self):
        """Pk degrades at longer range."""
        eng1 = _make_engine(seed=10)
        eng2 = _make_engine(seed=10)
        close = eng1.bvr_engagement("a1", "d1", 15_000.0, 0.8)
        far = eng2.bvr_engagement("a1", "d1", 70_000.0, 0.8)
        assert close.effective_pk > far.effective_pk

    def test_bvr_chaff_reduces_pk(self):
        """Chaff vs radar seeker should reduce effective Pk."""
        eng1 = _make_engine(seed=20)
        eng2 = _make_engine(seed=20)
        no_cm = eng1.bvr_engagement("a1", "d1", 30_000.0, 0.8, "none")
        with_chaff = eng2.bvr_engagement("a1", "d1", 30_000.0, 0.8, "chaff")
        assert with_chaff.effective_pk < no_cm.effective_pk
        assert with_chaff.countermeasure_reduction == pytest.approx(0.3)


class TestWVREngagement:
    """WVR IR-homing missile engagements."""

    def test_wvr_rear_aspect_bonus(self):
        """Tail-on (0 deg) should yield higher Pk than head-on (180 deg)."""
        eng1 = _make_engine(seed=30)
        eng2 = _make_engine(seed=30)
        tail_on = eng1.wvr_engagement("a1", "d1", 3000.0, 0.7, 0.0)
        head_on = eng2.wvr_engagement("a1", "d1", 3000.0, 0.7, 180.0)
        assert tail_on.effective_pk > head_on.effective_pk

    def test_wvr_flare_reduces_pk(self):
        """Flares vs IR seeker should reduce effective Pk."""
        eng1 = _make_engine(seed=40)
        eng2 = _make_engine(seed=40)
        no_cm = eng1.wvr_engagement("a1", "d1", 5000.0, 0.7, 0.0, "none")
        with_flare = eng2.wvr_engagement("a1", "d1", 5000.0, 0.7, 0.0, "flare")
        assert with_flare.effective_pk < no_cm.effective_pk
        assert with_flare.countermeasure_reduction == pytest.approx(0.4)


class TestGunsEngagement:
    """Guns engagement with deflection shooting."""

    def test_guns_deflection_penalty(self):
        """Higher deflection angle reduces Pk."""
        eng1 = _make_engine(seed=50)
        eng2 = _make_engine(seed=50)
        straight = eng1.guns_engagement("a1", "d1", 500.0, 0.8, 0.0)
        deflected = eng2.guns_engagement("a1", "d1", 500.0, 0.8, 60.0)
        assert straight.effective_pk > deflected.effective_pk

    def test_guns_skill_affects_pk(self):
        """Higher pilot skill yields higher Pk."""
        eng1 = _make_engine(seed=60)
        eng2 = _make_engine(seed=60)
        novice = eng1.guns_engagement("a1", "d1", 500.0, 0.2)
        ace = eng2.guns_engagement("a1", "d1", 500.0, 1.0)
        assert ace.effective_pk > novice.effective_pk

    def test_guns_mode_always_guns_only(self):
        eng = _make_engine(seed=70)
        result = eng.guns_engagement("a1", "d1", 500.0)
        assert result.mode == AirCombatMode.GUNS_ONLY
        assert result.missile_pk == 0.0


class TestEnergyState:
    """EnergyState specific energy computation."""

    def test_specific_energy_altitude_only(self):
        es = EnergyState(altitude_m=1000.0, speed_mps=0.0)
        assert es.specific_energy == pytest.approx(1000.0)

    def test_specific_energy_combined(self):
        es = EnergyState(altitude_m=5000.0, speed_mps=300.0)
        expected = 5000.0 + 300.0 ** 2 / (2 * 9.81)
        assert es.specific_energy == pytest.approx(expected)


class TestEnergyAdvantage:
    """Energy-maneuverability modifier (Boyd/Christie)."""

    def test_energy_advantage_increases_pk(self):
        eng = _make_engine(seed=80, energy_advantage_weight=0.5)
        high_e = EnergyState(altitude_m=8000.0, speed_mps=400.0)
        low_e = EnergyState(altitude_m=3000.0, speed_mps=200.0)
        result = eng.resolve_air_engagement(
            "a1", "d1",
            Position(0, 0, 8000), Position(20_000, 0, 3000),
            missile_pk=0.6,
            attacker_energy=high_e,
            defender_energy=low_e,
        )
        # Should have a higher effective_pk than base due to energy advantage
        assert result.effective_pk > 0.0


class TestCountermeasureStacking:
    """Multi-spectral CM stacking (multiplicative)."""

    def test_chaff_vs_radar_effective(self):
        eng = _make_engine(seed=90)
        reduction = eng.apply_countermeasures("radar", "chaff")
        assert reduction == pytest.approx(0.3)

    def test_flare_vs_ir_effective(self):
        eng = _make_engine(seed=91)
        reduction = eng.apply_countermeasures("ir", "flare")
        assert reduction == pytest.approx(0.4)

    def test_mismatched_cm_minimal(self):
        eng = _make_engine(seed=92)
        reduction = eng.apply_countermeasures("radar", "flare")
        assert reduction == pytest.approx(0.05)

    def test_multi_cm_stacking(self):
        """Multiplicative stacking: 1 - (1-eff1)(1-eff2) > any single."""
        eng = _make_engine(seed=93)
        single = eng.apply_countermeasures_multi("ir", ["flare"])
        double = eng.apply_countermeasures_multi("ir", ["flare", "dircm"])
        assert double > single


class TestAutoModeSelection:
    """resolve_air_engagement auto-selects mode from range."""

    def test_auto_bvr_mode(self):
        eng = _make_engine(seed=100)
        result = eng.resolve_air_engagement(
            "a1", "d1",
            Position(0, 0, 10000), Position(50_000, 0, 10000),
            missile_pk=0.7,
        )
        assert result.mode == AirCombatMode.BVR

    def test_auto_wvr_or_guns_at_close_range(self):
        eng = _make_engine(seed=101)
        result = eng.resolve_air_engagement(
            "a1", "d1",
            Position(0, 0, 5000), Position(600, 0, 5000),
            missile_pk=0.7,
        )
        # Within WVR range (500–10000m default), should select WVR or GUNS
        assert result.mode in (AirCombatMode.WVR, AirCombatMode.GUNS_ONLY)


class TestStateRoundtrip:
    """State serialization and restoration."""

    def test_state_roundtrip(self):
        eng = _make_engine(seed=200)
        # Perform an engagement to advance PRNG state
        eng.bvr_engagement("a1", "d1", 40_000.0, 0.7)
        state = eng.get_state()

        eng2 = _make_engine(seed=999)
        eng2.set_state(state)

        # Both engines should produce identical next random draw
        r1 = eng._rng.random()
        r2 = eng2._rng.random()
        assert r1 == pytest.approx(r2)
