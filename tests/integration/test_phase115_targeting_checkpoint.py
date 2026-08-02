"""Phase 115 tactical-targeting checkpoint integrity and continuation."""

from __future__ import annotations

import copy
import json
import sys
from dataclasses import replace

import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.detection.sensors import SensorType
from stochastic_warfare.entities.equipment import EquipmentCategory
from stochastic_warfare.environment.weather import WeatherState
from stochastic_warfare.simulation.force_builder import (
    RuntimeUnitSpec,
    UnitInstanceOverrides,
)
from stochastic_warfare.simulation.battle import BattleConfig
from stochastic_warfare.simulation.loadouts import (
    ResolutionDisposition,
    SensorModeledRole,
)
from stochastic_warfare.simulation.runtime import (
    AnalysisVariant,
    PreparedScenario,
    RuntimeSession,
    SimulationRuntimeFactory,
)
from stochastic_warfare.simulation.scenario import (
    CampaignScenarioConfig,
    register_dynamic_units,
)
from stochastic_warfare.simulation.tactical_targeting import (
    TacticalTargetingRuntime,
    sensor_environment_range_policy,
    sensor_environment_range_upper_bound_m,
)
from tests.integration.test_phase115_sensing_standoff_red import (
    DATA_DIR,
    SOURCE_LABEL,
    VARIANT_ID,
    _mark_iv_scenario,
)


ACOUSTIC_SOURCE_LABEL = str(
    (DATA_DIR / "eras" / "ww2" / "units" / "naval" / "flower_corvette.yaml").resolve(),
)
THERMAL_SOURCE_LABEL = str(
    (DATA_DIR / "scenarios" / "73_easting" / "scenario.yaml").resolve(),
)
RADAR_SOURCE_LABEL = str(
    (DATA_DIR / "scenarios" / "bekaa_valley_1982" / "scenario.yaml").resolve(),
)


def _prepare_targeting_scenario(
    *,
    fog_of_war: bool = False,
    separation_m: float = 5_000.0,
    reinforcement: bool = False,
    reinforcement_side: str = "british",
    northward_target: bool = False,
    scenario_date: str | None = None,
    target_unit_type: str | None = None,
) -> PreparedScenario:
    raw = _mark_iv_scenario().model_dump(mode="json")
    if scenario_date is not None:
        raw["date"] = scenario_date
    if target_unit_type is not None:
        raw["sides"][1]["units"][0]["unit_type"] = target_unit_type
    raw["calibration_overrides"]["enable_fog_of_war"] = fog_of_war
    raw["sides"][1]["units"][0]["position"] = (
        [1_000.0, 1_000.0 + separation_m, 0.0] if northward_target else [1_000.0 + separation_m, 1_000.0, 0.0]
    )
    if reinforcement:
        reinforcement_type = "mark_iv_tank" if reinforcement_side == "british" else "german_sturmtruppen"
        raw["reinforcements"] = [
            {
                "side": reinforcement_side,
                "arrival_time_s": 0.0,
                "units": [
                    {"unit_type": reinforcement_type, "count": 1},
                ],
                "position": [1_500.0, 1_500.0, 0.0],
            },
        ]
    config = CampaignScenarioConfig.model_validate(raw)
    return SimulationRuntimeFactory().prepare_config(
        config,
        DATA_DIR,
        (AnalysisVariant(variant_id=VARIANT_ID),),
        source_label=SOURCE_LABEL,
    )


def _prepare_acoustic_extension_scenario() -> PreparedScenario:
    """Prepare a real surface-duct contact beyond raw sonar range."""
    config = CampaignScenarioConfig.model_validate(
        {
            "name": "Phase 115 acoustic checkpoint range bound",
            "date": "1943-06-01T12:00:00Z",
            "duration_hours": 1.0,
            "era": "ww2",
            "tick_resolution": {
                "strategic_s": 3_600.0,
                "operational_s": 300.0,
                "tactical_s": 5.0,
            },
            "weather_conditions": {
                "visibility_m": 5_000.0,
                "precipitation": "none",
                "sea_state": 2,
            },
            "terrain": {
                "width_m": 10_000.0,
                "height_m": 5_000.0,
                "cell_size_m": 100.0,
                "terrain_type": "open_ocean",
            },
            "deployment": {"mode": "manual"},
            "sides": [
                {
                    "side": "allies",
                    "units": [
                        {
                            "unit_type": "flower_corvette",
                            "count": 1,
                            "position": [1_000.0, 1_000.0, 0.0],
                        },
                    ],
                },
                {
                    "side": "axis",
                    "units": [
                        {
                            "unit_type": "type_viic_uboat",
                            "count": 1,
                            "position": [4_000.0, 1_000.0, 0.0],
                        },
                    ],
                },
            ],
            "objectives": [],
            "victory_conditions": [],
            "calibration_overrides": {
                "defensive_sides": [],
                "enable_fog_of_war": False,
                "enable_sensing_aware_standoff": True,
                "enable_acoustic_layers": True,
                "target_selection_mode": "closest",
            },
        }
    )
    return SimulationRuntimeFactory().prepare_config(
        config,
        DATA_DIR,
        (AnalysisVariant(variant_id=VARIANT_ID),),
        source_label=ACOUSTIC_SOURCE_LABEL,
    )


def _prepare_thermal_extension_scenario() -> PreparedScenario:
    """Prepare schema-valid thermal contrast above the former fixed cap."""
    config = CampaignScenarioConfig.model_validate(
        {
            "name": "Phase 115 calibration-aware thermal checkpoint bound",
            "date": "2025-06-21T09:00:00Z",
            "duration_hours": 1.0,
            "era": "modern",
            "latitude": 30.0,
            "longitude": 47.0,
            "tick_resolution": {
                "strategic_s": 3_600.0,
                "operational_s": 300.0,
                "tactical_s": 5.0,
            },
            "weather_conditions": {
                "visibility_m": 800.0,
                "precipitation": "none",
            },
            "terrain": {
                "width_m": 10_000.0,
                "height_m": 10_000.0,
                "cell_size_m": 100.0,
                "terrain_type": "flat_desert",
            },
            "deployment": {"mode": "manual"},
            "sides": [
                {
                    "side": "blue",
                    "units": [
                        {
                            "unit_type": "us_m1a2_sep",
                            "count": 1,
                            "position": [1_000.0, 1_000.0, 0.0],
                        },
                    ],
                },
                {
                    "side": "red",
                    "units": [
                        {
                            "unit_type": "t90a",
                            "count": 1,
                            "position": [1_000.0, 6_000.0, 0.0],
                        },
                    ],
                },
            ],
            "objectives": [],
            "victory_conditions": [],
            "calibration_overrides": {
                "defensive_sides": [],
                "enable_fog_of_war": False,
                "enable_sensing_aware_standoff": True,
                "enable_thermal_crossover": True,
                "thermal_contrast": 2.25,
                "target_selection_mode": "closest",
            },
        }
    )
    return SimulationRuntimeFactory().prepare_config(
        config,
        DATA_DIR,
        (AnalysisVariant(variant_id=VARIANT_ID),),
        source_label=THERMAL_SOURCE_LABEL,
    )


