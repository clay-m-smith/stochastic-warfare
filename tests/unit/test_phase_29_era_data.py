"""Phase 29: Historical Era Data Expansion — YAML loading tests.

Validates all new data files load through their respective loaders
without errors and pass spot-check assertions.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from stochastic_warfare.entities.loader import UnitLoader
from stochastic_warfare.combat.ammunition import WeaponLoader, AmmoLoader
from stochastic_warfare.detection.signatures import SignatureLoader
from stochastic_warfare.c2.communications import CommEquipmentLoader
from stochastic_warfare.c2.ai.commander import CommanderProfileLoader

ERA_DATA = Path(__file__).resolve().parents[2] / "data" / "eras"


# ── WW2 Fixtures ────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def ww2_unit_loader() -> UnitLoader:
    loader = UnitLoader(ERA_DATA / "ww2" / "units")
    loader.load_all()
    return loader


@pytest.fixture(scope="module")
def ww2_weapon_loader() -> WeaponLoader:
    loader = WeaponLoader(ERA_DATA / "ww2" / "weapons")
    loader.load_all()
    return loader


@pytest.fixture(scope="module")
def ww2_ammo_loader() -> AmmoLoader:
    loader = AmmoLoader(ERA_DATA / "ww2" / "ammunition")
    loader.load_all()
    return loader


@pytest.fixture(scope="module")
def ww2_sig_loader() -> SignatureLoader:
    loader = SignatureLoader(ERA_DATA / "ww2" / "signatures")
    loader.load_all()
    return loader


@pytest.fixture(scope="module")
def ww2_comm_loader() -> CommEquipmentLoader:
    loader = CommEquipmentLoader(ERA_DATA / "ww2" / "comms")
    loader.load_all()
    return loader


# ── WW1 Fixtures ────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def ww1_unit_loader() -> UnitLoader:
    loader = UnitLoader(ERA_DATA / "ww1" / "units")
    loader.load_all()
    return loader


@pytest.fixture(scope="module")
def ww1_weapon_loader() -> WeaponLoader:
    loader = WeaponLoader(ERA_DATA / "ww1" / "weapons")
    loader.load_all()
    return loader


@pytest.fixture(scope="module")
def ww1_ammo_loader() -> AmmoLoader:
    loader = AmmoLoader(ERA_DATA / "ww1" / "ammunition")
    loader.load_all()
    return loader


@pytest.fixture(scope="module")
def ww1_sig_loader() -> SignatureLoader:
    loader = SignatureLoader(ERA_DATA / "ww1" / "signatures")
    loader.load_all()
    return loader


# ── Napoleonic Fixtures ─────────────────────────────────────────────

@pytest.fixture(scope="module")
def nap_unit_loader() -> UnitLoader:
    loader = UnitLoader(ERA_DATA / "napoleonic" / "units")
    loader.load_all()
    return loader


@pytest.fixture(scope="module")
def nap_weapon_loader() -> WeaponLoader:
    loader = WeaponLoader(ERA_DATA / "napoleonic" / "weapons")
    loader.load_all()
    return loader


@pytest.fixture(scope="module")
def nap_ammo_loader() -> AmmoLoader:
    loader = AmmoLoader(ERA_DATA / "napoleonic" / "ammunition")
    loader.load_all()
    return loader


@pytest.fixture(scope="module")
def nap_sig_loader() -> SignatureLoader:
    loader = SignatureLoader(ERA_DATA / "napoleonic" / "signatures")
    loader.load_all()
    return loader


# ── Ancient/Medieval Fixtures ───────────────────────────────────────

@pytest.fixture(scope="module")
def anc_unit_loader() -> UnitLoader:
    loader = UnitLoader(ERA_DATA / "ancient_medieval" / "units")
    loader.load_all()
    return loader


@pytest.fixture(scope="module")
def anc_weapon_loader() -> WeaponLoader:
    loader = WeaponLoader(ERA_DATA / "ancient_medieval" / "weapons")
    loader.load_all()
    return loader


@pytest.fixture(scope="module")
def anc_ammo_loader() -> AmmoLoader:
    loader = AmmoLoader(ERA_DATA / "ancient_medieval" / "ammunition")
    loader.load_all()
    return loader


@pytest.fixture(scope="module")
def anc_sig_loader() -> SignatureLoader:
    loader = SignatureLoader(ERA_DATA / "ancient_medieval" / "signatures")
    loader.load_all()
    return loader


@pytest.fixture(scope="module")
def anc_commander_loader() -> CommanderProfileLoader:
    loader = CommanderProfileLoader(ERA_DATA / "ancient_medieval" / "commanders")
    loader.load_all()
    return loader


# ═══════════════════════════════════════════════════════════════════
# 29a — WW2 Naval & Missing Types
# ═══════════════════════════════════════════════════════════════════

_WW2_NEW_NAVAL = [
    "essex_cv", "shokaku_cv", "type_ixc_uboat", "flower_corvette", "lst_mk2",
]

_WW2_NEW_GROUND = [
    "m1_105mm_battery", "sfh18_battery", "pak40_at", "6pdr_at",
]

_WW2_NEW_AIRCRAFT = ["a6m_zero"]

_WW2_NEW_WEAPONS = [
    "mg151_20mm", "m2_50cal_aircraft", "type99_20mm",
    "g7e_torpedo", "depth_charge_mk7", "type93_torpedo",
]

_WW2_NEW_AMMO = [
    "20mm_mg151_mine", "50cal_m2_ap", "20mm_type99_he",
    "g7e_warhead", "mk7_depth_charge", "type93_warhead",
]

_WW2_NEW_SIGS = _WW2_NEW_NAVAL + _WW2_NEW_GROUND + _WW2_NEW_AIRCRAFT

_WW2_NEW_COMMS = ["field_telephone_ww2", "radio_scr300_ww2"]


class TestWW2NavalUnits:
    """WW2 naval unit loading and spot checks."""

    @pytest.mark.parametrize("unit_type", _WW2_NEW_NAVAL)
    def test_unit_loads(self, ww2_unit_loader: UnitLoader, unit_type: str) -> None:
        defn = ww2_unit_loader.get_definition(unit_type)
        assert defn.unit_type == unit_type
        assert defn.domain == "naval"
        assert defn.max_speed > 0

    def test_essex_is_carrier(self, ww2_unit_loader: UnitLoader) -> None:
        defn = ww2_unit_loader.get_definition("essex_cv")
        assert defn.naval_type == "CARRIER"
        assert defn.displacement == 27100.0

    def test_shokaku_is_carrier(self, ww2_unit_loader: UnitLoader) -> None:
        defn = ww2_unit_loader.get_definition("shokaku_cv")
        assert defn.naval_type == "CARRIER"
        assert defn.displacement == 32000.0

    def test_type_ixc_is_submarine(self, ww2_unit_loader: UnitLoader) -> None:
        defn = ww2_unit_loader.get_definition("type_ixc_uboat")
        assert defn.naval_type == "SSK"
        assert defn.max_depth == 230.0

    def test_flower_is_corvette(self, ww2_unit_loader: UnitLoader) -> None:
        defn = ww2_unit_loader.get_definition("flower_corvette")
        assert defn.naval_type == "CORVETTE"

    def test_lst_is_lst(self, ww2_unit_loader: UnitLoader) -> None:
        defn = ww2_unit_loader.get_definition("lst_mk2")
        assert defn.naval_type == "LST"


class TestWW2GroundUnits:
    """WW2 ground unit loading and spot checks."""

    @pytest.mark.parametrize("unit_type", _WW2_NEW_GROUND)
    def test_unit_loads(self, ww2_unit_loader: UnitLoader, unit_type: str) -> None:
        defn = ww2_unit_loader.get_definition(unit_type)
        assert defn.unit_type == unit_type
        assert defn.domain == "ground"

    def test_battery_is_artillery(self, ww2_unit_loader: UnitLoader) -> None:
        defn = ww2_unit_loader.get_definition("m1_105mm_battery")
        assert defn.ground_type == "ARTILLERY_TOWED"

    def test_pak40_has_gun_shield(self, ww2_unit_loader: UnitLoader) -> None:
        defn = ww2_unit_loader.get_definition("pak40_at")
        assert defn.ground_type == "ARTILLERY_TOWED"
        assert defn.armor_front > 0


class TestWW2Aircraft:
    """WW2 aircraft unit loading."""

    def test_a6m_zero_loads(self, ww2_unit_loader: UnitLoader) -> None:
        defn = ww2_unit_loader.get_definition("a6m_zero")
        assert defn.aerial_type == "FIGHTER"
        assert defn.service_ceiling == 10000.0


class TestWW2Weapons:
    """WW2 weapon loading and spot checks."""

    @pytest.mark.parametrize("weapon_id", _WW2_NEW_WEAPONS)
    def test_weapon_loads(self, ww2_weapon_loader: WeaponLoader, weapon_id: str) -> None:
        defn = ww2_weapon_loader.get_definition(weapon_id)
        assert defn.weapon_id == weapon_id

    def test_g7e_is_torpedo(self, ww2_weapon_loader: WeaponLoader) -> None:
        defn = ww2_weapon_loader.get_definition("g7e_torpedo")
        assert defn.category == "TORPEDO_TUBE"

    def test_depth_charge_mk7(self, ww2_weapon_loader: WeaponLoader) -> None:
        defn = ww2_weapon_loader.get_definition("depth_charge_mk7")
        assert defn.category == "DEPTH_CHARGE"

    def test_type93_long_range(self, ww2_weapon_loader: WeaponLoader) -> None:
        defn = ww2_weapon_loader.get_definition("type93_torpedo")
        assert defn.max_range_m == 20000.0


class TestWW2Ammo:
    """WW2 ammunition loading."""

    @pytest.mark.parametrize("ammo_id", _WW2_NEW_AMMO)
    def test_ammo_loads(self, ww2_ammo_loader: AmmoLoader, ammo_id: str) -> None:
        defn = ww2_ammo_loader.get_definition(ammo_id)
        assert defn.ammo_id == ammo_id

    def test_torpedo_warhead_is_he(self, ww2_ammo_loader: AmmoLoader) -> None:
        defn = ww2_ammo_loader.get_definition("g7e_warhead")
        assert defn.ammo_type == "HE"
        assert defn.propulsion == "torpedo"


class TestWW2Signatures:
    """WW2 signature loading."""

    @pytest.mark.parametrize("profile_id", _WW2_NEW_SIGS)
    def test_signature_loads(self, ww2_sig_loader: SignatureLoader, profile_id: str) -> None:
        profile = ww2_sig_loader.get_profile(profile_id)
        assert profile.profile_id == profile_id
        assert profile.unit_type == profile_id


class TestWW2Comms:
    """WW2 communications loading."""

    @pytest.mark.parametrize("comm_id", _WW2_NEW_COMMS)
    def test_comm_loads(self, ww2_comm_loader: CommEquipmentLoader, comm_id: str) -> None:
        defn = ww2_comm_loader.get_definition(comm_id)
        assert defn.comm_id == comm_id

    def test_field_telephone_is_wire(self, ww2_comm_loader: CommEquipmentLoader) -> None:
        defn = ww2_comm_loader.get_definition("field_telephone_ww2")
        assert defn.comm_type == "WIRE"

    def test_scr300_is_radio(self, ww2_comm_loader: CommEquipmentLoader) -> None:
        defn = ww2_comm_loader.get_definition("radio_scr300_ww2")
        assert defn.comm_type == "RADIO_VHF"


class TestWW2CrossRef:
    """WW2 cross-reference validation."""

    def test_weapon_ammo_refs_resolve(
        self, ww2_weapon_loader: WeaponLoader, ww2_ammo_loader: AmmoLoader
    ) -> None:
        for wid in _WW2_NEW_WEAPONS:
            defn = ww2_weapon_loader.get_definition(wid)
            for aid in defn.compatible_ammo:
                assert aid in ww2_ammo_loader.available_ammo(), (
                    f"Weapon {wid} references unknown ammo {aid}"
                )

    def test_all_new_units_have_signatures(
        self, ww2_unit_loader: UnitLoader, ww2_sig_loader: SignatureLoader
    ) -> None:
        for ut in _WW2_NEW_NAVAL + _WW2_NEW_GROUND + _WW2_NEW_AIRCRAFT:
            assert ut in ww2_sig_loader.available_profiles(), (
                f"Missing WW2 signature for {ut}"
            )


# ═══════════════════════════════════════════════════════════════════
# 29b — WW1 Expansion
# ═══════════════════════════════════════════════════════════════════

_WW1_NEW_NAVAL = [
    "iron_duke_bb", "konig_bb", "invincible_bc",
    "g_class_destroyer", "u_boat_ww1",
]

_WW1_NEW_GROUND = ["18pdr_battery", "fk96_battery", "us_aef_squad"]

_WW1_NEW_AIRCRAFT = ["spad_xiii", "fokker_dvii"]

_WW1_NEW_WEAPONS = [
    "12in_bl_mk_x", "15cm_sk_l45", "18in_torpedo_ww1",
    "vickers_303", "lmg08_spandau",
]

_WW1_NEW_AMMO = [
    "12in_ap_mk_viia", "15cm_he_shell", "18in_torpedo_warhead",
    "792_smk",
]

_WW1_NEW_SIGS = _WW1_NEW_NAVAL + _WW1_NEW_GROUND + _WW1_NEW_AIRCRAFT


class TestWW1NavalUnits:
    """WW1 naval unit loading and spot checks."""

    @pytest.mark.parametrize("unit_type", _WW1_NEW_NAVAL)
    def test_unit_loads(self, ww1_unit_loader: UnitLoader, unit_type: str) -> None:
        defn = ww1_unit_loader.get_definition(unit_type)
        assert defn.unit_type == unit_type
        assert defn.domain == "naval"

    def test_iron_duke_is_cruiser(self, ww1_unit_loader: UnitLoader) -> None:
        defn = ww1_unit_loader.get_definition("iron_duke_bb")
        assert defn.naval_type == "CRUISER"
        assert defn.displacement == 25000.0

    def test_u_boat_is_ssk(self, ww1_unit_loader: UnitLoader) -> None:
        defn = ww1_unit_loader.get_definition("u_boat_ww1")
        assert defn.naval_type == "SSK"
        assert defn.max_depth == 50.0

    def test_destroyer_is_destroyer(self, ww1_unit_loader: UnitLoader) -> None:
        defn = ww1_unit_loader.get_definition("g_class_destroyer")
        assert defn.naval_type == "DESTROYER"


class TestWW1GroundUnits:
    """WW1 ground unit loading and spot checks."""

    @pytest.mark.parametrize("unit_type", _WW1_NEW_GROUND)
    def test_unit_loads(self, ww1_unit_loader: UnitLoader, unit_type: str) -> None:
        defn = ww1_unit_loader.get_definition(unit_type)
        assert defn.unit_type == unit_type
        assert defn.domain == "ground"

    def test_18pdr_is_artillery(self, ww1_unit_loader: UnitLoader) -> None:
        defn = ww1_unit_loader.get_definition("18pdr_battery")
        assert defn.ground_type == "ARTILLERY_TOWED"

    def test_us_aef_is_infantry(self, ww1_unit_loader: UnitLoader) -> None:
        defn = ww1_unit_loader.get_definition("us_aef_squad")
        assert defn.ground_type == "LIGHT_INFANTRY"


class TestWW1Aircraft:
    """WW1 aircraft unit loading."""

    @pytest.mark.parametrize("unit_type", _WW1_NEW_AIRCRAFT)
    def test_aircraft_loads(self, ww1_unit_loader: UnitLoader, unit_type: str) -> None:
        defn = ww1_unit_loader.get_definition(unit_type)
        assert defn.aerial_type == "FIGHTER"


class TestWW1Weapons:
    """WW1 weapon loading."""

    @pytest.mark.parametrize("weapon_id", _WW1_NEW_WEAPONS)
    def test_weapon_loads(self, ww1_weapon_loader: WeaponLoader, weapon_id: str) -> None:
        defn = ww1_weapon_loader.get_definition(weapon_id)
        assert defn.weapon_id == weapon_id

    def test_12in_is_naval_gun(self, ww1_weapon_loader: WeaponLoader) -> None:
        defn = ww1_weapon_loader.get_definition("12in_bl_mk_x")
        assert defn.category == "NAVAL_GUN"
        assert defn.caliber_mm == 305.0

    def test_torpedo_ww1(self, ww1_weapon_loader: WeaponLoader) -> None:
        defn = ww1_weapon_loader.get_definition("18in_torpedo_ww1")
        assert defn.category == "TORPEDO_TUBE"


class TestWW1Ammo:
    """WW1 ammunition loading."""

    @pytest.mark.parametrize("ammo_id", _WW1_NEW_AMMO)
    def test_ammo_loads(self, ww1_ammo_loader: AmmoLoader, ammo_id: str) -> None:
        defn = ww1_ammo_loader.get_definition(ammo_id)
        assert defn.ammo_id == ammo_id

    def test_12in_ap_penetration(self, ww1_ammo_loader: AmmoLoader) -> None:
        defn = ww1_ammo_loader.get_definition("12in_ap_mk_viia")
        assert defn.ammo_type == "AP"
        assert defn.penetration_mm_rha == 305.0

    def test_torpedo_warhead_propulsion(self, ww1_ammo_loader: AmmoLoader) -> None:
        defn = ww1_ammo_loader.get_definition("18in_torpedo_warhead")
        assert defn.propulsion == "torpedo"


class TestWW1Signatures:
    """WW1 signature loading."""

    @pytest.mark.parametrize("profile_id", _WW1_NEW_SIGS)
    def test_signature_loads(self, ww1_sig_loader: SignatureLoader, profile_id: str) -> None:
        profile = ww1_sig_loader.get_profile(profile_id)
        assert profile.profile_id == profile_id

    def test_pre_radar_era_no_rcs(self, ww1_sig_loader: SignatureLoader) -> None:
        """WW1 units should have zero radar cross-section (no radar)."""
        for pid in _WW1_NEW_SIGS:
            profile = ww1_sig_loader.get_profile(pid)
            assert profile.radar.rcs_frontal_m2 == 0.0


# ═══════════════════════════════════════════════════════════════════
# 29c — Napoleonic Naval & Expansion
# ═══════════════════════════════════════════════════════════════════

_NAP_NEW_NAVAL = [
    "ship_of_line_74", "first_rate_100", "frigate_32",
    "corvette_sloop", "fire_ship",
]

_NAP_NEW_GROUND = [
    "dragoon_squadron", "austrian_line_infantry", "russian_line_infantry",
    "congreve_rocket_battery", "pontoon_engineer", "supply_train_nap",
]

_NAP_NEW_WEAPONS = [
    "32pdr_cannon", "24pdr_cannon", "carronade_32pdr", "congreve_rocket",
]

_NAP_NEW_AMMO = [
    "round_shot_32pdr", "chain_shot", "grape_shot_naval", "congreve_rocket_round",
]

_NAP_NEW_SIGS = _NAP_NEW_NAVAL + _NAP_NEW_GROUND


class TestNapoleonicNavalUnits:
    """Napoleonic naval unit loading and spot checks."""

    @pytest.mark.parametrize("unit_type", _NAP_NEW_NAVAL)
    def test_unit_loads(self, nap_unit_loader: UnitLoader, unit_type: str) -> None:
        defn = nap_unit_loader.get_definition(unit_type)
        assert defn.unit_type == unit_type
        assert defn.domain == "naval"

    def test_ship_of_line_is_cruiser(self, nap_unit_loader: UnitLoader) -> None:
        defn = nap_unit_loader.get_definition("ship_of_line_74")
        assert defn.naval_type == "CRUISER"
        assert defn.displacement == 1600.0

    def test_frigate_is_frigate(self, nap_unit_loader: UnitLoader) -> None:
        defn = nap_unit_loader.get_definition("frigate_32")
        assert defn.naval_type == "FRIGATE"

    def test_fire_ship_is_patrol(self, nap_unit_loader: UnitLoader) -> None:
        defn = nap_unit_loader.get_definition("fire_ship")
        assert defn.naval_type == "PATROL"


class TestNapoleonicGroundUnits:
    """Napoleonic ground unit loading and spot checks."""

    @pytest.mark.parametrize("unit_type", _NAP_NEW_GROUND)
    def test_unit_loads(self, nap_unit_loader: UnitLoader, unit_type: str) -> None:
        defn = nap_unit_loader.get_definition(unit_type)
        assert defn.unit_type == unit_type
        assert defn.domain == "ground"

    def test_dragoon_is_cavalry(self, nap_unit_loader: UnitLoader) -> None:
        defn = nap_unit_loader.get_definition("dragoon_squadron")
        assert defn.ground_type == "CAVALRY"

    def test_pontoon_is_engineer(self, nap_unit_loader: UnitLoader) -> None:
        defn = nap_unit_loader.get_definition("pontoon_engineer")
        assert defn.ground_type == "ENGINEER"

    def test_rocket_battery_type(self, nap_unit_loader: UnitLoader) -> None:
        defn = nap_unit_loader.get_definition("congreve_rocket_battery")
        assert defn.ground_type == "ROCKET_ARTILLERY"


class TestNapoleonicWeapons:
    """Napoleonic weapon loading and spot checks."""

    @pytest.mark.parametrize("weapon_id", _NAP_NEW_WEAPONS)
    def test_weapon_loads(self, nap_weapon_loader: WeaponLoader, weapon_id: str) -> None:
        defn = nap_weapon_loader.get_definition(weapon_id)
        assert defn.weapon_id == weapon_id

    def test_carronade_short_range(self, nap_weapon_loader: WeaponLoader) -> None:
        defn = nap_weapon_loader.get_definition("carronade_32pdr")
        assert defn.max_range_m == 600.0


class TestNapoleonicAmmo:
    """Napoleonic ammunition loading."""

    @pytest.mark.parametrize("ammo_id", _NAP_NEW_AMMO)
    def test_ammo_loads(self, nap_ammo_loader: AmmoLoader, ammo_id: str) -> None:
        defn = nap_ammo_loader.get_definition(ammo_id)
        assert defn.ammo_id == ammo_id

    def test_grape_shot_is_shrapnel(self, nap_ammo_loader: AmmoLoader) -> None:
        defn = nap_ammo_loader.get_definition("grape_shot_naval")
        assert defn.ammo_type == "SHRAPNEL"

    def test_congreve_is_incendiary(self, nap_ammo_loader: AmmoLoader) -> None:
        defn = nap_ammo_loader.get_definition("congreve_rocket_round")
        assert defn.ammo_type == "INCENDIARY"


class TestNapoleonicSignatures:
    """Napoleonic signature loading."""

    @pytest.mark.parametrize("profile_id", _NAP_NEW_SIGS)
    def test_signature_loads(self, nap_sig_loader: SignatureLoader, profile_id: str) -> None:
        profile = nap_sig_loader.get_profile(profile_id)
        assert profile.profile_id == profile_id


# ═══════════════════════════════════════════════════════════════════
# 29d — Ancient/Medieval Naval & Expansion
# ═══════════════════════════════════════════════════════════════════

_ANC_NEW_NAVAL = [
    "greek_trireme", "roman_quinquereme", "viking_longship",
    "byzantine_dromon", "medieval_cog", "war_galley",
]

_ANC_NEW_GROUND = [
    "byzantine_kataphraktoi", "saracen_cavalry",
    "byzantine_skutatoi", "siege_engineer",
]

_ANC_NEW_WEAPONS = ["naval_ram", "greek_fire_siphon", "corvus_boarding"]

_ANC_NEW_AMMO = ["greek_fire_charge", "ram_charge"]

_ANC_NEW_SIGS = _ANC_NEW_NAVAL + _ANC_NEW_GROUND


class TestAncientNavalUnits:
    """Ancient/Medieval naval unit loading and spot checks."""

    @pytest.mark.parametrize("unit_type", _ANC_NEW_NAVAL)
    def test_unit_loads(self, anc_unit_loader: UnitLoader, unit_type: str) -> None:
        defn = anc_unit_loader.get_definition(unit_type)
        assert defn.unit_type == unit_type
        assert defn.domain == "naval"

    def test_trireme_is_cruiser(self, anc_unit_loader: UnitLoader) -> None:
        defn = anc_unit_loader.get_definition("greek_trireme")
        assert defn.naval_type == "CRUISER"
        assert defn.displacement == 40.0

    def test_longship_is_patrol(self, anc_unit_loader: UnitLoader) -> None:
        defn = anc_unit_loader.get_definition("viking_longship")
        assert defn.naval_type == "PATROL"

    def test_dromon_is_frigate(self, anc_unit_loader: UnitLoader) -> None:
        defn = anc_unit_loader.get_definition("byzantine_dromon")
        assert defn.naval_type == "FRIGATE"

    def test_cog_is_supply(self, anc_unit_loader: UnitLoader) -> None:
        defn = anc_unit_loader.get_definition("medieval_cog")
        assert defn.naval_type == "SUPPLY_SHIP"

    def test_war_galley_is_destroyer(self, anc_unit_loader: UnitLoader) -> None:
        defn = anc_unit_loader.get_definition("war_galley")
        assert defn.naval_type == "DESTROYER"


class TestAncientGroundUnits:
    """Ancient/Medieval ground unit loading and spot checks."""

    @pytest.mark.parametrize("unit_type", _ANC_NEW_GROUND)
    def test_unit_loads(self, anc_unit_loader: UnitLoader, unit_type: str) -> None:
        defn = anc_unit_loader.get_definition(unit_type)
        assert defn.unit_type == unit_type
        assert defn.domain == "ground"

    def test_kataphraktoi_is_armor(self, anc_unit_loader: UnitLoader) -> None:
        defn = anc_unit_loader.get_definition("byzantine_kataphraktoi")
        assert defn.ground_type == "ARMOR"
        assert defn.armor_front > 0

    def test_siege_engineer_type(self, anc_unit_loader: UnitLoader) -> None:
        defn = anc_unit_loader.get_definition("siege_engineer")
        assert defn.ground_type == "ENGINEER"


class TestAncientCommander:
    """Ancient/Medieval commander loading."""

    def test_subotai_loads(self, anc_commander_loader: CommanderProfileLoader) -> None:
        defn = anc_commander_loader.get_definition("mongol_subotai")
        assert defn.profile_id == "mongol_subotai"
        assert defn.aggression >= 0.7
        assert defn.experience >= 0.9


class TestAncientWeapons:
    """Ancient/Medieval weapon loading and spot checks."""

    @pytest.mark.parametrize("weapon_id", _ANC_NEW_WEAPONS)
    def test_weapon_loads(self, anc_weapon_loader: WeaponLoader, weapon_id: str) -> None:
        defn = anc_weapon_loader.get_definition(weapon_id)
        assert defn.weapon_id == weapon_id

    def test_ram_is_melee(self, anc_weapon_loader: WeaponLoader) -> None:
        defn = anc_weapon_loader.get_definition("naval_ram")
        assert defn.category == "MELEE"

    def test_greek_fire_range(self, anc_weapon_loader: WeaponLoader) -> None:
        defn = anc_weapon_loader.get_definition("greek_fire_siphon")
        assert defn.max_range_m == 30.0


class TestAncientAmmo:
    """Ancient/Medieval ammunition loading."""

    @pytest.mark.parametrize("ammo_id", _ANC_NEW_AMMO)
    def test_ammo_loads(self, anc_ammo_loader: AmmoLoader, ammo_id: str) -> None:
        defn = anc_ammo_loader.get_definition(ammo_id)
        assert defn.ammo_id == ammo_id

    def test_greek_fire_is_incendiary(self, anc_ammo_loader: AmmoLoader) -> None:
        defn = anc_ammo_loader.get_definition("greek_fire_charge")
        assert defn.ammo_type == "INCENDIARY"


class TestAncientSignatures:
    """Ancient/Medieval signature loading."""

    @pytest.mark.parametrize("profile_id", _ANC_NEW_SIGS)
    def test_signature_loads(self, anc_sig_loader: SignatureLoader, profile_id: str) -> None:
        profile = anc_sig_loader.get_profile(profile_id)
        assert profile.profile_id == profile_id

    def test_all_new_units_have_signatures(
        self, anc_unit_loader: UnitLoader, anc_sig_loader: SignatureLoader
    ) -> None:
        for ut in _ANC_NEW_NAVAL + _ANC_NEW_GROUND:
            assert ut in anc_sig_loader.available_profiles(), (
                f"Missing Ancient/Medieval signature for {ut}"
            )
