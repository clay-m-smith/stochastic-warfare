"""Phase 115 targeting evidence in movement diagnostics and evaluation."""

from __future__ import annotations

import copy
from dataclasses import replace

import pytest

from stochastic_warfare.core.types import Domain, Position
from stochastic_warfare.entities.base import Unit
from stochastic_warfare.simulation.loadouts import WeaponModeledRole
from stochastic_warfare.simulation.movement_diagnostics import (
    MovementDecision,
    MovementDiagnostics,
    MovementHoldRevalidationOutcome,
    MovementReason,
    MovementStage,
    MovementTargetingMembership,
)
from stochastic_warfare.simulation.tactical_targeting import (
    ContactSource,
    EffectiveRangeBasis,
    FireControlSource,
    TacticalTargetingDecision,
    TargetingDisposition,
    targeting_decision_to_state,
)
from stochastic_warfare.validation.movement_diagnostics import (
    evaluate_movement_diagnostics,
)


def _targeting_decision(**overrides: object) -> TacticalTargetingDecision:
    values: dict[str, object] = {
        "engine_tick": 7,
        "logical_time_s": 30.0,
        "battle_id": "battle-alpha",
        "ordinal": 0,
        "shooter_id": "blue-1",
        "shooter_side": "blue",
        "shooter_domain": Domain.GROUND,
        "target_id": "red-1",
        "target_side": "red",
        "target_domain": Domain.GROUND,
        "distance_m": 500.0,
        "weapon_id": "direct-gun",
        "weapon_source_equipment_index": 2,
        "weapon_modeled_role": WeaponModeledRole.GROUND_DIRECT_FIRE,
        "ammunition_id": "direct-shell",
        "physical_max_range_m": 1_000.0,
        "predictive_effective_range_m": 800.0,
        "effective_range_basis": EffectiveRangeBasis.AUTHORED,
        "legacy_derived_reference_range_m": 800.0,
        "contact_source": ContactSource.NON_FOW_LOCAL_OBSERVATION,
        "observing_unit_id": "blue-1",
        "contact_sensor_source_equipment_index": None,
        "contact_sensor_id": None,
        "contact_sensor_modeled_role": None,
        "contact_time_s": 30.0,
        "contact_range_m": 1_000.0,
        "visibility_bound_m": 1_000.0,
        "sensing_sensor_source_equipment_index": None,
        "sensing_sensor_id": None,
        "sensing_sensor_modeled_role": None,
        "sensing_range_m": 1_000.0,
        "fire_control_source": FireControlSource.DIRECT_VISUAL,
        "fire_control_sensor_source_equipment_index": None,
        "fire_control_sensor_id": None,
        "fire_control_sensor_modeled_role": None,
        "fire_control_range_m": 1_000.0,
        "disposition": TargetingDisposition.VALID_STANDOFF_HOLD,
        "authorized_standoff_m": 800.0,
        "hold_authorized": True,
        "engagement_solution_valid": True,
        "sensing_aware_standoff_enabled": True,
        "fog_of_war_enabled": False,
        "consumable": True,
    }
    values.update(overrides)
    return TacticalTargetingDecision(**values)  # type: ignore[arg-type]


def _hold_revalidation(
    targeting: TacticalTargetingDecision,
    **overrides: object,
) -> MovementHoldRevalidationOutcome:
    values: dict[str, object] = {
        "engine_tick": targeting.engine_tick,
        "battle_id": targeting.battle_id,
        "shooter_id": targeting.shooter_id,
        "target_id": targeting.target_id,
        "live_distance_m": targeting.distance_m,
        "disposition": TargetingDisposition.VALID_ENGAGEMENT_SOLUTION,
        "hold_authorized": True,
    }
    values.update(overrides)
    return MovementHoldRevalidationOutcome(**values)  # type: ignore[arg-type]


def _movement(
    targeting: TacticalTargetingDecision | None,
    *,
    hold_revalidation: MovementHoldRevalidationOutcome | None = None,
) -> MovementDecision:
    membership = (
        None
        if targeting is None
        else MovementTargetingMembership(
            battle_id=targeting.battle_id,
            unit_ids=("blue-1", "red-1"),
        )
    )
    return MovementDecision(
        unit_id="blue-1",
        side="blue",
        reason=MovementReason.ENGINE_WEAPON_STANDOFF,
        attempted_m=0.0,
        pre_position=Position(0.0, 0.0, 0.0),
        post_position=Position(0.0, 0.0, 0.0),
        targeting_decision=targeting,
        targeting_membership=membership,
        hold_revalidation=(
            _hold_revalidation(targeting)
            if targeting is not None and targeting.can_hold and hold_revalidation is None
            else hold_revalidation
        ),
    )


