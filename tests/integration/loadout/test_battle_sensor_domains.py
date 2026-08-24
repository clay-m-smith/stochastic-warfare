"""Production battle proofs for Phase 109 sensor-domain mappings."""

from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from stochastic_warfare.combat.events import (
    AmmoExpendedEvent,
    EngagementEvent,
    MissileInterceptEvent,
)
from stochastic_warfare.core.types import Domain, Position
from stochastic_warfare.detection.sensors import (
    SensorType,
    signature_domain_for_sensor_type,
)
from stochastic_warfare.detection.signatures import (
    SignatureDomain,
    SignatureProfile,
    ThermalSignature,
    VisualSignature,
)
from stochastic_warfare.entities.base import Unit
from stochastic_warfare.entities.unit_classes.aerial import (
    AirPosture,
    FlightState,
)
from stochastic_warfare.simulation.battle import BattleContext, BattleManager
from stochastic_warfare.simulation.loadouts import (
    ReferenceKind,
    ResolutionDisposition,
    SensorModeledRole,
    WeaponAttachment,
)
from stochastic_warfare.simulation.scenario import (
    ScenarioLoader,
    SimulationContext,
)
from stochastic_warfare.simulation.tactical_targeting import (
    TacticalTargetingRuntime,
)


DATA_DIR = Path("data")
SCENARIO_PATH = DATA_DIR / "scenarios/taiwan_strait/scenario.yaml"
FALLUJAH_SCENARIO_PATH = DATA_DIR / "scenarios/fallujah_phase_line_fran/scenario.yaml"
EASTING_SCENARIO_PATH = DATA_DIR / "scenarios/73_easting/scenario.yaml"
FALKLANDS_SCENARIO_PATH = (
    DATA_DIR / "scenarios/falklands_san_carlos/scenario.yaml"
)
BEKAA_SCENARIO_PATH = (
    DATA_DIR / "scenarios/bekaa_valley_1982/scenario.yaml"
)
SEED = 109
COMPARISON_RANGE_M = 20_000.0
MIXED_AIR_RANGE_M = 30_000.0


def _unit_of_type(ctx: SimulationContext, unit_type: str) -> Unit:
    return next(unit for unit in ctx.all_units() if unit.unit_type == unit_type)


def _place_aircraft(unit: Unit, easting_m: float) -> None:
    unit.position = Position(easting_m, 0.0, 5_000.0)
    unit.speed = 0.0
    unit.air_posture = AirPosture.ON_STATION
    unit.flight_state = FlightState.AIRBORNE


def _run_f16_engagement(
    targets: tuple[tuple[str, float], ...],
) -> tuple[
    SimulationContext,
    Unit,
    tuple[Unit, ...],
    list[EngagementEvent],
]:
    """Run one real, isolated production battle engagement selection."""
    ctx = ScenarioLoader(DATA_DIR).load(
        SCENARIO_PATH,
        seed=SEED,
        calibration_overrides={"target_selection_mode": "nearest"},
    )

    attacker = _unit_of_type(ctx, "f16c")
    _place_aircraft(attacker, 0.0)

    target_units: list[Unit] = []
    target_positions: list[tuple[float, float]] = []
    for unit_type, range_m in targets:
        target = _unit_of_type(ctx, unit_type)
        if target.domain.name == "AERIAL":
            _place_aircraft(target, range_m)
        else:
            target.position = Position(range_m, 0.0, 0.0)
            target.speed = 0.0
        target_units.append(target)
        target_positions.append((range_m, 0.0))

    # The production battle method consults context ownership for side lookup,
    # while the explicit inputs isolate this one attacker and target set.
    ctx.units_by_side = {
        "blue": [attacker],
        "red": target_units,
    }
    events: list[EngagementEvent] = []
    ctx.event_bus.subscribe(EngagementEvent, events.append)

    BattleManager(ctx.event_bus)._execute_engagements(
        ctx,
        {"blue": [attacker]},
        {"blue": target_units},
        {
            "blue": np.asarray(
                target_positions,
                dtype=np.float64,
            ),
        },
        1.0,
        ctx.clock.current_time,
    )
    return ctx, attacker, tuple(target_units), events


