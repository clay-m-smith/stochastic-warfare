"""Behavioral checkpoint integrity tests for Phase 105."""

from __future__ import annotations

import copy
import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.combat.ammunition import (
    AmmoState,
    WeaponDefinition,
    WeaponInstance,
)
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.detection.sensors import SensorDefinition, SensorInstance
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.entities.equipment import EquipmentCategory, EquipmentItem
from stochastic_warfare.entities.personnel import (
    CrewMember,
    CrewRole,
    InjuryState,
    SkillLevel,
)
from stochastic_warfare.entities.unit_classes.aerial import AerialUnit
from stochastic_warfare.entities.unit_classes.air_defense import AirDefenseUnit
from stochastic_warfare.entities.unit_classes.ground import (
    GroundUnit,
    GroundUnitType,
    Posture,
)
from stochastic_warfare.entities.unit_classes.naval import NavalUnit
from stochastic_warfare.entities.unit_classes.support import SupportUnit
from stochastic_warfare.morale.rout import RoutEngine
from stochastic_warfare.morale.runtime import MoraleRegistration, MoraleRuntime
from stochastic_warfare.morale.state import MoraleState
from stochastic_warfare.simulation.campaign import CampaignConfig
from stochastic_warfare.simulation.engine import SimulationEngine, TickResolution
from stochastic_warfare.simulation.recorder import SimulationRecorder
from stochastic_warfare.simulation.scenario import (
    CampaignScenarioConfig,
    SideConfig,
    ScenarioLoader,
    SimulationContext,
    TerrainConfig,
)

from tests.conftest import TS


def _config() -> CampaignScenarioConfig:
    return CampaignScenarioConfig(
        name="Phase 105 checkpoint test",
        date="2024-06-15",
        duration_hours=24.0,
        terrain=TerrainConfig(width_m=200_000, height_m=200_000),
        sides=[
            SideConfig(side="blue", units=[]),
            SideConfig(side="red", units=[]),
        ],
    )


def _context(
    units_by_side: dict[str, list[Unit]] | None = None,
    morale_states: dict[str, MoraleState] | None = None,
    *,
    seed: int = 105,
) -> SimulationContext:
    force = (
        units_by_side
        if units_by_side is not None
        else {"blue": [], "red": []}
    )
    ordered_units = [
        unit
        for side_units in force.values()
        for unit in side_units
    ]
    units = {unit.entity_id: unit for unit in ordered_units}
    if len(units) != len(ordered_units):
        raise ValueError("Test force fixture contains duplicate unit IDs")
    initial_morale = (
        morale_states
        if morale_states is not None
        else {unit_id: MoraleState.STEADY for unit_id in units}
    )
    if set(initial_morale) != set(units):
        raise ValueError("Test morale fixture must exactly match the roster")
    for unit_id, state in initial_morale.items():
        if state is MoraleState.ROUTED:
            units[unit_id].status = UnitStatus.ROUTING
        elif state is MoraleState.SURRENDERED:
            units[unit_id].status = UnitStatus.SURRENDERED
        else:
            units[unit_id].status = UnitStatus.ACTIVE

    rng_manager = RNGManager(seed)
    event_bus = EventBus()
    morale_rng = rng_manager.get_stream(ModuleId.MORALE)
    rout_engine = RoutEngine(event_bus, morale_rng)
    morale_runtime = MoraleRuntime(
        event_bus,
        morale_rng,
        rout_engine=rout_engine,
    )
    morale_runtime.register_units(
        tuple(
            MoraleRegistration(unit_id, initial_morale[unit_id])
            for unit_id in units
        ),
        units,
    )
    return SimulationContext(
        config=_config(),
        clock=SimulationClock(start=TS, tick_duration=timedelta(hours=1)),
        rng_manager=rng_manager,
        event_bus=event_bus,
        units_by_side=force,
        morale_runtime=morale_runtime,
        rout_engine=rout_engine,
    )


