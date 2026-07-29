"""Source-bounded historical weapon semantics introduced by Phase 109."""

from __future__ import annotations

from pathlib import Path

import pytest

from stochastic_warfare.combat.ammunition import (
    AmmoLoader,
    AmmoType,
    GuidanceType,
    WeaponCategory,
    WeaponLoader,
)


DATA_DIR = Path(__file__).parents[2] / "data" / "eras"

WW1_WEAPONS = (
    (
        "sk_l30_88mm",
        WeaponCategory.NAVAL_GUN,
        88.0,
        116,
        ("88mm_c07_he",),
        {"GROUND", "NAVAL"},
    ),
    (
        "qf_4in_mk_iii",
        WeaponCategory.NAVAL_GUN,
        101.6,
        100,
        ("4in_mk_iii_he",),
        {"GROUND", "NAVAL"},
    ),
    (
        "qf_4in_mk_iv",
        WeaponCategory.NAVAL_GUN,
        101.6,
        1,
        ("4in_mk_iv_he",),
        {"GROUND", "NAVAL"},
    ),
    (
        "bl_6in_mk_vii",
        WeaponCategory.NAVAL_GUN,
        152.4,
        130,
        ("6in_mk_vii_cpc",),
        {"GROUND", "NAVAL"},
    ),
    (
        "bl_13_5in_mk_v",
        WeaponCategory.NAVAL_GUN,
        343.0,
        100,
        ("13_5in_apc_mk_ia",),
        {"GROUND", "NAVAL"},
    ),
)

WW2_WEAPONS = (
    (
        "qf_6pdr_l50",
        WeaponCategory.CANNON,
        57.0,
        1,
        ("57mm_apcbc_mk9t",),
        {"GROUND"},
    ),
    (
        "kwk42_75mm",
        WeaponCategory.CANNON,
        75.0,
        79,
        ("75mm_pzgr39_42_apcbc",),
        {"GROUND"},
    ),
    (
        "sk_c35_88mm",
        WeaponCategory.NAVAL_GUN,
        88.0,
        220,
        ("88mm_c35_he",),
        {"GROUND", "NAVAL"},
    ),
    (
        "sk_c32_105mm",
        WeaponCategory.NAVAL_GUN,
        105.0,
        110,
        ("105mm_c32_he",),
        {"GROUND", "NAVAL"},
    ),
    (
        "bl_4in_mk_ix",
        WeaponCategory.NAVAL_GUN,
        101.6,
        1,
        ("4in_mk_ix_he",),
        {"GROUND", "NAVAL"},
    ),
    (
        "browning_303_mk_ii",
        WeaponCategory.AIRCRAFT_GUN,
        7.7,
        350,
        ("303_mk_vii_ball",),
        {"GROUND", "AERIAL"},
    ),
    (
        "type97_77mm_aircraft_mg",
        WeaponCategory.AIRCRAFT_GUN,
        7.7,
        500,
        ("77x56r_type97_ball",),
        {"GROUND", "AERIAL"},
    ),
    (
        "dp28_lmg",
        WeaponCategory.LIGHT_MG,
        7.62,
        47,
        ("762x54r_l_ball_ww2",),
        {"GROUND"},
    ),
    (
        "dt_762mm",
        WeaponCategory.MACHINE_GUN,
        7.62,
        60,
        ("762x54r_l_ball_ww2",),
        {"GROUND"},
    ),
    (
        "m1918a2_bar",
        WeaponCategory.LIGHT_MG,
        7.62,
        20,
        ("30_06_m2_ball",),
        {"GROUND"},
    ),
    (
        "bofors_40mm_l60",
        WeaponCategory.AAA,
        40.0,
        8,
        ("bofors_40mm_he",),
        {"AERIAL"},
    ),
    (
        "oerlikon_20mm_mk4",
        WeaponCategory.AAA,
        20.0,
        60,
        ("oerlikon_20mm_he",),
        {"AERIAL"},
    ),
    (
        "type96_25mm",
        WeaponCategory.AAA,
        25.0,
        15,
        ("type96_25mm_he",),
        {"AERIAL"},
    ),
    (
        "qf_2pdr_mk_viii",
        WeaponCategory.AAA,
        40.0,
        56,
        ("2pdr_pompom_he",),
        {"AERIAL"},
    ),
    (
        "flak_c30_20mm",
        WeaponCategory.AAA,
        20.0,
        20,
        ("20mm_c30_hei",),
        {"AERIAL"},
    ),
    (
        "flak_m42_37mm",
        WeaponCategory.AAA,
        37.0,
        5,
        ("37mm_m42_he",),
        {"AERIAL"},
    ),
    (
        "type89_127mm",
        WeaponCategory.AAA,
        127.0,
        250,
        ("type89_127mm_he",),
        {"AERIAL"},
    ),
    (
        "hedgehog_mk10",
        WeaponCategory.DEPTH_CHARGE,
        182.88,
        24,
        ("hedgehog_mk10_projectile",),
        {"SUBMARINE"},
    ),
)

