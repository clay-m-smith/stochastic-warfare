"""Phase 66a: Mine warfare completion tests — persistence, sweeping, laying."""

from __future__ import annotations

import math

import numpy as np

from stochastic_warfare.combat.damage import DamageEngine
from stochastic_warfare.combat.naval_mine import (
    MineType,
    MineWarfareEngine,
)
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position
from stochastic_warfare.simulation.calibration import CalibrationSchema


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def _make_mine_engine(seed: int = 42) -> MineWarfareEngine:
    bus = EventBus()
    rng = _rng(seed)
    damage = DamageEngine(bus, rng)
    return MineWarfareEngine(damage, bus, rng)


class TestMinePersistence:
    """Mine battery decay over time."""

    def test_mines_disarm_over_time(self) -> None:
        eng = _make_mine_engine(seed=0)
        positions = [Position(i * 100, 0, 0) for i in range(20)]
        eng.lay_mines("layer_1", positions, MineType.MAGNETIC)
        assert all(m.armed for m in eng._mines)
        # Large time step — many hours — some should disarm
        eng.update_mine_persistence(5000.0)  # ~5000 hours
        disarmed = sum(1 for m in eng._mines if not m.armed)
        assert disarmed > 0

    def test_persistence_gated_by_flag(self) -> None:
        cal = CalibrationSchema(enable_mine_persistence=False)
        assert cal.get("enable_mine_persistence", True) is False

    def test_zero_time_no_disarm(self) -> None:
        eng = _make_mine_engine()
        eng.lay_mines("l1", [Position(0, 0, 0)], MineType.CONTACT)
        eng.update_mine_persistence(0.0)
        assert all(m.armed for m in eng._mines)


class TestMineSweeping:
    """Mine sweeping called for minesweeper units."""

    def test_sweep_clears_mines_near_position(self) -> None:
        eng = _make_mine_engine(seed=10)
        # Lay mines at center
        center = Position(500, 500, 0)
        positions = [Position(500 + i * 10, 500 + i * 10, 0) for i in range(5)]
        eng.lay_mines("l1", positions, MineType.CONTACT)
        result = eng.sweep_mines(
            "sweeper_1", area_m2=500_000,
            mine_type=MineType.CONTACT, dt=300.0,
            sweep_center=center, sweep_radius_m=2000.0,
        )
        assert result.mines_swept >= 0
        assert result.area_cleared_m2 > 0

    def test_sweep_outside_radius_skips_mines(self) -> None:
        eng = _make_mine_engine(seed=10)
        eng.lay_mines("l1", [Position(10000, 10000, 0)], MineType.CONTACT)
        result = eng.sweep_mines(
            "sweeper_1", area_m2=500_000,
            mine_type=MineType.CONTACT, dt=300.0,
            sweep_center=Position(0, 0, 0), sweep_radius_m=100.0,
        )
        # Mine is 14km away — should not be swept
        assert result.mines_swept == 0


class TestMineLaying:
    """Direct API tests for mine laying."""

    def test_lay_mines_creates_mine_objects(self) -> None:
        eng = _make_mine_engine()
        mines = eng.lay_mines("l1", [Position(0, 0, 0)], MineType.ACOUSTIC, count_per_pos=3)
        assert len(mines) == 3
        assert all(m.mine_type == MineType.ACOUSTIC for m in mines)
        assert all(m.armed for m in mines)

    def test_mine_density_computation(self) -> None:
        eng = _make_mine_engine()
        eng.lay_mines("l1", [Position(0, 0, 0)], MineType.CONTACT, count_per_pos=5)
        density = eng.compute_minefield_density(Position(0, 0, 0), 100.0)
        expected = 5.0 / (math.pi * 100.0 ** 2)
        assert abs(density - expected) < 1e-8


class TestMineCheckpoint:
    """Mine warfare checkpoint round-trip."""

    def test_get_set_state_roundtrip(self) -> None:
        eng = _make_mine_engine()
        eng.lay_mines("l1", [Position(100, 200, 0)], MineType.MAGNETIC, count_per_pos=2)
        state = eng.get_state()
        eng2 = _make_mine_engine(seed=99)
        eng2.set_state(state)
        assert len(eng2._mines) == 2
        assert eng2._mines[0].mine_type == MineType.MAGNETIC