def _as_versionless_legacy_context(
    checkpoint: dict[str, Any],
) -> dict[str, Any]:
    """Translate an idle current context into the bounded legacy envelope."""
    legacy = copy.deepcopy(checkpoint)
    runtime_state = legacy.pop("morale_runtime")
    assert runtime_state["suspended_archives"] == {}
    records = runtime_state["active_records"]
    morale_rng = copy.deepcopy(
        legacy["rng"]["streams"][ModuleId.MORALE.value],
    )
    legacy["morale_states"] = {
        unit_id: record["current_state"]
        for unit_id, record in records.items()
    }
    legacy["morale_machine"] = {
        "unit_states": {
            unit_id: {
                "current_state": record["current_state"],
                "transition_cooldown_s": 0.0,
                "last_transition_time": (
                    -1e9
                    if record["last_transition_time_s"] is None
                    else record["last_transition_time_s"]
                ),
            }
            for unit_id, record in records.items()
        },
        "rng_state": morale_rng,
    }
    rout_state = legacy.get("rout_engine")
    if rout_state is not None:
        rout_state["rng_state"] = copy.deepcopy(morale_rng)
    return legacy


def _ground(
    entity_id: str,
    side: str,
    position: Position,
    *,
    max_speed: float = 0.0,
) -> GroundUnit:
    return GroundUnit(
        entity_id=entity_id,
        position=position,
        name=entity_id,
        unit_type="test_ground",
        side=side,
        max_speed=max_speed,
        ground_type=GroundUnitType.ARMOR,
        posture=Posture.DUG_IN,
        fuel_remaining=0.63,
    )


def _unit_ids(ctx: SimulationContext) -> dict[str, list[str]]:
    return {
        side: [unit.entity_id for unit in units]
        for side, units in ctx.units_by_side.items()
    }


def _loadout(
    weapon_equipment: EquipmentItem,
    sensor_equipment: EquipmentItem,
) -> tuple[WeaponInstance, SensorInstance]:
    weapon = WeaponInstance(
        definition=WeaponDefinition(
            weapon_id="test_gun",
            display_name="Test Gun",
            category="CANNON",
            caliber_mm=30.0,
            compatible_ammo=["test_round"],
            barrel_life_rounds=100,
            rate_of_fire_rpm=60.0,
        ),
        ammo_state=AmmoState(rounds_by_type={"test_round": 10}),
        equipment=weapon_equipment,
    )
    sensor = SensorInstance(
        SensorDefinition(
            sensor_id="test_sensor",
            sensor_type="VISUAL",
            display_name="Test Sensor",
            max_range_m=10_000,
            detection_threshold=1.0,
        ),
        sensor_equipment,
    )
    return weapon, sensor


