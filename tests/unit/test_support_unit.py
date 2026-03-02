"""Tests for entities/unit_classes/support.py."""

from stochastic_warfare.core.types import Domain, Position
from stochastic_warfare.entities.base import Entity, Unit
from stochastic_warfare.entities.unit_classes.support import (
    SupportUnit,
    SupportUnitType,
)


class TestSupportUnitType:
    def test_values(self) -> None:
        assert SupportUnitType.LOGISTICS_TRUCK == 0
        assert SupportUnitType.CIVIL_AFFAIRS == 9

    def test_count(self) -> None:
        assert len(SupportUnitType) == 10


class TestSupportUnitCreation:
    def test_defaults(self) -> None:
        u = SupportUnit(entity_id="s1", position=Position(0.0, 0.0))
        assert u.support_type == SupportUnitType.LOGISTICS_TRUCK
        assert u.cargo_capacity_tons == 0.0
        assert u.cargo_current_tons == 0.0
        assert u.domain == Domain.GROUND

    def test_logistics_truck(self) -> None:
        u = SupportUnit(
            entity_id="hemtt1", position=Position(0.0, 0.0),
            support_type=SupportUnitType.LOGISTICS_TRUCK,
            cargo_capacity_tons=10.0, cargo_current_tons=7.5,
        )
        assert u.cargo_capacity_tons == 10.0
        assert u.cargo_current_tons == 7.5

    def test_is_entity_subclass(self) -> None:
        u = SupportUnit(entity_id="s2", position=Position(0.0, 0.0))
        assert isinstance(u, Entity)
        assert isinstance(u, Unit)

    def test_domain_forced(self) -> None:
        u = SupportUnit(entity_id="s3", position=Position(0.0, 0.0),
                        domain=Domain.NAVAL)
        assert u.domain == Domain.GROUND


class TestCargoFraction:
    def test_full(self) -> None:
        u = SupportUnit(entity_id="s1", position=Position(0.0, 0.0),
                        cargo_capacity_tons=10.0, cargo_current_tons=10.0)
        assert u.cargo_fraction == 1.0

    def test_empty(self) -> None:
        u = SupportUnit(entity_id="s1", position=Position(0.0, 0.0),
                        cargo_capacity_tons=10.0, cargo_current_tons=0.0)
        assert u.cargo_fraction == 0.0

    def test_half(self) -> None:
        u = SupportUnit(entity_id="s1", position=Position(0.0, 0.0),
                        cargo_capacity_tons=10.0, cargo_current_tons=5.0)
        assert u.cargo_fraction == 0.5

    def test_zero_capacity(self) -> None:
        u = SupportUnit(entity_id="s1", position=Position(0.0, 0.0),
                        cargo_capacity_tons=0.0)
        assert u.cargo_fraction == 0.0

    def test_clamped_to_one(self) -> None:
        u = SupportUnit(entity_id="s1", position=Position(0.0, 0.0),
                        cargo_capacity_tons=10.0, cargo_current_tons=15.0)
        assert u.cargo_fraction == 1.0


class TestSupportState:
    def test_roundtrip(self) -> None:
        original = SupportUnit(
            entity_id="hemtt1", position=Position(300.0, 400.0),
            name="Supply Truck", unit_type="hemtt",
            support_type=SupportUnitType.LOGISTICS_TRUCK,
            cargo_capacity_tons=10.0, cargo_current_tons=6.5,
        )
        state = original.get_state()
        restored = SupportUnit(entity_id="", position=Position(0.0, 0.0))
        restored.set_state(state)

        assert restored.entity_id == original.entity_id
        assert restored.support_type == original.support_type
        assert restored.cargo_capacity_tons == original.cargo_capacity_tons
        assert restored.cargo_current_tons == original.cargo_current_tons

    def test_roundtrip_all_types(self) -> None:
        for st in SupportUnitType:
            u = SupportUnit(entity_id=f"s{st}", position=Position(0.0, 0.0),
                            support_type=st)
            state = u.get_state()
            r = SupportUnit(entity_id="", position=Position(0.0, 0.0))
            r.set_state(state)
            assert r.support_type == st
