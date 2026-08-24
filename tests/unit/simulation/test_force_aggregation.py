"""Phase 13a-7: Force aggregation/disaggregation tests."""

import copy
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import pytest
from pydantic import ValidationError

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.morale.runtime import MoraleRegistration, MoraleRuntime
from stochastic_warfare.morale.state import MoraleState
from stochastic_warfare.simulation.aggregation import (
    AggregationConfig,
    AggregationEngine,
)
from stochastic_warfare.simulation.tactical_targeting import (
    TacticalTargetingRuntime,
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
    unit_weapons: dict[str, tuple[object, ...]]
    unit_sensor_attachments: dict[str, tuple[object, ...]]
    unit_sensors: dict[str, tuple[object, ...]]
    equipment_resolutions: dict[str, tuple[object, ...]]
    tactical_targeting: TacticalTargetingRuntime
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
        unit_weapons={unit_id: () for unit_id in units},
        unit_sensor_attachments={unit_id: () for unit_id in units},
        unit_sensors={unit_id: () for unit_id in units},
        equipment_resolutions={unit_id: () for unit_id in units},
        tactical_targeting=TacticalTargetingRuntime(
            sensing_aware_standoff_enabled=True,
            unit_sides={
                unit_id: (
                    unit.side
                    if isinstance(unit.side, str)
                    else unit.side.value
                )
                for unit_id, unit in units.items()
            },
        ),
        stockpile_manager=None,
        order_execution=None,
    )


