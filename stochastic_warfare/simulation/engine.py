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

    resolution_closing_range_mult: float = 2.0
    """Phase 55a: Multiplier on engagement detection range.  When opposing
    forces are within ``engagement_range * mult``, the engine stays at
    OPERATIONAL resolution to prevent overshooting at STRATEGIC ticks."""


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
        strict_mode: bool = False,
    ) -> None:
        self._ctx = ctx
        self._config = config or EngineConfig()
        self._strict_mode = strict_mode

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

        # Detect initial engagement proximity — if opposing forces are
        # already within engagement range at start, begin at tactical
        # resolution instead of strategic (prevents overshooting short
        # engagement scenarios with hour-long ticks).
        initial_battles = self._campaign.detect_engagements(ctx, self._battle)
        if initial_battles:
            self._resolution = TickResolution.TACTICAL
            logger.info(
                "Forces in contact at start — beginning at TACTICAL resolution"
            )

        # Set initial tick duration
        ctx.clock.set_tick_duration(
            timedelta(seconds=self._tick_durations[self._resolution])
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
            composite_weights = getattr(ctx, "calibration", {}).get("victory_weights", None)
            result = VictoryEvaluator.evaluate_force_advantage(
                ctx.units_by_side,
                morale_states=getattr(ctx, "morale_states", None),
                weights=composite_weights,
            )
            self._last_victory = VictoryResult(
                game_over=True,
                winning_side=result.winning_side,
                condition_type="max_ticks",
                message=f"Max ticks reached — {result.message}",
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

            # Phase 24: Escalation update
            if ctx.escalation_engine is not None:
                self._update_escalation(dt)

            # Phase 53d: Planning process update (structural)
            if ctx.planning_engine is not None:
                try:
                    _plan_completions = ctx.planning_engine.update(dt, ts=timestamp)
                    if _plan_completions:
                        logger.debug("Planning completions: %d", len(_plan_completions))
                except Exception:
                    logger.debug("Planning engine update failed", exc_info=True)

            # Phase 53d: ATO generation (structural — auto-register aerial units)
            if getattr(ctx, "ato_engine", None) is not None:
                try:
                    from stochastic_warfare.c2.orders.air_orders import AircraftAvailability
                    from stochastic_warfare.core.types import Domain
                    for _side_units in ctx.units_by_side.values():
                        for _u in _side_units:
                            if getattr(_u, "domain", None) == Domain.AIR and _u.status == UnitStatus.ACTIVE:
                                try:
                                    ctx.ato_engine.register_aircraft(
                                        AircraftAvailability(unit_id=_u.entity_id),
                                    )
                                except Exception:
                                    pass  # already registered or invalid
                    _ato_entries = ctx.ato_engine.generate_ato(
                        current_time_s=ctx.clock.elapsed.total_seconds(),
                        timestamp=timestamp,
                    )
                    if _ato_entries:
                        logger.debug("ATO generated %d entries", len(_ato_entries))
                except Exception:
                    logger.debug("ATO generation failed", exc_info=True)

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

        # 4b. Phase 55a: engagement detection at OPERATIONAL resolution
        # (prevents forces overshooting each other between STRATEGIC ticks).
        # Phase 57: Also run strategic movement at OPERATIONAL to prevent
        # deadlock — the closing range guard can hold resolution at
        # OPERATIONAL while forces are still beyond engagement range.
        # Without movement here, units freeze in the 15–30 km gap.
        if self._resolution == TickResolution.OPERATIONAL:
            self._campaign.update_strategic(ctx, dt)
            new_battles = self._campaign.detect_engagements(ctx, self._battle)
            if new_battles:
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
            composite_weights = getattr(ctx, "calibration", {}).get("victory_weights", None)
            result = VictoryEvaluator.evaluate_force_advantage(
                ctx.units_by_side,
                morale_states=getattr(ctx, "morale_states", None),
                weights=composite_weights,
            )
            self._last_victory = VictoryResult(
                game_over=True,
                winning_side=result.winning_side,
                condition_type="time_expired",
                message=f"Time expired — {result.message}",
                tick=tick,
            )
            return True

        return False

    # ── Environment ──────────────────────────────────────────────────

    def _update_environment(self, dt: float) -> None:
        """Update environment engines for the current tick."""
        ctx = self._ctx
        clock = ctx.clock

        # Phase 44a: Fixed environment engine update calls — use actual
        # method signatures (update(dt_seconds), not step(clock)).
        if ctx.weather_engine is not None:
            try:
                ctx.weather_engine.update(dt)
            except Exception:
                logger.error("Weather engine update failed", exc_info=True)
                if self._strict_mode:
                    raise

        # TimeOfDayEngine is query-only — no per-tick update needed.

        if ctx.sea_state_engine is not None:
            try:
                ctx.sea_state_engine.update(dt)
            except Exception:
                logger.error("Sea state engine update failed", exc_info=True)
                if self._strict_mode:
                    raise

        if ctx.seasons_engine is not None and hasattr(ctx.seasons_engine, "update"):
            try:
                ctx.seasons_engine.update(clock)
            except Exception:
                logger.error("Seasons engine update failed", exc_info=True)
                if self._strict_mode:
                    raise

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
                logger.error("Space engine update failed", exc_info=True)
                if self._strict_mode:
                    raise

        # Phase 18: CBRN domain
        if ctx.cbrn_engine is not None and hasattr(ctx.cbrn_engine, "update"):
            try:
                elapsed = clock.elapsed.total_seconds()
                ctx.cbrn_engine.update(
                    dt, elapsed,
                    units_by_side=ctx.units_by_side,
                    weather_conditions=ctx.weather_engine,
                    classification=ctx.classification,
                    heightmap=ctx.heightmap,
                    time_of_day=ctx.time_of_day_engine,
                    timestamp=clock.current_time,
                )
            except Exception:
                logger.error("CBRN engine update failed", exc_info=True)
                if self._strict_mode:
                    raise

        # Phase 25: EW domain
        self._update_ew(dt)

        # Phase 52d: SIGINT fusion (after space + EW updates)
        self._fuse_sigint()

        # Phase 54: era-specific per-tick engine updates
        era = getattr(ctx.config, "era", "modern")

        # Phase 54b: WW1 barrage engine update (advance/drift barrages)
        if era == "ww1":
            barrage_eng = getattr(ctx, "barrage_engine", None)
            if barrage_eng is not None:
                try:
                    trench_eng = getattr(ctx, "trench_engine", None)
                    barrage_eng.update(dt, trench_engine=trench_eng)
                except Exception:
                    logger.debug("Barrage engine update failed", exc_info=True)

        # Phase 54c: Napoleonic courier delivery
        if era == "napoleonic":
            courier_eng = getattr(ctx, "courier_engine", None)
            if courier_eng is not None:
                try:
                    sim_time = clock.elapsed.total_seconds()
                    delivered = courier_eng.update(sim_time)
                    if delivered:
                        logger.debug("Courier: %d messages delivered", len(delivered))
                except Exception:
                    logger.debug("Courier update failed", exc_info=True)

        # Phase 54d: Ancient formation transitions + naval oar fatigue + visual signals
        if era == "ancient":
            af_eng = getattr(ctx, "formation_ancient_engine", None)
            if af_eng is not None:
                try:
                    completed = af_eng.update(dt)
                    if completed:
                        logger.debug("Formation transitions completed: %s", completed)
                except Exception:
                    logger.debug("Ancient formation update failed", exc_info=True)

            oar_eng = getattr(ctx, "naval_oar_engine", None)
            if oar_eng is not None:
                try:
                    oar_eng.update(dt)
                except Exception:
                    logger.debug("Naval oar update failed", exc_info=True)

            vs_eng = getattr(ctx, "visual_signals_engine", None)
            if vs_eng is not None:
                try:
                    sim_time = clock.elapsed.total_seconds()
                    delivered = vs_eng.update(dt, sim_time)
                    if delivered:
                        logger.debug("Visual signals: %d delivered", len(delivered))
                except Exception:
                    logger.debug("Visual signal update failed", exc_info=True)

        # Phase 44c / 56b: Maintenance engine — equipment breakdowns + readiness
        if ctx.maintenance_engine is not None:
            try:
                dt_hours = dt / 3600.0
                temp_c = 20.0
                if ctx.weather_engine is not None:
                    try:
                        temp_c = ctx.weather_engine.current.temperature
                    except Exception:
                        pass
                ctx.maintenance_engine.update(
                    dt_hours=dt_hours, temperature_c=temp_c,
                    timestamp=ctx.clock.current_time,
                )
                # Phase 56b: complete in-progress repairs
                ctx.maintenance_engine.complete_repairs(
                    dt_hours=dt_hours, timestamp=ctx.clock.current_time,
                )
                # Phase 56b: readiness = 0 → DISABLED
                for _su_list in getattr(ctx, "units_by_side", {}).values():
                    for _u in _su_list:
                        if _u.status != UnitStatus.ACTIVE:
                            continue
                        try:
                            _rd = ctx.maintenance_engine.get_unit_readiness(
                                _u.entity_id,
                            )
                            if _rd <= 0.0:
                                object.__setattr__(
                                    _u, "status", UnitStatus.DISABLED,
                                )
                        except (KeyError, Exception):
                            pass
            except Exception:
                logger.error("Maintenance update failed", exc_info=True)
                if self._strict_mode:
                    raise

        # Phase 44c: Medical engine — casualty processing
        if ctx.medical_engine is not None:
            try:
                ctx.medical_engine.update(
                    dt / 3600.0, ctx.clock.current_time,
                )
            except Exception:
                logger.error("Medical update failed", exc_info=True)
                if self._strict_mode:
                    raise

    # ── EW ────────────────────────────────────────────────────────────

    def _update_ew(self, dt: float) -> None:
        """Update EW engines for the current tick."""
        ctx = self._ctx
        if ctx.ew_engine is not None and hasattr(ctx.ew_engine, "update"):
            try:
                ctx.ew_engine.update(dt)
            except Exception:
                logger.error("EW jamming engine update failed", exc_info=True)
                if self._strict_mode:
                    raise
        if ctx.ew_decoy_engine is not None and hasattr(ctx.ew_decoy_engine, "update"):
            try:
                ctx.ew_decoy_engine.update(dt)
            except Exception:
                logger.error("EW decoy engine update failed", exc_info=True)
                if self._strict_mode:
                    raise

    # ── Phase 52d: SIGINT fusion ──────────────────────────────────────

    def _fuse_sigint(self) -> None:
        """Fuse space-based and EW SIGINT reports into unified tracks."""
        ctx = self._ctx
        space = getattr(ctx, "space_engine", None)
        ew = getattr(ctx, "ew_engine", None)
        fusion = getattr(ctx, "intel_fusion_engine", None)
        if space is None or ew is None or fusion is None:
            return
        sigint_engine = getattr(ew, "sigint_engine", None)
        if sigint_engine is None:
            return
        ew_raw = sigint_engine.get_recent_reports(clear=True)
        if not ew_raw:
            return

        from stochastic_warfare.detection.intel_fusion import IntelReport, IntelSource

        # Convert SIGINTReport → IntelReport
        ew_reports: list[IntelReport] = []
        for r in ew_raw:
            if r.estimated_position is None:
                continue
            ew_reports.append(IntelReport(
                source=IntelSource.SIGINT,
                timestamp=r.timestamp or 0.0,
                reliability=0.7,
                target_position=r.estimated_position,
                position_uncertainty_m=r.position_uncertainty_m,
            ))

        # Collect space SIGINT reports (from ISR engine if available)
        space_isr = getattr(space, "isr_engine", None)
        space_reports: list[IntelReport] = []
        if space_isr is not None:
            raw_space = getattr(space_isr, "get_recent_reports", None)
            if raw_space is not None:
                for sr in raw_space(clear=True):
                    if getattr(sr, "target_position", None) is not None:
                        space_reports.append(IntelReport(
                            source=IntelSource.SIGINT,
                            timestamp=getattr(sr, "timestamp", 0.0) or 0.0,
                            reliability=0.7,
                            target_position=sr.target_position,
                            position_uncertainty_m=getattr(
                                sr, "position_uncertainty_m", 1000.0,
                            ),
                        ))

        if not space_reports and not ew_reports:
            return

        # Fuse for each side
        for side in getattr(ctx, "side_names", []):
            try:
                fusion.fuse_sigint_tracks(
                    side, space_reports, ew_reports,
                )
            except Exception:
                logger.debug("SIGINT fusion failed for side %s", side, exc_info=True)

    # ── Escalation ────────────────────────────────────────────────────

    def _update_escalation(self, dt: float) -> None:
        """Update escalation engines for the current tick.

        Runs after strategic AI tick, before engagement detection.
        Updates: escalation ladder, political pressure, consequences,
        war termination, insurgency, SOF, fire zones.
        """
        ctx = self._ctx
        timestamp = ctx.clock.current_time
        dt_hours = dt / 3600.0

        # Update incendiary fire zones
        if ctx.incendiary_engine is not None:
            ctx.incendiary_engine.update_fire_zones(dt)

        # Update SOF missions
        if ctx.sof_engine is not None:
            ctx.sof_engine.update(dt, timestamp)

        # Update insurgency with real data
        if ctx.insurgency_engine is not None:
            # Compute military presence from active units per side
            military_presence: dict[str, float] = {}
            for side_name, units in ctx.units_by_side.items():
                active_count = sum(1 for u in units if u.status == UnitStatus.ACTIVE)
                military_presence[side_name] = float(active_count)

            # Compute collateral from consequence engine if available
            collateral: dict[str, float] = {}
            if ctx.consequence_engine is not None and hasattr(ctx.consequence_engine, "get_collateral_by_region"):
                try:
                    collateral = ctx.consequence_engine.get_collateral_by_region()
                except Exception:
                    pass

            ctx.insurgency_engine.update_radicalization(
                dt_hours=dt_hours,
                collateral_by_region=collateral,
                military_presence_by_region=military_presence,
                economic_factor=0.5,
                aid_by_region={},
                psyop_by_region={},
                timestamp=timestamp,
            )

        # Phase 53e: Political pressure update
        if ctx.political_engine is not None:
            for _side_name in ctx.side_names():
                _active = sum(1 for u in ctx.units_by_side.get(_side_name, [])
                              if u.status == UnitStatus.ACTIVE)
                _total = len(ctx.units_by_side.get(_side_name, []))
                _casualties = _total - _active
                try:
                    ctx.political_engine.update(
                        side=_side_name,
                        dt_hours=dt_hours,
                        war_crime_count=0,
                        civilian_casualties=0,
                        prohibited_weapon_events=0,
                        media_visibility=0.3,
                        own_casualties=_casualties,
                        stalemate_indicator=0.0,
                        enemy_psyop_effectiveness=0.0,
                        perceived_existential_threat=0.0,
                        timestamp=timestamp,
                    )
                except Exception:
                    logger.debug("Political pressure update failed for %s", _side_name, exc_info=True)

        # Phase 44d: Collateral damage tracking
        if ctx.collateral_engine is not None:
            try:
                # CollateralEngine is event-driven (record_damage called on hits),
                # no per-tick update needed.
                pass
            except Exception:
                logger.error("Collateral engine update failed", exc_info=True)
                if self._strict_mode:
                    raise

        # Phase 55c-4: drone provocation — drones in contact can trigger
        # escalation level increase
        drone_prob = getattr(ctx, "calibration", {}).get("drone_provocation_prob", None)
        if drone_prob is not None and ctx.escalation_engine is not None:
            _drone_rng = ctx.rng_manager.get_stream(
                __import__(
                    "stochastic_warfare.core.types", fromlist=["ModuleId"]
                ).ModuleId.CORE
            )
            for side_name, side_units in ctx.units_by_side.items():
                for u in side_units:
                    if u.status != UnitStatus.ACTIVE:
                        continue
                    _utype = getattr(u, "unit_type_id", "") or ""
                    if any(kw in _utype.lower() for kw in ("drone", "uav", "ucav", "unmanned")):
                        if _drone_rng.random() < drone_prob:
                            try:
                                ctx.escalation_engine.evaluate_trigger(
                                    trigger_type="drone_provocation",
                                    side=side_name,
                                    context={"unit_id": u.entity_id},
                                )
                            except Exception:
                                logger.debug(
                                    "Drone provocation trigger failed for %s",
                                    u.entity_id, exc_info=True,
                                )
                        break  # one provocation check per side per tick

        # Check war termination
        if ctx.war_termination_engine is not None:
            if ctx.war_termination_engine.is_ceasefire_active():
                # Ceasefire freezes combat -- handled by victory evaluator
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

    def _forces_within_closing_range(self) -> bool:
        """Phase 55a: Check if opposing forces are within closing range.

        Returns ``True`` when the minimum distance between any pair of
        opposing active units is less than
        ``engagement_range * resolution_closing_range_mult``.  This prevents
        the engine from escalating to STRATEGIC resolution when forces are
        approaching — avoiding 3600s ticks that overshoot the engagement
        detection window.
        """
        ctx = self._ctx
        threshold = (
            self._campaign._config.engagement_detection_range_m
            * self._config.resolution_closing_range_mult
        )
        sides = list(ctx.units_by_side.keys())
        if len(sides) < 2:
            return False
        for i in range(len(sides)):
            units_a = [
                u for u in ctx.units_by_side[sides[i]]
                if u.status == UnitStatus.ACTIVE
            ]
            if not units_a:
                continue
            for j in range(i + 1, len(sides)):
                units_b = [
                    u for u in ctx.units_by_side[sides[j]]
                    if u.status == UnitStatus.ACTIVE
                ]
                if not units_b:
                    continue
                min_dist = self._battle._min_distance(units_a, units_b)
                if min_dist <= threshold:
                    return True
        return False

    def _update_resolution(self) -> None:
        """Switch tick resolution based on battle state.

        Phase 55a: Guards against STRATEGIC when forces are closing.
        """
        active = self._battle.active_battles
        if active:
            self._set_resolution(TickResolution.TACTICAL)
            return
        # Phase 55a: Don't escalate to STRATEGIC if forces are approaching
        if self._forces_within_closing_range():
            if self._resolution != TickResolution.OPERATIONAL:
                self._set_resolution(TickResolution.OPERATIONAL)
            return
        # Normal de-escalation
        if self._resolution == TickResolution.TACTICAL:
            self._set_resolution(TickResolution.OPERATIONAL)
        elif self._resolution == TickResolution.OPERATIONAL:
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
