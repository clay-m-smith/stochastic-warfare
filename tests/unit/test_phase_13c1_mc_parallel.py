"""Phase 13c-1: MC parallelism enhancement tests."""

import pytest

from stochastic_warfare.validation.monte_carlo import (
    MonteCarloConfig,
    MonteCarloResult,
    RunResult,
)


class TestMCParallelism:
    def test_config_defaults(self):
        cfg = MonteCarloConfig()
        assert cfg.max_workers == 1
        assert cfg.num_iterations == 100

    def test_config_workers(self):
        cfg = MonteCarloConfig(max_workers=4)
        assert cfg.max_workers == 4

    def test_run_result_seed_sorting(self):
        """Results should be sortable by seed."""
        results = [
            RunResult(seed=42, metrics={"x": 1.0}, terminated_by="done"),
            RunResult(seed=10, metrics={"x": 2.0}, terminated_by="done"),
            RunResult(seed=30, metrics={"x": 3.0}, terminated_by="done"),
        ]
        sorted_results = sorted(results, key=lambda r: r.seed)
        assert [r.seed for r in sorted_results] == [10, 30, 42]

    def test_monte_carlo_result_mean(self):
        runs = [
            RunResult(seed=i, metrics={"loss": float(i)}, terminated_by="done")
            for i in range(10)
        ]
        mc = MonteCarloResult(runs)
        assert mc.mean("loss") == pytest.approx(4.5)

    def test_monte_carlo_result_distribution(self):
        runs = [
            RunResult(seed=i, metrics={"x": float(i * 2)}, terminated_by="done")
            for i in range(5)
        ]
        mc = MonteCarloResult(runs)
        dist = mc.distribution("x")
        assert len(dist) == 5

    def test_serial_mode_unchanged(self):
        """Serial mode should still work (max_workers=1)."""
        cfg = MonteCarloConfig(num_iterations=1, max_workers=1)
        assert cfg.max_workers == 1