def test_in_place_restore_preserves_nested_references_and_typed_morale() -> None:
    crew = CrewMember(
        member_id="crew-1",
        role=CrewRole.COMMANDER,
        skill=SkillLevel.VETERAN,
        experience=0.8,
        injury=InjuryState.MINOR_WOUND,
        fatigue=0.35,
    )
    equipment = EquipmentItem(
        equipment_id="gun-1",
        name="Test Gun",
        category=EquipmentCategory.WEAPON,
        condition=0.72,
        operational=True,
    )
    sensor_equipment = EquipmentItem(
        equipment_id="sensor-1",
        name="Test Sensor",
        category=EquipmentCategory.SENSOR,
        condition=0.81,
        operational=True,
    )
    unit = _ground("blue-1", "blue", Position(100, 200, 0))
    unit.personnel = [crew]
    unit.equipment = [equipment, sensor_equipment]
    weapon, sensor = _loadout(equipment, sensor_equipment)
    assert weapon.fire("test_round", 3)
    weapon.record_fire(120.0)
    ctx = _context(
        {"blue": [unit], "red": []},
        {"blue-1": MoraleState.BROKEN},
    )
    ctx.unit_weapons = {"blue-1": [(weapon, [])]}
    ctx.unit_sensors = {"blue-1": [sensor]}
    checkpoint = copy.deepcopy(ctx.get_state())

    unit.position = Position(900, 900, 0)
    unit.status = UnitStatus.DESTROYED
    unit.posture = Posture.MOVING
    unit.fuel_remaining = 0.02
    crew.injury = InjuryState.KIA
    crew.fatigue = 1.0
    assert weapon.fire("test_round", 2)
    weapon.record_fire(500.0)
    equipment.condition = 0.01
    equipment.operational = False
    sensor_equipment.condition = 0.02
    sensor_equipment.operational = False
    assert ctx.morale_runtime is not None
    mutated_morale = copy.deepcopy(ctx.morale_runtime.get_state())
    mutated_morale["active_records"]["blue-1"]["current_state"] = int(
        MoraleState.SURRENDERED,
    )
    ctx.morale_runtime.set_state(
        mutated_morale,
        expected_units={"blue-1": unit},
        elapsed_time_s=ctx.clock.elapsed.total_seconds(),
    )
    morale_view = ctx.morale_states
    morale_runtime = ctx.morale_runtime

    ctx.set_state(checkpoint)

    restored = ctx.units_by_side["blue"][0]
    assert restored is unit
    assert restored.personnel[0] is crew
    assert restored.equipment[0] is equipment
    assert restored.equipment[1] is sensor_equipment
    assert weapon.equipment is restored.equipment[0]
    assert sensor.equipment is restored.equipment[1]
    assert weapon.ammo_state.available("test_round") == 7
    assert weapon._rounds_since_maintenance == 3
    assert weapon._last_fire_time_s == 120.0
    assert sensor.equipment.condition == 0.81
    assert sensor.equipment.operational is True
    assert restored.get_state() == checkpoint["units_by_side"]["blue"][0]
    assert ctx.morale_runtime is morale_runtime
    assert ctx.morale_states is morale_view
    assert ctx.morale_states == {"blue-1": MoraleState.BROKEN}
    assert type(ctx.morale_states["blue-1"]) is MoraleState


def test_fresh_restore_rebuilds_exact_order_and_all_concrete_classes() -> None:
    classes = [
        Unit,
        GroundUnit,
        AerialUnit,
        NavalUnit,
        AirDefenseUnit,
        SupportUnit,
    ]
    source_units = [
        cls(
            entity_id=f"u-{index}",
            position=Position(index * 10, index * 20, 0),
            side="blue" if index % 2 == 0 else "red",
        )
        for index, cls in enumerate(classes)
    ]
    source = _context(
        {
            "red": [source_units[5], source_units[3], source_units[1]],
            "blue": [source_units[4], source_units[2], source_units[0]],
        },
        {unit.entity_id: MoraleState(index % len(MoraleState))
         for index, unit in enumerate(source_units)},
    )
    checkpoint = copy.deepcopy(source.get_state())
    target = _context(
        {"blue": [Unit("stale", Position(1, 1, 0))], "green": []},
        {"stale": MoraleState.STEADY},
        seed=999,
    )

    target.set_state(checkpoint)

    assert list(target.units_by_side) == ["red", "blue"]
    assert _unit_ids(target) == {
        "red": ["u-5", "u-3", "u-1"],
        "blue": ["u-4", "u-2", "u-0"],
    }
    assert {
        unit.entity_id: type(unit)
        for unit in target.all_units()
    } == {
        unit.entity_id: type(unit)
        for unit in source.all_units()
    }
    assert target.get_state()["units_by_side"] == checkpoint["units_by_side"]
    assert target.rng_manager.get_state() == checkpoint["rng"]

    target.set_state(checkpoint)
    assert target.get_state()["units_by_side"] == checkpoint["units_by_side"]


