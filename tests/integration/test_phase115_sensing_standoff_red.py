"""Phase 115 production-red proofs for sensing-aware tactical standoff."""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import pytest

from stochastic_warfare.combat.events import (
    AmmoExpendedEvent,
    EngagementEvent,
)
from stochastic_warfare.core.events import Event
from stochastic_warfare.core.types import Domain, Position
from stochastic_warfare.entities.base import UnitStatus
from stochastic_warfare.simulation.battle import BattleContext
from stochastic_warfare.simulation.engine import TickResolution
from stochastic_warfare.simulation.loadouts import WeaponModeledRole
from stochastic_warfare.simulation.movement_diagnostics import MovementReason
from stochastic_warfare.simulation.recorder import SimulationRecorder
from stochastic_warfare.simulation.runtime import (
    AnalysisVariant,
    PreparedScenario,
    RuntimeSession,
    SimulationRuntimeFactory,
)
from stochastic_warfare.simulation.scenario import CampaignScenarioConfig
from stochastic_warfare.simulation.tactical_targeting import (
    ContactSource,
    EffectiveRangeBasis,
    FireControlSource,
    TargetingDisposition,
)
from stochastic_warfare.validation.movement_diagnostics import (
    evaluate_movement_diagnostics,
)


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
SOURCE_LABEL = str(
    (DATA_DIR / "eras" / "ww1" / "scenarios" / "cambrai" / "scenario.yaml").resolve(),
)
VARIANT_ID = "phase115-sensing-standoff-red"


def _mark_iv_scenario(
    *,
    target_easting: float = 6_000.0,
    target_northing: float = 1_000.0,
    sensing_aware_standoff: bool = True,
    fog_of_war: bool = False,
) -> CampaignScenarioConfig:
    """Return a compact catalog-backed WW1 direct-fire engagement."""
    return CampaignScenarioConfig.model_validate(
        {
            "name": "Phase 115 sensing-aware standoff red",
            "date": "1917-11-20T06:20:00Z",
            "duration_hours": 1.0,
            "era": "ww1",
            "tick_resolution": {
                "strategic_s": 3600.0,
                "operational_s": 300.0,
                "tactical_s": 5.0,
            },
            "weather_conditions": {
                "visibility_m": 3_000.0,
            },
            "terrain": {
                "width_m": 10_000.0,
                "height_m": 2_000.0,
                "cell_size_m": 50.0,
                "terrain_type": "flat_desert",
            },
            "deployment": {"mode": "manual"},
            "sides": [
                {
                    "side": "british",
                    "units": [
                        {
                            "unit_type": "mark_iv_tank",
                            "count": 1,
                            "position": [1_000.0, 1_000.0, 0.0],
                        },
                    ],
                },
                {
                    "side": "german",
                    "units": [
                        {
                            "unit_type": "german_sturmtruppen",
                            "count": 1,
                            "position": [
                                target_easting,
                                target_northing,
                                0.0,
                            ],
                        },
                    ],
                },
            ],
            "objectives": [],
            "victory_conditions": [],
            "calibration_overrides": {
                "defensive_sides": [],
                "enable_fog_of_war": fog_of_war,
                "enable_sensing_aware_standoff": sensing_aware_standoff,
            },
        },
    )


def _prepare(
    *,
    target_easting: float = 6_000.0,
    target_northing: float = 1_000.0,
    sensing_aware_standoff: bool = True,
    fog_of_war: bool = False,
) -> PreparedScenario:
    return SimulationRuntimeFactory().prepare_config(
        _mark_iv_scenario(
            target_easting=target_easting,
            target_northing=target_northing,
            sensing_aware_standoff=sensing_aware_standoff,
            fog_of_war=fog_of_war,
        ),
        DATA_DIR,
        (AnalysisVariant(variant_id=VARIANT_ID),),
        source_label=SOURCE_LABEL,
    )


def _build(prepared: PreparedScenario) -> RuntimeSession:
    return prepared.build(
        VARIANT_ID,
        seed=115,
        max_ticks=10,
        strict_mode=True,
    )


def test_salamis_naval_projectile_profile_runs_through_live_targeting() -> None:
    """A naval profile for a shared ancient role must remain executable."""
    scenario_path = DATA_DIR / "eras" / "ancient_medieval" / "scenarios" / "salamis" / "scenario.yaml"
    variant_id = "phase115-salamis-naval-profile"
    prepared = SimulationRuntimeFactory().prepare(
        scenario_path,
        DATA_DIR,
        (AnalysisVariant(variant_id=variant_id),),
    )
    session = prepared.build(
        variant_id,
        seed=42,
        max_ticks=20_000,
        strict_mode=True,
        recorder_factory=lambda context: SimulationRecorder(
            context.event_bus,
        ),
    )

    result = session.run_to_completion()

    assert result.ticks_executed > 0
    assert session.recorder is not None
    engagements = tuple(event for event in session.recorder.events if event.event_type == "EngagementEvent")
    assert engagements
    assert {event.data["weapon_id"] for event in engagements} == {"javelin"}
    decisions = tuple(
        decision for picture in session.context.tactical_targeting.latest_pictures() for decision in picture.decisions
    )
    assert any(
        decision.shooter_domain is Domain.NAVAL
        and decision.target_domain is Domain.NAVAL
        and decision.weapon_modeled_role is WeaponModeledRole.ANCIENT_PROJECTILE
        and decision.fire_control_source is FireControlSource.DIRECT_VISUAL
        and decision.engagement_solution_valid
        for decision in decisions
    )


