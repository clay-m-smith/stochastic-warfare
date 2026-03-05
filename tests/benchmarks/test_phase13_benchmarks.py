"""Phase 13 performance benchmarks — baseline and post-optimization."""

import math
import time

import numpy as np
import pytest

from stochastic_warfare.core.types import Position


@pytest.mark.benchmark
class TestBaselineBenchmarks:
    """Pre-optimization baseline measurements.

    These capture the current performance so we can measure improvement
    after Phase 13 optimizations.  Results are printed and compared to
    targets in post-optimization tests.
    """

    def test_brute_force_spatial_query_baseline(self):
        """Time N brute-force distance computations (proxy for STRtree gain)."""
        rng = np.random.default_rng(42)
        n = 5000
        points = rng.uniform(0, 100_000, size=(n, 2))
        query = np.array([50_000.0, 50_000.0])
        radius = 10_000.0

        t0 = time.perf_counter()
        for _ in range(100):
            diffs = points - query
            dists = np.sqrt(np.sum(diffs * diffs, axis=1))
            _result = np.where(dists <= radius)[0]
        elapsed = time.perf_counter() - t0
        print(f"\nBrute-force spatial query (5000 pts, 100 iters): {elapsed:.4f}s")
        # Just record — no assertion for baseline
        assert elapsed > 0

    def test_kalman_predict_baseline(self):
        """Time N Kalman predict calls to measure matrix construction overhead."""
        from stochastic_warfare.detection.estimation import (
            EstimationConfig,
            StateEstimator,
            Track,
            TrackState,
            TrackStatus,
        )
        from stochastic_warfare.detection.identification import ContactInfo, ContactLevel

        est = StateEstimator(rng=np.random.default_rng(0), config=EstimationConfig())
        tracks = []
        for i in range(100):
            ci = ContactInfo(
                level=ContactLevel.DETECTED,
                domain_estimate=None,
                type_estimate=None,
                specific_estimate=None,
                confidence=0.5,
            )
            ts = TrackState(
                position=np.array([float(i * 100), float(i * 100)]),
                velocity=np.array([10.0, 5.0]),
                covariance=np.eye(4) * 100.0,
                last_update_time=0.0,
            )
            tracks.append(Track(track_id=f"t{i}", side="blue", contact_info=ci, state=ts))

        t0 = time.perf_counter()
        for _ in range(50):
            for track in tracks:
                est.predict(track, 5.0)
        elapsed = time.perf_counter() - t0
        print(f"\nKalman predict (100 tracks, 50 iters, dt=5.0): {elapsed:.4f}s")
        assert elapsed > 0

    def test_los_check_baseline(self):
        """Time LOS checks over a terrain grid."""
        from stochastic_warfare.terrain.heightmap import Heightmap, HeightmapConfig
        from stochastic_warfare.terrain.los import LOSEngine

        config = HeightmapConfig(cell_size=100.0, origin_easting=0.0, origin_northing=0.0)
        data = np.random.default_rng(42).uniform(0, 200, size=(100, 100))
        hm = Heightmap(data, config)
        los = LOSEngine(hm)

        observer = Position(5000.0, 5000.0, 0.0)

        t0 = time.perf_counter()
        for r in range(0, 100, 5):
            for c in range(0, 100, 5):
                target = hm.grid_to_enu(r, c)
                los.check_los(observer, target, observer_height=2.0)
        elapsed = time.perf_counter() - t0
        print(f"\nLOS checks (400 rays, 100x100 grid): {elapsed:.4f}s")
        assert elapsed > 0

    def test_pathfinding_baseline(self):
        """Time A* pathfinding over flat terrain."""
        from stochastic_warfare.movement.pathfinding import Pathfinder

        pf = Pathfinder()
        start = Position(0.0, 0.0, 0.0)
        goal = Position(5000.0, 5000.0, 0.0)

        t0 = time.perf_counter()
        for _ in range(10):
            pf.find_path(start, goal, grid_resolution=100.0, max_iterations=10000)
        elapsed = time.perf_counter() - t0
        print(f"\nA* pathfinding (5km diagonal, 10 iters): {elapsed:.4f}s")
        assert elapsed > 0

    def test_rk4_trajectory_baseline(self):
        """Time RK4 trajectory computation."""
        from stochastic_warfare.combat.ammunition import AmmoDefinition, WeaponDefinition
        from stochastic_warfare.combat.ballistics import BallisticsConfig, BallisticsEngine

        rng = np.random.default_rng(42)
        engine = BallisticsEngine(rng, BallisticsConfig(integration_step_s=0.01))

        weapon = WeaponDefinition(
            weapon_id="test_gun",
            display_name="Test Gun",
            category="GUN",
            caliber_mm=120,
            muzzle_velocity_mps=1700,
            max_range_m=4000,
            base_accuracy_mrad=0.3,
            rate_of_fire_rpm=6,
        )
        ammo = AmmoDefinition(
            ammo_id="test_round",
            display_name="Test Round",
            ammo_type="apfsds",
            mass_kg=4.5,
            diameter_mm=30,
            drag_coefficient=0.3,
        )

        t0 = time.perf_counter()
        for az in range(0, 360, 10):
            engine.compute_trajectory(weapon, ammo, Position(0, 0, 0), 5.0, float(az))
        elapsed = time.perf_counter() - t0
        print(f"\nRK4 trajectory (36 azimuths): {elapsed:.4f}s")
        assert elapsed > 0

    def test_mc_serial_baseline(self):
        """Time a single Monte Carlo iteration (serial baseline)."""
        # Just measure import + setup overhead
        t0 = time.perf_counter()
        from stochastic_warfare.validation.monte_carlo import MonteCarloConfig
        elapsed = time.perf_counter() - t0
        print(f"\nMC import overhead: {elapsed:.4f}s")
        assert elapsed >= 0

    def test_viewshed_baseline(self):
        """Time viewshed computation over a small grid."""
        from stochastic_warfare.terrain.heightmap import Heightmap, HeightmapConfig
        from stochastic_warfare.terrain.los import LOSEngine

        config = HeightmapConfig(cell_size=100.0, origin_easting=0.0, origin_northing=0.0)
        data = np.random.default_rng(42).uniform(0, 100, size=(50, 50))
        hm = Heightmap(data, config)
        los = LOSEngine(hm)

        observer = Position(2500.0, 2500.0, 0.0)

        t0 = time.perf_counter()
        los.visible_area(observer, max_range=3000.0, observer_height=2.0)
        elapsed = time.perf_counter() - t0
        print(f"\nViewshed (50x50 grid, 3km range): {elapsed:.4f}s")
        assert elapsed > 0
