"""Phase 112 production-red proofs for movement, Space ISR, and benchmarks."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.core.types import Position
from stochastic_warfare.simulation.engine import EngineConfig, SimulationEngine
from stochastic_warfare.simulation.recorder import SimulationRecorder
from stochastic_warfare.simulation.runtime import (
    AnalysisVariant,
    SimulationRuntimeFactory,
)


ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data"
CAMBRAI_PATH = DATA_DIR / "eras" / "ww1" / "scenarios" / "cambrai" / "scenario.yaml"
EASTING_PATH = DATA_DIR / "scenarios" / "73_easting" / "scenario.yaml"
SPACE_ASAT_PATH = DATA_DIR / "scenarios" / "space_asat_escalation" / "scenario.yaml"
SPACE_ISR_PATH = DATA_DIR / "scenarios" / "space_isr_gap" / "scenario.yaml"
RUNTIME_VARIANT = AnalysisVariant(variant_id="phase112-runtime-red")


def _engine(
    path: Path,
    *,
    seed: int = 42,
    calibration_patch: dict[str, Any] | None = None,
) -> SimulationEngine:
    variant = AnalysisVariant(
        variant_id=RUNTIME_VARIANT.variant_id,
        calibration_patch=calibration_patch or {},
    )
    prepared = SimulationRuntimeFactory().prepare(
        path,
        DATA_DIR,
        (variant,),
    )
    return prepared.build(
        RUNTIME_VARIANT.variant_id,
        seed=seed,
        max_ticks=1_000_000,
        strict_mode=True,
    ).engine


def _stateful_engine(
    path: Path,
    *,
    seed: int = 42,
    snapshot_interval_ticks: int = 100,
) -> tuple[SimulationEngine, SimulationRecorder]:
    """Build every checkpoint owner through the runtime-owned boundary."""
    prepared = SimulationRuntimeFactory().prepare(
        path,
        DATA_DIR,
        (RUNTIME_VARIANT,),
    )
    session = prepared.build(
        RUNTIME_VARIANT.variant_id,
        seed=seed,
        max_ticks=1_000_000,
        record_events=True,
        engine_config=EngineConfig(
            max_ticks=1_000_000,
            snapshot_interval_ticks=snapshot_interval_ticks,
        ),
        strict_mode=True,
    )
    assert session.recorder is not None
    return session.engine, session.recorder


def _corrupt_checkpoint_owner(
    state: dict[str, Any],
    owner: str,
) -> None:
    """Inject one invalid value at each top-level restore owner."""
    if owner == "engine":
        state["last_ato_day"] = True
    elif owner == "campaign":
        state["campaign"]["reinforcements"][0]["arrived"] = "yes"
    elif owner == "context":
        state["context"]["planning_engine"]["config"]["method_speed_multipliers"]["MDMP"] = None
    elif owner == "battle":
        state["battle"]["lod_pending_counts"] = {
            "blue_m1a2_0000": -1,
        }
    elif owner == "victory":
        state["victory"]["objectives"]["obj_alpha"]["contested"] = "yes"
    elif owner == "recorder":
        state["recorder"]["events"].append(
            {
                "tick": 0,
                "timestamp": "not-an-iso-timestamp",
                "event_type": "Phase112InvalidEvent",
                "source": "core",
                "data": {},
            }
        )
    else:  # pragma: no cover - the parametrization is intentionally closed
        raise AssertionError(f"Unknown checkpoint owner {owner!r}")


def _corrupt_checkpoint_semantics(
    state: dict[str, Any],
    corruption: str,
) -> None:
    """Inject one type-valid but impossible whole-runtime relationship."""
    if corruption == "clock_bool_tick":
        state["context"]["clock"]["tick_count"] = True
    elif corruption == "clock_elapsed_without_tick":
        state["context"]["clock"]["current"] = state["context"]["clock"]["start"]
    elif corruption == "terminal_winner":
        state["last_victory"] = {
            "game_over": True,
            "winning_side": "ghost",
            "condition_type": "time_expired",
            "message": "forged terminal result",
            "tick": state["context"]["clock"]["tick_count"],
        }
    elif corruption == "terminal_condition":
        state["last_victory"] = {
            "game_over": True,
            "winning_side": "blue",
            "condition_type": "invented",
            "message": "forged terminal result",
            "tick": state["context"]["clock"]["tick_count"],
        }
    elif corruption == "objective_owner":
        state["victory"]["objectives"]["obj_alpha"]["controlling_side"] = "ghost"
    elif corruption == "battle_allocator":
        assert "battle_0000" in state["battle"]["battles"]
        state["battle"]["next_battle_id"] = 0
    elif corruption == "recorder_tick":
        state["recorder"]["current_tick"] = 999
    elif corruption == "overdue_reinforcement":
        reinforcement = state["campaign"]["reinforcements"][0]
        assert reinforcement["arrived"] is False
        reinforcement["actual_arrival_time_s"] = 5.0
    else:  # pragma: no cover - the parametrization is intentionally closed
        raise AssertionError(f"Unknown checkpoint corruption {corruption!r}")


def _reason_counts_for_unit(value: Any, unit_id: str) -> dict[str, int]:
    """Find one unit's persisted semantic reason counters."""
    if isinstance(value, dict):
        identifies_unit = value.get("unit_id") == unit_id or value.get("entity_id") == unit_id
        reason_counts = value.get("reason_counts")
        if identifies_unit and isinstance(reason_counts, dict):
            return reason_counts

        direct = value.get(unit_id)
        if isinstance(direct, dict):
            direct_counts = direct.get("reason_counts")
            if isinstance(direct_counts, dict):
                return direct_counts

        for nested in value.values():
            try:
                return _reason_counts_for_unit(nested, unit_id)
            except AssertionError:
                pass
    elif isinstance(value, list):
        for nested in value:
            try:
                return _reason_counts_for_unit(nested, unit_id)
            except AssertionError:
                pass
    raise AssertionError(
        f"no persisted semantic movement diagnostics for {unit_id!r}",
    )


