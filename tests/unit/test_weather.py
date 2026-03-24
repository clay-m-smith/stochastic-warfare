"""Tests for environment.weather — Markov chain weather model."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.environment.weather import (
    ClimateZone,
    WeatherConfig,
    WeatherEngine,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2020, 6, 21, 12, 0, tzinfo=timezone.utc)


def _make_engine(seed: int = 42, **kwargs) -> tuple[WeatherEngine, SimulationClock]:
    clock = SimulationClock(_NOW, timedelta(hours=1))
    rng = RNGManager(seed).get_stream(ModuleId.ENVIRONMENT)
    config = WeatherConfig(**kwargs)
    return WeatherEngine(config, clock, rng), clock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_seed_same_sequence(self) -> None:
        eng1, c1 = _make_engine(seed=123)
        eng2, c2 = _make_engine(seed=123)

        for _ in range(20):
            eng1.update(3600); c1.advance()
            eng2.update(3600); c2.advance()

        assert eng1.current.state == eng2.current.state
        assert eng1.current.temperature == pytest.approx(eng2.current.temperature)
        assert eng1.current.wind.speed == pytest.approx(eng2.current.wind.speed)

    def test_different_seed_different(self) -> None:
        eng1, c1 = _make_engine(seed=42)
        eng2, c2 = _make_engine(seed=99)

        winds1, winds2 = [], []
        for _ in range(50):
            eng1.update(3600); c1.advance()
            eng2.update(3600); c2.advance()
            winds1.append(eng1.current.wind.speed)
            winds2.append(eng2.current.wind.speed)

        # Wind speeds from different seeds should diverge
        assert winds1 != winds2


class TestWeatherEvolution:
    def test_state_changes_over_time(self) -> None:
        eng, clock = _make_engine(seed=42)
        states = set()
        for _ in range(100):
            eng.update(3600); clock.advance()
            states.add(eng.current.state)
        assert len(states) > 1

    def test_temperature_varies(self) -> None:
        eng, clock = _make_engine(seed=42)
        temps = []
        for _ in range(24):
            eng.update(3600); clock.advance()
            temps.append(eng.current.temperature)
        assert max(temps) > min(temps)

    def test_wind_stays_positive(self) -> None:
        eng, clock = _make_engine(seed=42)
        for _ in range(100):
            eng.update(3600); clock.advance()
            assert eng.current.wind.speed >= 0


class TestAtmosphere:
    def test_isa_lapse_rate(self) -> None:
        eng, _ = _make_engine()
        t0 = eng.temperature_at_altitude(0)
        t5k = eng.temperature_at_altitude(5000)
        assert t0 - t5k == pytest.approx(32.5, abs=0.1)

    def test_density_decreases_with_altitude(self) -> None:
        eng, _ = _make_engine()
        d0 = eng.atmospheric_density(0)
        d5k = eng.atmospheric_density(5000)
        assert d5k < d0

    def test_pressure_decreases_with_altitude(self) -> None:
        eng, _ = _make_engine()
        p0 = eng.pressure_at_altitude(0)
        p5k = eng.pressure_at_altitude(5000)
        assert p5k < p0

    def test_sea_level_density_reasonable(self) -> None:
        eng, _ = _make_engine()
        d = eng.atmospheric_density(0)
        assert 1.0 < d < 1.5


class TestClimateZones:
    def test_arctic_cold(self) -> None:
        eng, _ = _make_engine(climate_zone=ClimateZone.ARCTIC)
        assert eng.current.temperature < 25

    def test_tropical_warm(self) -> None:
        eng, _ = _make_engine(climate_zone=ClimateZone.TROPICAL)
        assert eng.current.temperature > 15


class TestStateRoundTrip:
    def test_get_set_state_preserves_sequence(self) -> None:
        eng1, c1 = _make_engine(seed=42)
        for _ in range(10):
            eng1.update(3600); c1.advance()

        state = eng1.get_state()

        eng2, _ = _make_engine(seed=42)
        eng2.set_state(state)

        assert eng2.current.state == eng1.current.state
        assert eng2.current.temperature == pytest.approx(eng1.current.temperature)