def _prepare_extreme_rain_factor_scenario(
    *,
    precipitation: str,
) -> PreparedScenario:
    """Prepare schema-valid overflow-scale radar calibration evidence."""
    config = CampaignScenarioConfig.model_validate(
        {
            "name": "Phase 115 finite saturated radar range arithmetic",
            "date": "1991-06-21T12:00:00Z",
            "duration_hours": 1.0,
            "era": "modern",
            "tick_resolution": {
                "strategic_s": 3_600.0,
                "operational_s": 300.0,
                "tactical_s": 5.0,
            },
            "weather_conditions": {
                "visibility_m": 100.0,
                "precipitation": precipitation,
            },
            "terrain": {
                "width_m": 20_000.0,
                "height_m": 20_000.0,
                "cell_size_m": 100.0,
                "terrain_type": "flat_desert",
            },
            "deployment": {"mode": "manual"},
            "sides": [
                {
                    "side": "blue",
                    "units": [
                        {
                            "unit_type": "f16c",
                            "count": 1,
                            "position": [1_000.0, 1_000.0, 1_000.0],
                        },
                    ],
                },
                {
                    "side": "red",
                    "units": [
                        {
                            "unit_type": "mig29a",
                            "count": 1,
                            "position": [1_000.0, 2_000.0, 1_000.0],
                        },
                    ],
                },
            ],
            "objectives": [],
            "victory_conditions": [],
            "calibration_overrides": {
                "defensive_sides": [],
                "enable_fog_of_war": False,
                "enable_sensing_aware_standoff": True,
                "rain_attenuation_factor": -400.0,
                "target_selection_mode": "closest",
            },
        }
    )
    return SimulationRuntimeFactory().prepare_config(
        config,
        DATA_DIR,
        (AnalysisVariant(variant_id=VARIANT_ID),),
        source_label=RADAR_SOURCE_LABEL,
    )


def _prepare_battle_default_visibility_scenario() -> PreparedScenario:
    """Prepare targeting whose visibility comes only from BattleConfig."""
    raw = _mark_iv_scenario(
        target_easting=1_000.0,
        target_northing=1_100.0,
    ).model_dump(mode="json")
    raw["name"] = "Phase 115 battle-config visibility checkpoint binding"
    raw["weather_conditions"].pop("visibility_m")
    raw["calibration_overrides"]["visibility_m"] = None
    raw["calibration_overrides"]["enable_fog_of_war"] = False
    config = CampaignScenarioConfig.model_validate(raw)
    return SimulationRuntimeFactory().prepare_config(
        config,
        DATA_DIR,
        (AnalysisVariant(variant_id=VARIANT_ID),),
        source_label=SOURCE_LABEL,
    )


def _prepare_optical_attachment_scenario() -> PreparedScenario:
    """Prepare non-FOW NVG evidence exactly clamped by visibility."""
    raw = _mark_iv_scenario(
        target_easting=1_000.0,
        target_northing=1_100.0,
    ).model_dump(mode="json")
    raw["name"] = "Phase 115 optical attachment visibility bound"
    raw["date"] = "1991-06-21T21:00:00Z"
    raw["era"] = "modern"
    raw["weather_conditions"]["visibility_m"] = 300.0
    raw["sides"][0]["units"][0]["unit_type"] = "t72m"
    raw["sides"][1]["units"][0]["unit_type"] = "m1a1"
    raw["calibration_overrides"]["enable_fog_of_war"] = False
    raw["calibration_overrides"]["enable_nvg_detection"] = True
    config = CampaignScenarioConfig.model_validate(raw)
    return SimulationRuntimeFactory().prepare_config(
        config,
        DATA_DIR,
        (AnalysisVariant(variant_id=VARIANT_ID),),
        source_label=THERMAL_SOURCE_LABEL,
    )


def _build(prepared: PreparedScenario):
    return prepared.build(
        VARIANT_ID,
        seed=115,
        max_ticks=10,
        strict_mode=True,
    )


def _decoded_checkpoint(session) -> dict:
    return json.loads(session.engine.checkpoint().decode("utf-8"))


def _older_ring_targeting_decision(state: dict) -> dict:
    """Return a weapon- and sensor-bearing decision older than the picture."""
    latest_keys = {
        (
            decision["engine_tick"],
            decision["battle_id"],
            decision["shooter_id"],
        )
        for picture in state["context"]["tactical_targeting"]["latest_pictures"]
        for decision in picture["decisions"]
    }
    candidates = [
        decision
        for summary in state["context"]["movement_diagnostics"]["units"].values()
        for observation in summary["recent_observations"]
        if (decision := observation["targeting_decision"]) is not None
        and (
            decision["engine_tick"],
            decision["battle_id"],
            decision["shooter_id"],
        )
        not in latest_keys
        and decision["weapon_id"] is not None
        and decision["ammunition_id"] is not None
        and decision["contact_sensor_id"] is not None
    ]
    assert candidates
    return candidates[0]


def _targeting_observation(state: dict) -> dict:
    """Return one retained target-bearing movement observation."""
    candidates = [
        observation
        for summary in state["context"]["movement_diagnostics"]["units"].values()
        for observation in summary["recent_observations"]
        if observation["targeting_decision"] is not None
        and observation["targeting_decision"]["target_id"] is not None
        and observation["targeting_decision"]["weapon_id"] is not None
    ]
    assert candidates
    return candidates[0]


def _matching_targeting_decision_states(
    state: dict,
    reference: dict,
) -> tuple[dict, ...]:
    """Return every persisted copy of one exact targeting decision."""
    key = (
        reference["engine_tick"],
        reference["battle_id"],
        reference["shooter_id"],
    )
    candidates = [
        decision
        for picture in state["context"]["tactical_targeting"]["latest_pictures"]
        for decision in picture["decisions"]
    ]
    candidates.extend(
        decision
        for summary in state["context"]["movement_diagnostics"]["units"].values()
        for observation in summary["recent_observations"]
        if (decision := observation["targeting_decision"]) is not None
    )
    matches = tuple(
        decision
        for decision in candidates
        if (
            decision["engine_tick"],
            decision["battle_id"],
            decision["shooter_id"],
        )
        == key
    )
    assert len(matches) >= 2
    return matches


