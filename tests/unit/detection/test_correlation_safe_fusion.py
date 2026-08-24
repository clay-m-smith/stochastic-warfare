"""Focused behavioral proofs for correlation-safe same-epoch fusion."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from stochastic_warfare.core.indexed_rng import (
    FOWDecisionIdentity,
    FOWTargetKind,
    encode_fow_decision,
)
from stochastic_warfare.core.performance_receipts import (
    FOWDetectionReceipt,
    FOWFusionReceipt,
    FOWIndexedRNGReceipt,
    FOWReceipt,
    FOWScanReceipt,
)
from stochastic_warfare.core.types import Position
from stochastic_warfare.detection.detection import DetectionResult
from stochastic_warfare.detection.estimation import StateEstimator
from stochastic_warfare.detection.identification import ContactInfo, ContactLevel
from stochastic_warfare.detection.intel_fusion import (
    IntelFusionEngine,
    SensorFusionCandidate,
)
from stochastic_warfare.detection.sensors import SensorType


def _engine(seed: int = 7) -> IntelFusionEngine:
    return IntelFusionEngine(
        state_estimator=StateEstimator(
            rng=np.random.Generator(np.random.PCG64(seed + 1)),
        ),
        rng=np.random.Generator(np.random.PCG64(seed)),
    )


def _candidate(
    source_equipment_index: int,
    *,
    probability: float = 0.8,
    range_m: float = 1_000.0,
    bearing_deg: float = 90.0,
    observer_position: Position = Position(0.0, 0.0, 0.0),
    observation_time_s: float = 5.0,
    reporting_side: str = "blue",
    target_kind: FOWTargetKind = FOWTargetKind.UNIT,
    target_id: str = "target-1",
    engine_tick: int = 1,
) -> SensorFusionCandidate:
    return SensorFusionCandidate(
        identity=FOWDecisionIdentity(
            engine_tick=engine_tick,
            reporting_side=reporting_side,
            observer_unit_id=f"observer-{source_equipment_index}",
            source_equipment_index=source_equipment_index,
            sensor_id=f"sensor-{source_equipment_index}",
            modeled_role="local_fire_control",
            target_kind=target_kind,
            target_id=target_id,
        ),
        detection=DetectionResult(
            True,
            probability,
            12.0,
            range_m,
            SensorType.RADAR,
            bearing_deg,
            horizontal_range_m=range_m,
        ),
        contact_info=ContactInfo(
            ContactLevel.DETECTED,
            None,
            None,
            None,
            0.5,
        ),
        observer_position=observer_position,
        observation_time_s=observation_time_s,
    )


def _track_state(engine: IntelFusionEngine, track_id: str) -> dict[str, object]:
    return engine.get_tracks("blue")[track_id].get_state()


def test_same_epoch_correlated_reports_equal_one_representative() -> None:
    """Same-truth sensor reports must not masquerade as independent evidence."""
    first = _candidate(0)
    second = _candidate(1)

    selected_only = _engine()
    selected_outcome = selected_only.submit_sensor_detection_batch_with_outcome(
        [first],
    )

    correlated = _engine()
    correlated_outcome = correlated.submit_sensor_detection_batch_with_outcome(
        [first, second],
    )

    assert selected_outcome.track_id == correlated_outcome.track_id == "fow-track-0001"
    assert _track_state(
        correlated,
        correlated_outcome.track_id,
    ) == _track_state(selected_only, selected_outcome.track_id)
    assert correlated_outcome.position_measurement_candidates == 2
    assert correlated_outcome.position_measurement_groups == 1
    assert correlated_outcome.correlated_candidates_elided == 1
    assert correlated_outcome.creations == 1


def test_single_candidate_batch_preserves_legacy_sensor_submission_state() -> None:
    candidate = _candidate(0)

    legacy = _engine()
    legacy_outcome = legacy.submit_sensor_detection_with_outcome(
        candidate.identity.reporting_side,
        candidate.detection,
        candidate.contact_info,
        candidate.observer_position,
        allocate_fow_track=True,
        observation_time_s=candidate.observation_time_s,
    )
    batched = _engine()
    batch_outcome = batched.submit_sensor_detection_batch_with_outcome(
        [candidate],
    )

    assert batched.get_state() == legacy.get_state()
    assert (
        batch_outcome.track_id,
        batch_outcome.prediction_microseconds,
        batch_outcome.creations,
        batch_outcome.updates,
        batch_outcome.replacements,
    ) == (
        legacy_outcome.track_id,
        legacy_outcome.prediction_microseconds,
        legacy_outcome.creations,
        legacy_outcome.updates,
        legacy_outcome.replacements,
    )


def test_minimum_effective_variance_wins_independent_of_input_order() -> None:
    looser = _candidate(
        0,
        probability=0.5,
        observer_position=Position(5_000.0, 0.0, 0.0),
    )
    tighter = _candidate(
        1,
        probability=1.0,
        observer_position=Position(0.0, 0.0, 0.0),
    )

    forward = _engine()
    forward_outcome = forward.submit_sensor_detection_batch_with_outcome(
        [looser, tighter],
    )
    reverse = _engine()
    reverse_outcome = reverse.submit_sensor_detection_batch_with_outcome(
        [tighter, looser],
    )

    assert forward.get_state() == reverse.get_state()
    track = forward.get_tracks("blue")[forward_outcome.track_id]
    np.testing.assert_allclose(track.state.position, [1_000.0, 0.0], atol=1e-12)
    assert reverse_outcome.track_id == forward_outcome.track_id


def test_equal_variance_uses_canonical_encoded_identity_tie_break() -> None:
    candidates = (
        _candidate(4, observer_position=Position(4_000.0, 0.0, 0.0)),
        _candidate(2, observer_position=Position(2_000.0, 0.0, 0.0)),
    )
    representative = min(
        candidates,
        key=lambda candidate: encode_fow_decision(candidate.identity),
    )
    expected_easting = (
        representative.observer_position.easting
        + representative.detection.range_m
    )

    engine = _engine()
    outcome = engine.submit_sensor_detection_batch_with_outcome(candidates)

    track = engine.get_tracks("blue")[outcome.track_id]
    assert track.state.position[0] == expected_easting


def test_later_group_predicts_and_updates_once_for_multiple_candidates() -> None:
    initial = _candidate(0, observation_time_s=0.0, engine_tick=0)
    later_first = _candidate(1, observation_time_s=5.0, engine_tick=1)
    later_second = _candidate(2, observation_time_s=5.0, engine_tick=1)

    engine = _engine()
    initial_outcome = engine.submit_sensor_detection_batch_with_outcome([initial])
    later_outcome = engine.submit_sensor_detection_batch_with_outcome(
        [later_first, later_second],
        contact_id=initial_outcome.track_id,
    )

    track = engine.get_tracks("blue")[later_outcome.track_id]
    assert later_outcome.predictions == 1
    assert later_outcome.prediction_microseconds == 5_000_000
    assert later_outcome.updates == 1
    assert later_outcome.position_measurement_groups == 1
    assert track.hits == 2


def test_gated_representative_replaces_without_retrying_looser_candidate() -> None:
    initial = _candidate(
        0,
        probability=1.0,
        range_m=1.0,
        observer_position=Position(-1.0, 0.0, 0.0),
        observation_time_s=0.0,
        engine_tick=0,
    )
    tight_but_far = _candidate(
        1,
        probability=1.0,
        range_m=1.0,
        observer_position=Position(9_999.0, 0.0, 0.0),
        observation_time_s=1.0,
    )
    loose_but_near = _candidate(
        2,
        probability=0.5,
        range_m=100.0,
        observer_position=Position(-100.0, 0.0, 0.0),
        observation_time_s=1.0,
    )

    engine = _engine()
    initial_outcome = engine.submit_sensor_detection_batch_with_outcome([initial])
    replacement = engine.submit_sensor_detection_batch_with_outcome(
        [loose_but_near, tight_but_far],
        contact_id=initial_outcome.track_id,
    )

    assert replacement.track_id == "fow-track-0002"
    assert replacement.replacements == 1
    assert replacement.updates == 0
    assert tuple(engine.get_tracks("blue")) == ("fow-track-0002",)
    track = engine.get_tracks("blue")[replacement.track_id]
    np.testing.assert_allclose(track.state.position, [10_000.0, 0.0], atol=1e-12)


@pytest.mark.parametrize(
    "second",
    [
        _candidate(1, observation_time_s=6.0),
        _candidate(1, engine_tick=2),
        _candidate(1, reporting_side="red"),
        _candidate(1, target_id="target-2"),
        _candidate(1, target_kind=FOWTargetKind.DECOY),
    ],
    ids=("time", "tick", "side", "target", "target-kind"),
)
def test_mixed_exact_groups_reject_atomically(
    second: SensorFusionCandidate,
) -> None:
    engine = _engine()
    before = engine.get_state()

    with pytest.raises(ValueError, match="must share one exact"):
        engine.submit_sensor_detection_batch_with_outcome([_candidate(0), second])

    assert engine.get_state() == before


def test_duplicate_identity_rejects_atomically() -> None:
    engine = _engine()
    candidate = _candidate(0)
    before = engine.get_state()

    with pytest.raises(ValueError, match="duplicate decision identity"):
        engine.submit_sensor_detection_batch_with_outcome([candidate, candidate])

    assert engine.get_state() == before


def test_malformed_later_candidate_rejects_complete_batch_atomically() -> None:
    engine = _engine()
    malformed = replace(
        _candidate(1),
        detection=_candidate(1).detection._replace(probability=float("nan")),
    )
    before = engine.get_state()

    with pytest.raises(ValueError, match="probability must be a finite number"):
        engine.submit_sensor_detection_batch_with_outcome(
            [_candidate(0), malformed],
        )

    assert engine.get_state() == before


def test_checkpoint_restore_continues_same_batched_update() -> None:
    first = _candidate(0, observation_time_s=0.0, engine_tick=0)
    later = (
        _candidate(1, observation_time_s=5.0, engine_tick=1),
        _candidate(2, observation_time_s=5.0, engine_tick=1),
    )
    uninterrupted = _engine()
    first_outcome = uninterrupted.submit_sensor_detection_batch_with_outcome([first])
    checkpoint = uninterrupted.get_state()

    control_outcome = uninterrupted.submit_sensor_detection_batch_with_outcome(
        later,
        contact_id=first_outcome.track_id,
    )
    restored = _engine(seed=999)
    restored.set_state(checkpoint)
    restored_outcome = restored.submit_sensor_detection_batch_with_outcome(
        tuple(reversed(later)),
        contact_id=first_outcome.track_id,
    )

    assert restored_outcome == control_outcome
    assert restored.get_state() == uninterrupted.get_state()


def _valid_fow_receipt() -> FOWReceipt:
    return FOWReceipt(
        scan=FOWScanReceipt(operational_sensor_target_opportunities=2),
        detection=FOWDetectionReceipt(
            api_calls=2,
            stochastic_draws=2,
            successes=2,
        ),
        fusion=FOWFusionReceipt(
            position_measurement_candidates=2,
            position_measurement_groups=1,
            correlated_candidates_elided=1,
            creations=1,
        ),
        indexed_rng=FOWIndexedRNGReceipt(
            blocks=2,
            detection_lanes=2,
            transcript_entries=2,
        ),
    )


def test_fusion_receipt_reconciles_candidates_groups_and_dispositions() -> None:
    receipt = _valid_fow_receipt()
    doubled = receipt.plus(receipt)

    assert receipt.fusion.position_measurement_candidates == receipt.detection.successes
    assert receipt.fusion.to_state() == {
        "position_measurement_candidates": 2,
        "position_measurement_groups": 1,
        "correlated_candidates_elided": 1,
        "predictions": 0,
        "predicted_microseconds": 0,
        "creations": 1,
        "updates": 0,
        "replacements": 0,
    }
    assert doubled.fusion.position_measurement_candidates == 4
    assert doubled.fusion.position_measurement_groups == 2
    assert doubled.fusion.correlated_candidates_elided == 2


@pytest.mark.parametrize(
    "fields, message",
    [
        (
            {
                "position_measurement_candidates": 2,
                "position_measurement_groups": 1,
                "correlated_candidates_elided": 0,
                "creations": 1,
            },
            "candidates must equal groups plus",
        ),
        (
            {
                "position_measurement_candidates": 1,
                "position_measurement_groups": 1,
                "creations": 0,
            },
            "groups must equal creations plus",
        ),
        (
            {
                "position_measurement_candidates": 1,
                "position_measurement_groups": 1,
                "creations": 1,
                "predictions": 2,
                "predicted_microseconds": 1,
            },
            "predictions cannot exceed",
        ),
    ],
)
def test_fusion_receipt_rejects_local_reconciliation_failures(
    fields: dict[str, int],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        FOWFusionReceipt(**fields)


def test_fow_receipt_rejects_detection_success_candidate_mismatch() -> None:
    with pytest.raises(
        ValueError,
        match="candidates must equal detection successes",
    ):
        FOWReceipt(
            scan=FOWScanReceipt(operational_sensor_target_opportunities=2),
            detection=FOWDetectionReceipt(
                api_calls=2,
                stochastic_draws=2,
                successes=2,
            ),
            fusion=FOWFusionReceipt(
                position_measurement_candidates=1,
                position_measurement_groups=1,
                creations=1,
            ),
            indexed_rng=FOWIndexedRNGReceipt(
                blocks=2,
                detection_lanes=2,
                transcript_entries=2,
            ),
        )
