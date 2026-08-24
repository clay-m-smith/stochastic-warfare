"""Focused production controls for the Phase 115 targeting boundary."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
import math
from pathlib import Path
from typing import Any

import pytest

from stochastic_warfare.core.events import Event
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.detection.sensors import SensorInstance
from stochastic_warfare.simulation.battle import BattleContext
from stochastic_warfare.simulation.loadouts import (
    SensorModeledRole,
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
    ContactSource,
    FireControlSource,
    TacticalEngagementRevalidationOutcome,
    TacticalTargetingDecision,
    TacticalTargetingRuntime,
    TargetingDisposition,
)


ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data"
SOURCE_LABEL = str(
    (DATA_DIR / "eras" / "ww1" / "scenarios" / "jutland" / "scenario.yaml").resolve(),
)


def _scenario(
    *,
    blue_units: list[dict[str, Any]],
    red_units: list[dict[str, Any]],
    fog_of_war: bool = False,
    cbrn: bool = False,
    calibration: dict[str, Any] | None = None,
    era: str = "ww1",
) -> CampaignScenarioConfig:
    overrides: dict[str, Any] = {
        "defensive_sides": [],
        "enable_fog_of_war": fog_of_war,
        "enable_sensing_aware_standoff": True,
        "target_selection_mode": "closest",
    }
    if calibration is not None:
        overrides.update(calibration)
    return CampaignScenarioConfig.model_validate(
        {
            "name": "Phase 115 focused targeting controls",
            "date": ("2004-11-10T12:00:00Z" if era == "modern" else "1916-06-01T12:00:00Z"),
            "duration_hours": 1.0,
            "era": era,
            "tick_resolution": {
                "strategic_s": 3_600.0,
                "operational_s": 300.0,
                "tactical_s": 5.0,
            },
            "weather_conditions": {
                "visibility_m": 5_000.0,
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
                {"side": "blue", "units": blue_units},
                {"side": "red", "units": red_units},
            ],
            "objectives": [],
            "victory_conditions": [],
            "cbrn_config": {"enable_cbrn": True} if cbrn else None,
            "calibration_overrides": overrides,
        }
    )


def _unit(
    unit_type: str,
    position: tuple[float, float, float],
) -> dict[str, Any]:
    return {
        "unit_type": unit_type,
        "count": 1,
        "position": list(position),
    }


def _duel(
    shooter_type: str,
    target_type: str,
    *,
    target_position: tuple[float, float, float] = (1_000.0, 2_000.0, 0.0),
    fog_of_war: bool = False,
    cbrn: bool = False,
    calibration: dict[str, Any] | None = None,
) -> CampaignScenarioConfig:
    return _scenario(
        blue_units=[_unit(shooter_type, (1_000.0, 1_000.0, 0.0))],
        red_units=[_unit(target_type, target_position)],
        fog_of_war=fog_of_war,
        cbrn=cbrn,
        calibration=calibration,
    )


def _prepare(
    config: CampaignScenarioConfig,
    *,
    variant_id: str,
) -> PreparedScenario:
    return SimulationRuntimeFactory().prepare_config(
        config,
        DATA_DIR,
        (AnalysisVariant(variant_id=variant_id),),
        source_label=SOURCE_LABEL,
    )


def _build(
    prepared: PreparedScenario,
    *,
    variant_id: str,
    seed: int = 115,
) -> RuntimeSession:
    return prepared.build(
        variant_id,
        seed=seed,
        max_ticks=10,
        strict_mode=True,
    )


def _unit_of_type(session: RuntimeSession, unit_type: str):
    return next(unit for unit in session.context.all_units() if unit.unit_type == unit_type)


def _latest_decision(
    session: RuntimeSession,
    shooter_id: str,
) -> TacticalTargetingDecision:
    runtime = session.context.tactical_targeting
    matches = tuple(
        decision for picture in runtime.latest_pictures() if (decision := picture.decision_for(shooter_id)) is not None
    )
    assert len(matches) == 1
    decision = matches[0]
    assert isinstance(decision, TacticalTargetingDecision)
    assert decision is runtime.decision_for(
        engine_tick=decision.engine_tick,
        battle_id=decision.battle_id,
        shooter_id=shooter_id,
    )
    return decision


def _outcome_for(
    session: RuntimeSession,
    decision: TacticalTargetingDecision,
) -> TacticalEngagementRevalidationOutcome | None:
    return session.context.tactical_targeting.engagement_revalidation_for(
        engine_tick=decision.engine_tick,
        battle_id=decision.battle_id,
        shooter_id=decision.shooter_id,
    )


def test_catalog_naval_search_optic_and_live_director_controls() -> None:
    """Search optics cannot direct gunfire; the mapped director can."""
    search_variant = "phase115-search-optic-control"
    search_prepared = _prepare(
        _duel("g_class_destroyer", "konig_bb", fog_of_war=True),
        variant_id=search_variant,
    )
    search = _build(search_prepared, variant_id=search_variant)
    destroyer = _unit_of_type(search, "g_class_destroyer")
    search_attachment = search.context.unit_sensor_attachments[destroyer.entity_id][0]
    assert search_attachment.source_equipment.name == "Field Binoculars"
    assert search_attachment.modeled_role is (SensorModeledRole.VISUAL_OBSERVATION)
    assert search_attachment.compatible_weapon_source_indexes == ()

    assert search.step() is False
    search_decision = _latest_decision(search, destroyer.entity_id)
    assert search_decision.contact_source is ContactSource.FOW_OBSERVER_WITNESS
    assert search_decision.contact_sensor_id == "binoculars_ww1"
    assert search_decision.contact_sensor_modeled_role is (SensorModeledRole.VISUAL_OBSERVATION)
    assert search_decision.disposition is (TargetingDisposition.NO_COMPATIBLE_FIRE_CONTROL)
    assert search_decision.fire_control_source is FireControlSource.NONE
    assert not search_decision.can_engage
    assert _outcome_for(search, search_decision) is None

    director_variant = "phase115-naval-director-control"
    director_prepared = _prepare(
        _duel("iron_duke_bb", "konig_bb", fog_of_war=True),
        variant_id=director_variant,
    )
    valid = _build(director_prepared, variant_id=director_variant)
    battleship = _unit_of_type(valid, "iron_duke_bb")
    director = valid.context.unit_sensor_attachments[battleship.entity_id][0]
    assert director.source_equipment.name == "Barr & Stroud Rangefinder"
    assert director.modeled_role is SensorModeledRole.NAVAL_VISUAL_DIRECTOR
    assert director.compatible_weapon_source_indexes

    assert valid.step() is False
    valid_decision = _latest_decision(valid, battleship.entity_id)
    assert valid_decision.contact_source is ContactSource.FOW_OBSERVER_WITNESS
    assert valid_decision.contact_sensor_modeled_role is (SensorModeledRole.NAVAL_VISUAL_DIRECTOR)
    assert valid_decision.fire_control_source is (FireControlSource.SENSOR_ATTACHMENT)
    assert valid_decision.fire_control_sensor_modeled_role is (SensorModeledRole.NAVAL_VISUAL_DIRECTOR)
    assert valid_decision.weapon_source_equipment_index in (director.compatible_weapon_source_indexes)
    assert valid_decision.disposition is (TargetingDisposition.VALID_STANDOFF_HOLD)
    assert valid_decision.can_engage
    valid_outcome = _outcome_for(valid, valid_decision)
    assert isinstance(valid_outcome, TacticalEngagementRevalidationOutcome)
    assert valid_outcome.revalidation_passed
    assert valid_outcome.target_id == valid_decision.target_id
    assert valid_outcome.weapon_id == valid_decision.weapon_id
    assert valid_outcome.ammunition_id == valid_decision.ammunition_id


def test_picture_validates_only_selected_multi_solution_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each shooter publishes one validated winner, not every alternative."""
    variant = "phase115-deferred-targeting-decision"
    session = _build(
        _prepare(
            _duel("iron_duke_bb", "konig_bb"),
            variant_id=variant,
        ),
        variant_id=variant,
    )
    context = session.context
    shooter = _unit_of_type(session, "iron_duke_bb")
    target = _unit_of_type(session, "konig_bb")
    assert len(context.unit_weapons[shooter.entity_id]) > 1
    assert context.unit_sensor_attachments[shooter.entity_id]

    validated_keys: list[tuple[int, str, str]] = []
    real_post_init = TacticalTargetingDecision.__post_init__

    def _recording_post_init(decision: TacticalTargetingDecision) -> None:
        real_post_init(decision)
        validated_keys.append(decision.key)

    monkeypatch.setattr(
        TacticalTargetingDecision,
        "__post_init__",
        _recording_post_init,
    )
    battle = BattleContext(
        battle_id="battle-deferred-targeting-decision",
        start_tick=0,
        start_time=context.clock.current_time,
        involved_sides=["blue", "red"],
        unit_ids={shooter.entity_id, target.entity_id},
    )

    session.engine.battle_manager.prepare_tactical_interval(
        context,
        (battle,),
        5.0,
    )
    picture = context.tactical_targeting.latest_picture(battle.battle_id)
    assert picture is not None
    assert len(validated_keys) == len(picture.decisions) == 2
    assert set(validated_keys) == {decision.key for decision in picture.decisions}

    decision = picture.decision_for(shooter.entity_id)
    assert decision is not None
    assert decision.target_id == target.entity_id
    assert decision.can_engage
    assert decision.contact_source is ContactSource.NON_FOW_LOCAL_OBSERVATION
    # The unaided-contact identity sorts before the concurrent catalog sensor
    # contact; the chosen weapon and director still come from typed loadouts.
    assert decision.contact_sensor_source_equipment_index is None
    assert decision.contact_sensor_id is None
    assert decision.weapon_source_equipment_index is not None
    assert decision.fire_control_source is FireControlSource.SENSOR_ATTACHMENT


