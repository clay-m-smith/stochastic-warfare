"""Tests for stochastic_warfare.validation.scenario_runner."""

from __future__ import annotations

import math
import types
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.events import Event, EventBus
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.terrain.heightmap import HeightmapConfig
from stochastic_warfare.validation.historical_data import (
    ForceDefinition,
    HistoricalEngagement,
    HistoricalMetric,
    TerrainSpec,
)
from stochastic_warfare.validation.scenario_runner import (
    ForceDestroyedTermination,
    MoraleCollapseTermination,
    ScenarioRunnerConfig,
    TimeLimitTermination,
    apply_behavior,
    build_flat_desert,
    build_hilly_defense,
    build_open_ocean,
    build_terrain,
    _parse_start_time,
)


_TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def _make_clock(elapsed_s: float = 0.0) -> SimulationClock:
    clock = SimulationClock(
        start=_TS,
        tick_duration=timedelta(seconds=5),
    )
    ticks_needed = int(elapsed_s / 5.0)
    for _ in range(ticks_needed):
        clock.advance()
    return clock


def _make_unit(
    entity_id: str = "u1",
    status: UnitStatus = UnitStatus.ACTIVE,
    pos: Position = Position(0.0, 0.0),
    side: str = "blue",
) -> Unit:
    return Unit(
        entity_id=entity_id,
        position=pos,
        name=entity_id,
        unit_type="m1a1",
        side=side,
        status=status,
    )


# ── ScenarioRunnerConfig ─────────────────────────────────────────────


class TestScenarioRunnerConfig:
    def test_defaults(self) -> None:
        cfg = ScenarioRunnerConfig()
        assert cfg.master_seed == 42
        assert cfg.max_ticks == 10000
        assert cfg.data_dir == "data"

    def test_custom(self) -> None:
        cfg = ScenarioRunnerConfig(master_seed=123, max_ticks=500)
        assert cfg.master_seed == 123
        assert cfg.max_ticks == 500


# ── Terrain builders ─────────────────────────────────────────────────


class TestBuildFlatDesert:
    def test_shape(self) -> None:
        spec = TerrainSpec(width_m=4000, height_m=6000, cell_size_m=100.0,
                          base_elevation_m=200.0)
        hm = build_flat_desert(spec)
        assert hm.shape == (60, 40)

    def test_elevation(self) -> None:
        spec = TerrainSpec(width_m=1000, height_m=1000, cell_size_m=100.0,
                          base_elevation_m=200.0)
        hm = build_flat_desert(spec)
        assert hm.elevation_at(Position(50, 50)) == pytest.approx(200.0)

    def test_small_grid(self) -> None:
        spec = TerrainSpec(width_m=50, height_m=50, cell_size_m=100.0)
        hm = build_flat_desert(spec)
        assert hm.shape[0] >= 1
        assert hm.shape[1] >= 1


class TestBuildOpenOcean:
    def test_shape(self) -> None:
        spec = TerrainSpec(width_m=10000, height_m=10000, cell_size_m=1000.0,
                          terrain_type="open_ocean")
        hm = build_open_ocean(spec)
        assert hm.shape == (10, 10)

    def test_elevation_zero(self) -> None:
        spec = TerrainSpec(width_m=1000, height_m=1000, cell_size_m=100.0,
                          terrain_type="open_ocean")
        hm = build_open_ocean(spec)
        assert hm.elevation_at(Position(50, 50)) == pytest.approx(0.0)


class TestBuildHillyDefense:
    def test_shape(self) -> None:
        spec = TerrainSpec(width_m=10000, height_m=15000, cell_size_m=100.0,
                          terrain_type="hilly_defense", base_elevation_m=900.0)
        rng = _rng()
        hm = build_hilly_defense(spec, rng)
        assert hm.shape == (150, 100)

    def test_has_variation(self) -> None:
        spec = TerrainSpec(width_m=1000, height_m=1000, cell_size_m=50.0,
                          terrain_type="hilly_defense", base_elevation_m=900.0)
        rng = _rng()
        hm = build_hilly_defense(spec, rng)
        # Should not be perfectly flat
        elevations = [
            hm.elevation_at(Position(x, y))
            for x in range(50, 950, 100)
            for y in range(50, 950, 100)
        ]
        assert max(elevations) > min(elevations)

    def test_ridge_feature(self) -> None:
        spec = TerrainSpec(
            width_m=1000, height_m=1000, cell_size_m=50.0,
            terrain_type="hilly_defense", base_elevation_m=900.0,
            features=[{"type": "ridge", "position": [500, 0],
                       "params": {"height_m": 100.0, "width_m": 200.0}}],
        )
        rng = _rng()
        hm = build_hilly_defense(spec, rng)
        # Elevation at ridge should be higher than far away
        ridge_elev = hm.elevation_at(Position(500, 500))
        far_elev = hm.elevation_at(Position(50, 500))
        assert ridge_elev > far_elev

    def test_berm_feature(self) -> None:
        spec = TerrainSpec(
            width_m=1000, height_m=1000, cell_size_m=50.0,
            terrain_type="hilly_defense", base_elevation_m=900.0,
            features=[{"type": "berm", "position": [500, 500],
                       "params": {"height_m": 5.0, "radius_m": 75.0}}],
        )
        rng = _rng(99)
        hm = build_hilly_defense(spec, rng)
        berm_elev = hm.elevation_at(Position(500, 500))
        # Berm should raise elevation
        assert berm_elev > 900.0


