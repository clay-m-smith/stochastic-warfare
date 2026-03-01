"""Tests for terrain.bathymetry — underwater depth data layer."""

from __future__ import annotations

import numpy as np
import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.terrain.bathymetry import (
    Bathymetry,
    BathymetryConfig,
    BottomType,
    NavigationHazard,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CONFIG = BathymetryConfig(origin_easting=0.0, origin_northing=0.0, cell_size=100.0)


def _continental_shelf(rows: int = 10, cols: int = 10) -> Bathymetry:
    """Depth increases linearly eastward (simulates a shelf gradient)."""
    data = np.zeros((rows, cols), dtype=np.float64)
    bottom = np.full((rows, cols), BottomType.SAND, dtype=np.int32)
    for c in range(cols):
        data[:, c] = 10.0 * c  # 0, 10, 20, ... 90m
    # Column 0 is land (depth=0)
    return Bathymetry(data, bottom, _CONFIG)


def _uniform_sea(depth: float = 50.0) -> Bathymetry:
    data = np.full((10, 10), depth, dtype=np.float64)
    bottom = np.full((10, 10), BottomType.MUD, dtype=np.int32)
    return Bathymetry(data, bottom, _CONFIG)


def _with_hazard() -> Bathymetry:
    bath = _uniform_sea(depth=30.0)
    hazard = NavigationHazard(
        hazard_id="reef_01",
        hazard_type="reef",
        position=(500.0, 500.0),
        minimum_depth=3.0,
        radius=50.0,
    )
    return Bathymetry(bath._depth, bath._bottom, _CONFIG, [hazard])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDepthQueries:
    def test_shelf_gradient(self) -> None:
        bath = _continental_shelf()
        # Column 0 should be land (depth 0), column 5 should be ~50m
        d0 = bath.depth_at(Position(50.0, 50.0))  # cell (0,0)
        d5 = bath.depth_at(Position(550.0, 50.0))  # cell (0,5)
        assert d0 == pytest.approx(0.0, abs=0.5)
        assert d5 == pytest.approx(50.0, abs=1.0)

    def test_uniform_depth(self) -> None:
        bath = _uniform_sea(depth=100.0)
        assert bath.depth_at(Position(500.0, 500.0)) == pytest.approx(100.0)

    def test_land_returns_zero(self) -> None:
        bath = _continental_shelf()
        assert bath.depth_at(Position(50.0, 50.0)) == pytest.approx(0.0, abs=0.5)


class TestBottomType:
    def test_sand_bottom(self) -> None:
        bath = _continental_shelf()
        assert bath.bottom_type_at(Position(500.0, 500.0)) == BottomType.SAND

    def test_mud_bottom(self) -> None:
        bath = _uniform_sea()
        assert bath.bottom_type_at(Position(500.0, 500.0)) == BottomType.MUD


class TestNavigability:
    def test_deep_water_navigable(self) -> None:
        bath = _uniform_sea(depth=50.0)
        assert bath.is_navigable(Position(500.0, 500.0), draft=10.0)

    def test_shallow_water_not_navigable(self) -> None:
        bath = _uniform_sea(depth=5.0)
        assert not bath.is_navigable(Position(500.0, 500.0), draft=10.0)

    def test_land_not_navigable(self) -> None:
        bath = _continental_shelf()
        assert not bath.is_navigable(Position(50.0, 50.0), draft=3.0)

    def test_hazard_blocks_navigation(self) -> None:
        bath = _with_hazard()
        # At hazard center, depth=30m but hazard min_depth=3m
        assert not bath.is_navigable(Position(500.0, 500.0), draft=5.0)

    def test_away_from_hazard_navigable(self) -> None:
        bath = _with_hazard()
        # Far from the hazard
        assert bath.is_navigable(Position(50.0, 50.0), draft=5.0)

    def test_draft_less_than_hazard_depth_navigable(self) -> None:
        bath = _with_hazard()
        # Draft 2m < hazard min_depth 3m → navigable even at hazard
        assert bath.is_navigable(Position(500.0, 500.0), draft=2.0)


class TestHazardQueries:
    def test_hazards_near(self) -> None:
        bath = _with_hazard()
        nearby = bath.hazards_near(Position(510.0, 510.0), radius=100.0)
        assert len(nearby) == 1
        assert nearby[0].hazard_id == "reef_01"

    def test_no_hazards_far(self) -> None:
        bath = _with_hazard()
        assert len(bath.hazards_near(Position(50.0, 50.0), radius=50.0)) == 0


class TestBounds:
    def test_in_bounds(self) -> None:
        bath = _uniform_sea()
        assert bath.in_bounds(Position(500.0, 500.0))
        assert not bath.in_bounds(Position(-10.0, 500.0))

    def test_shape(self) -> None:
        bath = _uniform_sea()
        assert bath.shape == (10, 10)

    def test_cell_size(self) -> None:
        bath = _uniform_sea()
        assert bath.cell_size == 100.0


class TestStateRoundTrip:
    def test_get_set_state(self) -> None:
        bath1 = _with_hazard()
        state = bath1.get_state()

        bath2 = _uniform_sea()
        bath2.set_state(state)

        pos = Position(500.0, 500.0)
        assert bath2.depth_at(pos) == pytest.approx(bath1.depth_at(pos))
        assert len(bath2._hazards) == 1
        assert bath2._hazards[0].hazard_id == "reef_01"


class TestValidation:
    def test_1d_raises(self) -> None:
        with pytest.raises(ValueError, match="2-D"):
            Bathymetry(np.zeros(10), np.zeros(10, dtype=np.int32), _CONFIG)

    def test_shape_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="same shape"):
            Bathymetry(np.zeros((3, 3)), np.zeros((4, 4), dtype=np.int32), _CONFIG)
