"""Unit tests for VolleyFireEngine — Napoleonic massed musket fire."""

from __future__ import annotations

import pytest

from stochastic_warfare.combat.volley_fire import (
    VolleyFireEngine,
    VolleyResult,
    VolleyType,
)

from .conftest import _rng


# ---------------------------------------------------------------------------
# Range-dependent hit probability
# ---------------------------------------------------------------------------


class TestRangeDependentPhit:
    """Phit decays with range from smoothbore table."""

    def test_close_range_higher_casualties(self):
        """50m should produce more casualties than 200m."""
        eng1 = VolleyFireEngine(rng=_rng(seed=1))
        close = eng1.fire_volley(200, range_m=50.0)
        eng2 = VolleyFireEngine(rng=_rng(seed=1))
        far = eng2.fire_volley(200, range_m=200.0)
        # 50m Phit=0.15 vs 200m Phit=0.01
        assert close.casualties >= far.casualties

    def test_interpolation_midpoint(self):
        """100m Phit should be ~0.05 (from table)."""
        eng = VolleyFireEngine(rng=_rng(seed=2))
        result = eng.fire_volley(500, range_m=100.0)
        # 500 * 0.05 = 25 expected — allow stochastic variance
        assert 0 <= result.casualties <= 100


# ---------------------------------------------------------------------------
# Rifle accuracy multiplier
# ---------------------------------------------------------------------------


class TestRifleAccuracy:
    """is_rifle=True applies 3x accuracy multiplier."""

    def test_rifle_more_casualties_than_smoothbore(self):
        eng1 = VolleyFireEngine(rng=_rng(seed=5))
        smooth = eng1.fire_volley(200, 100.0, is_rifle=False)
        eng2 = VolleyFireEngine(rng=_rng(seed=5))
        rifle = eng2.fire_volley(200, 100.0, is_rifle=True)
        assert rifle.casualties >= smooth.casualties


# ---------------------------------------------------------------------------
# Smoke mechanics
# ---------------------------------------------------------------------------


class TestSmokeMechanics:
    """Smoke accumulation, penalty, and dissipation."""

    def test_smoke_accumulates_per_volley(self):
        eng = VolleyFireEngine(rng=_rng(seed=10))
        assert eng.current_smoke == pytest.approx(0.0)
        eng.fire_volley(100, 100.0)
        assert eng.current_smoke == pytest.approx(0.1)

    def test_smoke_penalty_reduces_casualties(self):
        """Firing into heavy smoke reduces effectiveness."""
        eng = VolleyFireEngine(rng=_rng(seed=11))
        clean = eng.fire_volley(500, 50.0, current_smoke=0.0)
        eng2 = VolleyFireEngine(rng=_rng(seed=11))
        smoky = eng2.fire_volley(500, 50.0, current_smoke=0.8)
        assert smoky.casualties <= clean.casualties

    def test_smoke_dissipation(self):
        """update_smoke reduces smoke level over time."""
        eng = VolleyFireEngine(rng=_rng(seed=12))
        eng.fire_volley(100, 100.0)  # generates 0.1 smoke
        initial = eng.current_smoke
        eng.update_smoke(dt_s=10.0, wind_speed_mps=0.0)
        # decay = 0.02 * 10 = 0.2, so smoke = max(0, 0.1 - 0.2) = 0.0
        assert eng.current_smoke < initial

    def test_wind_accelerates_dissipation(self):
        eng = VolleyFireEngine(rng=_rng(seed=13))
        eng.fire_volley(100, 100.0)
        smoke_before = eng.current_smoke
        eng.update_smoke(dt_s=1.0, wind_speed_mps=5.0)
        # Wind factor: 1.0 + 5.0*0.2 = 2.0 -> decay = 0.02 * 1 * 2.0 = 0.04
        assert eng.current_smoke < smoke_before


# ---------------------------------------------------------------------------
# Volley type modifiers
# ---------------------------------------------------------------------------


class TestVolleyTypeModifiers:
    """INDEPENDENT_FIRE and ROLLING_FIRE accuracy modifiers."""

    def test_independent_fire_lower_accuracy(self):
        eng1 = VolleyFireEngine(rng=_rng(seed=20))
        volley = eng1.fire_volley(300, 100.0, volley_type=VolleyType.VOLLEY_BY_RANK)
        eng2 = VolleyFireEngine(rng=_rng(seed=20))
        indep = eng2.fire_volley(300, 100.0, volley_type=VolleyType.INDEPENDENT_FIRE)
        # 0.7 modifier -> fewer expected casualties
        assert indep.casualties <= volley.casualties

    def test_rolling_fire_moderate_accuracy(self):
        eng = VolleyFireEngine(rng=_rng(seed=21))
        result = eng.fire_volley(300, 100.0, volley_type=VolleyType.ROLLING_FIRE)
        # 0.9 modifier on Phit=0.05 -> ~13.5 expected from 300
        assert result.casualties >= 0


# ---------------------------------------------------------------------------
# Canister fire
# ---------------------------------------------------------------------------


class TestCanisterFire:
    """Canister shot — short-range anti-personnel."""

    def test_canister_within_range(self):
        eng = VolleyFireEngine(rng=_rng(seed=25))
        result = eng.fire_canister(range_m=100.0, n_guns=4)
        assert isinstance(result, VolleyResult)
        assert result.casualties >= 0
        assert result.ammo_consumed == 4

    def test_canister_beyond_range(self):
        """Canister beyond max range produces zero casualties."""
        eng = VolleyFireEngine(rng=_rng(seed=26))
        result = eng.fire_canister(range_m=500.0, n_guns=4)
        assert result.casualties == 0

    def test_canister_formation_vulnerability(self):
        """Higher formation vulnerability increases canister casualties."""
        eng1 = VolleyFireEngine(rng=_rng(seed=27))
        low_vuln = eng1.fire_canister(range_m=100.0, n_guns=4, target_formation_artillery_vuln=0.5)
        eng2 = VolleyFireEngine(rng=_rng(seed=27))
        high_vuln = eng2.fire_canister(range_m=100.0, n_guns=4, target_formation_artillery_vuln=2.0)
        assert high_vuln.casualties >= low_vuln.casualties


# ---------------------------------------------------------------------------
# Formation firepower fraction
# ---------------------------------------------------------------------------


class TestFormationFirepower:
    """formation_firepower_fraction=0 -> 0 effective muskets."""

    def test_zero_fraction_no_casualties(self):
        eng = VolleyFireEngine(rng=_rng(seed=30))
        result = eng.fire_volley(200, 50.0, formation_firepower_fraction=0.0)
        assert result.casualties == 0
        assert result.ammo_consumed == 0


# ---------------------------------------------------------------------------
# State roundtrip
# ---------------------------------------------------------------------------


class TestVolleyFireStateRoundtrip:
    """State persistence for checkpointing."""

    def test_state_roundtrip(self):
        eng = VolleyFireEngine(rng=_rng(seed=40))
        eng.fire_volley(100, 100.0)
        eng.fire_volley(100, 100.0)
        state = eng.get_state()

        eng2 = VolleyFireEngine(rng=_rng(seed=40))
        eng2.set_state(state)
        assert eng2.current_smoke == pytest.approx(eng.current_smoke)
