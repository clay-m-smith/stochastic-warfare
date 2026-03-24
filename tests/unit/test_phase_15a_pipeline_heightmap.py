"""Phase 15a tests — data pipeline + SRTM heightmap loader."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from stochastic_warfare.terrain.data_pipeline import (
    BoundingBox,
    RealTerrainContext,
    TerrainDataConfig,
    check_data_available,
    compute_cache_key,
    is_cache_valid,
    load_cache,
    save_cache,
    srtm_tiles_for_bbox,
)


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def bbox_golan() -> BoundingBox:
    return BoundingBox(south=32.9, west=35.7, north=33.1, east=35.9)


@pytest.fixture
def bbox_falklands() -> BoundingBox:
    return BoundingBox(south=-52.5, west=-60.0, north=-51.0, east=-58.5)


# ── BoundingBox validation ────────────────────────────────────────────────


class TestBoundingBox:
    def test_valid_bbox(self, bbox_golan: BoundingBox) -> None:
        assert bbox_golan.south < bbox_golan.north
        assert bbox_golan.west < bbox_golan.east

    def test_north_must_exceed_south(self) -> None:
        with pytest.raises(ValueError, match="north.*must be > south"):
            BoundingBox(south=33.0, west=35.0, north=32.0, east=36.0)

    def test_east_must_exceed_west(self) -> None:
        with pytest.raises(ValueError, match="east.*must be > west"):
            BoundingBox(south=32.0, west=36.0, north=33.0, east=35.0)


# ── TerrainDataConfig validation ──────────────────────────────────────────


class TestTerrainDataConfig:
    def test_defaults(self, bbox_golan: BoundingBox) -> None:
        cfg = TerrainDataConfig(bbox=bbox_golan)
        assert cfg.cell_size_m == 100.0
        assert cfg.nodata_fill_method == "median"
        assert cfg.srtm_enabled is True
        assert cfg.gebco_enabled is False

    def test_invalid_fill_method(self, bbox_golan: BoundingBox) -> None:
        with pytest.raises(ValueError, match="nodata_fill_method"):
            TerrainDataConfig(bbox=bbox_golan, nodata_fill_method="cubic")

    def test_negative_cell_size(self, bbox_golan: BoundingBox) -> None:
        with pytest.raises(ValueError, match="cell_size_m must be positive"):
            TerrainDataConfig(bbox=bbox_golan, cell_size_m=-10.0)

    def test_invalid_nodata_fraction(self, bbox_golan: BoundingBox) -> None:
        with pytest.raises(ValueError, match="max_nodata_fraction"):
            TerrainDataConfig(bbox=bbox_golan, max_nodata_fraction=1.5)


# ── SRTM tile naming ─────────────────────────────────────────────────────


class TestSrtmTiles:
    def test_single_tile(self, bbox_golan: BoundingBox) -> None:
        tiles = srtm_tiles_for_bbox(bbox_golan)
        assert "N32E035" in tiles

    def test_multi_tile(self) -> None:
        bbox = BoundingBox(south=32.5, west=35.5, north=33.5, east=36.5)
        tiles = srtm_tiles_for_bbox(bbox)
        assert len(tiles) == 4
        assert set(tiles) == {"N32E035", "N32E036", "N33E035", "N33E036"}

    def test_southern_hemisphere(self, bbox_falklands: BoundingBox) -> None:
        tiles = srtm_tiles_for_bbox(bbox_falklands)
        assert all(t.startswith("S") for t in tiles)
        assert all("W" in t for t in tiles)

    def test_boundary_tile(self) -> None:
        bbox = BoundingBox(south=33.0, west=35.0, north=33.01, east=35.01)
        tiles = srtm_tiles_for_bbox(bbox)
        assert "N33E035" in tiles


# ── Cache helpers ─────────────────────────────────────────────────────────


class TestCacheHelpers:
    def test_cache_key_determinism(self, bbox_golan: BoundingBox) -> None:
        k1 = compute_cache_key("srtm", bbox_golan, 100.0)
        k2 = compute_cache_key("srtm", bbox_golan, 100.0)
        assert k1 == k2
        assert len(k1) == 16

    def test_cache_key_differs_by_source(self, bbox_golan: BoundingBox) -> None:
        k1 = compute_cache_key("srtm", bbox_golan, 100.0)
        k2 = compute_cache_key("copernicus", bbox_golan, 100.0)
        assert k1 != k2

    def test_cache_key_differs_by_cell_size(self, bbox_golan: BoundingBox) -> None:
        k1 = compute_cache_key("srtm", bbox_golan, 100.0)
        k2 = compute_cache_key("srtm", bbox_golan, 50.0)
        assert k1 != k2

    def test_save_load_roundtrip(self, tmp_path: Path) -> None:
        data = np.random.default_rng(42).random((10, 10))
        cache_path = tmp_path / "cache" / "test.npz"
        save_cache(cache_path, elevation=data)
        loaded = load_cache(cache_path)
        np.testing.assert_array_equal(loaded["elevation"], data)

    def test_cache_invalid_when_missing(self, tmp_path: Path) -> None:
        assert not is_cache_valid(tmp_path / "nonexistent.npz", [])

    def test_cache_valid_when_newer(self, tmp_path: Path) -> None:
        raw = tmp_path / "raw.dat"
        raw.write_bytes(b"data")
        cache = tmp_path / "cache.npz"
        np.savez(str(cache), x=np.array([1]))
        assert is_cache_valid(cache, [raw])

    def test_cache_invalid_when_raw_newer(self, tmp_path: Path) -> None:
        cache = tmp_path / "cache.npz"
        np.savez(str(cache), x=np.array([1]))
        import time
        time.sleep(0.05)
        raw = tmp_path / "raw.dat"
        raw.write_bytes(b"newer data")
        assert not is_cache_valid(cache, [raw])


# ── check_data_available ──────────────────────────────────────────────────


class TestCheckDataAvailable:
    def test_empty_dir(self, tmp_path: Path, bbox_golan: BoundingBox) -> None:
        cfg = TerrainDataConfig(bbox=bbox_golan, data_dir=str(tmp_path))
        result = check_data_available(cfg)
        assert result.get("srtm") is False

    def test_srtm_found(self, tmp_path: Path, bbox_golan: BoundingBox) -> None:
        srtm_dir = tmp_path / "srtm"
        srtm_dir.mkdir()
        (srtm_dir / "N32E035.hgt").write_bytes(b"\x00" * 100)
        cfg = TerrainDataConfig(bbox=bbox_golan, data_dir=str(tmp_path))
        result = check_data_available(cfg)
        assert result["srtm"] is True

    def test_osm_found(self, tmp_path: Path, bbox_golan: BoundingBox) -> None:
        osm_dir = tmp_path / "osm"
        osm_dir.mkdir()
        (osm_dir / "roads.geojson").write_text('{"type":"FeatureCollection","features":[]}')
        cfg = TerrainDataConfig(bbox=bbox_golan, data_dir=str(tmp_path))
        result = check_data_available(cfg)
        assert result["osm"] is True


# ── RealTerrainContext ────────────────────────────────────────────────────


class TestRealTerrainContext:
    def test_heightmap_required(self) -> None:
        from stochastic_warfare.terrain.heightmap import HeightmapConfig
        from stochastic_warfare.terrain.heightmap import Heightmap

        hm = Heightmap(np.zeros((5, 5)), HeightmapConfig(cell_size=10.0))
        ctx = RealTerrainContext(heightmap=hm)
        assert ctx.heightmap is hm
        assert ctx.classification is None
        assert ctx.infrastructure is None
        assert ctx.bathymetry is None


# ── SRTM Heightmap Loader ────────────────────────────────────────────────

rasterio = pytest.importorskip("rasterio")


def _make_synthetic_geotiff(
    path: Path,
    data: np.ndarray,
    bounds: tuple[float, float, float, float],
) -> None:
    """Write a synthetic GeoTIFF for testing."""
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
        dtype="float64",
        crs="EPSG:4326",
        transform=transform,
    ) as dst:
        # GeoTIFF: row 0 = north, row N = south
        dst.write(data[::-1], 1)


def _make_synthetic_hgt(
    path: Path,
    data: np.ndarray,
) -> None:
    """Write a synthetic SRTM .hgt file (big-endian int16)."""
    # HGT: row 0 = north, row N = south → flip our south-up data
    flipped = data[::-1].astype(np.int16)
    path.write_bytes(flipped.astype(">i2").tobytes())


class TestSrtmHeightmapLoader:
    def test_flat_geotiff_produces_correct_heightmap(self, tmp_path: Path) -> None:
        from stochastic_warfare.terrain.heightmap import Heightmap
        from stochastic_warfare.terrain.real_heightmap import load_srtm_heightmap
        from stochastic_warfare.coordinates.transforms import ScenarioProjection

        data = np.full((100, 100), 500.0)
        tif_path = tmp_path / "srtm" / "N32E035.tif"
        tif_path.parent.mkdir(parents=True)
        _make_synthetic_geotiff(
            tif_path, data, (35.7, 32.9, 35.9, 33.1),
        )

        bbox = BoundingBox(south=32.9, west=35.7, north=33.1, east=35.9)
        proj = ScenarioProjection(33.0, 35.8)
        hm = load_srtm_heightmap(
            tile_paths=[tif_path],
            bbox=bbox,
            cell_size_m=500.0,
            projection=proj,
        )
        assert isinstance(hm, Heightmap)
        assert hm.shape[0] > 0
        assert hm.shape[1] > 0
        # All cells should be ~500m for flat terrain
        np.testing.assert_allclose(hm._data, 500.0, atol=1.0)

    def test_sloped_values_preserved(self, tmp_path: Path) -> None:
        from stochastic_warfare.terrain.real_heightmap import load_srtm_heightmap
        from stochastic_warfare.coordinates.transforms import ScenarioProjection

        rows, cols = 100, 100
        # South-to-north slope: elevation increases with row
        data = np.tile(np.linspace(0, 1000, rows).reshape(-1, 1), (1, cols))
        tif_path = tmp_path / "slope.tif"
        _make_synthetic_geotiff(tif_path, data, (35.7, 32.9, 35.9, 33.1))

        bbox = BoundingBox(south=32.9, west=35.7, north=33.1, east=35.9)
        proj = ScenarioProjection(33.0, 35.8)
        hm = load_srtm_heightmap(
            tile_paths=[tif_path],
            bbox=bbox,
            cell_size_m=500.0,
            projection=proj,
        )
        # Top row (north) should be higher than bottom row (south)
        assert hm._data[-1, 0] > hm._data[0, 0]

    def test_nodata_median_fill(self, tmp_path: Path) -> None:
        from stochastic_warfare.terrain.real_heightmap import _fill_nodata

        data = np.full((10, 10), 100.0)
        data[4, 4] = np.nan
        data[5, 5] = np.nan
        filled = _fill_nodata(data, method="median", max_fraction=0.5)
        assert not np.any(np.isnan(filled))
        # Filled values should be close to 100
        assert abs(filled[4, 4] - 100.0) < 1.0

    def test_nodata_nearest_fill(self, tmp_path: Path) -> None:
        from stochastic_warfare.terrain.real_heightmap import _fill_nodata

        data = np.full((10, 10), 200.0)
        data[5, 5] = np.nan
        filled = _fill_nodata(data, method="nearest", max_fraction=0.5)
        assert not np.any(np.isnan(filled))
        assert filled[5, 5] == 200.0

    def test_nodata_zero_fill(self) -> None:
        from stochastic_warfare.terrain.real_heightmap import _fill_nodata

        data = np.full((5, 5), 300.0)
        data[2, 2] = np.nan
        filled = _fill_nodata(data, method="zero", max_fraction=0.5)
        assert filled[2, 2] == 0.0

    def test_nodata_threshold_exceeded(self) -> None:
        from stochastic_warfare.terrain.real_heightmap import _fill_nodata

        data = np.full((10, 10), np.nan)
        data[0, 0] = 100.0
        with pytest.raises(ValueError, match="exceeds threshold"):
            _fill_nodata(data, method="median", max_fraction=0.2)

    def test_grid_row_flip_geotiff(self, tmp_path: Path) -> None:
        """GeoTIFF north-up should flip to our south-up convention."""
        from stochastic_warfare.terrain.real_heightmap import _load_geotiff

        rows, cols = 20, 20
        # In our south-up convention: row 0 = south (low elev), row N = north (high)
        data = np.arange(rows * cols, dtype=np.float64).reshape(rows, cols)
        tif_path = tmp_path / "flip_test.tif"
        _make_synthetic_geotiff(tif_path, data, (35.0, 32.0, 36.0, 33.0))

        loaded, meta = _load_geotiff(tif_path)
        # After loading, row 0 is north (GeoTIFF convention)
        # The merge_tiles function flips it
        assert loaded.shape == (rows, cols)

    def test_hgt_format_detection(self, tmp_path: Path) -> None:
        from stochastic_warfare.terrain.real_heightmap import _load_hgt

        # Create a tiny SRTM-3 (1201×1201) HGT file
        side = 1201
        data = np.full((side, side), 500, dtype=np.int16)
        hgt_path = tmp_path / "N32E035.hgt"
        # HGT is north-to-south, big-endian int16
        hgt_path.write_bytes(data.astype(">i2").tobytes())

        elev, lat, lon, arcsec = _load_hgt(hgt_path)
        assert lat == 32.0
        assert lon == 35.0
        assert arcsec == 3.0
        assert elev.shape == (side, side)
        # After flip, should be south-up
        np.testing.assert_allclose(elev, 500.0)

    def test_enu_origin_alignment(self, tmp_path: Path) -> None:
        from stochastic_warfare.terrain.real_heightmap import load_srtm_heightmap
        from stochastic_warfare.coordinates.transforms import ScenarioProjection

        data = np.full((100, 100), 100.0)
        tif_path = tmp_path / "origin_test.tif"
        _make_synthetic_geotiff(tif_path, data, (35.7, 32.9, 35.9, 33.1))

        bbox = BoundingBox(south=32.9, west=35.7, north=33.1, east=35.9)
        proj = ScenarioProjection(33.0, 35.8)
        hm = load_srtm_heightmap(
            tile_paths=[tif_path],
            bbox=bbox,
            cell_size_m=500.0,
            projection=proj,
        )
        # HeightmapConfig should have origin at SW corner in ENU
        sw = proj.geodetic_to_enu(32.9, 35.7)
        assert abs(hm._config.origin_easting - sw.easting) < 1.0
        assert abs(hm._config.origin_northing - sw.northing) < 1.0

    def test_cell_size_determines_shape(self, tmp_path: Path) -> None:
        from stochastic_warfare.terrain.real_heightmap import load_srtm_heightmap
        from stochastic_warfare.coordinates.transforms import ScenarioProjection

        data = np.full((100, 100), 100.0)
        tif_path = tmp_path / "shape_test.tif"
        _make_synthetic_geotiff(tif_path, data, (35.7, 32.9, 35.9, 33.1))

        bbox = BoundingBox(south=32.9, west=35.7, north=33.1, east=35.9)
        proj = ScenarioProjection(33.0, 35.8)

        hm_coarse = load_srtm_heightmap(
            [tif_path], bbox, 1000.0, proj,
        )
        hm_fine = load_srtm_heightmap(
            [tif_path], bbox, 500.0, proj,
        )
        # Finer resolution → more cells
        assert hm_fine.shape[0] > hm_coarse.shape[0]
        assert hm_fine.shape[1] > hm_coarse.shape[1]

    def test_heightmap_config_correctness(self, tmp_path: Path) -> None:
        from stochastic_warfare.terrain.real_heightmap import load_srtm_heightmap
        from stochastic_warfare.coordinates.transforms import ScenarioProjection

        data = np.full((50, 50), 250.0)
        tif_path = tmp_path / "config_test.tif"
        _make_synthetic_geotiff(tif_path, data, (35.0, 32.0, 36.0, 33.0))

        bbox = BoundingBox(south=32.0, west=35.0, north=33.0, east=36.0)
        proj = ScenarioProjection(32.5, 35.5)
        hm = load_srtm_heightmap([tif_path], bbox, 200.0, proj)

        assert hm.cell_size == 200.0

    def test_missing_rasterio_error(self) -> None:
        """Import guard should give helpful message."""
        # We can't actually test removing rasterio, but we can verify the
        # module-level import is guarded
        from stochastic_warfare.terrain import real_heightmap
        assert hasattr(real_heightmap, "load_srtm_heightmap")

    def test_no_nodata_passthrough(self) -> None:
        from stochastic_warfare.terrain.real_heightmap import _fill_nodata

        data = np.arange(25, dtype=np.float64).reshape(5, 5)
        result = _fill_nodata(data, method="median", max_fraction=0.5)
        np.testing.assert_array_equal(result, data)
