"""Focused catalog proof for Phase 109 individual-weapon identity repairs."""

from __future__ import annotations

from pathlib import Path

from stochastic_warfare.combat.ammunition import (
    AmmoLoader,
    AmmoType,
    WeaponCategory,
    WeaponLoader,
)
from stochastic_warfare.entities.loader import UnitLoader


DATA_DIR = Path(__file__).parents[3] / "data"


def test_modern_individual_weapon_definitions_keep_exact_roles_and_ammunition() -> None:
    weapon_loader = WeaponLoader(DATA_DIR / "weapons")
    weapon_loader.load_all()
    ammo_loader = AmmoLoader(DATA_DIR / "ammunition")
    ammo_loader.load_all()

    expected = {
        "svd_dragunov": (
            WeaponCategory.RIFLE,
            7.62,
            ("7_62x54r_sniper_ball",),
        ),
        "m40a1_sniper": (
            WeaponCategory.RIFLE,
            7.62,
            ("m118_special_ball",),
        ),
        "m82a1_sasr": (
            WeaponCategory.RIFLE,
            12.7,
            ("50bmg_m2_ap",),
        ),
        "m203_40mm": (
            WeaponCategory.GRENADE,
            40.0,
            ("m433_40mm_hedp",),
        ),
        "matador_90mm": (
            WeaponCategory.ROCKET_LAUNCHER,
            90.0,
            ("matador_90mm_heat_hesh",),
        ),
    }

    for weapon_id, (category, caliber_mm, ammo_ids) in expected.items():
        definition = weapon_loader.get_definition(weapon_id)
        assert definition.parsed_category() is category
        assert definition.caliber_mm == caliber_mm
        assert tuple(definition.compatible_ammo) == ammo_ids
        for ammo_id in ammo_ids:
            ammo = ammo_loader.get_definition(ammo_id)
            assert ammo.diameter_mm == caliber_mm

    assert (
        ammo_loader.get_definition("m433_40mm_hedp").parsed_ammo_type()
        is AmmoType.HEAT
    )
    assert (
        ammo_loader.get_definition("matador_90mm_heat_hesh").parsed_ammo_type()
        is AmmoType.HEAT
    )


def test_ww1_mp18_is_not_a_light_machine_gun_proxy() -> None:
    weapon_loader = WeaponLoader(DATA_DIR / "eras" / "ww1" / "weapons")
    weapon_loader.load_all()
    ammo_loader = AmmoLoader(DATA_DIR / "eras" / "ww1" / "ammunition")
    ammo_loader.load_all()

    definition = weapon_loader.get_definition("mp18")
    assert definition.parsed_category() is WeaponCategory.SUBMACHINE_GUN
    assert definition.caliber_mm == 9.0
    assert definition.compatible_ammo == ["9x19mm_parabellum_ww1"]

    ammunition = ammo_loader.get_definition("9x19mm_parabellum_ww1")
    assert ammunition.parsed_ammo_type() is AmmoType.BALL
    assert ammunition.diameter_mm == definition.caliber_mm


def test_breaching_shotguns_are_utility_without_a_breaching_runtime() -> None:
    loader = UnitLoader(DATA_DIR / "units")
    loader.load_all()

    occurrences = [
        entry
        for definition in loader.definitions().values()
        for entry in definition.equipment
        if entry.name == "Benelli M1014 Shotgun"
    ]

    assert len(occurrences) == 2
    assert {entry.category for entry in occurrences} == {"UTILITY"}
