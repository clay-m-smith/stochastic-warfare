"""Focused indexed FOW receipt and cadence integration tests for Phase 118."""

from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import numpy as np
import pytest

import stochastic_warfare.detection.fog_of_war as fog_of_war_module
from stochastic_warfare.core.indexed_rng import (
    FOWDecisionIdentity,
    FOWTargetKind,
    IndexedFOWRNG,
    encode_fow_decision,
)
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.detection.cadence import (
    TacticalAttachmentIdentity,
    TacticalCadenceAttachment,
    TacticalCadenceScheduler,
)
from stochastic_warfare.detection.deception import Decoy, DeceptionEngine, DeceptionType
from stochastic_warfare.detection.detection import (
    DetectionDecisionStage,
    DetectionEngine,
    DetectionResult,
    PreparedDetection,
)
from stochastic_warfare.detection.estimation import StateEstimator
from stochastic_warfare.detection.fog_of_war import (
    FogOfWarCadenceBinding,
    FogOfWarCycleOutcome,
    FogOfWarLodTier,
    FogOfWarManager,
    FogOfWarNativePhaseBinding,
    FogOfWarSensorBinding,
)
from stochastic_warfare.detection.identification import IdentificationEngine
from stochastic_warfare.detection.intel_fusion import IntelFusionEngine
from stochastic_warfare.detection.sensors import SensorDefinition, SensorInstance
from stochastic_warfare.detection.signatures import SignatureProfile, VisualSignature
from stochastic_warfare.simulation.loadouts import SensorModeledRole


def _sensor(
    *,
    sensor_id: str = "phase118-eye",
    maximum_range_m: float = 1_000.0,
) -> SensorInstance:
    return SensorInstance(
        SensorDefinition(
            sensor_id=sensor_id,
            sensor_type="VISUAL",
            display_name="Phase 118 Eye",
            max_range_m=maximum_range_m,
            detection_threshold=0.0,
            scan_interval_ticks=2,
        )
    )


def _signature() -> SignatureProfile:
    return SignatureProfile(
        profile_id="phase118-target-signature",
        unit_type="phase118-target",
        visual=VisualSignature(
            cross_section_m2=1_000.0,
            camouflage_factor=1.0,
        ),
    )


def _manager(
    *,
    seed: int = 118_100,
    identification: bool,
    complete_from_tick_zero: bool = True,
) -> FogOfWarManager:
    rng = np.random.Generator(np.random.PCG64(seed))
    estimator = StateEstimator(rng=rng)
    return FogOfWarManager(
        detection_engine=DetectionEngine(rng=rng),
        identification_engine=IdentificationEngine(rng) if identification else None,
        state_estimator=estimator,
        intel_fusion=IntelFusionEngine(state_estimator=estimator, rng=rng),
        deception_engine=DeceptionEngine(rng=rng),
        rng=rng,
        cadence_scheduler=TacticalCadenceScheduler(
            complete_from_tick_zero=complete_from_tick_zero,
        ),
    )


def _attachment_record(
    sensor: SensorInstance,
    *,
    source_equipment_index: int = 7,
) -> SimpleNamespace:
    return SimpleNamespace(
        sensor=sensor,
        source_equipment_index=source_equipment_index,
        sensor_id=sensor.sensor_id,
        modeled_role=SensorModeledRole.VISUAL_OBSERVATION,
    )


def _own_unit(
    sensor: SensorInstance,
    *,
    unit_id: str = "blue-observer",
    position: Position = Position(0.0, 0.0, 0.0),
) -> dict[str, object]:
    attachment = _attachment_record(sensor)
    return {
        "unit_id": unit_id,
        "position": position,
        "sensors": [sensor],
        "sensor_attachments": [attachment],
        "observer_height": 1.8,
        "observer_heading_deg": 0.0,
    }


def _target(
    target_id: str = "red-target",
    *,
    position: Position = Position(0.0, 0.0, 0.0),
) -> dict[str, object]:
    return {
        "unit_id": target_id,
        "position": position,
        "signature": _signature(),
        "unit": None,
        "target_height": 0.0,
        "concealment": 0.0,
        "posture": 0,
    }


def _attachment_identity(
    sensor: SensorInstance,
    *,
    unit_id: str = "blue-observer",
    side: str = "blue",
    source_equipment_index: int = 7,
) -> TacticalAttachmentIdentity:
    return TacticalAttachmentIdentity(
        reporting_side=side,
        observer_unit_id=unit_id,
        source_equipment_index=source_equipment_index,
        sensor_id=sensor.sensor_id,
        modeled_role=SensorModeledRole.VISUAL_OBSERVATION.value,
    )


def _begin_cycle(
    manager: FogOfWarManager,
    sensor: SensorInstance,
    *,
    tick: int,
    native_period: int = 1,
    lod_period: int = 1,
    operational: bool = True,
) -> tuple[object, object, object, object, object, TacticalAttachmentIdentity]:
    transaction = manager.begin_update_transaction(("blue",))
    identity = _attachment_identity(sensor)
    cadence_plan = manager.cadence.stage_interval(
        [
            TacticalCadenceAttachment(
                identity=identity,
                native_period=native_period,
                lod_period=lod_period,
                operational=operational,
            )
        ]
    )
    indexed = IndexedFOWRNG(118_200)
    allocation = indexed.begin_interval(
        module=ModuleId.DETECTION,
        engine_tick=tick,
        reporting_sides=("blue",),
    )
    handle = allocation.acquire_side("blue")
    return transaction, cadence_plan, indexed, allocation, handle, identity


def _run_cycle(
    manager: FogOfWarManager,
    sensor: SensorInstance,
    *,
    tick: int,
    targets: list[dict[str, object]],
    native_period: int = 1,
    lod_period: int = 1,
    detection_culling: bool = False,
    soa_selection: bool = False,
    decoys: list[Decoy] | None = None,
    interval_seconds: float = 5.0,
    time_origin_seconds: float = 0.0,
) -> tuple[FogOfWarCycleOutcome, object]:
    transaction, plan, indexed, allocation, handle, identity = _begin_cycle(
        manager,
        sensor,
        tick=tick,
        native_period=native_period,
        lod_period=lod_period,
    )
    side_plan = manager.update_with_receipt(
        "blue",
        [_own_unit(sensor)],
        targets,
        interval_seconds,
        transaction=transaction,
        cadence_plan=plan,
        indexed_rng=handle,
        lod_tiers={identity.observer: FogOfWarLodTier.ACTIVE},
        current_time=time_origin_seconds + (tick + 1) * interval_seconds,
        current_tick=tick,
        detection_culling=detection_culling,
        soa_selection=soa_selection,
        decoys=decoys,
    )
    publication = manager.prevalidate_update_transaction(
        transaction,
        (side_plan,),
    )
    record = indexed.commit_interval(allocation)
    manager.cadence.commit_interval(plan)
    manager.commit_update_transaction(publication)
    assert indexed.committed_interval_count == 1
    return side_plan.outcome, record


