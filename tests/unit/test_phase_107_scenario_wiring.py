"""Phase 107 red tests for reinforcement and morale scenario wiring."""

from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.morale.rout import RoutEngine
from stochastic_warfare.morale.runtime import MoraleRuntime
from stochastic_warfare.morale.state import MoraleState
from stochastic_warfare.simulation.campaign import (
    CampaignConfig,
    ReinforcementArrivedEvent,
)
from stochastic_warfare.simulation.engine import (
    EngineConfig,
    SimulationEngine,
    TickResolution,
)
from stochastic_warfare.simulation.scenario import (
    CampaignScenarioConfig,
    ReinforcementConfig,
    ReinforcementUnitConfig,
    ScenarioLoader,
    SideConfig,
    SimulationContext,
    load_campaign_scenario_config,
)
from stochastic_warfare.simulation.tactical_targeting import (
    TacticalTargetingRuntime,
)
from stochastic_warfare.simulation.victory import VictoryEvaluator
from tests.conftest import make_versionless_legacy_morale_checkpoint


DATA_DIR = Path("data")
REINFORCEMENT_SCENARIO = Path(
    "data/scenarios/test_campaign_reinforce/scenario.yaml",
)
GOOSE_GREEN_SCENARIO = Path(
    "data/scenarios/falklands_goose_green/scenario.yaml",
)


def _reinforcement_config() -> CampaignScenarioConfig:
    return load_campaign_scenario_config(REINFORCEMENT_SCENARIO)


def _goose_green_config() -> CampaignScenarioConfig:
    return load_campaign_scenario_config(GOOSE_GREEN_SCENARIO)


def _one_wave(
    *,
    arrival_time_s: float,
    count: int = 1,
    position: list[float] | None = None,
) -> ReinforcementConfig:
    return ReinforcementConfig(
        side="blue",
        arrival_time_s=arrival_time_s,
        units=[ReinforcementUnitConfig(unit_type="m1a2", count=count)],
        position=position or [200.0, 5_000.0],
    )


def _load(
    scenario_path: Path,
    config: CampaignScenarioConfig,
    *,
    seed: int = 107,
) -> SimulationContext:
    return ScenarioLoader(DATA_DIR).load(
        scenario_path,
        seed=seed,
        scenario_config=config,
    )


def _quiet_campaign_config(
    *,
    engagement_detection_range_m: float = 1_000.0,
) -> CampaignConfig:
    return CampaignConfig(
        engagement_detection_range_m=engagement_detection_range_m,
        enable_strategic_movement=False,
        enable_maintenance=False,
        enable_supply_network=False,
    )


def _unit_ids(ctx: SimulationContext) -> dict[str, list[str]]:
    return {
        side: [unit.entity_id for unit in units]
        for side, units in ctx.units_by_side.items()
    }


