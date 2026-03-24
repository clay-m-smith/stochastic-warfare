"""Unit tests for SimulationEngine event handler methods.

Phase 75b: Tests _find_unit_by_id, _handle_return_to_duty,
_handle_equipment_breakdown, _handle_maintenance_completed.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from stochastic_warfare.core.types import Position

from .conftest import _make_unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_engine_with_ctx(
    units_by_side: dict[str, list] | None = None,
    calibration: object | None = None,
) -> SimpleNamespace:
    """Build a mock SimulationEngine with minimal ctx.

    We don't instantiate the real SimulationEngine (too many deps).
    Instead we build a namespace with the ctx fields the private methods
    access, and bind the methods from the real class.
    """
    from stochastic_warfare.simulation.engine import SimulationEngine

    ubs = units_by_side or {}
    ctx = SimpleNamespace(
        units_by_side=ubs,
        calibration=calibration,
        event_bus=SimpleNamespace(subscribe=lambda *a, **kw: None),
    )
    # Create a thin wrapper that has _ctx and the private methods
    engine = SimpleNamespace(_ctx=ctx)
    engine._find_unit_by_id = lambda uid: SimulationEngine._find_unit_by_id(engine, uid)
    engine._handle_return_to_duty = lambda ev: SimulationEngine._handle_return_to_duty(engine, ev)
    engine._handle_equipment_breakdown = lambda ev: SimulationEngine._handle_equipment_breakdown(engine, ev)
    engine._handle_maintenance_completed = lambda ev: SimulationEngine._handle_maintenance_completed(engine, ev)
    return engine


# ===================================================================
# _find_unit_by_id
# ===================================================================


class TestFindUnitById:
    """Find a unit across all sides by entity_id."""

    def test_finds_blue(self):
        u = _make_unit("u1", "blue")
        engine = _make_engine_with_ctx({"blue": [u]})
        assert engine._find_unit_by_id("u1") is u

    def test_finds_red(self):
        u = _make_unit("u1", "red")
        engine = _make_engine_with_ctx({"blue": [], "red": [u]})
        assert engine._find_unit_by_id("u1") is u

    def test_missing_returns_none(self):
        engine = _make_engine_with_ctx({"blue": [], "red": []})
        assert engine._find_unit_by_id("missing") is None


# ===================================================================
# _handle_return_to_duty
# ===================================================================


class TestHandleReturnToDuty:
    """Restore crew member after medical RTD event."""

    def test_restores_crew(self):
        restored = []
        u = _make_unit("u1")
        u.restore_crew_member = lambda mid: restored.append(mid)
        engine = _make_engine_with_ctx({"blue": [u]})
        event = SimpleNamespace(unit_id="u1", member_id="p0")
        engine._handle_return_to_duty(event)
        assert "p0" in restored

    def test_missing_unit_noop(self):
        engine = _make_engine_with_ctx({"blue": []})
        event = SimpleNamespace(unit_id="missing", member_id="p0")
        engine._handle_return_to_duty(event)  # no error

    def test_no_method_noop(self):
        u = _make_unit("u1")
        # No restore_crew_member method
        engine = _make_engine_with_ctx({"blue": [u]})
        event = SimpleNamespace(unit_id="u1", member_id="p0")
        engine._handle_return_to_duty(event)  # no error


# ===================================================================
# _handle_equipment_breakdown
# ===================================================================


class TestHandleEquipmentBreakdown:
    """Mark equipment as non-operational after breakdown."""

    def test_marks_non_operational(self):
        u = _make_unit("u1", equipment_count=3)
        u.equipment[1].equipment_id = "eq_target"
        engine = _make_engine_with_ctx(
            {"blue": [u]},
            calibration=SimpleNamespace(
                degraded_equipment_threshold=0.3,
                get=lambda k, d=None: d,
            ),
        )
        event = SimpleNamespace(unit_id="u1", equipment_id="eq_target")
        engine._handle_equipment_breakdown(event)
        assert u.equipment[1].operational is False

    def test_missing_equip_noop(self):
        u = _make_unit("u1")
        engine = _make_engine_with_ctx(
            {"blue": [u]},
            calibration=SimpleNamespace(
                degraded_equipment_threshold=0.3,
                get=lambda k, d=None: d,
            ),
        )
        event = SimpleNamespace(unit_id="u1", equipment_id="nonexistent")
        engine._handle_equipment_breakdown(event)
        # All equipment should still be operational
        assert all(e.operational for e in u.equipment)

    def test_missing_unit_noop(self):
        engine = _make_engine_with_ctx({"blue": []})
        event = SimpleNamespace(unit_id="missing", equipment_id="eq1")
        engine._handle_equipment_breakdown(event)  # no error

    def test_threshold_logged(self):
        # When broken/total > threshold, should log (we just verify no crash)
        u = _make_unit("u1", equipment_count=2)
        engine = _make_engine_with_ctx(
            {"blue": [u]},
            calibration=SimpleNamespace(
                degraded_equipment_threshold=0.3,
                get=lambda k, d=None: d,
            ),
        )
        # Break first equipment manually
        u.equipment[0].operational = False
        event = SimpleNamespace(unit_id="u1", equipment_id=u.equipment[1].equipment_id)
        engine._handle_equipment_breakdown(event)
        # 2/2 broken → 100% > 30% threshold
        assert u.equipment[1].operational is False


# ===================================================================
# _handle_maintenance_completed
# ===================================================================


class TestHandleMaintenanceCompleted:
    """Restore equipment to operational after maintenance."""

    def test_restores_operational(self):
        u = _make_unit("u1", equipment_count=2)
        u.equipment[0].operational = False
        engine = _make_engine_with_ctx({"blue": [u]})
        event = SimpleNamespace(unit_id="u1", equipment_id=u.equipment[0].equipment_id)
        engine._handle_maintenance_completed(event)
        assert u.equipment[0].operational is True

    def test_missing_equip_noop(self):
        u = _make_unit("u1")
        engine = _make_engine_with_ctx({"blue": [u]})
        event = SimpleNamespace(unit_id="u1", equipment_id="nonexistent")
        engine._handle_maintenance_completed(event)

    def test_missing_unit_noop(self):
        engine = _make_engine_with_ctx({"blue": []})
        event = SimpleNamespace(unit_id="missing", equipment_id="eq1")
        engine._handle_maintenance_completed(event)

    def test_partial_match(self):
        u = _make_unit("u1", equipment_count=3)
        u.equipment[1].operational = False
        engine = _make_engine_with_ctx({"blue": [u]})
        event = SimpleNamespace(unit_id="u1", equipment_id=u.equipment[1].equipment_id)
        engine._handle_maintenance_completed(event)
        assert u.equipment[1].operational is True
        assert u.equipment[0].operational is True  # unchanged
