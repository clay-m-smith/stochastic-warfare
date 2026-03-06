"""Tests for run management endpoints."""

from __future__ import annotations

import asyncio
import json

import pytest
import pytest_asyncio

pytestmark = [pytest.mark.api, pytest.mark.asyncio]


async def test_submit_run(client):
    resp = await client.post("/api/runs", json={
        "scenario": "test_campaign",
        "seed": 42,
        "max_ticks": 50,
    })
    assert resp.status_code == 202
    data = resp.json()
    assert "run_id" in data
    assert data["status"] == "pending"


async def test_submit_run_not_found(client):
    resp = await client.post("/api/runs", json={
        "scenario": "nonexistent_scenario_xyz",
        "seed": 42,
        "max_ticks": 50,
    })
    assert resp.status_code == 404


async def test_submit_and_poll_run(client):
    resp = await client.post("/api/runs", json={
        "scenario": "test_campaign",
        "seed": 42,
        "max_ticks": 50,
    })
    run_id = resp.json()["run_id"]

    # Poll until complete (with timeout)
    for _ in range(60):
        resp = await client.get(f"/api/runs/{run_id}")
        data = resp.json()
        if data["status"] in ("completed", "failed"):
            break
        await asyncio.sleep(0.5)
    else:
        pytest.fail("Run did not complete within timeout")

    assert data["status"] == "completed"
    assert data["result"] is not None
    assert "sides" in data["result"]
    assert "ticks_executed" in data["result"]


async def test_get_run_not_found(client):
    resp = await client.get("/api/runs/nonexistent_id")
    assert resp.status_code == 404


async def test_list_runs_empty(client):
    resp = await client.get("/api/runs")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_submit_and_list_runs(client):
    await client.post("/api/runs", json={
        "scenario": "test_campaign", "seed": 42, "max_ticks": 10,
    })
    resp = await client.get("/api/runs")
    data = resp.json()
    assert len(data) >= 1


async def test_delete_run(client):
    resp = await client.post("/api/runs", json={
        "scenario": "test_campaign", "seed": 42, "max_ticks": 10,
    })
    run_id = resp.json()["run_id"]

    # Wait for completion
    for _ in range(60):
        resp = await client.get(f"/api/runs/{run_id}")
        if resp.json()["status"] in ("completed", "failed"):
            break
        await asyncio.sleep(0.5)

    resp = await client.delete(f"/api/runs/{run_id}")
    assert resp.status_code == 204

    resp = await client.get(f"/api/runs/{run_id}")
    assert resp.status_code == 404


async def test_get_run_events(client):
    resp = await client.post("/api/runs", json={
        "scenario": "test_campaign", "seed": 42, "max_ticks": 50,
    })
    run_id = resp.json()["run_id"]

    for _ in range(60):
        resp = await client.get(f"/api/runs/{run_id}")
        if resp.json()["status"] == "completed":
            break
        await asyncio.sleep(0.5)

    resp = await client.get(f"/api/runs/{run_id}/events")
    assert resp.status_code == 200
    data = resp.json()
    assert "events" in data
    assert "total" in data
    assert isinstance(data["events"], list)


async def test_get_run_events_pagination(client):
    resp = await client.post("/api/runs", json={
        "scenario": "test_campaign", "seed": 42, "max_ticks": 50,
    })
    run_id = resp.json()["run_id"]

    for _ in range(60):
        resp = await client.get(f"/api/runs/{run_id}")
        if resp.json()["status"] == "completed":
            break
        await asyncio.sleep(0.5)

    resp = await client.get(f"/api/runs/{run_id}/events?limit=5&offset=0")
    data = resp.json()
    assert len(data["events"]) <= 5


async def test_get_run_narrative(client):
    resp = await client.post("/api/runs", json={
        "scenario": "test_campaign", "seed": 42, "max_ticks": 50,
    })
    run_id = resp.json()["run_id"]

    for _ in range(60):
        resp = await client.get(f"/api/runs/{run_id}")
        if resp.json()["status"] == "completed":
            break
        await asyncio.sleep(0.5)

    resp = await client.get(f"/api/runs/{run_id}/narrative")
    assert resp.status_code == 200
    data = resp.json()
    assert "narrative" in data
    assert "tick_count" in data


async def test_get_run_forces(client):
    resp = await client.post("/api/runs", json={
        "scenario": "test_campaign", "seed": 42, "max_ticks": 50,
    })
    run_id = resp.json()["run_id"]

    for _ in range(60):
        resp = await client.get(f"/api/runs/{run_id}")
        if resp.json()["status"] == "completed":
            break
        await asyncio.sleep(0.5)

    resp = await client.get(f"/api/runs/{run_id}/forces")
    assert resp.status_code == 200
    data = resp.json()
    assert "sides" in data


async def test_get_run_snapshots(client):
    resp = await client.post("/api/runs", json={
        "scenario": "test_campaign", "seed": 42, "max_ticks": 50,
    })
    run_id = resp.json()["run_id"]

    for _ in range(60):
        resp = await client.get(f"/api/runs/{run_id}")
        if resp.json()["status"] == "completed":
            break
        await asyncio.sleep(0.5)

    resp = await client.get(f"/api/runs/{run_id}/snapshots")
    assert resp.status_code == 200
    data = resp.json()
    assert "snapshots" in data


async def test_forces_before_completion(client):
    resp = await client.post("/api/runs", json={
        "scenario": "test_campaign", "seed": 42, "max_ticks": 100000,
    })
    run_id = resp.json()["run_id"]
    # Immediately try to get forces (likely not completed yet or just submitted)
    resp = await client.get(f"/api/runs/{run_id}/forces")
    # Either 409 (not completed) or 200 (already done)
    assert resp.status_code in (200, 409)


async def test_run_with_config_overrides(client):
    resp = await client.post("/api/runs", json={
        "scenario": "test_campaign",
        "seed": 42,
        "max_ticks": 10,
        "config_overrides": {"hit_probability_modifier": 0.5},
    })
    assert resp.status_code == 202
    run_id = resp.json()["run_id"]

    for _ in range(60):
        resp = await client.get(f"/api/runs/{run_id}")
        if resp.json()["status"] in ("completed", "failed"):
            break
        await asyncio.sleep(0.5)

    data = resp.json()
    assert data["config_overrides"] == {"hit_probability_modifier": 0.5}
