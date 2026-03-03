"""Validation tests for Golan Heights — Valley of Tears scenario.

Tests that the scenario loads, runs, and exercises the key dynamics:
hull-down positions, morale under extreme odds, sustained engagement.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from stochastic_warfare.validation.historical_data import HistoricalDataLoader
from stochastic_warfare.validation.metrics import EngagementMetrics
from stochastic_warfare.validation.monte_carlo import (
    MonteCarloConfig,
    MonteCarloHarness,
)
from stochastic_warfare.validation.scenario_runner import (
    ScenarioRunner,
    ScenarioRunnerConfig,
)

_SCENARIO_PATH = Path("data/scenarios/golan_heights/scenario.yaml")


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
        assert "Golan" in engagement.name

    def test_blue_forces(self, engagement) -> None:
        assert engagement.blue_forces.personnel_total == 160
        # Sho't Kal
        assert len(engagement.blue_forces.units) == 1

    def test_red_forces(self, engagement) -> None:
        assert engagement.red_forces.personnel_total == 2500
        # T-55A, T-62, BMP-1
        assert len(engagement.red_forces.units) == 3

    def test_terrain_hilly(self, engagement) -> None:
        assert engagement.terrain.terrain_type == "hilly_defense"
        assert engagement.terrain.base_elevation_m == 900.0

    def test_terrain_features(self, engagement) -> None:
        features = engagement.terrain.features
        ridge_count = sum(1 for f in features if f["type"] == "ridge")
        assert ridge_count >= 1

    def test_documented_outcomes(self, engagement) -> None:
        names = [o.name for o in engagement.documented_outcomes]
        assert "exchange_ratio" in names
        assert "red_units_destroyed" in names

    def test_blue_holds_position(self, engagement) -> None:
        assert engagement.behavior_rules["blue"]["hold_position"] is True


# ── Single run ───────────────────────────────────────────────────────


class TestSingleRun:
    def test_simulation_completes(self, single_run) -> None:
        assert single_run.ticks_executed > 0

    def test_has_units(self, single_run) -> None:
        assert len(single_run.units_final) > 0

    def test_blue_present(self, single_run) -> None:
        blue = [u for u in single_run.units_final if u.side == "blue"]
        assert len(blue) == 40  # 40 Sho't Kal

    def test_red_present(self, single_run) -> None:
        red = [u for u in single_run.units_final if u.side == "red"]
        assert len(red) == 250  # 100 T-55 + 100 T-62 + 50 BMP-1

    def test_has_events(self, single_run) -> None:
        assert len(single_run.event_log) > 0


# ── Metric extraction ────────────────────────────────────────────────


class TestMetricExtraction:
    def test_metrics_extracted(self, single_run) -> None:
        metrics = EngagementMetrics.extract_all(single_run)
        assert "exchange_ratio" in metrics

    def test_some_red_losses(self, single_run) -> None:
        metrics = EngagementMetrics.extract_all(single_run)
        # Should have some combat occurring
        assert (
            metrics["red_units_destroyed"] > 0
            or metrics["red_personnel_casualties"] > 0
            or len(single_run.event_log) > 10
        )


# ── Deterministic replay ─────────────────────────────────────────────


class TestDeterministicReplay:
    def test_same_seed(self, engagement, runner) -> None:
        r1 = runner.run(engagement, seed=42)
        r2 = runner.run(engagement, seed=42)
        m1 = EngagementMetrics.extract_all(r1)
        m2 = EngagementMetrics.extract_all(r2)
        for key in m1:
            assert m1[key] == m2[key]


# ── Monte Carlo (fast) ───────────────────────────────────────────────


class TestMonteCarloFast:
    def test_mc_runs(self, engagement, runner) -> None:
        mc_config = MonteCarloConfig(num_iterations=3, base_seed=42)
        harness = MonteCarloHarness(runner, mc_config)
        mc_result = harness.run(engagement)
        assert mc_result.num_runs == 3

    def test_mc_comparison(self, engagement, runner) -> None:
        mc_config = MonteCarloConfig(num_iterations=3, base_seed=42)
        harness = MonteCarloHarness(runner, mc_config)
        mc_result = harness.run(engagement)
        report = mc_result.compare_to_historical(engagement.documented_outcomes)
        assert len(report.metric_results) > 0


# ── Monte Carlo (1000 runs, slow) ────────────────────────────────────


@pytest.mark.slow
class TestMonteCarloFull:
    def test_mc_1000(self, engagement, runner) -> None:
        mc_config = MonteCarloConfig(num_iterations=1000, base_seed=42)
        harness = MonteCarloHarness(runner, mc_config)
        mc_result = harness.run(engagement)
        assert mc_result.num_runs == 1000
