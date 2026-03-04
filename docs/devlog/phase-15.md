# Phase 15: Real-World Terrain & Data Pipeline

**Status**: Complete
**Date**: 2026-03-04
**Tests**: 97 new tests across 4 test files (91 initial + 6 postmortem)
**Total**: 4,469 tests passing (up from 4,372)

---

## Summary

Phase 15 adds real-world geospatial data loading from SRTM (elevation), Copernicus (land cover), OpenStreetMap (infrastructure), and GEBCO (bathymetry). Five new source modules in `stochastic_warfare/terrain/`, one modified file (`simulation/scenario.py`), one download script, and optional dependencies via `uv sync --extra terrain`.

The existing terrain system uses procedural generation (flat_desert, open_ocean, hilly_defense). Phase 15 adds a `terrain_source: "real"` option that loads actual geospatial data into the same `Heightmap`, `TerrainClassification`, `InfrastructureManager`, and `Bathymetry` objects — downstream code (LOS, movement, combat, logistics) works unchanged.

---

## Implementation Details

### 15a: Elevation Pipeline (35 tests)

- **`terrain/data_pipeline.py`** — Tile management and caching infrastructure:
  - `BoundingBox` and `TerrainDataConfig` pydantic config models
  - `srtm_tiles_for_bbox()` — SRTM tile name computation from bbox
  - `compute_cache_key()` — deterministic SHA-256 hash for .npz filenames
  - `is_cache_valid()` / `save_cache()` / `load_cache()` — mtime-based cache management
  - `check_data_available()` — probe which data sources exist on disk
  - `load_real_terrain()` — unified entry point that calls all loaders, returns `RealTerrainContext`
  - `RealTerrainContext` dataclass — holds heightmap + optional classification/infrastructure/bathymetry

- **`terrain/real_heightmap.py`** — SRTM GeoTIFF → Heightmap:
  - `_load_hgt()` — raw SRTM .hgt format reader (big-endian int16, 1201×1201 or 3601×3601)
  - `_load_geotiff()` — rasterio-based GeoTIFF reader
  - `_fill_nodata()` — void filling (median filter, nearest neighbor, or zero)
  - `_merge_tiles()` — multi-tile merge via rasterio
  - `_crop_to_bbox()` — geographic cropping
  - `_sample_bilinear()` — geodetic→ENU bilinear interpolation
  - `load_srtm_heightmap()` — main entry point

### 15b: Classification & Infrastructure (29 tests)

- **`terrain/real_classification.py`** — Copernicus land cover → TerrainClassification:
  - 23-entry `_COPERNICUS_TO_LANDCOVER` mapping table
  - 15-entry `_LANDCOVER_TO_SOIL` derivation table
  - `load_copernicus_classification()` — window-read + nearest-neighbor resample + enum mapping

- **`terrain/real_infrastructure.py`** — OSM GeoJSON → InfrastructureManager:
  - Design decision: GeoJSON input (not PBF) — no C++ toolchain needed, offline-first
  - 18-entry `_HIGHWAY_TO_ROAD_TYPE` mapping table
  - `_extract_roads()` — roads + bridge detection from `bridge=yes` tag
  - `_extract_buildings()` — polygon footprints with construction type inference
  - `_extract_railways()` — rail lines with gauge detection
  - `load_osm_infrastructure()` — unified loader for all layers

### 15c: Maritime Data (12 tests)

- **`terrain/real_bathymetry.py`** — GEBCO NetCDF → Bathymetry:
  - GEBCO convention: negate values (positive-up → positive-depth)
  - `depth_to_bottom_type()` — heuristic: <50m SAND, 50-200m GRAVEL, 200-1000m MUD, >1000m CLAY
  - `_classify_bottom_types()` — vectorized classification
  - `load_gebco_bathymetry()` — xarray-based NetCDF reader with bilinear resample

### 15d: Integration (21 tests, 15 initial + 6 postmortem)

- **`simulation/scenario.py`** (modified):
  - `TerrainConfig` — added `terrain_source`, `data_dir`, `cache_dir` fields
  - `terrain_source` validated before `terrain_type` (Pydantic field order matters)
  - `_build_terrain()` dispatches to `_build_real_terrain()` when `terrain_source="real"`
  - `_build_real_terrain()` computes bbox from lat/lon + width/height, creates projection, calls `load_real_terrain()`
  - `SimulationContext` — added `classification`, `infrastructure_manager`, `bathymetry` optional fields

- **`scripts/download_terrain.py`** — CLI download script:
  - SRTM: tile list + USGS download instructions
  - Copernicus: Vito download instructions
  - OSM: Overpass API → GeoJSON conversion (the only actual network I/O)
  - GEBCO: download instructions

---

## Dependencies

Optional: `rasterio>=1.3`, `xarray>=2024.1` via `uv sync --extra terrain`.

`pytest.importorskip("rasterio")` and `pytest.importorskip("xarray")` guard tests. Pure Python tests (cache helpers, GeoJSON parsing, mapping tables) run without optional deps.

---

## Files Changed

| File | Type | Purpose |
|------|------|---------|
| `terrain/data_pipeline.py` | new | Tile management, caching, unified loader |
| `terrain/real_heightmap.py` | new | SRTM/ASTER GeoTIFF → Heightmap |
| `terrain/real_classification.py` | new | Copernicus → TerrainClassification |
| `terrain/real_infrastructure.py` | new | OSM GeoJSON → InfrastructureManager |
| `terrain/real_bathymetry.py` | new | GEBCO NetCDF → Bathymetry |
| `simulation/scenario.py` | modified | terrain_source dispatch, SimulationContext fields |
| `scripts/download_terrain.py` | new | CLI download script |
| `pyproject.toml` | modified | terrain extras, terrain marker |
| 4 test files | new | 91 tests total |

