"""Civilian entity manager — regions, disposition, displacement tracking.

Phase 12e-1.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums & types
# ---------------------------------------------------------------------------


class CivilianDisposition(enum.IntEnum):
    """Population disposition toward a side."""

    FRIENDLY = 0
    NEUTRAL = 1
    HOSTILE = 2
    MIXED = 3


@dataclass
class CivilianRegion:
    """A geographic region with civilian population."""

    region_id: str
    center: Position
    radius_m: float
    population: int
    disposition: CivilianDisposition = CivilianDisposition.NEUTRAL
    displaced_count: int = 0
    cumulative_collateral: int = 0


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class CivilianManagerConfig(BaseModel):
    """Configuration for civilian population management."""

    default_disposition: str = "NEUTRAL"


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class CivilianManager:
    """Track civilian regions, disposition, and displacement.

    Parameters
    ----------
    event_bus : EventBus
        For publishing population events.
    rng : numpy.random.Generator
        Deterministic PRNG stream.
    config : CivilianManagerConfig | None
        Configuration.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: CivilianManagerConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or CivilianManagerConfig()
        self._regions: dict[str, CivilianRegion] = {}

    def register_region(self, region: CivilianRegion) -> None:
        """Register a civilian region."""
        self._regions[region.region_id] = region
        logger.debug(
            "Registered region %s (pop=%d, disp=%s)",
            region.region_id, region.population, region.disposition.name,
        )

    def get_region(self, region_id: str) -> CivilianRegion:
        """Return a region; raises ``KeyError`` if not found."""
        return self._regions[region_id]

    def all_regions(self) -> list[CivilianRegion]:
        """Return all registered regions."""
        return list(self._regions.values())

    def get_regions_by_disposition(self, disposition: CivilianDisposition) -> list[CivilianRegion]:
        """Return all regions with the given disposition."""
        return [r for r in self._regions.values() if r.disposition == disposition]

    def query_disposition_at(self, position: Position) -> CivilianDisposition | None:
        """Return the disposition of the region containing *position*.

        Returns ``None`` if the position is outside all regions.
        """
        for region in self._regions.values():
            dx = position.easting - region.center.easting
            dy = position.northing - region.center.northing
            if math.hypot(dx, dy) <= region.radius_m:
                return region.disposition
        return None

    def record_displacement(self, region_id: str, count: int) -> None:
        """Record *count* civilians displaced from a region."""
        region = self._regions[region_id]
        region.displaced_count += count
        region.displaced_count = min(region.displaced_count, region.population)

    def total_displaced(self) -> int:
        """Return total displaced civilians across all regions."""
        return sum(r.displaced_count for r in self._regions.values())

    def record_collateral(self, region_id: str, casualties: int) -> None:
        """Record collateral damage in a region."""
        region = self._regions[region_id]
        region.cumulative_collateral += casualties

    # -- State protocol --

    def get_state(self) -> dict:
        return {
            "regions": {
                rid: {
                    "region_id": r.region_id,
                    "center": list(r.center),
                    "radius_m": r.radius_m,
                    "population": r.population,
                    "disposition": int(r.disposition),
                    "displaced_count": r.displaced_count,
                    "cumulative_collateral": r.cumulative_collateral,
                }
                for rid, r in self._regions.items()
            },
        }

    def set_state(self, state: dict) -> None:
        self._regions.clear()
        for rid, rd in state["regions"].items():
            self._regions[rid] = CivilianRegion(
                region_id=rd["region_id"],
                center=Position(*rd["center"]),
                radius_m=rd["radius_m"],
                population=rd["population"],
                disposition=CivilianDisposition(rd["disposition"]),
                displaced_count=rd.get("displaced_count", 0),
                cumulative_collateral=rd.get("cumulative_collateral", 0),
            )
