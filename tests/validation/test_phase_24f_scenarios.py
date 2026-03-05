"""Phase 24f validation scenario loading tests.

Verifies that the four Phase 24f scenario YAML files load and validate
correctly against the CampaignScenarioConfig schema.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from stochastic_warfare.simulation.scenario import CampaignScenarioConfig


_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_SCENARIOS_DIR = _DATA_DIR / "scenarios"


def _load_scenario(name: str) -> CampaignScenarioConfig:
    """Load and validate a scenario YAML by directory name."""
    path = _SCENARIOS_DIR / name / "scenario.yaml"
    with open(path) as f:
        raw = yaml.safe_load(f)
    return CampaignScenarioConfig.model_validate(raw)


# ===========================================================================
# Halabja 1988
# ===========================================================================


class TestHalabja:
    """Halabja Chemical Attack 1988 scenario."""

    def test_loads_and_validates(self):
        cfg = _load_scenario("halabja_1988")
        assert cfg.name == "Halabja Chemical Attack 1988"

    def test_has_escalation_config(self):
        cfg = _load_scenario("halabja_1988")
        assert cfg.escalation_config is not None
        assert "entry_thresholds" in cfg.escalation_config

    def test_two_sides(self):
        cfg = _load_scenario("halabja_1988")
        assert len(cfg.sides) == 2
        side_names = {s.side for s in cfg.sides}
        assert side_names == {"blue", "red"}

    def test_has_territory_control_vc(self):
        cfg = _load_scenario("halabja_1988")
        vc_types = {vc.type for vc in cfg.victory_conditions}
        assert "territory_control" in vc_types

    def test_duration(self):
        cfg = _load_scenario("halabja_1988")
        assert cfg.duration_hours == 48


# ===========================================================================
# Srebrenica 1995
# ===========================================================================


class TestSrebrenica:
    """Srebrenica Protected Zone 1995 scenario."""

    def test_loads_and_validates(self):
        cfg = _load_scenario("srebrenica_1995")
        assert cfg.name == "Srebrenica Protected Zone 1995"

    def test_two_sides_correct_units(self):
        cfg = _load_scenario("srebrenica_1995")
        assert len(cfg.sides) == 2
        blue = next(s for s in cfg.sides if s.side == "blue")
        red = next(s for s in cfg.sides if s.side == "red")
        blue_total = sum(u["count"] for u in blue.units)
        red_total = sum(u["count"] for u in red.units)
        assert blue_total == 2
        assert red_total == 11

    def test_escalation_config_present(self):
        cfg = _load_scenario("srebrenica_1995")
        assert cfg.escalation_config is not None

    def test_duration_72_hours(self):
        cfg = _load_scenario("srebrenica_1995")
        assert cfg.duration_hours == 72

    def test_has_victory_conditions(self):
        cfg = _load_scenario("srebrenica_1995")
        assert len(cfg.victory_conditions) >= 1


# ===========================================================================
# Eastern Front 1943
# ===========================================================================


class TestEasternFront:
    """Eastern Front Kursk Sector 1943 scenario."""

    def test_loads_and_validates(self):
        cfg = _load_scenario("eastern_front_1943")
        assert cfg.name == "Eastern Front Kursk Sector 1943"

    def test_has_force_destroyed_vc(self):
        cfg = _load_scenario("eastern_front_1943")
        vc_types = {vc.type for vc in cfg.victory_conditions}
        assert "force_destroyed" in vc_types

    def test_duration_168_hours(self):
        cfg = _load_scenario("eastern_front_1943")
        assert cfg.duration_hours == 168

    def test_escalation_config_present(self):
        cfg = _load_scenario("eastern_front_1943")
        assert cfg.escalation_config is not None

    def test_two_sides(self):
        cfg = _load_scenario("eastern_front_1943")
        assert len(cfg.sides) == 2


# ===========================================================================
# COIN Campaign
# ===========================================================================


class TestCOIN:
    """COIN Campaign scenario."""

    def test_loads_and_validates(self):
        cfg = _load_scenario("coin_campaign")
        assert cfg.name == "COIN Campaign"

    def test_has_time_expired_vc(self):
        cfg = _load_scenario("coin_campaign")
        vc_types = {vc.type for vc in cfg.victory_conditions}
        assert "time_expired" in vc_types

    def test_duration_720_hours(self):
        cfg = _load_scenario("coin_campaign")
        assert cfg.duration_hours == 720

    def test_commander_profiles(self):
        cfg = _load_scenario("coin_campaign")
        profiles = {s.commander_profile for s in cfg.sides}
        assert "pmc_operator" in profiles
        assert "insurgent_leader" in profiles

    def test_escalation_config_present(self):
        cfg = _load_scenario("coin_campaign")
        assert cfg.escalation_config is not None