def test_fresh_restore_preserves_checkpoint_only_empty_loadout_entries() -> None:
    unit = Unit("unarmed", Position(10, 20, 0), side="blue")
    source = _context({"blue": [unit], "red": []})
    source.unit_weapons = {"unarmed": ()}
    source.unit_sensors = {"unarmed": ()}
    checkpoint = copy.deepcopy(source.get_state())
    target = _context(seed=999)

    target.set_state(checkpoint)

    assert _unit_ids(target) == {"blue": ["unarmed"], "red": []}
    assert target.unit_weapons == {"unarmed": ()}
    assert target.unit_sensors == {"unarmed": ()}
    assert target.get_state() == checkpoint

    target.set_state(checkpoint)
    assert target.get_state() == checkpoint


def test_restore_rejects_nonreusable_same_id_unit_atomically() -> None:
    source_unit = Unit("unarmed", Position(10, 20, 0), side="blue")
    source = _context({"blue": [source_unit], "red": []})
    source.unit_weapons = {"unarmed": ()}
    source.unit_sensors = {"unarmed": ()}
    checkpoint = copy.deepcopy(source.get_state())

    weapon_equipment = EquipmentItem(
        equipment_id="stale-weapon",
        name="Stale Gun",
        category=EquipmentCategory.WEAPON,
    )
    sensor_equipment = EquipmentItem(
        equipment_id="stale-sensor",
        name="Stale Sensor",
        category=EquipmentCategory.SENSOR,
    )
    stale = _ground("unarmed", "blue", Position(0, 0, 0))
    stale.equipment = [weapon_equipment, sensor_equipment]
    weapon, sensor = _loadout(weapon_equipment, sensor_equipment)
    target = _context({"blue": [stale], "red": []}, seed=999)
    target.unit_weapons = {"unarmed": [(weapon, [])]}
    target.unit_sensors = {"unarmed": [sensor]}
    before = copy.deepcopy(target.get_state())

    with pytest.raises(ValueError, match="unit identity topology"):
        target.set_state(checkpoint)

    assert target.units_by_side["blue"][0] is stale
    assert target.get_state() == before


@pytest.mark.parametrize("kind", ["weapon", "sensor"])
def test_fresh_restore_rejects_checkpoint_only_nonempty_loadout_atomically(
    kind: str,
) -> None:
    weapon_equipment = EquipmentItem(
        equipment_id="weapon",
        name="Test Gun",
        category=EquipmentCategory.WEAPON,
    )
    sensor_equipment = EquipmentItem(
        equipment_id="sensor",
        name="Test Sensor",
        category=EquipmentCategory.SENSOR,
    )
    unit = Unit("armed", Position(10, 20, 0), side="blue")
    unit.equipment = [weapon_equipment, sensor_equipment]
    weapon, sensor = _loadout(weapon_equipment, sensor_equipment)
    source = _context({"blue": [unit], "red": []})
    source.unit_weapons = {"armed": [(weapon, [])] if kind == "weapon" else []}
    source.unit_sensors = {"armed": [sensor] if kind == "sensor" else []}
    checkpoint = copy.deepcopy(source.get_state())

    stale = Unit("stale", Position(0, 0, 0), side="blue")
    target = _context(
        {"blue": [stale], "red": []},
        {"stale": MoraleState.SHAKEN},
        seed=999,
    )
    target.clock.advance()
    target.rng_manager.get_stream(ModuleId.CORE).random()
    before = copy.deepcopy(target.get_state())

    with pytest.raises(
        ValueError,
        match=rf"Cannot restore {kind} state for reconstructed unit 'armed'",
    ):
        target.set_state(checkpoint)

    assert target.get_state() == before
    assert target.units_by_side["blue"][0] is stale


def test_legacy_unit_states_infer_concrete_classes() -> None:
    source = _context(
        {
            "blue": [
                GroundUnit("ground", Position(0, 0, 0), side="blue"),
                AerialUnit("air", Position(1, 0, 0), side="blue"),
                NavalUnit("naval", Position(2, 0, 0), side="blue"),
                AirDefenseUnit("ad", Position(3, 0, 0), side="blue"),
                SupportUnit("support", Position(4, 0, 0), side="blue"),
                Unit("base", Position(5, 0, 0), side="blue"),
            ],
            "red": [],
        },
    )
    checkpoint = _as_versionless_legacy_context(source.get_state())
    for state in checkpoint["units_by_side"]["blue"]:
        state.pop("unit_class", None)
    target = _context()

    target.set_state(checkpoint, allow_legacy_morale=True)

    assert [type(unit) for unit in target.units_by_side["blue"]] == [
        GroundUnit,
        AerialUnit,
        NavalUnit,
        AirDefenseUnit,
        SupportUnit,
        Unit,
    ]


