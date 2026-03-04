"""GEBCO NetCDF → Bathymetry loader.

Reads GEBCO gridded bathymetry data (NetCDF format), negates elevation
values to positive depth, derives bottom types from depth heuristics,
and produces a :class:`Bathymetry` grid.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from stochastic_warfare.coordinates.transforms import ScenarioProjection
    from stochastic_warfare.terrain.data_pipeline import BoundingBox

import numpy as np

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.terrain.bathymetry import (
    Bathymetry,
    BathymetryConfig,
    BottomType,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Depth → BottomType heuristic
# ---------------------------------------------------------------------------

# Thresholds in meters depth
_SHALLOW_THRESHOLD = 50.0
_SHELF_THRESHOLD = 200.0
_DEEP_THRESHOLD = 1000.0


def depth_to_bottom_type(depth: float) -> BottomType:
    """Heuristic: derive bottom type from water depth.

    - <50m (nearshore): SAND
    - 50–200m (continental shelf): GRAVEL
    - 200–1000m (slope): MUD
    - >1000m (deep ocean): CLAY
    - ≤0 (land): ROCK
    """
    if depth <= 0:
        return BottomType.ROCK
    if depth < _SHALLOW_THRESHOLD:
        return BottomType.SAND
    if depth < _SHELF_THRESHOLD:
        return BottomType.GRAVEL
    if depth < _DEEP_THRESHOLD:
        return BottomType.MUD
    return BottomType.CLAY


def _classify_bottom_types(depth_grid: np.ndarray) -> np.ndarray:
    """Vectorized bottom type classification."""
    result = np.full(depth_grid.shape, BottomType.CLAY.value, dtype=np.int32)
    result[depth_grid <= 0] = BottomType.ROCK.value
    result[(depth_grid > 0) & (depth_grid < _SHALLOW_THRESHOLD)] = BottomType.SAND.value
    result[
        (depth_grid >= _SHALLOW_THRESHOLD) & (depth_grid < _SHELF_THRESHOLD)
    ] = BottomType.GRAVEL.value
    result[
        (depth_grid >= _SHELF_THRESHOLD) & (depth_grid < _DEEP_THRESHOLD)
    ] = BottomType.MUD.value
    return result


# ---------------------------------------------------------------------------
# Main loader
# ---------------------------------------------------------------------------


def load_gebco_bathymetry(
    netcdf_path: Path,
    bbox: BoundingBox,
    cell_size_m: float,
    projection: ScenarioProjection,
) -> Bathymetry:
    """Load GEBCO NetCDF bathymetry and produce a Bathymetry grid.

    Parameters
    ----------
    netcdf_path:
        Path to GEBCO NetCDF file.
    bbox:
        :class:`BoundingBox` with south/west/north/east.
    cell_size_m:
        Target grid cell size in meters.
    projection:
        :class:`ScenarioProjection` for geodetic→ENU.

    Notes
    -----
    GEBCO convention: positive = elevation above sea level,
    negative = below sea level. Our convention: positive = depth below
    MSL, ≤0 = land. So we negate GEBCO values.
    """
    try:
        import xarray as xr
    except ImportError:
        raise ImportError(
            "xarray is required for GEBCO loading. "
            "Install with: uv sync --extra terrain"
        )

    # 1. Open and select bbox region
    ds = xr.open_dataset(str(netcdf_path))
    # GEBCO uses 'elevation' or 'z' variable, 'lat'/'lon' coordinates
    elev_var = "elevation" if "elevation" in ds else "z"
    lat_var = "lat" if "lat" in ds.dims else "latitude"
    lon_var = "lon" if "lon" in ds.dims else "longitude"

    subset = ds[elev_var].sel(
        **{lat_var: slice(bbox.south, bbox.north)},
        **{lon_var: slice(bbox.west, bbox.east)},
    )
    raw = subset.values.astype(np.float64)
    ds.close()

    # 2. Negate: GEBCO positive-up → our positive-depth
    depth_raw = -raw
    # Clamp land cells to 0 (negative depth = above sea level)
    depth_raw = np.maximum(depth_raw, 0.0)

    # 3. Flip to south-up (NetCDF may be north-up depending on coordinate order)
    # Check if latitude is ascending or descending
    lat_vals = subset[lat_var].values if lat_var in subset.dims else None
    if lat_vals is not None and len(lat_vals) > 1 and lat_vals[0] > lat_vals[-1]:
        # North-to-south → flip
        depth_raw = depth_raw[::-1]

    # 4. Resample to target cell size
    sw = projection.geodetic_to_enu(bbox.south, bbox.west)
    ne = projection.geodetic_to_enu(bbox.north, bbox.east)
    width_m = ne.easting - sw.easting
    height_m = ne.northing - sw.northing
    n_cols = max(1, int(round(width_m / cell_size_m)))
    n_rows = max(1, int(round(height_m / cell_size_m)))

    from scipy.ndimage import zoom

    if depth_raw.shape[0] > 0 and depth_raw.shape[1] > 0:
        row_factor = n_rows / depth_raw.shape[0]
        col_factor = n_cols / depth_raw.shape[1]
        depth_grid = zoom(depth_raw, (row_factor, col_factor), order=1)
    else:
        depth_grid = np.zeros((n_rows, n_cols))

    # 5. Classify bottom types
    bottom_types = _classify_bottom_types(depth_grid)

    # 6. Construct Bathymetry
    config = BathymetryConfig(
        origin_easting=sw.easting,
        origin_northing=sw.northing,
        cell_size=cell_size_m,
    )

    logger.info(
        "Loaded GEBCO bathymetry: %dx%d grid, max depth %.1fm",
        n_rows, n_cols, np.max(depth_grid),
    )
    return Bathymetry(depth_grid, bottom_types, config)
