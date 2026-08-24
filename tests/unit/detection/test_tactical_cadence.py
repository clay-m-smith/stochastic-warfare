"""Focused behavioral tests for the Phase 118 tactical cadence scheduler."""

from __future__ import annotations

import copy
from dataclasses import replace
import hashlib
import json

import pytest

from stochastic_warfare.detection.cadence import (
    CADENCE_SCHEMA_VERSION,
    TacticalAttachmentIdentity,
    TacticalCadenceAttachment,
    TacticalCadenceDisposition,
    TacticalCadenceRecovery,
    TacticalCadenceRecoveryAxis,
    TacticalCadenceScheduler,
    TacticalNativePhaseAssignment,
    TacticalObserverIdentity,
)


def _identity(
    index: int = 0,
    *,
    side: str = "blue",
    unit_id: str = "blue-observer",
    sensor_id: str = "search-radar",
    modeled_role: str = "air_search",
) -> TacticalAttachmentIdentity:
    return TacticalAttachmentIdentity(
        reporting_side=side,
        observer_unit_id=unit_id,
        source_equipment_index=index,
        sensor_id=sensor_id,
        modeled_role=modeled_role,
    )


def _attachment(
    identity: TacticalAttachmentIdentity | None = None,
    *,
    native_period: int = 1,
    lod_period: int = 1,
    operational: bool = True,
) -> TacticalCadenceAttachment:
    return TacticalCadenceAttachment(
        identity=_identity() if identity is None else identity,
        native_period=native_period,
        lod_period=lod_period,
        operational=operational,
    )


def _commit_cycle(
    scheduler: TacticalCadenceScheduler,
    roster: list[TacticalCadenceAttachment],
) -> tuple[bool, ...]:
    plan = scheduler.stage_interval(roster)
    admissions = tuple(decision.admitted for decision in plan.decisions)
    scheduler.commit_interval(plan)
    return admissions


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("reporting_side", ""),
        ("reporting_side", " blue"),
        ("observer_unit_id", "observer "),
        ("source_equipment_index", True),
        ("source_equipment_index", -1),
        ("sensor_id", ""),
        ("modeled_role", "\ud800"),
    ],
)
def test_attachment_identity_rejects_invalid_exact_fields(
    field: str,
    value: object,
) -> None:
    values: dict[str, object] = {
        "reporting_side": "blue",
        "observer_unit_id": "observer",
        "source_equipment_index": 0,
        "sensor_id": "radar",
        "modeled_role": "air_search",
    }
    values[field] = value

    with pytest.raises(ValueError):
        TacticalAttachmentIdentity(**values)  # type: ignore[arg-type]


def test_new_attachment_is_first_ready_and_zero_target_sweep_consumes() -> None:
    scheduler = TacticalCadenceScheduler()
    identity = _identity()
    request = _attachment(identity, native_period=2, lod_period=20)

    plan = scheduler.stage_interval([request])

    assert plan.ordinal == 0
    assert scheduler.committed_ordinal == 0
    assert scheduler.attachment_states == ()
    decision = plan.decision_for(identity)
    assert decision.first_cycle is True
    assert decision.native_ready is True
    assert decision.lod_ready is True
    assert decision.admitted is True
    assert decision.disposition is TacticalCadenceDisposition.ADMITTED
    staged = plan.state_for(identity)
    assert staged.last_admission_ordinal == 0
    assert staged.native_pending_ready is False
    assert staged.lod_pending_ready is False
    # The scheduler receives no target count.  Committing the admitted sweep
    # therefore consumes readiness equally for zero and nonzero target sets.
    with pytest.raises(RuntimeError, match="active interval"):
        scheduler.get_state()

    scheduler.commit_interval(plan)

    assert scheduler.committed_ordinal == 1
    committed = scheduler.state_for(identity)
    assert committed == staged
    assert committed.native_next_due == 2
    assert committed.lod_next_due == 20


def test_prepared_commit_plan_freezes_state_mapping_until_bounded_swap() -> None:
    scheduler = TacticalCadenceScheduler()
    identity = _identity()
    interval = scheduler.stage_interval([_attachment(identity)])
    prepared = scheduler.prepare_interval_commit(interval)

    with pytest.raises(TypeError):
        prepared._states[identity] = interval.state_for(identity)  # type: ignore[index]
    with pytest.raises(AttributeError):
        prepared._states[identity].native_next_due = 99  # type: ignore[misc]
    with pytest.raises(RuntimeError, match="already prepared"):
        scheduler.stage_witness_promotions(interval, ())

    scheduler.validate_prepared_interval_commit(prepared)
    scheduler.commit_prepared_interval(prepared)
    assert scheduler.committed_ordinal == 1
    assert scheduler.state_for(identity) == interval.state_for(identity)


def test_complete_roster_is_canonical_and_rejects_duplicate_identity() -> None:
    scheduler = TacticalCadenceScheduler()
    red = _identity(2, side="red", unit_id="red-observer")
    blue_later = _identity(4)
    blue_earlier = _identity(1)

    plan = scheduler.stage_interval(
        [
            _attachment(red),
            _attachment(blue_later),
            _attachment(blue_earlier),
        ]
    )
    assert tuple(decision.identity for decision in plan.decisions) == (
        blue_earlier,
        blue_later,
        red,
    )
    scheduler.commit_interval(plan)
    assert tuple(state.identity for state in scheduler.attachment_states) == (
        blue_earlier,
        blue_later,
        red,
    )

    with pytest.raises(ValueError, match="duplicate identities"):
        scheduler.stage_interval([_attachment(blue_earlier), _attachment(blue_earlier)])
    assert scheduler.has_active_interval is False


