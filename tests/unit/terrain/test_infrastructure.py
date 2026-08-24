"""Tests for terrain.infrastructure — roads, bridges, buildings, airfields."""

from __future__ import annotations

import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.terrain.infrastructure import (
    Airfield,
    Bridge,
    Building,
    InfrastructureManager,
    Road,
    RoadType,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _sample_infra() -> InfrastructureManager:
    roads = [
        Road(
            road_id="road_01",
            road_type=RoadType.PAVED,
            points=[(0.0, 500.0), (1000.0, 500.0)],
            width=8.0,
        ),
        Road(
            road_id="road_02",
            road_type=RoadType.TRAIL,
            points=[(500.0, 0.0), (500.0, 1000.0)],
            width=4.0,
        ),
    ]
    bridges = [
        Bridge(bridge_id="bridge_01", position=(500.0, 500.0),
               road_id="road_01", capacity_tons=60.0),
    ]
    buildings = [
        Building(
            building_id="bldg_01",
            footprint=[(100.0, 100.0), (200.0, 100.0), (200.0, 200.0), (100.0, 200.0)],
            height=15.0,
        ),
    ]
    airfields = [
        Airfield(airfield_id="af_01", position=(800.0, 800.0), runway_length=2500.0),
    ]
    return InfrastructureManager(
        roads=roads, bridges=bridges, buildings=buildings, airfields=airfields
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRoadQueries:
    def test_roads_near(self) -> None:
        infra = _sample_infra()
        nearby = infra.roads_near(Position(500.0, 500.0), radius=50.0)
        assert len(nearby) == 2  # both roads pass through center

    def test_nearest_road(self) -> None:
        infra = _sample_infra()
        result = infra.nearest_road(Position(500.0, 490.0))
        assert result is not None
        road, dist = result
        assert dist < 15.0

    def test_road_speed_on_road(self) -> None:
        infra = _sample_infra()
        # On road_01 (PAVED, width=8, so within 4m of centerline)
        speed = infra.road_speed_at(Position(500.0, 500.0))
        assert speed is not None
        assert speed > 1.0  # faster than off-road

    def test_road_speed_off_road(self) -> None:
        infra = _sample_infra()
        # Far from both roads (road_01 at y=500, road_02 at x=500)
        speed = infra.road_speed_at(Position(200.0, 300.0))
        assert speed is None

    def test_no_roads(self) -> None:
        infra = InfrastructureManager()
        assert infra.nearest_road(Position(0.0, 0.0)) is None


class TestBuildingQueries:
    def test_building_containment(self) -> None:
        infra = _sample_infra()
        bldgs = infra.buildings_at(Position(150.0, 150.0))
        assert len(bldgs) == 1
        assert bldgs[0].building_id == "bldg_01"

    def test_no_building_outside(self) -> None:
        infra = _sample_infra()
        assert len(infra.buildings_at(Position(500.0, 500.0))) == 0

    def test_buildings_near(self) -> None:
        infra = _sample_infra()
        nearby = infra.buildings_near(Position(250.0, 150.0), radius=100.0)
        assert len(nearby) == 1

    def test_max_building_height(self) -> None:
        infra = _sample_infra()
        h = infra.max_building_height_at(Position(150.0, 150.0))
        assert h == pytest.approx(15.0)

    def test_max_building_height_no_building(self) -> None:
        infra = _sample_infra()
        assert infra.max_building_height_at(Position(500.0, 500.0)) == 0.0


class TestAirfieldQueries:
    def test_airfield_near(self) -> None:
        infra = _sample_infra()
        nearby = infra.airfields_near(Position(800.0, 800.0), radius=100.0)
        assert len(nearby) == 1
        assert nearby[0].airfield_id == "af_01"

    def test_airfield_far(self) -> None:
        infra = _sample_infra()
        assert len(infra.airfields_near(Position(0.0, 0.0), radius=100.0)) == 0


class TestDamageRepair:
    def test_damage_reduces_condition(self) -> None:
        infra = _sample_infra()
        infra.damage("road_01", 0.3)
        road = infra._roads["road_01"]
        assert road.condition == pytest.approx(0.7)

    def test_repair_increases_condition(self) -> None:
        infra = _sample_infra()
        infra.damage("road_01", 0.5)
        infra.repair("road_01", 0.2)
        assert infra._roads["road_01"].condition == pytest.approx(0.7)

    def test_damage_clamps_to_zero(self) -> None:
        infra = _sample_infra()
        infra.damage("bldg_01", 2.0)
        assert infra._buildings["bldg_01"].condition == 0.0

    def test_repair_clamps_to_one(self) -> None:
        infra = _sample_infra()
        infra.repair("road_01", 0.5)
        assert infra._roads["road_01"].condition == 1.0

    def test_destroyed_not_in_queries(self) -> None:
        infra = _sample_infra()
        infra.damage("road_01", 1.0)
        nearby = infra.roads_near(Position(500.0, 500.0), radius=50.0)
        road_ids = [r.road_id for r in nearby]
        assert "road_01" not in road_ids

    def test_unknown_feature_raises(self) -> None:
        infra = _sample_infra()
        with pytest.raises(KeyError):
            infra.damage("nonexistent", 0.5)


class TestStateRoundTrip:
    def test_condition_round_trip(self) -> None:
        infra = _sample_infra()
        infra.damage("road_01", 0.4)
        infra.damage("bldg_01", 0.6)
        state = infra.get_state()

        infra2 = _sample_infra()
        infra2.set_state(state)
        assert infra2._roads["road_01"].condition == pytest.approx(0.6)
        assert infra2._buildings["bldg_01"].condition == pytest.approx(0.4)
