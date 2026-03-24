"""Tests for c2.planning.phases -- operational phasing module."""

from __future__ import annotations



from stochastic_warfare.c2.events import PhaseTransitionEvent
from stochastic_warfare.c2.orders.types import MissionType
from stochastic_warfare.c2.planning.coa import COA, COATimeline, ManeuverType, TaskAssignment
from stochastic_warfare.c2.planning.phases import (
    BranchPlan,
    ConditionType,
    OperationalPhaseType,
    OperationalPhase,
    OperationalPlan,
    PhasingConfig,
    PhasingEngine,
    SequelPlan,
    TransitionCondition,
)
from stochastic_warfare.core.events import EventBus

from tests.conftest import TS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_coa(
    coa_id: str = "coa_1",
    maneuver: ManeuverType = ManeuverType.FRONTAL_ATTACK,
) -> COA:
    """Create a minimal COA for testing."""
    return COA(
        coa_id=coa_id,
        name="Test COA",
        maneuver_type=maneuver,
        main_effort_direction=0.0,
        task_assignments=(
            TaskAssignment("sub_1", "Main effort", 0.6),
            TaskAssignment("sub_2", "Supporting", 0.4),
        ),
    )


def _make_coa_with_timeline(coa_id: str = "coa_tl") -> COA:
    """Create a COA with an explicit timeline."""
    return COA(
        coa_id=coa_id,
        name="COA with timeline",
        maneuver_type=ManeuverType.FRONTAL_ATTACK,
        main_effort_direction=0.0,
        task_assignments=(
            TaskAssignment("sub_1", "Main effort", 0.6),
        ),
        timeline=(
            COATimeline("Shape", 1000.0, ("Recon forward",)),
            COATimeline("Decisive", 3000.0, ("Assault objective",)),
            COATimeline("Exploit", 1000.0, ("Consolidate",)),
            COATimeline("Transition", 500.0, ("Handoff",)),
        ),
    )


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestOperationalPhaseType:
    def test_values(self) -> None:
        assert OperationalPhaseType.SHAPING == 0
        assert OperationalPhaseType.DECISIVE == 1
        assert OperationalPhaseType.EXPLOITATION == 2
        assert OperationalPhaseType.TRANSITION == 3
        assert OperationalPhaseType.PREPARATION == 4
        assert OperationalPhaseType.DEFENSE == 5
        assert OperationalPhaseType.COUNTERATTACK == 6
        assert OperationalPhaseType.CONSOLIDATION == 7

    def test_all_members(self) -> None:
        assert len(OperationalPhaseType) == 8


class TestConditionType:
    def test_values(self) -> None:
        assert ConditionType.TIME_ELAPSED == 0
        assert ConditionType.CASUALTIES_EXCEED == 1
        assert ConditionType.OBJECTIVE_SECURED == 2
        assert ConditionType.FORCE_RATIO_BELOW == 3
        assert ConditionType.FORCE_RATIO_ABOVE == 4
        assert ConditionType.SUPPLY_BELOW == 5
        assert ConditionType.MORALE_BELOW == 6
        assert ConditionType.ENEMY_RESERVE_COMMITTED == 7

    def test_all_members(self) -> None:
        assert len(ConditionType) == 8


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------


class TestTransitionCondition:
    def test_creation(self) -> None:
        tc = TransitionCondition(
            condition_type=ConditionType.TIME_ELAPSED,
            threshold=3600.0,
            description="Time limit",
        )
        assert tc.condition_type == ConditionType.TIME_ELAPSED
        assert tc.threshold == 3600.0
        assert tc.description == "Time limit"

    def test_mutable(self) -> None:
        tc = TransitionCondition(
            condition_type=ConditionType.CASUALTIES_EXCEED,
            threshold=0.3,
            description="Casualty limit",
        )
        tc.threshold = 0.5
        assert tc.threshold == 0.5


