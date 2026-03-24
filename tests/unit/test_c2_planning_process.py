"""Tests for planning process orchestrator (c2.planning.process).

Uses shared fixtures from conftest.py.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from stochastic_warfare.c2.events import (
    PlanningCompletedEvent,
    PlanningStartedEvent,
)
from stochastic_warfare.c2.orders.types import (
    MissionType,
    Order,
    OrderPriority,
    OrderType,
)
from stochastic_warfare.c2.planning.process import (
    PlanningMethod,
    PlanningPhase,
    PlanningProcessConfig,
    PlanningProcessEngine,
)
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position
from tests.conftest import DEFAULT_SEED, TS, make_rng


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_order(
    echelon: int = 6,
    mission_type: int = MissionType.ATTACK,
    **kwargs,
) -> Order:
    return Order(
        order_id=kwargs.pop("order_id", "test_order"),
        issuer_id=kwargs.pop("issuer_id", "higher_hq"),
        recipient_id=kwargs.pop("recipient_id", "unit_a"),
        timestamp=kwargs.pop("timestamp", TS),
        order_type=kwargs.pop("order_type", OrderType.OPORD),
        echelon_level=echelon,
        priority=kwargs.pop("priority", OrderPriority.ROUTINE),
        mission_type=mission_type,
        objective_position=kwargs.pop(
            "objective_position", Position(1000.0, 1000.0, 0.0),
        ),
        **kwargs,
    )


def _make_engine(
    event_bus: EventBus | None = None,
    rng: np.random.Generator | None = None,
    config: PlanningProcessConfig | None = None,
) -> PlanningProcessEngine:
    eb = event_bus or EventBus()
    r = rng or make_rng(DEFAULT_SEED)
    return PlanningProcessEngine(eb, r, config)


# ---------------------------------------------------------------------------
# Enum value tests
# ---------------------------------------------------------------------------


class TestEnums:
    """Verify enum ordinals match spec."""

    def test_planning_method_values(self) -> None:
        assert PlanningMethod.INTUITIVE == 0
        assert PlanningMethod.DIRECTIVE == 1
        assert PlanningMethod.RAPID == 2
        assert PlanningMethod.MDMP == 3

    def test_planning_phase_values(self) -> None:
        assert PlanningPhase.IDLE == 0
        assert PlanningPhase.RECEIVING_MISSION == 1
        assert PlanningPhase.ANALYZING == 2
        assert PlanningPhase.DEVELOPING_COA == 3
        assert PlanningPhase.COMPARING == 4
        assert PlanningPhase.APPROVING == 5
        assert PlanningPhase.ISSUING_ORDERS == 6
        assert PlanningPhase.COMPLETE == 7


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


class TestPlanningProcessConfig:
    """Verify config defaults."""

    def test_defaults(self) -> None:
        cfg = PlanningProcessConfig()
        assert cfg.method_speed_multipliers["MDMP"] == 1.0
        assert cfg.method_speed_multipliers["INTUITIVE"] == 10.0
        assert cfg.base_phase_durations_s["ANALYZING"] == 1800.0
        assert cfg.time_rule_fraction == pytest.approx(1.0 / 3.0)

    def test_custom_override(self) -> None:
        cfg = PlanningProcessConfig(time_rule_fraction=0.5)
        assert cfg.time_rule_fraction == 0.5


# ---------------------------------------------------------------------------
# select_method tests
# ---------------------------------------------------------------------------


class TestSelectMethod:
    """Test planning method selection logic."""

    def test_platoon_always_intuitive(self) -> None:
        engine = _make_engine()
        assert engine.select_method(4, 100_000) == PlanningMethod.INTUITIVE

    def test_squad_always_intuitive(self) -> None:
        engine = _make_engine()
        assert engine.select_method(2, 100_000) == PlanningMethod.INTUITIVE

    def test_battalion_ample_time_mdmp(self) -> None:
        engine = _make_engine()
        # 10,000s > 7,200s threshold
        assert engine.select_method(6, 10_000) == PlanningMethod.MDMP

    def test_battalion_limited_time_rapid(self) -> None:
        engine = _make_engine()
        # 3,000s: between 1,800 and 7,200
        assert engine.select_method(6, 3_000) == PlanningMethod.RAPID

    def test_battalion_very_limited_time_intuitive(self) -> None:
        engine = _make_engine()
        # 1,000s < 1,800s threshold
        assert engine.select_method(6, 1_000) == PlanningMethod.INTUITIVE

    def test_brigade_ample_time_mdmp(self) -> None:
        engine = _make_engine()
        # 5,000s > 3,600s threshold
        assert engine.select_method(8, 5_000) == PlanningMethod.MDMP

    def test_brigade_limited_time_rapid(self) -> None:
        engine = _make_engine()
        # 2,000s < 3,600s threshold
        assert engine.select_method(8, 2_000) == PlanningMethod.RAPID

    def test_befehlstaktik_prefers_directive(self) -> None:
        engine = _make_engine()
        # Company (5) with very little time -> would be INTUITIVE, but
        # Befehlstaktik upgrades to DIRECTIVE for company+
        method = engine.select_method(5, 500, doctrine_style="BEFEHLSTAKTIK")
        assert method == PlanningMethod.DIRECTIVE

    def test_befehlstaktik_does_not_affect_platoon(self) -> None:
        engine = _make_engine()
        # Platoon stays INTUITIVE even with BEFEHLSTAKTIK
        method = engine.select_method(4, 500, doctrine_style="BEFEHLSTAKTIK")
        assert method == PlanningMethod.INTUITIVE

    def test_auftragstaktik_relaxes_thresholds(self) -> None:
        engine = _make_engine()
        # Battalion with 2,500s: normally RAPID (> 1800, < 7200),
        # but Auftragstaktik doubles thresholds so 2500 < 3600 -> INTUITIVE
        method = engine.select_method(6, 2_500, doctrine_style="AUFTRAGSTAKTIK")
        assert method == PlanningMethod.INTUITIVE

    def test_auftragstaktik_battalion_rapid_threshold(self) -> None:
        engine = _make_engine()
        # Battalion with 5,000s: Auftragstaktik doubles 1800->3600 and 7200->14400
        # 5000 > 3600, 5000 < 14400 -> RAPID
        method = engine.select_method(6, 5_000, doctrine_style="AUFTRAGSTAKTIK")
        assert method == PlanningMethod.RAPID


# ---------------------------------------------------------------------------
# initiate_planning tests
# ---------------------------------------------------------------------------


class TestInitiatePlanning:
    """Test planning initiation."""

    def test_starts_at_receiving_mission(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = PlanningProcessEngine(event_bus, rng)
        order = _make_order(echelon=6)
        engine.initiate_planning("unit_a", order, 10_000, ts=TS)
        assert engine.get_planning_status("unit_a") == PlanningPhase.RECEIVING_MISSION

    def test_publishes_started_event(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        received: list = []
        event_bus.subscribe(PlanningStartedEvent, received.append)

        engine = PlanningProcessEngine(event_bus, rng)
        order = _make_order(echelon=6)
        engine.initiate_planning("unit_a", order, 10_000, ts=TS)

        assert len(received) == 1
        evt = received[0]
        assert evt.unit_id == "unit_a"
        assert evt.planning_method == "MDMP"
        assert evt.echelon_level == 6
        assert evt.estimated_duration_s > 0

    def test_applies_one_third_rule(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = PlanningProcessEngine(event_bus, rng)
        order = _make_order(echelon=6)
        engine.initiate_planning("unit_a", order, 9000, ts=TS)

        # Budget should be 9000 * 1/3 = 3000
        state = engine._states["unit_a"]
        assert state.available_time_s == pytest.approx(3000.0)

    def test_returns_correct_method(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = PlanningProcessEngine(event_bus, rng)
        # Battalion with ample time -> MDMP
        method = engine.initiate_planning(
            "unit_a", _make_order(echelon=6), 10_000, ts=TS,
        )
        assert method == PlanningMethod.MDMP

    def test_returns_rapid_for_limited_time(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = PlanningProcessEngine(event_bus, rng)
        # Battalion with 3000s -> RAPID
        method = engine.initiate_planning(
            "unit_a", _make_order(echelon=6), 3_000, ts=TS,
        )
        assert method == PlanningMethod.RAPID


# ---------------------------------------------------------------------------
# update tests
# ---------------------------------------------------------------------------


class TestUpdate:
    """Test timer update logic."""

    def test_decrements_timer(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = PlanningProcessEngine(event_bus, rng)
        order = _make_order(echelon=6)
        engine.initiate_planning("unit_a", order, 10_000, ts=TS)

        initial_timer = engine._states["unit_a"].phase_timer
        engine.update(100.0)
        assert engine._states["unit_a"].phase_timer == pytest.approx(initial_timer - 100.0)

    def test_returns_completed_phases(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = PlanningProcessEngine(event_bus, rng)
        order = _make_order(echelon=6)
        engine.initiate_planning("unit_a", order, 10_000, ts=TS)

        # Advance past the first phase timer
        timer = engine._states["unit_a"].phase_timer
        completed = engine.update(timer + 1.0)

        assert len(completed) == 1
        assert completed[0] == ("unit_a", PlanningPhase.RECEIVING_MISSION)

    def test_does_not_auto_advance(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = PlanningProcessEngine(event_bus, rng)
        order = _make_order(echelon=6)
        engine.initiate_planning("unit_a", order, 10_000, ts=TS)

        timer = engine._states["unit_a"].phase_timer
        engine.update(timer + 1.0)

        # Phase should still be RECEIVING_MISSION (not auto-advanced)
        assert engine.get_planning_status("unit_a") == PlanningPhase.RECEIVING_MISSION

    def test_multiple_units(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = PlanningProcessEngine(event_bus, rng)
        engine.initiate_planning(
            "unit_a", _make_order(echelon=6, order_id="o1"), 10_000, ts=TS,
        )
        engine.initiate_planning(
            "unit_b", _make_order(echelon=6, order_id="o2"), 10_000, ts=TS,
        )

        # Both have RECEIVING_MISSION with same base timer (MDMP)
        timer_a = engine._states["unit_a"].phase_timer
        timer_b = engine._states["unit_b"].phase_timer
        assert timer_a == pytest.approx(timer_b)

        # Advance past both
        completed = engine.update(timer_a + 1.0)
        unit_ids = {uid for uid, _ in completed}
        assert "unit_a" in unit_ids
        assert "unit_b" in unit_ids

    def test_skips_idle_and_complete(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = PlanningProcessEngine(event_bus, rng)
        order = _make_order(echelon=6)
        engine.initiate_planning("unit_a", order, 10_000, ts=TS)

        # Force to COMPLETE
        engine._states["unit_a"].phase = PlanningPhase.COMPLETE
        completed = engine.update(10_000.0)
        assert len(completed) == 0


# ---------------------------------------------------------------------------
# advance_phase tests
# ---------------------------------------------------------------------------


class TestAdvancePhase:
    """Test phase advancement logic."""

    def test_moves_to_next_phase(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = PlanningProcessEngine(event_bus, rng)
        engine.initiate_planning("unit_a", _make_order(echelon=8), 100_000, ts=TS)

        new_phase = engine.advance_phase("unit_a")
        assert new_phase == PlanningPhase.ANALYZING

    def test_intuitive_skips_coa_phases(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = PlanningProcessEngine(event_bus, rng)
        # Platoon -> INTUITIVE
        engine.initiate_planning("unit_a", _make_order(echelon=4), 100_000, ts=TS)
        assert engine.get_method("unit_a") == PlanningMethod.INTUITIVE

        # RECEIVING_MISSION -> ANALYZING
        phase = engine.advance_phase("unit_a")
        assert phase == PlanningPhase.ANALYZING

        # ANALYZING -> should skip DEVELOPING_COA, COMPARING, APPROVING
        # -> ISSUING_ORDERS
        phase = engine.advance_phase("unit_a")
        assert phase == PlanningPhase.ISSUING_ORDERS

    def test_rapid_skips_comparing(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = PlanningProcessEngine(event_bus, rng)
        engine.initiate_planning("unit_a", _make_order(echelon=6), 3_000, ts=TS)
        assert engine.get_method("unit_a") == PlanningMethod.RAPID

        # Advance through: RECEIVING -> ANALYZING -> DEVELOPING -> (skip COMPARING) -> APPROVING
        engine.advance_phase("unit_a")  # ANALYZING
        engine.advance_phase("unit_a")  # DEVELOPING_COA
        phase = engine.advance_phase("unit_a")  # Should skip COMPARING -> APPROVING
        assert phase == PlanningPhase.APPROVING

    def test_mdmp_goes_through_all_phases(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = PlanningProcessEngine(event_bus, rng)
        engine.initiate_planning("unit_a", _make_order(echelon=8), 100_000, ts=TS)
        assert engine.get_method("unit_a") == PlanningMethod.MDMP

        expected_sequence = [
            PlanningPhase.ANALYZING,
            PlanningPhase.DEVELOPING_COA,
            PlanningPhase.COMPARING,
            PlanningPhase.APPROVING,
            PlanningPhase.ISSUING_ORDERS,
        ]
        for expected in expected_sequence:
            actual = engine.advance_phase("unit_a")
            assert actual == expected, f"Expected {expected}, got {actual}"

    def test_advance_past_last_phase_goes_complete(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = PlanningProcessEngine(event_bus, rng)
        engine.initiate_planning("unit_a", _make_order(echelon=8), 100_000, ts=TS)

        # Advance through all phases
        for _ in range(5):
            engine.advance_phase("unit_a")

        assert engine.get_planning_status("unit_a") == PlanningPhase.ISSUING_ORDERS

        # One more advance should go to COMPLETE
        phase = engine.advance_phase("unit_a")
        assert phase == PlanningPhase.COMPLETE


# ---------------------------------------------------------------------------
# Status and getter tests
# ---------------------------------------------------------------------------


class TestStatusAndGetters:
    """Test query methods."""

    def test_get_planning_status_idle_for_unknown(self) -> None:
        engine = _make_engine()
        assert engine.get_planning_status("nonexistent") == PlanningPhase.IDLE

    def test_get_planning_status_returns_current(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = PlanningProcessEngine(event_bus, rng)
        engine.initiate_planning("unit_a", _make_order(echelon=6), 10_000, ts=TS)
        assert engine.get_planning_status("unit_a") == PlanningPhase.RECEIVING_MISSION

        engine.advance_phase("unit_a")
        assert engine.get_planning_status("unit_a") == PlanningPhase.ANALYZING

    def test_get_method_returns_none_for_unknown(self) -> None:
        engine = _make_engine()
        assert engine.get_method("nonexistent") is None

    def test_get_method_returns_correct_method(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = PlanningProcessEngine(event_bus, rng)
        engine.initiate_planning("unit_a", _make_order(echelon=8), 100_000, ts=TS)
        assert engine.get_method("unit_a") == PlanningMethod.MDMP


# ---------------------------------------------------------------------------
# Setter / injection tests
# ---------------------------------------------------------------------------


class TestResultInjection:
    """Test result setter methods."""

    def test_set_analysis_result(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = PlanningProcessEngine(event_bus, rng)
        engine.initiate_planning("unit_a", _make_order(echelon=6), 10_000, ts=TS)

        mock_result = {"tasks": ["seize_obj_a"]}
        engine.set_analysis_result("unit_a", mock_result)
        assert engine._states["unit_a"].analysis_result == mock_result

    def test_set_coas(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = PlanningProcessEngine(event_bus, rng)
        engine.initiate_planning("unit_a", _make_order(echelon=6), 10_000, ts=TS)

        mock_coas = [{"coa_id": "coa_1"}, {"coa_id": "coa_2"}]
        engine.set_coas("unit_a", mock_coas)
        assert engine._states["unit_a"].coas == mock_coas

    def test_set_selected_coa(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = PlanningProcessEngine(event_bus, rng)
        engine.initiate_planning("unit_a", _make_order(echelon=6), 10_000, ts=TS)

        mock_coa = {"coa_id": "coa_1"}
        engine.set_selected_coa("unit_a", mock_coa)
        assert engine._states["unit_a"].selected_coa == mock_coa

    def test_set_plan(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = PlanningProcessEngine(event_bus, rng)
        engine.initiate_planning("unit_a", _make_order(echelon=6), 10_000, ts=TS)

        mock_plan = {"phases": ["phase_1"]}
        engine.set_plan("unit_a", mock_plan)
        assert engine._states["unit_a"].plan == mock_plan


# ---------------------------------------------------------------------------
# complete / cancel tests
# ---------------------------------------------------------------------------


class TestCompleteCancel:
    """Test terminal transitions."""

    def test_complete_sets_phase_and_publishes(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        received: list = []
        event_bus.subscribe(PlanningCompletedEvent, received.append)

        engine = PlanningProcessEngine(event_bus, rng)
        engine.initiate_planning("unit_a", _make_order(echelon=6), 10_000, ts=TS)

        # Inject a mock selected COA with coa_id attribute
        @dataclass(frozen=True)
        class _MockCOA:
            coa_id: str = "coa_alpha"

        engine.set_coas("unit_a", [_MockCOA(), _MockCOA(coa_id="coa_beta")])
        engine.set_selected_coa("unit_a", _MockCOA())

        engine.complete_planning("unit_a", ts=TS)

        assert engine.get_planning_status("unit_a") == PlanningPhase.COMPLETE
        assert len(received) == 1
        evt = received[0]
        assert evt.unit_id == "unit_a"
        assert evt.planning_method == "MDMP"
        assert evt.selected_coa_id == "coa_alpha"
        assert evt.num_coas_evaluated == 2

    def test_cancel_removes_state(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = PlanningProcessEngine(event_bus, rng)
        engine.initiate_planning("unit_a", _make_order(echelon=6), 10_000, ts=TS)

        engine.cancel_planning("unit_a")
        assert engine.get_planning_status("unit_a") == PlanningPhase.IDLE

    def test_cancel_nonexistent_is_noop(self) -> None:
        engine = _make_engine()
        # Should not raise
        engine.cancel_planning("nonexistent")


# ---------------------------------------------------------------------------
# Full flow tests
# ---------------------------------------------------------------------------


class TestFullFlow:
    """End-to-end planning flows."""

    def test_full_mdmp_flow(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        """Complete MDMP flow: initiate -> advance all phases -> complete."""
        started: list = []
        completed: list = []
        event_bus.subscribe(PlanningStartedEvent, started.append)
        event_bus.subscribe(PlanningCompletedEvent, completed.append)

        engine = PlanningProcessEngine(event_bus, rng)
        method = engine.initiate_planning(
            "unit_a", _make_order(echelon=8), 100_000, ts=TS,
        )
        assert method == PlanningMethod.MDMP
        assert len(started) == 1

        # Phase 1: RECEIVING_MISSION -> tick past it
        timer = engine._states["unit_a"].phase_timer
        done = engine.update(timer + 1.0)
        assert ("unit_a", PlanningPhase.RECEIVING_MISSION) in done

        # Advance to ANALYZING
        engine.advance_phase("unit_a")
        assert engine.get_planning_status("unit_a") == PlanningPhase.ANALYZING

        # Inject analysis result, tick through ANALYZING
        engine.set_analysis_result("unit_a", {"mock": True})
        timer = engine._states["unit_a"].phase_timer
        engine.update(timer + 1.0)
        engine.advance_phase("unit_a")
        assert engine.get_planning_status("unit_a") == PlanningPhase.DEVELOPING_COA

        # Inject COAs, tick through DEVELOPING_COA
        engine.set_coas("unit_a", ["coa1", "coa2", "coa3"])
        timer = engine._states["unit_a"].phase_timer
        engine.update(timer + 1.0)
        engine.advance_phase("unit_a")
        assert engine.get_planning_status("unit_a") == PlanningPhase.COMPARING

        # Tick through COMPARING
        timer = engine._states["unit_a"].phase_timer
        engine.update(timer + 1.0)
        engine.advance_phase("unit_a")
        assert engine.get_planning_status("unit_a") == PlanningPhase.APPROVING

        # Select COA, tick through APPROVING
        engine.set_selected_coa("unit_a", "coa1")
        timer = engine._states["unit_a"].phase_timer
        engine.update(timer + 1.0)
        engine.advance_phase("unit_a")
        assert engine.get_planning_status("unit_a") == PlanningPhase.ISSUING_ORDERS

        # Tick through ISSUING_ORDERS
        timer = engine._states["unit_a"].phase_timer
        engine.update(timer + 1.0)

        # Complete
        engine.complete_planning("unit_a", ts=TS)
        assert engine.get_planning_status("unit_a") == PlanningPhase.COMPLETE
        assert len(completed) == 1
        assert completed[0].num_coas_evaluated == 3
        assert completed[0].duration_s > 0

    def test_full_intuitive_flow(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        """INTUITIVE flow skips COA development/comparison/approval."""
        engine = PlanningProcessEngine(event_bus, rng)
        method = engine.initiate_planning(
            "unit_a", _make_order(echelon=4), 100_000, ts=TS,
        )
        assert method == PlanningMethod.INTUITIVE

        # Tick past RECEIVING_MISSION
        timer = engine._states["unit_a"].phase_timer
        engine.update(timer + 1.0)
        engine.advance_phase("unit_a")
        assert engine.get_planning_status("unit_a") == PlanningPhase.ANALYZING

        # Tick past ANALYZING -> should skip to ISSUING_ORDERS
        timer = engine._states["unit_a"].phase_timer
        engine.update(timer + 1.0)
        phase = engine.advance_phase("unit_a")
        assert phase == PlanningPhase.ISSUING_ORDERS

        # Tick past ISSUING_ORDERS
        timer = engine._states["unit_a"].phase_timer
        engine.update(timer + 1.0)

        engine.complete_planning("unit_a", ts=TS)
        assert engine.get_planning_status("unit_a") == PlanningPhase.COMPLETE


# ---------------------------------------------------------------------------
# State checkpoint tests
# ---------------------------------------------------------------------------


class TestCheckpoint:
    """Test get_state / set_state round-trip."""

    def test_round_trip(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = PlanningProcessEngine(event_bus, rng)
        engine.initiate_planning("unit_a", _make_order(echelon=8), 100_000, ts=TS)
        engine.advance_phase("unit_a")
        engine.update(200.0)

        snapshot = engine.get_state()

        # Restore into a fresh engine
        engine2 = PlanningProcessEngine(event_bus, rng)
        engine2.set_state(snapshot)

        assert engine2.get_planning_status("unit_a") == PlanningPhase.ANALYZING
        assert engine2.get_method("unit_a") == PlanningMethod.MDMP
        state_orig = engine._states["unit_a"]
        state_rest = engine2._states["unit_a"]
        assert state_rest.phase_timer == pytest.approx(state_orig.phase_timer)
        assert state_rest.total_elapsed_s == pytest.approx(state_orig.total_elapsed_s)
        assert state_rest.available_time_s == pytest.approx(state_orig.available_time_s)
        assert state_rest.echelon_level == state_orig.echelon_level
        assert state_rest.order_id == state_orig.order_id


# ---------------------------------------------------------------------------
# Speed multiplier tests
# ---------------------------------------------------------------------------


class TestSpeedMultiplier:
    """Test that method speed multipliers affect phase duration."""

    def test_intuitive_faster_than_mdmp(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = PlanningProcessEngine(event_bus, rng)

        # MDMP battalion
        engine.initiate_planning(
            "mdmp_unit", _make_order(echelon=8, order_id="o1"), 100_000, ts=TS,
        )
        # INTUITIVE platoon
        engine.initiate_planning(
            "intuit_unit", _make_order(echelon=4, order_id="o2"), 100_000, ts=TS,
        )

        mdmp_timer = engine._states["mdmp_unit"].phase_timer
        intuit_timer = engine._states["intuit_unit"].phase_timer

        # INTUITIVE speed mult is 10x, so its timer should be 1/10 of MDMP
        assert mdmp_timer > intuit_timer
        assert intuit_timer == pytest.approx(mdmp_timer / 10.0)

    def test_custom_multiplier(self) -> None:
        cfg = PlanningProcessConfig(
            method_speed_multipliers={
                "INTUITIVE": 10.0,
                "DIRECTIVE": 5.0,
                "RAPID": 3.0,
                "MDMP": 2.0,  # double speed for MDMP
            },
        )
        engine = _make_engine(config=cfg)
        engine.initiate_planning(
            "unit_a", _make_order(echelon=8), 100_000, ts=TS,
        )
        # Base RECEIVING_MISSION = 300s, speed 2x -> 150s
        assert engine._states["unit_a"].phase_timer == pytest.approx(150.0)
