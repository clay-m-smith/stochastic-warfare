"""Escalation module events.

Phase 24a event types published by escalation subsystem engines.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from stochastic_warfare.core.events import Event
from stochastic_warfare.core.types import ModuleId, Position


@dataclass(frozen=True)
class EscalationLevelChangeEvent(Event):
    """Escalation level changed for a side."""

    timestamp: datetime
    source: ModuleId
    side: str
    old_level: int
    new_level: int
    desperation_index: float


@dataclass(frozen=True)
class WarCrimeRecordedEvent(Event):
    """A war crime was recorded."""

    timestamp: datetime
    source: ModuleId
    responsible_side: str
    crime_type: str
    severity: float
    position: Position


@dataclass(frozen=True)
class PoliticalPressureChangeEvent(Event):
    """Political pressure changed for a side."""

    timestamp: datetime
    source: ModuleId
    side: str
    old_international: float
    new_international: float
    old_domestic: float
    new_domestic: float


@dataclass(frozen=True)
class CoalitionFractureEvent(Event):
    """A coalition member departed due to political pressure."""

    timestamp: datetime
    source: ModuleId
    side: str
    departing_ally: str
    units_removed: int


@dataclass(frozen=True)
class ProhibitedWeaponEmployedEvent(Event):
    """A prohibited weapon was employed."""

    timestamp: datetime
    source: ModuleId
    responsible_side: str
    weapon_id: str
    ammo_id: str
    position: Position


@dataclass(frozen=True)
class CivilianAtrocityEvent(Event):
    """A civilian atrocity occurred."""

    timestamp: datetime
    source: ModuleId
    responsible_side: str
    atrocity_type: str
    civilian_casualties: int
    position: Position


@dataclass(frozen=True)
class PrisonerMistreatmentEvent(Event):
    """Prisoners were mistreated."""

    timestamp: datetime
    source: ModuleId
    responsible_side: str
    treatment_level: int
    prisoner_count: int


@dataclass(frozen=True)
class ScorchedEarthEvent(Event):
    """Scorched earth tactics employed."""

    timestamp: datetime
    source: ModuleId
    responsible_side: str
    infrastructure_destroyed: int
    position: Position
