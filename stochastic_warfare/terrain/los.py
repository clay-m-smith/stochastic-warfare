"""Line-of-sight analysis: DDA raycasting through the heightmap grid.

Checks terrain and building obstructions.  Earth curvature correction
applied for ranges > 2 km using the 4/3 effective earth radius model.

Phase 13a-4: Multi-tick LOS cache with selective invalidation based on
dirty grid cells (units that moved).
Phase 13a-5: Vectorized viewshed computation using numpy broadcasting.
"""

from __future__ import annotations

import math
from typing import NamedTuple

import numpy as np

from stochastic_warfare.core.numba_utils import optional_jit
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
# JIT kernel for terrain-only ray march
# ---------------------------------------------------------------------------


@optional_jit
def _los_terrain_kernel(
    obs_e: float, obs_n: float,
    obs_elev: float, tgt_elev: float,
    dx: float, dy: float,
    total_dist: float, num_steps: int,
    k_factor: float, r_earth: float,
    heightmap_data: np.ndarray,
    origin_e: float, origin_n: float, cell_size: float,
) -> tuple[int, float]:
    """JIT-compiled terrain-only LOS ray march.

    Returns (blocked_step, min_clearance).
    blocked_step = -1 if not blocked, otherwise the step index.
    """
    min_clearance = 1e30  # large initial value
    nrows = heightmap_data.shape[0]
    ncols = heightmap_data.shape[1]

    for i in range(1, num_steps):
        frac = i / num_steps
        d = frac * total_dist

        sample_e = obs_e + dx * frac
        sample_n = obs_n + dy * frac

        # Bounds check (inline)
        col_f = (sample_e - origin_e) / cell_size - 0.5
        row_f = (sample_n - origin_n) / cell_size - 0.5
        if row_f < 0 or row_f > nrows - 1 or col_f < 0 or col_f > ncols - 1:
            continue

        # Bilinear interpolation (inline)
        r0 = int(math.floor(row_f))
        c0 = int(math.floor(col_f))
        r1 = min(r0 + 1, nrows - 1)
        c1 = min(c0 + 1, ncols - 1)
        fr = row_f - r0
        fc = col_f - c0
        terrain_elev = (
            heightmap_data[r0, c0] * (1 - fr) * (1 - fc)
            + heightmap_data[r1, c0] * fr * (1 - fc)
            + heightmap_data[r0, c1] * (1 - fr) * fc
            + heightmap_data[r1, c1] * fr * fc
        )

        # Earth curvature
        curvature_drop = (d * (total_dist - d)) / (2 * k_factor * r_earth)
        ray_elev = obs_elev + (tgt_elev - obs_elev) * frac - curvature_drop
        clearance = ray_elev - terrain_elev

        if clearance < min_clearance:
            min_clearance = clearance

        if clearance < 0:
            return (i, min_clearance)

    return (-1, min_clearance)


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

    Notes
    -----
    A per-tick LOS result cache avoids redundant ray-march computations
    when the same observer→target pair is checked more than once in a
    single simulation tick (e.g. detection and engagement in the same
    tick, or viewshed computation).  Call :meth:`clear_los_cache` at the
    start of each tick (or whenever unit positions change).
    """

    def __init__(
        self,
        heightmap: Heightmap,
        infrastructure: InfrastructureManager | None = None,
    ) -> None:
        self._hm = heightmap
        self._infra = infrastructure
        # Per-tick LOS result cache.
        # Key: (obs_row, obs_col, tgt_row, tgt_col, obs_height_cm, tgt_height_cm)
        # Value: LOSResult
        self._los_cache: dict[tuple[int, int, int, int, int, int], LOSResult] = {}

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def clear_los_cache(self) -> None:
        """Clear the per-tick LOS result cache.

        Should be called at the start of each simulation tick so that
        stale results from prior ticks (before movement) are discarded.
        """
        self._los_cache.clear()

    def invalidate_cells(self, dirty_cells: set[tuple[int, int]]) -> None:
        """Selectively invalidate cache entries involving dirty grid cells.

        Only removes entries whose observer OR target grid cell is in
        *dirty_cells*.  More efficient than :meth:`clear_los_cache` when
        only a few units moved (Phase 13a-4).

        Parameters
        ----------
        dirty_cells:
            Set of (row, col) grid cells that changed (units moved to/from).
        """
        if not dirty_cells or not self._los_cache:
            return
        keys_to_remove = [
            key for key in self._los_cache
            if (key[0], key[1]) in dirty_cells or (key[2], key[3]) in dirty_cells
        ]
        for key in keys_to_remove:
            del self._los_cache[key]

    @property
    def los_cache_size(self) -> int:
        """Number of entries currently in the LOS cache."""
        return len(self._los_cache)

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

        Results are cached by grid-cell coordinates and quantized height
        so that repeated queries for the same pair within a tick skip
        the expensive ray march.
        """
        # Build cache key from grid-cell coordinates + quantized heights
        # (centimetre precision avoids float-key issues).
        obs_row, obs_col = self._hm.enu_to_grid(observer)
        tgt_row, tgt_col = self._hm.enu_to_grid(target)
        obs_h_cm = int(round(observer_height * 100))
        tgt_h_cm = int(round(target_height * 100))

        cache_key = (obs_row, obs_col, tgt_row, tgt_col, obs_h_cm, tgt_h_cm)
        cached = self._los_cache.get(cache_key)
        if cached is not None:
            return cached

        obs_elev = self._hm.elevation_at(observer) + observer_height
        tgt_elev = self._hm.elevation_at(target) + target_height

        dx = target.easting - observer.easting
        dy = target.northing - observer.northing
        total_dist = math.sqrt(dx * dx + dy * dy)

        if total_dist < 1.0:
            result = LOSResult(True, None, None, None)
            self._los_cache[cache_key] = result
            return result

        # Earth curvature constants
        _K_FACTOR = 4.0 / 3.0
        _R_EARTH = 6_371_000.0

        num_steps = max(2, int(total_dist / (self._hm.cell_size / 2.0)))

        if self._infra is None:
            result = self._check_los_vectorized(
                observer, obs_elev, tgt_elev, dx, dy, total_dist,
                num_steps, _K_FACTOR, _R_EARTH,
            )
        else:
            result = self._check_los_scalar(
                observer, obs_elev, tgt_elev, dx, dy, total_dist,
                num_steps, _K_FACTOR, _R_EARTH,
            )

        self._los_cache[cache_key] = result
        return result

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

    def _check_los_terrain_jit(
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
        """JIT-accelerated terrain-only LOS check (no infrastructure)."""
        blocked_step, min_clearance = _los_terrain_kernel(
            observer.easting, observer.northing,
            obs_elev, tgt_elev,
            dx, dy, total_dist, num_steps,
            k_factor, r_earth,
            self._hm._data,
            self._hm._config.origin_easting,
            self._hm._config.origin_northing,
            self._hm._config.cell_size,
        )
        if blocked_step >= 0:
            frac = blocked_step / num_steps
            bx = observer.easting + dx * frac
            by = observer.northing + dy * frac
            return LOSResult(False, Position(bx, by), "terrain", 0.0)
        grazing = min_clearance if min_clearance < 1e29 else None
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

        Uses vectorized distance computation to skip out-of-range cells
        (Phase 13a-5).  Individual LOS checks still go through
        :meth:`check_los` (which benefits from the per-tick cache).
        """
        rows, cols = self._hm.shape
        cs = self._hm.cell_size

        # Build grid-cell centre coordinate arrays
        row_indices = np.arange(rows)
        col_indices = np.arange(cols)
        # Northing increases with row, easting increases with col
        northings = self._hm._config.origin_northing + (row_indices + 0.5) * cs
        eastings = self._hm._config.origin_easting + (col_indices + 0.5) * cs

        # 2-D broadcast: (rows, 1) and (1, cols)
        de = eastings[np.newaxis, :] - observer.easting   # (1, cols)
        dn = northings[:, np.newaxis] - observer.northing  # (rows, 1)
        dist_sq = de * de + dn * dn
        max_range_sq = max_range * max_range
        in_range_mask = dist_sq <= max_range_sq

        viewshed = np.zeros((rows, cols), dtype=bool)

        # Get indices of in-range cells (avoids iterating all cells)
        in_range_rows, in_range_cols = np.where(in_range_mask)

        for idx in range(len(in_range_rows)):
            r = int(in_range_rows[idx])
            c = int(in_range_cols[idx])
            target = self._hm.grid_to_enu(r, c)
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