@pytest.mark.parametrize(
    ("native_period", "lod_period", "expected_admissions"),
    [
        (2, 5, [0, 5, 10, 15, 20, 25, 30, 35, 40]),
        (2, 20, [0, 20, 40]),
    ],
)
def test_independent_pending_readiness_never_starves_period_pairs(
    native_period: int,
    lod_period: int,
    expected_admissions: list[int],
) -> None:
    scheduler = TacticalCadenceScheduler()
    request = _attachment(
        native_period=native_period,
        lod_period=lod_period,
    )
    admitted_ordinals: list[int] = []

    for ordinal in range(41):
        (admitted,) = _commit_cycle(scheduler, [request])
        if admitted:
            admitted_ordinals.append(ordinal)

    assert admitted_ordinals == expected_admissions
    assert scheduler.committed_ordinal == 41


def test_offline_attachment_accrues_one_pending_opportunity_without_burst() -> None:
    scheduler = TacticalCadenceScheduler()
    identity = _identity()
    admitted_ordinals: list[int] = []
    dispositions: list[TacticalCadenceDisposition] = []

    for ordinal, operational in enumerate([False, False, False, True, True, True, True]):
        plan = scheduler.stage_interval(
            [
                _attachment(
                    identity,
                    native_period=2,
                    lod_period=3,
                    operational=operational,
                )
            ]
        )
        decision = plan.decision_for(identity)
        dispositions.append(decision.disposition)
        if decision.admitted:
            admitted_ordinals.append(ordinal)
        scheduler.commit_interval(plan)

    assert dispositions[:3] == [
        TacticalCadenceDisposition.OFFLINE,
        TacticalCadenceDisposition.OFFLINE,
        TacticalCadenceDisposition.OFFLINE,
    ]
    assert admitted_ordinals == [3, 6]
    assert dispositions[4] is TacticalCadenceDisposition.DEFERRED_LOD
    assert dispositions[5] is TacticalCadenceDisposition.DEFERRED_LOD


def test_same_attachment_deferral_is_closed_only_by_later_admission() -> None:
    scheduler = TacticalCadenceScheduler()
    identity = _identity()
    request = _attachment(identity, native_period=2, lod_period=2)

    assert _commit_cycle(scheduler, [request]) == (True,)
    deferred = scheduler.stage_interval([request])
    assert deferred.decision_for(identity).disposition is (TacticalCadenceDisposition.DEFERRED_BOTH)
    deferred_state = deferred.state_for(identity)
    assert deferred_state.native_deferrals == 1
    assert deferred_state.lod_deferrals == 1
    assert deferred_state.native_pending_deferral_ordinal == 1
    assert deferred_state.lod_pending_deferral_ordinal == 1
    assert deferred_state.lod_pending_deferral_period == 2
    assert deferred_state.native_recovery_admissions == 0
    assert deferred_state.lod_recovery_admissions == 0
    scheduler.commit_interval(deferred)

    recovered = scheduler.stage_interval([request])
    decision = recovered.decision_for(identity)
    assert decision.admitted is True
    assert decision.recoveries == (
        TacticalCadenceRecovery(
            axis=TacticalCadenceRecoveryAxis.NATIVE,
            deferral_ordinal=1,
            admission_ordinal=2,
            deferral_period=2,
        ),
        TacticalCadenceRecovery(
            axis=TacticalCadenceRecoveryAxis.LOD,
            deferral_ordinal=1,
            admission_ordinal=2,
            deferral_period=2,
        ),
    )
    recovered_state = recovered.state_for(identity)
    assert recovered_state.native_pending_deferral_ordinal is None
    assert recovered_state.lod_pending_deferral_ordinal is None
    assert recovered_state.lod_pending_deferral_period is None
    assert recovered_state.native_recovery_admissions == 1
    assert recovered_state.lod_recovery_admissions == 1
    assert recovered_state.native_last_recovered_deferral_ordinal == 1
    assert recovered_state.native_last_recovery_ordinal == 2
    assert recovered_state.lod_last_recovered_deferral_ordinal == 1
    assert recovered_state.lod_last_recovery_ordinal == 2
    assert recovered_state.lod_last_recovered_deferral_period == 2


