"""Airborne movement — drop scatter, DZ assessment, helicopter insertion."""

from __future__ import annotations

import enum
import math
from typing import NamedTuple

import numpy as np

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import Position, Seconds

logger = get_logger(__name__)


class AirborneMethod(enum.IntEnum):
    """Insertion method."""

    STATIC_LINE = 0
    HALO = 1
    HAHO = 2
    HELICOPTER_LANDING = 3
    FAST_ROPE = 4
    RAPPEL = 5


# Base scatter radius in meters per method
_SCATTER_BASE: dict[AirborneMethod, float] = {
    AirborneMethod.STATIC_LINE: 300.0,
    AirborneMethod.HALO: 100.0,
    AirborneMethod.HAHO: 500.0,
    AirborneMethod.HELICOPTER_LANDING: 50.0,
    AirborneMethod.FAST_ROPE: 20.0,
    AirborneMethod.RAPPEL: 30.0,
}


class DropResult(NamedTuple):
    """Result of an airborne drop operation."""

    landing_positions: list[Position]
    assembly_time: Seconds
    casualties_from_drop: int


class AirborneMovementEngine:
    """Airborne insertion movement.

    Parameters
    ----------
    heightmap:
        Terrain heightmap for DZ assessment.
    classification:
        Terrain classification for DZ suitability.
    rng:
        PRNG stream for scatter and casualty computation.
    """

    def __init__(
        self,
        heightmap=None,
        classification=None,
        rng: np.random.Generator | None = None,
    ) -> None:
        self._heightmap = heightmap
        self._classification = classification
        self._rng = rng

    def compute_drop_scatter(
        self,
        dz_center: Position,
        wind_speed: float,
        altitude: float,
        method: AirborneMethod,
        num_jumpers: int,
    ) -> list[Position]:
        """Compute landing positions for *num_jumpers*.

        Scatter is Gaussian around *dz_center*, scaled by method, wind,
        and altitude.
        """
        base_scatter = _SCATTER_BASE.get(method, 200.0)

        # Wind increases scatter linearly
        wind_factor = 1.0 + wind_speed / 10.0

        # Higher altitude = more drift time = more scatter
        alt_factor = 1.0 + altitude / 5000.0

        scatter_radius = base_scatter * wind_factor * alt_factor

        positions: list[Position] = []
        rng = self._rng
        for _ in range(num_jumpers):
            if rng is not None:
                dx = rng.normal(0.0, scatter_radius / 2.0)
                dy = rng.normal(0.0, scatter_radius / 2.0)
            else:
                dx, dy = 0.0, 0.0
            positions.append(
                Position(
                    dz_center.easting + dx,
                    dz_center.northing + dy,
                    dz_center.altitude,
                )
            )
        return positions

    def assess_dz(self, pos: Position, radius: float) -> dict:
        """Assess drop zone suitability.

        Returns dict with slope, terrain_type, suitability (0-1).
        """
        slope = 0.0
        if self._heightmap is not None:
            slope = self._heightmap.slope_at(pos)

        # DZ suitability: flat open terrain is best
        suitability = max(0.0, 1.0 - slope * 5.0)
        if self._classification is not None:
            trafficability = self._classification.trafficability_at(pos)
            suitability *= trafficability

        return {
            "slope": slope,
            "radius": radius,
            "suitability": min(1.0, suitability),
        }

    def assembly_time(
        self, scatter_positions: list[Position], dz_center: Position
    ) -> Seconds:
        """Estimate time to assemble at *dz_center* from scattered landing.

        Based on mean distance from center at walking speed (~1 m/s).
        """
        if not scatter_positions:
            return 0.0

        total_dist = 0.0
        for p in scatter_positions:
            dx = p.easting - dz_center.easting
            dy = p.northing - dz_center.northing
            total_dist += math.sqrt(dx * dx + dy * dy)

        mean_dist = total_dist / len(scatter_positions)
        # Walking speed ~1 m/s + 50% overhead for coordination
        return mean_dist / 1.0 * 1.5

    def helicopter_insertion(
        self,
        lz: Position,
        num_aircraft: int,
        conditions=None,
    ) -> dict:
        """Assess helicopter insertion at *lz*.

        Returns dict with time_to_offload, risk, suitability.
        """
        # Each helicopter offloads in ~2 minutes
        base_time = 120.0

        wind = 0.0
        if conditions is not None:
            wind = getattr(conditions, "wind_speed", 0.0) if hasattr(conditions, "wind_speed") else 0.0

        # Risk increases with wind
        risk = min(1.0, wind / 30.0)

        suitability = 1.0
        if self._heightmap is not None:
            slope = self._heightmap.slope_at(lz)
            suitability = max(0.0, 1.0 - slope * 3.0)

        return {
            "time_to_offload": base_time * num_aircraft,
            "risk": risk,
            "suitability": suitability,
            "num_aircraft": num_aircraft,
        }
