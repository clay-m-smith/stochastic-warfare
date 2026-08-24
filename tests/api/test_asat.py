"""Production API exposure proof for Phase 110 ASAT integration."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest


pytestmark = [pytest.mark.api, pytest.mark.asyncio]


async def _wait_for_terminal(
    client: Any,
    run_id: str,
) -> dict[str, Any]:
    for _ in range(200):
        response = await client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200
        detail = response.json()
        if detail["status"] in {"completed", "failed", "cancelled"}:
            return detail
        await asyncio.sleep(0.1)
    pytest.fail(f"Run {run_id} did not reach a terminal state")


async def test_asat_result_is_exposed_and_side_filterable(client: Any) -> None:
    response = await client.post(
        "/api/runs",
        json={
            "scenario": "space_asat_escalation",
            "seed": 42,
            "max_ticks": 3,
        },
    )
    assert response.status_code == 202
    run_id = response.json()["run_id"]

    detail = await _wait_for_terminal(client, run_id)
    assert detail["status"] == "completed", detail.get("error_message")

    red_response = await client.get(
        f"/api/runs/{run_id}/events",
        params={
            "event_type": "ASATEngagementEvent",
            "side": "red",
            "limit": 50_000,
        },
    )
    assert red_response.status_code == 200
    red_payload = red_response.json()
    assert red_payload["total"] == 1
    assert len(red_payload["events"]) == 1

    event = red_payload["events"][0]
    assert event["event_type"] == "ASATEngagementEvent"
    expected_data = {
        "order_id": "red_keyhole_strike_1",
        "asset_id": "red_nudol_1",
        "weapon_id": "nudol_asat",
        "attacker_side": "red",
        "target_satellite_id": "keyhole_optical_p0_s0",
        "target_constellation_id": "keyhole_optical",
        "launched": True,
        "hit": True,
        "outcome": "hit",
        "reason": "",
        "previous_constellation_count": 4,
        "new_constellation_count": 3,
    }
    assert {
        key: event["data"][key]
        for key in expected_data
    } == expected_data

    blue_response = await client.get(
        f"/api/runs/{run_id}/events",
        params={
            "event_type": "ASATEngagementEvent",
            "side": "blue",
            "limit": 50_000,
        },
    )
    assert blue_response.status_code == 200
    assert blue_response.json()["total"] == 0
