"""Phase 70a: Vectorized nearest-enemy and movement-target tests.

Verifies that the vectorized numpy paths produce identical results
to the original scalar Python loops.
"""

from __future__ import annotations

import numpy as np
import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.simulation.battle import (
    _movement_target,
    _nearest_enemy_dist,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeUnit:
    """Minimal unit stub for distance calculations."""

    def __init__(self, easting: float, northing: float) -> None:
        self.position = Position(easting, northing, 0.0)
        self.status = type("S", (), {"value": 1, "name": "ACTIVE"})()


def _make_enemies(n: int, rng: np.random.Generator) -> tuple[list[_FakeUnit], np.ndarray]:
    """Generate *n* random enemies and the corresponding position array."""
    positions = rng.uniform(-10_000, 10_000, size=(n, 2))
    enemies = [_FakeUnit(float(positions[i, 0]), float(positions[i, 1])) for i in range(n)]
    return enemies, positions.astype(np.float64)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestNearestEnemyDist:
    """_nearest_enemy_dist vectorized vs scalar parity."""

    def test_vectorized_matches_scalar_100(self) -> None:
        """100 random positions: vectorized == scalar."""
        rng = np.random.Generator(np.random.PCG64(42))
        enemies, arr = _make_enemies(50, rng)

        for _ in range(100):
            pos = Position(
                float(rng.uniform(-10_000, 10_000)),
                float(rng.uniform(-10_000, 10_000)),
                0.0,
            )
            scalar = _nearest_enemy_dist(pos, enemies)
            vectorized = _nearest_enemy_dist(pos, enemies, enemy_pos_arr=arr)
            assert abs(scalar - vectorized) < 1e-6, (
                f"scalar={scalar}, vectorized={vectorized}"
            )

    def test_empty_array_returns_inf(self) -> None:
        """Empty enemy_pos_arr → float('inf')."""
        pos = Position(0.0, 0.0, 0.0)
        empty = np.empty((0, 2), dtype=np.float64)
        result = _nearest_enemy_dist(pos, [], enemy_pos_arr=empty)
        assert result == float("inf")

    def test_single_enemy(self) -> None:
        """Single enemy: both paths agree."""
        pos = Position(0.0, 0.0, 0.0)
        enemy = _FakeUnit(3.0, 4.0)
        arr = np.array([[3.0, 4.0]], dtype=np.float64)
        scalar = _nearest_enemy_dist(pos, [enemy])
        vectorized = _nearest_enemy_dist(pos, [enemy], enemy_pos_arr=arr)
        assert abs(scalar - 5.0) < 1e-6
        assert abs(vectorized - 5.0) < 1e-6


class TestMovementTarget:
    """_movement_target vectorized vs scalar parity."""

    def test_vectorized_matches_scalar_100(self) -> None:
        """100 random positions: vectorized == scalar."""
        rng = np.random.Generator(np.random.PCG64(99))
        enemies, arr = _make_enemies(30, rng)

        for _ in range(100):
            pos = Position(
                float(rng.uniform(-10_000, 10_000)),
                float(rng.uniform(-10_000, 10_000)),
                0.0,
            )
            sx, sy = _movement_target(pos, enemies)
            vx, vy = _movement_target(pos, enemies, enemy_pos_arr=arr)
            assert abs(sx - vx) < 1e-6, f"x: scalar={sx}, vectorized={vx}"
            assert abs(sy - vy) < 1e-6, f"y: scalar={sy}, vectorized={vy}"

    def test_weight_1_is_centroid(self) -> None:
        """centroid_weight=1.0 → pure centroid."""
        enemies = [_FakeUnit(0.0, 0.0), _FakeUnit(100.0, 0.0)]
        arr = np.array([[0.0, 0.0], [100.0, 0.0]], dtype=np.float64)
        pos = Position(200.0, 0.0, 0.0)
        vx, vy = _movement_target(pos, enemies, centroid_weight=1.0, enemy_pos_arr=arr)
        assert abs(vx - 50.0) < 1e-6  # centroid at (50, 0)
        assert abs(vy - 0.0) < 1e-6

    def test_weight_0_is_nearest(self) -> None:
        """centroid_weight=0.0 → nearest enemy."""
        enemies = [_FakeUnit(0.0, 0.0), _FakeUnit(100.0, 0.0)]
        arr = np.array([[0.0, 0.0], [100.0, 0.0]], dtype=np.float64)
        pos = Position(90.0, 0.0, 0.0)
        vx, vy = _movement_target(pos, enemies, centroid_weight=0.0, enemy_pos_arr=arr)
        # Nearest enemy is at (100, 0)
        assert abs(vx - 100.0) < 1e-6
        assert abs(vy - 0.0) < 1e-6

    def test_single_enemy_both_paths(self) -> None:
        """Single enemy: centroid == nearest → both weights produce same point."""
        pos = Position(0.0, 0.0, 0.0)
        enemy = _FakeUnit(100.0, 200.0)
        arr = np.array([[100.0, 200.0]], dtype=np.float64)
        sx, sy = _movement_target(pos, [enemy])
        vx, vy = _movement_target(pos, [enemy], enemy_pos_arr=arr)
        assert abs(sx - vx) < 1e-6
        assert abs(sy - vy) < 1e-6
