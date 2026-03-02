"""Logistics event types published on the EventBus.

All events use ``source=ModuleId.LOGISTICS`` and ``frozen=True``.
"""

from __future__ import annotations

from dataclasses import dataclass

from stochastic_warfare.core.events import Event
from stochastic_warfare.core.types import Position


# ---------------------------------------------------------------------------
# Supply events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SupplyDeliveredEvent(Event):
    """Published when supplies are delivered to a unit or depot."""

    recipient_id: str
    supply_class: int
    quantity: float
    transport_mode: int


@dataclass(frozen=True)
class SupplyShortageEvent(Event):
    """Published when a unit's supply level drops below reserve threshold."""

    unit_id: str
    supply_class: int
    current_fraction: float
    hours_remaining: float


@dataclass(frozen=True)
class SupplyDepletedEvent(Event):
    """Published when a unit completely exhausts a supply class."""

    unit_id: str
    supply_class: int


# ---------------------------------------------------------------------------
# Transport events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConvoyDispatchedEvent(Event):
    """Published when a transport mission departs."""

    mission_id: str
    origin_id: str
    destination_id: str
    transport_mode: int
    cargo_tons: float


@dataclass(frozen=True)
class ConvoyArrivedEvent(Event):
    """Published when a transport mission reaches its destination."""

    mission_id: str
    destination_id: str
    cargo_tons: float


@dataclass(frozen=True)
class ConvoyDestroyedEvent(Event):
    """Published when a transport mission is destroyed en route."""

    mission_id: str
    position: Position
    cargo_lost_tons: float
    cause: str


# ---------------------------------------------------------------------------
# Maintenance events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MaintenanceStartedEvent(Event):
    """Published when equipment enters maintenance."""

    unit_id: str
    equipment_id: str
    estimated_hours: float


@dataclass(frozen=True)
class MaintenanceCompletedEvent(Event):
    """Published when maintenance finishes and equipment is restored."""

    unit_id: str
    equipment_id: str
    condition_restored: float


@dataclass(frozen=True)
class EquipmentBreakdownEvent(Event):
    """Published when equipment suffers a stochastic breakdown."""

    unit_id: str
    equipment_id: str


# ---------------------------------------------------------------------------
# Engineering events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConstructionStartedEvent(Event):
    """Published when an engineering project begins."""

    project_id: str
    task_type: int
    position: Position
    assigned_unit_id: str


@dataclass(frozen=True)
class ConstructionCompletedEvent(Event):
    """Published when an engineering project finishes."""

    project_id: str
    task_type: int
    target_feature_id: str


@dataclass(frozen=True)
class InfrastructureRepairedEvent(Event):
    """Published when infrastructure is restored to service."""

    feature_id: str
    condition_restored: float


@dataclass(frozen=True)
class ObstacleEmplacedEvent(Event):
    """Published when an obstacle is placed on the battlefield."""

    obstacle_id: str
    obstacle_type: str
    position: Position


@dataclass(frozen=True)
class ObstacleClearedEvent(Event):
    """Published when an obstacle is breached or removed."""

    obstacle_id: str


# ---------------------------------------------------------------------------
# Medical events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CasualtyEvacuatedEvent(Event):
    """Published when a casualty is moved between treatment echelons."""

    unit_id: str
    member_id: str
    from_facility_type: int
    to_facility_type: int


@dataclass(frozen=True)
class CasualtyTreatedEvent(Event):
    """Published when a casualty completes treatment."""

    unit_id: str
    member_id: str
    outcome: str


@dataclass(frozen=True)
class ReturnToDutyEvent(Event):
    """Published when a treated casualty returns to their unit."""

    unit_id: str
    member_id: str


# ---------------------------------------------------------------------------
# POW events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PrisonerCapturedEvent(Event):
    """Published when enemy personnel are taken prisoner."""

    capturing_unit_id: str
    prisoner_count: int
    side_captured: str


@dataclass(frozen=True)
class PrisonerTransferredEvent(Event):
    """Published when prisoners are moved to a rear facility."""

    group_id: str
    destination_id: str


# ---------------------------------------------------------------------------
# Naval logistics events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UnrepStartedEvent(Event):
    """Published when underway replenishment begins."""

    supply_ship_id: str
    receiving_unit_ids: tuple[str, ...]


@dataclass(frozen=True)
class UnrepCompletedEvent(Event):
    """Published when underway replenishment finishes."""

    supply_ship_id: str
    receiving_unit_ids: tuple[str, ...]
    fuel_transferred_tons: float
    ammo_transferred_tons: float


@dataclass(frozen=True)
class PortLoadingEvent(Event):
    """Published when port loading or unloading operations occur."""

    port_id: str
    ship_ids: tuple[str, ...]
    op_type: int
    tons_transferred: float


# ---------------------------------------------------------------------------
# Disruption events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RouteInterdictedEvent(Event):
    """Published when a supply route is struck by interdiction."""

    route_id: str
    position: Position
    severity: float


@dataclass(frozen=True)
class RouteDegradedEvent(Event):
    """Published when a route's condition worsens."""

    route_id: str
    old_condition: float
    new_condition: float
    cause: str


@dataclass(frozen=True)
class BlockadeEstablishedEvent(Event):
    """Published when a naval blockade is declared."""

    blockade_id: str
    sea_zone_ids: tuple[str, ...]
    enforcing_side: str
