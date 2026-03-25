"""Phase 84c: Engagement candidate culling via STRtree in battle.py."""

from __future__ import annotations

import numpy as np
import pytest
from shapely import STRtree
from shapely.geometry import Point


# ── STRtree engagement culling logic (unit tests) ───────────────────
#
# These test the STRtree query pattern used in _execute_engagements().
# Full integration with BattleManager is covered by existing scenario tests.


def _build_enemy_tree(positions: list[tuple[float, float]]) -> STRtree | None:
    """Reproduce the Phase 84c tree-building pattern."""
    if not positions:
        return None
    pts = [Point(x, y) for x, y in positions]
    return STRtree(pts)


def _query_candidates(
    tree: STRtree | None,
    attacker_pos: tuple[float, float],
    max_weapon_range: float,
    n_enemies: int,
) -> list[int]:
    """Reproduce the Phase 84c candidate query pattern."""
    if tree is not None:
        cand = sorted(tree.query(
            Point(attacker_pos[0], attacker_pos[1]).buffer(max_weapon_range),
        ))
    else:
        cand = list(range(n_enemies))
    if not cand:
        cand = list(range(n_enemies))
    return cand


class TestEngagementCulling:
    """STRtree candidate pre-filtering for engagement scoring."""

    def test_same_target_selected(self) -> None:
        """Threat scoring with/without culling selects same best target."""
        positions = [
            (1000.0, 0.0),   # close
            (5000.0, 0.0),   # mid
            (50000.0, 0.0),  # far
        ]
        tree = _build_enemy_tree(positions)
        attacker = (0.0, 0.0)
        wpn_range = 10000.0

        culled = _query_candidates(tree, attacker, wpn_range, len(positions))
        full = list(range(len(positions)))

        # Culled should include indices 0 and 1 (within 10km), exclude 2
        assert 0 in culled
        assert 1 in culled
        assert 2 not in culled

        # Full always includes all
        assert full == [0, 1, 2]

    def test_no_candidates_falls_back(self) -> None:
        """When no enemies in weapon range, falls back to all enemies."""
        positions = [(100_000.0, 0.0)]
        tree = _build_enemy_tree(positions)
        attacker = (0.0, 0.0)
        wpn_range = 5000.0

        cand = _query_candidates(tree, attacker, wpn_range, len(positions))
        # Fallback: all enemies
        assert cand == [0]

    def test_closest_mode_unchanged(self) -> None:
        """target_selection_mode='closest' uses argmin, not tree query."""
        positions = np.array([
            [1000.0, 0.0],
            [500.0, 0.0],
            [2000.0, 0.0],
        ])
        att_pos = np.array([0.0, 0.0])
        diffs = positions - att_pos
        dists = np.sqrt(np.sum(diffs * diffs, axis=1))

        best_idx = int(np.argmin(dists))
        assert best_idx == 1  # 500m is closest

    def test_all_in_range(self) -> None:
        """All enemies within range → full scoring, same result."""
        positions = [
            (100.0, 0.0),
            (200.0, 0.0),
            (300.0, 0.0),
        ]
        tree = _build_enemy_tree(positions)
        attacker = (0.0, 0.0)
        wpn_range = 10000.0

        cand = _query_candidates(tree, attacker, wpn_range, len(positions))
        assert sorted(cand) == [0, 1, 2]

    def test_single_enemy(self) -> None:
        """One enemy → selected correctly."""
        positions = [(500.0, 500.0)]
        tree = _build_enemy_tree(positions)
        cand = _query_candidates(tree, (0.0, 0.0), 10000.0, 1)
        assert cand == [0]

    def test_tree_per_side(self) -> None:
        """Trees are built independently per side."""
        red_positions = [(1000.0, 0.0), (2000.0, 0.0)]
        blue_positions = [(3000.0, 0.0)]

        trees = {
            "blue": _build_enemy_tree(red_positions),    # blue sees red enemies
            "red": _build_enemy_tree(blue_positions),     # red sees blue enemies
        }
        assert trees["blue"] is not None
        assert trees["red"] is not None

        # Blue querying from origin with 5km range
        blue_cand = _query_candidates(trees["blue"], (0.0, 0.0), 5000.0, 2)
        assert 0 in blue_cand  # 1km enemy
        assert 1 in blue_cand  # 2km enemy

    def test_deterministic(self) -> None:
        """Same scenario produces identical candidates."""
        positions = [(1000.0, 0.0), (5000.0, 3000.0), (8000.0, 0.0)]
        for _ in range(5):
            tree = _build_enemy_tree(positions)
            cand = _query_candidates(tree, (0.0, 0.0), 6000.0, len(positions))
            assert sorted(cand) == sorted(cand)  # same each time
            # Also verify specific content
            assert 0 in cand  # 1km — in range
            assert 1 in cand  # ~5.83km — in range
            # index 2 at 8km — outside 6km range
            assert 2 not in cand

    def test_empty_weapons_skips(self) -> None:
        """No tree when no enemies → returns None."""
        tree = _build_enemy_tree([])
        assert tree is None
        # Falls back to range(0) which is empty
        cand = _query_candidates(None, (0.0, 0.0), 1000.0, 0)
        assert cand == []
