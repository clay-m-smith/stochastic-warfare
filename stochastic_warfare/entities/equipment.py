"""Equipment modeling — items, degradation, breakdowns, environment stress."""

from __future__ import annotations

import enum
from dataclasses import dataclass

import numpy as np

from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


class EquipmentCategory(enum.IntEnum):
    """Functional category for equipment items."""

    WEAPON = 0
    SENSOR = 1
    PROPULSION = 2
    PROTECTION = 3
    COMMUNICATION = 4
    NAVIGATION = 5
    UTILITY = 6
    POWER = 7


@dataclass
class EquipmentItem:
    """A single piece of equipment attached to a unit."""

    equipment_id: str
    name: str
    category: EquipmentCategory
    condition: float = 1.0  # 0.0 (destroyed) – 1.0 (pristine)
    reliability: float = 0.95  # base MTBF-derived probability
    operational: bool = True
    weight_kg: float = 0.0
    temperature_range: tuple[float, float] = (-40.0, 50.0)  # rated celsius

    def get_state(self) -> dict:
        return {
            "equipment_id": self.equipment_id,
            "name": self.name,
            "category": int(self.category),
            "condition": self.condition,
            "reliability": self.reliability,
            "operational": self.operational,
            "weight_kg": self.weight_kg,
            "temperature_range": list(self.temperature_range),
        }

    def set_state(self, state: dict) -> None:
        self.equipment_id = state["equipment_id"]
        self.name = state["name"]
        self.category = EquipmentCategory(state["category"])
        self.condition = state["condition"]
        self.reliability = state["reliability"]
        self.operational = state["operational"]
        self.weight_kg = state["weight_kg"]
        self.temperature_range = tuple(state["temperature_range"])


class EquipmentManager:
    """Utility for degradation, breakdowns, and environment stress."""

    @staticmethod
    def apply_degradation(
        item: EquipmentItem,
        operating_hours: float,
        intensity: float = 1.0,
    ) -> None:
        """Reduce *item* condition based on usage.

        Parameters
        ----------
        operating_hours:
            Hours of operation in this tick.
        intensity:
            Multiplier for degradation rate (combat use > idle).
        """
        # Base rate: lose ~1% condition per 10 hours at intensity 1.0
        rate = 0.001 * intensity
        item.condition = max(0.0, item.condition - rate * operating_hours)
        if item.condition <= 0.0:
            item.operational = False

    @staticmethod
    def check_breakdown(item: EquipmentItem, rng: np.random.Generator) -> bool:
        """Stochastic breakdown check.

        Returns True if the item breaks down this check.
        P(fail) ~ (1 - condition) * (1 - reliability).
        """
        if not item.operational:
            return False
        p_fail = (1.0 - item.condition) * (1.0 - item.reliability)
        if rng.random() < p_fail:
            item.operational = False
            return True
        return False

    @staticmethod
    def environment_stress(item: EquipmentItem, temperature: float) -> float:
        """Return extra degradation factor for operation outside rated range.

        Returns 0.0 when within range, increasing linearly outside.
        """
        t_min, t_max = item.temperature_range
        if temperature < t_min:
            return (t_min - temperature) / 20.0  # per 20°C below: +1x
        if temperature > t_max:
            return (temperature - t_max) / 20.0
        return 0.0

    @staticmethod
    def operational_readiness(equipment: list[EquipmentItem]) -> float:
        """Return fraction of equipment items that are operational."""
        if not equipment:
            return 1.0
        return sum(1 for e in equipment if e.operational) / len(equipment)
