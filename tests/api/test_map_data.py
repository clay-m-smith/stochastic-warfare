"""Tests for Phase 35 map data API — terrain capture, frame capture, endpoints."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.api


# ── Unit helpers ──────────────────────────────────────────────────────────


class _FakeHeightmap:
    def __init__(self, cell_size: float = 50.0, shape: tuple = (10, 12),
                 extent: tuple = (1000.0, 1600.0, 2000.0, 2500.0)):
        self.cell_size = cell_size
        self.shape = shape
        self.extent = extent


class _FakeClassification:
    def __init__(self, land_cover: list[list[int]] | None = None):
        self._lc = land_cover or [[0, 1], [9, 3]]

    def get_state(self) -> dict:
        return {"land_cover": self._lc}


class _FakeUnit:
    def __init__(self, entity_id: str, side: str, x: float, y: float,
                 domain_val: int = 0, status_val: int = 0, heading: float = 90.0,
                 unit_type: str = "infantry"):
        self.entity_id = entity_id
        self.position = SimpleNamespace(easting=x, northing=y)
        self.domain = SimpleNamespace(value=domain_val)
        self.status = SimpleNamespace(value=status_val)
        self.heading = heading
        self.unit_type = unit_type


# ── _capture_terrain tests ────────────────────────────────────────────────


def test_capture_terrain_with_heightmap_and_classification():
    from api.run_manager import RunManager

    ctx = SimpleNamespace(
        heightmap=_FakeHeightmap(),
        classification=_FakeClassification(),
    )
    config = {"objectives": [{"objective_id": "obj1", "position": [1200.0, 2200.0], "radius_m": 300.0}]}

    result = RunManager._capture_terrain(ctx, config)

    assert result["width_cells"] == 12
    assert result["height_cells"] == 10
    assert result["cell_size"] == 50.0
    assert result["origin_easting"] == 1000.0
    assert result["origin_northing"] == 2000.0
    assert result["land_cover"] == [[0, 1], [9, 3]]
    assert len(result["objectives"]) == 1
    assert result["objectives"][0]["id"] == "obj1"
    assert result["objectives"][0]["x"] == 1200.0
    assert result["objectives"][0]["radius"] == 300.0
    assert len(result["extent"]) == 4


def test_capture_terrain_no_heightmap():
    from api.run_manager import RunManager

    ctx = SimpleNamespace(heightmap=None, classification=None)
    result = RunManager._capture_terrain(ctx, {})

    assert result["width_cells"] == 0
    assert result["height_cells"] == 0
    assert result["land_cover"] == []
    assert result["objectives"] == []


def test_capture_terrain_no_classification():
    from api.run_manager import RunManager

    ctx = SimpleNamespace(
        heightmap=_FakeHeightmap(cell_size=100.0, shape=(20, 30), extent=(0, 3000, 0, 2000)),
        classification=None,
    )
    result = RunManager._capture_terrain(ctx, {})
    assert result["width_cells"] == 30
    assert result["height_cells"] == 20
    # With no classification, a default grid is generated (flat_desert = code 11)
    assert len(result["land_cover"]) == 20
    assert all(len(row) == 30 for row in result["land_cover"])
    assert result["land_cover"][0][0] == 11


def test_capture_terrain_numpy_land_cover():
    import numpy as np
    from api.run_manager import RunManager

    class NpClassification:
        def get_state(self):
            return {"land_cover": np.array([[0, 9], [3, 6]])}

    ctx = SimpleNamespace(heightmap=None, classification=NpClassification())
    result = RunManager._capture_terrain(ctx, {})
    assert result["land_cover"] == [[0, 9], [3, 6]]


# ── _capture_frame tests ─────────────────────────────────────────────────


def test_capture_frame_basic():
    from api.run_manager import RunManager

    u1 = _FakeUnit("u1", "blue", 100.0, 200.0, domain_val=0, status_val=0, heading=45.0, unit_type="tank")
    u2 = _FakeUnit("u2", "red", 300.0, 400.0, domain_val=2, status_val=3, heading=180.0, unit_type="ship")
    ctx = SimpleNamespace(units_by_side={"blue": [u1], "red": [u2]})

    frame = RunManager._capture_frame(10, ctx)

    assert frame["tick"] == 10
    assert len(frame["units"]) == 2
    blue_unit = next(u for u in frame["units"] if u["side"] == "blue")
    assert blue_unit["id"] == "u1"
    assert blue_unit["x"] == 100.0
    assert blue_unit["y"] == 200.0
    assert blue_unit["d"] == 0
    assert blue_unit["t"] == "tank"
    red_unit = next(u for u in frame["units"] if u["side"] == "red")
    assert red_unit["s"] == 3


def test_capture_frame_empty_sides():
    from api.run_manager import RunManager

    ctx = SimpleNamespace(units_by_side={})
    frame = RunManager._capture_frame(0, ctx)
    assert frame["tick"] == 0
    assert frame["units"] == []


# ── Endpoint tests ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_terrain_endpoint_completed_run(client):
    """Submit run, wait for completion, verify terrain endpoint."""
    resp = await client.post("/api/runs", json={
        "scenario": "test_campaign", "seed": 42, "max_ticks": 50,
    })
    run_id = resp.json()["run_id"]

    for _ in range(60):
        resp = await client.get(f"/api/runs/{run_id}")
        if resp.json()["status"] == "completed":
            break
        await asyncio.sleep(0.5)

    resp = await client.get(f"/api/runs/{run_id}/terrain")
    assert resp.status_code == 200
    data = resp.json()
    assert "width_cells" in data
    assert "height_cells" in data
    assert "cell_size" in data
    assert "land_cover" in data
    assert "objectives" in data
    assert "extent" in data


@pytest.mark.asyncio
async def test_frames_endpoint_completed_run(client):
    """Submit run, wait for completion, verify frames endpoint."""
    resp = await client.post("/api/runs", json={
        "scenario": "test_campaign", "seed": 42, "max_ticks": 50,
    })
    run_id = resp.json()["run_id"]

    for _ in range(60):
        resp = await client.get(f"/api/runs/{run_id}")
        if resp.json()["status"] == "completed":
            break
        await asyncio.sleep(0.5)

    resp = await client.get(f"/api/runs/{run_id}/frames")
    assert resp.status_code == 200
    data = resp.json()
    assert "frames" in data
    assert "total_frames" in data
    assert isinstance(data["frames"], list)
    if data["total_frames"] > 0:
        frame = data["frames"][0]
        assert "tick" in frame
        assert "units" in frame
        if len(frame["units"]) > 0:
            unit = frame["units"][0]
            assert "id" in unit
            assert "side" in unit
            assert "x" in unit
            assert "y" in unit


@pytest.mark.asyncio
async def test_frames_endpoint_tick_range(client):
    """Verify start_tick/end_tick filtering on frames endpoint."""
    resp = await client.post("/api/runs", json={
        "scenario": "test_campaign", "seed": 42, "max_ticks": 50,
    })
    run_id = resp.json()["run_id"]

    for _ in range(60):
        resp = await client.get(f"/api/runs/{run_id}")
        if resp.json()["status"] == "completed":
            break
        await asyncio.sleep(0.5)

    # Get all frames first
    resp_all = await client.get(f"/api/runs/{run_id}/frames")
    all_data = resp_all.json()

    if all_data["total_frames"] > 1:
        # Request frames from tick 5 onwards
        resp = await client.get(f"/api/runs/{run_id}/frames?start_tick=5")
        data = resp.json()
        for f in data["frames"]:
            assert f["tick"] >= 5


@pytest.mark.asyncio
async def test_terrain_endpoint_not_found(client):
    resp = await client.get("/api/runs/nonexistent/terrain")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_frames_endpoint_not_found(client):
    resp = await client.get("/api/runs/nonexistent/frames")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_terrain_endpoint_no_data(client):
    """Pre-Phase-35 run (no terrain_json) returns empty terrain."""
    db = client._transport.app.state.db
    await db.create_run("old_run", "test", "path", 42, 100)
    await db.update_run_status("old_run", "completed")

    resp = await client.get("/api/runs/old_run/terrain")
    assert resp.status_code == 200
    data = resp.json()
    assert data["width_cells"] == 0
    assert data["land_cover"] == []


@pytest.mark.asyncio
async def test_frames_endpoint_no_data(client):
    """Pre-Phase-35 run (no frames_json) returns empty frames."""
    db = client._transport.app.state.db
    await db.create_run("old_run2", "test", "path", 42, 100)
    await db.update_run_status("old_run2", "completed")

    resp = await client.get("/api/runs/old_run2/frames")
    assert resp.status_code == 200
    data = resp.json()
    assert data["frames"] == []
    assert data["total_frames"] == 0
