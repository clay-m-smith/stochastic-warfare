"""Phase 113 morale-owned aggregation integration proofs."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from stochastic_warfare.c2.orders.air_orders import ATOPlanningEngine
from stochastic_warfare.c2.roe import RoeEngine, RoeLevel
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Domain, Position
from stochastic_warfare.entities.base import Unit
from stochastic_warfare.morale.runtime import (
    MoraleRegistration,
    MoraleRuntime,
    MoraleStateRecord,
    MoraleTransitionCause,
)
from stochastic_warfare.morale.state import MoraleConfig, MoraleState
from stochastic_warfare.simulation.aggregation import (
    AggregationConfig,
    AggregationEngine,
)
from stochastic_warfare.simulation.runtime import (
    AnalysisVariant,
    RuntimeSession,
    SimulationRuntimeFactory,
)
from stochastic_warfare.simulation.scenario import (
    CampaignScenarioConfig,
    load_campaign_scenario_config,
)
from stochastic_warfare.simulation.tactical_targeting import (
    TacticalTargetingRuntime,
)


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
SCENARIO_PATH = (
    DATA_DIR / "scenarios" / "test_campaign_reinforce" / "scenario.yaml"
)
MAX_TICKS = 1_000_000
TIMESTAMP = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _record_state(record: MoraleStateRecord) -> dict[str, Any]:
    return {
        "current_state": int(record.current_state),
        "last_transition_time_s": record.last_transition_time_s,
        "last_check_time_s": record.last_check_time_s,
        "generation": record.generation,
    }


def _production_session(
    variant_id: str,
    *,
    seed: int = 113,
    config: CampaignScenarioConfig | None = None,
) -> RuntimeSession:
    variants = (AnalysisVariant(variant_id=variant_id),)
    factory = SimulationRuntimeFactory()
    prepared = (
        factory.prepare(SCENARIO_PATH, DATA_DIR, variants)
        if config is None
        else factory.prepare_config(
            config,
            DATA_DIR,
            variants,
            source_label=str(SCENARIO_PATH.resolve()),
        )
    )
    return prepared.build(
        variant_id,
        seed=seed,
        max_ticks=MAX_TICKS,
        strict_mode=True,
    )


def _base_context(
    *,
    unit_weapons: dict[str, Any] | None = None,
    unit_ids: tuple[str, ...] = ("u0", "u1", "u2"),
) -> tuple[SimpleNamespace, dict[str, MoraleStateRecord]]:
    units = [
        Unit(
            entity_id=unit_id,
            position=Position(float(index * 100), 0.0),
            name=f"Unit {index}",
            unit_type="base",
            side="blue",
            max_speed=10.0,
        )
        for index, unit_id in enumerate(unit_ids)
    ]
    record_templates = (
        MoraleStateRecord(
            MoraleState.BROKEN,
            last_transition_time_s=7.0,
            last_check_time_s=9.0,
            generation=3,
        ),
        MoraleStateRecord(
            MoraleState.BROKEN,
            last_transition_time_s=5.0,
            last_check_time_s=8.0,
            generation=2,
        ),
        MoraleStateRecord(
            MoraleState.SHAKEN,
            last_transition_time_s=4.0,
            last_check_time_s=4.0,
            generation=1,
        ),
        MoraleStateRecord(MoraleState.STEADY),
    )
    records = {
        unit_id: record_templates[index]
        for index, unit_id in enumerate(unit_ids)
    }
    runtime = MoraleRuntime(EventBus(), np.random.default_rng(113))
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
                unit_id: _record_state(record)
                for unit_id, record in records.items()
            },
            "suspended_archives": {},
        },
        expected_units=units_by_id,
        elapsed_time_s=10.0,
    )
    context = SimpleNamespace(
        units_by_side={"blue": list(units)},
        morale_runtime=runtime,
        morale_states=runtime.states,
        unit_weapons=(
            unit_weapons
            if unit_weapons is not None
            else {unit_id: () for unit_id in units_by_id}
        ),
        unit_sensor_attachments={unit_id: () for unit_id in units_by_id},
        unit_sensors={unit_id: () for unit_id in units_by_id},
        equipment_resolutions={unit_id: () for unit_id in units_by_id},
        tactical_targeting=TacticalTargetingRuntime(
            sensing_aware_standoff_enabled=True,
            unit_sides={unit_id: "blue" for unit_id in units_by_id},
        ),
        stockpile_manager=None,
        order_execution=None,
    )
    return context, records


class _FailingPopDict(dict[str, Any]):
    """Mutable production-owner stand-in with one injected late failure."""

    def __init__(self, values: dict[str, Any]) -> None:
        super().__init__(values)
        self.fail_key = ""
        self.armed = False

    def pop(self, key: str, *default: Any) -> Any:
        if self.armed and key == self.fail_key:
            self.armed = False
            raise RuntimeError("phase113 injected late mapping failure")
        return super().pop(key, *default)


class _FailingTargetingRuntime(TacticalTargetingRuntime):
    """Forged owner whose virtual commit would mutate before failing."""

    armed = True

    def replace_registered_units(
        self,
        *,
        expected_current: Mapping[str, str],
        replacement: Mapping[str, str],
    ) -> None:
        super().replace_registered_units(
            expected_current=expected_current,
            replacement=replacement,
        )
        if self.armed:
            self.armed = False
            raise RuntimeError("phase115 injected targeting commit failure")


def test_aggregation_rejects_ownerless_empty_projection_before_mutation() -> None:
    context, _records = _base_context()
    unit_ids = sorted(
        unit.entity_id for unit in context.units_by_side["blue"]
    )
    context.morale_runtime = None
    context.morale_states = {}
    engine = AggregationEngine(
        AggregationConfig(
            enable_aggregation=True,
            min_units_to_aggregate=2,
        ),
        rng=np.random.default_rng(113),
        event_bus=EventBus(),
    )

    with pytest.raises(RuntimeError, match="require MoraleRuntime"):
        engine.aggregate(unit_ids, context)

    assert [
        unit.entity_id for unit in context.units_by_side["blue"]
    ] == unit_ids
    assert engine.get_state()["aggregates"] == {}


def test_disaggregation_rejects_ownerless_empty_projection_before_mutation() -> None:
    context, _records = _base_context()
    unit_ids = sorted(
        unit.entity_id for unit in context.units_by_side["blue"]
    )
    engine = AggregationEngine(
        AggregationConfig(
            enable_aggregation=True,
            min_units_to_aggregate=2,
        ),
        rng=np.random.default_rng(113),
        event_bus=EventBus(),
    )
    aggregate = engine.aggregate(unit_ids, context)
    assert aggregate is not None
    context.morale_runtime = None
    context.morale_states = {}
    roster_before = [
        unit.entity_id for unit in context.units_by_side["blue"]
    ]

    with pytest.raises(RuntimeError, match="require MoraleRuntime"):
        engine.disaggregate(aggregate.aggregate_id, context)

    assert [
        unit.entity_id for unit in context.units_by_side["blue"]
    ] == roster_before
    assert aggregate.aggregate_id in engine.get_state()["aggregates"]


def test_aggregation_rejects_ato_roster_owner_before_mutation() -> None:
    context, _records = _base_context()
    context.ato_engine = ATOPlanningEngine(EventBus())
    unit_ids = [unit.entity_id for unit in context.units_by_side["blue"]]
    engine = AggregationEngine(
        AggregationConfig(enable_aggregation=True, min_units_to_aggregate=2),
        rng=np.random.default_rng(113),
        event_bus=EventBus(),
    )
    roster_before = tuple(context.units_by_side["blue"])
    morale_before = copy.deepcopy(context.morale_runtime.get_state())

    with pytest.raises(ValueError, match="ato_engine"):
        engine.aggregate(unit_ids, context)

    assert tuple(context.units_by_side["blue"]) == roster_before
    assert context.morale_runtime.get_state() == morale_before
    assert engine.get_state()["aggregates"] == {}


def test_aggregation_rejects_populated_roe_owner_before_mutation() -> None:
    context, _records = _base_context()
    context.roe_engine = RoeEngine(EventBus())
    context.roe_engine.set_unit_roe("u0", RoeLevel.WEAPONS_HOLD)
    unit_ids = [unit.entity_id for unit in context.units_by_side["blue"]]
    engine = AggregationEngine(
        AggregationConfig(enable_aggregation=True, min_units_to_aggregate=2),
        rng=np.random.default_rng(113),
        event_bus=EventBus(),
    )
    roster_before = tuple(context.units_by_side["blue"])
    morale_before = copy.deepcopy(context.morale_runtime.get_state())
    roe_before = copy.deepcopy(context.roe_engine.get_state())

    with pytest.raises(ValueError, match="roe_engine"):
        engine.aggregate(unit_ids, context)

    assert tuple(context.units_by_side["blue"]) == roster_before
    assert context.morale_runtime.get_state() == morale_before
    assert context.roe_engine.get_state() == roe_before
    assert engine.get_state()["aggregates"] == {}


@pytest.mark.parametrize(
    "corruption",
    ("missing_attribute", "mismatched_owner", "duplicate_name"),
)
def test_aggregation_rejects_malformed_context_owner_registry_before_mutation(
    corruption: str,
) -> None:
    context, _records = _base_context()
    registered_owner = object()
    if corruption == "missing_attribute":
        owner_items = (("ghost_engine", registered_owner),)
    else:
        context.roe_engine = object()
        owner_items = (("roe_engine", registered_owner),)
        if corruption == "duplicate_name":
            context.roe_engine = registered_owner
            owner_items = (*owner_items, owner_items[0])
    context._checkpoint_engines = lambda: owner_items
    unit_ids = [unit.entity_id for unit in context.units_by_side["blue"]]
    engine = AggregationEngine(
        AggregationConfig(enable_aggregation=True, min_units_to_aggregate=2),
        rng=np.random.default_rng(113),
        event_bus=EventBus(),
    )
    roster_before = tuple(context.units_by_side["blue"])
    morale_before = copy.deepcopy(context.morale_runtime.get_state())

    with pytest.raises(ValueError, match="state-owner registry"):
        engine.aggregate(unit_ids, context)

    assert tuple(context.units_by_side["blue"]) == roster_before
    assert context.morale_runtime.get_state() == morale_before
    assert engine.get_state()["aggregates"] == {}


def test_aggregation_rejects_mixed_domains_before_mutation() -> None:
    context, _records = _base_context(unit_ids=("ground", "air"))
    context.units_by_side["blue"][1].domain = Domain.AERIAL
    engine = AggregationEngine(
        AggregationConfig(enable_aggregation=True, min_units_to_aggregate=2),
        rng=np.random.default_rng(113),
        event_bus=EventBus(),
    )
    roster_before = tuple(context.units_by_side["blue"])
    morale_before = copy.deepcopy(context.morale_runtime.get_state())

    with pytest.raises(ValueError, match="share one exact domain"):
        engine.aggregate(["ground", "air"], context)

    assert tuple(context.units_by_side["blue"]) == roster_before
    assert context.morale_runtime.get_state() == morale_before
    assert engine.get_state()["aggregates"] == {}


def test_production_equipped_aggregation_rejects_rem016_atomically() -> None:
    session = _production_session("phase113-aggregation-production")
    context = session.context
    constituent_ids = sorted(
        unit.entity_id for unit in context.units_by_side["red"]
    )
    before = {
        "roster": {
            side: tuple(units)
            for side, units in context.units_by_side.items()
        },
        "morale": copy.deepcopy(context.morale_runtime.get_state()),
        "weapons": dict(context.unit_weapons),
        "sensor_attachments": dict(context.unit_sensor_attachments),
        "sensors": dict(context.unit_sensors),
        "resolutions": dict(context.equipment_resolutions),
        "targeting": copy.deepcopy(context.tactical_targeting.get_state()),
        "aggregation": copy.deepcopy(context.aggregation_engine.get_state()),
        "rng": copy.deepcopy(context.rng_manager.get_state()),
    }

    with pytest.raises(ValueError, match="REM-016"):
        context.aggregation_engine.aggregate(constituent_ids, context)

    assert {
        side: tuple(units)
        for side, units in context.units_by_side.items()
    } == before["roster"]
    assert context.morale_runtime.get_state() == before["morale"]
    assert context.unit_weapons == before["weapons"]
    assert context.unit_sensor_attachments == before["sensor_attachments"]
    assert context.unit_sensors == before["sensors"]
    assert context.equipment_resolutions == before["resolutions"]
    assert context.tactical_targeting.get_state() == before["targeting"]
    assert context.aggregation_engine.get_state() == before["aggregation"]
    assert context.rng_manager.get_state() == before["rng"]


def test_equipmentless_evolved_proxy_rejects_before_roster_mutation() -> None:
    context, _records = _base_context()
    engine = AggregationEngine(
        AggregationConfig(
            enable_aggregation=True,
            min_units_to_aggregate=2,
        ),
        rng=np.random.default_rng(13),
    )
    runtime = context.morale_runtime
    constituent_ids = sorted(
        unit.entity_id for unit in context.units_by_side["blue"]
    )
    aggregate = engine.aggregate(constituent_ids, context)
    assert aggregate is not None
    aggregate_id = aggregate.aggregate_id
    baseline = runtime.record_for(aggregate_id)
    assert baseline.current_state is MoraleState.BROKEN

    assert runtime.force_transition(
        aggregate_id,
        MoraleState.ROUTED,
        cause=MoraleTransitionCause.MELEE_ROUT,
        timestamp=TIMESTAMP + timedelta(seconds=10.0),
        current_time_s=10.0,
    ) is MoraleState.ROUTED
    evolved = runtime.record_for(aggregate_id)
    assert evolved.current_state is MoraleState.ROUTED
    assert evolved.generation > baseline.generation

    roster_before = {
        side: tuple(units)
        for side, units in context.units_by_side.items()
    }
    runtime_before = copy.deepcopy(runtime.get_state())
    aggregation_before = copy.deepcopy(
        engine.get_state(),
    )

    with pytest.raises(ValueError, match="proxy .* evolved"):
        engine.disaggregate(aggregate_id, context)

    assert {
        side: tuple(units)
        for side, units in context.units_by_side.items()
    } == roster_before
    assert runtime.get_state() == runtime_before
    assert engine.get_state() == aggregation_before


def test_aggregate_id_collision_rejects_before_any_owner_mutation() -> None:
    context, _records = _base_context(
        unit_ids=("agg_0000", "u1", "u2", "u3"),
    )
    engine = AggregationEngine(
        AggregationConfig(
            enable_aggregation=True,
            min_units_to_aggregate=2,
        ),
        rng=np.random.default_rng(113),
    )
    before = {
        "roster": tuple(context.units_by_side["blue"]),
        "morale": copy.deepcopy(context.morale_runtime.get_state()),
        "weapons": dict(context.unit_weapons),
        "sensor_attachments": dict(context.unit_sensor_attachments),
        "sensors": dict(context.unit_sensors),
        "resolutions": dict(context.equipment_resolutions),
        "targeting": copy.deepcopy(context.tactical_targeting.get_state()),
        "aggregation": copy.deepcopy(engine.get_state()),
        "rng": copy.deepcopy(engine._rng.bit_generator.state),
    }

    with pytest.raises(ValueError, match="Aggregate ID .* collides"):
        engine.aggregate(["u1", "u2"], context)

    assert tuple(context.units_by_side["blue"]) == before["roster"]
    assert context.morale_runtime.get_state() == before["morale"]
    assert context.unit_weapons == before["weapons"]
    assert context.unit_sensor_attachments == before["sensor_attachments"]
    assert context.unit_sensors == before["sensors"]
    assert context.equipment_resolutions == before["resolutions"]
    assert context.tactical_targeting.get_state() == before["targeting"]
    assert engine.get_state() == before["aggregation"]
    assert engine._rng.bit_generator.state == before["rng"]


def test_targeting_runtime_subclass_rejects_before_every_owner_mutation() -> None:
    context, _records = _base_context()
    context.tactical_targeting = _FailingTargetingRuntime(
        sensing_aware_standoff_enabled=True,
        unit_sides={unit_id: "blue" for unit_id in context.unit_weapons},
    )
    engine = AggregationEngine(
        AggregationConfig(
            enable_aggregation=True,
            min_units_to_aggregate=2,
        ),
        rng=np.random.default_rng(113),
    )
    before = {
        "roster": tuple(context.units_by_side["blue"]),
        "morale": copy.deepcopy(context.morale_runtime.get_state()),
        "weapons": dict(context.unit_weapons),
        "sensor_attachments": dict(context.unit_sensor_attachments),
        "sensors": dict(context.unit_sensors),
        "resolutions": dict(context.equipment_resolutions),
        "targeting": copy.deepcopy(context.tactical_targeting.get_state()),
        "aggregation": copy.deepcopy(engine.get_state()),
    }

    with pytest.raises(ValueError, match="exact TacticalTargetingRuntime"):
        engine.aggregate(sorted(context.unit_weapons), context)

    assert tuple(context.units_by_side["blue"]) == before["roster"]
    assert context.morale_runtime.get_state() == before["morale"]
    assert context.unit_weapons == before["weapons"]
    assert context.unit_sensor_attachments == before["sensor_attachments"]
    assert context.unit_sensors == before["sensors"]
    assert context.equipment_resolutions == before["resolutions"]
    assert context.tactical_targeting.get_state() == before["targeting"]
    assert context.tactical_targeting.armed is True
    assert engine.get_state() == before["aggregation"]


def test_base_unit_empty_attachment_roundtrip_restores_exact_records() -> None:
    context, original_records = _base_context()
    engine = AggregationEngine(
        AggregationConfig(
            enable_aggregation=True,
            min_units_to_aggregate=2,
        ),
        rng=np.random.default_rng(113),
    )
    original_units = {
        unit.entity_id: unit.get_state()
        for unit in context.units_by_side["blue"]
    }
    morale_view = context.morale_states

    aggregate = engine.aggregate(sorted(original_units), context)

    assert aggregate is not None
    assert context.morale_states is morale_view
    assert context.morale_runtime.record_for(
        aggregate.aggregate_id
    ) == original_records["u0"]
    assert engine.disaggregate(aggregate.aggregate_id, context) == [
        "u0",
        "u1",
        "u2",
    ]
    assert context.morale_states is morale_view
    assert dict(context.morale_runtime.records) == original_records
    assert context.morale_runtime.get_state()["suspended_archives"] == {}
    assert {
        unit.entity_id: unit.get_state()
        for unit in context.units_by_side["blue"]
    } == original_units
    expected_empty_loadouts = {
        unit_id: () for unit_id in sorted(original_units)
    }
    assert context.unit_weapons == expected_empty_loadouts
    assert context.unit_sensor_attachments == expected_empty_loadouts
    assert context.unit_sensors == expected_empty_loadouts
    assert context.equipment_resolutions == expected_empty_loadouts
    assert dict(context.tactical_targeting.registered_unit_sides) == {
        unit_id: "blue" for unit_id in sorted(original_units)
    }


def test_partial_aggregation_roundtrip_preserves_exact_roster_order() -> None:
    context, _records = _base_context(unit_ids=("u0", "u1", "u2", "u3"))
    engine = AggregationEngine(
        AggregationConfig(enable_aggregation=True, min_units_to_aggregate=2),
        rng=np.random.default_rng(113),
        event_bus=EventBus(),
    )
    before = tuple(context.units_by_side["blue"])

    aggregate = engine.aggregate(["u1", "u2"], context)

    assert aggregate is not None
    assert [
        unit.entity_id for unit in context.units_by_side["blue"]
    ] == ["u0", aggregate.aggregate_id, "u3"]
    assert [
        snapshot.original_index
        for snapshot in aggregate.constituent_snapshots
    ] == [1, 2]

    assert engine.disaggregate(aggregate.aggregate_id, context) == ["u1", "u2"]
    assert tuple(context.units_by_side["blue"]) == before


@pytest.mark.parametrize("operation", ["aggregate", "disaggregate"])
def test_late_failure_rolls_back_morale_and_roster_in_place(
    operation: str,
) -> None:
    weapons = _FailingPopDict({
        "u0": (),
        "u1": (),
        "u2": (),
    })
    context, _records = _base_context(unit_weapons=weapons)
    engine = AggregationEngine(
        AggregationConfig(
            enable_aggregation=True,
            min_units_to_aggregate=2,
        ),
        rng=np.random.default_rng(113),
    )
    unit_ids = ["u0", "u1", "u2"]
    aggregate = None
    if operation == "disaggregate":
        aggregate = engine.aggregate(unit_ids, context)
        assert aggregate is not None
        weapons.fail_key = aggregate.aggregate_id
    else:
        weapons.fail_key = unit_ids[0]
    weapons.armed = True

    morale_view = context.morale_states
    roster_mapping = context.units_by_side
    blue_list = context.units_by_side["blue"]
    roster_before = tuple(blue_list)
    runtime_before = copy.deepcopy(context.morale_runtime.get_state())
    aggregation_before = copy.deepcopy(engine.get_state())
    loadouts_before = {
        "weapons": dict(context.unit_weapons),
        "sensor_attachments": dict(context.unit_sensor_attachments),
        "sensors": dict(context.unit_sensors),
        "resolutions": dict(context.equipment_resolutions),
    }
    targeting_before = copy.deepcopy(context.tactical_targeting.get_state())

    with pytest.raises(
        RuntimeError,
        match="phase113 injected late mapping failure",
    ):
        if operation == "aggregate":
            engine.aggregate(unit_ids, context)
        else:
            engine.disaggregate(aggregate.aggregate_id, context)

    assert context.morale_states is morale_view
    assert context.units_by_side is roster_mapping
    assert context.units_by_side["blue"] is blue_list
    assert tuple(blue_list) == roster_before
    assert context.morale_runtime.get_state() == runtime_before
    assert engine.get_state() == aggregation_before
    assert dict(context.unit_weapons) == loadouts_before["weapons"]
    assert (
        context.unit_sensor_attachments
        == loadouts_before["sensor_attachments"]
    )
    assert context.unit_sensors == loadouts_before["sensors"]
    assert context.equipment_resolutions == loadouts_before["resolutions"]
    assert context.tactical_targeting.get_state() == targeting_before

    if operation == "aggregate":
        assert engine.aggregate(unit_ids, context) is not None
    else:
        assert engine.disaggregate(aggregate.aggregate_id, context) == unit_ids
