"""Tests for movement/naval_movement.py."""

from types import SimpleNamespace

import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.movement.naval_movement import NavalMovementEngine


def _make_ship(
    max_speed: float = 16.0,
    draft: float = 9.4,
    fuel_capacity: float = 600.0,
    pos: Position = Position(0.0, 0.0),
) -> SimpleNamespace:
    return SimpleNamespace(
        entity_id="ddg1",
        position=pos,
        max_speed=max_speed,
        draft=draft,
        fuel_capacity=fuel_capacity,
    )


class TestComputeSpeed:
    def test_calm_seas(self) -> None:
        engine = NavalMovementEngine()
        ship = _make_ship()
        speed = engine.compute_speed(ship)
        assert speed == 16.0

    def test_low_beaufort_no_effect(self) -> None:
        engine = NavalMovementEngine()
        ship = _make_ship()
        sea_state = SimpleNamespace(beaufort_scale=2)
        assert engine.compute_speed(ship, sea_state) == 16.0

    def test_high_beaufort_reduces(self) -> None:
        engine = NavalMovementEngine()
        ship = _make_ship()
        sea_state = SimpleNamespace(beaufort_scale=6)
        speed = engine.compute_speed(ship, sea_state)
        assert speed < 16.0

    def test_very_high_beaufort_halves(self) -> None:
        engine = NavalMovementEngine()
        ship = _make_ship()
        sea_state = SimpleNamespace(beaufort_scale=8)
        speed = engine.compute_speed(ship, sea_state)
        assert speed == pytest.approx(8.0)


class TestFuelConsumption:
    def test_cubic_law(self) -> None:
        engine = NavalMovementEngine()
        ship = _make_ship()
        # Fuel at speed v should be proportional to v^3
        f_half = engine.fuel_consumption(ship, 8.0, 1.0)
        f_full = engine.fuel_consumption(ship, 16.0, 1.0)
        assert f_full == pytest.approx(f_half * 8.0, rel=0.01)  # 2^3 = 8x

    def test_zero_speed(self) -> None:
        engine = NavalMovementEngine()
        ship = _make_ship()
        f = engine.fuel_consumption(ship, 0.0, 1.0)
        assert f == 0.0

    def test_longer_duration_more_fuel(self) -> None:
        engine = NavalMovementEngine()
        ship = _make_ship()
        f1 = engine.fuel_consumption(ship, 10.0, 1.0)
        f2 = engine.fuel_consumption(ship, 10.0, 2.0)
        assert f2 == pytest.approx(2 * f1)


class TestCheckDraft:
    def test_no_bathymetry_ok(self) -> None:
        engine = NavalMovementEngine()
        assert engine.check_draft(_make_ship(), Position(0.0, 0.0)) is True

    def test_with_bathymetry_deep(self) -> None:
        bathy = SimpleNamespace(depth_at=lambda p: 50.0)
        engine = NavalMovementEngine(bathymetry=bathy)
        assert engine.check_draft(_make_ship(draft=9.4), Position(0.0, 0.0)) is True

    def test_with_bathymetry_shallow(self) -> None:
        bathy = SimpleNamespace(depth_at=lambda p: 5.0)
        engine = NavalMovementEngine(bathymetry=bathy)
        assert engine.check_draft(_make_ship(draft=9.4), Position(0.0, 0.0)) is False


class TestMoveShip:
    def test_moves_toward_target(self) -> None:
        engine = NavalMovementEngine()
        ship = _make_ship(pos=Position(0.0, 0.0))
        result = engine.move_ship(ship, Position(1000.0, 0.0), 16.0, 10.0)
        assert result.new_position.easting > 0
        assert result.new_position.easting <= 1000.0

    def test_already_at_target(self) -> None:
        engine = NavalMovementEngine()
        ship = _make_ship(pos=Position(50.0, 50.0))
        result = engine.move_ship(ship, Position(50.0, 50.0), 16.0, 10.0)
        assert result.speed_actual == 0.0

    def test_fuel_consumed(self) -> None:
        engine = NavalMovementEngine()
        ship = _make_ship()
        result = engine.move_ship(ship, Position(10000.0, 0.0), 16.0, 3600.0)
        assert result.fuel_consumed > 0

    def test_draft_check_at_destination(self) -> None:
        bathy = SimpleNamespace(depth_at=lambda p: 50.0)
        engine = NavalMovementEngine(bathymetry=bathy)
        ship = _make_ship()
        result = engine.move_ship(ship, Position(1000.0, 0.0), 16.0, 10.0)
        assert result.draft_ok is True