def _make_ownerless_ctx(
    units_by_side: Mapping[str, list[Unit]],
    morale_states: Mapping[str, MoraleState],
) -> _AggregationContext:
    """Build the deliberate legacy-ownerless failure control."""
    roster = _copy_roster(units_by_side)
    return _AggregationContext(
        event_bus=EventBus(),
        units_by_side=roster,
        morale_runtime=None,
        morale_states=dict(morale_states),
        unit_weapons={
            unit.entity_id: ()
            for side_units in roster.values()
            for unit in side_units
        },
        unit_sensor_attachments={
            unit.entity_id: ()
            for side_units in roster.values()
            for unit in side_units
        },
        unit_sensors={
            unit.entity_id: ()
            for side_units in roster.values()
            for unit in side_units
        },
        equipment_resolutions={
            unit.entity_id: ()
            for side_units in roster.values()
            for unit in side_units
        },
        tactical_targeting=TacticalTargetingRuntime(
            sensing_aware_standoff_enabled=True,
            unit_sides={
                unit.entity_id: (
                    unit.side
                    if isinstance(unit.side, str)
                    else unit.side.value
                )
                for side_units in roster.values()
                for unit in side_units
            },
        ),
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

    @pytest.mark.test_evidence("structural_only")
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

    def test_snapshot_state_failure_defaults_to_strict(self):
        engine = AggregationEngine(rng=_rng())
        unit = _make_unit("u1")
        ctx = _make_ctx({"blue": [unit]})
        failure = RuntimeError("stockpile snapshot failed")

        class FailingInventory:
            def get_state(self):
                raise failure

        class FailingStockpile:
            @staticmethod
            def has_unit_inventory(unit_id: str) -> bool:
                return unit_id == "u1"

            @staticmethod
            def get_unit_inventory(unit_id: str) -> FailingInventory:
                assert unit_id == "u1"
                return FailingInventory()

        ctx.stockpile_manager = FailingStockpile()

        with pytest.raises(RuntimeError) as caught:
            engine.snapshot_unit(unit, ctx)

        assert caught.value is failure


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

    def test_reversed_side_map_produces_same_candidates(self):
        config = AggregationConfig(
            enable_aggregation=True,
            min_units_to_aggregate=2,
        )
        engine = AggregationEngine(config=config, rng=_rng())
        blue_units = [_make_unit(f"b{i}", "blue") for i in range(2)]
        red_units = [_make_unit(f"r{i}", "red") for i in range(2)]
        context = _make_ctx({"red": red_units, "blue": blue_units})

        reversed_candidates = engine.check_aggregation_candidates(context)
        context.units_by_side = {
            "blue": context.units_by_side["blue"],
            "red": context.units_by_side["red"],
        }
        canonical_candidates = engine.check_aggregation_candidates(context)

        assert reversed_candidates == canonical_candidates
        assert canonical_candidates == [["b0", "b1"], ["r0", "r1"]]

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
        engine.aggregate([u.entity_id for u in units], ctx)

        battle_pos = [Position(0, 0)]
        triggers = engine.check_disaggregation_triggers(ctx, battle_pos)
        assert triggers == []


class TestStatePersistence:
    def test_config_is_public_and_immutable(self):
        config = AggregationConfig(
            enable_aggregation=True,
            min_units_to_aggregate=2,
        )
        engine = AggregationEngine(config=config, rng=_rng())

        assert engine.config is config
        with pytest.raises(ValidationError, match="frozen"):
            engine.config.enable_aggregation = False

    def test_get_set_state_roundtrip(self):
        config = AggregationConfig(enable_aggregation=True, min_units_to_aggregate=2)
        engine = AggregationEngine(config=config, rng=_rng())
        units = [_make_unit(f"u{i}", "blue") for i in range(4)]
        ctx = _make_ctx({"blue": list(units)})
        engine.aggregate([u.entity_id for u in units], ctx)

        state = engine.get_state()
        engine2 = AggregationEngine(config=config, rng=_rng())
        engine2.set_state(state)

        assert state["config"] == config.model_dump(mode="json")
        assert engine2.config == config
        assert len(engine2.active_aggregates) == 1
        agg = list(engine2.active_aggregates.values())[0]
        assert len(agg.constituent_snapshots) == 4
        assert engine2.get_state() == state

    def test_empty_state(self):
        engine = AggregationEngine(rng=_rng())
        state = engine.get_state()
        assert state["aggregates"] == {}
        engine2 = AggregationEngine(rng=_rng())
        engine2.set_state(state)
        assert len(engine2.active_aggregates) == 0

    @pytest.mark.parametrize("mutation", ("next_id", "position"))
    def test_corrupt_state_rejects_atomically(self, mutation):
        config = AggregationConfig(
            enable_aggregation=True,
            min_units_to_aggregate=2,
        )
        engine = AggregationEngine(config=config, rng=_rng())
        units = [_make_unit(f"u{i}", "blue") for i in range(4)]
        context = _make_ctx({"blue": list(units)})
        engine.aggregate([unit.entity_id for unit in units], context)
        before = copy.deepcopy(engine.get_state())
        invalid = copy.deepcopy(before)
        if mutation == "next_id":
            invalid["next_id"] = -1
        else:
            snapshot = invalid["aggregates"]["agg_0000"]["snapshots"][0]
            position = list(snapshot["unit_state"]["position"])
            position[0] = float("inf")
            snapshot["unit_state"]["position"] = position

        with pytest.raises(ValueError):
            engine.set_state(invalid)

        assert engine.get_state() == before

    def test_config_mismatch_rejects_state_atomically(self):
        source_config = AggregationConfig(
            enable_aggregation=True,
            min_units_to_aggregate=2,
        )
        source = AggregationEngine(config=source_config, rng=_rng())
        target = AggregationEngine(config=AggregationConfig(), rng=_rng())
        before = target.get_state()

        with pytest.raises(ValueError, match="config does not match"):
            target.set_state(source.get_state())

        assert target.get_state() == before

    def test_active_state_requires_enabled_config_atomically(self):
        enabled_config = AggregationConfig(
            enable_aggregation=True,
            min_units_to_aggregate=2,
        )
        source = AggregationEngine(config=enabled_config, rng=_rng())
        units = [_make_unit(f"u{i}", "blue") for i in range(2)]
        context = _make_ctx({"blue": units})
        aggregate = source.aggregate(
            [unit.entity_id for unit in units],
            context,
        )
        assert aggregate is not None
        invalid = source.get_state()
        disabled_config = AggregationConfig(
            enable_aggregation=False,
            min_units_to_aggregate=2,
        )
        invalid["config"] = disabled_config.model_dump(mode="json")
        target = AggregationEngine(config=disabled_config, rng=_rng())
        before = target.get_state()

        with pytest.raises(ValueError, match="require aggregation config"):
            target.set_state(invalid)

        assert target.get_state() == before

    def test_state_requires_config_envelope_key_atomically(self):
        engine = AggregationEngine(rng=_rng())
        invalid = engine.get_state()
        invalid.pop("config")
        before = engine.get_state()

        with pytest.raises(ValueError, match="state has invalid key topology"):
            engine.set_state(invalid)

        assert engine.get_state() == before

    @pytest.mark.parametrize("mutation", ("extra_key", "coerced_bool"))
    def test_config_requires_exact_strict_state(self, mutation):
        engine = AggregationEngine(rng=_rng())
        invalid = engine.get_state()
        if mutation == "extra_key":
            invalid["config"]["unexpected"] = True
        else:
            invalid["config"]["enable_aggregation"] = 0
        before = engine.get_state()

        with pytest.raises(ValueError, match="Aggregation config"):
            engine.set_state(invalid)

        assert engine.get_state() == before

    def test_get_state_detaches_nested_snapshot_payloads(self):
        config = AggregationConfig(
            enable_aggregation=True,
            min_units_to_aggregate=2,
        )
        engine = AggregationEngine(config=config, rng=_rng())
        units = [_make_unit(f"u{i}", "blue") for i in range(2)]
        context = _make_ctx({"blue": units})
        aggregate = engine.aggregate([unit.entity_id for unit in units], context)
        assert aggregate is not None
        baseline = engine.get_state()

        exposed = engine.get_state()
        exposed["config"]["enable_aggregation"] = False
        snapshot = exposed["aggregates"][aggregate.aggregate_id]["snapshots"][0]
        snapshot["unit_state"]["position"] = (999.0, 999.0, 999.0)
        snapshot["weapon_states"].append({"forged": True})

        assert engine.get_state() == baseline

    def test_active_aggregates_detaches_nested_snapshot_payloads(self):
        config = AggregationConfig(
            enable_aggregation=True,
            min_units_to_aggregate=2,
        )
        engine = AggregationEngine(config=config, rng=_rng())
        units = [_make_unit(f"u{i}", "blue") for i in range(2)]
        context = _make_ctx({"blue": units})
        aggregate = engine.aggregate([unit.entity_id for unit in units], context)
        assert aggregate is not None
        baseline = engine.get_state()

        exposed = engine.active_aggregates
        exposed_aggregate = exposed[aggregate.aggregate_id]
        exposed_aggregate.aggregate_combat_power = -1.0
        exposed_snapshot = exposed_aggregate.constituent_snapshots[0]
        exposed_snapshot.unit_state["position"] = (999.0, 999.0, 999.0)
        exposed_snapshot.weapon_states.append({"forged": True})
        exposed.clear()

        assert engine.get_state() == baseline

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
