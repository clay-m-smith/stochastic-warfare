"""Air-specific orders — ATO structure, ACO measures, CAS request flow.

Scope limited to data structures and check functions.
No ATO planning cycle (Phase 8).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel

from stochastic_warfare.c2.orders.types import (
    AirOrder,
    OrderPriority,
    OrderType,
)
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position

logger = get_logger(__name__)


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


# ---------------------------------------------------------------------------
# 12a-9: ATO Planning Engine
# ---------------------------------------------------------------------------


@dataclass
class AircraftAvailability:
    """Tracks an aircraft's ATO availability."""

    unit_id: str
    mission_capable: bool = True
    sorties_today: int = 0
    max_sorties_per_day: int = 2
    turnaround_time_s: float = 7200.0  # 2 hours
    last_sortie_end_time_s: float = -1e9


class ATOPlanningConfig(BaseModel):
    """Configuration for ATO planning engine."""

    cas_reserve_fraction: float = 0.2
    """Fraction of available sorties reserved for CAS."""
    priority_order: list[str] = ["DCA", "CAP", "SEAD", "STRIKE", "CAS", "RECON"]
    """Mission priority for ATO allocation."""


class ATOPlanningEngine:
    """Generates Air Tasking Orders from requests and JIPTL allocations.

    Parameters
    ----------
    event_bus:
        EventBus for publishing ``ATOGeneratedEvent``.
    config:
        ATO planning configuration.
    """

    def __init__(
        self,
        event_bus: EventBus,
        config: ATOPlanningConfig | None = None,
    ) -> None:
        from stochastic_warfare.c2.events import ATOGeneratedEvent

        self._event_bus = event_bus
        self._config = config or ATOPlanningConfig()
        self._aircraft: dict[str, AircraftAvailability] = {}
        self._requests: list[dict[str, Any]] = []

    def register_aircraft(self, aircraft: AircraftAvailability) -> None:
        """Register an aircraft for ATO planning."""
        self._aircraft[aircraft.unit_id] = aircraft

    def submit_request(
        self,
        mission_type: str,
        target_position: Position | None = None,
        priority: int = 5,
        requesting_unit: str = "",
    ) -> None:
        """Submit a mission request for ATO consideration."""
        self._requests.append({
            "mission_type": mission_type,
            "target_position": target_position,
            "priority": priority,
            "requesting_unit": requesting_unit,
        })

    def get_available_sorties(self, current_time_s: float = 0.0) -> int:
        """Count available sorties based on aircraft readiness."""
        count = 0
        for ac in self._aircraft.values():
            if not ac.mission_capable:
                continue
            if ac.sorties_today >= ac.max_sorties_per_day:
                continue
            if current_time_s - ac.last_sortie_end_time_s < ac.turnaround_time_s:
                continue
            count += 1
        return count

    def generate_ato(
        self,
        jiptl_allocations: list[Any] | None = None,
        current_time_s: float = 0.0,
        ato_start_time: datetime | None = None,
        timestamp: datetime | None = None,
    ) -> list[AtoEntry]:
        """Generate ATO missions from requests and JIPTL allocations.

        Parameters
        ----------
        jiptl_allocations:
            Target allocations from JIPTL (12a-6). Each has target_id,
            shooter_id, score, range_m.
        current_time_s:
            Current sim time for aircraft availability checks.
        ato_start_time:
            Start time for ATO period.
        timestamp:
            Event timestamp.

        Returns list of AtoEntry missions.
        """
        from datetime import timezone
        from stochastic_warfare.c2.events import ATOGeneratedEvent

        ts = timestamp or datetime.now(tz=timezone.utc)
        start = ato_start_time or ts
        end = start + timedelta(hours=24)

        # Get available aircraft
        available = []
        for ac in self._aircraft.values():
            if not ac.mission_capable:
                continue
            if ac.sorties_today >= ac.max_sorties_per_day:
                continue
            if current_time_s - ac.last_sortie_end_time_s < ac.turnaround_time_s:
                continue
            available.append(ac)

        if not available:
            return []

        # Reserve CAS fraction
        total = len(available)
        cas_reserve = max(1, int(total * self._config.cas_reserve_fraction))
        strike_available = available[:-cas_reserve] if cas_reserve < total else []
        cas_pool = available[-cas_reserve:] if cas_reserve <= total else list(available)

        entries: list[AtoEntry] = []
        used_aircraft: set[str] = set()

        # Allocate by priority order
        sorted_requests = sorted(
            self._requests,
            key=lambda r: (
                self._config.priority_order.index(r["mission_type"])
                if r["mission_type"] in self._config.priority_order
                else 99,
                r["priority"],
            ),
        )

        for req in sorted_requests:
            mission_type_str = req["mission_type"]
            # Choose from CAS pool or strike pool
            if mission_type_str == "CAS":
                pool = [a for a in cas_pool if a.unit_id not in used_aircraft]
            else:
                pool = [a for a in strike_available if a.unit_id not in used_aircraft]
                if not pool:
                    pool = [a for a in cas_pool if a.unit_id not in used_aircraft]

            if not pool:
                continue

            ac = pool[0]
            used_aircraft.add(ac.unit_id)

            # Map string to AirMissionType
            try:
                mission_enum = AirMissionType[mission_type_str]
            except KeyError:
                mission_enum = AirMissionType.STRIKE

            entry = AtoEntry(
                mission_id=f"ato_{ac.unit_id}_{mission_type_str}",
                mission_type=mission_enum,
                callsign=ac.unit_id,
                unit_id=ac.unit_id,
                target_position=req.get("target_position"),
                altitude_min_m=0.0,
                altitude_max_m=15000.0,
                time_on_station_s=3600.0,
                start_time=start,
                end_time=end,
            )
            entries.append(entry)

        # JIPTL strike allocations
        if jiptl_allocations:
            for alloc in jiptl_allocations:
                target_id = alloc.target_id if hasattr(alloc, "target_id") else alloc.get("target_id", "")
                target_pos = alloc.position if hasattr(alloc, "position") else None

                pool = [a for a in available if a.unit_id not in used_aircraft]
                if not pool:
                    break

                ac = pool[0]
                used_aircraft.add(ac.unit_id)

                entry = AtoEntry(
                    mission_id=f"ato_jiptl_{target_id}",
                    mission_type=AirMissionType.STRIKE,
                    callsign=ac.unit_id,
                    unit_id=ac.unit_id,
                    target_position=target_pos,
                    altitude_min_m=0.0,
                    altitude_max_m=15000.0,
                    time_on_station_s=1800.0,
                    start_time=start,
                    end_time=end,
                )
                entries.append(entry)

        # Publish event
        self._event_bus.publish(ATOGeneratedEvent(
            timestamp=ts, source=ModuleId.C2,
            num_missions=len(entries),
            num_aircraft=len(used_aircraft),
            cas_reserve_fraction=self._config.cas_reserve_fraction,
        ))

        # Clear requests after generation
        self._requests.clear()

        return entries
