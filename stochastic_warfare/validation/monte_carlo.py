"""Monte Carlo harness for engagement and campaign validation.

Runs N iterations of a scenario with different PRNG seeds, collects
per-run metrics, and compares aggregate statistics against historical
outcomes.  Supports both engagement-level (:class:`MonteCarloHarness`)
and campaign-level (:class:`CampaignMonteCarloHarness`) validation.
"""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.validation.historical_data import (
    ComparisonResult,
    HistoricalDataLoader,
    HistoricalEngagement,
    HistoricalMetric,
)
from stochastic_warfare.validation.metrics import EngagementMetrics
from stochastic_warfare.validation.scenario_runner import ScenarioRunner, ScenarioRunnerConfig

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class MonteCarloConfig(BaseModel):
    """Configuration for Monte Carlo runs."""

    num_iterations: int = 100
    base_seed: int = 42
    confidence_level: float = 0.95
    max_workers: int = 1  # >1 enables process-parallel MC


# ---------------------------------------------------------------------------
# Per-run result
# ---------------------------------------------------------------------------


@dataclass
class RunResult:
    """Metrics from a single simulation run."""

    seed: int
    metrics: dict[str, float]
    terminated_by: str


# ---------------------------------------------------------------------------
# Comparison report
# ---------------------------------------------------------------------------


