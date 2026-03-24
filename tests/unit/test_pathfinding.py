"""Tests for movement/pathfinding.py."""

import math


from stochastic_warfare.core.types import Position
from stochastic_warfare.movement.pathfinding import Pathfinder


class TestBasicPathfinding:
    def test_same_cell(self) -> None:
        pf = Pathfinder()
        result = pf.find_path(Position(50.0, 50.0), Position(50.0, 50.0))
        assert result.found
        assert len(result.waypoints) == 2

    def test_straight_line(self) -> None:
        pf = Pathfinder()
        result = pf.find_path(
            Position(0.0, 0.0), Position(500.0, 0.0),
            grid_resolution=100.0,
        )
        assert result.found
        assert len(result.waypoints) >= 2
        assert result.total_distance > 0
        # Start and end should be the input positions
        assert result.waypoints[0] == Position(0.0, 0.0)
        assert result.waypoints[-1] == Position(500.0, 0.0)

    def test_diagonal_path(self) -> None:
        pf = Pathfinder()
        result = pf.find_path(
            Position(0.0, 0.0), Position(300.0, 300.0),
            grid_resolution=100.0,
        )
        assert result.found
        assert result.total_distance >= math.sqrt(300**2 + 300**2) * 0.9

    def test_cost_is_positive(self) -> None:
        pf = Pathfinder()
        result = pf.find_path(Position(0.0, 0.0), Position(200.0, 200.0))
        assert result.total_cost >= 0


class TestThreatAvoidance:
    def test_avoids_threat(self) -> None:
        pf = Pathfinder()
        # Threat in the middle of the direct path
        threats = [(Position(250.0, 0.0), 200.0)]
        result = pf.find_path(
            Position(0.0, 0.0), Position(500.0, 0.0),
            avoid_threats=threats, grid_resolution=100.0,
        )
        assert result.found
        # Path should deviate away from threat
        max_northing = max(abs(w.northing) for w in result.waypoints)
        assert max_northing > 0  # should go around

    def test_no_threats_direct(self) -> None:
        pf = Pathfinder()
        result = pf.find_path(
            Position(0.0, 0.0), Position(500.0, 0.0),
            grid_resolution=100.0,
        )
        assert result.found
        # Without threats, path should be roughly direct
        max_northing = max(abs(w.northing) for w in result.waypoints)
        assert max_northing < 200.0


class TestMaxIterations:
    def test_gives_up_after_max(self) -> None:
        pf = Pathfinder()
        result = pf.find_path(
            Position(0.0, 0.0), Position(100000.0, 100000.0),
            grid_resolution=10.0,  # very fine grid = many iterations
            max_iterations=10,
        )
        assert not result.found
        assert result.waypoints == []


class TestMovementCost:
    def test_positive_cost(self) -> None:
        pf = Pathfinder()
        cost = pf.movement_cost(Position(0.0, 0.0), Position(100.0, 0.0))
        assert cost > 0

    def test_farther_costs_more(self) -> None:
        pf = Pathfinder()
        c1 = pf.movement_cost(Position(0.0, 0.0), Position(100.0, 0.0))
        c2 = pf.movement_cost(Position(0.0, 0.0), Position(200.0, 0.0))
        assert c2 > c1
