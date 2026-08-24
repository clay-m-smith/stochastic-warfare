"""Production contracts for global, battle-owned deferred OODA decisions."""

from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from stochastic_warfare.c2.ai.assessment import (
    AssessmentRating,
    SituationAssessment,
)
from stochastic_warfare.c2.ai.ooda import OODAConfig, OODALoopEngine, OODAPhase
from stochastic_warfare.c2.orders.propagation import PropagationResult
from stochastic_warfare.c2.planning.process import PlanningPhase
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.simulation.battle import BattleContext
from stochastic_warfare.simulation.runtime import (
    AnalysisVariant,
    PreparedScenario,
    RuntimeSession,
    SimulationRuntimeFactory,
)


ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data"
SCENARIO = DATA_DIR / "scenarios/test_campaign/scenario.yaml"
DEFAULT_VARIANT = "deferred-ooda-default"
C2_VARIANT = "deferred-ooda-c2"
TEST_SEED = 7


@pytest.fixture(scope="module")
def prepared() -> PreparedScenario:
    return SimulationRuntimeFactory().prepare(
        SCENARIO,
        DATA_DIR,
        (
            AnalysisVariant(variant_id=DEFAULT_VARIANT),
            AnalysisVariant(
                variant_id=C2_VARIANT,
                calibration_patch={
                    "enable_c2_friction": True,
                    "c2_min_effectiveness": 0.0,
                    "planning_available_time_s": 60.0,
                },
            ),
        ),
    )


def _session(
    prepared: PreparedScenario,
    variant_id: str = C2_VARIANT,
) -> RuntimeSession:
    return prepared.build(
        variant_id,
        seed=TEST_SEED,
        max_ticks=12,
        strict_mode=True,
    )


def _assessment(unit_id: str, timestamp: datetime) -> SituationAssessment:
    rating = AssessmentRating.NEUTRAL
    return SituationAssessment(
        unit_id=unit_id,
        timestamp=timestamp,
        force_ratio=1.0,
        force_ratio_rating=rating,
        terrain_advantage=0.0,
        terrain_rating=rating,
        supply_level=1.0,
        supply_rating=rating,
        morale_level=1.0,
        morale_rating=rating,
        intel_quality=1.0,
        intel_rating=rating,
        environmental_rating=rating,
        c2_effectiveness=1.0,
        c2_rating=rating,
        overall_rating=rating,
        confidence=1.0,
        opportunities=(),
        threats=(),
    )


def _arm_decide(
    session: RuntimeSession,
    unit_ids: tuple[str, ...],
    *,
    timer_s: float = 0.0,
) -> None:
    ooda = session.context.ooda_engine
    assert ooda is not None
    state = ooda.get_state()
    commanders = state["commanders"]
    for raw in commanders.values():
        raw["phase"] = int(OODAPhase.OBSERVE)
        raw["phase_timer"] = 10_000.0
        raw["phase_duration"] = 10_000.0
    for unit_id in unit_ids:
        raw = commanders[unit_id]
        raw["phase"] = int(OODAPhase.DECIDE)
        raw["phase_timer"] = timer_s
        raw["phase_duration"] = max(timer_s, 1.0)
        session.engine.battle_manager._cached_assessments[unit_id] = _assessment(
            unit_id,
            session.context.clock.current_time,
        )
    ooda.set_state(state)


def _quiet_tactical_work(
    monkeypatch: pytest.MonkeyPatch,
    session: RuntimeSession,
) -> None:
    """Keep the production step coordinator while isolating post-OODA combat."""
    manager = session.engine.battle_manager

    def quiet_tick(_ctx: Any, battle: BattleContext, dt: float) -> None:
        battle.ticks_executed += 1
        battle.battle_elapsed_s += dt

    monkeypatch.setattr(manager, "execute_tick", quiet_tick)


def _patch_completed_planning(
    monkeypatch: pytest.MonkeyPatch,
    session: RuntimeSession,
) -> dict[str, int]:
    planning = session.context.planning_engine
    assert planning is not None
    calls = {"status": 0, "consume": 0}

    def status(_unit_id: str) -> PlanningPhase:
        calls["status"] += 1
        return PlanningPhase.COMPLETE

    def consume(_unit_id: str) -> str:
        calls["consume"] += 1
        return "ATTACK"

    monkeypatch.setattr(planning, "get_planning_status", status)
    monkeypatch.setattr(planning, "consume_result", consume)
    return calls


