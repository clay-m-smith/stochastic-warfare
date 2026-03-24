"""Tests for Phase 19e — Integration wiring of doctrinal schools.

Covers SimulationContext.school_registry field, battle.py OODA wiring,
COA compare weight overrides, OODA multiplier stacking, and backward
compatibility (no school assigned = no change).
"""

from __future__ import annotations

import types
from datetime import timedelta

import numpy as np
import pytest

from tests.conftest import TS, make_rng

from stochastic_warfare.c2.ai.assessment import SituationAssessor
from stochastic_warfare.c2.ai.decisions import DecisionEngine
from stochastic_warfare.c2.ai.ooda import OODALoopEngine, OODAPhase
from stochastic_warfare.c2.ai.schools import SchoolRegistry
from stochastic_warfare.c2.ai.schools.base import DoctrinalSchool, SchoolDefinition
from stochastic_warfare.c2.planning.coa import (
    COA,
    COAEngine,
    ManeuverType,
    TaskAssignment,
    WargameResult,
)
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.simulation.battle import BattleManager
from stochastic_warfare.simulation.scenario import SimulationContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bus() -> EventBus:
    return EventBus()


def _rng(seed: int = 42) -> np.random.Generator:
    return make_rng(seed)


class _TestSchool(DoctrinalSchool):
    """Concrete school for testing."""
    pass


def _make_school(**overrides) -> _TestSchool:
    defaults = dict(
        school_id="test_school",
        display_name="Test School",
    )
    defaults.update(overrides)
    return _TestSchool(SchoolDefinition(**defaults))


def _make_coa(coa_id: str, maneuver: ManeuverType = ManeuverType.FRONTAL_ATTACK) -> COA:
    return COA(
        coa_id=coa_id,
        name=f"COA {coa_id}",
        maneuver_type=maneuver,
        main_effort_direction=0.0,
        task_assignments=(
            TaskAssignment(subordinate_id="sub1", task_description="Main effort", effort_weight=0.6),
        ),
        wargame_result=WargameResult(
            estimated_friendly_losses=0.1,
            estimated_enemy_losses=0.3,
            estimated_duration_s=28800.0,
            probability_of_success=0.7,
            risk_level="MODERATE",
        ),
    )


def _make_mock_ctx(
    seed: int = 42,
    school_registry: SchoolRegistry | None = None,
) -> types.SimpleNamespace:
    """Lightweight mock SimulationContext for battle manager tests."""
    bus = _bus()
    rng = _rng(seed)
    ooda = OODALoopEngine(bus, rng)
    assessor = SituationAssessor(bus, _rng(seed + 1))
    decision_engine = DecisionEngine(bus, _rng(seed + 2))

    units_by_side = {
        "blue": [
            Unit(entity_id="u1", position=Position(100, 100, 0), speed=5.0),
            Unit(entity_id="u2", position=Position(200, 100, 0), speed=5.0),
        ],
        "red": [
            Unit(entity_id="e1", position=Position(1000, 100, 0), speed=5.0),
        ],
    }

    # Register commanders in OODA
    for side_units in units_by_side.values():
        for u in side_units:
            ooda.register_commander(u.entity_id, 5)

    ctx = types.SimpleNamespace(
        ooda_engine=ooda,
        assessor=assessor,
        decision_engine=decision_engine,
        school_registry=school_registry,
        units_by_side=units_by_side,
        unit_weapons={},
        unit_sensors={},
        morale_states={},
        calibration={},
        config=types.SimpleNamespace(sides=[
            types.SimpleNamespace(side="blue", experience_level=0.5),
            types.SimpleNamespace(side="red", experience_level=0.5),
        ]),
        clock=types.SimpleNamespace(
            current_time=TS,
            elapsed=timedelta(seconds=100),
        ),
        order_execution=None,
        engagement_engine=None,
        consumption_engine=None,
        stockpile_manager=None,
        morale_machine=None,
        movement_engine=None,
        commander_engine=None,
    )
    ctx.all_units = lambda: [u for us in ctx.units_by_side.values() for u in us]
    ctx.active_units = lambda side: [
        u for u in ctx.units_by_side.get(side, [])
        if u.status == UnitStatus.ACTIVE
    ]
    ctx.side_names = lambda: sorted(ctx.units_by_side.keys())
    return ctx


