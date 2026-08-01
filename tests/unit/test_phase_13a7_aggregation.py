"""Phase 13a-7: Force aggregation/disaggregation tests."""

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.morale.runtime import MoraleRegistration, MoraleRuntime
from stochastic_warfare.morale.state import MoraleState
from stochastic_warfare.simulation.aggregation import (
    AggregationConfig,
    AggregationEngine,
)


def _rng() -> np.random.Generator:
    return np.random.default_rng(0)


def _make_unit(entity_id: str, side: str = "blue", pos: Position = Position(0, 0),
               unit_type: str = "infantry") -> Unit:
    return Unit(entity_id=entity_id, position=pos, side=side, unit_type=unit_type)


@dataclass
class _AggregationContext:
    """Typed aggregation boundary with an explicit morale owner."""

    event_bus: EventBus
    units_by_side: dict[str, list[Unit]]
    morale_runtime: MoraleRuntime | None
    morale_states: Mapping[str, MoraleState]
    unit_weapons: dict[str, list[object]]
    unit_sensors: dict[str, list[object]]
    equipment_resolutions: dict[str, tuple[object, ...]]
    stockpile_manager: object | None
    order_execution: object | None


def _copy_roster(
    units_by_side: Mapping[str, list[Unit]] | None,
) -> dict[str, list[Unit]]:
    return {
        side: list(units)
        for side, units in (units_by_side or {}).items()
    }


def _make_ctx(
    units_by_side: Mapping[str, list[Unit]] | None = None,
    morale_states: Mapping[str, MoraleState] | None = None,
) -> _AggregationContext:
    """Build an exactly registered runtime-owned aggregation context."""
    roster = _copy_roster(units_by_side)
    units = {
        unit.entity_id: unit
        for side_units in roster.values()
        for unit in side_units
    }
    if len(units) != sum(len(side_units) for side_units in roster.values()):
        raise ValueError("Test roster contains duplicate unit IDs")

    initial_states = (
        {unit_id: MoraleState.STEADY for unit_id in units}
        if morale_states is None
        else dict(morale_states)
    )
    if set(initial_states) != set(units):
        raise ValueError("Test morale topology must exactly match the roster")

    event_bus = EventBus()
    runtime = MoraleRuntime(event_bus, _rng())
    runtime.register_units(
        tuple(
            MoraleRegistration(unit_id, initial_states[unit_id])
            for unit_id in sorted(units)
        ),
        units,
    )
    runtime.validate_bindings(units)
    return _AggregationContext(
        event_bus=event_bus,
        units_by_side=roster,
        morale_runtime=runtime,
        morale_states=runtime.states,
        unit_weapons={},
        unit_sensors={},
        equipment_resolutions={},
        stockpile_manager=None,
        order_execution=None,
    )


def _make_ownerless_ctx(
    units_by_side: Mapping[str, list[Unit]],
    morale_states: Mapping[str, MoraleState],
) -> _AggregationContext:
    """Build the deliberate legacy-ownerless failure control."""
    return _AggregationContext(
        event_bus=EventBus(),
        units_by_side=_copy_roster(units_by_side),
        morale_runtime=None,
        morale_states=dict(morale_states),
        unit_weapons={},
        unit_sensors={},
        equipment_resolutions={},
        stockpile_manager=None,
        order_execution=None,
    )


class TestUnitSnapshot:
    def test_snapshot_captures_unit_state(self):
        engine = AggregationEngine(rng=_rng())
        unit = _make_unit("u1", "blue", Position(100, 200))
        ctx = _make_ctx({"blue": [unit]})
        snap = engine.snapshot_unit(unit, ctx)
        assert snap.unit_state["entity_id"] == "u1"
        assert snap.original_side == "blue"

    def test_snapshot_does_not_duplicate_morale(self):
        engine = AggregationEngine(rng=_rng())
        unit = _make_unit("u1")
        ctx = _make_ctx({"blue": [unit]}, {"u1": MoraleState.SHAKEN})
        snap = engine.snapshot_unit(unit, ctx)
        assert not hasattr(snap, "morale_state")

    def test_snapshot_state_omits_morale_key(self):
        engine = AggregationEngine(rng=_rng())
        unit = _make_unit("u1")
        ctx = _make_ctx({"blue": [unit]})
        snap = engine.snapshot_unit(unit, ctx)
        assert "morale_state" not in snap.__dict__


