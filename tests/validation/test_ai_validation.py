"""Tests for validation.ai_validation — AI decision quality analysis."""

from __future__ import annotations

from datetime import datetime, timezone


from stochastic_warfare.core.events import EventBus
from stochastic_warfare.simulation.recorder import RecordedEvent, SimulationRecorder
from stochastic_warfare.validation.ai_validation import (
    AIDecisionRecord,
    AIDecisionValidator,
    AIValidationResult,
    ExpectationResult,
    _matches_posture,
)
from stochastic_warfare.validation.campaign_data import AIExpectation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TS = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _make_recorded_event(
    tick: int,
    event_type: str,
    data: dict | None = None,
) -> RecordedEvent:
    """Create a RecordedEvent for testing."""
    return RecordedEvent(
        tick=tick,
        timestamp=_TS,
        event_type=event_type,
        source="CORE",
        data=data or {},
    )


def _make_recorder_with_events(events: list[RecordedEvent]) -> SimulationRecorder:
    """Create a recorder pre-populated with events."""
    bus = EventBus()
    recorder = SimulationRecorder(bus)
    recorder._events = list(events)
    return recorder


# ===========================================================================
# Posture matching
# ===========================================================================


class TestMatchesPosture:
    def test_attack_actions(self):
        assert _matches_posture("ATTACK", "attack")
        assert _matches_posture("FLANK", "attack")
        assert _matches_posture("ENVELOP", "attack")
        assert _matches_posture("PENETRATE", "attack")

    def test_defend_actions(self):
        assert _matches_posture("DEFEND", "defend")
        assert _matches_posture("HOLD", "defend")
        assert _matches_posture("DELAY", "defend")
        assert _matches_posture("AREA_DEFENSE", "defend")

    def test_withdraw_actions(self):
        assert _matches_posture("WITHDRAW", "withdraw")
        assert _matches_posture("RETREAT", "withdraw")
        assert _matches_posture("DISENGAGE", "withdraw")

    def test_culminate_includes_defend(self):
        assert _matches_posture("DEFEND", "culminate")
        assert _matches_posture("HOLD", "culminate")

    def test_culminate_includes_withdraw(self):
        assert _matches_posture("WITHDRAW", "culminate")
        assert _matches_posture("RETREAT", "culminate")

    def test_no_match(self):
        assert not _matches_posture("ATTACK", "defend")
        assert not _matches_posture("DEFEND", "attack")

    def test_case_insensitive(self):
        assert _matches_posture("attack", "attack")
        assert _matches_posture("Attack", "attack")

    def test_custom_posture_substring(self):
        assert _matches_posture("ADVANCE_GUARD", "advance")
        assert not _matches_posture("DEFEND", "advance")


# ===========================================================================
# Decision extraction
# ===========================================================================


