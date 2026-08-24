"""Strict schema and production-resolution proofs for Phase 111."""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from stochastic_warfare.combat.ammunition import (
    AmmoDefinition,
    AmmoLoader,
    WeaponCategory,
    WeaponDefinition,
    WeaponLoader,
)
from stochastic_warfare.combat.ballistics import BallisticsEngine
from stochastic_warfare.combat.damage import DamageEngine
from stochastic_warfare.combat.indirect_fire import IndirectFireEngine
from stochastic_warfare.combat.indirect_fire_config import (
    IndirectFireScenarioConfig,
)
from stochastic_warfare.core.era import EraConfig
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Domain, Position
from stochastic_warfare.detection.sensors import SensorLoader
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.entities.equipment import (
    EquipmentCategory,
    EquipmentItem,
)
from stochastic_warfare.entities.loader import (
    EquipmentEntry,
    SensorPolicy,
    UnitDefinition,
)
from stochastic_warfare.simulation.loadouts import (
    EquipmentMappingRegistry,
    RuntimeLoadoutBuilder,
    RuntimeLoadouts,
    WeaponAttachmentMapping,
    WeaponModeledRole,
)
from stochastic_warfare.simulation.scenario import (
    CampaignScenarioConfig,
    ScenarioLoader,
    load_campaign_scenario_config,
)
from stochastic_warfare.simulation.time_on_target import (
    TimeOnTargetMissionResolver,
    TimeOnTargetResolutionError,
)
from stochastic_warfare.terrain.heightmap import Heightmap, HeightmapConfig


DATA_DIR = Path("data")
SCENARIO_PATH = (
    DATA_DIR / "scenarios/time_on_target_validation/scenario.yaml"
)
BATTERY_ID = "blue_m109a6_0000"
SECOND_BATTERY_ID = "blue_m109a6_0001"
TARGET_ID = "red_hemtt_0000"


def _payload() -> dict:
    return load_campaign_scenario_config(SCENARIO_PATH).model_dump(
        mode="python",
    )


def _mission(payload: dict) -> dict:
    return payload["indirect_fire"]["time_on_target_missions"][0]


def _battery(payload: dict, index: int = 0) -> dict:
    return _mission(payload)["batteries"][index]


def _load_payload(payload: dict):
    config = CampaignScenarioConfig.model_validate(payload)
    return ScenarioLoader(DATA_DIR).load(
        SCENARIO_PATH,
        seed=111,
        scenario_config=config,
    )


def _assert_loader_rejects(
    mutate: Callable[[dict], None],
    match: str,
) -> None:
    payload = _payload()
    mutate(payload)
    with pytest.raises(TimeOnTargetResolutionError, match=match):
        _load_payload(payload)


def _runtime_loadouts(ctx) -> RuntimeLoadouts:
    return RuntimeLoadouts(
        unit_weapons=ctx.unit_weapons,
        unit_sensor_attachments=ctx.unit_sensor_attachments,
        equipment_resolutions=ctx.equipment_resolutions,
    )


def _resolve_loaded_context(ctx):
    return TimeOnTargetMissionResolver.resolve(
        ctx.config.indirect_fire,
        units_by_side=ctx.units_by_side,
        runtime_loadouts=_runtime_loadouts(ctx),
        terrain=ctx.heightmap,
        duration_hours=ctx.config.duration_hours,
        tick_duration_seconds=ctx.config.tick_duration_seconds,
    )


def test_shipped_schema_resolves_exact_live_attachments() -> None:
    ctx = ScenarioLoader(DATA_DIR).load(SCENARIO_PATH, seed=111)
    plans = _resolve_loaded_context(ctx)

    assert len(plans) == 1
    assert plans[0].mission_id == "blue_validation_tot"
    assert [
        (
            battery.unit_id,
            battery.source_equipment_index,
            battery.weapon.weapon_id,
            battery.ammunition.ammo_id,
            battery.scheduled_fire_time_s,
        )
        for battery in plans[0].batteries
    ] == [
        (BATTERY_ID, 0, "m284_155mm", "m982_excalibur", 60.0),
        (SECOND_BATTERY_ID, 0, "m284_155mm", "m982_excalibur", 65.0),
    ]
    for battery in plans[0].batteries:
        assert (
            battery.weapon.equipment
            is battery.unit.equipment[battery.source_equipment_index]
        )


