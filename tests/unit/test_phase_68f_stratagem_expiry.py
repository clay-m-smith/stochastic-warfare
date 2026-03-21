"""Phase 68f: Stratagem expiry tests.

Verifies that stratagems are tracked by activation tick and expire after
``stratagem_duration_ticks``.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from stochastic_warfare.c2.ai.stratagems import (
    StratagemEngine,
    StratagemPlan,
    StratagemType,
)
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.simulation.calibration import CalibrationSchema

TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def _make_plan(stratagem_id: str = "s1", stype: StratagemType = StratagemType.CONCENTRATION) -> StratagemPlan:
    return StratagemPlan(
        stratagem_id=stratagem_id,
        stratagem_type=stype,
        description="test stratagem",
        target_area="sector_A",
        units_involved=("u1", "u2"),
        estimated_effect=0.5,
        risk=0.2,
    )


class TestStratagemExpiry:
    """Stratagems expire after configured duration."""

    def test_active_at_activation_tick(self):
        eng = StratagemEngine(EventBus(), _rng())
        plan = _make_plan("s1")
        eng.activate_stratagem("cmd1", plan, TS, tick=0)

        assert eng.is_active("s1")
        assert "s1" in eng._active_plans
        assert eng._activation_ticks["s1"] == 0

    def test_expired_after_duration(self):
        eng = StratagemEngine(EventBus(), _rng())
        plan = _make_plan("s1")
        eng.activate_stratagem("cmd1", plan, TS, tick=0)

        expired = eng.expire_stratagems(current_tick=100, duration=100)
        assert "s1" in expired
        assert not eng.is_active("s1")
        assert "s1" not in eng._active_plans
        assert "s1" not in eng._activation_ticks

    def test_not_expired_before_duration(self):
        eng = StratagemEngine(EventBus(), _rng())
        plan = _make_plan("s1")
        eng.activate_stratagem("cmd1", plan, TS, tick=0)

        expired = eng.expire_stratagems(current_tick=99, duration=100)
        assert expired == []
        assert eng.is_active("s1")

    def test_custom_duration_from_calibration(self):
        schema = CalibrationSchema(stratagem_duration_ticks=50)
        assert schema.stratagem_duration_ticks == 50

        eng = StratagemEngine(EventBus(), _rng())
        plan = _make_plan("s1")
        eng.activate_stratagem("cmd1", plan, TS, tick=10)

        expired = eng.expire_stratagems(current_tick=60, duration=50)
        assert "s1" in expired

    def test_multiple_concurrent_stratagems(self):
        eng = StratagemEngine(EventBus(), _rng())
        p1 = _make_plan("s1")
        p2 = _make_plan("s2", StratagemType.DECEPTION)

        eng.activate_stratagem("cmd1", p1, TS, tick=0)
        eng.activate_stratagem("cmd1", p2, TS, tick=50)

        # At tick 100, duration=100: s1 expired, s2 still active
        expired = eng.expire_stratagems(current_tick=100, duration=100)
        assert "s1" in expired
        assert "s2" not in expired
        assert not eng.is_active("s1")
        assert eng.is_active("s2")

    def test_get_state_includes_activation_ticks(self):
        eng = StratagemEngine(EventBus(), _rng())
        plan = _make_plan("s1")
        eng.activate_stratagem("cmd1", plan, TS, tick=42)

        state = eng.get_state()
        assert "activation_ticks" in state
        assert state["activation_ticks"]["s1"] == 42

    def test_set_state_restores_activation_ticks(self):
        eng = StratagemEngine(EventBus(), _rng())
        plan = _make_plan("s1")
        eng.activate_stratagem("cmd1", plan, TS, tick=42)

        state = eng.get_state()

        eng2 = StratagemEngine(EventBus(), _rng())
        eng2.set_state(state)

        assert eng2.is_active("s1")
        assert eng2._activation_ticks["s1"] == 42

    def test_set_state_backward_compat(self):
        """Old state without activation_ticks → empty dict."""
        eng = StratagemEngine(EventBus(), _rng())
        old_state = {"active_plans": {}}
        eng.set_state(old_state)
        assert eng._activation_ticks == {}
