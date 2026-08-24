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

    def test_no_unwired_c2_delay_proxy(self) -> None:
        from stochastic_warfare.core.era import get_era_config

        cfg = get_era_config("napoleonic")
        assert "c2_delay_multiplier" not in cfg.physics_overrides.model_dump(
            mode="json",
        )

    def test_no_unwired_nuclear_proxy(self) -> None:
        from stochastic_warfare.core.era import get_era_config

        cfg = get_era_config("napoleonic")
        assert "cbrn_nuclear_enabled" not in cfg.physics_overrides.model_dump(
            mode="json",
        )

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
            name="test",
            date="1805-12-02",
            duration_hours=1.0,
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
HISTORICAL_ERA = "napoleonic"


class TestNapoleonicUnits:
    """Napoleonic unit YAML loading."""

    def test_cuirassier_armor(self, era_unit_loader) -> None:
        defn = era_unit_loader._definitions["cuirassier_squadron"]
        assert defn.armor_front > 0

    def test_infantry_speed(self, era_unit_loader) -> None:
        defn = era_unit_loader._definitions["french_line_infantry"]
        assert 1.0 <= defn.max_speed <= 2.0

    def test_cavalry_speed(self, era_unit_loader) -> None:
        defn = era_unit_loader._definitions["hussar_squadron"]
        assert defn.max_speed >= 7.0


# ---------------------------------------------------------------------------
# YAML data loading — weapons
# ---------------------------------------------------------------------------


class TestNapoleonicWeapons:
    """Napoleonic weapon YAML loading."""

    def test_musket_range(self, era_weapon_loader) -> None:
        defn = era_weapon_loader._definitions["brown_bess"]
        assert defn.max_range_m == 200.0

    def test_baker_longer_range(self, era_weapon_loader) -> None:
        defn = era_weapon_loader._definitions["baker_rifle"]
        assert defn.max_range_m > 200.0

    def test_cannon_requires_deployed(self, era_weapon_loader) -> None:
        defn = era_weapon_loader._definitions["12pdr_cannon"]
        assert defn.requires_deployed is True

    def test_melee_zero_velocity(self, era_weapon_loader) -> None:
        defn = era_weapon_loader._definitions["cavalry_saber"]
        assert defn.muzzle_velocity_mps == 0.0

    def test_melee_has_ammo(self, era_weapon_loader) -> None:
        defn = era_weapon_loader._definitions["bayonet"]
        assert len(defn.compatible_ammo) > 0
        assert "bayonet_thrust" in defn.compatible_ammo

    def test_musket_has_ammo(self, era_weapon_loader) -> None:
        defn = era_weapon_loader._definitions["charleville_1777"]
        assert len(defn.compatible_ammo) > 0

    def test_cannon_has_canister(self, era_weapon_loader) -> None:
        defn = era_weapon_loader._definitions["6pdr_cannon"]
        assert "canister_6pdr" in defn.compatible_ammo


# ---------------------------------------------------------------------------
# YAML data loading — ammunition
# ---------------------------------------------------------------------------


class TestNapoleonicAmmo:
    """Napoleonic ammunition YAML loading."""

    def test_canister_has_blast(self, era_ammo_loader) -> None:
        defn = era_ammo_loader._definitions["canister_6pdr"]
        assert defn.blast_radius_m > 0

    def test_musket_ball_no_blast(self, era_ammo_loader) -> None:
        defn = era_ammo_loader._definitions["musket_ball_75"]
        assert defn.blast_radius_m == 0.0

    def test_roundshot_is_ap(self, era_ammo_loader) -> None:
        defn = era_ammo_loader._definitions["roundshot_12pdr"]
        assert defn.ammo_type == "AP"


# ---------------------------------------------------------------------------
# YAML data loading — sensors
# ---------------------------------------------------------------------------


class TestNapoleonicSensors:
    """Napoleonic sensor YAML loading."""

    def test_telescope_narrow_fov(self, era_sensor_loader) -> None:
        defn = era_sensor_loader._definitions["telescope_napoleonic"]
        assert defn.fov_deg <= 10.0

    def test_observation_post_long_range(self, era_sensor_loader) -> None:
        defn = era_sensor_loader._definitions["observation_post_napoleonic"]
        assert defn.max_range_m >= 8000.0


# ---------------------------------------------------------------------------
# YAML data loading — signatures
# ---------------------------------------------------------------------------


class TestNapoleonicSignatures:
    """Napoleonic signature YAML loading."""

    def test_cavalry_larger_height(self, era_sig_loader) -> None:
        inf = era_sig_loader._profiles["french_line_infantry"]
        cav = era_sig_loader._profiles["cuirassier_squadron"]
        assert cav.visual.height_m > inf.visual.height_m

    def test_artillery_louder(self, era_sig_loader) -> None:
        inf = era_sig_loader._profiles["french_line_infantry"]
        art = era_sig_loader._profiles["foot_artillery_battery"]
        assert art.acoustic.noise_db > inf.acoustic.noise_db

    def test_zeroed_thermal(self, era_sig_loader) -> None:
        prof = era_sig_loader._profiles["french_line_infantry"]
        assert prof.thermal.emissivity == 0.0

    def test_zeroed_radar(self, era_sig_loader) -> None:
        prof = era_sig_loader._profiles["cuirassier_squadron"]
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
            name="nap_test",
            date="1805-12-02",
            duration_hours=1.0,
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
