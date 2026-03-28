"""Tests for meta/health endpoints."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.api, pytest.mark.asyncio]


async def test_health_endpoint(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert data["scenario_count"] >= 41
    assert data["unit_count"] >= 46


async def test_eras_endpoint(client):
    resp = await client.get("/api/meta/eras")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 5
    era_names = {e["name"] for e in data}
    assert "MODERN" in era_names
    assert "WW2" in era_names
    assert "WW1" in era_names
    assert "NAPOLEONIC" in era_names
    assert "ANCIENT_MEDIEVAL" in era_names


async def test_eras_have_disabled_modules(client):
    resp = await client.get("/api/meta/eras")
    data = resp.json()
    modern = next(e for e in data if e["name"] == "MODERN")
    assert modern["disabled_modules"] == []

    ww2 = next(e for e in data if e["name"] == "WW2")
    assert len(ww2["disabled_modules"]) > 0
    assert "space" in ww2["disabled_modules"]


async def test_doctrines_endpoint(client):
    resp = await client.get("/api/meta/doctrines")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 21
    for d in data:
        assert "name" in d
        assert "category" in d


async def test_terrain_types_endpoint(client):
    resp = await client.get("/api/meta/terrain-types")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert "OPEN" in data
    assert "URBAN_DENSE" in data
    assert "DESERT_SAND" in data
    assert len(data) >= 10


async def test_health_version_matches_package(client):
    from api import __version__

    resp = await client.get("/api/health")
    data = resp.json()
    assert data["version"] == __version__


async def test_doctrines_have_categories(client):
    resp = await client.get("/api/meta/doctrines")
    data = resp.json()
    categories = {d["category"] for d in data}
    assert len(categories) >= 2


# ---------------------------------------------------------------------------
# Phase 92: Schools, Commanders, Weapons metadata
# ---------------------------------------------------------------------------


async def test_schools_endpoint(client):
    resp = await client.get("/api/meta/schools")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 9
    ids = {s["school_id"] for s in data}
    assert "maneuverist" in ids
    assert "clausewitzian" in ids
    assert "sun_tzu" in ids
    for s in data:
        assert s["display_name"]
        assert s["description"]
        assert isinstance(s["ooda_multiplier"], float)


async def test_commanders_endpoint(client):
    resp = await client.get("/api/meta/commanders")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 10
    ids = {c["profile_id"] for c in data}
    assert "aggressive_armor" in ids
    assert "balanced_default" in ids
    for c in data:
        assert c["display_name"]
        assert isinstance(c["traits"], dict)
        if c["profile_id"] == "aggressive_armor":
            assert "aggression" in c["traits"]
            assert c["traits"]["aggression"] == pytest.approx(0.85)


async def test_weapons_endpoint(client):
    resp = await client.get("/api/meta/weapons")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 40
    ids = {w["weapon_id"] for w in data}
    assert "m256_smoothbore" in ids or any("m256" in wid for wid in ids)
    for w in data:
        assert w["weapon_id"]
        assert isinstance(w["max_range_m"], float)


async def test_weapon_detail(client):
    # Find a known weapon first
    resp = await client.get("/api/meta/weapons")
    data = resp.json()
    assert len(data) > 0
    first_id = data[0]["weapon_id"]

    resp2 = await client.get(f"/api/meta/weapons/{first_id}")
    assert resp2.status_code == 200
    detail = resp2.json()
    assert detail["weapon_id"] == first_id
    assert isinstance(detail["definition"], dict)
    assert len(detail["definition"]) > 0


async def test_weapon_detail_not_found(client):
    resp = await client.get("/api/meta/weapons/nonexistent_weapon_xyz")
    assert resp.status_code == 404
