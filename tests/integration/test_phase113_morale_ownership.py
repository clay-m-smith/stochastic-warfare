"""Phase 113 production proofs for single morale-state ownership."""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from stochastic_warfare.c2.orders.air_orders import (
    ATOPlanningEngine,
    AircraftAvailability,
)
from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.events import Event, EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import Domain, ModuleId, Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.morale.runtime import (
    MoraleRegistration,
    MoraleRuntime,
    MoraleStateRecord,
    MoraleTransitionCause,
)
from stochastic_warfare.morale.state import MoraleState
from stochastic_warfare.simulation.aggregation import (
    AggregationConfig,
    AggregationEngine,
)
from stochastic_warfare.simulation.battle import BattleConfig, BattleManager
from stochastic_warfare.simulation.campaign import CampaignConfig
from stochastic_warfare.simulation.engine import EngineConfig
from stochastic_warfare.simulation.runtime import (
    AnalysisVariant,
    PreparedScenario,
    RuntimeSession,
    SimulationRuntimeFactory,
)
from stochastic_warfare.simulation.scenario import (
    CampaignScenarioConfig,
    SimulationContext,
    load_campaign_scenario_config,
)
from stochastic_warfare.simulation.tactical_targeting import (
    TacticalTargetingRuntime,
)


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
REINFORCEMENT_SCENARIO = (
    DATA_DIR / "scenarios" / "test_campaign_reinforce" / "scenario.yaml"
)
GOOSE_GREEN_SCENARIO = (
    DATA_DIR / "scenarios" / "falklands_goose_green" / "scenario.yaml"
)
COIN_SCENARIO = DATA_DIR / "scenarios" / "coin_campaign" / "scenario.yaml"
SEED = 113
MAX_TICKS = 1_000_000
BASE_TIMESTAMP = datetime(2024, 6, 15, 6, 0, tzinfo=timezone.utc)
MELEE_SEED = 1
MELEE_MAX_TICKS = 2
MELEE_BLUE_ID = "blue_swiss_pike_block_0000"
MELEE_RED_ID = "red_norman_knight_conroi_0000"
MELEE_EVENT_TIMESTAMP = datetime(
    1066,
    10,
    14,
    9,
    0,
    1,
    tzinfo=timezone.utc,
)


def _prepare(
    scenario_path: Path,
    variant_id: str,
    *,
    config: CampaignScenarioConfig | None = None,
) -> PreparedScenario:
    variants = (AnalysisVariant(variant_id=variant_id),)
    factory = SimulationRuntimeFactory()
    if config is None:
        return factory.prepare(scenario_path, DATA_DIR, variants)
    return factory.prepare_config(
        config,
        DATA_DIR,
        variants,
        source_label=str(scenario_path.resolve()),
    )


def _build(prepared: PreparedScenario, variant_id: str) -> RuntimeSession:
    return prepared.build(
        variant_id,
        seed=SEED,
        max_ticks=MAX_TICKS,
        engine_config=EngineConfig(
            max_ticks=MAX_TICKS,
            resolution_closing_range_mult=0.0,
        ),
        campaign_config=CampaignConfig(
            engagement_detection_range_m=1.0,
            enable_strategic_movement=False,
            enable_maintenance=False,
            enable_supply_network=False,
        ),
        strict_mode=True,
    )


