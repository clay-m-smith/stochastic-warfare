"""Phase 85: Aggregation order preservation tests.

Validates that UnitSnapshot captures/restores orders through
aggregate/disaggregate roundtrips.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Domain, Position
from stochastic_warfare.entities.base import UnitStatus
from stochastic_warfare.morale.state import MoraleState
from stochastic_warfare.simulation.aggregation import (
    AggregationConfig,
    AggregationEngine,
    UnitSnapshot,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def _make_unit(uid: str, side: str = "blue", easting: float = 0.0) -> SimpleNamespace:
    u = SimpleNamespace(
        entity_id=uid,
        side=side,
        position=Position(easting, 0.0, 0.0),
        status=UnitStatus.ACTIVE,
        personnel=[f"p{i}" for i in range(10)],
        equipment=[],
        unit_type="infantry",
        domain=Domain.GROUND,
        speed=5.0,
        max_speed=10.0,
        name=f"Unit {uid}",
    )
    u.get_state = lambda: {
        "entity_id": u.entity_id,
        "name": u.name,
        "side": u.side,
        "unit_type": u.unit_type,
        "domain": int(u.domain),
        "status": int(u.status),
        "position": tuple(u.position),
        "heading": 0.0,
        "speed": u.speed,
        "max_speed": u.max_speed,
        "training_level": 0.5,
        "weight_tons": 0.0,
        "personnel": [],
        "equipment": [],
    }
    return u


def _make_order_record(order_id: str, recipient_id: str, status: int = 5) -> SimpleNamespace:
    """Minimal order execution record mock."""
    rec = SimpleNamespace(
        order_id=order_id,
        recipient_id=recipient_id,
    )
    rec.get_state = lambda: {
        "order_id": order_id,
        "recipient_id": recipient_id,
        "status": status,
        "issued_time": 0.0,
        "received_time": None,
        "acknowledged_time": None,
        "execution_start_time": None,
        "completion_time": None,
        "deviation_level": 0.0,
        "was_degraded": False,
        "was_misinterpreted": False,
        "misinterpretation_type": "",
        "superseded_by": None,
    }
    return rec


def _make_order_exec(records_by_unit: dict[str, list]) -> SimpleNamespace:
    """Minimal OrderExecutionEngine mock."""
    # Build _records dict keyed by order_id
    _records: dict[str, SimpleNamespace] = {}
    _by_unit: dict[str, list] = {}
    for uid, recs in records_by_unit.items():
        _by_unit[uid] = recs
        for r in recs:
            _records[r.order_id] = r

    def get_active_orders(uid):
        return [r for r in _by_unit.get(uid, []) if r.get_state()["status"] >= 3]

    def get_pending_orders(uid):
        return [r for r in _by_unit.get(uid, []) if r.get_state()["status"] < 3]

    return SimpleNamespace(
        get_active_orders=get_active_orders,
        get_pending_orders=get_pending_orders,
        _records=_records,
    )


def _make_ctx(units_by_side, order_exec=None):
    return SimpleNamespace(
        units_by_side=units_by_side,
        morale_states={u.entity_id: MoraleState.STEADY
                       for su in units_by_side.values() for u in su},
        unit_weapons={},
        unit_sensors={},
        stockpile_manager=None,
        order_execution=order_exec,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestOrderSnapshot:
    """Order capture in UnitSnapshot."""

    def test_snapshot_has_order_records_field(self):
        """UnitSnapshot has order_records attr with default []."""
        snap = UnitSnapshot(unit_state={}, morale_state=0)
        assert hasattr(snap, "order_records")
        assert snap.order_records == []

    def test_order_snapshot_roundtrip(self):
        """Unit with active orders → snapshot → order_records populated."""
        engine = AggregationEngine(rng=_rng(), event_bus=EventBus())
        u = _make_unit("u1")
        rec = _make_order_record("ord1", "u1", status=5)
        order_exec = _make_order_exec({"u1": [rec]})
        ctx = _make_ctx({"blue": [u]}, order_exec=order_exec)
        snap = engine.snapshot_unit(u, ctx)
        assert len(snap.order_records) == 1
        assert snap.order_records[0]["order_id"] == "ord1"

    def test_idle_unit_no_orders(self):
        """No orders → empty order_records."""
        engine = AggregationEngine(rng=_rng(), event_bus=EventBus())
        u = _make_unit("u1")
        order_exec = _make_order_exec({})
        ctx = _make_ctx({"blue": [u]}, order_exec=order_exec)
        snap = engine.snapshot_unit(u, ctx)
        assert snap.order_records == []

    def test_pending_orders_preserved(self):
        """IN_TRANSIT (status=1) orders are captured as pending."""
        engine = AggregationEngine(rng=_rng(), event_bus=EventBus())
        u = _make_unit("u1")
        rec = _make_order_record("ord1", "u1", status=1)  # ISSUED
        order_exec = _make_order_exec({"u1": [rec]})
        ctx = _make_ctx({"blue": [u]}, order_exec=order_exec)
        snap = engine.snapshot_unit(u, ctx)
        assert len(snap.order_records) == 1

    def test_multiple_orders_preserved(self):
        """Multiple active orders all captured."""
        engine = AggregationEngine(rng=_rng(), event_bus=EventBus())
        u = _make_unit("u1")
        recs = [
            _make_order_record(f"ord{i}", "u1", status=5)
            for i in range(3)
        ]
        order_exec = _make_order_exec({"u1": recs})
        ctx = _make_ctx({"blue": [u]}, order_exec=order_exec)
        snap = engine.snapshot_unit(u, ctx)
        assert len(snap.order_records) == 3

    def test_disaggregate_without_order_execution(self):
        """ctx.order_execution=None → no crash during disaggregate."""
        cfg = AggregationConfig(enable_aggregation=True, min_units_to_aggregate=2)
        engine = AggregationEngine(config=cfg, rng=_rng(), event_bus=EventBus())
        units = [_make_unit(f"u{i}", easting=float(i * 10)) for i in range(4)]
        ctx = _make_ctx({"blue": units}, order_exec=None)
        agg = engine.aggregate([u.entity_id for u in units], ctx)
        assert agg is not None
        restored = engine.disaggregate(agg.aggregate_id, ctx)
        assert len(restored) == 4


class TestOrderSerialization:
    """Order records in get_state()/set_state()."""

    def test_order_records_in_get_state(self):
        """Serialization includes order_records."""
        cfg = AggregationConfig(enable_aggregation=True, min_units_to_aggregate=2)
        engine = AggregationEngine(config=cfg, rng=_rng(), event_bus=EventBus())
        units = [_make_unit(f"u{i}", easting=float(i * 10)) for i in range(4)]
        rec = _make_order_record("ord1", "u0", status=5)
        order_exec = _make_order_exec({"u0": [rec]})
        ctx = _make_ctx({"blue": units}, order_exec=order_exec)
        engine.aggregate([u.entity_id for u in units], ctx)
        state = engine.get_state()
        snaps = list(state["aggregates"].values())[0]["snapshots"]
        # At least one snapshot should have order_records
        has_orders = any(s["order_records"] for s in snaps)
        assert has_orders

    def test_order_records_in_set_state(self):
        """Deserialization restores order_records."""
        cfg = AggregationConfig(enable_aggregation=True, min_units_to_aggregate=2)
        engine = AggregationEngine(config=cfg, rng=_rng(), event_bus=EventBus())
        units = [_make_unit(f"u{i}", easting=float(i * 10)) for i in range(4)]
        rec = _make_order_record("ord1", "u0", status=5)
        order_exec = _make_order_exec({"u0": [rec]})
        ctx = _make_ctx({"blue": units}, order_exec=order_exec)
        engine.aggregate([u.entity_id for u in units], ctx)
        state = engine.get_state()

        engine2 = AggregationEngine(config=cfg, rng=_rng(), event_bus=EventBus())
        engine2.set_state(state)
        agg = list(engine2._aggregates.values())[0]
        has_orders = any(s.order_records for s in agg.constituent_snapshots)
        assert has_orders

    def test_aggregation_still_disabled_by_default(self):
        """AggregationConfig().enable_aggregation is False."""
        assert AggregationConfig().enable_aggregation is False

    def test_full_roundtrip_with_orders(self):
        """4 units with orders → aggregate → disaggregate → orders restored."""
        cfg = AggregationConfig(enable_aggregation=True, min_units_to_aggregate=2)
        engine = AggregationEngine(config=cfg, rng=_rng(), event_bus=EventBus())
        units = [_make_unit(f"u{i}", easting=float(i * 10)) for i in range(4)]

        # Give u0 and u1 orders
        recs = {
            "u0": [_make_order_record("ord0", "u0", status=5)],
            "u1": [_make_order_record("ord1", "u1", status=5)],
        }
        order_exec = _make_order_exec(recs)
        ctx = _make_ctx({"blue": units}, order_exec=order_exec)

        agg = engine.aggregate([u.entity_id for u in units], ctx)
        assert agg is not None

        # Verify snapshots have order records
        snaps_with_orders = [s for s in agg.constituent_snapshots if s.order_records]
        assert len(snaps_with_orders) == 2

        # Disaggregate — orders should be restored to _records
        restored = engine.disaggregate(agg.aggregate_id, ctx)
        assert len(restored) == 4
        assert "ord0" in order_exec._records
        assert "ord1" in order_exec._records
