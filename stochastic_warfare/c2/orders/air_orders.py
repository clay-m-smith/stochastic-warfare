"""Air-specific orders — ATO structure, ACO measures, CAS request flow.

Scope limited to data structures and check functions.
No ATO planning cycle (Phase 8).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime

from stochastic_warfare.c2.orders.types import (
    AirOrder,
    OrderPriority,
    OrderType,
)
from stochastic_warfare.core.types import Position


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class AirMissionType(enum.IntEnum):
    """Air mission types."""

    CAS = 0        # Close Air Support
    CAP = 1        # Combat Air Patrol
    STRIKE = 2     # Interdiction / strike
    SEAD = 3       # Suppression of Enemy Air Defense
    DCA = 4        # Defensive Counter-Air
    OCA = 5        # Offensive Counter-Air
    AI = 6         # Air Interdiction
    RECON = 7      # Reconnaissance
    EW = 8         # Electronic Warfare
    TRANSPORT = 9  # Airlift
    REFUELING = 10 # Air refueling
    SAR = 11       # Search and Rescue


class AirspaceControlType(enum.IntEnum):
    """Airspace control measure types."""

    RESTRICTED_OPERATING_ZONE = 0
    HIGH_DENSITY_AIRSPACE_CONTROL_ZONE = 1
    MISSILE_ENGAGEMENT_ZONE = 2
    FIGHTER_ENGAGEMENT_ZONE = 3
    WEAPONS_FREE_ZONE = 4
    AIR_CORRIDOR = 5
    TRANSIT_ROUTE = 6
    LOW_LEVEL_TRANSIT_ROUTE = 7
    MINIMUM_RISK_ROUTE = 8


# ---------------------------------------------------------------------------
# ATO structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AtoEntry:
    """One mission entry in the Air Tasking Order."""

    mission_id: str
    mission_type: AirMissionType
    callsign: str
    unit_id: str  # Assigned aircraft/flight
    target_position: Position | None
    altitude_min_m: float
    altitude_max_m: float
    time_on_station_s: float
    start_time: datetime
    end_time: datetime


@dataclass(frozen=True)
class AirspaceControlMeasure:
    """A single airspace control measure in the ACO."""

    measure_id: str
    measure_type: AirspaceControlType
    center: Position
    radius_m: float
    altitude_min_m: float
    altitude_max_m: float
    start_time: datetime
    end_time: datetime
    controlling_unit: str


@dataclass(frozen=True)
class CasRequest:
    """Close Air Support request from ground unit."""

    request_id: str
    requesting_unit_id: str
    target_position: Position
    target_description: str
    priority: OrderPriority
    timestamp: datetime
    friendlies_position: Position | None = None
    minimum_safe_distance_m: float = 500.0


# ---------------------------------------------------------------------------
# ATO / ACO creation helpers
# ---------------------------------------------------------------------------


def create_ato_entry(
    mission_id: str,
    mission_type: AirMissionType,
    callsign: str,
    unit_id: str,
    start_time: datetime,
    end_time: datetime,
    target_position: Position | None = None,
    altitude_min_m: float = 0.0,
    altitude_max_m: float = 15000.0,
    time_on_station_s: float = 0.0,
) -> AtoEntry:
    """Create an ATO entry."""
    return AtoEntry(
        mission_id=mission_id,
        mission_type=mission_type,
        callsign=callsign,
        unit_id=unit_id,
        target_position=target_position,
        altitude_min_m=altitude_min_m,
        altitude_max_m=altitude_max_m,
        time_on_station_s=time_on_station_s,
        start_time=start_time,
        end_time=end_time,
    )


def create_cas_request(
    request_id: str,
    requesting_unit_id: str,
    target_position: Position,
    target_description: str,
    timestamp: datetime,
    priority: OrderPriority = OrderPriority.IMMEDIATE,
    friendlies_position: Position | None = None,
    minimum_safe_distance_m: float = 500.0,
) -> CasRequest:
    """Create a CAS request."""
    return CasRequest(
        request_id=request_id,
        requesting_unit_id=requesting_unit_id,
        target_position=target_position,
        target_description=target_description,
        priority=priority,
        timestamp=timestamp,
        friendlies_position=friendlies_position,
        minimum_safe_distance_m=minimum_safe_distance_m,
    )


def create_air_order(
    order_id: str,
    issuer_id: str,
    recipient_id: str,
    timestamp: datetime,
    air_mission: AirMissionType,
    objective_position: Position | None = None,
    order_type: OrderType = OrderType.OPORD,
    priority: OrderPriority = OrderPriority.PRIORITY,
    parent_order_id: str | None = None,
    altitude_min_m: float = 0.0,
    altitude_max_m: float = 15000.0,
    time_on_station_s: float = 0.0,
    callsign: str = "",
    echelon_level: int = 9,
) -> AirOrder:
    """Create an air-specific order."""
    return AirOrder(
        order_id=order_id,
        issuer_id=issuer_id,
        recipient_id=recipient_id,
        timestamp=timestamp,
        order_type=order_type,
        echelon_level=echelon_level,
        priority=priority,
        mission_type=int(air_mission),
        objective_position=objective_position,
        parent_order_id=parent_order_id,
        air_mission_type=air_mission.name,
        altitude_min_m=altitude_min_m,
        altitude_max_m=altitude_max_m,
        time_on_station_s=time_on_station_s,
        callsign=callsign,
    )


# ---------------------------------------------------------------------------
# Airspace deconfliction check
# ---------------------------------------------------------------------------


def check_airspace_deconfliction(
    position: Position,
    altitude_m: float,
    timestamp: datetime,
    measures: list[AirspaceControlMeasure],
) -> list[AirspaceControlMeasure]:
    """Return list of ACO measures violated by the given position/altitude/time.

    An empty list means the airspace is clear.
    """
    import math

    violations = []
    for m in measures:
        # Check time window
        if timestamp < m.start_time or timestamp > m.end_time:
            continue
        # Check altitude
        if altitude_m < m.altitude_min_m or altitude_m > m.altitude_max_m:
            continue
        # Check horizontal distance
        dx = position.easting - m.center.easting
        dy = position.northing - m.center.northing
        dist = math.sqrt(dx * dx + dy * dy)
        if dist <= m.radius_m:
            violations.append(m)

    return violations