def test_factory_loaded_zero_blend_retreat_preserves_morale_and_rng() -> None:
    variant_id = "phase113-guerrilla-zero-blend"
    session = SimulationRuntimeFactory().prepare(
        COIN_SCENARIO,
        DATA_DIR,
        (AnalysisVariant(variant_id=variant_id),),
    ).build(
        variant_id,
        seed=68,
        max_ticks=1,
        strict_mode=True,
    )
    ctx = session.context
    guerrilla = next(
        unit for unit in ctx.all_units()
        if unit.unit_type == "insurgent_squad"
    )
    enemy = next(
        unit for unit in ctx.all_units()
        if unit.side != guerrilla.side
    )
    guerrilla.position = Position(1_000.0, 1_000.0, 0.0)
    enemy.position = Position(500.0, 1_000.0, 0.0)
    ctx.unit_weapons[guerrilla.entity_id] = ()
    ctx.unit_weapons[enemy.entity_id] = ()

    assert getattr(ctx, "population_engine", None) is None
    assert ctx.population_manager is not None
    assert not hasattr(ctx.population_manager, "get_density_at")
    combat_rng = ctx.rng_manager.get_stream(ModuleId.COMBAT)
    morale_rng = ctx.rng_manager.get_stream(ModuleId.MORALE)
    assert ctx.unconventional_engine._rng is combat_rng
    combat_before = copy.deepcopy(combat_rng.bit_generator.state)
    morale_before = copy.deepcopy(morale_rng.bit_generator.state)
    record_before = ctx.morale_runtime.record_for(guerrilla.entity_id)
    events: list[Event] = []
    ctx.event_bus.subscribe(Event, events.append)

    manager = BattleManager(ctx.event_bus)
    manager._cumulative_casualties[guerrilla.entity_id] = 4
    pending = manager._execute_engagements(
        ctx,
        {guerrilla.side: [guerrilla], enemy.side: [enemy]},
        {guerrilla.side: [enemy], enemy.side: [guerrilla]},
        {
            guerrilla.side: np.asarray(
                [(enemy.position.easting, enemy.position.northing)],
                dtype=np.float64,
            ),
            enemy.side: np.asarray(
                [(guerrilla.position.easting, guerrilla.position.northing)],
                dtype=np.float64,
            ),
        },
        dt=1.0,
        timestamp=ctx.clock.current_time,
        _unit_index={
            guerrilla.entity_id: guerrilla,
            enemy.entity_id: enemy,
        },
    )

    assert pending == []
    assert guerrilla.position == Position(3_000.0, 1_000.0, 0.0)
    assert guerrilla.status is UnitStatus.ACTIVE
    assert ctx.morale_runtime.record_for(guerrilla.entity_id) is record_before
    assert ctx.morale_states[guerrilla.entity_id] is MoraleState.STEADY
    assert combat_rng.bit_generator.state == combat_before
    assert morale_rng.bit_generator.state == morale_before
    assert events == []


def _melee_config() -> CampaignScenarioConfig:
    return CampaignScenarioConfig.model_validate({
        "name": "Phase 113 melee rout proof",
        "date": "1066-10-14T09:00:00Z",
        "duration_hours": 1.0 / 3600.0,
        "era": "ancient_medieval",
        "tick_resolution": {
            "strategic_s": 3_600.0,
            "operational_s": 300.0,
            "tactical_s": 1.0,
        },
        "weather_conditions": {"visibility_m": 1_000.0},
        "terrain": {
            "width_m": 100.0,
            "height_m": 100.0,
            "cell_size_m": 10.0,
            "base_elevation_m": 0.0,
            "terrain_type": "open_field",
        },
        "sides": [
            {
                "side": "blue",
                "units": [{
                    "unit_type": "swiss_pike_block",
                    "count": 1,
                    "position": [40.0, 50.0],
                }],
                "experience_level": 1.0,
                "morale_initial": "STEADY",
            },
            {
                "side": "red",
                "units": [{
                    "unit_type": "norman_knight_conroi",
                    "count": 1,
                    "position": [40.5, 50.0],
                }],
                "experience_level": 0.5,
                "morale_initial": "STEADY",
            },
        ],
        "victory_conditions": [{
            "type": "time_expired",
            "side": "blue",
            "params": {"max_duration_s": 1.0},
        }],
        "behavior_rules": {
            "blue": {"hold_position": True},
            "red": {"hold_position": True},
        },
        "calibration_overrides": {
            "visibility_m": 1_000.0,
            "destruction_threshold": 0.95,
            "disable_threshold": 0.90,
            "target_selection_mode": "closest",
            "max_engagers_per_side": 1,
            "rout_cascade_base_chance": 0.0,
        },
    })


def _melee_prepared() -> PreparedScenario:
    return SimulationRuntimeFactory().prepare_config(
        _melee_config(),
        DATA_DIR,
        (
            AnalysisVariant(variant_id="phase113-melee-enabled"),
            AnalysisVariant(
                variant_id="phase113-melee-weapons-hold",
                calibration_patch={"roe_level": "WEAPONS_HOLD"},
            ),
        ),
        source_label="phase113-melee-rout-proof",
    )


def _melee_build(
    prepared: PreparedScenario,
    variant_id: str,
) -> RuntimeSession:
    return prepared.build(
        variant_id,
        seed=MELEE_SEED,
        max_ticks=MELEE_MAX_TICKS,
        record_events=True,
        engine_config=EngineConfig(
            max_ticks=MELEE_MAX_TICKS,
            snapshot_interval_ticks=1,
        ),
        campaign_config=CampaignConfig(
            engagement_detection_range_m=10.0,
            enable_strategic_movement=False,
            enable_maintenance=False,
            enable_supply_network=False,
        ),
        battle_config=BattleConfig(
            engagement_range_m=10.0,
            morale_check_interval=12,
        ),
        strict_mode=True,
    )


def _runtime_state(session: RuntimeSession, unit_id: str) -> MoraleState:
    return session.context.morale_runtime.record_for(unit_id).current_state


