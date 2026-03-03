"""Core movement engine — terrain-aware speed computation and unit movement."""

from __future__ import annotations

import math
from typing import NamedTuple

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import Meters, Position, Seconds

logger = get_logger(__name__)


class MovementResult(NamedTuple):
    """Result of a single movement tick."""

    new_position: Position
    distance_moved: Meters
    time_elapsed: Seconds
    fatigue_added: float
    fuel_consumed: float


class MovementConfig(BaseModel):
    """Configuration for ground movement parameters."""

    base_infantry_speed: float = 1.3  # m/s (~5 km/h)
    base_vehicle_speed: float = 10.0  # m/s cross-country
    slope_penalty_factor: float = 2.0  # per radian of slope
    night_speed_reduction: float = 0.5  # multiplier at night
    nvg_speed_recovery: float = 0.7  # of daytime speed with NVGs
    fatigue_speed_factor: float = 0.3  # max fatigue penalty
    road_speed_bonus: float = 2.0  # multiplier on roads
    noise_std: float = 0.02  # Gaussian noise std on speed


class MovementEngine:
    """Compute terrain-aware movement speed and move units.

    Parameters
    ----------
    heightmap:
        Terrain heightmap module (provides ``elevation_at``, ``slope_at``).
    classification:
        Terrain classification module (provides ``trafficability_at``).
    infrastructure:
        Infrastructure manager (provides ``road_speed_at``).
    obstacles:
        Obstacle manager (provides ``obstacles_at``).
    hydrography:
        Hydrography manager (provides ``is_in_water``).
    conditions_engine:
        Environment conditions facade (provides ``land``).
    rng:
        PRNG stream for stochastic speed deviation.
    config:
        Movement parameters.
    """

    def __init__(
        self,
        heightmap=None,
        classification=None,
        infrastructure=None,
        obstacles=None,
        hydrography=None,
        conditions_engine=None,
        rng: np.random.Generator | None = None,
        config: MovementConfig | None = None,
    ) -> None:
        self._heightmap = heightmap
        self._classification = classification
        self._infrastructure = infrastructure
        self._obstacles = obstacles
        self._hydrography = hydrography
        self._conditions = conditions_engine
        self._rng = rng
        self._config = config or MovementConfig()

    def terrain_speed_factor(self, pos: Position) -> float:
        """Return 0.0–1.0 trafficability-based speed factor at *pos*."""
        if self._classification is None:
            return 1.0
        return self._classification.trafficability_at(pos)

    def slope_speed_factor(self, pos: Position, heading: float) -> float:
        """Return speed factor for slope at *pos* along *heading*.

        Uphill reduces speed; downhill up to a point is neutral then
        reduces speed again (steep descent is slow).
        """
        if self._heightmap is None:
            return 1.0
        slope = self._heightmap.slope_at(pos)
        if slope <= 0.0:
            return 1.0
        # Aspect-aware: penalty is maximum when heading uphill
        aspect = self._heightmap.aspect_at(pos)
        # Angle between heading and uphill direction
        angle_diff = abs(heading - aspect)
        if angle_diff > math.pi:
            angle_diff = 2 * math.pi - angle_diff
        # If heading uphill (angle_diff near 0), full penalty
        # If heading downhill (angle_diff near pi), reduced penalty
        uphill_factor = math.cos(angle_diff)
        effective_slope = slope * uphill_factor
        # Penalty: exponential decay with slope
        return max(0.1, 1.0 - self._config.slope_penalty_factor * abs(effective_slope))

    def road_speed_factor(self, pos: Position) -> float:
        """Return road speed multiplier at *pos*, or 1.0 if off-road."""
        if self._infrastructure is None:
            return 1.0
        factor = self._infrastructure.road_speed_at(pos)
        if factor is not None:
            return factor
        return 1.0

    def compute_speed(
        self,
        unit,
        pos: Position,
        heading: float,
        conditions=None,
    ) -> float:
        """Compute effective speed in m/s for *unit* at *pos*.

        Speed = base * terrain * slope * road * weather * fatigue * night
        Plus stochastic Gaussian noise.
        """
        base = unit.max_speed if unit.max_speed > 0 else self._config.base_infantry_speed

        terrain = self.terrain_speed_factor(pos)
        slope = self.slope_speed_factor(pos, heading)
        road = self.road_speed_factor(pos)

        # Weather / trafficability from conditions
        weather = 1.0
        night = 1.0
        if conditions is not None:
            weather = getattr(conditions, "trafficability", 1.0)
            lux = getattr(conditions, "illumination_lux", 10000.0)
            if lux < 10.0:
                # Night movement
                nvg = getattr(conditions, "nvg_effectiveness", 0.0)
                night = self._config.night_speed_reduction
                if nvg > 0:
                    night += (1.0 - night) * nvg * self._config.nvg_speed_recovery

        speed = base * terrain * slope * road * weather * night

        # Stochastic noise
        if self._rng is not None and self._config.noise_std > 0:
            noise = 1.0 + self._config.noise_std * self._rng.standard_normal()
            speed *= max(0.5, noise)

        return max(0.0, speed)

    def move_unit(
        self,
        unit,
        target: Position,
        dt: Seconds,
        conditions=None,
        fuel_available: float = float("inf"),
    ) -> MovementResult:
        """Move *unit* toward *target* for *dt* seconds.

        Parameters
        ----------
        fuel_available:
            Fuel units available. If finite, clamps movement distance to
            what fuel allows. ``float('inf')`` means unlimited fuel
            (backward-compatible default).

        Returns the actual new position (may not reach target in one tick).
        """
        pos = unit.position
        dx = target.easting - pos.easting
        dy = target.northing - pos.northing
        dist_to_target = math.sqrt(dx * dx + dy * dy)

        if dist_to_target < 0.1:
            return MovementResult(pos, 0.0, dt, 0.0, 0.0)

        # Fuel gating: zero fuel → no movement
        if fuel_available <= 0:
            return MovementResult(pos, 0.0, dt, 0.0, 0.0)

        heading = math.atan2(dx, dy)  # 0=north, CW
        speed = self.compute_speed(unit, pos, heading, conditions)

        max_dist = speed * dt
        dist = min(dist_to_target, max_dist)

        # Fuel consumption rate (proportional to distance)
        fuel_rate = 0.0001 if unit.max_speed > 5.0 else 0.0

        # Fuel gating: clamp distance if insufficient fuel
        if fuel_rate > 0 and fuel_available < float("inf"):
            max_fuel_dist = fuel_available / fuel_rate
            dist = min(dist, max_fuel_dist)

        if dist_to_target > 0 and dist > 0:
            ratio = dist / dist_to_target
            new_pos = Position(
                pos.easting + dx * ratio,
                pos.northing + dy * ratio,
                target.altitude if ratio >= 1.0 else pos.altitude,
            )
        else:
            new_pos = pos

        # Fatigue from movement (hours * rate)
        hours = dt / 3600.0
        fatigue_added = hours * 0.08  # base rate

        # Fuel consumed
        fuel = dist * fuel_rate

        return MovementResult(new_pos, dist, dt, fatigue_added, fuel)
