"""Focused owner-bound observer-track-support tests for Phase 118."""

from __future__ import annotations

import copy
from types import SimpleNamespace

import numpy as np
import pytest

from stochastic_warfare.core.indexed_rng import IndexedFOWRNG
from stochastic_warfare.core.types import Domain, ModuleId, Position
from stochastic_warfare.detection.cadence import (
    TacticalAttachmentIdentity,
    TacticalCadenceAttachment,
    TacticalCadenceScheduler,
    TacticalObserverIdentity,
)
from stochastic_warfare.detection.deception import DeceptionEngine
from stochastic_warfare.detection.detection import DetectionEngine
from stochastic_warfare.detection.estimation import StateEstimator
from stochastic_warfare.detection.estimation import TrackStatus
from stochastic_warfare.detection.fog_of_war import (
    FogOfWarLodTier,
    FogOfWarManager,
    FogOfWarSensorBinding,
)
from stochastic_warfare.detection.intel_fusion import IntelFusionEngine
from stochastic_warfare.detection.sensors import SensorDefinition, SensorInstance
from stochastic_warfare.detection.signatures import RadarSignature, SignatureProfile
from stochastic_warfare.simulation.loadouts import SensorModeledRole


def _manager(seed: int = 118_700) -> FogOfWarManager:
    rng = np.random.Generator(np.random.PCG64(seed))
    estimator = StateEstimator(rng=rng)
    return FogOfWarManager(
        detection_engine=DetectionEngine(rng=rng),
        state_estimator=estimator,
        intel_fusion=IntelFusionEngine(state_estimator=estimator, rng=rng),
        deception_engine=DeceptionEngine(rng=rng),
        rng=rng,
        cadence_scheduler=TacticalCadenceScheduler(),
    )


def _radar(
    *,
    sensor_id: str = "phase118-support-radar",
    maximum_range_m: float = 20_000.0,
) -> SensorInstance:
    equipment = SimpleNamespace(operational=True, condition=1.0)
    return SensorInstance(
        SensorDefinition(
            sensor_id=sensor_id,
            sensor_type="RADAR",
            display_name="Phase 118 Support Radar",
            max_range_m=maximum_range_m,
            min_range_m=0.0,
            detection_threshold=-100.0,
            scan_interval_ticks=2,
            requires_los=False,
            target_domains=["AERIAL"],
            frequency_mhz=3_000.0,
            peak_power_w=1_000_000.0,
            antenna_gain_dbi=35.0,
        ),
        equipment=equipment,
    )


def _identity(
    sensor: SensorInstance,
    *,
    source_equipment_index: int = 7,
) -> TacticalAttachmentIdentity:
    return TacticalAttachmentIdentity(
        reporting_side="blue",
        observer_unit_id="blue-observer",
        source_equipment_index=source_equipment_index,
        sensor_id=sensor.sensor_id,
        modeled_role=SensorModeledRole.FIRE_CONTROL_RADAR.value,
    )


def _attachment(
    sensor: SensorInstance,
    *,
    source_equipment_index: int = 7,
) -> SimpleNamespace:
    return SimpleNamespace(
        sensor=sensor,
        source_equipment_index=source_equipment_index,
        sensor_id=sensor.sensor_id,
        modeled_role=SensorModeledRole.FIRE_CONTROL_RADAR,
    )


def _own_unit(
    attachments: tuple[SimpleNamespace, ...],
) -> dict[str, object]:
    return {
        "unit_id": "blue-observer",
        "position": Position(0.0, 0.0, 0.0),
        "sensors": [attachment.sensor for attachment in attachments],
        "sensor_attachments": list(attachments),
        "observer_height": 1.8,
        "observer_heading_deg": 0.0,
    }


def _target(
    *,
    position: Position = Position(1_000.0, 0.0, 0.0),
) -> dict[str, object]:
    return {
        "unit_id": "red-target",
        "position": position,
        "signature": SignatureProfile(
            profile_id="phase118-support-target",
            unit_type="aircraft",
            radar=RadarSignature(
                rcs_frontal_m2=1_000.0,
                rcs_side_m2=1_000.0,
                rcs_rear_m2=1_000.0,
            ),
        ),
        "unit": SimpleNamespace(domain=Domain.AERIAL),
        "target_height": 1_000.0,
        "concealment": 0.0,
        "posture": 0,
    }


