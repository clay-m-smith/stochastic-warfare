"""Real production API witness for Phase 115 targeting exposure."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from httpx import AsyncClient

from stochastic_warfare.simulation.tactical_targeting import (
    targeting_decision_to_state,
    targeting_revalidation_outcome_to_state,
)
from stochastic_warfare.simulation.targeting_exposure import (
    TargetingExposureScope,
)
from stochastic_warfare.tools.replay import extract_replay_frames


pytestmark = [pytest.mark.api, pytest.mark.asyncio]


def _production_fow_config() -> dict[str, Any]:
    """Return a compact catalog-backed engagement with a current FOW witness."""
    return {
        "name": "Phase 115 production API targeting exposure",
        "date": "1917-11-20T06:20:00Z",
        "duration_hours": 1.0,
        "era": "ww1",
        "tick_resolution": {
            "strategic_s": 3_600.0,
            "operational_s": 300.0,
            "tactical_s": 5.0,
        },
        "weather_conditions": {"visibility_m": 3_000.0},
        "terrain": {
            "width_m": 10_000.0,
            "height_m": 2_000.0,
            "cell_size_m": 50.0,
            "terrain_type": "flat_desert",
        },
        "deployment": {"mode": "manual"},
        "sides": [
            {
                "side": "british",
                "units": [
                    {
                        "unit_type": "mark_iv_tank",
                        "count": 1,
                        "position": [1_000.0, 1_000.0, 0.0],
                    },
                ],
            },
            {
                "side": "german",
                "units": [
                    {
                        "unit_type": "german_sturmtruppen",
                        "count": 1,
                        "position": [1_000.0, 1_800.0, 0.0],
                    },
                ],
            },
        ],
        "objectives": [],
        "victory_conditions": [],
        "calibration_overrides": {
            "defensive_sides": [],
            "enable_fog_of_war": True,
            "enable_sensing_aware_standoff": True,
        },
    }


async def _wait_for_terminal_run(
    client: AsyncClient,
    run_id: str,
) -> dict[str, Any]:
    for _ in range(400):
        response = await client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200, response.text
        detail = response.json()
        if detail["status"] in {"completed", "failed", "cancelled"}:
            return detail
        await asyncio.sleep(0.025)
    pytest.fail(f"production API run {run_id} did not reach a terminal state")


def _decision_key(item: dict[str, Any]) -> tuple[int, str, str]:
    return (
        item["engine_tick"],
        item["battle_id"],
        item["shooter_id"],
    )


async def test_real_run_persists_exact_and_side_safe_targeting_frames(
    client: AsyncClient,
) -> None:
    """Factory, RunManager, persistence, and paired API scopes share evidence."""
    submitted = await client.post(
        "/api/runs/from-config",
        json={
            "config": _production_fow_config(),
            "seed": 115,
            "max_ticks": 1,
        },
    )
    assert submitted.status_code == 202, submitted.text
    run_id = submitted.json()["run_id"]

    detail = await _wait_for_terminal_run(client, run_id)
    assert detail["status"] == "completed", detail.get("error_message")
    assert detail["scenario_path"] == "<inline-config>"
    assert detail["result"]["loaded_roster"] == [
        ["british", 1],
        ["german", 1],
    ]

    privileged_response = await client.get(f"/api/runs/{run_id}/frames")
    assert privileged_response.status_code == 200, privileged_response.text
    privileged = privileged_response.json()
    assert privileged["scope"] == "PRIVILEGED_ENGINE"
    assert privileged["viewer_side"] is None
    assert privileged["total_frames"] >= 1

    exact_frame, exact_decision = next(
        (frame, decision)
        for frame in privileged["frames"]
        for decision in frame["targeting"]
        if (decision["shooter_side"] == "british" and decision["target_id"] is not None)
    )
    exact_key = _decision_key(exact_decision)
    exact_outcome = next(
        outcome for outcome in exact_frame["targeting_outcomes"] if _decision_key(outcome) == exact_key
    )
    assert exact_frame["tick"] == exact_decision["engine_tick"] == 1
    assert exact_decision["contact_source"] == "FOW_OBSERVER_WITNESS"
    assert exact_decision["weapon_id"] == "qf_6pdr_6cwt"
    assert exact_decision["contact_sensor_id"] == "binoculars_ww1"
    assert exact_decision["sensing_sensor_id"] == "binoculars_ww1"
    assert exact_decision["disposition"] == "VALID_STANDOFF_HOLD"
    assert exact_decision["hold_authorized"] is True
    assert exact_decision["engagement_solution_valid"] is True
    assert exact_outcome["target_id"] == exact_decision["target_id"]
    assert exact_outcome["weapon_id"] == exact_decision["weapon_id"]
    assert exact_outcome["ammunition_id"] == exact_decision["ammunition_id"]
    assert exact_outcome["revalidation_passed"] is True
    assert exact_outcome["disposition"] == "VALID_ENGAGEMENT_SOLUTION"

    side_response = await client.get(
        f"/api/runs/{run_id}/frames",
        params={"scope": "SIDE_FOW", "side": "british"},
    )
    assert side_response.status_code == 200, side_response.text
    side = side_response.json()
    assert side["scope"] == "SIDE_FOW"
    assert side["viewer_side"] == "british"
    assert side["total_frames"] == privileged["total_frames"]

    side_frame = next(frame for frame in side["frames"] if frame["tick"] == exact_frame["tick"])
    public_decision = next(
        decision for decision in side_frame["side_targeting"] if _decision_key(decision) == exact_key
    )
    public_outcome = next(
        outcome for outcome in side_frame["side_targeting_outcomes"] if _decision_key(outcome) == exact_key
    )
    assert {unit["side"] for unit in side_frame["units"]} == {"british"}
    assert public_decision["viewer_side"] == "british"
    assert public_decision["target_track_id"] is not None
    assert public_decision["target_track_id"] != exact_decision["target_id"]
    assert public_decision["target_track_id"] in {track["track_id"] for track in side_frame["tracks"]}
    assert public_decision["target_track_id"] in side_frame["detected"]["british"]
    assert public_decision["disposition"] == exact_decision["disposition"]
    assert public_decision["hold_authorized"] is True
    assert public_outcome["target_track_id"] == public_decision["target_track_id"]
    assert public_outcome["disposition"] == exact_outcome["disposition"]
    assert public_outcome["revalidation_passed"] is True
    assert side_frame["targeting"] == []
    assert side_frame["targeting_outcomes"] == []

    public_wire = json.dumps(side, sort_keys=True)
    hidden_values = {
        exact_decision["target_id"],
        exact_decision["weapon_id"],
        exact_decision["ammunition_id"],
        exact_decision["contact_sensor_id"],
        exact_decision["sensing_sensor_id"],
        exact_decision["fire_control_sensor_id"],
        exact_decision["weapon_modeled_role"],
        exact_decision["contact_sensor_modeled_role"],
        exact_decision["sensing_sensor_modeled_role"],
        exact_decision["fire_control_sensor_modeled_role"],
    } - {None}
    for hidden_value in hidden_values:
        assert hidden_value not in public_wire
    for hidden_field in (
        '"target_id"',
        '"weapon_id"',
        '"ammunition_id"',
        '"contact_sensor_id"',
        '"sensing_sensor_id"',
        '"fire_control_sensor_id"',
        '"weapon_modeled_role"',
        '"contact_sensor_modeled_role"',
        '"sensing_sensor_modeled_role"',
        '"fire_control_sensor_modeled_role"',
        "source_equipment_index",
    ):
        assert hidden_field not in public_wire

    db = client._transport.app.state.db  # type: ignore[attr-defined]
    persisted_row = await db.get_run(run_id)
    assert persisted_row is not None
    assert persisted_row["frames_json"] is not None
    persisted_frames = json.loads(persisted_row["frames_json"])
    assert isinstance(persisted_frames, list)
    persisted_exact_frame = next(frame for frame in persisted_frames if frame["tick"] == exact_frame["tick"])

    privileged_replay = extract_replay_frames(
        persisted_frames,
        scope=TargetingExposureScope.PRIVILEGED_ENGINE,
    )
    privileged_replay_frame = next(frame for frame in privileged_replay if frame.tick == exact_frame["tick"])
    replay_exact_decision = next(
        decision for decision in privileged_replay_frame.targeting if decision.key == exact_key
    )
    replay_exact_outcome = next(
        outcome for outcome in privileged_replay_frame.targeting_outcomes if outcome.key == exact_key
    )
    persisted_exact_decision = next(
        decision for decision in persisted_exact_frame["targeting"] if _decision_key(decision) == exact_key
    )
    persisted_exact_outcome = next(
        outcome for outcome in persisted_exact_frame["targeting_outcomes"] if _decision_key(outcome) == exact_key
    )
    assert targeting_decision_to_state(replay_exact_decision) == (persisted_exact_decision)
    assert (
        targeting_revalidation_outcome_to_state(
            replay_exact_outcome,
        )
        == persisted_exact_outcome
    )
    assert replay_exact_decision.target_id == exact_decision["target_id"]
    assert replay_exact_outcome.target_id == exact_decision["target_id"]
    assert {unit.side for unit in privileged_replay_frame.units} == {
        "british",
        "german",
    }

    side_replay = extract_replay_frames(
        persisted_frames,
        scope=TargetingExposureScope.SIDE_FOW,
        viewer_side="british",
    )
    side_replay_frame = next(frame for frame in side_replay if frame.tick == exact_frame["tick"])
    replay_public_decision = next(
        decision
        for decision in side_replay_frame.targeting
        if (
            decision.engine_tick,
            decision.battle_id,
            decision.shooter_id,
        )
        == exact_key
    )
    replay_public_outcome = next(
        outcome
        for outcome in side_replay_frame.targeting_outcomes
        if (
            outcome.engine_tick,
            outcome.battle_id,
            outcome.shooter_id,
        )
        == exact_key
    )
    persisted_public = persisted_exact_frame["side_fow"]["british"]
    persisted_public_decision = next(
        decision for decision in persisted_public["targeting"] if _decision_key(decision) == exact_key
    )
    persisted_public_outcome = next(
        outcome for outcome in persisted_public["targeting_outcomes"] if _decision_key(outcome) == exact_key
    )
    assert replay_public_decision.to_wire() == persisted_public_decision
    assert replay_public_outcome.to_wire() == persisted_public_outcome
    assert replay_public_decision.target_track_id == (public_decision["target_track_id"])
    assert replay_public_outcome.target_track_id == (public_decision["target_track_id"])
    assert replay_public_decision.target_track_id != (replay_exact_decision.target_id)
    assert [track.to_wire() for track in side_replay_frame.tracks] == (persisted_public["tracks"])
    assert {unit.side for unit in side_replay_frame.units} == {"british"}
    replay_public_wire = json.dumps(
        {
            "units": [
                {
                    "unit_id": unit.unit_id,
                    "side": unit.side,
                    "x": unit.x,
                    "y": unit.y,
                    "active": unit.active,
                }
                for unit in side_replay_frame.units
            ],
            "tracks": [track.to_wire() for track in side_replay_frame.tracks],
            "targeting": [decision.to_wire() for decision in side_replay_frame.targeting],
            "targeting_outcomes": [outcome.to_wire() for outcome in side_replay_frame.targeting_outcomes],
        },
        sort_keys=True,
    )
    for hidden_value in hidden_values:
        assert hidden_value not in replay_public_wire
    for hidden_field in (
        '"target_id"',
        '"weapon_id"',
        '"ammunition_id"',
        '"contact_sensor_id"',
        '"sensing_sensor_id"',
        '"fire_control_sensor_id"',
        '"weapon_modeled_role"',
        '"contact_sensor_modeled_role"',
        '"sensing_sensor_modeled_role"',
        '"fire_control_sensor_modeled_role"',
        "source_equipment_index",
    ):
        assert hidden_field not in replay_public_wire
