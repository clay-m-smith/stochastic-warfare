"""Phase 20d — WW2 Validation Scenarios tests.

Tests that WW2 validation scenarios load correctly with era framework,
that modern systems are disabled, and that scenarios can be run through
the simulation engine.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from stochastic_warfare.core.era import Era, get_era_config
from stochastic_warfare.simulation.scenario import CampaignScenarioConfig

# ---------------------------------------------------------------------------
# Scenario paths
# ---------------------------------------------------------------------------

_DATA_DIR = Path("data")
_WW2_SCENARIOS_DIR = _DATA_DIR / "eras" / "ww2" / "scenarios"

_KURSK_PATH = _WW2_SCENARIOS_DIR / "kursk" / "scenario.yaml"
_MIDWAY_PATH = _WW2_SCENARIOS_DIR / "midway" / "scenario.yaml"
_BOCAGE_PATH = _WW2_SCENARIOS_DIR / "normandy_bocage" / "scenario.yaml"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _load_scenario_config(path: Path) -> CampaignScenarioConfig:
    """Load and parse a scenario YAML into CampaignScenarioConfig."""
    with open(path) as f:
        raw = yaml.safe_load(f)
    return CampaignScenarioConfig.model_validate(raw)


# ---------------------------------------------------------------------------
# Kursk scenario tests
# ---------------------------------------------------------------------------


class TestKurskScenario:
    """Prokhorovka/Kursk scenario YAML validation."""

    def test_scenario_loads(self) -> None:
        cfg = _load_scenario_config(_KURSK_PATH)
        assert cfg.name == "Prokhorovka Tank Battle (Kursk, 1943)"

    def test_era_is_ww2(self) -> None:
        cfg = _load_scenario_config(_KURSK_PATH)
        assert cfg.era == "ww2"

    def test_two_sides(self) -> None:
        cfg = _load_scenario_config(_KURSK_PATH)
        assert len(cfg.sides) == 2
        sides = {s.side for s in cfg.sides}
        assert sides == {"soviet", "german"}

    def test_soviet_units(self) -> None:
        cfg = _load_scenario_config(_KURSK_PATH)
        soviet = [s for s in cfg.sides if s.side == "soviet"][0]
        unit_types = [u["unit_type"] for u in soviet.units]
        assert "t34_85" in unit_types

    def test_german_units(self) -> None:
        cfg = _load_scenario_config(_KURSK_PATH)
        german = [s for s in cfg.sides if s.side == "german"][0]
        unit_types = [u["unit_type"] for u in german.units]
        assert "tiger_i" in unit_types
        assert "panther" in unit_types

    def test_has_objectives(self) -> None:
        cfg = _load_scenario_config(_KURSK_PATH)
        assert len(cfg.objectives) > 0

    def test_has_victory_conditions(self) -> None:
        cfg = _load_scenario_config(_KURSK_PATH)
        assert len(cfg.victory_conditions) > 0

    def test_era_config_disables_modern(self) -> None:
        cfg = _load_scenario_config(_KURSK_PATH)
        era_cfg = get_era_config(cfg.era)
        assert "ew" in era_cfg.disabled_modules
        assert "space" in era_cfg.disabled_modules
        assert "gps" in era_cfg.disabled_modules


# ---------------------------------------------------------------------------
# Midway scenario tests
# ---------------------------------------------------------------------------


class TestMidwayScenario:
    """Battle of Midway scenario YAML validation."""

    def test_scenario_loads(self) -> None:
        cfg = _load_scenario_config(_MIDWAY_PATH)
        assert "Midway" in cfg.name

    def test_era_is_ww2(self) -> None:
        cfg = _load_scenario_config(_MIDWAY_PATH)
        assert cfg.era == "ww2"

    def test_two_sides(self) -> None:
        cfg = _load_scenario_config(_MIDWAY_PATH)
        assert len(cfg.sides) == 2

    def test_naval_terrain(self) -> None:
        cfg = _load_scenario_config(_MIDWAY_PATH)
        assert cfg.terrain.terrain_type == "open_ocean"
        assert cfg.terrain.width_m >= 50000

    def test_has_objectives(self) -> None:
        cfg = _load_scenario_config(_MIDWAY_PATH)
        assert len(cfg.objectives) > 0


# ---------------------------------------------------------------------------
# Normandy Bocage scenario tests
# ---------------------------------------------------------------------------


class TestNormandyBocageScenario:
    """Normandy bocage fighting scenario YAML validation."""

    def test_scenario_loads(self) -> None:
        cfg = _load_scenario_config(_BOCAGE_PATH)
        assert "Normandy" in cfg.name or "Bocage" in cfg.name

    def test_era_is_ww2(self) -> None:
        cfg = _load_scenario_config(_BOCAGE_PATH)
        assert cfg.era == "ww2"

    def test_infantry_units(self) -> None:
        cfg = _load_scenario_config(_BOCAGE_PATH)
        all_unit_types = []
        for side in cfg.sides:
            all_unit_types.extend(u["unit_type"] for u in side.units)
        assert "us_rifle_squad_ww2" in all_unit_types
        assert "wehrmacht_rifle_squad" in all_unit_types

    def test_close_terrain(self) -> None:
        cfg = _load_scenario_config(_BOCAGE_PATH)
        assert cfg.terrain.width_m <= 5000  # close combat

    def test_terrain_features(self) -> None:
        cfg = _load_scenario_config(_BOCAGE_PATH)
        assert len(cfg.terrain.features) > 0


# ---------------------------------------------------------------------------
# Era framework integration tests
# ---------------------------------------------------------------------------


class TestEraIntegration:
    """Era framework integration with WW2 scenarios."""

    @pytest.mark.parametrize(
        "path",
        [_KURSK_PATH, _MIDWAY_PATH, _BOCAGE_PATH],
        ids=["kursk", "midway", "bocage"],
    )
    def test_all_scenarios_parse(self, path: Path) -> None:
        cfg = _load_scenario_config(path)
        assert cfg.era == "ww2"

    def test_ww2_era_config_loaded(self) -> None:
        era_cfg = get_era_config("ww2")
        assert era_cfg.era == Era.WW2
        assert "thermal_sights" in era_cfg.disabled_modules
        assert "pgm" in era_cfg.disabled_modules
        assert "data_links" in era_cfg.disabled_modules

    def test_ww2_sensor_types_limited(self) -> None:
        era_cfg = get_era_config("ww2")
        assert "VISUAL" in era_cfg.available_sensor_types
        assert "RADAR" in era_cfg.available_sensor_types
        assert "THERMAL" not in era_cfg.available_sensor_types


# ---------------------------------------------------------------------------
# Backward compatibility — modern scenarios unaffected
# ---------------------------------------------------------------------------


class TestModernScenariosUnchanged:
    """Existing modern scenarios still work after era framework added."""

    def test_golan_campaign_loads(self) -> None:
        path = _DATA_DIR / "scenarios" / "golan_campaign" / "scenario.yaml"
        if not path.exists():
            pytest.skip("Golan campaign scenario not found")
        cfg = _load_scenario_config(path)
        assert cfg.era == "modern"

    def test_test_campaign_loads(self) -> None:
        path = _DATA_DIR / "scenarios" / "test_campaign" / "scenario.yaml"
        if not path.exists():
            pytest.skip("Test campaign scenario not found")
        cfg = _load_scenario_config(path)
        assert cfg.era == "modern"

    def test_modern_era_all_enabled(self) -> None:
        era_cfg = get_era_config("modern")
        assert era_cfg.disabled_modules == set()
        assert era_cfg.available_sensor_types == set()

    def test_modern_config_no_era_field_defaults(self) -> None:
        raw = {
            "name": "no_era_field_test",
            "date": "2024-01-01",
            "duration_hours": 1.0,
            "terrain": {"width_m": 1000, "height_m": 1000},
            "sides": [
                {"side": "blue", "units": []},
                {"side": "red", "units": []},
            ],
        }
        cfg = CampaignScenarioConfig.model_validate(raw)
        assert cfg.era == "modern"

    def test_golan_has_no_era_field(self) -> None:
        """Existing campaign YAMLs without era: field default to modern."""
        path = _DATA_DIR / "scenarios" / "golan_campaign" / "scenario.yaml"
        if not path.exists():
            pytest.skip("Golan campaign scenario not found")
        with open(path) as f:
            raw = yaml.safe_load(f)
        assert "era" not in raw  # no era field in existing YAML
        cfg = CampaignScenarioConfig.model_validate(raw)
        assert cfg.era == "modern"  # defaults correctly