def test_legacy_checkpoint_without_force_sections_preserves_runtime_force() -> None:
    unit = _ground("existing", "blue", Position(50, 60, 0))
    target = _context(
        {"blue": [unit], "red": []},
        {"existing": MoraleState.SHAKEN},
    )
    expected_units = copy.deepcopy(target.get_state()["units_by_side"])
    checkpoint = _as_versionless_legacy_context(target.get_state())
    checkpoint.pop("units_by_side")
    checkpoint.pop("unit_weapon_states")
    checkpoint.pop("unit_sensor_states")
    unit.position = Position(70, 80, 0)
    expected_mutated = unit.get_state()

    target.set_state(checkpoint, allow_legacy_morale=True)

    assert target.units_by_side["blue"][0] is unit
    assert unit.get_state() == expected_mutated
    assert unit.get_state() != expected_units["blue"][0]
    assert target.morale_states == {"existing": MoraleState.SHAKEN}


@pytest.mark.parametrize("corrupt", ["missing_weapon_unit", "sensor_conflict"])
def test_runtime_instance_state_validation_is_atomic(corrupt: str) -> None:
    weapon_equipment = EquipmentItem(
        equipment_id="weapon",
        name="Test Gun",
        category=EquipmentCategory.WEAPON,
    )
    sensor_equipment = EquipmentItem(
        equipment_id="sensor",
        name="Test Sensor",
        category=EquipmentCategory.SENSOR,
    )
    unit = _ground("armed", "blue", Position(0, 0, 0))
    unit.equipment = [weapon_equipment, sensor_equipment]
    weapon, sensor = _loadout(weapon_equipment, sensor_equipment)
    ctx = _context(
        {"blue": [unit], "red": []},
        {"armed": MoraleState.STEADY},
    )
    ctx.unit_weapons = {"armed": [(weapon, [])]}
    ctx.unit_sensors = {"armed": [sensor]}
    checkpoint = copy.deepcopy(ctx.get_state())

    ctx.clock.advance()
    ctx.rng_manager.get_stream(ModuleId.CORE).random()
    before_clock = copy.deepcopy(ctx.clock.get_state())
    before_rng = copy.deepcopy(ctx.rng_manager.get_state())
    before_weapon = copy.deepcopy(weapon.get_state())

    if corrupt == "missing_weapon_unit":
        checkpoint["unit_weapon_states"].pop("armed")
    else:
        checkpoint["unit_sensor_states"]["armed"][0][
            "equipment_condition"
        ] = 0.25

    with pytest.raises(ValueError):
        ctx.set_state(checkpoint)

    assert "armed" in ctx.unit_weapons
    assert ctx.unit_weapons["armed"][0][0] is weapon
    assert weapon.get_state() == before_weapon
    assert ctx.clock.get_state() == before_clock
    assert ctx.rng_manager.get_state() == before_rng


def test_json_canonical_configuration_is_accepted() -> None:
    source = _context()
    source.config.behavior_rules = {"waypoints": (1.0, 2.0)}
    checkpoint = json.loads(json.dumps(source.get_state()))
    target = _context()
    target.config.behavior_rules = {"waypoints": (1.0, 2.0)}

    target.set_state(checkpoint)

    assert target.config.behavior_rules == {"waypoints": (1.0, 2.0)}


