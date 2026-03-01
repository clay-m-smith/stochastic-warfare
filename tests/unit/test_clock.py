"""Tests for core/clock.py — simulation clock and Julian Date."""

from datetime import datetime, timedelta, timezone

import pytest

from stochastic_warfare.core.clock import SimulationClock


@pytest.fixture
def clock() -> SimulationClock:
    """A clock starting at Desert Storm H-hour."""
    start = datetime(1991, 2, 24, 4, 0, 0, tzinfo=timezone.utc)
    return SimulationClock(start, tick_duration=timedelta(seconds=10))


class TestInit:
    def test_naive_datetime_raises(self) -> None:
        with pytest.raises(ValueError, match="UTC"):
            SimulationClock(datetime(2000, 1, 1), timedelta(seconds=1))

    def test_initial_time(self, clock: SimulationClock) -> None:
        assert clock.current_time == datetime(1991, 2, 24, 4, 0, 0, tzinfo=timezone.utc)

    def test_initial_tick_count(self, clock: SimulationClock) -> None:
        assert clock.tick_count == 0

    def test_initial_elapsed(self, clock: SimulationClock) -> None:
        assert clock.elapsed == timedelta(0)


class TestAdvance:
    def test_single_advance(self, clock: SimulationClock) -> None:
        new = clock.advance()
        assert new == datetime(1991, 2, 24, 4, 0, 10, tzinfo=timezone.utc)
        assert clock.tick_count == 1
        assert clock.elapsed == timedelta(seconds=10)

    def test_multiple_advances(self, clock: SimulationClock) -> None:
        for _ in range(100):
            clock.advance()
        assert clock.tick_count == 100
        assert clock.elapsed == timedelta(seconds=1000)


class TestCalendarQueries:
    def test_day_of_year(self, clock: SimulationClock) -> None:
        # Feb 24 = day 55
        assert clock.day_of_year == 55

    def test_month(self, clock: SimulationClock) -> None:
        assert clock.month == 2

    def test_year(self, clock: SimulationClock) -> None:
        assert clock.year == 1991

    def test_hour_utc(self, clock: SimulationClock) -> None:
        assert clock.hour_utc == 4.0

    def test_hour_utc_fractional(self) -> None:
        start = datetime(2000, 6, 15, 14, 30, 0, tzinfo=timezone.utc)
        c = SimulationClock(start, timedelta(seconds=1))
        assert c.hour_utc == pytest.approx(14.5)


class TestJulianDate:
    def test_j2000_epoch(self) -> None:
        """J2000.0 = 2000-01-01T12:00:00Z = JD 2451545.0."""
        start = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        c = SimulationClock(start, timedelta(seconds=1))
        assert c.julian_date == pytest.approx(2451545.0, abs=1e-6)

    def test_known_date_1(self) -> None:
        """1999-01-01T00:00:00Z = JD 2451179.5."""
        start = datetime(1999, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        c = SimulationClock(start, timedelta(seconds=1))
        assert c.julian_date == pytest.approx(2451179.5, abs=1e-6)

    def test_known_date_2(self) -> None:
        """1987-01-27T00:00:00Z = JD 2446822.5 (Meeus example)."""
        start = datetime(1987, 1, 27, 0, 0, 0, tzinfo=timezone.utc)
        c = SimulationClock(start, timedelta(seconds=1))
        assert c.julian_date == pytest.approx(2446822.5, abs=1e-6)


class TestVariableTickResolution:
    def test_change_tick_duration(self, clock: SimulationClock) -> None:
        clock.advance()  # 10s tick
        clock.set_tick_duration(timedelta(minutes=5))
        clock.advance()  # 5m tick
        expected = datetime(1991, 2, 24, 4, 5, 10, tzinfo=timezone.utc)
        assert clock.current_time == expected
        assert clock.tick_count == 2


class TestStateRoundTrip:
    def test_save_restore(self, clock: SimulationClock) -> None:
        for _ in range(10):
            clock.advance()
        state = clock.get_state()

        # Create a new clock, restore into it
        other = SimulationClock(
            datetime(2020, 1, 1, tzinfo=timezone.utc), timedelta(seconds=1)
        )
        other.set_state(state)

        assert other.current_time == clock.current_time
        assert other.tick_count == clock.tick_count
        assert other.elapsed == clock.elapsed
        assert other.tick_duration == clock.tick_duration