class TestOperationalPhase:
    def test_creation_defaults(self) -> None:
        phase = OperationalPhase(
            phase_type=OperationalPhaseType.SHAPING,
            name="Shaping",
            duration_estimate_s=1800.0,
            tasks=("Recon",),
            transition_conditions=[],
        )
        assert phase.is_active is False
        assert phase.is_complete is False

    def test_active_and_complete(self) -> None:
        phase = OperationalPhase(
            phase_type=OperationalPhaseType.DECISIVE,
            name="Decisive",
            duration_estimate_s=5000.0,
            tasks=("Attack",),
            transition_conditions=[],
            is_active=True,
        )
        assert phase.is_active is True
        phase.is_complete = True
        assert phase.is_complete is True


class TestBranchPlan:
    def test_creation(self) -> None:
        bp = BranchPlan(
            branch_id="branch_1",
            trigger_description="Enemy flanks",
            trigger_condition=TransitionCondition(
                ConditionType.FORCE_RATIO_BELOW, 0.5, "Force ratio low",
            ),
            phases=[],
        )
        assert bp.branch_id == "branch_1"
        assert bp.trigger_description == "Enemy flanks"
        assert bp.trigger_condition.threshold == 0.5
        assert bp.phases == []


class TestSequelPlan:
    def test_creation(self) -> None:
        sp = SequelPlan(
            sequel_id="sequel_1",
            description="Exploit success",
            mission_type=int(MissionType.MOVEMENT_TO_CONTACT),
            conditions_for_initiation=[],
        )
        assert sp.sequel_id == "sequel_1"
        assert sp.mission_type == MissionType.MOVEMENT_TO_CONTACT


class TestOperationalPlan:
    def test_creation_and_current_phase(self) -> None:
        phase = OperationalPhase(
            phase_type=OperationalPhaseType.SHAPING,
            name="Shaping",
            duration_estimate_s=1000.0,
            tasks=("Recon",),
            transition_conditions=[],
            is_active=True,
        )
        plan = OperationalPlan(
            plan_id="plan_1",
            unit_id="bn_1",
            coa_id="coa_1",
            timestamp=TS,
            phases=[phase],
        )
        assert plan.current_phase is phase
        assert plan.current_phase_index == 0
        assert plan.is_complete is False

    def test_current_phase_none_when_complete(self) -> None:
        plan = OperationalPlan(
            plan_id="plan_1",
            unit_id="bn_1",
            coa_id="coa_1",
            timestamp=TS,
            phases=[],
            is_complete=True,
        )
        assert plan.current_phase is None

    def test_current_phase_none_when_index_past_end(self) -> None:
        plan = OperationalPlan(
            plan_id="plan_1",
            unit_id="bn_1",
            coa_id="coa_1",
            timestamp=TS,
            phases=[],
            current_phase_index=5,
        )
        assert plan.current_phase is None


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


class TestPhasingConfig:
    def test_defaults(self) -> None:
        cfg = PhasingConfig()
        assert cfg.planning_horizons_s["PLATOON"] == 1800.0
        assert cfg.planning_horizons_s["CORPS"] == 345600.0
        assert cfg.default_casualty_threshold == 0.3
        assert cfg.default_supply_threshold == 0.15
        assert cfg.default_morale_threshold == 0.25

    def test_custom(self) -> None:
        cfg = PhasingConfig(default_casualty_threshold=0.5)
        assert cfg.default_casualty_threshold == 0.5
        # Other defaults preserved
        assert cfg.default_supply_threshold == 0.15


# ---------------------------------------------------------------------------
# PhasingEngine.create_plan tests
# ---------------------------------------------------------------------------