@pytest.mark.test_evidence("behavioral_oracle")
def test_ship_sam_uses_air_defense_route_against_aircraft() -> None:
    """A naval SAM must not be treated as an anti-ship missile salvo."""
    ctx = ScenarioLoader(DATA_DIR).load(
        FALKLANDS_SCENARIO_PATH,
        seed=SEED,
        calibration_overrides={
            "enable_air_routing": True,
            "target_selection_mode": "nearest",
        },
    )
    ship = _unit_of_type(ctx, "type42_destroyer")
    target = _unit_of_type(ctx, "a4_skyhawk")
    ship.position = Position(0.0, 0.0, 0.0)
    ship.speed = 0.0
    ship.heading = math.pi / 2.0
    _place_aircraft(target, 5_000.0)
    target.position = Position(5_000.0, 0.0, 1_000.0)
    sea_dart = next(
        attachment
        for attachment in ctx.unit_weapons[ship.entity_id]
        if attachment.source_equipment.name == "Sea Dart SAM"
    )
    ctx.unit_weapons[ship.entity_id] = (sea_dart,)
    ctx.units_by_side = {"blue": [ship], "red": [target]}

    naval_engine = MagicMock()
    naval_engine.salvo_exchange.return_value = SimpleNamespace(hits=0)
    ctx.naval_surface_engine = naval_engine
    ammo_events: list[AmmoExpendedEvent] = []
    intercept_events: list[MissileInterceptEvent] = []
    engagement_events: list[EngagementEvent] = []
    ctx.event_bus.subscribe(AmmoExpendedEvent, ammo_events.append)
    ctx.event_bus.subscribe(MissileInterceptEvent, intercept_events.append)
    ctx.event_bus.subscribe(EngagementEvent, engagement_events.append)
    ammo_id = sea_dart.ammunition[0].ammo_id
    before = sea_dart.weapon.ammo_state.available(ammo_id)
    interceptors_before = ctx.air_defense_engine.get_state()[
        "interceptors_fired"
    ]

    BattleManager(ctx.event_bus)._execute_engagements(
        ctx,
        {"blue": [ship]},
        {"blue": [target]},
        {
            "blue": np.asarray(
                [(target.position.easting, target.position.northing)],
                dtype=np.float64,
            ),
        },
        1.0,
        ctx.clock.current_time,
    )

    assert sea_dart.weapon.definition.target_domains == [Domain.AERIAL.name]
    assert sea_dart.weapon.ammo_state.available(ammo_id) == before - 1
    assert [(event.unit_id, event.ammo_type, event.quantity) for event in ammo_events] == [
        (ship.entity_id, ammo_id, 1),
    ]
    assert len(intercept_events) == 1
    assert intercept_events[0].defender_id == ship.entity_id
    assert (
        ctx.air_defense_engine.get_state()["interceptors_fired"]
        == interceptors_before + 1
    )
    assert [
        (event.attacker_id, event.target_id, event.weapon_id)
        for event in engagement_events
    ] == [(ship.entity_id, target.entity_id, "sea_dart")]
    naval_engine.salvo_exchange.assert_not_called()


