"""Production-path behavioral proofs for Phase 111 time-on-target execution."""

from __future__ import annotations

import copy
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from stochastic_warfare.combat.events import (
    AmmoExpendedEvent,
    ArtilleryFireEvent,
    TimeOnTargetMissionEvent,
)
from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.base import UnitStatus
from stochastic_warfare.entities.events import UnitDisabledEvent
from stochastic_warfare.simulation.battle import (
    BattleContext,
    BattleManager,
    _apply_indirect_fire_result,
)
from stochastic_warfare.simulation.engine import SimulationEngine
from stochastic_warfare.simulation.recorder import SimulationRecorder
from stochastic_warfare.simulation.scenario import (
    CampaignScenarioConfig,
    ScenarioLoader,
    load_campaign_scenario_config,
)


DATA_DIR = Path("data")
SCENARIO_PATH = DATA_DIR / "scenarios/time_on_target_validation/scenario.yaml"
MISSION_ID = "blue_validation_tot"
BATTERY_IDS = ("blue_m109a6_0000", "blue_m109a6_0001")
TARGET_ID = "red_hemtt_0000"


def _unit(ctx, unit_id: str):
    return next(unit for unit in ctx.all_units() if unit.entity_id == unit_id)


def _planned_attachment(ctx, battery_id: str):
    matches = [
        attachment
        for attachment in ctx.unit_weapons[battery_id]
        if (
            attachment.source_equipment_index == 0
            and attachment.weapon.weapon_id == "m284_155mm"
            and any(
                ammo.ammo_id == "m982_excalibur"
                for ammo in attachment.ammunition
            )
        )
    ]
    assert len(matches) == 1
    return matches[0]


def _m982_state(ctx, battery_id: str) -> tuple[int, int, float]:
    weapon = _planned_attachment(ctx, battery_id).weapon
    state = weapon.get_state()
    return (
        weapon.ammo_state.available("m982_excalibur"),
        state["rounds_since_maintenance"],
        state["last_fire_time_s"],
    )


def _load(*, seed: int = 42, enabled: bool | None = None, empty: bool = False):
    config = load_campaign_scenario_config(SCENARIO_PATH)
    if enabled is not None or empty:
        payload = config.model_dump(mode="python")
        if enabled is not None:
            payload["indirect_fire"]["enable_time_on_target"] = enabled
        if empty:
            payload["indirect_fire"] = {
                "enable_time_on_target": False,
                "time_on_target_missions": [],
            }
        config = CampaignScenarioConfig.model_validate(payload)
    return ScenarioLoader(DATA_DIR).load(
        SCENARIO_PATH,
        seed=seed,
        scenario_config=config,
    )


def _shared_attachment_config() -> CampaignScenarioConfig:
    payload = load_campaign_scenario_config(SCENARIO_PATH).model_dump(
        mode="python",
    )
    first = payload["indirect_fire"]["time_on_target_missions"][0]
    second = copy.deepcopy(first)
    second["mission_id"] = "blue_follow_on_tot"
    second["impact_time_s"] = 180.0
    second["batteries"] = [copy.deepcopy(first["batteries"][0])]
    payload["indirect_fire"]["time_on_target_missions"].append(second)
    return CampaignScenarioConfig.model_validate(payload)


def _run_ticks(ctx, count: int) -> tuple[SimulationEngine, SimulationRecorder]:
    recorder = SimulationRecorder(ctx.event_bus)
    recorder.start()
    engine = SimulationEngine(ctx, recorder=recorder)
    for _ in range(count):
        assert engine.step() is False
    return engine, recorder