def test_native_and_lod_recovery_evidence_are_identity_and_axis_separate() -> None:
    scheduler = TacticalCadenceScheduler()
    native_identity = _identity(0)
    lod_identity = _identity(1)
    roster = [
        _attachment(native_identity, native_period=2, lod_period=1),
        _attachment(lod_identity, native_period=1, lod_period=2),
    ]

    assert _commit_cycle(scheduler, roster) == (True, True)
    deferred = scheduler.stage_interval(roster)
    native_state = deferred.state_for(native_identity)
    lod_state = deferred.state_for(lod_identity)
    assert deferred.decision_for(native_identity).disposition is (TacticalCadenceDisposition.DEFERRED_NATIVE)
    assert deferred.decision_for(lod_identity).disposition is (TacticalCadenceDisposition.DEFERRED_LOD)
    assert (native_state.native_deferrals, native_state.lod_deferrals) == (1, 0)
    assert native_state.native_pending_deferral_ordinal == 1
    assert native_state.lod_pending_deferral_ordinal is None
    assert (lod_state.native_deferrals, lod_state.lod_deferrals) == (0, 1)
    assert lod_state.native_pending_deferral_ordinal is None
    assert lod_state.lod_pending_deferral_ordinal == 1
    scheduler.commit_interval(deferred)

    recovered = scheduler.stage_interval(roster)
    assert tuple(
        recovery.axis
        for recovery in recovered.decision_for(native_identity).recoveries
    ) == (TacticalCadenceRecoveryAxis.NATIVE,)
    assert tuple(
        recovery.axis
        for recovery in recovered.decision_for(lod_identity).recoveries
    ) == (TacticalCadenceRecoveryAxis.LOD,)
    native_state = recovered.state_for(native_identity)
    lod_state = recovered.state_for(lod_identity)
    assert (native_state.native_recovery_admissions, native_state.lod_recovery_admissions) == (1, 0)
    assert (lod_state.native_recovery_admissions, lod_state.lod_recovery_admissions) == (0, 1)
    assert native_state.native_last_recovered_deferral_ordinal == 1
    assert native_state.native_last_recovery_ordinal == 2
    assert lod_state.lod_last_recovered_deferral_ordinal == 1
    assert lod_state.lod_last_recovery_ordinal == 2


def test_offline_cycles_neither_open_nor_close_recovery_evidence() -> None:
    scheduler = TacticalCadenceScheduler()
    identity = _identity()
    online = _attachment(identity, native_period=2, lod_period=2)
    offline = _attachment(
        identity,
        native_period=2,
        lod_period=2,
        operational=False,
    )

    assert _commit_cycle(scheduler, [online]) == (True,)
    for _ordinal in (1, 2):
        plan = scheduler.stage_interval([offline])
        assert plan.decision_for(identity).disposition is (TacticalCadenceDisposition.OFFLINE)
        assert plan.decision_for(identity).recoveries == ()
        state = plan.state_for(identity)
        assert state.native_deferrals == 0
        assert state.lod_deferrals == 0
        assert state.native_pending_deferral_ordinal is None
        assert state.lod_pending_deferral_ordinal is None
        scheduler.commit_interval(plan)

    admitted = scheduler.stage_interval([online])
    state = admitted.state_for(identity)
    assert admitted.decision_for(identity).admitted is True
    assert admitted.decision_for(identity).recoveries == ()
    assert state.native_recovery_admissions == 0
    assert state.lod_recovery_admissions == 0


def test_lod_recovery_retains_the_origin_period_across_period_change() -> None:
    scheduler = TacticalCadenceScheduler()
    identity = _identity()
    period_two = _attachment(identity, native_period=1, lod_period=2)
    period_five = _attachment(identity, native_period=1, lod_period=5)

    assert _commit_cycle(scheduler, [period_two]) == (True,)
    deferred = scheduler.stage_interval([period_two])
    assert deferred.state_for(identity).lod_pending_deferral_period == 2
    scheduler.commit_interval(deferred)

    for ordinal in (2, 3, 4):
        plan = scheduler.stage_interval([period_five])
        state = plan.state_for(identity)
        assert state.lod_pending_deferral_ordinal == 1
        assert state.lod_pending_deferral_period == 2
        assert plan.ordinal == ordinal
        scheduler.commit_interval(plan)

    recovered = scheduler.stage_interval([period_five])
    state = recovered.state_for(identity)
    assert recovered.ordinal == 5
    decision = recovered.decision_for(identity)
    assert decision.admitted is True
    assert decision.lod_period == 5
    assert decision.recoveries == (
        TacticalCadenceRecovery(
            axis=TacticalCadenceRecoveryAxis.LOD,
            deferral_ordinal=1,
            admission_ordinal=5,
            deferral_period=2,
        ),
    )
    assert state.lod_last_recovered_deferral_ordinal == 1
    assert state.lod_last_recovery_ordinal == 5
    assert state.lod_last_recovered_deferral_period == 2


@pytest.mark.parametrize(
    ("values", "match"),
    [
        (
            {
                "axis": "lod",
                "deferral_ordinal": 1,
                "admission_ordinal": 2,
                "deferral_period": 2,
            },
            "axis",
        ),
        (
            {
                "axis": TacticalCadenceRecoveryAxis.LOD,
                "deferral_ordinal": True,
                "admission_ordinal": 2,
                "deferral_period": 2,
            },
            "deferral_ordinal",
        ),
        (
            {
                "axis": TacticalCadenceRecoveryAxis.LOD,
                "deferral_ordinal": 2,
                "admission_ordinal": 2,
                "deferral_period": 2,
            },
            "precede",
        ),
        (
            {
                "axis": TacticalCadenceRecoveryAxis.LOD,
                "deferral_ordinal": 1,
                "admission_ordinal": 2,
                "deferral_period": 0,
            },
            "positive",
        ),
    ],
)
def test_recovery_event_rejects_inexact_or_impossible_values(
    values: dict[str, object],
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        TacticalCadenceRecovery(**values)  # type: ignore[arg-type]


def test_recovery_events_are_canonical_axis_unique_and_plan_ordinal_bound() -> None:
    scheduler = TacticalCadenceScheduler()
    request = _attachment(native_period=2, lod_period=2)
    for _ in range(2):
        _commit_cycle(scheduler, [request])
    plan = scheduler.stage_interval([request])
    decision = plan.decisions[0]
    native, lod = decision.recoveries

    with pytest.raises(ValueError, match="canonical order"):
        replace(decision, recoveries=(lod, native))
    with pytest.raises(ValueError, match="at most one"):
        replace(decision, recoveries=(native, native))
    with pytest.raises(ValueError, match="tuple"):
        replace(decision, recoveries=[native])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="later operational admission"):
        replace(decision, first_cycle=True)

    wrong_native_period = replace(native, deferral_period=3)
    with pytest.raises(ValueError, match="native period"):
        replace(decision, recoveries=(wrong_native_period, lod))

    wrong_ordinal = replace(native, admission_ordinal=3)
    decision_with_wrong_ordinal = replace(
        decision,
        recoveries=(wrong_ordinal, replace(lod, admission_ordinal=3)),
    )
    with pytest.raises(ValueError, match="plan ordinal"):
        replace(plan, decisions=(decision_with_wrong_ordinal,))


