"""Tests for environment.obscurants — smoke, dust, fog."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.environment.astronomy import AstronomyEngine
from stochastic_warfare.environment.obscurants import ObscurantsEngine
from stochastic_warfare.environment.time_of_day import TimeOfDayEngine
from stochastic_warfare.environment.weather import WeatherConfig, WeatherEngine


def _build() -> tuple[ObscurantsEngine, WeatherEngine, SimulationClock]:
    dt = datetime(2020, 6, 21, 12, 0, tzinfo=timezone.utc)
    clock = SimulationClock(dt, timedelta(minutes=1))
    rng_mgr = RNGManager(42)
    rng = rng_mgr.get_stream(ModuleId.ENVIRONMENT)
    weather = WeatherEngine(WeatherConfig(), clock, rng)
    astro = AstronomyEngine(clock)
    tod = TimeOfDayEngine(astro, weather, clock)
    obs = ObscurantsEngine(weather, tod, clock, rng_mgr.get_stream(ModuleId.TERRAIN))
    return obs, weather, clock


class TestSmokeDeployment:
    def test_opacity_at_center(self) -> None:
        obs, _, _ = _build()
        obs.deploy_smoke(Position(500.0, 500.0), radius=100.0)
        opacity = obs.opacity_at(Position(500.0, 500.0))
        assert opacity.visual > 0.5

    def test_opacity_at_edge_less(self) -> None:
        obs, _, _ = _build()
        obs.deploy_smoke(Position(500.0, 500.0), radius=100.0)
        center = obs.opacity_at(Position(500.0, 500.0))
        edge = obs.opacity_at(Position(580.0, 500.0))
        assert edge.visual < center.visual

    def test_opacity_outside_zero(self) -> None:
        obs, _, _ = _build()
        obs.deploy_smoke(Position(500.0, 500.0), radius=100.0)
        outside = obs.opacity_at(Position(800.0, 800.0))
        assert outside.visual == pytest.approx(0.0)


class TestSpectralBlocking:
    def test_regular_smoke_visual_only(self) -> None:
        obs, _, _ = _build()
        obs.deploy_smoke(Position(500.0, 500.0), radius=100.0, multispectral=False)
        opacity = obs.opacity_at(Position(500.0, 500.0))
        assert opacity.visual > 0.5
        assert opacity.thermal < 0.2

    def test_multispectral_blocks_thermal(self) -> None:
        obs, _, _ = _build()
        obs.deploy_smoke(Position(500.0, 500.0), radius=100.0, multispectral=True)
        opacity = obs.opacity_at(Position(500.0, 500.0))
        assert opacity.visual > 0.5
        assert opacity.thermal > 0.3

    def test_dust_blocks_all(self) -> None:
        obs, _, _ = _build()
        obs.add_dust(Position(500.0, 500.0), radius=100.0)
        opacity = obs.opacity_at(Position(500.0, 500.0))
        assert opacity.visual > 0.3
        assert opacity.radar > 0.1


class TestDriftAndDecay:
    def test_drift_with_wind(self) -> None:
        obs, weather, clock = _build()
        cid = obs.deploy_smoke(Position(500.0, 500.0), radius=50.0)
        initial_e = obs._clouds[cid].center_e

        for _ in range(60):  # 60 minutes
            obs.update(60)
            clock.advance()

        # Cloud should have moved
        assert obs._clouds[cid].center_e != initial_e

    def test_dissipation(self) -> None:
        obs, weather, clock = _build()
        obs.deploy_smoke(Position(500.0, 500.0), radius=50.0)

        # Advance 2 hours (smoke half-life = 30 min)
        for _ in range(120):
            obs.update(60)
            clock.advance()

        opacity = obs.opacity_at(Position(500.0, 500.0))
        # After 4 half-lives, density < 0.1 → very low opacity
        assert opacity.visual < 0.5


class TestVisibility:
    def test_smoke_reduces_visibility(self) -> None:
        obs, weather, _ = _build()
        base_vis = obs.visibility_at(Position(500.0, 500.0))
        obs.deploy_smoke(Position(500.0, 500.0), radius=100.0)
        smoke_vis = obs.visibility_at(Position(500.0, 500.0))
        assert smoke_vis < base_vis


class TestStateRoundTrip:
    def test_get_set_state(self) -> None:
        obs1, _, _ = _build()
        obs1.deploy_smoke(Position(500.0, 500.0), radius=100.0)
        obs1.add_dust(Position(300.0, 300.0), radius=50.0)
        state = obs1.get_state()

        obs2, _, _ = _build()
        obs2.set_state(state)
        assert len(obs2._clouds) == 2
