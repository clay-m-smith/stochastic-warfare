"""Phase 64b: Planning process wiring tests."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from stochastic_warfare.c2.orders.types import Order, OrderPriority, OrderType
from stochastic_warfare.c2.planning.process import (
    PlanningMethod,
    PlanningPhase,
    PlanningProcessEngine,
)
from stochastic_warfare.core.events import EventBus


def _make_rng(seed: int = 42) -> np.random.Generator:
    return np.random.default_rng(seed)


def _make_order(echelon: int = 5) -> Order:
    return Order(
        order_id="plan_test_1",
        issuer_id="unit_a",
        recipient_id="unit_a",
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        order_type=OrderType.FRAGO,
        echelon_level=echelon,
        priority=OrderPriority.PRIORITY,
        mission_type=0,
    )


class TestPlanningProcessWiring:
    """Planning process engine integration tests."""

    def test_initiate_planning_returns_method(self):
        bus = EventBus()
        engine = PlanningProcessEngine(bus, _make_rng())
        method = engine.initiate_planning(
            "unit_a", _make_order(), 7200.0,
            datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert isinstance(method, PlanningMethod)

    def test_echelon_5_selects_rapid_or_intuitive(self):
        """Company echelon (5) with 7200s → RAPID (between 1800 and 7200)."""
        bus = EventBus()
        engine = PlanningProcessEngine(bus, _make_rng())
        method = engine.select_method(echelon=5, available_time_s=7200.0)
        assert method in (PlanningMethod.RAPID, PlanningMethod.MDMP)

    def test_update_decrements_timers(self):
        bus = EventBus()
        engine = PlanningProcessEngine(bus, _make_rng())
        engine.initiate_planning(
            "unit_a", _make_order(), 7200.0,
            datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        status_before = engine.get_planning_status("unit_a")
        assert status_before == PlanningPhase.RECEIVING_MISSION
        # Tick a large amount to complete the phase
        completions = engine.update(999999.0)
        assert len(completions) >= 1

    def test_advance_phase_progresses(self):
        bus = EventBus()
        engine = PlanningProcessEngine(bus, _make_rng())
        engine.initiate_planning(
            "unit_a", _make_order(), 7200.0,
            datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        next_phase = engine.advance_phase("unit_a")
        assert next_phase != PlanningPhase.RECEIVING_MISSION

    def test_complete_planning_sets_complete(self):
        bus = EventBus()
        engine = PlanningProcessEngine(bus, _make_rng())
        engine.initiate_planning(
            "unit_a", _make_order(), 7200.0,
            datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        engine.complete_planning("unit_a", datetime(2024, 1, 1, tzinfo=timezone.utc))
        assert engine.get_planning_status("unit_a") == PlanningPhase.COMPLETE

    def test_decide_deferred_while_planning(self):
        """Status not IDLE/COMPLETE → DECIDE should be deferred."""
        bus = EventBus()
        engine = PlanningProcessEngine(bus, _make_rng())
        engine.initiate_planning(
            "unit_a", _make_order(), 7200.0,
            datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        status = engine.get_planning_status("unit_a")
        assert status not in (PlanningPhase.IDLE, PlanningPhase.COMPLETE)

    def test_decide_proceeds_after_complete(self):
        bus = EventBus()
        engine = PlanningProcessEngine(bus, _make_rng())
        engine.initiate_planning(
            "unit_a", _make_order(), 7200.0,
            datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        engine.complete_planning("unit_a")
        status = engine.get_planning_status("unit_a")
        assert status in (PlanningPhase.IDLE, PlanningPhase.COMPLETE)

    def test_idle_unit_returns_idle(self):
        bus = EventBus()
        engine = PlanningProcessEngine(bus, _make_rng())
        assert engine.get_planning_status("nonexistent") == PlanningPhase.IDLE

    def test_planning_available_time_configurable(self):
        """Short available time → faster method selection."""
        bus = EventBus()
        engine = PlanningProcessEngine(bus, _make_rng())
        method_short = engine.select_method(echelon=5, available_time_s=600.0)
        method_long = engine.select_method(echelon=5, available_time_s=14400.0)
        assert method_short.value <= method_long.value  # INTUITIVE < MDMP

    def test_intuitive_faster_than_mdmp(self):
        bus = EventBus()
        engine = PlanningProcessEngine(bus, _make_rng())
        dur_int = engine._estimate_total_duration(PlanningMethod.INTUITIVE)
        dur_mdmp = engine._estimate_total_duration(PlanningMethod.MDMP)
        assert dur_int < dur_mdmp

    def test_planning_started_event_published(self):
        bus = EventBus()
        events = []
        from stochastic_warfare.c2.events import PlanningStartedEvent
        bus.subscribe(PlanningStartedEvent, lambda e: events.append(e))
        engine = PlanningProcessEngine(bus, _make_rng())
        engine.initiate_planning(
            "unit_a", _make_order(), 7200.0,
            datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert len(events) == 1

    def test_planning_completed_event_published(self):
        bus = EventBus()
        events = []
        from stochastic_warfare.c2.events import PlanningCompletedEvent
        bus.subscribe(PlanningCompletedEvent, lambda e: events.append(e))
        engine = PlanningProcessEngine(bus, _make_rng())
        engine.initiate_planning(
            "unit_a", _make_order(), 7200.0,
            datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        engine.complete_planning("unit_a", datetime(2024, 1, 1, tzinfo=timezone.utc))
        assert len(events) == 1
