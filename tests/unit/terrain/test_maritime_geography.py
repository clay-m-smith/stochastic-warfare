"""Tests for terrain.maritime_geography — ports, straits, sea lanes, anchorages."""

from __future__ import annotations

import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.terrain.maritime_geography import (
    Anchorage,
    MaritimeGeography,
    Port,
    SeaLane,
    Strait,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_COASTLINE = [
    (100.0, 100.0), (900.0, 100.0), (900.0, 900.0), (100.0, 900.0),
]


def _maritime() -> MaritimeGeography:
    ports = [
        Port(port_id="port_01", name="Main Harbor",
             position=(200.0, 200.0), max_draft=12.0),
    ]
    straits = [
        Strait(strait_id="strait_01", name="Narrow Passage",
               centerline=[(400.0, 400.0), (600.0, 400.0)],
               width=100.0, depth=20.0),
    ]
    sea_lanes = [
        SeaLane(lane_id="sl_01", name="Shipping Route",
                waypoints=[(200.0, 500.0), (800.0, 500.0)]),
    ]
    anchorages = [
        Anchorage(anchorage_id="anch_01", position=(300.0, 300.0),
                  radius=50.0, max_draft=10.0, shelter_factor=0.8),
    ]
    return MaritimeGeography(
        coastline=_COASTLINE, ports=ports, straits=straits,
        sea_lanes=sea_lanes, anchorages=anchorages,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCoastline:
    def test_sea_inside(self) -> None:
        mg = _maritime()
        assert mg.is_sea(Position(500.0, 500.0))

    def test_land_outside(self) -> None:
        mg = _maritime()
        assert not mg.is_sea(Position(50.0, 50.0))

    def test_all_sea_when_no_coastline(self) -> None:
        mg = MaritimeGeography()
        assert mg.is_sea(Position(0.0, 0.0))


class TestPortQueries:
    def test_nearest_port(self) -> None:
        mg = _maritime()
        result = mg.nearest_port(Position(210.0, 210.0))
        assert result is not None
        port, dist = result
        assert port.port_id == "port_01"
        assert dist < 20.0

    def test_ports_within(self) -> None:
        mg = _maritime()
        ports = mg.ports_within(Position(200.0, 200.0), radius=100.0)
        assert len(ports) == 1

    def test_no_ports_far(self) -> None:
        mg = _maritime()
        assert len(mg.ports_within(Position(800.0, 800.0), radius=50.0)) == 0


class TestStraitQueries:
    def test_in_strait(self) -> None:
        mg = _maritime()
        result = mg.strait_at(Position(500.0, 400.0))
        assert result is not None
        assert result.strait_id == "strait_01"

    def test_not_in_strait(self) -> None:
        mg = _maritime()
        assert mg.strait_at(Position(200.0, 200.0)) is None


class TestSeaLaneQueries:
    def test_nearest_sea_lane(self) -> None:
        mg = _maritime()
        result = mg.nearest_sea_lane(Position(500.0, 510.0))
        assert result is not None
        lane, dist = result
        assert lane.lane_id == "sl_01"
        assert dist < 15.0


class TestAnchorageQueries:
    def test_anchorage_near(self) -> None:
        mg = _maritime()
        nearby = mg.anchorages_near(Position(310.0, 310.0), radius=50.0)
        assert len(nearby) == 1

    def test_anchorage_far(self) -> None:
        mg = _maritime()
        assert len(mg.anchorages_near(Position(800.0, 800.0), radius=50.0)) == 0


class TestPortDamage:
    def test_damage_port(self) -> None:
        mg = _maritime()
        mg.damage_port("port_01", 0.4)
        result = mg.nearest_port(Position(200.0, 200.0))
        assert result is not None
        assert result[0].condition == pytest.approx(0.6)

    def test_destroyed_port_not_in_queries(self) -> None:
        mg = _maritime()
        mg.damage_port("port_01", 1.0)
        assert mg.nearest_port(Position(200.0, 200.0)) is None

    def test_unknown_port_raises(self) -> None:
        mg = _maritime()
        with pytest.raises(KeyError):
            mg.damage_port("nonexistent", 0.5)


class TestStateRoundTrip:
    def test_port_condition_round_trip(self) -> None:
        mg1 = _maritime()
        mg1.damage_port("port_01", 0.3)
        state = mg1.get_state()

        mg2 = _maritime()
        mg2.set_state(state)
        result = mg2.nearest_port(Position(200.0, 200.0))
        assert result is not None
        assert result[0].condition == pytest.approx(0.7)
