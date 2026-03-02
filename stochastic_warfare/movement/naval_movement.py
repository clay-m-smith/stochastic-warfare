"""Naval surface movement — speed, fuel, draft, sea state effects."""

from __future__ import annotations

from typing import NamedTuple
import math

import numpy as np

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import Position

logger = get_logger(__name__)


class NavalMovementResult(NamedTuple):
    """Result of a naval movement tick."""

    new_position: Position
    fuel_consumed: float
    speed_actual: float
    draft_ok: bool


class NavalMovementEngine:
    """Surface ship movement with fuel cubic law and draft checking.

    Parameters
    ----------
    bathymetry:
        Bathymetry module for depth queries.
    maritime_geo:
        Maritime geography for sea/land checks.
    sea_state_engine:
        Sea state engine for wave/current conditions.
    rng:
        PRNG stream.
    """

    def __init__(
        self,
        bathymetry=None,
        maritime_geo=None,
        sea_state_engine=None,
        rng: np.random.Generator | None = None,
    ) -> None:
        self._bathymetry = bathymetry
        self._maritime_geo = maritime_geo
        self._sea_state = sea_state_engine
        self._rng = rng

    def compute_speed(self, unit, sea_state=None) -> float:
        """Compute effective speed considering sea state.

        Heavy seas reduce speed. Beaufort 8+ halves speed.
        """
        max_speed = unit.max_speed
        if sea_state is None:
            return max_speed

        beaufort = getattr(sea_state, "beaufort_scale", 0)
        # Speed reduction: linear from beaufort 4 to 8
        if beaufort <= 3:
            return max_speed
        reduction = min(0.5, (beaufort - 3) * 0.1)
        return max_speed * (1.0 - reduction)

    def fuel_consumption(
        self, unit, speed: float, duration_hours: float
    ) -> float:
        """Compute fuel consumed using cubic speed law.

        Fuel ~ k * v^3 * t. Normalized so max_speed consumes fuel_capacity
        over design endurance.
        """
        if unit.max_speed <= 0:
            return 0.0
        # Normalized cubic: fraction of capacity per hour at max speed ~0.01
        k = 0.01 / (unit.max_speed ** 3) if unit.max_speed > 0 else 0.0
        return k * (speed ** 3) * duration_hours

    def check_draft(self, unit, pos: Position) -> bool:
        """Return True if water is deep enough for *unit* at *pos*."""
        if self._bathymetry is None:
            return True
        depth = self._bathymetry.depth_at(pos)
        draft = getattr(unit, "draft", 0.0)
        return depth >= draft

    def move_ship(
        self, unit, target: Position, speed: float, dt: float
    ) -> NavalMovementResult:
        """Move *unit* toward *target* at *speed* for *dt* seconds."""
        pos = unit.position
        dx = target.easting - pos.easting
        dy = target.northing - pos.northing
        dist_to_target = math.sqrt(dx * dx + dy * dy)

        if dist_to_target < 0.1:
            return NavalMovementResult(pos, 0.0, 0.0, True)

        actual_speed = speed
        sea_state = None
        if self._sea_state is not None:
            sea_state = getattr(self._sea_state, "current", None)
            actual_speed = self.compute_speed(unit, sea_state)

        max_dist = actual_speed * dt
        dist = min(dist_to_target, max_dist)

        ratio = dist / dist_to_target
        new_pos = Position(
            pos.easting + dx * ratio,
            pos.northing + dy * ratio,
            0.0,
        )

        draft_ok = self.check_draft(unit, new_pos)
        hours = dt / 3600.0
        fuel = self.fuel_consumption(unit, actual_speed, hours)

        return NavalMovementResult(new_pos, fuel, actual_speed, draft_ok)
