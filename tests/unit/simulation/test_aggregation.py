"""Unit tests for AggregationEngine — force aggregation/disaggregation.

Phase 75d: Edge cases NOT covered by test_phase_13a7_aggregation.py.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.base import Unit
from stochastic_warfare.entities.personnel import (
    CrewMember,
    CrewRole,
    SkillLevel,
)
from stochastic_warfare.morale.runtime import MoraleRegistration, MoraleRuntime
from stochastic_warfare.morale.state import MoraleState
from stochastic_warfare.simulation.aggregation import (
    AggregationConfig,
    AggregationEngine,
)
from stochastic_warfare.simulation.tactical_targeting import (
    TacticalTargetingRuntime,
)

from .conftest import _rng


# ===================================================================
# Config
# ===================================================================


class TestAggregationConfig:
    """AggregationConfig defaults and validation."""

    def test_default_disabled(self):
        cfg = AggregationConfig()
        assert cfg.enable_aggregation is False

    def test_distance_defaults(self):
        cfg = AggregationConfig()
        assert cfg.aggregation_distance_m == 50_000.0
        assert cfg.disaggregate_distance_m == 20_000.0

    def test_min_units(self):
        cfg = AggregationConfig()
        assert cfg.min_units_to_aggregate == 4


# ===================================================================
# Engine — aggregate method
# ===================================================================


def _make_real_unit(
    unit_id: str,
    side: str,
    position: Position,
    personnel_count: int = 10,
) -> Unit:
    """Create a real Unit with checkpointable personnel state."""
    return Unit(
        entity_id=unit_id,
        side=side,
        position=position,
        personnel=[
            CrewMember(
                member_id=f"{unit_id}-p{i}",
                role=CrewRole.RIFLEMAN,
                skill=SkillLevel.TRAINED,
                experience=0.5,
            )
            for i in range(personnel_count)
        ],
        unit_type="infantry",
        speed=5.0,
        max_speed=10.0,
        name=f"Unit {unit_id}",
    )


def _make_agg_ctx(
    units_by_side: dict[str, list[Unit]],
    initial_morale: dict[str, MoraleState] | None = None,
) -> SimpleNamespace:
    """Create an aggregation context with exact runtime-owned morale."""
    units = [unit for side_units in units_by_side.values() for unit in side_units]
    units_by_id = {unit.entity_id: unit for unit in units}
    if len(units_by_id) != len(units):
        raise ValueError("Aggregation test roster contains duplicate unit IDs")
    states = initial_morale or {}
    runtime = MoraleRuntime(EventBus(), _rng())
    runtime.register_units(
        tuple(
            MoraleRegistration(
                unit_id,
                states.get(unit_id, MoraleState.STEADY),
            )
            for unit_id in sorted(units_by_id)
        ),
        units_by_id,
    )
    ctx = SimpleNamespace(
        units_by_side=units_by_side,
        morale_runtime=runtime,
        morale_states=runtime.states,
        unit_weapons={unit_id: () for unit_id in units_by_id},
        unit_sensor_attachments={unit_id: () for unit_id in units_by_id},
        unit_sensors={unit_id: () for unit_id in units_by_id},
        equipment_resolutions={unit_id: () for unit_id in units_by_id},
        tactical_targeting=TacticalTargetingRuntime(
            sensing_aware_standoff_enabled=True,
            unit_sides={
                unit_id: (
                    unit.side
                    if isinstance(unit.side, str)
                    else unit.side.value
                )
                for unit_id, unit in units_by_id.items()
            },
        ),
        stockpile_manager=None,
    )
    return ctx


class TestAggregationEngine:
    """Aggregation engine operations."""

    def test_snapshot_captures_state(self):
        engine = AggregationEngine(rng=_rng(), event_bus=EventBus())
        u = _make_real_unit("u1", "blue", Position(100.0, 200.0, 0.0))
        ctx = _make_agg_ctx({"blue": [u]})
        snapshot = engine.snapshot_unit(u, ctx)
        assert snapshot.original_side == "blue"
        assert not hasattr(snapshot, "morale_state")

    def test_too_few_returns_none(self):
        cfg = AggregationConfig(enable_aggregation=True, min_units_to_aggregate=10)
        engine = AggregationEngine(config=cfg, rng=_rng(), event_bus=EventBus())
        units = [
            _make_real_unit(f"u{i}", "blue", Position(float(i * 10), 0.0, 0.0))
            for i in range(3)
        ]
        ctx = _make_agg_ctx({"blue": units})
        result = engine.aggregate(["u0", "u1", "u2"], ctx)
        assert result is None

    def test_id_increments(self):
        cfg = AggregationConfig(enable_aggregation=True, min_units_to_aggregate=2)
        engine = AggregationEngine(config=cfg, rng=_rng(), event_bus=EventBus())
        units = [
            _make_real_unit(f"u{i}", "blue", Position(float(i), 0, 0))
            for i in range(4)
        ]
        ctx = _make_agg_ctx({"blue": units})
        r1 = engine.aggregate(["u0", "u1"], ctx)
        assert r1 is not None
        engine.disaggregate(r1.aggregate_id, ctx)
        r2 = engine.aggregate(["u2", "u3"], ctx)
        assert r2 is not None
        assert r1.aggregate_id != r2.aggregate_id

    def test_second_same_side_aggregate_is_explicitly_unsupported(self):
        cfg = AggregationConfig(
            enable_aggregation=True,
            min_units_to_aggregate=2,
        )
        engine = AggregationEngine(config=cfg, rng=_rng(), event_bus=EventBus())
        units = [
            _make_real_unit(f"u{i}", "blue", Position(float(i), 0, 0))
            for i in range(4)
        ]
        ctx = _make_agg_ctx({"blue": units})
        first = engine.aggregate(["u0", "u1"], ctx)
        assert first is not None
        before = engine.get_state()

        with pytest.raises(ValueError, match="already has active aggregate"):
            engine.aggregate(["u2", "u3"], ctx)

        assert engine.get_state() == before


# ===================================================================
# Aggregate state
# ===================================================================


class TestAggregationState:
    """Aggregate unit properties."""

    def test_centroid_position(self):
        cfg = AggregationConfig(enable_aggregation=True, min_units_to_aggregate=2)
        engine = AggregationEngine(config=cfg, rng=_rng(), event_bus=EventBus())
        u1 = _make_real_unit("u1", "blue", Position(0.0, 0.0, 0.0))
        u2 = _make_real_unit("u2", "blue", Position(100.0, 0.0, 0.0))
        ctx = _make_agg_ctx({"blue": [u1, u2]})
        agg = engine.aggregate(["u1", "u2"], ctx)
        assert agg is not None
        assert agg.position.easting == pytest.approx(50.0)

    def test_aggregate_state_does_not_duplicate_morale(self):
        cfg = AggregationConfig(enable_aggregation=True, min_units_to_aggregate=2)
        engine = AggregationEngine(config=cfg, rng=_rng(), event_bus=EventBus())
        u1 = _make_real_unit("u1", "blue", Position(0, 0, 0))
        u2 = _make_real_unit("u2", "blue", Position(10, 0, 0))
        ctx = _make_agg_ctx(
            {"blue": [u1, u2]},
            {"u1": MoraleState.STEADY, "u2": MoraleState.BROKEN},
        )
        agg = engine.aggregate(["u1", "u2"], ctx)
        assert agg is not None
        assert ctx.morale_runtime.states == {
            agg.aggregate_id: MoraleState.BROKEN,
        }
        assert not hasattr(agg, "morale_state")
        assert "morale_state" not in engine.get_state()["aggregates"][
            agg.aggregate_id
        ]

    def test_combat_power_sum(self):
        cfg = AggregationConfig(enable_aggregation=True, min_units_to_aggregate=2)
        engine = AggregationEngine(config=cfg, rng=_rng(), event_bus=EventBus())
        u1 = _make_real_unit("u1", "blue", Position(0, 0, 0), personnel_count=10)
        u2 = _make_real_unit("u2", "blue", Position(10, 0, 0), personnel_count=20)
        ctx = _make_agg_ctx({"blue": [u1, u2]})
        agg = engine.aggregate(["u1", "u2"], ctx)
        assert agg is not None
        assert agg.aggregate_personnel == 30
