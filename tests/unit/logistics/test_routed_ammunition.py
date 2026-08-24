"""Live-ammunition contracts for EngagementEngine launch routes."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import numpy as np
import pytest

from stochastic_warfare.combat.ammunition import (
    AmmoDefinition,
    AmmoState,
    WeaponDefinition,
    WeaponInstance,
)
from stochastic_warfare.combat.engagement import (
    EngagementEngine,
    EngagementType,
)
from stochastic_warfare.combat.events import (
    AmmoExpendedEvent,
    EngagementEvent,
)
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position


TIMESTAMP = datetime(2024, 6, 15, tzinfo=timezone.utc)
AMMO_ID = "phase109_route_round"


def _engine(event_bus: EventBus) -> EngagementEngine:
    return EngagementEngine(
        hit_engine=MagicMock(),
        damage_engine=MagicMock(),
        suppression_engine=MagicMock(),
        fratricide_engine=MagicMock(),
        event_bus=event_bus,
        rng=np.random.default_rng(109),
    )


def _weapon(rounds: int = 4) -> WeaponInstance:
    return WeaponInstance(
        definition=WeaponDefinition(
            weapon_id="phase109_route_launcher",
            display_name="Phase 109 routed launcher",
            category="MISSILE_LAUNCHER",
            caliber_mm=150.0,
            min_range_m=100.0,
            max_range_m=10_000.0,
            rate_of_fire_rpm=6.0,
            magazine_capacity=4,
            compatible_ammo=[AMMO_ID],
        ),
        ammo_state=AmmoState(rounds_by_type={AMMO_ID: rounds}),
    )


def _ammo() -> AmmoDefinition:
    return AmmoDefinition(
        ammo_id=AMMO_ID,
        display_name="Phase 109 routed round",
        ammo_type="MISSILE",
        guidance="WIRE",
        pk_at_reference=0.6,
    )


@pytest.mark.test_evidence("behavioral_oracle")
@pytest.mark.parametrize(
    "engagement_type",
    (
        EngagementType.COASTAL_DEFENSE,
        EngagementType.AIR_LAUNCHED_ASHM,
        EngagementType.MISSILE,
        EngagementType.ATGM_VS_ROTARY,
    ),
)
def test_routed_launches_consume_record_and_publish_exactly_once(
    engagement_type: EngagementType,
) -> None:
    event_bus = EventBus()
    expenditures: list[AmmoExpendedEvent] = []
    engagements: list[EngagementEvent] = []
    event_bus.subscribe(AmmoExpendedEvent, expenditures.append)
    event_bus.subscribe(EngagementEvent, engagements.append)
    engine = _engine(event_bus)
    weapon = _weapon()
    missile_engine = MagicMock()

    result = engine.route_engagement(
        engagement_type=engagement_type,
        attacker_id="phase109-attacker",
        target_id="phase109-target",
        attacker_pos=Position(0.0, 0.0, 0.0),
        target_pos=Position(1_000.0, 0.0, 100.0),
        weapon=weapon,
        ammo_id=AMMO_ID,
        ammo_def=_ammo(),
        missile_engine=missile_engine,
        target_altitude_m=100.0,
        current_time_s=12.0,
        timestamp=TIMESTAMP,
    )

    assert result.engaged is True
    assert weapon.ammo_state.rounds_by_type == {AMMO_ID: 3}
    assert weapon.ammo_state.total_rounds_fired == 1
    assert weapon._last_fire_time_s == 12.0
    assert [
        (event.ammo_type, event.quantity)
        for event in expenditures
    ] == [(AMMO_ID, 1)]
    assert [
        (event.weapon_id, event.ammo_type)
        for event in engagements
    ] == [(weapon.weapon_id, AMMO_ID)]
    if engagement_type is EngagementType.ATGM_VS_ROTARY:
        missile_engine.launch_missile.assert_not_called()
    else:
        missile_engine.launch_missile.assert_called_once()


@pytest.mark.test_evidence("behavioral_oracle")
@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    (
        ("no_engine", "no_missile_engine"),
        ("out_of_range", "out_of_range"),
        ("no_ammo", "no_ammo"),
        ("cooldown", "cooldown"),
    ),
)
def test_missile_route_abort_does_not_consume_or_publish(
    mutation: str,
    expected_reason: str,
) -> None:
    event_bus = EventBus()
    expenditures: list[AmmoExpendedEvent] = []
    engagements: list[EngagementEvent] = []
    event_bus.subscribe(AmmoExpendedEvent, expenditures.append)
    event_bus.subscribe(EngagementEvent, engagements.append)
    engine = _engine(event_bus)
    weapon = _weapon(rounds=0 if mutation == "no_ammo" else 4)
    missile_engine = None if mutation == "no_engine" else MagicMock()
    target = (
        Position(20_000.0, 0.0, 0.0)
        if mutation == "out_of_range"
        else Position(1_000.0, 0.0, 0.0)
    )
    if mutation == "cooldown":
        weapon.record_fire(12.0)
    before = weapon.get_state()

    result = engine.route_engagement(
        engagement_type=EngagementType.MISSILE,
        attacker_id="phase109-attacker",
        target_id="phase109-target",
        attacker_pos=Position(0.0, 0.0, 0.0),
        target_pos=target,
        weapon=weapon,
        ammo_id=AMMO_ID,
        ammo_def=_ammo(),
        missile_engine=missile_engine,
        current_time_s=12.0,
        timestamp=TIMESTAMP,
    )

    assert result.engaged is False
    assert result.aborted_reason == expected_reason
    assert weapon.get_state() == before
    assert expenditures == []
    assert engagements == []
    if missile_engine is not None:
        missile_engine.launch_missile.assert_not_called()
