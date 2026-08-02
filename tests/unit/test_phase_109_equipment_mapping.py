"""Focused synthetic proofs for the Phase 109 runtime loadout boundary."""

from __future__ import annotations

from pathlib import Path

import pytest

from stochastic_warfare.combat.ammunition import (
    AmmoDefinition,
    AmmoLoader,
    AmmoType,
    GuidanceType,
    WeaponCategory,
    WeaponDefinition,
    WeaponLoader,
)
from stochastic_warfare.core.era import Era, EraConfig
from stochastic_warfare.core.strict_yaml import DuplicateKeyError
from stochastic_warfare.core.types import Domain, Position
from stochastic_warfare.detection.sensors import (
    SensorDefinition,
    SensorInstance,
    SensorLoader,
    SensorSuite,
    SensorType,
    signature_domain_for_sensor_type,
)
from stochastic_warfare.detection.signatures import SignatureDomain
from stochastic_warfare.entities.base import Unit
from stochastic_warfare.entities.equipment import EquipmentCategory, EquipmentItem
from stochastic_warfare.entities.loader import (
    EquipmentEntry,
    SensorPolicy,
    UnitDefinition,
)
from stochastic_warfare.simulation import equipment_mappings
from stochastic_warfare.simulation.equipment_mappings import (
    EQUIPMENT_MAPPING_RECORDS,
)
from stochastic_warfare.simulation.loadouts import (
    DuplicateEquipmentMappingError,
    EquipmentMappingError,
    EquipmentMappingRegistry,
    ReferenceKind,
    ResolutionDisposition,
    RuntimeLoadoutBuilder,
    SensorAttachmentMapping,
    SensorModeledRole,
    SensorNonRuntimeMapping,
    SensorUnsupportedMapping,
    UnsupportedEquipmentError,
    WeaponAssignment,
    WeaponAttachmentMapping,
    WeaponModeledRole,
    WeaponNonRuntimeMapping,
    WeaponStoreMapping,
    required_domains_for_sensor_role,
)
from stochastic_warfare.simulation.runtime import (
    AnalysisInputError,
    AnalysisVariant,
    DoctrineAnalysisVariant,
)
from stochastic_warfare.simulation.scenario import (
    DoctrineSideAssignment,
    load_campaign_scenario_config,
)
from stochastic_warfare.tools._run_helpers import prepare_analysis
from stochastic_warfare.tools.doctrine_compare import (
    DoctrineCompareConfig,
    run_doctrine_comparison,
)


def _weapon(
    weapon_id: str,
    *,
    category: str = "CANNON",
    guidance: str = "NONE",
    max_range_m: float = 1_000.0,
    magazine_capacity: int = 4,
    compatible_ammo: list[str] | None = None,
    target_domains: list[str] | None = None,
    caliber_mm: float = 20.0,
    rate_of_fire_rpm: float = 0.0,
    barrel_life_rounds: int = 0,
) -> WeaponDefinition:
    return WeaponDefinition(
        weapon_id=weapon_id,
        display_name=weapon_id,
        category=category,
        caliber_mm=caliber_mm,
        max_range_m=max_range_m,
        rate_of_fire_rpm=rate_of_fire_rpm,
        guidance=guidance,
        magazine_capacity=magazine_capacity,
        barrel_life_rounds=barrel_life_rounds,
        compatible_ammo=(compatible_ammo if compatible_ammo is not None else [f"{weapon_id}_ammo"]),
        target_domains=target_domains or [],
    )


def _ammo(
    ammo_id: str,
    *,
    ammo_type: str = "HE",
    guidance: str = "NONE",
) -> AmmoDefinition:
    return AmmoDefinition(
        ammo_id=ammo_id,
        display_name=ammo_id,
        ammo_type=ammo_type,
        guidance=guidance,
    )


def _sensor(
    sensor_id: str,
    *,
    sensor_type: str = "VISUAL",
    detects_domain: list[str] | None = None,
    target_domains: list[str] | None = None,
    max_range_m: float = 2_000.0,
) -> SensorDefinition:
    return SensorDefinition(
        sensor_id=sensor_id,
        sensor_type=sensor_type,
        display_name=sensor_id,
        max_range_m=max_range_m,
        detection_threshold=1.0,
        detects_domain=(detects_domain if detects_domain is not None else [sensor_type]),
        target_domains=target_domains or [],
    )


def _loaders(
    *,
    weapons: tuple[WeaponDefinition, ...] = (),
    ammunition: tuple[AmmoDefinition, ...] = (),
    sensors: tuple[SensorDefinition, ...] = (),
) -> tuple[WeaponLoader, AmmoLoader, SensorLoader]:
    weapon_loader = WeaponLoader(Path("."))
    ammo_loader = AmmoLoader(Path("."))
    sensor_loader = SensorLoader(Path("."))
    weapon_loader._definitions.update({definition.weapon_id: definition for definition in weapons})
    ammo_loader._definitions.update({definition.ammo_id: definition for definition in ammunition})
    sensor_loader._definitions.update({definition.sensor_id: definition for definition in sensors})
    return weapon_loader, ammo_loader, sensor_loader


def _unit_definition(
    unit_type: str,
    equipment: tuple[tuple[str, str], ...],
    *,
    sensor_policy: SensorPolicy = SensorPolicy.REQUIRED,
    sensor_policy_reason: str | None = None,
    data_link_range: float | None = None,
) -> UnitDefinition:
    return UnitDefinition(
        unit_type=unit_type,
        domain="ground",
        ground_type="LIGHT_INFANTRY",
        display_name=unit_type,
        max_speed=1.0,
        crew=[],
        equipment=[EquipmentEntry(name=name, category=category) for name, category in equipment],
        sensor_policy=sensor_policy,
        sensor_policy_reason=sensor_policy_reason,
        data_link_range=data_link_range,
    )


def _runtime_unit(
    definition: UnitDefinition,
    entity_id: str = "unit-1",
) -> Unit:
    return Unit(
        entity_id=entity_id,
        position=Position(0.0, 0.0),
        unit_type=definition.unit_type,
        equipment=[
            EquipmentItem(
                equipment_id=f"equip-{index:04d}",
                name=entry.name,
                category=EquipmentCategory[entry.category.upper()],
            )
            for index, entry in enumerate(definition.equipment)
        ],
    )


def _weapon_mapping(
    equipment_name: str,
    weapon_id: str,
    *,
    category: WeaponCategory = WeaponCategory.CANNON,
    modeled_role: WeaponModeledRole = WeaponModeledRole.GROUND_DIRECT_FIRE,
    target_domains: tuple[Domain, ...] = (Domain.GROUND,),
    allowed_ammo_ids: tuple[str, ...] = (),
) -> WeaponAttachmentMapping:
    return WeaponAttachmentMapping(
        equipment_name=equipment_name,
        weapon_id=weapon_id,
        expected_weapon_category=category,
        modeled_role=modeled_role,
        required_target_domains=target_domains,
        allowed_ammo_ids=allowed_ammo_ids,
    )


