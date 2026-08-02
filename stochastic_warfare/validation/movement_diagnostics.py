"""Typed evaluator consumption of production movement diagnostics."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, fields
from typing import Any

from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.simulation.movement_diagnostics import (
    MovementDiagnostics,
    MovementHoldRevalidationOutcome,
    MovementOrder,
    MovementReason,
    MovementUnitDiagnostics,
)
from stochastic_warfare.simulation.tactical_targeting import (
    TacticalTargetingDecision,
    targeting_decision_to_state,
)

_PRIVILEGED_TARGETING_SCOPE = "PRIVILEGED_ENGINE"
_TARGETING_SCALAR_NAMES = tuple(item.name for item in fields(TacticalTargetingDecision))


def _order_fields(order: MovementOrder | None) -> dict[str, Any] | None:
    if order is None:
        return None
    return {
        "engine_tick": order.engine_tick,
        "stage": order.stage.value,
        "battle_id": order.battle_id,
        "side": order.side,
        "unit_id": order.unit_id,
        "ordinal": order.ordinal,
    }


def _targeting_fields(
    decision: TacticalTargetingDecision | None,
) -> dict[str, Any]:
    """Expose the recorded privileged decision without reconstructing it."""
    state = None if decision is None else targeting_decision_to_state(decision)
    if state is not None and set(state) != set(_TARGETING_SCALAR_NAMES):
        raise RuntimeError(
            "targeting decision codec disagrees with its typed scalar fields",
        )
    return {
        "targeting_exposure_scope": _PRIVILEGED_TARGETING_SCOPE,
        **{f"targeting_{name}": None if state is None else state[name] for name in _TARGETING_SCALAR_NAMES},
    }


def _hold_revalidation_fields(
    outcome: MovementHoldRevalidationOutcome | None,
) -> dict[str, Any]:
    """Expose the exact live movement hold check from recorded diagnostics."""
    return {
        "targeting_hold_revalidation_engine_tick": (
            None if outcome is None else outcome.engine_tick
        ),
        "targeting_hold_revalidation_battle_id": (
            None if outcome is None else outcome.battle_id
        ),
        "targeting_hold_revalidation_shooter_id": (
            None if outcome is None else outcome.shooter_id
        ),
        "targeting_hold_revalidation_target_id": (
            None if outcome is None else outcome.target_id
        ),
        "targeting_hold_revalidation_live_distance_m": (
            None if outcome is None else outcome.live_distance_m
        ),
        "targeting_hold_revalidation_disposition": (
            None if outcome is None else outcome.disposition.value
        ),
        "targeting_hold_revalidation_hold_authorized": (
            None if outcome is None else outcome.hold_authorized
        ),
    }


@dataclass(frozen=True, slots=True)
class MovementUnitEvaluation:
    """Evaluator-facing fields derived from one typed cumulative summary."""

    unit_id: str
    movement_disposition: str | None
    movement_reason_counts: dict[str, int]
    movement_decision_count: int
    movement_attempted_m: float
    movement_achieved_m: float
    movement_expected_progress_count: int
    movement_zero_progress_count: int
    movement_positive_progress_count: int
    movement_recent_observation_count: int
    movement_dropped_observation_count: int
    movement_final_order: dict[str, Any] | None
    targeting_decision: TacticalTargetingDecision | None
    hold_revalidation: MovementHoldRevalidationOutcome | None
    stuck: bool
    resource_blocked: bool

    def as_fields(self) -> dict[str, Any]:
        """Return fields suitable for a scenario evaluator unit row."""
        return {
            "movement_disposition": self.movement_disposition,
            "movement_reason_counts": dict(self.movement_reason_counts),
            "movement_decision_count": self.movement_decision_count,
            "movement_attempted_m": self.movement_attempted_m,
            "movement_achieved_m": self.movement_achieved_m,
            "movement_expected_progress_count": (self.movement_expected_progress_count),
            "movement_zero_progress_count": (self.movement_zero_progress_count),
            "movement_positive_progress_count": (self.movement_positive_progress_count),
            "movement_recent_observation_count": (self.movement_recent_observation_count),
            "movement_dropped_observation_count": (self.movement_dropped_observation_count),
            "movement_final_order": (
                dict(self.movement_final_order) if self.movement_final_order is not None else None
            ),
            **_targeting_fields(self.targeting_decision),
            **_hold_revalidation_fields(self.hold_revalidation),
        }


@dataclass(frozen=True, slots=True)
class MovementDiagnosticEvaluation:
    """Typed per-unit evaluator data and semantic issue codes."""

    units: tuple[MovementUnitEvaluation, ...]
    issues: tuple[str, ...]
    stuck_count: int
    stuck_population: int
    resource_blocked_count: int
    resource_blocked_population: int

    def fields_by_unit(self) -> dict[str, dict[str, Any]]:
        """Return stable unit-ID keyed evaluator fields."""
        return {unit.unit_id: unit.as_fields() for unit in self.units}


def _summary_evaluation(
    summary: MovementUnitDiagnostics,
    *,
    stuck: bool,
    resource_blocked: bool,
) -> MovementUnitEvaluation:
    return MovementUnitEvaluation(
        unit_id=summary.unit_id,
        movement_disposition=(summary.final_reason.value if summary.final_reason is not None else None),
        movement_reason_counts=summary.reason_counts_by_name(),
        movement_decision_count=summary.decision_count,
        movement_attempted_m=summary.total_attempted_m,
        movement_achieved_m=summary.total_achieved_m,
        movement_expected_progress_count=summary.expected_progress_count,
        movement_zero_progress_count=summary.zero_progress_count,
        movement_positive_progress_count=summary.positive_progress_count,
        movement_recent_observation_count=len(
            summary.recent_observations,
        ),
        movement_dropped_observation_count=(summary.dropped_observation_count),
        movement_final_order=_order_fields(summary.final_order),
        targeting_decision=(
            summary.recent_observations[-1].targeting_decision if summary.recent_observations else None
        ),
        hold_revalidation=(
            summary.recent_observations[-1].hold_revalidation
            if summary.recent_observations
            else None
        ),
        stuck=stuck,
        resource_blocked=resource_blocked,
    )


def evaluate_movement_diagnostics(
    diagnostics: MovementDiagnostics,
    units_by_side: Mapping[str, Iterable[Unit]],
    *,
    context: Any,
) -> MovementDiagnosticEvaluation:
    """Classify exact typed counters without inferring intent from displacement.

    ``units_by_side`` may be the complete production roster or a deliberately
    selected production-path control population.  Every supplied unit must
    already be registered in ``diagnostics`` with the same immutable side.
    """
    if not isinstance(diagnostics, MovementDiagnostics):
        raise TypeError("diagnostics must be a MovementDiagnostics")

    units: list[tuple[str, Unit]] = []
    seen_ids: set[str] = set()
    for side, side_units in units_by_side.items():
        if not isinstance(side, str) or not side or side.strip() != side:
            raise ValueError(
                "movement evaluator side names must be non-empty and have no surrounding whitespace",
            )
        materialized = list(side_units)
        for unit in materialized:
            if unit.entity_id in seen_ids:
                raise ValueError(
                    f"duplicate movement evaluator unit_id {unit.entity_id!r}",
                )
            seen_ids.add(unit.entity_id)
            if unit.side != side:
                raise ValueError(
                    f"movement evaluator side disagrees for {unit.entity_id!r}",
                )
            units.append((side, unit))

    stuck_population = 0
    stuck_count = 0
    blocked_population = 0
    blocked_units: list[str] = []
    per_unit: list[MovementUnitEvaluation] = []

    for side, unit in sorted(
        units,
        key=lambda item: (item[0], item[1].entity_id),
    ):
        summary = diagnostics.get_unit(unit.entity_id)
        if summary.side != side:
            raise ValueError(
                f"movement diagnostics side disagrees for {unit.entity_id!r}",
            )

        active = unit.status == UnitStatus.ACTIVE
        expected_eligible = active and summary.expected_progress_count > 0
        stuck = (
            expected_eligible
            and summary.zero_progress_count == summary.expected_progress_count
            and summary.positive_progress_count == 0
        )
        if expected_eligible:
            stuck_population += 1
        if stuck:
            stuck_count += 1

        # The evaluator observes manager-owned reasons only.  In particular it
        # must not recover a target or a range from ground truth and thereby
        # disagree with the targeting decision recorded at movement time.
        resource_count = summary.reason_count(
            MovementReason.RESOURCE_BLOCKED,
        )
        moved_count = summary.reason_count(MovementReason.MOVED)
        blocked_candidate = (
            active
            and getattr(unit, "max_speed", 0.0) > 0.0
            and summary.decision_count > 0
            and resource_count + moved_count == summary.decision_count
        )
        resource_blocked = (
            blocked_candidate and resource_count == summary.decision_count and summary.positive_progress_count == 0
        )
        if blocked_candidate:
            blocked_population += 1
        if resource_blocked:
            blocked_units.append(unit.entity_id)

        per_unit.append(
            _summary_evaluation(
                summary,
                stuck=stuck,
                resource_blocked=resource_blocked,
            )
        )

    # Kept as a keyword-only compatibility boundary for evaluator callers;
    # targeting and resource classification deliberately consume diagnostics.
    del context

    issues = [f"UNIT_MOVEMENT_BLOCKED({unit_id})" for unit_id in sorted(blocked_units)]
    if stuck_population > 4 and stuck_count > stuck_population * 0.5:
        issues.append(
            f"MANY_STUCK_UNITS({stuck_count}/{stuck_population})",
        )
    if blocked_population > 4 and len(blocked_units) > blocked_population * 0.5:
        issues.append(
            f"MANY_MOVEMENT_BLOCKED({len(blocked_units)}/{blocked_population})",
        )

    return MovementDiagnosticEvaluation(
        units=tuple(per_unit),
        issues=tuple(issues),
        stuck_count=stuck_count,
        stuck_population=stuck_population,
        resource_blocked_count=len(blocked_units),
        resource_blocked_population=blocked_population,
    )
