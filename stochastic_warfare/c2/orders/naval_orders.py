"""Naval-specific orders — formation movement, ASW, strike, escort, blockade."""

from __future__ import annotations

import enum
from datetime import datetime

from stochastic_warfare.c2.orders.types import (
    NavalOrder,
    OrderPriority,
    OrderType,
)
from stochastic_warfare.core.types import Position


class NavalMissionType(enum.IntEnum):
    """Naval mission types."""

    FORMATION_MOVEMENT = 0
    ASW_PROSECUTION = 1
    ANTI_SURFACE_WARFARE = 2
    ANTI_AIR_WARFARE = 3
    STRIKE = 4
    CONVOY_ESCORT = 5
    BLOCKADE = 6
    MINE_WARFARE = 7
    AMPHIBIOUS_SUPPORT = 8
    SHORE_BOMBARDMENT = 9
    SEARCH_AND_RESCUE = 10
    UNDERWAY_REPLENISHMENT = 11


def create_naval_order(
    order_id: str,
    issuer_id: str,
    recipient_id: str,
    timestamp: datetime,
    naval_mission: NavalMissionType,
    objective_position: Position | None = None,
    order_type: OrderType = OrderType.OPORD,
    priority: OrderPriority = OrderPriority.PRIORITY,
    parent_order_id: str | None = None,
    formation_id: str = "",
    engagement_envelope: float = 0.0,
    echelon_level: int = 8,
) -> NavalOrder:
    """Create a naval-specific order."""
    return NavalOrder(
        order_id=order_id,
        issuer_id=issuer_id,
        recipient_id=recipient_id,
        timestamp=timestamp,
        order_type=order_type,
        echelon_level=echelon_level,
        priority=priority,
        mission_type=int(naval_mission),
        objective_position=objective_position,
        parent_order_id=parent_order_id,
        formation_id=formation_id,
        naval_mission_type=naval_mission.name,
        engagement_envelope=engagement_envelope,
    )
