"""Checkpoint integrity and deterministic continuation for Phase 111 TOT."""

from __future__ import annotations

import copy
from dataclasses import replace
from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Any

import pytest

from stochastic_warfare.combat.indirect_fire import IndirectFireEngine
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.entities.base import UnitStatus
from stochastic_warfare.morale.state import MoraleState
from stochastic_warfare.simulation.engine import SimulationEngine
from stochastic_warfare.simulation.loadouts import RuntimeLoadouts
from stochastic_warfare.simulation.recorder import SimulationRecorder
from stochastic_warfare.simulation.scenario import (
    CampaignScenarioConfig,
    ScenarioLoader,
    load_campaign_scenario_config,
)
from stochastic_warfare.simulation.time_on_target import (
    TimeOnTargetMissionResolver,
)
from tests.conftest import make_versionless_legacy_morale_checkpoint


DATA_DIR = Path("data")
SCENARIO_PATH = DATA_DIR / "scenarios/time_on_target_validation/scenario.yaml"
MISSION_ID = "blue_validation_tot"
BATTERY_IDS = ("blue_m109a6_0000", "blue_m109a6_0001")
TARGET_ID = "red_hemtt_0000"
WEAPON_ID = "m284_155mm"
AMMO_ID = "m982_excalibur"
_TOT_EVENT_TYPES = {
    "AmmoExpendedEvent",
    "ArtilleryFireEvent",
    "TimeOnTargetMissionEvent",
    "UnitDestroyedEvent",
    "UnitDisabledEvent",
}


def _scenario_config(
    *,
    enabled: bool = True,
    empty: bool = False,
) -> CampaignScenarioConfig:
    config = load_campaign_scenario_config(SCENARIO_PATH)
    if enabled and not empty:
        return config
    payload = config.model_dump(mode="python")
    if empty:
        payload["indirect_fire"] = {
            "enable_time_on_target": False,
            "time_on_target_missions": [],
        }
    else:
        payload["indirect_fire"]["enable_time_on_target"] = False
    return CampaignScenarioConfig.model_validate(payload)


def _shared_attachment_config() -> CampaignScenarioConfig:
    payload = _scenario_config().model_dump(mode="python")
    first = payload["indirect_fire"]["time_on_target_missions"][0]
    second = copy.deepcopy(first)
    second["mission_id"] = "blue_follow_on_tot"
    second["impact_time_s"] = 180.0
    second["batteries"] = [copy.deepcopy(first["batteries"][0])]
    payload["indirect_fire"]["time_on_target_missions"].append(second)
    return CampaignScenarioConfig.model_validate(payload)


