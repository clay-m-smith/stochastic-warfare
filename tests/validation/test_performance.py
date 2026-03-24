"""Tests for validation.performance — campaign performance profiling."""

from __future__ import annotations

from pathlib import Path

import pytest

from stochastic_warfare.simulation.engine import EngineConfig
from stochastic_warfare.validation.campaign_data import HistoricalCampaign
from stochastic_warfare.validation.campaign_runner import CampaignRunner, CampaignRunnerConfig
from stochastic_warfare.validation.performance import PerformanceProfiler, PerformanceResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _minimal_campaign() -> HistoricalCampaign:
    """Minimal campaign for fast profiling tests."""
    return HistoricalCampaign.model_validate({
        "name": "Perf Test",
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
                "units": [{"unit_type": "m1a2", "count": 2}],
                "experience_level": 0.5,
                "commander_profile": "cautious_infantry",
                "doctrine_template": "russian_deep_operations",
            },
        ],
        "victory_conditions": [
            {"type": "force_destroyed"},
            {"type": "time_expired"},
        ],
        "calibration_overrides": {
            "hit_probability_modifier": 1.0,
            "target_size_modifier": 1.0,
        },
    })


# ===========================================================================
# PerformanceResult tests
# ===========================================================================


class TestPerformanceResult:
    def test_fields(self):
        r = PerformanceResult(
            wall_clock_s=10.0,
            sim_duration_s=3600.0,
            realtime_ratio=360.0,
            ticks_executed=100,
            ticks_per_second=10.0,
            peak_memory_mb=50.0,
            hotspots=[("func", 1.0, 10)],
        )
        assert r.wall_clock_s == 10.0
        assert r.realtime_ratio == 360.0
        assert len(r.hotspots) == 1

    def test_default_hotspots(self):
        r = PerformanceResult(
            wall_clock_s=1, sim_duration_s=100, realtime_ratio=100,
            ticks_executed=10, ticks_per_second=10, peak_memory_mb=1,
        )
        assert r.hotspots == []


# ===========================================================================
# Profiler integration tests
# ===========================================================================


@pytest.mark.slow
class TestPerformanceProfiler:
    @pytest.fixture
    def profiler(self) -> PerformanceProfiler:
        cfg = CampaignRunnerConfig(
            data_dir=str(DATA_DIR),
            engine_config=EngineConfig(max_ticks=5),
        )
        runner = CampaignRunner(cfg)
        return PerformanceProfiler(runner)

    def test_profile_completes(self, profiler: PerformanceProfiler):
        campaign = _minimal_campaign()
        result = profiler.profile_campaign(campaign, seed=42)
        assert isinstance(result, PerformanceResult)
        assert result.wall_clock_s > 0
        assert result.ticks_executed > 0

    def test_realtime_ratio_computed(self, profiler: PerformanceProfiler):
        campaign = _minimal_campaign()
        result = profiler.profile_campaign(campaign, seed=42)
        assert result.realtime_ratio > 0
        assert result.sim_duration_s > 0

    def test_hotspot_extraction(self, profiler: PerformanceProfiler):
        campaign = _minimal_campaign()
        result = profiler.profile_campaign(campaign, seed=42, top_n=5)
        assert len(result.hotspots) > 0
        # Hotspots should be tuples of (name, cumtime, calls)
        for name, cumtime, calls in result.hotspots:
            assert isinstance(name, str)
            assert cumtime >= 0
            assert calls >= 0

    def test_memory_tracking(self, profiler: PerformanceProfiler):
        campaign = _minimal_campaign()
        result = profiler.profile_campaign(campaign, seed=42)
        assert result.peak_memory_mb >= 0

    def test_ticks_per_second(self, profiler: PerformanceProfiler):
        campaign = _minimal_campaign()
        result = profiler.profile_campaign(campaign, seed=42)
        assert result.ticks_per_second > 0


# ===========================================================================
# Report formatting
# ===========================================================================


class TestReport:
    def test_report_format(self):
        result = PerformanceResult(
            wall_clock_s=5.5,
            sim_duration_s=86400.0,
            realtime_ratio=15709.0,
            ticks_executed=500,
            ticks_per_second=90.9,
            peak_memory_mb=45.2,
            hotspots=[
                ("engine.py:100(run)", 3.0, 500),
                ("battle.py:50(execute_tick)", 2.0, 300),
            ],
        )
        report = PerformanceProfiler.report(result)
        assert "Wall-clock" in report
        assert "5.50s" in report
        assert "Realtime ratio" in report
        assert "Peak memory" in report
        assert "Hotspots" in report

    def test_report_empty_hotspots(self):
        result = PerformanceResult(
            wall_clock_s=1, sim_duration_s=100, realtime_ratio=100,
            ticks_executed=10, ticks_per_second=10, peak_memory_mb=1,
        )
        report = PerformanceProfiler.report(result)
        assert "Hotspots" in report

    def test_report_long_function_names(self):
        result = PerformanceResult(
            wall_clock_s=1, sim_duration_s=100, realtime_ratio=100,
            ticks_executed=10, ticks_per_second=10, peak_memory_mb=1,
            hotspots=[("a" * 100, 1.0, 10)],
        )
        report = PerformanceProfiler.report(result)
        # Long names should be truncated
        assert "..." in report