def test_cambrai_mark_iv_advance_is_not_reported_as_stuck_or_blocked() -> None:
    """The evaluator must expose sensing-aware Mark IV movement."""
    from scripts.evaluate_scenarios import run_scenario

    result = run_scenario(CAMBRAI_PATH, DATA_DIR, seed=42)

    assert result.success, result.error
    assert result.ticks_executed == 156
    assert result.units_that_moved == 7
    assert result.units_that_didnt_move == 3
    assert not any(issue.startswith("MANY_STUCK_UNITS") for issue in result.issues), result.issues

    mark_ivs = [detail for detail in result.unit_details if detail["unit_type"] == "mark_iv_tank"]
    assert len(mark_ivs) == 4
    for detail in mark_ivs:
        assert detail["movement_disposition"] == "MOVED"
        assert detail["distance_moved"] > 1_300.0
        assert detail["movement_reason_counts"]["MOVED"] == 156
        assert detail["movement_reason_counts"]["ENGINE_WEAPON_STANDOFF"] == 0
        assert detail["movement_reason_counts"].get("RESOURCE_BLOCKED", 0) == 0


def test_fuel_depleted_vehicles_record_real_resource_block() -> None:
    """The ordinary tactical fuel gate must persist a different disposition."""
    engine = _engine(
        EASTING_PATH,
        calibration_patch={"defensive_sides": []},
    )
    context = engine._ctx

    movers = context.units_by_side["blue"][:5]
    target = context.units_by_side["red"][0]
    for index, unit in enumerate(movers):
        object.__setattr__(
            unit,
            "position",
            Position(0.0, index * 50.0, 0.0),
        )
        object.__setattr__(unit, "speed", unit.max_speed)
        object.__setattr__(unit, "fuel_remaining", 0.0)
    object.__setattr__(target, "position", Position(20_000.0, 100.0, 0.0))

    before = {unit.entity_id: unit.position for unit in movers}
    engine._battle._execute_movement(
        context,
        {"blue": movers},
        {"blue": [target]},
        60.0,
    )
    assert {unit.entity_id: unit.position for unit in movers} == before

    persisted = engine.get_state()
    for unit in movers:
        counts = _reason_counts_for_unit(persisted, unit.entity_id)
        assert counts["RESOURCE_BLOCKED"] > 0
        assert counts.get("ENGINE_WEAPON_STANDOFF", 0) == 0
        assert counts.get("ZERO_PROGRESS", 0) == 0


def test_unknown_space_report_shape_is_rejected_atomically() -> None:
    """The whole-runtime state boundary must not accept arbitrary report JSON."""
    source = _engine(SPACE_ASAT_PATH)
    invalid = copy.deepcopy(source.get_state())
    isr_state = invalid["context"]["space_engine"]["isr_engine"]
    queue_key = "report_queue" if "report_queue" in isr_state else "recent_reports"
    isr_state[queue_key] = [
        {
            "unexpected_phase112_report_key": True,
            "satellite_id": "unknown_phase112_satellite",
        },
    ]

    target = _engine(SPACE_ASAT_PATH)
    before = target.checkpoint()
    with pytest.raises(
        ValueError,
        match=r"(ISR|report|unknown|keys)",
    ):
        target.set_state(invalid)
    assert target.checkpoint() == before


