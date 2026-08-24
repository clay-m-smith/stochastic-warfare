"""Tests for movement/obstacles.py."""

from types import SimpleNamespace

import numpy as np

from stochastic_warfare.movement.obstacles import (
    ObstacleAction,
    ObstacleInteraction,
)


def _make_obstacle(
    density: float = 0.5,
    traversal_risk: float = 0.1,
    traversal_time_multiplier: float = 5.0,
    is_natural: bool = False,
    obstacle_type: int = 0,
) -> SimpleNamespace:
    return SimpleNamespace(
        density=density,
        traversal_risk=traversal_risk,
        traversal_time_multiplier=traversal_time_multiplier,
        is_natural=is_natural,
        obstacle_type=obstacle_type,
    )


def _make_unit(mounted: bool = False) -> SimpleNamespace:
    return SimpleNamespace(entity_id="u1", mounted=mounted)


class TestAssessObstacle:
    def test_artificial_has_breach_and_clear(self) -> None:
        oi = ObstacleInteraction()
        obs = _make_obstacle(is_natural=False)
        actions = oi.assess_obstacle(obs, _make_unit())
        assert ObstacleAction.BYPASS in actions
        assert ObstacleAction.BREACH in actions
        assert ObstacleAction.CLEAR in actions
        assert ObstacleAction.CROSS in actions

    def test_natural_no_breach(self) -> None:
        oi = ObstacleInteraction()
        obs = _make_obstacle(is_natural=True)
        actions = oi.assess_obstacle(obs, _make_unit())
        assert ObstacleAction.BYPASS in actions
        assert ObstacleAction.BREACH not in actions
        assert ObstacleAction.CROSS in actions


class TestExecuteAction:
    def test_bypass_always_succeeds(self) -> None:
        oi = ObstacleInteraction()
        result = oi.execute_action(_make_obstacle(), _make_unit(), ObstacleAction.BYPASS)
        assert result.success is True
        assert result.casualties_risk == 0.0
        assert result.time_cost > 0

    def test_breach_time_scales_with_density(self) -> None:
        oi = ObstacleInteraction()
        r_low = oi.execute_action(
            _make_obstacle(density=0.2), _make_unit(), ObstacleAction.BREACH,
        )
        r_high = oi.execute_action(
            _make_obstacle(density=0.8), _make_unit(), ObstacleAction.BREACH,
        )
        assert r_high.time_cost > r_low.time_cost

    def test_clear_always_succeeds(self) -> None:
        oi = ObstacleInteraction()
        result = oi.execute_action(_make_obstacle(), _make_unit(), ObstacleAction.CLEAR)
        assert result.success is True

    def test_cross_has_risk(self) -> None:
        oi = ObstacleInteraction()
        result = oi.execute_action(
            _make_obstacle(traversal_risk=0.5, density=0.8),
            _make_unit(),
            ObstacleAction.CROSS,
        )
        assert result.casualties_risk > 0

    def test_breach_deterministic(self) -> None:
        rng1 = np.random.Generator(np.random.PCG64(42))
        rng2 = np.random.Generator(np.random.PCG64(42))
        oi1 = ObstacleInteraction(rng=rng1)
        oi2 = ObstacleInteraction(rng=rng2)
        r1 = oi1.execute_action(_make_obstacle(), _make_unit(), ObstacleAction.BREACH)
        r2 = oi2.execute_action(_make_obstacle(), _make_unit(), ObstacleAction.BREACH)
        assert r1.success == r2.success


class TestMinefieldRisk:
    def test_non_minefield_zero(self) -> None:
        oi = ObstacleInteraction()
        obs = _make_obstacle(obstacle_type=1)  # not MINEFIELD
        risk = oi.minefield_transit_risk(obs, _make_unit())
        assert risk == 0.0

    def test_minefield_risk_positive(self) -> None:
        oi = ObstacleInteraction()
        obs = _make_obstacle(obstacle_type=0, density=0.5)  # MINEFIELD = 0
        risk = oi.minefield_transit_risk(obs, _make_unit())
        assert risk > 0

    def test_mounted_higher_risk(self) -> None:
        oi = ObstacleInteraction()
        obs = _make_obstacle(obstacle_type=0, density=0.5)
        risk_dismounted = oi.minefield_transit_risk(obs, _make_unit(mounted=False))
        risk_mounted = oi.minefield_transit_risk(obs, _make_unit(mounted=True))
        assert risk_mounted > risk_dismounted