class TestBuildTerrain:
    def test_flat_desert(self) -> None:
        spec = TerrainSpec(width_m=1000, height_m=1000)
        hm = build_terrain(spec)
        assert hm.shape[0] > 0

    def test_open_ocean(self) -> None:
        spec = TerrainSpec(width_m=1000, height_m=1000, terrain_type="open_ocean")
        hm = build_terrain(spec)
        assert hm.elevation_at(Position(50, 50)) == pytest.approx(0.0)

    def test_hilly_defense(self) -> None:
        spec = TerrainSpec(width_m=1000, height_m=1000,
                          terrain_type="hilly_defense", base_elevation_m=900.0)
        hm = build_terrain(spec, _rng())
        assert hm.shape[0] > 0

    def test_unknown_type(self) -> None:
        # TerrainSpec validator rejects unknown types, but test build_terrain directly
        # by creating a spec with valid type then changing it
        spec = TerrainSpec(width_m=1000, height_m=1000)
        object.__setattr__(spec, "terrain_type", "swamp")
        with pytest.raises(ValueError, match="Unknown terrain type"):
            build_terrain(spec)


# ── Termination conditions ───────────────────────────────────────────


class TestTimeLimitTermination:
    def test_not_expired(self) -> None:
        cond = TimeLimitTermination(max_duration_s=1000.0)
        clock = _make_clock(elapsed_s=500.0)
        done, reason = cond.check(clock, {}, [])
        assert done is False
        assert reason == ""

    def test_expired(self) -> None:
        cond = TimeLimitTermination(max_duration_s=100.0)
        clock = _make_clock(elapsed_s=100.0)
        done, reason = cond.check(clock, {}, [])
        assert done is True
        assert reason == "time_limit"

    def test_exactly_at_limit(self) -> None:
        cond = TimeLimitTermination(max_duration_s=50.0)
        clock = _make_clock(elapsed_s=50.0)
        done, reason = cond.check(clock, {}, [])
        assert done is True


class TestForceDestroyedTermination:
    def test_below_threshold(self) -> None:
        cond = ForceDestroyedTermination(threshold=0.7)
        units = {"blue": [_make_unit("b1"), _make_unit("b2")]}
        done, _ = cond.check(_make_clock(), units, [])
        assert done is False

    def test_above_threshold(self) -> None:
        cond = ForceDestroyedTermination(threshold=0.5)
        units = {
            "red": [
                _make_unit("r1", UnitStatus.DESTROYED),
                _make_unit("r2", UnitStatus.DESTROYED),
                _make_unit("r3", UnitStatus.ACTIVE),
            ]
        }
        done, reason = cond.check(_make_clock(), units, [])
        assert done is True
        assert "red" in reason

    def test_surrendered_counts(self) -> None:
        cond = ForceDestroyedTermination(threshold=0.5)
        units = {
            "red": [
                _make_unit("r1", UnitStatus.SURRENDERED),
                _make_unit("r2"),
            ]
        }
        done, reason = cond.check(_make_clock(), units, [])
        assert done is True

    def test_empty_force(self) -> None:
        cond = ForceDestroyedTermination(threshold=0.5)
        units = {"blue": []}
        done, _ = cond.check(_make_clock(), units, [])
        assert done is False


class TestMoraleCollapseTermination:
    def test_no_collapse(self) -> None:
        cond = MoraleCollapseTermination(threshold=0.6)
        units = {"blue": [_make_unit("b1"), _make_unit("b2")]}
        done, _ = cond.check(_make_clock(), units, [])
        assert done is False

    def test_collapse(self) -> None:
        cond = MoraleCollapseTermination(threshold=0.5)
        units = {
            "red": [
                _make_unit("r1", UnitStatus.ROUTING),
                _make_unit("r2", UnitStatus.ROUTING),
                _make_unit("r3", UnitStatus.ACTIVE),
            ]
        }
        done, reason = cond.check(_make_clock(), units, [])
        assert done is True
        assert "morale_collapse" in reason


