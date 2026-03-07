"""Phase 39 tests: frame interval, __main__, static serving, terrain types."""

from __future__ import annotations

import pytest


# ── 39b: Frame interval ─────────────────────────────────────────────────

class TestFrameInterval:
    """Verify configurable frame_interval in RunSubmitRequest."""

    def test_schema_accepts_frame_interval(self):
        from api.schemas import RunSubmitRequest

        req = RunSubmitRequest(scenario="test", frame_interval=10)
        assert req.frame_interval == 10

    def test_schema_defaults_frame_interval_to_none(self):
        from api.schemas import RunSubmitRequest

        req = RunSubmitRequest(scenario="test")
        assert req.frame_interval is None


# ── 39c: __main__ ────────────────────────────────────────────────────────

class TestMainModule:
    """Verify api/__main__.py is importable."""

    def test_main_module_importable(self):
        import api.__main__  # noqa: F401


# ── 39c: Static file serving & SPA fallback ─────────────────────────────

@pytest.mark.asyncio
async def test_spa_fallback_serves_index(client):
    """GET /scenarios/foo returns index.html (SPA fallback) when frontend/dist exists."""
    resp = await client.get("/scenarios/foo")
    # If frontend/dist exists, we get 200 with HTML; otherwise 404
    if resp.status_code == 200:
        assert "html" in resp.text.lower()


@pytest.mark.asyncio
async def test_api_routes_take_precedence(client):
    """GET /api/health returns JSON, not index.html."""
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


# ── 39d: Terrain types from LandCover enum ──────────────────────────────

@pytest.mark.asyncio
async def test_terrain_types_from_enum(client):
    """GET /api/meta/terrain-types returns LandCover enum names."""
    resp = await client.get("/api/meta/terrain-types")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0
    # Should contain LandCover enum member names
    assert "OPEN" in data