def test_battle_tick_requires_complete_prepublished_picture_before_mutation() -> None:
    """Direct battle execution cannot construct or partially publish a picture."""
    variant = "phase115-complete-picture-guard"
    session = _build(
        _prepare(
            _duel("iron_duke_bb", "konig_bb"),
            variant_id=variant,
        ),
        variant_id=variant,
    )
    context = session.context
    shooter = _unit_of_type(session, "iron_duke_bb")
    target = _unit_of_type(session, "konig_bb")
    battle = BattleContext(
        battle_id="battle-complete-picture-guard",
        start_tick=0,
        start_time=context.clock.current_time,
        involved_sides=["blue", "red"],
        unit_ids={shooter.entity_id, target.entity_id},
    )
    targeting_before = context.tactical_targeting.get_state()
    ticks_before = battle.ticks_executed
    elapsed_before = battle.battle_elapsed_s

    with pytest.raises(RuntimeError, match="complete prepublished"):
        session.engine.battle_manager.execute_tick(context, battle, 5.0)

    assert battle.ticks_executed == ticks_before
    assert battle.battle_elapsed_s == elapsed_before
    assert context.tactical_targeting.get_state() == targeting_before


@pytest.mark.parametrize("selection_mode", ("closest", "threat_scored"))
def test_tied_target_contact_weapon_selection_is_weapon_first_and_exact(
    selection_mode: str,
) -> None:
    """The public interval boundary applies the complete canonical tie key."""
    variant = f"phase115-targeting-tie-contract-{selection_mode}"
    target_offset_m = math.sqrt(500.0**2 - 50.0**2)
    config = _scenario(
        blue_units=[
            _unit("ah1w", (1_000.0, 1_000.0, 0.0)),
            _unit("ac130u", (9_000.0, 9_000.0, 1_000.0)),
        ],
        red_units=[
            _unit("t72m", (950.0, 1_000.0 + target_offset_m, 0.0)),
            _unit("t72m", (1_050.0, 1_000.0 + target_offset_m, 0.0)),
        ],
        fog_of_war=True,
        calibration={"target_selection_mode": selection_mode},
        era="modern",
    )

    def resolve_once() -> tuple[object, ...]:
        session = _build(
            _prepare(config, variant_id=variant),
            variant_id=variant,
            seed=91_115,
        )
        context = session.context
        shooter = _unit_of_type(session, "ah1w")
        donor = _unit_of_type(session, "ac130u")
        targets = tuple(
            sorted(
                (unit for unit in context.units_by_side["red"] if unit.unit_type == "t72m"),
                key=lambda unit: unit.entity_id,
            )
        )
        assert len(targets) == 2
        assert all(
            math.dist(
                (
                    shooter.position.easting,
                    shooter.position.northing,
                    shooter.position.altitude,
                ),
                (
                    target.position.easting,
                    target.position.northing,
                    target.position.altitude,
                ),
            )
            == pytest.approx(500.0)
            for target in targets
        )
        # Factory IDs normally contain their original side.  Re-home the two
        # exact live targets under an equally valid runtime topology whose side
        # order opposes its ID order, then install the public targeting owner
        # for that topology.  This makes target side independently observable
        # in the manager-boundary tie rather than accidentally redundant.
        targets[0].side = "zulu"
        targets[1].side = "amber"
        context.units_by_side.pop("red")
        context.units_by_side["zulu"] = [targets[0]]
        context.units_by_side["amber"] = [targets[1]]
        context.tactical_targeting = TacticalTargetingRuntime(
            sensing_aware_standoff_enabled=True,
            unit_sides={unit.entity_id: side for side, units in context.units_by_side.items() for unit in units},
        )

        weapons = context.unit_weapons[shooter.entity_id]
        tow = next(attachment for attachment in weapons if attachment.modeled_role is WeaponModeledRole.ANTI_ARMOR)
        hellfire = next(
            attachment for attachment in weapons if attachment.modeled_role is WeaponModeledRole.AIR_TO_GROUND_MISSILE
        )
        assert tow.source_equipment_index == 1
        assert hellfire.source_equipment_index == 2
        assert tow.weapon.definition.max_range_m >= 1_500.0
        assert hellfire.weapon.definition.max_range_m >= 1_500.0

        shooter_sensors = context.unit_sensor_attachments[shooter.entity_id]
        director = next(
            attachment
            for attachment in shooter_sensors
            if attachment.modeled_role is SensorModeledRole.AIRBORNE_GROUND_VISUAL_TARGETING
        )
        assert director.source_equipment_index == 4
        assert director.compatible_weapon_source_indexes == (hellfire.source_equipment_index,)

        observer_template = next(
            attachment
            for attachment in context.unit_sensor_attachments[donor.entity_id]
            if attachment.modeled_role is SensorModeledRole.AIRBORNE_LOW_LIGHT_OBSERVATION
        )
        assert observer_template.source_equipment_index == 5
        assert observer_template.compatible_weapon_source_indexes == ()
        observer_equipment = deepcopy(observer_template.source_equipment)
        observer_sensor = SensorInstance(
            observer_template.sensor.definition,
            observer_equipment,
        )
        observer = replace(
            observer_template,
            sensor=observer_sensor,
            source_equipment=observer_equipment,
        )
        # This deliberately assembled test topology uses two real definitions
        # and their real typed roles.  No shipped unit mapping is changed: the
        # donor supplies a production-built observation attachment solely to
        # make the otherwise catalog-absent adversarial tie reachable.
        shooter.equipment[observer.source_equipment_index] = observer.source_equipment
        assembled_sensors = tuple(
            sorted(
                (*shooter_sensors, observer),
                key=lambda attachment: (
                    attachment.source_equipment_index,
                    attachment.sensor_id,
                ),
            )
        )
        context.unit_sensor_attachments[shooter.entity_id] = assembled_sensors
        context.unit_sensors[shooter.entity_id] = tuple(attachment.sensor for attachment in assembled_sensors)

        battles = (
            BattleContext(
                battle_id="battle-tie-left",
                start_tick=0,
                start_time=context.clock.current_time,
                involved_sides=["blue", "zulu"],
                unit_ids={shooter.entity_id, targets[0].entity_id},
            ),
            BattleContext(
                battle_id="battle-tie-right",
                start_tick=0,
                start_time=context.clock.current_time,
                involved_sides=["amber", "blue"],
                unit_ids={shooter.entity_id, targets[1].entity_id},
            ),
            BattleContext(
                battle_id="battle-tie-mixed",
                start_tick=0,
                start_time=context.clock.current_time,
                involved_sides=["amber", "blue", "zulu"],
                unit_ids={
                    shooter.entity_id,
                    targets[0].entity_id,
                    targets[1].entity_id,
                },
            ),
        )
        canonical = session.engine.battle_manager.prepare_tactical_interval(
            context,
            tuple(reversed(battles)),
            5.0,
        )
        assert tuple(battle.battle_id for battle in canonical) == (
            "battle-tie-left",
            "battle-tie-mixed",
            "battle-tie-right",
        )

        witnesses = {
            (
                witness.target_id,
                witness.source_equipment_index,
                witness.modeled_role,
            )
            for witness in context.fog_of_war.get_current_detection_witnesses(
                "blue",
            )
            if witness.observer_unit_id == shooter.entity_id
            and witness.target_id in {target.entity_id for target in targets}
        }
        assert witnesses == {
            (
                target.entity_id,
                director.source_equipment_index,
                director.modeled_role.value,
            )
            for target in targets
        } | {
            (
                target.entity_id,
                observer.source_equipment_index,
                observer.modeled_role.value,
            )
            for target in targets
        }

        runtime = context.tactical_targeting
        decisions = tuple(
            runtime.decision_for(
                engine_tick=0,
                battle_id=battle.battle_id,
                shooter_id=shooter.entity_id,
            )
            for battle in canonical
        )
        assert all(isinstance(decision, TacticalTargetingDecision) for decision in decisions)
        assert all(decision.distance_m == pytest.approx(500.0) for decision in decisions)
        assert tuple((decision.target_side, decision.target_id) for decision in decisions) == (
            ("zulu", targets[0].entity_id),
            ("amber", targets[1].entity_id),
            ("amber", targets[1].entity_id),
        )
        for decision in decisions:
            assert decision.can_engage
            assert decision.weapon_source_equipment_index == (tow.source_equipment_index)
            assert decision.weapon_id == tow.weapon.weapon_id
            assert decision.contact_sensor_source_equipment_index == (observer.source_equipment_index)
            assert decision.contact_sensor_id == observer.sensor_id
            assert decision.fire_control_source is FireControlSource.DIRECT_VISUAL
            assert decision.fire_control_sensor_source_equipment_index is None
            assert decision.fire_control_sensor_id is None

        return tuple(
            (
                decision.target_side,
                decision.target_id,
                decision.weapon_source_equipment_index,
                decision.weapon_id,
                decision.contact_sensor_source_equipment_index,
                decision.contact_sensor_id,
                decision.fire_control_source,
            )
            for decision in decisions
        )

    first = resolve_once()
    assert resolve_once() == first


