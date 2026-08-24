"""Focused Phase 115 proofs for typed runtime loadout bindings."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from stochastic_warfare.combat.ammunition import (
    AmmoDefinition,
    AmmoLoader,
    WeaponCategory,
    WeaponDefinition,
    WeaponLoader,
)
from stochastic_warfare.core.era import EraConfig
from stochastic_warfare.core.types import Domain, Position
from stochastic_warfare.detection.sensors import (
    SensorDefinition,
    SensorLoader,
    SensorType,
)
from stochastic_warfare.detection.signatures import SignatureDomain
from stochastic_warfare.entities.base import Unit
from stochastic_warfare.entities.equipment import (
    EquipmentCategory,
    EquipmentItem,
)
from stochastic_warfare.entities.loader import (
    EquipmentEntry,
    SensorPolicy,
    UnitDefinition,
)
from stochastic_warfare.simulation.equipment_mappings import (
    EQUIPMENT_MAPPING_RECORDS,
    EQUIPMENT_MAPPING_REGISTRY,
)
from stochastic_warfare.simulation.loadouts import (
    EquipmentMappingError,
    EquipmentMappingRegistry,
    ReferenceKind,
    ResolutionDisposition,
    RuntimeLoadoutBuilder,
    RuntimeLoadouts,
    SensorAttachmentMapping,
    SensorModeledRole,
    SensorTargetingClass,
    WeaponAttachmentMapping,
    WeaponModeledRole,
    WeaponStandoffClass,
    allowed_shooter_domains_for_sensor_role,
    compatible_sensor_roles_for_weapon_role,
    required_domains_for_sensor_role,
    required_domains_for_weapon_role,
    sensor_targeting_class,
    weapon_standoff_class,
)


def _duplicate_binding_builder() -> tuple[RuntimeLoadoutBuilder, Unit]:
    weapon = WeaponDefinition(
        weapon_id="direct-gun",
        display_name="Direct gun",
        category="CANNON",
        caliber_mm=20.0,
        max_range_m=1_000.0,
        effective_range_m=800.0,
        rate_of_fire_rpm=10.0,
        magazine_capacity=5,
        compatible_ammo=["direct-round"],
        target_domains=["GROUND"],
    )
    ammunition = AmmoDefinition(
        ammo_id="direct-round",
        display_name="Direct round",
        ammo_type="HE",
    )
    sensor = SensorDefinition(
        sensor_id="ground-sight",
        sensor_type="VISUAL",
        display_name="Ground sight",
        max_range_m=900.0,
        detection_threshold=1.0,
        fov_deg=30.0,
        detects_domain=["VISUAL"],
        target_domains=["GROUND"],
    )

    weapon_loader = WeaponLoader(Path("."))
    ammunition_loader = AmmoLoader(Path("."))
    sensor_loader = SensorLoader(Path("."))
    weapon_loader._definitions[weapon.weapon_id] = weapon
    ammunition_loader._definitions[ammunition.ammo_id] = ammunition
    sensor_loader._definitions[sensor.sensor_id] = sensor

    definition = UnitDefinition(
        unit_type="duplicate-bindings",
        domain="ground",
        ground_type="LIGHT_INFANTRY",
        display_name="Duplicate bindings",
        max_speed=1.0,
        crew=[],
        equipment=[
            EquipmentEntry(name="Twin Gun", category="WEAPON"),
            EquipmentEntry(name="Shared Sight", category="SENSOR"),
            EquipmentEntry(name="Twin Gun", category="WEAPON"),
            EquipmentEntry(name="Shared Sight", category="SENSOR"),
        ],
        sensor_policy=SensorPolicy.REQUIRED,
    )
    unit = Unit(
        entity_id="duplicate-unit",
        position=Position(0.0, 0.0),
        unit_type=definition.unit_type,
        equipment=[
            EquipmentItem(
                equipment_id=f"duplicate-equipment-{index}",
                name=entry.name,
                category=EquipmentCategory[entry.category],
            )
            for index, entry in enumerate(definition.equipment)
        ],
    )
    registry = EquipmentMappingRegistry(
        (
            WeaponAttachmentMapping(
                equipment_name="Twin Gun",
                weapon_id=weapon.weapon_id,
                expected_weapon_category=WeaponCategory.CANNON,
                modeled_role=WeaponModeledRole.GROUND_DIRECT_FIRE,
                required_target_domains=(Domain.GROUND,),
            ),
            SensorAttachmentMapping(
                equipment_name="Shared Sight",
                sensor_id=sensor.sensor_id,
                expected_sensor_type=SensorType.VISUAL,
                expected_signature_domain=SignatureDomain.VISUAL,
                modeled_role=SensorModeledRole.GROUND_VISUAL_SIGHT,
                compatible_weapon_roles=(WeaponModeledRole.GROUND_DIRECT_FIRE,),
                required_target_domains=required_domains_for_sensor_role(
                    SensorModeledRole.GROUND_VISUAL_SIGHT,
                ),
            ),
        )
    )
    builder = RuntimeLoadoutBuilder(
        weapon_loader=weapon_loader,
        ammo_loader=ammunition_loader,
        sensor_loader=sensor_loader,
        unit_definitions={definition.unit_type: definition},
        era_config=EraConfig(),
        assignment_overrides=(),
        reachable_unit_types=(definition.unit_type,),
        registry=registry,
    )
    return builder, unit


def test_targeting_policies_are_total_and_fail_closed() -> None:
    assert len(WeaponModeledRole) == 35
    assert len(SensorModeledRole) == 38
    assert {weapon_standoff_class(role) for role in WeaponModeledRole} == set(WeaponStandoffClass)
    assert {sensor_targeting_class(role) for role in SensorModeledRole} == set(SensorTargetingClass)

    for role in WeaponModeledRole:
        compatible = compatible_sensor_roles_for_weapon_role(role)
        assert isinstance(compatible, tuple)
        assert len(compatible) == len(set(compatible))
        if weapon_standoff_class(role) is WeaponStandoffClass.UNSUPPORTED:
            assert compatible == ()

    for role in SensorModeledRole:
        shooter_domains = allowed_shooter_domains_for_sensor_role(role)
        assert shooter_domains
        assert len(shooter_domains) == len(set(shooter_domains))

    with pytest.raises(EquipmentMappingError, match="WeaponModeledRole"):
        weapon_standoff_class("ground_direct_fire")  # type: ignore[arg-type]
    with pytest.raises(EquipmentMappingError, match="SensorModeledRole"):
        sensor_targeting_class("visual_observation")  # type: ignore[arg-type]


def test_targeting_policy_oracle_is_exact_and_cartesian() -> None:
    organic_roles = frozenset(
        {
            WeaponModeledRole.GROUND_DIRECT_FIRE,
            WeaponModeledRole.ASSAULT_RIFLE,
            WeaponModeledRole.MUZZLE_LOADING_MUSKET,
            WeaponModeledRole.BOLT_ACTION_RIFLE,
            WeaponModeledRole.SEMI_AUTOMATIC_RIFLE,
            WeaponModeledRole.SNIPER_RIFLE,
            WeaponModeledRole.ANTI_MATERIEL_RIFLE,
            WeaponModeledRole.SUBMACHINE_GUN,
            WeaponModeledRole.LIGHT_MACHINE_GUN,
            WeaponModeledRole.GENERAL_PURPOSE_MACHINE_GUN,
            WeaponModeledRole.HEAVY_MACHINE_GUN,
            WeaponModeledRole.INDIVIDUAL_GRENADE_LAUNCHER,
            WeaponModeledRole.AUTOMATIC_GRENADE_LAUNCHER,
            WeaponModeledRole.ANCIENT_PROJECTILE,
            WeaponModeledRole.ANTI_ARMOR,
            WeaponModeledRole.INCENDIARY_PROJECTOR,
        }
    )
    unsupported_roles = frozenset(
        {
            WeaponModeledRole.FIELD_ARTILLERY,
            WeaponModeledRole.MORTAR_FIRE,
            WeaponModeledRole.ROCKET_ARTILLERY,
            WeaponModeledRole.HAND_GRENADE,
            WeaponModeledRole.MELEE,
            WeaponModeledRole.BOMB_DELIVERY,
            WeaponModeledRole.TORPEDO,
            WeaponModeledRole.ANTI_SUBMARINE,
        }
    )
    director_roles = frozenset(
        {
            WeaponModeledRole.AIR_DEFENSE_GUN,
            WeaponModeledRole.NAVAL_GUNFIRE,
            WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN,
            WeaponModeledRole.AIR_DEFENSE_MISSILE,
            WeaponModeledRole.AIR_TO_AIR_MISSILE,
            WeaponModeledRole.AIR_TO_GROUND_MISSILE,
            WeaponModeledRole.ANTI_SHIP_MISSILE,
            WeaponModeledRole.MULTI_ROLE_VLS,
            WeaponModeledRole.AIRCRAFT_GUN,
            WeaponModeledRole.CLOSE_IN_DEFENSE,
            WeaponModeledRole.DIRECTED_ENERGY,
        }
    )
    assert organic_roles | unsupported_roles | director_roles == set(
        WeaponModeledRole,
    )
    assert not (
        organic_roles & unsupported_roles or organic_roles & director_roles or unsupported_roles & director_roles
    )
    for role in organic_roles:
        assert weapon_standoff_class(role) is (WeaponStandoffClass.ORGANIC_DIRECT_AIM)
    for role in director_roles:
        assert weapon_standoff_class(role) is (WeaponStandoffClass.COMPATIBLE_DIRECTOR_REQUIRED)
    for role in unsupported_roles:
        assert weapon_standoff_class(role) is WeaponStandoffClass.UNSUPPORTED

    local_fire_control_roles = frozenset(
        {
            SensorModeledRole.THERMAL_TARGETING,
            SensorModeledRole.AIRBORNE_FIRE_CONTROL_RADAR,
            SensorModeledRole.AIRBORNE_GROUND_FIRE_CONTROL_RADAR,
            SensorModeledRole.AIRBORNE_MULTI_DOMAIN_FIRE_CONTROL_RADAR,
            SensorModeledRole.FIRE_CONTROL_RADAR,
            SensorModeledRole.GROUND_AIR_DEFENSE_FIRE_CONTROL_RADAR,
            SensorModeledRole.NAVAL_FIRE_CONTROL_RADAR,
            SensorModeledRole.NAVAL_AIR_DEFENSE_FIRE_CONTROL_RADAR,
            SensorModeledRole.GROUND_VISUAL_SIGHT,
            SensorModeledRole.GROUND_AIR_DEFENSE_OPTICAL_SIGHT,
            SensorModeledRole.AIRBORNE_VISUAL_SIGHT,
            SensorModeledRole.AIRBORNE_GROUND_VISUAL_TARGETING,
            SensorModeledRole.AIRBORNE_GROUND_BOMBSIGHT,
            SensorModeledRole.NAVAL_VISUAL_DIRECTOR,
            SensorModeledRole.NAVAL_AIR_DEFENSE_OPTICAL_DIRECTOR,
            SensorModeledRole.GROUND_NIGHT_SIGHT,
            SensorModeledRole.GROUND_ACTIVE_IR_SIGHT,
            SensorModeledRole.GROUND_THERMAL_TARGETING,
            SensorModeledRole.AIRBORNE_GROUND_THERMAL_TARGETING,
        }
    )
    assert set(SensorModeledRole) - local_fire_control_roles == {
        role for role in SensorModeledRole if sensor_targeting_class(role) is SensorTargetingClass.CONTACT_SEARCH_ONLY
    }
    for role in local_fire_control_roles:
        assert sensor_targeting_class(role) is (SensorTargetingClass.LOCAL_FIRE_CONTROL)

    organic_sensors = (
        SensorModeledRole.THERMAL_TARGETING,
        SensorModeledRole.FIRE_CONTROL_RADAR,
        SensorModeledRole.GROUND_VISUAL_SIGHT,
        SensorModeledRole.GROUND_NIGHT_SIGHT,
        SensorModeledRole.GROUND_ACTIVE_IR_SIGHT,
        SensorModeledRole.GROUND_THERMAL_TARGETING,
    )
    ground_air_defense_sensors = (
        SensorModeledRole.GROUND_AIR_DEFENSE_OPTICAL_SIGHT,
        SensorModeledRole.GROUND_AIR_DEFENSE_FIRE_CONTROL_RADAR,
        SensorModeledRole.FIRE_CONTROL_RADAR,
    )
    naval_gun_sensors = (
        SensorModeledRole.NAVAL_VISUAL_DIRECTOR,
        SensorModeledRole.NAVAL_FIRE_CONTROL_RADAR,
    )
    naval_air_defense_sensors = (
        SensorModeledRole.NAVAL_AIR_DEFENSE_OPTICAL_DIRECTOR,
        SensorModeledRole.NAVAL_AIR_DEFENSE_FIRE_CONTROL_RADAR,
        SensorModeledRole.NAVAL_FIRE_CONTROL_RADAR,
    )
    air_to_air_sensors = (
        SensorModeledRole.AIRBORNE_VISUAL_SIGHT,
        SensorModeledRole.AIRBORNE_FIRE_CONTROL_RADAR,
        SensorModeledRole.AIRBORNE_MULTI_DOMAIN_FIRE_CONTROL_RADAR,
    )
    air_to_ground_sensors = (
        SensorModeledRole.AIRBORNE_GROUND_VISUAL_TARGETING,
        SensorModeledRole.AIRBORNE_GROUND_THERMAL_TARGETING,
        SensorModeledRole.AIRBORNE_GROUND_FIRE_CONTROL_RADAR,
        SensorModeledRole.AIRBORNE_MULTI_DOMAIN_FIRE_CONTROL_RADAR,
    )
    aircraft_gun_sensors = (
        *air_to_air_sensors,
        SensorModeledRole.AIRBORNE_GROUND_VISUAL_TARGETING,
        SensorModeledRole.AIRBORNE_GROUND_THERMAL_TARGETING,
        SensorModeledRole.AIRBORNE_GROUND_FIRE_CONTROL_RADAR,
    )
    expected_compatibility = {
        **{role: organic_sensors for role in organic_roles},
        **{role: () for role in unsupported_roles},
        WeaponModeledRole.AIR_DEFENSE_GUN: ground_air_defense_sensors,
        WeaponModeledRole.NAVAL_GUNFIRE: naval_gun_sensors,
        WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN: naval_air_defense_sensors,
        WeaponModeledRole.AIR_DEFENSE_MISSILE: ground_air_defense_sensors,
        WeaponModeledRole.AIR_TO_AIR_MISSILE: air_to_air_sensors,
        WeaponModeledRole.AIR_TO_GROUND_MISSILE: air_to_ground_sensors,
        WeaponModeledRole.ANTI_SHIP_MISSILE: (
            SensorModeledRole.NAVAL_FIRE_CONTROL_RADAR,
            SensorModeledRole.AIRBORNE_MULTI_DOMAIN_FIRE_CONTROL_RADAR,
            SensorModeledRole.FIRE_CONTROL_RADAR,
        ),
        WeaponModeledRole.MULTI_ROLE_VLS: (
            SensorModeledRole.FIRE_CONTROL_RADAR,
            SensorModeledRole.GROUND_AIR_DEFENSE_FIRE_CONTROL_RADAR,
            SensorModeledRole.NAVAL_FIRE_CONTROL_RADAR,
            SensorModeledRole.NAVAL_AIR_DEFENSE_FIRE_CONTROL_RADAR,
        ),
        WeaponModeledRole.AIRCRAFT_GUN: aircraft_gun_sensors,
        WeaponModeledRole.CLOSE_IN_DEFENSE: naval_air_defense_sensors,
        WeaponModeledRole.DIRECTED_ENERGY: (
            SensorModeledRole.FIRE_CONTROL_RADAR,
            SensorModeledRole.GROUND_AIR_DEFENSE_FIRE_CONTROL_RADAR,
            SensorModeledRole.NAVAL_FIRE_CONTROL_RADAR,
            SensorModeledRole.NAVAL_AIR_DEFENSE_FIRE_CONTROL_RADAR,
            SensorModeledRole.GROUND_AIR_DEFENSE_OPTICAL_SIGHT,
            SensorModeledRole.NAVAL_AIR_DEFENSE_OPTICAL_DIRECTOR,
        ),
    }
    assert set(expected_compatibility) == set(WeaponModeledRole)
    for weapon_role, sensor_roles in expected_compatibility.items():
        assert (
            compatible_sensor_roles_for_weapon_role(
                weapon_role,
            )
            == sensor_roles
        )
        for sensor_role in SensorModeledRole:
            assert (
                sensor_role
                in compatible_sensor_roles_for_weapon_role(
                    weapon_role,
                )
            ) is (sensor_role in sensor_roles)


def test_ww1_optics_have_exact_roles_bindings_and_source_provenance() -> None:
    expected = {
        "Field Binoculars": (
            SensorModeledRole.VISUAL_OBSERVATION,
            (),
            "history.army.mil",
        ),
        "Barr & Stroud Rangefinder": (
            SensorModeledRole.NAVAL_VISUAL_DIRECTOR,
            (WeaponModeledRole.NAVAL_GUNFIRE,),
            "dreadnoughtproject.org",
        ),
        "Zeiss Entfernungsmesser Rangefinder": (
            SensorModeledRole.NAVAL_VISUAL_DIRECTOR,
            (WeaponModeledRole.NAVAL_GUNFIRE,),
            "zeiss.de",
        ),
        "No. 7 Dial Sight": (
            SensorModeledRole.GROUND_VISUAL_SIGHT,
            (WeaponModeledRole.FIELD_ARTILLERY,),
            "collectionswa.net.au",
        ),
        "Panoramic Sight": (
            SensorModeledRole.GROUND_VISUAL_SIGHT,
            (WeaponModeledRole.FIELD_ARTILLERY,),
            "awm.gov.au",
        ),
    }

    for equipment_name, (role, compatible_roles, source_fragment) in expected.items():
        record = EQUIPMENT_MAPPING_REGISTRY.require(
            EquipmentCategory.SENSOR,
            equipment_name,
        )
        assert isinstance(record, SensorAttachmentMapping)
        assert record.sensor_id == "binoculars_ww1"
        assert record.modeled_role is role
        assert record.compatible_weapon_roles == compatible_roles
        assert record.modeled_max_range_m == pytest.approx(3_000.0)
        assert record.reference_kind is ReferenceKind.FUNCTIONAL_ANALOGUE
        assert record.source is not None
        assert source_fragment in record.source
        assert record.rationale is not None
        assert "not asserted as a source-measured historical value" in (record.rationale)


def test_mapping_bindings_reject_search_promotion_and_unrelated_roles() -> None:
    common = {
        "equipment_name": "Invalid sensor",
        "sensor_id": "sensor",
        "expected_sensor_type": SensorType.VISUAL,
        "expected_signature_domain": SignatureDomain.VISUAL,
        "required_target_domains": required_domains_for_sensor_role(
            SensorModeledRole.VISUAL_OBSERVATION,
        ),
    }
    with pytest.raises(EquipmentMappingError, match="Contact/search-only"):
        SensorAttachmentMapping(
            **common,
            modeled_role=SensorModeledRole.VISUAL_OBSERVATION,
            compatible_weapon_roles=(WeaponModeledRole.GROUND_DIRECT_FIRE,),
        )

    with pytest.raises(EquipmentMappingError, match="cannot bind"):
        SensorAttachmentMapping(
            equipment_name="Invalid director",
            sensor_id="sensor",
            expected_sensor_type=SensorType.VISUAL,
            expected_signature_domain=SignatureDomain.VISUAL,
            modeled_role=SensorModeledRole.NAVAL_VISUAL_DIRECTOR,
            compatible_weapon_roles=(WeaponModeledRole.ASSAULT_RIFLE,),
            required_target_domains=required_domains_for_sensor_role(
                SensorModeledRole.NAVAL_VISUAL_DIRECTOR,
            ),
        )


def test_mapping_fire_control_bindings_share_a_target_domain() -> None:
    attachment_records = tuple(
        record for record in EQUIPMENT_MAPPING_RECORDS if isinstance(record, SensorAttachmentMapping)
    )
    assert attachment_records

    for record in attachment_records:
        sensor_domains = set(
            required_domains_for_sensor_role(
                record.modeled_role,
            )
        )
        for weapon_role in record.compatible_weapon_roles:
            assert sensor_domains & set(
                required_domains_for_weapon_role(
                    weapon_role,
                )
            ), (
                record.equipment_name,
                record.modeled_role,
                weapon_role,
            )

    for equipment_name in ("AN/APG-73 Radar", "AN/APG-79 AESA Radar"):
        record = EQUIPMENT_MAPPING_REGISTRY.require(
            EquipmentCategory.SENSOR,
            equipment_name,
        )
        assert isinstance(record, SensorAttachmentMapping)
        assert Domain.NAVAL in record.required_target_domains
        assert WeaponModeledRole.ANTI_SHIP_MISSILE in record.compatible_weapon_roles


def test_builder_resolves_duplicate_names_by_exact_source_identity() -> None:
    builder, unit = _duplicate_binding_builder()
    loadouts = builder.build((unit,))

    weapons = loadouts.unit_weapons[unit.entity_id]
    sensors = loadouts.unit_sensor_attachments[unit.entity_id]
    projection = loadouts.unit_sensors[unit.entity_id]

    assert tuple(item.source_equipment_index for item in weapons) == (0, 2)
    assert tuple(item.source_equipment_index for item in sensors) == (1, 3)
    assert all(item.modeled_role is WeaponModeledRole.GROUND_DIRECT_FIRE for item in weapons)
    assert all(item.modeled_role is SensorModeledRole.GROUND_VISUAL_SIGHT for item in sensors)
    assert all(item.compatible_weapon_source_indexes == (0, 2) for item in sensors)
    assert all(item.source_equipment is unit.equipment[item.source_equipment_index] for item in (*weapons, *sensors))
    assert len({id(item.weapon) for item in weapons}) == 2
    assert len({id(item.sensor) for item in sensors}) == 2
    assert len(projection) == len(sensors)
    assert all(projected is attachment.sensor for projected, attachment in zip(projection, sensors, strict=True))


def test_runtime_loadouts_rejects_forged_resolved_source_indexes() -> None:
    builder, unit = _duplicate_binding_builder()
    loadouts = builder.build((unit,))
    exact = loadouts.unit_sensor_attachments[unit.entity_id]
    forged = (
        replace(exact[0], compatible_weapon_source_indexes=(0,)),
        exact[1],
    )

    with pytest.raises(ValueError, match=r"declares resolved weapon indexes"):
        RuntimeLoadouts(
            unit_weapons=loadouts.unit_weapons,
            unit_sensor_attachments={unit.entity_id: forged},
            equipment_resolutions=loadouts.equipment_resolutions,
        )


def test_runtime_loadouts_rejects_reordered_weapon_attachments() -> None:
    builder, unit = _duplicate_binding_builder()
    loadouts = builder.build((unit,))
    reversed_weapons = tuple(reversed(loadouts.unit_weapons[unit.entity_id]))
    assert len(reversed_weapons) > 1

    with pytest.raises(ValueError, match="canonical range/source/ID order"):
        RuntimeLoadouts(
            unit_weapons={unit.entity_id: reversed_weapons},
            unit_sensor_attachments=loadouts.unit_sensor_attachments,
            equipment_resolutions=loadouts.equipment_resolutions,
        )


def test_runtime_loadouts_rejects_reordered_equipment_resolutions() -> None:
    builder, unit = _duplicate_binding_builder()
    loadouts = builder.build((unit,))
    reversed_resolutions = tuple(
        reversed(loadouts.equipment_resolutions[unit.entity_id]),
    )
    assert len(reversed_resolutions) > 1

    with pytest.raises(ValueError, match="retain source equipment order"):
        RuntimeLoadouts(
            unit_weapons=loadouts.unit_weapons,
            unit_sensor_attachments=loadouts.unit_sensor_attachments,
            equipment_resolutions={unit.entity_id: reversed_resolutions},
        )


def test_runtime_loadouts_rejects_dangling_attachment_resolution() -> None:
    builder, unit = _duplicate_binding_builder()
    loadouts = builder.build((unit,))
    sensors = loadouts.unit_sensor_attachments[unit.entity_id]
    assert len(sensors) > 1

    with pytest.raises(ValueError, match="has no exact live attachment"):
        RuntimeLoadouts(
            unit_weapons=loadouts.unit_weapons,
            unit_sensor_attachments={unit.entity_id: sensors[:-1]},
            equipment_resolutions=loadouts.equipment_resolutions,
        )


def test_equipment_resolution_rejects_forged_source_category() -> None:
    builder, unit = _duplicate_binding_builder()
    resolution = builder.build((unit,)).equipment_resolutions[unit.entity_id][0]

    with pytest.raises(ValueError, match="match the exact source equipment"):
        replace(resolution, category=EquipmentCategory.SENSOR)


@pytest.mark.parametrize("binding", ("weapon", "sensor", "resolution"))
def test_loadout_bindings_reject_boolean_source_indexes(binding: str) -> None:
    builder, unit = _duplicate_binding_builder()
    loadouts = builder.build((unit,))
    value = {
        "weapon": loadouts.unit_weapons[unit.entity_id][0],
        "sensor": loadouts.unit_sensor_attachments[unit.entity_id][0],
        "resolution": loadouts.equipment_resolutions[unit.entity_id][0],
    }[binding]

    with pytest.raises(ValueError, match="non-negative non-bool integer"):
        replace(value, source_equipment_index=True)


def test_store_resolution_rejects_boolean_attachment_index() -> None:
    builder, unit = _duplicate_binding_builder()
    resolution = builder.build((unit,)).equipment_resolutions[unit.entity_id][0]

    with pytest.raises(ValueError, match="non-negative non-bool integer"):
        replace(
            resolution,
            disposition=ResolutionDisposition.STORE,
            modeled_role=None,
            target_id="direct-round",
            attached_to_equipment_index=True,
            attached_to_target_id=resolution.target_id,
            source_system_count=None,
            target_system_count=None,
            runtime_system_multiplier=None,
        )
