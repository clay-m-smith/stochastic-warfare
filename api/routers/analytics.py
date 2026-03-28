"""Per-run analytics endpoints — casualties, suppression, morale, engagements."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from api.database import Database
from api.dependencies import get_db
from api.schemas import (
    AnalyticsSummary,
    CasualtyAnalytics,
    CasualtyGroup,
    EngagementAnalytics,
    EngagementTypeGroup,
    MoraleAnalytics,
    MoraleTimelinePoint,
    SuppressionAnalytics,
    SuppressionTimelinePoint,
)

router = APIRouter(prefix="/runs", tags=["analytics"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _load_events(run_id: str, db: Database) -> list[dict[str, Any]]:
    """Load and parse events from a completed run. Raises 404/409."""
    row = await db.get_run(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    if row.get("status") != "completed":
        raise HTTPException(status_code=409, detail="Run not yet completed")
    raw = row.get("events_json") or "[]"
    return json.loads(raw)


def _compute_casualties(
    events: list[dict[str, Any]],
    group_by: str = "weapon",
    side_filter: str | None = None,
) -> CasualtyAnalytics:
    """Aggregate casualty data from events."""
    groups: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    total = 0

    for ev in events:
        et = ev.get("event_type", "")
        data = ev.get("data", {})

        if et not in ("UnitDestroyedEvent", "UnitDisabledEvent"):
            continue

        ev_side = data.get("side", "")
        if side_filter and ev_side != side_filter:
            continue

        total += 1

        if group_by == "weapon":
            label = data.get("weapon_id") or data.get("cause", "unknown")
        elif group_by == "side":
            label = ev_side or "unknown"
        elif group_by == "tick":
            label = str(ev.get("tick", 0))
        else:
            label = data.get("weapon_id") or data.get("cause", "unknown")

        groups[label][ev_side] += 1

    result_groups = [
        CasualtyGroup(
            label=label,
            count=sum(sides.values()),
            side=max(sides, key=sides.get) if sides else "",  # type: ignore[arg-type]
        )
        for label, sides in sorted(groups.items(), key=lambda x: -sum(x[1].values()))
    ]
    return CasualtyAnalytics(groups=result_groups, total=total)


def _compute_suppression(events: list[dict[str, Any]]) -> SuppressionAnalytics:
    """Aggregate suppression data from events."""
    # Track suppressed units per tick
    tick_suppressed: dict[int, set[str]] = defaultdict(set)
    rout_count = 0

    for ev in events:
        et = ev.get("event_type", "")
        data = ev.get("data", {})
        tick = ev.get("tick", 0)

        if "Suppression" in et:
            uid = data.get("target_id") or data.get("unit_id", "")
            level = data.get("suppression_level", data.get("level", 0))
            if level and level > 0:
                tick_suppressed[tick].add(uid)

        if "Rout" in et:
            rout_count += 1

    # Build timeline and find peak
    timeline: list[SuppressionTimelinePoint] = []
    peak = 0
    peak_tick = 0
    for tick in sorted(tick_suppressed):
        count = len(tick_suppressed[tick])
        timeline.append(SuppressionTimelinePoint(tick=tick, count=count))
        if count > peak:
            peak = count
            peak_tick = tick

    return SuppressionAnalytics(
        peak_suppressed=peak,
        peak_tick=peak_tick,
        rout_cascades=rout_count,
        timeline=timeline,
    )


def _compute_morale(events: list[dict[str, Any]]) -> MoraleAnalytics:
    """Aggregate morale state distribution from events."""
    # Track current state per unit (running counters)
    state_names = ["steady", "shaken", "broken", "routed", "surrendered"]
    unit_states: dict[str, int] = {}  # unit_id -> current state index
    tick_snapshots: dict[int, dict[str, int]] = {}

    for ev in events:
        if ev.get("event_type") != "MoraleStateChangeEvent":
            continue
        data = ev.get("data", {})
        tick = ev.get("tick", 0)
        uid = data.get("unit_id", "")
        new_state = data.get("new_state", 0)
        if isinstance(new_state, str):
            # Handle string state names
            new_state = next(
                (i for i, n in enumerate(state_names) if n == new_state.lower()), 0
            )
        unit_states[uid] = int(new_state)

        # Snapshot current distribution
        dist = {n: 0 for n in state_names}
        for st in unit_states.values():
            if 0 <= st < len(state_names):
                dist[state_names[st]] += 1
        tick_snapshots[tick] = dist

    timeline = [
        MoraleTimelinePoint(tick=tick, **dist)
        for tick, dist in sorted(tick_snapshots.items())
    ]
    return MoraleAnalytics(timeline=timeline)


def _compute_engagements(events: list[dict[str, Any]]) -> EngagementAnalytics:
    """Aggregate engagement data from events."""
    type_counts: dict[str, int] = defaultdict(int)
    type_hits: dict[str, int] = defaultdict(int)
    total = 0

    for ev in events:
        if ev.get("event_type") != "EngagementEvent":
            continue
        data = ev.get("data", {})
        total += 1

        eng_type = (
            data.get("engagement_type")
            or data.get("weapon_category")
            or data.get("weapon_id")
            or "unknown"
        )
        type_counts[eng_type] += 1

        result = data.get("result", "")
        if result == "hit":
            type_hits[eng_type] += 1

    by_type = [
        EngagementTypeGroup(
            type=t,
            count=c,
            hit_rate=round(type_hits.get(t, 0) / c, 3) if c > 0 else 0.0,
        )
        for t, c in sorted(type_counts.items(), key=lambda x: -x[1])
    ]
    return EngagementAnalytics(by_type=by_type, total=total)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/{run_id}/analytics/casualties", response_model=CasualtyAnalytics)
async def get_casualties(
    run_id: str,
    group_by: str = Query("weapon", pattern="^(weapon|side|tick)$"),
    side: str | None = Query(None),
    db: Database = Depends(get_db),
) -> CasualtyAnalytics:
    events = await _load_events(run_id, db)
    return _compute_casualties(events, group_by=group_by, side_filter=side)


@router.get("/{run_id}/analytics/suppression", response_model=SuppressionAnalytics)
async def get_suppression(
    run_id: str,
    db: Database = Depends(get_db),
) -> SuppressionAnalytics:
    events = await _load_events(run_id, db)
    return _compute_suppression(events)


@router.get("/{run_id}/analytics/morale", response_model=MoraleAnalytics)
async def get_morale(
    run_id: str,
    db: Database = Depends(get_db),
) -> MoraleAnalytics:
    events = await _load_events(run_id, db)
    return _compute_morale(events)


@router.get("/{run_id}/analytics/engagements", response_model=EngagementAnalytics)
async def get_engagements(
    run_id: str,
    db: Database = Depends(get_db),
) -> EngagementAnalytics:
    events = await _load_events(run_id, db)
    return _compute_engagements(events)


@router.get("/{run_id}/analytics/summary", response_model=AnalyticsSummary)
async def get_analytics_summary(
    run_id: str,
    db: Database = Depends(get_db),
) -> AnalyticsSummary:
    events = await _load_events(run_id, db)
    return AnalyticsSummary(
        casualties=_compute_casualties(events),
        suppression=_compute_suppression(events),
        morale=_compute_morale(events),
        engagements=_compute_engagements(events),
    )
