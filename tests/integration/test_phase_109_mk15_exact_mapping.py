"""Production-loadout proof for the Fletcher-class Mark 15 correction."""

from __future__ import annotations

from pathlib import Path

from stochastic_warfare.combat.ammunition import AmmoType, GuidanceType
from stochastic_warfare.core.types import Domain
from stochastic_warfare.entities.equipment import EquipmentCategory
from stochastic_warfare.simulation.equipment_mappings import (
    EQUIPMENT_MAPPING_REGISTRY,
)
from stochastic_warfare.simulation.loadouts import (
    ReferenceKind,
    WeaponAttachmentMapping,
    WeaponModeledRole,
)
from stochastic_warfare.simulation.scenario import ScenarioLoader


DATA_DIR = Path("data")
MIDWAY_SCENARIO = DATA_DIR / "eras/ww2/scenarios/midway/scenario.yaml"
EQUIPMENT_NAME = "Mk 15 Torpedo Tubes (2x5)"


def test_fletcher_loads_exact_surface_mk15_with_live_torpedoes() -> None:
    ctx = ScenarioLoader(DATA_DIR).load(MIDWAY_SCENARIO, seed=109)
    fletcher = next(
        unit for unit in ctx.all_units() if unit.unit_type == "fletcher_dd"
    )
    attachment = next(
        item
        for item in ctx.unit_weapons[fletcher.entity_id]
        if item.source_equipment.name == EQUIPMENT_NAME
    )
    mapping = EQUIPMENT_MAPPING_REGISTRY.require(
        EquipmentCategory.WEAPON,
        EQUIPMENT_NAME,
    )

    assert isinstance(mapping, WeaponAttachmentMapping)
    assert mapping.reference_kind is ReferenceKind.EXACT
    assert mapping.modeled_role is WeaponModeledRole.TORPEDO
    assert mapping.weapon_id == "mk15_torpedo_tubes"
    assert mapping.required_ammo_types == (AmmoType.TORPEDO,)
    assert mapping.allowed_ammo_ids == ("mk15_torpedo_warhead",)
    assert mapping.required_target_domains == (Domain.NAVAL,)
    assert mapping.expected_caliber_mm == 533.4
    assert mapping.expected_guidance is GuidanceType.NONE

    weapon = attachment.weapon
    assert weapon.weapon_id == "mk15_torpedo_tubes"
    assert weapon.definition.display_name == EQUIPMENT_NAME
    assert weapon.definition.compatible_ammo == ["mk15_torpedo_warhead"]
    assert weapon.definition.effective_target_domains() == {"NAVAL"}
    assert weapon.definition.magazine_capacity == 10
    assert [ammo.ammo_id for ammo in attachment.ammunition] == [
        "mk15_torpedo_warhead",
    ]
    assert attachment.ammunition[0].parsed_ammo_type() is AmmoType.TORPEDO
    assert weapon.ammo_state.rounds_by_type == {
        "mk15_torpedo_warhead": 10,
    }

    before = weapon.ammo_state.available("mk15_torpedo_warhead")
    assert weapon.fire("mk15_torpedo_warhead")
    assert weapon.ammo_state.available("mk15_torpedo_warhead") == before - 1