class TestExtractDecisions:
    def test_extracts_decision_made_event(self):
        events = [
            _make_recorded_event(10, "DecisionMadeEvent", {
                "unit_id": "cmd_1",
                "decision_type": "ATTACK",
                "echelon_level": 5,
                "confidence": 0.8,
            }),
        ]
        recorder = _make_recorder_with_events(events)
        decisions = AIDecisionValidator.extract_decisions(recorder)
        assert len(decisions) == 1
        assert decisions[0].commander_id == "cmd_1"
        assert decisions[0].action_chosen == "ATTACK"

    def test_extracts_plan_adapted_event(self):
        events = [
            _make_recorded_event(20, "PlanAdaptedEvent", {
                "unit_id": "cmd_2",
                "trigger": "CASUALTIES",
                "action": "WITHDRAW",
                "frago_order_id": "o1",
            }),
        ]
        recorder = _make_recorder_with_events(events)
        decisions = AIDecisionValidator.extract_decisions(recorder)
        assert len(decisions) == 1
        assert decisions[0].action_chosen == "WITHDRAW"

    def test_extracts_ooda_phase_change(self):
        events = [
            _make_recorded_event(5, "OODAPhaseChangeEvent", {
                "unit_id": "cmd_1",
                "old_phase": 0,
                "new_phase": 2,
                "cycle_number": 1,
            }),
        ]
        recorder = _make_recorder_with_events(events)
        decisions = AIDecisionValidator.extract_decisions(recorder)
        assert len(decisions) == 1
        assert "OODA_" in decisions[0].action_chosen

    def test_extracts_coa_selected(self):
        events = [
            _make_recorded_event(15, "COASelectedEvent", {
                "unit_id": "cmd_1",
                "coa_id": "coa_attack_north",
                "score": 0.7,
                "risk_level": "MODERATE",
            }),
        ]
        recorder = _make_recorder_with_events(events)
        decisions = AIDecisionValidator.extract_decisions(recorder)
        assert len(decisions) == 1
        assert decisions[0].action_chosen == "coa_attack_north"

    def test_ignores_non_ai_events(self):
        events = [
            _make_recorded_event(1, "EngagementEvent", {"weapon_id": "gun"}),
            _make_recorded_event(2, "MoraleChangeEvent", {}),
        ]
        recorder = _make_recorder_with_events(events)
        decisions = AIDecisionValidator.extract_decisions(recorder)
        assert len(decisions) == 0

    def test_multiple_events_sorted_by_timestamp(self):
        events = [
            _make_recorded_event(20, "DecisionMadeEvent", {
                "unit_id": "cmd_1", "decision_type": "DEFEND",
            }),
            _make_recorded_event(5, "DecisionMadeEvent", {
                "unit_id": "cmd_1", "decision_type": "ATTACK",
            }),
        ]
        recorder = _make_recorder_with_events(events)
        decisions = AIDecisionValidator.extract_decisions(recorder)
        assert len(decisions) == 2
        assert decisions[0].timestamp_s < decisions[1].timestamp_s

    def test_empty_recorder(self):
        recorder = _make_recorder_with_events([])
        decisions = AIDecisionValidator.extract_decisions(recorder)
        assert len(decisions) == 0

    def test_mixed_event_types(self):
        events = [
            _make_recorded_event(1, "DecisionMadeEvent", {
                "unit_id": "cmd_1", "decision_type": "ATTACK",
            }),
            _make_recorded_event(2, "SituationAssessedEvent", {
                "unit_id": "cmd_1", "overall_rating": 2, "confidence": 0.6,
            }),
            _make_recorded_event(3, "EngagementEvent", {}),
            _make_recorded_event(4, "PlanAdaptedEvent", {
                "unit_id": "cmd_1", "action": "HOLD",
            }),
        ]
        recorder = _make_recorder_with_events(events)
        decisions = AIDecisionValidator.extract_decisions(recorder)
        # Should include DecisionMade, SituationAssessed, PlanAdapted but not Engagement
        assert len(decisions) == 3


# ===========================================================================
# Expectation validation
# ===========================================================================


