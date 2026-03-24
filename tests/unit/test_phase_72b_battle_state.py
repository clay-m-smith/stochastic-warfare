"""Phase 72b — Verify BattleManager get_state/set_state includes all instance vars.

Tests ensure the 7 previously missing instance variables are now captured
in checkpoint state and correctly restored.
"""

from __future__ import annotations

from typing import Any


from stochastic_warfare.combat.suppression import UnitSuppressionState
from stochastic_warfare.core.events import EventBus


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
        bm._misinterpreted_orders = {"u1": {"offset": 150.0}}
        state = bm.get_state()
        assert "misinterpreted_orders" in state


class TestSetStateRestore:
    """set_state() correctly restores each field."""

    def test_restore_ticks_stationary(self):
        bm = _make_battle_manager()
        bm.set_state({"ticks_stationary": {"u1": 10}})
        assert bm._ticks_stationary == {"u1": 10}

    def test_restore_suppression_states(self):
        bm = _make_battle_manager()
        bm.set_state({
            "suppression_states": {
                "u1": {"value": 0.5, "source_direction": 3.14}
            }
        })
        assert "u1" in bm._suppression_states
        assert isinstance(bm._suppression_states["u1"], UnitSuppressionState)
        assert bm._suppression_states["u1"].value == 0.5
        assert bm._suppression_states["u1"].source_direction == 3.14

    def test_restore_cumulative_casualties(self):
        bm = _make_battle_manager()
        bm.set_state({"cumulative_casualties": {"u1": 5}})
        assert bm._cumulative_casualties == {"u1": 5}

    def test_restore_undigging(self):
        bm = _make_battle_manager()
        bm.set_state({"undigging": {"u1": True}})
        assert bm._undigging == {"u1": True}

    def test_restore_concealment_scores(self):
        bm = _make_battle_manager()
        bm.set_state({"concealment_scores": {"u1": 0.9}})
        assert bm._concealment_scores == {"u1": 0.9}
        assert isinstance(bm._concealment_scores["u1"], float)

    def test_restore_env_casualty_accum(self):
        bm = _make_battle_manager()
        bm.set_state({"env_casualty_accum": {"u1": 0.7}})
        assert bm._env_casualty_accum == {"u1": 0.7}
        assert isinstance(bm._env_casualty_accum["u1"], float)

    def test_restore_misinterpreted_orders(self):
        bm = _make_battle_manager()
        bm.set_state({"misinterpreted_orders": {"u1": "offset_data"}})
        assert bm._misinterpreted_orders == {"u1": "offset_data"}


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
        bm._misinterpreted_orders = {"u3": {"radius": 100}}

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

    def test_backward_compat_empty_state(self):
        """Old checkpoints missing new keys → defaults to empty."""
        bm = _make_battle_manager()
        # Simulate old checkpoint format (no Phase 72b keys)
        bm.set_state({})
        assert bm._ticks_stationary == {}
        assert bm._suppression_states == {}
        assert bm._cumulative_casualties == {}
        assert bm._undigging == {}
        assert bm._concealment_scores == {}
        assert bm._env_casualty_accum == {}
        assert bm._misinterpreted_orders == {}
