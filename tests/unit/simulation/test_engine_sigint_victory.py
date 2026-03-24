"""Unit tests for SimulationEngine SIGINT fusion and victory evaluation.

Phase 75b: Tests _evaluate_victory and _fuse_sigint methods.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.base import UnitStatus

from .conftest import _make_ctx, _make_unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_victory_engine(
    units_by_side: dict | None = None,
    victory_evaluator: object | None = None,
    morale_states: dict | None = None,
    stockpile_manager: object | None = None,
):
    """Build a minimal mock for _evaluate_victory."""
    from stochastic_warfare.simulation.engine import SimulationEngine

    ubs = units_by_side or {}
    clock = SimpleNamespace(
        elapsed=SimpleNamespace(total_seconds=lambda: 100.0),
    )
    ctx = SimpleNamespace(
        units_by_side=ubs,
        clock=clock,
        morale_states=morale_states or {},
        stockpile_manager=stockpile_manager,
    )

    engine = SimpleNamespace(
        _ctx=ctx,
        _victory=victory_evaluator,
    )
    engine._evaluate_victory = lambda tick: SimulationEngine._evaluate_victory(engine, tick)
    return engine


def _make_sigint_engine(
    calibration: object | None = None,
    space_engine: object | None = None,
    sigint_engine: object | None = None,
    fow: object | None = None,
):
    """Build a minimal mock for _fuse_sigint."""
    from stochastic_warfare.simulation.engine import SimulationEngine

    cal = calibration or SimpleNamespace(get=lambda k, d=None: d)
    ctx = SimpleNamespace(
        calibration=cal,
        space_engine=space_engine,
        fow=fow,
    )
    if sigint_engine is not None:
        ctx.sigint_engine = sigint_engine

    engine = SimpleNamespace(_ctx=ctx)
    engine._fuse_sigint = lambda: SimulationEngine._fuse_sigint(engine)
    return engine


# ===================================================================
# _evaluate_victory
# ===================================================================


class TestEvaluateVictory:
    """Victory evaluation delegation."""

    def test_no_evaluator(self):
        engine = _make_victory_engine(victory_evaluator=None)
        result = engine._evaluate_victory(10)
        assert result.game_over is False

    def test_delegates_to_evaluator(self):
        from stochastic_warfare.simulation.victory import VictoryResult
        mock_result = VictoryResult(
            game_over=True,
            winning_side="blue",
            condition_type="force_destroyed",
            message="Blue wins",
            tick=10,
        )
        evaluator = SimpleNamespace(
            update_objective_control=lambda ubs: None,
            evaluate=lambda **kwargs: mock_result,
            get_state=lambda: {},
        )
        engine = _make_victory_engine(
            units_by_side={"blue": [], "red": []},
            victory_evaluator=evaluator,
        )
        result = engine._evaluate_victory(10)
        assert result.game_over is True
        assert result.winning_side == "blue"

    def test_supply_states_forwarded(self):
        captured = {}

        def mock_evaluate(**kwargs):
            captured.update(kwargs)
            from stochastic_warfare.simulation.victory import VictoryResult
            return VictoryResult(game_over=False)

        mgr = SimpleNamespace(get_supply_state=lambda uid: 0.75)
        u = _make_unit("u1", "blue")
        evaluator = SimpleNamespace(
            update_objective_control=lambda ubs: None,
            evaluate=mock_evaluate,
        )
        engine = _make_victory_engine(
            units_by_side={"blue": [u]},
            victory_evaluator=evaluator,
            stockpile_manager=mgr,
        )
        engine._evaluate_victory(10)
        assert "supply_states" in captured
        assert captured["supply_states"]["u1"] == pytest.approx(0.75)

    def test_objectives_updated(self):
        updated = []
        evaluator = SimpleNamespace(
            update_objective_control=lambda ubs: updated.append(True),
            evaluate=lambda **kw: SimpleNamespace(game_over=False),
        )
        engine = _make_victory_engine(
            units_by_side={"blue": [], "red": []},
            victory_evaluator=evaluator,
        )
        engine._evaluate_victory(10)
        assert len(updated) == 1

    def test_exception_in_supply(self):
        """Supply manager exception should not prevent victory eval."""
        def bad_supply(uid):
            raise RuntimeError("fail")

        mgr = SimpleNamespace(get_supply_state=bad_supply)
        u = _make_unit("u1")
        evaluator = SimpleNamespace(
            update_objective_control=lambda ubs: None,
            evaluate=lambda **kw: SimpleNamespace(game_over=False),
        )
        engine = _make_victory_engine(
            units_by_side={"blue": [u]},
            victory_evaluator=evaluator,
            stockpile_manager=mgr,
        )
        # Should not raise — exception caught per unit
        engine._evaluate_victory(10)


# ===================================================================
# _fuse_sigint
# ===================================================================


class TestFuseSigint:
    """SIGINT fusion gated by enable_space_effects."""

    def test_disabled_noop(self):
        cal = SimpleNamespace(get=lambda k, d=None: False if k == "enable_space_effects" else d)
        engine = _make_sigint_engine(calibration=cal)
        engine._fuse_sigint()  # no error

    def test_missing_engines_noop(self):
        cal = SimpleNamespace(get=lambda k, d=None: True if k == "enable_space_effects" else d)
        engine = _make_sigint_engine(calibration=cal, space_engine=None)
        engine._fuse_sigint()  # no error

    def test_no_fow_noop(self):
        cal = SimpleNamespace(get=lambda k, d=None: True if k == "enable_space_effects" else d)
        space = SimpleNamespace(
            isr_engine=SimpleNamespace(get_recent_reports=lambda: []),
        )
        engine = _make_sigint_engine(calibration=cal, space_engine=space, fow=None)
        engine._fuse_sigint()  # no error
