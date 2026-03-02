"""Tests for movement/formation.py."""

import math

import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.movement.formation import FormationManager, FormationType


class TestComputePositions:
    def test_single_element(self) -> None:
        positions = FormationManager.compute_positions(
            Position(100.0, 200.0), 0.0, 1, FormationType.COLUMN, 50.0,
        )
        assert len(positions) == 1
        assert positions[0] == Position(100.0, 200.0)

    def test_zero_elements(self) -> None:
        assert FormationManager.compute_positions(
            Position(0.0, 0.0), 0.0, 0, FormationType.COLUMN, 50.0,
        ) == []

    def test_column_north(self) -> None:
        positions = FormationManager.compute_positions(
            Position(0.0, 0.0), 0.0, 4, FormationType.COLUMN, 50.0,
        )
        assert len(positions) == 4
        # Column heading north: elements trail southward
        for i in range(1, 4):
            assert positions[i].northing < positions[0].northing

    def test_line_symmetric(self) -> None:
        positions = FormationManager.compute_positions(
            Position(0.0, 0.0), 0.0, 3, FormationType.LINE, 50.0,
        )
        assert len(positions) == 3
        # Lead is at center; two flanks left and right
        # All at roughly same northing
        for p in positions:
            assert abs(p.northing) < 1.0

    def test_wedge_trails(self) -> None:
        positions = FormationManager.compute_positions(
            Position(0.0, 0.0), 0.0, 5, FormationType.WEDGE, 50.0,
        )
        # Lead is forward, all others trail behind
        for i in range(1, 5):
            assert positions[i].northing < positions[0].northing + 1.0

    def test_heading_rotates(self) -> None:
        # Same column, different heading — should rotate
        pos_north = FormationManager.compute_positions(
            Position(0.0, 0.0), 0.0, 3, FormationType.COLUMN, 50.0,
        )
        pos_east = FormationManager.compute_positions(
            Position(0.0, 0.0), math.pi / 2, 3, FormationType.COLUMN, 50.0,
        )
        # North heading: trail south (northing decreases)
        assert pos_north[1].northing < pos_north[0].northing
        # East heading: trail west (easting decreases)
        assert pos_east[1].easting < pos_east[0].easting

    def test_all_formations_produce_correct_count(self) -> None:
        for ft in FormationType:
            positions = FormationManager.compute_positions(
                Position(0.0, 0.0), 0.0, 5, ft, 50.0,
            )
            assert len(positions) == 5, f"Failed for {ft.name}"


class TestCoherence:
    def test_perfect(self) -> None:
        positions = [Position(0.0, 0.0), Position(50.0, 0.0)]
        c = FormationManager.coherence(positions, positions)
        assert c == pytest.approx(1.0)

    def test_scattered(self) -> None:
        intended = [Position(0.0, 0.0), Position(50.0, 0.0)]
        actual = [Position(0.0, 0.0), Position(200.0, 200.0)]
        c = FormationManager.coherence(intended, actual)
        assert c < 0.5

    def test_single_element(self) -> None:
        assert FormationManager.coherence(
            [Position(0.0, 0.0)], [Position(0.0, 0.0)],
        ) == 1.0

    def test_empty(self) -> None:
        assert FormationManager.coherence([], []) == 0.0

    def test_mismatched_lengths(self) -> None:
        assert FormationManager.coherence(
            [Position(0.0, 0.0)], [Position(0.0, 0.0), Position(1.0, 0.0)],
        ) == 0.0


class TestFormationSpeedFactor:
    def test_column_fastest(self) -> None:
        col = FormationManager.formation_speed_factor(FormationType.COLUMN)
        line = FormationManager.formation_speed_factor(FormationType.LINE)
        assert col >= line

    def test_all_positive(self) -> None:
        for ft in FormationType:
            assert FormationManager.formation_speed_factor(ft) > 0.0

    def test_column_is_one(self) -> None:
        assert FormationManager.formation_speed_factor(FormationType.COLUMN) == 1.0


class TestFormationFrontage:
    def test_column_zero(self) -> None:
        assert FormationManager.formation_frontage(FormationType.COLUMN, 4, 50.0) == 0.0

    def test_line_scales(self) -> None:
        f3 = FormationManager.formation_frontage(FormationType.LINE, 3, 50.0)
        f5 = FormationManager.formation_frontage(FormationType.LINE, 5, 50.0)
        assert f5 > f3

    def test_single_element_zero(self) -> None:
        assert FormationManager.formation_frontage(FormationType.LINE, 1, 50.0) == 0.0

    def test_all_formations_non_negative(self) -> None:
        for ft in FormationType:
            assert FormationManager.formation_frontage(ft, 4, 50.0) >= 0.0
