"""Integration tests for Phase 9: Simulation Orchestration.

End-to-end tests exercising the full simulation loop: scenario loading,
campaign management, battle detection and resolution, victory evaluation,
event recording, checkpoint/restore, reinforcements, and metrics extraction.

Uses both full ScenarioLoader paths (when YAML data is available) and
lightweight mock contexts for fast, deterministic testing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.morale.state import MoraleState
from stochastic_warfare.simulation.battle import (
    BattleConfig,
    BattleContext,
    BattleManager,
    BattleResult,
)
from stochastic_warfare.simulation.campaign import CampaignConfig, CampaignManager
from stochastic_warfare.simulation.engine import (
    EngineConfig,
    SimulationEngine,
    SimulationRunResult,
    TickResolution,
)
from stochastic_warfare.simulation.metrics import CampaignMetrics, CampaignSummary
from stochastic_warfare.simulation.recorder import (
    RecorderConfig,
    SimulationRecorder,
)
from stochastic_warfare.simulation.scenario import (
    CampaignScenarioConfig,
    ReinforcementConfig,
    ReinforcementUnitConfig,
    ScenarioLoader,
    SideConfig,
    SimulationContext,
    TerrainConfig,
    TickResolutionConfig,
    VictoryConditionConfig,
)
from stochastic_warfare.simulation.victory import (
    ObjectiveState,
    VictoryDeclaredEvent,
    VictoryEvaluator,
    VictoryEvaluatorConfig,
    VictoryResult,
)

from tests.conftest import DEFAULT_SEED, POS_ORIGIN, TS, make_clock, make_rng

# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR = _PROJECT_ROOT / "data"
_TEST_SCENARIO = _DATA_DIR / "scenarios" / "test_campaign" / "scenario.yaml"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_unit(
    eid: str,
    pos: Position,
    side: str = "blue",
    *,
    status: UnitStatus = UnitStatus.ACTIVE,
    speed: float = 0.0,
) -> Unit:
    """Create a minimal Unit with the given properties."""
    u = Unit(entity_id=eid, position=pos)
    object.__setattr__(u, "side", side)
    object.__setattr__(u, "status", status)
    object.__setattr__(u, "speed", speed)
    return u


def _minimal_config(**overrides: Any) -> CampaignScenarioConfig:
    """Create a minimal valid CampaignScenarioConfig."""
    defaults: dict[str, Any] = {
        "name": "IntegrationTest",
        "date": "2024-06-15",
        "duration_hours": 24.0,
        "terrain": TerrainConfig(width_m=10000, height_m=10000),
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
    """Create a lightweight SimulationContext for integration tests."""
    cfg = config or _minimal_config()
    bus = EventBus()
    rng_mgr = RNGManager(seed)
    clock = SimulationClock(
        start=TS,
        tick_duration=timedelta(seconds=tick_s),
    )
    return SimulationContext(
        config=cfg,
        clock=clock,
        rng_manager=rng_mgr,
        event_bus=bus,
        units_by_side={
            "blue": blue_units if blue_units is not None else [],
            "red": red_units if red_units is not None else [],
        },
    )


def _scenario_data_available() -> bool:
    """Return True if the test campaign YAML and required unit data exist."""
    return _TEST_SCENARIO.exists() and (_DATA_DIR / "units").exists()


# ---------------------------------------------------------------------------
# Test 1: Full scenario load + single strategic tick
# ---------------------------------------------------------------------------


class TestScenarioLoadStrategicTick:
    """Load a full scenario from YAML and execute one strategic tick."""

    @pytest.mark.skipif(
        not _scenario_data_available(),
        reason="Test campaign YAML / unit data not found",
    )
    def test_full_scenario_load_and_strategic_tick(self) -> None:
        loader = ScenarioLoader(_DATA_DIR)
        ctx = loader.load(_TEST_SCENARIO, seed=42)

        assert "blue" in ctx.units_by_side
        assert "red" in ctx.units_by_side
        assert len(ctx.units_by_side["blue"]) == 4
        assert len(ctx.units_by_side["red"]) == 6
        assert ctx.heightmap is not None

        # The test scenario has blue at x=100 and red at x=9900 (9800m apart).
        # Default engagement detection range is 15000m, so a battle will be
        # detected on the first strategic tick.  Use a shorter range to keep
        # forces from engaging immediately.
        engine = SimulationEngine(
            ctx,
            campaign_config=CampaignConfig(engagement_detection_range_m=5000),
        )
        done = engine.step()
        assert done is False
        assert ctx.clock.tick_count == 1
        assert engine.resolution == TickResolution.STRATEGIC

    @pytest.mark.skipif(
        not _scenario_data_available(),
        reason="Test campaign YAML / unit data not found",
    )
    def test_full_scenario_clock_advances_correctly(self) -> None:
        loader = ScenarioLoader(_DATA_DIR)
        ctx = loader.load(_TEST_SCENARIO, seed=42)
        engine = SimulationEngine(ctx)
        engine.step()
        # Strategic tick is 3600s per the YAML
        assert ctx.clock.elapsed.total_seconds() == pytest.approx(3600.0)


# ---------------------------------------------------------------------------
# Test 2: Full scenario load + single tactical tick (via battle detection)
# ---------------------------------------------------------------------------


class TestScenarioLoadTacticalTick:
    """Force a battle to start and verify tactical tick execution."""

    def test_battle_detection_triggers_tactical(self) -> None:
        """Close-range opposing forces trigger a battle and tactical ticks."""
        blue = [_make_unit("b1", Position(100, 5000, 0), "blue")]
        red = [_make_unit("r1", Position(500, 5000, 0), "red")]
        cfg = _minimal_config(duration_hours=24.0)
        ctx = _make_ctx(blue_units=blue, red_units=red, config=cfg)

        engine = SimulationEngine(
            ctx,
            campaign_config=CampaignConfig(engagement_detection_range_m=5000),
        )
        engine.step()

        assert engine.resolution == TickResolution.TACTICAL
        assert len(engine.battle_manager.active_battles) >= 1
        # Clock should have switched to tactical tick duration
        assert ctx.clock.tick_duration.total_seconds() == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# Test 3: Campaign with one battle (detect -> resolve -> resume strategic)
# ---------------------------------------------------------------------------


class TestSingleBattleCampaign:
    """Detect a battle, let it terminate, and resume strategic ticks."""

    def test_detect_resolve_resume(self) -> None:
        blue = [_make_unit("b1", Position(100, 5000, 0), "blue")]
        red = [_make_unit("r1", Position(500, 5000, 0), "red")]
        cfg = _minimal_config(duration_hours=24.0)
        ctx = _make_ctx(blue_units=blue, red_units=red, config=cfg)

        engine = SimulationEngine(
            ctx,
            campaign_config=CampaignConfig(engagement_detection_range_m=5000),
        )

        # Step 1: detect battle
        engine.step()
        assert engine.resolution == TickResolution.TACTICAL
        battles = engine.battle_manager.active_battles
        assert len(battles) >= 1

        # Terminate the battle manually (one side eliminated)
        object.__setattr__(red[0], "status", UnitStatus.DESTROYED)

        # Step until battle resolves
        for _ in range(10):
            done = engine.step()
            if engine.resolution != TickResolution.TACTICAL:
                break

        # Should have stepped back from tactical
        assert engine.resolution in (TickResolution.OPERATIONAL, TickResolution.STRATEGIC)

        # Run one more step to get back to strategic
        if engine.resolution == TickResolution.OPERATIONAL:
            engine.step()
            assert engine.resolution == TickResolution.STRATEGIC


# ---------------------------------------------------------------------------
# Test 4: Multi-step campaign to time expiration
# ---------------------------------------------------------------------------


class TestCampaignTimeExpiration:
    """Run a short campaign to the time limit."""

    def test_campaign_runs_to_time_limit(self) -> None:
        cfg = _minimal_config(duration_hours=3.0)
        ctx = _make_ctx(config=cfg, tick_s=3600.0)
        engine = SimulationEngine(ctx)
        result = engine.run()

        assert result.victory_result.game_over is True
        assert result.ticks_executed >= 3
        assert result.duration_s >= 3 * 3600.0

    def test_time_expired_victory_condition(self) -> None:
        cfg = _minimal_config(
            duration_hours=2.0,
            victory_conditions=[
                VictoryConditionConfig(
                    type="time_expired", side="draw",
                    params={"max_duration_s": 7200},
                ),
            ],
        )
        ctx = _make_ctx(config=cfg, tick_s=3600.0)
        ve = VictoryEvaluator(
            objectives=[],
            conditions=cfg.victory_conditions,
            event_bus=ctx.event_bus,
            max_duration_s=7200,
        )
        engine = SimulationEngine(ctx, victory_evaluator=ve)
        result = engine.run()

        assert result.victory_result.game_over is True
        assert result.victory_result.condition_type == "time_expired"


# ---------------------------------------------------------------------------
# Test 5: Checkpoint at mid-campaign, restore
# ---------------------------------------------------------------------------


class TestCheckpointRestore:
    """Checkpoint mid-campaign, restore, and verify state consistency."""

    def test_checkpoint_and_restore_mid_campaign(self) -> None:
        cfg = _minimal_config(duration_hours=10.0)
        blue = [_make_unit("b1", Position(100, 5000, 0), "blue")]
        red = [_make_unit("r1", Position(9900, 5000, 0), "red")]
        ctx = _make_ctx(blue_units=blue, red_units=red, config=cfg, tick_s=3600.0)

        rec = SimulationRecorder(ctx.event_bus)
        engine = SimulationEngine(ctx, recorder=rec)

        # Run 3 ticks
        for _ in range(3):
            engine.step()
        assert ctx.clock.tick_count == 3

        # Checkpoint
        checkpoint_data = engine.checkpoint()
        assert isinstance(checkpoint_data, bytes)
        assert len(checkpoint_data) > 0

        # Create fresh engine and restore
        ctx2 = _make_ctx(
            blue_units=[_make_unit("b1", Position(100, 5000, 0), "blue")],
            red_units=[_make_unit("r1", Position(9900, 5000, 0), "red")],
            config=cfg,
            tick_s=3600.0,
        )
        rec2 = SimulationRecorder(ctx2.event_bus)
        engine2 = SimulationEngine(ctx2, recorder=rec2)
        engine2.restore(checkpoint_data)

        assert ctx2.clock.tick_count == 3
        assert engine2.resolution == engine.resolution

    def test_checkpoint_preserves_victory_state(self) -> None:
        cfg = _minimal_config(duration_hours=10.0)
        ctx = _make_ctx(config=cfg, tick_s=3600.0)

        obj = ObjectiveState("obj_test", Position(5000, 5000, 0), 500.0)
        obj.controlling_side = "blue"
        ve = VictoryEvaluator(
            objectives=[obj], conditions=[], event_bus=ctx.event_bus,
        )
        engine = SimulationEngine(ctx, victory_evaluator=ve)
        engine.step()

        state = engine.get_state()
        assert "victory" in state
        assert state["victory"]["objectives"]["obj_test"]["controlling_side"] == "blue"


# ---------------------------------------------------------------------------
# Test 6: Reinforcement arrival during campaign
# ---------------------------------------------------------------------------


class TestReinforcementArrival:
    """Reinforcements arrive at the scheduled time."""

    def test_reinforcement_schedule_fires(self) -> None:
        cfg = _minimal_config(
            duration_hours=10.0,
            reinforcements=[
                ReinforcementConfig(
                    side="blue",
                    arrival_time_s=3600,
                    units=[ReinforcementUnitConfig(unit_type="m1a2", count=2)],
                    position=[200, 5000],
                ),
            ],
        )
        blue = [_make_unit("b1", Position(100, 5000, 0), "blue")]
        red = [_make_unit("r1", Position(9900, 5000, 0), "red")]
        ctx = _make_ctx(blue_units=blue, red_units=red, config=cfg, tick_s=3600.0)
        engine = SimulationEngine(ctx)
        engine.campaign_manager.set_reinforcements(cfg.reinforcements)

        initial_blue_count = len(ctx.units_by_side["blue"])
        assert initial_blue_count == 1

        # After 1 tick (3600s), reinforcements should be checked
        # Without unit_loader, no units actually spawn, but the
        # entry should be marked as arrived
        engine.step()

        # The reinforcement entry is marked arrived even without a loader
        entries = engine.campaign_manager._reinforcements
        assert len(entries) == 1
        assert entries[0].arrived is True

    def test_reinforcement_not_arrived_before_time(self) -> None:
        cfg = _minimal_config(
            duration_hours=10.0,
            reinforcements=[
                ReinforcementConfig(
                    side="blue",
                    arrival_time_s=7200,
                    units=[ReinforcementUnitConfig(unit_type="m1a2")],
                    position=[200, 5000],
                ),
            ],
        )
        ctx = _make_ctx(config=cfg, tick_s=3600.0)
        engine = SimulationEngine(ctx)
        engine.campaign_manager.set_reinforcements(cfg.reinforcements)

        # After 1 tick (3600s), reinforcement at 7200s has not arrived
        engine.step()
        entries = engine.campaign_manager._reinforcements
        assert entries[0].arrived is False

        # After 2nd tick (7200s), it should arrive
        engine.step()
        assert entries[0].arrived is True

    @pytest.mark.skipif(
        not _scenario_data_available(),
        reason="Test campaign YAML / unit data not found",
    )
    def test_reinforcement_with_real_loader(self) -> None:
        """With real scenario data, reinforcements spawn actual units."""
        loader = ScenarioLoader(_DATA_DIR)
        ctx = loader.load(_TEST_SCENARIO, seed=42)

        # Use short engagement range to prevent battle detection (units are
        # 9800m apart), keeping strategic ticks at 3600s so we reach 7200s
        # in just 2 ticks.
        engine = SimulationEngine(
            ctx,
            campaign_config=CampaignConfig(engagement_detection_range_m=5000),
        )
        engine.campaign_manager.set_reinforcements(ctx.config.reinforcements)

        initial_blue = len(ctx.units_by_side["blue"])

        # Advance past 7200s (reinforcement time per YAML)
        # 3 strategic ticks at 3600s = 10800s > 7200s
        for _ in range(3):
            engine.step()

        # Should have spawned 2 more blue m1a2 units
        assert len(ctx.units_by_side["blue"]) == initial_blue + 2


# ---------------------------------------------------------------------------
# Test 7: Objective control changing hands
# ---------------------------------------------------------------------------


class TestObjectiveControl:
    """Objective control updates based on unit proximity."""

    def test_objective_changes_hands(self) -> None:
        obj = ObjectiveState(
            objective_id="obj_alpha",
            position=Position(5000, 5000, 0),
            radius_m=500,
        )
        cfg = _minimal_config(
            duration_hours=24.0,
            victory_conditions=[
                VictoryConditionConfig(
                    type="territory_control", side="blue",
                    params={"threshold": 1.0},
                ),
            ],
        )

        # Red starts on objective
        blue = [_make_unit("b1", Position(100, 5000, 0), "blue")]
        red = [_make_unit("r1", Position(5000, 5000, 0), "red")]
        ctx = _make_ctx(blue_units=blue, red_units=red, config=cfg)

        ve = VictoryEvaluator(
            objectives=[obj],
            conditions=cfg.victory_conditions,
            event_bus=ctx.event_bus,
        )
        engine = SimulationEngine(ctx, victory_evaluator=ve)

        # Step 1: red controls objective
        engine.step()
        obj_state = ve.get_objective_state("obj_alpha")
        assert obj_state is not None
        assert obj_state.controlling_side == "red"

        # Move red away, move blue onto objective
        object.__setattr__(red[0], "position", Position(9000, 5000, 0))
        object.__setattr__(blue[0], "position", Position(5000, 5000, 0))

        engine.step()
        assert obj_state.controlling_side == "blue"

    def test_contested_objective(self) -> None:
        obj = ObjectiveState(
            objective_id="obj_bravo",
            position=Position(5000, 5000, 0),
            radius_m=1000,
        )
        blue = [_make_unit("b1", Position(5000, 5000, 0), "blue")]
        red = [_make_unit("r1", Position(5100, 5000, 0), "red")]
        cfg = _minimal_config(duration_hours=24.0)
        ctx = _make_ctx(blue_units=blue, red_units=red, config=cfg)

        ve = VictoryEvaluator(
            objectives=[obj],
            conditions=[],
            event_bus=ctx.event_bus,
        )
        engine = SimulationEngine(ctx, victory_evaluator=ve)
        engine.step()

        assert obj.contested is True


# ---------------------------------------------------------------------------
# Test 8: Victory condition evaluation with multiple conditions
# ---------------------------------------------------------------------------


class TestMultipleVictoryConditions:
    """Multiple victory conditions - first satisfied wins."""

    def test_force_destroyed_before_time_expired(self) -> None:
        cfg = _minimal_config(
            duration_hours=24.0,
            victory_conditions=[
                VictoryConditionConfig(type="force_destroyed", side="blue"),
                VictoryConditionConfig(
                    type="time_expired", side="draw",
                    params={"max_duration_s": 86400},
                ),
            ],
        )
        # All red units destroyed
        red_units = [
            _make_unit(f"r{i}", Position(5000 + i * 10, 5000, 0), "red",
                       status=UnitStatus.DESTROYED)
            for i in range(10)
        ]
        blue_units = [_make_unit("b1", Position(100, 5000, 0), "blue")]
        ctx = _make_ctx(blue_units=blue_units, red_units=red_units, config=cfg)

        ve = VictoryEvaluator(
            objectives=[],
            conditions=cfg.victory_conditions,
            event_bus=ctx.event_bus,
            max_duration_s=86400,
        )
        engine = SimulationEngine(ctx, victory_evaluator=ve)
        result = engine.run()

        assert result.victory_result.game_over is True
        assert result.victory_result.condition_type == "force_destroyed"
        assert result.victory_result.winning_side == "blue"

    def test_morale_collapsed_victory(self) -> None:
        cfg = _minimal_config(
            duration_hours=24.0,
            victory_conditions=[
                VictoryConditionConfig(type="morale_collapsed", side="blue"),
            ],
        )
        red_units = [
            _make_unit(f"r{i}", Position(5000 + i * 10, 5000, 0), "red")
            for i in range(5)
        ]
        blue_units = [_make_unit("b1", Position(100, 5000, 0), "blue")]
        ctx = _make_ctx(blue_units=blue_units, red_units=red_units, config=cfg)

        # Set red morale to ROUTED for most units
        for u in red_units:
            ctx.morale_states[u.entity_id] = MoraleState.ROUTED

        ve = VictoryEvaluator(
            objectives=[],
            conditions=cfg.victory_conditions,
            event_bus=ctx.event_bus,
            config=VictoryEvaluatorConfig(morale_collapse_threshold=0.6),
        )
        engine = SimulationEngine(ctx, victory_evaluator=ve)
        result = engine.run()

        assert result.victory_result.game_over is True
        assert result.victory_result.condition_type == "morale_collapsed"

    def test_supply_exhausted_victory(self) -> None:
        cfg = _minimal_config(
            duration_hours=24.0,
            victory_conditions=[
                VictoryConditionConfig(type="supply_exhausted", side="blue"),
            ],
        )
        red_units = [
            _make_unit(f"r{i}", Position(5000, 5000, 0), "red")
            for i in range(3)
        ]
        blue_units = [_make_unit("b1", Position(100, 5000, 0), "blue")]
        ctx = _make_ctx(blue_units=blue_units, red_units=red_units, config=cfg)

        # Create a mock stockpile manager that returns very low supply
        class _MockStockpile:
            def get_supply_state(self, unit_id: str) -> float:
                # Red side has nearly 0 supply
                if unit_id.startswith("r"):
                    return 0.05
                return 1.0

        ctx.stockpile_manager = _MockStockpile()

        ve = VictoryEvaluator(
            objectives=[],
            conditions=cfg.victory_conditions,
            event_bus=ctx.event_bus,
            config=VictoryEvaluatorConfig(supply_exhaustion_threshold=0.2),
        )
        engine = SimulationEngine(ctx, victory_evaluator=ve)
        result = engine.run()

        assert result.victory_result.game_over is True
        assert result.victory_result.condition_type == "supply_exhausted"


# ---------------------------------------------------------------------------
# Test 9: Recorder captures event history
# ---------------------------------------------------------------------------


class TestRecorderEventCapture:
    """SimulationRecorder captures events during a run."""

    def test_recorder_captures_tick_events(self) -> None:
        cfg = _minimal_config(duration_hours=3.0)
        ctx = _make_ctx(config=cfg, tick_s=3600.0)
        rec = SimulationRecorder(ctx.event_bus)
        engine = SimulationEngine(ctx, recorder=rec)

        result = engine.run()

        # Recorder was started and stopped by engine.run()
        assert rec._subscribed is False  # stopped
        assert rec._current_tick >= 3

    def test_recorder_captures_victory_event(self) -> None:
        cfg = _minimal_config(
            duration_hours=24.0,
            victory_conditions=[
                VictoryConditionConfig(
                    type="time_expired", side="draw",
                    params={"max_duration_s": 3600},
                ),
            ],
        )
        ctx = _make_ctx(config=cfg, tick_s=3600.0)
        rec = SimulationRecorder(ctx.event_bus)
        ve = VictoryEvaluator(
            objectives=[],
            conditions=cfg.victory_conditions,
            event_bus=ctx.event_bus,
            max_duration_s=3600,
        )
        engine = SimulationEngine(ctx, recorder=rec, victory_evaluator=ve)
        engine.run()

        victory_events = rec.events_of_type("VictoryDeclaredEvent")
        assert len(victory_events) >= 1
        assert victory_events[0].data.get("condition_type") == "time_expired"

    def test_recorder_event_count_grows_with_steps(self) -> None:
        cfg = _minimal_config(duration_hours=24.0)
        ctx = _make_ctx(config=cfg, tick_s=3600.0)
        rec = SimulationRecorder(ctx.event_bus)
        engine = SimulationEngine(ctx, recorder=rec)
        rec.start()

        engine.step()
        count_after_1 = rec.event_count()
        engine.step()
        count_after_2 = rec.event_count()

        # Count should be non-decreasing (may be same if no events published)
        assert count_after_2 >= count_after_1


# ---------------------------------------------------------------------------
# Test 10: Campaign metrics extraction from completed run
# ---------------------------------------------------------------------------


class TestCampaignMetrics:
    """Extract structured metrics from a completed campaign."""

    def test_extract_campaign_summary(self) -> None:
        cfg = _minimal_config(
            duration_hours=2.0,
            victory_conditions=[
                VictoryConditionConfig(type="force_destroyed", side="blue"),
            ],
        )
        red_destroyed = [
            _make_unit(f"r{i}", Position(5000, 5000, 0), "red",
                       status=UnitStatus.DESTROYED)
            for i in range(10)
        ]
        blue_units = [
            _make_unit("b1", Position(100, 5000, 0), "blue"),
            _make_unit("b2", Position(200, 5000, 0), "blue"),
        ]
        ctx = _make_ctx(blue_units=blue_units, red_units=red_destroyed, config=cfg)
        rec = SimulationRecorder(ctx.event_bus)
        ve = VictoryEvaluator(
            objectives=[],
            conditions=cfg.victory_conditions,
            event_bus=ctx.event_bus,
        )
        engine = SimulationEngine(ctx, recorder=rec, victory_evaluator=ve)
        result = engine.run()

        summary = CampaignMetrics.extract_campaign_summary(
            recorder=rec,
            victory=result.victory_result,
            units_by_side=ctx.units_by_side,
            campaign_name="test_campaign",
            ticks_executed=result.ticks_executed,
            duration_s=result.duration_s,
        )

        assert isinstance(summary, CampaignSummary)
        assert summary.game_over is True
        assert summary.winning_side == "blue"
        assert summary.victory_condition == "force_destroyed"
        assert "blue" in summary.sides
        assert "red" in summary.sides
        assert summary.sides["red"].units_destroyed == 10
        assert summary.sides["blue"].final_active_units == 2

    def test_engagement_outcomes_from_events(self) -> None:
        # With no combat, engagement outcomes should be all zeros
        events: list[Any] = []
        outcomes = CampaignMetrics.engagement_outcomes(events)
        assert outcomes["total"] == 0
        assert outcomes["hits"] == 0
        assert outcomes["misses"] == 0


# ---------------------------------------------------------------------------
# Test 11: Tick resolution switching (strategic -> tactical -> strategic)
# ---------------------------------------------------------------------------


class TestTickResolutionSwitching:
    """Full resolution cycle: strategic -> tactical -> operational -> strategic."""

    def test_full_resolution_cycle(self) -> None:
        blue = [_make_unit("b1", Position(100, 5000, 0), "blue")]
        red = [_make_unit("r1", Position(500, 5000, 0), "red")]
        cfg = _minimal_config(duration_hours=24.0)
        ctx = _make_ctx(blue_units=blue, red_units=red, config=cfg)

        engine = SimulationEngine(
            ctx,
            campaign_config=CampaignConfig(engagement_detection_range_m=5000),
        )

        # Step 1: STRATEGIC -> TACTICAL (battle detected)
        engine.step()
        assert engine.resolution == TickResolution.TACTICAL
        assert ctx.clock.tick_duration.total_seconds() == pytest.approx(5.0)

        # Terminate battle and separate forces so they won't re-detect
        for b in engine.battle_manager._battles.values():
            b.active = False
        object.__setattr__(red[0], "position", Position(9000, 5000, 0))

        # Step 2: TACTICAL -> OPERATIONAL
        engine.step()
        assert engine.resolution == TickResolution.OPERATIONAL
        assert ctx.clock.tick_duration.total_seconds() == pytest.approx(300.0)

        # Step 3: OPERATIONAL -> STRATEGIC (forces still far apart)
        engine.step()
        assert engine.resolution == TickResolution.STRATEGIC
        assert ctx.clock.tick_duration.total_seconds() == pytest.approx(3600.0)

    def test_custom_tick_durations_used(self) -> None:
        cfg = _minimal_config(
            duration_hours=24.0,
            tick_resolution=TickResolutionConfig(
                strategic_s=1800.0, operational_s=120.0, tactical_s=2.0,
            ),
        )
        ctx = _make_ctx(config=cfg)
        engine = SimulationEngine(ctx)

        # Strategic tick
        assert ctx.clock.tick_duration.total_seconds() == pytest.approx(1800.0)

        # Force tactical
        engine._set_resolution(TickResolution.TACTICAL)
        assert ctx.clock.tick_duration.total_seconds() == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# Test 12: Deterministic replay (same seed = identical tick count)
# ---------------------------------------------------------------------------


class TestDeterministicReplay:
    """Same seed and configuration yields identical simulation results."""

    def test_same_seed_identical_tick_count(self) -> None:
        def _run(seed: int = 42) -> SimulationRunResult:
            cfg = _minimal_config(duration_hours=5.0)
            blue = [_make_unit("b1", Position(100, 5000, 0), "blue")]
            red = [_make_unit("r1", Position(9900, 5000, 0), "red")]
            ctx = _make_ctx(
                blue_units=blue, red_units=red,
                config=cfg, tick_s=3600.0, seed=seed,
            )
            engine = SimulationEngine(ctx)
            return engine.run()

        result_a = _run(seed=42)
        result_b = _run(seed=42)

        assert result_a.ticks_executed == result_b.ticks_executed
        assert result_a.duration_s == pytest.approx(result_b.duration_s)
        assert result_a.victory_result.condition_type == result_b.victory_result.condition_type

    def test_different_seed_may_differ(self) -> None:
        """Sanity check: different seeds produce same structure but may differ
        in stochastic outcomes. For a purely time-limited campaign without
        combat, tick count will be identical; the important thing is both
        complete successfully."""
        def _run(seed: int) -> SimulationRunResult:
            cfg = _minimal_config(duration_hours=3.0)
            ctx = _make_ctx(config=cfg, tick_s=3600.0, seed=seed)
            engine = SimulationEngine(ctx)
            return engine.run()

        r1 = _run(42)
        r2 = _run(99)
        # Both should complete
        assert r1.victory_result.game_over is True
        assert r2.victory_result.game_over is True


# ---------------------------------------------------------------------------
# Test 13: Environment update during run
# ---------------------------------------------------------------------------


class TestEnvironmentUpdate:
    """Environment engines are called each tick."""

    def test_weather_engine_called_each_tick(self) -> None:
        call_count = {"n": 0}

        class _MockWeather:
            def step(self, clock: Any) -> None:
                call_count["n"] += 1

        cfg = _minimal_config(duration_hours=24.0)
        ctx = _make_ctx(config=cfg, tick_s=3600.0)
        ctx.weather_engine = _MockWeather()

        engine = SimulationEngine(ctx)
        for _ in range(5):
            engine.step()

        assert call_count["n"] == 5

    def test_multiple_environment_engines_called(self) -> None:
        calls: dict[str, int] = {"weather": 0, "tod": 0, "sea": 0, "seasons": 0}

        class _W:
            def step(self, clock: Any) -> None:
                calls["weather"] += 1

        class _T:
            def update(self, clock: Any) -> None:
                calls["tod"] += 1

        class _S:
            def update(self, clock: Any) -> None:
                calls["sea"] += 1

        class _Sn:
            def update(self, clock: Any) -> None:
                calls["seasons"] += 1

        cfg = _minimal_config(duration_hours=24.0)
        ctx = _make_ctx(config=cfg, tick_s=3600.0)
        ctx.weather_engine = _W()
        ctx.time_of_day_engine = _T()
        ctx.sea_state_engine = _S()
        ctx.seasons_engine = _Sn()

        engine = SimulationEngine(ctx)
        engine.step()
        engine.step()

        assert all(v == 2 for v in calls.values())

    def test_environment_failure_does_not_halt(self) -> None:
        class _BrokenEngine:
            def step(self, clock: Any) -> None:
                raise RuntimeError("Weather crash!")

        cfg = _minimal_config(duration_hours=24.0)
        ctx = _make_ctx(config=cfg, tick_s=3600.0)
        ctx.weather_engine = _BrokenEngine()

        engine = SimulationEngine(ctx)
        # Should not raise
        engine.step()
        assert ctx.clock.tick_count == 1


# ---------------------------------------------------------------------------
# Test 14: C2/AI engines present but don't crash
# ---------------------------------------------------------------------------


class TestC2AIPresence:
    """When C2/AI engines are wired into the context, they don't crash."""

    @pytest.mark.skipif(
        not _scenario_data_available(),
        reason="Test campaign YAML / unit data not found",
    )
    def test_full_scenario_with_c2_ai_engines(self) -> None:
        """Full scenario with all engines wired; run 3 strategic ticks."""
        loader = ScenarioLoader(_DATA_DIR)
        ctx = loader.load(_TEST_SCENARIO, seed=42)

        # All these engines should be non-None
        assert ctx.engagement_engine is not None
        assert ctx.morale_machine is not None
        assert ctx.ooda_engine is not None
        assert ctx.decision_engine is not None
        assert ctx.assessor is not None
        assert ctx.consumption_engine is not None
        assert ctx.stockpile_manager is not None

        engine = SimulationEngine(ctx)
        for _ in range(3):
            done = engine.step()
            if done:
                break

        assert ctx.clock.tick_count >= 3

    def test_mock_ooda_engine_called_in_strategic(self) -> None:
        calls = {"update": 0}

        class _MockOODA:
            def update(self, dt: float, ts: Any = None) -> list:
                calls["update"] += 1
                return []

        cfg = _minimal_config(duration_hours=24.0)
        ctx = _make_ctx(config=cfg, tick_s=3600.0)
        ctx.ooda_engine = _MockOODA()

        engine = SimulationEngine(ctx)
        engine.step()

        # OODA update is called in campaign_manager.update_strategic
        assert calls["update"] >= 1