@pytest.fixture(scope="module")
def older_ring_checkpoint() -> tuple[PreparedScenario, bytes, str]:
    """Produce retained FOW evidence plus one live non-member target."""
    prepared = _prepare_targeting_scenario(
        fog_of_war=True,
        separation_m=1_500.0,
        reinforcement=True,
        reinforcement_side="german",
        northward_target=True,
        scenario_date="1917-11-20T12:00:00Z",
        target_unit_type="mark_iv_tank",
    )
    source = _build(prepared)
    arrived = source.engine.campaign_manager.check_reinforcements(
        source.context,
        0.0,
    )
    assert len(arrived) == 1
    outside_member_id = arrived[0].entity_id
    assert source.step() is False
    assert source.step() is False

    checkpoint = source.engine.checkpoint()
    state = json.loads(checkpoint.decode("utf-8"))
    decision = _older_ring_targeting_decision(state)
    interval = state["context"]["tactical_targeting"]["prepared_interval"]
    membership = next(
        member for member in interval["battle_memberships"] if member["battle_id"] == decision["battle_id"]
    )
    assert outside_member_id not in membership["unit_ids"]
    return prepared, checkpoint, outside_member_id


@pytest.fixture(scope="module")
def history_reinforcement_checkpoint() -> tuple[
    PreparedScenario,
    RuntimeSession,
    bytes,
]:
    """Checkpoint retained targeting history after live topology invalidation."""
    prepared = _prepare_targeting_scenario(
        separation_m=2_500.0,
    )
    source = _build(prepared)
    assert source.step() is False
    before_arrival = _decoded_checkpoint(source)
    observation = _targeting_observation(before_arrival)
    assert observation["targeting_membership"] is not None

    force_builder = source.context.force_builder
    assert force_builder is not None
    reinforcement = force_builder.build_units(
        (
            RuntimeUnitSpec(
                entity_id="reinforce_british_phase115_history_0000",
                unit_type="mark_iv_tank",
                side="british",
                position=Position(1_500.0, 1_500.0, 0.0),
                overrides=UnitInstanceOverrides(),
            ),
        )
    )[0]
    # CampaignManager delegates scheduled waves to this same public atomic
    # registration transaction. Direct use supplies the supported
    # between-interval boundary needed by this checkpoint proof; scheduled
    # arrivals ordinarily continue into targeting within their engine step.
    register_dynamic_units(source.context, [reinforcement])
    assert reinforcement in source.context.units_by_side["british"]
    assert source.context.tactical_targeting.prepared_interval is None
    assert source.context.tactical_targeting.latest_pictures() == ()

    checkpoint = source.engine.checkpoint()
    state = json.loads(checkpoint.decode("utf-8"))
    assert state["context"]["tactical_targeting"]["prepared_interval"] is None
    assert state["context"]["tactical_targeting"]["latest_pictures"] == []
    retained = _targeting_observation(state)
    assert retained["targeting_membership"] == (observation["targeting_membership"])
    return prepared, source, checkpoint


@pytest.fixture(scope="module")
def acoustic_extension_checkpoint() -> tuple[
    PreparedScenario,
    RuntimeSession,
    bytes,
]:
    """Capture production sonar evidence extended by a surface duct."""
    prepared = _prepare_acoustic_extension_scenario()
    source = _build(prepared)
    assert source.step() is False

    corvette = next(unit for unit in source.context.all_units() if unit.unit_type == "flower_corvette")
    sonar = next(
        attachment
        for attachment in source.context.unit_sensor_attachments[corvette.entity_id]
        if attachment.sensor.sensor_type is SensorType.ACTIVE_SONAR
    )
    decision = next(
        candidate
        for picture in source.context.tactical_targeting.latest_pictures()
        if (candidate := picture.decision_for(corvette.entity_id)) is not None
    )
    assert decision.contact_sensor_id == sonar.sensor_id == "active_sonar"
    assert sonar.sensor.effective_range == pytest.approx(2_000.0)
    assert decision.contact_range_m == pytest.approx(6_000.0)
    assert decision.sensing_range_m == decision.contact_range_m
    assert decision.contact_range_m > sonar.sensor.definition.max_range_m

    checkpoint = source.engine.checkpoint()
    return prepared, source, checkpoint


@pytest.fixture(scope="module")
def thermal_extension_checkpoint() -> tuple[
    PreparedScenario,
    RuntimeSession,
    bytes,
]:
    """Capture production thermal evidence under accepted 2.25 contrast."""
    prepared = _prepare_thermal_extension_scenario()
    source = _build(prepared)
    assert source.context.calibration.thermal_contrast == 2.25
    assert source.step() is False

    shooter = next(unit for unit in source.context.all_units() if unit.unit_type == "us_m1a2_sep")
    thermals = tuple(
        attachment
        for attachment in source.context.unit_sensor_attachments[shooter.entity_id]
        if attachment.sensor.sensor_type is SensorType.THERMAL
    )
    assert len(thermals) == 2
    decision = next(
        candidate
        for picture in source.context.tactical_targeting.latest_pictures()
        if (candidate := picture.decision_for(shooter.entity_id)) is not None
    )
    selected = next(attachment for attachment in thermals if attachment.sensor_id == decision.contact_sensor_id)
    assert selected.sensor.effective_range == pytest.approx(4_000.0)
    assert decision.contact_range_m > selected.sensor.effective_range * 1.5
    assert decision.contact_range_m == decision.sensing_range_m
    assert decision.visibility_bound_m == pytest.approx(800.0)

    checkpoint = source.engine.checkpoint()
    return prepared, source, checkpoint


def _versionless_pristine_checkpoint(state: dict) -> dict:
    """Convert current pristine state to the bounded legacy envelope."""
    legacy = copy.deepcopy(state)
    assert legacy.pop("checkpoint_version") == 115
    context = legacy["context"]
    context.pop("targeting_default_visibility_m")
    context.pop("tactical_targeting")
    context.pop("era_runtime_contract")
    morale_runtime = context.pop("morale_runtime")
    assert morale_runtime["suspended_archives"] == {}
    active_records = morale_runtime["active_records"]
    morale_rng = copy.deepcopy(context["rng"]["streams"]["morale"])
    context["morale_states"] = {unit_id: record["current_state"] for unit_id, record in active_records.items()}
    context["morale_machine"] = {
        "unit_states": {
            unit_id: {
                "current_state": record["current_state"],
                "transition_cooldown_s": 0.0,
                "last_transition_time": (
                    -1e9 if record["last_transition_time_s"] is None else record["last_transition_time_s"]
                ),
            }
            for unit_id, record in active_records.items()
        },
        "rng_state": copy.deepcopy(morale_rng),
    }
    rout_state = context.get("rout_engine")
    if isinstance(rout_state, dict):
        rout_state["rng_state"] = copy.deepcopy(morale_rng)
    return legacy


