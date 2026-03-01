"""Hydrographic features: rivers, lakes, and ford points.

Rivers are modelled as shapely LineStrings buffered by width for containment
queries.  Fordability depends on river depth and an externally-supplied water
level multiplier (provided by the environment, not imported here).
"""

from __future__ import annotations

import math

from pydantic import BaseModel
from shapely.geometry import Point, Polygon
from shapely.geometry import LineString as ShapelyLineString

from stochastic_warfare.core.types import Meters, Position


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class River(BaseModel):
    """A river segment."""

    river_id: str
    name: str
    centerline: list[tuple[float, float]]  # [(easting, northing), ...]
    width: float  # meters
    depth: float  # meters (normal depth)
    current_speed: float  # m/s
    ford_points: list[tuple[float, float]] | None = None
    ford_depth: float = 0.8  # meters — max wading depth


class Lake(BaseModel):
    """A lake or reservoir."""

    lake_id: str
    name: str
    boundary: list[tuple[float, float]]  # polygon vertices
    depth: float  # average depth, meters


# ---------------------------------------------------------------------------
# HydrographyManager
# ---------------------------------------------------------------------------


class HydrographyManager:
    """Manages rivers and lakes with spatial queries.

    Parameters
    ----------
    rivers, lakes:
        Lists of feature models.
    """

    def __init__(
        self,
        rivers: list[River] | None = None,
        lakes: list[Lake] | None = None,
    ) -> None:
        self._rivers: dict[str, River] = {}
        self._river_lines: dict[str, ShapelyLineString] = {}
        self._river_polys: dict[str, Polygon] = {}
        for r in (rivers or []):
            self._rivers[r.river_id] = r
            line = ShapelyLineString(r.centerline)
            self._river_lines[r.river_id] = line
            self._river_polys[r.river_id] = line.buffer(r.width / 2)

        self._lakes: dict[str, Lake] = {}
        self._lake_polys: dict[str, Polygon] = {}
        for lk in (lakes or []):
            self._lakes[lk.lake_id] = lk
            self._lake_polys[lk.lake_id] = Polygon(lk.boundary)

    # ------------------------------------------------------------------
    # River queries
    # ------------------------------------------------------------------

    def rivers_near(self, pos: Position, radius: Meters) -> list[River]:
        """Return all rivers within *radius* of *pos*."""
        pt = Point(pos.easting, pos.northing)
        return [
            self._rivers[rid]
            for rid, line in self._river_lines.items()
            if line.distance(pt) <= radius
        ]

    def nearest_river(self, pos: Position) -> tuple[River, Meters] | None:
        """Return the nearest river and the distance to its centreline."""
        pt = Point(pos.easting, pos.northing)
        best: tuple[River, float] | None = None
        for rid, line in self._river_lines.items():
            d = line.distance(pt)
            if best is None or d < best[1]:
                best = (self._rivers[rid], d)
        return best

    # ------------------------------------------------------------------
    # Water containment
    # ------------------------------------------------------------------

    def is_in_water(self, pos: Position) -> bool:
        """True if *pos* is inside a river polygon or a lake."""
        pt = Point(pos.easting, pos.northing)
        for poly in self._river_polys.values():
            if poly.contains(pt):
                return True
        for poly in self._lake_polys.values():
            if poly.contains(pt):
                return True
        return False

    # ------------------------------------------------------------------
    # Fordability
    # ------------------------------------------------------------------

    def ford_points_near(
        self, pos: Position, radius: Meters
    ) -> list[tuple[float, float]]:
        """Return ford points within *radius* of *pos*."""
        result: list[tuple[float, float]] = []
        for river in self._rivers.values():
            if river.ford_points is None:
                continue
            for fp in river.ford_points:
                d = math.sqrt(
                    (pos.easting - fp[0]) ** 2 + (pos.northing - fp[1]) ** 2
                )
                if d <= radius:
                    result.append(fp)
        return result

    def is_fordable(
        self, river_id: str, water_level_multiplier: float = 1.0
    ) -> bool:
        """True if the river can be waded at its ford points.

        The caller supplies *water_level_multiplier* from the environment
        (e.g. seasonal flooding).  No environment import here.
        """
        river = self._rivers.get(river_id)
        if river is None:
            raise KeyError(f"Unknown river: {river_id}")
        if river.ford_points is None or len(river.ford_points) == 0:
            return False
        effective = self.effective_depth(river_id, water_level_multiplier)
        return effective <= river.ford_depth

    def effective_depth(
        self, river_id: str, water_level_multiplier: float = 1.0
    ) -> Meters:
        """Effective depth at the river's ford points."""
        river = self._rivers.get(river_id)
        if river is None:
            raise KeyError(f"Unknown river: {river_id}")
        return river.depth * water_level_multiplier

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        return {
            "rivers": [r.model_dump() for r in self._rivers.values()],
            "lakes": [lk.model_dump() for lk in self._lakes.values()],
        }

    def set_state(self, state: dict) -> None:
        self._rivers.clear()
        self._river_lines.clear()
        self._river_polys.clear()
        self._lakes.clear()
        self._lake_polys.clear()

        for rd in state["rivers"]:
            r = River.model_validate(rd)
            self._rivers[r.river_id] = r
            line = ShapelyLineString(r.centerline)
            self._river_lines[r.river_id] = line
            self._river_polys[r.river_id] = line.buffer(r.width / 2)

        for ld in state["lakes"]:
            lk = Lake.model_validate(ld)
            self._lakes[lk.lake_id] = lk
            self._lake_polys[lk.lake_id] = Polygon(lk.boundary)
