"""Stockpile management — depots and unit supply inventories.

Manages the physical storage of supplies at depots and tracks per-unit
inventories.  Handles issuing, receiving, spoilage, and depot capture.
"""

from __future__ import annotations

import enum
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict

from stochastic_warfare.core.events import Event, EventBus
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

    model_config = ConfigDict(extra="forbid")

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


@dataclass(frozen=True)
class SupplyDeliveryResult:
    """Committed item-native quantity and corresponding metric-ton mass."""

    quantity: float
    quantity_tons: float


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
        _validate_stockpile_config(self._config)
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
        condition: float = 1.0,
    ) -> Depot:
        """Create and register a new depot."""
        _validate_identifier(depot_id, "depot ID")
        _validate_identifier(side, "depot side")
        if depot_id in self._depots:
            raise ValueError(f"Duplicate depot ID: {depot_id}")
        _validate_position(position, f"depot {depot_id} position")
        if isinstance(depot_type, bool) or not isinstance(depot_type, int):
            raise ValueError(f"Invalid depot type for {depot_id}")
        try:
            normalized_depot_type = DepotType(depot_type)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid depot type for {depot_id}") from exc
        _validate_positive_finite(capacity_tons, f"depot {depot_id} capacity")
        _validate_positive_finite(
            throughput_tons_per_hour,
            f"depot {depot_id} throughput",
        )
        _validate_unit_interval(condition, f"depot {depot_id} condition")
        inventory = initial_inventory or SupplyInventory()
        _normalize_inventory_state(
            inventory.get_state(),
            f"depot {depot_id} inventory",
        )
        depot = Depot(
            depot_id=depot_id,
            position=position,
            depot_type=normalized_depot_type,
            side=side,
            inventory=inventory,
            capacity_tons=capacity_tons,
            throughput_tons_per_hour=throughput_tons_per_hour,
            condition=condition,
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
            return [self._depots[depot_id] for depot_id in sorted(self._depots)]
        return [
            self._depots[depot_id]
            for depot_id in sorted(self._depots)
            if self._depots[depot_id].side == side
        ]

    # -- Unit inventory management --

    def register_unit_inventory(
        self,
        unit_id: str,
        inventory: SupplyInventory,
        max_supplies: dict[int, dict[str, float]] | None = None,
    ) -> None:
        """Register a unit's supply inventory for tracking."""
        _validate_identifier(unit_id, "unit ID")
        if unit_id in self._unit_inventories:
            raise ValueError(f"Duplicate unit inventory: {unit_id}")
        inventory_state = _normalize_inventory_state(
            inventory.get_state(),
            f"unit {unit_id} inventory",
        )
        normalized_max = (
            _normalize_supply_map(
                max_supplies,
                f"unit {unit_id} maximum supplies",
                strictly_positive=True,
            )
            if max_supplies is not None
            else None
        )
        if normalized_max is not None:
            _validate_inventory_within_maximum(
                inventory_state,
                normalized_max,
                unit_id,
            )
        self._unit_inventories[unit_id] = inventory
        if normalized_max is not None:
            self._unit_max_supplies[unit_id] = normalized_max

    def get_unit_inventory(self, unit_id: str) -> SupplyInventory:
        """Return a unit's inventory; raises ``KeyError`` if not registered."""
        return self._unit_inventories[unit_id]

    def has_unit_inventory(self, unit_id: str) -> bool:
        """Return whether *unit_id* has a registered logistics inventory."""
        return unit_id in self._unit_inventories

    def registered_unit_ids(self) -> list[str]:
        """Return registered unit IDs in deterministic order."""
        return sorted(self._unit_inventories)

    def get_unit_max_supplies(
        self,
        unit_id: str,
    ) -> dict[int, dict[str, float]]:
        """Return a defensive, deterministically ordered maximum inventory."""
        if unit_id not in self._unit_inventories:
            raise KeyError(unit_id)
        maxima = self._unit_max_supplies.get(unit_id, {})
        return {
            supply_class: {
                item_id: items[item_id]
                for item_id in sorted(items)
            }
            for supply_class, items in sorted(maxima.items())
        }

    def get_unit_deficits(
        self,
        unit_id: str,
    ) -> dict[int, dict[str, float]]:
        """Return positive item-native deficits relative to registered maxima."""
        inventory = self._unit_inventories[unit_id]
        deficits: dict[int, dict[str, float]] = {}
        for supply_class, items in self.get_unit_max_supplies(unit_id).items():
            for item_id, maximum in items.items():
                deficit = maximum - inventory.available(supply_class, item_id)
                if deficit > 0.0:
                    deficits.setdefault(supply_class, {})[item_id] = deficit
        return deficits

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
        normalized = _normalize_supply_map(
            requests,
            "supply issue request",
            strictly_positive=False,
        )
        issued: dict[int, dict[str, float]] = {}
        for cls, items in normalized.items():
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
        normalized = _normalize_supply_map(
            supplies,
            "supply receipt",
            strictly_positive=False,
        )
        for cls, items in normalized.items():
            for item_id, qty in items.items():
                depot.inventory.add(cls, item_id, qty)

    def quantity_weight_tons(self, item_id: str, quantity: float) -> float:
        """Convert an item-native quantity to metric tons using catalog mass."""
        _validate_identifier(item_id, "supply item ID")
        _validate_nonnegative_finite(quantity, f"{item_id} quantity")
        definition = self._get_item_definition(item_id)
        _validate_positive_finite(
            definition.weight_per_unit_kg,
            f"{item_id} weight_per_unit_kg",
        )
        return quantity * definition.weight_per_unit_kg / 1000.0

    def deliver_to_unit(
        self,
        depot_id: str,
        unit_id: str,
        supply_class: int,
        item_id: str,
        requested_quantity: float,
        max_quantity_tons: float,
        timestamp: datetime,
        transport_mode: int,
        route_id: str = "",
        event_sink: list[Event] | None = None,
    ) -> SupplyDeliveryResult:
        """Atomically transfer one catalog item from a depot to a unit.

        ``requested_quantity`` and the returned ``quantity`` use the item's
        native catalog unit.  The transfer is capped by unit deficit, depot
        stock, and ``max_quantity_tons``.
        """
        depot = self._depots[depot_id]
        unit_inventory = self._unit_inventories[unit_id]
        supply_class_value = _normalize_supply_class(
            supply_class,
            "delivery supply class",
        )
        _validate_identifier(item_id, "delivery item ID")
        _validate_nonnegative_finite(
            requested_quantity,
            "requested delivery quantity",
        )
        _validate_nonnegative_finite(
            max_quantity_tons,
            "maximum delivery tons",
        )
        if not isinstance(timestamp, datetime):
            raise TypeError("delivery timestamp must be a datetime")
        if isinstance(transport_mode, bool) or not isinstance(
            transport_mode,
            (int, enum.IntEnum),
        ):
            raise TypeError("delivery transport mode must be an integer enum value")
        if not isinstance(route_id, str):
            raise TypeError("delivery route ID must be a string")
        if event_sink is not None and not isinstance(event_sink, list):
            raise TypeError("event_sink must be a list or None")

        definition = self._get_item_definition(item_id)
        if definition.supply_class_enum != SupplyClass(supply_class_value):
            raise ValueError(
                f"Supply class {supply_class_value} does not match catalog item "
                f"{item_id} ({definition.supply_class})",
            )
        weight_per_unit_kg = definition.weight_per_unit_kg
        _validate_positive_finite(
            weight_per_unit_kg,
            f"{item_id} weight_per_unit_kg",
        )
        maximum = self._unit_max_supplies.get(unit_id, {}).get(
            supply_class_value,
            {},
        ).get(item_id)
        if maximum is None:
            raise KeyError(
                f"No maximum supply registered for {unit_id}:"
                f"{supply_class_value}/{item_id}",
            )

        deficit = max(
            0.0,
            maximum - unit_inventory.available(supply_class_value, item_id),
        )
        depot_available = depot.inventory.available(supply_class_value, item_id)
        mass_limited_quantity = max_quantity_tons * 1000.0 / weight_per_unit_kg
        quantity = min(
            requested_quantity,
            deficit,
            depot_available,
            mass_limited_quantity,
        )
        if quantity <= 0.0:
            return SupplyDeliveryResult(quantity=0.0, quantity_tons=0.0)

        depot_before = depot.inventory.get_state()
        actual = depot.inventory.consume(supply_class_value, item_id, quantity)
        if actual != quantity:
            depot.inventory.set_state(depot_before)
            raise RuntimeError(
                f"Depot {depot_id} issued {actual} instead of staged {quantity}",
            )
        unit_inventory.add(supply_class_value, item_id, actual)
        quantity_tons = actual * weight_per_unit_kg / 1000.0
        event = SupplyDeliveredEvent(
            timestamp=timestamp,
            source=ModuleId.LOGISTICS,
            recipient_id=unit_id,
            supply_class=supply_class_value,
            quantity=actual,
            transport_mode=int(transport_mode),
            depot_id=depot_id,
            item_id=item_id,
            route_id=route_id,
            quantity_tons=quantity_tons,
        )
        if event_sink is not None:
            event_sink.append(event)
        else:
            self.publish_events([event])
        return SupplyDeliveryResult(
            quantity=actual,
            quantity_tons=quantity_tons,
        )

    def _get_item_definition(self, item_id: str) -> Any:
        """Resolve one item, loading the configured catalog on first access."""
        try:
            return self._loader.get_definition(item_id)
        except KeyError:
            self._loader.load_all()
            return self._loader.get_definition(item_id)

    # -- Unit consumption --

    def consume_unit_supplies(
        self,
        unit_id: str,
        consumption: dict[int, dict[str, float]],
        timestamp: datetime | None = None,
        event_sink: list[Event] | None = None,
    ) -> dict[int, dict[str, float]]:
        """Consume supplies from a unit's inventory.

        Returns shortfalls (requested minus actual consumed) for each
        item where supply was insufficient.
        """
        inv = self._unit_inventories[unit_id]
        if event_sink is not None and not isinstance(event_sink, list):
            raise TypeError("event_sink must be a list or None")
        publish_after_commit = event_sink is None
        committed_events: list[Event] = [] if event_sink is None else event_sink
        normalized = _normalize_supply_map(
            consumption,
            "unit supply consumption",
            strictly_positive=False,
        )
        shortfalls: dict[int, dict[str, float]] = {}
        for cls, items in normalized.items():
            class_total_before = inv.total_by_class(cls)
            for item_id, qty in items.items():
                actual = inv.consume(cls, item_id, qty)
                shortfall = qty - actual
                if shortfall > 0:
                    shortfalls.setdefault(cls, {})[item_id] = shortfall
            if (
                timestamp is not None
                and class_total_before > 0.0
                and inv.total_by_class(cls) <= 0.0
            ):
                event = SupplyDepletedEvent(
                    timestamp=timestamp,
                    source=ModuleId.LOGISTICS,
                    unit_id=unit_id,
                    supply_class=cls,
                )
                committed_events.append(event)
        # Check for shortage warnings
        if timestamp is not None:
            self._check_shortages(
                unit_id,
                timestamp,
                event_sink=committed_events,
            )
        if publish_after_commit:
            self.publish_events(committed_events)
        return shortfalls

    def _check_shortages(
        self,
        unit_id: str,
        timestamp: datetime,
        *,
        event_sink: list[Event] | None = None,
    ) -> None:
        """Publish shortage events for low supply levels."""
        inv = self._unit_inventories[unit_id]
        max_supplies = self._unit_max_supplies.get(unit_id)
        if max_supplies is None:
            return
        for cls, items in sorted(max_supplies.items()):
            for item_id, max_qty in sorted(items.items()):
                fraction = inv.fraction_of(cls, item_id, max_qty)
                if 0 < fraction < self._config.shortage_threshold:
                    # Estimate hours remaining (very rough)
                    hours_est = fraction * 24.0  # simple heuristic
                    event = SupplyShortageEvent(
                        timestamp=timestamp,
                        source=ModuleId.LOGISTICS,
                        unit_id=unit_id,
                        supply_class=cls,
                        current_fraction=fraction,
                        hours_remaining=hours_est,
                    )
                    if event_sink is None:
                        self._event_bus.publish(event)
                    else:
                        event_sink.append(event)

    def publish_events(self, events: Sequence[Event]) -> None:
        """Publish an already committed deterministic event batch."""
        failures: list[Exception] = []
        for event in events:
            failures.extend(self._event_bus.publish_collecting(event))
        if failures:
            raise ExceptionGroup(
                "Logistics event subscriber failures after state commit",
                failures,
            )

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
        for cls, items in sorted(max_supplies.items()):
            w = weights.get(cls, 1.0)
            for item_id, max_qty in sorted(items.items()):
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
        for depot_id in sorted(self._depots):
            spoiled_count += self._spoil_inventory(
                self._depots[depot_id].inventory,
                dt_hours,
            )
        # Check unit inventories
        for unit_id in sorted(self._unit_inventories):
            spoiled_count += self._spoil_inventory(
                self._unit_inventories[unit_id],
                dt_hours,
            )
        return spoiled_count

    def _spoil_inventory(self, inv: SupplyInventory, dt_hours: float) -> int:
        """Remove expired perishables from an inventory."""
        spoiled = 0
        try:
            self._loader.load_all()
        except Exception:
            return 0
        state = inv.get_state()
        for cls_str, bucket in sorted(
            state["items"].items(),
            key=lambda item: int(item[0]),
        ):
            for item_id, qty in sorted(bucket.items()):
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
            "config": self._config.model_dump(mode="json"),
            "depots": {
                did: {
                    "depot_id": d.depot_id,
                    "position": list(d.position),
                    "depot_type": int(d.depot_type),
                    "side": d.side,
                    "inventory": _normalize_inventory_state(
                        d.inventory.get_state(),
                        f"depot {did} inventory",
                    ),
                    "capacity_tons": d.capacity_tons,
                    "throughput_tons_per_hour": d.throughput_tons_per_hour,
                    "condition": d.condition,
                }
                for did, d in (
                    (depot_id, self._depots[depot_id])
                    for depot_id in sorted(self._depots)
                )
            },
            "unit_inventories": {
                uid: _normalize_inventory_state(
                    self._unit_inventories[uid].get_state(),
                    f"unit {uid} inventory",
                )
                for uid in sorted(self._unit_inventories)
            },
            "unit_max_supplies": {
                uid: {
                    str(supply_class): {
                        item_id: items[item_id]
                        for item_id in sorted(items)
                    }
                    for supply_class, items in sorted(
                        self._unit_max_supplies[uid].items(),
                    )
                }
                for uid in sorted(self._unit_max_supplies)
            },
            "spoilage_accumulator": self._spoilage_accumulator,
        }

    def set_state(self, state: dict) -> None:
        """Restore a validated checkpoint without partial mutation."""
        if not isinstance(state, dict):
            raise TypeError("Stockpile state must be a mapping")
        depot_states = state.get("depots")
        inventory_states = state.get("unit_inventories")
        maxima_states = state.get("unit_max_supplies", {})
        if not isinstance(depot_states, dict):
            raise ValueError("Stockpile state depots must be a mapping")
        if not isinstance(inventory_states, dict):
            raise ValueError("Stockpile state unit_inventories must be a mapping")
        if not isinstance(maxima_states, dict):
            raise ValueError("Stockpile state unit_max_supplies must be a mapping")

        staged_depots: dict[str, Depot] = {}
        for did, sd in sorted(depot_states.items()):
            _validate_identifier(did, "depot state key")
            if not isinstance(sd, dict):
                raise ValueError(f"Depot state {did} must be a mapping")
            declared_id = sd.get("depot_id")
            if declared_id != did:
                raise ValueError(
                    f"Depot state key {did!r} does not match depot_id "
                    f"{declared_id!r}",
                )
            position_values = sd.get("position")
            if not isinstance(position_values, (list, tuple)):
                raise ValueError(f"Depot {did} position must be a sequence")
            position = Position(*position_values)
            _validate_position(position, f"depot {did} position")
            inventory_state = _normalize_inventory_state(
                sd.get("inventory"),
                f"depot {did} inventory",
            )
            inv = SupplyInventory()
            inv.set_state(inventory_state)
            raw_depot_type = sd.get("depot_type")
            if (
                isinstance(raw_depot_type, bool)
                or not isinstance(raw_depot_type, int)
            ):
                raise ValueError(
                    f"Depot {did} depot_type must be an integer enum value",
                )
            depot_type = DepotType(raw_depot_type)
            side = sd.get("side")
            _validate_identifier(side, f"depot {did} side")
            capacity = sd.get("capacity_tons")
            throughput = sd.get("throughput_tons_per_hour")
            condition = sd.get("condition")
            _validate_positive_finite(capacity, f"depot {did} capacity")
            _validate_positive_finite(throughput, f"depot {did} throughput")
            _validate_unit_interval(condition, f"depot {did} condition")
            staged_depots[did] = Depot(
                depot_id=did,
                position=position,
                depot_type=depot_type,
                side=side,
                inventory=inv,
                capacity_tons=capacity,
                throughput_tons_per_hour=throughput,
                condition=condition,
            )

        staged_inventories: dict[str, SupplyInventory] = {}
        normalized_inventory_states: dict[str, dict[str, Any]] = {}
        for uid, inv_state in sorted(inventory_states.items()):
            _validate_identifier(uid, "unit inventory state key")
            normalized = _normalize_inventory_state(
                inv_state,
                f"unit {uid} inventory",
            )
            inv = SupplyInventory()
            inv.set_state(normalized)
            staged_inventories[uid] = inv
            normalized_inventory_states[uid] = normalized

        staged_maxima: dict[str, dict[int, dict[str, float]]] = {}
        for uid, maximum_state in sorted(maxima_states.items()):
            _validate_identifier(uid, "unit maximum state key")
            if uid not in staged_inventories:
                raise ValueError(
                    f"Maximum supply state references unknown unit inventory {uid}",
                )
            normalized = _normalize_supply_map(
                maximum_state,
                f"unit {uid} maximum supplies",
                strictly_positive=True,
            )
            _validate_inventory_within_maximum(
                normalized_inventory_states[uid],
                normalized,
                uid,
            )
            staged_maxima[uid] = normalized

        spoilage_accumulator = state.get("spoilage_accumulator", 0.0)
        _validate_nonnegative_finite(
            spoilage_accumulator,
            "stockpile spoilage accumulator",
        )
        staged_config = self._config
        if "config" in state:
            try:
                staged_config = StockpileConfig.model_validate(state["config"])
            except Exception as exc:
                raise ValueError("Invalid stockpile configuration state") from exc
            _validate_stockpile_config(staged_config)

        self._depots = staged_depots
        self._unit_inventories = staged_inventories
        self._unit_max_supplies = staged_maxima
        self._spoilage_accumulator = spoilage_accumulator
        self._config = staged_config


