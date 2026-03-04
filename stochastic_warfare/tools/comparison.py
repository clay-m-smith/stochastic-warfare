"""A/B statistical comparison of simulation configurations.

Runs two configurations N times each, compares per-metric distributions
using the Mann-Whitney U test, and reports effect sizes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel
from scipy import stats

from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class ComparisonConfig(BaseModel):
    """Configuration for A/B comparison."""

    scenario_path: str
    overrides_a: dict[str, Any] = {}
    overrides_b: dict[str, Any] = {}
    label_a: str = "A"
    label_b: str = "B"
    metric_names: list[str] = ["blue_destroyed", "red_destroyed"]
    num_iterations: int = 20
    alpha: float = 0.05
    base_seed: int = 42
    max_ticks: int = 100


# ---------------------------------------------------------------------------
# Result structures
# ---------------------------------------------------------------------------


@dataclass
class MetricComparison:
    """Statistical comparison of a single metric between two configs."""

    metric: str
    mean_a: float
    std_a: float
    mean_b: float
    std_b: float
    u_statistic: float
    p_value: float
    significant: bool
    effect_size: float  # rank-biserial r


@dataclass
class ComparisonResult:
    """Complete A/B comparison result."""

    label_a: str
    label_b: str
    num_iterations: int
    metrics: list[MetricComparison] = field(default_factory=list)
    raw_a: dict[str, list[float]] = field(default_factory=dict)
    raw_b: dict[str, list[float]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Core comparison logic
# ---------------------------------------------------------------------------


def compare_distributions(
    values_a: list[float],
    values_b: list[float],
    metric_name: str,
    alpha: float = 0.05,
) -> MetricComparison:
    """Compare two distributions using Mann-Whitney U test.

    Parameters
    ----------
    values_a, values_b:
        Sample values from configurations A and B.
    metric_name:
        Name of the metric being compared.
    alpha:
        Significance level.

    Returns
    -------
    MetricComparison
        Statistical comparison result.
    """
    arr_a = np.array(values_a, dtype=float)
    arr_b = np.array(values_b, dtype=float)

    mean_a = float(np.mean(arr_a)) if len(arr_a) > 0 else 0.0
    std_a = float(np.std(arr_a, ddof=1)) if len(arr_a) > 1 else 0.0
    mean_b = float(np.mean(arr_b)) if len(arr_b) > 0 else 0.0
    std_b = float(np.std(arr_b, ddof=1)) if len(arr_b) > 1 else 0.0

    if len(arr_a) < 2 or len(arr_b) < 2:
        return MetricComparison(
            metric=metric_name,
            mean_a=mean_a, std_a=std_a,
            mean_b=mean_b, std_b=std_b,
            u_statistic=0.0, p_value=1.0,
            significant=False, effect_size=0.0,
        )

    # Mann-Whitney U test
    try:
        u_stat, p_value = stats.mannwhitneyu(arr_a, arr_b, alternative="two-sided")
    except ValueError:
        # All values identical
        u_stat = 0.0
        p_value = 1.0

    # Rank-biserial correlation as effect size
    n1, n2 = len(arr_a), len(arr_b)
    effect_size = 1.0 - (2.0 * u_stat) / (n1 * n2) if n1 * n2 > 0 else 0.0

    return MetricComparison(
        metric=metric_name,
        mean_a=mean_a, std_a=std_a,
        mean_b=mean_b, std_b=std_b,
        u_statistic=float(u_stat),
        p_value=float(p_value),
        significant=p_value < alpha,
        effect_size=float(effect_size),
    )


def run_comparison(config: ComparisonConfig) -> ComparisonResult:
    """Run A/B comparison using CampaignRunner.

    Runs ``num_iterations`` of each config variant, collects metrics,
    and performs Mann-Whitney U test per metric.
    """
    from stochastic_warfare.tools._run_helpers import run_scenario_batch

    raw_a = run_scenario_batch(
        config.scenario_path,
        config.overrides_a,
        config.num_iterations,
        config.base_seed,
        config.max_ticks,
        config.metric_names,
    )
    raw_b = run_scenario_batch(
        config.scenario_path,
        config.overrides_b,
        config.num_iterations,
        config.base_seed,
        config.max_ticks,
        config.metric_names,
    )

    metrics: list[MetricComparison] = []
    for name in config.metric_names:
        mc = compare_distributions(
            raw_a.get(name, []),
            raw_b.get(name, []),
            name,
            config.alpha,
        )
        metrics.append(mc)

    return ComparisonResult(
        label_a=config.label_a,
        label_b=config.label_b,
        num_iterations=config.num_iterations,
        metrics=metrics,
        raw_a=raw_a,
        raw_b=raw_b,
    )


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def format_comparison(result: ComparisonResult) -> str:
    """Format comparison result as human-readable table."""
    lines = [
        f"A/B Comparison: {result.label_a} vs {result.label_b}",
        f"Iterations: {result.num_iterations}",
        "",
        f"{'Metric':<25} {'Mean A':>10} {'Mean B':>10} {'p-value':>10} {'Sig?':>5} {'Effect':>8}",
        "-" * 72,
    ]
    for mc in result.metrics:
        sig = " *" if mc.significant else ""
        lines.append(
            f"{mc.metric:<25} {mc.mean_a:>10.3f} {mc.mean_b:>10.3f} "
            f"{mc.p_value:>10.4f} {sig:>5} {mc.effect_size:>8.3f}"
        )
    return "\n".join(lines)