def test_offline_and_degraded_catalog_director_reject_exactly() -> None:
    """Live director condition controls fire-control authorization."""
    variant = "phase115-director-condition-controls"
    prepared = _prepare(
        _duel("iron_duke_bb", "konig_bb"),
        variant_id=variant,
    )

    offline = _build(prepared, variant_id=variant)
    offline_ship = _unit_of_type(offline, "iron_duke_bb")
    offline_director = offline.context.unit_sensor_attachments[offline_ship.entity_id][0]
    assert offline_director.sensor.equipment is not None
    offline_director.sensor.equipment.operational = False
    assert not offline_director.sensor.operational

    assert offline.step() is False
    offline_decision = _latest_decision(offline, offline_ship.entity_id)
    assert offline_decision.disposition is (TargetingDisposition.FIRE_CONTROL_SENSOR_OFFLINE)
    assert offline_decision.contact_source is (ContactSource.NON_FOW_LOCAL_OBSERVATION)
    assert offline_decision.fire_control_source is FireControlSource.NONE
    assert not offline_decision.can_engage
    assert _outcome_for(offline, offline_decision) is None

    degraded = _build(prepared, variant_id=variant)
    degraded_ship = _unit_of_type(degraded, "iron_duke_bb")
    degraded_director = degraded.context.unit_sensor_attachments[degraded_ship.entity_id][0]
    assert degraded_director.sensor.equipment is not None
    degraded_director.sensor.equipment.condition = 0.25
    assert degraded_director.sensor.operational
    assert degraded_director.sensor.effective_range == pytest.approx(750.0)

    assert degraded.step() is False
    degraded_decision = _latest_decision(degraded, degraded_ship.entity_id)
    assert degraded_decision.distance_m > (degraded_director.sensor.effective_range)
    assert degraded_decision.disposition is (TargetingDisposition.FIRE_CONTROL_RANGE_EXCEEDED)
    assert degraded_decision.fire_control_source is FireControlSource.NONE
    assert not degraded_decision.can_engage
    assert _outcome_for(degraded, degraded_decision) is None