@pytest.mark.parametrize(
    ("location", "field"),
    (
        ("indirect_fire", "surprise"),
        ("mission", "target"),
        ("position", "latitude"),
        ("battery", "hang_time"),
    ),
)
def test_every_nested_schema_level_rejects_unknown_fields(
    location: str,
    field: str,
) -> None:
    payload = _payload()
    containers = {
        "indirect_fire": payload["indirect_fire"],
        "mission": _mission(payload),
        "position": _mission(payload)["target_position"],
        "battery": _battery(payload),
    }
    containers[location][field] = "not-supported"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CampaignScenarioConfig.model_validate(payload)


@pytest.mark.parametrize(
    "field",
    (
        "indirect_fier",
        "indrect_fire",
        "indirect-fire-plan",
        "time_on_target_missions",
        "timeOnTargetMissions",
        "time_on_targte_missions",
        "tot_plan",
        "totPlan",
        "enableTimeOnTarget",
        "enableIndirectFire",
        "enable_time_on_targte",
        "enable_time_target",
        "enable_time_of_target",
        "enable_tot",
        "enableTot",
        "totEnabled",
    ),
)
def test_root_rejects_indirect_fire_typos_and_misplaced_keys(
    field: str,
) -> None:
    payload = _payload()
    payload[field] = (
        payload["indirect_fire"]
        if field.startswith("indirect")
        else _mission(payload)
    )

    with pytest.raises(
        ValidationError,
        match="Unknown or misplaced scenario indirect-fire field",
    ):
        CampaignScenarioConfig.model_validate(payload)


def test_unrelated_historical_root_metadata_remains_outside_strict_boundary() -> None:
    extension_fields = (
        "ai_expectations",
        "blue_forces",
        "documented_outcomes",
        "id",
        "indirect_cost_notes",
        "indirectly_sourced_notes",
        "master_seed",
        "red_forces",
        "sources",
        "start_time",
        "weather",
    )
    for field in extension_fields:
        payload = _payload()
        payload[field] = {"source": "historical metadata"}

        config = CampaignScenarioConfig.model_validate(payload)

        assert config.indirect_fire.enable_time_on_target is True
        assert field not in config.model_dump(mode="python")


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("mission_id", ""),
        ("mission_id", " mission"),
        ("target_unit_id", "target "),
        ("unit_id", ""),
        ("unit_id", " battery"),
        ("weapon_id", "weapon "),
        ("ammo_id", " ammo"),
    ),
)
def test_nested_identifiers_must_be_nonempty_and_trimmed(
    field: str,
    value: str,
) -> None:
    payload = _payload()
    container = (
        _mission(payload)
        if field in {"mission_id", "target_unit_id"}
        else _battery(payload)
    )
    container[field] = value

    with pytest.raises(ValidationError, match="non-empty trimmed string"):
        CampaignScenarioConfig.model_validate(payload)


@pytest.mark.parametrize("value", ("true", 1, 0))
def test_enable_gate_is_a_strict_boolean(value: object) -> None:
    payload = _payload()
    payload["indirect_fire"]["enable_time_on_target"] = value

    with pytest.raises(ValidationError):
        CampaignScenarioConfig.model_validate(payload)


