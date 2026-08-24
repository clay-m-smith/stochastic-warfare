"""Phase 39 tests: frame interval, __main__, static serving, terrain types."""

from __future__ import annotations

import importlib
from pathlib import Path

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

    @pytest.mark.test_evidence("structural_only")
    def test_main_module_import_does_not_raise_structural_diagnostic(
        self,
    ):
        """Structural import diagnostic only; it makes no runtime claim."""
        module = importlib.import_module("api.__main__")
        assert module.__name__ == "api.__main__"


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


def test_openapi_remains_available_with_spa_fallback(
    tmp_path: Path,
):
    """The built frontend catch-all must not break OpenAPI generation."""
    from api.config import ApiSettings
    from api.main import create_app

    frontend_dist = tmp_path / "frontend-dist"
    frontend_dist.mkdir()
    (frontend_dist / "index.html").write_text(
        "<!doctype html><title>test</title>",
        encoding="utf-8",
    )
    payload = create_app(
        ApiSettings(frontend_dir=str(frontend_dist)),
    ).openapi()

    assert payload["openapi"].startswith("3.")
    assert payload["info"]["title"] == "Stochastic Warfare API"


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