def _sensor_mapping(
    equipment_name: str = "Eyes",
    sensor_id: str = "visual",
) -> SensorAttachmentMapping:
    return SensorAttachmentMapping(
        equipment_name=equipment_name,
        sensor_id=sensor_id,
        expected_sensor_type=SensorType.VISUAL,
        expected_signature_domain=SignatureDomain.VISUAL,
        modeled_role=SensorModeledRole.VISUAL_OBSERVATION,
        compatible_weapon_roles=(),
        required_target_domains=required_domains_for_sensor_role(
            SensorModeledRole.VISUAL_OBSERVATION,
        ),
    )


def _builder(
    *,
    definitions: tuple[UnitDefinition, ...],
    records: tuple,
    weapons: tuple[WeaponDefinition, ...] = (),
    ammunition: tuple[AmmoDefinition, ...] = (),
    sensors: tuple[SensorDefinition, ...] = (),
    assignments: dict[str, str] | tuple[WeaponAssignment, ...] = {},
    era_config: EraConfig | None = None,
) -> RuntimeLoadoutBuilder:
    weapon_loader, ammo_loader, sensor_loader = _loaders(
        weapons=weapons,
        ammunition=ammunition,
        sensors=sensors,
    )
    return RuntimeLoadoutBuilder(
        weapon_loader=weapon_loader,
        ammo_loader=ammo_loader,
        sensor_loader=sensor_loader,
        unit_definitions={definition.unit_type: definition for definition in definitions},
        era_config=era_config or EraConfig(),
        assignment_overrides=assignments,
        reachable_unit_types=tuple(definition.unit_type for definition in definitions),
        registry=EquipmentMappingRegistry(records),
    )


def test_registry_rejects_duplicate_key_before_indexing() -> None:
    record = _weapon_mapping("Main Gun", "gun")
    with pytest.raises(
        DuplicateEquipmentMappingError,
        match=r"WEAPON.*'Main Gun'.*indexes 0 and 1",
    ):
        EquipmentMappingRegistry((record, record))


def test_registry_rejects_nonadjacent_exact_target_role_conflicts() -> None:
    exact_direct = _weapon_mapping("Direct Gun", "shared-gun")
    functional_air_defense = WeaponAttachmentMapping(
        equipment_name="Air-Defense Analogue",
        weapon_id="shared-gun",
        expected_weapon_category=WeaponCategory.CANNON,
        modeled_role=WeaponModeledRole.AIR_DEFENSE_GUN,
        required_target_domains=(Domain.AERIAL,),
        reference_kind=ReferenceKind.FUNCTIONAL_ANALOGUE,
        allowed_target_ids=("shared-gun",),
        rationale="Synthetic intervening functional role",
        source="Synthetic test source",
        expected_caliber_mm=20.0,
    )
    exact_artillery = _weapon_mapping(
        "Field Gun",
        "shared-gun",
        modeled_role=WeaponModeledRole.FIELD_ARTILLERY,
    )

    with pytest.raises(
        EquipmentMappingError,
        match=r"conflicting modeled roles.*index 0.*index 2",
    ):
        EquipmentMappingRegistry(
            (
                exact_direct,
                functional_air_defense,
                exact_artillery,
            ),
        )


def test_scenario_config_rejects_duplicate_weapon_assignment_yaml_keys(
    tmp_path: Path,
) -> None:
    scenario_path = tmp_path / "duplicate-assignment.yaml"
    scenario_path.write_text(
        "calibration_overrides:\n  weapon_assignments:\n    Main Gun: first\n    Main Gun: second\n",
        encoding="utf-8",
    )

    with pytest.raises(
        DuplicateKeyError,
        match=r"Duplicate YAML mapping key 'Main Gun'",
    ):
        load_campaign_scenario_config(scenario_path)


@pytest.mark.parametrize("consumer", ("scenario-batch", "doctrine-comparison"))
def test_tool_scenario_ingestion_rejects_duplicate_weapon_assignment_keys(
    consumer: str,
    tmp_path: Path,
) -> None:
    scenario_path = tmp_path / "duplicate-assignment.yaml"
    scenario_path.write_text(
        "calibration_overrides:\n"
        "  weapon_assignments:\n"
        "    Main Gun: first\n"
        "    Main Gun: second\n",
        encoding="utf-8",
    )

    with pytest.raises(
        AnalysisInputError,
        match=(
            r"Invalid scenario source .*duplicate-assignment\.yaml: "
            r"Duplicate YAML mapping key 'Main Gun'"
        ),
    ) as exc_info:
        if consumer == "scenario-batch":
            prepare_analysis(
                scenario_path=scenario_path,
                variants=(AnalysisVariant(variant_id="batch"),),
                metric_names=("ticks_executed",),
                data_dir=Path("data"),
            )
        else:
            run_doctrine_comparison(
                DoctrineCompareConfig(
                    scenario_path=str(scenario_path),
                    variants=(
                        AnalysisVariant(
                            variant_id="maneuverist",
                            doctrine_variant=DoctrineAnalysisVariant(
                                assignments=(
                                    DoctrineSideAssignment(
                                        side="blue",
                                        school_id="maneuverist",
                                    ),
                                ),
                            ),
                        ),
                        AnalysisVariant(
                            variant_id="attrition",
                            doctrine_variant=DoctrineAnalysisVariant(
                                assignments=(
                                    DoctrineSideAssignment(
                                        side="blue",
                                        school_id="attrition",
                                    ),
                                ),
                            ),
                        ),
                    ),
                    num_iterations=2,
                    data_dir="data",
                ),
            )
    assert isinstance(exc_info.value.__cause__, DuplicateKeyError)
    assert "Duplicate YAML mapping key 'Main Gun'" in str(exc_info.value.__cause__)


def test_record_shapes_are_frozen_typed_and_discriminated() -> None:
    record = _weapon_mapping("Main Gun", "gun")
    with pytest.raises(AttributeError):
        record.weapon_id = "other"  # type: ignore[misc]
    with pytest.raises(
        EquipmentMappingError,
        match="allowed_target_ids must be an immutable tuple",
    ):
        WeaponAttachmentMapping(
            equipment_name="Main Gun",
            weapon_id="gun",
            expected_weapon_category=WeaponCategory.CANNON,
            modeled_role=WeaponModeledRole.GROUND_DIRECT_FIRE,
            required_target_domains=(Domain.GROUND,),
            reference_kind=ReferenceKind.FUNCTIONAL_ANALOGUE,
            allowed_target_ids=["gun"],  # type: ignore[arg-type]
            rationale="same modeled role",
            source="source",
        )


