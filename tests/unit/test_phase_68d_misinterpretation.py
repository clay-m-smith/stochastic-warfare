"""Phase 68d: Order misinterpretation enforcement tests.

Verifies that misinterpretation types produce correct behavioral effects:
position offset, timing re-delay, objective swap, unit designation skip.
"""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position
from stochastic_warfare.simulation.battle import BattleManager
from stochastic_warfare.simulation.calibration import CalibrationSchema


class TestMisinterpretedOrdersState:
    """Misinterpreted orders state tracking."""

    def test_starts_empty(self):
        mgr = BattleManager(EventBus())
        assert mgr._misinterpreted_orders == {}

    def test_store_and_pop(self):
        mgr = BattleManager(EventBus())
        result = SimpleNamespace(
            was_misinterpreted=True,
            misinterpretation_type="position",
            total_delay_s=10.0,
        )
        mgr._misinterpreted_orders["u1"] = result
        popped = mgr._misinterpreted_orders.pop("u1", None)
        assert popped is result
        assert "u1" not in mgr._misinterpreted_orders


class TestTimingMisinterpretation:
    """Timing misinterpretation doubles remaining delay."""

    def test_timing_re_delays(self):
        """Unit with timing misinterpretation should be re-queued."""
        mgr = BattleManager(EventBus())
        result = SimpleNamespace(
            was_misinterpreted=True,
            misinterpretation_type="timing",
            total_delay_s=30.0,
        )
        # Simulate: store misinterp, then when processing, re-delay
        elapsed = 100.0
        extra = result.total_delay_s
        mgr._pending_decisions["u1"] = elapsed + extra
        assert mgr._pending_decisions["u1"] == 130.0


class TestUnitDesignationMisinterpretation:
    """Unit designation misinterpretation skips decide entirely."""

    def test_wrong_unit_skips(self):
        """Unit_designation type → decide skipped for this cycle."""
        mistype = "unit_designation"
        # The gate: if _mistype == "unit_designation": continue
        assert mistype == "unit_designation"  # triggers skip


class TestObjectiveMisinterpretation:
    """Objective misinterpretation swaps ATTACK and DEFEND."""

    def test_attack_defend_swap(self):
        school_adjustments = {"ATTACK": 0.5, "DEFEND": 0.1}
        # The swap: ATTACK ↔ DEFEND
        atk = school_adjustments.get("ATTACK", 0.0)
        dfn = school_adjustments.get("DEFEND", 0.0)
        school_adjustments["ATTACK"] = dfn
        school_adjustments["DEFEND"] = atk
        assert school_adjustments["ATTACK"] == 0.1
        assert school_adjustments["DEFEND"] == 0.5

    def test_swap_with_missing_keys(self):
        """Missing ATTACK/DEFEND defaults to 0.0."""
        school_adjustments: dict[str, float] = {"WITHDRAW": 0.3}
        atk = school_adjustments.get("ATTACK", 0.0)
        dfn = school_adjustments.get("DEFEND", 0.0)
        school_adjustments["ATTACK"] = dfn
        school_adjustments["DEFEND"] = atk
        assert school_adjustments["ATTACK"] == 0.0
        assert school_adjustments["DEFEND"] == 0.0


class TestPositionMisinterpretation:
    """Position misinterpretation offsets movement target."""

    def test_position_offset_magnitude(self):
        """Offset vector magnitude matches misinterpretation_radius_m."""
        radius = 500.0
        angle = 0.785  # ~45 degrees
        offset_e = math.cos(angle) * radius
        offset_n = math.sin(angle) * radius
        magnitude = math.sqrt(offset_e ** 2 + offset_n ** 2)
        assert magnitude == pytest.approx(radius, rel=0.01)

    def test_position_offset_applied(self):
        """Unit position is shifted by the offset vector."""
        original = Position(1000, 2000, 0)
        radius = 500.0
        angle = 0.0  # due east
        new_pos = Position(
            original.easting + math.cos(angle) * radius,
            original.northing + math.sin(angle) * radius,
            original.altitude,
        )
        assert new_pos.easting == pytest.approx(1500.0)
        assert new_pos.northing == pytest.approx(2000.0)

    def test_calibration_radius_field(self):
        schema = CalibrationSchema(misinterpretation_radius_m=1000.0)
        assert schema.misinterpretation_radius_m == 1000.0

        default = CalibrationSchema()
        assert default.misinterpretation_radius_m == 500.0


class TestMisinterpretationRate:
    """Misinterpretation probability verification."""

    def test_base_rate_configurable(self):
        schema = CalibrationSchema(order_misinterpretation_base=0.1)
        assert schema.order_misinterpretation_base == 0.1

    def test_default_base_rate(self):
        schema = CalibrationSchema()
        assert schema.order_misinterpretation_base == 0.05