def _record_payload(record: MoraleStateRecord) -> dict[str, object]:
    return {
        "current_state": int(record.current_state),
        "last_transition_time_s": record.last_transition_time_s,
        "last_check_time_s": record.last_check_time_s,
        "generation": record.generation,
    }


def _base_aggregation_context() -> tuple[
    SimulationContext,
    dict[str, MoraleStateRecord],
]:
    units = [
        Unit(
            entity_id=f"base_{index}",
            position=Position(float(index * 100), 0.0),
            name=f"Base Unit {index}",
            unit_type="base",
            side="blue",
            max_speed=10.0,
        )
        for index in range(3)
    ]
    records = {
        "base_0": MoraleStateRecord(
            MoraleState.BROKEN,
            last_transition_time_s=7.0,
            last_check_time_s=9.0,
            generation=3,
        ),
        "base_1": MoraleStateRecord(
            MoraleState.BROKEN,
            last_transition_time_s=5.0,
            last_check_time_s=8.0,
            generation=2,
        ),
        "base_2": MoraleStateRecord(
            MoraleState.SHAKEN,
            last_transition_time_s=4.0,
            last_check_time_s=4.0,
            generation=1,
        ),
    }
    rng_manager = RNGManager(SEED)
    event_bus = EventBus()
    runtime = MoraleRuntime(
        event_bus,
        rng_manager.get_stream(ModuleId.MORALE),
    )
    units_by_id = {unit.entity_id: unit for unit in units}
    runtime.register_units(
        tuple(
            MoraleRegistration(unit_id, record.current_state)
            for unit_id, record in records.items()
        ),
        units_by_id,
    )
    runtime.set_state(
        {
            "active_records": {
                unit_id: _record_payload(record)
                for unit_id, record in records.items()
            },
            "suspended_archives": {},
        },
        expected_units=units_by_id,
        elapsed_time_s=10.0,
    )
    clock = SimulationClock(
        start=BASE_TIMESTAMP,
        tick_duration=timedelta(seconds=10.0),
    )
    clock.advance()
    aggregation = AggregationEngine(
        AggregationConfig(
            enable_aggregation=True,
            min_units_to_aggregate=2,
        ),
        rng=np.random.default_rng(SEED),
        event_bus=event_bus,
    )
    unit_sides = {unit_id: "blue" for unit_id in sorted(units_by_id)}
    context = SimulationContext(
        config=load_campaign_scenario_config(REINFORCEMENT_SCENARIO),
        clock=clock,
        rng_manager=rng_manager,
        event_bus=event_bus,
        units_by_side={"blue": units},
        unit_weapons={unit_id: () for unit_id in unit_sides},
        unit_sensor_attachments={unit_id: () for unit_id in unit_sides},
        unit_sensors={unit_id: () for unit_id in unit_sides},
        equipment_resolutions={unit_id: () for unit_id in unit_sides},
        tactical_targeting=TacticalTargetingRuntime(
            sensing_aware_standoff_enabled=True,
            unit_sides=unit_sides,
        ),
        morale_runtime=runtime,
        rout_engine=runtime.rout_engine,
        aggregation_engine=aggregation,
    )
    return context, records


