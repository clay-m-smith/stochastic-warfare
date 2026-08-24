"""Production-path red proof for Phase 118 receipts and checkpoints."""

from __future__ import annotations

import copy
from collections import Counter
from dataclasses import replace
import json
import math
from pathlib import Path
from typing import Any, Callable, NoReturn

import pytest

from stochastic_warfare.c2.ai.assessment import (
    AssessmentRating,
    SituationAssessment,
)
from stochastic_warfare.simulation.runtime import (
    AnalysisVariant,
    RuntimeSession,
    SimulationRuntimeFactory,
)
from stochastic_warfare.simulation.performance_flags import (
    LOD_RUNTIME_COMPATIBILITY_DEFAULTS,
    PerformanceExecutionReceipt,
)


ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data"
SCENARIO = DATA_DIR / "scenarios" / "calibration_air_ground" / "scenario.yaml"
DIAGNOSTIC_SEED = 118
CONTROL_PATCH = {
    "enable_detection_culling": False,
    "enable_scan_scheduling": False,
    "enable_lod": False,
    "enable_soa": False,
    "enable_parallel_detection": False,
}
UNSUPPORTED_MODEL_CONTROLS = (
    "enable_scan_scheduling",
    "enable_lod",
)
UNSUPPORTED_LOD_TUNING = tuple(
    (field_name, default_value + 1)
    for field_name, default_value in LOD_RUNTIME_COMPATIBILITY_DEFAULTS.items()
)


class _InjectedTacticalBaseFault(BaseException):
    """Deliberate non-Exception fault for fail-closed interval coverage."""


def _build_session(
    calibration_patch: dict[str, Any] | None = None,
    *,
    record_events: bool = False,
) -> RuntimeSession:
    effective_patch = {
        **CONTROL_PATCH,
        **(calibration_patch or {}),
    }
    prepared = SimulationRuntimeFactory().prepare(
        SCENARIO,
        DATA_DIR,
        (
            AnalysisVariant(
                variant_id="phase118-receipt-checkpoint-red",
                calibration_patch=effective_patch,
            ),
        ),
    )
    return prepared.build(
        "phase118-receipt-checkpoint-red",
        seed=DIAGNOSTIC_SEED,
        max_ticks=4,
        record_events=record_events,
        strict_mode=True,
    )


def _as_started_versionless(
    checkpoint: dict[str, Any],
) -> dict[str, Any]:
    """Translate a started format-118 checkpoint to the bounded legacy path."""
    legacy = copy.deepcopy(checkpoint)
    assert legacy.pop("checkpoint_version") == 118
    context = legacy["context"]
    context["rng"].pop("indexed_fow")
    context.pop("era_runtime_contract")
    context["planning_engine"].pop("checkpoint_schema")
    fog_state = context["fog_of_war"]
    fog_state.pop("cadence")
    fog_state.pop("scan_counts")
    fog_state.pop("observer_track_supports")

    morale_runtime = context.pop("morale_runtime")
    assert morale_runtime["suspended_archives"] == {}
    active_records = morale_runtime["active_records"]
    morale_rng = copy.deepcopy(context["rng"]["streams"]["morale"])
    context["morale_states"] = {unit_id: record["current_state"] for unit_id, record in active_records.items()}
    context["morale_machine"] = {
        "unit_states": {
            unit_id: {
                "current_state": record["current_state"],
                "transition_cooldown_s": 0.0,
                "last_transition_time": (
                    -1e9 if record["last_transition_time_s"] is None else record["last_transition_time_s"]
                ),
            }
            for unit_id, record in active_records.items()
        },
        "rng_state": copy.deepcopy(morale_rng),
    }
    rout_state = context.get("rout_engine")
    if isinstance(rout_state, dict):
        rout_state["rng_state"] = copy.deepcopy(morale_rng)

    legacy["battle"].pop("deferred_ooda_schema")
    legacy["battle"].pop("performance_execution_receipt")
    legacy["battle"].pop("fow_observer_unit_ids")
    return legacy


def _reject_json_constant(value: str) -> NoReturn:
    raise ValueError(f"non-finite JSON constant: {value}")


