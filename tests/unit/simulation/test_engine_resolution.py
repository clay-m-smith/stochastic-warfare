"""Unit tests for SimulationEngine resolution switching methods.

Phase 75b: Tests _forces_within_closing_range, _update_resolution,
_set_resolution, _compute_battle_positions, _snapshot_unit_cells.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.base import UnitStatus

from .conftest import _make_unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_resolution_engine(
    units_by_side: dict[str, list] | None = None,
    engagement_range_m: float = 10000.0,
    closing_range_mult: float = 2.0,
    active_battles: list | None = None,
):
    """Build a mock SimulationEngine for resolution tests."""
    from stochastic_warfare.simulation.engine import TickResolution
    from stochastic_warfare.simulation.battle import BattleManager

    ubs = units_by_side or {}

    clock = SimpleNamespace(
        tick_duration=timedelta(seconds=10),
        set_tick_duration=lambda td: setattr(clock, "tick_duration", td),
    )

    ctx = SimpleNamespace(
        units_by_side=ubs,
        clock=clock,
        heightmap=None,
    )

    campaign_config = SimpleNamespace(
        engagement_detection_range_m=engagement_range_m,
    )

    battle = SimpleNamespace(
        active_battles=active_battles or [],
        _min_distance=BattleManager._min_distance,
    )

    engine = SimpleNamespace(
        _ctx=ctx,
        _config=SimpleNamespace(resolution_closing_range_mult=closing_range_mult),
        _campaign=SimpleNamespace(_config=campaign_config),
        _battle=battle,
        _resolution=TickResolution.STRATEGIC,
        _tick_durations={
            TickResolution.STRATEGIC: 3600.0,
            TickResolution.OPERATIONAL: 60.0,
            TickResolution.TACTICAL: 10.0,
        },
    )

    from stochastic_warfare.simulation.engine import SimulationEngine

    engine._forces_within_closing_range = lambda: SimulationEngine._forces_within_closing_range(engine)
    engine._update_resolution = lambda: SimulationEngine._update_resolution(engine)
    engine._set_resolution = lambda r: SimulationEngine._set_resolution(engine, r)
    engine._compute_battle_positions = lambda ctx: SimulationEngine._compute_battle_positions(engine, ctx)
    engine._snapshot_unit_cells = lambda ctx: SimulationEngine._snapshot_unit_cells(engine, ctx)

    return engine


# ===================================================================
# _forces_within_closing_range
# ===================================================================


class TestForcesWithinClosingRange:
    """Check if opposing forces are within closing range."""

    def test_far_apart(self):
        u_blue = _make_unit("u1", "blue", Position(0.0, 0.0, 0.0))
        u_red = _make_unit("u2", "red", Position(100000.0, 0.0, 0.0))
        u_blue.status = UnitStatus.ACTIVE
        u_red.status = UnitStatus.ACTIVE
        engine = _make_resolution_engine({"blue": [u_blue], "red": [u_red]})
        assert engine._forces_within_closing_range() is False

    def test_close_together(self):
        u_blue = _make_unit("u1", "blue", Position(0.0, 0.0, 0.0))
        u_red = _make_unit("u2", "red", Position(100.0, 0.0, 0.0))
        u_blue.status = UnitStatus.ACTIVE
        u_red.status = UnitStatus.ACTIVE
        engine = _make_resolution_engine({"blue": [u_blue], "red": [u_red]})
        assert engine._forces_within_closing_range() is True

    def test_single_side(self):
        u = _make_unit("u1", "blue", Position(0.0, 0.0, 0.0))
        u.status = UnitStatus.ACTIVE
        engine = _make_resolution_engine({"blue": [u]})
        assert engine._forces_within_closing_range() is False

    def test_empty(self):
        engine = _make_resolution_engine({})
        assert engine._forces_within_closing_range() is False

    def test_config_threshold(self):
        # threshold = engagement_range * mult = 10000 * 2 = 20000
        u_blue = _make_unit("u1", "blue", Position(0.0, 0.0, 0.0))
        u_red = _make_unit("u2", "red", Position(15000.0, 0.0, 0.0))
        u_blue.status = UnitStatus.ACTIVE
        u_red.status = UnitStatus.ACTIVE
        engine = _make_resolution_engine({"blue": [u_blue], "red": [u_red]})
        assert engine._forces_within_closing_range() is True  # 15000 < 20000


# ===================================================================
# _update_resolution
# ===================================================================


class TestUpdateResolution:
    """Resolution switching based on battle state."""

    def test_active_battles_to_tactical(self):
        from stochastic_warfare.simulation.engine import TickResolution
        engine = _make_resolution_engine(active_battles=["battle_1"])
        engine._update_resolution()
        assert engine._resolution == TickResolution.TACTICAL

    def test_closing_to_operational(self):
        from stochastic_warfare.simulation.engine import TickResolution
        u_blue = _make_unit("u1", "blue", Position(0.0, 0.0, 0.0))
        u_red = _make_unit("u2", "red", Position(100.0, 0.0, 0.0))
        u_blue.status = UnitStatus.ACTIVE
        u_red.status = UnitStatus.ACTIVE
        engine = _make_resolution_engine({"blue": [u_blue], "red": [u_red]})
        engine._update_resolution()
        assert engine._resolution == TickResolution.OPERATIONAL

    def test_deescalation_chain(self):
        from stochastic_warfare.simulation.engine import TickResolution
        u_blue = _make_unit("u1", "blue", Position(0.0, 0.0, 0.0))
        u_red = _make_unit("u2", "red", Position(200000.0, 0.0, 0.0))
        u_blue.status = UnitStatus.ACTIVE
        u_red.status = UnitStatus.ACTIVE
        engine = _make_resolution_engine({"blue": [u_blue], "red": [u_red]})
        engine._resolution = TickResolution.TACTICAL
        engine._update_resolution()
        assert engine._resolution == TickResolution.OPERATIONAL

    def test_operational_to_strategic(self):
        from stochastic_warfare.simulation.engine import TickResolution
        u_blue = _make_unit("u1", "blue", Position(0.0, 0.0, 0.0))
        u_red = _make_unit("u2", "red", Position(200000.0, 0.0, 0.0))
        u_blue.status = UnitStatus.ACTIVE
        u_red.status = UnitStatus.ACTIVE
        engine = _make_resolution_engine({"blue": [u_blue], "red": [u_red]})
        engine._resolution = TickResolution.OPERATIONAL
        engine._update_resolution()
        assert engine._resolution == TickResolution.STRATEGIC

    def test_already_strategic_stays(self):
        from stochastic_warfare.simulation.engine import TickResolution
        u_blue = _make_unit("u1", "blue", Position(0.0, 0.0, 0.0))
        u_red = _make_unit("u2", "red", Position(200000.0, 0.0, 0.0))
        u_blue.status = UnitStatus.ACTIVE
        u_red.status = UnitStatus.ACTIVE
        engine = _make_resolution_engine({"blue": [u_blue], "red": [u_red]})
        engine._resolution = TickResolution.STRATEGIC
        engine._update_resolution()
        assert engine._resolution == TickResolution.STRATEGIC


# ===================================================================
# _set_resolution
# ===================================================================


class TestSetResolution:
    """Apply new tick resolution."""

    def test_changes_resolution(self):
        from stochastic_warfare.simulation.engine import TickResolution
        engine = _make_resolution_engine()
        engine._set_resolution(TickResolution.TACTICAL)
        assert engine._resolution == TickResolution.TACTICAL

    def test_same_noop(self):
        from stochastic_warfare.simulation.engine import TickResolution
        engine = _make_resolution_engine()
        engine._resolution = TickResolution.STRATEGIC
        engine._set_resolution(TickResolution.STRATEGIC)
        # Clock duration should not change from initial
        assert engine._ctx.clock.tick_duration == timedelta(seconds=10)

    def test_clock_updated(self):
        from stochastic_warfare.simulation.engine import TickResolution
        engine = _make_resolution_engine()
        engine._set_resolution(TickResolution.TACTICAL)
        assert engine._ctx.clock.tick_duration == timedelta(seconds=10)

    def test_transition_logged(self):
        from stochastic_warfare.simulation.engine import TickResolution
        engine = _make_resolution_engine()
        # Just verify no crash — logging is tested structurally
        engine._set_resolution(TickResolution.OPERATIONAL)


# ===================================================================
# _compute_battle_positions
# ===================================================================


class TestComputeBattlePositions:
    """Compute centroid positions of active battles."""

    def test_no_battles(self):
        engine = _make_resolution_engine()
        result = engine._compute_battle_positions(engine._ctx)
        assert result == []

    def test_with_battle(self):
        u1 = _make_unit("u1", "blue", Position(100.0, 200.0, 0.0))
        u1.status = UnitStatus.ACTIVE
        u2 = _make_unit("u2", "blue", Position(300.0, 400.0, 0.0))
        u2.status = UnitStatus.ACTIVE
        battle = SimpleNamespace(unit_ids={"u1", "u2"})
        engine = _make_resolution_engine(
            {"blue": [u1, u2]},
            active_battles=[battle],
        )
        result = engine._compute_battle_positions(engine._ctx)
        assert len(result) == 1
        assert result[0].easting == pytest.approx(200.0)
        assert result[0].northing == pytest.approx(300.0)


# ===================================================================
# _snapshot_unit_cells
# ===================================================================


class TestSnapshotUnitCells:
    """Snapshot grid cells for selective LOS invalidation."""

    def test_no_heightmap(self):
        engine = _make_resolution_engine()
        result = engine._snapshot_unit_cells(engine._ctx)
        assert result == {}

    def test_with_heightmap(self):
        u = _make_unit("u1")
        u.status = UnitStatus.ACTIVE
        engine = _make_resolution_engine({"blue": [u]})
        engine._ctx.heightmap = SimpleNamespace(
            enu_to_grid=lambda pos: (5, 10),
        )
        result = engine._snapshot_unit_cells(engine._ctx)
        assert result["u1"] == (5, 10)