def test_loaded_melee_rout_is_enabled_exposed_and_persisted() -> None:
    prepared = _melee_prepared()
    assert prepared.authored_roster == (("blue", 1), ("red", 1))

    enabled = _melee_build(prepared, "phase113-melee-enabled")
    blue = enabled.context.units_by_side["blue"][0]
    red = enabled.context.units_by_side["red"][0]
    blue_attachments = enabled.context.unit_weapons[MELEE_BLUE_ID]
    assert blue.entity_id == MELEE_BLUE_ID
    assert red.entity_id == MELEE_RED_ID
    assert (blue.position.easting, blue.position.northing) == (40.0, 50.0)
    assert (red.position.easting, red.position.northing) == (40.5, 50.0)
    assert len(blue.personnel) == 500
    assert len(red.personnel) == 30
    assert [
        attachment.weapon.definition.weapon_id
        for attachment in blue_attachments
    ] == ["pike"]
    assert [
        ammo.ammo_id
        for attachment in blue_attachments
        for ammo in attachment.ammunition
    ] == ["pike_thrust"]

    result = enabled.run_to_completion()
    assert (
        result.ticks_executed,
        result.duration_s,
        result.victory_result.condition_type,
    ) == (1, 1.0, "time_expired")
    assert enabled.recorder is not None
    engagements = enabled.recorder.events_of_type("EngagementEvent")
    damage = enabled.recorder.events_of_type("DamageEvent")
    transitions = enabled.recorder.events_of_type("MoraleStateChangeEvent")
    assert [
        (
            event.data["attacker_id"],
            event.data["target_id"],
            event.data["weapon_id"],
            event.data["ammo_type"],
        )
        for event in engagements
    ] == [(MELEE_BLUE_ID, MELEE_RED_ID, "pike", "melee")]
    assert [
        (
            event.data["target_id"],
            event.data["damage_type"],
            event.data["damage_amount"],
        )
        for event in damage
    ] == [(MELEE_RED_ID, "melee_casualties", 12.0)]
    assert [
        event.timestamp
        for event in [*engagements, *damage, *transitions]
    ] == [MELEE_EVENT_TIMESTAMP] * 3
    assert [event.data for event in transitions] == [{
        "unit_id": MELEE_RED_ID,
        "old_state": int(MoraleState.STEADY),
        "new_state": int(MoraleState.ROUTED),
        "cause": "melee_rout",
        "logical_time_s": 1.0,
    }]
    assert enabled.recorder.events_of_type("RallyEvent") == []
    record = enabled.context.morale_runtime.record_for(MELEE_RED_ID)
    assert red.status is UnitStatus.ROUTING
    assert enabled.context.morale_states[MELEE_RED_ID] is MoraleState.ROUTED
    assert (
        record.current_state,
        record.last_transition_time_s,
        record.last_check_time_s,
        record.generation,
    ) == (MoraleState.ROUTED, 1.0, 1.0, 1)

    hold = _melee_build(prepared, "phase113-melee-weapons-hold")
    hold_result = hold.run_to_completion()
    assert (hold_result.ticks_executed, hold_result.duration_s) == (1, 1.0)
    assert hold.recorder is not None
    assert hold.recorder.events_of_type("EngagementEvent") == []
    assert hold.recorder.events_of_type("DamageEvent") == []
    assert hold.recorder.events_of_type("MoraleStateChangeEvent") == []
    hold_red = hold.context.units_by_side["red"][0]
    hold_record = hold.context.morale_runtime.record_for(MELEE_RED_ID)
    assert hold_red.status is UnitStatus.ACTIVE
    assert hold.context.morale_states[MELEE_RED_ID] is MoraleState.STEADY
    assert (
        hold_record.current_state,
        hold_record.last_transition_time_s,
        hold_record.last_check_time_s,
        hold_record.generation,
    ) == (MoraleState.STEADY, None, None, 0)

    checkpoint = enabled.engine.checkpoint()
    restored = _melee_build(prepared, "phase113-melee-enabled")
    restored.engine.restore(checkpoint)
    assert restored.context.get_state() == enabled.context.get_state()
    assert restored.recorder is not None
    assert restored.recorder.get_state() == enabled.recorder.get_state()
    assert restored.finalize() == result
    assert restored.context.morale_runtime.record_for(MELEE_RED_ID) == record
    assert restored.context.units_by_side["red"][0].status is UnitStatus.ROUTING

    replay = _melee_build(prepared, "phase113-melee-enabled")
    assert replay.run_to_completion() == result
    assert replay.context.get_state() == enabled.context.get_state()
    assert replay.recorder is not None
    assert replay.recorder.get_state() == enabled.recorder.get_state()


def test_context_rejects_ownerless_nonempty_morale_projection() -> None:
    rng_manager = RNGManager(SEED)
    with pytest.raises(ValueError, match="requires MoraleRuntime"):
        SimulationContext(
            config=load_campaign_scenario_config(REINFORCEMENT_SCENARIO),
            clock=SimulationClock(
                start=BASE_TIMESTAMP,
                tick_duration=timedelta(seconds=10.0),
            ),
            rng_manager=rng_manager,
            event_bus=EventBus(),
            morale_states={"ghost": MoraleState.STEADY},
        )


def test_context_rejects_incomplete_runtime_roster_binding() -> None:
    unit = Unit(entity_id="unbound", position=Position(0.0, 0.0))
    rng_manager = RNGManager(SEED)
    event_bus = EventBus()
    runtime = MoraleRuntime(
        event_bus,
        rng_manager.get_stream(ModuleId.MORALE),
    )
    with pytest.raises(ValueError, match="topology"):
        SimulationContext(
            config=load_campaign_scenario_config(REINFORCEMENT_SCENARIO),
            clock=SimulationClock(
                start=BASE_TIMESTAMP,
                tick_duration=timedelta(seconds=10.0),
            ),
            rng_manager=rng_manager,
            event_bus=event_bus,
            units_by_side={"blue": [unit]},
            morale_runtime=runtime,
            rout_engine=runtime.rout_engine,
        )


