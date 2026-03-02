"""Supply classification, item definitions, and inventory tracking.

NATO supply classes form the backbone of military logistics.  Each class
has distinct consumption patterns, transport requirements, and criticality
weightings for combat power assessment.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

from pydantic import BaseModel

from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SupplyClass(enum.IntEnum):
    """NATO supply classification."""

    CLASS_I = 1  # food & water
    CLASS_II = 2  # clothing & equipment
    CLASS_III = 3  # fuel (ground)
    CLASS_IIIA = 30  # aviation fuel
    CLASS_IV = 4  # construction materials
    CLASS_V = 5  # ammunition
    CLASS_VIII = 8  # medical supplies
    CLASS_IX = 9  # spare parts
    CLASS_X = 10  # miscellaneous


class FuelType(enum.IntEnum):
    """Fuel variants tracked by the logistics engine."""

    DIESEL = 0
    JP8 = 1
    AVGAS = 2
    BUNKER_FUEL = 3
    NUCLEAR = 4


# Mapping from YAML string → SupplyClass
_SUPPLY_CLASS_MAP: dict[str, SupplyClass] = {sc.name: sc for sc in SupplyClass}


# ---------------------------------------------------------------------------
# YAML-loaded supply item definition
# ---------------------------------------------------------------------------


class SupplyItemDefinition(BaseModel):
    """Physical properties of a supply item, loaded from YAML."""

    item_id: str
    supply_class: str  # resolved via property
    display_name: str
    weight_per_unit_kg: float
    volume_per_unit_m3: float
    perishable: bool = False
    shelf_life_hours: float | None = None

    @property
    def supply_class_enum(self) -> SupplyClass:
        """Resolve string to ``SupplyClass``."""
        return _SUPPLY_CLASS_MAP[self.supply_class]


class SupplyItemLoader:
    """Load and cache ``SupplyItemDefinition`` from YAML files."""

    def __init__(self, data_dir: Path | None = None) -> None:
        if data_dir is None:
            data_dir = (
                Path(__file__).resolve().parents[2] / "data" / "logistics" / "supply_items"
            )
        self._data_dir = data_dir
        self._definitions: dict[str, SupplyItemDefinition] = {}

    def load_definition(self, path: Path) -> SupplyItemDefinition:
        """Load a single YAML file and cache it."""
        import yaml

        with open(path) as f:
            data = yaml.safe_load(f)
        if isinstance(data, list):
            for entry in data:
                defn = SupplyItemDefinition.model_validate(entry)
                self._definitions[defn.item_id] = defn
            return self._definitions[data[-1]["item_id"]]
        defn = SupplyItemDefinition.model_validate(data)
        self._definitions[defn.item_id] = defn
        return defn

    def load_all(self) -> None:
        """Load every ``*.yaml`` file under the data directory."""
        for path in sorted(self._data_dir.rglob("*.yaml")):
            self.load_definition(path)
        logger.info("Loaded %d supply item definitions", len(self._definitions))

    def get_definition(self, item_id: str) -> SupplyItemDefinition:
        """Return a cached definition; raises ``KeyError`` if not found."""
        return self._definitions[item_id]

    def available_items(self) -> list[str]:
        """Return sorted list of loaded item IDs."""
        return sorted(self._definitions.keys())


# ---------------------------------------------------------------------------
# Runtime inventory
# ---------------------------------------------------------------------------


@dataclass
class SupplyInventory:
    """Mutable per-unit or per-depot inventory, keyed by supply class and item ID."""

    _items: dict[int, dict[str, float]] = field(default_factory=dict)

    def add(self, supply_class: int, item_id: str, quantity: float) -> None:
        """Add *quantity* of *item_id* under *supply_class*."""
        bucket = self._items.setdefault(supply_class, {})
        bucket[item_id] = bucket.get(item_id, 0.0) + quantity

    def consume(self, supply_class: int, item_id: str, quantity: float) -> float:
        """Consume up to *quantity*; return the amount actually consumed."""
        bucket = self._items.get(supply_class)
        if bucket is None or item_id not in bucket:
            return 0.0
        available = bucket[item_id]
        consumed = min(available, quantity)
        bucket[item_id] = available - consumed
        return consumed

    def available(self, supply_class: int, item_id: str) -> float:
        """Return the quantity on hand for *item_id*."""
        bucket = self._items.get(supply_class)
        if bucket is None:
            return 0.0
        return bucket.get(item_id, 0.0)

    def total_by_class(self, supply_class: int) -> float:
        """Return total quantity across all items in *supply_class*."""
        bucket = self._items.get(supply_class)
        if bucket is None:
            return 0.0
        return sum(bucket.values())

    def total_weight(self, loader: SupplyItemLoader | None = None) -> float:
        """Return total weight in kg.  Without a loader, each unit = 1 kg."""
        total = 0.0
        for _cls, bucket in self._items.items():
            for item_id, qty in bucket.items():
                if loader is not None:
                    try:
                        defn = loader.get_definition(item_id)
                        total += qty * defn.weight_per_unit_kg
                    except KeyError:
                        total += qty
                else:
                    total += qty
        return total

    def fraction_of(self, supply_class: int, item_id: str, max_qty: float) -> float:
        """Return the fraction of *max_qty* currently available (0-1)."""
        if max_qty <= 0.0:
            return 0.0
        return min(self.available(supply_class, item_id) / max_qty, 1.0)

    def classes_present(self) -> list[int]:
        """Return sorted list of supply classes that have any stock."""
        return sorted(
            cls for cls, bucket in self._items.items() if any(v > 0 for v in bucket.values())
        )

    def get_state(self) -> dict:
        """Serialize for checkpoint."""
        return {
            "items": {
                str(cls): dict(bucket) for cls, bucket in self._items.items()
            }
        }

    def set_state(self, state: dict) -> None:
        """Restore from checkpoint."""
        self._items.clear()
        for cls_str, bucket in state["items"].items():
            self._items[int(cls_str)] = dict(bucket)


# ---------------------------------------------------------------------------
# Supply requirement descriptor
# ---------------------------------------------------------------------------


class SupplyRequirement(NamedTuple):
    """Describes a unit's need for a particular supply item."""

    supply_class: int
    item_id: str
    rate_per_hour: float
    minimum_reserve: float