class TestAggregation:
    def test_aggregate_basic(self):
        config = AggregationConfig(enable_aggregation=True, min_units_to_aggregate=2)
        engine = AggregationEngine(config=config, rng=_rng())
        units = [_make_unit(f"u{i}", "blue", Position(100 * i, 0)) for i in range(4)]
        ctx = _make_ctx({"blue": units})
        agg = engine.aggregate([u.entity_id for u in units], ctx)
        assert agg is not None
        assert len(agg.constituent_snapshots) == 4
        assert agg.side == "blue"

    def test_aggregate_removes_units_from_context(self):
        config = AggregationConfig(enable_aggregation=True, min_units_to_aggregate=2)
        engine = AggregationEngine(config=config, rng=_rng())
        units = [_make_unit(f"u{i}", "blue") for i in range(4)]
        ctx = _make_ctx({"blue": list(units)})
        engine.aggregate([u.entity_id for u in units], ctx)
        # Original units should be gone, proxy should be present
        blue_ids = {u.entity_id for u in ctx.units_by_side["blue"]}
        assert "u0" not in blue_ids
        assert any(uid.startswith("agg_") for uid in blue_ids)

    def test_aggregate_proxy_in_units_by_side(self):
        config = AggregationConfig(enable_aggregation=True, min_units_to_aggregate=2)
        engine = AggregationEngine(config=config, rng=_rng())
        units = [_make_unit(f"u{i}", "blue") for i in range(4)]
        ctx = _make_ctx({"blue": list(units)})
        agg = engine.aggregate([u.entity_id for u in units], ctx)
        proxy = [u for u in ctx.units_by_side["blue"] if u.entity_id == agg.aggregate_id]
        assert len(proxy) == 1
        assert proxy[0].status == UnitStatus.ACTIVE

    def test_aggregate_centroid_position(self):
        config = AggregationConfig(enable_aggregation=True, min_units_to_aggregate=2)
        engine = AggregationEngine(config=config, rng=_rng())
        units = [
            _make_unit("u0", "blue", Position(0, 0)),
            _make_unit("u1", "blue", Position(1000, 0)),
        ]
        ctx = _make_ctx({"blue": list(units)})
        agg = engine.aggregate(["u0", "u1"], ctx)
        assert agg.position.easting == pytest.approx(500.0)

    def test_aggregate_uses_worst_runtime_owned_morale(self):
        config = AggregationConfig(enable_aggregation=True, min_units_to_aggregate=2)
        engine = AggregationEngine(config=config, rng=_rng())
        units = [_make_unit("u0", "blue"), _make_unit("u1", "blue")]
        morale = {"u0": MoraleState.STEADY, "u1": MoraleState.BROKEN}
        ctx = _make_ctx({"blue": list(units)}, morale)

        agg = engine.aggregate(["u0", "u1"], ctx)

        assert ctx.morale_states == {agg.aggregate_id: MoraleState.BROKEN}

    def test_aggregate_mixed_types(self):
        config = AggregationConfig(enable_aggregation=True, min_units_to_aggregate=2)
        engine = AggregationEngine(config=config, rng=_rng())
        units = [
            _make_unit("u0", "blue", unit_type="infantry"),
            _make_unit("u1", "blue", unit_type="armor"),
        ]
        ctx = _make_ctx({"blue": list(units)})
        agg = engine.aggregate(["u0", "u1"], ctx)
        assert agg.unit_type == "mixed"

    def test_aggregate_same_type(self):
        config = AggregationConfig(enable_aggregation=True, min_units_to_aggregate=2)
        engine = AggregationEngine(config=config, rng=_rng())
        units = [_make_unit(f"u{i}", "blue", unit_type="infantry") for i in range(3)]
        ctx = _make_ctx({"blue": list(units)})
        agg = engine.aggregate([u.entity_id for u in units], ctx)
        assert agg.unit_type == "infantry"

    def test_aggregate_too_few_units(self):
        config = AggregationConfig(enable_aggregation=True, min_units_to_aggregate=5)
        engine = AggregationEngine(config=config, rng=_rng())
        units = [_make_unit(f"u{i}", "blue") for i in range(3)]
        ctx = _make_ctx({"blue": list(units)})
        agg = engine.aggregate([u.entity_id for u in units], ctx)
        assert agg is None

    def test_aggregate_different_sides_rejected(self):
        config = AggregationConfig(enable_aggregation=True, min_units_to_aggregate=2)
        engine = AggregationEngine(config=config, rng=_rng())
        units = [_make_unit("u0", "blue"), _make_unit("u1", "red")]
        ctx = _make_ctx({"blue": [units[0]], "red": [units[1]]})
        agg = engine.aggregate(["u0", "u1"], ctx)
        assert agg is None


