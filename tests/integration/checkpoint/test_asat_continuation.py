"""Full-runtime persistence and determinism proofs for Phase 110 ASAT."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

import pytest

from stochastic_warfare.simulation.engine import SimulationEngine
from stochastic_warfare.simulation.recorder import SimulationRecorder
from stochastic_warfare.simulation.scenario import ScenarioLoader
from stochastic_warfare.simulation.scenario import (
    CampaignScenarioConfig,
    load_campaign_scenario_config,
)


DATA_DIR = Path("data")
SCENARIO_PATH = (
    DATA_DIR / "scenarios/space_asat_escalation/scenario.yaml"
)
ORDER_ID = "red_keyhole_strike_1"
ASSET_ID = "red_nudol_1"
TARGET_ID = "keyhole_optical_p0_s0"
_HASHSEED_MARKER = "PHASE110_HASHSEED_RESULT="


def _engine(
    *,
    seed: int = 42,
    enable_asat: bool | None = None,
    execute_at_s: float | None = None,
) -> tuple[SimulationEngine, SimulationRecorder]:
    scenario_config = None
    if enable_asat is not None or execute_at_s is not None:
        payload = load_campaign_scenario_config(
            SCENARIO_PATH,
        ).model_dump(mode="python")
        if enable_asat is not None:
            payload["space_config"]["enable_asat"] = enable_asat
        if execute_at_s is not None:
            payload["space_config"]["asat_orders"][0][
                "execute_at_s"
            ] = execute_at_s
        scenario_config = CampaignScenarioConfig.model_validate(payload)
    context = ScenarioLoader(DATA_DIR).load(
        SCENARIO_PATH,
        seed=seed,
        scenario_config=scenario_config,
    )
    recorder = SimulationRecorder(context.event_bus)
    recorder.start()
    return (
        SimulationEngine(
            context,
            recorder=recorder,
            strict_mode=True,
        ),
        recorder,
    )


def _phase110_events(
    recorder: SimulationRecorder,
) -> list[dict[str, Any]]:
    return [
        {
            "tick": event.tick,
            "timestamp": event.timestamp.isoformat(),
            "event_type": event.event_type,
            "source": event.source,
            "data": event.data,
        }
        for event in recorder.events
        if event.event_type in {
            "ConstellationDegradedEvent",
            "ASATEngagementEvent",
            "DebrisCascadeEvent",
        }
    ]


def _decoded_checkpoint(engine: SimulationEngine) -> dict[str, Any]:
    return json.loads(engine.checkpoint().decode("utf-8"))


def test_fresh_checkpoint_continuation_before_and_after_action_is_exact(
) -> None:
    source, source_recorder = _engine(seed=42)
    assert source.step() is False
    before_action = source.checkpoint()
    assert _phase110_events(source_recorder) == []

    assert source.step() is False
    source_after_action = source.checkpoint()
    source_events_after_action = _phase110_events(source_recorder)
    assert [
        event["event_type"] for event in source_events_after_action
    ] == ["ConstellationDegradedEvent", "ASATEngagementEvent"]

    resumed, resumed_recorder = _engine(seed=999_110)
    resumed.restore(before_action)
    assert resumed.checkpoint() == before_action
    assert resumed.step() is False
    assert _decoded_checkpoint(resumed) == _decoded_checkpoint(source)
    assert _phase110_events(resumed_recorder) == source_events_after_action

    resumed_after, resumed_after_recorder = _engine(seed=888_110)
    resumed_after.restore(source_after_action)
    assert resumed_after.checkpoint() == source_after_action
    events_before_third_tick = _phase110_events(resumed_after_recorder)
    assert len(events_before_third_tick) == 2

    assert source.step() is False
    assert resumed_after.step() is False
    assert _decoded_checkpoint(resumed_after) == _decoded_checkpoint(source)
    assert _phase110_events(resumed_after_recorder) == events_before_third_tick
    assert len([
        event
        for event in _phase110_events(resumed_after_recorder)
        if event["event_type"] == "ASATEngagementEvent"
    ]) == 1


@pytest.mark.parametrize(
    ("corruption", "expected"),
    (
        ("catalog_fingerprint", "catalog fingerprint"),
        ("satellite_topology", "satellite topology"),
        ("asset_topology", "asset topology"),
        ("order_topology", "order topology"),
        ("asset_inventory", "rounds_remaining"),
        ("asat_fingerprint", "configuration fingerprint"),
        ("gps_service_state", "gps_engine state keys"),
        ("manager_time_overflow", "Constellation sim_time_s must be finite"),
        ("asset_ready_overflow", "invalid ready_at_s"),
    ),
)
def test_corrupt_space_checkpoint_is_rejected_before_any_runtime_mutation(
    corruption: str,
    expected: str,
) -> None:
    source, _ = _engine(seed=42)
    invalid = copy.deepcopy(source.get_state())
    space_state = invalid["context"]["space_engine"]
    asat_state = space_state["asat_engine"]

    if corruption == "catalog_fingerprint":
        space_state["catalog_fingerprint"] = "0" * 64
    elif corruption == "satellite_topology":
        space_state["constellation_manager"]["satellites"].pop(TARGET_ID)
    elif corruption == "asset_topology":
        asat_state["assets"].pop(ASSET_ID)
    elif corruption == "order_topology":
        asat_state["pending_order_ids"] = ["unknown_phase110_order"]
    elif corruption == "asset_inventory":
        asat_state["assets"][ASSET_ID]["rounds_remaining"] = 2
    elif corruption == "gps_service_state":
        space_state["gps_engine"] = {"bogus": "silently accepted before 110"}
    elif corruption == "manager_time_overflow":
        space_state["constellation_manager"]["sim_time_s"] = 10**400
    elif corruption == "asset_ready_overflow":
        asat_state["assets"][ASSET_ID]["ready_at_s"] = 10**400
    else:
        asat_state["configuration_fingerprint"] = "0" * 64

    fresh, _ = _engine(seed=999_110)
    for candidate in (source, fresh):
        before = candidate.checkpoint()
        with pytest.raises(ValueError, match=expected):
            candidate.set_state(copy.deepcopy(invalid))
        assert candidate.checkpoint() == before


@pytest.mark.parametrize(
    (
        "service_name",
        "field_name",
        "entry_key",
        "forged_value",
        "expected",
    ),
    (
        (
            "gps_engine",
            "previous_accuracy",
            "blue",
            99.0,
            "disagrees with the staged constellation state",
        ),
        (
            "satcom_engine",
            "previous_available",
            "blue",
            False,
            "disagrees with the staged constellation state",
        ),
        (
            "isr_engine",
            "last_overpass_time",
            TARGET_ID,
            1.0e12,
            "after checkpoint time",
        ),
    ),
)
def test_outcome_affecting_service_history_is_validated_atomically(
    service_name: str,
    field_name: str,
    entry_key: str,
    forged_value: float | bool,
    expected: str,
) -> None:
    source, _ = _engine(seed=42)
    source.step()
    source.step()
    invalid = source.get_state()
    invalid["context"]["space_engine"][service_name][field_name][
        entry_key
    ] = forged_value

    target, _ = _engine(seed=999_110)
    before = target.checkpoint()
    with pytest.raises(ValueError, match=expected):
        target.set_state(invalid)
    assert target.checkpoint() == before


def test_future_completed_action_cannot_be_transplanted_to_earlier_clock(
) -> None:
    completed, _ = _engine(seed=42)
    completed.step()
    completed.step()
    completed_state = completed.get_state()

    target, _ = _engine(seed=999_110)
    invalid = target.get_state()
    invalid["context"]["space_engine"] = copy.deepcopy(
        completed_state["context"]["space_engine"],
    )
    before = target.checkpoint()

    with pytest.raises(ValueError, match="checkpoint clock"):
        target.set_state(invalid)
    assert target.checkpoint() == before


def test_impossible_depleted_result_is_rejected_atomically() -> None:
    completed, _ = _engine(seed=42)
    completed.step()
    completed.step()
    invalid = completed.get_state()
    space_state = invalid["context"]["space_engine"]
    target_state = space_state["constellation_manager"]["satellites"][
        TARGET_ID
    ]
    target_state["is_active"] = True
    asat_state = space_state["asat_engine"]
    asset_state = asat_state["assets"][ASSET_ID]
    asset_state["rounds_remaining"] = 1
    asset_state["ready_at_s"] = 0.0
    result = asat_state["completed_orders"][ORDER_ID]
    result.update({
        "launched": False,
        "hit": False,
        "pk": 0.0,
        "outcome": "rejected",
        "reason": "asset_depleted",
        "debris_generated": 0,
        "rounds_remaining": 1,
        "new_constellation_count": 4,
    })
    asat_state["debris_clouds"] = []

    target, _ = _engine(seed=999_110)
    before = target.checkpoint()
    with pytest.raises(ValueError, match="asset_depleted result is impossible"):
        target.set_state(invalid)
    assert target.checkpoint() == before


def test_zero_time_order_cannot_be_completed_before_first_tick() -> None:
    completed, _ = _engine(seed=42, execute_at_s=0.0)
    completed.step()
    completed_space = copy.deepcopy(
        completed.get_state()["context"]["space_engine"],
    )

    target, _ = _engine(seed=999_110, execute_at_s=0.0)
    invalid = target.get_state()
    initial_space = invalid["context"]["space_engine"]
    initial_manager = initial_space["constellation_manager"]
    completed_space["constellation_manager"]["sim_time_s"] = 0.0
    completed_space["constellation_manager"]["satellites"] = copy.deepcopy(
        initial_manager["satellites"],
    )
    completed_space["constellation_manager"]["satellites"][TARGET_ID][
        "is_active"
    ] = False
    completed_space["gps_engine"] = copy.deepcopy(
        initial_space["gps_engine"],
    )
    completed_space["satcom_engine"] = copy.deepcopy(
        initial_space["satcom_engine"],
    )
    asat_state = completed_space["asat_engine"]
    result = asat_state["completed_orders"][ORDER_ID]
    result["execution_time_s"] = 0.0
    asat_state["assets"][ASSET_ID]["ready_at_s"] = 7200.0
    invalid["context"]["space_engine"] = completed_space
    before = target.checkpoint()

    with pytest.raises(ValueError, match="before the first simulation tick"):
        target.set_state(invalid)
    assert target.checkpoint() == before


def test_disabled_runtime_rejects_transplanted_completed_history() -> None:
    enabled, _ = _engine(seed=42, enable_asat=True)
    disabled, _ = _engine(seed=42, enable_asat=False)
    for _ in range(2):
        enabled.step()
        disabled.step()

    invalid = disabled.get_state()
    enabled_asat = enabled.get_state()["context"]["space_engine"][
        "asat_engine"
    ]
    disabled_asat = invalid["context"]["space_engine"]["asat_engine"]
    for field_name in (
        "assets",
        "pending_order_ids",
        "completed_orders",
        "debris_clouds",
    ):
        disabled_asat[field_name] = copy.deepcopy(
            enabled_asat[field_name],
        )
    before = disabled.checkpoint()

    with pytest.raises(ValueError, match="ASAT-disabled checkpoint"):
        disabled.set_state(invalid)
    assert disabled.checkpoint() == before


@pytest.mark.parametrize(
    ("corruption", "expected"),
    (
        ("missing_cloud", "do not preserve completed hit debris"),
        ("huge_count", "invalid debris count"),
    ),
)
def test_corrupt_debris_state_is_rejected_atomically(
    corruption: str,
    expected: str,
) -> None:
    source, _ = _engine(seed=42)
    source.step()
    source.step()
    invalid = source.get_state()
    clouds = invalid["context"]["space_engine"]["asat_engine"][
        "debris_clouds"
    ]
    if corruption == "missing_cloud":
        clouds.clear()
    else:
        clouds[0]["debris_count"] = 10**400

    target, _ = _engine(seed=999_110)
    before = target.checkpoint()
    with pytest.raises(ValueError, match=expected):
        target.set_state(invalid)
    assert target.checkpoint() == before


def test_same_seed_runs_preserve_order_outcome_state_and_space_rng() -> None:
    runs: list[dict[str, Any]] = []
    for _ in range(2):
        engine, recorder = _engine(seed=42)
        assert engine.step() is False
        assert engine.step() is False
        checkpoint = _decoded_checkpoint(engine)
        runs.append({
            "space": checkpoint["context"]["space_engine"],
            "space_rng": checkpoint["context"]["rng"]["streams"]["space"],
            "events": _phase110_events(recorder),
        })

    assert runs[1] == runs[0]
    engagement = runs[0]["events"][1]["data"]
    assert engagement["order_id"] == ORDER_ID
    assert engagement["target_satellite_id"] == TARGET_ID
    assert engagement["outcome"] == "hit"
    assert engagement["debris_generated"] == 488


def _hashseed_probe_result() -> dict[str, str]:
    engine, recorder = _engine(seed=42)
    engine.step()
    engine.step()
    checkpoint = _decoded_checkpoint(engine)
    payload = {
        "space": checkpoint["context"]["space_engine"],
        "space_rng": checkpoint["context"]["rng"]["streams"]["space"],
        "events": _phase110_events(recorder),
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "phase110_sha256": hashlib.sha256(encoded).hexdigest(),
    }


def test_phase110_output_is_independent_of_python_hash_seed() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    results: list[dict[str, str]] = []
    for hash_seed in ("1", "987654"):
        environment = os.environ.copy()
        environment["PYTHONHASHSEED"] = hash_seed
        environment["PHASE110_HASHSEED_PROBE"] = "1"
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).resolve())],
            cwd=repo_root,
            env=environment,
            capture_output=True,
            check=True,
            text=True,
        )
        result_line = next(
            line
            for line in completed.stdout.splitlines()
            if line.startswith(_HASHSEED_MARKER)
        )
        results.append(
            json.loads(result_line.removeprefix(_HASHSEED_MARKER)),
        )

    assert results[1] == results[0]


if __name__ == "__main__" and os.environ.get(
    "PHASE110_HASHSEED_PROBE",
) == "1":
    print(
        _HASHSEED_MARKER
        + json.dumps(_hashseed_probe_result(), sort_keys=True),
    )
