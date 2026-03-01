"""Bathymetry (underwater depth) data layer.

Same grid convention as :mod:`heightmap` — ``grid[0, 0]`` is the south-west
corner.  Depth values are positive below mean sea level (MSL).  Zero or
negative values indicate land.  Navigation hazards (reefs, shoals, wrecks)
are modelled as point features with a minimum depth and radius.
"""

from __future__ import annotations

import enum
import math

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.types import Meters, Position


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class BottomType(enum.IntEnum):
    """Seabed classification codes."""

    SAND = 0
    MUD = 1
    CLAY = 2
    ROCK = 3
    GRAVEL = 4
    CORAL = 5


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class NavigationHazard(BaseModel):
    """A point navigation hazard (reef, shoal, wreck, etc.)."""

    hazard_id: str
    hazard_type: str  # "reef", "shoal", "wreck", "rock"
    position: tuple[float, float]  # (easting, northing)
    minimum_depth: float  # meters below surface
    radius: float  # meters


class BathymetryConfig(BaseModel):
    """Grid geometry for bathymetric data."""

    origin_easting: float = 0.0
    origin_northing: float = 0.0
    cell_size: float
    no_data_value: float = 0.0  # 0 = land


# ---------------------------------------------------------------------------
# Bathymetry
# ---------------------------------------------------------------------------


class Bathymetry:
    """Raster depth model with navigation hazard overlay.

    Parameters
    ----------
    depth_data:
        2-D float array of depths (positive = below MSL, zero/negative = land).
    bottom_type:
        2-D integer array of :class:`BottomType` codes (same shape).
    config:
        Grid geometry metadata.
    hazards:
        Optional list of navigation hazards overlaid on the grid.
    """

    def __init__(
        self,
        depth_data: np.ndarray,
        bottom_type: np.ndarray,
        config: BathymetryConfig,
        hazards: list[NavigationHazard] | None = None,
    ) -> None:
        if depth_data.ndim != 2:
            raise ValueError("depth_data must be 2-D")
        if depth_data.shape != bottom_type.shape:
            raise ValueError("depth_data and bottom_type must have the same shape")
        self._depth = depth_data.astype(np.float64, copy=False)
        self._bottom = bottom_type.astype(np.int32, copy=False)
        self._config = config
        self._hazards = list(hazards) if hazards else []

    # ------------------------------------------------------------------
    # Core queries
    # ------------------------------------------------------------------

    def depth_at(self, pos: Position) -> Meters:
        """Bilinear-interpolated depth at an ENU position.

        Positive values = depth below MSL.  Zero or negative = land.
        """
        col_f, row_f = self._enu_to_grid_float(pos)
        return float(self._bilinear(row_f, col_f))

    def bottom_type_at(self, pos: Position) -> BottomType:
        """Seabed type at the nearest grid cell."""
        row, col = self._enu_to_grid(pos)
        return BottomType(self._bottom[row, col])

    def is_navigable(self, pos: Position, draft: Meters) -> bool:
        """True if water depth >= *draft* and no hazards block passage."""
        depth = self.depth_at(pos)
        if depth < draft:
            return False
        for hz in self._hazards:
            dist = math.sqrt(
                (pos.easting - hz.position[0]) ** 2
                + (pos.northing - hz.position[1]) ** 2
            )
            if dist <= hz.radius and hz.minimum_depth < draft:
                return False
        return True

    def hazards_near(self, pos: Position, radius: Meters) -> list[NavigationHazard]:
        """Return all hazards within *radius* metres of *pos*."""
        result: list[NavigationHazard] = []
        for hz in self._hazards:
            dist = math.sqrt(
                (pos.easting - hz.position[0]) ** 2
                + (pos.northing - hz.position[1]) ** 2
            )
            if dist <= radius:
                result.append(hz)
        return result

    def in_bounds(self, pos: Position) -> bool:
        """True if the ENU position falls within the grid extent."""
        col_f, row_f = self._enu_to_grid_float(pos)
        return (
            0 <= row_f <= self._depth.shape[0] - 1
            and 0 <= col_f <= self._depth.shape[1] - 1
        )

    @property
    def shape(self) -> tuple[int, int]:
        return (self._depth.shape[0], self._depth.shape[1])

    @property
    def cell_size(self) -> Meters:
        return self._config.cell_size

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        return {
            "depth": self._depth.tolist(),
            "bottom": self._bottom.tolist(),
            "config": self._config.model_dump(),
            "hazards": [h.model_dump() for h in self._hazards],
        }

    def set_state(self, state: dict) -> None:
        self._depth = np.array(state["depth"], dtype=np.float64)
        self._bottom = np.array(state["bottom"], dtype=np.int32)
        self._config = BathymetryConfig.model_validate(state["config"])
        self._hazards = [NavigationHazard.model_validate(h) for h in state["hazards"]]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _enu_to_grid_float(self, pos: Position) -> tuple[float, float]:
        """Return fractional (col, row) for an ENU position."""
        col_f = (pos.easting - self._config.origin_easting) / self._config.cell_size - 0.5
        row_f = (pos.northing - self._config.origin_northing) / self._config.cell_size - 0.5
        return (col_f, row_f)

    def _enu_to_grid(self, pos: Position) -> tuple[int, int]:
        """Nearest grid cell, clamped to bounds."""
        col_f, row_f = self._enu_to_grid_float(pos)
        row = int(max(0, min(round(row_f), self._depth.shape[0] - 1)))
        col = int(max(0, min(round(col_f), self._depth.shape[1] - 1)))
        return (row, col)

    def _bilinear(self, row_f: float, col_f: float) -> float:
        """Bilinear interpolation of the depth grid."""
        nrows, ncols = self._depth.shape
        row_f = max(0.0, min(row_f, nrows - 1.0))
        col_f = max(0.0, min(col_f, ncols - 1.0))

        r0 = int(np.floor(row_f))
        c0 = int(np.floor(col_f))
        r1 = min(r0 + 1, nrows - 1)
        c1 = min(c0 + 1, ncols - 1)

        dr = row_f - r0
        dc = col_f - c0

        v00 = self._depth[r0, c0]
        v01 = self._depth[r0, c1]
        v10 = self._depth[r1, c0]
        v11 = self._depth[r1, c1]

        return float(
            v00 * (1 - dr) * (1 - dc)
            + v01 * (1 - dr) * dc
            + v10 * dr * (1 - dc)
            + v11 * dr * dc
        )