@pytest.mark.parametrize("precipitation", ("none", "storm"))
def test_schema_valid_extreme_rain_factor_continues_exactly(
    precipitation: str,
) -> None:
    """Inactive and active finite extenders cannot false-reject the runtime."""
    prepared = _prepare_extreme_rain_factor_scenario(
        precipitation=precipitation,
    )
    source = _build(prepared)
    rain_rate = source.context.weather_engine.current.precipitation_rate
    assert (rain_rate > 0.0) is (precipitation == "storm")
    assert source.step() is False

    shooter = next(unit for unit in source.context.all_units() if unit.unit_type == "f16c")
    radar_source_indexes = {
        attachment.source_equipment_index
        for attachment in source.context.unit_sensor_attachments[shooter.entity_id]
        if attachment.sensor.sensor_type is SensorType.RADAR
    }
    assert radar_source_indexes
    decision = next(
        candidate
        for picture in source.context.tactical_targeting.latest_pictures()
        if (candidate := picture.decision_for(shooter.entity_id)) is not None
    )
    assert decision.contact_sensor_source_equipment_index in radar_source_indexes
    if rain_rate > 0.0:
        assert decision.contact_range_m == sys.float_info.max
        assert decision.sensing_range_m == sys.float_info.max

    checkpoint = source.engine.checkpoint()
    resumed = _build(prepared)
    resumed.engine.restore(checkpoint)
    assert resumed.engine.checkpoint() == checkpoint

    assert source.step() is False
    assert resumed.step() is False
    assert resumed.engine.checkpoint() == source.engine.checkpoint()


def test_battle_config_visibility_restores_exactly_and_rejects_mismatch() -> None:
    """A production BattleConfig visibility remains part of restore identity."""
    prepared = _prepare_battle_default_visibility_scenario()
    config = BattleConfig(default_visibility_m=1_234.0)
    source = prepared.build(
        VARIANT_ID,
        seed=115,
        max_ticks=10,
        strict_mode=True,
        battle_config=config,
    )
    assert source.step() is False
    decision = next(
        candidate for picture in source.context.tactical_targeting.latest_pictures() for candidate in picture.decisions
    )
    assert decision.visibility_bound_m == pytest.approx(1_234.0)

    checkpoint = source.engine.checkpoint()
    resumed = prepared.build(
        VARIANT_ID,
        seed=115,
        max_ticks=10,
        strict_mode=True,
        battle_config=config,
    )
    resumed.engine.restore(checkpoint)
    assert resumed.engine.checkpoint() == checkpoint
    assert source.step() is False
    assert resumed.step() is False
    assert resumed.engine.checkpoint() == source.engine.checkpoint()

    mismatched = prepared.build(
        VARIANT_ID,
        seed=115,
        max_ticks=10,
        strict_mode=True,
        battle_config=BattleConfig(default_visibility_m=1_235.0),
    )
    before = mismatched.engine.checkpoint()
    with pytest.raises(
        ValueError,
        match="targeting default visibility does not match",
    ):
        mismatched.engine.restore(checkpoint)
    assert mismatched.engine.checkpoint() == before


def test_historical_targeting_keeps_its_own_visibility_across_restore() -> None:
    """Later weather cannot rewrite or invalidate a retained interval."""
    prepared = _prepare_targeting_scenario()
    battle_config = BattleConfig(max_ticks_per_battle=1)
    source = prepared.build(
        VARIANT_ID,
        seed=115,
        max_ticks=10,
        strict_mode=True,
        battle_config=battle_config,
    )
    assert source.step() is False
    assert source.step() is False

    interval = source.context.tactical_targeting.prepared_interval
    assert interval is not None
    assert interval.engine_tick == 1
    assert interval.logical_time_s == 5.0
    assert source.context.clock.tick_count == 2
    assert source.context.clock.elapsed.total_seconds() == 305.0
    pictures = source.context.tactical_targeting.latest_pictures()
    recorded_visibility = {decision.visibility_bound_m for picture in pictures for decision in picture.decisions}
    assert recorded_visibility == {3_000.0}

    weather_state = source.context.weather_engine.get_state()
    weather_state["state"] = int(WeatherState.FOG)
    source.context.weather_engine.set_state(weather_state)
    assert source.context.weather_engine.current.visibility == 200.0

    checkpoint = source.engine.checkpoint()
    resumed = prepared.build(
        VARIANT_ID,
        seed=115,
        max_ticks=10,
        strict_mode=True,
        battle_config=battle_config,
    )
    resumed.engine.restore(checkpoint)

    assert resumed.engine.checkpoint() == checkpoint
    assert resumed.context.weather_engine.current.visibility == 200.0
    assert resumed.context.tactical_targeting.latest_pictures() == pictures

    assert source.step() is False
    assert resumed.step() is False
    assert resumed.engine.checkpoint() == source.engine.checkpoint()


@pytest.mark.parametrize("replacement_kind", ("missing", "replacement"))
def test_engine_rejects_targeting_owner_drift_before_work_or_state_io(
    replacement_kind: str,
) -> None:
    """The production engine cannot fall back after losing its bound owner."""
    prepared = _prepare_targeting_scenario()
    session = _build(prepared)
    checkpoint = session.engine.checkpoint()
    original = session.context.tactical_targeting
    assert isinstance(original, TacticalTargetingRuntime)
    replacement = (
        None
        if replacement_kind == "missing"
        else TacticalTargetingRuntime(
            sensing_aware_standoff_enabled=(original.sensing_aware_standoff_enabled),
            unit_sides=original.registered_unit_sides,
        )
    )
    session.context.tactical_targeting = replacement

    with pytest.raises(RuntimeError, match="targeting owner changed"):
        session.step()
    assert session.context.clock.tick_count == 0
    with pytest.raises(RuntimeError, match="targeting owner changed"):
        session.engine.get_state()
    with pytest.raises(RuntimeError, match="targeting owner changed"):
        session.engine.restore(checkpoint)
    assert session.context.clock.tick_count == 0


@pytest.mark.parametrize("mutation", ("missing", "extra", "wrong_side"))
def test_engine_rejects_targeting_registration_drift_before_work(
    mutation: str,
) -> None:
    """Owner identity cannot hide mutated registered unit/side topology."""
    session = _build(_prepare_targeting_scenario())
    context = session.context
    runtime = context.tactical_targeting
    registered = dict(runtime.registered_unit_sides)
    replacement = dict(registered)
    first_unit = sorted(replacement)[0]
    if mutation == "missing":
        replacement.pop(first_unit)
    elif mutation == "extra":
        replacement["forged-targeting-unit"] = "british"
    else:
        replacement[first_unit] = "forged-side"
    runtime.replace_registered_units(
        expected_current=registered,
        replacement=replacement,
    )
    before_clock = copy.deepcopy(context.clock.get_state())
    before_rng = copy.deepcopy(context.rng_manager.get_state())
    before_positions = {unit.entity_id: unit.position for unit in context.all_units()}

    with pytest.raises(ValueError, match="registration disagrees"):
        session.step()

    assert context.clock.get_state() == before_clock
    assert context.rng_manager.get_state() == before_rng
    assert {unit.entity_id: unit.position for unit in context.all_units()} == before_positions