class TestCreatePlan:
    def test_attack_mission_phases(self, event_bus: EventBus) -> None:
        engine = PhasingEngine(event_bus)
        coa = _make_coa()
        plan = engine.create_plan("bn_1", coa, echelon=6, mission_type=MissionType.ATTACK, ts=TS)

        # Offensive: SHAPING -> DECISIVE -> EXPLOITATION -> TRANSITION
        assert len(plan.phases) == 4
        assert plan.phases[0].phase_type == OperationalPhaseType.SHAPING
        assert plan.phases[1].phase_type == OperationalPhaseType.DECISIVE
        assert plan.phases[2].phase_type == OperationalPhaseType.EXPLOITATION
        assert plan.phases[3].phase_type == OperationalPhaseType.TRANSITION

    def test_defend_mission_phases(self, event_bus: EventBus) -> None:
        engine = PhasingEngine(event_bus)
        coa = _make_coa()
        plan = engine.create_plan("bn_1", coa, echelon=6, mission_type=MissionType.DEFEND, ts=TS)

        # Defensive: PREPARATION -> DEFENSE -> COUNTERATTACK -> CONSOLIDATION
        assert len(plan.phases) == 4
        assert plan.phases[0].phase_type == OperationalPhaseType.PREPARATION
        assert plan.phases[1].phase_type == OperationalPhaseType.DEFENSE
        assert plan.phases[2].phase_type == OperationalPhaseType.COUNTERATTACK
        assert plan.phases[3].phase_type == OperationalPhaseType.CONSOLIDATION

    def test_delay_mission_phases(self, event_bus: EventBus) -> None:
        engine = PhasingEngine(event_bus)
        coa = _make_coa()
        plan = engine.create_plan("bn_1", coa, echelon=6, mission_type=MissionType.DELAY, ts=TS)

        # Delay: SHAPING -> DEFENSE -> TRANSITION
        assert len(plan.phases) == 3
        assert plan.phases[0].phase_type == OperationalPhaseType.SHAPING
        assert plan.phases[1].phase_type == OperationalPhaseType.DEFENSE
        assert plan.phases[2].phase_type == OperationalPhaseType.TRANSITION

    def test_default_mission_phases(self, event_bus: EventBus) -> None:
        engine = PhasingEngine(event_bus)
        coa = _make_coa()
        # Use SCREEN which is not in any specific category
        plan = engine.create_plan("bn_1", coa, echelon=6, mission_type=MissionType.SCREEN, ts=TS)

        # Default: SHAPING -> DECISIVE -> TRANSITION
        assert len(plan.phases) == 3
        assert plan.phases[0].phase_type == OperationalPhaseType.SHAPING
        assert plan.phases[1].phase_type == OperationalPhaseType.DECISIVE
        assert plan.phases[2].phase_type == OperationalPhaseType.TRANSITION

    def test_first_phase_is_active(self, event_bus: EventBus) -> None:
        engine = PhasingEngine(event_bus)
        coa = _make_coa()
        plan = engine.create_plan("bn_1", coa, echelon=6, mission_type=MissionType.ATTACK, ts=TS)

        assert plan.phases[0].is_active is True
        for phase in plan.phases[1:]:
            assert phase.is_active is False

    def test_planning_horizon_scales_with_echelon(self, event_bus: EventBus) -> None:
        engine = PhasingEngine(event_bus)
        coa = _make_coa()

        platoon_plan = engine.create_plan("plt_1", coa, echelon=3, mission_type=MissionType.ATTACK, ts=TS)
        corps_plan = engine.create_plan("corps_1", coa, echelon=10, mission_type=MissionType.ATTACK, ts=TS)

        assert platoon_plan.planning_horizon_s == 1800.0
        assert corps_plan.planning_horizon_s == 345600.0
        assert platoon_plan.planning_horizon_s < corps_plan.planning_horizon_s

    def test_includes_branch_plans(self, event_bus: EventBus) -> None:
        engine = PhasingEngine(event_bus)
        coa = _make_coa()
        plan = engine.create_plan("bn_1", coa, echelon=6, mission_type=MissionType.ATTACK, ts=TS)

        assert len(plan.branches) >= 1
        branch = plan.branches[0]
        assert "counterattack" in branch.branch_id.lower() or "counterattack" in branch.trigger_description.lower()
        assert branch.trigger_condition.condition_type == ConditionType.FORCE_RATIO_BELOW
        assert branch.trigger_condition.threshold == 0.5

    def test_includes_sequel_plans(self, event_bus: EventBus) -> None:
        engine = PhasingEngine(event_bus)
        coa = _make_coa()
        plan = engine.create_plan("bn_1", coa, echelon=6, mission_type=MissionType.ATTACK, ts=TS)

        assert len(plan.sequels) >= 1
        sequel = plan.sequels[0]
        assert sequel.mission_type == MissionType.MOVEMENT_TO_CONTACT

    def test_plan_id_contains_unit_id(self, event_bus: EventBus) -> None:
        engine = PhasingEngine(event_bus)
        coa = _make_coa()
        plan = engine.create_plan("alpha_bn", coa, echelon=6, mission_type=MissionType.ATTACK, ts=TS)

        assert plan.plan_id.startswith("alpha_bn_plan_")

    def test_seize_mission_is_offensive(self, event_bus: EventBus) -> None:
        engine = PhasingEngine(event_bus)
        coa = _make_coa()
        plan = engine.create_plan("bn_1", coa, echelon=6, mission_type=MissionType.SEIZE, ts=TS)

        # Should use offensive phasing: 4 phases
        assert len(plan.phases) == 4
        assert plan.phases[0].phase_type == OperationalPhaseType.SHAPING

    def test_coa_timeline_tasks_used(self, event_bus: EventBus) -> None:
        engine = PhasingEngine(event_bus)
        coa = _make_coa_with_timeline()
        plan = engine.create_plan("bn_1", coa, echelon=6, mission_type=MissionType.ATTACK, ts=TS)

        # The first phase should use COA timeline tasks
        assert plan.phases[0].tasks == ("Recon forward",)
        assert plan.phases[1].tasks == ("Assault objective",)

    def test_transition_conditions_present(self, event_bus: EventBus) -> None:
        engine = PhasingEngine(event_bus)
        coa = _make_coa()
        plan = engine.create_plan("bn_1", coa, echelon=6, mission_type=MissionType.ATTACK, ts=TS)

        # Every phase should have at least one transition condition
        for phase in plan.phases:
            assert len(phase.transition_conditions) >= 1

    def test_withdraw_mission_uses_delay_phases(self, event_bus: EventBus) -> None:
        engine = PhasingEngine(event_bus)
        coa = _make_coa()
        plan = engine.create_plan("bn_1", coa, echelon=6, mission_type=MissionType.WITHDRAW, ts=TS)

        # Same as DELAY: SHAPING -> DEFENSE -> TRANSITION
        assert len(plan.phases) == 3

    def test_defensive_sequel_is_counterattack(self, event_bus: EventBus) -> None:
        engine = PhasingEngine(event_bus)
        coa = _make_coa()
        plan = engine.create_plan("bn_1", coa, echelon=6, mission_type=MissionType.DEFEND, ts=TS)

        assert len(plan.sequels) >= 1
        assert plan.sequels[0].mission_type == MissionType.ATTACK


