"""Exact-data proof for the residual Phase 109 historical proxy repairs."""

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
    weapon_id: str
    category: WeaponCategory
    role: WeaponModeledRole
    caliber_mm: float
    ammo: tuple[tuple[str, AmmoType], ...]
    domains: tuple[Domain, ...]


_EXPECTED = (
    _Expected(
        "ww1",
        "konig_bb",
        "30.5cm SK L/50 Gun (5x2 turrets)",
        "sk_l50_305mm",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        305.0,
        (
            ("305mm_psgr_l3_4_apc", AmmoType.AP),
            ("305mm_spgr_l3_8_he", AmmoType.HE),
        ),
        (Domain.GROUND, Domain.NAVAL),
    ),
    _Expected(
        "ww1",
        "g_class_destroyer",
        "21-inch Torpedo Tubes (x2x2)",
        "british_21in_torpedo_ww1",
        WeaponCategory.TORPEDO_TUBE,
        WeaponModeledRole.TORPEDO,
        533.0,
        (("british_21in_mk_ii_warhead", AmmoType.HE),),
        (Domain.NAVAL, Domain.SUBMARINE),
    ),
    _Expected(
        "ww1",
        "iron_duke_bb",
        "21-inch Torpedo Tubes (x4)",
        "british_21in_torpedo_ww1",
        WeaponCategory.TORPEDO_TUBE,
        WeaponModeledRole.TORPEDO,
        533.0,
        (("british_21in_mk_ii_warhead", AmmoType.HE),),
        (Domain.NAVAL, Domain.SUBMARINE),
    ),
    _Expected(
        "ww1",
        "u_boat_ww1",
        "45cm Torpedo Tubes (x4)",
        "c06d_45cm_torpedo_ww1",
        WeaponCategory.TORPEDO_TUBE,
        WeaponModeledRole.TORPEDO,
        450.0,
        (("c06d_45cm_warhead", AmmoType.HE),),
        (Domain.NAVAL, Domain.SUBMARINE),
    ),
    _Expected(
        "ww1",
        "konig_bb",
        "50cm Torpedo Tubes (x5)",
        "g7_50cm_torpedo_ww1",
        WeaponCategory.TORPEDO_TUBE,
        WeaponModeledRole.TORPEDO,
        500.0,
        (("g7_50cm_warhead", AmmoType.HE),),
        (Domain.NAVAL, Domain.SUBMARINE),
    ),
    _Expected(
        "napoleonic",
        "ship_of_line_74",
        "18-pdr Long Guns (upper deck, x30)",
        "18pdr_naval",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        134.4,
        (
            ("round_shot_18pdr", AmmoType.AP),
            ("grape_shot_18pdr", AmmoType.SHRAPNEL),
        ),
        (Domain.GROUND, Domain.NAVAL),
    ),
    _Expected(
        "napoleonic",
        "first_rate_100",
        "18-pdr Long Guns (upper deck, x34)",
        "18pdr_naval",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        134.4,
        (
            ("round_shot_18pdr", AmmoType.AP),
            ("grape_shot_18pdr", AmmoType.SHRAPNEL),
        ),
        (Domain.GROUND, Domain.NAVAL),
    ),
    _Expected(
        "napoleonic",
        "corvette_sloop",
        "Carronades 24-pdr (x2)",
        "carronade_24pdr",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        144.0,
        (
            ("round_shot_24pdr_carronade", AmmoType.AP),
            ("grape_shot_24pdr_carronade", AmmoType.SHRAPNEL),
        ),
        (Domain.GROUND, Domain.NAVAL),
    ),
    _Expected(
        "ww2",
        "pak40_at",
        "7.5cm PaK 40 L/46",
        "pak40_l46_75mm",
        WeaponCategory.CANNON,
        WeaponModeledRole.GROUND_DIRECT_FIRE,
        75.0,
        (
            ("75mm_pzgr39_pak40_apcbc", AmmoType.AP),
            ("75mm_sprgr34_pak40_he", AmmoType.HE),
        ),
        (Domain.GROUND,),
    ),
    _Expected(
        "ww2",
        "panzer_iv_h",
        "75mm KwK 40 L/48 Gun",
        "kwk40_l48_75mm",
        WeaponCategory.CANNON,
        WeaponModeledRole.GROUND_DIRECT_FIRE,
        75.0,
        (
            ("75mm_pzgr39_kwk40_apcbc", AmmoType.AP),
            ("75mm_sprgr34_kwk40_he", AmmoType.HE),
        ),
        (Domain.GROUND,),
    ),
)


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