def _patch_propagation(
    monkeypatch: pytest.MonkeyPatch,
    session: RuntimeSession,
    result: PropagationResult,
) -> dict[str, int]:
    propagation = session.context.order_propagation
    assert propagation is not None
    calls = {"propagate": 0}

    def propagate(*_args: Any, **_kwargs: Any) -> PropagationResult:
        calls["propagate"] += 1
        return result

    monkeypatch.setattr(propagation, "propagate_order", propagate)
    return calls


def _patch_decision(
    monkeypatch: pytest.MonkeyPatch,
    session: RuntimeSession,
) -> list[str]:
    decision = session.context.decision_engine
    assert decision is not None
    calls: list[str] = []

    def decide(**kwargs: Any) -> None:
        calls.append(kwargs["unit_id"])

    monkeypatch.setattr(decision, "decide", decide)
    return calls


def _patch_stratagem(
    monkeypatch: pytest.MonkeyPatch,
    session: RuntimeSession,
    *,
    deception_viable: bool,
) -> dict[str, int]:
    stratagem = session.context.stratagem_engine
    assert stratagem is not None
    calls = {
        "expire": 0,
        "concentration": 0,
        "deception": 0,
        "plan": 0,
        "activate": 0,
    }

    def expire(*_args: Any, **_kwargs: Any) -> list[str]:
        calls["expire"] += 1
        return []

    def concentration(*_args: Any, **_kwargs: Any) -> tuple[bool, str]:
        calls["concentration"] += 1
        return False, ""

    def deception(*_args: Any, **_kwargs: Any) -> tuple[bool, str]:
        calls["deception"] += 1
        return deception_viable, ""

    def plan(*_args: Any, **_kwargs: Any) -> SimpleNamespace:
        calls["plan"] += 1
        return SimpleNamespace(stratagem_id="test-deception")

    def activate(*_args: Any, **_kwargs: Any) -> None:
        calls["activate"] += 1

    monkeypatch.setattr(stratagem, "expire_stratagems", expire)
    monkeypatch.setattr(
        stratagem,
        "evaluate_concentration_opportunity",
        concentration,
    )
    monkeypatch.setattr(
        stratagem,
        "evaluate_deception_opportunity",
        deception,
    )
    monkeypatch.setattr(stratagem, "plan_deception", plan)
    monkeypatch.setattr(stratagem, "activate_stratagem", activate)
    return calls


def _split_into_two_battles(session: RuntimeSession) -> tuple[BattleContext, BattleContext]:
    manager = session.engine.battle_manager
    first = manager.active_battles[0]
    units_by_id = {unit.entity_id: unit for units in session.context.units_by_side.values() for unit in units}
    blue = sorted(unit_id for unit_id in first.unit_ids if units_by_id[unit_id].side == "blue")
    red = sorted(unit_id for unit_id in first.unit_ids if units_by_id[unit_id].side == "red")
    first.unit_ids = set(blue[:2] + red[:3])
    second = BattleContext(
        battle_id="battle_0001",
        start_tick=first.start_tick,
        start_time=first.start_time,
        involved_sides=list(first.involved_sides),
        unit_ids=set(blue[2:] + red[3:]),
    )
    manager._battles[second.battle_id] = second
    manager._next_battle_id = 2
    return first, second


def _c2_rng_state(session: RuntimeSession) -> dict[str, Any]:
    state = session.context.rng_manager.get_state()
    return copy.deepcopy(state["streams"][ModuleId.C2.value])


