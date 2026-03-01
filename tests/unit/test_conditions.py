"""Tests for environment.conditions — composite conditions facade."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.environment.astronomy import AstronomyEngine
from stochastic_warfare.environment.conditions import ConditionsEngine
from stochastic_warfare.environment.electromagnetic import EMEnvironment
from stochastic_warfare.environment.obscurants import ObscurantsEngine
from stochastic_warfare.environment.sea_state import SeaStateConfig, SeaStateEngine
from stochastic_warfare.environment.seasons import SeasonsConfig, SeasonsEngine
from stochastic_warfare.environment.time_of_day import TimeOfDayEngine
from stochastic_warfare.environment.underwater_acoustics import UnderwaterAcousticsEngine
from stochastic_warfare.environment.weather import WeatherConfig, WeatherEngine


def _build_all() -> ConditionsEngine:
    dt = datetime(2020, 6, 21, 12, 0, tzinfo=timezone.utc)
    clock = SimulationClock(dt, timedelta(hours=1))
    rng_mgr = RNGManager(42)
    rng_env = rng_mgr.get_stream(ModuleId.ENVIRONMENT)
    rng_ter = rng_mgr.get_stream(ModuleId.TERRAIN)
    rng_core = rng_mgr.get_stream(ModuleId.CORE)

    weather = WeatherEngine(WeatherConfig(), clock, rng_env)
    astro = AstronomyEngine(clock)
    tod = TimeOfDayEngine(astro, weather, clock)
    seasons = SeasonsEngine(SeasonsConfig(latitude=45.0), clock, weather, astro)
    obscurants = ObscurantsEngine(weather, tod, clock, rng_ter)
    sea = SeaStateEngine(SeaStateConfig(), clock, astro, weather, rng_core)
    acoustics = UnderwaterAcousticsEngine(sea, clock, rng_mgr.get_stream(ModuleId.COMBAT))
    em = EMEnvironment(weather, sea, clock)

    return ConditionsEngine(weather, tod, seasons, obscurants, sea, acoustics, em)


class TestLandConditions:
    def test_land_returns_all_fields(self) -> None:
        cond = _build_all()
        lc = cond.land(Position(0, 0), 45.0, 0.0)
        assert lc.visibility > 0
        assert 0 <= lc.trafficability <= 1
        assert lc.temperature != 0  # some value
        assert lc.illumination_lux > 0

    def test_obscurants_reduce_visibility(self) -> None:
        cond = _build_all()
        base = cond.land(Position(500, 500), 45.0, 0.0)
        cond._obscurants.deploy_smoke(Position(500, 500), radius=100.0)
        with_smoke = cond.land(Position(500, 500), 45.0, 0.0)
        assert with_smoke.visibility < base.visibility


class TestAirConditions:
    def test_air_returns_all_fields(self) -> None:
        cond = _build_all()
        ac = cond.air(Position(0, 0), 5000.0, 45.0, 0.0)
        assert ac.visibility > 0
        assert ac.temperature_at_altitude < cond._weather.current.temperature
        assert ac.gps_accuracy > 0


class TestMaritimeConditions:
    def test_maritime_returns_all_fields(self) -> None:
        cond = _build_all()
        mc = cond.maritime(45.0, 0.0)
        assert mc.sea_state_beaufort >= 0
        assert mc.sst > -5

    def test_no_sea_state_raises(self) -> None:
        dt = datetime(2020, 6, 21, 12, 0, tzinfo=timezone.utc)
        clock = SimulationClock(dt, timedelta(hours=1))
        rng = RNGManager(42).get_stream(ModuleId.ENVIRONMENT)
        weather = WeatherEngine(WeatherConfig(), clock, rng)
        astro = AstronomyEngine(clock)
        tod = TimeOfDayEngine(astro, weather, clock)
        seasons = SeasonsEngine(SeasonsConfig(latitude=45.0), clock, weather, astro)
        obs = ObscurantsEngine(weather, tod, clock, RNGManager(42).get_stream(ModuleId.TERRAIN))
        cond = ConditionsEngine(weather, tod, seasons, obs)
        with pytest.raises(RuntimeError):
            cond.maritime(45.0, 0.0)


class TestAcousticConditions:
    def test_acoustic_returns(self) -> None:
        cond = _build_all()
        ac = cond.acoustic()
        assert ac.ambient_noise_db > 0
        assert len(ac.convergence_zone_ranges) > 0


class TestEMConditions:
    def test_em_returns(self) -> None:
        cond = _build_all()
        em = cond.electromagnetic()
        assert 0 <= em.hf_quality <= 1
        assert em.radar_refraction > 1
        assert em.gps_accuracy > 0


class TestStatePersistence:
    def test_stateless(self) -> None:
        cond = _build_all()
        assert cond.get_state() == {}
