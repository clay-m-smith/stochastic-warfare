"""Tests for entities/organization/echelons.py."""

from stochastic_warfare.entities.organization.echelons import (
    ECHELON_DEFINITIONS,
    EchelonDefinition,
    EchelonLevel,
)


class TestEchelonLevel:
    def test_progression(self) -> None:
        assert EchelonLevel.FIRE_TEAM < EchelonLevel.SQUAD < EchelonLevel.PLATOON
        assert EchelonLevel.COMPANY < EchelonLevel.BATTALION < EchelonLevel.BRIGADE
        assert EchelonLevel.DIVISION < EchelonLevel.CORPS < EchelonLevel.THEATER

    def test_count(self) -> None:
        assert len(EchelonLevel) == 14

    def test_individual_is_zero(self) -> None:
        assert EchelonLevel.INDIVIDUAL == 0


class TestEchelonDefinition:
    def test_creation(self) -> None:
        d = EchelonDefinition(
            level=4, name="Platoon", typical_size=40,
            span_of_control=4, staff_available=[], planning_capacity="none",
        )
        assert d.name == "Platoon"
        assert d.typical_size == 40

    def test_with_staff(self) -> None:
        d = EchelonDefinition(
            level=6, name="Battalion", typical_size=600,
            span_of_control=5, staff_available=["S1", "S2", "S3", "S4"],
            planning_capacity="full",
        )
        assert "S3" in d.staff_available


class TestStandardDefinitions:
    def test_definitions_exist(self) -> None:
        assert EchelonLevel.SQUAD in ECHELON_DEFINITIONS
        assert EchelonLevel.BATTALION in ECHELON_DEFINITIONS
        assert EchelonLevel.DIVISION in ECHELON_DEFINITIONS

    def test_squad_size(self) -> None:
        d = ECHELON_DEFINITIONS[EchelonLevel.SQUAD]
        assert d.typical_size == 9

    def test_battalion_has_staff(self) -> None:
        d = ECHELON_DEFINITIONS[EchelonLevel.BATTALION]
        assert len(d.staff_available) >= 4

    def test_size_increases_with_echelon(self) -> None:
        levels = [
            EchelonLevel.SQUAD, EchelonLevel.PLATOON,
            EchelonLevel.COMPANY, EchelonLevel.BATTALION,
            EchelonLevel.BRIGADE, EchelonLevel.DIVISION,
        ]
        sizes = [ECHELON_DEFINITIONS[l].typical_size for l in levels]
        assert sizes == sorted(sizes)
