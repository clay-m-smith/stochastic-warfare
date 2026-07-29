"""Exact-data and production-loadout proofs for Phase 109 residual proxies."""

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
    ammo_type: AmmoType
    ammo_id: str
    caliber_mm: float
    guidance: GuidanceType


_EXPECTED_MAPPINGS = (
    _ExpectedMapping(
        "ah64d",
        "M230 Chain Gun 30mm",
        "m230_chain_gun",
        WeaponCategory.AIRCRAFT_GUN,
        WeaponModeledRole.AIRCRAFT_GUN,
        AmmoType.HEAT,
        "30x113_m789_hedp",
        30.0,
        GuidanceType.NONE,
    ),
    _ExpectedMapping(
        "sea_harrier",
        "30mm ADEN",
        "aden_30mm",
        WeaponCategory.AIRCRAFT_GUN,
        WeaponModeledRole.AIRCRAFT_GUN,
        AmmoType.HE,
        "30x113b_aden_hei",
        30.0,
        GuidanceType.NONE,
    ),
    _ExpectedMapping(
        "sovremenny",
        "3M80 Moskit Launcher",
        "3m80_moskit",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.ANTI_SHIP_MISSILE,
        AmmoType.MISSILE,
        "3m80_moskit",
        760.0,
        GuidanceType.COMBINED,
    ),
    _ExpectedMapping(
        "kilo636",
        "533mm Torpedo Tubes x6",
        "project636_533mm_torpedo_tube",
        WeaponCategory.TORPEDO_TUBE,
        WeaponModeledRole.TORPEDO,
        AmmoType.TORPEDO,
        "ugst_torpedo",
        533.0,
        GuidanceType.COMBINED,
    ),
    _ExpectedMapping(
        "ranger_plt",
        "Carl Gustaf M3",
        "carl_gustaf_m3",
        WeaponCategory.ROCKET_LAUNCHER,
        WeaponModeledRole.ANTI_ARMOR,
        AmmoType.HEAT,
        "carl_gustaf_heat551",
        84.0,
        GuidanceType.NONE,
    ),
    _ExpectedMapping(
        "iraqi_insurgent_mortar_team",
        "Iraqi 82mm 2B14 Mortar",
        "2b14_82mm_mortar",
        WeaponCategory.MORTAR,
        WeaponModeledRole.MORTAR_FIRE,
        AmmoType.HE,
        "o832du_82mm_he",
        82.0,
        GuidanceType.NONE,
    ),
    _ExpectedMapping(
        "sovremenny",
        "AK-130 130mm Twin Gun",
        "ak130_130mm",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        AmmoType.HE,
        "ak130_he_frag",
        130.0,
        GuidanceType.NONE,
    ),
    _ExpectedMapping(
        "challenger2",
        "L30A1 120mm Rifled Gun",
        "l30a1_120mm",
        WeaponCategory.CANNON,
        WeaponModeledRole.GROUND_DIRECT_FIRE,
        AmmoType.AP,
        "l27a1_charm3_apfsds",
        120.0,
        GuidanceType.NONE,
    ),
    _ExpectedMapping(
        "leopard2a6",
        "Rh-120 L/55 120mm Smoothbore",
        "rh120_l55_120mm",
        WeaponCategory.CANNON,
        WeaponModeledRole.GROUND_DIRECT_FIRE,
        AmmoType.AP,
        "dm53_apfsds",
        120.0,
        GuidanceType.NONE,
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
def test_residual_mapping_declares_exact_semantics(
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
    assert record.expected_caliber_mm == expected.caliber_mm
    assert record.expected_guidance is expected.guidance
    assert record.required_target_domains == required_domains_for_weapon_role(
        expected.role,
    )


@pytest.mark.parametrize(
    "expected",
    _EXPECTED_MAPPINGS,
    ids=lambda expected: expected.weapon_id,
)
def test_residual_exact_catalog_pair_loads(
    expected: _ExpectedMapping,
) -> None:
    weapon_loader = WeaponLoader(DATA_DIR / "weapons")
    weapon_loader.load_all()
    ammo_loader = AmmoLoader(DATA_DIR / "ammunition")
    ammo_loader.load_all()

    weapon = weapon_loader.get_definition(expected.weapon_id)
    ammo = ammo_loader.get_definition(expected.ammo_id)
    assert weapon.parsed_category() is expected.category
    assert weapon.parsed_guidance() is expected.guidance
    assert weapon.caliber_mm == expected.caliber_mm
    assert weapon.compatible_ammo == [expected.ammo_id]
    assert weapon.target_domains == [
        domain.name for domain in required_domains_for_weapon_role(expected.role)
    ]
    assert ammo.parsed_ammo_type() is expected.ammo_type
    assert ammo.parsed_guidance() is expected.guidance


def test_residual_exact_mappings_build_runtime_owned_loadouts() -> None:
    weapon_loader, ammo_loader, sensor_loader, unit_loader = _load_catalogs()
    unit_types = tuple(
        dict.fromkeys(expected.unit_type for expected in _EXPECTED_MAPPINGS)
    )
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
            f"phase109-residual-{index}",
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

        observed_targets.add(attachment.weapon.weapon_id)
        assert attachment.weapon.weapon_id == expected.weapon_id
        assert [ammo.ammo_id for ammo in attachment.ammunition] == [
            expected.ammo_id,
        ]
        assert attachment.weapon.ammo_state.rounds_by_type == {
            expected.ammo_id: attachment.weapon.definition.magazine_capacity,
        }
        assert attachment.weapon.equipment is attachment.source_equipment
        assert resolution.disposition is ResolutionDisposition.ATTACHMENT
        assert resolution.target_id == expected.weapon_id
        assert resolution.modeled_role is expected.role
        assert resolution.reference_kind is ReferenceKind.EXACT

    assert observed_targets == {
        expected.weapon_id for expected in _EXPECTED_MAPPINGS
    }
    assert len(observed_targets) == 9


def test_exact_m230_mapping_rejects_catalog_caliber_drift() -> None:
    weapon_loader, ammo_loader, sensor_loader, unit_loader = _load_catalogs()
    m230 = weapon_loader.get_definition("m230_chain_gun")
    weapon_loader._definitions["m230_chain_gun"] = m230.model_copy(
        update={"caliber_mm": 20.0},
    )

    with pytest.raises(
        EquipmentMappingError,
        match="caliber 20.0 mm does not match required 30.0 mm",
    ):
        _builder(
            weapon_loader,
            ammo_loader,
            sensor_loader,
            unit_loader,
            ("ah64d",),
        )
