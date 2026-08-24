"""Strict paired-seed parameter sensitivity for production scenarios."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    field_validator,
)

from stochastic_warfare.simulation.performance_flags import (
    validate_supported_runtime_performance_parameter_name,
)
from stochastic_warfare.simulation.runtime import AnalysisVariant
from stochastic_warfare.tools._run_helpers import (
    AnalysisBatchResult,
    prepare_analysis,
)


class SweepConfig(BaseModel):
    """Validated configuration for one production parameter sweep."""

    model_config = ConfigDict(extra="forbid")

    scenario_path: str
    parameter_name: str
    values: list[StrictFloat] = Field(min_length=1)
    metric_names: list[str] | None = Field(default=None, min_length=1)
    iterations_per_point: StrictInt = Field(default=10, ge=2)
    base_seed: StrictInt = Field(default=42, ge=0)
    max_ticks: StrictInt = Field(default=100, ge=1)
    data_dir: str | None = None

    @field_validator("scenario_path", "parameter_name", mode="before")
    @classmethod
    def _trimmed_required_text(cls, value: Any) -> str:
        if not isinstance(value, str) or not value or value != value.strip():
            raise ValueError("value must be a non-empty trimmed string")
        return value

    @field_validator("parameter_name")
    @classmethod
    def _supported_governed_performance_parameter(
        cls,
        value: str,
    ) -> str:
        return validate_supported_runtime_performance_parameter_name(value)

    @field_validator("values")
    @classmethod
    def _finite_unique_values(
        cls,
        values: list[float],
    ) -> list[float]:
        if any(isinstance(value, bool) or not math.isfinite(value) for value in values):
            raise ValueError("sweep values must be finite numbers")
        if len(values) != len(set(values)):
            raise ValueError("sweep values must be duplicate-free")
        return values

    @field_validator("metric_names")
    @classmethod
    def _unique_metric_names(
        cls,
        values: list[str] | None,
    ) -> list[str] | None:
        if values is None:
            return None
        if any(not isinstance(value, str) or not value or value != value.strip() for value in values):
            raise ValueError(
                "metric_names must contain non-empty trimmed strings",
            )
        if len(values) != len(set(values)):
            raise ValueError("metric_names must be duplicate-free")
        return values


@dataclass(frozen=True)
class MetricResult:
    """Statistics and exact raw vector for one metric at one point."""

    metric: str
    mean: float
    std: float
    min: float
    max: float
    values: list[float] = field(default_factory=list)


@dataclass(frozen=True)
class SweepPoint:
    """One independently prepared calibration value."""

    parameter_value: float
    metric_results: list[MetricResult] = field(default_factory=list)
    batch: AnalysisBatchResult | None = None


@dataclass(frozen=True)
class SweepResult:
    """Complete source-once production sweep."""

    parameter_name: str
    points: list[SweepPoint] = field(default_factory=list)
    ordered_metrics: tuple[str, ...] = ()
    base_seed: int = 42
    seeds: tuple[int, ...] = ()
    max_ticks: int = 100
    source_fingerprint: str = ""
    data_root: str = ""


def run_sweep(config: SweepConfig) -> SweepResult:
    """Run every point against the same source and ordered seed sequence."""
    variants = tuple(
        AnalysisVariant(
            variant_id=f"point-{index}",
            calibration_patch={config.parameter_name: value},
        )
        for index, value in enumerate(config.values)
    )
    prepared, runner = prepare_analysis(
        scenario_path=config.scenario_path,
        variants=variants,
        metric_names=config.metric_names,
        data_dir=config.data_dir,
    )

    points: list[SweepPoint] = []
    seeds = tuple(config.base_seed + index for index in range(config.iterations_per_point))
    for value, variant in zip(config.values, variants, strict=True):
        batch = runner.run_variant(
            variant.variant_id,
            num_iterations=config.iterations_per_point,
            base_seed=config.base_seed,
            max_ticks=config.max_ticks,
        )
        metric_results: list[MetricResult] = []
        for name in runner.metric_names:
            values = list(batch.metric_values(name))
            if len(values) != config.iterations_per_point:
                raise RuntimeError(
                    f"Metric {name!r} has a partial result vector",
                )
            array = np.asarray(values, dtype=float)
            if not np.isfinite(array).all():
                raise ValueError(
                    f"Metric {name!r} contains non-finite values",
                )
            metric_results.append(
                MetricResult(
                    metric=name,
                    mean=float(np.mean(array)),
                    std=float(np.std(array, ddof=1)),
                    min=float(np.min(array)),
                    max=float(np.max(array)),
                    values=values,
                ),
            )
        points.append(
            SweepPoint(
                parameter_value=value,
                metric_results=metric_results,
                batch=batch,
            ),
        )

    return SweepResult(
        parameter_name=config.parameter_name,
        points=points,
        ordered_metrics=runner.metric_names,
        base_seed=config.base_seed,
        seeds=seeds,
        max_ticks=config.max_ticks,
        source_fingerprint=prepared.source_fingerprint,
        data_root=str(prepared.data_root),
    )


def plot_sweep(result: SweepResult, metric: str | None = None) -> Any:
    """Plot one exact metric; reject absent vectors instead of adding zeros."""
    import matplotlib.pyplot as plt

    if not result.points:
        raise ValueError("Sweep result contains no points")
    if not result.points[0].metric_results:
        raise ValueError("Sweep result contains no metric vectors")
    if metric is None:
        metric = result.points[0].metric_results[0].metric

    x_values: list[float] = []
    means: list[float] = []
    stds: list[float] = []
    for point in result.points:
        matches = [item for item in point.metric_results if item.metric == metric]
        if len(matches) != 1:
            raise ValueError(
                f"Sweep point {point.parameter_value!r} does not contain exactly one vector for metric {metric!r}",
            )
        x_values.append(point.parameter_value)
        means.append(matches[0].mean)
        stds.append(matches[0].std)

    figure, axis = plt.subplots(figsize=(10, 6))
    axis.errorbar(
        x_values,
        means,
        yerr=stds,
        marker="o",
        capsize=4,
        linewidth=1.5,
    )
    axis.set_xlabel(result.parameter_name)
    axis.set_ylabel(metric)
    axis.set_title(f"Sensitivity: {metric} vs {result.parameter_name}")
    axis.grid(True, alpha=0.3)
    figure.tight_layout()
    plt.close(figure)
    return figure