def test_real_scenario_executes_two_battery_mission_once(caplog) -> None:
    caplog.set_level(logging.ERROR)
    ctx = ScenarioLoader(DATA_DIR).load(SCENARIO_PATH, seed=42)
    before = {
        battery_id: _m982_state(ctx, battery_id)
        for battery_id in BATTERY_IDS
    }
    target = _unit(ctx, TARGET_ID)
    assert target.status is UnitStatus.ACTIVE

    def broken_observer(event) -> None:
        raise RuntimeError(f"deliberate {type(event).__name__} failure")

    for event_type in (
        AmmoExpendedEvent,
        ArtilleryFireEvent,
        UnitDisabledEvent,
        TimeOnTargetMissionEvent,
    ):
        ctx.event_bus.subscribe(event_type, broken_observer)

    recorder = SimulationRecorder(ctx.event_bus)
    recorder.start()
    engine = SimulationEngine(ctx, recorder=recorder)
    for _ in range(25):
        assert engine.step() is False

    terminal = [
        event
        for event in recorder.events
        if event.event_type == "TimeOnTargetMissionEvent"
    ]
    assert len(terminal) == 1
    assert terminal[0].data == {
        "mission_id": MISSION_ID,
        "attacker_side": "blue",
        "target_unit_id": TARGET_ID,
        "target_position": (22000.0, 10000.0, 0.0),
        "scheduled_impact_time_s": 120.0,
        "processing_time_s": 120.0,
        "battery_results": (
            {
                "battery_id": BATTERY_IDS[0],
                "source_equipment_index": 0,
                "runtime_system_multiplier": 1,
                "weapon_id": "m284_155mm",
                "ammo_id": "m982_excalibur",
                "planned_fire_position": (1000.0, 9000.0, 0.0),
                "actual_fire_position": (1000.0, 9000.0, 0.0),
                "scheduled_fire_time_s": 60.0,
                "predicted_time_of_flight_s": 60.0,
                "processing_time_s": 60.0,
                "status": "fired",
                "reason": "",
                "rounds_fired": 1,
                "generated_impact_count": 1,
            },
            {
                "battery_id": BATTERY_IDS[1],
                "source_equipment_index": 0,
                "runtime_system_multiplier": 1,
                "weapon_id": "m284_155mm",
                "ammo_id": "m982_excalibur",
                "planned_fire_position": (4000.0, 11000.0, 0.0),
                "actual_fire_position": (4000.0, 11000.0, 0.0),
                "scheduled_fire_time_s": 65.0,
                "predicted_time_of_flight_s": 55.0,
                "processing_time_s": 65.0,
                "status": "fired",
                "reason": "",
                "rounds_fired": 1,
                "generated_impact_count": 1,
            },
        ),
        "total_generated_impacts": 2,
        "near_target_impacts": 2,
        "outcome": "completed",
        "target_effect": "disabled",
        "target_status_before": "ACTIVE",
        "target_status_after": "DISABLED",
    }
    assert target.status is UnitStatus.DISABLED

    relevant_events = [
        event
        for event in recorder.events
        if event.event_type in {
            "AmmoExpendedEvent",
            "ArtilleryFireEvent",
            "UnitDisabledEvent",
            "TimeOnTargetMissionEvent",
        }
    ]
    assert [event.event_type for event in relevant_events] == [
        "AmmoExpendedEvent",
        "ArtilleryFireEvent",
        "AmmoExpendedEvent",
        "ArtilleryFireEvent",
        "UnitDisabledEvent",
        "TimeOnTargetMissionEvent",
    ]
    disabled = next(
        event
        for event in relevant_events
        if event.event_type == "UnitDisabledEvent"
    )
    assert disabled.data == {
        "unit_id": TARGET_ID,
        "cause": "time_on_target",
        "side": "red",
        "weapon_id": "",
    }
    fire_events = [
        event
        for event in relevant_events
        if event.event_type == "ArtilleryFireEvent"
    ]
    assert [event.data["battery_id"] for event in fire_events] == [
        BATTERY_IDS[0],
        BATTERY_IDS[1],
    ]
    assert [
        event.data["round_count"]
        for event in fire_events
    ] == [1, 1]

    assert {
        battery_id: _m982_state(ctx, battery_id)
        for battery_id in BATTERY_IDS
    } == {
        BATTERY_IDS[0]: (before[BATTERY_IDS[0]][0] - 1, 1, 60.0),
        BATTERY_IDS[1]: (before[BATTERY_IDS[1]][0] - 1, 1, 65.0),
    }

    completed_snapshot = {
        "weapons": {
            battery_id: copy.deepcopy(
                _planned_attachment(ctx, battery_id).weapon.get_state(),
            )
            for battery_id in BATTERY_IDS
        },
        "target_status": target.status,
        "combat_rng": copy.deepcopy(
            ctx.rng_manager.get_state()["streams"]["combat"],
        ),
        "indirect_fire": copy.deepcopy(
            ctx.indirect_fire_engine.get_state(),
        ),
    }
    completed_event_projection = [
        (event.event_type, event.data)
        for event in recorder.events
        if event.event_type in {
            "AmmoExpendedEvent",
            "ArtilleryFireEvent",
            "UnitDisabledEvent",
            "TimeOnTargetMissionEvent",
        }
    ]
    for _ in range(5):
        assert engine.step() is False
    recorder.stop()
    assert [
        (event.event_type, event.data)
        for event in recorder.events
        if event.event_type in {
            "AmmoExpendedEvent",
            "ArtilleryFireEvent",
            "UnitDisabledEvent",
            "TimeOnTargetMissionEvent",
        }
    ] == completed_event_projection
    assert len([
        event
        for event in recorder.events
        if event.event_type == "TimeOnTargetMissionEvent"
    ]) == 1
    assert {
        "weapons": {
            battery_id: _planned_attachment(
                ctx,
                battery_id,
            ).weapon.get_state()
            for battery_id in BATTERY_IDS
        },
        "target_status": target.status,
        "combat_rng": ctx.rng_manager.get_state()["streams"]["combat"],
        "indirect_fire": ctx.indirect_fire_engine.get_state(),
    } == completed_snapshot
    for event_type in (
        "AmmoExpendedEvent",
        "ArtilleryFireEvent",
        "UnitDisabledEvent",
        "TimeOnTargetMissionEvent",
    ):
        assert event_type in caplog.text


