"""Phase 28: Modern Era Data Package — YAML loading tests.

Validates all new data files load through their respective loaders
without errors and pass spot-check assertions.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from stochastic_warfare.entities.loader import UnitLoader
from stochastic_warfare.combat.ammunition import WeaponLoader, AmmoLoader
from stochastic_warfare.detection.sensors import SensorLoader
from stochastic_warfare.detection.signatures import SignatureLoader
from stochastic_warfare.entities.organization.orbat import OrbatLoader
from stochastic_warfare.c2.ai.doctrine import DoctrineTemplateLoader
from stochastic_warfare.c2.ai.commander import CommanderProfileLoader
from stochastic_warfare.escalation.ladder import EscalationLadderConfig

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def unit_loader() -> UnitLoader:
    loader = UnitLoader(DATA_DIR / "units")
    loader.load_all()
    return loader


@pytest.fixture(scope="module")
def weapon_loader() -> WeaponLoader:
    loader = WeaponLoader(DATA_DIR / "weapons")
    loader.load_all()
    return loader


@pytest.fixture(scope="module")
def ammo_loader() -> AmmoLoader:
    loader = AmmoLoader(DATA_DIR / "ammunition")
    loader.load_all()
    return loader


@pytest.fixture(scope="module")
def sensor_loader() -> SensorLoader:
    loader = SensorLoader(DATA_DIR / "sensors")
    loader.load_all()
    return loader


@pytest.fixture(scope="module")
def sig_loader() -> SignatureLoader:
    loader = SignatureLoader(DATA_DIR / "signatures")
    loader.load_all()
    return loader


@pytest.fixture(scope="module")
def doctrine_loader() -> DoctrineTemplateLoader:
    loader = DoctrineTemplateLoader(DATA_DIR / "doctrine")
    loader.load_all()
    return loader


@pytest.fixture(scope="module")
def commander_loader() -> CommanderProfileLoader:
    loader = CommanderProfileLoader(DATA_DIR / "commander_profiles")
    loader.load_all()
    return loader


# ── 28a Units ────────────────────────────────────────────────────────

_NEW_UNIT_TYPES = [
    "mig29a", "su27s", "j10a",
    "bmp2", "btr80", "t90a",
    "sovremenny", "kilo636",
    "sa11_buk", "s300pmu",
    "leopard2a6", "challenger2",
    "b52h", "ea18g", "mi24v", "c17",
    "javelin_team", "kornet_team", "engineer_squad",
]


class TestPhase28aUnits:
    """Loading and spot-checks for 19 new unit types."""

    @pytest.mark.parametrize("unit_type", _NEW_UNIT_TYPES)
    def test_unit_loads(self, unit_loader: UnitLoader, unit_type: str) -> None:
        defn = unit_loader.get_definition(unit_type)
        assert defn.unit_type == unit_type
        assert defn.max_speed > 0

    def test_t90a_armor_type(self, unit_loader: UnitLoader) -> None:
        defn = unit_loader.get_definition("t90a")
        assert defn.armor_type == "COMPOSITE"
        assert defn.armor_front == 800.0

    def test_kilo636_is_submarine(self, unit_loader: UnitLoader) -> None:
        defn = unit_loader.get_definition("kilo636")
        assert defn.domain == "submarine"
        assert defn.naval_type == "SSK"
        assert defn.max_depth == 300.0

    def test_sa11_buk_is_sam_medium(self, unit_loader: UnitLoader) -> None:
        defn = unit_loader.get_definition("sa11_buk")
        assert defn.ad_type == "SAM_MEDIUM"
        assert defn.max_engagement_range == 35000.0

    def test_ea18g_is_ew(self, unit_loader: UnitLoader) -> None:
        defn = unit_loader.get_definition("ea18g")
        assert defn.aerial_type == "EW"

    def test_b52h_is_bomber(self, unit_loader: UnitLoader) -> None:
        defn = unit_loader.get_definition("b52h")
        assert defn.aerial_type == "BOMBER"
        assert defn.service_ceiling == 15200.0

    def test_bmp2_armor_type(self, unit_loader: UnitLoader) -> None:
        defn = unit_loader.get_definition("bmp2")
        assert defn.armor_type == "ALUMINUM"
        assert defn.ground_type == "MECHANIZED_INFANTRY"

    def test_adversary_fighters_count(self, unit_loader: UnitLoader) -> None:
        adversary_fighters = {"mig29a", "su27s", "j10a"}
        loaded = set(unit_loader.available_types())
        assert adversary_fighters.issubset(loaded)

    def test_adversary_ground_beyond_t72(self, unit_loader: UnitLoader) -> None:
        adversary_ground = {"t90a", "bmp2", "btr80"}
        loaded = set(unit_loader.available_types())
        assert adversary_ground.issubset(loaded)

    def test_adversary_naval(self, unit_loader: UnitLoader) -> None:
        adversary_naval = {"sovremenny", "kilo636"}
        loaded = set(unit_loader.available_types())
        assert adversary_naval.issubset(loaded)

    def test_engineer_squad_ground_type(self, unit_loader: UnitLoader) -> None:
        defn = unit_loader.get_definition("engineer_squad")
        assert defn.ground_type == "ENGINEER"

    def test_javelin_team_light_infantry(self, unit_loader: UnitLoader) -> None:
        defn = unit_loader.get_definition("javelin_team")
        assert defn.ground_type == "LIGHT_INFANTRY"

    def test_mi24v_attack_helo(self, unit_loader: UnitLoader) -> None:
        defn = unit_loader.get_definition("mi24v")
        assert defn.aerial_type == "ATTACK_HELO"


# ── 28b Weapons ──────────────────────────────────────────────────────

_NEW_WEAPON_IDS = [
    "agm88_harm", "r77", "r73", "igla_9k38",
    "2a42_30mm", "javelin_clm", "kornet_9m133",
    "asroc_rur5", "mk54_torpedo",
]


class TestPhase28bWeapons:
    """Loading and spot-checks for 9 new weapon definitions."""

    @pytest.mark.parametrize("weapon_id", _NEW_WEAPON_IDS)
    def test_weapon_loads(self, weapon_loader: WeaponLoader, weapon_id: str) -> None:
        defn = weapon_loader.get_definition(weapon_id)
        assert defn.weapon_id == weapon_id

    def test_harm_guidance(self, weapon_loader: WeaponLoader) -> None:
        defn = weapon_loader.get_definition("agm88_harm")
        assert defn.guidance == "RADAR_ACTIVE"
        assert defn.max_range_m == 150000.0

    def test_javelin_guidance(self, weapon_loader: WeaponLoader) -> None:
        defn = weapon_loader.get_definition("javelin_clm")
        assert defn.guidance == "IR"
        assert defn.max_range_m == 2500.0

    def test_kornet_guidance(self, weapon_loader: WeaponLoader) -> None:
        defn = weapon_loader.get_definition("kornet_9m133")
        assert defn.guidance == "LASER"
        assert defn.requires_deployed is True

    def test_2a42_is_cannon(self, weapon_loader: WeaponLoader) -> None:
        defn = weapon_loader.get_definition("2a42_30mm")
        assert defn.category == "CANNON"
        assert defn.rate_of_fire_rpm == 550.0


# ── 28b Ammunition ───────────────────────────────────────────────────

_NEW_AMMO_IDS = [
    "30mm_m789_hedp", "30mm_3uor6_hei",
    "mk82_500lb", "mk84_2000lb", "gbu12_paveway", "gbu38_jdam",
    "m720_mortar_he", "m853a1_illumination",
    "mk54_warhead", "asroc_payload",
    "agm88_harm_warhead", "r77_warhead", "r73_warhead", "igla_warhead",
    "javelin_warhead", "kornet_warhead",
]


class TestPhase28bAmmo:
    """Loading and spot-checks for 16 new ammo definitions."""

    @pytest.mark.parametrize("ammo_id", _NEW_AMMO_IDS)
    def test_ammo_loads(self, ammo_loader: AmmoLoader, ammo_id: str) -> None:
        defn = ammo_loader.get_definition(ammo_id)
        assert defn.ammo_id == ammo_id

    def test_gbu12_is_guided(self, ammo_loader: AmmoLoader) -> None:
        defn = ammo_loader.get_definition("gbu12_paveway")
        assert defn.ammo_type == "GUIDED"
        assert defn.guidance == "LASER"

    def test_gbu38_gps(self, ammo_loader: AmmoLoader) -> None:
        defn = ammo_loader.get_definition("gbu38_jdam")
        assert defn.guidance == "GPS"

    def test_javelin_penetration(self, ammo_loader: AmmoLoader) -> None:
        defn = ammo_loader.get_definition("javelin_warhead")
        assert defn.penetration_mm_rha == 750.0

    def test_kornet_penetration(self, ammo_loader: AmmoLoader) -> None:
        defn = ammo_loader.get_definition("kornet_warhead")
        assert defn.penetration_mm_rha == 1200.0

    def test_illumination_type(self, ammo_loader: AmmoLoader) -> None:
        defn = ammo_loader.get_definition("m853a1_illumination")
        assert defn.ammo_type == "ILLUMINATION"


# ── 28b Sensors ──────────────────────────────────────────────────────

_NEW_SENSOR_IDS = [
    "apg68_radar", "apy1_radar", "aaq33_sniper",
    "sqr19_towed_array", "uv_maws",
]


class TestPhase28bSensors:
    """Loading and spot-checks for 5 new sensor definitions."""

    @pytest.mark.parametrize("sensor_id", _NEW_SENSOR_IDS)
    def test_sensor_loads(self, sensor_loader: SensorLoader, sensor_id: str) -> None:
        defn = sensor_loader.get_definition(sensor_id)
        assert defn.sensor_id == sensor_id

    def test_apg68_is_radar(self, sensor_loader: SensorLoader) -> None:
        defn = sensor_loader.get_definition("apg68_radar")
        assert defn.sensor_type == "RADAR"
        assert defn.max_range_m == 296000.0

    def test_sqr19_is_passive_sonar(self, sensor_loader: SensorLoader) -> None:
        defn = sensor_loader.get_definition("sqr19_towed_array")
        assert defn.sensor_type == "PASSIVE_SONAR"
        assert defn.max_range_m == 120000.0


# ── 28c Organizations ────────────────────────────────────────────────

_ORG_FILES = [
    "organizations/us_modern/combined_arms_btf.yaml",
    "organizations/us_modern/stryker_company.yaml",
    "organizations/us_modern/m109a6_battery.yaml",
    "organizations/russian/btg.yaml",
    "organizations/chinese/combined_arms_brigade.yaml",
    "organizations/uk/armoured_battlegroup.yaml",
    "organizations/generic/mech_company.yaml",
]


class TestPhase28cOrgs:
    """Loading for 7 new organization TOE files."""

    @pytest.mark.parametrize("rel_path", _ORG_FILES)
    def test_org_loads(self, rel_path: str) -> None:
        toe = OrbatLoader.load_toe(DATA_DIR / rel_path)
        assert toe.name
        assert len(toe.subordinates) > 0

    def test_russian_btg_name(self) -> None:
        toe = OrbatLoader.load_toe(DATA_DIR / "organizations/russian/btg.yaml")
        assert "BTG" in toe.name or "Battalion" in toe.name

    def test_pla_cab_is_brigade(self) -> None:
        toe = OrbatLoader.load_toe(DATA_DIR / "organizations/chinese/combined_arms_brigade.yaml")
        assert toe.echelon == "BRIGADE"

    def test_cabtf_is_battalion(self) -> None:
        toe = OrbatLoader.load_toe(DATA_DIR / "organizations/us_modern/combined_arms_btf.yaml")
        assert toe.echelon == "BATTALION"

    def test_stryker_has_javelin(self) -> None:
        toe = OrbatLoader.load_toe(DATA_DIR / "organizations/us_modern/stryker_company.yaml")
        types = [s.unit_type for s in toe.subordinates]
        assert "javelin_team" in types

    def test_uk_battlegroup_has_challenger2(self) -> None:
        toe = OrbatLoader.load_toe(DATA_DIR / "organizations/uk/armoured_battlegroup.yaml")
        types = [s.unit_type for s in toe.subordinates]
        assert "challenger2" in types

    def test_mech_company_has_bmp1(self) -> None:
        toe = OrbatLoader.load_toe(DATA_DIR / "organizations/generic/mech_company.yaml")
        types = [s.unit_type for s in toe.subordinates]
        assert "bmp1" in types


# ── 28c Doctrine ─────────────────────────────────────────────────────

_NEW_DOCTRINE_IDS = [
    "pla_active_defense",
    "idf_preemptive",
    "airborne_vertical_envelopment",
    "amphibious_ship_to_shore",
    "naval_sea_control",
]


class TestPhase28cDoctrine:
    """Loading and spot-checks for 5 new doctrine templates."""

    @pytest.mark.parametrize("doctrine_id", _NEW_DOCTRINE_IDS)
    def test_doctrine_loads(self, doctrine_loader: DoctrineTemplateLoader, doctrine_id: str) -> None:
        defn = doctrine_loader.get_definition(doctrine_id)
        assert defn.doctrine_id == doctrine_id

    def test_pla_is_defensive(self, doctrine_loader: DoctrineTemplateLoader) -> None:
        defn = doctrine_loader.get_definition("pla_active_defense")
        assert defn.category == "DEFENSIVE"

    def test_idf_is_offensive(self, doctrine_loader: DoctrineTemplateLoader) -> None:
        defn = doctrine_loader.get_definition("idf_preemptive")
        assert defn.category == "OFFENSIVE"


# ── 28c Commander Profiles ───────────────────────────────────────────

_NEW_COMMANDER_IDS = [
    "joint_campaign",
    "naval_aviation",
    "logistics_sustainment",
]


class TestPhase28cCommanders:
    """Loading for 3 new commander personality profiles."""

    @pytest.mark.parametrize("profile_id", _NEW_COMMANDER_IDS)
    def test_commander_loads(self, commander_loader: CommanderProfileLoader, profile_id: str) -> None:
        defn = commander_loader.get_definition(profile_id)
        assert defn.profile_id == profile_id
        assert 0.0 <= defn.aggression <= 1.0
        assert 0.0 <= defn.experience <= 1.0


# ── 28c Escalation Configs ──────────────────────────────────────────

_ESCALATION_FILES = [
    "escalation/peer_competitor.yaml",
    "escalation/conventional_only.yaml",
    "escalation/nato_article5.yaml",
]


class TestPhase28cEscalation:
    """Loading and spot-checks for 3 new escalation configurations."""

    @pytest.mark.parametrize("rel_path", _ESCALATION_FILES)
    def test_escalation_loads(self, rel_path: str) -> None:
        path = DATA_DIR / rel_path
        with open(path) as f:
            raw = yaml.safe_load(f)
        config = EscalationLadderConfig.model_validate(raw)
        assert len(config.entry_thresholds) == 11

    def test_conventional_only_blocks_nuclear(self) -> None:
        path = DATA_DIR / "escalation/conventional_only.yaml"
        with open(path) as f:
            raw = yaml.safe_load(f)
        config = EscalationLadderConfig.model_validate(raw)
        # Levels 5-10 should be unreachable (threshold > 1.0)
        for i in range(5, 11):
            assert config.entry_thresholds[i] > 1.0

    def test_peer_competitor_high_cooldown(self) -> None:
        path = DATA_DIR / "escalation/peer_competitor.yaml"
        with open(path) as f:
            raw = yaml.safe_load(f)
        config = EscalationLadderConfig.model_validate(raw)
        assert config.cooldown_s >= 14400.0

    def test_nato_article5_moderate_thresholds(self) -> None:
        path = DATA_DIR / "escalation/nato_article5.yaml"
        with open(path) as f:
            raw = yaml.safe_load(f)
        config = EscalationLadderConfig.model_validate(raw)
        # Should have moderate thresholds — level 5 between 0.5 and 0.8
        assert 0.5 < config.entry_thresholds[5] < 0.8


# ── 28d Signatures ───────────────────────────────────────────────────

_ALL_28_SIGNATURE_IDS = _NEW_UNIT_TYPES + [
    "bmp1", "m1a1", "m3a2_bradley", "ranger_plt",
    "sea_harrier", "sf_oda", "t55a", "t62", "type22_frigate",
]


class TestPhase28dSignatures:
    """Loading for all 28 new signature profiles."""

    @pytest.mark.parametrize("profile_id", _ALL_28_SIGNATURE_IDS)
    def test_signature_loads(self, sig_loader: SignatureLoader, profile_id: str) -> None:
        profile = sig_loader.get_profile(profile_id)
        assert profile.profile_id == profile_id
        assert profile.unit_type == profile_id

    def test_kilo636_low_acoustic(self, sig_loader: SignatureLoader) -> None:
        profile = sig_loader.get_profile("kilo636")
        assert profile.acoustic.noise_db <= 90.0

    def test_mig29a_em_emitting(self, sig_loader: SignatureLoader) -> None:
        profile = sig_loader.get_profile("mig29a")
        assert profile.electromagnetic.emitting is True

    def test_t90a_not_emitting(self, sig_loader: SignatureLoader) -> None:
        profile = sig_loader.get_profile("t90a")
        assert profile.electromagnetic.emitting is False

    def test_all_new_units_have_signatures(
        self, unit_loader: UnitLoader, sig_loader: SignatureLoader
    ) -> None:
        """Every new Phase 28a unit type has a matching signature profile."""
        for ut in _NEW_UNIT_TYPES:
            assert ut in sig_loader.available_profiles(), f"Missing signature for {ut}"


# ── Cross-Reference ──────────────────────────────────────────────────


class TestPhase28CrossRef:
    """Cross-referencing between data categories."""

    def test_weapon_ammo_refs_resolve(
        self, weapon_loader: WeaponLoader, ammo_loader: AmmoLoader
    ) -> None:
        """All weapon compatible_ammo refs exist in AmmoLoader."""
        for wid in _NEW_WEAPON_IDS:
            defn = weapon_loader.get_definition(wid)
            for aid in defn.compatible_ammo:
                assert aid in ammo_loader.available_ammo(), (
                    f"Weapon {wid} references unknown ammo {aid}"
                )

    def test_armored_units_have_armor_type(self, unit_loader: UnitLoader) -> None:
        """All ARMOR / MECHANIZED_INFANTRY units have non-default armor."""
        armored_types = {"ARMOR", "MECHANIZED_INFANTRY"}
        for ut in _NEW_UNIT_TYPES:
            defn = unit_loader.get_definition(ut)
            if defn.ground_type in armored_types:
                assert defn.armor_front > 0, f"{ut} missing armor_front"

    def test_org_subordinate_unit_types_exist(self, unit_loader: UnitLoader) -> None:
        """All org subordinate unit_types exist in UnitLoader."""
        for rel_path in _ORG_FILES:
            toe = OrbatLoader.load_toe(DATA_DIR / rel_path)
            available = set(unit_loader.available_types())
            for sub in toe.subordinates:
                assert sub.unit_type in available, (
                    f"Org {toe.name}: unknown unit_type {sub.unit_type}"
                )

    def test_total_unit_count(self, unit_loader: UnitLoader) -> None:
        """Total loaded unit count should be >= 43 (24 existing + 19 new)."""
        assert len(unit_loader.available_types()) >= 43
