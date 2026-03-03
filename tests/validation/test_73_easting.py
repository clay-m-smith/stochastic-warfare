"""Validation tests for 73 Easting scenario.

Tests that the scenario loads, runs, produces non-trivial results,
and (after calibration) produces metrics within historical tolerance.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from stochastic_warfare.validation.historical_data import HistoricalDataLoader
from stochastic_warfare.validation.metrics import EngagementMetrics
from stochastic_warfare.validation.monte_carlo import (
    MonteCarloConfig,
    MonteCarloHarness,
    MonteCarloResult,
)
from stochastic_warfare.validation.scenario_runner import (
    ScenarioRunner,
    ScenarioRunnerConfig,
    TimeLimitTermination,
)

_SCENARIO_PATH = Path("data/scenarios/73_easting/scenario.yaml")


@pytest.fixture(scope="module")
def engagement():
    loader = HistoricalDataLoader()
    return loader.load(_SCENARIO_PATH)


@pytest.fixture(scope="module")
def runner():
    config = ScenarioRunnerConfig(master_seed=42, max_ticks=2000, data_dir="data")
    return ScenarioRunner(config)


@pytest.fixture(scope="module")
def single_run(engagement, runner):
    return runner.run(engagement)


# ── Scenario loading ─────────────────────────────────────────────────


class TestScenarioLoading:
    def test_loads_scenario(self, engagement) -> None:
        assert "73 Easting" in engagement.name
        assert "Eagle Troop" in engagement.name

    def test_blue_forces(self, engagement) -> None:
        assert engagement.blue_forces.personnel_total == 120
        assert len(engagement.blue_forces.units) == 2

    def test_red_forces(self, engagement) -> None:
        assert engagement.red_forces.personnel_total == 500
        assert len(engagement.red_forces.units) == 2

    def test_terrain(self, engagement) -> None:
        assert engagement.terrain.terrain_type == "flat_desert"
        assert engagement.terrain.width_m == 6000

    def test_documented_outcomes(self, engagement) -> None:
        assert len(engagement.documented_outcomes) >= 3

    def test_calibration_overrides(self, engagement) -> None:
        assert "hit_probability_modifier" in engagement.calibration_overrides

    def test_behavior_rules(self, engagement) -> None:
        assert "blue" in engagement.behavior_rules
        assert "red" in engagement.behavior_rules


# ── Single run ───────────────────────────────────────────────────────


class TestSingleRun:
    def test_simulation_completes(self, single_run) -> None:
        assert single_run.ticks_executed > 0

    def test_has_final_states(self, single_run) -> None:
        assert len(single_run.units_final) > 0

    def test_has_events(self, single_run) -> None:
        assert len(single_run.event_log) > 0

    def test_terminated(self, single_run) -> None:
        assert single_run.terminated_by != ""

    def test_blue_side_present(self, single_run) -> None:
        blue = [u for u in single_run.units_final if u.side == "blue"]
        assert len(blue) > 0

    def test_red_side_present(self, single_run) -> None:
        red = [u for u in single_run.units_final if u.side == "red"]
        assert len(red) > 0


# ── Metric extraction ────────────────────────────────────────────────


class TestMetricExtraction:
    def test_metrics_extracted(self, single_run) -> None:
        metrics = EngagementMetrics.extract_all(single_run)
        assert "exchange_ratio" in metrics
        assert "duration_s" in metrics

    def test_duration_nonzero(self, single_run) -> None:
        metrics = EngagementMetrics.extract_all(single_run)
        assert metrics["duration_s"] > 0

    def test_some_combat_occurred(self, single_run) -> None:
        assert len(single_run.event_log) > 0


# ── Deterministic replay ─────────────────────────────────────────────


class TestDeterministicReplay:
    def test_same_seed_same_result(self, engagement, runner) -> None:
        r1 = runner.run(engagement, seed=42)
        r2 = runner.run(engagement, seed=42)
        m1 = EngagementMetrics.extract_all(r1)
        m2 = EngagementMetrics.extract_all(r2)
        for key in m1:
            assert m1[key] == m2[key], f"Mismatch on {key}: {m1[key]} != {m2[key]}"

    def test_different_seed_different_result(self, engagement, runner) -> None:
        r1 = runner.run(engagement, seed=42)
        r2 = runner.run(engagement, seed=999)
        m1 = EngagementMetrics.extract_all(r1)
        m2 = EngagementMetrics.extract_all(r2)
        # At least some metrics should differ
        assert m1 != m2 or r1.ticks_executed != r2.ticks_executed


# ── Monte Carlo (fast, 5 runs) ───────────────────────────────────────


class TestMonteCarloFast:
    def test_mc_runs(self, engagement, runner) -> None:
        mc_config = MonteCarloConfig(num_iterations=5, base_seed=42)
        harness = MonteCarloHarness(runner, mc_config)
        mc_result = harness.run(engagement)
        assert mc_result.num_runs == 5

    def test_mc_statistics(self, engagement, runner) -> None:
        mc_config = MonteCarloConfig(num_iterations=5, base_seed=42)
        harness = MonteCarloHarness(runner, mc_config)
        mc_result = harness.run(engagement)
        assert mc_result.mean("duration_s") > 0

    def test_mc_comparison(self, engagement, runner) -> None:
        mc_config = MonteCarloConfig(num_iterations=5, base_seed=42)
        harness = MonteCarloHarness(runner, mc_config)
        mc_result = harness.run(engagement)
        report = mc_result.compare_to_historical(engagement.documented_outcomes)
        assert len(report.metric_results) > 0


# ── Monte Carlo (1000 runs, slow) ────────────────────────────────────


@pytest.mark.slow
class TestMonteCarloFull:
    def test_mc_1000_runs(self, engagement, runner) -> None:
        mc_config = MonteCarloConfig(num_iterations=1000, base_seed=42)
        harness = MonteCarloHarness(runner, mc_config)
        mc_result = harness.run(engagement)
        assert mc_result.num_runs == 1000

    def test_mc_1000_convergence(self, engagement, runner) -> None:
        mc_config = MonteCarloConfig(num_iterations=1000, base_seed=42)
        harness = MonteCarloHarness(runner, mc_config)
        mc_result = harness.run(engagement)
        # CI should be narrower than full tolerance
        lo, hi = mc_result.confidence_interval("duration_s", 0.95)
        assert hi - lo < mc_result.mean("duration_s")