def test_lod_promotion_and_demotion_use_frozen_deadline_formulas() -> None:
    scheduler = TacticalCadenceScheduler()
    identity = _identity()
    _commit_cycle(
        scheduler,
        [_attachment(identity, native_period=1, lod_period=20)],
    )

    promotion = scheduler.stage_interval([_attachment(identity, native_period=1, lod_period=5)])
    promoted = promotion.state_for(identity)
    assert promotion.ordinal == 1
    assert promoted.current_lod_period == 5
    assert promoted.lod_next_due == 5
    assert promotion.decision_for(identity).disposition is (TacticalCadenceDisposition.DEFERRED_LOD)
    scheduler.commit_interval(promotion)

    demotion = scheduler.stage_interval([_attachment(identity, native_period=1, lod_period=20)])
    demoted = demotion.state_for(identity)
    assert demotion.ordinal == 2
    assert demoted.current_lod_period == 20
    assert demoted.lod_next_due == 20
    scheduler.commit_interval(demotion)


def test_demotion_preserves_readiness_accrued_while_offline() -> None:
    scheduler = TacticalCadenceScheduler()
    identity = _identity()
    _commit_cycle(
        scheduler,
        [
            _attachment(
                identity,
                native_period=5,
                lod_period=5,
                operational=False,
            )
        ],
    )

    plan = scheduler.stage_interval([_attachment(identity, native_period=5, lod_period=20)])

    decision = plan.decision_for(identity)
    assert decision.native_ready is True
    assert decision.lod_ready is True
    assert decision.admitted is True
    state = plan.state_for(identity)
    assert state.current_lod_period == 20
    assert state.lod_next_due == 21
    scheduler.commit_interval(plan)


def test_witness_promotion_to_period_one_is_ready_next_interval() -> None:
    scheduler = TacticalCadenceScheduler()
    identity = _identity()
    observer = identity.observer
    _commit_cycle(
        scheduler,
        [_attachment(identity, native_period=2, lod_period=20)],
    )

    plan = scheduler.stage_interval([_attachment(identity, native_period=2, lod_period=20)])
    assert plan.ordinal == 1
    assert plan.decision_for(identity).admitted is False
    promoted_plan = scheduler.stage_witness_promotions(
        plan,
        [observer, observer],
    )
    assert promoted_plan.witness_promoted_observers == (observer,)
    assert promoted_plan.state_for(identity).current_lod_period == 1
    assert promoted_plan.state_for(identity).lod_next_due == 2
    with pytest.raises(ValueError, match="stale"):
        scheduler.commit_interval(plan)
    scheduler.commit_interval(promoted_plan)

    next_plan = scheduler.stage_interval([_attachment(identity, native_period=2, lod_period=1)])
    assert next_plan.ordinal == 2
    assert next_plan.decision_for(identity).admitted is True
    scheduler.commit_interval(next_plan)


def test_unknown_witness_promotion_fails_without_invalidating_plan() -> None:
    scheduler = TacticalCadenceScheduler()
    request = _attachment()
    plan = scheduler.stage_interval([request])

    with pytest.raises(ValueError, match="absent observers"):
        scheduler.stage_witness_promotions(
            plan,
            [
                TacticalObserverIdentity(
                    reporting_side="red",
                    observer_unit_id="missing",
                )
            ],
        )

    scheduler.commit_interval(plan)
    assert scheduler.committed_ordinal == 1


def test_removed_attachment_is_pruned_only_when_complete_roster_commits() -> None:
    scheduler = TacticalCadenceScheduler()
    retained = _identity(0)
    removed = _identity(1)
    _commit_cycle(
        scheduler,
        [_attachment(retained), _attachment(removed)],
    )

    plan = scheduler.stage_interval([_attachment(retained)])

    assert tuple(state.identity for state in scheduler.attachment_states) == (
        retained,
        removed,
    )
    assert tuple(state.identity for state in plan.staged_states) == (retained,)
    scheduler.commit_interval(plan)
    assert tuple(state.identity for state in scheduler.attachment_states) == (retained,)


def test_interval_plan_is_owner_bound() -> None:
    first = TacticalCadenceScheduler()
    second = TacticalCadenceScheduler()
    first_plan = first.stage_interval([_attachment()])

    with pytest.raises(ValueError, match="another scheduler"):
        second.commit_interval(first_plan)

    first.commit_interval(first_plan)
    assert first.committed_ordinal == 1
    assert second.committed_ordinal == 0


