"""Operational-level orders — brigade through corps.

Planning time scales with echelon:
- Brigade: ~12 hours
- Division: ~24 hours
- Corps: ~48 hours
"""

from __future__ import annotations

import enum
from datetime import datetime

from stochastic_warfare.c2.orders.types import (
    MissionType,
    OperationalOrder,
    OrderPriority,
    OrderType,
)
from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.organization.echelons import EchelonLevel


class OperationalMission(enum.IntEnum):
    """Operational-level missions."""

    DECISIVE_OPERATION = 0
    SHAPING_OPERATION = 1
    SUSTAINING_OPERATION = 2
    DEEP_STRIKE = 3
    COUNTERATTACK = 4
    EXPLOITATION = 5
    PURSUIT = 6
    RETROGRADE = 7
    AREA_DEFENSE = 8
    MOBILE_DEFENSE = 9
    RIVER_CROSSING = 10
    AIRBORNE_OPERATION = 11


# Base planning times by echelon (seconds)
_PLANNING_TIMES: dict[EchelonLevel, float] = {
    EchelonLevel.BRIGADE: 43200.0,   # 12 hr
    EchelonLevel.DIVISION: 86400.0,  # 24 hr
    EchelonLevel.CORPS: 172800.0,    # 48 hr
}


def get_planning_time(echelon: EchelonLevel) -> float:
    """Return base planning time for an operational echelon (seconds)."""
    return _PLANNING_TIMES.get(echelon, 86400.0)


def create_operational_order(
    order_id: str,
    issuer_id: str,
    recipient_id: str,
    timestamp: datetime,
    mission_type: MissionType | OperationalMission,
    echelon: EchelonLevel,
    objective_position: Position | None = None,
    order_type: OrderType = OrderType.OPORD,
    priority: OrderPriority = OrderPriority.PRIORITY,
    parent_order_id: str | None = None,
    main_effort_id: str = "",
    supporting_effort_ids: tuple[str, ...] = (),
    reserve_id: str = "",
) -> OperationalOrder:
    """Create an operational-level order."""
    return OperationalOrder(
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
        main_effort_id=main_effort_id,
        supporting_effort_ids=supporting_effort_ids,
        reserve_id=reserve_id,
    )
