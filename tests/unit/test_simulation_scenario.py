"""Tests for simulation scenario configuration and loading.

Uses shared fixtures from conftest.py: rng, event_bus, sim_clock, rng_manager.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.simulation.scenario import (
    CampaignScenarioConfig,
    DepotConfig,
    ObjectiveConfig,
    ReinforcementConfig,
    ReinforcementUnitConfig,
    ScenarioLoader,
    SideConfig,
    SimulationContext,
    TerrainConfig,
    TickResolutionConfig,
    VictoryConditionConfig,
    _parse_start_time,
)
from stochastic_warfare.terrain.heightmap import Heightmap, HeightmapConfig

from tests.conftest import DEFAULT_SEED, POS_ORIGIN, TS, make_rng


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DATA_DIR = Path("data")

_MINIMAL_TERRAIN = {"width_m": 1000, "height_m": 1000}

_MINIMAL_SIDES = [
    {"side": "blue", "units": [{"unit_type": "m1a2", "count": 1}]},
    {"side": "red", "units": [{"unit_type": "m1a2", "count": 1}]},
]


def _minimal_config(**overrides: Any) -> dict[str, Any]:
    """Return a minimal valid campaign config dict."""
    base: dict[str, Any] = {
        "name": "Test",
        "date": "2024-06-15T12:00:00Z",
        "duration_hours": 24,
        "terrain": _MINIMAL_TERRAIN,
        "sides": _MINIMAL_SIDES,
    }
    base.update(overrides)
    return base


def _make_ctx(**overrides: Any) -> SimulationContext:
    """Create a minimal SimulationContext for testing."""
    config = CampaignScenarioConfig.model_validate(_minimal_config())
    clock = SimulationClock(start=TS, tick_duration=timedelta(seconds=10))
    rng_mgr = RNGManager(DEFAULT_SEED)
    bus = EventBus()
    defaults: dict[str, Any] = {
        "config": config,
        "clock": clock,
        "rng_manager": rng_mgr,
        "event_bus": bus,
    }
    defaults.update(overrides)
    return SimulationContext(**defaults)


# ---------------------------------------------------------------------------
# Config model: DepotConfig
# ---------------------------------------------------------------------------


class TestDepotConfig:
    """Depot configuration validation."""

    def test_valid_depot(self) -> None:
        d = DepotConfig(depot_id="fob1", position=[100.0, 200.0])
        assert d.depot_id == "fob1"
        assert d.capacity_tons == 1000.0

    def test_defaults(self) -> None:
        d = DepotConfig(depot_id="d1", position=[0.0, 0.0])
        assert d.throughput_tons_per_hour == 50.0

    def test_custom_capacity(self) -> None:
        d = DepotConfig(depot_id="d1", position=[0, 0], capacity_tons=500)
        assert d.capacity_tons == 500.0

    def test_short_position_rejected(self) -> None:
        with pytest.raises(ValueError, match="at least"):
            DepotConfig(depot_id="d1", position=[100.0])


# ---------------------------------------------------------------------------
# Config model: ReinforcementConfig
# ---------------------------------------------------------------------------


class TestReinforcementConfig:
    """Reinforcement schedule validation."""

    def test_valid_reinforcement(self) -> None:
        r = ReinforcementConfig(
            side="blue",
            arrival_time_s=3600,
            units=[ReinforcementUnitConfig(unit_type="m1a2", count=2)],
        )
        assert r.side == "blue"
        assert r.arrival_time_s == 3600.0
        assert len(r.units) == 1

    def test_default_position(self) -> None:
        r = ReinforcementConfig(
            side="red",
            arrival_time_s=0,
            units=[ReinforcementUnitConfig(unit_type="t72m")],
        )
        assert r.position == [0.0, 0.0]

    def test_negative_time_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            ReinforcementConfig(
                side="blue",
                arrival_time_s=-100,
                units=[ReinforcementUnitConfig(unit_type="m1a2")],
            )

    def test_unit_defaults(self) -> None:
        u = ReinforcementUnitConfig(unit_type="m1a2")
        assert u.count == 1
        assert u.overrides == {}


# ---------------------------------------------------------------------------
# Config model: ObjectiveConfig
# ---------------------------------------------------------------------------


class TestObjectiveConfig:
    """Objective configuration validation."""

    def test_valid_objective(self) -> None:
        o = ObjectiveConfig(
            objective_id="obj1",
            position=[5000, 5000],
            radius_m=500,
            type="territory",
        )
        assert o.objective_id == "obj1"

    def test_defaults(self) -> None:
        o = ObjectiveConfig(objective_id="o1", position=[0, 0])
        assert o.radius_m == 500.0
        assert o.type == "territory"

    def test_invalid_type_rejected(self) -> None:
        with pytest.raises(ValueError, match="objective type"):
            ObjectiveConfig(objective_id="o1", position=[0, 0], type="invalid")

    def test_zero_radius_rejected(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            ObjectiveConfig(objective_id="o1", position=[0, 0], radius_m=0.0)

    def test_key_terrain_type(self) -> None:
        o = ObjectiveConfig(objective_id="o1", position=[0, 0], type="key_terrain")
        assert o.type == "key_terrain"

    def test_infrastructure_type(self) -> None:
        o = ObjectiveConfig(objective_id="o1", position=[0, 0], type="infrastructure")
        assert o.type == "infrastructure"


# ---------------------------------------------------------------------------
# Config model: VictoryConditionConfig
# ---------------------------------------------------------------------------


class TestVictoryConditionConfig:
    """Victory condition validation."""

    def test_valid_territory_control(self) -> None:
        vc = VictoryConditionConfig(
            type="territory_control",
            side="blue",
            params={"objective_ids": ["obj1"], "threshold": 1.0},
        )
        assert vc.type == "territory_control"
        assert vc.side == "blue"

    def test_valid_force_destroyed(self) -> None:
        vc = VictoryConditionConfig(type="force_destroyed", params={"threshold": 0.7})
        assert vc.type == "force_destroyed"

    def test_valid_time_expired(self) -> None:
        vc = VictoryConditionConfig(type="time_expired")
        assert vc.params == {}

    def test_invalid_type_rejected(self) -> None:
        with pytest.raises(ValueError, match="victory condition type"):
            VictoryConditionConfig(type="unknown_condition")

    def test_morale_collapsed(self) -> None:
        vc = VictoryConditionConfig(type="morale_collapsed", side="red")
        assert vc.type == "morale_collapsed"

    def test_supply_exhausted(self) -> None:
        vc = VictoryConditionConfig(type="supply_exhausted")
        assert vc.type == "supply_exhausted"


# ---------------------------------------------------------------------------
# Config model: SideConfig
# ---------------------------------------------------------------------------


class TestSideConfig:
    """Side configuration validation."""

    def test_valid_side(self) -> None:
        s = SideConfig(
            side="blue",
            units=[{"unit_type": "m1a2", "count": 4}],
            experience_level=0.8,
        )
        assert s.side == "blue"
        assert s.experience_level == 0.8

    def test_defaults(self) -> None:
        s = SideConfig(side="red", units=[{"unit_type": "t72m"}])
        assert s.experience_level == 0.5
        assert s.morale_initial == "STEADY"
        assert s.commander_profile == ""
        assert s.doctrine_template == ""
        assert s.depots == []

    def test_experience_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="experience_level"):
            SideConfig(side="blue", units=[], experience_level=1.5)

    def test_negative_experience_rejected(self) -> None:
        with pytest.raises(ValueError, match="experience_level"):
            SideConfig(side="blue", units=[], experience_level=-0.1)

    def test_with_depots(self) -> None:
        s = SideConfig(
            side="blue",
            units=[{"unit_type": "m1a2"}],
            depots=[DepotConfig(depot_id="d1", position=[100, 200])],
        )
        assert len(s.depots) == 1

    def test_commander_and_doctrine(self) -> None:
        s = SideConfig(
            side="blue",
            units=[{"unit_type": "m1a2"}],
            commander_profile="aggressive_armor",
            doctrine_template="us_combined_arms",
        )
        assert s.commander_profile == "aggressive_armor"
        assert s.doctrine_template == "us_combined_arms"

    def test_units_with_overrides(self) -> None:
        s = SideConfig(
            side="blue",
            units=[{"unit_type": "m1a2", "count": 2, "overrides": {"speed": 15.0}}],
        )
        assert s.units[0]["overrides"]["speed"] == 15.0

    def test_custom_morale(self) -> None:
        s = SideConfig(side="blue", units=[], morale_initial="SHAKEN")
        assert s.morale_initial == "SHAKEN"


# ---------------------------------------------------------------------------
# Config model: TickResolutionConfig
# ---------------------------------------------------------------------------


class TestTickResolutionConfig:
    """Tick resolution defaults and overrides."""

    def test_defaults(self) -> None:
        t = TickResolutionConfig()
        assert t.strategic_s == 3600.0
        assert t.operational_s == 300.0
        assert t.tactical_s == 5.0

    def test_custom_values(self) -> None:
        t = TickResolutionConfig(strategic_s=7200, operational_s=600, tactical_s=1)
        assert t.strategic_s == 7200.0


# ---------------------------------------------------------------------------
# Config model: TerrainConfig
# ---------------------------------------------------------------------------


class TestTerrainConfig:
    """Terrain configuration validation."""

    def test_minimal(self) -> None:
        t = TerrainConfig(width_m=1000, height_m=1000)
        assert t.cell_size_m == 100.0
        assert t.terrain_type == "flat_desert"

    def test_invalid_terrain_type(self) -> None:
        with pytest.raises(ValueError, match="terrain_type"):
            TerrainConfig(width_m=100, height_m=100, terrain_type="jungle")

    def test_hilly_defense(self) -> None:
        t = TerrainConfig(
            width_m=5000, height_m=5000, terrain_type="hilly_defense",
            features=[{"type": "ridge", "position": [2500, 0], "params": {"height_m": 50}}],
        )
        assert len(t.features) == 1

    def test_open_ocean(self) -> None:
        t = TerrainConfig(width_m=10000, height_m=10000, terrain_type="open_ocean")
        assert t.base_elevation_m == 0.0


# ---------------------------------------------------------------------------
# Config model: CampaignScenarioConfig
# ---------------------------------------------------------------------------


class TestCampaignScenarioConfig:
    """Top-level campaign configuration."""

    def test_minimal_valid(self) -> None:
        cfg = CampaignScenarioConfig.model_validate(_minimal_config())
        assert cfg.name == "Test"
        assert cfg.duration_hours == 24

    def test_fewer_than_two_sides_rejected(self) -> None:
        raw = _minimal_config(sides=[{"side": "blue", "units": []}])
        with pytest.raises(ValueError, match="at least 2"):
            CampaignScenarioConfig.model_validate(raw)

    def test_zero_duration_rejected(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            CampaignScenarioConfig.model_validate(_minimal_config(duration_hours=0))

    def test_negative_duration_rejected(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            CampaignScenarioConfig.model_validate(_minimal_config(duration_hours=-1))

    def test_defaults(self) -> None:
        cfg = CampaignScenarioConfig.model_validate(_minimal_config())
        assert cfg.latitude == 0.0
        assert cfg.objectives == []
        assert cfg.victory_conditions == []
        assert cfg.reinforcements == []
        assert cfg.calibration_overrides == {}

    def test_with_objectives_and_victory(self) -> None:
        raw = _minimal_config(
            objectives=[{
                "objective_id": "obj1",
                "position": [5000, 5000],
                "type": "territory",
            }],
            victory_conditions=[
                {"type": "territory_control", "side": "blue"},
                {"type": "time_expired"},
            ],
        )
        cfg = CampaignScenarioConfig.model_validate(raw)
        assert len(cfg.objectives) == 1
        assert len(cfg.victory_conditions) == 2

    def test_with_reinforcements(self) -> None:
        raw = _minimal_config(
            reinforcements=[{
                "side": "blue",
                "arrival_time_s": 3600,
                "units": [{"unit_type": "m1a2", "count": 2}],
            }],
        )
        cfg = CampaignScenarioConfig.model_validate(raw)
        assert len(cfg.reinforcements) == 1
        assert cfg.reinforcements[0].units[0].count == 2

    def test_tick_resolution_defaults(self) -> None:
        cfg = CampaignScenarioConfig.model_validate(_minimal_config())
        assert cfg.tick_resolution.strategic_s == 3600.0

    def test_custom_tick_resolution(self) -> None:
        raw = _minimal_config(
            tick_resolution={"strategic_s": 7200, "operational_s": 600, "tactical_s": 2},
        )
        cfg = CampaignScenarioConfig.model_validate(raw)
        assert cfg.tick_resolution.strategic_s == 7200.0

    def test_weather_conditions(self) -> None:
        raw = _minimal_config(
            weather_conditions={"visibility_m": 5000, "wind_speed_mps": 10},
        )
        cfg = CampaignScenarioConfig.model_validate(raw)
        assert cfg.weather_conditions["visibility_m"] == 5000


# ---------------------------------------------------------------------------
# YAML parsing (round-trip)
# ---------------------------------------------------------------------------


class TestYamlParsing:
    """End-to-end YAML → config parsing."""

    def test_load_from_yaml_file(self, tmp_path: Path) -> None:
        raw = _minimal_config()
        p = tmp_path / "scenario.yaml"
        p.write_text(yaml.dump(raw))
        with open(p) as f:
            loaded = yaml.safe_load(f)
        cfg = CampaignScenarioConfig.model_validate(loaded)
        assert cfg.name == "Test"

    def test_round_trip_preserves_data(self, tmp_path: Path) -> None:
        raw = _minimal_config(
            objectives=[{"objective_id": "o1", "position": [100, 200], "type": "territory"}],
            victory_conditions=[{"type": "force_destroyed", "params": {"threshold": 0.7}}],
        )
        p = tmp_path / "scenario.yaml"
        p.write_text(yaml.dump(raw))
        with open(p) as f:
            loaded = yaml.safe_load(f)
        cfg = CampaignScenarioConfig.model_validate(loaded)
        assert cfg.objectives[0].objective_id == "o1"
        assert cfg.victory_conditions[0].params["threshold"] == 0.7

    def test_model_dump_serializable(self) -> None:
        cfg = CampaignScenarioConfig.model_validate(_minimal_config())
        d = cfg.model_dump()
        assert isinstance(d, dict)
        assert d["name"] == "Test"

    def test_full_campaign_yaml(self, tmp_path: Path) -> None:
        """Parse a comprehensive campaign YAML with all fields."""
        raw = {
            "name": "Full Campaign",
            "date": "2024-01-01T00:00:00Z",
            "duration_hours": 72,
            "latitude": 33.0,
            "longitude": 45.0,
            "tick_resolution": {"strategic_s": 3600, "operational_s": 300, "tactical_s": 5},
            "weather_conditions": {"visibility_m": 8000},
            "terrain": {
                "width_m": 20000,
                "height_m": 20000,
                "cell_size_m": 200,
                "terrain_type": "hilly_defense",
                "features": [{"type": "ridge", "position": [10000, 0], "params": {"height_m": 50}}],
            },
            "sides": [
                {
                    "side": "blue",
                    "units": [{"unit_type": "m1a2", "count": 10}],
                    "experience_level": 0.9,
                    "commander_profile": "aggressive_armor",
                    "depots": [{"depot_id": "d1", "position": [1000, 10000]}],
                },
                {
                    "side": "red",
                    "units": [{"unit_type": "m1a2", "count": 15}],
                    "experience_level": 0.6,
                },
            ],
            "objectives": [
                {"objective_id": "city", "position": [10000, 10000], "radius_m": 1000, "type": "territory"},
            ],
            "victory_conditions": [
                {"type": "territory_control", "side": "blue", "params": {"threshold": 1.0}},
                {"type": "force_destroyed", "params": {"threshold": 0.8}},
                {"type": "time_expired"},
            ],
            "reinforcements": [
                {
                    "side": "blue",
                    "arrival_time_s": 14400,
                    "units": [{"unit_type": "m1a2", "count": 5}],
                    "position": [500, 10000],
                },
            ],
            "calibration_overrides": {"hit_probability_modifier": 1.2},
        }
        p = tmp_path / "full.yaml"
        p.write_text(yaml.dump(raw))
        with open(p) as f:
            loaded = yaml.safe_load(f)
        cfg = CampaignScenarioConfig.model_validate(loaded)
        assert cfg.name == "Full Campaign"
        assert cfg.duration_hours == 72
        assert len(cfg.sides) == 2
        assert len(cfg.objectives) == 1
        assert len(cfg.victory_conditions) == 3
        assert len(cfg.reinforcements) == 1
        assert cfg.calibration_overrides["hit_probability_modifier"] == 1.2


# ---------------------------------------------------------------------------
# Parse start time helper
# ---------------------------------------------------------------------------


class TestParseStartTime:
    """ISO datetime parsing."""

    def test_full_iso_with_tz(self) -> None:
        dt = _parse_start_time("2024-06-15T12:00:00+00:00")
        assert dt.year == 2024
        assert dt.hour == 12
        assert dt.tzinfo is not None

    def test_iso_without_tz_defaults_utc(self) -> None:
        dt = _parse_start_time("2024-06-15T12:00:00")
        assert dt.tzinfo == timezone.utc

    def test_date_only(self) -> None:
        dt = _parse_start_time("2024-06-15")
        assert dt.hour == 0
        assert dt.tzinfo == timezone.utc

    def test_z_suffix(self) -> None:
        dt = _parse_start_time("2024-06-15T12:00:00Z")
        assert dt.tzinfo is not None


# ---------------------------------------------------------------------------
# SimulationContext
# ---------------------------------------------------------------------------


class TestSimulationContext:
    """SimulationContext dataclass behavior."""

    def test_creation(self) -> None:
        ctx = _make_ctx()
        assert ctx.config.name == "Test"
        assert ctx.heightmap is None

    def test_all_units_empty(self) -> None:
        ctx = _make_ctx()
        assert ctx.all_units() == []

    def test_all_units_flattens(self) -> None:
        from stochastic_warfare.entities.base import Unit
        u1 = Unit(entity_id="u1", position=POS_ORIGIN)
        u2 = Unit(entity_id="u2", position=POS_ORIGIN)
        ctx = _make_ctx(units_by_side={"blue": [u1], "red": [u2]})
        assert len(ctx.all_units()) == 2

    def test_active_units_filters(self) -> None:
        from stochastic_warfare.entities.base import Unit, UnitStatus
        u1 = Unit(entity_id="u1", position=POS_ORIGIN)
        u2 = Unit(entity_id="u2", position=POS_ORIGIN)
        object.__setattr__(u2, "status", UnitStatus.DESTROYED)
        ctx = _make_ctx(units_by_side={"blue": [u1, u2]})
        assert len(ctx.active_units("blue")) == 1

    def test_side_names_sorted(self) -> None:
        ctx = _make_ctx(units_by_side={"red": [], "blue": []})
        assert ctx.side_names() == ["blue", "red"]

    def test_get_state_captures_config(self) -> None:
        ctx = _make_ctx()
        state = ctx.get_state()
        assert state["config"]["name"] == "Test"
        assert "clock" in state
        assert "rng" in state

    def test_get_state_captures_units(self) -> None:
        from stochastic_warfare.entities.base import Unit
        u = Unit(entity_id="u1", position=POS_ORIGIN)
        ctx = _make_ctx(units_by_side={"blue": [u]})
        state = ctx.get_state()
        assert "blue" in state["units_by_side"]
        assert len(state["units_by_side"]["blue"]) == 1

    def test_set_state_restores_clock(self) -> None:
        ctx = _make_ctx()
        ctx.clock.advance()
        state = ctx.get_state()

        # Create fresh context and restore
        ctx2 = _make_ctx()
        assert ctx2.clock.tick_count == 0
        ctx2.set_state(state)
        assert ctx2.clock.tick_count == 1

    def test_calibration_round_trip(self) -> None:
        ctx = _make_ctx(calibration={"some_key": 42})
        state = ctx.get_state()
        ctx2 = _make_ctx()
        ctx2.set_state(state)
        assert ctx2.calibration["some_key"] == 42


# ---------------------------------------------------------------------------
# Terrain building (via ScenarioLoader)
# ---------------------------------------------------------------------------


class TestTerrainBuilding:
    """Terrain construction from config."""

    def test_flat_desert(self) -> None:
        loader = ScenarioLoader(DATA_DIR)
        tc = TerrainConfig(width_m=1000, height_m=1000, terrain_type="flat_desert")
        hm = loader._build_terrain(tc, RNGManager(42))
        assert hm.shape == (10, 10)  # 1000/100

    def test_open_ocean(self) -> None:
        loader = ScenarioLoader(DATA_DIR)
        tc = TerrainConfig(width_m=500, height_m=500, terrain_type="open_ocean")
        hm = loader._build_terrain(tc, RNGManager(42))
        assert np.all(hm._data == 0.0)

    def test_hilly_defense(self) -> None:
        loader = ScenarioLoader(DATA_DIR)
        tc = TerrainConfig(
            width_m=1000, height_m=1000, terrain_type="hilly_defense",
            features=[{"type": "ridge", "position": [500, 0], "params": {"height_m": 50}}],
        )
        hm = loader._build_terrain(tc, RNGManager(42))
        assert hm._data.max() > 0  # ridge elevates terrain

    def test_custom_cell_size(self) -> None:
        loader = ScenarioLoader(DATA_DIR)
        tc = TerrainConfig(width_m=1000, height_m=1000, cell_size_m=50)
        hm = loader._build_terrain(tc, RNGManager(42))
        assert hm.shape == (20, 20)  # 1000/50


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Validation and error cases."""

    def test_missing_name_rejected(self) -> None:
        raw = _minimal_config()
        del raw["name"]
        with pytest.raises(Exception):
            CampaignScenarioConfig.model_validate(raw)

    def test_missing_terrain_rejected(self) -> None:
        raw = _minimal_config()
        del raw["terrain"]
        with pytest.raises(Exception):
            CampaignScenarioConfig.model_validate(raw)

    def test_missing_sides_rejected(self) -> None:
        raw = _minimal_config()
        del raw["sides"]
        with pytest.raises(Exception):
            CampaignScenarioConfig.model_validate(raw)

    def test_empty_sides_rejected(self) -> None:
        with pytest.raises(ValueError):
            CampaignScenarioConfig.model_validate(_minimal_config(sides=[]))

    def test_invalid_victory_condition_type(self) -> None:
        raw = _minimal_config(
            victory_conditions=[{"type": "bad_type"}],
        )
        with pytest.raises(ValueError):
            CampaignScenarioConfig.model_validate(raw)

    def test_invalid_objective_type(self) -> None:
        raw = _minimal_config(
            objectives=[{"objective_id": "o1", "position": [0, 0], "type": "invalid"}],
        )
        with pytest.raises(ValueError):
            CampaignScenarioConfig.model_validate(raw)

    def test_invalid_terrain_type(self) -> None:
        raw = _minimal_config(
            terrain={"width_m": 1000, "height_m": 1000, "terrain_type": "swamp"},
        )
        with pytest.raises(ValueError):
            CampaignScenarioConfig.model_validate(raw)

    def test_nonexistent_yaml_file(self) -> None:
        loader = ScenarioLoader(DATA_DIR)
        with pytest.raises(FileNotFoundError):
            loader.load(Path("nonexistent/scenario.yaml"))


