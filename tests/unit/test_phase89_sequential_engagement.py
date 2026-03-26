"""Phase 89c/d: Sequential engagement verification and integration tests.

Engagement resolution must remain sequential for determinism.
Per-side parallel detection must not affect engagement outcomes.
"""

from __future__ import annotations

import inspect

import numpy as np
import pytest

from stochastic_warfare.simulation.battle import BattleManager
from stochastic_warfare.simulation.calibration import CalibrationSchema


# ── Sequential Engagement Tests ────────────────────────────────────────


class TestSequentialEngagement:
    """Engagement resolution is sequential and deterministic."""

    def test_engagement_not_threaded(self) -> None:
        """_execute_engagements does not use ThreadPoolExecutor."""
        src = inspect.getsource(BattleManager._execute_engagements)
        assert "ThreadPoolExecutor" not in src
        assert ".submit(" not in src

    def test_engagement_source_is_per_side_loop(self) -> None:
        """Engagements iterate per side sequentially."""
        src = inspect.getsource(BattleManager._execute_engagements)
        assert "for side_name, side_units in" in src or "for side_name," in src

    def test_parallel_detection_flag_not_in_engagements(self) -> None:
        """enable_parallel_detection is not referenced in engagement code."""
        src = inspect.getsource(BattleManager._execute_engagements)
        assert "enable_parallel_detection" not in src


class TestDeferredFlag:
    """Phase 89 flag properly deferred."""

    def test_enable_parallel_detection_default_false(self) -> None:
        cal = CalibrationSchema()
        assert cal.enable_parallel_detection is False

    def test_enable_parallel_detection_in_flat_dict(self) -> None:
        """Flat dict includes the new flag."""
        cal = CalibrationSchema()
        flat = cal.to_flat_dict(["blue", "red"])
        assert "enable_parallel_detection" in flat
        assert flat["enable_parallel_detection"] is False

    def test_enable_parallel_detection_in_deferred_flags(self) -> None:
        """Structural: flag is in _DEFERRED_FLAGS in test_phase_67_structural.py."""
        from pathlib import Path
        structural = Path(__file__).resolve().parents[1] / "validation" / "test_phase_67_structural.py"
        src = structural.read_text(encoding="utf-8")
        assert "enable_parallel_detection" in src