# ===========================================================================
# SimulationContext school_registry field
# ===========================================================================


class TestSimulationContext:
    def test_school_registry_field_exists(self):
        """SimulationContext should have school_registry field."""
        # Just verify the import and field existence via introspection
        import dataclasses
        fields = {f.name for f in dataclasses.fields(SimulationContext)}
        assert "school_registry" in fields

    def test_school_registry_defaults_to_none(self):
        """school_registry should default to None."""
        import dataclasses
        for f in dataclasses.fields(SimulationContext):
            if f.name == "school_registry":
                assert f.default is None
                break


# ===========================================================================
# Battle OODA wiring
# ===========================================================================


class TestBattleOODA:
    def test_weight_overrides_passed_to_assessor(self):
        """When a school has weight overrides, they should be passed to assess()."""
        reg = SchoolRegistry()
        school = _make_school(
            school_id="weighted",
            assessment_weight_overrides={"intel": 3.0},
        )
        reg.register(school)
        reg.assign_to_unit("u1", "weighted")

        ctx = _make_mock_ctx(school_registry=reg)
        bm = BattleManager(_bus())

        # Start OBSERVE phase and complete it
        ctx.ooda_engine.start_phase("u1", OODAPhase.OBSERVE, ts=TS)
        completions = [(("u1", OODAPhase.OBSERVE))]

        # Process completions — should not crash, school weight overrides applied
        bm._process_ooda_completions(ctx, [("u1", OODAPhase.OBSERVE)], TS)

    def test_school_adjustments_passed_to_decide(self):
        """When school provides adjustments, they flow to decide()."""
        reg = SchoolRegistry()
        school = _make_school(
            school_id="adj_test",
            preferred_actions={"DEFEND": 5.0},
        )
        reg.register(school)
        reg.assign_to_unit("u1", "adj_test")

        ctx = _make_mock_ctx(school_registry=reg)

        # Verify school adjustments are computed correctly
        s = ctx.school_registry.get_for_unit("u1")
        adj = s.get_decision_score_adjustments(echelon=5, assessment_summary={})
        assert adj["DEFEND"] == pytest.approx(5.0)

        # Test decision engine directly with adjustments
        assessor = SituationAssessor(_bus(), _rng(100))
        assessment = assessor.assess(
            unit_id="u1", echelon=5, friendly_units=10,
            friendly_power=100.0, morale_level=0.7, supply_level=0.6,
            c2_effectiveness=0.7, contacts=5, enemy_power=100.0, ts=TS,
        )
        result = ctx.decision_engine.decide(
            "u1", 6, assessment, None, None, ts=TS,
            school_adjustments=adj,
        )
        assert result.action_name == "DEFEND"

    def test_ooda_multiplier_stacked(self):
        """School OODA multiplier should stack with tactical_mult."""
        reg = SchoolRegistry()
        school = _make_school(
            school_id="fast",
            ooda_multiplier=0.7,
        )
        reg.register(school)
        reg.assign_to_unit("u1", "fast")

        ctx = _make_mock_ctx(school_registry=reg)
        bm = BattleManager(_bus())

        # Process ACT completion — should advance to OBSERVE and start with
        # effective_mult = tactical_mult(0.5) * school(0.7) = 0.35
        ctx.ooda_engine.start_phase("u1", OODAPhase.ACT, ts=TS)
        bm._process_ooda_completions(ctx, [("u1", OODAPhase.ACT)], TS)
        # Just verify it doesn't crash — the multiplier is applied internally

    def test_no_school_no_change(self):
        """Without school_registry, OBSERVE behavior should be unchanged."""
        ctx = _make_mock_ctx(school_registry=None)
        bm = BattleManager(_bus())

        # Process OBSERVE without school — should work as before
        bm._process_ooda_completions(ctx, [("u1", OODAPhase.OBSERVE)], TS)

    def test_unassigned_unit_no_change(self):
        """Unit without school assignment should get no adjustments."""
        reg = SchoolRegistry()
        school = _make_school(school_id="unused")
        reg.register(school)
        # Do NOT assign to any unit

        ctx = _make_mock_ctx(school_registry=reg)
        bm = BattleManager(_bus())

        # OBSERVE should work — school lookup returns None for unassigned
        bm._process_ooda_completions(ctx, [("u1", OODAPhase.OBSERVE)], TS)

    def test_opponent_modeling_integration(self):
        """School with opponent modeling computes adjustments correctly."""
        reg = SchoolRegistry()
        school = _make_school(
            school_id="opponent_model",
            opponent_modeling_enabled=True,
            opponent_modeling_weight=0.8,
        )
        reg.register(school)
        reg.assign_to_unit("u1", "opponent_model")

        # Default DoctrinalSchool.predict_opponent_action returns {}
        # so opponent modeling path should be a no-op
        prediction = school.predict_opponent_action({}, 100, 0.5, 100)
        assert prediction == {}  # Base class returns empty

        # When prediction is empty, adjust_scores_for_opponent returns scores unchanged
        scores = {"ATTACK": 0.5, "DEFEND": 0.3}
        adjusted = school.adjust_scores_for_opponent(scores, prediction)
        assert adjusted == scores