class ComparisonReport:
    """Aggregate comparison of Monte Carlo results to historical data."""

    def __init__(self, metric_results: list[ComparisonResult]) -> None:
        self.metric_results = metric_results

    def all_within_tolerance(self) -> bool:
        """True if every metric falls within historical tolerance."""
        return all(r.within_tolerance for r in self.metric_results)

    def passing_count(self) -> int:
        """Number of metrics within tolerance."""
        return sum(1 for r in self.metric_results if r.within_tolerance)

    def failing_count(self) -> int:
        """Number of metrics outside tolerance."""
        return sum(1 for r in self.metric_results if not r.within_tolerance)

    def summary(self) -> str:
        """Human-readable summary of comparison results."""
        lines = [
            f"Comparison Report: {self.passing_count()}/{len(self.metric_results)} metrics within tolerance",
            "",
        ]
        for r in self.metric_results:
            status = "PASS" if r.within_tolerance else "FAIL"
            lines.append(
                f"  [{status}] {r.metric_name}: "
                f"historical={r.historical_value:.3f}, "
                f"simulated={r.simulated_mean:.3f} +/- {r.simulated_std:.3f}, "
                f"deviation={r.deviation_factor:.3f}x, "
                f"tolerance={r.tolerance_factor:.1f}x"
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Monte Carlo result
# ---------------------------------------------------------------------------


class MonteCarloResult:
    """Collected results from all Monte Carlo runs."""

    def __init__(self, runs: list[RunResult]) -> None:
        self.runs = runs

    @property
    def num_runs(self) -> int:
        return len(self.runs)

    def _values(self, metric: str) -> np.ndarray:
        """Extract values of *metric* across all runs."""
        vals = []
        for run in self.runs:
            v = run.metrics.get(metric)
            if v is not None and np.isfinite(v):
                vals.append(v)
        return np.array(vals, dtype=np.float64) if vals else np.array([], dtype=np.float64)

    def mean(self, metric: str) -> float:
        """Mean of *metric* across runs."""
        v = self._values(metric)
        return float(np.mean(v)) if len(v) > 0 else 0.0

    def median(self, metric: str) -> float:
        """Median of *metric* across runs."""
        v = self._values(metric)
        return float(np.median(v)) if len(v) > 0 else 0.0

    def std(self, metric: str) -> float:
        """Standard deviation of *metric* across runs."""
        v = self._values(metric)
        return float(np.std(v, ddof=1)) if len(v) > 1 else 0.0

    def percentile(self, metric: str, p: float) -> float:
        """Percentile *p* (0-100) of *metric*."""
        v = self._values(metric)
        return float(np.percentile(v, p)) if len(v) > 0 else 0.0

    def confidence_interval(
        self, metric: str, level: float = 0.95
    ) -> tuple[float, float]:
        """Confidence interval for the mean of *metric*.

        Uses Student's t-distribution for n < 30 (exact small-sample CI)
        and normal approximation for n >= 30 (CLT).
        """
        v = self._values(metric)
        n = len(v)
        if n < 2:
            m = float(np.mean(v)) if n == 1 else 0.0
            return (m, m)

        m = float(np.mean(v))
        se = float(np.std(v, ddof=1)) / np.sqrt(n)

        if n < 30:
            # Use t-distribution for small samples
            from scipy.stats import t as t_dist

            alpha = 1.0 - level
            t_val = float(t_dist.ppf(1.0 - alpha / 2.0, df=n - 1))
            return (m - t_val * se, m + t_val * se)
        else:
            # Normal approximation (CLT valid)
            from scipy.stats import norm

            alpha = 1.0 - level
            z = float(norm.ppf(1.0 - alpha / 2.0))
            return (m - z * se, m + z * se)

    def distribution(self, metric: str) -> np.ndarray:
        """Raw array of *metric* values across runs."""
        return self._values(metric)

    def compare_to_historical(
        self, historical: list[HistoricalMetric]
    ) -> ComparisonReport:
        """Compare MC statistics to historical metrics."""
        simulated: dict[str, float] = {}
        stds: dict[str, float] = {}

        # Collect all metric names from runs
        all_names: set[str] = set()
        for run in self.runs:
            all_names.update(run.metrics.keys())

        for name in all_names:
            simulated[name] = self.mean(name)
            stds[name] = self.std(name)

        results = HistoricalDataLoader.compare_all(simulated, historical, stds)
        return ComparisonReport(results)


# ---------------------------------------------------------------------------
# Monte Carlo Harness
# ---------------------------------------------------------------------------


def _run_single_iteration(args: tuple[Any, ...]) -> RunResult:
    """Execute one MC iteration in a worker process.

    Top-level function so it can be pickled by :class:`ProcessPoolExecutor`.
    Each worker constructs its own :class:`ScenarioRunner` to avoid shared state.
    """
    runner_config_dict, engagement_dict, seed, blue_side, red_side = args
    runner_config = ScenarioRunnerConfig.model_validate(runner_config_dict)
    engagement = HistoricalEngagement.model_validate(engagement_dict)
    runner = ScenarioRunner(runner_config)
    sim_result = runner.run(engagement, seed=seed)
    metrics = EngagementMetrics.extract_all(sim_result, blue_side, red_side)
    return RunResult(seed=seed, metrics=metrics, terminated_by=sim_result.terminated_by)


class MonteCarloHarness:
    """Run N scenario iterations and collect statistics.

    Parameters
    ----------
    runner:
        ScenarioRunner to execute each iteration (used for serial mode).
    config:
        Monte Carlo configuration.  Set ``max_workers > 1`` to run
        iterations in parallel using :class:`ProcessPoolExecutor`.
    """

    def __init__(
        self,
        runner: ScenarioRunner,
        config: MonteCarloConfig | None = None,
    ) -> None:
        self._runner = runner
        self._config = config or MonteCarloConfig()

    def run(
        self,
        engagement: HistoricalEngagement,
        blue_side: str = "blue",
        red_side: str = "red",
    ) -> MonteCarloResult:
        """Execute *num_iterations* runs and return collected results."""
        n = self._config.num_iterations
        seeds = [self._config.base_seed + i for i in range(n)]

        if self._config.max_workers > 1:
            run_results = self._run_parallel(engagement, seeds, blue_side, red_side)
        else:
            run_results = self._run_serial(engagement, seeds, blue_side, red_side)

        logger.info("MC complete: %d runs", len(run_results))
        return MonteCarloResult(run_results)

    def _run_serial(
        self,
        engagement: HistoricalEngagement,
        seeds: list[int],
        blue_side: str,
        red_side: str,
    ) -> list[RunResult]:
        """Run iterations sequentially in the current process."""
        run_results: list[RunResult] = []
        n = len(seeds)
        for i, seed in enumerate(seeds):
            logger.info("MC run %d/%d (seed=%d)", i + 1, n, seed)
            sim_result = self._runner.run(engagement, seed=seed)
            metrics = EngagementMetrics.extract_all(sim_result, blue_side, red_side)
            run_results.append(
                RunResult(seed=seed, metrics=metrics, terminated_by=sim_result.terminated_by)
            )
        return run_results

    def _run_parallel(
        self,
        engagement: HistoricalEngagement,
        seeds: list[int],
        blue_side: str,
        red_side: str,
    ) -> list[RunResult]:
        """Run iterations in parallel using submit + as_completed.

        Results are collected as they finish (out of order) and sorted
        by seed at the end for deterministic ordering.
        """
        workers = min(self._config.max_workers, len(seeds), os.cpu_count() or 1)
        logger.info(
            "MC parallel: %d iterations across %d workers", len(seeds), workers
        )

        runner_cfg_dict = self._runner._config.model_dump()
        eng_dict = engagement.model_dump()

        run_results: list[RunResult] = []
        completed = 0
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    _run_single_iteration,
                    (runner_cfg_dict, eng_dict, seed, blue_side, red_side),
                ): seed
                for seed in seeds
            }
            for future in as_completed(futures):
                result = future.result()
                completed += 1
                logger.info(
                    "MC run %d/%d complete (seed=%d)",
                    completed, len(seeds), result.seed,
                )
                run_results.append(result)

        # Sort by seed for deterministic ordering
        run_results.sort(key=lambda r: r.seed)
        return run_results


