"""Tests for scenario editor endpoints — validate and from-config."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.api, pytest.mark.asyncio]


# --- Minimal valid config for CampaignScenarioConfig ---

def _minimal_config() -> dict:
    return {
        "name": "Test Custom",
        "date": "2025-01-01",
        "duration_hours": 4.0,
        "terrain": {
            "width_m": 5000,
            "height_m": 5000,
            "cell_size_m": 100,
        },
        "sides": [
            {
                "side": "blue",
                "units": [{"unit_type": "m1a2_abrams", "count": 2}],
            },
            {
                "side": "red",
                "units": [{"unit_type": "t72b3", "count": 2}],
            },
        ],
    }


# --- Validate endpoint ---


async def test_validate_valid_config(client):
    cfg = _minimal_config()
    resp = await client.post("/api/scenarios/validate", json={"config": cfg})
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert data["errors"] == []


async def test_validate_missing_required_fields(client):
    resp = await client.post("/api/scenarios/validate", json={"config": {}})
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is False
    assert len(data["errors"]) > 0


async def test_validate_bad_duration(client):
    cfg = _minimal_config()
    cfg["duration_hours"] = -1
    resp = await client.post("/api/scenarios/validate", json={"config": cfg})
    data = resp.json()
    assert data["valid"] is False
    assert any("duration" in e.lower() for e in data["errors"])


async def test_validate_one_side_fails(client):
    cfg = _minimal_config()
    cfg["sides"] = [cfg["sides"][0]]
    resp = await client.post("/api/scenarios/validate", json={"config": cfg})
    data = resp.json()
    assert data["valid"] is False
    assert any("2 sides" in e for e in data["errors"])


async def test_validate_missing_terrain(client):
    cfg = _minimal_config()
    del cfg["terrain"]
    resp = await client.post("/api/scenarios/validate", json={"config": cfg})
    data = resp.json()
    assert data["valid"] is False


async def test_validate_bad_type(client):
    cfg = _minimal_config()
    cfg["duration_hours"] = "not_a_number"
    resp = await client.post("/api/scenarios/validate", json={"config": cfg})
    data = resp.json()
    assert data["valid"] is False


async def test_validate_with_optional_configs(client):
    cfg = _minimal_config()
    cfg["ew_config"] = {"enable_ew": True}
    cfg["cbrn_config"] = {"enable_cbrn": True}
    resp = await client.post("/api/scenarios/validate", json={"config": cfg})
    data = resp.json()
    assert data["valid"] is True


# --- From-config endpoint ---


async def test_from_config_accepts_valid(client):
    cfg = _minimal_config()
    resp = await client.post("/api/runs/from-config", json={"config": cfg, "seed": 1, "max_ticks": 10})
    assert resp.status_code == 202
    data = resp.json()
    assert "run_id" in data
    assert data["status"] == "pending"


async def test_from_config_rejects_invalid(client):
    resp = await client.post("/api/runs/from-config", json={"config": {}, "seed": 1})
    assert resp.status_code == 422


async def test_from_config_missing_config_field(client):
    resp = await client.post("/api/runs/from-config", json={"seed": 1})
    assert resp.status_code == 422


async def test_from_config_custom_seed(client):
    cfg = _minimal_config()
    resp = await client.post("/api/runs/from-config", json={"config": cfg, "seed": 99, "max_ticks": 5})
    assert resp.status_code == 202
    data = resp.json()
    assert "run_id" in data


async def test_from_config_default_params(client):
    cfg = _minimal_config()
    resp = await client.post("/api/runs/from-config", json={"config": cfg})
    assert resp.status_code == 202


async def test_from_config_run_appears_in_list(client):
    cfg = _minimal_config()
    resp = await client.post("/api/runs/from-config", json={"config": cfg, "max_ticks": 5})
    run_id = resp.json()["run_id"]
    resp2 = await client.get(f"/api/runs/{run_id}")
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["scenario_name"] == "Test Custom"