class TestValidateExpectations:
    def test_single_matching_expectation(self):
        decisions = [
            AIDecisionRecord("cmd_1", 100, "DecisionMadeEvent", "ATTACK"),
            AIDecisionRecord("cmd_1", 200, "DecisionMadeEvent", "FLANK"),
        ]
        expectations = [
            AIExpectation(
                side="red",
                time_range_s=[0, 500],
                expected_posture="attack",
                tolerance="moderate",
            ),
        ]
        result = AIDecisionValidator.validate_expectations(decisions, expectations)
        assert len(result.expectation_results) == 1
        assert result.expectation_results[0].passed

    def test_failing_expectation(self):
        decisions = [
            AIDecisionRecord("cmd_1", 100, "DecisionMadeEvent", "DEFEND"),
            AIDecisionRecord("cmd_1", 200, "DecisionMadeEvent", "HOLD"),
        ]
        expectations = [
            AIExpectation(
                side="red",
                time_range_s=[0, 500],
                expected_posture="attack",
                tolerance="moderate",
            ),
        ]
        result = AIDecisionValidator.validate_expectations(decisions, expectations)
        assert len(result.expectation_results) == 1
        assert not result.expectation_results[0].passed

    def test_strict_tolerance_requires_80_percent(self):
        # 3/4 = 75% < 80% → fail for strict
        decisions = [
            AIDecisionRecord("cmd_1", 100, "DecisionMadeEvent", "ATTACK"),
            AIDecisionRecord("cmd_1", 200, "DecisionMadeEvent", "ATTACK"),
            AIDecisionRecord("cmd_1", 300, "DecisionMadeEvent", "ATTACK"),
            AIDecisionRecord("cmd_1", 400, "DecisionMadeEvent", "DEFEND"),
        ]
        expectations = [
            AIExpectation(
                side="red",
                time_range_s=[0, 500],
                expected_posture="attack",
                tolerance="strict",
            ),
        ]
        result = AIDecisionValidator.validate_expectations(decisions, expectations)
        assert not result.expectation_results[0].passed

    def test_loose_tolerance_requires_20_percent(self):
        # 1/4 = 25% >= 20% → pass for loose
        decisions = [
            AIDecisionRecord("cmd_1", 100, "DecisionMadeEvent", "ATTACK"),
            AIDecisionRecord("cmd_1", 200, "DecisionMadeEvent", "DEFEND"),
            AIDecisionRecord("cmd_1", 300, "DecisionMadeEvent", "DEFEND"),
            AIDecisionRecord("cmd_1", 400, "DecisionMadeEvent", "DEFEND"),
        ]
        expectations = [
            AIExpectation(
                side="red",
                time_range_s=[0, 500],
                expected_posture="attack",
                tolerance="loose",
            ),
        ]
        result = AIDecisionValidator.validate_expectations(decisions, expectations)
        assert result.expectation_results[0].passed

    def test_no_decisions_in_window_loose_passes(self):
        decisions = []
        expectations = [
            AIExpectation(
                side="red",
                time_range_s=[0, 500],
                expected_posture="attack",
                tolerance="loose",
            ),
        ]
        result = AIDecisionValidator.validate_expectations(decisions, expectations)
        assert result.expectation_results[0].passed

    def test_no_decisions_in_window_moderate_fails(self):
        decisions = []
        expectations = [
            AIExpectation(
                side="red",
                time_range_s=[0, 500],
                expected_posture="attack",
                tolerance="moderate",
            ),
        ]
        result = AIDecisionValidator.validate_expectations(decisions, expectations)
        assert not result.expectation_results[0].passed

    def test_time_window_filtering(self):
        decisions = [
            AIDecisionRecord("cmd_1", 50, "DecisionMadeEvent", "ATTACK"),
            AIDecisionRecord("cmd_1", 600, "DecisionMadeEvent", "DEFEND"),
        ]
        expectations = [
            AIExpectation(
                side="red",
                time_range_s=[0, 100],
                expected_posture="attack",
                tolerance="moderate",
            ),
        ]
        result = AIDecisionValidator.validate_expectations(decisions, expectations)
        # Only the first decision in window
        assert result.expectation_results[0].decisions_in_window == 1
        assert result.expectation_results[0].passed

    def test_side_unit_filtering(self):
        decisions = [
            AIDecisionRecord("blue_cmd", 100, "DecisionMadeEvent", "ATTACK"),
            AIDecisionRecord("red_cmd", 200, "DecisionMadeEvent", "DEFEND"),
        ]
        expectations = [
            AIExpectation(
                side="red",
                time_range_s=[0, 500],
                expected_posture="defend",
                tolerance="moderate",
            ),
        ]
        side_units = {"red": ["red_cmd"], "blue": ["blue_cmd"]}
        result = AIDecisionValidator.validate_expectations(
            decisions, expectations, side_units
        )
        # Only red_cmd's DEFEND should be considered
        assert result.expectation_results[0].decisions_in_window == 1
        assert result.expectation_results[0].passed

    def test_multiple_expectations(self):
        decisions = [
            AIDecisionRecord("cmd_1", 100, "DecisionMadeEvent", "ATTACK"),
            AIDecisionRecord("cmd_1", 200, "DecisionMadeEvent", "ATTACK"),
            AIDecisionRecord("cmd_2", 300, "DecisionMadeEvent", "DEFEND"),
        ]
        expectations = [
            AIExpectation(
                side="red",
                time_range_s=[0, 250],
                expected_posture="attack",
                tolerance="moderate",
            ),
            AIExpectation(
                side="blue",
                time_range_s=[250, 500],
                expected_posture="defend",
                tolerance="moderate",
            ),
        ]
        result = AIDecisionValidator.validate_expectations(decisions, expectations)
        assert len(result.expectation_results) == 2

    def test_decision_distribution(self):
        decisions = [
            AIDecisionRecord("cmd_1", 100, "DecisionMadeEvent", "ATTACK"),
            AIDecisionRecord("cmd_1", 200, "DecisionMadeEvent", "DEFEND"),
            AIDecisionRecord("cmd_1", 300, "PlanAdaptedEvent", "WITHDRAW"),
        ]
        result = AIDecisionValidator.validate_expectations(decisions, [])
        assert result.decision_distribution["DecisionMadeEvent"] == 2
        assert result.decision_distribution["PlanAdaptedEvent"] == 1

    def test_deficiencies_populated(self):
        decisions = [
            AIDecisionRecord("cmd_1", 100, "DecisionMadeEvent", "DEFEND"),
        ]
        expectations = [
            AIExpectation(
                side="red",
                time_range_s=[0, 500],
                expected_posture="attack",
                tolerance="strict",
            ),
        ]
        result = AIDecisionValidator.validate_expectations(decisions, expectations)
        assert len(result.deficiencies) == 1
        assert "FAILED" in result.deficiencies[0]

    def test_all_passed_property(self):
        decisions = [
            AIDecisionRecord("cmd_1", 100, "DecisionMadeEvent", "ATTACK"),
        ]
        expectations = [
            AIExpectation(
                side="red",
                time_range_s=[0, 500],
                expected_posture="attack",
                tolerance="loose",
            ),
        ]
        result = AIDecisionValidator.validate_expectations(decisions, expectations)
        assert result.all_passed


