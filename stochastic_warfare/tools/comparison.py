"""Common-seed production comparison with exact paired inference."""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Any, Mapping

import numpy as np
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    field_validator,
)
from scipy.stats import binomtest

from stochastic_warfare.simulation.calibration import CalibrationSchema
from stochastic_warfare.simulation.runtime import AnalysisVariant
from stochastic_warfare.tools._run_helpers import (
    AnalysisBatchResult,
    prepare_analysis,
)


class ComparisonConfig(BaseModel):
    """Strict configuration for a paired A/B production comparison."""

    model_config = ConfigDict(extra="forbid")

    scenario_path: str
    overrides_a: dict[str, Any] = Field(default_factory=dict)
    overrides_b: dict[str, Any] = Field(default_factory=dict)
    label_a: str = "A"
    label_b: str = "B"
    metric_names: list[str] | None = Field(default=None, min_length=1)
    num_iterations: StrictInt = Field(default=20, ge=2)
    alpha: StrictFloat = Field(default=0.05, gt=0.0, lt=1.0)
    base_seed: StrictInt = Field(default=42, ge=0)
    max_ticks: StrictInt = Field(default=100, ge=1)
    data_dir: str | None = None

    @field_validator("scenario_path", "label_a", "label_b", mode="before")
    @classmethod
    def _trimmed_required_text(cls, value: Any) -> str:
        if not isinstance(value, str) or not value or value != value.strip():
            raise ValueError("value must be a non-empty trimmed string")
        return value

    @field_validator("overrides_a", "overrides_b", mode="before")
    @classmethod
    def _mapping_override(cls, value: Any) -> dict[str, Any]:
        if isinstance(value, CalibrationSchema):
            raw = value.to_sparse_patch(mode="python")
        elif isinstance(value, Mapping):
            raw = dict(value)
        else:
            raise ValueError("calibration overrides must be mappings")
        return CalibrationSchema.model_validate(
            raw,
            strict=True,
        ).to_sparse_patch(mode="python")

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

    @field_validator("alpha")
    @classmethod
    def _finite_alpha(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("alpha must be finite")
        return value


@dataclass(frozen=True)
class MetricComparison:
    """Exact paired sign-test evidence for one metric."""

    metric: str
    mean_a: float
    std_a: float
    mean_b: float
    std_b: float
    n_total: int
    n_nonzero: int
    positive: int
    negative: int
    tied: int
    mean_paired_difference: float
    median_paired_difference: float
    paired_superiority: float
    raw_p_value: float
    holm_adjusted_p_value: float
    alpha: float
    family_wise_significant: bool

    @property
    def p_value(self) -> float:
        """Compatibility accessor for callers that only display one p-value."""
        return self.holm_adjusted_p_value

    @property
    def significant(self) -> bool:
        """Compatibility accessor with the paired family-wise meaning."""
        return self.family_wise_significant


@dataclass(frozen=True)
class ComparisonResult:
    """Complete paired production comparison and exact raw provenance."""

    label_a: str
    label_b: str
    num_iterations: int
    alpha: float = 0.05
    ordered_metrics: tuple[str, ...] = ()
    seeds: tuple[int, ...] = ()
    metrics: list[MetricComparison] = field(default_factory=list)
    raw_a: dict[str, list[float]] = field(default_factory=dict)
    raw_b: dict[str, list[float]] = field(default_factory=dict)
    batch_a: AnalysisBatchResult | None = None
    batch_b: AnalysisBatchResult | None = None


def compare_distributions(
    values_a: list[float],
    values_b: list[float],
    metric_name: str,
    alpha: float = 0.05,
) -> MetricComparison:
    """Compare aligned values with the two-sided exact paired sign test."""
    if not isinstance(metric_name, str) or not metric_name or metric_name != metric_name.strip():
        raise ValueError("metric_name must be a non-empty trimmed string")
    if isinstance(alpha, bool) or not isinstance(alpha, float) or not math.isfinite(alpha) or not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be a strict finite float in (0, 1)")
    if len(values_a) != len(values_b):
        raise ValueError("Paired metric vectors must have equal length")
    if len(values_a) < 2:
        raise ValueError("Paired comparison requires at least two values")

    def _strict_vector(values: list[float], *, label: str) -> np.ndarray:
        if any(type(value) not in {int, float} for value in values):
            raise ValueError(
                f"Paired metric vector {label} must contain only strict integer or float values",
            )
        array = np.asarray(values, dtype=float)
        if not np.isfinite(array).all():
            raise ValueError(
                f"Paired metric vector {label} must contain finite values",
            )
        return array

    array_a = _strict_vector(values_a, label="A")
    array_b = _strict_vector(values_b, label="B")
    differences = array_b - array_a
    positive = int(np.count_nonzero(differences > 0.0))
    negative = int(np.count_nonzero(differences < 0.0))
    tied = int(np.count_nonzero(differences == 0.0))
    n_total = len(differences)
    n_nonzero = positive + negative
    raw_p_value = (
        1.0
        if n_nonzero == 0
        else float(
            binomtest(
                positive,
                n_nonzero,
                p=0.5,
                alternative="two-sided",
            ).pvalue,
        )
    )

    return MetricComparison(
        metric=metric_name,
        mean_a=float(np.mean(array_a)),
        std_a=float(np.std(array_a, ddof=1)),
        mean_b=float(np.mean(array_b)),
        std_b=float(np.std(array_b, ddof=1)),
        n_total=n_total,
        n_nonzero=n_nonzero,
        positive=positive,
        negative=negative,
        tied=tied,
        mean_paired_difference=float(np.mean(differences)),
        median_paired_difference=float(np.median(differences)),
        paired_superiority=float(
            (positive + 0.5 * tied) / n_total,
        ),
        raw_p_value=raw_p_value,
        holm_adjusted_p_value=raw_p_value,
        alpha=alpha,
        family_wise_significant=raw_p_value <= alpha,
    )


def _apply_holm(
    comparisons: list[MetricComparison],
    *,
    alpha: float,
) -> list[MetricComparison]:
    """Apply stable Holm step-down adjustment in original metric order."""
    count = len(comparisons)
    ordered_indexes = _holm_order_indices(comparisons)
    adjusted = [1.0] * count
    running_max = 0.0
    for rank, original_index in enumerate(ordered_indexes):
        candidate = min(
            1.0,
            (count - rank) * comparisons[original_index].raw_p_value,
        )
        running_max = max(running_max, candidate)
        adjusted[original_index] = running_max
    return [
        replace(
            comparison,
            holm_adjusted_p_value=adjusted[index],
            family_wise_significant=adjusted[index] <= alpha,
        )
        for index, comparison in enumerate(comparisons)
    ]


def _holm_order_indices(
    comparisons: list[MetricComparison],
) -> tuple[int, ...]:
    """Return the production step-down order, including stable p-value ties."""
    return tuple(
        sorted(
            range(len(comparisons)),
            key=lambda index: (
                comparisons[index].raw_p_value,
                index,
            ),
        )
    )


def run_comparison(config: ComparisonConfig) -> ComparisonResult:
    """Run A and B from one source with the exact same ordered seeds."""
    variants = (
        AnalysisVariant(
            variant_id="a",
            calibration_patch=config.overrides_a,
        ),
        AnalysisVariant(
            variant_id="b",
            calibration_patch=config.overrides_b,
        ),
    )
    _, runner = prepare_analysis(
        scenario_path=config.scenario_path,
        variants=variants,
        metric_names=config.metric_names,
        data_dir=config.data_dir,
    )
    batch_a = runner.run_variant(
        "a",
        num_iterations=config.num_iterations,
        base_seed=config.base_seed,
        max_ticks=config.max_ticks,
    )
    batch_b = runner.run_variant(
        "b",
        num_iterations=config.num_iterations,
        base_seed=config.base_seed,
        max_ticks=config.max_ticks,
    )
    if batch_a.seeds != batch_b.seeds:
        raise RuntimeError("Comparison variants did not use the same seeds")

    comparisons = [
        compare_distributions(
            list(batch_a.metric_values(metric)),
            list(batch_b.metric_values(metric)),
            metric,
            config.alpha,
        )
        for metric in runner.metric_names
    ]
    comparisons = _apply_holm(comparisons, alpha=config.alpha)
    return ComparisonResult(
        label_a=config.label_a,
        label_b=config.label_b,
        num_iterations=config.num_iterations,
        alpha=config.alpha,
        ordered_metrics=runner.metric_names,
        seeds=batch_a.seeds,
        metrics=comparisons,
        raw_a=batch_a.metrics_dict(),
        raw_b=batch_b.metrics_dict(),
        batch_a=batch_a,
        batch_b=batch_b,
    )


def format_comparison(result: ComparisonResult) -> str:
    """Format the paired result without legacy unpaired terminology."""
    lines = [
        f"Paired A/B Comparison: {result.label_a} vs {result.label_b}",
        f"Iterations: {result.num_iterations}",
        f"Family-wise alpha: {result.alpha:g}",
        "",
        (f"{'Metric':<22} {'Mean A':>9} {'Mean B':>9} {'+/-/=':>11} {'Raw p':>9} {'Holm p':>9} {'Sig?':>5}"),
        "-" * 82,
    ]
    for comparison in result.metrics:
        signs = f"{comparison.positive}/{comparison.negative}/{comparison.tied}"
        significant = "*" if comparison.family_wise_significant else ""
        lines.append(
            f"{comparison.metric:<22} "
            f"{comparison.mean_a:>9.3f} "
            f"{comparison.mean_b:>9.3f} "
            f"{signs:>11} "
            f"{comparison.raw_p_value:>9.4f} "
            f"{comparison.holm_adjusted_p_value:>9.4f} "
            f"{significant:>5}",
        )
    return "\n".join(lines)
