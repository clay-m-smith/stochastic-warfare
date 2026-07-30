"""Strict production analysis-run boundary.

Sensitivity, comparison, API, and MCP consumers use this module to execute
fresh sessions prepared by :mod:`stochastic_warfare.simulation.runtime`.
Unsupported metrics and incomplete runs fail instead of acquiring plausible
zero values.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from stochastic_warfare.entities.base import UnitStatus
from stochastic_warfare.simulation.engine import SimulationRunResult
from stochastic_warfare.simulation.runtime import (
    AnalysisInputError,
    AnalysisVariant,
    CodeRevision,
    PreparedScenario,
    RuntimeProvenance,
    RuntimeSession,
    SimulationRuntimeFactory,
    UnitCommandAssignment,
)


@dataclass(frozen=True)
class AnalysisRunRecord:
    """Public provenance and outcome for one completed production run."""

    variant_id: str
    seed: int
    ticks_executed: int
    duration_s: float
    winning_side: str
    condition_type: str
    game_over: bool
    source_fingerprint: str
    config_fingerprint: str
    authored_roster: tuple[tuple[str, int], ...]
    loaded_roster: tuple[tuple[str, int], ...]
    runtime_provenance: RuntimeProvenance


@dataclass(frozen=True)
class AnalysisBatchResult:
    """Complete immutable evidence for one variant and ordered seed sequence."""

    scenario_path: str
    data_root: str
    variant_id: str
    ordered_metrics: tuple[str, ...]
    base_seed: int
    seeds: tuple[int, ...]
    max_ticks: int
    source_fingerprint: str
    config_fingerprint: str
    authored_roster: tuple[tuple[str, int], ...]
    loaded_roster: tuple[tuple[str, int], ...]
    code_revision: CodeRevision
    data_revision: str
    data_file_count: int
    catalog_revision: str
    doctrine_catalog_fingerprint: str
    loaded_roster_loadout_fingerprint: str
    initial_unit_assignments: tuple[UnitCommandAssignment, ...]
    metric_vectors: tuple[tuple[str, tuple[float, ...]], ...]
    runs: tuple[AnalysisRunRecord, ...]

    def metric_values(self, metric: str) -> tuple[float, ...]:
        """Return one exact metric vector or reject an absent key."""
        for name, values in self.metric_vectors:
            if name == metric:
                return values
        raise ValueError(f"Missing analysis metric vector {metric!r}")

    def metrics_dict(self) -> dict[str, list[float]]:
        """Return a serialization-compatible copy of the exact vectors."""
        return {metric: list(values) for metric, values in self.metric_vectors}

    def statistics_dict(self) -> dict[str, dict[str, float | int]]:
        """Derive the shared public statistics from exact metric vectors."""
        return _statistics_for_metric_vectors(
            self.metrics_dict(),
            ordered_metrics=self.ordered_metrics,
            expected_count=len(self.seeds),
        )

    def provenance_dict(self) -> dict[str, Any]:
        """Return the exact durable Python/MCP/HTTP provenance contract."""
        return {
            "scenario_path": self.scenario_path,
            "data_root": self.data_root,
            "variant_id": self.variant_id,
            "ordered_metrics": list(self.ordered_metrics),
            "base_seed": self.base_seed,
            "seeds": list(self.seeds),
            "max_ticks": self.max_ticks,
            "source_fingerprint": self.source_fingerprint,
            "config_fingerprint": self.config_fingerprint,
            "authored_roster": self.authored_roster,
            "loaded_roster": self.loaded_roster,
            "code_revision": asdict(self.code_revision),
            "data_revision": self.data_revision,
            "data_file_count": self.data_file_count,
            "catalog_revision": self.catalog_revision,
            "doctrine_catalog_fingerprint": (self.doctrine_catalog_fingerprint),
            "loaded_roster_loadout_fingerprint": (self.loaded_roster_loadout_fingerprint),
            "initial_unit_assignments": [asdict(assignment) for assignment in self.initial_unit_assignments],
            "runs": [asdict(run) for run in self.runs],
        }


_STATISTIC_FIELDS = frozenset(
    {
        "mean",
        "median",
        "std",
        "min",
        "max",
        "p5",
        "p95",
        "n",
    },
)
_BATCH_PAYLOAD_FIELDS = frozenset(
    {
        "statistics",
        "raw_metrics",
        "ordered_metrics",
        "provenance",
    },
)
_BATCH_PROVENANCE_FIELDS = frozenset(
    {
        "scenario_path",
        "data_root",
        "variant_id",
        "ordered_metrics",
        "base_seed",
        "seeds",
        "max_ticks",
        "source_fingerprint",
        "config_fingerprint",
        "authored_roster",
        "loaded_roster",
        "code_revision",
        "data_revision",
        "data_file_count",
        "catalog_revision",
        "doctrine_catalog_fingerprint",
        "loaded_roster_loadout_fingerprint",
        "initial_unit_assignments",
        "runs",
    },
)
_ANALYSIS_RUN_FIELDS = frozenset(
    {
        "variant_id",
        "seed",
        "ticks_executed",
        "duration_s",
        "winning_side",
        "condition_type",
        "game_over",
        "source_fingerprint",
        "config_fingerprint",
        "authored_roster",
        "loaded_roster",
        "runtime_provenance",
    },
)
_RUNTIME_PROVENANCE_FIELDS = frozenset(
    {
        "code_revision",
        "data_revision",
        "data_file_count",
        "catalog_revision",
        "doctrine_catalog_fingerprint",
        "doctrine_assignment_fingerprint",
        "loaded_roster_loadout_fingerprint",
        "final_roster_loadout_fingerprint",
        "initial_unit_assignments",
        "arriving_unit_assignments",
    },
)
_CODE_REVISION_FIELDS = frozenset(
    {
        "commit",
        "dirty",
        "worktree_fingerprint",
    },
)
_UNIT_ASSIGNMENT_FIELDS = frozenset(
    {
        "unit_id",
        "side",
        "commander_profile_id",
        "doctrine_school_id",
    },
)
_TERMINAL_CONDITION_TYPES = frozenset(
    {
        "attrition_ratio",
        "force_destroyed",
        "max_ticks",
        "morale_collapsed",
        "supply_exhausted",
        "territory_control",
        "time_expired",
    },
)


def _exact_mapping(
    value: Any,
    *,
    fields: frozenset[str],
    path: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must be a mapping")
    actual = set(value)
    if actual != fields:
        raise ValueError(
            f"{path} fields mismatch: "
            f"missing={sorted(fields - actual)!r}, "
            f"extra={sorted(actual - fields)!r}",
        )
    return value


def _digest(value: Any, *, path: str, length: int = 64) -> str:
    if (
        not isinstance(value, str)
        or len(value) != length
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(
            f"{path} must be a {length}-character lowercase hex digest",
        )
    return value


def _trimmed_text(value: Any, *, path: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
    ):
        raise ValueError(f"{path} must be a non-empty trimmed string")
    return value


def _strict_int(
    value: Any,
    *,
    path: str,
    minimum: int = 0,
) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < minimum
    ):
        raise ValueError(
            f"{path} must be a strict integer >= {minimum}",
        )
    return value


def _strict_finite_number(value: Any, *, path: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
    ):
        raise ValueError(f"{path} must be a finite integer or float")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(
            f"{path} must be a finite integer or float",
        ) from exc
    if not math.isfinite(number):
        raise ValueError(f"{path} must be a finite integer or float")
    return number


def _validated_roster(
    value: Any,
    *,
    path: str,
) -> tuple[tuple[str, int], ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError(f"{path} must be a non-empty ordered roster")
    roster: list[tuple[str, int]] = []
    for index, entry in enumerate(value):
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            raise ValueError(
                f"{path}[{index}] must contain [side, unit_count]",
            )
        side = _trimmed_text(
            entry[0],
            path=f"{path}[{index}].side",
        )
        count = _strict_int(
            entry[1],
            path=f"{path}[{index}].unit_count",
            minimum=1,
        )
        roster.append((side, count))
    sides = [side for side, _ in roster]
    if len(sides) != len(set(sides)):
        raise ValueError(f"{path} contains duplicate sides")
    return tuple(roster)


def _validated_code_revision(
    value: Any,
    *,
    path: str,
) -> tuple[str, bool, str]:
    revision = _exact_mapping(
        value,
        fields=_CODE_REVISION_FIELDS,
        path=path,
    )
    commit = _digest(
        revision["commit"],
        path=f"{path}.commit",
        length=40,
    )
    dirty = revision["dirty"]
    if not isinstance(dirty, bool):
        raise ValueError(f"{path}.dirty must be a boolean")
    fingerprint = _digest(
        revision["worktree_fingerprint"],
        path=f"{path}.worktree_fingerprint",
    )
    return commit, dirty, fingerprint


def _validated_assignments(
    value: Any,
    *,
    path: str,
    require_nonempty: bool,
) -> tuple[tuple[str, str, str | None, str | None], ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{path} must be an ordered list")
    if require_nonempty and not value:
        raise ValueError(f"{path} must be non-empty")
    assignments: list[tuple[str, str, str | None, str | None]] = []
    for index, raw_assignment in enumerate(value):
        assignment = _exact_mapping(
            raw_assignment,
            fields=_UNIT_ASSIGNMENT_FIELDS,
            path=f"{path}[{index}]",
        )
        profile = assignment["commander_profile_id"]
        school = assignment["doctrine_school_id"]
        for field_name, optional_value in (
            ("commander_profile_id", profile),
            ("doctrine_school_id", school),
        ):
            if optional_value is not None:
                _trimmed_text(
                    optional_value,
                    path=f"{path}[{index}].{field_name}",
                )
        assignments.append(
            (
                _trimmed_text(
                    assignment["unit_id"],
                    path=f"{path}[{index}].unit_id",
                ),
                _trimmed_text(
                    assignment["side"],
                    path=f"{path}[{index}].side",
                ),
                profile,
                school,
            ),
        )
    unit_ids = [assignment[0] for assignment in assignments]
    if len(unit_ids) != len(set(unit_ids)):
        raise ValueError(f"{path} contains duplicate unit IDs")
    return tuple(assignments)


def _statistics_for_metric_vectors(
    raw_metrics: Mapping[str, Sequence[float]],
    *,
    ordered_metrics: Sequence[str],
    expected_count: int,
) -> dict[str, dict[str, float | int]]:
    import numpy as np

    statistics: dict[str, dict[str, float | int]] = {}
    for metric in ordered_metrics:
        values = raw_metrics[metric]
        if len(values) != expected_count:
            raise ValueError(
                f"Metric {metric!r} is partial: "
                f"{len(values)}/{expected_count} values",
            )
        strict_values = [
            _strict_finite_number(
                value,
                path=f"raw_metrics.{metric}[{index}]",
            )
            for index, value in enumerate(values)
        ]
        array = np.asarray(strict_values, dtype=float)
        statistics[metric] = {
            "mean": float(np.mean(array)),
            "median": float(np.median(array)),
            "std": (
                float(np.std(array, ddof=1))
                if array.size > 1
                else 0.0
            ),
            "min": float(np.min(array)),
            "max": float(np.max(array)),
            "p5": float(np.percentile(array, 5)),
            "p95": float(np.percentile(array, 95)),
            "n": int(array.size),
        }
    return statistics


def validate_serialized_batch_evidence(
    payload: Any,
    *,
    num_iterations: int,
    base_seed: int,
    max_ticks: int,
    completed_iterations: int,
) -> None:
    """Reject incomplete, inconsistent, or fabricated durable batch data."""
    envelope = _exact_mapping(
        payload,
        fields=_BATCH_PAYLOAD_FIELDS,
        path="batch evidence",
    )
    expected_count = _strict_int(
        num_iterations,
        path="num_iterations",
        minimum=1,
    )
    if (
        _strict_int(
            completed_iterations,
            path="completed_iterations",
        )
        != expected_count
    ):
        raise ValueError(
            "completed_iterations does not equal num_iterations",
        )
    expected_base_seed = _strict_int(
        base_seed,
        path="base_seed",
    )
    expected_max_ticks = _strict_int(
        max_ticks,
        path="max_ticks",
        minimum=1,
    )

    ordered_metrics = envelope["ordered_metrics"]
    if not isinstance(ordered_metrics, (list, tuple)) or not ordered_metrics:
        raise ValueError("ordered_metrics must be a non-empty ordered list")
    ordered = tuple(
        _trimmed_text(
            metric,
            path=f"ordered_metrics[{index}]",
        )
        for index, metric in enumerate(ordered_metrics)
    )
    if len(ordered) != len(set(ordered)):
        raise ValueError("ordered_metrics must be duplicate-free")

    raw_metrics = envelope["raw_metrics"]
    if not isinstance(raw_metrics, Mapping):
        raise ValueError("raw_metrics must be a mapping")
    if tuple(raw_metrics) != ordered:
        raise ValueError(
            "raw_metrics keys/order must exactly match ordered_metrics",
        )
    if any(
        not isinstance(values, (list, tuple))
        for values in raw_metrics.values()
    ):
        raise ValueError("raw metric vectors must be ordered lists")
    expected_statistics = _statistics_for_metric_vectors(
        raw_metrics,
        ordered_metrics=ordered,
        expected_count=expected_count,
    )

    statistics = envelope["statistics"]
    if not isinstance(statistics, Mapping) or tuple(statistics) != ordered:
        raise ValueError(
            "statistics keys/order must exactly match ordered_metrics",
        )
    for metric in ordered:
        actual = _exact_mapping(
            statistics[metric],
            fields=_STATISTIC_FIELDS,
            path=f"statistics.{metric}",
        )
        for field_name, expected in expected_statistics[metric].items():
            value = actual[field_name]
            if field_name == "n":
                if (
                    _strict_int(
                        value,
                        path=f"statistics.{metric}.n",
                        minimum=1,
                    )
                    != expected
                ):
                    raise ValueError(
                        f"statistics.{metric}.n is inconsistent",
                    )
            elif (
                _strict_finite_number(
                    value,
                    path=f"statistics.{metric}.{field_name}",
                )
                != expected
            ):
                raise ValueError(
                    f"statistics.{metric}.{field_name} is inconsistent",
                )

    provenance = _exact_mapping(
        envelope["provenance"],
        fields=_BATCH_PROVENANCE_FIELDS,
        path="provenance",
    )
    for field_name in ("scenario_path", "data_root", "variant_id"):
        _trimmed_text(
            provenance[field_name],
            path=f"provenance.{field_name}",
        )
    if tuple(provenance["ordered_metrics"]) != ordered:
        raise ValueError(
            "provenance.ordered_metrics is inconsistent",
        )
    if (
        _strict_int(provenance["base_seed"], path="provenance.base_seed")
        != expected_base_seed
    ):
        raise ValueError("provenance.base_seed is inconsistent")
    expected_seeds = tuple(
        expected_base_seed + index
        for index in range(expected_count)
    )
    raw_seeds = provenance["seeds"]
    if (
        not isinstance(raw_seeds, (list, tuple))
        or len(raw_seeds) != expected_count
    ):
        raise ValueError(
            "provenance.seeds must contain one strict seed per iteration",
        )
    persisted_seeds = tuple(
        _strict_int(
            seed,
            path=f"provenance.seeds[{index}]",
        )
        for index, seed in enumerate(raw_seeds)
    )
    if persisted_seeds != expected_seeds:
        raise ValueError("provenance.seeds is inconsistent")
    if (
        _strict_int(
            provenance["max_ticks"],
            path="provenance.max_ticks",
            minimum=1,
        )
        != expected_max_ticks
    ):
        raise ValueError("provenance.max_ticks is inconsistent")

    source_fingerprint = _digest(
        provenance["source_fingerprint"],
        path="provenance.source_fingerprint",
    )
    config_fingerprint = _digest(
        provenance["config_fingerprint"],
        path="provenance.config_fingerprint",
    )
    code_revision = _validated_code_revision(
        provenance["code_revision"],
        path="provenance.code_revision",
    )
    data_revision = _digest(
        provenance["data_revision"],
        path="provenance.data_revision",
    )
    data_file_count = _strict_int(
        provenance["data_file_count"],
        path="provenance.data_file_count",
        minimum=1,
    )
    catalog_revision = _digest(
        provenance["catalog_revision"],
        path="provenance.catalog_revision",
    )
    doctrine_catalog_fingerprint = _digest(
        provenance["doctrine_catalog_fingerprint"],
        path="provenance.doctrine_catalog_fingerprint",
    )
    loaded_roster_loadout_fingerprint = _digest(
        provenance["loaded_roster_loadout_fingerprint"],
        path="provenance.loaded_roster_loadout_fingerprint",
    )
    authored_roster = _validated_roster(
        provenance["authored_roster"],
        path="provenance.authored_roster",
    )
    loaded_roster = _validated_roster(
        provenance["loaded_roster"],
        path="provenance.loaded_roster",
    )
    if loaded_roster != authored_roster:
        raise ValueError(
            "provenance loaded roster differs from authored roster",
        )
    _validate_metric_names(
        tuple(side for side, _count in authored_roster),
        ordered,
    )
    initial_assignments = _validated_assignments(
        provenance["initial_unit_assignments"],
        path="provenance.initial_unit_assignments",
        require_nonempty=True,
    )
    expected_side_counts = dict(authored_roster)
    initial_side_counts = {
        side: sum(
            assignment_side == side
            for _unit_id, assignment_side, _profile, _school
            in initial_assignments
        )
        for side in expected_side_counts
    }
    if (
        len(initial_assignments) != sum(expected_side_counts.values())
        or initial_side_counts != expected_side_counts
        or any(
            assignment[1] not in expected_side_counts
            for assignment in initial_assignments
        )
    ):
        raise ValueError(
            "provenance.initial_unit_assignments does not exactly match "
            "the authored roster",
        )
    initial_unit_ids = {
        assignment[0]
        for assignment in initial_assignments
    }

    runs = provenance["runs"]
    if not isinstance(runs, (list, tuple)) or len(runs) != expected_count:
        raise ValueError(
            "provenance.runs must contain exactly one run per seed",
        )
    for index, raw_run in enumerate(runs):
        run_path = f"provenance.runs[{index}]"
        run = _exact_mapping(
            raw_run,
            fields=_ANALYSIS_RUN_FIELDS,
            path=run_path,
        )
        if run["variant_id"] != provenance["variant_id"]:
            raise ValueError(f"{run_path}.variant_id is inconsistent")
        if (
            _strict_int(
                run["seed"],
                path=f"{run_path}.seed",
            )
            != expected_seeds[index]
        ):
            raise ValueError(f"{run_path}.seed is inconsistent")
        ticks_executed = _strict_int(
            run["ticks_executed"],
            path=f"{run_path}.ticks_executed",
            minimum=1,
        )
        if ticks_executed > expected_max_ticks:
            raise ValueError(
                f"{run_path}.ticks_executed exceeds max_ticks",
            )
        duration_s = _strict_finite_number(
            run["duration_s"],
            path=f"{run_path}.duration_s",
        )
        if duration_s < 0.0:
            raise ValueError(f"{run_path}.duration_s must be non-negative")
        winning_side = _trimmed_text(
            run["winning_side"],
            path=f"{run_path}.winning_side",
        )
        if winning_side not in {*expected_side_counts, "draw"}:
            raise ValueError(
                f"{run_path}.winning_side is not an authored side or draw",
            )
        condition_type = _trimmed_text(
            run["condition_type"],
            path=f"{run_path}.condition_type",
        )
        if condition_type not in _TERMINAL_CONDITION_TYPES:
            raise ValueError(
                f"{run_path}.condition_type is not a supported terminal "
                "condition",
            )
        if run["game_over"] is not True:
            raise ValueError(f"{run_path}.game_over must be true")
        if (
            run["source_fingerprint"] != source_fingerprint
            or run["config_fingerprint"] != config_fingerprint
        ):
            raise ValueError(
                f"{run_path} source/config fingerprint is inconsistent",
            )
        if (
            _validated_roster(
                run["authored_roster"],
                path=f"{run_path}.authored_roster",
            )
            != authored_roster
            or _validated_roster(
                run["loaded_roster"],
                path=f"{run_path}.loaded_roster",
            )
            != loaded_roster
        ):
            raise ValueError(f"{run_path} roster is inconsistent")

        runtime = _exact_mapping(
            run["runtime_provenance"],
            fields=_RUNTIME_PROVENANCE_FIELDS,
            path=f"{run_path}.runtime_provenance",
        )
        if (
            _validated_code_revision(
                runtime["code_revision"],
                path=f"{run_path}.runtime_provenance.code_revision",
            )
            != code_revision
            or runtime["data_revision"] != data_revision
            or _strict_int(
                runtime["data_file_count"],
                path=(
                    f"{run_path}.runtime_provenance."
                    "data_file_count"
                ),
                minimum=1,
            )
            != data_file_count
            or runtime["catalog_revision"] != catalog_revision
            or runtime["doctrine_catalog_fingerprint"]
            != doctrine_catalog_fingerprint
            or runtime["loaded_roster_loadout_fingerprint"]
            != loaded_roster_loadout_fingerprint
            or _validated_assignments(
                runtime["initial_unit_assignments"],
                path=(
                    f"{run_path}.runtime_provenance."
                    "initial_unit_assignments"
                ),
                require_nonempty=True,
            )
            != initial_assignments
        ):
            raise ValueError(
                f"{run_path}.runtime_provenance static identity is inconsistent",
            )
        _digest(
            runtime["doctrine_assignment_fingerprint"],
            path=(
                f"{run_path}.runtime_provenance."
                "doctrine_assignment_fingerprint"
            ),
        )
        _digest(
            runtime["final_roster_loadout_fingerprint"],
            path=(
                f"{run_path}.runtime_provenance."
                "final_roster_loadout_fingerprint"
            ),
        )
        arriving_assignments = _validated_assignments(
            runtime["arriving_unit_assignments"],
            path=(
                f"{run_path}.runtime_provenance."
                "arriving_unit_assignments"
            ),
            require_nonempty=False,
        )
        if any(
            assignment[0] in initial_unit_ids
            or assignment[1] not in expected_side_counts
            for assignment in arriving_assignments
        ):
            raise ValueError(
                f"{run_path}.runtime_provenance.arriving_unit_assignments "
                "must use new unit IDs on authored sides",
            )

        final_side_counts = {
            side: expected_count
            + sum(
                assignment[1] == side
                for assignment in arriving_assignments
            )
            for side, expected_count in expected_side_counts.items()
        }
        for metric in ordered:
            observed = float(raw_metrics[metric][index])
            if metric == "ticks_executed" and observed != float(
                ticks_executed,
            ):
                raise ValueError(
                    f"raw_metrics.{metric}[{index}] is inconsistent "
                    "with the run outcome",
                )
            if metric.startswith("win_"):
                side = metric.removeprefix("win_")
                expected_win = float(winning_side == side)
                if observed != expected_win:
                    raise ValueError(
                        f"raw_metrics.{metric}[{index}] is inconsistent "
                        "with the run outcome",
                    )
            for side, final_count in final_side_counts.items():
                if metric not in {
                    f"{side}_active",
                    f"{side}_destroyed",
                }:
                    continue
                if (
                    not observed.is_integer()
                    or observed < 0.0
                    or observed > final_count
                ):
                    raise ValueError(
                        f"raw_metrics.{metric}[{index}] must be an "
                        "integral count within the run roster",
                    )
                active_metric = f"{side}_active"
                destroyed_metric = f"{side}_destroyed"
                if (
                    active_metric in raw_metrics
                    and destroyed_metric in raw_metrics
                    and float(raw_metrics[active_metric][index])
                    + float(raw_metrics[destroyed_metric][index])
                    > final_count
                ):
                    raise ValueError(
                        f"raw metrics for {side!r} at index {index} "
                        "exceed the run roster",
                    )
            if metric == "exchange_ratio":
                if (
                    observed < 0.0
                    or observed > final_side_counts["red"]
                ):
                    raise ValueError(
                        f"raw_metrics.{metric}[{index}] is outside "
                        "the run roster bounds",
                    )
                if {
                    "blue_destroyed",
                    "red_destroyed",
                }.issubset(raw_metrics):
                    expected_ratio = float(
                        raw_metrics["red_destroyed"][index],
                    ) / max(
                        1.0,
                        float(
                            raw_metrics["blue_destroyed"][index],
                        ),
                    )
                    if observed != expected_ratio:
                        raise ValueError(
                            f"raw_metrics.{metric}[{index}] is "
                            "inconsistent with destroyed counts",
                        )


def _strict_positive_int(value: Any, *, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive strict integer")
    return value


def _strict_nonnegative_int(value: Any, *, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be a non-negative strict integer")
    return value


def _validate_metric_names(
    side_ids: Sequence[str],
    metric_names: Sequence[str],
) -> tuple[str, ...]:
    """Resolve the complete metric vocabulary against exact side IDs."""
    if not metric_names:
        raise AnalysisInputError("metric_names must be non-empty")
    normalized: list[str] = []
    for metric in metric_names:
        if not isinstance(metric, str) or not metric or metric != metric.strip():
            raise AnalysisInputError(
                "metric_names must contain non-empty trimmed strings",
            )
        normalized.append(metric)
    if len(normalized) != len(set(normalized)):
        raise AnalysisInputError(
            f"metric_names must be duplicate-free: {normalized!r}",
        )

    supported = {"ticks_executed"}
    for side in side_ids:
        supported.update(
            {
                f"{side}_active",
                f"{side}_destroyed",
                f"win_{side}",
            },
        )
    if tuple(side_ids) == ("blue", "red") or set(side_ids) == {
        "blue",
        "red",
    }:
        supported.add("exchange_ratio")

    unknown = [name for name in normalized if name not in supported]
    if unknown:
        raise AnalysisInputError(
            f"Unsupported metrics {unknown!r}; supported metrics are {sorted(supported)!r}",
        )
    return tuple(normalized)


def _extract_metrics(
    run_result: SimulationRunResult,
    session: RuntimeSession,
    metric_names: tuple[str, ...],
) -> dict[str, float]:
    """Extract prevalidated metrics from a public result and loaded roster."""
    side_ids = session.context.side_names()
    status_counts = {
        side: {
            UnitStatus.ACTIVE: sum(unit.status == UnitStatus.ACTIVE for unit in session.context.units_by_side[side]),
            UnitStatus.DESTROYED: sum(
                unit.status == UnitStatus.DESTROYED for unit in session.context.units_by_side[side]
            ),
        }
        for side in side_ids
    }

    resolved: dict[str, float] = {}
    for metric in metric_names:
        if metric == "ticks_executed":
            value = float(run_result.ticks_executed)
        elif metric == "exchange_ratio":
            value = float(status_counts["red"][UnitStatus.DESTROYED]) / max(
                1.0,
                float(status_counts["blue"][UnitStatus.DESTROYED]),
            )
        elif metric.startswith("win_"):
            side = metric.removeprefix("win_")
            value = float(run_result.victory_result.game_over and run_result.victory_result.winning_side == side)
        else:
            matched = False
            value = 0.0
            for side in side_ids:
                if metric == f"{side}_active":
                    value = float(status_counts[side][UnitStatus.ACTIVE])
                    matched = True
                    break
                if metric == f"{side}_destroyed":
                    value = float(status_counts[side][UnitStatus.DESTROYED])
                    matched = True
                    break
            if not matched:
                raise ValueError(f"Unsupported metric {metric!r}")
        if not math.isfinite(value):
            raise ValueError(
                f"Metric {metric!r} produced a non-finite value {value!r}",
            )
        resolved[metric] = value
    return resolved


class AnalysisRunner:
    """Execute complete, fresh production runs from one prepared source."""

    def __init__(
        self,
        prepared: PreparedScenario,
        metric_names: Sequence[str],
    ) -> None:
        self._prepared = prepared
        self._metric_names = _validate_metric_names(
            prepared.side_ids,
            metric_names,
        )

    @property
    def metric_names(self) -> tuple[str, ...]:
        return self._metric_names

    def run_variant(
        self,
        variant_id: str,
        *,
        num_iterations: int,
        base_seed: int,
        max_ticks: int,
        cancellation_check: Callable[[], None] | None = None,
        progress_callback: Callable[[int, int, int], None] | None = None,
    ) -> AnalysisBatchResult:
        """Run every requested seed or raise without returning partial data."""
        count = _strict_positive_int(
            num_iterations,
            name="num_iterations",
        )
        first_seed = _strict_nonnegative_int(base_seed, name="base_seed")
        tick_limit = _strict_positive_int(max_ticks, name="max_ticks")
        if cancellation_check is not None and not callable(
            cancellation_check,
        ):
            raise TypeError("cancellation_check must be callable")
        if progress_callback is not None and not callable(progress_callback):
            raise TypeError("progress_callback must be callable")
        variant = self._prepared.variant(variant_id)
        seeds = tuple(first_seed + index for index in range(count))
        vectors = {metric: [] for metric in self._metric_names}
        run_records: list[AnalysisRunRecord] = []
        loaded_roster: tuple[tuple[str, int], ...] | None = None
        static_provenance: RuntimeProvenance | None = None

        for index, seed in enumerate(seeds):
            if cancellation_check is not None:
                cancellation_check()
            session = self._prepared.build(
                variant,
                seed=seed,
                max_ticks=tick_limit,
            )
            result = session.run_to_completion()
            metrics = _extract_metrics(result, session, self._metric_names)
            runtime_provenance = session.provenance()
            if cancellation_check is not None:
                cancellation_check()
            for metric in self._metric_names:
                vectors[metric].append(metrics[metric])
            if loaded_roster is None:
                loaded_roster = session.loaded_roster
                static_provenance = runtime_provenance
            elif loaded_roster != session.loaded_roster:
                raise ValueError(
                    "Loaded roster changed between analysis iterations",
                )
            elif static_provenance is None:
                raise RuntimeError("Analysis provenance was not initialized")
            elif (
                runtime_provenance.code_revision != static_provenance.code_revision
                or runtime_provenance.data_revision != static_provenance.data_revision
                or runtime_provenance.catalog_revision != static_provenance.catalog_revision
                or runtime_provenance.doctrine_catalog_fingerprint != static_provenance.doctrine_catalog_fingerprint
                or runtime_provenance.loaded_roster_loadout_fingerprint
                != static_provenance.loaded_roster_loadout_fingerprint
                or runtime_provenance.initial_unit_assignments != static_provenance.initial_unit_assignments
            ):
                raise ValueError(
                    "Static runtime provenance changed between analysis iterations",
                )
            run_records.append(
                AnalysisRunRecord(
                    variant_id=variant_id,
                    seed=seed,
                    ticks_executed=result.ticks_executed,
                    duration_s=result.duration_s,
                    winning_side=result.victory_result.winning_side,
                    condition_type=result.victory_result.condition_type,
                    game_over=result.victory_result.game_over,
                    source_fingerprint=session.source_fingerprint,
                    config_fingerprint=session.config_fingerprint,
                    authored_roster=session.authored_roster,
                    loaded_roster=session.loaded_roster,
                    runtime_provenance=runtime_provenance,
                ),
            )
            if progress_callback is not None:
                progress_callback(index + 1, count, seed)

        if loaded_roster is None or static_provenance is None:
            raise RuntimeError("Analysis produced no completed runs")
        for metric, values in vectors.items():
            if len(values) != count:
                raise RuntimeError(
                    f"Metric {metric!r} is partial: {len(values)}/{count} values",
                )
            if not all(math.isfinite(value) for value in values):
                raise ValueError(
                    f"Metric {metric!r} contains a non-finite value",
                )

        return AnalysisBatchResult(
            scenario_path=str(self._prepared.scenario_path),
            data_root=str(self._prepared.data_root),
            variant_id=variant_id,
            ordered_metrics=self._metric_names,
            base_seed=first_seed,
            seeds=seeds,
            max_ticks=tick_limit,
            source_fingerprint=self._prepared.source_fingerprint,
            config_fingerprint=variant.config_fingerprint,
            authored_roster=self._prepared.authored_roster,
            loaded_roster=loaded_roster,
            code_revision=static_provenance.code_revision,
            data_revision=static_provenance.data_revision,
            data_file_count=static_provenance.data_file_count,
            catalog_revision=static_provenance.catalog_revision,
            doctrine_catalog_fingerprint=(static_provenance.doctrine_catalog_fingerprint),
            loaded_roster_loadout_fingerprint=(static_provenance.loaded_roster_loadout_fingerprint),
            initial_unit_assignments=(static_provenance.initial_unit_assignments),
            metric_vectors=tuple((metric, tuple(vectors[metric])) for metric in self._metric_names),
            runs=tuple(run_records),
        )


def prepare_analysis(
    *,
    scenario_path: str | Path,
    variants: Sequence[AnalysisVariant],
    metric_names: Sequence[str] | None,
    data_dir: str | Path | None = None,
    include_ticks_in_default: bool = False,
) -> tuple[PreparedScenario, AnalysisRunner]:
    """Prepare one source and validate all metrics before the first run."""
    prepared = SimulationRuntimeFactory().prepare(
        scenario_path,
        data_dir,
        variants,
    )
    resolved_metrics = (
        tuple(metric_names)
        if metric_names is not None
        else (
            tuple(
                f"{side}_destroyed"
                for side in prepared.side_ids
            )
            + (
                ("ticks_executed",)
                if include_ticks_in_default
                else ()
            )
        )
    )
    return prepared, AnalysisRunner(prepared, resolved_metrics)


def run_scenario_batch(
    scenario_path: str,
    overrides: Mapping[str, Any],
    num_iterations: int,
    base_seed: int,
    max_ticks: int,
    metric_names: list[str],
    data_dir: str | Path | None = None,
) -> AnalysisBatchResult:
    """Run one authoritative sparse variant with complete public evidence."""
    variant = AnalysisVariant(
        variant_id="analysis",
        calibration_patch=overrides,
    )
    _, runner = prepare_analysis(
        scenario_path=scenario_path,
        variants=(variant,),
        metric_names=metric_names,
        data_dir=data_dir,
    )
    return runner.run_variant(
        variant.variant_id,
        num_iterations=num_iterations,
        base_seed=base_seed,
        max_ticks=max_ticks,
    )
