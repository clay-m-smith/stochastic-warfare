"""Support unit types — logistics, HQ, signal, medical, engineers."""

from __future__ import annotations

import enum
from dataclasses import dataclass

from stochastic_warfare.core.types import Domain
from stochastic_warfare.entities.base import Unit


class SupportUnitType(enum.IntEnum):
    """Combat support / combat service support classification."""

    LOGISTICS_TRUCK = 0
    FUEL_TRUCK = 1
    AMMO_TRUCK = 2
    HQ = 3
    SIGNAL = 4
    ENGINEER = 5
    MEDICAL = 6
    MAINTENANCE = 7
    MP = 8
    CIVIL_AFFAIRS = 9


@dataclass
class SupportUnit(Unit):
    """A support-domain unit with cargo capacity."""

    support_type: SupportUnitType = SupportUnitType.LOGISTICS_TRUCK
    cargo_capacity_tons: float = 0.0
    cargo_current_tons: float = 0.0

    def __post_init__(self) -> None:
        self.domain = Domain.GROUND

    @property
    def cargo_fraction(self) -> float:
        """Return fraction of cargo capacity in use (0.0–1.0)."""
        if self.cargo_capacity_tons <= 0.0:
            return 0.0
        return min(1.0, self.cargo_current_tons / self.cargo_capacity_tons)

    def get_state(self) -> dict:
        state = super().get_state()
        state.update(
            {
                "support_type": int(self.support_type),
                "cargo_capacity_tons": self.cargo_capacity_tons,
                "cargo_current_tons": self.cargo_current_tons,
            }
        )
        return state

    def set_state(self, state: dict) -> None:
        super().set_state(state)
        self.support_type = SupportUnitType(state["support_type"])
        self.cargo_capacity_tons = state["cargo_capacity_tons"]
        self.cargo_current_tons = state["cargo_current_tons"]
