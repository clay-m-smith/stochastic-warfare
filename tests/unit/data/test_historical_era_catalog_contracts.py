"""Shared load contracts for the pre-modern era catalogs."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from tests.unit.data.historical_catalog_support import (
    HistoricalEraCatalogs,
    load_historical_era_catalogs,
)


_ERA_NAMES = ("ancient_medieval", "napoleonic", "ww1")


def _ids(value: str) -> tuple[str, ...]:
    return tuple(value.split())


_ERA_UNITS = {
    "ancient_medieval": _ids(
        "roman_legionary_cohort greek_hoplite_phalanx english_longbowman "
        "norman_knight_conroi swiss_pike_block mongol_horse_archer viking_huscarl"
    ),
    "napoleonic": _ids(
        "french_line_infantry french_light_infantry french_old_guard "
        "british_line_infantry british_rifle_company cuirassier_squadron "
        "hussar_squadron lancer_squadron horse_artillery_battery "
        "foot_artillery_battery"
    ),
    "ww1": _ids("british_infantry_platoon german_sturmtruppen french_poilu_squad mark_iv_tank a7v cavalry_troop"),
}

_ERA_WEAPONS = {
    "ancient_medieval": _ids(
        "gladius pilum sarissa longbow crossbow lance_medieval sword_medieval "
        "mace pike catapult trebuchet ballista battering_ram"
    ),
    "napoleonic": _ids(
        "brown_bess charleville_1777 baker_rifle 6pdr_cannon 12pdr_cannon "
        "howitzer_napoleonic cavalry_saber lance bayonet"
    ),
    "ww1": _ids("lee_enfield gewehr_98 maxim_mg08 lewis_gun 18pdr_field_gun 77mm_fk96 21cm_morser mills_bomb"),
}

_ERA_AMMUNITION = {
    "ancient_medieval": _ids(
        "arrow_longbow bolt_crossbow pilum_javelin stone_catapult "
        "stone_trebuchet bolt_ballista composite_arrow sling_stone"
    ),
    "napoleonic": _ids(
        "musket_ball_75 musket_ball_69 rifle_ball roundshot_6pdr "
        "roundshot_12pdr canister_6pdr canister_12pdr howitzer_shell_nap "
        "howitzer_canister_nap"
    ),
    "ww1": _ids(
        "303_ball 303_ap 792mm_s_patrone 18pdr_shrapnel 18pdr_he 77mm_he "
        "77mm_shrapnel 21cm_he mills_bomb_frag 77mm_gas_shell"
    ),
}

_ERA_SENSORS = {
    "ancient_medieval": _ids("mounted_scout_ancient watchtower ship_lookout"),
    "napoleonic": _ids("telescope_napoleonic cavalry_scout observation_post_napoleonic"),
    "ww1": _ids("binoculars_ww1 sound_ranging flash_spotting observation_balloon aircraft_recon"),
}

_ERA_SIGNATURES = {
    "ancient_medieval": _ERA_UNITS["ancient_medieval"],
    "napoleonic": _ERA_UNITS["napoleonic"],
    "ww1": _ERA_UNITS["ww1"],
}


def _catalog_cases(
    catalog: dict[str, Sequence[str]],
) -> tuple[object, ...]:
    return tuple(
        pytest.param(era_name, identifier, id=f"{era_name}-{identifier}")
        for era_name in _ERA_NAMES
        for identifier in catalog[era_name]
    )


@pytest.fixture(scope="module")
def era_catalogs_by_name() -> dict[str, HistoricalEraCatalogs]:
    """Load each declared era once; every catalog remains directly inspectable."""
    return {era_name: load_historical_era_catalogs(era_name) for era_name in _ERA_NAMES}


@pytest.mark.test_evidence("structural_only")
@pytest.mark.parametrize(("era_name", "unit_type"), _catalog_cases(_ERA_UNITS))
def test_unit_loads(
    era_catalogs_by_name: dict[str, HistoricalEraCatalogs],
    era_name: str,
    unit_type: str,
) -> None:
    definition = era_catalogs_by_name[era_name].units._definitions.get(unit_type)
    assert definition is not None, f"Unit {unit_type} not found"


@pytest.mark.parametrize(("era_name", "unit_type"), _catalog_cases(_ERA_UNITS))
def test_unit_has_display_name(
    era_catalogs_by_name: dict[str, HistoricalEraCatalogs],
    era_name: str,
    unit_type: str,
) -> None:
    assert era_catalogs_by_name[era_name].units._definitions[unit_type].display_name


@pytest.mark.test_evidence("structural_only")
@pytest.mark.parametrize(("era_name", "weapon_id"), _catalog_cases(_ERA_WEAPONS))
def test_weapon_loads(
    era_catalogs_by_name: dict[str, HistoricalEraCatalogs],
    era_name: str,
    weapon_id: str,
) -> None:
    definition = era_catalogs_by_name[era_name].weapons._definitions.get(weapon_id)
    assert definition is not None, f"Weapon {weapon_id} not found"


@pytest.mark.test_evidence("structural_only")
@pytest.mark.parametrize(
    ("era_name", "ammo_id"),
    _catalog_cases(_ERA_AMMUNITION),
)
def test_ammo_loads(
    era_catalogs_by_name: dict[str, HistoricalEraCatalogs],
    era_name: str,
    ammo_id: str,
) -> None:
    definition = era_catalogs_by_name[era_name].ammunition._definitions.get(ammo_id)
    assert definition is not None, f"Ammo {ammo_id} not found"


@pytest.mark.test_evidence("structural_only")
@pytest.mark.parametrize(("era_name", "sensor_id"), _catalog_cases(_ERA_SENSORS))
def test_sensor_loads(
    era_catalogs_by_name: dict[str, HistoricalEraCatalogs],
    era_name: str,
    sensor_id: str,
) -> None:
    definition = era_catalogs_by_name[era_name].sensors._definitions.get(sensor_id)
    assert definition is not None, f"Sensor {sensor_id} not found"


@pytest.mark.parametrize(("era_name", "sensor_id"), _catalog_cases(_ERA_SENSORS))
def test_sensor_is_visual(
    era_catalogs_by_name: dict[str, HistoricalEraCatalogs],
    era_name: str,
    sensor_id: str,
) -> None:
    definition = era_catalogs_by_name[era_name].sensors._definitions[sensor_id]
    assert definition.sensor_type == "VISUAL"


@pytest.mark.test_evidence("structural_only")
@pytest.mark.parametrize(
    ("era_name", "profile_id"),
    _catalog_cases(_ERA_SIGNATURES),
)
def test_signature_loads(
    era_catalogs_by_name: dict[str, HistoricalEraCatalogs],
    era_name: str,
    profile_id: str,
) -> None:
    profile = era_catalogs_by_name[era_name].signatures._profiles.get(profile_id)
    assert profile is not None, f"Signature {profile_id} not found"
