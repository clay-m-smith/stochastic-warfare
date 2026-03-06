"""Tests for scenario listing and detail endpoints."""

from __future__ import annotations

import pytest
import pytest_asyncio

pytestmark = [pytest.mark.api, pytest.mark.asyncio]


async def test_list_scenarios_returns_list(client):
    resp = await client.get("/api/scenarios")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 41


async def test_list_scenarios_has_required_fields(client):
    resp = await client.get("/api/scenarios")
    data = resp.json()
    for s in data:
        assert "name" in s
        assert "display_name" in s
        assert "era" in s
        assert "sides" in s


async def test_list_scenarios_includes_base_scenario(client):
    resp = await client.get("/api/scenarios")
    names = [s["name"] for s in resp.json()]
    assert "73_easting" in names
    assert "golan_heights" in names
    assert "test_scenario" in names


async def test_list_scenarios_includes_era_scenarios(client):
    resp = await client.get("/api/scenarios")
    names = [s["name"] for s in resp.json()]
    assert "midway" in names
    assert "waterloo" in names
    assert "jutland" in names
    assert "salamis" in names


async def test_get_scenario_by_name(client):
    resp = await client.get("/api/scenarios/73_easting")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "73_easting"
    assert "config" in data
    assert "force_summary" in data


async def test_get_scenario_era(client):
    resp = await client.get("/api/scenarios/midway")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "midway"
    assert "config" in data


async def test_get_scenario_config_has_sides(client):
    # Use test_campaign which has standard sides format
    resp = await client.get("/api/scenarios/test_campaign")
    data = resp.json()
    assert "sides" in data["config"]
    assert len(data["config"]["sides"]) >= 2


async def test_get_scenario_force_summary(client):
    resp = await client.get("/api/scenarios/test_campaign")
    data = resp.json()
    fs = data["force_summary"]
    assert len(fs) >= 2
    for side, info in fs.items():
        assert "unit_count" in info
        assert "unit_types" in info


async def test_get_scenario_not_found(client):
    resp = await client.get("/api/scenarios/nonexistent_scenario_xyz")
    assert resp.status_code == 404


async def test_scenarios_have_era_field(client):
    resp = await client.get("/api/scenarios")
    data = resp.json()
    eras = {s["era"] for s in data}
    assert "modern" in eras or "" in eras


async def test_scenario_detail_config_serializable(client):
    resp = await client.get("/api/scenarios/test_scenario")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["config"], dict)


async def test_scenario_ew_cbrn_flags(client):
    resp = await client.get("/api/scenarios")
    data = resp.json()
    # At least one scenario should have EW or CBRN
    has_ew = any(s.get("has_ew") for s in data)
    has_cbrn = any(s.get("has_cbrn") for s in data)
    assert has_ew or has_cbrn


async def test_list_scenarios_no_duplicates(client):
    resp = await client.get("/api/scenarios")
    data = resp.json()
    names = [s["name"] for s in data]
    assert len(names) == len(set(names))
