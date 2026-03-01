"""Infrastructure features: roads, bridges, buildings, airfields, rail, tunnels.

Vector features stored as shapely geometries with mutable ``condition``
(0.0 = destroyed, 1.0 = pristine).  Spatial queries use brute-force
iteration; STRtree optimization can be added later if profiling warrants it.
"""

from __future__ import annotations

import enum
import math

from pydantic import BaseModel
from shapely.geometry import LineString, Point, Polygon

from stochastic_warfare.core.types import Meters, Position


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class RoadType(enum.IntEnum):
    """Road surface classification."""

    HIGHWAY = 0
    PAVED = 1
    IMPROVED_DIRT = 2
    UNIMPROVED = 3
    TRAIL = 4


# Speed factor by road type (fraction of max off-road speed increase)
_ROAD_SPEED_FACTORS: dict[RoadType, float] = {
    RoadType.HIGHWAY: 3.0,
    RoadType.PAVED: 2.5,
    RoadType.IMPROVED_DIRT: 1.5,
    RoadType.UNIMPROVED: 1.2,
    RoadType.TRAIL: 1.0,
}


# ---------------------------------------------------------------------------
# Feature models
# ---------------------------------------------------------------------------


class Road(BaseModel):
    """A road segment."""

    road_id: str
    road_type: RoadType
    points: list[tuple[float, float]]  # [(easting, northing), ...]
    width: float = 6.0  # meters
    speed_factor: float | None = None  # override default
    capacity: float = 100.0  # vehicles per hour
    condition: float = 1.0  # 0.0 destroyed – 1.0 pristine


class Bridge(BaseModel):
    """A bridge along a road."""

    bridge_id: str
    position: tuple[float, float]  # (easting, northing)
    road_id: str
    capacity_tons: float = 40.0
    condition: float = 1.0


class Building(BaseModel):
    """A building footprint."""

    building_id: str
    footprint: list[tuple[float, float]]  # polygon vertices
    height: float = 10.0  # meters
    construction: str = "concrete"  # concrete, masonry, wood
    cover_value: float = 0.7  # 0–1
    condition: float = 1.0


class Airfield(BaseModel):
    """An airfield / landing strip."""

    airfield_id: str
    position: tuple[float, float]
    runway_length: float = 2000.0  # meters
    runway_surface: str = "paved"  # paved, grass, dirt
    condition: float = 1.0


class RailLine(BaseModel):
    """A railway line segment."""

    rail_id: str
    points: list[tuple[float, float]]
    gauge: str = "standard"  # standard, narrow, broad
    condition: float = 1.0


class Tunnel(BaseModel):
    """A tunnel (road or rail)."""

    tunnel_id: str
    entry_points: list[tuple[float, float]]  # two entry positions
    road_id: str | None = None
    rail_id: str | None = None


# ---------------------------------------------------------------------------
# InfrastructureManager
# ---------------------------------------------------------------------------