def test_cooldown_blocked_sam_does_not_consume_engager_limit() -> None:
    """A handled-but-unfired route must leave room for a ready battery."""
    ctx = ScenarioLoader(DATA_DIR).load(
        BEKAA_SCENARIO_PATH,
        seed=SEED,
        calibration_overrides={
            "max_engagers_per_side": 1,
            "target_selection_mode": "nearest",
        },
    )
    batteries = [
        unit for unit in ctx.all_units() if unit.unit_type == "sa6_gainful"
    ][:2]
    target = _unit_of_type(ctx, "f16c")
    assert len(batteries) == 2
    for index, battery in enumerate(batteries):
        battery.position = Position(float(index * 100), 0.0, 0.0)
        battery.speed = 0.0
        battery.heading = math.pi / 2.0
    _place_aircraft(target, 5_000.0)
    target.position = Position(5_000.0, 0.0, 1_000.0)
    attachments = [
        next(
            attachment
            for attachment in ctx.unit_weapons[battery.entity_id]
            if attachment.weapon.weapon_id == "sa6_3m9"
        )
        for battery in batteries
    ]
    for battery, attachment in zip(batteries, attachments, strict=True):
        ctx.unit_weapons[battery.entity_id] = (attachment,)
    ctx.units_by_side = {"red": batteries, "blue": [target]}

    current_time_s = ctx.clock.elapsed.total_seconds()
    attachments[0].weapon.record_fire(current_time_s)
    first_ammo_id = attachments[0].ammunition[0].ammo_id
    second_ammo_id = attachments[1].ammunition[0].ammo_id
    first_before = attachments[0].weapon.ammo_state.available(first_ammo_id)
    second_before = attachments[1].weapon.ammo_state.available(second_ammo_id)
    events: list[EngagementEvent] = []
    ctx.event_bus.subscribe(EngagementEvent, events.append)

    BattleManager(ctx.event_bus)._execute_engagements(
        ctx,
        {"red": batteries},
        {"red": [target]},
        {
            "red": np.asarray(
                [(target.position.easting, target.position.northing)],
                dtype=np.float64,
            ),
        },
        1.0,
        ctx.clock.current_time,
    )

    assert (
        attachments[0].weapon.ammo_state.available(first_ammo_id)
        == first_before
    )
    assert (
        attachments[1].weapon.ammo_state.available(second_ammo_id)
        == second_before - 1
    )
    assert [
        (event.attacker_id, event.target_id, event.weapon_id)
        for event in events
    ] == [(batteries[1].entity_id, target.entity_id, "sa6_3m9")]


def test_air_only_attachment_changes_production_standoff_by_target_domain() -> None:
    ctx = ScenarioLoader(DATA_DIR).load(
        SCENARIO_PATH,
        seed=SEED,
        calibration_overrides={"defensive_sides": []},
    )
    attacker = _unit_of_type(ctx, "f16c")
    ground_target = _unit_of_type(ctx, "m1a2")
    air_target = _unit_of_type(ctx, "j10a")
    air_only = next(
        attachment
        for attachment in ctx.unit_weapons[attacker.entity_id]
        if attachment.weapon.definition.target_domains
        == [Domain.AERIAL.name]
        and attachment.weapon.definition.max_range_m > 25_000.0
    )
    ctx.unit_weapons[attacker.entity_id] = (air_only,)
    manager = BattleManager(ctx.event_bus)

    _place_aircraft(attacker, 0.0)
    attacker.speed = 100.0
    ground_target.position = Position(20_000.0, 0.0, 0.0)
    manager._execute_movement(
        ctx,
        {"blue": [attacker]},
        {"blue": [ground_target]},
        1.0,
    )
    assert attacker.position.easting > 0.0

    _place_aircraft(attacker, 0.0)
    attacker.speed = 100.0
    _place_aircraft(air_target, 20_000.0)
    manager._execute_movement(
        ctx,
        {"blue": [attacker]},
        {"blue": [air_target]},
        1.0,
    )
    assert attacker.position == Position(0.0, 0.0, 5_000.0)


def test_multidomain_fire_control_radar_allows_real_aerial_engagement() -> None:
    ctx, attacker, (target,), events = _run_f16_engagement(
        (("j10a", COMPARISON_RANGE_M),),
    )

    attachments = ctx.unit_weapons[attacker.entity_id]
    assert all(isinstance(item, WeaponAttachment) for item in attachments)
    radar = next(sensor for sensor in ctx.unit_sensors[attacker.entity_id] if sensor.sensor_id == "apg68_radar")
    assert radar.supports_target_domain(target.domain)
    assert [(event.attacker_id, event.target_id, event.weapon_id) for event in events] == [
        (attacker.entity_id, target.entity_id, "aim120_amraam"),
    ]


