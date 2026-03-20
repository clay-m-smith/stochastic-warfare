"""Phase 30 — Scenario & Campaign Library tests.

Validates all new and modified scenario YAML files load correctly against
the CampaignScenarioConfig schema. Tests cover:
- 30a: 4 modern joint scenarios (Taiwan Strait, Korean Peninsula, Suwalki Gap, Hybrid Gray Zone)
- 30b: 4 historical scenarios (Jutland, Trafalgar, Salamis, Stalingrad)
- 30c: 3 modified scenarios (73 Easting fix, Midway fix, Golan expansion) + 2 new Falklands
- 30d: Cross-scenario validation (all scenarios load, domain coverage)
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from stochastic_warfare.simulation.scenario import CampaignScenarioConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_SCENARIOS_DIR = _DATA_DIR / "scenarios"
_ERAS_DIR = _DATA_DIR / "eras"


def _load_campaign_scenario(path: Path) -> CampaignScenarioConfig:
    """Load and validate a scenario YAML as CampaignScenarioConfig."""
    with open(path) as f:
        raw = yaml.safe_load(f)
    return CampaignScenarioConfig.model_validate(raw)


def _load_scenario_by_name(name: str) -> CampaignScenarioConfig:
    """Load a modern scenario from data/scenarios/{name}/scenario.yaml."""
    return _load_campaign_scenario(_SCENARIOS_DIR / name / "scenario.yaml")


def _load_era_scenario(era: str, name: str) -> CampaignScenarioConfig:
    """Load an era scenario from data/eras/{era}/scenarios/{name}/scenario.yaml."""
    return _load_campaign_scenario(
        _ERAS_DIR / era / "scenarios" / name / "scenario.yaml"
    )


# ===========================================================================
# 30a: Modern Joint Scenarios
# ===========================================================================


class TestTaiwanStrait:
    """Taiwan Strait joint air-naval scenario."""

    def test_loads_and_validates(self):
        cfg = _load_scenario_by_name("taiwan_strait")
        assert "Taiwan Strait" in cfg.name

    def test_era_is_modern(self):
        cfg = _load_scenario_by_name("taiwan_strait")
        assert cfg.era == "modern"

    def test_two_sides(self):
        cfg = _load_scenario_by_name("taiwan_strait")
        assert len(cfg.sides) == 2
        sides = {s.side for s in cfg.sides}
        assert sides == {"blue", "red"}

    def test_has_naval_units(self):
        cfg = _load_scenario_by_name("taiwan_strait")
        all_unit_types = []
        for side in cfg.sides:
            all_unit_types.extend(u["unit_type"] for u in side.units)
        assert "ddg51" in all_unit_types
        assert "sovremenny" in all_unit_types

    def test_has_ew_config(self):
        cfg = _load_scenario_by_name("taiwan_strait")
        assert cfg.ew_config is not None
        assert cfg.ew_config["enable_ew"] is True

    def test_has_escalation_config(self):
        cfg = _load_scenario_by_name("taiwan_strait")
        assert cfg.escalation_config is not None
        assert "entry_thresholds" in cfg.escalation_config

    def test_has_documented_outcomes(self):
        cfg = _load_scenario_by_name("taiwan_strait")
        raw = yaml.safe_load(
            open(_SCENARIOS_DIR / "taiwan_strait" / "scenario.yaml")
        )
        assert len(raw.get("documented_outcomes", [])) >= 2

    def test_duration_24h(self):
        cfg = _load_scenario_by_name("taiwan_strait")
        assert cfg.duration_hours == 24.0


class TestKoreanPeninsula:
    """Korean Peninsula combined arms defense scenario."""

    def test_loads_and_validates(self):
        cfg = _load_scenario_by_name("korean_peninsula")
        assert "Korean Peninsula" in cfg.name

    def test_era_is_modern(self):
        cfg = _load_scenario_by_name("korean_peninsula")
        assert cfg.era == "modern"

    def test_two_sides(self):
        cfg = _load_scenario_by_name("korean_peninsula")
        assert len(cfg.sides) == 2

    def test_has_armor_and_artillery(self):
        cfg = _load_scenario_by_name("korean_peninsula")
        all_types = []
        for side in cfg.sides:
            all_types.extend(u["unit_type"] for u in side.units)
        assert "m1a2" in all_types
        assert "t72m" in all_types

    def test_has_cbrn_config(self):
        cfg = _load_scenario_by_name("korean_peninsula")
        assert cfg.cbrn_config is not None

    def test_has_documented_outcomes(self):
        raw = yaml.safe_load(
            open(_SCENARIOS_DIR / "korean_peninsula" / "scenario.yaml")
        )
        assert len(raw.get("documented_outcomes", [])) >= 2

    def test_duration_96h(self):
        cfg = _load_scenario_by_name("korean_peninsula")
        assert cfg.duration_hours == 96.0


class TestSuwalkiGap:
    """Suwalki Gap NATO vs Russia scenario."""

    def test_loads_and_validates(self):
        cfg = _load_scenario_by_name("suwalki_gap")
        assert "Suwalki Gap" in cfg.name

    def test_era_is_modern(self):
        cfg = _load_scenario_by_name("suwalki_gap")
        assert cfg.era == "modern"

    def test_two_sides(self):
        cfg = _load_scenario_by_name("suwalki_gap")
        assert len(cfg.sides) == 2

    def test_has_nato_units(self):
        cfg = _load_scenario_by_name("suwalki_gap")
        blue = next(s for s in cfg.sides if s.side == "blue")
        blue_types = [u["unit_type"] for u in blue.units]
        assert "leopard2a6" in blue_types
        assert "challenger2" in blue_types

    def test_has_ew_config(self):
        cfg = _load_scenario_by_name("suwalki_gap")
        assert cfg.ew_config is not None

    def test_has_school_config(self):
        cfg = _load_scenario_by_name("suwalki_gap")
        assert cfg.school_config is not None
        assert cfg.school_config["blue_school"] == "maneuverist"
        assert cfg.school_config["red_school"] == "deep_battle"

    def test_has_documented_outcomes(self):
        raw = yaml.safe_load(
            open(_SCENARIOS_DIR / "suwalki_gap" / "scenario.yaml")
        )
        assert len(raw.get("documented_outcomes", [])) >= 2

    def test_duration_120h(self):
        cfg = _load_scenario_by_name("suwalki_gap")
        assert cfg.duration_hours == 120.0


class TestHybridGrayZone:
    """Hybrid Gray Zone escalation campaign scenario."""

    def test_loads_and_validates(self):
        cfg = _load_scenario_by_name("hybrid_gray_zone")
        assert "Hybrid Gray Zone" in cfg.name

    def test_era_is_modern(self):
        cfg = _load_scenario_by_name("hybrid_gray_zone")
        assert cfg.era == "modern"

    def test_two_sides(self):
        cfg = _load_scenario_by_name("hybrid_gray_zone")
        assert len(cfg.sides) == 2

    def test_has_sof_units(self):
        cfg = _load_scenario_by_name("hybrid_gray_zone")
        blue = next(s for s in cfg.sides if s.side == "blue")
        blue_types = [u["unit_type"] for u in blue.units]
        assert "sf_oda" in blue_types
        assert "us_rifle_squad" in blue_types

    def test_has_escalation_config(self):
        cfg = _load_scenario_by_name("hybrid_gray_zone")
        assert cfg.escalation_config is not None

    def test_duration_720h(self):
        cfg = _load_scenario_by_name("hybrid_gray_zone")
        assert cfg.duration_hours == 720.0

    def test_has_documented_outcomes(self):
        raw = yaml.safe_load(
            open(_SCENARIOS_DIR / "hybrid_gray_zone" / "scenario.yaml")
        )
        assert len(raw.get("documented_outcomes", [])) >= 2


# ===========================================================================
# 30b: Historical Scenarios
# ===========================================================================


class TestJutland:
    """Battle of Jutland 1916 — WW1 naval scenario."""

    def test_loads_and_validates(self):
        cfg = _load_era_scenario("ww1", "jutland")
        assert "Jutland" in cfg.name

    def test_era_is_ww1(self):
        cfg = _load_era_scenario("ww1", "jutland")
        assert cfg.era == "ww1"

    def test_two_sides(self):
        cfg = _load_era_scenario("ww1", "jutland")
        assert len(cfg.sides) == 2
        sides = {s.side for s in cfg.sides}
        assert sides == {"british", "german"}

    def test_has_dreadnoughts(self):
        cfg = _load_era_scenario("ww1", "jutland")
        all_types = []
        for side in cfg.sides:
            all_types.extend(u["unit_type"] for u in side.units)
        assert "iron_duke_bb" in all_types
        assert "konig_bb" in all_types

    def test_open_ocean_terrain(self):
        cfg = _load_era_scenario("ww1", "jutland")
        assert cfg.terrain.terrain_type == "open_ocean"

    def test_has_documented_outcomes(self):
        raw = yaml.safe_load(
            open(_ERAS_DIR / "ww1" / "scenarios" / "jutland" / "scenario.yaml")
        )
        assert len(raw.get("documented_outcomes", [])) >= 2


class TestTrafalgar:
    """Battle of Trafalgar 1805 — Napoleonic naval scenario."""

    def test_loads_and_validates(self):
        cfg = _load_era_scenario("napoleonic", "trafalgar")
        assert "Trafalgar" in cfg.name

    def test_era_is_napoleonic(self):
        cfg = _load_era_scenario("napoleonic", "trafalgar")
        assert cfg.era == "napoleonic"

    def test_two_sides(self):
        cfg = _load_era_scenario("napoleonic", "trafalgar")
        assert len(cfg.sides) == 2
        sides = {s.side for s in cfg.sides}
        assert sides == {"british", "franco_spanish"}

    def test_has_ships_of_line(self):
        cfg = _load_era_scenario("napoleonic", "trafalgar")
        all_types = []
        for side in cfg.sides:
            all_types.extend(u["unit_type"] for u in side.units)
        assert "ship_of_line_74" in all_types
        assert "first_rate_100" in all_types

    def test_open_ocean_terrain(self):
        cfg = _load_era_scenario("napoleonic", "trafalgar")
        assert cfg.terrain.terrain_type == "open_ocean"

    def test_has_documented_outcomes(self):
        raw = yaml.safe_load(
            open(
                _ERAS_DIR
                / "napoleonic"
                / "scenarios"
                / "trafalgar"
                / "scenario.yaml"
            )
        )
        assert len(raw.get("documented_outcomes", [])) >= 2


class TestSalamis:
    """Battle of Salamis 480 BC — Ancient naval scenario."""

    def test_loads_and_validates(self):
        cfg = _load_era_scenario("ancient_medieval", "salamis")
        assert "Salamis" in cfg.name

    def test_era_is_ancient_medieval(self):
        cfg = _load_era_scenario("ancient_medieval", "salamis")
        assert cfg.era == "ancient_medieval"

    def test_two_sides(self):
        cfg = _load_era_scenario("ancient_medieval", "salamis")
        assert len(cfg.sides) == 2
        sides = {s.side for s in cfg.sides}
        assert sides == {"greek", "persian"}

    def test_has_triremes(self):
        cfg = _load_era_scenario("ancient_medieval", "salamis")
        all_types = []
        for side in cfg.sides:
            all_types.extend(u["unit_type"] for u in side.units)
        assert "greek_trireme" in all_types

    def test_narrow_terrain(self):
        cfg = _load_era_scenario("ancient_medieval", "salamis")
        assert cfg.terrain.width_m == 8000
        assert cfg.terrain.height_m == 4000

    def test_has_documented_outcomes(self):
        raw = yaml.safe_load(
            open(
                _ERAS_DIR
                / "ancient_medieval"
                / "scenarios"
                / "salamis"
                / "scenario.yaml"
            )
        )
        assert len(raw.get("documented_outcomes", [])) >= 2


class TestStalingrad:
    """Battle of Stalingrad 1942 — WW2 urban combat scenario."""

    def test_loads_and_validates(self):
        cfg = _load_era_scenario("ww2", "stalingrad")
        assert "Stalingrad" in cfg.name

    def test_era_is_ww2(self):
        cfg = _load_era_scenario("ww2", "stalingrad")
        assert cfg.era == "ww2"

    def test_two_sides(self):
        cfg = _load_era_scenario("ww2", "stalingrad")
        assert len(cfg.sides) == 2
        sides = {s.side for s in cfg.sides}
        assert sides == {"soviet", "german"}

    def test_has_infantry_and_armor(self):
        cfg = _load_era_scenario("ww2", "stalingrad")
        all_types = []
        for side in cfg.sides:
            all_types.extend(u["unit_type"] for u in side.units)
        assert "soviet_rifle_squad" in all_types
        assert "wehrmacht_rifle_squad" in all_types
        assert "t34_85" in all_types

    def test_urban_terrain(self):
        cfg = _load_era_scenario("ww2", "stalingrad")
        assert cfg.terrain.width_m == 5000
        assert cfg.terrain.height_m == 3000
        assert cfg.terrain.cell_size_m == 50.0

    def test_duration_168h(self):
        cfg = _load_era_scenario("ww2", "stalingrad")
        assert cfg.duration_hours == 168.0

    def test_has_documented_outcomes(self):
        raw = yaml.safe_load(
            open(
                _ERAS_DIR
                / "ww2"
                / "scenarios"
                / "stalingrad"
                / "scenario.yaml"
            )
        )
        assert len(raw.get("documented_outcomes", [])) >= 2


# ===========================================================================
# 30c: Existing Scenario Fixes + New Falklands
# ===========================================================================


class Test73EastingFix:
    """73 Easting scenario calibration fix (deficit 2.20)."""

    def _load_raw(self):
        with open(_SCENARIOS_DIR / "73_easting" / "scenario.yaml") as f:
            return yaml.safe_load(f)

    def test_visibility_increased(self):
        raw = self._load_raw()
        assert raw["weather_conditions"]["visibility_m"] == 800

    def test_red_engagement_range_increased(self):
        raw = self._load_raw()
        assert raw["behavior_rules"]["red"]["engagement_range_m"] == 1500

    def test_thermal_contrast_reduced(self):
        raw = self._load_raw()
        assert raw["calibration_overrides"]["thermal_contrast"] == 1.5

    def test_has_bmp2_in_red(self):
        raw = self._load_raw()
        red_types = [u["unit_type"] for u in raw["red_forces"]["units"]]
        assert "bmp2" in red_types

    def test_red_forces_expanded(self):
        raw = self._load_raw()
        total = sum(u["count"] for u in raw["red_forces"]["units"])
        assert total == 50  # 30 T-72M + 16 BMP-1 + 4 BMP-2


class TestFalklandsSanCarlos:
    """Falklands San Carlos Air Raids scenario (deficit 4.4)."""

    def test_loads_and_validates(self):
        cfg = _load_scenario_by_name("falklands_san_carlos")
        assert "San Carlos" in cfg.name

    def test_two_sides(self):
        cfg = _load_scenario_by_name("falklands_san_carlos")
        assert len(cfg.sides) == 2

    def test_has_destroyers_and_frigates(self):
        cfg = _load_scenario_by_name("falklands_san_carlos")
        blue = next(s for s in cfg.sides if s.side == "blue")
        blue_types = [u["unit_type"] for u in blue.units]
        assert "type42_destroyer" in blue_types
        assert "type22_frigate" in blue_types

    def test_open_ocean_terrain(self):
        cfg = _load_scenario_by_name("falklands_san_carlos")
        assert cfg.terrain.terrain_type == "open_ocean"

    def test_has_documented_outcomes(self):
        raw = yaml.safe_load(
            open(_SCENARIOS_DIR / "falklands_san_carlos" / "scenario.yaml")
        )
        assert len(raw.get("documented_outcomes", [])) >= 2


class TestFalklandsGooseGreen:
    """Falklands Goose Green ground engagement scenario."""

    def test_loads_and_validates(self):
        cfg = _load_scenario_by_name("falklands_goose_green")
        assert "Goose Green" in cfg.name

    def test_two_sides(self):
        cfg = _load_scenario_by_name("falklands_goose_green")
        assert len(cfg.sides) == 2

    def test_ground_units(self):
        cfg = _load_scenario_by_name("falklands_goose_green")
        all_types = []
        for side in cfg.sides:
            all_types.extend(u["unit_type"] for u in side.units)
        assert "us_rifle_squad" in all_types

    def test_hilly_defense_terrain(self):
        cfg = _load_scenario_by_name("falklands_goose_green")
        assert cfg.terrain.terrain_type == "hilly_defense"

    def test_duration_18h(self):
        cfg = _load_scenario_by_name("falklands_goose_green")
        assert cfg.duration_hours == 18.0


class TestMidwayFix:
    """Midway scenario fix — carrier units replace fletcher_dd proxy."""

    def test_loads_and_validates(self):
        cfg = _load_era_scenario("ww2", "midway")
        assert "Midway" in cfg.name

    def test_era_is_ww2(self):
        cfg = _load_era_scenario("ww2", "midway")
        assert cfg.era == "ww2"

    def test_usn_has_essex_cv(self):
        cfg = _load_era_scenario("ww2", "midway")
        usn = next(s for s in cfg.sides if s.side == "usn")
        usn_types = [u["unit_type"] for u in usn.units]
        assert "essex_cv" in usn_types

    def test_ijn_has_shokaku_cv(self):
        cfg = _load_era_scenario("ww2", "midway")
        ijn = next(s for s in cfg.sides if s.side == "ijn")
        ijn_types = [u["unit_type"] for u in ijn.units]
        assert "shokaku_cv" in ijn_types

    def test_ijn_has_a6m_zero(self):
        cfg = _load_era_scenario("ww2", "midway")
        ijn = next(s for s in cfg.sides if s.side == "ijn")
        ijn_types = [u["unit_type"] for u in ijn.units]
        assert "a6m_zero" in ijn_types


class TestGolanExpansion:
    """Golan Campaign expansion — BMP-2 added to red forces."""

    def test_loads_and_validates(self):
        cfg = _load_scenario_by_name("golan_campaign")
        assert "Golan" in cfg.name

    def test_has_bmp1_in_red(self):
        cfg = _load_scenario_by_name("golan_campaign")
        red = next(s for s in cfg.sides if s.side == "red")
        red_types = [u["unit_type"] for u in red.units]
        assert "bmp1" in red_types

    def test_red_forces_expanded(self):
        cfg = _load_scenario_by_name("golan_campaign")
        red = next(s for s in cfg.sides if s.side == "red")
        total = sum(u.get("count", 1) for u in red.units)
        assert total >= 100  # 40+40+20 (recalibrated for Phase 47)


# ===========================================================================
# 30d: Cross-Scenario Validation
# ===========================================================================


def _collect_all_scenario_paths() -> list[Path]:
    """Collect all scenario.yaml paths across both modern and era directories."""
    paths = []
    # Modern scenarios
    for d in sorted(_SCENARIOS_DIR.iterdir()):
        p = d / "scenario.yaml"
        if p.exists():
            paths.append(p)
    # Era scenarios
    for era_dir in sorted(_ERAS_DIR.iterdir()):
        scenarios_dir = era_dir / "scenarios"
        if scenarios_dir.exists():
            for d in sorted(scenarios_dir.iterdir()):
                p = d / "scenario.yaml"
                if p.exists():
                    paths.append(p)
    return paths


_ALL_SCENARIO_PATHS = _collect_all_scenario_paths()
_ALL_SCENARIO_IDS = [
    str(p.parent.relative_to(_DATA_DIR)) for p in _ALL_SCENARIO_PATHS
]


class TestAllScenariosLoad:
    """Every scenario YAML in the project validates against CampaignScenarioConfig."""

    @pytest.mark.parametrize("path", _ALL_SCENARIO_PATHS, ids=_ALL_SCENARIO_IDS)
    def test_scenario_validates(self, path: Path):
        with open(path) as f:
            raw = yaml.safe_load(f)
        # Some legacy scenarios use blue_forces/red_forces or other formats
        if "sides" in raw and "date" in raw and "duration_hours" in raw:
            cfg = CampaignScenarioConfig.model_validate(raw)
            assert cfg.name
            assert len(cfg.sides) >= 2
        else:
            # Legacy engagement or domain-specific format — verify valid YAML
            assert "name" in raw


_MODERN_CAMPAIGN_PATHS = [
    _SCENARIOS_DIR / name / "scenario.yaml"
    for name in [
        "taiwan_strait",
        "korean_peninsula",
        "suwalki_gap",
        "hybrid_gray_zone",
        "falklands_san_carlos",
        "falklands_goose_green",
        "falklands_campaign",
        "golan_campaign",
    ]
]


class TestModernScenariosHaveDocumentedOutcomes:
    """Modern campaign scenarios should have documented_outcomes."""

    @pytest.mark.parametrize(
        "path",
        _MODERN_CAMPAIGN_PATHS,
        ids=[p.parent.name for p in _MODERN_CAMPAIGN_PATHS],
    )
    def test_has_documented_outcomes(self, path: Path):
        with open(path) as f:
            raw = yaml.safe_load(f)
        assert len(raw.get("documented_outcomes", [])) >= 1


_ERA_SCENARIO_PATHS = []
for _era in ["ww2", "ww1", "napoleonic", "ancient_medieval"]:
    _era_dir = _ERAS_DIR / _era / "scenarios"
    if _era_dir.exists():
        for _d in sorted(_era_dir.iterdir()):
            _p = _d / "scenario.yaml"
            if _p.exists():
                _ERA_SCENARIO_PATHS.append(_p)


class TestHistoricalScenariosHaveEra:
    """Era scenario YAMLs should have non-modern era field."""

    @pytest.mark.parametrize(
        "path",
        _ERA_SCENARIO_PATHS,
        ids=[str(p.parent.relative_to(_ERAS_DIR)) for p in _ERA_SCENARIO_PATHS],
    )
    def test_era_not_modern(self, path: Path):
        with open(path) as f:
            raw = yaml.safe_load(f)
        assert raw.get("era", "modern") != "modern"


_EW_SCENARIO_NAMES = ["bekaa_valley_1982", "taiwan_strait", "suwalki_gap"]


class TestEWScenariosHaveEWConfig:
    """Scenarios known to exercise EW should have ew_config."""

    @pytest.mark.parametrize("name", _EW_SCENARIO_NAMES)
    def test_ew_config_present(self, name: str):
        with open(_SCENARIOS_DIR / name / "scenario.yaml") as f:
            raw = yaml.safe_load(f)
        assert raw.get("ew_config") is not None


_ESCALATION_SCENARIO_NAMES = [
    "halabja_1988",
    "eastern_front_1943",
    "hybrid_gray_zone",
    "coin_campaign",
    "taiwan_strait",
]


class TestEscalationScenariosHaveConfig:
    """Scenarios known to exercise escalation should have escalation_config."""

    @pytest.mark.parametrize("name", _ESCALATION_SCENARIO_NAMES)
    def test_escalation_config_present(self, name: str):
        with open(_SCENARIOS_DIR / name / "scenario.yaml") as f:
            raw = yaml.safe_load(f)
        assert raw.get("escalation_config") is not None


_NAVAL_SCENARIO_PATHS = [
    _SCENARIOS_DIR / "falklands_san_carlos" / "scenario.yaml",
    _SCENARIOS_DIR / "falklands_campaign" / "scenario.yaml",
    _SCENARIOS_DIR / "falklands_naval" / "scenario.yaml",
    _SCENARIOS_DIR / "taiwan_strait" / "scenario.yaml",
    _ERAS_DIR / "ww2" / "scenarios" / "midway" / "scenario.yaml",
    _ERAS_DIR / "ww1" / "scenarios" / "jutland" / "scenario.yaml",
    _ERAS_DIR / "napoleonic" / "scenarios" / "trafalgar" / "scenario.yaml",
    _ERAS_DIR / "ancient_medieval" / "scenarios" / "salamis" / "scenario.yaml",
]


class TestNavalScenariosHaveOceanTerrain:
    """Naval scenarios should use open_ocean terrain."""

    @pytest.mark.parametrize(
        "path",
        _NAVAL_SCENARIO_PATHS,
        ids=[str(p.parent.name) for p in _NAVAL_SCENARIO_PATHS],
    )
    def test_open_ocean(self, path: Path):
        with open(path) as f:
            raw = yaml.safe_load(f)
        assert raw.get("terrain", {}).get("terrain_type") == "open_ocean"


class TestDocumentedOutcomesFormat:
    """Documented outcomes should have required fields: name, value."""

    @pytest.mark.parametrize("path", _ALL_SCENARIO_PATHS, ids=_ALL_SCENARIO_IDS)
    def test_outcomes_have_name_and_value(self, path: Path):
        with open(path) as f:
            raw = yaml.safe_load(f)
        outcomes = raw.get("documented_outcomes", [])
        if not isinstance(outcomes, list):
            pytest.skip("documented_outcomes is not a list (domain-specific format)")
        for outcome in outcomes:
            if not isinstance(outcome, dict):
                continue
            assert "name" in outcome, f"outcome missing 'name' in {path}"
            assert "value" in outcome, f"outcome missing 'value' in {path}"


# ---------------------------------------------------------------------------
# Full-stack scenario loading validation
# ---------------------------------------------------------------------------

def _scenario_has_campaign_schema(path: Path) -> bool:
    """Check if scenario YAML has the required campaign schema fields."""
    with open(path) as f:
        raw = yaml.safe_load(f)
    return all(k in raw for k in ("sides", "date", "duration_hours", "terrain"))


# Scenarios that can load through ScenarioLoader (have sides + terrain + date)
_LOADABLE_SCENARIO_PATHS = [
    p for p in _ALL_SCENARIO_PATHS
    if _scenario_has_campaign_schema(p)
]
_LOADABLE_SCENARIO_IDS = [
    str(p.parent.relative_to(_DATA_DIR)) for p in _LOADABLE_SCENARIO_PATHS
]


class TestScenarioFullLoad:
    """Every loadable scenario produces units with weapons and sensors.

    Catches data-schema drift: crew role mismatches, weapon_assignment
    name mismatches, missing sensor name mappings, missing era data, etc.
    """

    @pytest.mark.parametrize(
        "path", _LOADABLE_SCENARIO_PATHS, ids=_LOADABLE_SCENARIO_IDS,
    )
    def test_scenario_loads_with_armed_units(self, path: Path):
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader(_DATA_DIR)
        ctx = loader.load(path, seed=42)

        # Every side must have at least one unit
        for side, units in ctx.units_by_side.items():
            assert len(units) > 0, (
                f"Side {side!r} has 0 units in {path} — "
                "check unit_type names match era YAML definitions "
                "and crew roles are valid CrewRole enum values"
            )

        # At least one unit across all sides must have weapons
        all_weapon_counts = [
            len(ctx.unit_weapons.get(u.entity_id, []))
            for units in ctx.units_by_side.values()
            for u in units
        ]
        assert sum(all_weapon_counts) > 0, (
            f"No units have weapons in {path} — "
            "check weapon_assignments keys match equipment names exactly "
            "and weapon YAML IDs exist in the era data"
        )

        # At least one unit across all sides must have sensors
        all_sensor_counts = [
            len(ctx.unit_sensors.get(u.entity_id, []))
            for units in ctx.units_by_side.values()
            for u in units
        ]
        assert sum(all_sensor_counts) > 0, (
            f"No units have sensors in {path} — "
            "check _SENSOR_NAME_MAP in scenario_runner.py covers "
            "all SENSOR equipment names used in unit YAML"
        )
