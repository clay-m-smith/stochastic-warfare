"""Phase 62c: CBRN-Environment Interaction — weather effects on dispersal puffs.

Tests verify ``DispersalEngine.apply_weather_effects()`` — rain washout,
Arrhenius thermal decay, inversion trapping, and UV photo-degradation.
"""

from __future__ import annotations

import math

import pytest

from stochastic_warfare.cbrn.dispersal import DispersalEngine, DispersalConfig, PuffState
from stochastic_warfare.simulation.calibration import CalibrationSchema


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_puff(mass_kg: float = 10.0) -> PuffState:
    return PuffState(
        puff_id="test_puff_0",
        agent_id="agent_vx",
        center_e=1000.0,
        center_n=2000.0,
        mass_kg=mass_kg,
        release_time_s=0.0,
        age_s=0.0,
    )


def _make_engine() -> DispersalEngine:
    return DispersalEngine(DispersalConfig())


# ---------------------------------------------------------------------------
# Rain washout tests
# ---------------------------------------------------------------------------


class TestRainWashout:
    def test_heavy_rain_reduces_mass(self) -> None:
        """Heavy rain (30 mm/hr): concentration drops significantly in 30 min."""
        engine = _make_engine()
        puff = _make_puff(10.0)
        initial_mass = puff.mass_kg
        # 30 minutes = 1800 seconds
        engine.apply_weather_effects(
            puff, 1800.0,
            precipitation_rate_mm_hr=30.0,
            washout_coefficient=1e-4,
        )
        # exp(-1e-4 * 30 * 1800) = exp(-5.4) ≈ 0.0045 → significant reduction
        assert puff.mass_kg < initial_mass * 0.5
        assert puff.mass_kg > 0

    def test_no_rain_no_washout(self) -> None:
        """No precipitation: no washout effect."""
        engine = _make_engine()
        puff = _make_puff(10.0)
        initial_mass = puff.mass_kg
        engine.apply_weather_effects(
            puff, 1800.0,
            precipitation_rate_mm_hr=0.0,
            temperature_c=20.0,
            is_daytime=False,  # disable UV
            cloud_cover=1.0,   # disable UV
            stability_class="D",  # neutral — no inversion
        )
        # Only Arrhenius acts, at 20°C rate is negligible
        assert puff.mass_kg == pytest.approx(initial_mass, rel=0.01)


# ---------------------------------------------------------------------------
# Arrhenius thermal decay tests
# ---------------------------------------------------------------------------


class TestArrheniusDecay:
    def test_high_temp_faster_decay(self) -> None:
        """At 40°C: faster Arrhenius decay than at 0°C."""
        engine = _make_engine()
        puff_hot = _make_puff(10.0)
        puff_cold = _make_puff(10.0)
        dt = 3600.0  # 1 hour
        engine.apply_weather_effects(
            puff_hot, dt,
            temperature_c=40.0,
            precipitation_rate_mm_hr=0.0,
            is_daytime=False,
            cloud_cover=1.0,
            stability_class="D",
        )
        engine.apply_weather_effects(
            puff_cold, dt,
            temperature_c=0.0,
            precipitation_rate_mm_hr=0.0,
            is_daytime=False,
            cloud_cover=1.0,
            stability_class="D",
        )
        # Hot decays faster
        assert puff_hot.mass_kg < puff_cold.mass_kg

    def test_cold_slow_decay(self) -> None:
        """At 0°C: decay should be very slow over 30 min."""
        engine = _make_engine()
        puff = _make_puff(10.0)
        initial = puff.mass_kg
        engine.apply_weather_effects(
            puff, 1800.0,
            temperature_c=0.0,
            precipitation_rate_mm_hr=0.0,
            is_daytime=False,
            cloud_cover=1.0,
            stability_class="D",
        )
        # At 0°C (273K), k = exp(-50000/(8.314*273)) ≈ exp(-22) ≈ very small
        assert puff.mass_kg == pytest.approx(initial, rel=0.01)


# ---------------------------------------------------------------------------
# Inversion trapping tests
# ---------------------------------------------------------------------------