@pytest.mark.parametrize(
    ("mutation", "error_match"),
    (
        ("duplicate", "duplicate entity_id"),
        ("wrong_bucket", "roster bucket disagrees"),
    ),
)
def test_engine_rejects_noncanonical_targeting_roster_before_work(
    mutation: str,
    error_match: str,
) -> None:
    """Roster corruption cannot pass through a lossy registration map."""
    session = _build(_prepare_targeting_scenario())
    context = session.context
    source_side = next(side for side, units in context.units_by_side.items() if units)
    unit = context.units_by_side[source_side][0]
    if mutation == "duplicate":
        context.units_by_side[source_side].append(unit)
    else:
        target_side = next(side for side in context.units_by_side if side != source_side)
        context.units_by_side[source_side].pop(0)
        context.units_by_side[target_side].append(unit)

    before_clock = copy.deepcopy(context.clock.get_state())
    before_rng = copy.deepcopy(context.rng_manager.get_state())
    before_positions = tuple(
        (side, id(roster_unit), roster_unit.position)
        for side, units in context.units_by_side.items()
        for roster_unit in units
    )
    before_targeting = context.tactical_targeting.get_state()

    with pytest.raises(ValueError, match=error_match):
        session.step()

    assert context.clock.get_state() == before_clock
    assert context.rng_manager.get_state() == before_rng
    assert (
        tuple(
            (side, id(roster_unit), roster_unit.position)
            for side, units in context.units_by_side.items()
            for roster_unit in units
        )
        == before_positions
    )
    assert context.tactical_targeting.get_state() == before_targeting


@pytest.mark.parametrize("mutation", ("context", "battle_config"))
def test_engine_rejects_targeting_default_visibility_drift(
    mutation: str,
) -> None:
    """The checkpoint and battle owners retain one immutable default."""
    session = _build(_prepare_targeting_scenario())
    checkpoint = session.engine.checkpoint()
    if mutation == "context":
        session.context.targeting_default_visibility_m += 1.0
    else:
        session.engine.battle_manager._config.default_visibility_m += 1.0

    with pytest.raises(RuntimeError, match="visibility binding changed"):
        session.step()
    with pytest.raises(RuntimeError, match="visibility binding changed"):
        session.engine.get_state()
    with pytest.raises(RuntimeError, match="visibility binding changed"):
        session.engine.restore(checkpoint)
    assert session.context.clock.tick_count == 0


@pytest.mark.parametrize(
    ("mutation", "error_match"),
    (
        ("missing", "must exactly cover"),
        ("unit_type", "detached from the exact unit type"),
        ("source_object", "detached from the exact unit type or equipment"),
        ("store_link", "does not match an exact weapon/ammunition"),
    ),
)
def test_checkpoint_rejects_forged_resolution_topology(
    mutation: str,
    error_match: str,
) -> None:
    """Checkpoint capture requires exact ordered resolution/live bindings."""
    session = _build(_prepare_targeting_scenario())
    unit = next(
        candidate
        for candidate in session.context.all_units()
        if any(
            resolution.disposition is ResolutionDisposition.NON_RUNTIME
            for resolution in session.context.equipment_resolutions[candidate.entity_id]
        )
    )
    resolutions = list(
        session.context.equipment_resolutions[unit.entity_id],
    )
    index = next(
        candidate
        for candidate, resolution in enumerate(resolutions)
        if resolution.disposition is ResolutionDisposition.NON_RUNTIME
    )
    if mutation == "missing":
        resolutions.pop(index)
    elif mutation == "unit_type":
        resolutions[index] = replace(
            resolutions[index],
            unit_type="forged-unit-type",
        )
    else:
        resolutions[index] = replace(
            resolutions[index],
            source_equipment=copy.deepcopy(
                resolutions[index].source_equipment,
            ),
        )
    if mutation == "store_link":
        linked = next(
            resolution
            for resolution in resolutions
            if (
                resolution.category is EquipmentCategory.WEAPON
                and resolution.disposition is ResolutionDisposition.ATTACHMENT
            )
        )
        resolutions[index] = replace(
            resolutions[index],
            disposition=ResolutionDisposition.STORE,
            reference_kind=linked.reference_kind,
            target_id="forged-ammunition",
            attached_to_equipment_index=linked.source_equipment_index,
            attached_to_target_id=linked.target_id,
            reason=None,
        )
    session.context.equipment_resolutions[unit.entity_id] = tuple(resolutions)

    with pytest.raises(ValueError, match=error_match):
        session.engine.checkpoint()


def test_format_115_no_fow_fresh_continuation_is_exact() -> None:
    prepared = _prepare_targeting_scenario()
    control = _build(prepared)
    assert control.step() is False

    checkpoint = control.engine.checkpoint()
    state = json.loads(checkpoint.decode("utf-8"))
    targeting = state["context"]["tactical_targeting"]
    assert state["checkpoint_version"] == 115
    assert targeting["prepared_interval"]["engine_tick"] == 1
    assert targeting["prepared_interval"]["logical_time_s"] == 5.0
    assert len(targeting["latest_pictures"]) == 1
    assert all(decision["consumable"] for decision in targeting["latest_pictures"][0]["decisions"])

    resumed = _build(prepared)
    resumed.engine.restore(checkpoint)
    assert resumed.engine.checkpoint() == checkpoint

    assert control.step() is False
    assert resumed.step() is False
    assert resumed.engine.checkpoint() == control.engine.checkpoint()


def test_environment_extended_sonar_checkpoint_and_continuation_are_exact(
    acoustic_extension_checkpoint: tuple[
        PreparedScenario,
        RuntimeSession,
        bytes,
    ],
) -> None:
    prepared, source, checkpoint = acoustic_extension_checkpoint
    resumed = _build(prepared)

    resumed.engine.restore(checkpoint)
    assert resumed.engine.checkpoint() == checkpoint
    assert source.step() is False
    assert resumed.step() is False
    assert resumed.engine.checkpoint() == source.engine.checkpoint()


def test_schema_valid_extended_thermal_checkpoint_and_continuation_are_exact(
    thermal_extension_checkpoint: tuple[
        PreparedScenario,
        RuntimeSession,
        bytes,
    ],
) -> None:
    prepared, source, checkpoint = thermal_extension_checkpoint
    resumed = _build(prepared)

    resumed.engine.restore(checkpoint)
    assert resumed.engine.checkpoint() == checkpoint
    assert source.step() is False
    assert resumed.step() is False
    assert resumed.engine.checkpoint() == source.engine.checkpoint()


def test_production_sensor_owner_exceeding_total_bound_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _build(_prepare_acoustic_extension_scenario())
    manager = session.engine.battle_manager
    monkeypatch.setattr(
        manager,
        "_targeting_observer_range_modifier",
        lambda _ctx, _shooter, *, evidence_cache=None: 10.0,
    )

    with pytest.raises(
        RuntimeError,
        match="exceeded the total environmental range bound",
    ):
        session.step()
    assert session.context.tactical_targeting.latest_pictures() == ()


