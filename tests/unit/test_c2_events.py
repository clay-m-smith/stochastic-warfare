"""Tests for c2/events.py — event creation, immutability, EventBus integration."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from stochastic_warfare.core.events import Event, EventBus
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.c2.events import (
    CommandStatusChangeEvent,
    CommsLostEvent,
    CommsRestoredEvent,
    CoordinationViolationEvent,
    EmconStateChangeEvent,
    InitiativeActionEvent,
    OrderCompletedEvent,
    OrderIssuedEvent,
    OrderMisunderstoodEvent,
    OrderReceivedEvent,
    RoeChangeEvent,
    RoeViolationEvent,
    SuccessionEvent,
)

_TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
_SRC = ModuleId.C2


class TestCommandEvents:
    """Command authority events."""

    def test_command_status_change_event(self) -> None:
        e = CommandStatusChangeEvent(
            timestamp=_TS, source=_SRC,
            unit_id="bn1", old_status=0, new_status=1, cause="commander_kia",
        )
        assert e.unit_id == "bn1"
        assert e.old_status == 0
        assert e.new_status == 1
        assert e.cause == "commander_kia"

    def test_succession_event(self) -> None:
        e = SuccessionEvent(
            timestamp=_TS, source=_SRC,
            unit_id="bn1", old_commander_id="cdr1",
            new_commander_id="xo1", succession_delay_s=300.0,
        )
        assert e.old_commander_id == "cdr1"
        assert e.new_commander_id == "xo1"
        assert e.succession_delay_s == 300.0

    def test_command_event_frozen(self) -> None:
        e = CommandStatusChangeEvent(
            timestamp=_TS, source=_SRC,
            unit_id="bn1", old_status=0, new_status=1, cause="test",
        )
        with pytest.raises(AttributeError):
            e.unit_id = "other"  # type: ignore[misc]


class TestCommsEvents:
    """Communication events."""

    def test_comms_lost_event(self) -> None:
        e = CommsLostEvent(
            timestamp=_TS, source=_SRC,
            from_unit_id="u1", to_unit_id="u2",
            channel_type=0, cause="jamming",
        )
        assert e.from_unit_id == "u1"
        assert e.cause == "jamming"

    def test_comms_restored_event(self) -> None:
        e = CommsRestoredEvent(
            timestamp=_TS, source=_SRC,
            from_unit_id="u1", to_unit_id="u2", channel_type=0,
        )
        assert e.channel_type == 0

    def test_emcon_state_change_event(self) -> None:
        e = EmconStateChangeEvent(
            timestamp=_TS, source=_SRC,
            unit_id="ddg1", old_state=0, new_state=2,
        )
        assert e.old_state == 0
        assert e.new_state == 2

    def test_comms_event_frozen(self) -> None:
        e = CommsLostEvent(
            timestamp=_TS, source=_SRC,
            from_unit_id="u1", to_unit_id="u2",
            channel_type=0, cause="jamming",
        )
        with pytest.raises(AttributeError):
            e.cause = "range"  # type: ignore[misc]


class TestOrderEvents:
    """Order lifecycle events."""

    def test_order_issued_event(self) -> None:
        e = OrderIssuedEvent(
            timestamp=_TS, source=_SRC,
            order_id="ord1", issuer_id="bde1", recipient_id="bn1",
            order_type=0, echelon_level=6,
        )
        assert e.order_id == "ord1"
        assert e.echelon_level == 6

    def test_order_received_event(self) -> None:
        e = OrderReceivedEvent(
            timestamp=_TS, source=_SRC,
            order_id="ord1", recipient_id="bn1",
            delay_s=120.0, degraded=False,
        )
        assert e.delay_s == 120.0
        assert e.degraded is False

    def test_order_misunderstood_event(self) -> None:
        e = OrderMisunderstoodEvent(
            timestamp=_TS, source=_SRC,
            order_id="ord1", recipient_id="bn1",
            misinterpretation_type="position",
        )
        assert e.misinterpretation_type == "position"

    def test_order_completed_event(self) -> None:
        e = OrderCompletedEvent(
            timestamp=_TS, source=_SRC,
            order_id="ord1", unit_id="bn1",
            success=True, deviation_level=0.1,
        )
        assert e.success is True
        assert e.deviation_level == pytest.approx(0.1)

    def test_order_event_frozen(self) -> None:
        e = OrderIssuedEvent(
            timestamp=_TS, source=_SRC,
            order_id="ord1", issuer_id="bde1", recipient_id="bn1",
            order_type=0, echelon_level=6,
        )
        with pytest.raises(AttributeError):
            e.order_id = "other"  # type: ignore[misc]


class TestRoeEvents:
    """Rules of engagement events."""

    def test_roe_violation_event(self) -> None:
        e = RoeViolationEvent(
            timestamp=_TS, source=_SRC,
            unit_id="plt1", violation_type="unauthorized_engagement",
            severity="major",
        )
        assert e.violation_type == "unauthorized_engagement"
        assert e.severity == "major"

    def test_roe_change_event(self) -> None:
        e = RoeChangeEvent(
            timestamp=_TS, source=_SRC,
            affected_unit_ids=("bn1", "bn2"),
            old_roe_level=1, new_roe_level=2,
        )
        assert len(e.affected_unit_ids) == 2
        assert e.old_roe_level == 1

    def test_roe_change_event_frozen(self) -> None:
        e = RoeChangeEvent(
            timestamp=_TS, source=_SRC,
            affected_unit_ids=("bn1",),
            old_roe_level=0, new_roe_level=1,
        )
        with pytest.raises(AttributeError):
            e.new_roe_level = 2  # type: ignore[misc]


class TestCoordinationEvents:
    """Coordination measure events."""

    def test_coordination_violation_event(self) -> None:
        e = CoordinationViolationEvent(
            timestamp=_TS, source=_SRC,
            unit_id="bn1", measure_type="NFA", measure_id="nfa_alpha",
        )
        assert e.measure_type == "NFA"
        assert e.measure_id == "nfa_alpha"


class TestMissionCommandEvents:
    """Initiative / mission command events."""

    def test_initiative_action_event(self) -> None:
        e = InitiativeActionEvent(
            timestamp=_TS, source=_SRC,
            unit_id="plt1", action_type="engage",
            justification="self_defense",
        )
        assert e.action_type == "engage"
        assert e.justification == "self_defense"


class TestEventBusIntegration:
    """C2 events work with the EventBus."""

    def test_c2_events_inherit_from_event(self) -> None:
        e = CommandStatusChangeEvent(
            timestamp=_TS, source=_SRC,
            unit_id="bn1", old_status=0, new_status=1, cause="test",
        )
        assert isinstance(e, Event)

    def test_event_bus_receives_c2_events(self) -> None:
        bus = EventBus()
        received: list[Event] = []
        bus.subscribe(CommandStatusChangeEvent, received.append)
        bus.publish(CommandStatusChangeEvent(
            timestamp=_TS, source=_SRC,
            unit_id="bn1", old_status=0, new_status=1, cause="test",
        ))
        assert len(received) == 1
        assert received[0].unit_id == "bn1"  # type: ignore[attr-defined]

    def test_base_event_subscription_receives_c2(self) -> None:
        bus = EventBus()
        received: list[Event] = []
        bus.subscribe(Event, received.append)
        bus.publish(OrderIssuedEvent(
            timestamp=_TS, source=_SRC,
            order_id="o1", issuer_id="bde1", recipient_id="bn1",
            order_type=0, echelon_level=6,
        ))
        assert len(received) == 1