def test_disabled_populated_and_empty_controls_are_inert() -> None:
    disabled = _load(enabled=False)
    empty = _load(empty=True)
    disabled_before = {
        battery_id: copy.deepcopy(
            _planned_attachment(disabled, battery_id).weapon.get_state(),
        )
        for battery_id in BATTERY_IDS
    }
    empty_before = {
        battery_id: copy.deepcopy(
            _planned_attachment(empty, battery_id).weapon.get_state(),
        )
        for battery_id in BATTERY_IDS
    }
    disabled_rng_before = copy.deepcopy(
        disabled.rng_manager.get_state()["streams"]["combat"],
    )
    empty_rng_before = copy.deepcopy(
        empty.rng_manager.get_state()["streams"]["combat"],
    )

    _, disabled_recorder = _run_ticks(disabled, 30)
    _, empty_recorder = _run_ticks(empty, 30)
    disabled_recorder.stop()
    empty_recorder.stop()

    assert not [
        event
        for event in disabled_recorder.events + empty_recorder.events
        if event.event_type in {
            "AmmoExpendedEvent",
            "ArtilleryFireEvent",
            "TimeOnTargetMissionEvent",
        }
    ]
    assert _unit(disabled, TARGET_ID).status is UnitStatus.ACTIVE
    assert _unit(empty, TARGET_ID).status is UnitStatus.ACTIVE
    assert {
        battery_id: _planned_attachment(
            disabled,
            battery_id,
        ).weapon.get_state()
        for battery_id in BATTERY_IDS
    } == disabled_before
    assert {
        battery_id: _planned_attachment(
            empty,
            battery_id,
        ).weapon.get_state()
        for battery_id in BATTERY_IDS
    } == empty_before
    assert (
        disabled.rng_manager.get_state()["streams"]["combat"]
        == disabled_rng_before
        == empty.rng_manager.get_state()["streams"]["combat"]
        == empty_rng_before
    )
    assert all(
        mission["status"] == "dormant"
        for mission in disabled.indirect_fire_engine.get_state()["missions"]
    )
    assert empty.indirect_fire_engine.get_state() == {
        "rng_state": empty_rng_before,
    }
    assert all(
        not disabled.indirect_fire_engine.is_attachment_reserved(
            battery_id,
            0,
            "m284_155mm",
        )
        for battery_id in BATTERY_IDS
    )


