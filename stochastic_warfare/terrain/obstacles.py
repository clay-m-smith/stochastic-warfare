"""Obstacle features: minefields, wire, ditches, barriers, fortifications.

Obstacles are polygon-based features that can be emplaced, breached, or
cleared by engineer units.  Natural obstacles (ravines, cliffs, dense forest)
cannot be cleared.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel
from shapely.geometry import Point, Polygon, box

from stochastic_warfare.core.types import Meters, Position


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ObstacleType(enum.IntEnum):
    """Types of obstacles."""

    MINEFIELD = 0
    WIRE = 1
    ANTI_TANK_DITCH = 2
    BARRIER = 3
    FORTIFICATION = 4
    RAVINE = 5
    CLIFF = 6
    DENSE_FOREST = 7


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


class Obstacle(BaseModel):
    """An obstacle feature with polygon footprint."""

    obstacle_id: str
    obstacle_type: ObstacleType
    footprint: list[tuple[float, float]]  # polygon vertices (easting, northing)
    density: float = 1.0  # 0–1
    condition: float = 1.0  # 0 = cleared/breached, 1 = intact
    is_natural: bool = False
    traversal_risk: float = 0.0  # 0–1 probability of casualty per crossing
    traversal_time_multiplier: float = 5.0  # movement time multiplier


# ---------------------------------------------------------------------------
# ObstacleManager
# ---------------------------------------------------------------------------


class ObstacleManager:
    """Manages emplacement, breaching, and querying of obstacles.

    Parameters
    ----------
    obstacles:
        Initial list of obstacles.
    """

    def __init__(self, obstacles: list[Obstacle] | None = None) -> None:
        self._obstacles: dict[str, Obstacle] = {}
        self._geoms: dict[str, Polygon] = {}
        for obs in (obstacles or []):
            self._add(obs)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def obstacles_at(self, pos: Position) -> list[Obstacle]:
        """Return all obstacles containing *pos* with condition > 0."""
        pt = Point(pos.easting, pos.northing)
        return [
            self._obstacles[oid]
            for oid, geom in self._geoms.items()
            if geom.contains(pt) and self._obstacles[oid].condition > 0
        ]

    def obstacles_in_area(
        self, min_pos: Position, max_pos: Position
    ) -> list[Obstacle]:
        """Return obstacles intersecting the axis-aligned bounding box."""
        bbox = box(min_pos.easting, min_pos.northing,
                   max_pos.easting, max_pos.northing)
        return [
            self._obstacles[oid]
            for oid, geom in self._geoms.items()
            if geom.intersects(bbox) and self._obstacles[oid].condition > 0
        ]

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def emplace(self, obstacle: Obstacle) -> None:
        """Add a new obstacle to the battlefield."""
        if obstacle.obstacle_id in self._obstacles:
            raise ValueError(f"Obstacle {obstacle.obstacle_id} already exists")
        self._add(obstacle)

    def breach(self, obstacle_id: str, breach_width: Meters) -> None:
        """Reduce an obstacle's condition (partial breach)."""
        obs = self._obstacles.get(obstacle_id)
        if obs is None:
            raise KeyError(f"Unknown obstacle: {obstacle_id}")
        if obs.is_natural:
            return  # natural obstacles cannot be breached
        # Reduce condition proportional to breach width vs obstacle area
        geom = self._geoms[obstacle_id]
        if geom.length > 0:
            reduction = min(1.0, breach_width / geom.length)
        else:
            reduction = 1.0
        obs.condition = max(0.0, obs.condition - reduction)

    def clear(self, obstacle_id: str) -> None:
        """Fully clear an obstacle (set condition to 0)."""
        obs = self._obstacles.get(obstacle_id)
        if obs is None:
            raise KeyError(f"Unknown obstacle: {obstacle_id}")
        if obs.is_natural:
            return  # natural obstacles cannot be cleared
        obs.condition = 0.0

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        return {
            "obstacles": [obs.model_dump() for obs in self._obstacles.values()],
        }

    def set_state(self, state: dict) -> None:
        self._obstacles.clear()
        self._geoms.clear()
        for obs_data in state["obstacles"]:
            self._add(Obstacle.model_validate(obs_data))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _add(self, obs: Obstacle) -> None:
        self._obstacles[obs.obstacle_id] = obs
        self._geoms[obs.obstacle_id] = Polygon(obs.footprint)