def _checkpoint_bytes(state: dict[str, Any]) -> bytes:
    return json.dumps(
        state,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def test_step_updates_global_ooda_once_with_multiple_active_battles(
    prepared: PreparedScenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session(prepared, DEFAULT_VARIANT)
    _quiet_tactical_work(monkeypatch, session)
    first, second = _split_into_two_battles(session)
    target = sorted(first.unit_ids)[0]
    _arm_decide(session, (target,), timer_s=10.0)
    ooda = session.context.ooda_engine
    assert ooda is not None
    original_update = ooda.update
    calls = 0

    def update(dt_seconds: float, ts: datetime | None = None):
        nonlocal calls
        calls += 1
        return original_update(dt_seconds, ts=ts)

    monkeypatch.setattr(ooda, "update", update)

    session.step()

    target_state = ooda.get_state()["commanders"][target]
    assert calls == 1
    assert target_state["phase_timer"] == pytest.approx(5.0)
    assert session.context.clock.elapsed.total_seconds() == 5.0
    assert first.active and second.active


def test_step_preserves_simultaneous_new_completion_order(
    prepared: PreparedScenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session(prepared, DEFAULT_VARIANT)
    _quiet_tactical_work(monkeypatch, session)
    battle = session.engine.battle_manager.active_battles[0]
    lexical = sorted(battle.unit_ids)[:2]
    expected = (lexical[1], lexical[0])
    ooda = OODALoopEngine(
        session.context.event_bus,
        session.context.rng_manager.get_stream(ModuleId.C2),
        OODAConfig(
            base_durations_s={
                echelon: {phase.name: 1.0 for phase in OODAPhase}
                for echelon in (
                    "PLATOON",
                    "COMPANY",
                    "BATTALION",
                    "BRIGADE",
                    "DIVISION",
                    "CORPS",
                )
            },
            timing_sigma=0.0,
        ),
    )
    for unit_id in expected:
        ooda.register_commander(unit_id, 5)
        ooda.start_phase(
            unit_id,
            OODAPhase.DECIDE,
            ts=session.context.clock.current_time,
        )
    session.context.ooda_engine = ooda
    session.context.stratagem_engine = None
    decisions = _patch_decision(monkeypatch, session)

    session.step()

    assert decisions == list(expected)


def test_waiting_uses_global_clock_and_is_side_effect_free_until_maturity(
    prepared: PreparedScenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session(prepared)
    _quiet_tactical_work(monkeypatch, session)
    battle = session.engine.battle_manager.active_battles[0]
    target = sorted(battle.unit_ids)[0]
    battle.battle_elapsed_s = 100.0
    _arm_decide(session, (target,))
    planning = _patch_completed_planning(monkeypatch, session)
    propagation = _patch_propagation(
        monkeypatch,
        session,
        PropagationResult(True, 10.0, False, "", 1.0, False),
    )
    decisions = _patch_decision(monkeypatch, session)
    stratagem = _patch_stratagem(
        monkeypatch,
        session,
        deception_viable=True,
    )

    session.step()
    queue = session.engine.battle_manager.deferred_ooda_decisions
    assert [(record.unit_id, record.battle_id) for record in queue] == [
        (target, battle.battle_id),
    ]
    assert queue[0].due_elapsed_s == pytest.approx(15.0)
    waiting_rng = _c2_rng_state(session)

    session.step()

    assert session.context.clock.elapsed.total_seconds() == 10.0
    assert _c2_rng_state(session) == waiting_rng
    assert planning == {"status": 1, "consume": 0}
    assert propagation == {"propagate": 1}
    assert decisions == []
    assert all(value == 0 for value in stratagem.values())

    session.step()

    assert session.context.clock.elapsed.total_seconds() == 15.0
    assert planning == {"status": 1, "consume": 1}
    assert propagation == {"propagate": 1}
    assert decisions == [target]
    assert stratagem == {
        "expire": 1,
        "concentration": 1,
        "deception": 1,
        "plan": 1,
        "activate": 1,
    }
    assert session.engine.battle_manager.deferred_ooda_decisions == ()
    assert session.context.ooda_engine.get_phase(target) is OODAPhase.ACT


def test_full_checkpoint_restore_derives_owner_and_continues_exactly(
    prepared: PreparedScenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _session(prepared)
    _quiet_tactical_work(monkeypatch, source)
    battle = source.engine.battle_manager.active_battles[0]
    target = sorted(battle.unit_ids)[0]
    _arm_decide(source, (target,))
    _patch_completed_planning(monkeypatch, source)
    _patch_propagation(
        monkeypatch,
        source,
        PropagationResult(True, 10.0, False, "", 1.0, False),
    )
    _patch_decision(monkeypatch, source)
    _patch_stratagem(monkeypatch, source, deception_viable=False)
    source.step()
    checkpoint = source.engine.checkpoint()
    checkpoint_state = json.loads(checkpoint)
    assert checkpoint_state["checkpoint_version"] == 118
    assert checkpoint_state["battle"]["deferred_ooda_schema"] == 1
    assert "deferred_battle_ids" not in checkpoint_state["battle"]

    restored = _session(prepared)
    _quiet_tactical_work(monkeypatch, restored)
    _patch_decision(monkeypatch, restored)
    _patch_stratagem(monkeypatch, restored, deception_viable=False)
    restored.engine.restore(checkpoint)

    restored_queue = restored.engine.battle_manager.deferred_ooda_decisions
    assert len(restored_queue) == 1
    assert restored_queue[0].battle_id == battle.battle_id
    assert restored.engine.checkpoint() == checkpoint

    for _ in range(2):
        source.step()
        restored.step()

    assert source.engine.checkpoint() == restored.engine.checkpoint()
    assert source.engine.battle_manager.deferred_ooda_decisions == ()


def test_complete_planning_result_survives_propagated_wait_checkpoint(
    prepared: PreparedScenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _session(prepared)
    restored = _session(prepared)
    _quiet_tactical_work(monkeypatch, source)
    _quiet_tactical_work(monkeypatch, restored)
    battle = source.engine.battle_manager.active_battles[0]
    target = sorted(battle.unit_ids)[0]
    _arm_decide(source, (target,))
    source_propagation = _patch_propagation(
        monkeypatch,
        source,
        PropagationResult(True, 10.0, False, "", 1.0, False),
    )
    restored_propagation = _patch_propagation(
        monkeypatch,
        restored,
        PropagationResult(True, 999.0, False, "", 1.0, False),
    )
    _patch_stratagem(monkeypatch, source, deception_viable=False)
    _patch_stratagem(monkeypatch, restored, deception_viable=False)
    source_decisions = _patch_decision(monkeypatch, source)
    restored_decisions = _patch_decision(monkeypatch, restored)

    # First production interval starts the real planning process and binds its
    # expired DECIDE completion to the active battle.
    source.step()
    planning = source.context.planning_engine
    assert planning is not None
    assert planning.get_planning_status(target) not in {
        PlanningPhase.IDLE,
        PlanningPhase.COMPLETE,
    }
    planning.complete_planning(target, source.context.clock.current_time)

    # The next production interval observes COMPLETE, propagates exactly once,
    # and retains the selected planning result while the order delay waits.
    source.step()
    assert source_propagation == {"propagate": 1}
    checkpoint = source.engine.checkpoint()
    raw = json.loads(checkpoint)
    planning_state = raw["context"]["planning_engine"]
    assert planning_state["checkpoint_schema"] == 1
    assert planning_state["states"][target]["selected_result"] == {
        "kind": "planning_result",
        "value": "ATTACK",
    }

    restored.engine.restore(checkpoint)
    assert restored.engine.checkpoint() == checkpoint
    source_results: list[str | None] = []
    restored_results: list[str | None] = []
    restored_planning = restored.context.planning_engine
    assert restored_planning is not None
    original_source_consume = planning.consume_result
    original_restored_consume = restored_planning.consume_result

    def consume_source(unit_id: str) -> str | None:
        result = original_source_consume(unit_id)
        source_results.append(result)
        return result

    def consume_restored(unit_id: str) -> str | None:
        result = original_restored_consume(unit_id)
        restored_results.append(result)
        return result

    monkeypatch.setattr(planning, "consume_result", consume_source)
    monkeypatch.setattr(restored_planning, "consume_result", consume_restored)

    for _ in range(2):
        source.step()
        restored.step()

    assert source_results == ["ATTACK"]
    assert restored_results == source_results
    assert source_decisions == [target]
    assert restored_decisions == source_decisions
    assert restored_propagation == {"propagate": 0}
    assert restored.engine.checkpoint() == source.engine.checkpoint()


def test_markerless_format_118_pending_state_migrates_to_global_time(
    prepared: PreparedScenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _session(prepared)
    _quiet_tactical_work(monkeypatch, source)
    manager = source.engine.battle_manager
    battle = manager.active_battles[0]
    target = sorted(battle.unit_ids)[0]
    battle.battle_elapsed_s = 100.0
    _arm_decide(source, (target,))
    _patch_completed_planning(monkeypatch, source)
    _patch_propagation(
        monkeypatch,
        source,
        PropagationResult(True, 10.0, False, "", 1.0, False),
    )
    _patch_decision(monkeypatch, source)
    _patch_stratagem(monkeypatch, source, deception_viable=False)
    source.step()

    markerless = json.loads(source.engine.checkpoint())
    assert markerless["checkpoint_version"] == 118
    markerless_battle = markerless["battle"]
    markerless_battle.pop("deferred_ooda_schema")
    # Pre-marker format 118 stored this deadline on the owning battle clock.
    markerless_battle["pending_decisions"][target] = 115.0
    # Correctly interpreted delayed orders previously omitted their successful
    # one-shot propagation result.
    markerless_battle["misinterpreted_orders"].pop(target)

    before_standalone = source.engine.battle_manager.get_state()
    with pytest.raises(
        ValueError,
        match="requires global checkpoint elapsed time",
    ):
        source.engine.battle_manager.set_state(copy.deepcopy(markerless_battle))
    assert source.engine.battle_manager.get_state() == before_standalone

    restored = _session(prepared)
    _quiet_tactical_work(monkeypatch, restored)
    propagation = _patch_propagation(
        monkeypatch,
        restored,
        PropagationResult(True, 999.0, True, "timing", 0.0, True),
    )
    decisions = _patch_decision(monkeypatch, restored)
    _patch_stratagem(monkeypatch, restored, deception_viable=False)
    restored.engine.restore(_checkpoint_bytes(markerless))

    queue = restored.engine.battle_manager.deferred_ooda_decisions
    assert len(queue) == 1
    record = queue[0]
    assert record.unit_id == target
    assert record.battle_id == battle.battle_id
    assert record.due_elapsed_s == pytest.approx(15.0)
    assert record.propagation == PropagationResult(
        True,
        0.0,
        False,
        "",
        1.0,
        False,
    )
    migrated = json.loads(restored.engine.checkpoint())
    assert migrated["checkpoint_version"] == 118
    assert migrated["battle"]["deferred_ooda_schema"] == 1

    restored.step()
    assert decisions == []
    restored.step()
    assert decisions == [target]
    assert propagation == {"propagate": 0}
    assert restored.engine.battle_manager.deferred_ooda_decisions == ()


def test_markerless_timing_deferral_migrates_without_repeating_extension(
    prepared: PreparedScenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _session(prepared)
    _quiet_tactical_work(monkeypatch, source)
    battle = source.engine.battle_manager.active_battles[0]
    target = sorted(battle.unit_ids)[0]
    battle.battle_elapsed_s = 100.0
    _arm_decide(source, (target,))
    _patch_completed_planning(monkeypatch, source)
    source_propagation = _patch_propagation(
        monkeypatch,
        source,
        PropagationResult(True, 10.0, True, "timing", 0.7, True),
    )
    _patch_decision(monkeypatch, source)
    _patch_stratagem(monkeypatch, source, deception_viable=False)
    source.step()
    current = source.engine.checkpoint()
    markerless = json.loads(current)
    markerless["battle"].pop("deferred_ooda_schema")
    # The old queue held the first battle-local deadline; its retained timing
    # result caused one further equal extension when that deadline matured.
    markerless["battle"]["pending_decisions"][target] = 115.0

    restored = _session(prepared)
    _quiet_tactical_work(monkeypatch, restored)
    _patch_completed_planning(monkeypatch, restored)
    restored_propagation = _patch_propagation(
        monkeypatch,
        restored,
        PropagationResult(True, 999.0, False, "", 1.0, False),
    )
    restored_decisions = _patch_decision(monkeypatch, restored)
    _patch_stratagem(monkeypatch, restored, deception_viable=False)
    restored.engine.restore(_checkpoint_bytes(markerless))

    queue = restored.engine.battle_manager.deferred_ooda_decisions
    assert len(queue) == 1
    assert queue[0].due_elapsed_s == pytest.approx(25.0)
    assert restored.engine.checkpoint() == current

    for _ in range(4):
        source.step()
        restored.step()

    assert restored.engine.checkpoint() == source.engine.checkpoint()
    assert restored_decisions == [target]
    assert source_propagation == {"propagate": 1}
    assert restored_propagation == {"propagate": 0}


def test_markerless_pending_migration_rejects_ambiguous_owner_atomically(
    prepared: PreparedScenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _session(prepared)
    restored = _session(prepared)
    _quiet_tactical_work(monkeypatch, source)
    battle = source.engine.battle_manager.active_battles[0]
    target = sorted(battle.unit_ids)[0]
    _arm_decide(source, (target,))
    _patch_completed_planning(monkeypatch, source)
    _patch_propagation(
        monkeypatch,
        source,
        PropagationResult(True, 10.0, False, "", 1.0, False),
    )
    source.step()
    markerless = json.loads(source.engine.checkpoint())
    markerless["battle"].pop("deferred_ooda_schema")
    markerless["battle"]["misinterpreted_orders"].pop(target)

    no_owner = copy.deepcopy(markerless)
    no_owner["battle"]["battles"][battle.battle_id]["active"] = False

    duplicate_owner = copy.deepcopy(markerless)
    duplicate = copy.deepcopy(
        duplicate_owner["battle"]["battles"][battle.battle_id],
    )
    duplicate["battle_id"] = "battle_0001"
    duplicate["unit_ids"] = [target]
    duplicate_owner["battle"]["battles"]["battle_0001"] = duplicate
    duplicate_owner["battle"]["next_battle_id"] = 2

    for tampered in (no_owner, duplicate_owner):
        before = restored.engine.checkpoint()
        with pytest.raises(
            ValueError,
            match="must belong to exactly one active battle roster",
        ):
            restored.engine.restore(_checkpoint_bytes(tampered))
        assert restored.engine.checkpoint() == before


def test_current_deferred_schema_rejects_missing_and_extra_propagation(
    prepared: PreparedScenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _session(prepared)
    _quiet_tactical_work(monkeypatch, source)
    battle = source.engine.battle_manager.active_battles[0]
    target = sorted(battle.unit_ids)[0]
    extra = next(unit_id for unit_id in sorted(battle.unit_ids) if unit_id != target)
    _arm_decide(source, (target,))
    _patch_completed_planning(monkeypatch, source)
    _patch_propagation(
        monkeypatch,
        source,
        PropagationResult(True, 10.0, False, "", 1.0, False),
    )
    source.step()
    current = json.loads(source.engine.checkpoint())
    propagation = current["battle"]["misinterpreted_orders"][target]

    missing = copy.deepcopy(current)
    missing["battle"]["misinterpreted_orders"].pop(target)
    extra_state = copy.deepcopy(current)
    extra_state["battle"]["misinterpreted_orders"][extra] = propagation

    for tampered, expected in ((missing, "missing"), (extra_state, "extra")):
        restored = _session(prepared)
        before = restored.engine.checkpoint()
        with pytest.raises(
            ValueError,
            match=rf"propagation record per pending decision: .*{expected}=",
        ):
            restored.engine.restore(_checkpoint_bytes(tampered))
        assert restored.engine.checkpoint() == before


@pytest.mark.parametrize("invalid_marker", [False, 0, 2, "1"])
def test_current_deferred_schema_rejects_invalid_marker(
    prepared: PreparedScenario,
    invalid_marker: object,
) -> None:
    source = _session(prepared)
    tampered = json.loads(source.engine.checkpoint())
    tampered["battle"]["deferred_ooda_schema"] = invalid_marker
    before = source.engine.checkpoint()

    with pytest.raises(ValueError, match="deferred_ooda_schema is unsupported"):
        source.engine.restore(_checkpoint_bytes(tampered))

    assert source.engine.checkpoint() == before


def test_resolved_battle_cancels_and_advances_waiting_decision(
    prepared: PreparedScenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session(prepared)
    _quiet_tactical_work(monkeypatch, session)
    manager = session.engine.battle_manager
    battle = manager.active_battles[0]
    target = sorted(battle.unit_ids)[0]
    _arm_decide(session, (target,))
    _patch_completed_planning(monkeypatch, session)
    planning = session.context.planning_engine
    assert planning is not None
    planning_cancellations: list[str] = []
    monkeypatch.setattr(
        planning,
        "cancel_planning",
        planning_cancellations.append,
    )
    propagation = _patch_propagation(
        monkeypatch,
        session,
        PropagationResult(True, 100.0, False, "", 1.0, False),
    )
    decisions = _patch_decision(monkeypatch, session)
    manager._config.max_ticks_per_battle = 2

    session.step()
    assert len(manager.deferred_ooda_decisions) == 1
    session.step()

    assert battle.active is False
    assert manager.deferred_ooda_decisions == ()
    assert propagation == {"propagate": 1}
    assert decisions == []
    assert planning_cancellations == [target]
    assert session.context.ooda_engine.get_phase(target) is OODAPhase.ACT


def test_resolved_battle_cancels_planning_only_decide_and_advances_once(
    prepared: PreparedScenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _session(prepared)
    _quiet_tactical_work(monkeypatch, source)
    battle = source.engine.battle_manager.active_battles[0]
    target = sorted(battle.unit_ids)[0]
    _arm_decide(source, (target,))
    source_decisions = _patch_decision(monkeypatch, source)
    source_propagation = _patch_propagation(
        monkeypatch,
        source,
        PropagationResult(True, 10.0, False, "", 1.0, False),
    )

    source.step()

    assert source_decisions == []
    assert source_propagation == {"propagate": 0}
    assert source.engine.battle_manager.deferred_ooda_decisions == ()
    assert source.engine.battle_manager._deferred_battle_ids == {
        target: battle.battle_id,
    }
    planning = source.context.planning_engine
    assert planning is not None
    assert planning.get_planning_status(target) not in {
        PlanningPhase.IDLE,
        PlanningPhase.COMPLETE,
    }
    checkpoint = source.engine.checkpoint()

    restored = _session(prepared)
    _quiet_tactical_work(monkeypatch, restored)
    restored_decisions = _patch_decision(monkeypatch, restored)
    restored_propagation = _patch_propagation(
        monkeypatch,
        restored,
        PropagationResult(True, 10.0, False, "", 1.0, False),
    )
    restored.engine.restore(checkpoint)
    restored_manager = restored.engine.battle_manager
    restored_battle = restored_manager.active_battles[0]
    assert restored_manager._deferred_battle_ids == {
        target: restored_battle.battle_id,
    }
    assert restored.engine.checkpoint() == checkpoint

    restored_planning = restored.context.planning_engine
    restored_ooda = restored.context.ooda_engine
    assert restored_planning is not None
    assert restored_ooda is not None
    cancellations: list[str] = []
    advances: list[str] = []
    original_cancel = restored_planning.cancel_planning
    original_advance = restored_ooda.advance_phase

    def cancel(unit_id: str) -> None:
        cancellations.append(unit_id)
        original_cancel(unit_id)

    def advance(unit_id: str) -> OODAPhase:
        advances.append(unit_id)
        return original_advance(unit_id)

    monkeypatch.setattr(restored_planning, "cancel_planning", cancel)
    monkeypatch.setattr(restored_ooda, "advance_phase", advance)
    restored_manager._config.max_ticks_per_battle = (
        restored_battle.ticks_executed + 1
    )

    restored.step()

    assert restored_battle.active is False
    assert cancellations == [target]
    assert advances == [target]
    assert restored_decisions == []
    assert restored_propagation == {"propagate": 0}
    assert restored_planning.get_planning_status(target) is PlanningPhase.IDLE
    assert restored_manager._deferred_battle_ids == {}
    assert restored_ooda.get_phase(target) is OODAPhase.ACT


def test_duplicate_active_battle_ownership_is_rejected_before_update(
    prepared: PreparedScenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session(prepared, DEFAULT_VARIANT)
    _quiet_tactical_work(monkeypatch, session)
    manager = session.engine.battle_manager
    first = manager.active_battles[0]
    duplicate_id = sorted(first.unit_ids)[0]
    second = BattleContext(
        battle_id="battle_0001",
        start_tick=first.start_tick,
        start_time=first.start_time,
        involved_sides=list(first.involved_sides),
        unit_ids={duplicate_id},
    )
    manager._battles[second.battle_id] = second
    ooda = session.context.ooda_engine
    assert ooda is not None
    original_update = ooda.update
    update_calls = 0

    def update(dt_seconds: float, ts: datetime | None = None):
        nonlocal update_calls
        update_calls += 1
        return original_update(dt_seconds, ts=ts)

    monkeypatch.setattr(ooda, "update", update)

    with pytest.raises(RuntimeError, match="duplicate active battle ownership"):
        session.step()

    assert update_calls == 0