# ---------------------------------------------------------------------------
# Campaign Monte Carlo — top-level picklable iteration function
# ---------------------------------------------------------------------------


def _run_campaign_iteration(args: tuple[Any, ...]) -> RunResult:
    """Execute one campaign MC iteration in a worker process.

    Top-level function so it can be pickled by :class:`ProcessPoolExecutor`.
    Each worker constructs its own :class:`CampaignRunner` to avoid shared state.
    """
    from stochastic_warfare.validation.campaign_data import HistoricalCampaign
    from stochastic_warfare.validation.campaign_metrics import CampaignValidationMetrics
    from stochastic_warfare.validation.campaign_runner import (
        CampaignRunner,
        CampaignRunnerConfig,
    )

    runner_config_dict, campaign_dict, seed, blue_side, red_side = args
    runner_config = CampaignRunnerConfig.model_validate(runner_config_dict)
    campaign = HistoricalCampaign.model_validate(campaign_dict)
    runner = CampaignRunner(runner_config)
    result = runner.run(campaign, seed=seed)
    metrics = CampaignValidationMetrics.extract_all(result, blue_side, red_side)
    return RunResult(seed=seed, metrics=metrics, terminated_by=result.terminated_by)


# ---------------------------------------------------------------------------
# Campaign Monte Carlo Harness
# ---------------------------------------------------------------------------


class CampaignMonteCarloHarness:
    """Run N campaign iterations and collect statistics.

    Campaign analog of :class:`MonteCarloHarness`.  Wraps
    :class:`CampaignRunner` in a Monte Carlo loop with per-iteration
    PRNG seeds.

    Parameters
    ----------
    runner:
        CampaignRunner to execute each iteration (used for serial mode).
    config:
        Monte Carlo configuration.  Set ``max_workers > 1`` to run
        iterations in parallel using :class:`ProcessPoolExecutor`.
    """

    def __init__(
        self,
        runner: Any,
        config: MonteCarloConfig | None = None,
    ) -> None:
        self._runner = runner
        self._config = config or MonteCarloConfig()

    def run(
        self,
        campaign: Any,
        blue_side: str = "blue",
        red_side: str = "red",
    ) -> MonteCarloResult:
        """Execute *num_iterations* campaign runs and return collected results."""
        n = self._config.num_iterations
        seeds = [self._config.base_seed + i for i in range(n)]

        if self._config.max_workers > 1:
            run_results = self._run_parallel(campaign, seeds, blue_side, red_side)
        else:
            run_results = self._run_serial(campaign, seeds, blue_side, red_side)

        logger.info("Campaign MC complete: %d runs", len(run_results))
        return MonteCarloResult(run_results)

    def _run_serial(
        self,
        campaign: Any,
        seeds: list[int],
        blue_side: str,
        red_side: str,
    ) -> list[RunResult]:
        """Run campaign iterations sequentially."""
        from stochastic_warfare.validation.campaign_metrics import CampaignValidationMetrics

        run_results: list[RunResult] = []
        n = len(seeds)
        for i, seed in enumerate(seeds):
            logger.info("Campaign MC run %d/%d (seed=%d)", i + 1, n, seed)
            result = self._runner.run(campaign, seed=seed)
            metrics = CampaignValidationMetrics.extract_all(result, blue_side, red_side)
            run_results.append(
                RunResult(seed=seed, metrics=metrics, terminated_by=result.terminated_by)
            )
        return run_results

    def _run_parallel(
        self,
        campaign: Any,
        seeds: list[int],
        blue_side: str,
        red_side: str,
    ) -> list[RunResult]:
        """Run campaign iterations in parallel using submit + as_completed.

        Results sorted by seed for deterministic ordering.
        """
        workers = min(self._config.max_workers, len(seeds), os.cpu_count() or 1)
        logger.info(
            "Campaign MC parallel: %d iterations across %d workers",
            len(seeds), workers,
        )

        runner_cfg_dict = self._runner._config.model_dump()
        campaign_dict = campaign.model_dump()

        run_results: list[RunResult] = []
        completed = 0
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    _run_campaign_iteration,
                    (runner_cfg_dict, campaign_dict, seed, blue_side, red_side),
                ): seed
                for seed in seeds
            }
            for future in as_completed(futures):
                result = future.result()
                completed += 1
                logger.info(
                    "Campaign MC run %d/%d complete (seed=%d)",
                    completed, len(seeds), result.seed,
                )
                run_results.append(result)

        # Sort by seed for deterministic ordering
        run_results.sort(key=lambda r: r.seed)
        return run_results