def test_context_freezes_and_revalidates_morale_owner_graph() -> None:
    context, _records = _base_aggregation_context()

    for field_name in ("morale_states", "morale_runtime", "rout_engine"):
        with pytest.raises(AttributeError, match="stable MoraleRuntime"):
            setattr(context, field_name, getattr(context, field_name))

    unit_id = next(iter(context.morale_runtime.records))
    context.morale_runtime._units[unit_id] = Unit(
        entity_id=unit_id,
        position=Position(0.0, 0.0),
    )
    with pytest.raises(ValueError, match="unit binding disagrees"):
        context.get_state()


def test_public_bypass_after_reinforcement_updates_single_projection() -> None:
    """A runtime transition updates the post-reinforcement projection."""
    variant_id = "phase113-green-reinforcement-runtime"
    session = _build(
        _prepare(REINFORCEMENT_SCENARIO, variant_id),
        variant_id,
    )
    context = session.context
    initial_ids = {unit.entity_id for unit in context.all_units()}

    assert session.step() is False
    arrived_ids = sorted(
        unit.entity_id
        for unit in context.all_units()
        if unit.entity_id not in initial_ids
    )
    assert arrived_ids == [
        "reinforce_blue_0000_m1a2_0000",
        "reinforce_blue_0000_m1a2_0001",
    ]
    unit_id = arrived_ids[0]

    record_before = context.morale_runtime.record_for(unit_id)
    transitioned = context.morale_runtime.check_transition(
        unit_id=unit_id,
        casualty_rate=1.0,
        suppression_level=1.0,
        leadership_present=False,
        cohesion=0.0,
        force_ratio=0.01,
        timestamp=context.clock.current_time,
        current_time_s=context.clock.elapsed.total_seconds(),
    )

    assert transitioned is MoraleState.SHAKEN
    record_after = context.morale_runtime.record_for(unit_id)
    assert record_after.current_state is transitioned
    assert record_after.generation == record_before.generation + 1
    assert context.morale_states[unit_id] is transitioned, (
        "the stable public view must reflect the post-reinforcement runtime "
        "transition"
    )


def test_real_cascade_checkpoint_restores_through_single_morale_owner() -> None:
    """A real cascade must not create a checkpoint that fresh restore rejects."""
    variant_id = "phase113-green-cascade-restore"
    raw = load_campaign_scenario_config(REINFORCEMENT_SCENARIO).model_dump(
        mode="python",
    )
    raw["calibration_overrides"]["rout_cascade_base_chance"] = 1.0
    raw["calibration_overrides"]["rout_cascade_shaken_susceptibility"] = 2.0
    config = CampaignScenarioConfig.model_validate(raw)
    prepared = _prepare(
        REINFORCEMENT_SCENARIO,
        variant_id,
        config=config,
    )
    source = _build(prepared, variant_id)
    resumed = _build(prepared, variant_id)
    context = source.context
    source_id = "blue_m1a2_0000"
    candidate_id = "blue_m1a2_0001"

    assert source.step() is False
    logical_time_s = context.clock.elapsed.total_seconds()
    timestamp = context.clock.current_time
    assert context.morale_runtime.check_transition(
        candidate_id,
        1.0,
        1.0,
        False,
        0.0,
        0.01,
        timestamp=timestamp,
        current_time_s=logical_time_s,
    ) is MoraleState.SHAKEN
    assert context.morale_runtime.force_transition(
        source_id,
        MoraleState.ROUTED,
        cause=MoraleTransitionCause.MELEE_ROUT,
        timestamp=timestamp,
        current_time_s=logical_time_s,
    ) is MoraleState.ROUTED
    source_unit = next(
        unit
        for unit in context.all_units()
        if unit.entity_id == source_id
    )
    candidate = next(
        unit for unit in context.all_units() if unit.entity_id == candidate_id
    )
    assert source_unit.status is UnitStatus.ROUTING
    assert candidate.status is UnitStatus.ACTIVE

    active_enemies, _ = source.engine.battle_manager._build_enemy_data(
        context.units_by_side,
    )
    source.engine.battle_manager._execute_morale(
        context,
        context.units_by_side,
        active_enemies,
        context.clock.current_time,
    )

    assert candidate.status is UnitStatus.ROUTING
    assert context.morale_states[candidate_id] is MoraleState.ROUTED
    source_morale = copy.deepcopy(context.morale_runtime.get_state())
    checkpoint = source.engine.checkpoint()

    resumed.engine.restore(checkpoint)

    assert resumed.context.morale_states[candidate_id] is MoraleState.ROUTED
    assert _runtime_state(resumed, candidate_id) is MoraleState.ROUTED
    assert resumed.context.morale_runtime.get_state() == source_morale


