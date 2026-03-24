"""Unit tests for terrain data pipeline — BoundingBox, SRTM tiles, cache keys.

Phase 75c: Tests config validation, tile naming, cache hashing.
Skips load_real_terrain (requires external data).
"""

from __future__ import annotations

import pytest

from stochastic_warfare.terrain.data_pipeline import (
    BoundingBox,
    compute_cache_key,
    srtm_tiles_for_bbox,
)


# ===================================================================
# BoundingBox validation
# ===================================================================


class TestBoundingBox:
    """Pydantic BoundingBox validators."""

    def test_valid_accepted(self):
        bb = BoundingBox(south=29.0, west=46.0, north=30.0, east=47.0)
        assert bb.south == 29.0
        assert bb.north == 30.0

    def test_north_le_south_rejected(self):
        with pytest.raises(Exception):
            BoundingBox(south=30.0, west=46.0, north=29.0, east=47.0)

    def test_east_le_west_rejected(self):
        with pytest.raises(Exception):
            BoundingBox(south=29.0, west=47.0, north=30.0, east=46.0)

    def test_values_accessible(self):
        bb = BoundingBox(south=10.0, west=20.0, north=30.0, east=40.0)
        assert bb.west == 20.0
        assert bb.east == 40.0


# ===================================================================
# SRTM tiles
# ===================================================================


class TestSrtmTiles:
    """SRTM tile naming for bounding boxes."""

    def test_single_tile(self):
        bb = BoundingBox(south=29.5, west=46.5, north=29.9, east=46.9)
        tiles = srtm_tiles_for_bbox(bb)
        assert tiles == ["N29E046"]

    def test_multi_tile(self):
        bb = BoundingBox(south=29.0, west=46.0, north=31.0, east=48.0)
        tiles = srtm_tiles_for_bbox(bb)
        assert len(tiles) == 9  # 3 lats × 3 lons
        assert "N29E046" in tiles
        assert "N31E048" in tiles

    def test_southern_hemisphere(self):
        bb = BoundingBox(south=-35.0, west=18.0, north=-34.0, east=19.0)
        tiles = srtm_tiles_for_bbox(bb)
        assert any("S" in t for t in tiles)


# ===================================================================
# Cache key
# ===================================================================


class TestCacheKey:
    """Deterministic cache key hashing."""

    def test_deterministic(self):
        bb = BoundingBox(south=29.0, west=46.0, north=30.0, east=47.0)
        k1 = compute_cache_key("srtm", bb, 100.0)
        k2 = compute_cache_key("srtm", bb, 100.0)
        assert k1 == k2

    def test_different_inputs(self):
        bb1 = BoundingBox(south=29.0, west=46.0, north=30.0, east=47.0)
        bb2 = BoundingBox(south=30.0, west=46.0, north=31.0, east=47.0)
        assert compute_cache_key("srtm", bb1, 100.0) != compute_cache_key("srtm", bb2, 100.0)

    def test_correct_length(self):
        bb = BoundingBox(south=29.0, west=46.0, north=30.0, east=47.0)
        key = compute_cache_key("srtm", bb, 100.0)
        assert len(key) == 16  # sha256[:16]
