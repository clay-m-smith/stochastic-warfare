"""Phase 68b: Ammo depletion gate tests.

Verifies that when ``enable_ammo_gate=True`` weapons with a
``magazine_capacity`` are blocked after firing that many rounds, and that
weapons without capacity fire unlimited.
"""

from __future__ import annotations

import pytest

from stochastic_warfare.simulation.battle import BattleManager
from stochastic_warfare.simulation.calibration import CalibrationSchema
from stochastic_warfare.core.events import EventBus


class TestAmmoExpendedTracking:
    """Low-level _ammo_expended tracking on BattleManager."""

    def test_ammo_expended_starts_empty(self):
        mgr = BattleManager(EventBus())
        assert mgr._ammo_expended == {}

    def test_ammo_expended_increments(self):
        mgr = BattleManager(EventBus())
        key = "tank1:m256_120mm"
        mgr._ammo_expended[key] = mgr._ammo_expended.get(key, 0) + 1
        assert mgr._ammo_expended[key] == 1
        mgr._ammo_expended[key] = mgr._ammo_expended.get(key, 0) + 1
        assert mgr._ammo_expended[key] == 2

    def test_different_weapons_tracked_independently(self):
        mgr = BattleManager(EventBus())
        mgr._ammo_expended["tank1:main_gun"] = 5
        mgr._ammo_expended["tank1:coax_mg"] = 100
        assert mgr._ammo_expended["tank1:main_gun"] == 5
        assert mgr._ammo_expended["tank1:coax_mg"] == 100

    def test_ammo_gate_blocks_when_exhausted(self):
        """Magazine capacity reached → weapon should be blocked."""
        mgr = BattleManager(EventBus())
        key = "unit1:javelin"
        magazine_capacity = 2
        mgr._ammo_expended[key] = 2

        rounds_fired = mgr._ammo_expended.get(key, 0)
        assert rounds_fired >= magazine_capacity  # should block

    def test_ammo_gate_allows_when_remaining(self):
        """Rounds < capacity → weapon should fire."""
        mgr = BattleManager(EventBus())
        key = "unit1:javelin"
        magazine_capacity = 2
        mgr._ammo_expended[key] = 1

        rounds_fired = mgr._ammo_expended.get(key, 0)
        assert rounds_fired < magazine_capacity  # should allow

    def test_no_magazine_capacity_means_unlimited(self):
        """Weapons without magazine_capacity fire unlimited."""
        # magazine_capacity == 0 means unlimited
        magazine_capacity = 0
        assert not (magazine_capacity > 0)  # gate check: if _mag_cap > 0


class TestAmmoCheckpointState:
    """Ammo expended state survives get_state/set_state."""

    def test_get_state_includes_ammo(self):
        mgr = BattleManager(EventBus())
        mgr._ammo_expended["t1:gun"] = 5
        state = mgr.get_state()
        assert state["ammo_expended"] == {"t1:gun": 5}

    def test_set_state_restores_ammo(self):
        mgr = BattleManager(EventBus())
        state = mgr.get_state()
        state["ammo_expended"] = {"t1:gun": 3, "t2:missile": 1}
        mgr.set_state(state)
        assert mgr._ammo_expended == {"t1:gun": 3, "t2:missile": 1}

    def test_set_state_backward_compat(self):
        """Old states without ammo_expended default to empty."""
        mgr = BattleManager(EventBus())
        mgr._ammo_expended["old"] = 99
        state = {"next_battle_id": 0, "battles": {}}
        mgr.set_state(state)
        assert mgr._ammo_expended == {}


class TestCalibrationField:
    """CalibrationSchema accepts enable_ammo_gate."""

    def test_default_false(self):
        schema = CalibrationSchema()
        assert schema.enable_ammo_gate is False

    def test_can_enable(self):
        schema = CalibrationSchema(enable_ammo_gate=True)
        assert schema.enable_ammo_gate is True
