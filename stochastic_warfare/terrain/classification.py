"""Land-cover and soil classification layers.

Same grid convention as :mod:`heightmap` — ``grid[0, 0]`` is the south-west
corner.  Each cell carries a land-cover enum and a soil-type enum; a default
properties table maps land-cover codes to military-relevant terrain properties
(trafficability, concealment, cover, etc.).
"""

from __future__ import annotations

import enum
from typing import NamedTuple

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.types import Meters, Position


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class LandCover(enum.IntEnum):
    """Land-cover classification codes."""

    OPEN = 0
    GRASSLAND = 1
    SHRUBLAND = 2
    FOREST_DECIDUOUS = 3
    FOREST_CONIFEROUS = 4
    FOREST_MIXED = 5
    URBAN_DENSE = 6
    URBAN_SUBURBAN = 7
    URBAN_RURAL = 8
    WATER = 9
    WETLAND = 10
    DESERT_SAND = 11
    DESERT_ROCK = 12
    SNOW_ICE = 13
    CULTIVATED = 14


class SoilType(enum.IntEnum):
    """Soil classification codes."""

    SAND = 0
    CLAY = 1
    LOAM = 2
    ROCK = 3
    GRAVEL = 4
    PEAT = 5
    MUD = 6


# ---------------------------------------------------------------------------
# Terrain properties
# ---------------------------------------------------------------------------


class TerrainProperties(NamedTuple):
    """Military-relevant properties for a land-cover / soil combination."""

    land_cover: LandCover
    soil_type: SoilType
    base_trafficability: float  # 0.0–1.0
    concealment: float  # 0.0–1.0
    cover: float  # 0.0–1.0
    vegetation_height: Meters  # metres
    combustibility: float  # 0.0–1.0


# Default properties keyed by LandCover (assuming LOAM soil where applicable)
DEFAULT_PROPERTIES: dict[LandCover, TerrainProperties] = {
    LandCover.OPEN: TerrainProperties(LandCover.OPEN, SoilType.LOAM, 1.0, 0.0, 0.0, 0.0, 0.1),
    LandCover.GRASSLAND: TerrainProperties(LandCover.GRASSLAND, SoilType.LOAM, 0.9, 0.2, 0.0, 0.5, 0.4),
    LandCover.SHRUBLAND: TerrainProperties(LandCover.SHRUBLAND, SoilType.LOAM, 0.7, 0.4, 0.1, 1.5, 0.5),
    LandCover.FOREST_DECIDUOUS: TerrainProperties(LandCover.FOREST_DECIDUOUS, SoilType.LOAM, 0.3, 0.9, 0.5, 15.0, 0.6),
    LandCover.FOREST_CONIFEROUS: TerrainProperties(LandCover.FOREST_CONIFEROUS, SoilType.LOAM, 0.3, 0.9, 0.5, 20.0, 0.7),
    LandCover.FOREST_MIXED: TerrainProperties(LandCover.FOREST_MIXED, SoilType.LOAM, 0.3, 0.9, 0.5, 18.0, 0.65),
    LandCover.URBAN_DENSE: TerrainProperties(LandCover.URBAN_DENSE, SoilType.ROCK, 0.4, 0.7, 0.8, 20.0, 0.2),
    LandCover.URBAN_SUBURBAN: TerrainProperties(LandCover.URBAN_SUBURBAN, SoilType.LOAM, 0.6, 0.5, 0.5, 10.0, 0.3),
    LandCover.URBAN_RURAL: TerrainProperties(LandCover.URBAN_RURAL, SoilType.LOAM, 0.7, 0.3, 0.3, 6.0, 0.3),
    LandCover.WATER: TerrainProperties(LandCover.WATER, SoilType.MUD, 0.0, 0.0, 0.0, 0.0, 0.0),
    LandCover.WETLAND: TerrainProperties(LandCover.WETLAND, SoilType.PEAT, 0.2, 0.4, 0.1, 1.0, 0.1),
    LandCover.DESERT_SAND: TerrainProperties(LandCover.DESERT_SAND, SoilType.SAND, 0.6, 0.0, 0.0, 0.0, 0.0),
    LandCover.DESERT_ROCK: TerrainProperties(LandCover.DESERT_ROCK, SoilType.ROCK, 0.8, 0.1, 0.2, 0.0, 0.0),
    LandCover.SNOW_ICE: TerrainProperties(LandCover.SNOW_ICE, SoilType.ROCK, 0.5, 0.0, 0.0, 0.0, 0.0),
    LandCover.CULTIVATED: TerrainProperties(LandCover.CULTIVATED, SoilType.LOAM, 0.7, 0.3, 0.0, 1.0, 0.5),
}


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class ClassificationConfig(BaseModel):
    """Grid geometry for classification layers."""

    origin_easting: float = 0.0
    origin_northing: float = 0.0
    cell_size: float  # meters per cell