# ---------------------------------------------------------------------------
# PhasingEngine.check_transition tests
# ---------------------------------------------------------------------------


class TestCheckTransition:
    def _make_attack_plan(self, event_bus: EventBus) -> OperationalPlan:
        engine = PhasingEngine(event_bus)
        coa = _make_coa()
        return engine.create_plan("bn_1", coa, echelon=6, mission_type=MissionType.ATTACK, ts=TS)

    def test_time_elapsed_triggers_transition(self, event_bus: EventBus) -> None:
        engine = PhasingEngine(event_bus)
        plan = self._make_attack_plan(event_bus)

        # Shaping phase has a TIME_ELAPSED condition
        shaping_duration = plan.phases[0].duration_estimate_s

        # Not enough time yet
        result = engine.check_transition(
            plan, force_ratio=2.0, casualties_fraction=0.0,
            objectives_progress=0.0, supply_level=1.0, morale_level=1.0,
            elapsed_s=shaping_duration * 0.5, ts=TS,
        )
        assert result is False
        assert plan.current_phase_index == 0

        # Enough time
        result = engine.check_transition(
            plan, force_ratio=2.0, casualties_fraction=0.0,
            objectives_progress=0.0, supply_level=1.0, morale_level=1.0,
            elapsed_s=shaping_duration + 1.0, ts=TS,
        )
        assert result is True
        assert plan.current_phase_index == 1

    def test_casualties_triggers_transition(self, event_bus: EventBus) -> None:
        engine = PhasingEngine(event_bus)
        plan = self._make_attack_plan(event_bus)

        # Advance to DECISIVE phase first (via objective progress on SHAPING)
        engine.check_transition(
            plan, force_ratio=2.0, casualties_fraction=0.0,
            objectives_progress=0.5, supply_level=1.0, morale_level=1.0,
            elapsed_s=0.0, ts=TS,
        )
        assert plan.current_phase_index == 1  # Now in DECISIVE

        # Casualties trigger transition from DECISIVE
        result = engine.check_transition(
            plan, force_ratio=2.0, casualties_fraction=0.35,
            objectives_progress=0.0, supply_level=1.0, morale_level=1.0,
            elapsed_s=0.0, ts=TS,
        )
        assert result is True
        assert plan.current_phase_index == 2  # EXPLOITATION

    def test_objective_secured_triggers_transition(self, event_bus: EventBus) -> None:
        engine = PhasingEngine(event_bus)
        plan = self._make_attack_plan(event_bus)

        # SHAPING has OBJECTIVE_SECURED at 0.3 threshold
        result = engine.check_transition(
            plan, force_ratio=2.0, casualties_fraction=0.0,
            objectives_progress=0.35, supply_level=1.0, morale_level=1.0,
            elapsed_s=0.0, ts=TS,
        )
        assert result is True
        assert plan.phases[0].is_complete is True
        assert plan.phases[1].is_active is True

    def test_publishes_phase_transition_event(self, event_bus: EventBus) -> None:
        engine = PhasingEngine(event_bus)
        plan = self._make_attack_plan(event_bus)

        events_received: list[PhaseTransitionEvent] = []
        event_bus.subscribe(PhaseTransitionEvent, lambda e: events_received.append(e))

        shaping_duration = plan.phases[0].duration_estimate_s
        engine.check_transition(
            plan, force_ratio=2.0, casualties_fraction=0.0,
            objectives_progress=0.0, supply_level=1.0, morale_level=1.0,
            elapsed_s=shaping_duration + 1.0, ts=TS,
        )

        assert len(events_received) == 1
        evt = events_received[0]
        assert evt.unit_id == "bn_1"
        assert evt.plan_id == plan.plan_id
        assert evt.old_phase == "SHAPING"
        assert evt.new_phase == "DECISIVE"

    def test_advances_phase_index(self, event_bus: EventBus) -> None:
        engine = PhasingEngine(event_bus)
        plan = self._make_attack_plan(event_bus)

        assert plan.current_phase_index == 0
        shaping_duration = plan.phases[0].duration_estimate_s
        engine.check_transition(
            plan, force_ratio=2.0, casualties_fraction=0.0,
            objectives_progress=0.0, supply_level=1.0, morale_level=1.0,
            elapsed_s=shaping_duration + 1.0, ts=TS,
        )
        assert plan.current_phase_index == 1

    def test_marks_plan_complete_at_end(self, event_bus: EventBus) -> None:
        engine = PhasingEngine(event_bus)
        plan = self._make_attack_plan(event_bus)

        # Advance through all phases by using objective/time triggers
        # Phase 0: SHAPING -> objective 0.3
        engine.check_transition(
            plan, force_ratio=2.0, casualties_fraction=0.0,
            objectives_progress=0.5, supply_level=1.0, morale_level=1.0,
            elapsed_s=0.0, ts=TS,
        )
        # Phase 1: DECISIVE -> objective 0.7
        engine.check_transition(
            plan, force_ratio=2.0, casualties_fraction=0.0,
            objectives_progress=0.75, supply_level=1.0, morale_level=1.0,
            elapsed_s=0.0, ts=TS,
        )
        # Phase 2: EXPLOITATION -> objective 1.0
        engine.check_transition(
            plan, force_ratio=2.0, casualties_fraction=0.0,
            objectives_progress=1.0, supply_level=1.0, morale_level=1.0,
            elapsed_s=0.0, ts=TS,
        )
        # Phase 3: TRANSITION -> time elapsed
        transition_duration = plan.phases[3].duration_estimate_s
        engine.check_transition(
            plan, force_ratio=2.0, casualties_fraction=0.0,
            objectives_progress=1.0, supply_level=1.0, morale_level=1.0,
            elapsed_s=transition_duration + 1.0, ts=TS,
        )

        assert plan.is_complete is True
        assert plan.current_phase is None

    def test_returns_false_when_no_condition_met(self, event_bus: EventBus) -> None:
        engine = PhasingEngine(event_bus)
        plan = self._make_attack_plan(event_bus)

        result = engine.check_transition(
            plan, force_ratio=2.0, casualties_fraction=0.0,
            objectives_progress=0.0, supply_level=1.0, morale_level=1.0,
            elapsed_s=0.0, ts=TS,
        )
        assert result is False
        assert plan.current_phase_index == 0

    def test_returns_false_on_complete_plan(self, event_bus: EventBus) -> None:
        engine = PhasingEngine(event_bus)
        plan = self._make_attack_plan(event_bus)
        plan.is_complete = True

        result = engine.check_transition(
            plan, force_ratio=2.0, casualties_fraction=0.0,
            objectives_progress=1.0, supply_level=1.0, morale_level=1.0,
            elapsed_s=999999.0, ts=TS,
        )
        assert result is False

    def test_force_ratio_below_triggers_exploitation_exit(self, event_bus: EventBus) -> None:
        engine = PhasingEngine(event_bus)
        plan = self._make_attack_plan(event_bus)

        # Advance to EXPLOITATION (index 2)
        engine.check_transition(
            plan, force_ratio=2.0, casualties_fraction=0.0,
            objectives_progress=0.5, supply_level=1.0, morale_level=1.0,
            elapsed_s=0.0, ts=TS,
        )
        engine.check_transition(
            plan, force_ratio=2.0, casualties_fraction=0.0,
            objectives_progress=0.75, supply_level=1.0, morale_level=1.0,
            elapsed_s=0.0, ts=TS,
        )
        assert plan.current_phase_index == 2  # EXPLOITATION

        # EXPLOITATION has FORCE_RATIO_BELOW at 0.5
        result = engine.check_transition(
            plan, force_ratio=0.4, casualties_fraction=0.0,
            objectives_progress=0.0, supply_level=1.0, morale_level=1.0,
            elapsed_s=0.0, ts=TS,
        )
        assert result is True
        assert plan.current_phase_index == 3  # TRANSITION


