"""Typed evaluator consumption of production movement diagnostics."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.simulation.battle import (
    nearest_enemy_weapon_standoff,
)
from stochastic_warfare.simulation.movement_diagnostics import (
    MovementDiagnostics,
    MovementOrder,
    MovementReason,
    MovementUnitDiagnostics,
)


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
            "movement_expected_progress_count": (
                self.movement_expected_progress_count
            ),
            "movement_zero_progress_count": (
                self.movement_zero_progress_count
            ),
            "movement_positive_progress_count": (
                self.movement_positive_progress_count
            ),
            "movement_recent_observation_count": (
                self.movement_recent_observation_count
            ),
            "movement_dropped_observation_count": (
                self.movement_dropped_observation_count
            ),
            "movement_final_order": (
                dict(self.movement_final_order)
                if self.movement_final_order is not None
                else None
            ),
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
        return {
            unit.unit_id: unit.as_fields()
            for unit in self.units
        }


def _summary_evaluation(
    summary: MovementUnitDiagnostics,
    *,
    stuck: bool,
    resource_blocked: bool,
) -> MovementUnitEvaluation:
    return MovementUnitEvaluation(
        unit_id=summary.unit_id,
        movement_disposition=(
            summary.final_reason.value
            if summary.final_reason is not None
            else None
        ),
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
        movement_dropped_observation_count=(
            summary.dropped_observation_count
        ),
        movement_final_order=_order_fields(summary.final_order),
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
    materialized_by_side: dict[str, list[Unit]] = {}
    for side, side_units in units_by_side.items():
        if (
            not isinstance(side, str)
            or not side
            or side.strip() != side
        ):
            raise ValueError(
                "movement evaluator side names must be non-empty and have "
                "no surrounding whitespace",
            )
        materialized = list(side_units)
        materialized_by_side[side] = materialized
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
        expected_eligible = (
            active and summary.expected_progress_count > 0
        )
        stuck = (
            expected_eligible
            and summary.zero_progress_count
            == summary.expected_progress_count
            and summary.positive_progress_count == 0
        )
        if expected_eligible:
            stuck_population += 1
        if stuck:
            stuck_count += 1

        enemies = [
            enemy
            for other_side in sorted(materialized_by_side)
            if other_side != side
            for enemy in sorted(
                materialized_by_side[other_side],
                key=lambda candidate: candidate.entity_id,
            )
            if enemy.status == UnitStatus.ACTIVE
        ]
        nearest_index, nearest_distance, standoff = (
            nearest_enemy_weapon_standoff(
                unit,
                context,
                enemies,
            )
            if enemies
            else (None, float("inf"), 0.0)
        )
        blocked_candidate = (
            active
            and getattr(unit, "max_speed", 0.0) > 0.0
            and summary.decision_count > 0
            and nearest_index is not None
            and nearest_distance > standoff
        )
        resource_count = summary.reason_count(
            MovementReason.RESOURCE_BLOCKED,
        )
        resource_blocked = (
            blocked_candidate
            and resource_count == summary.decision_count
            and summary.positive_progress_count == 0
        )
        if blocked_candidate:
            blocked_population += 1
        if resource_blocked:
            blocked_units.append(unit.entity_id)

        per_unit.append(_summary_evaluation(
            summary,
            stuck=stuck,
            resource_blocked=resource_blocked,
        ))

    issues = [
        f"UNIT_MOVEMENT_BLOCKED({unit_id})"
        for unit_id in sorted(blocked_units)
    ]
    if stuck_population > 4 and stuck_count > stuck_population * 0.5:
        issues.append(
            f"MANY_STUCK_UNITS({stuck_count}/{stuck_population})",
        )
    if (
        blocked_population > 4
        and len(blocked_units) > blocked_population * 0.5
    ):
        issues.append(
            "MANY_MOVEMENT_BLOCKED"
            f"({len(blocked_units)}/{blocked_population})",
        )

    return MovementDiagnosticEvaluation(
        units=tuple(per_unit),
        issues=tuple(issues),
        stuck_count=stuck_count,
        stuck_population=stuck_population,
        resource_blocked_count=len(blocked_units),
        resource_blocked_population=blocked_population,
    )