def _weapon_signature(
    ctx: SimulationContext,
    unit_id: str,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    return tuple(
        (
            weapon.definition.weapon_id,
            tuple(ammo.ammo_id for ammo in ammo_definitions),
        )
        for weapon, ammo_definitions in ctx.unit_weapons[unit_id]
    )


def _sensor_signature(
    ctx: SimulationContext,
    unit_id: str,
) -> tuple[str, ...]:
    return tuple(
        sensor.definition.sensor_id
        for sensor in ctx.unit_sensors[unit_id]
    )


@pytest.mark.parametrize(
    ("model", "payload", "typo"),
    [
        (
            ReinforcementUnitConfig,
            {"unit_type": "m1a2", "cnt": 2},
            "cnt",
        ),
        (
            ReinforcementConfig,
            {
                "side": "blue",
                "arrival_time_s": 3_600.0,
                "units": [{"unit_type": "m1a2"}],
                "arrival_sigam": 0.2,
            },
            "arrival_sigam",
        ),
        (
            SideConfig,
            {
                "side": "blue",
                "units": [],
                "morale_inital": "SHAKEN",
            },
            "morale_inital",
        ),
    ],
)
def test_phase107_config_models_reject_behavior_changing_typos(
    model: Any,
    payload: dict[str, Any],
    typo: str,
) -> None:
    with pytest.raises(ValidationError, match=typo):
        model.model_validate(payload)


def _assert_unit_morale(
    ctx: SimulationContext,
    unit_ids: list[str],
    expected: MoraleState,
    expected_status: UnitStatus,
) -> None:
    assert ctx.morale_runtime is not None
    for unit_id in unit_ids:
        assert ctx.morale_states[unit_id] is expected
        assert ctx.morale_runtime.record_for(unit_id).current_state is expected
        unit = next(unit for unit in ctx.all_units() if unit.entity_id == unit_id)
        assert unit.status is expected_status


@pytest.mark.parametrize(
    ("resolution", "arrival_time_s", "engagement_range_m", "closing_mult"),
    [
        (TickResolution.STRATEGIC, 3_600.0, 1_000.0, 0.0),
        (TickResolution.OPERATIONAL, 300.0, 1_000.0, 20.0),
        (TickResolution.TACTICAL, 5.0, 15_000.0, 0.0),
    ],
)
def test_engine_registers_once_and_checks_due_waves_at_every_resolution(
    resolution: TickResolution,
    arrival_time_s: float,
    engagement_range_m: float,
    closing_mult: float,
) -> None:
    config = _reinforcement_config()
    config.reinforcements = [_one_wave(arrival_time_s=arrival_time_s)]
    ctx = _load(REINFORCEMENT_SCENARIO, config)
    received: list[ReinforcementArrivedEvent] = []
    ctx.event_bus.subscribe(ReinforcementArrivedEvent, received.append)
    initial_count = len(ctx.units_by_side["blue"])
    engine = SimulationEngine(
        ctx,
        config=EngineConfig(resolution_closing_range_mult=closing_mult),
        campaign_config=_quiet_campaign_config(
            engagement_detection_range_m=engagement_range_m,
        ),
    )
    engine._set_resolution(resolution)

    entries = engine.campaign_manager._reinforcements
    assert len(entries) == 1
    assert entries[0].config == config.reinforcements[0]
    assert entries[0].arrived is False

    engine.step()

    assert entries[0].arrived is True
    assert len(ctx.units_by_side["blue"]) == initial_count + 1
    assert len(received) == 1

    engine.step()

    assert len(engine.campaign_manager._reinforcements) == 1
    assert len(ctx.units_by_side["blue"]) == initial_count + 1
    assert len(received) == 1


def _run_two_same_type_waves() -> tuple[
    SimulationContext,
    SimulationEngine,
    list[str],
]:
    config = _reinforcement_config()
    config.reinforcements = [
        _one_wave(
            arrival_time_s=3_600.0,
            count=2,
            position=[200.0, 5_000.0, 125.0],
        ),
        _one_wave(
            arrival_time_s=3_600.0,
            count=2,
            position=[200.0, 6_000.0, 250.0],
        ),
    ]
    ctx = _load(REINFORCEMENT_SCENARIO, config)
    initial_ids = {unit.entity_id for unit in ctx.all_units()}
    engine = SimulationEngine(
        ctx,
        config=EngineConfig(resolution_closing_range_mult=0.0),
        campaign_config=_quiet_campaign_config(),
    )

    engine.step()

    arrived_ids = [
        unit.entity_id
        for unit in ctx.units_by_side["blue"]
        if unit.entity_id not in initial_ids
    ]
    return ctx, engine, arrived_ids


def test_same_type_waves_have_stable_ordinals_unique_ids_and_exact_loadouts(
) -> None:
    ctx, engine, arrived_ids = _run_two_same_type_waves()
    replay_ctx, replay_engine, replay_arrived_ids = _run_two_same_type_waves()

    assert [
        entry.wave_ordinal
        for entry in engine.campaign_manager._reinforcements
    ] == [0, 1]
    assert [
        entry.wave_ordinal
        for entry in replay_engine.campaign_manager._reinforcements
    ] == [0, 1]
    assert len(arrived_ids) == 4
    assert len(set(arrived_ids)) == 4
    assert arrived_ids == replay_arrived_ids
    assert arrived_ids[:2] != arrived_ids[2:]

    arrived_units = [
        unit
        for unit in ctx.units_by_side["blue"]
        if unit.entity_id in set(arrived_ids)
    ]
    assert [
        (
            unit.position.easting,
            unit.position.northing,
            unit.position.altitude,
        )
        for unit in arrived_units
    ] == [
        (200.0, 5_000.0, 125.0),
        (200.0, 5_050.0, 125.0),
        (200.0, 6_000.0, 250.0),
        (200.0, 6_050.0, 250.0),
    ]

    reference_id = next(
        unit.entity_id
        for unit in ctx.units_by_side["blue"]
        if unit.entity_id not in arrived_ids and unit.unit_type == "m1a2"
    )
    expected_weapons = _weapon_signature(ctx, reference_id)
    expected_sensors = _sensor_signature(ctx, reference_id)
    assert expected_weapons
    assert expected_sensors

    weapon_list_ids: set[int] = set()
    sensor_list_ids: set[int] = set()
    weapon_instance_ids: set[int] = set()
    sensor_instance_ids: set[int] = set()
    for unit in arrived_units:
        unit_id = unit.entity_id
        assert unit_id in ctx.unit_weapons
        assert unit_id in ctx.unit_sensors
        assert _weapon_signature(ctx, unit_id) == expected_weapons
        assert _sensor_signature(ctx, unit_id) == expected_sensors
        weapon_list_ids.add(id(ctx.unit_weapons[unit_id]))
        sensor_list_ids.add(id(ctx.unit_sensors[unit_id]))
        for weapon, _ in ctx.unit_weapons[unit_id]:
            weapon_instance_ids.add(id(weapon))
            assert weapon.equipment in unit.equipment
        for sensor in ctx.unit_sensors[unit_id]:
            sensor_instance_ids.add(id(sensor))
            assert sensor.equipment in unit.equipment

    assert len(weapon_list_ids) == len(arrived_ids)
    assert len(sensor_list_ids) == len(arrived_ids)
    assert len(weapon_instance_ids) == len(arrived_ids) * len(expected_weapons)
    assert len(sensor_instance_ids) == len(arrived_ids) * len(expected_sensors)
    assert set(arrived_ids).issubset(replay_ctx.unit_weapons)
    assert set(arrived_ids).issubset(replay_ctx.unit_sensors)


def test_arrived_reinforcement_fires_through_production_battle_path() -> None:
    config = _reinforcement_config()
    config.reinforcements = [
        _one_wave(
            arrival_time_s=3_600.0,
            position=[9_800.0, 5_000.0],
        ),
    ]
    ctx = _load(REINFORCEMENT_SCENARIO, config)
    engine = SimulationEngine(
        ctx,
        config=EngineConfig(resolution_closing_range_mult=0.0),
        campaign_config=_quiet_campaign_config(
            engagement_detection_range_m=1_000.0,
        ),
    )
    assert engine.battle_manager.active_battles == []

    engine.step()

    dynamic_id = "reinforce_blue_0000_m1a2_0000"
    battle = engine.battle_manager.active_battles[0]
    assert dynamic_id in battle.unit_ids
    assert battle.ticks_executed == 0
    assert battle.start_time.isoformat() == "2024-06-15T07:00:00+00:00"

    engine.step()

    assert battle.ticks_executed == 1
    main_gun = next(
        weapon
        for weapon, _ in ctx.unit_weapons[dynamic_id]
        if weapon.definition.weapon_id == "m256_120mm"
    )
    remaining = main_gun.ammo_state.available("m829a3_apfsds")
    assert 0 < remaining < main_gun.definition.magazine_capacity


def test_loader_rejects_unknown_reinforcement_type_before_engine_construction(
) -> None:
    config = _reinforcement_config()
    config.reinforcements = [
        ReinforcementConfig(
            side="blue",
            arrival_time_s=3_600.0,
            units=[
                ReinforcementUnitConfig(
                    unit_type="phase107_missing_unit",
                    count=1,
                ),
            ],
            position=[200.0, 5_000.0],
        ),
    ]

    with pytest.raises(
        ValueError,
        match=r"(?i)reinforcement.*phase107_missing_unit",
    ):
        _load(REINFORCEMENT_SCENARIO, config)


def test_failed_wave_is_atomic_and_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _reinforcement_config()
    config.reinforcements = [
        _one_wave(arrival_time_s=3_600.0, count=2),
    ]
    ctx = _load(REINFORCEMENT_SCENARIO, config)
    engine = SimulationEngine(
        ctx,
        config=EngineConfig(resolution_closing_range_mult=0.0),
        campaign_config=_quiet_campaign_config(),
    )
    events: list[ReinforcementArrivedEvent] = []
    ctx.event_bus.subscribe(ReinforcementArrivedEvent, events.append)
    before_units = _unit_ids(ctx)
    before_weapon_keys = set(ctx.unit_weapons)
    before_sensor_keys = set(ctx.unit_sensors)
    before_morale = dict(ctx.morale_states)
    original_create_unit = ctx.unit_loader.create_unit
    calls = 0

    def fail_second_unit(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("phase107 injected unit creation failure")
        return original_create_unit(*args, **kwargs)

    monkeypatch.setattr(ctx.unit_loader, "create_unit", fail_second_unit)

    with pytest.raises(
        RuntimeError,
        match="phase107 injected unit creation failure",
    ):
        engine.step()

    entry = engine.campaign_manager._reinforcements[0]
    assert calls == 2
    assert entry.arrived is False
    assert _unit_ids(ctx) == before_units
    assert set(ctx.unit_weapons) == before_weapon_keys
    assert set(ctx.unit_sensors) == before_sensor_keys
    assert ctx.morale_states == before_morale
    assert events == []

    monkeypatch.setattr(ctx.unit_loader, "create_unit", original_create_unit)
    engine.step()

    assert entry.arrived is True
    assert len(ctx.units_by_side["blue"]) == len(before_units["blue"]) + 2
    assert len(events) == 1


def test_goose_green_initial_morale_populates_context_and_state_machine(
) -> None:
    ctx = _load(GOOSE_GREEN_SCENARIO, _goose_green_config())
    blue_ids = [unit.entity_id for unit in ctx.units_by_side["blue"]]
    red_ids = [unit.entity_id for unit in ctx.units_by_side["red"]]

    _assert_unit_morale(
        ctx,
        blue_ids,
        MoraleState.STEADY,
        UnitStatus.ACTIVE,
    )
    _assert_unit_morale(
        ctx,
        red_ids,
        MoraleState.SHAKEN,
        UnitStatus.ACTIVE,
    )


@pytest.mark.parametrize(
    ("initial_morale", "expected_status"),
    [
        (MoraleState.SHAKEN, UnitStatus.ACTIVE),
        (MoraleState.ROUTED, UnitStatus.ROUTING),
        (MoraleState.SURRENDERED, UnitStatus.SURRENDERED),
    ],
)
def test_reinforcements_inherit_side_morale_and_status(
    initial_morale: MoraleState,
    expected_status: UnitStatus,
) -> None:
    config = _reinforcement_config()
    config.sides[0].morale_initial = initial_morale.name
    config.reinforcements = [_one_wave(arrival_time_s=3_600.0)]
    ctx = _load(REINFORCEMENT_SCENARIO, config)
    initial_ids = [unit.entity_id for unit in ctx.units_by_side["blue"]]
    _assert_unit_morale(ctx, initial_ids, initial_morale, expected_status)
    engine = SimulationEngine(
        ctx,
        config=EngineConfig(resolution_closing_range_mult=0.0),
        campaign_config=_quiet_campaign_config(),
    )

    engine.step()

    arrived_ids = [
        unit.entity_id
        for unit in ctx.units_by_side["blue"]
        if unit.entity_id not in set(initial_ids)
    ]
    assert len(arrived_ids) == 1
    _assert_unit_morale(
        ctx,
        arrived_ids,
        initial_morale,
        expected_status,
    )


@pytest.mark.parametrize("invalid_morale", ["shaken", "PANICKED"])
def test_side_morale_rejects_noncanonical_values(
    invalid_morale: str,
) -> None:
    raw_config = _reinforcement_config().model_dump(mode="python")
    raw_config["sides"][0]["morale_initial"] = invalid_morale

    with pytest.raises(ValueError, match="morale_initial"):
        CampaignScenarioConfig.model_validate(raw_config)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("arrival_time_s", float("nan")),
        ("arrival_time_s", float("inf")),
        ("arrival_sigma", float("nan")),
        ("arrival_sigma", float("inf")),
        ("position", [0.0, float("inf")]),
    ],
)
def test_reinforcement_rejects_nonfinite_values(
    field: str,
    value: Any,
) -> None:
    data = _one_wave(arrival_time_s=1.0).model_dump(mode="python")
    data[field] = value

    with pytest.raises(ValueError, match=field):
        ReinforcementConfig.model_validate(data)


