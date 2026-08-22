"""Phase 72b — Verify BattleManager get_state/set_state includes all instance vars.

Tests ensure the 7 previously missing instance variables are now captured
in checkpoint state and correctly restored.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from stochastic_warfare.c2.orders.propagation import PropagationResult
from stochastic_warfare.combat.suppression import UnitSuppressionState
from stochastic_warfare.core.checkpoint import NumpyEncoder
from stochastic_warfare.core.events import EventBus


def _misinterpreted_order() -> PropagationResult:
    """Return a real production value for the typed checkpoint boundary."""
    return PropagationResult(
        success=True,
        total_delay_s=30.0,
        was_misinterpreted=True,
        misinterpretation_type="position",
        comms_quality=0.7,
        degraded=True,
    )


def _make_battle_manager() -> Any:
    """Create a minimal BattleManager for testing."""
    from stochastic_warfare.simulation.battle import BattleManager

    bm = BattleManager(EventBus(), {})
    return bm


class TestGetStateCompleteness:
    """get_state() includes all 12 expected fields."""

    def test_ticks_stationary_in_state(self):
        bm = _make_battle_manager()
        bm._ticks_stationary = {"u1": 5, "u2": 3}
        state = bm.get_state()
        assert "ticks_stationary" in state
        assert state["ticks_stationary"] == {"u1": 5, "u2": 3}

    def test_suppression_states_in_state(self):
        bm = _make_battle_manager()
        s = UnitSuppressionState()
        s.value = 0.75
        s.source_direction = 1.57
        bm._suppression_states = {"u1": s}
        state = bm.get_state()
        assert "suppression_states" in state
        assert state["suppression_states"]["u1"]["value"] == 0.75
        assert state["suppression_states"]["u1"]["source_direction"] == 1.57

    def test_cumulative_casualties_in_state(self):
        bm = _make_battle_manager()
        bm._cumulative_casualties = {"u1": 3, "u2": 7}
        state = bm.get_state()
        assert state["cumulative_casualties"] == {"u1": 3, "u2": 7}

    def test_undigging_in_state(self):
        bm = _make_battle_manager()
        bm._undigging = {"u1": True, "u3": True}
        state = bm.get_state()
        assert state["undigging"] == {"u1": True, "u3": True}

    def test_concealment_scores_in_state(self):
        bm = _make_battle_manager()
        bm._concealment_scores = {"u1": 0.8, "u2": 0.3}
        state = bm.get_state()
        assert state["concealment_scores"] == {"u1": 0.8, "u2": 0.3}

    def test_env_casualty_accum_in_state(self):
        bm = _make_battle_manager()
        bm._env_casualty_accum = {"u1": 0.6, "u2": 0.2}
        state = bm.get_state()
        assert state["env_casualty_accum"] == {"u1": 0.6, "u2": 0.2}

    def test_misinterpreted_orders_in_state(self):
        bm = _make_battle_manager()
        bm._misinterpreted_orders = {"u1": _misinterpreted_order()}
        state = bm.get_state()
        assert "misinterpreted_orders" in state
        assert state["misinterpreted_orders"]["u1"] == {
            "success": True,
            "total_delay_s": 30.0,
            "was_misinterpreted": True,
            "misinterpretation_type": "position",
            "comms_quality": 0.7,
            "degraded": True,
        }


class TestSetStateRestore:
    """set_state() correctly restores each field."""

    def test_restore_ticks_stationary(self):
        bm = _make_battle_manager()
        state = bm.get_state()
        state["ticks_stationary"] = {"u1": 10}
        bm.set_state(state)
        assert bm._ticks_stationary == {"u1": 10}

    def test_restore_suppression_states(self):
        bm = _make_battle_manager()
        state = bm.get_state()
        state["suppression_states"] = {
            "u1": {"value": 0.5, "source_direction": 3.14},
        }
        bm.set_state(state)
        assert "u1" in bm._suppression_states
        assert isinstance(bm._suppression_states["u1"], UnitSuppressionState)
        assert bm._suppression_states["u1"].value == 0.5
        assert bm._suppression_states["u1"].source_direction == 3.14

    def test_restore_cumulative_casualties(self):
        bm = _make_battle_manager()
        state = bm.get_state()
        state["cumulative_casualties"] = {"u1": 5}
        bm.set_state(state)
        assert bm._cumulative_casualties == {"u1": 5}

    def test_restore_undigging(self):
        bm = _make_battle_manager()
        state = bm.get_state()
        state["undigging"] = {"u1": True}
        bm.set_state(state)
        assert bm._undigging == {"u1": True}

    def test_restore_concealment_scores(self):
        bm = _make_battle_manager()
        state = bm.get_state()
        state["concealment_scores"] = {"u1": 0.9}
        bm.set_state(state)
        assert bm._concealment_scores == {"u1": 0.9}
        assert isinstance(bm._concealment_scores["u1"], float)

    def test_restore_env_casualty_accum(self):
        bm = _make_battle_manager()
        state = bm.get_state()
        state["env_casualty_accum"] = {"u1": 0.7}
        bm.set_state(state)
        assert bm._env_casualty_accum == {"u1": 0.7}
        assert isinstance(bm._env_casualty_accum["u1"], float)

    def test_restore_misinterpreted_orders(self):
        bm = _make_battle_manager()
        state = bm.get_state()
        state["misinterpreted_orders"] = {
            "u1": {
                "success": True,
                "total_delay_s": 30.0,
                "was_misinterpreted": True,
                "misinterpretation_type": "position",
                "comms_quality": 0.7,
                "degraded": True,
            },
        }
        bm.set_state(state)
        assert bm._misinterpreted_orders == {"u1": _misinterpreted_order()}

    def test_misinterpreted_orders_cross_json_checkpoint_boundary(self):
        bm = _make_battle_manager()
        bm._misinterpreted_orders = {"u1": _misinterpreted_order()}
        serialized = json.dumps(bm.get_state(), cls=NumpyEncoder)

        restored = _make_battle_manager()
        restored.set_state(json.loads(serialized))

        assert restored._misinterpreted_orders == {
            "u1": _misinterpreted_order(),
        }
        assert restored.get_state() == bm.get_state()


class TestRoundTrip:
    """get_state → set_state → get_state produces consistent results."""

    def test_full_round_trip(self):
        bm = _make_battle_manager()
        # Populate all fields
        bm._ticks_stationary = {"u1": 5}
        s = UnitSuppressionState()
        s.value = 0.6
        s.source_direction = 2.0
        bm._suppression_states = {"u1": s}
        bm._cumulative_casualties = {"u1": 3}
        bm._undigging = {"u2": True}
        bm._concealment_scores = {"u1": 0.4}
        bm._env_casualty_accum = {"u1": 0.3}
        bm._misinterpreted_orders = {"u3": _misinterpreted_order()}

        state1 = bm.get_state()

        # Restore into a fresh BattleManager
        bm2 = _make_battle_manager()
        bm2.set_state(state1)
        state2 = bm2.get_state()

        # Compare all Phase 72b fields
        assert state2["ticks_stationary"] == state1["ticks_stationary"]
        assert state2["suppression_states"] == state1["suppression_states"]
        assert state2["cumulative_casualties"] == state1["cumulative_casualties"]
        assert state2["undigging"] == state1["undigging"]
        assert state2["concealment_scores"] == state1["concealment_scores"]
        assert state2["env_casualty_accum"] == state1["env_casualty_accum"]
        assert state2["misinterpreted_orders"] == state1["misinterpreted_orders"]

    def test_incomplete_state_rejects_without_mutation(self):
        """Only the engine's explicit versionless route may migrate old state."""
        bm = _make_battle_manager()
        bm._ticks_stationary = {"u1": 5}
        before = bm.get_state()

        with pytest.raises(ValueError, match="key topology"):
            bm.set_state({})

        assert bm.get_state() == before
