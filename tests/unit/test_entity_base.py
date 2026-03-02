"""Tests for entities/base.py — Entity and Unit classes."""

import numpy as np

from stochastic_warfare.core.types import Domain, Position, Side
from stochastic_warfare.entities.base import Entity, Unit, UnitStatus
from stochastic_warfare.entities.equipment import EquipmentCategory, EquipmentItem
from stochastic_warfare.entities.personnel import CrewMember, CrewRole, SkillLevel


# ── Entity basics (backward-compatible) ──────────────────────────────


class TestEntityBasics:
    def test_creation(self) -> None:
        e = Entity(entity_id="tank-01", position=Position(100.0, 200.0, 0.0))
        assert e.entity_id == "tank-01"
        assert e.position == Position(100.0, 200.0, 0.0)

    def test_position_mutable(self) -> None:
        e = Entity(entity_id="inf-01", position=Position(0.0, 0.0))
        e.position = Position(50.0, 75.0, 10.0)
        assert e.position.easting == 50.0


class TestEntityState:
    def test_get_state(self) -> None:
        e = Entity(entity_id="arty-01", position=Position(1.0, 2.0, 3.0))
        state = e.get_state()
        assert state["entity_id"] == "arty-01"
        assert state["position"] == (1.0, 2.0, 3.0)

    def test_roundtrip(self) -> None:
        original = Entity(entity_id="helo-01", position=Position(500.0, 600.0, 100.0))
        state = original.get_state()

        restored = Entity(entity_id="", position=Position(0.0, 0.0))
        restored.set_state(state)

        assert restored.entity_id == original.entity_id
        assert restored.position == original.position


# ── UnitStatus enum ──────────────────────────────────────────────────


class TestUnitStatus:
    def test_values(self) -> None:
        assert UnitStatus.ACTIVE == 0
        assert UnitStatus.DESTROYED == 2
        assert UnitStatus.ROUTING == 4

    def test_all_members(self) -> None:
        assert len(UnitStatus) == 5


# ── Unit basics ──────────────────────────────────────────────────────


class TestUnitCreation:
    def test_minimal(self) -> None:
        u = Unit(entity_id="u1", position=Position(0.0, 0.0))
        assert u.entity_id == "u1"
        assert u.domain == Domain.GROUND
        assert u.status == UnitStatus.ACTIVE
        assert u.personnel == []
        assert u.equipment == []

    def test_full_fields(self) -> None:
        crew = [
            CrewMember("c1", CrewRole.COMMANDER, SkillLevel.VETERAN, 0.8),
            CrewMember("c2", CrewRole.GUNNER, SkillLevel.TRAINED, 0.5),
        ]
        gear = [
            EquipmentItem("e1", "M256 120mm", EquipmentCategory.WEAPON),
        ]
        u = Unit(
            entity_id="tank-01",
            position=Position(100.0, 200.0, 50.0),
            name="1st Tank",
            unit_type="m1a2",
            side=Side.BLUE,
            domain=Domain.GROUND,
            status=UnitStatus.ACTIVE,
            heading=1.57,
            speed=5.0,
            max_speed=18.0,
            personnel=crew,
            equipment=gear,
        )
        assert u.name == "1st Tank"
        assert u.unit_type == "m1a2"
        assert u.side == Side.BLUE
        assert len(u.personnel) == 2
        assert len(u.equipment) == 1

    def test_is_entity_subclass(self) -> None:
        u = Unit(entity_id="u2", position=Position(0.0, 0.0))
        assert isinstance(u, Entity)

    def test_heading_and_speed(self) -> None:
        u = Unit(entity_id="u3", position=Position(0.0, 0.0), heading=3.14, speed=10.0)
        assert u.heading == 3.14
        assert u.speed == 10.0

    def test_default_side(self) -> None:
        u = Unit(entity_id="u4", position=Position(0.0, 0.0))
        assert u.side == Side.BLUE

    def test_domain_values(self) -> None:
        for domain in Domain:
            u = Unit(entity_id=f"d{domain}", position=Position(0.0, 0.0), domain=domain)
            assert u.domain == domain


class TestUnitState:
    def test_get_state_includes_all_fields(self) -> None:
        u = Unit(
            entity_id="u1",
            position=Position(10.0, 20.0, 5.0),
            name="Test",
            unit_type="test_type",
            side=Side.RED,
            domain=Domain.AERIAL,
            status=UnitStatus.DISABLED,
            heading=0.5,
            speed=3.0,
            max_speed=15.0,
        )
        state = u.get_state()
        assert state["entity_id"] == "u1"
        assert state["name"] == "Test"
        assert state["unit_type"] == "test_type"
        assert state["side"] == Side.RED
        assert state["domain"] == int(Domain.AERIAL)
        assert state["status"] == int(UnitStatus.DISABLED)
        assert state["heading"] == 0.5
        assert state["speed"] == 3.0
        assert state["max_speed"] == 15.0

    def test_roundtrip_empty_unit(self) -> None:
        original = Unit(entity_id="u1", position=Position(100.0, 200.0))
        state = original.get_state()
        restored = Unit(entity_id="", position=Position(0.0, 0.0))
        restored.set_state(state)
        assert restored.entity_id == original.entity_id
        assert restored.position == original.position
        assert restored.domain == original.domain

    def test_roundtrip_with_personnel_and_equipment(self) -> None:
        crew = [
            CrewMember("c1", CrewRole.COMMANDER, SkillLevel.VETERAN, 0.8),
            CrewMember("c2", CrewRole.DRIVER, SkillLevel.TRAINED, 0.3),
        ]
        gear = [
            EquipmentItem("e1", "Main Gun", EquipmentCategory.WEAPON, condition=0.9),
            EquipmentItem("e2", "Radio", EquipmentCategory.COMMUNICATION),
        ]
        original = Unit(
            entity_id="tank-01",
            position=Position(500.0, 600.0, 100.0),
            name="Alpha",
            unit_type="m1a2",
            side=Side.BLUE,
            domain=Domain.GROUND,
            status=UnitStatus.ACTIVE,
            heading=1.0,
            speed=5.0,
            max_speed=18.0,
            personnel=crew,
            equipment=gear,
        )
        state = original.get_state()
        restored = Unit(entity_id="", position=Position(0.0, 0.0))
        restored.set_state(state)

        assert restored.entity_id == original.entity_id
        assert restored.name == original.name
        assert len(restored.personnel) == 2
        assert restored.personnel[0].member_id == "c1"
        assert restored.personnel[0].role == CrewRole.COMMANDER
        assert restored.personnel[0].skill == SkillLevel.VETERAN
        assert len(restored.equipment) == 2
        assert restored.equipment[0].equipment_id == "e1"
        assert restored.equipment[0].condition == 0.9

    def test_roundtrip_preserves_status(self) -> None:
        for status in UnitStatus:
            u = Unit(entity_id="u", position=Position(0.0, 0.0), status=status)
            state = u.get_state()
            r = Unit(entity_id="", position=Position(0.0, 0.0))
            r.set_state(state)
            assert r.status == status
