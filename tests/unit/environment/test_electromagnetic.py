"""Tests for environment.electromagnetic — RF propagation model."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.environment.astronomy import AstronomyEngine
from stochastic_warfare.environment.electromagnetic import EMEnvironment, FrequencyBand
from stochastic_warfare.environment.sea_state import SeaStateConfig, SeaStateEngine
from stochastic_warfare.environment.weather import WeatherConfig, WeatherEngine


def _build(dt: datetime | None = None) -> EMEnvironment:
    if dt is None:
        dt = datetime(2020, 6, 21, 12, 0, tzinfo=timezone.utc)
    clock = SimulationClock(dt, timedelta(hours=1))
    rng_mgr = RNGManager(42)
    rng = rng_mgr.get_stream(ModuleId.ENVIRONMENT)
    weather = WeatherEngine(WeatherConfig(), clock, rng)
    astro = AstronomyEngine(clock)
    sea = SeaStateEngine(SeaStateConfig(), clock, astro, weather, rng_mgr.get_stream(ModuleId.TERRAIN))
    return EMEnvironment(weather, sea, clock)


class TestFSPL:
    def test_known_value(self) -> None:
        """FSPL at 1 GHz, 10 km: 20*log10(10) + 20*log10(1000) + 32.45 ≈ 112.45 dB."""
        em = _build()
        fspl = em.free_space_path_loss(1000.0, 10.0)
        assert fspl == pytest.approx(112.45, abs=0.01)

    def test_increases_with_range(self) -> None:
        em = _build()
        near = em.free_space_path_loss(1000.0, 1.0)
        far = em.free_space_path_loss(1000.0, 100.0)
        assert far > near

    def test_increases_with_frequency(self) -> None:
        em = _build()
        low = em.free_space_path_loss(100.0, 10.0)
        high = em.free_space_path_loss(10000.0, 10.0)
        assert high > low


class TestRadarHorizon:
    def test_known_antenna_height(self) -> None:
        """10m antenna: horizon ≈ sqrt(2 * 4/3 * 6371000 * 10) ≈ 13km."""
        em = _build()
        horizon = em.radar_horizon(10.0)
        assert 10_000 < horizon < 20_000  # 10-20 km

    def test_higher_sees_farther(self) -> None:
        em = _build()
        low = em.radar_horizon(5.0)
        high = em.radar_horizon(30.0)
        assert high > low


class TestHFPropagation:
    def test_night_better_than_day(self) -> None:
        day = _build(datetime(2020, 6, 21, 12, 0, tzinfo=timezone.utc))
        night = _build(datetime(2020, 6, 21, 0, 0, tzinfo=timezone.utc))
        assert night.hf_propagation_quality() > day.hf_propagation_quality()

    def test_quality_bounded(self) -> None:
        em = _build()
        assert 0 <= em.hf_propagation_quality() <= 1


class TestGPS:
    def test_baseline_accuracy(self) -> None:
        em = _build()
        acc = em.gps_accuracy()
        assert 3 < acc < 15  # metres


class TestPropagation:
    def test_propagation_complete(self) -> None:
        em = _build()
        cond = em.propagation(FrequencyBand.UHF, 50.0)
        assert cond.free_space_loss > 0
        assert cond.refraction_factor > 1


class TestStatePersistence:
    def test_default_state(self) -> None:
        em = _build()
        state = em.get_state()
        assert state["gps_jam_degradation_m"] == 0.0
        assert state["gps_spoof_offset"] == [0.0, 0.0]

    def test_state_roundtrip(self) -> None:
        em = _build()
        em.set_gps_jam_degradation(10.0)
        em.set_gps_spoof_offset(50.0, -30.0)
        state = em.get_state()

        em2 = _build()
        em2.set_state(state)
        assert em2._gps_jam_degradation_m == 10.0
        assert em2.gps_spoof_offset == (50.0, -30.0)