# ---------------------------------------------------------------------------
# Test 15: Multiple sequential battles
# ---------------------------------------------------------------------------


class TestMultipleSequentialBattles:
    """Detect, resolve, detect again with fresh forces."""

    def test_two_sequential_battles(self) -> None:
        blue = [
            _make_unit("b1", Position(100, 5000, 0), "blue"),
            _make_unit("b2", Position(100, 5100, 0), "blue"),
        ]
        red = [
            _make_unit("r1", Position(500, 5000, 0), "red"),
            _make_unit("r2", Position(500, 5100, 0), "red"),
        ]
        cfg = _minimal_config(duration_hours=24.0)
        ctx = _make_ctx(blue_units=blue, red_units=red, config=cfg)

        engine = SimulationEngine(
            ctx,
            campaign_config=CampaignConfig(engagement_detection_range_m=5000),
        )

        # Battle 1: detect
        engine.step()
        assert engine.resolution == TickResolution.TACTICAL
        assert len(engine.battle_manager.active_battles) >= 1
        first_battle_id = engine.battle_manager.active_battles[0].battle_id

        # Terminate battle 1 by destroying red[0]
        object.__setattr__(red[0], "status", UnitStatus.DESTROYED)
        object.__setattr__(red[1], "status", UnitStatus.DESTROYED)

        # Step until resolved and back to strategic
        for _ in range(20):
            engine.step()
            if engine.resolution == TickResolution.STRATEGIC:
                break

        assert engine.resolution == TickResolution.STRATEGIC
        assert engine.battle_manager._battles[first_battle_id].active is False

        # Revive red and move close for battle 2
        object.__setattr__(red[0], "status", UnitStatus.ACTIVE)
        object.__setattr__(red[1], "status", UnitStatus.ACTIVE)
        object.__setattr__(red[0], "position", Position(200, 5000, 0))
        object.__setattr__(red[1], "position", Position(200, 5100, 0))

        # Battle 2: detect
        engine.step()
        assert engine.resolution == TickResolution.TACTICAL
        active = engine.battle_manager.active_battles
        assert len(active) >= 1
        # New battle created (different ID)
        assert active[0].battle_id != first_battle_id

    def test_simultaneous_battles_different_zones(self) -> None:
        """Two separate engagements in different areas."""
        ctx = _make_ctx(config=_minimal_config(duration_hours=24.0))
        engine = SimulationEngine(ctx)

        b1 = BattleContext(
            battle_id="b_north",
            start_tick=0,
            start_time=TS,
            involved_sides=["blue", "red"],
        )
        b2 = BattleContext(
            battle_id="b_south",
            start_tick=0,
            start_time=TS,
            involved_sides=["blue", "red"],
        )
        engine.battle_manager._battles["b_north"] = b1
        engine.battle_manager._battles["b_south"] = b2

        engine.step()

        # Both should have been ticked
        assert b1.ticks_executed >= 1 or not b1.active
        assert b2.ticks_executed >= 1 or not b2.active
        assert engine.resolution == TickResolution.TACTICAL


