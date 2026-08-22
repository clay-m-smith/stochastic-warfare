"""Dormant observer-support lifecycle regression coverage.

This module calls the lower-level FOW owner directly. It preserves the
retired cadence algorithm's track-generation and checkpoint invariants but is
not evidence that scan scheduling or LOD is a supported production input.
"""

from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from typing import Any

import numpy as np

from stochastic_warfare.core.indexed_rng import IndexedFOWRNG
from stochastic_warfare.core.types import Domain, ModuleId, Position
from stochastic_warfare.detection.cadence import (
    TacticalAttachmentIdentity,
    TacticalCadenceAttachment,
    TacticalObserverIdentity,
)
from stochastic_warfare.detection.deception import DeceptionEngine
from stochastic_warfare.detection.detection import DetectionEngine
from stochastic_warfare.detection.estimation import (
    EstimationConfig,
    StateEstimator,
    TrackStatus,
)
from stochastic_warfare.detection.fog_of_war import (
    FogOfWarLodTier,
    FogOfWarManager,
)
from stochastic_warfare.detection.intel_fusion import IntelFusionEngine
from stochastic_warfare.detection.sensors import (
    SensorDefinition,
    SensorInstance,
)
from stochastic_warfare.detection.signatures import (
    RadarSignature,
    SignatureProfile,
)
from stochastic_warfare.simulation.loadouts import SensorModeledRole


DIAGNOSTIC_SEED = 118_012


def _support_key(support: Any) -> tuple[str, str, int, str, str, str]:
    attachment = support.identity.attachment_identity
    return (
        attachment.reporting_side,
        attachment.observer_unit_id,
        attachment.source_equipment_index,
        attachment.sensor_id,
        attachment.modeled_role,
        support.identity.target_id,
    )


def _witness_key(witness: Any) -> tuple[str, str, int, str, str, str]:
    return (
        witness.side,
        witness.observer_unit_id,
        witness.source_equipment_index,
        witness.sensor_id,
        witness.modeled_role,
        witness.target_id,
    )


def _immediate_loss_support_manager(*, seed: int) -> FogOfWarManager:
    rng = np.random.Generator(np.random.PCG64(seed))
    estimator = StateEstimator(
        rng=rng,
        config=EstimationConfig(
            confirmation_threshold=1,
            coast_timeout_s=0.0,
            lost_timeout_s=0.0,
        ),
    )
    return FogOfWarManager(
        detection_engine=DetectionEngine(rng=rng),
        state_estimator=estimator,
        intel_fusion=IntelFusionEngine(
            state_estimator=estimator,
            rng=rng,
        ),
        deception_engine=DeceptionEngine(rng=rng),
        rng=rng,
    )


