"""Order execution tracking engine.

Manages the lifecycle of orders from issuance through completion:
``DRAFT → ISSUED → IN_TRANSIT → RECEIVED → ACKNOWLEDGED → EXECUTING → COMPLETED``

Tracks deviation, supersession, and publishes completion events.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.c2.events import (
    OrderCompletedEvent,
)
from stochastic_warfare.c2.orders.propagation import (
    OrderPropagationEngine,
    PropagationResult,
)
from stochastic_warfare.c2.orders.types import (
    Order,
    OrderExecutionRecord,
    OrderStatus,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class ExecutionConfig:
    """Tuning parameters for execution tracking."""

    def __init__(
        self,
        deviation_alert_threshold: float = 0.5,
        order_expiry_s: float = 86400.0,  # 24 hours
    ) -> None:
        self.deviation_alert_threshold = deviation_alert_threshold
        self.order_expiry_s = order_expiry_s


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class OrderExecutionEngine:
    """Tracks order execution lifecycle.

    Parameters
    ----------
    propagation_engine : OrderPropagationEngine
        For propagating new orders through comms.
    event_bus : EventBus
        Publishes ``OrderCompletedEvent``.
    rng : numpy.random.Generator
        Deterministic PRNG.
    config : ExecutionConfig | None
        Tuning parameters.
    """

    def __init__(
        self,
        propagation_engine: OrderPropagationEngine,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: ExecutionConfig | None = None,
    ) -> None:
        self._propagation = propagation_engine
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or ExecutionConfig()
        self._records: dict[str, OrderExecutionRecord] = {}
        self._orders: dict[str, Order] = {}
        self._sim_time: float = 0.0

    def issue_order(
        self,
        order: Order,
        sender_pos: Position,
        recipient_pos: Position,
        timestamp: datetime,
    ) -> PropagationResult:
        """Issue an order: propagate it and create an execution record."""
        result = self._propagation.propagate_order(
            order, sender_pos, recipient_pos, timestamp,
        )

        record = OrderExecutionRecord(
            order_id=order.order_id,
            recipient_id=order.recipient_id,
            issued_time=self._sim_time,
        )

        if result.success:
            record.status = OrderStatus.IN_TRANSIT
            record.was_degraded = result.degraded
            record.was_misinterpreted = result.was_misinterpreted
            record.misinterpretation_type = result.misinterpretation_type
            record.received_time = self._sim_time + result.total_delay_s
        else:
            record.status = OrderStatus.FAILED

        self._records[order.order_id] = record
        self._orders[order.order_id] = order
        return result

    def acknowledge_order(self, order_id: str, unit_id: str) -> None:
        """Mark an order as acknowledged by the recipient."""
        record = self._records[order_id]
        if record.recipient_id != unit_id:
            raise ValueError(
                f"Unit {unit_id} is not recipient of order {order_id}"
            )
        if record.status in (OrderStatus.RECEIVED, OrderStatus.IN_TRANSIT):
            record.status = OrderStatus.ACKNOWLEDGED
            record.acknowledged_time = self._sim_time

    def report_execution_status(
        self,
        order_id: str,
        unit_id: str,
        status: OrderStatus,
        deviation: float = 0.0,
    ) -> None:
        """Report execution progress/completion."""
        record = self._records[order_id]
        if record.recipient_id != unit_id:
            raise ValueError(
                f"Unit {unit_id} is not recipient of order {order_id}"
            )
        record.status = status
        record.deviation_level = deviation

        if status == OrderStatus.EXECUTING and record.execution_start_time is None:
            record.execution_start_time = self._sim_time

        if status in (OrderStatus.COMPLETED, OrderStatus.FAILED):
            record.completion_time = self._sim_time
            order = self._orders.get(order_id)
            self._event_bus.publish(OrderCompletedEvent(
                timestamp=datetime.min,  # Placeholder — caller should provide
                source=ModuleId.C2,
                order_id=order_id,
                unit_id=unit_id,
                success=(status == OrderStatus.COMPLETED),
                deviation_level=deviation,
            ))

    def get_pending_orders(self, unit_id: str) -> list[OrderExecutionRecord]:
        """Return orders pending receipt for a unit."""
        return [
            r for r in self._records.values()
            if r.recipient_id == unit_id
            and r.status in (OrderStatus.ISSUED, OrderStatus.IN_TRANSIT)
        ]

    def get_active_orders(self, unit_id: str) -> list[OrderExecutionRecord]:
        """Return orders currently being executed by a unit."""
        return [
            r for r in self._records.values()
            if r.recipient_id == unit_id
            and r.status in (
                OrderStatus.RECEIVED, OrderStatus.ACKNOWLEDGED,
                OrderStatus.EXECUTING,
            )
        ]

    def get_record(self, order_id: str) -> OrderExecutionRecord:
        """Return the execution record for an order."""
        return self._records[order_id]

    def supersede_order(
        self,
        old_order_id: str,
        new_order: Order,
        sender_pos: Position,
        recipient_pos: Position,
        timestamp: datetime,
    ) -> PropagationResult:
        """Issue a new order that supersedes an existing one."""
        # Mark old order as superseded
        if old_order_id in self._records:
            old_record = self._records[old_order_id]
            old_record.status = OrderStatus.SUPERSEDED
            old_record.superseded_by = new_order.order_id

        # Issue the new order
        return self.issue_order(new_order, sender_pos, recipient_pos, timestamp)

    def update(self, dt_seconds: float) -> None:
        """Advance time — process in-transit orders and check expiry."""
        self._sim_time += dt_seconds

        for record in self._records.values():
            # Transit → Received
            if (
                record.status == OrderStatus.IN_TRANSIT
                and record.received_time is not None
                and self._sim_time >= record.received_time
            ):
                record.status = OrderStatus.RECEIVED

            # Check expiry
            if (
                record.status in (
                    OrderStatus.RECEIVED, OrderStatus.ACKNOWLEDGED,
                    OrderStatus.EXECUTING,
                )
                and self._sim_time - record.issued_time > self._config.order_expiry_s
            ):
                record.status = OrderStatus.SUPERSEDED
                logger.info("Order %s expired", record.order_id)

    # -- State protocol -----------------------------------------------------

    def get_state(self) -> dict:
        """Serialize for checkpoint/restore."""
        return {
            "sim_time": self._sim_time,
            "records": {
                oid: r.get_state()
                for oid, r in self._records.items()
            },
        }

    def set_state(self, state: dict) -> None:
        """Restore from checkpoint."""
        self._sim_time = state["sim_time"]
        self._records.clear()
        for oid, rd in state["records"].items():
            r = OrderExecutionRecord(order_id="", recipient_id="")
            r.set_state(rd)
            self._records[oid] = r
