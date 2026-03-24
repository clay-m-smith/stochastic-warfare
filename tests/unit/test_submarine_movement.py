"""Tests for movement/submarine_movement.py."""

import math
from types import SimpleNamespace

import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.movement.submarine_movement import (
    SubDepthBand,
    SubmarineMovementEngine,
)


def _make_sub(
    max_speed: float = 17.0,
    depth: float = 150.0,
    max_depth: float = 450.0,
    noise_base: float = 95.0,
    fuel_capacity: float = 0.0,  # nuclear
    pos: Position = Position(0.0, 0.0),
) -> SimpleNamespace:
    return SimpleNamespace(
        entity_id="ssn1",
        position=pos,
        max_speed=max_speed,
        depth=depth,
        max_depth=max_depth,
        noise_signature_base=noise_base,
        fuel_capacity=fuel_capacity,
    )


class TestSpeedNoiseCurve:
    def test_quiet_speed(self) -> None:
        engine = SubmarineMovementEngine()
        sub = _make_sub()
        noise = engine.speed_noise_curve(sub, 2.0)
        assert noise == pytest.approx(95.0)

    def test_noise_increases_with_speed(self) -> None:
        engine = SubmarineMovementEngine()
        sub = _make_sub()
        n_slow = engine.speed_noise_curve(sub, 3.0)
        n_fast = engine.speed_noise_curve(sub, 15.0)
        assert n_fast > n_slow

    def test_noise_follows_log(self) -> None:
        engine = SubmarineMovementEngine()
        sub = _make_sub()
        n5 = engine.speed_noise_curve(sub, 5.0)
        n10 = engine.speed_noise_curve(sub, 10.0)
        # Doubling speed adds ~6 dB (20*log10(2))
        assert n10 - n5 == pytest.approx(20 * math.log10(10.0 / 5.0), abs=1.0)


class TestChangeDepth:
    def test_descend(self) -> None:
        engine = SubmarineMovementEngine()
        sub = _make_sub(depth=100.0)
        new_depth = engine.change_depth(sub, 200.0, 30.0)
        assert new_depth > 100.0
        assert new_depth <= 130.0  # 1 m/s * 30s

    def test_ascend(self) -> None:
        engine = SubmarineMovementEngine()
        sub = _make_sub(depth=200.0)
        new_depth = engine.change_depth(sub, 100.0, 30.0)
        assert new_depth < 200.0
        assert new_depth >= 170.0

    def test_at_target(self) -> None:
        engine = SubmarineMovementEngine()
        sub = _make_sub(depth=150.0)
        new_depth = engine.change_depth(sub, 150.0, 30.0)
        assert new_depth == 150.0

    def test_capped_at_max_depth(self) -> None:
        engine = SubmarineMovementEngine()
        sub = _make_sub(depth=400.0, max_depth=450.0)
        new_depth = engine.change_depth(sub, 500.0, 100.0)
        assert new_depth <= 450.0

    def test_floor_at_zero(self) -> None:
        engine = SubmarineMovementEngine()
        sub = _make_sub(depth=10.0)
        new_depth = engine.change_depth(sub, -50.0, 100.0)
        assert new_depth >= 0.0


class TestSnorkelExposure:
    def test_deep_no_exposure(self) -> None:
        engine = SubmarineMovementEngine()
        sub = _make_sub(depth=100.0)
        assert engine.snorkel_exposure(sub) == 0.0

    def test_surface_max_exposure(self) -> None:
        engine = SubmarineMovementEngine()
        sub = _make_sub(depth=0.0)
        assert engine.snorkel_exposure(sub) == 1.0

    def test_periscope_partial(self) -> None:
        engine = SubmarineMovementEngine()
        sub = _make_sub(depth=10.0)
        exp = engine.snorkel_exposure(sub)
        assert 0.0 < exp < 1.0


class TestDepthBand:
    def test_surface(self) -> None:
        engine = SubmarineMovementEngine()
        assert engine.depth_band(0.0) == SubDepthBand.SURFACE

    def test_periscope(self) -> None:
        engine = SubmarineMovementEngine()
        assert engine.depth_band(18.0) == SubDepthBand.PERISCOPE

    def test_operating(self) -> None:
        engine = SubmarineMovementEngine()
        assert engine.depth_band(200.0) == SubDepthBand.OPERATING

    def test_deep(self) -> None:
        engine = SubmarineMovementEngine()
        assert engine.depth_band(350.0) == SubDepthBand.DEEP


class TestMoveSubmarine:
    def test_moves_toward_target(self) -> None:
        engine = SubmarineMovementEngine()
        sub = _make_sub(pos=Position(0.0, 0.0))
        result = engine.move_submarine(sub, Position(1000.0, 0.0), 10.0, 150.0, 30.0)
        assert result.new_position.easting > 0

    def test_nuclear_no_fuel(self) -> None:
        engine = SubmarineMovementEngine()
        sub = _make_sub(fuel_capacity=0.0)
        result = engine.move_submarine(sub, Position(1000.0, 0.0), 10.0, 150.0, 30.0)
        assert result.fuel_consumed == 0.0

    def test_diesel_uses_fuel(self) -> None:
        engine = SubmarineMovementEngine()
        sub = _make_sub(fuel_capacity=100.0)
        result = engine.move_submarine(sub, Position(1000.0, 0.0), 10.0, 150.0, 3600.0)
        assert result.fuel_consumed > 0

    def test_noise_reported(self) -> None:
        engine = SubmarineMovementEngine()
        sub = _make_sub()
        result = engine.move_submarine(sub, Position(1000.0, 0.0), 10.0, 150.0, 30.0)
        assert result.noise_level > 0

    def test_snorkeling_at_shallow(self) -> None:
        engine = SubmarineMovementEngine()
        sub = _make_sub(depth=15.0)
        result = engine.move_submarine(sub, Position(1000.0, 0.0), 4.0, 15.0, 30.0)
        assert result.snorkeling is True

    def test_already_at_target(self) -> None:
        engine = SubmarineMovementEngine()
        sub = _make_sub(pos=Position(50.0, 50.0))
        result = engine.move_submarine(sub, Position(50.0, 50.0), 10.0, 150.0, 30.0)
        assert result.new_position == Position(50.0, 50.0)
