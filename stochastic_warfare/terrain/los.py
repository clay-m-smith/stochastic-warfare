"""Line-of-sight analysis: DDA raycasting through the heightmap grid.

Checks terrain and building obstructions.  Earth curvature correction
applied for ranges > 2 km using the 4/3 effective earth radius model.
"""

from __future__ import annotations

import math
from typing import NamedTuple

import numpy as np

from stochastic_warfare.core.types import Meters, Position
from stochastic_warfare.terrain.heightmap import Heightmap
from stochastic_warfare.terrain.infrastructure import InfrastructureManager


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


class LOSResult(NamedTuple):
    """Line-of-sight check result."""

    visible: bool
    blocked_at: Position | None
    blocked_by: str | None  # "terrain" or "building"
    grazing_distance: Meters | None  # closest clearance distance


# ---------------------------------------------------------------------------
# LOSEngine
# ---------------------------------------------------------------------------


class LOSEngine:
    """Terrain-aware line-of-sight analysis.

    Parameters
    ----------
    heightmap:
        Elevation data.
    infrastructure:
        Optional building data for obstruction checking.
    """

    def __init__(
        self,
        heightmap: Heightmap,
        infrastructure: InfrastructureManager | None = None,
    ) -> None:
        self._hm = heightmap
        self._infra = infrastructure

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_los(
        self,
        observer: Position,
        target: Position,
        observer_height: Meters = 1.8,
        target_height: Meters = 0.0,
    ) -> LOSResult:
        """Check line of sight from observer to target.

        Returns a :class:`LOSResult` indicating whether the target is
        visible and, if not, what blocks the view.
        """
        obs_elev = self._hm.elevation_at(observer) + observer_height
        tgt_elev = self._hm.elevation_at(target) + target_height

        dx = target.easting - observer.easting
        dy = target.northing - observer.northing
        total_dist = math.sqrt(dx * dx + dy * dy)

        if total_dist < 1.0:
            return LOSResult(True, None, None, None)

        # Earth curvature correction factor
        k_factor = 4.0 / 3.0
        R_earth = 6_371_000.0

        # Step along the ray at cell_size resolution
        step = self._hm.cell_size / 2.0
        num_steps = max(2, int(total_dist / step))
        step = total_dist / num_steps

        min_clearance = float("inf")
        blocked_at: Position | None = None
        blocked_by: str | None = None

        for i in range(1, num_steps):
            frac = i / num_steps
            d = frac * total_dist

            sample_e = observer.easting + dx * frac
            sample_n = observer.northing + dy * frac
            sample_pos = Position(sample_e, sample_n)

            if not self._hm.in_bounds(sample_pos):
                continue

            # Terrain elevation at sample point
            terrain_elev = self._hm.elevation_at(sample_pos)

            # Building height
            building_h = 0.0
            if self._infra is not None:
                building_h = self._infra.max_building_height_at(sample_pos)

            surface_elev = terrain_elev + building_h

            # Earth curvature drop
            curvature_drop = (d * (total_dist - d)) / (2 * k_factor * R_earth)

            # Expected ray elevation at this distance (linear interpolation)
            ray_elev = obs_elev + (tgt_elev - obs_elev) * frac - curvature_drop

            clearance = ray_elev - surface_elev

            if clearance < min_clearance:
                min_clearance = clearance

            if clearance < 0:
                blocked_at = sample_pos
                blocked_by = "building" if building_h > 0 else "terrain"
                return LOSResult(False, blocked_at, blocked_by, 0.0)

        grazing = min_clearance if min_clearance < float("inf") else None
        return LOSResult(True, None, None, grazing)

    def visible_area(
        self,
        observer: Position,
        max_range: Meters,
        observer_height: Meters = 1.8,
        resolution: Meters | None = None,
    ) -> np.ndarray:
        """Compute a viewshed (boolean grid) around the observer.

        Returns a 2-D boolean array aligned with the heightmap where
        True = visible from the observer position.
        """
        rows, cols = self._hm.shape
        viewshed = np.zeros((rows, cols), dtype=bool)

        for r in range(rows):
            for c in range(cols):
                target = self._hm.grid_to_enu(r, c)
                dist = math.sqrt(
                    (target.easting - observer.easting) ** 2
                    + (target.northing - observer.northing) ** 2
                )
                if dist > max_range:
                    continue
                result = self.check_los(observer, target, observer_height)
                viewshed[r, c] = result.visible

        return viewshed

    def los_profile(
        self, observer: Position, target: Position
    ) -> tuple[np.ndarray, np.ndarray]:
        """Return the elevation profile along the LOS ray.

        Returns (distances, elevations) arrays.
        """
        dx = target.easting - observer.easting
        dy = target.northing - observer.northing
        total_dist = math.sqrt(dx * dx + dy * dy)

        num_samples = max(2, int(total_dist / (self._hm.cell_size / 2)))
        distances = np.linspace(0, total_dist, num_samples)
        elevations = np.zeros(num_samples)

        for i, d in enumerate(distances):
            frac = d / total_dist if total_dist > 0 else 0
            e = observer.easting + dx * frac
            n = observer.northing + dy * frac
            pos = Position(e, n)
            if self._hm.in_bounds(pos):
                elevations[i] = self._hm.elevation_at(pos)
            else:
                elevations[i] = 0.0

        return (distances, elevations)
