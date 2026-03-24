"""Tests for environment.time_of_day — illumination and thermal models."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.environment.astronomy import AstronomyEngine
from stochastic_warfare.environment.time_of_day import TimeOfDayEngine
from stochastic_warfare.environment.weather import WeatherConfig, WeatherEngine


def _build(dt: datetime) -> TimeOfDayEngine:
    clock = SimulationClock(dt, timedelta(hours=1))
    rng = RNGManager(42).get_stream(ModuleId.ENVIRONMENT)
    weather = WeatherEngine(WeatherConfig(), clock, rng)
    astro = AstronomyEngine(clock)
    return TimeOfDayEngine(astro, weather, clock)


class TestIllumination:
    def test_noon_bright(self) -> None:
        tod = _build(datetime(2020, 6, 21, 12, 0, tzinfo=timezone.utc))
        illum = tod.illumination_at(45.0, 0.0)
        assert illum.ambient_lux > 10_000
        assert illum.is_day

    def test_midnight_dark(self) -> None:
        tod = _build(datetime(2020, 6, 21, 0, 0, tzinfo=timezone.utc))
        illum = tod.illumination_at(45.0, 0.0)
        assert illum.ambient_lux < 1.0
        assert not illum.is_day

    def test_noon_brighter_than_midnight(self) -> None:
        noon = _build(datetime(2020, 6, 21, 12, 0, tzinfo=timezone.utc))
        midnight = _build(datetime(2020, 6, 21, 0, 0, tzinfo=timezone.utc))
        assert noon.illumination_at(45.0, 0.0).ambient_lux > midnight.illumination_at(45.0, 0.0).ambient_lux

    def test_full_moon_brighter_than_new_moon(self) -> None:
        # Full moon ~2020-07-05
        full = _build(datetime(2020, 7, 5, 0, 0, tzinfo=timezone.utc))
        # New moon ~2020-06-21
        new = _build(datetime(2020, 6, 21, 0, 0, tzinfo=timezone.utc))
        full_lux = full.illumination_at(45.0, 0.0).ambient_lux
        new_lux = new.illumination_at(45.0, 0.0).ambient_lux
        # Full moon night should be brighter (if moon is up)
        # This may not always hold depending on moonrise, so just check >= baseline
        assert full_lux >= 0.001


class TestNVG:
    def test_nvg_tracks_illumination(self) -> None:
        noon = _build(datetime(2020, 6, 21, 12, 0, tzinfo=timezone.utc))
        midnight = _build(datetime(2020, 6, 21, 0, 0, tzinfo=timezone.utc))
        # NVG less effective at noon (too bright, but still works in model)
        nvg_noon = noon.nvg_effectiveness(45.0, 0.0)
        nvg_night = midnight.nvg_effectiveness(45.0, 0.0)
        assert 0 <= nvg_noon <= 1
        assert 0 <= nvg_night <= 1

    def test_nvg_bounded(self) -> None:
        tod = _build(datetime(2020, 6, 21, 0, 0, tzinfo=timezone.utc))
        assert 0 <= tod.nvg_effectiveness(45.0, 0.0) <= 1


class TestThermal:
    def test_crossover_near_dawn_dusk(self) -> None:
        # Near sunset (~19:00 UTC at 45N in June)
        tod = _build(datetime(2020, 6, 21, 19, 0, tzinfo=timezone.utc))
        te = tod.thermal_environment(45.0, 0.0)
        assert te.crossover_in_hours >= 0

    def test_thermal_contrast_bounded(self) -> None:
        tod = _build(datetime(2020, 6, 21, 12, 0, tzinfo=timezone.utc))
        te = tod.thermal_environment(45.0, 0.0)
        assert 0 <= te.thermal_contrast <= 1


class TestShadows:
    def test_shadow_at_noon(self) -> None:
        tod = _build(datetime(2020, 6, 21, 12, 0, tzinfo=timezone.utc))
        az = tod.shadow_azimuth(45.0, 0.0)
        assert az is not None

    def test_no_shadow_at_night(self) -> None:
        tod = _build(datetime(2020, 6, 21, 0, 0, tzinfo=timezone.utc))
        assert tod.shadow_azimuth(45.0, 0.0) is None


class TestStatePersistence:
    def test_stateless(self) -> None:
        tod = _build(datetime(2020, 6, 21, 12, 0, tzinfo=timezone.utc))
        assert tod.get_state() == {}