def _unit(unit_id: str, side: str, easting: float) -> Unit:
    return Unit(
        entity_id=unit_id,
        position=Position(easting, 0.0, 0.0),
        side=side,
        unit_type="phase115-control",
        speed=10.0,
        max_speed=10.0,
    )


def test_targeting_decision_round_trip_is_exact_and_lossless() -> None:
    decision = _targeting_decision()
    source = MovementDiagnostics({"blue-1": "blue", "red-1": "red"})
    observations = source.record_batch(
        engine_tick=7,
        stage=MovementStage.TACTICAL,
        battle_id="battle-alpha",
        decisions=(_movement(decision),),
    )

    assert observations[0].targeting_decision is decision
    assert observations[0].targeting_membership == (
        MovementTargetingMembership(
            battle_id="battle-alpha",
            unit_ids=("blue-1", "red-1"),
        )
    )
    assert observations[0].hold_revalidation == _hold_revalidation(decision)
    state = source.get_state()
    encoded = state["units"]["blue-1"]["recent_observations"][0]["targeting_decision"]
    assert encoded == targeting_decision_to_state(decision)
    encoded_membership = state["units"]["blue-1"]["recent_observations"][0]["targeting_membership"]
    assert encoded_membership == {
        "battle_id": "battle-alpha",
        "unit_ids": ["blue-1", "red-1"],
    }
    encoded_hold = state["units"]["blue-1"]["recent_observations"][0]["hold_revalidation"]
    assert encoded_hold == {
        "engine_tick": 7,
        "battle_id": "battle-alpha",
        "shooter_id": "blue-1",
        "target_id": "red-1",
        "live_distance_m": 500.0,
        "disposition": "VALID_ENGAGEMENT_SOLUTION",
        "hold_authorized": True,
    }

    restored = MovementDiagnostics({"blue-1": "blue", "red-1": "red"})
    restored.set_state(
        state,
        expected_unit_sides={"blue-1": "blue", "red-1": "red"},
    )

    assert restored.get_state() == state
    restored_decision = (
        restored.get_unit(
            "blue-1",
        )
        .recent_observations[0]
        .targeting_decision
    )
    assert restored_decision == decision
    assert (
        restored.get_unit("blue-1").recent_observations[0].targeting_membership == observations[0].targeting_membership
    )
    assert restored.get_unit("blue-1").recent_observations[0].hold_revalidation == observations[0].hold_revalidation


@pytest.mark.parametrize(
    ("movement", "error_match"),
    (
        (
            replace(
                _movement(_targeting_decision()),
                hold_revalidation=None,
            ),
            "must accompany every consumable can-hold targeting decision",
        ),
        (
            _movement(
                _targeting_decision(
                    disposition=TargetingDisposition.STANDOFF_DISABLED,
                    authorized_standoff_m=0.0,
                    hold_authorized=False,
                ),
                hold_revalidation=_hold_revalidation(
                    _targeting_decision(),
                ),
            ),
            "is forbidden without a consumable can-hold targeting decision",
        ),
        (
            _movement(
                _targeting_decision(),
                hold_revalidation=_hold_revalidation(
                    _targeting_decision(),
                    battle_id="battle-bravo",
                ),
            ),
            "key disagrees with targeting decision",
        ),
        (
            _movement(
                _targeting_decision(),
                hold_revalidation=_hold_revalidation(
                    _targeting_decision(),
                    target_id="red-2",
                ),
            ),
            "target disagrees with targeting decision",
        ),
        (
            _movement(
                _targeting_decision(),
                hold_revalidation=_hold_revalidation(
                    _targeting_decision(),
                    live_distance_m=900.0,
                ),
            ),
            "authorized hold exceeds the decision standoff range",
        ),
        (
            _movement(
                _targeting_decision(),
                hold_revalidation=_hold_revalidation(
                    _targeting_decision(),
                    live_distance_m=500.0,
                    hold_authorized=False,
                ),
            ),
            "valid solution inside the standoff range must authorize hold",
        ),
        (
            _movement(
                _targeting_decision(),
                hold_revalidation=_hold_revalidation(
                    _targeting_decision(),
                    disposition=TargetingDisposition.NO_FIREABLE_AMMUNITION,
                    hold_authorized=False,
                ),
            ),
            "automatic standoff reason lacks authorized live hold",
        ),
    ),
)
def test_record_requires_exact_live_hold_revalidation_without_mutation(
    movement: MovementDecision,
    error_match: str,
) -> None:
    diagnostics = MovementDiagnostics({"blue-1": "blue", "red-1": "red"})
    before = diagnostics.get_state()

    with pytest.raises(ValueError, match=error_match):
        diagnostics.record_batch(
            engine_tick=7,
            stage=MovementStage.TACTICAL,
            battle_id="battle-alpha",
            decisions=(movement,),
        )

    assert diagnostics.get_state() == before


