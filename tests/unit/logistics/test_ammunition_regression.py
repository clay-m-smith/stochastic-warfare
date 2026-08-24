"""Phase 68b: Ammo-gate configuration and checkpoint-state contracts."""

from __future__ import annotations

import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.simulation.battle import BattleManager
from stochastic_warfare.simulation.calibration import CalibrationSchema


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

    def test_incomplete_state_rejects_atomically(self):
        """Strict restore rejects incomplete state without clearing ammo."""
        mgr = BattleManager(EventBus())
        mgr._ammo_expended["old"] = 99
        before = mgr.get_state()
        state = {"next_battle_id": 0, "battles": {}}

        with pytest.raises(ValueError, match="key topology"):
            mgr.set_state(state)

        assert mgr.get_state() == before


class TestCalibrationField:
    """CalibrationSchema accepts enable_ammo_gate."""

    def test_default_false(self):
        schema = CalibrationSchema()
        assert schema.enable_ammo_gate is False

    def test_can_enable(self):
        schema = CalibrationSchema(enable_ammo_gate=True)
        assert schema.enable_ammo_gate is True
