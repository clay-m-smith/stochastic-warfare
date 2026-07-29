"""Production mapping proofs for Phase 109 modern exact weapon identities."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
    EquipmentMappingError,
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
    unit_type: str
    equipment_name: str
    weapon_id: str
    category: WeaponCategory
    role: WeaponModeledRole
    reference_kind: ReferenceKind
    ammo_type: AmmoType
    ammo_id: str
    caliber_mm: float
    guidance: GuidanceType


_EXPECTED_MAPPINGS = (
    _ExpectedMapping(
        "mi24v",
        "9M114 Shturm-V Launcher",
        "shturm_v_9m114",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.AIR_TO_GROUND_MISSILE,
        ReferenceKind.EXACT,
        AmmoType.HEAT,
        "9m114_shturm",
        130.0,
        GuidanceType.COMMAND,
    ),
    _ExpectedMapping(
        "mi24v",
        "YakB-12.7 Gatling Gun",
        "yakb_127mm",
        WeaponCategory.AIRCRAFT_GUN,
        WeaponModeledRole.AIRCRAFT_GUN,
        ReferenceKind.EXACT,
        AmmoType.AP,
        "yakb_12_7x108_api",
        12.7,
        GuidanceType.NONE,
    ),
    _ExpectedMapping(
        "f15e",
        "AIM-7M Sparrow",
        "aim7m_sparrow",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.AIR_TO_AIR_MISSILE,
        ReferenceKind.EXACT,
        AmmoType.MISSILE,
        "aim7m_sparrow",
        200.0,
        GuidanceType.RADAR_SEMI,
    ),
    _ExpectedMapping(
        "f15e",
        "AIM-9L Sidewinder",
        "aim9l_sidewinder",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.AIR_TO_AIR_MISSILE,
        ReferenceKind.EXACT,
        AmmoType.MISSILE,
        "aim9l_sidewinder",
        130.0,
        GuidanceType.IR,
    ),
    _ExpectedMapping(
        "s300pmu",
        "5P85 TEL",
        "s300pmu_5p85",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.AIR_DEFENSE_MISSILE,
        ReferenceKind.VARIANT,
        AmmoType.MISSILE,
        "48n6_sam",
        500.0,
        GuidanceType.COMBINED,
    ),
    _ExpectedMapping(
        "sa11_buk",
        "9A310 TELAR",
        "buk_m1_9a310",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.AIR_DEFENSE_MISSILE,
        ReferenceKind.VARIANT,
        AmmoType.MISSILE,
        "9m38m1_sam",
        400.0,
        GuidanceType.RADAR_SEMI,
    ),
    _ExpectedMapping(
        "iraqi_foreign_fighter",
        "PKM GPMG",
        "pkm_762x54r",
        WeaponCategory.MACHINE_GUN,
        WeaponModeledRole.GENERAL_PURPOSE_MACHINE_GUN,
        ReferenceKind.EXACT,
        AmmoType.BALL,
        "762x54r_ball",
        7.62,
        GuidanceType.NONE,
    ),
    _ExpectedMapping(
        "iraqi_foreign_fighter",
        "AK-74",
        "ak74_545mm",
        WeaponCategory.RIFLE,
        WeaponModeledRole.ASSAULT_RIFLE,
        ReferenceKind.VARIANT,
        AmmoType.BALL,
        "545x39_ball",
        5.45,
        GuidanceType.NONE,
    ),
    _ExpectedMapping(
        "idf_egoz_team",
        "IMI Negev 5.56mm LMG",
        "negev_ng5_lmg",
        WeaponCategory.LIGHT_MG,
        WeaponModeledRole.LIGHT_MACHINE_GUN,
        ReferenceKind.VARIANT,
        AmmoType.BALL,
        "556_ss109_ball",
        5.56,
        GuidanceType.NONE,
    ),
    _ExpectedMapping(
        "us_marine_recon_team",
        "M249 SAW",
        "m249_saw",
        WeaponCategory.LIGHT_MG,
        WeaponModeledRole.LIGHT_MACHINE_GUN,
        ReferenceKind.EXACT,
        AmmoType.BALL,
        "556_m855a1_linked",
        5.56,
        GuidanceType.NONE,
    ),
    _ExpectedMapping(
        "t72m",
        "PKT 7.62mm Coaxial",
        "pkt_762x54r",
        WeaponCategory.MACHINE_GUN,
        WeaponModeledRole.GENERAL_PURPOSE_MACHINE_GUN,
        ReferenceKind.EXACT,
        AmmoType.BALL,
        "762x54r_ball",
        7.62,
        GuidanceType.NONE,
    ),
    _ExpectedMapping(
        "btr80",
        "KPVT 14.5mm HMG",
        "kpvt_145mm",
        WeaponCategory.HEAVY_MG,
        WeaponModeledRole.HEAVY_MACHINE_GUN,
        ReferenceKind.EXACT,
        AmmoType.AP,
        "145x114_bzt561sm",
        14.5,
        GuidanceType.NONE,
    ),
    _ExpectedMapping(
        "btr80",
        "PKT 7.62mm MG",
        "pkt_762x54r",
        WeaponCategory.MACHINE_GUN,
        WeaponModeledRole.GENERAL_PURPOSE_MACHINE_GUN,
        ReferenceKind.EXACT,
        AmmoType.BALL,
        "762x54r_ball",
        7.62,
        GuidanceType.NONE,
    ),
    _ExpectedMapping(
        "iraqi_mtlb",
        "PKT 7.62mm Machine Gun",
        "pkt_762x54r",
        WeaponCategory.MACHINE_GUN,
        WeaponModeledRole.GENERAL_PURPOSE_MACHINE_GUN,
        ReferenceKind.EXACT,
        AmmoType.BALL,
        "762x54r_ball",
        7.62,
        GuidanceType.NONE,
    ),
    _ExpectedMapping(
        "t55a",
        "SGMT 7.62mm Coaxial",
        "sgmt_762x54r",
        WeaponCategory.MACHINE_GUN,
        WeaponModeledRole.GENERAL_PURPOSE_MACHINE_GUN,
        ReferenceKind.EXACT,
        AmmoType.BALL,
        "762x54r_ball",
        7.62,
        GuidanceType.NONE,
    ),
    _ExpectedMapping(
        "qatari_amx30b2",
        "20mm M693 Coaxial",
        "m693_20mm",
        WeaponCategory.AUTOCANNON,
        WeaponModeledRole.GROUND_DIRECT_FIRE,
        ReferenceKind.EXACT,
        AmmoType.HE,
        "20x139_m693_hei",
        20.0,
        GuidanceType.NONE,
    ),
    _ExpectedMapping(
        "type42_destroyer",
        "4.5 inch Mk 8 Naval Gun",
        "mk8_45in",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        ReferenceKind.EXACT,
        AmmoType.HE,
        "45in_mk8_n20_he",
        114.3,
        GuidanceType.NONE,
    ),
    _ExpectedMapping(
        "super_etendard",
        "DEFA 553 30mm Cannon",
        "defa553_30mm",
        WeaponCategory.AIRCRAFT_GUN,
        WeaponModeledRole.AIRCRAFT_GUN,
        ReferenceKind.EXACT,
        AmmoType.HE,
        "30x113b_defa_hei",
        30.0,
        GuidanceType.NONE,
    ),
    _ExpectedMapping(
        "j10a",
        "GSh-23 23mm Cannon",
        "gsh23_23mm",
        WeaponCategory.AIRCRAFT_GUN,
        WeaponModeledRole.AIRCRAFT_GUN,
        ReferenceKind.EXACT,
        AmmoType.HE,
        "23x115_hei",
        23.0,
        GuidanceType.NONE,
    ),
    _ExpectedMapping(
        "su27s",
        "GSh-30-1 30mm Cannon",
        "gsh30_1_30mm",
        WeaponCategory.AIRCRAFT_GUN,
        WeaponModeledRole.AIRCRAFT_GUN,
        ReferenceKind.EXACT,
        AmmoType.AP,
        "30x165_gsh_ap_t",
        30.0,
        GuidanceType.NONE,
    ),
    _ExpectedMapping(
        "lhd1",
        "RAM Launcher",
        "rim116_ram",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.AIR_DEFENSE_MISSILE,
        ReferenceKind.VARIANT,
        AmmoType.MISSILE,
        "rim116_block1a",
        127.0,
        GuidanceType.COMBINED,
    ),
    _ExpectedMapping(
        "type22_frigate",
        "Sea Wolf SAM",
        "sea_wolf_sam",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.AIR_DEFENSE_MISSILE,
        ReferenceKind.VARIANT,
        AmmoType.MISSILE,
        "sea_wolf_gws25",
        180.0,
        GuidanceType.COMMAND,
    ),
)


def _load_catalogs() -> tuple[
    WeaponLoader,
    AmmoLoader,
    SensorLoader,
    UnitLoader,
]:
    weapon_loader = WeaponLoader(DATA_DIR / "weapons")
    weapon_loader.load_all()
    ammo_loader = AmmoLoader(DATA_DIR / "ammunition")
    ammo_loader.load_all()
    sensor_loader = SensorLoader(DATA_DIR / "sensors")
    sensor_loader.load_all()
    unit_loader = UnitLoader(DATA_DIR / "units")
    unit_loader.load_all()
    return weapon_loader, ammo_loader, sensor_loader, unit_loader


def _builder(
    weapon_loader: WeaponLoader,
    ammo_loader: AmmoLoader,
    sensor_loader: SensorLoader,
    unit_loader: UnitLoader,
    unit_types: tuple[str, ...],
) -> RuntimeLoadoutBuilder:
    return RuntimeLoadoutBuilder(
        weapon_loader=weapon_loader,
        ammo_loader=ammo_loader,
        sensor_loader=sensor_loader,
        unit_definitions=unit_loader.definitions(),
        era_config=get_era_config("modern"),
        assignment_overrides=(),
        reachable_unit_types=unit_types,
        registry=EQUIPMENT_MAPPING_REGISTRY,
    )


@pytest.mark.parametrize(
    "expected",
    _EXPECTED_MAPPINGS,
    ids=lambda expected: expected.equipment_name,
)
def test_registry_declares_exact_modern_weapon_semantics(
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
    assert record.reference_kind is expected.reference_kind
    assert record.required_ammo_types == (expected.ammo_type,)
    assert record.allowed_ammo_ids == (expected.ammo_id,)
    assert record.expected_caliber_mm == expected.caliber_mm
    assert record.expected_guidance is expected.guidance
    assert record.required_target_domains == required_domains_for_weapon_role(
        expected.role,
    )


def test_exact_modern_mappings_build_runtime_owned_loadouts() -> None:
    weapon_loader, ammo_loader, sensor_loader, unit_loader = _load_catalogs()
    unit_types = tuple(dict.fromkeys(expected.unit_type for expected in _EXPECTED_MAPPINGS))
    builder = _builder(
        weapon_loader,
        ammo_loader,
        sensor_loader,
        unit_loader,
        unit_types,
    )
    rng = np.random.default_rng(109)
    units = [
        unit_loader.create_unit(
            unit_type,
            f"phase109-modern-{index}",
            Position(float(index * 100), 0.0),
            "blue",
            rng,
        )
        for index, unit_type in enumerate(unit_types)
    ]

    loadouts = builder.build(units)
    units_by_type = {unit.unit_type: unit for unit in units}
    observed_targets: set[str] = set()
    for expected in _EXPECTED_MAPPINGS:
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
        domains = required_domains_for_weapon_role(expected.role)

        observed_targets.add(attachment.weapon.weapon_id)
        assert attachment.weapon.weapon_id == expected.weapon_id
        assert [ammo.ammo_id for ammo in attachment.ammunition] == [
            expected.ammo_id,
        ]
        assert attachment.weapon.definition.compatible_ammo == [
            expected.ammo_id,
        ]
        assert attachment.weapon.definition.target_domains == [domain.name for domain in domains]
        assert attachment.weapon.definition.parsed_category() is expected.category
        assert attachment.weapon.definition.parsed_guidance() is expected.guidance
        assert attachment.weapon.ammo_state.rounds_by_type == {
            expected.ammo_id: attachment.weapon.definition.magazine_capacity,
        }
        assert attachment.weapon.equipment is attachment.source_equipment
        assert resolution.disposition is ResolutionDisposition.ATTACHMENT
        assert resolution.target_id == expected.weapon_id
        assert resolution.modeled_role is expected.role
        assert resolution.reference_kind is expected.reference_kind

    assert observed_targets == {expected.weapon_id for expected in _EXPECTED_MAPPINGS}
    assert len(observed_targets) == 20


@pytest.mark.parametrize(
    ("definition_update", "message"),
    (
        (
            {"guidance": "IR"},
            "guidance IR does not match required RADAR_SEMI",
        ),
        (
            {"caliber_mm": 130.0},
            "caliber 130.0 mm does not match required 200.0 mm",
        ),
        (
            {"compatible_ammo": ["aim9l_sidewinder"]},
            "does not declare mapping-allowed ammunition",
        ),
        (
            {"target_domains": ["GROUND"]},
            "lacks required target domains",
        ),
    ),
)
def test_exact_mapping_rejects_semantically_incompatible_catalog_target(
    definition_update: dict[str, Any],
    message: str,
) -> None:
    weapon_loader, ammo_loader, sensor_loader, unit_loader = _load_catalogs()
    sparrow = weapon_loader.get_definition("aim7m_sparrow")
    weapon_loader._definitions["aim7m_sparrow"] = sparrow.model_copy(
        update=definition_update,
    )

    with pytest.raises(EquipmentMappingError, match=message):
        _builder(
            weapon_loader,
            ammo_loader,
            sensor_loader,
            unit_loader,
            ("f15e",),
        )
