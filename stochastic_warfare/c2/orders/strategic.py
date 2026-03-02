"""Strategic-level orders — theater / campaign.

Planning time: ~7 days for a full campaign order.
"""

from __future__ import annotations

import enum
from datetime import datetime

from stochastic_warfare.c2.orders.types import (
    MissionType,
    OrderPriority,
    OrderType,
    StrategicOrder,
)
from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.organization.echelons import EchelonLevel


class StrategicMission(enum.IntEnum):
    """Strategic-level missions."""

    MAJOR_OPERATION = 0
    CAMPAIGN = 1
    THEATER_OPENING = 2
    FORCE_PROJECTION = 3
    STRATEGIC_DEFENSE = 4
    PEACEKEEPING = 5
    HUMANITARIAN_ASSISTANCE = 6
    BLOCKADE = 7


# Planning time: ~7 days
STRATEGIC_PLANNING_TIME_S: float = 604800.0  # 7 * 24 * 3600


def get_planning_time(echelon: EchelonLevel) -> float:
    """Return base planning time for a strategic echelon (seconds)."""
    return STRATEGIC_PLANNING_TIME_S


def create_strategic_order(
    order_id: str,
    issuer_id: str,
    recipient_id: str,
    timestamp: datetime,
    mission_type: MissionType | StrategicMission,
    objective_position: Position | None = None,
    order_type: OrderType = OrderType.OPORD,
    priority: OrderPriority = OrderPriority.ROUTINE,
    parent_order_id: str | None = None,
    campaign_phase: str = "",
    political_constraints: tuple[str, ...] = (),
) -> StrategicOrder:
    """Create a strategic-level order."""
    return StrategicOrder(
        order_id=order_id,
        issuer_id=issuer_id,
        recipient_id=recipient_id,
        timestamp=timestamp,
        order_type=order_type,
        echelon_level=int(EchelonLevel.THEATER),
        priority=priority,
        mission_type=int(mission_type),
        objective_position=objective_position,
        parent_order_id=parent_order_id,
        campaign_phase=campaign_phase,
        political_constraints=political_constraints,
    )