# ---------------------------------------------------------------------------
# PhasingEngine.check_branch_activation tests
# ---------------------------------------------------------------------------


class TestCheckBranchActivation:
    def test_triggers_on_force_ratio(self, event_bus: EventBus) -> None:
        engine = PhasingEngine(event_bus)
        coa = _make_coa()
        plan = engine.create_plan("bn_1", coa, echelon=6, mission_type=MissionType.ATTACK, ts=TS)

        # Standard branch triggers at force_ratio <= 0.5
        branch = engine.check_branch_activation(
            plan, force_ratio=0.3, casualties_fraction=0.0,
            objectives_progress=0.0, supply_level=1.0, morale_level=1.0,
            elapsed_s=0.0,
        )
        assert branch is not None
        assert "counterattack" in branch.branch_id.lower()

    def test_returns_none_when_no_trigger(self, event_bus: EventBus) -> None:
        engine = PhasingEngine(event_bus)
        coa = _make_coa()
        plan = engine.create_plan("bn_1", coa, echelon=6, mission_type=MissionType.ATTACK, ts=TS)

        branch = engine.check_branch_activation(
            plan, force_ratio=3.0, casualties_fraction=0.0,
            objectives_progress=0.0, supply_level=1.0, morale_level=1.0,
            elapsed_s=0.0,
        )
        assert branch is None