def _engine(
    *,
    seed: int = 42,
    enabled: bool = True,
    empty: bool = False,
    scenario_config: CampaignScenarioConfig | None = None,
) -> tuple[SimulationEngine, SimulationRecorder]:
    context = ScenarioLoader(DATA_DIR).load(
        SCENARIO_PATH,
        seed=seed,
        scenario_config=(
            scenario_config
            if scenario_config is not None
            else _scenario_config(enabled=enabled, empty=empty)
        ),
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


def _quantity_aware_engine(
    *,
    seed: int,
) -> tuple[SimulationEngine, SimulationRecorder]:
    payload = _scenario_config().model_dump(mode="python")
    first = payload["indirect_fire"]["time_on_target_missions"][0]
    first["batteries"] = [first["batteries"][0]]
    first["rounds_per_battery"] = 3
    second = copy.deepcopy(first)
    second["mission_id"] = "blue_quantity_follow_on"
    second["impact_time_s"] = 165.0
    payload["indirect_fire"]["time_on_target_missions"] = [first, second]
    payload["tick_resolution"] = {
        "strategic_s": 5.0,
        "operational_s": 5.0,
        "tactical_s": 5.0,
    }
    config = CampaignScenarioConfig.model_validate(payload)
    loader_payload = _scenario_config(empty=True).model_dump(mode="python")
    loader_payload["tick_resolution"] = copy.deepcopy(
        payload["tick_resolution"],
    )
    context = ScenarioLoader(DATA_DIR).load(
        SCENARIO_PATH,
        seed=seed,
        scenario_config=CampaignScenarioConfig.model_validate(loader_payload),
    )

    original = context.unit_weapons[BATTERY_IDS[0]][0]
    expanded = replace(
        original,
        source_system_count=4,
        target_system_count=1,
        runtime_system_multiplier=4,
    )
    context.unit_weapons[BATTERY_IDS[0]] = (
        expanded,
        *context.unit_weapons[BATTERY_IDS[0]][1:],
    )
    runtime_loadouts = RuntimeLoadouts(
        unit_weapons=context.unit_weapons,
        unit_sensor_attachments=context.unit_sensor_attachments,
        equipment_resolutions=context.equipment_resolutions,
    )
    missions = TimeOnTargetMissionResolver.resolve(
        config.indirect_fire,
        units_by_side=context.units_by_side,
        runtime_loadouts=runtime_loadouts,
        terrain=context.heightmap,
        duration_hours=config.duration_hours,
        tick_duration_seconds=config.tick_duration_seconds,
    )
    old_engine = context.indirect_fire_engine
    context.config = config
    context.indirect_fire_engine = IndirectFireEngine(
        old_engine._ballistics,
        old_engine._damage,
        context.event_bus,
        context.rng_manager.get_stream(ModuleId.COMBAT),
        config=old_engine._config,
        time_on_target_enabled=True,
        time_on_target_missions=missions,
        destruction_threshold=old_engine._destruction_threshold,
        disable_threshold=old_engine._disable_threshold,
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


def _advance(engine: SimulationEngine, ticks: int) -> None:
    for _ in range(ticks):
        assert engine.step() is False


def _decoded_checkpoint(engine: SimulationEngine) -> dict[str, Any]:
    return json.loads(engine.checkpoint().decode("utf-8"))


def _event_projection(engine: SimulationEngine) -> list[dict[str, Any]]:
    return [
        event
        for event in _decoded_checkpoint(engine)["recorder"]["events"]
        if event["event_type"] in _TOT_EVENT_TYPES
    ]


def _indirect_state(state: dict[str, Any]) -> dict[str, Any]:
    return state["context"]["indirect_fire_engine"]


def _resource_record(
    state: dict[str, Any],
    battery_id: str,
) -> dict[str, Any]:
    matches = [
        record
        for record in _indirect_state(state)["resource_observations"]
        if (
            record["unit_id"] == battery_id
            and record["source_equipment_index"] == 0
            and record["weapon_id"] == WEAPON_ID
        )
    ]
    assert len(matches) == 1
    return matches[0]


def _weapon_state(
    state: dict[str, Any],
    battery_id: str,
) -> dict[str, Any]:
    matches = [
        weapon
        for weapon in state["context"]["unit_weapon_states"][battery_id]
        if weapon["weapon_id"] == WEAPON_ID
    ]
    assert len(matches) == 1
    return matches[0]


def _saved_unit(
    state: dict[str, Any],
    unit_id: str,
) -> dict[str, Any]:
    matches = [
        unit
        for units in state["context"]["units_by_side"].values()
        for unit in units
        if unit["entity_id"] == unit_id
    ]
    assert len(matches) == 1
    return matches[0]


def _assert_atomic_rejection(
    source: SimulationEngine,
    invalid: dict[str, Any],
    *,
    expected: str,
    enabled: bool = True,
    empty: bool = False,
) -> None:
    fresh, _ = _engine(
        seed=999_111,
        enabled=enabled,
        empty=empty,
    )
    for candidate in (source, fresh):
        before = candidate.checkpoint()
        with pytest.raises(ValueError, match=expected):
            candidate.set_state(copy.deepcopy(invalid))
        assert candidate.checkpoint() == before


@pytest.mark.parametrize("checkpoint_tick", (11, 14, 25))
def test_fresh_runtime_continuation_is_exact_at_every_tot_lifecycle(
    checkpoint_tick: int,
) -> None:
    control, _ = _engine(seed=42)
    _advance(control, checkpoint_tick)
    saved = control.checkpoint()
    saved_decoded = json.loads(saved.decode("utf-8"))

    lifecycle = saved_decoded["context"]["indirect_fire_engine"]["missions"][0]
    if checkpoint_tick == 11:
        assert lifecycle["status"] == "pending"
        assert [
            battery["status"] for battery in lifecycle["batteries"]
        ] == ["pending", "pending"]
    elif checkpoint_tick == 14:
        assert lifecycle["status"] == "pending"
        assert [
            battery["status"] for battery in lifecycle["batteries"]
        ] == ["fired", "fired"]
    else:
        assert lifecycle["status"] == "completed"
        assert [
            battery["status"] for battery in lifecycle["batteries"]
        ] == ["fired", "fired"]

    resumed, _ = _engine(seed=999_111)
    resumed.restore(saved)
    assert _decoded_checkpoint(resumed) == saved_decoded

    _advance(control, 30 - checkpoint_tick)
    _advance(resumed, 30 - checkpoint_tick)
    assert _decoded_checkpoint(resumed) == _decoded_checkpoint(control)
    assert _event_projection(resumed) == _event_projection(control)

    projected = _event_projection(resumed)
    assert [event["event_type"] for event in projected] == [
        "AmmoExpendedEvent",
        "ArtilleryFireEvent",
        "AmmoExpendedEvent",
        "ArtilleryFireEvent",
        "UnitDisabledEvent",
        "TimeOnTargetMissionEvent",
    ]
    assert sum(
        event["data"]["quantity"]
        for event in projected
        if event["event_type"] == "AmmoExpendedEvent"
    ) == 2
    assert len([
        event
        for event in projected
        if event["event_type"] == "TimeOnTargetMissionEvent"
    ]) == 1
    assert len([
        event
        for event in projected
        if event["event_type"] in {
            "UnitDestroyedEvent",
            "UnitDisabledEvent",
        }
    ]) == 1


@pytest.mark.parametrize(
    ("fault", "expected_reason"),
    (
        ("depleted", "insufficient_ammunition"),
        ("cooldown", "weapon_cooldown"),
    ),
)
@pytest.mark.parametrize("checkpoint_tick", (14, 25))
def test_external_resource_rejection_checkpoint_is_exact(
    fault: str,
    expected_reason: str,
    checkpoint_tick: int,
) -> None:
    context = ScenarioLoader(DATA_DIR).load(
        SCENARIO_PATH,
        seed=42,
        scenario_config=_scenario_config(),
    )
    for battery_id in BATTERY_IDS:
        matches = [
            attachment
            for attachment in context.unit_weapons[battery_id]
            if (
                attachment.source_equipment_index == 0
                and attachment.weapon.weapon_id == WEAPON_ID
            )
        ]
        assert len(matches) == 1
        weapon = matches[0].weapon
        if fault == "depleted":
            available = weapon.ammo_state.available(AMMO_ID)
            assert weapon.fire(AMMO_ID, available)
            weapon.record_fire(10.0)
        else:
            assert fault == "cooldown"
            assert weapon.fire("m795_he", 1)
            weapon.record_fire(55.0)

    source_recorder = SimulationRecorder(context.event_bus)
    source_recorder.start()
    source = SimulationEngine(
        context,
        recorder=source_recorder,
        strict_mode=True,
    )
    _advance(source, checkpoint_tick)
    saved = source.checkpoint()
    lifecycle = _indirect_state(
        json.loads(saved.decode("utf-8")),
    )["missions"][0]
    assert [
        battery["status"]
        for battery in lifecycle["batteries"]
    ] == ["rejected", "rejected"]
    assert [
        battery["reason"]
        for battery in lifecycle["batteries"]
    ] == [expected_reason, expected_reason]

    resumed, _ = _engine(seed=999_111)
    resumed.restore(saved)
    assert resumed.checkpoint() == saved

    _advance(source, 30 - checkpoint_tick)
    _advance(resumed, 30 - checkpoint_tick)
    assert resumed.checkpoint() == source.checkpoint()
    terminal = [
        event
        for event in _event_projection(resumed)
        if event["event_type"] == "TimeOnTargetMissionEvent"
    ]
    assert len(terminal) == 1
    assert terminal[0]["data"]["outcome"] == "rejected"
    assert [
        battery["reason"]
        for battery in terminal[0]["data"]["battery_results"]
    ] == [expected_reason, expected_reason]


@pytest.mark.parametrize(
    ("enabled", "ticks"),
    (
        (True, 24),
        (False, 30),
    ),
    ids=("completed-plan", "disabled-populated-plan"),
)
def test_unreserved_external_fire_checkpoint_round_trip_is_exact(
    enabled: bool,
    ticks: int,
) -> None:
    source, _ = _engine(seed=42, enabled=enabled)
    _advance(source, ticks)
    attachment = source._ctx.unit_weapons[BATTERY_IDS[0]][0]
    assert attachment.source_equipment_index == 0
    assert attachment.weapon.weapon_id == WEAPON_ID
    assert not source._ctx.indirect_fire_engine.is_attachment_reserved(
        BATTERY_IDS[0],
        0,
        WEAPON_ID,
    )

    fire_time_s = source._ctx.clock.elapsed.total_seconds()
    assert attachment.weapon.fire("m795_he", 1)
    attachment.weapon.record_fire(fire_time_s)
    saved = source.checkpoint()

    resumed, _ = _engine(seed=999_111, enabled=enabled)
    resumed.restore(saved)
    assert resumed.checkpoint() == saved

    _advance(source, 1)
    _advance(resumed, 1)
    assert resumed.checkpoint() == source.checkpoint()


def test_reserved_external_fire_checkpoint_round_trip_is_exact() -> None:
    source, _ = _engine(seed=42)
    _advance(source, 11)
    attachment = source._ctx.unit_weapons[BATTERY_IDS[0]][0]
    assert source._ctx.clock.elapsed.total_seconds() == 55.0
    assert source._ctx.indirect_fire_engine.is_attachment_reserved(
        BATTERY_IDS[0],
        0,
        WEAPON_ID,
    )
    assert attachment.weapon.fire("m795_he", 1)
    attachment.weapon.record_fire(55.0)
    saved = source.checkpoint()

    resumed, _ = _engine(seed=999_111)
    resumed.restore(saved)
    assert resumed.checkpoint() == saved

    _advance(source, 14)
    _advance(resumed, 14)
    assert resumed.checkpoint() == source.checkpoint()
    assert _event_projection(resumed) == _event_projection(source)

    terminal = [
        event
        for event in _event_projection(resumed)
        if event["event_type"] == "TimeOnTargetMissionEvent"
    ]
    assert len(terminal) == 1
    assert terminal[0]["data"]["outcome"] == "partial"
    assert [
        result["reason"]
        for result in terminal[0]["data"]["battery_results"]
    ] == ["weapon_cooldown", ""]


def test_reserved_external_fire_before_impact_restores_after_release() -> None:
    source, _ = _engine(seed=42)
    _advance(source, 16)
    attachment = source._ctx.unit_weapons[BATTERY_IDS[0]][0]
    assert source._ctx.clock.elapsed.total_seconds() == 80.0
    assert source._ctx.indirect_fire_engine.is_attachment_reserved(
        BATTERY_IDS[0],
        0,
        WEAPON_ID,
    )
    assert attachment.weapon.can_fire_timed(80.0)
    assert attachment.weapon.fire("m795_he", 1)
    attachment.weapon.record_fire(80.0)

    reserved_checkpoint = source.checkpoint()
    resumed, _ = _engine(seed=999_111)
    resumed.restore(reserved_checkpoint)
    assert resumed.checkpoint() == reserved_checkpoint

    _advance(source, 9)
    _advance(resumed, 9)
    assert source._ctx.clock.elapsed.total_seconds() == 125.0
    assert resumed.checkpoint() == source.checkpoint()
    assert not resumed._ctx.indirect_fire_engine.is_attachment_reserved(
        BATTERY_IDS[0],
        0,
        WEAPON_ID,
    )

    terminal_checkpoint = resumed.checkpoint()
    fresh, _ = _engine(seed=111_999)
    fresh.restore(terminal_checkpoint)
    assert fresh.checkpoint() == terminal_checkpoint


def test_never_fired_sentinel_round_trip_is_exact() -> None:
    source, _ = _engine(seed=42)
    _advance(source, 1)
    state = source.get_state()
    for battery_id in BATTERY_IDS:
        assert _weapon_state(state, battery_id)["last_fire_time_s"] is None
        assert _resource_record(
            state,
            battery_id,
        )["last_fire_time_s"] is None

    resumed, _ = _engine(seed=999_111)
    resumed.set_state(copy.deepcopy(state))
    assert resumed.checkpoint() == source.checkpoint()


@pytest.mark.test_evidence("helper_assertion")
@pytest.mark.parametrize(
    ("authority", "invalid_value", "expected"),
    (
        (
            "resource",
            float("-inf"),
            "Resource last_fire_time_s observation is invalid",
        ),
        (
            "resource",
            float("nan"),
            "Resource last_fire_time_s observation is invalid",
        ),
        (
            "resource",
            -1.0,
            "Resource last_fire_time_s observation is invalid",
        ),
        (
            "weapon",
            float("-inf"),
            "Weapon last_fire_time_s must be null",
        ),
        (
            "weapon",
            float("nan"),
            "Weapon last_fire_time_s must be null",
        ),
        (
            "weapon",
            float("inf"),
            "Weapon last_fire_time_s must be null",
        ),
        (
            "weapon",
            -1.0,
            "Weapon last_fire_time_s must be null",
        ),
    ),
)
def test_corrupt_never_fired_boundary_is_rejected_atomically(
    authority: str,
    invalid_value: float | None,
    expected: str,
) -> None:
    source, _ = _engine(seed=42)
    _advance(source, 1)
    invalid = copy.deepcopy(source.get_state())
    if authority == "resource":
        _resource_record(
            invalid,
            BATTERY_IDS[0],
        )["last_fire_time_s"] = invalid_value
    else:
        _weapon_state(
            invalid,
            BATTERY_IDS[0],
        )["last_fire_time_s"] = invalid_value

    _assert_atomic_rejection(source, invalid, expected=expected)


def test_surrendered_terminal_target_cannot_regress_on_restore() -> None:
    source, _ = _engine(seed=42)
    _advance(source, 23)
    surrendered = source.get_state()
    _saved_unit(surrendered, TARGET_ID)["status"] = (
        UnitStatus.SURRENDERED.value
    )
    logical_time_s = source._ctx.clock.elapsed.total_seconds()
    morale_record = surrendered["context"]["morale_runtime"][
        "active_records"
    ][TARGET_ID]
    morale_record.update({
        "current_state": int(MoraleState.SURRENDERED),
        "last_transition_time_s": logical_time_s,
        "last_check_time_s": logical_time_s,
        "generation": morale_record["generation"] + 1,
    })
    source.set_state(surrendered)
    _advance(source, 1)

    valid = source.get_state()
    transition = _indirect_state(valid)["missions"][0]["target_transition"]
    assert transition["status_before"] == "SURRENDERED"
    assert transition["status_after"] == "SURRENDERED"

    resumed, _ = _engine(seed=999_111)
    resumed.set_state(copy.deepcopy(valid))
    assert resumed.checkpoint() == source.checkpoint()

    invalid = copy.deepcopy(valid)
    _saved_unit(invalid, TARGET_ID)["status"] = UnitStatus.ACTIVE.value
    invalid["context"]["morale_runtime"]["active_records"][TARGET_ID][
        "current_state"
    ] = int(MoraleState.STEADY)
    _assert_atomic_rejection(
        source,
        invalid,
        expected="Surrendered TOT target checkpoint regressed",
    )


def test_routing_terminal_target_may_rally_before_checkpoint() -> None:
    source, _ = _engine(seed=42)
    _advance(source, 23)
    target = next(
        unit
        for unit in source._ctx.units_by_side["red"]
        if unit.entity_id == TARGET_ID
    )
    object.__setattr__(target, "status", UnitStatus.ROUTING)
    _advance(source, 1)
    object.__setattr__(target, "status", UnitStatus.ACTIVE)

    saved = source.checkpoint()
    transition = _indirect_state(source.get_state())["missions"][0][
        "target_transition"
    ]
    assert transition["status_before"] == "ROUTING"
    assert transition["status_after"] == "ROUTING"

    resumed, _ = _engine(seed=999_111)
    resumed.restore(saved)
    assert resumed.checkpoint() == saved


def test_shared_attachment_rejects_nonadvancing_external_fire_history(
) -> None:
    source, _ = _engine(
        seed=42,
        scenario_config=_shared_attachment_config(),
    )
    _advance(source, 25)
    invalid = copy.deepcopy(source.get_state())
    indirect = _indirect_state(invalid)
    second_battery = indirect["missions"][1]["batteries"][0]
    weapon = _weapon_state(invalid, BATTERY_IDS[0])
    resource = _resource_record(invalid, BATTERY_IDS[0])

    second_battery["resource_before"]["ammunition_by_type"][AMMO_ID] -= 1
    second_battery["resource_before"]["total_rounds_fired"] += 1
    second_battery["resource_before"]["rounds_since_maintenance"] += 1
    for observation in (
        second_battery["resource_after"],
        resource,
    ):
        observation["ammunition_by_type"][AMMO_ID] -= 1
        observation["total_rounds_fired"] += 1
        observation["rounds_since_maintenance"] += 1
    weapon["ammo_state"]["rounds_by_type"][AMMO_ID] -= 1
    weapon["ammo_state"]["total_rounds_fired"] += 1
    weapon["rounds_since_maintenance"] += 1

    fresh, _ = _engine(
        seed=999_111,
        scenario_config=_shared_attachment_config(),
    )
    for candidate in (source, fresh):
        before = candidate.checkpoint()
        with pytest.raises(
            ValueError,
            match="External indirect-fire resource transition is impossible",
        ):
            candidate.set_state(copy.deepcopy(invalid))
        assert candidate.checkpoint() == before


def test_shared_attachment_rejects_bridge_before_observed_milestone(
) -> None:
    config = _shared_attachment_config()
    source, _ = _engine(seed=42, scenario_config=config)
    battery = next(
        unit
        for unit in source._ctx.units_by_side["blue"]
        if unit.entity_id == BATTERY_IDS[0]
    )
    object.__setattr__(battery, "status", UnitStatus.DISABLED)
    _advance(source, 12)
    object.__setattr__(battery, "status", UnitStatus.ACTIVE)
    _advance(source, 12)

    invalid = copy.deepcopy(source.get_state())
    second_battery = _indirect_state(invalid)["missions"][1][
        "batteries"
    ][0]
    for observation in (
        second_battery["resource_before"],
        second_battery["resource_after"],
        _resource_record(invalid, BATTERY_IDS[0]),
    ):
        observation["ammunition_by_type"]["m795_he"] -= 1
        observation["total_rounds_fired"] += 1
        observation["rounds_since_maintenance"] += 1
    second_battery["resource_before"]["last_fire_time_s"] = 50.0
    weapon = _weapon_state(invalid, BATTERY_IDS[0])
    weapon["ammo_state"]["rounds_by_type"]["m795_he"] -= 1
    weapon["ammo_state"]["total_rounds_fired"] += 1
    weapon["rounds_since_maintenance"] += 1

    fresh, _ = _engine(
        seed=999_111,
        scenario_config=_shared_attachment_config(),
    )
    for candidate in (source, fresh):
        before = candidate.checkpoint()
        with pytest.raises(
            ValueError,
            match="External indirect-fire resource transition is impossible",
        ):
            candidate.set_state(copy.deepcopy(invalid))
        assert candidate.checkpoint() == before


def test_shared_attachment_fresh_checkpoint_continuation_is_exact() -> None:
    config = _shared_attachment_config()
    source, _ = _engine(seed=42, scenario_config=config)
    _advance(source, 25)
    state = source.get_state()
    assert [
        mission["status"]
        for mission in _indirect_state(state)["missions"]
    ] == ["completed", "pending"]
    assert _indirect_state(state)["missions"][1]["batteries"][0][
        "status"
    ] == "fired"
    assert source._ctx.indirect_fire_engine.is_attachment_reserved(
        BATTERY_IDS[0],
        0,
        WEAPON_ID,
    )
    saved = source.checkpoint()

    resumed, _ = _engine(
        seed=999_111,
        scenario_config=_shared_attachment_config(),
    )
    resumed.restore(saved)
    assert resumed.checkpoint() == saved

    _advance(source, 12)
    _advance(resumed, 12)
    assert resumed.checkpoint() == source.checkpoint()
    assert _event_projection(resumed) == _event_projection(source)
    assert not resumed._ctx.indirect_fire_engine.is_attachment_reserved(
        BATTERY_IDS[0],
        0,
        WEAPON_ID,
    )
    assert [
        event["data"]["mission_id"]
        for event in _event_projection(resumed)
        if event["event_type"] == "TimeOnTargetMissionEvent"
    ] == [MISSION_ID, "blue_follow_on_tot"]


def test_quantity_aware_cooldown_is_enforced_by_whole_checkpoint() -> None:
    source, _ = _quantity_aware_engine(seed=42)
    _advance(source, 22)
    valid = source.checkpoint()
    state = _decoded_checkpoint(source)
    missions = _indirect_state(state)["missions"]
    assert [
        mission["batteries"][0]["status"]
        for mission in missions
    ] == ["fired", "fired"]
    assert [
        mission["batteries"][0]["rounds_fired"]
        for mission in missions
    ] == [3, 3]

    resumed, _ = _quantity_aware_engine(seed=999_111)
    resumed.restore(valid)
    assert resumed.checkpoint() == valid

    invalid = copy.deepcopy(state)
    second_battery = _indirect_state(invalid)["missions"][1][
        "batteries"
    ][0]
    for observation in (
        second_battery["resource_before"],
        second_battery["resource_after"],
        _resource_record(invalid, BATTERY_IDS[0]),
    ):
        observation["ammunition_by_type"]["m795_he"] -= 1
        observation["total_rounds_fired"] += 1
        observation["rounds_since_maintenance"] += 1
    second_battery["resource_before"]["last_fire_time_s"] = 90.0
    weapon = _weapon_state(invalid, BATTERY_IDS[0])
    weapon["ammo_state"]["rounds_by_type"]["m795_he"] -= 1
    weapon["ammo_state"]["total_rounds_fired"] += 1
    weapon["rounds_since_maintenance"] += 1

    for candidate in (source, resumed):
        before = candidate.checkpoint()
        with pytest.raises(
            ValueError,
            match="Fired indirect-fire lifecycle is inconsistent",
        ):
            candidate.set_state(copy.deepcopy(invalid))
        assert candidate.checkpoint() == before


@pytest.mark.parametrize(
    ("corruption", "expected"),
    (
        ("topology", "topology fingerprint"),
        ("resource_order", "topology or ordering"),
        ("lifecycle", "battery lifecycle"),
        ("lifecycle_bool_rounds", "rounds_fired is invalid"),
        ("lifecycle_int_processed_time", "processing chronology"),
        ("due_equal_pending", "milestone is already due"),
        ("combat_rng_mirror", "COMBAT RNG mirror"),
        ("combat_rng_bool_alias", "COMBAT RNG mirror"),
        (
            "pending_missing_fire_time",
            "External indirect-fire resource transition is impossible",
        ),
        ("fired_unspent", "resource ammunition increased"),
        (
            "completed_forged_history",
            "resource ammunition increased",
        ),
        (
            "trailing_future_fire",
            "External indirect-fire resource transition is impossible",
        ),
        ("fired_cooldown", "live-state delta"),
        ("fired_maintenance", "live-state delta"),
        ("terminal_target", "target checkpoint regressed"),
        (
            "terminal_bool_rounds",
            "terminal result does not match lifecycle",
        ),
    ),
)
def test_corrupt_tot_authorities_are_rejected_atomically(
    corruption: str,
    expected: str,
) -> None:
    ticks = {
        "due_equal_pending": 11,
        "lifecycle_bool_rounds": 25,
        "lifecycle_int_processed_time": 25,
        "pending_missing_fire_time": 11,
        "fired_unspent": 12,
        "completed_forged_history": 25,
        "trailing_future_fire": 25,
        "fired_cooldown": 12,
        "fired_maintenance": 12,
        "terminal_target": 25,
        "terminal_bool_rounds": 25,
    }.get(corruption, 0)
    source, _ = _engine(seed=42)
    _advance(source, ticks)
    invalid = copy.deepcopy(source.get_state())
    indirect = _indirect_state(invalid)
    mission = indirect["missions"][0]
    first_battery = mission["batteries"][0]

    if corruption == "topology":
        indirect["topology_fingerprint"] = "0" * 64
    elif corruption == "resource_order":
        indirect["resource_observations"].reverse()
    elif corruption == "lifecycle":
        first_battery["status"] = "phase111_corrupt"
    elif corruption == "lifecycle_bool_rounds":
        first_battery["rounds_fired"] = True
    elif corruption == "lifecycle_int_processed_time":
        processed_time = first_battery["processed_time_s"]
        assert type(processed_time) is float
        first_battery["processed_time_s"] = int(processed_time)
    elif corruption == "due_equal_pending":
        clock = invalid["context"]["clock"]
        current = datetime.fromisoformat(clock["current"])
        clock["current"] = (current + timedelta(seconds=5)).isoformat()
        clock["tick_count"] += 1
    elif corruption == "combat_rng_mirror":
        indirect["rng_state"]["state"]["state"] += 1
    elif corruption == "combat_rng_bool_alias":
        assert indirect["rng_state"]["has_uint32"] == 0
        indirect["rng_state"]["has_uint32"] = False
    elif corruption == "pending_missing_fire_time":
        weapon = _weapon_state(invalid, BATTERY_IDS[0])
        resource = _resource_record(invalid, BATTERY_IDS[0])
        weapon["ammo_state"]["rounds_by_type"][AMMO_ID] -= 1
        weapon["ammo_state"]["total_rounds_fired"] += 1
        weapon["rounds_since_maintenance"] += 1
        resource["ammunition_by_type"][AMMO_ID] -= 1
        resource["total_rounds_fired"] += 1
        resource["rounds_since_maintenance"] += 1
    elif corruption == "fired_unspent":
        pristine, _ = _engine(seed=42)
        pristine_state = pristine.get_state()
        invalid_weapon = _weapon_state(invalid, BATTERY_IDS[0])
        invalid_weapon.clear()
        invalid_weapon.update(
            copy.deepcopy(_weapon_state(pristine_state, BATTERY_IDS[0])),
        )
        invalid_resource = _resource_record(invalid, BATTERY_IDS[0])
        invalid_resource.clear()
        invalid_resource.update(
            copy.deepcopy(
                _resource_record(pristine_state, BATTERY_IDS[0]),
            ),
        )
    elif corruption == "completed_forged_history":
        weapon = _weapon_state(invalid, BATTERY_IDS[0])
        resource = _resource_record(invalid, BATTERY_IDS[0])
        weapon["ammo_state"]["rounds_by_type"][AMMO_ID] += 1
        resource["ammunition_by_type"][AMMO_ID] += 1
        first_battery["resource_before"]["ammunition_by_type"][
            AMMO_ID
        ] += 1
        first_battery["resource_after"]["ammunition_by_type"][
            AMMO_ID
        ] += 1
    elif corruption == "trailing_future_fire":
        weapon = _weapon_state(invalid, BATTERY_IDS[0])
        resource = _resource_record(invalid, BATTERY_IDS[0])
        fire_time_s = 130.0
        weapon["ammo_state"]["rounds_by_type"]["m795_he"] -= 1
        weapon["ammo_state"]["total_rounds_fired"] += 1
        weapon["rounds_since_maintenance"] += 1
        weapon["last_fire_time_s"] = fire_time_s
        resource["ammunition_by_type"]["m795_he"] -= 1
        resource["total_rounds_fired"] += 1
        resource["rounds_since_maintenance"] += 1
        resource["last_fire_time_s"] = fire_time_s
    elif corruption == "fired_cooldown":
        _weapon_state(
            invalid,
            BATTERY_IDS[0],
        )["last_fire_time_s"] = 55.0
        _resource_record(
            invalid,
            BATTERY_IDS[0],
        )["last_fire_time_s"] = 55.0
        first_battery["resource_after"]["last_fire_time_s"] = 55.0
    elif corruption == "fired_maintenance":
        _weapon_state(
            invalid,
            BATTERY_IDS[0],
        )["rounds_since_maintenance"] = 0
        _resource_record(
            invalid,
            BATTERY_IDS[0],
        )["rounds_since_maintenance"] = 0
        first_battery["resource_after"]["rounds_since_maintenance"] = 0
    elif corruption == "terminal_target":
        _saved_unit(invalid, TARGET_ID)["status"] = UnitStatus.ACTIVE.value
    else:
        assert corruption == "terminal_bool_rounds"
        mission["terminal_result"]["battery_results"][0][
            "rounds_fired"
        ] = True

    _assert_atomic_rejection(source, invalid, expected=expected)


@pytest.mark.parametrize(
    "invalid_version",
    (113, 117, True, None),
    ids=("version-113", "future", "boolean", "null"),
)
def test_checkpoint_version_118_is_exact_and_atomic(
    invalid_version: int | bool | None,
) -> None:
    source, _ = _engine(seed=42)
    invalid = copy.deepcopy(source.get_state())
    assert invalid["checkpoint_version"] == 118
    invalid["checkpoint_version"] = invalid_version

    _assert_atomic_rejection(
        source,
        invalid,
        expected="Unsupported checkpoint version",
    )


@pytest.mark.test_evidence("helper_assertion")
@pytest.mark.parametrize("enabled", (True, False))
def test_versionless_checkpoint_rejects_every_declared_tot_plan(
    enabled: bool,
) -> None:
    source, _ = _engine(seed=42, enabled=enabled)
    invalid = make_versionless_legacy_morale_checkpoint(
        source.get_state(),
    )

    _assert_atomic_rejection(
        source,
        invalid,
        expected="declared time-on-target missions",
        enabled=enabled,
    )


def test_unconfigured_combat_rng_bool_alias_is_rejected_atomically() -> None:
    source, _ = _engine(seed=42, empty=True)
    invalid = copy.deepcopy(source.get_state())
    indirect = _indirect_state(invalid)
    assert set(indirect) == {"rng_state"}
    assert indirect["rng_state"]["has_uint32"] == 0
    indirect["rng_state"]["has_uint32"] = False

    _assert_atomic_rejection(
        source,
        invalid,
        expected="COMBAT RNG mirror",
        empty=True,
    )


@pytest.mark.test_evidence("helper_assertion")
def test_started_versionless_checkpoint_without_declared_plan_rejects_atomically(
) -> None:
    source, _ = _engine(seed=42, empty=True)
    _advance(source, 3)
    versionless = make_versionless_legacy_morale_checkpoint(
        source.get_state(),
    )

    _assert_atomic_rejection(
        source,
        versionless,
        expected="only at pristine tick 0",
        empty=True,
    )


def test_disabled_populated_plan_restores_dormant_after_authored_times(
) -> None:
    control, _ = _engine(seed=42, enabled=False)
    _advance(control, 30)
    checkpoint = control.checkpoint()

    resumed, _ = _engine(seed=999_111, enabled=False)
    resumed.restore(checkpoint)
    assert resumed.checkpoint() == checkpoint
    indirect = _decoded_checkpoint(resumed)["context"][
        "indirect_fire_engine"
    ]
    assert indirect["enabled"] is False
    assert indirect["missions"] == [
        {
            "mission_id": MISSION_ID,
            "status": "dormant",
            "batteries": [
                {
                    "battery_id": battery_id,
                    "status": "dormant",
                    "reason": "",
                    "processed_time_s": None,
                    "actual_fire_position": None,
                    "rounds_fired": 0,
                    "impacts": [],
                    "resource_before": None,
                    "resource_after": None,
                    "precondition": None,
                }
                for battery_id in BATTERY_IDS
            ],
            "terminal_result": None,
            "target_transition": None,
        },
    ]
    assert _event_projection(resumed) == []

    _advance(control, 1)
    _advance(resumed, 1)
    assert _decoded_checkpoint(resumed) == _decoded_checkpoint(control)
