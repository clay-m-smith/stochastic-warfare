"""Phase 108 behavioral tests for production logistics wiring.

The compatibility seeding helper is intentionally limited to tests whose
subject is the engine loop or checkpoint protocol.  Loader behavior has its
own test and must materialize the configured topology without that helper.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.environment.seasons import GroundState
from stochastic_warfare.entities.base import UnitStatus
from stochastic_warfare.logistics.events import (
    SupplyDepletedEvent,
    SupplyDeliveredEvent,
)
from stochastic_warfare.logistics.runtime import logistics_ground_state_code
from stochastic_warfare.logistics.stockpile import DepotType
from stochastic_warfare.logistics.supply_classes import (
    SupplyClass,
    SupplyInventory,
)
from stochastic_warfare.logistics.supply_network import TransportMode
from stochastic_warfare.simulation.campaign import CampaignConfig
from stochastic_warfare.simulation.engine import EngineConfig, SimulationEngine
from stochastic_warfare.simulation.recorder import SimulationRecorder
from stochastic_warfare.simulation.scenario import (
    CampaignScenarioConfig,
    ScenarioLoader,
    SimulationContext,
    VictoryConditionConfig,
    load_campaign_scenario_config,
)
from stochastic_warfare.simulation.victory import (
    VictoryDeclaredEvent,
    VictoryEvaluator,
    VictoryEvaluatorConfig,
)
from stochastic_warfare.tools.serializers import serialize_to_dict


DATA_DIR = Path("data")
LOGISTICS_SCENARIO = Path(
    "data/scenarios/test_campaign_logistics/scenario.yaml",
)
LEGACY_SCENARIO = Path("data/scenarios/test_campaign/scenario.yaml")

CLASS_I = int(SupplyClass.CLASS_I)
UNIT_ID = "blue_m1a2_0000"
DEPOT_ID = "blue_depot"
ITEM_ID = "water_potable"


def _item(quantity: float, *, item_id: str = ITEM_ID) -> dict[str, Any]:
    return {
        "supply_class": "CLASS_I",
        "item_id": item_id,
        "quantity": quantity,
    }


def _enabled_payload() -> dict[str, Any]:
    payload = load_campaign_scenario_config(
        LOGISTICS_SCENARIO,
    ).model_dump(mode="python")
    payload["duration_hours"] = 48.0
    payload["tick_duration_seconds"] = 3600.0
    payload["victory_conditions"] = []
    payload["reinforcements"] = []
    payload["sides"][0]["units"] = [{"unit_type": "m1a2", "count": 1}]
    payload["sides"][1]["units"] = [{"unit_type": "m1a2", "count": 1}]
    payload["sides"][0]["depots"] = [
        {
            "depot_id": DEPOT_ID,
            "position": [0.0, 7500.0],
            "depot_type": "DEPOT",
            "condition": 1.0,
            "capacity_tons": 100.0,
            "throughput_tons_per_hour": 100.0,
            "initial_inventory": [_item(10.0)],
        },
    ]
    payload["sides"][1]["depots"] = []
    payload["logistics"] = {
        "enabled": True,
        "update_interval_seconds": 3600.0,
        "unit_profiles": [
            {
                "side": "blue",
                "unit_type": "m1a2",
                "initial_inventory": [_item(1.0)],
                "maximum_inventory": [_item(4.0)],
                "idle_consumption_per_hour": [_item(1.0)],
            },
            {
                "side": "red",
                "unit_type": "m1a2",
                "initial_inventory": [_item(4.0)],
                "maximum_inventory": [_item(4.0)],
                "idle_consumption_per_hour": [_item(1.0)],
            },
        ],
        "route_templates": [
            {
                "route_id": "blue_water",
                "side": "blue",
                "depot_id": DEPOT_ID,
                "unit_types": ["m1a2"],
                "transport_mode": "ROAD",
                "transport_speed_kph": 40.0,
                "capacity_tons_per_hour": 10.0,
                "condition": 1.0,
            },
        ],
    }
    return payload


def _enabled_config() -> CampaignScenarioConfig:
    return CampaignScenarioConfig.model_validate(_enabled_payload())


def _load_enabled(*, seed: int = 108) -> SimulationContext:
    return ScenarioLoader(DATA_DIR).load(
        LOGISTICS_SCENARIO,
        seed=seed,
        scenario_config=_enabled_config(),
    )


def _load_payload(
    payload: dict[str, Any],
    *,
    seed: int = 108,
) -> SimulationContext:
    return ScenarioLoader(DATA_DIR).load(
        LOGISTICS_SCENARIO,
        seed=seed,
        scenario_config=CampaignScenarioConfig.model_validate(payload),
    )


def _quiet_campaign(
    *,
    enable_supply_network: bool = True,
) -> CampaignConfig:
    return CampaignConfig(
        engagement_detection_range_m=1.0,
        enable_maintenance=False,
        enable_strategic_movement=False,
        enable_supply_network=enable_supply_network,
    )


def _engine_for(
    payload: dict[str, Any],
    *,
    seed: int = 108,
    enable_supply_network: bool = True,
    victory_evaluator: VictoryEvaluator | None = None,
) -> tuple[SimulationContext, SimulationEngine]:
    ctx = _load_payload(payload, seed=seed)
    engine = SimulationEngine(
        ctx,
        config=EngineConfig(resolution_closing_range_mult=0.0),
        campaign_config=_quiet_campaign(
            enable_supply_network=enable_supply_network,
        ),
        victory_evaluator=victory_evaluator,
    )
    return ctx, engine


def _inventory_quantity(
    inventory: SupplyInventory,
    item_id: str = ITEM_ID,
) -> float:
    return inventory.available(CLASS_I, item_id)


def _maximum_quantity(
    state: dict[str, Any],
    unit_id: str = UNIT_ID,
) -> float:
    maximum = state["unit_max_supplies"][unit_id]
    class_bucket = maximum.get(CLASS_I, maximum.get(str(CLASS_I)))
    assert class_bucket is not None
    return class_bucket[ITEM_ID]


def _unit_quantity(
    ctx: SimulationContext,
    unit_id: str = UNIT_ID,
) -> float:
    return _inventory_quantity(
        ctx.stockpile_manager.get_unit_inventory(unit_id),
    )


def _depot_quantity(
    ctx: SimulationContext,
    depot_id: str = DEPOT_ID,
) -> float:
    return _inventory_quantity(
        ctx.stockpile_manager.get_depot(depot_id).inventory,
    )


def _delivery_signature(
    events: list[SupplyDeliveredEvent],
) -> tuple[tuple[Any, ...], ...]:
    return tuple(
        (
            event.timestamp.isoformat(),
            event.recipient_id,
            event.supply_class,
            event.item_id,
            event.quantity,
            event.quantity_tons,
            event.depot_id,
            event.route_id,
            event.transport_mode,
        )
        for event in events
    )


def _run_with_deliveries(
    payload: dict[str, Any],
    *,
    steps: int = 1,
    seed: int = 108,
    enable_supply_network: bool = True,
) -> tuple[
    SimulationContext,
    SimulationEngine,
    list[SupplyDeliveredEvent],
]:
    ctx, engine = _engine_for(
        payload,
        seed=seed,
        enable_supply_network=enable_supply_network,
    )
    delivered: list[SupplyDeliveredEvent] = []
    ctx.event_bus.subscribe(SupplyDeliveredEvent, delivered.append)
    for _ in range(steps):
        assert engine.step() is False
    return ctx, engine, delivered


def _network_ids(
    ctx: SimulationContext,
) -> tuple[str, str, str]:
    state = ctx.supply_network_engine.get_state()
    depot_node_id = next(
        node_id
        for node_id, node in state["nodes"].items()
        if node.get("node_type") == "DEPOT"
        and node.get("linked_id") == DEPOT_ID
    )
    unit_node_id = next(
        node_id
        for node_id, node in state["nodes"].items()
        if node.get("node_type") == "UNIT"
        and node.get("linked_id") == UNIT_ID
    )
    route_id = next(
        route_id
        for route_id, route in state["routes"].items()
        if route["from_node"] == depot_node_id
        and route["to_node"] == unit_node_id
    )
    return depot_node_id, unit_node_id, route_id


def test_valid_logistics_contract_is_retained_as_typed_configuration() -> None:
    config = _enabled_config()

    logistics = getattr(config, "logistics", None)
    assert logistics is not None
    assert logistics.enabled is True
    assert logistics.update_interval_seconds == pytest.approx(3600.0)
    assert len(logistics.unit_profiles) == 2
    assert len(logistics.route_templates) == 1


@pytest.mark.parametrize(
    "location",
    ["root", "logistics", "profile", "route", "depot"],
)
def test_logistics_contract_rejects_behavior_changing_typos(
    location: str,
) -> None:
    payload = _enabled_payload()
    if location == "root":
        payload["logistcs"] = payload.pop("logistics")
        typo = "logistcs"
    elif location == "logistics":
        payload["logistics"]["update_interval_second"] = (
            payload["logistics"].pop("update_interval_seconds")
        )
        typo = "update_interval_second"
    elif location == "profile":
        profile = payload["logistics"]["unit_profiles"][0]
        profile["idle_consumption_per_hours"] = profile.pop(
            "idle_consumption_per_hour",
        )
        typo = "idle_consumption_per_hours"
    elif location == "route":
        route = payload["logistics"]["route_templates"][0]
        route["transport_speed_kphs"] = route.pop("transport_speed_kph")
        typo = "transport_speed_kphs"
    else:
        depot = payload["sides"][0]["depots"][0]
        depot["conditoin"] = depot.pop("condition")
        typo = "conditoin"

    with pytest.raises(ValidationError, match=typo):
        CampaignScenarioConfig.model_validate(payload)


def test_logistics_contract_rejects_known_root_logisitics_typo() -> None:
    payload = _enabled_payload()
    payload["logisitics"] = payload.pop("logistics")

    with pytest.raises(ValidationError, match="logisitics"):
        CampaignScenarioConfig.model_validate(payload)


def test_unrelated_legacy_root_metadata_is_not_a_logistics_typo() -> None:
    payload = _enabled_payload()
    payload["linguistics"] = {"language": "en"}

    config = CampaignScenarioConfig.model_validate(payload)

    assert config.logistics.enabled is True


@pytest.mark.parametrize(
    ("case", "match"),
    [
        ("zero_interval", "update_interval_seconds"),
        ("initial_above_maximum", "initial_inventory"),
        ("missing_enabled_depot_type", "depot_type"),
    ],
)
def test_logistics_contract_rejects_invalid_enabled_semantics(
    case: str,
    match: str,
) -> None:
    payload = _enabled_payload()
    if case == "zero_interval":
        payload["logistics"]["update_interval_seconds"] = 0.0
    elif case == "initial_above_maximum":
        payload["logistics"]["unit_profiles"][0][
            "initial_inventory"
        ][0]["quantity"] = 5.0
    else:
        payload["sides"][0]["depots"][0].pop("depot_type")

    with pytest.raises(ValidationError, match=match):
        CampaignScenarioConfig.model_validate(payload)


def test_loader_rejects_unknown_configured_supply_item() -> None:
    payload = _enabled_payload()
    unknown_item = "not_a_catalogued_supply_item"
    for inventory_name in (
        "initial_inventory",
        "maximum_inventory",
        "idle_consumption_per_hour",
    ):
        payload["logistics"]["unit_profiles"][0][inventory_name][0][
            "item_id"
        ] = unknown_item
    payload["sides"][0]["depots"][0]["initial_inventory"][0][
        "item_id"
    ] = unknown_item
    config = CampaignScenarioConfig.model_validate(payload)

    with pytest.raises(ValueError, match=unknown_item):
        ScenarioLoader(DATA_DIR).load(
            LOGISTICS_SCENARIO,
            seed=108,
            scenario_config=config,
        )


def test_loader_materializes_exact_enabled_logistics_topology() -> None:
    ctx = _load_enabled()

    runtime = getattr(ctx, "logistics_runtime", None)
    assert runtime is not None

    depot = ctx.stockpile_manager.get_depot(DEPOT_ID)
    assert depot.side == "blue"
    assert depot.depot_type is DepotType.DEPOT
    assert depot.condition == pytest.approx(1.0)
    assert _inventory_quantity(depot.inventory) == pytest.approx(10.0)

    unit_inventory = ctx.stockpile_manager.get_unit_inventory(UNIT_ID)
    assert _inventory_quantity(unit_inventory) == pytest.approx(1.0)
    stockpile_state = ctx.stockpile_manager.get_state()
    assert _maximum_quantity(stockpile_state) == pytest.approx(4.0)

    network_state = ctx.supply_network_engine.get_state()
    assert ctx.supply_network_engine.node_count() == 3
    assert ctx.supply_network_engine.route_count() == 1
    _network_ids(ctx)

    replay = _load_enabled()
    assert replay.stockpile_manager.get_state() == stockpile_state
    assert replay.supply_network_engine.get_state() == network_state


def test_enabled_fixture_starts_outside_tactical_engagement_range() -> None:
    ctx = _load_enabled(seed=108)
    separation = min(
        math.dist(blue.position, red.position)
        for blue in ctx.units_by_side["blue"]
        for red in ctx.units_by_side["red"]
    )

    assert separation > 15_000.0


def test_production_tick_resupplies_then_applies_explicit_idle_consumption(
) -> None:
    ctx = _load_enabled()
    _network_ids(ctx)
    delivered: list[SupplyDeliveredEvent] = []
    ctx.event_bus.subscribe(SupplyDeliveredEvent, delivered.append)
    engine = SimulationEngine(
        ctx,
        config=EngineConfig(resolution_closing_range_mult=0.0),
        campaign_config=_quiet_campaign(),
    )

    before_total = (
        _inventory_quantity(ctx.stockpile_manager.get_depot(DEPOT_ID).inventory)
        + _inventory_quantity(
            ctx.stockpile_manager.get_unit_inventory(UNIT_ID),
        )
    )

    assert engine.step() is False

    unit_after = _inventory_quantity(
        ctx.stockpile_manager.get_unit_inventory(UNIT_ID),
    )
    depot_after = _inventory_quantity(
        ctx.stockpile_manager.get_depot(DEPOT_ID).inventory,
    )
    assert unit_after == pytest.approx(3.0)
    assert depot_after == pytest.approx(7.0)
    assert before_total - (unit_after + depot_after) == pytest.approx(1.0)
    assert sum(
        event.quantity
        for event in delivered
        if event.recipient_id == UNIT_ID
    ) == pytest.approx(3.0)


def test_delivery_provenance_reaches_recorder_and_api_serializer() -> None:
    ctx = _load_enabled(seed=1_108)
    recorder = SimulationRecorder(ctx.event_bus)
    recorder.start()
    engine = SimulationEngine(
        ctx,
        config=EngineConfig(resolution_closing_range_mult=0.0),
        campaign_config=_quiet_campaign(),
        recorder=recorder,
    )

    assert engine.step() is False

    recorded = recorder.events_of_type("SupplyDeliveredEvent")
    assert len(recorded) == 1
    event = recorded[0]
    assert event.source == ModuleId.LOGISTICS.value
    assert event.data == {
        "recipient_id": UNIT_ID,
        "supply_class": CLASS_I,
        "quantity": pytest.approx(3.0),
        "transport_mode": int(TransportMode.ROAD),
        "depot_id": DEPOT_ID,
        "item_id": ITEM_ID,
        "route_id": f"blue_water:{UNIT_ID}",
        "quantity_tons": pytest.approx(0.003),
    }

    api_event = serialize_to_dict(event)
    assert api_event["event_type"] == "SupplyDeliveredEvent"
    assert api_event["source"] == ModuleId.LOGISTICS.value
    assert api_event["data"] == event.data
    json.dumps(api_event, allow_nan=False)
    json.dumps(recorder.get_state(), allow_nan=False)
    recorder.stop()


@pytest.mark.parametrize("control", ["no_route", "zero_condition"])
def test_unusable_route_blocks_delivery_without_blocking_idle_consumption(
    control: str,
) -> None:
    payload = _enabled_payload()
    if control == "no_route":
        payload["logistics"]["route_templates"] = []
    else:
        payload["logistics"]["route_templates"][0]["condition"] = 0.0

    ctx, _, delivered = _run_with_deliveries(payload)

    assert _unit_quantity(ctx) == pytest.approx(0.0)
    assert _depot_quantity(ctx) == pytest.approx(10.0)
    assert delivered == []


@pytest.mark.parametrize(
    ("transport_mode", "active_blockade", "effectiveness", "expected_condition"),
    [
        ("SEA", True, 0.5, 0.5),
        ("ROAD", True, 0.5, 1.0),
        ("SEA", False, 0.5, 1.0),
    ],
)
def test_production_runtime_applies_blockade_only_to_sea_routes(
    monkeypatch: pytest.MonkeyPatch,
    transport_mode: str,
    active_blockade: bool,
    effectiveness: float,
    expected_condition: float,
) -> None:
    payload = _enabled_payload()
    payload["logistics"]["route_templates"][0][
        "transport_mode"
    ] = transport_mode
    ctx, engine = _engine_for(payload, seed=1_608)
    blockade = SimpleNamespace(
        blockade_id="phase-108-blockade",
        sea_zone_ids=["zone-a"],
    )
    monkeypatch.setattr(
        ctx.disruption_engine,
        "active_blockades",
        lambda: [blockade] if active_blockade else [],
    )
    monkeypatch.setattr(
        ctx.disruption_engine,
        "check_blockade",
        lambda _zone_id: effectiveness,
    )
    _, _, route_id = _network_ids(ctx)

    assert engine.step() is False

    assert ctx.supply_network_engine.get_route(
        route_id,
    ).condition == pytest.approx(expected_condition)


@pytest.mark.parametrize(
    ("bottleneck", "capacity_tons", "expected_quantity"),
    [
        ("route", 0.002, 2.0),
        ("depot", 0.001, 1.0),
    ],
)
def test_delivery_obeys_exact_route_and_depot_mass_capacity(
    bottleneck: str,
    capacity_tons: float,
    expected_quantity: float,
) -> None:
    payload = _enabled_payload()
    route = payload["logistics"]["route_templates"][0]
    route["transport_mode"] = "AIR"
    if bottleneck == "route":
        route["capacity_tons_per_hour"] = capacity_tons
    else:
        payload["sides"][0]["depots"][0][
            "throughput_tons_per_hour"
        ] = capacity_tons

    ctx, _, delivered = _run_with_deliveries(payload)

    blue_events = [
        event for event in delivered if event.recipient_id == UNIT_ID
    ]
    assert len(blue_events) == 1
    assert blue_events[0].quantity == pytest.approx(expected_quantity)
    assert blue_events[0].quantity_tons == pytest.approx(
        expected_quantity / 1000.0,
    )
    assert _unit_quantity(ctx) == pytest.approx(expected_quantity)
    assert _depot_quantity(ctx) == pytest.approx(
        10.0 - expected_quantity,
    )
    _, _, route_id = _network_ids(ctx)
    route_state = ctx.supply_network_engine.get_route(route_id)
    assert route_state.current_flow_tons_per_hour == pytest.approx(
        expected_quantity / 1000.0,
    )


def test_subscriber_exception_commits_once_and_retry_advances_next_tick(
) -> None:
    ctx, engine = _engine_for(_enabled_payload(), seed=2_008)
    healthy_checkpoint = engine.checkpoint()
    observed: list[SupplyDeliveredEvent] = []
    failed: list[SupplyDeliveredEvent] = []
    tail: list[SupplyDeliveredEvent] = []

    def fail_after_observation(event: SupplyDeliveredEvent) -> None:
        failed.append(event)
        raise RuntimeError("phase-108 subscriber failure")

    ctx.event_bus.subscribe(
        SupplyDeliveredEvent,
        observed.append,
        priority=-10,
    )
    ctx.event_bus.subscribe(
        SupplyDeliveredEvent,
        fail_after_observation,
        priority=0,
    )
    ctx.event_bus.subscribe(
        SupplyDeliveredEvent,
        tail.append,
        priority=10,
    )

    with pytest.raises(ExceptionGroup) as exc_info:
        engine.step()
    assert len(exc_info.value.exceptions) == 1
    subscriber_error = exc_info.value.exceptions[0]
    assert isinstance(subscriber_error, RuntimeError)
    assert str(subscriber_error) == "phase-108 subscriber failure"

    assert ctx.clock.tick_count == 1
    assert ctx.clock.elapsed.total_seconds() == pytest.approx(3600.0)
    assert _unit_quantity(ctx) == pytest.approx(3.0)
    assert _depot_quantity(ctx) == pytest.approx(7.0)
    assert ctx.logistics_runtime.get_state()[
        "elapsed_accumulator_seconds"
    ] == pytest.approx(0.0)
    assert ctx.logistics_runtime.get_state()[
        "unit_last_accounted_seconds"
    ][UNIT_ID] == pytest.approx(3600.0)
    assert [event.quantity for event in observed] == pytest.approx([3.0])
    assert [event.quantity for event in failed] == pytest.approx([3.0])
    assert [event.quantity for event in tail] == pytest.approx([3.0])

    ctx.event_bus.unsubscribe(
        SupplyDeliveredEvent,
        fail_after_observation,
    )
    with pytest.raises(ExceptionGroup) as retry_error:
        engine.step()
    assert retry_error.value is exc_info.value
    with pytest.raises(ExceptionGroup) as checkpoint_error:
        engine.checkpoint()
    assert checkpoint_error.value is exc_info.value
    assert ctx.clock.tick_count == 1
    assert _unit_quantity(ctx) == pytest.approx(3.0)
    assert _depot_quantity(ctx) == pytest.approx(7.0)
    assert [event.quantity for event in observed] == pytest.approx([3.0])
    assert [event.quantity for event in failed] == pytest.approx([3.0])
    assert [event.quantity for event in tail] == pytest.approx([3.0])

    retry_ctx, retry_engine = _engine_for(
        _enabled_payload(),
        seed=2_008,
    )
    retry_engine.restore(healthy_checkpoint)
    retry_events: list[SupplyDeliveredEvent] = []
    retry_ctx.event_bus.subscribe(SupplyDeliveredEvent, retry_events.append)
    assert retry_engine.step() is False

    control_ctx, control_engine = _engine_for(
        _enabled_payload(),
        seed=2_008,
    )
    assert control_engine.step() is False
    assert retry_engine.checkpoint() == control_engine.checkpoint()
    assert retry_ctx.clock.tick_count == 1
    assert _unit_quantity(retry_ctx) == pytest.approx(3.0)
    assert _depot_quantity(retry_ctx) == pytest.approx(7.0)
    assert [event.quantity for event in retry_events] == pytest.approx([3.0])


def test_second_quantum_failure_commits_first_and_retries_without_duplicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _load_enabled(seed=2_208)
    runtime = ctx.logistics_runtime
    delivered: list[SupplyDeliveredEvent] = []
    ctx.event_bus.subscribe(SupplyDeliveredEvent, delivered.append)
    original_consume_idle = runtime._consume_idle
    consume_calls = 0

    def fail_second_idle(**kwargs: Any) -> None:
        nonlocal consume_calls
        consume_calls += 1
        if consume_calls == 2:
            raise RuntimeError("phase-108 quantum-2 failure")
        original_consume_idle(**kwargs)

    monkeypatch.setattr(runtime, "_consume_idle", fail_second_idle)
    interval_end = ctx.clock.current_time + timedelta(hours=2)

    with pytest.raises(
        RuntimeError,
        match="phase-108 quantum-2 failure",
    ):
        runtime.update(
            dt_seconds=7200.0,
            interval_end=interval_end,
            interval_end_elapsed_seconds=7200.0,
            units=ctx.all_units(),
        )

    failed_state = runtime.get_state()
    assert failed_state["last_boundary_elapsed_seconds"] == pytest.approx(
        3600.0,
    )
    assert failed_state["elapsed_accumulator_seconds"] == pytest.approx(
        3600.0,
    )
    assert failed_state["unit_last_accounted_seconds"][
        UNIT_ID
    ] == pytest.approx(3600.0)
    assert _unit_quantity(ctx) == pytest.approx(3.0)
    assert _depot_quantity(ctx) == pytest.approx(7.0)
    assert [event.quantity for event in delivered] == pytest.approx([3.0])
    assert [
        event.timestamp for event in delivered
    ] == [ctx.clock.current_time + timedelta(hours=1)]

    runtime.update(
        dt_seconds=0.0,
        interval_end=interval_end,
        interval_end_elapsed_seconds=7200.0,
        units=ctx.all_units(),
    )

    retried_state = runtime.get_state()
    assert retried_state["last_boundary_elapsed_seconds"] == pytest.approx(
        7200.0,
    )
    assert retried_state["elapsed_accumulator_seconds"] == pytest.approx(0.0)
    assert retried_state["unit_last_accounted_seconds"][
        UNIT_ID
    ] == pytest.approx(7200.0)
    assert _unit_quantity(ctx) == pytest.approx(3.0)
    assert _depot_quantity(ctx) == pytest.approx(6.0)
    assert [event.quantity for event in delivered] == pytest.approx(
        [3.0, 1.0],
    )
    assert [
        event.timestamp for event in delivered
    ] == [
        ctx.clock.current_time + timedelta(hours=1),
        ctx.clock.current_time + timedelta(hours=2),
    ]


def test_first_quantum_failure_rolls_back_and_leaves_boundary_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _load_enabled(seed=2_308)
    runtime = ctx.logistics_runtime
    before = copy.deepcopy(runtime.get_state())
    delivered: list[SupplyDeliveredEvent] = []
    ctx.event_bus.subscribe(SupplyDeliveredEvent, delivered.append)
    original_consume_idle = runtime._consume_idle
    consume_calls = 0

    def fail_first_idle(**kwargs: Any) -> None:
        nonlocal consume_calls
        consume_calls += 1
        if consume_calls == 1:
            raise RuntimeError("phase-108 quantum-1 failure")
        original_consume_idle(**kwargs)

    monkeypatch.setattr(runtime, "_consume_idle", fail_first_idle)
    interval_end = ctx.clock.current_time + timedelta(hours=1)

    with pytest.raises(
        RuntimeError,
        match="phase-108 quantum-1 failure",
    ):
        runtime.update(
            dt_seconds=3600.0,
            interval_end=interval_end,
            interval_end_elapsed_seconds=3600.0,
            units=ctx.all_units(),
        )

    failed_state = runtime.get_state()
    assert failed_state["stockpile"] == before["stockpile"]
    assert failed_state["supply_network"] == before["supply_network"]
    assert (
        failed_state["unit_last_accounted_seconds"]
        == before["unit_last_accounted_seconds"]
    )
    assert (
        failed_state["last_boundary_positions"]
        == before["last_boundary_positions"]
    )
    assert failed_state["last_boundary_elapsed_seconds"] == pytest.approx(
        0.0,
    )
    assert failed_state["elapsed_accumulator_seconds"] == pytest.approx(
        3600.0,
    )
    assert delivered == []

    runtime.update(
        dt_seconds=0.0,
        interval_end=interval_end,
        interval_end_elapsed_seconds=3600.0,
        units=ctx.all_units(),
    )

    assert runtime.get_state()[
        "last_boundary_elapsed_seconds"
    ] == pytest.approx(3600.0)
    assert runtime.elapsed_accumulator_seconds == pytest.approx(0.0)
    assert _unit_quantity(ctx) == pytest.approx(3.0)
    assert _depot_quantity(ctx) == pytest.approx(7.0)
    assert [event.quantity for event in delivered] == pytest.approx([3.0])


@pytest.mark.parametrize("operation", ["delivery", "consumption"])
def test_direct_stockpile_mutations_notify_all_observers_post_commit(
    operation: str,
) -> None:
    ctx = _load_enabled(seed=2_408)
    manager = ctx.stockpile_manager
    event_type: type[Any] = (
        SupplyDeliveredEvent
        if operation == "delivery"
        else SupplyDepletedEvent
    )
    attempts: list[str] = []

    def first_observer(_event: Any) -> None:
        attempts.append("first")

    def first_failure(_event: Any) -> None:
        attempts.append("failure-one")
        raise RuntimeError("direct observer failure one")

    def middle_observer(_event: Any) -> None:
        attempts.append("middle")

    def second_failure(_event: Any) -> None:
        attempts.append("failure-two")
        raise ValueError("direct observer failure two")

    def final_observer(_event: Any) -> None:
        attempts.append("final")

    for priority, observer in enumerate(
        (
            first_observer,
            first_failure,
            middle_observer,
            second_failure,
            final_observer,
        ),
    ):
        ctx.event_bus.subscribe(event_type, observer, priority=priority)

    with pytest.raises(ExceptionGroup) as exc_info:
        if operation == "delivery":
            manager.deliver_to_unit(
                DEPOT_ID,
                UNIT_ID,
                CLASS_I,
                ITEM_ID,
                requested_quantity=1.0,
                max_quantity_tons=1.0,
                timestamp=ctx.clock.current_time,
                transport_mode=int(TransportMode.ROAD),
                route_id=f"blue_water:{UNIT_ID}",
            )
        else:
            manager.consume_unit_supplies(
                UNIT_ID,
                {CLASS_I: {ITEM_ID: 1.0}},
                timestamp=ctx.clock.current_time,
            )

    assert attempts == [
        "first",
        "failure-one",
        "middle",
        "failure-two",
        "final",
    ]
    assert [
        (type(error), str(error))
        for error in exc_info.value.exceptions
    ] == [
        (RuntimeError, "direct observer failure one"),
        (ValueError, "direct observer failure two"),
    ]
    if operation == "delivery":
        assert _unit_quantity(ctx) == pytest.approx(2.0)
        assert _depot_quantity(ctx) == pytest.approx(9.0)
    else:
        assert _unit_quantity(ctx) == pytest.approx(0.0)
        assert _depot_quantity(ctx) == pytest.approx(10.0)


def test_same_side_scarcity_is_greedy_stable_and_never_crosses_sides(
) -> None:
    payload = _enabled_payload()
    payload["sides"][0]["units"] = [
        {"unit_type": "m1a2", "count": 2},
    ]
    payload["sides"][0]["depots"][0]["initial_inventory"] = [_item(2.0)]
    red_profile = payload["logistics"]["unit_profiles"][1]
    red_profile["initial_inventory"] = [_item(1.0)]

    def run_once() -> tuple[tuple[float, ...], tuple[tuple[Any, ...], ...]]:
        ctx, _, delivered = _run_with_deliveries(
            copy.deepcopy(payload),
            seed=2_108,
        )
        quantities = tuple(
            _unit_quantity(ctx, unit_id)
            for unit_id in (
                "blue_m1a2_0000",
                "blue_m1a2_0001",
                "red_m1a2_0000",
            )
        )
        return quantities, _delivery_signature(delivered)

    first = run_once()
    second = run_once()

    assert first == second
    assert first[0] == pytest.approx((2.0, 0.0, 0.0))
    assert [event[1] for event in first[1]] == ["blue_m1a2_0000"]
    assert first[1][0][4] == pytest.approx(2.0)


@pytest.mark.parametrize(
    ("ground_state", "expected_code"),
    [
        pytest.param(GroundState.DRY, 0, id="dry"),
        pytest.param(GroundState.WET, 1, id="wet"),
        pytest.param(GroundState.THAWING, 2, id="mud-thawing"),
        pytest.param(GroundState.SATURATED, 2, id="mud-saturated"),
        pytest.param(GroundState.SNOW_COVERED, 3, id="snow"),
        pytest.param(GroundState.FROZEN, 4, id="frozen"),
    ],
)
def test_environment_ground_states_map_by_semantics_not_enum_integer(
    ground_state: GroundState,
    expected_code: int,
) -> None:
    assert logistics_ground_state_code(ground_state) == expected_code

    ctx = _load_enabled(seed=3_108 + int(ground_state))
    ctx.logistics_runtime.update(
        dt_seconds=3600.0,
        interval_end=ctx.clock.current_time + timedelta(hours=1),
        interval_end_elapsed_seconds=3600.0,
        units=ctx.all_units(),
        ground_state=ground_state,
    )
    _, _, route_id = _network_ids(ctx)
    expected_condition = 1.0 if expected_code < 2 else 0.99
    assert ctx.supply_network_engine.get_route(
        route_id,
    ).condition == pytest.approx(expected_condition)


def test_subinterval_ticks_retain_exact_remainder_until_boundary() -> None:
    payload = _enabled_payload()
    payload["tick_duration_seconds"] = 300.0
    ctx, engine = _engine_for(payload)

    for _ in range(11):
        assert engine.step() is False

    runtime_state = ctx.logistics_runtime.get_state()
    assert runtime_state["elapsed_accumulator_seconds"] == pytest.approx(
        3300.0,
    )
    assert _unit_quantity(ctx) == pytest.approx(1.0)
    assert _depot_quantity(ctx) == pytest.approx(10.0)

    assert engine.step() is False
    assert ctx.logistics_runtime.get_state()[
        "elapsed_accumulator_seconds"
    ] == pytest.approx(0.0)
    assert _unit_quantity(ctx) == pytest.approx(3.0)
    assert _depot_quantity(ctx) == pytest.approx(7.0)


def test_equal_elapsed_chunking_matches_across_3600_300_and_5_seconds(
) -> None:
    results: list[
        tuple[dict[str, Any], tuple[tuple[Any, ...], ...]]
    ] = []
    for tick_seconds, steps in ((3600.0, 1), (300.0, 12), (5.0, 720)):
        payload = _enabled_payload()
        payload["tick_duration_seconds"] = tick_seconds
        payload["logistics"]["route_templates"][0][
            "transport_mode"
        ] = "AIR"
        ctx, _, delivered = _run_with_deliveries(
            payload,
            steps=steps,
            seed=4_108,
        )
        results.append(
            (
                ctx.logistics_runtime.get_state(),
                _delivery_signature(delivered),
            ),
        )

    assert results[1] == results[0]
    assert results[2] == results[0]


def test_moving_and_active_battle_units_are_idle_consumption_controls(
) -> None:
    payload = _enabled_payload()
    payload["logistics"]["route_templates"] = []
    blue_profile = payload["logistics"]["unit_profiles"][0]
    blue_profile["initial_inventory"] = [_item(4.0)]

    stationary_ctx, stationary_engine = _engine_for(
        copy.deepcopy(payload),
    )
    assert stationary_engine.step() is False
    assert _unit_quantity(stationary_ctx) == pytest.approx(3.0)

    moving_ctx, moving_engine = _engine_for(copy.deepcopy(payload))
    moving_unit = next(
        unit
        for unit in moving_ctx.all_units()
        if unit.entity_id == UNIT_ID
    )
    moving_unit.position = Position(
        moving_unit.position.easting + 1.0,
        moving_unit.position.northing,
        moving_unit.position.altitude,
    )
    assert moving_engine.step() is False
    assert _unit_quantity(moving_ctx) == pytest.approx(4.0)

    battle_ctx, battle_engine = _engine_for(copy.deepcopy(payload))
    created = battle_engine.battle_manager.detect_engagement(
        battle_ctx.units_by_side,
        engagement_range_m=100_000.0,
        timestamp=battle_ctx.clock.current_time,
    )
    assert len(created) == 1
    assert UNIT_ID in created[0].unit_ids
    assert battle_engine.step() is False
    assert _unit_quantity(battle_ctx) == pytest.approx(4.0)


@pytest.mark.parametrize("activity", ["move-return", "battle-before-boundary"])
def test_any_interval_activity_suppresses_idle_after_checkpoint_restore(
    activity: str,
) -> None:
    payload = _enabled_payload()
    payload["tick_duration_seconds"] = 300.0
    payload["logistics"]["route_templates"] = []
    payload["logistics"]["unit_profiles"][0][
        "initial_inventory"
    ] = [_item(4.0)]
    source_ctx, source = _engine_for(
        copy.deepcopy(payload),
        seed=6_108,
    )
    blue = next(
        unit for unit in source_ctx.all_units()
        if unit.entity_id == UNIT_ID
    )
    starting_position = blue.position

    if activity == "move-return":
        blue.position = Position(
            starting_position.easting + 100.0,
            starting_position.northing,
            starting_position.altitude,
        )
        assert source.step() is False
        blue.position = starting_position
        assert source.step() is False
        remaining_steps = 10
    else:
        for unit in source_ctx.all_units():
            object.__setattr__(unit, "speed", 0.0)
            object.__setattr__(unit, "max_speed", 0.0)
        battles = source.battle_manager.detect_engagement(
            source_ctx.units_by_side,
            engagement_range_m=100_000.0,
            timestamp=source_ctx.clock.current_time,
        )
        assert len(battles) == 1
        assert source.step() is False
        assert blue.position == starting_position
        assert blue.status.name == "ACTIVE"
        assert battles[0].active is False
        remaining_steps = 11

    checkpoint = source.checkpoint()
    for _ in range(remaining_steps):
        assert source.step() is False
    assert _unit_quantity(source_ctx) == pytest.approx(4.0)

    target_ctx, target = _engine_for(
        copy.deepcopy(payload),
        seed=999_108,
    )
    target.restore(checkpoint)
    for _ in range(remaining_steps):
        assert target.step() is False

    assert _unit_quantity(target_ctx) == pytest.approx(4.0)
    assert json.loads(target.checkpoint()) == json.loads(source.checkpoint())


def test_battle_created_and_resolved_after_logistics_marks_open_interval(
) -> None:
    payload = _enabled_payload()
    payload["tick_duration_seconds"] = 300.0
    payload["logistics"]["route_templates"] = []
    payload["logistics"]["unit_profiles"][0][
        "initial_inventory"
    ] = [_item(4.0)]
    source_ctx = _load_payload(copy.deepcopy(payload), seed=6_208)
    for unit in source_ctx.all_units():
        object.__setattr__(unit, "speed", 0.0)
        object.__setattr__(unit, "max_speed", 0.0)
    starting_positions = {
        unit.entity_id: unit.position
        for unit in source_ctx.all_units()
    }
    campaign = _quiet_campaign()
    source = SimulationEngine(
        source_ctx,
        config=EngineConfig(resolution_closing_range_mult=0.0),
        campaign_config=campaign,
    )
    assert source.battle_manager.active_battles == []

    campaign.engagement_detection_range_m = 100_000.0
    assert source.step() is False
    campaign.engagement_detection_range_m = 1.0

    active_battles = source.battle_manager.active_battles
    assert len(active_battles) == 1
    assert active_battles[0].ticks_executed == 0
    assert {
        unit.entity_id: unit.position
        for unit in source_ctx.all_units()
    } == starting_positions
    runtime_state = source_ctx.logistics_runtime.get_state()
    assert runtime_state["elapsed_accumulator_seconds"] == pytest.approx(
        300.0,
    )
    assert runtime_state["unit_interval_disqualified"][UNIT_ID] is True
    checkpoint = source.checkpoint()

    for _ in range(11):
        assert source.step() is False
    assert _unit_quantity(source_ctx) == pytest.approx(4.0)

    target_ctx, target = _engine_for(
        copy.deepcopy(payload),
        seed=999_208,
    )
    target.restore(checkpoint)
    restored_battles = target.battle_manager.active_battles
    assert len(restored_battles) == 1
    assert restored_battles[0].ticks_executed == 0
    assert target_ctx.logistics_runtime.get_state()[
        "unit_interval_disqualified"
    ][UNIT_ID] is True
    for _ in range(11):
        assert target.step() is False

    assert _unit_quantity(target_ctx) == pytest.approx(4.0)
    assert json.loads(target.checkpoint()) == json.loads(source.checkpoint())


def test_crossing_call_applies_motion_only_to_first_of_two_open_intervals(
) -> None:
    payload = _enabled_payload()
    payload.pop("tick_duration_seconds", None)
    payload["tick_resolution"] = {
        "strategic_s": 1800.0,
        "operational_s": 3600.0,
        "tactical_s": 300.0,
    }
    payload["logistics"]["route_templates"] = []
    payload["logistics"]["unit_profiles"][0][
        "initial_inventory"
    ] = [_item(4.0)]
    ctx = _load_payload(payload, seed=6_308)
    blue = next(
        unit for unit in ctx.all_units()
        if unit.entity_id == UNIT_ID
    )
    red = ctx.units_by_side["red"][0]
    red.position = Position(
        blue.position.easting + 50_000.0,
        blue.position.northing,
        blue.position.altitude,
    )
    engine = SimulationEngine(
        ctx,
        config=EngineConfig(resolution_closing_range_mult=2.0),
        campaign_config=CampaignConfig(
            engagement_detection_range_m=15_000.0,
            enable_maintenance=False,
            enable_strategic_movement=False,
            enable_supply_network=True,
        ),
    )

    assert engine.step() is False
    assert ctx.logistics_runtime.elapsed_accumulator_seconds == pytest.approx(
        1800.0,
    )
    blue.position = Position(
        blue.position.easting + 100.0,
        blue.position.northing,
        blue.position.altitude,
    )
    red.position = Position(
        blue.position.easting + 20_000.0,
        blue.position.northing,
        blue.position.altitude,
    )

    assert engine.step() is False
    assert ctx.clock.elapsed.total_seconds() == pytest.approx(5400.0)
    assert ctx.logistics_runtime.elapsed_accumulator_seconds == pytest.approx(
        1800.0,
    )
    assert _unit_quantity(ctx) == pytest.approx(4.0)

    red.position = Position(
        blue.position.easting + 50_000.0,
        blue.position.northing,
        blue.position.altitude,
    )
    assert engine.step() is False
    assert ctx.clock.elapsed.total_seconds() == pytest.approx(7200.0)
    assert ctx.logistics_runtime.elapsed_accumulator_seconds == pytest.approx(
        0.0,
    )
    assert _unit_quantity(ctx) == pytest.approx(3.0)


def test_zero_dt_cannot_cross_positive_tiny_logistics_interval() -> None:
    payload = _enabled_payload()
    payload["logistics"]["update_interval_seconds"] = 1e-10
    ctx = _load_payload(payload, seed=6_408)
    before = copy.deepcopy(ctx.logistics_runtime.get_state())
    delivered: list[SupplyDeliveredEvent] = []
    ctx.event_bus.subscribe(SupplyDeliveredEvent, delivered.append)

    ctx.logistics_runtime.update(
        dt_seconds=0.0,
        interval_end=ctx.clock.current_time,
        interval_end_elapsed_seconds=0.0,
        units=ctx.all_units(),
    )

    assert ctx.logistics_runtime.get_state() == before
    assert ctx.logistics_runtime.elapsed_accumulator_seconds == 0.0
    assert delivered == []


def test_positive_tiny_interval_consumes_positive_eligible_duration() -> None:
    payload = _enabled_payload()
    payload["logistics"]["update_interval_seconds"] = 1e-10
    payload["logistics"]["route_templates"] = []
    ctx = _load_payload(payload, seed=6_508)
    before = _unit_quantity(ctx)

    ctx.logistics_runtime.update(
        dt_seconds=1e-10,
        interval_end=ctx.clock.current_time,
        interval_end_elapsed_seconds=1e-10,
        units=ctx.all_units(),
    )

    expected_debit = 1e-10 / 3600.0
    actual_debit = before - _unit_quantity(ctx)
    assert actual_debit > 0.0
    assert actual_debit == pytest.approx(
        expected_debit,
        rel=1e-3,
        abs=1e-16,
    )
    runtime_state = ctx.logistics_runtime.get_state()
    assert runtime_state["last_boundary_elapsed_seconds"] == pytest.approx(
        1e-10,
    )
    assert runtime_state["unit_last_accounted_seconds"][
        UNIT_ID
    ] == pytest.approx(1e-10)
    assert runtime_state["elapsed_accumulator_seconds"] == pytest.approx(0.0)


@pytest.mark.parametrize(
    ("control", "expected_quantity"),
    [
        ("active-battle", 4.0),
        ("inactive-status", 4.0),
        ("movement-only", 3.0),
    ],
)
def test_multi_quantum_activity_latch_persists_only_for_persistent_controls(
    control: str,
    expected_quantity: float,
) -> None:
    payload = _enabled_payload()
    payload["logistics"]["route_templates"] = []
    payload["logistics"]["unit_profiles"][0][
        "initial_inventory"
    ] = [_item(4.0)]
    ctx = _load_payload(payload, seed=6_608)
    blue = next(
        unit for unit in ctx.all_units()
        if unit.entity_id == UNIT_ID
    )
    active_battle_ids: set[str] = set()
    if control == "active-battle":
        active_battle_ids.add(UNIT_ID)
    elif control == "inactive-status":
        blue.status = UnitStatus.DISABLED
    else:
        blue.position = Position(
            blue.position.easting + 100.0,
            blue.position.northing,
            blue.position.altitude,
        )

    ctx.logistics_runtime.update(
        dt_seconds=7200.0,
        interval_end=ctx.clock.current_time + timedelta(hours=2),
        interval_end_elapsed_seconds=7200.0,
        units=ctx.all_units(),
        active_battle_unit_ids=active_battle_ids,
    )

    assert _unit_quantity(ctx) == pytest.approx(expected_quantity)
    runtime_state = ctx.logistics_runtime.get_state()
    assert runtime_state["last_boundary_elapsed_seconds"] == pytest.approx(
        7200.0,
    )
    assert runtime_state["unit_last_accounted_seconds"][
        UNIT_ID
    ] == pytest.approx(7200.0)
    assert runtime_state["elapsed_accumulator_seconds"] == pytest.approx(0.0)


def test_network_disabled_retains_idle_consumption_only() -> None:
    payload = _enabled_payload()
    ctx, _, delivered = _run_with_deliveries(
        payload,
        enable_supply_network=False,
    )

    assert _unit_quantity(ctx) == pytest.approx(0.0)
    assert _depot_quantity(ctx) == pytest.approx(10.0)
    assert delivered == []
    _, _, route_id = _network_ids(ctx)
    assert ctx.supply_network_engine.get_route(
        route_id,
    ).current_flow_tons_per_hour == pytest.approx(0.0)


def test_enabled_logistics_does_not_draw_from_logistics_rng_stream() -> None:
    payload = _enabled_payload()
    payload["tick_duration_seconds"] = 300.0
    ctx, engine = _engine_for(payload, seed=7_108)
    stream = ctx.rng_manager.get_stream(ModuleId.LOGISTICS)
    before = copy.deepcopy(stream.bit_generator.state)

    for _ in range(24):
        assert engine.step() is False

    assert stream.bit_generator.state == before


def test_disabled_runtime_adds_no_unit_or_battle_enumeration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _enabled_payload()
    payload["logistics"] = {"enabled": False}
    ctx, engine = _engine_for(payload, seed=7_208)
    assert ctx.logistics_runtime is not None
    assert ctx.logistics_runtime.enabled is False

    def unexpected_all_units() -> list[Any]:
        raise AssertionError(
            "disabled logistics must not enumerate the force roster",
        )

    monkeypatch.setattr(ctx, "all_units", unexpected_all_units)
    battle_manager_type = type(engine.battle_manager)
    active_battles_property = battle_manager_type.active_battles
    battle_scan_count = 0

    def counted_active_battles(manager: Any) -> list[Any]:
        nonlocal battle_scan_count
        battle_scan_count += 1
        assert active_battles_property.fget is not None
        return active_battles_property.fget(manager)

    monkeypatch.setattr(
        battle_manager_type,
        "active_battles",
        property(counted_active_battles),
    )

    assert engine.step() is False
    # One scan selects the interval resolution; disabled logistics adds none.
    assert battle_scan_count == 1


def test_disabled_runtime_restores_after_elapsed_scenario_time() -> None:
    payload = _enabled_payload()
    payload["logistics"] = {"enabled": False}
    payload["tick_duration_seconds"] = 300.0
    source_ctx, source = _engine_for(payload, seed=7_308)
    for _ in range(3):
        assert source.step() is False

    checkpoint = source.checkpoint()
    runtime_state = json.loads(checkpoint)["context"]["logistics_runtime"]
    assert runtime_state["elapsed_accumulator_seconds"] == 0.0
    assert runtime_state["last_boundary_elapsed_seconds"] == 0.0

    target_ctx, target = _engine_for(payload, seed=7_308)
    target.restore(checkpoint)

    assert target_ctx.clock.elapsed.total_seconds() == pytest.approx(900.0)
    assert json.loads(target.checkpoint()) == json.loads(checkpoint)


def test_legacy_scenario_without_logistics_contract_remains_inert() -> None:
    ctx = ScenarioLoader(DATA_DIR).load(LEGACY_SCENARIO, seed=108)
    delivered: list[SupplyDeliveredEvent] = []
    ctx.event_bus.subscribe(SupplyDeliveredEvent, delivered.append)
    before_stockpile = copy.deepcopy(ctx.stockpile_manager.get_state())
    before_network = copy.deepcopy(ctx.supply_network_engine.get_state())
    assert before_stockpile["depots"] == {}
    assert before_stockpile["unit_inventories"] == {}
    assert before_network["nodes"] == {}
    assert before_network["routes"] == {}

    engine = SimulationEngine(
        ctx,
        config=EngineConfig(resolution_closing_range_mult=0.0),
        campaign_config=_quiet_campaign(),
    )
    assert engine.step() is False

    assert ctx.stockpile_manager.get_state() == before_stockpile
    assert ctx.supply_network_engine.get_state() == before_network
    assert delivered == []


def test_json_checkpoint_preserves_supply_fraction_and_complete_network_state(
) -> None:
    source_ctx = _load_enabled()
    _, _, route_id = _network_ids(source_ctx)
    source_route = source_ctx.supply_network_engine.get_route(route_id)
    source_depot = source_ctx.stockpile_manager.get_depot(DEPOT_ID)
    source_depot.condition = 0.75
    assert source_depot.inventory.consume(
        CLASS_I,
        ITEM_ID,
        0.5,
    ) == pytest.approx(0.5)
    source_ctx.stockpile_manager.get_unit_inventory(UNIT_ID).add(
        CLASS_I,
        ITEM_ID,
        0.25,
    )
    source_route.condition = 0.8
    source_route.current_flow_tons_per_hour = 0.25
    expected_supply_state = source_ctx.stockpile_manager.get_supply_state(
        UNIT_ID,
    )
    source = SimulationEngine(
        source_ctx,
        config=EngineConfig(resolution_closing_range_mult=0.0),
        campaign_config=_quiet_campaign(),
    )
    checkpoint = source.checkpoint()
    json.loads(checkpoint.decode("utf-8"))

    target_ctx = _load_enabled()
    _network_ids(target_ctx)
    target = SimulationEngine(
        target_ctx,
        config=EngineConfig(resolution_closing_range_mult=0.0),
        campaign_config=_quiet_campaign(),
    )
    target.restore(checkpoint)

    assert target_ctx.stockpile_manager.get_supply_state(
        UNIT_ID,
    ) == pytest.approx(expected_supply_state)
    restored_depot_node_id, _, restored_route_id = _network_ids(target_ctx)
    restored_node = target_ctx.supply_network_engine.get_node(
        restored_depot_node_id,
    )
    restored_depot = target_ctx.stockpile_manager.get_depot(DEPOT_ID)
    restored_route = target_ctx.supply_network_engine.get_route(
        restored_route_id,
    )
    assert restored_node.echelon_level == 3
    assert restored_node.infrastructure_id is None
    assert restored_node.throughput_tons_per_hour == pytest.approx(100.0)
    assert restored_depot.condition == pytest.approx(0.75)
    assert _inventory_quantity(restored_depot.inventory) == pytest.approx(9.5)
    assert restored_route.condition == pytest.approx(0.8)
    assert restored_route.current_flow_tons_per_hour == pytest.approx(0.25)
    assert restored_route.infrastructure_ids == []


def test_mutated_or_foreign_registration_plan_rejects_without_mutation() -> None:
    source_ctx = _load_enabled(seed=8_108)
    target_ctx = _load_enabled(seed=8_109)
    incoming = copy.deepcopy(
        next(
            unit
            for unit in source_ctx.all_units()
            if unit.entity_id == UNIT_ID
        ),
    )
    incoming.entity_id = "blue_plan_probe"
    plan = source_ctx.logistics_runtime.prepare_unit_registration(
        [incoming],
        eligible_from_seconds=0.0,
    )
    source_before = copy.deepcopy(source_ctx.logistics_runtime.get_state())
    target_before = copy.deepcopy(target_ctx.logistics_runtime.get_state())

    with pytest.raises(ValueError, match="foreign"):
        target_ctx.logistics_runtime.commit_unit_registration(plan)
    assert target_ctx.logistics_runtime.get_state() == target_before

    plan.registrations[0].maximum[CLASS_I][ITEM_ID] = 8.0
    with pytest.raises(ValueError, match="mutated"):
        source_ctx.logistics_runtime.commit_unit_registration(plan)
    assert source_ctx.logistics_runtime.get_state() == source_before


def test_mutated_restore_plan_rejects_without_mutation() -> None:
    ctx = _load_enabled(seed=8_110)
    runtime = ctx.logistics_runtime
    before = copy.deepcopy(runtime.get_state())
    plan = runtime.stage_state(
        before,
        expected_units={
            unit.entity_id: unit
            for unit in ctx.all_units()
        },
        expected_elapsed_seconds=0.0,
    )
    maximum = plan.stockpile_state["unit_max_supplies"][UNIT_ID]
    class_bucket = maximum.get(CLASS_I, maximum.get(str(CLASS_I)))
    assert class_bucket is not None
    class_bucket[ITEM_ID] = 8.0

    with pytest.raises(ValueError, match="mutated"):
        runtime.commit_state(plan)

    assert runtime.get_state() == before


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        ("v107", r"Unsupported checkpoint version 107; expected 118"),
        (
            "versionless",
            r"Versionless checkpoints cannot restore a logistics-enabled",
        ),
    ],
)
def test_enabled_runtime_rejects_old_or_versionless_checkpoints_atomically(
    mutation: str,
    match: str,
) -> None:
    payload = _enabled_payload()
    _, source = _engine_for(copy.deepcopy(payload))
    invalid = source.get_state()
    if mutation == "v107":
        invalid["checkpoint_version"] = 107
    else:
        invalid.pop("checkpoint_version")

    _, target = _engine_for(copy.deepcopy(payload))
    before = target.checkpoint()
    with pytest.raises(ValueError, match=match):
        target.set_state(invalid)
    assert target.checkpoint() == before


def test_partial_boundary_json_checkpoint_continues_exactly_in_fresh_runtime(
) -> None:
    payload = _enabled_payload()
    payload["tick_duration_seconds"] = 300.0
    source_ctx, source = _engine_for(copy.deepcopy(payload), seed=8_108)
    for _ in range(11):
        assert source.step() is False
    assert source_ctx.logistics_runtime.get_state()[
        "elapsed_accumulator_seconds"
    ] == pytest.approx(3300.0)

    checkpoint = source.checkpoint()
    json.loads(checkpoint.decode("utf-8"))
    source_events: list[SupplyDeliveredEvent] = []
    source_ctx.event_bus.subscribe(SupplyDeliveredEvent, source_events.append)
    assert source.step() is False

    target_ctx, target = _engine_for(
        copy.deepcopy(payload),
        seed=999_108,
    )
    target_events: list[SupplyDeliveredEvent] = []
    target_ctx.event_bus.subscribe(SupplyDeliveredEvent, target_events.append)
    target.restore(checkpoint)
    assert json.loads(target.checkpoint()) == json.loads(checkpoint)
    assert target.step() is False

    assert json.loads(target.checkpoint()) == json.loads(source.checkpoint())
    assert _delivery_signature(target_events) == _delivery_signature(
        source_events,
    )


def test_full_engine_restore_excludes_event_observer_object_graph() -> None:
    class NonCopyableSubscriber:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(self, _event: SupplyDeliveredEvent) -> None:
            self.calls += 1

        def __deepcopy__(self, _memo: dict[int, Any]) -> Any:
            raise AssertionError("event observers must not be checkpointed")

    payload = _enabled_payload()
    ctx, engine = _engine_for(payload, seed=8_158)
    subscriber = NonCopyableSubscriber()
    ctx.event_bus.subscribe(SupplyDeliveredEvent, subscriber)
    checkpoint = engine.checkpoint()

    engine.restore(checkpoint)

    assert json.loads(engine.checkpoint()) == json.loads(checkpoint)
    assert subscriber.calls == 0
    assert engine.step() is False
    assert subscriber.calls == 1


@pytest.mark.parametrize(
    "corruption",
    ["accumulator", "negative_inventory", "cross_side_node"],
)
def test_corrupt_logistics_checkpoint_is_rejected_atomically(
    corruption: str,
) -> None:
    payload = _enabled_payload()
    payload["tick_duration_seconds"] = 300.0
    _, source = _engine_for(copy.deepcopy(payload))
    for _ in range(5):
        assert source.step() is False
    invalid = source.get_state()
    logistics = invalid["context"]["logistics_runtime"]
    if corruption == "accumulator":
        logistics["elapsed_accumulator_seconds"] = 3600.0
    elif corruption == "negative_inventory":
        logistics["stockpile"]["unit_inventories"][UNIT_ID]["items"][
            str(CLASS_I)
        ][ITEM_ID] = -1.0
    else:
        logistics["supply_network"]["nodes"][f"unit:{UNIT_ID}"][
            "side"
        ] = "red"

    _, target = _engine_for(copy.deepcopy(payload))
    before = target.checkpoint()
    with pytest.raises(ValueError, match=r"(?i)logistics"):
        target.set_state(invalid)
    assert target.checkpoint() == before


def test_checkpoint_rejects_removed_materialized_zero_inventory_item(
) -> None:
    payload = _enabled_payload()
    payload["logistics"]["route_templates"] = []
    source_ctx, source = _engine_for(copy.deepcopy(payload), seed=8_258)
    assert source.step() is False
    assert _unit_quantity(source_ctx) == pytest.approx(0.0)
    invalid = source.get_state()
    inventory_items = invalid["context"]["logistics_runtime"][
        "stockpile"
    ]["unit_inventories"][UNIT_ID]["items"][str(CLASS_I)]
    assert inventory_items[ITEM_ID] == pytest.approx(0.0)
    inventory_items.pop(ITEM_ID)

    _, target = _engine_for(copy.deepcopy(payload), seed=999_258)
    before = target.checkpoint()
    with pytest.raises(
        ValueError,
        match=r"inventory item topology differs from its profile",
    ):
        target.set_state(invalid)
    assert target.checkpoint() == before


def test_checkpoint_rejects_shifted_last_accounted_time_atomically() -> None:
    payload = _enabled_payload()
    payload["tick_duration_seconds"] = 300.0
    _, source = _engine_for(copy.deepcopy(payload), seed=8_268)
    for _ in range(5):
        assert source.step() is False
    invalid = source.get_state()
    runtime_state = invalid["context"]["logistics_runtime"]
    assert runtime_state["last_boundary_elapsed_seconds"] == pytest.approx(
        0.0,
    )
    assert runtime_state["unit_last_accounted_seconds"][
        UNIT_ID
    ] == pytest.approx(0.0)
    runtime_state["unit_last_accounted_seconds"][UNIT_ID] = 300.0

    _, target = _engine_for(copy.deepcopy(payload), seed=999_268)
    before = target.checkpoint()
    with pytest.raises(
        ValueError,
        match=r"accounting time disagrees with the last committed boundary",
    ):
        target.set_state(invalid)
    assert target.checkpoint() == before


def test_checkpoint_clear_latch_cannot_hide_coordinated_position_shift(
) -> None:
    payload = _enabled_payload()
    _, source = _engine_for(copy.deepcopy(payload), seed=8_278)
    invalid = source.get_state()
    runtime_state = invalid["context"]["logistics_runtime"]
    assert runtime_state["unit_interval_disqualified"][UNIT_ID] is False
    boundary_position = runtime_state["last_boundary_positions"][UNIT_ID]
    boundary_position[0] += 100.0
    network = runtime_state["supply_network"]
    unit_node = network["nodes"][f"unit:{UNIT_ID}"]
    unit_node["position"] = list(boundary_position)
    route = network["routes"][f"blue_water:{UNIT_ID}"]
    depot_position = network["nodes"][f"depot:{DEPOT_ID}"]["position"]
    route["distance_m"] = math.dist(depot_position, unit_node["position"])
    route["base_transit_time_hours"] = (
        route["distance_m"]
        / 1000.0
        / route["transport_speed_kph"]
    )

    _, target = _engine_for(copy.deepcopy(payload), seed=999_278)
    before = target.checkpoint()
    with pytest.raises(
        ValueError,
        match=r"boundary position disagrees with its staged unit position",
    ):
        target.set_state(invalid)
    assert target.checkpoint() == before


def _mutate_v108_logistics_checkpoint(
    state: dict[str, Any],
    mutation: str,
) -> None:
    runtime = state["context"]["logistics_runtime"]
    stockpile = runtime["stockpile"]
    depot = stockpile["depots"][DEPOT_ID]
    depot_items = depot["inventory"]["items"]
    unit_inventory = stockpile["unit_inventories"][UNIT_ID]
    unit_maximum = stockpile["unit_max_supplies"][UNIT_ID]
    network = runtime["supply_network"]
    depot_node = network["nodes"][f"depot:{DEPOT_ID}"]
    unit_node = network["nodes"][f"unit:{UNIT_ID}"]
    route = network["routes"][f"blue_water:{UNIT_ID}"]

    if mutation == "nested_missing_depot_key":
        depot.pop("condition")
    elif mutation == "nested_extra_route_key":
        route["undeclared"] = True
    elif mutation == "nested_missing_inventory_key":
        unit_inventory.pop("items")
    elif mutation == "depot_declared_id":
        depot["depot_id"] = "other_depot"
    elif mutation == "depot_side":
        depot["side"] = "red"
    elif mutation == "depot_type":
        depot["depot_type"] = int(DepotType.LOGISTICS_SUPPORT_AREA)
    elif mutation == "depot_position":
        depot["position"][0] += 1.0
    elif mutation == "depot_capacity":
        depot["capacity_tons"] += 1.0
    elif mutation == "depot_throughput":
        depot["throughput_tons_per_hour"] -= 1.0
    elif mutation == "depot_remove_item":
        depot_items[str(CLASS_I)].pop(ITEM_ID)
    elif mutation == "depot_add_known_item":
        depot_items[str(CLASS_I)]["ration_mre"] = 1.0
    elif mutation == "unknown_item":
        quantity = depot_items[str(CLASS_I)].pop(ITEM_ID)
        depot_items[str(CLASS_I)]["phase108_unknown_item"] = quantity
    elif mutation == "class_mismatched_item":
        quantity = depot_items.pop(str(CLASS_I))[ITEM_ID]
        depot_items[str(int(SupplyClass.CLASS_III))] = {
            ITEM_ID: quantity,
        }
    elif mutation == "unit_maximum_quantity":
        unit_maximum[str(CLASS_I)][ITEM_ID] += 1.0
    elif mutation == "node_declared_id":
        unit_node["node_id"] = "unit:other"
    elif mutation == "node_linked_id":
        unit_node["linked_id"] = "red_m1a2_0000"
    elif mutation == "node_type":
        unit_node["node_type"] = "DEPOT"
    elif mutation == "node_side":
        unit_node["side"] = "red"
    elif mutation == "node_position":
        unit_node["position"][0] += 1.0
    elif mutation == "depot_node_identity":
        depot_node["echelon_level"] = 2
    elif mutation == "route_declared_id":
        route["route_id"] = "other_route"
    elif mutation == "route_from_endpoint":
        route["from_node"] = "unit:red_m1a2_0000"
    elif mutation == "route_to_endpoint":
        route["to_node"] = "unit:red_m1a2_0000"
    elif mutation == "route_mode":
        route["transport_mode"] = int(TransportMode.RAIL)
    elif mutation == "route_capacity":
        route["capacity_tons_per_hour"] += 1.0
    elif mutation == "route_speed":
        route["transport_speed_kph"] += 1.0
    elif mutation == "route_distance":
        route["distance_m"] += 1.0
    elif mutation == "route_transit":
        route["base_transit_time_hours"] += 1.0
    elif mutation == "route_geometry_pair":
        route["distance_m"] += 100.0
        route["base_transit_time_hours"] = (
            route["distance_m"]
            / 1000.0
            / route["transport_speed_kph"]
        )
    elif mutation == "stockpile_config_omission":
        stockpile["config"].pop("shortage_threshold")
    elif mutation == "network_config_typo":
        config = network["config"]
        config["road_capacity_multipler"] = config.pop(
            "road_capacity_multiplier",
        )
    elif mutation == "stockpile_config_coercion":
        stockpile["config"]["capture_efficiency"] = "0.5"
    elif mutation == "network_config_coercion":
        network["config"]["enable_capacity_constraints"] = 0
    elif mutation == "stockpile_config_changed":
        stockpile["config"]["capture_efficiency"] = 0.6
    elif mutation == "network_config_changed":
        network["config"]["road_capacity_multiplier"] = 2.0
    elif mutation == "integral_float_depot_enum":
        depot["depot_type"] = float(depot["depot_type"])
    elif mutation == "integral_float_route_enum":
        route["transport_mode"] = float(route["transport_mode"])
    else:
        raise AssertionError(f"Unknown checkpoint mutation {mutation!r}")


@pytest.mark.parametrize(
    "mutation",
    [
        "nested_missing_depot_key",
        "nested_extra_route_key",
        "nested_missing_inventory_key",
        "depot_declared_id",
        "depot_side",
        "depot_type",
        "depot_position",
        "depot_capacity",
        "depot_throughput",
        "depot_remove_item",
        "depot_add_known_item",
        "unknown_item",
        "class_mismatched_item",
        "unit_maximum_quantity",
        "node_declared_id",
        "node_linked_id",
        "node_type",
        "node_side",
        "node_position",
        "depot_node_identity",
        "route_declared_id",
        "route_from_endpoint",
        "route_to_endpoint",
        "route_mode",
        "route_capacity",
        "route_speed",
        "route_distance",
        "route_transit",
        "route_geometry_pair",
        "stockpile_config_omission",
        "network_config_typo",
        "stockpile_config_coercion",
        "network_config_coercion",
        "stockpile_config_changed",
        "network_config_changed",
        "integral_float_depot_enum",
        "integral_float_route_enum",
    ],
)
def test_v108_rejects_mutated_logistics_contract_atomically(
    mutation: str,
) -> None:
    payload = _enabled_payload()
    _, source = _engine_for(copy.deepcopy(payload), seed=8_308)
    invalid = source.get_state()
    _mutate_v108_logistics_checkpoint(invalid, mutation)

    _, target = _engine_for(copy.deepcopy(payload), seed=999_308)
    before = target.checkpoint()
    with pytest.raises(ValueError, match=r"(?i)checkpoint"):
        target.set_state(invalid)
    assert target.checkpoint() == before


@pytest.mark.parametrize(
    ("corruption", "match"),
    [
        (
            "future_accounting",
            r"(?i)logistics time exceeds checkpoint clock",
        ),
        (
            "clock_inconsistent_accumulator",
            r"(?i)accumulator.*(clock|elapsed)",
        ),
    ],
)
def test_checkpoint_rejects_logistics_time_inconsistent_with_clock_atomically(
    corruption: str,
    match: str,
) -> None:
    payload = _enabled_payload()
    payload["tick_duration_seconds"] = 300.0
    source_ctx, source = _engine_for(copy.deepcopy(payload), seed=8_208)
    for _ in range(5):
        assert source.step() is False
    elapsed_seconds = source_ctx.clock.elapsed.total_seconds()
    assert elapsed_seconds == pytest.approx(1500.0)

    invalid = source.get_state()
    logistics = invalid["context"]["logistics_runtime"]
    if corruption == "future_accounting":
        logistics["unit_last_accounted_seconds"][UNIT_ID] = (
            elapsed_seconds + 300.0
        )
    else:
        assert logistics[
            "elapsed_accumulator_seconds"
        ] == pytest.approx(elapsed_seconds)
        logistics["elapsed_accumulator_seconds"] = (
            elapsed_seconds - 300.0
        )

    _, target = _engine_for(copy.deepcopy(payload), seed=999_208)
    before = target.checkpoint()
    with pytest.raises(ValueError, match=match):
        target.set_state(invalid)
    assert target.checkpoint() == before


@pytest.mark.parametrize(
    ("value", "match"),
    [
        pytest.param(
            "3600",
            r"last_boundary_elapsed_seconds must be finite",
            id="invalid-type",
        ),
        pytest.param(
            1.0,
            r"last_boundary_elapsed_seconds is not on the configured cadence",
            id="off-cadence",
        ),
        pytest.param(
            3600.0,
            r"Last logistics boundary exceeds checkpoint clock",
            id="checkpoint-clock",
        ),
    ],
)
def test_checkpoint_rejects_invalid_last_boundary_atomically(
    value: Any,
    match: str,
) -> None:
    payload = _enabled_payload()
    payload["tick_duration_seconds"] = 300.0
    _, source = _engine_for(copy.deepcopy(payload), seed=8_408)
    for _ in range(5):
        assert source.step() is False
    invalid = source.get_state()
    logistics = invalid["context"]["logistics_runtime"]
    assert logistics["last_boundary_elapsed_seconds"] == pytest.approx(0.0)
    logistics["last_boundary_elapsed_seconds"] = value

    _, target = _engine_for(copy.deepcopy(payload), seed=999_408)
    before = target.checkpoint()
    with pytest.raises(ValueError, match=match):
        target.set_state(invalid)
    assert target.checkpoint() == before


def _reinforcement_payload(
    *,
    arrival_time_s: float,
    tick_duration_seconds: float,
) -> dict[str, Any]:
    payload = _enabled_payload()
    payload["tick_duration_seconds"] = tick_duration_seconds
    payload["reinforcements"] = [
        {
            "side": "blue",
            "arrival_time_s": arrival_time_s,
            "units": [{"unit_type": "m1a2", "count": 1}],
            "position": [200.0, 7475.0],
            "arrival_sigma": 0.0,
        },
    ]
    return payload


def test_boundary_reinforcement_skips_prior_interval_and_persists(
) -> None:
    payload = _reinforcement_payload(
        arrival_time_s=3600.0,
        tick_duration_seconds=3600.0,
    )
    dynamic_id = "reinforce_blue_0000_m1a2_0000"
    source_ctx, source = _engine_for(copy.deepcopy(payload), seed=9_108)
    first_events: list[SupplyDeliveredEvent] = []
    source_ctx.event_bus.subscribe(SupplyDeliveredEvent, first_events.append)

    assert source.step() is False
    assert _unit_quantity(source_ctx, dynamic_id) == pytest.approx(1.0)
    assert all(
        event.recipient_id != dynamic_id for event in first_events
    )
    runtime_state = source_ctx.logistics_runtime.get_state()
    assert runtime_state["unit_eligible_from_seconds"][
        dynamic_id
    ] == pytest.approx(3600.0)
    assert f"unit:{dynamic_id}" in runtime_state["supply_network"]["nodes"]
    assert (
        f"blue_water:{dynamic_id}"
        in runtime_state["supply_network"]["routes"]
    )

    checkpoint = source.checkpoint()
    source_continuation: list[SupplyDeliveredEvent] = []
    source_ctx.event_bus.subscribe(
        SupplyDeliveredEvent,
        source_continuation.append,
    )
    assert source.step() is False

    target_ctx, target = _engine_for(copy.deepcopy(payload), seed=1)
    target_continuation: list[SupplyDeliveredEvent] = []
    target_ctx.event_bus.subscribe(
        SupplyDeliveredEvent,
        target_continuation.append,
    )
    target.restore(checkpoint)
    assert json.loads(target.checkpoint()) == json.loads(checkpoint)
    assert _unit_quantity(target_ctx, dynamic_id) == pytest.approx(1.0)
    assert target.step() is False

    assert _unit_quantity(target_ctx, dynamic_id) == pytest.approx(3.0)
    assert json.loads(target.checkpoint()) == json.loads(source.checkpoint())
    assert _delivery_signature(target_continuation) == _delivery_signature(
        source_continuation,
    )


def test_midinterval_reinforcement_gets_positive_resupply_and_prorated_idle(
) -> None:
    payload = _reinforcement_payload(
        arrival_time_s=1800.0,
        tick_duration_seconds=1800.0,
    )
    dynamic_id = "reinforce_blue_0000_m1a2_0000"
    ctx, engine = _engine_for(payload, seed=10_108)
    delivered: list[SupplyDeliveredEvent] = []
    ctx.event_bus.subscribe(SupplyDeliveredEvent, delivered.append)

    assert engine.step() is False
    assert _unit_quantity(ctx, dynamic_id) == pytest.approx(1.0)
    assert delivered == []

    assert engine.step() is False
    dynamic_events = [
        event for event in delivered if event.recipient_id == dynamic_id
    ]
    assert len(dynamic_events) == 1
    assert dynamic_events[0].quantity == pytest.approx(3.0)
    assert _unit_quantity(ctx, dynamic_id) == pytest.approx(3.5)
    runtime_state = ctx.logistics_runtime.get_state()
    assert runtime_state["unit_last_accounted_seconds"][
        dynamic_id
    ] == pytest.approx(3600.0)


@pytest.mark.parametrize("bottleneck", ["route", "depot"])
def test_midinterval_reinforcement_prorates_route_and_depot_throughput(
    bottleneck: str,
) -> None:
    payload = _reinforcement_payload(
        arrival_time_s=1800.0,
        tick_duration_seconds=1800.0,
    )
    route = payload["logistics"]["route_templates"][0]
    route["transport_mode"] = "AIR"
    if bottleneck == "route":
        route["capacity_tons_per_hour"] = 0.004
    else:
        payload["sides"][0]["depots"][0][
            "throughput_tons_per_hour"
        ] = 0.004
    dynamic_id = "reinforce_blue_0000_m1a2_0000"
    ctx, engine = _engine_for(payload, seed=10_208)
    # Preserve an exact, non-empty authored initial roster while excluding
    # that control unit from the throughput competition under test.
    ctx.units_by_side["blue"][0].status = UnitStatus.DESTROYED
    delivered: list[SupplyDeliveredEvent] = []
    ctx.event_bus.subscribe(SupplyDeliveredEvent, delivered.append)

    assert engine.step() is False
    assert delivered == []
    assert engine.step() is False

    dynamic_events = [
        event for event in delivered if event.recipient_id == dynamic_id
    ]
    assert len(dynamic_events) == 1
    assert dynamic_events[0].quantity == pytest.approx(2.0)
    assert dynamic_events[0].quantity_tons == pytest.approx(0.002)
    assert _unit_quantity(ctx, dynamic_id) == pytest.approx(2.5)
    assert _depot_quantity(ctx) == pytest.approx(8.0)


def test_same_seed_runs_emit_identical_ordered_delivery_events() -> None:
    payload = _enabled_payload()
    payload["sides"][0]["units"] = [
        {"unit_type": "m1a2", "count": 2},
    ]
    payload["sides"][0]["depots"][0]["initial_inventory"] = [_item(5.0)]

    runs = []
    for _ in range(2):
        ctx, _, events = _run_with_deliveries(
            copy.deepcopy(payload),
            seed=11_108,
        )
        runs.append(
            (
                ctx.logistics_runtime.get_state(),
                _delivery_signature(events),
            ),
        )

    assert runs[1] == runs[0]
    assert [event[1] for event in runs[0][1]] == [
        "blue_m1a2_0000",
        "blue_m1a2_0001",
    ]
    assert [event[4] for event in runs[0][1]] == pytest.approx(
        [3.0, 2.0],
    )


def _hashseed_probe_result() -> dict[str, str]:
    payload = _enabled_payload()
    payload["sides"][0]["units"] = [
        {"unit_type": "m1a2", "count": 2},
    ]
    payload["sides"][0]["depots"][0]["initial_inventory"] = [_item(5.0)]
    _, engine, events = _run_with_deliveries(
        payload,
        steps=2,
        seed=11_108,
    )
    event_payload = json.dumps(
        _delivery_signature(events),
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "checkpoint_sha256": hashlib.sha256(
            engine.checkpoint(),
        ).hexdigest(),
        "events_sha256": hashlib.sha256(event_payload).hexdigest(),
    }


def test_canonical_output_is_independent_of_python_hash_seed() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    results: list[dict[str, str]] = []
    marker = "PHASE108_HASHSEED_RESULT="
    for hash_seed in ("1", "2"):
        environment = os.environ.copy()
        environment["PYTHONHASHSEED"] = hash_seed
        environment["PHASE108_HASHSEED_PROBE"] = "1"
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
            if line.startswith(marker)
        )
        results.append(json.loads(result_line.removeprefix(marker)))

    assert results[1] == results[0]


@pytest.mark.parametrize(
    ("connected", "expected_game_over", "expected_supply"),
    [
        (True, False, 0.9),
        (False, True, 0.1),
    ],
)
def test_real_supply_exhausted_outcome_diverges_at_condition_threshold(
    connected: bool,
    expected_game_over: bool,
    expected_supply: float,
) -> None:
    payload = _enabled_payload()
    blue_profile = payload["logistics"]["unit_profiles"][0]
    blue_profile["initial_inventory"] = [_item(0.2)]
    blue_profile["maximum_inventory"] = [_item(1.0)]
    blue_profile["idle_consumption_per_hour"] = [_item(0.1)]
    red_profile = payload["logistics"]["unit_profiles"][1]
    red_profile["initial_inventory"] = [_item(1.0)]
    red_profile["maximum_inventory"] = [_item(1.0)]
    red_profile["idle_consumption_per_hour"] = []
    if not connected:
        payload["logistics"]["route_templates"] = []

    ctx = _load_payload(payload, seed=12_108)
    condition = VictoryConditionConfig(
        type="supply_exhausted",
        params={"threshold": 0.2},
    )
    evaluator = VictoryEvaluator(
        objectives=[],
        conditions=[condition],
        event_bus=ctx.event_bus,
        config=VictoryEvaluatorConfig(
            supply_exhaustion_threshold=0.95,
        ),
    )
    engine = SimulationEngine(
        ctx,
        config=EngineConfig(resolution_closing_range_mult=0.0),
        campaign_config=_quiet_campaign(),
        victory_evaluator=evaluator,
    )
    victories: list[VictoryDeclaredEvent] = []
    ctx.event_bus.subscribe(VictoryDeclaredEvent, victories.append)

    assert engine.step() is expected_game_over
    assert ctx.stockpile_manager.get_supply_state(
        UNIT_ID,
    ) == pytest.approx(expected_supply)
    if connected:
        assert victories == []
    else:
        assert len(victories) == 1
        assert victories[0].condition_type == "supply_exhausted"
        assert victories[0].winning_side == "red"


if __name__ == "__main__" and os.environ.get(
    "PHASE108_HASHSEED_PROBE",
) == "1":
    print(
        "PHASE108_HASHSEED_RESULT="
        + json.dumps(
            _hashseed_probe_result(),
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ),
    )
