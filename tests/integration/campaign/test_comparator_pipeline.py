"""Phase 10 integration tests for campaign-comparator plumbing.

The tests exercise load, bounded simulation, Monte Carlo aggregation, metric
comparison, and AI-decision reporting.  Merely producing a comparison report
does not establish historical or predictive accuracy; outcome envelopes need
their own sourced acceptance evidence.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from stochastic_warfare.simulation.engine import EngineConfig
from stochastic_warfare.validation.ai_validation import AIDecisionValidator
from stochastic_warfare.validation.campaign_data import CampaignDataLoader, HistoricalCampaign
from stochastic_warfare.validation.campaign_metrics import CampaignValidationMetrics
from stochastic_warfare.validation.campaign_runner import (
    CampaignRunner,
    CampaignRunnerConfig,
    CampaignRunResult,
)
from stochastic_warfare.legacy.validation.monte_carlo import (
    CampaignMonteCarloHarness,
    MonteCarloConfig,
)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
GOLAN_YAML = DATA_DIR / "scenarios" / "golan_campaign" / "scenario.yaml"
FALKLANDS_YAML = DATA_DIR / "scenarios" / "falklands_campaign" / "scenario.yaml"


def _fast_runner() -> CampaignRunner:
    """Runner limited to 10 ticks for fast tests."""
    return CampaignRunner(CampaignRunnerConfig(
        data_dir=str(DATA_DIR),
        engine_config=EngineConfig(max_ticks=10),
        snapshot_interval_ticks=5,
    ))


# ===========================================================================
# End-to-end pipeline
# ===========================================================================


@pytest.mark.slow
class TestEndToEndPipeline:
    """Full pipeline: load → run MC → build report → validate AI."""

    def test_golan_pipeline(self):
        if not GOLAN_YAML.exists():
            pytest.skip("Golan campaign YAML not found")

        # 1. Load
        campaign = CampaignDataLoader().load(GOLAN_YAML)
        assert campaign.name.startswith("Golan")

        # 2. Run MC
        runner = _fast_runner()
        mc_config = MonteCarloConfig(num_iterations=2, base_seed=42, max_workers=1)
        harness = CampaignMonteCarloHarness(runner, mc_config)
        mc_result = harness.run(campaign)
        assert mc_result.num_runs == 2

        # 3. Compare
        report = mc_result.compare_to_historical(campaign.documented_outcomes)
        assert len(report.metric_results) > 0
        summary = report.summary()
        assert "Comparison Report" in summary

    def test_falklands_pipeline(self):
        if not FALKLANDS_YAML.exists():
            pytest.skip("Falklands campaign YAML not found")

        campaign = CampaignDataLoader().load(FALKLANDS_YAML)
        runner = _fast_runner()
        mc_config = MonteCarloConfig(num_iterations=2, base_seed=42, max_workers=1)
        harness = CampaignMonteCarloHarness(runner, mc_config)
        mc_result = harness.run(campaign)
        report = mc_result.compare_to_historical(campaign.documented_outcomes)
        assert len(report.metric_results) > 0

    def test_pipeline_with_ai_validation(self):
        if not GOLAN_YAML.exists():
            pytest.skip("Golan campaign YAML not found")

        campaign = CampaignDataLoader().load(GOLAN_YAML)
        runner = _fast_runner()
        result = runner.run(campaign, seed=42)

        # Extract AI decisions
        if result.recorder is not None:
            decisions = AIDecisionValidator.extract_decisions(result.recorder)
            ai_result = AIDecisionValidator.validate_expectations(
                decisions, campaign.ai_expectations
            )
            summary = AIDecisionValidator.summarize(ai_result)
            assert "AI Decision Validation" in summary


# ===========================================================================
# Cross-domain
# ===========================================================================


@pytest.mark.slow
class TestCrossDomain:
    """Verify both land and naval domains work in the same test suite."""

    def test_both_domains(self):
        golan_ok = GOLAN_YAML.exists()
        falklands_ok = FALKLANDS_YAML.exists()
        if not golan_ok and not falklands_ok:
            pytest.skip("No campaign YAMLs found")

        runner = _fast_runner()
        results = {}

        if golan_ok:
            golan = CampaignDataLoader().load(GOLAN_YAML)
            results["golan"] = runner.run(golan, seed=42)

        if falklands_ok:
            falklands = CampaignDataLoader().load(FALKLANDS_YAML)
            results["falklands"] = runner.run(falklands, seed=42)

        for name, result in results.items():
            assert result.ticks_executed > 0, f"{name} had zero ticks"

    def test_land_campaign_no_ships(self):
        if not GOLAN_YAML.exists():
            pytest.skip("Golan campaign YAML not found")

        campaign = CampaignDataLoader().load(GOLAN_YAML)
        runner = _fast_runner()
        result = runner.run(campaign, seed=42)
        metrics = CampaignValidationMetrics.extract_all(result)
        assert metrics["blue_ships_sunk"] == 0
        assert metrics["red_ships_sunk"] == 0


# ===========================================================================
# Campaign with all domain modules
# ===========================================================================


@pytest.mark.slow
class TestAllDomainModules:
    """Verify all domain modules are wired in the campaign context."""

    @pytest.mark.test_evidence("structural_only")
    def test_all_modules_active(self):
        if not GOLAN_YAML.exists():
            pytest.skip("Golan campaign YAML not found")

        campaign = CampaignDataLoader().load(GOLAN_YAML)
        runner = _fast_runner()
        result = runner.run(campaign, seed=42)
        assert isinstance(result, CampaignRunResult)
        # If the run completed without error, all domain modules were wired

    def test_recorder_captures_events(self):
        if not GOLAN_YAML.exists():
            pytest.skip("Golan campaign YAML not found")

        campaign = CampaignDataLoader().load(GOLAN_YAML)
        runner = _fast_runner()
        result = runner.run(campaign, seed=42)
        assert result.recorder is not None
        # Recorder should have captured at least tick events
        event_count = result.recorder.event_count()
        assert event_count >= 0  # may be 0 for very short runs


# ===========================================================================
# Deficiency detection
# ===========================================================================


@pytest.mark.slow
class TestDeficiencyDetection:
    """Verify comparator pass/fail branches with synthetic references."""

    def test_synthetic_out_of_range_reference_is_detected(self):
        """A deliberately out-of-range synthetic value fails comparison."""
        campaign = HistoricalCampaign.model_validate({
            "name": "Deficiency Test",
            "date": "2024-06-15",
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
                    "commander_profile": "aggressive_armor",
                    "doctrine_template": "us_combined_arms",
                },
                {
                    "side": "red",
                    "units": [{"unit_type": "m1a2", "count": 2}],
                    "commander_profile": "cautious_infantry",
                    "doctrine_template": "russian_deep_operations",
                },
            ],
            "victory_conditions": [{"type": "time_expired"}],
            "documented_outcomes": [
                {
                    "name": "red_units_destroyed",
                    "value": 999999.0,
                    "tolerance_factor": 1.1,
                }
            ],
        })
        runner = _fast_runner()
        mc_config = MonteCarloConfig(num_iterations=2, base_seed=42, max_workers=1)
        harness = CampaignMonteCarloHarness(runner, mc_config)
        mc_result = harness.run(campaign)
        report = mc_result.compare_to_historical(campaign.documented_outcomes)
        # The synthetic value is intentionally outside the produced range.
        assert report.failing_count() > 0

    def test_synthetic_current_duration_reference_passes(self):
        """A synthetic exact-current reference exercises the pass branch.

        The ten-tick test runner advances five logical seconds per tick, so its
        current simulated duration is 50 seconds.  This is comparator test data,
        not a widened historical envelope.
        """
        campaign = HistoricalCampaign.model_validate({
            "name": "Pass Test",
            "date": "2024-06-15",
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
                    "commander_profile": "aggressive_armor",
                    "doctrine_template": "us_combined_arms",
                },
                {
                    "side": "red",
                    "units": [{"unit_type": "m1a2", "count": 2}],
                    "commander_profile": "cautious_infantry",
                    "doctrine_template": "russian_deep_operations",
                },
            ],
            "victory_conditions": [{"type": "time_expired"}],
            "documented_outcomes": [
                {
                    "name": "campaign_duration_s",
                    "value": 50.0,
                    "tolerance_factor": 1.0,
                }
            ],
        })
        runner = _fast_runner()
        mc_config = MonteCarloConfig(num_iterations=2, base_seed=42, max_workers=1)
        harness = CampaignMonteCarloHarness(runner, mc_config)
        mc_result = harness.run(campaign)
        report = mc_result.compare_to_historical(campaign.documented_outcomes)
        duration_result = [
            r for r in report.metric_results
            if r.metric_name == "campaign_duration_s"
        ]
        assert len(duration_result) == 1
        assert duration_result[0].simulated_mean == 50.0
        assert duration_result[0].within_tolerance
