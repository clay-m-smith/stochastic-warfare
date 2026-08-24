"""Phase 112 red proofs for commander and unit-data integrity."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from stochastic_warfare.entities.base import Unit
from stochastic_warfare.entities.loader import UnitLoader
from stochastic_warfare.simulation.scenario import (
    CampaignScenarioConfig,
    ScenarioLoader,
    load_campaign_scenario_config,
)


DATA_DIR = Path("data")


def test_missing_side_commander_profile_rejects_before_unit_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario_path = DATA_DIR / "scenarios" / "test_campaign" / "scenario.yaml"
    payload = load_campaign_scenario_config(scenario_path).model_dump(mode="python")
    missing_profile = "phase112_missing_commander_profile"
    payload["sides"][0]["commander_profile"] = missing_profile
    invalid_config = CampaignScenarioConfig.model_validate(payload)

    constructed_ids: list[str] = []
    original_create = UnitLoader.create_unit

    def record_create(
        self: UnitLoader,
        *args: Any,
        **kwargs: Any,
    ) -> Unit:
        constructed_ids.append(str(kwargs["entity_id"]))
        return original_create(self, *args, **kwargs)

    monkeypatch.setattr(UnitLoader, "create_unit", record_create)

    with pytest.raises(ValueError, match=missing_profile):
        ScenarioLoader(DATA_DIR).load(
            scenario_path,
            scenario_config=invalid_config,
        )

    assert constructed_ids == []


def test_unit_loader_rejects_invalid_crew_skill_eagerly(
    tmp_path: Path,
) -> None:
    invalid_path = tmp_path / "invalid_crew_skill.yaml"
    invalid_path.write_text(
        """
unit_type: phase112_invalid_skill
domain: ground
display_name: Invalid crew-skill probe
ground_type: LIGHT_INFANTRY
max_speed: 1.0
crew:
  - role: COMMANDER
    count: 1
    skill: EXPERT
equipment:
  - name: Naked Eye Observation
    category: SENSOR
""".lstrip(),
        encoding="utf-8",
    )

    loader = UnitLoader(tmp_path)
    with pytest.raises(ValueError) as exc_info:
        loader.load_definition(invalid_path)

    message = str(exc_info.value)
    assert "skill" in message.lower()
    assert "EXPERT" in message
    assert "ELITE" in message
    assert invalid_path.name in message


def test_austerlitz_production_load_preserves_authored_old_guard_roster() -> None:
    scenario_path = (
        DATA_DIR
        / "eras"
        / "napoleonic"
        / "scenarios"
        / "austerlitz"
        / "scenario.yaml"
    )
    config = load_campaign_scenario_config(scenario_path)
    authored_counts = {
        side.side: sum(entry.get("count", 1) for entry in side.units)
        for side in config.sides
    }

    context = ScenarioLoader(DATA_DIR).load(scenario_path, seed=42)
    loaded_counts = {
        side: len(context.units_by_side.get(side, []))
        for side in authored_counts
    }
    old_guard_count = sum(
        unit.unit_type == "french_old_guard"
        for unit in context.units_by_side["french"]
    )

    assert (loaded_counts, old_guard_count) == (authored_counts, 1)
