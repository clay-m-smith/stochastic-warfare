"""Canonical exact/variant equipment-mapping contracts across all eras."""

from __future__ import annotations

from collections import Counter
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
from stochastic_warfare.core.types import Domain, Position
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


DATA_DIR = Path(__file__).parents[3] / "data"


@dataclass(frozen=True, slots=True)
class _ExpectedMapping:
    era: str
    unit_type: str
    equipment_name: str
    weapon_id: str
    category: WeaponCategory
    role: WeaponModeledRole
    caliber_mm: float
    ammunition: tuple[tuple[str, AmmoType], ...]
    reference_kind: ReferenceKind
    guidance: GuidanceType
    required_domains: tuple[Domain, ...]
    catalog_domains: tuple[Domain, ...]
    replaced_weapon_ids: tuple[str, ...]
    verify_catalog_domains: bool
    catalog_domain_ordered: bool
    verify_ammunition_guidance: bool
    verify_ammunition_diameter: bool


def _single(
    era: str,
    unit_type: str,
    equipment_name: str,
    weapon_id: str,
    category: WeaponCategory,
    role: WeaponModeledRole,
    ammo_id: str,
    ammo_type: AmmoType,
    caliber_mm: float,
    *,
    reference_kind: ReferenceKind = ReferenceKind.EXACT,
    guidance: GuidanceType = GuidanceType.NONE,
    required_domains: tuple[Domain, ...] | None = None,
    catalog_domains: tuple[Domain, ...] | None = None,
    replaced_weapon_id: str | None = None,
    verify_catalog_contract: bool = False,
    verify_catalog_domains: bool = False,
    catalog_domain_ordered: bool = False,
    verify_ammunition_guidance: bool = False,
    verify_ammunition_diameter: bool = False,
) -> _ExpectedMapping:
    domains = (
        required_domains_for_weapon_role(role)
        if required_domains is None
        else required_domains
    )
    return _ExpectedMapping(
        era=era,
        unit_type=unit_type,
        equipment_name=equipment_name,
        weapon_id=weapon_id,
        category=category,
        role=role,
        caliber_mm=caliber_mm,
        ammunition=((ammo_id, ammo_type),),
        reference_kind=reference_kind,
        guidance=guidance,
        required_domains=domains,
        catalog_domains=domains if catalog_domains is None else catalog_domains,
        replaced_weapon_ids=(
            () if replaced_weapon_id is None else (replaced_weapon_id,)
        ),
        verify_catalog_domains=(
            verify_catalog_contract
            or verify_catalog_domains
            or verify_ammunition_diameter
        ),
        catalog_domain_ordered=(
            verify_catalog_contract or catalog_domain_ordered
        ),
        verify_ammunition_guidance=(
            verify_catalog_contract
            or verify_ammunition_guidance
            or verify_ammunition_diameter
        ),
        verify_ammunition_diameter=verify_ammunition_diameter,
    )


def _multi(
    era: str,
    unit_type: str,
    equipment_name: str,
    weapon_id: str,
    category: WeaponCategory,
    role: WeaponModeledRole,
    ammunition: tuple[tuple[str, AmmoType], ...],
    caliber_mm: float,
    *,
    guidance: GuidanceType = GuidanceType.NONE,
    required_domains: tuple[Domain, ...] | None = None,
    catalog_domains: tuple[Domain, ...] | None = None,
    replaced_weapon_id: str | None = None,
) -> _ExpectedMapping:
    domains = (
        required_domains_for_weapon_role(role)
        if required_domains is None
        else required_domains
    )
    return _ExpectedMapping(
        era=era,
        unit_type=unit_type,
        equipment_name=equipment_name,
        weapon_id=weapon_id,
        category=category,
        role=role,
        caliber_mm=caliber_mm,
        ammunition=ammunition,
        reference_kind=ReferenceKind.EXACT,
        guidance=guidance,
        required_domains=domains,
        catalog_domains=domains if catalog_domains is None else catalog_domains,
        replaced_weapon_ids=(
            () if replaced_weapon_id is None else (replaced_weapon_id,)
        ),
        verify_catalog_domains=True,
        catalog_domain_ordered=False,
        verify_ammunition_guidance=True,
        verify_ammunition_diameter=False,
    )


