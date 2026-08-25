"""Focused owner-bound observer-track-support tests for Phase 118."""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import numpy as np
import pytest

from stochastic_warfare.core.indexed_rng import IndexedFOWRNG
from stochastic_warfare.core.events import EventBus
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
from stochastic_warfare.simulation.battle import (
    BattleContext,
    BattleManager,
    _TargetingFireControl,
)
from stochastic_warfare.simulation.loadouts import SensorModeledRole
from stochastic_warfare.simulation.tactical_targeting import (
    ContactSource,
    FireControlSource,
    TargetingDisposition,
)


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
    prepared = manager.prepare_update_commit(publication)
    record = indexed.commit_interval(allocation)
    manager.cadence.commit_interval(cadence_plan)
    manager.commit_prepared_update(prepared)
    return side_plan.outcome, record, cadence_plan, prepared


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


def test_same_sensor_id_candidates_preserve_support_and_contact_provenance() -> None:
    manager = _manager()
    sensor = _radar()
    attachments = (
        _attachment(sensor, source_equipment_index=7),
        _attachment(sensor, source_equipment_index=8),
    )

    outcome, record, cadence_plan, prepared = _cycle(
        manager,
        attachments,
        tick=0,
        targets=[_target()],
        native_periods=(2, 2),
    )

    contact = outcome.world_view.contacts["red-target"]
    assert len(record.entries) == 2
    assert len(outcome.witnesses) == 2
    assert tuple(
        support.identity.attachment_identity.source_equipment_index for support in outcome.observer_track_supports
    ) == (7, 8)
    decisions_by_index = {decision.identity.source_equipment_index: decision for decision in cadence_plan.decisions}
    assert tuple(decisions_by_index) == (7, 8)
    assert all(
        support.identity.attachment_identity
        == decisions_by_index[support.identity.attachment_identity.source_equipment_index].identity
        for support in outcome.observer_track_supports
    )
    assert all(
        support.identity.attachment_identity
        is not decisions_by_index[support.identity.attachment_identity.source_equipment_index].identity
        for support in outcome.observer_track_supports
    )
    assert decisions_by_index[7].identity.sensor_id == decisions_by_index[8].identity.sensor_id == sensor.sensor_id
    assert decisions_by_index[7].identity is not decisions_by_index[8].identity
    assert contact.reporting_sensors == [sensor.sensor_id]
    assert contact.first_detected_time == 5.0
    assert contact.last_sensor_contact_time == 5.0
    assert outcome.receipt.fusion.position_measurement_candidates == 2
    assert outcome.receipt.fusion.position_measurement_groups == 1
    assert outcome.receipt.fusion.correlated_candidates_elided == 1
    assert outcome.receipt.fusion.creations == 1
    assert outcome.receipt.fusion.updates == 0

    committed_states = {state.identity.source_equipment_index: state for state in manager.cadence.attachment_states}
    committed_assignments = {
        assignment.identity.source_equipment_index: assignment for assignment in manager.cadence.phase_assignments
    }
    assert tuple(committed_states) == (7, 8)
    assert tuple(committed_assignments) == (7, 8)
    for equipment_index in (7, 8):
        committed_identity = committed_states[equipment_index].identity
        assert committed_identity is committed_assignments[equipment_index].identity
        assert committed_identity == decisions_by_index[equipment_index].identity
        assert committed_identity is not decisions_by_index[equipment_index].identity

    live_supports = manager.get_observer_track_supports("blue")
    live_support_states = tuple(support.get_state() for support in live_supports)
    live_witnesses = manager.get_current_detection_witnesses("blue")
    live_witness_states = tuple(witness.get_state() for witness in live_witnesses)
    manager_state = manager.get_state()
    cadence_state = manager.cadence.get_state()
    checkpoint_state = manager.capture_checkpoint_snapshot().state
    authoritative_supports = tuple(
        sorted(
            manager._observer_track_supports.values(),
            key=lambda support: support.identity.sort_key(),
        ),
    )
    authoritative_witnesses = manager._current_detection_witnesses["blue"]
    for public_supports in (
        live_supports,
        manager.get_observer_track_supports(),
    ):
        assert all(
            public_support is not authoritative_support
            and public_support.identity is not authoritative_support.identity
            and public_support.identity.attachment_identity is not authoritative_support.identity.attachment_identity
            for public_support, authoritative_support in zip(
                public_supports,
                authoritative_supports,
                strict=True,
            )
        )
        object.__setattr__(
            public_supports[0].identity.attachment_identity,
            "sensor_id",
            "mutated-public-support-getter",
        )
    for public_witnesses in (
        live_witnesses,
        manager.get_current_detection_witnesses(),
    ):
        assert all(
            public_witness is not authoritative_witness
            for public_witness, authoritative_witness in zip(
                public_witnesses,
                authoritative_witnesses,
                strict=True,
            )
        )
        object.__setattr__(
            public_witnesses[0],
            "sensor_id",
            "mutated-public-witness-getter",
        )
    live_supports = manager.get_observer_track_supports("blue")
    live_witnesses = manager.get_current_detection_witnesses("blue")
    assert tuple(support.get_state() for support in live_supports) == live_support_states
    assert tuple(witness.get_state() for witness in live_witnesses) == live_witness_states
    assert manager.get_state() == manager_state
    assert manager.cadence.get_state() == cadence_state
    assert manager.capture_checkpoint_snapshot().state == checkpoint_state

    retained_outcomes = (outcome, prepared.outcomes[0])
    for retained_outcome in retained_outcomes:
        assert all(
            retained_support is not live_support
            and retained_support.identity is not live_support.identity
            and retained_support.identity.attachment_identity is not live_support.identity.attachment_identity
            for retained_support, live_support in zip(
                retained_outcome.observer_track_supports,
                live_supports,
                strict=True,
            )
        )
        assert all(
            retained_witness is not live_witness
            for retained_witness, live_witness in zip(
                retained_outcome.witnesses,
                live_witnesses,
                strict=True,
            )
        )
        object.__setattr__(
            retained_outcome.observer_track_supports[0].identity.attachment_identity,
            "sensor_id",
            "mutated-retained-support",
        )
        object.__setattr__(
            retained_outcome.witnesses[0],
            "sensor_id",
            "mutated-retained-witness",
        )
        object.__setattr__(
            retained_outcome.receipt,
            "engine_tick",
            retained_outcome.receipt.engine_tick + 100,
        )

    assert tuple(support.get_state() for support in manager.get_observer_track_supports("blue")) == live_support_states
    assert (
        tuple(witness.get_state() for witness in manager.get_current_detection_witnesses("blue")) == live_witness_states
    )
    assert tuple(witness.get_state() for witness in prepared.outcomes[0].witnesses) == live_witness_states
    assert manager.get_state() == manager_state
    assert manager.cadence.get_state() == cadence_state
    assert manager.capture_checkpoint_snapshot().state == checkpoint_state

    retained_identity = decisions_by_index[7].identity
    original_sensor_id = retained_identity.sensor_id
    object.__setattr__(
        retained_identity,
        "sensor_id",
        "mutated-retained-plan-sensor",
    )

    assert retained_identity.sensor_id != original_sensor_id
    assert manager.get_observer_track_supports("blue") == live_supports
    assert tuple(support.get_state() for support in manager.get_observer_track_supports("blue")) == live_support_states
    assert all(
        manager._observer_track_supports[support.identity] is not support
        and manager._observer_track_supports[support.identity].identity is not support.identity
        and manager._observer_track_supports[support.identity].identity.attachment_identity
        is not support.identity.attachment_identity
        for support in live_supports
    )
    assert manager.get_state() == manager_state
    assert manager.cadence.get_state() == cadence_state
    assert manager.capture_checkpoint_snapshot().state == checkpoint_state


