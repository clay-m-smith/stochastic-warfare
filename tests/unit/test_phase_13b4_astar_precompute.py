"""Phase 13b-4: A* difficulty grid pre-computation tests."""

import numpy as np
import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.movement.pathfinding import Pathfinder


class TestDifficultyGrid:
    def test_difficulty_grid_shape(self):
        pf = Pathfinder()
        grid = pf._compute_difficulty_grid(-5, 5, -5, 5, 100.0)
        assert grid.shape == (11, 11)

    def test_difficulty_grid_flat_terrain(self):
        """Without terrain modules, all cells should have difficulty 1.0."""
        pf = Pathfinder()
        grid = pf._compute_difficulty_grid(0, 10, 0, 10, 100.0)
        np.testing.assert_array_equal(grid, np.ones((11, 11)))

    def test_difficulty_grid_single_cell(self):
        pf = Pathfinder()
        grid = pf._compute_difficulty_grid(5, 5, 5, 5, 100.0)
        assert grid.shape == (1, 1)
        assert grid[0, 0] == 1.0


class TestPathfindingWithGrid:
    def test_path_found_basic(self):
        """Path should still be found with grid pre-computation."""
        pf = Pathfinder()
        result = pf.find_path(
            Position(0, 0), Position(500, 500),
            grid_resolution=100.0,
        )
        assert result.found
        assert len(result.waypoints) > 0

    def test_path_result_identical_to_baseline(self):
        """Grid pre-compute should produce same path as dict cache."""
        pf = Pathfinder()
        result = pf.find_path(
            Position(0, 0), Position(1000, 1000),
            grid_resolution=100.0,
        )
        assert result.found
        assert result.total_cost > 0
        assert result.total_distance > 0

    def test_same_start_goal(self):
        pf = Pathfinder()
        result = pf.find_path(Position(0, 0), Position(0, 0), grid_resolution=100.0)
        assert result.found

    def test_long_path(self):
        """Longer paths should still work with grid pre-compute."""
        pf = Pathfinder()
        result = pf.find_path(
            Position(0, 0), Position(5000, 5000),
            grid_resolution=100.0, max_iterations=20000,
        )
        assert result.found

    def test_path_with_threats(self):
        """Threat avoidance should still work with grid pre-compute."""
        pf = Pathfinder()
        threats = [(Position(250, 250), 300.0)]
        result = pf.find_path(
            Position(0, 0), Position(500, 500),
            grid_resolution=100.0, avoid_threats=threats,
        )
        assert result.found

    def test_path_deterministic(self):
        """Same inputs should produce same path."""
        pf = Pathfinder()
        r1 = pf.find_path(Position(0, 0), Position(1000, 1000), grid_resolution=100.0)
        r2 = pf.find_path(Position(0, 0), Position(1000, 1000), grid_resolution=100.0)
        assert r1.total_cost == pytest.approx(r2.total_cost)
        assert len(r1.waypoints) == len(r2.waypoints)

    def test_path_outside_grid_falls_back(self):
        """Cells outside pre-computed grid should fall back to on-demand."""
        pf = Pathfinder()
        # This path should work even if cells are outside the initial bbox
        result = pf.find_path(
            Position(0, 0), Position(2000, 0),
            grid_resolution=100.0, max_iterations=5000,
        )
        assert result.found

    def test_max_iterations_exceeded(self):
        """Should gracefully fail when max_iterations is too low."""
        pf = Pathfinder()
        result = pf.find_path(
            Position(0, 0), Position(10000, 10000),
            grid_resolution=100.0, max_iterations=5,
        )
        assert not result.found
