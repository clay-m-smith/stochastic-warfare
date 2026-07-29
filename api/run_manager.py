"""Async simulation run execution manager.

Handles single runs and Monte Carlo batches, with progress streaming
via asyncio.Queue for WebSocket consumers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from typing import TYPE_CHECKING, Any

from api.database import Database

if TYPE_CHECKING:
    from stochastic_warfare.simulation.loadouts import WeaponAttachment
    from stochastic_warfare.simulation.scenario import CampaignScenarioConfig

logger = logging.getLogger(__name__)


class RunCancelledError(RuntimeError):
    """Raised inside a worker when cooperative cancellation is requested."""


class RunManagerClosedError(RuntimeError):
    """Raised when work is submitted after manager shutdown begins."""


class RunManager:
    """Manages background simulation execution with progress streaming."""

    def __init__(self, db: Database, *, data_dir: str, max_concurrent: int = 4,
                 max_stored_events: int = 50_000, default_max_ticks: int = 10_000) -> None:
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be at least 1")
        self._db = db
        self._data_dir = Path(data_dir)
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max_stored_events = max_stored_events
        self._default_max_ticks = default_max_ticks
        self._progress_queues: dict[str, list[asyncio.Queue]] = {}
        self._cancel_events: dict[str, Event] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._lifecycle_lock = asyncio.Lock()
        self._shutdown_task: asyncio.Task[None] | None = None
        self._closing = False
        self._closed = False

    async def submit(
        self,
        scenario_name: str,
        scenario_path: str,
        seed: int,
        max_ticks: int,
        config_overrides: dict[str, Any] | None = None,
        frame_interval: int | None = None,
    ) -> str:
        """Submit a run for background execution. Returns run_id."""
        if self._closing or self._closed:
            raise RunManagerClosedError("Run manager is shutting down")

        from stochastic_warfare.simulation.scenario import (
            load_campaign_scenario_config,
        )

        patch = dict(config_overrides or {})
        effective_config = await asyncio.to_thread(
            load_campaign_scenario_config,
            Path(scenario_path),
            patch,
        )
        run_id = uuid.uuid4().hex[:12]
        async with self._lifecycle_lock:
            if self._closing or self._closed:
                raise RunManagerClosedError("Run manager is shutting down")
            await self._db.create_run(
                run_id,
                scenario_name,
                scenario_path,
                seed,
                max_ticks,
                patch,
            )
            self._progress_queues[run_id] = []
            cancel_event = Event()
            self._cancel_events[run_id] = cancel_event
            try:
                task = asyncio.create_task(
                    self._execute_run(
                        run_id,
                        scenario_path,
                        seed,
                        max_ticks,
                        effective_config,
                        cancel_event,
                        frame_interval,
                    ),
                )
            except Exception as exc:
                self._progress_queues.pop(run_id, None)
                self._cancel_events.pop(run_id, None)
                await self._db.update_run_status(
                    run_id,
                    "failed",
                    completed_at=datetime.now(timezone.utc).isoformat(),
                    error_message=f"Could not schedule run: {exc}",
                )
                raise
            self._tasks[run_id] = task
            task.add_done_callback(self._retrieve_task_result)
        return run_id

    def subscribe(self, run_id: str) -> asyncio.Queue | None:
        """Subscribe to progress updates for a run. Returns a Queue or None if not active."""
        queues = self._progress_queues.get(run_id)
        if queues is None:
            return None
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        queues.append(q)
        return q

    def unsubscribe(self, run_id: str, queue: asyncio.Queue) -> None:
        """Unsubscribe a queue from progress updates."""
        queues = self._progress_queues.get(run_id)
        if queues is not None:
            try:
                queues.remove(queue)
            except ValueError:
                pass

    @staticmethod
    def _retrieve_task_result(task: asyncio.Task[None]) -> None:
        """Consume and report exceptions even after task bookkeeping is gone."""
        try:
            exception = task.exception()
        except asyncio.CancelledError:
            return
        if exception is not None:
            logger.error(
                "Background task ended with an exception",
                exc_info=(
                    type(exception),
                    exception,
                    exception.__traceback__,
                ),
            )

    @staticmethod
    async def _await_worker(
        worker_future: asyncio.Future[dict[str, Any]],
        cancel_event: Event,
    ) -> dict[str, Any]:
        """Keep ownership until an executor worker stops, even if cancelled."""
        try:
            return await asyncio.shield(worker_future)
        except asyncio.CancelledError:
            cancel_event.set()
            while not worker_future.done():
                try:
                    await asyncio.shield(worker_future)
                except asyncio.CancelledError:
                    cancel_event.set()
                except BaseException:
                    break
            try:
                worker_future.result()
            except RunCancelledError:
                pass
            except BaseException as exception:
                logger.error(
                    "Executor worker failed while stopping after cancellation",
                    exc_info=(
                        type(exception),
                        exception,
                        exception.__traceback__,
                    ),
                )
            raise

    @staticmethod
    def _put_progress(
        queue: asyncio.Queue,
        message: dict[str, Any],
    ) -> None:
        """Deliver best-effort progress without leaking QueueFull callbacks."""
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            pass

    @staticmethod
    def _signal_terminal(queue: asyncio.Queue) -> None:
        """Guarantee room for the terminal sentinel on a bounded queue."""
        try:
            queue.put_nowait(None)
            return
        except asyncio.QueueFull:
            pass
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
        queue.put_nowait(None)

    async def cancel(self, run_id: str) -> bool:
        """Request cancellation of a running job."""
        async with self._lifecycle_lock:
            cancel_event = self._cancel_events.get(run_id)
            if cancel_event is None:
                return False
            cancel_event.set()
            return True

    async def cancel_and_wait(self, run_id: str) -> bool:
        """Cancel an active job and wait for its terminal persistence."""
        async with self._lifecycle_lock:
            cancel_event = self._cancel_events.get(run_id)
            task = self._tasks.get(run_id)
            if cancel_event is None or task is None:
                return False
            cancel_event.set()
        await asyncio.shield(task)
        return True

    async def shutdown(self, timeout: float = 5.0) -> None:
        """Cooperatively stop all work before allowing database teardown."""
        async with self._lifecycle_lock:
            if self._shutdown_task is None:
                self._closing = True
                for cancel_event in self._cancel_events.values():
                    cancel_event.set()
                tasks = list(self._tasks.values())
                self._shutdown_task = asyncio.create_task(
                    self._finish_shutdown(tasks, timeout),
                )
            shutdown_task = self._shutdown_task

        caller_cancelled = False
        while True:
            try:
                await asyncio.shield(shutdown_task)
                break
            except asyncio.CancelledError:
                if shutdown_task.done():
                    raise
                caller_cancelled = True

        if caller_cancelled:
            raise asyncio.CancelledError

    async def _finish_shutdown(
        self,
        tasks: list[asyncio.Task[None]],
        timeout: float,
    ) -> None:
        """Finish shared shutdown independently of cancelling callers."""
        try:
            if tasks:
                _, pending = await asyncio.wait(tasks, timeout=timeout)
                if pending:
                    logger.warning(
                        "Shutdown grace threshold reached; waiting for %d "
                        "cooperative worker(s)",
                        len(pending),
                    )
                await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            async with self._lifecycle_lock:
                self._closed = True

    async def _execute_run(
        self,
        run_id: str,
        scenario_path: str,
        seed: int,
        max_ticks: int,
        effective_config: CampaignScenarioConfig,
        cancel_event: Event,
        frame_interval: int | None = None,
    ) -> None:
        """Execute a simulation run in a background thread."""
        loop = asyncio.get_running_loop()

        try:
            await self._db.update_run_status(
                run_id,
                "running",
                started_at=datetime.now(timezone.utc).isoformat(),
            )
            async with self._semaphore:
                worker_future = loop.run_in_executor(
                    None,
                    self._run_sync,
                    run_id,
                    scenario_path,
                    seed,
                    max_ticks,
                    effective_config,
                    loop,
                    None,
                    frame_interval,
                    cancel_event,
                )
                result = await self._await_worker(
                    worker_future,
                    cancel_event,
                )

            now = datetime.now(timezone.utc).isoformat()
            await self._db.update_run_status(
                run_id, "completed",
                completed_at=now,
                result_json=json.dumps(result["summary"], default=str),
                events_json=json.dumps(result["events"], default=str),
                snapshots_json=json.dumps(result["snapshots"], default=str),
                terrain_json=json.dumps(result["terrain"], default=str),
                frames_json=json.dumps(result["frames"], default=str),
            )
        except RunCancelledError:
            await self._db.update_run_status(
                run_id,
                "cancelled",
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
        except asyncio.CancelledError:
            cancel_event.set()
            await asyncio.shield(
                self._db.update_run_status(
                    run_id,
                    "cancelled",
                    completed_at=datetime.now(timezone.utc).isoformat(),
                ),
            )
            raise
        except Exception as exc:
            now = datetime.now(timezone.utc).isoformat()
            await self._db.update_run_status(
                run_id, "failed",
                completed_at=now,
                error_message=str(exc),
            )
        finally:
            # Send terminal sentinel to all subscribers
            for q in list(self._progress_queues.get(run_id, [])):
                self._signal_terminal(q)
            # Cleanup
            self._progress_queues.pop(run_id, None)
            self._cancel_events.pop(run_id, None)
            self._tasks.pop(run_id, None)

    def _run_sync(
        self,
        run_id: str,
        scenario_path: str,
        seed: int,
        max_ticks: int,
        effective_config: CampaignScenarioConfig,
        loop: asyncio.AbstractEventLoop,
        queue: asyncio.Queue | None,
        frame_interval: int | None = None,
        cancel_event: Event | None = None,
    ) -> dict[str, Any]:
        """Core synchronous simulation execution (runs in thread pool)."""
        from stochastic_warfare.entities.base import UnitStatus
        from stochastic_warfare.simulation.engine import EngineConfig, SimulationEngine
        from stochastic_warfare.simulation.recorder import SimulationRecorder
        from stochastic_warfare.simulation.scenario import ScenarioLoader, VictoryConditionConfig
        from stochastic_warfare.simulation.victory import ObjectiveState, VictoryEvaluator
        from stochastic_warfare.core.types import Position
        from stochastic_warfare.tools.serializers import serialize_to_dict

        path = Path(scenario_path)
        loader = ScenarioLoader(self._data_dir)
        ctx = loader.load(
            path,
            seed=seed,
            scenario_config=effective_config,
        )
        config_dict = ctx.config.model_dump(mode="json")

        # Capture static terrain data (Phase 35)
        terrain_data = self._capture_terrain(ctx, config_dict)

        # Build victory evaluator
        objectives = []
        for obj_cfg in config_dict.get("objectives", []):
            pos_list = obj_cfg.get("position", [0.0, 0.0])
            objectives.append(ObjectiveState(
                objective_id=obj_cfg["objective_id"],
                position=Position(easting=pos_list[0], northing=pos_list[1]),
                radius_m=obj_cfg.get("radius_m", 500.0),
            ))

        conditions = [VictoryConditionConfig(**vc) for vc in config_dict.get("victory_conditions", [])]
        # Default: end when any side loses 70%+ of forces
        if not conditions:
            conditions = [VictoryConditionConfig(type="force_destroyed")]
        max_dur = config_dict.get("duration_hours", 24) * 3600.0

        victory_eval = VictoryEvaluator(
            objectives=objectives,
            conditions=conditions,
            event_bus=ctx.event_bus,
            max_duration_s=max_dur,
        )

        recorder = SimulationRecorder(ctx.event_bus)
        engine = SimulationEngine(
            ctx,
            config=EngineConfig(max_ticks=max_ticks),
            victory_evaluator=victory_eval,
            recorder=recorder,
        )

        # Step-based loop with progress
        recorder.start()
        game_over = False
        progress_interval = max(1, max_ticks // 100)

        # Frame interval: use scenario duration to estimate actual ticks
        tick_res = config_dict.get("tick_resolution")
        if tick_res and isinstance(tick_res, dict):
            # Campaign scenarios use tick_resolution — strategic_s is the
            # dominant tick duration (engine starts at strategic resolution)
            tick_dur = tick_res.get("strategic_s", 3600)
        else:
            tick_dur = config_dict.get("tick_duration_seconds", 5.0)
        dur_hours = config_dict.get("duration_hours", 24)
        expected_ticks = int(dur_hours * 3600.0 / tick_dur)
        actual_ticks = min(max_ticks, expected_ticks)
        if frame_interval is not None:
            fi = max(1, frame_interval)
        else:
            fi = max(1, actual_ticks // 500)
        map_frames: list[dict] = []

        while not game_over:
            # Check cancellation
            if cancel_event is not None and cancel_event.is_set():
                raise RunCancelledError("Run cancelled by user")

            game_over = engine.step()
            tick = ctx.clock.tick_count

            # Capture position frame at dynamic intervals (Phase 35)
            if tick % fi == 0 or game_over:
                # Phase 92: build engaged set from events recorded this tick
                _engaged: set[str] = set()
                for _ev in recorder.events:
                    if _ev.tick == tick and _ev.event_type == "EngagementEvent":
                        _engaged.add(_ev.data.get("attacker_id", ""))
                        _engaged.add(_ev.data.get("target_id", ""))
                _engaged.discard("")

                _bm = getattr(engine, "battle_manager", None)
                map_frames.append(self._capture_frame(
                    tick, ctx,
                    morale_states=getattr(ctx, "morale_states", None),
                    suppression_states=getattr(_bm, "_suppression_states", None) if _bm else None,
                    engaged_ids=_engaged,
                    unit_weapons=ctx.unit_weapons,
                ))

            # Emit progress to all subscribers
            if tick % progress_interval == 0 or game_over:
                active_units: dict[str, int] = {}
                for side, units in ctx.units_by_side.items():
                    active_units[side] = sum(1 for u in units if u.status == UnitStatus.ACTIVE)

                progress = {
                    "type": "tick",
                    "tick": tick,
                    "max_ticks": max_ticks,
                    "elapsed_s": ctx.clock.elapsed.total_seconds(),
                    "active_units": active_units,
                    "game_over": game_over,
                }
                for q in list(self._progress_queues.get(run_id, [])):
                    try:
                        loop.call_soon_threadsafe(
                            self._put_progress,
                            q,
                            progress,
                        )
                    except RuntimeError:
                        pass

        recorder.stop()

        # Build summary
        run_result = engine._last_victory
        side_summaries = {}
        for side, units in ctx.units_by_side.items():
            active = sum(1 for u in units if u.status == UnitStatus.ACTIVE)
            disabled = sum(1 for u in units if u.status == UnitStatus.DISABLED)
            destroyed = sum(1 for u in units if u.status == UnitStatus.DESTROYED)
            side_summaries[side] = {
                "total": len(units),
                "active": active,
                "disabled": disabled,
                "destroyed": destroyed,
            }

        # Transform VictoryResult into frontend-friendly format
        victory_raw = serialize_to_dict(run_result)
        ct = victory_raw.get("condition_type", "")
        ws = victory_raw.get("winning_side", "")
        if ws and ws != "draw":
            status = "decisive"
        elif ws == "draw":
            status = "draw"
        elif ct:
            status = ct
        else:
            status = "unknown"
        victory_dict = {
            "status": status,
            "winner": ws if ws and ws != "draw" else None,
            "winning_side": ws,
            "condition_type": ct,
            "message": victory_raw.get("message", ""),
        }

        summary = {
            "scenario": config_dict.get("name", path.stem),
            "seed": seed,
            "ticks_executed": ctx.clock.tick_count,
            "duration_s": ctx.clock.elapsed.total_seconds(),
            "victory": victory_dict,
            "sides": side_summaries,
        }

        events = [serialize_to_dict(e) for e in recorder.events[:self._max_stored_events]]
        snapshots = [{"tick": s.tick} for s in recorder.snapshots]

        return {
            "summary": summary,
            "events": events,
            "snapshots": snapshots,
            "terrain": terrain_data,
            "frames": map_frames,
        }

    # ── Map data capture (Phase 35) ─────────────────────────────────

    @staticmethod
    def _capture_terrain(ctx: Any, config_dict: dict[str, Any]) -> dict[str, Any]:
        """Extract static terrain data from simulation context."""
        terrain: dict[str, Any] = {
            "width_cells": 0,
            "height_cells": 0,
            "cell_size": 100.0,
            "origin_easting": 0.0,
            "origin_northing": 0.0,
            "land_cover": [],
            "objectives": [],
            "extent": [],
        }

        heightmap = getattr(ctx, "heightmap", None)
        if heightmap is not None:
            cell_size = getattr(heightmap, "cell_size", 100.0)
            shape = getattr(heightmap, "shape", (0, 0))
            extent = getattr(heightmap, "extent", None)
            terrain["cell_size"] = float(cell_size)
            terrain["height_cells"] = int(shape[0])
            terrain["width_cells"] = int(shape[1])
            if extent is not None:
                # extent from heightmap is (min_e, max_e, min_n, max_n)
                terrain["origin_easting"] = float(extent[0])   # min_easting
                terrain["origin_northing"] = float(extent[2])  # min_northing
                # Frontend expects [minX, minY, maxX, maxY]
                terrain["extent"] = [
                    float(extent[0]), float(extent[2]),  # min_e, min_n
                    float(extent[1]), float(extent[3]),  # max_e, max_n
                ]

        if heightmap is not None:
            raw = getattr(heightmap, "_data", None)
            if raw is not None:
                import numpy as np
                if isinstance(raw, np.ndarray):
                    terrain["elevation"] = raw.tolist()

        classification = getattr(ctx, "classification", None)
        if classification is not None:
            state = classification.get_state()
            lc = state.get("land_cover")
            if lc is not None:
                import numpy as np
                if isinstance(lc, np.ndarray):
                    terrain["land_cover"] = lc.tolist()
                else:
                    terrain["land_cover"] = [list(row) for row in lc]

        # Generate default land_cover grid for synthetic terrain
        if not terrain["land_cover"] and terrain["height_cells"] > 0 and terrain["width_cells"] > 0:
            # Map terrain_type -> land cover code
            terrain_type = config_dict.get("terrain", {}).get("terrain_type", "flat_desert")
            lc_map = {
                "flat_desert": 11,     # DESERT_SAND
                "open_ocean": 9,       # WATER
                "hilly_defense": 1,    # GRASSLAND
                "trench_warfare": 14,  # CULTIVATED
                "open_field": 0,       # OPEN
            }
            code = lc_map.get(terrain_type, 0)
            h, w = terrain["height_cells"], terrain["width_cells"]
            terrain["land_cover"] = [[code] * w for _ in range(h)]

        for obj_cfg in config_dict.get("objectives", []):
            pos = obj_cfg.get("position", [0.0, 0.0])
            terrain["objectives"].append({
                "id": obj_cfg.get("objective_id", ""),
                "x": float(pos[0]),
                "y": float(pos[1]),
                "radius": float(obj_cfg.get("radius_m", 500.0)),
            })

        return terrain

    @staticmethod
    def _capture_frame(
        tick: int,
        ctx: Any,
        *,
        morale_states: dict | None = None,
        suppression_states: dict | None = None,
        engaged_ids: set[str] | None = None,
        unit_weapons: Mapping[str, tuple[WeaponAttachment, ...]] | None = None,
    ) -> dict[str, Any]:
        """Capture unit positions and enriched state for a single tick."""
        units = []
        for side, unit_list in ctx.units_by_side.items():
            for u in unit_list:
                uid = str(u.entity_id)
                unit_entry: dict[str, Any] = {
                    "id": uid,
                    "side": side,
                    "x": float(u.position.easting),
                    "y": float(u.position.northing),
                    "d": int(u.domain.value) if hasattr(u.domain, "value") else 0,
                    "s": int(u.status.value) if hasattr(u.status, "value") else 0,
                    "h": round(float(getattr(u, "heading", 0.0)), 1),
                    "t": str(getattr(u, "unit_type", "")),
                }
                # Sensor range (Phase 38b)
                unit_sensors = getattr(ctx, "unit_sensors", {})
                sensors = unit_sensors.get(uid, [])
                if sensors:
                    max_range = max(
                        (getattr(s, "effective_range", 0.0) for s in sensors),
                        default=0.0,
                    )
                    if max_range > 0:
                        unit_entry["sr"] = round(max_range, 0)

                # Phase 92: enriched unit state
                # Morale
                if morale_states is not None:
                    ms = morale_states.get(uid, 0)
                    unit_entry["mo"] = int(ms.value) if hasattr(ms, "value") else int(ms)

                # Posture (domain-specific)
                for attr in ("posture", "air_posture", "naval_posture"):
                    p = getattr(u, attr, None)
                    if p is not None:
                        unit_entry["po"] = p.name if hasattr(p, "name") else str(p)
                        break

                # Health (fraction of effective personnel)
                personnel = getattr(u, "personnel", None)
                if personnel:
                    eff = sum(1 for p in personnel if getattr(p, "is_effective", lambda: True)())
                    unit_entry["hp"] = round(eff / len(personnel), 2)
                else:
                    # No personnel — infer from status
                    status_val = unit_entry["s"]
                    unit_entry["hp"] = 0.0 if status_val >= 3 else 1.0  # DESTROYED=3+

                # Fuel
                fuel = getattr(u, "fuel_remaining", None)
                if fuel is not None:
                    unit_entry["fp"] = round(float(fuel), 2)

                # Ammo (aggregate across all weapons)
                if unit_weapons is not None:
                    attachments = unit_weapons.get(uid, ())
                    total_remaining = 0
                    total_initial = 0
                    for attachment in attachments:
                        ammo_state = attachment.weapon.ammo_state
                        remaining = sum(ammo_state.rounds_by_type.values())
                        fired = ammo_state.total_rounds_fired
                        total_remaining += remaining
                        total_initial += remaining + fired
                    if total_initial > 0:
                        unit_entry["ap"] = round(total_remaining / total_initial, 2)

                # Suppression
                if suppression_states is not None:
                    ss = suppression_states.get(uid)
                    if ss is not None:
                        # UnitSuppressionState.value is float 0.0-1.0; map to int 0-4
                        sv = getattr(ss, "value", 0.0)
                        if isinstance(sv, (int, float)):
                            unit_entry["su"] = min(4, int(sv * 4))

                # Engaged
                if engaged_ids and uid in engaged_ids:
                    unit_entry["eg"] = True

                units.append(unit_entry)
        # FOW detection data (Phase 38a)
        detected: dict[str, list[str]] = {}
        fow = getattr(ctx, "fog_of_war", None)
        if fow is not None:
            for side in ctx.units_by_side:
                try:
                    wv = fow.get_world_view(side)
                    detected[side] = sorted(wv.contacts.keys())
                except Exception:
                    pass

        result: dict[str, Any] = {"tick": tick, "units": units}
        if detected:
            result["det"] = detected
        return result

    # ── Batch ────────────────────────────────────────────────────────

    async def submit_batch(
        self,
        scenario_name: str,
        scenario_path: str,
        num_iterations: int,
        base_seed: int,
        max_ticks: int,
    ) -> str:
        """Submit a Monte Carlo batch for background execution."""
        if self._closing or self._closed:
            raise RunManagerClosedError("Run manager is shutting down")

        from stochastic_warfare.simulation.scenario import (
            load_campaign_scenario_config,
        )

        effective_config = await asyncio.to_thread(
            load_campaign_scenario_config,
            Path(scenario_path),
        )
        batch_id = uuid.uuid4().hex[:12]
        async with self._lifecycle_lock:
            if self._closing or self._closed:
                raise RunManagerClosedError("Run manager is shutting down")
            await self._db.create_batch(
                batch_id,
                scenario_name,
                scenario_path,
                num_iterations,
                base_seed,
                max_ticks,
            )
            self._progress_queues[batch_id] = []
            cancel_event = Event()
            self._cancel_events[batch_id] = cancel_event
            try:
                task = asyncio.create_task(
                    self._execute_batch(
                        batch_id,
                        scenario_path,
                        num_iterations,
                        base_seed,
                        max_ticks,
                        effective_config,
                        cancel_event,
                    ),
                )
            except Exception as exc:
                self._progress_queues.pop(batch_id, None)
                self._cancel_events.pop(batch_id, None)
                await self._db.update_batch(
                    batch_id,
                    status="failed",
                    completed_at=datetime.now(timezone.utc).isoformat(),
                    error_message=f"Could not schedule batch: {exc}",
                )
                raise
            self._tasks[batch_id] = task
            task.add_done_callback(self._retrieve_task_result)
        return batch_id

    async def _execute_batch(
        self,
        batch_id: str,
        scenario_path: str,
        num_iterations: int,
        base_seed: int,
        max_ticks: int,
        effective_config: CampaignScenarioConfig,
        cancel_event: Event,
    ) -> None:
        """Execute a Monte Carlo batch sequentially."""
        import numpy as np

        loop = asyncio.get_running_loop()

        try:
            await self._db.update_batch(batch_id, status="running")
            all_metrics: dict[str, list[float]] = {}
            completed = 0

            for i in range(num_iterations):
                if cancel_event.is_set():
                    raise RunCancelledError("Batch cancelled by user")

                seed = base_seed + i
                async with self._semaphore:
                    worker_future = loop.run_in_executor(
                        None,
                        self._run_sync,
                        f"batch_{batch_id}_{i}",
                        scenario_path,
                        seed,
                        max_ticks,
                        effective_config,
                        loop,
                        None,
                        None,
                        cancel_event,
                    )
                    result = await self._await_worker(
                        worker_future,
                        cancel_event,
                    )

                # Extract metrics
                for side, data in result["summary"].get("sides", {}).items():
                    for key in ("destroyed", "active", "total"):
                        metric_name = f"{side}_{key}"
                        all_metrics.setdefault(metric_name, []).append(float(data.get(key, 0)))

                completed += 1
                await self._db.update_batch(batch_id, completed_iterations=completed)

                # Emit progress to all subscribers
                progress = {
                    "type": "iteration",
                    "iteration": i + 1,
                    "total": num_iterations,
                    "seed": seed,
                }
                for q in list(self._progress_queues.get(batch_id, [])):
                    self._put_progress(q, progress)

            # Compute statistics
            stats: dict[str, Any] = {}
            for metric_name, values in all_metrics.items():
                arr = np.array(values)
                stats[metric_name] = {
                    "mean": float(np.mean(arr)),
                    "median": float(np.median(arr)),
                    "std": float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0,
                    "min": float(np.min(arr)),
                    "max": float(np.max(arr)),
                    "p5": float(np.percentile(arr, 5)),
                    "p95": float(np.percentile(arr, 95)),
                    "n": len(values),
                }

            now = datetime.now(timezone.utc).isoformat()
            await self._db.update_batch(
                batch_id,
                status="completed",
                completed_at=now,
                metrics_json=json.dumps(stats, default=str),
            )
        except RunCancelledError:
            await self._db.update_batch(
                batch_id,
                status="cancelled",
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
        except asyncio.CancelledError:
            cancel_event.set()
            await asyncio.shield(
                self._db.update_batch(
                    batch_id,
                    status="cancelled",
                    completed_at=datetime.now(timezone.utc).isoformat(),
                ),
            )
            raise
        except Exception as exc:
            now = datetime.now(timezone.utc).isoformat()
            await self._db.update_batch(
                batch_id,
                status="failed",
                completed_at=now,
                error_message=str(exc),
            )
        finally:
            for q in list(self._progress_queues.get(batch_id, [])):
                self._signal_terminal(q)
            self._progress_queues.pop(batch_id, None)
            self._cancel_events.pop(batch_id, None)
            self._tasks.pop(batch_id, None)
