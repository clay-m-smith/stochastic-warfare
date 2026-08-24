"""Phase 13b-3: Numba JIT for DDA raycasting tests."""

import math

import numpy as np
import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.terrain.heightmap import Heightmap, HeightmapConfig
from stochastic_warfare.terrain.los import LOSEngine, _los_terrain_kernel


def _make_los(rows=20, cols=20, cell_size=100.0, data=None):
    cfg = HeightmapConfig(cell_size=cell_size, origin_easting=0.0, origin_northing=0.0)
    if data is None:
        data = np.zeros((rows, cols), dtype=np.float64)
    hm = Heightmap(data, cfg)
    return LOSEngine(hm)


class TestLOSTerrainKernel:
    def test_kernel_flat_terrain_visible(self):
        """Flat terrain should not block LOS."""
        data = np.zeros((20, 20), dtype=np.float64)
        blocked, clearance = _los_terrain_kernel(
            500.0, 500.0,  # observer
            2.0, 0.0,      # obs_elev, tgt_elev
            1000.0, 0.0,   # dx, dy
            1000.0, 20,    # total_dist, num_steps
            4.0/3.0, 6_371_000.0,  # k_factor, r_earth
            data,
            0.0, 0.0, 100.0,  # origin_e, origin_n, cell_size
        )
        assert blocked == -1

    def test_kernel_blocked_by_ridge(self):
        """A tall ridge should block LOS."""
        data = np.zeros((20, 20), dtype=np.float64)
        data[:, 10] = 500.0  # wall at col 10
        blocked, clearance = _los_terrain_kernel(
            250.0, 1000.0,  # observer at col ~2
            2.0, 0.0,
            1500.0, 0.0,   # target at col 17
            1500.0, 30,
            4.0/3.0, 6_371_000.0,
            data,
            0.0, 0.0, 100.0,
        )
        assert blocked > 0

    def test_kernel_out_of_bounds_skipped(self):
        """Ray samples outside grid bounds should be skipped, not crash."""
        data = np.zeros((10, 10), dtype=np.float64)
        blocked, clearance = _los_terrain_kernel(
            500.0, 500.0,
            2.0, 0.0,
            5000.0, 0.0,  # target far beyond grid
            5000.0, 100,
            4.0/3.0, 6_371_000.0,
            data,
            0.0, 0.0, 100.0,
        )
        assert blocked == -1

    def test_kernel_returns_min_clearance(self):
        """Kernel should track minimum clearance."""
        data = np.zeros((20, 20), dtype=np.float64)
        data[:, 10] = 0.5  # small bump at col 10
        blocked, clearance = _los_terrain_kernel(
            250.0, 1000.0,
            2.0, 2.0,       # observer and target at same elevation
            1500.0, 0.0,
            1500.0, 30,
            4.0/3.0, 6_371_000.0,
            data,
            0.0, 0.0, 100.0,
        )
        assert blocked == -1  # not tall enough to block
        assert clearance < 2.0  # but clearance should be less than observer height


class TestLOSTerrainJitMethod:
    def test_jit_matches_vectorized(self):
        """JIT terrain check should match vectorized result."""
        los = _make_los(20, 20, 100.0)
        obs = Position(500.0, 500.0)
        tgt = Position(1500.0, 500.0)
        obs_elev = los._hm.elevation_at(obs) + 2.0
        tgt_elev = los._hm.elevation_at(tgt)
        dx = tgt.easting - obs.easting
        dy = tgt.northing - obs.northing
        total_dist = math.sqrt(dx * dx + dy * dy)
        num_steps = max(2, int(total_dist / (los._hm.cell_size / 2.0)))

        vec_result = los._check_los_vectorized(
            obs, obs_elev, tgt_elev, dx, dy, total_dist,
            num_steps, 4.0/3.0, 6_371_000.0,
        )
        jit_result = los._check_los_terrain_jit(
            obs, obs_elev, tgt_elev, dx, dy, total_dist,
            num_steps, 4.0/3.0, 6_371_000.0,
        )
        assert vec_result.visible == jit_result.visible

    def test_jit_blocked_terrain(self):
        """JIT method should detect terrain blockage."""
        data = np.zeros((20, 20), dtype=np.float64)
        data[:, 10] = 500.0
        los = _make_los(20, 20, 100.0, data=data)
        obs = Position(250.0, 1000.0)
        tgt = Position(1750.0, 1000.0)
        obs_elev = los._hm.elevation_at(obs) + 2.0
        tgt_elev = los._hm.elevation_at(tgt)
        dx = tgt.easting - obs.easting
        dy = tgt.northing - obs.northing
        total_dist = math.sqrt(dx * dx + dy * dy)
        num_steps = max(2, int(total_dist / (los._hm.cell_size / 2.0)))

        result = los._check_los_terrain_jit(
            obs, obs_elev, tgt_elev, dx, dy, total_dist,
            num_steps, 4.0/3.0, 6_371_000.0,
        )
        assert not result.visible
        assert result.blocked_by == "terrain"

    def test_jit_flat_terrain_visible(self):
        """JIT method should report visible on flat terrain."""
        los = _make_los(20, 20, 100.0)
        obs = Position(500.0, 500.0)
        tgt = Position(1500.0, 500.0)
        obs_elev = los._hm.elevation_at(obs) + 2.0
        tgt_elev = los._hm.elevation_at(tgt)
        dx = tgt.easting - obs.easting
        dy = tgt.northing - obs.northing
        total_dist = math.sqrt(dx * dx + dy * dy)
        num_steps = max(2, int(total_dist / (los._hm.cell_size / 2.0)))

        result = los._check_los_terrain_jit(
            obs, obs_elev, tgt_elev, dx, dy, total_dist,
            num_steps, 4.0/3.0, 6_371_000.0,
        )
        assert result.visible

    def test_jit_multiple_checks_deterministic(self):
        """Multiple JIT LOS checks should be deterministic."""
        los = _make_los(20, 20, 100.0)
        obs = Position(500.0, 500.0)
        tgt = Position(1500.0, 1500.0)
        obs_elev = los._hm.elevation_at(obs) + 2.0
        tgt_elev = los._hm.elevation_at(tgt)
        dx = tgt.easting - obs.easting
        dy = tgt.northing - obs.northing
        total_dist = math.sqrt(dx * dx + dy * dy)
        num_steps = max(2, int(total_dist / (los._hm.cell_size / 2.0)))

        r1 = los._check_los_terrain_jit(
            obs, obs_elev, tgt_elev, dx, dy, total_dist,
            num_steps, 4.0/3.0, 6_371_000.0,
        )
        r2 = los._check_los_terrain_jit(
            obs, obs_elev, tgt_elev, dx, dy, total_dist,
            num_steps, 4.0/3.0, 6_371_000.0,
        )
        assert r1.visible == r2.visible
        assert r1.grazing_distance == pytest.approx(r2.grazing_distance, abs=0.01)
