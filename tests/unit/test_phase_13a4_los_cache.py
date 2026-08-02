"""Phase 13a-4: Multi-tick LOS cache with selective invalidation."""

import numpy as np

from stochastic_warfare.core.types import Position
from stochastic_warfare.terrain.heightmap import Heightmap, HeightmapConfig
from stochastic_warfare.terrain.los import LOSEngine


def _make_los(rows: int = 20, cols: int = 20, cell_size: float = 100.0) -> LOSEngine:
    cfg = HeightmapConfig(cell_size=cell_size, origin_easting=0.0, origin_northing=0.0)
    data = np.zeros((rows, cols), dtype=np.float64)
    hm = Heightmap(data, cfg)
    return LOSEngine(hm)


class TestSelectiveLOSInvalidation:
    def test_public_identity_matches_same_cell_engine_cache(self):
        los = _make_los()
        observer_a = Position(510, 510)
        observer_b = Position(590, 590)
        target_a = Position(1510, 510)
        target_b = Position(1590, 590)

        observer_cell = los.cache_cell(observer_a)
        target_cell = los.cache_cell(target_a)
        assert observer_cell == los.cache_cell(observer_b)
        assert target_cell == los.cache_cell(target_b)
        assert los.cache_key(observer_cell, target_cell) == los.cache_key(
            los.cache_cell(observer_b),
            los.cache_cell(target_b),
        )

        first = los.check_los(observer_a, target_a)
        same_identity = los.check_los(observer_b, target_b)
        assert same_identity is first
        assert los.los_cache_size == 1

    def test_public_identity_preserves_direction_and_height(self):
        los = _make_los()
        observer = Position(500, 500)
        target = Position(1500, 500)
        observer_cell = los.cache_cell(observer)
        target_cell = los.cache_cell(target)

        forward = los.cache_key(observer_cell, target_cell, 1.8, 0.0)
        reverse = los.cache_key(target_cell, observer_cell, 1.8, 0.0)
        higher_observer = los.cache_key(
            observer_cell,
            target_cell,
            2.0,
            0.0,
        )
        assert forward != reverse
        assert forward != higher_observer

        forward_result = los.check_los(observer, target, 1.8, 0.0)
        reverse_result = los.check_los(target, observer, 1.8, 0.0)
        assert forward_result.visible
        assert reverse_result.visible
        assert los.los_cache_size == 2

    def test_invalidate_empty_dirty_set(self):
        los = _make_los()
        obs = Position(500, 500)
        tgt = Position(1500, 500)
        los.check_los(obs, tgt)
        assert los.los_cache_size == 1
        los.invalidate_cells(set())
        assert los.los_cache_size == 1

    def test_invalidate_removes_observer_cell(self):
        los = _make_los()
        obs = Position(500, 500)
        tgt = Position(1500, 500)
        los.check_los(obs, tgt)
        assert los.los_cache_size == 1
        obs_cell = los._hm.enu_to_grid(obs)
        los.invalidate_cells({obs_cell})
        assert los.los_cache_size == 0

    def test_invalidate_removes_target_cell(self):
        los = _make_los()
        obs = Position(500, 500)
        tgt = Position(1500, 500)
        los.check_los(obs, tgt)
        tgt_cell = los._hm.enu_to_grid(tgt)
        los.invalidate_cells({tgt_cell})
        assert los.los_cache_size == 0

    def test_invalidate_keeps_unaffected_entries(self):
        los = _make_los()
        obs1 = Position(500, 500)
        tgt1 = Position(1500, 500)
        obs2 = Position(500, 1500)
        tgt2 = Position(1500, 1500)
        los.check_los(obs1, tgt1)
        los.check_los(obs2, tgt2)
        assert los.los_cache_size == 2
        # Only invalidate cells for first pair
        obs1_cell = los._hm.enu_to_grid(obs1)
        los.invalidate_cells({obs1_cell})
        assert los.los_cache_size == 1

    def test_clear_still_works(self):
        los = _make_los()
        los.check_los(Position(500, 500), Position(1500, 500))
        los.check_los(Position(500, 1500), Position(1500, 1500))
        assert los.los_cache_size == 2
        los.clear_los_cache()
        assert los.los_cache_size == 0

    def test_invalidate_on_empty_cache(self):
        los = _make_los()
        los.invalidate_cells({(5, 5)})
        assert los.los_cache_size == 0

    def test_dirty_cell_symmetric_difference(self):
        """Simulate pre/post move dirty cells."""
        los = _make_los()
        obs = Position(500, 500)
        tgt = Position(1500, 500)
        los.check_los(obs, tgt)

        # Simulate unit moving from (500,500) to (600,500)
        pre_cell = los._hm.enu_to_grid(Position(500, 500))
        post_cell = los._hm.enu_to_grid(Position(600, 500))
        dirty = {pre_cell, post_cell}
        los.invalidate_cells(dirty)
        assert los.los_cache_size == 0

    def test_cache_retained_across_ticks_for_stationary(self):
        """Cache entries for stationary units should survive invalidation."""
        los = _make_los()
        stationary_obs = Position(500, 500)
        stationary_tgt = Position(1500, 500)
        los.check_los(stationary_obs, stationary_tgt)

        # A different unit moves
        moving_cell = los._hm.enu_to_grid(Position(500, 1500))
        new_cell = los._hm.enu_to_grid(Position(600, 1500))
        los.invalidate_cells({moving_cell, new_cell})

        # Stationary pair should still be cached
        assert los.los_cache_size == 1

    def test_invalidation_result_consistency(self):
        """After invalidation, re-check should produce same result."""
        los = _make_los()
        obs = Position(500, 500)
        tgt = Position(1500, 500)
        result1 = los.check_los(obs, tgt)
        obs_cell = los._hm.enu_to_grid(obs)
        los.invalidate_cells({obs_cell})
        result2 = los.check_los(obs, tgt)
        assert result1.visible == result2.visible

    def test_multiple_entries_same_observer(self):
        """Multiple targets from same observer — invalidating observer clears all."""
        los = _make_los()
        obs = Position(500, 500)
        for i in range(5):
            los.check_los(obs, Position(1500, 500 + i * 200))
        assert los.los_cache_size == 5
        obs_cell = los._hm.enu_to_grid(obs)
        los.invalidate_cells({obs_cell})
        assert los.los_cache_size == 0

    def test_selective_vs_full_clear_correctness(self):
        """Selective invalidation + re-query matches full clear + re-query."""
        los1 = _make_los()
        los2 = _make_los()
        obs = Position(500, 500)
        targets = [Position(1500, 200 + i * 200) for i in range(5)]

        for t in targets:
            los1.check_los(obs, t)
            los2.check_los(obs, t)

        # Selective invalidation on los1
        obs_cell = los1._hm.enu_to_grid(obs)
        los1.invalidate_cells({obs_cell})
        # Full clear on los2
        los2.clear_los_cache()

        # Re-query should match
        for t in targets:
            r1 = los1.check_los(obs, t)
            r2 = los2.check_los(obs, t)
            assert r1.visible == r2.visible