def _validate_identifier(value: object, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")


def _validate_finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be a finite number")
    return number


def _validate_positive_finite(value: object, label: str) -> float:
    number = _validate_finite(value, label)
    if number <= 0.0:
        raise ValueError(f"{label} must be positive")
    return number


def _validate_nonnegative_finite(value: object, label: str) -> float:
    number = _validate_finite(value, label)
    if number < 0.0:
        raise ValueError(f"{label} must be non-negative")
    return number


def _validate_unit_interval(value: object, label: str) -> float:
    number = _validate_finite(value, label)
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"{label} must be between 0 and 1")
    return number


def _validate_position(position: Position, label: str) -> None:
    if not isinstance(position, Position):
        raise ValueError(f"{label} must be a Position")
    for coordinate in position:
        _validate_finite(coordinate, label)


def _normalize_supply_class(value: object, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a SupplyClass integer")
    try:
        supply_class = int(value)
        SupplyClass(supply_class)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} is invalid: {value!r}") from exc
    if str(value).strip() != str(supply_class) and not isinstance(
        value,
        (int, enum.IntEnum),
    ):
        raise ValueError(f"{label} is invalid: {value!r}")
    return supply_class


def _normalize_supply_map(
    supplies: object,
    label: str,
    *,
    strictly_positive: bool,
) -> dict[int, dict[str, float]]:
    if not isinstance(supplies, dict):
        raise ValueError(f"{label} must be a mapping")
    normalized: dict[int, dict[str, float]] = {}
    for raw_class, raw_items in supplies.items():
        supply_class = _normalize_supply_class(raw_class, f"{label} supply class")
        if supply_class in normalized:
            raise ValueError(f"{label} contains duplicate supply class {supply_class}")
        if not isinstance(raw_items, dict):
            raise ValueError(f"{label} class {supply_class} must be a mapping")
        items: dict[str, float] = {}
        for item_id, raw_quantity in raw_items.items():
            _validate_identifier(item_id, f"{label} item ID")
            if item_id in items:
                raise ValueError(f"{label} contains duplicate item {item_id}")
            quantity = (
                _validate_positive_finite(raw_quantity, f"{label} {item_id}")
                if strictly_positive
                else _validate_nonnegative_finite(raw_quantity, f"{label} {item_id}")
            )
            items[item_id] = quantity
        normalized[supply_class] = {
            item_id: items[item_id]
            for item_id in sorted(items)
        }
    return {
        supply_class: normalized[supply_class]
        for supply_class in sorted(normalized)
    }


