"""Phase 69b — Planning result injection tests."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from stochastic_warfare.c2.planning.process import (
    PlanningMethod,
    PlanningPhase,
    PlanningProcessEngine,
)
from stochastic_warfare.core.events import EventBus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def _rng():
    return np.random.Generator(np.random.PCG64(42))


def _make_order(unit_id="unit_a"):
    from stochastic_warfare.c2.orders.types import Order, OrderType, OrderPriority
    return Order(
        order_id=f"plan_{unit_id}",
        issuer_id=unit_id,
        recipient_id=unit_id,
        timestamp=_TS,
        order_type=OrderType.FRAGO,
        echelon_level=5,
        priority=OrderPriority.PRIORITY,
        mission_type=0,
    )


@pytest.fixture
def engine() -> PlanningProcessEngine:
    return PlanningProcessEngine(EventBus(), _rng())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGetPlanningResult:
    """Phase 69b: get_planning_result() returns posture string."""

    def test_mdmp_complete_returns_auto_coa(self, engine: PlanningProcessEngine):
        """MDMP completes → auto-generated COA is 'ATTACK'."""
        engine.initiate_planning("unit_a", _make_order(), 10000.0, _TS)
        # Fast-forward through all phases
        for _ in range(20):
            completions = engine.update(1000.0, _TS)
            for uid, phase in completions:
                next_phase = engine.advance_phase(uid)
                if next_phase == PlanningPhase.ISSUING_ORDERS:
                    engine.complete_planning(uid, _TS)

        result = engine.get_planning_result("unit_a")
        assert result == "ATTACK"

    def test_consume_result_returns_once_then_none(self, engine: PlanningProcessEngine):
        """consume_result() returns the result once, then None."""
        engine.initiate_planning("unit_a", _make_order(), 10000.0, _TS)
        # Fast-forward to completion
        for _ in range(20):
            completions = engine.update(1000.0, _TS)
            for uid, phase in completions:
                next_phase = engine.advance_phase(uid)
                if next_phase == PlanningPhase.ISSUING_ORDERS:
                    engine.complete_planning(uid, _TS)

        result1 = engine.consume_result("unit_a")
        assert result1 == "ATTACK"

        result2 = engine.consume_result("unit_a")
        assert result2 is None

    def test_not_complete_returns_none(self, engine: PlanningProcessEngine):
        """Planning not complete → get_planning_result returns None."""
        engine.initiate_planning("unit_a", _make_order(), 10000.0, _TS)
        assert engine.get_planning_result("unit_a") is None

    def test_idle_returns_none(self, engine: PlanningProcessEngine):
        """IDLE status → no result available."""
        assert engine.get_planning_result("unit_a") is None

    def test_explicit_coa_injection(self, engine: PlanningProcessEngine):
        """Explicitly set COA is returned instead of auto-generated."""
        engine.initiate_planning("unit_a", _make_order(), 10000.0, _TS)
        engine.set_selected_coa("unit_a", "DEFEND")
        # Fast-forward to completion
        for _ in range(20):
            completions = engine.update(1000.0, _TS)
            for uid, phase in completions:
                next_phase = engine.advance_phase(uid)
                if next_phase == PlanningPhase.ISSUING_ORDERS:
                    engine.complete_planning(uid, _TS)

        result = engine.get_planning_result("unit_a")
        # Explicitly set COA should be preserved (not overwritten by auto)
        assert result == "DEFEND"

    def test_auto_coa_only_when_none(self, engine: PlanningProcessEngine):
        """Auto-generate COA only when selected_coa is None."""
        engine.initiate_planning("unit_a", _make_order(), 10000.0, _TS)
        # Set a COA then clear it
        engine.set_selected_coa("unit_a", "DELAY")
        engine.set_selected_coa("unit_a", None)
        # Complete
        for _ in range(20):
            completions = engine.update(1000.0, _TS)
            for uid, phase in completions:
                next_phase = engine.advance_phase(uid)
                if next_phase == PlanningPhase.ISSUING_ORDERS:
                    engine.complete_planning(uid, _TS)
        # Should get auto-generated "ATTACK"
        result = engine.get_planning_result("unit_a")
        assert result == "ATTACK"


class TestPlanningResultBias:
    """Phase 69b: planning result biases school_adjustments."""

    def test_result_boosts_matching_posture(self):
        """consume_result returns value that would boost school_adjustments."""
        engine = PlanningProcessEngine(EventBus(), _rng())
        engine.initiate_planning("unit_a", _make_order(), 10000.0, _TS)
        for _ in range(20):
            completions = engine.update(1000.0, _TS)
            for uid, phase in completions:
                next_phase = engine.advance_phase(uid)
                if next_phase == PlanningPhase.ISSUING_ORDERS:
                    engine.complete_planning(uid, _TS)

        result = engine.consume_result("unit_a")
        assert result is not None
        # Simulate what battle.py does
        school_adjustments = {"ATTACK": 0.3, "DEFEND": 0.2}
        planning_bonus = 0.10
        school_adjustments[result] = school_adjustments.get(result, 0.0) + planning_bonus
        assert school_adjustments["ATTACK"] == pytest.approx(0.4)

    def test_no_result_no_change(self):
        """No planning result → school_adjustments unchanged."""
        engine = PlanningProcessEngine(EventBus(), _rng())
        result = engine.consume_result("unit_a")
        assert result is None
        school_adjustments = {"ATTACK": 0.3, "DEFEND": 0.2}
        # No change
        assert school_adjustments == {"ATTACK": 0.3, "DEFEND": 0.2}