# ---------------------------------------------------------------------------
# Additional integration tests
# ---------------------------------------------------------------------------


class TestRecorderSnapshots:
    """Recorder takes periodic state snapshots during a run."""

    def test_snapshots_taken_at_interval(self) -> None:
        cfg = _minimal_config(duration_hours=24.0)
        ctx = _make_ctx(config=cfg, tick_s=3600.0)
        rec = SimulationRecorder(ctx.event_bus)
        eng_cfg = EngineConfig(snapshot_interval_ticks=2)
        engine = SimulationEngine(ctx, config=eng_cfg, recorder=rec)
        rec.start()

        for _ in range(6):
            engine.step()

        # At ticks 2, 4, 6 there should be snapshots
        assert len(rec.snapshots) >= 3

    def test_events_in_range_query(self) -> None:
        cfg = _minimal_config(
            duration_hours=24.0,
            victory_conditions=[
                VictoryConditionConfig(
                    type="time_expired", side="draw",
                    params={"max_duration_s": 14400},
                ),
            ],
        )
        ctx = _make_ctx(config=cfg, tick_s=3600.0)
        rec = SimulationRecorder(ctx.event_bus)
        ve = VictoryEvaluator(
            objectives=[], conditions=cfg.victory_conditions,
            event_bus=ctx.event_bus, max_duration_s=14400,
        )
        engine = SimulationEngine(ctx, recorder=rec, victory_evaluator=ve)
        engine.run()

        # The VictoryDeclaredEvent is published during the final step's
        # victory evaluation, *before* record_tick updates the current tick
        # number.  So it is recorded under the previous tick's number.
        # Query the full run range to find it.
        final_tick = ctx.clock.tick_count
        all_events = rec.events_in_range(0, final_tick)
        victory_in_range = [
            e for e in all_events if e.event_type == "VictoryDeclaredEvent"
        ]
        assert len(victory_in_range) >= 1
        # Verify it was captured during the run
        assert victory_in_range[0].data.get("condition_type") == "time_expired"