def test_functional_weapon_analogue_requires_consumed_semantic_constraint() -> None:
    with pytest.raises(
        EquipmentMappingError,
        match=("Functional weapon analogues require at least one outcome-consumed.*constraint"),
    ):
        WeaponAttachmentMapping(
            equipment_name="Unbounded Role Gun",
            weapon_id="gun",
            expected_weapon_category=WeaponCategory.CANNON,
            modeled_role=WeaponModeledRole.GROUND_DIRECT_FIRE,
            required_target_domains=(Domain.GROUND,),
            reference_kind=ReferenceKind.FUNCTIONAL_ANALOGUE,
            allowed_target_ids=("gun",),
            rationale="Synthetic same-role analogue without a live envelope.",
            source="https://example.invalid/source",
        )


def test_production_functional_analogues_are_sourced_and_outcome_bounded() -> None:
    functional_weapons = [
        record
        for record in EQUIPMENT_MAPPING_RECORDS
        if (isinstance(record, WeaponAttachmentMapping) and record.reference_kind is ReferenceKind.FUNCTIONAL_ANALOGUE)
    ]
    functional_sensors = [
        record
        for record in EQUIPMENT_MAPPING_RECORDS
        if (isinstance(record, SensorAttachmentMapping) and record.reference_kind is ReferenceKind.FUNCTIONAL_ANALOGUE)
    ]

    weapon_source_keys = {(record.weapon_id, record.modeled_role) for record in functional_weapons}
    sensor_source_keys = {(record.sensor_id, record.modeled_role) for record in functional_sensors}
    assert weapon_source_keys == set(
        equipment_mappings._WEAPON_FUNCTIONAL_SOURCES,
    )
    assert sensor_source_keys == set(
        equipment_mappings._SENSOR_FUNCTIONAL_SOURCES,
    )
    assert len(
        equipment_mappings._WEAPON_FUNCTIONAL_SOURCE_DECLARATIONS,
    ) == len(set(equipment_mappings._WEAPON_FUNCTIONAL_SOURCE_DECLARATIONS))
    assert len(
        equipment_mappings._SENSOR_FUNCTIONAL_SOURCE_DECLARATIONS,
    ) == len(set(equipment_mappings._SENSOR_FUNCTIONAL_SOURCE_DECLARATIONS))
    assert len(functional_weapons) == len({record.equipment_name for record in functional_weapons})
    assert len(functional_sensors) == len({record.equipment_name for record in functional_sensors})
    for record in (*functional_weapons, *functional_sensors):
        assert record.source is not None
        assert record.source.startswith(("http://", "https://"))
        assert "per-entry decision" not in record.source
        assert record.rationale is not None

    for record in functional_weapons:
        assert (
            record.required_ammo_types
            or record.allowed_ammo_ids
            or record.expected_caliber_mm is not None
            or record.expected_guidance is not None
        )

    for record in functional_sensors:
        assert signature_domain_for_sensor_type(record.expected_sensor_type) is record.expected_signature_domain
        assert record.required_target_domains == required_domains_for_sensor_role(
            record.modeled_role,
        )
        assert record.modeled_max_range_m is not None
        assert record.modeled_max_range_m > 0.0
        assert record.modeled_fov_deg is not None
        assert 0.0 < record.modeled_fov_deg <= 360.0


def test_reviewed_identity_and_variant_labels_match_target_relationship() -> None:
    expected_kinds = {
        # Mount/count qualifiers preserve the identity of these cataloged guns.
        "5-inch/38 Mk 12 Gun (x5)": ReferenceKind.EXACT,
        "Lewis Gun Sponson Mount": ReferenceKind.EXACT,
        "M2 Browning .50 Cal (x13)": ReferenceKind.EXACT,
        "M240 7.62mm": ReferenceKind.EXACT,
        "M240 7.62mm Coaxial": ReferenceKind.EXACT,
        "M240 7.62mm Loader": ReferenceKind.EXACT,
        "Harpoon Quad Launchers (x2)": ReferenceKind.EXACT,
        "Mk 48 Torpedo Tubes": ReferenceKind.EXACT,
        "Mk 141 Harpoon Quad Launchers (x4)": ReferenceKind.EXACT,
        "RGM-84 Harpoon Missiles (x16)": ReferenceKind.EXACT,
        "Type 99 Model 2 20mm Cannon (x2)": ReferenceKind.EXACT,
        "Vickers .303 Synchronized MG (x2)": ReferenceKind.EXACT,
        # These names select a distinct model, launcher, or platform variant.
        "2A46M-5 125mm Smoothbore": ReferenceKind.VARIANT,
        "9P163-2 Kornet Launcher": ReferenceKind.VARIANT,
        "Harpoon Block 1C ASCM (x8)": ReferenceKind.VARIANT,
        "M16A2 Rifle": ReferenceKind.VARIANT,
        "M240C 7.62mm Coaxial": ReferenceKind.VARIANT,
        "M299 Launchers (x4)": ReferenceKind.VARIANT,
        "M901 Launching Station": ReferenceKind.VARIANT,
        "M901 TOW-2 Launcher": ReferenceKind.VARIANT,
        "SMLE Cavalry Carbine": ReferenceKind.VARIANT,
    }
    records_by_name = {record.equipment_name: record for record in EQUIPMENT_MAPPING_RECORDS}

    assert {
        equipment_name: records_by_name[equipment_name].reference_kind for equipment_name in expected_kinds
    } == expected_kinds


def test_identity_declarations_reject_duplicates_and_remain_disjoint() -> None:
    with pytest.raises(
        EquipmentMappingError,
        match="Duplicate synthetic identity declarations",
    ):
        equipment_mappings._checked_name_set(
            "synthetic",
            ("Duplicate", "Duplicate"),
        )

    assert (equipment_mappings._EXACT_WEAPON_EQUIPMENT & equipment_mappings._VARIANT_WEAPON_EQUIPMENT) == frozenset()
    assert (equipment_mappings._EXACT_SENSOR_EQUIPMENT & equipment_mappings._VARIANT_SENSOR_EQUIPMENT) == frozenset()
    weapon_attachments = [record for record in EQUIPMENT_MAPPING_RECORDS if isinstance(record, WeaponAttachmentMapping)]
    sensor_attachments = [record for record in EQUIPMENT_MAPPING_RECORDS if isinstance(record, SensorAttachmentMapping)]
    assert equipment_mappings._EXACT_WEAPON_EQUIPMENT == {
        record.equipment_name for record in weapon_attachments if record.reference_kind is ReferenceKind.EXACT
    }
    assert equipment_mappings._VARIANT_WEAPON_EQUIPMENT == {
        record.equipment_name for record in weapon_attachments if record.reference_kind is ReferenceKind.VARIANT
    }
    assert equipment_mappings._EXACT_SENSOR_EQUIPMENT == {
        record.equipment_name for record in sensor_attachments if record.reference_kind is ReferenceKind.EXACT
    }
    assert equipment_mappings._VARIANT_SENSOR_EQUIPMENT == {
        record.equipment_name for record in sensor_attachments if record.reference_kind is ReferenceKind.VARIANT
    }