def test_targeting_support_evidence_is_detached_from_live_fow_state() -> None:
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
    deferred, _, _, _ = _cycle(
        manager,
        (attachment,),
        tick=1,
        targets=[_target()],
        native_periods=(2,),
    )
    assert deferred.witnesses == ()
    authoritative_support = next(iter(manager._observer_track_supports.values()))
    support_state = authoritative_support.get_state()
    manager_state = manager.get_state()
    checkpoint_state = manager.capture_checkpoint_snapshot().state

    context = SimpleNamespace(
        cal_flat={
            "enable_fog_of_war": True,
            "enable_sensing_aware_standoff": True,
        },
        clock=SimpleNamespace(
            elapsed=timedelta(seconds=10),
            tick_count=1,
        ),
        fog_of_war=manager,
        unit_sensor_attachments={"blue-observer": (attachment,)},
    )
    shooter = SimpleNamespace(
        entity_id="blue-observer",
        side="blue",
        domain=Domain.GROUND,
        position=Position(0.0, 0.0, 0.0),
        heading=0.0,
    )
    target = SimpleNamespace(
        entity_id="red-target",
        side="red",
        domain=Domain.AERIAL,
        position=Position(1_000.0, 0.0, 0.0),
    )
    battle_manager = BattleManager(EventBus())
    contacts = battle_manager._targeting_contacts(
        context,
        shooter,
        target,
        distance_m=1_000.0,
        visibility_bound_m=10_000.0,
        direct_visual_range_m=0.0,
        sensor_ranges={7: 20_000.0},
    )
    support_contact = next(
        contact for contact in contacts if contact.source is ContactSource.FOW_OBSERVER_TRACK_SUPPORT
    )
    decision = battle_manager._build_targeting_decision(
        ctx=context,
        battle=BattleContext(
            battle_id="support-alias-regression",
            start_tick=1,
            start_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
            involved_sides=["blue", "red"],
            unit_ids={"blue-observer", "red-target"},
        ),
        shooter=shooter,
        target=target,
        ordinal=0,
        distance_m=1_000.0,
        direct_visual_range_m=0.0,
        contact=support_contact,
        weapon=None,
        ammunition=None,
        fire_control=_TargetingFireControl(
            source=FireControlSource.SENSOR_ATTACHMENT,
            range_m=20_000.0,
            sensor_attachment=attachment,
        ),
        disposition=TargetingDisposition.NO_USABLE_WEAPON,
    )
    evidence = decision.observer_track_support
    assert evidence is not None
    assert evidence.identity is not authoritative_support.identity
    assert evidence.identity.attachment_identity is not authoritative_support.identity.attachment_identity

    object.__setattr__(
        evidence.identity.attachment_identity,
        "sensor_id",
        "mutated-targeting-evidence",
    )

    assert authoritative_support.get_state() == support_state
    assert manager._observer_track_supports[authoritative_support.identity] is authoritative_support
    assert manager.get_state() == manager_state
    assert manager.capture_checkpoint_snapshot().state == checkpoint_state


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
    assert manager._update_workspace is not None

    manager.abort_update_transaction(transaction)
    manager.cadence.abort_interval(cadence_plan)
    allocation.abort()

    assert manager._update_workspace is None
    assert manager.get_observer_track_supports("blue") == ()


