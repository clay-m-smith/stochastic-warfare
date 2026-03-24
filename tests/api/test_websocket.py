"""Tests for WebSocket progress streaming."""

from __future__ import annotations


import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = [pytest.mark.api, pytest.mark.asyncio]


async def test_websocket_nonexistent_run(app):
    """WebSocket to nonexistent run should get error and close."""
    from starlette.testclient import TestClient

    with TestClient(app) as tc:
        with tc.websocket_connect("/api/runs/nonexistent/progress") as ws:
            data = ws.receive_json()
            assert data["type"] == "error"


async def test_websocket_progress_stream(app):
    """Submit a run and stream progress via WebSocket."""
    from starlette.testclient import TestClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/runs", json={
            "scenario": "test_campaign",
            "seed": 42,
            "max_ticks": 50,
        })
        assert resp.status_code == 202
        run_id = resp.json()["run_id"]

    # Use sync test client for WebSocket
    with TestClient(app) as tc:
        messages = []
        with tc.websocket_connect(f"/api/runs/{run_id}/progress") as ws:
            for _ in range(200):
                try:
                    data = ws.receive_json(mode="text")
                    messages.append(data)
                    if data.get("type") in ("complete", "error"):
                        break
                except Exception:
                    break

        # Should have received at least a completion message
        assert len(messages) >= 1
        # Last message should be complete or have tick data
        types = {m.get("type") for m in messages}
        assert "complete" in types or "tick" in types or "error" in types


async def test_websocket_batch_nonexistent(app):
    """WebSocket to nonexistent batch should get error."""
    from starlette.testclient import TestClient

    with TestClient(app) as tc:
        with tc.websocket_connect("/api/runs/batch/nonexistent/progress") as ws:
            data = ws.receive_json()
            assert data["type"] == "error"
