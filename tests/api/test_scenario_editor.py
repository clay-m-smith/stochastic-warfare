"""Tests for scenario editor endpoints — validate and from-config."""

from __future__ import annotations

import asyncio
import tempfile
import time
from typing import Any

import pytest

pytestmark = [pytest.mark.api, pytest.mark.asyncio]

_RUN_POLL_INTERVAL_S = 0.01
_RUN_POLL_TIMEOUT_S = 10.0
_RUN_PENDING_STATUSES = frozenset({"pending", "running"})
_RUN_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})


async def _wait_for_terminal_run(
    client,
    run_id: str,
    *,
    timeout_s: float = _RUN_POLL_TIMEOUT_S,
) -> dict[str, Any]:
    """Poll a run endpoint until it reports a terminal lifecycle status."""
    endpoint = f"/api/runs/{run_id}"
    started_at = time.monotonic()
    deadline = started_at + timeout_s
    attempts = 0

    while True:
        response = await client.get(endpoint)
        attempts += 1
        if response.status_code != 200:
            pytest.fail(
                f"run {run_id!r} status poll returned HTTP "
                f"{response.status_code} on attempt {attempts}: {response.text!r}",
            )

        payload = response.json()
        status = payload.get("status")
        if status in _RUN_TERMINAL_STATUSES:
            return payload
        if status not in _RUN_PENDING_STATUSES:
            pytest.fail(
                f"run {run_id!r} status poll returned unexpected status {status!r} on attempt {attempts}: {payload!r}",
            )

        remaining_s = deadline - time.monotonic()
        if remaining_s <= 0:
            elapsed_s = time.monotonic() - started_at
            pytest.fail(
                f"run {run_id!r} did not reach a terminal state within "
                f"{timeout_s:.1f}s after {attempts} polls "
                f"(elapsed={elapsed_s:.3f}s, last_status={status!r}, "
                f"last_payload={payload!r})",
            )
        await asyncio.sleep(min(_RUN_POLL_INTERVAL_S, remaining_s))


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


@pytest.mark.parametrize(
    "school_config",
    [
        {"enable_schools": True},
        {"enable_schools": False},
        {"blue_school": "maneuverist", "red_school": "attrition"},
        {"blue": "maneuverist", "red": "attrition"},
    ],
)
async def test_school_proxy_configs_fail_validation_and_submission(
    client,
    school_config,
):
    cfg = _minimal_config()
    cfg["school_config"] = school_config

    validation = await client.post(
        "/api/scenarios/validate",
        json={"config": cfg},
    )
    assert validation.status_code == 200
    assert validation.json()["valid"] is False

    submission = await client.post(
        "/api/runs/from-config",
        json={"config": cfg, "seed": 1, "max_ticks": 1},
    )
    assert submission.status_code == 422


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

    payload = await _wait_for_terminal_run(client, data["run_id"])
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


async def test_from_config_preserves_exact_school_and_side_commander_assignments(
    client,
):
    cfg = _minimal_config()
    cfg["sides"][0]["commander_profile"] = "joint_campaign"
    cfg["sides"][1]["commander_profile"] = "aggressive_armor"
    cfg["school_config"] = {
        "unit_assignments": {
            "blue_m1a2_0000": "maneuverist",
            "blue_m1a2_0001": "maneuverist",
            "red_t72m_0000": "attrition",
            "red_t72m_0001": "attrition",
        },
    }

    response = await client.post(
        "/api/runs/from-config",
        json={"config": cfg, "seed": 117, "max_ticks": 1},
    )
    assert response.status_code == 202, response.text
    run_id = response.json()["run_id"]

    payload = await _wait_for_terminal_run(client, run_id)
    assert payload["status"] == "completed", payload
    assignments = payload["result"]["provenance"]["initial_unit_assignments"]
    assert len(assignments) == 4
    assert {
        (
            assignment["side"],
            assignment["commander_profile_id"],
            assignment["doctrine_school_id"],
        )
        for assignment in assignments
    } == {
        ("blue", "joint_campaign", "maneuverist"),
        ("red", "aggressive_armor", "attrition"),
    }


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


async def test_public_scenario_config_validates_and_runs_without_claim_metadata(
    client,
) -> None:
    scenario = await client.get("/api/scenarios/73_easting")
    assert scenario.status_code == 200
    config = scenario.json()["config"]
    assert "documented_outcomes" not in config
    assert "sources" not in config
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
