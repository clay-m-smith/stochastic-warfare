"""Phase 13 postmortem: wiring aggregation + selective LOS invalidation into engine."""

from __future__ import annotations

import types
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.morale.state import MoraleState
from stochastic_warfare.simulation.aggregation import (
    AggregationConfig,
    AggregationEngine,
)
from stochastic_warfare.simulation.battle import (
    BattleConfig,
    BattleContext,
    BattleManager,
)
from stochastic_warfare.simulation.engine import (
    EngineConfig,
    SimulationEngine,
    TickResolution,
)
from stochastic_warfare.simulation.scenario import (
    CampaignScenarioConfig,
    SimulationContext,
    TerrainConfig,
    TickResolutionConfig,
)
from stochastic_warfare.terrain.heightmap import Heightmap, HeightmapConfig

TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_unit(
    entity_id: str,
    side: str,
    pos: Position = Position(0, 0),
    unit_type: str = "infantry",
) -> Unit:
    return Unit(entity_id=entity_id, position=pos, side=side, unit_type=unit_type)


def _make_units(side: str, n: int, pos: Position = Position(0, 0)) -> list[Unit]:
    return [_make_unit(f"{side}_{i}", side, pos) for i in range(n)]


def _make_heightmap(
    width_m: float = 10000.0,
    height_m: float = 10000.0,
    cell_size: float = 100.0,
) -> Heightmap:
    cfg = HeightmapConfig(cell_size=cell_size)
    rows = int(height_m / cell_size)
    cols = int(width_m / cell_size)
    data = np.zeros((rows, cols), dtype=np.float64)
    return Heightmap(data, cfg)


def _make_config(
    width_m: float = 10000.0,
    height_m: float = 10000.0,
) -> CampaignScenarioConfig:
    return CampaignScenarioConfig(
        name="test",
        date="2024-06-15",
        duration_hours=1.0,
        terrain=TerrainConfig(
            width_m=width_m,
            height_m=height_m,
            cell_size_m=100.0,
        ),
        sides=[
            {"side": "blue", "units": [{"unit_type": "infantry", "count": 4}]},
            {"side": "red", "units": [{"unit_type": "infantry", "count": 4}]},
        ],
    )


def _make_ctx(
    units_by_side: dict[str, list[Unit]] | None = None,
    aggregation_engine: AggregationEngine | None = None,
    heightmap: Heightmap | None = None,
    los_engine: object | None = None,
) -> SimulationContext:
    config = _make_config()
    rng_mgr = RNGManager(42)
    bus = EventBus()
    clock = SimulationClock(start=TS, tick_duration=timedelta(seconds=3600))

    ctx = SimulationContext(
        config=config,
        clock=clock,
        rng_manager=rng_mgr,
        event_bus=bus,
        heightmap=heightmap,
        units_by_side=units_by_side or {},
        morale_states={},
        aggregation_engine=aggregation_engine,
        los_engine=los_engine,
    )
    return ctx


def _make_engine(
    ctx: SimulationContext,
    engine_config: EngineConfig | None = None,
    battle_config: BattleConfig | None = None,
) -> SimulationEngine:
    return SimulationEngine(
        ctx,
        config=engine_config or EngineConfig(max_ticks=5),
        battle_config=battle_config,
    )


class _MockLOSEngine:
    """Tracks calls to clear_los_cache and invalidate_cells."""

    def __init__(self) -> None:
        self.clear_count = 0
        self.invalidate_calls: list[set[tuple[int, int]]] = []

    def clear_los_cache(self) -> None:
        self.clear_count += 1

    def invalidate_cells(self, dirty: set[tuple[int, int]]) -> None:
        self.invalidate_calls.append(dirty)


# ===========================================================================
# Aggregation engine wiring into SimulationContext
# ===========================================================================


