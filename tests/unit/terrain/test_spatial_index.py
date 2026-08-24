"""Phase 13a-2: STRtree spatial indexing tests."""


import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.terrain.infrastructure import (
    Airfield,
    Building,
    InfrastructureManager,
    Road,
    RoadType,
)


def _make_road(road_id: str, points: list[tuple[float, float]], **kw) -> Road:
    return Road(road_id=road_id, road_type=RoadType.PAVED, points=points, **kw)


def _make_building(building_id: str, cx: float, cy: float, size: float = 20.0, **kw) -> Building:
    hs = size / 2
    return Building(
        building_id=building_id,
        footprint=[(cx - hs, cy - hs), (cx + hs, cy - hs), (cx + hs, cy + hs), (cx - hs, cy + hs)],
        **kw,
    )


class TestSTRtreeRoads:
    def test_roads_near_basic(self):
        roads = [
            _make_road("r1", [(0, 0), (1000, 0)]),
            _make_road("r2", [(0, 5000), (1000, 5000)]),
        ]
        mgr = InfrastructureManager(roads=roads)
        result = mgr.roads_near(Position(500, 0), 100.0)
        assert len(result) == 1
        assert result[0].road_id == "r1"

    def test_roads_near_empty(self):
        mgr = InfrastructureManager()
        assert mgr.roads_near(Position(0, 0), 100.0) == []

    def test_roads_near_filters_destroyed(self):
        roads = [_make_road("r1", [(0, 0), (1000, 0)], condition=0.0)]
        mgr = InfrastructureManager(roads=roads)
        assert mgr.roads_near(Position(500, 0), 100.0) == []

    def test_nearest_road_basic(self):
        roads = [
            _make_road("r1", [(0, 0), (1000, 0)]),
            _make_road("r2", [(0, 500), (1000, 500)]),
        ]
        mgr = InfrastructureManager(roads=roads)
        result = mgr.nearest_road(Position(500, 100))
        assert result is not None
        assert result[0].road_id == "r1"
        assert result[1] == pytest.approx(100.0, abs=1.0)

    def test_nearest_road_empty(self):
        mgr = InfrastructureManager()
        assert mgr.nearest_road(Position(0, 0)) is None

    def test_nearest_road_skips_destroyed(self):
        roads = [
            _make_road("r1", [(0, 0), (1000, 0)], condition=0.0),
            _make_road("r2", [(0, 500), (1000, 500)]),
        ]
        mgr = InfrastructureManager(roads=roads)
        result = mgr.nearest_road(Position(500, 100))
        assert result is not None
        assert result[0].road_id == "r2"


class TestSTRtreeBuildings:
    def test_buildings_at_basic(self):
        buildings = [_make_building("b1", 500, 500)]
        mgr = InfrastructureManager(buildings=buildings)
        result = mgr.buildings_at(Position(500, 500))
        assert len(result) == 1
        assert result[0].building_id == "b1"

    def test_buildings_at_outside(self):
        buildings = [_make_building("b1", 500, 500, size=20)]
        mgr = InfrastructureManager(buildings=buildings)
        result = mgr.buildings_at(Position(0, 0))
        assert len(result) == 0

    def test_buildings_at_filters_destroyed(self):
        buildings = [_make_building("b1", 500, 500, condition=0.0)]
        mgr = InfrastructureManager(buildings=buildings)
        result = mgr.buildings_at(Position(500, 500))
        assert len(result) == 0

    def test_buildings_near_basic(self):
        buildings = [
            _make_building("b1", 100, 100),
            _make_building("b2", 5000, 5000),
        ]
        mgr = InfrastructureManager(buildings=buildings)
        result = mgr.buildings_near(Position(100, 100), 500.0)
        assert len(result) == 1
        assert result[0].building_id == "b1"

    def test_buildings_near_empty(self):
        mgr = InfrastructureManager()
        assert mgr.buildings_near(Position(0, 0), 100.0) == []


class TestSTRtreeAirfields:
    def test_airfields_near_basic(self):
        airfields = [
            Airfield(airfield_id="af1", position=(1000, 1000)),
            Airfield(airfield_id="af2", position=(50000, 50000)),
        ]
        mgr = InfrastructureManager(airfields=airfields)
        result = mgr.airfields_near(Position(1000, 1000), 5000.0)
        assert len(result) == 1
        assert result[0].airfield_id == "af1"

    def test_airfields_near_empty(self):
        mgr = InfrastructureManager()
        assert mgr.airfields_near(Position(0, 0), 100.0) == []

    def test_airfields_near_filters_destroyed(self):
        airfields = [Airfield(airfield_id="af1", position=(100, 100), condition=0.0)]
        mgr = InfrastructureManager(airfields=airfields)
        result = mgr.airfields_near(Position(100, 100), 5000.0)
        assert len(result) == 0
