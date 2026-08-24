"""Non-coplanar detection geometry through fusion and observer support."""

from __future__ import annotations

import math
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from stochastic_warfare.core.indexed_rng import (
    FOWDecisionIdentity,
    FOWTargetKind,
)
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import Domain, Position
from stochastic_warfare.detection.cadence import (
    TacticalAttachmentIdentity,
    TacticalCadenceAttachment,
    TacticalCadenceScheduler,
    TacticalObserverIdentity,
)
from stochastic_warfare.detection.deception import DeceptionEngine
from stochastic_warfare.detection.detection import (
    DetectionEngine,
    PreparedDetection,
)
from stochastic_warfare.detection.estimation import StateEstimator
from stochastic_warfare.detection.fog_of_war import (
    FogOfWarLodTier,
    FogOfWarManager,
)
from stochastic_warfare.detection.identification import ContactInfo, ContactLevel
from stochastic_warfare.detection.intel_fusion import (
    IntelFusionEngine,
    SensorFusionCandidate,
)
from stochastic_warfare.detection.sensors import (
    SensorDefinition,
    SensorInstance,
)
from stochastic_warfare.detection.signatures import RadarSignature, SignatureProfile
from stochastic_warfare.simulation.loadouts import SensorModeledRole


_TARGET_POSITION = Position(300.0, 400.0, 0.0)


def _slant_range(observer: Position, target: Position = _TARGET_POSITION) -> float:
    return math.sqrt(
        (target.easting - observer.easting) ** 2
        + (target.northing - observer.northing) ** 2
        + (target.altitude - observer.altitude) ** 2,
    )


def _fusion_engine(seed: int = 118_800) -> IntelFusionEngine:
    estimator = StateEstimator(
        rng=np.random.Generator(np.random.PCG64(seed + 1)),
    )
    return IntelFusionEngine(
        state_estimator=estimator,
        rng=np.random.Generator(np.random.PCG64(seed)),
    )


def _fusion_candidate(
    source_equipment_index: int,
    *,
    observer_position: Position,
    probability: float,
) -> SensorFusionCandidate:
    prepared = DetectionEngine(
        rng=np.random.Generator(np.random.PCG64(118_805 + source_equipment_index)),
    ).prepare_detection(
        observer_position,
        _TARGET_POSITION,
        _fire_control_radar(),
        _target_signature(),
        target_unit=SimpleNamespace(domain=Domain.AERIAL),
    )
    assert isinstance(prepared, PreparedDetection)
    detection = replace(prepared, probability=probability).adjudicate(0.0)
    return SensorFusionCandidate(
        identity=FOWDecisionIdentity(
            engine_tick=0,
            reporting_side="blue",
            observer_unit_id=f"blue-observer-{source_equipment_index}",
            source_equipment_index=source_equipment_index,
            sensor_id=f"radar-{source_equipment_index}",
            modeled_role=SensorModeledRole.FIRE_CONTROL_RADAR.value,
            target_kind=FOWTargetKind.UNIT,
            target_id="red-target",
        ),
        detection=detection,
        contact_info=ContactInfo(
            ContactLevel.DETECTED,
            None,
            None,
            None,
            0.5,
        ),
        observer_position=observer_position,
        observation_time_s=5.0,
    )


def test_single_non_coplanar_candidate_preserves_horizontal_xy_and_slant_noise() -> None:
    observer = Position(0.0, 0.0, 1_000.0)
    candidate = _fusion_candidate(
        0,
        observer_position=observer,
        probability=0.8,
    )
    engine = _fusion_engine()

    outcome = engine.submit_sensor_detection_batch_with_outcome((candidate,))

    track = engine.get_tracks("blue")[outcome.track_id]
    expected_variance = (0.05 * candidate.detection.range_m / 0.8) ** 2
    assert candidate.detection.range_m == pytest.approx(_slant_range(observer))
    assert candidate.detection.horizontal_range_m == pytest.approx(500.0)
    np.testing.assert_array_equal(track.state.position, [300.0, 400.0])
    np.testing.assert_allclose(
        np.diag(track.state.covariance),
        [expected_variance, expected_variance, 100.0, 100.0],
        rtol=0.0,
        atol=1e-12,
    )


def test_non_coplanar_multi_observer_fusion_is_permutation_invariant() -> None:
    tighter = _fusion_candidate(
        0,
        observer_position=Position(0.0, 0.0, 1_000.0),
        probability=0.9,
    )
    looser = _fusion_candidate(
        1,
        observer_position=Position(300.0, -600.0, 0.0),
        probability=0.5,
    )

    forward = _fusion_engine()
    forward_outcome = forward.submit_sensor_detection_batch_with_outcome(
        (tighter, looser),
    )
    reverse = _fusion_engine()
    reverse_outcome = reverse.submit_sensor_detection_batch_with_outcome(
        (looser, tighter),
    )

    expected_variance = (0.05 * tighter.detection.range_m / 0.9) ** 2
    assert forward_outcome == reverse_outcome
    assert forward.get_state() == reverse.get_state()
    track = forward.get_tracks("blue")[forward_outcome.track_id]
    np.testing.assert_array_equal(track.state.position, [300.0, 400.0])
    np.testing.assert_allclose(
        np.diag(track.state.covariance),
        [expected_variance, expected_variance, 100.0, 100.0],
        rtol=0.0,
        atol=1e-12,
    )