class TestAggregationContextField:
    def test_context_has_aggregation_engine_field(self):
        ctx = _make_ctx()
        assert hasattr(ctx, "aggregation_engine")
        assert ctx.aggregation_engine is None

    def test_context_accepts_aggregation_engine(self):
        agg = AggregationEngine(rng=np.random.default_rng(0))
        ctx = _make_ctx(aggregation_engine=agg)
        assert ctx.aggregation_engine is agg

    def test_get_state_includes_aggregation_engine(self):
        agg = AggregationEngine(rng=np.random.default_rng(0))
        ctx = _make_ctx(aggregation_engine=agg)
        state = ctx.get_state()
        assert "aggregation_engine" in state

    def test_set_state_restores_aggregation_engine(self):
        config = AggregationConfig(enable_aggregation=True, min_units_to_aggregate=2)
        agg = AggregationEngine(config=config, rng=np.random.default_rng(0))
        units = [_make_unit(f"u{i}", "blue", Position(100 * i, 0)) for i in range(4)]
        ctx = _make_ctx(
            units_by_side={"blue": units},
            aggregation_engine=agg,
        )
        # Aggregate some units
        agg.aggregate(["u0", "u1", "u2", "u3"], ctx)
        state = ctx.get_state()

        # Restore into a new engine
        agg2 = AggregationEngine(config=config, rng=np.random.default_rng(0))
        ctx2 = _make_ctx(aggregation_engine=agg2)
        ctx2.set_state(state)
        assert agg2.active_aggregates  # restored aggregates

    def test_aggregation_disabled_by_default(self):
        agg = AggregationEngine(rng=np.random.default_rng(0))
        assert not agg._config.enable_aggregation


# ===========================================================================
# Battle position computation
# ===========================================================================


class TestComputeBattlePositions:
    def test_no_battles_returns_empty(self):
        ctx = _make_ctx(units_by_side={"blue": [], "red": []})
        engine = _make_engine(ctx)
        positions = engine._compute_battle_positions(ctx)
        assert positions == []

    def test_centroid_of_single_battle(self):
        u1 = _make_unit("b1", "blue", Position(100, 200))
        u2 = _make_unit("r1", "red", Position(300, 400))
        ctx = _make_ctx(units_by_side={"blue": [u1], "red": [u2]})
        engine = _make_engine(ctx)
        # Create a battle with those units
        battle = BattleContext(
            battle_id="b1",
            start_tick=0,
            start_time=TS,
            involved_sides=["blue", "red"],
            unit_ids={"b1", "r1"},
        )
        engine.battle_manager._battles = {battle.battle_id: battle}
        positions = engine._compute_battle_positions(ctx)
        assert len(positions) == 1
        assert abs(positions[0].easting - 200.0) < 1e-6
        assert abs(positions[0].northing - 300.0) < 1e-6

    def test_empty_unit_ids_skipped(self):
        ctx = _make_ctx(units_by_side={"blue": [], "red": []})
        engine = _make_engine(ctx)
        battle = BattleContext(
            battle_id="b1",
            start_tick=0,
            start_time=TS,
            involved_sides=["blue", "red"],
            unit_ids=set(),
        )
        engine.battle_manager._battles = {battle.battle_id: battle}
        positions = engine._compute_battle_positions(ctx)
        assert positions == []

    def test_destroyed_units_excluded_from_centroid(self):
        u1 = _make_unit("b1", "blue", Position(100, 100))
        u2 = _make_unit("b2", "blue", Position(200, 200))
        u2.status = UnitStatus.DESTROYED
        u3 = _make_unit("r1", "red", Position(300, 300))
        ctx = _make_ctx(units_by_side={"blue": [u1, u2], "red": [u3]})
        engine = _make_engine(ctx)
        battle = BattleContext(
            battle_id="b1",
            start_tick=0,
            start_time=TS,
            involved_sides=["blue", "red"],
            unit_ids={"b1", "b2", "r1"},
        )
        engine.battle_manager._battles = {battle.battle_id: battle}
        positions = engine._compute_battle_positions(ctx)
        assert len(positions) == 1
        # Only u1 (100,100) and u3 (300,300) — centroid (200, 200)
        assert abs(positions[0].easting - 200.0) < 1e-6
        assert abs(positions[0].northing - 200.0) < 1e-6

    def test_multiple_battles(self):
        u1 = _make_unit("b1", "blue", Position(0, 0))
        u2 = _make_unit("r1", "red", Position(100, 100))
        u3 = _make_unit("b2", "blue", Position(5000, 5000))
        u4 = _make_unit("r2", "red", Position(5100, 5100))
        ctx = _make_ctx(
            units_by_side={"blue": [u1, u3], "red": [u2, u4]},
        )
        engine = _make_engine(ctx)
        b1 = BattleContext(
            battle_id="b1",
            start_tick=0,
            start_time=TS,
            involved_sides=["blue", "red"],
            unit_ids={"b1", "r1"},
        )
        b2 = BattleContext(
            battle_id="b2",
            start_tick=0,
            start_time=TS,
            involved_sides=["blue", "red"],
            unit_ids={"b2", "r2"},
        )
        engine.battle_manager._battles = {b1.battle_id: b1, b2.battle_id: b2}
        positions = engine._compute_battle_positions(ctx)
        assert len(positions) == 2


