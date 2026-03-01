"""Tests for terrain.heightmap — elevation data layer."""

from __future__ import annotations

import math

import numpy as np
import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.terrain.heightmap import Heightmap, HeightmapConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CONFIG = HeightmapConfig(origin_easting=0.0, origin_northing=0.0, cell_size=100.0)


def _flat(rows: int = 10, cols: int = 10, elevation: float = 50.0) -> Heightmap:
    data = np.full((rows, cols), elevation, dtype=np.float64)
    return Heightmap(data, _CONFIG)


def _ramp_east(rows: int = 10, cols: int = 10) -> Heightmap:
    """Elevation increases linearly eastward: 0 at col 0, 10*col at col n."""
    data = np.zeros((rows, cols), dtype=np.float64)
    for c in range(cols):
        data[:, c] = 10.0 * c
    return Heightmap(data, _CONFIG)


def _ramp_north(rows: int = 10, cols: int = 10) -> Heightmap:
    """Elevation increases linearly northward: 0 at row 0, 10*row at row n."""
    data = np.zeros((rows, cols), dtype=np.float64)
    for r in range(rows):
        data[r, :] = 10.0 * r
    return Heightmap(data, _CONFIG)


def _gaussian_hill(rows: int = 21, cols: int = 21, peak: float = 200.0) -> Heightmap:
    """Single Gaussian peak centred on the grid."""
    cy, cx = rows // 2, cols // 2
    y, x = np.mgrid[0:rows, 0:cols]
    sigma = 3.0
    data = peak * np.exp(-((x - cx) ** 2 + (y - cy) ** 2) / (2 * sigma**2))
    return Heightmap(data, _CONFIG)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestElevationQueries:
    def test_flat_cell_center(self) -> None:
        hm = _flat()
        # Cell (0,0) centre is at (50, 50)
        assert hm.elevation_at(Position(50.0, 50.0)) == pytest.approx(50.0)

    def test_flat_at_grid(self) -> None:
        hm = _flat(elevation=100.0)
        assert hm.elevation_at_grid(0, 0) == pytest.approx(100.0)
        assert hm.elevation_at_grid(9, 9) == pytest.approx(100.0)

    def test_ramp_east_interpolation(self) -> None:
        hm = _ramp_east()
        # Cell (r,0) centre is at easting=50, cell (r,1) at easting=150
        # Midpoint between cell 0 and cell 1 (easting=100) should be 5.0
        assert hm.elevation_at(Position(100.0, 50.0)) == pytest.approx(5.0, abs=0.5)

    def test_gaussian_peak(self) -> None:
        hm = _gaussian_hill()
        # Centre of grid is cell (10,10), at ENU (1050, 1050)
        elev = hm.elevation_at(Position(1050.0, 1050.0))
        assert elev == pytest.approx(200.0, abs=1.0)

    def test_gaussian_flanks_lower(self) -> None:
        hm = _gaussian_hill()
        peak = hm.elevation_at(Position(1050.0, 1050.0))
        flank = hm.elevation_at(Position(550.0, 1050.0))
        assert flank < peak


