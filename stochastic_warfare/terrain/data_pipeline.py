"""Tile management, caching, and unified real-terrain loading.

Provides :func:`load_real_terrain` as the single entry point for loading
real-world geospatial data (SRTM, Copernicus, OSM, GEBCO) into the
simulation's terrain objects.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from stochastic_warfare.coordinates.transforms import ScenarioProjection

import numpy as np
from pydantic import BaseModel, field_validator

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.terrain.bathymetry import Bathymetry
from stochastic_warfare.terrain.classification import TerrainClassification
from stochastic_warfare.terrain.heightmap import Heightmap
from stochastic_warfare.terrain.infrastructure import InfrastructureManager

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Configuration models
# ---------------------------------------------------------------------------


class BoundingBox(BaseModel):
    """WGS-84 bounding box (decimal degrees)."""

    south: float
    west: float
    north: float
    east: float

    @field_validator("north")
    @classmethod
    def _north_gt_south(cls, v: float, info: Any) -> float:
        south = info.data.get("south")
        if south is not None and v <= south:
            raise ValueError(f"north ({v}) must be > south ({south})")
        return v

    @field_validator("east")
    @classmethod
    def _east_gt_west(cls, v: float, info: Any) -> float:
        west = info.data.get("west")
        if west is not None and v <= west:
            raise ValueError(f"east ({v}) must be > west ({west})")
        return v


class TerrainDataConfig(BaseModel):
    """Configuration for real-world terrain data loading."""

    bbox: BoundingBox
    cell_size_m: float = 100.0
    data_dir: str = "data/terrain_raw"
    cache_dir: str = "data/terrain_cache"
    srtm_enabled: bool = True
    copernicus_enabled: bool = True
    osm_enabled: bool = True
    gebco_enabled: bool = False
    nodata_fill_method: str = "median"
    max_nodata_fraction: float = 0.2

    @field_validator("nodata_fill_method")
    @classmethod
    def _known_fill(cls, v: str) -> str:
        allowed = {"median", "nearest", "zero"}
        if v not in allowed:
            raise ValueError(f"nodata_fill_method must be one of {allowed}; got {v!r}")
        return v

    @field_validator("cell_size_m")
    @classmethod
    def _positive_cell(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("cell_size_m must be positive")
        return v

    @field_validator("max_nodata_fraction")
    @classmethod
    def _fraction_range(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("max_nodata_fraction must be in [0, 1]")
        return v


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


@dataclass
class RealTerrainContext:
    """All terrain layers loaded from real-world data."""

    heightmap: Heightmap
    classification: TerrainClassification | None = None
    infrastructure: InfrastructureManager | None = None
    bathymetry: Bathymetry | None = None


# ---------------------------------------------------------------------------
# SRTM tile naming
# ---------------------------------------------------------------------------


def srtm_tiles_for_bbox(bbox: BoundingBox) -> list[str]:
    """Return SRTM tile names covering *bbox*.

    SRTM tiles are named by their SW corner: ``N29E046`` covers
    latitudes [29, 30) and longitudes [46, 47).
    """
    import math

    lat_min = math.floor(bbox.south)
    lat_max = math.floor(bbox.north)
    lon_min = math.floor(bbox.west)
    lon_max = math.floor(bbox.east)

    tiles: list[str] = []
    for lat in range(lat_min, lat_max + 1):
        for lon in range(lon_min, lon_max + 1):
            ns = "N" if lat >= 0 else "S"
            ew = "E" if lon >= 0 else "W"
            tiles.append(f"{ns}{abs(lat):02d}{ew}{abs(lon):03d}")
    return tiles


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def compute_cache_key(source: str, bbox: BoundingBox, cell_size_m: float) -> str:
    """Deterministic hash for cache filenames."""
    raw = f"{source}:{bbox.south:.6f},{bbox.west:.6f},{bbox.north:.6f},{bbox.east:.6f}:{cell_size_m:.2f}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def is_cache_valid(cache_path: Path, raw_paths: list[Path]) -> bool:
    """Check whether *cache_path* is newer than all *raw_paths*."""
    if not cache_path.exists():
        return False
    cache_mtime = cache_path.stat().st_mtime
    for p in raw_paths:
        if not p.exists():
            return False
        if p.stat().st_mtime > cache_mtime:
            return False
    return True


def save_cache(cache_path: Path, **arrays: np.ndarray) -> None:
    """Save numpy arrays to .npz cache file."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(str(cache_path), **arrays)
    logger.debug("Cached terrain data to %s", cache_path)


def load_cache(cache_path: Path) -> dict[str, np.ndarray]:
    """Load numpy arrays from .npz cache file."""
    data = np.load(str(cache_path))
    result = {k: data[k] for k in data.files}
    data.close()
    return result


# ---------------------------------------------------------------------------
# Data availability check
# ---------------------------------------------------------------------------


def check_data_available(config: TerrainDataConfig) -> dict[str, bool]:
    """Check which data sources have files on disk."""
    data_dir = Path(config.data_dir)
    result: dict[str, bool] = {}

    if config.srtm_enabled:
        tiles = srtm_tiles_for_bbox(config.bbox)
        srtm_found = False
        for tile in tiles:
            for ext in (".hgt", ".tif", ".tiff"):
                if (data_dir / "srtm" / f"{tile}{ext}").exists():
                    srtm_found = True
                    break
        result["srtm"] = srtm_found

    if config.copernicus_enabled:
        cop_dir = data_dir / "copernicus"
        result["copernicus"] = cop_dir.exists() and any(cop_dir.glob("*.tif"))

    if config.osm_enabled:
        osm_dir = data_dir / "osm"
        result["osm"] = osm_dir.exists() and any(osm_dir.glob("*.geojson"))

    if config.gebco_enabled:
        gebco_dir = data_dir / "gebco"
        result["gebco"] = gebco_dir.exists() and any(
            gebco_dir.glob("*.nc") or gebco_dir.glob("*.netcdf")
        )

    return result


