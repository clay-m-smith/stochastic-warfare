"""Phase 65 Step S: Structural verification tests.

Source-level assertions ensuring Phase 65 wiring is present.
"""

from __future__ import annotations

import inspect

import pytest


def test_engine_sigint_uses_ctx_not_ew():
    """Bug fix: sigint_engine accessed from ctx, not ew_engine."""
    from stochastic_warfare.simulation.engine import SimulationEngine

    source = inspect.getsource(SimulationEngine._fuse_sigint)
    assert 'getattr(ctx, "sigint_engine"' in source
    # Must NOT have the old buggy pattern
    assert 'getattr(ew, "sigint_engine"' not in source


def test_engine_fusion_via_intel_fusion_not_intel_fusion_engine():
    """Bug fix: fusion accessed via fog_of_war.intel_fusion, not ctx.intel_fusion_engine."""
    from stochastic_warfare.simulation.engine import SimulationEngine

    source = inspect.getsource(SimulationEngine._fuse_sigint)
    assert "intel_fusion" in source
    assert '"intel_fusion_engine"' not in source


def test_battle_contains_compute_jam_reduction():
    """ECCM wiring: battle.py calls compute_jam_reduction."""
    from stochastic_warfare.simulation.battle import BattleManager

    source = inspect.getsource(BattleManager)
    assert "compute_jam_reduction" in source


def test_engine_contains_run_sigint_intercepts():
    """SIGINT wiring: engine.py has _run_sigint_intercepts."""
    from stochastic_warfare.simulation.engine import SimulationEngine

    assert hasattr(SimulationEngine, "_run_sigint_intercepts")
    source = inspect.getsource(SimulationEngine._run_sigint_intercepts)
    assert "attempt_intercept" in source


def test_engine_contains_missile_launch_handler():
    """Early warning wiring: engine.py has _handle_missile_launch."""
    from stochastic_warfare.simulation.engine import SimulationEngine

    assert hasattr(SimulationEngine, "_handle_missile_launch")
    source = inspect.getsource(SimulationEngine._handle_missile_launch)
    assert "check_launch_detection" in source


def test_calibration_contains_enable_space_effects():
    """CalibrationSchema has enable_space_effects field."""
    from stochastic_warfare.simulation.calibration import CalibrationSchema

    assert "enable_space_effects" in CalibrationSchema.model_fields
