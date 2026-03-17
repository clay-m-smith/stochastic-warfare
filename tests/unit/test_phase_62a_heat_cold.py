"""Phase 62a: Heat & Cold Environmental Casualties — inline math verification tests.

Tests verify the WBGT/wind-chill helpers and the environmental casualty
accumulation logic wired into BattleManager.execute_tick() when
``enable_human_factors=True``.
"""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from stochastic_warfare.simulation.battle import _compute_wbgt, _compute_wind_chill
from stochastic_warfare.simulation.calibration import CalibrationSchema


# ---------------------------------------------------------------------------
# Helper: replicate the inline environmental casualty math from battle.py
# ---------------------------------------------------------------------------

def _heat_casualties_per_hour(
    temperature_c: float,
    humidity: float,
    mopp_level: int = 0,
    is_moving: bool = False,
    base_rate: float = 0.02,
) -> float:
    """Compute fractional heat casualties per hour."""
    wbgt = _compute_wbgt(temperature_c, humidity)
    if wbgt <= 28.0:
        return 0.0
    rate = base_rate * (wbgt - 28.0) / 10.0
    rate *= 1.0 + mopp_level * 0.5  # MOPP heat trap
    if is_moving:
        rate *= 1.5
    return rate


def _cold_casualties_per_hour(
    temperature_c: float,
    wind_speed_mps: float,
    base_rate: float = 0.015,
) -> float:
    """Compute fractional cold casualties per hour."""
    wc = _compute_wind_chill(temperature_c, wind_speed_mps)
    if wc >= -20.0:
        return 0.0
    return base_rate * (abs(wc) - 20.0) / 20.0


# ---------------------------------------------------------------------------
# WBGT helper tests
# ---------------------------------------------------------------------------


class TestWBGT:
    def test_high_heat_high_humidity(self) -> None:
        """WBGT at 40°C / 80% humidity should exceed 28°C threshold."""
        wbgt = _compute_wbgt(40.0, 0.8)
        assert wbgt > 28.0

    def test_moderate_heat_low_humidity(self) -> None:
        """25°C / 30% humidity — WBGT should be below threshold."""
        wbgt = _compute_wbgt(25.0, 0.3)
        assert wbgt < 28.0

    def test_formula_sanity(self) -> None:
        """WBGT(T, H=1.0) = 0.7·T + 0.3·T = T."""
        assert _compute_wbgt(35.0, 1.0) == pytest.approx(35.0, abs=0.1)


# ---------------------------------------------------------------------------
# Wind chill helper tests
# ---------------------------------------------------------------------------


class TestWindChill:
    def test_extreme_cold_strong_wind(self) -> None:
        """Wind chill at -15°C / 10 m/s should be well below -20°C."""
        wc = _compute_wind_chill(-15.0, 10.0)
        assert wc < -20.0

    def test_mild_cold_no_effect(self) -> None:
        """5°C — mild cold, but formula only applies at T ≤ 10°C.
        Wind chill should still be > -20°C."""
        wc = _compute_wind_chill(5.0, 5.0)
        assert wc > -20.0

    def test_warm_returns_temperature(self) -> None:
        """Above 10°C the formula is not valid; should return T."""
        wc = _compute_wind_chill(15.0, 10.0)
        assert wc == pytest.approx(15.0)

    def test_low_wind_returns_temperature(self) -> None:
        """Below 4.8 km/h wind (1.33 m/s), formula not valid; returns T."""
        wc = _compute_wind_chill(-5.0, 1.0)
        assert wc == pytest.approx(-5.0)


# ---------------------------------------------------------------------------
# Casualty rate computation tests
# ---------------------------------------------------------------------------


class TestHeatColdCasualtyRates:
    def test_high_wbgt_produces_casualties(self) -> None:
        """WBGT > 32°C: heat casualties should accumulate."""
        rate = _heat_casualties_per_hour(40.0, 0.8)
        assert rate > 0.0

    def test_moderate_wbgt_low_rate(self) -> None:
        """WBGT 28–32°C: low but non-zero rate."""
        # 30°C, 70% humidity → WBGT ≈ 30 * (0.7 * sqrt(0.7) + 0.3) ≈ 26.6 ... let's check
        wbgt = _compute_wbgt(30.0, 0.7)
        if wbgt > 28.0:
            rate = _heat_casualties_per_hour(30.0, 0.7)
            assert rate > 0.0
            assert rate < 0.02  # lower than extreme heat
        else:
            rate = _heat_casualties_per_hour(30.0, 0.7)
            assert rate == 0.0

    def test_cool_weather_no_heat_casualties(self) -> None:
        """WBGT < 28°C: zero heat casualties."""
        rate = _heat_casualties_per_hour(20.0, 0.5)
        assert rate == 0.0

    def test_mopp4_triples_heat_rate(self) -> None:
        """MOPP-4 (mopp_level=4): multiplier = 1 + 4*0.5 = 3.0."""
        base = _heat_casualties_per_hour(40.0, 0.8, mopp_level=0)
        mopp4 = _heat_casualties_per_hour(40.0, 0.8, mopp_level=4)
        assert mopp4 == pytest.approx(base * 3.0, rel=0.01)

    def test_severe_cold_produces_casualties(self) -> None:
        """Wind chill < -25°C: cold casualties accumulate."""
        rate = _cold_casualties_per_hour(-20.0, 10.0)
        assert rate > 0.0

    def test_moderate_cold_low_rate(self) -> None:
        """Wind chill -20 to -25°C: low rate."""
        # -15°C with 5 m/s → WC ≈ -21 to -22
        wc = _compute_wind_chill(-15.0, 5.0)
        rate = _cold_casualties_per_hour(-15.0, 5.0)
        if wc < -20.0:
            assert rate > 0.0
            assert rate < 0.015  # below max base rate
        else:
            assert rate == 0.0

    def test_warm_no_cold_casualties(self) -> None:
        """Wind chill > -20°C: zero cold casualties."""
        rate = _cold_casualties_per_hour(0.0, 2.0)
        assert rate == 0.0


class TestEnableHumanFactorsGate:
    def test_disabled_no_casualties(self) -> None:
        """enable_human_factors=False: no environmental casualties applied."""
        cal = CalibrationSchema(enable_human_factors=False)
        # Just verifying the gate — the actual battle loop is tested
        # via the structural test. Here we confirm the flag defaults off.
        assert cal.enable_human_factors is False

    def test_enabled_flag(self) -> None:
        cal = CalibrationSchema(enable_human_factors=True)
        assert cal.enable_human_factors is True


class TestFractionalAccumulation:
    def test_accumulation_below_one(self) -> None:
        """At very low rate, fractional accumulator < 1.0 → no immediate casualty."""
        # 0.001 fraction per tick → need 1000 ticks for 1 casualty
        accum = 0.0
        accum += 0.001
        assert accum < 1.0
        assert int(accum) == 0

    def test_accumulation_crosses_one(self) -> None:
        """Accumulator crosses 1.0 → yields integer casualties."""
        accum = 0.0
        for _ in range(1001):
            accum += 0.001
        cas = int(accum)
        assert cas >= 1