def _morale_only_engine(
    config: CampaignScenarioConfig,
) -> SimulationEngine:
    ctx = _load(GOOSE_GREEN_SCENARIO, config)
    morale_condition = next(
        condition
        for condition in config.victory_conditions
        if condition.type == "morale_collapsed"
    )
    evaluator = VictoryEvaluator(
        objectives=[],
        conditions=[morale_condition],
        event_bus=ctx.event_bus,
    )
    return SimulationEngine(
        ctx,
        config=EngineConfig(resolution_closing_range_mult=0.0),
        campaign_config=_quiet_campaign_config(
            engagement_detection_range_m=1.0,
        ),
        victory_evaluator=evaluator,
    )


def test_initial_rout_drives_morale_collapsed_with_shaken_control() -> None:
    shaken_config = _goose_green_config()
    shaken_engine = _morale_only_engine(shaken_config)
    assert shaken_engine.step() is False

    routed_config = _goose_green_config()
    routed_config.sides[1].morale_initial = MoraleState.ROUTED.name
    routed_engine = _morale_only_engine(routed_config)

    assert routed_engine.step() is True
    assert routed_engine._last_victory.condition_type == "morale_collapsed"
    assert routed_engine._last_victory.winning_side == "blue"


def _checkpoint_engine(
    *,
    continuous_time: bool = False,
) -> tuple[SimulationContext, SimulationEngine]:
    config = _reinforcement_config()
    if continuous_time:
        raw_config = config.model_dump(mode="python")
        raw_config["calibration_overrides"]["morale"][
            "use_continuous_time"
        ] = True
        config = CampaignScenarioConfig.model_validate(raw_config)
    ctx = _load(REINFORCEMENT_SCENARIO, config)
    engine = SimulationEngine(
        ctx,
        config=EngineConfig(resolution_closing_range_mult=0.0),
        campaign_config=_quiet_campaign_config(),
    )
    return ctx, engine


def _json_checkpoint(engine: SimulationEngine) -> dict[str, Any]:
    return json.loads(engine.checkpoint().decode("utf-8"))


def _versionless_legacy_morale_checkpoint(
    checkpoint: dict[str, Any],
) -> dict[str, Any]:
    """Convert one current checkpoint into the bounded pre-113 envelope."""
    return make_versionless_legacy_morale_checkpoint(checkpoint)


