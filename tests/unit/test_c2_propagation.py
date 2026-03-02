"""Tests for c2/orders/propagation.py — order propagation with stochastic friction."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from stochastic_warfare.core.events import Event, EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.c2.command import CommandConfig, CommandEngine, CommandStatus
from stochastic_warfare.c2.communications import (
    CommEquipmentDefinition,
    CommEquipmentLoader,
    CommunicationsEngine,
)
from stochastic_warfare.c2.events import (
    OrderIssuedEvent,
    OrderMisunderstoodEvent,
    OrderReceivedEvent,
)
from stochastic_warfare.c2.orders.propagation import (
    OrderPropagationEngine,
    PropagationConfig,
    PropagationResult,
)
from stochastic_warfare.c2.orders.types import (
    MissionType,
    Order,
    OrderPriority,
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


def _make_engines(
    seed: int = 42,
    prop_config: PropagationConfig | None = None,
) -> tuple[OrderPropagationEngine, EventBus, CommandEngine, CommunicationsEngine]:
    """Build a complete propagation setup."""
    hierarchy = HierarchyTree()
    hierarchy.add_unit("div1", EchelonLevel.DIVISION)
    hierarchy.add_unit("bde1", EchelonLevel.BRIGADE, "div1")
    hierarchy.add_unit("bn1", EchelonLevel.BATTALION, "bde1")
    hierarchy.add_unit("co1", EchelonLevel.COMPANY, "bn1")

    task_org = TaskOrgManager(hierarchy)
    bus = EventBus()
    rng_mgr = RNGManager(seed)

    cmd_rng = rng_mgr.get_stream(ModuleId.C2)
    cmd = CommandEngine(hierarchy, task_org, {}, bus, cmd_rng)
    for uid in ["div1", "bde1", "bn1", "co1"]:
        cmd.register_unit(uid, f"cdr_{uid}")

    vhf = _make_vhf()
    loader = CommEquipmentLoader()
    loader._definitions[vhf.comm_id] = vhf
    comms_rng = rng_mgr.get_stream(ModuleId.ENVIRONMENT)
    comms = CommunicationsEngine(bus, comms_rng, loader)
    for uid in ["div1", "bde1", "bn1", "co1"]:
        comms.register_unit(uid, ["test_vhf"])

    prop_rng = rng_mgr.get_stream(ModuleId.MOVEMENT)
    prop = OrderPropagationEngine(
        comms, cmd, bus, prop_rng, config=prop_config,
    )
    return prop, bus, cmd, comms


def _make_order(
    echelon: EchelonLevel = EchelonLevel.BATTALION,
    issuer: str = "bde1",
    recipient: str = "bn1",
    order_type: OrderType = OrderType.OPORD,
    priority: OrderPriority = OrderPriority.ROUTINE,
) -> Order:
    return Order(
        order_id="ord_001", issuer_id=issuer, recipient_id=recipient,
        timestamp=_TS, order_type=order_type,
        echelon_level=int(echelon), priority=priority,
        mission_type=int(MissionType.ATTACK),
    )


class TestPropagationBasic:
    """Basic order propagation."""

    def test_successful_propagation(self) -> None:
        prop, bus, cmd, comms = _make_engines()
        order = _make_order()
        result = prop.propagate_order(order, _POS_A, _POS_B, _TS)
        assert result.success is True
        assert result.total_delay_s > 0

    def test_no_authority_fails(self) -> None:
        prop, bus, cmd, comms = _make_engines()
        # bn1 cannot issue to bde1 (subordinate → superior)
        order = _make_order(issuer="bn1", recipient="bde1")
        result = prop.propagate_order(order, _POS_A, _POS_B, _TS)
        assert result.success is False

    def test_publishes_issued_event(self) -> None:
        prop, bus, cmd, comms = _make_engines()
        events: list[OrderIssuedEvent] = []
        bus.subscribe(OrderIssuedEvent, events.append)
        order = _make_order()
        prop.propagate_order(order, _POS_A, _POS_B, _TS)
        assert len(events) == 1
        assert events[0].order_id == "ord_001"

    def test_publishes_received_event(self) -> None:
        prop, bus, cmd, comms = _make_engines()
        events: list[OrderReceivedEvent] = []
        bus.subscribe(OrderReceivedEvent, events.append)
        order = _make_order()
        prop.propagate_order(order, _POS_A, _POS_B, _TS)
        assert len(events) == 1
        assert events[0].delay_s > 0


class TestDelayScaling:
    """Delay scales with echelon and order type."""

    def test_individual_faster_than_battalion(self) -> None:
        prop, *_ = _make_engines(seed=100)
        # Use same config to compare
        delay_ind = prop.compute_delay(
            int(EchelonLevel.INDIVIDUAL), 1.0,
            _make_order(EchelonLevel.INDIVIDUAL),
        )
        prop2, *_ = _make_engines(seed=100)
        delay_bn = prop2.compute_delay(
            int(EchelonLevel.BATTALION), 1.0,
            _make_order(EchelonLevel.BATTALION),
        )
        assert delay_ind < delay_bn

    def test_battalion_faster_than_corps(self) -> None:
        prop, *_ = _make_engines(seed=100)
        delay_bn = prop.compute_delay(
            int(EchelonLevel.BATTALION), 1.0,
            _make_order(EchelonLevel.BATTALION),
        )
        prop2, *_ = _make_engines(seed=100)
        delay_corps = prop2.compute_delay(
            int(EchelonLevel.CORPS), 1.0,
            _make_order(EchelonLevel.CORPS),
        )
        assert delay_bn < delay_corps

    def test_frago_faster_than_opord(self) -> None:
        prop, *_ = _make_engines(seed=200)
        delay_opord = prop.compute_delay(
            int(EchelonLevel.BATTALION), 1.0,
            _make_order(order_type=OrderType.OPORD),
        )
        prop2, *_ = _make_engines(seed=200)
        delay_frago = prop2.compute_delay(
            int(EchelonLevel.BATTALION), 1.0,
            _make_order(order_type=OrderType.FRAGO),
        )
        assert delay_frago < delay_opord

    def test_flash_priority_reduces_delay(self) -> None:
        prop, *_ = _make_engines(seed=300)
        delay_routine = prop.compute_delay(
            int(EchelonLevel.BATTALION), 1.0,
            _make_order(priority=OrderPriority.ROUTINE),
        )
        prop2, *_ = _make_engines(seed=300)
        delay_flash = prop2.compute_delay(
            int(EchelonLevel.BATTALION), 1.0,
            _make_order(priority=OrderPriority.FLASH),
        )
        assert delay_flash < delay_routine

    def test_poor_staff_increases_delay(self) -> None:
        prop, *_ = _make_engines(seed=400)
        delay_good = prop.compute_delay(int(EchelonLevel.BATTALION), 1.0)
        prop2, *_ = _make_engines(seed=400)
        delay_poor = prop2.compute_delay(int(EchelonLevel.BATTALION), 0.2)
        assert delay_poor > delay_good


class TestMisinterpretation:
    """Order misinterpretation."""

    def test_misinterpretation_probability_increases_with_poor_staff(self) -> None:
        prop, *_ = _make_engines()
        order = _make_order()
        p_good = prop.compute_misinterpretation_probability(order, 1.0, 1.0)
        p_bad = prop.compute_misinterpretation_probability(order, 0.0, 1.0)
        assert p_bad > p_good

    def test_misinterpretation_probability_increases_with_poor_comms(self) -> None:
        prop, *_ = _make_engines()
        order = _make_order()
        p_good = prop.compute_misinterpretation_probability(order, 1.0, 1.0)
        p_bad = prop.compute_misinterpretation_probability(order, 1.0, 0.0)
        assert p_bad > p_good

    def test_misinterpretation_publishes_event(self) -> None:
        # Use high misinterpretation base to ensure it triggers
        config = PropagationConfig(base_misinterpretation=1.0)
        prop, bus, *_ = _make_engines(seed=42, prop_config=config)
        events: list[OrderMisunderstoodEvent] = []
        bus.subscribe(OrderMisunderstoodEvent, events.append)

        order = _make_order()
        prop.propagate_order(order, _POS_A, _POS_B, _TS)
        assert len(events) >= 1  # Should definitely misinterpret
        assert events[0].misinterpretation_type in (
            "position", "timing", "objective", "unit_designation",
        )

    def test_minimum_misinterpretation_probability(self) -> None:
        prop, *_ = _make_engines()
        order = _make_order()
        # Even perfect conditions have nonzero probability
        p = prop.compute_misinterpretation_probability(order, 1.0, 1.0)
        assert p > 0


class TestCommsFailure:
    """Comms failure blocks propagation."""

    def test_no_comms_equipment_fails(self) -> None:
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

        prop = OrderPropagationEngine(
            comms, cmd, bus, rng_mgr.get_stream(ModuleId.MOVEMENT),
        )

        order = _make_order()
        result = prop.propagate_order(order, _POS_A, _POS_B, _TS)
        assert result.success is False


class TestDegradedSender:
    """Degraded sender C2 is reported."""

    def test_degraded_sender_flagged(self) -> None:
        prop, bus, cmd, comms = _make_engines()
        cmd.handle_comms_loss("bde1", _TS)  # Degrade sender
        order = _make_order(issuer="bde1", recipient="bn1")
        result = prop.propagate_order(order, _POS_A, _POS_B, _TS)
        if result.success:
            assert result.degraded is True


class TestStateProtocol:
    """State round-trip."""

    def test_state_round_trip(self) -> None:
        prop, *_ = _make_engines()
        state = prop.get_state()
        prop2, *_ = _make_engines()
        prop2.set_state(state)
        assert prop2.get_state() == state


class TestDeterministicReplay:
    """Same seed → identical propagation results."""

    def test_deterministic_delays(self) -> None:
        def run(seed: int) -> list[float]:
            prop, *_ = _make_engines(seed=seed)
            return [
                prop.compute_delay(int(EchelonLevel.BATTALION), 1.0)
                for _ in range(10)
            ]
        assert run(55) == run(55)

    def test_deterministic_propagation(self) -> None:
        def run(seed: int) -> list[bool]:
            prop, *_ = _make_engines(seed=seed)
            order = _make_order()
            results = []
            for i in range(10):
                o = Order(
                    order_id=f"ord_{i}", issuer_id="bde1", recipient_id="bn1",
                    timestamp=_TS, order_type=OrderType.OPORD,
                    echelon_level=int(EchelonLevel.BATTALION),
                    priority=OrderPriority.ROUTINE,
                    mission_type=int(MissionType.ATTACK),
                )
                r = prop.propagate_order(o, _POS_A, _POS_B, _TS)
                results.append(r.success)
            return results
        assert run(88) == run(88)
