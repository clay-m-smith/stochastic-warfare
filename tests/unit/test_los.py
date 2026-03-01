"""Tests for terrain.los — line-of-sight analysis."""

from __future__ import annotations

import numpy as np
import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.terrain.heightmap import Heightmap, HeightmapConfig
from stochastic_warfare.terrain.infrastructure import Building, InfrastructureManager
from stochastic_warfare.terrain.los import LOSEngine


_CONFIG = HeightmapConfig(origin_easting=0.0, origin_northing=0.0, cell_size=100.0)


def _flat(elevation: float = 0.0) -> Heightmap:
    return Heightmap(np.full((20, 20), elevation, dtype=np.float64), _CONFIG)


def _hill_in_middle() -> Heightmap:
    data = np.zeros((20, 20), dtype=np.float64)
    # Peaked ridge spanning full width, highest at row 10
    data[8, :] = 20.0
    data[9, :] = 50.0
    data[10, :] = 80.0
    data[11, :] = 50.0
    data[12, :] = 20.0
    return Heightmap(data, _CONFIG)


def _valley() -> Heightmap:
    """Observer on one ridge, target on another, valley in between."""
    data = np.zeros((20, 20), dtype=np.float64)
    data[0:5, :] = 100.0  # south ridge
    data[15:20, :] = 100.0  # north ridge
    return Heightmap(data, _CONFIG)


class TestFlatTerrain:
    def test_clear_los_flat(self) -> None:
        los = LOSEngine(_flat())
        result = los.check_los(Position(50.0, 50.0), Position(1950.0, 1950.0))
        assert result.visible

    def test_very_close(self) -> None:
        los = LOSEngine(_flat())
        result = los.check_los(Position(500.0, 500.0), Position(500.5, 500.5))
        assert result.visible


class TestHillBlocking:
    def test_hill_blocks_los(self) -> None:
        los = LOSEngine(_hill_in_middle())
        # Observer at south edge, target at north edge
        observer = Position(500.0, 50.0)
        target = Position(500.0, 1950.0)
        result = los.check_los(observer, target)
        assert not result.visible
        assert result.blocked_by == "terrain"

    def test_observer_on_hill_sees(self) -> None:
        hm = _hill_in_middle()
        los = LOSEngine(hm)
        # Observer on the ridge (row 10, col 10), target on south flat
        observer = Position(1050.0, 1050.0)  # on the ridge, elev=80
        target = Position(1050.0, 50.0)  # south of ridge, elev=0
        result = los.check_los(observer, target, observer_height=2.0)
        assert result.visible


class TestValley:
    def test_ridge_to_ridge_clear(self) -> None:
        hm = _valley()
        los = LOSEngine(hm)
        # Both on ridges, valley below → LOS clear over valley
        observer = Position(500.0, 250.0)  # south ridge
        target = Position(500.0, 1750.0)  # north ridge
        result = los.check_los(observer, target)
        assert result.visible


class TestBuildingBlocking:
    def test_building_blocks(self) -> None:
        hm = _flat()
        # Building at (500, 500), 30m tall
        bldg = Building(
            building_id="b1",
            footprint=[(450, 450), (550, 450), (550, 550), (450, 550)],
            height=30.0,
        )
        infra = InfrastructureManager(buildings=[bldg])
        los = LOSEngine(hm, infra)

        # Observer to the south, target to the north, building in between
        result = los.check_los(Position(500.0, 50.0), Position(500.0, 950.0))
        assert not result.visible
        assert result.blocked_by == "building"


class TestEarthCurvature:
    def test_curvature_at_long_range(self) -> None:
        """At 20+ km on flat terrain, curvature should matter."""
        # Large flat grid
        big_config = HeightmapConfig(cell_size=100.0)
        big_flat = Heightmap(np.zeros((400, 400), dtype=np.float64), big_config)
        los = LOSEngine(big_flat)

        # At 30km, curvature drop ≈ d²/(2kR) ≈ 30000²/(2*4/3*6371000) ≈ 53m
        observer = Position(50.0, 50.0)
        target = Position(50.0, 30050.0)
        # With 1.8m observer height on flat terrain, should be blocked at 30km
        result = los.check_los(observer, target, observer_height=1.8, target_height=0.0)
        assert not result.visible


class TestViewshed:
    def test_viewshed_shape(self) -> None:
        hm = _flat()
        los = LOSEngine(hm)
        vs = los.visible_area(Position(1000.0, 1000.0), max_range=500.0)
        assert vs.shape == hm.shape

    def test_flat_viewshed_circular(self) -> None:
        hm = _flat()
        los = LOSEngine(hm)
        vs = los.visible_area(Position(1000.0, 1000.0), max_range=400.0)
        # Should have some visible cells
        assert vs.sum() > 0


class TestLOSProfile:
    def test_profile_length(self) -> None:
        hm = _flat()
        los = LOSEngine(hm)
        dists, elevs = los.los_profile(Position(50.0, 50.0), Position(950.0, 50.0))
        assert len(dists) == len(elevs)
        assert dists[0] == pytest.approx(0.0)
        assert dists[-1] == pytest.approx(900.0, abs=1.0)
