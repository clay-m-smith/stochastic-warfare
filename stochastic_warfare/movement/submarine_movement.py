"""Submarine movement — depth, speed-noise curve, snorkeling."""

from __future__ import annotations

import enum
import math
from typing import NamedTuple

import numpy as np

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import Position

logger = get_logger(__name__)


class SubDepthBand(enum.IntEnum):
    """Depth bands for submarine operations."""

    SURFACE = 0
    PERISCOPE = 1  # ~18m
    SHALLOW = 2  # ~60m
    OPERATING = 3  # ~150m
    DEEP = 4  # ~300m
    MAXIMUM = 5  # test depth


# Approximate depth for each band (meters)
_BAND_DEPTHS: dict[SubDepthBand, float] = {
    SubDepthBand.SURFACE: 0.0,
    SubDepthBand.PERISCOPE: 18.0,
    SubDepthBand.SHALLOW: 60.0,
    SubDepthBand.OPERATING: 150.0,
    SubDepthBand.DEEP: 300.0,
    SubDepthBand.MAXIMUM: 450.0,
}


class SubmarineMovementResult(NamedTuple):
    """Result of a submarine movement tick."""

    new_position: Position
    new_depth: float
    noise_level: float
    fuel_consumed: float
    snorkeling: bool


class SubmarineMovementEngine:
    """Submarine movement with speed-noise tradeoff and depth management.

    Parameters
    ----------
    bathymetry:
        Bathymetry module for depth limits.
    acoustics_engine:
        Underwater acoustics engine for noise context.
    rng:
        PRNG stream.
    """

    def __init__(
        self,
        bathymetry=None,
        acoustics_engine=None,
        rng: np.random.Generator | None = None,
    ) -> None:
        self._bathymetry = bathymetry
        self._acoustics = acoustics_engine
        self._rng = rng

    def speed_noise_curve(self, unit, speed: float) -> float:
        """Return noise level in dB for *unit* at *speed*.

        Noise increases roughly as 20*log10(speed/quiet_speed) above
        a base signature.
        """
        base = getattr(unit, "noise_signature_base", 90.0)
        # Quiet speed: ~5 knots = ~2.5 m/s
        quiet_speed = 2.5
        if speed <= quiet_speed:
            return base
        # 20*log10(speed_ratio) increase
        return base + 20.0 * math.log10(speed / quiet_speed)

    def change_depth(self, unit, target_depth: float, dt: float) -> float:
        """Change *unit*'s depth toward *target_depth* at standard rate.

        Returns the new depth. Rate: ~1 m/s vertical.
        """
        current = getattr(unit, "depth", 0.0)
        max_depth = getattr(unit, "max_depth", 300.0)
        target_depth = min(target_depth, max_depth)
        target_depth = max(0.0, target_depth)

        rate = 1.0  # m/s
        max_change = rate * dt
        diff = target_depth - current

        if abs(diff) <= max_change:
            return target_depth
        return current + math.copysign(max_change, diff)

    def snorkel_exposure(self, unit) -> float:
        """Return detection risk factor when snorkeling.

        Higher values mean greater exposure. Depth near periscope
        depth + mast up = high exposure.
        """
        depth = getattr(unit, "depth", 0.0)
        if depth > 20.0:
            return 0.0  # too deep to snorkel
        # Exposure decreases with depth
        return max(0.0, 1.0 - depth / 20.0)

    def depth_band(self, depth: float) -> SubDepthBand:
        """Return the depth band for a given depth."""
        for band in reversed(SubDepthBand):
            if depth >= _BAND_DEPTHS[band]:
                return band
        return SubDepthBand.SURFACE

    def move_submarine(
        self, unit, target: Position, speed: float, depth: float, dt: float
    ) -> SubmarineMovementResult:
        """Move submarine toward *target* at *speed* and *depth*."""
        pos = unit.position
        dx = target.easting - pos.easting
        dy = target.northing - pos.northing
        dist_to_target = math.sqrt(dx * dx + dy * dy)

        if dist_to_target < 0.1:
            noise = self.speed_noise_curve(unit, 0.0)
            return SubmarineMovementResult(pos, depth, noise, 0.0, False)

        max_dist = speed * dt
        dist = min(dist_to_target, max_dist)
        ratio = dist / dist_to_target

        new_pos = Position(
            pos.easting + dx * ratio,
            pos.northing + dy * ratio,
            0.0,
        )

        new_depth = self.change_depth(unit, depth, dt)
        noise = self.speed_noise_curve(unit, speed)
        snorkeling = new_depth <= 18.0 and speed <= 5.0

        # Nuclear subs: no fuel consumption
        fuel_cap = getattr(unit, "fuel_capacity", 0.0)
        if fuel_cap <= 0:
            fuel = 0.0
        else:
            hours = dt / 3600.0
            fuel = 0.005 * speed * hours  # diesel-electric approximation

        return SubmarineMovementResult(
            new_pos, new_depth, noise, fuel, snorkeling,
        )
