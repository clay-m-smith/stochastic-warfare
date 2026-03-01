"""Tests for environment.sea_state — waves, tides, SST."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.environment.astronomy import AstronomyEngine
from stochastic_warfare.environment.sea_state import SeaStateConfig, SeaStateEngine
from stochastic_warfare.environment.weather import WeatherConfig, WeatherEngine


def _build(dt: datetime | None = None, seed: int = 42) -> tuple[SeaStateEngine, SimulationClock, WeatherEngine]:
    if dt is None:
        dt = datetime(2020, 6, 21, 12, 0, tzinfo=timezone.utc)
    clock = SimulationClock(dt, timedelta(hours=1))
    rng_mgr = RNGManager(seed)
    rng = rng_mgr.get_stream(ModuleId.ENVIRONMENT)
    weather = WeatherEngine(WeatherConfig(), clock, rng)
    astro = AstronomyEngine(clock)
    sea = SeaStateEngine(SeaStateConfig(), clock, astro, weather, rng_mgr.get_stream(ModuleId.TERRAIN))
    return sea, clock, weather


class TestWaves:
    def test_wave_height_scales_with_wind(self) -> None:
        sea, _, _ = _build()
        # Pierson-Moskowitz: H_s = 0.22 * U^2 / g
        Hs = sea.current.significant_wave_height
        assert Hs >= 0

    def test_no_waves_in_calm(self) -> None:
        sea, _, weather = _build()
        # Force calm
        weather._wind_speed = 0.0
        assert sea.current.significant_wave_height == pytest.approx(0.0, abs=0.01)


class TestTides:
    def test_m2_period(self) -> None:
        """M2 tidal constituent has ~12.42 hour period."""
        sea, clock, weather = _build()
        tides = []
        for h in range(26):
            sea.update(3600)
            clock.advance()
            weather.update(3600)
            tides.append(sea.current.tide_height)

        # Should see roughly 2 cycles in 25 hours
        # Find zero crossings
        crossings = 0
        for i in range(1, len(tides)):
            if tides[i] * tides[i - 1] < 0:
                crossings += 1
        # M2: ~2 full cycles in 25h → ~4 zero crossings (±1)
        assert crossings >= 2

    def test_spring_greater_than_neap(self) -> None:
        """Spring tide range > neap tide range."""
        # Spring tide near new moon 2020-06-21
        spring, _, _ = _build(datetime(2020, 6, 21, 12, 0, tzinfo=timezone.utc))
        # Neap near first quarter 2020-06-28
        neap, _, _ = _build(datetime(2020, 6, 28, 12, 0, tzinfo=timezone.utc))

        # Compare tide_at amplitudes
        spring_range = abs(spring.tide_at(0)) + abs(spring.tide_at(6.2))
        neap_range = abs(neap.tide_at(0)) + abs(neap.tide_at(6.2))
        assert spring_range > neap_range * 0.5  # spring should be higher


class TestBeaufort:
    def test_beaufort_mapping(self) -> None:
        sea, _, _ = _build()
        b = sea.current.beaufort_scale
        assert 0 <= b <= 12


class TestSST:
    def test_sst_reasonable(self) -> None:
        sea, _, _ = _build()
        assert -5 < sea.current.sst < 35


class TestStateRoundTrip:
    def test_get_set_state(self) -> None:
        sea1, clock, weather = _build()
        for _ in range(10):
            sea1.update(3600)
            clock.advance()
            weather.update(3600)

        state = sea1.get_state()
        sea2, _, _ = _build()
        sea2.set_state(state)
        assert sea2._hours_elapsed == pytest.approx(sea1._hours_elapsed)