@pytest.mark.parametrize(
    ("location", "field", "value"),
    (
        ("position", "easting", True),
        ("position", "easting", "22000"),
        ("position", "easting", float("nan")),
        ("position", "easting", float("inf")),
        ("mission", "impact_time_s", True),
        ("mission", "impact_time_s", "120"),
        ("mission", "impact_time_s", float("nan")),
        ("mission", "impact_time_s", float("inf")),
        ("mission", "impact_time_s", 120.5),
        ("mission", "rounds_per_battery", True),
        ("mission", "rounds_per_battery", "1"),
        ("battery", "source_equipment_index", True),
        ("battery", "source_equipment_index", "0"),
        ("battery", "time_of_flight_s", True),
        ("battery", "time_of_flight_s", "60"),
        ("battery", "time_of_flight_s", float("nan")),
        ("battery", "time_of_flight_s", float("inf")),
        ("battery", "time_of_flight_s", 60.5),
    ),
)
def test_nested_numeric_fields_reject_coercion_nonfinite_and_fractional_time(
    location: str,
    field: str,
    value: object,
) -> None:
    payload = _payload()
    containers = {
        "position": _mission(payload)["target_position"],
        "mission": _mission(payload),
        "battery": _battery(payload),
    }
    containers[location][field] = value

    with pytest.raises(ValidationError):
        CampaignScenarioConfig.model_validate(payload)


@pytest.mark.parametrize(
    "value",
    (None, True, "5", 0, -5, 2.5, float("nan"), float("inf")),
)
def test_declared_plan_requires_strict_positive_whole_second_cadence(
    value: object,
) -> None:
    payload = _payload()
    payload["tick_duration_seconds"] = value

    with pytest.raises(
        ValidationError,
        match="positive whole-second tick_duration_seconds",
    ):
        CampaignScenarioConfig.model_validate(payload)


@pytest.mark.parametrize(
    ("impact_time_s", "time_of_flight_s", "match"),
    (
        (121.0, 56.0, "impact time is not aligned"),
        (120.0, 56.0, "fire time is not aligned"),
    ),
)
def test_schedule_times_must_align_to_fixed_cadence(
    impact_time_s: float,
    time_of_flight_s: float,
    match: str,
) -> None:
    payload = _payload()
    _mission(payload)["impact_time_s"] = impact_time_s
    _battery(payload)["time_of_flight_s"] = time_of_flight_s

    with pytest.raises(ValidationError, match=match):
        CampaignScenarioConfig.model_validate(payload)


def test_derived_fire_time_must_be_strictly_positive() -> None:
    payload = _payload()
    _battery(payload)["time_of_flight_s"] = _mission(payload)["impact_time_s"]

    with pytest.raises(ValidationError, match="non-positive fire time"):
        CampaignScenarioConfig.model_validate(payload)


@pytest.mark.parametrize(
    "value",
    (True, "1", 0, -1, float("nan"), float("inf")),
)
def test_scenario_duration_is_strict_finite_and_positive(value: object) -> None:
    payload = _payload()
    payload["duration_hours"] = value

    with pytest.raises(
        ValidationError,
        match="duration_hours must be a finite positive number",
    ):
        CampaignScenarioConfig.model_validate(payload)


def test_mission_impact_cannot_exceed_scenario_duration() -> None:
    payload = _payload()
    _mission(payload)["impact_time_s"] = 3605.0

    with pytest.raises(ValidationError, match="exceeds scenario duration"):
        CampaignScenarioConfig.model_validate(payload)


def test_enabled_gate_requires_at_least_one_mission() -> None:
    payload = _payload()
    payload["indirect_fire"]["time_on_target_missions"] = []

    with pytest.raises(
        ValidationError,
        match="enable_time_on_target requires at least one mission",
    ):
        CampaignScenarioConfig.model_validate(payload)


def test_mission_ids_must_be_unique() -> None:
    payload = _payload()
    duplicate = copy.deepcopy(_mission(payload))
    payload["indirect_fire"]["time_on_target_missions"].append(duplicate)

    with pytest.raises(
        ValidationError,
        match="time-on-target mission IDs must be unique",
    ):
        CampaignScenarioConfig.model_validate(payload)