def test_no_ammunition_and_inoperable_weapon_reject_exactly() -> None:
    """The picture uses live weapon and ammunition state before movement."""
    variant = "phase115-weapon-state-controls"
    prepared = _prepare(
        _duel(
            "mark_iv_tank",
            "german_sturmtruppen",
            target_position=(1_000.0, 1_800.0, 0.0),
        ),
        variant_id=variant,
    )

    empty = _build(prepared, variant_id=variant)
    empty_tank = _unit_of_type(empty, "mark_iv_tank")
    for attachment in empty.context.unit_weapons[empty_tank.entity_id]:
        for ammunition_id in attachment.weapon.ammo_state.rounds_by_type:
            attachment.weapon.ammo_state.rounds_by_type[ammunition_id] = 0

    assert empty.step() is False
    empty_decision = _latest_decision(empty, empty_tank.entity_id)
    assert empty_decision.weapon_id == "qf_6pdr_6cwt"
    assert empty_decision.ammunition_id is None
    assert empty_decision.disposition is (TargetingDisposition.NO_FIREABLE_AMMUNITION)
    assert not empty_decision.can_engage
    assert _outcome_for(empty, empty_decision) is None

    inoperable = _build(prepared, variant_id=variant)
    inoperable_tank = _unit_of_type(inoperable, "mark_iv_tank")
    for attachment in inoperable.context.unit_weapons[inoperable_tank.entity_id]:
        assert attachment.weapon.equipment is not None
        attachment.weapon.equipment.operational = False

    assert inoperable.step() is False
    inoperable_decision = _latest_decision(
        inoperable,
        inoperable_tank.entity_id,
    )
    assert inoperable_decision.weapon_id == "qf_6pdr_6cwt"
    assert inoperable_decision.ammunition_id is None
    assert inoperable_decision.disposition is (TargetingDisposition.WEAPON_INOPERABLE)
    assert not inoperable_decision.can_engage
    assert _outcome_for(inoperable, inoperable_decision) is None


def test_wrong_target_domain_is_a_typed_production_rejection() -> None:
    """A visible aircraft cannot make a ship's surface gun domain-valid."""
    variant = "phase115-wrong-target-domain"
    session = _build(
        _prepare(
            _duel(
                "g_class_destroyer",
                "fokker_dvii",
                target_position=(1_000.0, 1_500.0, 100.0),
            ),
            variant_id=variant,
        ),
        variant_id=variant,
    )
    destroyer = _unit_of_type(session, "g_class_destroyer")
    aircraft = _unit_of_type(session, "fokker_dvii")

    assert session.step() is False
    decision = _latest_decision(session, destroyer.entity_id)
    assert decision.target_id == aircraft.entity_id
    assert decision.weapon_id == "qf_4in_mk_iv"
    assert decision.disposition is (TargetingDisposition.TARGET_DOMAIN_UNSUPPORTED)
    assert not decision.can_engage
    assert _outcome_for(session, decision) is None


def test_overlapping_battles_do_not_let_nearer_invalid_target_starve_valid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One interval retains three exact solutions for one shared shooter."""
    variant = "phase115-overlap-nonstarvation"
    session = _build(
        _prepare(
            _scenario(
                blue_units=[
                    _unit("iron_duke_bb", (1_000.0, 1_000.0, 0.0)),
                ],
                red_units=[
                    _unit("fokker_dvii", (1_000.0, 1_400.0, 100.0)),
                    _unit("konig_bb", (1_000.0, 2_000.0, 0.0)),
                ],
            ),
            variant_id=variant,
        ),
        variant_id=variant,
    )
    context = session.context
    shooter = _unit_of_type(session, "iron_duke_bb")
    near = _unit_of_type(session, "fokker_dvii")
    far = _unit_of_type(session, "konig_bb")
    los_calls: list[tuple[tuple[float, float, float], tuple[float, float, float]]] = []
    real_check_los = context.los_engine.check_los

    def _recording_check_los(start, end, *args, **kwargs):
        los_calls.append(
            (
                (start.easting, start.northing, start.altitude),
                (end.easting, end.northing, end.altitude),
            )
        )
        return real_check_los(start, end, *args, **kwargs)

    monkeypatch.setattr(
        context.los_engine,
        "check_los",
        _recording_check_los,
    )
    battles = (
        BattleContext(
            battle_id="battle-near",
            start_tick=0,
            start_time=context.clock.current_time,
            involved_sides=["blue", "red"],
            unit_ids={shooter.entity_id, near.entity_id},
        ),
        BattleContext(
            battle_id="battle-far",
            start_tick=0,
            start_time=context.clock.current_time,
            involved_sides=["blue", "red"],
            unit_ids={shooter.entity_id, far.entity_id},
        ),
        BattleContext(
            battle_id="battle-mixed",
            start_tick=0,
            start_time=context.clock.current_time,
            involved_sides=["blue", "red"],
            unit_ids={shooter.entity_id, near.entity_id, far.entity_id},
        ),
    )

    canonical = session.engine.battle_manager.prepare_tactical_interval(
        context,
        battles,
        5.0,
    )
    assert tuple(battle.battle_id for battle in canonical) == (
        "battle-far",
        "battle-mixed",
        "battle-near",
    )
    runtime = context.tactical_targeting
    interval = runtime.prepared_interval
    assert interval is not None
    assert interval.engine_tick == context.clock.tick_count == 0
    assert interval.battle_ids == (
        "battle-far",
        "battle-mixed",
        "battle-near",
    )
    assert len(runtime.latest_pictures()) == 3

    near_decision = runtime.decision_for(
        engine_tick=0,
        battle_id="battle-near",
        shooter_id=shooter.entity_id,
    )
    far_decision = runtime.decision_for(
        engine_tick=0,
        battle_id="battle-far",
        shooter_id=shooter.entity_id,
    )
    mixed_decision = runtime.decision_for(
        engine_tick=0,
        battle_id="battle-mixed",
        shooter_id=shooter.entity_id,
    )
    assert isinstance(near_decision, TacticalTargetingDecision)
    assert isinstance(far_decision, TacticalTargetingDecision)
    assert isinstance(mixed_decision, TacticalTargetingDecision)
    assert near_decision.target_id == near.entity_id
    assert not near_decision.can_engage
    assert near_decision.disposition is (TargetingDisposition.NO_COMPATIBLE_FIRE_CONTROL)
    assert far_decision.target_id == far.entity_id
    assert far_decision.can_engage
    assert mixed_decision.target_id == far.entity_id
    assert mixed_decision.can_engage
    assert near_decision.distance_m < far_decision.distance_m
    assert {near_decision.key, far_decision.key, mixed_decision.key} == {
        (0, "battle-near", shooter.entity_id),
        (0, "battle-far", shooter.entity_id),
        (0, "battle-mixed", shooter.entity_id),
    }
    # All three immutable pictures use one pre-movement snapshot.  The shared
    # shooter/target pairs are resolved once each even though both also appear
    # in the mixed battle and fire-control reuses the same terrain evidence.
    assert len(los_calls) == 4
    assert len(set(los_calls)) == 4

    mixed = next(battle for battle in canonical if battle.battle_id == "battle-mixed")
    session.engine.battle_manager.execute_tick(context, mixed, 5.0)
    outcome = runtime.engagement_revalidation_for(
        engine_tick=0,
        battle_id="battle-mixed",
        shooter_id=shooter.entity_id,
    )
    assert isinstance(outcome, TacticalEngagementRevalidationOutcome)
    assert outcome.revalidation_passed
    assert outcome.target_id == mixed_decision.target_id
    assert outcome.weapon_id == mixed_decision.weapon_id
    assert outcome.ammunition_id == mixed_decision.ammunition_id


def test_same_cell_units_reuse_exact_directed_los_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Distinct units share only the LOS engine's directed cell identity."""
    variant = "phase115-same-cell-los-cache"
    session = _build(
        _prepare(
            _scenario(
                blue_units=[
                    _unit("mark_iv_tank", (1_000.0, 1_000.0, 0.0)),
                ],
                red_units=[
                    _unit(
                        "german_sturmtruppen",
                        (1_010.0, 1_210.0, 0.0),
                    ),
                    _unit(
                        "german_sturmtruppen",
                        (1_040.0, 1_240.0, 0.0),
                    ),
                ],
            ),
            variant_id=variant,
        ),
        variant_id=variant,
    )
    context = session.context
    shooter = _unit_of_type(session, "mark_iv_tank")
    targets = tuple(unit for unit in context.units_by_side["red"] if unit.unit_type == "german_sturmtruppen")
    assert len(targets) == 2
    target_cells = {context.los_engine.cache_cell(target.position) for target in targets}
    assert len(target_cells) == 1

    los_calls: list[tuple[tuple[float, float, float], tuple[float, float, float]]] = []
    real_check_los = context.los_engine.check_los

    def _recording_check_los(start, end, *args, **kwargs):
        los_calls.append(
            (
                (start.easting, start.northing, start.altitude),
                (end.easting, end.northing, end.altitude),
            )
        )
        return real_check_los(start, end, *args, **kwargs)

    monkeypatch.setattr(
        context.los_engine,
        "check_los",
        _recording_check_los,
    )
    battles = tuple(
        BattleContext(
            battle_id=f"battle-same-cell-{index}",
            start_tick=0,
            start_time=context.clock.current_time,
            involved_sides=["blue", "red"],
            unit_ids={shooter.entity_id, target.entity_id},
        )
        for index, target in enumerate(targets)
    )

    canonical = session.engine.battle_manager.prepare_tactical_interval(
        context,
        battles,
        5.0,
    )
    runtime = context.tactical_targeting
    for battle, target in zip(canonical, targets):
        decision = runtime.decision_for(
            engine_tick=0,
            battle_id=battle.battle_id,
            shooter_id=shooter.entity_id,
        )
        assert isinstance(decision, TacticalTargetingDecision)
        assert decision.target_id == target.entity_id
        assert decision.can_engage

    # Four entity pairs collapse to two directed LOS identities.  Direction
    # remains material because observer and target heights are asymmetric.
    assert len(los_calls) == 2
    assert len(set(los_calls)) == 2


