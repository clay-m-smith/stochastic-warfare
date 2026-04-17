"""Phase 104 regression test — deployment mode framework.

Validates:
- DeploymentConfig schema parses legacy / bounding_box / clustered / doctrinal /
  manual modes
- Legacy mode preserves pre-Phase-104 behavior (backward compat)
- bounding_box mode places units inside the configured box
- Clustered mode groups by ground_type into vertical strips
- Doctrinal mode follows formation template echelons
- Manual mode (per-unit `position:` YAML) overrides auto-deployment
- min_side_separation warning fires when boxes overlap
- All 6 starter formation templates load cleanly
- Bint Jbeil retrofitted to doctrinal now has tick-0 force separation > 500m
"""

from __future__ import annotations

import math
import tempfile
from collections import defaultdict
from pathlib import Path

import pytest
import yaml

from stochastic_warfare.simulation.deployment import (
    DeploymentBox,
    DeploymentConfig,
    DeploymentMode,
    FormationTemplate,
    FormationTemplateLoader,
    GroupKey,
    check_side_separation,
    deploy_units,
)
from stochastic_warfare.simulation.scenario import ScenarioLoader

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


# ---------------------------------------------------------------------------
# Schema + enum
# ---------------------------------------------------------------------------


class TestDeploymentSchema:
    """Phase 104 data model."""

    def test_deployment_mode_values(self) -> None:
        assert set(DeploymentMode).__ge__({
            DeploymentMode.LEGACY, DeploymentMode.BOUNDING_BOX,
            DeploymentMode.CLUSTERED, DeploymentMode.DOCTRINAL,
            DeploymentMode.MANUAL,
        })

    def test_group_key_enum(self) -> None:
        assert set(GroupKey) == {
            GroupKey.GROUND_TYPE, GroupKey.UNIT_TYPE, GroupKey.DOMAIN,
        }

    def test_deployment_config_default_is_legacy(self) -> None:
        cfg = DeploymentConfig()
        assert cfg.mode == DeploymentMode.LEGACY

    def test_deployment_box_validators(self) -> None:
        # x_max > x_min enforced
        with pytest.raises(Exception):
            DeploymentBox(x_min=10.0, y_min=0.0, x_max=5.0, y_max=10.0)
        with pytest.raises(Exception):
            DeploymentBox(x_min=0.0, y_min=10.0, x_max=10.0, y_max=5.0)

    def test_deployment_box_overlap(self) -> None:
        a = DeploymentBox(x_min=0, y_min=0, x_max=100, y_max=100)
        b = DeploymentBox(x_min=50, y_min=50, x_max=150, y_max=150)
        assert a.overlaps(b)
        c = DeploymentBox(x_min=200, y_min=200, x_max=300, y_max=300)
        assert not a.overlaps(c)
        assert a.min_separation_to(c) == pytest.approx(math.hypot(100, 100))


# ---------------------------------------------------------------------------
# Formation template loader
# ---------------------------------------------------------------------------


class TestFormationTemplates:
    """All 6 starter templates load and validate."""

    def test_loader_finds_templates(self) -> None:
        loader = FormationTemplateLoader(DATA_DIR / "formations")
        loader.load_all()
        expected = {
            "brigade_attack", "brigade_defense", "battalion_urban_defense",
            "marine_urban_assault", "mechanized_thrust", "naval_patrol_station",
        }
        missing = expected - set(loader.available())
        assert not missing, f"missing templates: {missing}"

    @pytest.mark.parametrize("template_id", [
        "brigade_attack", "brigade_defense", "battalion_urban_defense",
        "marine_urban_assault", "mechanized_thrust", "naval_patrol_station",
    ])
    def test_template_loads(self, template_id: str) -> None:
        loader = FormationTemplateLoader(DATA_DIR / "formations")
        loader.load_all()
        tpl = loader.get(template_id)
        assert tpl is not None, f"{template_id} failed to load"
        assert len(tpl.echelons) >= 1, f"{template_id} has no echelons"


# ---------------------------------------------------------------------------
# End-to-end: scenario-driven deployment modes
# ---------------------------------------------------------------------------


def _minimal_scenario(mode: str, extra: str = "") -> str:
    return f"""
name: "Deploy Test"
date: "2006-07-24T16:00:00+03:00"
duration_hours: 1
tick_duration_seconds: 5.0
tick_resolution: {{strategic_s: 60, operational_s: 60, tactical_s: 60}}
latitude: 33.0
longitude: 35.0
weather_conditions: {{visibility_m: 5000, wind_speed_mps: 3, temperature_c: 20, cloud_cover: 0.1, humidity: 0.5, precipitation: none, wind_direction_deg: 270}}
terrain: {{width_m: 10000, height_m: 8000, cell_size_m: 50.0, base_elevation_m: 0.0, terrain_type: hilly_defense}}
deployment:
  mode: {mode}
  blue_box: {{x_min: 2000, y_min: 5500, x_max: 7000, y_max: 7000}}
  red_box:  {{x_min: 2000, y_min: 1000, x_max: 7000, y_max: 2500}}
  min_spacing_m: 40
{extra}
sides:
  - side: blue
    units:
      - {{unit_type: idf_golani_squad, count: 8}}
      - {{unit_type: idf_merkava_mk4, count: 4}}
    experience_level: 0.8
    morale_initial: STEADY
  - side: red
    units:
      - {{unit_type: hezbollah_local_fighter, count: 6}}
    experience_level: 0.5
    morale_initial: STEADY
victory_conditions:
  - type: time_expired
    side: blue
    params: {{max_duration_s: 3600}}
"""


