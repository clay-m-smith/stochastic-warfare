"""Phase 23a tests -- Ancient & Medieval era config and YAML data loading.

Tests that:
- Ancient/Medieval era config is registered and has correct properties
- All 7 modern modules are disabled (ew, space, cbrn, gps, thermal_sights,
  data_links, pgm)
- All Ancient/Medieval YAML data files load without validation errors
- Unit, weapon, ammo, sensor, signature, doctrine, commander, comms
- SimulationContext has 5 new Ancient/Medieval engine fields
- Era-aware loader merging works correctly
- Terrain validators accept "open_field"
- Melee/ranged/siege weapon properties are correct
- Backward compatibility with all existing era configs
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.conftest import make_rng


# ---------------------------------------------------------------------------
# Era config tests
# ---------------------------------------------------------------------------


class TestAncientMedievalEraConfig:
    """Ancient/Medieval era configuration."""

    def test_ancient_medieval_registered(self) -> None:
        from stochastic_warfare.core.era import get_era_config

        cfg = get_era_config("ancient_medieval")
        assert cfg.era.value == "ancient_medieval"

    def test_disabled_modules_exact(self) -> None:
        from stochastic_warfare.core.era import get_era_config

        cfg = get_era_config("ancient_medieval")
        expected = {"ew", "space", "cbrn", "gps", "thermal_sights", "data_links", "pgm"}
        assert cfg.disabled_modules == expected

    def test_visual_only_sensor(self) -> None:
        from stochastic_warfare.core.era import get_era_config

        cfg = get_era_config("ancient_medieval")
        assert cfg.available_sensor_types == {"VISUAL"}

    def test_c2_delay_multiplier(self) -> None:
        from stochastic_warfare.core.era import get_era_config

        cfg = get_era_config("ancient_medieval")
        assert cfg.physics_overrides.get("c2_delay_multiplier") == 12.0

    def test_nuclear_disabled_override(self) -> None:
        from stochastic_warfare.core.era import get_era_config

        cfg = get_era_config("ancient_medieval")
        assert cfg.physics_overrides.get("cbrn_nuclear_enabled") is False

    def test_era_enum_value(self) -> None:
        from stochastic_warfare.core.era import Era

        assert Era.ANCIENT_MEDIEVAL.value == "ancient_medieval"

    def test_unknown_era_returns_modern(self) -> None:
        from stochastic_warfare.core.era import get_era_config

        cfg = get_era_config("totally_unknown_era")
        assert cfg.era.value == "modern"

    def test_existing_eras_still_work(self) -> None:
        from stochastic_warfare.core.era import get_era_config

        for era_name in ("modern", "ww2", "ww1", "napoleonic"):
            cfg = get_era_config(era_name)
            assert cfg.era.value == era_name


# ---------------------------------------------------------------------------
# SimulationContext new fields
# ---------------------------------------------------------------------------


class TestContextFields:
    """SimulationContext has Ancient/Medieval engine fields."""

    def _make_ctx(self):
        from stochastic_warfare.simulation.scenario import (
            CampaignScenarioConfig,
            SimulationContext,
            TerrainConfig,
            SideConfig,
        )
        from stochastic_warfare.core.clock import SimulationClock
        from stochastic_warfare.core.events import EventBus
        from stochastic_warfare.core.rng import RNGManager
        from datetime import datetime, timezone, timedelta

        config = CampaignScenarioConfig(
            name="test", date="0480-08-11", duration_hours=1.0,
            terrain=TerrainConfig(width_m=1000, height_m=1000),
            sides=[
                SideConfig(side="a", units=[]),
                SideConfig(side="b", units=[]),
            ],
        )
        return SimulationContext(
            config=config,
            clock=SimulationClock(
                start=datetime(480, 8, 11, tzinfo=timezone.utc),
                tick_duration=timedelta(seconds=5),
            ),
            rng_manager=RNGManager(42),
            event_bus=EventBus(),
        )

    def test_archery_engine_default_none(self) -> None:
        ctx = self._make_ctx()
        assert ctx.archery_engine is None

    def test_siege_engine_default_none(self) -> None:
        ctx = self._make_ctx()
        assert ctx.siege_engine is None

    def test_formation_ancient_engine_default_none(self) -> None:
        ctx = self._make_ctx()
        assert ctx.formation_ancient_engine is None

    def test_naval_oar_engine_default_none(self) -> None:
        ctx = self._make_ctx()
        assert ctx.naval_oar_engine is None

    def test_visual_signals_engine_default_none(self) -> None:
        ctx = self._make_ctx()
        assert ctx.visual_signals_engine is None

    def test_get_state_includes_ancient_engine_keys(self) -> None:
        ctx = self._make_ctx()
        state = ctx.get_state()
        # When engines are None they are not in state dict, but set_state
        # roundtrip should work cleanly
        ctx2 = self._make_ctx()
        ctx2.set_state(state)
        assert ctx2.archery_engine is None
        assert ctx2.siege_engine is None
        assert ctx2.formation_ancient_engine is None
        assert ctx2.naval_oar_engine is None
        assert ctx2.visual_signals_engine is None


# ---------------------------------------------------------------------------
# YAML data loading -- units
# ---------------------------------------------------------------------------

DATA_DIR = Path("data")
AM_DIR = DATA_DIR / "eras" / "ancient_medieval"

_AM_UNITS = [
    "roman_legionary_cohort",
    "greek_hoplite_phalanx",
    "english_longbowman",
    "norman_knight_conroi",
    "swiss_pike_block",
    "mongol_horse_archer",
    "viking_huscarl",
]


class TestAncientMedievalUnits:
    """Ancient/Medieval unit YAML loading."""

    @pytest.fixture()
    def unit_loader(self):
        from stochastic_warfare.entities.loader import UnitLoader

        base = UnitLoader(DATA_DIR / "units")
        base.load_all()
        era = UnitLoader(AM_DIR / "units")
        era.load_all()
        base._definitions.update(era._definitions)
        return base

    @pytest.mark.parametrize("unit_type", _AM_UNITS)
    def test_unit_loads(self, unit_loader, unit_type: str) -> None:
        defn = unit_loader._definitions.get(unit_type)
        assert defn is not None, f"Unit {unit_type} not found"

    @pytest.mark.parametrize("unit_type", _AM_UNITS)
    def test_unit_has_display_name(self, unit_loader, unit_type: str) -> None:
        defn = unit_loader._definitions[unit_type]
        assert defn.display_name

    @pytest.mark.parametrize("unit_type", _AM_UNITS)
    def test_unit_domain_ground(self, unit_loader, unit_type: str) -> None:
        defn = unit_loader._definitions[unit_type]
        assert defn.domain == "ground"

    def test_cavalry_speed(self, unit_loader) -> None:
        defn = unit_loader._definitions["mongol_horse_archer"]
        assert defn.max_speed >= 7.0

    def test_infantry_speed(self, unit_loader) -> None:
        defn = unit_loader._definitions["roman_legionary_cohort"]
        assert 1.0 <= defn.max_speed <= 2.0

    def test_knight_armor(self, unit_loader) -> None:
        defn = unit_loader._definitions["norman_knight_conroi"]
        assert defn.armor_front >= 3.0

    def test_phalanx_slow(self, unit_loader) -> None:
        defn = unit_loader._definitions["greek_hoplite_phalanx"]
        assert defn.max_speed < 1.0


# ---------------------------------------------------------------------------
# YAML data loading -- weapons
# ---------------------------------------------------------------------------

_AM_WEAPONS = [
    "gladius",
    "pilum",
    "sarissa",
    "longbow",
    "crossbow",
    "lance_medieval",
    "sword_medieval",
    "mace",
    "pike",
    "catapult",
    "trebuchet",
    "ballista",
    "battering_ram",
]


class TestAncientMedievalWeapons:
    """Ancient/Medieval weapon YAML loading."""

    @pytest.fixture()
    def weapon_loader(self):
        from stochastic_warfare.combat.ammunition import WeaponLoader

        base = WeaponLoader(DATA_DIR / "weapons")
        base.load_all()
        era = WeaponLoader(AM_DIR / "weapons")
        era.load_all()
        base._definitions.update(era._definitions)
        return base

    @pytest.mark.parametrize("weapon_id", _AM_WEAPONS)
    def test_weapon_loads(self, weapon_loader, weapon_id: str) -> None:
        defn = weapon_loader._definitions.get(weapon_id)
        assert defn is not None, f"Weapon {weapon_id} not found"

    @pytest.mark.parametrize("weapon_id", _AM_WEAPONS)
    def test_weapon_has_weapon_id(self, weapon_loader, weapon_id: str) -> None:
        defn = weapon_loader._definitions[weapon_id]
        assert defn.weapon_id == weapon_id

    def test_longbow_category(self, weapon_loader) -> None:
        defn = weapon_loader._definitions["longbow"]
        assert defn.category == "RIFLE"

    def test_gladius_category(self, weapon_loader) -> None:
        defn = weapon_loader._definitions["gladius"]
        assert defn.category == "MELEE"

    def test_catapult_category(self, weapon_loader) -> None:
        defn = weapon_loader._definitions["catapult"]
        assert defn.category == "HOWITZER"


# ---------------------------------------------------------------------------
# YAML data loading -- ammunition
# ---------------------------------------------------------------------------

_AM_AMMO = [
    "arrow_longbow",
    "bolt_crossbow",
    "pilum_javelin",
    "stone_catapult",
    "stone_trebuchet",
    "bolt_ballista",
    "composite_arrow",
    "sling_stone",
]


class TestAncientMedievalAmmo:
    """Ancient/Medieval ammunition YAML loading."""

    @pytest.fixture()
    def ammo_loader(self):
        from stochastic_warfare.combat.ammunition import AmmoLoader

        base = AmmoLoader(DATA_DIR / "ammunition")
        base.load_all()
        era = AmmoLoader(AM_DIR / "ammunition")
        era.load_all()
        base._definitions.update(era._definitions)
        return base

    @pytest.mark.parametrize("ammo_id", _AM_AMMO)
    def test_ammo_loads(self, ammo_loader, ammo_id: str) -> None:
        defn = ammo_loader._definitions.get(ammo_id)
        assert defn is not None, f"Ammo {ammo_id} not found"

    @pytest.mark.parametrize("ammo_id", _AM_AMMO)
    def test_ammo_has_display_name(self, ammo_loader, ammo_id: str) -> None:
        defn = ammo_loader._definitions[ammo_id]
        assert defn.display_name

    def test_arrow_no_blast(self, ammo_loader) -> None:
        defn = ammo_loader._definitions["arrow_longbow"]
        assert defn.blast_radius_m == 0.0

    def test_stone_catapult_has_mass(self, ammo_loader) -> None:
        defn = ammo_loader._definitions["stone_catapult"]
        assert defn.mass_kg > 0

    def test_sling_stone_exists(self, ammo_loader) -> None:
        defn = ammo_loader._definitions["sling_stone"]
        assert defn.ammo_id == "sling_stone"


# ---------------------------------------------------------------------------
# YAML data loading -- sensors
# ---------------------------------------------------------------------------

_AM_SENSORS = [
    "mounted_scout_ancient",
    "watchtower",
    "ship_lookout",
]


class TestAncientMedievalSensors:
    """Ancient/Medieval sensor YAML loading."""

    @pytest.fixture()
    def sensor_loader(self):
        from stochastic_warfare.detection.sensors import SensorLoader

        base = SensorLoader(DATA_DIR / "sensors")
        base.load_all()
        era = SensorLoader(AM_DIR / "sensors")
        era.load_all()
        base._definitions.update(era._definitions)
        return base

    @pytest.mark.parametrize("sensor_id", _AM_SENSORS)
    def test_sensor_loads(self, sensor_loader, sensor_id: str) -> None:
        defn = sensor_loader._definitions.get(sensor_id)
        assert defn is not None, f"Sensor {sensor_id} not found"

    @pytest.mark.parametrize("sensor_id", _AM_SENSORS)
    def test_sensor_is_visual(self, sensor_loader, sensor_id: str) -> None:
        defn = sensor_loader._definitions[sensor_id]
        assert defn.sensor_type == "VISUAL"

    def test_watchtower_long_range(self, sensor_loader) -> None:
        defn = sensor_loader._definitions["watchtower"]
        assert defn.max_range_m >= 8000.0

    def test_watchtower_full_fov(self, sensor_loader) -> None:
        defn = sensor_loader._definitions["watchtower"]
        assert defn.fov_deg == 360.0

    def test_scout_wide_fov(self, sensor_loader) -> None:
        defn = sensor_loader._definitions["mounted_scout_ancient"]
        assert defn.fov_deg >= 90.0

    def test_ship_lookout_range(self, sensor_loader) -> None:
        defn = sensor_loader._definitions["ship_lookout"]
        assert defn.max_range_m >= 3000.0


# ---------------------------------------------------------------------------
# YAML data loading -- signatures
# ---------------------------------------------------------------------------

_AM_SIGS = [
    "roman_legionary_cohort",
    "greek_hoplite_phalanx",
    "english_longbowman",
    "norman_knight_conroi",
    "swiss_pike_block",
    "mongol_horse_archer",
    "viking_huscarl",
]


class TestAncientMedievalSignatures:
    """Ancient/Medieval signature YAML loading."""

    @pytest.fixture()
    def sig_loader(self):
        from stochastic_warfare.detection.signatures import SignatureLoader

        base = SignatureLoader(DATA_DIR / "signatures")
        base.load_all()
        era = SignatureLoader(AM_DIR / "signatures")
        era.load_all()
        base._profiles.update(era._profiles)
        return base

    @pytest.mark.parametrize("profile_id", _AM_SIGS)
    def test_sig_loads(self, sig_loader, profile_id: str) -> None:
        prof = sig_loader._profiles.get(profile_id)
        assert prof is not None, f"Signature {profile_id} not found"

    @pytest.mark.parametrize("profile_id", _AM_SIGS)
    def test_zeroed_thermal(self, sig_loader, profile_id: str) -> None:
        prof = sig_loader._profiles[profile_id]
        assert prof.thermal.emissivity == 0.0

    @pytest.mark.parametrize("profile_id", _AM_SIGS)
    def test_zeroed_radar(self, sig_loader, profile_id: str) -> None:
        prof = sig_loader._profiles[profile_id]
        assert prof.radar.rcs_frontal_m2 == 0.0

    def test_cavalry_taller_than_infantry(self, sig_loader) -> None:
        inf = sig_loader._profiles["roman_legionary_cohort"]
        cav = sig_loader._profiles["norman_knight_conroi"]
        assert cav.visual.height_m > inf.visual.height_m

    def test_cavalry_noisier_than_infantry(self, sig_loader) -> None:
        inf = sig_loader._profiles["english_longbowman"]
        cav = sig_loader._profiles["norman_knight_conroi"]
        assert cav.acoustic.noise_db > inf.acoustic.noise_db


# ---------------------------------------------------------------------------
# YAML data loading -- doctrine, commanders, comms
# ---------------------------------------------------------------------------


class TestAncientMedievalDoctrine:
    """Ancient/Medieval doctrine YAML files exist and load."""

    def _load_yaml(self, path: Path) -> dict:
        with open(path) as f:
            return yaml.safe_load(f)

    def test_roman_legion(self) -> None:
        d = self._load_yaml(AM_DIR / "doctrine" / "roman_legion.yaml")
        assert d["doctrine_id"] == "roman_legion"
        assert d["category"] == "OFFENSIVE"

    def test_english_defensive(self) -> None:
        d = self._load_yaml(AM_DIR / "doctrine" / "english_defensive.yaml")
        assert d["doctrine_id"] == "english_defensive"
        assert d["category"] == "DEFENSIVE"

    def test_steppe_nomad(self) -> None:
        d = self._load_yaml(AM_DIR / "doctrine" / "steppe_nomad.yaml")
        assert d["doctrine_id"] == "steppe_nomad"
        assert d["category"] == "OFFENSIVE"

    def test_roman_legion_has_phases(self) -> None:
        d = self._load_yaml(AM_DIR / "doctrine" / "roman_legion.yaml")
        assert isinstance(d["phases"], list)
        assert len(d["phases"]) >= 3

    def test_english_defensive_has_actions(self) -> None:
        d = self._load_yaml(AM_DIR / "doctrine" / "english_defensive.yaml")
        assert "archery" in d["actions"]

    def test_steppe_nomad_high_tempo(self) -> None:
        d = self._load_yaml(AM_DIR / "doctrine" / "steppe_nomad.yaml")
        assert d["tempo"] == "high"


class TestAncientMedievalCommanders:
    """Ancient/Medieval commander YAML files."""

    def _load_yaml(self, path: Path) -> dict:
        with open(path) as f:
            return yaml.safe_load(f)

    def test_hannibal_barca(self) -> None:
        d = self._load_yaml(AM_DIR / "commanders" / "hannibal_barca.yaml")
        assert d["profile_id"] == "hannibal_barca"
        assert d["aggression"] >= 0.8

    def test_henry_v(self) -> None:
        d = self._load_yaml(AM_DIR / "commanders" / "henry_v.yaml")
        assert d["profile_id"] == "henry_v"
        assert d["caution"] >= 0.5

    def test_william_conqueror(self) -> None:
        d = self._load_yaml(AM_DIR / "commanders" / "william_conqueror.yaml")
        assert d["profile_id"] == "william_conqueror"
        assert d["aggression"] >= 0.7

    def test_hannibal_high_flexibility(self) -> None:
        d = self._load_yaml(AM_DIR / "commanders" / "hannibal_barca.yaml")
        assert d["flexibility"] >= 0.9

    def test_henry_defensive_doctrine(self) -> None:
        d = self._load_yaml(AM_DIR / "commanders" / "henry_v.yaml")
        assert d["preferred_doctrine"] == "english_defensive"

    def test_commanders_have_experience(self) -> None:
        for fname in ["hannibal_barca.yaml", "henry_v.yaml", "william_conqueror.yaml"]:
            d = self._load_yaml(AM_DIR / "commanders" / fname)
            assert "experience" in d
            assert d["experience"] >= 0.5


class TestAncientMedievalComms:
    """Ancient/Medieval communications YAML files."""

    def _load_yaml(self, path: Path) -> dict:
        with open(path) as f:
            return yaml.safe_load(f)

    def test_battle_horn(self) -> None:
        d = self._load_yaml(AM_DIR / "comms" / "battle_horn.yaml")
        assert d["comm_type"] == "MESSENGER"
        assert d["max_range_m"] <= 500.0

    def test_banner_signal(self) -> None:
        d = self._load_yaml(AM_DIR / "comms" / "banner_signal.yaml")
        assert d["comm_type"] == "MESSENGER"
        assert d["max_range_m"] <= 1000.0

    def test_banner_requires_los(self) -> None:
        d = self._load_yaml(AM_DIR / "comms" / "banner_signal.yaml")
        assert d["requires_los"] is True

    def test_horn_no_los_needed(self) -> None:
        d = self._load_yaml(AM_DIR / "comms" / "battle_horn.yaml")
        assert d["requires_los"] is False


# ---------------------------------------------------------------------------
# Era-aware loader merging
# ---------------------------------------------------------------------------


class TestEraAwareLoaderMerging:
    """Era-aware YAML loading merges ancient_medieval data on top of base."""

    def test_ancient_units_available_after_merge(self) -> None:
        from stochastic_warfare.entities.loader import UnitLoader

        base = UnitLoader(DATA_DIR / "units")
        base.load_all()
        era = UnitLoader(AM_DIR / "units")
        era.load_all()
        base._definitions.update(era._definitions)
        assert "roman_legionary_cohort" in base._definitions

    def test_base_units_still_present(self) -> None:
        from stochastic_warfare.entities.loader import UnitLoader

        base = UnitLoader(DATA_DIR / "units")
        base.load_all()
        base_count = len(base._definitions)
        era = UnitLoader(AM_DIR / "units")
        era.load_all()
        base._definitions.update(era._definitions)
        # After merge, should have at least original + new
        assert len(base._definitions) >= base_count

    def test_modern_config_not_affected(self) -> None:
        from stochastic_warfare.core.era import get_era_config

        cfg = get_era_config("modern")
        assert len(cfg.disabled_modules) == 0

    def test_other_era_configs_not_affected(self) -> None:
        from stochastic_warfare.core.era import get_era_config

        for era_name in ("ww2", "ww1", "napoleonic"):
            cfg = get_era_config(era_name)
            assert cfg.era.value == era_name


# ---------------------------------------------------------------------------
# Terrain tests
# ---------------------------------------------------------------------------


class TestTerrainOpenField:
    """Terrain validators accept 'open_field' terrain type."""

    def test_terrain_config_accepts_open_field(self) -> None:
        from stochastic_warfare.simulation.scenario import TerrainConfig

        tc = TerrainConfig(width_m=1000, height_m=1000, terrain_type="open_field")
        assert tc.terrain_type == "open_field"

    def test_terrain_spec_accepts_open_field(self) -> None:
        from stochastic_warfare.validation.historical_data import TerrainSpec

        ts = TerrainSpec(width_m=1000, height_m=1000, terrain_type="open_field")
        assert ts.terrain_type == "open_field"

    def test_existing_terrain_types_still_valid(self) -> None:
        from stochastic_warfare.simulation.scenario import TerrainConfig

        for tt in ("flat_desert", "open_ocean", "hilly_defense", "trench_warfare"):
            tc = TerrainConfig(width_m=1000, height_m=1000, terrain_type=tt)
            assert tc.terrain_type == tt

    def test_invalid_terrain_type_rejected(self) -> None:
        from stochastic_warfare.simulation.scenario import TerrainConfig
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            TerrainConfig(width_m=1000, height_m=1000, terrain_type="lava_field")


# ---------------------------------------------------------------------------
# Melee / weapon-specific tests
# ---------------------------------------------------------------------------

_MELEE_WEAPONS = ["gladius", "sarissa", "lance_medieval", "sword_medieval", "mace", "pike"]
_RANGED_WEAPONS = ["longbow", "crossbow"]
_SIEGE_WEAPONS = ["catapult", "trebuchet", "ballista"]


class TestMeleeWeaponProperties:
    """Melee weapons have correct physical properties."""

    @pytest.fixture()
    def weapon_loader(self):
        from stochastic_warfare.combat.ammunition import WeaponLoader

        base = WeaponLoader(DATA_DIR / "weapons")
        base.load_all()
        era = WeaponLoader(AM_DIR / "weapons")
        era.load_all()
        base._definitions.update(era._definitions)
        return base

    @pytest.mark.parametrize("weapon_id", _MELEE_WEAPONS)
    def test_melee_max_range_short(self, weapon_loader, weapon_id: str) -> None:
        defn = weapon_loader._definitions[weapon_id]
        assert defn.max_range_m <= 5.0

    @pytest.mark.parametrize("weapon_id", _MELEE_WEAPONS)
    def test_melee_zero_muzzle_velocity(self, weapon_loader, weapon_id: str) -> None:
        defn = weapon_loader._definitions[weapon_id]
        assert defn.muzzle_velocity_mps == 0.0

    @pytest.mark.parametrize("weapon_id", _RANGED_WEAPONS)
    def test_ranged_has_compatible_ammo(self, weapon_loader, weapon_id: str) -> None:
        defn = weapon_loader._definitions[weapon_id]
        assert len(defn.compatible_ammo) > 0

    @pytest.mark.parametrize("weapon_id", _SIEGE_WEAPONS)
    def test_siege_requires_deployed(self, weapon_loader, weapon_id: str) -> None:
        defn = weapon_loader._definitions[weapon_id]
        assert defn.requires_deployed is True

    def test_battering_ram_requires_deployed(self, weapon_loader) -> None:
        defn = weapon_loader._definitions["battering_ram"]
        assert defn.requires_deployed is True

    def test_longbow_has_arrow_ammo(self, weapon_loader) -> None:
        defn = weapon_loader._definitions["longbow"]
        assert "arrow_longbow" in defn.compatible_ammo


# ---------------------------------------------------------------------------
# Physics / backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    """Existing era configs remain unchanged after ancient_medieval addition."""

    def test_modern_no_disabled_modules(self) -> None:
        from stochastic_warfare.core.era import get_era_config

        cfg = get_era_config("modern")
        assert len(cfg.disabled_modules) == 0

    def test_ww2_has_correct_sensors(self) -> None:
        from stochastic_warfare.core.era import get_era_config

        cfg = get_era_config("ww2")
        assert "RADAR" in cfg.available_sensor_types

    def test_ww1_c2_delay(self) -> None:
        from stochastic_warfare.core.era import get_era_config

        cfg = get_era_config("ww1")
        assert cfg.physics_overrides.get("c2_delay_multiplier") == 5.0

    def test_napoleonic_c2_delay(self) -> None:
        from stochastic_warfare.core.era import get_era_config

        cfg = get_era_config("napoleonic")
        assert cfg.physics_overrides.get("c2_delay_multiplier") == 8.0
