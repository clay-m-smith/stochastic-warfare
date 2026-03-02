"""Tests for entities/unit_classes/ground.py."""

from stochastic_warfare.core.types import Domain, Position, Side
from stochastic_warfare.entities.base import Entity, Unit, UnitStatus
from stochastic_warfare.entities.unit_classes.ground import (
    GroundUnit,
    GroundUnitType,
    Posture,
)


class TestGroundUnitType:
    def test_values(self) -> None:
        assert GroundUnitType.ARMOR == 0
        assert GroundUnitType.ENGINEER == 9

    def test_count(self) -> None:
        assert len(GroundUnitType) == 10


class TestPosture:
    def test_progression(self) -> None:
        assert Posture.MOVING < Posture.HALTED < Posture.DUG_IN < Posture.FORTIFIED


class TestGroundUnitCreation:
    def test_defaults(self) -> None:
        u = GroundUnit(entity_id="g1", position=Position(0.0, 0.0))
        assert u.ground_type == GroundUnitType.LIGHT_INFANTRY
        assert u.posture == Posture.MOVING
        assert u.mounted is False
        assert u.domain == Domain.GROUND

    def test_armor(self) -> None:
        u = GroundUnit(
            entity_id="t1", position=Position(100.0, 200.0),
            ground_type=GroundUnitType.ARMOR,
            armor_front=600.0, armor_side=200.0,
        )
        assert u.ground_type == GroundUnitType.ARMOR
        assert u.armor_front == 600.0
        assert u.armor_side == 200.0

    def test_is_entity_subclass(self) -> None:
        u = GroundUnit(entity_id="g2", position=Position(0.0, 0.0))
        assert isinstance(u, Entity)
        assert isinstance(u, Unit)

    def test_domain_forced_ground(self) -> None:
        u = GroundUnit(entity_id="g3", position=Position(0.0, 0.0),
                       domain=Domain.AERIAL)  # should be overridden
        assert u.domain == Domain.GROUND

    def test_posture_transitions(self) -> None:
        u = GroundUnit(entity_id="g4", position=Position(0.0, 0.0))
        for posture in Posture:
            u.posture = posture
            assert u.posture == posture

    def test_mounted_state(self) -> None:
        u = GroundUnit(entity_id="g5", position=Position(0.0, 0.0), mounted=True)
        assert u.mounted is True

    def test_dug_in_time(self) -> None:
        u = GroundUnit(entity_id="g6", position=Position(0.0, 0.0),
                       posture=Posture.DUG_IN, dug_in_time=2.5)
        assert u.dug_in_time == 2.5


class TestGroundUnitState:
    def test_get_state(self) -> None:
        u = GroundUnit(
            entity_id="g1", position=Position(10.0, 20.0),
            ground_type=GroundUnitType.ARMOR,
            posture=Posture.DEFENSIVE,
            mounted=True, dug_in_time=1.5,
            armor_front=500.0, armor_side=150.0,
        )
        state = u.get_state()
        assert state["ground_type"] == int(GroundUnitType.ARMOR)
        assert state["posture"] == int(Posture.DEFENSIVE)
        assert state["mounted"] is True
        assert state["armor_front"] == 500.0

    def test_roundtrip(self) -> None:
        original = GroundUnit(
            entity_id="g1", position=Position(100.0, 200.0, 50.0),
            name="1st Armor", unit_type="m1a2", side=Side.BLUE,
            ground_type=GroundUnitType.ARMOR,
            posture=Posture.DUG_IN, mounted=True,
            dug_in_time=3.0, armor_front=600.0, armor_side=200.0,
        )
        state = original.get_state()
        restored = GroundUnit(entity_id="", position=Position(0.0, 0.0))
        restored.set_state(state)

        assert restored.entity_id == original.entity_id
        assert restored.name == original.name
        assert restored.ground_type == original.ground_type
        assert restored.posture == original.posture
        assert restored.mounted == original.mounted
        assert restored.dug_in_time == original.dug_in_time
        assert restored.armor_front == original.armor_front
        assert restored.armor_side == original.armor_side

    def test_roundtrip_all_ground_types(self) -> None:
        for gt in GroundUnitType:
            u = GroundUnit(entity_id=f"g{gt}", position=Position(0.0, 0.0),
                           ground_type=gt)
            state = u.get_state()
            r = GroundUnit(entity_id="", position=Position(0.0, 0.0))
            r.set_state(state)
            assert r.ground_type == gt
