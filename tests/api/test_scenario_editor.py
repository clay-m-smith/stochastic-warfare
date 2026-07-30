"""Tests for scenario editor endpoints — validate and from-config."""

from __future__ import annotations

import asyncio
import tempfile

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
                "units": [{"unit_type": "m1a2", "count": 2}],
            },
            {
                "side": "red",
                "units": [{"unit_type": "t72m", "count": 2}],
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
    invalid_configs = []
    bad_duration = _minimal_config()
    bad_duration["duration_hours"] = "not_a_number"
    invalid_configs.append(bad_duration)

    for bad_width in (True, "5000"):
        config = _minimal_config()
        config["terrain"]["width_m"] = bad_width
        invalid_configs.append(config)

    unknown_nested = _minimal_config()
    unknown_nested["terrain"]["phase112_typo"] = "must reject"
    invalid_configs.append(unknown_nested)

    for config in invalid_configs:
        resp = await client.post(
            "/api/scenarios/validate",
            json={"config": config},
        )
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


async def test_from_config_accepts_valid(client, monkeypatch):
    cfg = _minimal_config()
    monkeypatch.setattr(
        tempfile,
        "mkdtemp",
        lambda *args, **kwargs: pytest.fail(
            "inline production runs must not create a temporary scenario",
        ),
    )
    resp = await client.post("/api/runs/from-config", json={"config": cfg, "seed": 1, "max_ticks": 10})
    assert resp.status_code == 202
    data = resp.json()
    assert "run_id" in data
    assert data["status"] == "pending"

    detail = await client.get(f"/api/runs/{data['run_id']}")
    for _ in range(100):
        assert detail.status_code == 200
        if detail.json()["status"] in {"completed", "failed"}:
            break
        await asyncio.sleep(0.01)
        detail = await client.get(f"/api/runs/{data['run_id']}")
    else:
        pytest.fail("inline scenario did not reach a terminal state")
    payload = detail.json()
    assert payload["status"] == "completed", payload
    assert payload["scenario_path"] == "<inline-config>"
    assert payload["config_overrides"] == {}
    assert payload["result"]["authored_roster"] == [
        ["blue", 2],
        ["red", 2],
    ]
    assert payload["result"]["loaded_roster"] == [
        ["blue", 2],
        ["red", 2],
    ]


async def test_from_config_rejects_invalid(client):
    resp = await client.post("/api/runs/from-config", json={"config": {}, "seed": 1})
    assert resp.status_code == 422

    invalid_payloads = [
        {"config": _minimal_config(), "seed": True},
        {"config": _minimal_config(), "max_ticks": True},
        {"config": _minimal_config(), "seed": 1 << 63},
        {
            "config": {
                **_minimal_config(),
                "unknown_top_level": "must not be discarded",
            },
        },
        {
            "config": {
                **_minimal_config(),
                "calibration_overrides": {"advance_speed": 5.0},
            },
        },
        {
            "config": {
                **_minimal_config(),
                "terrain": {
                    **_minimal_config()["terrain"],
                    "phase112_typo": "must not be discarded",
                },
            },
        },
        {
            "config": {
                **_minimal_config(),
                "terrain": {
                    **_minimal_config()["terrain"],
                    "width_m": True,
                },
            },
        },
        {
            "config": {
                **_minimal_config(),
                "terrain": {
                    **_minimal_config()["terrain"],
                    "width_m": "5000",
                },
            },
        },
        {
            "config": _minimal_config(),
            "max_tikcs": 5,
        },
    ]
    for payload in invalid_payloads:
        rejected = await client.post(
            "/api/runs/from-config",
            json=payload,
        )
        assert rejected.status_code == 422, rejected.text


async def test_from_config_missing_config_field(client):
    resp = await client.post("/api/runs/from-config", json={"seed": 1})
    assert resp.status_code == 422


async def test_shipped_metadata_validates_and_runs_from_editor_config(
    client,
) -> None:
    scenario = await client.get("/api/scenarios/73_easting")
    assert scenario.status_code == 200
    config = scenario.json()["config"]
    assert "documented_outcomes" in config
    assert "blue_forces" in config

    validation = await client.post(
        "/api/scenarios/validate",
        json={"config": config},
    )
    assert validation.status_code == 200
    assert validation.json() == {"valid": True, "errors": []}

    submitted = await client.post(
        "/api/runs/from-config",
        json={
            "config": config,
            "seed": 112,
            "max_ticks": 1,
        },
    )
    assert submitted.status_code == 202, submitted.text


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