def test_mark_iv_advances_outside_current_sensing_and_effective_envelope() -> None:
    """Catalog maximum alone must not stop a factory-built runtime unit."""
    session = _build(_prepare())
    tank = session.context.units_by_side["british"][0]
    target = session.context.units_by_side["german"][0]
    main_gun = next(
        attachment
        for attachment in session.context.unit_weapons[tank.entity_id]
        if attachment.weapon.weapon_id == "qf_6pdr_6cwt"
    )
    binoculars = next(
        sensor for sensor in session.context.unit_sensors[tank.entity_id] if sensor.sensor_id == "binoculars_ww1"
    )

    assert main_gun.weapon.definition.max_range_m == pytest.approx(6_675.0)
    assert main_gun.weapon.definition.effective_range_m == pytest.approx(1_000.0)
    assert binoculars.effective_range == pytest.approx(3_000.0)

    assert session.engine.battle_manager.active_battles
    before = tank.position
    distance_before = math.hypot(
        tank.position.easting - target.position.easting,
        tank.position.northing - target.position.northing,
    )
    assert 3_000.0 < distance_before < 0.8 * 6_675.0

    assert session.step() is False
    assert session.engine.resolution is TickResolution.TACTICAL

    observation = session.context.movement_diagnostics.get_unit(
        tank.entity_id,
    ).recent_observations[-1]
    assert observation.reason is MovementReason.MOVED
    decision = observation.targeting_decision
    assert decision is not None
    assert decision.disposition is TargetingDisposition.NO_CONTACT
    assert decision.target_id is None
    assert decision.authorized_standoff_m == 0.0
    assert decision.can_hold is False
    assert decision.can_engage is False
    assert tank.position.easting > before.easting
    distance_after = math.hypot(
        tank.position.easting - target.position.easting,
        tank.position.northing - target.position.northing,
    )
    assert distance_after < distance_before


def test_current_authored_solution_holds_and_is_shared_with_diagnostics() -> None:
    """A real local contact/direct-aim solution may authorize the hold."""
    session = _build(_prepare(target_easting=1_800.0))
    tank = session.context.units_by_side["british"][0]
    before = tank.position

    assert session.step() is False

    observation = session.context.movement_diagnostics.get_unit(
        tank.entity_id,
    ).recent_observations[-1]
    decision = observation.targeting_decision
    assert observation.reason is MovementReason.ENGINE_WEAPON_STANDOFF
    assert tank.position == before
    assert decision is not None
    assert decision is session.context.tactical_targeting.decision_for(
        engine_tick=session.context.clock.tick_count,
        battle_id=decision.battle_id,
        shooter_id=tank.entity_id,
    )
    assert decision.target_id == session.context.units_by_side["german"][0].entity_id
    assert decision.contact_source is ContactSource.NON_FOW_LOCAL_OBSERVATION
    assert decision.fire_control_source is FireControlSource.DIRECT_VISUAL
    assert decision.effective_range_basis is EffectiveRangeBasis.AUTHORED
    assert decision.disposition is TargetingDisposition.VALID_STANDOFF_HOLD
    assert decision.authorized_standoff_m == pytest.approx(1_000.0)
    assert decision.can_hold is True
    assert decision.can_engage is True
    hold_revalidation = observation.hold_revalidation
    assert hold_revalidation is not None
    assert hold_revalidation.key == decision.key
    assert hold_revalidation.target_id == decision.target_id
    assert hold_revalidation.live_distance_m == pytest.approx(
        decision.distance_m,
    )
    assert hold_revalidation.disposition is (TargetingDisposition.VALID_ENGAGEMENT_SOLUTION)
    assert hold_revalidation.hold_authorized is True
    evaluator_fields = evaluate_movement_diagnostics(
        session.context.movement_diagnostics,
        session.context.units_by_side,
        context=session.context,
    ).fields_by_unit()[tank.entity_id]
    assert evaluator_fields["targeting_hold_revalidation_engine_tick"] == (decision.engine_tick)
    assert evaluator_fields["targeting_hold_revalidation_battle_id"] == (decision.battle_id)
    assert evaluator_fields["targeting_hold_revalidation_shooter_id"] == (decision.shooter_id)
    assert evaluator_fields["targeting_hold_revalidation_target_id"] == (decision.target_id)
    assert evaluator_fields["targeting_hold_revalidation_live_distance_m"] == pytest.approx(
        hold_revalidation.live_distance_m
    )
    assert (
        evaluator_fields["targeting_hold_revalidation_disposition"]
        == TargetingDisposition.VALID_ENGAGEMENT_SOLUTION.value
    )
    assert evaluator_fields["targeting_hold_revalidation_hold_authorized"] is True
    revalidation = session.context.tactical_targeting.engagement_revalidation_for(
        engine_tick=decision.engine_tick,
        battle_id=decision.battle_id,
        shooter_id=decision.shooter_id,
    )
    assert revalidation is not None
    assert revalidation.target_id == decision.target_id
    assert revalidation.weapon_id == decision.weapon_id
    assert revalidation.ammunition_id == decision.ammunition_id
    assert revalidation.revalidation_passed is True
    assert revalidation.disposition is (TargetingDisposition.VALID_ENGAGEMENT_SOLUTION)


