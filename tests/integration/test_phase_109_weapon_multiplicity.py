"""Production runtime proofs for Phase 109 composite weapon multiplicity."""

from __future__ import annotations

import copy
from pathlib import Path

import numpy as np
import pytest

from stochastic_warfare.combat.ammunition import (
    AmmoLoader,
    WeaponLoader,
)
from stochastic_warfare.combat.events import (
    AmmoExpendedEvent,
    TorpedoEvent,
)
from stochastic_warfare.core.era import get_era_config
from stochastic_warfare.core.types import Domain, Position, Side
from stochastic_warfare.detection.sensors import SensorLoader
from stochastic_warfare.entities.base import Unit
from stochastic_warfare.entities.loader import UnitLoader
from stochastic_warfare.simulation.battle import (
    BattleManager,
    _route_naval_engagement,
)
from stochastic_warfare.simulation.engine import SimulationEngine
from stochastic_warfare.simulation.equipment_mappings import (
    EQUIPMENT_MAPPING_REGISTRY,
)
from stochastic_warfare.simulation.loadouts import RuntimeLoadoutBuilder
from stochastic_warfare.simulation.scenario import ScenarioLoader


DATA_DIR = Path(__file__).parents[2] / "data"


def _load_ww2_catalogs() -> tuple[
    WeaponLoader,
    AmmoLoader,
    SensorLoader,
    UnitLoader,
]:
    weapon_loader = WeaponLoader(DATA_DIR / "weapons")
    weapon_loader.load_all()
    era_weapon_loader = WeaponLoader(DATA_DIR / "eras" / "ww2" / "weapons")
    era_weapon_loader.load_all()
    weapon_loader._definitions.update(era_weapon_loader._definitions)

    ammo_loader = AmmoLoader(DATA_DIR / "ammunition")
    ammo_loader.load_all()
    era_ammo_loader = AmmoLoader(
        DATA_DIR / "eras" / "ww2" / "ammunition",
    )
    era_ammo_loader.load_all()
    ammo_loader._definitions.update(era_ammo_loader._definitions)

    sensor_loader = SensorLoader(DATA_DIR / "sensors")
    sensor_loader.load_all()
    era_sensor_loader = SensorLoader(DATA_DIR / "eras" / "ww2" / "sensors")
    era_sensor_loader.load_all()
    sensor_loader._definitions.update(era_sensor_loader._definitions)

    unit_loader = UnitLoader(DATA_DIR / "units")
    unit_loader.load_all()
    era_unit_loader = UnitLoader(DATA_DIR / "eras" / "ww2" / "units")
    era_unit_loader.load_all()
    unit_loader._definitions.update(era_unit_loader._definitions)
    return weapon_loader, ammo_loader, sensor_loader, unit_loader


def _attachment_named(loadouts, unit_id: str, equipment_name: str):
    return next(
        attachment
        for attachment in loadouts.unit_weapons[unit_id]
        if attachment.source_equipment.name == equipment_name
    )


