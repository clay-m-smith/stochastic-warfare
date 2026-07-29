"""Production consumption proof for Phase 109 multi-ammunition mappings."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from stochastic_warfare.combat.events import (
    AmmoExpendedEvent,
    EngagementEvent,
)
from stochastic_warfare.core.types import Position
from stochastic_warfare.simulation.battle import BattleManager
from stochastic_warfare.simulation.scenario import ScenarioLoader


DATA_DIR = Path("data")
KURSK_SCENARIO = DATA_DIR / "eras/ww2/scenarios/kursk/scenario.yaml"
MIDWAY_SCENARIO = DATA_DIR / "eras/ww2/scenarios/midway/scenario.yaml"
SUWALKI_SCENARIO = DATA_DIR / "scenarios/suwalki_gap/scenario.yaml"


def test_battle_consumes_second_declared_ammunition_after_first_depletes() -> None:
    """A live PaK/KwK-style two-type loadout must not stop at entry zero."""
    ctx = ScenarioLoader(DATA_DIR).load(KURSK_SCENARIO, seed=109)
    attacker = next(
        unit for unit in ctx.all_units() if unit.unit_type == "panzer_iv_h"
    )
    target = next(
        unit for unit in ctx.all_units() if unit.unit_type == "t34_85"
    )
    attacker.position = Position(0.0, 0.0, 0.0)
    target.position = Position(300.0, 0.0, 0.0)
    attacker.speed = 0.0
    target.speed = 0.0
    ctx.units_by_side = {"german": [attacker], "soviet": [target]}
    ctx.calibration = ctx.calibration.model_copy(
        update={
            "enable_ammo_gate": True,
            "target_selection_mode": "nearest",
            "visibility_m": 5_000.0,
        },
    )
    ctx.cal_flat = {
        **ctx.cal_flat,
        "enable_ammo_gate": True,
        "target_selection_mode": "nearest",
        "visibility_m": 5_000.0,
    }

    attachment = next(
        item
        for item in ctx.unit_weapons[attacker.entity_id]
        if item.weapon.weapon_id == "kwk40_l48_75mm"
    )
    first_ammo, second_ammo = attachment.ammunition
    attachment.weapon.ammo_state.rounds_by_type[first_ammo.ammo_id] = 0
    second_before = attachment.weapon.ammo_state.available(
        second_ammo.ammo_id,
    )
    ctx.unit_weapons[attacker.entity_id] = (attachment,)

    battle = BattleManager(ctx.event_bus)
    first_key = (
        f"{attacker.entity_id}:{attachment.weapon.weapon_id}:"
        f"{first_ammo.ammo_id}"
    )
    battle._ammo_expended[first_key] = (
        attachment.weapon.definition.magazine_capacity
    )
    events: list[EngagementEvent] = []
    ctx.event_bus.subscribe(EngagementEvent, events.append)

    battle._execute_engagements(
        ctx,
        {"german": [attacker]},
        {"german": [target]},
        {"german": np.asarray([(300.0, 0.0)], dtype=np.float64)},
        1.0,
        ctx.clock.current_time,
    )

    assert [
        (event.weapon_id, event.ammo_type)
        for event in events
    ] == [(attachment.weapon.weapon_id, second_ammo.ammo_id)]
    assert attachment.weapon.ammo_state.available(second_ammo.ammo_id) == (
        second_before - 1
    )
    second_key = (
        f"{attacker.entity_id}:{attachment.weapon.weapon_id}:"
        f"{second_ammo.ammo_id}"
    )
    assert battle._ammo_expended[second_key] == 1


def test_naval_route_consumes_and_exposes_selected_second_ammunition() -> None:
    """A real Fletcher gunnery route must fire the selected AP, not empty HE."""
    ctx = ScenarioLoader(DATA_DIR).load(MIDWAY_SCENARIO, seed=109)
    attacker = next(
        unit
        for unit in ctx.units_by_side["usn"]
        if unit.unit_type == "fletcher_dd"
    )
    target = next(
        unit
        for unit in ctx.units_by_side["ijn"]
        if unit.unit_type == "fletcher_dd"
    )
    attacker.position = Position(0.0, 0.0, 0.0)
    target.position = Position(1_000.0, 0.0, 0.0)
    attacker.speed = 0.0
    target.speed = 0.0
    ctx.units_by_side = {"usn": [attacker], "ijn": [target]}
    ctx.calibration = ctx.calibration.model_copy(
        update={
            "enable_ammo_gate": True,
            "target_selection_mode": "nearest",
            "visibility_m": 5_000.0,
        },
    )
    ctx.cal_flat = {
        **ctx.cal_flat,
        "enable_ammo_gate": True,
        "target_selection_mode": "nearest",
        "visibility_m": 5_000.0,
    }

    attachment = next(
        item
        for item in ctx.unit_weapons[attacker.entity_id]
        if item.weapon.weapon_id == "5in38_naval"
    )
    empty_he, selected_ap = attachment.ammunition
    attachment.weapon.ammo_state.rounds_by_type[empty_he.ammo_id] = 0
    ap_before = attachment.weapon.ammo_state.available(selected_ap.ammo_id)
    ctx.unit_weapons[attacker.entity_id] = (attachment,)

    battle = BattleManager(ctx.event_bus)
    engagements: list[EngagementEvent] = []
    expenditures: list[AmmoExpendedEvent] = []
    ctx.event_bus.subscribe(EngagementEvent, engagements.append)
    ctx.event_bus.subscribe(AmmoExpendedEvent, expenditures.append)

    battle._execute_engagements(
        ctx,
        {"usn": [attacker]},
        {"usn": [target]},
        {"usn": np.asarray([(1_000.0, 0.0)], dtype=np.float64)},
        1.0,
        ctx.clock.current_time,
    )

    assert [
        (event.weapon_id, event.ammo_type)
        for event in engagements
    ] == [(attachment.weapon.weapon_id, selected_ap.ammo_id)]
    assert [
        (event.ammo_type, event.quantity)
        for event in expenditures
    ] == [(
        selected_ap.ammo_id,
        attachment.runtime_system_multiplier,
    )]
    assert attachment.runtime_system_multiplier == 5
    assert attachment.weapon.ammo_state.available(empty_he.ammo_id) == 0
    assert attachment.weapon.ammo_state.available(selected_ap.ammo_id) == (
        ap_before - attachment.runtime_system_multiplier
    )
    assert battle._ammo_expended[
        f"{attacker.entity_id}:{attachment.weapon.weapon_id}:"
        f"{selected_ap.ammo_id}"
    ] == attachment.runtime_system_multiplier


def test_air_route_consumes_and_exposes_selected_live_missile() -> None:
    """The loaded F-16/Su-27 air route must consume its selected AMRAAM."""
    ctx = ScenarioLoader(DATA_DIR).load(SUWALKI_SCENARIO, seed=109)
    attacker = next(
        unit
        for unit in ctx.units_by_side["blue"]
        if unit.unit_type == "f16c"
    )
    target = next(
        unit
        for unit in ctx.units_by_side["red"]
        if unit.unit_type == "su27s"
    )
    attacker.position = Position(0.0, 0.0, 5_000.0)
    target.position = Position(5_000.0, 0.0, 5_000.0)
    attacker.speed = 0.0
    target.speed = 0.0
    ctx.units_by_side = {"blue": [attacker], "red": [target]}
    ctx.calibration = ctx.calibration.model_copy(
        update={
            "enable_air_routing": True,
            "enable_ammo_gate": True,
            "target_selection_mode": "nearest",
            "visibility_m": 10_000.0,
        },
    )
    ctx.cal_flat = {
        **ctx.cal_flat,
        "enable_air_routing": True,
        "enable_ammo_gate": True,
        "target_selection_mode": "nearest",
        "visibility_m": 10_000.0,
    }

    attachment = next(
        item
        for item in ctx.unit_weapons[attacker.entity_id]
        if item.weapon.weapon_id == "aim120_amraam"
    )
    selected_ammo = attachment.ammunition[0]
    ammo_before = attachment.weapon.ammo_state.available(
        selected_ammo.ammo_id,
    )
    ctx.unit_weapons[attacker.entity_id] = (attachment,)

    battle = BattleManager(ctx.event_bus)
    engagements: list[EngagementEvent] = []
    expenditures: list[AmmoExpendedEvent] = []
    ctx.event_bus.subscribe(EngagementEvent, engagements.append)
    ctx.event_bus.subscribe(AmmoExpendedEvent, expenditures.append)

    battle._execute_engagements(
        ctx,
        {"blue": [attacker]},
        {"blue": [target]},
        {"blue": np.asarray([(5_000.0, 0.0)], dtype=np.float64)},
        1.0,
        ctx.clock.current_time,
    )

    assert [
        (event.weapon_id, event.ammo_type)
        for event in engagements
    ] == [(attachment.weapon.weapon_id, selected_ammo.ammo_id)]
    assert [
        (event.ammo_type, event.quantity)
        for event in expenditures
    ] == [(selected_ammo.ammo_id, 1)]
    assert attachment.weapon.ammo_state.available(selected_ammo.ammo_id) == (
        ammo_before - 1
    )
    assert battle._ammo_expended[
        f"{attacker.entity_id}:{attachment.weapon.weapon_id}:"
        f"{selected_ammo.ammo_id}"
    ] == 1
