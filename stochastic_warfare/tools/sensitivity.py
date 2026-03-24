"""Parameter sensitivity sweep for scenario analysis.

Runs a scenario at multiple parameter values, collecting metrics
at each point for sensitivity visualization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class SweepConfig(BaseModel):
    """Configuration for a parameter sweep."""

    scenario_path: str
    parameter_name: str  # calibration_overrides key
    values: list[float]
    metric_names: list[str] = ["blue_destroyed", "red_destroyed"]
    iterations_per_point: int = 10
    base_seed: int = 42
    max_ticks: int = 100


# ---------------------------------------------------------------------------
# Result structures
# ---------------------------------------------------------------------------


@dataclass
class MetricResult:
    """Statistics for one metric at one sweep point."""

    metric: str
    mean: float
    std: float
    min: float
    max: float
    values: list[float] = field(default_factory=list)


@dataclass
class SweepPoint:
    """Results at one parameter value."""

    parameter_value: float
    metric_results: list[MetricResult] = field(default_factory=list)


@dataclass
class SweepResult:
    """Complete sweep result."""

    parameter_name: str
    points: list[SweepPoint] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Core sweep logic
# ---------------------------------------------------------------------------


def run_sweep(config: SweepConfig) -> SweepResult:
    """Run a parameter sweep over a scenario.

    For each value in ``config.values``, runs ``iterations_per_point``
    simulations with the parameter set in ``calibration_overrides``,
    collecting the specified metrics.

    Uses the same seed sequence at every sweep point — only the
    parameter changes.
    """
    from stochastic_warfare.tools._run_helpers import run_scenario_batch

    result = SweepResult(parameter_name=config.parameter_name)

    for val in config.values:
        overrides = {config.parameter_name: val}
        raw = run_scenario_batch(
            config.scenario_path,
            overrides,
            config.iterations_per_point,
            config.base_seed,
            config.max_ticks,
            config.metric_names,
        )

        metric_results: list[MetricResult] = []
        for name in config.metric_names:
            vals = raw.get(name, [])
            arr = np.array(vals, dtype=float) if vals else np.array([0.0])
            metric_results.append(
                MetricResult(
                    metric=name,
                    mean=float(np.mean(arr)),
                    std=float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0,
                    min=float(np.min(arr)),
                    max=float(np.max(arr)),
                    values=vals,
                )
            )

        result.points.append(SweepPoint(parameter_value=val, metric_results=metric_results))

    return result


# ---------------------------------------------------------------------------
# Plotting (requires matplotlib)
# ---------------------------------------------------------------------------


def plot_sweep(result: SweepResult, metric: str | None = None) -> Any:
    """Plot sweep results as errorbar chart.

    Parameters
    ----------
    result:
        Output from ``run_sweep()``.
    metric:
        Which metric to plot. If None, plots the first available.

    Returns ``matplotlib.figure.Figure``.
    """
    import matplotlib.pyplot as plt

    if not result.points:
        fig, ax = plt.subplots()
        ax.text(0.5, 0.5, "No sweep data", transform=ax.transAxes, ha="center")
        plt.close(fig)
        return fig

    # Determine metric to plot
    if metric is None:
        metric = result.points[0].metric_results[0].metric

    x_vals = [p.parameter_value for p in result.points]
    means = []
    stds = []
    for p in result.points:
        for mr in p.metric_results:
            if mr.metric == metric:
                means.append(mr.mean)
                stds.append(mr.std)
                break
        else:
            means.append(0.0)
            stds.append(0.0)

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.errorbar(x_vals, means, yerr=stds, marker="o", capsize=4, linewidth=1.5)
    ax.set_xlabel(result.parameter_name)
    ax.set_ylabel(metric)
    ax.set_title(f"Sensitivity: {metric} vs {result.parameter_name}")
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    plt.close(fig)
    return fig
