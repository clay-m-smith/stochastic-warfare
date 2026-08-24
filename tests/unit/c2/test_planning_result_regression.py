"""Phase 69b — Planning result injection tests."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from stochastic_warfare.c2.planning.process import (
    PlanningPhase,
    PlanningProcessEngine,
)
from stochastic_warfare.c2.ai.ooda import OODAPhase
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.simulation.battle import BattleManager
from tests.unit.simulation._battle_feature_harness import (
    make_ooda_context,
    make_unit,
)


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


def _complete_planning(
    engine: PlanningProcessEngine,
    unit_id: str = "unit_a",
) -> None:
    engine.initiate_planning(unit_id, _make_order(unit_id), 10000.0, _TS)
    for _ in range(20):
        completions = engine.update(1000.0, _TS)
        for completed_unit_id, _phase in completions:
            next_phase = engine.advance_phase(completed_unit_id)
            if next_phase == PlanningPhase.ISSUING_ORDERS:
                engine.complete_planning(completed_unit_id, _TS)


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
    """The production OODA executor owns planning-result biasing."""

    @pytest.mark.parametrize(
        ("enabled", "with_result", "expected_attack", "result_consumed"),
        [
            (True, True, 0.4, True),
            (False, True, 0.3, False),
            (True, False, 0.3, True),
        ],
    )
    def test_executor_biases_only_an_enabled_available_result(
        self,
        enabled: bool,
        with_result: bool,
        expected_attack: float,
        result_consumed: bool,
    ) -> None:
        planning = PlanningProcessEngine(EventBus(), _rng()) if with_result else None
        if planning is not None:
            _complete_planning(planning)
        unit = make_unit("unit_a", "blue", 0.0)
        context, decisions = make_ooda_context(
            unit,
            calibration={
                "enable_c2_friction": enabled,
                "c2_min_effectiveness": 0.0,
            },
            school_adjustments={"ATTACK": 0.3, "DEFEND": 0.2},
            planning_engine=planning,
        )

        BattleManager(EventBus())._process_ooda_completions(
            context,
            [(unit.entity_id, OODAPhase.DECIDE)],
            _TS,
        )

        assert decisions.calls[0]["school_adjustments"]["ATTACK"] == pytest.approx(
            expected_attack,
        )
        if planning is not None:
            assert (planning.get_planning_result(unit.entity_id) is None) is result_consumed