@pytest.mark.parametrize(
    "expected",
    _EXPECTED,
    ids=lambda item: item.equipment_name,
)
def test_residual_historical_registry_records_are_exact_and_constrained(
    expected: _Expected,
) -> None:
    record = EQUIPMENT_MAPPING_REGISTRY.require(
        EquipmentCategory.WEAPON,
        expected.equipment_name,
    )

    assert isinstance(record, WeaponAttachmentMapping)
    assert record.weapon_id == expected.weapon_id
    assert record.reference_kind is ReferenceKind.EXACT
    assert record.expected_weapon_category is expected.category
    assert record.modeled_role is expected.role
    assert record.expected_caliber_mm == expected.caliber_mm
    assert record.expected_guidance is GuidanceType.NONE
    assert record.required_target_domains == expected.domains
    assert record.allowed_ammo_ids == tuple(
        ammo_id for ammo_id, _ in expected.ammo
    )
    assert record.required_ammo_types == tuple(
        ammo_type for _, ammo_type in expected.ammo
    )


@pytest.mark.parametrize("era", ("napoleonic", "ww1", "ww2"))
def test_residual_historical_exact_definitions_load_and_build(
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
            f"phase109-residual-{era}-{index}",
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
        assert definition.parsed_category() is expected.category
        assert definition.caliber_mm == expected.caliber_mm
        assert definition.parsed_guidance() is GuidanceType.NONE
        assert definition.effective_target_domains() == {
            domain.name for domain in expected.domains
        }
        assert tuple(definition.compatible_ammo) == tuple(
            ammo_id for ammo_id, _ in expected.ammo
        )
        for ammo_id, ammo_type in expected.ammo:
            ammunition = ammo_loader.get_definition(ammo_id)
            assert ammunition.parsed_ammo_type() is ammo_type
            assert ammunition.parsed_guidance() is GuidanceType.NONE

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
            ammo_id for ammo_id, _ in expected.ammo
        ]
        assert attachment.weapon.equipment is attachment.source_equipment
        assert resolution.disposition is ResolutionDisposition.ATTACHMENT
        assert resolution.target_id == expected.weapon_id
        assert resolution.reference_kind is ReferenceKind.EXACT


def test_residual_historical_names_no_longer_resolve_to_gross_proxies() -> None:
    old_targets = {
        "30.5cm SK L/50 Gun (5x2 turrets)": "12in_bl_mk_x",
        "21-inch Torpedo Tubes (x2x2)": "18in_torpedo_ww1",
        "21-inch Torpedo Tubes (x4)": "18in_torpedo_ww1",
        "45cm Torpedo Tubes (x4)": "18in_torpedo_ww1",
        "50cm Torpedo Tubes (x5)": "18in_torpedo_ww1",
        "18-pdr Long Guns (upper deck, x30)": "24pdr_cannon",
        "18-pdr Long Guns (upper deck, x34)": "24pdr_cannon",
        "Carronades 24-pdr (x2)": "carronade_32pdr",
        "7.5cm PaK 40 L/46": "75mm_m3",
        "75mm KwK 40 L/48 Gun": "75mm_m3",
    }

    for equipment_name, old_target in old_targets.items():
        record = EQUIPMENT_MAPPING_REGISTRY.require(
            EquipmentCategory.WEAPON,
            equipment_name,
        )
        assert isinstance(record, WeaponAttachmentMapping)
        assert record.weapon_id != old_target
