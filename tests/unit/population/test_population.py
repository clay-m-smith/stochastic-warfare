"""Tests for terrain.population — population density and disposition."""

from __future__ import annotations

import numpy as np
import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.terrain.population import (
    Disposition,
    PopulationConfig,
    PopulationManager,
    PopulationRegion,
)

_CONFIG = PopulationConfig(origin_easting=0.0, origin_northing=0.0, cell_size=100.0)


def _basic_pop() -> PopulationManager:
    density = np.array([
        [100.0, 500.0, 1000.0],
        [50.0, 200.0, 800.0],
        [10.0, 30.0, 100.0],
    ], dtype=np.float64)
    regions = [
        PopulationRegion(
            region_id="r1", name="Friendly Town",
            disposition=Disposition.FRIENDLY,
            boundary=[(0.0, 0.0), (150.0, 0.0), (150.0, 150.0), (0.0, 150.0)],
        ),
        PopulationRegion(
            region_id="r2", name="Hostile District",
            disposition=Disposition.HOSTILE,
            boundary=[(150.0, 150.0), (300.0, 150.0), (300.0, 300.0), (150.0, 300.0)],
        ),
    ]
    return PopulationManager(density, _CONFIG, regions)


class TestDensity:
    def test_density_at_cell(self) -> None:
        mgr = _basic_pop()
        # Cell (0,0) centre at (50, 50) → density 100
        assert mgr.density_at(Position(50.0, 50.0)) == pytest.approx(100.0)

    def test_density_at_urban(self) -> None:
        mgr = _basic_pop()
        # Cell (0,2) centre at (250, 50) → density 1000
        assert mgr.density_at(Position(250.0, 50.0)) == pytest.approx(1000.0)


class TestDisposition:
    def test_friendly_region(self) -> None:
        mgr = _basic_pop()
        assert mgr.disposition_at(Position(75.0, 75.0)) == Disposition.FRIENDLY

    def test_hostile_region(self) -> None:
        mgr = _basic_pop()
        assert mgr.disposition_at(Position(225.0, 225.0)) == Disposition.HOSTILE

    def test_neutral_outside_regions(self) -> None:
        mgr = _basic_pop()
        # Outside both regions
        assert mgr.disposition_at(Position(75.0, 225.0)) == Disposition.NEUTRAL

    def test_region_at(self) -> None:
        mgr = _basic_pop()
        region = mgr.region_at(Position(75.0, 75.0))
        assert region is not None
        assert region.region_id == "r1"

    def test_region_at_none(self) -> None:
        mgr = _basic_pop()
        assert mgr.region_at(Position(75.0, 225.0)) is None


class TestShiftDisposition:
    def test_shift(self) -> None:
        mgr = _basic_pop()
        mgr.shift_disposition("r1", Disposition.HOSTILE)
        assert mgr.disposition_at(Position(75.0, 75.0)) == Disposition.HOSTILE

    def test_shift_unknown_raises(self) -> None:
        mgr = _basic_pop()
        with pytest.raises(KeyError):
            mgr.shift_disposition("nonexistent", Disposition.NEUTRAL)


class TestStateRoundTrip:
    def test_get_set_state(self) -> None:
        mgr1 = _basic_pop()
        mgr1.shift_disposition("r1", Disposition.NEUTRAL)
        state = mgr1.get_state()

        mgr2 = PopulationManager(np.zeros((1, 1)), _CONFIG)
        mgr2.set_state(state)

        assert mgr2.density_at(Position(50.0, 50.0)) == pytest.approx(100.0)
        assert mgr2.disposition_at(Position(75.0, 75.0)) == Disposition.NEUTRAL
