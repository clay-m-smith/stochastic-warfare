"""Tests for validation.campaign_data — campaign-level historical data models."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from stochastic_warfare.simulation.scenario import CampaignScenarioConfig
from stochastic_warfare.validation.campaign_data import (
    AIExpectation,
    CampaignDataLoader,
    HistoricalCampaign,
)
from stochastic_warfare.validation.historical_data import HistoricalMetric


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _minimal_campaign_dict(**overrides) -> dict:
    """Return a minimal valid HistoricalCampaign dict."""
    base = {
        "name": "Test Campaign",
        "date": "1973-10-06",
        "duration_hours": 96.0,
        "terrain": {
            "width_m": 10000,
            "height_m": 15000,
            "terrain_type": "hilly_defense",
        },
        "sides": [
            {
                "side": "blue",
                "units": [{"unit_type": "m1a2", "count": 4}],
                "experience_level": 0.7,
            },
            {
                "side": "red",
                "units": [{"unit_type": "m1a2", "count": 8}],
                "experience_level": 0.4,
            },
        ],
    }
    base.update(overrides)
    return base


# ===========================================================================
# Model validation
# ===========================================================================


class TestHistoricalCampaignModel:
    """Tests for HistoricalCampaign pydantic model."""

    def test_minimal_valid(self):
        c = HistoricalCampaign.model_validate(_minimal_campaign_dict())
        assert c.name == "Test Campaign"
        assert c.duration_hours == 96.0
        assert len(c.sides) == 2

    def test_full_valid(self):
        d = _minimal_campaign_dict(
            documented_outcomes=[
                {"name": "exchange_ratio", "value": 4.6, "tolerance_factor": 3.0}
            ],
            sources=["Source A", "Source B"],
            ai_expectations=[
                {
                    "side": "red",
                    "time_range_s": [0, 172800],
                    "expected_posture": "attack",
                    "tolerance": "moderate",
                }
            ],
            objectives=[
                {
                    "objective_id": "obj1",
                    "position": [5000, 7500],
                    "radius_m": 500,
                }
            ],
            victory_conditions=[
                {"type": "force_destroyed", "side": "blue"},
                {"type": "time_expired", "side": "blue"},
            ],
            reinforcements=[
                {
                    "side": "blue",
                    "arrival_time_s": 36000,
                    "units": [{"unit_type": "m1a2", "count": 2}],
                }
            ],
        )
        c = HistoricalCampaign.model_validate(d)
        assert len(c.documented_outcomes) == 1
        assert len(c.sources) == 2
        assert len(c.ai_expectations) == 1
        assert len(c.objectives) == 1
        assert len(c.victory_conditions) == 2
        assert len(c.reinforcements) == 1

    def test_defaults_empty_lists(self):
        c = HistoricalCampaign.model_validate(_minimal_campaign_dict())
        assert c.documented_outcomes == []
        assert c.sources == []
        assert c.ai_expectations == []
        assert c.objectives == []
        assert c.reinforcements == []

    def test_rejects_single_side(self):
        d = _minimal_campaign_dict()
        d["sides"] = [d["sides"][0]]
        with pytest.raises(Exception, match="at least 2"):
            HistoricalCampaign.model_validate(d)

    def test_rejects_zero_duration(self):
        with pytest.raises(Exception, match="positive"):
            HistoricalCampaign.model_validate(
                _minimal_campaign_dict(duration_hours=0)
            )

    def test_rejects_negative_duration(self):
        with pytest.raises(Exception, match="positive"):
            HistoricalCampaign.model_validate(
                _minimal_campaign_dict(duration_hours=-1)
            )

    def test_tick_resolution_defaults(self):
        c = HistoricalCampaign.model_validate(_minimal_campaign_dict())
        assert c.tick_resolution.strategic_s == 3600.0
        assert c.tick_resolution.tactical_s == 5.0

    def test_calibration_overrides_preserved(self):
        cal = {"hit_probability_modifier": 0.8, "target_size_modifier": 0.55}
        c = HistoricalCampaign.model_validate(
            _minimal_campaign_dict(calibration_overrides=cal)
        )
        assert c.calibration_overrides.get("target_size_modifier", 1.0) == 0.55


# ===========================================================================
# AIExpectation validation
# ===========================================================================


class TestAIExpectation:
    """Tests for AIExpectation model."""

    def test_valid(self):
        e = AIExpectation(
            side="red",
            time_range_s=[0, 172800],
            expected_posture="attack",
            tolerance="moderate",
        )
        assert e.side == "red"
        assert e.expected_posture == "attack"

    def test_rejects_single_element_range(self):
        with pytest.raises(Exception, match="exactly"):
            AIExpectation(
                side="red",
                time_range_s=[0],
                expected_posture="attack",
            )

    def test_rejects_negative_range(self):
        with pytest.raises(Exception, match="non-negative"):
            AIExpectation(
                side="red",
                time_range_s=[-1, 100],
                expected_posture="attack",
            )

    def test_rejects_start_ge_end(self):
        with pytest.raises(Exception, match="start must be < end"):
            AIExpectation(
                side="red",
                time_range_s=[100, 100],
                expected_posture="attack",
            )

    def test_rejects_invalid_tolerance(self):
        with pytest.raises(Exception, match="tolerance"):
            AIExpectation(
                side="red",
                time_range_s=[0, 100],
                expected_posture="attack",
                tolerance="very_strict",
            )

    def test_tolerance_defaults_moderate(self):
        e = AIExpectation(
            side="red",
            time_range_s=[0, 100],
            expected_posture="attack",
        )
        assert e.tolerance == "moderate"


# ===========================================================================
# YAML loading
# ===========================================================================


class TestCampaignDataLoader:
    """Tests for CampaignDataLoader YAML loading."""

    def test_load_valid_yaml(self, tmp_path: Path):
        yaml_content = textwrap.dedent("""\
            name: "Test Campaign"
            date: "1973-10-06"
            duration_hours: 96.0
            terrain:
              width_m: 10000
              height_m: 15000
              terrain_type: hilly_defense
            sides:
              - side: blue
                units:
                  - unit_type: m1a2
                    count: 4
                experience_level: 0.7
              - side: red
                units:
                  - unit_type: m1a2
                    count: 8
                experience_level: 0.4
            documented_outcomes:
              - name: exchange_ratio
                value: 4.6
                tolerance_factor: 3.0
            sources:
              - "Source A"
        """)
        p = tmp_path / "scenario.yaml"
        p.write_text(yaml_content)

        loader = CampaignDataLoader()
        campaign = loader.load(p)
        assert campaign.name == "Test Campaign"
        assert len(campaign.documented_outcomes) == 1
        assert campaign.documented_outcomes[0].tolerance_factor == 3.0

    def test_load_with_ai_expectations(self, tmp_path: Path):
        yaml_content = textwrap.dedent("""\
            name: "AI Test"
            date: "1973-10-06"
            duration_hours: 48.0
            terrain:
              width_m: 5000
              height_m: 5000
              terrain_type: flat_desert
            sides:
              - side: blue
                units:
                  - unit_type: m1a2
                    count: 2
              - side: red
                units:
                  - unit_type: m1a2
                    count: 4
            ai_expectations:
              - side: red
                time_range_s: [0, 86400]
                expected_posture: attack
                tolerance: moderate
              - side: blue
                time_range_s: [0, 86400]
                expected_posture: defend
                tolerance: loose
        """)
        p = tmp_path / "scenario.yaml"
        p.write_text(yaml_content)

        loader = CampaignDataLoader()
        campaign = loader.load(p)
        assert len(campaign.ai_expectations) == 2
        assert campaign.ai_expectations[0].expected_posture == "attack"

    def test_load_with_reinforcements(self, tmp_path: Path):
        yaml_content = textwrap.dedent("""\
            name: "Reinforce Test"
            date: "1973-10-06"
            duration_hours: 96.0
            terrain:
              width_m: 10000
              height_m: 10000
              terrain_type: flat_desert
            sides:
              - side: blue
                units:
                  - unit_type: m1a2
                    count: 4
              - side: red
                units:
                  - unit_type: m1a2
                    count: 8
            reinforcements:
              - side: blue
                arrival_time_s: 36000
                units:
                  - unit_type: m1a2
                    count: 2
                position: [100, 5000]
        """)
        p = tmp_path / "scenario.yaml"
        p.write_text(yaml_content)

        loader = CampaignDataLoader()
        campaign = loader.load(p)
        assert len(campaign.reinforcements) == 1
        assert campaign.reinforcements[0].arrival_time_s == 36000

    def test_load_nonexistent_path(self):
        loader = CampaignDataLoader()
        with pytest.raises(FileNotFoundError):
            loader.load(Path("/nonexistent/path.yaml"))

    def test_load_invalid_yaml_content(self, tmp_path: Path):
        p = tmp_path / "bad.yaml"
        p.write_text("name: 123\n")
        loader = CampaignDataLoader()
        with pytest.raises(Exception):
            loader.load(p)

    def test_load_missing_required_fields(self, tmp_path: Path):
        p = tmp_path / "missing.yaml"
        p.write_text("name: test\n")
        loader = CampaignDataLoader()
        with pytest.raises(Exception):
            loader.load(p)


# ===========================================================================
# Conversion to CampaignScenarioConfig
# ===========================================================================


class TestToScenarioConfig:
    """Tests for CampaignDataLoader.to_scenario_config conversion."""

    def test_basic_conversion(self):
        campaign = HistoricalCampaign.model_validate(_minimal_campaign_dict())
        config = CampaignDataLoader.to_scenario_config(campaign)
        assert isinstance(config, CampaignScenarioConfig)
        assert config.name == campaign.name
        assert config.duration_hours == campaign.duration_hours

    def test_sides_preserved(self):
        campaign = HistoricalCampaign.model_validate(_minimal_campaign_dict())
        config = CampaignDataLoader.to_scenario_config(campaign)
        assert len(config.sides) == 2
        assert config.sides[0].side == "blue"
        assert config.sides[1].side == "red"

    def test_terrain_preserved(self):
        campaign = HistoricalCampaign.model_validate(_minimal_campaign_dict())
        config = CampaignDataLoader.to_scenario_config(campaign)
        assert config.terrain.width_m == 10000
        assert config.terrain.terrain_type == "hilly_defense"

    def test_strips_documented_outcomes(self):
        d = _minimal_campaign_dict(
            documented_outcomes=[
                {"name": "exchange_ratio", "value": 4.6, "tolerance_factor": 3.0}
            ],
        )
        campaign = HistoricalCampaign.model_validate(d)
        config = CampaignDataLoader.to_scenario_config(campaign)
        assert not hasattr(config, "documented_outcomes")

    def test_strips_ai_expectations(self):
        d = _minimal_campaign_dict(
            ai_expectations=[
                {
                    "side": "red",
                    "time_range_s": [0, 100],
                    "expected_posture": "attack",
                }
            ],
        )
        campaign = HistoricalCampaign.model_validate(d)
        config = CampaignDataLoader.to_scenario_config(campaign)
        assert not hasattr(config, "ai_expectations")

    def test_calibration_overrides_carried(self):
        cal = {"hit_probability_modifier": 0.8}
        campaign = HistoricalCampaign.model_validate(
            _minimal_campaign_dict(calibration_overrides=cal)
        )
        config = CampaignDataLoader.to_scenario_config(campaign)
        assert config.calibration_overrides.get("hit_probability_modifier", 1.0) == 0.8

    def test_victory_conditions_preserved(self):
        d = _minimal_campaign_dict(
            victory_conditions=[
                {"type": "force_destroyed", "side": "blue"},
                {"type": "time_expired", "side": "blue"},
            ]
        )
        campaign = HistoricalCampaign.model_validate(d)
        config = CampaignDataLoader.to_scenario_config(campaign)
        assert len(config.victory_conditions) == 2

    def test_reinforcements_preserved(self):
        d = _minimal_campaign_dict(
            reinforcements=[
                {
                    "side": "blue",
                    "arrival_time_s": 36000,
                    "units": [{"unit_type": "m1a2", "count": 2}],
                }
            ]
        )
        campaign = HistoricalCampaign.model_validate(d)
        config = CampaignDataLoader.to_scenario_config(campaign)
        assert len(config.reinforcements) == 1
        assert config.reinforcements[0].arrival_time_s == 36000


# ===========================================================================
# Documented outcomes parsing
# ===========================================================================


class TestDocumentedOutcomes:
    """Tests for documented_outcomes integration."""

    def test_multiple_metrics(self):
        d = _minimal_campaign_dict(
            documented_outcomes=[
                {"name": "red_tanks_destroyed", "value": 1100, "tolerance_factor": 3.0},
                {"name": "blue_tanks_destroyed", "value": 250, "tolerance_factor": 3.0},
                {"name": "campaign_duration_s", "value": 345600, "tolerance_factor": 1.5},
            ],
        )
        campaign = HistoricalCampaign.model_validate(d)
        assert len(campaign.documented_outcomes) == 3
        assert campaign.documented_outcomes[0].value == 1100
        assert campaign.documented_outcomes[2].name == "campaign_duration_s"

    def test_historical_metric_fields(self):
        d = _minimal_campaign_dict(
            documented_outcomes=[
                {
                    "name": "exchange_ratio",
                    "value": 4.6,
                    "tolerance_factor": 3.0,
                    "unit": "red:blue",
                    "source": "Test Source",
                    "source_quality": 1,
                    "notes": "approximate",
                }
            ],
        )
        campaign = HistoricalCampaign.model_validate(d)
        m = campaign.documented_outcomes[0]
        assert isinstance(m, HistoricalMetric)
        assert m.unit == "red:blue"
        assert m.source_quality == 1

    def test_default_tolerance_factor(self):
        d = _minimal_campaign_dict(
            documented_outcomes=[{"name": "test", "value": 100}],
        )
        campaign = HistoricalCampaign.model_validate(d)
        assert campaign.documented_outcomes[0].tolerance_factor == 2.0

    def test_rejects_zero_tolerance(self):
        d = _minimal_campaign_dict(
            documented_outcomes=[
                {"name": "test", "value": 100, "tolerance_factor": 0}
            ],
        )
        with pytest.raises(Exception, match="positive"):
            HistoricalCampaign.model_validate(d)

    def test_empty_outcomes_valid(self):
        campaign = HistoricalCampaign.model_validate(_minimal_campaign_dict())
        assert campaign.documented_outcomes == []