def test_battery_ids_must_be_unique_within_a_mission() -> None:
    payload = _payload()
    _mission(payload)["batteries"][1]["unit_id"] = BATTERY_ID

    with pytest.raises(
        ValidationError,
        match="battery unit IDs must be unique",
    ):
        CampaignScenarioConfig.model_validate(payload)


def test_mission_rejects_more_than_six_batteries_without_truncation() -> None:
    payload = _payload()
    prototype = copy.deepcopy(_battery(payload))
    _mission(payload)["batteries"] = [
        {
            **copy.deepcopy(prototype),
            "unit_id": f"battery-{index}",
        }
        for index in range(7)
    ]

    with pytest.raises(ValidationError, match="at most 6 items"):
        CampaignScenarioConfig.model_validate(payload)


@pytest.mark.test_evidence("helper_assertion")
@pytest.mark.parametrize(
    ("role", "unit_id", "match"),
    (
        ("target", "missing-target", "target.*unknown unit"),
        ("battery", "missing-battery", "unknown battery unit"),
    ),
)
def test_loader_rejects_unknown_target_and_battery_units(
    role: str,
    unit_id: str,
    match: str,
) -> None:
    def mutate(payload: dict) -> None:
        if role == "target":
            _mission(payload)["target_unit_id"] = unit_id
        else:
            _battery(payload)["unit_id"] = unit_id

    _assert_loader_rejects(mutate, match)


@pytest.mark.test_evidence("helper_assertion")
def test_loader_rejects_friendly_target() -> None:
    _assert_loader_rejects(
        lambda payload: _mission(payload).__setitem__(
            "target_unit_id",
            BATTERY_ID,
        ),
        "is friendly to side",
    )


@pytest.mark.test_evidence("helper_assertion")
def test_loader_rejects_batteries_from_multiple_sides() -> None:
    _assert_loader_rejects(
        lambda payload: _mission(payload)["batteries"][1].__setitem__(
            "unit_id",
            TARGET_ID,
        ),
        "batteries must all belong to one scenario side",
    )


@pytest.mark.parametrize(
    ("unit_id", "role"),
    (
        (TARGET_ID, "target"),
        (BATTERY_ID, "battery"),
    ),
)
def test_resolver_rejects_initially_inactive_target_and_battery(
    unit_id: str,
    role: str,
) -> None:
    ctx = ScenarioLoader(DATA_DIR).load(SCENARIO_PATH, seed=111)
    unit = next(
        candidate
        for candidate in ctx.all_units()
        if candidate.entity_id == unit_id
    )
    unit.status = UnitStatus.DISABLED

    with pytest.raises(
        TimeOnTargetResolutionError,
        match=rf"{role} {unit_id!r} must initially be ACTIVE",
    ):
        _resolve_loaded_context(ctx)


@pytest.mark.test_evidence("helper_assertion")
@pytest.mark.parametrize(
    ("field", "value", "match"),
    (
        (
            "source_equipment_index",
            99,
            "unknown source_equipment_index 99",
        ),
        (
            "weapon_id",
            "not_the_indexed_weapon",
            "not declared 'not_the_indexed_weapon'",
        ),
        (
            "ammo_id",
            "not_on_the_attachment",
            "unknown ammunition 'not_on_the_attachment'",
        ),
    ),
)
def test_loader_rejects_wrong_exact_attachment_identity(
    field: str,
    value: object,
    match: str,
) -> None:
    _assert_loader_rejects(
        lambda payload: _battery(payload).__setitem__(field, value),
        match,
    )


