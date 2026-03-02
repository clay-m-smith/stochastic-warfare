"""Movement-layer events published on the EventBus."""

from __future__ import annotations

from dataclasses import dataclass

from stochastic_warfare.core.events import Event
from stochastic_warfare.core.types import Position


@dataclass(frozen=True)
class UnitMovedEvent(Event):
    """Published when a unit completes a movement tick."""

    unit_id: str
    from_pos: Position
    to_pos: Position
    distance: float
    duration: float


@dataclass(frozen=True)
class FormationChangedEvent(Event):
    """Published when a unit changes formation."""

    unit_id: str
    new_formation: int


@dataclass(frozen=True)
class FatigueChangedEvent(Event):
    """Published when a unit's fatigue level changes significantly."""

    unit_id: str
    fatigue_level: float
