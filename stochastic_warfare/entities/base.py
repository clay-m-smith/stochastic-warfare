"""Base entity and unit classes for the simulation.

Entity is the minimal base (entity_id + position).  Unit extends Entity
with personnel, equipment, domain, status and other fields needed by
all force elements.  Domain-specific subclasses live in
``entities.unit_classes``.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

from stochastic_warfare.core.types import Domain, Position, Side
from stochastic_warfare.entities.equipment import EquipmentItem
from stochastic_warfare.entities.personnel import CrewMember


class UnitStatus(enum.IntEnum):
    """Operational status of a unit."""

    ACTIVE = 0
    DISABLED = 1
    DESTROYED = 2
    SURRENDERED = 3
    ROUTING = 4


@dataclass
class Entity:
    """Base class for all simulation entities (units, platforms, etc.)."""

    entity_id: str
    position: Position

    def get_state(self) -> dict:
        """Serialize entity state for checkpointing."""
        return {
            "entity_id": self.entity_id,
            "position": tuple(self.position),
        }

    def set_state(self, state: dict) -> None:
        """Restore entity state from a checkpoint dict."""
        self.entity_id = state["entity_id"]
        self.position = Position(*state["position"])


@dataclass
class Unit(Entity):
    """A force element with personnel, equipment, and operational state.

    All fields after ``position`` have defaults so that ``Entity`` (with
    only ``entity_id`` and ``position``) remains backward-compatible.
    """

    name: str = ""
    unit_type: str = ""
    side: str = Side.BLUE
    domain: Domain = Domain.GROUND
    status: UnitStatus = UnitStatus.ACTIVE
    heading: float = 0.0  # radians, 0 = north
    speed: float = 0.0  # m/s current
    max_speed: float = 0.0  # m/s design maximum
    personnel: list[CrewMember] = field(default_factory=list)
    equipment: list[EquipmentItem] = field(default_factory=list)

    def get_state(self) -> dict:
        state = super().get_state()
        state.update(
            {
                "name": self.name,
                "unit_type": self.unit_type,
                "side": self.side,
                "domain": int(self.domain),
                "status": int(self.status),
                "heading": self.heading,
                "speed": self.speed,
                "max_speed": self.max_speed,
                "personnel": [m.get_state() for m in self.personnel],
                "equipment": [e.get_state() for e in self.equipment],
            }
        )
        return state

    def set_state(self, state: dict) -> None:
        super().set_state(state)
        self.name = state["name"]
        self.unit_type = state["unit_type"]
        self.side = state["side"]
        self.domain = Domain(state["domain"])
        self.status = UnitStatus(state["status"])
        self.heading = state["heading"]
        self.speed = state["speed"]
        self.max_speed = state["max_speed"]

        self.personnel = []
        for ms in state["personnel"]:
            m = CrewMember(member_id="", role=0, skill=0, experience=0.0)
            m.set_state(ms)
            self.personnel.append(m)

        self.equipment = []
        for es in state["equipment"]:
            e = EquipmentItem(equipment_id="", name="", category=0)
            e.set_state(es)
            self.equipment.append(e)
