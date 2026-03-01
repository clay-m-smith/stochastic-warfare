"""Tests for terrain.classification — land-cover and soil layers."""

from __future__ import annotations

import numpy as np
import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.terrain.classification import (
    DEFAULT_PROPERTIES,
    ClassificationConfig,
    LandCover,
    SoilType,
    TerrainClassification,
    TerrainProperties,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CONFIG = ClassificationConfig(origin_easting=0.0, origin_northing=0.0, cell_size=100.0)


def _uniform(lc: LandCover = LandCover.GRASSLAND, soil: SoilType = SoilType.LOAM,
             rows: int = 10, cols: int = 10) -> TerrainClassification:
    lc_grid = np.full((rows, cols), lc.value, dtype=np.int32)
    soil_grid = np.full((rows, cols), soil.value, dtype=np.int32)
    return TerrainClassification(lc_grid, soil_grid, _CONFIG)


def _mixed() -> TerrainClassification:
    """4x4 grid with different land covers."""
    lc = np.array([
        [LandCover.OPEN, LandCover.GRASSLAND, LandCover.FOREST_DECIDUOUS, LandCover.WATER],
        [LandCover.OPEN, LandCover.URBAN_DENSE, LandCover.FOREST_CONIFEROUS, LandCover.WATER],
        [LandCover.DESERT_SAND, LandCover.URBAN_SUBURBAN, LandCover.SHRUBLAND, LandCover.WETLAND],
        [LandCover.DESERT_ROCK, LandCover.CULTIVATED, LandCover.SNOW_ICE, LandCover.FOREST_MIXED],
    ], dtype=np.int32)
    soil = np.full((4, 4), SoilType.LOAM, dtype=np.int32)
    return TerrainClassification(lc, soil, _CONFIG)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLandCoverQueries:
    def test_uniform_grassland(self) -> None:
        tc = _uniform(LandCover.GRASSLAND)
        assert tc.land_cover_at(Position(50.0, 50.0)) == LandCover.GRASSLAND

    def test_mixed_grid(self) -> None:
        tc = _mixed()
        # Cell (0,0) = OPEN, centre at (50, 50)
        assert tc.land_cover_at(Position(50.0, 50.0)) == LandCover.OPEN
        # Cell (0,3) = WATER, centre at (350, 50)
        assert tc.land_cover_at(Position(350.0, 50.0)) == LandCover.WATER
        # Cell (3,3) = FOREST_MIXED, centre at (350, 350)
        assert tc.land_cover_at(Position(350.0, 350.0)) == LandCover.FOREST_MIXED


class TestSoilQueries:
    def test_uniform_soil(self) -> None:
        tc = _uniform(soil=SoilType.CLAY)
        assert tc.soil_at(Position(50.0, 50.0)) == SoilType.CLAY

    def test_different_soils(self) -> None:
        lc = np.full((2, 2), LandCover.OPEN, dtype=np.int32)
        soil = np.array([[SoilType.SAND, SoilType.CLAY],
                         [SoilType.ROCK, SoilType.GRAVEL]], dtype=np.int32)
        tc = TerrainClassification(lc, soil, _CONFIG)
        assert tc.soil_at(Position(50.0, 50.0)) == SoilType.SAND
        assert tc.soil_at(Position(150.0, 150.0)) == SoilType.GRAVEL


class TestProperties:
    def test_properties_lookup(self) -> None:
        tc = _uniform(LandCover.FOREST_DECIDUOUS)
        props = tc.properties_at(Position(50.0, 50.0))
        assert props.land_cover == LandCover.FOREST_DECIDUOUS
        assert props.concealment == pytest.approx(0.9)
        assert props.cover == pytest.approx(0.5)
        assert props.base_trafficability == pytest.approx(0.3)

    def test_water_impassable(self) -> None:
        tc = _uniform(LandCover.WATER)
        assert tc.trafficability_at(Position(50.0, 50.0)) == pytest.approx(0.0)

    def test_concealment_vs_cover(self) -> None:
        """Concealment (visual hiding) and cover (ballistic protection) differ."""
        # Grassland: concealment 0.2, cover 0.0
        tc = _uniform(LandCover.GRASSLAND)
        props = tc.properties_at(Position(50.0, 50.0))
        assert props.concealment > props.cover

    def test_all_land_covers_have_defaults(self) -> None:
        for lc in LandCover:
            assert lc in DEFAULT_PROPERTIES

    def test_custom_properties_table(self) -> None:
        custom = dict(DEFAULT_PROPERTIES)
        custom[LandCover.OPEN] = TerrainProperties(
            LandCover.OPEN, SoilType.LOAM, 0.5, 0.5, 0.5, 5.0, 0.5
        )
        tc = _uniform(LandCover.OPEN, properties_table=custom)
        assert tc.trafficability_at(Position(50.0, 50.0)) == pytest.approx(0.5)


def _uniform(lc: LandCover = LandCover.GRASSLAND, soil: SoilType = SoilType.LOAM,
             rows: int = 10, cols: int = 10,
             properties_table: dict | None = None) -> TerrainClassification:
    lc_grid = np.full((rows, cols), lc.value, dtype=np.int32)
    soil_grid = np.full((rows, cols), soil.value, dtype=np.int32)
    return TerrainClassification(lc_grid, soil_grid, _CONFIG, properties_table)


class TestGridGeometry:
    def test_shape(self) -> None:
        tc = _uniform(rows=5, cols=8)
        assert tc.shape == (5, 8)

    def test_cell_size(self) -> None:
        tc = _uniform()
        assert tc.cell_size == 100.0

    def test_grid_to_enu(self) -> None:
        tc = _uniform()
        pos = tc.grid_to_enu(0, 0)
        assert pos.easting == pytest.approx(50.0)
        assert pos.northing == pytest.approx(50.0)

    def test_enu_to_grid_round_trip(self) -> None:
        tc = _uniform()
        for r in range(10):
            for c in range(10):
                pos = tc.grid_to_enu(r, c)
                r2, c2 = tc.enu_to_grid(pos)
                assert (r2, c2) == (r, c)


class TestStateRoundTrip:
    def test_get_set_state(self) -> None:
        tc1 = _mixed()
        state = tc1.get_state()

        tc2 = _uniform()
        tc2.set_state(state)

        pos = Position(350.0, 350.0)
        assert tc2.land_cover_at(pos) == tc1.land_cover_at(pos)
        assert tc2.soil_at(pos) == tc1.soil_at(pos)


class TestValidation:
    def test_shape_mismatch_raises(self) -> None:
        lc = np.zeros((3, 3), dtype=np.int32)
        soil = np.zeros((4, 4), dtype=np.int32)
        with pytest.raises(ValueError, match="same shape"):
            TerrainClassification(lc, soil, _CONFIG)
