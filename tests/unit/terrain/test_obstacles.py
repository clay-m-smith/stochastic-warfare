"""Tests for terrain.obstacles — obstacle features."""

from __future__ import annotations

import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.terrain.obstacles import Obstacle, ObstacleManager, ObstacleType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _minefield() -> Obstacle:
    return Obstacle(
        obstacle_id="mine_01",
        obstacle_type=ObstacleType.MINEFIELD,
        footprint=[(100.0, 100.0), (300.0, 100.0), (300.0, 300.0), (100.0, 300.0)],
        density=0.8,
        traversal_risk=0.3,
    )


def _ravine() -> Obstacle:
    return Obstacle(
        obstacle_id="ravine_01",
        obstacle_type=ObstacleType.RAVINE,
        footprint=[(400.0, 400.0), (600.0, 400.0), (600.0, 450.0), (400.0, 450.0)],
        is_natural=True,
        traversal_time_multiplier=10.0,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestQueries:
    def test_point_in_obstacle(self) -> None:
        mgr = ObstacleManager([_minefield()])
        obs = mgr.obstacles_at(Position(200.0, 200.0))
        assert len(obs) == 1
        assert obs[0].obstacle_type == ObstacleType.MINEFIELD

    def test_point_outside_obstacle(self) -> None:
        mgr = ObstacleManager([_minefield()])
        assert len(mgr.obstacles_at(Position(50.0, 50.0))) == 0

    def test_obstacles_in_area(self) -> None:
        mgr = ObstacleManager([_minefield(), _ravine()])
        # Area that covers both
        obs = mgr.obstacles_in_area(Position(0.0, 0.0), Position(700.0, 700.0))
        assert len(obs) == 2

    def test_obstacles_in_area_partial(self) -> None:
        mgr = ObstacleManager([_minefield(), _ravine()])
        # Area covers only minefield
        obs = mgr.obstacles_in_area(Position(0.0, 0.0), Position(350.0, 350.0))
        assert len(obs) == 1
        assert obs[0].obstacle_id == "mine_01"


class TestLifecycle:
    def test_emplace(self) -> None:
        mgr = ObstacleManager()
        mgr.emplace(_minefield())
        assert len(mgr.obstacles_at(Position(200.0, 200.0))) == 1

    def test_emplace_duplicate_raises(self) -> None:
        mgr = ObstacleManager([_minefield()])
        with pytest.raises(ValueError, match="already exists"):
            mgr.emplace(_minefield())

    def test_clear(self) -> None:
        mgr = ObstacleManager([_minefield()])
        mgr.clear("mine_01")
        assert len(mgr.obstacles_at(Position(200.0, 200.0))) == 0

    def test_breach(self) -> None:
        mgr = ObstacleManager([_minefield()])
        mgr.breach("mine_01", breach_width=100.0)
        obs = mgr._obstacles["mine_01"]
        assert obs.condition < 1.0
        assert obs.condition > 0.0

    def test_natural_cannot_be_cleared(self) -> None:
        mgr = ObstacleManager([_ravine()])
        mgr.clear("ravine_01")
        # Ravine should still have condition = 1.0
        assert mgr._obstacles["ravine_01"].condition == 1.0

    def test_natural_cannot_be_breached(self) -> None:
        mgr = ObstacleManager([_ravine()])
        mgr.breach("ravine_01", breach_width=50.0)
        assert mgr._obstacles["ravine_01"].condition == 1.0

    def test_unknown_clear_raises(self) -> None:
        mgr = ObstacleManager()
        with pytest.raises(KeyError):
            mgr.clear("nonexistent")


class TestStateRoundTrip:
    def test_get_set_state(self) -> None:
        mgr1 = ObstacleManager([_minefield(), _ravine()])
        mgr1.breach("mine_01", breach_width=50.0)
        state = mgr1.get_state()

        mgr2 = ObstacleManager()
        mgr2.set_state(state)
        assert len(mgr2._obstacles) == 2
        assert mgr2._obstacles["mine_01"].condition < 1.0
        assert mgr2._obstacles["ravine_01"].condition == 1.0