def test_functional_source_declarations_reject_duplicates_before_indexing() -> None:
    equipment_mappings._checked_functional_source_key(
        "synthetic-test",
        "target",
        WeaponModeledRole.MELEE,
    )
    with pytest.raises(
        EquipmentMappingError,
        match="Duplicate synthetic-test functional-source declaration",
    ):
        equipment_mappings._checked_functional_source_key(
            "synthetic-test",
            "target",
            WeaponModeledRole.MELEE,
        )


def test_weapon_role_contract_rejects_category_and_domain_shortcuts() -> None:
    with pytest.raises(
        EquipmentMappingError,
        match="air_defense_missile.*category 'RIFLE'",
    ):
        WeaponAttachmentMapping(
            equipment_name="False SAM",
            weapon_id="rifle",
            expected_weapon_category=WeaponCategory.RIFLE,
            modeled_role=WeaponModeledRole.AIR_DEFENSE_MISSILE,
            required_target_domains=(Domain.AERIAL,),
        )

    with pytest.raises(
        EquipmentMappingError,
        match=("ground_direct_fire.*requires one exact target-domain profile.*GROUND.*AERIAL"),
    ):
        WeaponAttachmentMapping(
            equipment_name="False Ground Gun",
            weapon_id="gun",
            expected_weapon_category=WeaponCategory.CANNON,
            modeled_role=WeaponModeledRole.GROUND_DIRECT_FIRE,
            required_target_domains=(Domain.AERIAL,),
        )


def test_sensor_role_contract_rejects_unrelated_detection_interface() -> None:
    with pytest.raises(
        EquipmentMappingError,
        match="radar_warning_esm.*ESM/ELECTROMAGNETIC.*RADAR/RADAR",
    ):
        SensorAttachmentMapping(
            equipment_name="False ESM",
            sensor_id="radar",
            expected_sensor_type=SensorType.RADAR,
            expected_signature_domain=SignatureDomain.RADAR,
            modeled_role=SensorModeledRole.RADAR_WARNING_ESM,
            compatible_weapon_roles=(),
            required_target_domains=required_domains_for_sensor_role(
                SensorModeledRole.RADAR_WARNING_ESM,
            ),
        )


def test_sensor_catalog_target_domains_cannot_be_broadened_by_mapping() -> None:
    definition = _unit_definition(
        "observer",
        (("Ground Sight", "SENSOR"),),
    )
    with pytest.raises(
        EquipmentMappingError,
        match="sensor target 'visual'.*lacks required target domains.*GROUND",
    ):
        _builder(
            definitions=(definition,),
            records=(
                SensorAttachmentMapping(
                    equipment_name="Ground Sight",
                    sensor_id="visual",
                    expected_sensor_type=SensorType.VISUAL,
                    expected_signature_domain=SignatureDomain.VISUAL,
                    modeled_role=SensorModeledRole.GROUND_VISUAL_SIGHT,
                    compatible_weapon_roles=(),
                    required_target_domains=(Domain.GROUND,),
                ),
            ),
            sensors=(
                _sensor(
                    "visual",
                    target_domains=["AERIAL"],
                ),
            ),
        )


def test_registry_rejects_conflicting_roles_for_one_target() -> None:
    direct_fire = _weapon_mapping("Ground Mount", "shared-gun")
    air_defense = _weapon_mapping(
        "Air-Defense Mount",
        "shared-gun",
        modeled_role=WeaponModeledRole.AIR_DEFENSE_GUN,
        target_domains=(Domain.AERIAL,),
    )
    with pytest.raises(
        EquipmentMappingError,
        match="shared-gun.*conflicting modeled roles",
    ):
        EquipmentMappingRegistry((direct_fire, air_defense))


@pytest.mark.parametrize(
    ("sensor_type", "expected_domain"),
    (
        (SensorType.VISUAL, SignatureDomain.VISUAL),
        (SensorType.NVG, SignatureDomain.VISUAL),
        (SensorType.THERMAL, SignatureDomain.THERMAL),
        (SensorType.RADAR, SignatureDomain.RADAR),
        (SensorType.ACTIVE_SONAR, SignatureDomain.ACOUSTIC),
        (SensorType.ESM, SignatureDomain.ELECTROMAGNETIC),
    ),
)
def test_authoritative_sensor_domain_function(
    sensor_type: SensorType,
    expected_domain: SignatureDomain,
) -> None:
    assert signature_domain_for_sensor_type(sensor_type) is expected_domain


def test_unimplemented_sensor_type_fails_instead_of_silently_skipping() -> None:
    with pytest.raises(ValueError, match="SEISMIC.*no production"):
        signature_domain_for_sensor_type(SensorType.SEISMIC)
    suite = SensorSuite(
        [
            SensorInstance(_sensor("seismic", sensor_type="SEISMIC")),
        ]
    )
    with pytest.raises(ValueError, match="SEISMIC.*no production"):
        suite.best_sensor_for(SignatureDomain.ACOUSTIC)


