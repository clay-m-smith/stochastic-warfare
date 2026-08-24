"""Production controls for Phase 115 direct/routed owner arbitration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from stochastic_warfare.combat.events import (
    AmmoExpendedEvent,
    ArtilleryFireEvent,
    EngagementEvent,
)
from stochastic_warfare.core.events import Event
from stochastic_warfare.core.types import Domain
from stochastic_warfare.entities.unit_classes.naval import (
    NavalUnit,
    NavalUnitType,
)
from stochastic_warfare.simulation.battle import BattleConfig
from stochastic_warfare.simulation.campaign import CampaignConfig
from stochastic_warfare.simulation.loadouts import (
    WeaponAttachment,
    WeaponModeledRole,
)
from stochastic_warfare.simulation.runtime import (
    AnalysisVariant,
    PreparedScenario,
    RuntimeSession,
    SimulationRuntimeFactory,
)
from stochastic_warfare.simulation.scenario import CampaignScenarioConfig
from stochastic_warfare.simulation.tactical_targeting import (
    TacticalTargetingDecision,
)


ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data"
_SOURCE_BY_ERA = {
    "modern": DATA_DIR / "scenarios" / "khafji" / "scenario.yaml",
    "ww2": DATA_DIR / "eras" / "ww2" / "scenarios" / "midway" / "scenario.yaml",
    "ww1": DATA_DIR / "eras" / "ww1" / "scenarios" / "cambrai" / "scenario.yaml",
    "ancient_medieval": (DATA_DIR / "eras" / "ancient_medieval" / "scenarios" / "cannae" / "scenario.yaml"),
}
_DATE_BY_ERA = {
    "modern": "2004-01-01T12:00:00Z",
    "ww2": "1943-01-01T12:00:00Z",
    "ww1": "1917-01-01T12:00:00Z",
    "ancient_medieval": "0216-08-02T12:00:00Z",
}


@dataclass(frozen=True, slots=True)
class _OwnerCase:
    name: str
    era: str
    shooter_type: str
    target_type: str
    role: WeaponModeledRole
    weapon_id: str
    distance_m: float
    shooter_altitude_m: float = 0.0
    event_owner: str = "engagement"


_OWNER_CASES = (
    _OwnerCase(
        "field_artillery",
        "ww1",
        "18pdr_battery",
        "german_sturmtruppen",
        WeaponModeledRole.FIELD_ARTILLERY,
        "18pdr_field_gun",
        1_000.0,
        event_owner="artillery",
    ),
    _OwnerCase(
        "mortar_fire",
        "modern",
        "iraqi_insurgent_mortar_team",
        "t72m",
        WeaponModeledRole.MORTAR_FIRE,
        "2b14_82mm_mortar",
        1_000.0,
        event_owner="artillery",
    ),
    _OwnerCase(
        "rocket_artillery",
        "modern",
        "iraqi_bm21_grad",
        "t72m",
        WeaponModeledRole.ROCKET_ARTILLERY,
        "bm21_grad",
        5_000.0,
        event_owner="artillery",
    ),
    _OwnerCase(
        "bomb_delivery",
        "modern",
        "b52h",
        "t72m",
        WeaponModeledRole.BOMB_DELIVERY,
        "bomb_rack_generic",
        1_000.0,
        shooter_altitude_m=1_000.0,
    ),
    _OwnerCase(
        "torpedo",
        "modern",
        "kilo636",
        "ddg51",
        WeaponModeledRole.TORPEDO,
        "project636_533mm_torpedo_tube",
        1_000.0,
    ),
    _OwnerCase(
        "anti_submarine",
        "ww2",
        "flower_corvette",
        "type_viic_uboat",
        WeaponModeledRole.ANTI_SUBMARINE,
        "depth_charge_mk7",
        100.0,
    ),
    _OwnerCase(
        "hand_grenade",
        "ww1",
        "british_infantry_platoon",
        "german_sturmtruppen",
        WeaponModeledRole.HAND_GRENADE,
        "mills_bomb",
        20.0,
    ),
    _OwnerCase(
        "melee",
        "ancient_medieval",
        "roman_legionary_cohort",
        "carthaginian_infantry",
        WeaponModeledRole.MELEE,
        "gladius",
        1.0,
    ),
)


def _scenario(case: _OwnerCase) -> CampaignScenarioConfig:
    shooter_position = [
        10_000.0,
        10_000.0,
        case.shooter_altitude_m,
    ]
    target_position = [
        10_000.0,
        10_000.0 + case.distance_m,
        0.0,
    ]
    return CampaignScenarioConfig.model_validate(
        {
            "name": f"Phase 115 {case.name} owner control",
            "date": _DATE_BY_ERA[case.era],
            "duration_hours": 1.0,
            "era": case.era,
            "tick_resolution": {
                "strategic_s": 3_600.0,
                "operational_s": 300.0,
                "tactical_s": 5.0,
            },
            "weather_conditions": {
                "visibility_m": 60_000.0,
                "precipitation": "none",
            },
            "terrain": {
                "width_m": 100_000.0,
                "height_m": 100_000.0,
                "cell_size_m": 100.0,
                "terrain_type": "flat_desert",
            },
            "deployment": {"mode": "manual"},
            "sides": [
                {
                    "side": "blue",
                    "units": [
                        {
                            "unit_type": case.shooter_type,
                            "count": 1,
                            "position": shooter_position,
                        }
                    ],
                },
                {
                    "side": "red",
                    "units": [
                        {
                            "unit_type": case.target_type,
                            "count": 1,
                            "position": target_position,
                        }
                    ],
                },
            ],
            "objectives": [],
            "victory_conditions": [],
            "behavior_rules": {
                "blue": {"hold_position": True},
                "red": {"hold_position": True},
            },
            "calibration_overrides": {
                "defensive_sides": [],
                "enable_air_routing": True,
                "enable_fog_of_war": False,
                "enable_sensing_aware_standoff": True,
                "target_selection_mode": "closest",
                "visibility_m": 60_000.0,
            },
        }
    )


def _prepare(case: _OwnerCase) -> PreparedScenario:
    return SimulationRuntimeFactory().prepare_config(
        _scenario(case),
        DATA_DIR,
        (
            AnalysisVariant(variant_id=f"{case.name}-standoff-on"),
            AnalysisVariant(
                variant_id=f"{case.name}-standoff-off",
                calibration_patch={
                    "enable_sensing_aware_standoff": False,
                },
            ),
        ),
        source_label=str(_SOURCE_BY_ERA[case.era].resolve()),
    )


def _build(
    prepared: PreparedScenario,
    case: _OwnerCase,
    *,
    standoff_enabled: bool,
) -> RuntimeSession:
    suffix = "on" if standoff_enabled else "off"
    return prepared.build(
        f"{case.name}-standoff-{suffix}",
        seed=115,
        max_ticks=2,
        campaign_config=CampaignConfig(
            engagement_detection_range_m=60_000.0,
            enable_strategic_movement=False,
            enable_maintenance=False,
            enable_supply_network=False,
        ),
        battle_config=BattleConfig(engagement_range_m=60_000.0),
        strict_mode=True,
    )


def _unit(session: RuntimeSession, unit_type: str):
    return next(unit for unit in session.context.all_units() if unit.unit_type == unit_type)


def _attachment(
    session: RuntimeSession,
    shooter_id: str,
    *,
    role: WeaponModeledRole,
    weapon_id: str,
) -> WeaponAttachment:
    matches = tuple(
        attachment
        for attachment in session.context.unit_weapons[shooter_id]
        if attachment.modeled_role is role and attachment.weapon.weapon_id == weapon_id
    )
    assert len(matches) == 1
    return matches[0]


def _exhaust_attachment(attachment: WeaponAttachment) -> None:
    for ammunition_id in attachment.weapon.ammo_state.rounds_by_type:
        attachment.weapon.ammo_state.rounds_by_type[ammunition_id] = 0


def _isolate_attachment(
    session: RuntimeSession,
    shooter_id: str,
    selected: WeaponAttachment,
) -> None:
    for attachment in session.context.unit_weapons[shooter_id]:
        if attachment is not selected:
            _exhaust_attachment(attachment)


def _decision(
    session: RuntimeSession,
    shooter_id: str,
) -> TacticalTargetingDecision:
    matches = tuple(
        decision
        for picture in session.context.tactical_targeting.latest_pictures()
        if (decision := picture.decision_for(shooter_id)) is not None
    )
    assert len(matches) == 1
    return matches[0]


def _capture_events(session: RuntimeSession) -> list[Event]:
    events: list[Event] = []
    session.context.event_bus.subscribe(Event, events.append)
    return events


def _assert_one_owner_action(
    *,
    case: _OwnerCase,
    shooter_id: str,
    target_id: str,
    attachment: WeaponAttachment,
    ammunition_id: str,
    ammunition_before: int,
    events: list[Event],
) -> tuple[int, int]:
    ammunition_after = attachment.weapon.ammo_state.available(ammunition_id)
    ammunition_delta = ammunition_before - ammunition_after
    ammo_events = [
        event
        for event in events
        if isinstance(event, AmmoExpendedEvent) and event.unit_id == shooter_id and event.ammo_type == ammunition_id
    ]
    if case.role is WeaponModeledRole.MELEE:
        assert ammunition_delta == 0
        assert ammo_events == []
    else:
        assert ammunition_delta > 0
        assert len(ammo_events) == 1
        assert ammo_events[0].quantity == ammunition_delta

    if case.event_owner == "artillery":
        owner_events = [
            event
            for event in events
            if isinstance(event, ArtilleryFireEvent)
            and event.battery_id == shooter_id
            and event.ammo_type == ammunition_id
        ]
        assert len(owner_events) == 1
        assert owner_events[0].round_count == ammunition_delta
    else:
        owner_events = [
            event
            for event in events
            if isinstance(event, EngagementEvent)
            and event.attacker_id == shooter_id
            and event.target_id == target_id
            and event.weapon_id == case.weapon_id
        ]
        assert len(owner_events) == 1
    return ammunition_delta, len(owner_events)


@pytest.mark.parametrize("case", _OWNER_CASES, ids=lambda case: case.name)
def test_typed_owner_action_is_flag_invariant_and_single_commit(
    case: _OwnerCase,
) -> None:
    """Every excluded/close role retains one exact production owner action."""
    prepared = _prepare(case)
    observations: list[tuple[int, int]] = []
    for standoff_enabled in (True, False):
        session = _build(
            prepared,
            case,
            standoff_enabled=standoff_enabled,
        )
        shooter = _unit(session, case.shooter_type)
        target = _unit(session, case.target_type)
        if case.role is WeaponModeledRole.ANTI_SUBMARINE:
            assert isinstance(target, NavalUnit)
            assert target.domain is Domain.SUBMARINE
            assert target.naval_type is NavalUnitType.SSK
            assert target.is_submarine
        attachment = _attachment(
            session,
            shooter.entity_id,
            role=case.role,
            weapon_id=case.weapon_id,
        )
        _isolate_attachment(session, shooter.entity_id, attachment)
        ammunition = attachment.first_fireable_ammunition()
        assert ammunition is not None
        ammunition_before = attachment.weapon.ammo_state.available(
            ammunition.ammo_id,
        )
        events = _capture_events(session)

        assert session.step() is False

        decision = _decision(session, shooter.entity_id)
        assert decision.authorized_standoff_m == 0.0
        assert not decision.can_hold
        observations.append(
            _assert_one_owner_action(
                case=case,
                shooter_id=shooter.entity_id,
                target_id=target.entity_id,
                attachment=attachment,
                ammunition_id=ammunition.ammo_id,
                ammunition_before=ammunition_before,
                events=events,
            )
        )
    assert observations[0] == observations[1]


@pytest.mark.parametrize(
    ("distance_m", "empty_routed", "expected_owner", "direct_valid"),
    (
        (100.0, False, "artillery", True),
        (1_000.0, False, "artillery", False),
        (100.0, True, "direct", True),
    ),
    ids=("valid-direct", "invalid-direct", "invalid-routed"),
)
def test_mixed_mortar_and_rifle_arbitrate_before_one_action(
    distance_m: float,
    empty_routed: bool,
    expected_owner: str,
    direct_valid: bool,
) -> None:
    """Independent direct/routed lanes produce one deterministic winner."""
    case = _OwnerCase(
        "mixed_mortar_rifle",
        "modern",
        "iraqi_insurgent_mortar_team",
        "t72m",
        WeaponModeledRole.MORTAR_FIRE,
        "2b14_82mm_mortar",
        distance_m,
        event_owner="artillery",
    )
    prepared = _prepare(case)
    session = _build(prepared, case, standoff_enabled=True)
    shooter = _unit(session, case.shooter_type)
    _unit(session, case.target_type)
    mortar = _attachment(
        session,
        shooter.entity_id,
        role=WeaponModeledRole.MORTAR_FIRE,
        weapon_id="2b14_82mm_mortar",
    )
    rifle = next(
        attachment
        for attachment in session.context.unit_weapons[shooter.entity_id]
        if attachment.modeled_role is WeaponModeledRole.ASSAULT_RIFLE
    )
    mortar_ammunition = mortar.first_fireable_ammunition()
    rifle_ammunition = rifle.first_fireable_ammunition()
    assert mortar_ammunition is not None
    assert rifle_ammunition is not None
    if empty_routed:
        _exhaust_attachment(mortar)
    mortar_before = mortar.weapon.ammo_state.available(
        mortar_ammunition.ammo_id,
    )
    rifle_before = rifle.weapon.ammo_state.available(rifle_ammunition.ammo_id)
    events = _capture_events(session)

    assert session.step() is False

    decision = _decision(session, shooter.entity_id)
    assert decision.can_engage is direct_valid
    mortar_delta = mortar_before - mortar.weapon.ammo_state.available(
        mortar_ammunition.ammo_id,
    )
    rifle_delta = rifle_before - rifle.weapon.ammo_state.available(
        rifle_ammunition.ammo_id,
    )
    artillery_events = [
        event for event in events if isinstance(event, ArtilleryFireEvent) and event.battery_id == shooter.entity_id
    ]
    direct_events = [
        event
        for event in events
        if isinstance(event, EngagementEvent)
        and event.attacker_id == shooter.entity_id
        and event.weapon_id == rifle.weapon.weapon_id
    ]
    ammo_events = [
        event for event in events if isinstance(event, AmmoExpendedEvent) and event.unit_id == shooter.entity_id
    ]
    assert len(ammo_events) == 1
    if expected_owner == "artillery":
        assert mortar_delta > 0
        assert rifle_delta == 0
        assert len(artillery_events) == 1
        assert direct_events == []
    else:
        assert mortar_delta == 0
        assert rifle_delta > 0
        assert artillery_events == []
        assert len(direct_events) == 1
    assert len(artillery_events) + len(direct_events) == 1
