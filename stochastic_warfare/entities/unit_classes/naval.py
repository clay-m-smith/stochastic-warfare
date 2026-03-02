"""Naval unit types — surface combatants, submarines, amphibious, auxiliary."""

from __future__ import annotations

import enum
from dataclasses import dataclass

from stochastic_warfare.core.types import Domain
from stochastic_warfare.entities.base import Unit


class NavalUnitType(enum.IntEnum):
    """Naval platform classification."""

    # Surface combatants
    CARRIER = 0
    CRUISER = 1
    DESTROYER = 2
    FRIGATE = 3
    CORVETTE = 4
    PATROL = 5
    # Submarines
    SSN = 6
    SSBN = 7
    SSK = 8
    # Amphibious
    LHD = 9
    LPD = 10
    LST = 11
    LANDING_CRAFT = 12
    # Mine warfare
    MINESWEEPER = 13
    MINELAYER = 14
    MINE_HUNTER = 15
    # Auxiliary
    OILER = 16
    SUPPLY_SHIP = 17
    HOSPITAL_SHIP = 18
    SALVAGE = 19


@dataclass
class NavalUnit(Unit):
    """A naval unit with hull integrity, draft, fuel, and submarine fields."""

    naval_type: NavalUnitType = NavalUnitType.DESTROYER
    hull_integrity: float = 1.0  # 0.0–1.0
    draft: float = 0.0  # meters
    displacement: float = 0.0  # metric tons
    fuel_capacity: float = 0.0  # metric tons
    fuel_remaining: float = 1.0  # 0.0–1.0 fraction
    depth: float = 0.0  # submarines: meters below surface
    max_depth: float = 0.0  # maximum operating depth
    noise_signature_base: float = 0.0  # dB reference
    is_submarine: bool = False

    def __post_init__(self) -> None:
        if self.naval_type in (NavalUnitType.SSN, NavalUnitType.SSBN,
                               NavalUnitType.SSK):
            self.is_submarine = True
            self.domain = Domain.SUBMARINE
        elif self.naval_type in (NavalUnitType.LHD, NavalUnitType.LPD,
                                 NavalUnitType.LST, NavalUnitType.LANDING_CRAFT):
            self.domain = Domain.AMPHIBIOUS
        else:
            self.domain = Domain.NAVAL

    def get_state(self) -> dict:
        state = super().get_state()
        state.update(
            {
                "naval_type": int(self.naval_type),
                "hull_integrity": self.hull_integrity,
                "draft": self.draft,
                "displacement": self.displacement,
                "fuel_capacity": self.fuel_capacity,
                "fuel_remaining": self.fuel_remaining,
                "depth": self.depth,
                "max_depth": self.max_depth,
                "noise_signature_base": self.noise_signature_base,
                "is_submarine": self.is_submarine,
            }
        )
        return state

    def set_state(self, state: dict) -> None:
        super().set_state(state)
        self.naval_type = NavalUnitType(state["naval_type"])
        self.hull_integrity = state["hull_integrity"]
        self.draft = state["draft"]
        self.displacement = state["displacement"]
        self.fuel_capacity = state["fuel_capacity"]
        self.fuel_remaining = state["fuel_remaining"]
        self.depth = state["depth"]
        self.max_depth = state["max_depth"]
        self.noise_signature_base = state["noise_signature_base"]
        self.is_submarine = state["is_submarine"]