def _run_two_sensor_cycle(
    manager: FogOfWarManager,
    first_sensor: SensorInstance,
    second_sensor: SensorInstance,
    *,
    tick: int,
    targets: list[dict[str, object]],
    first_native_period: int,
    first_lod_period: int,
    reverse_scan_order: bool = False,
) -> tuple[FogOfWarCycleOutcome, object]:
    transaction = manager.begin_update_transaction(("blue",))
    identities = (
        _attachment_identity(first_sensor, source_equipment_index=7),
        _attachment_identity(second_sensor, source_equipment_index=8),
    )
    cadence_plan = manager.cadence.stage_interval(
        (
            TacticalCadenceAttachment(
                identity=identities[0],
                native_period=first_native_period,
                lod_period=first_lod_period,
                operational=True,
            ),
            TacticalCadenceAttachment(
                identity=identities[1],
                native_period=1,
                lod_period=1,
                operational=True,
            ),
        ),
    )
    indexed = IndexedFOWRNG(118_201)
    allocation = indexed.begin_interval(
        module=ModuleId.DETECTION,
        engine_tick=tick,
        reporting_sides=("blue",),
    )
    sensors = [first_sensor, second_sensor]
    attachments = [
        _attachment_record(first_sensor, source_equipment_index=7),
        _attachment_record(second_sensor, source_equipment_index=8),
    ]
    if reverse_scan_order:
        sensors.reverse()
        attachments.reverse()
    own_unit = {
        "unit_id": "blue-observer",
        "position": Position(0.0, 0.0, 0.0),
        "sensors": sensors,
        "sensor_attachments": attachments,
        "observer_height": 1.8,
        "observer_heading_deg": 0.0,
    }
    side_plan = manager.update_with_receipt(
        "blue",
        [own_unit],
        targets,
        5.0,
        transaction=transaction,
        cadence_plan=cadence_plan,
        indexed_rng=allocation.acquire_side("blue"),
        lod_tiers={identities[0].observer: FogOfWarLodTier.ACTIVE},
        current_time=(tick + 1) * 5.0,
        current_tick=tick,
        detection_culling=False,
    )
    publication = manager.prevalidate_update_transaction(
        transaction,
        (side_plan,),
    )
    record = indexed.commit_interval(allocation)
    manager.cadence.commit_interval(cadence_plan)
    manager.commit_update_transaction(publication)
    assert indexed.committed_interval_count == 1
    return side_plan.outcome, record


def test_prepared_detection_exposes_pre_rng_stage_without_consuming_rng() -> None:
    rng = np.random.Generator(np.random.PCG64(118_300))
    engine = DetectionEngine(rng=rng)
    sensor = _sensor(maximum_range_m=10.0)
    before = copy.deepcopy(rng.bit_generator.state)

    result = engine.prepare_detection(
        Position(0.0, 0.0, 0.0),
        Position(11.0, 0.0, 0.0),
        sensor,
        _signature(),
    )

    assert isinstance(result, DetectionResult)
    assert result.detected is False
    assert result.decision_stage is DetectionDecisionStage.PRE_RNG_ABOVE_MAX_RANGE
    assert rng.bit_generator.state == before


def test_prepared_detection_adjudicates_one_explicit_uniform() -> None:
    engine = DetectionEngine(rng=np.random.Generator(np.random.PCG64(118_301)))
    prepared = engine.prepare_detection(
        Position(0.0, 0.0, 0.0),
        Position(0.0, 0.0, 0.0),
        _sensor(),
        _signature(),
    )
    assert isinstance(prepared, PreparedDetection)

    result = prepared.adjudicate(0.5)

    assert result.detected is True
    assert result.decision_stage is DetectionDecisionStage.STOCHASTIC
    with pytest.raises(ValueError, match=r"in \[0, 1\)"):
        prepared.adjudicate(1.0)


def test_identification_explicit_uniform_does_not_advance_legacy_rng() -> None:
    rng = np.random.Generator(np.random.PCG64(118_302))
    engine = IdentificationEngine(rng)
    detection = DetectionResult(
        True,
        1.0,
        100.0,
        0.0,
        _sensor().sensor_type,
        0.0,
    )
    before = copy.deepcopy(rng.bit_generator.state)

    engine.classify_from_detection(
        detection,
        threshold_db=0.0,
        classification_uniform=0.5,
    )

    assert rng.bit_generator.state == before
    with pytest.raises(ValueError, match="either rng"):
        engine.classify_from_detection(
            detection,
            rng=rng,
            classification_uniform=0.5,
        )


@pytest.mark.parametrize(
    ("identification", "expected_mask", "expected_identification_lanes"),
    [(False, 1, 0), (True, 3, 1)],
)
def test_receipt_reconciles_indexed_detection_and_conditional_identification(
    identification: bool,
    expected_mask: int,
    expected_identification_lanes: int,
) -> None:
    manager = _manager(identification=identification)
    sensor = _sensor()

    outcome, record = _run_cycle(
        manager,
        sensor,
        tick=0,
        targets=[_target()],
    )

    receipt = outcome.receipt
    assert receipt.observers == 1
    assert receipt.targets == 1
    assert receipt.sensors == 1
    assert receipt.target_opportunities == 1
    assert receipt.selection.brute_force_cycles == 1
    assert receipt.selection.brute_force_admitted_targets == 1
    assert receipt.cadence.attachment_cycles == 1
    assert receipt.cadence.operational_attachment_cycles == 1
    assert receipt.cadence.native_ready == 1
    assert receipt.cadence.lod_ready == 1
    assert receipt.cadence.admitted == 1
    assert receipt.scan.operational_sensor_target_opportunities == 1
    assert receipt.detection.api_calls == 1
    assert receipt.detection.stochastic_draws == 1
    assert receipt.detection.successes == 1
    assert receipt.detection.published_witnesses == 1
    assert receipt.fusion.position_measurement_candidates == 1
    assert receipt.fusion.position_measurement_groups == 1
    assert receipt.fusion.correlated_candidates_elided == 0
    assert receipt.fusion.creations == 1
    assert receipt.indexed_rng.blocks == 1
    assert receipt.indexed_rng.detection_lanes == 1
    assert receipt.indexed_rng.identification_lanes == (expected_identification_lanes)
    assert receipt.indexed_rng.transcript_entries == 1
    assert receipt.lod_detection.active_attachments_admitted == 1
    assert len(record.entries) == 1
    assert record.entries[0].consumed_lane_mask == expected_mask


