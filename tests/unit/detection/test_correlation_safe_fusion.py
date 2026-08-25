"""Focused behavioral proofs for correlation-safe same-epoch fusion."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from stochastic_warfare.core.indexed_rng import (
    FOWDecisionIdentity,
    FOWTargetKind,
    IndexedFOWRNG,
    IndexedRNGLifecycleError,
    IndexedRNGValidationError,
    encode_fow_decision,
)
from stochastic_warfare.core.performance_receipts import (
    FOWDetectionReceipt,
    FOWFusionReceipt,
    FOWIndexedRNGReceipt,
    FOWReceipt,
    FOWScanReceipt,
)
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.detection.detection import DetectionResult
from stochastic_warfare.detection.estimation import StateEstimator
from stochastic_warfare.detection.fog_of_war import _FOWFusionAccumulator
from stochastic_warfare.detection.identification import ContactInfo, ContactLevel
from stochastic_warfare.detection.intel_fusion import (
    IntelFusionEngine,
    SensorFusionCandidate,
)
from stochastic_warfare.detection.sensors import SensorType


class _TextSubclass(str):
    pass


class _MutableNamespace(str):
    def __new__(cls, value: str) -> _MutableNamespace:
        instance = super().__new__(cls, value)
        instance.accepted = True
        return instance

    def __eq__(self, other: object) -> bool:
        return self.accepted and super().__eq__(other)

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    __hash__ = str.__hash__


class _CountingNamespace(str):
    def __new__(cls, value: str) -> _CountingNamespace:
        instance = super().__new__(cls, value)
        instance.comparisons = 0
        return instance

    def __ne__(self, other: object) -> bool:
        self.comparisons += 1
        return super().__ne__(other)


class _IssuanceMutatingNamespace(str):
    identity: FOWDecisionIdentity

    def __ne__(self, other: object) -> bool:
        object.__setattr__(self.identity, "schema_version", 2)
        return super().__ne__(other)


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
    expected_easting = representative.observer_position.easting + representative.detection.range_m

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


def test_issued_preimage_requires_exact_identity_and_active_lifecycle() -> None:
    candidate = _candidate(1)
    indexed = IndexedFOWRNG(142_001)
    allocation = indexed.begin_interval(
        module=ModuleId.DETECTION,
        engine_tick=1,
        reporting_sides=("blue",),
    )
    decision = allocation.acquire_side("blue").issue(candidate.identity)

    assert decision._issued_preimage(candidate.identity) == encode_fow_decision(
        candidate.identity,
    )

    equal_identity = replace(candidate.identity)
    assert equal_identity == candidate.identity
    assert equal_identity is not candidate.identity
    with pytest.raises(
        IndexedRNGValidationError,
        match="not its issued identity",
    ):
        decision._issued_preimage(equal_identity)

    with pytest.raises(IndexedRNGLifecycleError, match="not active"):
        decision._issued_preimage(candidate.identity)
    with pytest.raises(IndexedRNGLifecycleError, match="not active"):
        indexed.commit_interval(allocation)
    assert indexed.committed_interval_count == 0
    assert indexed.committed_entry_count == 0


@pytest.mark.parametrize(
    ("field_name", "mutated_value", "encoder_outcome"),
    (
        pytest.param(
            "sensor_id",
            "mutated-after-issue",
            "changed",
            id="scalar-value",
        ),
        pytest.param(
            "sensor_id",
            _TextSubclass("sensor-1"),
            "invalid",
            id="equal-text-subclass",
        ),
        pytest.param("engine_tick", 2, "unchanged", id="unencoded-tick-value"),
        pytest.param("engine_tick", True, "invalid", id="bool-for-int"),
        pytest.param("reporting_side", "red", "changed", id="reporting-side"),
        pytest.param(
            "observer_unit_id",
            "observer-mutated",
            "changed",
            id="observer-unit-id",
        ),
        pytest.param(
            "source_equipment_index",
            2,
            "changed",
            id="source-equipment-index",
        ),
        pytest.param(
            "source_equipment_index",
            True,
            "invalid",
            id="bool-for-u64",
        ),
        pytest.param(
            "modeled_role",
            "area_search",
            "changed",
            id="modeled-role",
        ),
        pytest.param(
            "target_kind",
            FOWTargetKind.DECOY,
            "changed",
            id="target-kind",
        ),
        pytest.param("target_id", "target-2", "changed", id="target-id"),
        pytest.param(
            "opportunity_ordinal",
            1,
            "changed",
            id="opportunity-ordinal",
        ),
        pytest.param(
            "opportunity_ordinal",
            False,
            "invalid",
            id="bool-for-u32",
        ),
        pytest.param(
            "target_kind",
            FOWTargetKind.UNIT.value,
            "invalid",
            id="raw-int-for-enum",
        ),
        pytest.param(
            "schema_version",
            True,
            "invalid",
            id="schema-version-type",
        ),
        pytest.param(
            "namespace",
            "MUTATED_NAMESPACE",
            "invalid",
            id="namespace-value",
        ),
        pytest.param(
            "namespace",
            _TextSubclass("FOW_DETECTION"),
            "unchanged",
            id="equal-namespace-subclass",
        ),
    ),
)
def test_issued_preimage_rejects_same_identity_mutated_after_issue(
    field_name: str,
    mutated_value: object,
    encoder_outcome: str,
) -> None:
    identity = _candidate(1).identity
    indexed = IndexedFOWRNG(142_004)
    initial_transcript_digest = indexed.transcript_digest_hex
    allocation = indexed.begin_interval(
        module=ModuleId.DETECTION,
        engine_tick=1,
        reporting_sides=("blue",),
    )
    decision = allocation.acquire_side("blue").issue(identity)
    issued_preimage = decision._issued_preimage(identity)
    assert issued_preimage == encode_fow_decision(identity)

    object.__setattr__(identity, field_name, mutated_value)
    if encoder_outcome == "invalid":
        with pytest.raises(IndexedRNGValidationError):
            encode_fow_decision(identity)
    else:
        mutated_preimage = encode_fow_decision(identity)
        if encoder_outcome == "unchanged":
            assert mutated_preimage == issued_preimage
        else:
            assert mutated_preimage != issued_preimage
    with pytest.raises(
        IndexedRNGValidationError,
        match="indexed decision identity changed after issuance",
    ):
        decision._issued_preimage(identity)

    with pytest.raises(IndexedRNGLifecycleError, match="not active"):
        decision._issued_preimage(identity)
    with pytest.raises(IndexedRNGLifecycleError, match="not active"):
        indexed.commit_interval(allocation)
    assert indexed.committed_interval_count == 0
    assert indexed.committed_entry_count == 0
    assert indexed.transcript_digest_hex == initial_transcript_digest


def test_issued_preimage_snapshot_does_not_retain_mutable_namespace_state() -> None:
    identity = _candidate(1).identity
    namespace = _MutableNamespace("FOW_DETECTION")
    object.__setattr__(identity, "namespace", namespace)
    indexed = IndexedFOWRNG(142_005)
    initial_transcript_digest = indexed.transcript_digest_hex
    allocation = indexed.begin_interval(
        module=ModuleId.DETECTION,
        engine_tick=1,
        reporting_sides=("blue",),
    )
    decision = allocation.acquire_side("blue").issue(identity)
    assert decision._issued_preimage(identity) == encode_fow_decision(identity)

    namespace.accepted = False
    with pytest.raises(
        IndexedRNGValidationError,
        match="indexed decision identity changed after issuance",
    ):
        decision._issued_preimage(identity)

    with pytest.raises(IndexedRNGLifecycleError, match="not active"):
        indexed.commit_interval(allocation)
    assert indexed.committed_interval_count == 0
    assert indexed.committed_entry_count == 0
    assert indexed.transcript_digest_hex == initial_transcript_digest


def test_issue_observes_custom_namespace_equality_once() -> None:
    identity = _candidate(1).identity
    namespace = _CountingNamespace("FOW_DETECTION")
    object.__setattr__(identity, "namespace", namespace)
    indexed = IndexedFOWRNG(142_006)
    allocation = indexed.begin_interval(
        module=ModuleId.DETECTION,
        engine_tick=1,
        reporting_sides=("blue",),
    )

    allocation.acquire_side("blue").issue(identity)

    assert namespace.comparisons == 1
    indexed.abort_interval(allocation)
    assert indexed.committed_interval_count == 0
    assert indexed.committed_entry_count == 0


def test_issued_preimage_detects_namespace_comparator_identity_mutation() -> None:
    identity = _candidate(1).identity
    namespace = _IssuanceMutatingNamespace("FOW_DETECTION")
    namespace.identity = identity
    object.__setattr__(identity, "namespace", namespace)
    indexed = IndexedFOWRNG(142_007)
    initial_transcript_digest = indexed.transcript_digest_hex
    allocation = indexed.begin_interval(
        module=ModuleId.DETECTION,
        engine_tick=1,
        reporting_sides=("blue",),
    )

    try:
        decision = allocation.acquire_side("blue").issue(identity)
    except IndexedRNGValidationError:
        pass
    else:
        with pytest.raises(
            IndexedRNGValidationError,
            match="indexed decision identity changed after issuance",
        ):
            decision._issued_preimage(identity)

    with pytest.raises(IndexedRNGLifecycleError, match="not active"):
        indexed.commit_interval(allocation)
    assert indexed.committed_interval_count == 0
    assert indexed.committed_entry_count == 0
    assert indexed.transcript_digest_hex == initial_transcript_digest


def test_prevalidated_fow_accumulator_matches_atomic_public_batch_exactly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial = _candidate(0, observation_time_s=0.0, engine_tick=0)
    later = (
        _candidate(
            4,
            observation_time_s=5.0,
            engine_tick=1,
            observer_position=Position(4_000.0, 0.0, 0.0),
        ),
        _candidate(
            2,
            observation_time_s=5.0,
            engine_tick=1,
            observer_position=Position(2_000.0, 0.0, 0.0),
        ),
    )
    public = _engine()
    public_initial = public.submit_sensor_detection_batch_with_outcome((initial,))
    public_outcome = public.submit_sensor_detection_batch_with_outcome(
        later,
        contact_id=public_initial.track_id,
    )
    detached_controls = tuple(_engine() for _ in range(2))
    detached_initials = tuple(
        detached.submit_sensor_detection_batch_with_outcome((initial,)) for detached in detached_controls
    )

    indexed = IndexedFOWRNG(142_002)
    allocation = indexed.begin_interval(
        module=ModuleId.DETECTION,
        engine_tick=1,
        reporting_sides=("blue",),
    )
    handle = allocation.acquire_side("blue")
    issued_preimages = {
        candidate.identity: handle.issue(candidate.identity)._issued_preimage(
            candidate.identity,
        )
        for candidate in later
    }
    expected_representative = min(
        later,
        key=lambda candidate: issued_preimages[candidate.identity],
    )

    def reject_public_batch_preparation(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("private FOW fusion called public batch preparation")

    monkeypatch.setattr(
        IntelFusionEngine,
        "_prepare_sensor_fusion_batch",
        reject_public_batch_preparation,
    )

    for detached, detached_initial, ordered_candidates in zip(
        detached_controls,
        detached_initials,
        (later, tuple(reversed(later))),
        strict=True,
    ):
        first = ordered_candidates[0]
        validated = detached._validate_prevalidated_fow_candidate(
            first,
            decision_preimage=issued_preimages[first.identity],
        )
        accumulator = _FOWFusionAccumulator.from_candidate(
            validated,
            first,
            issued_preimages[first.identity],
        )
        for candidate in ordered_candidates[1:]:
            validated = detached._validate_prevalidated_fow_candidate(
                candidate,
                decision_preimage=issued_preimages[candidate.identity],
            )
            assert validated.group_key == accumulator.representative.group_key
            accumulator.accumulate(
                validated,
                candidate,
                issued_preimages[candidate.identity],
            )

        assert accumulator.candidate_count == 2
        assert accumulator.representative.identity is expected_representative.identity
        assert accumulator.candidate_ledger[accumulator.representative_key[1]] is expected_representative
        assert tuple(sorted(accumulator.candidate_ledger)) == tuple(
            sorted(issued_preimages.values()),
        )
        prepared = detached._materialize_validated_sensor_fusion_candidate(
            accumulator.representative,
        )
        detached_outcome = detached._submit_prevalidated_detached_sensor_fusion_with_outcome(
            prepared,
            candidate_count=accumulator.candidate_count,
            contact_id=detached_initial.track_id,
        )

        assert detached_outcome == public_outcome
        assert detached.get_state() == public.get_state()

    indexed.abort_interval(allocation)


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    (
        pytest.param("snr_db", float("nan"), id="snr"),
        pytest.param("bearing_deg", float("inf"), id="bearing"),
    ),
)
def test_malformed_nonrepresentative_rejects_before_private_submission(
    monkeypatch: pytest.MonkeyPatch,
    field_name: str,
    invalid_value: float,
) -> None:
    initial = _candidate(0, observation_time_s=0.0, engine_tick=0)
    representative = _candidate(
        1,
        probability=1.0,
        range_m=1.0,
        observation_time_s=5.0,
        engine_tick=1,
    )
    nonrepresentative = _candidate(
        2,
        probability=0.5,
        range_m=100.0,
        observation_time_s=5.0,
        engine_tick=1,
    )
    malformed = replace(
        nonrepresentative,
        detection=nonrepresentative.detection._replace(
            **{field_name: invalid_value},
        ),
    )

    public = _engine()
    public_initial = public.submit_sensor_detection_batch_with_outcome((initial,))
    public_before = public.get_state()
    with pytest.raises(
        ValueError,
        match=rf"detection\.{field_name} must be a finite number",
    ):
        public.submit_sensor_detection_batch_with_outcome(
            (representative, malformed),
            contact_id=public_initial.track_id,
        )
    assert public.get_state() == public_before

    private = _engine()
    private_initial = private.submit_sensor_detection_batch_with_outcome((initial,))
    private_before = private.get_state()
    indexed = IndexedFOWRNG(142_003)
    allocation = indexed.begin_interval(
        module=ModuleId.DETECTION,
        engine_tick=1,
        reporting_sides=("blue",),
    )
    handle = allocation.acquire_side("blue")
    representative_decision = handle.issue(representative.identity)
    representative_preimage = representative_decision._issued_preimage(
        representative.identity,
    )
    malformed_decision = handle.issue(malformed.identity)
    malformed_preimage = malformed_decision._issued_preimage(
        malformed.identity,
    )
    validated_representative = private._validate_prevalidated_fow_candidate(
        representative,
        decision_preimage=representative_preimage,
    )
    validated_nonrepresentative_control = private._validate_prevalidated_fow_candidate(
        nonrepresentative,
        decision_preimage=malformed_preimage,
    )
    assert validated_representative.effective_variance_m2 < validated_nonrepresentative_control.effective_variance_m2
    accumulator = _FOWFusionAccumulator.from_candidate(
        validated_representative,
        representative,
        representative_preimage,
    )
    private_submit_called = False

    def unexpected_private_submit(*_args: object, **_kwargs: object) -> None:
        nonlocal private_submit_called
        private_submit_called = True
        raise AssertionError("malformed nonrepresentative reached private submit")

    monkeypatch.setattr(
        IntelFusionEngine,
        "_submit_prevalidated_detached_sensor_fusion_with_outcome",
        unexpected_private_submit,
    )

    with pytest.raises(
        ValueError,
        match=rf"detection\.{field_name} must be a finite number",
    ):
        validated_nonrepresentative = private._validate_prevalidated_fow_candidate(
            malformed,
            decision_preimage=malformed_preimage,
        )
        accumulator.accumulate(
            validated_nonrepresentative,
            malformed,
            malformed_preimage,
        )
        prepared = private._materialize_validated_sensor_fusion_candidate(
            accumulator.representative,
        )
        private._submit_prevalidated_detached_sensor_fusion_with_outcome(
            prepared,
            candidate_count=accumulator.candidate_count,
            contact_id=private_initial.track_id,
        )

    assert private_submit_called is False
    assert accumulator.candidate_count == 1
    assert tuple(accumulator.candidate_ledger.values()) == (representative,)
    assert private.get_state() == private_before
    indexed.abort_interval(allocation)


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