def test_disabled_flag_removes_only_automatic_standoff() -> None:
    """Explicit-off never restores the legacy maximum-range hold."""
    session = _build(
        _prepare(
            target_easting=1_800.0,
            sensing_aware_standoff=False,
        )
    )
    tank = session.context.units_by_side["british"][0]
    before = tank.position

    assert session.step() is False

    observation = session.context.movement_diagnostics.get_unit(
        tank.entity_id,
    ).recent_observations[-1]
    decision = observation.targeting_decision
    assert observation.reason is MovementReason.MOVED
    assert tank.position.easting > before.easting
    assert decision is not None
    assert decision.disposition is TargetingDisposition.STANDOFF_DISABLED
    assert decision.authorized_standoff_m == 0.0
    assert decision.can_hold is False
    assert decision.can_engage is True
    revalidation = session.context.tactical_targeting.engagement_revalidation_for(
        engine_tick=decision.engine_tick,
        battle_id=decision.battle_id,
        shooter_id=decision.shooter_id,
    )
    assert revalidation is not None
    assert revalidation.revalidation_passed is True


def test_authored_hold_retains_live_revalidation_without_changing_owner() -> None:
    """A can-hold card is diagnosed even when the authored hold wins first."""
    raw = _mark_iv_scenario(target_easting=1_800.0).model_dump(mode="python")
    raw["behavior_rules"] = {"british": {"hold_position": True}}
    prepared = SimulationRuntimeFactory().prepare_config(
        CampaignScenarioConfig.model_validate(raw),
        DATA_DIR,
        (AnalysisVariant(variant_id=VARIANT_ID),),
        source_label=SOURCE_LABEL,
    )
    session = _build(prepared)
    tank = session.context.units_by_side["british"][0]
    before = tank.position

    assert session.step() is False

    observation = session.context.movement_diagnostics.get_unit(
        tank.entity_id,
    ).recent_observations[-1]
    decision = observation.targeting_decision
    assert decision is not None
    assert decision.can_hold
    assert observation.reason is MovementReason.AUTHORED_HOLD
    assert tank.position == before
    hold_revalidation = observation.hold_revalidation
    assert hold_revalidation is not None
    assert hold_revalidation.key == decision.key
    assert hold_revalidation.target_id == decision.target_id
    assert hold_revalidation.hold_authorized is True
    assert hold_revalidation.disposition is (TargetingDisposition.VALID_ENGAGEMENT_SOLUTION)


