"""Tests for movement/engine.py."""

import math

import numpy as np
import pytest

from stochastic_warfare.core.types import Domain, Position, Side
from stochastic_warfare.entities.base import Unit
from stochastic_warfare.movement.engine import MovementConfig, MovementEngine


def _make_unit(max_speed: float = 10.0, pos: Position = Position(0.0, 0.0)) -> Unit:
    return Unit(
        entity_id="u1", position=pos, max_speed=max_speed,
        domain=Domain.GROUND, side=Side.BLUE,
    )


class TestComputeSpeed:
    def test_flat_no_terrain(self) -> None:
        engine = MovementEngine()
        u = _make_unit(10.0)
        speed = engine.compute_speed(u, u.position, 0.0)
        assert speed == pytest.approx(10.0, abs=1.0)

    def test_zero_max_speed_uses_infantry(self) -> None:
        engine = MovementEngine()
        u = _make_unit(0.0)
        speed = engine.compute_speed(u, u.position, 0.0)
        assert speed == pytest.approx(1.3, abs=0.5)

    def test_deterministic_with_seed(self) -> None:
        rng1 = np.random.Generator(np.random.PCG64(42))
        rng2 = np.random.Generator(np.random.PCG64(42))
        e1 = MovementEngine(rng=rng1)
        e2 = MovementEngine(rng=rng2)
        u = _make_unit()
        s1 = e1.compute_speed(u, u.position, 0.0)
        s2 = e2.compute_speed(u, u.position, 0.0)
        assert s1 == s2

    def test_noise_creates_variation(self) -> None:
        rng = np.random.Generator(np.random.PCG64(42))
        engine = MovementEngine(rng=rng)
        u = _make_unit()
        speeds = [engine.compute_speed(u, u.position, 0.0) for _ in range(20)]
        assert min(speeds) != max(speeds)

    def test_no_noise_config(self) -> None:
        config = MovementConfig(noise_std=0.0)
        engine = MovementEngine(config=config)
        u = _make_unit()
        s1 = engine.compute_speed(u, u.position, 0.0)
        s2 = engine.compute_speed(u, u.position, 0.0)
        assert s1 == s2


class TestTerrainSpeedFactor:
    def test_no_terrain_returns_one(self) -> None:
        engine = MovementEngine()
        assert engine.terrain_speed_factor(Position(0.0, 0.0)) == 1.0


class TestSlopeSpeedFactor:
    def test_no_heightmap_returns_one(self) -> None:
        engine = MovementEngine()
        assert engine.slope_speed_factor(Position(0.0, 0.0), 0.0) == 1.0


class TestRoadSpeedFactor:
    def test_no_infrastructure_returns_one(self) -> None:
        engine = MovementEngine()
        assert engine.road_speed_factor(Position(0.0, 0.0)) == 1.0


class TestMoveUnit:
    def test_move_toward_target(self) -> None:
        config = MovementConfig(noise_std=0.0)
        engine = MovementEngine(config=config)
        u = _make_unit(10.0, Position(0.0, 0.0))
        target = Position(100.0, 0.0)
        result = engine.move_unit(u, target, 5.0)
        assert result.distance_moved > 0
        assert result.new_position.easting > 0
        assert result.new_position.easting <= 100.0

    def test_reaches_target_exactly(self) -> None:
        config = MovementConfig(noise_std=0.0)
        engine = MovementEngine(config=config)
        u = _make_unit(100.0, Position(0.0, 0.0))
        target = Position(50.0, 0.0)
        result = engine.move_unit(u, target, 10.0)
        assert result.new_position.easting == pytest.approx(50.0)
        assert result.distance_moved == pytest.approx(50.0)

    def test_already_at_target(self) -> None:
        engine = MovementEngine()
        u = _make_unit(10.0, Position(50.0, 50.0))
        result = engine.move_unit(u, Position(50.0, 50.0), 5.0)
        assert result.distance_moved == 0.0

    def test_diagonal_movement(self) -> None:
        config = MovementConfig(noise_std=0.0)
        engine = MovementEngine(config=config)
        u = _make_unit(10.0, Position(0.0, 0.0))
        target = Position(100.0, 100.0)
        result = engine.move_unit(u, target, 5.0)
        assert result.new_position.easting > 0
        assert result.new_position.northing > 0

    def test_fatigue_added(self) -> None:
        config = MovementConfig(noise_std=0.0)
        engine = MovementEngine(config=config)
        u = _make_unit(10.0)
        result = engine.move_unit(u, Position(1000.0, 0.0), 60.0)
        assert result.fatigue_added > 0

    def test_fuel_consumed_vehicle(self) -> None:
        config = MovementConfig(noise_std=0.0)
        engine = MovementEngine(config=config)
        u = _make_unit(15.0)
        result = engine.move_unit(u, Position(1000.0, 0.0), 60.0)
        assert result.fuel_consumed > 0

    def test_deterministic_movement(self) -> None:
        rng1 = np.random.Generator(np.random.PCG64(42))
        rng2 = np.random.Generator(np.random.PCG64(42))
        e1 = MovementEngine(rng=rng1)
        e2 = MovementEngine(rng=rng2)
        u = _make_unit(10.0)
        r1 = e1.move_unit(u, Position(500.0, 0.0), 10.0)
        r2 = e2.move_unit(u, Position(500.0, 0.0), 10.0)
        assert r1.new_position == r2.new_position
        assert r1.distance_moved == r2.distance_moved
