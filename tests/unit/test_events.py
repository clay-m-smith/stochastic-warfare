"""Tests for core/events.py — event bus pub-sub."""

from dataclasses import dataclass
from datetime import datetime, timezone

from stochastic_warfare.core.events import Event, EventBus
from stochastic_warfare.core.types import ModuleId

_NOW = datetime(2000, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class CombatEvent(Event):
    damage: float = 0.0


@dataclass(frozen=True)
class MovementEvent(Event):
    distance: float = 0.0


class TestBasicPubSub:
    def test_subscribe_and_publish(self) -> None:
        bus = EventBus()
        received: list[Event] = []
        bus.subscribe(CombatEvent, received.append)

        evt = CombatEvent(timestamp=_NOW, source=ModuleId.COMBAT, damage=10.0)
        bus.publish(evt)
        assert received == [evt]

    def test_no_handler_no_error(self) -> None:
        bus = EventBus()
        evt = CombatEvent(timestamp=_NOW, source=ModuleId.COMBAT)
        bus.publish(evt)  # should not raise

    def test_multiple_subscribers(self) -> None:
        bus = EventBus()
        a: list[Event] = []
        b: list[Event] = []
        bus.subscribe(CombatEvent, a.append)
        bus.subscribe(CombatEvent, b.append)

        evt = CombatEvent(timestamp=_NOW, source=ModuleId.COMBAT)
        bus.publish(evt)
        assert len(a) == 1
        assert len(b) == 1

    def test_wrong_event_type_not_received(self) -> None:
        bus = EventBus()
        received: list[Event] = []
        bus.subscribe(MovementEvent, received.append)

        evt = CombatEvent(timestamp=_NOW, source=ModuleId.COMBAT)
        bus.publish(evt)
        assert received == []


class TestPriority:
    def test_lower_priority_first(self) -> None:
        bus = EventBus()
        order: list[str] = []

        bus.subscribe(CombatEvent, lambda e: order.append("low"), priority=10)
        bus.subscribe(CombatEvent, lambda e: order.append("high"), priority=1)

        bus.publish(CombatEvent(timestamp=_NOW, source=ModuleId.COMBAT))
        assert order == ["high", "low"]

    def test_same_priority_preserves_insertion_order(self) -> None:
        bus = EventBus()
        order: list[str] = []

        bus.subscribe(CombatEvent, lambda e: order.append("first"), priority=0)
        bus.subscribe(CombatEvent, lambda e: order.append("second"), priority=0)

        bus.publish(CombatEvent(timestamp=_NOW, source=ModuleId.COMBAT))
        assert order == ["first", "second"]


class TestInheritance:
    def test_base_subscriber_receives_derived(self) -> None:
        bus = EventBus()
        received: list[Event] = []
        bus.subscribe(Event, received.append)  # subscribe to base

        combat = CombatEvent(timestamp=_NOW, source=ModuleId.COMBAT, damage=5.0)
        movement = MovementEvent(timestamp=_NOW, source=ModuleId.MOVEMENT, distance=100.0)
        bus.publish(combat)
        bus.publish(movement)

        assert len(received) == 2
        assert received[0] is combat
        assert received[1] is movement


class TestUnsubscribe:
    def test_unsubscribe_stops_delivery(self) -> None:
        bus = EventBus()
        received: list[Event] = []
        bus.subscribe(CombatEvent, received.append)
        bus.unsubscribe(CombatEvent, received.append)

        bus.publish(CombatEvent(timestamp=_NOW, source=ModuleId.COMBAT))
        assert received == []


class TestClear:
    def test_clear_removes_all(self) -> None:
        bus = EventBus()
        received: list[Event] = []
        bus.subscribe(CombatEvent, received.append)
        bus.subscribe(MovementEvent, received.append)
        bus.clear()

        bus.publish(CombatEvent(timestamp=_NOW, source=ModuleId.COMBAT))
        bus.publish(MovementEvent(timestamp=_NOW, source=ModuleId.MOVEMENT))
        assert received == []