def test_support_previews_are_defensive_but_handle_binding_mutation_rejects() -> None:
    manager = _manager()
    sensor = _radar()
    _cycle(
        manager,
        (_attachment(sensor),),
        tick=0,
        targets=[_target()],
        native_periods=(2,),
    )
    retained = manager.get_observer_track_supports("blue")
    snapshot = manager.snapshot_side("blue")
    fusion = manager.intel_fusion.get_state()
    transaction, cadence_plan, allocation, side_plan = _cycle(
        manager,
        (_attachment(sensor),),
        tick=1,
        targets=[_target()],
        native_periods=(2,),
        commit=False,
    )
    expected_supports = side_plan.outcome.observer_track_supports
    assert expected_supports == retained
    side_preview = side_plan._observer_track_supports[0]
    assert side_preview is not retained[0]
    object.__setattr__(
        side_preview,
        "native_due_ordinal",
        side_preview.native_due_ordinal + 100,
    )

    transaction_preview = transaction._observer_track_supports[0]
    object.__setattr__(
        transaction_preview,
        "native_due_ordinal",
        transaction_preview.native_due_ordinal + 100,
    )
    publication = manager.prevalidate_update_transaction(
        transaction,
        (side_plan,),
    )
    assert publication.outcomes[0].observer_track_supports == expected_supports

    publication_preview = publication._observer_track_supports[0]
    object.__setattr__(
        publication_preview,
        "native_due_ordinal",
        publication_preview.native_due_ordinal + 100,
    )
    prepared = manager.prepare_update_commit(publication)
    assert prepared.outcomes[0].observer_track_supports == expected_supports
    payload = manager._prepared_update_payload
    assert payload is not None
    prepared_support_map = payload.observer_track_support_map
    assert all(
        key is support.identity and value is support
        for (key, value), support in zip(
            prepared_support_map.items(),
            payload.observer_track_supports,
            strict=True,
        )
    )

    payload.observer_track_support_map = dict(prepared_support_map)
    with pytest.raises(ValueError, match="commit plan metadata was mutated"):
        manager.validate_prepared_update_commit(prepared)
    payload.observer_track_support_map = prepared_support_map

    original_support_binding = publication._observer_track_supports
    object.__setattr__(
        publication,
        "_observer_track_supports",
        list(original_support_binding),
    )
    with pytest.raises(ValueError, match="exact ObserverTrackSupportState tuple"):
        manager.validate_prepared_update_commit(prepared)
    assert manager.snapshot_side("blue") == snapshot
    assert manager.get_observer_track_supports("blue") == retained
    assert manager.intel_fusion.get_state() == fusion
    object.__setattr__(
        publication,
        "_observer_track_supports",
        original_support_binding,
    )
    manager.validate_prepared_update_commit(prepared)

    allocation._owner.commit_interval(allocation)
    manager.cadence.commit_interval(cadence_plan)
    manager.commit_prepared_update(prepared)
    assert manager._observer_track_supports is prepared_support_map
    assert manager._update_workspace is None


