"""Phase 7 integration tests — validation infrastructure end-to-end.

Tests that the entire pipeline (historical data → scenario runner →
metrics → monte carlo → comparison) works correctly together.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from stochastic_warfare.validation.historical_data import (
    ComparisonResult,
    HistoricalDataLoader,
    HistoricalEngagement,
    HistoricalMetric,
)
from stochastic_warfare.validation.metrics import (
    EngagementMetrics,
    SimulationResult,
    UnitFinalState,
)
from stochastic_warfare.validation.monte_carlo import (
    ComparisonReport,
    MonteCarloConfig,
    MonteCarloHarness,
    MonteCarloResult,
    RunResult,
)
from stochastic_warfare.validation.scenario_runner import (
    ScenarioRunner,
    ScenarioRunnerConfig,
    build_terrain,
)


# ── Data loading integration ─────────────────────────────────────────


class TestDataLoadingIntegration:
    def test_load_73_easting(self) -> None:
        loader = HistoricalDataLoader()
        eng = loader.load(Path("data/scenarios/73_easting/scenario.yaml"))
        assert "73 Easting" in eng.name
        assert eng.blue_forces.experience_level == 0.8
        assert eng.red_forces.experience_level == 0.3

    def test_load_falklands(self) -> None:
        loader = HistoricalDataLoader()
        eng = loader.load(Path("data/scenarios/falklands_naval/scenario.yaml"))
        assert "Falklands" in eng.name
        assert eng.terrain.terrain_type == "open_ocean"

    def test_load_golan(self) -> None:
        loader = HistoricalDataLoader()
        eng = loader.load(Path("data/scenarios/golan_heights/scenario.yaml"))
        assert "Golan" in eng.name
        assert eng.terrain.base_elevation_m == 900.0

    def test_all_scenarios_load(self) -> None:
        loader = HistoricalDataLoader()
        scenarios = [
            "data/scenarios/73_easting/scenario.yaml",
            "data/scenarios/falklands_naval/scenario.yaml",
            "data/scenarios/golan_heights/scenario.yaml",
        ]
        for path in scenarios:
            eng = loader.load(Path(path))
            assert eng.name != ""
            assert len(eng.documented_outcomes) > 0


# ── Terrain building integration ─────────────────────────────────────


class TestTerrainIntegration:
    def test_flat_desert_from_73_easting(self) -> None:
        loader = HistoricalDataLoader()
        eng = loader.load(Path("data/scenarios/73_easting/scenario.yaml"))
        hm = build_terrain(eng.terrain)
        assert hm.shape[0] > 0
        assert hm.shape[1] > 0

    def test_open_ocean_from_falklands(self) -> None:
        loader = HistoricalDataLoader()
        eng = loader.load(Path("data/scenarios/falklands_naval/scenario.yaml"))
        hm = build_terrain(eng.terrain)
        assert hm.shape[0] > 0

    def test_hilly_from_golan(self) -> None:
        loader = HistoricalDataLoader()
        eng = loader.load(Path("data/scenarios/golan_heights/scenario.yaml"))
        import numpy as np

        rng = np.random.Generator(np.random.PCG64(42))
        hm = build_terrain(eng.terrain, rng)
        assert hm.shape[0] > 0


# ── Scenario runner integration ──────────────────────────────────────


class TestScenarioRunnerIntegration:
    def test_73_easting_runs(self) -> None:
        loader = HistoricalDataLoader()
        eng = loader.load(Path("data/scenarios/73_easting/scenario.yaml"))
        config = ScenarioRunnerConfig(master_seed=42, max_ticks=100, data_dir="data")
        runner = ScenarioRunner(config)
        result = runner.run(eng)
        assert result.ticks_executed > 0
        assert len(result.units_final) > 0

    def test_falklands_runs(self) -> None:
        loader = HistoricalDataLoader()
        eng = loader.load(Path("data/scenarios/falklands_naval/scenario.yaml"))
        config = ScenarioRunnerConfig(master_seed=42, max_ticks=100, data_dir="data")
        runner = ScenarioRunner(config)
        result = runner.run(eng)
        assert result.ticks_executed > 0

    def test_golan_runs(self) -> None:
        loader = HistoricalDataLoader()
        eng = loader.load(Path("data/scenarios/golan_heights/scenario.yaml"))
        config = ScenarioRunnerConfig(master_seed=42, max_ticks=100, data_dir="data")
        runner = ScenarioRunner(config)
        result = runner.run(eng)
        assert result.ticks_executed > 0


# ── Metrics integration ──────────────────────────────────────────────


class TestMetricsIntegration:
    def test_extract_from_scenario(self) -> None:
        loader = HistoricalDataLoader()
        eng = loader.load(Path("data/scenarios/73_easting/scenario.yaml"))
        config = ScenarioRunnerConfig(master_seed=42, max_ticks=100, data_dir="data")
        runner = ScenarioRunner(config)
        result = runner.run(eng)
        metrics = EngagementMetrics.extract_all(result)

        required_keys = [
            "exchange_ratio",
            "duration_s",
            "blue_personnel_casualties",
            "red_personnel_casualties",
            "blue_units_destroyed",
            "red_units_destroyed",
        ]
        for key in required_keys:
            assert key in metrics, f"Missing metric: {key}"


# ── Monte Carlo integration ──────────────────────────────────────────


class TestMonteCarloIntegration:
    def test_mc_3_runs_73_easting(self) -> None:
        loader = HistoricalDataLoader()
        eng = loader.load(Path("data/scenarios/73_easting/scenario.yaml"))
        config = ScenarioRunnerConfig(master_seed=42, max_ticks=100, data_dir="data")
        runner = ScenarioRunner(config)
        mc_config = MonteCarloConfig(num_iterations=3, base_seed=42)
        harness = MonteCarloHarness(runner, mc_config)
        mc_result = harness.run(eng)

        assert mc_result.num_runs == 3
        assert mc_result.mean("duration_s") > 0

    def test_comparison_report(self) -> None:
        loader = HistoricalDataLoader()
        eng = loader.load(Path("data/scenarios/73_easting/scenario.yaml"))
        config = ScenarioRunnerConfig(master_seed=42, max_ticks=100, data_dir="data")
        runner = ScenarioRunner(config)
        mc_config = MonteCarloConfig(num_iterations=3, base_seed=42)
        harness = MonteCarloHarness(runner, mc_config)
        mc_result = harness.run(eng)

        report = mc_result.compare_to_historical(eng.documented_outcomes)
        assert len(report.metric_results) == len(eng.documented_outcomes)
        summary = report.summary()
        assert "Comparison Report" in summary


# ── Calibration overrides integration ────────────────────────────────


class TestCalibrationIntegration:
    def test_overrides_applied(self) -> None:
        loader = HistoricalDataLoader()
        eng = loader.load(Path("data/scenarios/73_easting/scenario.yaml"))
        assert eng.calibration_overrides.get("hit_probability_modifier") == 1.0

    def test_weapon_assignments_present(self) -> None:
        loader = HistoricalDataLoader()
        eng = loader.load(Path("data/scenarios/73_easting/scenario.yaml"))
        assignments = eng.calibration_overrides.get("weapon_assignments", {})
        assert "M256 120mm Smoothbore" in assignments


# ── Deterministic replay integration ─────────────────────────────────


class TestDeterministicReplayIntegration:
    def test_replay_across_all_scenarios(self) -> None:
        loader = HistoricalDataLoader()
        scenarios = [
            "data/scenarios/73_easting/scenario.yaml",
            "data/scenarios/falklands_naval/scenario.yaml",
            "data/scenarios/golan_heights/scenario.yaml",
        ]
        config = ScenarioRunnerConfig(master_seed=42, max_ticks=50, data_dir="data")
        runner = ScenarioRunner(config)

        for path in scenarios:
            eng = loader.load(Path(path))
            r1 = runner.run(eng, seed=42)
            r2 = runner.run(eng, seed=42)
            m1 = EngagementMetrics.extract_all(r1)
            m2 = EngagementMetrics.extract_all(r2)
            for key in m1:
                assert m1[key] == m2[key], (
                    f"Non-deterministic replay in {path}: "
                    f"{key}: {m1[key]} != {m2[key]}"
                )
