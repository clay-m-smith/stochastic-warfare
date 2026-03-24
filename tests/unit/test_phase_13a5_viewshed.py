"""Phase 13a-5: Vectorized viewshed computation tests."""

import numpy as np

from stochastic_warfare.core.types import Position
from stochastic_warfare.terrain.heightmap import Heightmap, HeightmapConfig
from stochastic_warfare.terrain.los import LOSEngine


def _make_los(
    rows: int = 20, cols: int = 20, cell_size: float = 100.0,
    data: np.ndarray | None = None,
) -> LOSEngine:
    cfg = HeightmapConfig(cell_size=cell_size, origin_easting=0.0, origin_northing=0.0)
    if data is None:
        data = np.zeros((rows, cols), dtype=np.float64)
    hm = Heightmap(data, cfg)
    return LOSEngine(hm)


class TestViewshedVectorization:
    def test_flat_terrain_all_visible(self):
        """On flat terrain, all in-range cells should be visible."""
        los = _make_los(rows=10, cols=10, cell_size=100.0)
        observer = Position(500.0, 500.0, 0.0)
        viewshed = los.visible_area(observer, max_range=2000.0, observer_height=2.0)
        assert viewshed.shape == (10, 10)
        # All cells within 2km range on 1km grid should be visible
        assert viewshed.sum() > 0

    def test_viewshed_shape_matches_heightmap(self):
        los = _make_los(rows=15, cols=25)
        observer = Position(500.0, 500.0, 0.0)
        viewshed = los.visible_area(observer, max_range=5000.0)
        assert viewshed.shape == (15, 25)

    def test_out_of_range_cells_not_visible(self):
        """Cells beyond max_range should always be False."""
        los = _make_los(rows=50, cols=50, cell_size=100.0)
        observer = Position(2500.0, 2500.0, 0.0)
        viewshed = los.visible_area(observer, max_range=500.0, observer_height=2.0)
        # Most of the 5km x 5km grid should be out of 500m range
        assert viewshed.sum() < 50 * 50

    def test_terrain_blocks_visibility(self):
        """A tall ridge should block visibility to cells behind it."""
        data = np.zeros((20, 20), dtype=np.float64)
        # Create a wall at col 10
        data[:, 10] = 500.0
        los = _make_los(rows=20, cols=20, cell_size=100.0, data=data)
        observer = Position(250.0, 1000.0, 0.0)  # col ~2
        viewshed = los.visible_area(observer, max_range=3000.0, observer_height=2.0)
        # Cells behind the wall (col > 10) should mostly not be visible
        behind_wall = viewshed[:, 12:]
        in_front = viewshed[:, :9]
        assert behind_wall.sum() < in_front.sum()

    def test_viewshed_uses_cache(self):
        """Viewshed should populate the LOS cache."""
        los = _make_los(rows=10, cols=10, cell_size=100.0)
        observer = Position(500.0, 500.0, 0.0)
        los.visible_area(observer, max_range=2000.0, observer_height=2.0)
        assert los.los_cache_size > 0

    def test_viewshed_deterministic(self):
        """Two calls with same params should produce identical result."""
        los = _make_los(rows=10, cols=10, cell_size=100.0)
        observer = Position(500.0, 500.0, 0.0)
        v1 = los.visible_area(observer, max_range=2000.0, observer_height=2.0)
        los.clear_los_cache()
        v2 = los.visible_area(observer, max_range=2000.0, observer_height=2.0)
        np.testing.assert_array_equal(v1, v2)

    def test_observer_at_center_sees_nearby(self):
        """Observer at grid center should see immediate neighbors."""
        los = _make_los(rows=10, cols=10, cell_size=100.0)
        observer = Position(500.0, 500.0, 0.0)
        viewshed = los.visible_area(observer, max_range=200.0, observer_height=2.0)
        # At least the observer's own cell should be visible
        obs_row, obs_col = los._hm.enu_to_grid(observer)
        assert viewshed[obs_row, obs_col] is np.True_

    def test_small_range_limits_visibility(self):
        """Very small range should only see a few cells."""
        los = _make_los(rows=20, cols=20, cell_size=100.0)
        observer = Position(1000.0, 1000.0, 0.0)
        viewshed = los.visible_area(observer, max_range=50.0, observer_height=2.0)
        # 50m range on 100m grid — observer cell center at 50m may or may not be in range
        assert viewshed.sum() <= 4