def test_multidomain_fire_control_radar_allows_real_ground_engagement() -> None:
    ctx, attacker, (target,), events = _run_f16_engagement(
        (("bmp2", COMPARISON_RANGE_M),),
    )

    radar = next(sensor for sensor in ctx.unit_sensors[attacker.entity_id] if sensor.sensor_id == "apg68_radar")
    maverick = next(
        attachment
        for attachment in ctx.unit_weapons[attacker.entity_id]
        if attachment.weapon.weapon_id == "agm65_maverick"
    )
    assert radar.effective_range > COMPARISON_RANGE_M
    assert radar.supports_target_domain(target.domain)
    assert target.domain.name in maverick.weapon.definition.effective_target_domains()
    assert maverick.weapon.definition.max_range_m > COMPARISON_RANGE_M
    assert maverick.weapon.can_fire(maverick.ammunition[0].ammo_id)
    assert [(event.attacker_id, event.target_id, event.weapon_id) for event in events] == [
        (attacker.entity_id, target.entity_id, "agm65_maverick"),
    ]


def test_multidomain_radar_preserves_nearest_compatible_target_selection() -> None:
    _ctx, attacker, (ground_target, aerial_target), events = _run_f16_engagement(
        (
            ("bmp2", COMPARISON_RANGE_M),
            ("j10a", MIXED_AIR_RANGE_M),
        ),
    )

    assert COMPARISON_RANGE_M < MIXED_AIR_RANGE_M
    assert ground_target.domain.name == "GROUND"
    assert aerial_target.domain.name == "AERIAL"
    assert [(event.attacker_id, event.target_id, event.weapon_id) for event in events] == [
        (attacker.entity_id, ground_target.entity_id, "agm65_maverick"),
    ]


def test_ground_targeting_sensors_do_not_grant_aerial_battle_detection() -> None:
    ctx = ScenarioLoader(DATA_DIR).load(
        DATA_DIR / "scenarios/benchmark_brigade/scenario.yaml",
        seed=SEED,
        calibration_overrides={
            "target_selection_mode": "nearest",
            "visibility_m": 100.0,
        },
    )
    attacker = _unit_of_type(ctx, "ah64d")
    target = _unit_of_type(ctx, "j10a")
    _place_aircraft(attacker, 0.0)
    _place_aircraft(target, 1_000.0)
    ctx.units_by_side = {"blue": [attacker], "red": [target]}

    sensors = ctx.unit_sensors[attacker.entity_id]
    assert sensors
    assert all(not sensor.supports_target_domain(target.domain) for sensor in sensors)
    gun = next(
        attachment
        for attachment in ctx.unit_weapons[attacker.entity_id]
        if target.domain.name in attachment.weapon.definition.effective_target_domains()
    )
    assert gun.weapon.definition.max_range_m > 1_000.0
    assert gun.weapon.can_fire(gun.ammunition[0].ammo_id)

    events: list[EngagementEvent] = []
    ctx.event_bus.subscribe(EngagementEvent, events.append)
    BattleManager(ctx.event_bus)._execute_engagements(
        ctx,
        {"blue": [attacker]},
        {"blue": [target]},
        {
            "blue": np.asarray(
                [(target.position.easting, target.position.northing)],
                dtype=np.float64,
            ),
        },
        1.0,
        ctx.clock.current_time,
    )

    assert events == []


def _run_fallujah_night_engagement(
    attacker_type: str,
    target_type: str,
    target_range_m: float,
) -> tuple[SimulationContext, Unit, Unit, list[EngagementEvent]]:
    """Run one isolated engagement under the scenario's real night engines."""
    ctx = ScenarioLoader(DATA_DIR).load(
        FALLUJAH_SCENARIO_PATH,
        seed=SEED,
        calibration_overrides={"target_selection_mode": "nearest"},
    )
    attacker = _unit_of_type(ctx, attacker_type)
    target = _unit_of_type(ctx, target_type)
    attacker.position = Position(0.0, 0.0, 0.0)
    target.position = Position(target_range_m, 0.0, 0.0)
    attacker.speed = 0.0
    target.speed = 0.0
    ctx.units_by_side = {"blue": [attacker], "red": [target]}

    events: list[EngagementEvent] = []
    ctx.event_bus.subscribe(EngagementEvent, events.append)
    BattleManager(ctx.event_bus)._execute_engagements(
        ctx,
        {"blue": [attacker]},
        {"blue": [target]},
        {
            "blue": np.asarray(
                [(target_range_m, 0.0)],
                dtype=np.float64,
            ),
        },
        1.0,
        ctx.clock.current_time,
    )
    return ctx, attacker, target, events


