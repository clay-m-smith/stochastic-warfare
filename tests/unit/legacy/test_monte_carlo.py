"""Legacy Monte Carlo diagnostic unit tests.

Synthetic per-metric range comparisons are compatibility diagnostics only.
This module does not execute a historical study and cannot support a
historical-validation claim.
"""

from __future__ import annotations


import numpy as np
import pytest

from stochastic_warfare.legacy.validation.historical_data import HistoricalMetric
from stochastic_warfare.legacy.validation.monte_carlo import (
    ComparisonReport,
    MonteCarloConfig,
    MonteCarloResult,
    RunResult,
)


# ── helpers ──────────────────────────────────────────────────────────


def _make_runs(
    n: int = 10,
    exchange_ratio: float = 25.0,
    std: float = 5.0,
    seed_base: int = 42,
) -> list[RunResult]:
    """Generate synthetic run results with normal-distributed metrics."""
    rng = np.random.Generator(np.random.PCG64(seed_base))
    runs = []
    for i in range(n):
        er = max(0.0, rng.normal(exchange_ratio, std))
        runs.append(
            RunResult(
                seed=seed_base + i,
                metrics={
                    "exchange_ratio": er,
                    "duration_s": 1380.0 + rng.normal(0, 60),
                    "blue_units_destroyed": float(rng.integers(0, 2)),
                    "red_units_destroyed": float(rng.integers(10, 30)),
                },
                terminated_by="time_limit",
            )
        )
    return runs


# ── MonteCarloConfig ─────────────────────────────────────────────────


class TestMonteCarloConfig:
    def test_defaults(self) -> None:
        cfg = MonteCarloConfig()
        assert cfg.num_iterations == 100
        assert cfg.base_seed == 42
        assert cfg.confidence_level == 0.95

    def test_custom(self) -> None:
        cfg = MonteCarloConfig(num_iterations=1000, base_seed=7)
        assert cfg.num_iterations == 1000


# ── RunResult ────────────────────────────────────────────────────────


class TestRunResult:
    def test_construction(self) -> None:
        rr = RunResult(seed=42, metrics={"x": 1.0}, terminated_by="time_limit")
        assert rr.seed == 42
        assert rr.metrics["x"] == 1.0


# ── MonteCarloResult — statistics ────────────────────────────────────


class TestMonteCarloResultStats:
    def test_mean(self) -> None:
        runs = _make_runs(100, exchange_ratio=25.0, std=5.0)
        mc = MonteCarloResult(runs)
        # With 100 samples, mean should be close to 25
        assert mc.mean("exchange_ratio") == pytest.approx(25.0, abs=3.0)

    def test_median(self) -> None:
        runs = _make_runs(100, exchange_ratio=25.0, std=5.0)
        mc = MonteCarloResult(runs)
        assert mc.median("exchange_ratio") == pytest.approx(25.0, abs=4.0)

    def test_std(self) -> None:
        runs = _make_runs(200, exchange_ratio=25.0, std=5.0)
        mc = MonteCarloResult(runs)
        assert mc.std("exchange_ratio") == pytest.approx(5.0, abs=2.0)

    def test_percentile(self) -> None:
        runs = _make_runs(100, exchange_ratio=25.0, std=5.0)
        mc = MonteCarloResult(runs)
        p50 = mc.percentile("exchange_ratio", 50.0)
        assert p50 == pytest.approx(mc.median("exchange_ratio"))

    def test_confidence_interval(self) -> None:
        runs = _make_runs(100, exchange_ratio=25.0, std=5.0)
        mc = MonteCarloResult(runs)
        lo, hi = mc.confidence_interval("exchange_ratio", 0.95)
        assert lo < 25.0
        assert hi > 25.0
        assert lo < hi

    def test_distribution(self) -> None:
        runs = _make_runs(50)
        mc = MonteCarloResult(runs)
        dist = mc.distribution("exchange_ratio")
        assert len(dist) == 50

    def test_num_runs(self) -> None:
        runs = _make_runs(30)
        mc = MonteCarloResult(runs)
        assert mc.num_runs == 30

    def test_missing_metric(self) -> None:
        runs = _make_runs(10)
        mc = MonteCarloResult(runs)

        with pytest.raises(ValueError, match="missing metric 'nonexistent'"):
            mc.mean("nonexistent")
        with pytest.raises(ValueError, match="missing metric 'nonexistent'"):
            mc.std("nonexistent")
        with pytest.raises(ValueError, match="missing metric 'nonexistent'"):
            mc.distribution("nonexistent")

    def test_single_run(self) -> None:
        runs = [RunResult(seed=42, metrics={"x": 10.0}, terminated_by="done")]
        mc = MonteCarloResult(runs)
        assert mc.mean("x") == 10.0
        assert mc.std("x") == 0.0
        lo, hi = mc.confidence_interval("x")
        assert lo == 10.0

    def test_empty_runs(self) -> None:
        mc = MonteCarloResult([])
        assert mc.num_runs == 0

        with pytest.raises(ValueError, match="no runs"):
            mc.mean("x")

    @pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
    def test_nonfinite_values_rejected(self, value: float) -> None:
        runs = [
            RunResult(seed=1, metrics={"er": value}, terminated_by="t"),
            RunResult(seed=2, metrics={"er": 25.0}, terminated_by="t"),
        ]
        mc = MonteCarloResult(runs)

        with pytest.raises(ValueError, match="non-finite metric 'er'"):
            mc.mean("er")

    def test_partial_metric_vector_rejected(self) -> None:
        runs = [
            RunResult(seed=1, metrics={"er": 25.0}, terminated_by="t"),
            RunResult(seed=2, metrics={"other": 30.0}, terminated_by="t"),
        ]

        with pytest.raises(ValueError, match="missing metric 'er'.*seed 2"):
            MonteCarloResult(runs).mean("er")