AMMO_TYPES = {
    "88mm_c07_he": AmmoType.HE,
    "4in_mk_iii_he": AmmoType.HE,
    "4in_mk_iv_he": AmmoType.HE,
    "6in_mk_vii_cpc": AmmoType.AP,
    "13_5in_apc_mk_ia": AmmoType.AP,
    "57mm_apcbc_mk9t": AmmoType.AP,
    "75mm_pzgr39_42_apcbc": AmmoType.AP,
    "88mm_c35_he": AmmoType.HE,
    "105mm_c32_he": AmmoType.HE,
    "4in_mk_ix_he": AmmoType.HE,
    "303_mk_vii_ball": AmmoType.BALL,
    "77x56r_type97_ball": AmmoType.BALL,
    "762x54r_l_ball_ww2": AmmoType.BALL,
    "30_06_m2_ball": AmmoType.BALL,
    "bofors_40mm_he": AmmoType.HE,
    "oerlikon_20mm_he": AmmoType.HE,
    "type96_25mm_he": AmmoType.HE,
    "2pdr_pompom_he": AmmoType.HE,
    "20mm_c30_hei": AmmoType.HE,
    "37mm_m42_he": AmmoType.HE,
    "type89_127mm_he": AmmoType.HE,
    "hedgehog_mk10_projectile": AmmoType.HE,
}


@pytest.fixture(scope="module")
def ww1_weapon_loader() -> WeaponLoader:
    loader = WeaponLoader(DATA_DIR / "ww1" / "weapons")
    loader.load_all()
    return loader


@pytest.fixture(scope="module")
def ww1_ammo_loader() -> AmmoLoader:
    loader = AmmoLoader(DATA_DIR / "ww1" / "ammunition")
    loader.load_all()
    return loader


@pytest.fixture(scope="module")
def ww2_weapon_loader() -> WeaponLoader:
    loader = WeaponLoader(DATA_DIR / "ww2" / "weapons")
    loader.load_all()
    return loader


@pytest.fixture(scope="module")
def ww2_ammo_loader() -> AmmoLoader:
    loader = AmmoLoader(DATA_DIR / "ww2" / "ammunition")
    loader.load_all()
    return loader


@pytest.mark.parametrize(
    ("weapon_id", "category", "caliber", "capacity", "ammo_ids", "domains"),
    WW1_WEAPONS,
)
def test_ww1_exact_weapon_semantics(
    weapon_id: str,
    category: WeaponCategory,
    caliber: float,
    capacity: int,
    ammo_ids: tuple[str, ...],
    domains: set[str],
    ww1_weapon_loader: WeaponLoader,
    ww1_ammo_loader: AmmoLoader,
) -> None:
    _assert_weapon_semantics(
        ww1_weapon_loader,
        ww1_ammo_loader,
        weapon_id,
        category,
        caliber,
        capacity,
        ammo_ids,
        domains,
    )