def test_builds_typed_ordered_loadout_with_store_and_non_runtime_outcomes() -> None:
    definition = _unit_definition(
        "armed",
        (
            ("Short Gun", "WEAPON"),
            ("Long Gun", "WEAPON"),
            ("Long Gun Store", "WEAPON"),
            ("Jammer", "WEAPON"),
            ("Eyes", "SENSOR"),
        ),
    )
    short_definition = _weapon("short", max_range_m=500.0)
    long_definition = _weapon(
        "long",
        max_range_m=2_000.0,
        target_domains=["GROUND", "AERIAL"],
    )
    builder = _builder(
        definitions=(definition,),
        records=(
            _weapon_mapping("Short Gun", "short"),
            _weapon_mapping("Long Gun", "long"),
            WeaponStoreMapping(
                equipment_name="Long Gun Store",
                ammo_id="long_ammo",
                compatible_weapon_ids=("long",),
                expected_ammo_type=AmmoType.HE,
            ),
            WeaponNonRuntimeMapping(
                equipment_name="Jammer",
                reason="EW effects are outside this boundary",
            ),
            _sensor_mapping(),
        ),
        weapons=(short_definition, long_definition),
        ammunition=(
            _ammo("short_ammo"),
            _ammo("long_ammo"),
        ),
        sensors=(_sensor("visual"),),
    )

    unit = _runtime_unit(definition)
    loadouts = builder.build((unit,))
    attachments = loadouts.unit_weapons[unit.entity_id]
    assert [attachment.weapon.weapon_id for attachment in attachments] == [
        "long",
        "short",
    ]
    assert attachments[0].source_equipment is unit.equipment[1]
    assert loadouts.unit_sensors[unit.entity_id][0].equipment is unit.equipment[4]
    assert attachments[0].weapon.ammo_state.rounds_by_type == {
        "long_ammo": 4,
    }
    assert attachments[0].weapon.definition.target_domains == ["GROUND"]
    assert attachments[0].weapon.definition.effective_target_domains() == {
        "GROUND",
    }
    # The mapping-owned live envelope cannot mutate the shared catalog model.
    assert long_definition.target_domains == ["GROUND", "AERIAL"]
    assert long_definition.effective_target_domains() == {
        "GROUND",
        "AERIAL",
    }
    assert [resolution.disposition for resolution in loadouts.resolutions[unit.entity_id]] == [
        ResolutionDisposition.ATTACHMENT,
        ResolutionDisposition.ATTACHMENT,
        ResolutionDisposition.STORE,
        ResolutionDisposition.NON_RUNTIME,
        ResolutionDisposition.ATTACHMENT,
    ]
    store = loadouts.resolutions[unit.entity_id][2]
    assert store.attached_to_equipment_index == 1
    assert store.attached_to_target_id == "long"
    assert len(builder.fingerprint()) == 64
    assert builder.topology(loadouts) == loadouts.topology()
    assert len(loadouts.topology_fingerprint()) == 64


def test_two_units_get_independent_live_weapon_and_ammunition_state() -> None:
    definition = _unit_definition(
        "armed",
        (("Gun", "WEAPON"), ("Eyes", "SENSOR")),
    )
    builder = _builder(
        definitions=(definition,),
        records=(_weapon_mapping("Gun", "gun"), _sensor_mapping()),
        weapons=(_weapon("gun"),),
        ammunition=(_ammo("gun_ammo"),),
        sensors=(_sensor("visual"),),
    )
    first = _runtime_unit(definition, "first")
    second = _runtime_unit(definition, "second")
    loadouts = builder.build((first, second))
    first_weapon = loadouts.weapons["first"][0].weapon
    second_weapon = loadouts.weapons["second"][0].weapon
    assert first_weapon is not second_weapon
    assert first_weapon.equipment is first.equipment[0]
    assert second_weapon.equipment is second.equipment[0]
    assert first_weapon.fire("gun_ammo")
    assert first_weapon.ammo_state.available("gun_ammo") == 3
    assert second_weapon.ammo_state.available("gun_ammo") == 4


@pytest.mark.parametrize(
    ("compatible_ammo", "expected"),
    (
        ([], "must not be empty"),
        (["missing"], "references missing ammunition 'missing'"),
        (["round", "round"], "contains duplicate values"),
    ),
)
def test_strict_ammunition_resolution_rejects_every_invalid_reference(
    compatible_ammo: list[str],
    expected: str,
) -> None:
    definition = _unit_definition(
        "armed",
        (("Gun", "WEAPON"), ("Eyes", "SENSOR")),
    )
    with pytest.raises(EquipmentMappingError, match=expected):
        _builder(
            definitions=(definition,),
            records=(_weapon_mapping("Gun", "gun"), _sensor_mapping()),
            weapons=(_weapon("gun", compatible_ammo=compatible_ammo),),
            ammunition=(_ammo("round"),),
            sensors=(_sensor("visual"),),
        )


def test_mapping_ammunition_envelope_is_strict_runtime_state() -> None:
    definition = _unit_definition(
        "armed",
        (("Gun", "WEAPON"), ("Eyes", "SENSOR")),
    )
    catalog_definition = _weapon(
        "gun",
        compatible_ammo=["he_round", "ap_round"],
    )
    builder = _builder(
        definitions=(definition,),
        records=(
            _weapon_mapping(
                "Gun",
                "gun",
                allowed_ammo_ids=("ap_round",),
            ),
            _sensor_mapping(),
        ),
        weapons=(catalog_definition,),
        ammunition=(_ammo("he_round"), _ammo("ap_round", ammo_type="AP")),
        sensors=(_sensor("visual"),),
    )

    attachment = builder.build((_runtime_unit(definition),)).weapons["unit-1"][0]

    assert attachment.weapon.definition.compatible_ammo == ["ap_round"]
    assert [ammo.ammo_id for ammo in attachment.ammunition] == ["ap_round"]
    assert attachment.weapon.ammo_state.rounds_by_type == {"ap_round": 4}
    assert attachment.weapon.can_fire("he_round") is False
    assert attachment.weapon.fire("ap_round") is True
    assert catalog_definition.compatible_ammo == ["he_round", "ap_round"]


def test_mapping_ammunition_envelope_rejects_invalid_declarations() -> None:
    with pytest.raises(
        EquipmentMappingError,
        match="allowed_ammo_ids contains duplicate values",
    ):
        _weapon_mapping(
            "Gun",
            "gun",
            allowed_ammo_ids=("round", "round"),
        )

    definition = _unit_definition(
        "armed",
        (("Gun", "WEAPON"), ("Eyes", "SENSOR")),
    )
    with pytest.raises(
        EquipmentMappingError,
        match="does not declare mapping-allowed ammunition.*missing",
    ):
        _builder(
            definitions=(definition,),
            records=(
                _weapon_mapping(
                    "Gun",
                    "gun",
                    allowed_ammo_ids=("missing",),
                ),
                _sensor_mapping(),
            ),
            weapons=(_weapon("gun", compatible_ammo=["round"]),),
            ammunition=(_ammo("round"),),
            sensors=(_sensor("visual"),),
        )

    # Selection cannot conceal a broken catalog reference: every compatible
    # ammunition ID is still resolved before the live envelope is narrowed.
    with pytest.raises(
        EquipmentMappingError,
        match="references missing ammunition 'missing'",
    ):
        _builder(
            definitions=(definition,),
            records=(
                _weapon_mapping(
                    "Gun",
                    "gun",
                    allowed_ammo_ids=("round",),
                ),
                _sensor_mapping(),
            ),
            weapons=(_weapon("gun", compatible_ammo=["round", "missing"]),),
            ammunition=(_ammo("round"),),
            sensors=(_sensor("visual"),),
        )