def test_historical_can_hold_evidence_forbids_live_revalidation() -> None:
    historical = _targeting_decision().as_historical()
    assert historical.hold_authorized is True
    assert historical.can_hold is False
    diagnostics = MovementDiagnostics({"blue-1": "blue", "red-1": "red"})

    observation = diagnostics.record_batch(
        engine_tick=7,
        stage=MovementStage.TACTICAL,
        battle_id="battle-alpha",
        decisions=(
            replace(
                _movement(historical),
                reason=MovementReason.AUTHORED_HOLD,
            ),
        ),
    )[0]

    assert observation.targeting_decision is historical
    assert observation.hold_revalidation is None
    assert diagnostics.get_state()["units"]["blue-1"]["recent_observations"][0]["hold_revalidation"] is None


@pytest.mark.parametrize(
    "decision",
    (
        _targeting_decision(engine_tick=8),
        _targeting_decision(battle_id="battle-bravo"),
        _targeting_decision(
            shooter_id="blue-2",
            observing_unit_id="blue-2",
        ),
        _targeting_decision(shooter_side="allied-blue"),
    ),
)
def test_record_rejects_cross_identity_targeting_without_mutation(
    decision: TacticalTargetingDecision,
) -> None:
    diagnostics = MovementDiagnostics({"blue-1": "blue", "red-1": "red"})
    before = diagnostics.get_state()

    with pytest.raises(ValueError, match="tick/battle/shooter/side identity"):
        diagnostics.record_batch(
            engine_tick=7,
            stage=MovementStage.TACTICAL,
            battle_id="battle-alpha",
            decisions=(_movement(decision),),
        )

    assert diagnostics.get_state() == before


def test_restore_rejects_cross_identity_targeting_without_mutation() -> None:
    source = MovementDiagnostics({"blue-1": "blue", "red-1": "red"})
    source.record_batch(
        engine_tick=7,
        stage=MovementStage.TACTICAL,
        battle_id="battle-alpha",
        decisions=(_movement(_targeting_decision()),),
    )
    invalid = copy.deepcopy(source.get_state())
    invalid["units"]["blue-1"]["recent_observations"][0]["targeting_decision"]["engine_tick"] = 8

    target = MovementDiagnostics({"blue-1": "blue", "red-1": "red"})
    before = target.get_state()
    with pytest.raises(ValueError, match="tick/battle/shooter/side identity"):
        target.set_state(
            invalid,
            expected_unit_sides={"blue-1": "blue", "red-1": "red"},
        )
    assert target.get_state() == before


