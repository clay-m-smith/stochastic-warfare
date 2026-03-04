"""Copernicus land cover GeoTIFF → TerrainClassification loader.

Maps Copernicus Global Land Service (CGLS) land cover codes to the
simulation's :class:`LandCover` enum, derives default soil types,
and produces a :class:`TerrainClassification` grid.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from stochastic_warfare.coordinates.transforms import ScenarioProjection
    from stochastic_warfare.terrain.data_pipeline import BoundingBox

import numpy as np

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.terrain.classification import (
    ClassificationConfig,
    LandCover,
    SoilType,
    TerrainClassification,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Copernicus → LandCover mapping
# ---------------------------------------------------------------------------

# CGLS-LC100 discrete classification codes
_COPERNICUS_TO_LANDCOVER: dict[int, LandCover] = {
    0: LandCover.OPEN,               # No input data available
    20: LandCover.SHRUBLAND,          # Shrubs
    30: LandCover.GRASSLAND,          # Herbaceous vegetation
    40: LandCover.CULTIVATED,         # Cultivated and managed
    50: LandCover.URBAN_DENSE,        # Urban / built up
    60: LandCover.DESERT_ROCK,        # Bare / sparse vegetation
    70: LandCover.SNOW_ICE,           # Snow and Ice
    80: LandCover.WATER,              # Permanent water bodies
    90: LandCover.WETLAND,            # Herbaceous wetland
    100: LandCover.WETLAND,           # Moss and lichen
    111: LandCover.FOREST_CONIFEROUS, # Closed forest, evergreen needle leaf
    112: LandCover.FOREST_DECIDUOUS,  # Closed forest, deciduous broad leaf
    113: LandCover.FOREST_MIXED,      # Closed forest, mixed
    114: LandCover.FOREST_CONIFEROUS, # Closed forest, evergreen broad leaf
    115: LandCover.FOREST_DECIDUOUS,  # Closed forest, deciduous needle leaf
    116: LandCover.FOREST_MIXED,      # Closed forest, not matching any
    121: LandCover.FOREST_CONIFEROUS, # Open forest, evergreen needle leaf
    122: LandCover.FOREST_DECIDUOUS,  # Open forest, deciduous broad leaf
    123: LandCover.FOREST_MIXED,      # Open forest, mixed
    124: LandCover.FOREST_CONIFEROUS, # Open forest, evergreen broad leaf
    125: LandCover.FOREST_DECIDUOUS,  # Open forest, deciduous needle leaf
    126: LandCover.FOREST_MIXED,      # Open forest, not matching any
    200: LandCover.WATER,             # Open sea
}

# Default soil type for each land cover
_LANDCOVER_TO_SOIL: dict[LandCover, SoilType] = {
    LandCover.OPEN: SoilType.LOAM,
    LandCover.GRASSLAND: SoilType.LOAM,
    LandCover.SHRUBLAND: SoilType.LOAM,
    LandCover.FOREST_DECIDUOUS: SoilType.LOAM,
    LandCover.FOREST_CONIFEROUS: SoilType.LOAM,
    LandCover.FOREST_MIXED: SoilType.LOAM,
    LandCover.URBAN_DENSE: SoilType.ROCK,
    LandCover.URBAN_SUBURBAN: SoilType.LOAM,
    LandCover.URBAN_RURAL: SoilType.LOAM,
    LandCover.WATER: SoilType.MUD,
    LandCover.WETLAND: SoilType.PEAT,
    LandCover.DESERT_SAND: SoilType.SAND,
    LandCover.DESERT_ROCK: SoilType.ROCK,
    LandCover.SNOW_ICE: SoilType.ROCK,
    LandCover.CULTIVATED: SoilType.LOAM,
}


def copernicus_to_landcover(code: int) -> LandCover:
    """Map a Copernicus code to LandCover, falling back to OPEN."""
    return _COPERNICUS_TO_LANDCOVER.get(code, LandCover.OPEN)


def landcover_to_soil(lc: LandCover) -> SoilType:
    """Derive default SoilType from LandCover."""
    return _LANDCOVER_TO_SOIL.get(lc, SoilType.LOAM)


# ---------------------------------------------------------------------------
# Main loader
# ---------------------------------------------------------------------------


def load_copernicus_classification(
    tif_path: Path,
    bbox: BoundingBox,
    cell_size_m: float,
    projection: ScenarioProjection,
) -> TerrainClassification:
    """Load Copernicus land cover GeoTIFF and produce a TerrainClassification.

    Parameters
    ----------
    tif_path:
        Path to the Copernicus land cover GeoTIFF.
    bbox:
        :class:`BoundingBox` with south/west/north/east.
    cell_size_m:
        Target grid cell size in meters.
    projection:
        :class:`ScenarioProjection` for geodetic→ENU.
    """
    try:
        import rasterio
        from rasterio.windows import from_bounds
    except ImportError:
        raise ImportError(
            "rasterio is required for Copernicus loading. "
            "Install with: uv sync --extra terrain"
        )

    # 1. Window-read the bbox region
    with rasterio.open(str(tif_path)) as src:
        window = from_bounds(
            bbox.west, bbox.south, bbox.east, bbox.north,
            transform=src.transform,
        )
        raw = src.read(1, window=window)

    # 2. Compute ENU grid dimensions
    sw = projection.geodetic_to_enu(bbox.south, bbox.west)
    ne = projection.geodetic_to_enu(bbox.north, bbox.east)
    width_m = ne.easting - sw.easting
    height_m = ne.northing - sw.northing
    n_cols = max(1, int(round(width_m / cell_size_m)))
    n_rows = max(1, int(round(height_m / cell_size_m)))

    # 3. Nearest-neighbor resample (categorical data → no interpolation)
    from scipy.ndimage import zoom

    raw_south_up = raw[::-1]  # GeoTIFF north-up → our south-up
    if raw_south_up.shape[0] > 0 and raw_south_up.shape[1] > 0:
        row_factor = n_rows / raw_south_up.shape[0]
        col_factor = n_cols / raw_south_up.shape[1]
        resampled = zoom(raw_south_up, (row_factor, col_factor), order=0).astype(int)
    else:
        resampled = np.zeros((n_rows, n_cols), dtype=int)

    # 4. Map codes to LandCover and SoilType
    land_cover = np.zeros((n_rows, n_cols), dtype=np.int32)
    soil = np.zeros((n_rows, n_cols), dtype=np.int32)

    unique_codes = np.unique(resampled)
    for code in unique_codes:
        mask = resampled == code
        lc = copernicus_to_landcover(int(code))
        st = landcover_to_soil(lc)
        land_cover[mask] = lc.value
        soil[mask] = st.value

    # 5. Construct TerrainClassification
    config = ClassificationConfig(
        origin_easting=sw.easting,
        origin_northing=sw.northing,
        cell_size=cell_size_m,
    )
    logger.info(
        "Loaded Copernicus classification: %dx%d grid, %d unique land cover types",
        n_rows, n_cols, len(unique_codes),
    )
    return TerrainClassification(land_cover, soil, config)