# ===========================================================================
# Summary formatting
# ===========================================================================


class TestSummarize:
    def test_summary_format(self):
        result = AIValidationResult(
            total_decisions=5,
            decision_distribution={"DecisionMadeEvent": 3, "PlanAdaptedEvent": 2},
            expectation_results=[
                ExpectationResult(
                    expectation=AIExpectation(
                        side="red",
                        time_range_s=[0, 100],
                        expected_posture="attack",
                    ),
                    decisions_in_window=3,
                    matching_decisions=2,
                    passed=True,
                ),
            ],
            deficiencies=[],
        )
        summary = AIDecisionValidator.summarize(result)
        assert "5" in summary  # total decisions
        assert "PASS" in summary
        assert "DecisionMadeEvent" in summary

    def test_summary_with_failures(self):
        result = AIValidationResult(
            total_decisions=2,
            decision_distribution={"DecisionMadeEvent": 2},
            expectation_results=[
                ExpectationResult(
                    expectation=AIExpectation(
                        side="red",
                        time_range_s=[0, 100],
                        expected_posture="attack",
                    ),
                    decisions_in_window=2,
                    matching_decisions=0,
                    passed=False,
                ),
            ],
            deficiencies=["AI expectation FAILED: test"],
        )
        summary = AIDecisionValidator.summarize(result)
        assert "FAIL" in summary
        assert "Deficiencies" in summary

    def test_empty_result(self):
        result = AIValidationResult(
            total_decisions=0,
            decision_distribution={},
            expectation_results=[],
            deficiencies=[],
        )
        summary = AIDecisionValidator.summarize(result)
        assert "0" in summary