def test_catalog_direct_action_survives_paired_standoff_flag_control() -> None:
    """The flag changes movement, not the exact committed direct-fire owner."""
    config_data = _mark_iv_scenario(
        target_easting=1_300.0,
    ).model_dump(mode="json")
    config_data.update(
        {
            "name": "Phase 115 paired modern direct-fire control",
            "date": "2003-04-02T12:00:00Z",
            "era": "modern",
        }
    )
    config_data["sides"][0]["units"][0]["unit_type"] = "iraqi_foreign_fighter"
    config_data["sides"][1]["units"][0]["unit_type"] = "t72m"
    prepared = SimulationRuntimeFactory().prepare_config(
        CampaignScenarioConfig.model_validate(config_data),
        DATA_DIR,
        (
            AnalysisVariant(variant_id="phase115-direct-action-on"),
            AnalysisVariant(
                variant_id="phase115-direct-action-off",
                calibration_patch={
                    "enable_sensing_aware_standoff": False,
                },
            ),
        ),
        source_label=str(
            (DATA_DIR / "scenarios" / "73_easting" / "scenario.yaml").resolve(),
        ),
    )
    observations: dict[
        bool,
        tuple[float, MovementReason, TargetingDisposition, int],
    ] = {}
    for enabled in (True, False):
        session = prepared.build(
            ("phase115-direct-action-on" if enabled else "phase115-direct-action-off"),
            seed=115,
            max_ticks=10,
            strict_mode=True,
        )
        tank = session.context.units_by_side["british"][0]
        target = session.context.units_by_side["german"][0]
        main_gun = next(
            attachment
            for attachment in session.context.unit_weapons[tank.entity_id]
            if attachment.weapon.weapon_id == "ak74_545mm"
        )
        ammunition = main_gun.first_fireable_ammunition()
        assert ammunition is not None
        ammunition_before = main_gun.weapon.ammo_state.available(
            ammunition.ammo_id,
        )
        events: list[Event] = []
        session.context.event_bus.subscribe(Event, events.append)

        assert session.step() is False

        observation = session.context.movement_diagnostics.get_unit(
            tank.entity_id,
        ).recent_observations[-1]
        decision = observation.targeting_decision
        assert decision is not None
        assert decision.target_id == target.entity_id
        assert decision.weapon_id == main_gun.weapon.weapon_id
        assert decision.weapon_source_equipment_index == main_gun.source_equipment_index
        assert decision.ammunition_id == ammunition.ammo_id
        assert decision.can_engage
        revalidation = session.context.tactical_targeting.engagement_revalidation_for(
            engine_tick=decision.engine_tick,
            battle_id=decision.battle_id,
            shooter_id=decision.shooter_id,
        )
        assert revalidation is not None
        assert revalidation.revalidation_passed
        assert revalidation.disposition is (TargetingDisposition.VALID_ENGAGEMENT_SOLUTION)
        assert revalidation.target_id == decision.target_id
        assert revalidation.weapon_id == decision.weapon_id
        assert revalidation.ammunition_id == decision.ammunition_id

        ammunition_after = main_gun.weapon.ammo_state.available(
            ammunition.ammo_id,
        )
        ammunition_delta = ammunition_before - ammunition_after
        expenditure_events = [
            event
            for event in events
            if isinstance(event, AmmoExpendedEvent)
            and event.unit_id == tank.entity_id
            and event.ammo_type == ammunition.ammo_id
        ]
        engagement_events = [
            event
            for event in events
            if isinstance(event, EngagementEvent)
            and event.attacker_id == tank.entity_id
            and event.target_id == target.entity_id
            and event.weapon_id == main_gun.weapon.weapon_id
            and event.ammo_type == ammunition.ammo_id
        ]
        assert ammunition_delta > 0
        assert len(expenditure_events) == 1
        assert expenditure_events[0].quantity == ammunition_delta
        assert len(engagement_events) == 1
        # Hit resolution is a later stochastic gate; either terminal result
        # proves the same catalog-backed direct action was committed.
        assert engagement_events[0].result in {"hit", "miss"}
        observations[enabled] = (
            tank.position.easting,
            observation.reason,
            decision.disposition,
            ammunition_delta,
        )

    enabled = observations[True]
    disabled = observations[False]
    assert enabled[0] == pytest.approx(1_000.0)
    assert enabled[1] is MovementReason.ENGINE_WEAPON_STANDOFF
    assert enabled[2] is TargetingDisposition.VALID_STANDOFF_HOLD
    assert disabled[0] > enabled[0]
    assert disabled[1] is MovementReason.MOVED
    assert disabled[2] is TargetingDisposition.STANDOFF_DISABLED
    assert enabled[3] == disabled[3] > 0


def test_fow_current_witness_is_the_same_local_targeting_authority() -> None:
    """The canonical FOW draw supplies one exact same-shooter witness."""
    session = _build(
        _prepare(
            target_easting=1_000.0,
            target_northing=1_800.0,
            fog_of_war=True,
        )
    )
    tank = session.context.units_by_side["british"][0]

    assert session.step() is False

    observation = session.context.movement_diagnostics.get_unit(
        tank.entity_id,
    ).recent_observations[-1]
    decision = observation.targeting_decision
    assert decision is not None
    assert observation.reason is MovementReason.ENGINE_WEAPON_STANDOFF
    assert decision.fog_of_war_enabled is True
    assert decision.contact_source is ContactSource.FOW_OBSERVER_WITNESS
    assert decision.observing_unit_id == tank.entity_id
    assert decision.contact_time_s == pytest.approx(
        session.context.clock.elapsed.total_seconds(),
    )
    witnesses = session.context.fog_of_war.get_current_detection_witnesses(
        "british",
    )
    exact = [
        witness
        for witness in witnesses
        if (
            witness.detected
            and witness.observer_unit_id == tank.entity_id
            and witness.target_id == decision.target_id
            and witness.source_equipment_index == decision.contact_sensor_source_equipment_index
            and witness.sensor_id == decision.contact_sensor_id
        )
    ]
    assert len(exact) == 1
    assert exact[0].logical_time_s == decision.logical_time_s
    revalidation = session.context.tactical_targeting.engagement_revalidation_for(
        engine_tick=decision.engine_tick,
        battle_id=decision.battle_id,
        shooter_id=decision.shooter_id,
    )
    assert revalidation is not None
    assert revalidation.revalidation_passed is True


