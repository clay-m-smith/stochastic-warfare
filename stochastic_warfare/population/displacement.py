"""Refugee displacement engine.

Phase 12e-2. Combat intensity drives civilian displacement along road
networks. Refugees reduce transport throughput.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.population.civilians import CivilianManager
from stochastic_warfare.population.events import DisplacementEvent

logger = get_logger(__name__)


class DisplacementConfig(BaseModel):
    """Displacement engine configuration."""

    displacement_rate_per_intensity: float = 0.05
    """Fraction of population displaced per unit combat intensity per hour."""
    refugee_transport_penalty: float = 0.1
    """Transport speed penalty per 1000 refugees on a route."""
    max_displacement_fraction: float = 0.8
    """Maximum fraction of population that can be displaced."""


class DisplacementEngine:
    """Compute civilian displacement from combat zones.

    Parameters
    ----------
    civilian_manager : CivilianManager
        Source of civilian region data.
    event_bus : EventBus
        For publishing displacement events.
    rng : numpy.random.Generator
        Deterministic PRNG stream.
    config : DisplacementConfig | None
        Configuration.
    """

    def __init__(
        self,
        civilian_manager: CivilianManager,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: DisplacementConfig | None = None,
    ) -> None:
        self._civilians = civilian_manager
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or DisplacementConfig()

    def update(
        self,
        dt_hours: float,
        combat_zones: list[tuple[Position, float]] | None = None,
        timestamp: datetime | None = None,
    ) -> dict[str, int]:
        """Advance displacement simulation.

        Parameters
        ----------
        dt_hours:
            Time step in hours.
        combat_zones:
            List of (position, intensity) pairs where combat is occurring.
            Intensity 0.0-1.0.
        timestamp:
            Simulation timestamp.

        Returns
        -------
        dict[str, int]
            Region ID → newly displaced count.
        """
        if combat_zones is None:
            return {}

        ts = timestamp or datetime.now(tz=timezone.utc)
        cfg = self._config
        results: dict[str, int] = {}

        for region in self._civilians.all_regions():
            # Find maximum combat intensity affecting this region
            max_intensity = 0.0
            for zone_pos, intensity in combat_zones:
                dx = zone_pos.easting - region.center.easting
                dy = zone_pos.northing - region.center.northing
                dist = math.hypot(dx, dy)
                if dist <= region.radius_m * 2.0:
                    # Intensity falls off with distance
                    falloff = max(0.0, 1.0 - dist / (region.radius_m * 2.0))
                    max_intensity = max(max_intensity, intensity * falloff)

            if max_intensity <= 0.0:
                continue

            # Compute displacement
            max_displaceable = int(
                region.population * cfg.max_displacement_fraction
            ) - region.displaced_count
            if max_displaceable <= 0:
                continue

            rate = cfg.displacement_rate_per_intensity * max_intensity * dt_hours
            # Add stochastic variation
            rate *= 0.5 + self._rng.random()
            newly_displaced = min(max_displaceable, int(rate * region.population))

            if newly_displaced > 0:
                self._civilians.record_displacement(region.region_id, newly_displaced)
                results[region.region_id] = newly_displaced
                self._event_bus.publish(DisplacementEvent(
                    timestamp=ts,
                    source=ModuleId.POPULATION,
                    region_id=region.region_id,
                    displaced_count=newly_displaced,
                ))

        return results

    def compute_transport_penalty(self, route_displaced_count: int) -> float:
        """Compute transport speed penalty from refugees on a route.

        Parameters
        ----------
        route_displaced_count:
            Number of refugees on the transport route.

        Returns
        -------
        float
            Speed multiplier 0.0-1.0 (1.0 = no penalty).
        """
        penalty = self._config.refugee_transport_penalty * (
            route_displaced_count / 1000.0
        )
        return max(0.1, 1.0 - penalty)  # minimum 10% speed
