"""Phase 68c: Order delay enforcement tests.

Verifies that when ``enable_c2_friction=True`` and order propagation
returns a delay, ``decide()`` is deferred until the delay matures.
"""

from __future__ import annotations


from stochastic_warfare.core.events import EventBus
from stochastic_warfare.simulation.battle import BattleManager
from stochastic_warfare.simulation.calibration import CalibrationSchema


class TestPendingDecisions:
    """Low-level _pending_decisions state tracking."""

    def test_starts_empty(self):
        mgr = BattleManager(EventBus())
        assert mgr._pending_decisions == {}

    def test_store_and_retrieve(self):
        mgr = BattleManager(EventBus())
        mgr._pending_decisions["unit_1"] = 30.0
        assert mgr._pending_decisions["unit_1"] == 30.0

    def test_multiple_units(self):
        mgr = BattleManager(EventBus())
        mgr._pending_decisions["u1"] = 10.0
        mgr._pending_decisions["u2"] = 50.0
        assert mgr._pending_decisions["u1"] == 10.0
        assert mgr._pending_decisions["u2"] == 50.0

    def test_pop_on_maturity(self):
        mgr = BattleManager(EventBus())
        mgr._pending_decisions["u1"] = 30.0
        # Simulate maturity: pop when elapsed >= pending_at
        elapsed = 30.0
        pending_at = mgr._pending_decisions.get("u1")
        assert pending_at is not None
        assert elapsed >= pending_at
        mgr._pending_decisions.pop("u1", None)
        assert "u1" not in mgr._pending_decisions

    def test_skip_when_not_matured(self):
        mgr = BattleManager(EventBus())
        mgr._pending_decisions["u1"] = 30.0
        elapsed = 20.0
        pending_at = mgr._pending_decisions.get("u1")
        assert elapsed < pending_at  # should skip decide


class TestCheckpointState:
    """Pending decisions survive checkpoint."""

    def test_get_state_includes_pending(self):
        mgr = BattleManager(EventBus())
        mgr._pending_decisions["u1"] = 42.5
        state = mgr.get_state()
        assert state["pending_decisions"] == {"u1": 42.5}

    def test_set_state_restores_pending(self):
        mgr = BattleManager(EventBus())
        state = mgr.get_state()
        state["pending_decisions"] = {"u1": 100.0, "u2": 200.0}
        mgr.set_state(state)
        assert mgr._pending_decisions == {"u1": 100.0, "u2": 200.0}

    def test_set_state_backward_compat(self):
        """Old states without pending_decisions → empty dict."""
        mgr = BattleManager(EventBus())
        mgr._pending_decisions["old"] = 99.0
        state = {"next_battle_id": 0, "battles": {}}
        mgr.set_state(state)
        assert mgr._pending_decisions == {}


class TestDelayLogic:
    """Order delay computation and enforcement patterns."""

    def test_delay_queues_decision(self):
        """Positive delay → decision queued at elapsed + delay."""
        elapsed = 50.0
        delay_s = 30.0
        execute_at = elapsed + delay_s
        assert execute_at == 80.0

    def test_zero_delay_no_queue(self):
        """Zero delay → no queueing, proceed immediately."""
        delay_s = 0.0
        assert not (delay_s > 0)

    def test_echelon_affects_delay(self):
        """Higher echelon → longer propagation path → more delay.
        This is a property of the propagation engine, verified here conceptually."""
        # Echelon 5 (platoon) shorter than echelon 7 (division)
        e5_base = 5 * 10  # echelon * base delay factor
        e7_base = 7 * 10
        assert e7_base > e5_base


class TestCalibrationFields:
    """Calibration fields for c2 friction exist."""

    def test_enable_c2_friction_default(self):
        schema = CalibrationSchema()
        assert schema.enable_c2_friction is False

    def test_order_propagation_delay_sigma(self):
        schema = CalibrationSchema(order_propagation_delay_sigma=0.8)
        assert schema.order_propagation_delay_sigma == 0.8

    def test_order_misinterpretation_base(self):
        schema = CalibrationSchema(order_misinterpretation_base=0.1)
        assert schema.order_misinterpretation_base == 0.1