def test_abort_retains_committed_state_and_poisons_checkpoint_boundary() -> None:
    scheduler = TacticalCadenceScheduler()
    identity = _identity()
    _commit_cycle(scheduler, [_attachment(identity)])
    committed_state = scheduler.attachment_states
    ordinal = scheduler.committed_ordinal
    plan = scheduler.stage_interval([])

    with pytest.raises(RuntimeError, match="active interval"):
        scheduler.get_state()
    scheduler.abort_interval(plan)

    assert scheduler.poisoned is True
    assert scheduler.has_active_interval is False
    assert scheduler.committed_ordinal == ordinal
    assert scheduler.attachment_states == committed_state
    with pytest.raises(RuntimeError, match="poisoned interval"):
        scheduler.get_state()
    with pytest.raises(RuntimeError, match="poisoned"):
        scheduler.stage_interval([])
    with pytest.raises(RuntimeError, match="poisoned interval"):
        scheduler.set_state(
            {
                "schema_version": CADENCE_SCHEMA_VERSION,
                "committed_ordinal": 0,
                "complete_from_tick_zero": True,
                "attachments": [],
            }
        )


def test_checkpoint_round_trip_is_exact_json_and_owner_bound() -> None:
    source = TacticalCadenceScheduler()
    first = _identity(0)
    second = _identity(1, sensor_id="infrared", modeled_role="ir_search")
    _commit_cycle(
        source,
        [
            _attachment(first, native_period=2, lod_period=5),
            _attachment(second, native_period=1, lod_period=20),
        ],
    )
    _commit_cycle(
        source,
        [
            _attachment(first, native_period=2, lod_period=5),
            _attachment(second, native_period=1, lod_period=20),
        ],
    )
    state = source.get_state()
    assert set(state["attachments"][0]).issuperset(
        {
            "native_deferrals",
            "lod_deferrals",
            "native_recovery_admissions",
            "lod_recovery_admissions",
            "native_pending_deferral_ordinal",
            "lod_pending_deferral_ordinal",
            "native_last_recovered_deferral_ordinal",
            "native_last_recovery_ordinal",
            "lod_last_recovered_deferral_ordinal",
            "lod_last_recovery_ordinal",
            "lod_pending_deferral_period",
            "lod_last_recovered_deferral_period",
        },
    )
    encoded = json.dumps(
        state,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
    )

    target = TacticalCadenceScheduler()
    restore_plan = target.stage_state(json.loads(encoded))
    target.commit_state(restore_plan)

    assert target.get_state() == state
    assert target.attachment_states == source.attachment_states
    foreign = TacticalCadenceScheduler()
    with pytest.raises(ValueError, match="another scheduler"):
        foreign.commit_state(restore_plan)


def _checkpoint_with_two_attachments() -> dict[str, object]:
    scheduler = TacticalCadenceScheduler()
    _commit_cycle(
        scheduler,
        [_attachment(_identity(0)), _attachment(_identity(1))],
    )
    return scheduler.get_state()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda state: state.update({"extra": 1}),
        lambda state: state.update({"schema_version": True}),
        lambda state: state.update({"committed_ordinal": False}),
        lambda state: state.update({"complete_from_tick_zero": 1}),
        lambda state: state.update({"attachments": "not-a-list"}),
        lambda state: state["attachments"].reverse(),
        lambda state: state["attachments"].append(copy.deepcopy(state["attachments"][0])),
        lambda state: state["attachments"][0].update({"native_next_due": 0}),
        lambda state: state["attachments"][0].update({"lod_next_due": 0}),
        lambda state: state["attachments"][0].update({"last_admission_ordinal": state["committed_ordinal"]}),
        lambda state: state["attachments"][0].update({"native_pending_ready": "false"}),
        lambda state: state["attachments"][0].pop("native_deferrals"),
        lambda state: state["attachments"][0].update({"native_deferrals": True}),
        lambda state: state["attachments"][0].update({"native_recovery_admissions": 1}),
        lambda state: state["attachments"][0].update({"native_pending_deferral_ordinal": 0}),
        lambda state: state["attachments"][0].update({"lod_pending_deferral_period": 2}),
        lambda state: state["attachments"][0]["identity"].update({"sensor_id": ""}),
    ],
)
def test_invalid_checkpoint_rejects_atomically(mutate: object) -> None:
    target = TacticalCadenceScheduler()
    _commit_cycle(target, [_attachment(_identity(8))])
    before = target.get_state()
    invalid = _checkpoint_with_two_attachments()
    mutate(invalid)  # type: ignore[operator]

    with pytest.raises(ValueError):
        target.set_state(invalid)

    assert target.get_state() == before


@pytest.mark.parametrize(
    "mutate",
    [
        lambda attachment, _committed: attachment.update(
            {"native_last_recovered_deferral_ordinal": 2},
        ),
        lambda attachment, committed: attachment.update(
            {
                "native_deferrals": 2,
                "native_pending_deferral_ordinal": committed,
            },
        ),
        lambda attachment, _committed: attachment.update(
            {"lod_last_recovered_deferral_period": 0},
        ),
        lambda attachment, _committed: attachment.pop(
            "lod_last_recovered_deferral_ordinal",
        ),
    ],
)
def test_recovery_checkpoint_chronology_tamper_rejects_atomically(
    mutate: object,
) -> None:
    source = TacticalCadenceScheduler()
    request = _attachment(native_period=2, lod_period=2)
    for _ in range(3):
        _commit_cycle(source, [request])
    invalid = source.get_state()
    attachment = invalid["attachments"][0]
    mutate(attachment, invalid["committed_ordinal"])  # type: ignore[operator]

    target = TacticalCadenceScheduler()
    _commit_cycle(target, [_attachment(_identity(8))])
    before = target.get_state()
    with pytest.raises(ValueError):
        target.set_state(invalid)

    assert target.get_state() == before