def test_resolver_rejects_ambiguous_source_attachment() -> None:
    ctx = ScenarioLoader(DATA_DIR).load(SCENARIO_PATH, seed=111)
    attachments = ctx.unit_weapons[BATTERY_ID]
    unit_weapons = dict(ctx.unit_weapons)
    unit_weapons[BATTERY_ID] = (attachments[0], *attachments)
    with pytest.raises(
        ValueError,
        match="duplicate weapon source index 0",
    ):
        RuntimeLoadouts(
            unit_weapons=unit_weapons,
            unit_sensor_attachments=ctx.unit_sensor_attachments,
            equipment_resolutions=ctx.equipment_resolutions,
        )


def test_resolver_rejects_ambiguous_attachment_ammunition() -> None:
    ctx = ScenarioLoader(DATA_DIR).load(SCENARIO_PATH, seed=111)
    attachments = ctx.unit_weapons[BATTERY_ID]
    exact = attachments[0]
    ammunition = next(
        ammo
        for ammo in exact.ammunition
        if ammo.ammo_id == "m982_excalibur"
    )
    ambiguous = replace(
        exact,
        ammunition=(*exact.ammunition, ammunition),
    )
    unit_weapons = dict(ctx.unit_weapons)
    unit_weapons[BATTERY_ID] = (ambiguous, *attachments[1:])
    loadouts = RuntimeLoadouts(
        unit_weapons=unit_weapons,
        unit_sensor_attachments=ctx.unit_sensor_attachments,
        equipment_resolutions=ctx.equipment_resolutions,
    )

    with pytest.raises(
        TimeOnTargetResolutionError,
        match="ambiguous ammunition 'm982_excalibur'",
    ):
        TimeOnTargetMissionResolver.resolve(
            ctx.config.indirect_fire,
            units_by_side=ctx.units_by_side,
            runtime_loadouts=loadouts,
            terrain=ctx.heightmap,
            duration_hours=ctx.config.duration_hours,
            tick_duration_seconds=ctx.config.tick_duration_seconds,
        )


@pytest.mark.test_evidence("helper_assertion")
def test_loader_rejects_unsupported_weapon_category() -> None:
    def use_machine_gun(payload: dict) -> None:
        battery = _battery(payload)
        battery.update({
            "source_equipment_index": 1,
            "weapon_id": "m2hb_50cal",
            "ammo_id": "50bmg_m2_ap",
        })

    _assert_loader_rejects(
        use_machine_gun,
        "unsupported time-on-target weapon category MACHINE_GUN",
    )


def test_resolver_rejects_unsupported_target_domain() -> None:
    ctx = ScenarioLoader(DATA_DIR).load(SCENARIO_PATH, seed=111)
    target = next(
        unit for unit in ctx.all_units() if unit.entity_id == TARGET_ID
    )
    target.domain = Domain.AERIAL

    with pytest.raises(
        TimeOnTargetResolutionError,
        match="cannot engage target domain AERIAL",
    ):
        _resolve_loaded_context(ctx)


@pytest.mark.test_evidence("helper_assertion")
@pytest.mark.parametrize(
    "ammo_id",
    ("m825_smoke", "m485_illumination"),
)
def test_loader_rejects_non_damaging_ammunition(ammo_id: str) -> None:
    _assert_loader_rejects(
        lambda payload: _battery(payload).__setitem__("ammo_id", ammo_id),
        "non-damaging and unsupported",
    )


def test_resolver_rejects_zero_blast_ammunition() -> None:
    ctx = ScenarioLoader(DATA_DIR).load(SCENARIO_PATH, seed=111)
    attachment = ctx.unit_weapons[BATTERY_ID][0]
    ammunition = next(
        ammo
        for ammo in attachment.ammunition
        if ammo.ammo_id == "m982_excalibur"
    )
    ammunition.blast_radius_m = 0.0

    with pytest.raises(
        TimeOnTargetResolutionError,
        match="requires a finite positive blast_radius_m",
    ):
        _resolve_loaded_context(ctx)


