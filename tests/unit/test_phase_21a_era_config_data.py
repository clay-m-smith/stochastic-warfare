"""Phase 21a tests — WW1 era config and YAML data loading.

Tests that:
- WW1 era config is registered and has correct properties
- CBRN is NOT disabled (chemical warfare is a WW1 feature)
- All WW1 YAML data files load without validation errors
- Unit, weapon, ammo, sensor, signature, doctrine, commander, comms
"""

from __future__ import annotations

from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Era config tests
# ---------------------------------------------------------------------------


class TestWW1EraConfig:
    """WW1 era configuration."""

    def test_ww1_registered(self) -> None:
        from stochastic_warfare.core.era import get_era_config
        cfg = get_era_config("ww1")
        assert cfg.era.value == "ww1"

    def test_ew_disabled(self) -> None:
        from stochastic_warfare.core.era import get_era_config
        cfg = get_era_config("ww1")
        assert "ew" in cfg.disabled_modules

    def test_space_disabled(self) -> None:
        from stochastic_warfare.core.era import get_era_config
        cfg = get_era_config("ww1")
        assert "space" in cfg.disabled_modules

    def test_gps_disabled(self) -> None:
        from stochastic_warfare.core.era import get_era_config
        cfg = get_era_config("ww1")
        assert "gps" in cfg.disabled_modules

    def test_thermal_sights_disabled(self) -> None:
        from stochastic_warfare.core.era import get_era_config
        cfg = get_era_config("ww1")
        assert "thermal_sights" in cfg.disabled_modules

    def test_data_links_disabled(self) -> None:
        from stochastic_warfare.core.era import get_era_config
        cfg = get_era_config("ww1")
        assert "data_links" in cfg.disabled_modules

    def test_pgm_disabled(self) -> None:
        from stochastic_warfare.core.era import get_era_config
        cfg = get_era_config("ww1")
        assert "pgm" in cfg.disabled_modules

    def test_cbrn_not_disabled(self) -> None:
        from stochastic_warfare.core.era import get_era_config
        cfg = get_era_config("ww1")
        assert "cbrn" not in cfg.disabled_modules

    def test_visual_only_sensor(self) -> None:
        from stochastic_warfare.core.era import get_era_config
        cfg = get_era_config("ww1")
        assert cfg.available_sensor_types == {"VISUAL"}

    def test_c2_delay_multiplier(self) -> None:
        from stochastic_warfare.core.era import get_era_config
        cfg = get_era_config("ww1")
        assert cfg.physics_overrides.get("c2_delay_multiplier") == 5.0

    def test_nuclear_disabled_override(self) -> None:
        from stochastic_warfare.core.era import get_era_config
        cfg = get_era_config("ww1")
        assert cfg.physics_overrides.get("cbrn_nuclear_enabled") is False


# ---------------------------------------------------------------------------
# Scenario.py terrain type
# ---------------------------------------------------------------------------


class TestTerrainType:
    """Trench warfare terrain type accepted."""

    def test_trench_warfare_accepted(self) -> None:
        from stochastic_warfare.simulation.scenario import TerrainConfig
        tc = TerrainConfig(
            width_m=5000, height_m=3000,
            terrain_type="trench_warfare",
        )
        assert tc.terrain_type == "trench_warfare"

    def test_historical_data_trench_warfare(self) -> None:
        from stochastic_warfare.validation.historical_data import TerrainSpec
        ts = TerrainSpec(
            width_m=5000, height_m=3000,
            terrain_type="trench_warfare",
        )
        assert ts.terrain_type == "trench_warfare"


# ---------------------------------------------------------------------------
# SimulationContext new fields
# ---------------------------------------------------------------------------


class TestContextFields:
    """SimulationContext has WW1 engine fields."""

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
            name="test", date="1916-07-01", duration_hours=1.0,
            terrain=TerrainConfig(width_m=1000, height_m=1000),
            sides=[
                SideConfig(side="a", units=[]),
                SideConfig(side="b", units=[]),
            ],
        )
        return SimulationContext(
            config=config,
            clock=SimulationClock(
                start=datetime(1916, 7, 1, tzinfo=timezone.utc),
                tick_duration=timedelta(seconds=5),
            ),
            rng_manager=RNGManager(42),
            event_bus=EventBus(),
        )

    def test_trench_engine_default_none(self) -> None:
        ctx = self._make_ctx()
        assert ctx.trench_engine is None

    def test_barrage_engine_default_none(self) -> None:
        ctx = self._make_ctx()
        assert ctx.barrage_engine is None

    def test_gas_warfare_engine_default_none(self) -> None:
        ctx = self._make_ctx()
        assert ctx.gas_warfare_engine is None


# ---------------------------------------------------------------------------
# YAML data loading — units
# ---------------------------------------------------------------------------

DATA_DIR = Path("data")
WW1_DIR = DATA_DIR / "eras" / "ww1"

_WW1_UNITS = [
    "british_infantry_platoon",
    "german_sturmtruppen",
    "french_poilu_squad",
    "mark_iv_tank",
    "a7v",
    "cavalry_troop",
]


