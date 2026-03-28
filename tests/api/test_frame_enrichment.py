"""Tests for Phase 92 replay frame enrichment."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api.config import ApiSettings
from api.database import Database
from api.main import create_app
from api.run_manager import RunManager


# ---------------------------------------------------------------------------
# Unit test: _capture_frame enrichment
# ---------------------------------------------------------------------------


class _MockPosition:
    def __init__(self, e: float = 100.0, n: float = 200.0):
        self.easting = e
        self.northing = n


class _MockPosture:
    """Simulates an IntEnum posture."""
    def __init__(self, name: str):
        self.name = name
        self.value = 0


class _MockPersonnel:
    def __init__(self, effective: bool = True):
        self._effective = effective

    def is_effective(self) -> bool:
        return self._effective


class _MockUnit:
    def __init__(
        self,
        entity_id: str = "u1",
        side: str = "blue",
        posture_name: str = "MOVING",
        fuel: float = 0.75,
        personnel_eff: list[bool] | None = None,
    ):
        self.entity_id = entity_id
        self.position = _MockPosition()
        self.domain = SimpleNamespace(value=0)
        self.status = SimpleNamespace(value=0)
        self.heading = 45.0
        self.unit_type = "tank"
        self.posture = _MockPosture(posture_name)
        self.fuel_remaining = fuel
        if personnel_eff is not None:
            self.personnel = [_MockPersonnel(e) for e in personnel_eff]
        else:
            self.personnel = [_MockPersonnel(True), _MockPersonnel(True)]


def test_capture_frame_enriched_fields():
    """_capture_frame returns enriched fields when state dicts provided."""
    unit = _MockUnit(entity_id="u1", posture_name="DEFENSIVE", fuel=0.6,
                     personnel_eff=[True, True, False])
    ctx = SimpleNamespace(
        units_by_side={"blue": [unit]},
        unit_sensors={},
        fog_of_war=None,
        unit_weapons={},
        morale_states={},
    )
    morale_states = {"u1": SimpleNamespace(value=1)}  # SHAKEN
    suppression_states = {"u1": SimpleNamespace(value=0.5)}  # 50% -> level 2
    engaged_ids = {"u1"}

    frame = RunManager._capture_frame(
        tick=10, ctx=ctx,
        morale_states=morale_states,
        suppression_states=suppression_states,
        engaged_ids=engaged_ids,
        unit_weapons={},
    )

    assert frame["tick"] == 10
    u = frame["units"][0]
    assert u["id"] == "u1"
    assert u["mo"] == 1  # SHAKEN
    assert u["po"] == "DEFENSIVE"
    assert u["hp"] == pytest.approx(2 / 3, abs=0.01)
    assert u["fp"] == 0.6
    assert u["su"] == 2  # int(0.5 * 4)
    assert u["eg"] is True


def test_capture_frame_defaults_without_enrichment():
    """_capture_frame without enrichment args still works (backward compat)."""
    unit = _MockUnit()
    ctx = SimpleNamespace(
        units_by_side={"blue": [unit]},
        unit_sensors={},
        fog_of_war=None,
    )

    frame = RunManager._capture_frame(tick=1, ctx=ctx)
    u = frame["units"][0]
    assert u["id"] == "u1"
    # Enriched keys should not be present when no state provided
    assert "mo" not in u or u.get("mo", 0) == 0


def test_capture_frame_no_personnel():
    """Units with no personnel use status-based health defaults."""
    unit = _MockUnit()
    del unit.personnel  # Remove personnel attr
    ctx = SimpleNamespace(
        units_by_side={"blue": [unit]},
        unit_sensors={},
        fog_of_war=None,
    )

    frame = RunManager._capture_frame(
        tick=1, ctx=ctx,
        morale_states={},
        suppression_states={},
        engaged_ids=set(),
        unit_weapons={},
    )
    u = frame["units"][0]
    assert u["hp"] == 1.0  # ACTIVE status -> 1.0


# ---------------------------------------------------------------------------
# Integration: frame deserialization backward compat
# ---------------------------------------------------------------------------


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
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await db.close()


@pytest.mark.asyncio
async def test_old_frames_deserialize_with_defaults(client: AsyncClient):
    """Old runs without enriched fields should deserialize with defaults."""
    db = client._transport.app.state.db  # type: ignore[attr-defined]
    # Insert a run with old-style frames (no enriched fields)
    old_frames = [
        {"tick": 0, "units": [
            {"id": "u1", "side": "blue", "x": 100, "y": 200,
             "d": 0, "s": 0, "h": 0, "t": "tank"},
        ]},
    ]
    await db.create_run("old_run", "test", "path", 42, 100)
    await db.update_run_status(
        "old_run", "completed",
        frames_json=json.dumps(old_frames),
        events_json="[]",
    )

    resp = await client.get("/api/runs/old_run/frames")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["frames"]) == 1
    u = data["frames"][0]["units"][0]
    # Enriched fields should have defaults
    assert u["morale"] == 0
    assert u["posture"] == ""
    assert u["health"] == 1.0
    assert u["fuel_pct"] == 1.0
    assert u["ammo_pct"] == 1.0
    assert u["suppression"] == 0
    assert u["engaged"] is False


@pytest.mark.asyncio
async def test_enriched_frames_deserialize(client: AsyncClient):
    """New runs with enriched fields should deserialize correctly."""
    db = client._transport.app.state.db  # type: ignore[attr-defined]
    enriched_frames = [
        {"tick": 5, "units": [
            {"id": "u1", "side": "blue", "x": 100, "y": 200,
             "d": 0, "s": 0, "h": 45, "t": "tank",
             "mo": 2, "po": "DUG_IN", "hp": 0.75,
             "fp": 0.5, "ap": 0.3, "su": 3, "eg": True},
        ]},
    ]
    await db.create_run("new_run", "test", "path", 42, 100)
    await db.update_run_status(
        "new_run", "completed",
        frames_json=json.dumps(enriched_frames),
        events_json="[]",
    )

    resp = await client.get("/api/runs/new_run/frames")
    assert resp.status_code == 200
    u = resp.json()["frames"][0]["units"][0]
    assert u["morale"] == 2
    assert u["posture"] == "DUG_IN"
    assert u["health"] == 0.75
    assert u["fuel_pct"] == 0.5
    assert u["ammo_pct"] == 0.3
    assert u["suppression"] == 3
    assert u["engaged"] is True