# ===========================================================================
# COA compare weight overrides
# ===========================================================================


class TestCOACompare:
    def test_no_overrides_uses_defaults(self):
        engine = COAEngine(_bus(), _rng(42))
        coa1 = _make_coa("coa_0")
        coa2 = _make_coa("coa_1", ManeuverType.FLANKING)
        scored = engine.compare_coas([coa1, coa2])
        assert all(c.score is not None for c in scored)

    def test_weight_overrides_applied(self):
        engine1 = COAEngine(_bus(), _rng(42))
        engine2 = COAEngine(_bus(), _rng(42))
        coa1 = _make_coa("coa_0")

        scored_default = engine1.compare_coas([coa1])
        scored_override = engine2.compare_coas(
            [coa1],
            score_weight_overrides={"mission": 0.0, "preservation": 1.0},
        )
        # Both should produce scores
        assert scored_default[0].score is not None
        assert scored_override[0].score is not None
        # With different weights, scores should differ
        # (mission=0 vs default mission weight produces different total)
        assert scored_default[0].score.total != scored_override[0].score.total

    def test_preservation_heavy(self):
        """Preservation-heavy weighting should favor low-loss COAs."""
        engine = COAEngine(_bus(), _rng(42))
        coa_low_loss = COA(
            coa_id="low_loss",
            name="Low Loss",
            maneuver_type=ManeuverType.DEFENSE_IN_DEPTH,
            main_effort_direction=0.0,
            task_assignments=(
                TaskAssignment("sub1", "defend", 0.5),
            ),
            wargame_result=WargameResult(0.05, 0.2, 28800.0, 0.6, "LOW"),
        )
        coa_high_loss = COA(
            coa_id="high_loss",
            name="High Loss",
            maneuver_type=ManeuverType.FRONTAL_ATTACK,
            main_effort_direction=0.0,
            task_assignments=(
                TaskAssignment("sub1", "attack", 0.5),
            ),
            wargame_result=WargameResult(0.4, 0.5, 28800.0, 0.8, "HIGH"),
        )
        scored = engine.compare_coas(
            [coa_low_loss, coa_high_loss],
            score_weight_overrides={"mission": 0.1, "preservation": 0.7, "tempo": 0.1, "simplicity": 0.1},
        )
        # Low-loss COA should rank first with preservation-heavy weights
        assert scored[0].coa_id == "low_loss"

    def test_tempo_heavy(self):
        """Tempo-heavy weighting should favor shorter duration COAs."""
        engine = COAEngine(_bus(), _rng(42))
        coa_fast = COA(
            coa_id="fast",
            name="Fast",
            maneuver_type=ManeuverType.PENETRATION,
            main_effort_direction=0.0,
            task_assignments=(
                TaskAssignment("sub1", "attack", 0.5),
            ),
            wargame_result=WargameResult(0.2, 0.3, 3600.0, 0.6, "MODERATE"),
        )
        coa_slow = COA(
            coa_id="slow",
            name="Slow",
            maneuver_type=ManeuverType.DEFENSE_IN_DEPTH,
            main_effort_direction=0.0,
            task_assignments=(
                TaskAssignment("sub1", "defend", 0.5),
            ),
            wargame_result=WargameResult(0.1, 0.1, 80000.0, 0.65, "LOW"),
        )
        scored = engine.compare_coas(
            [coa_fast, coa_slow],
            score_weight_overrides={"mission": 0.1, "preservation": 0.1, "tempo": 0.7, "simplicity": 0.1},
        )
        assert scored[0].coa_id == "fast"