def test_same_epoch_sensor_attachments_share_one_position_measurement_group() -> None:
    manager = _manager(identification=True)
    first_sensor = _sensor(sensor_id="phase118-eye-a")
    second_sensor = _sensor(sensor_id="phase118-eye-b")

    outcome, record = _run_two_sensor_cycle(
        manager,
        first_sensor,
        second_sensor,
        tick=0,
        targets=[_target()],
        first_native_period=1,
        first_lod_period=1,
    )

    contact = outcome.world_view.contacts["red-target"]
    assert len(record.entries) == 2
    assert len(outcome.witnesses) == 2
    assert contact.reporting_sensors == ["phase118-eye-a", "phase118-eye-b"]
    assert outcome.receipt.detection.successes == 2
    assert outcome.receipt.fusion.position_measurement_candidates == 2
    assert contact.track.hits == 1
    assert outcome.receipt.fusion.position_measurement_groups == 1
    assert outcome.receipt.fusion.correlated_candidates_elided == 1
    assert outcome.receipt.fusion.creations == 1
    assert outcome.receipt.fusion.updates == 0
    assert outcome.receipt.indexed_rng.identification_lanes == 2


def test_same_epoch_fusion_is_exact_under_attachment_scan_permutation() -> None:
    first_sensor = _sensor(sensor_id="phase118-eye-a")
    second_sensor = _sensor(sensor_id="phase118-eye-b")
    forward_manager = _manager(identification=True)
    reverse_manager = _manager(identification=True)

    forward = _run_two_sensor_cycle(
        forward_manager,
        first_sensor,
        second_sensor,
        tick=0,
        targets=[_target()],
        first_native_period=1,
        first_lod_period=1,
    )
    reverse = _run_two_sensor_cycle(
        reverse_manager,
        first_sensor,
        second_sensor,
        tick=0,
        targets=[_target()],
        first_native_period=1,
        first_lod_period=1,
        reverse_scan_order=True,
    )

    assert reverse[0].world_view.get_state() == forward[0].world_view.get_state()
    assert reverse[0].receipt == forward[0].receipt
    assert reverse[0].witnesses == forward[0].witnesses
    assert reverse[1] == forward[1]
    assert reverse_manager.get_state() == forward_manager.get_state()


def test_pre_rng_rejection_has_api_call_but_no_indexed_block() -> None:
    manager = _manager(identification=False)
    sensor = _sensor(maximum_range_m=10.0)

    outcome, record = _run_cycle(
        manager,
        sensor,
        tick=0,
        targets=[
            _target(position=Position(11.0, 0.0, 0.0)),
        ],
    )

    receipt = outcome.receipt
    assert receipt.detection.api_calls == 1
    assert receipt.detection.pre_rng_above_max_range_rejections == 1
    assert receipt.detection.stochastic_draws == 0
    assert receipt.indexed_rng.blocks == 0
    assert record.entries == ()


def test_culling_uses_conservative_closed_square_before_canonical_range_gate() -> None:
    manager = _manager(identification=False)
    sensor = _sensor(maximum_range_m=100.0)

    outcome, record = _run_cycle(
        manager,
        sensor,
        tick=0,
        targets=[
            _target(position=Position(100.0, 100.0, 0.0)),
        ],
        detection_culling=True,
    )

    receipt = outcome.receipt
    assert receipt.selection.strtree_builds == 1
    assert receipt.selection.strtree_queries == 1
    assert receipt.selection.strtree_admitted_targets == 1
    assert receipt.selection.strtree_pruned_targets == 0
    assert receipt.detection.api_calls == 1
    assert receipt.detection.pre_rng_above_max_range_rejections == 1
    assert record.entries == ()


def test_culling_prunes_target_outside_closed_square_without_api_call() -> None:
    manager = _manager(identification=False)
    sensor = _sensor(maximum_range_m=100.0)

    outcome, record = _run_cycle(
        manager,
        sensor,
        tick=0,
        targets=[
            _target(position=Position(101.0, 0.0, 0.0)),
        ],
        detection_culling=True,
    )

    receipt = outcome.receipt
    assert receipt.selection.strtree_admitted_targets == 0
    assert receipt.selection.strtree_pruned_targets == 1
    assert receipt.detection.api_calls == 0
    assert record.entries == ()


def test_deferred_attachment_is_a_scheduled_skip_not_a_target_opportunity() -> None:
    manager = _manager(identification=False)
    sensor = _sensor()
    first, _record = _run_cycle(
        manager,
        sensor,
        tick=0,
        targets=[_target()],
        native_period=2,
    )
    assert first.receipt.cadence.admitted == 1

    second, record = _run_cycle(
        manager,
        sensor,
        tick=1,
        targets=[_target()],
        native_period=2,
    )

    receipt = second.receipt
    assert receipt.target_opportunities == 1
    assert receipt.cadence.deferred_native == 1
    assert receipt.scan.scheduled_attachment_skips == 1
    assert receipt.scan.operational_sensor_target_opportunities == 0
    assert receipt.detection.api_calls == 0
    assert record.entries == ()


def test_native_recovery_receipt_requires_same_admission_indexed_work() -> None:
    manager = _manager(identification=False)
    sensor = _sensor()
    _run_cycle(
        manager,
        sensor,
        tick=0,
        targets=[_target()],
        native_period=2,
        lod_period=1,
    )
    deferred, _record = _run_cycle(
        manager,
        sensor,
        tick=1,
        targets=[_target()],
        native_period=2,
        lod_period=1,
    )
    assert deferred.receipt.cadence.deferred_native == 1

    recovered, record = _run_cycle(
        manager,
        sensor,
        tick=2,
        targets=[_target(), _target("red-target-2")],
        native_period=2,
        lod_period=1,
    )

    assert len(record.entries) == 2
    assert recovered.receipt.indexed_rng.blocks == 2
    assert recovered.receipt.cadence.lod_recoveries_by_period == ()
    assert len(recovered.receipt.cadence.native_recoveries_by_period) == 1
    bucket = recovered.receipt.cadence.native_recoveries_by_period[0]
    assert bucket.deferral_period == 2
    assert bucket.recovery_admissions == 1
    assert bucket.recovery_admissions_with_indexed_work == 1
    assert bucket.indexed_detection_blocks == 2


