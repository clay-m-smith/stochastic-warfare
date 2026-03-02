"""Stockpile management — depots and unit supply inventories.

Manages the physical storage of supplies at depots and tracks per-unit
inventories.  Handles issuing, receiving, spoilage, and depot capture.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.logistics.events import (
    SupplyDeliveredEvent,
    SupplyDepletedEvent,
    SupplyShortageEvent,
)
from stochastic_warfare.logistics.supply_classes import (
    SupplyClass,
    SupplyInventory,
    SupplyItemLoader,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums & config
# ---------------------------------------------------------------------------


class DepotType(enum.IntEnum):
    """Classification of supply storage facilities."""

    SUPPLY_POINT = 0
    LOGISTICS_SUPPORT_AREA = 1
    DEPOT = 2
    PORT_FACILITY = 3
    AIRFIELD_STORES = 4
    FORWARD_ARMING_REFUELING_POINT = 5


class StockpileConfig(BaseModel):
    """Tuning parameters for stockpile management."""

    spoilage_check_interval_hours: float = 24.0
    capture_efficiency: float = 0.5
    shortage_threshold: float = 0.25  # fraction below which shortage event fires


# ---------------------------------------------------------------------------
# Depot
# ---------------------------------------------------------------------------


@dataclass
class Depot:
    """A physical supply storage location."""

    depot_id: str
    position: Position
    depot_type: DepotType
    side: str
    inventory: SupplyInventory
    capacity_tons: float
    throughput_tons_per_hour: float
    condition: float = 1.0  # 0-1, degraded by damage


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class StockpileManager:
    """Manage supply depots and per-unit inventories.

    Parameters
    ----------
    event_bus : EventBus
        Publishes ``SupplyShortageEvent``, ``SupplyDepletedEvent``,
        ``SupplyDeliveredEvent``.
    rng : numpy.random.Generator
        Deterministic PRNG stream.
    loader : SupplyItemLoader | None
        For shelf-life lookups during spoilage checks.
    config : StockpileConfig | None
        Tuning parameters.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        loader: SupplyItemLoader | None = None,
        config: StockpileConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._loader = loader or SupplyItemLoader()
        self._config = config or StockpileConfig()
        self._depots: dict[str, Depot] = {}
        self._unit_inventories: dict[str, SupplyInventory] = {}
        self._unit_max_supplies: dict[str, dict[int, dict[str, float]]] = {}
        self._spoilage_accumulator: float = 0.0

    # -- Depot management --

    def create_depot(
        self,
        depot_id: str,
        position: Position,
        depot_type: DepotType,
        side: str,
        initial_inventory: SupplyInventory | None = None,
        capacity_tons: float = 1000.0,
        throughput_tons_per_hour: float = 50.0,
    ) -> Depot:
        """Create and register a new depot."""
        depot = Depot(
            depot_id=depot_id,
            position=position,
            depot_type=depot_type,
            side=side,
            inventory=initial_inventory or SupplyInventory(),
            capacity_tons=capacity_tons,
            throughput_tons_per_hour=throughput_tons_per_hour,
        )
        self._depots[depot_id] = depot
        logger.info("Created depot %s at %s", depot_id, position)
        return depot

    def get_depot(self, depot_id: str) -> Depot:
        """Return a depot; raises ``KeyError`` if not found."""
        return self._depots[depot_id]

    def list_depots(self, side: str | None = None) -> list[Depot]:
        """Return depots, optionally filtered by side."""
        if side is None:
            return list(self._depots.values())
        return [d for d in self._depots.values() if d.side == side]

    # -- Unit inventory management --

    def register_unit_inventory(
        self,
        unit_id: str,
        inventory: SupplyInventory,
        max_supplies: dict[int, dict[str, float]] | None = None,
    ) -> None:
        """Register a unit's supply inventory for tracking."""
        self._unit_inventories[unit_id] = inventory
        if max_supplies is not None:
            self._unit_max_supplies[unit_id] = max_supplies

    def get_unit_inventory(self, unit_id: str) -> SupplyInventory:
        """Return a unit's inventory; raises ``KeyError`` if not registered."""
        return self._unit_inventories[unit_id]

    # -- Issue & receive --

    def issue_supplies(
        self,
        depot_id: str,
        requests: dict[int, dict[str, float]],
    ) -> dict[int, dict[str, float]]:
        """Issue supplies from a depot.  Returns actual quantities issued.

        May be partial if depot stock is insufficient.
        """
        depot = self._depots[depot_id]
        issued: dict[int, dict[str, float]] = {}
        for cls, items in requests.items():
            for item_id, qty in items.items():
                actual = depot.inventory.consume(cls, item_id, qty)
                if actual > 0:
                    issued.setdefault(cls, {})[item_id] = actual
        return issued

    def receive_supplies(
        self,
        depot_id: str,
        supplies: dict[int, dict[str, float]],
    ) -> None:
        """Add supplies to a depot."""
        depot = self._depots[depot_id]
        for cls, items in supplies.items():
            for item_id, qty in items.items():
                depot.inventory.add(cls, item_id, qty)

    # -- Unit consumption --

    def consume_unit_supplies(
        self,
        unit_id: str,
        consumption: dict[int, dict[str, float]],
        timestamp: datetime | None = None,
    ) -> dict[int, dict[str, float]]:
        """Consume supplies from a unit's inventory.

        Returns shortfalls (requested minus actual consumed) for each
        item where supply was insufficient.
        """
        inv = self._unit_inventories[unit_id]
        shortfalls: dict[int, dict[str, float]] = {}
        for cls, items in consumption.items():
            for item_id, qty in items.items():
                actual = inv.consume(cls, item_id, qty)
                shortfall = qty - actual
                if shortfall > 0:
                    shortfalls.setdefault(cls, {})[item_id] = shortfall
                    # Check for depletion
                    if inv.available(cls, item_id) <= 0 and timestamp is not None:
                        self._event_bus.publish(SupplyDepletedEvent(
                            timestamp=timestamp,
                            source=ModuleId.LOGISTICS,
                            unit_id=unit_id,
                            supply_class=cls,
                        ))
        # Check for shortage warnings
        if timestamp is not None:
            self._check_shortages(unit_id, timestamp)
        return shortfalls

    def _check_shortages(self, unit_id: str, timestamp: datetime) -> None:
        """Publish shortage events for low supply levels."""
        inv = self._unit_inventories[unit_id]
        max_supplies = self._unit_max_supplies.get(unit_id)
        if max_supplies is None:
            return
        for cls, items in max_supplies.items():
            for item_id, max_qty in items.items():
                fraction = inv.fraction_of(cls, item_id, max_qty)
                if 0 < fraction < self._config.shortage_threshold:
                    # Estimate hours remaining (very rough)
                    hours_est = fraction * 24.0  # simple heuristic
                    self._event_bus.publish(SupplyShortageEvent(
                        timestamp=timestamp,
                        source=ModuleId.LOGISTICS,
                        unit_id=unit_id,
                        supply_class=cls,
                        current_fraction=fraction,
                        hours_remaining=hours_est,
                    ))

    # -- Supply state query --

    def get_supply_state(self, unit_id: str) -> float:
        """Return composite supply state (0-1) for combat power calculation.

        Weighted average of key supply classes relative to max capacity.
        """
        if unit_id not in self._unit_inventories:
            return 1.0  # unregistered units assumed fully supplied
        inv = self._unit_inventories[unit_id]
        max_supplies = self._unit_max_supplies.get(unit_id)
        if not max_supplies:
            return 1.0

        # Weights: fuel and ammo most critical for combat power
        weights = {
            int(SupplyClass.CLASS_I): 1.0,
            int(SupplyClass.CLASS_III): 2.0,
            int(SupplyClass.CLASS_IIIA): 2.0,
            int(SupplyClass.CLASS_V): 3.0,
            int(SupplyClass.CLASS_VIII): 1.0,
            int(SupplyClass.CLASS_IX): 1.0,
        }

        total_weight = 0.0
        weighted_sum = 0.0
        for cls, items in max_supplies.items():
            w = weights.get(cls, 1.0)
            for item_id, max_qty in items.items():
                fraction = inv.fraction_of(cls, item_id, max_qty)
                weighted_sum += fraction * w
                total_weight += w

        if total_weight == 0:
            return 1.0
        return weighted_sum / total_weight

    # -- Capture --

    def capture_depot(
        self,
        depot_id: str,
        capturing_side: str,
        timestamp: datetime | None = None,
    ) -> None:
        """Transfer a depot to the capturing side with efficiency loss."""
        depot = self._depots[depot_id]
        eff = self._config.capture_efficiency
        old_state = depot.inventory.get_state()
        depot.inventory.set_state({"items": {}})
        for cls_str, bucket in old_state["items"].items():
            for item_id, qty in bucket.items():
                depot.inventory.add(int(cls_str), item_id, qty * eff)
        depot.side = capturing_side
        logger.info(
            "Depot %s captured by %s (%.0f%% efficiency)",
            depot_id, capturing_side, eff * 100,
        )

    # -- Spoilage --

    def spoilage_check(self, dt_hours: float) -> int:
        """Check for and remove spoiled perishable items.

        Returns the number of items spoiled.
        """
        self._spoilage_accumulator += dt_hours
        if self._spoilage_accumulator < self._config.spoilage_check_interval_hours:
            return 0
        self._spoilage_accumulator = 0.0

        spoiled_count = 0
        # Check depot inventories
        for depot in self._depots.values():
            spoiled_count += self._spoil_inventory(depot.inventory, dt_hours)
        # Check unit inventories
        for inv in self._unit_inventories.values():
            spoiled_count += self._spoil_inventory(inv, dt_hours)
        return spoiled_count

    def _spoil_inventory(self, inv: SupplyInventory, dt_hours: float) -> int:
        """Remove expired perishables from an inventory."""
        spoiled = 0
        try:
            self._loader.load_all()
        except Exception:
            return 0
        state = inv.get_state()
        for cls_str, bucket in state["items"].items():
            for item_id, qty in bucket.items():
                if qty <= 0:
                    continue
                try:
                    defn = self._loader.get_definition(item_id)
                except KeyError:
                    continue
                if defn.perishable and defn.shelf_life_hours is not None:
                    # Probabilistic spoilage: chance proportional to
                    # check_interval / shelf_life
                    spoilage_prob = (
                        self._config.spoilage_check_interval_hours / defn.shelf_life_hours
                    )
                    if self._rng.random() < spoilage_prob:
                        # Spoil a fraction
                        spoil_qty = qty * spoilage_prob
                        inv.consume(int(cls_str), item_id, spoil_qty)
                        spoiled += 1
        return spoiled

    # -- State protocol --

    def get_state(self) -> dict:
        """Serialize for checkpoint."""
        return {
            "depots": {
                did: {
                    "depot_id": d.depot_id,
                    "position": list(d.position),
                    "depot_type": int(d.depot_type),
                    "side": d.side,
                    "inventory": d.inventory.get_state(),
                    "capacity_tons": d.capacity_tons,
                    "throughput_tons_per_hour": d.throughput_tons_per_hour,
                    "condition": d.condition,
                }
                for did, d in self._depots.items()
            },
            "unit_inventories": {
                uid: inv.get_state()
                for uid, inv in self._unit_inventories.items()
            },
            "unit_max_supplies": dict(self._unit_max_supplies),
            "spoilage_accumulator": self._spoilage_accumulator,
        }

    def set_state(self, state: dict) -> None:
        """Restore from checkpoint."""
        self._depots.clear()
        for did, sd in state["depots"].items():
            inv = SupplyInventory()
            inv.set_state(sd["inventory"])
            self._depots[did] = Depot(
                depot_id=sd["depot_id"],
                position=Position(*sd["position"]),
                depot_type=DepotType(sd["depot_type"]),
                side=sd["side"],
                inventory=inv,
                capacity_tons=sd["capacity_tons"],
                throughput_tons_per_hour=sd["throughput_tons_per_hour"],
                condition=sd["condition"],
            )
        self._unit_inventories.clear()
        for uid, inv_state in state["unit_inventories"].items():
            inv = SupplyInventory()
            inv.set_state(inv_state)
            self._unit_inventories[uid] = inv
        self._unit_max_supplies = dict(state.get("unit_max_supplies", {}))
        self._spoilage_accumulator = state.get("spoilage_accumulator", 0.0)