# ── Behavior engine ──────────────────────────────────────────────────


class TestApplyBehavior:
    def test_hold_position(self) -> None:
        units = [_make_unit("b1", pos=Position(0, 0))]
        apply_behavior(units, {"blue": {"hold_position": True}}, "blue", [], 5.0)
        assert units[0].speed == 0.0

    def test_advance_toward_enemy(self) -> None:
        attackers = [_make_unit("b1", pos=Position(0, 0))]
        enemies = [_make_unit("r1", pos=Position(1000, 0), side="red")]
        apply_behavior(
            attackers,
            {"blue": {"advance_speed_mps": 10.0}},
            "blue",
            enemies,
            5.0,
        )
        assert attackers[0].position.easting > 0  # moved east
        assert attackers[0].speed == 10.0

    def test_no_movement_without_enemies(self) -> None:
        attackers = [_make_unit("b1", pos=Position(0, 0))]
        apply_behavior(
            attackers,
            {"blue": {"advance_speed_mps": 10.0}},
            "blue",
            [],
            5.0,
        )
        assert attackers[0].position.easting == 0.0

    def test_no_movement_when_destroyed(self) -> None:
        attackers = [_make_unit("b1", UnitStatus.DESTROYED, pos=Position(0, 0))]
        enemies = [_make_unit("r1", pos=Position(1000, 0), side="red")]
        apply_behavior(
            attackers,
            {"blue": {"advance_speed_mps": 10.0}},
            "blue",
            enemies,
            5.0,
        )
        assert attackers[0].position.easting == 0.0

    def test_advance_distance_correct(self) -> None:
        attackers = [_make_unit("b1", pos=Position(0, 0))]
        enemies = [_make_unit("r1", pos=Position(1000, 0), side="red")]
        apply_behavior(
            attackers,
            {"blue": {"advance_speed_mps": 10.0}},
            "blue",
            enemies,
            5.0,
        )
        # Should advance 50m (10 m/s * 5s)
        assert attackers[0].position.easting == pytest.approx(50.0, abs=0.1)

    def test_no_rules_for_side(self) -> None:
        attackers = [_make_unit("b1", pos=Position(0, 0))]
        enemies = [_make_unit("r1", pos=Position(1000, 0), side="red")]
        apply_behavior(attackers, {}, "blue", enemies, 5.0)
        assert attackers[0].position.easting == 0.0


# ── _parse_start_time ────────────────────────────────────────────────


class TestParseStartTime:
    def test_date_only(self) -> None:
        dt = _parse_start_time("1991-02-26")
        assert dt.year == 1991
        assert dt.month == 2
        assert dt.day == 26
        assert dt.tzinfo is not None

    def test_iso_datetime(self) -> None:
        dt = _parse_start_time("1991-02-26T16:18:00Z")
        assert dt.hour == 16
        assert dt.minute == 18

    def test_iso_datetime_no_tz(self) -> None:
        dt = _parse_start_time("1991-02-26T16:18:00")
        assert dt.tzinfo is not None  # Should default to UTC


# ── Deterministic replay ─────────────────────────────────────────────


class TestDeterministicTerrain:
    def test_same_seed_same_terrain(self) -> None:
        spec = TerrainSpec(
            width_m=500, height_m=500, cell_size_m=50.0,
            terrain_type="hilly_defense", base_elevation_m=900.0,
        )
        hm1 = build_hilly_defense(spec, _rng(42))
        hm2 = build_hilly_defense(spec, _rng(42))
        e1 = hm1.elevation_at(Position(100, 100))
        e2 = hm2.elevation_at(Position(100, 100))
        assert e1 == pytest.approx(e2)

    def test_different_seed_different_terrain(self) -> None:
        spec = TerrainSpec(
            width_m=500, height_m=500, cell_size_m=50.0,
            terrain_type="hilly_defense", base_elevation_m=900.0,
        )
        hm1 = build_hilly_defense(spec, _rng(42))
        hm2 = build_hilly_defense(spec, _rng(99))
        e1 = hm1.elevation_at(Position(100, 100))
        e2 = hm2.elevation_at(Position(100, 100))
        assert e1 != pytest.approx(e2, abs=0.01)
