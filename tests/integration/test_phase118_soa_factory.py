"""Production-factory proof for the Phase 118 SoA contract."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Iterable

from stochastic_warfare.simulation.runtime import (
    AnalysisVariant,
    PreparedScenario,
    RuntimeSession,
    SimulationRuntimeFactory,
)
from stochastic_warfare.simulation.recorder import RecorderConfig, SimulationRecorder
from stochastic_warfare.simulation.scenario import SimulationContext


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
SCENARIO = DATA_DIR / "scenarios/calibration_air_ground/scenario.yaml"
FLAG = "enable_soa"
CONTROL_VARIANT = "phase118-soa-factory-control"
CANDIDATE_VARIANT = "phase118-soa-factory-candidate"

TEST_SEED = 42
CHECKPOINT_INTERVALS = 10
OBSERVATION_INTERVALS = 20
CONTROL_FLAGS = {
    "enable_detection_culling": False,
    "enable_scan_scheduling": False,
    "enable_lod": False,
    "enable_soa": False,
    "enable_parallel_detection": False,
}
SOA_RECEIPT_COUNTER_PATHS = (
    "fow/selection/soa_vector_builds",
    "fow/selection/soa_vector_queries",
    "fow/selection/soa_vector_admitted_targets",
    "fow/selection/soa_vector_pruned_targets",
    "fow/selection/brute_force_cycles",
    "fow/selection/brute_force_admitted_targets",
    "fow/scan/operational_sensor_target_opportunities",
    "fow/detection/api_calls",
    "fow/detection/pre_rng_unsupported_domain_rejections",
    "fow/detection/pre_rng_above_max_range_rejections",
    "soa/pre_movement_builds",
    "soa/pre_movement_enemy_position_projections",
    "soa/post_movement_builds",
    "soa/post_movement_enemy_position_projections",
)


def _prepare_pair() -> PreparedScenario:
    prepared = SimulationRuntimeFactory().prepare(
        SCENARIO,
        DATA_DIR,
        (
            AnalysisVariant(
                variant_id=CONTROL_VARIANT,
                calibration_patch=CONTROL_FLAGS,
            ),
            AnalysisVariant(
                variant_id=CANDIDATE_VARIANT,
                calibration_patch={**CONTROL_FLAGS, FLAG: True},
            ),
        ),
    )

    control = prepared.variant(CONTROL_VARIANT).config.model_dump(mode="json")
    candidate = prepared.variant(CANDIDATE_VARIANT).config.model_dump(mode="json")
    projected_candidate = copy.deepcopy(candidate)
    projected_candidate["calibration_overrides"][FLAG] = False

    assert control == projected_candidate
    assert control["calibration_overrides"][FLAG] is False
    assert candidate["calibration_overrides"][FLAG] is True
    assert control["calibration_overrides"]["enable_detection_culling"] is False
    assert candidate["calibration_overrides"]["enable_detection_culling"] is False
    assert prepared.side_ids == ("blue", "red")
    return prepared


def _build(prepared: PreparedScenario, variant: str) -> RuntimeSession:
    def strict_recorder(context: SimulationContext) -> SimulationRecorder:
        return SimulationRecorder(
            context.event_bus,
            RecorderConfig(
                max_events=50_000,
                snapshot_interval_ticks=0,
                enabled=True,
                strict_overflow=True,
                strict_extraction_errors=True,
            ),
        )

    session = prepared.build(
        variant,
        seed=TEST_SEED,
        max_ticks=OBSERVATION_INTERVALS + 4,
        strict_mode=True,
        recorder_factory=strict_recorder,
    )
    assert session.recorder is not None
    return session


def _start_recorders(sessions: Iterable[RuntimeSession]) -> None:
    for session in sessions:
        assert session.recorder is not None
        session.recorder.start()


def _stop_recorders(sessions: Iterable[RuntimeSession]) -> None:
    for session in sessions:
        assert session.recorder is not None
        session.recorder.stop()


def _advance(
    sessions: tuple[RuntimeSession, ...],
    *,
    intervals: int,
    exact_indexed_pairs: tuple[tuple[RuntimeSession, RuntimeSession], ...],
) -> None:
    for _ in range(intervals):
        for session in sessions:
            assert session.step() is False
        for left, right in exact_indexed_pairs:
            left_record = left.fow_indexed_interval_record()
            right_record = right.fow_indexed_interval_record()
            assert left_record is not None
            assert left_record == right_record


def _set_receipt_counter(receipt: dict[str, object], path: str) -> None:
    current = receipt
    parts = path.split("/")
    for part in parts[:-1]:
        child = current.get(part)
        assert isinstance(child, dict)
        current = child
    assert type(current.get(parts[-1])) is int
    current[parts[-1]] = 0


def _normalized_checkpoint(checkpoint: bytes) -> str:
    projected = json.loads(checkpoint)
    assert isinstance(projected, dict)
    assert type(projected.get("checkpoint_version")) is int
    assert projected["checkpoint_version"] == 118
    context = projected.get("context")
    battle = projected.get("battle")
    assert isinstance(context, dict)
    assert isinstance(battle, dict)
    config = context.get("config")
    calibration = context.get("calibration")
    receipt = battle.get("performance_execution_receipt")
    assert isinstance(config, dict)
    assert isinstance(calibration, dict)
    assert isinstance(receipt, dict)
    overrides = config.get("calibration_overrides")
    effective_flags = receipt.get("effective_flags")
    assert isinstance(overrides, dict)
    assert isinstance(effective_flags, dict)
    assert type(overrides.get(FLAG)) is bool
    assert type(calibration.get(FLAG)) is bool
    assert type(effective_flags.get(FLAG)) is bool
    overrides[FLAG] = False
    calibration[FLAG] = False
    effective_flags[FLAG] = False
    for path in SOA_RECEIPT_COUNTER_PATHS:
        _set_receipt_counter(receipt, path)
    return json.dumps(
        projected,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _assert_exact_pair_semantics(
    control: RuntimeSession,
    candidate: RuntimeSession,
) -> None:
    control_checkpoint = control.engine.checkpoint()
    candidate_checkpoint = candidate.engine.checkpoint()

    # Raw checkpoints retain the effective flag and branch receipts; the
    # contract permits only those enumerated differences.
    assert control_checkpoint != candidate_checkpoint
    assert _normalized_checkpoint(control_checkpoint) == _normalized_checkpoint(
        candidate_checkpoint,
    )
    assert control.context.rng_manager.get_state() == (candidate.context.rng_manager.get_state())
    assert control.fow_indexed_interval_record() == (candidate.fow_indexed_interval_record())
    assert control.recorder is not None
    assert candidate.recorder is not None
    assert control.recorder.get_state() == candidate.recorder.get_state()


def test_soa_factory_pair_executes_material_work_with_exact_semantics() -> None:
    """The real SoA branch must prune work without changing simulation state."""
    prepared = _prepare_pair()
    control = _build(prepared, CONTROL_VARIANT)
    candidate = _build(prepared, CANDIDATE_VARIANT)
    control_repeat = _build(prepared, CONTROL_VARIANT)
    candidate_repeat = _build(prepared, CANDIDATE_VARIANT)
    initial_sessions = (
        control,
        candidate,
        control_repeat,
        candidate_repeat,
    )
    all_sessions = list(initial_sessions)
    _start_recorders(initial_sessions)
    try:
        control_tick_zero = control.engine.checkpoint()
        candidate_tick_zero = candidate.engine.checkpoint()
        assert _normalized_checkpoint(control_tick_zero) == (_normalized_checkpoint(candidate_tick_zero))

        _advance(
            initial_sessions,
            intervals=CHECKPOINT_INTERVALS,
            exact_indexed_pairs=(
                (control, candidate),
                (control, control_repeat),
                (candidate, candidate_repeat),
            ),
        )
        control_midpoint = control.engine.checkpoint()
        candidate_midpoint = candidate.engine.checkpoint()
        assert control_midpoint == control_repeat.engine.checkpoint()
        assert candidate_midpoint == candidate_repeat.engine.checkpoint()
        _assert_exact_pair_semantics(control, candidate)

        control_resumed = _build(prepared, CONTROL_VARIANT)
        candidate_resumed = _build(prepared, CANDIDATE_VARIANT)
        all_sessions.extend((control_resumed, candidate_resumed))
        control_resumed.engine.restore(control_midpoint)
        candidate_resumed.engine.restore(candidate_midpoint)
        assert control_resumed.engine.checkpoint() == control_midpoint
        assert candidate_resumed.engine.checkpoint() == candidate_midpoint
        _start_recorders((control_resumed, candidate_resumed))

        continued_sessions = (
            control,
            candidate,
            control_repeat,
            candidate_repeat,
            control_resumed,
            candidate_resumed,
        )
        _advance(
            continued_sessions,
            intervals=OBSERVATION_INTERVALS - CHECKPOINT_INTERVALS,
            exact_indexed_pairs=(
                (control, candidate),
                (control, control_repeat),
                (candidate, candidate_repeat),
                (control, control_resumed),
                (candidate, candidate_resumed),
            ),
        )
        _stop_recorders(continued_sessions)

        control_final = control.engine.checkpoint()
        candidate_final = candidate.engine.checkpoint()
        assert control_final == control_repeat.engine.checkpoint()
        assert candidate_final == candidate_repeat.engine.checkpoint()
        assert control_final == control_resumed.engine.checkpoint()
        assert candidate_final == candidate_resumed.engine.checkpoint()
        _assert_exact_pair_semantics(control, candidate)

        control_receipt = control.performance_execution_receipt()
        candidate_receipt = candidate.performance_execution_receipt()
        control_selection = control_receipt.fow.selection
        candidate_selection = candidate_receipt.fow.selection

        assert control_receipt.complete_from_tick_zero is True
        assert candidate_receipt.complete_from_tick_zero is True
        assert control_receipt.tactical_intervals == OBSERVATION_INTERVALS
        assert candidate_receipt.tactical_intervals == OBSERVATION_INTERVALS
        assert control_receipt.effective_flags.enable_soa is False
        assert candidate_receipt.effective_flags.enable_soa is True

        assert not any(control_receipt.soa.model_dump(mode="python").values())
        assert control_selection.brute_force_cycles > 0
        assert control_selection.brute_force_admitted_targets == (control_receipt.fow.target_opportunities)
        assert not any(
            (
                control_selection.soa_vector_builds,
                control_selection.soa_vector_queries,
                control_selection.soa_vector_admitted_targets,
                control_selection.soa_vector_pruned_targets,
            ),
        )

        assert candidate_selection.soa_vector_builds > 0
        assert candidate_selection.soa_vector_queries > 0
        assert candidate_selection.soa_vector_admitted_targets > 0
        assert candidate_selection.soa_vector_pruned_targets > 0
        assert candidate_selection.brute_force_cycles == 0
        assert candidate_selection.brute_force_admitted_targets == 0
        assert candidate_receipt.soa.pre_movement_builds > 0
        assert candidate_receipt.soa.pre_movement_enemy_position_projections > 0
        assert candidate_receipt.soa.post_movement_builds > 0
        assert candidate_receipt.soa.post_movement_enemy_position_projections > 0
        assert (
            candidate_selection.soa_vector_admitted_targets + candidate_selection.soa_vector_pruned_targets
            == candidate_receipt.fow.target_opportunities
        )
        assert control_receipt.fow.target_opportunities == (candidate_receipt.fow.target_opportunities)
        assert not any(
            (
                control_selection.strtree_builds,
                control_selection.strtree_queries,
                candidate_selection.strtree_builds,
                candidate_selection.strtree_queries,
            ),
        )

        control_detection = control_receipt.fow.detection
        candidate_detection = candidate_receipt.fow.detection
        api_call_delta = control_detection.api_calls - candidate_detection.api_calls
        normalizable_rejection_delta = (
            control_detection.pre_rng_unsupported_domain_rejections
            + control_detection.pre_rng_above_max_range_rejections
            - candidate_detection.pre_rng_unsupported_domain_rejections
            - candidate_detection.pre_rng_above_max_range_rejections
        )
        assert api_call_delta == candidate_selection.soa_vector_pruned_targets
        assert api_call_delta == normalizable_rejection_delta
        assert control_detection.stochastic_draws > 0
        assert control_detection.stochastic_draws == candidate_detection.stochastic_draws
        assert control_detection.successes == candidate_detection.successes
        assert control_detection.published_witnesses == (candidate_detection.published_witnesses)
        assert control_receipt.fow.indexed_rng == candidate_receipt.fow.indexed_rng
        assert control_receipt.fow.indexed_rng.blocks > 0

        control_recorder = control.recorder
        candidate_recorder = candidate.recorder
        assert control_recorder is not None
        assert candidate_recorder is not None
        assert control_recorder.get_state()["events"]
        assert control_recorder.get_state() == candidate_recorder.get_state()

        persisted_control = json.loads(control_final)
        persisted_candidate = json.loads(candidate_final)
        assert persisted_control["checkpoint_version"] == 118
        assert persisted_candidate["checkpoint_version"] == 118
        assert persisted_control["battle"]["performance_execution_receipt"] == (control_receipt.to_state())
        assert persisted_candidate["battle"]["performance_execution_receipt"] == (candidate_receipt.to_state())
    finally:
        _stop_recorders(all_sessions)
