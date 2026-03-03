"""Performance tests for campaign validation — all @pytest.mark.slow.

Profiles full campaign runs to verify wall-clock time and realtime ratio
targets.  These tests are expensive and excluded from the default test run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from stochastic_warfare.simulation.engine import EngineConfig
from stochastic_warfare.validation.campaign_data import CampaignDataLoader
from stochastic_warfare.validation.campaign_runner import CampaignRunner, CampaignRunnerConfig
from stochastic_warfare.validation.performance import PerformanceProfiler, PerformanceResult


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
GOLAN_YAML = DATA_DIR / "scenarios" / "golan_campaign" / "scenario.yaml"
FALKLANDS_YAML = DATA_DIR / "scenarios" / "falklands_campaign" / "scenario.yaml"


# ===========================================================================
# Golan full profile
# ===========================================================================


@pytest.mark.slow
class TestGolanPerformance:
    def test_golan_profile(self):
        if not GOLAN_YAML.exists():
            pytest.skip("Golan campaign YAML not found")

        campaign = CampaignDataLoader().load(GOLAN_YAML)
        runner = CampaignRunner(CampaignRunnerConfig(
            data_dir=str(DATA_DIR),
            engine_config=EngineConfig(max_ticks=200),
        ))
        profiler = PerformanceProfiler(runner)
        result = profiler.profile_campaign(campaign, seed=42)

        print(PerformanceProfiler.report(result))
        assert result.wall_clock_s > 0
        assert result.ticks_executed > 0

    def test_golan_realtime_ratio(self):
        if not GOLAN_YAML.exists():
            pytest.skip("Golan campaign YAML not found")

        campaign = CampaignDataLoader().load(GOLAN_YAML)
        runner = CampaignRunner(CampaignRunnerConfig(
            data_dir=str(DATA_DIR),
            engine_config=EngineConfig(max_ticks=200),
        ))
        profiler = PerformanceProfiler(runner)
        result = profiler.profile_campaign(campaign, seed=42)
        # Realtime ratio should be positive
        assert result.realtime_ratio > 0

    def test_golan_memory(self):
        if not GOLAN_YAML.exists():
            pytest.skip("Golan campaign YAML not found")

        campaign = CampaignDataLoader().load(GOLAN_YAML)
        runner = CampaignRunner(CampaignRunnerConfig(
            data_dir=str(DATA_DIR),
            engine_config=EngineConfig(max_ticks=200),
        ))
        profiler = PerformanceProfiler(runner)
        result = profiler.profile_campaign(campaign, seed=42)
        assert result.peak_memory_mb >= 0


# ===========================================================================
# Falklands full profile
# ===========================================================================


@pytest.mark.slow
class TestFalklandsPerformance:
    def test_falklands_profile(self):
        if not FALKLANDS_YAML.exists():
            pytest.skip("Falklands campaign YAML not found")

        campaign = CampaignDataLoader().load(FALKLANDS_YAML)
        runner = CampaignRunner(CampaignRunnerConfig(
            data_dir=str(DATA_DIR),
            engine_config=EngineConfig(max_ticks=200),
        ))
        profiler = PerformanceProfiler(runner)
        result = profiler.profile_campaign(campaign, seed=42)

        print(PerformanceProfiler.report(result))
        assert result.wall_clock_s > 0

    def test_falklands_realtime_ratio(self):
        if not FALKLANDS_YAML.exists():
            pytest.skip("Falklands campaign YAML not found")

        campaign = CampaignDataLoader().load(FALKLANDS_YAML)
        runner = CampaignRunner(CampaignRunnerConfig(
            data_dir=str(DATA_DIR),
            engine_config=EngineConfig(max_ticks=200),
        ))
        profiler = PerformanceProfiler(runner)
        result = profiler.profile_campaign(campaign, seed=42)
        assert result.realtime_ratio > 0

    def test_falklands_memory(self):
        if not FALKLANDS_YAML.exists():
            pytest.skip("Falklands campaign YAML not found")

        campaign = CampaignDataLoader().load(FALKLANDS_YAML)
        runner = CampaignRunner(CampaignRunnerConfig(
            data_dir=str(DATA_DIR),
            engine_config=EngineConfig(max_ticks=200),
        ))
        profiler = PerformanceProfiler(runner)
        result = profiler.profile_campaign(campaign, seed=42)
        assert result.peak_memory_mb >= 0


# ===========================================================================
# Wall-clock assertions
# ===========================================================================


@pytest.mark.slow
class TestPerformanceAssertions:
    def test_golan_under_120s(self):
        """Golan 200-tick campaign should complete in under 120s."""
        if not GOLAN_YAML.exists():
            pytest.skip("Golan campaign YAML not found")

        campaign = CampaignDataLoader().load(GOLAN_YAML)
        runner = CampaignRunner(CampaignRunnerConfig(
            data_dir=str(DATA_DIR),
            engine_config=EngineConfig(max_ticks=200),
        ))
        profiler = PerformanceProfiler(runner)
        result = profiler.profile_campaign(campaign, seed=42)
        assert result.wall_clock_s < 120, (
            f"Golan campaign took {result.wall_clock_s:.1f}s (target < 120s)"
        )

    def test_falklands_under_60s(self):
        """Falklands 200-tick campaign should complete in under 60s."""
        if not FALKLANDS_YAML.exists():
            pytest.skip("Falklands campaign YAML not found")

        campaign = CampaignDataLoader().load(FALKLANDS_YAML)
        runner = CampaignRunner(CampaignRunnerConfig(
            data_dir=str(DATA_DIR),
            engine_config=EngineConfig(max_ticks=200),
        ))
        profiler = PerformanceProfiler(runner)
        result = profiler.profile_campaign(campaign, seed=42)
        assert result.wall_clock_s < 60, (
            f"Falklands campaign took {result.wall_clock_s:.1f}s (target < 60s)"
        )
