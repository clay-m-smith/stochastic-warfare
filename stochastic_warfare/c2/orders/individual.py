"""Individual / fire team level orders.

Near-instant propagation (~0.5s). Used for direct verbal commands:
"Move to that building", "Engage that target", "Take cover".
"""

from __future__ import annotations

import enum
from datetime import datetime

from stochastic_warfare.c2.orders.types import (
    IndividualOrder,
    OrderPriority,
    OrderType,
)
from stochastic_warfare.entities.organization.echelons import EchelonLevel
from stochastic_warfare.core.types import Position


class IndividualAction(enum.IntEnum):
    """Actions available at individual / fire team level."""

    MOVE_TO = 0
    ENGAGE = 1
    TAKE_COVER = 2
    CEASE_FIRE = 3
    FOLLOW_ME = 4
    HOLD_POSITION = 5
    MOUNT = 6
    DISMOUNT = 7
    TREAT_CASUALTY = 8
    MARK_TARGET = 9


# Planning time is essentially zero — verbal order
INDIVIDUAL_PLANNING_TIME_S: float = 0.5


def get_planning_time(echelon: EchelonLevel) -> float:
    """Return planning time for individual-level order (~0.5s)."""
    return INDIVIDUAL_PLANNING_TIME_S


def create_individual_order(
    order_id: str,
    issuer_id: str,
    recipient_id: str,
    timestamp: datetime,
    action: IndividualAction,
    objective_position: Position | None = None,
    order_type: OrderType = OrderType.FRAGO,
    priority: OrderPriority = OrderPriority.FLASH,
    parent_order_id: str | None = None,
) -> IndividualOrder:
    """Create an individual-level order."""
    return IndividualOrder(
        order_id=order_id,
        issuer_id=issuer_id,
        recipient_id=recipient_id,
        timestamp=timestamp,
        order_type=order_type,
        echelon_level=int(EchelonLevel.INDIVIDUAL),
        priority=priority,
        mission_type=int(action),
        objective_position=objective_position,
        parent_order_id=parent_order_id,
        immediate=True,
    )