# ── MonteCarloResult — comparison ────────────────────────────────────


class TestLegacyHistoricalComparisonDiagnostic:
    """Exercise the legacy comparator without granting it verdict authority."""

    def test_compare_within_tolerance(self) -> None:
        runs = _make_runs(50, exchange_ratio=25.0, std=3.0)
        mc = MonteCarloResult(runs)
        historical = [
            HistoricalMetric(name="exchange_ratio", value=28.0, tolerance_factor=2.0),
        ]
        report = mc.compare_to_historical(historical)
        # 25 is within [14, 56] → pass
        assert report.metric_results[0].within_tolerance is True

    def test_compare_outside_tolerance(self) -> None:
        runs = _make_runs(50, exchange_ratio=5.0, std=1.0)
        mc = MonteCarloResult(runs)
        historical = [
            HistoricalMetric(name="exchange_ratio", value=28.0, tolerance_factor=2.0),
        ]
        report = mc.compare_to_historical(historical)
        # 5 is below [14, 56] → fail
        assert report.metric_results[0].within_tolerance is False

    def test_compare_missing_metric(self) -> None:
        runs = [RunResult(seed=1, metrics={"other": 1.0}, terminated_by="t")]
        mc = MonteCarloResult(runs)
        historical = [
            HistoricalMetric(name="exchange_ratio", value=28.0),
        ]

        with pytest.raises(ValueError, match="missing metric 'exchange_ratio'.*seed 1"):
            mc.compare_to_historical(historical)

    def test_compare_empty_historical_rejected(self) -> None:
        mc = MonteCarloResult(_make_runs(2))

        with pytest.raises(ValueError, match="requires at least one metric"):
            mc.compare_to_historical([])

    def test_compare_rejects_incomplete_run_vectors(self) -> None:
        runs = [
            RunResult(seed=1, metrics={"exchange_ratio": 25.0}, terminated_by="t"),
            RunResult(seed=2, metrics={"other": 1.0}, terminated_by="t"),
        ]
        historical = [HistoricalMetric(name="exchange_ratio", value=28.0)]

        with pytest.raises(ValueError, match="missing metric"):
            MonteCarloResult(runs).compare_to_historical(historical)

    def test_compare_ignores_unrequested_nonfinite_diagnostics(self) -> None:
        runs = [
            RunResult(
                seed=1,
                metrics={"duration_s": 10.0, "exchange_ratio": float("inf")},
                terminated_by="t",
            ),
            RunResult(
                seed=2,
                metrics={"duration_s": 12.0, "exchange_ratio": float("inf")},
                terminated_by="t",
            ),
        ]
        historical = [
            HistoricalMetric(
                name="duration_s",
                value=11.0,
                tolerance_factor=2.0,
            ),
        ]

        report = MonteCarloResult(runs).compare_to_historical(historical)

        assert [result.metric_name for result in report.metric_results] == [
            "duration_s",
        ]
        assert report.metric_results[0].simulated_mean == pytest.approx(11.0)


# ── ComparisonReport ─────────────────────────────────────────────────


class TestComparisonReport:
    def _make_report(self, passing: int, failing: int) -> ComparisonReport:
        from stochastic_warfare.legacy.validation.historical_data import ComparisonResult

        results = []
        for i in range(passing):
            results.append(
                ComparisonResult(
                    metric_name=f"pass_{i}",
                    historical_value=10.0,
                    simulated_mean=10.0,
                    simulated_std=1.0,
                    tolerance_factor=2.0,
                    within_tolerance=True,
                    deviation_factor=1.0,
                )
            )
        for i in range(failing):
            results.append(
                ComparisonResult(
                    metric_name=f"fail_{i}",
                    historical_value=10.0,
                    simulated_mean=1.0,
                    simulated_std=0.5,
                    tolerance_factor=2.0,
                    within_tolerance=False,
                    deviation_factor=0.1,
                )
            )
        return ComparisonReport(results)

    @pytest.mark.test_evidence("behavioral_oracle")
    def test_report_has_no_boolean_validation_verdict(self) -> None:
        report = self._make_report(3, 0)
        assert not hasattr(report, "all_within_tolerance")

    def test_passing_count(self) -> None:
        report = self._make_report(3, 2)
        assert report.passing_count() == 3
        assert report.failing_count() == 2

    def test_summary_format(self) -> None:
        report = self._make_report(1, 1)
        text = report.summary()
        assert "1/2" in text
        assert "legacy diagnostic only" in text
        assert "IN RANGE" in text
        assert "OUT OF RANGE" in text
        assert "historical validation" not in text

    def test_empty_report_rejected(self) -> None:
        with pytest.raises(ValueError, match="requires at least one metric"):
            ComparisonReport([])