def test_fow_visual_witness_beyond_visibility_cannot_authorize_targeting() -> None:
    """A real successful optical draw cannot bypass the hard visibility cap."""
    raw = _mark_iv_scenario(
        target_easting=1_000.0,
        target_northing=1_050.0,
        fog_of_war=True,
    ).model_dump(mode="json")
    raw["weather_conditions"]["visibility_m"] = 49.0
    prepared = SimulationRuntimeFactory().prepare_config(
        CampaignScenarioConfig.model_validate(raw),
        DATA_DIR,
        (AnalysisVariant(variant_id=VARIANT_ID),),
        source_label=SOURCE_LABEL,
    )
    session = _build(prepared)
    tank = session.context.units_by_side["british"][0]
    target = session.context.units_by_side["german"][0]

    assert session.step() is False

    witnesses = tuple(
        witness
        for witness in session.context.fog_of_war.get_current_detection_witnesses(
            "british",
        )
        if (
            witness.detected
            and witness.observer_unit_id == tank.entity_id
            and witness.target_id == target.entity_id
            and witness.sensor_type in {"VISUAL", "NVG"}
        )
    )
    assert len(witnesses) == 1
    assert witnesses[0].range_m == pytest.approx(50.0)
    assert witnesses[0].range_m > 49.0

    decision = session.context.tactical_targeting.latest_pictures()[0].decision_for(
        tank.entity_id,
    )
    assert decision is not None
    assert session.context.cal_flat["visibility_m"] == pytest.approx(49.0)
    assert session.context.weather_engine.current.visibility >= 49.0
    assert decision.disposition is TargetingDisposition.NO_CONTACT
    assert decision.target_id is None
    assert not decision.can_hold
    assert not decision.can_engage


def test_fow_off_boresight_target_has_no_ground_truth_fallback() -> None:
    """A close hostile outside the real observer sector cannot authorize hold."""
    session = _build(
        _prepare(
            target_easting=1_800.0,
            fog_of_war=True,
        )
    )
    tank = session.context.units_by_side["british"][0]
    before = tank.position

    assert session.step() is False

    observation = session.context.movement_diagnostics.get_unit(
        tank.entity_id,
    ).recent_observations[-1]
    decision = observation.targeting_decision
    assert observation.reason is MovementReason.MOVED
    assert tank.position != before
    assert decision is not None
    assert decision.disposition is TargetingDisposition.NO_CONTACT
    assert decision.target_id is None
    assert decision.can_hold is False
    assert decision.can_engage is False
    assert (
        session.context.tactical_targeting.engagement_revalidation_for(
            engine_tick=decision.engine_tick,
            battle_id=decision.battle_id,
            shooter_id=decision.shooter_id,
        )
        is None
    )


def test_post_movement_ammunition_failure_is_published_without_retargeting() -> None:
    """A live fault after picture publication yields one typed failed consume."""
    session = _build(
        _prepare(
            target_easting=1_800.0,
            sensing_aware_standoff=False,
        )
    )
    tank = session.context.units_by_side["british"][0]
    main_gun = next(
        attachment
        for attachment in session.context.unit_weapons[tank.entity_id]
        if attachment.weapon.weapon_id == "qf_6pdr_6cwt"
    )

    def exhaust_after_movement(unit, proposed_position):
        if unit.entity_id == tank.entity_id:
            for ammunition_id in main_gun.weapon.ammo_state.rounds_by_type:
                main_gun.weapon.ammo_state.rounds_by_type[ammunition_id] = 0
        return proposed_position

    session.engine.battle_manager._movement_committer = exhaust_after_movement

    assert session.step() is False

    observation = session.context.movement_diagnostics.get_unit(
        tank.entity_id,
    ).recent_observations[-1]
    decision = observation.targeting_decision
    assert decision is not None
    assert decision.can_engage is True
    outcome = session.context.tactical_targeting.engagement_revalidation_for(
        engine_tick=decision.engine_tick,
        battle_id=decision.battle_id,
        shooter_id=decision.shooter_id,
    )
    assert outcome is not None
    assert outcome.target_id == decision.target_id
    assert outcome.weapon_id == decision.weapon_id
    assert outcome.ammunition_id == decision.ammunition_id
    assert outcome.revalidation_passed is False
    assert outcome.disposition is (TargetingDisposition.NO_FIREABLE_AMMUNITION)


