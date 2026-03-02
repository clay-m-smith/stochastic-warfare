"""Tests for entities/unit_classes/aerial.py."""

from stochastic_warfare.core.types import Domain, Position, Side
from stochastic_warfare.entities.base import Entity, Unit
from stochastic_warfare.entities.unit_classes.aerial import (
    AerialUnit,
    AerialUnitType,
    FlightState,
)


class TestAerialUnitType:
    def test_fixed_wing(self) -> None:
        assert AerialUnitType.FIGHTER == 0
        assert AerialUnitType.AEW == 7

    def test_rotary(self) -> None:
        assert AerialUnitType.ATTACK_HELO == 8
        assert AerialUnitType.CARGO_HELO == 11

    def test_uav(self) -> None:
        assert AerialUnitType.UAV_RECON == 12
        assert AerialUnitType.UAV_LOITERING_MUNITION == 14

    def test_count(self) -> None:
        assert len(AerialUnitType) == 15


class TestFlightState:
    def test_values(self) -> None:
        assert FlightState.GROUNDED == 0
        assert FlightState.HOVERING == 5


class TestAerialUnitCreation:
    def test_defaults(self) -> None:
        u = AerialUnit(entity_id="a1", position=Position(0.0, 0.0))
        assert u.aerial_type == AerialUnitType.FIGHTER
        assert u.flight_state == FlightState.GROUNDED
        assert u.altitude == 0.0
        assert u.fuel_remaining == 1.0
        assert u.domain == Domain.AERIAL
        assert u.data_link_range is None

    def test_fighter(self) -> None:
        u = AerialUnit(
            entity_id="f16", position=Position(0.0, 0.0),
            aerial_type=AerialUnitType.FIGHTER,
            service_ceiling=15240.0,
            max_speed=600.0,
        )
        assert u.service_ceiling == 15240.0

    def test_uav_with_data_link(self) -> None:
        u = AerialUnit(
            entity_id="mq9", position=Position(0.0, 0.0),
            aerial_type=AerialUnitType.UAV_RECON,
            data_link_range=250000.0,
            data_link_active=True,
        )
        assert u.is_uav
        assert u.data_link_range == 250000.0

    def test_is_entity_subclass(self) -> None:
        u = AerialUnit(entity_id="a2", position=Position(0.0, 0.0))
        assert isinstance(u, Entity)
        assert isinstance(u, Unit)

    def test_domain_forced_aerial(self) -> None:
        u = AerialUnit(entity_id="a3", position=Position(0.0, 0.0),
                       domain=Domain.GROUND)
        assert u.domain == Domain.AERIAL


class TestAerialProperties:
    def test_is_uav_fixed_wing(self) -> None:
        for at in (AerialUnitType.UAV_RECON, AerialUnitType.UAV_ARMED,
                   AerialUnitType.UAV_LOITERING_MUNITION):
            u = AerialUnit(entity_id="u", position=Position(0.0, 0.0),
                           aerial_type=at)
            assert u.is_uav

    def test_not_uav(self) -> None:
        u = AerialUnit(entity_id="f", position=Position(0.0, 0.0),
                       aerial_type=AerialUnitType.FIGHTER)
        assert not u.is_uav

    def test_is_rotary_wing(self) -> None:
        for at in (AerialUnitType.ATTACK_HELO, AerialUnitType.UTILITY_HELO,
                   AerialUnitType.RECON_HELO, AerialUnitType.CARGO_HELO):
            u = AerialUnit(entity_id="h", position=Position(0.0, 0.0),
                           aerial_type=at)
            assert u.is_rotary_wing

    def test_not_rotary(self) -> None:
        u = AerialUnit(entity_id="f", position=Position(0.0, 0.0),
                       aerial_type=AerialUnitType.FIGHTER)
        assert not u.is_rotary_wing


class TestAerialFlightStates:
    def test_all_states(self) -> None:
        for fs in FlightState:
            u = AerialUnit(entity_id="a", position=Position(0.0, 0.0),
                           flight_state=fs)
            assert u.flight_state == fs

    def test_loiter_time(self) -> None:
        u = AerialUnit(entity_id="a", position=Position(0.0, 0.0),
                       loiter_time_remaining=3600.0)
        assert u.loiter_time_remaining == 3600.0


class TestAerialState:
    def test_get_state(self) -> None:
        u = AerialUnit(
            entity_id="a1", position=Position(0.0, 0.0),
            aerial_type=AerialUnitType.ATTACK_HELO,
            flight_state=FlightState.AIRBORNE,
            altitude=500.0, fuel_remaining=0.8,
        )
        state = u.get_state()
        assert state["aerial_type"] == int(AerialUnitType.ATTACK_HELO)
        assert state["flight_state"] == int(FlightState.AIRBORNE)
        assert state["altitude"] == 500.0

    def test_roundtrip(self) -> None:
        original = AerialUnit(
            entity_id="f16", position=Position(1000.0, 2000.0, 5000.0),
            name="Viper 1", unit_type="f16c", side=Side.BLUE,
            aerial_type=AerialUnitType.FIGHTER,
            flight_state=FlightState.AIRBORNE,
            altitude=8000.0, fuel_remaining=0.65,
            service_ceiling=15240.0,
            data_link_range=None, data_link_active=True,
            loiter_time_remaining=1800.0,
        )
        state = original.get_state()
        restored = AerialUnit(entity_id="", position=Position(0.0, 0.0))
        restored.set_state(state)

        assert restored.entity_id == original.entity_id
        assert restored.aerial_type == original.aerial_type
        assert restored.flight_state == original.flight_state
        assert restored.altitude == original.altitude
        assert restored.fuel_remaining == original.fuel_remaining
        assert restored.service_ceiling == original.service_ceiling
        assert restored.data_link_range is None
        assert restored.loiter_time_remaining == original.loiter_time_remaining

    def test_roundtrip_all_types(self) -> None:
        for at in AerialUnitType:
            u = AerialUnit(entity_id=f"a{at}", position=Position(0.0, 0.0),
                           aerial_type=at)
            state = u.get_state()
            r = AerialUnit(entity_id="", position=Position(0.0, 0.0))
            r.set_state(state)
            assert r.aerial_type == at