def test_resolver_rejects_ammunition_incompatible_with_exact_weapon() -> None:
    ctx = ScenarioLoader(DATA_DIR).load(SCENARIO_PATH, seed=111)
    attachment = ctx.unit_weapons[BATTERY_ID][0]
    attachment.weapon.definition.compatible_ammo.remove("m982_excalibur")

    with pytest.raises(
        TimeOnTargetResolutionError,
        match="ammunition 'm982_excalibur' is incompatible",
    ):
        _resolve_loaded_context(ctx)


@pytest.mark.test_evidence("helper_assertion")
@pytest.mark.parametrize(
    ("target_position", "range_fragment"),
    (
        (
            {"easting": 1000.0, "northing": 9000.0, "altitude": 0.0},
            "outside weapon bounds",
        ),
        (
            {"easting": 29900.0, "northing": 19900.0, "altitude": 0.0},
            "outside weapon bounds",
        ),
    ),
    ids=("below-minimum", "above-maximum"),
)
def test_loader_rejects_target_outside_weapon_range(
    target_position: dict[str, float],
    range_fragment: str,
) -> None:
    _assert_loader_rejects(
        lambda payload: _mission(payload).__setitem__(
            "target_position",
            target_position,
        ),
        range_fragment,
    )


@pytest.mark.test_evidence("helper_assertion")
def test_loader_rejects_target_outside_loaded_terrain() -> None:
    _assert_loader_rejects(
        lambda payload: _mission(payload).__setitem__(
            "target_position",
            {
                "easting": -100.0,
                "northing": 1000.0,
                "altitude": 0.0,
            },
        ),
        "lies outside loaded terrain bounds",
    )


@pytest.mark.test_evidence("helper_assertion")
def test_loader_rejects_time_of_flight_below_physical_speed_bound() -> None:
    _assert_loader_rejects(
        lambda payload: _battery(payload).__setitem__(
            "time_of_flight_s",
            5.0,
        ),
        "shorter than physical lower bound",
    )


@pytest.mark.test_evidence("helper_assertion")
def test_loader_rejects_rounds_above_exact_runtime_multiplier() -> None:
    _assert_loader_rejects(
        lambda payload: _mission(payload).__setitem__(
            "rounds_per_battery",
            2,
        ),
        "exceeding runtime_system_multiplier 1",
    )


def test_loader_rejects_aggregate_ammunition_overbooking() -> None:
    payload = _payload()
    prototype = copy.deepcopy(_mission(payload))
    prototype["batteries"] = [prototype["batteries"][0]]
    missions = []
    for index in range(40):
        mission = copy.deepcopy(prototype)
        mission["mission_id"] = f"aggregate-{index:02d}"
        mission["impact_time_s"] = 120.0 + 20.0 * index
        missions.append(mission)
    payload["indirect_fire"]["time_on_target_missions"] = missions

    with pytest.raises(
        TimeOnTargetResolutionError,
        match=r"aggregate-overbook.*requested=40, available=39",
    ):
        _load_payload(payload)


def _empty_loader(loader_type):
    return loader_type(Path("."))


