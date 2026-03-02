"""Tests for movement/airborne.py."""

import numpy as np
import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.movement.airborne import (
    AirborneMethod,
    AirborneMovementEngine,
)


class TestAirborneMethod:
    def test_values(self) -> None:
        assert AirborneMethod.STATIC_LINE == 0
        assert AirborneMethod.RAPPEL == 5

    def test_count(self) -> None:
        assert len(AirborneMethod) == 6


class TestDropScatter:
    def test_correct_count(self) -> None:
        rng = np.random.Generator(np.random.PCG64(42))
        engine = AirborneMovementEngine(rng=rng)
        positions = engine.compute_drop_scatter(
            Position(0.0, 0.0), 5.0, 300.0, AirborneMethod.STATIC_LINE, 10,
        )
        assert len(positions) == 10

    def test_deterministic(self) -> None:
        rng1 = np.random.Generator(np.random.PCG64(42))
        rng2 = np.random.Generator(np.random.PCG64(42))
        e1 = AirborneMovementEngine(rng=rng1)
        e2 = AirborneMovementEngine(rng=rng2)
        p1 = e1.compute_drop_scatter(
            Position(0.0, 0.0), 5.0, 300.0, AirborneMethod.STATIC_LINE, 5,
        )
        p2 = e2.compute_drop_scatter(
            Position(0.0, 0.0), 5.0, 300.0, AirborneMethod.STATIC_LINE, 5,
        )
        for a, b in zip(p1, p2):
            assert a == b

    def test_wind_increases_scatter(self) -> None:
        rng1 = np.random.Generator(np.random.PCG64(42))
        rng2 = np.random.Generator(np.random.PCG64(42))
        e1 = AirborneMovementEngine(rng=rng1)
        e2 = AirborneMovementEngine(rng=rng2)
        p_calm = e1.compute_drop_scatter(
            Position(0.0, 0.0), 0.0, 300.0, AirborneMethod.STATIC_LINE, 20,
        )
        p_windy = e2.compute_drop_scatter(
            Position(0.0, 0.0), 20.0, 300.0, AirborneMethod.STATIC_LINE, 20,
        )
        # Mean distance from center
        def mean_dist(positions):
            return sum(
                (p.easting ** 2 + p.northing ** 2) ** 0.5 for p in positions
            ) / len(positions)

        assert mean_dist(p_windy) > mean_dist(p_calm)

    def test_halo_tighter_than_static_line(self) -> None:
        rng1 = np.random.Generator(np.random.PCG64(42))
        rng2 = np.random.Generator(np.random.PCG64(42))
        e1 = AirborneMovementEngine(rng=rng1)
        e2 = AirborneMovementEngine(rng=rng2)
        p_static = e1.compute_drop_scatter(
            Position(0.0, 0.0), 5.0, 300.0, AirborneMethod.STATIC_LINE, 20,
        )
        p_halo = e2.compute_drop_scatter(
            Position(0.0, 0.0), 5.0, 300.0, AirborneMethod.HALO, 20,
        )

        def mean_dist(positions):
            return sum(
                (p.easting ** 2 + p.northing ** 2) ** 0.5 for p in positions
            ) / len(positions)

        assert mean_dist(p_halo) < mean_dist(p_static)

    def test_no_rng_centered(self) -> None:
        engine = AirborneMovementEngine()
        center = Position(100.0, 200.0)
        positions = engine.compute_drop_scatter(
            center, 5.0, 300.0, AirborneMethod.STATIC_LINE, 3,
        )
        for p in positions:
            assert p.easting == 100.0
            assert p.northing == 200.0


class TestAssessDZ:
    def test_without_terrain(self) -> None:
        engine = AirborneMovementEngine()
        result = engine.assess_dz(Position(0.0, 0.0), 500.0)
        assert "suitability" in result
        assert result["suitability"] == 1.0

    def test_radius_reported(self) -> None:
        engine = AirborneMovementEngine()
        result = engine.assess_dz(Position(0.0, 0.0), 750.0)
        assert result["radius"] == 750.0


class TestAssemblyTime:
    def test_empty(self) -> None:
        engine = AirborneMovementEngine()
        assert engine.assembly_time([], Position(0.0, 0.0)) == 0.0

    def test_at_center(self) -> None:
        engine = AirborneMovementEngine()
        positions = [Position(0.0, 0.0), Position(0.0, 0.0)]
        t = engine.assembly_time(positions, Position(0.0, 0.0))
        assert t == 0.0

    def test_scattered(self) -> None:
        engine = AirborneMovementEngine()
        positions = [Position(100.0, 0.0), Position(-100.0, 0.0)]
        t = engine.assembly_time(positions, Position(0.0, 0.0))
        assert t > 0
        # ~100m mean distance / 1 m/s * 1.5 = ~150s
        assert t == pytest.approx(150.0)


class TestHelicopterInsertion:
    def test_basic(self) -> None:
        engine = AirborneMovementEngine()
        result = engine.helicopter_insertion(Position(0.0, 0.0), 4)
        assert result["time_to_offload"] == 480.0  # 4 * 120s
        assert result["num_aircraft"] == 4
        assert "risk" in result
        assert "suitability" in result