def test_reachable_space_report_queue_rehydrates_typed_reports() -> None:
    """A loader-wired observation must survive a fresh runtime checkpoint."""
    source = _engine(SPACE_ISR_PATH)
    assert source._ctx.space_engine is not None

    while source._ctx.clock.elapsed.total_seconds() < 14_400.0:
        assert source.step() is False

    state = source.get_state()
    isr_state = state["context"]["space_engine"]["isr_engine"]
    assert set(isr_state) == {
        "last_overpass_time",
        "last_reported_at",
        "report_queue",
        "next_report_sequence",
    }
    assert len(isr_state["report_queue"]) == 8

    checkpoint = source.checkpoint()
    resumed = _engine(SPACE_ISR_PATH, seed=999_112)
    resumed.restore(checkpoint)
    assert resumed.checkpoint() == checkpoint

    from stochastic_warfare.space.isr import SpaceISRReport

    queue = resumed._ctx.space_engine.isr_engine._report_queue
    assert len(queue) == 8
    assert all(isinstance(report, SpaceISRReport) for report in queue)
    assert all(isinstance(report.target_position, Position) for report in queue)

    malformed = copy.deepcopy(resumed.get_state())
    malformed_queue = malformed["context"]["space_engine"]["isr_engine"]["report_queue"]
    malformed_queue[0]["unknown_report_field"] = "must reject"

    target = _engine(SPACE_ISR_PATH, seed=888_112)
    before = target.checkpoint()
    with pytest.raises(ValueError, match=r"(report|unknown|keys)"):
        target.set_state(malformed)
    assert target.checkpoint() == before


@pytest.mark.parametrize(
    "owner",
    (
        "engine",
        "campaign",
        "context",
        "battle",
        "victory",
        "recorder",
    ),
)
def test_whole_runtime_rejects_each_invalid_owner_atomically(
    owner: str,
) -> None:
    """No late owner may partially rewind an already-progressed runtime."""
    scenario_path = DATA_DIR / "scenarios" / "test_campaign" / "scenario.yaml"
    source, _ = _stateful_engine(scenario_path, seed=112)
    invalid = copy.deepcopy(source.get_state())
    _corrupt_checkpoint_owner(invalid, owner)

    target, _ = _stateful_engine(scenario_path, seed=112)
    assert target.step() is False
    before = target.checkpoint()

    with pytest.raises((TypeError, ValueError)):
        target.set_state(invalid)

    assert target.checkpoint() == before


@pytest.mark.parametrize(
    ("corruption", "message"),
    (
        ("clock_bool_tick", "clock tick_count"),
        ("clock_elapsed_without_tick", "logical time"),
        ("terminal_winner", "victory result"),
        ("terminal_condition", "victory result"),
        ("objective_owner", "controlling_side"),
        ("battle_allocator", "would collide"),
        ("recorder_tick", "checkpoint clock"),
        ("overdue_reinforcement", "remains pending"),
    ),
)
def test_whole_runtime_rejects_impossible_cross_owner_state_atomically(
    corruption: str,
    message: str,
) -> None:
    """Format-115 cross-owner contradictions fail before any live rewind."""
    scenario_path = DATA_DIR / "scenarios" / "test_campaign" / "scenario.yaml"
    source, _ = _stateful_engine(scenario_path, seed=112)
    assert source.step() is False
    assert source.step() is False
    invalid = copy.deepcopy(source.get_state())
    _corrupt_checkpoint_semantics(invalid, corruption)

    target, _ = _stateful_engine(scenario_path, seed=999_112)
    assert target.step() is False
    before = target.checkpoint()

    with pytest.raises(ValueError, match=message):
        target.set_state(invalid)

    assert target.checkpoint() == before