def _cycle(
    manager: FogOfWarManager,
    attachments: tuple[SimpleNamespace, ...],
    *,
    tick: int,
    targets: list[dict[str, object]],
    native_periods: tuple[int, ...],
    lod_periods: tuple[int, ...] | None = None,
    commit: bool = True,
) -> tuple[object, object, object, object]:
    if lod_periods is None:
        lod_periods = tuple(1 for _ in attachments)
    identities = tuple(
        _identity(
            attachment.sensor,
            source_equipment_index=attachment.source_equipment_index,
        )
        for attachment in attachments
    )
    transaction = manager.begin_update_transaction(("blue",))
    cadence_plan = manager.cadence.stage_interval(
        tuple(
            TacticalCadenceAttachment(
                identity=identity,
                native_period=native_period,
                lod_period=lod_period,
                operational=attachment.sensor.operational,
            )
            for identity, attachment, native_period, lod_period in zip(
                identities,
                attachments,
                native_periods,
                lod_periods,
                strict=True,
            )
        ),
    )
    indexed = IndexedFOWRNG(118_701)
    allocation = indexed.begin_interval(
        module=ModuleId.DETECTION,
        engine_tick=tick,
        reporting_sides=("blue",),
    )
    side_plan = manager.update_with_receipt(
        "blue",
        [_own_unit(attachments)],
        targets,
        5.0,
        transaction=transaction,
        cadence_plan=cadence_plan,
        indexed_rng=allocation.acquire_side("blue"),
        lod_tiers={
            TacticalObserverIdentity(
                reporting_side="blue",
                observer_unit_id="blue-observer",
            ): FogOfWarLodTier.ACTIVE,
        },
        current_time=(tick + 1) * 5.0,
        current_tick=tick,
        detection_culling=False,
    )
    if not commit:
        return transaction, cadence_plan, allocation, side_plan
    publication = manager.prevalidate_update_transaction(
        transaction,
        (side_plan,),
    )
    record = indexed.commit_interval(allocation)
    manager.cadence.commit_interval(cadence_plan)
    manager.commit_update_transaction(publication)
    return side_plan.outcome, record, cadence_plan, publication


def test_success_creates_exact_support_and_native_deferral_reuses_without_rng() -> None:
    manager = _manager()
    sensor = _radar()
    attachment = _attachment(sensor)

    first, first_record, _, _ = _cycle(
        manager,
        (attachment,),
        tick=0,
        targets=[_target()],
        native_periods=(2,),
    )
    support = first.observer_track_supports[0]
    assert len(first_record.entries) == 1
    assert support.observation_ordinal == 0
    assert support.native_due_ordinal == 2
    assert support.position_m == pytest.approx((1_000.0, 0.0))
    assert support.velocity_mps == (0.0, 0.0)
    assert support.covariance[2][2] == support.covariance[3][3] == 100.0
    conventional_rng = copy.deepcopy(manager._rng.bit_generator.state)

    deferred, deferred_record, _, _ = _cycle(
        manager,
        (attachment,),
        tick=1,
        targets=[_target()],
        native_periods=(2,),
    )

    assert deferred.observer_track_supports == (support,)
    assert deferred.witnesses == ()
    assert deferred.receipt.cadence.deferred_native == 1
    assert deferred.receipt.detection.api_calls == 0
    assert deferred_record.entries == ()
    assert manager._rng.bit_generator.state == conventional_rng


@pytest.mark.parametrize("failure", ["stochastic_miss", "pre_rng"])
def test_native_due_failure_expires_support(
    failure: str,
) -> None:
    manager = _manager()
    sensor = _radar()
    attachment = _attachment(sensor)
    _cycle(
        manager,
        (attachment,),
        tick=0,
        targets=[_target()],
        native_periods=(2,),
    )
    _cycle(
        manager,
        (attachment,),
        tick=1,
        targets=[_target()],
        native_periods=(2,),
    )
    if failure == "stochastic_miss":
        sensor.definition.detection_threshold = 1_000.0
        target = _target()
    else:
        target = _target(position=Position(30_000.0, 0.0, 0.0))

    outcome, record, _, _ = _cycle(
        manager,
        (attachment,),
        tick=2,
        targets=[target],
        native_periods=(2,),
    )

    assert outcome.observer_track_supports == ()
    assert manager.get_observer_track_supports("blue") == ()
    assert outcome.receipt.detection.successes == 0
    assert len(record.entries) == (1 if failure == "stochastic_miss" else 0)