@pytest.mark.parametrize("axis", ("native", "lod"))
@pytest.mark.parametrize("pending_offset", (0, -1))
def test_pending_deferral_must_follow_last_admission_atomically(
    axis: str,
    pending_offset: int,
) -> None:
    source = TacticalCadenceScheduler()
    request = _attachment(native_period=1, lod_period=1)
    for _ in range(3):
        _commit_cycle(source, [request])
    invalid = source.get_state()
    attachment = invalid["attachments"][0]
    last_admission = attachment["last_admission_ordinal"]
    assert last_admission == 2
    attachment[f"{axis}_deferrals"] = 1
    attachment[f"{axis}_pending_deferral_ordinal"] = last_admission + pending_offset
    if axis == "lod":
        attachment["lod_pending_deferral_period"] = 1

    target = TacticalCadenceScheduler()
    _commit_cycle(target, [_attachment(_identity(8))])
    before = target.get_state()

    with pytest.raises(ValueError, match="must follow the last admission"):
        target.set_state(invalid)

    assert target.get_state() == before


@pytest.mark.parametrize("axis", ("native", "lod"))
def test_pending_deferral_without_prior_admission_rejects_atomically(
    axis: str,
) -> None:
    source = TacticalCadenceScheduler()
    _commit_cycle(
        source,
        [_attachment(operational=False, native_period=2, lod_period=5)],
    )
    invalid = source.get_state()
    attachment = invalid["attachments"][0]
    assert attachment["last_admission_ordinal"] is None
    attachment[f"{axis}_deferrals"] = 1
    attachment[f"{axis}_pending_deferral_ordinal"] = 0
    if axis == "lod":
        attachment["lod_pending_deferral_period"] = 5

    target = TacticalCadenceScheduler()
    _commit_cycle(target, [_attachment(_identity(8))])
    before = target.get_state()

    with pytest.raises(ValueError, match="requires a prior admission"):
        target.set_state(invalid)

    assert target.get_state() == before


def test_checkpoint_without_admission_must_retain_both_readiness_bits() -> None:
    source = TacticalCadenceScheduler()
    _commit_cycle(
        source,
        [_attachment(operational=False, native_period=2, lod_period=5)],
    )
    state = source.get_state()
    assert state["attachments"][0]["last_admission_ordinal"] is None
    invalid = copy.deepcopy(state)
    invalid["attachments"][0]["lod_pending_ready"] = False

    with pytest.raises(ValueError, match="must retain readiness"):
        TacticalCadenceScheduler().set_state(invalid)


def test_completeness_can_only_transition_from_true_to_false() -> None:
    source = TacticalCadenceScheduler()
    _commit_cycle(source, [_attachment()])
    incomplete = source.get_state()
    incomplete["complete_from_tick_zero"] = False
    target = TacticalCadenceScheduler()
    target.set_state(incomplete)
    assert target.complete_from_tick_zero is False

    _commit_cycle(target, [_attachment()])
    assert target.complete_from_tick_zero is False
    forbidden = target.get_state()
    forbidden["complete_from_tick_zero"] = True
    before = target.get_state()

    with pytest.raises(ValueError, match="cannot be promoted"):
        target.set_state(forbidden)

    assert target.get_state() == before


def test_native_period_is_immutable_for_retained_attachment() -> None:
    scheduler = TacticalCadenceScheduler()
    identity = _identity()
    _commit_cycle(
        scheduler,
        [_attachment(identity, native_period=2, lod_period=1)],
    )
    before = scheduler.get_state()

    with pytest.raises(ValueError, match="native cadence period changed"):
        scheduler.stage_interval([_attachment(identity, native_period=3, lod_period=1)])

    assert scheduler.has_active_interval is False
    assert scheduler.get_state() == before


def test_empty_complete_roster_advances_global_ordinal() -> None:
    scheduler = TacticalCadenceScheduler()

    for expected in range(1, 4):
        plan = scheduler.stage_interval([])
        assert plan.decisions == ()
        scheduler.commit_interval(plan)
        assert scheduler.committed_ordinal == expected


