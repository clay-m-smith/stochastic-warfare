"""Tests for combat/events.py — event creation, immutability, EventBus integration."""

from __future__ import annotations

from datetime import datetime, timezone

from stochastic_warfare.core.events import Event, EventBus
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.combat.events import (
    AirEngagementEvent,
    AmmoExpendedEvent,
    ArtilleryFireEvent,
    CarrierSortieEvent,
    DamageEvent,
    EngagementEvent,
    FratricideEvent,
    HitEvent,
    MineEvent,
    MissileInterceptEvent,
    MissileLaunchEvent,
    NavalEngagementEvent,
    ShipDamageEvent,
    SuppressionEvent,
    TorpedoEvent,
)

_TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
_SRC = ModuleId.COMBAT


class TestCombatEventCreation:
    """All combat events can be instantiated with correct fields."""

    def test_engagement_event(self) -> None:
        e = EngagementEvent(
            timestamp=_TS, source=_SRC,
            attacker_id="u1", target_id="u2",
            weapon_id="w1", ammo_type="APFSDS", result="hit",
        )
        assert e.attacker_id == "u1"
        assert e.result == "hit"

    def test_hit_event(self) -> None:
        e = HitEvent(
            timestamp=_TS, source=_SRC,
            target_id="u2", weapon_id="w1",
            damage_type="KINETIC", penetrated=True,
        )
        assert e.penetrated is True
        assert e.damage_type == "KINETIC"

    def test_damage_event(self) -> None:
        e = DamageEvent(
            timestamp=_TS, source=_SRC,
            target_id="u2", damage_amount=0.35,
            damage_type="BLAST", location="hull",
        )
        assert e.damage_amount == 0.35

    def test_suppression_event(self) -> None:
        e = SuppressionEvent(
            timestamp=_TS, source=_SRC,
            target_id="u2", suppression_level=3,
            source_direction=1.57,
        )
        assert e.suppression_level == 3

    def test_ammo_expended_event(self) -> None:
        e = AmmoExpendedEvent(
            timestamp=_TS, source=_SRC,
            unit_id="u1", ammo_type="762_ball", quantity=30,
        )
        assert e.quantity == 30

    def test_fratricide_event(self) -> None:
        e = FratricideEvent(
            timestamp=_TS, source=_SRC,
            shooter_id="u1", victim_id="u3",
            weapon_id="w1", cause="misidentification",
        )
        assert e.cause == "misidentification"

    def test_artillery_fire_event(self) -> None:
        e = ArtilleryFireEvent(
            timestamp=_TS, source=_SRC,
            battery_id="b1", target_pos=(1000.0, 2000.0, 0.0),
            ammo_type="HE", round_count=6,
        )
        assert e.round_count == 6

    def test_missile_launch_event(self) -> None:
        e = MissileLaunchEvent(
            timestamp=_TS, source=_SRC,
            launcher_id="l1", missile_id="m1",
            target_id="u2", missile_type="CRUISE_SUBSONIC",
        )
        assert e.missile_type == "CRUISE_SUBSONIC"

    def test_missile_intercept_event(self) -> None:
        e = MissileInterceptEvent(
            timestamp=_TS, source=_SRC,
            defender_id="d1", missile_id="m1",
            interceptor_type="PAC3", success=True,
        )
        assert e.success is True

    def test_air_engagement_event(self) -> None:
        e = AirEngagementEvent(
            timestamp=_TS, source=_SRC,
            attacker_id="f1", target_id="f2",
            engagement_type="BVR",
        )
        assert e.engagement_type == "BVR"

    def test_naval_engagement_event(self) -> None:
        e = NavalEngagementEvent(
            timestamp=_TS, source=_SRC,
            attacker_id="s1", target_id="s2",
            weapon_type="ASHM",
        )
        assert e.weapon_type == "ASHM"

    def test_ship_damage_event(self) -> None:
        e = ShipDamageEvent(
            timestamp=_TS, source=_SRC,
            ship_id="s1", damage_type="missile",
            severity=0.25, system_affected="propulsion",
        )
        assert e.severity == 0.25

    def test_torpedo_event(self) -> None:
        e = TorpedoEvent(
            timestamp=_TS, source=_SRC,
            shooter_id="sub1", target_id="s1",
            torpedo_id="t1", result="hit",
        )
        assert e.result == "hit"

    def test_mine_event(self) -> None:
        e = MineEvent(
            timestamp=_TS, source=_SRC,
            mine_id="mine1", victim_id="s1",
            mine_type="MAGNETIC", result="detonated",
        )
        assert e.mine_type == "MAGNETIC"

    def test_carrier_sortie_event(self) -> None:
        e = CarrierSortieEvent(
            timestamp=_TS, source=_SRC,
            carrier_id="cv1", aircraft_id="f1",
            mission_type="CAP",
        )
        assert e.mission_type == "CAP"


class TestCombatEventImmutability:
    """Frozen dataclass events cannot be mutated."""

    def test_engagement_event_frozen(self) -> None:
        e = EngagementEvent(
            timestamp=_TS, source=_SRC,
            attacker_id="u1", target_id="u2",
            weapon_id="w1", ammo_type="HE", result="miss",
        )
        import pytest
        with pytest.raises(AttributeError):
            e.result = "hit"  # type: ignore[misc]


class TestCombatEventInheritance:
    """All combat events inherit from Event base class."""

    def test_all_inherit_from_event(self) -> None:
        event_classes = [
            EngagementEvent, HitEvent, DamageEvent, SuppressionEvent,
            AmmoExpendedEvent, FratricideEvent, ArtilleryFireEvent,
            MissileLaunchEvent, MissileInterceptEvent, AirEngagementEvent,
            NavalEngagementEvent, ShipDamageEvent, TorpedoEvent,
            MineEvent, CarrierSortieEvent,
        ]
        for cls in event_classes:
            assert issubclass(cls, Event), f"{cls.__name__} must inherit Event"


class TestCombatEventBusIntegration:
    """Combat events dispatch through the EventBus."""

    def test_engagement_event_dispatched(self) -> None:
        bus = EventBus()
        received: list[EngagementEvent] = []
        bus.subscribe(EngagementEvent, lambda e: received.append(e))

        event = EngagementEvent(
            timestamp=_TS, source=_SRC,
            attacker_id="u1", target_id="u2",
            weapon_id="w1", ammo_type="APFSDS", result="hit",
        )
        bus.publish(event)
        assert len(received) == 1
        assert received[0].attacker_id == "u1"

    def test_base_event_subscriber_receives_combat_events(self) -> None:
        bus = EventBus()
        received: list[Event] = []
        bus.subscribe(Event, lambda e: received.append(e))

        bus.publish(HitEvent(
            timestamp=_TS, source=_SRC,
            target_id="u2", weapon_id="w1",
            damage_type="KINETIC", penetrated=True,
        ))
        bus.publish(DamageEvent(
            timestamp=_TS, source=_SRC,
            target_id="u2", damage_amount=0.5,
            damage_type="BLAST", location="turret",
        ))
        assert len(received) == 2