def test_support_map_preparation_failure_precedes_every_owner_swap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _manager()
    sensor = _radar()
    live_bindings = (
        manager._detection._scan_counts,
        manager._intel_fusion._tracks,
        manager._intel_fusion._fow_track_counters,
        manager.cadence._states,
        manager.cadence._phase_assignments,
        manager._world_views,
        manager._current_detection_witnesses,
        manager._observer_track_supports,
    )
    rng_state = copy.deepcopy(manager._rng.bit_generator.state)
    transaction, cadence_plan, allocation, side_plan = _cycle(
        manager,
        (_attachment(sensor),),
        tick=0,
        targets=[_target()],
        native_periods=(2,),
        commit=False,
    )
    publication = manager.prevalidate_update_transaction(
        transaction,
        (side_plan,),
    )

    def fail_support_map(
        supports: tuple[object, ...],
    ) -> dict[object, object]:
        assert supports
        raise RuntimeError("injected support map preparation failure")

    monkeypatch.setattr(
        FogOfWarManager,
        "_prepare_observer_track_support_map",
        staticmethod(fail_support_map),
    )

    with pytest.raises(
        RuntimeError,
        match="injected support map preparation failure",
    ):
        manager.prepare_update_commit(publication)

    assert manager._prepared_update_commit is None
    assert manager._prepared_update_payload is None
    assert all(
        current is previous
        for current, previous in zip(
            (
                manager._detection._scan_counts,
                manager._intel_fusion._tracks,
                manager._intel_fusion._fow_track_counters,
                manager.cadence._states,
                manager.cadence._phase_assignments,
                manager._world_views,
                manager._current_detection_witnesses,
                manager._observer_track_supports,
            ),
            live_bindings,
            strict=True,
        )
    )
    assert manager._rng.bit_generator.state == rng_state
    assert manager.peek_world_view("blue") is None
    assert manager.intel_fusion.get_tracks("blue") == {}
    assert manager.get_current_detection_witnesses() == ()
    assert manager.get_observer_track_supports() == ()
    assert allocation._owner.committed_interval_count == 0
    assert allocation._owner.committed_entry_count == 0

    allocation.abort()
    manager.cadence.abort_interval(cadence_plan)
    manager.abort_update_transaction(transaction)
    assert manager._update_workspace is None


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
    support_preview = plan.observer_track_supports[0]
    witness_preview = plan.current_detection_witnesses["blue"][0]
    assert support_preview is not plan._observer_track_supports[0]
    assert witness_preview is not plan._current_detection_witnesses["blue"][0]
    object.__setattr__(
        support_preview.identity.attachment_identity,
        "sensor_id",
        "mutated-restore-support-preview",
    )
    object.__setattr__(
        witness_preview,
        "sensor_id",
        "mutated-restore-witness-preview",
    )
    target.commit_state(plan)
    assert target.get_state() == state

    restore_cadence_state = plan._cadence_plan.attachment_states[0]
    restore_cadence_assignment = plan._cadence_plan.phase_assignments[0]
    committed_cadence_state = target.cadence.attachment_states[0]
    committed_cadence_assignment = target.cadence.phase_assignments[0]
    assert committed_cadence_state.identity is committed_cadence_assignment.identity
    assert committed_cadence_state.identity == restore_cadence_state.identity
    assert committed_cadence_state.identity == restore_cadence_assignment.identity
    assert committed_cadence_state.identity is not restore_cadence_state.identity
    assert committed_cadence_state.identity is not restore_cadence_assignment.identity
    assert committed_cadence_state is not restore_cadence_state
    assert committed_cadence_assignment is not restore_cadence_assignment
    target_state = target.get_state()
    target_supports = target.get_observer_track_supports("blue")
    object.__setattr__(
        restore_cadence_state.identity,
        "sensor_id",
        "mutated-restore-plan-sensor",
    )
    object.__setattr__(
        restore_cadence_state,
        "native_next_due",
        restore_cadence_state.native_next_due + 100,
    )
    object.__setattr__(
        restore_cadence_assignment.identity,
        "sensor_id",
        "mutated-restore-plan-assignment-sensor",
    )

    assert target.get_state() == target_state
    assert target.cadence.get_state() == target_state["cadence"]
    assert target.capture_checkpoint_snapshot().state == target_state
    assert target.get_observer_track_supports("blue") == target_supports
    assert all(
        target._observer_track_supports[support.identity] is not support
        and target._observer_track_supports[support.identity].identity is not support.identity
        and target._observer_track_supports[support.identity].identity.attachment_identity
        is not support.identity.attachment_identity
        for support in target_supports
    )

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


def test_disabled_fow_clear_nested_support_mutation_never_reaches_live_state() -> None:
    manager = _manager()
    sensor = _radar()
    _cycle(
        manager,
        (_attachment(sensor),),
        tick=0,
        targets=[_target()],
        native_periods=(2,),
    )
    live_support = next(iter(manager._observer_track_supports.values()))
    state_before = manager.get_state()
    checkpoint_before = manager.capture_checkpoint_snapshot().state
    plan = manager.prepare_witness_clear()
    plan_support = plan._observer_track_supports[0]
    assert plan_support is not live_support
    assert plan_support.identity is not live_support.identity
    assert plan_support.identity.attachment_identity is not live_support.identity.attachment_identity

    object.__setattr__(
        plan_support.identity.attachment_identity,
        "sensor_id",
        "mutated-witness-clear-support",
    )

    with pytest.raises(ValueError, match="witness clear was mutated"):
        manager.validate_prepared_witness_clear(plan)
    assert live_support.get_state() == state_before["observer_track_supports"][0]
    manager.abort_witness_clear(plan)
    assert manager.get_state() == state_before
    assert manager.capture_checkpoint_snapshot().state == checkpoint_before


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
