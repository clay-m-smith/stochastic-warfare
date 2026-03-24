"""Tests for request body validation — field limits, depth checks, health endpoints."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.api, pytest.mark.asyncio]


# ── Field constraint validation ───────────────────────────────────────────


async def test_oversized_max_ticks_rejected(client):
    """max_ticks > 1_000_000 should be rejected with 422."""
    resp = await client.post("/api/runs", json={
        "scenario": "test_campaign",
        "max_ticks": 10_000_001,
    })
    assert resp.status_code == 422


async def test_oversized_batch_iterations_rejected(client):
    """num_iterations > 1_000 should be rejected with 422."""
    resp = await client.post("/api/runs/batch", json={
        "scenario": "test_campaign",
        "num_iterations": 5000,
    })
    assert resp.status_code == 422


async def test_deeply_nested_config_rejected(client):
    """config_overrides nested deeper than 5 levels should be rejected."""
    # Build 10-level nested dict
    nested: dict = {}
    current = nested
    for i in range(10):
        current[f"level_{i}"] = {}
        current = current[f"level_{i}"]
    current["leaf"] = "value"

    resp = await client.post("/api/runs", json={
        "scenario": "test_campaign",
        "config_overrides": nested,
    })
    assert resp.status_code == 422


async def test_too_many_keys_config_rejected(client):
    """config_overrides with > 200 keys at one level should be rejected."""
    big_dict = {f"key_{i}": i for i in range(300)}
    resp = await client.post("/api/runs", json={
        "scenario": "test_campaign",
        "config_overrides": big_dict,
    })
    assert resp.status_code == 422


async def test_valid_config_overrides_accepted(client):
    """Normal config_overrides should pass validation."""
    resp = await client.post("/api/runs", json={
        "scenario": "test_campaign",
        "max_ticks": 50,
        "config_overrides": {"calibration": {"hit_probability_modifier": 1.5}},
    })
    # 202 (accepted) or 404 (scenario not found) — not 422
    assert resp.status_code in (202, 404)


# ── Health endpoints ──────────────────────────────────────────────────────


async def test_health_live_instant(client):
    """GET /api/health/live should return 200 with status ok."""
    resp = await client.get("/api/health/live")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


async def test_health_ready_checks_db(client):
    """GET /api/health/ready should return 200 with db_connected."""
    resp = await client.get("/api/health/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["db_connected"] is True
    assert "version" in data
    assert "scenario_count" in data
    assert "unit_count" in data
