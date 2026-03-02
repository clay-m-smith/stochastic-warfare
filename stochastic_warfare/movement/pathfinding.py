"""A* pathfinding over terrain grids."""

from __future__ import annotations

import heapq
import math
from typing import NamedTuple

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

    def movement_cost(
        self, from_pos: Position, to_pos: Position, unit=None
    ) -> float:
        """Compute the movement cost between two adjacent grid cells."""
        dx = to_pos.easting - from_pos.easting
        dy = to_pos.northing - from_pos.northing
        dist = math.sqrt(dx * dx + dy * dy)

        # Base cost = distance
        cost = dist

        # Terrain trafficability penalty
        if self._classification is not None:
            trafficability = self._classification.trafficability_at(to_pos)
            if trafficability <= 0.01:
                return float("inf")  # impassable
            cost /= trafficability

        # Slope penalty
        if self._heightmap is not None:
            slope = self._heightmap.slope_at(to_pos)
            cost *= 1.0 + 2.0 * abs(slope)

        # Road bonus — reduce cost
        if self._infrastructure is not None:
            road_factor = self._infrastructure.road_speed_at(to_pos)
            if road_factor is not None and road_factor > 1.0:
                cost /= road_factor

        # Obstacle penalty
        if self._obstacles is not None:
            obs = self._obstacles.obstacles_at(to_pos)
            for o in obs:
                cost *= o.traversal_time_multiplier

        # Water penalty
        if self._hydrography is not None and self._hydrography.is_in_water(to_pos):
            cost *= 10.0  # heavy penalty for water crossing

        return cost

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

        # Threat cost cache
        threat_cost_fn = None
        if avoid_threats:
            def threat_cost_fn(pos: Position) -> float:
                extra = 0.0
                for tp, tr in avoid_threats:
                    dx = pos.easting - tp.easting
                    dy = pos.northing - tp.northing
                    d = math.sqrt(dx * dx + dy * dy)
                    if d < tr:
                        extra += (tr - d) / tr * res * 5.0
                return extra

        # A* with 8-connectivity
        open_set: list[tuple[float, int, tuple[int, int]]] = []
        counter = 0
        heapq.heappush(open_set, (0.0, counter, start_g))
        came_from: dict[tuple[int, int], tuple[int, int] | None] = {start_g: None}
        g_score: dict[tuple[int, int], float] = {start_g: 0.0}

        neighbors_8 = [
            (-1, -1), (-1, 0), (-1, 1), (0, -1),
            (0, 1), (1, -1), (1, 0), (1, 1),
        ]

        iterations = 0
        while open_set and iterations < max_iterations:
            iterations += 1
            _, _, current = heapq.heappop(open_set)

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

            cur_pos = to_pos(current)
            for dx, dy in neighbors_8:
                nb = (current[0] + dx, current[1] + dy)
                nb_pos = to_pos(nb)

                edge_cost = self.movement_cost(cur_pos, nb_pos, unit)
                if edge_cost == float("inf"):
                    continue

                if threat_cost_fn is not None:
                    edge_cost += threat_cost_fn(nb_pos)

                tentative = g_score[current] + edge_cost

                if nb not in g_score or tentative < g_score[nb]:
                    g_score[nb] = tentative
                    f = tentative + heuristic(nb, goal_g)
                    counter += 1
                    heapq.heappush(open_set, (f, counter, nb))
                    came_from[nb] = current

        # No path found
        return PathResult([], float("inf"), 0.0, False)
