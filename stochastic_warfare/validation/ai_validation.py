"""AI decision quality validation for campaign runs.

Extracts AI decision events from :class:`SimulationRecorder` output and
validates that commanders made contextually appropriate decisions during
the campaign.  Checks against :class:`AIExpectation` entries from the
campaign YAML.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.simulation.recorder import RecordedEvent, SimulationRecorder
from stochastic_warfare.validation.campaign_data import AIExpectation

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# AI event type names that we look for in the recorder
# ---------------------------------------------------------------------------

_AI_EVENT_TYPES = frozenset({
    "OODAPhaseChangeEvent",
    "OODALoopResetEvent",
    "SituationAssessedEvent",
    "DecisionMadeEvent",
    "PlanAdaptedEvent",
    "StratagemActivatedEvent",
    "PlanningStartedEvent",
    "PlanningCompletedEvent",
    "COASelectedEvent",
    "PhaseTransitionEvent",
})

# Decision types that map to postures for expectation matching
_ATTACK_ACTIONS = frozenset({
    "ATTACK", "FLANK", "ENVELOP", "PENETRATE",
    "DEEP_STRIKE", "PURSUIT", "OFFENSIVE", "ASSAULT",
    "OPERATIONAL_MANEUVER", "EXPLOITATION",
    "attack", "flank", "envelop", "penetrate",
})

_DEFEND_ACTIONS = frozenset({
    "DEFEND", "DELAY", "HOLD", "AREA_DEFENSE",
    "MOBILE_DEFENSE", "DEFENSIVE", "RETROGRADE",
    "defend", "delay", "hold",
})

_WITHDRAW_ACTIONS = frozenset({
    "WITHDRAW", "RETREAT", "DISENGAGE", "RETROGRADE",
    "withdraw", "retreat", "disengage",
})


# ---------------------------------------------------------------------------
# Data records
# ---------------------------------------------------------------------------


@dataclass
class AIDecisionRecord:
    """Extracted AI decision from recorder events."""

    commander_id: str
    timestamp_s: float
    event_type: str
    action_chosen: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExpectationResult:
    """Result of checking one AI expectation against recorded decisions."""

    expectation: AIExpectation
    decisions_in_window: int
    matching_decisions: int
    passed: bool


@dataclass
class AIValidationResult:
    """Complete AI validation result for a campaign run."""

    total_decisions: int
    decision_distribution: dict[str, int]
    expectation_results: list[ExpectationResult]
    deficiencies: list[str]

    @property
    def all_passed(self) -> bool:
        """True if all expectations passed."""
        return all(r.passed for r in self.expectation_results)


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


class AIDecisionValidator:
    """Validate AI decision quality from campaign recorder output."""

    @staticmethod
    def extract_decisions(recorder: SimulationRecorder) -> list[AIDecisionRecord]:
        """Extract AI decision records from recorder events.

        Scans for event types in ``_AI_EVENT_TYPES`` and converts
        them to :class:`AIDecisionRecord` instances.

        Parameters
        ----------
        recorder:
            The simulation recorder with captured events.

        Returns
        -------
        list[AIDecisionRecord]
            Extracted decision records sorted by timestamp.
        """
        decisions: list[AIDecisionRecord] = []

        for event in recorder.events:
            if event.event_type not in _AI_EVENT_TYPES:
                continue

            commander_id = event.data.get("unit_id", "")
            timestamp_s = event.tick * 5.0  # approximate from tick

            # Extract action from event data
            action = ""
            if event.event_type == "DecisionMadeEvent":
                action = event.data.get("decision_type", "")
            elif event.event_type == "PlanAdaptedEvent":
                action = event.data.get("action", "")
            elif event.event_type == "COASelectedEvent":
                action = event.data.get("coa_id", "")
            elif event.event_type == "OODAPhaseChangeEvent":
                action = f"OODA_{event.data.get('new_phase', '')}"
            elif event.event_type == "StratagemActivatedEvent":
                action = event.data.get("stratagem_type", "")
            elif event.event_type == "PhaseTransitionEvent":
                action = event.data.get("new_phase", "")
            else:
                action = event.event_type

            decisions.append(
                AIDecisionRecord(
                    commander_id=commander_id,
                    timestamp_s=timestamp_s,
                    event_type=event.event_type,
                    action_chosen=action,
                    context=dict(event.data),
                )
            )

        decisions.sort(key=lambda d: d.timestamp_s)
        return decisions

    @staticmethod
    def validate_expectations(
        decisions: list[AIDecisionRecord],
        expectations: list[AIExpectation],
        side_units: dict[str, list[str]] | None = None,
    ) -> AIValidationResult:
        """Check decisions against AI expectations.

        Parameters
        ----------
        decisions:
            Extracted AI decision records.
        expectations:
            Expected AI behavior from campaign YAML.
        side_units:
            Mapping of side name to list of commander unit IDs.
            If None, all decisions are checked against all expectations.

        Returns
        -------
        AIValidationResult
            Validation result with per-expectation pass/fail.
        """
        # Build decision distribution
        distribution: dict[str, int] = {}
        for d in decisions:
            distribution[d.event_type] = distribution.get(d.event_type, 0) + 1

        # Check each expectation
        results: list[ExpectationResult] = []
        deficiencies: list[str] = []

        for exp in expectations:
            # Filter decisions in time window
            start_s, end_s = exp.time_range_s
            window_decisions = [
                d for d in decisions
                if start_s <= d.timestamp_s <= end_s
            ]

            # If side_units provided, filter by side
            if side_units is not None:
                side_ids = set(side_units.get(exp.side, []))
                if side_ids:
                    window_decisions = [
                        d for d in window_decisions
                        if d.commander_id in side_ids
                    ]

            # Count matching decisions
            matching = 0
            for d in window_decisions:
                if _matches_posture(d.action_chosen, exp.expected_posture):
                    matching += 1

            # Determine threshold based on tolerance
            thresholds = {"strict": 0.8, "moderate": 0.5, "loose": 0.2}
            threshold = thresholds.get(exp.tolerance, 0.5)

            total = len(window_decisions)
            if total == 0:
                # No decisions in window — pass for loose, fail otherwise
                passed = exp.tolerance == "loose"
            else:
                ratio = matching / total
                passed = ratio >= threshold

            results.append(
                ExpectationResult(
                    expectation=exp,
                    decisions_in_window=total,
                    matching_decisions=matching,
                    passed=passed,
                )
            )

            if not passed:
                deficiencies.append(
                    f"AI expectation FAILED: {exp.side} expected {exp.expected_posture} "
                    f"in [{start_s:.0f}s, {end_s:.0f}s] — "
                    f"{matching}/{total} matching ({exp.tolerance} tolerance)"
                )

        return AIValidationResult(
            total_decisions=len(decisions),
            decision_distribution=distribution,
            expectation_results=results,
            deficiencies=deficiencies,
        )

    @staticmethod
    def summarize(result: AIValidationResult) -> str:
        """Human-readable summary of AI validation results."""
        lines = [
            f"AI Decision Validation: {len(result.expectation_results)} expectations",
            f"  Total decisions recorded: {result.total_decisions}",
            "",
            "  Decision distribution:",
        ]
        for etype, count in sorted(result.decision_distribution.items()):
            lines.append(f"    {etype}: {count}")
        lines.append("")

        passed = sum(1 for r in result.expectation_results if r.passed)
        total = len(result.expectation_results)
        lines.append(f"  Expectations: {passed}/{total} passed")

        for r in result.expectation_results:
            status = "PASS" if r.passed else "FAIL"
            exp = r.expectation
            lines.append(
                f"    [{status}] {exp.side} {exp.expected_posture} "
                f"[{exp.time_range_s[0]:.0f}s-{exp.time_range_s[1]:.0f}s]: "
                f"{r.matching_decisions}/{r.decisions_in_window} "
                f"({exp.tolerance})"
            )

        if result.deficiencies:
            lines.append("")
            lines.append("  Deficiencies:")
            for d in result.deficiencies:
                lines.append(f"    - {d}")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _matches_posture(action: str, expected_posture: str) -> bool:
    """Check if an action string matches the expected posture."""
    action_upper = action.upper()

    if expected_posture == "attack":
        return action_upper in {a.upper() for a in _ATTACK_ACTIONS}
    elif expected_posture == "defend":
        return action_upper in {a.upper() for a in _DEFEND_ACTIONS}
    elif expected_posture == "withdraw":
        return action_upper in {a.upper() for a in _WITHDRAW_ACTIONS}
    elif expected_posture == "culminate":
        # Culmination can look like defend or withdraw
        return (
            action_upper in {a.upper() for a in _DEFEND_ACTIONS}
            or action_upper in {a.upper() for a in _WITHDRAW_ACTIONS}
        )
    else:
        # Custom posture — check if action contains it
        return expected_posture.lower() in action.lower()