@pytest.mark.parametrize(
    ("horizontal_range_m", "message"),
    (
        (None, "must carry detector-emitted horizontal_range_m"),
        (float("nan"), "must be a finite number"),
        (True, "must be a finite number"),
        (-1.0, "must be non-negative"),
        (2_000.0, "must not exceed range_m"),
    ),
)
def test_invalid_detector_horizontal_range_rejects_before_mutation(
    horizontal_range_m: float | bool | None,
    message: str,
) -> None:
    engine = _fusion_engine()
    original = _fusion_candidate(
        0,
        observer_position=Position(0.0, 0.0, 1_000.0),
        probability=0.8,
    )
    candidate = replace(
        original,
        detection=original.detection._replace(
            horizontal_range_m=horizontal_range_m,
        ),
    )
    before = engine.get_state()

    with pytest.raises(
        ValueError,
        match=message,
    ):
        engine.submit_sensor_detection_batch_with_outcome((candidate,))

    assert engine.get_state() == before


def test_public_sensor_adapter_requires_and_uses_emitted_horizontal_range() -> None:
    observer = Position(0.0, 0.0, 1_000.0)
    candidate = _fusion_candidate(
        0,
        observer_position=observer,
        probability=0.8,
    )
    engine = _fusion_engine()

    outcome = engine.submit_sensor_detection_with_outcome(
        "blue",
        candidate.detection,
        candidate.contact_info,
        observer,
        allocate_fow_track=True,
        observation_time_s=5.0,
    )

    track = engine.get_tracks("blue")[outcome.track_id]
    np.testing.assert_array_equal(track.state.position, [300.0, 400.0])
    for horizontal_range_m, message in (
        (None, "must carry detector-emitted horizontal_range_m"),
        (2_000.0, "must not exceed range_m"),
    ):
        invalid_geometry = candidate.detection._replace(
            horizontal_range_m=horizontal_range_m,
        )
        before = engine.get_state()
        with pytest.raises(ValueError, match=message):
            engine.submit_sensor_detection_with_outcome(
                "blue",
                invalid_geometry,
                candidate.contact_info,
                observer,
                allocate_fow_track=True,
                observation_time_s=10.0,
            )
        assert engine.get_state() == before


def _fow_manager(seed: int = 118_810) -> FogOfWarManager:
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


def _fire_control_radar() -> SensorInstance:
    return SensorInstance(
        SensorDefinition(
            sensor_id="phase118-noncoplanar-radar",
            sensor_type="RADAR",
            display_name="Phase 118 Non-coplanar Radar",
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
        equipment=SimpleNamespace(operational=True, condition=1.0),
    )


def _target_signature() -> SignatureProfile:
    return SignatureProfile(
        profile_id="phase118-noncoplanar-target",
        unit_type="aircraft",
        radar=RadarSignature(
            rcs_frontal_m2=1_000.0,
            rcs_side_m2=1_000.0,
            rcs_rear_m2=1_000.0,
        ),
    )


def test_fow_transaction_publishes_exact_non_coplanar_track_support_estimate() -> None:
    manager = _fow_manager()
    sensor = _fire_control_radar()
    source_equipment_index = 7
    observer_position = Position(0.0, 0.0, 1_000.0)
    identity = TacticalAttachmentIdentity(
        reporting_side="blue",
        observer_unit_id="blue-observer",
        source_equipment_index=source_equipment_index,
        sensor_id=sensor.sensor_id,
        modeled_role=SensorModeledRole.FIRE_CONTROL_RADAR.value,
    )
    attachment = SimpleNamespace(
        sensor=sensor,
        source_equipment_index=source_equipment_index,
        sensor_id=sensor.sensor_id,
        modeled_role=SensorModeledRole.FIRE_CONTROL_RADAR,
    )
    transaction = manager.begin_update_transaction(("blue",))
    cadence_plan = manager.cadence.stage_interval(
        (
            TacticalCadenceAttachment(
                identity=identity,
                native_period=2,
                lod_period=1,
                operational=True,
            ),
        ),
    )
    rng_manager = RNGManager(118_811)
    allocation = rng_manager.begin_fow_detection_interval(0, ("blue",))
    side_plan = manager.update_with_receipt(
        "blue",
        [
            {
                "unit_id": "blue-observer",
                "position": observer_position,
                "sensors": [sensor],
                "sensor_attachments": [attachment],
                "observer_height": observer_position.altitude,
                "observer_heading_deg": 0.0,
            },
        ],
        [
            {
                "unit_id": "red-target",
                "position": _TARGET_POSITION,
                "signature": _target_signature(),
                "unit": SimpleNamespace(domain=Domain.AERIAL),
                "target_height": _TARGET_POSITION.altitude,
                "concealment": 0.0,
                "posture": 0,
            },
        ],
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
        current_time=5.0,
        current_tick=0,
        detection_culling=False,
    )
    publication = manager.prevalidate_update_transaction(
        transaction,
        (side_plan,),
    )
    rng_manager.commit_fow_detection_interval(allocation)
    manager.cadence.commit_interval(cadence_plan)
    manager.commit_update_transaction(publication)

    outcome = side_plan.outcome
    witness = outcome.witnesses[0]
    support = outcome.observer_track_supports[0]
    contact = outcome.world_view.contacts["red-target"]
    expected_variance = (max(0.05 * witness.range_m, 1.0) / max(witness.probability, 0.01)) ** 2
    np.testing.assert_array_equal(contact.track.state.position, [300.0, 400.0])
    assert support.position_m == pytest.approx((300.0, 400.0), abs=1e-12)
    assert support.covariance[0][0] == pytest.approx(expected_variance)
    assert support.covariance[1][1] == pytest.approx(expected_variance)
    assert witness.range_m == pytest.approx(_slant_range(observer_position))
