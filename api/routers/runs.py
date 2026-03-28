"""Run management endpoints — submit, poll, events, narrative, WebSocket, batch."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect

from api.config import ApiSettings
from api.database import Database
from api.dependencies import get_db, get_run_manager, get_settings
from api.run_manager import RunManager
from api.scenarios import resolve_scenario
from api.schemas import (
    BatchDetail,
    BatchSubmitRequest,
    BatchSubmitResponse,
    EventItem,
    EventsResponse,
    ForcesResponse,
    FramesResponse,
    MapUnitFrame,
    NarrativeResponse,
    ObjectiveInfo,
    ReplayFrame,
    RunDetail,
    RunFromConfigRequest,
    RunStatus,
    RunSubmitRequest,
    RunSubmitResponse,
    RunSummary,
    SnapshotsResponse,
    TerrainResponse,
)

router = APIRouter(prefix="/runs", tags=["runs"])


# ── Single runs ──────────────────────────────────────────────────────────


@router.post("", response_model=RunSubmitResponse, status_code=202)
async def submit_run(
    req: RunSubmitRequest,
    settings: ApiSettings = Depends(get_settings),
    mgr: RunManager = Depends(get_run_manager),
) -> RunSubmitResponse:
    data_dir = Path(settings.data_dir)
    try:
        path = resolve_scenario(req.scenario, data_dir)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Scenario '{req.scenario}' not found")

    run_id = await mgr.submit(
        req.scenario, str(path), req.seed, req.max_ticks, req.config_overrides,
        frame_interval=req.frame_interval,
    )
    return RunSubmitResponse(run_id=run_id, status=RunStatus.PENDING)


@router.post("/from-config", response_model=RunSubmitResponse, status_code=202)
async def submit_run_from_config(
    req: RunFromConfigRequest,
    mgr: RunManager = Depends(get_run_manager),
) -> RunSubmitResponse:
    """Start a run from an inline config dict (no saved scenario file required)."""
    import tempfile
    import yaml
    from pydantic import ValidationError
    from stochastic_warfare.simulation.scenario import CampaignScenarioConfig

    # Validate first
    try:
        CampaignScenarioConfig(**req.config)
    except (ValidationError, Exception) as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # Write config to temp YAML (off event loop)
    tmp_dir = await asyncio.to_thread(tempfile.mkdtemp, prefix="sw_custom_")
    tmp_path = Path(tmp_dir) / "custom_scenario.yaml"
    with open(tmp_path, "w") as f:
        yaml.dump(req.config, f, default_flow_style=False)

    scenario_name = req.config.get("name", "[custom]")
    run_id = await mgr.submit(
        str(scenario_name), str(tmp_path), req.seed, req.max_ticks,
    )
    return RunSubmitResponse(run_id=run_id, status=RunStatus.PENDING)


@router.get("", response_model=list[RunSummary])
async def list_runs(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    scenario: str | None = Query(None),
    status: str | None = Query(None),
    db: Database = Depends(get_db),
) -> list[RunSummary]:
    rows = await db.list_runs(limit=limit, offset=offset, scenario=scenario, status=status)
    return [
        RunSummary(
            run_id=r["id"],
            scenario_name=r["scenario_name"],
            seed=r["seed"],
            status=RunStatus(r["status"]),
            created_at=r["created_at"],
            completed_at=r.get("completed_at"),
            error_message=r.get("error_message"),
        )
        for r in rows
    ]


@router.get("/{run_id}", response_model=RunDetail)
async def get_run(run_id: str, db: Database = Depends(get_db)) -> RunDetail:
    row = await db.get_run(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return RunDetail(
        run_id=row["id"],
        scenario_name=row["scenario_name"],
        scenario_path=row["scenario_path"],
        seed=row["seed"],
        max_ticks=row["max_ticks"],
        config_overrides=json.loads(row["config_overrides"]) if row["config_overrides"] else {},
        status=RunStatus(row["status"]),
        created_at=row["created_at"],
        started_at=row.get("started_at"),
        completed_at=row.get("completed_at"),
        result=json.loads(row["result_json"]) if row.get("result_json") else None,
        error_message=row.get("error_message"),
    )


@router.delete("/{run_id}", status_code=204)
async def delete_run(run_id: str, db: Database = Depends(get_db)) -> None:
    deleted = await db.delete_run(run_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")


@router.get("/{run_id}/forces", response_model=ForcesResponse)
async def get_run_forces(run_id: str, db: Database = Depends(get_db)) -> ForcesResponse:
    row = await db.get_run(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    if not row.get("result_json"):
        raise HTTPException(status_code=409, detail="Run not yet completed")
    result = json.loads(row["result_json"])
    return ForcesResponse(sides=result.get("sides", {}))


@router.get("/{run_id}/events", response_model=EventsResponse)
async def get_run_events(
    run_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=50000),
    event_type: str | None = Query(None),
    db: Database = Depends(get_db),
) -> EventsResponse:
    row = await db.get_run(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    if not row.get("events_json"):
        return EventsResponse(events=[], total=0, offset=offset, limit=limit)

    all_events = json.loads(row["events_json"])
    if event_type:
        all_events = [e for e in all_events if e.get("event_type") == event_type]

    total = len(all_events)
    page = all_events[offset:offset + limit]
    items = [
        EventItem(
            tick=e.get("tick", 0),
            event_type=e.get("event_type", ""),
            source=e.get("source", ""),
            data=e.get("data", {}),
        )
        for e in page
    ]
    return EventsResponse(events=items, total=total, offset=offset, limit=limit)


@router.get("/{run_id}/narrative", response_model=NarrativeResponse)
async def get_run_narrative(
    run_id: str,
    side: str | None = Query(None),
    style: str = Query("full"),
    max_ticks: int | None = Query(None),
    db: Database = Depends(get_db),
) -> NarrativeResponse:
    row = await db.get_run(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    if not row.get("events_json"):
        return NarrativeResponse(narrative="No events recorded.", tick_count=0)

    from stochastic_warfare.simulation.recorder import RecordedEvent
    from stochastic_warfare.tools.narrative import format_narrative, generate_narrative
    from datetime import datetime, timezone

    raw_events = json.loads(row["events_json"])

    # Convert to RecordedEvent-like objects for narrative generation
    events = [
        RecordedEvent(
            tick=e.get("tick", 0),
            timestamp=datetime.now(timezone.utc),
            event_type=e.get("event_type", ""),
            source=e.get("source", ""),
            data=e.get("data", {}),
        )
        for e in raw_events
    ]

    ticks = generate_narrative(events, side_filter=side, max_ticks=max_ticks)
    text = format_narrative(ticks, style=style)
    return NarrativeResponse(narrative=text, tick_count=len(ticks))


@router.get("/{run_id}/snapshots", response_model=SnapshotsResponse)
async def get_run_snapshots(run_id: str, db: Database = Depends(get_db)) -> SnapshotsResponse:
    row = await db.get_run(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    if not row.get("snapshots_json"):
        return SnapshotsResponse(snapshots=[])
    snapshots = json.loads(row["snapshots_json"])
    return SnapshotsResponse(snapshots=snapshots)


# ── Map data (Phase 35) ──────────────────────────────────────────────────


@router.get("/{run_id}/terrain", response_model=TerrainResponse)
async def get_run_terrain(run_id: str, db: Database = Depends(get_db)) -> TerrainResponse:
    row = await db.get_run(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    if not row.get("terrain_json"):
        return TerrainResponse()
    data = json.loads(row["terrain_json"])
    objectives = [
        ObjectiveInfo(id=o.get("id", ""), x=o.get("x", 0), y=o.get("y", 0), radius=o.get("radius", 500))
        for o in data.get("objectives", [])
    ]
    return TerrainResponse(
        width_cells=data.get("width_cells", 0),
        height_cells=data.get("height_cells", 0),
        cell_size=data.get("cell_size", 100.0),
        origin_easting=data.get("origin_easting", 0.0),
        origin_northing=data.get("origin_northing", 0.0),
        land_cover=data.get("land_cover", []),
        elevation=data.get("elevation", []),
        objectives=objectives,
        extent=data.get("extent", []),
    )


@router.get("/{run_id}/frames", response_model=FramesResponse)
async def get_run_frames(
    run_id: str,
    start_tick: int | None = Query(None, ge=0),
    end_tick: int | None = Query(None, ge=0),
    db: Database = Depends(get_db),
) -> FramesResponse:
    row = await db.get_run(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    if not row.get("frames_json"):
        return FramesResponse()
    all_frames = json.loads(row["frames_json"])

    # Filter by tick range
    filtered = all_frames
    if start_tick is not None:
        filtered = [f for f in filtered if f.get("tick", 0) >= start_tick]
    if end_tick is not None:
        filtered = [f for f in filtered if f.get("tick", 0) <= end_tick]

    frames = [
        ReplayFrame(
            tick=f.get("tick", 0),
            units=[
                MapUnitFrame(
                    id=u.get("id", ""),
                    side=u.get("side", ""),
                    x=u.get("x", 0),
                    y=u.get("y", 0),
                    domain=u.get("d", 0),
                    status=u.get("s", 0),
                    heading=u.get("h", 0),
                    type=u.get("t", ""),
                    sensor_range=u.get("sr", 0.0),
                    # Phase 92: enriched state
                    morale=u.get("mo", 0),
                    posture=u.get("po", ""),
                    health=u.get("hp", 1.0),
                    fuel_pct=u.get("fp", 1.0),
                    ammo_pct=u.get("ap", 1.0),
                    suppression=u.get("su", 0),
                    engaged=u.get("eg", False),
                )
                for u in f.get("units", [])
            ],
            detected=f.get("det", {}),
        )
        for f in filtered
    ]
    return FramesResponse(frames=frames, total_frames=len(all_frames))


# ── WebSocket progress ───────────────────────────────────────────────────


@router.websocket("/{run_id}/progress")
async def run_progress_ws(run_id: str, websocket: WebSocket) -> None:
    mgr: RunManager = websocket.app.state.run_manager
    queue = mgr.subscribe(run_id)

    await websocket.accept()

    if queue is None:
        # Run already finished or doesn't exist
        await websocket.send_json({"type": "error", "message": "Run not active"})
        await websocket.close()
        return

    try:
        while True:
            msg = await queue.get()
            if msg is None:
                # Terminal sentinel
                await websocket.send_json({"type": "complete"})
                break
            await websocket.send_json(msg)
    except WebSocketDisconnect:
        pass
    finally:
        mgr.unsubscribe(run_id, queue)
        await websocket.close()


# ── Batch ────────────────────────────────────────────────────────────────


@router.post("/batch", response_model=BatchSubmitResponse, status_code=202)
async def submit_batch(
    req: BatchSubmitRequest,
    settings: ApiSettings = Depends(get_settings),
    mgr: RunManager = Depends(get_run_manager),
) -> BatchSubmitResponse:
    data_dir = Path(settings.data_dir)
    try:
        path = resolve_scenario(req.scenario, data_dir)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Scenario '{req.scenario}' not found")

    batch_id = await mgr.submit_batch(
        req.scenario, str(path), req.num_iterations, req.base_seed, req.max_ticks,
    )
    return BatchSubmitResponse(batch_id=batch_id, status=RunStatus.PENDING)


@router.get("/batch/{batch_id}", response_model=BatchDetail)
async def get_batch(batch_id: str, db: Database = Depends(get_db)) -> BatchDetail:
    row = await db.get_batch(batch_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Batch '{batch_id}' not found")
    return BatchDetail(
        batch_id=row["id"],
        scenario_name=row["scenario_name"],
        num_iterations=row["num_iterations"],
        completed_iterations=row["completed_iterations"],
        status=RunStatus(row["status"]),
        created_at=row["created_at"],
        completed_at=row.get("completed_at"),
        metrics=json.loads(row["metrics_json"]) if row.get("metrics_json") else None,
        error_message=row.get("error_message"),
    )


@router.websocket("/batch/{batch_id}/progress")
async def batch_progress_ws(batch_id: str, websocket: WebSocket) -> None:
    mgr: RunManager = websocket.app.state.run_manager
    queue = mgr.subscribe(batch_id)

    await websocket.accept()

    if queue is None:
        await websocket.send_json({"type": "error", "message": "Batch not active"})
        await websocket.close()
        return

    try:
        while True:
            msg = await queue.get()
            if msg is None:
                await websocket.send_json({"type": "complete"})
                break
            await websocket.send_json(msg)
    except WebSocketDisconnect:
        pass
    finally:
        mgr.unsubscribe(batch_id, queue)
        await websocket.close()