def _empty_direct_engine(
    *,
    with_runtime: bool,
    with_targeting: bool = True,
) -> tuple[SimulationContext, SimulationEngine]:
    config = _reinforcement_config()
    event_bus = EventBus()
    rng_manager = RNGManager(113)
    morale_rng = rng_manager.get_stream(ModuleId.MORALE)
    rout_engine = RoutEngine(event_bus, morale_rng)
    morale_runtime = None
    if with_runtime:
        morale_runtime = MoraleRuntime(
            event_bus,
            morale_rng,
            rout_engine=rout_engine,
        )
    context = SimulationContext(
        config=config,
        clock=SimulationClock(
            start=datetime(2024, 6, 15, 6, 0, tzinfo=timezone.utc),
            tick_duration=timedelta(hours=1),
        ),
        rng_manager=rng_manager,
        event_bus=event_bus,
        units_by_side={"blue": [], "red": []},
        tactical_targeting=(
            TacticalTargetingRuntime(
                sensing_aware_standoff_enabled=True,
                unit_sides={},
            )
            if with_targeting
            else None
        ),
        morale_runtime=morale_runtime,
        rout_engine=rout_engine,
    )
    return context, SimulationEngine(
        context,
        config=EngineConfig(resolution_closing_range_mult=0.0),
        campaign_config=_quiet_campaign_config(),
    )


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("entity_id", "custom"),
        ("position", ["invalid"]),
        ("side", "red"),
        ("unit_type", "t72"),
        ("domain", "AIR"),
        ("status", "DESTROYED"),
        ("personnel", []),
        ("equipment", []),
        ("training_level", 0.8),
        ("training_level", -5.0),
        ("max_speed", "fast"),
    ],
)
def test_loader_rejects_untyped_reinforcement_overrides(
    field_name: str,
    value: Any,
) -> None:
    config = _reinforcement_config()
    config.reinforcements[0].units[0].overrides[field_name] = value

    with pytest.raises(
        ValueError,
        match="overrides are not supported",
    ):
        _load(REINFORCEMENT_SCENARIO, config)


def test_unknown_reinforcement_override_rejects_wave_atomically() -> None:
    config = _reinforcement_config()
    ctx = _load(REINFORCEMENT_SCENARIO, config)
    engine = SimulationEngine(
        ctx,
        config=EngineConfig(resolution_closing_range_mult=0.0),
        campaign_config=_quiet_campaign_config(),
    )
    engine.campaign_manager._reinforcements[0].config.units[0].overrides[
        "not_a_unit_field"
    ] = 1
    before_ids = _unit_ids(ctx)
    entities_rng = ctx.rng_manager.get_stream(ModuleId.ENTITIES)
    before_rng = copy.deepcopy(entities_rng.bit_generator.state)

    with pytest.raises(ValueError, match="overrides are not supported"):
        engine.campaign_manager.check_reinforcements(
            ctx,
            elapsed_s=10_000.0,
        )

    assert _unit_ids(ctx) == before_ids
    assert entities_rng.bit_generator.state == before_rng
    assert engine.campaign_manager._reinforcements[0].arrived is False


def test_arrived_dynamic_loadouts_restore_fresh_and_continue_exactly() -> None:
    control_ctx, control = _checkpoint_engine()
    initial_ids = {unit.entity_id for unit in control_ctx.all_units()}

    control.step()

    arrived_ids = [
        unit.entity_id
        for unit in control_ctx.units_by_side["blue"]
        if unit.entity_id not in initial_ids
    ]
    assert len(arrived_ids) == 2
    for unit_id in arrived_ids:
        assert _weapon_signature(control_ctx, unit_id)
        assert _sensor_signature(control_ctx, unit_id)
    checkpoint = control.checkpoint()
    checkpoint_state = json.loads(checkpoint.decode("utf-8"))

    control.step()
    expected_continuation = _json_checkpoint(control)

    resumed_ctx, resumed = _checkpoint_engine()
    assert resumed_ctx.morale_runtime is not None
    runtime_identity = resumed_ctx.morale_runtime
    view_identity = resumed_ctx.morale_states
    records_identity = resumed_ctx.morale_runtime.records
    machine_identity = resumed_ctx.morale_runtime._machine
    morale_rng = resumed_ctx.rng_manager.get_stream(ModuleId.MORALE)
    resumed.restore(checkpoint)

    assert _json_checkpoint(resumed) == checkpoint_state
    assert resumed_ctx.morale_runtime is runtime_identity
    assert resumed_ctx.morale_states is view_identity
    assert resumed_ctx.morale_runtime.records is records_identity
    assert resumed_ctx.morale_runtime._machine is machine_identity
    assert resumed_ctx.morale_runtime.rng is morale_rng
    assert resumed_ctx.morale_runtime._machine.rng is morale_rng
    assert resumed_ctx.rout_engine.rng is morale_rng
    for unit_id in arrived_ids:
        assert _weapon_signature(resumed_ctx, unit_id) == _weapon_signature(
            control_ctx,
            unit_id,
        )
        assert _sensor_signature(resumed_ctx, unit_id) == _sensor_signature(
            control_ctx,
            unit_id,
        )

    resumed.step()

    assert _json_checkpoint(resumed) == expected_continuation


def test_current_checkpoint_has_one_canonical_morale_owner() -> None:
    ctx, engine = _checkpoint_engine()
    state = _json_checkpoint(engine)
    context_state = state["context"]

    assert state["checkpoint_version"] == 118
    assert "morale_states" not in context_state
    assert "morale_machine" not in context_state
    assert set(context_state["morale_runtime"]) == {
        "active_records",
        "suspended_archives",
    }
    assert "rng_state" not in context_state["morale_runtime"]
    assert "rng_state" not in context_state["rout_engine"]
    assert ctx.morale_runtime is not None
    assert set(context_state["morale_runtime"]["active_records"]) == {
        unit.entity_id
        for unit in ctx.all_units()
    }


def test_campaign_topology_rejection_precedes_context_restore() -> None:
    ctx, engine = _checkpoint_engine()
    checkpoint = _json_checkpoint(engine)
    engine.step()
    before = _json_checkpoint(engine)
    assert len(ctx.units_by_side["blue"]) > len(
        checkpoint["context"]["units_by_side"]["blue"],
    )

    invalid = copy.deepcopy(checkpoint)
    invalid["campaign"]["reinforcements"][0]["config"]["side"] = "red"

    with pytest.raises(ValueError, match="configuration differs"):
        engine.set_state(invalid)

    assert _json_checkpoint(engine) == before


@pytest.mark.parametrize("unsupported_version", [113, 117])
def test_unknown_checkpoint_version_rejects_atomically(
    unsupported_version: int,
) -> None:
    _, engine = _checkpoint_engine()
    invalid = _json_checkpoint(engine)
    invalid["checkpoint_version"] = unsupported_version
    before = _json_checkpoint(engine)

    with pytest.raises(ValueError, match="Unsupported checkpoint version"):
        engine.set_state(invalid)

    assert _json_checkpoint(engine) == before