class TestAutoCheckpointing:
    """Auto-checkpoint collects state at configured intervals."""

    def test_auto_checkpoints_collected(self) -> None:
        cfg = _minimal_config(duration_hours=24.0)
        ctx = _make_ctx(config=cfg, tick_s=3600.0)
        engine = SimulationEngine(
            ctx, config=EngineConfig(checkpoint_interval_ticks=3),
        )

        for _ in range(9):
            engine.step()

        # At ticks 3, 6, 9 there should be checkpoints
        assert len(engine._checkpoints) >= 3

    def test_checkpoint_contains_required_keys(self) -> None:
        cfg = _minimal_config(duration_hours=24.0)
        ctx = _make_ctx(config=cfg, tick_s=3600.0)
        engine = SimulationEngine(
            ctx, config=EngineConfig(checkpoint_interval_ticks=1),
        )
        engine.step()

        assert len(engine._checkpoints) >= 1
        cp = engine._checkpoints[0]
        assert "resolution" in cp
        assert "context" in cp
        assert "campaign" in cp
        assert "battle" in cp


class TestMaxTicksSafety:
    """Engine stops at max_ticks safety limit."""

    def test_max_ticks_limit(self) -> None:
        cfg = _minimal_config(duration_hours=1000.0)
        ctx = _make_ctx(config=cfg, tick_s=3600.0)
        engine = SimulationEngine(
            ctx, config=EngineConfig(max_ticks=10),
        )
        result = engine.run()

        assert result.ticks_executed == 10
        assert result.victory_result.game_over is True
        assert result.victory_result.condition_type == "max_ticks"