def test_same_seed_fresh_runs_match_complete_state_and_ordered_events() -> None:
    first = _load(seed=42)
    second = _load(seed=42)
    first_engine, first_recorder = _run_ticks(first, 30)
    second_engine, second_recorder = _run_ticks(second, 30)

    assert first_engine.checkpoint() == second_engine.checkpoint()
    assert [
        (event.event_type, event.data)
        for event in first_recorder.events
    ] == [
        (event.event_type, event.data)
        for event in second_recorder.events
    ]
    first_recorder.stop()
    second_recorder.stop()


def test_target_movement_and_inactive_status_are_resolved_at_impact() -> None:
    moved = _load()
    moved_engine, moved_recorder = _run_ticks(moved, 14)
    moved_target = _unit(moved, TARGET_ID)
    object.__setattr__(
        moved_target,
        "position",
        Position(10000.0, 10000.0, 0.0),
    )
    for _ in range(11):
        assert moved_engine.step() is False
    moved_recorder.stop()
    moved_terminal = next(
        event
        for event in moved_recorder.events
        if event.event_type == "TimeOnTargetMissionEvent"
    )
    assert moved_terminal.data["near_target_impacts"] == 0
    assert moved_terminal.data["target_effect"] == "missed"
    assert moved_target.status is UnitStatus.ACTIVE

    inactive = _load()
    inactive_engine, inactive_recorder = _run_ticks(inactive, 14)
    inactive_target = _unit(inactive, TARGET_ID)
    object.__setattr__(
        inactive_target,
        "status",
        UnitStatus.SURRENDERED,
    )
    for _ in range(11):
        assert inactive_engine.step() is False
    inactive_recorder.stop()
    inactive_terminal = next(
        event
        for event in inactive_recorder.events
        if event.event_type == "TimeOnTargetMissionEvent"
    )
    assert inactive_terminal.data["target_effect"] == "target_inactive"
    assert inactive_terminal.data["target_status_before"] == "SURRENDERED"
    assert inactive_terminal.data["target_status_after"] == "SURRENDERED"
    assert inactive_target.status is UnitStatus.SURRENDERED


def test_mixed_battery_result_is_partial_and_commits_only_real_fire() -> None:
    ctx = _load()
    rejected = _unit(ctx, BATTERY_IDS[0])
    object.__setattr__(rejected, "status", UnitStatus.DISABLED)
    first_before = _m982_state(ctx, BATTERY_IDS[0])
    second_before = _m982_state(ctx, BATTERY_IDS[1])

    _engine, recorder = _run_ticks(ctx, 25)
    recorder.stop()
    terminal = next(
        event
        for event in recorder.events
        if event.event_type == "TimeOnTargetMissionEvent"
    )

    assert terminal.data["outcome"] == "partial"
    assert [
        battery["status"]
        for battery in terminal.data["battery_results"]
    ] == ["rejected", "fired"]
    assert [
        battery["reason"]
        for battery in terminal.data["battery_results"]
    ] == ["battery_inactive", ""]
    assert terminal.data["total_generated_impacts"] == 1
    assert _m982_state(ctx, BATTERY_IDS[0]) == first_before
    assert _m982_state(ctx, BATTERY_IDS[1]) == (
        second_before[0] - 1,
        1,
        65.0,
    )


def test_ordinary_indirect_assessment_keeps_cumulative_terrain_inputs() -> None:
    ctx = _load(empty=True)
    target = _unit(ctx, TARGET_ID)
    result = SimpleNamespace(
        impacts=[
            SimpleNamespace(
                position=Position(22010.0, 10000.0, 0.0),
                ammo_id="m982_excalibur",
            ),
            SimpleNamespace(
                position=Position(22020.0, 10000.0, 0.0),
                ammo_id="m982_excalibur",
            ),
        ],
    )
    tracker = {TARGET_ID: 1}
    pending: list[tuple] = []

    _apply_indirect_fire_result(
        result,
        target,
        pending,
        destruction_threshold=0.5,
        disable_threshold=0.3,
        cumulative_tracker=tracker,
        terrain_modifier=0.5,
        lethal_radius_m=50.0,
        casualty_per_hit=0.2,
        weapon_id="m284_155mm",
    )

    assert tracker == {TARGET_ID: 3}
    assert pending == [
        (target, UnitStatus.DISABLED, "m284_155mm"),
    ]
    assert target.status is UnitStatus.ACTIVE