def test_both_axis_recovery_receipts_share_one_indexed_detection_block() -> None:
    manager = _manager(identification=False)
    sensor = _sensor()
    _run_cycle(
        manager,
        sensor,
        tick=0,
        targets=[_target()],
        native_period=2,
        lod_period=2,
    )
    deferred, _record = _run_cycle(
        manager,
        sensor,
        tick=1,
        targets=[_target()],
        native_period=2,
        lod_period=2,
    )
    assert deferred.receipt.cadence.deferred_both == 1

    recovered, record = _run_cycle(
        manager,
        sensor,
        tick=2,
        targets=[_target()],
        native_period=2,
        lod_period=2,
    )

    assert len(record.entries) == 1
    assert recovered.receipt.indexed_rng.blocks == 1
    for buckets in (
        recovered.receipt.cadence.native_recoveries_by_period,
        recovered.receipt.cadence.lod_recoveries_by_period,
    ):
        assert len(buckets) == 1
        assert buckets[0].deferral_period == 2
        assert buckets[0].recovery_admissions == 1
        assert buckets[0].recovery_admissions_with_indexed_work == 1
        assert buckets[0].indexed_detection_blocks == 1


def test_recovery_pre_rng_rejection_does_not_invent_indexed_work() -> None:
    manager = _manager(identification=False)
    sensor = _sensor(maximum_range_m=10.0)
    distant_target = _target(position=Position(11.0, 0.0, 0.0))
    _run_cycle(
        manager,
        sensor,
        tick=0,
        targets=[distant_target],
        native_period=2,
        lod_period=1,
    )
    _run_cycle(
        manager,
        sensor,
        tick=1,
        targets=[distant_target],
        native_period=2,
        lod_period=1,
    )

    recovered, record = _run_cycle(
        manager,
        sensor,
        tick=2,
        targets=[distant_target],
        native_period=2,
        lod_period=1,
    )

    assert record.entries == ()
    assert recovered.receipt.detection.pre_rng_above_max_range_rejections == 1
    assert recovered.receipt.indexed_rng.blocks == 0
    bucket = recovered.receipt.cadence.native_recoveries_by_period[0]
    assert bucket.recovery_admissions == 1
    assert bucket.recovery_admissions_with_indexed_work == 0
    assert bucket.indexed_detection_blocks == 0


def test_unrelated_attachment_indexed_work_cannot_materialize_recovery() -> None:
    manager = _manager(identification=False)
    recovering_sensor = _sensor(
        sensor_id="phase118-short-eye",
        maximum_range_m=10.0,
    )
    working_sensor = _sensor(sensor_id="phase118-long-eye")
    distant_target = _target(position=Position(11.0, 0.0, 0.0))
    for tick in (0, 1):
        _run_two_sensor_cycle(
            manager,
            recovering_sensor,
            working_sensor,
            tick=tick,
            targets=[distant_target],
            first_native_period=2,
            first_lod_period=1,
        )

    recovered, record = _run_two_sensor_cycle(
        manager,
        recovering_sensor,
        working_sensor,
        tick=2,
        targets=[distant_target],
        first_native_period=2,
        first_lod_period=1,
    )

    assert len(record.entries) == 1
    assert record.entries[0].decision_preimage == encode_fow_decision(
        FOWDecisionIdentity(
            engine_tick=2,
            reporting_side="blue",
            observer_unit_id="blue-observer",
            source_equipment_index=8,
            sensor_id="phase118-long-eye",
            modeled_role=SensorModeledRole.VISUAL_OBSERVATION.value,
            target_kind=FOWTargetKind.UNIT,
            target_id="red-target",
        ),
    )
    assert recovered.receipt.indexed_rng.blocks == 1
    assert recovered.receipt.detection.pre_rng_above_max_range_rejections == 1
    bucket = recovered.receipt.cadence.native_recoveries_by_period[0]
    assert bucket.recovery_admissions == 1
    assert bucket.recovery_admissions_with_indexed_work == 0
    assert bucket.indexed_detection_blocks == 0


def test_aborted_recovery_plan_does_not_publish_staged_recovery_state() -> None:
    manager = _manager(identification=False)
    sensor = _sensor()
    _run_cycle(
        manager,
        sensor,
        tick=0,
        targets=[_target()],
        native_period=2,
        lod_period=1,
    )
    _run_cycle(
        manager,
        sensor,
        tick=1,
        targets=[_target()],
        native_period=2,
        lod_period=1,
    )
    cadence_before = manager.cadence.attachment_states
    fog_before = manager.snapshot_side("blue")
    fusion_before = manager.intel_fusion.get_state()
    transaction, cadence_plan, indexed, allocation, handle, identity = _begin_cycle(
        manager,
        sensor,
        tick=2,
        native_period=2,
        lod_period=1,
    )

    side_plan = manager.update_with_receipt(
        "blue",
        [_own_unit(sensor)],
        [_target()],
        5.0,
        transaction=transaction,
        cadence_plan=cadence_plan,
        indexed_rng=handle,
        lod_tiers={identity.observer: FogOfWarLodTier.ACTIVE},
        current_time=15.0,
        current_tick=2,
        detection_culling=False,
    )
    bucket = side_plan.receipt.cadence.native_recoveries_by_period[0]
    assert bucket.recovery_admissions == 1

    indexed.abort_interval(allocation)
    manager.cadence.abort_interval(cadence_plan)
    manager.abort_update_transaction(transaction)

    assert manager.cadence.attachment_states == cadence_before
    assert manager.snapshot_side("blue") == fog_before
    assert manager.intel_fusion.get_state() == fusion_before


def test_admitted_zero_target_sweep_consumes_cadence_without_invented_work() -> None:
    manager = _manager(identification=False)
    sensor = _sensor()

    outcome, record = _run_cycle(
        manager,
        sensor,
        tick=0,
        targets=[],
    )

    receipt = outcome.receipt
    assert receipt.targets == 0
    assert receipt.target_opportunities == 0
    assert receipt.selection.brute_force_cycles == 1
    assert receipt.cadence.admitted == 1
    assert receipt.detection.api_calls == 0
    assert record.entries == ()
    state = manager.cadence.attachment_states[0]
    assert state.native_pending_ready is False
    assert state.lod_pending_ready is False