# ---------------------------------------------------------------------------
# Full plan traversal
# ---------------------------------------------------------------------------


class TestFullPlanTraversal:
    def test_multiple_transitions_through_entire_plan(self, event_bus: EventBus) -> None:
        engine = PhasingEngine(event_bus)
        coa = _make_coa()
        plan = engine.create_plan("bn_1", coa, echelon=6, mission_type=MissionType.ATTACK, ts=TS)

        events_received: list[PhaseTransitionEvent] = []
        event_bus.subscribe(PhaseTransitionEvent, lambda e: events_received.append(e))

        # Walk through all 4 phases
        assert plan.current_phase_index == 0
        assert not plan.is_complete

        # Phase 0 -> 1: SHAPING -> DECISIVE (objective 30%)
        engine.check_transition(
            plan, force_ratio=2.0, casualties_fraction=0.0,
            objectives_progress=0.4, supply_level=1.0, morale_level=1.0,
            elapsed_s=0.0, ts=TS,
        )
        assert plan.current_phase_index == 1

        # Phase 1 -> 2: DECISIVE -> EXPLOITATION (objective 70%)
        engine.check_transition(
            plan, force_ratio=2.0, casualties_fraction=0.0,
            objectives_progress=0.8, supply_level=1.0, morale_level=1.0,
            elapsed_s=0.0, ts=TS,
        )
        assert plan.current_phase_index == 2

        # Phase 2 -> 3: EXPLOITATION -> TRANSITION (objective 100%)
        engine.check_transition(
            plan, force_ratio=2.0, casualties_fraction=0.0,
            objectives_progress=1.0, supply_level=1.0, morale_level=1.0,
            elapsed_s=0.0, ts=TS,
        )
        assert plan.current_phase_index == 3

        # Phase 3 -> complete: TRANSITION (time elapsed)
        transition_dur = plan.phases[3].duration_estimate_s
        engine.check_transition(
            plan, force_ratio=2.0, casualties_fraction=0.0,
            objectives_progress=1.0, supply_level=1.0, morale_level=1.0,
            elapsed_s=transition_dur + 1.0, ts=TS,
        )
        assert plan.is_complete is True

        # We should have 4 transition events
        assert len(events_received) == 4


