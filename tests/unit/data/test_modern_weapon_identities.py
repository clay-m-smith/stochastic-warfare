"""Exact modern weapon identities introduced by Phase 109."""

from __future__ import annotations


import pytest

from stochastic_warfare.combat.ammunition import (
    AmmoLoader,
    AmmoType,
    GuidanceType,
    WeaponCategory,
    WeaponLoader,
)


@pytest.mark.parametrize(
    (
        "weapon_id",
        "category",
        "caliber_mm",
        "guidance",
        "magazine_capacity",
        "ammo_ids",
        "domains",
    ),
    (
        (
            "yakb_127mm",
            WeaponCategory.AIRCRAFT_GUN,
            12.7,
            GuidanceType.NONE,
            1470,
            ("yakb_12_7x108_api",),
            {"GROUND", "AERIAL"},
        ),
        (
            "shturm_v_9m114",
            WeaponCategory.MISSILE_LAUNCHER,
            130.0,
            GuidanceType.COMMAND,
            8,
            ("9m114_shturm",),
            {"GROUND"},
        ),
        (
            "s300pmu_5p85",
            WeaponCategory.MISSILE_LAUNCHER,
            500.0,
            GuidanceType.COMBINED,
            4,
            ("48n6_sam",),
            {"AERIAL"},
        ),
        (
            "buk_m1_9a310",
            WeaponCategory.MISSILE_LAUNCHER,
            400.0,
            GuidanceType.RADAR_SEMI,
            4,
            ("9m38m1_sam",),
            {"AERIAL"},
        ),
        (
            "rim116_ram",
            WeaponCategory.MISSILE_LAUNCHER,
            127.0,
            GuidanceType.COMBINED,
            21,
            ("rim116_block1a",),
            {"AERIAL"},
        ),
        (
            "sea_wolf_sam",
            WeaponCategory.MISSILE_LAUNCHER,
            180.0,
            GuidanceType.COMMAND,
            6,
            ("sea_wolf_gws25",),
            {"AERIAL"},
        ),
        (
            "aim7m_sparrow",
            WeaponCategory.MISSILE_LAUNCHER,
            200.0,
            GuidanceType.RADAR_SEMI,
            4,
            ("aim7m_sparrow",),
            {"AERIAL"},
        ),
        (
            "aim9l_sidewinder",
            WeaponCategory.MISSILE_LAUNCHER,
            130.0,
            GuidanceType.IR,
            4,
            ("aim9l_sidewinder",),
            {"AERIAL"},
        ),
        (
            "gsh23_23mm",
            WeaponCategory.AIRCRAFT_GUN,
            23.0,
            GuidanceType.NONE,
            200,
            ("23x115_hei",),
            {"GROUND", "AERIAL"},
        ),
        (
            "gsh30_1_30mm",
            WeaponCategory.AIRCRAFT_GUN,
            30.0,
            GuidanceType.NONE,
            150,
            ("30x165_gsh_ap_t",),
            {"GROUND", "AERIAL"},
        ),
        (
            "defa553_30mm",
            WeaponCategory.AIRCRAFT_GUN,
            30.0,
            GuidanceType.NONE,
            125,
            ("30x113b_defa_hei",),
            {"GROUND", "AERIAL"},
        ),
        (
            "m693_20mm",
            WeaponCategory.AUTOCANNON,
            20.0,
            GuidanceType.NONE,
            480,
            ("20x139_m693_hei",),
            {"GROUND", "AERIAL"},
        ),
        (
            "kpvt_145mm",
            WeaponCategory.HEAVY_MG,
            14.5,
            GuidanceType.NONE,
            500,
            ("145x114_bzt561sm",),
            {"GROUND", "AERIAL"},
        ),
        (
            "negev_ng5_lmg",
            WeaponCategory.LIGHT_MG,
            5.56,
            GuidanceType.NONE,
            150,
            ("556_ss109_ball",),
            {"GROUND"},
        ),
        (
            "m249_saw",
            WeaponCategory.LIGHT_MG,
            5.56,
            GuidanceType.NONE,
            200,
            ("556_m855a1_linked",),
            {"GROUND"},
        ),
        (
            "pkm_762x54r",
            WeaponCategory.MACHINE_GUN,
            7.62,
            GuidanceType.NONE,
            200,
            ("762x54r_ball",),
            {"GROUND"},
        ),
        (
            "pkt_762x54r",
            WeaponCategory.MACHINE_GUN,
            7.62,
            GuidanceType.NONE,
            250,
            ("762x54r_ball",),
            {"GROUND"},
        ),
        (
            "sgmt_762x54r",
            WeaponCategory.MACHINE_GUN,
            7.62,
            GuidanceType.NONE,
            250,
            ("762x54r_ball",),
            {"GROUND"},
        ),
        (
            "ak74_545mm",
            WeaponCategory.RIFLE,
            5.45,
            GuidanceType.NONE,
            30,
            ("545x39_ball",),
            {"GROUND"},
        ),
        (
            "mk8_45in",
            WeaponCategory.NAVAL_GUN,
            114.3,
            GuidanceType.NONE,
            22,
            ("45in_mk8_n20_he",),
            {"GROUND", "NAVAL", "AERIAL"},
        ),
    ),
)
def test_exact_weapon_identity_and_runtime_semantics(
    weapon_id: str,
    category: WeaponCategory,
    caliber_mm: float,
    guidance: GuidanceType,
    magazine_capacity: int,
    ammo_ids: tuple[str, ...],
    domains: set[str],
    weapon_loader: WeaponLoader,
    ammo_loader: AmmoLoader,
) -> None:
    definition = weapon_loader.get_definition(weapon_id)

    assert definition.weapon_id == weapon_id
    assert definition.parsed_category() is category
    assert definition.caliber_mm == caliber_mm
    assert definition.parsed_guidance() is guidance
    assert definition.magazine_capacity == magazine_capacity
    assert tuple(definition.compatible_ammo) == ammo_ids
    assert set(definition.target_domains) == domains
    assert definition.effective_target_domains() == domains

    for ammo_id in ammo_ids:
        ammunition = ammo_loader.get_definition(ammo_id)
        assert ammunition.ammo_id == ammo_id
        assert ammunition.diameter_mm == caliber_mm
        assert ammunition.parsed_guidance() is guidance