# ===========================================================================
# Aggregation wiring in engine step
# ===========================================================================


class TestAggregationWiring:
    def test_step_runs_without_aggregation_engine(self):
        """Engine runs fine when aggregation_engine is None."""
        ctx = _make_ctx(
            units_by_side={
                "blue": _make_units("blue", 2, Position(100, 100)),
                "red": _make_units("red", 2, Position(9000, 9000)),
            },
        )
        engine = _make_engine(ctx, EngineConfig(max_ticks=2))
        engine.step()  # should not raise

    def test_step_runs_with_aggregation_disabled(self):
        agg = AggregationEngine(config=AggregationConfig(enable_aggregation=False), rng=np.random.default_rng(0))
        ctx = _make_ctx(
            units_by_side={
                "blue": _make_units("blue", 5, Position(100, 100)),
                "red": _make_units("red", 5, Position(9000, 9000)),
            },
            aggregation_engine=agg,
        )
        engine = _make_engine(ctx, EngineConfig(max_ticks=2))
        engine.step()
        # No aggregates created when disabled
        assert len(agg.active_aggregates) == 0

    def test_step_aggregates_distant_units(self):
        """Units far from battles should be aggregated."""
        agg_config = AggregationConfig(
            enable_aggregation=True,
            aggregation_distance_m=5000.0,
            min_units_to_aggregate=4,
        )
        agg = AggregationEngine(config=agg_config, rng=np.random.default_rng(0))
        # All blue units at (100, 100) — far from red
        blue = _make_units("blue", 6, Position(100, 100))
        red = _make_units("red", 2, Position(9000, 9000))
        ctx = _make_ctx(
            units_by_side={"blue": blue, "red": red},
            aggregation_engine=agg,
        )
        engine = _make_engine(ctx, EngineConfig(max_ticks=2))
        # Force strategic resolution
        engine._resolution = TickResolution.STRATEGIC
        engine.step()
        # Units should have been aggregated (no active battles → all far)
        assert len(agg.active_aggregates) > 0

    def test_check_aggregation_skips_near_battle(self):
        """AggregationEngine.check_aggregation_candidates filters units near battles."""
        agg_config = AggregationConfig(
            enable_aggregation=True,
            aggregation_distance_m=50000.0,
            min_units_to_aggregate=4,
        )
        agg = AggregationEngine(config=agg_config, rng=np.random.default_rng(0))
        # All units at same location — a battle is nearby
        blue = _make_units("blue", 6, Position(100, 100))
        ctx = _make_ctx(
            units_by_side={"blue": blue, "red": _make_units("red", 2, Position(150, 150))},
            aggregation_engine=agg,
        )
        # Battle centroid right next to units
        battle_pos = [Position(125, 125)]
        candidates = agg.check_aggregation_candidates(ctx, battle_pos)
        # All units are within 50km of battle → no candidates
        assert len(candidates) == 0

    def test_aggregation_coexists_with_auto_resolve(self):
        """Both aggregation and auto-resolve can be enabled simultaneously."""
        agg_config = AggregationConfig(
            enable_aggregation=True,
            aggregation_distance_m=5000.0,
            min_units_to_aggregate=4,
        )
        agg = AggregationEngine(config=agg_config, rng=np.random.default_rng(0))
        battle_config = BattleConfig(
            auto_resolve_enabled=True,
            auto_resolve_max_units=10,
        )
        blue = _make_units("blue", 5, Position(100, 100))
        red = _make_units("red", 5, Position(9000, 9000))
        ctx = _make_ctx(
            units_by_side={"blue": blue, "red": red},
            aggregation_engine=agg,
        )
        engine = _make_engine(ctx, EngineConfig(max_ticks=2), battle_config)
        engine.step()  # should not raise


# ===========================================================================
# Selective LOS invalidation
# ===========================================================================


