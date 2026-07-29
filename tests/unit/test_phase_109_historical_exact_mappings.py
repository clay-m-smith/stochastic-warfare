"""Exact registry and runtime proofs for Phase 109 historical repairs."""

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
from stochastic_warfare.core.types import Position
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
    required_domains_for_weapon_role,
)


DATA_DIR = Path(__file__).parents[2] / "data"


@dataclass(frozen=True, slots=True)
class _ExpectedMapping:
    era: str
    unit_type: str
    equipment_name: str
    weapon_id: str
    category: WeaponCategory
    role: WeaponModeledRole
    ammo_type: AmmoType
    ammo_id: str
    caliber_mm: float


def _expected(
    era: str,
    unit_type: str,
    equipment_name: str,
    weapon_id: str,
    category: WeaponCategory,
    role: WeaponModeledRole,
    ammo_type: AmmoType,
    ammo_id: str,
    caliber_mm: float,
) -> _ExpectedMapping:
    return _ExpectedMapping(
        era=era,
        unit_type=unit_type,
        equipment_name=equipment_name,
        weapon_id=weapon_id,
        category=category,
        role=role,
        ammo_type=ammo_type,
        ammo_id=ammo_id,
        caliber_mm=caliber_mm,
    )


_EXPECTED_MAPPINGS = (
    _expected(
        "ww1",
        "iron_duke_bb",
        "BL 13.5-inch Mk V Gun (5x2 turrets)",
        "bl_13_5in_mk_v",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        AmmoType.AP,
        "13_5in_apc_mk_ia",
        343.0,
    ),
    _expected(
        "ww1",
        "iron_duke_bb",
        "BL 6-inch Mk VII Gun (x12)",
        "bl_6in_mk_vii",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        AmmoType.AP,
        "6in_mk_vii_cpc",
        152.4,
    ),
    _expected(
        "ww1",
        "g_class_destroyer",
        "QF 4-inch Mk IV Gun (x3)",
        "qf_4in_mk_iv",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        AmmoType.HE,
        "4in_mk_iv_he",
        101.6,
    ),
    _expected(
        "ww1",
        "u_boat_ww1",
        "8.8cm SK L/30 Deck Gun",
        "sk_l30_88mm",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        AmmoType.HE,
        "88mm_c07_he",
        88.0,
    ),
    _expected(
        "ww1",
        "invincible_bc",
        "QF 4-inch Mk III Gun (x16)",
        "qf_4in_mk_iii",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        AmmoType.HE,
        "4in_mk_iii_he",
        101.6,
    ),
    _expected(
        "ww2",
        "6pdr_at",
        "QF 6-Pounder (57mm) L/50",
        "qf_6pdr_l50",
        WeaponCategory.CANNON,
        WeaponModeledRole.GROUND_DIRECT_FIRE,
        AmmoType.AP,
        "57mm_apcbc_mk9t",
        57.0,
    ),
    _expected(
        "ww2",
        "panther",
        "75mm KwK 42 L/70 Gun",
        "kwk42_75mm",
        WeaponCategory.CANNON,
        WeaponModeledRole.GROUND_DIRECT_FIRE,
        AmmoType.AP,
        "75mm_pzgr39_42_apcbc",
        75.0,
    ),
    _expected(
        "ww2",
        "type_viic_uboat",
        "8.8cm SK C/35 Deck Gun",
        "sk_c35_88mm",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        AmmoType.HE,
        "88mm_c35_he",
        88.0,
    ),
    _expected(
        "ww2",
        "type_ixc_uboat",
        "10.5cm SK C/32 Deck Gun",
        "sk_c32_105mm",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        AmmoType.HE,
        "105mm_c32_he",
        105.0,
    ),
    _expected(
        "ww2",
        "flower_corvette",
        "BL 4-inch Mk IX Gun",
        "bl_4in_mk_ix",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        AmmoType.HE,
        "4in_mk_ix_he",
        101.6,
    ),
    _expected(
        "ww2",
        "spitfire_ix",
        "Browning .303 Machine Gun (x4)",
        "browning_303_mk_ii",
        WeaponCategory.AIRCRAFT_GUN,
        WeaponModeledRole.AIRCRAFT_GUN,
        AmmoType.BALL,
        "303_mk_vii_ball",
        7.7,
    ),
    _expected(
        "ww2",
        "a6m_zero",
        "Type 97 7.7mm MG (x2)",
        "type97_77mm_aircraft_mg",
        WeaponCategory.AIRCRAFT_GUN,
        WeaponModeledRole.AIRCRAFT_GUN,
        AmmoType.BALL,
        "77x56r_type97_ball",
        7.7,
    ),
    _expected(
        "ww2",
        "soviet_rifle_squad",
        "DP-28 Light Machine Gun",
        "dp28_lmg",
        WeaponCategory.LIGHT_MG,
        WeaponModeledRole.LIGHT_MACHINE_GUN,
        AmmoType.BALL,
        "762x54r_l_ball_ww2",
        7.62,
    ),
    _expected(
        "ww2",
        "t34_85",
        "DT 7.62mm Coaxial MG",
        "dt_762mm",
        WeaponCategory.MACHINE_GUN,
        WeaponModeledRole.GENERAL_PURPOSE_MACHINE_GUN,
        AmmoType.BALL,
        "762x54r_l_ball_ww2",
        7.62,
    ),
    _expected(
        "ww2",
        "us_rifle_squad_ww2",
        "M1918A2 BAR",
        "m1918a2_bar",
        WeaponCategory.LIGHT_MG,
        WeaponModeledRole.LIGHT_MACHINE_GUN,
        AmmoType.BALL,
        "30_06_m2_ball",
        7.62,
    ),
    _expected(
        "ww2",
        "flower_corvette",
        "2-pdr Pom-Pom",
        "qf_2pdr_mk_viii",
        WeaponCategory.AAA,
        WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN,
        AmmoType.HE,
        "2pdr_pompom_he",
        40.0,
    ),
    _expected(
        "ww2",
        "type_viic_uboat",
        "2cm FlaK C/30 AA Gun",
        "flak_c30_20mm",
        WeaponCategory.AAA,
        WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN,
        AmmoType.HE,
        "20mm_c30_hei",
        20.0,
    ),
    _expected(
        "ww2",
        "type_ixc_uboat",
        "3.7cm FlaK M42 AA Gun",
        "flak_m42_37mm",
        WeaponCategory.AAA,
        WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN,
        AmmoType.HE,
        "37mm_m42_he",
        37.0,
    ),
    _expected(
        "ww2",
        "iowa_bb",
        "Bofors 40mm Quad Mount (x20)",
        "bofors_40mm_l60",
        WeaponCategory.AAA,
        WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN,
        AmmoType.HE,
        "bofors_40mm_he",
        40.0,
    ),
    _expected(
        "ww2",
        "essex_cv",
        "Bofors 40mm Quad Mount (x8)",
        "bofors_40mm_l60",
        WeaponCategory.AAA,
        WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN,
        AmmoType.HE,
        "bofors_40mm_he",
        40.0,
    ),
    _expected(
        "ww2",
        "lst_mk2",
        "Bofors 40mm Twin Mount (x2)",
        "bofors_40mm_l60",
        WeaponCategory.AAA,
        WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN,
        AmmoType.HE,
        "bofors_40mm_he",
        40.0,
    ),
    _expected(
        "ww2",
        "fletcher_dd",
        "Bofors 40mm Twin Mount (x5)",
        "bofors_40mm_l60",
        WeaponCategory.AAA,
        WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN,
        AmmoType.HE,
        "bofors_40mm_he",
        40.0,
    ),
    _expected(
        "ww2",
        "essex_cv",
        "Oerlikon 20mm (x46)",
        "oerlikon_20mm_mk4",
        WeaponCategory.AAA,
        WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN,
        AmmoType.HE,
        "oerlikon_20mm_he",
        20.0,
    ),
    _expected(
        "ww2",
        "iowa_bb",
        "Oerlikon 20mm (x49)",
        "oerlikon_20mm_mk4",
        WeaponCategory.AAA,
        WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN,
        AmmoType.HE,
        "oerlikon_20mm_he",
        20.0,
    ),
    _expected(
        "ww2",
        "lst_mk2",
        "Oerlikon 20mm (x6)",
        "oerlikon_20mm_mk4",
        WeaponCategory.AAA,
        WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN,
        AmmoType.HE,
        "oerlikon_20mm_he",
        20.0,
    ),
    _expected(
        "ww2",
        "fletcher_dd",
        "Oerlikon 20mm (x7)",
        "oerlikon_20mm_mk4",
        WeaponCategory.AAA,
        WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN,
        AmmoType.HE,
        "oerlikon_20mm_he",
        20.0,
    ),
    _expected(
        "ww2",
        "shokaku_cv",
        "Type 96 25mm Triple Mount (x12)",
        "type96_25mm",
        WeaponCategory.AAA,
        WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN,
        AmmoType.HE,
        "type96_25mm_he",
        25.0,
    ),
    _expected(
        "ww2",
        "shokaku_cv",
        "Type 89 12.7cm AA Gun (8x2)",
        "type89_127mm",
        WeaponCategory.AAA,
        WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN,
        AmmoType.HE,
        "type89_127mm_he",
        127.0,
    ),
    _expected(
        "ww2",
        "flower_corvette",
        "Hedgehog ASW Mortar",
        "hedgehog_mk10",
        WeaponCategory.DEPTH_CHARGE,
        WeaponModeledRole.ANTI_SUBMARINE,
        AmmoType.HE,
        "hedgehog_mk10_projectile",
        182.88,
    ),
)