def test_explicit_null_checkpoint_version_rejects_atomically() -> None:
    _, engine = _checkpoint_engine()
    invalid = _json_checkpoint(engine)
    invalid["checkpoint_version"] = None
    before = _json_checkpoint(engine)

    with pytest.raises(ValueError, match="Unsupported checkpoint version"):
        engine.set_state(invalid)

    assert _json_checkpoint(engine) == before


def test_current_checkpoint_requires_morale_runtime_atomically() -> None:
    _, source = _checkpoint_engine()
    invalid = _json_checkpoint(source)
    invalid["context"].pop("morale_runtime")

    _, target = _checkpoint_engine()
    target.step()
    before = _json_checkpoint(target)

    with pytest.raises(
        ValueError,
        match="missing required morale state",
    ):
        target.set_state(invalid)

    assert _json_checkpoint(target) == before


@pytest.mark.parametrize("invalid_runtime", [None, False, []])
def test_current_checkpoint_rejects_malformed_runtime_atomically(
    invalid_runtime: object,
) -> None:
    _, target = _checkpoint_engine()
    invalid = _json_checkpoint(target)
    invalid["context"]["morale_runtime"] = invalid_runtime
    before = _json_checkpoint(target)

    with pytest.raises(ValueError, match="morale-runtime mapping"):
        target.set_state(invalid)

    assert _json_checkpoint(target) == before


@pytest.mark.parametrize(
    "missing_key",
    ["config", "era_config", "unit_weapon_states", "unit_sensor_states"],
)
def test_current_checkpoint_requires_exact_context_key_topology_atomically(
    missing_key: str,
) -> None:
    _, target = _checkpoint_engine()
    invalid = _json_checkpoint(target)
    invalid["context"].pop(missing_key)
    before = _json_checkpoint(target)

    with pytest.raises(ValueError, match="context key topology"):
        target.set_state(invalid)

    assert _json_checkpoint(target) == before


def test_current_checkpoint_rejects_extra_context_key_atomically() -> None:
    _, target = _checkpoint_engine()
    invalid = _json_checkpoint(target)
    invalid["context"]["unknown_v107_state"] = {}
    before = _json_checkpoint(target)

    with pytest.raises(ValueError, match="context key topology"):
        target.set_state(invalid)

    assert _json_checkpoint(target) == before


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("config", None, "Checkpoint configuration"),
        ("config", [], "Checkpoint configuration"),
        ("calibration", None, "Checkpoint calibration"),
        ("calibration", [], "Checkpoint calibration"),
    ],
)
def test_current_checkpoint_rejects_invalid_context_value_shapes_atomically(
    key: str,
    value: object,
    message: str,
) -> None:
    _, target = _checkpoint_engine()
    invalid = _json_checkpoint(target)
    invalid["context"][key] = value
    before = _json_checkpoint(target)

    with pytest.raises(ValueError, match=message):
        target.set_state(invalid)

    assert _json_checkpoint(target) == before


def test_current_checkpoint_config_comparison_is_type_aware_atomically() -> None:
    _, target = _checkpoint_engine()
    invalid = _json_checkpoint(target)
    latitude = invalid["context"]["config"]["latitude"]
    assert isinstance(latitude, float)
    invalid["context"]["config"]["latitude"] = int(latitude)
    before = _json_checkpoint(target)

    with pytest.raises(ValueError, match="configuration does not match"):
        target.set_state(invalid)

    assert _json_checkpoint(target) == before


@pytest.mark.parametrize("mutation", ["missing", "extra"])
def test_current_checkpoint_requires_exact_engine_key_topology_atomically(
    mutation: str,
) -> None:
    _, target = _checkpoint_engine()
    invalid = _json_checkpoint(target)
    if mutation == "missing":
        invalid.pop("battle")
    else:
        invalid["unknown_v107_state"] = {}
    before = _json_checkpoint(target)

    with pytest.raises(ValueError, match="engine key topology"):
        target.set_state(invalid)

    assert _json_checkpoint(target) == before


@pytest.mark.parametrize(
    ("mutation", "value"),
    [
        ("wave_ordinal", False),
        ("wave_ordinal", 0.0),
        ("side", "red"),
        ("arrival_time_s", 3600),
        ("config_count", 2.0),
        ("config_sigma", False),
    ],
)
def test_current_campaign_state_is_canonical_and_type_aware_atomically(
    mutation: str,
    value: object,
) -> None:
    _, target = _checkpoint_engine()
    invalid = _json_checkpoint(target)
    reinforcement = invalid["campaign"]["reinforcements"][0]
    if mutation == "config_count":
        reinforcement["config"]["units"][0]["count"] = value
    elif mutation == "config_sigma":
        reinforcement["config"]["arrival_sigma"] = value
    else:
        reinforcement[mutation] = value
    before = _json_checkpoint(target)

    with pytest.raises(ValueError, match="schedule topology"):
        target.set_state(invalid)

    assert _json_checkpoint(target) == before


def test_current_checkpoint_rejects_legacy_campaign_shape_atomically() -> None:
    _, source = _checkpoint_engine()
    invalid = _json_checkpoint(source)
    for reinforcement in invalid["campaign"]["reinforcements"]:
        reinforcement.pop("wave_ordinal")
        reinforcement.pop("config")

    _, target = _checkpoint_engine()
    target.step()
    before = _json_checkpoint(target)

    with pytest.raises(
        ValueError,
        match="Legacy reinforcement checkpoint entries require",
    ):
        target.set_state(invalid)

    assert _json_checkpoint(target) == before


def test_checkpoint_rejects_dynamic_unit_type_mismatch_atomically() -> None:
    _, source = _checkpoint_engine()
    source.step()
    invalid = _json_checkpoint(source)
    dynamic_id = "reinforce_blue_0000_m1a2_0000"
    raw_unit = next(
        unit
        for unit in invalid["context"]["units_by_side"]["blue"]
        if unit["entity_id"] == dynamic_id
    )
    raw_unit["unit_type"] = "t72m"

    _, target = _checkpoint_engine()
    before = _json_checkpoint(target)

    with pytest.raises(
        ValueError,
        match=(
            "reinforcement arrival flag or unit topology disagrees with "
            "force roster at wave 0"
        ),
    ):
        target.set_state(invalid)

    assert _json_checkpoint(target) == before