def test_iowa_and_essex_bofors_counts_change_live_cadence_and_magazine() -> None:
    weapon_loader, ammo_loader, sensor_loader, unit_loader = _load_ww2_catalogs()
    builder = RuntimeLoadoutBuilder(
        weapon_loader=weapon_loader,
        ammo_loader=ammo_loader,
        sensor_loader=sensor_loader,
        unit_definitions=unit_loader.definitions(),
        era_config=get_era_config("ww2"),
        assignment_overrides=(),
        reachable_unit_types=("iowa_bb", "essex_cv"),
        registry=EQUIPMENT_MAPPING_REGISTRY,
    )
    rng = np.random.default_rng(109)
    iowa = unit_loader.create_unit(
        "iowa_bb",
        "phase109-iowa",
        Position(0.0, 0.0),
        "blue",
        rng,
    )
    essex = unit_loader.create_unit(
        "essex_cv",
        "phase109-essex",
        Position(1_000.0, 0.0),
        "blue",
        rng,
    )

    loadouts = builder.build((iowa, essex))
    iowa_bofors = _attachment_named(
        loadouts,
        iowa.entity_id,
        "Bofors 40mm Quad Mount (x20)",
    )
    essex_bofors = _attachment_named(
        loadouts,
        essex.entity_id,
        "Bofors 40mm Quad Mount (x8)",
    )
    catalog = weapon_loader.get_definition("bofors_40mm_l60")

    assert (
        iowa_bofors.source_system_count,
        iowa_bofors.target_system_count,
        iowa_bofors.runtime_system_multiplier,
    ) == (80, 1, 80)
    assert (
        essex_bofors.source_system_count,
        essex_bofors.target_system_count,
        essex_bofors.runtime_system_multiplier,
    ) == (32, 1, 32)
    assert (
        iowa_bofors.weapon.definition.rate_of_fire_rpm,
        iowa_bofors.weapon.definition.burst_size,
        iowa_bofors.weapon.definition.magazine_capacity,
        iowa_bofors.weapon.definition.barrel_life_rounds,
    ) == (
        catalog.rate_of_fire_rpm * 80,
        catalog.burst_size,
        catalog.magazine_capacity * 80,
        catalog.barrel_life_rounds * 80,
    )
    assert (
        essex_bofors.weapon.definition.rate_of_fire_rpm,
        essex_bofors.weapon.definition.burst_size,
        essex_bofors.weapon.definition.magazine_capacity,
        essex_bofors.weapon.definition.barrel_life_rounds,
    ) == (
        catalog.rate_of_fire_rpm * 32,
        catalog.burst_size,
        catalog.magazine_capacity * 32,
        catalog.barrel_life_rounds * 32,
    )
    assert set(iowa_bofors.weapon.ammo_state.rounds_by_type.values()) == {
        catalog.magazine_capacity * 80,
    }
    assert set(essex_bofors.weapon.ammo_state.rounds_by_type.values()) == {
        catalog.magazine_capacity * 32,
    }

    # Burst semantics remain per target system. Aggregate cadence already
    # scales by barrel count, so multiplying the burst again would make
    # theoretical throughput grow with the square of the multiplier.
    ctx = ScenarioLoader(DATA_DIR).load(
        DATA_DIR / "eras" / "ww2" / "scenarios" / "midway" / "scenario.yaml",
        seed=109,
    )
    ctx.engagement_engine._config.enable_burst_fire = True
    burst_ammo = iowa_bofors.ammunition[0]
    burst_before = iowa_bofors.weapon.ammo_state.available(
        burst_ammo.ammo_id,
    )
    burst_result = ctx.engagement_engine.execute_burst_engagement(
        attacker_id=iowa.entity_id,
        target_id="phase109-burst-target",
        shooter_pos=Position(0.0, 0.0),
        target_pos=Position(1_000.0, 0.0),
        weapon=iowa_bofors.weapon,
        ammo_id=burst_ammo.ammo_id,
        ammo_def=burst_ammo,
        current_time_s=-100.0,
    )
    assert burst_result.engaged
    assert burst_result.rounds_fired == catalog.burst_size == 4
    assert (
        iowa_bofors.weapon.ammo_state.available(burst_ammo.ammo_id)
        == burst_before - catalog.burst_size
    )

    for unit, attachment in (
        (iowa, iowa_bofors),
        (essex, essex_bofors),
    ):
        assert (
            len(
                [
                    candidate
                    for candidate in loadouts.unit_weapons[unit.entity_id]
                    if candidate.source_equipment is attachment.source_equipment
                ],
            )
            == 1
        )

    # Exercise both attachments through the real production battle manager.
    # The routed engagement consumes live ammunition and its suppression
    # engine consumes the scaled rate of fire, producing a controlled outcome
    # difference for the 80- versus 32-barrel batteries.
    targets = [unit for unit in ctx.all_units() if unit.unit_type == "a6m_zero"][:2]
    assert len(targets) == 2
    ctx.cal_flat = {
        **ctx.cal_flat,
        "target_selection_mode": "nearest",
        "visibility_m": 15_000.0,
        "enable_air_routing": False,
        "engagement_concealment_threshold": 1.0,
    }

    def run_production_engagement(
        attacker,
        attachment,
        target,
    ) -> float:
        attacker.position = Position(0.0, 0.0, 0.0)
        target.position = Position(1_000.0, 0.0, 500.0)
        attacker.speed = 0.0
        target.speed = 0.0
        ctx.unit_weapons[attacker.entity_id] = (attachment,)
        ctx.unit_sensors[attacker.entity_id] = loadouts.unit_sensors[attacker.entity_id]
        ctx.units_by_side = {
            "usn": [attacker],
            "ijn": [target],
        }
        ammo_id = attachment.ammunition[0].ammo_id
        before = attachment.weapon.ammo_state.available(ammo_id)
        manager = BattleManager(ctx.event_bus)
        manager._execute_engagements(
            ctx,
            {"usn": [attacker]},
            {"usn": [target]},
            {"usn": np.asarray([[1_000.0, 0.0]], dtype=np.float64)},
            1.0,
            ctx.clock.current_time,
        )
        assert attachment.weapon.ammo_state.available(ammo_id) == before - 1
        return manager._suppression_states[target.entity_id].value

    iowa_suppression = run_production_engagement(
        iowa,
        iowa_bofors,
        targets[0],
    )
    essex_suppression = run_production_engagement(
        essex,
        essex_bofors,
        targets[1],
    )
    assert 0.0 < essex_suppression < iowa_suppression

    # WeaponInstance also consumes the scaled cadence as a shorter live
    # cooldown.
    iowa_bofors.weapon.record_fire(0.0)
    essex_bofors.weapon.record_fire(0.0)
    assert iowa_bofors.weapon.can_fire_timed(0.01)
    assert not essex_bofors.weapon.can_fire_timed(0.01)

    iowa_topology = loadouts.topology()[iowa.entity_id]
    essex_topology = loadouts.topology()[essex.entity_id]
    assert (
        next(row for row in iowa_topology if row["equipment_name"].startswith("Bofors"))["runtime_system_multiplier"]
        == 80
    )
    assert (
        next(row for row in essex_topology if row["equipment_name"].startswith("Bofors"))["runtime_system_multiplier"]
        == 32
    )