class TestWW1Units:
    """WW1 unit YAML loading."""

    @pytest.fixture()
    def unit_loader(self):
        from stochastic_warfare.entities.loader import UnitLoader
        base = UnitLoader(DATA_DIR / "units")
        base.load_all()
        era = UnitLoader(WW1_DIR / "units")
        era.load_all()
        base._definitions.update(era._definitions)
        return base

    @pytest.mark.parametrize("unit_type", _WW1_UNITS)
    def test_unit_loads(self, unit_loader, unit_type: str) -> None:
        defn = unit_loader._definitions.get(unit_type)
        assert defn is not None, f"Unit {unit_type} not found"

    @pytest.mark.parametrize("unit_type", _WW1_UNITS)
    def test_unit_has_display_name(self, unit_loader, unit_type: str) -> None:
        defn = unit_loader._definitions[unit_type]
        assert defn.display_name

    def test_mark_iv_is_armor(self, unit_loader) -> None:
        defn = unit_loader._definitions["mark_iv_tank"]
        assert defn.ground_type == "ARMOR"

    def test_infantry_speed(self, unit_loader) -> None:
        defn = unit_loader._definitions["british_infantry_platoon"]
        assert 1.0 <= defn.max_speed <= 2.0


# ---------------------------------------------------------------------------
# YAML data loading — weapons
# ---------------------------------------------------------------------------

_WW1_WEAPONS = [
    "lee_enfield",
    "gewehr_98",
    "maxim_mg08",
    "lewis_gun",
    "18pdr_field_gun",
    "77mm_fk96",
    "21cm_morser",
    "mills_bomb",
]


class TestWW1Weapons:
    """WW1 weapon YAML loading."""

    @pytest.fixture()
    def weapon_loader(self):
        from stochastic_warfare.combat.ammunition import WeaponLoader
        base = WeaponLoader(DATA_DIR / "weapons")
        base.load_all()
        era = WeaponLoader(WW1_DIR / "weapons")
        era.load_all()
        base._definitions.update(era._definitions)
        return base

    @pytest.mark.parametrize("weapon_id", _WW1_WEAPONS)
    def test_weapon_loads(self, weapon_loader, weapon_id: str) -> None:
        defn = weapon_loader._definitions.get(weapon_id)
        assert defn is not None, f"Weapon {weapon_id} not found"

    @pytest.mark.parametrize("weapon_id", _WW1_WEAPONS)
    def test_weapon_has_ammo(self, weapon_loader, weapon_id: str) -> None:
        defn = weapon_loader._definitions[weapon_id]
        assert len(defn.compatible_ammo) > 0

    def test_maxim_requires_deployed(self, weapon_loader) -> None:
        defn = weapon_loader._definitions["maxim_mg08"]
        assert defn.requires_deployed is True

    def test_lee_enfield_not_deployed(self, weapon_loader) -> None:
        defn = weapon_loader._definitions["lee_enfield"]
        assert defn.requires_deployed is False


# ---------------------------------------------------------------------------
# YAML data loading — ammunition
# ---------------------------------------------------------------------------

_WW1_AMMO = [
    "303_ball",
    "303_ap",
    "792mm_s_patrone",
    "18pdr_shrapnel",
    "18pdr_he",
    "77mm_he",
    "77mm_shrapnel",
    "21cm_he",
    "mills_bomb_frag",
    "77mm_gas_shell",
]


class TestWW1Ammo:
    """WW1 ammunition YAML loading."""

    @pytest.fixture()
    def ammo_loader(self):
        from stochastic_warfare.combat.ammunition import AmmoLoader
        base = AmmoLoader(DATA_DIR / "ammunition")
        base.load_all()
        era = AmmoLoader(WW1_DIR / "ammunition")
        era.load_all()
        base._definitions.update(era._definitions)
        return base

    @pytest.mark.parametrize("ammo_id", _WW1_AMMO)
    def test_ammo_loads(self, ammo_loader, ammo_id: str) -> None:
        defn = ammo_loader._definitions.get(ammo_id)
        assert defn is not None, f"Ammo {ammo_id} not found"

    def test_gas_shell_is_chemical(self, ammo_loader) -> None:
        defn = ammo_loader._definitions["77mm_gas_shell"]
        assert defn.ammo_type == "CHEMICAL"

    def test_he_has_blast(self, ammo_loader) -> None:
        defn = ammo_loader._definitions["18pdr_he"]
        assert defn.blast_radius_m > 0


# ---------------------------------------------------------------------------
# YAML data loading — sensors
# ---------------------------------------------------------------------------

_WW1_SENSORS = [
    "binoculars_ww1",
    "sound_ranging",
    "flash_spotting",
    "observation_balloon",
    "aircraft_recon",
]


