"""Phase 46: Scenario Data Cleanup & Expansion — YAML loading tests.

Validates all new unit/weapon/ammo/sensor/signature data files load
through their respective loaders, and all 9 modified scenarios load
correctly with faction-appropriate units.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from stochastic_warfare.entities.loader import UnitLoader
from stochastic_warfare.combat.ammunition import WeaponLoader, AmmoLoader
from stochastic_warfare.detection.sensors import SensorLoader
from stochastic_warfare.detection.signatures import SignatureLoader

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
ERA_DIR = DATA_DIR / "eras"


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def unit_loader() -> UnitLoader:
    loader = UnitLoader(DATA_DIR / "units")
    loader.load_all()
    return loader


@pytest.fixture(scope="module")
def era_unit_loader() -> UnitLoader:
    loader = UnitLoader(ERA_DIR / "ancient_medieval" / "units")
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
def era_sig_loader() -> SignatureLoader:
    loader = SignatureLoader(ERA_DIR / "ancient_medieval" / "signatures")
    loader.load_all()
    return loader


# ── 46a-1: SA-6 Gainful ─────────────────────────────────────────────

class TestSA6Gainful:
    """SA-6 unit, weapon, ammo, sensor, signature load correctly."""

    def test_unit_loads(self, unit_loader: UnitLoader) -> None:
        defn = unit_loader.get_definition("sa6_gainful")
        assert defn.unit_type == "sa6_gainful"
        assert defn.domain == "ground"
        assert defn.ad_type == "SAM_MEDIUM"

    def test_max_range(self, unit_loader: UnitLoader) -> None:
        defn = unit_loader.get_definition("sa6_gainful")
        assert 20000.0 <= defn.max_engagement_range <= 30000.0

    def test_weapon_loads(self, weapon_loader: WeaponLoader) -> None:
        defn = weapon_loader.get_definition("sa6_3m9")
        assert defn.weapon_id == "sa6_3m9"
        assert defn.guidance == "RADAR_SEMI_ACTIVE"
        assert defn.max_range_m == 24000.0

    def test_ammo_loads(self, ammo_loader: AmmoLoader) -> None:
        defn = ammo_loader.get_definition("3m9_sam")
        assert defn.ammo_id == "3m9_sam"
        assert defn.ammo_type == "MISSILE"
        assert defn.pk_at_reference == 0.55

    def test_sensor_loads(self, sensor_loader: SensorLoader) -> None:
        defn = sensor_loader.get_definition("1s91_straight_flush")
        assert defn.sensor_id == "1s91_straight_flush"
        assert defn.sensor_type == "RADAR"
        assert defn.max_range_m == 75000.0

    def test_signature_loads(self, sig_loader: SignatureLoader) -> None:
        profile = sig_loader.get_profile("sa6_gainful")
        assert profile.profile_id == "sa6_gainful"
        assert profile.electromagnetic.emitting is True

    def test_weapon_ammo_cross_ref(
        self, weapon_loader: WeaponLoader, ammo_loader: AmmoLoader
    ) -> None:
        defn = weapon_loader.get_definition("sa6_3m9")
        for aid in defn.compatible_ammo:
            assert aid in ammo_loader.available_ammo(), f"Missing ammo {aid}"


# ── 46a-2: A-4 Skyhawk ──────────────────────────────────────────────

class TestA4Skyhawk:
    """A-4 unit, weapon, ammo, sensor, signature load correctly."""

    def test_unit_loads(self, unit_loader: UnitLoader) -> None:
        defn = unit_loader.get_definition("a4_skyhawk")
        assert defn.unit_type == "a4_skyhawk"
        assert defn.domain == "aerial"
        assert defn.aerial_type == "ATTACK"

    def test_speed_subsonic(self, unit_loader: UnitLoader) -> None:
        defn = unit_loader.get_definition("a4_skyhawk")
        # A-4: ~1080 km/h = 300 m/s, should be > 222 m/s (800 km/h)
        assert defn.max_speed > 222.0

    def test_weapon_loads(self, weapon_loader: WeaponLoader) -> None:
        defn = weapon_loader.get_definition("mk12_20mm")
        assert defn.weapon_id == "mk12_20mm"
        assert defn.caliber_mm == 20.0

    def test_ammo_loads(self, ammo_loader: AmmoLoader) -> None:
        defn = ammo_loader.get_definition("20mm_mk100")
        assert defn.ammo_id == "20mm_mk100"
        assert defn.ammo_type == "HE"

    def test_sensor_loads(self, sensor_loader: SensorLoader) -> None:
        defn = sensor_loader.get_definition("apq94_radar")
        assert defn.sensor_id == "apq94_radar"
        assert defn.sensor_type == "RADAR"

    def test_signature_loads(self, sig_loader: SignatureLoader) -> None:
        profile = sig_loader.get_profile("a4_skyhawk")
        assert profile.profile_id == "a4_skyhawk"
        assert profile.radar.rcs_frontal_m2 == 3.0


# ── 46a-3: Carthaginian Units ───────────────────────────────────────

class TestCarthaginianUnits:
    """Carthaginian infantry + Numidian cavalry for Cannae."""

    def test_infantry_loads(self, era_unit_loader: UnitLoader) -> None:
        defn = era_unit_loader.get_definition("carthaginian_infantry")
        assert defn.unit_type == "carthaginian_infantry"
        assert defn.ground_type == "LIGHT_INFANTRY"
        assert defn.armor_front == 1.5

    def test_cavalry_loads(self, era_unit_loader: UnitLoader) -> None:
        defn = era_unit_loader.get_definition("numidian_cavalry")
        assert defn.unit_type == "numidian_cavalry"
        assert defn.ground_type == "CAVALRY"
        assert defn.max_speed == 9.0

    def test_infantry_has_melee_weapons(self, era_unit_loader: UnitLoader) -> None:
        defn = era_unit_loader.get_definition("carthaginian_infantry")
        equip_names = [e.name for e in defn.equipment]
        assert "Gladius" in equip_names
        assert "Pilum" in equip_names

    def test_infantry_signature(self, era_sig_loader: SignatureLoader) -> None:
        profile = era_sig_loader.get_profile("carthaginian_infantry")
        assert profile.profile_id == "carthaginian_infantry"
        assert profile.electromagnetic.emitting is False

    def test_cavalry_signature(self, era_sig_loader: SignatureLoader) -> None:
        profile = era_sig_loader.get_profile("numidian_cavalry")
        assert profile.profile_id == "numidian_cavalry"
        assert profile.acoustic.noise_db == 60.0


# ── 46b-1: Eastern Front Era Fix ────────────────────────────────────

class TestEasternFrontEraFix:
    """Eastern Front 1943 scenario uses WW2 era and units."""

    def test_era_is_ww2(self) -> None:
        path = DATA_DIR / "scenarios" / "eastern_front_1943" / "scenario.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)
        assert data["era"] == "ww2"

    def test_blue_uses_soviet_units(self) -> None:
        path = DATA_DIR / "scenarios" / "eastern_front_1943" / "scenario.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)
        blue = data["sides"][0]
        unit_types = [u["unit_type"] for u in blue["units"]]
        assert "soviet_rifle_squad" in unit_types
        assert "t34_85" in unit_types
        assert "us_rifle_squad" not in unit_types

    def test_red_uses_german_units(self) -> None:
        path = DATA_DIR / "scenarios" / "eastern_front_1943" / "scenario.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)
        red = data["sides"][1]
        unit_types = [u["unit_type"] for u in red["units"]]
        assert "wehrmacht_rifle_squad" in unit_types
        assert "panzer_iv_h" in unit_types
        assert "tiger_i" in unit_types
        assert "us_rifle_squad" not in unit_types


# ── 46b-2: Insurgent Squad ──────────────────────────────────────────

class TestInsurgentSquad:
    """Insurgent squad unit, weapons, ammo, signature load correctly."""

    def test_unit_loads(self, unit_loader: UnitLoader) -> None:
        defn = unit_loader.get_definition("insurgent_squad")
        assert defn.unit_type == "insurgent_squad"
        assert defn.ground_type == "LIGHT_INFANTRY"
        assert defn.armor_front == 0.0

    def test_has_ak47_and_rpg7(self, unit_loader: UnitLoader) -> None:
        defn = unit_loader.get_definition("insurgent_squad")
        equip_names = [e.name for e in defn.equipment]
        assert "AK-47" in equip_names
        assert "RPG-7" in equip_names

    def test_ak47_loads(self, weapon_loader: WeaponLoader) -> None:
        defn = weapon_loader.get_definition("ak47")
        assert defn.weapon_id == "ak47"
        assert defn.caliber_mm == 7.62
        assert defn.max_range_m == 400.0

    def test_rpg7_loads(self, weapon_loader: WeaponLoader) -> None:
        defn = weapon_loader.get_definition("rpg7")
        assert defn.weapon_id == "rpg7"
        assert defn.max_range_m == 300.0

    def test_762x39_ammo_loads(self, ammo_loader: AmmoLoader) -> None:
        defn = ammo_loader.get_definition("7_62x39_fmj")
        assert defn.ammo_id == "7_62x39_fmj"
        assert defn.ammo_type == "AP"

    def test_pg7_heat_loads(self, ammo_loader: AmmoLoader) -> None:
        defn = ammo_loader.get_definition("pg7_heat")
        assert defn.ammo_id == "pg7_heat"
        assert defn.ammo_type == "HEAT"
        assert defn.penetration_mm_rha == 260.0

    def test_signature_loads(self, sig_loader: SignatureLoader) -> None:
        profile = sig_loader.get_profile("insurgent_squad")
        assert profile.profile_id == "insurgent_squad"
        assert profile.visual.camouflage_factor == 0.5

    def test_weapon_ammo_cross_ref(
        self, weapon_loader: WeaponLoader, ammo_loader: AmmoLoader
    ) -> None:
        for wid in ("ak47", "rpg7"):
            defn = weapon_loader.get_definition(wid)
            for aid in defn.compatible_ammo:
                assert aid in ammo_loader.available_ammo(), (
                    f"Weapon {wid} references unknown ammo {aid}"
                )


# ── 46b-3: Civilian Noncombatant ────────────────────────────────────

class TestCivilianNoncombatant:
    """Civilian noncombatant unit with no weapons."""

    def test_unit_loads(self, unit_loader: UnitLoader) -> None:
        defn = unit_loader.get_definition("civilian_noncombatant")
        assert defn.unit_type == "civilian_noncombatant"
        assert defn.ground_type == "LIGHT_INFANTRY"
        assert defn.armor_front == 0.0

    def test_no_weapons(self, unit_loader: UnitLoader) -> None:
        defn = unit_loader.get_definition("civilian_noncombatant")
        weapon_equip = [e for e in defn.equipment if e.category == "WEAPON"]
        assert len(weapon_equip) == 0

    def test_signature_loads(self, sig_loader: SignatureLoader) -> None:
        profile = sig_loader.get_profile("civilian_noncombatant")
        assert profile.profile_id == "civilian_noncombatant"
        assert profile.electromagnetic.emitting is False
        assert profile.visual.camouflage_factor == 0.0


# ── Scenario Load Tests ─────────────────────────────────────────────

_MODIFIED_SCENARIOS = [
    DATA_DIR / "scenarios" / "bekaa_valley_1982" / "scenario.yaml",
    DATA_DIR / "scenarios" / "gulf_war_ew_1991" / "scenario.yaml",
    DATA_DIR / "scenarios" / "falklands_san_carlos" / "scenario.yaml",
    ERA_DIR / "ancient_medieval" / "scenarios" / "cannae" / "scenario.yaml",
    DATA_DIR / "scenarios" / "eastern_front_1943" / "scenario.yaml",
    DATA_DIR / "scenarios" / "coin_campaign" / "scenario.yaml",
    DATA_DIR / "scenarios" / "hybrid_gray_zone" / "scenario.yaml",
    DATA_DIR / "scenarios" / "srebrenica_1995" / "scenario.yaml",
    DATA_DIR / "scenarios" / "halabja_1988" / "scenario.yaml",
]


class TestModifiedScenarioLoad:
    """All 9 modified scenarios load as valid YAML with expected structure."""

    @pytest.mark.parametrize("path", _MODIFIED_SCENARIOS, ids=lambda p: p.parent.name)
    def test_scenario_loads_yaml(self, path: Path) -> None:
        with open(path) as f:
            data = yaml.safe_load(f)
        assert "name" in data
        assert "sides" in data
        assert len(data["sides"]) >= 2

    @pytest.mark.parametrize("path", _MODIFIED_SCENARIOS, ids=lambda p: p.parent.name)
    def test_no_us_rifle_squad_proxy(self, path: Path) -> None:
        """No modified scenario uses us_rifle_squad as a wrong-faction proxy."""
        with open(path) as f:
            data = yaml.safe_load(f)
        # These specific scenarios should NOT have us_rifle_squad
        skip = {"coin_campaign", "hybrid_gray_zone"}
        scenario_name = path.parent.name
        if scenario_name in skip:
            # COIN blue side still legitimately uses us_rifle_squad
            return
        for side in data["sides"]:
            for unit in side["units"]:
                if scenario_name in (
                    "eastern_front_1943", "srebrenica_1995",
                    "halabja_1988", "cannae",
                ):
                    assert unit["unit_type"] != "us_rifle_squad", (
                        f"{scenario_name} still uses us_rifle_squad"
                    )

    def test_bekaa_valley_uses_sa6(self) -> None:
        path = DATA_DIR / "scenarios" / "bekaa_valley_1982" / "scenario.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)
        red = data["sides"][1]
        assert red["units"][0]["unit_type"] == "sa6_gainful"
        assert "patriot" not in str(data)

    def test_gulf_war_uses_sa6(self) -> None:
        path = DATA_DIR / "scenarios" / "gulf_war_ew_1991" / "scenario.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)
        red = data["sides"][1]
        assert red["units"][0]["unit_type"] == "sa6_gainful"
        assert "patriot" not in str(data)

    def test_falklands_uses_a4(self) -> None:
        path = DATA_DIR / "scenarios" / "falklands_san_carlos" / "scenario.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)
        red = data["sides"][1]
        unit_types = [u["unit_type"] for u in red["units"]]
        assert "a4_skyhawk" in unit_types
        assert "mig29a" not in unit_types

    def test_cannae_uses_carthaginian(self) -> None:
        path = ERA_DIR / "ancient_medieval" / "scenarios" / "cannae" / "scenario.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)
        carthaginian = data["sides"][0]
        unit_types = [u["unit_type"] for u in carthaginian["units"]]
        assert "carthaginian_infantry" in unit_types
        assert "numidian_cavalry" in unit_types
        assert "roman_legionary_cohort" not in unit_types
        assert "mongol_horse_archer" not in unit_types

    def test_cannae_roman_cavalry(self) -> None:
        path = ERA_DIR / "ancient_medieval" / "scenarios" / "cannae" / "scenario.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)
        roman = data["sides"][1]
        unit_types = [u["unit_type"] for u in roman["units"]]
        # Phase 48: replaced anachronistic saracen_cavalry with roman_equites
        assert "roman_equites" in unit_types
        assert "norman_knight_conroi" not in unit_types

    def test_halabja_uses_civilian(self) -> None:
        path = DATA_DIR / "scenarios" / "halabja_1988" / "scenario.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)
        blue = data["sides"][0]
        assert blue["units"][0]["unit_type"] == "civilian_noncombatant"

    def test_srebrenica_uses_insurgent(self) -> None:
        path = DATA_DIR / "scenarios" / "srebrenica_1995" / "scenario.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)
        blue = data["sides"][0]
        assert blue["units"][0]["unit_type"] == "insurgent_squad"
        red = data["sides"][1]
        red_types = [u["unit_type"] for u in red["units"]]
        assert "insurgent_squad" in red_types
        assert "t72m" in red_types