def test_iowa_main_battery_count_reaches_naval_gunnery_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The nine authored 16-inch guns must fire as a nine-shell salvo."""
    weapon_loader, ammo_loader, sensor_loader, unit_loader = _load_ww2_catalogs()
    builder = RuntimeLoadoutBuilder(
        weapon_loader=weapon_loader,
        ammo_loader=ammo_loader,
        sensor_loader=sensor_loader,
        unit_definitions=unit_loader.definitions(),
        era_config=get_era_config("ww2"),
        assignment_overrides=(),
        reachable_unit_types=("iowa_bb",),
        registry=EQUIPMENT_MAPPING_REGISTRY,
    )
    ctx = ScenarioLoader(DATA_DIR).load(
        DATA_DIR / "eras" / "ww2" / "scenarios" / "midway" / "scenario.yaml",
        seed=109,
    )
    iowa = unit_loader.create_unit(
        "iowa_bb",
        "phase109-iowa-main-battery",
        Position(0.0, 0.0),
        "usn",
        np.random.default_rng(109),
    )
    loadouts = builder.build((iowa,))
    main_battery = _attachment_named(
        loadouts,
        iowa.entity_id,
        "16-inch/50 Mk 7 Gun (3x3 turrets)",
    )
    target = next(
        unit
        for unit in ctx.all_units()
        if unit.unit_type == "shokaku_cv"
    )
    target.position = Position(10_000.0, 0.0, 0.0)
    target.speed = 0.0
    ctx.unit_weapons[iowa.entity_id] = (main_battery,)
    ctx.unit_sensors[iowa.entity_id] = loadouts.unit_sensors[iowa.entity_id]
    ctx.units_by_side = {"usn": [iowa], "ijn": [target]}
    ctx.cal_flat = {
        **ctx.cal_flat,
        "target_selection_mode": "nearest",
        "visibility_m": 15_000.0,
    }
    salvo_gun_counts: list[int] = []
    original_fire_salvo = ctx.naval_gunnery_engine.fire_salvo

    def record_fire_salvo(*args, **kwargs):
        salvo_gun_counts.append(kwargs["num_guns"])
        return original_fire_salvo(*args, **kwargs)

    monkeypatch.setattr(
        ctx.naval_gunnery_engine,
        "fire_salvo",
        record_fire_salvo,
    )
    ammo_id = main_battery.ammunition[0].ammo_id
    before = main_battery.weapon.ammo_state.available(ammo_id)

    BattleManager(ctx.event_bus)._execute_engagements(
        ctx,
        {"usn": [iowa]},
        {"usn": [target]},
        {
            "usn": np.asarray(
                [(target.position.easting, target.position.northing)],
                dtype=np.float64,
            ),
        },
        5.0,
        ctx.clock.current_time,
    )

    assert main_battery.runtime_system_multiplier == 9
    assert salvo_gun_counts == [9]
    assert main_battery.weapon.ammo_state.available(ammo_id) == before - 9


def test_kilo_tube_count_reaches_subsurface_salvo_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Six authored tubes must create six live torpedo opportunities."""
    ctx = ScenarioLoader(DATA_DIR).load(
        DATA_DIR / "scenarios" / "taiwan_strait" / "scenario.yaml",
        seed=109,
    )
    kilo = next(
        unit for unit in ctx.all_units() if unit.unit_type == "kilo636"
    )
    target = next(
        unit for unit in ctx.all_units() if unit.unit_type == "ddg51"
    )
    kilo.position = Position(0.0, 0.0, 0.0)
    kilo.speed = 0.0
    kilo.heading = np.pi / 2.0
    target.position = Position(1_000.0, 0.0, 0.0)
    target.speed = 0.0
    torpedo_tubes = next(
        attachment
        for attachment in ctx.unit_weapons[kilo.entity_id]
        if attachment.source_equipment.name == "533mm Torpedo Tubes x6"
    )
    ctx.unit_weapons[kilo.entity_id] = (torpedo_tubes,)
    ctx.units_by_side = {"red": [kilo], "blue": [target]}
    ctx.cal_flat = {
        **ctx.cal_flat,
        "target_selection_mode": "nearest",
    }
    torpedo_calls: list[str] = []
    original_torpedo_engagement = (
        ctx.naval_subsurface_engine.torpedo_engagement
    )

    def record_torpedo_engagement(*args, **kwargs):
        torpedo_calls.append(kwargs["target_id"])
        return original_torpedo_engagement(*args, **kwargs)

    monkeypatch.setattr(
        ctx.naval_subsurface_engine,
        "torpedo_engagement",
        record_torpedo_engagement,
    )
    expenditure_events: list[AmmoExpendedEvent] = []
    torpedo_events: list[TorpedoEvent] = []
    ctx.event_bus.subscribe(AmmoExpendedEvent, expenditure_events.append)
    ctx.event_bus.subscribe(TorpedoEvent, torpedo_events.append)
    ammo_id = torpedo_tubes.ammunition[0].ammo_id
    before = torpedo_tubes.weapon.ammo_state.available(ammo_id)

    BattleManager(ctx.event_bus)._execute_engagements(
        ctx,
        {"red": [kilo]},
        {"red": [target]},
        {
            "red": np.asarray(
                [(target.position.easting, target.position.northing)],
                dtype=np.float64,
            ),
        },
        5.0,
        ctx.clock.current_time,
    )

    assert torpedo_tubes.runtime_system_multiplier == 6
    assert torpedo_calls == [target.entity_id] * 6
    assert (
        torpedo_tubes.weapon.ammo_state.available(ammo_id)
        == before - 6
    )
    assert [
        (event.unit_id, event.ammo_type, event.quantity)
        for event in expenditure_events
    ] == [(kilo.entity_id, ammo_id, 6)]
    assert len(torpedo_events) == 6