def test_non_fow_range_cull_preserves_boundary_and_skips_far_local_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only provably unreachable contacts bypass target-local evidence."""
    variant = "phase115-non-fow-range-cull"
    session = _build(
        _prepare(
            _scenario(
                blue_units=[
                    _unit("civilian_noncombatant", (1_000.0, 1_000.0, 0.0)),
                ],
                red_units=[
                    # Exactly the scenario's 5 km visibility ceiling.  The
                    # conservative cull must retain the full resolver path.
                    _unit("civilian_noncombatant", (1_000.0, 6_000.0, 0.0)),
                    # No civilian has a sensor attachment, so this target is
                    # provably outside both direct and sensor observation.
                    _unit("civilian_noncombatant", (9_000.0, 1_000.0, 0.0)),
                ],
                calibration={"enable_obscurants": True},
                era="modern",
            ),
            variant_id=variant,
        ),
        variant_id=variant,
    )
    context = session.context
    blue = context.units_by_side["blue"][0]
    boundary = next(unit for unit in context.units_by_side["red"] if unit.position.northing == 6_000.0)
    far = next(unit for unit in context.units_by_side["red"] if unit.position.easting == 9_000.0)
    assert context.unit_sensor_attachments[blue.entity_id] == ()
    assert context.unit_sensor_attachments[boundary.entity_id] == ()
    assert context.unit_sensor_attachments[far.entity_id] == ()

    opacity_calls: list[tuple[float, float, float]] = []
    real_opacity_at = context.obscurants_engine.opacity_at

    def _recording_opacity_at(position):
        opacity_calls.append(
            (position.easting, position.northing, position.altitude),
        )
        return real_opacity_at(position)

    los_calls: list[tuple[tuple[float, float, float], tuple[float, float, float]]] = []
    real_check_los = context.los_engine.check_los

    def _recording_check_los(start, end, *args, **kwargs):
        los_calls.append(
            (
                (start.easting, start.northing, start.altitude),
                (end.easting, end.northing, end.altitude),
            ),
        )
        return real_check_los(start, end, *args, **kwargs)

    monkeypatch.setattr(
        context.obscurants_engine,
        "opacity_at",
        _recording_opacity_at,
    )
    monkeypatch.setattr(
        context.los_engine,
        "check_los",
        _recording_check_los,
    )
    battle = BattleContext(
        battle_id="battle-non-fow-range-cull",
        start_tick=0,
        start_time=context.clock.current_time,
        involved_sides=["blue", "red"],
        unit_ids={blue.entity_id, boundary.entity_id, far.entity_id},
    )

    session.engine.battle_manager.prepare_tactical_interval(
        context,
        (battle,),
        5.0,
    )

    far_position = (
        far.position.easting,
        far.position.northing,
        far.position.altitude,
    )
    boundary_position = (
        boundary.position.easting,
        boundary.position.northing,
        boundary.position.altitude,
    )
    assert boundary_position in opacity_calls
    assert far_position not in opacity_calls
    assert any(boundary_position in directed for directed in los_calls)
    assert all(far_position not in directed for directed in los_calls)
    far_decision = context.tactical_targeting.decision_for(
        engine_tick=0,
        battle_id=battle.battle_id,
        shooter_id=far.entity_id,
    )
    assert isinstance(far_decision, TacticalTargetingDecision)
    assert far_decision.disposition is TargetingDisposition.NO_CONTACT


def _detection_rng_fingerprint(session: RuntimeSession) -> str:
    state = session.context.rng_manager.get_stream(
        ModuleId.DETECTION,
    ).bit_generator.state
    return json.dumps(state, sort_keys=True)


def _downstream_commit_state(session: RuntimeSession) -> dict[str, Any]:
    """Return state that targeting preparation must not commit on failure."""
    context = session.context
    return {
        "units": {
            unit.entity_id: unit.get_state()
            for unit in sorted(
                context.all_units(),
                key=lambda item: item.entity_id,
            )
        },
        "weapons": {
            (
                unit_id,
                attachment.source_equipment_index,
                attachment.weapon.weapon_id,
            ): attachment.weapon.get_state()
            for unit_id, attachments in sorted(context.unit_weapons.items())
            for attachment in attachments
        },
        "movement_diagnostics": context.movement_diagnostics.get_state(),
    }


def _observation_commit_state(session: RuntimeSession) -> dict[str, Any]:
    """Return readable committed observation owners, even while staging."""
    context = session.context
    fog = context.fog_of_war
    battle = session.engine.battle_manager
    return {
        "world_views": {
            side: view.get_state()
            for side in sorted(context.units_by_side)
            if (view := fog.peek_world_view(side)) is not None
        },
        "witnesses": fog.get_current_detection_witnesses(),
        "fusion": fog.intel_fusion.get_state(),
        "scan_counts": fog._detection.get_scan_count_state(),
        "cadence_ordinal": fog.cadence.committed_ordinal,
        "cadence_states": fog.cadence.attachment_states,
        "indexed_digest": (context.rng_manager.indexed_fow_transcript_digest_hex),
        "indexed_latest": (context.rng_manager.latest_fow_detection_interval_record),
        "conventional_rng": _detection_rng_fingerprint(session),
        "targeting": context.tactical_targeting.get_state(),
        "signature_cache": dict(battle._signature_cache),
        "concealment": dict(battle._concealment_scores),
        "lod_tiers": dict(battle._lod_tiers),
        "lod_pending_tiers": dict(battle._lod_pending_tiers),
        "lod_pending_counts": dict(battle._lod_pending_counts),
    }


def test_enabled_em_owner_fault_aborts_before_fow_and_downstream_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An enabled EM owner fault cannot become default attenuation."""
    variant_id = "phase115-enabled-em-owner-fault"
    session = _build(
        _prepare(
            _duel(
                "mark_iv_tank",
                "german_sturmtruppen",
                fog_of_war=True,
                calibration={"enable_em_propagation": True},
            ),
            variant_id=variant_id,
        ),
        variant_id=variant_id,
    )
    context = session.context
    battles = tuple(session.engine.battle_manager.active_battles)
    assert len(battles) == 1
    assert context.calibration.get("enable_em_propagation", False) is True
    assert context.conditions_facade is not None

    events: list[Event] = []
    context.event_bus.subscribe(Event, events.append)
    fow_state_before = context.fog_of_war.get_state()
    witnesses_before = context.fog_of_war.get_current_detection_witnesses()
    rng_before = _detection_rng_fingerprint(session)
    targeting_before = context.tactical_targeting.get_state()
    downstream_before = _downstream_commit_state(session)

    def _fail_electromagnetic():
        raise RuntimeError("injected enabled EM owner failure")

    monkeypatch.setattr(
        context.conditions_facade,
        "electromagnetic",
        _fail_electromagnetic,
    )
    with pytest.raises(
        RuntimeError,
        match="injected enabled EM owner failure",
    ):
        session.engine.battle_manager.prepare_tactical_interval(
            context,
            battles,
            5.0,
        )

    # The EM query precedes the FOW owner call.  These equalities follow from
    # that ordering; they are not a claim that arbitrary FOW failures roll
    # their own draws or contact mutations back.
    assert context.fog_of_war.get_state() == fow_state_before
    assert context.fog_of_war.get_current_detection_witnesses() == witnesses_before
    assert _detection_rng_fingerprint(session) == rng_before
    assert context.tactical_targeting.get_state() == targeting_before
    assert _downstream_commit_state(session) == downstream_before
    assert events == []