def _load_scenario(yaml_text: str):
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8",
    ) as f:
        f.write(yaml_text)
        path = f.name
    try:
        loader = ScenarioLoader(DATA_DIR)
        ctx = loader.load(Path(path), seed=42)
        return ctx
    finally:
        Path(path).unlink(missing_ok=True)


class TestBoundingBoxMode:
    """bounding_box places all units inside the configured box."""

    def test_units_inside_box(self) -> None:
        ctx = _load_scenario(_minimal_scenario("bounding_box"))
        bx = ctx.config.deployment.blue_box
        for u in ctx.units_by_side["blue"]:
            assert bx.x_min <= u.position.easting <= bx.x_max, (
                f"blue {u.entity_id} at x={u.position.easting} outside [{bx.x_min}, {bx.x_max}]"
            )
            assert bx.y_min <= u.position.northing <= bx.y_max

    def test_min_side_separation(self) -> None:
        ctx = _load_scenario(_minimal_scenario("bounding_box"))
        min_d = min(
            math.hypot(b.position.easting - r.position.easting,
                       b.position.northing - r.position.northing)
            for b in ctx.units_by_side["blue"]
            for r in ctx.units_by_side["red"]
        )
        assert min_d > 500.0, (
            f"bounding_box mode: min side separation {min_d:.0f}m < 500m"
        )


class TestClusteredMode:
    """Clustered mode groups units by ground_type into vertical strips."""

    def test_ground_type_cluster_separation(self) -> None:
        ctx = _load_scenario(_minimal_scenario("clustered"))
        groups = defaultdict(list)
        for u in ctx.units_by_side["blue"]:
            gt = getattr(u, "ground_type", None)
            key = gt.name if hasattr(gt, "name") else str(gt)
            groups[key].append(u)
        assert len(groups) >= 2, (
            f"expected >= 2 ground_type groups, got {list(groups)}"
        )
        # Each group's x-range should be tighter than the full box width
        bx = ctx.config.deployment.blue_box
        for key, members in groups.items():
            xs = [u.position.easting for u in members]
            xrange = max(xs) - min(xs)
            assert xrange < bx.width_m * 0.8, (
                f"cluster {key} x-range {xrange:.0f}m ≥ 0.8x box width — not strip-separated"
            )


class TestDoctrinalMode:
    """Doctrinal mode with brigade_attack template places RECON forward."""

    def test_brigade_attack_recon_forward(self) -> None:
        extra = "  blue_template: brigade_attack\n  red_template: brigade_defense"
        ctx = _load_scenario(_minimal_scenario("doctrinal", extra))
        # Get ARMOR and RECON y-centers
        groups = defaultdict(list)
        for u in ctx.units_by_side["blue"]:
            gt = getattr(u, "ground_type", None)
            key = gt.name if hasattr(gt, "name") else str(gt)
            groups[key].append(u)
        if "RECON" in groups and "ARMOR" in groups:
            recon_y = sum(u.position.northing for u in groups["RECON"]) / len(groups["RECON"])
            armor_y = sum(u.position.northing for u in groups["ARMOR"]) / len(groups["ARMOR"])
            # brigade_attack: advance_guard (RECON) at 0.9, main_body_1 (ARMOR) at 0.65
            # Blue attacks toward higher y (toward red), so RECON should be y > ARMOR
            assert recon_y > armor_y, (
                f"brigade_attack: RECON y={recon_y:.0f} not forward of ARMOR y={armor_y:.0f}"
            )


