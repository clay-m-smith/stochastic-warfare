"""Tactical-level orders — squad through battalion.

Planning time scales with echelon:
- Squad: ~1 minute
- Platoon: ~15 minutes
- Company: ~1 hour
- Battalion: ~2 hours
"""

from __future__ import annotations

import enum
from datetime import datetime

from stochastic_warfare.c2.orders.types import (
    MissionType,
    OrderPriority,
    OrderType,
    TacticalOrder,
)
from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.organization.echelons import EchelonLevel


class TacticalMission(enum.IntEnum):
    """Tactical missions specific to squad-battalion echelons."""

    ASSAULT = 0
    AMBUSH = 1
    RAID = 2
    RECONNAISSANCE_PATROL = 3
    SECURITY_PATROL = 4
    OCCUPY_BATTLE_POSITION = 5
    ESTABLISH_CHECKPOINT = 6
    CLEAR_BUILDING = 7
    ESTABLISH_OP = 8
    REACT_TO_CONTACT = 9
    BREAK_CONTACT = 10
    CONSOLIDATE = 11


# Base planning times by echelon (seconds)
_PLANNING_TIMES: dict[EchelonLevel, float] = {
    EchelonLevel.SQUAD: 60.0,        # 1 min
    EchelonLevel.SECTION: 300.0,     # 5 min
    EchelonLevel.PLATOON: 900.0,     # 15 min
    EchelonLevel.COMPANY: 3600.0,    # 1 hr
    EchelonLevel.BATTALION: 7200.0,  # 2 hr
}


def get_planning_time(echelon: EchelonLevel) -> float:
    """Return base planning time for a tactical echelon (seconds)."""
    return _PLANNING_TIMES.get(echelon, 3600.0)


def create_tactical_order(
    order_id: str,
    issuer_id: str,
    recipient_id: str,
    timestamp: datetime,
    mission_type: MissionType | TacticalMission,
    echelon: EchelonLevel,
    objective_position: Position | None = None,
    order_type: OrderType = OrderType.OPORD,
    priority: OrderPriority = OrderPriority.PRIORITY,
    parent_order_id: str | None = None,
    formation: str = "",
    route_waypoints: tuple[Position, ...] = (),
) -> TacticalOrder:
    """Create a tactical-level order."""
    return TacticalOrder(
        order_id=order_id,
        issuer_id=issuer_id,
        recipient_id=recipient_id,
        timestamp=timestamp,
        order_type=order_type,
        echelon_level=int(echelon),
        priority=priority,
        mission_type=int(mission_type),
        objective_position=objective_position,
        parent_order_id=parent_order_id,
        formation=formation,
        route_waypoints=route_waypoints,
    )
