"""Tests for unit listing and detail endpoints."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.api, pytest.mark.asyncio]


async def test_list_units_returns_list(client):
    resp = await client.get("/api/units")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 46


async def test_list_units_has_required_fields(client):
    resp = await client.get("/api/units")
    data = resp.json()
    for u in data:
        assert "unit_type" in u
        assert "domain" in u


async def test_filter_units_by_domain_ground(client):
    resp = await client.get("/api/units?domain=ground")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    for u in data:
        assert u["domain"] == "ground"


async def test_filter_units_by_domain_aerial(client):
    resp = await client.get("/api/units?domain=aerial")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    for u in data:
        assert u["domain"] == "aerial"


async def test_filter_units_by_domain_naval(client):
    resp = await client.get("/api/units?domain=naval")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    for u in data:
        assert u["domain"] == "naval"


async def test_filter_units_by_era(client):
    resp = await client.get("/api/units?era=ww2")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    for u in data:
        assert u["era"] == "ww2"


async def test_get_unit_by_type(client):
    # First find a valid unit type
    resp = await client.get("/api/units")
    data = resp.json()
    assert len(data) > 0
    first_type = data[0]["unit_type"]

    resp = await client.get(f"/api/units/{first_type}")
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["unit_type"] == first_type
    assert "definition" in detail


async def test_get_unit_not_found(client):
    resp = await client.get("/api/units/nonexistent_unit_xyz")
    assert resp.status_code == 404


async def test_units_include_multiple_domains(client):
    resp = await client.get("/api/units")
    data = resp.json()
    domains = {u["domain"] for u in data}
    assert "ground" in domains
    assert "aerial" in domains


async def test_units_include_era_units(client):
    resp = await client.get("/api/units")
    data = resp.json()
    eras = {u["era"] for u in data}
    assert len(eras) >= 2


async def test_filter_by_category(client):
    # Get a category from available units
    resp = await client.get("/api/units")
    data = resp.json()
    cats = {u["category"] for u in data if u["category"]}
    if cats:
        cat = sorted(cats)[0]
        resp2 = await client.get(f"/api/units?category={cat}")
        assert resp2.status_code == 200
        filtered = resp2.json()
        for u in filtered:
            assert u["category"] == cat


async def test_unit_detail_has_definition_dict(client):
    resp = await client.get("/api/units")
    data = resp.json()
    first_type = data[0]["unit_type"]

    resp = await client.get(f"/api/units/{first_type}")
    detail = resp.json()
    assert isinstance(detail["definition"], dict)
    assert "unit_type" in detail["definition"]


async def test_combined_filter_domain_and_era(client):
    resp = await client.get("/api/units?domain=ground&era=modern")
    assert resp.status_code == 200
    data = resp.json()
    for u in data:
        assert u["domain"] == "ground"
        assert u["era"] == "modern"