def test_in_range_thermal_sensor_is_not_hidden_by_daytime_visibility() -> None:
    target_range_m = 1_800.0
    ctx, attacker, target, events = _run_fallujah_night_engagement(
        "us_m1a2_sep",
        "iraqi_insurgent_urban",
        target_range_m,
    )

    illumination = ctx.time_of_day_engine.illumination_at(
        ctx.config.latitude,
        ctx.config.longitude,
    )
    thermal = next(sensor for sensor in ctx.unit_sensors[attacker.entity_id] if sensor.sensor_type.name == "THERMAL")
    main_gun = next(
        attachment for attachment in ctx.unit_weapons[attacker.entity_id] if attachment.weapon.weapon_id == "m256_120mm"
    )
    assert illumination.is_day is False
    assert ctx.cal_flat["visibility_m"] > thermal.effective_range
    assert thermal.effective_range > target_range_m
    assert thermal.supports_target_domain(target.domain)
    assert main_gun.weapon.definition.max_range_m > target_range_m
    assert [(event.attacker_id, event.target_id, event.weapon_id) for event in events] == [
        (attacker.entity_id, target.entity_id, "m256_120mm"),
    ]


def test_out_of_range_nvg_does_not_recover_visual_detection() -> None:
    target_range_m = 1_600.0
    ctx, attacker, target, events = _run_fallujah_night_engagement(
        "us_army_infantry_cav",
        "iraqi_foreign_fighter",
        target_range_m,
    )

    illumination = ctx.time_of_day_engine.illumination_at(
        ctx.config.latitude,
        ctx.config.longitude,
    )
    nvg = next(sensor for sensor in ctx.unit_sensors[attacker.entity_id] if sensor.sensor_type.name == "NVG")
    machine_gun = next(
        attachment for attachment in ctx.unit_weapons[attacker.entity_id] if attachment.weapon.weapon_id == "m240_762mm"
    )
    assert illumination.is_day is False
    assert nvg.supports_target_domain(target.domain)
    assert nvg.effective_range < target_range_m
    assert machine_gun.weapon.definition.max_range_m > target_range_m
    assert events == []


def _fow_contact_with_heading(attacker_heading_rad: float) -> tuple[bool, float]:
    ctx = ScenarioLoader(DATA_DIR).load(SCENARIO_PATH, seed=SEED)
    attacker = _unit_of_type(ctx, "f16c")
    target = _unit_of_type(ctx, "j10a")
    _place_aircraft(attacker, 0.0)
    _place_aircraft(target, COMPARISON_RANGE_M)
    attacker.heading = attacker_heading_rad
    ctx.units_by_side = {"blue": [attacker], "red": [target]}

    radar = next(sensor for sensor in ctx.unit_sensors[attacker.entity_id] if sensor.sensor_id == "apg68_radar")
    battle = BattleContext(
        battle_id="phase109-fow-heading",
        start_tick=0,
        start_time=ctx.clock.current_time,
        involved_sides=["blue", "red"],
        unit_ids={attacker.entity_id, target.entity_id},
    )
    ctx.tactical_targeting = TacticalTargetingRuntime(
        sensing_aware_standoff_enabled=(
            ctx.tactical_targeting.sensing_aware_standoff_enabled
        ),
        unit_sides={
            attacker.entity_id: "blue",
            target.entity_id: "red",
        },
    )
    battle_manager = BattleManager(ctx.event_bus)
    battle_manager.prepare_tactical_interval(ctx, (battle,), 1.0)
    battle_manager.execute_tick(ctx, battle, 1.0)
    world_view = ctx.fog_of_war.get_world_view("blue")
    return target.entity_id in world_view.contacts, radar.definition.fov_deg


def test_nonzero_unit_heading_controls_narrow_fov_in_production_fow() -> None:
    on_boresight, fov_deg = _fow_contact_with_heading(math.pi / 2.0)
    off_boresight, repeated_fov_deg = _fow_contact_with_heading(math.pi)

    assert 0.0 < fov_deg < 360.0
    assert repeated_fov_deg == fov_deg
    assert on_boresight is True
    assert off_boresight is False