def test_disabled_em_propagation_does_not_query_faulting_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The disabled control retains the non-EM FOW preparation path."""
    variant_id = "phase115-disabled-em-owner-control"
    session = _build(
        _prepare(
            _duel(
                "mark_iv_tank",
                "german_sturmtruppen",
                fog_of_war=True,
                calibration={"enable_em_propagation": False},
            ),
            variant_id=variant_id,
        ),
        variant_id=variant_id,
    )
    context = session.context
    battles = tuple(session.engine.battle_manager.active_battles)
    assert len(battles) == 1

    def _fail_if_queried():
        raise AssertionError("disabled EM owner was queried")

    monkeypatch.setattr(
        context.conditions_facade,
        "electromagnetic",
        _fail_if_queried,
    )
    canonical = session.engine.battle_manager.prepare_tactical_interval(
        context,
        battles,
        5.0,
    )
    assert canonical == battles
    assert (
        context.tactical_targeting.latest_picture(
            battles[0].battle_id,
        )
        is not None
    )


def test_missing_enabled_em_owner_rejects_before_fow() -> None:
    """Enabled EM propagation requires its production conditions owner."""
    variant_id = "phase115-missing-enabled-em-owner"
    session = _build(
        _prepare(
            _duel(
                "mark_iv_tank",
                "german_sturmtruppen",
                fog_of_war=True,
                calibration={"enable_em_propagation": True},
            ),
            variant_id=variant_id,
        ),
        variant_id=variant_id,
    )
    context = session.context
    battles = tuple(session.engine.battle_manager.active_battles)
    assert len(battles) == 1
    context.conditions_facade = None
    fow_state_before = context.fog_of_war.get_state()
    witnesses_before = context.fog_of_war.get_current_detection_witnesses()
    rng_before = _detection_rng_fingerprint(session)
    targeting_before = context.tactical_targeting.get_state()

    with pytest.raises(
        RuntimeError,
        match="EM propagation is enabled without a ConditionsEngine",
    ):
        session.engine.battle_manager.prepare_tactical_interval(
            context,
            battles,
            5.0,
        )

    assert context.fog_of_war.get_state() == fow_state_before
    assert context.fog_of_war.get_current_detection_witnesses() == witnesses_before
    assert _detection_rng_fingerprint(session) == rng_before
    assert context.tactical_targeting.get_state() == targeting_before


@pytest.mark.parametrize("parallel_detection", [False, True])
def test_cbrn_owner_fault_preserves_outer_observation_commit_boundary(
    monkeypatch: pytest.MonkeyPatch,
    parallel_detection: bool,
) -> None:
    """A post-FOW CBRN fault publishes none of the observation owners."""
    variant_id = f"phase115-cbrn-owner-picture-fault-{'parallel' if parallel_detection else 'sequential'}"
    session = _build(
        _prepare(
            _duel(
                "mark_iv_tank",
                "german_sturmtruppen",
                fog_of_war=True,
                cbrn=True,
                calibration={
                    "enable_parallel_detection": parallel_detection,
                },
            ),
            variant_id=variant_id,
        ),
        variant_id=variant_id,
    )
    context = session.context
    battles = tuple(session.engine.battle_manager.active_battles)
    assert len(battles) == 1
    cbrn = context.cbrn_engine
    assert cbrn is not None
    assert cbrn._config.enable_cbrn is True

    # Missing unit state is a normal, neutral MOPP-0 result.  It does not
    # raise any of the exceptions that the old targeting path swallowed.
    missing_id = "phase115-unregistered-cbrn-unit"
    assert cbrn.get_mopp_level(missing_id) == 0
    assert cbrn.get_mopp_effects(missing_id) == pytest.approx(
        (1.0, 1.0, 1.0),
    )

    events: list[Event] = []
    context.event_bus.subscribe(Event, events.append)
    rng_before = _detection_rng_fingerprint(session)
    downstream_before = _downstream_commit_state(session)
    observation_before = _observation_commit_state(session)
    fault_baseline: dict[str, Any] = {}

    def _fail_mopp_effects(_unit_id: str):
        fault_baseline.update(_observation_commit_state(session))
        raise ValueError("injected CBRN targeting owner failure")

    monkeypatch.setattr(cbrn, "get_mopp_effects", _fail_mopp_effects)
    with pytest.raises(
        ValueError,
        match="injected CBRN targeting owner failure",
    ):
        session.engine.battle_manager.prepare_tactical_interval(
            context,
            battles,
            5.0,
        )

    assert fault_baseline
    assert fault_baseline == observation_before
    assert _observation_commit_state(session) == observation_before
    assert _detection_rng_fingerprint(session) == rng_before
    assert context.fog_of_war.cadence.poisoned is True
    with pytest.raises(RuntimeError, match="poisoned update transaction"):
        context.fog_of_war.get_state()
    assert (
        context.tactical_targeting.latest_picture(
            battles[0].battle_id,
        )
        is None
    )
    assert _downstream_commit_state(session) == downstream_before
    assert events == []


def test_cross_owner_precommit_fault_leaves_every_observation_owner_unpublished(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    variant_id = "phase115-cross-owner-precommit-fault"
    session = _build(
        _prepare(
            _duel(
                "mark_iv_tank",
                "german_sturmtruppen",
                fog_of_war=True,
            ),
            variant_id=variant_id,
        ),
        variant_id=variant_id,
    )
    context = session.context
    battles = tuple(session.engine.battle_manager.active_battles)
    observation_before = _observation_commit_state(session)
    validate_indexed = context.rng_manager.validate_prepared_fow_detection_interval_commit

    def _fail_after_indexed_validation(plan: object) -> None:
        validate_indexed(plan)
        raise RuntimeError("injected cross-owner precommit failure")

    monkeypatch.setattr(
        context.rng_manager,
        "validate_prepared_fow_detection_interval_commit",
        _fail_after_indexed_validation,
    )
    with pytest.raises(
        RuntimeError,
        match="injected cross-owner precommit failure",
    ):
        session.engine.battle_manager.prepare_tactical_interval(
            context,
            battles,
            5.0,
        )

    assert _observation_commit_state(session) == observation_before
    assert context.fog_of_war.cadence.poisoned is True
    assert context.tactical_targeting.latest_pictures() == ()


def test_multibattle_picture_fault_rejects_without_publishing_a_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All battle pictures commit together after complete resolution."""
    variant_id = "phase115-multibattle-picture-atomicity"
    session = _build(
        _prepare(
            _scenario(
                blue_units=[
                    _unit("mark_iv_tank", (1_000.0, 1_000.0, 0.0)),
                ],
                red_units=[
                    _unit("german_sturmtruppen", (1_000.0, 1_500.0, 0.0)),
                    _unit("german_sturmtruppen", (1_000.0, 2_000.0, 0.0)),
                ],
            ),
            variant_id=variant_id,
        ),
        variant_id=variant_id,
    )
    context = session.context
    shooter = _unit_of_type(session, "mark_iv_tank")
    targets = tuple(
        sorted(
            (unit for unit in context.units_by_side["red"] if unit.unit_type == "german_sturmtruppen"),
            key=lambda unit: unit.entity_id,
        )
    )
    assert len(targets) == 2
    battles = tuple(
        BattleContext(
            battle_id=f"battle-atomic-{index}",
            start_tick=0,
            start_time=context.clock.current_time,
            involved_sides=["blue", "red"],
            unit_ids={shooter.entity_id, target.entity_id},
        )
        for index, target in enumerate(targets)
    )
    manager = session.engine.battle_manager
    original_resolver = manager._resolve_targeting_decision

    def _fail_on_second_battle(*args: Any, **kwargs: Any):
        battle = kwargs["battle"]
        if battle.battle_id == battles[1].battle_id:
            raise RuntimeError("injected second-battle targeting failure")
        return original_resolver(*args, **kwargs)

    monkeypatch.setattr(
        manager,
        "_resolve_targeting_decision",
        _fail_on_second_battle,
    )
    targeting_before = deepcopy(context.tactical_targeting.get_state())
    observation_before = _observation_commit_state(session)

    with pytest.raises(
        RuntimeError,
        match="injected second-battle targeting failure",
    ):
        manager.prepare_tactical_interval(context, battles, 5.0)

    assert context.tactical_targeting.get_state() == targeting_before
    assert _observation_commit_state(session) == observation_before
    assert all(context.tactical_targeting.latest_picture(battle.battle_id) is None for battle in battles)