@pytest.mark.parametrize("termination", ["offline", "attachment", "target"])
def test_support_expires_when_exact_operational_binding_is_not_native_deferred(
    termination: str,
) -> None:
    manager = _manager()
    sensor = _radar()
    attachment = _attachment(sensor)
    _cycle(
        manager,
        (attachment,),
        tick=0,
        targets=[_target()],
        native_periods=(2,),
    )
    attachments = (attachment,)
    targets = [_target()]
    if termination == "offline":
        sensor.equipment.operational = False
    elif termination == "attachment":
        attachments = ()
    elif termination == "target":
        targets = []

    outcome, _, _, _ = _cycle(
        manager,
        attachments,
        tick=1,
        targets=targets,
        native_periods=tuple(2 for _ in attachments),
        lod_periods=tuple(1 for _ in attachments),
    )

    assert outcome.observer_track_supports == ()
    assert manager.get_observer_track_supports("blue") == ()


def test_native_and_lod_deferral_retains_exact_support_without_rng() -> None:
    manager = _manager()
    sensor = _radar()
    attachment = _attachment(sensor)
    first, _, _, _ = _cycle(
        manager,
        (attachment,),
        tick=0,
        targets=[_target()],
        native_periods=(2,),
    )
    support = first.observer_track_supports[0]

    outcome, record, cadence_plan, _ = _cycle(
        manager,
        (attachment,),
        tick=1,
        targets=[_target()],
        native_periods=(2,),
        lod_periods=(3,),
    )

    decision = cadence_plan.decision_for(_identity(sensor))
    assert decision.disposition.value == "deferred_both"
    assert outcome.observer_track_supports == (support,)
    assert outcome.witnesses == ()
    assert outcome.receipt.detection.api_calls == 0
    assert record.entries == ()


def test_track_replacement_expires_deferred_attachment_support() -> None:
    manager = _manager()
    deferred_sensor = _radar(sensor_id="phase118-deferred-radar")
    full_rate_sensor = _radar(sensor_id="phase118-full-rate-radar")
    attachments = (
        _attachment(deferred_sensor, source_equipment_index=7),
        _attachment(full_rate_sensor, source_equipment_index=8),
    )
    first, _, _, _ = _cycle(
        manager,
        attachments,
        tick=0,
        targets=[_target()],
        native_periods=(2, 1),
    )
    assert len(first.observer_track_supports) == 1
    original_track_id = first.observer_track_supports[0].fusion_track_id

    second, _, _, _ = _cycle(
        manager,
        attachments,
        tick=1,
        targets=[_target(position=Position(10_000.0, 0.0, 0.0))],
        native_periods=(2, 1),
    )

    assert second.receipt.fusion.replacements == 1
    assert all(support.fusion_track_id != original_track_id for support in second.observer_track_supports)
    assert second.observer_track_supports == ()


def test_lod_only_deferral_at_native_due_expires_support_without_scan() -> None:
    manager = _manager()
    sensor = _radar()
    attachment = _attachment(sensor)
    _cycle(
        manager,
        (attachment,),
        tick=0,
        targets=[_target()],
        native_periods=(2,),
    )
    identity = _identity(sensor)
    skipped_fow_plan = manager.cadence.stage_interval(
        (
            TacticalCadenceAttachment(
                identity=identity,
                native_period=2,
                lod_period=3,
                operational=True,
            ),
        )
    )
    manager.cadence.commit_interval(skipped_fow_plan)

    outcome, record, cadence_plan, _ = _cycle(
        manager,
        (attachment,),
        tick=2,
        targets=[_target()],
        native_periods=(2,),
        lod_periods=(3,),
    )

    decision = cadence_plan.decision_for(identity)
    assert decision.native_ready is True
    assert decision.lod_ready is False
    assert decision.disposition.value == "deferred_lod"
    assert outcome.observer_track_supports == ()
    assert outcome.receipt.detection.api_calls == 0
    assert record.entries == ()


def test_lost_track_expires_support_and_contact_generation() -> None:
    manager = _manager()
    sensor = _radar()
    attachment = _attachment(sensor)
    _cycle(
        manager,
        (attachment,),
        tick=0,
        targets=[_target()],
        native_periods=(2,),
    )
    contact = manager.get_contact("blue", "red-target")
    assert contact is not None
    contact.track.status = TrackStatus.LOST

    outcome, _, _, _ = _cycle(
        manager,
        (attachment,),
        tick=1,
        targets=[_target()],
        native_periods=(2,),
    )

    assert outcome.observer_track_supports == ()
    assert "red-target" not in outcome.world_view.contacts


def test_same_sensor_id_different_equipment_indexes_do_not_overwrite_support() -> None:
    manager = _manager()
    sensor = _radar()
    attachments = (
        _attachment(sensor, source_equipment_index=7),
        _attachment(sensor, source_equipment_index=8),
    )

    outcome, _, _, _ = _cycle(
        manager,
        attachments,
        tick=0,
        targets=[_target()],
        native_periods=(2, 2),
    )

    assert tuple(
        support.identity.attachment_identity.source_equipment_index for support in outcome.observer_track_supports
    ) == (7, 8)


