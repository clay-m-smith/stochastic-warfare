"""Elevation data layer backed by a 2-D numpy array.

Grid convention: ``grid[0, 0]`` is the south-west corner.  Row index
increases northward, column index increases eastward.  The grid origin is
specified in ENU meters.  Bilinear interpolation is used for sub-cell
queries; slope and aspect are derived from the gradient of the surface.
"""

from __future__ import annotations

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.types import Meters, Position, Radians


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class HeightmapConfig(BaseModel):
    """Metadata describing the spatial extent of a heightmap grid."""

    origin_easting: float = 0.0
    origin_northing: float = 0.0
    cell_size: float  # meters per cell
    no_data_value: float = -9999.0


# ---------------------------------------------------------------------------
# Heightmap
# ---------------------------------------------------------------------------


class Heightmap:
    """Raster elevation model with bilinear interpolation.

    Parameters
    ----------
    data:
        2-D float array of elevations (meters ASL).  ``data[0, 0]`` is the
        south-west corner of the data extent.
    config:
        Grid geometry metadata.
    """

    def __init__(self, data: np.ndarray, config: HeightmapConfig) -> None:
        if data.ndim != 2:
            raise ValueError("heightmap data must be 2-D")
        self._data = data.astype(np.float64, copy=False)
        self._config = config

        # Cached derived arrays (computed lazily)
        self._slope_grid: np.ndarray | None = None
        self._aspect_grid: np.ndarray | None = None

    # ------------------------------------------------------------------
    # Core queries
    # ------------------------------------------------------------------

    def elevation_at(self, pos: Position) -> Meters:
        """Bilinear-interpolated elevation at an ENU position."""
        col_f, row_f = self._enu_to_grid_float(pos)
        return float(self._bilinear(row_f, col_f))

    def elevation_at_grid(self, row: int, col: int) -> Meters:
        """Elevation at an integer grid cell."""
        return float(self._data[row, col])

    def slope_at(self, pos: Position) -> Radians:
        """Terrain slope (steepest descent angle) at an ENU position."""
        col_f, row_f = self._enu_to_grid_float(pos)
        row, col = int(np.clip(round(row_f), 0, self._data.shape[0] - 1)), int(
            np.clip(round(col_f), 0, self._data.shape[1] - 1)
        )
        return float(self.slope_grid()[row, col])

    def aspect_at(self, pos: Position) -> Radians:
        """Downhill direction (north-referenced azimuth) at an ENU position."""
        col_f, row_f = self._enu_to_grid_float(pos)
        row, col = int(np.clip(round(row_f), 0, self._data.shape[0] - 1)), int(
            np.clip(round(col_f), 0, self._data.shape[1] - 1)
        )
        return float(self.aspect_grid()[row, col])

    def slope_grid(self) -> np.ndarray:
        """Full slope array (cached).  Units: radians."""
        if self._slope_grid is None:
            self._compute_gradients()
        return self._slope_grid  # type: ignore[return-value]

    def aspect_grid(self) -> np.ndarray:
        """Full aspect array (cached).  Units: radians, 0 = north."""
        if self._aspect_grid is None:
            self._compute_gradients()
        return self._aspect_grid  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Grid geometry
    # ------------------------------------------------------------------

    def grid_to_enu(self, row: int, col: int) -> Position:
        """Convert integer grid indices to an ENU position (cell centre)."""
        easting = self._config.origin_easting + (col + 0.5) * self._config.cell_size
        northing = self._config.origin_northing + (row + 0.5) * self._config.cell_size
        return Position(easting, northing, float(self._data[row, col]))

    def enu_to_grid(self, pos: Position) -> tuple[int, int]:
        """Convert an ENU position to the nearest grid cell (row, col)."""
        col_f, row_f = self._enu_to_grid_float(pos)
        row = int(np.clip(round(row_f), 0, self._data.shape[0] - 1))
        col = int(np.clip(round(col_f), 0, self._data.shape[1] - 1))
        return (row, col)

    def in_bounds(self, pos: Position) -> bool:
        """True if the ENU position falls within the grid extent."""
        col_f, row_f = self._enu_to_grid_float(pos)
        return (
            0 <= row_f <= self._data.shape[0] - 1
            and 0 <= col_f <= self._data.shape[1] - 1
        )

    @property
    def shape(self) -> tuple[int, int]:
        """(rows, cols) of the underlying grid."""
        return (self._data.shape[0], self._data.shape[1])

    @property
    def cell_size(self) -> Meters:
        return self._config.cell_size

    @property
    def extent(self) -> tuple[float, float, float, float]:
        """Spatial extent as (min_easting, max_easting, min_northing, max_northing)."""
        rows, cols = self._data.shape
        return (
            self._config.origin_easting,
            self._config.origin_easting + cols * self._config.cell_size,
            self._config.origin_northing,
            self._config.origin_northing + rows * self._config.cell_size,
        )

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        return {
            "data": self._data.tolist(),
            "config": self._config.model_dump(),
        }

    def set_state(self, state: dict) -> None:
        self._data = np.array(state["data"], dtype=np.float64)
        self._config = HeightmapConfig.model_validate(state["config"])
        self._slope_grid = None
        self._aspect_grid = None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _enu_to_grid_float(self, pos: Position) -> tuple[float, float]:
        """Return fractional (col, row) for an ENU position."""
        col_f = (pos.easting - self._config.origin_easting) / self._config.cell_size - 0.5
        row_f = (pos.northing - self._config.origin_northing) / self._config.cell_size - 0.5
        return (col_f, row_f)

    def _bilinear(self, row_f: float, col_f: float) -> float:
        """Bilinear interpolation of the elevation grid."""
        nrows, ncols = self._data.shape

        # Clamp to valid range
        row_f = max(0.0, min(row_f, nrows - 1.0))
        col_f = max(0.0, min(col_f, ncols - 1.0))

        r0 = int(np.floor(row_f))
        c0 = int(np.floor(col_f))
        r1 = min(r0 + 1, nrows - 1)
        c1 = min(c0 + 1, ncols - 1)

        dr = row_f - r0
        dc = col_f - c0

        v00 = self._data[r0, c0]
        v01 = self._data[r0, c1]
        v10 = self._data[r1, c0]
        v11 = self._data[r1, c1]

        return float(
            v00 * (1 - dr) * (1 - dc)
            + v01 * (1 - dr) * dc
            + v10 * dr * (1 - dc)
            + v11 * dr * dc
        )

    def _compute_gradients(self) -> None:
        """Compute slope and aspect grids from elevation via np.gradient."""
        cs = self._config.cell_size
        # np.gradient returns [dz/drow, dz/dcol] — row increases northward
        dz_dn, dz_de = np.gradient(self._data, cs)

        self._slope_grid = np.arctan(np.sqrt(dz_de**2 + dz_dn**2))
        # Aspect: azimuth of downhill direction (north-referenced)
        # Downhill = negative gradient direction
        self._aspect_grid = np.arctan2(-dz_de, -dz_dn) % (2 * np.pi)
