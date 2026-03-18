"""Phase 64 Step S: Structural verification tests.

Source-level string assertions to catch regressions in Phase 64 wiring.
"""

from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _read_source(rel_path: str) -> str:
    return (PROJECT_ROOT / rel_path).read_text(encoding="utf-8")


class TestPhase64Structural:
    """Structural verification that Phase 64 wiring is present."""

    def test_propagation_none_guard(self):
        """propagation.py contains None guard for command engine."""
        text = _read_source("stochastic_warfare/c2/orders/propagation.py")
        assert "self._command is not None" in text

    def test_battle_propagate_order(self):
        """battle.py calls propagate_order (not just logging)."""
        text = _read_source("stochastic_warfare/simulation/battle.py")
        assert "propagate_order" in text

    def test_battle_initiate_planning(self):
        """battle.py calls initiate_planning (planning wiring)."""
        text = _read_source("stochastic_warfare/simulation/battle.py")
        assert "initiate_planning" in text

    def test_battle_activate_stratagem(self):
        """battle.py calls activate_stratagem (not just evaluate)."""
        text = _read_source("stochastic_warfare/simulation/battle.py")
        assert "activate_stratagem" in text

    def test_engine_advance_phase(self):
        """engine.py calls advance_phase (planning tick)."""
        text = _read_source("stochastic_warfare/simulation/engine.py")
        assert "advance_phase" in text

    def test_engine_register_aircraft(self):
        """engine.py calls register_aircraft (ATO registration)."""
        text = _read_source("stochastic_warfare/simulation/engine.py")
        assert "register_aircraft" in text

    def test_calibration_planning_available_time(self):
        """calibration.py contains planning_available_time_s."""
        text = _read_source("stochastic_warfare/simulation/calibration.py")
        assert "planning_available_time_s" in text

    def test_calibration_stratagem_concentration_bonus(self):
        """calibration.py contains stratagem_concentration_bonus."""
        text = _read_source("stochastic_warfare/simulation/calibration.py")
        assert "stratagem_concentration_bonus" in text