@pytest.mark.parametrize(
    ("arrive_before_checkpoint", "corrupt_arrived"),
    [(False, True), (True, False)],
)
def test_checkpoint_arrival_flag_must_match_force_roster_atomically(
    arrive_before_checkpoint: bool,
    corrupt_arrived: bool,
) -> None:
    _, source = _checkpoint_engine()
    if arrive_before_checkpoint:
        source.step()
    invalid = _json_checkpoint(source)
    reinforcement = invalid["campaign"]["reinforcements"][0]
    reinforcement["arrived"] = corrupt_arrived
    reinforcement["actual_arrival_time_s"] = (
        0.0 if corrupt_arrived else 7200.0
    )

    _, target = _checkpoint_engine()
    before = _json_checkpoint(target)

    expected_validation = (
        "Checkpoint reinforcement arrival flag or unit topology disagrees "
        "with force roster at wave 0: "
        "'reinforce_blue_0000_m1a2_0000' must be present as 'blue'/'m1a2'"
        if corrupt_arrived
        else "Checkpoint reinforcement arrival flag disagrees with force "
        "roster at wave 0: 'reinforce_blue_0000_m1a2_0000' is present "
        "before arrival"
    )
    with pytest.raises(ValueError, match=expected_validation):
        target.set_state(invalid)

    assert _json_checkpoint(target) == before


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_record",
        "empty_records",
        "invalid_state",
        "status_disagreement",
        "boolean_generation",
        "future_check_time",
    ],
)
def test_dynamic_morale_runtime_records_validate_atomically(
    mutation: str,
) -> None:
    _, source = _checkpoint_engine()
    source.step()
    invalid = _json_checkpoint(source)
    dynamic_id = "reinforce_blue_0000_m1a2_0000"
    records = invalid["context"]["morale_runtime"]["active_records"]
    if mutation == "missing_record":
        records.pop(dynamic_id)
    elif mutation == "empty_records":
        records.clear()
    elif mutation == "invalid_state":
        records[dynamic_id]["current_state"] = 99
    elif mutation == "status_disagreement":
        records[dynamic_id]["current_state"] = int(MoraleState.ROUTED)
    elif mutation == "boolean_generation":
        records[dynamic_id]["generation"] = False
    else:
        records[dynamic_id]["last_check_time_s"] = 1.0e12
        records[dynamic_id]["generation"] = 1

    _, target = _checkpoint_engine()
    before = _json_checkpoint(target)

    with pytest.raises(ValueError, match="morale"):
        target.set_state(invalid)

    assert _json_checkpoint(target) == before


@pytest.mark.parametrize("value", [False, 0.0])
def test_current_checkpoint_requires_integer_morale_values_atomically(
    value: object,
) -> None:
    _, target = _checkpoint_engine()
    invalid = _json_checkpoint(target)
    records = invalid["context"]["morale_runtime"]["active_records"]
    unit_id = next(iter(records))
    records[unit_id]["current_state"] = value
    before = _json_checkpoint(target)

    with pytest.raises(ValueError, match="morale"):
        target.set_state(invalid)

    assert _json_checkpoint(target) == before


def test_current_checkpoint_rejects_extra_morale_record_atomically(
) -> None:
    _, target = _checkpoint_engine()
    invalid = _json_checkpoint(target)
    records = invalid["context"]["morale_runtime"]["active_records"]
    records["ghost"] = copy.deepcopy(next(iter(records.values())))
    before = _json_checkpoint(target)

    with pytest.raises(ValueError, match="morale"):
        target.set_state(invalid)

    assert _json_checkpoint(target) == before


def test_versionless_checkpoint_retains_named_morale_compatibility() -> None:
    _, target = _checkpoint_engine()
    legacy = _versionless_legacy_morale_checkpoint(
        _json_checkpoint(target),
    )
    unit_id = next(iter(legacy["context"]["morale_states"]))
    legacy["context"]["morale_states"][unit_id] = "STEADY"

    target.set_state(legacy)

    runtime_state = target.get_state()["context"]["morale_runtime"]
    assert (
        runtime_state["active_records"][unit_id]["current_state"]
        == int(MoraleState.STEADY)
    )


def test_versionless_morale_missing_from_both_owners_uses_side_backfill() -> None:
    ctx, target = _checkpoint_engine()
    legacy = _versionless_legacy_morale_checkpoint(
        _json_checkpoint(target),
    )
    unit_id = next(iter(legacy["context"]["morale_states"]))
    legacy["context"]["morale_states"].pop(unit_id)
    legacy["context"]["morale_machine"]["unit_states"].pop(unit_id)

    target.set_state(legacy)

    assert ctx.morale_runtime is not None
    record = ctx.morale_runtime.record_for(unit_id)
    assert record.current_state is MoraleState.STEADY
    assert record.last_transition_time_s is None
    assert record.last_check_time_s is None
    assert record.generation == 0


def test_versionless_morale_owner_disagreement_rejects_atomically() -> None:
    _, target = _checkpoint_engine()
    legacy = _versionless_legacy_morale_checkpoint(
        _json_checkpoint(target),
    )
    unit_id = next(iter(legacy["context"]["morale_states"]))
    legacy["context"]["morale_machine"]["unit_states"][unit_id][
        "current_state"
    ] = int(MoraleState.SHAKEN)
    before = _json_checkpoint(target)

    with pytest.raises(ValueError, match="morale stores disagree"):
        target.set_state(legacy)

    assert _json_checkpoint(target) == before


def test_versionless_current_morale_envelope_rejects_atomically() -> None:
    _, target = _checkpoint_engine()
    versionless_current = _json_checkpoint(target)
    versionless_current.pop("checkpoint_version")
    before = _json_checkpoint(target)

    with pytest.raises(
        ValueError,
        match="Versionless battle state cannot contain a Phase 118 performance receipt",
    ):
        target.set_state(versionless_current)

    assert _json_checkpoint(target) == before


@pytest.mark.parametrize("cooldown", [True, 30.0])
def test_versionless_morale_dead_cooldown_rejects_atomically(
    cooldown: object,
) -> None:
    _, target = _checkpoint_engine()
    legacy = _versionless_legacy_morale_checkpoint(
        _json_checkpoint(target),
    )
    record = next(
        iter(legacy["context"]["morale_machine"]["unit_states"].values()),
    )
    record["transition_cooldown_s"] = cooldown
    before = _json_checkpoint(target)

    with pytest.raises(ValueError, match="canonical inert 0.0"):
        target.set_state(legacy)

    assert _json_checkpoint(target) == before