class InfrastructureManager:
    """Manages all infrastructure features with spatial queries.

    Parameters
    ----------
    roads, bridges, buildings, airfields, tunnels, rail_lines:
        Lists of feature models.  All are optional (default to empty).
    """

    def __init__(
        self,
        roads: list[Road] | None = None,
        bridges: list[Bridge] | None = None,
        buildings: list[Building] | None = None,
        airfields: list[Airfield] | None = None,
        tunnels: list[Tunnel] | None = None,
        rail_lines: list[RailLine] | None = None,
    ) -> None:
        self._roads = {r.road_id: r for r in (roads or [])}
        self._bridges = {b.bridge_id: b for b in (bridges or [])}
        self._buildings = {b.building_id: b for b in (buildings or [])}
        self._airfields = {a.airfield_id: a for a in (airfields or [])}
        self._tunnels = {t.tunnel_id: t for t in (tunnels or [])}
        self._rail_lines = {r.rail_id: r for r in (rail_lines or [])}

        # Pre-build shapely geometries
        self._road_geoms: dict[str, LineString] = {
            rid: LineString(r.points) for rid, r in self._roads.items()
        }
        self._building_geoms: dict[str, Polygon] = {
            bid: Polygon(b.footprint) for bid, b in self._buildings.items()
        }

    # ------------------------------------------------------------------
    # Spatial queries — roads
    # ------------------------------------------------------------------

    def roads_near(self, pos: Position, radius: Meters) -> list[Road]:
        """Return all roads within *radius* metres of *pos*."""
        pt = Point(pos.easting, pos.northing)
        return [
            self._roads[rid]
            for rid, geom in self._road_geoms.items()
            if geom.distance(pt) <= radius and self._roads[rid].condition > 0
        ]

    def nearest_road(self, pos: Position) -> tuple[Road, Meters] | None:
        """Return the closest non-destroyed road and the distance to it."""
        pt = Point(pos.easting, pos.northing)
        best: tuple[Road, float] | None = None
        for rid, geom in self._road_geoms.items():
            road = self._roads[rid]
            if road.condition <= 0:
                continue
            d = geom.distance(pt)
            if best is None or d < best[1]:
                best = (road, d)
        return best

    def road_speed_at(self, pos: Position) -> float | None:
        """Speed factor of the nearest road if within its width, else None."""
        result = self.nearest_road(pos)
        if result is None:
            return None
        road, dist = result
        if dist > road.width / 2:
            return None
        sf = road.speed_factor if road.speed_factor is not None else _ROAD_SPEED_FACTORS.get(road.road_type, 1.0)
        return sf * road.condition

    # ------------------------------------------------------------------
    # Spatial queries — buildings
    # ------------------------------------------------------------------

    def buildings_at(self, pos: Position) -> list[Building]:
        """Return buildings whose footprint contains *pos*."""
        pt = Point(pos.easting, pos.northing)
        return [
            self._buildings[bid]
            for bid, geom in self._building_geoms.items()
            if geom.contains(pt) and self._buildings[bid].condition > 0
        ]

    def buildings_near(self, pos: Position, radius: Meters) -> list[Building]:
        """Return buildings within *radius* of *pos*."""
        pt = Point(pos.easting, pos.northing)
        return [
            self._buildings[bid]
            for bid, geom in self._building_geoms.items()
            if geom.distance(pt) <= radius and self._buildings[bid].condition > 0
        ]

    def max_building_height_at(self, pos: Position) -> Meters:
        """Maximum building height at *pos* (0 if no building)."""
        bldgs = self.buildings_at(pos)
        if not bldgs:
            return 0.0
        return max(b.height * b.condition for b in bldgs)

    # ------------------------------------------------------------------
    # Spatial queries — airfields
    # ------------------------------------------------------------------

    def airfields_near(self, pos: Position, radius: Meters) -> list[Airfield]:
        """Return airfields within *radius* of *pos*."""
        return [
            a for a in self._airfields.values()
            if a.condition > 0
            and math.sqrt(
                (pos.easting - a.position[0]) ** 2
                + (pos.northing - a.position[1]) ** 2
            ) <= radius
        ]

    # ------------------------------------------------------------------
    # Mutable state
    # ------------------------------------------------------------------

    def damage(self, feature_id: str, amount: float) -> None:
        """Reduce condition of any feature by *amount* (clamped to 0)."""
        for store in (self._roads, self._bridges, self._buildings,
                      self._airfields, self._tunnels, self._rail_lines):
            if feature_id in store:
                feat = store[feature_id]
                feat.condition = max(0.0, feat.condition - amount)  # type: ignore[union-attr]
                return
        raise KeyError(f"Unknown feature: {feature_id}")

    def repair(self, feature_id: str, amount: float) -> None:
        """Increase condition of any feature by *amount* (clamped to 1)."""
        for store in (self._roads, self._bridges, self._buildings,
                      self._airfields, self._tunnels, self._rail_lines):
            if feature_id in store:
                feat = store[feature_id]
                feat.condition = min(1.0, feat.condition + amount)  # type: ignore[union-attr]
                return
        raise KeyError(f"Unknown feature: {feature_id}")

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        """Capture mutable condition values for all features."""
        conditions: dict[str, float] = {}
        for store in (self._roads, self._bridges, self._buildings,
                      self._airfields, self._tunnels, self._rail_lines):
            for fid, feat in store.items():
                conditions[fid] = feat.condition  # type: ignore[union-attr]
        return {"conditions": conditions}

    def set_state(self, state: dict) -> None:
        """Restore condition values."""
        conditions = state["conditions"]
        for store in (self._roads, self._bridges, self._buildings,
                      self._airfields, self._tunnels, self._rail_lines):
            for fid, feat in store.items():
                if fid in conditions:
                    feat.condition = conditions[fid]  # type: ignore[union-attr]
