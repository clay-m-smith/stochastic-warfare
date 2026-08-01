"""Phase 113 morale-owned aggregation integration proofs."""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position
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
) -> tuple[SimpleNamespace, dict[str, MoraleStateRecord]]:
    units = [
        Unit(
            entity_id=f"u{index}",
            position=Position(float(index * 100), 0.0),
            name=f"Unit {index}",
            unit_type="base",
            side="blue",
            max_speed=10.0,
        )
        for index in range(3)
    ]
    records = {
        "u0": MoraleStateRecord(
            MoraleState.BROKEN,
            last_transition_time_s=7.0,
            last_check_time_s=9.0,
            generation=3,
        ),
        "u1": MoraleStateRecord(
            MoraleState.BROKEN,
            last_transition_time_s=5.0,
            last_check_time_s=8.0,
            generation=2,
        ),
        "u2": MoraleStateRecord(
            MoraleState.SHAKEN,
            last_transition_time_s=4.0,
            last_check_time_s=4.0,
            generation=1,
        ),
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
        unit_weapons=(unit_weapons if unit_weapons is not None else {}),
        unit_sensors={},
        equipment_resolutions={},
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


def test_production_aggregation_uses_runtime_archive_as_only_morale_owner() -> None:
    session = _production_session("phase113-aggregation-production")
    context = session.context
    runtime = context.morale_runtime
    constituent_ids = sorted(
        unit.entity_id for unit in context.units_by_side["red"]
    )
    original_records = {
        unit_id: runtime.record_for(unit_id)
        for unit_id in constituent_ids
    }

    aggregate = context.aggregation_engine.aggregate(
        constituent_ids,
        context,
    )

    assert aggregate is not None
    roster_ids = {unit.entity_id for unit in context.all_units()}
    assert set(runtime.records) == roster_ids == set(context.morale_states)
    assert aggregate.aggregate_id in roster_ids
    assert set(constituent_ids).isdisjoint(roster_ids)
    expected_baseline = original_records[constituent_ids[0]]
    assert runtime.record_for(aggregate.aggregate_id) == expected_baseline
    morale_state = runtime.get_state()
    archive = morale_state["suspended_archives"][aggregate.aggregate_id]
    assert archive["proxy_baseline"] == _record_state(expected_baseline)
    assert archive["constituent_records"] == {
        unit_id: _record_state(original_records[unit_id])
        for unit_id in constituent_ids
    }
    aggregate_state = context.aggregation_engine.get_state()["aggregates"][
        aggregate.aggregate_id
    ]
    assert "morale_state" not in aggregate_state
    assert all(
        "morale_state" not in snapshot
        for snapshot in aggregate_state["snapshots"]
    )


def test_production_evolved_proxy_rejects_before_roster_mutation() -> None:
    raw = load_campaign_scenario_config(SCENARIO_PATH).model_dump(
        mode="python",
    )
    raw["calibration_overrides"]["morale"].update(
        {
            "base_degrade_rate": 0.0,
            "base_recover_rate": 0.8,
            "leadership_weight": 0.0,
            "cohesion_weight": 0.0,
            "force_ratio_weight": 0.0,
            "transition_cooldown_s": 0.0,
        },
    )
    config = CampaignScenarioConfig.model_validate(raw)
    session = _production_session(
        "phase113-aggregation-evolved-proxy",
        seed=13,
        config=config,
    )
    context = session.context
    runtime = context.morale_runtime
    constituent_ids = sorted(
        unit.entity_id for unit in context.units_by_side["red"]
    )
    baseline_source = constituent_ids[0]

    assert runtime.check_transition(
        baseline_source,
        1.0,
        1.0,
        False,
        0.0,
        0.01,
        timestamp=TIMESTAMP + timedelta(seconds=1.0),
        current_time_s=1.0,
    ) is MoraleState.SHAKEN
    assert runtime.check_transition(
        baseline_source,
        1.0,
        1.0,
        False,
        0.0,
        0.01,
        timestamp=TIMESTAMP + timedelta(seconds=2.0),
        current_time_s=2.0,
    ) is MoraleState.BROKEN
    aggregate = context.aggregation_engine.aggregate(
        constituent_ids,
        context,
    )
    assert aggregate is not None
    aggregate_id = aggregate.aggregate_id
    baseline = runtime.record_for(aggregate_id)
    assert baseline.current_state is MoraleState.BROKEN

    assert runtime.force_transition(
        aggregate_id,
        MoraleState.ROUTED,
        cause=MoraleTransitionCause.MELEE_ROUT,
        timestamp=TIMESTAMP + timedelta(seconds=3.0),
        current_time_s=3.0,
    ) is MoraleState.ROUTED
    recovered = MoraleState.ROUTED
    logical_time_s = 3.0
    while recovered is MoraleState.ROUTED:
        logical_time_s += 1.0
        recovered = runtime.check_transition(
            aggregate_id,
            0.0,
            0.0,
            False,
            0.0,
            1.0,
            timestamp=TIMESTAMP + timedelta(seconds=logical_time_s),
            current_time_s=logical_time_s,
        )
        assert logical_time_s <= 5.0
    assert recovered is MoraleState.BROKEN
    evolved = runtime.record_for(aggregate_id)
    assert evolved.current_state is baseline.current_state
    assert evolved.generation > baseline.generation

    roster_before = {
        side: tuple(units)
        for side, units in context.units_by_side.items()
    }
    runtime_before = copy.deepcopy(runtime.get_state())
    aggregation_before = copy.deepcopy(
        context.aggregation_engine.get_state(),
    )

    with pytest.raises(ValueError, match="proxy .* evolved"):
        context.aggregation_engine.disaggregate(aggregate_id, context)

    assert {
        side: tuple(units)
        for side, units in context.units_by_side.items()
    } == roster_before
    assert runtime.get_state() == runtime_before
    assert context.aggregation_engine.get_state() == aggregation_before


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
    assert context.unit_weapons == {}
    assert context.unit_sensors == {}
    assert context.equipment_resolutions == {}


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
    weapons_before = dict(weapons)

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
    assert dict(weapons) == weapons_before

    if operation == "aggregate":
        assert engine.aggregate(unit_ids, context) is not None
    else:
        assert engine.disaggregate(aggregate.aggregate_id, context) == unit_ids
