"""Phase 80 structural + integration tests — API & Frontend Sync.

Verifies enable_all_modern meta-flag, ScenarioSummary has_space/has_dew,
eastern_front_1943 weapon fix, golan_heights victory_conditions,
calibration exercise scenarios, and WW2 weapon data.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
SCENARIOS = DATA / "scenarios"
WW2_WEAPONS = DATA / "eras" / "ww2" / "weapons"
WW2_AMMO = DATA / "eras" / "ww2" / "ammunition" / "small_arms"


# ---------------------------------------------------------------------------
# ScenarioSummary schema — has_space, has_dew
# ---------------------------------------------------------------------------


class TestScenarioSummarySchema:
    """ScenarioSummary pydantic model has the new fields."""

    def test_has_space_field_exists(self):
        from api.schemas import ScenarioSummary
        s = ScenarioSummary(name="test")
        assert hasattr(s, "has_space")
        assert s.has_space is False

    def test_has_dew_field_exists(self):
        from api.schemas import ScenarioSummary
        s = ScenarioSummary(name="test")
        assert hasattr(s, "has_dew")
        assert s.has_dew is False


# ---------------------------------------------------------------------------
# _extract_summary wiring
# ---------------------------------------------------------------------------


class TestExtractSummary:
    """_extract_summary sets has_space/has_dew from config keys."""

    def test_space_config_detected(self):
        from api.routers.scenarios import _extract_summary
        cfg = {"name": "test", "space_config": {"enable_space": True}}
        summary = _extract_summary("test", cfg)
        assert summary.has_space is True
        assert summary.has_dew is False

    def test_dew_config_detected(self):
        from api.routers.scenarios import _extract_summary
        cfg = {"name": "test", "dew_config": {"enable_dew": True}}
        summary = _extract_summary("test", cfg)
        assert summary.has_dew is True
        assert summary.has_space is False


# ---------------------------------------------------------------------------
# enable_all_modern meta-flag
# ---------------------------------------------------------------------------


class TestEnableAllModern:
    """CalibrationSchema.enable_all_modern sets 21 flags, excludes deferred."""

    def test_enable_all_modern_sets_21_flags(self):
        from stochastic_warfare.simulation.calibration import CalibrationSchema
        cal = CalibrationSchema(enable_all_modern=True)
        assert cal.enable_fog_of_war is True
        assert cal.enable_air_routing is True
        assert cal.enable_space_effects is True
        assert cal.enable_unconventional_warfare is True
        assert cal.enable_mine_persistence is True

    def test_enable_all_modern_false_leaves_defaults(self):
        from stochastic_warfare.simulation.calibration import CalibrationSchema
        cal = CalibrationSchema(enable_all_modern=False)
        assert cal.enable_fog_of_war is False
        assert cal.enable_air_routing is False

    def test_deferred_flags_excluded(self):
        from stochastic_warfare.simulation.calibration import CalibrationSchema
        cal = CalibrationSchema(enable_all_modern=True)
        # These 7 deferred flags must NOT be set by enable_all_modern
        assert cal.enable_fuel_consumption is False
        assert cal.enable_ammo_gate is False
        assert cal.enable_command_hierarchy is False
        assert cal.enable_carrier_ops is False
        assert cal.enable_ice_crossing is False
        assert cal.enable_bridge_capacity is False
        assert cal.enable_environmental_fatigue is False


# ---------------------------------------------------------------------------
# Eastern Front 1943 weapon fix
# ---------------------------------------------------------------------------


class TestEasternFrontWeapons:
    """eastern_front_1943 uses WW2 weapon IDs, not WW1."""

    def _load(self):
        path = SCENARIOS / "eastern_front_1943" / "scenario.yaml"
        return yaml.safe_load(path.read_text())

    def test_no_ww1_weapon_ids(self):
        cfg = self._load()
        assignments = cfg.get("calibration_overrides", {}).get("weapon_assignments", {})
        ww1_ids = {"lee_enfield", "gewehr_98", "mills_bomb"}
        used_ids = set(assignments.values())
        assert used_ids.isdisjoint(ww1_ids), f"WW1 IDs still referenced: {used_ids & ww1_ids}"

    def test_ww2_weapon_ids_present(self):
        cfg = self._load()
        assignments = cfg.get("calibration_overrides", {}).get("weapon_assignments", {})
        used_ids = set(assignments.values())
        expected = {"mosin_nagant", "kar98k", "ppsh41", "stielhandgranate", "rgd33"}
        assert expected.issubset(used_ids), f"Missing WW2 IDs: {expected - used_ids}"


# ---------------------------------------------------------------------------
# Golan Heights victory conditions
# ---------------------------------------------------------------------------


class TestGolanVictoryConditions:
    """golan_heights has explicit victory_conditions."""

    def _load(self):
        path = SCENARIOS / "golan_heights" / "scenario.yaml"
        return yaml.safe_load(path.read_text())

    def test_victory_conditions_exist(self):
        cfg = self._load()
        assert "victory_conditions" in cfg

    def test_victory_condition_types(self):
        cfg = self._load()
        vc = cfg["victory_conditions"]
        types = {c["type"] for c in vc}
        assert "force_destroyed" in types
        assert "time_expired" in types


# ---------------------------------------------------------------------------
# Calibration exercise scenarios
# ---------------------------------------------------------------------------


class TestCalibrationExerciseScenarios:
    """Three calibration exercise scenarios load and contain non-default fields."""

    def test_arctic_scenario_loads(self):
        path = SCENARIOS / "calibration_arctic" / "scenario.yaml"
        cfg = yaml.safe_load(path.read_text())
        cal = cfg.get("calibration_overrides", {})
        assert cal.get("cold_casualty_base_rate") == 0.03
        assert cal.get("dig_in_ticks") == 60

    def test_urban_cbrn_scenario_loads(self):
        path = SCENARIOS / "calibration_urban_cbrn" / "scenario.yaml"
        cfg = yaml.safe_load(path.read_text())
        cal = cfg.get("calibration_overrides", {})
        assert cal.get("gas_casualty_floor") == 0.15
        assert cal.get("c2_min_effectiveness") == 0.2

    def test_air_ground_scenario_loads(self):
        path = SCENARIOS / "calibration_air_ground" / "scenario.yaml"
        cfg = yaml.safe_load(path.read_text())
        cal = cfg.get("calibration_overrides", {})
        assert cal.get("cloud_ceiling_min_attack_m") == 800
        assert cal.get("planning_available_time_s") == 3600


# ---------------------------------------------------------------------------
# WW2 weapon & ammo data
# ---------------------------------------------------------------------------


class TestWW2WeaponData:
    """New WW2 weapon and ammo YAML files exist and parse correctly."""

    def test_weapon_files_exist(self):
        expected_guns = ["kar98k.yaml", "mosin_nagant.yaml", "ppsh41.yaml"]
        expected_explosives = ["stielhandgranate.yaml", "rgd33.yaml"]
        for f in expected_guns:
            assert (WW2_WEAPONS / "guns" / f).is_file(), f"Missing {f}"
        for f in expected_explosives:
            assert (WW2_WEAPONS / "explosives" / f).is_file(), f"Missing {f}"

    def test_ammo_files_exist(self):
        expected = [
            "792x57mm_mauser.yaml", "762x54r.yaml", "762x25mm_tokarev.yaml",
            "stielhandgranate_charge.yaml", "rgd33_charge.yaml",
        ]
        for f in expected:
            assert (WW2_AMMO / f).is_file(), f"Missing {f}"

    def test_weapons_have_required_fields(self):
        required = {"weapon_id", "display_name", "category", "compatible_ammo"}
        for subdir in ["guns/kar98k.yaml", "guns/mosin_nagant.yaml", "guns/ppsh41.yaml",
                       "explosives/stielhandgranate.yaml", "explosives/rgd33.yaml"]:
            path = WW2_WEAPONS / subdir
            data = yaml.safe_load(path.read_text())
            missing = required - set(data.keys())
            assert not missing, f"{subdir} missing fields: {missing}"

    def test_ammo_has_required_fields(self):
        required = {"ammo_id", "display_name", "ammo_type", "mass_kg"}
        for f in ["792x57mm_mauser.yaml", "762x54r.yaml", "762x25mm_tokarev.yaml",
                   "stielhandgranate_charge.yaml", "rgd33_charge.yaml"]:
            path = WW2_AMMO / f
            data = yaml.safe_load(path.read_text())
            missing = required - set(data.keys())
            assert not missing, f"{f} missing fields: {missing}"