def test_fusion_outcome_counts_elapsed_prediction_and_update() -> None:
    manager = _manager(identification=False)
    sensor = _sensor()
    first, _first_record = _run_cycle(
        manager,
        sensor,
        tick=0,
        targets=[_target()],
    )
    assert first.receipt.fusion.creations == 1

    second, _second_record = _run_cycle(
        manager,
        sensor,
        tick=1,
        targets=[_target()],
    )

    assert second.receipt.fusion.predictions == 1
    assert second.receipt.fusion.predicted_microseconds == 5_000_000
    assert second.receipt.fusion.updates == 1
    assert second.receipt.fusion.replacements == 0


def test_fusion_receipt_preserves_microsecond_clock_cadence() -> None:
    manager = _manager(identification=False)
    sensor = _sensor()
    first, _first_record = _run_cycle(
        manager,
        sensor,
        tick=0,
        targets=[_target()],
        interval_seconds=1e-6,
        time_origin_seconds=1.0,
    )
    assert first.receipt.fusion.creations == 1

    second, _second_record = _run_cycle(
        manager,
        sensor,
        tick=1,
        targets=[_target()],
        interval_seconds=1e-6,
        time_origin_seconds=1.0,
    )

    assert second.receipt.fusion.predictions == 1
    assert second.receipt.fusion.predicted_microseconds == 1
    assert second.receipt.fusion.updates == 1


def test_unit_and_decoy_use_distinct_exact_indexed_target_kinds() -> None:
    manager = _manager(identification=False)
    sensor = _sensor()
    decoy = Decoy(
        decoy_id="red-decoy",
        position=Position(0.0, 0.0, 0.0),
        deception_type=DeceptionType.DECOY_VISUAL,
        signature=_signature(),
        active=True,
    )

    outcome, record = _run_cycle(
        manager,
        sensor,
        tick=0,
        targets=[_target()],
        decoys=[decoy],
    )

    assert outcome.receipt.detection.stochastic_draws == 2
    expected_preimages = {
        encode_fow_decision(
            FOWDecisionIdentity(
                engine_tick=0,
                reporting_side="blue",
                observer_unit_id="blue-observer",
                source_equipment_index=7,
                sensor_id=sensor.sensor_id,
                modeled_role=SensorModeledRole.VISUAL_OBSERVATION.value,
                target_kind=kind,
                target_id=target_id,
            )
        )
        for kind, target_id in (
            (FOWTargetKind.UNIT, "red-target"),
            (FOWTargetKind.DECOY, "red-decoy"),
        )
    }
    assert {entry.decision_preimage for entry in record.entries} == (expected_preimages)


def test_fog_state_owns_strict_cadence_path_and_round_trips() -> None:
    source = _manager(identification=False)
    sensor = _sensor()
    _outcome, _record = _run_cycle(
        source,
        sensor,
        tick=0,
        targets=[],
    )
    state = source.get_state()

    assert state["cadence"] == source.cadence.get_state()
    assert state["cadence"]["committed_ordinal"] == 1
    target = _manager(seed=118_999, identification=False)
    target.set_state(copy.deepcopy(state))
    assert target.get_state() == state
    assert target.cadence.get_state() == source.cadence.get_state()


def test_fog_checkpoint_persists_scan_integration_and_continues_exactly() -> None:
    source = _manager(identification=False)
    sensor = _sensor()
    _first_outcome, _first_record = _run_cycle(
        source,
        sensor,
        tick=0,
        targets=[_target()],
    )
    state = source.get_state()

    assert list(state["scan_counts"].values()) == [1]
    target = _manager(seed=118_998, identification=False)
    target.set_state(copy.deepcopy(state))

    source_outcome, source_record = _run_cycle(
        source,
        sensor,
        tick=1,
        targets=[_target()],
    )
    target_outcome, target_record = _run_cycle(
        target,
        sensor,
        tick=1,
        targets=[_target()],
    )

    assert target_outcome.world_view.get_state() == source_outcome.world_view.get_state()
    assert target_outcome.receipt == source_outcome.receipt
    assert target_outcome.witnesses == source_outcome.witnesses
    assert target_record == source_record
    assert target.get_state() == source.get_state()
    assert list(target.get_state()["scan_counts"].values()) == [2]


@pytest.mark.parametrize(
    ("scan_counts", "message"),
    [
        ([], "must be a mapping"),
        ({"observer-v1:not-json": 1}, "state key is invalid"),
        ({"sensor:target": True}, "positive integer"),
        ({"sensor:target": 0}, "positive integer"),
        ({"": 1}, "non-empty text"),
    ],
)
def test_fog_checkpoint_rejects_malformed_scan_count_state(
    scan_counts: object,
    message: str,
) -> None:
    manager = _manager(identification=False)
    state = manager.get_state()
    state["scan_counts"] = scan_counts
    before = manager.get_state()

    with pytest.raises(ValueError, match=message):
        manager.stage_state(state)

    assert manager.get_state() == before


def test_fog_checkpoint_rejects_noncanonical_scan_count_state() -> None:
    manager = _manager(identification=False)
    state = manager.get_state()
    state["scan_counts"] = {
        "z-sensor:z-target": 1,
        "a-sensor:a-target": 1,
    }
    with pytest.raises(ValueError, match="not canonically ordered"):
        manager.stage_state(state)

    spaced = 'observer-v1:[ "blue", "blue-observer", 7, "phase118-eye", "red-target" ]'
    state["scan_counts"] = {spaced: 1}
    with pytest.raises(ValueError, match="not canonically encoded"):
        manager.stage_state(state)


@pytest.mark.parametrize("mutation", ["missing", "extra"])
def test_fog_checkpoint_requires_exact_modern_scan_count_topology(
    mutation: str,
) -> None:
    manager = _manager(identification=False)
    state = manager.get_state()
    if mutation == "missing":
        del state["scan_counts"]
    else:
        state["unexpected"] = {}

    with pytest.raises(ValueError, match="invalid topology"):
        manager.stage_state(state)