def test_battle_reserves_only_exact_attachment_and_releases_after_impact() -> None:
    reserved = _load()
    attacker = _unit(reserved, BATTERY_IDS[0])
    target = _unit(reserved, TARGET_ID)
    object.__setattr__(target, "position", Position(1500.0, 9000.0, 0.0))
    reserved.units_by_side = {"blue": [attacker], "red": [target]}
    recorder = SimulationRecorder(reserved.event_bus)
    recorder.start()
    battle = BattleContext(
        battle_id="phase111-reserved",
        start_tick=0,
        start_time=reserved.clock.current_time,
        involved_sides=["blue", "red"],
        unit_ids={attacker.entity_id, target.entity_id},
    )
    BattleManager(reserved.event_bus).execute_tick(reserved, battle, 5.0)
    recorder.stop()

    assert [
        event.data["weapon_id"]
        for event in recorder.events
        if event.event_type == "EngagementEvent"
    ] == ["m2hb_50cal"]
    assert not [
        event
        for event in recorder.events
        if event.event_type == "ArtilleryFireEvent"
    ]
    assert reserved.indirect_fire_engine.is_attachment_reserved(
        attacker.entity_id,
        0,
        "m284_155mm",
    )
    assert not reserved.indirect_fire_engine.is_attachment_reserved(
        attacker.entity_id,
        1,
        "m2hb_50cal",
    )

    completed = _load()
    _engine, completion_recorder = _run_ticks(completed, 25)
    completion_recorder.stop()
    completed_target = _unit(completed, TARGET_ID)
    completed_attacker = _unit(completed, BATTERY_IDS[0])
    object.__setattr__(completed_target, "status", UnitStatus.ACTIVE)
    object.__setattr__(
        completed_target,
        "position",
        Position(5000.0, 9000.0, 0.0),
    )
    completed.units_by_side = {
        "blue": [completed_attacker],
        "red": [completed_target],
    }
    release_recorder = SimulationRecorder(completed.event_bus)
    release_recorder.start()
    release_battle = BattleContext(
        battle_id="phase111-released",
        start_tick=completed.clock.tick_count,
        start_time=completed.clock.current_time,
        involved_sides=["blue", "red"],
        unit_ids={
            completed_attacker.entity_id,
            completed_target.entity_id,
        },
    )
    BattleManager(completed.event_bus).execute_tick(
        completed,
        release_battle,
        5.0,
    )
    release_recorder.stop()

    assert not completed.indirect_fire_engine.is_attachment_reserved(
        completed_attacker.entity_id,
        0,
        "m284_155mm",
    )
    assert [
        event.data["ammo_type"]
        for event in release_recorder.events
        if event.event_type == "ArtilleryFireEvent"
    ] == ["m795_he"]


def test_shared_attachment_releases_only_after_every_mission_completes() -> None:
    ctx = ScenarioLoader(DATA_DIR).load(
        SCENARIO_PATH,
        seed=42,
        scenario_config=_shared_attachment_config(),
    )
    engine, recorder = _run_ticks(ctx, 25)

    state_after_first_impact = ctx.indirect_fire_engine.get_state()
    assert [
        mission["status"]
        for mission in state_after_first_impact["missions"]
    ] == ["completed", "pending"]
    assert state_after_first_impact["missions"][1]["batteries"][0][
        "status"
    ] == "fired"
    assert ctx.indirect_fire_engine.is_attachment_reserved(
        BATTERY_IDS[0],
        0,
        "m284_155mm",
    )
    terminal_timestamp = next(
        event.timestamp
        for event in recorder.events
        if event.event_type == "TimeOnTargetMissionEvent"
        and event.data["mission_id"] == MISSION_ID
    )
    simultaneous = [
        event
        for event in recorder.events
        if event.timestamp == terminal_timestamp
        and event.event_type in {
            "AmmoExpendedEvent",
            "ArtilleryFireEvent",
            "UnitDisabledEvent",
            "TimeOnTargetMissionEvent",
        }
    ]
    assert [
        (event.event_type, event.data)
        for event in simultaneous
    ] == [
        (
            "AmmoExpendedEvent",
            {
                "unit_id": BATTERY_IDS[0],
                "ammo_type": "m982_excalibur",
                "quantity": 1,
            },
        ),
        (
            "ArtilleryFireEvent",
            {
                "battery_id": BATTERY_IDS[0],
                "target_pos": (22000.0, 10000.0, 0.0),
                "ammo_type": "m982_excalibur",
                "round_count": 1,
            },
        ),
        (
            "UnitDisabledEvent",
            {
                "unit_id": TARGET_ID,
                "cause": "time_on_target",
                "side": "red",
                "weapon_id": "",
            },
        ),
        (
            "TimeOnTargetMissionEvent",
            state_after_first_impact["missions"][0]["terminal_result"],
        ),
    ]

    for _ in range(12):
        assert engine.step() is False
    recorder.stop()

    assert [
        mission["status"]
        for mission in ctx.indirect_fire_engine.get_state()["missions"]
    ] == ["completed", "completed"]
    assert not ctx.indirect_fire_engine.is_attachment_reserved(
        BATTERY_IDS[0],
        0,
        "m284_155mm",
    )
    assert [
        event.data["mission_id"]
        for event in recorder.events
        if event.event_type == "TimeOnTargetMissionEvent"
    ] == [MISSION_ID, "blue_follow_on_tot"]


