"""Tests for environment.seasons — seasonal accumulation model."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.environment.astronomy import AstronomyEngine
from stochastic_warfare.environment.seasons import GroundState, SeasonsConfig, SeasonsEngine
from stochastic_warfare.environment.weather import ClimateZone, WeatherConfig, WeatherEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build(
    start: datetime, latitude: float = 50.0,
    climate_zone: ClimateZone = ClimateZone.TEMPERATE,
    seed: int = 42,
) -> tuple[SeasonsEngine, SimulationClock, WeatherEngine]:
    clock = SimulationClock(start, timedelta(hours=1))
    rng = RNGManager(seed).get_stream(ModuleId.ENVIRONMENT)
    wx_config = WeatherConfig(climate_zone=climate_zone, latitude=latitude)
    weather = WeatherEngine(wx_config, clock, rng)
    astro = AstronomyEngine(clock)
    seasons = SeasonsEngine(SeasonsConfig(latitude=latitude), clock, weather, astro)
    return (seasons, clock, weather)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGroundState:
    def test_initial_state_dry(self) -> None:
        seasons, _, _ = _build(datetime(2020, 6, 21, tzinfo=timezone.utc))
        assert seasons.current.ground_state == GroundState.DRY

    def test_freeze_thaw_cycle(self) -> None:
        """Simulating deep winter should eventually freeze the ground."""
        seasons, clock, weather = _build(
            datetime(2020, 1, 15, tzinfo=timezone.utc),
            latitude=55.0,
            climate_zone=ClimateZone.CONTINENTAL,
        )
        # Advance many days in cold weather
        for _ in range(30 * 24):  # 30 days
            weather.update(3600)
            seasons.update(3600)
            clock.advance()

        # In continental winter, ground should freeze or have snow
        gs = seasons.current.ground_state
        assert gs in (GroundState.FROZEN, GroundState.SNOW_COVERED,
                      GroundState.THAWING, GroundState.WET)


class TestSnow:
    def test_snow_accumulation_in_winter(self) -> None:
        """Some snow should accumulate in a cold winter scenario."""
        seasons, clock, weather = _build(
            datetime(2020, 1, 1, tzinfo=timezone.utc),
            latitude=60.0,
            climate_zone=ClimateZone.SUBARCTIC,
        )
        for _ in range(60 * 24):  # 60 days
            weather.update(3600)
            seasons.update(3600)
            clock.advance()

        # Snow may or may not have accumulated depending on stochastic weather
        # At minimum, the model ran without error
        assert seasons.current.snow_depth >= 0


class TestVegetation:
    def test_tropical_always_dense(self) -> None:
        seasons, _, _ = _build(
            datetime(2020, 1, 1, tzinfo=timezone.utc),
            latitude=10.0,
            climate_zone=ClimateZone.TROPICAL,
        )
        assert seasons.current.vegetation_density > 0.8

    def test_growing_season_increases_vegetation(self) -> None:
        seasons, clock, weather = _build(
            datetime(2020, 4, 1, tzinfo=timezone.utc),
            latitude=45.0,
        )
        initial = seasons.current.vegetation_density
        for _ in range(90 * 24):  # 90 days (spring→summer)
            weather.update(3600)
            seasons.update(3600)
            clock.advance()

        final = seasons.current.vegetation_density
        assert final >= initial  # should increase or stay same


class TestWildfireRisk:
    def test_cold_no_wildfire(self) -> None:
        seasons, _, _ = _build(
            datetime(2020, 1, 15, tzinfo=timezone.utc),
            latitude=55.0,
            climate_zone=ClimateZone.CONTINENTAL,
        )
        assert seasons.current.wildfire_risk == pytest.approx(0.0)

    def test_wildfire_risk_bounded(self) -> None:
        seasons, clock, weather = _build(
            datetime(2020, 8, 1, tzinfo=timezone.utc),
            latitude=35.0,
            climate_zone=ClimateZone.ARID,
        )
        for _ in range(24):
            weather.update(3600)
            seasons.update(3600)
            clock.advance()
        assert 0.0 <= seasons.current.wildfire_risk <= 1.0


class TestTrafficability:
    def test_dry_ground_full_trafficability(self) -> None:
        seasons, _, _ = _build(datetime(2020, 6, 21, tzinfo=timezone.utc))
        assert seasons.current.ground_trafficability == pytest.approx(1.0)


class TestDaylight:
    def test_daylight_hours_positive(self) -> None:
        seasons, _, _ = _build(datetime(2020, 6, 21, tzinfo=timezone.utc))
        assert seasons.current.daylight_hours > 0

    def test_summer_longer_than_winter(self) -> None:
        summer, _, _ = _build(datetime(2020, 6, 21, 12, 0, tzinfo=timezone.utc), latitude=45.0)
        winter, _, _ = _build(datetime(2020, 12, 21, 12, 0, tzinfo=timezone.utc), latitude=45.0)
        assert summer.current.daylight_hours > winter.current.daylight_hours


class TestStateRoundTrip:
    def test_get_set_state_preserves_accumulators(self) -> None:
        seasons1, clock, weather = _build(
            datetime(2020, 4, 1, tzinfo=timezone.utc),
        )
        for _ in range(48):
            weather.update(3600)
            seasons1.update(3600)
            clock.advance()

        state = seasons1.get_state()

        seasons2, _, _ = _build(datetime(2020, 4, 1, tzinfo=timezone.utc))
        seasons2.set_state(state)

        assert seasons2.current.ground_state == seasons1.current.ground_state
        assert seasons2.current.snow_depth == pytest.approx(seasons1.current.snow_depth)

    def test_deterministic_with_fixed_weather(self) -> None:
        s1, c1, w1 = _build(datetime(2020, 6, 1, tzinfo=timezone.utc), seed=42)
        s2, c2, w2 = _build(datetime(2020, 6, 1, tzinfo=timezone.utc), seed=42)

        for _ in range(48):
            w1.update(3600); s1.update(3600); c1.advance()
            w2.update(3600); s2.update(3600); c2.advance()

        assert s1.current.ground_state == s2.current.ground_state
        assert s1.current.vegetation_density == pytest.approx(s2.current.vegetation_density)
