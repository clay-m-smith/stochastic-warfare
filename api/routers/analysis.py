"""Analysis endpoints — compare, sweep, tempo."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from api.config import ApiSettings
from api.database import Database
from api.dependencies import get_db, get_settings
from api.scenarios import resolve_scenario
from api.schemas import CompareRequest, SweepRequest

router = APIRouter(prefix="/analysis", tags=["analysis"])

_ANALYSIS_SEMAPHORE: asyncio.Semaphore | None = None


def _get_analysis_semaphore() -> asyncio.Semaphore:
    """Lazily initialize analysis concurrency semaphore."""
    global _ANALYSIS_SEMAPHORE
    if _ANALYSIS_SEMAPHORE is None:
        _ANALYSIS_SEMAPHORE = asyncio.Semaphore(2)
    return _ANALYSIS_SEMAPHORE


@router.post("/compare")
async def run_compare(
    req: CompareRequest,
    settings: ApiSettings = Depends(get_settings),
) -> dict:
    data_dir = Path(settings.data_dir)
    try:
        path = resolve_scenario(req.scenario, data_dir)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Scenario '{req.scenario}' not found")

    from stochastic_warfare.tools.comparison import ComparisonConfig, run_comparison
    from stochastic_warfare.tools.serializers import serialize_to_dict

    config = ComparisonConfig(
        scenario_path=str(path),
        overrides_a=req.overrides_a,
        overrides_b=req.overrides_b,
        label_a=req.label_a,
        label_b=req.label_b,
        num_iterations=req.num_iterations,
        max_ticks=req.max_ticks,
    )
    async with _get_analysis_semaphore():
        result = await asyncio.to_thread(run_comparison, config)
    return serialize_to_dict(result)


@router.post("/sweep")
async def run_sweep(
    req: SweepRequest,
    settings: ApiSettings = Depends(get_settings),
) -> dict:
    data_dir = Path(settings.data_dir)
    try:
        path = resolve_scenario(req.scenario, data_dir)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Scenario '{req.scenario}' not found")

    from stochastic_warfare.tools.sensitivity import SweepConfig, run_sweep as _run_sweep
    from stochastic_warfare.tools.serializers import serialize_to_dict

    config = SweepConfig(
        scenario_path=str(path),
        parameter_name=req.parameter_name,
        values=req.values,
        iterations_per_point=req.num_iterations,
        max_ticks=req.max_ticks,
    )
    async with _get_analysis_semaphore():
        result = await asyncio.to_thread(_run_sweep, config)
    return serialize_to_dict(result)


@router.get("/tempo/{run_id}")
async def get_tempo(
    run_id: str,
    window_s: float = 60.0,
    side: str | None = None,
    db: Database = Depends(get_db),
) -> dict:
    import json

    row = await db.get_run(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    if not row.get("events_json"):
        raise HTTPException(status_code=409, detail="Run has no events")

    from datetime import datetime, timezone
    from stochastic_warfare.simulation.recorder import RecordedEvent
    from stochastic_warfare.tools.tempo_analysis import compute_tempo
    from stochastic_warfare.tools.serializers import serialize_to_dict

    raw = json.loads(row["events_json"])
    events = [
        RecordedEvent(
            tick=e.get("tick", 0),
            timestamp=datetime.now(timezone.utc),
            event_type=e.get("event_type", ""),
            source=e.get("source", ""),
            data=e.get("data", {}),
        )
        for e in raw
    ]

    result = await asyncio.to_thread(compute_tempo, events, window_s=window_s, side_filter=side)
    return serialize_to_dict(result)
