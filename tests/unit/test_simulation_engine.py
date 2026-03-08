"""Tests for the master simulation engine (simulation.engine).

Uses shared fixtures from conftest.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pytest

from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.simulation.battle import BattleConfig, BattleContext, BattleManager
from stochastic_warfare.simulation.campaign import CampaignConfig, CampaignManager
from stochastic_warfare.simulation.engine import (
    EngineConfig,
    SimulationEngine,
    SimulationRunResult,
    TickResolution,
)
from stochastic_warfare.simulation.recorder import RecorderConfig, SimulationRecorder
from stochastic_warfare.simulation.scenario import (
    CampaignScenarioConfig,
    ReinforcementConfig,
    ReinforcementUnitConfig,
    SideConfig,
    SimulationContext,
    TerrainConfig,
    TickResolutionConfig,
    VictoryConditionConfig,
)
from stochastic_warfare.simulation.victory import (
    ObjectiveState,
    VictoryEvaluator,
    VictoryEvaluatorConfig,
    VictoryResult,
)

from tests.conftest import DEFAULT_SEED, POS_ORIGIN, TS, make_clock, make_rng


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_unit(eid: str, pos: Position, side: str = "blue") -> Unit:
    u = Unit(entity_id=eid, position=pos)
    object.__setattr__(u, "side", side)
    return u


def _minimal_config(**overrides: Any) -> CampaignScenarioConfig:
    """Create a minimal valid CampaignScenarioConfig."""
    defaults = {
        "name": "Test",
        "date": "2024-06-15",
        "duration_hours": 1.0,
        "terrain": TerrainConfig(width_m=5000, height_m=5000),
        "sides": [
            SideConfig(side="blue", units=[]),
            SideConfig(side="red", units=[]),
        ],
    }
    defaults.update(overrides)
    return CampaignScenarioConfig(**defaults)


def _make_ctx(
    *,
    blue_units: list[Unit] | None = None,
    red_units: list[Unit] | None = None,
    config: CampaignScenarioConfig | None = None,
    tick_s: float = 3600.0,
    seed: int = DEFAULT_SEED,
) -> SimulationContext:
    """Create a minimal SimulationContext for engine tests."""
    cfg = config or _minimal_config()
    bus = EventBus()
    rng_mgr = RNGManager(seed)
    clock = SimulationClock(
        start=TS,
        tick_duration=timedelta(seconds=tick_s),
    )
    blue = blue_units if blue_units is not None else []
    red = red_units if red_units is not None else []
    ctx = SimulationContext(
        config=cfg,
        clock=clock,
        rng_manager=rng_mgr,
        event_bus=bus,
        units_by_side={"blue": blue, "red": red},
    )
    return ctx


# ---------------------------------------------------------------------------
# TickResolution enum
# ---------------------------------------------------------------------------


class TestTickResolution:
    """TickResolution enum values."""

    def test_values(self) -> None:
        assert TickResolution.STRATEGIC == 0
        assert TickResolution.OPERATIONAL == 1
        assert TickResolution.TACTICAL == 2

    def test_ordering(self) -> None:
        assert TickResolution.STRATEGIC < TickResolution.OPERATIONAL < TickResolution.TACTICAL


# ---------------------------------------------------------------------------
# EngineConfig
# ---------------------------------------------------------------------------


class TestEngineConfig:
    """EngineConfig pydantic model."""

    def test_defaults(self) -> None:
        c = EngineConfig()
        assert c.checkpoint_interval_ticks == 0
        assert c.max_ticks == 1_000_000
        assert c.snapshot_interval_ticks == 100

    def test_custom_values(self) -> None:
        c = EngineConfig(checkpoint_interval_ticks=50, max_ticks=100)
        assert c.checkpoint_interval_ticks == 50
        assert c.max_ticks == 100


# ---------------------------------------------------------------------------
# SimulationRunResult
# ---------------------------------------------------------------------------


class TestSimulationRunResult:
    """SimulationRunResult frozen dataclass."""

    def test_creation(self) -> None:
        vr = VictoryResult(game_over=True, winning_side="blue")
        r = SimulationRunResult(ticks_executed=100, duration_s=3600.0, victory_result=vr)
        assert r.ticks_executed == 100
        assert r.duration_s == 3600.0
        assert r.victory_result.winning_side == "blue"

    def test_frozen(self) -> None:
        vr = VictoryResult(game_over=False)
        r = SimulationRunResult(ticks_executed=0, duration_s=0.0, victory_result=vr)
        with pytest.raises(AttributeError):
            r.ticks_executed = 5  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Engine initialization
# ---------------------------------------------------------------------------


class TestEngineInit:
    """SimulationEngine construction."""

    def test_default_init(self) -> None:
        ctx = _make_ctx()
        engine = SimulationEngine(ctx)
        assert engine.resolution == TickResolution.STRATEGIC
        assert engine.campaign_manager is not None
        assert engine.battle_manager is not None

    def test_custom_config(self) -> None:
        ctx = _make_ctx()
        cfg = EngineConfig(max_ticks=50)
        engine = SimulationEngine(ctx, config=cfg)
        assert engine._config.max_ticks == 50

    def test_with_recorder(self) -> None:
        ctx = _make_ctx()
        rec = SimulationRecorder(ctx.event_bus)
        engine = SimulationEngine(ctx, recorder=rec)
        assert engine.recorder is rec

    def test_with_victory_evaluator(self) -> None:
        ctx = _make_ctx()
        ve = VictoryEvaluator([], [], ctx.event_bus)
        engine = SimulationEngine(ctx, victory_evaluator=ve)
        assert engine.victory_evaluator is ve

    def test_initial_clock_duration_is_strategic(self) -> None:
        ctx = _make_ctx()
        engine = SimulationEngine(ctx)
        assert ctx.clock.tick_duration.total_seconds() == 3600.0


# ---------------------------------------------------------------------------
# Single step
# ---------------------------------------------------------------------------


class TestSingleStep:
    """SimulationEngine.step() — one tick at a time."""

    def test_step_advances_clock(self) -> None:
        ctx = _make_ctx()
        engine = SimulationEngine(ctx)
        initial_tick = ctx.clock.tick_count
        engine.step()
        assert ctx.clock.tick_count == initial_tick + 1

    def test_step_returns_false_when_not_over(self) -> None:
        ctx = _make_ctx(config=_minimal_config(duration_hours=24.0))
        engine = SimulationEngine(ctx)
        result = engine.step()
        assert result is False

    def test_step_returns_true_at_max_ticks(self) -> None:
        ctx = _make_ctx()
        engine = SimulationEngine(ctx, config=EngineConfig(max_ticks=1))
        # First step uses tick 0 → advance to tick 1 which == max_ticks
        result = engine.step()
        assert result is True

    def test_step_returns_true_at_time_limit(self) -> None:
        # 1-hour campaign with 1-hour tick → done after 1 step
        cfg = _minimal_config(duration_hours=1.0)
        ctx = _make_ctx(config=cfg, tick_s=3600.0)
        engine = SimulationEngine(ctx)
        result = engine.step()
        assert result is True

    def test_multiple_steps_track_progress(self) -> None:
        ctx = _make_ctx(config=_minimal_config(duration_hours=24.0))
        engine = SimulationEngine(ctx)
        for _ in range(5):
            engine.step()
        assert ctx.clock.tick_count == 5

    def test_step_updates_environment(self) -> None:
        # Create a mock weather engine to verify it gets called
        called = {"update": False}

        class _MockWeather:
            def update(self, dt: float) -> None:
                called["update"] = True

        ctx = _make_ctx(config=_minimal_config(duration_hours=24.0))
        ctx.weather_engine = _MockWeather()
        engine = SimulationEngine(ctx)
        engine.step()
        assert called["update"] is True

    def test_step_with_recorder(self) -> None:
        ctx = _make_ctx(config=_minimal_config(duration_hours=24.0))
        rec = SimulationRecorder(ctx.event_bus)
        rec.start()
        engine = SimulationEngine(ctx, recorder=rec)
        engine.step()
        # Recorder should have recorded tick 1
        assert rec._current_tick == 1


# ---------------------------------------------------------------------------
# Resolution switching
# ---------------------------------------------------------------------------


class TestResolutionSwitching:
    """Tick resolution management."""

    def test_starts_strategic(self) -> None:
        ctx = _make_ctx()
        engine = SimulationEngine(ctx)
        assert engine.resolution == TickResolution.STRATEGIC

    def test_switches_to_tactical_on_battle(self) -> None:
        ctx = _make_ctx(config=_minimal_config(duration_hours=24.0))
        engine = SimulationEngine(ctx)
        # Manually create a battle
        battle = BattleContext(
            battle_id="test_battle",
            start_tick=0,
            start_time=TS,
            involved_sides=["blue", "red"],
        )
        engine.battle_manager._battles["test_battle"] = battle
        engine.step()
        assert engine.resolution == TickResolution.TACTICAL

    def test_tactical_tick_duration(self) -> None:
        ctx = _make_ctx(config=_minimal_config(duration_hours=24.0))
        engine = SimulationEngine(ctx)
        # Create active battle
        battle = BattleContext(
            battle_id="t", start_tick=0, start_time=TS,
            involved_sides=["blue", "red"],
        )
        engine.battle_manager._battles["t"] = battle
        engine.step()
        assert ctx.clock.tick_duration.total_seconds() == 5.0

    def test_returns_to_operational_after_battle(self) -> None:
        ctx = _make_ctx(config=_minimal_config(duration_hours=24.0))
        engine = SimulationEngine(ctx)
        # Create and terminate a battle
        battle = BattleContext(
            battle_id="t", start_tick=0, start_time=TS,
            involved_sides=["blue", "red"],
        )
        engine.battle_manager._battles["t"] = battle
        engine.step()  # Goes TACTICAL
        assert engine.resolution == TickResolution.TACTICAL
        battle.active = False
        engine.step()  # Goes OPERATIONAL
        assert engine.resolution == TickResolution.OPERATIONAL

    def test_returns_to_strategic_from_operational(self) -> None:
        ctx = _make_ctx(config=_minimal_config(duration_hours=24.0))
        engine = SimulationEngine(ctx)
        # Force operational
        engine._set_resolution(TickResolution.OPERATIONAL)
        engine.step()
        assert engine.resolution == TickResolution.STRATEGIC

    def test_custom_tick_durations(self) -> None:
        cfg = _minimal_config(
            duration_hours=24.0,
            tick_resolution=TickResolutionConfig(
                strategic_s=1800.0, operational_s=60.0, tactical_s=2.0,
            ),
        )
        ctx = _make_ctx(config=cfg)
        engine = SimulationEngine(ctx)
        assert ctx.clock.tick_duration.total_seconds() == 1800.0

    def test_resolution_doesnt_change_without_battles(self) -> None:
        ctx = _make_ctx(config=_minimal_config(duration_hours=24.0))
        engine = SimulationEngine(ctx)
        for _ in range(5):
            engine.step()
        assert engine.resolution == TickResolution.STRATEGIC

    def test_set_resolution_noop_when_same(self) -> None:
        ctx = _make_ctx(config=_minimal_config(duration_hours=24.0))
        engine = SimulationEngine(ctx)
        engine._set_resolution(TickResolution.STRATEGIC)
        assert engine.resolution == TickResolution.STRATEGIC


# ---------------------------------------------------------------------------
# Strategic tick
# ---------------------------------------------------------------------------


class TestStrategicTick:
    """Strategic tick execution via campaign manager."""

    def test_strategic_runs_campaign_update(self) -> None:
        ctx = _make_ctx(config=_minimal_config(duration_hours=24.0))
        engine = SimulationEngine(ctx)
        # Should not raise
        engine.step()

    def test_engagement_detection_triggers_battle(self) -> None:
        # Blue and red units within engagement range
        blue = [_make_unit("b1", Position(0, 0, 0), "blue")]
        red = [_make_unit("r1", Position(1000, 0, 0), "red")]
        cfg = _minimal_config(duration_hours=24.0)
        ctx = _make_ctx(blue_units=blue, red_units=red, config=cfg)
        engine = SimulationEngine(ctx, campaign_config=CampaignConfig(engagement_detection_range_m=5000))
        engine.step()
        assert len(engine.battle_manager.active_battles) >= 1
        assert engine.resolution == TickResolution.TACTICAL


# ---------------------------------------------------------------------------
# Tactical tick
# ---------------------------------------------------------------------------


class TestTacticalTick:
    """Tactical tick execution via battle manager."""

    def test_battle_ticks_increment(self) -> None:
        ctx = _make_ctx(config=_minimal_config(duration_hours=24.0))
        engine = SimulationEngine(ctx)
        battle = BattleContext(
            battle_id="t", start_tick=0, start_time=TS,
            involved_sides=["blue", "red"],
        )
        engine.battle_manager._battles["t"] = battle
        engine.step()
        assert battle.ticks_executed >= 1

    def test_battle_terminates_on_no_active_units(self) -> None:
        # Blue units only, no red → should terminate
        blue = [_make_unit("b1", Position(0, 0, 0), "blue")]
        ctx = _make_ctx(blue_units=blue, config=_minimal_config(duration_hours=24.0))
        engine = SimulationEngine(ctx)
        battle = BattleContext(
            battle_id="t", start_tick=0, start_time=TS,
            involved_sides=["blue", "red"],
        )
        engine.battle_manager._battles["t"] = battle
        engine.step()
        assert battle.active is False

    def test_battle_terminates_on_max_ticks(self) -> None:
        blue = [_make_unit("b1", Position(0, 0, 0), "blue")]
        red = [_make_unit("r1", Position(100, 0, 0), "red")]
        ctx = _make_ctx(blue_units=blue, red_units=red,
                        config=_minimal_config(duration_hours=24.0))
        engine = SimulationEngine(
            ctx,
            battle_config=BattleConfig(max_ticks_per_battle=1),
        )
        battle = BattleContext(
            battle_id="t", start_tick=0, start_time=TS,
            involved_sides=["blue", "red"],
        )
        engine.battle_manager._battles["t"] = battle
        engine.step()
        assert battle.active is False


# ---------------------------------------------------------------------------
# Victory evaluation
# ---------------------------------------------------------------------------


class TestVictoryEvaluation:
    """Victory condition integration."""

    def test_no_victory_evaluator_continues(self) -> None:
        ctx = _make_ctx(config=_minimal_config(duration_hours=24.0))
        engine = SimulationEngine(ctx, victory_evaluator=None)
        assert engine.step() is False

    def test_time_expired_victory(self) -> None:
        cfg = _minimal_config(
            duration_hours=1.0,
            victory_conditions=[
                VictoryConditionConfig(
                    type="time_expired", side="draw",
                    params={"max_duration_s": 3600},
                ),
            ],
        )
        ctx = _make_ctx(config=cfg, tick_s=3600.0)
        ve = VictoryEvaluator(
            objectives=[], conditions=cfg.victory_conditions,
            event_bus=ctx.event_bus, max_duration_s=3600,
        )
        engine = SimulationEngine(ctx, victory_evaluator=ve)
        result = engine.step()
        assert result is True

    def test_force_destroyed_victory(self) -> None:
        cfg = _minimal_config(
            duration_hours=24.0,
            victory_conditions=[
                VictoryConditionConfig(type="force_destroyed", side="blue"),
            ],
        )
        # All red units destroyed
        red_units: list[Unit] = []
        for i in range(10):
            u = _make_unit(f"r{i}", Position(5000 + i * 10, 0, 0), "red")
            object.__setattr__(u, "status", UnitStatus.DESTROYED)
            red_units.append(u)
        blue_units = [_make_unit("b1", Position(0, 0, 0), "blue")]
        ctx = _make_ctx(blue_units=blue_units, red_units=red_units, config=cfg)
        ve = VictoryEvaluator(
            objectives=[], conditions=cfg.victory_conditions,
            event_bus=ctx.event_bus,
        )
        engine = SimulationEngine(ctx, victory_evaluator=ve)
        result = engine.step()
        assert result is True

    def test_territory_control_victory(self) -> None:
        cfg = _minimal_config(
            duration_hours=24.0,
            victory_conditions=[
                VictoryConditionConfig(
                    type="territory_control", side="blue",
                    params={"threshold": 1.0},
                ),
            ],
        )
        # Blue unit right on the objective
        blue = [_make_unit("b1", Position(100, 100, 0), "blue")]
        ctx = _make_ctx(blue_units=blue, config=cfg)
        obj = ObjectiveState(
            objective_id="obj1", position=Position(100, 100, 0),
            radius_m=500,
        )
        ve = VictoryEvaluator(
            objectives=[obj], conditions=cfg.victory_conditions,
            event_bus=ctx.event_bus,
        )
        engine = SimulationEngine(ctx, victory_evaluator=ve)
        result = engine.step()
        assert result is True


# ---------------------------------------------------------------------------
# Recorder integration
# ---------------------------------------------------------------------------


class TestRecorderIntegration:
    """Event recorder integration with engine."""

    def test_recorder_captures_ticks(self) -> None:
        ctx = _make_ctx(config=_minimal_config(duration_hours=24.0))
        rec = SimulationRecorder(ctx.event_bus)
        engine = SimulationEngine(ctx, recorder=rec)
        rec.start()
        for _ in range(3):
            engine.step()
        assert rec._current_tick == 3

    def test_recorder_takes_snapshots(self) -> None:
        ctx = _make_ctx(config=_minimal_config(duration_hours=24.0))
        rec = SimulationRecorder(ctx.event_bus)
        cfg = EngineConfig(snapshot_interval_ticks=2)
        engine = SimulationEngine(ctx, config=cfg, recorder=rec)
        rec.start()
        for _ in range(4):
            engine.step()
        assert len(rec.snapshots) >= 2

    def test_run_starts_and_stops_recorder(self) -> None:
        cfg = _minimal_config(duration_hours=0.5)
        ctx = _make_ctx(config=cfg, tick_s=1800.0)
        rec = SimulationRecorder(ctx.event_bus)
        engine = SimulationEngine(ctx, recorder=rec)
        engine.run()
        assert rec._subscribed is False  # stopped after run


# ---------------------------------------------------------------------------
# Full run
# ---------------------------------------------------------------------------


class TestFullRun:
    """SimulationEngine.run() — run to completion."""

    def test_run_to_time_limit(self) -> None:
        cfg = _minimal_config(duration_hours=2.0)
        ctx = _make_ctx(config=cfg, tick_s=3600.0)
        engine = SimulationEngine(ctx)
        result = engine.run()
        assert result.ticks_executed >= 2
        assert result.victory_result.game_over is True

    def test_run_with_max_ticks(self) -> None:
        cfg = _minimal_config(duration_hours=1000.0)
        ctx = _make_ctx(config=cfg, tick_s=3600.0)
        engine = SimulationEngine(ctx, config=EngineConfig(max_ticks=5))
        result = engine.run()
        assert result.ticks_executed == 5
        assert result.victory_result.condition_type == "max_ticks"

    def test_run_result_has_duration(self) -> None:
        cfg = _minimal_config(duration_hours=1.0)
        ctx = _make_ctx(config=cfg, tick_s=3600.0)
        engine = SimulationEngine(ctx)
        result = engine.run()
        assert result.duration_s > 0

    def test_run_with_victory_evaluator(self) -> None:
        cfg = _minimal_config(
            duration_hours=24.0,
            victory_conditions=[
                VictoryConditionConfig(
                    type="time_expired", side="draw",
                    params={"max_duration_s": 7200},
                ),
            ],
        )
        ctx = _make_ctx(config=cfg, tick_s=3600.0)
        ve = VictoryEvaluator(
            objectives=[], conditions=cfg.victory_conditions,
            event_bus=ctx.event_bus, max_duration_s=7200,
        )
        engine = SimulationEngine(ctx, victory_evaluator=ve)
        result = engine.run()
        assert result.victory_result.game_over is True
        assert result.victory_result.condition_type == "time_expired"

    def test_deterministic_tick_count(self) -> None:
        """Same config → same tick count."""
        def _run() -> int:
            cfg = _minimal_config(duration_hours=3.0)
            ctx = _make_ctx(config=cfg, tick_s=3600.0)
            engine = SimulationEngine(ctx)
            return engine.run().ticks_executed

        t1 = _run()
        t2 = _run()
        assert t1 == t2

    def test_run_returns_result_type(self) -> None:
        cfg = _minimal_config(duration_hours=1.0)
        ctx = _make_ctx(config=cfg, tick_s=3600.0)
        engine = SimulationEngine(ctx)
        result = engine.run()
        assert isinstance(result, SimulationRunResult)


# ---------------------------------------------------------------------------
# Checkpoint / restore
# ---------------------------------------------------------------------------


class TestCheckpointRestore:
    """Engine state persistence."""

    def test_get_state_contains_keys(self) -> None:
        ctx = _make_ctx()
        engine = SimulationEngine(ctx)
        state = engine.get_state()
        assert "resolution" in state
        assert "context" in state
        assert "campaign" in state
        assert "battle" in state

    def test_set_state_restores_resolution(self) -> None:
        ctx = _make_ctx(config=_minimal_config(duration_hours=24.0))
        engine = SimulationEngine(ctx)
        engine._set_resolution(TickResolution.TACTICAL)
        state = engine.get_state()

        ctx2 = _make_ctx(config=_minimal_config(duration_hours=24.0))
        engine2 = SimulationEngine(ctx2)
        engine2.set_state(state)
        assert engine2.resolution == TickResolution.TACTICAL

    def test_checkpoint_restore_round_trip(self) -> None:
        cfg = _minimal_config(duration_hours=24.0)
        ctx = _make_ctx(config=cfg, tick_s=3600.0)
        engine = SimulationEngine(ctx)
        engine.step()
        engine.step()
        data = engine.checkpoint()

        ctx2 = _make_ctx(config=cfg, tick_s=3600.0)
        engine2 = SimulationEngine(ctx2)
        engine2.restore(data)
        assert ctx2.clock.tick_count == 2

    def test_auto_checkpoint_at_interval(self) -> None:
        cfg = _minimal_config(duration_hours=24.0)
        ctx = _make_ctx(config=cfg, tick_s=3600.0)
        engine = SimulationEngine(
            ctx, config=EngineConfig(checkpoint_interval_ticks=2),
        )
        for _ in range(4):
            engine.step()
        assert len(engine._checkpoints) >= 2

    def test_no_auto_checkpoint_when_disabled(self) -> None:
        cfg = _minimal_config(duration_hours=24.0)
        ctx = _make_ctx(config=cfg, tick_s=3600.0)
        engine = SimulationEngine(
            ctx, config=EngineConfig(checkpoint_interval_ticks=0),
        )
        for _ in range(5):
            engine.step()
        assert len(engine._checkpoints) == 0

    def test_checkpoint_includes_victory_state(self) -> None:
        ctx = _make_ctx(config=_minimal_config(duration_hours=24.0))
        obj = ObjectiveState("obj1", Position(0, 0, 0), 500.0)
        ve = VictoryEvaluator(
            objectives=[obj], conditions=[], event_bus=ctx.event_bus,
        )
        engine = SimulationEngine(ctx, victory_evaluator=ve)
        state = engine.get_state()
        assert "victory" in state

    def test_checkpoint_includes_recorder_state(self) -> None:
        ctx = _make_ctx(config=_minimal_config(duration_hours=24.0))
        rec = SimulationRecorder(ctx.event_bus)
        engine = SimulationEngine(ctx, recorder=rec)
        state = engine.get_state()
        assert "recorder" in state

    def test_bytes_serialization_round_trip(self) -> None:
        cfg = _minimal_config(duration_hours=24.0)
        ctx = _make_ctx(config=cfg, tick_s=3600.0)
        engine = SimulationEngine(ctx)
        engine.step()
        data = engine.checkpoint()
        assert isinstance(data, bytes)
        assert len(data) > 0

        ctx2 = _make_ctx(config=cfg, tick_s=3600.0)
        engine2 = SimulationEngine(ctx2)
        engine2.restore(data)
        assert ctx2.clock.tick_count == 1


# ---------------------------------------------------------------------------
# Strategic → tactical transitions
# ---------------------------------------------------------------------------


class TestStratTactTransitions:
    """Full strategic → tactical → strategic resolution cycling."""

    def test_detection_triggers_tactical(self) -> None:
        blue = [_make_unit("b1", Position(0, 0, 0), "blue")]
        red = [_make_unit("r1", Position(500, 0, 0), "red")]
        cfg = _minimal_config(duration_hours=24.0)
        ctx = _make_ctx(blue_units=blue, red_units=red, config=cfg)
        engine = SimulationEngine(
            ctx,
            campaign_config=CampaignConfig(engagement_detection_range_m=5000),
        )
        engine.step()
        assert engine.resolution == TickResolution.TACTICAL

    def test_battle_end_returns_to_operational(self) -> None:
        blue = [_make_unit("b1", Position(0, 0, 0), "blue")]
        red = [_make_unit("r1", Position(500, 0, 0), "red")]
        cfg = _minimal_config(duration_hours=24.0)
        ctx = _make_ctx(blue_units=blue, red_units=red, config=cfg)
        engine = SimulationEngine(
            ctx,
            campaign_config=CampaignConfig(engagement_detection_range_m=5000),
        )
        engine.step()  # STRATEGIC → TACTICAL (battle detected)
        # Deactivate all battles
        for b in engine.battle_manager._battles.values():
            b.active = False
        engine.step()  # TACTICAL → OPERATIONAL
        assert engine.resolution == TickResolution.OPERATIONAL

    def test_full_cycle_back_to_strategic(self) -> None:
        ctx = _make_ctx(config=_minimal_config(duration_hours=24.0))
        engine = SimulationEngine(ctx)
        # Force through the cycle
        engine._set_resolution(TickResolution.TACTICAL)
        engine.step()  # no active battles → OPERATIONAL
        assert engine.resolution == TickResolution.OPERATIONAL
        engine.step()  # OPERATIONAL → STRATEGIC
        assert engine.resolution == TickResolution.STRATEGIC


# ---------------------------------------------------------------------------
# Reinforcements
# ---------------------------------------------------------------------------


class TestReinforcements:
    """Reinforcement scheduling through engine."""

    def test_reinforcements_via_campaign_manager(self) -> None:
        cfg = _minimal_config(
            duration_hours=24.0,
            reinforcements=[
                ReinforcementConfig(
                    side="blue", arrival_time_s=3600,
                    units=[ReinforcementUnitConfig(unit_type="m1a2")],
                ),
            ],
        )
        ctx = _make_ctx(config=cfg, tick_s=3600.0)
        engine = SimulationEngine(ctx)
        engine.campaign_manager.set_reinforcements(cfg.reinforcements)
        # After 1 tick (3600s), reinforcements should arrive (if loader available)
        # Without loader, they won't spawn but should not crash
        engine.step()


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases and error conditions."""

    def test_empty_units_no_crash(self) -> None:
        ctx = _make_ctx()
        engine = SimulationEngine(ctx)
        engine.step()

    def test_zero_duration_campaign(self) -> None:
        # 0.1 hour campaign → finishes immediately with strategic tick
        cfg = _minimal_config(duration_hours=0.1)
        ctx = _make_ctx(config=cfg, tick_s=3600.0)
        engine = SimulationEngine(ctx)
        result = engine.run()
        assert result.victory_result.game_over is True

    def test_environment_engine_failure_doesnt_crash(self) -> None:
        class _BrokenWeather:
            def update(self, dt: float) -> None:
                raise RuntimeError("Weather broken!")

        ctx = _make_ctx(config=_minimal_config(duration_hours=24.0))
        ctx.weather_engine = _BrokenWeather()
        engine = SimulationEngine(ctx)
        engine.step()  # Should not raise

    def test_multiple_battles_simultaneously(self) -> None:
        ctx = _make_ctx(config=_minimal_config(duration_hours=24.0))
        engine = SimulationEngine(ctx)
        b1 = BattleContext(
            battle_id="b1", start_tick=0, start_time=TS,
            involved_sides=["blue", "red"],
        )
        b2 = BattleContext(
            battle_id="b2", start_tick=0, start_time=TS,
            involved_sides=["blue", "red"],
        )
        engine.battle_manager._battles["b1"] = b1
        engine.battle_manager._battles["b2"] = b2
        engine.step()
        # Both battles should have been ticked
        # (they'll terminate since no units, but should not crash)

    def test_very_short_campaign(self) -> None:
        cfg = _minimal_config(duration_hours=0.01)
        ctx = _make_ctx(config=cfg, tick_s=100.0)
        engine = SimulationEngine(ctx)
        result = engine.run()
        assert result.ticks_executed >= 1

    def test_long_strategic_ticks(self) -> None:
        cfg = _minimal_config(
            duration_hours=24.0,
            tick_resolution=TickResolutionConfig(strategic_s=7200.0),
        )
        ctx = _make_ctx(config=cfg)
        engine = SimulationEngine(ctx)
        assert ctx.clock.tick_duration.total_seconds() == 7200.0
        engine.step()
        assert ctx.clock.elapsed.total_seconds() == 7200.0