@pytest.mark.parametrize(
    ("weapon_id", "category", "caliber", "capacity", "ammo_ids", "domains"),
    WW2_WEAPONS,
)
def test_ww2_exact_weapon_semantics(
    weapon_id: str,
    category: WeaponCategory,
    caliber: float,
    capacity: int,
    ammo_ids: tuple[str, ...],
    domains: set[str],
    ww2_weapon_loader: WeaponLoader,
    ww2_ammo_loader: AmmoLoader,
) -> None:
    _assert_weapon_semantics(
        ww2_weapon_loader,
        ww2_ammo_loader,
        weapon_id,
        category,
        caliber,
        capacity,
        ammo_ids,
        domains,
    )


def _assert_weapon_semantics(
    weapon_loader: WeaponLoader,
    ammo_loader: AmmoLoader,
    weapon_id: str,
    category: WeaponCategory,
    caliber: float,
    capacity: int,
    ammo_ids: tuple[str, ...],
    domains: set[str],
) -> None:
    weapon = weapon_loader.get_definition(weapon_id)

    assert weapon.parsed_category() is category
    assert weapon.caliber_mm == caliber
    assert weapon.parsed_guidance() is GuidanceType.NONE
    assert weapon.magazine_capacity == capacity
    assert tuple(weapon.compatible_ammo) == ammo_ids
    assert weapon.effective_target_domains() == domains
    assert set(weapon.target_domains) == domains
    assert 0.0 < weapon.effective_range_m <= weapon.max_range_m
    assert weapon.rate_of_fire_rpm > 0.0

    lowered_name = weapon.display_name.lower()
    assert "(x" not in lowered_name
    assert "twin" not in lowered_name
    assert "triple" not in lowered_name
    assert "quad" not in lowered_name
    assert "battery role model" not in lowered_name

    for ammo_id in ammo_ids:
        ammo = ammo_loader.get_definition(ammo_id)
        assert ammo.diameter_mm == caliber
        assert ammo.parsed_ammo_type() is AMMO_TYPES[ammo_id]
        assert ammo.parsed_guidance() is GuidanceType.NONE


def test_historical_definitions_keep_mount_multiplicity_out_of_weapon_identity(
    ww1_weapon_loader: WeaponLoader,
    ww2_weapon_loader: WeaponLoader,
) -> None:
    definitions = (
        *(ww1_weapon_loader.get_definition(row[0]) for row in WW1_WEAPONS),
        *(ww2_weapon_loader.get_definition(row[0]) for row in WW2_WEAPONS),
    )

    assert len({definition.weapon_id for definition in definitions}) == len(definitions)
    assert all("(x" not in definition.display_name.lower() for definition in definitions)


@pytest.mark.parametrize(
    ("relative_path", "source_fragment"),
    (
        ("ww1/weapons/naval/sk_l30_88mm.yaml", "navweaps.com"),
        ("ww1/weapons/naval/qf_4in_mk_iii.yaml", "cgsc.contentdm.oclc.org"),
        ("ww1/weapons/naval/bl_13_5in_mk_v.yaml", "navweaps.com"),
        ("ww2/weapons/guns/qf_6pdr_l50.yaml", "ibiblio.org"),
        ("ww2/weapons/guns/kwk42_75mm.yaml", "tankmuseum.org"),
        ("ww2/weapons/air/browning_303_mk_ii.yaml", "iwm.org.uk"),
        ("ww2/weapons/air/type97_77mm_aircraft_mg.yaml", "awm.gov.au"),
        ("ww2/weapons/naval/type89_127mm.yaml", "ibiblio.org"),
        ("ww2/weapons/naval/hedgehog_mk10.yaml", "history.navy.mil"),
    ),
)
def test_representative_definitions_retain_traceable_source_comments(
    relative_path: str,
    source_fragment: str,
) -> None:
    text = (DATA_DIR / relative_path).read_text(encoding="utf-8")

    assert source_fragment in text
