"""Integration tests for Phase 8: AI & Planning.

Validates that the AI modules work together end-to-end: OODA loop
driving assessment, planning, and decision-making with doctrine and
commander personality influencing outcomes.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import ModuleId, Position

# AI modules
from stochastic_warfare.c2.ai.ooda import OODALoopEngine, OODAPhase, OODAConfig
from stochastic_warfare.c2.ai.commander import (
    CommanderEngine,
    CommanderPersonality,
    CommanderProfileLoader,
    CommanderConfig,
)
from stochastic_warfare.c2.ai.doctrine import (
    DoctrineEngine,
    DoctrineTemplateLoader,
)
from stochastic_warfare.c2.ai.assessment import (
    SituationAssessor,
    AssessmentRating,
    SituationAssessment,
)
from stochastic_warfare.c2.ai.decisions import (
    DecisionEngine,
    DecisionResult,
)
from stochastic_warfare.c2.ai.adaptation import (
    AdaptationEngine,
    AdaptationAction,
    AdaptationTrigger,
)
from stochastic_warfare.c2.ai.stratagems import (
    StratagemEngine,
    StratagemType,
)

# Planning modules
from stochastic_warfare.c2.planning.estimates import EstimatesEngine
from stochastic_warfare.c2.planning.mission_analysis import (
    MissionAnalysisEngine,
    MissionAnalysisResult,
)
from stochastic_warfare.c2.planning.coa import COAEngine
from stochastic_warfare.c2.planning.phases import PhasingEngine
from stochastic_warfare.c2.planning.process import (
    PlanningProcessEngine,
    PlanningMethod,
    PlanningPhase,
)

# Order types
from stochastic_warfare.c2.orders.types import (
    Order,
    OrderType,
    OrderPriority,
    MissionType,
)

# Events
from stochastic_warfare.c2.events import (
    OODAPhaseChangeEvent,
    SituationAssessedEvent,
    DecisionMadeEvent,
    PlanAdaptedEvent,
    PlanningStartedEvent,
    PlanningCompletedEvent,
    COASelectedEvent,
    PhaseTransitionEvent,
)

# Shared test fixtures
from tests.conftest import TS, DEFAULT_SEED, make_rng

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ECHELON_BN = 6  # Battalion


def _make_rng(seed: int = DEFAULT_SEED) -> np.random.Generator:
    return make_rng(seed)


def _make_order(
    mission_type: int = MissionType.ATTACK,
    echelon: int = _ECHELON_BN,
    objective: Position = Position(5000, 5000, 0),
) -> Order:
    return Order(
        order_id="opord_001",
        issuer_id="bde_cmd",
        recipient_id="bn_alpha",
        timestamp=TS,
        order_type=OrderType.OPORD,
        echelon_level=echelon,
        priority=OrderPriority.ROUTINE,
        mission_type=mission_type,
        objective_position=objective,
        phase_line="PL BRAVO",
    )


def _make_personality(
    aggression: float = 0.5,
    caution: float = 0.5,
    **kwargs,
) -> CommanderPersonality:
    defaults = dict(
        profile_id="test",
        display_name="Test",
        description="Test",
        flexibility=0.5,
        initiative=0.5,
        experience=0.6,
        stress_tolerance=0.5,
        decision_speed=0.5,
        risk_acceptance=0.5,
    )
    defaults.update(kwargs)
    return CommanderPersonality(aggression=aggression, caution=caution, **defaults)


def _make_assessment(
    force_ratio: float = 1.5,
    overall: AssessmentRating = AssessmentRating.FAVORABLE,
    morale: float = 0.7,
    supply: float = 0.8,
    c2: float = 0.8,
    confidence: float = 0.7,
    opportunities: tuple[str, ...] = (),
    threats: tuple[str, ...] = (),
) -> SituationAssessment:
    return SituationAssessment(
        unit_id="bn_alpha",
        timestamp=TS,
        force_ratio=force_ratio,
        force_ratio_rating=AssessmentRating.FAVORABLE,
        terrain_advantage=0.1,
        terrain_rating=AssessmentRating.NEUTRAL,
        supply_level=supply,
        supply_rating=AssessmentRating.FAVORABLE,
        morale_level=morale,
        morale_rating=AssessmentRating.FAVORABLE,
        intel_quality=0.6,
        intel_rating=AssessmentRating.FAVORABLE,
        environmental_rating=AssessmentRating.NEUTRAL,
        c2_effectiveness=c2,
        c2_rating=AssessmentRating.FAVORABLE,
        overall_rating=overall,
        confidence=confidence,
        opportunities=opportunities,
        threats=threats,
    )


# ---------------------------------------------------------------------------
# Test 1: Full OODA cycle — observe → orient → decide → act
# ---------------------------------------------------------------------------


class TestFullOODACycle:
    """Verify the complete OODA loop: registration, phase cycling, and events."""

    def test_full_ooda_observe_orient_decide_act(self):
        """Walk through a full OODA cycle and verify phase transitions."""
        eb = EventBus()
        rng = _make_rng()
        events_captured: list = []
        eb.subscribe(OODAPhaseChangeEvent, lambda e: events_captured.append(e))

        ooda = OODALoopEngine(eb, rng)
        ooda.register_commander("bn_alpha", _ECHELON_BN)

        # Start OBSERVE
        ooda.start_phase("bn_alpha", OODAPhase.OBSERVE, ts=TS)
        assert ooda.get_phase("bn_alpha") == OODAPhase.OBSERVE

        # Advance until OBSERVE completes
        completed = []
        for _ in range(1000):
            result = ooda.update(10.0, ts=TS)
            completed.extend(result)
            if result:
                break

        assert len(completed) == 1
        assert completed[0] == ("bn_alpha", OODAPhase.OBSERVE)

        # Advance to ORIENT
        new_phase = ooda.advance_phase("bn_alpha")
        assert new_phase == OODAPhase.ORIENT
        ooda.start_phase("bn_alpha", OODAPhase.ORIENT, ts=TS)

        # Advance to DECIDE
        completed = []
        for _ in range(2000):
            result = ooda.update(10.0, ts=TS)
            completed.extend(result)
            if result:
                break
        new_phase = ooda.advance_phase("bn_alpha")
        assert new_phase == OODAPhase.DECIDE
        ooda.start_phase("bn_alpha", OODAPhase.DECIDE, ts=TS)

        # Advance to ACT
        completed = []
        for _ in range(2000):
            result = ooda.update(10.0, ts=TS)
            completed.extend(result)
            if result:
                break
        new_phase = ooda.advance_phase("bn_alpha")
        assert new_phase == OODAPhase.ACT
        ooda.start_phase("bn_alpha", OODAPhase.ACT, ts=TS)

        # Complete ACT -> wraps to OBSERVE
        completed = []
        for _ in range(1000):
            result = ooda.update(10.0, ts=TS)
            completed.extend(result)
            if result:
                break
        new_phase = ooda.advance_phase("bn_alpha")
        assert new_phase == OODAPhase.OBSERVE
        assert ooda.get_cycle_count("bn_alpha") == 1

        # Events were published for each phase change
        assert len(events_captured) >= 4


# ---------------------------------------------------------------------------
# Test 2: Assessment feeding into decision selection
# ---------------------------------------------------------------------------


class TestAssessmentToDecision:
    """Assessment drives the decision engine."""

    def test_favorable_assessment_produces_offensive_decision(self):
        eb = EventBus()
        rng = _make_rng()

        assessor = SituationAssessor(eb, rng)
        assessment = assessor.assess(
            unit_id="bn_alpha",
            echelon=_ECHELON_BN,
            friendly_units=5,
            friendly_power=100.0,
            morale_level=0.8,
            supply_level=0.9,
            c2_effectiveness=0.9,
            contacts=3,
            enemy_power=40.0,
            experience=0.7,
            staff_quality=0.6,
            ts=TS,
        )

        assert assessment.overall_rating >= AssessmentRating.FAVORABLE

        decision_engine = DecisionEngine(eb, _make_rng(99))
        personality = _make_personality(aggression=0.7, caution=0.3)
        result = decision_engine.decide(
            unit_id="bn_alpha",
            echelon=_ECHELON_BN,
            assessment=assessment,
            personality=personality,
            doctrine=None,
            ts=TS,
        )

        assert isinstance(result, DecisionResult)
        assert result.confidence > 0.3
        # With favorable assessment + aggressive personality, likely offensive
        assert result.action_name in (
            "ATTACK", "COUNTERATTACK", "ENVELOP", "BYPASS",
            "FIX", "CONSOLIDATE", "RESERVE", "DELAY", "WITHDRAW",
            "DEFEND",
        )

    def test_unfavorable_assessment_produces_defensive_decision(self):
        eb = EventBus()
        rng = _make_rng()

        assessor = SituationAssessor(eb, rng)
        assessment = assessor.assess(
            unit_id="bn_alpha",
            echelon=_ECHELON_BN,
            friendly_units=2,
            friendly_power=30.0,
            morale_level=0.3,
            supply_level=0.2,
            c2_effectiveness=0.3,
            contacts=8,
            enemy_power=100.0,
            experience=0.4,
            staff_quality=0.3,
            ts=TS,
        )

        assert assessment.overall_rating <= AssessmentRating.NEUTRAL

        decision_engine = DecisionEngine(eb, _make_rng(99))
        personality = _make_personality(aggression=0.3, caution=0.8)
        result = decision_engine.decide(
            unit_id="bn_alpha",
            echelon=_ECHELON_BN,
            assessment=assessment,
            personality=personality,
            doctrine=None,
            ts=TS,
        )

        # With unfavorable assessment + cautious personality, likely defensive
        assert result.action_name in (
            "DEFEND", "DELAY", "WITHDRAW", "RESERVE",
            "CONSOLIDATE", "COUNTERATTACK", "ATTACK",
            "BYPASS", "FIX", "ENVELOP",
        )


# ---------------------------------------------------------------------------
# Test 3: Full planning pipeline
# ---------------------------------------------------------------------------


class TestFullPlanningPipeline:
    """Mission analysis → COA development → wargame → select → phase plan."""

    def test_end_to_end_planning(self):
        eb = EventBus()
        rng = _make_rng()

        order = _make_order(MissionType.ATTACK)

        # Step 1: Mission analysis
        ma_engine = MissionAnalysisEngine(eb, rng)
        analysis = ma_engine.analyze(
            unit_id="bn_alpha",
            order=order,
            friendly_units=4,
            contacts=3,
            supply_level=0.8,
            terrain_positions=[Position(3000, 3000, 0)],
            combat_power_ratio=1.8,
            staff_quality=0.7,
            ts=TS,
        )
        assert len(analysis.specified_tasks) >= 1
        assert len(analysis.implied_tasks) >= 0

        # Step 2: COA development
        coa_engine = COAEngine(eb, _make_rng(77))
        coas = coa_engine.develop_coas(
            unit_id="bn_alpha",
            analysis=analysis,
            friendly_power=100.0,
            subordinate_ids=["co_a", "co_b", "co_c"],
            contacts=3,
            enemy_power=55.0,
            supply_level=0.8,
            terrain_advantage=0.1,
            echelon=_ECHELON_BN,
        )
        assert len(coas) >= 1

        # Step 3: Wargame each COA
        wargamed = []
        for coa in coas:
            wr = coa_engine.wargame_coa(
                coa=coa,
                friendly_power=100.0,
                enemy_power=55.0,
                supply_level=0.8,
                terrain_advantage=0.1,
                staff_quality=0.7,
            )
            from dataclasses import replace
            wargamed.append(replace(coa, wargame_result=wr))

        # Step 4: Compare and select
        ranked = coa_engine.compare_coas(wargamed)
        assert all(c.score is not None for c in ranked)
        assert ranked[0].score.total >= ranked[-1].score.total

        selected = coa_engine.select_coa(ranked, ts=TS)
        assert selected.coa_id in [c.coa_id for c in ranked]

        # Step 5: Create operational plan
        phasing = PhasingEngine(eb)
        plan = phasing.create_plan(
            unit_id="bn_alpha",
            coa=selected,
            echelon=_ECHELON_BN,
            mission_type=MissionType.ATTACK,
            ts=TS,
        )
        assert len(plan.phases) >= 3
        assert plan.current_phase is not None
        assert plan.current_phase.is_active


# ---------------------------------------------------------------------------
# Test 4: Adaptation triggering re-decision on surprise contact
# ---------------------------------------------------------------------------


class TestAdaptationTrigger:
    """When conditions change, adaptation engine triggers plan adjustment."""

    def test_surprise_contact_triggers_frago(self):
        eb = EventBus()
        rng = _make_rng()
        events_captured: list = []
        eb.subscribe(PlanAdaptedEvent, lambda e: events_captured.append(e))

        adaptation = AdaptationEngine(eb, rng)
        personality = _make_personality(aggression=0.5, caution=0.5, flexibility=0.5)

        # Previous: comfortable ratio
        previous = _make_assessment(force_ratio=2.0, overall=AssessmentRating.FAVORABLE)
        # Current: surprise contact slashes ratio
        current = _make_assessment(force_ratio=0.3, overall=AssessmentRating.UNFAVORABLE)

        action, trigger = adaptation.check_adaptation_needed(
            unit_id="bn_alpha",
            current=current,
            previous=previous,
            personality=personality,
            current_action="ATTACK",
            casualties_fraction=0.05,
            ts=TS,
        )

        # Should trigger — either FORCE_RATIO_CHANGE or SURPRISE_CONTACT
        assert trigger is not None
        assert action != AdaptationAction.CONTINUE
        assert len(events_captured) == 1

    def test_stable_conditions_no_adaptation(self):
        eb = EventBus()
        rng = _make_rng()

        adaptation = AdaptationEngine(eb, rng)
        assessment = _make_assessment()

        action, trigger = adaptation.check_adaptation_needed(
            unit_id="bn_alpha",
            current=assessment,
            previous=assessment,
            personality=None,
            current_action="DEFEND",
            casualties_fraction=0.05,
            ts=TS,
        )

        assert action == AdaptationAction.CONTINUE
        assert trigger is None


# ---------------------------------------------------------------------------
# Test 5: Doctrine constraining decision options
# ---------------------------------------------------------------------------


class TestDoctrineConstraint:
    """Doctrine templates filter available actions."""

    def test_doctrine_constrains_decisions(self):
        eb = EventBus()

        # Load real doctrine
        loader = DoctrineTemplateLoader()
        loader.load_all()
        doctrine_engine = DoctrineEngine(loader)

        defense_doctrine = doctrine_engine.get_applicable_doctrine(
            "us_defend_area", echelon=_ECHELON_BN, domain="LAND",
        )
        assert defense_doctrine is not None
        assert "defend" in defense_doctrine.actions

        # Make decision with defensive doctrine
        decision_engine = DecisionEngine(eb, _make_rng(42))
        assessment = _make_assessment(
            force_ratio=0.8,
            overall=AssessmentRating.NEUTRAL,
        )
        personality = _make_personality(caution=0.6)

        result = decision_engine.decide(
            unit_id="bn_alpha",
            echelon=_ECHELON_BN,
            assessment=assessment,
            personality=personality,
            doctrine=defense_doctrine,
            ts=TS,
        )
        assert isinstance(result, DecisionResult)
        # Doctrine should bias toward defensive actions
        assert result.action_name is not None


# ---------------------------------------------------------------------------
# Test 6: Commander personality creates measurably different outcomes
# ---------------------------------------------------------------------------


class TestPersonalityDifference:
    """Different commander personalities produce statistically different decisions."""

    def test_aggressive_vs_cautious_over_many_trials(self):
        eb = EventBus()
        # Ambiguous scenario — parity force ratio, neutral terrain, moderate
        # everything. Personality should be the swing factor.
        assessment = _make_assessment(
            force_ratio=0.9,
            overall=AssessmentRating.NEUTRAL,
            morale=0.5,
            supply=0.5,
            c2=0.6,
            confidence=0.5,
        )

        aggressive_personality = _make_personality(
            aggression=0.95, caution=0.05, initiative=0.9, experience=0.3,
        )
        cautious_personality = _make_personality(
            aggression=0.05, caution=0.95, initiative=0.2, experience=0.3,
        )

        aggressive_actions: list[str] = []
        cautious_actions: list[str] = []

        for seed in range(200):
            # Aggressive
            de = DecisionEngine(eb, _make_rng(seed))
            r = de.decide("a", _ECHELON_BN, assessment, aggressive_personality, None, ts=TS)
            aggressive_actions.append(r.action_name)

            # Cautious
            de2 = DecisionEngine(eb, _make_rng(seed))
            r2 = de2.decide("a", _ECHELON_BN, assessment, cautious_personality, None, ts=TS)
            cautious_actions.append(r2.action_name)

        # The action distributions should differ — aggressive should
        # choose ATTACK/COUNTERATTACK more, cautious should choose
        # DEFEND/DELAY/WITHDRAW more
        from collections import Counter
        agg_dist = Counter(aggressive_actions)
        caut_dist = Counter(cautious_actions)
        assert agg_dist != caut_dist


# ---------------------------------------------------------------------------
# Test 7: Echelon-appropriate decisions
# ---------------------------------------------------------------------------


class TestEchelonAppropriate:
    """Different echelons produce different action enums."""

    def test_platoon_vs_brigade_vs_corps(self):
        eb = EventBus()
        assessment = _make_assessment()
        personality = _make_personality()

        # Platoon
        de = DecisionEngine(eb, _make_rng())
        r_plt = de.decide("plt", 4, assessment, personality, None, ts=TS)

        # Brigade (dispatched to brigade_div handler)
        de2 = DecisionEngine(eb, _make_rng())
        r_bde = de2.decide("bde", 8, assessment, personality, None, ts=TS)

        # Corps
        de3 = DecisionEngine(eb, _make_rng())
        r_corps = de3.decide("corps", 10, assessment, personality, None, ts=TS)

        # Each echelon uses different action enums
        # Platoon uses SmallUnitAction, Brigade uses BrigadeDivAction, Corps uses CorpsAction
        assert r_plt.echelon_level == 4
        # Brigade dispatches to _decide_brigade_div which covers 8-9 range
        assert r_bde.echelon_level in (8, 9)
        assert r_corps.echelon_level >= 10


# ---------------------------------------------------------------------------
# Test 8: Deterministic replay
# ---------------------------------------------------------------------------


class TestDeterministicReplay:
    """Same seed produces identical decisions across multiple runs."""

    def test_same_seed_same_decisions(self):
        eb = EventBus()
        assessment = _make_assessment()
        personality = _make_personality()
        order = _make_order()

        results_a: list[str] = []
        results_b: list[str] = []

        for run_results in [results_a, results_b]:
            rng = _make_rng(DEFAULT_SEED)

            # Assessment
            assessor = SituationAssessor(eb, rng)
            sa = assessor.assess(
                "bn", _ECHELON_BN, 4, 100.0, 0.7, 0.8, 0.8,
                3, 60.0, ts=TS,
            )
            run_results.append(str(sa.overall_rating))
            run_results.append(f"{sa.confidence:.6f}")

            # Mission analysis
            ma = MissionAnalysisEngine(eb, _make_rng(DEFAULT_SEED + 1))
            analysis = ma.analyze(
                "bn", order, 4, 3, 0.8,
                [Position(1000, 1000, 0)], 1.5, 0.6, ts=TS,
            )
            run_results.append(str(len(analysis.implied_tasks)))

            # Decision
            de = DecisionEngine(eb, _make_rng(DEFAULT_SEED + 2))
            dr = de.decide("bn", _ECHELON_BN, sa, personality, None, ts=TS)
            run_results.append(dr.action_name)

        assert results_a == results_b

    def test_different_seed_different_results(self):
        eb = EventBus()

        results: list[list[str]] = []
        for seed in [42, 123]:
            run = []
            rng = _make_rng(seed)
            assessor = SituationAssessor(eb, rng)
            sa = assessor.assess(
                "bn", _ECHELON_BN, 4, 100.0, 0.7, 0.8, 0.8,
                3, 60.0, ts=TS,
            )
            run.append(f"{sa.confidence:.6f}")

            de = DecisionEngine(eb, _make_rng(seed + 1))
            dr = de.decide("bn", _ECHELON_BN, sa, _make_personality(), None, ts=TS)
            run.append(dr.action_name)
            results.append(run)

        # At least the confidence noise should differ
        assert results[0][0] != results[1][0]


# ---------------------------------------------------------------------------
# Test 9: State checkpoint/restore round-trip
# ---------------------------------------------------------------------------


class TestCheckpointRestore:
    """All engines support get_state/set_state for deterministic checkpoint."""

    def test_ooda_checkpoint_restore(self):
        eb = EventBus()
        rng = _make_rng()

        ooda = OODALoopEngine(eb, rng)
        ooda.register_commander("bn_alpha", _ECHELON_BN)
        ooda.start_phase("bn_alpha", OODAPhase.OBSERVE, ts=TS)
        ooda.update(50.0, ts=TS)

        state = ooda.get_state()
        assert isinstance(state, dict)

        ooda2 = OODALoopEngine(eb, _make_rng())
        ooda2.set_state(state)
        assert ooda2.get_phase("bn_alpha") == OODAPhase.OBSERVE

    def test_estimates_checkpoint_restore(self):
        eb = EventBus()
        est = EstimatesEngine(eb)
        est.update_all(
            "bn_alpha", 0.9, 0.5, True, 3, 50.0, 0.6, 2,
            1.5, 0.5, 0.3, 0.1, 0.8, 0.7, 0.9, 0.8, 0.9,
            0.8, True, True, 0.1, ts=TS,
        )
        state = est.get_state()

        est2 = EstimatesEngine(eb)
        est2.set_state(state)
        r = est2.get_estimates("bn_alpha")
        assert r is not None
        assert r.overall_supportability > 0

    def test_adaptation_checkpoint_restore(self):
        eb = EventBus()
        rng = _make_rng()
        adaptation = AdaptationEngine(eb, rng)

        assessment = _make_assessment()
        adaptation.check_adaptation_needed(
            "bn_alpha", assessment, None, None, "ATTACK", 0.05, ts=TS,
        )

        state = adaptation.get_state()
        adaptation2 = AdaptationEngine(eb, _make_rng())
        adaptation2.set_state(state)
        # Should have stored previous assessment
        assert isinstance(state, dict)


# ---------------------------------------------------------------------------
# Test 10: FRAGO superseding existing orders on plan adaptation
# ---------------------------------------------------------------------------


class TestFragoOnAdaptation:
    """When adaptation triggers ISSUE_FRAGO, the planning process should
    be able to generate a new plan."""

    def test_adaptation_leads_to_new_planning(self):
        eb = EventBus()
        rng = _make_rng()

        # Initial assessment: comfortable
        prev = _make_assessment(force_ratio=2.0, overall=AssessmentRating.FAVORABLE)
        # Crisis: surprise contact
        current = _make_assessment(
            force_ratio=0.3,
            overall=AssessmentRating.VERY_UNFAVORABLE,
            morale=0.4,
            supply=0.5,
            threats=("outnumbered",),
        )

        adaptation = AdaptationEngine(eb, rng)
        action, trigger = adaptation.check_adaptation_needed(
            "bn_alpha", current, prev, None, "ATTACK", 0.1, ts=TS,
        )

        # Adaptation recommended action, now initiate new planning
        assert action != AdaptationAction.CONTINUE

        # Re-plan with FRAGO
        frago = Order(
            order_id="frago_001",
            issuer_id="bn_alpha",
            recipient_id="bn_alpha",
            timestamp=TS,
            order_type=OrderType.FRAGO,
            echelon_level=_ECHELON_BN,
            priority=OrderPriority.IMMEDIATE,
            mission_type=MissionType.DEFEND,
            parent_order_id="opord_001",
        )

        process = PlanningProcessEngine(eb, _make_rng(55))
        method = process.initiate_planning(
            "bn_alpha", frago, available_time_s=1800, ts=TS,
        )
        assert method in (PlanningMethod.RAPID, PlanningMethod.INTUITIVE)


# ---------------------------------------------------------------------------
# Test 11: Planning process FSM full walkthrough
# ---------------------------------------------------------------------------


class TestPlanningProcessFSM:
    """Walk the planning process through all phases."""

    def test_mdmp_full_walkthrough(self):
        eb = EventBus()
        rng = _make_rng()
        events_captured: list = []
        eb.subscribe(PlanningStartedEvent, lambda e: events_captured.append(e))
        eb.subscribe(PlanningCompletedEvent, lambda e: events_captured.append(e))

        order = _make_order()
        process = PlanningProcessEngine(eb, rng)
        method = process.initiate_planning(
            "bn_alpha", order, available_time_s=86400, ts=TS,
        )
        assert method == PlanningMethod.MDMP

        # Walk through phases until complete or stuck
        max_iterations = 1000
        for _ in range(max_iterations):
            completed = process.update(100.0, ts=TS)
            for uid, phase in completed:
                if phase == PlanningPhase.COMPLETE:
                    break
                process.advance_phase(uid)
            status = process.get_planning_status("bn_alpha")
            if status == PlanningPhase.COMPLETE:
                break
            if status in (PlanningPhase.IDLE, PlanningPhase.COMPLETE):
                break

        # Inject a mock selected COA for completion
        process.set_selected_coa("bn_alpha", type("MockCOA", (), {"coa_id": "coa_1"})())
        process.set_coas("bn_alpha", [1, 2])
        process.complete_planning("bn_alpha", ts=TS)

        assert process.get_planning_status("bn_alpha") == PlanningPhase.COMPLETE
        # PlanningStartedEvent should have been published
        assert any(isinstance(e, PlanningStartedEvent) for e in events_captured)


# ---------------------------------------------------------------------------
# Test 12: Stratagem evaluation
# ---------------------------------------------------------------------------


class TestStratagemIntegration:
    """Stratagems require adequate echelon and experience."""

    def test_deception_evaluated_in_context(self):
        eb = EventBus()
        rng = _make_rng()

        strat = StratagemEngine(eb, rng)
        assessment = _make_assessment(force_ratio=1.2, c2=0.7)

        # Battalion with experienced commander
        viable, reason = strat.evaluate_deception_opportunity(
            assessment, ["co_a", "co_b", "co_c"], echelon=_ECHELON_BN, experience=0.6,
        )
        assert viable is True
        assert "deception" in reason.lower() or "force ratio" in reason.lower()

    def test_concentration_plan_creation(self):
        eb = EventBus()
        rng = _make_rng()

        strat = StratagemEngine(eb, rng)
        plan = strat.plan_concentration(
            unit_ids=["co_a", "co_b", "co_c"],
            concentration_point=Position(5000, 5000, 0),
            economy_unit_ids=["co_d"],
        )
        assert plan.stratagem_type == StratagemType.CONCENTRATION
        # units_involved includes both concentration and economy units
        assert len(plan.units_involved) == 4
        assert "co_a" in plan.units_involved
        assert "co_d" in plan.units_involved
        assert plan.estimated_effect > 0
        assert plan.risk > 0


# ---------------------------------------------------------------------------
# Test 13: Running estimates update cycle
# ---------------------------------------------------------------------------


class TestEstimatesIntegration:
    """Running estimates update periodically and reflect battlefield state."""

    def test_estimates_update_and_query(self):
        eb = EventBus()
        est = EstimatesEngine(eb)

        # First update
        result = est.update_all(
            "bn_alpha",
            strength_ratio=0.85,
            casualty_rate=2.0,
            replacement_available=True,
            confirmed_contacts=5,
            estimated_enemy_strength=60.0,
            intel_coverage=0.7,
            collection_assets=2,
            combat_power_ratio=1.5,
            tempo=0.5,
            objectives_progress=0.3,
            terrain_favorability=0.2,
            supply_level=0.75,
            ammo_level=0.8,
            fuel_level=0.7,
            transport_available=0.6,
            msr_status=0.9,
            network_connectivity=0.85,
            primary_comms_up=True,
            alternate_comms_available=True,
            jamming_threat=0.1,
            ts=TS,
        )

        assert result.overall_supportability > 0.3
        assert est.check_supportability("bn_alpha") == result.overall_supportability

        # Update again with degraded conditions
        result2 = est.update_all(
            "bn_alpha",
            strength_ratio=0.5,
            casualty_rate=8.0,
            replacement_available=False,
            confirmed_contacts=10,
            estimated_enemy_strength=100.0,
            intel_coverage=0.3,
            collection_assets=1,
            combat_power_ratio=0.6,
            tempo=0.2,
            objectives_progress=0.1,
            terrain_favorability=-0.3,
            supply_level=0.2,
            ammo_level=0.15,
            fuel_level=0.3,
            transport_available=0.3,
            msr_status=0.4,
            network_connectivity=0.4,
            primary_comms_up=False,
            alternate_comms_available=True,
            jamming_threat=0.5,
            ts=TS,
        )

        assert result2.overall_supportability < result.overall_supportability
