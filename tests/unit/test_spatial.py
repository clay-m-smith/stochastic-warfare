"""Tests for coordinates/spatial.py."""

import math

import pytest

from stochastic_warfare.coordinates.spatial import (
    bearing,
    distance,
    distance_2d,
    point_at,
)
from stochastic_warfare.core.types import Position


class TestDistance:
    def test_zero_distance(self) -> None:
        p = Position(100.0, 200.0, 50.0)
        assert distance(p, p) == 0.0

    def test_known_3d(self) -> None:
        a = Position(0.0, 0.0, 0.0)
        b = Position(3.0, 4.0, 0.0)
        assert distance(a, b) == pytest.approx(5.0)

    def test_altitude_included(self) -> None:
        a = Position(0.0, 0.0, 0.0)
        b = Position(0.0, 0.0, 100.0)
        assert distance(a, b) == pytest.approx(100.0)


class TestDistance2D:
    def test_ignores_altitude(self) -> None:
        a = Position(0.0, 0.0, 0.0)
        b = Position(3.0, 4.0, 999.0)
        assert distance_2d(a, b) == pytest.approx(5.0)


class TestBearing:
    def test_north(self) -> None:
        a = Position(0.0, 0.0)
        b = Position(0.0, 100.0)
        assert bearing(a, b) == pytest.approx(0.0, abs=1e-10)

    def test_east(self) -> None:
        a = Position(0.0, 0.0)
        b = Position(100.0, 0.0)
        assert bearing(a, b) == pytest.approx(math.pi / 2)

    def test_south(self) -> None:
        a = Position(0.0, 0.0)
        b = Position(0.0, -100.0)
        assert bearing(a, b) == pytest.approx(math.pi)

    def test_west(self) -> None:
        a = Position(0.0, 0.0)
        b = Position(-100.0, 0.0)
        assert bearing(a, b) == pytest.approx(3 * math.pi / 2)


class TestPointAt:
    def test_north_1km(self) -> None:
        origin = Position(0.0, 0.0, 0.0)
        p = point_at(origin, 0.0, 1000.0)
        assert p.easting == pytest.approx(0.0, abs=1e-10)
        assert p.northing == pytest.approx(1000.0)

    def test_east_1km(self) -> None:
        origin = Position(0.0, 0.0, 0.0)
        p = point_at(origin, math.pi / 2, 1000.0)
        assert p.easting == pytest.approx(1000.0)
        assert p.northing == pytest.approx(0.0, abs=1e-10)

    def test_inverse_of_bearing_distance(self) -> None:
        a = Position(500.0, 300.0, 0.0)
        b = Position(800.0, 700.0, 0.0)
        brg = bearing(a, b)
        dist = distance_2d(a, b)
        c = point_at(a, brg, dist)
        assert c.easting == pytest.approx(b.easting, abs=1e-6)
        assert c.northing == pytest.approx(b.northing, abs=1e-6)

    def test_preserves_altitude(self) -> None:
        origin = Position(0.0, 0.0, 150.0)
        p = point_at(origin, 0.0, 100.0)
        assert p.altitude == 150.0