class TestWW1Sensors:
    """WW1 sensor YAML loading."""

    @pytest.fixture()
    def sensor_loader(self):
        from stochastic_warfare.detection.sensors import SensorLoader
        base = SensorLoader(DATA_DIR / "sensors")
        base.load_all()
        era = SensorLoader(WW1_DIR / "sensors")
        era.load_all()
        base._definitions.update(era._definitions)
        return base

    @pytest.mark.parametrize("sensor_id", _WW1_SENSORS)
    def test_sensor_loads(self, sensor_loader, sensor_id: str) -> None:
        defn = sensor_loader._definitions.get(sensor_id)
        assert defn is not None, f"Sensor {sensor_id} not found"

    @pytest.mark.parametrize("sensor_id", _WW1_SENSORS)
    def test_sensor_is_visual(self, sensor_loader, sensor_id: str) -> None:
        defn = sensor_loader._definitions[sensor_id]
        assert defn.sensor_type == "VISUAL"

    def test_balloon_range(self, sensor_loader) -> None:
        defn = sensor_loader._definitions["observation_balloon"]
        assert defn.max_range_m >= 15000.0


# ---------------------------------------------------------------------------
# YAML data loading — signatures
# ---------------------------------------------------------------------------

_WW1_SIGS = [
    "british_infantry_platoon",
    "german_sturmtruppen",
    "french_poilu_squad",
    "mark_iv_tank",
    "a7v",
    "cavalry_troop",
]


class TestWW1Signatures:
    """WW1 signature YAML loading."""

    @pytest.fixture()
    def sig_loader(self):
        from stochastic_warfare.detection.signatures import SignatureLoader
        base = SignatureLoader(DATA_DIR / "signatures")
        base.load_all()
        era = SignatureLoader(WW1_DIR / "signatures")
        era.load_all()
        base._profiles.update(era._profiles)
        return base

    @pytest.mark.parametrize("profile_id", _WW1_SIGS)
    def test_sig_loads(self, sig_loader, profile_id: str) -> None:
        prof = sig_loader._profiles.get(profile_id)
        assert prof is not None, f"Signature {profile_id} not found"

    def test_tank_larger_cross_section(self, sig_loader) -> None:
        inf = sig_loader._profiles["british_infantry_platoon"]
        tank = sig_loader._profiles["mark_iv_tank"]
        assert tank.visual.cross_section_m2 > inf.visual.cross_section_m2


# ---------------------------------------------------------------------------
# YAML data loading — doctrine, commanders, comms
# ---------------------------------------------------------------------------


class TestWW1Doctrine:
    """WW1 doctrine YAML files exist and load."""

    def _load_yaml(self, path: Path) -> dict:
        import yaml
        with open(path) as f:
            return yaml.safe_load(f)

    def test_british_trench_warfare(self) -> None:
        d = self._load_yaml(WW1_DIR / "doctrine" / "british_trench_warfare.yaml")
        assert d["doctrine_id"] == "british_trench_warfare"

    def test_german_sturmtaktik(self) -> None:
        d = self._load_yaml(WW1_DIR / "doctrine" / "german_sturmtaktik.yaml")
        assert d["doctrine_id"] == "german_sturmtaktik"

    def test_french_attaque_outrance(self) -> None:
        d = self._load_yaml(WW1_DIR / "doctrine" / "french_attaque_outrance.yaml")
        assert d["doctrine_id"] == "french_attaque_outrance"


class TestWW1Commanders:
    """WW1 commander YAML files."""

    def _load_yaml(self, path: Path) -> dict:
        import yaml
        with open(path) as f:
            return yaml.safe_load(f)

    def test_haig(self) -> None:
        d = self._load_yaml(WW1_DIR / "commanders" / "haig_attritional.yaml")
        assert d["profile_id"] == "haig_attritional"
        assert 0.0 <= d["aggression"] <= 1.0

    def test_ludendorff(self) -> None:
        d = self._load_yaml(WW1_DIR / "commanders" / "ludendorff_storm.yaml")
        assert d["profile_id"] == "ludendorff_storm"

    def test_foch(self) -> None:
        d = self._load_yaml(WW1_DIR / "commanders" / "foch_unified.yaml")
        assert d["profile_id"] == "foch_unified"


class TestWW1Comms:
    """WW1 communications YAML files."""

    def _load_yaml(self, path: Path) -> dict:
        import yaml
        with open(path) as f:
            return yaml.safe_load(f)

    def test_field_telephone(self) -> None:
        d = self._load_yaml(WW1_DIR / "comms" / "field_telephone_ww1.yaml")
        assert d["comm_type"] == "WIRE"
        assert d["base_latency_s"] >= 1.0

    def test_runner_messenger(self) -> None:
        d = self._load_yaml(WW1_DIR / "comms" / "runner_messenger_ww1.yaml")
        assert d["comm_type"] == "MESSENGER"
        assert d["base_latency_s"] >= 300.0


# ---------------------------------------------------------------------------
# CBRN phosgene agent
# ---------------------------------------------------------------------------


class TestPhosgeneAgent:
    """Phosgene CBRN agent YAML."""

    def _load_yaml(self, path: Path) -> dict:
        import yaml
        with open(path) as f:
            return yaml.safe_load(f)

    def test_phosgene_loads(self) -> None:
        d = self._load_yaml(DATA_DIR / "cbrn" / "agents" / "phosgene.yaml")
        assert d["agent_id"] == "phosgene"
        assert d["category"] == 2  # CHOKING
        assert d["lct50_mg_min_m3"] == 3200.0
