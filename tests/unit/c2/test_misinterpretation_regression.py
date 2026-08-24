"""Phase 68d: production order-misinterpretation enforcement tests."""

from __future__ import annotations

import copy
import math
from datetime import timedelta
from typing import Any

import pytest

from stochastic_warfare.c2.ai.ooda import OODAPhase
from stochastic_warfare.c2.orders.propagation import PropagationResult
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.simulation.battle import BattleContext, BattleManager
from stochastic_warfare.simulation.calibration import CalibrationSchema
from tests.unit.simulation._battle_feature_harness import (
    TS,
    make_ooda_context,
    make_unit,
)


class _FixedPropagation:
    """Return one typed result while recording production propagation calls."""

    def __init__(self, result: PropagationResult) -> None:
        self.result = result
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def propagate_order(self, *args: Any, **kwargs: Any) -> PropagationResult:
        self.calls.append((args, kwargs))
        return copy.deepcopy(self.result)


def _result(kind: str, *, delay_s: float = 0.0) -> PropagationResult:
    return PropagationResult(
        success=True,
        total_delay_s=delay_s,
        was_misinterpreted=True,
        misinterpretation_type=kind,
        comms_quality=0.5,
        degraded=True,
    )


def _execute(
    kind: str,
    *,
    adjustments: dict[str, float] | None = None,
    delay_s: float = 0.0,
    seed: int = 42,
) -> tuple[BattleManager, Any, Any, _FixedPropagation, BattleContext]:
    unit = make_unit("u1", "blue", 1_000.0, northing=2_000.0)
    propagation = _FixedPropagation(_result(kind, delay_s=delay_s))
    context, decisions = make_ooda_context(
        unit,
        calibration={
            "enable_c2_friction": True,
            "c2_min_effectiveness": 0.0,
            "misinterpretation_radius_m": 500.0,
        },
        school_adjustments=(
            {"ATTACK": 0.5, "DEFEND": 0.1}
            if adjustments is None
            else adjustments
        ),
        order_propagation=propagation,
        seed=seed,
    )
    battle = BattleContext(
        battle_id="battle_0000",
        start_tick=0,
        start_time=TS,
        involved_sides=["blue", "red"],
        unit_ids={unit.entity_id},
    )
    manager = BattleManager(EventBus())
    manager._battles[battle.battle_id] = battle
    manager._next_battle_id = 1
    manager._process_ooda_completions(
        context,
        [(unit.entity_id, OODAPhase.DECIDE)],
        TS,
        battle=battle,
    )
    return manager, context, decisions, propagation, battle


class TestProductionMisinterpretation:
    """BattleManager applies typed propagation effects exactly once."""

    def test_unit_designation_skips_the_recorded_decision(self) -> None:
        manager, _context, decisions, propagation, _battle = _execute(
            "unit_designation",
        )

        assert len(propagation.calls) == 1
        assert decisions.calls == []
        assert manager.deferred_ooda_decisions == ()

    @pytest.mark.parametrize(
        ("adjustments", "expected"),
        [
            (
                {"ATTACK": 0.5, "DEFEND": 0.1},
                {"ATTACK": 0.1, "DEFEND": 0.5},
            ),
            (
                {"WITHDRAW": 0.3},
                {"WITHDRAW": 0.3, "ATTACK": 0.0, "DEFEND": 0.0},
            ),
        ],
    )
    def test_objective_swaps_attack_and_defend_on_the_real_decision_path(
        self,
        adjustments: dict[str, float],
        expected: dict[str, float],
    ) -> None:
        _manager, _context, decisions, propagation, _battle = _execute(
            "objective",
            adjustments=adjustments,
        )

        assert len(propagation.calls) == 1
        assert [call["school_adjustments"] for call in decisions.calls] == [
            expected,
        ]

    def test_position_offset_uses_manager_rng_deterministically(self) -> None:
        first = _execute("position", seed=68)
        second = _execute("position", seed=68)
        first_context, first_decisions = first[1], first[2]
        second_context, second_decisions = second[1], second[2]
        first_position = first_context.units_by_side["blue"][0].position
        second_position = second_context.units_by_side["blue"][0].position

        assert math.hypot(
            first_position.easting - 1_000.0,
            first_position.northing - 2_000.0,
        ) == pytest.approx(500.0)
        assert first_position == second_position
        assert [call["unit_id"] for call in first_decisions.calls] == ["u1"]
        assert [call["unit_id"] for call in second_decisions.calls] == ["u1"]
        assert (
            first_context.rng_manager.get_stream(ModuleId.C2).random()
            == second_context.rng_manager.get_stream(ModuleId.C2).random()
        )

    def test_timing_delay_has_closed_boundary_and_checkpoint_continuation(
        self,
    ) -> None:
        manager, _context, decisions, propagation, _battle = _execute(
            "timing",
            delay_s=30.0,
        )
        assert decisions.calls == []
        assert len(propagation.calls) == 1
        assert manager.get_state()["pending_decisions"] == {"u1": 60.0}

        restored = BattleManager(EventBus())
        restored.set_state(copy.deepcopy(manager.get_state()))
        restored_battle = restored._battles["battle_0000"]
        restored_unit = make_unit("u1", "blue", 1_000.0, northing=2_000.0)
        unused_propagation = _FixedPropagation(_result("position"))
        restored_context, restored_decisions = make_ooda_context(
            restored_unit,
            calibration={
                "enable_c2_friction": True,
                "c2_min_effectiveness": 0.0,
            },
            school_adjustments={"ATTACK": 0.5, "DEFEND": 0.1},
            order_propagation=unused_propagation,
            seed=99,
        )
        restored_context.clock.set_tick_duration(timedelta(seconds=59.0))
        restored_context.clock.advance()
        restored._process_ooda_completions(
            restored_context,
            [("u1", OODAPhase.DECIDE)],
            restored_context.clock.current_time,
            battle=restored_battle,
        )
        assert restored_decisions.calls == []
        assert restored.get_state()["pending_decisions"] == {"u1": 60.0}

        restored_context.clock.set_tick_duration(timedelta(seconds=1.0))
        restored_context.clock.advance()
        restored._process_ooda_completions(
            restored_context,
            [("u1", OODAPhase.DECIDE)],
            restored_context.clock.current_time,
            battle=restored_battle,
        )

        assert [call["unit_id"] for call in restored_decisions.calls] == ["u1"]
        assert unused_propagation.calls == []
        assert restored.deferred_ooda_decisions == ()


class TestMisinterpretationCalibration:
    """Direct schema obligations remain source-local."""

    def test_radius_field(self) -> None:
        schema = CalibrationSchema(misinterpretation_radius_m=1000.0)
        assert schema.misinterpretation_radius_m == 1000.0
        assert CalibrationSchema().misinterpretation_radius_m == 500.0

    def test_base_rate_configurable(self) -> None:
        schema = CalibrationSchema(order_misinterpretation_base=0.1)
        assert schema.order_misinterpretation_base == 0.1

    def test_default_base_rate(self) -> None:
        assert CalibrationSchema().order_misinterpretation_base == 0.05
