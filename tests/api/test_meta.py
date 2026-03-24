"""Tests for meta/health endpoints."""

from __future__ import annotations

import pytest
import pytest_asyncio

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