class TestScenarioLoaderIntegration:
    """Full ScenarioLoader round-trip tests."""

    @pytest.mark.skipif(
        not _scenario_data_available(),
        reason="Test campaign YAML / unit data not found",
    )
    def test_loader_creates_all_engines(self) -> None:
        loader = ScenarioLoader(_DATA_DIR)
        ctx = loader.load(_TEST_SCENARIO, seed=42)

        # Verify all major engines are wired
        assert ctx.engagement_engine is not None
        assert ctx.fog_of_war is not None
        assert ctx.morale_machine is not None
        assert ctx.movement_engine is not None
        assert ctx.comms_engine is not None
        assert ctx.ooda_engine is not None
        assert ctx.planning_engine is not None
        assert ctx.assessor is not None
        assert ctx.decision_engine is not None
        assert ctx.consumption_engine is not None
        assert ctx.stockpile_manager is not None
        assert ctx.unit_loader is not None

    @pytest.mark.skipif(
        not _scenario_data_available(),
        reason="Test campaign YAML / unit data not found",
    )
    def test_loader_assigns_weapons_and_sensors(self) -> None:
        loader = ScenarioLoader(_DATA_DIR)
        ctx = loader.load(_TEST_SCENARIO, seed=42)

        # m1a2 should have weapons and sensors assigned
        assert len(ctx.unit_weapons) > 0
        assert len(ctx.unit_sensors) > 0

    @pytest.mark.skipif(
        not _scenario_data_available(),
        reason="Test campaign YAML / unit data not found",
    )
    def test_full_campaign_run_to_completion(self) -> None:
        """Full end-to-end: load, create engine with all bells and whistles, run."""
        loader = ScenarioLoader(_DATA_DIR)
        ctx = loader.load(_TEST_SCENARIO, seed=42)

        rec = SimulationRecorder(ctx.event_bus)
        ve = VictoryEvaluator(
            objectives=[
                ObjectiveState(
                    objective_id=obj.objective_id,
                    position=Position(*obj.position),
                    radius_m=obj.radius_m,
                )
                for obj in ctx.config.objectives
            ],
            conditions=ctx.config.victory_conditions,
            event_bus=ctx.event_bus,
            max_duration_s=ctx.config.duration_hours * 3600,
        )
        engine = SimulationEngine(
            ctx,
            config=EngineConfig(max_ticks=50),
            victory_evaluator=ve,
            recorder=rec,
        )
        engine.campaign_manager.set_reinforcements(ctx.config.reinforcements)

        result = engine.run()

        assert result.victory_result.game_over is True
        assert result.ticks_executed >= 1
        assert result.duration_s > 0

        # Extract summary
        summary = CampaignMetrics.extract_campaign_summary(
            recorder=rec,
            victory=result.victory_result,
            units_by_side=ctx.units_by_side,
            campaign_name=ctx.config.name,
            ticks_executed=result.ticks_executed,
            duration_s=result.duration_s,
        )
        assert isinstance(summary, CampaignSummary)
        assert summary.ticks_executed == result.ticks_executed
