"""Tests for c2/roe.py — rules of engagement."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from stochastic_warfare.core.events import Event, EventBus
from stochastic_warfare.c2.events import RoeChangeEvent, RoeViolationEvent
from stochastic_warfare.c2.roe import (
    RoeAreaOverride,
    RoeEngine,
    RoeLevel,
    TargetCategory,
)
from stochastic_warfare.core.types import Position

_TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


class TestRoeEnums:
    """ROE enums."""

    def test_roe_level_values(self) -> None:
        assert RoeLevel.WEAPONS_HOLD == 0
        assert RoeLevel.WEAPONS_TIGHT == 1
        assert RoeLevel.WEAPONS_FREE == 2
        assert len(RoeLevel) == 3

    def test_target_category_values(self) -> None:
        assert TargetCategory.MILITARY_COMBATANT == 0
        assert TargetCategory.UNKNOWN == 5
        assert len(TargetCategory) == 6


class TestWeaponsHold:
    """WEAPONS_HOLD: fire only in self-defense."""

    def test_weapons_hold_blocks_non_self_defense(self) -> None:
        bus = EventBus()
        roe = RoeEngine(bus, default_level=RoeLevel.WEAPONS_HOLD)
        auth, reason = roe.check_engagement_authorized(
            "plt1", "enemy1", TargetCategory.MILITARY_COMBATANT,
            id_confidence=1.0, timestamp=_TS,
        )
        assert auth is False
        assert reason == "weapons_hold_no_self_defense"

    def test_weapons_hold_allows_self_defense(self) -> None:
        bus = EventBus()
        roe = RoeEngine(bus, default_level=RoeLevel.WEAPONS_HOLD)
        auth, reason = roe.check_engagement_authorized(
            "plt1", "enemy1", TargetCategory.MILITARY_COMBATANT,
            id_confidence=1.0, is_self_defense=True, timestamp=_TS,
        )
        assert auth is True
        assert reason == "self_defense"


class TestWeaponsTight:
    """WEAPONS_TIGHT: positive ID required."""

    def test_tight_blocks_unknown_target(self) -> None:
        bus = EventBus()
        roe = RoeEngine(bus, default_level=RoeLevel.WEAPONS_TIGHT)
        auth, reason = roe.check_engagement_authorized(
            "plt1", "contact1", TargetCategory.UNKNOWN,
            id_confidence=0.3, timestamp=_TS,
        )
        assert auth is False
        assert reason == "target_not_identified"

    def test_tight_blocks_low_confidence(self) -> None:
        bus = EventBus()
        roe = RoeEngine(bus, default_level=RoeLevel.WEAPONS_TIGHT)
        auth, reason = roe.check_engagement_authorized(
            "plt1", "enemy1", TargetCategory.MILITARY_COMBATANT,
            id_confidence=0.3, timestamp=_TS,
        )
        assert auth is False
        assert reason == "insufficient_confidence"

    def test_tight_allows_high_confidence_military(self) -> None:
        bus = EventBus()
        roe = RoeEngine(bus, default_level=RoeLevel.WEAPONS_TIGHT)
        auth, reason = roe.check_engagement_authorized(
            "plt1", "enemy1", TargetCategory.MILITARY_COMBATANT,
            id_confidence=0.9, timestamp=_TS,
        )
        assert auth is True
        assert reason == "authorized"


class TestWeaponsFree:
    """WEAPONS_FREE: fire at any non-friendly target."""

    def test_weapons_free_authorizes(self) -> None:
        bus = EventBus()
        roe = RoeEngine(bus, default_level=RoeLevel.WEAPONS_FREE)
        auth, reason = roe.check_engagement_authorized(
            "plt1", "enemy1", TargetCategory.MILITARY_COMBATANT,
            id_confidence=0.5, timestamp=_TS,
        )
        assert auth is True


class TestProtectedAndCivilian:
    """Protected sites and civilians always blocked."""

    def test_protected_site_always_blocked(self) -> None:
        bus = EventBus()
        roe = RoeEngine(bus, default_level=RoeLevel.WEAPONS_FREE)
        events: list[RoeViolationEvent] = []
        bus.subscribe(RoeViolationEvent, events.append)
        auth, reason = roe.check_engagement_authorized(
            "plt1", "hospital", TargetCategory.PROTECTED_SITE,
            id_confidence=1.0, timestamp=_TS,
        )
        assert auth is False
        assert reason == "target_is_protected_site"
        assert len(events) == 1
        assert events[0].severity == "critical"

    def test_civilian_always_blocked(self) -> None:
        bus = EventBus()
        roe = RoeEngine(bus, default_level=RoeLevel.WEAPONS_FREE)
        events: list[RoeViolationEvent] = []
        bus.subscribe(RoeViolationEvent, events.append)
        auth, reason = roe.check_engagement_authorized(
            "plt1", "civ1", TargetCategory.CIVILIAN,
            id_confidence=1.0, timestamp=_TS,
        )
        assert auth is False
        assert len(events) == 1


class TestCivilianProximity:
    """Civilian proximity check."""

    def test_close_proximity_blocks(self) -> None:
        bus = EventBus()
        roe = RoeEngine(bus, default_level=RoeLevel.WEAPONS_FREE)
        auth, reason = roe.check_engagement_authorized(
            "plt1", "enemy1", TargetCategory.MILITARY_SUPPORT,
            id_confidence=0.9, civilian_proximity=100.0, timestamp=_TS,
        )
        assert auth is False
        assert "civilian_proximity" in reason

    def test_combatant_near_civilians_allowed(self) -> None:
        """Military combatants can be engaged even near civilians."""
        bus = EventBus()
        roe = RoeEngine(bus, default_level=RoeLevel.WEAPONS_FREE)
        auth, reason = roe.check_engagement_authorized(
            "plt1", "enemy1", TargetCategory.MILITARY_COMBATANT,
            id_confidence=0.9, civilian_proximity=100.0, timestamp=_TS,
        )
        assert auth is True


class TestAreaOverride:
    """Geographic ROE overrides."""

    def test_area_override_applies(self) -> None:
        bus = EventBus()
        roe = RoeEngine(bus, default_level=RoeLevel.WEAPONS_TIGHT)
        roe.set_area_override(RoeAreaOverride(
            area_id="zone1", center=Position(1000, 2000),
            radius_m=500.0, roe_level=RoeLevel.WEAPONS_FREE,
        ))
        auth, reason = roe.check_engagement_authorized(
            "plt1", "enemy1", TargetCategory.MILITARY_COMBATANT,
            id_confidence=0.5,
            target_position=Position(1000, 2000),
            timestamp=_TS,
        )
        assert auth is True  # WEAPONS_FREE in override zone


class TestRoeChangeEvent:
    """ROE change events."""

    def test_set_unit_roe_publishes_event(self) -> None:
        bus = EventBus()
        roe = RoeEngine(bus)
        events: list[RoeChangeEvent] = []
        bus.subscribe(RoeChangeEvent, events.append)
        roe.set_unit_roe("plt1", RoeLevel.WEAPONS_FREE, _TS)
        assert len(events) == 1
        assert events[0].new_roe_level == int(RoeLevel.WEAPONS_FREE)

    def test_same_level_no_event(self) -> None:
        bus = EventBus()
        roe = RoeEngine(bus, default_level=RoeLevel.WEAPONS_TIGHT)
        roe.set_unit_roe("plt1", RoeLevel.WEAPONS_TIGHT, _TS)
        events: list[RoeChangeEvent] = []
        bus.subscribe(RoeChangeEvent, events.append)
        roe.set_unit_roe("plt1", RoeLevel.WEAPONS_TIGHT, _TS)
        assert len(events) == 0


class TestRoeState:
    """State protocol."""

    def test_state_round_trip(self) -> None:
        bus = EventBus()
        roe = RoeEngine(bus, default_level=RoeLevel.WEAPONS_TIGHT)
        roe.set_unit_roe("plt1", RoeLevel.WEAPONS_FREE, _TS)
        roe.set_area_override(RoeAreaOverride(
            area_id="z1", center=Position(100, 200),
            radius_m=300.0, roe_level=RoeLevel.WEAPONS_HOLD,
        ))
        state = roe.get_state()
        roe2 = RoeEngine(bus)
        roe2.set_state(state)
        assert roe2.get_state() == state
        assert roe2.get_roe_level("plt1") == RoeLevel.WEAPONS_FREE
