"""Tests for Phase 92 per-run analytics endpoints."""

from __future__ import annotations

import json

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api.database import Database
from api.main import create_app
from api.config import ApiSettings
from api.run_manager import RunManager


# ---------------------------------------------------------------------------
# Fixtures — in-memory DB with pre-inserted run data
# ---------------------------------------------------------------------------

_EVENTS = [
    {"tick": 1, "event_type": "EngagementEvent", "source": "combat",
     "data": {"attacker_id": "u1", "target_id": "u2", "weapon_id": "m256",
              "engagement_type": "DIRECT_FIRE", "result": "hit"}},
    {"tick": 1, "event_type": "EngagementEvent", "source": "combat",
     "data": {"attacker_id": "u3", "target_id": "u4", "weapon_id": "rpg7",
              "engagement_type": "DIRECT_FIRE", "result": "miss"}},
    {"tick": 2, "event_type": "EngagementEvent", "source": "combat",
     "data": {"attacker_id": "u1", "target_id": "u4", "weapon_id": "m256",
              "engagement_type": "DIRECT_FIRE", "result": "hit"}},
    {"tick": 2, "event_type": "UnitDestroyedEvent", "source": "combat",
     "data": {"unit_id": "u2", "cause": "combat_damage", "side": "red",
              "weapon_id": "m256"}},
    {"tick": 3, "event_type": "UnitDisabledEvent", "source": "combat",
     "data": {"unit_id": "u4", "cause": "combat_damage", "side": "red",
              "weapon_id": "m256"}},
    {"tick": 2, "event_type": "SuppressionEvent", "source": "combat",
     "data": {"target_id": "u3", "suppression_level": 2}},
    {"tick": 3, "event_type": "SuppressionEvent", "source": "combat",
     "data": {"target_id": "u3", "suppression_level": 3}},
    {"tick": 3, "event_type": "SuppressionEvent", "source": "combat",
     "data": {"target_id": "u5", "suppression_level": 1}},
    {"tick": 3, "event_type": "RoutEvent", "source": "morale",
     "data": {"unit_id": "u3", "direction": 180}},
    {"tick": 1, "event_type": "MoraleStateChangeEvent", "source": "morale",
     "data": {"unit_id": "u3", "old_state": 0, "new_state": 1}},
    {"tick": 2, "event_type": "MoraleStateChangeEvent", "source": "morale",
     "data": {"unit_id": "u3", "old_state": 1, "new_state": 2}},
    {"tick": 3, "event_type": "MoraleStateChangeEvent", "source": "morale",
     "data": {"unit_id": "u5", "old_state": 0, "new_state": 1}},
]


@pytest.fixture
def settings() -> ApiSettings:
    return ApiSettings(db_path=":memory:", data_dir="data")


@pytest_asyncio.fixture
async def client(settings: ApiSettings):
    app = create_app(settings)
    from api.dependencies import get_settings
    app.dependency_overrides[get_settings] = lambda: settings

    db = Database(settings.db_path)
    await db.initialize()
    app.state.db = db
    app.state.run_manager = RunManager(
        db, data_dir=settings.data_dir,
        max_concurrent=1, max_stored_events=50000, default_max_ticks=10000,
    )

    # Insert a completed run with events
    await db.create_run("test_run", "test_scenario", "data/scenarios/test_scenario/scenario.yaml", 42, 100)
    await db.update_run_status(
        "test_run", "completed",
        events_json=json.dumps(_EVENTS),
    )

    # Insert a pending run (not completed)
    await db.create_run("pending_run", "test_scenario", "path", 1, 100)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await db.close()


# ---------------------------------------------------------------------------
# Casualty analytics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_casualties_default(client: AsyncClient):
    resp = await client.get("/api/runs/test_run/analytics/casualties")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2  # 1 destroyed + 1 disabled
    assert len(data["groups"]) >= 1
    # Both casualties are from m256
    assert data["groups"][0]["label"] == "m256"
    assert data["groups"][0]["count"] == 2


@pytest.mark.asyncio
async def test_casualties_group_by_side(client: AsyncClient):
    resp = await client.get("/api/runs/test_run/analytics/casualties?group_by=side")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert data["groups"][0]["label"] == "red"


@pytest.mark.asyncio
async def test_casualties_filter_side(client: AsyncClient):
    resp = await client.get("/api/runs/test_run/analytics/casualties?side=blue")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0  # No blue casualties


# ---------------------------------------------------------------------------
# Suppression analytics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_suppression(client: AsyncClient):
    resp = await client.get("/api/runs/test_run/analytics/suppression")
    assert resp.status_code == 200
    data = resp.json()
    assert data["peak_suppressed"] == 2  # tick 3: u3 + u5
    assert data["peak_tick"] == 3
    assert data["rout_cascades"] == 1
    assert len(data["timeline"]) >= 1


# ---------------------------------------------------------------------------
# Morale analytics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_morale(client: AsyncClient):
    resp = await client.get("/api/runs/test_run/analytics/morale")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["timeline"]) >= 2
    # At tick 3: u3 is BROKEN (2), u5 is SHAKEN (1)
    last = data["timeline"][-1]
    assert last["tick"] == 3
    assert last["broken"] == 1
    assert last["shaken"] == 1


# ---------------------------------------------------------------------------
# Engagement analytics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_engagements(client: AsyncClient):
    resp = await client.get("/api/runs/test_run/analytics/engagements")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["by_type"]) >= 1
    df = data["by_type"][0]
    assert df["type"] == "DIRECT_FIRE"
    assert df["count"] == 3
    assert df["hit_rate"] == pytest.approx(2 / 3, abs=0.01)


# ---------------------------------------------------------------------------
# Summary analytics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summary(client: AsyncClient):
    resp = await client.get("/api/runs/test_run/analytics/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert "casualties" in data
    assert "suppression" in data
    assert "morale" in data
    assert "engagements" in data
    assert data["casualties"]["total"] == 2
    assert data["engagements"]["total"] == 3


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_not_found(client: AsyncClient):
    resp = await client.get("/api/runs/nonexistent/analytics/casualties")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_not_completed(client: AsyncClient):
    resp = await client.get("/api/runs/pending_run/analytics/casualties")
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_empty_events(client: AsyncClient):
    """Run with no events should return zero-value analytics."""
    db = client._transport.app.state.db  # type: ignore[attr-defined]
    await db.create_run("empty_run", "test", "path", 1, 100)
    await db.update_run_status("empty_run", "completed", events_json="[]")

    resp = await client.get("/api/runs/empty_run/analytics/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["casualties"]["total"] == 0
    assert data["engagements"]["total"] == 0
    assert data["suppression"]["peak_suppressed"] == 0
    assert len(data["morale"]["timeline"]) == 0
