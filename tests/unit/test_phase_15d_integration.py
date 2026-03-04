"""Phase 15d tests — scenario integration + unified loader."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from stochastic_warfare.simulation.scenario import TerrainConfig, CampaignScenarioConfig
from stochastic_warfare.terrain.data_pipeline import (
    BoundingBox,
    RealTerrainContext,
    TerrainDataConfig,
    load_real_terrain,
)


# ── Helpers ───────────────────────────────────────────────────────────────


def _make_synthetic_geotiff(
    path: Path,
    data: np.ndarray,
    bounds: tuple[float, float, float, float],
) -> None:
    import rasterio
    from rasterio.transform import from_bounds

    rows, cols = data.shape
    west, south, east, north = bounds
    transform = from_bounds(west, south, east, north, cols, rows)

    with rasterio.open(
        str(path), "w", driver="GTiff",
        height=rows, width=cols, count=1, dtype="float64",
        crs="EPSG:4326", transform=transform,
    ) as dst:
        dst.write(data[::-1], 1)


def _make_copernicus_tif(
    path: Path,
    data: np.ndarray,
    bounds: tuple[float, float, float, float],
) -> None:
    import rasterio
    from rasterio.transform import from_bounds

    rows, cols = data.shape
    west, south, east, north = bounds
    transform = from_bounds(west, south, east, north, cols, rows)

    with rasterio.open(
        str(path), "w", driver="GTiff",
        height=rows, width=cols, count=1, dtype="uint8",
        crs="EPSG:4326", transform=transform,
    ) as dst:
        dst.write(data[::-1].astype(np.uint8), 1)


def _make_roads_geojson(path: Path, features: list[dict]) -> None:
    collection = {"type": "FeatureCollection", "features": features}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(collection, f)


def _setup_real_terrain(tmp_path: Path, bounds: tuple = (35.7, 32.9, 35.9, 33.1)) -> Path:
    """Create synthetic terrain data in tmp_path."""
    west, south, east, north = bounds

    # SRTM
    srtm_dir = tmp_path / "srtm"
    srtm_dir.mkdir()
    elev = np.full((50, 50), 400.0)
    _make_synthetic_geotiff(srtm_dir / "N32E035.tif", elev, bounds)

    # Copernicus
    cop_dir = tmp_path / "copernicus"
    cop_dir.mkdir()
    lc = np.full((20, 20), 30, dtype=np.uint8)  # Grassland
    _make_copernicus_tif(cop_dir / "landcover.tif", lc, bounds)

    # OSM
    osm_dir = tmp_path / "osm"
    osm_dir.mkdir()
    road_feat = {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": [[35.8, 33.0], [35.85, 33.0]],
        },
        "properties": {"highway": "primary"},
    }
    _make_roads_geojson(osm_dir / "roads.geojson", [road_feat])

    return tmp_path


# ── TerrainConfig Tests ──────────────────────────────────────────────────


class TestTerrainConfig:
    def test_default_source_is_procedural(self) -> None:
        tc = TerrainConfig(width_m=1000, height_m=1000)
        assert tc.terrain_source == "procedural"
        assert tc.terrain_type == "flat_desert"

    def test_accepts_real_source(self) -> None:
        tc = TerrainConfig(
            width_m=1000, height_m=1000,
            terrain_source="real",
            terrain_type="golan_heights",
        )
        assert tc.terrain_source == "real"

    def test_rejects_invalid_source(self) -> None:
        with pytest.raises(ValueError, match="terrain_source"):
            TerrainConfig(width_m=1000, height_m=1000, terrain_source="magic")

    def test_procedural_still_validates_type(self) -> None:
        with pytest.raises(ValueError, match="terrain_type"):
            TerrainConfig(
                width_m=1000, height_m=1000,
                terrain_source="procedural",
                terrain_type="unknown",
            )

    def test_real_source_allows_arbitrary_type(self) -> None:
        tc = TerrainConfig(
            width_m=1000, height_m=1000,
            terrain_source="real",
            terrain_type="custom_name",
        )
        assert tc.terrain_type == "custom_name"

    def test_yaml_with_terrain_source_parses(self) -> None:
        """Ensure YAML with terrain_source field validates."""
        import yaml
        raw = yaml.safe_load("""
            width_m: 15000
            height_m: 20000
            cell_size_m: 100.0
            terrain_source: real
            terrain_type: golan
            data_dir: data/terrain_raw
        """)
        tc = TerrainConfig.model_validate(raw)
        assert tc.terrain_source == "real"
        assert tc.data_dir == "data/terrain_raw"


# ── Unified Loader Tests ─────────────────────────────────────────────────


class TestLoadRealTerrain:
    @pytest.fixture(autouse=True)
    def _require_rasterio(self) -> None:
        pytest.importorskip("rasterio")

    def test_loads_all_layers(self, tmp_path: Path) -> None:
        data_dir = _setup_real_terrain(tmp_path)
        from stochastic_warfare.coordinates.transforms import ScenarioProjection

        bbox = BoundingBox(south=32.9, west=35.7, north=33.1, east=35.9)
        proj = ScenarioProjection(33.0, 35.8)
        config = TerrainDataConfig(
            bbox=bbox,
            cell_size_m=500.0,
            data_dir=str(data_dir),
        )
        ctx = load_real_terrain(config, proj)

        assert ctx.heightmap is not None
        assert ctx.classification is not None
        assert ctx.infrastructure is not None
        assert ctx.bathymetry is None  # GEBCO disabled by default

    def test_heightmap_classification_same_grid(self, tmp_path: Path) -> None:
        data_dir = _setup_real_terrain(tmp_path)
        from stochastic_warfare.coordinates.transforms import ScenarioProjection

        bbox = BoundingBox(south=32.9, west=35.7, north=33.1, east=35.9)
        proj = ScenarioProjection(33.0, 35.8)
        config = TerrainDataConfig(
            bbox=bbox, cell_size_m=500.0, data_dir=str(data_dir),
        )
        ctx = load_real_terrain(config, proj)
        # Same cell_size → same shape
        assert ctx.heightmap.shape == ctx.classification.shape

    def test_infrastructure_has_roads(self, tmp_path: Path) -> None:
        data_dir = _setup_real_terrain(tmp_path)
        from stochastic_warfare.coordinates.transforms import ScenarioProjection

        bbox = BoundingBox(south=32.9, west=35.7, north=33.1, east=35.9)
        proj = ScenarioProjection(33.0, 35.8)
        config = TerrainDataConfig(
            bbox=bbox, cell_size_m=500.0, data_dir=str(data_dir),
        )
        ctx = load_real_terrain(config, proj)
        assert len(ctx.infrastructure._roads) > 0

    def test_cache_speedup(self, tmp_path: Path) -> None:
        """Second load should use cache."""
        data_dir = _setup_real_terrain(tmp_path)
        cache_dir = tmp_path / "cache"
        from stochastic_warfare.coordinates.transforms import ScenarioProjection

        bbox = BoundingBox(south=32.9, west=35.7, north=33.1, east=35.9)
        proj = ScenarioProjection(33.0, 35.8)
        config = TerrainDataConfig(
            bbox=bbox, cell_size_m=500.0,
            data_dir=str(data_dir), cache_dir=str(cache_dir),
        )
        # First load
        ctx1 = load_real_terrain(config, proj)
        # Cache file should exist
        assert any(cache_dir.glob("*.npz"))
        # Second load (uses cache)
        ctx2 = load_real_terrain(config, proj)
        np.testing.assert_array_equal(ctx1.heightmap._data, ctx2.heightmap._data)

    def test_missing_data_raises(self, tmp_path: Path) -> None:
        bbox = BoundingBox(south=32.9, west=35.7, north=33.1, east=35.9)
        config = TerrainDataConfig(
            bbox=bbox, cell_size_m=500.0,
            data_dir=str(tmp_path / "empty"),
        )
        from stochastic_warfare.coordinates.transforms import ScenarioProjection
        proj = ScenarioProjection(33.0, 35.8)
        with pytest.raises(ValueError, match="No heightmap"):
            load_real_terrain(config, proj)

    def test_srtm_only_mode(self, tmp_path: Path) -> None:
        srtm_dir = tmp_path / "srtm"
        srtm_dir.mkdir()
        _make_synthetic_geotiff(
            srtm_dir / "N32E035.tif",
            np.full((50, 50), 200.0),
            (35.7, 32.9, 35.9, 33.1),
        )
        from stochastic_warfare.coordinates.transforms import ScenarioProjection

        bbox = BoundingBox(south=32.9, west=35.7, north=33.1, east=35.9)
        proj = ScenarioProjection(33.0, 35.8)
        config = TerrainDataConfig(
            bbox=bbox, cell_size_m=500.0,
            data_dir=str(tmp_path),
            copernicus_enabled=False,
            osm_enabled=False,
        )
        ctx = load_real_terrain(config, proj)
        assert ctx.heightmap is not None
        assert ctx.classification is None
        assert ctx.infrastructure is None


# ── SimulationContext Real Terrain Fields ─────────────────────────────────


class TestSimulationContextFields:
    def test_classification_field_exists(self) -> None:
        from stochastic_warfare.simulation.scenario import SimulationContext
        import dataclasses

        fields = {f.name for f in dataclasses.fields(SimulationContext)}
        assert "classification" in fields
        assert "infrastructure_manager" in fields
        assert "bathymetry" in fields

    def test_default_none(self) -> None:
        from stochastic_warfare.simulation.scenario import SimulationContext
        from stochastic_warfare.core.clock import SimulationClock
        from stochastic_warfare.core.events import EventBus
        from stochastic_warfare.core.rng import RNGManager
        from datetime import datetime, timezone, timedelta

        config = CampaignScenarioConfig(
            name="test", date="2024-01-01", duration_hours=1,
            terrain=TerrainConfig(width_m=1000, height_m=1000),
            sides=[
                {"side": "A", "units": []},
                {"side": "B", "units": []},
            ],
        )
        ctx = SimulationContext(
            config=config,
            clock=SimulationClock(
                start=datetime(2024, 1, 1, tzinfo=timezone.utc),
                tick_duration=timedelta(seconds=300),
            ),
            rng_manager=RNGManager(42),
            event_bus=EventBus(),
        )
        assert ctx.classification is None
        assert ctx.infrastructure_manager is None
        assert ctx.bathymetry is None


# ── Deterministic Replay ─────────────────────────────────────────────────


class TestDeterministicReplay:
    @pytest.fixture(autouse=True)
    def _require_rasterio(self) -> None:
        pytest.importorskip("rasterio")

    def test_same_data_same_result(self, tmp_path: Path) -> None:
        data_dir = _setup_real_terrain(tmp_path)
        from stochastic_warfare.coordinates.transforms import ScenarioProjection

        bbox = BoundingBox(south=32.9, west=35.7, north=33.1, east=35.9)
        proj = ScenarioProjection(33.0, 35.8)
        config = TerrainDataConfig(
            bbox=bbox, cell_size_m=500.0, data_dir=str(data_dir),
            cache_dir=str(tmp_path / "c1"),
        )
        ctx1 = load_real_terrain(config, proj)
        config2 = TerrainDataConfig(
            bbox=bbox, cell_size_m=500.0, data_dir=str(data_dir),
            cache_dir=str(tmp_path / "c2"),
        )
        ctx2 = load_real_terrain(config2, proj)
        np.testing.assert_array_equal(ctx1.heightmap._data, ctx2.heightmap._data)


# ── Edge Cases & Error Paths ─────────────────────────────────────────────


class TestEdgeCases:
    def test_nodata_fill_unknown_method_raises(self) -> None:
        from stochastic_warfare.terrain.real_heightmap import _fill_nodata

        data = np.full((5, 5), np.nan)
        data[0, 0] = 100.0
        with pytest.raises(ValueError, match="Unknown fill method"):
            _fill_nodata(data, method="cubic", max_fraction=1.0)

    def test_empty_geojson_roads(self, tmp_path: Path) -> None:
        from stochastic_warfare.terrain.real_infrastructure import load_osm_infrastructure
        from stochastic_warfare.coordinates.transforms import ScenarioProjection

        roads_path = tmp_path / "roads.geojson"
        roads_path.write_text('{"type":"FeatureCollection","features":[]}')
        proj = ScenarioProjection(33.0, 35.8)
        mgr = load_osm_infrastructure({"roads": roads_path}, proj)
        assert len(mgr._roads) == 0
        assert len(mgr._bridges) == 0

    def test_geojson_missing_geometry_skipped(self, tmp_path: Path) -> None:
        from stochastic_warfare.terrain.real_infrastructure import load_osm_infrastructure
        from stochastic_warfare.coordinates.transforms import ScenarioProjection
        import json

        feat = {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [35.8, 33.0]},
            "properties": {"highway": "primary"},
        }
        roads_path = tmp_path / "roads.geojson"
        roads_path.write_text(json.dumps({"type": "FeatureCollection", "features": [feat]}))
        proj = ScenarioProjection(33.0, 35.8)
        mgr = load_osm_infrastructure({"roads": roads_path}, proj)
        assert len(mgr._roads) == 0  # Point geometry not a road

    def test_depth_to_bottom_type_boundary_values(self) -> None:
        from stochastic_warfare.terrain.real_bathymetry import depth_to_bottom_type
        from stochastic_warfare.terrain.bathymetry import BottomType

        assert depth_to_bottom_type(0.0) == BottomType.ROCK
        assert depth_to_bottom_type(0.01) == BottomType.SAND
        assert depth_to_bottom_type(49.99) == BottomType.SAND
        assert depth_to_bottom_type(50.0) == BottomType.GRAVEL
        assert depth_to_bottom_type(199.99) == BottomType.GRAVEL
        assert depth_to_bottom_type(200.0) == BottomType.MUD
        assert depth_to_bottom_type(999.99) == BottomType.MUD
        assert depth_to_bottom_type(1000.0) == BottomType.CLAY

    def test_copernicus_unknown_codes_produce_valid_landcover(self) -> None:
        from stochastic_warfare.terrain.real_classification import copernicus_to_landcover
        from stochastic_warfare.terrain.classification import LandCover

        for code in [1, 2, 10, 15, 255]:
            lc = copernicus_to_landcover(code)
            assert isinstance(lc, LandCover)
            assert lc == LandCover.OPEN  # Unknown codes fall back to OPEN

    def test_srtm_tiles_single_point(self) -> None:
        from stochastic_warfare.terrain.data_pipeline import srtm_tiles_for_bbox

        bbox = BoundingBox(south=33.0, west=35.0, north=33.001, east=35.001)
        tiles = srtm_tiles_for_bbox(bbox)
        assert len(tiles) == 1
        assert tiles[0] == "N33E035"
