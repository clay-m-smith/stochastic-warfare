"""Naval basing — bases, repair capacity, station time, tidal access.

Provides the shore infrastructure that sustains fleet operations: fuel
storage, berths, repair docks, and throughput limits.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import Position

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums & types
# ---------------------------------------------------------------------------


class NavalBaseType(enum.IntEnum):
    """Classification of naval shore facilities."""

    NAVAL_BASE = 0
    FORWARD_OPERATING_BASE = 1
    ANCHORAGE = 2
    DRY_DOCK = 3


@dataclass
class NavalBase:
    """A naval shore facility."""

    base_id: str
    base_type: NavalBaseType
    port_id: str | None
    position: Position
    side: str
    repair_capacity: int  # number of ships that can be repaired concurrently
    fuel_storage_tons: float
    berths: int
    condition: float = 1.0  # 0-1


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class NavalBasingConfig(BaseModel):
    """Tuning parameters for naval basing operations."""

    base_throughput_tons_per_hour: float = 100.0
    tidal_access_margin_m: float = 1.0
    fuel_reserve_warning_fraction: float = 0.2


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class NavalBasingEngine:
    """Manage naval bases and their support capabilities.

    Parameters
    ----------
    event_bus : EventBus
        For future event publishing.
    rng : numpy.random.Generator
        Deterministic PRNG stream.
    config : NavalBasingConfig | None
        Tuning parameters.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: NavalBasingConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or NavalBasingConfig()
        self._bases: dict[str, NavalBase] = {}

    def register_base(self, base: NavalBase) -> None:
        """Register a naval base."""
        self._bases[base.base_id] = base
        logger.info("Registered naval base %s (%s)", base.base_id, base.base_type.name)

    def get_base(self, base_id: str) -> NavalBase:
        """Return a base; raises ``KeyError`` if not found."""
        return self._bases[base_id]

    def list_bases(self, side: str | None = None) -> list[NavalBase]:
        """Return bases, optionally filtered by side."""
        if side is None:
            return list(self._bases.values())
        return [b for b in self._bases.values() if b.side == side]

    def get_repair_capacity(self, base_id: str) -> int:
        """Return the number of ships that can be repaired at a base."""
        base = self._bases[base_id]
        return int(base.repair_capacity * base.condition)

    def compute_station_time(
        self,
        fuel_remaining_tons: float,
        fuel_consumption_rate_tons_per_hour: float,
        distance_to_base_m: float,
        transit_speed_mps: float = 8.0,
    ) -> float:
        """Compute how long a ship can remain on station.

        Returns hours of station time before needing to return to base
        (accounting for transit fuel).
        """
        if fuel_consumption_rate_tons_per_hour <= 0 or transit_speed_mps <= 0:
            return float("inf")
        # Transit time (one way) in hours
        transit_hours = distance_to_base_m / (transit_speed_mps * 3600.0)
        # Fuel needed for transit (round trip)
        transit_fuel = fuel_consumption_rate_tons_per_hour * transit_hours * 2
        # Usable fuel after reserving transit
        usable_fuel = fuel_remaining_tons - transit_fuel
        if usable_fuel <= 0:
            return 0.0
        return usable_fuel / fuel_consumption_rate_tons_per_hour

    def port_throughput(
        self,
        base_id: str,
        sea_state: int = 2,
    ) -> float:
        """Return effective port throughput in tons/hour."""
        base = self._bases[base_id]
        # Sea state reduces throughput for exposed facilities
        sea_state_factor = 1.0
        if base.base_type == NavalBaseType.ANCHORAGE:
            sea_state_factor = max(0.0, 1.0 - sea_state * 0.15)
        elif base.base_type == NavalBaseType.FORWARD_OPERATING_BASE:
            sea_state_factor = max(0.0, 1.0 - sea_state * 0.1)
        return self._config.base_throughput_tons_per_hour * base.condition * sea_state_factor

    def tidal_access(
        self,
        base_id: str,
        tide_height_m: float,
        ship_draft_m: float,
        channel_depth_m: float = 10.0,
    ) -> bool:
        """Check if a ship can access a base given current tide.

        The ship needs ``draft + margin <= channel_depth + tide_height``.
        """
        margin = self._config.tidal_access_margin_m
        available_depth = channel_depth_m + tide_height_m
        return ship_draft_m + margin <= available_depth

    # -- State protocol --

    def get_state(self) -> dict:
        """Serialize for checkpoint."""
        return {
            "bases": {
                bid: {
                    "base_id": b.base_id,
                    "base_type": int(b.base_type),
                    "port_id": b.port_id,
                    "position": list(b.position),
                    "side": b.side,
                    "repair_capacity": b.repair_capacity,
                    "fuel_storage_tons": b.fuel_storage_tons,
                    "berths": b.berths,
                    "condition": b.condition,
                }
                for bid, b in self._bases.items()
            },
        }

    def set_state(self, state: dict) -> None:
        """Restore from checkpoint."""
        self._bases.clear()
        for bid, bd in state["bases"].items():
            self._bases[bid] = NavalBase(
                base_id=bd["base_id"],
                base_type=NavalBaseType(bd["base_type"]),
                port_id=bd.get("port_id"),
                position=Position(*bd["position"]),
                side=bd["side"],
                repair_capacity=bd["repair_capacity"],
                fuel_storage_tons=bd["fuel_storage_tons"],
                berths=bd["berths"],
                condition=bd.get("condition", 1.0),
            )
