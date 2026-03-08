"""Phase 22a tests — Napoleonic era config and YAML data loading.

Tests that:
- Napoleonic era config is registered and has correct properties
- CBRN IS disabled (no chemical warfare in Napoleonic era)
- All Napoleonic YAML data files load without validation errors
- Unit, weapon, ammo, sensor, signature, doctrine, commander, comms
- SimulationContext has 6 new Napoleonic engine fields
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import make_rng

# ---------------------------------------------------------------------------
# Era config tests
# ---------------------------------------------------------------------------


class TestNapoleonicEraConfig:
    """Napoleonic era configuration."""

    def test_napoleonic_registered(self) -> None:
        from stochastic_warfare.core.era import get_era_config
        cfg = get_era_config("napoleonic")
        assert cfg.era.value == "napoleonic"

    def test_ew_disabled(self) -> None:
        from stochastic_warfare.core.era import get_era_config
        cfg = get_era_config("napoleonic")
        assert "ew" in cfg.disabled_modules

    def test_space_disabled(self) -> None:
        from stochastic_warfare.core.era import get_era_config
        cfg = get_era_config("napoleonic")
        assert "space" in cfg.disabled_modules

    def test_gps_disabled(self) -> None:
        from stochastic_warfare.core.era import get_era_config
        cfg = get_era_config("napoleonic")
        assert "gps" in cfg.disabled_modules

    def test_thermal_sights_disabled(self) -> None:
        from stochastic_warfare.core.era import get_era_config
        cfg = get_era_config("napoleonic")
        assert "thermal_sights" in cfg.disabled_modules

    def test_data_links_disabled(self) -> None:
        from stochastic_warfare.core.era import get_era_config
        cfg = get_era_config("napoleonic")
        assert "data_links" in cfg.disabled_modules

    def test_pgm_disabled(self) -> None:
        from stochastic_warfare.core.era import get_era_config
        cfg = get_era_config("napoleonic")
        assert "pgm" in cfg.disabled_modules

    def test_cbrn_disabled(self) -> None:
        """Unlike WW1, Napoleonic era has NO chemical weapons."""
        from stochastic_warfare.core.era import get_era_config
        cfg = get_era_config("napoleonic")
        assert "cbrn" in cfg.disabled_modules

    def test_visual_only_sensor(self) -> None:
        from stochastic_warfare.core.era import get_era_config
        cfg = get_era_config("napoleonic")
        assert cfg.available_sensor_types == {"VISUAL"}

    def test_c2_delay_multiplier(self) -> None:
        from stochastic_warfare.core.era import get_era_config
        cfg = get_era_config("napoleonic")
        assert cfg.physics_overrides.get("c2_delay_multiplier") == 8.0

    def test_nuclear_disabled_override(self) -> None:
        from stochastic_warfare.core.era import get_era_config
        cfg = get_era_config("napoleonic")
        assert cfg.physics_overrides.get("cbrn_nuclear_enabled") is False

    def test_modern_unaffected(self) -> None:
        from stochastic_warfare.core.era import get_era_config
        cfg = get_era_config("modern")
        assert len(cfg.disabled_modules) == 0

    def test_ww1_unaffected(self) -> None:
        from stochastic_warfare.core.era import get_era_config
        cfg = get_era_config("ww1")
        assert "cbrn" not in cfg.disabled_modules

    def test_ww2_unaffected(self) -> None:
        from stochastic_warfare.core.era import get_era_config
        cfg = get_era_config("ww2")
        assert cfg.era.value == "ww2"


# ---------------------------------------------------------------------------
# SimulationContext new fields
# ---------------------------------------------------------------------------


class TestContextFields:
    """SimulationContext has Napoleonic engine fields."""

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
            name="test", date="1805-12-02", duration_hours=1.0,
            terrain=TerrainConfig(width_m=1000, height_m=1000),
            sides=[
                SideConfig(side="a", units=[]),
                SideConfig(side="b", units=[]),
            ],
        )
        return SimulationContext(
            config=config,
            clock=SimulationClock(
                start=datetime(1805, 12, 2, tzinfo=timezone.utc),
                tick_duration=timedelta(seconds=5),
            ),
            rng_manager=RNGManager(42),
            event_bus=EventBus(),
        )

    def test_volley_fire_engine_default_none(self) -> None:
        ctx = self._make_ctx()
        assert ctx.volley_fire_engine is None

    def test_melee_engine_default_none(self) -> None:
        ctx = self._make_ctx()
        assert ctx.melee_engine is None

    def test_cavalry_engine_default_none(self) -> None:
        ctx = self._make_ctx()
        assert ctx.cavalry_engine is None

    def test_formation_napoleonic_engine_default_none(self) -> None:
        ctx = self._make_ctx()
        assert ctx.formation_napoleonic_engine is None

    def test_courier_engine_default_none(self) -> None:
        ctx = self._make_ctx()
        assert ctx.courier_engine is None

    def test_foraging_engine_default_none(self) -> None:
        ctx = self._make_ctx()
        assert ctx.foraging_engine is None


# ---------------------------------------------------------------------------
# YAML data loading — units
# ---------------------------------------------------------------------------

DATA_DIR = Path("data")
NAP_DIR = DATA_DIR / "eras" / "napoleonic"

_NAP_UNITS = [
    "french_line_infantry",
    "french_light_infantry",
    "french_old_guard",
    "british_line_infantry",
    "british_rifle_company",
    "cuirassier_squadron",
    "hussar_squadron",
    "lancer_squadron",
    "horse_artillery_battery",
    "foot_artillery_battery",
]


class TestNapoleonicUnits:
    """Napoleonic unit YAML loading."""

    @pytest.fixture()
    def unit_loader(self):
        from stochastic_warfare.entities.loader import UnitLoader
        base = UnitLoader(DATA_DIR / "units")
        base.load_all()
        era = UnitLoader(NAP_DIR / "units")
        era.load_all()
        base._definitions.update(era._definitions)
        return base

    @pytest.mark.parametrize("unit_type", _NAP_UNITS)
    def test_unit_loads(self, unit_loader, unit_type: str) -> None:
        defn = unit_loader._definitions.get(unit_type)
        assert defn is not None, f"Unit {unit_type} not found"

    @pytest.mark.parametrize("unit_type", _NAP_UNITS)
    def test_unit_has_display_name(self, unit_loader, unit_type: str) -> None:
        defn = unit_loader._definitions[unit_type]
        assert defn.display_name

    def test_cuirassier_armor(self, unit_loader) -> None:
        defn = unit_loader._definitions["cuirassier_squadron"]
        assert defn.armor_front > 0

    def test_infantry_speed(self, unit_loader) -> None:
        defn = unit_loader._definitions["french_line_infantry"]
        assert 1.0 <= defn.max_speed <= 2.0

    def test_cavalry_speed(self, unit_loader) -> None:
        defn = unit_loader._definitions["hussar_squadron"]
        assert defn.max_speed >= 7.0


# ---------------------------------------------------------------------------
# YAML data loading — weapons
# ---------------------------------------------------------------------------

_NAP_WEAPONS = [
    "brown_bess",
    "charleville_1777",
    "baker_rifle",
    "6pdr_cannon",
    "12pdr_cannon",
    "howitzer_napoleonic",
    "cavalry_saber",
    "lance",
    "bayonet",
]


class TestNapoleonicWeapons:
    """Napoleonic weapon YAML loading."""

    @pytest.fixture()
    def weapon_loader(self):
        from stochastic_warfare.combat.ammunition import WeaponLoader
        base = WeaponLoader(DATA_DIR / "weapons")
        base.load_all()
        era = WeaponLoader(NAP_DIR / "weapons")
        era.load_all()
        base._definitions.update(era._definitions)
        return base

    @pytest.mark.parametrize("weapon_id", _NAP_WEAPONS)
    def test_weapon_loads(self, weapon_loader, weapon_id: str) -> None:
        defn = weapon_loader._definitions.get(weapon_id)
        assert defn is not None, f"Weapon {weapon_id} not found"

    def test_musket_range(self, weapon_loader) -> None:
        defn = weapon_loader._definitions["brown_bess"]
        assert defn.max_range_m == 200.0

    def test_baker_longer_range(self, weapon_loader) -> None:
        defn = weapon_loader._definitions["baker_rifle"]
        assert defn.max_range_m > 200.0

    def test_cannon_requires_deployed(self, weapon_loader) -> None:
        defn = weapon_loader._definitions["12pdr_cannon"]
        assert defn.requires_deployed is True

    def test_melee_zero_velocity(self, weapon_loader) -> None:
        defn = weapon_loader._definitions["cavalry_saber"]
        assert defn.muzzle_velocity_mps == 0.0

    def test_melee_has_ammo(self, weapon_loader) -> None:
        defn = weapon_loader._definitions["bayonet"]
        assert len(defn.compatible_ammo) > 0
        assert "bayonet_thrust" in defn.compatible_ammo

    def test_musket_has_ammo(self, weapon_loader) -> None:
        defn = weapon_loader._definitions["charleville_1777"]
        assert len(defn.compatible_ammo) > 0

    def test_cannon_has_canister(self, weapon_loader) -> None:
        defn = weapon_loader._definitions["6pdr_cannon"]
        assert "canister_6pdr" in defn.compatible_ammo


# ---------------------------------------------------------------------------
# YAML data loading — ammunition
# ---------------------------------------------------------------------------

_NAP_AMMO = [
    "musket_ball_75",
    "musket_ball_69",
    "rifle_ball",
    "roundshot_6pdr",
    "roundshot_12pdr",
    "canister_6pdr",
    "canister_12pdr",
    "howitzer_shell_nap",
    "howitzer_canister_nap",
]


class TestNapoleonicAmmo:
    """Napoleonic ammunition YAML loading."""

    @pytest.fixture()
    def ammo_loader(self):
        from stochastic_warfare.combat.ammunition import AmmoLoader
        base = AmmoLoader(DATA_DIR / "ammunition")
        base.load_all()
        era = AmmoLoader(NAP_DIR / "ammunition")
        era.load_all()
        base._definitions.update(era._definitions)
        return base

    @pytest.mark.parametrize("ammo_id", _NAP_AMMO)
    def test_ammo_loads(self, ammo_loader, ammo_id: str) -> None:
        defn = ammo_loader._definitions.get(ammo_id)
        assert defn is not None, f"Ammo {ammo_id} not found"

    def test_canister_has_blast(self, ammo_loader) -> None:
        defn = ammo_loader._definitions["canister_6pdr"]
        assert defn.blast_radius_m > 0

    def test_musket_ball_no_blast(self, ammo_loader) -> None:
        defn = ammo_loader._definitions["musket_ball_75"]
        assert defn.blast_radius_m == 0.0

    def test_roundshot_is_ap(self, ammo_loader) -> None:
        defn = ammo_loader._definitions["roundshot_12pdr"]
        assert defn.ammo_type == "AP"


# ---------------------------------------------------------------------------
# YAML data loading — sensors
# ---------------------------------------------------------------------------

_NAP_SENSORS = [
    "telescope_napoleonic",
    "cavalry_scout",
    "observation_post_napoleonic",
]


class TestNapoleonicSensors:
    """Napoleonic sensor YAML loading."""

    @pytest.fixture()
    def sensor_loader(self):
        from stochastic_warfare.detection.sensors import SensorLoader
        base = SensorLoader(DATA_DIR / "sensors")
        base.load_all()
        era = SensorLoader(NAP_DIR / "sensors")
        era.load_all()
        base._definitions.update(era._definitions)
        return base

    @pytest.mark.parametrize("sensor_id", _NAP_SENSORS)
    def test_sensor_loads(self, sensor_loader, sensor_id: str) -> None:
        defn = sensor_loader._definitions.get(sensor_id)
        assert defn is not None, f"Sensor {sensor_id} not found"

    @pytest.mark.parametrize("sensor_id", _NAP_SENSORS)
    def test_sensor_is_visual(self, sensor_loader, sensor_id: str) -> None:
        defn = sensor_loader._definitions[sensor_id]
        assert defn.sensor_type == "VISUAL"

    def test_telescope_narrow_fov(self, sensor_loader) -> None:
        defn = sensor_loader._definitions["telescope_napoleonic"]
        assert defn.fov_deg <= 10.0

    def test_observation_post_long_range(self, sensor_loader) -> None:
        defn = sensor_loader._definitions["observation_post_napoleonic"]
        assert defn.max_range_m >= 8000.0


# ---------------------------------------------------------------------------
# YAML data loading — signatures
# ---------------------------------------------------------------------------

_NAP_SIGS = [
    "french_line_infantry",
    "french_light_infantry",
    "french_old_guard",
    "british_line_infantry",
    "british_rifle_company",
    "cuirassier_squadron",
    "hussar_squadron",
    "lancer_squadron",
    "horse_artillery_battery",
    "foot_artillery_battery",
]


class TestNapoleonicSignatures:
    """Napoleonic signature YAML loading."""

    @pytest.fixture()
    def sig_loader(self):
        from stochastic_warfare.detection.signatures import SignatureLoader
        base = SignatureLoader(DATA_DIR / "signatures")
        base.load_all()
        era = SignatureLoader(NAP_DIR / "signatures")
        era.load_all()
        base._profiles.update(era._profiles)
        return base

    @pytest.mark.parametrize("profile_id", _NAP_SIGS)
    def test_sig_loads(self, sig_loader, profile_id: str) -> None:
        prof = sig_loader._profiles.get(profile_id)
        assert prof is not None, f"Signature {profile_id} not found"

    def test_cavalry_larger_height(self, sig_loader) -> None:
        inf = sig_loader._profiles["french_line_infantry"]
        cav = sig_loader._profiles["cuirassier_squadron"]
        assert cav.visual.height_m > inf.visual.height_m

    def test_artillery_louder(self, sig_loader) -> None:
        inf = sig_loader._profiles["french_line_infantry"]
        art = sig_loader._profiles["foot_artillery_battery"]
        assert art.acoustic.noise_db > inf.acoustic.noise_db

    def test_zeroed_thermal(self, sig_loader) -> None:
        prof = sig_loader._profiles["french_line_infantry"]
        assert prof.thermal.emissivity == 0.0

    def test_zeroed_radar(self, sig_loader) -> None:
        prof = sig_loader._profiles["cuirassier_squadron"]
        assert prof.radar.rcs_frontal_m2 == 0.0


# ---------------------------------------------------------------------------
# YAML data loading — doctrine, commanders, comms
# ---------------------------------------------------------------------------


class TestNapoleonicDoctrine:
    """Napoleonic doctrine YAML files exist and load."""

    def _load_yaml(self, path: Path) -> dict:
        import yaml
        with open(path) as f:
            return yaml.safe_load(f)

    def test_french_grande_armee(self) -> None:
        d = self._load_yaml(NAP_DIR / "doctrine" / "french_grande_armee.yaml")
        assert d["doctrine_id"] == "french_grande_armee"
        assert d["category"] == "OFFENSIVE"

    def test_british_thin_red_line(self) -> None:
        d = self._load_yaml(NAP_DIR / "doctrine" / "british_thin_red_line.yaml")
        assert d["doctrine_id"] == "british_thin_red_line"
        assert d["category"] == "DEFENSIVE"

    def test_coalition_linear(self) -> None:
        d = self._load_yaml(NAP_DIR / "doctrine" / "coalition_linear.yaml")
        assert d["doctrine_id"] == "coalition_linear"
        assert d["category"] == "BALANCED"


class TestNapoleonicCommanders:
    """Napoleonic commander YAML files."""

    def _load_yaml(self, path: Path) -> dict:
        import yaml
        with open(path) as f:
            return yaml.safe_load(f)

    def test_napoleon(self) -> None:
        d = self._load_yaml(NAP_DIR / "commanders" / "napoleon_grande_armee.yaml")
        assert d["profile_id"] == "napoleon_grande_armee"
        assert d["aggression"] >= 0.8

    def test_wellington(self) -> None:
        d = self._load_yaml(NAP_DIR / "commanders" / "wellington_defense.yaml")
        assert d["profile_id"] == "wellington_defense"
        assert d["caution"] >= 0.7

    def test_blucher(self) -> None:
        d = self._load_yaml(NAP_DIR / "commanders" / "blucher_offensive.yaml")
        assert d["profile_id"] == "blucher_offensive"
        assert d["aggression"] >= 0.8


class TestNapoleonicComms:
    """Napoleonic communications YAML files."""

    def _load_yaml(self, path: Path) -> dict:
        import yaml
        with open(path) as f:
            return yaml.safe_load(f)

    def test_mounted_courier(self) -> None:
        d = self._load_yaml(NAP_DIR / "comms" / "mounted_courier.yaml")
        assert d["comm_type"] == "MESSENGER"
        assert d["base_latency_s"] >= 1000.0

    def test_drum_bugle(self) -> None:
        d = self._load_yaml(NAP_DIR / "comms" / "drum_bugle_signals.yaml")
        assert d["comm_type"] == "MESSENGER"
        assert d["max_range_m"] <= 500.0


# ---------------------------------------------------------------------------
# State persistence with Napoleonic engines
# ---------------------------------------------------------------------------


class TestStatePersistence:
    """Napoleonic engines persist in SimulationContext state."""

    def test_engines_in_state_roundtrip(self) -> None:
        from stochastic_warfare.simulation.scenario import (
            CampaignScenarioConfig,
            SimulationContext,
            TerrainConfig,
            SideConfig,
        )
        from stochastic_warfare.core.clock import SimulationClock
        from stochastic_warfare.core.events import EventBus
        from stochastic_warfare.core.rng import RNGManager
        from stochastic_warfare.combat.volley_fire import VolleyFireEngine
        from stochastic_warfare.movement.formation_napoleonic import (
            NapoleonicFormationEngine,
        )
        from datetime import datetime, timezone, timedelta

        config = CampaignScenarioConfig(
            name="nap_test", date="1805-12-02", duration_hours=1.0,
            era="napoleonic",
            terrain=TerrainConfig(width_m=1000, height_m=1000),
            sides=[
                SideConfig(side="a", units=[]),
                SideConfig(side="b", units=[]),
            ],
        )
        volley_eng = VolleyFireEngine(rng=make_rng(1))
        form_eng = NapoleonicFormationEngine()

        ctx = SimulationContext(
            config=config,
            clock=SimulationClock(
                start=datetime(1805, 12, 2, tzinfo=timezone.utc),
                tick_duration=timedelta(seconds=5),
            ),
            rng_manager=RNGManager(42),
            event_bus=EventBus(),
            volley_fire_engine=volley_eng,
            formation_napoleonic_engine=form_eng,
        )
        state = ctx.get_state()
        assert "volley_fire_engine" in state
        assert "formation_napoleonic_engine" in state
