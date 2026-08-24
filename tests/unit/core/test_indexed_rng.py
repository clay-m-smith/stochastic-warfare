"""Focused Phase 118 tests for identity-addressed FOW randomness."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import math

import numpy as np
import pytest

from stochastic_warfare.core.indexed_rng import (
    FOWDecisionIdentity,
    FOWDecisionLane,
    FOWTargetKind,
    INDEXED_FOW_NAMESPACE,
    IndexedFOWRNG,
    IndexedRNGLifecycleError,
    IndexedRNGValidationError,
    _ReusablePhilox,
    derive_indexed_fow_key,
    encode_fow_decision,
    raw_u64_to_uniform,
)
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId


DIAGNOSTIC_SEED = 118


def _identity(
    *,
    tick: int = 9,
    side: str = "blue",
    observer: str = "observer-1",
    target: str = "target-7",
) -> FOWDecisionIdentity:
    return FOWDecisionIdentity(
        engine_tick=tick,
        reporting_side=side,
        observer_unit_id=observer,
        source_equipment_index=2,
        sensor_id="radar-x",
        modeled_role="search",
        target_kind=FOWTargetKind.UNIT,
        target_id=target,
    )


def _complete_one(
    manager: RNGManager,
    identity: FOWDecisionIdentity,
) -> tuple[tuple[int, int, int, int], bytes]:
    allocation = manager.begin_fow_detection_interval(
        identity.engine_tick,
        (identity.reporting_side,),
    )
    handle = allocation.acquire_side(identity.reporting_side)
    decision = handle.issue(identity)
    decision.detection_uniform(probability=1.0)
    handle.complete()
    record = manager.commit_fow_detection_interval(allocation)
    return decision.raw_lanes, record.record_bytes


def test_exact_key_decision_counter_and_philox_known_answer() -> None:
    key, preimage, preimage_digest = derive_indexed_fow_key(DIAGNOSTIC_SEED)
    identity = _identity()
    decision_preimage = encode_fow_decision(identity)

    assert preimage.hex() == (
        "73746f636861737469632d776172666172652f696e64657865642d7068696c6f782d6b65792f7631000000000176"
    )
    assert key.hex() == "7c674f12a6f97085cd5bf3558f173219"
    assert preimage_digest.hex() == ("7c674f12a6f97085cd5bf3558f17321940d1cea6ec67a3cab7e800655797d2be")
    assert decision_preimage.hex() == (
        "73746f636861737469632d776172666172652f666f772d6465636973696f6e"
        "2f763100000100000004626c75650000000a6f627365727665722d31000000"
        "00000000020000000772616461722d78000000067365617263680100000008"
        "7461726765742d3700000000"
    )

    manager = RNGManager(DIAGNOSTIC_SEED)
    raw_lanes, _record = _complete_one(manager, identity)
    assert raw_lanes == (
        5_538_687_799_951_155_000,
        15_927_348_875_832_564_203,
        14_149_535_250_555_364_766,
        7_494_692_077_604_261_356,
    )


def test_reusable_philox_matches_fresh_full_state_nonmonotonically() -> None:
    key = bytes.fromhex("7c674f12a6f97085cd5bf3558f173219")
    reusable = _ReusablePhilox(key)
    counters = (
        bytes.fromhex("f2" * 24 + "0000000000000009"),
        bytes.fromhex("01" * 24 + "ffffffffffffffff"),
        bytes.fromhex("80" + "00" * 31),
        bytes.fromhex("f2" * 24 + "0000000000000009"),
    )
    for counter in counters:
        actual_raw = reusable.draw_block(counter)
        fresh = np.random.Philox(
            counter=int.from_bytes(counter, "big"),
            key=int.from_bytes(key, "big"),
        )
        expected_raw = tuple(int(value) for value in fresh.random_raw(4))
        assert actual_raw == expected_raw
        actual_state = reusable.get_state()
        expected_state = fresh.state
        assert actual_state["bit_generator"] == expected_state["bit_generator"]
        for field in ("counter", "key"):
            np.testing.assert_array_equal(
                actual_state["state"][field],
                expected_state["state"][field],
            )
        np.testing.assert_array_equal(actual_state["buffer"], expected_state["buffer"])
        assert actual_state["buffer_pos"] == expected_state["buffer_pos"]
        assert actual_state["has_uint32"] == expected_state["has_uint32"]
        assert actual_state["uinteger"] == expected_state["uinteger"]


def test_raw_lane_conversion_uses_exact_binary64_rule() -> None:
    assert raw_u64_to_uniform(0) == 0.0
    assert raw_u64_to_uniform((1 << 64) - 1) == 1.0 - 2.0**-53
    with pytest.raises(IndexedRNGValidationError):
        raw_u64_to_uniform(True)
    with pytest.raises(IndexedRNGValidationError):
        raw_u64_to_uniform(1 << 64)


def test_indexed_decisions_do_not_advance_conventional_detection_stream() -> None:
    manager = RNGManager(DIAGNOSTIC_SEED)
    before = deepcopy(manager.get_state()["streams"][ModuleId.DETECTION.value])
    _complete_one(manager, _identity())
    after = manager.get_state()["streams"][ModuleId.DETECTION.value]
    assert after == before


def test_skipped_prior_identity_does_not_phase_shift_common_identity() -> None:
    sparse = RNGManager(DIAGNOSTIC_SEED)
    dense = RNGManager(DIAGNOSTIC_SEED)
    sparse_allocation = sparse.begin_fow_detection_interval(9, ("blue",))
    dense_allocation = dense.begin_fow_detection_interval(9, ("blue",))
    sparse_handle = sparse_allocation.acquire_side("blue")
    dense_handle = dense_allocation.acquire_side("blue")

    omitted = dense_handle.issue(_identity(target="earlier-target"))
    omitted.detection_uniform(probability=1.0)
    sparse_common = sparse_handle.issue(_identity(target="common-target"))
    dense_common = dense_handle.issue(_identity(target="common-target"))
    sparse_common.detection_uniform(probability=1.0)
    dense_common.detection_uniform(probability=1.0)

    assert sparse_common.counter == dense_common.counter
    assert sparse_common.raw_lanes == dense_common.raw_lanes
    sparse_handle.complete()
    dense_handle.complete()
    sparse.commit_fow_detection_interval(sparse_allocation)
    dense.commit_fow_detection_interval(dense_allocation)


def test_transcript_record_and_fold_follow_exact_codec() -> None:
    manager = RNGManager(DIAGNOSTIC_SEED)
    assert manager.latest_fow_detection_interval_record is None
    allocation = manager.begin_fow_detection_interval(9, ("blue", "red"))
    blue = allocation.acquire_side("blue")
    red = allocation.acquire_side("red")
    blue_decision = blue.issue(_identity())
    red_decision = red.issue(_identity(side="red", observer="observer-2"))
    blue_decision.detection_uniform(probability=1.0)
    red_decision.detection_uniform(probability=1.0)
    red_decision.identification_uniform(detection_succeeded=True)
    blue.complete()
    red.complete()
    interval = manager.commit_fow_detection_interval(allocation)
    assert manager.latest_fow_detection_interval_record is interval

    expected_record = b"".join(
        (
            b"stochastic-warfare/fow-transcript-record/v1\x00",
            (1).to_bytes(2, "big"),
            (9).to_bytes(8, "big"),
            (2).to_bytes(4, "big"),
            (4).to_bytes(4, "big"),
            b"blue",
            (3).to_bytes(4, "big"),
            b"red",
            (2).to_bytes(8, "big"),
            (4).to_bytes(4, "big"),
            b"blue",
            blue_decision.counter,
            bytes((1,)),
            (3).to_bytes(4, "big"),
            b"red",
            red_decision.counter,
            bytes((3,)),
        )
    )
    initial = hashlib.sha256(b"stochastic-warfare/fow-transcript/v1\x00").digest()
    expected_digest = hashlib.sha256(
        b"stochastic-warfare/fow-transcript-fold/v1\x00"
        + initial
        + len(expected_record).to_bytes(8, "big")
        + expected_record
    ).hexdigest()
    assert interval.record_bytes == expected_record
    assert interval.previous_digest_hex == initial.hex()
    assert interval.transcript_digest_hex == expected_digest
    assert interval.committed_interval_count == 1
    assert interval.committed_entry_count == 2
    assert tuple(entry.consumed_lane_mask for entry in interval.entries) == (
        1,
        3,
    )
    assert tuple((adjudication.probability, adjudication.detected) for adjudication in interval.adjudications) == (
        (1.0, True),
        (1.0, True),
    )


def test_detection_adjudication_uses_the_exact_lane_zero_threshold() -> None:
    for probability_delta, expected in ((0.0, False), (math.ulp(0.5), True)):
        manager = RNGManager(DIAGNOSTIC_SEED)
        allocation = manager.begin_fow_detection_interval(9, ("blue",))
        handle = allocation.acquire_side("blue")
        decision = handle.issue(_identity())
        uniform = raw_u64_to_uniform(decision.raw_lanes[0])
        probability = uniform + probability_delta

        assert decision.detection_uniform(probability=probability) == uniform
        assert decision.detection_succeeded is expected
        handle.complete()
        record = manager.commit_fow_detection_interval(allocation)

        assert len(record.adjudications) == 1
        assert record.adjudications[0].probability == probability
        assert record.adjudications[0].detected is expected


def test_missing_or_false_detection_adjudication_poisons_interval() -> None:
    missing = RNGManager(DIAGNOSTIC_SEED)
    allocation = missing.begin_fow_detection_interval(9, ("blue",))
    handle = allocation.acquire_side("blue")
    decision = handle.issue(_identity())
    decision.consume_lane(FOWDecisionLane.DETECTION)
    with pytest.raises(IndexedRNGLifecycleError, match="retain"):
        handle.complete()
    with pytest.raises(IndexedRNGLifecycleError, match="poisoned"):
        missing.get_state()

    false = RNGManager(DIAGNOSTIC_SEED)
    allocation = false.begin_fow_detection_interval(9, ("blue",))
    decision = allocation.acquire_side("blue").issue(_identity())
    decision.detection_uniform(probability=0.0)
    with pytest.raises(IndexedRNGLifecycleError, match="disagrees"):
        decision.identification_uniform(detection_succeeded=True)
    with pytest.raises(IndexedRNGLifecycleError, match="poisoned"):
        false.get_state()


@pytest.mark.parametrize(
    "probability",
    (True, -math.ulp(0.0), math.nextafter(1.0, math.inf), math.inf, math.nan),
)
def test_invalid_detection_probability_poisons_interval(
    probability: object,
) -> None:
    manager = RNGManager(DIAGNOSTIC_SEED)
    allocation = manager.begin_fow_detection_interval(9, ("blue",))
    decision = allocation.acquire_side("blue").issue(_identity())

    with pytest.raises(IndexedRNGValidationError, match="probability"):
        decision.detection_uniform(probability=probability)  # type: ignore[arg-type]
    with pytest.raises(IndexedRNGLifecycleError, match="poisoned"):
        manager.get_state()


def test_commit_revalidates_detection_adjudication_against_raw_lane() -> None:
    manager = RNGManager(DIAGNOSTIC_SEED)
    allocation = manager.begin_fow_detection_interval(9, ("blue",))
    handle = allocation.acquire_side("blue")
    decision = handle.issue(_identity())
    decision.detection_uniform(probability=1.0)
    assert decision._adjudication is not None
    decision._adjudication = replace(
        decision._adjudication,
        detected=False,
    )
    handle.complete()

    with pytest.raises(IndexedRNGLifecycleError, match="lane zero"):
        manager.commit_fow_detection_interval(allocation)
    with pytest.raises(IndexedRNGLifecycleError, match="poisoned"):
        manager.get_state()


def test_prepared_or_aborted_interval_never_replaces_latest_committed_record() -> None:
    manager = RNGManager(DIAGNOSTIC_SEED)
    first_identity = _identity(tick=9, target="first-target")
    first_allocation = manager.begin_fow_detection_interval(9, ("blue",))
    first_handle = first_allocation.acquire_side("blue")
    first_handle.issue(first_identity).detection_uniform(probability=1.0)
    first_handle.complete()
    first_record = manager.commit_fow_detection_interval(first_allocation)
    committed_state = manager.get_state()["indexed_fow"]

    second_identity = _identity(tick=10, target="second-target")
    second_allocation = manager.begin_fow_detection_interval(10, ("blue",))
    second_handle = second_allocation.acquire_side("blue")
    second_handle.issue(second_identity).detection_uniform(probability=1.0)
    second_handle.complete()
    prepared = manager.prepare_fow_detection_interval_commit(
        second_allocation,
    )

    assert manager.latest_fow_detection_interval_record is first_record
    assert prepared.record.engine_tick == 10
    assert prepared.record.committed_interval_count == 2
    with pytest.raises(IndexedRNGLifecycleError, match="active"):
        manager.get_state()

    manager.abort_fow_detection_interval(second_allocation)

    assert manager.latest_fow_detection_interval_record is first_record
    assert manager.indexed_fow_committed_interval_count == 1
    assert manager.indexed_fow_committed_entry_count == 1
    with pytest.raises(IndexedRNGLifecycleError, match="poisoned"):
        manager.get_state()
    assert committed_state["transcript"]["committed_interval_count"] == 1


def test_prepared_interval_freezes_side_issuance_and_poison_rejects_commit() -> None:
    manager = RNGManager(DIAGNOSTIC_SEED)
    allocation = manager.begin_fow_detection_interval(9, ("blue",))
    handle = allocation.acquire_side("blue")
    handle.issue(_identity()).detection_uniform(probability=1.0)
    handle.complete()
    prepared = manager.prepare_fow_detection_interval_commit(allocation)

    with pytest.raises(IndexedRNGLifecycleError, match="not active"):
        handle.issue(_identity(target="too-late"))
    with pytest.raises(IndexedRNGLifecycleError, match="stale|inactive"):
        manager.commit_prepared_fow_detection_interval(prepared)
    assert manager.indexed_fow_committed_interval_count == 0
    assert manager.latest_fow_detection_interval_record is None


def test_allocation_cannot_bypass_manager_owned_commit_publication() -> None:
    manager = RNGManager(DIAGNOSTIC_SEED)
    allocation = manager.begin_fow_detection_interval(9, ("blue",))
    allocation.acquire_side("blue").complete()

    assert not hasattr(allocation, "commit")

    record = manager.commit_fow_detection_interval(allocation)

    assert manager.latest_fow_detection_interval_record is record
    assert manager.indexed_fow_committed_interval_count == 1


@pytest.mark.parametrize("prepared", (False, True))
def test_reset_rejects_live_indexed_allocation_before_any_mutation(
    prepared: bool,
) -> None:
    manager = RNGManager(DIAGNOSTIC_SEED)
    first = manager.begin_fow_detection_interval(8, ("blue",))
    first.acquire_side("blue").complete()
    previous_record = manager.commit_fow_detection_interval(first)
    before = manager.get_state()
    allocation = manager.begin_fow_detection_interval(9, ("blue",))
    allocation.acquire_side("blue").complete()
    plan = (
        manager.prepare_fow_detection_interval_commit(allocation)
        if prepared
        else None
    )

    with pytest.raises(
        IndexedRNGLifecycleError,
        match="active or prepared indexed allocation",
    ):
        manager.reset(999)

    assert manager.latest_fow_detection_interval_record is previous_record

    record = (
        manager.commit_prepared_fow_detection_interval(plan)
        if plan is not None
        else manager.commit_fow_detection_interval(allocation)
    )
    after = manager.get_state()
    assert after["master_seed"] == DIAGNOSTIC_SEED
    assert after["streams"] == before["streams"]
    assert manager.latest_fow_detection_interval_record is record
    assert manager.indexed_fow_committed_interval_count == 2

    manager.reset(999)
    reset_state = manager.get_state()
    assert reset_state["master_seed"] == 999
    assert manager.latest_fow_detection_interval_record is None
    assert manager.indexed_fow_committed_interval_count == 0


def test_abort_then_reset_recovers_without_reactivating_old_allocation() -> None:
    manager = RNGManager(DIAGNOSTIC_SEED)
    allocation = manager.begin_fow_detection_interval(9, ("blue",))
    allocation.acquire_side("blue").complete()
    manager.abort_fow_detection_interval(allocation)

    manager.reset(999)
    reset_state = manager.get_state()

    with pytest.raises(IndexedRNGLifecycleError, match="different RNG manager"):
        manager.commit_fow_detection_interval(allocation)
    assert manager.get_state() == reset_state

    retry = manager.begin_fow_detection_interval(9, ("blue",))
    retry.acquire_side("blue").complete()
    record = manager.commit_fow_detection_interval(retry)
    assert manager.latest_fow_detection_interval_record is record
    assert manager.indexed_fow_committed_interval_count == 1


@pytest.mark.parametrize(
    "sides",
    [
        ("red", "blue"),
        ("blue", "blue"),
        (),
        "blue",
    ],
)
def test_reporting_side_set_must_be_complete_unique_and_ordered(
    sides: object,
) -> None:
    manager = RNGManager(DIAGNOSTIC_SEED)
    with pytest.raises(IndexedRNGValidationError):
        manager.begin_fow_detection_interval(9, sides)  # type: ignore[arg-type]
    assert manager.get_state()["indexed_fow"]


def test_wrong_module_owner_tick_side_and_extra_side_reject() -> None:
    wrong_module = RNGManager(DIAGNOSTIC_SEED)
    with pytest.raises(IndexedRNGValidationError, match="DETECTION"):
        wrong_module.begin_fow_detection_interval(
            9,
            ("blue",),
            module=ModuleId.COMBAT,
        )

    owner = RNGManager(DIAGNOSTIC_SEED)
    other = RNGManager(DIAGNOSTIC_SEED)
    allocation = owner.begin_fow_detection_interval(9, ("blue",))
    with pytest.raises(IndexedRNGLifecycleError, match="different"):
        other.commit_fow_detection_interval(allocation)
    with pytest.raises(IndexedRNGLifecycleError, match="poisoned"):
        owner.get_state()

    for bad_identity in (_identity(tick=10), _identity(side="red")):
        manager = RNGManager(DIAGNOSTIC_SEED)
        allocation = manager.begin_fow_detection_interval(9, ("blue",))
        handle = allocation.acquire_side("blue")
        with pytest.raises(IndexedRNGValidationError):
            handle.issue(bad_identity)
        with pytest.raises(IndexedRNGLifecycleError, match="poisoned"):
            manager.get_state()

    manager = RNGManager(DIAGNOSTIC_SEED)
    allocation = manager.begin_fow_detection_interval(9, ("blue",))
    with pytest.raises(IndexedRNGValidationError, match="complete side set"):
        allocation.acquire_side("red")


def test_missing_duplicate_identity_and_handle_reuse_reject() -> None:
    missing = RNGManager(DIAGNOSTIC_SEED)
    allocation = missing.begin_fow_detection_interval(9, ("blue", "red"))
    blue = allocation.acquire_side("blue")
    blue.complete()
    with pytest.raises(IndexedRNGLifecycleError, match="complete ordered"):
        missing.commit_fow_detection_interval(allocation)
    with pytest.raises(IndexedRNGLifecycleError, match="poisoned"):
        missing.get_state()

    duplicate = RNGManager(DIAGNOSTIC_SEED)
    allocation = duplicate.begin_fow_detection_interval(9, ("blue",))
    handle = allocation.acquire_side("blue")
    first = handle.issue(_identity())
    first.detection_uniform(probability=1.0)
    with pytest.raises(IndexedRNGLifecycleError, match="more than once"):
        handle.issue(_identity())

    reused = RNGManager(DIAGNOSTIC_SEED)
    allocation = reused.begin_fow_detection_interval(9, ("blue",))
    handle = allocation.acquire_side("blue")
    handle.complete()
    reused.commit_fow_detection_interval(allocation)
    with pytest.raises(IndexedRNGLifecycleError, match="not active"):
        handle.issue(_identity())


@pytest.mark.parametrize(
    "misuse",
    ["identification_first", "false_identification", "duplicate_detection"],
)
def test_lane_misuse_poison_rejects_checkpoint(misuse: str) -> None:
    manager = RNGManager(DIAGNOSTIC_SEED)
    allocation = manager.begin_fow_detection_interval(9, ("blue",))
    decision = allocation.acquire_side("blue").issue(_identity())
    with pytest.raises((IndexedRNGLifecycleError, IndexedRNGValidationError)):
        if misuse == "identification_first":
            decision.identification_uniform(detection_succeeded=True)
        elif misuse == "false_identification":
            decision.detection_uniform(probability=1.0)
            decision.identification_uniform(detection_succeeded=False)
        else:
            decision.detection_uniform(probability=1.0)
            decision.detection_uniform(probability=1.0)
    with pytest.raises(IndexedRNGLifecycleError, match="poisoned"):
        manager.get_state()


def test_reserved_or_untyped_lane_rejects() -> None:
    manager = RNGManager(DIAGNOSTIC_SEED)
    allocation = manager.begin_fow_detection_interval(9, ("blue",))
    decision = allocation.acquire_side("blue").issue(_identity())
    with pytest.raises(IndexedRNGValidationError, match="exact"):
        decision.consume_lane(2)  # type: ignore[arg-type]


class _CollidingIndexedFOWRNG(IndexedFOWRNG):
    @staticmethod
    def _decision_digest(preimage: bytes) -> bytes:
        del preimage
        return bytes(24)


def test_distinct_preimage_collision_is_rejected() -> None:
    indexed = _CollidingIndexedFOWRNG(DIAGNOSTIC_SEED)
    allocation = indexed.begin_interval(
        module=ModuleId.DETECTION,
        engine_tick=9,
        reporting_sides=("blue",),
    )
    handle = allocation.acquire_side("blue")
    first = handle.issue(_identity(target="one"))
    first.detection_uniform(probability=1.0)
    with pytest.raises(IndexedRNGLifecycleError, match="collided"):
        handle.issue(_identity(target="two"))
    with pytest.raises(IndexedRNGLifecycleError, match="poisoned"):
        indexed.get_state()


def test_active_and_aborted_allocations_reject_checkpoint() -> None:
    manager = RNGManager(DIAGNOSTIC_SEED)
    allocation = manager.begin_fow_detection_interval(9, ("blue",))
    with pytest.raises(IndexedRNGLifecycleError, match="active"):
        manager.get_state()
    allocation.abort()
    with pytest.raises(IndexedRNGLifecycleError, match="poisoned"):
        manager.get_state()


def test_state_restore_is_strict_rederived_atomic_and_preserves_stream_owner() -> None:
    manager = RNGManager(DIAGNOSTIC_SEED)
    detection_stream = manager.get_stream(ModuleId.DETECTION)
    _complete_one(manager, _identity())
    state = manager.get_state()
    expected_digest = manager.indexed_fow_transcript_digest_hex
    manager.get_stream(ModuleId.COMBAT).random(5)
    manager.set_state(deepcopy(state))

    assert manager.get_stream(ModuleId.DETECTION) is detection_stream
    assert manager.indexed_fow_transcript_digest_hex == expected_digest
    assert manager.indexed_fow_committed_interval_count == 1
    assert manager.indexed_fow_committed_entry_count == 1

    for path in ("key_hex", "key_preimage_sha256", "namespace"):
        corrupted = deepcopy(state)
        corrupted["indexed_fow"][path] = "0" * 32
        before = manager.get_state()
        with pytest.raises(IndexedRNGValidationError):
            manager.set_state(corrupted)
        assert manager.get_state() == before


def test_incomplete_evidence_bit_is_monotonic_across_commits_and_restore() -> None:
    manager = RNGManager(DIAGNOSTIC_SEED)
    manager.mark_indexed_fow_history_incomplete()
    _complete_one(manager, _identity())
    state = manager.get_state()
    assert manager.indexed_fow_complete_from_tick_zero is False
    assert state["indexed_fow"]["complete_from_tick_zero"] is False

    restored = RNGManager(DIAGNOSTIC_SEED)
    restored.set_state(state)
    _complete_one(restored, _identity(tick=10))
    assert restored.indexed_fow_complete_from_tick_zero is False


def test_exact_identity_rejects_wrong_schema_namespace_and_integer_types() -> None:
    valid = _identity()
    invalid = (
        replace(valid, schema_version=2),
        replace(valid, namespace="other"),
        replace(valid, engine_tick=True),
        replace(valid, target_kind=1),  # type: ignore[arg-type]
    )
    for identity in invalid:
        with pytest.raises(IndexedRNGValidationError):
            encode_fow_decision(identity)


def test_namespace_literal_is_frozen() -> None:
    assert INDEXED_FOW_NAMESPACE == "FOW_DETECTION"
    assert FOWDecisionLane.DETECTION.value == 0
    assert FOWDecisionLane.IDENTIFICATION.value == 1
