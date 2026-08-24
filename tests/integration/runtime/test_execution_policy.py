"""Production runtime contracts for strict and degraded execution."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from stochastic_warfare.simulation.engine import (
    RuntimeExecutionMode,
    SuppressedRuntimeFailure,
    TickResolution,
)
from stochastic_warfare.simulation.runtime import (
    AnalysisVariant,
    PreparedScenario,
    RuntimeSession,
    SimulationRuntimeFactory,
)
from stochastic_warfare.tools.serializers import serialize_to_dict


ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data"
SCENARIO = DATA_DIR / "scenarios/test_campaign/scenario.yaml"
VARIANT = AnalysisVariant(variant_id="runtime-execution-policy")
BATTLE_VARIANT = AnalysisVariant(
    variant_id="battle-execution-policy",
    calibration_patch={"enable_fog_of_war": True},
)


@pytest.fixture
def prepared() -> PreparedScenario:
    return SimulationRuntimeFactory().prepare(
        SCENARIO,
        DATA_DIR,
        (VARIANT, BATTLE_VARIANT),
    )


def _session(
    prepared: PreparedScenario,
    *,
    mode: RuntimeExecutionMode = RuntimeExecutionMode.STRICT,
    max_ticks: int = 1,
    variant: AnalysisVariant = VARIANT,
) -> RuntimeSession:
    return prepared.build(
        variant.variant_id,
        seed=7,
        max_ticks=max_ticks,
        execution_mode=mode,
    )


def _force_one_observe_completion(session: RuntimeSession) -> None:
    state = next(iter(session.context.ooda_engine._commanders.values()))
    state.phase_timer = 1.0
    state.phase_duration = 1.0


def _inject_battle_failure(
    session: RuntimeSession,
    monkeypatch: pytest.MonkeyPatch,
    *,
    site: str,
    failure: Exception,
) -> None:
    manager = session.engine.battle_manager
    context = session.context

    if site == "ooda":
        _force_one_observe_completion(session)
        original_interval = manager.execute_ooda_interval
        original_world_view = context.fog_of_war.get_world_view
        raised = False

        def fail_world_view(*args: object, **kwargs: object):
            nonlocal raised
            if not raised:
                raised = True
                raise failure
            return original_world_view(*args, **kwargs)

        def inject_before_ooda(*args: object, **kwargs: object):
            monkeypatch.setattr(
                context.fog_of_war,
                "get_world_view",
                fail_world_view,
            )
            return original_interval(*args, **kwargs)

        monkeypatch.setattr(
            manager,
            "execute_ooda_interval",
            inject_before_ooda,
        )
        return

    if site == "movement":
        original_executor = manager._movement_executor
        original_readiness = context.maintenance_engine.get_unit_readiness
        raised = False

        def fail_readiness(*args: object, **kwargs: object):
            nonlocal raised
            if not raised:
                raised = True
                raise failure
            return original_readiness(*args, **kwargs)

        def inject_before_movement(owner: object, request: object):
            monkeypatch.setattr(
                context.maintenance_engine,
                "get_unit_readiness",
                fail_readiness,
            )
            return original_executor.execute(owner, request)

        manager._movement_executor = SimpleNamespace(
            execute=inject_before_movement,
        )
        return

    if site == "engagement":
        raised = False

        def fail_mopp(*_args: object, **_kwargs: object):
            nonlocal raised
            if not raised:
                raised = True
                raise failure
            return None, 1.0, 1.0

        context.cbrn_engine = SimpleNamespace(
            get_mopp_level=lambda _unit_id: 0,
            get_mopp_effects=fail_mopp,
        )
        return

    if site == "facade":
        _force_one_observe_completion(session)
        original_interval = manager.execute_ooda_interval
        original_effectiveness = (
            context.comms_engine.compute_c2_effectiveness
        )
        raised = False

        def fail_effectiveness(*args: object, **kwargs: object):
            nonlocal raised
            if not raised:
                raised = True
                raise failure
            return original_effectiveness(*args, **kwargs)

        def inject_before_ooda(*args: object, **kwargs: object):
            monkeypatch.setattr(
                context.comms_engine,
                "compute_c2_effectiveness",
                fail_effectiveness,
            )
            return original_interval(*args, **kwargs)

        monkeypatch.setattr(
            manager,
            "execute_ooda_interval",
            inject_before_ooda,
        )
        return

    raise AssertionError(f"unknown battle failure site: {site}")


def _fail_weather_update(
    session: RuntimeSession,
    failure: Exception,
) -> None:
    current = session.context.weather_engine.current

    def fail(_dt: float) -> None:
        raise failure

    session.context.weather_engine = SimpleNamespace(
        current=current,
        update=fail,
    )


def test_prepared_runtime_defaults_to_strict_and_preserves_exception(
    prepared: PreparedScenario,
) -> None:
    session = _session(prepared)
    failure = RuntimeError("weather contract failure")
    _fail_weather_update(session, failure)

    assert session.engine.execution_mode is RuntimeExecutionMode.STRICT
    with pytest.raises(RuntimeError) as caught:
        session.run_to_completion()

    assert caught.value is failure
    assert session.engine.suppressed_failures == ()
    for rejected_operation in (
        session.step,
        session.finalize,
        session.engine.checkpoint,
    ):
        with pytest.raises(RuntimeError) as rejected:
            rejected_operation()
        assert rejected.value is failure


def test_explicit_degraded_mode_publishes_typed_result_and_provenance(
    prepared: PreparedScenario,
) -> None:
    session = _session(prepared, mode=RuntimeExecutionMode.DEGRADED)
    _fail_weather_update(session, RuntimeError("weather contract failure"))

    result = session.run_to_completion()
    provenance = session.provenance()

    assert result.execution_mode is RuntimeExecutionMode.DEGRADED
    assert provenance.execution_mode is RuntimeExecutionMode.DEGRADED
    assert len(result.suppressed_failures) == 1
    failure = result.suppressed_failures[0]
    assert isinstance(failure, SuppressedRuntimeFailure)
    assert failure == SuppressedRuntimeFailure(
        sequence=0,
        tick=1,
        logical_time_s=session.context.clock.elapsed.total_seconds(),
        subsystem="environment.weather",
        operation="update",
        exception_type="builtins.RuntimeError",
        message="weather contract failure",
    )
    assert provenance.suppressed_failures == result.suppressed_failures
    assert result.authoritative is False
    assert provenance.authoritative is False
    serialized = serialize_to_dict(provenance)
    assert serialized["execution_mode"] == "degraded"
    assert serialized["suppressed_failures"][0]["operation"] == "update"


def test_degraded_failure_evidence_is_deterministic(
    prepared: PreparedScenario,
) -> None:
    evidence: list[tuple[SuppressedRuntimeFailure, ...]] = []
    for _ in range(2):
        session = _session(prepared, mode=RuntimeExecutionMode.DEGRADED)
        _fail_weather_update(session, RuntimeError("repeatable failure"))
        evidence.append(session.run_to_completion().suppressed_failures)

    assert evidence[0] == evidence[1]


def test_strict_scripted_event_dispatch_preserves_exception(
    prepared: PreparedScenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session(prepared)
    failure = RuntimeError("scripted dispatch failure")
    session.context.scripted_events = [
        SimpleNamespace(time_s=0.0, event_type="forced_failure"),
    ]
    session.context._fired_scripted_events = set()

    def fail(*_args: object) -> None:
        raise failure

    monkeypatch.setattr(
        session.engine.campaign_manager,
        "_dispatch_scripted_event",
        fail,
    )

    with pytest.raises(RuntimeError) as caught:
        session.step()

    assert caught.value is failure
    assert session.context._fired_scripted_events == set()


def test_degraded_scripted_event_failure_is_recorded_once(
    prepared: PreparedScenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session(prepared, mode=RuntimeExecutionMode.DEGRADED)
    session.context.scripted_events = [
        SimpleNamespace(time_s=0.0, event_type="forced_failure"),
    ]
    session.context._fired_scripted_events = set()

    def fail(*_args: object) -> None:
        raise RuntimeError("scripted dispatch failure")

    monkeypatch.setattr(
        session.engine.campaign_manager,
        "_dispatch_scripted_event",
        fail,
    )

    result = session.run_to_completion()

    assert session.context._fired_scripted_events == {0}
    assert len(result.suppressed_failures) == 1
    assert result.suppressed_failures[0].subsystem == "simulation.campaign"
    assert result.suppressed_failures[0].operation == "dispatch_scripted_event"


@pytest.mark.parametrize("operation", ["capture", "restore"])
def test_degraded_mode_rejects_authoritative_checkpoint_operations(
    prepared: PreparedScenario,
    operation: str,
) -> None:
    session = _session(prepared, mode=RuntimeExecutionMode.DEGRADED)

    with pytest.raises(RuntimeError, match="Degraded runtimes cannot"):
        if operation == "capture":
            session.engine.checkpoint()
        else:
            session.engine.restore(b"{}")


def test_strict_checkpoint_retains_format_118_topology(
    prepared: PreparedScenario,
) -> None:
    source = _session(prepared)
    checkpoint = source.engine.checkpoint()
    restored = _session(prepared)

    restored.engine.restore(checkpoint)

    state = restored.engine.get_state()
    assert state["checkpoint_version"] == 118
    assert "runtime_failure_policy" not in state
    assert restored.engine.suppressed_failures == ()


def test_planning_advances_before_ooda_on_a_tactical_interval(
    prepared: PreparedScenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session(prepared, max_ticks=2)
    planning = session.context.planning_engine
    battle = session.engine.battle_manager
    original_update = planning.update
    original_execute_tick = battle.execute_tick
    order: list[str] = []

    def update(*args: object, **kwargs: object):
        order.append("planning")
        return original_update(*args, **kwargs)

    def execute_tick(*args: object, **kwargs: object):
        order.append("ooda")
        return original_execute_tick(*args, **kwargs)

    monkeypatch.setattr(planning, "update", update)
    monkeypatch.setattr(battle, "execute_tick", execute_tick)

    assert session.engine.resolution is TickResolution.TACTICAL
    session.step()

    assert order[0] == "planning"
    assert "ooda" in order


def test_strict_planning_update_failure_preserves_exception(
    prepared: PreparedScenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session(prepared)
    failure = RuntimeError("planning update failure")

    def fail(*_args: object, **_kwargs: object) -> None:
        raise failure

    monkeypatch.setattr(session.context.planning_engine, "update", fail)

    with pytest.raises(RuntimeError) as caught:
        session.step()

    assert caught.value is failure
    assert session.engine.suppressed_failures == ()


def test_degraded_planning_update_failure_is_typed_evidence(
    prepared: PreparedScenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session(prepared, mode=RuntimeExecutionMode.DEGRADED)

    def fail(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("planning update failure")

    monkeypatch.setattr(session.context.planning_engine, "update", fail)

    result = session.run_to_completion()

    assert len(result.suppressed_failures) == 1
    assert result.suppressed_failures[0].subsystem == "c2.planning"
    assert result.suppressed_failures[0].operation == "update"


_BATTLE_FAILURE_CASES = (
    (
        "ooda",
        BATTLE_VARIANT,
        "detection.fog_of_war",
        "get_world_view",
    ),
    (
        "movement",
        VARIANT,
        "logistics.maintenance",
        "get_unit_readiness",
    ),
    (
        "engagement",
        VARIANT,
        "cbrn.protection",
        "get_mopp_effects",
    ),
    (
        "facade",
        VARIANT,
        "c2.communications",
        "compute_c2_effectiveness",
    ),
)


@pytest.mark.parametrize(
    ("site", "variant", "subsystem", "operation"),
    _BATTLE_FAILURE_CASES,
)
def test_strict_battle_fallback_preserves_original_exception(
    prepared: PreparedScenario,
    monkeypatch: pytest.MonkeyPatch,
    site: str,
    variant: AnalysisVariant,
    subsystem: str,
    operation: str,
) -> None:
    del subsystem, operation
    session = _session(prepared, variant=variant)
    failure = RuntimeError(f"{site} battle contract failure")
    _inject_battle_failure(
        session,
        monkeypatch,
        site=site,
        failure=failure,
    )

    with pytest.raises(RuntimeError) as caught:
        session.step()

    assert caught.value is failure
    assert session.engine.suppressed_failures == ()
    with pytest.raises(RuntimeError) as rejected:
        session.step()
    assert rejected.value is failure


@pytest.mark.parametrize(
    ("site", "variant", "subsystem", "operation"),
    _BATTLE_FAILURE_CASES,
)
def test_degraded_battle_fallback_is_typed_non_authoritative_evidence(
    prepared: PreparedScenario,
    monkeypatch: pytest.MonkeyPatch,
    site: str,
    variant: AnalysisVariant,
    subsystem: str,
    operation: str,
) -> None:
    session = _session(
        prepared,
        mode=RuntimeExecutionMode.DEGRADED,
        variant=variant,
    )
    failure = RuntimeError(f"{site} battle contract failure")
    _inject_battle_failure(
        session,
        monkeypatch,
        site=site,
        failure=failure,
    )

    result = session.run_to_completion()
    provenance = session.provenance()

    assert result.suppressed_failures == (
        SuppressedRuntimeFailure(
            sequence=0,
            tick=1,
            logical_time_s=session.context.clock.elapsed.total_seconds(),
            subsystem=subsystem,
            operation=operation,
            exception_type="builtins.RuntimeError",
            message=f"{site} battle contract failure",
        ),
    )
    assert provenance.suppressed_failures == result.suppressed_failures
    assert result.authoritative is False
    assert provenance.authoritative is False


def test_execution_mode_requires_typed_enum(
    prepared: PreparedScenario,
) -> None:
    with pytest.raises(TypeError, match="RuntimeExecutionMode"):
        prepared.build(
            VARIANT.variant_id,
            seed=7,
            max_ticks=1,
            execution_mode="degraded",  # type: ignore[arg-type]
        )


def test_explicit_legacy_and_typed_mode_disagreement_rejects(
    prepared: PreparedScenario,
) -> None:
    with pytest.raises(ValueError, match="strict_mode and execution_mode disagree"):
        prepared.build(
            VARIANT.variant_id,
            seed=7,
            max_ticks=1,
            strict_mode=False,
            execution_mode=RuntimeExecutionMode.STRICT,
        )


def test_post_commit_strict_failure_rejects_all_evidence_exposure(
    prepared: PreparedScenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session(prepared)
    failure = RuntimeError("reinforcement boundary failure")

    def fail(*_args: object, **_kwargs: object) -> None:
        raise failure

    monkeypatch.setattr(
        session.engine.campaign_manager,
        "check_reinforcements",
        fail,
    )

    with pytest.raises(RuntimeError) as caught:
        session.step()
    assert caught.value is failure
    assert session.context.clock.tick_count == 1

    for rejected_operation in (
        session.step,
        session.finalize,
        session.engine.checkpoint,
        session.provenance,
    ):
        with pytest.raises(RuntimeError) as rejected:
            rejected_operation()
        assert rejected.value is failure
