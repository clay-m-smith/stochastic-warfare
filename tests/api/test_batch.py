"""Tests for batch/Monte Carlo execution."""

from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio

pytestmark = [pytest.mark.api, pytest.mark.asyncio]


async def test_submit_batch(client):
    resp = await client.post("/api/runs/batch", json={
        "scenario": "test_campaign",
        "num_iterations": 3,
        "base_seed": 42,
        "max_ticks": 20,
    })
    assert resp.status_code == 202
    data = resp.json()
    assert "batch_id" in data
    assert data["status"] == "pending"


async def test_submit_batch_not_found(client):
    resp = await client.post("/api/runs/batch", json={
        "scenario": "nonexistent_scenario",
        "num_iterations": 3,
        "base_seed": 42,
        "max_ticks": 20,
    })
    assert resp.status_code == 404


async def test_submit_and_poll_batch(client):
    resp = await client.post("/api/runs/batch", json={
        "scenario": "test_campaign",
        "num_iterations": 3,
        "base_seed": 42,
        "max_ticks": 20,
    })
    batch_id = resp.json()["batch_id"]

    for _ in range(120):
        resp = await client.get(f"/api/runs/batch/{batch_id}")
        data = resp.json()
        if data["status"] in ("completed", "failed"):
            break
        await asyncio.sleep(0.5)
    else:
        pytest.fail("Batch did not complete within timeout")

    assert data["status"] == "completed"
    assert data["completed_iterations"] == 3
    assert data["metrics"] is not None
    assert isinstance(data["metrics"], dict)


async def test_batch_metrics_have_stats(client):
    resp = await client.post("/api/runs/batch", json={
        "scenario": "test_campaign",
        "num_iterations": 3,
        "base_seed": 42,
        "max_ticks": 20,
    })
    batch_id = resp.json()["batch_id"]

    for _ in range(120):
        resp = await client.get(f"/api/runs/batch/{batch_id}")
        data = resp.json()
        if data["status"] in ("completed", "failed"):
            break
        await asyncio.sleep(0.5)

    if data["status"] == "completed" and data["metrics"]:
        for metric_name, stats in data["metrics"].items():
            assert "mean" in stats
            assert "std" in stats
            assert "min" in stats
            assert "max" in stats
            assert "n" in stats


async def test_get_batch_not_found(client):
    resp = await client.get("/api/runs/batch/nonexistent_id")
    assert resp.status_code == 404
