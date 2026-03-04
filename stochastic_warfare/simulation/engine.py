"""Master simulation engine — top-level orchestrator for campaign runs.

Ties all domain modules together into a coherent multi-scale simulation
loop.  Manages tick resolution switching (strategic ↔ operational ↔
tactical), delegates to :class:`CampaignManager` and :class:`BattleManager`
for scale-specific logic, and coordinates victory evaluation, event
recording, and checkpointing.

No domain logic lives here — only sequencing, resolution management,
and state collection.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import timedelta
from enum import IntEnum
from typing import Any

from pydantic import BaseModel

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.base import UnitStatus
from stochastic_warfare.simulation.battle import BattleConfig, BattleContext, BattleManager
from stochastic_warfare.simulation.campaign import CampaignConfig, CampaignManager
from stochastic_warfare.simulation.recorder import SimulationRecorder
from stochastic_warfare.simulation.scenario import SimulationContext
from stochastic_warfare.simulation.victory import VictoryEvaluator, VictoryResult

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class EngineConfig(BaseModel):
    """Tuning parameters for the simulation engine."""

    checkpoint_interval_ticks: int = 0
    """Ticks between automatic checkpoints.  0 disables auto-checkpoint."""

    max_ticks: int = 1_000_000
    """Safety limit — stop the simulation after this many ticks."""

    snapshot_interval_ticks: int = 100
    """Ticks between recorder state snapshots."""

    enable_selective_los_invalidation: bool = False
    """Use selective cell invalidation instead of full LOS cache clear."""


# ---------------------------------------------------------------------------
# Tick resolution
# ---------------------------------------------------------------------------


class TickResolution(IntEnum):
    """Time-scale resolution for the simulation loop."""

    STRATEGIC = 0    # 3600s default
    OPERATIONAL = 1  # 300s default
    TACTICAL = 2     # 5s default


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SimulationRunResult:
    """Outcome of a complete simulation run."""

    ticks_executed: int
    duration_s: float
    victory_result: VictoryResult
    campaign_summary: Any = None  # CampaignSummary or None


# ---------------------------------------------------------------------------
# Master engine
# ---------------------------------------------------------------------------


class SimulationEngine:
    """Top-level simulation orchestrator.

    Manages the master tick loop that ties campaign-level strategy to
    tactical-level battle resolution.  Automatically switches tick
    resolution based on battle state.

    Parameters
    ----------
    ctx : SimulationContext
        Fully-wired context from :class:`ScenarioLoader`.
    config : EngineConfig | None
        Engine tuning parameters.
    campaign_config : CampaignConfig | None
        Campaign manager tuning parameters.
    battle_config : BattleConfig | None
        Battle manager tuning parameters.
    victory_evaluator : VictoryEvaluator | None
        Victory condition evaluator.  If *None*, no victory checks.
    recorder : SimulationRecorder | None
        Event recorder.  If *None*, no event recording.
    """

    def __init__(
        self,
        ctx: SimulationContext,
        config: EngineConfig | None = None,
        campaign_config: CampaignConfig | None = None,
        battle_config: BattleConfig | None = None,
        victory_evaluator: VictoryEvaluator | None = None,
        recorder: SimulationRecorder | None = None,
    ) -> None:
        self._ctx = ctx
        self._config = config or EngineConfig()

        # Sub-managers
        core_rng = ctx.rng_manager.get_stream(
            __import__(
                "stochastic_warfare.core.types", fromlist=["ModuleId"]
            ).ModuleId.CORE
        )
        self._campaign = CampaignManager(
            ctx.event_bus, core_rng, campaign_config,
        )
        self._battle = BattleManager(ctx.event_bus, battle_config)
        self._victory = victory_evaluator
        self._recorder = recorder

        # Tick resolution state
        self._resolution = TickResolution.STRATEGIC
        self._tick_durations = {
            TickResolution.STRATEGIC: ctx.config.tick_resolution.strategic_s,
            TickResolution.OPERATIONAL: ctx.config.tick_resolution.operational_s,
            TickResolution.TACTICAL: ctx.config.tick_resolution.tactical_s,
        }
        # Set initial tick duration
        ctx.clock.set_tick_duration(
            timedelta(seconds=self._tick_durations[TickResolution.STRATEGIC])
        )

        # Campaign duration limit
        self._max_duration_s = ctx.config.duration_hours * 3600.0

        # Checkpoints
        self._checkpoints: list[dict[str, Any]] = []

    # ── Properties ────────────────────────────────────────────────────

    @property
    def resolution(self) -> TickResolution:
        """Current tick resolution."""
        return self._resolution

    @property
    def campaign_manager(self) -> CampaignManager:
        """The campaign manager sub-component."""
        return self._campaign

    @property
    def battle_manager(self) -> BattleManager:
        """The battle manager sub-component."""
        return self._battle

    @property
    def victory_evaluator(self) -> VictoryEvaluator | None:
        """The victory evaluator, if any."""
        return self._victory

    @property
    def recorder(self) -> SimulationRecorder | None:
        """The event recorder, if any."""
        return self._recorder

    # ── Run ───────────────────────────────────────────────────────────

    def run(self) -> SimulationRunResult:
        """Run the simulation to completion (victory or max ticks).

        Returns
        -------
        SimulationRunResult
            Final result with ticks executed, duration, and victory info.
        """
        if self._recorder is not None:
            self._recorder.start()

        game_over = False
        while not game_over:
            game_over = self.step()

        if self._recorder is not None:
            self._recorder.stop()

        elapsed_s = self._ctx.clock.elapsed.total_seconds()
        victory = self._last_victory or VictoryResult(game_over=False)

        return SimulationRunResult(
            ticks_executed=self._ctx.clock.tick_count,
            duration_s=elapsed_s,
            victory_result=victory,
        )

    # ── Single step ──────────────────────────────────────────────────

    def step(self) -> bool:
        """Advance the simulation by one tick.

        Returns
        -------
        bool
            ``True`` if the simulation is over (victory or max ticks).
        """
        ctx = self._ctx
        clock = ctx.clock
        tick = clock.tick_count

        # Safety limit
        if tick >= self._config.max_ticks:
            logger.info("Max ticks (%d) reached — stopping", self._config.max_ticks)
            self._last_victory = VictoryResult(
                game_over=True,
                winning_side="draw",
                condition_type="max_ticks",
                message=f"Safety limit of {self._config.max_ticks} ticks reached",
                tick=tick,
            )
            return True

        # 1. Advance clock
        clock.advance()
        tick = clock.tick_count
        dt = clock.tick_duration.total_seconds()
        timestamp = clock.current_time

        # 1b. LOS cache management
        selective_los = (
            self._config.enable_selective_los_invalidation
            and ctx.los_engine is not None
            and hasattr(ctx.los_engine, "invalidate_cells")
        )
        if not selective_los and ctx.los_engine is not None and hasattr(ctx.los_engine, "clear_los_cache"):
            ctx.los_engine.clear_los_cache()

        # Record pre-move grid cells for selective LOS invalidation
        pre_move_cells: dict[str, tuple[int, int]] | None = None
        if selective_los:
            pre_move_cells = self._snapshot_unit_cells(ctx)

        # 2. Update environment
        self._update_environment(dt)

        # 3. Determine and apply tick resolution
        self._update_resolution()

        # 4. Strategic logic (runs at all resolutions, but campaign
        #    manager internally gates on strategic tick intervals)
        if self._resolution == TickResolution.STRATEGIC:
            self._campaign.update_strategic(ctx, dt)

            # Phase 13 postmortem: aggregation/disaggregation
            if (ctx.aggregation_engine is not None
                    and ctx.aggregation_engine._config.enable_aggregation):
                battle_positions = self._compute_battle_positions(ctx)
                # Disaggregate first (units approaching battle)
                for agg_id in ctx.aggregation_engine.check_disaggregation_triggers(
                    ctx, battle_positions,
                ):
                    ctx.aggregation_engine.disaggregate(agg_id, ctx)
                # Then aggregate (distant units can be merged)
                for group in ctx.aggregation_engine.check_aggregation_candidates(
                    ctx, battle_positions,
                ):
                    ctx.aggregation_engine.aggregate(group, ctx)

            # Detect new engagements
            new_battles = self._campaign.detect_engagements(ctx, self._battle)
            if new_battles:
                # Phase 13a-6: Auto-resolve minor battles
                remaining = []
                for battle in new_battles:
                    total_units = sum(
                        len([u for u in ctx.units_by_side.get(s, [])
                             if u.status == UnitStatus.ACTIVE])
                        for s in battle.involved_sides
                    )
                    if (self._battle._config.auto_resolve_enabled
                            and self._battle._config.auto_resolve_max_units > 0
                            and total_units <= self._battle._config.auto_resolve_max_units):
                        ar_rng = ctx.rng_manager.get_stream(
                            __import__(
                                "stochastic_warfare.core.types", fromlist=["ModuleId"]
                            ).ModuleId.CORE
                        )
                        self._battle.auto_resolve(
                            battle, ctx.units_by_side, ar_rng,
                            morale_states=ctx.morale_states,
                        )
                    else:
                        remaining.append(battle)
                if remaining:
                    # Switch to tactical
                    self._set_resolution(TickResolution.TACTICAL)

        # 5. Tactical logic (active battles)
        active = self._battle.active_battles
        if active:
            for battle in active:
                self._battle.execute_tick(ctx, battle, dt)
                if self._battle.check_battle_termination(battle, ctx.units_by_side):
                    self._battle.resolve_battle(battle, ctx.units_by_side)
                    # Clear integration gain scan counts so they don't bleed
                    # across battles.
                    det_eng = getattr(
                        getattr(ctx, "fog_of_war", None), "_detection", None
                    )
                    if det_eng is not None and hasattr(det_eng, "reset_scan_counts"):
                        det_eng.reset_scan_counts()
                    logger.info("Battle %s resolved after %d ticks",
                                battle.battle_id, battle.ticks_executed)

        # 5b. Selective LOS invalidation after movement
        if selective_los and pre_move_cells is not None:
            post_move_cells = self._snapshot_unit_cells(ctx)
            dirty_cells: set[tuple[int, int]] = set()
            all_ids = set(pre_move_cells) | set(post_move_cells)
            for uid in all_ids:
                pre = pre_move_cells.get(uid)
                post = post_move_cells.get(uid)
                if pre != post:
                    if pre is not None:
                        dirty_cells.add(pre)
                    if post is not None:
                        dirty_cells.add(post)
            if dirty_cells:
                ctx.los_engine.invalidate_cells(dirty_cells)

        # 6. Victory evaluation
        victory = self._evaluate_victory(tick)
        if victory.game_over:
            self._last_victory = victory
            # Record final tick
            if self._recorder is not None:
                self._recorder.record_tick(tick, timestamp)
            return True

        # 7. Recorder
        if self._recorder is not None:
            self._recorder.record_tick(tick, timestamp)
            if self._config.snapshot_interval_ticks > 0:
                if tick % self._config.snapshot_interval_ticks == 0:
                    self._recorder.take_snapshot(
                        tick, timestamp, ctx.get_state,
                    )

        # 8. Auto-checkpoint
        if (self._config.checkpoint_interval_ticks > 0
                and tick % self._config.checkpoint_interval_ticks == 0):
            self._checkpoints.append(self.get_state())

        # Check time limit
        elapsed_s = ctx.clock.elapsed.total_seconds()
        if elapsed_s >= self._max_duration_s:
            self._last_victory = VictoryResult(
                game_over=True,
                winning_side="draw",
                condition_type="time_expired",
                message=f"Campaign duration {elapsed_s:.0f}s reached limit {self._max_duration_s:.0f}s",
                tick=tick,
            )
            return True

        return False

    # ── Environment ──────────────────────────────────────────────────

    def _update_environment(self, dt: float) -> None:
        """Update environment engines for the current tick."""
        ctx = self._ctx
        clock = ctx.clock

        if ctx.weather_engine is not None and hasattr(ctx.weather_engine, "step"):
            try:
                ctx.weather_engine.step(clock)
            except Exception:
                pass  # Non-critical

        if ctx.time_of_day_engine is not None and hasattr(ctx.time_of_day_engine, "update"):
            try:
                ctx.time_of_day_engine.update(clock)
            except Exception:
                pass

        if ctx.sea_state_engine is not None and hasattr(ctx.sea_state_engine, "update"):
            try:
                ctx.sea_state_engine.update(clock)
            except Exception:
                pass

        if ctx.seasons_engine is not None and hasattr(ctx.seasons_engine, "update"):
            try:
                ctx.seasons_engine.update(clock)
            except Exception:
                pass

        # Phase 17: Space domain
        if ctx.space_engine is not None and hasattr(ctx.space_engine, "update"):
            try:
                elapsed = clock.elapsed.total_seconds()
                ctx.space_engine.update(
                    dt, elapsed,
                    em_environment=ctx.conditions_engine,
                    comms_engine=ctx.comms_engine,
                    targets_by_side=ctx.units_by_side,
                )
            except Exception:
                pass

    # ── Battle positions (for aggregation) ─────────────────────────────

    def _compute_battle_positions(self, ctx: SimulationContext) -> list[Position]:
        """Compute centroid positions of active battles for aggregation distance checks."""
        positions: list[Position] = []
        for battle in self._battle.active_battles:
            if not battle.unit_ids:
                continue
            eastings: list[float] = []
            northings: list[float] = []
            for side_units in ctx.units_by_side.values():
                for u in side_units:
                    if u.entity_id in battle.unit_ids and u.status == UnitStatus.ACTIVE:
                        eastings.append(u.position.easting)
                        northings.append(u.position.northing)
            if eastings:
                positions.append(Position(
                    sum(eastings) / len(eastings),
                    sum(northings) / len(northings),
                ))
        return positions

    # ── Selective LOS invalidation helpers ──────────────────────────────

    def _snapshot_unit_cells(self, ctx: SimulationContext) -> dict[str, tuple[int, int]]:
        """Snapshot current grid cell for each active unit (for dirty-cell tracking)."""
        cells: dict[str, tuple[int, int]] = {}
        if ctx.heightmap is None:
            return cells
        for side_units in ctx.units_by_side.values():
            for u in side_units:
                if u.status == UnitStatus.ACTIVE:
                    cells[u.entity_id] = ctx.heightmap.enu_to_grid(u.position)
        return cells

    # ── Resolution switching ─────────────────────────────────────────

    def _update_resolution(self) -> None:
        """Switch tick resolution based on battle state."""
        active = self._battle.active_battles
        if active:
            self._set_resolution(TickResolution.TACTICAL)
        elif self._resolution == TickResolution.TACTICAL:
            # All battles concluded — step back
            self._set_resolution(TickResolution.OPERATIONAL)
        elif self._resolution == TickResolution.OPERATIONAL:
            # No contacts — back to strategic
            self._set_resolution(TickResolution.STRATEGIC)

    def _set_resolution(self, resolution: TickResolution) -> None:
        """Apply a new tick resolution."""
        if resolution == self._resolution:
            return
        old = self._resolution
        self._resolution = resolution
        new_dt = self._tick_durations[resolution]
        self._ctx.clock.set_tick_duration(timedelta(seconds=new_dt))
        logger.info(
            "Resolution switch: %s -> %s (%.1fs tick)",
            old.name, resolution.name, new_dt,
        )

    # ── Victory evaluation ───────────────────────────────────────────

    def _evaluate_victory(self, tick: int) -> VictoryResult:
        """Delegate to the victory evaluator if present."""
        if self._victory is None:
            return VictoryResult(game_over=False, tick=tick)

        ctx = self._ctx
        supply_states: dict[str, float] = {}
        if ctx.stockpile_manager is not None and hasattr(ctx.stockpile_manager, "get_supply_state"):
            for units in ctx.units_by_side.values():
                for u in units:
                    try:
                        supply_states[u.entity_id] = ctx.stockpile_manager.get_supply_state(u.entity_id)
                    except Exception:
                        supply_states[u.entity_id] = 1.0

        # Update objective control before checking victory
        self._victory.update_objective_control(ctx.units_by_side)

        return self._victory.evaluate(
            clock=ctx.clock,
            units_by_side=ctx.units_by_side,
            morale_states=ctx.morale_states,
            supply_states=supply_states,
        )

    # ── Checkpoint / restore ─────────────────────────────────────────

    def get_state(self) -> dict[str, Any]:
        """Capture full engine state for checkpointing."""
        state: dict[str, Any] = {
            "resolution": self._resolution.value,
            "context": self._ctx.get_state(),
            "campaign": self._campaign.get_state(),
            "battle": self._battle.get_state(),
        }
        if self._victory is not None:
            state["victory"] = self._victory.get_state()
        if self._recorder is not None:
            state["recorder"] = self._recorder.get_state()
        return state

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore engine state from a checkpoint dict."""
        self._resolution = TickResolution(state["resolution"])
        new_dt = self._tick_durations[self._resolution]
        self._ctx.clock.set_tick_duration(timedelta(seconds=new_dt))

        self._ctx.set_state(state["context"])
        self._campaign.set_state(state.get("campaign", {}))
        self._battle.set_state(state.get("battle", {}))

        if self._victory is not None and "victory" in state:
            self._victory.set_state(state["victory"])
        if self._recorder is not None and "recorder" in state:
            self._recorder.set_state(state["recorder"])

    def checkpoint(self) -> bytes:
        """Serialize engine state to bytes."""
        state = self.get_state()
        return json.dumps(state, default=str).encode("utf-8")

    def restore(self, data: bytes) -> None:
        """Restore engine state from serialized bytes."""
        state = json.loads(data.decode("utf-8"))
        self.set_state(state)

    # ── Internal state ───────────────────────────────────────────────

    _last_victory: VictoryResult = VictoryResult(game_over=False)
