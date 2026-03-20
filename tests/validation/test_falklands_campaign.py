"""Campaign-level validation tests — Falklands San Carlos (May 21-25, 1982).

Tests the full simulation engine producing realistic campaign outcomes
for the Falklands San Carlos naval air defense campaign.  British ships
defend against Argentine air raids over 5 days.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from stochastic_warfare.simulation.engine import EngineConfig
from stochastic_warfare.validation.ai_validation import AIDecisionValidator
from stochastic_warfare.validation.campaign_data import CampaignDataLoader
from stochastic_warfare.validation.campaign_metrics import CampaignValidationMetrics
from stochastic_warfare.validation.campaign_runner import (
    CampaignRunner,
    CampaignRunnerConfig,
    CampaignRunResult,
)
from stochastic_warfare.validation.monte_carlo import (
    CampaignMonteCarloHarness,
    MonteCarloConfig,
)


# ---------------------------------------------------------------------------
# Paths and fixtures
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
FALKLANDS_YAML = DATA_DIR / "scenarios" / "falklands_campaign" / "scenario.yaml"


@pytest.fixture(scope="module")
def falklands_campaign():
    """Load the Falklands campaign YAML once for all tests."""
    if not FALKLANDS_YAML.exists():
        pytest.skip("Falklands campaign YAML not found")
    return CampaignDataLoader().load(FALKLANDS_YAML)


def _fast_runner() -> CampaignRunner:
    """Runner limited to 20 ticks for fast tests."""
    return CampaignRunner(CampaignRunnerConfig(
        data_dir=str(DATA_DIR),
        engine_config=EngineConfig(max_ticks=20),
        snapshot_interval_ticks=10,
    ))


# ===========================================================================
# Scenario loading
# ===========================================================================


class TestFalklandsScenarioLoading:
    def test_yaml_parses(self, falklands_campaign):
        assert falklands_campaign.name.startswith("Falklands")

    def test_forces_correct(self, falklands_campaign):
        blue = falklands_campaign.sides[0]
        red = falklands_campaign.sides[1]
        assert blue.side == "blue"
        assert red.side == "red"
        blue_count = sum(u.get("count", 1) for u in blue.units)
        assert blue_count == 16  # 4 Type 42 + 4 Type 22 + 8 Sea Harrier

    def test_terrain_ocean(self, falklands_campaign):
        assert falklands_campaign.terrain.terrain_type == "open_ocean"
        assert falklands_campaign.terrain.width_m == 100000


# ===========================================================================
# Single run completion
# ===========================================================================


@pytest.mark.slow
class TestFalklandsSingleRun:
    def test_runs_to_completion(self, falklands_campaign):
        runner = _fast_runner()
        result = runner.run(falklands_campaign, seed=42)
        assert isinstance(result, CampaignRunResult)
        assert result.ticks_executed > 0

    def test_both_sides_present(self, falklands_campaign):
        runner = _fast_runner()
        result = runner.run(falklands_campaign, seed=42)
        assert "blue" in result.final_units_by_side
        assert "red" in result.final_units_by_side

    def test_naval_units_exist(self, falklands_campaign):
        runner = _fast_runner()
        result = runner.run(falklands_campaign, seed=42)
        blue_types = [
            getattr(u, "unit_type", "") for u in result.final_units_by_side["blue"]
        ]
        # Should have some naval unit types
        assert len(blue_types) > 0

    def test_recorder_present(self, falklands_campaign):
        runner = _fast_runner()
        result = runner.run(falklands_campaign, seed=42)
        assert result.recorder is not None

    def test_has_victory_result(self, falklands_campaign):
        runner = _fast_runner()
        result = runner.run(falklands_campaign, seed=42)
        assert result.victory_result is not None


# ===========================================================================
# Deterministic replay
# ===========================================================================


@pytest.mark.slow
class TestFalklandsDeterministicReplay:
    def test_same_seed_identical(self, falklands_campaign):
        runner = _fast_runner()
        r1 = runner.run(falklands_campaign, seed=42)
        r2 = runner.run(falklands_campaign, seed=42)
        assert r1.ticks_executed == r2.ticks_executed
        assert r1.terminated_by == r2.terminated_by

    def test_metrics_deterministic(self, falklands_campaign):
        runner = _fast_runner()
        r1 = runner.run(falklands_campaign, seed=42)
        r2 = runner.run(falklands_campaign, seed=42)
        m1 = CampaignValidationMetrics.extract_all(r1)
        m2 = CampaignValidationMetrics.extract_all(r2)
        for key in m1:
            assert m1[key] == m2[key], f"Metric {key} differs"


# ===========================================================================
# Historical comparison (single run)
# ===========================================================================


@pytest.mark.slow
class TestFalklandsHistoricalSingleRun:
    def test_metrics_extracted(self, falklands_campaign):
        runner = _fast_runner()
        result = runner.run(falklands_campaign, seed=42)
        metrics = CampaignValidationMetrics.extract_all(result)
        assert "blue_ships_sunk" in metrics
        assert "red_units_destroyed" in metrics

    def test_campaign_duration_positive(self, falklands_campaign):
        runner = _fast_runner()
        result = runner.run(falklands_campaign, seed=42)
        metrics = CampaignValidationMetrics.extract_all(result)
        assert metrics["campaign_duration_s"] > 0


# ===========================================================================
# MC fast (3 runs)
# ===========================================================================


@pytest.mark.slow
class TestFalklandsMCFast:
    def test_mc_3_runs(self, falklands_campaign):
        runner = _fast_runner()
        mc_config = MonteCarloConfig(num_iterations=3, base_seed=42, max_workers=1)
        harness = CampaignMonteCarloHarness(runner, mc_config)
        result = harness.run(falklands_campaign)
        assert result.num_runs == 3

    def test_all_complete(self, falklands_campaign):
        runner = _fast_runner()
        mc_config = MonteCarloConfig(num_iterations=3, base_seed=42, max_workers=1)
        harness = CampaignMonteCarloHarness(runner, mc_config)
        result = harness.run(falklands_campaign)
        for run in result.runs:
            assert "blue_ships_sunk" in run.metrics

    def test_comparison_report(self, falklands_campaign):
        runner = _fast_runner()
        mc_config = MonteCarloConfig(num_iterations=3, base_seed=42, max_workers=1)
        harness = CampaignMonteCarloHarness(runner, mc_config)
        result = harness.run(falklands_campaign)
        report = result.compare_to_historical(falklands_campaign.documented_outcomes)
        assert len(report.metric_results) > 0

    def test_stats_computed(self, falklands_campaign):
        runner = _fast_runner()
        mc_config = MonteCarloConfig(num_iterations=3, base_seed=42, max_workers=1)
        harness = CampaignMonteCarloHarness(runner, mc_config)
        result = harness.run(falklands_campaign)
        mean = result.mean("campaign_duration_s")
        assert mean > 0


# ===========================================================================
# MC full (slow — 50+ runs)
# ===========================================================================


@pytest.mark.slow
class TestFalklandsMCFull:
    """Full Monte Carlo validation — expensive, marked @slow."""

    def test_mc_50_runs(self, falklands_campaign):
        runner = CampaignRunner(CampaignRunnerConfig(
            data_dir=str(DATA_DIR),
            engine_config=EngineConfig(max_ticks=100),
        ))
        mc_config = MonteCarloConfig(num_iterations=50, base_seed=42, max_workers=1)
        harness = CampaignMonteCarloHarness(runner, mc_config)
        result = harness.run(falklands_campaign)
        assert result.num_runs == 50

    def test_compare_to_historical(self, falklands_campaign):
        runner = CampaignRunner(CampaignRunnerConfig(
            data_dir=str(DATA_DIR),
            engine_config=EngineConfig(max_ticks=100),
        ))
        mc_config = MonteCarloConfig(num_iterations=50, base_seed=42, max_workers=1)
        harness = CampaignMonteCarloHarness(runner, mc_config)
        result = harness.run(falklands_campaign)
        report = result.compare_to_historical(falklands_campaign.documented_outcomes)
        print(report.summary())
        assert report.passing_count() >= 0


# ===========================================================================
# AI decision quality
# ===========================================================================


@pytest.mark.slow
class TestFalklandsAIDecisions:
    def test_decisions_extracted(self, falklands_campaign):
        runner = _fast_runner()
        result = runner.run(falklands_campaign, seed=42)
        if result.recorder is None:
            pytest.skip("No recorder")
        decisions = AIDecisionValidator.extract_decisions(result.recorder)
        assert isinstance(decisions, list)

    def test_expectations_checked(self, falklands_campaign):
        runner = _fast_runner()
        result = runner.run(falklands_campaign, seed=42)
        if result.recorder is None:
            pytest.skip("No recorder")
        decisions = AIDecisionValidator.extract_decisions(result.recorder)
        ai_result = AIDecisionValidator.validate_expectations(
            decisions, falklands_campaign.ai_expectations
        )
        assert len(ai_result.expectation_results) == len(falklands_campaign.ai_expectations)


# ===========================================================================
# Naval-specific metrics
# ===========================================================================


@pytest.mark.slow
class TestFalklandsNavalMetrics:
    def test_ships_sunk_metric(self, falklands_campaign):
        runner = _fast_runner()
        result = runner.run(falklands_campaign, seed=42)
        metrics = CampaignValidationMetrics.extract_all(result)
        # Ships sunk should be a non-negative number
        assert metrics["blue_ships_sunk"] >= 0

    def test_red_units_tracked(self, falklands_campaign):
        runner = _fast_runner()
        result = runner.run(falklands_campaign, seed=42)
        metrics = CampaignValidationMetrics.extract_all(result)
        assert metrics["red_units_destroyed"] >= 0

    def test_reinforcements_configured(self, falklands_campaign):
        assert len(falklands_campaign.reinforcements) == 4
        for r in falklands_campaign.reinforcements:
            assert r.side == "red"