# ---------------------------------------------------------------------------
# Unified loader
# ---------------------------------------------------------------------------


def _find_srtm_tiles(data_dir: Path, tile_names: list[str]) -> list[Path]:
    """Locate SRTM tile files on disk."""
    paths: list[Path] = []
    srtm_dir = data_dir / "srtm"
    for name in tile_names:
        for ext in (".hgt", ".tif", ".tiff"):
            p = srtm_dir / f"{name}{ext}"
            if p.exists():
                paths.append(p)
                break
    return paths


def load_real_terrain(
    config: TerrainDataConfig,
    projection: ScenarioProjection,
) -> RealTerrainContext:
    """Load all enabled terrain layers from real-world data.

    Parameters
    ----------
    config:
        Data source configuration and bounding box.
    projection:
        :class:`~stochastic_warfare.coordinates.transforms.ScenarioProjection`
        for geodetic→ENU conversion.

    Returns
    -------
    RealTerrainContext
        Container with all loaded terrain layers.
    """
    data_dir = Path(config.data_dir)
    cache_dir = Path(config.cache_dir)

    # --- Heightmap (SRTM) ---
    heightmap: Heightmap | None = None
    if config.srtm_enabled:
        tile_names = srtm_tiles_for_bbox(config.bbox)
        tile_paths = _find_srtm_tiles(data_dir, tile_names)
        if tile_paths:
            cache_key = compute_cache_key("srtm", config.bbox, config.cell_size_m)
            cache_path = cache_dir / f"srtm_{cache_key}.npz"

            if is_cache_valid(cache_path, tile_paths):
                logger.info("Loading SRTM from cache: %s", cache_path)
                cached = load_cache(cache_path)
                from stochastic_warfare.terrain.heightmap import HeightmapConfig

                heightmap = Heightmap(
                    cached["elevation"],
                    HeightmapConfig(cell_size=config.cell_size_m),
                )
            else:
                from stochastic_warfare.terrain.real_heightmap import (
                    load_srtm_heightmap,
                )

                heightmap = load_srtm_heightmap(
                    tile_paths=tile_paths,
                    bbox=config.bbox,
                    cell_size_m=config.cell_size_m,
                    projection=projection,
                    nodata_fill=config.nodata_fill_method,
                    max_nodata_fraction=config.max_nodata_fraction,
                )
                save_cache(cache_path, elevation=heightmap._data)
        else:
            logger.warning("SRTM enabled but no tiles found for %s", tile_names)

    if heightmap is None:
        raise ValueError(
            "No heightmap data available. Ensure SRTM tiles exist in "
            f"{data_dir / 'srtm'}"
        )

    # --- Classification (Copernicus) ---
    classification: TerrainClassification | None = None
    if config.copernicus_enabled:
        cop_dir = data_dir / "copernicus"
        tif_files = sorted(cop_dir.glob("*.tif")) if cop_dir.exists() else []
        if tif_files:
            from stochastic_warfare.terrain.real_classification import (
                load_copernicus_classification,
            )

            classification = load_copernicus_classification(
                tif_path=tif_files[0],
                bbox=config.bbox,
                cell_size_m=config.cell_size_m,
                projection=projection,
            )
        else:
            logger.warning("Copernicus enabled but no .tif found in %s", cop_dir)

    # --- Infrastructure (OSM) ---
    infrastructure: InfrastructureManager | None = None
    if config.osm_enabled:
        osm_dir = data_dir / "osm"
        geojson_paths: dict[str, Path] = {}
        if osm_dir.exists():
            for name in ("roads", "buildings", "railways", "waterways"):
                p = osm_dir / f"{name}.geojson"
                if p.exists():
                    geojson_paths[name] = p
        if geojson_paths:
            from stochastic_warfare.terrain.real_infrastructure import (
                load_osm_infrastructure,
            )

            infrastructure = load_osm_infrastructure(
                geojson_paths=geojson_paths,
                projection=projection,
                bbox=config.bbox,
            )
        else:
            logger.warning("OSM enabled but no .geojson found in %s", osm_dir)

    # --- Bathymetry (GEBCO) ---
    bathymetry: Bathymetry | None = None
    if config.gebco_enabled:
        gebco_dir = data_dir / "gebco"
        nc_files = sorted(gebco_dir.glob("*.nc")) if gebco_dir.exists() else []
        if nc_files:
            from stochastic_warfare.terrain.real_bathymetry import (
                load_gebco_bathymetry,
            )

            bathymetry = load_gebco_bathymetry(
                netcdf_path=nc_files[0],
                bbox=config.bbox,
                cell_size_m=config.cell_size_m,
                projection=projection,
            )
        else:
            logger.warning("GEBCO enabled but no .nc found in %s", gebco_dir)

    return RealTerrainContext(
        heightmap=heightmap,
        classification=classification,
        infrastructure=infrastructure,
        bathymetry=bathymetry,
    )
