"""Tests for environment.underwater_acoustics — Mackenzie equation, TL, SVP."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.environment.astronomy import AstronomyEngine
from stochastic_warfare.environment.sea_state import SeaStateConfig, SeaStateEngine
from stochastic_warfare.environment.underwater_acoustics import UnderwaterAcousticsEngine
from stochastic_warfare.environment.weather import WeatherConfig, WeatherEngine


def _build() -> UnderwaterAcousticsEngine:
    dt = datetime(2020, 6, 21, 12, 0, tzinfo=timezone.utc)
    clock = SimulationClock(dt, timedelta(hours=1))
    rng_mgr = RNGManager(42)
    rng = rng_mgr.get_stream(ModuleId.ENVIRONMENT)
    weather = WeatherEngine(WeatherConfig(), clock, rng)
    astro = AstronomyEngine(clock)
    sea = SeaStateEngine(SeaStateConfig(), clock, astro, weather, rng_mgr.get_stream(ModuleId.TERRAIN))
    return UnderwaterAcousticsEngine(sea, clock, rng_mgr.get_stream(ModuleId.CORE))


class TestMackenzie:
    def test_known_value(self) -> None:
        """Mackenzie at T=10°C, S=35PSU, D=0m ≈ 1490 m/s."""
        eng = _build()
        c = eng.sound_velocity(10.0, 35.0, 0.0)
        assert 1485 < c < 1495

    def test_increases_with_temperature(self) -> None:
        eng = _build()
        c10 = eng.sound_velocity(10.0, 35.0, 0.0)
        c20 = eng.sound_velocity(20.0, 35.0, 0.0)
        assert c20 > c10

    def test_increases_with_depth(self) -> None:
        eng = _build()
        c0 = eng.sound_velocity(10.0, 35.0, 0.0)
        c1000 = eng.sound_velocity(10.0, 35.0, 1000.0)
        assert c1000 > c0


class TestSVP:
    def test_svp_shape(self) -> None:
        eng = _build()
        svp = eng.svp_at(500.0)
        assert len(svp.depths) == len(svp.velocities)
        assert svp.depths[0] == 0.0
        assert svp.depths[-1] == pytest.approx(500.0)

    def test_svp_reasonable_values(self) -> None:
        eng = _build()
        svp = eng.svp_at(1000.0)
        assert all(1400 < v < 1600 for v in svp.velocities)


class TestTransmissionLoss:
    def test_tl_increases_with_range(self) -> None:
        eng = _build()
        tl1 = eng.transmission_loss(1000, 50, 50)
        tl10 = eng.transmission_loss(10000, 50, 50)
        assert tl10 > tl1

    def test_tl_zero_at_origin(self) -> None:
        eng = _build()
        assert eng.transmission_loss(0, 50, 50) == 0.0


class TestConvergenceZones:
    def test_cz_roughly_55km(self) -> None:
        eng = _build()
        czs = eng.convergence_zone_ranges(100.0)
        assert len(czs) > 0
        assert czs[0] == pytest.approx(55_000, abs=1000)


class TestAmbientNoise:
    def test_noise_increases_with_beaufort(self) -> None:
        eng = _build()
        n0 = eng.ambient_noise(0)
        n5 = eng.ambient_noise(5)
        assert n5 > n0


class TestConditions:
    def test_conditions_complete(self) -> None:
        eng = _build()
        cond = eng.conditions
        assert cond.ambient_noise_level > 0
        assert cond.deep_channel_depth > 0


class TestStateRoundTrip:
    def test_get_set_state(self) -> None:
        eng = _build()
        state = eng.get_state()
        eng2 = _build()
        eng2.set_state(state)
        assert eng2._salinity == eng._salinity