def _composite_fixture():
    equipment_name = "Composite Howitzer Battery (x4)"
    weapon_id = "composite_155mm"
    ammo_id = "composite_he"
    battery_definition = UnitDefinition(
        unit_type="composite_battery",
        domain="ground",
        ground_type="ARTILLERY_SP",
        display_name="Composite Battery",
        max_speed=1.0,
        crew=[],
        equipment=[
            EquipmentEntry(
                name=equipment_name,
                category="WEAPON",
            ),
        ],
        sensor_policy=SensorPolicy.INTENTIONALLY_NONE,
        sensor_policy_reason="Synthetic resolver fixture has no detection role.",
    )
    target_definition = UnitDefinition(
        unit_type="composite_target",
        domain="ground",
        ground_type="LIGHT_INFANTRY",
        display_name="Composite Target",
        max_speed=1.0,
        crew=[],
        equipment=[],
        sensor_policy=SensorPolicy.INTENTIONALLY_NONE,
        sensor_policy_reason="Synthetic resolver target has no detection role.",
    )
    weapon_definition = WeaponDefinition(
        weapon_id=weapon_id,
        display_name="Composite 155 mm Howitzer",
        category="HOWITZER",
        caliber_mm=155.0,
        muzzle_velocity_mps=500.0,
        min_range_m=100.0,
        max_range_m=5000.0,
        rate_of_fire_rpm=15.0,
        magazine_capacity=10,
        compatible_ammo=[ammo_id],
        target_domains=["GROUND"],
    )
    ammunition = AmmoDefinition(
        ammo_id=ammo_id,
        display_name="Composite HE",
        ammo_type="HE",
        blast_radius_m=25.0,
        max_speed_mps=500.0,
    )
    weapon_loader = _empty_loader(WeaponLoader)
    ammunition_loader = _empty_loader(AmmoLoader)
    sensor_loader = _empty_loader(SensorLoader)
    weapon_loader._definitions[weapon_id] = weapon_definition
    ammunition_loader._definitions[ammo_id] = ammunition
    builder = RuntimeLoadoutBuilder(
        weapon_loader=weapon_loader,
        ammo_loader=ammunition_loader,
        sensor_loader=sensor_loader,
        unit_definitions={
            battery_definition.unit_type: battery_definition,
            target_definition.unit_type: target_definition,
        },
        era_config=EraConfig(),
        assignment_overrides=(),
        reachable_unit_types=(
            battery_definition.unit_type,
            target_definition.unit_type,
        ),
        registry=EquipmentMappingRegistry((
            WeaponAttachmentMapping(
                equipment_name=equipment_name,
                weapon_id=weapon_id,
                expected_weapon_category=WeaponCategory.HOWITZER,
                modeled_role=WeaponModeledRole.FIELD_ARTILLERY,
                allowed_ammo_ids=(ammo_id,),
                required_target_domains=(Domain.GROUND,),
                source_system_count=4,
                target_system_count=1,
            ),
        )),
    )
    battery = Unit(
        entity_id="blue-composite",
        position=Position(100.0, 100.0, 0.0),
        unit_type=battery_definition.unit_type,
        side="blue",
        equipment=[
            EquipmentItem(
                equipment_id="composite-equipment",
                name=equipment_name,
                category=EquipmentCategory.WEAPON,
            ),
        ],
    )
    target = Unit(
        entity_id="red-target",
        position=Position(1100.0, 100.0, 0.0),
        unit_type=target_definition.unit_type,
        side="red",
    )
    loadouts = builder.build((battery, target))
    terrain = Heightmap(
        np.zeros((30, 30), dtype=np.float64),
        HeightmapConfig(cell_size=100.0),
    )
    return battery, target, loadouts, terrain


def _composite_config(second_fire_time_s: float) -> IndirectFireScenarioConfig:
    def mission(mission_id: str, fire_time_s: float) -> dict:
        return {
            "mission_id": mission_id,
            "target_unit_id": "red-target",
            "target_position": {
                "easting": 1100.0,
                "northing": 100.0,
                "altitude": 0.0,
            },
            "impact_time_s": fire_time_s + 5.0,
            "rounds_per_battery": 3,
            "batteries": [
                {
                    "unit_id": "blue-composite",
                    "source_equipment_index": 0,
                    "weapon_id": "composite_155mm",
                    "ammo_id": "composite_he",
                    "time_of_flight_s": 5.0,
                },
            ],
        }

    return IndirectFireScenarioConfig.model_validate({
        "enable_time_on_target": True,
        "time_on_target_missions": [
            mission("first", 10.0),
            mission("second", second_fire_time_s),
        ],
    })