def test_zero_capacity_weapon_is_not_accepted_as_usable() -> None:
    definition = _unit_definition(
        "armed",
        (("Gun", "WEAPON"), ("Eyes", "SENSOR")),
    )
    with pytest.raises(
        EquipmentMappingError,
        match=r"unit_type 'armed'.*'Gun'.*no usable magazine capacity",
    ):
        _builder(
            definitions=(definition,),
            records=(_weapon_mapping("Gun", "gun"), _sensor_mapping()),
            weapons=(_weapon("gun", magazine_capacity=0),),
            ammunition=(_ammo("gun_ammo"),),
            sensors=(_sensor("visual"),),
        )


def test_weapon_semantic_constraints_are_enforced() -> None:
    definition = _unit_definition(
        "armed",
        (("Gun", "WEAPON"), ("Eyes", "SENSOR")),
    )
    record = WeaponAttachmentMapping(
        equipment_name="Gun",
        weapon_id="gun",
        expected_weapon_category=WeaponCategory.MISSILE_LAUNCHER,
        modeled_role=WeaponModeledRole.AIR_DEFENSE_MISSILE,
        expected_guidance=GuidanceType.IR,
        required_ammo_types=(AmmoType.MISSILE,),
        required_target_domains=(Domain.AERIAL,),
        expected_caliber_mm=70.0,
    )
    with pytest.raises(
        EquipmentMappingError,
        match=r"'Gun'.*category CANNON.*MISSILE_LAUNCHER",
    ):
        _builder(
            definitions=(definition,),
            records=(record, _sensor_mapping()),
            weapons=(_weapon("gun"),),
            ammunition=(_ammo("gun_ammo"),),
            sensors=(_sensor("visual"),),
        )


def test_sensor_metadata_must_match_authoritative_production_dispatch() -> None:
    definition = _unit_definition(
        "observer",
        (("Radar", "SENSOR"),),
    )
    record = SensorAttachmentMapping(
        equipment_name="Radar",
        sensor_id="radar",
        expected_sensor_type=SensorType.RADAR,
        expected_signature_domain=SignatureDomain.RADAR,
        modeled_role=SensorModeledRole.FIRE_CONTROL_RADAR,
        compatible_weapon_roles=(),
        required_target_domains=required_domains_for_sensor_role(
            SensorModeledRole.FIRE_CONTROL_RADAR,
        ),
    )
    with pytest.raises(
        EquipmentMappingError,
        match=r"authored detects_domain.*VISUAL.*production dispatch RADAR",
    ):
        _builder(
            definitions=(definition,),
            records=(record,),
            sensors=(
                _sensor(
                    "radar",
                    sensor_type="RADAR",
                    detects_domain=["VISUAL"],
                ),
            ),
        )


def test_required_sensor_policy_rejects_non_runtime_only_mapping() -> None:
    definition = _unit_definition(
        "observer",
        (("Unmodeled Sensor", "SENSOR"),),
    )
    with pytest.raises(
        EquipmentMappingError,
        match="sensor_policy='required'.*no live sensor",
    ):
        _builder(
            definitions=(definition,),
            records=(
                SensorNonRuntimeMapping(
                    equipment_name="Unmodeled Sensor",
                    reason="No modeled detection interface",
                ),
            ),
        )


def test_intentionally_sensorless_unit_builds_explicit_empty_entries() -> None:
    definition = _unit_definition(
        "civilian",
        (),
        sensor_policy=SensorPolicy.INTENTIONALLY_NONE,
        sensor_policy_reason="Civilian noncombatant has no modeled observer",
    )
    builder = _builder(definitions=(definition,), records=())
    loadouts = builder.build((_runtime_unit(definition),))
    assert loadouts.unit_weapons["unit-1"] == ()
    assert loadouts.unit_sensors["unit-1"] == ()
    assert loadouts.equipment_resolutions["unit-1"] == ()


def test_unsupported_and_unmapped_equipment_fail_with_unit_context() -> None:
    definition = _unit_definition(
        "observer",
        (("Mystery", "SENSOR"),),
    )
    with pytest.raises(
        UnsupportedEquipmentError,
        match=r"unit_type 'observer'.*'Mystery'.*explicitly unsupported",
    ):
        _builder(
            definitions=(definition,),
            records=(
                SensorUnsupportedMapping(
                    equipment_name="Mystery",
                    reason="No defensible production target",
                ),
            ),
        )
    with pytest.raises(
        EquipmentMappingError,
        match=r"unit_type 'observer'.*'Mystery'.*no mapping",
    ):
        _builder(definitions=(definition,), records=())


def test_store_requires_exactly_one_compatible_same_unit_attachment() -> None:
    definition = _unit_definition(
        "armed",
        (
            ("Gun A", "WEAPON"),
            ("Gun B", "WEAPON"),
            ("Store", "WEAPON"),
            ("Eyes", "SENSOR"),
        ),
    )
    with pytest.raises(
        EquipmentMappingError,
        match=r"'Store'.*ambiguously matches.*\[0, 1\]",
    ):
        _builder(
            definitions=(definition,),
            records=(
                _weapon_mapping("Gun A", "gun"),
                _weapon_mapping("Gun B", "gun"),
                WeaponStoreMapping(
                    equipment_name="Store",
                    ammo_id="gun_ammo",
                    compatible_weapon_ids=("gun",),
                ),
                _sensor_mapping(),
            ),
            weapons=(_weapon("gun"),),
            ammunition=(_ammo("gun_ammo"),),
            sensors=(_sensor("visual"),),
        )


def test_typed_assignments_reject_duplicates_stale_and_identity_changes() -> None:
    definition = _unit_definition(
        "armed",
        (("Gun", "WEAPON"), ("Eyes", "SENSOR")),
    )
    common = {
        "definitions": (definition,),
        "records": (_weapon_mapping("Gun", "gun"), _sensor_mapping()),
        "weapons": (_weapon("gun"), _weapon("other")),
        "ammunition": (_ammo("gun_ammo"), _ammo("other_ammo")),
        "sensors": (_sensor("visual"),),
    }
    with pytest.raises(EquipmentMappingError, match="Duplicate weapon assignment"):
        _builder(
            **common,
            assignments=(
                WeaponAssignment("Gun", "gun"),
                WeaponAssignment("Gun", "gun"),
            ),
        )
    with pytest.raises(EquipmentMappingError, match="do not name reachable"):
        _builder(**common, assignments={"Stale": "gun"})
    with pytest.raises(
        EquipmentMappingError,
        match="contradicts the registry identity/role contract",
    ):
        _builder(**common, assignments={"Gun": "other"})