def _canonical_checkpoint_bytes(checkpoint: dict[str, Any]) -> bytes:
    """Encode one finite checkpoint mutation with production ordering."""
    return json.dumps(
        checkpoint,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _cache_assessment(
    session: RuntimeSession,
    *,
    force_ratio: float,
    force_ratio_rating: AssessmentRating,
) -> tuple[str, SituationAssessment]:
    """Install one typed assessment at a valid runtime unit/time identity."""
    unit_id = min(unit.entity_id for unit in session.context.all_units())
    assessment = SituationAssessment(
        unit_id=unit_id,
        timestamp=session.context.clock.current_time,
        force_ratio=force_ratio,
        force_ratio_rating=force_ratio_rating,
        terrain_advantage=0.0,
        terrain_rating=AssessmentRating.NEUTRAL,
        supply_level=1.0,
        supply_rating=AssessmentRating.VERY_FAVORABLE,
        morale_level=1.0,
        morale_rating=AssessmentRating.VERY_FAVORABLE,
        intel_quality=0.0,
        intel_rating=AssessmentRating.VERY_UNFAVORABLE,
        environmental_rating=AssessmentRating.NEUTRAL,
        c2_effectiveness=1.0,
        c2_rating=AssessmentRating.VERY_FAVORABLE,
        overall_rating=AssessmentRating.FAVORABLE,
        confidence=1.0,
        opportunities=(),
        threats=(),
    )
    session.engine.battle_manager._cached_assessments[unit_id] = assessment
    return unit_id, assessment


def test_runtime_exposes_committed_production_execution_receipt() -> None:
    session = _build_session()

    assert session.step() is False

    receipt = session.performance_execution_receipt()
    assert receipt.complete_from_tick_zero is True
    assert receipt.tactical_interval_microseconds == 5_000_000
    assert receipt.tactical_intervals == 1
    assert receipt.tactical_duration_microseconds == 5_000_000
    assert receipt.fow.side_cycles == 2


def test_engine_baseexception_fault_poisons_active_receipt_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _build_session()
    battle = session.engine.battle_manager
    accumulator = battle._performance_receipts
    baseline = accumulator._receipt

    def _fail_after_receipt_begin(*_args: object, **_kwargs: object) -> NoReturn:
        raise _InjectedTacticalBaseFault("injected fatal tactical fault")

    monkeypatch.setattr(
        battle,
        "prepare_tactical_interval",
        _fail_after_receipt_begin,
    )
    with pytest.raises(
        _InjectedTacticalBaseFault,
        match="injected fatal tactical fault",
    ):
        session.step()

    assert accumulator._receipt is baseline
    assert accumulator.poisoned is True
    assert accumulator.poison_reason == ("production tactical interval failed: _InjectedTacticalBaseFault")
    assert battle._performance_transaction is None
    with pytest.raises(RuntimeError, match="poisoned"):
        session.performance_execution_receipt()
    with pytest.raises(RuntimeError, match="poisoned"):
        session.engine.checkpoint()


def test_initial_receipt_stage_baseexception_is_internally_poisoned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _build_session()
    battle = session.engine.battle_manager
    accumulator = battle._performance_receipts

    def _fail_initial_stage(*_args: object, **_kwargs: object) -> NoReturn:
        raise _InjectedTacticalBaseFault("injected initial receipt fault")

    monkeypatch.setattr(accumulator, "stage", _fail_initial_stage)
    with pytest.raises(
        _InjectedTacticalBaseFault,
        match="injected initial receipt fault",
    ):
        battle.begin_performance_interval(dt_seconds=5.0)

    assert accumulator.poisoned is True
    assert accumulator.poison_reason == ("initial performance receipt staging failed: _InjectedTacticalBaseFault")
    assert battle._performance_transaction is None


def test_final_receipt_reconciliation_baseexception_closes_and_poisons(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _build_session()
    battle = session.engine.battle_manager
    accumulator = battle._performance_receipts
    baseline = accumulator._receipt

    original_from_delta = PerformanceExecutionReceipt.from_delta
    calls = 0

    def _fail_reconciliation(
        _cls: type[PerformanceExecutionReceipt],
        *args: object,
        **kwargs: object,
    ) -> PerformanceExecutionReceipt:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise _InjectedTacticalBaseFault(
                "injected final reconciliation fault",
            )
        return original_from_delta(*args, **kwargs)

    monkeypatch.setattr(
        PerformanceExecutionReceipt,
        "from_delta",
        classmethod(_fail_reconciliation),
    )
    with pytest.raises(
        _InjectedTacticalBaseFault,
        match="injected final reconciliation fault",
    ):
        session.step()

    assert accumulator._receipt is baseline
    assert calls == 1
    assert accumulator.poisoned is True
    assert accumulator.poison_reason == ("receipt reconciliation failed: _InjectedTacticalBaseFault")
    assert accumulator.transaction_active is False
    assert battle._performance_transaction is None
    with pytest.raises(RuntimeError, match="poisoned"):
        battle.begin_performance_interval(dt_seconds=5.0)
    with pytest.raises(RuntimeError, match="poisoned"):
        session.performance_execution_receipt()
    with pytest.raises(RuntimeError, match="poisoned"):
        session.engine.checkpoint()


def test_production_checkpoint_uses_phase118_format() -> None:
    session = _build_session()
    assert session.step() is False

    checkpoint = json.loads(session.engine.checkpoint().decode("utf-8"))

    assert checkpoint["checkpoint_version"] == 118
    assert checkpoint["battle"]["performance_execution_receipt"]["complete_from_tick_zero"] is True
    assert checkpoint["context"]["fog_of_war"]["cadence"]["complete_from_tick_zero"] is True
    assert checkpoint["context"]["rng"]["indexed_fow"]["complete_from_tick_zero"] is True


def test_checkpoint_capture_uses_one_typed_fow_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _build_session()
    counts: Counter[str] = Counter()

    def count_calls(owner: object, method_name: str, label: str) -> None:
        original = getattr(owner, method_name)

        def counted(*args: Any, **kwargs: Any) -> Any:
            counts[label] += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(owner, method_name, counted)

    fow = session.context.fog_of_war
    targeting = session.context.tactical_targeting
    assert fow is not None
    assert targeting is not None
    count_calls(fow, "capture_checkpoint_snapshot", "fow_capture")
    count_calls(fow, "get_state", "fow_get")
    count_calls(fow, "stage_state", "fow_stage")
    count_calls(targeting, "get_state", "targeting_get")
    count_calls(targeting, "stage_state", "targeting_stage")
    count_calls(session.context.rng_manager, "get_state", "rng_get")
    count_calls(session.context.detection_engine, "get_state", "detection_get")

    session.engine.checkpoint()

    assert counts["fow_capture"] == 1
    assert counts["fow_get"] == 0
    assert counts["fow_stage"] == 1
    assert counts["targeting_get"] == 1
    assert counts["targeting_stage"] == 1
    assert counts["rng_get"] == 1
    assert counts["detection_get"] == 1


def test_checkpoint_fresh_in_place_and_replay_continuation_are_exact() -> None:
    source = _build_session(record_events=True)
    assert source.step() is False
    checkpoint = source.engine.checkpoint()

    assert source.step() is False
    expected = source.engine.checkpoint()

    source.engine.restore(checkpoint)
    assert source.engine.checkpoint() == checkpoint
    assert source.step() is False
    assert source.engine.checkpoint() == expected

    fresh = _build_session(record_events=True)
    fresh.engine.restore(checkpoint)
    assert fresh.engine.checkpoint() == checkpoint
    assert fresh.step() is False
    assert fresh.engine.checkpoint() == expected

    replay = _build_session(record_events=True)
    assert replay.step() is False
    assert replay.engine.checkpoint() == checkpoint
    assert replay.step() is False
    assert replay.engine.checkpoint() == expected
    assert source.recorder.get_state() == fresh.recorder.get_state() == replay.recorder.get_state()


def test_restore_rejects_duplicate_json_keys_before_mutation() -> None:
    session = _build_session()
    assert session.step() is False
    before = session.engine.checkpoint()
    checkpoint_version = json.loads(before.decode("utf-8"))["checkpoint_version"]
    duplicate = b'{"checkpoint_version":' + str(checkpoint_version).encode("ascii") + b"," + before[1:]

    with pytest.raises(ValueError, match="duplicate"):
        session.engine.restore(duplicate)

    assert session.engine.checkpoint() == before


@pytest.mark.parametrize(
    "marker",
    (
        {"__ndarray__": [True, 2], "__dtype__": "int64"},
        {"__ndarray__": [1.75, 2.0], "__dtype__": "int64"},
        {"__ndarray__": [256], "__dtype__": "uint8"},
        {"__ndarray__": [1, False], "__dtype__": "bool"},
    ),
    ids=("bool-as-int", "fraction-as-int", "integer-overflow", "int-as-bool"),
)
def test_restore_rejects_numpy_marker_coercion_before_mutation(
    marker: dict[str, object],
) -> None:
    session = _build_session()
    assert session.step() is False
    before = session.engine.checkpoint()
    checkpoint = json.loads(before)
    checkpoint["context"]["clock"]["tick_count"] = marker

    with pytest.raises(ValueError, match="NumPy checkpoint"):
        session.engine.restore(_canonical_checkpoint_bytes(checkpoint))

    assert session.engine.checkpoint() == before


def test_checkpoint_encodes_never_fired_weapons_as_json_null() -> None:
    session = _build_session()

    checkpoint_bytes = session.engine.checkpoint()
    assert b"-Infinity" not in checkpoint_bytes
    checkpoint = json.loads(
        checkpoint_bytes.decode("utf-8"),
        parse_constant=_reject_json_constant,
    )
    last_fire_times = tuple(
        weapon["last_fire_time_s"]
        for unit_weapons in checkpoint["context"]["unit_weapon_states"].values()
        for weapon in unit_weapons
    )

    assert len(last_fire_times) == 34
    assert all(value is None for value in last_fire_times)
    assert not any(isinstance(value, float) and not math.isfinite(value) for value in last_fire_times)


def test_checkpoint_round_trips_unbounded_assessment_ratio_as_json_null() -> None:
    source = _build_session()
    unit_id, _ = _cache_assessment(
        source,
        force_ratio=math.inf,
        force_ratio_rating=AssessmentRating.VERY_FAVORABLE,
    )

    checkpoint_bytes = source.engine.checkpoint()
    assert b"Infinity" not in checkpoint_bytes
    assert b"NaN" not in checkpoint_bytes
    checkpoint = json.loads(
        checkpoint_bytes.decode("utf-8"),
        parse_constant=_reject_json_constant,
    )
    persisted = checkpoint["battle"]["cached_assessments"][unit_id]
    assert persisted["force_ratio"] is None
    assert persisted["force_ratio_rating"] == int(
        AssessmentRating.VERY_FAVORABLE,
    )

    resumed = _build_session()
    resumed.engine.restore(checkpoint_bytes)
    restored = resumed.engine.battle_manager._cached_assessments[unit_id]
    assert math.isinf(restored.force_ratio)
    assert restored.force_ratio > 0.0
    assert restored.force_ratio_rating is AssessmentRating.VERY_FAVORABLE
    assert resumed.engine.checkpoint() == checkpoint_bytes

    assert source.step() is False
    assert resumed.step() is False
    assert resumed.engine.checkpoint() == source.engine.checkpoint()


@pytest.mark.parametrize(
    ("force_ratio", "force_ratio_rating", "message"),
    (
        (-1.0, AssessmentRating.VERY_UNFAVORABLE, "non-negative"),
        (-math.inf, AssessmentRating.VERY_UNFAVORABLE, "non-negative"),
        (math.nan, AssessmentRating.VERY_UNFAVORABLE, "non-negative"),
        (math.inf, AssessmentRating.FAVORABLE, "VERY_FAVORABLE"),
    ),
    ids=("negative", "negative-infinity", "nan", "unbounded-wrong-rating"),
)
def test_checkpoint_capture_rejects_invalid_assessment_force_ratio(
    force_ratio: float,
    force_ratio_rating: AssessmentRating,
    message: str,
) -> None:
    session = _build_session()
    unit_id, invalid = _cache_assessment(
        session,
        force_ratio=force_ratio,
        force_ratio_rating=force_ratio_rating,
    )

    with pytest.raises(ValueError, match=message):
        session.engine.checkpoint()

    assert session.engine.battle_manager._cached_assessments[unit_id] is invalid
    session.engine.battle_manager._cached_assessments[unit_id] = replace(
        invalid,
        force_ratio=1.0,
        force_ratio_rating=AssessmentRating.FAVORABLE,
    )
    assert session.engine.checkpoint()


@pytest.mark.parametrize(
    ("malformed_value", "rating", "message"),
    (
        (None, AssessmentRating.FAVORABLE, "VERY_FAVORABLE"),
        (-1.0, AssessmentRating.VERY_FAVORABLE, ">= 0.0"),
        ("-Infinity", AssessmentRating.VERY_FAVORABLE, "outside a weapon timestamp path"),
        ("NaN", AssessmentRating.VERY_FAVORABLE, "outside a weapon timestamp path"),
    ),
    ids=("null-wrong-rating", "negative", "negative-infinity", "nan"),
)
def test_restore_rejects_invalid_assessment_force_ratio_atomically(
    malformed_value: float | str | None,
    rating: AssessmentRating,
    message: str,
) -> None:
    source = _build_session()
    unit_id, _ = _cache_assessment(
        source,
        force_ratio=math.inf,
        force_ratio_rating=AssessmentRating.VERY_FAVORABLE,
    )
    checkpoint = json.loads(source.engine.checkpoint())
    assessment = checkpoint["battle"]["cached_assessments"][unit_id]
    assessment["force_ratio_rating"] = int(rating)
    if isinstance(malformed_value, str):
        marker = "__phase118_nonfinite_force_ratio__"
        assessment["force_ratio"] = marker
        tampered = _canonical_checkpoint_bytes(checkpoint)
        encoded_marker = json.dumps(marker).encode("ascii")
        assert tampered.count(encoded_marker) == 1
        tampered = tampered.replace(
            encoded_marker,
            malformed_value.encode("ascii"),
            1,
        )
    else:
        assessment["force_ratio"] = malformed_value
        tampered = _canonical_checkpoint_bytes(checkpoint)

    target = _build_session()
    before = target.engine.checkpoint()
    with pytest.raises(ValueError, match=message):
        target.engine.restore(tampered)

    assert target.engine.checkpoint() == before


def test_format118_restore_rejects_missing_weapon_timestamp_atomically() -> None:
    session = _build_session()
    unit_id = next(unit_id for unit_id in sorted(session.context.unit_weapons) if session.context.unit_weapons[unit_id])
    weapon = session.context.unit_weapons[unit_id][0].weapon
    assert weapon.cooldown_s > 0.0
    weapon.record_fire(0.0)
    assert weapon.can_fire_timed(0.0) is False
    before_weapon_state = copy.deepcopy(weapon.get_state())
    before = session.engine.checkpoint()
    malformed = json.loads(before)
    removed = malformed["context"]["unit_weapon_states"][unit_id][0].pop(
        "last_fire_time_s",
    )
    assert removed == 0.0
    encoded = json.dumps(
        malformed,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")

    with pytest.raises(
        ValueError,
        match="missing required last_fire_time_s",
    ):
        session.engine.restore(encoded)

    assert session.engine.checkpoint() == before
    assert weapon.get_state() == before_weapon_state
    assert weapon.can_fire_timed(0.0) is False


def test_explicit_format116_restore_rejects_before_mutation() -> None:
    session = _build_session()
    before = session.engine.checkpoint()
    finite_baseline = json.loads(before.replace(b"-Infinity", b"0.0"))
    finite_baseline["checkpoint_version"] = 116
    explicit_116 = json.dumps(
        finite_baseline,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")

    with pytest.raises(ValueError, match="116"):
        session.engine.restore(explicit_116)

    assert session.engine.checkpoint() == before


def test_started_versionless_period_one_continuation_stays_incomplete() -> None:
    """The bounded no-cadence migration must remain exact and qualified."""
    source = _build_session()
    assert source.step() is False
    modern = source.engine.get_state()
    retained_fow = {
        key: copy.deepcopy(modern["context"]["fog_of_war"][key])
        for key in (
            "world_views",
            "current_detection_witnesses",
            "rng_state",
            "intel_fusion",
        )
    }
    legacy = _as_started_versionless(modern)
    legacy_weapon_unit_id = next(
        unit_id
        for unit_id in sorted(legacy["context"]["unit_weapon_states"])
        if legacy["context"]["unit_weapon_states"][unit_id]
    )
    assert (
        legacy["context"]["unit_weapon_states"][legacy_weapon_unit_id][0].pop(
            "last_fire_time_s",
        )
        is None
    )

    resumed = _build_session()
    resumed.engine.set_state(legacy)
    resumed_fow = resumed.context.fog_of_war.get_state()
    assert resumed.context.get_state()["unit_weapon_states"][legacy_weapon_unit_id][0]["last_fire_time_s"] is None
    assert {key: resumed_fow[key] for key in retained_fow} == retained_fow
    assert resumed.context.detection_engine.get_scan_count_state() == {}
    initial_receipt = resumed.performance_execution_receipt()
    initial_cadence = resumed_fow["cadence"]
    initial_indexed = resumed.context.rng_manager.get_state()["indexed_fow"]
    assert initial_receipt.complete_from_tick_zero is False
    assert initial_receipt.tactical_intervals == 0
    assert initial_cadence["complete_from_tick_zero"] is False
    assert initial_cadence["committed_ordinal"] == 0
    assert initial_cadence["attachments"] == []
    assert initial_indexed["complete_from_tick_zero"] is False
    assert initial_indexed["transcript"]["committed_interval_count"] == 0
    assert initial_indexed["transcript"]["committed_entry_count"] == 0

    assert resumed.step() is False
    descendant = resumed.engine.checkpoint()
    descendant_state = json.loads(descendant)
    descendant_receipt = descendant_state["battle"]["performance_execution_receipt"]
    descendant_cadence = descendant_state["context"]["fog_of_war"]["cadence"]
    descendant_indexed = descendant_state["context"]["rng"]["indexed_fow"]
    assert descendant_state["checkpoint_version"] == 118
    assert descendant_receipt["complete_from_tick_zero"] is False
    assert descendant_cadence["complete_from_tick_zero"] is False
    assert descendant_indexed["complete_from_tick_zero"] is False
    assert (
        descendant_receipt["tactical_intervals"]
        == descendant_cadence["committed_ordinal"]
        == descendant_indexed["transcript"]["committed_interval_count"]
        == 1
    )

    restored_descendant = _build_session()
    restored_descendant.engine.restore(descendant)
    assert restored_descendant.engine.checkpoint() == descendant
    assert resumed.step() is False
    assert restored_descendant.step() is False
    assert restored_descendant.engine.checkpoint() == resumed.engine.checkpoint()


@pytest.mark.parametrize(
    "owner",
    ("receipt", "cadence", "indexed"),
)
def test_versionless_rejects_mixed_phase118_evidence_owner(
    owner: str,
) -> None:
    source = _build_session()
    assert source.step() is False
    modern = source.engine.get_state()
    legacy = _as_started_versionless(modern)
    if owner == "receipt":
        legacy["battle"]["performance_execution_receipt"] = copy.deepcopy(
            modern["battle"]["performance_execution_receipt"],
        )
    elif owner == "cadence":
        legacy["context"]["fog_of_war"]["cadence"] = copy.deepcopy(
            modern["context"]["fog_of_war"]["cadence"],
        )
    else:
        legacy["context"]["rng"]["indexed_fow"] = copy.deepcopy(
            modern["context"]["rng"]["indexed_fow"],
        )

    target = _build_session()
    before = target.engine.checkpoint()
    with pytest.raises(ValueError, match="Versionless"):
        target.engine.set_state(legacy)
    assert target.engine.checkpoint() == before


@pytest.mark.parametrize(
    ("mutate", "message"),
    (
        (
            lambda checkpoint: checkpoint["context"]["fog_of_war"]["cadence"].__setitem__(
                "complete_from_tick_zero", False
            ),
            "completeness",
        ),
        (
            lambda checkpoint: checkpoint["context"]["rng"]["indexed_fow"]["transcript"].__setitem__(
                "committed_interval_count",
                checkpoint["context"]["rng"]["indexed_fow"]["transcript"]["committed_interval_count"] + 1,
            ),
            "interval counts disagree",
        ),
        (
            lambda checkpoint: checkpoint["context"]["rng"]["indexed_fow"]["transcript"].__setitem__(
                "committed_entry_count",
                checkpoint["context"]["rng"]["indexed_fow"]["transcript"]["committed_entry_count"] + 1,
            ),
            "indexed-entry and receipt counts disagree",
        ),
    ),
)
def test_restore_rejects_cross_owner_evidence_disagreement_before_mutation(
    mutate: Callable[[dict[str, Any]], None],
    message: str,
) -> None:
    session = _build_session()
    assert session.step() is False
    before = session.engine.checkpoint()
    checkpoint = json.loads(before)

    mutate(checkpoint)
    tampered = json.dumps(
        checkpoint,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")

    with pytest.raises(ValueError, match=message):
        session.engine.restore(tampered)

    assert session.engine.checkpoint() == before


def test_restore_rejects_internally_coherent_tactical_cadence_drift() -> None:
    session = _build_session()
    assert session.step() is False
    before = session.engine.checkpoint()
    checkpoint = json.loads(before)
    receipt = checkpoint["battle"]["performance_execution_receipt"]
    receipt["tactical_interval_microseconds"] = 3_000_000
    receipt["tactical_duration_microseconds"] = receipt["tactical_intervals"] * 3_000_000
    tampered = json.dumps(
        checkpoint,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")

    with pytest.raises(ValueError, match="tactical cadence"):
        session.engine.restore(tampered)

    assert session.engine.checkpoint() == before


@pytest.mark.parametrize("flag", UNSUPPORTED_MODEL_CONTROLS)
def test_runtime_rejects_retired_flag_drift_before_any_step_mutation(
    flag: str,
) -> None:
    session = _build_session()
    before = session.engine.checkpoint()
    setattr(session.context.calibration, flag, True)

    with pytest.raises(ValueError) as captured:
        session.step()

    message = str(captured.value)
    assert flag in message
    assert "unsupported" in message.lower()
    setattr(session.context.calibration, flag, False)
    assert session.engine.checkpoint() == before


@pytest.mark.parametrize("flag", UNSUPPORTED_MODEL_CONTROLS)
def test_runtime_rejects_retired_resolved_calibration_mutation(
    flag: str,
) -> None:
    session = _build_session()
    before = session.engine.checkpoint()

    with pytest.raises(TypeError):
        session.context.cal_flat[flag] = True

    assert session.context.cal_flat[flag] is False
    assert session.engine.checkpoint() == before


@pytest.mark.parametrize(("field_name", "invalid_value"), UNSUPPORTED_LOD_TUNING)
def test_runtime_rejects_resolved_lod_tuning_mutation(
    field_name: str,
    invalid_value: int,
) -> None:
    session = _build_session()
    before = session.engine.checkpoint()
    original_value = session.context.cal_flat[field_name]

    with pytest.raises(TypeError):
        session.context.cal_flat[field_name] = invalid_value

    assert session.context.cal_flat[field_name] == original_value
    assert session.engine.checkpoint() == before


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    (
        ("enable_scan_scheduling", True),
        ("enable_lod", True),
        *UNSUPPORTED_LOD_TUNING,
    ),
)
def test_runtime_rejects_unsupported_authored_config_drift_before_mutation(
    field_name: str,
    invalid_value: bool | int,
) -> None:
    session = _build_session()
    before = session.engine.checkpoint()
    original_calibration = session.context.config.calibration_overrides
    session.context.config.calibration_overrides = session.context.calibration.model_copy(
        update={field_name: invalid_value},
    )

    with pytest.raises(ValueError) as captured:
        session.step()

    message = str(captured.value)
    assert field_name in message
    assert "unsupported" in message.lower()
    session.context.config.calibration_overrides = original_calibration
    assert session.engine.checkpoint() == before


def test_runtime_rejects_supported_authored_flag_drift_before_mutation() -> None:
    session = _build_session()
    before = session.engine.checkpoint()
    original_calibration = session.context.config.calibration_overrides
    session.context.config.calibration_overrides = session.context.calibration.model_copy(
        update={"enable_soa": True},
    )

    with pytest.raises(RuntimeError, match="Authored runtime configuration"):
        session.step()

    session.context.config.calibration_overrides = original_calibration
    assert session.engine.checkpoint() == before


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    (
        ("enable_scan_scheduling", True),
        ("enable_lod", True),
        *UNSUPPORTED_LOD_TUNING,
    ),
)
def test_receipt_owner_rejects_unsupported_resolved_calibration_mutation(
    field_name: str,
    invalid_value: bool | int,
) -> None:
    session = _build_session()
    before = session.performance_execution_receipt()
    original_value = session.context.cal_flat[field_name]

    with pytest.raises(TypeError):
        session.context.cal_flat[field_name] = invalid_value

    assert session.context.cal_flat[field_name] == original_value
    assert session.performance_execution_receipt() == before


def test_receipt_owner_rejects_supported_resolved_calibration_mutation() -> None:
    session = _build_session()
    before = session.performance_execution_receipt()
    original_value = session.context.cal_flat["enable_soa"]

    with pytest.raises(TypeError):
        session.context.cal_flat["enable_soa"] = True

    assert session.context.cal_flat["enable_soa"] is original_value
    assert session.performance_execution_receipt() == before


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    (
        ("enable_scan_scheduling", True),
        ("enable_lod", True),
        *UNSUPPORTED_LOD_TUNING,
    ),
)
def test_run_rejects_unsupported_authored_config_before_recorder_mutation(
    field_name: str,
    invalid_value: bool | int,
) -> None:
    session = _build_session(record_events=True)
    recorder = session.engine.recorder
    assert recorder is not None
    before = session.engine.checkpoint()
    before_receipt = session.performance_execution_receipt()
    before_events = recorder.events
    original_calibration = session.context.config.calibration_overrides
    session.context.config.calibration_overrides = session.context.calibration.model_copy(
        update={field_name: invalid_value},
    )

    with pytest.raises(ValueError) as captured:
        session.run_to_completion()

    message = str(captured.value)
    assert field_name in message
    assert "unsupported" in message.lower()
    assert recorder._subscribed is False
    assert recorder.events == before_events
    assert session.context.clock.tick_count == 0
    session.context.config.calibration_overrides = original_calibration
    assert session.performance_execution_receipt() == before_receipt
    assert session.engine.checkpoint() == before


def test_run_stops_recorder_without_masking_interval_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _build_session(record_events=True)
    recorder = session.engine.recorder
    assert recorder is not None
    accumulator = session.engine.battle_manager._performance_receipts

    def fail_stage(*_args: object, **_kwargs: object) -> NoReturn:
        raise _InjectedTacticalBaseFault("injected run-path interval failure")

    monkeypatch.setattr(accumulator, "stage", fail_stage)

    with pytest.raises(
        _InjectedTacticalBaseFault,
        match="injected run-path interval failure",
    ):
        session.run_to_completion()

    assert recorder._subscribed is False
    assert accumulator.poisoned is True


@pytest.mark.parametrize("flag", UNSUPPORTED_MODEL_CONTROLS)
def test_restore_rejects_coherent_retired_flag_activation_atomically(
    flag: str,
) -> None:
    session = _build_session()
    before = session.engine.checkpoint()
    checkpoint = json.loads(before)
    checkpoint["context"]["config"]["calibration_overrides"][flag] = True
    checkpoint["context"]["calibration"][flag] = True
    checkpoint["battle"]["performance_execution_receipt"]["effective_flags"][flag] = True
    tampered = json.dumps(
        checkpoint,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")

    with pytest.raises(ValueError) as captured:
        session.engine.restore(tampered)

    message = str(captured.value)
    assert flag in message
    assert "unsupported" in message.lower()
    assert session.engine.checkpoint() == before


@pytest.mark.parametrize(("field_name", "invalid_value"), UNSUPPORTED_LOD_TUNING)
def test_restore_rejects_retired_lod_tuning_atomically(
    field_name: str,
    invalid_value: int,
) -> None:
    session = _build_session()
    before = session.engine.checkpoint()
    checkpoint = json.loads(before)
    checkpoint["context"]["config"]["calibration_overrides"][field_name] = invalid_value
    checkpoint["context"]["calibration"][field_name] = invalid_value
    tampered = json.dumps(
        checkpoint,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")

    with pytest.raises(ValueError) as captured:
        session.engine.restore(tampered)

    message = str(captured.value)
    assert field_name in message
    assert "unsupported" in message.lower()
    assert session.engine.checkpoint() == before