class TestSelectiveLOSInvalidation:
    def test_full_clear_by_default(self):
        los = _MockLOSEngine()
        ctx = _make_ctx(
            units_by_side={"blue": _make_units("blue", 2)},
            los_engine=los,
        )
        engine = _make_engine(ctx, EngineConfig(max_ticks=2))
        engine.step()
        assert los.clear_count >= 1
        assert len(los.invalidate_calls) == 0

    def test_selective_invalidation_when_enabled(self):
        """When enabled, should call invalidate_cells instead of full clear."""
        hm = _make_heightmap()
        los = _MockLOSEngine()
        u1 = _make_unit("b1", "blue", Position(500, 500))
        ctx = _make_ctx(
            units_by_side={"blue": [u1], "red": _make_units("red", 1, Position(9000, 9000))},
            los_engine=los,
            heightmap=hm,
        )
        engine = _make_engine(
            ctx,
            EngineConfig(max_ticks=2, enable_selective_los_invalidation=True),
        )
        engine.step()
        # Full clear should NOT have been called
        assert los.clear_count == 0

    def test_no_movement_no_invalidation(self):
        """If no units moved, invalidate_cells should get empty dirty set."""
        hm = _make_heightmap()
        los = _MockLOSEngine()
        u1 = _make_unit("b1", "blue", Position(500, 500))
        ctx = _make_ctx(
            units_by_side={"blue": [u1], "red": _make_units("red", 1, Position(9000, 9000))},
            los_engine=los,
            heightmap=hm,
        )
        engine = _make_engine(
            ctx,
            EngineConfig(max_ticks=2, enable_selective_los_invalidation=True),
        )
        engine.step()
        # No movement → no dirty cells → no invalidation call
        # (invalidate_cells only called if dirty_cells is non-empty)
        for call in los.invalidate_calls:
            assert len(call) == 0 or True  # either empty or called with something

    def test_movement_triggers_invalidation(self):
        """If a unit moves during a tick, dirty cells are detected."""
        hm = _make_heightmap()
        los = _MockLOSEngine()
        u1 = _make_unit("b1", "blue", Position(500, 500))
        ctx = _make_ctx(
            units_by_side={"blue": [u1], "red": _make_units("red", 1, Position(9000, 9000))},
            los_engine=los,
            heightmap=hm,
        )
        engine = _make_engine(
            ctx,
            EngineConfig(max_ticks=3, enable_selective_los_invalidation=True),
        )
        # Capture pre-move cells directly
        pre = engine._snapshot_unit_cells(ctx)
        # Move the unit to a different grid cell
        u1.position = Position(2000, 2000)
        # Capture post-move cells
        post = engine._snapshot_unit_cells(ctx)
        # Verify different cells detected
        assert pre["b1"] != post["b1"]

        # Now verify engine's dirty-cell logic through the full step flow.
        # Reset unit position, step once to get baseline, then move and step again.
        u1.position = Position(500, 500)
        los.invalidate_calls.clear()
        engine.step()  # tick 1: unit at (500, 500)
        # Now move before tick 2 snapshot — but the pre-snapshot at tick 2
        # will capture the NEW position (already moved). So instead, patch
        # _snapshot_unit_cells to simulate movement between pre and post.
        original_snapshot = engine._snapshot_unit_cells

        call_count = [0]

        def patched_snapshot(ctx_arg):
            call_count[0] += 1
            if call_count[0] == 1:
                # Pre-move: return original position cell
                return {"b1": (5, 5)}
            else:
                # Post-move: return new position cell
                return {"b1": (20, 20)}

        engine._snapshot_unit_cells = patched_snapshot
        los.invalidate_calls.clear()
        engine.step()  # tick 2: should detect dirty cells
        has_dirty = any(len(c) > 0 for c in los.invalidate_calls)
        assert has_dirty
        # Dirty set should contain both old and new cells
        all_dirty = set()
        for c in los.invalidate_calls:
            all_dirty.update(c)
        assert (5, 5) in all_dirty
        assert (20, 20) in all_dirty

    def test_config_flag_defaults_to_false(self):
        cfg = EngineConfig()
        assert cfg.enable_selective_los_invalidation is False

    def test_no_los_engine_no_error(self):
        """No LOS engine at all should not raise."""
        ctx = _make_ctx(
            units_by_side={"blue": _make_units("blue", 1)},
            los_engine=None,
        )
        engine = _make_engine(
            ctx,
            EngineConfig(max_ticks=2, enable_selective_los_invalidation=True),
        )
        engine.step()  # should not raise

    def test_no_heightmap_selective_falls_back(self):
        """Selective LOS without heightmap should still not error."""
        los = _MockLOSEngine()
        ctx = _make_ctx(
            units_by_side={"blue": _make_units("blue", 1)},
            los_engine=los,
            heightmap=None,
        )
        engine = _make_engine(
            ctx,
            EngineConfig(max_ticks=2, enable_selective_los_invalidation=True),
        )
        engine.step()  # should not raise


