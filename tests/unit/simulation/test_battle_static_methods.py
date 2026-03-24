"""Unit tests for BattleManager static/class methods.

Phase 75a: Tests static methods on BattleManager and remaining
module-level functions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.base import UnitStatus

from .conftest import _make_ctx, _make_unit


# ---------------------------------------------------------------------------
# Import class under test
# ---------------------------------------------------------------------------

from stochastic_warfare.simulation.battle import BattleManager


# ===================================================================
# _apply_deferred_damage
# ===================================================================


class TestApplyDeferredDamage:
    """Deferred damage application — worst outcome wins per unit."""

    def test_single_destroy(self):
        u = _make_unit("u1")
        pending = [(u, UnitStatus.DESTROYED)]
        BattleManager._apply_deferred_damage(pending)
        assert u.status == UnitStatus.DESTROYED

    def test_worst_outcome_wins(self):
        u = _make_unit("u1")
        pending = [
            (u, UnitStatus.DISABLED),
            (u, UnitStatus.DESTROYED),
        ]
        BattleManager._apply_deferred_damage(pending)
        assert u.status == UnitStatus.DESTROYED

    def test_dedup_applies_once(self):
        u = _make_unit("u1")
        pending = [
            (u, UnitStatus.DISABLED),
            (u, UnitStatus.DISABLED),
        ]
        BattleManager._apply_deferred_damage(pending)
        assert u.status == UnitStatus.DISABLED

    def test_destroyed_event_published(self):
        u = _make_unit("u1")
        pending = [(u, UnitStatus.DESTROYED)]
        events = []
        bus = SimpleNamespace(publish=lambda e: events.append(e))
        ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        BattleManager._apply_deferred_damage(pending, event_bus=bus, timestamp=ts)
        assert len(events) == 1
        assert events[0].unit_id == "u1"

    def test_disabled_event_published(self):
        u = _make_unit("u1")
        pending = [(u, UnitStatus.DISABLED)]
        events = []
        bus = SimpleNamespace(publish=lambda e: events.append(e))
        ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        BattleManager._apply_deferred_damage(pending, event_bus=bus, timestamp=ts)
        assert len(events) == 1

    def test_empty_noop(self):
        BattleManager._apply_deferred_damage([])


# ===================================================================
# _find_unit_side
# ===================================================================


class TestFindUnitSide:
    """Find which side a unit belongs to."""

    def test_blue_found(self):
        u = _make_unit("u1", "blue")
        ctx = _make_ctx({"blue": [u], "red": []})
        assert BattleManager._find_unit_side(ctx, "u1") == "blue"

    def test_red_found(self):
        u = _make_unit("u1", "red")
        ctx = _make_ctx({"blue": [], "red": [u]})
        assert BattleManager._find_unit_side(ctx, "u1") == "red"

    def test_missing_returns_empty(self):
        ctx = _make_ctx({"blue": [], "red": []})
        assert BattleManager._find_unit_side(ctx, "missing") == ""


# ===================================================================
# _get_unit_morale_level
# ===================================================================


class TestGetUnitMoraleLevel:
    """Morale state → [0, 1] scalar."""

    def test_steady(self):
        ctx = _make_ctx(morale_states={"u1": 0})  # STEADY = 0
        assert BattleManager._get_unit_morale_level(ctx, "u1") == pytest.approx(1.0)

    def test_shaken(self):
        ctx = _make_ctx(morale_states={"u1": 1})  # SHAKEN = 1
        assert BattleManager._get_unit_morale_level(ctx, "u1") == pytest.approx(0.75)

    def test_broken(self):
        ctx = _make_ctx(morale_states={"u1": 2})  # BROKEN = 2
        assert BattleManager._get_unit_morale_level(ctx, "u1") == pytest.approx(0.5)

    def test_routed(self):
        ctx = _make_ctx(morale_states={"u1": 3})  # ROUTED = 3
        assert BattleManager._get_unit_morale_level(ctx, "u1") == pytest.approx(0.25)

    def test_none_defaults_to_0_7(self):
        ctx = _make_ctx(morale_states={})
        assert BattleManager._get_unit_morale_level(ctx, "missing") == pytest.approx(0.7)


# ===================================================================
# _get_unit_supply_level
# ===================================================================


class TestGetUnitSupplyLevel:
    """Supply state [0, 1] from stockpile manager."""

    def test_no_manager_returns_1(self):
        ctx = _make_ctx(stockpile_manager=None)
        assert BattleManager._get_unit_supply_level(ctx, "u1") == 1.0

    def test_returns_value(self):
        mgr = SimpleNamespace(get_supply_state=lambda uid: 0.6)
        ctx = _make_ctx(stockpile_manager=mgr)
        assert BattleManager._get_unit_supply_level(ctx, "u1") == pytest.approx(0.6)

    def test_exception_returns_1(self):
        def bad_get(uid):
            raise RuntimeError("fail")
        mgr = SimpleNamespace(get_supply_state=bad_get)
        ctx = _make_ctx(stockpile_manager=mgr)
        assert BattleManager._get_unit_supply_level(ctx, "u1") == 1.0

    def test_missing_method_returns_1(self):
        mgr = SimpleNamespace()  # no get_supply_state
        ctx = _make_ctx(stockpile_manager=mgr)
        assert BattleManager._get_unit_supply_level(ctx, "u1") == 1.0


# ===================================================================
# _build_assessment_summary
# ===================================================================


class TestBuildAssessmentSummary:
    """Build assessment summary from real or fallback data."""

    def test_with_assessment(self):
        assessment = SimpleNamespace(
            force_ratio=2.0,
            supply_level=0.8,
            morale_level=0.9,
            intel_quality=0.6,
            c2_effectiveness=0.95,
        )
        ctx = _make_ctx()
        result = BattleManager._build_assessment_summary(ctx, "u1", assessment)
        assert result["force_ratio"] == 2.0
        assert result["supply_level"] == 0.8
        assert result["morale_level"] == 0.9

    def test_fallback_computes_force_ratio(self):
        u_blue = _make_unit("u1", "blue")
        u_red = _make_unit("u2", "red")
        ctx = _make_ctx({"blue": [u_blue], "red": [u_red]})
        result = BattleManager._build_assessment_summary(ctx, "u1", None)
        assert result["force_ratio"] == pytest.approx(1.0)

    def test_empty_sides(self):
        ctx = _make_ctx({})
        result = BattleManager._build_assessment_summary(ctx, "u1", None)
        assert "force_ratio" in result

    def test_assessment_missing_attrs_use_defaults(self):
        assessment = SimpleNamespace()  # no attributes
        ctx = _make_ctx()
        result = BattleManager._build_assessment_summary(ctx, "u1", assessment)
        assert result["force_ratio"] == 1.0
        assert result["morale_level"] == 0.7