@pytest.mark.parametrize(
    "expected",
    _EXPECTED_MAPPINGS,
    ids=lambda expected: expected.equipment_name,
)
def test_registry_declares_exact_historical_weapon_semantics(
    expected: _ExpectedMapping,
) -> None:
    record = EQUIPMENT_MAPPING_REGISTRY.require(
        EquipmentCategory.WEAPON,
        expected.equipment_name,
    )

    assert isinstance(record, WeaponAttachmentMapping)
    assert record.weapon_id == expected.weapon_id
    assert record.expected_weapon_category is expected.category
    assert record.modeled_role is expected.role
    assert record.reference_kind is ReferenceKind.EXACT
    assert record.required_ammo_types == (expected.ammo_type,)
    assert record.allowed_ammo_ids == (expected.ammo_id,)
    assert record.required_target_domains == required_domains_for_weapon_role(
        expected.role,
    )
    assert record.expected_caliber_mm == expected.caliber_mm
    assert record.expected_guidance is GuidanceType.NONE


def _load_effective_catalogs(
    era: str,
) -> tuple[WeaponLoader, AmmoLoader, SensorLoader, UnitLoader]:
    weapon_loader = WeaponLoader(DATA_DIR / "weapons")
    weapon_loader.load_all()
    era_weapon_loader = WeaponLoader(DATA_DIR / "eras" / era / "weapons")
    era_weapon_loader.load_all()
    weapon_loader._definitions.update(era_weapon_loader._definitions)

    ammo_loader = AmmoLoader(DATA_DIR / "ammunition")
    ammo_loader.load_all()
    era_ammo_loader = AmmoLoader(DATA_DIR / "eras" / era / "ammunition")
    era_ammo_loader.load_all()
    ammo_loader._definitions.update(era_ammo_loader._definitions)

    sensor_loader = SensorLoader(DATA_DIR / "sensors")
    sensor_loader.load_all()
    era_sensor_loader = SensorLoader(DATA_DIR / "eras" / era / "sensors")
    era_sensor_loader.load_all()
    sensor_loader._definitions.update(era_sensor_loader._definitions)

    unit_loader = UnitLoader(DATA_DIR / "units")
    unit_loader.load_all()
    era_unit_loader = UnitLoader(DATA_DIR / "eras" / era / "units")
    era_unit_loader.load_all()
    unit_loader._definitions.update(era_unit_loader._definitions)
    return weapon_loader, ammo_loader, sensor_loader, unit_loader


