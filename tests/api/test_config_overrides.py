"""Focused tests for typed API calibration overlays."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from stochastic_warfare.simulation.scenario import (
    load_campaign_scenario_config,
)

SCENARIO_PATH = Path("data/scenarios/test_campaign/scenario.yaml")
NONDEFAULT_SCENARIO_PATH = Path(
    "data/scenarios/golan_heights/scenario.yaml",
)


def test_flat_scalar_override() -> None:
    config = load_campaign_scenario_config(
        SCENARIO_PATH,
        {"hit_probability_modifier": 0.5},
    )
    assert config.calibration_overrides.hit_probability_modifier == 0.5


def test_nested_dict_merge_preserves_sibling() -> None:
    config = load_campaign_scenario_config(
        NONDEFAULT_SCENARIO_PATH,
        {"morale": {"base_degrade_rate": 0.2}},
    )
    assert config.calibration_overrides.morale.base_degrade_rate == 0.2
    assert config.calibration_overrides.morale.base_recover_rate == 0.15


def test_flat_legacy_alias_normalizes_to_side_override() -> None:
    config = load_campaign_scenario_config(
        SCENARIO_PATH,
        {"blue_start_x": 2500.0},
    )
    assert config.calibration_overrides.side_overrides["blue"].start_x == 2500.0


def test_list_replaced_not_merged() -> None:
    baseline = load_campaign_scenario_config(NONDEFAULT_SCENARIO_PATH)
    assert baseline.calibration_overrides.defensive_sides == ["blue"]

    config = load_campaign_scenario_config(
        NONDEFAULT_SCENARIO_PATH,
        {"defensive_sides": ["red"]},
    )
    assert config.calibration_overrides.defensive_sides == ["red"]


def test_mixed_structured_and_legacy_fields_are_all_applied() -> None:
    config = load_campaign_scenario_config(
        SCENARIO_PATH,
        {
            "morale": {"base_recover_rate": 0.2},
            "morale_degrade_rate_modifier": 0.4,
            "side_overrides": {"blue": {"start_x": 2500.0}},
            "blue_cohesion": 0.8,
        },
    )
    calibration = config.calibration_overrides
    assert calibration.morale.base_recover_rate == 0.2
    assert calibration.morale.degrade_rate_modifier == 0.4
    assert calibration.side_overrides["blue"].start_x == 2500.0
    assert calibration.side_overrides["blue"].cohesion == 0.8
    assert (
        calibration.to_flat_dict(["blue", "red"])[
            "morale_degrade_rate_modifier"
        ]
        == 0.4
    )


def test_empty_overrides_noop() -> None:
    baseline = load_campaign_scenario_config(SCENARIO_PATH)
    effective = load_campaign_scenario_config(SCENARIO_PATH, {})
    assert effective == baseline


def test_unknown_key_rejected() -> None:
    with pytest.raises(ValidationError, match="unknown_field"):
        load_campaign_scenario_config(
            SCENARIO_PATH,
            {"unknown_field": 1},
        )


def test_wrong_scenario_wrapper_rejected() -> None:
    with pytest.raises(ValidationError, match="calibration_overrides"):
        load_campaign_scenario_config(
            SCENARIO_PATH,
            {"calibration_overrides": {"hit_probability_modifier": 0.5}},
        )


def test_unknown_side_rejected() -> None:
    with pytest.raises(ValueError, match="unknown sides"):
        load_campaign_scenario_config(
            SCENARIO_PATH,
            {"side_overrides": {"green": {"start_x": 1000.0}}},
        )