def test_rwr_is_transparent_non_runtime_equipment_not_a_live_sensor() -> None:
    ctx = ScenarioLoader(DATA_DIR).load(SCENARIO_PATH, seed=SEED)
    f16 = _unit_of_type(ctx, "f16c")
    rwr = next(equipment for equipment in f16.equipment if equipment.name == "AN/ALR-56M RWR")
    resolution = next(item for item in ctx.equipment_resolutions[f16.entity_id] if item.source_equipment is rwr)

    assert resolution.disposition is ResolutionDisposition.NON_RUNTIME
    assert resolution.target_id is None
    assert resolution.reason is not None
    assert "Radar-warning alerting" in resolution.reason
    assert all(sensor.equipment is not rwr for sensor in ctx.unit_sensors[f16.entity_id])


@pytest.mark.parametrize(
    ("scenario_name", "unit_type", "avionics_name"),
    (
        ("debecka_pass", "b52h", "AN/ASQ-176 OAS"),
        ("suwalki_gap", "mi24v", "Raduga-Sh Sight"),
    ),
)
def test_non_detection_avionics_are_explicit_and_do_not_grant_sensor_capability(
    scenario_name: str,
    unit_type: str,
    avionics_name: str,
) -> None:
    ctx = ScenarioLoader(DATA_DIR).load(
        DATA_DIR / "scenarios" / scenario_name / "scenario.yaml",
        seed=SEED,
    )
    unit = _unit_of_type(ctx, unit_type)
    avionics = next(item for item in unit.equipment if item.name == avionics_name)
    resolution = next(item for item in ctx.equipment_resolutions[unit.entity_id] if item.source_equipment is avionics)
    sensors = ctx.unit_sensors[unit.entity_id]

    assert resolution.disposition is ResolutionDisposition.NON_RUNTIME
    assert resolution.target_id is None
    assert resolution.reason
    assert all(sensor.equipment is not avionics for sensor in sensors)
    assert [sensor.equipment.name for sensor in sensors] == [
        "Naked Eye Observation",
    ]
    assert sensors[0].sensor_type is SensorType.VISUAL
    assert sensors[0].definition.detects_domain == ["VISUAL"]


