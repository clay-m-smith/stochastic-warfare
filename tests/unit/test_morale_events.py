"""Tests for morale/events.py — event creation, immutability, EventBus integration."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from stochastic_warfare.core.events import Event, EventBus
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.morale.events import (
    CohesionChangeEvent,
    MoraleStateChangeEvent,
    RallyEvent,
    RoutEvent,
    StressChangeEvent,
    SurrenderEvent,
)

_TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
_SRC = ModuleId.MORALE


class TestMoraleEventCreation:
    """All morale events can be instantiated with correct fields."""

    def test_morale_state_change(self) -> None:
        e = MoraleStateChangeEvent(
            timestamp=_TS, source=_SRC,
            unit_id="u1", old_state=0, new_state=1,
        )
        assert e.unit_id == "u1"
        assert e.old_state == 0
        assert e.new_state == 1

    def test_rout_event(self) -> None:
        e = RoutEvent(
            timestamp=_TS, source=_SRC,
            unit_id="u1", direction=3.14,
        )
        assert e.direction == pytest.approx(3.14)

    def test_rally_event(self) -> None:
        e = RallyEvent(
            timestamp=_TS, source=_SRC,
            unit_id="u1", rallied_by="cdr1",
        )
        assert e.rallied_by == "cdr1"

    def test_rally_event_self_rally(self) -> None:
        e = RallyEvent(
            timestamp=_TS, source=_SRC,
            unit_id="u1", rallied_by="",
        )
        assert e.rallied_by == ""

    def test_surrender_event(self) -> None:
        e = SurrenderEvent(
            timestamp=_TS, source=_SRC,
            unit_id="u1", capturing_side="red",
        )
        assert e.capturing_side == "red"

    def test_stress_change_event(self) -> None:
        e = StressChangeEvent(
            timestamp=_TS, source=_SRC,
            unit_id="u1", stress_delta=0.15, cause="combat",
        )
        assert e.stress_delta == 0.15

    def test_cohesion_change_event(self) -> None:
        e = CohesionChangeEvent(
            timestamp=_TS, source=_SRC,
            unit_id="u1", cohesion_delta=-0.2, cause="leader_lost",
        )
        assert e.cohesion_delta == -0.2


class TestMoraleEventImmutability:

    def test_morale_state_change_frozen(self) -> None:
        e = MoraleStateChangeEvent(
            timestamp=_TS, source=_SRC,
            unit_id="u1", old_state=0, new_state=1,
        )
        with pytest.raises(AttributeError):
            e.new_state = 2  # type: ignore[misc]

    def test_rout_event_frozen(self) -> None:
        e = RoutEvent(
            timestamp=_TS, source=_SRC,
            unit_id="u1", direction=0.0,
        )
        with pytest.raises(AttributeError):
            e.direction = 1.0  # type: ignore[misc]


class TestMoraleEventInheritance:

    def test_all_inherit_from_event(self) -> None:
        event_classes = [
            MoraleStateChangeEvent, RoutEvent, RallyEvent,
            SurrenderEvent, StressChangeEvent, CohesionChangeEvent,
        ]
        for cls in event_classes:
            assert issubclass(cls, Event), f"{cls.__name__} must inherit Event"


class TestMoraleEventBusIntegration:

    def test_morale_state_change_dispatched(self) -> None:
        bus = EventBus()
        received: list[MoraleStateChangeEvent] = []
        bus.subscribe(MoraleStateChangeEvent, lambda e: received.append(e))

        bus.publish(MoraleStateChangeEvent(
            timestamp=_TS, source=_SRC,
            unit_id="u1", old_state=0, new_state=1,
        ))
        assert len(received) == 1

    def test_stress_and_cohesion_dispatched(self) -> None:
        bus = EventBus()
        received: list[Event] = []
        bus.subscribe(Event, lambda e: received.append(e))

        bus.publish(StressChangeEvent(
            timestamp=_TS, source=_SRC,
            unit_id="u1", stress_delta=0.1, cause="casualties",
        ))
        bus.publish(CohesionChangeEvent(
            timestamp=_TS, source=_SRC,
            unit_id="u1", cohesion_delta=-0.3, cause="isolation",
        ))
        assert len(received) == 2