@pytest.mark.parametrize(
    ("corruption", "error_match"),
    (
        (
            "second_attachment",
            "contact and sensing attachment identity must match",
        ),
        (
            "split_range",
            "contact and sensing ranges must match exactly",
        ),
        (
            "environment_bound",
            "exceeds the live sensor environmental range bound",
        ),
        (
            "live_visibility",
            "recorded visibility disagrees with the live environment",
        ),
    ),
)
def test_extended_sensor_checkpoint_corruption_rejects_atomically(
    acoustic_extension_checkpoint: tuple[
        PreparedScenario,
        RuntimeSession,
        bytes,
    ],
    corruption: str,
    error_match: str,
) -> None:
    prepared, source, checkpoint = acoustic_extension_checkpoint
    invalid = json.loads(checkpoint.decode("utf-8"))
    reference = next(
        decision
        for picture in invalid["context"]["tactical_targeting"]["latest_pictures"]
        for decision in picture["decisions"]
        if decision["contact_sensor_id"] == "active_sonar"
    )
    copies = _matching_targeting_decision_states(invalid, reference)

    corvette = next(unit for unit in source.context.all_units() if unit.entity_id == reference["shooter_id"])
    attachments = source.context.unit_sensor_attachments[corvette.entity_id]
    sonar = next(attachment for attachment in attachments if attachment.sensor.sensor_type is SensorType.ACTIVE_SONAR)
    if corruption == "second_attachment":
        radar = next(attachment for attachment in attachments if attachment.sensor.sensor_type is SensorType.RADAR)
        for decision in copies:
            decision["sensing_sensor_source_equipment_index"] = radar.source_equipment_index
            decision["sensing_sensor_id"] = radar.sensor_id
            decision["sensing_sensor_modeled_role"] = SensorModeledRole.SHIP_SURFACE_SEARCH_RADAR.value
    elif corruption == "split_range":
        for decision in copies:
            decision["sensing_range_m"] = decision["contact_range_m"] + 1.0
    elif corruption == "live_visibility":
        for decision in copies:
            decision["visibility_bound_m"] += 1.0
    else:
        forged_range = (
            sensor_environment_range_upper_bound_m(
                policy=sensor_environment_range_policy(
                    calibration=source.context.cal_flat,
                    observer_domain=corvette.domain,
                    observer_altitude_m=float(
                        corvette.position.altitude or 0.0,
                    ),
                    observer_acclimatized=getattr(
                        corvette,
                        "acclimatized",
                        False,
                    ),
                ),
                sensor_type=sonar.sensor.sensor_type,
                condition_adjusted_range_m=sonar.sensor.effective_range,
            )
            + 1.0
        )
        for decision in copies:
            decision["contact_range_m"] = forged_range
            decision["sensing_range_m"] = forged_range

    target = _build(prepared)
    before = target.engine.checkpoint()
    with pytest.raises(ValueError, match=error_match):
        target.engine.set_state(invalid)
    assert target.engine.checkpoint() == before


def test_targetless_picture_visibility_corruption_rejects_atomically() -> None:
    prepared = _prepare_targeting_scenario(separation_m=5_000.0)
    source = _build(prepared)
    assert source.step() is False
    invalid = _decoded_checkpoint(source)
    reference = next(
        decision
        for picture in invalid["context"]["tactical_targeting"][
            "latest_pictures"
        ]
        for decision in picture["decisions"]
        if decision["target_id"] is None
    )
    for decision in _matching_targeting_decision_states(invalid, reference):
        decision["visibility_bound_m"] += 1.0

    target = _build(prepared)
    before = target.engine.checkpoint()
    with pytest.raises(
        ValueError,
        match="recorded visibility disagrees with the live environment",
    ):
        target.engine.set_state(invalid)
    assert target.engine.checkpoint() == before


def test_fow_witness_range_retains_live_sensor_ceiling(
    older_ring_checkpoint: tuple[PreparedScenario, bytes, str],
) -> None:
    prepared, checkpoint, _outside_member_id = older_ring_checkpoint
    invalid = json.loads(checkpoint.decode("utf-8"))
    reference = next(
        decision
        for picture in invalid["context"]["tactical_targeting"]["latest_pictures"]
        for decision in picture["decisions"]
        if decision["contact_sensor_source_equipment_index"] is not None
    )
    copies = _matching_targeting_decision_states(invalid, reference)

    target = _build(prepared)
    attachment = next(
        candidate
        for candidate in target.context.unit_sensor_attachments[reference["shooter_id"]]
        if (
            candidate.source_equipment_index == reference["contact_sensor_source_equipment_index"]
            and candidate.sensor_id == reference["contact_sensor_id"]
        )
    )
    forged_range = attachment.sensor.effective_range + 1.0
    shooter = target.context._morale_roster()[reference["shooter_id"]]
    assert forged_range < sensor_environment_range_upper_bound_m(
        policy=sensor_environment_range_policy(
            calibration=target.context.cal_flat,
            observer_domain=shooter.domain,
            observer_altitude_m=float(shooter.position.altitude or 0.0),
            observer_acclimatized=getattr(shooter, "acclimatized", False),
        ),
        sensor_type=attachment.sensor.sensor_type,
        condition_adjusted_range_m=attachment.sensor.effective_range,
    )
    for decision in copies:
        decision["distance_m"] = forged_range
        decision["contact_range_m"] = forged_range
        decision["sensing_range_m"] = forged_range

    before = target.engine.checkpoint()
    with pytest.raises(
        ValueError,
        match="FOW witness range exceeds the live sensor range",
    ):
        target.engine.set_state(invalid)
    assert target.engine.checkpoint() == before


def test_checkpoint_staged_weather_binds_recorded_visibility_atomically(
    acoustic_extension_checkpoint: tuple[
        PreparedScenario,
        RuntimeSession,
        bytes,
    ],
) -> None:
    prepared, _source, checkpoint = acoustic_extension_checkpoint
    invalid = json.loads(checkpoint.decode("utf-8"))
    invalid["context"]["weather_engine"]["state"] = int(WeatherState.FOG)

    target = _build(prepared)
    before = target.engine.checkpoint()
    with pytest.raises(
        ValueError,
        match="recorded visibility disagrees with the live environment",
    ):
        target.engine.set_state(invalid)
    assert target.engine.checkpoint() == before


def test_non_fow_optical_attachment_cannot_exceed_recorded_visibility() -> None:
    prepared = _prepare_optical_attachment_scenario()
    source = _build(prepared)
    assert source.step() is False
    invalid = _decoded_checkpoint(source)
    shooter = next(unit for unit in source.context.all_units() if unit.unit_type == "t72m")
    reference = next(
        decision
        for picture in invalid["context"]["tactical_targeting"]["latest_pictures"]
        for decision in picture["decisions"]
        if decision["shooter_id"] == shooter.entity_id
    )
    attachment = next(
        candidate
        for candidate in source.context.unit_sensor_attachments[shooter.entity_id]
        if candidate.sensor_id == reference["contact_sensor_id"]
    )
    assert attachment.sensor.sensor_type is SensorType.NVG
    assert 0.0 < reference["contact_range_m"] <= 300.0
    assert reference["visibility_bound_m"] == pytest.approx(300.0)
    for decision in _matching_targeting_decision_states(invalid, reference):
        decision["contact_range_m"] = 301.0
        decision["sensing_range_m"] = 301.0

    target = _build(prepared)
    before = target.engine.checkpoint()
    with pytest.raises(
        ValueError,
        match="contact optical range exceeds the recorded visibility bound",
    ):
        target.engine.set_state(invalid)
    assert target.engine.checkpoint() == before


