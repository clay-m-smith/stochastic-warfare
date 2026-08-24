"""Tests for movement/amphibious_movement.py."""

from types import SimpleNamespace

import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.movement.amphibious_movement import (
    AmphibiousMovementEngine,
    AmphibPhase,
)


def _make_unit(pos: Position = Position(0.0, 0.0)) -> SimpleNamespace:
    return SimpleNamespace(entity_id="u1", position=pos)


class TestAmphibPhase:
    def test_progression(self) -> None:
        assert AmphibPhase.LOADING < AmphibPhase.TRANSIT < AmphibPhase.INLAND

    def test_count(self) -> None:
        assert len(AmphibPhase) == 6


class TestAssessBeach:
    def test_without_bathymetry(self) -> None:
        engine = AmphibiousMovementEngine()
        result = engine.assess_beach(Position(0.0, 0.0))
        assert "gradient" in result
        assert "suitability" in result
        assert 0.0 <= result["suitability"] <= 1.0

    def test_with_bathymetry(self) -> None:
        bathy = SimpleNamespace(depth_at=lambda p: 5.0)
        engine = AmphibiousMovementEngine(bathymetry=bathy)
        result = engine.assess_beach(Position(0.0, 0.0))
        assert result["depth_offshore"] == 5.0


class TestShipToShoreTime:
    def test_basic(self) -> None:
        engine = AmphibiousMovementEngine()
        t = engine.ship_to_shore_time(2000.0, 5.0)
        assert t == pytest.approx(400.0)

    def test_zero_speed(self) -> None:
        engine = AmphibiousMovementEngine()
        t = engine.ship_to_shore_time(2000.0, 0.0)
        assert t == float("inf")

    def test_sea_state_slows(self) -> None:
        engine = AmphibiousMovementEngine()
        sea_calm = SimpleNamespace(beaufort_scale=2)
        sea_rough = SimpleNamespace(beaufort_scale=6)
        t_calm = engine.ship_to_shore_time(2000.0, 5.0, sea_calm)
        t_rough = engine.ship_to_shore_time(2000.0, 5.0, sea_rough)
        assert t_rough > t_calm


class TestExecutePhase:
    def test_loading(self) -> None:
        engine = AmphibiousMovementEngine()
        units = [_make_unit()]
        result = engine.execute_phase(units, AmphibPhase.LOADING, 60.0)
        assert result.phase == AmphibPhase.LOADING
        assert result.units_ashore == 0

    def test_ship_to_shore(self) -> None:
        engine = AmphibiousMovementEngine()
        units = [_make_unit() for _ in range(4)]
        result = engine.execute_phase(units, AmphibPhase.SHIP_TO_SHORE, 60.0)
        assert result.phase == AmphibPhase.SHIP_TO_SHORE
        assert result.units_ashore == 2  # half per wave

    def test_beach_landing(self) -> None:
        engine = AmphibiousMovementEngine()
        units = [_make_unit() for _ in range(4)]
        result = engine.execute_phase(units, AmphibPhase.BEACH_LANDING, 60.0)
        assert result.units_ashore == 4

    def test_inland(self) -> None:
        engine = AmphibiousMovementEngine()
        units = [_make_unit()]
        result = engine.execute_phase(units, AmphibPhase.INLAND, 60.0)
        assert result.phase == AmphibPhase.INLAND
        assert result.units_ashore == 1

    def test_all_phases(self) -> None:
        engine = AmphibiousMovementEngine()
        units = [_make_unit()]
        for phase in AmphibPhase:
            result = engine.execute_phase(units, phase, 60.0)
            assert result.phase == phase