def test_aborted_side_plan_does_not_publish_support() -> None:
    manager = _manager()
    sensor = _radar()
    transaction, cadence_plan, allocation, side_plan = _cycle(
        manager,
        (_attachment(sensor),),
        tick=0,
        targets=[_target()],
        native_periods=(2,),
        commit=False,
    )
    assert side_plan.outcome.observer_track_supports

    manager.abort_update_transaction(transaction)
    manager.cadence.abort_interval(cadence_plan)
    allocation.abort()

    assert manager.get_observer_track_supports("blue") == ()


def test_transaction_and_publication_support_structure_mutation_rejects() -> None:
    primed = _manager()
    sensor = _radar()
    _cycle(
        primed,
        (_attachment(sensor),),
        tick=0,
        targets=[_target()],
        native_periods=(2,),
    )
    retained = primed.get_observer_track_supports("blue")
    snapshot = primed.snapshot_side("blue")
    fusion = primed.intel_fusion.get_state()
    transaction = primed.begin_update_transaction(("blue",))
    object.__setattr__(
        transaction,
        "_observer_track_supports",
        list(transaction._observer_track_supports),
    )

    with pytest.raises(ValueError, match="exact ObserverTrackSupportState tuple"):
        primed.prevalidate_update_transaction(transaction, ())
    assert primed.get_observer_track_supports("blue") == retained
    assert primed.snapshot_side("blue") == snapshot
    assert primed.intel_fusion.get_state() == fusion
    primed.abort_update_transaction(transaction)

    candidate = _manager(seed=118_705)
    transaction, cadence_plan, allocation, side_plan = _cycle(
        candidate,
        (_attachment(_radar()),),
        tick=0,
        targets=[_target()],
        native_periods=(2,),
        commit=False,
    )
    publication = candidate.prevalidate_update_transaction(
        transaction,
        (side_plan,),
    )
    object.__setattr__(
        publication,
        "_observer_track_supports",
        list(publication._observer_track_supports),
    )

    with pytest.raises(ValueError, match="exact ObserverTrackSupportState tuple"):
        candidate.prepare_update_commit(publication)
    assert candidate.snapshot_side("blue").present is False
    assert candidate.get_observer_track_supports() == ()
    allocation.abort()
    candidate.cadence.abort_interval(cadence_plan)
    candidate.abort_update_transaction(transaction)

    valid = _manager(seed=118_706)
    outcome, _, _, _ = _cycle(
        valid,
        (_attachment(_radar()),),
        tick=0,
        targets=[_target()],
        native_periods=(2,),
    )
    assert outcome.observer_track_supports


def test_support_checkpoint_restores_fresh_and_in_place_and_retries_after_corruption() -> None:
    source = _manager()
    sensor = _radar()
    attachment = _attachment(sensor)
    _cycle(
        source,
        (attachment,),
        tick=0,
        targets=[_target()],
        native_periods=(2,),
    )
    state = source.get_state()
    binding = FogOfWarSensorBinding(
        unit_id="blue-observer",
        side="blue",
        source_equipment_index=7,
        sensor_id=sensor.sensor_id,
        modeled_role=SensorModeledRole.FIRE_CONTROL_RADAR.value,
        sensor_type="RADAR",
    )
    target = _manager(seed=118_702)
    before = target.get_state()
    corrupt = copy.deepcopy(state)
    corrupt["observer_track_supports"][0]["native_due_ordinal"] = 3

    with pytest.raises(ValueError, match="observer track support"):
        target.stage_state(
            corrupt,
            expected_sides={"blue"},
            expected_target_sides={
                "blue-observer": "blue",
                "red-target": "red",
            },
            expected_sensor_bindings=(binding,),
            checkpoint_elapsed_s=5.0,
        )
    assert target.get_state() == before

    plan = target.stage_state(
        state,
        expected_sides={"blue"},
        expected_target_sides={
            "blue-observer": "blue",
            "red-target": "red",
        },
        expected_sensor_bindings=(binding,),
        checkpoint_elapsed_s=5.0,
    )
    target.commit_state(plan)
    assert target.get_state() == state
    source.commit_state(source.stage_state(copy.deepcopy(state)))
    assert source.get_state() == state