@pytest.mark.parametrize(
    ("legacy_time", "expected_time", "expected_generation"),
    [(-1e9, None, 0), (0.0, 0.0, 1)],
)
def test_versionless_morale_time_migration_is_bounded(
    legacy_time: float,
    expected_time: float | None,
    expected_generation: int,
) -> None:
    ctx, target = _checkpoint_engine()
    legacy = _versionless_legacy_morale_checkpoint(
        _json_checkpoint(target),
    )
    unit_id = next(iter(legacy["context"]["morale_states"]))
    legacy["context"]["morale_machine"]["unit_states"][unit_id][
        "last_transition_time"
    ] = legacy_time

    target.set_state(legacy)

    assert ctx.morale_runtime is not None
    record = ctx.morale_runtime.record_for(unit_id)
    assert record.last_transition_time_s == expected_time
    assert record.last_check_time_s == expected_time
    assert record.generation == expected_generation


@pytest.mark.parametrize("legacy_time", [True, -2.0, 1.0])
def test_versionless_morale_impossible_time_rejects_atomically(
    legacy_time: object,
) -> None:
    _, target = _checkpoint_engine()
    legacy = _versionless_legacy_morale_checkpoint(
        _json_checkpoint(target),
    )
    record = next(
        iter(legacy["context"]["morale_machine"]["unit_states"].values()),
    )
    record["last_transition_time"] = legacy_time
    before = _json_checkpoint(target)

    with pytest.raises(ValueError, match="transition time"):
        target.set_state(legacy)

    assert _json_checkpoint(target) == before


@pytest.mark.parametrize("owner", ["morale_machine", "rout_engine"])
def test_versionless_morale_rng_mirror_must_match_authority_atomically(
    owner: str,
) -> None:
    _, target = _checkpoint_engine()
    legacy = _versionless_legacy_morale_checkpoint(
        _json_checkpoint(target),
    )
    rng_state = legacy["context"][owner]["rng_state"]
    rng_state["state"]["state"] ^= 1
    before = _json_checkpoint(target)

    with pytest.raises(ValueError, match=f"Legacy {owner} RNG disagrees"):
        target.set_state(legacy)

    assert _json_checkpoint(target) == before


def test_versionless_rout_rng_mirror_is_required_atomically() -> None:
    _, target = _checkpoint_engine()
    legacy = _versionless_legacy_morale_checkpoint(
        _json_checkpoint(target),
    )
    legacy["context"]["rout_engine"].pop("rng_state")
    before = _json_checkpoint(target)

    with pytest.raises(ValueError, match="rout_engine has invalid key"):
        target.set_state(legacy)

    assert _json_checkpoint(target) == before


def test_versionless_default_config_without_new_flag_migrates() -> None:
    ctx, target = _checkpoint_engine()
    legacy = _versionless_legacy_morale_checkpoint(
        _json_checkpoint(target),
    )
    del legacy["context"]["config"]["calibration_overrides"]["morale"][
        "use_continuous_time"
    ]

    target.set_state(legacy)

    assert ctx.morale_runtime is not None
    assert ctx.morale_runtime.config.use_continuous_time is False


def test_versionless_migration_plan_preserves_legacy_rout_envelope() -> None:
    ctx, target = _checkpoint_engine()
    legacy = _versionless_legacy_morale_checkpoint(
        _json_checkpoint(target),
    )
    legacy_context = legacy["context"]
    original_context = copy.deepcopy(legacy_context)

    plan = ctx.stage_state(legacy_context, allow_legacy_morale=True)

    assert plan.state["rout_engine"] == original_context["rout_engine"]
    assert legacy_context == original_context
    ctx.commit_state(plan)
    assert legacy_context == original_context


def test_started_continuous_time_versionless_checkpoint_rejects_atomically() -> None:
    _, source = _checkpoint_engine(continuous_time=True)
    source.step()
    legacy = _versionless_legacy_morale_checkpoint(
        _json_checkpoint(source),
    )
    ctx, target = _checkpoint_engine(continuous_time=True)
    assert ctx.morale_runtime is not None
    assert ctx.morale_runtime.config.use_continuous_time is True
    before = _json_checkpoint(target)

    with pytest.raises(ValueError, match="pristine tick 0"):
        target.set_state(legacy)

    assert _json_checkpoint(target) == before


def test_tick_zero_continuous_time_legacy_morale_migrates() -> None:
    ctx, target = _checkpoint_engine(continuous_time=True)
    assert ctx.morale_runtime is not None
    assert ctx.morale_runtime.config.use_continuous_time is True
    legacy = _versionless_legacy_morale_checkpoint(
        _json_checkpoint(target),
    )

    target.set_state(legacy)

    assert all(
        record.last_check_time_s is None and record.generation == 0
        for record in ctx.morale_runtime.records.values()
    )


@pytest.mark.parametrize(
    ("continuous_time", "expected_state"),
    [
        (False, MoraleState.STEADY),
        (True, MoraleState.SHAKEN),
    ],
)
def test_typed_continuous_time_config_changes_production_transition(
    continuous_time: bool,
    expected_state: MoraleState,
) -> None:
    patch = (
        {"morale": {"use_continuous_time": True}}
        if continuous_time
        else None
    )
    config = load_campaign_scenario_config(
        REINFORCEMENT_SCENARIO,
        patch,
    )
    ctx = _load(REINFORCEMENT_SCENARIO, config, seed=0)
    assert ctx.morale_runtime is not None
    unit_id = ctx.units_by_side["blue"][0].entity_id

    result = ctx.morale_runtime.check_transition(
        unit_id,
        0.0,
        0.0,
        False,
        0.0,
        1.0,
        timestamp=ctx.clock.current_time + timedelta(seconds=60.0),
        current_time_s=60.0,
    )

    record = ctx.morale_runtime.record_for(unit_id)
    assert config.calibration_overrides.morale.use_continuous_time is (
        continuous_time
    )
    assert ctx.morale_runtime.config.use_continuous_time is continuous_time
    assert result is expected_state
    assert record.current_state is expected_state
    assert record.last_transition_time_s == (
        60.0 if continuous_time else None
    )
    assert record.last_check_time_s == 60.0
    assert record.generation == 1


def test_continuous_time_configuration_is_checkpoint_identity() -> None:
    _, source = _checkpoint_engine(continuous_time=True)
    checkpoint = _json_checkpoint(source)
    assert checkpoint["context"]["config"]["calibration_overrides"][
        "morale"
    ]["use_continuous_time"] is True

    _, discrete = _checkpoint_engine()
    discrete_before = _json_checkpoint(discrete)
    with pytest.raises(ValueError, match="configuration does not match"):
        discrete.set_state(checkpoint)
    assert _json_checkpoint(discrete) == discrete_before

    _, resumed = _checkpoint_engine(continuous_time=True)
    resumed.set_state(checkpoint)
    assert _json_checkpoint(resumed) == checkpoint


