"""Production API exposure proof for Phase 111 time-on-target execution."""

from __future__ import annotations

import asyncio
import copy
from pathlib import Path
from typing import Any

import pytest

from stochastic_warfare.simulation.scenario import (
    load_campaign_scenario_config,
)


pytestmark = [pytest.mark.api, pytest.mark.asyncio]

SCENARIO_PATH = Path(
    "data/scenarios/time_on_target_validation/scenario.yaml",
)


def _shipped_inline_config() -> dict[str, Any]:
    """Return the shipped scenario only after the strict production load."""
    return load_campaign_scenario_config(SCENARIO_PATH).model_dump(mode="json")


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


async def test_time_on_target_result_is_exact_and_side_filterable(
    client: Any,
) -> None:
    response = await client.post(
        "/api/runs/from-config",
        json={
            "config": _shipped_inline_config(),
            "seed": 42,
            "max_ticks": 30,
        },
    )
    assert response.status_code == 202
    run_id = response.json()["run_id"]

    detail = await _wait_for_terminal(client, run_id)
    assert detail["status"] == "completed", detail.get("error_message")

    blue_response = await client.get(
        f"/api/runs/{run_id}/events",
        params={
            "event_type": "TimeOnTargetMissionEvent",
            "side": "blue",
            "limit": 10,
        },
    )
    assert blue_response.status_code == 200
    assert blue_response.json() == {
        "events": [
            {
                "tick": 23,
                "event_type": "TimeOnTargetMissionEvent",
                "source": "combat",
                "data": {
                    "mission_id": "blue_validation_tot",
                    "attacker_side": "blue",
                    "target_unit_id": "red_hemtt_0000",
                    "target_position": [22000.0, 10000.0, 0.0],
                    "scheduled_impact_time_s": 120.0,
                    "processing_time_s": 120.0,
                    "battery_results": [
                        {
                            "battery_id": "blue_m109a6_0000",
                            "source_equipment_index": 0,
                            "runtime_system_multiplier": 1,
                            "weapon_id": "m284_155mm",
                            "ammo_id": "m982_excalibur",
                            "planned_fire_position": [
                                1000.0,
                                9000.0,
                                0.0,
                            ],
                            "actual_fire_position": [
                                1000.0,
                                9000.0,
                                0.0,
                            ],
                            "scheduled_fire_time_s": 60.0,
                            "predicted_time_of_flight_s": 60.0,
                            "processing_time_s": 60.0,
                            "status": "fired",
                            "reason": "",
                            "rounds_fired": 1,
                            "generated_impact_count": 1,
                        },
                        {
                            "battery_id": "blue_m109a6_0001",
                            "source_equipment_index": 0,
                            "runtime_system_multiplier": 1,
                            "weapon_id": "m284_155mm",
                            "ammo_id": "m982_excalibur",
                            "planned_fire_position": [
                                4000.0,
                                11000.0,
                                0.0,
                            ],
                            "actual_fire_position": [
                                4000.0,
                                11000.0,
                                0.0,
                            ],
                            "scheduled_fire_time_s": 65.0,
                            "predicted_time_of_flight_s": 55.0,
                            "processing_time_s": 65.0,
                            "status": "fired",
                            "reason": "",
                            "rounds_fired": 1,
                            "generated_impact_count": 1,
                        },
                    ],
                    "total_generated_impacts": 2,
                    "near_target_impacts": 2,
                    "outcome": "completed",
                    "target_effect": "disabled",
                    "target_status_before": "ACTIVE",
                    "target_status_after": "DISABLED",
                },
            },
        ],
        "total": 1,
        "offset": 0,
        "limit": 10,
    }

    red_response = await client.get(
        f"/api/runs/{run_id}/events",
        params={
            "event_type": "TimeOnTargetMissionEvent",
            "side": "red",
            "limit": 10,
        },
    )
    assert red_response.status_code == 200
    assert red_response.json() == {
        "events": [],
        "total": 0,
        "offset": 0,
        "limit": 10,
    }


async def test_malformed_nested_time_on_target_config_is_rejected(
    client: Any,
) -> None:
    malformed = _shipped_inline_config()
    battery = malformed["indirect_fire"]["time_on_target_missions"][0][
        "batteries"
    ][0]
    battery["time_of_flight_seconds"] = battery.pop("time_of_flight_s")

    response = await client.post(
        "/api/runs/from-config",
        json={
            "config": malformed,
            "seed": 42,
            "max_ticks": 1,
        },
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "time_of_flight_s" in detail
    assert "time_of_flight_seconds" in detail


async def test_unresolved_nested_battery_reference_is_rejected_before_persistence(
    client: Any,
    app: Any,
) -> None:
    unresolved = copy.deepcopy(_shipped_inline_config())
    unresolved["indirect_fire"]["time_on_target_missions"][0]["batteries"][
        0
    ]["unit_id"] = "blue_missing_battery"
    before_runs = await app.state.db.count_runs()

    response = await client.post(
        "/api/runs/from-config",
        json={
            "config": unresolved,
            "seed": 42,
            "max_ticks": 1,
        },
    )
    assert response.status_code == 422
    assert response.json() == {
        "detail": (
            "mission 'blue_validation_tot' references unknown battery "
            "unit(s) ['blue_missing_battery']"
        ),
    }
    assert await app.state.db.count_runs() == before_runs
    assert app.state.run_manager._tasks == {}
    assert app.state.run_manager._progress_queues == {}
    assert app.state.run_manager._cancel_events == {}
