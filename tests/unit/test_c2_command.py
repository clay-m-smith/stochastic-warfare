"""Tests for c2/command.py — command authority, succession, effectiveness."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from stochastic_warfare.core.events import Event, EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.c2.command import (
    CommandConfig,
    CommandEngine,
    CommandStatus,
)
from stochastic_warfare.c2.events import (
    CommandStatusChangeEvent,
    SuccessionEvent,
)
from stochastic_warfare.entities.organization.echelons import EchelonLevel
from stochastic_warfare.entities.organization.hierarchy import HierarchyTree
from stochastic_warfare.entities.organization.task_org import (
    CommandRelationship,
    TaskOrgManager,
)

_TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def _make_engine(
    seed: int = 42,
    config: CommandConfig | None = None,
) -> tuple[CommandEngine, EventBus, HierarchyTree, TaskOrgManager]:
    """Build a CommandEngine with a standard 3-level hierarchy."""
    hierarchy = HierarchyTree()
    hierarchy.add_unit("div1", EchelonLevel.DIVISION)
    hierarchy.add_unit("bde1", EchelonLevel.BRIGADE, "div1")
    hierarchy.add_unit("bde2", EchelonLevel.BRIGADE, "div1")
    hierarchy.add_unit("bn1", EchelonLevel.BATTALION, "bde1")
    hierarchy.add_unit("bn2", EchelonLevel.BATTALION, "bde1")
    hierarchy.add_unit("co1", EchelonLevel.COMPANY, "bn1")

    task_org = TaskOrgManager(hierarchy)
    bus = EventBus()
    rng = RNGManager(seed).get_stream(ModuleId.C2)

    engine = CommandEngine(
        hierarchy=hierarchy,
        task_org=task_org,
        staff_capabilities={},
        event_bus=bus,
        rng=rng,
        config=config,
    )
    # Register units with commanders
    for uid in ["div1", "bde1", "bde2", "bn1", "bn2", "co1"]:
        engine.register_unit(uid, f"cdr_{uid}")

    return engine, bus, hierarchy, task_org


class TestCommandStatus:
    """CommandStatus enum."""

    def test_status_values(self) -> None:
        assert CommandStatus.FULLY_OPERATIONAL == 0
        assert CommandStatus.DEGRADED == 1
        assert CommandStatus.DISRUPTED == 2
        assert CommandStatus.DESTROYED == 3
        assert len(CommandStatus) == 4

    def test_status_ordering(self) -> None:
        assert CommandStatus.FULLY_OPERATIONAL < CommandStatus.DEGRADED
        assert CommandStatus.DEGRADED < CommandStatus.DISRUPTED
        assert CommandStatus.DISRUPTED < CommandStatus.DESTROYED


class TestCommandConfig:
    """CommandConfig defaults."""

    def test_default_config(self) -> None:
        c = CommandConfig()
        assert c.succession_delay_mean_s == 300.0
        assert c.succession_delay_sigma == 0.5
        assert c.degraded_effectiveness_mult == 0.6
        assert c.disrupted_effectiveness_mult == 0.2
        assert c.destroyed_effectiveness_mult == 0.0

    def test_custom_config(self) -> None:
        c = CommandConfig(succession_delay_mean_s=600.0)
        assert c.succession_delay_mean_s == 600.0


class TestRegistrationAndQueries:
    """Unit registration and status queries."""

    def test_register_unit(self) -> None:
        engine, *_ = _make_engine()
        assert engine.get_status("bn1") == CommandStatus.FULLY_OPERATIONAL

    def test_get_commander(self) -> None:
        engine, *_ = _make_engine()
        assert engine.get_commander("bn1") == "cdr_bn1"

    def test_initial_effectiveness(self) -> None:
        engine, *_ = _make_engine()
        assert engine.get_effectiveness("bn1") == 1.0

    def test_unregistered_unit_raises(self) -> None:
        engine, *_ = _make_engine()
        with pytest.raises(KeyError):
            engine.get_status("nonexistent")


class TestCommanderLoss:
    """Commander KIA triggers succession."""

    def test_succession_triggers(self) -> None:
        engine, bus, *_ = _make_engine()
        events: list[Event] = []
        bus.subscribe(SuccessionEvent, events.append)
        engine.handle_commander_loss("bn1", _TS)
        assert len(events) == 1
        e = events[0]
        assert e.unit_id == "bn1"
        assert e.old_commander_id == "cdr_bn1"
        assert e.succession_delay_s > 0

    def test_succession_degrades_to_disrupted(self) -> None:
        engine, *_ = _make_engine()
        engine.handle_commander_loss("bn1", _TS)
        assert engine.get_status("bn1") == CommandStatus.DISRUPTED

    def test_succession_effectiveness_during_transition(self) -> None:
        engine, *_ = _make_engine()
        engine.handle_commander_loss("bn1", _TS)
        # During succession, effectiveness is disrupted level
        assert engine.get_effectiveness("bn1") == 0.2

    def test_succession_completes_after_timer(self) -> None:
        engine, bus, *_ = _make_engine()
        events: list[SuccessionEvent] = []
        bus.subscribe(SuccessionEvent, events.append)

        engine.handle_commander_loss("bn1", _TS)
        delay = events[0].succession_delay_s

        # Advance time past the succession delay
        engine.update(delay + 1.0, _TS)

        # Commander should have changed
        assert engine.get_commander("bn1") != "cdr_bn1"
        # Status should recover to DEGRADED (not fully operational yet)
        assert engine.get_status("bn1") == CommandStatus.DEGRADED

    def test_succession_new_commander_is_subordinate(self) -> None:
        engine, bus, *_ = _make_engine()
        events: list[SuccessionEvent] = []
        bus.subscribe(SuccessionEvent, events.append)

        engine.handle_commander_loss("bn1", _TS)
        # First child of bn1 is co1
        assert events[0].new_commander_id == "co1"

    def test_succession_publishes_status_change(self) -> None:
        engine, bus, *_ = _make_engine()
        events: list[CommandStatusChangeEvent] = []
        bus.subscribe(CommandStatusChangeEvent, events.append)
        engine.handle_commander_loss("bn1", _TS)
        assert len(events) == 1
        assert events[0].old_status == int(CommandStatus.FULLY_OPERATIONAL)
        assert events[0].new_status == int(CommandStatus.DISRUPTED)
        assert events[0].cause == "commander_kia"

    def test_no_successor_destroys_unit(self) -> None:
        """Leaf unit with no children or siblings → DESTROYED."""
        hierarchy = HierarchyTree()
        hierarchy.add_unit("lone", EchelonLevel.COMPANY)
        task_org = TaskOrgManager(hierarchy)
        bus = EventBus()
        rng = RNGManager(42).get_stream(ModuleId.C2)
        engine = CommandEngine(hierarchy, task_org, {}, bus, rng)
        engine.register_unit("lone", "cdr_lone")

        engine.handle_commander_loss("lone", _TS)
        assert engine.get_status("lone") == CommandStatus.DESTROYED

    def test_multiple_successive_losses(self) -> None:
        """Two commander losses in quick succession."""
        engine, bus, *_ = _make_engine()
        events: list[SuccessionEvent] = []
        bus.subscribe(SuccessionEvent, events.append)

        engine.handle_commander_loss("bde1", _TS)
        assert engine.get_status("bde1") == CommandStatus.DISRUPTED

        # Another loss while still in succession
        engine.handle_commander_loss("bde1", _TS)
        # Should still be DISRUPTED (can't go lower except DESTROYED)
        assert engine.get_status("bde1") == CommandStatus.DISRUPTED
        assert len(events) == 2


class TestHQDestroyed:
    """HQ destruction is terminal."""

    def test_hq_destroyed_status(self) -> None:
        engine, *_ = _make_engine()
        engine.handle_hq_destroyed("bn1", _TS)
        assert engine.get_status("bn1") == CommandStatus.DESTROYED
        assert engine.get_effectiveness("bn1") == 0.0

    def test_hq_destroyed_publishes_event(self) -> None:
        engine, bus, *_ = _make_engine()
        events: list[CommandStatusChangeEvent] = []
        bus.subscribe(CommandStatusChangeEvent, events.append)
        engine.handle_hq_destroyed("bn1", _TS)
        assert len(events) == 1
        assert events[0].cause == "hq_destroyed"


class TestCommsLoss:
    """Communications loss degrades command."""

    def test_comms_loss_degrades(self) -> None:
        engine, *_ = _make_engine()
        engine.handle_comms_loss("bn1", _TS)
        assert engine.get_status("bn1") == CommandStatus.DEGRADED

    def test_comms_loss_twice_disrupts(self) -> None:
        engine, *_ = _make_engine()
        engine.handle_comms_loss("bn1", _TS)
        engine.handle_comms_loss("bn1", _TS)
        assert engine.get_status("bn1") == CommandStatus.DISRUPTED

    def test_comms_restored_recovers(self) -> None:
        engine, *_ = _make_engine()
        engine.handle_comms_loss("bn1", _TS)
        assert engine.get_status("bn1") == CommandStatus.DEGRADED
        engine.handle_comms_restored("bn1", _TS)
        # Remains DEGRADED until recovery timer completes
        assert engine.get_status("bn1") == CommandStatus.DEGRADED

    def test_comms_restored_from_disrupted(self) -> None:
        engine, *_ = _make_engine()
        engine.handle_comms_loss("bn1", _TS)
        engine.handle_comms_loss("bn1", _TS)
        assert engine.get_status("bn1") == CommandStatus.DISRUPTED
        engine.handle_comms_restored("bn1", _TS)
        # Should recover to DEGRADED
        assert engine.get_status("bn1") == CommandStatus.DEGRADED

    def test_comms_loss_publishes_event(self) -> None:
        engine, bus, *_ = _make_engine()
        events: list[CommandStatusChangeEvent] = []
        bus.subscribe(CommandStatusChangeEvent, events.append)
        engine.handle_comms_loss("bn1", _TS)
        assert len(events) == 1
        assert events[0].cause == "comms_loss"


class TestUpdateLoop:
    """Time advancement — succession timers and recovery."""

    def test_succession_timer_advances(self) -> None:
        engine, bus, *_ = _make_engine()
        events: list[SuccessionEvent] = []
        bus.subscribe(SuccessionEvent, events.append)

        engine.handle_commander_loss("bn1", _TS)
        delay = events[0].succession_delay_s

        # Advance half the delay — still in succession
        engine.update(delay / 2, _TS)
        assert engine.get_status("bn1") == CommandStatus.DISRUPTED

        # Advance past the rest
        engine.update(delay, _TS)
        assert engine.get_status("bn1") == CommandStatus.DEGRADED

    def test_full_recovery_after_succession(self) -> None:
        config = CommandConfig(recovery_time_s=100.0)
        engine, bus, *_ = _make_engine(config=config)
        events: list[SuccessionEvent] = []
        bus.subscribe(SuccessionEvent, events.append)

        engine.handle_commander_loss("bn1", _TS)
        delay = events[0].succession_delay_s

        # Complete succession
        engine.update(delay + 1.0, _TS)
        assert engine.get_status("bn1") == CommandStatus.DEGRADED

        # Wait for recovery
        engine.update(101.0, _TS)
        assert engine.get_status("bn1") == CommandStatus.FULLY_OPERATIONAL

    def test_recovery_blocked_by_comms_loss(self) -> None:
        config = CommandConfig(recovery_time_s=100.0)
        engine, bus, *_ = _make_engine(config=config)
        events: list[SuccessionEvent] = []
        bus.subscribe(SuccessionEvent, events.append)

        engine.handle_commander_loss("bn1", _TS)
        delay = events[0].succession_delay_s

        # Complete succession
        engine.update(delay + 1.0, _TS)
        assert engine.get_status("bn1") == CommandStatus.DEGRADED

        # Lose comms — blocks recovery
        engine.handle_comms_loss("bn1", _TS)

        # Wait long enough for recovery — but comms still lost
        engine.update(200.0, _TS)
        # Still degraded (not fully operational) because comms are lost
        assert engine.get_status("bn1") != CommandStatus.FULLY_OPERATIONAL


class TestAuthorityChecks:
    """Order authority validation."""

    def test_organic_parent_can_issue(self) -> None:
        engine, *_ = _make_engine()
        assert engine.can_issue_order("bde1", "bn1") is True

    def test_higher_echelon_can_issue(self) -> None:
        engine, *_ = _make_engine()
        assert engine.can_issue_order("div1", "bn1") is True

    def test_peer_cannot_issue(self) -> None:
        engine, *_ = _make_engine()
        assert engine.can_issue_order("bn1", "bn2") is False

    def test_subordinate_cannot_issue_to_superior(self) -> None:
        engine, *_ = _make_engine()
        assert engine.can_issue_order("bn1", "bde1") is False

    def test_destroyed_unit_cannot_issue(self) -> None:
        engine, *_ = _make_engine()
        engine.handle_hq_destroyed("bde1", _TS)
        assert engine.can_issue_order("bde1", "bn1") is False

    def test_opcon_grants_authority(self) -> None:
        engine, bus, hierarchy, task_org = _make_engine()
        task_org.attach("bn2", "bde2", CommandRelationship.OPCON)
        engine.register_unit("bde2", "cdr_bde2")
        assert engine.can_issue_order("bde2", "bn2") is True

    def test_tacon_grants_authority(self) -> None:
        engine, bus, hierarchy, task_org = _make_engine()
        task_org.attach("bn2", "bde2", CommandRelationship.TACON)
        assert engine.can_issue_order("bde2", "bn2") is True

    def test_adcon_does_not_grant_authority(self) -> None:
        engine, bus, hierarchy, task_org = _make_engine()
        task_org.attach("bn2", "bde2", CommandRelationship.ADCON)
        # ADCON parent can't issue operational orders
        assert engine.can_issue_order("bde2", "bn2") is False

    def test_unregistered_issuer_cannot_issue(self) -> None:
        engine, *_ = _make_engine()
        assert engine.can_issue_order("phantom", "bn1") is False


class TestEffectiveness:
    """Command effectiveness multipliers."""

    def test_fully_operational_effectiveness(self) -> None:
        engine, *_ = _make_engine()
        assert engine.get_effectiveness("bn1") == 1.0

    def test_degraded_effectiveness(self) -> None:
        engine, *_ = _make_engine()
        engine.handle_comms_loss("bn1", _TS)
        assert engine.get_effectiveness("bn1") == 0.6

    def test_disrupted_effectiveness(self) -> None:
        engine, *_ = _make_engine()
        engine.handle_comms_loss("bn1", _TS)
        engine.handle_comms_loss("bn1", _TS)
        assert engine.get_effectiveness("bn1") == 0.2

    def test_destroyed_effectiveness(self) -> None:
        engine, *_ = _make_engine()
        engine.handle_hq_destroyed("bn1", _TS)
        assert engine.get_effectiveness("bn1") == 0.0

    def test_custom_effectiveness_multipliers(self) -> None:
        config = CommandConfig(
            degraded_effectiveness_mult=0.7,
            disrupted_effectiveness_mult=0.3,
        )
        engine, *_ = _make_engine(config=config)
        engine.handle_comms_loss("bn1", _TS)
        assert engine.get_effectiveness("bn1") == 0.7


class TestStateProtocol:
    """Checkpoint / restore."""

    def test_get_state(self) -> None:
        engine, *_ = _make_engine()
        engine.handle_comms_loss("bn1", _TS)
        state = engine.get_state()
        assert "units" in state
        assert "bn1" in state["units"]
        assert state["units"]["bn1"]["status"] == int(CommandStatus.DEGRADED)

    def test_set_state(self) -> None:
        engine1, *_ = _make_engine(seed=42)
        engine1.handle_comms_loss("bn1", _TS)
        state = engine1.get_state()

        engine2, *_ = _make_engine(seed=42)
        engine2.set_state(state)
        assert engine2.get_status("bn1") == CommandStatus.DEGRADED
        assert engine2.get_state() == state

    def test_state_round_trip(self) -> None:
        engine, *_ = _make_engine()
        engine.handle_comms_loss("bn1", _TS)
        engine.handle_commander_loss("bde1", _TS)
        state1 = engine.get_state()

        engine2, *_ = _make_engine()
        engine2.set_state(state1)
        assert engine2.get_state() == state1


class TestDeterministicReplay:
    """Same seed → identical succession delays."""

    def test_deterministic_succession_delay(self) -> None:
        engine1, bus1, *_ = _make_engine(seed=123)
        events1: list[SuccessionEvent] = []
        bus1.subscribe(SuccessionEvent, events1.append)
        engine1.handle_commander_loss("bn1", _TS)

        engine2, bus2, *_ = _make_engine(seed=123)
        events2: list[SuccessionEvent] = []
        bus2.subscribe(SuccessionEvent, events2.append)
        engine2.handle_commander_loss("bn1", _TS)

        assert events1[0].succession_delay_s == events2[0].succession_delay_s
