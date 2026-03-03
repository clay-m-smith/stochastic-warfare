"""Tests for validation.monte_carlo — CampaignMonteCarloHarness extension."""

from __future__ import annotations

from pathlib import Path

import pytest

from stochastic_warfare.simulation.engine import EngineConfig
from stochastic_warfare.validation.campaign_data import CampaignDataLoader, HistoricalCampaign
from stochastic_warfare.validation.campaign_runner import CampaignRunner, CampaignRunnerConfig
from stochastic_warfare.validation.monte_carlo import (
    CampaignMonteCarloHarness,
    ComparisonReport,
    MonteCarloConfig,
    MonteCarloResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _minimal_campaign() -> HistoricalCampaign:
    """Minimal campaign for fast MC tests."""
    return HistoricalCampaign.model_validate({
        "name": "MC Test Campaign",
        "date": "2024-06-15T12:00:00Z",
        "duration_hours": 24.0,
        "terrain": {
            "width_m": 5000,
            "height_m": 5000,
            "terrain_type": "flat_desert",
        },
        "sides": [
            {
                "side": "blue",
                "units": [{"unit_type": "m1a2", "count": 2}],
                "experience_level": 0.8,
                "commander_profile": "aggressive_armor",
                "doctrine_template": "us_combined_arms",
            },
            {
                "side": "red",
                "units": [{"unit_type": "m1a2", "count": 3}],
                "experience_level": 0.5,
                "commander_profile": "cautious_infantry",
                "doctrine_template": "russian_deep_operations",
            },
        ],
        "victory_conditions": [
            {"type": "force_destroyed"},
            {"type": "time_expired"},
        ],
        "documented_outcomes": [
            {"name": "red_units_destroyed", "value": 2.0, "tolerance_factor": 3.0},
            {"name": "campaign_duration_s", "value": 86400.0, "tolerance_factor": 2.0},
        ],
        "calibration_overrides": {
            "hit_probability_modifier": 1.0,
            "target_size_modifier": 1.0,
        },
    })


def _make_runner() -> CampaignRunner:
    """Create a campaign runner with fast settings."""
    cfg = CampaignRunnerConfig(
        data_dir=str(DATA_DIR),
        engine_config=EngineConfig(max_ticks=5),
    )
    return CampaignRunner(cfg)


# ===========================================================================
# Serial MC tests
# ===========================================================================


@pytest.mark.slow
class TestCampaignMCSerial:
    def test_serial_3_runs(self):
        runner = _make_runner()
        mc_config = MonteCarloConfig(num_iterations=3, base_seed=42, max_workers=1)
        harness = CampaignMonteCarloHarness(runner, mc_config)
        campaign = _minimal_campaign()

        result = harness.run(campaign)
        assert isinstance(result, MonteCarloResult)
        assert result.num_runs == 3

    def test_all_runs_complete(self):
        runner = _make_runner()
        mc_config = MonteCarloConfig(num_iterations=3, base_seed=42, max_workers=1)
        harness = CampaignMonteCarloHarness(runner, mc_config)
        campaign = _minimal_campaign()

        result = harness.run(campaign)
        for run in result.runs:
            assert run.seed >= 42
            assert "red_units_destroyed" in run.metrics

    def test_stats_computed(self):
        runner = _make_runner()
        mc_config = MonteCarloConfig(num_iterations=3, base_seed=42, max_workers=1)
        harness = CampaignMonteCarloHarness(runner, mc_config)
        campaign = _minimal_campaign()

        result = harness.run(campaign)
        mean_dur = result.mean("campaign_duration_s")
        assert mean_dur > 0

    def test_different_seeds_per_run(self):
        runner = _make_runner()
        mc_config = MonteCarloConfig(num_iterations=3, base_seed=100, max_workers=1)
        harness = CampaignMonteCarloHarness(runner, mc_config)
        campaign = _minimal_campaign()

        result = harness.run(campaign)
        seeds = [r.seed for r in result.runs]
        assert seeds == [100, 101, 102]


# ===========================================================================
# Comparison to historical
# ===========================================================================


@pytest.mark.slow
class TestCampaignMCComparison:
    def test_compare_to_documented_outcomes(self):
        runner = _make_runner()
        mc_config = MonteCarloConfig(num_iterations=3, base_seed=42, max_workers=1)
        harness = CampaignMonteCarloHarness(runner, mc_config)
        campaign = _minimal_campaign()

        result = harness.run(campaign)
        report = result.compare_to_historical(campaign.documented_outcomes)
        assert isinstance(report, ComparisonReport)
        assert len(report.metric_results) > 0

    def test_comparison_report_has_summary(self):
        runner = _make_runner()
        mc_config = MonteCarloConfig(num_iterations=3, base_seed=42, max_workers=1)
        harness = CampaignMonteCarloHarness(runner, mc_config)
        campaign = _minimal_campaign()

        result = harness.run(campaign)
        report = result.compare_to_historical(campaign.documented_outcomes)
        summary = report.summary()
        assert "Comparison Report" in summary

    def test_metric_aggregation(self):
        runner = _make_runner()
        mc_config = MonteCarloConfig(num_iterations=3, base_seed=42, max_workers=1)
        harness = CampaignMonteCarloHarness(runner, mc_config)
        campaign = _minimal_campaign()

        result = harness.run(campaign)
        # Should be able to get confidence intervals
        ci = result.confidence_interval("campaign_duration_s")
        assert ci[0] <= ci[1]

    def test_metric_std(self):
        runner = _make_runner()
        mc_config = MonteCarloConfig(num_iterations=3, base_seed=42, max_workers=1)
        harness = CampaignMonteCarloHarness(runner, mc_config)
        campaign = _minimal_campaign()

        result = harness.run(campaign)
        std = result.std("campaign_duration_s")
        # With max_ticks=5 all runs likely have same duration, so std may be 0
        assert std >= 0

    def test_distribution_values(self):
        runner = _make_runner()
        mc_config = MonteCarloConfig(num_iterations=3, base_seed=42, max_workers=1)
        harness = CampaignMonteCarloHarness(runner, mc_config)
        campaign = _minimal_campaign()

        result = harness.run(campaign)
        dist = result.distribution("campaign_duration_s")
        assert len(dist) == 3


# ===========================================================================
# Deterministic serial
# ===========================================================================


@pytest.mark.slow
class TestCampaignMCDeterminism:
    def test_serial_deterministic(self):
        """Same base_seed in serial mode produces identical results."""
        runner = _make_runner()
        mc_config = MonteCarloConfig(num_iterations=2, base_seed=42, max_workers=1)

        harness1 = CampaignMonteCarloHarness(runner, mc_config)
        harness2 = CampaignMonteCarloHarness(runner, mc_config)
        campaign = _minimal_campaign()

        r1 = harness1.run(campaign)
        r2 = harness2.run(campaign)

        for run1, run2 in zip(r1.runs, r2.runs):
            assert run1.seed == run2.seed
            assert run1.terminated_by == run2.terminated_by
            for key in run1.metrics:
                assert run1.metrics[key] == run2.metrics[key], f"Metric {key} differs"