@pytest.mark.parametrize(
    ("ammo_id", "ammo_type", "guidance"),
    (
        ("yakb_12_7x108_api", AmmoType.AP, GuidanceType.NONE),
        ("9m114_shturm", AmmoType.HEAT, GuidanceType.COMMAND),
        ("48n6_sam", AmmoType.MISSILE, GuidanceType.COMBINED),
        ("9m38m1_sam", AmmoType.MISSILE, GuidanceType.RADAR_SEMI),
        ("rim116_block1a", AmmoType.MISSILE, GuidanceType.COMBINED),
        ("sea_wolf_gws25", AmmoType.MISSILE, GuidanceType.COMMAND),
        ("aim7m_sparrow", AmmoType.MISSILE, GuidanceType.RADAR_SEMI),
        ("aim9l_sidewinder", AmmoType.MISSILE, GuidanceType.IR),
        ("23x115_hei", AmmoType.HE, GuidanceType.NONE),
        ("30x165_gsh_ap_t", AmmoType.AP, GuidanceType.NONE),
        ("30x113b_defa_hei", AmmoType.HE, GuidanceType.NONE),
        ("20x139_m693_hei", AmmoType.HE, GuidanceType.NONE),
        ("145x114_bzt561sm", AmmoType.AP, GuidanceType.NONE),
        ("556_ss109_ball", AmmoType.BALL, GuidanceType.NONE),
        ("556_m855a1_linked", AmmoType.BALL, GuidanceType.NONE),
        ("762x54r_ball", AmmoType.BALL, GuidanceType.NONE),
        ("545x39_ball", AmmoType.BALL, GuidanceType.NONE),
        ("45in_mk8_n20_he", AmmoType.HE, GuidanceType.NONE),
    ),
)
def test_exact_ammunition_identity_and_typed_semantics(
    ammo_id: str,
    ammo_type: AmmoType,
    guidance: GuidanceType,
    ammo_loader: AmmoLoader,
) -> None:
    definition = ammo_loader.get_definition(ammo_id)

    assert definition.ammo_id == ammo_id
    assert definition.parsed_ammo_type() is ammo_type
    assert definition.parsed_guidance() is guidance
