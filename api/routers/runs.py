"""Run management endpoints — submit, poll, events, narrative, WebSocket, batch."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect

from api.config import ApiSettings
from api.database import Database
from api.dependencies import get_db, get_run_manager, get_settings
from api.run_manager import RunManager, RunManagerClosedError
from api.runtime_errors import RUNTIME_INPUT_EXCEPTIONS
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
    PrivilegedEngagementRevalidationOutcome,
    PrivilegedTargetingDecision,
    ReplayFrame,
    RunDetail,
    RunFromConfigRequest,
    RunStatus,
    RunSubmitRequest,
    RunSubmitResponse,
    RunSummary,
    SnapshotsResponse,
    SideFowEngagementRevalidationOutcome,
    SideFowPublicTrack,
    SideFowTargetingDecision,
    TerrainResponse,
)
from stochastic_warfare.simulation.scenario import parse_campaign_scenario_config
from stochastic_warfare.simulation.targeting_exposure import (
    PrivilegedEngagementRevalidationExposure,
    PrivilegedTargetingExposure,
    TargetingExposureBundle,
    TargetingExposureScope,
    decode_stored_side_fow_targeting_exposure,
    validate_privileged_targeting_roster,
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

    patch = req.config_overrides.model_dump(
        mode="json",
        exclude_unset=True,
    )
    try:
        run_id = await mgr.submit(
            req.scenario,
            str(path),
            req.seed,
            req.max_ticks,
            patch,
            frame_interval=req.frame_interval,
        )
    except RunManagerClosedError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RUNTIME_INPUT_EXCEPTIONS as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return RunSubmitResponse(run_id=run_id, status=RunStatus.PENDING)


@router.post("/from-config", response_model=RunSubmitResponse, status_code=202)
async def submit_run_from_config(
    req: RunFromConfigRequest,
    mgr: RunManager = Depends(get_run_manager),
) -> RunSubmitResponse:
    """Start a run from an inline config dict (no saved scenario file required)."""
    try:
        source_config = parse_campaign_scenario_config(req.config)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        run_id = await mgr.submit_config(
            source_config.name,
            source_config,
            req.seed,
            req.max_ticks,
        )
    except RunManagerClosedError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RUNTIME_INPUT_EXCEPTIONS as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
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
async def delete_run(
    run_id: str,
    db: Database = Depends(get_db),
    mgr: RunManager = Depends(get_run_manager),
) -> None:
    await mgr.cancel_and_wait(run_id)
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
    side: str | None = Query(None),
    tick_min: int | None = Query(None, ge=0),
    tick_max: int | None = Query(None, ge=0),
    search: str | None = Query(None),
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
    if side:
        side_lower = side.lower()
        all_events = [
            e
            for e in all_events
            if str(e.get("data", {}).get("side", "")).lower() == side_lower
            or str(e.get("data", {}).get("attacker_side", "")).lower() == side_lower
            or side_lower in str(e.get("source", "")).lower()
        ]
    if tick_min is not None:
        all_events = [e for e in all_events if e.get("tick", 0) >= tick_min]
    if tick_max is not None:
        all_events = [e for e in all_events if e.get("tick", 0) <= tick_max]
    if search:
        search_lower = search.lower()
        all_events = [
            e
            for e in all_events
            if search_lower in str(e.get("event_type", "")).lower()
            or search_lower in str(e.get("source", "")).lower()
            or search_lower in json.dumps(e.get("data", {})).lower()
        ]

    total = len(all_events)
    page = all_events[offset : offset + limit]
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


def _map_unit_frame(value: object) -> MapUnitFrame:
    """Validate one compact stored unit frame into the public API schema."""
    if not isinstance(value, dict):
        raise ValueError("stored unit frame must be a mapping")
    return MapUnitFrame(
        id=value.get("id", ""),
        side=value.get("side", ""),
        x=value.get("x", 0),
        y=value.get("y", 0),
        domain=value.get("d", 0),
        status=value.get("s", 0),
        heading=value.get("h", 0),
        type=value.get("t", ""),
        sensor_range=value.get("sr", 0.0),
        morale=value.get("mo", 0),
        posture=value.get("po", ""),
        health=value.get("hp", 1.0),
        fuel_pct=value.get("fp", 1.0),
        ammo_pct=value.get("ap", 1.0),
        suppression=value.get("su", 0),
        engaged=value.get("eg", False),
    )


def _frame_from_storage(
    value: object,
    *,
    scope: TargetingExposureScope,
    side: str | None,
) -> ReplayFrame:
    """Project one stored frame without deriving SIDE_FOW from ground truth."""
    if not isinstance(value, dict):
        raise ValueError("stored replay frame must be a mapping")
    tick = value.get("tick", 0)
    stored_scope = value.get(
        "scope",
        TargetingExposureScope.PRIVILEGED_ENGINE.value,
    )
    if stored_scope != TargetingExposureScope.PRIVILEGED_ENGINE.value:
        raise ValueError("stored frame has an unknown exposure scope")
    if scope is TargetingExposureScope.PRIVILEGED_ENGINE:
        raw_targeting = value.get("targeting", [])
        if not isinstance(raw_targeting, list):
            raise ValueError("stored privileged targeting must be a list")
        raw_outcomes = value.get("targeting_outcomes", [])
        if not isinstance(raw_outcomes, list):
            raise ValueError("stored privileged targeting outcomes must be a list")
        raw_units = value.get("units", [])
        if not isinstance(raw_units, list):
            raise ValueError("stored privileged units must be a list")
        privileged = PrivilegedTargetingExposure.from_wire(
            engine_tick=tick,
            value=raw_targeting,
        )
        outcomes = PrivilegedEngagementRevalidationExposure.from_wire(
            engine_tick=tick,
            value=raw_outcomes,
        )
        bundle = TargetingExposureBundle(
            privileged=privileged,
            privileged_engagement_revalidations=outcomes,
            side_fow_available=False,
            sides=(),
        )
        validate_privileged_targeting_roster(
            exposure=bundle,
            authoritative_unit_frames=raw_units,
        )
        return ReplayFrame(
            scope=scope,
            tick=tick,
            units=[_map_unit_frame(item) for item in raw_units],
            detected=value.get("det", {}),
            targeting=[
                PrivilegedTargetingDecision.model_validate(item)
                for item in privileged.to_wire()
            ],
            targeting_outcomes=[
                PrivilegedEngagementRevalidationOutcome.model_validate(item)
                for item in outcomes.to_wire()
            ],
        )

    if side is None:
        raise ValueError("SIDE_FOW projection requires side")
    decoded = decode_stored_side_fow_targeting_exposure(
        engine_tick=tick,
        viewer_side=side,
        stored_frame=value,
    )
    public = decoded.exposure
    raw_units = decoded.unit_frames
    units = [_map_unit_frame(item) for item in raw_units]
    if any(unit.side != side for unit in units):
        raise ValueError("SIDE_FOW unit snapshot contains another side")
    return ReplayFrame(
        scope=scope,
        viewer_side=side,
        tick=tick,
        units=units,
        detected={side: [track.track_id for track in public.tracks]},
        tracks=[
            SideFowPublicTrack.model_validate(track.to_wire())
            for track in public.tracks
        ],
        side_targeting=[
            SideFowTargetingDecision.model_validate(decision.to_wire())
            for decision in public.decisions
        ],
        side_targeting_outcomes=[
            SideFowEngagementRevalidationOutcome.model_validate(
                outcome.to_wire(),
            )
            for outcome in public.engagement_revalidations
        ],
    )


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
    scope: TargetingExposureScope = Query(
        TargetingExposureScope.PRIVILEGED_ENGINE,
    ),
    side: str | None = Query(None, min_length=1, max_length=200),
    db: Database = Depends(get_db),
) -> FramesResponse:
    if scope is TargetingExposureScope.PRIVILEGED_ENGINE and side is not None:
        raise HTTPException(
            status_code=422,
            detail="side is valid only for SIDE_FOW frame exposure",
        )
    if scope is TargetingExposureScope.SIDE_FOW and side is None:
        raise HTTPException(
            status_code=422,
            detail="SIDE_FOW frame exposure requires side",
        )
    if side is not None and side != side.strip():
        raise HTTPException(
            status_code=422,
            detail="side must be a trimmed identifier",
        )
    row = await db.get_run(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    if not row.get("frames_json"):
        if scope is TargetingExposureScope.SIDE_FOW:
            raise HTTPException(
                status_code=409,
                detail="run has no stored SIDE_FOW frame snapshots",
            )
        return FramesResponse(scope=scope)
    try:
        all_frames = json.loads(row["frames_json"])
    except (TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=409,
            detail="stored frame exposure is not valid JSON",
        ) from exc
    if not isinstance(all_frames, list):
        raise HTTPException(
            status_code=409,
            detail="stored frame exposure must be a list",
        )
    if any(not isinstance(frame, dict) for frame in all_frames):
        raise HTTPException(
            status_code=409,
            detail="stored frame exposure entries must be mappings",
        )

    # Filter by tick range
    filtered = all_frames
    if start_tick is not None:
        filtered = [f for f in filtered if f.get("tick", 0) >= start_tick]
    if end_tick is not None:
        filtered = [f for f in filtered if f.get("tick", 0) <= end_tick]

    try:
        frames = [
            _frame_from_storage(frame, scope=scope, side=side)
            for frame in filtered
        ]
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=409,
            detail=f"stored frame exposure is invalid: {exc}",
        ) from exc
    return FramesResponse(
        scope=scope,
        viewer_side=side,
        frames=frames,
        total_frames=len(all_frames),
    )


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

    try:
        batch_id = await mgr.submit_batch(
            scenario_name=req.scenario,
            scenario_path=str(path),
            num_iterations=req.num_iterations,
            base_seed=req.base_seed,
            max_ticks=req.max_ticks,
            metric_names=req.metrics,
            config_overrides=req.config_overrides.model_dump(
                mode="json",
                exclude_unset=True,
            ),
        )
    except RunManagerClosedError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RUNTIME_INPUT_EXCEPTIONS as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return BatchSubmitResponse(batch_id=batch_id, status=RunStatus.PENDING)


@router.get("/batch/{batch_id}", response_model=BatchDetail)
async def get_batch(batch_id: str, db: Database = Depends(get_db)) -> BatchDetail:
    row = await db.get_batch(batch_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Batch '{batch_id}' not found")
    status = RunStatus(row["status"])
    if status is RunStatus.COMPLETED:
        from stochastic_warfare.tools._run_helpers import (
            validate_serialized_batch_evidence,
        )

        try:
            stored_metrics = json.loads(row["metrics_json"])
            validate_serialized_batch_evidence(
                stored_metrics,
                num_iterations=row["num_iterations"],
                base_seed=row["base_seed"],
                max_ticks=row["max_ticks"],
                completed_iterations=row["completed_iterations"],
            )
        except (
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Completed batch lacks valid Phase 112 raw-vector and "
                    f"provenance evidence: {exc}"
                ),
            ) from exc
        statistics = stored_metrics["statistics"]
        ordered_metrics = stored_metrics["ordered_metrics"]
        raw_metrics = stored_metrics["raw_metrics"]
        provenance = stored_metrics["provenance"]
    else:
        statistics = None
        ordered_metrics = []
        raw_metrics = None
        provenance = None
    return BatchDetail(
        batch_id=row["id"],
        scenario_name=row["scenario_name"],
        num_iterations=row["num_iterations"],
        base_seed=row["base_seed"],
        max_ticks=row["max_ticks"],
        completed_iterations=row["completed_iterations"],
        status=status,
        created_at=row["created_at"],
        completed_at=row.get("completed_at"),
        metrics=statistics,
        ordered_metrics=ordered_metrics,
        raw_metrics=raw_metrics,
        provenance=provenance,
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
