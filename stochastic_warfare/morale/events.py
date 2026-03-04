"""Morale-layer events published on the EventBus.

Combat modules do not import morale — morale subscribes to combat events
and publishes its own events for downstream consumers (C2, simulation).
"""

from __future__ import annotations

from dataclasses import dataclass

from stochastic_warfare.core.events import Event


@dataclass(frozen=True)
class MoraleStateChangeEvent(Event):
    """Published when a unit's morale state transitions."""

    unit_id: str
    old_state: int  # MoraleState value
    new_state: int


@dataclass(frozen=True)
class RoutEvent(Event):
    """Published when a unit begins routing."""

    unit_id: str
    direction: float  # radians, direction of flight


@dataclass(frozen=True)
class RallyEvent(Event):
    """Published when a routing unit rallies."""

    unit_id: str
    rallied_by: str  # entity_id of the rallying leader, or "" for self-rally


@dataclass(frozen=True)
class SurrenderEvent(Event):
    """Published when a unit surrenders."""

    unit_id: str
    capturing_side: str  # Side value


@dataclass(frozen=True)
class StressChangeEvent(Event):
    """Published when a unit's stress level changes significantly."""

    unit_id: str
    stress_delta: float
    cause: str  # "combat", "casualties", "sleep_deprivation", "environment"


@dataclass(frozen=True)
class CohesionChangeEvent(Event):
    """Published when unit cohesion changes significantly."""

    unit_id: str
    cohesion_delta: float
    cause: str  # "casualties", "leader_lost", "isolation", "reinforcement"


@dataclass(frozen=True)
class PsyopAppliedEvent(Event):
    """Published when a PSYOP operation is applied against a target."""

    target_unit_id: str
    message_type: str  # "surrender", "desertion", "fear", "deception"
    delivery_method: str  # "leaflet", "broadcast", "social_media", "loudspeaker"
    morale_degradation: float
    effective: bool