def test_later_overlapping_battle_revalidates_hold_after_earlier_movement() -> None:
    """An earlier battle's live mutation invalidates a prepublished hold."""
    raw = _mark_iv_scenario(target_easting=1_999.0).model_dump(mode="python")
    raw["sides"][1]["units"].append(
        {
            "unit_type": "german_sturmtruppen",
            "count": 1,
            "position": [6_000.0, 1_000.0, 0.0],
        }
    )
    prepared = SimulationRuntimeFactory().prepare_config(
        CampaignScenarioConfig.model_validate(raw),
        DATA_DIR,
        (AnalysisVariant(variant_id=VARIANT_ID),),
        source_label=SOURCE_LABEL,
    )
    session = _build(prepared)
    context = session.context
    tank = context.units_by_side["british"][0]
    targets = sorted(
        context.units_by_side["german"],
        key=lambda unit: unit.position.easting,
    )
    near_target, far_target = targets
    far_battle = BattleContext(
        battle_id="battle-a-far",
        start_tick=0,
        start_time=context.clock.current_time,
        involved_sides=["british", "german"],
        unit_ids={tank.entity_id, far_target.entity_id},
    )
    near_battle = BattleContext(
        battle_id="battle-b-near",
        start_tick=0,
        start_time=context.clock.current_time,
        involved_sides=["british", "german"],
        unit_ids={tank.entity_id, near_target.entity_id},
    )

    session.engine.battle_manager.prepare_tactical_interval(
        context,
        (far_battle, near_battle),
        5.0,
    )
    runtime = context.tactical_targeting
    far_decision = runtime.decision_for(
        engine_tick=0,
        battle_id=far_battle.battle_id,
        shooter_id=tank.entity_id,
    )
    near_decision = runtime.decision_for(
        engine_tick=0,
        battle_id=near_battle.battle_id,
        shooter_id=tank.entity_id,
    )
    assert far_decision is not None
    assert near_decision is not None
    assert not far_decision.can_hold
    assert near_decision.can_hold

    def reverse_far_movement(unit, proposed_position):
        if unit.entity_id == tank.entity_id:
            return Position(
                2.0 * unit.position.easting - proposed_position.easting,
                2.0 * unit.position.northing - proposed_position.northing,
                2.0 * unit.position.altitude - proposed_position.altitude,
            )
        return proposed_position

    session.engine.battle_manager._movement_committer = reverse_far_movement
    first_position = tank.position
    session.engine.battle_manager.execute_tick(context, far_battle, 5.0)
    assert tank.position != first_position
    live_distance_before_second = math.dist(
        tuple(tank.position),
        tuple(near_target.position),
    )
    assert live_distance_before_second > near_decision.authorized_standoff_m

    second_position = tank.position
    session.engine.battle_manager.execute_tick(context, near_battle, 5.0)
    assert tank.position != second_position
    observation = context.movement_diagnostics.get_unit(
        tank.entity_id,
    ).recent_observations[-1]
    assert observation.reason is MovementReason.MOVED
    assert observation.targeting_decision is near_decision
    hold_revalidation = observation.hold_revalidation
    assert hold_revalidation is not None
    assert hold_revalidation.key == near_decision.key
    assert hold_revalidation.target_id == near_decision.target_id
    assert hold_revalidation.live_distance_m == pytest.approx(
        live_distance_before_second,
    )
    assert hold_revalidation.live_distance_m > (near_decision.authorized_standoff_m)
    assert hold_revalidation.disposition is (TargetingDisposition.OUTSIDE_EFFECTIVE_RANGE)
    assert hold_revalidation.hold_authorized is False
    outcome = runtime.engagement_revalidation_for(
        engine_tick=0,
        battle_id=near_battle.battle_id,
        shooter_id=tank.entity_id,
    )
    assert outcome is not None
    assert not outcome.revalidation_passed
    assert outcome.disposition is TargetingDisposition.OUTSIDE_EFFECTIVE_RANGE