@pytest.mark.parametrize(
    "corrupt",
    [
        "duplicate_id",
        "duplicate_personnel",
        "duplicate_equipment",
        "unknown_class",
        "ambiguous_class",
        "invalid_morale",
        "config_mismatch",
        "loadout_mismatch",
    ],
)
def test_corrupt_force_state_fails_without_partial_force_commit(corrupt: str) -> None:
    target_unit = _ground("existing", "blue", Position(50, 60, 0))
    target_unit.personnel = [
        CrewMember(
            member_id="crew",
            role=CrewRole.DRIVER,
            skill=SkillLevel.TRAINED,
            experience=0.5,
        ),
    ]
    target_unit.equipment = [
        EquipmentItem(
            equipment_id="equipment",
            name="Equipment",
            category=EquipmentCategory.UTILITY,
        ),
    ]
    target = _context(
        {"blue": [target_unit], "red": []},
        {"existing": MoraleState.SHAKEN},
    )
    checkpoint = copy.deepcopy(target.get_state())
    target.clock.advance()
    target.rng_manager.get_stream(ModuleId.CORE).random()
    before_units = copy.deepcopy(target.get_state()["units_by_side"])
    before_morale = dict(target.morale_states)
    before_clock = copy.deepcopy(target.clock.get_state())
    before_rng = copy.deepcopy(target.rng_manager.get_state())

    if corrupt == "duplicate_id":
        duplicate = copy.deepcopy(checkpoint["units_by_side"]["blue"][0])
        duplicate["side"] = "red"
        checkpoint["units_by_side"]["red"].append(duplicate)
    elif corrupt == "duplicate_personnel":
        personnel = checkpoint["units_by_side"]["blue"][0]["personnel"]
        personnel.append(copy.deepcopy(personnel[0]))
    elif corrupt == "duplicate_equipment":
        equipment_states = checkpoint["units_by_side"]["blue"][0]["equipment"]
        equipment_states.append(copy.deepcopy(equipment_states[0]))
    elif corrupt == "unknown_class":
        checkpoint["units_by_side"]["blue"][0]["unit_class"] = "UntrustedUnit"
    elif corrupt == "ambiguous_class":
        unit_state = checkpoint["units_by_side"]["blue"][0]
        unit_state.pop("unit_class")
        unit_state["aerial_type"] = 0
    elif corrupt == "invalid_morale":
        checkpoint["morale_runtime"]["active_records"]["existing"][
            "current_state"
        ] = "NOT_A_MORALE_STATE"
    elif corrupt == "config_mismatch":
        checkpoint["config"]["name"] = "Different scenario"
    else:
        checkpoint["unit_weapon_states"]["existing"] = [
            {"weapon_id": "missing_weapon"},
        ]

    with pytest.raises(ValueError):
        target.set_state(checkpoint)

    assert target.get_state()["units_by_side"] == before_units
    assert target.morale_states == before_morale
    assert target.units_by_side["blue"][0] is target_unit
    assert target.clock.get_state() == before_clock
    assert target.rng_manager.get_state() == before_rng


def _engine() -> tuple[SimulationEngine, WeaponInstance]:
    blue = _ground("blue-1", "blue", Position(0, 0, 0), max_speed=2.0)
    red = _ground("red-1", "red", Position(150_000, 0, 0), max_speed=1.5)
    weapon_equipment = EquipmentItem(
        equipment_id="blue-gun",
        name="Test Gun",
        category=EquipmentCategory.WEAPON,
    )
    sensor_equipment = EquipmentItem(
        equipment_id="blue-sensor",
        name="Test Sensor",
        category=EquipmentCategory.SENSOR,
    )
    blue.equipment = [weapon_equipment, sensor_equipment]
    weapon, sensor = _loadout(weapon_equipment, sensor_equipment)
    ctx = _context(
        {"blue": [blue], "red": [red]},
        {
            "blue-1": MoraleState.STEADY,
            "red-1": MoraleState.SHAKEN,
        },
    )
    ctx.unit_weapons = {"blue-1": [(weapon, [])], "red-1": []}
    ctx.unit_sensors = {"blue-1": [sensor], "red-1": []}
    recorder = SimulationRecorder(ctx.event_bus)
    recorder.start()
    engine = SimulationEngine(
        ctx,
        campaign_config=CampaignConfig(
            engagement_detection_range_m=1_000,
            strategic_speed_fraction=0.5,
        ),
        recorder=recorder,
    )
    return engine, weapon


