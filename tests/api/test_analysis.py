"""Tests for analysis endpoints (compare, sweep, tempo)."""

from __future__ import annotations

import asyncio

import pytest

pytestmark = [pytest.mark.api, pytest.mark.asyncio]


async def test_compare_endpoint(client):
    resp = await client.post("/api/analysis/compare", json={
        "scenario": "test_campaign",
        "overrides_a": {},
        "overrides_b": {"hit_probability_modifier": 2.0},
        "num_iterations": 3,
        "max_ticks": 20,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "label_a" in data
    assert "label_b" in data
    assert "metrics" in data


async def test_compare_not_found(client):
    resp = await client.post("/api/analysis/compare", json={
        "scenario": "nonexistent_scenario",
        "num_iterations": 3,
        "max_ticks": 20,
    })
    assert resp.status_code == 404


async def test_sweep_endpoint(client):
    resp = await client.post("/api/analysis/sweep", json={
        "scenario": "test_campaign",
        "parameter_name": "hit_probability_modifier",
        "values": [0.5, 1.0, 2.0],
        "num_iterations": 2,
        "max_ticks": 20,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "parameter_name" in data
    assert "points" in data
    assert len(data["points"]) == 3


async def test_sweep_not_found(client):
    resp = await client.post("/api/analysis/sweep", json={
        "scenario": "nonexistent_scenario",
        "parameter_name": "test",
        "values": [1.0],
    })
    assert resp.status_code == 404


async def test_tempo_endpoint(client):
    # First submit and complete a run
    resp = await client.post("/api/runs", json={
        "scenario": "test_campaign",
        "seed": 42,
        "max_ticks": 50,
    })
    run_id = resp.json()["run_id"]

    for _ in range(60):
        resp = await client.get(f"/api/runs/{run_id}")
        if resp.json()["status"] == "completed":
            break
        await asyncio.sleep(0.5)
    else:
        pytest.fail("Run did not complete")

    resp = await client.get(f"/api/analysis/tempo/{run_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)


async def test_tempo_not_found(client):
    resp = await client.get("/api/analysis/tempo/nonexistent_id")
    assert resp.status_code == 404


async def test_tempo_no_events(client):
    # Submit a run with 0 max_ticks to get no events
    resp = await client.post("/api/runs", json={
        "scenario": "test_campaign",
        "seed": 42,
        "max_ticks": 1,
    })
    run_id = resp.json()["run_id"]

    for _ in range(60):
        resp = await client.get(f"/api/runs/{run_id}")
        if resp.json()["status"] in ("completed", "failed"):
            break
        await asyncio.sleep(0.5)

    resp = await client.get(f"/api/analysis/tempo/{run_id}")
    # Either 200 with empty result or 409 if no events
    assert resp.status_code in (200, 409)
