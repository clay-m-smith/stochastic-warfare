"""Tests for c2/orders/types.py — enums, base order hierarchy, execution record."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.c2.orders.types import (
    AirOrder,
    IndividualOrder,
    MissionType,
    NavalOrder,
    OperationalOrder,
    Order,
    OrderExecutionRecord,
    OrderPriority,
    OrderStatus,
    OrderType,
    StrategicOrder,
    TacticalOrder,
)

_TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
_POS = Position(1000.0, 2000.0, 0.0)


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestOrderEnums:
    """Order-related enums have correct values."""

    def test_order_type_values(self) -> None:
        assert OrderType.OPORD == 0
        assert OrderType.FRAGO == 1
        assert OrderType.WARNO == 2
        assert len(OrderType) == 3

    def test_order_priority_values(self) -> None:
        assert OrderPriority.ROUTINE == 0
        assert OrderPriority.FLASH == 3
        assert len(OrderPriority) == 4

    def test_order_priority_ordering(self) -> None:
        assert OrderPriority.ROUTINE < OrderPriority.PRIORITY
        assert OrderPriority.PRIORITY < OrderPriority.IMMEDIATE
        assert OrderPriority.IMMEDIATE < OrderPriority.FLASH

    def test_order_status_values(self) -> None:
        assert OrderStatus.DRAFT == 0
        assert OrderStatus.SUPERSEDED == 8
        assert len(OrderStatus) == 9

    def test_order_status_lifecycle_ordering(self) -> None:
        assert OrderStatus.ISSUED < OrderStatus.IN_TRANSIT
        assert OrderStatus.IN_TRANSIT < OrderStatus.RECEIVED
        assert OrderStatus.RECEIVED < OrderStatus.ACKNOWLEDGED
        assert OrderStatus.ACKNOWLEDGED < OrderStatus.EXECUTING
        assert OrderStatus.EXECUTING < OrderStatus.COMPLETED

    def test_mission_type_values(self) -> None:
        assert MissionType.ATTACK == 0
        assert MissionType.AMBUSH == 17
        assert len(MissionType) == 18

    @pytest.mark.parametrize("mt", list(MissionType))
    def test_all_mission_types_are_ints(self, mt: MissionType) -> None:
        assert isinstance(int(mt), int)


# ---------------------------------------------------------------------------
# Base Order
# ---------------------------------------------------------------------------


class TestBaseOrder:
    """Immutable base Order dataclass."""

    def test_create_order(self) -> None:
        o = Order(
            order_id="ord_001", issuer_id="bde1", recipient_id="bn1",
            timestamp=_TS, order_type=OrderType.OPORD,
            echelon_level=6, priority=OrderPriority.ROUTINE,
            mission_type=MissionType.ATTACK,
            objective_position=_POS,
        )
        assert o.order_id == "ord_001"
        assert o.issuer_id == "bde1"
        assert o.recipient_id == "bn1"
        assert o.order_type == OrderType.OPORD
        assert o.priority == OrderPriority.ROUTINE
        assert o.mission_type == MissionType.ATTACK
        assert o.objective_position == _POS
        assert o.parent_order_id is None

    def test_order_is_frozen(self) -> None:
        o = Order(
            order_id="ord_001", issuer_id="bde1", recipient_id="bn1",
            timestamp=_TS, order_type=OrderType.OPORD,
            echelon_level=6, priority=OrderPriority.ROUTINE,
            mission_type=MissionType.ATTACK,
        )
        with pytest.raises(AttributeError):
            o.order_id = "changed"  # type: ignore[misc]

    def test_frago_references_parent(self) -> None:
        o = Order(
            order_id="frago_001", issuer_id="bde1", recipient_id="bn1",
            timestamp=_TS, order_type=OrderType.FRAGO,
            echelon_level=6, priority=OrderPriority.IMMEDIATE,
            mission_type=MissionType.WITHDRAW,
            parent_order_id="ord_001",
        )
        assert o.parent_order_id == "ord_001"
        assert o.order_type == OrderType.FRAGO

    def test_order_defaults(self) -> None:
        o = Order(
            order_id="o1", issuer_id="a", recipient_id="b",
            timestamp=_TS, order_type=OrderType.OPORD,
            echelon_level=4, priority=OrderPriority.ROUTINE,
            mission_type=MissionType.DEFEND,
        )
        assert o.objective_position is None
        assert o.parent_order_id is None
        assert o.phase_line == ""
        assert o.execution_time is None

    def test_order_with_execution_time(self) -> None:
        h_hour = datetime(2024, 6, 16, 6, 0, 0, tzinfo=timezone.utc)
        o = Order(
            order_id="o1", issuer_id="a", recipient_id="b",
            timestamp=_TS, order_type=OrderType.OPORD,
            echelon_level=8, priority=OrderPriority.PRIORITY,
            mission_type=MissionType.ATTACK,
            execution_time=h_hour, phase_line="PL_ALPHA",
        )
        assert o.execution_time == h_hour
        assert o.phase_line == "PL_ALPHA"


# ---------------------------------------------------------------------------
# Echelon-specific orders
# ---------------------------------------------------------------------------


class TestEchelonOrders:
    """Echelon-specific order subclasses."""

    def test_individual_order(self) -> None:
        o = IndividualOrder(
            order_id="io1", issuer_id="sql1", recipient_id="sol1",
            timestamp=_TS, order_type=OrderType.FRAGO,
            echelon_level=0, priority=OrderPriority.FLASH,
            mission_type=MissionType.ATTACK,
            immediate=True,
        )
        assert o.immediate is True
        assert isinstance(o, Order)

    def test_individual_order_frozen(self) -> None:
        o = IndividualOrder(
            order_id="io1", issuer_id="sql1", recipient_id="sol1",
            timestamp=_TS, order_type=OrderType.FRAGO,
            echelon_level=0, priority=OrderPriority.FLASH,
            mission_type=MissionType.ATTACK,
        )
        with pytest.raises(AttributeError):
            o.immediate = False  # type: ignore[misc]

    def test_tactical_order(self) -> None:
        wps = (Position(100, 200), Position(300, 400))
        o = TacticalOrder(
            order_id="to1", issuer_id="co1", recipient_id="plt1",
            timestamp=_TS, order_type=OrderType.OPORD,
            echelon_level=5, priority=OrderPriority.PRIORITY,
            mission_type=MissionType.MOVEMENT_TO_CONTACT,
            formation="wedge", route_waypoints=wps,
        )
        assert o.formation == "wedge"
        assert len(o.route_waypoints) == 2
        assert isinstance(o, Order)

    def test_tactical_order_defaults(self) -> None:
        o = TacticalOrder(
            order_id="to1", issuer_id="co1", recipient_id="plt1",
            timestamp=_TS, order_type=OrderType.OPORD,
            echelon_level=5, priority=OrderPriority.ROUTINE,
            mission_type=MissionType.DEFEND,
        )
        assert o.formation == ""
        assert o.route_waypoints == ()

    def test_operational_order(self) -> None:
        o = OperationalOrder(
            order_id="oo1", issuer_id="div1", recipient_id="bde1",
            timestamp=_TS, order_type=OrderType.OPORD,
            echelon_level=9, priority=OrderPriority.PRIORITY,
            mission_type=MissionType.ATTACK,
            main_effort_id="bde2",
            supporting_effort_ids=("bde3", "bde4"),
            reserve_id="bde5",
        )
        assert o.main_effort_id == "bde2"
        assert len(o.supporting_effort_ids) == 2
        assert o.reserve_id == "bde5"
        assert isinstance(o, Order)

    def test_strategic_order(self) -> None:
        o = StrategicOrder(
            order_id="so1", issuer_id="theater1", recipient_id="army1",
            timestamp=_TS, order_type=OrderType.OPORD,
            echelon_level=13, priority=OrderPriority.ROUTINE,
            mission_type=MissionType.ATTACK,
            campaign_phase="Phase III",
            political_constraints=("no_cross_border", "minimize_collateral"),
        )
        assert o.campaign_phase == "Phase III"
        assert len(o.political_constraints) == 2
        assert isinstance(o, Order)


# ---------------------------------------------------------------------------
# Domain-specific orders
# ---------------------------------------------------------------------------


class TestDomainOrders:
    """Naval and air order subclasses."""

    def test_naval_order(self) -> None:
        o = NavalOrder(
            order_id="no1", issuer_id="tf1", recipient_id="tg1",
            timestamp=_TS, order_type=OrderType.OPORD,
            echelon_level=8, priority=OrderPriority.PRIORITY,
            mission_type=0,
            formation_id="tf_alpha",
            naval_mission_type="ASW_PROSECUTION",
            engagement_envelope=50000.0,
        )
        assert o.naval_mission_type == "ASW_PROSECUTION"
        assert o.engagement_envelope == 50000.0
        assert isinstance(o, Order)

    def test_naval_order_frozen(self) -> None:
        o = NavalOrder(
            order_id="no1", issuer_id="tf1", recipient_id="tg1",
            timestamp=_TS, order_type=OrderType.OPORD,
            echelon_level=8, priority=OrderPriority.ROUTINE,
            mission_type=0,
        )
        with pytest.raises(AttributeError):
            o.naval_mission_type = "STRIKE"  # type: ignore[misc]

    def test_air_order(self) -> None:
        o = AirOrder(
            order_id="ao1", issuer_id="jfacc", recipient_id="wing1",
            timestamp=_TS, order_type=OrderType.OPORD,
            echelon_level=9, priority=OrderPriority.IMMEDIATE,
            mission_type=0,
            air_mission_type="CAS",
            altitude_min_m=500.0, altitude_max_m=3000.0,
            time_on_station_s=1800.0, callsign="HAWG11",
        )
        assert o.air_mission_type == "CAS"
        assert o.callsign == "HAWG11"
        assert o.altitude_min_m == 500.0
        assert isinstance(o, Order)

    def test_air_order_defaults(self) -> None:
        o = AirOrder(
            order_id="ao1", issuer_id="jfacc", recipient_id="wing1",
            timestamp=_TS, order_type=OrderType.OPORD,
            echelon_level=9, priority=OrderPriority.ROUTINE,
            mission_type=0,
        )
        assert o.altitude_min_m == 0.0
        assert o.altitude_max_m == 15000.0
        assert o.time_on_station_s == 0.0
        assert o.callsign == ""


# ---------------------------------------------------------------------------
# OrderExecutionRecord
# ---------------------------------------------------------------------------


class TestOrderExecutionRecord:
    """Mutable execution tracking record."""

    def test_create_record(self) -> None:
        r = OrderExecutionRecord(order_id="ord1", recipient_id="bn1")
        assert r.status == OrderStatus.DRAFT
        assert r.deviation_level == 0.0
        assert r.was_degraded is False
        assert r.was_misinterpreted is False
        assert r.received_time is None

    def test_record_is_mutable(self) -> None:
        r = OrderExecutionRecord(order_id="ord1", recipient_id="bn1")
        r.status = OrderStatus.ISSUED
        r.issued_time = 100.0
        assert r.status == OrderStatus.ISSUED
        assert r.issued_time == 100.0

    def test_record_lifecycle(self) -> None:
        r = OrderExecutionRecord(
            order_id="ord1", recipient_id="bn1",
            status=OrderStatus.DRAFT, issued_time=0.0,
        )
        r.status = OrderStatus.ISSUED
        r.issued_time = 100.0
        r.status = OrderStatus.IN_TRANSIT
        r.status = OrderStatus.RECEIVED
        r.received_time = 220.0
        r.status = OrderStatus.ACKNOWLEDGED
        r.acknowledged_time = 230.0
        r.status = OrderStatus.EXECUTING
        r.execution_start_time = 240.0
        r.status = OrderStatus.COMPLETED
        r.completion_time = 600.0
        assert r.status == OrderStatus.COMPLETED
        assert r.received_time == 220.0

    def test_record_degraded(self) -> None:
        r = OrderExecutionRecord(order_id="ord1", recipient_id="bn1")
        r.was_degraded = True
        r.was_misinterpreted = True
        r.misinterpretation_type = "position"
        assert r.was_degraded is True
        assert r.misinterpretation_type == "position"

    def test_record_superseded(self) -> None:
        r = OrderExecutionRecord(order_id="ord1", recipient_id="bn1")
        r.status = OrderStatus.EXECUTING
        r.superseded_by = "frago_001"
        r.status = OrderStatus.SUPERSEDED
        assert r.superseded_by == "frago_001"
        assert r.status == OrderStatus.SUPERSEDED

    def test_get_state(self) -> None:
        r = OrderExecutionRecord(
            order_id="ord1", recipient_id="bn1",
            status=OrderStatus.EXECUTING,
            issued_time=100.0, received_time=200.0,
            deviation_level=0.3, was_degraded=True,
        )
        state = r.get_state()
        assert state["order_id"] == "ord1"
        assert state["status"] == int(OrderStatus.EXECUTING)
        assert state["deviation_level"] == 0.3
        assert state["was_degraded"] is True

    def test_set_state(self) -> None:
        r = OrderExecutionRecord(order_id="", recipient_id="")
        state = {
            "order_id": "ord1",
            "recipient_id": "bn1",
            "status": int(OrderStatus.COMPLETED),
            "issued_time": 100.0,
            "received_time": 200.0,
            "acknowledged_time": 210.0,
            "execution_start_time": 220.0,
            "completion_time": 500.0,
            "deviation_level": 0.15,
            "was_degraded": False,
            "was_misinterpreted": True,
            "misinterpretation_type": "timing",
            "superseded_by": None,
        }
        r.set_state(state)
        assert r.order_id == "ord1"
        assert r.status == OrderStatus.COMPLETED
        assert r.completion_time == 500.0
        assert r.was_misinterpreted is True

    def test_state_round_trip(self) -> None:
        r1 = OrderExecutionRecord(
            order_id="ord1", recipient_id="bn1",
            status=OrderStatus.EXECUTING,
            issued_time=100.0, received_time=200.0,
            acknowledged_time=210.0, execution_start_time=220.0,
            deviation_level=0.25, was_degraded=True,
            was_misinterpreted=True, misinterpretation_type="position",
        )
        state = r1.get_state()
        r2 = OrderExecutionRecord(order_id="", recipient_id="")
        r2.set_state(state)
        assert r2.get_state() == state