def _json_checkpoint(engine: SimulationEngine) -> dict[str, Any]:
    return json.loads(engine.checkpoint().decode("utf-8"))


def test_fresh_engine_restore_continues_identically_to_control() -> None:
    control, control_weapon = _engine()
    for _ in range(2):
        control.step()
    assert control_weapon.fire("test_round", 3)
    control_weapon.record_fire(7_200.0)
    checkpoint = control.checkpoint()
    checkpoint_state = json.loads(checkpoint.decode("utf-8"))

    assert control_weapon.fire("test_round", 2)
    control_weapon.record_fire(7_500.0)
    for _ in range(3):
        control.step()
    expected = _json_checkpoint(control)

    resumed, resumed_weapon = _engine()
    resumed.restore(checkpoint)
    assert _json_checkpoint(resumed) == checkpoint_state
    assert resumed_weapon.ammo_state.available("test_round") == 7
    assert resumed_weapon._rounds_since_maintenance == 3
    assert resumed_weapon._last_fire_time_s == 7_200.0
    assert resumed_weapon.fire("test_round", 2)
    resumed_weapon.record_fire(7_500.0)
    for _ in range(3):
        resumed.step()

    assert _json_checkpoint(resumed) == expected


@pytest.mark.parametrize("corrupt", ["config", "resolution_clock"])
def test_rejected_engine_restore_preserves_resolution_and_clock(
    corrupt: str,
) -> None:
    engine, _ = _engine()
    checkpoint = engine.get_state()
    checkpoint["resolution"] = TickResolution.TACTICAL.value
    if corrupt == "config":
        checkpoint["context"]["clock"]["tick_duration_seconds"] = 5.0
        checkpoint["context"]["config"]["name"] = "Different scenario"
    before_resolution = engine.resolution
    before_clock = copy.deepcopy(engine._ctx.clock.get_state())

    with pytest.raises(ValueError):
        engine.set_state(checkpoint)

    assert engine.resolution == before_resolution
    assert engine._ctx.clock.get_state() == before_clock


def test_loaded_production_scenario_restores_live_weapon_state() -> None:
    scenario_path = Path("data/scenarios/test_campaign/scenario.yaml")
    control_ctx = ScenarioLoader(Path("data")).load(scenario_path, seed=105)
    control_recorder = SimulationRecorder(control_ctx.event_bus)
    control_recorder.start()
    control = SimulationEngine(control_ctx, recorder=control_recorder)

    unit_id, weapon_index, weapon, ammo_id = next(
        (
            unit_id,
            index,
            weapon,
            ammo_defs[0].ammo_id,
        )
        for unit_id, entries in control_ctx.unit_weapons.items()
        for index, (weapon, ammo_defs) in enumerate(entries)
        if ammo_defs and weapon.can_fire(ammo_defs[0].ammo_id)
    )
    assert weapon.fire(ammo_id)
    weapon.record_fire(30.0)
    checkpoint = control.checkpoint()

    resumed_ctx = ScenarioLoader(Path("data")).load(scenario_path, seed=105)
    resumed_recorder = SimulationRecorder(resumed_ctx.event_bus)
    resumed_recorder.start()
    resumed = SimulationEngine(resumed_ctx, recorder=resumed_recorder)
    resumed.restore(checkpoint)
    resumed_weapon = resumed_ctx.unit_weapons[unit_id][weapon_index][0]

    assert resumed_weapon.get_state() == weapon.get_state()
    assert _json_checkpoint(resumed) == json.loads(checkpoint.decode("utf-8"))

    control.step()
    resumed.step()
    assert _json_checkpoint(resumed) == _json_checkpoint(control)