def test_fow_optical_history_cannot_exceed_checkpoint_staged_visibility(
    older_ring_checkpoint: tuple[PreparedScenario, bytes, str],
) -> None:
    """Restore rejects optical witness authority beyond staged visibility."""
    prepared, checkpoint, _outside_member_id = older_ring_checkpoint
    invalid = json.loads(checkpoint.decode("utf-8"))
    invalid["context"]["weather_engine"]["state"] = int(WeatherState.FOG)
    decisions = [
        decision
        for picture in invalid["context"]["tactical_targeting"]["latest_pictures"]
        for decision in picture["decisions"]
    ]
    decisions.extend(
        decision
        for summary in invalid["context"]["movement_diagnostics"]["units"].values()
        for observation in summary["recent_observations"]
        if (decision := observation["targeting_decision"]) is not None
    )
    optical_fow = [
        decision
        for decision in decisions
        if (
            decision["target_id"] is not None
            and decision["contact_source"] == "FOW_OBSERVER_WITNESS"
            and decision["contact_sensor_id"] is not None
        )
    ]
    assert optical_fow
    assert all(decision["contact_range_m"] > 200.0 for decision in optical_fow)
    for decision in optical_fow:
        decision["visibility_bound_m"] = 200.0
        decision["disposition"] = "FIRE_CONTROL_RANGE_EXCEEDED"
        decision["engagement_solution_valid"] = False
        decision["authorized_standoff_m"] = 0.0
        decision["hold_authorized"] = False
        if decision["fire_control_source"] == "DIRECT_VISUAL":
            decision["fire_control_range_m"] = 200.0

    target = _build(prepared)
    before = target.engine.checkpoint()
    with pytest.raises(
        ValueError,
        match="contact optical range exceeds the recorded visibility bound",
    ):
        target.engine.set_state(invalid)
    assert target.engine.checkpoint() == before


def test_pristine_versionless_omission_migrates_to_unprepared_state() -> None:
    prepared = _prepare_targeting_scenario()
    source = _build(prepared)
    assert source.context.tactical_targeting.prepared_interval is None
    current_checkpoint = source.engine.checkpoint()

    current_resumed = _build(prepared)
    current_resumed.engine.restore(current_checkpoint)
    assert current_resumed.engine.checkpoint() == current_checkpoint

    versionless = _versionless_pristine_checkpoint(
        _decoded_checkpoint(source),
    )

    resumed = _build(prepared)
    resumed.engine.set_state(versionless)
    assert resumed.context.tactical_targeting.prepared_interval is None
    assert resumed.engine.checkpoint() == source.engine.checkpoint()


def test_live_attachment_corruption_rejects_before_runtime_mutation() -> None:
    prepared = _prepare_targeting_scenario(separation_m=2_500.0)
    source = _build(prepared)
    assert source.step() is False
    valid = _decoded_checkpoint(source)
    decision = next(
        candidate
        for candidate in valid["context"]["tactical_targeting"]["latest_pictures"][0]["decisions"]
        if candidate["weapon_id"] is not None
    )
    decision["weapon_id"] = "not-the-loaded-weapon"

    target = _build(prepared)
    before = target.engine.checkpoint()
    with pytest.raises(
        ValueError,
        match="weapon identity does not resolve",
    ):
        target.engine.set_state(valid)
    assert target.engine.checkpoint() == before


@pytest.mark.parametrize(
    ("field", "replacement", "error_match"),
    (
        (
            "target_id",
            "missing-target",
            "omits the decision target",
        ),
        (
            "weapon_id",
            "missing-weapon",
            "weapon identity does not resolve",
        ),
        (
            "weapon_source_equipment_index",
            9_999,
            "weapon identity does not resolve",
        ),
        (
            "ammunition_id",
            "missing-ammunition",
            "ammunition identity is absent",
        ),
        (
            "contact_sensor_source_equipment_index",
            9_999,
            "contact sensor identity does not resolve",
        ),
        (
            "contact_sensor_id",
            "missing-sensor",
            "contact sensor identity does not resolve",
        ),
        (
            "contact_sensor_modeled_role",
            "night_vision",
            "contact sensor identity does not resolve",
        ),
        (
            "target_id",
            "__outside_retained_battle__",
            "omits the decision target",
        ),
    ),
)
def test_older_ring_corruption_rejects_atomically(
    older_ring_checkpoint: tuple[PreparedScenario, bytes, str],
    field: str,
    replacement: object,
    error_match: str,
) -> None:
    prepared, checkpoint, outside_member_id = older_ring_checkpoint
    invalid = json.loads(checkpoint.decode("utf-8"))
    latest_before = copy.deepcopy(
        invalid["context"]["tactical_targeting"]["latest_pictures"],
    )
    decision = _older_ring_targeting_decision(invalid)
    decision[field] = outside_member_id if replacement == "__outside_retained_battle__" else replacement
    if field.startswith("contact_sensor_"):
        decision[field.replace("contact_", "sensing_", 1)] = replacement
    assert invalid["context"]["tactical_targeting"]["latest_pictures"] == latest_before

    target = _build(prepared)
    before = target.engine.checkpoint()
    with pytest.raises(ValueError, match=error_match):
        target.engine.set_state(invalid)
    assert target.engine.checkpoint() == before


def test_valid_older_ring_restore_continues_deterministically(
    older_ring_checkpoint: tuple[PreparedScenario, bytes, str],
) -> None:
    prepared, checkpoint, _outside_member_id = older_ring_checkpoint
    first = _build(prepared)
    second = _build(prepared)

    first.engine.restore(checkpoint)
    second.engine.restore(checkpoint)
    assert first.engine.checkpoint() == second.engine.checkpoint()
    assert (
        _older_ring_targeting_decision(
            _decoded_checkpoint(first),
        )["engine_tick"]
        < first.context.clock.tick_count
    )

    assert first.step() is False
    assert second.step() is False
    assert first.engine.checkpoint() == second.engine.checkpoint()


