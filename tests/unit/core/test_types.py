"""Tests for core/types.py — shared types and constants."""

from stochastic_warfare.core.types import (
    EARTH_MEAN_RADIUS,
    SPEED_OF_LIGHT,
    STANDARD_GRAVITY,
    STANDARD_LAPSE_RATE,
    GeodeticPosition,
    ModuleId,
    Position,
    TickResolution,
)


class TestPosition:
    def test_construction(self) -> None:
        p = Position(100.0, 200.0, 50.0)
        assert p.easting == 100.0
        assert p.northing == 200.0
        assert p.altitude == 50.0

    def test_default_altitude(self) -> None:
        p = Position(1.0, 2.0)
        assert p.altitude == 0.0

    def test_immutable(self) -> None:
        p = Position(1.0, 2.0, 3.0)
        try:
            p.easting = 99.0  # type: ignore[misc]
            assert False, "Should have raised"
        except AttributeError:
            pass

    def test_tuple_unpacking(self) -> None:
        e, n, a = Position(10.0, 20.0, 30.0)
        assert (e, n, a) == (10.0, 20.0, 30.0)


class TestGeodeticPosition:
    def test_construction(self) -> None:
        g = GeodeticPosition(34.05, -118.25, 100.0)
        assert g.latitude == 34.05
        assert g.longitude == -118.25
        assert g.altitude == 100.0

    def test_default_altitude(self) -> None:
        g = GeodeticPosition(0.0, 0.0)
        assert g.altitude == 0.0

    def test_immutable(self) -> None:
        g = GeodeticPosition(1.0, 2.0, 3.0)
        try:
            g.latitude = 99.0  # type: ignore[misc]
            assert False, "Should have raised"
        except AttributeError:
            pass


class TestModuleId:
    def test_all_members(self) -> None:
        expected = {
            "CORE", "COMBAT", "MOVEMENT", "DETECTION", "MORALE",
            "ENVIRONMENT", "LOGISTICS", "C2", "ENTITIES", "TERRAIN",
            "POPULATION", "AIR_CAMPAIGN", "EW", "SPACE", "CBRN",
            "ESCALATION",
        }
        assert {m.name for m in ModuleId} == expected

    def test_string_value(self) -> None:
        assert ModuleId.COMBAT == "combat"
        assert ModuleId.C2 == "c2"


class TestTickResolution:
    def test_members(self) -> None:
        assert TickResolution.SECONDS.value == "seconds"
        assert TickResolution.MINUTES.value == "minutes"
        assert TickResolution.HOURS.value == "hours"


class TestConstants:
    def test_speed_of_light(self) -> None:
        assert SPEED_OF_LIGHT == 299_792_458.0

    def test_standard_gravity(self) -> None:
        assert STANDARD_GRAVITY == 9.80665

    def test_earth_radius(self) -> None:
        assert EARTH_MEAN_RADIUS == 6_371_000.0

    def test_lapse_rate(self) -> None:
        assert STANDARD_LAPSE_RATE == 0.0065
