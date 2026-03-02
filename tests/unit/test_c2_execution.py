"""Tests for c2/orders/execution.py — order execution tracking lifecycle."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from stochastic_warfare.core.events import Event, EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.c2.command import CommandEngine
from stochastic_warfare.c2.communications import (
    CommEquipmentDefinition,
    CommEquipmentLoader,
    CommunicationsEngine,
)
from stochastic_warfare.c2.events import OrderCompletedEvent
from stochastic_warfare.c2.orders.execution import (
    ExecutionConfig,
    OrderExecutionEngine,
)
from stochastic_warfare.c2.orders.propagation import (
    OrderPropagationEngine,
    PropagationConfig,
)
from stochastic_warfare.c2.orders.types import (
    MissionType,
    Order,
    OrderPriority,
    OrderStatus,
    OrderType,
)
from stochastic_warfare.entities.organization.echelons import EchelonLevel
from stochastic_warfare.entities.organization.hierarchy import HierarchyTree
from stochastic_warfare.entities.organization.task_org import TaskOrgManager

_TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
_POS_A = Position(0.0, 0.0, 0.0)
_POS_B = Position(5000.0, 0.0, 0.0)


def _make_vhf() -> CommEquipmentDefinition:
    return CommEquipmentDefinition(
        comm_id="test_vhf", comm_type="RADIO_VHF",
        display_name="Test VHF", max_range_m=50000.0,
        bandwidth_bps=16000.0, base_latency_s=0.5,
        base_reliability=0.99, intercept_risk=0.3,
        jam_resistance=0.5, requires_los=True,
    )


def _make_exec_engine(
    seed: int = 42,
    exec_config: ExecutionConfig | None = None,
) -> tuple[OrderExecutionEngine, EventBus]:
    hierarchy = HierarchyTree()
    hierarchy.add_unit("bde1", EchelonLevel.BRIGADE)
    hierarchy.add_unit("bn1", EchelonLevel.BATTALION, "bde1")
    hierarchy.add_unit("co1", EchelonLevel.COMPANY, "bn1")
    task_org = TaskOrgManager(hierarchy)
    bus = EventBus()
    rng_mgr = RNGManager(seed)

    cmd = CommandEngine(hierarchy, task_org, {}, bus, rng_mgr.get_stream(ModuleId.C2))
    for uid in ["bde1", "bn1", "co1"]:
        cmd.register_unit(uid, f"cdr_{uid}")

    vhf = _make_vhf()
    loader = CommEquipmentLoader()
    loader._definitions[vhf.comm_id] = vhf
    comms = CommunicationsEngine(bus, rng_mgr.get_stream(ModuleId.ENVIRONMENT), loader)
    for uid in ["bde1", "bn1", "co1"]:
        comms.register_unit(uid, ["test_vhf"])

    prop = OrderPropagationEngine(
        comms, cmd, bus, rng_mgr.get_stream(ModuleId.MOVEMENT),
    )
    exec_eng = OrderExecutionEngine(
        prop, bus, rng_mgr.get_stream(ModuleId.ENTITIES), exec_config,
    )
    return exec_eng, bus


def _make_order(order_id: str = "ord_001") -> Order:
    return Order(
        order_id=order_id, issuer_id="bde1", recipient_id="bn1",
        timestamp=_TS, order_type=OrderType.OPORD,
        echelon_level=int(EchelonLevel.BATTALION),
        priority=OrderPriority.ROUTINE,
        mission_type=int(MissionType.ATTACK),
    )


class TestIssueOrder:
    """Order issuance."""

    def test_issue_creates_record(self) -> None:
        eng, bus = _make_exec_engine()
        order = _make_order()
        result = eng.issue_order(order, _POS_A, _POS_B, _TS)
        assert result.success is True
        record = eng.get_record("ord_001")
        assert record.order_id == "ord_001"
        assert record.status == OrderStatus.IN_TRANSIT

    def test_issue_failed_creates_failed_record(self) -> None:
        hierarchy = HierarchyTree()
        hierarchy.add_unit("bde1", EchelonLevel.BRIGADE)
        hierarchy.add_unit("bn1", EchelonLevel.BATTALION, "bde1")
        task_org = TaskOrgManager(hierarchy)
        bus = EventBus()
        rng_mgr = RNGManager(42)
        cmd = CommandEngine(hierarchy, task_org, {}, bus, rng_mgr.get_stream(ModuleId.C2))
        cmd.register_unit("bde1", "cdr_bde1")
        cmd.register_unit("bn1", "cdr_bn1")
        comms = CommunicationsEngine(bus, rng_mgr.get_stream(ModuleId.ENVIRONMENT))
        comms.register_unit("bde1", [])
        comms.register_unit("bn1", [])
        prop = OrderPropagationEngine(comms, cmd, bus, rng_mgr.get_stream(ModuleId.MOVEMENT))
        eng = OrderExecutionEngine(prop, bus, rng_mgr.get_stream(ModuleId.ENTITIES))

        order = _make_order()
        result = eng.issue_order(order, _POS_A, _POS_B, _TS)
        assert result.success is False
        assert eng.get_record("ord_001").status == OrderStatus.FAILED


class TestAcknowledgment:
    """Order acknowledgment."""

    def test_acknowledge_order(self) -> None:
        eng, bus = _make_exec_engine()
        eng.issue_order(_make_order(), _POS_A, _POS_B, _TS)
        # Advance time to receive (must exceed transit delay but not expiry)
        eng.update(50000)
        eng.acknowledge_order("ord_001", "bn1")
        assert eng.get_record("ord_001").status == OrderStatus.ACKNOWLEDGED

    def test_wrong_unit_cannot_acknowledge(self) -> None:
        eng, bus = _make_exec_engine()
        eng.issue_order(_make_order(), _POS_A, _POS_B, _TS)
        with pytest.raises(ValueError, match="not recipient"):
            eng.acknowledge_order("ord_001", "co1")


class TestExecutionLifecycle:
    """Full lifecycle: ISSUED → IN_TRANSIT → RECEIVED → ... → COMPLETED."""

    def test_transit_to_received(self) -> None:
        eng, bus = _make_exec_engine()
        eng.issue_order(_make_order(), _POS_A, _POS_B, _TS)
        record = eng.get_record("ord_001")
        assert record.status == OrderStatus.IN_TRANSIT
        # Advance past received_time (must not exceed expiry)
        eng.update(50000)
        assert record.status == OrderStatus.RECEIVED

    def test_full_lifecycle(self) -> None:
        eng, bus = _make_exec_engine()
        eng.issue_order(_make_order(), _POS_A, _POS_B, _TS)
        eng.update(50000)  # IN_TRANSIT → RECEIVED
        eng.acknowledge_order("ord_001", "bn1")
        eng.report_execution_status("ord_001", "bn1", OrderStatus.EXECUTING)
        eng.report_execution_status("ord_001", "bn1", OrderStatus.COMPLETED, deviation=0.1)
        record = eng.get_record("ord_001")
        assert record.status == OrderStatus.COMPLETED
        assert record.deviation_level == pytest.approx(0.1)

    def test_completed_publishes_event(self) -> None:
        eng, bus = _make_exec_engine()
        events: list[OrderCompletedEvent] = []
        bus.subscribe(OrderCompletedEvent, events.append)
        eng.issue_order(_make_order(), _POS_A, _POS_B, _TS)
        eng.update(200000)
        eng.report_execution_status("ord_001", "bn1", OrderStatus.COMPLETED)
        assert len(events) == 1
        assert events[0].success is True


class TestPendingAndActive:
    """Query orders by unit."""

    def test_pending_orders(self) -> None:
        eng, bus = _make_exec_engine()
        eng.issue_order(_make_order("o1"), _POS_A, _POS_B, _TS)
        pending = eng.get_pending_orders("bn1")
        assert len(pending) == 1

    def test_active_orders_after_receipt(self) -> None:
        eng, bus = _make_exec_engine()
        eng.issue_order(_make_order("o1"), _POS_A, _POS_B, _TS)
        eng.update(50000)
        active = eng.get_active_orders("bn1")
        assert len(active) == 1

    def test_no_orders_for_wrong_unit(self) -> None:
        eng, bus = _make_exec_engine()
        eng.issue_order(_make_order(), _POS_A, _POS_B, _TS)
        assert eng.get_pending_orders("co1") == []


class TestSupersession:
    """FRAGO supersedes OPORD."""

    def test_supersede_marks_old_order(self) -> None:
        eng, bus = _make_exec_engine()
        old = _make_order("ord_001")
        eng.issue_order(old, _POS_A, _POS_B, _TS)

        new = Order(
            order_id="frago_001", issuer_id="bde1", recipient_id="bn1",
            timestamp=_TS, order_type=OrderType.FRAGO,
            echelon_level=int(EchelonLevel.BATTALION),
            priority=OrderPriority.IMMEDIATE,
            mission_type=int(MissionType.WITHDRAW),
            parent_order_id="ord_001",
        )
        eng.supersede_order("ord_001", new, _POS_A, _POS_B, _TS)

        old_record = eng.get_record("ord_001")
        assert old_record.status == OrderStatus.SUPERSEDED
        assert old_record.superseded_by == "frago_001"

        new_record = eng.get_record("frago_001")
        assert new_record.status == OrderStatus.IN_TRANSIT


class TestExpiry:
    """Orders expire after configured time."""

    def test_order_expires(self) -> None:
        # Use expiry slightly longer than transit time so order receives then expires
        config = ExecutionConfig(order_expiry_s=60000.0)
        eng, bus = _make_exec_engine(exec_config=config)
        eng.issue_order(_make_order(), _POS_A, _POS_B, _TS)
        # Advance past transit to receive, then past expiry
        eng.update(50000)  # Transit completes, order received
        assert eng.get_record("ord_001").status == OrderStatus.RECEIVED
        eng.update(20000)  # Total 70000 > 60000 expiry
        record = eng.get_record("ord_001")
        assert record.status == OrderStatus.SUPERSEDED


class TestStateProtocol:
    """Checkpoint / restore."""

    def test_state_round_trip(self) -> None:
        eng, bus = _make_exec_engine()
        eng.issue_order(_make_order(), _POS_A, _POS_B, _TS)
        state = eng.get_state()
        eng2, bus2 = _make_exec_engine()
        eng2.set_state(state)
        assert eng2.get_state() == state