def test_functional_analogue_override_is_limited_to_explicit_allowed_set() -> None:
    definition = _unit_definition(
        "armed",
        (("Role Gun", "WEAPON"), ("Eyes", "SENSOR")),
    )
    record = WeaponAttachmentMapping(
        equipment_name="Role Gun",
        weapon_id="gun-a",
        expected_weapon_category=WeaponCategory.CANNON,
        modeled_role=WeaponModeledRole.GROUND_DIRECT_FIRE,
        required_target_domains=(Domain.GROUND,),
        expected_caliber_mm=20.0,
        reference_kind=ReferenceKind.FUNCTIONAL_ANALOGUE,
        allowed_target_ids=("gun-a", "gun-b"),
        rationale="Both targets implement the same modeled cannon role",
        source="Synthetic test source",
    )
    builder = _builder(
        definitions=(definition,),
        records=(record, _sensor_mapping()),
        weapons=(_weapon("gun-a"), _weapon("gun-b")),
        ammunition=(_ammo("gun-a_ammo"), _ammo("gun-b_ammo")),
        sensors=(_sensor("visual"),),
        assignments={"Role Gun": "gun-b"},
    )
    loadouts = builder.build((_runtime_unit(definition),))
    assert loadouts.weapons["unit-1"][0].weapon.weapon_id == "gun-b"


@pytest.mark.parametrize(
    ("era_config", "weapon_guidance", "ammo_guidance", "expected"),
    (
        (
            EraConfig(era=Era.WW2, disabled_modules={"pgm"}),
            "IR",
            "NONE",
            "feature 'pgm'.*weapon 'gun'.*IR",
        ),
        (
            EraConfig(era=Era.WW2, disabled_modules={"gps"}),
            "NONE",
            "GPS",
            "feature 'gps'.*ammunition 'gun_ammo'.*GPS",
        ),
    ),
)
def test_weapon_era_gates_are_part_of_preflight(
    era_config: EraConfig,
    weapon_guidance: str,
    ammo_guidance: str,
    expected: str,
) -> None:
    definition = _unit_definition(
        "armed",
        (("Gun", "WEAPON"), ("Eyes", "SENSOR")),
    )
    with pytest.raises(EquipmentMappingError, match=expected):
        _builder(
            definitions=(definition,),
            records=(_weapon_mapping("Gun", "gun"), _sensor_mapping()),
            weapons=(_weapon("gun", guidance=weapon_guidance),),
            ammunition=(_ammo("gun_ammo", guidance=ammo_guidance),),
            sensors=(_sensor("visual"),),
            era_config=era_config,
        )


def test_sensor_and_data_link_era_gates_are_part_of_preflight() -> None:
    definition = _unit_definition(
        "observer",
        (("Thermal", "SENSOR"),),
        data_link_range=1_000.0,
    )
    record = SensorAttachmentMapping(
        equipment_name="Thermal",
        sensor_id="thermal",
        expected_sensor_type=SensorType.THERMAL,
        expected_signature_domain=SignatureDomain.THERMAL,
        modeled_role=SensorModeledRole.THERMAL_TARGETING,
        compatible_weapon_roles=(),
        required_target_domains=required_domains_for_sensor_role(
            SensorModeledRole.THERMAL_TARGETING,
        ),
    )
    era_config = EraConfig(
        disabled_modules={"thermal_sights", "data_links"},
        available_sensor_types={"VISUAL"},
    )
    with pytest.raises(
        EquipmentMappingError,
        match="feature 'data_links' is disabled",
    ):
        _builder(
            definitions=(definition,),
            records=(record,),
            sensors=(_sensor("thermal", sensor_type="THERMAL"),),
            era_config=era_config,
        )


def test_builder_rejects_duplicate_empty_and_drifted_runtime_topology() -> None:
    definition = _unit_definition(
        "observer",
        (("Eyes", "SENSOR"),),
    )
    builder = _builder(
        definitions=(definition,),
        records=(_sensor_mapping(),),
        sensors=(_sensor("visual"),),
    )
    first = _runtime_unit(definition, "duplicate")
    second = _runtime_unit(definition, "duplicate")
    with pytest.raises(EquipmentMappingError, match="Duplicate unit ID"):
        builder.build((first, second))
    empty = _runtime_unit(definition, " ")
    with pytest.raises(EquipmentMappingError, match="empty unit ID"):
        builder.build((empty,))
    drifted = _runtime_unit(definition)
    drifted.equipment[0].name = "Different"
    with pytest.raises(
        EquipmentMappingError,
        match="does not match effective authored topology",
    ):
        builder.build((drifted,))


def test_fingerprint_is_canonical_and_changes_with_reachable_contract() -> None:
    definition = _unit_definition(
        "observer",
        (("Eyes", "SENSOR"),),
    )
    common = {
        "definitions": (definition,),
        "records": (_sensor_mapping(),),
        "sensors": (_sensor("visual"),),
    }
    assert _builder(**common).fingerprint() == _builder(**common).fingerprint()

    changed_equipment = definition.model_copy(deep=True)
    changed_equipment.equipment[0].reliability = 0.94
    assert (
        _builder(
            definitions=(changed_equipment,),
            records=common["records"],
            sensors=common["sensors"],
        ).fingerprint()
        != _builder(**common).fingerprint()
    )

    changed_domain = definition.model_copy(
        update={"domain": "aerial"},
        deep=True,
    )
    assert (
        _builder(
            definitions=(changed_domain,),
            records=common["records"],
            sensors=common["sensors"],
        ).fingerprint()
        != _builder(**common).fingerprint()
    )

    changed = _builder(
        definitions=(definition,),
        records=(
            SensorAttachmentMapping(
                equipment_name="Eyes",
                sensor_id="other-visual",
                expected_sensor_type=SensorType.VISUAL,
                expected_signature_domain=SignatureDomain.VISUAL,
                modeled_role=SensorModeledRole.VISUAL_OBSERVATION,
                compatible_weapon_roles=(),
                required_target_domains=required_domains_for_sensor_role(
                    SensorModeledRole.VISUAL_OBSERVATION,
                ),
            ),
        ),
        sensors=(_sensor("other-visual"),),
    )
    assert changed.fingerprint() != _builder(**common).fingerprint()

    armed = _unit_definition(
        "armed",
        (("Gun", "WEAPON"), ("Eyes", "SENSOR")),
    )
    ammunition_common = {
        "definitions": (armed,),
        "weapons": (_weapon("gun", compatible_ammo=["he_round", "ap_round"]),),
        "ammunition": (_ammo("he_round"), _ammo("ap_round", ammo_type="AP")),
        "sensors": (_sensor("visual"),),
    }
    he_only = _builder(
        **ammunition_common,
        records=(
            _weapon_mapping(
                "Gun",
                "gun",
                allowed_ammo_ids=("he_round",),
            ),
            _sensor_mapping(),
        ),
    )
    ap_only = _builder(
        **ammunition_common,
        records=(
            _weapon_mapping(
                "Gun",
                "gun",
                allowed_ammo_ids=("ap_round",),
            ),
            _sensor_mapping(),
        ),
    )
    assert he_only.fingerprint() != ap_only.fingerprint()


