"""Async simulation run execution manager.

Handles single runs and Monte Carlo batches, with progress streaming
via asyncio.Queue for WebSocket consumers.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from api.database import Database


class RunManager:
    """Manages background simulation execution with progress streaming."""

    def __init__(self, db: Database, *, data_dir: str, max_concurrent: int = 4,
                 max_stored_events: int = 50_000, default_max_ticks: int = 10_000) -> None:
        self._db = db
        self._data_dir = Path(data_dir)
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max_stored_events = max_stored_events
        self._default_max_ticks = default_max_ticks
        self._progress_queues: dict[str, asyncio.Queue] = {}
        self._cancel_flags: dict[str, bool] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    async def submit(
        self,
        scenario_name: str,
        scenario_path: str,
        seed: int,
        max_ticks: int,
        config_overrides: dict[str, Any] | None = None,
    ) -> str:
        """Submit a run for background execution. Returns run_id."""
        run_id = uuid.uuid4().hex[:12]
        await self._db.create_run(
            run_id, scenario_name, scenario_path, seed, max_ticks, config_overrides,
        )
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._progress_queues[run_id] = queue
        self._cancel_flags[run_id] = False
        task = asyncio.create_task(self._execute_run(run_id, scenario_path, seed, max_ticks, config_overrides or {}))
        self._tasks[run_id] = task
        return run_id

    def get_progress_queue(self, run_id: str) -> asyncio.Queue | None:
        """Get the progress queue for a run, if it exists."""
        return self._progress_queues.get(run_id)

    async def cancel(self, run_id: str) -> bool:
        """Request cancellation of a running job."""
        if run_id in self._cancel_flags:
            self._cancel_flags[run_id] = True
            return True
        return False

    async def _execute_run(
        self,
        run_id: str,
        scenario_path: str,
        seed: int,
        max_ticks: int,
        config_overrides: dict[str, Any],
    ) -> None:
        """Execute a simulation run in a background thread."""
        loop = asyncio.get_running_loop()
        queue = self._progress_queues.get(run_id)

        await self._db.update_run_status(
            run_id, "running",
            started_at=datetime.now(timezone.utc).isoformat(),
        )

        try:
            async with self._semaphore:
                result = await loop.run_in_executor(
                    None,
                    self._run_sync,
                    run_id, scenario_path, seed, max_ticks, config_overrides,
                    loop, queue,
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
        except Exception as exc:
            now = datetime.now(timezone.utc).isoformat()
            await self._db.update_run_status(
                run_id, "failed",
                completed_at=now,
                error_message=str(exc),
            )
        finally:
            # Send terminal sentinel
            if queue is not None:
                try:
                    queue.put_nowait(None)
                except asyncio.QueueFull:
                    pass
            # Cleanup
            self._progress_queues.pop(run_id, None)
            self._cancel_flags.pop(run_id, None)
            self._tasks.pop(run_id, None)

    def _run_sync(
        self,
        run_id: str,
        scenario_path: str,
        seed: int,
        max_ticks: int,
        config_overrides: dict[str, Any],
        loop: asyncio.AbstractEventLoop,
        queue: asyncio.Queue | None,
    ) -> dict[str, Any]:
        """Core synchronous simulation execution (runs in thread pool)."""
        from stochastic_warfare.entities.base import UnitStatus
        from stochastic_warfare.simulation.engine import EngineConfig, SimulationEngine
        from stochastic_warfare.simulation.recorder import SimulationRecorder
        from stochastic_warfare.simulation.scenario import ScenarioLoader, VictoryConditionConfig
        from stochastic_warfare.simulation.victory import ObjectiveState, VictoryEvaluator
        from stochastic_warfare.core.types import Position
        from stochastic_warfare.tools.serializers import serialize_to_dict
        import yaml

        path = Path(scenario_path)
        with open(path) as f:
            config_dict = yaml.safe_load(f)

        loader = ScenarioLoader(self._data_dir)
        ctx = loader.load(path, seed=seed)

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
        frame_interval = max(1, max_ticks // 500)
        map_frames: list[dict] = []

        while not game_over:
            # Check cancellation
            if self._cancel_flags.get(run_id, False):
                raise RuntimeError("Run cancelled by user")

            game_over = engine.step()
            tick = ctx.clock.tick_count

            # Capture position frame at dynamic intervals (Phase 35)
            if tick % frame_interval == 0 or game_over:
                map_frames.append(self._capture_frame(tick, ctx))

            # Emit progress
            if queue is not None and (tick % progress_interval == 0 or game_over):
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
                try:
                    loop.call_soon_threadsafe(queue.put_nowait, progress)
                except (RuntimeError, asyncio.QueueFull):
                    pass

        recorder.stop()

        # Build summary
        run_result = engine._last_victory
        side_summaries = {}
        for side, units in ctx.units_by_side.items():
            active = sum(1 for u in units if u.status == UnitStatus.ACTIVE)
            destroyed = sum(1 for u in units if u.status == UnitStatus.DESTROYED)
            side_summaries[side] = {
                "total": len(units),
                "active": active,
                "destroyed": destroyed,
            }

        summary = {
            "scenario": config_dict.get("name", path.stem),
            "seed": seed,
            "ticks_executed": ctx.clock.tick_count,
            "duration_s": ctx.clock.elapsed.total_seconds(),
            "victory": serialize_to_dict(run_result),
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
                terrain["origin_easting"] = float(extent[0])
                terrain["origin_northing"] = float(extent[1])
                terrain["extent"] = [float(v) for v in extent]

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
    def _capture_frame(tick: int, ctx: Any) -> dict[str, Any]:
        """Capture unit positions for a single tick."""
        units = []
        for side, unit_list in ctx.units_by_side.items():
            for u in unit_list:
                units.append({
                    "id": str(u.entity_id),
                    "side": side,
                    "x": float(u.position.easting),
                    "y": float(u.position.northing),
                    "d": int(u.domain.value) if hasattr(u.domain, "value") else 0,
                    "s": int(u.status.value) if hasattr(u.status, "value") else 0,
                    "h": round(float(getattr(u, "heading", 0.0)), 1),
                    "t": str(getattr(u, "unit_type", "")),
                })
        return {"tick": tick, "units": units}

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
        batch_id = uuid.uuid4().hex[:12]
        await self._db.create_batch(
            batch_id, scenario_name, scenario_path,
            num_iterations, base_seed, max_ticks,
        )
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._progress_queues[batch_id] = queue
        self._cancel_flags[batch_id] = False
        task = asyncio.create_task(
            self._execute_batch(batch_id, scenario_path, num_iterations, base_seed, max_ticks),
        )
        self._tasks[batch_id] = task
        return batch_id

    async def _execute_batch(
        self,
        batch_id: str,
        scenario_path: str,
        num_iterations: int,
        base_seed: int,
        max_ticks: int,
    ) -> None:
        """Execute a Monte Carlo batch sequentially."""
        import numpy as np

        loop = asyncio.get_running_loop()
        queue = self._progress_queues.get(batch_id)

        await self._db.update_batch(batch_id, status="running")

        try:
            all_metrics: dict[str, list[float]] = {}
            completed = 0

            for i in range(num_iterations):
                if self._cancel_flags.get(batch_id, False):
                    raise RuntimeError("Batch cancelled by user")

                seed = base_seed + i
                result = await loop.run_in_executor(
                    None,
                    self._run_sync,
                    f"batch_{batch_id}_{i}", scenario_path, seed, max_ticks, {},
                    loop, None,
                )

                # Extract metrics
                for side, data in result["summary"].get("sides", {}).items():
                    for key in ("destroyed", "active", "total"):
                        metric_name = f"{side}_{key}"
                        all_metrics.setdefault(metric_name, []).append(float(data.get(key, 0)))

                completed += 1
                await self._db.update_batch(batch_id, completed_iterations=completed)

                # Emit progress
                if queue is not None:
                    progress = {
                        "type": "iteration",
                        "iteration": i + 1,
                        "total": num_iterations,
                        "seed": seed,
                    }
                    try:
                        queue.put_nowait(progress)
                    except asyncio.QueueFull:
                        pass

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
        except Exception as exc:
            now = datetime.now(timezone.utc).isoformat()
            await self._db.update_batch(
                batch_id,
                status="failed",
                completed_at=now,
                error_message=str(exc),
            )
        finally:
            if queue is not None:
                try:
                    queue.put_nowait(None)
                except asyncio.QueueFull:
                    pass
            self._progress_queues.pop(batch_id, None)
            self._cancel_flags.pop(batch_id, None)
            self._tasks.pop(batch_id, None)