class TestDisaggregation:
    def test_disaggregate_restores_units(self):
        config = AggregationConfig(enable_aggregation=True, min_units_to_aggregate=2)
        engine = AggregationEngine(config=config, rng=_rng())
        units = [_make_unit(f"u{i}", "blue", Position(i * 100, 0)) for i in range(4)]
        ctx = _make_ctx({"blue": list(units)})
        agg = engine.aggregate([u.entity_id for u in units], ctx)

        restored = engine.disaggregate(agg.aggregate_id, ctx)
        assert len(restored) == 4
        assert set(restored) == {"u0", "u1", "u2", "u3"}

    def test_disaggregate_removes_proxy(self):
        config = AggregationConfig(enable_aggregation=True, min_units_to_aggregate=2)
        engine = AggregationEngine(config=config, rng=_rng())
        units = [_make_unit(f"u{i}", "blue") for i in range(4)]
        ctx = _make_ctx({"blue": list(units)})
        agg = engine.aggregate([u.entity_id for u in units], ctx)
        engine.disaggregate(agg.aggregate_id, ctx)

        blue_ids = {u.entity_id for u in ctx.units_by_side["blue"]}
        assert agg.aggregate_id not in blue_ids
        assert "u0" in blue_ids

    def test_disaggregate_restores_runtime_owned_morale(self):
        config = AggregationConfig(enable_aggregation=True, min_units_to_aggregate=2)
        engine = AggregationEngine(config=config, rng=_rng())
        units = [_make_unit("u0", "blue"), _make_unit("u1", "blue")]
        morale = {"u0": MoraleState.STEADY, "u1": MoraleState.SHAKEN}
        ctx = _make_ctx({"blue": list(units)}, morale)
        agg = engine.aggregate(["u0", "u1"], ctx)

        engine.disaggregate(agg.aggregate_id, ctx)

        assert ctx.morale_states == morale

    def test_ownerless_morale_rejection_precedes_roster_mutation(self):
        config = AggregationConfig(enable_aggregation=True, min_units_to_aggregate=2)
        engine = AggregationEngine(config=config, rng=_rng())
        units = [_make_unit("u0", "blue"), _make_unit("u1", "blue")]
        morale = {"u0": MoraleState.STEADY, "u1": MoraleState.SHAKEN}
        ctx = _make_ownerless_ctx({"blue": list(units)}, morale)
        before = list(ctx.units_by_side["blue"])

        with pytest.raises(RuntimeError, match="MoraleRuntime"):
            engine.aggregate(["u0", "u1"], ctx)

        assert ctx.units_by_side["blue"] == before
        assert ctx.morale_states == morale

    def test_disaggregate_unknown_id(self):
        engine = AggregationEngine(rng=_rng())
        ctx = _make_ctx()
        result = engine.disaggregate("nonexistent", ctx)
        assert result == []

    def test_roundtrip_preserves_unit_state(self):
        config = AggregationConfig(enable_aggregation=True, min_units_to_aggregate=2)
        engine = AggregationEngine(config=config, rng=_rng())
        units = [
            _make_unit("u0", "blue", Position(100, 200), "infantry"),
            _make_unit("u1", "blue", Position(300, 400), "infantry"),
        ]
        ctx = _make_ctx({"blue": list(units)})

        # Aggregate
        agg = engine.aggregate(["u0", "u1"], ctx)
        # Disaggregate
        engine.disaggregate(agg.aggregate_id, ctx)

        # Find restored units
        restored = {u.entity_id: u for u in ctx.units_by_side["blue"]}
        assert "u0" in restored
        assert "u1" in restored
        assert restored["u0"].unit_type == "infantry"
        assert restored["u1"].unit_type == "infantry"
        assert restored["u0"].position.easting == pytest.approx(100.0)