def _normalize_inventory_state(state: object, label: str) -> dict[str, Any]:
    if not isinstance(state, dict) or not isinstance(state.get("items"), dict):
        raise ValueError(f"{label} must contain an items mapping")
    normalized = _normalize_supply_map(
        state["items"],
        label,
        strictly_positive=False,
    )
    return {
        "items": {
            str(supply_class): items
            for supply_class, items in normalized.items()
        },
    }


def _validate_inventory_within_maximum(
    inventory_state: dict[str, Any],
    maxima: dict[int, dict[str, float]],
    unit_id: str,
) -> None:
    inventory = _normalize_supply_map(
        inventory_state["items"],
        f"unit {unit_id} inventory",
        strictly_positive=False,
    )
    for supply_class, items in inventory.items():
        for item_id, quantity in items.items():
            maximum = maxima.get(supply_class, {}).get(item_id)
            if maximum is None:
                if quantity > 0.0:
                    raise ValueError(
                        f"Unit {unit_id} inventory item "
                        f"{supply_class}/{item_id} has no maximum",
                    )
                continue
            if quantity > maximum:
                raise ValueError(
                    f"Unit {unit_id} inventory item {supply_class}/{item_id} "
                    f"quantity {quantity} exceeds maximum {maximum}",
                )


def _validate_stockpile_config(config: StockpileConfig) -> None:
    _validate_positive_finite(
        config.spoilage_check_interval_hours,
        "spoilage check interval",
    )
    _validate_unit_interval(
        config.capture_efficiency,
        "capture efficiency",
    )
    _validate_unit_interval(
        config.shortage_threshold,
        "shortage threshold",
    )