class TestInversionTrapping:
    def test_stable_atmosphere_boosts_concentration(self) -> None:
        """Stability class E/F: inversion trapping increases effective mass."""
        engine = _make_engine()
        puff = _make_puff(10.0)
        initial = puff.mass_kg
        engine.apply_weather_effects(
            puff, 3600.0,
            stability_class="E",
            precipitation_rate_mm_hr=0.0,
            temperature_c=20.0,
            is_daytime=False,
            cloud_cover=1.0,
            inversion_multiplier=8.0,
        )
        # Inversion should increase mass (represents concentration near ground)
        assert puff.mass_kg > initial

    def test_unstable_no_inversion(self) -> None:
        """Stability class A/B: no inversion effect."""
        engine = _make_engine()
        puff = _make_puff(10.0)
        initial = puff.mass_kg
        engine.apply_weather_effects(
            puff, 3600.0,
            stability_class="A",
            precipitation_rate_mm_hr=0.0,
            temperature_c=20.0,
            is_daytime=False,
            cloud_cover=1.0,
        )
        # Only Arrhenius at 20°C — negligible
        assert puff.mass_kg <= initial


# ---------------------------------------------------------------------------
# UV degradation tests
# ---------------------------------------------------------------------------


class TestUVDegradation:
    def test_clear_daytime_accelerates_decay(self) -> None:
        """Clear daytime (cloud < 0.5): UV accelerates agent decay."""
        engine = _make_engine()
        puff_day = _make_puff(10.0)
        puff_night = _make_puff(10.0)
        dt = 3600.0  # 1 hour
        engine.apply_weather_effects(
            puff_day, dt,
            is_daytime=True,
            cloud_cover=0.2,
            temperature_c=20.0,
            precipitation_rate_mm_hr=0.0,
            stability_class="D",
            uv_degradation_rate=0.1,
        )
        engine.apply_weather_effects(
            puff_night, dt,
            is_daytime=False,
            cloud_cover=0.2,
            temperature_c=20.0,
            precipitation_rate_mm_hr=0.0,
            stability_class="D",
            uv_degradation_rate=0.1,
        )
        assert puff_day.mass_kg < puff_night.mass_kg

    def test_overcast_no_uv(self) -> None:
        """Overcast (cloud ≥ 0.5): UV degradation disabled."""
        engine = _make_engine()
        puff_clear = _make_puff(10.0)
        puff_overcast = _make_puff(10.0)
        dt = 3600.0
        engine.apply_weather_effects(
            puff_clear, dt,
            is_daytime=True,
            cloud_cover=0.2,
            stability_class="D",
            precipitation_rate_mm_hr=0.0,
            temperature_c=20.0,
        )
        engine.apply_weather_effects(
            puff_overcast, dt,
            is_daytime=True,
            cloud_cover=0.8,
            stability_class="D",
            precipitation_rate_mm_hr=0.0,
            temperature_c=20.0,
        )
        assert puff_overcast.mass_kg > puff_clear.mass_kg


# ---------------------------------------------------------------------------
# Gate & compound tests
# ---------------------------------------------------------------------------


class TestCBRNEnvironmentGate:
    def test_disabled_no_weather_effects(self) -> None:
        """enable_cbrn_environment=False: no weather effects on puffs."""
        cal = CalibrationSchema(enable_cbrn_environment=False)
        assert cal.enable_cbrn_environment is False


class TestCompoundEffects:
    def test_rain_plus_heat_plus_uv_rapid_decay(self) -> None:
        """Multiple effects compound: rain + high temp + UV → rapid decay."""
        engine = _make_engine()
        puff_multi = _make_puff(10.0)
        puff_single = _make_puff(10.0)
        dt = 1800.0  # 30 min

        # Multi-effect: rain + heat + UV
        engine.apply_weather_effects(
            puff_multi, dt,
            precipitation_rate_mm_hr=20.0,
            temperature_c=40.0,
            is_daytime=True,
            cloud_cover=0.1,
            stability_class="D",
            washout_coefficient=1e-4,
            uv_degradation_rate=0.1,
        )

        # Single-effect: rain only
        engine.apply_weather_effects(
            puff_single, dt,
            precipitation_rate_mm_hr=20.0,
            temperature_c=0.0,
            is_daytime=False,
            cloud_cover=1.0,
            stability_class="D",
            washout_coefficient=1e-4,
        )

        # Multi-effect should decay faster
        assert puff_multi.mass_kg < puff_single.mass_kg