def test_support_restore_plan_collection_mutation_rejects_and_retries() -> None:
    source = _manager()
    sensor = _radar()
    _cycle(
        source,
        (_attachment(sensor),),
        tick=0,
        targets=[_target()],
        native_periods=(2,),
    )
    state = source.get_state()
    binding = FogOfWarSensorBinding(
        unit_id="blue-observer",
        side="blue",
        source_equipment_index=7,
        sensor_id=sensor.sensor_id,
        modeled_role=SensorModeledRole.FIRE_CONTROL_RADAR.value,
        sensor_type="RADAR",
    )
    target = _manager(seed=118_704)
    before = target.get_state()
    plan = target.stage_state(
        state,
        expected_sides={"blue"},
        expected_target_sides={
            "blue-observer": "blue",
            "red-target": "red",
        },
        expected_sensor_bindings=(binding,),
        checkpoint_elapsed_s=5.0,
    )
    object.__setattr__(
        plan,
        "_observer_track_supports",
        list(plan._observer_track_supports),
    )

    with pytest.raises(ValueError, match="foreign or was mutated"):
        target.commit_state(plan)
    assert target.get_state() == before

    target.commit_state(
        target.stage_state(
            state,
            expected_sides={"blue"},
            expected_target_sides={
                "blue-observer": "blue",
                "red-target": "red",
            },
            expected_sensor_bindings=(binding,),
            checkpoint_elapsed_s=5.0,
        ),
    )
    assert target.get_state() == state


@pytest.mark.parametrize(
    "corruption",
    ("duplicate", "track", "covariance", "friendly"),
)
def test_support_checkpoint_corruption_is_rejected_before_mutation(
    corruption: str,
) -> None:
    source = _manager()
    sensor = _radar()
    _cycle(
        source,
        (_attachment(sensor),),
        tick=0,
        targets=[_target()],
        native_periods=(2,),
    )
    state = source.get_state()
    invalid = copy.deepcopy(state)
    expected_target_sides = {
        "blue-observer": "blue",
        "red-target": "red",
    }
    if corruption == "duplicate":
        invalid["observer_track_supports"].append(
            copy.deepcopy(invalid["observer_track_supports"][0]),
        )
    elif corruption == "track":
        invalid["observer_track_supports"][0]["fusion_track_id"] = "fow-track-9999"
    elif corruption == "covariance":
        invalid["observer_track_supports"][0]["covariance"][0][0] = -1.0
    else:
        expected_target_sides["red-target"] = "blue"
    target = _manager(seed=118_703)
    before = target.get_state()
    binding = FogOfWarSensorBinding(
        unit_id="blue-observer",
        side="blue",
        source_equipment_index=7,
        sensor_id=sensor.sensor_id,
        modeled_role=SensorModeledRole.FIRE_CONTROL_RADAR.value,
        sensor_type="RADAR",
    )

    with pytest.raises(ValueError):
        target.stage_state(
            invalid,
            expected_sides={"blue"},
            expected_target_sides=expected_target_sides,
            expected_sensor_bindings=(binding,),
            checkpoint_elapsed_s=5.0,
        )

    assert target.get_state() == before


def test_disabled_fow_clear_atomically_removes_witness_and_support() -> None:
    manager = _manager()
    sensor = _radar()
    _cycle(
        manager,
        (_attachment(sensor),),
        tick=0,
        targets=[_target()],
        native_periods=(2,),
    )
    assert manager.get_current_detection_witnesses("blue")
    assert manager.get_observer_track_supports("blue")

    plan = manager.prepare_witness_clear()
    manager.commit_prepared_witness_clear(plan)

    assert manager.get_current_detection_witnesses() == ()
    assert manager.get_observer_track_supports() == ()


def test_disabled_fow_clear_support_structure_mutation_rejects_and_retries() -> None:
    manager = _manager()
    sensor = _radar()
    _cycle(
        manager,
        (_attachment(sensor),),
        tick=0,
        targets=[_target()],
        native_periods=(2,),
    )
    witnesses = manager.get_current_detection_witnesses()
    supports = manager.get_observer_track_supports()
    plan = manager.prepare_witness_clear()
    object.__setattr__(
        plan,
        "_observer_track_supports",
        list(plan._observer_track_supports),
    )

    with pytest.raises(ValueError, match="exact ObserverTrackSupportState tuple"):
        manager.commit_prepared_witness_clear(plan)
    assert manager.get_current_detection_witnesses() == witnesses
    assert manager.get_observer_track_supports() == supports

    manager.abort_witness_clear(plan)
    manager.commit_prepared_witness_clear(manager.prepare_witness_clear())
    assert manager.get_current_detection_witnesses() == ()
    assert manager.get_observer_track_supports() == ()