@pytest.mark.parametrize(
    ("movement", "error_match"),
    (
        (
            replace(
                _movement(_targeting_decision()),
                targeting_membership=None,
            ),
            "must accompany every targeting decision",
        ),
        (
            replace(
                _movement(None),
                targeting_membership=MovementTargetingMembership(
                    battle_id="battle-alpha",
                    unit_ids=("blue-1", "red-1"),
                ),
            ),
            "requires a targeting decision",
        ),
        (
            replace(
                _movement(_targeting_decision()),
                targeting_membership=MovementTargetingMembership(
                    battle_id="battle-bravo",
                    unit_ids=("blue-1", "red-1"),
                ),
            ),
            "disagrees with movement battle identity",
        ),
        (
            replace(
                _movement(_targeting_decision()),
                targeting_membership=MovementTargetingMembership(
                    battle_id="battle-alpha",
                    unit_ids=("blue-1",),
                ),
            ),
            "omits the decision target",
        ),
        (
            replace(
                _movement(_targeting_decision()),
                targeting_membership=MovementTargetingMembership(
                    battle_id="battle-alpha",
                    unit_ids=("blue-1", "red-1", "yellow-1"),
                ),
            ),
            "references an unregistered movement unit",
        ),
    ),
)
def test_record_rejects_invalid_targeting_membership_without_mutation(
    movement: MovementDecision,
    error_match: str,
) -> None:
    diagnostics = MovementDiagnostics({"blue-1": "blue", "red-1": "red"})
    before = diagnostics.get_state()

    with pytest.raises(ValueError, match=error_match):
        diagnostics.record_batch(
            engine_tick=7,
            stage=MovementStage.TACTICAL,
            battle_id="battle-alpha",
            decisions=(movement,),
        )

    assert diagnostics.get_state() == before


@pytest.mark.parametrize(
    ("unit_ids", "error_match"),
    (
        (("red-1", "blue-1"), "canonical order"),
        (("blue-1", "red-1", "red-1"), "duplicate unit IDs"),
        (("blue-1", " red-1"), "without surrounding whitespace"),
        ((), "non-empty tuple"),
    ),
)
def test_targeting_membership_requires_canonical_exact_ids(
    unit_ids: tuple[str, ...],
    error_match: str,
) -> None:
    with pytest.raises(ValueError, match=error_match):
        MovementTargetingMembership(
            battle_id="battle-alpha",
            unit_ids=unit_ids,
        )


@pytest.mark.parametrize(
    ("corruption", "error_match"),
    (
        ("reorder", "canonical order"),
        ("unknown", "outside the checkpoint force roster"),
        ("omit_target", "omits the decision target"),
        ("missing", "must accompany every targeting decision"),
    ),
)
def test_restore_rejects_corrupt_targeting_membership_atomically(
    corruption: str,
    error_match: str,
) -> None:
    source = MovementDiagnostics({"blue-1": "blue", "red-1": "red"})
    source.record_batch(
        engine_tick=7,
        stage=MovementStage.TACTICAL,
        battle_id="battle-alpha",
        decisions=(_movement(_targeting_decision()),),
    )
    invalid = copy.deepcopy(source.get_state())
    observation = invalid["units"]["blue-1"]["recent_observations"][0]
    membership = observation["targeting_membership"]
    if corruption == "reorder":
        membership["unit_ids"] = list(reversed(membership["unit_ids"]))
    elif corruption == "unknown":
        membership["unit_ids"].append("yellow-1")
    elif corruption == "omit_target":
        membership["unit_ids"] = ["blue-1"]
    else:
        observation["targeting_membership"] = None

    target = MovementDiagnostics({"blue-1": "blue", "red-1": "red"})
    before = target.get_state()
    with pytest.raises(ValueError, match=error_match):
        target.set_state(
            invalid,
            expected_unit_sides={"blue-1": "blue", "red-1": "red"},
        )
    assert target.get_state() == before


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
def test_restore_rejects_corrupt_hold_revalidation_atomically(
    corruption: str,
    error_match: str,
) -> None:
    source = MovementDiagnostics({"blue-1": "blue", "red-1": "red"})
    source.record_batch(
        engine_tick=7,
        stage=MovementStage.TACTICAL,
        battle_id="battle-alpha",
        decisions=(_movement(_targeting_decision()),),
    )
    invalid = copy.deepcopy(source.get_state())
    observation = invalid["units"]["blue-1"]["recent_observations"][0]
    hold = observation["hold_revalidation"]
    if corruption == "missing":
        observation["hold_revalidation"] = None
    elif corruption == "key":
        hold["engine_tick"] = 8
    elif corruption == "target":
        hold["target_id"] = "red-2"
    elif corruption == "distance":
        hold["live_distance_m"] = 900.0
    elif corruption == "authorization":
        hold["hold_authorized"] = False
    elif corruption == "disposition":
        hold["hold_authorized"] = False
        hold["disposition"] = "NO_TARGET"
    else:
        hold["unexpected"] = "value"

    target = MovementDiagnostics({"blue-1": "blue", "red-1": "red"})
    before = target.get_state()
    with pytest.raises(ValueError, match=error_match):
        target.set_state(
            invalid,
            expected_unit_sides={"blue-1": "blue", "red-1": "red"},
        )
    assert target.get_state() == before


