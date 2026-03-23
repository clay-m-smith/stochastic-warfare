"""Unit tests for MineWarfareEngine — mine laying, encounter, sweeping."""

from __future__ import annotations

import pytest

from stochastic_warfare.combat.damage import DamageEngine
from stochastic_warfare.combat.naval_mine import (
    Mine,
    MineResult,
    MineType,
    MineWarfareConfig,
    MineWarfareEngine,
    SweepResult,
)
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position

from .conftest import _rng


def _make_engine(seed: int = 42, **cfg_kwargs) -> MineWarfareEngine:
    config = MineWarfareConfig(**cfg_kwargs) if cfg_kwargs else None
    damage = DamageEngine(EventBus(), _rng(seed + 10))
    return MineWarfareEngine(damage, EventBus(), _rng(seed), config=config)


# ---------------------------------------------------------------------------
# Lay mines
# ---------------------------------------------------------------------------


class TestLayMines:
    """Mine laying creates Mine objects."""

    def test_lay_mines_creates_objects(self):
        eng = _make_engine()
        mines = eng.lay_mines(
            "layer_1",
            positions=[Position(0, 0, -10), Position(100, 0, -10)],
            mine_type=MineType.CONTACT,
            count_per_pos=3,
        )
        # 2 positions * 3 per pos = 6
        assert len(mines) == 6
        assert all(isinstance(m, Mine) for m in mines)

    def test_mine_types_preserved(self):
        eng = _make_engine()
        for mt in [MineType.CONTACT, MineType.MAGNETIC, MineType.SMART]:
            mines = eng.lay_mines(
                f"layer_{mt.name}",
                positions=[Position(0, 0, -10)],
                mine_type=mt,
            )
            assert len(mines) == 1
            assert mines[0].mine_type == mt

    def test_placement_accuracy_scatter(self):
        """Nonzero placement_accuracy_m scatters mine positions."""
        eng = _make_engine(seed=5)
        mines = eng.lay_mines(
            "layer_1",
            positions=[Position(100.0, 200.0, -10)],
            mine_type=MineType.CONTACT,
            count_per_pos=5,
            placement_accuracy_m=50.0,
        )
        # At least one mine should be displaced from (100, 200)
        positions_differ = any(
            m.position.easting != 100.0 or m.position.northing != 200.0
            for m in mines
        )
        assert positions_differ


# ---------------------------------------------------------------------------
# Mine encounter
# ---------------------------------------------------------------------------


class TestMineEncounter:
    """Resolve mine encounters by type."""

    def test_contact_mine_trigger(self):
        eng = _make_engine(seed=10)
        mines = eng.lay_mines("l1", [Position(0, 0, -10)], MineType.CONTACT)
        result = eng.resolve_mine_encounter(
            "ship_1", mines[0],
            ship_magnetic_sig=0.5, ship_acoustic_sig=0.5,
        )
        assert isinstance(result, MineResult)
        assert hasattr(result, "triggered")

    def test_magnetic_mine_high_signature(self):
        """High magnetic signature increases trigger probability."""
        triggered_count = 0
        for i in range(50):
            eng = _make_engine(seed=i)
            mines = eng.lay_mines("l1", [Position(0, 0, -10)], MineType.MAGNETIC)
            result = eng.resolve_mine_encounter(
                "ship_1", mines[0],
                ship_magnetic_sig=1.0, ship_acoustic_sig=0.0,
            )
            if result.triggered:
                triggered_count += 1
        assert triggered_count > 10  # 1.0 * 0.9 = 0.9 trigger prob

    def test_smart_mine_selectivity(self):
        eng = _make_engine(seed=15)
        mines = eng.lay_mines("l1", [Position(0, 0, -10)], MineType.SMART)
        result = eng.resolve_mine_encounter(
            "ship_1", mines[0],
            ship_magnetic_sig=0.8, ship_acoustic_sig=0.8,
        )
        assert isinstance(result, MineResult)


# ---------------------------------------------------------------------------
# Sweeping
# ---------------------------------------------------------------------------


class TestMineSweeping:
    """Mine sweeping operations."""

    def test_sweep_clears_area(self):
        eng = _make_engine()
        eng.lay_mines("l1", [Position(0, 0, -10)], MineType.CONTACT, count_per_pos=10)
        result = eng.sweep_mines(
            "sweeper_1",
            area_m2=50000.0,
            mine_type=MineType.CONTACT,
            dt=120.0,
        )
        assert isinstance(result, SweepResult)
        assert result.area_cleared_m2 > 0

    def test_sweep_at_base_rate(self):
        """Cleared area respects base_sweep_rate_m2_per_s * difficulty * dt."""
        eng = _make_engine(base_sweep_rate_m2_per_s=1000.0)
        result = eng.sweep_mines(
            "sweeper_1",
            area_m2=200000.0,
            mine_type=MineType.CONTACT,  # difficulty 1.0
            dt=60.0,
        )
        # 1000 * 1.0 * 60 = 60000
        assert result.area_cleared_m2 == pytest.approx(60000.0)


# ---------------------------------------------------------------------------
# Battery decay / persistence
# ---------------------------------------------------------------------------


class TestMinePersistence:
    """Battery decay disarms mines over time."""

    def test_battery_decay(self):
        eng = _make_engine()
        mines = eng.lay_mines(
            "l1", [Position(0, 0, -10)], MineType.MAGNETIC, count_per_pos=20,
        )
        initially_armed = sum(1 for m in mines if m.armed)
        assert initially_armed == 20
        # Exponential decay with rate 0.001/hr over 5000 hrs
        eng.update_mine_persistence(dt_hours=5000.0)
        still_armed = sum(1 for m in mines if m.armed)
        assert still_armed < initially_armed


# ---------------------------------------------------------------------------
# State roundtrip
# ---------------------------------------------------------------------------


class TestMineStateRoundtrip:
    """State persistence."""

    def test_state_roundtrip(self):
        eng = _make_engine(seed=55)
        eng.lay_mines("l1", [Position(10, 20, -5)], MineType.CONTACT, count_per_pos=3)
        state = eng.get_state()

        eng2 = _make_engine(seed=1)
        eng2.set_state(state)
        # Verify RNG state restored
        assert eng._rng.random() == eng2._rng.random()
        # Verify mine count restored
        assert len(eng2._mines) == 3