def test_aggregation_checkpoint_restores_one_exact_morale_topology() -> None:
    """A fresh base-unit restore preserves the sole morale archive exactly."""
    source, original_records = _base_aggregation_context()
    constituent_ids = sorted(original_records)

    aggregate = source.aggregation_engine.aggregate(constituent_ids, source)

    assert aggregate is not None
    assert aggregate.aggregate_id == "agg_0000"
    for owner in (
        source.unit_weapons,
        source.unit_sensor_attachments,
        source.unit_sensors,
        source.equipment_resolutions,
    ):
        assert owner == {"agg_0000": ()}
    assert dict(source.tactical_targeting.registered_unit_sides) == {
        "agg_0000": "blue",
    }
    checkpoint = source.get_state()
    source_morale = copy.deepcopy(source.morale_runtime.get_state())
    source_aggregation = copy.deepcopy(source.aggregation_engine.get_state())
    resumed, _ = _base_aggregation_context()

    resumed.set_state(checkpoint)

    roster_ids = {unit.entity_id for unit in resumed.all_units()}
    assert roster_ids == set(resumed.morale_states) == {"agg_0000"}
    assert resumed.morale_runtime.get_state() == source_morale
    assert resumed.aggregation_engine.get_state() == source_aggregation
    for owner in (
        resumed.unit_weapons,
        resumed.unit_sensor_attachments,
        resumed.unit_sensors,
        resumed.equipment_resolutions,
    ):
        assert owner == {"agg_0000": ()}
    assert dict(resumed.tactical_targeting.registered_unit_sides) == {
        "agg_0000": "blue",
    }
    archive = source_morale["suspended_archives"]["agg_0000"]
    assert archive["constituent_records"] == {
        unit_id: _record_payload(record)
        for unit_id, record in original_records.items()
    }

    assert resumed.aggregation_engine.disaggregate(
        "agg_0000",
        resumed,
    ) == constituent_ids
    assert dict(resumed.morale_runtime.records) == original_records
    assert resumed.morale_runtime.get_state()["suspended_archives"] == {}
    for owner in (
        resumed.unit_weapons,
        resumed.unit_sensor_attachments,
        resumed.unit_sensors,
        resumed.equipment_resolutions,
    ):
        assert owner == {unit_id: () for unit_id in constituent_ids}
    assert dict(resumed.tactical_targeting.registered_unit_sides) == {
        unit_id: "blue" for unit_id in constituent_ids
    }


def test_active_aggregate_checkpoint_rejects_ato_owner_atomically() -> None:
    source, original_records = _base_aggregation_context()
    aggregate = source.aggregation_engine.aggregate(
        sorted(original_records),
        source,
    )
    assert aggregate is not None
    checkpoint = copy.deepcopy(source.get_state())
    source.ato_engine = ATOPlanningEngine(source.event_bus)
    source.ato_engine.register_aircraft(
        AircraftAvailability(unit_id="base_0"),
    )
    with pytest.raises(ValueError, match="ato_engine"):
        source.get_state()
    checkpoint["ato_engine"] = copy.deepcopy(source.ato_engine.get_state())

    target, _ = _base_aggregation_context()
    target.ato_engine = ATOPlanningEngine(target.event_bus)
    before = copy.deepcopy(target.get_state())

    with pytest.raises(ValueError, match="ato_engine"):
        target.set_state(checkpoint)

    assert target.get_state() == before