def test_fog_checkpoint_rejects_detection_scan_mirror_disagreement() -> None:
    source = _manager(identification=False)
    sensor = _sensor()
    _outcome, _record = _run_cycle(
        source,
        sensor,
        tick=0,
        targets=[_target()],
    )
    state = source.get_state()
    target = _manager(identification=False)
    before = target.get_state()

    with pytest.raises(ValueError, match="disagree with DetectionEngine"):
        target.stage_state(
            state,
            authoritative_detection_scan_counts={},
        )

    assert target.get_state() == before
    plan = target.stage_state(
        state,
        authoritative_detection_scan_counts=state["scan_counts"],
    )
    target.commit_state(plan)
    assert target.get_state() == state


def test_fog_restore_rejects_foreign_and_tampered_scan_snapshots_atomically() -> None:
    source = _manager(identification=False)
    sensor = _sensor()
    _outcome, _record = _run_cycle(
        source,
        sensor,
        tick=0,
        targets=[_target()],
    )
    target = _manager(identification=False)
    before = target.get_state()

    foreign_plan = source.stage_state(source.get_state())
    with pytest.raises(ValueError, match="restore plan is foreign"):
        target.commit_state(foreign_plan)
    foreign_scan_counts = source._detection.snapshot_scan_counts()
    with pytest.raises(ValueError, match="belongs to another engine"):
        target._detection.commit_scan_counts(foreign_scan_counts)
    assert target.get_state() == before

    plan = target.stage_state(source.get_state())
    object.__setattr__(plan._scan_counts, "_fingerprint", "tampered")
    with pytest.raises(ValueError, match="snapshot was mutated"):
        target.commit_state(plan)
    assert target.get_state() == before


def test_fog_checkpoint_rejects_active_and_poisoned_cadence_transaction() -> None:
    manager = _manager(identification=False)
    sensor = _sensor()
    transaction, plan, _indexed, _allocation, _handle, _identity_value = _begin_cycle(
        manager,
        sensor,
        tick=0,
    )

    with pytest.raises(RuntimeError, match="active update transaction"):
        manager.get_state()
    manager.abort_update_transaction(transaction)
    manager.cadence.abort_interval(plan)
    with pytest.raises(RuntimeError, match="poisoned update transaction"):
        manager.get_state()


def _run_two_side_transaction(
    *,
    parallel: bool,
) -> tuple[dict[str, object], object, tuple[object, ...], tuple[object, ...]]:
    manager = _manager(identification=False)
    sensor = _sensor()
    transaction = manager.begin_update_transaction(("blue", "red"))
    identities = {
        "blue": _attachment_identity(sensor),
        "red": _attachment_identity(
            sensor,
            unit_id="red-observer",
            side="red",
        ),
    }
    cadence_plan = manager.cadence.stage_interval(
        [
            TacticalCadenceAttachment(
                identity=identities[side],
                native_period=1,
                lod_period=1,
                operational=True,
            )
            for side in ("blue", "red")
        ]
    )
    indexed = IndexedFOWRNG(118_700)
    allocation = indexed.begin_interval(
        module=ModuleId.DETECTION,
        engine_tick=0,
        reporting_sides=("blue", "red"),
    )
    handles = {side: allocation.acquire_side(side) for side in ("blue", "red")}
    side_inputs = {
        "blue": (
            [_own_unit(sensor)],
            [_target()],
        ),
        "red": (
            [_own_unit(sensor, unit_id="red-observer")],
            [_target("blue-target")],
        ),
    }

    def stage(side: str) -> object:
        own_units, enemy_units = side_inputs[side]
        return manager.update_with_receipt(
            side,
            own_units,
            enemy_units,
            5.0,
            transaction=transaction,
            cadence_plan=cadence_plan,
            indexed_rng=handles[side],
            lod_tiers={
                identities[side].observer: FogOfWarLodTier.ACTIVE,
            },
            current_time=5.0,
            current_tick=0,
            detection_culling=False,
        )

    if parallel:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {side: executor.submit(stage, side) for side in ("blue", "red")}
            plans = {side: futures[side].result() for side in ("blue", "red")}
    else:
        plans = {side: stage(side) for side in ("blue", "red")}

    for side, plan in plans.items():
        assert plan._fusion_delta.reporting_side == side
        assert all(track.side == side for track in plan._fusion_delta.tracks.values())
        assert all(
            entry.scan_identity is not None and entry.scan_identity.side == side for entry in plan._scan_count_entries
        )

    publication = manager.prevalidate_update_transaction(
        transaction,
        tuple(plans[side] for side in ("blue", "red")),
    )
    record = indexed.commit_interval(allocation)
    manager.cadence.commit_interval(cadence_plan)
    manager.commit_update_transaction(publication)
    return (
        manager.get_state(),
        record,
        tuple(plans[side].receipt for side in ("blue", "red")),
        tuple(manager.snapshot_side(side) for side in ("blue", "red")),
    )


def test_side_plans_are_isolated_and_serial_threaded_publication_is_exact() -> None:
    sequential = _run_two_side_transaction(parallel=False)
    threaded = _run_two_side_transaction(parallel=True)

    assert threaded == sequential