def _support_radar_attachment() -> SimpleNamespace:
    equipment = SimpleNamespace(operational=True, condition=1.0)
    sensor = SensorInstance(
        SensorDefinition(
            sensor_id="phase118-continuation-radar",
            sensor_type="RADAR",
            display_name="Phase 118 continuation radar",
            max_range_m=20_000.0,
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
    return SimpleNamespace(
        sensor=sensor,
        source_equipment_index=7,
        sensor_id=sensor.sensor_id,
        modeled_role=SensorModeledRole.FIRE_CONTROL_RADAR,
    )


def _support_target() -> dict[str, object]:
    return {
        "unit_id": "red-target",
        "position": Position(1_000.0, 0.0, 0.0),
        "signature": SignatureProfile(
            profile_id="phase118-continuation-target",
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


def _public_support_cycle(
    manager: FogOfWarManager,
    attachment: SimpleNamespace,
    *,
    tick: int,
    targets: list[dict[str, object]],
) -> tuple[Any, Any]:
    attachment_identity = TacticalAttachmentIdentity(
        reporting_side="blue",
        observer_unit_id="blue-observer",
        source_equipment_index=attachment.source_equipment_index,
        sensor_id=attachment.sensor.sensor_id,
        modeled_role=attachment.modeled_role.value,
    )
    cadence_identity = TacticalCadenceAttachment(
        identity=attachment_identity,
        native_period=2,
        lod_period=1,
        operational=attachment.sensor.operational,
    )
    transaction = manager.begin_update_transaction(("blue",))
    cadence_plan = manager.cadence.stage_interval((cadence_identity,))
    indexed = IndexedFOWRNG(DIAGNOSTIC_SEED)
    allocation = indexed.begin_interval(
        module=ModuleId.DETECTION,
        engine_tick=tick,
        reporting_sides=("blue",),
    )
    side_plan = manager.update_with_receipt(
        "blue",
        [
            {
                "unit_id": "blue-observer",
                "position": Position(0.0, 0.0, 0.0),
                "sensors": [attachment.sensor],
                "sensor_attachments": [attachment],
                "observer_height": 1.8,
                "observer_heading_deg": 0.0,
            },
        ],
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
    publication = manager.prevalidate_update_transaction(
        transaction,
        (side_plan,),
    )
    record = indexed.commit_interval(allocation)
    manager.cadence.commit_interval(cadence_plan)
    manager.commit_update_transaction(publication)
    assert cadence_plan.decision_for(attachment_identity).native_period == 2
    return side_plan.outcome, record


def test_public_fow_loss_and_real_redetection_allocate_fresh_support_generation() -> None:
    """A natural loss cannot resurrect the prior support/track generation."""
    manager = _immediate_loss_support_manager(seed=DIAGNOSTIC_SEED)
    attachment = _support_radar_attachment()

    initial, initial_record = _public_support_cycle(
        manager,
        attachment,
        tick=0,
        targets=[_support_target()],
    )
    assert len(initial_record.entries) == 1
    assert len(initial.observer_track_supports) == 1
    old_support = initial.observer_track_supports[0]
    old_track_id = old_support.fusion_track_id
    old_contact = manager.get_contact("blue", "red-target")
    assert old_contact is not None
    assert old_contact.track is manager.intel_fusion.get_tracks("blue")[old_track_id]
    assert old_contact.track.status is TrackStatus.CONFIRMED
    assert old_support.observation_ordinal == 0
    assert old_support.native_due_ordinal == 2
    assert _support_key(old_support) == _witness_key(initial.witnesses[0])

    lost, lost_record = _public_support_cycle(
        manager,
        attachment,
        tick=1,
        targets=[],
    )
    assert lost_record.entries == ()
    assert lost.witnesses == ()
    assert lost.observer_track_supports == ()
    assert manager.get_observer_track_supports("blue") == ()
    assert manager.get_contact("blue", "red-target") is None
    assert manager.snapshot_side("blue").identities == ()
    lost_tracks = manager.intel_fusion.get_tracks("blue")
    assert set(lost_tracks) == {old_track_id}
    assert lost_tracks[old_track_id].status is TrackStatus.LOST
    assert lost.receipt.cadence.deferred_native == 1
    assert lost.receipt.detection.api_calls == 0

    lost_state = deepcopy(manager.get_state())
    restored = _immediate_loss_support_manager(seed=DIAGNOSTIC_SEED + 1)
    restored.set_state(deepcopy(lost_state))
    assert restored.get_state() == lost_state

    redetected, redetected_record = _public_support_cycle(
        manager,
        attachment,
        tick=2,
        targets=[_support_target()],
    )
    restored_redetected, restored_record = _public_support_cycle(
        restored,
        attachment,
        tick=2,
        targets=[_support_target()],
    )
    assert redetected_record == restored_record
    assert len(redetected_record.entries) == 1
    assert manager.get_state() == restored.get_state()

    fresh_supports = manager.get_observer_track_supports("blue")
    assert fresh_supports == redetected.observer_track_supports
    assert fresh_supports == restored_redetected.observer_track_supports
    assert len(fresh_supports) == 1
    fresh_support = fresh_supports[0]
    fresh_track_id = fresh_support.fusion_track_id
    assert fresh_support.identity == old_support.identity
    assert fresh_support != old_support
    assert fresh_track_id != old_track_id
    assert fresh_support.observation_ordinal == 2
    assert fresh_support.native_due_ordinal == 4
    assert _support_key(fresh_support) == _witness_key(
        redetected.witnesses[0],
    )

    redetected_tracks = manager.intel_fusion.get_tracks("blue")
    assert set(redetected_tracks) == {old_track_id, fresh_track_id}
    assert redetected_tracks[old_track_id].status is TrackStatus.LOST
    assert redetected_tracks[fresh_track_id].status is TrackStatus.CONFIRMED
    contact = manager.get_contact("blue", "red-target")
    assert contact is not None
    assert contact.track is redetected_tracks[fresh_track_id]
    assert contact.track.track_id == fresh_support.fusion_track_id
    assert all(support.fusion_track_id != old_track_id for support in manager.get_observer_track_supports())

    redetected_state = deepcopy(manager.get_state())
    manager.set_state(deepcopy(lost_state))
    assert manager.get_state() == lost_state
    replayed, replayed_record = _public_support_cycle(
        manager,
        attachment,
        tick=2,
        targets=[_support_target()],
    )
    assert replayed_record == redetected_record
    assert replayed.observer_track_supports == fresh_supports
    assert manager.get_state() == redetected_state