@pytest.mark.parametrize(
    "owner_mutation",
    ("missing", "forged", "subclass", "disabled", "config_mismatch"),
)
def test_active_aggregate_checkpoint_requires_enabled_owner_atomically(
    owner_mutation: str,
) -> None:
    source, original_records = _base_aggregation_context()
    aggregate = source.aggregation_engine.aggregate(
        sorted(original_records),
        source,
    )
    assert aggregate is not None
    checkpoint = copy.deepcopy(source.get_state())

    target, _ = _base_aggregation_context()
    if owner_mutation == "missing":
        target.aggregation_engine = None
        error_match = "exact AggregationEngine runtime owner"
    elif owner_mutation == "forged":
        target.aggregation_engine = SimpleNamespace(
            config=AggregationConfig(
                enable_aggregation=True,
                min_units_to_aggregate=2,
            ),
        )
        error_match = "exact AggregationEngine runtime owner"
    elif owner_mutation == "subclass":
        class ForgedAggregationEngine(AggregationEngine):
            pass

        target.aggregation_engine = ForgedAggregationEngine(
            AggregationConfig(
                enable_aggregation=True,
                min_units_to_aggregate=2,
            ),
            rng=np.random.default_rng(SEED),
            event_bus=target.event_bus,
        )
        error_match = "exact AggregationEngine runtime owner"
    elif owner_mutation == "disabled":
        target.aggregation_engine = AggregationEngine(
            AggregationConfig(enable_aggregation=False),
            rng=np.random.default_rng(SEED),
            event_bus=target.event_bus,
        )
        error_match = "requires an enabled aggregation runtime owner"
    else:
        target.aggregation_engine = AggregationEngine(
            AggregationConfig(
                enable_aggregation=True,
                min_units_to_aggregate=3,
            ),
            rng=np.random.default_rng(SEED),
            event_bus=target.event_bus,
        )
        error_match = "config does not match"
    before_clock = copy.deepcopy(target.clock.get_state())
    before_rng = copy.deepcopy(target.rng_manager.get_state())
    before_units = copy.deepcopy({
        side: [unit.get_state() for unit in units]
        for side, units in target.units_by_side.items()
    })
    before_morale = copy.deepcopy(target.morale_runtime.get_state())
    before_targeting = copy.deepcopy(target.tactical_targeting.get_state())

    with pytest.raises(ValueError, match=error_match):
        target.set_state(checkpoint)

    assert target.clock.get_state() == before_clock
    assert target.rng_manager.get_state() == before_rng
    assert {
        side: [unit.get_state() for unit in units]
        for side, units in target.units_by_side.items()
    } == before_units
    assert target.morale_runtime.get_state() == before_morale
    assert target.tactical_targeting.get_state() == before_targeting


@pytest.mark.parametrize(
    ("mutation", "error_match"),
    (
        ("negative_next_id", "next_id"),
        ("nonfinite_constituent", "finite numbers"),
        ("unrestorable_index", "proxy/order"),
        ("proxy_domain", "roster proxy"),
    ),
)
def test_aggregation_checkpoint_rejects_nested_corruption_atomically(
    mutation: str,
    error_match: str,
) -> None:
    source, original_records = _base_aggregation_context()
    aggregate = source.aggregation_engine.aggregate(
        sorted(original_records),
        source,
    )
    assert aggregate is not None
    invalid = copy.deepcopy(source.get_state())
    raw_aggregation = invalid["aggregation_engine"]
    snapshots = raw_aggregation["aggregates"][aggregate.aggregate_id][
        "snapshots"
    ]
    if mutation == "negative_next_id":
        raw_aggregation["next_id"] = -1
    elif mutation == "nonfinite_constituent":
        position = list(snapshots[0]["unit_state"]["position"])
        position[0] = float("inf")
        snapshots[0]["unit_state"]["position"] = position
    elif mutation == "unrestorable_index":
        snapshots[0]["original_index"] = 99
    else:
        invalid["units_by_side"]["blue"][0]["domain"] = int(Domain.AERIAL)

    target, _ = _base_aggregation_context()
    before = copy.deepcopy(target.get_state())

    with pytest.raises(ValueError, match=error_match):
        target.set_state(invalid)

    assert target.get_state() == before


def test_aggregation_checkpoint_rejects_suspended_status_disagreement_atomically(
) -> None:
    source, original_records = _base_aggregation_context()
    constituent_ids = sorted(original_records)
    aggregate = source.aggregation_engine.aggregate(constituent_ids, source)
    assert aggregate is not None
    invalid = copy.deepcopy(source.get_state())
    snapshots = invalid["aggregation_engine"]["aggregates"][
        aggregate.aggregate_id
    ]["snapshots"]
    assert snapshots[0]["unit_state"]["status"] == int(UnitStatus.ACTIVE)
    snapshots[0]["unit_state"]["status"] = int(UnitStatus.ROUTING)

    target, _ = _base_aggregation_context()
    before = target.get_state()
    with pytest.raises(ValueError, match="suspended morale/status disagree"):
        target.set_state(invalid)

    assert target.get_state() == before


@pytest.mark.parametrize(
    "field,value",
    (
        ("weapon_states", [{}]),
        ("sensor_states", [{}]),
        ("supply_inventory", {}),
        ("order_records", [{}]),
        ("original_side", "red"),
    ),
)
def test_aggregation_checkpoint_rejects_unsupported_snapshot_atomically(
    field: str,
    value: object,
) -> None:
    source, original_records = _base_aggregation_context()
    aggregate = source.aggregation_engine.aggregate(
        sorted(original_records),
        source,
    )
    assert aggregate is not None
    invalid = copy.deepcopy(source.get_state())
    invalid["aggregation_engine"]["aggregates"][
        aggregate.aggregate_id
    ]["snapshots"][0][field] = value

    target, _ = _base_aggregation_context()
    before = target.get_state()
    with pytest.raises(ValueError, match="REM-016"):
        target.set_state(invalid)

    assert target.get_state() == before


