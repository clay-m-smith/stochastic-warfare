"""Production publication proofs for Phase 113 morale ownership."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from stochastic_warfare.entities.base import UnitStatus
from stochastic_warfare.morale.state import MoraleState
from stochastic_warfare.simulation.engine import EngineConfig
from stochastic_warfare.validation.campaign_data import HistoricalCampaign
from stochastic_warfare.validation.campaign_runner import (
    CampaignRunner,
    CampaignRunnerConfig,
)


pytestmark = pytest.mark.api

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _morale_transition_config() -> dict[str, Any]:
    """Return one typed two-unit scenario with deterministic degradation."""
    return {
        "name": "Phase 113 morale exposure",
        "date": "2024-01-01T00:00:00Z",
        "duration_hours": 1.0,
        "terrain": {
            "width_m": 20_000,
            "height_m": 10_000,
            "terrain_type": "flat_desert",
        },
        "sides": [
            {
                "side": "blue",
                "units": [
                    {
                        "unit_type": "m1a2",
                        "count": 1,
                        "position": [1_000, 5_000],
                    },
                ],
                "morale_initial": "STEADY",
                "commander_profile": "aggressive_armor",
                "doctrine_template": "us_combined_arms",
            },
            {
                "side": "red",
                "units": [
                    {
                        "unit_type": "m1a2",
                        "count": 1,
                        "position": [15_000, 5_000],
                    },
                ],
                "morale_initial": "STEADY",
                "commander_profile": "cautious_infantry",
                "doctrine_template": "russian_deep_operations",
            },
        ],
        "victory_conditions": [{"type": "time_expired"}],
        "calibration_overrides": {
            "morale": {
                "base_degrade_rate": 0.8,
                "base_recover_rate": 0.0,
                "casualty_weight": 0.0,
                "suppression_weight": 0.0,
                "leadership_weight": 0.0,
                "cohesion_weight": 0.0,
                "force_ratio_weight": 0.0,
                "transition_cooldown_s": 0.0,
            },
        },
    }


async def _wait_for_terminal(client: Any, run_id: str) -> dict[str, Any]:
    for _ in range(200):
        response = await client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200, response.text
        detail = response.json()
        if detail["status"] in {"completed", "failed", "cancelled"}:
            return detail
        await asyncio.sleep(0.025)
    pytest.fail(f"Run {run_id} did not reach a terminal state")


@pytest.mark.asyncio
async def test_api_persists_runtime_morale_events_frames_and_analytics(
    client: Any,
) -> None:
    response = await client.post(
        "/api/runs/from-config",
        json={
            "config": _morale_transition_config(),
            "seed": 113,
            "max_ticks": 12,
        },
    )
    assert response.status_code == 202, response.text
    run_id = response.json()["run_id"]
    detail = await _wait_for_terminal(client, run_id)
    assert detail["status"] == "completed", detail.get("error_message")
    assert detail["result"]["ticks_executed"] == 12

    events_response = await client.get(
        f"/api/runs/{run_id}/events",
        params={"event_type": "MoraleStateChangeEvent", "limit": 10},
    )
    assert events_response.status_code == 200, events_response.text
    assert events_response.json() == {
        "events": [
            {
                "tick": 11,
                "event_type": "MoraleStateChangeEvent",
                "source": "morale",
                "data": {
                    "unit_id": "blue_m1a2_0000",
                    "old_state": 0,
                    "new_state": 1,
                    "cause": "stochastic",
                    "logical_time_s": 60.0,
                },
            },
            {
                "tick": 11,
                "event_type": "MoraleStateChangeEvent",
                "source": "morale",
                "data": {
                    "unit_id": "red_m1a2_0000",
                    "old_state": 0,
                    "new_state": 1,
                    "cause": "stochastic",
                    "logical_time_s": 60.0,
                },
            },
        ],
        "total": 2,
        "offset": 0,
        "limit": 10,
    }

    frames_response = await client.get(f"/api/runs/{run_id}/frames")
    assert frames_response.status_code == 200, frames_response.text
    frames = frames_response.json()
    assert frames["total_frames"] == 13
    final_frame = frames["frames"][-1]
    assert final_frame["tick"] == 12
    assert {
        unit["id"]: (unit["morale"], unit["status"])
        for unit in final_frame["units"]
    } == {
        "blue_m1a2_0000": (int(MoraleState.SHAKEN), int(UnitStatus.ACTIVE)),
        "red_m1a2_0000": (int(MoraleState.SHAKEN), int(UnitStatus.ACTIVE)),
    }

    analytics_response = await client.get(
        f"/api/runs/{run_id}/analytics/morale",
    )
    assert analytics_response.status_code == 200, analytics_response.text
    assert analytics_response.json() == {
        "timeline": [
            {
                "tick": 11,
                "steady": 0,
                "shaken": 2,
                "broken": 0,
                "routed": 0,
                "surrendered": 0,
            },
        ],
    }


def test_campaign_runner_exposes_exact_runtime_morale_and_events() -> None:
    campaign = HistoricalCampaign.model_validate(
        _morale_transition_config(),
    )
    runner = CampaignRunner(
        CampaignRunnerConfig(
            data_dir=str(DATA_DIR),
            engine_config=EngineConfig(max_ticks=12),
        ),
    )

    result = runner.run(campaign, seed=113)

    expected_states = {
        "blue_m1a2_0000": MoraleState.SHAKEN,
        "red_m1a2_0000": MoraleState.SHAKEN,
    }
    assert result.ticks_executed == 12
    assert result.final_morale_states == expected_states
    assert {
        unit.entity_id: unit.status
        for units in result.final_units_by_side.values()
        for unit in units
    } == {
        unit_id: UnitStatus.ACTIVE for unit_id in expected_states
    }
    assert result.recorder is not None
    morale_events = [
        event
        for event in result.recorder.events
        if event.event_type == "MoraleStateChangeEvent"
    ]
    assert [event.tick for event in morale_events] == [11, 11]
    assert [event.data for event in morale_events] == [
        {
            "unit_id": "blue_m1a2_0000",
            "old_state": 0,
            "new_state": 1,
            "cause": "stochastic",
            "logical_time_s": 60.0,
        },
        {
            "unit_id": "red_m1a2_0000",
            "old_state": 0,
            "new_state": 1,
            "cause": "stochastic",
            "logical_time_s": 60.0,
        },
    ]
