"""A* pathfinding over terrain grids."""

from __future__ import annotations

import heapq
import math
from typing import NamedTuple

import numpy as np

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import Meters, Position

logger = get_logger(__name__)


class PathResult(NamedTuple):
    """Result of a pathfinding query."""

    waypoints: list[Position]
    total_cost: float
    total_distance: Meters
    found: bool


class Pathfinder:
    """A* pathfinding over terrain.

    Discretizes the world into a grid at *grid_resolution* and finds
    minimum-cost paths considering terrain, slope, roads, and obstacles.

    Parameters
    ----------
    heightmap:
        Terrain heightmap for elevation / slope queries.
    classification:
        Terrain classification for trafficability.
    infrastructure:
        Infrastructure manager for road detection.
    obstacles:
        Obstacle manager for impassable areas.
    hydrography:
        Hydrography manager for water body detection.
    """

    def __init__(
        self,
        heightmap=None,
        classification=None,
        infrastructure=None,
        obstacles=None,
        hydrography=None,
    ) -> None:
        self._heightmap = heightmap
        self._classification = classification
        self._infrastructure = infrastructure
        self._obstacles = obstacles
        self._hydrography = hydrography

    def _cell_difficulty(self, pos: Position) -> float:
        """Terrain difficulty multiplier at *pos* (terrain factors only).

        This captures trafficability, slope, roads, obstacles, and water —
        everything that depends only on the destination cell, not the edge.
        Returns ``inf`` for impassable cells.
        """
        mult = 1.0

        if self._classification is not None:
            trafficability = self._classification.trafficability_at(pos)
            if trafficability <= 0.01:
                return float("inf")
            mult /= trafficability

        if self._heightmap is not None:
            slope = self._heightmap.slope_at(pos)
            mult *= 1.0 + 2.0 * abs(slope)

        if self._infrastructure is not None:
            road_factor = self._infrastructure.road_speed_at(pos)
            if road_factor is not None and road_factor > 1.0:
                mult /= road_factor

        if self._obstacles is not None:
            obs = self._obstacles.obstacles_at(pos)
            for o in obs:
                mult *= o.traversal_time_multiplier

        if self._hydrography is not None and self._hydrography.is_in_water(pos):
            mult *= 10.0

        return mult

    def _compute_difficulty_grid(
        self,
        min_gc: int,
        max_gc: int,
        min_gr: int,
        max_gr: int,
        res: float,
    ) -> np.ndarray:
        """Pre-compute cell difficulty for a bounding box.

        Returns a 2-D array where ``grid[r - min_gr, c - min_gc]`` gives the
        difficulty multiplier for grid cell ``(c, r)``.

        Parameters
        ----------
        min_gc, max_gc:
            Column range (inclusive).
        min_gr, max_gr:
            Row range (inclusive).
        res:
            Grid resolution in meters.
        """
        height = max_gr - min_gr + 1
        width = max_gc - min_gc + 1
        grid = np.full((height, width), 1.0, dtype=np.float64)

        for dr in range(height):
            for dc in range(width):
                gc = min_gc + dc
                gr = min_gr + dr
                pos = Position(gc * res, gr * res, 0.0)
                grid[dr, dc] = self._cell_difficulty(pos)

        return grid

    def movement_cost(
        self, from_pos: Position, to_pos: Position, unit=None
    ) -> float:
        """Compute the movement cost between two adjacent grid cells."""
        dx = to_pos.easting - from_pos.easting
        dy = to_pos.northing - from_pos.northing
        dist = math.sqrt(dx * dx + dy * dy)

        difficulty = self._cell_difficulty(to_pos)
        if difficulty == float("inf"):
            return float("inf")

        return dist * difficulty

    def find_path(
        self,
        start: Position,
        goal: Position,
        unit=None,
        avoid_threats: list[tuple[Position, float]] | None = None,
        grid_resolution: float = 100.0,
        max_iterations: int = 10000,
    ) -> PathResult:
        """Find minimum-cost path from *start* to *goal*.

        Parameters
        ----------
        avoid_threats:
            List of (position, radius) threat zones that add cost.
        grid_resolution:
            Grid cell size in meters for A* discretization.
        max_iterations:
            Maximum A* iterations before giving up.
        """
        res = grid_resolution

        def to_grid(p: Position) -> tuple[int, int]:
            return (int(round(p.easting / res)), int(round(p.northing / res)))

        def to_pos(g: tuple[int, int]) -> Position:
            return Position(g[0] * res, g[1] * res, 0.0)

        start_g = to_grid(start)
        goal_g = to_grid(goal)

        if start_g == goal_g:
            return PathResult([start, goal], 0.0, 0.0, True)

        def heuristic(a: tuple[int, int], b: tuple[int, int]) -> float:
            return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) * res

        # Threat cost function + per-cell cache
        threat_cost_fn = None
        _threat_cache: dict[tuple[int, int], float] = {}
        if avoid_threats:
            def _raw_threat_cost(pos: Position) -> float:
                extra = 0.0
                for tp, tr in avoid_threats:
                    dx = pos.easting - tp.easting
                    dy = pos.northing - tp.northing
                    d = math.sqrt(dx * dx + dy * dy)
                    if d < tr:
                        extra += (tr - d) / tr * res * 5.0
                return extra

            def threat_cost_fn(cell: tuple[int, int], pos: Position) -> float:
                cached = _threat_cache.get(cell)
                if cached is not None:
                    return cached
                cost = _raw_threat_cost(pos)
                _threat_cache[cell] = cost
                return cost

        # Pre-compute diagonal/cardinal distances
        _DIAG_DIST = math.sqrt(2.0) * res
        _CARD_DIST = res

        # A* with 8-connectivity and closed set
        open_set: list[tuple[float, int, tuple[int, int]]] = []
        counter = 0
        heapq.heappush(open_set, (0.0, counter, start_g))
        came_from: dict[tuple[int, int], tuple[int, int] | None] = {start_g: None}
        g_score: dict[tuple[int, int], float] = {start_g: 0.0}
        closed: set[tuple[int, int]] = set()

        # Pre-compute difficulty grid for bounding box (Phase 13b-4)
        margin = 10  # cells beyond start/goal bounding box
        min_gc = min(start_g[0], goal_g[0]) - margin
        max_gc = max(start_g[0], goal_g[0]) + margin
        min_gr = min(start_g[1], goal_g[1]) - margin
        max_gr = max(start_g[1], goal_g[1]) + margin
        _diff_grid = self._compute_difficulty_grid(min_gc, max_gc, min_gr, max_gr, res)
        _grid_width = max_gc - min_gc + 1
        _grid_height = max_gr - min_gr + 1

        neighbors_8 = [
            (-1, -1), (-1, 0), (-1, 1), (0, -1),
            (0, 1), (1, -1), (1, 0), (1, 1),
        ]

        iterations = 0
        while open_set and iterations < max_iterations:
            iterations += 1
            _, _, current = heapq.heappop(open_set)

            if current in closed:
                continue
            closed.add(current)

            if current == goal_g:
                # Reconstruct path
                path = []
                c: tuple[int, int] | None = current
                while c is not None:
                    path.append(to_pos(c))
                    c = came_from.get(c)
                path.reverse()
                # Replace first and last with exact positions
                path[0] = start
                path[-1] = goal

                total_dist = sum(
                    math.sqrt(
                        (path[i + 1].easting - path[i].easting) ** 2
                        + (path[i + 1].northing - path[i].northing) ** 2
                    )
                    for i in range(len(path) - 1)
                )

                return PathResult(path, g_score[current], total_dist, True)

            for dx, dy in neighbors_8:
                nb = (current[0] + dx, current[1] + dy)
                if nb in closed:
                    continue

                # Grid-based difficulty lookup (Phase 13b-4)
                gc = nb[0] - min_gc
                gr = nb[1] - min_gr
                if 0 <= gc < _grid_width and 0 <= gr < _grid_height:
                    difficulty = _diff_grid[gr, gc]
                else:
                    # Outside pre-computed grid — compute on demand
                    difficulty = self._cell_difficulty(to_pos(nb))

                if difficulty == float("inf"):
                    continue

                # Distance: diagonal or cardinal
                dist = _DIAG_DIST if (dx != 0 and dy != 0) else _CARD_DIST
                edge_cost = dist * difficulty

                if threat_cost_fn is not None:
                    edge_cost += threat_cost_fn(nb, to_pos(nb))

                tentative = g_score[current] + edge_cost

                if nb not in g_score or tentative < g_score[nb]:
                    g_score[nb] = tentative
                    f = tentative + heuristic(nb, goal_g)
                    counter += 1
                    heapq.heappush(open_set, (f, counter, nb))
                    came_from[nb] = current

        # No path found
        return PathResult([], float("inf"), 0.0, False)