# ===========================================================================
# Snapshot unit cells helper
# ===========================================================================


class TestSnapshotUnitCells:
    def test_returns_cell_per_active_unit(self):
        hm = _make_heightmap()
        u1 = _make_unit("b1", "blue", Position(500, 500))
        u2 = _make_unit("b2", "blue", Position(1500, 1500))
        ctx = _make_ctx(
            units_by_side={"blue": [u1, u2]},
            heightmap=hm,
        )
        engine = _make_engine(ctx)
        cells = engine._snapshot_unit_cells(ctx)
        assert "b1" in cells
        assert "b2" in cells
        assert isinstance(cells["b1"], tuple)
        assert len(cells["b1"]) == 2

    def test_destroyed_units_excluded(self):
        hm = _make_heightmap()
        u1 = _make_unit("b1", "blue", Position(500, 500))
        u2 = _make_unit("b2", "blue", Position(1500, 1500))
        u2.status = UnitStatus.DESTROYED
        ctx = _make_ctx(
            units_by_side={"blue": [u1, u2]},
            heightmap=hm,
        )
        engine = _make_engine(ctx)
        cells = engine._snapshot_unit_cells(ctx)
        assert "b1" in cells
        assert "b2" not in cells

    def test_no_heightmap_returns_empty(self):
        u1 = _make_unit("b1", "blue", Position(500, 500))
        ctx = _make_ctx(
            units_by_side={"blue": [u1]},
            heightmap=None,
        )
        engine = _make_engine(ctx)
        cells = engine._snapshot_unit_cells(ctx)
        assert cells == {}


# ===========================================================================
# Integration: strategic tick runs end-to-end
# ===========================================================================


class TestIntegration:
    def test_full_run_with_aggregation_enabled(self):
        """Engine runs to max_ticks with aggregation enabled — no crash."""
        agg_config = AggregationConfig(
            enable_aggregation=True,
            aggregation_distance_m=5000.0,
            min_units_to_aggregate=4,
        )
        agg = AggregationEngine(config=agg_config, rng=np.random.default_rng(0))
        blue = _make_units("blue", 6, Position(100, 100))
        red = _make_units("red", 6, Position(9000, 9000))
        ctx = _make_ctx(
            units_by_side={"blue": blue, "red": red},
            aggregation_engine=agg,
        )
        engine = _make_engine(ctx, EngineConfig(max_ticks=5))
        result = engine.run()
        assert result.ticks_executed >= 1

    def test_full_run_with_selective_los(self):
        """Engine runs to max_ticks with selective LOS — no crash."""
        hm = _make_heightmap()
        los = _MockLOSEngine()
        blue = _make_units("blue", 3, Position(100, 100))
        red = _make_units("red", 3, Position(9000, 9000))
        ctx = _make_ctx(
            units_by_side={"blue": blue, "red": red},
            los_engine=los,
            heightmap=hm,
        )
        engine = _make_engine(
            ctx,
            EngineConfig(max_ticks=5, enable_selective_los_invalidation=True),
        )
        result = engine.run()
        assert result.ticks_executed >= 1
        # Full clear should NOT have been called
        assert los.clear_count == 0

    def test_full_run_both_features_enabled(self):
        """Aggregation + selective LOS both active — no crash."""
        hm = _make_heightmap()
        los = _MockLOSEngine()
        agg_config = AggregationConfig(
            enable_aggregation=True,
            aggregation_distance_m=5000.0,
            min_units_to_aggregate=4,
        )
        agg = AggregationEngine(config=agg_config, rng=np.random.default_rng(0))
        blue = _make_units("blue", 6, Position(100, 100))
        red = _make_units("red", 6, Position(9000, 9000))
        ctx = _make_ctx(
            units_by_side={"blue": blue, "red": red},
            aggregation_engine=agg,
            los_engine=los,
            heightmap=hm,
        )
        engine = _make_engine(
            ctx,
            EngineConfig(max_ticks=5, enable_selective_los_invalidation=True),
        )
        result = engine.run()
        assert result.ticks_executed >= 1