@pytest.mark.parametrize(
    ("unit_type", "equipment_name", "expected_role", "expected_range_m"),
    (
        (
            "ah1w",
            "M65 TOW Sight",
            SensorModeledRole.AIRBORNE_GROUND_VISUAL_TARGETING,
            3_750.0,
        ),
        (
            "av8b",
            "ARBS TV/Laser Spot Tracker",
            SensorModeledRole.AIRBORNE_GROUND_BOMBSIGHT,
            5_000.0,
        ),
    ),
)
def test_daylight_airborne_sights_consume_visual_not_thermal_signature(
    unit_type: str,
    equipment_name: str,
    expected_role: SensorModeledRole,
    expected_range_m: float,
) -> None:
    ctx = ScenarioLoader(DATA_DIR).load(
        DATA_DIR / "scenarios/khafji/scenario.yaml",
        seed=SEED,
    )
    observer = _unit_of_type(ctx, unit_type)
    target = _unit_of_type(ctx, "t72m")
    equipment = next(item for item in observer.equipment if item.name == equipment_name)
    sensor = next(item for item in ctx.unit_sensors[observer.entity_id] if item.equipment is equipment)
    resolution = next(
        item for item in ctx.equipment_resolutions[observer.entity_id] if item.source_equipment is equipment
    )

    assert resolution.disposition is ResolutionDisposition.ATTACHMENT
    assert resolution.modeled_role is expected_role
    assert sensor.sensor_type is SensorType.VISUAL
    assert sensor.definition.detects_domain == ["VISUAL"]
    assert sensor.definition.max_range_m == expected_range_m
    assert sensor.supports_target_domain(target.domain)

    common_visual = VisualSignature(
        cross_section_m2=10.0,
        camouflage_factor=1.0,
    )
    cool_target = SignatureProfile(
        profile_id=f"phase109-{unit_type}-cool",
        unit_type=target.unit_type,
        visual=common_visual,
        thermal=ThermalSignature(
            emissivity=0.1,
            heat_output_kw=1.0,
            contrast_modifier=0.1,
        ),
    )
    hot_target = SignatureProfile(
        profile_id=f"phase109-{unit_type}-hot",
        unit_type=target.unit_type,
        visual=common_visual,
        thermal=ThermalSignature(
            emissivity=1.0,
            heat_output_kw=10_000.0,
            contrast_modifier=10.0,
        ),
    )
    kwargs = {
        "observer_pos": Position(0.0, 0.0, 1_000.0),
        "target_pos": Position(1_000.0, 0.0, 0.0),
        "sensor": sensor,
        "target_unit": target,
        "observer_heading_deg": 90.0,
        "illumination_lux": 10_000.0,
        "visibility_m": 10_000.0,
    }
    cool_result = ctx.detection_engine.check_detection(
        target_sig=cool_target,
        rng=np.random.default_rng(SEED),
        **kwargs,
    )
    hot_result = ctx.detection_engine.check_detection(
        target_sig=hot_target,
        rng=np.random.default_rng(SEED),
        **kwargs,
    )
    larger_visual_result = ctx.detection_engine.check_detection(
        target_sig=hot_target.model_copy(
            update={
                "visual": VisualSignature(
                    cross_section_m2=100.0,
                    camouflage_factor=1.0,
                ),
            },
        ),
        rng=np.random.default_rng(SEED),
        **kwargs,
    )

    assert hot_result.snr_db == pytest.approx(cool_result.snr_db)
    assert hot_result.probability == pytest.approx(cool_result.probability)
    assert larger_visual_result.snr_db > hot_result.snr_db


@pytest.mark.parametrize(
    (
        "observer_type",
        "sensor_id",
        "expected_range_m",
        "expected_role",
    ),
    (
        pytest.param(
            "t72m",
            "active_ir_sight",
            800.0,
            SensorModeledRole.GROUND_ACTIVE_IR_SIGHT,
            id="tpn-3-49-active-ir",
        ),
        pytest.param(
            "bmp1",
            "1pn22m1_gunner_sight",
            400.0,
            SensorModeledRole.GROUND_NIGHT_SIGHT,
            id="1pn22m1-passive-night",
        ),
    ),
)
def test_night_sights_consume_visual_not_thermal_signature(
    observer_type: str,
    sensor_id: str,
    expected_range_m: float,
    expected_role: SensorModeledRole,
) -> None:
    """Active-IR and passive-night identities remain distinct and nonthermal."""
    ctx = ScenarioLoader(DATA_DIR).load(EASTING_SCENARIO_PATH, seed=SEED)
    observer = _unit_of_type(ctx, observer_type)
    target = _unit_of_type(ctx, "m1a1")
    sensor = next(item for item in ctx.unit_sensors[observer.entity_id] if item.sensor_id == sensor_id)

    assert sensor.sensor_type is SensorType.NVG
    assert sensor.definition.max_range_m == expected_range_m
    assert sensor.definition.fov_deg == 6.0
    assert signature_domain_for_sensor_type(sensor.sensor_type) is SignatureDomain.VISUAL
    assert sensor.definition.detects_domain == ["VISUAL"]

    if sensor_id == "1pn22m1_gunner_sight":
        source_equipment = next(
            equipment for equipment in observer.equipment if equipment.name == "1PN22M1 Gunner Sight"
        )
        resolution = next(
            item for item in ctx.equipment_resolutions[observer.entity_id] if item.source_equipment is source_equipment
        )
        assert resolution.reference_kind is ReferenceKind.EXACT
        assert resolution.modeled_role is expected_role
        assert resolution.target_id == "1pn22m1_gunner_sight"
        assert resolution.target_id != "active_ir_sight"

    common_visual = VisualSignature(
        cross_section_m2=10.0,
        camouflage_factor=1.0,
    )
    cool_target = SignatureProfile(
        profile_id=f"phase109-{sensor_id}-cool",
        unit_type=target.unit_type,
        visual=common_visual,
        thermal=ThermalSignature(
            emissivity=0.1,
            heat_output_kw=1.0,
            contrast_modifier=0.1,
        ),
    )
    hot_target = SignatureProfile(
        profile_id=f"phase109-{sensor_id}-hot",
        unit_type=target.unit_type,
        visual=common_visual,
        thermal=ThermalSignature(
            emissivity=1.0,
            heat_output_kw=10_000.0,
            contrast_modifier=10.0,
        ),
    )
    observer_pos = Position(0.0, 0.0, 0.0)
    target_pos = Position(400.0, 0.0, 0.0)
    common_kwargs = {
        "observer_pos": observer_pos,
        "target_pos": target_pos,
        "sensor": sensor,
        "target_unit": target,
        "observer_heading_deg": 90.0,
        "illumination_lux": 10.0,
        "visibility_m": 10_000.0,
    }
    cool_result = ctx.detection_engine.check_detection(
        target_sig=cool_target,
        rng=np.random.default_rng(SEED),
        **common_kwargs,
    )
    hot_result = ctx.detection_engine.check_detection(
        target_sig=hot_target,
        rng=np.random.default_rng(SEED),
        **common_kwargs,
    )
    larger_visual_result = ctx.detection_engine.check_detection(
        target_sig=hot_target.model_copy(
            update={
                "visual": VisualSignature(
                    cross_section_m2=100.0,
                    camouflage_factor=1.0,
                ),
            },
        ),
        rng=np.random.default_rng(SEED),
        **common_kwargs,
    )

    assert hot_result.snr_db == pytest.approx(cool_result.snr_db)
    assert hot_result.probability == pytest.approx(cool_result.probability)
    assert larger_visual_result.snr_db > hot_result.snr_db


