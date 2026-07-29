"""Production-path behavioral proofs for Phase 110 ASAT integration."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
from pydantic import ValidationError

from stochastic_warfare.simulation.engine import SimulationEngine
from stochastic_warfare.simulation.recorder import SimulationRecorder
from stochastic_warfare.simulation.scenario import (
    CampaignScenarioConfig,
    ScenarioLoader,
    load_campaign_scenario_config,
)


DATA_DIR = Path("data")
SCENARIO_PATH = DATA_DIR / "scenarios/space_asat_escalation/scenario.yaml"
TARGET_ID = "keyhole_optical_p0_s0"
ASSET_ID = "red_nudol_1"
ORDER_ID = "red_keyhole_strike_1"


def _load(
    *,
    seed: int = 42,
    enable_asat: bool | None = None,
):
    config = load_campaign_scenario_config(SCENARIO_PATH)
    if enable_asat is not None:
        payload = config.model_dump(mode="python")
        payload["space_config"]["enable_asat"] = enable_asat
        config = CampaignScenarioConfig.model_validate(payload)
    return ScenarioLoader(DATA_DIR).load(
        SCENARIO_PATH,
        seed=seed,
        scenario_config=config,
    )


def _run_two_ticks(ctx):
    recorder = SimulationRecorder(ctx.event_bus)
    recorder.start()
    engine = SimulationEngine(ctx, recorder=recorder)
    engine.step()
    events_after_first = list(recorder.events)
    engine.step()
    recorder.stop()
    return engine, recorder, events_after_first


def _asat_events(recorder: SimulationRecorder):
    return [
        event
        for event in recorder.events
        if event.event_type == "ASATEngagementEvent"
    ]


def test_shipped_scenario_loads_real_space_catalog_and_asset() -> None:
    ctx = _load()

    assert ctx.space_engine is not None
    manager = ctx.space_engine.constellation_manager
    assert [sat.satellite_id for sat in manager.all_satellites()] == [
        "keyhole_optical_p0_s0",
        "keyhole_optical_p0_s1",
        "keyhole_optical_p1_s0",
        "keyhole_optical_p1_s1",
    ]
    assert manager.active_count("keyhole_optical") == 4

    asat_state = ctx.space_engine.asat_engine.get_state()
    assert set(asat_state["assets"]) == {ASSET_ID}
    assert asat_state["assets"][ASSET_ID] == {
        "weapon_id": "nudol_asat",
        "side": "red",
        "rounds_initial": 1,
        "rounds_remaining": 1,
        "ready_at_s": 0.0,
    }
    assert asat_state["pending_order_ids"] == [ORDER_ID]
    assert asat_state["completed_orders"] == {}


def test_due_order_executes_once_and_disabled_control_preserves_target() -> None:
    enabled = _load(enable_asat=True)
    disabled = _load(enable_asat=False)

    enabled_target = enabled.space_engine.constellation_manager.get_satellite(
        TARGET_ID,
    )
    disabled_target = disabled.space_engine.constellation_manager.get_satellite(
        TARGET_ID,
    )
    assert enabled_target is not None and enabled_target.is_active
    assert disabled_target is not None and disabled_target.is_active

    disabled_space_rng_before = copy.deepcopy(
        disabled.rng_manager.get_state()["streams"]["space"],
    )
    _, enabled_recorder, enabled_first_tick = _run_two_ticks(enabled)
    _, disabled_recorder, disabled_first_tick = _run_two_ticks(disabled)

    assert not [
        event
        for event in enabled_first_tick
        if event.event_type == "ASATEngagementEvent"
    ]
    assert not [
        event
        for event in disabled_first_tick
        if event.event_type == "ASATEngagementEvent"
    ]

    enabled_events = _asat_events(enabled_recorder)
    assert len(enabled_events) == 1
    event = enabled_events[0]
    assert event.timestamp == enabled.clock.current_time
    assert event.data == {
        "order_id": ORDER_ID,
        "asset_id": ASSET_ID,
        "weapon_id": "nudol_asat",
        "attacker_side": "red",
        "target_satellite_id": TARGET_ID,
        "target_constellation_id": "keyhole_optical",
        "scheduled_time_s": 7200.0,
        "execution_time_s": 7200.0,
        "launched": True,
        "hit": True,
        "pk": pytest.approx(0.9996645373720975),
        "outcome": "hit",
        "reason": "",
        "debris_generated": 488,
        "rounds_remaining": 0,
        "previous_constellation_count": 4,
        "new_constellation_count": 3,
    }
    assert not enabled_target.is_active
    assert (
        enabled.space_engine.constellation_manager.active_count(
            "keyhole_optical",
        )
        == 3
    )
    enabled_state = enabled.space_engine.asat_engine.get_state()
    assert enabled_state["pending_order_ids"] == []
    assert list(enabled_state["completed_orders"]) == [ORDER_ID]
    assert enabled_state["assets"][ASSET_ID]["rounds_remaining"] == 0

    assert not _asat_events(disabled_recorder)
    assert disabled_target.is_active
    disabled_state = disabled.space_engine.asat_engine.get_state()
    assert disabled_state["pending_order_ids"] == [ORDER_ID]
    assert disabled_state["completed_orders"] == {}
    assert disabled_state["assets"][ASSET_ID]["rounds_remaining"] == 1
    assert (
        disabled.rng_manager.get_state()["streams"]["space"]
        == disabled_space_rng_before
    )

    # A third enabled tick cannot execute the completed order again.
    recorder = SimulationRecorder(enabled.event_bus)
    recorder.start()
    SimulationEngine(enabled, recorder=recorder).step()
    recorder.stop()
    assert not _asat_events(recorder)


def test_space_schema_rejects_unknown_fields_instead_of_ignoring_them() -> None:
    payload = load_campaign_scenario_config(
        DATA_DIR / "scenarios/test_campaign/scenario.yaml",
    ).model_dump(mode="python")
    payload["space_config"] = {
        "enable_space": True,
        "constellation_ids": ["keyhole_optical"],
        "enable_asat": False,
        "enable_assat": True,
    }

    with pytest.raises(ValidationError, match="enable_assat"):
        CampaignScenarioConfig.model_validate(payload)
