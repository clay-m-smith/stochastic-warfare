"""Strict common-seed comparison of production doctrinal policies."""

from __future__ import annotations

from dataclasses import dataclass
import math
import statistics
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    field_validator,
    model_validator,
)

from stochastic_warfare.simulation.runtime import AnalysisVariant
from stochastic_warfare.tools._run_helpers import (
    AnalysisBatchResult,
    prepare_analysis,
)


class DoctrineCompareConfig(BaseModel):
    """Typed contract for a doctrine-only production comparison."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_path: str
    variants: tuple[AnalysisVariant, ...] = Field(min_length=2)
    metric_names: tuple[str, ...] | None = Field(
        default=None,
        min_length=1,
    )
    num_iterations: StrictInt = Field(default=10, ge=2)
    base_seed: StrictInt = Field(default=42, ge=0)
    max_ticks: StrictInt = Field(default=100, ge=1)
    data_dir: str | None = None

    @field_validator("scenario_path", mode="before")
    @classmethod
    def _trimmed_scenario_path(cls, value: Any) -> str:
        if not isinstance(value, str) or not value or value != value.strip():
            raise ValueError(
                "scenario_path must be a non-empty trimmed string",
            )
        return value

    @field_validator("variants", "metric_names", mode="before")
    @classmethod
    def _ordered_public_sequence(cls, value: Any, info: Any) -> Any:
        if info.field_name == "metric_names" and value is None:
            return None
        if not isinstance(value, (list, tuple)):
            raise ValueError(
                f"{info.field_name} must be an ordered list or tuple",
            )
        return value

    @field_validator("metric_names")
    @classmethod
    def _strict_metrics(
        cls,
        values: tuple[str, ...] | None,
    ) -> tuple[str, ...] | None:
        if values is None:
            return None
        if any(not isinstance(value, str) or not value or value != value.strip() for value in values):
            raise ValueError(
                "metric_names must contain non-empty trimmed strings",
            )
        if len(values) != len(set(values)):
            raise ValueError("metric_names must be duplicate-free")
        return values

    @model_validator(mode="after")
    def _doctrine_only_variants(self) -> DoctrineCompareConfig:
        variant_ids = [variant.variant_id for variant in self.variants]
        if len(variant_ids) != len(set(variant_ids)):
            raise ValueError(
                f"variant_id values must be unique: {variant_ids!r}",
            )
        if any(variant.doctrine_variant is None for variant in self.variants):
            raise ValueError(
                "every doctrine comparison variant requires doctrine_variant assignments",
            )

        side_sets = [
            frozenset(assignment.side for assignment in variant.doctrine_variant.assignments)
            for variant in self.variants
            if variant.doctrine_variant is not None
        ]
        if not side_sets or not side_sets[0]:
            raise ValueError(
                "doctrine comparison variants must map at least one side",
            )
        if any(side_set != side_sets[0] for side_set in side_sets[1:]):
            raise ValueError(
                "all doctrine variants must map the same exact side set",
            )

        policies = {
            tuple(
                sorted(
                    (
                        assignment.side,
                        assignment.school_id,
                    )
                    for assignment in variant.doctrine_variant.assignments
                ),
            )
            for variant in self.variants
            if variant.doctrine_variant is not None
        }
        if len(policies) < 2:
            raise ValueError(
                "doctrine comparison requires at least two distinct assignment policies",
            )

        school_ids = {
            assignment.school_id
            for variant in self.variants
            if variant.doctrine_variant is not None
            for assignment in variant.doctrine_variant.assignments
        }
        if len(school_ids) < 2:
            raise ValueError(
                "doctrine comparison requires at least two distinct schools",
            )

        calibration_payloads = [
            variant.calibration_patch.to_sparse_patch(mode="json")
            for variant in self.variants
        ]
        if any(payload != calibration_payloads[0] for payload in calibration_payloads[1:]):
            raise ValueError(
                "doctrine comparison must hold calibration patches identical",
            )
        return self


@dataclass(frozen=True)
class DoctrineMetricResult:
    """Exact values and sample statistics for one requested metric."""

    metric: str
    mean: float
    std: float
    values: tuple[float, ...]


@dataclass(frozen=True)
class DoctrineVariantResult:
    """One doctrine policy, its exact metrics, and runtime provenance."""

    variant_id: str
    assignments: tuple[dict[str, str], ...]
    metrics: tuple[DoctrineMetricResult, ...]
    batch: AnalysisBatchResult


@dataclass(frozen=True)
class DoctrineCompareResult:
    """Complete common-seed production doctrine comparison."""

    scenario: str
    num_iterations: int
    base_seed: int
    max_ticks: int
    ordered_metrics: tuple[str, ...]
    seeds: tuple[int, ...]
    results: tuple[DoctrineVariantResult, ...]


def _assert_policy_applied(
    batch: AnalysisBatchResult,
    variant: AnalysisVariant,
) -> None:
    """Reject a run whose declared side policy did not reach its roster."""
    doctrine_variant = variant.doctrine_variant
    if doctrine_variant is None:
        raise RuntimeError("Doctrine variant disappeared after validation")
    requested_by_side = {assignment.side: assignment.school_id for assignment in doctrine_variant.assignments}
    assignments_by_side: dict[str, list[str | None]] = {}
    for assignment in batch.initial_unit_assignments:
        assignments_by_side.setdefault(assignment.side, []).append(
            assignment.doctrine_school_id,
        )
    for requested in doctrine_variant.assignments:
        observed = assignments_by_side.get(requested.side)
        if not observed:
            raise RuntimeError(
                f"Doctrine policy side has no loaded initial units: {requested.side!r}",
            )
        if any(school_id != requested.school_id for school_id in observed):
            raise RuntimeError(
                f"Doctrine policy was not applied exactly to every initial {requested.side!r} unit",
            )
    for run in batch.runs:
        for observed in run.runtime_provenance.arriving_unit_assignments:
            expected_school = requested_by_side.get(observed.side)
            if expected_school is not None and observed.doctrine_school_id != expected_school:
                raise RuntimeError(
                    "Doctrine policy was not applied exactly to arriving "
                    f"unit {observed.unit_id!r} on mapped side "
                    f"{observed.side!r} for seed {run.seed}: expected "
                    f"{expected_school!r}, observed "
                    f"{observed.doctrine_school_id!r}",
                )


def run_doctrine_comparison(
    config: DoctrineCompareConfig,
) -> DoctrineCompareResult:
    """Run all doctrine policies from one source using identical seeds."""
    _, runner = prepare_analysis(
        scenario_path=config.scenario_path,
        variants=config.variants,
        metric_names=config.metric_names,
        data_dir=config.data_dir,
        include_ticks_in_default=True,
    )

    results: list[DoctrineVariantResult] = []
    common_seeds: tuple[int, ...] | None = None
    for variant in config.variants:
        batch = runner.run_variant(
            variant.variant_id,
            num_iterations=config.num_iterations,
            base_seed=config.base_seed,
            max_ticks=config.max_ticks,
        )
        _assert_policy_applied(batch, variant)
        if common_seeds is None:
            common_seeds = batch.seeds
        elif batch.seeds != common_seeds:
            raise RuntimeError(
                "Doctrine variants did not use the same ordered seeds",
            )

        metric_results: list[DoctrineMetricResult] = []
        for metric in runner.metric_names:
            values = batch.metric_values(metric)
            if len(values) != config.num_iterations or not all(math.isfinite(value) for value in values):
                raise RuntimeError(
                    f"Doctrine metric {metric!r} is incomplete or non-finite",
                )
            metric_results.append(
                DoctrineMetricResult(
                    metric=metric,
                    mean=float(statistics.mean(values)),
                    std=float(statistics.stdev(values)),
                    values=values,
                ),
            )

        doctrine_variant = variant.doctrine_variant
        if doctrine_variant is None:
            raise RuntimeError(
                "Doctrine variant disappeared after validation",
            )
        results.append(
            DoctrineVariantResult(
                variant_id=variant.variant_id,
                assignments=tuple(
                    {
                        "side": assignment.side,
                        "school_id": assignment.school_id,
                    }
                    for assignment in doctrine_variant.assignments
                ),
                metrics=tuple(metric_results),
                batch=batch,
            ),
        )

    if common_seeds is None:
        raise RuntimeError("Doctrine comparison produced no variants")
    return DoctrineCompareResult(
        scenario=config.scenario_path,
        num_iterations=config.num_iterations,
        base_seed=config.base_seed,
        max_ticks=config.max_ticks,
        ordered_metrics=runner.metric_names,
        seeds=common_seeds,
        results=tuple(results),
    )