def _run_active_ir_smoke_engagement(
    *,
    deploy_smoke: bool,
) -> tuple[SimulationContext, Unit, Unit, list[EngagementEvent]]:
    ctx = ScenarioLoader(DATA_DIR).load(
        EASTING_SCENARIO_PATH,
        seed=SEED,
        calibration_overrides={
            "target_selection_mode": "nearest",
            "visibility_m": 100.0,
        },
    )
    attacker = _unit_of_type(ctx, "t72m")
    target = _unit_of_type(ctx, "m1a1")
    attacker.position = Position(0.0, 0.0, 0.0)
    target.position = Position(300.0, 0.0, 0.0)
    attacker.speed = 0.0
    target.speed = 0.0
    ctx.units_by_side = {"red": [attacker], "blue": [target]}
    if deploy_smoke:
        ctx.obscurants_engine.deploy_smoke(
            target.position,
            radius=100.0,
            multispectral=False,
        )

    events: list[EngagementEvent] = []
    ctx.event_bus.subscribe(EngagementEvent, events.append)
    BattleManager(ctx.event_bus)._execute_engagements(
        ctx,
        {"red": [attacker]},
        {"red": [target]},
        {
            "red": np.asarray(
                [(target.position.easting, target.position.northing)],
                dtype=np.float64,
            ),
        },
        1.0,
        ctx.clock.current_time,
    )
    return ctx, attacker, target, events


def test_active_ir_sight_uses_visual_obscurant_behavior_in_production() -> None:
    clear_ctx, attacker, target, clear_events = _run_active_ir_smoke_engagement(deploy_smoke=False)
    smoke_ctx, _smoke_attacker, smoke_target, smoke_events = _run_active_ir_smoke_engagement(deploy_smoke=True)
    opacity = smoke_ctx.obscurants_engine.opacity_at(smoke_target.position)
    sensor = next(item for item in clear_ctx.unit_sensors[attacker.entity_id] if item.sensor_id == "active_ir_sight")

    assert sensor.sensor_type is SensorType.NVG
    assert opacity.visual == pytest.approx(0.9)
    assert opacity.thermal == pytest.approx(0.1)
    assert [(event.attacker_id, event.target_id) for event in clear_events] == [(attacker.entity_id, target.entity_id)]
    assert smoke_events == []
