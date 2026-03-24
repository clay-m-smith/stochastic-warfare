"""SRTM/ASTER GeoTIFF → Heightmap loader.

Reads one or more SRTM tiles (GeoTIFF or raw .hgt format), merges them,
fills no-data voids, reprojects to a local ENU grid, and produces a
:class:`~stochastic_warfare.terrain.heightmap.Heightmap` matching the
simulation's south-west origin convention.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from stochastic_warfare.coordinates.transforms import ScenarioProjection
    from stochastic_warfare.terrain.data_pipeline import BoundingBox

import numpy as np
from scipy.ndimage import distance_transform_edt, generic_filter

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.terrain.heightmap import Heightmap, HeightmapConfig

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# SRTM 1-arc-second tiles are 3601×3601 samples
_SRTM1_SIZE = 3601
# SRTM 3-arc-second tiles are 1201×1201 samples
_SRTM3_SIZE = 1201
# SRTM void sentinel
_SRTM_NODATA = -32768


# ---------------------------------------------------------------------------
# HGT format reader
# ---------------------------------------------------------------------------


def _load_hgt(path: Path) -> tuple[np.ndarray, float, float, float]:
    """Load a raw SRTM .hgt file.

    Returns (elevation_array, south_lat, west_lon, arc_seconds_per_cell).
    HGT filename encodes the SW corner: ``N29E046.hgt``.
    """
    name = path.stem.upper()
    ns = 1 if name[0] == "N" else -1
    lat = ns * int(name[1:3])
    ew = 1 if name[3] == "E" else -1
    lon = ew * int(name[4:7])

    raw = path.read_bytes()
    n_samples = len(raw) // 2
    side = int(np.sqrt(n_samples))
    if side not in (_SRTM1_SIZE, _SRTM3_SIZE):
        raise ValueError(f"Unexpected HGT size: {side}×{side}")

    # Big-endian signed 16-bit integers, north-to-south row order
    data = np.frombuffer(raw, dtype=">i2").reshape((side, side)).astype(np.float64)
    # Flip to south-to-north (our convention)
    data = data[::-1]
    # Mark voids
    data[data == _SRTM_NODATA] = np.nan

    arc_seconds = 1.0 if side == _SRTM1_SIZE else 3.0
    return data, float(lat), float(lon), arc_seconds


# ---------------------------------------------------------------------------
# GeoTIFF reader (rasterio)
# ---------------------------------------------------------------------------


def _load_geotiff(path: Path) -> tuple[np.ndarray, dict[str, Any]]:
    """Load a GeoTIFF elevation file via rasterio.

    Returns (elevation_2d, metadata_dict).
    """
    try:
        import rasterio
    except ImportError:
        raise ImportError(
            "rasterio is required for GeoTIFF loading. "
            "Install with: uv sync --extra terrain"
        )

    with rasterio.open(str(path)) as src:
        data = src.read(1).astype(np.float64)
        nodata = src.nodata
        meta = {
            "transform": src.transform,
            "crs": src.crs,
            "width": src.width,
            "height": src.height,
            "bounds": src.bounds,
        }

    if nodata is not None:
        data[data == nodata] = np.nan

    return data, meta


# ---------------------------------------------------------------------------
# No-data fill
# ---------------------------------------------------------------------------


def _fill_nodata(
    data: np.ndarray,
    method: str = "median",
    max_fraction: float = 0.2,
) -> np.ndarray:
    """Fill NaN voids in elevation data.

    Parameters
    ----------
    method:
        ``"median"`` — local median filter, ``"nearest"`` — nearest-neighbor
        interpolation, ``"zero"`` — fill with 0.
    max_fraction:
        Maximum fraction of NaN cells allowed. Raises ValueError if exceeded.
    """
    mask = np.isnan(data)
    frac = mask.sum() / data.size
    if frac > max_fraction:
        raise ValueError(
            f"No-data fraction {frac:.1%} exceeds threshold {max_fraction:.1%}"
        )
    if not mask.any():
        return data

    result = data.copy()
    if method == "zero":
        result[mask] = 0.0
    elif method == "nearest":
        # Distance transform gives index of nearest valid cell
        _, indices = distance_transform_edt(mask, return_distances=True, return_indices=True)
        result[mask] = data[tuple(indices[:, mask])]
    elif method == "median":
        # Iterative median fill: replace NaN with local median until done
        filled = result.copy()
        remaining = mask.copy()
        for _ in range(20):  # max iterations
            if not remaining.any():
                break
            median_vals = generic_filter(
                filled, np.nanmedian, size=3, mode="nearest",
            )
            filled[remaining] = median_vals[remaining]
            remaining = np.isnan(filled)
        result = filled
    else:
        raise ValueError(f"Unknown fill method: {method!r}")

    return result


# ---------------------------------------------------------------------------
# Main loader
# ---------------------------------------------------------------------------


def load_srtm_heightmap(
    tile_paths: list[Path],
    bbox: BoundingBox,
    cell_size_m: float,
    projection: ScenarioProjection,
    nodata_fill: str = "median",
    max_nodata_fraction: float = 0.2,
) -> Heightmap:
    """Load SRTM tiles and produce a Heightmap in ENU coordinates.

    Parameters
    ----------
    tile_paths:
        Paths to .hgt or .tif SRTM tile files.
    bbox:
        :class:`~stochastic_warfare.terrain.data_pipeline.BoundingBox` with
        south/west/north/east in decimal degrees.
    cell_size_m:
        Target grid cell size in meters.
    projection:
        :class:`~stochastic_warfare.coordinates.transforms.ScenarioProjection`.
    nodata_fill:
        Method for filling no-data voids.
    max_nodata_fraction:
        Maximum allowable fraction of no-data cells.

    Returns
    -------
    Heightmap
        Elevation grid in ENU coordinates with [0,0] = SW corner.
    """
    try:
        import rasterio
        from rasterio.transform import from_bounds
        from rasterio.warp import Resampling, reproject
    except ImportError:
        raise ImportError(
            "rasterio is required for SRTM loading. "
            "Install with: uv sync --extra terrain"
        )

    # 1. Load and merge tiles
    merged_data, merged_bounds = _merge_tiles(tile_paths)

    # 2. Crop to bounding box
    cropped, crop_transform = _crop_to_bbox(
        merged_data, merged_bounds, bbox,
    )

    # 3. Fill no-data
    filled = _fill_nodata(cropped, method=nodata_fill, max_fraction=max_nodata_fraction)

    # 4. Compute output grid dimensions from bbox + cell_size
    sw = projection.geodetic_to_enu(bbox.south, bbox.west)
    ne = projection.geodetic_to_enu(bbox.north, bbox.east)
    width_m = ne.easting - sw.easting
    height_m = ne.northing - sw.northing
    n_cols = max(1, int(round(width_m / cell_size_m)))
    n_rows = max(1, int(round(height_m / cell_size_m)))

    # 5. Create target grid sample points (cell centres in geodetic)
    eastings = np.linspace(
        sw.easting + cell_size_m / 2,
        sw.easting + (n_cols - 0.5) * cell_size_m,
        n_cols,
    )
    northings = np.linspace(
        sw.northing + cell_size_m / 2,
        sw.northing + (n_rows - 0.5) * cell_size_m,
        n_rows,
    )

    # Sample source data via bilinear interpolation
    elevation = _sample_bilinear(
        filled, crop_transform, eastings, northings, projection, bbox,
    )

    # 6. Construct Heightmap (already in south-up convention since northings
    #    increase with row index)
    config = HeightmapConfig(
        origin_easting=sw.easting,
        origin_northing=sw.northing,
        cell_size=cell_size_m,
    )
    return Heightmap(elevation, config)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _merge_tiles(
    tile_paths: list[Path],
) -> tuple[np.ndarray, tuple[float, float, float, float]]:
    """Merge multiple tiles into a single array.

    Returns (merged_data, (west, south, east, north)) in geographic coords.
    """
    if len(tile_paths) == 1:
        path = tile_paths[0]
        if path.suffix.lower() == ".hgt":
            data, lat, lon, arcsec = _load_hgt(path)
            # HGT covers [lat, lat+1] × [lon, lon+1]
            return data, (lon, lat, lon + 1.0, lat + 1.0)
        else:
            data, meta = _load_geotiff(path)
            b = meta["bounds"]
            # GeoTIFF stores north-to-south; flip to south-to-north
            data = data[::-1]
            return data, (b.left, b.bottom, b.right, b.top)

    # Multiple tiles: use rasterio merge
    import rasterio
    from rasterio.merge import merge

    datasets = []
    try:
        for p in tile_paths:
            if p.suffix.lower() == ".hgt":
                # Convert HGT to temp GeoTIFF for merge
                data, lat, lon, arcsec = _load_hgt(p)
                # Create in-memory dataset
                from rasterio.transform import from_bounds
                from rasterio.io import MemoryFile

                side = data.shape[0]
                transform = from_bounds(lon, lat, lon + 1.0, lat + 1.0, side, side)
                memfile = MemoryFile()
                with memfile.open(
                    driver="GTiff",
                    height=side,
                    width=side,
                    count=1,
                    dtype="float64",
                    crs="EPSG:4326",
                    transform=transform,
                ) as dst:
                    # Write in north-to-south order (GeoTIFF convention)
                    dst.write(data[::-1], 1)
                datasets.append(memfile.open())
            else:
                datasets.append(rasterio.open(str(p)))

        mosaic, out_transform = merge(datasets)
        merged = mosaic[0].astype(np.float64)

        # Compute merged bounds
        rows, cols = merged.shape
        west = out_transform.c
        north = out_transform.f
        east = west + cols * out_transform.a
        south = north + rows * out_transform.e  # e is negative

        # Flip to south-to-north
        merged = merged[::-1]
        return merged, (west, south, east, north)
    finally:
        for ds in datasets:
            ds.close()


def _crop_to_bbox(
    data: np.ndarray,
    bounds: tuple[float, float, float, float],
    bbox: BoundingBox,
) -> tuple[np.ndarray, tuple[float, float, float, float]]:
    """Crop data array to bbox. Data is in south-to-north row order."""
    west, south, east, north = bounds
    rows, cols = data.shape

    # Compute pixel coordinates
    col_res = (east - west) / cols
    row_res = (north - south) / rows

    c0 = max(0, int((bbox.west - west) / col_res))
    c1 = min(cols, int(np.ceil((bbox.east - west) / col_res)))
    r0 = max(0, int((bbox.south - south) / row_res))
    r1 = min(rows, int(np.ceil((bbox.north - south) / row_res)))

    cropped = data[r0:r1, c0:c1]

    crop_west = west + c0 * col_res
    crop_south = south + r0 * row_res
    crop_east = west + c1 * col_res
    crop_north = south + r1 * row_res

    return cropped, (crop_west, crop_south, crop_east, crop_north)


def _sample_bilinear(
    source: np.ndarray,
    source_bounds: tuple[float, float, float, float],
    target_eastings: np.ndarray,
    target_northings: np.ndarray,
    projection: ScenarioProjection,
    bbox: BoundingBox,
) -> np.ndarray:
    """Bilinear interpolation from source geodetic grid to target ENU grid."""
    west, south, east, north = source_bounds
    src_rows, src_cols = source.shape

    n_rows = len(target_northings)
    n_cols = len(target_eastings)
    result = np.zeros((n_rows, n_cols), dtype=np.float64)

    for r in range(n_rows):
        for c in range(n_cols):
            # Convert ENU to geodetic
            from stochastic_warfare.core.types import Position

            pos = Position(
                easting=float(target_eastings[c]),
                northing=float(target_northings[r]),
            )
            geo = projection.enu_to_geodetic(pos)
            lat, lon = geo.latitude, geo.longitude

            # Map to source pixel (fractional), clamp to valid range
            fc = np.clip(
                (lon - west) / (east - west) * (src_cols - 1),
                0.0, src_cols - 1,
            )
            fr = np.clip(
                (lat - south) / (north - south) * (src_rows - 1),
                0.0, src_rows - 1,
            )

            # Bilinear interpolation
            c0 = min(int(np.floor(fc)), src_cols - 1)
            r0 = min(int(np.floor(fr)), src_rows - 1)
            c1 = min(c0 + 1, src_cols - 1)
            r1 = min(r0 + 1, src_rows - 1)
            c0 = max(0, c0)
            r0 = max(0, r0)

            dc = fc - c0
            dr = fr - r0

            val = (
                source[r0, c0] * (1 - dr) * (1 - dc)
                + source[r1, c0] * dr * (1 - dc)
                + source[r0, c1] * (1 - dr) * dc
                + source[r1, c1] * dr * dc
            )
            result[r, c] = val

    return result