# ---------------------------------------------------------------------------
# Full scenario load (integration-style)
# ---------------------------------------------------------------------------


class TestScenarioLoad:
    """Full scenario loading from YAML — creates real engines."""

    def test_load_test_campaign(self) -> None:
        loader = ScenarioLoader(DATA_DIR)
        ctx = loader.load(Path("data/scenarios/test_campaign/scenario.yaml"))
        assert "Test Campaign" in ctx.config.name
        assert len(ctx.units_by_side) == 2
        assert "blue" in ctx.units_by_side
        assert "red" in ctx.units_by_side

    def test_units_created_correctly(self) -> None:
        loader = ScenarioLoader(DATA_DIR)
        ctx = loader.load(Path("data/scenarios/test_campaign/scenario.yaml"))
        blue = ctx.units_by_side["blue"]
        red = ctx.units_by_side["red"]
        assert len(blue) == 4  # 4 m1a2s
        assert len(red) == 6   # 6 m1a2s

    def test_engines_created(self) -> None:
        loader = ScenarioLoader(DATA_DIR)
        ctx = loader.load(Path("data/scenarios/test_campaign/scenario.yaml"))
        assert ctx.engagement_engine is not None
        assert ctx.fog_of_war is not None
        assert ctx.morale_machine is not None
        assert ctx.ooda_engine is not None
        assert ctx.stockpile_manager is not None

    def test_deterministic_seed(self) -> None:
        loader = ScenarioLoader(DATA_DIR)
        ctx1 = loader.load(Path("data/scenarios/test_campaign/scenario.yaml"), seed=100)
        ctx2 = loader.load(Path("data/scenarios/test_campaign/scenario.yaml"), seed=100)
        # Same seed → same unit positions
        for u1, u2 in zip(ctx1.all_units(), ctx2.all_units()):
            assert u1.position.easting == u2.position.easting
            assert u1.position.northing == u2.position.northing

    def test_heightmap_created(self) -> None:
        loader = ScenarioLoader(DATA_DIR)
        ctx = loader.load(Path("data/scenarios/test_campaign/scenario.yaml"))
        assert ctx.heightmap is not None
        assert ctx.heightmap.shape[0] == 100  # 10000/100