@pytest.mark.parametrize("era", ("ww1", "ww2"))
def test_exact_historical_mappings_build_runtime_loadouts(
    era: str,
) -> None:
    expected_rows = tuple(expected for expected in _EXPECTED_MAPPINGS if expected.era == era)
    unit_types = tuple(dict.fromkeys(row.unit_type for row in expected_rows))
    weapon_loader, ammo_loader, sensor_loader, unit_loader = _load_effective_catalogs(era)
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
            f"phase109-{era}-{index}",
            Position(float(index * 100), 0.0),
            "blue",
            rng,
        )
        for index, unit_type in enumerate(unit_types)
    )

    loadouts = builder.build(units)
    units_by_type = {unit.unit_type: unit for unit in units}
    for expected in expected_rows:
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
        catalog_definition = weapon_loader.get_definition(
            expected.weapon_id,
        )

        assert attachment.weapon.weapon_id == expected.weapon_id
        assert attachment.weapon.definition.magazine_capacity == (
            catalog_definition.magazine_capacity
            * attachment.runtime_system_multiplier
        )
        assert attachment.weapon.ammo_state.rounds_by_type == {
            expected.ammo_id: (
                catalog_definition.magazine_capacity
                * attachment.runtime_system_multiplier
            ),
        }
        assert [ammo.ammo_id for ammo in attachment.ammunition] == [
            expected.ammo_id,
        ]
        assert attachment.weapon.equipment is attachment.source_equipment
        assert resolution.disposition is ResolutionDisposition.ATTACHMENT
        assert resolution.target_id == expected.weapon_id
        assert resolution.modeled_role is expected.role
        assert resolution.reference_kind is ReferenceKind.EXACT
        assert resolution.source_system_count == (
            attachment.source_system_count
        )
        assert resolution.target_system_count == (
            attachment.target_system_count
        )
        assert resolution.runtime_system_multiplier == (
            attachment.runtime_system_multiplier
        )


def test_invincible_catalog_uses_qf_mk_iii_identity() -> None:
    loader = UnitLoader(DATA_DIR / "eras" / "ww1" / "units")
    definition = loader.load_definition(
        DATA_DIR / "eras" / "ww1" / "units" / "naval" / "invincible_bc.yaml",
    )
    weapon_names = {equipment.name for equipment in definition.equipment if equipment.category == "WEAPON"}

    assert "QF 4-inch Mk III Gun (x16)" in weapon_names
    assert "BL 4-inch Mk III Gun (x16)" not in weapon_names
    assert (
        EQUIPMENT_MAPPING_REGISTRY.get(
            EquipmentCategory.WEAPON,
            "BL 4-inch Mk III Gun (x16)",
        )
        is None
    )
