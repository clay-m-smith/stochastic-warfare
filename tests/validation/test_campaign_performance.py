"""Measurement-only campaign profiler coverage.

These slow tests prove that profiling returns finite raw measurements. They do
not compare an unpaired run to an absolute or stale performance threshold.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from stochastic_warfare.simulation.engine import EngineConfig
from stochastic_warfare.validation.campaign_data import CampaignDataLoader
from stochastic_warfare.validation.campaign_runner import (
    CampaignRunner,
    CampaignRunnerConfig,
)
from stochastic_warfare.validation.performance import PerformanceProfiler


DATA_DIR = Path(__file__).resolve().parents[2] / "data"


@pytest.mark.slow
@pytest.mark.parametrize(
    "scenario_name",
    ("golan_campaign", "falklands_campaign"),
)
def test_campaign_profile_is_a_valid_measurement_only_result(
    scenario_name: str,
) -> None:
    scenario_path = DATA_DIR / "scenarios" / scenario_name / "scenario.yaml"
    if not scenario_path.is_file():
        pytest.fail(f"required campaign scenario is missing: {scenario_path}")

    campaign = CampaignDataLoader().load(scenario_path)
    runner = CampaignRunner(CampaignRunnerConfig(
        data_dir=str(DATA_DIR),
        engine_config=EngineConfig(max_ticks=200),
    ))
    result = PerformanceProfiler(runner).profile_campaign(
        campaign,
        seed=42,
    )

    assert math.isfinite(result.wall_clock_s)
    assert result.wall_clock_s > 0.0
    assert math.isfinite(result.realtime_ratio)
    assert result.realtime_ratio > 0.0
    assert result.ticks_executed > 0
    assert math.isfinite(result.peak_memory_mb)
    assert result.peak_memory_mb >= 0.0
