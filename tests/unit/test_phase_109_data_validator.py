"""Phase 109 production-registry coverage for the static data validator."""

from pathlib import Path

import pytest

import scripts.validate_scenario_data as data_validator
from scripts.validate_scenario_data import (
    compare_equipment_mapping_coverage,
    validate_unit_catalog,
    validate_unit_catalogs,
    validate_unit_yaml,
)
from stochastic_warfare.entities.equipment import EquipmentCategory
from stochastic_warfare.simulation.equipment_mappings import (
    EQUIPMENT_MAPPING_REGISTRY,
)
from stochastic_warfare.simulation.loadouts import (
    EquipmentMappingRegistry,
    SensorNonRuntimeMapping,
)


def test_all_unit_catalogs_preflight_through_runtime_loadout_builder() -> None:
    result, stats_by_era = validate_unit_catalogs()

    assert result.errors == []
    assert result.warnings == []
    assert {
        era: stats.units
        for era, stats in stats_by_era.items()
    } == {
        "modern": 102,
        "ancient_medieval": 20,
        "napoleonic": 21,
        "ww1": 16,
        "ww2": 25,
    }
    assert sum(
        stats.authored_mapping_entries
        for stats in stats_by_era.values()
    ) == 679
    assert {
        era: stats.distinct_authored_mapping_keys
        for era, stats in stats_by_era.items()
    } == {
        "modern": 244,
        "ancient_medieval": 34,
        "napoleonic": 27,
        "ww1": 47,
        "ww2": 93,
    }
    assert result.mapping_coverage is not None
    assert result.mapping_coverage.authored_keys == 442
    assert result.mapping_coverage.registry_keys == 442
    assert result.mapping_coverage.covered_keys == 442
    assert result.mapping_coverage.unmapped_authored_keys == 0
    assert result.mapping_coverage.stale_registry_keys == 0
    assert sum(stats.sensor_required for stats in stats_by_era.values()) == 183
    assert sum(
        stats.sensor_intentionally_none
        for stats in stats_by_era.values()
    ) == 1
    assert result.classifications == [
        "modern/civilian_noncombatant: "
        "sensor_policy='intentionally_none' — "
        "Noncombatant group has no modeled surveillance equipment.",
    ]


def test_former_no_sensor_findings_have_typed_outcomes() -> None:
    civilian = validate_unit_yaml(
        Path("data/units/civilian_noncombatant.yaml"),
    )
    insurgent = validate_unit_yaml(
        Path("data/units/infantry/insurgent_squad.yaml"),
    )

    assert civilian.errors == []
    assert civilian.warnings == []
    assert civilian.classifications == [
        "modern/civilian_noncombatant: "
        "sensor_policy='intentionally_none' — "
        "Noncombatant group has no modeled surveillance equipment.",
    ]
    assert insurgent.errors == []
    assert insurgent.warnings == []
    assert insurgent.classifications == []


def test_unit_validator_rejects_unmapped_equipment(
    tmp_path: Path,
) -> None:
    source = Path("data/units/infantry/insurgent_squad.yaml").read_text(
        encoding="utf-8",
    )
    invalid_unit = tmp_path / "unmapped_unit.yaml"
    invalid_unit.write_text(
        source.replace('name: "AK-47"', 'name: "Unmapped Placeholder Rifle"'),
        encoding="utf-8",
    )

    result, stats = validate_unit_catalog(
        "modern",
        unit_file=invalid_unit,
    )

    assert stats.units == 1
    assert len(result.errors) == 1
    assert "Unmapped Placeholder Rifle" in result.errors[0]
    assert "no mapping declaration" in result.errors[0]


def test_full_catalog_coverage_rejects_unmapped_authored_key() -> None:
    registry_keys = {
        (record.category, record.equipment_name)
        for record in EQUIPMENT_MAPPING_REGISTRY.records
    }
    authored_keys = registry_keys | {
        (EquipmentCategory.WEAPON, "Unmapped Full-Catalog Fixture"),
    }

    result, stats = compare_equipment_mapping_coverage(authored_keys)

    assert stats.authored_keys == 443
    assert stats.registry_keys == 442
    assert stats.covered_keys == 442
    assert stats.unmapped_authored_keys == 1
    assert stats.stale_registry_keys == 0
    assert result.errors == [
        "Full-catalog equipment coverage: authored key "
        "(WEAPON, 'Unmapped Full-Catalog Fixture') "
        "has no registry declaration",
    ]


def test_stale_registry_check_is_full_catalog_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stale_name = "Registry-Only Sensor Fixture"
    registry_with_stale_key = EquipmentMappingRegistry((
        *EQUIPMENT_MAPPING_REGISTRY.records,
        SensorNonRuntimeMapping(
            equipment_name=stale_name,
            reason="Focused stale-registry coverage fixture.",
        ),
    ))
    monkeypatch.setattr(
        data_validator,
        "EQUIPMENT_MAPPING_REGISTRY",
        registry_with_stale_key,
    )

    full_result, _ = validate_unit_catalogs()
    single_result, _ = validate_unit_catalog(
        "modern",
        unit_file=Path("data/units/infantry/insurgent_squad.yaml"),
    )

    assert full_result.mapping_coverage is not None
    assert full_result.mapping_coverage.authored_keys == 442
    assert full_result.mapping_coverage.registry_keys == 443
    assert full_result.mapping_coverage.covered_keys == 442
    assert full_result.mapping_coverage.unmapped_authored_keys == 0
    assert full_result.mapping_coverage.stale_registry_keys == 1
    assert full_result.errors == [
        "Full-catalog equipment coverage: stale registry key "
        f"(SENSOR, {stale_name!r}) is not authored by any unit catalog",
    ]
    assert single_result.errors == []
    assert single_result.mapping_coverage is None
