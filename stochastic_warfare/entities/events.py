"""Entity-layer events published on the EventBus."""

from __future__ import annotations

from dataclasses import dataclass

from stochastic_warfare.core.events import Event
from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.personnel import InjuryState


@dataclass(frozen=True)
class UnitCreatedEvent(Event):
    """Published when a new unit is instantiated."""

    unit_id: str
    unit_type: str
    position: Position
    side: str


@dataclass(frozen=True)
class UnitDestroyedEvent(Event):
    """Published when a unit is destroyed or removed from play."""

    unit_id: str
    cause: str
    side: str = ""


@dataclass(frozen=True)
class PersonnelCasualtyEvent(Event):
    """Published when a crew member suffers a casualty."""

    unit_id: str
    member_id: str
    severity: InjuryState


@dataclass(frozen=True)
class EquipmentBreakdownEvent(Event):
    """Published when an equipment item breaks down."""

    unit_id: str
    equipment_id: str
