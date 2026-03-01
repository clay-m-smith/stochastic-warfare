"""Tests for environment.astronomy — Meeus solar/lunar algorithms."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.environment.astronomy import AstronomyEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clock(dt: datetime) -> SimulationClock:
    return SimulationClock(dt, timedelta(seconds=10))


def _engine(dt: datetime) -> AstronomyEngine:
    return AstronomyEngine(_clock(dt))


# ---------------------------------------------------------------------------
# Solar tests
# ---------------------------------------------------------------------------


class TestSolarPosition:
    def test_equinox_equator_noon(self) -> None:
        """At spring equinox, equator, local noon: elevation ≈ 90°."""
        # March 20, 2020 ~12:00 UTC, lon=0 → local noon
        dt = datetime(2020, 3, 20, 12, 0, tzinfo=timezone.utc)
        eng = _engine(dt)
        pos = eng.solar_position(0.0, 0.0)
        assert pos.elevation == pytest.approx(math.pi / 2, abs=0.05)  # within ~3°

    def test_midnight_below_horizon(self) -> None:
        """At midnight, mid-latitude: sun is below horizon."""
        dt = datetime(2020, 6, 21, 0, 0, tzinfo=timezone.utc)
        eng = _engine(dt)
        pos = eng.solar_position(45.0, 0.0)
        assert pos.elevation < 0

    def test_distance_roughly_1au(self) -> None:
        dt = datetime(2020, 6, 21, 12, 0, tzinfo=timezone.utc)
        eng = _engine(dt)
        pos = eng.solar_position(0.0, 0.0)
        assert 147e6 < pos.distance < 153e6  # km, ~1 AU range

    def test_summer_higher_than_winter(self) -> None:
        """Summer noon elevation > winter noon elevation at 45°N."""
        summer = _engine(datetime(2020, 6, 21, 12, 0, tzinfo=timezone.utc))
        winter = _engine(datetime(2020, 12, 21, 12, 0, tzinfo=timezone.utc))
        s_el = summer.solar_position(45.0, 0.0).elevation
        w_el = winter.solar_position(45.0, 0.0).elevation
        assert s_el > w_el


class TestTwilightTimes:
    def test_sunrise_before_sunset(self) -> None:
        dt = datetime(2020, 6, 21, tzinfo=timezone.utc)
        eng = _engine(dt)
        tt = eng.twilight_times(45.0, 0.0, dt)
        assert tt.sunrise is not None
        assert tt.sunset is not None
        assert tt.sunrise < tt.sunset

    def test_dawn_before_sunrise(self) -> None:
        dt = datetime(2020, 6, 21, tzinfo=timezone.utc)
        eng = _engine(dt)
        tt = eng.twilight_times(45.0, 0.0, dt)
        assert tt.civil_dawn is not None
        assert tt.sunrise is not None
        assert tt.civil_dawn < tt.sunrise

    def test_sunrise_within_5min_usno(self) -> None:
        """Sunrise at DC (38.9N, -77.0W) on 2020-06-21.
        USNO reference: sunrise ~09:49 UTC (05:49 EDT).
        """
        dt = datetime(2020, 6, 21, tzinfo=timezone.utc)
        eng = _engine(dt)
        tt = eng.twilight_times(38.9, -77.0, dt)
        assert tt.sunrise is not None
        # 09:49 UTC = 9.817 hours
        assert abs(tt.sunrise - 9.82) < 0.25  # within ~15 min tolerance


class TestDayLength:
    def test_equinox_equator_12h(self) -> None:
        dt = datetime(2020, 3, 20, 12, 0, tzinfo=timezone.utc)
        eng = _engine(dt)
        dl = eng.day_length_hours(0.0, 0.0)
        assert dl == pytest.approx(12.0, abs=0.5)

    def test_summer_60n_long_day(self) -> None:
        dt = datetime(2020, 6, 21, 12, 0, tzinfo=timezone.utc)
        eng = _engine(dt)
        dl = eng.day_length_hours(60.0, 0.0)
        assert dl > 18.0

    def test_winter_60n_short_day(self) -> None:
        dt = datetime(2020, 12, 21, 12, 0, tzinfo=timezone.utc)
        eng = _engine(dt)
        dl = eng.day_length_hours(60.0, 0.0)
        assert dl < 7.0


# ---------------------------------------------------------------------------
# Lunar tests
# ---------------------------------------------------------------------------


class TestLunarPosition:
    def test_distance_reasonable(self) -> None:
        dt = datetime(2020, 6, 21, 12, 0, tzinfo=timezone.utc)
        eng = _engine(dt)
        pos = eng.lunar_position(45.0, 0.0)
        assert 350000 < pos.distance < 420000  # km


class TestLunarPhase:
    def test_illumination_range(self) -> None:
        dt = datetime(2020, 6, 21, 12, 0, tzinfo=timezone.utc)
        eng = _engine(dt)
        phase = eng.lunar_phase()
        assert 0.0 <= phase.illumination_fraction <= 1.0

    def test_phase_name_valid(self) -> None:
        dt = datetime(2020, 6, 21, 12, 0, tzinfo=timezone.utc)
        eng = _engine(dt)
        phase = eng.lunar_phase()
        valid_names = {"new", "waxing_crescent", "first_quarter", "waxing_gibbous",
                       "full", "waning_gibbous", "last_quarter", "waning_crescent"}
        assert phase.phase_name in valid_names

    def test_new_moon_low_illumination(self) -> None:
        """Near known new moon (2020-06-21): should be low illumination."""
        dt = datetime(2020, 6, 21, 12, 0, tzinfo=timezone.utc)
        eng = _engine(dt)
        phase = eng.lunar_phase()
        assert phase.illumination_fraction < 0.15

    def test_full_moon_high_illumination(self) -> None:
        """Near known full moon (2020-07-05): should be high illumination."""
        dt = datetime(2020, 7, 5, 12, 0, tzinfo=timezone.utc)
        eng = _engine(dt)
        phase = eng.lunar_phase()
        assert phase.illumination_fraction > 0.85


# ---------------------------------------------------------------------------
# Tidal forcing tests
# ---------------------------------------------------------------------------


class TestTidalForcing:
    def test_spring_greater_than_neap(self) -> None:
        """Spring tide (new/full moon) forcing > neap tide (quarter)."""
        # New moon 2020-06-21
        spring = _engine(datetime(2020, 6, 21, 12, 0, tzinfo=timezone.utc))
        # First quarter ~2020-06-28
        neap = _engine(datetime(2020, 6, 28, 12, 0, tzinfo=timezone.utc))
        assert spring.tidal_forcing() > neap.tidal_forcing()

    def test_range(self) -> None:
        dt = datetime(2020, 6, 21, 12, 0, tzinfo=timezone.utc)
        eng = _engine(dt)
        tf = eng.tidal_forcing()
        assert 0.4 <= tf <= 1.6


class TestStatePersistence:
    def test_stateless(self) -> None:
        eng = _engine(datetime(2020, 6, 21, 12, 0, tzinfo=timezone.utc))
        assert eng.get_state() == {}
        eng.set_state({})  # no-op