# ---------------------------------------------------------------------------
# Echelon mapping
# ---------------------------------------------------------------------------


class TestEchelonMapping:
    def test_platoon_shorter_than_corps(self, event_bus: EventBus) -> None:
        engine = PhasingEngine(event_bus)
        coa = _make_coa()

        plt_plan = engine.create_plan("plt_1", coa, echelon=3, mission_type=MissionType.ATTACK, ts=TS)
        corps_plan = engine.create_plan("corps_1", coa, echelon=10, mission_type=MissionType.ATTACK, ts=TS)

        assert plt_plan.planning_horizon_s < corps_plan.planning_horizon_s
        # Platoon phases have shorter durations
        assert plt_plan.phases[0].duration_estimate_s < corps_plan.phases[0].duration_estimate_s

    def test_company_echelon(self, event_bus: EventBus) -> None:
        engine = PhasingEngine(event_bus)
        coa = _make_coa()
        plan = engine.create_plan("co_1", coa, echelon=5, mission_type=MissionType.ATTACK, ts=TS)
        assert plan.planning_horizon_s == 7200.0

    def test_brigade_echelon(self, event_bus: EventBus) -> None:
        engine = PhasingEngine(event_bus)
        coa = _make_coa()
        plan = engine.create_plan("bde_1", coa, echelon=8, mission_type=MissionType.ATTACK, ts=TS)
        assert plan.planning_horizon_s == 86400.0


# ---------------------------------------------------------------------------
# State protocol
# ---------------------------------------------------------------------------


class TestGetSetState:
    def test_round_trip(self, event_bus: EventBus) -> None:
        engine = PhasingEngine(event_bus)
        coa = _make_coa()

        # Create a couple of plans to bump plan_count
        engine.create_plan("bn_1", coa, echelon=6, mission_type=MissionType.ATTACK, ts=TS)
        engine.create_plan("bn_2", coa, echelon=6, mission_type=MissionType.DEFEND, ts=TS)

        state = engine.get_state()
        assert state["plan_count"] == 2

        # Create a fresh engine and restore
        engine2 = PhasingEngine(event_bus)
        assert engine2.get_state()["plan_count"] == 0
        engine2.set_state(state)
        assert engine2.get_state()["plan_count"] == 2