class TestSlopeAspect:
    def test_flat_slope_zero(self) -> None:
        hm = _flat()
        assert hm.slope_at(Position(500.0, 500.0)) == pytest.approx(0.0, abs=1e-10)

    def test_ramp_east_slope(self) -> None:
        hm = _ramp_east()
        # Rise = 10m per cell, run = 100m → slope = atan(0.1)
        expected = math.atan(10.0 / 100.0)
        # Check interior cell (avoid edge effects)
        slope = hm.slope_at(Position(500.0, 500.0))
        assert slope == pytest.approx(expected, abs=0.02)

    def test_ramp_east_aspect(self) -> None:
        hm = _ramp_east()
        # Elevation increases east → downhill is west → aspect ≈ π (south of west? no, west = 3π/2)
        # Downhill is west: azimuth = 3π/2 (270°)
        aspect = hm.aspect_at(Position(500.0, 500.0))
        assert aspect == pytest.approx(3 * math.pi / 2, abs=0.1)

    def test_ramp_north_aspect(self) -> None:
        hm = _ramp_north()
        # Elevation increases north → downhill is south → aspect = π (180°)
        aspect = hm.aspect_at(Position(500.0, 500.0))
        assert aspect == pytest.approx(math.pi, abs=0.1)

    def test_slope_grid_cached(self) -> None:
        hm = _flat()
        sg1 = hm.slope_grid()
        sg2 = hm.slope_grid()
        assert sg1 is sg2  # same object, no recompute

    def test_slope_grid_shape(self) -> None:
        hm = _flat()
        assert hm.slope_grid().shape == hm.shape


class TestGridGeometry:
    def test_grid_to_enu(self) -> None:
        hm = _flat(elevation=50.0)
        pos = hm.grid_to_enu(0, 0)
        assert pos.easting == pytest.approx(50.0)
        assert pos.northing == pytest.approx(50.0)
        assert pos.altitude == pytest.approx(50.0)

    def test_enu_to_grid(self) -> None:
        hm = _flat()
        row, col = hm.enu_to_grid(Position(50.0, 50.0))
        assert (row, col) == (0, 0)

    def test_grid_enu_round_trip(self) -> None:
        hm = _flat()
        for r in range(10):
            for c in range(10):
                pos = hm.grid_to_enu(r, c)
                r2, c2 = hm.enu_to_grid(pos)
                assert (r2, c2) == (r, c)

    def test_in_bounds(self) -> None:
        hm = _flat()
        assert hm.in_bounds(Position(50.0, 50.0))
        assert hm.in_bounds(Position(950.0, 950.0))
        assert not hm.in_bounds(Position(-10.0, 50.0))
        assert not hm.in_bounds(Position(50.0, 1100.0))

    def test_shape(self) -> None:
        hm = _flat(5, 8)
        assert hm.shape == (5, 8)

    def test_cell_size(self) -> None:
        hm = _flat()
        assert hm.cell_size == 100.0

    def test_extent(self) -> None:
        hm = _flat(10, 10)
        assert hm.extent == (0.0, 1000.0, 0.0, 1000.0)


class TestBilinearInterpolation:
    def test_cell_center_exact(self) -> None:
        """Cell center should return exact value."""
        data = np.arange(100, dtype=np.float64).reshape(10, 10)
        hm = Heightmap(data, _CONFIG)
        # Cell (3, 4) centre = (450, 350)
        assert hm.elevation_at(Position(450.0, 350.0)) == pytest.approx(34.0)

    def test_midpoint_between_cells(self) -> None:
        """Midpoint between two cells should average their values."""
        data = np.zeros((4, 4), dtype=np.float64)
        data[1, 1] = 0.0
        data[1, 2] = 100.0
        cfg = HeightmapConfig(cell_size=100.0)
        hm = Heightmap(data, cfg)
        mid = hm.elevation_at(Position(200.0, 150.0))
        assert mid == pytest.approx(50.0, abs=1.0)


class TestStateRoundTrip:
    def test_get_set_state(self) -> None:
        hm1 = _gaussian_hill()
        state = hm1.get_state()

        hm2 = _flat()
        hm2.set_state(state)

        assert hm2.shape == hm1.shape
        pos = Position(1050.0, 1050.0)
        assert hm2.elevation_at(pos) == pytest.approx(hm1.elevation_at(pos))

    def test_state_resets_cache(self) -> None:
        hm = _ramp_east()
        _ = hm.slope_grid()
        state = _flat().get_state()
        hm.set_state(state)
        # After set_state, slope should be recomputed (flat = 0)
        assert hm.slope_at(Position(500.0, 500.0)) == pytest.approx(0.0, abs=1e-10)
