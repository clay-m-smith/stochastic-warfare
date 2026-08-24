"""Behavioral wiring contracts for the deterministic battle facade."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast

import numpy as np
import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.simulation.battle import (
    BattleContext,
    BattleManager,
    BattleStatePlan,
)
from stochastic_warfare.simulation.battle_checkpoint_executor import (
    DefaultBattleCheckpointExecutor,
)
from stochastic_warfare.simulation.battle_engagement_executor import (
    DefaultBattleEngagementExecutor,
)
from stochastic_warfare.simulation.battle_executor_contracts import (
    BattleCheckpointStageRequest,
    BattleExecutorOwner,
    CheckpointValue,
    EngagementExecutionRequest,
    MovementExecutionRequest,
    OODACompletionRequest,
    OODAIntervalRequest,
)
from stochastic_warfare.simulation.battle_movement_executor import (
    DefaultBattleMovementExecutor,
)
from stochastic_warfare.simulation.battle_ooda_executor import (
    DefaultBattleOODAExecutor,
)
from stochastic_warfare.simulation.runtime import (
    AnalysisVariant,
    RuntimeSession,
    SimulationRuntimeFactory,
)
from stochastic_warfare.simulation.runtime_context import SimulationContext
from stochastic_warfare.simulation.scenario_config import CampaignScenarioConfig


ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data"
SCENARIO = DATA_DIR / "scenarios/test_campaign/scenario.yaml"
VARIANT_ID = "r16-baseline"
EXPECTED_CHECKPOINTS = (
    (66010, "9d97ebe7b38b9a5f92405ee63f634bfe44a89a7c3f61e097aeaf80dfe531e449"),
    (98757, "674bf6c0b6908075de40e3c9182a9aec94bf642d2e7055b94658a43b494247c8"),
    (116582, "e8e3c5951923d301a6e125333d329af5cd84061591cb9760fb59dcbb6e70db32"),
)


class _RecordingOODAExecutor:
    def __init__(self, calls: list[tuple[str, object]]) -> None:
        self.calls = calls

    def execute_interval(
        self,
        owner: BattleExecutorOwner,
        request: OODAIntervalRequest,
    ) -> None:
        del owner
        self.calls.append(("ooda", request))

    def process_completions(
        self,
        owner: BattleExecutorOwner,
        request: OODACompletionRequest,
    ) -> None:
        del owner
        self.calls.append(("ooda-completions", request))

class _RecordingMovementExecutor:
    def __init__(self, calls: list[tuple[str, object]]) -> None:
        self.calls = calls

    def execute(
        self,
        owner: BattleExecutorOwner,
        request: MovementExecutionRequest,
    ) -> None:
        del owner
        self.calls.append(("movement", request))


class _RecordingEngagementExecutor:
    def __init__(self, calls: list[tuple[str, object]]) -> None:
        self.calls = calls

    def execute(
        self,
        owner: BattleExecutorOwner,
        request: EngagementExecutionRequest,
    ) -> list[tuple[Unit, UnitStatus, str]]:
        del owner
        self.calls.append(("engagement", request))
        return []


class _RecordingCheckpointExecutor:
    def __init__(self, calls: list[tuple[str, object]]) -> None:
        self.calls = calls

    def get_state(self, owner: BattleExecutorOwner) -> dict[str, object]:
        self.calls.append(("checkpoint", owner))
        return {"executor": "injected"}

    def stage_state(
        self,
        owner: BattleExecutorOwner,
        request: BattleCheckpointStageRequest,
    ) -> BattleStatePlan:
        del owner, request
        raise AssertionError("not exercised by this wiring contract")

    def commit_state(
        self,
        owner: BattleExecutorOwner,
        plan: BattleStatePlan,
    ) -> None:
        del owner, plan
        raise AssertionError("not exercised by this wiring contract")

    def set_state(
        self,
        owner: BattleExecutorOwner,
        state: Mapping[str, CheckpointValue],
        *,
        allow_legacy: bool = False,
    ) -> None:
        del owner, state, allow_legacy
        raise AssertionError("not exercised by this wiring contract")


def _checkpoint_bytes(manager: BattleManager) -> bytes:
    return json.dumps(
        manager.get_state(),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _engine_checkpoint_bytes(session: RuntimeSession) -> bytes:
    return json.dumps(
        session.engine.get_state(),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _install_explicit_defaults(session: RuntimeSession) -> None:
    current = session.engine.battle_manager
    replacement = BattleManager(
        session.context.event_bus,
        current._config,
        movement_diagnostics=current._movement_diagnostics,
        movement_committer=current._movement_committer,
        effective_performance_flags=(current._performance_receipts.effective_flags),
        tactical_interval_seconds=(
            current._performance_receipts.tactical_interval_microseconds
            / 1_000_000.0
        ),
        ooda_executor=DefaultBattleOODAExecutor(),
        movement_executor=DefaultBattleMovementExecutor(),
        engagement_executor=DefaultBattleEngagementExecutor(),
        checkpoint_executor=DefaultBattleCheckpointExecutor(),
    )
    replacement.set_state(copy.deepcopy(current.get_state()))
    session.engine._battle = replacement


def test_injected_executors_receive_immutable_topology_with_live_units() -> None:
    """Injected executors cannot rewrite routing state but retain Unit identity."""
    calls: list[tuple[str, object]] = []
    manager = BattleManager(
        EventBus(),
        ooda_executor=_RecordingOODAExecutor(calls),
        movement_executor=_RecordingMovementExecutor(calls),
        engagement_executor=_RecordingEngagementExecutor(calls),
        checkpoint_executor=_RecordingCheckpointExecutor(calls),
    )
    blue = Unit(
        entity_id="blue-1",
        position=Position(0.0, 0.0),
        side="blue",
    )
    red = Unit(
        entity_id="red-1",
        position=Position(10.0, 0.0),
        side="red",
    )
    battle = BattleContext(
        battle_id="battle_0000",
        start_tick=0,
        start_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
        involved_sides=["blue", "red"],
        unit_ids={blue.entity_id, red.entity_id},
        wave_assignments={blue.entity_id: 0, red.entity_id: 1},
    )
    units_by_side = {"blue": [blue], "red": [red]}
    config = CampaignScenarioConfig.model_validate(
        {
            "name": "battle-executor-capabilities",
            "date": "2024-01-01",
            "duration_hours": 1.0,
            "terrain": {
                "width_m": 1_000,
                "height_m": 1_000,
                "cell_size_m": 100,
            },
            "behavior_rules": {
                "blue": {
                    "hold_position": False,
                    "nested": {"speed": 2.5},
                },
            },
            "sides": [
                {
                    "side": "blue",
                    "units": [
                        {"unit_type": "infantry_platoon", "count": 1},
                    ],
                },
                {
                    "side": "red",
                    "units": [
                        {"unit_type": "infantry_platoon", "count": 1},
                    ],
                },
            ],
        },
    )
    context = SimulationContext(
        config=config,
        clock=SimulationClock(
            start=battle.start_time,
            tick_duration=timedelta(seconds=5),
        ),
        rng_manager=RNGManager(42),
        event_bus=EventBus(),
        units_by_side=units_by_side,
        unit_weapons={blue.entity_id: (), red.entity_id: ()},
        unit_sensor_attachments={blue.entity_id: (), red.entity_id: ()},
        unit_sensors={blue.entity_id: (), red.entity_id: ()},
        equipment_resolutions={blue.entity_id: (), red.entity_id: ()},
        aggregation_engine=object(),
    )
    active_enemies = {"blue": [red], "red": [blue]}
    enemy_positions = {
        "blue": np.array([[10.0, 0.0]], dtype=np.float64),
        "red": np.array([[0.0, 0.0]], dtype=np.float64),
    }
    behavior_rules = {
        "blue": {
            "hold_position": False,
            "waypoints": ["phase-line-a", "phase-line-b"],
            "tags": {"screen", "guard"},
            "nested": {"speed": 2.5},
        },
    }

    manager.execute_ooda_interval(context, (battle,), 5.0)
    manager._execute_movement(
        context,
        units_by_side,
        active_enemies,
        5.0,
        battle,
        behavior_rules=behavior_rules,
        enemy_pos_arrays=enemy_positions,
    )
    assert (
        manager._execute_engagements(
            context,
            units_by_side,
            active_enemies,
            enemy_positions,
            5.0,
            battle.start_time,
            _unit_index={blue.entity_id: blue, red.entity_id: red},
            battle=battle,
        )
        == []
    )
    assert manager.get_state() == {"executor": "injected"}

    assert [name for name, _ in calls] == [
        "ooda",
        "movement",
        "engagement",
        "checkpoint",
    ]
    ooda_request = calls[0][1]
    movement_request = calls[1][1]
    engagement_request = calls[2][1]
    assert isinstance(ooda_request, OODAIntervalRequest)
    assert isinstance(movement_request, MovementExecutionRequest)
    assert isinstance(engagement_request, EngagementExecutionRequest)
    assert ooda_request.runtime is not context
    assert movement_request.runtime is not context
    assert engagement_request.runtime is not context
    for runtime in (
        ooda_request.runtime,
        movement_request.runtime,
        engagement_request.runtime,
    ):
        assert not hasattr(runtime, "aggregation_engine")
        assert runtime.units_by_side["blue"][0] is blue
        with pytest.raises(TypeError):
            runtime.units_by_side["green"] = ()  # type: ignore[index]
        with pytest.raises(FrozenInstanceError):
            runtime.clock.tick_count = 99  # type: ignore[misc]

    assert not hasattr(ooda_request.runtime, "engagement_engine")
    assert not hasattr(ooda_request.runtime, "config")
    assert not hasattr(movement_request.runtime, "engagement_engine")
    runtime_rules = movement_request.runtime.config.behavior_rules
    runtime_blue_rules = runtime_rules["blue"]
    assert isinstance(runtime_blue_rules, Mapping)
    runtime_nested = runtime_blue_rules["nested"]
    assert isinstance(runtime_nested, Mapping)
    with pytest.raises(TypeError):
        runtime_rules["red"] = {}  # type: ignore[index]
    with pytest.raises(TypeError):
        runtime_nested["speed"] = 9.0  # type: ignore[index]
    assert ooda_request.battles[0].battle_id == battle.battle_id
    assert ooda_request.battles[0].involved_sides == ("blue", "red")
    assert ooda_request.battles[0].unit_ids == {blue.entity_id, red.entity_id}
    assert movement_request.units_by_side is not units_by_side
    assert movement_request.units_by_side["blue"] == (blue,)
    assert movement_request.active_enemies["blue"] == (red,)
    assert engagement_request.units_by_side["blue"][0] is blue
    assert engagement_request.active_enemies["blue"][0] is red
    assert engagement_request.unit_index is not None
    assert engagement_request.unit_index[blue.entity_id] is blue
    assert movement_request.enemy_position_arrays is not None
    for side in ("blue", "red"):
        movement_array = movement_request.enemy_position_arrays[side]
        engagement_array = engagement_request.enemy_position_arrays[side]
        assert not np.shares_memory(movement_array, enemy_positions[side])
        assert not np.shares_memory(engagement_array, enemy_positions[side])
        assert not movement_array.flags.writeable
        assert not engagement_array.flags.writeable

    rules = movement_request.behavior_rules
    assert rules is not None
    blue_rules = rules["blue"]
    assert isinstance(blue_rules, Mapping)
    assert blue_rules["waypoints"] == ("phase-line-a", "phase-line-b")
    assert blue_rules["tags"] == frozenset({"screen", "guard"})

    with pytest.raises(TypeError):
        movement_request.units_by_side["green"] = ()  # type: ignore[index]
    with pytest.raises(AttributeError):
        movement_request.units_by_side["blue"].append(blue)  # type: ignore[attr-defined]
    with pytest.raises(TypeError):
        blue_rules["hold_position"] = True  # type: ignore[index]
    with pytest.raises(AttributeError):
        blue_rules["tags"].add("attack")  # type: ignore[union-attr]
    with pytest.raises(ValueError):
        movement_request.enemy_position_arrays["blue"][0, 0] = 99.0
    with pytest.raises(TypeError):
        engagement_request.unit_index["new"] = blue  # type: ignore[index]
    with pytest.raises(AttributeError):
        ooda_request.battles[0].unit_ids.add("new")  # type: ignore[attr-defined]
    with pytest.raises(TypeError):
        ooda_request.battles[0].wave_assignments["new"] = 2  # type: ignore[index]

    owner = cast(BattleExecutorOwner, calls[3][1])
    assert not hasattr(owner, "config")
    with pytest.raises(FrozenInstanceError):
        owner.config_view.destruction_threshold = 0.1  # type: ignore[misc]

    # Unit is the deliberate live-domain seam: identity and semantic mutation
    # remain observable through each otherwise-frozen request.
    object.__setattr__(blue, "speed", 7.0)
    assert movement_request.units_by_side["blue"][0].speed == 7.0
    assert engagement_request.unit_index[blue.entity_id].speed == 7.0
    with pytest.raises(FrozenInstanceError):
        setattr(ooda_request, "dt_seconds", 1.0)


def test_checkpoint_executor_receives_isolated_readonly_payloads() -> None:
    """Checkpoint injection cannot mutate manager state or caller payloads."""
    blue = Unit(
        entity_id="blue-checkpoint",
        position=Position(0.0, 0.0),
        side="blue",
    )
    red = Unit(
        entity_id="red-checkpoint",
        position=Position(5.0, 0.0),
        side="red",
    )
    source_state: dict[str, object] = {
        "outer": {"items": [1, 2], "nested": {"value": "original"}},
    }

    class _AdversarialCheckpointExecutor:
        def get_state(self, owner: BattleExecutorOwner) -> dict[str, object]:
            snapshot = owner.checkpoint_snapshot()
            with pytest.raises(TypeError):
                snapshot.ammo_expended["injected"] = 99  # type: ignore[index]
            with pytest.raises(TypeError):
                snapshot.battles["injected"] = next(  # type: ignore[index]
                    iter(snapshot.battles.values()),
                )
            interval = next(iter(snapshot.battles.values()))
            with pytest.raises(AttributeError):
                interval.unit_ids.add("injected")  # type: ignore[attr-defined]
            with pytest.raises(TypeError):
                interval.wave_assignments["injected"] = 3  # type: ignore[index]

            # Mutable domain records are detached copies in checkpoint views.
            snapshot.suppression_states[blue.entity_id].value = 0.9
            assert owner.suppression_state(blue.entity_id).value == 0.4
            return {"executor": "adversarial"}

        def stage_state(
            self,
            owner: BattleExecutorOwner,
            request: BattleCheckpointStageRequest,
        ) -> BattleStatePlan:
            del owner
            outer = request.state["outer"]
            assert isinstance(outer, Mapping)
            items = outer["items"]
            assert items == (1, 2)
            with pytest.raises(TypeError):
                outer["new"] = "injected"  # type: ignore[index]
            with pytest.raises(AttributeError):
                items.append(3)  # type: ignore[union-attr]
            assert request.expected_unit_ids == frozenset({blue.entity_id})
            assert request.expected_sides == frozenset({"blue", "red"})
            with pytest.raises(AttributeError):
                request.expected_unit_ids.add("injected")  # type: ignore[union-attr]

            detached = request.detached_state()
            detached_outer = detached["outer"]
            assert isinstance(detached_outer, dict)
            detached_items = detached_outer["items"]
            assert isinstance(detached_items, list)
            detached_items.append(3)
            assert source_state == {
                "outer": {
                    "items": [1, 2],
                    "nested": {"value": "original"},
                },
            }
            raise RuntimeError("stage inspected")

        def commit_state(
            self,
            owner: BattleExecutorOwner,
            plan: BattleStatePlan,
        ) -> None:
            del owner, plan
            raise AssertionError("not exercised")

        def set_state(
            self,
            owner: BattleExecutorOwner,
            state: Mapping[str, CheckpointValue],
            *,
            allow_legacy: bool = False,
        ) -> None:
            del owner, state, allow_legacy
            raise AssertionError("not exercised")

    manager = BattleManager(
        EventBus(),
        checkpoint_executor=_AdversarialCheckpointExecutor(),
    )
    manager.detect_engagement(
        {"blue": [blue], "red": [red]},
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    owner = manager._executor_owner
    owner.record_ammunition_expenditure("baseline", 2)
    owner.suppression_state(blue.entity_id).value = 0.4

    assert manager.get_state() == {"executor": "adversarial"}
    assert owner.suppression_state(blue.entity_id).value == 0.4
    assert owner.ammunition_expenditure("injected") == 0

    with pytest.raises(RuntimeError, match="stage inspected"):
        manager.stage_state(
            cast("dict[str, CheckpointValue]", source_state),
            expected_unit_ids={blue.entity_id},
            expected_sides={"blue", "red"},
        )


def test_typed_owner_commands_roundtrip_through_checkpoint() -> None:
    """Executor commands own transitions and retain exact checkpoint state."""
    manager = BattleManager(EventBus())
    owner = manager._executor_owner
    unit_id = "typed-owner-unit"

    owner.begin_undigging(unit_id)
    owner.record_ammunition_expenditure("legacy-ammo", 3)
    owner.record_ammunition_expenditure(
        "weapon:ammo",
        2,
        fallback_key="legacy-ammo",
    )
    concealment = owner.update_legacy_concealment(
        unit_id,
        terrain_concealment=0.8,
        target_is_moving=True,
        observation_decay=0.1,
    )
    owner.suppression_state(unit_id).value = 0.45

    state = manager.get_state()
    assert concealment == pytest.approx(0.3)
    assert state["undigging"] == {unit_id: True}
    assert state["ammo_expended"] == {
        "legacy-ammo": 3,
        "weapon:ammo": 5,
    }
    assert state["concealment_scores"] == {unit_id: pytest.approx(0.3)}
    assert state["suppression_states"][unit_id]["value"] == pytest.approx(0.45)

    restored = BattleManager(EventBus())
    restored.set_state(copy.deepcopy(state))
    assert _checkpoint_bytes(restored) == _checkpoint_bytes(manager)

    invalid_tuple = copy.deepcopy(state)
    invalid_tuple["lod_promoted"] = ()
    with pytest.raises(ValueError, match="lod_promoted must be a list"):
        manager.stage_state(invalid_tuple)

    owner.finish_undigging(unit_id)
    assert unit_id not in manager.get_state()["undigging"]


def test_failure_policy_injection_is_observable_and_defaults_strict() -> None:
    """Standalone managers reject fallback unless an owner authorizes it."""
    failure = RuntimeError("battle adapter failure")
    strict = BattleManager(EventBus())

    assert (
        strict._executor_owner.suppress_runtime_failure(
            "test.subsystem",
            "test_operation",
            failure,
        )
        is False
    )

    calls: list[tuple[str, str, Exception]] = []

    def allow_degraded_fallback(
        subsystem: str,
        operation: str,
        exception: Exception,
    ) -> bool:
        calls.append((subsystem, operation, exception))
        return True

    degraded = BattleManager(
        EventBus(),
        failure_handler=allow_degraded_fallback,
    )
    assert (
        degraded._executor_owner.suppress_runtime_failure(
            "test.subsystem",
            "test_operation",
            failure,
        )
        is True
    )
    assert calls == [("test.subsystem", "test_operation", failure)]


def test_explicit_default_injection_preserves_checkpoint_bytes() -> None:
    """Explicit defaults and constructor defaults expose identical bytes."""
    implicit = BattleManager(EventBus())
    explicit = BattleManager(
        EventBus(),
        ooda_executor=DefaultBattleOODAExecutor(),
        movement_executor=DefaultBattleMovementExecutor(),
        engagement_executor=DefaultBattleEngagementExecutor(),
        checkpoint_executor=DefaultBattleCheckpointExecutor(),
    )

    before = _checkpoint_bytes(implicit)
    assert _checkpoint_bytes(explicit) == before
    explicit.set_state(copy.deepcopy(implicit.get_state()))
    assert _checkpoint_bytes(explicit) == before


def test_production_defaults_preserve_frozen_bytes_and_continuation() -> None:
    """Explicit injection matches the pre-split production byte oracle."""
    prepared = SimulationRuntimeFactory().prepare(
        SCENARIO,
        DATA_DIR,
        (AnalysisVariant(variant_id=VARIANT_ID),),
    )

    def build() -> RuntimeSession:
        return prepared.build(
            VARIANT_ID,
            seed=31,
            max_ticks=4,
            strict_mode=True,
        )

    control = build()
    explicit = build()
    _install_explicit_defaults(explicit)

    for index, (expected_size, expected_digest) in enumerate(
        EXPECTED_CHECKPOINTS[:2],
    ):
        control_bytes = _engine_checkpoint_bytes(control)
        explicit_bytes = _engine_checkpoint_bytes(explicit)
        assert explicit_bytes == control_bytes
        assert len(control_bytes) == expected_size
        assert hashlib.sha256(control_bytes).hexdigest() == expected_digest
        if index == 0:
            control.engine.step()
            explicit.engine.step()

    checkpoint = copy.deepcopy(explicit.engine.get_state())
    resumed = build()
    _install_explicit_defaults(resumed)
    resumed.engine.set_state(copy.deepcopy(checkpoint))
    assert _engine_checkpoint_bytes(resumed) == _engine_checkpoint_bytes(explicit)

    control.engine.step()
    explicit.engine.step()
    resumed.engine.step()
    expected_size, expected_digest = EXPECTED_CHECKPOINTS[2]
    continuation = _engine_checkpoint_bytes(control)
    assert _engine_checkpoint_bytes(explicit) == continuation
    assert _engine_checkpoint_bytes(resumed) == continuation
    assert len(continuation) == expected_size
    assert hashlib.sha256(continuation).hexdigest() == expected_digest
