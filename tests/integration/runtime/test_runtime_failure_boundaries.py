"""Production runtime proofs for nested failure-policy boundaries."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from stochastic_warfare.c2.communications import (
    CommEquipmentDefinition,
    CommunicationsEngine,
    EmconState,
)
from stochastic_warfare.combat.events import TimeOnTargetMissionEvent
from stochastic_warfare.core.events import Event, EventBus
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.simulation.engine import (
    RuntimeExecutionMode,
    SuppressedRuntimeFailure,
)
from stochastic_warfare.simulation.recorder import (
    RecorderConfig,
    SimulationRecorder,
)
from stochastic_warfare.simulation.runtime import (
    AnalysisVariant,
    PreparedScenario,
    RuntimeSession,
    SimulationRuntimeFactory,
)
from stochastic_warfare.simulation.scenario import SimulationContext
from stochastic_warfare.space.events import ASATEngagementEvent


ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data"
BASE_SCENARIO = DATA_DIR / "scenarios/test_campaign/scenario.yaml"
TOT_SCENARIO = DATA_DIR / "scenarios/time_on_target_validation/scenario.yaml"
ASAT_SCENARIO = DATA_DIR / "scenarios/space_asat_escalation/scenario.yaml"
VARIANT = AnalysisVariant(variant_id="nested-runtime-failure-policy")
TOT_MISSION_ID = "blue_validation_tot"
ASAT_ORDER_ID = "red_keyhole_strike_1"
ASAT_TARGET_ID = "keyhole_optical_p0_s0"


@pytest.fixture(scope="module")
def base_prepared() -> PreparedScenario:
    return SimulationRuntimeFactory().prepare(
        BASE_SCENARIO,
        DATA_DIR,
        (VARIANT,),
    )


@pytest.fixture(scope="module")
def tot_prepared() -> PreparedScenario:
    return SimulationRuntimeFactory().prepare(
        TOT_SCENARIO,
        DATA_DIR,
        (VARIANT,),
    )


@pytest.fixture(scope="module")
def asat_prepared() -> PreparedScenario:
    return SimulationRuntimeFactory().prepare(
        ASAT_SCENARIO,
        DATA_DIR,
        (VARIANT,),
    )


def _build(
    prepared: PreparedScenario,
    *,
    mode: RuntimeExecutionMode = RuntimeExecutionMode.STRICT,
    max_ticks: int = 1,
    record_events: bool = False,
    recorder_factory: (Callable[[SimulationContext], SimulationRecorder] | None) = None,
    seed: int = 7,
) -> RuntimeSession:
    return prepared.build(
        VARIANT.variant_id,
        seed=seed,
        max_ticks=max_ticks,
        execution_mode=mode,
        record_events=record_events,
        recorder_factory=recorder_factory,
    )


def _assert_strict_failure_latched(
    session: RuntimeSession,
    failure: Exception,
) -> None:
    assert session.engine.suppressed_failures == ()
    for rejected_operation in (
        session.step,
        session.finalize,
        session.engine.checkpoint,
        session.provenance,
    ):
        with pytest.raises(type(failure)) as rejected:
            rejected_operation()
        assert rejected.value is failure


def _assert_one_degraded_failure(
    session: RuntimeSession,
    *,
    subsystem: str,
    operation: str,
) -> None:
    failures = session.engine.suppressed_failures
    assert len(failures) == 1
    assert isinstance(failures[0], SuppressedRuntimeFailure)
    assert failures[0].subsystem == subsystem
    assert failures[0].operation == operation
    provenance = session.provenance()
    assert provenance.suppressed_failures == failures
    assert provenance.authoritative is False


def _hf_equipment() -> CommEquipmentDefinition:
    return CommEquipmentDefinition(
        comm_id="runtime_failure_hf",
        comm_type="RADIO_HF",
        display_name="Runtime failure HF control",
        max_range_m=100_000.0,
        bandwidth_bps=1_000.0,
        base_latency_s=0.1,
        base_reliability=0.9,
        intercept_risk=0.2,
        jam_resistance=0.8,
        requires_los=False,
    )


def _channel_reliability(comms: CommunicationsEngine) -> float:
    return comms._channel_reliability(
        _hf_equipment(),
        Position(0.0, 0.0, 0.0),
        Position(1_000.0, 0.0, 0.0),
        EmconState.RADIATE,
    )


@pytest.mark.parametrize(
    "prepared_fixture",
    ("base_prepared", "tot_prepared", "asat_prepared"),
)
def test_runtime_failure_policy_wiring_is_checkpoint_transparent(
    request: pytest.FixtureRequest,
    prepared_fixture: str,
) -> None:
    prepared = request.getfixturevalue(prepared_fixture)
    session = _build(prepared, record_events=True)

    checkpoint = session.engine.checkpoint()
    session.engine.restore(checkpoint)

    assert session.engine.checkpoint() == checkpoint
    session.engine.assert_evidence_healthy()


class _FailingEMEnvironment:
    def __init__(self, failure: Exception) -> None:
        self._failure = failure

    def hf_propagation_quality(self) -> float:
        raise self._failure


class _BrokenPayload:
    def __init__(self, failure: Exception) -> None:
        self._failure = failure

    def __deepcopy__(self, _memo: dict[int, object]) -> object:
        raise self._failure


@dataclass(frozen=True)
class _BrokenRecorderEvent(Event):
    payload: object


class _FailingInventory:
    def __init__(self, failure: Exception) -> None:
        self._failure = failure

    def get_state(self) -> dict[str, object]:
        raise self._failure


class _FailingOrderRecord:
    def __init__(self, failure: Exception) -> None:
        self._failure = failure

    def get_state(self) -> dict[str, object]:
        raise self._failure


def test_missing_optional_em_owner_retains_neutral_behavior(
    base_prepared: PreparedScenario,
) -> None:
    session = _build(base_prepared)
    comms = session.context.comms_engine
    original_environment = comms._em_environment
    comms.set_em_environment(None)
    try:
        assert _channel_reliability(comms) == pytest.approx(0.9)
    finally:
        comms.set_em_environment(original_environment)
    assert session.engine.suppressed_failures == ()


def test_strict_em_propagation_failure_preserves_root_exception(
    base_prepared: PreparedScenario,
) -> None:
    session = _build(base_prepared)
    failure = RuntimeError("EM propagation owner failed")
    session.context.comms_engine.set_em_environment(
        _FailingEMEnvironment(failure),
    )

    with pytest.raises(RuntimeError) as caught:
        _channel_reliability(session.context.comms_engine)

    assert caught.value is failure
    later_failure = RuntimeError("later EM propagation owner failure")
    session.context.comms_engine.set_em_environment(
        _FailingEMEnvironment(later_failure),
    )
    with pytest.raises(RuntimeError) as later:
        _channel_reliability(session.context.comms_engine)
    assert later.value is later_failure
    _assert_strict_failure_latched(session, failure)


def test_degraded_em_propagation_fallback_is_explicit_evidence(
    base_prepared: PreparedScenario,
) -> None:
    session = _build(base_prepared, mode=RuntimeExecutionMode.DEGRADED)
    comms = session.context.comms_engine
    original_environment = comms._em_environment
    comms.set_em_environment(None)
    baseline = _channel_reliability(comms)
    comms.set_em_environment(
        _FailingEMEnvironment(RuntimeError("EM propagation owner failed")),
    )

    assert _channel_reliability(comms) == baseline
    comms.set_em_environment(original_environment)

    _assert_one_degraded_failure(
        session,
        subsystem="c2.communications",
        operation="apply_em_propagation",
    )


def test_missing_optional_gps_owner_retains_documented_cep(
    asat_prepared: PreparedScenario,
) -> None:
    session = _build(asat_prepared, max_ticks=2, seed=42)
    space = session.context.space_engine
    original_gps = space._gps_engine
    space._gps_engine = None
    try:
        assert space.get_gps_cep("blue", 0.0) == 100.0
    finally:
        space._gps_engine = original_gps
    assert session.engine.suppressed_failures == ()


def test_strict_enabled_gps_fault_preserves_root_exception(
    asat_prepared: PreparedScenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _build(asat_prepared, max_ticks=2, seed=42)
    failure = RuntimeError("GPS accuracy owner failed")

    def fail(_side: str, _sim_time_s: float) -> object:
        raise failure

    monkeypatch.setattr(
        session.context.space_engine.gps_engine,
        "compute_gps_accuracy",
        fail,
    )

    with pytest.raises(RuntimeError) as caught:
        session.context.space_engine.get_gps_cep("blue", 0.0)

    assert caught.value is failure
    _assert_strict_failure_latched(session, failure)


def test_degraded_enabled_gps_fault_uses_non_authoritative_cep(
    asat_prepared: PreparedScenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _build(
        asat_prepared,
        mode=RuntimeExecutionMode.DEGRADED,
        max_ticks=2,
        seed=42,
    )
    space = session.context.space_engine
    failure = RuntimeError("GPS accuracy owner failed")

    def fail(_side: str, _sim_time_s: float) -> object:
        raise failure

    monkeypatch.setattr(
        space.gps_engine,
        "compute_gps_accuracy",
        fail,
    )

    assert space.get_gps_cep("blue", 0.0) == 100.0
    monkeypatch.undo()

    _assert_one_degraded_failure(
        session,
        subsystem="space.gps",
        operation="get_cep",
    )


def test_runtime_recorder_factory_rejects_wrong_event_bus(
    base_prepared: PreparedScenario,
) -> None:
    with pytest.raises(ValueError, match="SimulationContext event bus"):
        _build(
            base_prepared,
            recorder_factory=lambda _context: SimulationRecorder(EventBus()),
        )


def test_runtime_recorder_factory_rejects_disabled_recorder(
    base_prepared: PreparedScenario,
) -> None:
    with pytest.raises(ValueError, match="must be enabled"):
        _build(
            base_prepared,
            recorder_factory=lambda context: SimulationRecorder(
                context.event_bus,
                RecorderConfig(enabled=False),
            ),
        )


def test_runtime_recorder_factory_rejects_prebinding_event_loss(
    base_prepared: PreparedScenario,
) -> None:
    def recorder_factory(context: SimulationContext) -> SimulationRecorder:
        recorder = SimulationRecorder(
            context.event_bus,
            RecorderConfig(max_events=1),
        )
        recorder.start()
        context.event_bus.publish(
            Event(timestamp=context.clock.current_time, source=ModuleId.CORE),
        )
        context.event_bus.publish(
            Event(timestamp=context.clock.current_time, source=ModuleId.CORE),
        )
        recorder.stop()
        return recorder

    with pytest.raises(RuntimeError, match="event limit exceeded"):
        _build(base_prepared, recorder_factory=recorder_factory)


def test_strict_recorder_overflow_latches_exact_generated_failure(
    base_prepared: PreparedScenario,
) -> None:
    session = _build(
        base_prepared,
        recorder_factory=lambda context: SimulationRecorder(
            context.event_bus,
            RecorderConfig(max_events=1),
        ),
    )
    recorder = session.recorder
    assert recorder is not None
    recorder.start()
    event = Event(
        timestamp=session.context.clock.current_time,
        source=ModuleId.CORE,
    )
    session.context.event_bus.publish(event)

    with pytest.raises(RuntimeError, match="event limit exceeded") as caught:
        session.context.event_bus.publish(event)

    recorder.stop()
    _assert_strict_failure_latched(session, caught.value)


def test_degraded_recorder_overflow_is_typed_and_non_authoritative(
    base_prepared: PreparedScenario,
) -> None:
    session = _build(
        base_prepared,
        mode=RuntimeExecutionMode.DEGRADED,
        recorder_factory=lambda context: SimulationRecorder(
            context.event_bus,
            RecorderConfig(max_events=1),
        ),
    )
    recorder = session.recorder
    assert recorder is not None
    recorder.start()
    event = Event(
        timestamp=session.context.clock.current_time,
        source=ModuleId.CORE,
    )
    session.context.event_bus.publish(event)
    session.context.event_bus.publish(event)
    session.context.event_bus.publish(event)
    recorder.stop()

    assert len(recorder.events) == 1
    _assert_one_degraded_failure(
        session,
        subsystem="simulation.recorder",
        operation="record_event_overflow",
    )


def test_strict_recorder_extraction_preserves_payload_exception(
    base_prepared: PreparedScenario,
) -> None:
    session = _build(base_prepared, record_events=True)
    recorder = session.recorder
    assert recorder is not None
    failure = RuntimeError("recorder payload deepcopy failed")
    recorder.start()

    with pytest.raises(RuntimeError) as caught:
        session.context.event_bus.publish(
            _BrokenRecorderEvent(
                timestamp=session.context.clock.current_time,
                source=ModuleId.CORE,
                payload=_BrokenPayload(failure),
            ),
        )

    recorder.stop()
    assert caught.value is failure
    assert recorder.events == []
    _assert_strict_failure_latched(session, failure)


def test_degraded_recorder_extraction_emits_nonempty_integrity_record(
    base_prepared: PreparedScenario,
) -> None:
    session = _build(
        base_prepared,
        mode=RuntimeExecutionMode.DEGRADED,
        record_events=True,
    )
    recorder = session.recorder
    assert recorder is not None
    recorder.start()
    session.context.event_bus.publish(
        _BrokenRecorderEvent(
            timestamp=session.context.clock.current_time,
            source=ModuleId.CORE,
            payload=_BrokenPayload(
                RuntimeError("recorder payload deepcopy failed"),
            ),
        ),
    )
    recorder.stop()

    assert recorder.events[0].data == {
        "recorder_integrity_error": {
            "exception_type": "builtins.RuntimeError",
            "message": "recorder payload deepcopy failed",
        },
    }
    _assert_one_degraded_failure(
        session,
        subsystem="simulation.recorder",
        operation="extract_event_data",
    )


def test_strict_tot_observer_failure_occurs_after_committed_notification(
    tot_prepared: PreparedScenario,
) -> None:
    session = _build(
        tot_prepared,
        max_ticks=25,
        record_events=True,
        seed=42,
    )
    failure = RuntimeError("time-on-target observer failed")

    def fail(_event: Event) -> None:
        raise failure

    session.context.event_bus.subscribe(TimeOnTargetMissionEvent, fail)

    with pytest.raises(RuntimeError) as caught:
        session.run_to_completion()

    assert caught.value is failure
    mission = session.context.indirect_fire_engine.get_state()["missions"][0]
    assert mission["mission_id"] == TOT_MISSION_ID
    assert mission["status"] == "completed"
    assert session.recorder is not None
    assert [
        event.event_type for event in session.recorder.events if event.event_type == "TimeOnTargetMissionEvent"
    ] == ["TimeOnTargetMissionEvent"]
    _assert_strict_failure_latched(session, failure)


def test_degraded_tot_observer_failure_records_one_ordered_failure(
    tot_prepared: PreparedScenario,
) -> None:
    session = _build(
        tot_prepared,
        mode=RuntimeExecutionMode.DEGRADED,
        max_ticks=25,
        record_events=True,
        seed=42,
    )

    def fail(_event: Event) -> None:
        raise RuntimeError("time-on-target observer failed")

    session.context.event_bus.subscribe(TimeOnTargetMissionEvent, fail)

    result = session.run_to_completion()

    mission = session.context.indirect_fire_engine.get_state()["missions"][0]
    assert mission["mission_id"] == TOT_MISSION_ID
    assert mission["status"] == "completed"
    assert session.recorder is not None
    assert [
        event.event_type for event in session.recorder.events if event.event_type == "TimeOnTargetMissionEvent"
    ] == ["TimeOnTargetMissionEvent"]
    _assert_one_degraded_failure(
        session,
        subsystem="combat.indirect_fire",
        operation="publish_committed_event",
    )
    assert result.suppressed_failures == session.engine.suppressed_failures
    assert result.authoritative is False


def test_strict_asat_observer_failure_occurs_after_committed_notification(
    asat_prepared: PreparedScenario,
) -> None:
    session = _build(
        asat_prepared,
        max_ticks=2,
        record_events=True,
        seed=42,
    )
    failure = RuntimeError("ASAT observer failed")

    def fail(_event: Event) -> None:
        raise failure

    session.context.event_bus.subscribe(ASATEngagementEvent, fail)

    with pytest.raises(RuntimeError) as caught:
        session.run_to_completion()

    assert caught.value is failure
    asat_state = session.context.space_engine.asat_engine.get_state()
    assert list(asat_state["completed_orders"]) == [ASAT_ORDER_ID]
    target = session.context.space_engine.constellation_manager.get_satellite(
        ASAT_TARGET_ID,
    )
    assert target is not None and target.is_active is False
    assert session.recorder is not None
    assert [event.event_type for event in session.recorder.events if event.event_type == "ASATEngagementEvent"] == [
        "ASATEngagementEvent"
    ]
    _assert_strict_failure_latched(session, failure)


def test_degraded_asat_observer_failure_records_one_ordered_failure(
    asat_prepared: PreparedScenario,
) -> None:
    session = _build(
        asat_prepared,
        mode=RuntimeExecutionMode.DEGRADED,
        max_ticks=2,
        record_events=True,
        seed=42,
    )

    def fail(_event: Event) -> None:
        raise RuntimeError("ASAT observer failed")

    session.context.event_bus.subscribe(ASATEngagementEvent, fail)

    result = session.run_to_completion()

    asat_state = session.context.space_engine.asat_engine.get_state()
    assert list(asat_state["completed_orders"]) == [ASAT_ORDER_ID]
    target = session.context.space_engine.constellation_manager.get_satellite(
        ASAT_TARGET_ID,
    )
    assert target is not None and target.is_active is False
    assert session.recorder is not None
    assert [event.event_type for event in session.recorder.events if event.event_type == "ASATEngagementEvent"] == [
        "ASATEngagementEvent"
    ]
    _assert_one_degraded_failure(
        session,
        subsystem="space.asat",
        operation="publish_committed_event",
    )
    assert result.suppressed_failures == session.engine.suppressed_failures
    assert result.authoritative is False


@pytest.mark.parametrize(
    ("site", "subsystem", "operation"),
    (
        (
            "supply_inventory",
            "logistics.stockpile",
            "snapshot_supply_inventory",
        ),
        ("order_lookup", "c2.order_execution", "snapshot_orders"),
        ("order_record", "c2.order_execution", "snapshot_order_record"),
    ),
)
@pytest.mark.parametrize(
    "mode",
    (RuntimeExecutionMode.STRICT, RuntimeExecutionMode.DEGRADED),
)
def test_aggregation_snapshot_faults_follow_runtime_policy(
    base_prepared: PreparedScenario,
    monkeypatch: pytest.MonkeyPatch,
    site: str,
    subsystem: str,
    operation: str,
    mode: RuntimeExecutionMode,
) -> None:
    session = _build(base_prepared, mode=mode)
    context = session.context
    unit = context.units_by_side["blue"][0]
    failure = RuntimeError(f"aggregation {site} failed")

    if site == "supply_inventory":
        monkeypatch.setattr(
            context.stockpile_manager,
            "has_unit_inventory",
            lambda _unit_id: True,
        )
        monkeypatch.setattr(
            context.stockpile_manager,
            "get_unit_inventory",
            lambda _unit_id: _FailingInventory(failure),
        )
    elif site == "order_lookup":
        monkeypatch.setattr(
            context.order_execution,
            "get_active_orders",
            lambda _unit_id: (_ for _ in ()).throw(failure),
        )
    else:
        monkeypatch.setattr(
            context.order_execution,
            "get_active_orders",
            lambda _unit_id: [_FailingOrderRecord(failure)],
        )
        monkeypatch.setattr(
            context.order_execution,
            "get_pending_orders",
            lambda _unit_id: [],
        )

    if mode is RuntimeExecutionMode.STRICT:
        with pytest.raises(RuntimeError) as caught:
            context.aggregation_engine.snapshot_unit(
                unit,
                context,
                failure_handler=session.engine._suppress_runtime_failure,
            )
        assert caught.value is failure
        monkeypatch.undo()
        _assert_strict_failure_latched(session, failure)
        return

    snapshot = context.aggregation_engine.snapshot_unit(
        unit,
        context,
        failure_handler=session.engine._suppress_runtime_failure,
    )
    assert snapshot.supply_inventory is None
    assert snapshot.order_records == []
    monkeypatch.undo()

    _assert_one_degraded_failure(
        session,
        subsystem=subsystem,
        operation=operation,
    )
