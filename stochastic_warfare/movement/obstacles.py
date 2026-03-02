"""Obstacle interaction — breach, bypass, clear, cross."""

from __future__ import annotations

import enum
from typing import NamedTuple

import numpy as np

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import Seconds

logger = get_logger(__name__)


class ObstacleAction(enum.IntEnum):
    """Actions a unit can take against an obstacle."""

    BYPASS = 0
    BREACH = 1
    CLEAR = 2
    CROSS = 3


class ObstacleInteractionResult(NamedTuple):
    """Result of an obstacle interaction attempt."""

    action: ObstacleAction
    time_cost: Seconds
    casualties_risk: float
    success: bool


class ObstacleInteraction:
    """Assess and execute obstacle interactions.

    Parameters
    ----------
    obstacle_manager:
        The terrain obstacle manager (provides ``obstacles_at``).
    rng:
        PRNG stream for stochastic outcomes.
    """

    def __init__(self, obstacle_manager=None, rng: np.random.Generator | None = None) -> None:
        self._obstacles = obstacle_manager
        self._rng = rng

    def assess_obstacle(self, obstacle, unit) -> list[ObstacleAction]:
        """Return available actions for *unit* facing *obstacle*."""
        actions = [ObstacleAction.BYPASS]  # always available

        if not getattr(obstacle, "is_natural", False):
            actions.append(ObstacleAction.BREACH)
            actions.append(ObstacleAction.CLEAR)

        # Everyone can attempt crossing
        actions.append(ObstacleAction.CROSS)
        return actions

    def execute_action(
        self, obstacle, unit, action: ObstacleAction
    ) -> ObstacleInteractionResult:
        """Execute *action* against *obstacle* and return result."""
        density = getattr(obstacle, "density", 0.5)
        risk = getattr(obstacle, "traversal_risk", 0.1)
        time_mult = getattr(obstacle, "traversal_time_multiplier", 5.0)

        if action == ObstacleAction.BYPASS:
            return ObstacleInteractionResult(
                action=action,
                time_cost=300.0,  # 5 minutes to bypass
                casualties_risk=0.0,
                success=True,
            )

        if action == ObstacleAction.BREACH:
            success = True
            if self._rng is not None:
                # Success probability decreases with density
                p_success = 1.0 - 0.3 * density
                success = self._rng.random() < p_success
            return ObstacleInteractionResult(
                action=action,
                time_cost=600.0 * density,  # up to 10 min
                casualties_risk=risk * 0.5,
                success=success,
            )

        if action == ObstacleAction.CLEAR:
            return ObstacleInteractionResult(
                action=action,
                time_cost=1800.0 * density,  # up to 30 min
                casualties_risk=risk * 0.3,
                success=True,  # clearing always succeeds eventually
            )

        # CROSS
        casualty_risk = risk * density
        success = True
        if self._rng is not None and casualty_risk > 0.5:
            success = self._rng.random() > 0.2  # high risk may fail
        return ObstacleInteractionResult(
            action=action,
            time_cost=60.0 * time_mult,
            casualties_risk=casualty_risk,
            success=success,
        )

    def minefield_transit_risk(self, obstacle, unit) -> float:
        """Return casualty probability for transiting a minefield.

        Based on obstacle density, unit mounted/dismount state, and
        obstacle type.
        """
        from stochastic_warfare.terrain.obstacles import ObstacleType

        obs_type = getattr(obstacle, "obstacle_type", None)
        if obs_type != ObstacleType.MINEFIELD:
            return 0.0

        density = getattr(obstacle, "density", 0.5)
        mounted = getattr(unit, "mounted", False)

        # Mounted vehicles trigger mines more reliably
        base_risk = density * 0.3
        if mounted:
            base_risk *= 1.5
        return min(1.0, base_risk)