@pytest.mark.parametrize(
    "stage",
    (MovementStage.STRATEGIC, MovementStage.OPERATIONAL),
)
def test_non_tactical_observations_preserve_none_and_reject_targeting(
    stage: MovementStage,
) -> None:
    diagnostics = MovementDiagnostics({"blue-1": "blue", "red-1": "red"})
    without_targeting = replace(_movement(None), reason=MovementReason.NO_TARGET)
    observation = diagnostics.record_batch(
        engine_tick=7,
        stage=stage,
        battle_id="",
        decisions=(without_targeting,),
    )[0]
    assert observation.targeting_decision is None

    before = diagnostics.get_state()
    with pytest.raises(ValueError, match="only for tactical movement"):
        diagnostics.record_batch(
            engine_tick=8,
            stage=stage,
            battle_id="battle-alpha",
            decisions=(_movement(_targeting_decision(engine_tick=8)),),
        )
    assert diagnostics.get_state() == before


def test_evaluator_exposes_recorded_privileged_scalars_without_context_lookup() -> None:
    decision = _targeting_decision()
    diagnostics = MovementDiagnostics({"blue-1": "blue", "red-1": "red"})
    diagnostics.record_batch(
        engine_tick=7,
        stage=MovementStage.TACTICAL,
        battle_id="battle-alpha",
        decisions=(_movement(decision),),
    )
    blue = _unit("blue-1", "blue", 0.0)
    red = _unit("red-1", "red", 500.0)

    evaluation = evaluate_movement_diagnostics(
        diagnostics,
        {"blue": [blue], "red": [red]},
        context=object(),
    )
    fields_by_unit = evaluation.fields_by_unit()
    blue_fields = fields_by_unit["blue-1"]

    assert blue_fields["targeting_exposure_scope"] == "PRIVILEGED_ENGINE"
    assert blue_fields["targeting_engine_tick"] == 7
    assert blue_fields["targeting_battle_id"] == "battle-alpha"
    assert blue_fields["targeting_shooter_id"] == "blue-1"
    assert blue_fields["targeting_target_id"] == "red-1"
    assert blue_fields["targeting_disposition"] == "VALID_STANDOFF_HOLD"
    assert blue_fields["targeting_contact_source"] == ("NON_FOW_LOCAL_OBSERVATION")
    assert blue_fields["targeting_contact_time_s"] == 30.0
    assert blue_fields["targeting_physical_max_range_m"] == 1_000.0
    assert blue_fields["targeting_predictive_effective_range_m"] == 800.0
    assert blue_fields["targeting_sensing_range_m"] == 1_000.0
    assert blue_fields["targeting_fire_control_source"] == "DIRECT_VISUAL"
    assert blue_fields["targeting_fire_control_range_m"] == 1_000.0
    assert blue_fields["targeting_authorized_standoff_m"] == 800.0
    assert blue_fields["targeting_sensing_aware_standoff_enabled"] is True
    assert blue_fields["targeting_hold_revalidation_engine_tick"] == 7
    assert blue_fields["targeting_hold_revalidation_battle_id"] == "battle-alpha"
    assert blue_fields["targeting_hold_revalidation_shooter_id"] == "blue-1"
    assert blue_fields["targeting_hold_revalidation_target_id"] == "red-1"
    assert blue_fields["targeting_hold_revalidation_live_distance_m"] == 500.0
    assert blue_fields["targeting_hold_revalidation_disposition"] == "VALID_ENGAGEMENT_SOLUTION"
    assert blue_fields["targeting_hold_revalidation_hold_authorized"] is True

    red_fields = fields_by_unit["red-1"]
    assert red_fields["targeting_exposure_scope"] == "PRIVILEGED_ENGINE"
    assert red_fields["targeting_target_id"] is None
    assert red_fields["targeting_disposition"] is None
    assert red_fields["targeting_hold_revalidation_target_id"] is None
    assert red_fields["targeting_hold_revalidation_disposition"] is None
    assert red_fields["targeting_hold_revalidation_hold_authorized"] is None
