"""Focused integrity tests for Phase 118 performance receipts."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
import json
from typing import Any

import pytest
from pydantic import ValidationError

from stochastic_warfare.core.performance_receipts import (
    FOWCadenceRecoveryPeriodReceipt,
)
from stochastic_warfare.simulation.performance_flags import (
    DispatchReceipt,
    EffectivePerformanceFlags,
    FOWCadenceReceipt,
    FOWDetectionReceipt,
    FOWFusionReceipt,
    FOWIndexedRNGReceipt,
    FOWScanReceipt,
    FOWSelectionReceipt,
    FogOfWarCycleReceipt,
    LODDetectionReceipt,
    LODEngagementReceipt,
    LODMoraleReceipt,
    LODMovementReceipt,
    LODReceipt,
    PERFORMANCE_FLAG_ORDER,
    PERFORMANCE_FLAG_REGISTRY,
    PerformanceExecutionReceipt,
    PerformanceFlagClassification,
    PerformanceReceiptAccumulator,
    PerformanceReceiptDelta,
)


def _flags() -> EffectivePerformanceFlags:
    return EffectivePerformanceFlags.all_disabled()


def _cycle(side: str, tick: int = 0) -> FogOfWarCycleReceipt:
    return FogOfWarCycleReceipt(
        reporting_side=side,
        engine_tick=tick,
        observers=1,
        targets=2,
        sensors=2,
        target_opportunities=2,
        selection=FOWSelectionReceipt(
            brute_force_cycles=1,
            brute_force_admitted_targets=2,
        ),
        scan=FOWScanReceipt(
            operational_sensor_target_opportunities=2,
        ),
        cadence=FOWCadenceReceipt(
            attachment_cycles=2,
            operational_attachment_cycles=1,
            native_ready=2,
            lod_ready=2,
            admitted=1,
            offline=1,
        ),
        detection=FOWDetectionReceipt(
            api_calls=2,
            pre_rng_above_max_range_rejections=1,
            stochastic_draws=1,
            successes=1,
            published_witnesses=1,
        ),
        fusion=FOWFusionReceipt(
            position_measurement_candidates=1,
            position_measurement_groups=1,
            creations=1,
        ),
        indexed_rng=FOWIndexedRNGReceipt(
            blocks=1,
            detection_lanes=1,
            identification_lanes=1,
            transcript_entries=1,
        ),
        lod_detection=LODDetectionReceipt(
            active_attachments_admitted=1,
        ),
    )


def _interval_delta(
    *,
    side_count: int = 2,
    tactical_duration_microseconds: int = 5_000_000,
) -> PerformanceReceiptDelta:
    return PerformanceReceiptDelta(
        tactical_intervals=1,
        tactical_duration_microseconds=tactical_duration_microseconds,
        dispatch=DispatchReceipt(
            sequential_intervals=1,
            sequential_side_updates=side_count,
        ),
        lod=LODReceipt(
            active_classifications=4,
            engagement=LODEngagementReceipt(attacker_cycles_processed=4),
            morale=LODMoraleReceipt(unit_cycles_processed=4),
            movement=LODMovementReceipt(active_processed=4),
        ),
    )


def _zero_receipt_state() -> dict[str, Any]:
    return PerformanceExecutionReceipt.zero(
        effective_flags=_flags(),
    ).to_state()


def _one_side_interval_state() -> dict[str, Any]:
    state = _zero_receipt_state()
    state["tactical_intervals"] = 1
    state["tactical_duration_microseconds"] = 5_000_000
    state["fow"]["side_cycles"] = 1
    state["dispatch"]["sequential_intervals"] = 1
    state["dispatch"]["sequential_side_updates"] = 1
    return state


def _deferred_attachment_state(*, lod_deferred: bool) -> dict[str, Any]:
    state = _one_side_interval_state()
    state["fow"]["sensors"] = 1
    state["fow"]["scan"]["scheduled_attachment_skips"] = 1
    cadence = state["fow"]["cadence"]
    cadence.update(
        {
            "attachment_cycles": 1,
            "operational_attachment_cycles": 1,
            "native_ready": int(lod_deferred),
            "lod_ready": int(not lod_deferred),
            "deferred_native": int(not lod_deferred),
            "deferred_lod": int(lod_deferred),
        },
    )
    state["lod"]["detection"]["active_attachments_deferred"] = 1
    return state


def _native_recovery_execution_state() -> dict[str, Any]:
    state = _zero_receipt_state()
    state["tactical_intervals"] = 2
    state["tactical_duration_microseconds"] = 10_000_000
    state["fow"]["side_cycles"] = 2
    state["fow"]["sensors"] = 2
    state["fow"]["scan"]["scheduled_attachment_skips"] = 1
    state["fow"]["cadence"] = FOWCadenceReceipt(
        attachment_cycles=2,
        operational_attachment_cycles=2,
        native_ready=1,
        lod_ready=2,
        admitted=1,
        deferred_native=1,
        native_recoveries_by_period=(
            FOWCadenceRecoveryPeriodReceipt(
                deferral_period=2,
                recovery_admissions=1,
            ),
        ),
    ).to_state()
    state["dispatch"]["sequential_intervals"] = 2
    state["dispatch"]["sequential_side_updates"] = 2
    state["lod"]["detection"]["active_attachments_admitted"] = 1
    state["lod"]["detection"]["active_attachments_deferred"] = 1
    return state


def _commit_one_interval(
    accumulator: PerformanceReceiptAccumulator,
    owner: object,
) -> PerformanceExecutionReceipt:
    transaction = accumulator.begin(owner)
    accumulator.stage_fow_cycle(owner, transaction, _cycle("blue"))
    accumulator.stage_fow_cycle(owner, transaction, _cycle("red"))
    accumulator.stage(owner, transaction, _interval_delta())
    return accumulator.commit(owner, transaction)


def test_classification_registry_is_complete_canonical_and_immutable() -> None:
    assert tuple(PERFORMANCE_FLAG_REGISTRY) == PERFORMANCE_FLAG_ORDER
    assert len(PERFORMANCE_FLAG_REGISTRY) == 5
    assert (
        PERFORMANCE_FLAG_REGISTRY["enable_detection_culling"].classification
        is PerformanceFlagClassification.SEMANTICS_PRESERVING_EXECUTION_OPTIMIZATION
    )
    assert (
        PERFORMANCE_FLAG_REGISTRY["enable_scan_scheduling"].classification
        is PerformanceFlagClassification.MODEL_FIDELITY_APPROXIMATION
    )
    assert (
        PERFORMANCE_FLAG_REGISTRY["enable_lod"].classification
        is PerformanceFlagClassification.MODEL_FIDELITY_APPROXIMATION
    )

    with pytest.raises(TypeError):
        PERFORMANCE_FLAG_REGISTRY["enable_lod"] = PERFORMANCE_FLAG_REGISTRY["enable_detection_culling"]
    with pytest.raises(FrozenInstanceError):
        PERFORMANCE_FLAG_REGISTRY["enable_lod"].required_meaning = "changed"


@pytest.mark.parametrize("invalid", [0, 1, "false", None])
def test_effective_flags_require_strict_booleans(invalid: object) -> None:
    payload = _flags().to_state()
    payload["enable_lod"] = invalid

    with pytest.raises(ValidationError):
        EffectivePerformanceFlags.from_state(payload)


def test_effective_flags_reject_missing_and_extra_keys() -> None:
    missing = _flags().to_state()
    missing.pop("enable_soa")
    extra = _flags().to_state()
    extra["enable_unknown"] = False

    with pytest.raises(ValidationError):
        EffectivePerformanceFlags.from_state(missing)
    with pytest.raises(ValidationError):
        EffectivePerformanceFlags.from_state(extra)


def test_side_cycle_keeps_attachment_skips_out_of_target_counts() -> None:
    payload = _cycle("blue").to_state()
    payload["scan"] = FOWScanReceipt(
        scheduled_attachment_skips=1,
    ).to_state()
    payload["cadence"] = FOWCadenceReceipt(
        attachment_cycles=2,
        operational_attachment_cycles=1,
        native_ready=1,
        lod_ready=2,
        deferred_native=1,
        offline=1,
    ).to_state()
    payload["detection"] = FOWDetectionReceipt().to_state()
    payload["fusion"] = FOWFusionReceipt().to_state()
    payload["indexed_rng"] = FOWIndexedRNGReceipt().to_state()
    payload["lod_detection"] = LODDetectionReceipt(
        active_attachments_deferred=1,
    ).to_state()
    receipt = FogOfWarCycleReceipt.from_state(payload)

    assert receipt.target_opportunities == 2
    assert receipt.selection.admitted_targets == 2
    assert receipt.selection.pruned_targets == 0
    assert receipt.sensors == receipt.cadence.attachment_cycles == 2
    assert receipt.scan.scheduled_attachment_skips == receipt.cadence.deferred == 1
    assert receipt.scan.operational_sensor_target_opportunities == 0
    assert receipt.detection.api_calls == 0


def _recovery_bucket(
    period: int,
    *,
    recoveries: int = 1,
    with_work: int = 0,
    blocks: int = 0,
) -> FOWCadenceRecoveryPeriodReceipt:
    return FOWCadenceRecoveryPeriodReceipt(
        deferral_period=period,
        recovery_admissions=recoveries,
        recovery_admissions_with_indexed_work=with_work,
        indexed_detection_blocks=blocks,
    )


def test_cadence_recovery_buckets_round_trip_and_add_by_origin_period() -> None:
    left = FOWCadenceReceipt(
        attachment_cycles=2,
        operational_attachment_cycles=2,
        native_ready=2,
        lod_ready=2,
        admitted=2,
        native_recoveries_by_period=(
            _recovery_bucket(2),
            _recovery_bucket(5, with_work=1, blocks=2),
        ),
        lod_recoveries_by_period=(_recovery_bucket(5),),
    )
    right = FOWCadenceReceipt(
        attachment_cycles=2,
        operational_attachment_cycles=2,
        native_ready=2,
        lod_ready=2,
        admitted=2,
        native_recoveries_by_period=(
            _recovery_bucket(5, with_work=1, blocks=3),
            _recovery_bucket(20),
        ),
        lod_recoveries_by_period=(_recovery_bucket(20, with_work=1, blocks=1),),
    )

    combined = left.plus(right)

    assert tuple(bucket.deferral_period for bucket in combined.native_recoveries_by_period) == (2, 5, 20)
    period_five = combined.native_recoveries_by_period[1]
    assert period_five.recovery_admissions == 2
    assert period_five.recovery_admissions_with_indexed_work == 2
    assert period_five.indexed_detection_blocks == 5
    assert tuple(bucket.deferral_period for bucket in combined.lod_recoveries_by_period) == (5, 20)
    assert FOWCadenceReceipt.from_state(combined.to_state()) == combined


def test_recovery_cycle_does_not_require_origin_deferral_in_same_receipt() -> None:
    receipt = FOWCadenceReceipt(
        attachment_cycles=1,
        operational_attachment_cycles=1,
        native_ready=1,
        lod_ready=1,
        admitted=1,
        lod_recoveries_by_period=(_recovery_bucket(5, with_work=1, blocks=1),),
    )

    assert receipt.deferred == 0
    assert receipt.lod_recoveries_by_period[0].recovery_admissions == 1


@pytest.mark.parametrize(
    "buckets",
    [
        (_recovery_bucket(5), _recovery_bucket(2)),
        (_recovery_bucket(5), _recovery_bucket(5)),
    ],
)
def test_cadence_recovery_buckets_require_canonical_unique_periods(
    buckets: tuple[FOWCadenceRecoveryPeriodReceipt, ...],
) -> None:
    with pytest.raises(ValidationError, match="strictly increasing"):
        FOWCadenceReceipt(
            attachment_cycles=2,
            operational_attachment_cycles=2,
            admitted=2,
            native_recoveries_by_period=buckets,
        )


@pytest.mark.parametrize(
    "values",
    [
        {
            "deferral_period": 0,
            "recovery_admissions": 1,
        },
        {
            "deferral_period": 5,
            "recovery_admissions": 0,
        },
        {
            "deferral_period": 5,
            "recovery_admissions": 1,
            "recovery_admissions_with_indexed_work": 2,
            "indexed_detection_blocks": 2,
        },
        {
            "deferral_period": 5,
            "recovery_admissions": 2,
            "recovery_admissions_with_indexed_work": 2,
            "indexed_detection_blocks": 1,
        },
        {
            "deferral_period": 5,
            "recovery_admissions": 1,
            "recovery_admissions_with_indexed_work": 0,
            "indexed_detection_blocks": 1,
        },
    ],
)
def test_cadence_recovery_bucket_rejects_invalid_counts(
    values: dict[str, int],
) -> None:
    with pytest.raises(ValidationError):
        FOWCadenceRecoveryPeriodReceipt(**values)


def test_cadence_recoveries_cannot_exceed_admissions_or_indexed_blocks() -> None:
    with pytest.raises(ValidationError, match="cannot exceed admitted"):
        FOWCadenceReceipt(
            attachment_cycles=1,
            operational_attachment_cycles=1,
            admitted=1,
            native_recoveries_by_period=(_recovery_bucket(2, recoveries=2),),
        )

    payload = _cycle("blue").to_state()
    payload["cadence"]["native_recoveries_by_period"] = [
        _recovery_bucket(2, with_work=1, blocks=2).to_state(),
    ]
    with pytest.raises(ValidationError, match="cannot exceed indexed RNG blocks"):
        FogOfWarCycleReceipt.from_state(payload)


def test_side_cycle_requires_exact_observer_target_product() -> None:
    payload = _cycle("blue").to_state()
    payload["targets"] = 3

    with pytest.raises(ValidationError, match="observers times targets"):
        FogOfWarCycleReceipt.from_state(payload)


@pytest.mark.parametrize(
    ("field", "replacement", "match"),
    [
        (
            "scan",
            FOWScanReceipt(
                operational_sensor_target_opportunities=2,
                scheduled_attachment_skips=2,
            ),
            "scheduled attachment skips",
        ),
        (
            "indexed_rng",
            FOWIndexedRNGReceipt(
                blocks=1,
                detection_lanes=1,
                transcript_entries=0,
            ),
            "transcript entries",
        ),
        (
            "lod_detection",
            LODDetectionReceipt(active_attachments_admitted=2),
            "LOD tier admissions",
        ),
    ],
)
def test_side_cycle_rejects_cross_unit_reconciliation_errors(
    field: str,
    replacement: object,
    match: str,
) -> None:
    payload = _cycle("blue").to_state()
    assert isinstance(replacement, (FOWScanReceipt, FOWIndexedRNGReceipt, LODDetectionReceipt))
    payload[field] = replacement.to_state()

    with pytest.raises(ValidationError, match=match):
        FogOfWarCycleReceipt.from_state(payload)


@pytest.mark.parametrize("invalid", [-1, True, 1.0, "1"])
def test_receipt_integer_fields_are_strict_and_non_negative(invalid: object) -> None:
    payload = _cycle("blue").to_state()
    payload["observers"] = invalid

    with pytest.raises(ValidationError):
        FogOfWarCycleReceipt.from_state(payload)


def test_committed_receipt_has_frozen_public_shape_and_strict_round_trip() -> None:
    owner = object()
    accumulator = PerformanceReceiptAccumulator(
        owner=owner,
        effective_flags=_flags(),
    )

    receipt = _commit_one_interval(accumulator, owner)
    state = receipt.to_state()

    assert state["schema_version"] == 2
    assert receipt.complete_from_tick_zero is True
    assert receipt.tactical_interval_microseconds == 5_000_000
    assert receipt.tactical_intervals == 1
    assert receipt.tactical_duration_microseconds == 5_000_000
    assert receipt.fow.side_cycles == 2
    assert receipt.fow.cadence.attachment_cycles == 4
    assert receipt.lod.detection.active_attachments_admitted == 2
    assert receipt.lod.engagement.attacker_cycles_processed == 4
    assert receipt.lod.morale.unit_cycles_processed == 4
    assert receipt.lod.movement.active_processed == 4
    assert PerformanceExecutionReceipt.from_state(state) == receipt
    assert json.loads(json.dumps(state, allow_nan=False)) == state

    with pytest.raises(ValidationError):
        receipt.tactical_intervals = 99


def test_receipt_schema_two_rejects_v1_without_inventing_recovery_history() -> None:
    state = _zero_receipt_state()
    state["schema_version"] = 1

    with pytest.raises(ValidationError, match="strict integer 2"):
        PerformanceExecutionReceipt.from_state(state)


def test_cumulative_recovery_requires_its_flag_and_recorded_deferral() -> None:
    disabled = _native_recovery_execution_state()
    with pytest.raises(ValidationError, match="enable_scan_scheduling"):
        PerformanceExecutionReceipt.from_state(disabled)

    enabled = deepcopy(disabled)
    enabled["effective_flags"]["enable_scan_scheduling"] = True
    assert PerformanceExecutionReceipt.from_state(enabled).fow.cadence.native_recoveries_by_period

    fabricated = deepcopy(enabled)
    fabricated["fow"]["scan"]["scheduled_attachment_skips"] = 0
    fabricated["fow"]["cadence"] = FOWCadenceReceipt(
        attachment_cycles=2,
        operational_attachment_cycles=2,
        native_ready=2,
        lod_ready=2,
        admitted=2,
        native_recoveries_by_period=(
            FOWCadenceRecoveryPeriodReceipt(
                deferral_period=2,
                recovery_admissions=1,
            ),
        ),
    ).to_state()
    fabricated["lod"]["detection"]["active_attachments_admitted"] = 2
    fabricated["lod"]["detection"]["active_attachments_deferred"] = 0
    with pytest.raises(ValidationError, match="cannot exceed native deferrals"):
        PerformanceExecutionReceipt.from_state(fabricated)


def test_receipt_binds_and_reconciles_nondefault_runtime_cadence() -> None:
    owner = object()
    accumulator = PerformanceReceiptAccumulator(
        owner=owner,
        effective_flags=_flags(),
        tactical_interval_microseconds=3_000_000,
    )
    transaction = accumulator.begin(owner)
    accumulator.stage_fow_cycle(owner, transaction, _cycle("blue"))
    accumulator.stage_fow_cycle(owner, transaction, _cycle("red"))
    accumulator.stage(
        owner,
        transaction,
        _interval_delta(tactical_duration_microseconds=3_000_000),
    )

    receipt = accumulator.commit(owner, transaction)

    assert receipt.tactical_interval_microseconds == 3_000_000
    assert receipt.tactical_duration_microseconds == 3_000_000


def test_committed_receipt_rejects_unknown_topology_and_dispatch_mismatch() -> None:
    owner = object()
    accumulator = PerformanceReceiptAccumulator(
        owner=owner,
        effective_flags=_flags(),
    )
    receipt = _commit_one_interval(accumulator, owner)
    unknown = receipt.to_state()
    unknown["fow"]["unknown_count"] = 0
    mismatch = receipt.to_state()
    mismatch["dispatch"]["sequential_side_updates"] = 1

    with pytest.raises(ValidationError, match="Extra inputs"):
        PerformanceExecutionReceipt.from_state(unknown)
    with pytest.raises(ValidationError, match="FOW side_cycles"):
        PerformanceExecutionReceipt.from_state(mismatch)


def test_receipt_rejects_obsolete_millisecond_topology() -> None:
    state = _zero_receipt_state()
    state["tactical_duration_milliseconds"] = state.pop(
        "tactical_duration_microseconds",
    )

    with pytest.raises(ValidationError, match="tactical_duration_milliseconds"):
        PerformanceExecutionReceipt.from_state(state)


@pytest.mark.parametrize(
    "remove",
    (
        lambda state: state.pop("tactical_interval_microseconds"),
        lambda state: state["fow"]["fusion"].pop("predicted_microseconds"),
    ),
)
def test_receipt_rejects_missing_topology_at_every_depth(
    remove: Any,
) -> None:
    state = _zero_receipt_state()
    remove(state)

    with pytest.raises(ValueError, match="inexact topology"):
        PerformanceExecutionReceipt.from_state(state)


@pytest.mark.parametrize(
    "fusion_state",
    (
        {"predictions": 1, "predicted_microseconds": 0},
        {"predictions": 0, "predicted_microseconds": 1},
    ),
)
def test_fusion_receipt_reconciles_prediction_count_and_duration(
    fusion_state: dict[str, int],
) -> None:
    with pytest.raises(ValidationError, match="zero together"):
        FOWFusionReceipt.from_state(fusion_state)


def test_receipt_rejects_strtree_work_when_culling_is_disabled() -> None:
    state = _one_side_interval_state()
    state["fow"].update(
        {
            "observers": 1,
            "targets": 2,
            "target_opportunities": 2,
        },
    )
    state["fow"]["selection"].update(
        {
            "strtree_builds": 1,
            "strtree_queries": 1,
            "strtree_admitted_targets": 1,
            "strtree_pruned_targets": 1,
        },
    )

    with pytest.raises(ValidationError, match="enable_detection_culling"):
        PerformanceExecutionReceipt.from_state(state)

    state["effective_flags"]["enable_detection_culling"] = True
    PerformanceExecutionReceipt.from_state(state)


def test_receipt_rejects_native_deferral_when_scan_scheduling_is_disabled() -> None:
    state = _deferred_attachment_state(lod_deferred=False)

    with pytest.raises(ValidationError, match="enable_scan_scheduling"):
        PerformanceExecutionReceipt.from_state(state)

    state["effective_flags"]["enable_scan_scheduling"] = True
    PerformanceExecutionReceipt.from_state(state)


def test_receipt_rejects_lod_work_when_lod_is_disabled() -> None:
    deferred = _deferred_attachment_state(lod_deferred=True)
    classified = _zero_receipt_state()
    classified["lod"]["nearby_classifications"] = 1

    with pytest.raises(ValidationError, match="enable_lod"):
        PerformanceExecutionReceipt.from_state(deferred)
    with pytest.raises(ValidationError, match="enable_lod"):
        PerformanceExecutionReceipt.from_state(classified)

    deferred["effective_flags"]["enable_lod"] = True
    classified["effective_flags"]["enable_lod"] = True
    PerformanceExecutionReceipt.from_state(deferred)
    PerformanceExecutionReceipt.from_state(classified)


def test_receipt_rejects_soa_work_when_soa_is_disabled() -> None:
    selection = _one_side_interval_state()
    selection["fow"].update(
        {
            "observers": 1,
            "targets": 2,
            "target_opportunities": 2,
        },
    )
    selection["fow"]["selection"].update(
        {
            "soa_vector_builds": 1,
            "soa_vector_queries": 1,
            "soa_vector_admitted_targets": 1,
            "soa_vector_pruned_targets": 1,
        },
    )
    snapshot = _zero_receipt_state()
    snapshot["soa"]["pre_movement_builds"] = 1

    with pytest.raises(ValidationError, match="enable_soa"):
        PerformanceExecutionReceipt.from_state(selection)
    with pytest.raises(ValidationError, match="enable_soa"):
        PerformanceExecutionReceipt.from_state(snapshot)

    selection["effective_flags"]["enable_soa"] = True
    snapshot["effective_flags"]["enable_soa"] = True
    PerformanceExecutionReceipt.from_state(selection)
    PerformanceExecutionReceipt.from_state(snapshot)


def test_culling_takes_precedence_over_soa_target_selection() -> None:
    state = _one_side_interval_state()
    state["fow"].update(
        {
            "observers": 1,
            "targets": 2,
            "target_opportunities": 2,
        },
    )
    state["fow"]["selection"].update(
        {
            "soa_vector_builds": 1,
            "soa_vector_queries": 1,
            "soa_vector_admitted_targets": 2,
        },
    )
    state["effective_flags"].update(
        {
            "enable_detection_culling": True,
            "enable_soa": True,
        },
    )

    with pytest.raises(ValidationError, match="incompatible"):
        PerformanceExecutionReceipt.from_state(state)


def test_receipt_rejects_parallel_work_when_parallel_flag_is_disabled() -> None:
    state = _zero_receipt_state()
    state["tactical_intervals"] = 1
    state["tactical_duration_microseconds"] = 5_000_000
    state["fow"]["side_cycles"] = 2
    state["dispatch"].update(
        {
            "parallel_intervals": 1,
            "parallel_tasks_submitted": 2,
            "parallel_tasks_joined": 2,
        },
    )

    with pytest.raises(ValidationError, match="enable_parallel_detection"):
        PerformanceExecutionReceipt.from_state(state)

    state["effective_flags"]["enable_parallel_detection"] = True
    PerformanceExecutionReceipt.from_state(state)


@pytest.mark.parametrize(
    "lod_state",
    [
        {"engagement": {"attacker_cycles_processed": 1, "deferred": 1}},
        {"morale": {"unit_cycles_processed": 1, "deferred": 1}},
        {
            "movement": {
                "active_processed": 1,
                "nearby_processed": 0,
                "distant_processed": 0,
                "deferred": 1,
            },
        },
    ],
)
def test_lod_never_accepts_non_sensing_deferral(
    lod_state: dict[str, dict[str, int]],
) -> None:
    with pytest.raises(ValidationError, match="may not defer"):
        LODReceipt.from_state(lod_state)


def test_accumulator_is_owner_and_transaction_bound() -> None:
    owner = object()
    foreign_owner = object()
    accumulator = PerformanceReceiptAccumulator(
        owner=owner,
        effective_flags=_flags(),
    )
    foreign = PerformanceReceiptAccumulator(
        owner=foreign_owner,
        effective_flags=_flags(),
    )
    transaction = accumulator.begin(owner)
    foreign_transaction = foreign.begin(foreign_owner)

    with pytest.raises(RuntimeError, match="owner mismatch"):
        accumulator.stage(foreign_owner, transaction, PerformanceReceiptDelta())
    with pytest.raises(RuntimeError, match="owner mismatch"):
        accumulator.stage(owner, foreign_transaction, PerformanceReceiptDelta())
    with pytest.raises(RuntimeError, match="active transaction"):
        accumulator.get_state(owner)


def test_invalid_commit_is_atomic_and_permanently_poisoned() -> None:
    owner = object()
    accumulator = PerformanceReceiptAccumulator(
        owner=owner,
        effective_flags=_flags(),
    )
    baseline = accumulator.get_state(owner)
    transaction = accumulator.begin(owner)
    accumulator.stage_fow_cycle(owner, transaction, _cycle("blue"))
    accumulator.stage(owner, transaction, _interval_delta(side_count=1))
    accumulator.stage(
        owner,
        transaction,
        PerformanceReceiptDelta(
            lod=LODReceipt(
                detection=LODDetectionReceipt(
                    active_attachments_admitted=1,
                ),
            ),
        ),
    )

    with pytest.raises(ValidationError, match="LOD tier admissions"):
        accumulator.commit(owner, transaction)

    assert accumulator.poisoned is True
    assert accumulator._receipt.to_state() == baseline
    with pytest.raises(RuntimeError, match="poisoned"):
        accumulator.get_state(owner)
    with pytest.raises(RuntimeError, match="poisoned"):
        accumulator.begin(owner)


def test_explicit_poison_rejects_checkpoint_and_continued_capture() -> None:
    owner = object()
    accumulator = PerformanceReceiptAccumulator(
        owner=owner,
        effective_flags=_flags(),
    )
    transaction = accumulator.begin(owner)

    accumulator.poison(owner, transaction, reason="later battle failed")

    assert accumulator.poison_reason == "later battle failed"
    with pytest.raises(RuntimeError, match="later battle failed"):
        accumulator.checkpoint_state(owner)
    with pytest.raises(RuntimeError, match="poisoned"):
        accumulator.commit(owner, transaction)


def test_restore_is_atomic_owner_bound_and_preserves_incompleteness() -> None:
    owner = object()
    foreign_owner = object()
    accumulator = PerformanceReceiptAccumulator(
        owner=owner,
        effective_flags=_flags(),
    )
    committed = _commit_one_interval(accumulator, owner)
    plan = accumulator.stage_state(owner, committed.to_state())
    foreign = PerformanceReceiptAccumulator(
        owner=foreign_owner,
        effective_flags=_flags(),
    )

    with pytest.raises(RuntimeError, match="another owner"):
        foreign.commit_state(foreign_owner, plan)

    incomplete = accumulator.mark_incomplete(owner)
    assert incomplete.complete_from_tick_zero is False
    assert accumulator.set_state(owner, incomplete.to_state()) == incomplete

    complete_state = incomplete.to_state()
    complete_state["complete_from_tick_zero"] = True
    with pytest.raises(ValueError, match="cannot be promoted"):
        accumulator.set_state(owner, complete_state)
    assert accumulator.receipt(owner) == incomplete

    transaction = accumulator.begin(owner)
    accumulator.stage_fow_cycle(owner, transaction, _cycle("blue", tick=1))
    accumulator.stage_fow_cycle(owner, transaction, _cycle("red", tick=1))
    accumulator.stage(owner, transaction, _interval_delta())
    continued = accumulator.commit(owner, transaction)
    assert continued.complete_from_tick_zero is False
    assert continued.tactical_intervals == 2


def test_restore_rejects_flag_drift_without_mutation() -> None:
    owner = object()
    accumulator = PerformanceReceiptAccumulator(
        owner=owner,
        effective_flags=_flags(),
    )
    before = accumulator.get_state(owner)
    drifted = dict(before)
    drifted["effective_flags"] = {
        **before["effective_flags"],
        "enable_lod": True,
    }

    with pytest.raises(ValueError) as captured:
        accumulator.set_state(owner, drifted)

    message = str(captured.value)
    assert "enable_lod" in message
    assert "unsupported" in message.lower()
    assert accumulator.get_state(owner) == before


def test_restore_rejects_tactical_cadence_drift_without_mutation() -> None:
    owner = object()
    accumulator = PerformanceReceiptAccumulator(
        owner=owner,
        effective_flags=_flags(),
    )
    before = accumulator.get_state(owner)
    drifted = dict(before)
    drifted["tactical_interval_microseconds"] = 3_000_000

    with pytest.raises(ValueError, match="tactical cadence"):
        accumulator.set_state(owner, drifted)

    assert accumulator.get_state(owner) == before