def test_flower_depth_charge_count_preserves_live_multitick_cadence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Four throwers fire four charges per base-system cadence interval."""
    weapon_loader, ammo_loader, sensor_loader, unit_loader = _load_ww2_catalogs()
    builder = RuntimeLoadoutBuilder(
        weapon_loader=weapon_loader,
        ammo_loader=ammo_loader,
        sensor_loader=sensor_loader,
        unit_definitions=unit_loader.definitions(),
        era_config=get_era_config("ww2"),
        assignment_overrides=(),
        reachable_unit_types=("flower_corvette", "type_ixc_uboat"),
        registry=EQUIPMENT_MAPPING_REGISTRY,
    )
    rng = np.random.default_rng(109)
    flower = unit_loader.create_unit(
        "flower_corvette",
        "phase109-flower",
        Position(0.0, 0.0),
        "blue",
        rng,
    )
    submarine = unit_loader.create_unit(
        "type_ixc_uboat",
        "phase109-uboat",
        Position(100.0, 0.0),
        "red",
        rng,
    )
    loadouts = builder.build((flower, submarine))
    depth_charges = _attachment_named(
        loadouts,
        flower.entity_id,
        "Depth Charge Rails and Throwers (x4)",
    )
    ctx = ScenarioLoader(DATA_DIR).load(
        DATA_DIR / "eras" / "ww2" / "scenarios" / "midway"
        / "scenario.yaml",
        seed=109,
    )
    engine_calls: list[int] = []
    original_attack = ctx.naval_subsurface_engine.depth_charge_attack

    def record_depth_charge_attack(*args, **kwargs):
        engine_calls.append(kwargs["num_charges"])
        return original_attack(*args, **kwargs)

    monkeypatch.setattr(
        ctx.naval_subsurface_engine,
        "depth_charge_attack",
        record_depth_charge_attack,
    )
    expenditure_events: list[AmmoExpendedEvent] = []
    ctx.event_bus.subscribe(AmmoExpendedEvent, expenditure_events.append)
    ammo = depth_charges.ammunition[0]
    before = depth_charges.weapon.ammo_state.available(ammo.ammo_id)

    for current_time_s in (0.0, 2.5, 9.999, 10.0, 12.5, 20.0):
        handled, _status = _route_naval_engagement(
            ctx,
            flower,
            submarine,
            depth_charges.weapon,
            100.0,
            2.5,
            ctx.clock.current_time,
            ammo_def=ammo,
            current_time_s=current_time_s,
            runtime_system_multiplier=(
                depth_charges.runtime_system_multiplier
            ),
        )
        assert handled is True

    assert depth_charges.runtime_system_multiplier == 4
    assert engine_calls == [4, 4, 4]
    assert (
        depth_charges.weapon.ammo_state.available(ammo.ammo_id)
        == before - 12
    )
    assert [event.quantity for event in expenditure_events] == [4, 4, 4]


def test_harpoon_battery_rate_is_cadence_not_salvo_quantity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A two-rpm aggregate battery launches one missile every 30 seconds."""
    ctx = ScenarioLoader(DATA_DIR).load(
        DATA_DIR / "scenarios" / "ins_hanit_2006" / "scenario.yaml",
        seed=109,
    )
    attacker = next(
        unit for unit in ctx.all_units() if unit.unit_type == "idf_saar5"
    )
    target = Unit(
        entity_id="phase109-naval-target",
        position=Position(1_000.0, 0.0),
        name="Phase 109 naval target",
        unit_type="phase109_target",
        side=Side.RED,
        domain=Domain.NAVAL,
    )
    harpoon = _attachment_named(
        ctx,
        attacker.entity_id,
        "Harpoon Quad Launchers (x2)",
    )
    engine_calls: list[int] = []
    original_exchange = ctx.naval_surface_engine.salvo_exchange

    def record_salvo_exchange(*args, **kwargs):
        engine_calls.append(kwargs["attacker_missiles"])
        return original_exchange(*args, **kwargs)

    monkeypatch.setattr(
        ctx.naval_surface_engine,
        "salvo_exchange",
        record_salvo_exchange,
    )
    expenditure_events: list[AmmoExpendedEvent] = []
    ctx.event_bus.subscribe(AmmoExpendedEvent, expenditure_events.append)
    ammo = harpoon.ammunition[0]
    before = harpoon.weapon.ammo_state.available(ammo.ammo_id)
    vls_launches: dict[str, int] = {}

    for current_time_s in (0.0, 15.0, 29.999, 30.0, 45.0, 60.0):
        handled, _status = _route_naval_engagement(
            ctx,
            attacker,
            target,
            harpoon.weapon,
            1_000.0,
            15.0,
            ctx.clock.current_time,
            vls_launches=vls_launches,
            ammo_def=ammo,
            current_time_s=current_time_s,
            runtime_system_multiplier=harpoon.runtime_system_multiplier,
        )
        assert handled is True

    assert harpoon.runtime_system_multiplier == 1
    assert engine_calls == [1, 1, 1]
    assert harpoon.weapon.ammo_state.available(ammo.ammo_id) == before - 3
    assert vls_launches == {attacker.entity_id: 3}
    assert [event.quantity for event in expenditure_events] == [1, 1, 1]