@pytest.mark.parametrize(
    ("fault", "expected_reason"),
    [
        ("inactive", "battery_inactive"),
        ("moving", "battery_moving"),
        ("displaced", "battery_displaced"),
        ("inoperable", "weapon_inoperable"),
        ("depleted", "insufficient_ammunition"),
        ("cooldown", "weapon_cooldown"),
        ("precedence", "battery_inactive"),
    ],
)
def test_runtime_rejections_are_terminal_ordered_and_rng_free(
    fault: str,
    expected_reason: str,
) -> None:
    ctx = _load()
    for battery_id in BATTERY_IDS:
        unit = _unit(ctx, battery_id)
        weapon = _planned_attachment(ctx, battery_id).weapon
        if fault in {"depleted", "precedence"}:
            available = weapon.ammo_state.available("m982_excalibur")
            assert weapon.fire("m982_excalibur", available)
            weapon.record_fire(10.0)
        if fault in {"cooldown", "precedence"}:
            assert weapon.fire("m795_he", 1)
            weapon.record_fire(55.0)
        if fault in {"inactive", "precedence"}:
            object.__setattr__(unit, "status", UnitStatus.DISABLED)
        if fault in {"moving", "precedence"}:
            object.__setattr__(unit, "speed", 1.0)
        if fault in {"displaced", "precedence"}:
            object.__setattr__(
                unit,
                "position",
                Position(
                    unit.position.easting + 1.0,
                    unit.position.northing,
                    unit.position.altitude,
                ),
            )
        if fault in {"inoperable", "precedence"}:
            weapon.equipment.operational = False

    resources_before = {
        battery_id: copy.deepcopy(
            _planned_attachment(ctx, battery_id).weapon.get_state(),
        )
        for battery_id in BATTERY_IDS
    }
    rng_before = copy.deepcopy(
        ctx.rng_manager.get_state()["streams"]["combat"],
    )
    _, recorder = _run_ticks(ctx, 25)
    recorder.stop()

    terminal = [
        event
        for event in recorder.events
        if event.event_type == "TimeOnTargetMissionEvent"
    ]
    assert len(terminal) == 1
    assert terminal[0].data["outcome"] == "rejected"
    assert terminal[0].data["target_effect"] == "missed"
    assert [
        result["reason"]
        for result in terminal[0].data["battery_results"]
    ] == [expected_reason, expected_reason]
    assert [
        result["status"]
        for result in terminal[0].data["battery_results"]
    ] == ["rejected", "rejected"]
    assert not [
        event
        for event in recorder.events
        if event.event_type in {
            "AmmoExpendedEvent",
            "ArtilleryFireEvent",
            "UnitDisabledEvent",
        }
    ]
    assert _unit(ctx, TARGET_ID).status is UnitStatus.ACTIVE
    assert {
        battery_id: _planned_attachment(
            ctx,
            battery_id,
        ).weapon.get_state()
        for battery_id in BATTERY_IDS
    } == resources_before
    assert (
        ctx.rng_manager.get_state()["streams"]["combat"]
        == rng_before
    )
