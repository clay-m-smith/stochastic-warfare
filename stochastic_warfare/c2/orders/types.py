"""Order type hierarchy and execution tracking.

All orders are frozen dataclasses — immutable once created. Execution state
is tracked separately via ``OrderExecutionRecord`` (mutable), which references
the order by ID. This follows the same pattern as ``ContactRecord`` wrapping
immutable detection results.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime

from stochastic_warfare.core.types import Position


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class OrderType(enum.IntEnum):
    """High-level order category."""

    OPORD = 0  # Operations Order — full 5-paragraph
    FRAGO = 1  # Fragmentary Order — amendment to existing OPORD
    WARNO = 2  # Warning Order — advance notice


class OrderPriority(enum.IntEnum):
    """Message precedence affecting propagation speed."""

    ROUTINE = 0
    PRIORITY = 1
    IMMEDIATE = 2
    FLASH = 3


class OrderStatus(enum.IntEnum):
    """Lifecycle state of an order."""

    DRAFT = 0
    ISSUED = 1
    IN_TRANSIT = 2
    RECEIVED = 3
    ACKNOWLEDGED = 4
    EXECUTING = 5
    COMPLETED = 6
    FAILED = 7
    SUPERSEDED = 8


class MissionType(enum.IntEnum):
    """Standard ground tactical missions."""

    ATTACK = 0
    DEFEND = 1
    DELAY = 2
    WITHDRAW = 3
    SCREEN = 4
    GUARD = 5
    COVER = 6
    MOVEMENT_TO_CONTACT = 7
    RECON = 8
    PASSAGE_OF_LINES = 9
    RELIEF_IN_PLACE = 10
    SUPPORT_BY_FIRE = 11
    SUPPRESS = 12
    BREACH = 13
    SEIZE = 14
    SECURE = 15
    PATROL = 16
    AMBUSH = 17


# ---------------------------------------------------------------------------
# Base order (frozen)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Order:
    """Base order — immutable once created.

    All echelon-specific and domain-specific orders inherit from this.
    """

    order_id: str
    issuer_id: str
    recipient_id: str
    timestamp: datetime
    order_type: OrderType
    echelon_level: int  # EchelonLevel value
    priority: OrderPriority
    mission_type: int  # MissionType or domain-specific enum value
    objective_position: Position | None = None
    parent_order_id: str | None = None  # For FRAGOs referencing an OPORD
    phase_line: str = ""  # Named control measure
    execution_time: datetime | None = None  # H-hour / NLT


# ---------------------------------------------------------------------------
# Echelon-specific orders
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IndividualOrder(Order):
    """Individual / fire team level order."""

    immediate: bool = True  # Expect near-instant execution


@dataclass(frozen=True)
class TacticalOrder(Order):
    """Squad through battalion level order."""

    formation: str = ""  # Requested formation
    route_waypoints: tuple[Position, ...] = ()


@dataclass(frozen=True)
class OperationalOrder(Order):
    """Brigade through corps level order."""

    main_effort_id: str = ""  # Unit designated as main effort
    supporting_effort_ids: tuple[str, ...] = ()
    reserve_id: str = ""


@dataclass(frozen=True)
class StrategicOrder(Order):
    """Theater / campaign level order."""

    campaign_phase: str = ""
    political_constraints: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Domain-specific orders
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NavalOrder(Order):
    """Naval-specific order."""

    formation_id: str = ""  # Target naval formation
    naval_mission_type: str = ""  # NavalMissionType name
    engagement_envelope: float = 0.0  # Max engagement range, meters


@dataclass(frozen=True)
class AirOrder(Order):
    """Air-specific order."""

    air_mission_type: str = ""  # AirMissionType name
    altitude_min_m: float = 0.0
    altitude_max_m: float = 15000.0
    time_on_station_s: float = 0.0
    callsign: str = ""


# ---------------------------------------------------------------------------
# Execution tracking (mutable)
# ---------------------------------------------------------------------------


@dataclass
class OrderExecutionRecord:
    """Mutable record tracking order execution lifecycle.

    One record per order-recipient pair. References the immutable
    ``Order`` by ``order_id``.
    """

    order_id: str
    recipient_id: str
    status: OrderStatus = OrderStatus.DRAFT
    issued_time: float = 0.0  # sim seconds
    received_time: float | None = None
    acknowledged_time: float | None = None
    execution_start_time: float | None = None
    completion_time: float | None = None
    deviation_level: float = 0.0  # 0.0 = perfect compliance
    was_degraded: bool = False
    was_misinterpreted: bool = False
    misinterpretation_type: str = ""
    superseded_by: str | None = None

    def get_state(self) -> dict:
        """Serialize for checkpoint/restore."""
        return {
            "order_id": self.order_id,
            "recipient_id": self.recipient_id,
            "status": int(self.status),
            "issued_time": self.issued_time,
            "received_time": self.received_time,
            "acknowledged_time": self.acknowledged_time,
            "execution_start_time": self.execution_start_time,
            "completion_time": self.completion_time,
            "deviation_level": self.deviation_level,
            "was_degraded": self.was_degraded,
            "was_misinterpreted": self.was_misinterpreted,
            "misinterpretation_type": self.misinterpretation_type,
            "superseded_by": self.superseded_by,
        }

    def set_state(self, state: dict) -> None:
        """Restore from checkpoint."""
        self.order_id = state["order_id"]
        self.recipient_id = state["recipient_id"]
        self.status = OrderStatus(state["status"])
        self.issued_time = state["issued_time"]
        self.received_time = state["received_time"]
        self.acknowledged_time = state["acknowledged_time"]
        self.execution_start_time = state["execution_start_time"]
        self.completion_time = state["completion_time"]
        self.deviation_level = state["deviation_level"]
        self.was_degraded = state["was_degraded"]
        self.was_misinterpreted = state["was_misinterpreted"]
        self.misinterpretation_type = state["misinterpretation_type"]
        self.superseded_by = state["superseded_by"]