_EXPECTED_MAPPINGS = (
    # Cross-era follow-up repairs. These retain explicit catalog domains and
    # the former proxy target as a negative oracle.
    _single(
        "modern",
        "bmp2",
        "9P135M ATGM Launcher",
        "9p135m_konkurs",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.ANTI_ARMOR,
        "9m113_konkurs",
        AmmoType.HEAT,
        135.0,
        guidance=GuidanceType.WIRE,
        required_domains=(Domain.GROUND,),
        catalog_domains=(Domain.GROUND,),
        replaced_weapon_id="at3_sagger",
        verify_ammunition_diameter=True,
    ),
    _single(
        "modern",
        "qatari_amx30b2",
        "F1 105mm Rifled Gun",
        "cn105_f1_105mm",
        WeaponCategory.CANNON,
        WeaponModeledRole.GROUND_DIRECT_FIRE,
        "occ_105_f1_heat",
        AmmoType.HEAT,
        105.0,
        required_domains=(Domain.GROUND,),
        catalog_domains=(Domain.GROUND,),
        replaced_weapon_id="l7_105mm",
        verify_ammunition_diameter=True,
    ),
    _single(
        "ww1",
        "french_poilu_squad",
        "Lebel Mle 1886 M93 Rifle",
        "lebel_m1886_m93",
        WeaponCategory.RIFLE,
        WeaponModeledRole.BOLT_ACTION_RIFLE,
        "8x50r_lebel_balle_d",
        AmmoType.BALL,
        8.0,
        required_domains=(Domain.GROUND,),
        catalog_domains=(Domain.GROUND,),
        replaced_weapon_id="lee_enfield",
        verify_ammunition_diameter=True,
    ),
    _single(
        "ww1",
        "french_poilu_squad",
        "Chauchat M1915 CSRG Light Machine Gun",
        "chauchat_m1915",
        WeaponCategory.LIGHT_MG,
        WeaponModeledRole.LIGHT_MACHINE_GUN,
        "8x50r_lebel_balle_d",
        AmmoType.BALL,
        8.0,
        required_domains=(Domain.GROUND,),
        catalog_domains=(Domain.GROUND,),
        replaced_weapon_id="lewis_gun",
        verify_ammunition_diameter=True,
    ),
    _single(
        "ww1",
        "us_aef_squad",
        "M1918 BAR",
        "m1918a2_bar",
        WeaponCategory.LIGHT_MG,
        WeaponModeledRole.LIGHT_MACHINE_GUN,
        "30_06_m1906_ball",
        AmmoType.BALL,
        7.62,
        required_domains=(Domain.GROUND,),
        catalog_domains=(Domain.GROUND,),
        replaced_weapon_id="lewis_gun",
        verify_ammunition_diameter=True,
    ),
    _single(
        "modern",
        "t90a",
        "NSVT 12.7mm HMG",
        "nsvt_127mm",
        WeaponCategory.HEAVY_MG,
        WeaponModeledRole.HEAVY_MACHINE_GUN,
        "12_7x108_api",
        AmmoType.AP,
        12.7,
        required_domains=(Domain.GROUND,),
        catalog_domains=(Domain.GROUND, Domain.AERIAL),
        replaced_weapon_id="m2hb_50cal",
        verify_ammunition_diameter=True,
    ),
    _single(
        "ww2",
        "spitfire_ix",
        "Hispano Mk II 20mm Cannon (x2)",
        "hispano_mk_ii_20mm",
        WeaponCategory.AUTOCANNON,
        WeaponModeledRole.AIRCRAFT_GUN,
        "20mm_hispano_mk_ii_he",
        AmmoType.HE,
        20.0,
        required_domains=(Domain.GROUND, Domain.AERIAL),
        catalog_domains=(Domain.GROUND, Domain.AERIAL),
        replaced_weapon_id="mg151_20mm",
        verify_ammunition_diameter=True,
    ),
    _single(
        "ww2",
        "bf109g",
        "MG 131 13mm Machine Gun (x2)",
        "mg131_13mm",
        WeaponCategory.HEAVY_MG,
        WeaponModeledRole.AIRCRAFT_GUN,
        "13mm_mg131_he",
        AmmoType.HE,
        13.0,
        required_domains=(Domain.GROUND, Domain.AERIAL),
        catalog_domains=(Domain.GROUND, Domain.AERIAL),
        replaced_weapon_id="m2_50cal_aircraft",
        verify_ammunition_diameter=True,
    ),
    # Historical exact-identity repairs.
    _single(
        "ww1",
        "iron_duke_bb",
        "BL 13.5-inch Mk V Gun (5x2 turrets)",
        "bl_13_5in_mk_v",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        "13_5in_apc_mk_ia",
        AmmoType.AP,
        343.0,
    ),
    _single(
        "ww1",
        "iron_duke_bb",
        "BL 6-inch Mk VII Gun (x12)",
        "bl_6in_mk_vii",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        "6in_mk_vii_cpc",
        AmmoType.AP,
        152.4,
    ),
    _single(
        "ww1",
        "g_class_destroyer",
        "QF 4-inch Mk IV Gun (x3)",
        "qf_4in_mk_iv",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        "4in_mk_iv_he",
        AmmoType.HE,
        101.6,
    ),
    _single(
        "ww1",
        "u_boat_ww1",
        "8.8cm SK L/30 Deck Gun",
        "sk_l30_88mm",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        "88mm_c07_he",
        AmmoType.HE,
        88.0,
    ),
    _single(
        "ww1",
        "invincible_bc",
        "QF 4-inch Mk III Gun (x16)",
        "qf_4in_mk_iii",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        "4in_mk_iii_he",
        AmmoType.HE,
        101.6,
    ),
    _single(
        "ww2",
        "6pdr_at",
        "QF 6-Pounder (57mm) L/50",
        "qf_6pdr_l50",
        WeaponCategory.CANNON,
        WeaponModeledRole.GROUND_DIRECT_FIRE,
        "57mm_apcbc_mk9t",
        AmmoType.AP,
        57.0,
    ),
    _single(
        "ww2",
        "panther",
        "75mm KwK 42 L/70 Gun",
        "kwk42_75mm",
        WeaponCategory.CANNON,
        WeaponModeledRole.GROUND_DIRECT_FIRE,
        "75mm_pzgr39_42_apcbc",
        AmmoType.AP,
        75.0,
    ),
    _single(
        "ww2",
        "type_viic_uboat",
        "8.8cm SK C/35 Deck Gun",
        "sk_c35_88mm",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        "88mm_c35_he",
        AmmoType.HE,
        88.0,
    ),
    _single(
        "ww2",
        "type_ixc_uboat",
        "10.5cm SK C/32 Deck Gun",
        "sk_c32_105mm",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        "105mm_c32_he",
        AmmoType.HE,
        105.0,
    ),
    _single(
        "ww2",
        "flower_corvette",
        "BL 4-inch Mk IX Gun",
        "bl_4in_mk_ix",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        "4in_mk_ix_he",
        AmmoType.HE,
        101.6,
    ),
    _single(
        "ww2",
        "spitfire_ix",
        "Browning .303 Machine Gun (x4)",
        "browning_303_mk_ii",
        WeaponCategory.AIRCRAFT_GUN,
        WeaponModeledRole.AIRCRAFT_GUN,
        "303_mk_vii_ball",
        AmmoType.BALL,
        7.7,
    ),
    _single(
        "ww2",
        "a6m_zero",
        "Type 97 7.7mm MG (x2)",
        "type97_77mm_aircraft_mg",
        WeaponCategory.AIRCRAFT_GUN,
        WeaponModeledRole.AIRCRAFT_GUN,
        "77x56r_type97_ball",
        AmmoType.BALL,
        7.7,
    ),
    _single(
        "ww2",
        "soviet_rifle_squad",
        "DP-28 Light Machine Gun",
        "dp28_lmg",
        WeaponCategory.LIGHT_MG,
        WeaponModeledRole.LIGHT_MACHINE_GUN,
        "762x54r_l_ball_ww2",
        AmmoType.BALL,
        7.62,
    ),
    _single(
        "ww2",
        "t34_85",
        "DT 7.62mm Coaxial MG",
        "dt_762mm",
        WeaponCategory.MACHINE_GUN,
        WeaponModeledRole.GENERAL_PURPOSE_MACHINE_GUN,
        "762x54r_l_ball_ww2",
        AmmoType.BALL,
        7.62,
    ),
    _single(
        "ww2",
        "us_rifle_squad_ww2",
        "M1918A2 BAR",
        "m1918a2_bar",
        WeaponCategory.LIGHT_MG,
        WeaponModeledRole.LIGHT_MACHINE_GUN,
        "30_06_m2_ball",
        AmmoType.BALL,
        7.62,
    ),
    _single(
        "ww2",
        "flower_corvette",
        "2-pdr Pom-Pom",
        "qf_2pdr_mk_viii",
        WeaponCategory.AAA,
        WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN,
        "2pdr_pompom_he",
        AmmoType.HE,
        40.0,
    ),
    _single(
        "ww2",
        "type_viic_uboat",
        "2cm FlaK C/30 AA Gun",
        "flak_c30_20mm",
        WeaponCategory.AAA,
        WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN,
        "20mm_c30_hei",
        AmmoType.HE,
        20.0,
    ),
    _single(
        "ww2",
        "type_ixc_uboat",
        "3.7cm FlaK M42 AA Gun",
        "flak_m42_37mm",
        WeaponCategory.AAA,
        WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN,
        "37mm_m42_he",
        AmmoType.HE,
        37.0,
    ),
    _single(
        "ww2",
        "iowa_bb",
        "Bofors 40mm Quad Mount (x20)",
        "bofors_40mm_l60",
        WeaponCategory.AAA,
        WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN,
        "bofors_40mm_he",
        AmmoType.HE,
        40.0,
    ),
    _single(
        "ww2",
        "essex_cv",
        "Bofors 40mm Quad Mount (x8)",
        "bofors_40mm_l60",
        WeaponCategory.AAA,
        WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN,
        "bofors_40mm_he",
        AmmoType.HE,
        40.0,
    ),
    _single(
        "ww2",
        "lst_mk2",
        "Bofors 40mm Twin Mount (x2)",
        "bofors_40mm_l60",
        WeaponCategory.AAA,
        WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN,
        "bofors_40mm_he",
        AmmoType.HE,
        40.0,
    ),
    _single(
        "ww2",
        "fletcher_dd",
        "Bofors 40mm Twin Mount (x5)",
        "bofors_40mm_l60",
        WeaponCategory.AAA,
        WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN,
        "bofors_40mm_he",
        AmmoType.HE,
        40.0,
    ),
    _single(
        "ww2",
        "essex_cv",
        "Oerlikon 20mm (x46)",
        "oerlikon_20mm_mk4",
        WeaponCategory.AAA,
        WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN,
        "oerlikon_20mm_he",
        AmmoType.HE,
        20.0,
    ),
    _single(
        "ww2",
        "iowa_bb",
        "Oerlikon 20mm (x49)",
        "oerlikon_20mm_mk4",
        WeaponCategory.AAA,
        WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN,
        "oerlikon_20mm_he",
        AmmoType.HE,
        20.0,
    ),
    _single(
        "ww2",
        "lst_mk2",
        "Oerlikon 20mm (x6)",
        "oerlikon_20mm_mk4",
        WeaponCategory.AAA,
        WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN,
        "oerlikon_20mm_he",
        AmmoType.HE,
        20.0,
    ),
    _single(
        "ww2",
        "fletcher_dd",
        "Oerlikon 20mm (x7)",
        "oerlikon_20mm_mk4",
        WeaponCategory.AAA,
        WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN,
        "oerlikon_20mm_he",
        AmmoType.HE,
        20.0,
    ),
    _single(
        "ww2",
        "shokaku_cv",
        "Type 96 25mm Triple Mount (x12)",
        "type96_25mm",
        WeaponCategory.AAA,
        WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN,
        "type96_25mm_he",
        AmmoType.HE,
        25.0,
    ),
    _single(
        "ww2",
        "shokaku_cv",
        "Type 89 12.7cm AA Gun (8x2)",
        "type89_127mm",
        WeaponCategory.AAA,
        WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN,
        "type89_127mm_he",
        AmmoType.HE,
        127.0,
    ),
    _single(
        "ww2",
        "flower_corvette",
        "Hedgehog ASW Mortar",
        "hedgehog_mk10",
        WeaponCategory.DEPTH_CHARGE,
        WeaponModeledRole.ANTI_SUBMARINE,
        "hedgehog_mk10_projectile",
        AmmoType.HE,
        182.88,
    ),
    # Modern exact and explicitly reviewed variant identities.
    _single(
        "modern",
        "mi24v",
        "9M114 Shturm-V Launcher",
        "shturm_v_9m114",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.AIR_TO_GROUND_MISSILE,
        "9m114_shturm",
        AmmoType.HEAT,
        130.0,
        guidance=GuidanceType.COMMAND,
    ),
    _single(
        "modern",
        "mi24v",
        "YakB-12.7 Gatling Gun",
        "yakb_127mm",
        WeaponCategory.AIRCRAFT_GUN,
        WeaponModeledRole.AIRCRAFT_GUN,
        "yakb_12_7x108_api",
        AmmoType.AP,
        12.7,
    ),
    _single(
        "modern",
        "f15e",
        "AIM-7M Sparrow",
        "aim7m_sparrow",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.AIR_TO_AIR_MISSILE,
        "aim7m_sparrow",
        AmmoType.MISSILE,
        200.0,
        guidance=GuidanceType.RADAR_SEMI,
    ),
    _single(
        "modern",
        "f15e",
        "AIM-9L Sidewinder",
        "aim9l_sidewinder",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.AIR_TO_AIR_MISSILE,
        "aim9l_sidewinder",
        AmmoType.MISSILE,
        130.0,
        guidance=GuidanceType.IR,
    ),
    _single(
        "modern",
        "s300pmu",
        "5P85 TEL",
        "s300pmu_5p85",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.AIR_DEFENSE_MISSILE,
        "48n6_sam",
        AmmoType.MISSILE,
        500.0,
        reference_kind=ReferenceKind.VARIANT,
        guidance=GuidanceType.COMBINED,
    ),
    _single(
        "modern",
        "sa11_buk",
        "9A310 TELAR",
        "buk_m1_9a310",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.AIR_DEFENSE_MISSILE,
        "9m38m1_sam",
        AmmoType.MISSILE,
        400.0,
        reference_kind=ReferenceKind.VARIANT,
        guidance=GuidanceType.RADAR_SEMI,
    ),
    _single(
        "modern",
        "iraqi_foreign_fighter",
        "PKM GPMG",
        "pkm_762x54r",
        WeaponCategory.MACHINE_GUN,
        WeaponModeledRole.GENERAL_PURPOSE_MACHINE_GUN,
        "762x54r_ball",
        AmmoType.BALL,
        7.62,
    ),
    _single(
        "modern",
        "iraqi_foreign_fighter",
        "AK-74",
        "ak74_545mm",
        WeaponCategory.RIFLE,
        WeaponModeledRole.ASSAULT_RIFLE,
        "545x39_ball",
        AmmoType.BALL,
        5.45,
        reference_kind=ReferenceKind.VARIANT,
    ),
    _single(
        "modern",
        "idf_egoz_team",
        "IMI Negev 5.56mm LMG",
        "negev_ng5_lmg",
        WeaponCategory.LIGHT_MG,
        WeaponModeledRole.LIGHT_MACHINE_GUN,
        "556_ss109_ball",
        AmmoType.BALL,
        5.56,
        reference_kind=ReferenceKind.VARIANT,
    ),
    _single(
        "modern",
        "us_marine_recon_team",
        "M249 SAW",
        "m249_saw",
        WeaponCategory.LIGHT_MG,
        WeaponModeledRole.LIGHT_MACHINE_GUN,
        "556_m855a1_linked",
        AmmoType.BALL,
        5.56,
    ),
    _single(
        "modern",
        "t72m",
        "PKT 7.62mm Coaxial",
        "pkt_762x54r",
        WeaponCategory.MACHINE_GUN,
        WeaponModeledRole.GENERAL_PURPOSE_MACHINE_GUN,
        "762x54r_ball",
        AmmoType.BALL,
        7.62,
    ),
    _single(
        "modern",
        "btr80",
        "KPVT 14.5mm HMG",
        "kpvt_145mm",
        WeaponCategory.HEAVY_MG,
        WeaponModeledRole.HEAVY_MACHINE_GUN,
        "145x114_bzt561sm",
        AmmoType.AP,
        14.5,
    ),
    _single(
        "modern",
        "btr80",
        "PKT 7.62mm MG",
        "pkt_762x54r",
        WeaponCategory.MACHINE_GUN,
        WeaponModeledRole.GENERAL_PURPOSE_MACHINE_GUN,
        "762x54r_ball",
        AmmoType.BALL,
        7.62,
    ),
    _single(
        "modern",
        "iraqi_mtlb",
        "PKT 7.62mm Machine Gun",
        "pkt_762x54r",
        WeaponCategory.MACHINE_GUN,
        WeaponModeledRole.GENERAL_PURPOSE_MACHINE_GUN,
        "762x54r_ball",
        AmmoType.BALL,
        7.62,
    ),
    _single(
        "modern",
        "t55a",
        "SGMT 7.62mm Coaxial",
        "sgmt_762x54r",
        WeaponCategory.MACHINE_GUN,
        WeaponModeledRole.GENERAL_PURPOSE_MACHINE_GUN,
        "762x54r_ball",
        AmmoType.BALL,
        7.62,
    ),
    _single(
        "modern",
        "qatari_amx30b2",
        "20mm M693 Coaxial",
        "m693_20mm",
        WeaponCategory.AUTOCANNON,
        WeaponModeledRole.GROUND_DIRECT_FIRE,
        "20x139_m693_hei",
        AmmoType.HE,
        20.0,
    ),
    _single(
        "modern",
        "type42_destroyer",
        "4.5 inch Mk 8 Naval Gun",
        "mk8_45in",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        "45in_mk8_n20_he",
        AmmoType.HE,
        114.3,
    ),
    _single(
        "modern",
        "super_etendard",
        "DEFA 553 30mm Cannon",
        "defa553_30mm",
        WeaponCategory.AIRCRAFT_GUN,
        WeaponModeledRole.AIRCRAFT_GUN,
        "30x113b_defa_hei",
        AmmoType.HE,
        30.0,
    ),
    _single(
        "modern",
        "j10a",
        "GSh-23 23mm Cannon",
        "gsh23_23mm",
        WeaponCategory.AIRCRAFT_GUN,
        WeaponModeledRole.AIRCRAFT_GUN,
        "23x115_hei",
        AmmoType.HE,
        23.0,
    ),
    _single(
        "modern",
        "su27s",
        "GSh-30-1 30mm Cannon",
        "gsh30_1_30mm",
        WeaponCategory.AIRCRAFT_GUN,
        WeaponModeledRole.AIRCRAFT_GUN,
        "30x165_gsh_ap_t",
        AmmoType.AP,
        30.0,
    ),
    _single(
        "modern",
        "lhd1",
        "RAM Launcher",
        "rim116_ram",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.AIR_DEFENSE_MISSILE,
        "rim116_block1a",
        AmmoType.MISSILE,
        127.0,
        reference_kind=ReferenceKind.VARIANT,
        guidance=GuidanceType.COMBINED,
    ),
    _single(
        "modern",
        "type22_frigate",
        "Sea Wolf SAM",
        "sea_wolf_sam",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.AIR_DEFENSE_MISSILE,
        "sea_wolf_gws25",
        AmmoType.MISSILE,
        180.0,
        reference_kind=ReferenceKind.VARIANT,
        guidance=GuidanceType.COMMAND,
    ),
    # Residual modern proxy repairs.
    _single(
        "modern",
        "ah64d",
        "M230 Chain Gun 30mm",
        "m230_chain_gun",
        WeaponCategory.AIRCRAFT_GUN,
        WeaponModeledRole.AIRCRAFT_GUN,
        "30x113_m789_hedp",
        AmmoType.HEAT,
        30.0,
        verify_catalog_contract=True,
    ),
    _single(
        "modern",
        "sea_harrier",
        "30mm ADEN",
        "aden_30mm",
        WeaponCategory.AIRCRAFT_GUN,
        WeaponModeledRole.AIRCRAFT_GUN,
        "30x113b_aden_hei",
        AmmoType.HE,
        30.0,
        verify_catalog_contract=True,
    ),
    _single(
        "modern",
        "sovremenny",
        "3M80 Moskit Launcher",
        "3m80_moskit",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.ANTI_SHIP_MISSILE,
        "3m80_moskit",
        AmmoType.MISSILE,
        760.0,
        guidance=GuidanceType.COMBINED,
        verify_catalog_contract=True,
    ),
    _single(
        "modern",
        "kilo636",
        "533mm Torpedo Tubes x6",
        "project636_533mm_torpedo_tube",
        WeaponCategory.TORPEDO_TUBE,
        WeaponModeledRole.TORPEDO,
        "ugst_torpedo",
        AmmoType.TORPEDO,
        533.0,
        guidance=GuidanceType.COMBINED,
        verify_catalog_contract=True,
    ),
    _single(
        "modern",
        "ranger_plt",
        "Carl Gustaf M3",
        "carl_gustaf_m3",
        WeaponCategory.ROCKET_LAUNCHER,
        WeaponModeledRole.ANTI_ARMOR,
        "carl_gustaf_heat551",
        AmmoType.HEAT,
        84.0,
        verify_catalog_contract=True,
    ),
    _single(
        "modern",
        "iraqi_insurgent_mortar_team",
        "Iraqi 82mm 2B14 Mortar",
        "2b14_82mm_mortar",
        WeaponCategory.MORTAR,
        WeaponModeledRole.MORTAR_FIRE,
        "o832du_82mm_he",
        AmmoType.HE,
        82.0,
        verify_catalog_contract=True,
    ),
    _single(
        "modern",
        "sovremenny",
        "AK-130 130mm Twin Gun",
        "ak130_130mm",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        "ak130_he_frag",
        AmmoType.HE,
        130.0,
        verify_catalog_contract=True,
    ),
    _single(
        "modern",
        "challenger2",
        "L30A1 120mm Rifled Gun",
        "l30a1_120mm",
        WeaponCategory.CANNON,
        WeaponModeledRole.GROUND_DIRECT_FIRE,
        "l27a1_charm3_apfsds",
        AmmoType.AP,
        120.0,
        verify_catalog_contract=True,
    ),
    _single(
        "modern",
        "leopard2a6",
        "Rh-120 L/55 120mm Smoothbore",
        "rh120_l55_120mm",
        WeaponCategory.CANNON,
        WeaponModeledRole.GROUND_DIRECT_FIRE,
        "dm53_apfsds",
        AmmoType.AP,
        120.0,
        verify_catalog_contract=True,
    ),
    # Residual historical repairs, including ordered multi-ammunition pairs.
    _multi(
        "ww1",
        "konig_bb",
        "30.5cm SK L/50 Gun (5x2 turrets)",
        "sk_l50_305mm",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        (
            ("305mm_psgr_l3_4_apc", AmmoType.AP),
            ("305mm_spgr_l3_8_he", AmmoType.HE),
        ),
        305.0,
        required_domains=(Domain.GROUND, Domain.NAVAL),
        replaced_weapon_id="12in_bl_mk_x",
    ),
    _multi(
        "ww1",
        "g_class_destroyer",
        "21-inch Torpedo Tubes (x2x2)",
        "british_21in_torpedo_ww1",
        WeaponCategory.TORPEDO_TUBE,
        WeaponModeledRole.TORPEDO,
        (("british_21in_mk_ii_warhead", AmmoType.HE),),
        533.0,
        required_domains=(Domain.NAVAL, Domain.SUBMARINE),
        replaced_weapon_id="18in_torpedo_ww1",
    ),
    _multi(
        "ww1",
        "iron_duke_bb",
        "21-inch Torpedo Tubes (x4)",
        "british_21in_torpedo_ww1",
        WeaponCategory.TORPEDO_TUBE,
        WeaponModeledRole.TORPEDO,
        (("british_21in_mk_ii_warhead", AmmoType.HE),),
        533.0,
        required_domains=(Domain.NAVAL, Domain.SUBMARINE),
        replaced_weapon_id="18in_torpedo_ww1",
    ),
    _multi(
        "ww1",
        "u_boat_ww1",
        "45cm Torpedo Tubes (x4)",
        "c06d_45cm_torpedo_ww1",
        WeaponCategory.TORPEDO_TUBE,
        WeaponModeledRole.TORPEDO,
        (("c06d_45cm_warhead", AmmoType.HE),),
        450.0,
        required_domains=(Domain.NAVAL, Domain.SUBMARINE),
        replaced_weapon_id="18in_torpedo_ww1",
    ),
    _multi(
        "ww1",
        "konig_bb",
        "50cm Torpedo Tubes (x5)",
        "g7_50cm_torpedo_ww1",
        WeaponCategory.TORPEDO_TUBE,
        WeaponModeledRole.TORPEDO,
        (("g7_50cm_warhead", AmmoType.HE),),
        500.0,
        required_domains=(Domain.NAVAL, Domain.SUBMARINE),
        replaced_weapon_id="18in_torpedo_ww1",
    ),
    _multi(
        "napoleonic",
        "ship_of_line_74",
        "18-pdr Long Guns (upper deck, x30)",
        "18pdr_naval",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        (
            ("round_shot_18pdr", AmmoType.AP),
            ("grape_shot_18pdr", AmmoType.SHRAPNEL),
        ),
        134.4,
        required_domains=(Domain.GROUND, Domain.NAVAL),
        replaced_weapon_id="24pdr_cannon",
    ),
    _multi(
        "napoleonic",
        "first_rate_100",
        "18-pdr Long Guns (upper deck, x34)",
        "18pdr_naval",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        (
            ("round_shot_18pdr", AmmoType.AP),
            ("grape_shot_18pdr", AmmoType.SHRAPNEL),
        ),
        134.4,
        required_domains=(Domain.GROUND, Domain.NAVAL),
        replaced_weapon_id="24pdr_cannon",
    ),
    _multi(
        "napoleonic",
        "corvette_sloop",
        "Carronades 24-pdr (x2)",
        "carronade_24pdr",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        (
            ("round_shot_24pdr_carronade", AmmoType.AP),
            ("grape_shot_24pdr_carronade", AmmoType.SHRAPNEL),
        ),
        144.0,
        required_domains=(Domain.GROUND, Domain.NAVAL),
        replaced_weapon_id="carronade_32pdr",
    ),
    _multi(
        "ww2",
        "pak40_at",
        "7.5cm PaK 40 L/46",
        "pak40_l46_75mm",
        WeaponCategory.CANNON,
        WeaponModeledRole.GROUND_DIRECT_FIRE,
        (
            ("75mm_pzgr39_pak40_apcbc", AmmoType.AP),
            ("75mm_sprgr34_pak40_he", AmmoType.HE),
        ),
        75.0,
        required_domains=(Domain.GROUND,),
        replaced_weapon_id="75mm_m3",
    ),
    _multi(
        "ww2",
        "panzer_iv_h",
        "75mm KwK 40 L/48 Gun",
        "kwk40_l48_75mm",
        WeaponCategory.CANNON,
        WeaponModeledRole.GROUND_DIRECT_FIRE,
        (
            ("75mm_pzgr39_kwk40_apcbc", AmmoType.AP),
            ("75mm_sprgr34_kwk40_he", AmmoType.HE),
        ),
        75.0,
        required_domains=(Domain.GROUND,),
        replaced_weapon_id="75mm_m3",
    ),
)