def test_resolver_enforces_quantity_aware_composite_cooldown() -> None:
    battery, target, loadouts, terrain = _composite_fixture()
    attachment = loadouts.unit_weapons[battery.entity_id][0]
    assert attachment.runtime_system_multiplier == 4
    assert attachment.weapon.cooldown_s == pytest.approx(1.0)

    with pytest.raises(
        TimeOnTargetResolutionError,
        match=r"quantity-aware cooldown.*gap=2s, required=3s",
    ):
        TimeOnTargetMissionResolver.resolve(
            _composite_config(second_fire_time_s=12.0),
            units_by_side={"blue": (battery,), "red": (target,)},
            runtime_loadouts=loadouts,
            terrain=terrain,
            duration_hours=1.0,
            tick_duration_seconds=1.0,
        )

    accepted = TimeOnTargetMissionResolver.resolve(
        _composite_config(second_fire_time_s=13.0),
        units_by_side={"blue": (battery,), "red": (target,)},
        runtime_loadouts=loadouts,
        terrain=terrain,
        duration_hours=1.0,
        tick_duration_seconds=1.0,
    )
    assert [
        mission.batteries[0].scheduled_fire_time_s
        for mission in accepted
    ] == [10.0, 13.0]


def test_composite_runtime_enforces_quantity_aware_cooldown() -> None:
    def runtime(*, external_fire_time_s: float | None):
        battery, target, loadouts, terrain = _composite_fixture()
        missions = TimeOnTargetMissionResolver.resolve(
            _composite_config(second_fire_time_s=13.0),
            units_by_side={"blue": (battery,), "red": (target,)},
            runtime_loadouts=loadouts,
            terrain=terrain,
            duration_hours=1.0,
            tick_duration_seconds=1.0,
        )
        weapon = loadouts.unit_weapons[battery.entity_id][0].weapon
        if external_fire_time_s is not None:
            assert weapon.fire("composite_he", 1)
            weapon.record_fire(external_fire_time_s)
        event_bus = EventBus()
        engine = IndirectFireEngine(
            BallisticsEngine(np.random.default_rng(1111)),
            DamageEngine(event_bus, np.random.default_rng(2222)),
            event_bus,
            np.random.default_rng(3333),
            time_on_target_enabled=True,
            time_on_target_missions=missions,
        )
        return engine, weapon

    timestamp = datetime(2024, 1, 1, tzinfo=timezone.utc)
    accepted, accepted_weapon = runtime(external_fire_time_s=None)
    initial_rounds = accepted_weapon.ammo_state.available("composite_he")
    accepted.update_time_on_target(10.0, timestamp)
    accepted.update_time_on_target(13.0, timestamp)
    accepted_state = accepted.get_state()
    assert [
        mission["batteries"][0]["status"]
        for mission in accepted_state["missions"]
    ] == ["fired", "fired"]
    assert (
        accepted_weapon.ammo_state.available("composite_he")
        == initial_rounds - 6
    )
    assert accepted_weapon.get_state()["ammo_state"]["total_rounds_fired"] == 6
    assert accepted_weapon.get_state()["rounds_since_maintenance"] == 6
    assert accepted_weapon.get_state()["last_fire_time_s"] == 13.0

    rejected, rejected_weapon = runtime(external_fire_time_s=8.0)
    before_rejection = copy.deepcopy(rejected_weapon.get_state())
    rejected.update_time_on_target(10.0, timestamp)
    rejected_state = rejected.get_state()
    assert rejected_state["missions"][0]["batteries"][0]["status"] == (
        "rejected"
    )
    assert rejected_state["missions"][0]["batteries"][0]["reason"] == (
        "weapon_cooldown"
    )
    assert rejected_weapon.get_state() == before_rejection

    rejected.update_time_on_target(13.0, timestamp)
    assert rejected.get_state()["missions"][1]["batteries"][0]["status"] == (
        "fired"
    )
    assert rejected_weapon.get_state()["ammo_state"]["total_rounds_fired"] == 4
    assert rejected_weapon.get_state()["rounds_since_maintenance"] == 4
    assert rejected_weapon.get_state()["last_fire_time_s"] == 13.0