def test_movement_recomputes_live_fire_control_after_picture_degradation() -> None:
    """A condition loss after publication cannot preserve a stale hold."""
    raw = _mark_iv_scenario(
        target_easting=1_000.0,
        target_northing=2_000.0,
    ).model_dump(mode="python")
    raw["weather_conditions"]["visibility_m"] = 5_000.0
    raw["sides"][0]["units"][0]["unit_type"] = "iron_duke_bb"
    raw["sides"][1]["units"][0]["unit_type"] = "konig_bb"
    prepared = SimulationRuntimeFactory().prepare_config(
        CampaignScenarioConfig.model_validate(raw),
        DATA_DIR,
        (AnalysisVariant(variant_id=VARIANT_ID),),
        source_label=SOURCE_LABEL,
    )
    session = _build(prepared)
    context = session.context
    tank = context.units_by_side["british"][0]
    target = context.units_by_side["german"][0]
    battle = BattleContext(
        battle_id="battle-live-sensor-degradation",
        start_tick=0,
        start_time=context.clock.current_time,
        involved_sides=["british", "german"],
        unit_ids={tank.entity_id, target.entity_id},
    )
    session.engine.battle_manager.prepare_tactical_interval(
        context,
        (battle,),
        5.0,
    )
    runtime = context.tactical_targeting
    decision = runtime.decision_for(
        engine_tick=0,
        battle_id=battle.battle_id,
        shooter_id=tank.entity_id,
    )
    assert decision is not None
    assert decision.can_hold
    assert decision.fire_control_source is FireControlSource.SENSOR_ATTACHMENT
    assert decision.fire_control_sensor_source_equipment_index is not None
    sensor = next(
        attachment
        for attachment in context.unit_sensor_attachments[tank.entity_id]
        if (
            attachment.source_equipment_index == decision.fire_control_sensor_source_equipment_index
            and attachment.sensor_id == decision.fire_control_sensor_id
            and attachment.modeled_role is decision.fire_control_sensor_modeled_role
        )
    )
    assert sensor.sensor.equipment is not None
    published_range_m = decision.fire_control_range_m
    sensor.sensor.equipment.condition = 0.25
    assert sensor.sensor.effective_range < decision.distance_m
    assert decision.fire_control_range_m == published_range_m

    before = tank.position
    session.engine.battle_manager.execute_tick(context, battle, 5.0)
    assert tank.position != before
    observation = context.movement_diagnostics.get_unit(
        tank.entity_id,
    ).recent_observations[-1]
    assert observation.reason is MovementReason.MOVED
    assert observation.targeting_decision is decision
    hold_revalidation = observation.hold_revalidation
    assert hold_revalidation is not None
    assert hold_revalidation.key == decision.key
    assert hold_revalidation.target_id == decision.target_id
    assert hold_revalidation.live_distance_m == pytest.approx(
        decision.distance_m,
    )
    assert hold_revalidation.disposition is (TargetingDisposition.FIRE_CONTROL_RANGE_EXCEEDED)
    assert hold_revalidation.hold_authorized is False
    outcome = runtime.engagement_revalidation_for(
        engine_tick=0,
        battle_id=battle.battle_id,
        shooter_id=tank.entity_id,
    )
    assert outcome is not None
    assert outcome.revalidation_passed
    assert outcome.disposition is (TargetingDisposition.VALID_ENGAGEMENT_SOLUTION)
    assert (
        math.dist(
            (
                tank.position.easting,
                tank.position.northing,
                tank.position.altitude,
            ),
            (
                target.position.easting,
                target.position.northing,
                target.position.altitude,
            ),
        )
        < decision.distance_m
    )


def test_later_overlapping_battle_records_inactive_shooter_revalidation() -> None:
    """An earlier battle can invalidate the shooter without rewriting its card."""
    raw = _mark_iv_scenario(target_easting=1_800.0).model_dump(mode="python")
    raw["sides"][1]["units"].append(
        {
            "unit_type": "german_sturmtruppen",
            "count": 1,
            "position": [6_000.0, 1_000.0, 0.0],
        }
    )
    prepared = SimulationRuntimeFactory().prepare_config(
        CampaignScenarioConfig.model_validate(raw),
        DATA_DIR,
        (AnalysisVariant(variant_id=VARIANT_ID),),
        source_label=SOURCE_LABEL,
    )
    session = _build(prepared)
    context = session.context
    tank = context.units_by_side["british"][0]
    near_target, far_target = sorted(
        context.units_by_side["german"],
        key=lambda unit: unit.position.easting,
    )
    far_battle = BattleContext(
        battle_id="battle-a-inactivation",
        start_tick=0,
        start_time=context.clock.current_time,
        involved_sides=["british", "german"],
        unit_ids={tank.entity_id, far_target.entity_id},
    )
    near_battle = BattleContext(
        battle_id="battle-b-stale-hold",
        start_tick=0,
        start_time=context.clock.current_time,
        involved_sides=["british", "german"],
        unit_ids={tank.entity_id, near_target.entity_id},
    )
    session.engine.battle_manager.prepare_tactical_interval(
        context,
        (far_battle, near_battle),
        5.0,
    )
    runtime = context.tactical_targeting
    near_decision = runtime.decision_for(
        engine_tick=0,
        battle_id=near_battle.battle_id,
        shooter_id=tank.entity_id,
    )
    assert near_decision is not None
    assert near_decision.can_hold

    def disable_during_far_movement(unit, proposed_position):
        if unit.entity_id == tank.entity_id:
            object.__setattr__(unit, "status", UnitStatus.DISABLED)
        return proposed_position

    session.engine.battle_manager._movement_committer = disable_during_far_movement
    session.engine.battle_manager.execute_tick(context, far_battle, 5.0)
    assert tank.status is UnitStatus.DISABLED

    session.engine.battle_manager.execute_tick(context, near_battle, 5.0)
    observation = context.movement_diagnostics.get_unit(
        tank.entity_id,
    ).recent_observations[-1]
    assert observation.reason is MovementReason.INACTIVE
    assert observation.targeting_decision is near_decision
    hold_revalidation = observation.hold_revalidation
    assert hold_revalidation is not None
    assert hold_revalidation.key == near_decision.key
    assert hold_revalidation.target_id == near_decision.target_id
    assert hold_revalidation.disposition is TargetingDisposition.SHOOTER_INACTIVE
    assert hold_revalidation.hold_authorized is False
    assert (
        runtime.engagement_revalidation_for(
            engine_tick=near_decision.engine_tick,
            battle_id=near_decision.battle_id,
            shooter_id=near_decision.shooter_id,
        )
        is None
    )