def test_side_staging_never_copies_or_mutates_foreign_side_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, _record, _receipts, _snapshots = _run_two_side_transaction(
        parallel=False,
    )
    manager = _manager(seed=118_702, identification=False)
    manager.set_state(copy.deepcopy(state))
    sensor = _sensor()
    transaction = manager.begin_update_transaction(("blue", "red"))
    red_world_view = transaction._world_views["red"]
    red_tracks = transaction._intel_fusion["tracks"]["red"]
    assert red_tracks
    red_world_view_state = red_world_view.get_state()
    red_track_states = {track_id: track.get_state() for track_id, track in red_tracks.items()}
    identities = {
        "blue": _attachment_identity(sensor),
        "red": _attachment_identity(
            sensor,
            unit_id="red-observer",
            side="red",
        ),
    }
    cadence_plan = manager.cadence.stage_interval(
        [
            TacticalCadenceAttachment(
                identity=identities[side],
                native_period=1,
                lod_period=1,
                operational=True,
            )
            for side in ("blue", "red")
        ]
    )
    indexed = IndexedFOWRNG(118_702)
    allocation = indexed.begin_interval(
        module=ModuleId.DETECTION,
        engine_tick=1,
        reporting_sides=("blue", "red"),
    )
    handle = allocation.acquire_side("blue")
    original_deepcopy = copy.deepcopy
    copied_object_ids: set[int] = set()

    def observed_deepcopy(value: object, *args: object, **kwargs: object) -> object:
        copied_object_ids.add(id(value))
        return original_deepcopy(value, *args, **kwargs)

    monkeypatch.setattr(fog_of_war_module.copy, "deepcopy", observed_deepcopy)
    side_plan = manager.update_with_receipt(
        "blue",
        [_own_unit(sensor)],
        [_target()],
        5.0,
        transaction=transaction,
        cadence_plan=cadence_plan,
        indexed_rng=handle,
        lod_tiers={identities["blue"].observer: FogOfWarLodTier.ACTIVE},
        current_time=10.0,
        current_tick=1,
        detection_culling=False,
    )

    assert side_plan._fusion_delta.tracks is not red_tracks
    assert not set(map(id, side_plan._fusion_delta.tracks.values())).intersection(
        map(id, red_tracks.values()),
    )
    assert all(track.side == "blue" for track in side_plan._fusion_delta.tracks.values())
    assert id(transaction._world_views) not in copied_object_ids
    assert id(transaction._intel_fusion) not in copied_object_ids
    assert id(red_world_view) not in copied_object_ids
    assert not copied_object_ids.intersection(map(id, red_tracks.values()))
    assert red_world_view.get_state() == red_world_view_state
    assert {track_id: track.get_state() for track_id, track in red_tracks.items()} == red_track_states
    assert manager.snapshot_side("red").identities == _snapshots[1].identities

    indexed.abort_interval(allocation)
    manager.cadence.abort_interval(cadence_plan)
    manager.abort_update_transaction(transaction)


def test_committed_fog_payload_does_not_alias_retained_public_plan() -> None:
    manager = _manager(identification=False)
    sensor = _sensor()
    transaction, cadence, indexed, allocation, handle, identity = _begin_cycle(
        manager,
        sensor,
        tick=0,
    )
    side_plan = manager.update_with_receipt(
        "blue",
        [_own_unit(sensor)],
        [_target()],
        5.0,
        transaction=transaction,
        cadence_plan=cadence,
        indexed_rng=handle,
        lod_tiers={identity.observer: FogOfWarLodTier.ACTIVE},
        current_time=5.0,
        current_tick=0,
        detection_culling=False,
    )
    publication = manager.prevalidate_update_transaction(
        transaction,
        (side_plan,),
    )
    prepared = manager.prepare_update_commit(publication)
    indexed.commit_interval(allocation)
    manager.cadence.commit_interval(cadence)
    manager.commit_prepared_update(prepared)
    committed = manager.get_state()

    publication._world_views.clear()
    publication._current_detection_witnesses.clear()
    object.__setattr__(publication, "_observer_track_supports", [])
    publication._intel_fusion["tracks"].clear()

    assert manager.get_state() == committed
    assert indexed.committed_interval_count == 1


def test_later_side_failure_leaves_public_fog_and_fusion_unpublished() -> None:
    manager = _manager(identification=False)
    sensor = _sensor()
    before_fog = manager.get_state()
    before_fusion = manager.intel_fusion.get_state()
    before_snapshots = tuple(manager.snapshot_side(side) for side in ("blue", "red"))
    transaction = manager.begin_update_transaction(("blue", "red"))
    identities = {
        "blue": _attachment_identity(sensor),
        "red": _attachment_identity(
            sensor,
            unit_id="red-observer",
            side="red",
        ),
    }
    cadence_plan = manager.cadence.stage_interval(
        [
            TacticalCadenceAttachment(
                identity=identities[side],
                native_period=1,
                lod_period=1,
                operational=True,
            )
            for side in ("blue", "red")
        ]
    )
    indexed = IndexedFOWRNG(118_701)
    allocation = indexed.begin_interval(
        module=ModuleId.DETECTION,
        engine_tick=0,
        reporting_sides=("blue", "red"),
    )
    blue_handle = allocation.acquire_side("blue")
    red_handle = allocation.acquire_side("red")
    blue_plan = manager.update_with_receipt(
        "blue",
        [_own_unit(sensor)],
        [_target()],
        5.0,
        transaction=transaction,
        cadence_plan=cadence_plan,
        indexed_rng=blue_handle,
        lod_tiers={identities["blue"].observer: FogOfWarLodTier.ACTIVE},
        current_time=5.0,
        current_tick=0,
        detection_culling=False,
    )
    assert blue_plan.outcome.witnesses
    assert manager.snapshot_side("blue").present is False
    assert manager.get_current_detection_witnesses("blue") == ()
    assert manager.intel_fusion.get_state() == before_fusion

    with pytest.raises(ValueError, match="duplicate ID"):
        manager.update_with_receipt(
            "red",
            [_own_unit(sensor, unit_id="red-observer")],
            [_target("duplicate"), _target("duplicate")],
            5.0,
            transaction=transaction,
            cadence_plan=cadence_plan,
            indexed_rng=red_handle,
            lod_tiers={
                identities["red"].observer: FogOfWarLodTier.ACTIVE,
            },
            current_time=5.0,
            current_tick=0,
            detection_culling=False,
        )
    indexed.abort_interval(allocation)
    manager.cadence.abort_interval(cadence_plan)

    assert tuple(manager.snapshot_side(side) for side in ("blue", "red")) == before_snapshots
    assert manager.intel_fusion.get_state() == before_fusion
    with pytest.raises(RuntimeError, match="poisoned update transaction"):
        manager.get_state()
    assert before_fog["world_views"] == {}


def test_soa_selection_receipts_the_actual_side_vector_build() -> None:
    manager = _manager(identification=False)
    outcome, _record = _run_cycle(
        manager,
        _sensor(),
        tick=0,
        targets=[_target()],
        soa_selection=True,
    )

    assert outcome.receipt.selection.soa_vector_builds == 1
    assert outcome.receipt.selection.soa_vector_queries == 1
    assert outcome.receipt.selection.soa_vector_admitted_targets == 1
    assert outcome.receipt.selection.brute_force_cycles == 0


def test_snapshot_side_is_immutable_ordered_and_non_creating() -> None:
    manager = _manager(identification=False)
    before = manager.get_state()

    absent = manager.snapshot_side("blue")

    assert absent.reporting_side == "blue"
    assert absent.present is False
    assert absent.identities == ()
    assert manager.get_state() == before

    outcome, _record = _run_cycle(
        manager,
        _sensor(),
        tick=0,
        targets=[_target("z-target"), _target("a-target")],
    )
    snapshot = manager.snapshot_side("blue")
    assert outcome.witnesses == manager.get_current_detection_witnesses("blue")
    assert tuple(identity.target_id for identity in snapshot.identities) == (
        "a-target",
        "z-target",
    )


