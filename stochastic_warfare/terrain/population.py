"""Civilian population density and disposition layers.

Population density is stored as a raster grid (people per square kilometre).
Regional disposition (friendly / neutral / hostile) is modelled as polygonal
regions that can shift over time in response to events.
"""

from __future__ import annotations

import enum

import numpy as np
from pydantic import BaseModel
from shapely.geometry import Point, Polygon

from stochastic_warfare.core.types import Position


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Disposition(enum.IntEnum):
    """Civilian population disposition toward the player's force."""

    FRIENDLY = 0
    NEUTRAL = 1
    HOSTILE = 2


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class PopulationRegion(BaseModel):
    """A named region with a population disposition."""

    region_id: str
    name: str
    disposition: Disposition
    boundary: list[tuple[float, float]]  # polygon vertices (easting, northing)


class PopulationConfig(BaseModel):
    """Grid geometry for the population density raster."""

    origin_easting: float = 0.0
    origin_northing: float = 0.0
    cell_size: float


# ---------------------------------------------------------------------------
# PopulationManager
# ---------------------------------------------------------------------------


class PopulationManager:
    """Manages population density and regional disposition.

    Parameters
    ----------
    density:
        2-D float array of population density (people/km²).
    config:
        Grid geometry metadata.
    regions:
        Optional list of disposition regions.
    """

    def __init__(
        self,
        density: np.ndarray,
        config: PopulationConfig,
        regions: list[PopulationRegion] | None = None,
    ) -> None:
        self._density = density.astype(np.float64, copy=False)
        self._config = config
        self._regions: dict[str, PopulationRegion] = {}
        self._region_geoms: dict[str, Polygon] = {}
        for reg in (regions or []):
            self._regions[reg.region_id] = reg
            self._region_geoms[reg.region_id] = Polygon(reg.boundary)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def density_at(self, pos: Position) -> float:
        """Population density (people/km²) at an ENU position."""
        row, col = self._enu_to_grid(pos)
        return float(self._density[row, col])

    def disposition_at(self, pos: Position) -> Disposition:
        """Population disposition at *pos* (NEUTRAL if outside all regions)."""
        region = self.region_at(pos)
        if region is None:
            return Disposition.NEUTRAL
        return region.disposition

    def region_at(self, pos: Position) -> PopulationRegion | None:
        """Return the region containing *pos*, or None."""
        pt = Point(pos.easting, pos.northing)
        for rid, geom in self._region_geoms.items():
            if geom.contains(pt):
                return self._regions[rid]
        return None

    def shift_disposition(self, region_id: str, new_disposition: Disposition) -> None:
        """Change the disposition of a region."""
        if region_id not in self._regions:
            raise KeyError(f"Unknown region: {region_id}")
        self._regions[region_id].disposition = new_disposition

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        return {
            "density": self._density.tolist(),
            "config": self._config.model_dump(),
            "regions": [r.model_dump() for r in self._regions.values()],
        }

    def set_state(self, state: dict) -> None:
        self._density = np.array(state["density"], dtype=np.float64)
        self._config = PopulationConfig.model_validate(state["config"])
        self._regions.clear()
        self._region_geoms.clear()
        for rd in state["regions"]:
            reg = PopulationRegion.model_validate(rd)
            self._regions[reg.region_id] = reg
            self._region_geoms[reg.region_id] = Polygon(reg.boundary)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _enu_to_grid(self, pos: Position) -> tuple[int, int]:
        col = int(round(
            (pos.easting - self._config.origin_easting) / self._config.cell_size - 0.5
        ))
        row = int(round(
            (pos.northing - self._config.origin_northing) / self._config.cell_size - 0.5
        ))
        row = max(0, min(row, self._density.shape[0] - 1))
        col = max(0, min(col, self._density.shape[1] - 1))
        return (row, col)
