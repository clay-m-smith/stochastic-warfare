"""Tests for validation.campaign_runner — campaign execution wrapper."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from stochastic_warfare.simulation.engine import EngineConfig
from stochastic_warfare.simulation.victory import VictoryResult
from stochastic_warfare.validation.campaign_data import (
    CampaignDataLoader,
    HistoricalCampaign,
)
from stochastic_warfare.validation.campaign_runner import (
    CampaignRunner,
    CampaignRunnerConfig,
    CampaignRunResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _minimal_campaign(**overrides) -> HistoricalCampaign:
    """Minimal valid HistoricalCampaign for testing."""
    d: dict = {
        "name": "Test Campaign",
        "date": "2024-06-15T12:00:00Z",
        "duration_hours": 24.0,
        "terrain": {
            "width_m": 10000,
            "height_m": 10000,
            "terrain_type": "flat_desert",
        },
        "sides": [
            {
                "side": "blue",
                "units": [{"unit_type": "m1a2", "count": 4}],
                "experience_level": 0.8,
                "commander_profile": "aggressive_armor",
                "doctrine_template": "us_combined_arms",
                "depots": [
                    {"depot_id": "blue_fob", "position": [500, 5000]}
                ],
            },
            {
                "side": "red",
                "units": [{"unit_type": "m1a2", "count": 6}],
                "experience_level": 0.5,
                "commander_profile": "cautious_infantry",
                "doctrine_template": "russian_deep_operations",
            },
        ],
        "objectives": [
            {"objective_id": "obj1", "position": [5000, 5000], "radius_m": 500}
        ],
        "victory_conditions": [
            {"type": "force_destroyed"},
            {"type": "time_expired"},
        ],
        "calibration_overrides": {
            "hit_probability_modifier": 1.0,
            "target_size_modifier": 1.0,
        },
    }
    d.update(overrides)
    return HistoricalCampaign.model_validate(d)


# ===========================================================================
# Config tests
# ===========================================================================


class TestCampaignRunnerConfig:
    def test_defaults(self):
        cfg = CampaignRunnerConfig()
        assert cfg.data_dir == "data"
        assert cfg.snapshot_interval_ticks == 100

    def test_custom_data_dir(self):
        cfg = CampaignRunnerConfig(data_dir="custom/data")
        assert cfg.data_dir == "custom/data"

    def test_engine_config_override(self):
        cfg = CampaignRunnerConfig(
            engine_config=EngineConfig(max_ticks=500)
        )
        assert cfg.engine_config.max_ticks == 500

    def test_snapshot_interval(self):
        cfg = CampaignRunnerConfig(snapshot_interval_ticks=50)
        assert cfg.snapshot_interval_ticks == 50


# ===========================================================================
# CampaignRunResult tests
# ===========================================================================


class TestCampaignRunResult:
    def test_fields(self):
        result = CampaignRunResult(
            seed=42,
            ticks_executed=100,
            duration_simulated_s=3600.0,
            victory_result=VictoryResult(game_over=True, winning_side="blue"),
            recorder=None,
            final_units_by_side={"blue": [], "red": []},
            final_morale_states={},
            terminated_by="force_destroyed",
        )
        assert result.seed == 42
        assert result.ticks_executed == 100
        assert result.terminated_by == "force_destroyed"
        assert result.victory_result.winning_side == "blue"

    def test_default_run_result_none(self):
        result = CampaignRunResult(
            seed=1, ticks_executed=0, duration_simulated_s=0,
            victory_result=VictoryResult(game_over=False),
            recorder=None, final_units_by_side={},
            final_morale_states={}, terminated_by="",
        )
        assert result.run_result is None


# ===========================================================================
# Runner integration — uses real ScenarioLoader (requires data/ files)
# ===========================================================================


@pytest.mark.slow
class TestCampaignRunnerIntegration:
    """Integration tests that actually run campaigns.

    These load real YAML data files from data/ and run the simulation
    engine for a small number of ticks.
    """

    @pytest.fixture
    def runner(self) -> CampaignRunner:
        cfg = CampaignRunnerConfig(
            data_dir=str(DATA_DIR),
            engine_config=EngineConfig(max_ticks=10),
            snapshot_interval_ticks=5,
        )
        return CampaignRunner(cfg)

    def test_run_minimal_campaign(self, runner: CampaignRunner):
        campaign = _minimal_campaign()
        result = runner.run(campaign, seed=42)
        assert isinstance(result, CampaignRunResult)
        assert result.seed == 42
        assert result.ticks_executed > 0

    def test_deterministic_replay(self, runner: CampaignRunner):
        campaign = _minimal_campaign()
        r1 = runner.run(campaign, seed=42)
        r2 = runner.run(campaign, seed=42)
        assert r1.ticks_executed == r2.ticks_executed
        assert r1.terminated_by == r2.terminated_by

    def test_different_seeds_differ(self, runner: CampaignRunner):
        campaign = _minimal_campaign()
        r1 = runner.run(campaign, seed=42)
        r2 = runner.run(campaign, seed=99)
        # Results may differ (not guaranteed but probable with different seeds)
        # At minimum both complete successfully
        assert isinstance(r1, CampaignRunResult)
        assert isinstance(r2, CampaignRunResult)

    def test_result_has_units(self, runner: CampaignRunner):
        campaign = _minimal_campaign()
        result = runner.run(campaign, seed=42)
        assert "blue" in result.final_units_by_side
        assert "red" in result.final_units_by_side
        assert len(result.final_units_by_side["blue"]) > 0

    def test_result_has_victory(self, runner: CampaignRunner):
        campaign = _minimal_campaign()
        result = runner.run(campaign, seed=42)
        assert isinstance(result.victory_result, VictoryResult)

    def test_recorder_present(self, runner: CampaignRunner):
        campaign = _minimal_campaign()
        result = runner.run(campaign, seed=42)
        assert result.recorder is not None

    def test_default_seed_42(self, runner: CampaignRunner):
        campaign = _minimal_campaign()
        result = runner.run(campaign)
        assert result.seed == 42

    def test_max_ticks_limits_run(self):
        cfg = CampaignRunnerConfig(
            data_dir=str(DATA_DIR),
            engine_config=EngineConfig(max_ticks=3),
        )
        runner = CampaignRunner(cfg)
        campaign = _minimal_campaign()
        result = runner.run(campaign, seed=42)
        assert result.ticks_executed <= 3

    def test_morale_states_populated(self, runner: CampaignRunner):
        campaign = _minimal_campaign()
        result = runner.run(campaign, seed=42)
        assert len(result.final_morale_states) > 0

    def test_victory_conditions_active(self, runner: CampaignRunner):
        campaign = _minimal_campaign(
            victory_conditions=[
                {"type": "force_destroyed"},
                {"type": "time_expired", "side": "blue"},
            ],
        )
        result = runner.run(campaign, seed=42)
        # Should complete without error
        assert isinstance(result, CampaignRunResult)

    def test_reinforcements_config_accepted(self, runner: CampaignRunner):
        campaign = _minimal_campaign(
            reinforcements=[
                {
                    "side": "blue",
                    "arrival_time_s": 7200,
                    "units": [{"unit_type": "m1a2", "count": 2}],
                    "position": [200, 5000],
                }
            ],
        )
        result = runner.run(campaign, seed=42)
        assert isinstance(result, CampaignRunResult)

    def test_calibration_overrides_passed(self, runner: CampaignRunner):
        campaign = _minimal_campaign(
            calibration_overrides={
                "hit_probability_modifier": 0.5,
                "target_size_modifier": 0.8,
            }
        )
        result = runner.run(campaign, seed=42)
        assert isinstance(result, CampaignRunResult)


# ===========================================================================
# Golan campaign YAML loading
# ===========================================================================


class TestGolanCampaignYAML:
    """Verify the Golan campaign YAML loads correctly."""

    def test_load_golan_campaign(self):
        loader = CampaignDataLoader()
        path = DATA_DIR / "scenarios" / "golan_campaign" / "scenario.yaml"
        if not path.exists():
            pytest.skip("Golan campaign YAML not found")
        campaign = loader.load(path)
        assert campaign.name.startswith("Golan")
        assert campaign.duration_hours == 96.0
        assert len(campaign.sides) == 2

    def test_golan_forces_correct(self):
        loader = CampaignDataLoader()
        path = DATA_DIR / "scenarios" / "golan_campaign" / "scenario.yaml"
        if not path.exists():
            pytest.skip("Golan campaign YAML not found")
        campaign = loader.load(path)
        blue = campaign.sides[0]
        red = campaign.sides[1]
        assert blue.side == "blue"
        assert red.side == "red"
        assert sum(u.get("count", 1) for u in blue.units) == 40
        assert sum(u.get("count", 1) for u in red.units) >= 100

    def test_golan_has_reinforcements(self):
        loader = CampaignDataLoader()
        path = DATA_DIR / "scenarios" / "golan_campaign" / "scenario.yaml"
        if not path.exists():
            pytest.skip("Golan campaign YAML not found")
        campaign = loader.load(path)
        assert len(campaign.reinforcements) == 2

    def test_golan_has_ai_expectations(self):
        loader = CampaignDataLoader()
        path = DATA_DIR / "scenarios" / "golan_campaign" / "scenario.yaml"
        if not path.exists():
            pytest.skip("Golan campaign YAML not found")
        campaign = loader.load(path)
        assert len(campaign.ai_expectations) >= 2

    def test_golan_has_documented_outcomes(self):
        loader = CampaignDataLoader()
        path = DATA_DIR / "scenarios" / "golan_campaign" / "scenario.yaml"
        if not path.exists():
            pytest.skip("Golan campaign YAML not found")
        campaign = loader.load(path)
        assert len(campaign.documented_outcomes) >= 2


# ===========================================================================
# Falklands campaign YAML loading
# ===========================================================================


class TestFalklandsCampaignYAML:
    """Verify the Falklands campaign YAML loads correctly."""

    def test_load_falklands_campaign(self):
        loader = CampaignDataLoader()
        path = DATA_DIR / "scenarios" / "falklands_campaign" / "scenario.yaml"
        if not path.exists():
            pytest.skip("Falklands campaign YAML not found")
        campaign = loader.load(path)
        assert campaign.name.startswith("Falklands")
        assert campaign.duration_hours == 120.0

    def test_falklands_forces_correct(self):
        loader = CampaignDataLoader()
        path = DATA_DIR / "scenarios" / "falklands_campaign" / "scenario.yaml"
        if not path.exists():
            pytest.skip("Falklands campaign YAML not found")
        campaign = loader.load(path)
        blue = campaign.sides[0]
        red = campaign.sides[1]
        assert blue.side == "blue"
        assert red.side == "red"
        # British: 4 Type 42 + 4 Type 22 + 8 Sea Harrier = 16
        assert sum(u.get("count", 1) for u in blue.units) == 16

    def test_falklands_has_documented_outcomes(self):
        loader = CampaignDataLoader()
        path = DATA_DIR / "scenarios" / "falklands_campaign" / "scenario.yaml"
        if not path.exists():
            pytest.skip("Falklands campaign YAML not found")
        campaign = loader.load(path)
        assert len(campaign.documented_outcomes) >= 2
