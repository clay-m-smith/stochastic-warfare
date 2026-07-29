"""Strict production-path proof for the Phase 109 exact-data follow-up."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

from stochastic_warfare.combat.ammunition import (
    AmmoLoader,
    AmmoType,
    GuidanceType,
    WeaponCategory,
    WeaponLoader,
)
from stochastic_warfare.core.era import get_era_config
from stochastic_warfare.core.types import Domain, Position
from stochastic_warfare.detection.sensors import SensorLoader
from stochastic_warfare.entities.equipment import EquipmentCategory
from stochastic_warfare.entities.loader import UnitLoader
from stochastic_warfare.simulation.equipment_mappings import (
    EQUIPMENT_MAPPING_REGISTRY,
)
from stochastic_warfare.simulation.loadouts import (
    ReferenceKind,
    ResolutionDisposition,
    RuntimeLoadoutBuilder,
    WeaponAttachmentMapping,
    WeaponModeledRole,
)


DATA_DIR = Path(__file__).parents[2] / "data"


@dataclass(frozen=True, slots=True)
class _Expected:
    era: str
    unit_type: str
    equipment_name: str
    old_target: str
    weapon_id: str
    category: WeaponCategory
    role: WeaponModeledRole
    caliber_mm: float
    ammo_id: str
    ammo_type: AmmoType
    guidance: GuidanceType
    required_domains: tuple[Domain, ...]
    target_domains: frozenset[str]


_EXPECTED = (
    _Expected(
        "modern",
        "bmp2",
        "9P135M ATGM Launcher",
        "at3_sagger",
        "9p135m_konkurs",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.ANTI_ARMOR,
        135.0,
        "9m113_konkurs",
        AmmoType.HEAT,
        GuidanceType.WIRE,
        (Domain.GROUND,),
        frozenset({"GROUND"}),
    ),
    _Expected(
        "modern",
        "qatari_amx30b2",
        "F1 105mm Rifled Gun",
        "l7_105mm",
        "cn105_f1_105mm",
        WeaponCategory.CANNON,
        WeaponModeledRole.GROUND_DIRECT_FIRE,
        105.0,
        "occ_105_f1_heat",
        AmmoType.HEAT,
        GuidanceType.NONE,
        (Domain.GROUND,),
        frozenset({"GROUND"}),
    ),
    _Expected(
        "ww1",
        "french_poilu_squad",
        "Lebel Mle 1886 M93 Rifle",
        "lee_enfield",
        "lebel_m1886_m93",
        WeaponCategory.RIFLE,
        WeaponModeledRole.BOLT_ACTION_RIFLE,
        8.0,
        "8x50r_lebel_balle_d",
        AmmoType.BALL,
        GuidanceType.NONE,
        (Domain.GROUND,),
        frozenset({"GROUND"}),
    ),
    _Expected(
        "ww1",
        "french_poilu_squad",
        "Chauchat M1915 CSRG Light Machine Gun",
        "lewis_gun",
        "chauchat_m1915",
        WeaponCategory.LIGHT_MG,
        WeaponModeledRole.LIGHT_MACHINE_GUN,
        8.0,
        "8x50r_lebel_balle_d",
        AmmoType.BALL,
        GuidanceType.NONE,
        (Domain.GROUND,),
        frozenset({"GROUND"}),
    ),
    _Expected(
        "ww1",
        "us_aef_squad",
        "M1918 BAR",
        "lewis_gun",
        "m1918a2_bar",
        WeaponCategory.LIGHT_MG,
        WeaponModeledRole.LIGHT_MACHINE_GUN,
        7.62,
        "30_06_m1906_ball",
        AmmoType.BALL,
        GuidanceType.NONE,
        (Domain.GROUND,),
        frozenset({"GROUND"}),
    ),
    _Expected(
        "modern",
        "t90a",
        "NSVT 12.7mm HMG",
        "m2hb_50cal",
        "nsvt_127mm",
        WeaponCategory.HEAVY_MG,
        WeaponModeledRole.HEAVY_MACHINE_GUN,
        12.7,
        "12_7x108_api",
        AmmoType.AP,
        GuidanceType.NONE,
        (Domain.GROUND,),
        frozenset({"GROUND", "AERIAL"}),
    ),
    _Expected(
        "ww2",
        "spitfire_ix",
        "Hispano Mk II 20mm Cannon (x2)",
        "mg151_20mm",
        "hispano_mk_ii_20mm",
        WeaponCategory.AUTOCANNON,
        WeaponModeledRole.AIRCRAFT_GUN,
        20.0,
        "20mm_hispano_mk_ii_he",
        AmmoType.HE,
        GuidanceType.NONE,
        (Domain.GROUND, Domain.AERIAL),
        frozenset({"GROUND", "AERIAL"}),
    ),
    _Expected(
        "ww2",
        "bf109g",
        "MG 131 13mm Machine Gun (x2)",
        "m2_50cal_aircraft",
        "mg131_13mm",
        WeaponCategory.HEAVY_MG,
        WeaponModeledRole.AIRCRAFT_GUN,
        13.0,
        "13mm_mg131_he",
        AmmoType.HE,
        GuidanceType.NONE,
        (Domain.GROUND, Domain.AERIAL),
        frozenset({"GROUND", "AERIAL"}),
    ),
)


def _load_effective_catalogs(
    era: str,
) -> tuple[WeaponLoader, AmmoLoader, SensorLoader, UnitLoader]:
    weapon_loader = WeaponLoader(DATA_DIR / "weapons")
    weapon_loader.load_all()
    ammo_loader = AmmoLoader(DATA_DIR / "ammunition")
    ammo_loader.load_all()
    sensor_loader = SensorLoader(DATA_DIR / "sensors")
    sensor_loader.load_all()
    unit_loader = UnitLoader(DATA_DIR / "units")
    unit_loader.load_all()

    if era != "modern":
        era_root = DATA_DIR / "eras" / era

        era_weapons = WeaponLoader(era_root / "weapons")
        era_weapons.load_all()
        weapon_loader._definitions.update(era_weapons.definitions())

        era_ammunition = AmmoLoader(era_root / "ammunition")
        era_ammunition.load_all()
        ammo_loader._definitions.update(era_ammunition.definitions())

        era_sensors = SensorLoader(era_root / "sensors")
        era_sensors.load_all()
        sensor_loader._definitions.update(era_sensors.definitions())

        era_units = UnitLoader(era_root / "units")
        era_units.load_all()
        unit_loader._definitions.update(era_units.definitions())

    return weapon_loader, ammo_loader, sensor_loader, unit_loader


@pytest.mark.parametrize(
    "expected",
    _EXPECTED,
    ids=lambda item: item.equipment_name,
)
def test_followup_registry_records_are_exact_and_semantically_constrained(
    expected: _Expected,
) -> None:
    record = EQUIPMENT_MAPPING_REGISTRY.require(
        EquipmentCategory.WEAPON,
        expected.equipment_name,
    )

    assert isinstance(record, WeaponAttachmentMapping)
    assert record.weapon_id == expected.weapon_id
    assert record.weapon_id != expected.old_target
    assert record.reference_kind is ReferenceKind.EXACT
    assert record.allowed_target_ids == ()
    assert record.rationale is None
    assert record.source is None
    assert record.expected_weapon_category is expected.category
    assert record.modeled_role is expected.role
    assert record.required_ammo_types == (expected.ammo_type,)
    assert record.allowed_ammo_ids == (expected.ammo_id,)
    assert record.required_target_domains == expected.required_domains
    assert record.expected_caliber_mm == expected.caliber_mm
    assert record.expected_guidance is expected.guidance


@pytest.mark.parametrize("era", ("modern", "ww1", "ww2"))
def test_followup_exact_data_loads_and_builds_through_runtime_boundary(
    era: str,
) -> None:
    expected_rows = tuple(item for item in _EXPECTED if item.era == era)
    unit_types = tuple(dict.fromkeys(item.unit_type for item in expected_rows))
    weapon_loader, ammo_loader, sensor_loader, unit_loader = (
        _load_effective_catalogs(era)
    )
    builder = RuntimeLoadoutBuilder(
        weapon_loader=weapon_loader,
        ammo_loader=ammo_loader,
        sensor_loader=sensor_loader,
        unit_definitions=unit_loader.definitions(),
        era_config=get_era_config(era),
        assignment_overrides=(),
        reachable_unit_types=unit_types,
        registry=EQUIPMENT_MAPPING_REGISTRY,
    )
    rng = np.random.default_rng(109)
    units = tuple(
        unit_loader.create_unit(
            unit_type,
            f"phase109-followup-{era}-{index}",
            Position(float(index * 100), 0.0),
            "blue",
            rng,
        )
        for index, unit_type in enumerate(unit_types)
    )

    loadouts = builder.build(units)
    units_by_type = {unit.unit_type: unit for unit in units}
    for expected in expected_rows:
        definition = weapon_loader.get_definition(expected.weapon_id)
        ammunition = ammo_loader.get_definition(expected.ammo_id)
        assert definition.parsed_category() is expected.category
        assert definition.caliber_mm == expected.caliber_mm
        assert definition.parsed_guidance() is expected.guidance
        assert frozenset(definition.effective_target_domains()) == (
            expected.target_domains
        )
        assert tuple(definition.compatible_ammo) == (expected.ammo_id,)
        assert ammunition.parsed_ammo_type() is expected.ammo_type
        assert ammunition.diameter_mm == expected.caliber_mm
        assert ammunition.parsed_guidance() is expected.guidance

        unit = units_by_type[expected.unit_type]
        attachment = next(
            item
            for item in loadouts.unit_weapons[unit.entity_id]
            if item.source_equipment.name == expected.equipment_name
        )
        resolution = next(
            item
            for item in loadouts.equipment_resolutions[unit.entity_id]
            if item.source_equipment is attachment.source_equipment
        )

        assert attachment.weapon.weapon_id == expected.weapon_id
        assert [item.ammo_id for item in attachment.ammunition] == [
            expected.ammo_id,
        ]
        assert attachment.weapon.equipment is attachment.source_equipment
        assert resolution.disposition is ResolutionDisposition.ATTACHMENT
        assert resolution.target_id == expected.weapon_id
        assert resolution.reference_kind is ReferenceKind.EXACT