def test_system_count_changes_fingerprint_topology_and_live_outcome_fields() -> None:
    definition = _unit_definition(
        "composite-battery",
        (("Composite Battery", "WEAPON"), ("Eyes", "SENSOR")),
    )
    ammunition = _ammo("gun_ammo")
    weapon = _weapon(
        "gun",
        magazine_capacity=4,
        rate_of_fire_rpm=6.0,
        barrel_life_rounds=100,
    )

    def counted_mapping(source_system_count: int) -> WeaponAttachmentMapping:
        return WeaponAttachmentMapping(
            equipment_name="Composite Battery",
            weapon_id="gun",
            expected_weapon_category=WeaponCategory.CANNON,
            modeled_role=WeaponModeledRole.GROUND_DIRECT_FIRE,
            required_target_domains=(Domain.GROUND,),
            source_system_count=source_system_count,
            target_system_count=1,
        )

    common = {
        "definitions": (definition,),
        "weapons": (weapon,),
        "ammunition": (ammunition,),
        "sensors": (_sensor("visual"),),
    }
    pair_builder = _builder(
        **common,
        records=(counted_mapping(2), _sensor_mapping()),
    )
    quartet_builder = _builder(
        **common,
        records=(counted_mapping(4), _sensor_mapping()),
    )
    pair = pair_builder.build((_runtime_unit(definition, "pair"),))
    quartet = quartet_builder.build((_runtime_unit(definition, "quartet"),))
    pair_attachment = pair.unit_weapons["pair"][0]
    quartet_attachment = quartet.unit_weapons["quartet"][0]

    assert pair_builder.fingerprint() != quartet_builder.fingerprint()
    assert pair_attachment.runtime_system_multiplier == 2
    assert quartet_attachment.runtime_system_multiplier == 4
    assert (
        pair_attachment.weapon.definition.rate_of_fire_rpm,
        pair_attachment.weapon.definition.burst_size,
        pair_attachment.weapon.definition.magazine_capacity,
        pair_attachment.weapon.definition.barrel_life_rounds,
    ) == (12.0, 1, 8, 200)
    assert (
        quartet_attachment.weapon.definition.rate_of_fire_rpm,
        quartet_attachment.weapon.definition.burst_size,
        quartet_attachment.weapon.definition.magazine_capacity,
        quartet_attachment.weapon.definition.barrel_life_rounds,
    ) == (24.0, 1, 16, 400)
    assert pair.topology()["pair"][0]["source_system_count"] == 2
    assert quartet.topology()["quartet"][0]["source_system_count"] == 4
    assert pair.topology_fingerprint() != quartet.topology_fingerprint()


@pytest.mark.parametrize(
    ("modeled_max_range_m", "modeled_fov_deg"),
    (
        (None, None),
        (1_000.0, None),
        (None, 90.0),
    ),
)
def test_functional_sensor_analogue_requires_consumed_range_and_fov_envelope(
    modeled_max_range_m: float | None,
    modeled_fov_deg: float | None,
) -> None:
    with pytest.raises(
        EquipmentMappingError,
        match=("Functional sensor analogues require.*modeled_max_range_m.*modeled_fov_deg"),
    ):
        SensorAttachmentMapping(
            equipment_name="Role Sensor",
            sensor_id="broad-visual",
            expected_sensor_type=SensorType.VISUAL,
            expected_signature_domain=SignatureDomain.VISUAL,
            modeled_role=SensorModeledRole.GROUND_VISUAL_SIGHT,
            compatible_weapon_roles=(),
            required_target_domains=required_domains_for_sensor_role(
                SensorModeledRole.GROUND_VISUAL_SIGHT,
            ),
            modeled_max_range_m=modeled_max_range_m,
            modeled_fov_deg=modeled_fov_deg,
            reference_kind=ReferenceKind.FUNCTIONAL_ANALOGUE,
            allowed_target_ids=("broad-visual",),
            rationale="Bounded ground-observation role model.",
            source="Phase 109 focused semantic proof.",
        )


def test_functional_sensor_envelope_changes_live_definition_and_fingerprint() -> None:
    definition = _unit_definition(
        "observer",
        (("Role Sensor", "SENSOR"),),
    )
    catalog_sensor = SensorDefinition(
        sensor_id="broad-visual",
        sensor_type="VISUAL",
        display_name="Broad visual catalog target",
        max_range_m=2_000.0,
        detection_threshold=1.0,
        fov_deg=360.0,
        detects_domain=["VISUAL"],
    )

    def build_for(
        *,
        modeled_max_range_m: float,
        modeled_fov_deg: float,
    ) -> RuntimeLoadoutBuilder:
        record = SensorAttachmentMapping(
            equipment_name="Role Sensor",
            sensor_id="broad-visual",
            expected_sensor_type=SensorType.VISUAL,
            expected_signature_domain=SignatureDomain.VISUAL,
            modeled_role=SensorModeledRole.GROUND_VISUAL_SIGHT,
            compatible_weapon_roles=(),
            required_target_domains=required_domains_for_sensor_role(
                SensorModeledRole.GROUND_VISUAL_SIGHT,
            ),
            modeled_max_range_m=modeled_max_range_m,
            modeled_fov_deg=modeled_fov_deg,
            reference_kind=ReferenceKind.FUNCTIONAL_ANALOGUE,
            allowed_target_ids=("broad-visual",),
            rationale="Bounded ground-observation role model.",
            source="Phase 109 focused semantic proof.",
        )
        return _builder(
            definitions=(definition,),
            records=(record,),
            sensors=(catalog_sensor,),
        )

    narrowed_builder = build_for(
        modeled_max_range_m=1_000.0,
        modeled_fov_deg=90.0,
    )
    runtime_unit = _runtime_unit(definition)
    runtime_loadouts = narrowed_builder.build((runtime_unit,))
    live_sensor = runtime_loadouts.unit_sensors[runtime_unit.entity_id][0]

    assert live_sensor.definition.max_range_m == 1_000.0
    assert live_sensor.definition.fov_deg == 90.0
    assert live_sensor.definition.target_domains == ["GROUND"]
    assert catalog_sensor.max_range_m == 2_000.0
    assert catalog_sensor.fov_deg == 360.0
    assert (
        narrowed_builder.fingerprint()
        != build_for(
            modeled_max_range_m=900.0,
            modeled_fov_deg=90.0,
        ).fingerprint()
    )
    assert (
        narrowed_builder.fingerprint()
        != build_for(
            modeled_max_range_m=1_000.0,
            modeled_fov_deg=80.0,
        ).fingerprint()
    )
