"""Ground unit types — armor, infantry, artillery, engineers."""

from __future__ import annotations

import enum
from dataclasses import dataclass

from stochastic_warfare.core.types import Domain
from stochastic_warfare.entities.base import Unit


class GroundUnitType(enum.IntEnum):
    """Ground-domain unit classification."""

    ARMOR = 0
    MECHANIZED_INFANTRY = 1
    LIGHT_INFANTRY = 2
    MOTORIZED = 3
    ARTILLERY_SP = 4
    ARTILLERY_TOWED = 5
    ROCKET_ARTILLERY = 6
    MORTAR = 7
    RECON = 8
    ENGINEER = 9
    CAVALRY = 10
    MILITIA = 11
    ARTILLERY = 12


class Posture(enum.IntEnum):
    """Defensive posture progression (time to establish increases)."""

    MOVING = 0
    HALTED = 1
    DEFENSIVE = 2
    DUG_IN = 3
    FORTIFIED = 4


@dataclass
class GroundUnit(Unit):
    """A ground-domain unit with armor, posture, and mount state."""

    ground_type: GroundUnitType = GroundUnitType.LIGHT_INFANTRY
    posture: Posture = Posture.MOVING
    mounted: bool = False
    dug_in_time: float = 0.0  # hours spent in current posture
    armor_front: float = 0.0  # mm RHA equivalent
    armor_side: float = 0.0
    armor_type: str = "RHA"
    fuel_remaining: float = 1.0  # 0.0–1.0 fraction; 1.0 = full tank

    def __post_init__(self) -> None:
        self.domain = Domain.GROUND

    def get_state(self) -> dict:
        state = super().get_state()
        state.update(
            {
                "ground_type": int(self.ground_type),
                "posture": int(self.posture),
                "mounted": self.mounted,
                "dug_in_time": self.dug_in_time,
                "armor_front": self.armor_front,
                "armor_side": self.armor_side,
                "armor_type": self.armor_type,
                "fuel_remaining": self.fuel_remaining,
            }
        )
        return state

    def set_state(self, state: dict) -> None:
        super().set_state(state)
        self.ground_type = GroundUnitType(state["ground_type"])
        self.posture = Posture(state["posture"])
        self.mounted = state["mounted"]
        self.dug_in_time = state["dug_in_time"]
        self.armor_front = state["armor_front"]
        self.armor_side = state["armor_side"]
        self.armor_type = state.get("armor_type", "RHA")
        self.fuel_remaining = state.get("fuel_remaining", 1.0)