def test_valid_schema115_restore_preserves_identity_and_continuation() -> None:
    """A strict valid restore remains exact, in-place, and deterministic."""
    scenario_path = DATA_DIR / "scenarios" / "test_campaign" / "scenario.yaml"
    source, _ = _stateful_engine(scenario_path, seed=112)
    assert source.step() is False
    assert source.step() is False
    checkpoint = source.checkpoint()

    resumed, _ = _stateful_engine(scenario_path, seed=999_112)
    units_before = {unit.entity_id: unit for unit in resumed._ctx.all_units()}
    weapons_before = {
        unit_id: tuple(weapon for weapon, _ in attachments)
        for unit_id, attachments in resumed._ctx.unit_weapons.items()
    }
    sensors_before = {unit_id: tuple(sensors) for unit_id, sensors in resumed._ctx.unit_sensors.items()}
    rng_before = {module: resumed._ctx.rng_manager.get_stream(module) for module in ModuleId}
    objectives_before = dict(resumed._victory._objectives)

    resumed.restore(checkpoint)

    assert resumed.checkpoint() == checkpoint
    assert {unit.entity_id: unit for unit in resumed._ctx.all_units()} == units_before
    for unit in resumed._ctx.all_units():
        assert unit is units_before[unit.entity_id]
    for unit_id, attachments in resumed._ctx.unit_weapons.items():
        assert tuple(weapon for weapon, _ in attachments) == weapons_before[unit_id]
        for index, (weapon, _) in enumerate(attachments):
            assert weapon is weapons_before[unit_id][index]
    for unit_id, sensors in resumed._ctx.unit_sensors.items():
        assert tuple(sensors) == sensors_before[unit_id]
        for index, sensor in enumerate(sensors):
            assert sensor is sensors_before[unit_id][index]
    for module in ModuleId:
        assert resumed._ctx.rng_manager.get_stream(module) is rng_before[module]
    assert resumed._victory._objectives == objectives_before
    for objective_id, objective in resumed._victory._objectives.items():
        assert objective is objectives_before[objective_id]

    assert source.step() is False
    assert resumed.step() is False
    assert resumed.checkpoint() == source.checkpoint()


def test_recorder_snapshot_payload_survives_exact_checkpoint_restore() -> None:
    """Recorder evidence includes its full snapshot, not metadata alone."""
    scenario_path = DATA_DIR / "scenarios" / "test_campaign" / "scenario.yaml"
    source, source_recorder = _stateful_engine(
        scenario_path,
        seed=112,
        snapshot_interval_ticks=1,
    )
    source_recorder.start()
    assert source.step() is False
    source_recorder.stop()
    assert len(source_recorder.snapshots) == 1

    checkpoint = source.checkpoint()
    resumed, resumed_recorder = _stateful_engine(
        scenario_path,
        seed=999_112,
        snapshot_interval_ticks=1,
    )
    resumed.restore(checkpoint)

    assert len(resumed_recorder.snapshots) == 1
    assert resumed_recorder.get_state()["snapshots"][0]["state"]
    assert resumed.checkpoint() == checkpoint


def test_cached_ooda_assessments_resume_with_exact_decisions_and_rng() -> None:
    """OBSERVE output must survive until DECIDE in a fresh runtime."""
    source, source_recorder = _stateful_engine(
        SPACE_ASAT_PATH,
        seed=112,
        snapshot_interval_ticks=0,
    )
    source_recorder.start()
    assert source.step() is False
    assert source.step() is False

    saved_state = source.get_state()
    saved_assessments = saved_state["battle"]["cached_assessments"]
    assert len(saved_assessments) == 16
    assert {commander["phase"] for commander in saved_state["context"]["ooda_engine"]["commanders"].values()} == {2}
    checkpoint = source.checkpoint()

    resumed, resumed_recorder = _stateful_engine(
        SPACE_ASAT_PATH,
        seed=999_112,
        snapshot_interval_ticks=0,
    )
    resumed.restore(checkpoint)
    resumed_recorder.start()
    assert resumed.checkpoint() == checkpoint

    assert source.step() is False
    assert resumed.step() is False

    source_decisions = source_recorder.events_of_type(
        "DecisionMadeEvent",
    )
    resumed_decisions = resumed_recorder.events_of_type(
        "DecisionMadeEvent",
    )
    assert len(source_decisions) == len(resumed_decisions) == 16
    assert source_decisions == resumed_decisions
    assert (
        source._ctx.rng_manager.get_state()["streams"][ModuleId.C2.value]
        == resumed._ctx.rng_manager.get_state()["streams"][ModuleId.C2.value]
    )
    assert source.checkpoint() == resumed.checkpoint()


def test_legacy_unpaired_golan_baseline_cannot_authorize_a_pass() -> None:
    """The public verifier must refuse the contradictory absolute baseline."""
    from tests.benchmarks.benchmark_suite import (
        BenchmarkBaseline,
        BenchmarkResult,
    )

    candidate = BenchmarkResult(
        scenario_name="golan_heights",
        unit_count=290,
        wall_clock_s=129.517695006,
        ticks_executed=6480,
        ticks_per_second=6480 / 129.517695006,
        peak_memory_mb=0.0,
        seed=42,
        winner="blue",
        commit="0460ac70be86784bcc6e359ae4202f4bcb938c60",
    )

    with pytest.raises(
        ValueError,
        match=r"(paired|version.?2|measurement.?only)",
    ):
        BenchmarkBaseline().check_regression(
            "golan_heights",
            candidate,
        )