---

## Known Limitations & Post-MVP Refinements

1. **Bilinear interpolation in Python loops**: The `_sample_bilinear()` function uses nested Python loops for geodetic→ENU sampling. Could be vectorized or JIT-compiled for large grids.
2. **No automatic SRTM download**: Requires Earthdata credentials. Download script provides instructions but doesn't auto-authenticate.
3. **Copernicus soil derivation is heuristic**: Default soil types from land cover. Real soil data (e.g., SoilGrids) could improve trafficability.
4. **GEBCO bottom type heuristic is depth-only**: Real bottom type depends on geological surveys, not just depth.
5. **Supply network not auto-wired**: Real roads populate InfrastructureManager but don't auto-create supply routes. Phase 12b's `sync_infrastructure()` must be called explicitly.
6. **No tile stitching validation**: Multi-tile seams not tested with real data (synthetic tests use single tiles).

---

## Test Distribution

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `test_phase_15a_pipeline_heightmap.py` | 35 | Pipeline config, caching, SRTM loader |
| `test_phase_15b_classification_infrastructure.py` | 29 | Copernicus + OSM GeoJSON |
| `test_phase_15c_bathymetry.py` | 12 | GEBCO bathymetry |
| `test_phase_15d_integration.py` | 21 | Scenario wiring, unified loader, edge cases |
| **Total** | **97** | |

---

## Postmortem

### 1. Delivered vs Planned

**Scope**: On target. All planned items delivered across all 4 sub-phases. The download script (`scripts/download_terrain.py`) provides instructions rather than fully automated downloads (requires Earthdata credentials for SRTM), which is the practical design choice.

**Intentionally deferred**: Supply network auto-wiring (real roads populate InfrastructureManager but don't auto-create supply routes — Phase 12b's `sync_infrastructure()` must be called explicitly). This is logged as a known limitation.

### 2. Integration Audit

All 5 new modules are imported and used:
- `data_pipeline.py` → imported by `simulation/scenario.py` (conditional on `terrain_source="real"`)
- `real_heightmap.py` → imported by `data_pipeline.py`
- `real_classification.py` → imported by `data_pipeline.py`
- `real_infrastructure.py` → imported by `data_pipeline.py`
- `real_bathymetry.py` → imported by `data_pipeline.py`
- `scenario.py` modifications → `_build_real_terrain()` wired into `_build_terrain()` dispatch
- `SimulationContext` fields → `classification`, `infrastructure_manager`, `bathymetry` added with `None` defaults

No dead code. Download script is standalone CLI (correct — not imported by sim code).

### 3. Test Quality Review

**Strengths**:
- Synthetic test files (GeoTIFF, HGT, GeoJSON, NetCDF) avoid needing real data in CI
- Cross-module integration tests (unified loader, scenario wiring)
- Deterministic replay tested
- Edge cases added during postmortem (empty GeoJSON, unknown codes, boundary values, missing data)

**Fixes applied**:
- Moved `pytest.importorskip("rasterio")` from file-level to class-level fixtures so pure-Python tests still run without optional deps
- Added 6 edge case tests (nodata fill error, empty GeoJSON, Point geometry skipped, bottom type boundaries, unknown Copernicus codes, single-point SRTM tiles)

### 4. API Surface Check

**Fix applied**: Replaced `Any` type hints with concrete types (`ScenarioProjection`, `BoundingBox`) across all 5 source files, using `TYPE_CHECKING` imports to avoid circular dependencies.

All public functions have type hints. Private functions use `_` prefix correctly. `get_logger(__name__)` used in all modules. No bare `print()`.

### 5. Deficit Discovery

No new TODOs/FIXMEs in code. Known limitations already documented in the devlog:
1. Bilinear interpolation in Python loops (could be vectorized/JIT'd)
2. No automatic SRTM download (requires Earthdata credentials)
3. Copernicus soil derivation is heuristic (real soil data could improve trafficability)
4. GEBCO bottom type heuristic is depth-only
5. Supply network not auto-wired from real roads
6. No tile stitching validation with real data

**Resolved deficits** from earlier phases:
- Phases 7, 9, 10: "Synthetic terrain only" → resolved by Phase 15 (real-world terrain pipeline)

### 6. Documentation Freshness

**Issues found and fixed**:
- README.md badge: 4,372 → 4,469 tests, Phase 13 → Phase 15
- README.md body: 4,463 → 4,469 tests, 91 → 97 Phase 15 tests
- CLAUDE.md: 91 → 97 tests, added "+ postmortem cleanup" to status
- devlog/index.md: 3 "Synthetic terrain" deficits marked resolved by Phase 15
- phase-15.md: test counts updated (91 → 97, 15 → 21 for 15d)

### 7. Performance Sanity

Full test suite: **4,469 passed in 89.96s** (~1:30).
Phase 14 baseline: ~85s for 4,372 tests.
Phase 15 adds 97 tests in 3.86s — proportional increase, no performance regression.

### 8. Summary

- **Scope**: On target — all 4 sub-phases delivered as planned
- **Quality**: High — 97 tests, synthetic test data, edge cases covered
- **Integration**: Fully wired — scenario dispatch, SimulationContext fields, unified loader
- **Deficits**: 6 known limitations documented (all minor/expected), 3 earlier deficits resolved
- **Action items**: All completed during postmortem (type hints, importorskip placement, edge case tests, doc freshness fixes)