def test_legacy_fog_restore_rejects_mixed_modern_cadence_state() -> None:
    manager = _manager(identification=False)
    modern = manager.get_state()

    with pytest.raises(ValueError, match="cannot supply modern cadence"):
        manager.stage_state(modern, allow_legacy_state=True)


def test_legacy_fog_restore_rejects_mixed_modern_scan_count_state() -> None:
    manager = _manager(identification=False)
    mixed = manager.get_state()
    del mixed["cadence"]

    with pytest.raises(ValueError, match="invalid topology"):
        manager.stage_state(mixed, allow_legacy_state=True)


def test_legacy_four_key_fog_restore_preserves_contacts_tracks_and_witnesses() -> None:
    source = _manager(identification=False)
    sensor = _sensor()
    _outcome, _record = _run_cycle(
        source,
        sensor,
        tick=0,
        targets=[_target()],
    )
    source_state = source.get_state()
    legacy_state = copy.deepcopy(source_state)
    del legacy_state["cadence"]
    del legacy_state["scan_counts"]
    del legacy_state["observer_track_supports"]
    target = _manager(
        identification=False,
        complete_from_tick_zero=False,
    )
    binding = FogOfWarSensorBinding(
        unit_id="blue-observer",
        side="blue",
        source_equipment_index=7,
        sensor_id=sensor.sensor_id,
        modeled_role=SensorModeledRole.VISUAL_OBSERVATION.value,
        sensor_type=sensor.sensor_type.name,
    )

    plan = target.stage_state(
        legacy_state,
        expected_sides={"blue"},
        expected_target_sides={
            "blue-observer": "blue",
            "red-target": "red",
        },
        expected_sensor_bindings=(binding,),
        allow_legacy_state=True,
    )
    target.commit_state(plan)
    restored = target.get_state()

    assert restored["world_views"] == source_state["world_views"]
    assert restored["current_detection_witnesses"] == source_state["current_detection_witnesses"]
    assert restored["intel_fusion"] == source_state["intel_fusion"]
    assert restored["scan_counts"] == {}
    assert (
        restored["cadence"]
        == TacticalCadenceScheduler(
            complete_from_tick_zero=False,
        ).get_state()
    )


def test_cadence_completeness_promotion_rejects_during_fog_stage() -> None:
    source = _manager(identification=False)
    target = _manager(
        identification=False,
        complete_from_tick_zero=False,
    )
    state = source.get_state()
    before_fusion = target.intel_fusion.get_state()

    with pytest.raises(ValueError, match="completeness cannot be promoted"):
        target.stage_state(state)

    assert target.intel_fusion.get_state() == before_fusion
    assert target.snapshot_side("blue").present is False


def test_cadence_restore_binding_requires_exact_runtime_roster_and_periods() -> None:
    manager = _manager(identification=False)
    sensor = _sensor()
    _outcome, _record = _run_cycle(
        manager,
        sensor,
        tick=0,
        targets=[],
    )
    sensor_binding = FogOfWarSensorBinding(
        unit_id="blue-observer",
        side="blue",
        source_equipment_index=7,
        sensor_id=sensor.sensor_id,
        modeled_role=SensorModeledRole.VISUAL_OBSERVATION.value,
        sensor_type=sensor.sensor_type.name,
    )
    cadence_binding = FogOfWarCadenceBinding(
        identity=sensor_binding.cadence_identity,
        native_period=1,
        current_lod_period=1,
    )
    unused_roster_binding = FogOfWarSensorBinding(
        unit_id="blue-unused",
        side="blue",
        source_equipment_index=8,
        sensor_id=sensor.sensor_id,
        modeled_role=SensorModeledRole.VISUAL_OBSERVATION.value,
        sensor_type=sensor.sensor_type.name,
    )
    full_sensor_bindings = (sensor_binding, unused_roster_binding)
    native_phase_bindings = tuple(
        FogOfWarNativePhaseBinding(
            identity=binding.cadence_identity,
            native_period=1,
        )
        for binding in full_sensor_bindings
    )
    plan = manager.stage_state(
        manager.get_state(),
        expected_sides={"blue"},
        expected_target_sides={
            "blue-observer": "blue",
            "blue-unused": "blue",
        },
        expected_sensor_bindings=full_sensor_bindings,
        expected_cadence_sensor_bindings=(sensor_binding,),
        expected_cadence_bindings=(cadence_binding,),
        expected_native_phase_bindings=native_phase_bindings,
    )
    manager.validate_cadence_restore_bindings(
        plan,
        expected_sensor_bindings=full_sensor_bindings,
        expected_cadence_sensor_bindings=(sensor_binding,),
        expected_cadence_bindings=(cadence_binding,),
        expected_native_phase_bindings=native_phase_bindings,
    )

    wrong_lod = FogOfWarCadenceBinding(
        identity=sensor_binding.cadence_identity,
        native_period=1,
        current_lod_period=5,
    )
    with pytest.raises(ValueError, match="LOD cadence period"):
        manager.validate_cadence_restore_bindings(
            plan,
            expected_sensor_bindings=full_sensor_bindings,
            expected_cadence_sensor_bindings=(sensor_binding,),
            expected_cadence_bindings=(wrong_lod,),
            expected_native_phase_bindings=native_phase_bindings,
        )

    wrong_native_period = (
        FogOfWarNativePhaseBinding(
            identity=sensor_binding.cadence_identity,
            native_period=2,
        ),
        native_phase_bindings[1],
    )
    with pytest.raises(
        ValueError,
        match="native phase period disagrees",
    ):
        manager.validate_cadence_restore_bindings(
            plan,
            expected_sensor_bindings=full_sensor_bindings,
            expected_cadence_sensor_bindings=(sensor_binding,),
            expected_cadence_bindings=(cadence_binding,),
            expected_native_phase_bindings=wrong_native_period,
        )

    with pytest.raises(ValueError, match="complete runtime sensor roster"):
        manager.validate_cadence_restore_bindings(
            plan,
            expected_sensor_bindings=full_sensor_bindings,
            expected_cadence_sensor_bindings=(sensor_binding,),
            expected_cadence_bindings=(cadence_binding,),
            expected_native_phase_bindings=(native_phase_bindings[0],),
        )