def test_fow_restore_marks_targeting_history_non_consumable() -> None:
    prepared = _prepare_targeting_scenario(fog_of_war=True)
    source = _build(prepared)
    assert source.step() is False
    saved = _decoded_checkpoint(source)
    saved_decisions = saved["context"]["tactical_targeting"]
    saved_decisions = saved_decisions["latest_pictures"][0]["decisions"]
    assert all(decision["consumable"] for decision in saved_decisions)

    resumed = _build(prepared)
    resumed.engine.set_state(saved)
    picture = resumed.context.tactical_targeting.latest_pictures()[0]
    assert all(not decision.consumable for decision in picture.decisions)
    for decision in picture.decisions:
        assert (
            resumed.context.tactical_targeting.decision_for(
                engine_tick=decision.engine_tick,
                battle_id=decision.battle_id,
                shooter_id=decision.shooter_id,
            )
            is None
        )

    assert resumed.step() is False
    current = resumed.context.tactical_targeting.latest_pictures()[0]
    assert current.engine_tick == 2
    assert all(decision.consumable for decision in current.decisions)


def test_detection_engine_rng_mirror_rejects_tamper_atomically() -> None:
    """The generic detection owner cannot override RNGManager on restore."""
    prepared = _prepare_targeting_scenario(
        fog_of_war=True,
        separation_m=1_500.0,
    )
    source = _build(prepared)
    assert source.step() is False
    invalid = _decoded_checkpoint(source)
    context_state = invalid["context"]
    authoritative = context_state["rng"]["streams"]["detection"]
    assert context_state["fog_of_war"]["rng_state"] == authoritative
    assert context_state["detection_engine"]["rng_state"] == authoritative
    context_state["detection_engine"]["rng_state"]["state"]["state"] += 1

    target = _build(prepared)
    before = target.engine.checkpoint()
    with pytest.raises(
        ValueError,
        match="DetectionEngine RNG mirror disagrees with RNGManager DETECTION",
    ):
        target.engine.set_state(invalid)
    assert target.engine.checkpoint() == before


def test_reinforcement_targeting_failure_rolls_back_every_registration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare_targeting_scenario(reinforcement=True)
    session = _build(prepared)
    context = session.context
    roster_before = tuple(unit.entity_id for unit in context.all_units())
    weapons_before = dict(context.unit_weapons)
    sensors_before = dict(context.unit_sensor_attachments)
    resolutions_before = dict(context.equipment_resolutions)
    morale_before = context.morale_runtime.get_state()
    movement_before = context.movement_diagnostics.get_state()
    targeting_before = context.tactical_targeting.get_state()

    original_register = context.tactical_targeting.register_units

    def fail_after_targeting_registration(unit_sides) -> None:
        original_register(unit_sides)
        raise RuntimeError("injected targeting registration failure")

    monkeypatch.setattr(
        context.tactical_targeting,
        "register_units",
        fail_after_targeting_registration,
    )
    with pytest.raises(
        RuntimeError,
        match="injected targeting registration failure",
    ):
        session.engine.campaign_manager.check_reinforcements(
            context,
            0.0,
        )

    assert tuple(unit.entity_id for unit in context.all_units()) == roster_before
    assert context.unit_weapons == weapons_before
    assert context.unit_sensor_attachments == sensors_before
    assert context.equipment_resolutions == resolutions_before
    assert context.morale_runtime.get_state() == morale_before
    assert context.movement_diagnostics.get_state() == movement_before
    assert context.tactical_targeting.get_state() == targeting_before


def test_reinforcement_topology_fresh_restore_and_continuation_are_exact() -> None:
    prepared = _prepare_targeting_scenario(reinforcement=True)
    source = _build(prepared)
    arrived = source.engine.campaign_manager.check_reinforcements(
        source.context,
        0.0,
    )
    assert len(arrived) == 1
    reinforcement_id = arrived[0].entity_id
    assert reinforcement_id in source.context.unit_sensor_attachments
    assert source.context.tactical_targeting.registered_unit_sides[reinforcement_id] == "british"

    checkpoint = source.engine.checkpoint()
    resumed = _build(prepared)
    resumed.engine.restore(checkpoint)
    assert resumed.engine.checkpoint() == checkpoint
    assert reinforcement_id in resumed.context.unit_sensor_attachments

    assert source.step() is False
    assert resumed.step() is False
    assert resumed.engine.checkpoint() == source.engine.checkpoint()


def test_targeting_history_survives_reinforcement_invalidation_and_continues(
    history_reinforcement_checkpoint: tuple[
        PreparedScenario,
        RuntimeSession,
        bytes,
    ],
) -> None:
    prepared, source, checkpoint = history_reinforcement_checkpoint
    resumed = _build(prepared)

    resumed.engine.restore(checkpoint)
    assert resumed.engine.checkpoint() == checkpoint
    assert resumed.context.tactical_targeting.prepared_interval is None
    assert resumed.context.tactical_targeting.latest_pictures() == ()

    assert source.step() is False
    assert resumed.step() is False
    assert resumed.engine.checkpoint() == source.engine.checkpoint()


@pytest.mark.parametrize(
    ("corruption", "error_match"),
    (
        ("omit_target", "omits the decision target"),
        ("reorder", "canonical order"),
        ("unknown_member", "outside the checkpoint force roster"),
        ("weapon_source", "weapon identity does not resolve"),
    ),
)
def test_unprepared_targeting_history_corruption_rejects_atomically(
    history_reinforcement_checkpoint: tuple[
        PreparedScenario,
        RuntimeSession,
        bytes,
    ],
    corruption: str,
    error_match: str,
) -> None:
    prepared, _source, checkpoint = history_reinforcement_checkpoint
    invalid = json.loads(checkpoint.decode("utf-8"))
    observation = _targeting_observation(invalid)
    membership = observation["targeting_membership"]
    decision = observation["targeting_decision"]
    if corruption == "omit_target":
        membership["unit_ids"].remove(decision["target_id"])
    elif corruption == "reorder":
        membership["unit_ids"] = list(reversed(membership["unit_ids"]))
    elif corruption == "unknown_member":
        membership["unit_ids"].append("zz-unknown-member")
    else:
        decision["weapon_source_equipment_index"] = 9_999

    target = _build(prepared)
    before = target.engine.checkpoint()
    with pytest.raises(ValueError, match=error_match):
        target.engine.set_state(invalid)
    assert target.engine.checkpoint() == before


def test_format_114_and_elapsed_versionless_omission_reject_atomically() -> None:
    prepared = _prepare_targeting_scenario()
    source = _build(prepared)
    assert source.step() is False
    current = _decoded_checkpoint(source)

    target = _build(prepared)
    before = target.engine.checkpoint()
    old_version = copy.deepcopy(current)
    old_version["checkpoint_version"] = 114
    with pytest.raises(
        ValueError,
        match="Unsupported checkpoint version 114; expected 115",
    ):
        target.engine.set_state(old_version)
    assert target.engine.checkpoint() == before

    versionless = copy.deepcopy(current)
    versionless.pop("checkpoint_version")
    versionless["context"].pop("tactical_targeting")
    with pytest.raises(
        ValueError,
        match="only at pristine tick 0",
    ):
        target.engine.set_state(versionless)
    assert target.engine.checkpoint() == before