@pytest.fixture
def hold_revalidation_checkpoint() -> tuple[RuntimeSession, dict]:
    """Return a pristine target and real format-115 live-hold checkpoint."""
    prepared = _prepare(target_easting=1_800.0)
    source = _build(prepared)
    target = _build(prepared)
    assert source.step() is False
    state = json.loads(source.engine.checkpoint().decode("utf-8"))
    candidates = [
        observation
        for summary in state["context"]["movement_diagnostics"]["units"].values()
        for observation in summary["recent_observations"]
        if observation["hold_revalidation"] is not None
    ]
    assert candidates
    return target, state


@pytest.mark.parametrize(
    ("corruption", "error_match"),
    (
        (
            "missing",
            "must accompany every consumable can-hold targeting decision",
        ),
        ("key", "key disagrees with targeting decision"),
        ("target", "target disagrees with targeting decision"),
        ("distance", "authorized hold exceeds the decision standoff range"),
        (
            "authorization",
            "valid solution inside the standoff range must authorize hold",
        ),
        ("disposition", "unsupported disposition"),
        ("extra_key", "invalid key topology"),
    ),
)
def test_corrupt_hold_revalidation_checkpoint_rejects_atomically(
    hold_revalidation_checkpoint: tuple[RuntimeSession, dict],
    corruption: str,
    error_match: str,
) -> None:
    """Malformed nested live-hold evidence cannot partially restore state."""
    target, valid = hold_revalidation_checkpoint
    invalid = copy.deepcopy(valid)
    observation = next(
        candidate
        for summary in invalid["context"]["movement_diagnostics"]["units"].values()
        for candidate in summary["recent_observations"]
        if candidate["hold_revalidation"] is not None
    )
    hold = observation["hold_revalidation"]
    decision = observation["targeting_decision"]
    assert hold is not None
    assert decision is not None
    if corruption == "missing":
        observation["hold_revalidation"] = None
    elif corruption == "key":
        hold["engine_tick"] += 1
    elif corruption == "target":
        hold["target_id"] = "not-the-published-target"
    elif corruption == "distance":
        hold["live_distance_m"] = decision["authorized_standoff_m"] + 1.0
    elif corruption == "authorization":
        hold["hold_authorized"] = False
    elif corruption == "disposition":
        hold["hold_authorized"] = False
        hold["disposition"] = "NO_TARGET"
    else:
        hold["unexpected"] = "value"

    before = target.engine.checkpoint()
    with pytest.raises(ValueError, match=error_match):
        target.engine.set_state(invalid)
    assert target.engine.checkpoint() == before


def test_hold_revalidation_checkpoint_round_trip_is_exact(
    hold_revalidation_checkpoint: tuple[RuntimeSession, dict],
) -> None:
    """A fresh runtime restores the nested decision, membership, and outcome."""
    resumed, valid = hold_revalidation_checkpoint

    resumed.engine.set_state(copy.deepcopy(valid))

    restored = json.loads(resumed.engine.checkpoint().decode("utf-8"))
    assert restored == valid
    restored_observations = [
        observation
        for summary in restored["context"]["movement_diagnostics"]["units"].values()
        for observation in summary["recent_observations"]
        if observation["hold_revalidation"] is not None
    ]
    assert restored_observations
    for observation in restored_observations:
        decision = observation["targeting_decision"]
        membership = observation["targeting_membership"]
        outcome = observation["hold_revalidation"]
        assert decision is not None
        assert membership is not None
        assert outcome is not None
        assert (
            outcome["engine_tick"],
            outcome["battle_id"],
            outcome["shooter_id"],
        ) == (
            decision["engine_tick"],
            decision["battle_id"],
            decision["shooter_id"],
        )
        assert outcome["target_id"] == decision["target_id"]
        assert outcome["target_id"] in membership["unit_ids"]
