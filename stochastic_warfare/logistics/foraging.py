"""Napoleonic foraging logistics — living off the land.

Napoleonic armies "lived off the land."  Terrain productivity × seasonal
modifier × army size determines food supply.  Depletion and recovery
model.  Simplified but captures the key dynamic (army size vs land
capacity).
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TerrainProductivity(enum.IntEnum):
    """Agricultural productivity of terrain."""

    BARREN = 0
    POOR = 1
    AVERAGE = 2
    GOOD = 3
    ABUNDANT = 4


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class ForagingConfig(BaseModel):
    """Configuration for Napoleonic foraging model."""

    productivity_values: dict[int, float] = {
        TerrainProductivity.BARREN: 0.1,
        TerrainProductivity.POOR: 0.3,
        TerrainProductivity.AVERAGE: 0.5,
        TerrainProductivity.GOOD: 0.7,
        TerrainProductivity.ABUNDANT: 1.0,
    }

    seasonal_modifiers: dict[str, float] = {
        "spring": 0.3,
        "summer": 0.8,
        "autumn": 1.0,
        "winter": 0.1,
    }

    men_per_km2_per_day: float = 500.0
    depletion_rate: float = 0.1
    recovery_days: float = 30.0
    foraging_party_fraction: float = 0.10
    ambush_risk_per_mission: float = 0.05
    attrition_rate_no_food: float = 0.01
    ambush_casualty_rate: float = 0.1


# ---------------------------------------------------------------------------
# Zone model
# ---------------------------------------------------------------------------


@dataclass
class ForageZone:
    """A terrain zone available for foraging."""

    zone_id: str
    position: tuple[float, float]
    radius_m: float
    productivity: TerrainProductivity
    remaining_fraction: float = 1.0


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass
class ForageResult:
    """Result of a foraging operation."""

    rations_supplied: float
    rations_needed: float
    deficit: float
    zone_depleted_by: float
    ambush_occurred: bool
    ambush_casualties: int


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ForagingEngine:
    """Napoleonic foraging logistics engine.

    Parameters
    ----------
    config:
        Foraging configuration.
    rng:
        Numpy random generator.
    """

    def __init__(
        self,
        config: ForagingConfig | None = None,
        *,
        rng: np.random.Generator,
    ) -> None:
        self._config = config or ForagingConfig()
        self._rng = rng
        self._zones: dict[str, ForageZone] = {}

    def register_zone(
        self,
        zone_id: str,
        position: tuple[float, float],
        radius_m: float,
        productivity: TerrainProductivity,
    ) -> ForageZone:
        """Register a forage zone."""
        zone = ForageZone(
            zone_id=zone_id,
            position=position,
            radius_m=radius_m,
            productivity=productivity,
        )
        self._zones[zone_id] = zone
        return zone

    def compute_daily_capacity(
        self,
        zone_id: str,
        season: str = "summer",
    ) -> float:
        """Compute how many men a zone can feed per day.

        Parameters
        ----------
        zone_id:
            Zone identifier.
        season:
            Season string (``"spring"``, ``"summer"``, ``"autumn"``, ``"winter"``).

        Returns
        -------
        Number of men that can be sustained per day.
        """
        zone = self._zones.get(zone_id)
        if zone is None:
            return 0.0

        cfg = self._config
        area_km2 = math.pi * (zone.radius_m / 1000.0) ** 2
        prod = cfg.productivity_values.get(int(zone.productivity), 0.5)
        seasonal = cfg.seasonal_modifiers.get(season, 0.5)

        return (
            cfg.men_per_km2_per_day
            * area_km2
            * prod
            * seasonal
            * zone.remaining_fraction
        )

    def forage(
        self,
        zone_id: str,
        army_size: int,
        season: str = "summer",
    ) -> ForageResult:
        """Execute a foraging operation for one day.

        Parameters
        ----------
        zone_id:
            Zone to forage in.
        army_size:
            Number of men to feed.
        season:
            Current season.
        """
        zone = self._zones.get(zone_id)
        if zone is None:
            return ForageResult(
                rations_supplied=0.0,
                rations_needed=float(army_size),
                deficit=float(army_size),
                zone_depleted_by=0.0,
                ambush_occurred=False,
                ambush_casualties=0,
            )

        cfg = self._config
        capacity = self.compute_daily_capacity(zone_id, season)
        rations_supplied = min(float(army_size), capacity)
        deficit = max(0.0, float(army_size) - capacity)

        # Zone depletion
        if capacity > 0:
            depletion = cfg.depletion_rate * (army_size / capacity)
        else:
            depletion = cfg.depletion_rate
        depletion = min(zone.remaining_fraction, depletion)
        zone.remaining_fraction = max(0.0, zone.remaining_fraction - depletion)

        # Ambush risk for foraging parties
        foraging_party_size = int(army_size * cfg.foraging_party_fraction)
        ambush = bool(self._rng.random() < cfg.ambush_risk_per_mission)
        ambush_casualties = 0
        if ambush and foraging_party_size > 0:
            ambush_casualties = int(
                self._rng.binomial(foraging_party_size, cfg.ambush_casualty_rate),
            )

        return ForageResult(
            rations_supplied=rations_supplied,
            rations_needed=float(army_size),
            deficit=deficit,
            zone_depleted_by=depletion,
            ambush_occurred=ambush,
            ambush_casualties=ambush_casualties,
        )

    def update_recovery(self, dt_days: float) -> None:
        """Recover depleted zones over time.

        Parameters
        ----------
        dt_days:
            Time step in days.
        """
        cfg = self._config
        recovery = dt_days / cfg.recovery_days
        for zone in self._zones.values():
            if zone.remaining_fraction < 1.0:
                zone.remaining_fraction = min(
                    1.0,
                    zone.remaining_fraction + recovery,
                )

    # ── State persistence ─────────────────────────────────────────────

    def get_state(self) -> dict[str, Any]:
        """Capture state for checkpointing."""
        return {
            "zones": {
                zid: {
                    "zone_id": z.zone_id,
                    "position": list(z.position),
                    "radius_m": z.radius_m,
                    "productivity": int(z.productivity),
                    "remaining_fraction": z.remaining_fraction,
                }
                for zid, z in self._zones.items()
            },
        }

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore state from checkpoint."""
        self._zones.clear()
        for zid, zdata in state.get("zones", {}).items():
            self._zones[zid] = ForageZone(
                zone_id=zdata["zone_id"],
                position=tuple(zdata["position"]),
                radius_m=zdata["radius_m"],
                productivity=TerrainProductivity(zdata["productivity"]),
                remaining_fraction=zdata["remaining_fraction"],
            )
