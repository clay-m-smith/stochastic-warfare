"""Phase 15b tests — Copernicus classification + OSM infrastructure loaders."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from stochastic_warfare.terrain.data_pipeline import BoundingBox
from stochastic_warfare.terrain.classification import LandCover, SoilType
from stochastic_warfare.terrain.infrastructure import RoadType


# ── Helpers ───────────────────────────────────────────────────────────────


def _make_copernicus_tif(
    path: Path,
    data: np.ndarray,
    bounds: tuple[float, float, float, float],
) -> None:
    """Write synthetic Copernicus land cover GeoTIFF (uint8 codes)."""
    import rasterio
    from rasterio.transform import from_bounds

    rows, cols = data.shape
    west, south, east, north = bounds
    transform = from_bounds(west, south, east, north, cols, rows)

    with rasterio.open(
        str(path),
        "w",
        driver="GTiff",
        height=rows,
        width=cols,
        count=1,
        dtype="uint8",
        crs="EPSG:4326",
        transform=transform,
    ) as dst:
        # GeoTIFF: row 0 = north → write data reversed (our data is south-up)
        dst.write(data[::-1].astype(np.uint8), 1)


def _make_roads_geojson(path: Path, features: list[dict]) -> None:
    """Write a GeoJSON FeatureCollection."""
    collection = {"type": "FeatureCollection", "features": features}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(collection, f)


def _road_feature(
    coords: list[list[float]],
    highway: str = "primary",
    bridge: str | None = None,
) -> dict:
    """Create a GeoJSON road feature."""
    props = {"highway": highway}
    if bridge is not None:
        props["bridge"] = bridge
    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": coords},
        "properties": props,
    }


def _building_feature(
    coords: list[list[list[float]]],
    building: str = "yes",
    height: float | None = None,
) -> dict:
    """Create a GeoJSON building feature."""
    props: dict = {"building": building}
    if height is not None:
        props["height"] = str(height)
    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": coords},
        "properties": props,
    }


def _rail_feature(
    coords: list[list[float]],
    railway: str = "rail",
) -> dict:
    """Create a GeoJSON railway feature."""
    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": coords},
        "properties": {"railway": railway},
    }


@pytest.fixture
def bbox() -> BoundingBox:
    return BoundingBox(south=32.9, west=35.7, north=33.1, east=35.9)


@pytest.fixture
def projection():
    from stochastic_warfare.coordinates.transforms import ScenarioProjection
    return ScenarioProjection(33.0, 35.8)


# ── Classification Tests ─────────────────────────────────────────────────


class TestCopernicusMapping:
    def test_copernicus_to_landcover_known_code(self) -> None:
        from stochastic_warfare.terrain.real_classification import copernicus_to_landcover
        assert copernicus_to_landcover(50) == LandCover.URBAN_DENSE

    def test_copernicus_to_landcover_forest(self) -> None:
        from stochastic_warfare.terrain.real_classification import copernicus_to_landcover
        assert copernicus_to_landcover(111) == LandCover.FOREST_CONIFEROUS
        assert copernicus_to_landcover(112) == LandCover.FOREST_DECIDUOUS
        assert copernicus_to_landcover(113) == LandCover.FOREST_MIXED

    def test_unknown_code_fallback(self) -> None:
        from stochastic_warfare.terrain.real_classification import copernicus_to_landcover
        assert copernicus_to_landcover(999) == LandCover.OPEN

    def test_water_codes(self) -> None:
        from stochastic_warfare.terrain.real_classification import copernicus_to_landcover
        assert copernicus_to_landcover(80) == LandCover.WATER
        assert copernicus_to_landcover(200) == LandCover.WATER

    def test_all_defined_codes_map(self) -> None:
        from stochastic_warfare.terrain.real_classification import (
            _COPERNICUS_TO_LANDCOVER,
            copernicus_to_landcover,
        )
        for code, expected in _COPERNICUS_TO_LANDCOVER.items():
            assert copernicus_to_landcover(code) == expected

    def test_soil_derivation(self) -> None:
        from stochastic_warfare.terrain.real_classification import landcover_to_soil
        assert landcover_to_soil(LandCover.URBAN_DENSE) == SoilType.ROCK
        assert landcover_to_soil(LandCover.WETLAND) == SoilType.PEAT
        assert landcover_to_soil(LandCover.GRASSLAND) == SoilType.LOAM


class TestCopernicusLoader:
    @pytest.fixture(autouse=True)
    def _require_rasterio(self) -> None:
        pytest.importorskip("rasterio")

    def test_basic_load(self, tmp_path: Path, bbox: BoundingBox, projection) -> None:
        from stochastic_warfare.terrain.real_classification import load_copernicus_classification
        from stochastic_warfare.terrain.classification import TerrainClassification

        data = np.full((50, 50), 30, dtype=np.uint8)  # Herbaceous → GRASSLAND
        tif_path = tmp_path / "copernicus.tif"
        _make_copernicus_tif(tif_path, data, (35.7, 32.9, 35.9, 33.1))

        tc = load_copernicus_classification(tif_path, bbox, 500.0, projection)
        assert isinstance(tc, TerrainClassification)
        assert tc.shape[0] > 0
        assert tc.shape[1] > 0

    def test_nearest_neighbor_no_interpolation(
        self, tmp_path: Path, bbox: BoundingBox, projection,
    ) -> None:
        from stochastic_warfare.terrain.real_classification import load_copernicus_classification

        # Checkerboard of urban (50) and water (80)
        data = np.zeros((20, 20), dtype=np.uint8)
        data[::2, ::2] = 50
        data[1::2, 1::2] = 50
        data[::2, 1::2] = 80
        data[1::2, ::2] = 80
        tif_path = tmp_path / "checker.tif"
        _make_copernicus_tif(tif_path, data, (35.7, 32.9, 35.9, 33.1))

        tc = load_copernicus_classification(tif_path, bbox, 500.0, projection)
        # All values should be valid LandCover codes (no fractional artifacts)
        unique = np.unique(tc._land_cover)
        for code in unique:
            assert code in [lc.value for lc in LandCover]

    def test_urban_classification(
        self, tmp_path: Path, bbox: BoundingBox, projection,
    ) -> None:
        from stochastic_warfare.terrain.real_classification import load_copernicus_classification

        data = np.full((20, 20), 50, dtype=np.uint8)  # Urban
        tif_path = tmp_path / "urban.tif"
        _make_copernicus_tif(tif_path, data, (35.7, 32.9, 35.9, 33.1))

        tc = load_copernicus_classification(tif_path, bbox, 500.0, projection)
        # All cells should be URBAN_DENSE
        assert np.all(tc._land_cover == LandCover.URBAN_DENSE.value)

    def test_grid_alignment_with_cell_size(
        self, tmp_path: Path, bbox: BoundingBox, projection,
    ) -> None:
        from stochastic_warfare.terrain.real_classification import load_copernicus_classification

        data = np.full((20, 20), 30, dtype=np.uint8)
        tif_path = tmp_path / "align.tif"
        _make_copernicus_tif(tif_path, data, (35.7, 32.9, 35.9, 33.1))

        tc_coarse = load_copernicus_classification(tif_path, bbox, 1000.0, projection)
        tc_fine = load_copernicus_classification(tif_path, bbox, 500.0, projection)
        assert tc_fine.shape[0] > tc_coarse.shape[0]

    def test_forest_classification(
        self, tmp_path: Path, bbox: BoundingBox, projection,
    ) -> None:
        from stochastic_warfare.terrain.real_classification import load_copernicus_classification

        data = np.full((20, 20), 111, dtype=np.uint8)  # Closed evergreen needle
        tif_path = tmp_path / "forest.tif"
        _make_copernicus_tif(tif_path, data, (35.7, 32.9, 35.9, 33.1))

        tc = load_copernicus_classification(tif_path, bbox, 500.0, projection)
        assert np.all(tc._land_cover == LandCover.FOREST_CONIFEROUS.value)

    def test_mixed_terrain(
        self, tmp_path: Path, bbox: BoundingBox, projection,
    ) -> None:
        from stochastic_warfare.terrain.real_classification import load_copernicus_classification

        data = np.zeros((20, 20), dtype=np.uint8)
        data[:10, :] = 30   # Grassland (south half)
        data[10:, :] = 80   # Water (north half)
        tif_path = tmp_path / "mixed.tif"
        _make_copernicus_tif(tif_path, data, (35.7, 32.9, 35.9, 33.1))

        tc = load_copernicus_classification(tif_path, bbox, 500.0, projection)
        unique = np.unique(tc._land_cover)
        assert len(unique) >= 2


# ── Infrastructure Tests ─────────────────────────────────────────────────


class TestHighwayMapping:
    def test_motorway(self) -> None:
        from stochastic_warfare.terrain.real_infrastructure import highway_to_road_type
        assert highway_to_road_type("motorway") == RoadType.HIGHWAY

    def test_primary(self) -> None:
        from stochastic_warfare.terrain.real_infrastructure import highway_to_road_type
        assert highway_to_road_type("primary") == RoadType.PAVED

    def test_residential(self) -> None:
        from stochastic_warfare.terrain.real_infrastructure import highway_to_road_type
        assert highway_to_road_type("residential") == RoadType.IMPROVED_DIRT

    def test_track(self) -> None:
        from stochastic_warfare.terrain.real_infrastructure import highway_to_road_type
        assert highway_to_road_type("track") == RoadType.UNIMPROVED

    def test_footway(self) -> None:
        from stochastic_warfare.terrain.real_infrastructure import highway_to_road_type
        assert highway_to_road_type("footway") == RoadType.TRAIL

    def test_unknown_fallback(self) -> None:
        from stochastic_warfare.terrain.real_infrastructure import highway_to_road_type
        assert highway_to_road_type("unknown_type") == RoadType.UNIMPROVED


class TestOsmRoadLoader:
    def test_load_single_road(
        self, tmp_path: Path, bbox: BoundingBox, projection,
    ) -> None:
        from stochastic_warfare.terrain.real_infrastructure import load_osm_infrastructure

        feat = _road_feature(
            [[35.8, 33.0], [35.85, 33.0]], highway="primary",
        )
        roads_path = tmp_path / "osm" / "roads.geojson"
        _make_roads_geojson(roads_path, [feat])

        mgr = load_osm_infrastructure(
            {"roads": roads_path}, projection, bbox,
        )
        assert len(mgr._roads) == 1
        assert list(mgr._roads.values())[0].road_type == RoadType.PAVED

    def test_road_coordinate_conversion(
        self, tmp_path: Path, bbox: BoundingBox, projection,
    ) -> None:
        from stochastic_warfare.terrain.real_infrastructure import load_osm_infrastructure

        feat = _road_feature(
            [[35.8, 33.0], [35.85, 33.0]], highway="secondary",
        )
        roads_path = tmp_path / "osm" / "roads.geojson"
        _make_roads_geojson(roads_path, [feat])

        mgr = load_osm_infrastructure(
            {"roads": roads_path}, projection, bbox,
        )
        # Points should be in ENU (meters), not geodetic
        road = list(mgr._roads.values())[0]
        for pt in road.points:
            # ENU coordinates near origin should be within km range
            assert abs(pt[0]) < 50000
            assert abs(pt[1]) < 50000

    def test_bridge_extraction(
        self, tmp_path: Path, bbox: BoundingBox, projection,
    ) -> None:
        from stochastic_warfare.terrain.real_infrastructure import load_osm_infrastructure

        feat = _road_feature(
            [[35.8, 33.0], [35.85, 33.0]], highway="primary", bridge="yes",
        )
        roads_path = tmp_path / "osm" / "roads.geojson"
        _make_roads_geojson(roads_path, [feat])

        mgr = load_osm_infrastructure(
            {"roads": roads_path}, projection, bbox,
        )
        assert len(mgr._bridges) == 1
        assert list(mgr._bridges.values())[0].road_id == list(mgr._roads.values())[0].road_id


class TestOsmBuildingLoader:
    def test_load_building(
        self, tmp_path: Path, bbox: BoundingBox, projection,
    ) -> None:
        from stochastic_warfare.terrain.real_infrastructure import load_osm_infrastructure

        ring = [[35.8, 33.0], [35.81, 33.0], [35.81, 33.01], [35.8, 33.01], [35.8, 33.0]]
        feat = _building_feature([ring])
        bldg_path = tmp_path / "osm" / "buildings.geojson"
        _make_roads_geojson(bldg_path, [feat])

        mgr = load_osm_infrastructure(
            {"buildings": bldg_path}, projection, bbox,
        )
        assert len(mgr._buildings) == 1
        assert list(mgr._buildings.values())[0].construction == "masonry"

    def test_building_height(
        self, tmp_path: Path, bbox: BoundingBox, projection,
    ) -> None:
        from stochastic_warfare.terrain.real_infrastructure import load_osm_infrastructure

        ring = [[35.8, 33.0], [35.81, 33.0], [35.81, 33.01], [35.8, 33.01], [35.8, 33.0]]
        feat = _building_feature([ring], height=25.0)
        bldg_path = tmp_path / "osm" / "buildings.geojson"
        _make_roads_geojson(bldg_path, [feat])

        mgr = load_osm_infrastructure(
            {"buildings": bldg_path}, projection, bbox,
        )
        assert list(mgr._buildings.values())[0].height == 25.0

    def test_industrial_construction(
        self, tmp_path: Path, bbox: BoundingBox, projection,
    ) -> None:
        from stochastic_warfare.terrain.real_infrastructure import load_osm_infrastructure

        ring = [[35.8, 33.0], [35.81, 33.0], [35.81, 33.01], [35.8, 33.01], [35.8, 33.0]]
        feat = _building_feature([ring], building="industrial")
        bldg_path = tmp_path / "osm" / "buildings.geojson"
        _make_roads_geojson(bldg_path, [feat])

        mgr = load_osm_infrastructure(
            {"buildings": bldg_path}, projection, bbox,
        )
        assert list(mgr._buildings.values())[0].construction == "concrete"


class TestOsmRailLoader:
    def test_load_rail(
        self, tmp_path: Path, bbox: BoundingBox, projection,
    ) -> None:
        from stochastic_warfare.terrain.real_infrastructure import load_osm_infrastructure

        feat = _rail_feature([[35.8, 33.0], [35.85, 33.0]])
        rail_path = tmp_path / "osm" / "railways.geojson"
        _make_roads_geojson(rail_path, [feat])

        mgr = load_osm_infrastructure(
            {"railways": rail_path}, projection, bbox,
        )
        assert len(mgr._rail_lines) == 1
        assert list(mgr._rail_lines.values())[0].gauge == "standard"

    def test_narrow_gauge(
        self, tmp_path: Path, bbox: BoundingBox, projection,
    ) -> None:
        from stochastic_warfare.terrain.real_infrastructure import load_osm_infrastructure

        feat = _rail_feature([[35.8, 33.0], [35.85, 33.0]], railway="narrow_gauge")
        rail_path = tmp_path / "osm" / "railways.geojson"
        _make_roads_geojson(rail_path, [feat])

        mgr = load_osm_infrastructure(
            {"railways": rail_path}, projection, bbox,
        )
        assert list(mgr._rail_lines.values())[0].gauge == "narrow"


class TestOsmEdgeCases:
    def test_empty_geojson(
        self, tmp_path: Path, bbox: BoundingBox, projection,
    ) -> None:
        from stochastic_warfare.terrain.real_infrastructure import load_osm_infrastructure

        roads_path = tmp_path / "osm" / "roads.geojson"
        _make_roads_geojson(roads_path, [])

        mgr = load_osm_infrastructure(
            {"roads": roads_path}, projection, bbox,
        )
        assert len(mgr._roads) == 0

    def test_missing_tags_handled(
        self, tmp_path: Path, bbox: BoundingBox, projection,
    ) -> None:
        from stochastic_warfare.terrain.real_infrastructure import load_osm_infrastructure

        # Feature with no highway tag → should be skipped
        feat = {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[35.8, 33.0], [35.85, 33.0]],
            },
            "properties": {"name": "test"},
        }
        roads_path = tmp_path / "osm" / "roads.geojson"
        _make_roads_geojson(roads_path, [feat])

        mgr = load_osm_infrastructure(
            {"roads": roads_path}, projection, bbox,
        )
        assert len(mgr._roads) == 0

    def test_combined_layers(
        self, tmp_path: Path, bbox: BoundingBox, projection,
    ) -> None:
        from stochastic_warfare.terrain.real_infrastructure import load_osm_infrastructure

        road_feat = _road_feature([[35.8, 33.0], [35.85, 33.0]])
        roads_path = tmp_path / "osm" / "roads.geojson"
        _make_roads_geojson(roads_path, [road_feat])

        ring = [[35.8, 33.0], [35.81, 33.0], [35.81, 33.01], [35.8, 33.01], [35.8, 33.0]]
        bldg_feat = _building_feature([ring])
        bldg_path = tmp_path / "osm" / "buildings.geojson"
        _make_roads_geojson(bldg_path, [bldg_feat])

        mgr = load_osm_infrastructure(
            {"roads": roads_path, "buildings": bldg_path}, projection, bbox,
        )
        assert len(mgr._roads) == 1
        assert len(mgr._buildings) == 1
