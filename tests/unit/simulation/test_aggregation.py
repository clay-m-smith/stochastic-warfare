"""Unit tests for AggregationEngine — force aggregation/disaggregation.

Phase 75d: Edge cases NOT covered by test_phase_13a7_aggregation.py.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position
from stochastic_warfare.simulation.aggregation import (
    AggregationConfig,
    AggregationEngine,
)
from stochastic_warfare.morale.state import MoraleState

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


def _make_real_unit(unit_id, side, position, personnel_count=10):
    """Create a minimal real-ish Unit-like object for aggregation tests."""
    from stochastic_warfare.entities.base import UnitStatus

    u = SimpleNamespace(
        entity_id=unit_id,
        side=side,
        position=position,
        status=UnitStatus.ACTIVE,
        personnel=[f"p{i}" for i in range(personnel_count)],
        equipment=[],
        unit_type="infantry",
        domain="GROUND",
        speed=5.0,
        max_speed=10.0,
        name=f"Unit {unit_id}",
    )
    u.get_state = lambda: {
        "entity_id": u.entity_id,
        "side": u.side,
        "personnel": list(u.personnel),
    }
    return u


def _make_agg_ctx(units_by_side):
    """Create a context with the fields aggregation needs."""
    ctx = SimpleNamespace(
        units_by_side=units_by_side,
        morale_states={},
        unit_weapons={},
        unit_sensors={},
        stockpile_manager=None,
    )
    return ctx


class TestAggregationEngine:
    """Aggregation engine operations."""

    def test_snapshot_captures_state(self):
        engine = AggregationEngine(rng=_rng(), event_bus=EventBus())
        u = _make_real_unit("u1", "blue", Position(100.0, 200.0, 0.0))
        ctx = _make_agg_ctx({"blue": [u]})
        ctx.morale_states = {"u1": MoraleState.STEADY}
        snapshot = engine.snapshot_unit(u, ctx)
        assert snapshot.original_side == "blue"
        assert snapshot.morale_state == int(MoraleState.STEADY)

    def test_too_few_returns_none(self):
        cfg = AggregationConfig(enable_aggregation=True, min_units_to_aggregate=10)
        engine = AggregationEngine(config=cfg, rng=_rng(), event_bus=EventBus())
        units = [
            _make_real_unit(f"u{i}", "blue", Position(float(i * 10), 0.0, 0.0))
            for i in range(3)
        ]
        ctx = _make_agg_ctx({"blue": units})
        ctx.morale_states = {u.entity_id: MoraleState.STEADY for u in units}
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
        ctx.morale_states = {u.entity_id: MoraleState.STEADY for u in units}
        r1 = engine.aggregate(["u0", "u1"], ctx)
        r2 = engine.aggregate(["u2", "u3"], ctx)
        assert r1 is not None and r2 is not None
        assert r1.aggregate_id != r2.aggregate_id


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
        ctx.morale_states = {"u1": MoraleState.STEADY, "u2": MoraleState.STEADY}
        agg = engine.aggregate(["u1", "u2"], ctx)
        assert agg is not None
        assert agg.position.easting == pytest.approx(50.0)

    def test_worst_morale(self):
        cfg = AggregationConfig(enable_aggregation=True, min_units_to_aggregate=2)
        engine = AggregationEngine(config=cfg, rng=_rng(), event_bus=EventBus())
        u1 = _make_real_unit("u1", "blue", Position(0, 0, 0))
        u2 = _make_real_unit("u2", "blue", Position(10, 0, 0))
        ctx = _make_agg_ctx({"blue": [u1, u2]})
        ctx.morale_states = {"u1": MoraleState.STEADY, "u2": MoraleState.BROKEN}
        agg = engine.aggregate(["u1", "u2"], ctx)
        assert agg is not None
        assert int(agg.morale_state) >= int(MoraleState.BROKEN)

    def test_combat_power_sum(self):
        cfg = AggregationConfig(enable_aggregation=True, min_units_to_aggregate=2)
        engine = AggregationEngine(config=cfg, rng=_rng(), event_bus=EventBus())
        u1 = _make_real_unit("u1", "blue", Position(0, 0, 0), personnel_count=10)
        u2 = _make_real_unit("u2", "blue", Position(10, 0, 0), personnel_count=20)
        ctx = _make_agg_ctx({"blue": [u1, u2]})
        ctx.morale_states = {"u1": MoraleState.STEADY, "u2": MoraleState.STEADY}
        agg = engine.aggregate(["u1", "u2"], ctx)
        assert agg is not None
        assert agg.aggregate_personnel == 30