@pytest.mark.parametrize(
    ("variant_id", "calibration"),
    [
        (
            "phase115-fow-single-draw-sequential",
            {
                "enable_parallel_detection": False,
                "enable_scan_scheduling": False,
                "enable_lod": False,
            },
        ),
        (
            "phase115-fow-single-draw-parallel",
            {
                "enable_parallel_detection": True,
                "enable_scan_scheduling": False,
                "enable_lod": False,
            },
        ),
    ],
)
def test_overlapping_fow_pictures_consume_one_detection_draw(
    variant_id: str,
    calibration: dict[str, Any],
) -> None:
    """Preparation owns the only DETECTION draw for both battle consumers."""
    session = _build(
        _prepare(
            _scenario(
                blue_units=[
                    _unit("mark_iv_tank", (1_000.0, 1_000.0, 0.0)),
                ],
                red_units=[
                    _unit(
                        "german_sturmtruppen",
                        (990.0, 1_100.0, 0.0),
                    ),
                    _unit(
                        "german_sturmtruppen",
                        (1_010.0, 1_200.0, 0.0),
                    ),
                ],
                fog_of_war=True,
                calibration=calibration,
            ),
            variant_id=variant_id,
        ),
        variant_id=variant_id,
    )
    context = session.context
    shooter = _unit_of_type(session, "mark_iv_tank")
    targets = tuple(unit for unit in context.units_by_side["red"] if unit.unit_type == "german_sturmtruppen")
    assert len(targets) == 2
    battles = tuple(
        BattleContext(
            battle_id=f"battle-overlap-{index}",
            start_tick=0,
            start_time=context.clock.current_time,
            involved_sides=["blue", "red"],
            unit_ids={shooter.entity_id, target.entity_id},
        )
        for index, target in enumerate(targets)
    )

    before_prepare = _detection_rng_fingerprint(session)
    indexed_before = context.rng_manager.latest_fow_detection_interval_record
    canonical = session.engine.battle_manager.prepare_tactical_interval(
        context,
        tuple(reversed(battles)),
        5.0,
    )
    after_prepare = _detection_rng_fingerprint(session)
    indexed_after = context.rng_manager.latest_fow_detection_interval_record
    assert after_prepare == before_prepare
    assert indexed_after is not None
    assert indexed_after is not indexed_before
    assert indexed_after.engine_tick == 0
    assert tuple(battle.battle_id for battle in canonical) == (
        "battle-overlap-0",
        "battle-overlap-1",
    )

    runtime = context.tactical_targeting
    interval = runtime.prepared_interval
    assert interval is not None
    assert interval.engine_tick == 0
    assert interval.logical_time_s == 0.0
    decisions: list[TacticalTargetingDecision] = []
    for battle, target in zip(canonical, targets):
        decision = runtime.decision_for(
            engine_tick=0,
            battle_id=battle.battle_id,
            shooter_id=shooter.entity_id,
        )
        assert isinstance(decision, TacticalTargetingDecision)
        assert decision.target_id == target.entity_id
        assert decision.contact_source is ContactSource.FOW_OBSERVER_WITNESS
        assert decision.observing_unit_id == shooter.entity_id
        assert decision.contact_time_s == 0.0
        assert decision.can_engage
        decisions.append(decision)

    witnesses = context.fog_of_war.get_current_detection_witnesses("blue")
    exact_witnesses = {
        (witness.observer_unit_id, witness.target_id)
        for witness in witnesses
        if witness.detected and witness.observer_unit_id == shooter.entity_id
    }
    assert exact_witnesses == {(shooter.entity_id, target.entity_id) for target in targets}
    assert context.fog_of_war.get_world_view("blue").last_update_time == 0.0

    battle_state_after_prepare = session.engine.battle_manager.get_state()
    fow_state_after_prepare = context.fog_of_war.get_state()
    targeting_state_after_prepare = runtime.get_state()
    with pytest.raises(ValueError, match="strictly newer tick"):
        session.engine.battle_manager.prepare_tactical_interval(
            context,
            canonical,
            5.0,
        )
    assert _detection_rng_fingerprint(session) == after_prepare
    assert session.engine.battle_manager.get_state() == battle_state_after_prepare
    assert context.fog_of_war.get_state() == fow_state_after_prepare
    assert (
        context.fog_of_war.get_current_detection_witnesses(
            "blue",
        )
        == witnesses
    )
    assert runtime.get_state() == targeting_state_after_prepare

    for battle in canonical:
        session.engine.battle_manager.execute_tick(context, battle, 5.0)
    assert _detection_rng_fingerprint(session) == after_prepare

    for decision in decisions:
        outcome = runtime.engagement_revalidation_for(
            engine_tick=decision.engine_tick,
            battle_id=decision.battle_id,
            shooter_id=decision.shooter_id,
        )
        assert isinstance(outcome, TacticalEngagementRevalidationOutcome)
        assert outcome.revalidation_passed
        assert outcome.target_id == decision.target_id
        assert outcome.weapon_id == decision.weapon_id
        assert outcome.ammunition_id == decision.ammunition_id


