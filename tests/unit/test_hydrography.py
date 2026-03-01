"""Tests for terrain.hydrography — rivers, lakes, and ford points."""

from __future__ import annotations

import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.terrain.hydrography import HydrographyManager, Lake, River


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _river() -> River:
    return River(
        river_id="danube",
        name="Danube",
        centerline=[(0.0, 500.0), (1000.0, 500.0)],
        width=40.0,
        depth=3.0,
        current_speed=1.5,
        ford_points=[(200.0, 500.0)],
        ford_depth=0.8,
    )


def _lake() -> Lake:
    return Lake(
        lake_id="lake_01",
        name="Mirror Lake",
        boundary=[(600.0, 600.0), (800.0, 600.0), (800.0, 800.0), (600.0, 800.0)],
        depth=10.0,
    )


def _hydro() -> HydrographyManager:
    return HydrographyManager(rivers=[_river()], lakes=[_lake()])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRiverQueries:
    def test_rivers_near(self) -> None:
        h = _hydro()
        nearby = h.rivers_near(Position(500.0, 480.0), radius=50.0)
        assert len(nearby) == 1
        assert nearby[0].river_id == "danube"

    def test_rivers_far(self) -> None:
        h = _hydro()
        assert len(h.rivers_near(Position(500.0, 100.0), radius=10.0)) == 0

    def test_nearest_river(self) -> None:
        h = _hydro()
        result = h.nearest_river(Position(500.0, 520.0))
        assert result is not None
        river, dist = result
        assert river.river_id == "danube"
        assert dist < 25.0

    def test_nearest_river_empty(self) -> None:
        h = HydrographyManager()
        assert h.nearest_river(Position(0.0, 0.0)) is None


class TestWaterContainment:
    def test_in_river(self) -> None:
        h = _hydro()
        # On the river centerline (within buffer)
        assert h.is_in_water(Position(500.0, 500.0))

    def test_not_in_river(self) -> None:
        h = _hydro()
        assert not h.is_in_water(Position(500.0, 100.0))

    def test_in_lake(self) -> None:
        h = _hydro()
        assert h.is_in_water(Position(700.0, 700.0))

    def test_not_in_lake(self) -> None:
        h = _hydro()
        assert not h.is_in_water(Position(900.0, 900.0))


class TestFordability:
    def test_fordable_normal(self) -> None:
        h = _hydro()
        # Normal depth 3.0 * 1.0 = 3.0 > ford_depth 0.8 → NOT fordable
        assert not h.is_fordable("danube", water_level_multiplier=1.0)

    def test_fordable_low_water(self) -> None:
        h = _hydro()
        # Depth 3.0 * 0.2 = 0.6 < ford_depth 0.8 → fordable
        assert h.is_fordable("danube", water_level_multiplier=0.2)

    def test_fordable_flood(self) -> None:
        h = _hydro()
        assert not h.is_fordable("danube", water_level_multiplier=2.0)

    def test_effective_depth(self) -> None:
        h = _hydro()
        assert h.effective_depth("danube", 1.5) == pytest.approx(4.5)

    def test_unknown_river_raises(self) -> None:
        h = _hydro()
        with pytest.raises(KeyError):
            h.is_fordable("nonexistent")

    def test_ford_points_near(self) -> None:
        h = _hydro()
        fords = h.ford_points_near(Position(200.0, 500.0), radius=50.0)
        assert len(fords) == 1

    def test_ford_points_far(self) -> None:
        h = _hydro()
        assert len(h.ford_points_near(Position(800.0, 800.0), radius=50.0)) == 0

    def test_no_ford_points_not_fordable(self) -> None:
        river = River(
            river_id="no_ford",
            name="Deep River",
            centerline=[(0.0, 0.0), (100.0, 0.0)],
            width=20.0,
            depth=5.0,
            current_speed=2.0,
        )
        h = HydrographyManager(rivers=[river])
        assert not h.is_fordable("no_ford")


class TestStateRoundTrip:
    def test_get_set_state(self) -> None:
        h1 = _hydro()
        state = h1.get_state()

        h2 = HydrographyManager()
        h2.set_state(state)

        assert len(h2._rivers) == 1
        assert len(h2._lakes) == 1
        assert h2.is_in_water(Position(700.0, 700.0))