class TestCandidateDetection:
    def test_no_candidates_when_disabled(self):
        config = AggregationConfig(enable_aggregation=False)
        engine = AggregationEngine(config=config, rng=_rng())
        units = [_make_unit(f"u{i}", "blue") for i in range(5)]
        ctx = _make_ctx({"blue": units})
        candidates = engine.check_aggregation_candidates(ctx)
        assert candidates == []

    def test_candidates_found(self):
        config = AggregationConfig(
            enable_aggregation=True, min_units_to_aggregate=3,
            aggregation_distance_m=1000.0,
        )
        engine = AggregationEngine(config=config, rng=_rng())
        units = [_make_unit(f"u{i}", "blue", unit_type="infantry") for i in range(5)]
        ctx = _make_ctx({"blue": units})
        candidates = engine.check_aggregation_candidates(ctx)
        assert len(candidates) == 1
        assert len(candidates[0]) == 5

    def test_candidates_filtered_by_battle_distance(self):
        config = AggregationConfig(
            enable_aggregation=True, min_units_to_aggregate=2,
            aggregation_distance_m=10_000.0,
        )
        engine = AggregationEngine(config=config, rng=_rng())
        # Units near a battle
        units = [_make_unit(f"u{i}", "blue", Position(100, 0)) for i in range(4)]
        ctx = _make_ctx({"blue": units})
        battle_pos = [Position(0, 0)]
        candidates = engine.check_aggregation_candidates(ctx, battle_pos)
        assert candidates == []

    def test_candidates_far_from_battle(self):
        config = AggregationConfig(
            enable_aggregation=True, min_units_to_aggregate=2,
            aggregation_distance_m=1000.0,
        )
        engine = AggregationEngine(config=config, rng=_rng())
        units = [_make_unit(f"u{i}", "blue", Position(50000, 0)) for i in range(4)]
        ctx = _make_ctx({"blue": units})
        battle_pos = [Position(0, 0)]
        candidates = engine.check_aggregation_candidates(ctx, battle_pos)
        assert len(candidates) > 0


class TestDisaggregationTriggers:
    def test_no_triggers_when_disabled(self):
        config = AggregationConfig(enable_aggregation=False)
        engine = AggregationEngine(config=config, rng=_rng())
        ctx = _make_ctx()
        triggers = engine.check_disaggregation_triggers(ctx)
        assert triggers == []

    def test_trigger_when_battle_approaches(self):
        config = AggregationConfig(
            enable_aggregation=True, min_units_to_aggregate=2,
            disaggregate_distance_m=10_000.0,
        )
        engine = AggregationEngine(config=config, rng=_rng())
        units = [_make_unit(f"u{i}", "blue", Position(5000, 0)) for i in range(4)]
        ctx = _make_ctx({"blue": list(units)})
        agg = engine.aggregate([u.entity_id for u in units], ctx)

        battle_pos = [Position(0, 0)]
        triggers = engine.check_disaggregation_triggers(ctx, battle_pos)
        assert agg.aggregate_id in triggers

    def test_no_trigger_when_far(self):
        config = AggregationConfig(
            enable_aggregation=True, min_units_to_aggregate=2,
            disaggregate_distance_m=1000.0,
        )
        engine = AggregationEngine(config=config, rng=_rng())
        units = [_make_unit(f"u{i}", "blue", Position(50000, 0)) for i in range(4)]
        ctx = _make_ctx({"blue": list(units)})
        agg = engine.aggregate([u.entity_id for u in units], ctx)

        battle_pos = [Position(0, 0)]
        triggers = engine.check_disaggregation_triggers(ctx, battle_pos)
        assert triggers == []


class TestStatePersistence:
    def test_get_set_state_roundtrip(self):
        config = AggregationConfig(enable_aggregation=True, min_units_to_aggregate=2)
        engine = AggregationEngine(config=config, rng=_rng())
        units = [_make_unit(f"u{i}", "blue") for i in range(4)]
        ctx = _make_ctx({"blue": list(units)})
        engine.aggregate([u.entity_id for u in units], ctx)

        state = engine.get_state()
        engine2 = AggregationEngine(config=config, rng=_rng())
        engine2.set_state(state)

        assert len(engine2.active_aggregates) == 1
        agg = list(engine2.active_aggregates.values())[0]
        assert len(agg.constituent_snapshots) == 4

    def test_empty_state(self):
        engine = AggregationEngine(rng=_rng())
        state = engine.get_state()
        assert state["aggregates"] == {}
        engine2 = AggregationEngine(rng=_rng())
        engine2.set_state(state)
        assert len(engine2.active_aggregates) == 0

    def test_deterministic_aggregate_ids(self):
        """Aggregate IDs should be deterministic."""
        config = AggregationConfig(enable_aggregation=True, min_units_to_aggregate=2)
        ids = []
        for _ in range(2):
            engine = AggregationEngine(config=config, rng=_rng())
            units = [_make_unit(f"u{i}", "blue") for i in range(4)]
            ctx = _make_ctx({"blue": list(units)})
            agg = engine.aggregate([u.entity_id for u in units], ctx)
            ids.append(agg.aggregate_id)
        assert ids[0] == ids[1]