def _three_side_parallel_scenario() -> CampaignScenarioConfig:
    return CampaignScenarioConfig.model_validate(
        {
            "name": "Phase 115 three-side parallel FOW control",
            "date": "1916-06-01T12:00:00Z",
            "duration_hours": 1.0,
            "era": "ww1",
            "tick_resolution": {
                "strategic_s": 3_600.0,
                "operational_s": 300.0,
                "tactical_s": 5.0,
            },
            "weather_conditions": {
                "visibility_m": 10_000.0,
                "precipitation": "none",
            },
            "terrain": {
                "width_m": 10_000.0,
                "height_m": 10_000.0,
                "cell_size_m": 100.0,
                "terrain_type": "open_ocean",
            },
            "deployment": {"mode": "manual"},
            "sides": [
                {
                    "side": "blue",
                    "units": [
                        _unit(
                            "iron_duke_bb",
                            (990.0, 1_000.0, 0.0),
                        )
                    ],
                },
                {
                    "side": "green",
                    "units": [
                        _unit(
                            "iron_duke_bb",
                            (1_010.0, 1_000.0, 0.0),
                        )
                    ],
                },
                {
                    "side": "red",
                    "units": [
                        _unit(
                            "iron_duke_bb",
                            (1_000.0, 1_100.0, 0.0),
                        )
                    ],
                },
            ],
            "objectives": [],
            "victory_conditions": [],
            "calibration_overrides": {
                "defensive_sides": [],
                "enable_fog_of_war": True,
                "enable_sensing_aware_standoff": True,
                "enable_parallel_detection": True,
                "enable_scan_scheduling": False,
                "enable_lod": False,
                "target_selection_mode": "closest",
            },
        }
    )


def test_three_side_parallel_factory_interval_repeats_exactly() -> None:
    """One parallel configuration is exact across fresh same-seed builds."""
    variant_id = "phase115-three-side-parallel-repeat"
    prepared = _prepare(
        _three_side_parallel_scenario(),
        variant_id=variant_id,
    )

    def run_once() -> dict[str, Any]:
        session = _build(
            prepared,
            variant_id=variant_id,
            seed=91_115,
        )
        context = session.context
        # Both southern directors retain their authored forward sector.  The
        # northern ship faces south, so the same catalog sensor on two sides
        # scans that red target concurrently while red scans both opponents.
        context.units_by_side["red"][0].heading = math.pi
        units = tuple(
            sorted(
                context.all_units(),
                key=lambda unit: unit.entity_id,
            )
        )
        battle = BattleContext(
            battle_id="battle-three-side-parallel-repeat",
            start_tick=0,
            start_time=context.clock.current_time,
            involved_sides=["blue", "green", "red"],
            unit_ids={unit.entity_id for unit in units},
        )

        canonical = session.engine.battle_manager.prepare_tactical_interval(
            context,
            (battle,),
            5.0,
        )
        assert tuple(item.battle_id for item in canonical) == (battle.battle_id,)
        witnesses = context.fog_of_war.get_current_detection_witnesses()
        assert len(witnesses) == 4
        assert {witness.sensor_id for witness in witnesses} == {"binoculars_ww1"}
        assert {witness.side for witness in witnesses} == {"blue", "green", "red"}

        detection_state = context.detection_engine.get_state()
        assert len(detection_state["scan_counts"]) == 4
        assert set(detection_state["scan_counts"].values()) == {1}
        detection_rng_state = context.rng_manager.get_stream(
            ModuleId.DETECTION,
        ).bit_generator.state
        fog_state = context.fog_of_war.get_state()
        assert detection_state["rng_state"] == detection_rng_state
        assert fog_state["rng_state"] == detection_rng_state
        assert fog_state["intel_fusion"]["rng_state"] == detection_rng_state

        return {
            "world_views": {
                side: context.fog_of_war.get_world_view(side).get_state() for side in ("blue", "green", "red")
            },
            "witnesses": witnesses,
            "targeting": context.tactical_targeting.get_state(),
            "fog_of_war": fog_state,
            "detection": detection_state,
            "rng": context.rng_manager.get_state(),
        }

    runs = [run_once() for _ in range(3)]
    assert runs[1:] == [runs[0], runs[0]]