def test_jutland_fallback_gunnery_preserves_ten_gun_cadence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WWI fallback gunnery fires the physical battery at base-gun cadence."""
    ctx = ScenarioLoader(DATA_DIR).load(
        DATA_DIR / "eras" / "ww1" / "scenarios" / "jutland"
        / "scenario.yaml",
        seed=109,
    )
    attacker = next(
        unit for unit in ctx.all_units() if unit.unit_type == "iron_duke_bb"
    )
    target = next(
        unit
        for unit in ctx.all_units()
        if unit.side != attacker.side and unit.domain is Domain.NAVAL
    )
    main_battery = _attachment_named(
        ctx,
        attacker.entity_id,
        "BL 13.5-inch Mk V Gun (5x2 turrets)",
    )
    assert ctx.naval_gunnery_engine is None
    round_counts: list[int] = []
    original_engagement = ctx.naval_surface_engine.naval_gun_engagement

    def record_naval_gun_engagement(*args, **kwargs):
        round_counts.append(kwargs["rounds_fired"])
        return original_engagement(*args, **kwargs)

    monkeypatch.setattr(
        ctx.naval_surface_engine,
        "naval_gun_engagement",
        record_naval_gun_engagement,
    )
    expenditure_events: list[AmmoExpendedEvent] = []
    ctx.event_bus.subscribe(AmmoExpendedEvent, expenditure_events.append)
    ammo = main_battery.ammunition[0]
    before = main_battery.weapon.ammo_state.available(ammo.ammo_id)

    for current_time_s in range(0, 60, 5):
        handled, _status = _route_naval_engagement(
            ctx,
            attacker,
            target,
            main_battery.weapon,
            10_000.0,
            5.0,
            ctx.clock.current_time,
            ammo_def=ammo,
            current_time_s=float(current_time_s),
            runtime_system_multiplier=(
                main_battery.runtime_system_multiplier
            ),
        )
        assert handled is True

    assert main_battery.runtime_system_multiplier == 10
    assert round_counts == [10, 10]
    assert (
        main_battery.weapon.ammo_state.available(ammo.ammo_id)
        == before - 20
    )
    assert [event.quantity for event in expenditure_events] == [10, 10]


def test_iowa_shore_bombardment_preserves_nine_gun_cadence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """NGFS dispatch fires the physical battery at base-gun cadence."""
    weapon_loader, ammo_loader, sensor_loader, unit_loader = _load_ww2_catalogs()
    builder = RuntimeLoadoutBuilder(
        weapon_loader=weapon_loader,
        ammo_loader=ammo_loader,
        sensor_loader=sensor_loader,
        unit_definitions=unit_loader.definitions(),
        era_config=get_era_config("ww2"),
        assignment_overrides=(),
        reachable_unit_types=("iowa_bb",),
        registry=EQUIPMENT_MAPPING_REGISTRY,
    )
    attacker = unit_loader.create_unit(
        "iowa_bb",
        "phase109-iowa-shore",
        Position(0.0, 0.0),
        "blue",
        np.random.default_rng(109),
    )
    loadouts = builder.build((attacker,))
    ctx = ScenarioLoader(DATA_DIR).load(
        DATA_DIR / "eras" / "ww2" / "scenarios" / "midway"
        / "scenario.yaml",
        seed=109,
    )
    target = Unit(
        entity_id="phase109-shore-target",
        position=Position(10_000.0, 0.0),
        name="Phase 109 shore target",
        unit_type="phase109_shore_target",
        side=Side.RED,
        domain=Domain.GROUND,
    )
    main_battery = _attachment_named(
        loadouts,
        attacker.entity_id,
        "16-inch/50 Mk 7 Gun (3x3 turrets)",
    )
    round_counts: list[int] = []
    original_bombardment = (
        ctx.naval_gunfire_support_engine.shore_bombardment
    )

    def record_shore_bombardment(*args, **kwargs):
        round_counts.append(kwargs["round_count"])
        return original_bombardment(*args, **kwargs)

    monkeypatch.setattr(
        ctx.naval_gunfire_support_engine,
        "shore_bombardment",
        record_shore_bombardment,
    )
    expenditure_events: list[AmmoExpendedEvent] = []
    ctx.event_bus.subscribe(AmmoExpendedEvent, expenditure_events.append)
    ammo = main_battery.ammunition[0]
    before = main_battery.weapon.ammo_state.available(ammo.ammo_id)

    for current_time_s in range(0, 60, 5):
        handled, _status = _route_naval_engagement(
            ctx,
            attacker,
            target,
            main_battery.weapon,
            10_000.0,
            5.0,
            ctx.clock.current_time,
            ammo_def=ammo,
            current_time_s=float(current_time_s),
            runtime_system_multiplier=(
                main_battery.runtime_system_multiplier
            ),
        )
        assert handled is True

    assert main_battery.runtime_system_multiplier == 9
    assert round_counts == [9, 9]
    assert (
        main_battery.weapon.ammo_state.available(ammo.ammo_id)
        == before - 18
    )
    assert [event.quantity for event in expenditure_events] == [9, 9]


def test_checkpoint_preserves_and_rejects_composite_count_topology() -> None:
    scenario_path = DATA_DIR / "eras" / "ww2" / "scenarios" / "midway" / "scenario.yaml"
    control_ctx = ScenarioLoader(DATA_DIR).load(scenario_path, seed=109)
    control = SimulationEngine(control_ctx)
    unit_id, control_attachment = next(
        (unit_id, attachment)
        for unit_id, attachments in control_ctx.unit_weapons.items()
        for attachment in attachments
        if attachment.source_equipment.name == "Bofors 40mm Quad Mount (x8)"
    )
    checkpoint = control.checkpoint()

    resumed_ctx = ScenarioLoader(DATA_DIR).load(scenario_path, seed=109)
    resumed = SimulationEngine(resumed_ctx)
    resumed.restore(checkpoint)
    resumed_attachment = _attachment_named(
        resumed_ctx,
        unit_id,
        "Bofors 40mm Quad Mount (x8)",
    )
    assert (
        (
            resumed_attachment.source_system_count,
            resumed_attachment.target_system_count,
            resumed_attachment.runtime_system_multiplier,
        )
        == (
            control_attachment.source_system_count,
            control_attachment.target_system_count,
            control_attachment.runtime_system_multiplier,
        )
        == (32, 1, 32)
    )
    assert resumed_ctx.get_state()["loadout_topology"] == control_ctx.get_state()["loadout_topology"]

    invalid = copy.deepcopy(control.get_state())
    resolution = next(
        row
        for row in invalid["context"]["loadout_topology"][unit_id]
        if row["equipment_name"] == "Bofors 40mm Quad Mount (x8)"
    )
    resolution["source_system_count"] = 31
    before = control.checkpoint()
    with pytest.raises(
        ValueError,
        match="loadout resolution topology",
    ):
        control.set_state(invalid)
    assert control.checkpoint() == before