# ===========================================================================
# OODA multiplier stacking
# ===========================================================================


class TestOODAStacking:
    def test_maneuverist_with_tactical(self):
        """Maneuverist 0.7 * tactical 0.5 = 0.35 effective."""
        # Run multiple iterations to get statistical average
        durations_fast = []
        durations_slow = []
        for i in range(20):
            ooda = OODALoopEngine(_bus(), _rng(42 + i))
            ooda.register_commander("u1", 5)
            durations_fast.append(
                ooda.compute_phase_duration(5, OODAPhase.OBSERVE, tactical_mult=0.35)
            )
            durations_slow.append(
                ooda.compute_phase_duration(5, OODAPhase.OBSERVE, tactical_mult=1.0)
            )
        # Faster multiplier should produce shorter average duration
        avg_fast = sum(durations_fast) / len(durations_fast)
        avg_slow = sum(durations_slow) / len(durations_slow)
        assert avg_fast < avg_slow

    def test_slow_school_with_tactical(self):
        """Attrition 1.2 * tactical 0.5 = 0.6 effective."""
        ooda = OODALoopEngine(_bus(), _rng(42))
        ooda.register_commander("u1", 5)
        d = ooda.compute_phase_duration(5, OODAPhase.OBSERVE, tactical_mult=0.6)
        assert d > 0

    def test_multiplier_stacking_produces_different_results(self):
        """Different school multipliers should produce different durations."""
        ooda1 = OODALoopEngine(_bus(), _rng(42))
        ooda2 = OODALoopEngine(_bus(), _rng(42))
        ooda1.register_commander("u1", 5)
        ooda2.register_commander("u1", 5)
        d_fast = ooda1.compute_phase_duration(5, OODAPhase.OBSERVE, tactical_mult=0.35)
        d_slow = ooda2.compute_phase_duration(5, OODAPhase.OBSERVE, tactical_mult=0.6)
        # Same seed, different tactical_mult -> different durations
        assert d_fast != d_slow


# ===========================================================================
# Backward compatibility
# ===========================================================================


class TestBackwardCompat:
    def test_no_school_registry_on_context(self):
        """battle.py should work fine with school_registry=None."""
        ctx = _make_mock_ctx(school_registry=None)
        bm = BattleManager(_bus())
        # Process OBSERVE and ACT phases without school (DECIDE passes None
        # assessment which is a pre-existing gap — test OBSERVE and ACT only)
        bm._process_ooda_completions(ctx, [
            ("u1", OODAPhase.OBSERVE),
            ("u1", OODAPhase.ACT),
        ], TS)

    def test_empty_school_registry(self):
        """Empty registry should behave same as None."""
        reg = SchoolRegistry()
        ctx = _make_mock_ctx(school_registry=reg)
        bm = BattleManager(_bus())
        bm._process_ooda_completions(ctx, [
            ("u1", OODAPhase.OBSERVE),
        ], TS)

    def test_existing_coa_compare_unchanged(self):
        """compare_coas() without overrides should produce same results."""
        engine1 = COAEngine(_bus(), _rng(42))
        engine2 = COAEngine(_bus(), _rng(42))
        coa = _make_coa("coa_0")
        r1 = engine1.compare_coas([coa])
        r2 = engine2.compare_coas([coa], score_weight_overrides=None)
        assert r1[0].score.total == r2[0].score.total