# ---------------------------------------------------------------------------
# TerrainClassification
# ---------------------------------------------------------------------------


class TerrainClassification:
    """Raster land-cover and soil layers with property lookup.

    Parameters
    ----------
    land_cover:
        2-D integer array of :class:`LandCover` codes.
    soil:
        2-D integer array of :class:`SoilType` codes (same shape).
    config:
        Grid geometry metadata.
    properties_table:
        Optional override for the default properties mapping.
    """

    def __init__(
        self,
        land_cover: np.ndarray,
        soil: np.ndarray,
        config: ClassificationConfig,
        properties_table: dict[LandCover, TerrainProperties] | None = None,
    ) -> None:
        if land_cover.shape != soil.shape:
            raise ValueError("land_cover and soil arrays must have the same shape")
        self._land_cover = land_cover.astype(np.int32, copy=False)
        self._soil = soil.astype(np.int32, copy=False)
        self._config = config
        self._properties = properties_table if properties_table is not None else DEFAULT_PROPERTIES

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def land_cover_at(self, pos: Position) -> LandCover:
        """Land-cover code at an ENU position."""
        row, col = self._enu_to_grid(pos)
        return LandCover(self._land_cover[row, col])

    def soil_at(self, pos: Position) -> SoilType:
        """Soil-type code at an ENU position."""
        row, col = self._enu_to_grid(pos)
        return SoilType(self._soil[row, col])

    def properties_at(self, pos: Position) -> TerrainProperties:
        """Full terrain properties at an ENU position."""
        lc = self.land_cover_at(pos)
        soil = self.soil_at(pos)
        base = self._properties[lc]
        # Return with actual soil from grid (base may assume LOAM)
        return TerrainProperties(
            land_cover=lc,
            soil_type=soil,
            base_trafficability=base.base_trafficability,
            concealment=base.concealment,
            cover=base.cover,
            vegetation_height=base.vegetation_height,
            combustibility=base.combustibility,
        )

    def trafficability_at(self, pos: Position) -> float:
        """Base dry-weather trafficability (0–1) at an ENU position."""
        lc = self.land_cover_at(pos)
        return self._properties[lc].base_trafficability

    @property
    def shape(self) -> tuple[int, int]:
        return (self._land_cover.shape[0], self._land_cover.shape[1])

    @property
    def cell_size(self) -> Meters:
        return self._config.cell_size

    # ------------------------------------------------------------------
    # Grid helpers
    # ------------------------------------------------------------------

    def grid_to_enu(self, row: int, col: int) -> Position:
        """Convert integer grid indices to an ENU position (cell centre)."""
        easting = self._config.origin_easting + (col + 0.5) * self._config.cell_size
        northing = self._config.origin_northing + (row + 0.5) * self._config.cell_size
        return Position(easting, northing, 0.0)

    def enu_to_grid(self, pos: Position) -> tuple[int, int]:
        """Convert an ENU position to the nearest grid cell (row, col)."""
        return self._enu_to_grid(pos)

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        return {
            "land_cover": self._land_cover.tolist(),
            "soil": self._soil.tolist(),
            "config": self._config.model_dump(),
        }

    def set_state(self, state: dict) -> None:
        self._land_cover = np.array(state["land_cover"], dtype=np.int32)
        self._soil = np.array(state["soil"], dtype=np.int32)
        self._config = ClassificationConfig.model_validate(state["config"])

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _enu_to_grid(self, pos: Position) -> tuple[int, int]:
        """Nearest grid cell for an ENU position, clamped to bounds."""
        col = int(round(
            (pos.easting - self._config.origin_easting) / self._config.cell_size - 0.5
        ))
        row = int(round(
            (pos.northing - self._config.origin_northing) / self._config.cell_size - 0.5
        ))
        row = max(0, min(row, self._land_cover.shape[0] - 1))
        col = max(0, min(col, self._land_cover.shape[1] - 1))
        return (row, col)