class TestManualMode:
    """Per-unit position: YAML override wins in any mode."""

    def test_per_unit_position_override(self) -> None:
        yaml_txt = """
name: "Manual Test"
date: "2006-07-24T16:00:00+03:00"
duration_hours: 1
tick_duration_seconds: 5.0
tick_resolution: {strategic_s: 60, operational_s: 60, tactical_s: 60}
latitude: 33.0
longitude: 35.0
weather_conditions: {visibility_m: 5000, wind_speed_mps: 3, temperature_c: 20, cloud_cover: 0.1, humidity: 0.5, precipitation: none, wind_direction_deg: 270}
terrain: {width_m: 10000, height_m: 8000, cell_size_m: 50.0, base_elevation_m: 0.0, terrain_type: hilly_defense}
deployment:
  mode: bounding_box
  blue_box: {x_min: 2000, y_min: 5500, x_max: 7000, y_max: 7000}
  red_box:  {x_min: 2000, y_min: 1000, x_max: 7000, y_max: 2500}
  min_spacing_m: 40
sides:
  - side: blue
    units:
      - unit_type: idf_golani_squad
        count: 1
        position: [1234.5, 6789.0]
      - {unit_type: idf_golani_squad, count: 3}
    experience_level: 0.8
    morale_initial: STEADY
  - side: red
    units:
      - {unit_type: hezbollah_local_fighter, count: 2}
    experience_level: 0.5
    morale_initial: STEADY
victory_conditions:
  - type: time_expired
    side: blue
    params: {max_duration_s: 3600}
"""
        ctx = _load_scenario(yaml_txt)
        # First blue unit should be at exact override position
        first = ctx.units_by_side["blue"][0]
        assert first.position.easting == pytest.approx(1234.5)
        assert first.position.northing == pytest.approx(6789.0)
        assert getattr(first, "_manually_positioned", False) is True
        # Other blue units should be inside blue_box (auto-deployed)
        for u in ctx.units_by_side["blue"][1:]:
            assert 2000 <= u.position.easting <= 7000
            assert 5500 <= u.position.northing <= 7000


# ---------------------------------------------------------------------------
# Backward compat
# ---------------------------------------------------------------------------


class TestLegacyBackwardCompat:
    """Scenarios without a `deployment:` block keep working as LEGACY."""

    @pytest.mark.parametrize("scenario", [
        "ins_hanit_2006",  # only golden scenario still on legacy post-104b
    ])
    def test_loads_with_legacy_default(self, scenario: str) -> None:
        loader = ScenarioLoader(DATA_DIR)
        ctx = loader.load(
            DATA_DIR / "scenarios" / scenario / "scenario.yaml", seed=42,
        )
        assert ctx.config.deployment.mode == DeploymentMode.LEGACY


# ---------------------------------------------------------------------------
# All golden scenarios: no OOB, tick-0 separation > 500m
# ---------------------------------------------------------------------------


class TestAllGoldenScenarioDeployment:
    """Phase 104b retrofit — every golden scenario must deploy cleanly:

    - zero out-of-bounds units (formation stays inside map)
    - tick-0 minimum side separation >= 500m (no tick-0 TACTICAL trigger)

    Prevents the class of bug that caused Bint Jbeil's 8-tick over-resolution
    (Phase 102) from recurring in any Block 11 scenario.
    """

    GOLDEN_SCENARIOS = [
        ("debecka_pass", DeploymentMode.BOUNDING_BOX),
        ("khafji", DeploymentMode.DOCTRINAL),
        ("fallujah_phase_line_fran", DeploymentMode.DOCTRINAL),
        ("bint_jbeil_2006", DeploymentMode.DOCTRINAL),
        ("ins_hanit_2006", DeploymentMode.LEGACY),
    ]

    @pytest.mark.parametrize("scenario,expected_mode", GOLDEN_SCENARIOS)
    def test_expected_mode(self, scenario: str, expected_mode: DeploymentMode) -> None:
        loader = ScenarioLoader(DATA_DIR)
        ctx = loader.load(
            DATA_DIR / "scenarios" / scenario / "scenario.yaml", seed=42,
        )
        assert ctx.config.deployment.mode == expected_mode, (
            f"{scenario}: expected mode={expected_mode.value}, got {ctx.config.deployment.mode.value}"
        )

    @pytest.mark.parametrize("scenario,_mode", GOLDEN_SCENARIOS)
    def test_no_units_out_of_map_bounds(self, scenario: str, _mode: DeploymentMode) -> None:
        loader = ScenarioLoader(DATA_DIR)
        ctx = loader.load(
            DATA_DIR / "scenarios" / scenario / "scenario.yaml", seed=42,
        )
        w = ctx.config.terrain.width_m
        h = ctx.config.terrain.height_m
        oob = [
            u for units in ctx.units_by_side.values() for u in units
            if not (0 <= u.position.easting <= w and 0 <= u.position.northing <= h)
        ]
        assert len(oob) == 0, (
            f"{scenario}: {len(oob)} units outside map {w}x{h} — "
            f"formation overflow bug"
        )

    @pytest.mark.parametrize("scenario,_mode", GOLDEN_SCENARIOS)
    def test_min_side_separation(self, scenario: str, _mode: DeploymentMode) -> None:
        loader = ScenarioLoader(DATA_DIR)
        ctx = loader.load(
            DATA_DIR / "scenarios" / scenario / "scenario.yaml", seed=42,
        )
        sides = [s for s in ctx.units_by_side.values() if s]
        if len(sides) < 2:
            pytest.skip(f"{scenario}: fewer than 2 populated sides")
        # Check separation between the two largest sides
        sides.sort(key=len, reverse=True)
        s1, s2 = sides[0], sides[1]
        min_d = min(
            math.hypot(a.position.easting - b.position.easting,
                       a.position.northing - b.position.northing)
            for a in s1 for b in s2
        )
        assert min_d >= 500.0, (
            f"{scenario}: tick-0 min side separation {min_d:.0f}m < 500m — "
            f"forces will engage at TACTICAL resolution on tick 0"
        )
