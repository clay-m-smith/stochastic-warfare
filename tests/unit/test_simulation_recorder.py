"""Tests for stochastic_warfare.simulation.recorder — event recording & snapshots.

Covers RecorderConfig, RecordedEvent, StateSnapshot frozen dataclasses,
event capture via EventBus subscription, type filtering, tick range queries,
memory limits, start/stop lifecycle, and checkpoint/restore.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import pytest

from stochastic_warfare.core.events import Event, EventBus
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.simulation.recorder import (
    RecorderConfig,
    RecordedEvent,
    SimulationRecorder,
    StateSnapshot,
)
from tests.conftest import TS

# ---------------------------------------------------------------------------
# Test event subclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _TestCombatEvent(Event):
    attacker_id: str = ""
    target_id: str = ""


@dataclass(frozen=True)
class _TestMovementEvent(Event):
    unit_id: str = ""
    distance: float = 0.0


# ---------------------------------------------------------------------------
# TestRecorderConfig
# ---------------------------------------------------------------------------


class TestRecorderConfig:
    def test_defaults(self) -> None:
        cfg = RecorderConfig()
        assert cfg.max_events == 1_000_000
        assert cfg.snapshot_interval_ticks == 100
        assert cfg.enabled is True

    def test_custom_values(self) -> None:
        cfg = RecorderConfig(max_events=500, snapshot_interval_ticks=10, enabled=False)
        assert cfg.max_events == 500
        assert cfg.snapshot_interval_ticks == 10
        assert cfg.enabled is False

    def test_enabled_flag(self) -> None:
        cfg_on = RecorderConfig(enabled=True)
        cfg_off = RecorderConfig(enabled=False)
        assert cfg_on.enabled is True
        assert cfg_off.enabled is False


# ---------------------------------------------------------------------------
# TestRecordedEvent
# ---------------------------------------------------------------------------


class TestRecordedEvent:
    def test_creation(self) -> None:
        evt = RecordedEvent(
            tick=5,
            timestamp=TS,
            event_type="CombatEvent",
            source="core",
            data={"attacker_id": "u1"},
        )
        assert evt.tick == 5
        assert evt.event_type == "CombatEvent"
        assert evt.source == "core"
        assert evt.data == {"attacker_id": "u1"}

    def test_frozen_immutability(self) -> None:
        evt = RecordedEvent(
            tick=0, timestamp=TS, event_type="X", source="core", data={},
        )
        with pytest.raises(AttributeError):
            evt.tick = 99  # type: ignore[misc]

    def test_field_access(self) -> None:
        evt = RecordedEvent(
            tick=3,
            timestamp=TS,
            event_type="Move",
            source="movement",
            data={"distance": 100.0},
        )
        assert evt.timestamp == TS
        assert evt.data["distance"] == 100.0


# ---------------------------------------------------------------------------
# TestStateSnapshot
# ---------------------------------------------------------------------------


class TestStateSnapshot:
    def test_creation(self) -> None:
        snap = StateSnapshot(tick=10, timestamp=TS, state={"units": 5})
        assert snap.tick == 10
        assert snap.timestamp == TS
        assert snap.state == {"units": 5}

    def test_frozen_immutability(self) -> None:
        snap = StateSnapshot(tick=0, timestamp=TS, state={})
        with pytest.raises(AttributeError):
            snap.tick = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TestEventCapture
# ---------------------------------------------------------------------------


class TestEventCapture:
    def test_start_subscribes_to_events(self) -> None:
        bus = EventBus()
        rec = SimulationRecorder(bus)
        rec.start()
        bus.publish(Event(timestamp=TS, source=ModuleId.CORE))
        assert rec.event_count() == 1

    def test_captures_events_published_to_bus(self) -> None:
        bus = EventBus()
        rec = SimulationRecorder(bus)
        rec.start()
        bus.publish(Event(timestamp=TS, source=ModuleId.CORE))
        bus.publish(Event(timestamp=TS, source=ModuleId.COMBAT))
        assert rec.event_count() == 2

    def test_captures_event_type_name_correctly(self) -> None:
        bus = EventBus()
        rec = SimulationRecorder(bus)
        rec.start()
        bus.publish(_TestCombatEvent(timestamp=TS, source=ModuleId.COMBAT, attacker_id="a1"))
        evts = rec.events
        assert evts[0].event_type == "_TestCombatEvent"

    def test_captures_event_timestamp(self) -> None:
        bus = EventBus()
        rec = SimulationRecorder(bus)
        rec.start()
        t = TS + timedelta(hours=1)
        bus.publish(Event(timestamp=t, source=ModuleId.CORE))
        assert rec.events[0].timestamp == t

    def test_captures_event_source(self) -> None:
        bus = EventBus()
        rec = SimulationRecorder(bus)
        rec.start()
        bus.publish(Event(timestamp=TS, source=ModuleId.MOVEMENT))
        assert rec.events[0].source == "movement"

    def test_multiple_event_types_captured(self) -> None:
        bus = EventBus()
        rec = SimulationRecorder(bus)
        rec.start()
        bus.publish(_TestCombatEvent(timestamp=TS, source=ModuleId.COMBAT))
        bus.publish(_TestMovementEvent(timestamp=TS, source=ModuleId.MOVEMENT, unit_id="u1"))
        bus.publish(Event(timestamp=TS, source=ModuleId.CORE))
        assert rec.event_count() == 3
        types = {e.event_type for e in rec.events}
        assert types == {"_TestCombatEvent", "_TestMovementEvent", "Event"}


# ---------------------------------------------------------------------------
# TestStateSnapshots
# ---------------------------------------------------------------------------


class TestStateSnapshots:
    def test_take_snapshot_stores_state(self) -> None:
        bus = EventBus()
        rec = SimulationRecorder(bus)
        rec.take_snapshot(0, TS, lambda: {"units": 3})
        assert len(rec.snapshots) == 1
        assert rec.snapshots[0].state == {"units": 3}

    def test_multiple_snapshots(self) -> None:
        bus = EventBus()
        rec = SimulationRecorder(bus)
        rec.take_snapshot(0, TS, lambda: {"tick": 0})
        rec.take_snapshot(100, TS, lambda: {"tick": 100})
        assert len(rec.snapshots) == 2

    def test_state_provider_called_at_snapshot_time(self) -> None:
        bus = EventBus()
        rec = SimulationRecorder(bus)
        counter = {"calls": 0}

        def provider() -> dict:
            counter["calls"] += 1
            return {"calls": counter["calls"]}

        rec.take_snapshot(0, TS, provider)
        rec.take_snapshot(1, TS, provider)
        assert counter["calls"] == 2
        assert rec.snapshots[0].state == {"calls": 1}
        assert rec.snapshots[1].state == {"calls": 2}

    def test_snapshot_captures_tick_and_timestamp(self) -> None:
        bus = EventBus()
        rec = SimulationRecorder(bus)
        t = TS + timedelta(minutes=30)
        rec.take_snapshot(42, t, lambda: {})
        snap = rec.snapshots[0]
        assert snap.tick == 42
        assert snap.timestamp == t

    def test_snapshots_property_returns_copy(self) -> None:
        bus = EventBus()
        rec = SimulationRecorder(bus)
        rec.take_snapshot(0, TS, lambda: {"a": 1})
        snaps1 = rec.snapshots
        snaps2 = rec.snapshots
        assert snaps1 == snaps2
        assert snaps1 is not snaps2  # different list objects


# ---------------------------------------------------------------------------
# TestTypeFiltering
# ---------------------------------------------------------------------------


class TestTypeFiltering:
    def test_events_of_type_returns_matching(self) -> None:
        bus = EventBus()
        rec = SimulationRecorder(bus)
        rec.start()
        bus.publish(_TestCombatEvent(timestamp=TS, source=ModuleId.COMBAT))
        bus.publish(_TestMovementEvent(timestamp=TS, source=ModuleId.MOVEMENT))
        bus.publish(_TestCombatEvent(timestamp=TS, source=ModuleId.COMBAT))
        result = rec.events_of_type("_TestCombatEvent")
        assert len(result) == 2

    def test_events_of_type_no_matches(self) -> None:
        bus = EventBus()
        rec = SimulationRecorder(bus)
        rec.start()
        bus.publish(Event(timestamp=TS, source=ModuleId.CORE))
        result = rec.events_of_type("NonExistentEvent")
        assert result == []

    def test_multiple_types_filter_correctly(self) -> None:
        bus = EventBus()
        rec = SimulationRecorder(bus)
        rec.start()
        bus.publish(_TestCombatEvent(timestamp=TS, source=ModuleId.COMBAT))
        bus.publish(_TestMovementEvent(timestamp=TS, source=ModuleId.MOVEMENT))
        bus.publish(Event(timestamp=TS, source=ModuleId.CORE))
        combat = rec.events_of_type("_TestCombatEvent")
        movement = rec.events_of_type("_TestMovementEvent")
        base = rec.events_of_type("Event")
        assert len(combat) == 1
        assert len(movement) == 1
        assert len(base) == 1

    def test_type_name_is_class_name_not_module_path(self) -> None:
        bus = EventBus()
        rec = SimulationRecorder(bus)
        rec.start()
        bus.publish(_TestCombatEvent(timestamp=TS, source=ModuleId.COMBAT))
        evt = rec.events[0]
        # Should be just the class name, not the full module path
        assert "." not in evt.event_type
        assert evt.event_type == "_TestCombatEvent"


# ---------------------------------------------------------------------------
# TestRangeQueries
# ---------------------------------------------------------------------------


class TestRangeQueries:
    def test_events_in_range_returns_correct_events(self) -> None:
        bus = EventBus()
        rec = SimulationRecorder(bus)
        rec.start()
        # Publish events at different ticks
        for tick in range(5):
            rec.record_tick(tick, TS + timedelta(seconds=tick))
            bus.publish(Event(timestamp=TS + timedelta(seconds=tick), source=ModuleId.CORE))
        result = rec.events_in_range(1, 3)
        assert len(result) == 3
        assert all(1 <= e.tick <= 3 for e in result)

    def test_empty_range_returns_empty(self) -> None:
        bus = EventBus()
        rec = SimulationRecorder(bus)
        rec.start()
        rec.record_tick(0, TS)
        bus.publish(Event(timestamp=TS, source=ModuleId.CORE))
        result = rec.events_in_range(10, 20)
        assert result == []

    def test_inclusive_boundaries(self) -> None:
        bus = EventBus()
        rec = SimulationRecorder(bus)
        rec.start()
        rec.record_tick(5, TS)
        bus.publish(Event(timestamp=TS, source=ModuleId.CORE))
        rec.record_tick(10, TS)
        bus.publish(Event(timestamp=TS, source=ModuleId.CORE))
        # Exactly at boundaries
        result_start = rec.events_in_range(5, 7)
        assert len(result_start) == 1
        result_end = rec.events_in_range(8, 10)
        assert len(result_end) == 1
        result_both = rec.events_in_range(5, 10)
        assert len(result_both) == 2

    def test_all_events_within_range(self) -> None:
        bus = EventBus()
        rec = SimulationRecorder(bus)
        rec.start()
        for tick in range(10):
            rec.record_tick(tick, TS)
            bus.publish(Event(timestamp=TS, source=ModuleId.CORE))
        result = rec.events_in_range(0, 9)
        assert len(result) == 10


# ---------------------------------------------------------------------------
# TestMemoryLimits
# ---------------------------------------------------------------------------


class TestMemoryLimits:
    def test_events_dropped_when_max_events_reached(self) -> None:
        bus = EventBus()
        cfg = RecorderConfig(max_events=5)
        rec = SimulationRecorder(bus, cfg)
        rec.start()
        for _ in range(10):
            bus.publish(Event(timestamp=TS, source=ModuleId.CORE))
        assert rec.event_count() == 5

    def test_event_count_reflects_actual_count(self) -> None:
        bus = EventBus()
        cfg = RecorderConfig(max_events=3)
        rec = SimulationRecorder(bus, cfg)
        rec.start()
        bus.publish(Event(timestamp=TS, source=ModuleId.CORE))
        assert rec.event_count() == 1
        bus.publish(Event(timestamp=TS, source=ModuleId.CORE))
        bus.publish(Event(timestamp=TS, source=ModuleId.CORE))
        assert rec.event_count() == 3
        # Additional events should be silently dropped
        bus.publish(Event(timestamp=TS, source=ModuleId.CORE))
        assert rec.event_count() == 3

    def test_disabled_recorder_captures_nothing(self) -> None:
        bus = EventBus()
        cfg = RecorderConfig(enabled=False)
        rec = SimulationRecorder(bus, cfg)
        rec.start()
        bus.publish(Event(timestamp=TS, source=ModuleId.CORE))
        bus.publish(_TestCombatEvent(timestamp=TS, source=ModuleId.COMBAT))
        assert rec.event_count() == 0


# ---------------------------------------------------------------------------
# TestStartStop
# ---------------------------------------------------------------------------


class TestStartStop:
    def test_stop_unsubscribes_from_bus(self) -> None:
        bus = EventBus()
        rec = SimulationRecorder(bus)
        rec.start()
        bus.publish(Event(timestamp=TS, source=ModuleId.CORE))
        assert rec.event_count() == 1
        rec.stop()
        # After stop, the handler should be removed from the bus
        bus.publish(Event(timestamp=TS, source=ModuleId.CORE))
        assert rec.event_count() == 1

    def test_events_after_stop_not_captured(self) -> None:
        bus = EventBus()
        rec = SimulationRecorder(bus)
        rec.start()
        bus.publish(Event(timestamp=TS, source=ModuleId.CORE))
        rec.stop()
        bus.publish(Event(timestamp=TS, source=ModuleId.COMBAT))
        bus.publish(Event(timestamp=TS, source=ModuleId.MOVEMENT))
        assert rec.event_count() == 1
        assert rec.events[0].source == "core"

    def test_start_after_stop_resumes_capture(self) -> None:
        bus = EventBus()
        rec = SimulationRecorder(bus)
        rec.start()
        bus.publish(Event(timestamp=TS, source=ModuleId.CORE))
        rec.stop()
        bus.publish(Event(timestamp=TS, source=ModuleId.CORE))  # not captured
        rec.start()
        bus.publish(Event(timestamp=TS, source=ModuleId.COMBAT))
        assert rec.event_count() == 2
        assert rec.events[1].source == "combat"


# ---------------------------------------------------------------------------
# TestCheckpointRestore
# ---------------------------------------------------------------------------


class TestCheckpointRestore:
    def test_get_state_returns_serializable_dict(self) -> None:
        bus = EventBus()
        rec = SimulationRecorder(bus)
        rec.start()
        rec.record_tick(5, TS)
        bus.publish(Event(timestamp=TS, source=ModuleId.CORE))
        state = rec.get_state()
        assert isinstance(state, dict)
        assert "events" in state
        assert "snapshots" in state
        assert "current_tick" in state
        assert state["current_tick"] == 5
        # Verify event is serialized correctly
        assert len(state["events"]) == 1
        evt = state["events"][0]
        assert evt["tick"] == 5
        assert evt["event_type"] == "Event"
        assert evt["source"] == "core"
        assert isinstance(evt["timestamp"], str)  # ISO format string

    def test_set_state_restores_events(self) -> None:
        bus = EventBus()
        rec = SimulationRecorder(bus)
        state = {
            "current_tick": 10,
            "events": [
                {
                    "tick": 3,
                    "timestamp": TS.isoformat(),
                    "event_type": "CombatEvent",
                    "source": "combat",
                    "data": {"target": "tank1"},
                },
                {
                    "tick": 7,
                    "timestamp": (TS + timedelta(seconds=30)).isoformat(),
                    "event_type": "MoveEvent",
                    "source": "movement",
                    "data": {"distance": 500.0},
                },
            ],
            "snapshots": [],
        }
        rec.set_state(state)
        assert rec.event_count() == 2
        assert rec.events[0].event_type == "CombatEvent"
        assert rec.events[0].data == {"target": "tank1"}
        assert rec.events[1].event_type == "MoveEvent"

    def test_round_trip_preserves_event_count(self) -> None:
        bus = EventBus()
        rec1 = SimulationRecorder(bus)
        rec1.start()
        rec1.record_tick(1, TS)
        bus.publish(Event(timestamp=TS, source=ModuleId.CORE))
        rec1.record_tick(2, TS)
        bus.publish(_TestCombatEvent(timestamp=TS, source=ModuleId.COMBAT, attacker_id="a1"))
        bus.publish(_TestMovementEvent(timestamp=TS, source=ModuleId.MOVEMENT, unit_id="u1"))
        rec1.stop()

        state = rec1.get_state()

        rec2 = SimulationRecorder(bus)
        rec2.set_state(state)
        assert rec2.event_count() == rec1.event_count()

    def test_current_tick_restored(self) -> None:
        bus = EventBus()
        rec = SimulationRecorder(bus)
        state = {
            "current_tick": 42,
            "events": [],
            "snapshots": [],
        }
        rec.set_state(state)
        # After restore, new events should be tagged with the restored tick
        rec.start()
        bus.publish(Event(timestamp=TS, source=ModuleId.CORE))
        assert rec.events[0].tick == 42
