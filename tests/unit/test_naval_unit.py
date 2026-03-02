"""Tests for entities/unit_classes/naval.py."""

from stochastic_warfare.core.types import Domain, Position, Side
from stochastic_warfare.entities.base import Entity, Unit
from stochastic_warfare.entities.unit_classes.naval import NavalUnit, NavalUnitType


class TestNavalUnitType:
    def test_surface_combatants(self) -> None:
        assert NavalUnitType.CARRIER == 0
        assert NavalUnitType.PATROL == 5

    def test_submarines(self) -> None:
        assert NavalUnitType.SSN == 6
        assert NavalUnitType.SSK == 8

    def test_amphibious(self) -> None:
        assert NavalUnitType.LHD == 9
        assert NavalUnitType.LANDING_CRAFT == 12

    def test_count(self) -> None:
        assert len(NavalUnitType) == 20


class TestNavalUnitCreation:
    def test_defaults(self) -> None:
        u = NavalUnit(entity_id="n1", position=Position(0.0, 0.0))
        assert u.naval_type == NavalUnitType.DESTROYER
        assert u.hull_integrity == 1.0
        assert u.domain == Domain.NAVAL
        assert u.is_submarine is False

    def test_destroyer(self) -> None:
        u = NavalUnit(
            entity_id="ddg51", position=Position(0.0, 0.0),
            naval_type=NavalUnitType.DESTROYER,
            draft=9.4, displacement=9200.0,
            fuel_capacity=600.0, max_speed=16.0,
        )
        assert u.draft == 9.4
        assert u.displacement == 9200.0

    def test_is_entity_subclass(self) -> None:
        u = NavalUnit(entity_id="n2", position=Position(0.0, 0.0))
        assert isinstance(u, Entity)
        assert isinstance(u, Unit)


class TestNavalDomainAutoDetect:
    def test_ssn_is_submarine(self) -> None:
        u = NavalUnit(entity_id="ssn1", position=Position(0.0, 0.0),
                      naval_type=NavalUnitType.SSN)
        assert u.is_submarine
        assert u.domain == Domain.SUBMARINE

    def test_ssbn_is_submarine(self) -> None:
        u = NavalUnit(entity_id="ssbn1", position=Position(0.0, 0.0),
                      naval_type=NavalUnitType.SSBN)
        assert u.is_submarine
        assert u.domain == Domain.SUBMARINE

    def test_ssk_is_submarine(self) -> None:
        u = NavalUnit(entity_id="ssk1", position=Position(0.0, 0.0),
                      naval_type=NavalUnitType.SSK)
        assert u.is_submarine
        assert u.domain == Domain.SUBMARINE

    def test_lhd_is_amphibious(self) -> None:
        u = NavalUnit(entity_id="lhd1", position=Position(0.0, 0.0),
                      naval_type=NavalUnitType.LHD)
        assert u.domain == Domain.AMPHIBIOUS
        assert not u.is_submarine

    def test_lpd_is_amphibious(self) -> None:
        u = NavalUnit(entity_id="lpd1", position=Position(0.0, 0.0),
                      naval_type=NavalUnitType.LPD)
        assert u.domain == Domain.AMPHIBIOUS

    def test_destroyer_is_naval(self) -> None:
        u = NavalUnit(entity_id="dd1", position=Position(0.0, 0.0),
                      naval_type=NavalUnitType.DESTROYER)
        assert u.domain == Domain.NAVAL
        assert not u.is_submarine

    def test_carrier_is_naval(self) -> None:
        u = NavalUnit(entity_id="cv1", position=Position(0.0, 0.0),
                      naval_type=NavalUnitType.CARRIER)
        assert u.domain == Domain.NAVAL


class TestNavalSubmarineFields:
    def test_depth_and_max_depth(self) -> None:
        u = NavalUnit(
            entity_id="ssn1", position=Position(0.0, 0.0),
            naval_type=NavalUnitType.SSN,
            depth=150.0, max_depth=300.0,
        )
        assert u.depth == 150.0
        assert u.max_depth == 300.0

    def test_noise_signature(self) -> None:
        u = NavalUnit(
            entity_id="ssn1", position=Position(0.0, 0.0),
            naval_type=NavalUnitType.SSN,
            noise_signature_base=90.0,
        )
        assert u.noise_signature_base == 90.0


class TestNavalState:
    def test_roundtrip_surface(self) -> None:
        original = NavalUnit(
            entity_id="ddg51", position=Position(5000.0, 10000.0),
            name="USS Arleigh Burke", unit_type="ddg51",
            side=Side.BLUE, naval_type=NavalUnitType.DESTROYER,
            hull_integrity=0.95, draft=9.4, displacement=9200.0,
            fuel_capacity=600.0, fuel_remaining=0.85,
        )
        state = original.get_state()
        restored = NavalUnit(entity_id="", position=Position(0.0, 0.0))
        restored.set_state(state)

        assert restored.entity_id == original.entity_id
        assert restored.naval_type == original.naval_type
        assert restored.hull_integrity == original.hull_integrity
        assert restored.draft == original.draft
        assert restored.displacement == original.displacement
        assert restored.fuel_remaining == original.fuel_remaining

    def test_roundtrip_submarine(self) -> None:
        original = NavalUnit(
            entity_id="ssn688", position=Position(0.0, 0.0),
            naval_type=NavalUnitType.SSN,
            depth=200.0, max_depth=450.0,
            noise_signature_base=95.0,
        )
        state = original.get_state()
        restored = NavalUnit(entity_id="", position=Position(0.0, 0.0))
        restored.set_state(state)

        assert restored.is_submarine
        assert restored.depth == 200.0
        assert restored.max_depth == 450.0
        assert restored.noise_signature_base == 95.0

    def test_roundtrip_all_types(self) -> None:
        for nt in NavalUnitType:
            u = NavalUnit(entity_id=f"n{nt}", position=Position(0.0, 0.0),
                          naval_type=nt)
            state = u.get_state()
            r = NavalUnit(entity_id="", position=Position(0.0, 0.0))
            r.set_state(state)
            assert r.naval_type == nt