_CATALOG_DRIFT_CASES = (
    pytest.param(
        "aim7m_sparrow",
        "f15e",
        {"guidance": "IR"},
        "guidance IR does not match required RADAR_SEMI",
        id="sparrow-guidance",
    ),
    pytest.param(
        "aim7m_sparrow",
        "f15e",
        {"caliber_mm": 130.0},
        "caliber 130.0 mm does not match required 200.0 mm",
        id="sparrow-caliber",
    ),
    pytest.param(
        "aim7m_sparrow",
        "f15e",
        {"compatible_ammo": ["aim9l_sidewinder"]},
        "does not declare mapping-allowed ammunition",
        id="sparrow-ammunition",
    ),
    pytest.param(
        "aim7m_sparrow",
        "f15e",
        {"target_domains": ["GROUND"]},
        "lacks required target domains",
        id="sparrow-domain",
    ),
    pytest.param(
        "m230_chain_gun",
        "ah64d",
        {"caliber_mm": 20.0},
        "caliber 20.0 mm does not match required 30.0 mm",
        id="m230-caliber",
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
        for loader, loader_type, child in (
            (weapon_loader, WeaponLoader, "weapons"),
            (ammo_loader, AmmoLoader, "ammunition"),
            (sensor_loader, SensorLoader, "sensors"),
            (unit_loader, UnitLoader, "units"),
        ):
            era_loader = loader_type(era_root / child)
            era_loader.load_all()
            loader._definitions.update(era_loader.definitions())

    return weapon_loader, ammo_loader, sensor_loader, unit_loader


def _builder(
    era: str,
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
        era_config=get_era_config(era),
        assignment_overrides=(),
        reachable_unit_types=unit_types,
        registry=EQUIPMENT_MAPPING_REGISTRY,
    )


def test_exact_mapping_contract_table_is_complete_and_unique() -> None:
    assert len(_EXPECTED_MAPPINGS) == 78
    assert len({item.equipment_name for item in _EXPECTED_MAPPINGS}) == 78
    assert Counter(item.era for item in _EXPECTED_MAPPINGS) == {
        "modern": 34,
        "ww1": 13,
        "ww2": 28,
        "napoleonic": 3,
    }
    assert Counter(item.reference_kind for item in _EXPECTED_MAPPINGS) == {
        ReferenceKind.EXACT: 72,
        ReferenceKind.VARIANT: 6,
    }


@pytest.mark.parametrize(
    "expected",
    _EXPECTED_MAPPINGS,
    ids=lambda item: item.equipment_name,
)
def test_registry_declares_canonical_weapon_mapping_contract(
    expected: _ExpectedMapping,
) -> None:
    record = EQUIPMENT_MAPPING_REGISTRY.require(
        EquipmentCategory.WEAPON,
        expected.equipment_name,
    )

    assert isinstance(record, WeaponAttachmentMapping)
    assert record.weapon_id == expected.weapon_id
    assert record.weapon_id not in expected.replaced_weapon_ids
    assert record.expected_weapon_category is expected.category
    assert record.modeled_role is expected.role
    assert record.reference_kind is expected.reference_kind
    assert record.required_ammo_types == tuple(
        ammo_type for _, ammo_type in expected.ammunition
    )
    assert record.allowed_ammo_ids == tuple(
        ammo_id for ammo_id, _ in expected.ammunition
    )
    assert record.required_target_domains == expected.required_domains
    assert record.expected_caliber_mm == expected.caliber_mm
    assert record.expected_guidance is expected.guidance
    assert record.allowed_target_ids == ()
    assert record.rationale is None
    assert record.source is None


@pytest.mark.parametrize("era", ("modern", "ww1", "ww2", "napoleonic"))
def test_exact_mappings_load_and_build_through_runtime_boundary(
    era: str,
) -> None:
    expected_rows = tuple(
        expected for expected in _EXPECTED_MAPPINGS if expected.era == era
    )
    unit_types = tuple(dict.fromkeys(row.unit_type for row in expected_rows))
    weapon_loader, ammo_loader, sensor_loader, unit_loader = (
        _load_effective_catalogs(era)
    )
    builder = _builder(
        era,
        weapon_loader,
        ammo_loader,
        sensor_loader,
        unit_loader,
        unit_types,
    )
    rng = np.random.default_rng(109)
    units = tuple(
        unit_loader.create_unit(
            unit_type,
            f"exact-mapping-{era}-{index}",
            Position(float(index * 100), 0.0),
            "blue",
            rng,
        )
        for index, unit_type in enumerate(unit_types)
    )

    loadouts = builder.build(units)
    units_by_type = {unit.unit_type: unit for unit in units}
    observed_equipment: set[str] = set()
    for expected in expected_rows:
        definition = weapon_loader.get_definition(expected.weapon_id)
        ammunition_ids = tuple(
            ammo_id for ammo_id, _ in expected.ammunition
        )
        assert definition.parsed_category() is expected.category
        assert definition.caliber_mm == expected.caliber_mm
        assert definition.parsed_guidance() is expected.guidance
        assert tuple(definition.compatible_ammo) == ammunition_ids
        if expected.verify_catalog_domains:
            expected_domain_names = tuple(
                domain.name for domain in expected.catalog_domains
            )
            if expected.catalog_domain_ordered:
                assert tuple(definition.target_domains) == expected_domain_names
            else:
                assert frozenset(definition.effective_target_domains()) == (
                    frozenset(expected_domain_names)
                )
        for ammo_id, ammo_type in expected.ammunition:
            ammunition = ammo_loader.get_definition(ammo_id)
            assert ammunition.parsed_ammo_type() is ammo_type
            if expected.verify_ammunition_guidance:
                assert ammunition.parsed_guidance() is expected.guidance
            if expected.verify_ammunition_diameter:
                assert ammunition.diameter_mm == expected.caliber_mm

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
        observed_equipment.add(attachment.source_equipment.name)

        scaled_capacity = (
            definition.magazine_capacity
            * attachment.runtime_system_multiplier
        )
        assert attachment.weapon.weapon_id == expected.weapon_id
        assert tuple(item.ammo_id for item in attachment.ammunition) == (
            ammunition_ids
        )
        assert attachment.weapon.definition.compatible_ammo == list(
            ammunition_ids,
        )
        assert attachment.weapon.definition.target_domains == [
            domain.name for domain in expected.required_domains
        ]
        assert attachment.weapon.definition.magazine_capacity == scaled_capacity
        assert attachment.weapon.ammo_state.rounds_by_type == {
            ammo_id: scaled_capacity for ammo_id in ammunition_ids
        }
        assert attachment.weapon.equipment is attachment.source_equipment
        assert attachment.mapping_rationale is None
        assert attachment.mapping_source is None
        assert resolution.disposition is ResolutionDisposition.ATTACHMENT
        assert resolution.target_id == expected.weapon_id
        assert resolution.modeled_role is expected.role
        assert resolution.reference_kind is expected.reference_kind
        assert resolution.source_system_count == attachment.source_system_count
        assert resolution.target_system_count == attachment.target_system_count
        assert (
            resolution.runtime_system_multiplier
            == attachment.runtime_system_multiplier
        )

    assert observed_equipment == {
        expected.equipment_name for expected in expected_rows
    }


@pytest.mark.parametrize(
    ("weapon_id", "unit_type", "definition_update", "message"),
    _CATALOG_DRIFT_CASES,
)
def test_exact_mapping_rejects_semantically_incompatible_catalog_target(
    weapon_id: str,
    unit_type: str,
    definition_update: dict[str, Any],
    message: str,
) -> None:
    weapon_loader, ammo_loader, sensor_loader, unit_loader = (
        _load_effective_catalogs("modern")
    )
    definition = weapon_loader.get_definition(weapon_id)
    weapon_loader._definitions[weapon_id] = definition.model_copy(
        update=definition_update,
    )

    with pytest.raises(EquipmentMappingError, match=message):
        _builder(
            "modern",
            weapon_loader,
            ammo_loader,
            sensor_loader,
            unit_loader,
            (unit_type,),
        )


def test_invincible_catalog_uses_qf_mk_iii_identity() -> None:
    loader = UnitLoader(DATA_DIR / "eras" / "ww1" / "units")
    definition = loader.load_definition(
        DATA_DIR / "eras" / "ww1" / "units" / "naval" / "invincible_bc.yaml",
    )
    weapon_names = {
        equipment.name
        for equipment in definition.equipment
        if equipment.category == "WEAPON"
    }

    assert "QF 4-inch Mk III Gun (x16)" in weapon_names
    assert "BL 4-inch Mk III Gun (x16)" not in weapon_names
    assert (
        EQUIPMENT_MAPPING_REGISTRY.get(
            EquipmentCategory.WEAPON,
            "BL 4-inch Mk III Gun (x16)",
        )
        is None
    )
