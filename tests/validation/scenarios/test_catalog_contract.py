"""Phase 112 production scenario-data validation outcomes."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts.validate_scenario_data import (
    ScenarioLoadStats,
    _collect_scenario_yamls,
    validate_scenario_loads,
)
from stochastic_warfare.simulation.scenario import (
    parse_campaign_scenario_config,
)

ROOT = Path(__file__).resolve().parents[3]
SOURCE_SCENARIO = ROOT / "data" / "scenarios" / "test_campaign" / "scenario.yaml"


@pytest.mark.test_evidence("behavioral_oracle")
def test_all_shipped_scenarios_strictly_round_trip_through_typed_json() -> None:
    """Editor JSON, including materialized enum defaults, remains loadable."""
    scenario_paths = _collect_scenario_yamls()
    assert len(scenario_paths) == 52

    for path in scenario_paths:
        source = yaml.safe_load(path.read_text(encoding="utf-8"))
        parsed = parse_campaign_scenario_config(source)
        reparsed = parse_campaign_scenario_config(
            parsed.model_dump(mode="json"),
        )
        assert reparsed.model_dump(mode="json") == parsed.model_dump(
            mode="json",
        ), path


def test_all_shipped_instance_overrides_are_applied_exactly() -> None:
    """Every authored override must be observed on every constructed unit."""
    totals = ScenarioLoadStats()
    scenario_paths = _collect_scenario_yamls()
    assert len(scenario_paths) == 52

    for path in scenario_paths:
        result = validate_scenario_loads(path)
        assert result.errors == [], (path, result.errors)
        assert result.warnings == []
        assert result.scenario_load_stats is not None
        stats = result.scenario_load_stats
        totals = ScenarioLoadStats(
            authored_initial_units=(totals.authored_initial_units + stats.authored_initial_units),
            loaded_initial_units=(totals.loaded_initial_units + stats.loaded_initial_units),
            authored_override_groups=(totals.authored_override_groups + stats.authored_override_groups),
            authored_override_units=(totals.authored_override_units + stats.authored_override_units),
            authored_override_fields=(totals.authored_override_fields + stats.authored_override_fields),
            verified_override_units=(totals.verified_override_units + stats.verified_override_units),
            verified_override_fields=(totals.verified_override_fields + stats.verified_override_fields),
        )

    assert totals == ScenarioLoadStats(
        authored_initial_units=8388,
        loaded_initial_units=8388,
        authored_override_groups=70,
        authored_override_units=1128,
        authored_override_fields=1131,
        verified_override_units=1128,
        verified_override_fields=1131,
    )


@pytest.mark.test_evidence("behavioral_oracle")
def test_scenario_data_validator_rejects_incompatible_override(
    tmp_path: Path,
) -> None:
    """A typed but domain-incompatible override must fail production load."""
    source = yaml.safe_load(
        SOURCE_SCENARIO.read_text(encoding="utf-8"),
    )
    source["name"] = "Phase 112 invalid aerial armor override"
    source["sides"][0]["units"] = [
        {
            "unit_type": "f16c",
            "count": 1,
            "overrides": {"armor_front": 100.0},
        },
    ]
    invalid = tmp_path / "scenario.yaml"
    invalid.write_text(
        yaml.safe_dump(source, sort_keys=False),
        encoding="utf-8",
    )

    result = validate_scenario_loads(invalid)

    assert result.scenario_load_stats is None
    assert len(result.errors) == 1
    assert "ScenarioLoader.load() failed" in result.errors[0]
    assert "'f16c' is incompatible with armor_front override" in (result.errors[0])