def test_versionless_active_aggregate_morale_rejects_atomically() -> None:
    _, target = _checkpoint_engine()
    legacy = _versionless_legacy_morale_checkpoint(
        _json_checkpoint(target),
    )
    proxy = Unit(
        "agg_0000",
        Position(100.0, 200.0, 0.0),
        unit_type="test_aggregate",
        side="blue",
    )
    constituent = Unit(
        "archived-blue-1",
        Position(100.0, 200.0, 0.0),
        unit_type="test_constituent",
        side="blue",
    )
    legacy["context"]["units_by_side"]["blue"].append(proxy.get_state())
    legacy["context"]["aggregation_engine"]["aggregates"]["agg_0000"] = {
        "aggregate_id": "agg_0000",
        "side": "blue",
        "unit_type": "test_aggregate",
        "position": [100.0, 200.0, 0.0],
        "aggregate_combat_power": 1.0,
        "aggregate_personnel": 1,
        "aggregate_supply_state": 1.0,
        "snapshots": [
            {
                "unit_state": constituent.get_state(),
                "weapon_states": [],
                "sensor_states": [],
                "supply_inventory": None,
                "original_side": "blue",
                "order_records": [],
            },
        ],
    }
    before = _json_checkpoint(target)

    with pytest.raises(ValueError, match="active aggregation"):
        target.set_state(legacy)

    assert _json_checkpoint(target) == before


def test_current_null_morale_runtime_matrix_is_fail_closed() -> None:
    _, absent_target = _empty_direct_engine(with_runtime=False)
    null_state = _json_checkpoint(absent_target)
    assert null_state["context"]["morale_runtime"] is None
    absent_target.set_state(copy.deepcopy(null_state))

    _, runtime_target = _empty_direct_engine(with_runtime=True)
    envelope_state = _json_checkpoint(runtime_target)
    with pytest.raises(ValueError, match="must contain a morale-runtime mapping"):
        runtime_target.set_state(copy.deepcopy(null_state))
    with pytest.raises(ValueError, match="without MoraleRuntime"):
        absent_target.set_state(copy.deepcopy(envelope_state))

    active_route_state = copy.deepcopy(null_state)
    active_route_state["context"]["rout_engine"] = {
        "active_routs": {"ghost": {}},
    }
    with pytest.raises(ValueError, match="null morale runtime"):
        absent_target.set_state(active_route_state)


def test_started_versionless_reinforcement_checkpoint_rejects_atomically(
) -> None:
    _, source = _checkpoint_engine()
    source.step()
    checkpoint = _versionless_legacy_morale_checkpoint(
        _json_checkpoint(source),
    )
    for reinforcement in checkpoint["campaign"]["reinforcements"]:
        reinforcement.pop("wave_ordinal")
        reinforcement.pop("config")
    for index in range(2):
        checkpoint["context"]["morale_states"].pop(
            f"reinforce_blue_0000_m1a2_{index:04d}",
        )
        checkpoint["context"]["morale_machine"]["unit_states"].pop(
            f"reinforce_blue_0000_m1a2_{index:04d}",
        )
    serialized = json.dumps(checkpoint)
    for index in range(2):
        serialized = serialized.replace(
            f"reinforce_blue_0000_m1a2_{index:04d}",
            f"reinforce_blue_m1a2_{index:04d}",
        )
    legacy = json.loads(serialized)

    _, target = _checkpoint_engine()
    before = _json_checkpoint(target)

    with pytest.raises(ValueError, match="pristine tick 0"):
        target.set_state(legacy)

    assert _json_checkpoint(target) == before


def test_empty_engine_requires_tactical_targeting_owner() -> None:
    with pytest.raises(
        RuntimeError,
        match="requires tactical-targeting ownership",
    ):
        _empty_direct_engine(with_runtime=True, with_targeting=False)


@pytest.mark.parametrize(
    ("state_key", "kind"),
    [
        ("unit_weapon_states", "weapon"),
        ("unit_sensor_states", "sensor"),
    ],
)
def test_fresh_restore_rejects_missing_dynamic_loadout_key_atomically(
    state_key: str,
    kind: str,
) -> None:
    source_ctx, source = _checkpoint_engine()
    initial_ids = {unit.entity_id for unit in source_ctx.all_units()}
    source.step()
    checkpoint = _json_checkpoint(source)
    dynamic_id = next(
        unit.entity_id
        for unit in source_ctx.all_units()
        if unit.entity_id not in initial_ids
    )
    assert checkpoint["context"][state_key][dynamic_id]
    checkpoint["context"][state_key].pop(dynamic_id)

    _, target = _checkpoint_engine()
    before = _json_checkpoint(target)

    with pytest.raises(
        ValueError,
        match=rf"Incompatible {kind} unit topology",
    ):
        target.set_state(checkpoint)

    assert _json_checkpoint(target) == before


def _stochastic_wave_replay() -> tuple[bytes, list[ReinforcementArrivedEvent]]:
    config = _reinforcement_config()
    config.reinforcements[0].arrival_sigma = 0.25
    ctx = _load(REINFORCEMENT_SCENARIO, config, seed=107)
    received: list[ReinforcementArrivedEvent] = []
    ctx.event_bus.subscribe(ReinforcementArrivedEvent, received.append)
    engine = SimulationEngine(
        ctx,
        config=EngineConfig(resolution_closing_range_mult=0.0),
        campaign_config=_quiet_campaign_config(),
    )

    for _ in range(3):
        engine.step()

    return engine.checkpoint(), received


def test_stochastic_wave_full_state_and_events_replay_exactly() -> None:
    first_checkpoint, first_events = _stochastic_wave_replay()
    second_checkpoint, second_events = _stochastic_wave_replay()

    assert first_checkpoint == second_checkpoint
    assert first_events == second_events
    assert len(first_events) == len(_reinforcement_config().reinforcements)


def test_schedule_sampling_does_not_perturb_entity_stream() -> None:
    config = _reinforcement_config()
    config.reinforcements[0].arrival_sigma = 0.25
    ctx = _load(REINFORCEMENT_SCENARIO, config, seed=107)
    core_rng = ctx.rng_manager.get_stream(ModuleId.CORE)
    entities_rng = ctx.rng_manager.get_stream(ModuleId.ENTITIES)
    core_before = copy.deepcopy(core_rng.bit_generator.state)
    entities_before = copy.deepcopy(entities_rng.bit_generator.state)

    SimulationEngine(
        ctx,
        campaign_config=_quiet_campaign_config(),
    )

    assert core_rng.bit_generator.state != core_before
    assert entities_rng.bit_generator.state == entities_before
