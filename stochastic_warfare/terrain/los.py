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

        Uses vectorized numpy operations for the ray march when no
        infrastructure (building) data is present — the common case.
        Falls back to per-sample scalar lookups when buildings must be
        checked.
        """
        obs_elev = self._hm.elevation_at(observer) + observer_height
        tgt_elev = self._hm.elevation_at(target) + target_height

        dx = target.easting - observer.easting
        dy = target.northing - observer.northing
        total_dist = math.sqrt(dx * dx + dy * dy)

        if total_dist < 1.0:
            return LOSResult(True, None, None, None)

        # Earth curvature constants
        _K_FACTOR = 4.0 / 3.0
        _R_EARTH = 6_371_000.0

        num_steps = max(2, int(total_dist / (self._hm.cell_size / 2.0)))

        if self._infra is None:
            return self._check_los_vectorized(
                observer, obs_elev, tgt_elev, dx, dy, total_dist,
                num_steps, _K_FACTOR, _R_EARTH,
            )

        return self._check_los_scalar(
            observer, obs_elev, tgt_elev, dx, dy, total_dist,
            num_steps, _K_FACTOR, _R_EARTH,
        )

    def _check_los_vectorized(
        self,
        observer: Position,
        obs_elev: float,
        tgt_elev: float,
        dx: float,
        dy: float,
        total_dist: float,
        num_steps: int,
        k_factor: float,
        r_earth: float,
    ) -> LOSResult:
        """Fully vectorized LOS ray march (no infrastructure)."""
        fracs = np.arange(1, num_steps, dtype=np.float64) / num_steps
        d = fracs * total_dist

        sample_e = observer.easting + dx * fracs
        sample_n = observer.northing + dy * fracs

        # Vectorized bounds check
        in_bounds = self._hm.in_bounds_batch(sample_e, sample_n)
        if not np.any(in_bounds):
            return LOSResult(True, None, None, None)

        # Vectorized bilinear elevation lookup
        terrain_elev = self._hm.elevation_at_batch(sample_e, sample_n)

        # Earth curvature drop
        curvature_drop = (d * (total_dist - d)) / (2 * k_factor * r_earth)

        # Ray elevation (linear interpolation)
        ray_elev = obs_elev + (tgt_elev - obs_elev) * fracs - curvature_drop

        # Clearance — set out-of-bounds samples to +inf (non-blocking)
        clearance = ray_elev - terrain_elev
        clearance[~in_bounds] = np.inf

        # Check for blocked
        blocked_mask = clearance < 0
        if np.any(blocked_mask):
            idx = int(np.argmax(blocked_mask))
            return LOSResult(
                False,
                Position(float(sample_e[idx]), float(sample_n[idx])),
                "terrain",
                0.0,
            )

        valid_clearance = clearance[in_bounds]
        min_clearance = float(np.min(valid_clearance)) if len(valid_clearance) > 0 else None
        return LOSResult(True, None, None, min_clearance)

    def _check_los_scalar(
        self,
        observer: Position,
        obs_elev: float,
        tgt_elev: float,
        dx: float,
        dy: float,
        total_dist: float,
        num_steps: int,
        k_factor: float,
        r_earth: float,
    ) -> LOSResult:
        """Scalar LOS ray march (with infrastructure/building checks)."""
        min_clearance = float("inf")

        for i in range(1, num_steps):
            frac = i / num_steps
            d = frac * total_dist

            sample_e = observer.easting + dx * frac
            sample_n = observer.northing + dy * frac
            sample_pos = Position(sample_e, sample_n)

            if not self._hm.in_bounds(sample_pos):
                continue

            terrain_elev = self._hm.elevation_at(sample_pos)

            building_h = 0.0
            if self._infra is not None:
                building_h = self._infra.max_building_height_at(sample_pos)

            surface_elev = terrain_elev + building_h

            curvature_drop = (d * (total_dist - d)) / (2 * k_factor * r_earth)
            ray_elev = obs_elev + (tgt_elev - obs_elev) * frac - curvature_drop
            clearance = ray_elev - surface_elev

            if clearance < min_clearance:
                min_clearance = clearance

            if clearance < 0:
                blocked_by = "building" if building_h > 0 else "terrain"
                return LOSResult(False, sample_pos, blocked_by, 0.0)

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