def _registry_digest(state: dict[str, object]) -> str:
    raw = json.dumps(
        {"native_phase_assignments": state["native_phase_assignments"]},
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _refresh_registry_digest(state: dict[str, object]) -> None:
    state["native_phase_assignments_sha256"] = _registry_digest(state)


def test_period_one_assignment_is_zero_phase_and_exposed_everywhere() -> None:
    scheduler = TacticalCadenceScheduler()
    identity = _identity()

    plan = scheduler.stage_interval([_attachment(identity, native_period=1)])

    assignment = plan.phase_assignments[0]
    assert type(assignment) is TacticalNativePhaseAssignment
    assert assignment.native_assignment_ordinal == 0
    assert assignment.native_phase_residue == 0
    decision = plan.decision_for(identity)
    assert decision.native_assignment_ordinal == 0
    assert decision.native_phase_residue == 0
    staged = plan.state_for(identity)
    assert staged.native_assignment_ordinal == 0
    assert staged.native_phase_residue == 0
    assert staged.native_next_due == 1

    scheduler.commit_interval(plan)
    assert scheduler.phase_assignments == (assignment,)
    state = scheduler.get_state()
    assert state["schema_version"] == 2
    assert state["native_phase_assignments"][0] == assignment.get_state()
    assert state["native_phase_assignments_sha256"] == _registry_digest(state)


@pytest.mark.parametrize(
    ("period", "count", "expected_residues"),
    [
        (2, 2, (0, 1)),
        (2, 3, (0, 1, 0)),
        (5, 3, (0, 1, 2)),
        (3, 8, (0, 1, 2, 0, 1, 2, 0, 1)),
    ],
)
def test_group_assignment_prefix_is_balanced_for_all_roster_sizes(
    period: int,
    count: int,
    expected_residues: tuple[int, ...],
) -> None:
    scheduler = TacticalCadenceScheduler()
    roster = [_attachment(_identity(index), native_period=period) for index in reversed(range(count))]

    plan = scheduler.stage_interval(roster)

    assert tuple(assignment.native_assignment_ordinal for assignment in plan.phase_assignments) == tuple(range(count))
    assert tuple(assignment.native_phase_residue for assignment in plan.phase_assignments) == expected_residues
    counts = [expected_residues.count(residue) for residue in range(period)]
    assert max(counts) - min(counts) <= 1


def test_phase_groups_are_side_sensor_role_and_period_isolated() -> None:
    scheduler = TacticalCadenceScheduler()
    identities = (
        _identity(0),
        _identity(1),
        _identity(2, side="red", unit_id="red-observer"),
        _identity(3, sensor_id="infrared"),
        _identity(4, modeled_role="surface_search"),
        _identity(5),
    )
    roster = [
        _attachment(identities[5], native_period=3),
        _attachment(identities[4], native_period=2),
        _attachment(identities[3], native_period=2),
        _attachment(identities[2], native_period=2),
        _attachment(identities[1], native_period=2),
        _attachment(identities[0], native_period=2),
    ]

    plan = scheduler.stage_interval(roster)
    assignments = {assignment.identity: assignment for assignment in plan.phase_assignments}

    assert (
        assignments[identities[0]].native_assignment_ordinal,
        assignments[identities[1]].native_assignment_ordinal,
    ) == (0, 1)
    for identity in identities[2:]:
        assert assignments[identity].native_assignment_ordinal == 0
        assert assignments[identity].native_phase_residue == 0


def test_two_period_two_attachments_are_first_ready_then_alternate() -> None:
    scheduler = TacticalCadenceScheduler()
    phase_zero = _identity(0)
    phase_one = _identity(1)
    roster = [
        _attachment(phase_zero, native_period=2),
        _attachment(phase_one, native_period=2),
    ]
    observed: list[tuple[bool, bool]] = []
    deadlines: list[tuple[int, int]] = []

    for _ in range(7):
        plan = scheduler.stage_interval(roster)
        observed.append(
            (
                plan.decision_for(phase_zero).admitted,
                plan.decision_for(phase_one).admitted,
            ),
        )
        deadlines.append(
            (
                plan.state_for(phase_zero).native_next_due,
                plan.state_for(phase_one).native_next_due,
            ),
        )
        scheduler.commit_interval(plan)

    assert observed == [
        (True, True),
        (False, True),
        (True, False),
        (False, True),
        (True, False),
        (False, True),
        (True, False),
    ]
    assert deadlines == [
        (2, 1),
        (2, 3),
        (4, 3),
        (4, 5),
        (6, 5),
        (6, 7),
        (8, 7),
    ]


def test_retirement_reappearance_and_reinforcement_never_rephase() -> None:
    scheduler = TacticalCadenceScheduler()
    incumbent_zero = _identity(0)
    incumbent_one = _identity(1)
    reinforcement = _identity(2)
    initial = [
        _attachment(incumbent_zero, native_period=2),
        _attachment(incumbent_one, native_period=2),
    ]
    _commit_cycle(scheduler, initial)
    original = {assignment.identity: assignment for assignment in scheduler.phase_assignments}

    _commit_cycle(
        scheduler,
        [_attachment(incumbent_zero, native_period=2)],
    )
    assert tuple(assignment.identity for assignment in scheduler.phase_assignments) == (incumbent_zero, incumbent_one)

    reinforced = scheduler.stage_interval(
        [
            _attachment(reinforcement, native_period=2),
            _attachment(incumbent_zero, native_period=2),
        ],
    )
    reinforced_assignments = {assignment.identity: assignment for assignment in reinforced.phase_assignments}
    assert reinforced_assignments[incumbent_zero] == original[incumbent_zero]
    assert reinforced_assignments[incumbent_one] == original[incumbent_one]
    assert reinforced_assignments[reinforcement].native_assignment_ordinal == 2
    assert reinforced_assignments[reinforcement].native_phase_residue == 0
    scheduler.commit_interval(reinforced)

    returning = scheduler.stage_interval(
        [
            _attachment(incumbent_zero, native_period=2),
            _attachment(incumbent_one, native_period=2),
            _attachment(reinforcement, native_period=2),
        ],
    )
    returning_decision = returning.decision_for(incumbent_one)
    assert returning_decision.first_cycle is True
    assert returning_decision.admitted is True
    assert returning_decision.native_assignment_ordinal == 1
    assert returning_decision.native_phase_residue == 1
    assert returning.state_for(incumbent_one).native_next_due % 2 == 1


def test_operational_and_lod_changes_do_not_change_native_phase() -> None:
    scheduler = TacticalCadenceScheduler()
    identity = _identity(1)
    request = _attachment(
        identity,
        native_period=3,
        lod_period=20,
        operational=False,
    )
    _commit_cycle(scheduler, [request])
    assignment = scheduler.phase_assignments[0]

    promoted = scheduler.stage_interval(
        [_attachment(identity, native_period=3, lod_period=1)],
    )

    decision = promoted.decision_for(identity)
    assert decision.operational is True
    assert decision.native_assignment_ordinal == assignment.native_assignment_ordinal
    assert decision.native_phase_residue == assignment.native_phase_residue
    assert promoted.state_for(identity).current_lod_period == 1
    assert promoted.phase_assignments == (assignment,)


def test_failed_stage_and_abort_do_not_consume_assignment_ordinals() -> None:
    scheduler = TacticalCadenceScheduler()
    incumbent = _identity(0)
    valid_new = _identity(1)
    overflow_incumbent = _identity(2, sensor_id="overflow-radar")
    overflowing = _identity(3, sensor_id="overflow-radar")
    _commit_cycle(
        scheduler,
        [
            _attachment(incumbent, native_period=2),
            _attachment(overflow_incumbent, native_period=(1 << 64) - 1),
        ],
    )
    before = scheduler.get_state()

    with pytest.raises(ValueError, match="new attachment native deadline"):
        scheduler.stage_interval(
            [
                _attachment(valid_new, native_period=2),
                _attachment(overflowing, native_period=(1 << 64) - 1),
            ],
        )

    assert scheduler.has_active_interval is False
    assert scheduler.get_state() == before
    retry = scheduler.stage_interval(
        [
            _attachment(incumbent, native_period=2),
            _attachment(valid_new, native_period=2),
        ],
    )
    assert retry.decision_for(valid_new).native_assignment_ordinal == 1
    scheduler.commit_interval(retry)

    aborted_identity = _identity(4)
    committed_assignments = scheduler.phase_assignments
    aborted = scheduler.stage_interval(
        [_attachment(aborted_identity, native_period=2)],
    )
    assert len(aborted.phase_assignments) == len(committed_assignments) + 1
    scheduler.abort_interval(aborted)
    assert scheduler.phase_assignments == committed_assignments


def test_checkpoint_roundtrip_continuation_preserves_phase_sequence() -> None:
    source = TacticalCadenceScheduler()
    identities = (_identity(0), _identity(1), _identity(2))
    roster = [_attachment(identity, native_period=2, lod_period=1) for identity in identities]
    for _ in range(4):
        _commit_cycle(source, roster)
    state = source.get_state()

    restored = TacticalCadenceScheduler()
    restored.set_state(copy.deepcopy(state))
    assert restored.get_state() == state
    assert restored.phase_assignments == source.phase_assignments

    for _ in range(8):
        source_plan = source.stage_interval(roster)
        restored_plan = restored.stage_interval(list(reversed(roster)))
        assert restored_plan.decisions == source_plan.decisions
        assert restored_plan.staged_states == source_plan.staged_states
        assert restored_plan.phase_assignments == source_plan.phase_assignments
        source.commit_interval(source_plan)
        restored.commit_interval(restored_plan)
        assert restored.get_state() == source.get_state()


def _phase_checkpoint() -> dict[str, object]:
    scheduler = TacticalCadenceScheduler()
    _commit_cycle(
        scheduler,
        [
            _attachment(_identity(0), native_period=2),
            _attachment(_identity(1), native_period=2),
        ],
    )
    return scheduler.get_state()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda state: state.update({"native_phase_assignments_sha256": "0" * 64}),
        lambda state: state.update({"native_phase_assignments_sha256": "A" * 64}),
        lambda state: state["native_phase_assignments"].reverse(),
        lambda state: state["native_phase_assignments"].append(
            copy.deepcopy(state["native_phase_assignments"][0]),
        ),
        lambda state: (
            state["native_phase_assignments"][1].update(
                {"native_assignment_ordinal": 2, "native_phase_residue": 0},
            ),
            _refresh_registry_digest(state),
        ),
        lambda state: (
            state["native_phase_assignments"][1].update(
                {"native_assignment_ordinal": 0, "native_phase_residue": 0},
            ),
            _refresh_registry_digest(state),
        ),
        lambda state: (
            state["native_phase_assignments"][1].update(
                {"native_phase_residue": 0},
            ),
            _refresh_registry_digest(state),
        ),
        lambda state: (
            state["native_phase_assignments"].pop(),
            _refresh_registry_digest(state),
        ),
        lambda state: state["attachments"][0].update(
            {"native_assignment_ordinal": 1},
        ),
        lambda state: state["attachments"][0].update(
            {"native_phase_residue": 1},
        ),
        lambda state: state["attachments"][0].update({"native_next_due": 3}),
        lambda state: state["native_phase_assignments"][0].update(
            {"native_assignment_ordinal": True},
        ),
    ],
)
def test_native_phase_checkpoint_tamper_rejects_atomically(mutate: object) -> None:
    target = TacticalCadenceScheduler()
    _commit_cycle(target, [_attachment(_identity(8))])
    before = target.get_state()
    invalid = _phase_checkpoint()
    mutate(invalid)  # type: ignore[operator]

    with pytest.raises(ValueError):
        target.set_state(invalid)

    assert target.get_state() == before
