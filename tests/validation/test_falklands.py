"""Validation tests for Falklands Naval scenario.

Tests that the scenario loads, runs, and produces metrics
for the Sheffield Exocet engagement.
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

_SCENARIO_PATH = Path("data/scenarios/falklands_naval/scenario.yaml")


@pytest.fixture(scope="module")
def engagement():
    loader = HistoricalDataLoader()
    return loader.load(_SCENARIO_PATH)


@pytest.fixture(scope="module")
def runner():
    config = ScenarioRunnerConfig(master_seed=42, max_ticks=1000, data_dir="data")
    return ScenarioRunner(config)


@pytest.fixture(scope="module")
def single_run(engagement, runner):
    return runner.run(engagement)


# ── Scenario loading ─────────────────────────────────────────────────


class TestScenarioLoading:
    def test_loads_scenario(self, engagement) -> None:
        assert "Falklands" in engagement.name

    def test_blue_forces(self, engagement) -> None:
        assert engagement.blue_forces.personnel_total == 1200
        # Type 42, Type 22, Sea Harrier
        assert len(engagement.blue_forces.units) == 3

    def test_red_forces(self, engagement) -> None:
        # Super Etendard
        assert len(engagement.red_forces.units) == 1

    def test_terrain_ocean(self, engagement) -> None:
        assert engagement.terrain.terrain_type == "open_ocean"

    def test_documented_outcomes(self, engagement) -> None:
        assert len(engagement.documented_outcomes) >= 2
        names = [o.name for o in engagement.documented_outcomes]
        assert "blue_ships_sunk" in names


# ── Single run ───────────────────────────────────────────────────────


class TestSingleRun:
    def test_simulation_completes(self, single_run) -> None:
        assert single_run.ticks_executed > 0

    def test_has_units(self, single_run) -> None:
        assert len(single_run.units_final) > 0

    def test_blue_naval_present(self, single_run) -> None:
        naval = [
            u
            for u in single_run.units_final
            if u.side == "blue"
            and u.unit_type in ("type42_destroyer", "type22_frigate")
        ]
        assert len(naval) > 0

    def test_has_events(self, single_run) -> None:
        assert len(single_run.event_log) > 0


# ── Metric extraction ────────────────────────────────────────────────


class TestMetricExtraction:
    def test_metrics_extracted(self, single_run) -> None:
        metrics = EngagementMetrics.extract_all(single_run)
        assert "blue_ships_sunk" in metrics

    def test_duration_reasonable(self, single_run) -> None:
        metrics = EngagementMetrics.extract_all(single_run)
        assert metrics["duration_s"] > 0


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
        mc_config = MonteCarloConfig(num_iterations=5, base_seed=42)
        harness = MonteCarloHarness(runner, mc_config)
        mc_result = harness.run(engagement)
        assert mc_result.num_runs == 5

    def test_mc_comparison(self, engagement, runner) -> None:
        mc_config = MonteCarloConfig(num_iterations=5, base_seed=42)
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
