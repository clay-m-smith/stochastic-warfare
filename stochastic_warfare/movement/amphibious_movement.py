"""Amphibious movement — ship-to-shore phase transitions."""

from __future__ import annotations

import enum
from typing import NamedTuple

import numpy as np

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import Position, Seconds

logger = get_logger(__name__)


class AmphibPhase(enum.IntEnum):
    """Phases of an amphibious operation."""

    LOADING = 0
    TRANSIT = 1
    STAGING = 2
    SHIP_TO_SHORE = 3
    BEACH_LANDING = 4
    INLAND = 5


class AmphibMovementResult(NamedTuple):
    """Result of an amphibious movement tick."""

    phase: AmphibPhase
    position: Position
    time_elapsed: Seconds
    units_ashore: int


class AmphibiousMovementEngine:
    """Amphibious operation movement through phases.

    Parameters
    ----------
    bathymetry:
        Bathymetry module for beach gradient.
    sea_state_engine:
        Sea state engine for wave conditions.
    rng:
        PRNG stream.
    """

    def __init__(
        self,
        bathymetry=None,
        sea_state_engine=None,
        rng: np.random.Generator | None = None,
    ) -> None:
        self._bathymetry = bathymetry
        self._sea_state = sea_state_engine
        self._rng = rng

    def assess_beach(self, pos: Position) -> dict:
        """Assess beach suitability for landing.

        Returns dict with gradient, depth_offshore, suitability (0-1).
        """
        depth = 0.0
        if self._bathymetry is not None:
            depth = self._bathymetry.depth_at(
                Position(pos.easting, pos.northing - 200.0)
            )

        # Gentle gradient = better beach
        gradient = depth / 200.0 if depth > 0 else 0.01
        suitability = 1.0 if 0.01 < gradient < 0.05 else max(0.2, 1.0 - abs(gradient - 0.03) * 20)

        return {
            "gradient": gradient,
            "depth_offshore": depth,
            "suitability": min(1.0, max(0.0, suitability)),
        }

    def ship_to_shore_time(
        self, distance: float, craft_speed: float, sea_state=None
    ) -> Seconds:
        """Compute time for landing craft to transit ship to shore.

        Parameters
        ----------
        distance:
            Meters from ship to beach.
        craft_speed:
            Landing craft speed in m/s.
        sea_state:
            Current sea state conditions.
        """
        if craft_speed <= 0:
            return float("inf")

        speed = craft_speed
        if sea_state is not None:
            beaufort = getattr(sea_state, "beaufort_scale", 0)
            if beaufort > 3:
                speed *= max(0.3, 1.0 - (beaufort - 3) * 0.15)

        return distance / speed

    def execute_phase(
        self,
        units: list,
        phase: AmphibPhase,
        dt: Seconds,
    ) -> AmphibMovementResult:
        """Advance amphibious operation by one tick.

        Parameters
        ----------
        units:
            List of units participating.
        phase:
            Current phase of the operation.
        dt:
            Time step in seconds.
        """
        position = units[0].position if units else Position(0.0, 0.0)

        if phase == AmphibPhase.LOADING:
            # Loading takes ~2 hours
            return AmphibMovementResult(
                AmphibPhase.LOADING, position, dt, 0,
            )

        if phase == AmphibPhase.TRANSIT:
            return AmphibMovementResult(
                AmphibPhase.TRANSIT, position, dt, 0,
            )

        if phase == AmphibPhase.STAGING:
            return AmphibMovementResult(
                AmphibPhase.STAGING, position, dt, 0,
            )

        if phase == AmphibPhase.SHIP_TO_SHORE:
            # Units are transitioning to shore
            ashore = len(units) // 2  # half per wave
            return AmphibMovementResult(
                AmphibPhase.SHIP_TO_SHORE, position, dt, ashore,
            )

        if phase == AmphibPhase.BEACH_LANDING:
            return AmphibMovementResult(
                AmphibPhase.BEACH_LANDING, position, dt, len(units),
            )

        # INLAND
        return AmphibMovementResult(
            AmphibPhase.INLAND, position, dt, len(units),
        )