def test_aggregate_checkpoint_rejects_builder_owner_before_build_atomically(
) -> None:
    source, original_records = _base_aggregation_context()
    aggregate = source.aggregation_engine.aggregate(
        sorted(original_records),
        source,
    )
    assert aggregate is not None
    checkpoint = source.get_state()

    target, _ = _base_aggregation_context()
    before = target.get_state()

    class _ForbiddenBuilder:
        era_config = target._captured_era_config()

        @staticmethod
        def fingerprint() -> None:
            return None

        @staticmethod
        def build(_units: object) -> object:
            raise AssertionError("aggregate checkpoint reached loadout build")

    target.loadout_builder = _ForbiddenBuilder()  # type: ignore[assignment]
    with pytest.raises(ValueError, match="REM-016.*loadout_builder"):
        target.set_state(checkpoint)

    assert target.get_state() == before


def test_machine_rout_changes_production_morale_collapsed_outcome() -> None:
    """Authoritative routed records terminate; a SHAKEN control does not."""
    routed_variant = "phase113-green-morale-collapsed"
    routed = _build(
        _prepare(GOOSE_GREEN_SCENARIO, routed_variant),
        routed_variant,
    )
    control_variant = "phase113-green-morale-shaken-control"
    control = _build(
        _prepare(GOOSE_GREEN_SCENARIO, control_variant),
        control_variant,
    )
    routed_context = routed.context
    red_ids = [
        unit.entity_id
        for unit in routed_context.units_by_side["red"]
    ]
    for unit_id in red_ids:
        assert routed_context.morale_runtime.force_transition(
            unit_id,
            MoraleState.ROUTED,
            cause=MoraleTransitionCause.MELEE_ROUT,
            timestamp=routed_context.clock.current_time,
            current_time_s=0.0,
        ) is MoraleState.ROUTED

    assert all(
        _runtime_state(routed, unit_id) is MoraleState.ROUTED
        and routed_context.morale_states[unit_id] is MoraleState.ROUTED
        for unit_id in red_ids
    )
    assert routed.step() is True
    assert routed.engine._last_victory.condition_type == "morale_collapsed"

    control_ids = [
        unit.entity_id
        for unit in control.context.units_by_side["red"]
    ]
    assert all(
        _runtime_state(control, unit_id) is MoraleState.SHAKEN
        for unit_id in control_ids
    )
    assert control.step() is False
    assert control.engine._last_victory.game_over is False


def test_ordinary_battle_uses_logical_time_for_second_morale_check() -> None:
    """A second ordinary check after cooldown must consume its morale draw."""
    variant_id = "phase113-green-battle-logical-time"
    session = _build(
        _prepare(REINFORCEMENT_SCENARIO, variant_id),
        variant_id,
    )
    context = session.context
    target_id = "blue_m1a2_0000"
    target = next(
        unit for unit in context.all_units() if unit.entity_id == target_id
    )
    for unit in context.all_units():
        if unit is not target:
            object.__setattr__(unit, "status", UnitStatus.DESTROYED)
    active_enemies, _ = session.engine.battle_manager._build_enemy_data(
        context.units_by_side,
    )

    context.clock.set_tick_duration(timedelta(seconds=1.0))
    context.clock.advance()
    session.engine.battle_manager._execute_morale(
        context,
        context.units_by_side,
        active_enemies,
        context.clock.current_time,
    )
    assert context.morale_states[target_id] is MoraleState.SHAKEN
    first_record = context.morale_runtime.record_for(target_id)
    assert first_record.current_state is MoraleState.SHAKEN
    assert first_record.last_check_time_s == 1.0
    assert first_record.generation == 1

    context.clock.set_tick_duration(timedelta(seconds=31.0))
    context.clock.advance()
    morale_rng = context.rng_manager.get_stream(ModuleId.MORALE)
    before_second_rng = copy.deepcopy(morale_rng.bit_generator.state)

    session.engine.battle_manager._execute_morale(
        context,
        context.units_by_side,
        active_enemies,
        context.clock.current_time,
    )
    second_record = context.morale_runtime.record_for(target_id)
    after_second_rng = copy.deepcopy(morale_rng.bit_generator.state)

    assert second_record.current_state is MoraleState.STEADY
    assert context.morale_states[target_id] is second_record.current_state
    assert second_record.last_check_time_s == 32.0
    assert second_record.last_transition_time_s == 32.0
    assert second_record.generation == first_record.generation + 1
    assert after_second_rng != before_second_rng
