"""Phase 113 production battle wiring for the authoritative morale runtime."""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import numpy as np
import pytest

from stochastic_warfare.core.events import Event, EventBus
from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.morale.events import MoraleStateChangeEvent, RallyEvent
from stochastic_warfare.morale.rout import RoutConfig, RoutEngine
from stochastic_warfare.morale.runtime import (
    MoraleRegistration,
    MoraleRuntime,
    MoraleTransitionCause,
)
from stochastic_warfare.morale.state import MoraleConfig, MoraleState
from stochastic_warfare.simulation.battle import BattleManager, _apply_melee_result


TIMESTAMP = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _unit(
    unit_id: str,
    *,
    state: MoraleState = MoraleState.STEADY,
    easting: float = 0.0,
) -> Unit:
    status = (
        UnitStatus.ROUTING
        if state is MoraleState.ROUTED
        else UnitStatus.SURRENDERED
        if state is MoraleState.SURRENDERED
        else UnitStatus.ACTIVE
    )
    return Unit(
        entity_id=unit_id,
        position=Position(easting, 0.0, 0.0),
        side="blue",
        status=status,
    )


def _runtime(
    units: list[Unit],
    states: list[MoraleState],
    *,
    seed: int = 113,
    morale_config: MoraleConfig | None = None,
    rout_config: RoutConfig | None = None,
) -> tuple[MoraleRuntime, RoutEngine, EventBus, np.random.Generator]:
    bus = EventBus()
    rng = np.random.default_rng(seed)
    rout = RoutEngine(bus, rng, rout_config)
    runtime = MoraleRuntime(
        bus,
        rng,
        morale_config,
        rout_engine=rout,
    )
    runtime.register_units(
        tuple(
            MoraleRegistration(unit.entity_id, state)
            for unit, state in zip(units, states, strict=True)
        ),
        {unit.entity_id: unit for unit in units},
    )
    return runtime, rout, bus, rng


def _context(
    runtime: MoraleRuntime,
    *,
    elapsed_s: float,
) -> SimpleNamespace:
    return SimpleNamespace(
        calibration={},
        clock=SimpleNamespace(elapsed=timedelta(seconds=elapsed_s)),
        morale_runtime=runtime,
        morale_states=runtime.states,
        rout_engine=runtime.rout_engine,
    )


def _no_change_config(
    *,
    transition_cooldown_s: float = 30.0,
) -> MoraleConfig:
    return MoraleConfig(
        base_degrade_rate=0.0,
        base_recover_rate=0.0,
        casualty_weight=0.0,
        suppression_weight=0.0,
        leadership_weight=0.0,
        cohesion_weight=0.0,
        force_ratio_weight=0.0,
        transition_cooldown_s=transition_cooldown_s,
    )


def test_battle_ordinary_check_uses_elapsed_scenario_time() -> None:
    unit = _unit("blue-1")
    runtime, _rout, _bus, rng = _runtime(
        [unit],
        [MoraleState.STEADY],
        morale_config=_no_change_config(),
    )
    before_rng = copy.deepcopy(rng.bit_generator.state)
    manager = BattleManager(event_bus=EventBus())

    manager._execute_morale(
        _context(runtime, elapsed_s=31.0),
        {"blue": [unit]},
        {"blue": []},
        TIMESTAMP,
    )

    record = runtime.record_for(unit.entity_id)
    assert record.current_state is MoraleState.STEADY
    assert record.last_check_time_s == 31.0
    assert record.generation == 1
    assert rng.bit_generator.state != before_rng


def test_battle_skips_ordinary_check_at_logical_time_zero() -> None:
    unit = _unit("blue-zero")
    runtime, _rout, _bus, rng = _runtime(
        [unit],
        [MoraleState.STEADY],
        morale_config=_no_change_config(),
    )
    before_rng = copy.deepcopy(rng.bit_generator.state)
    before_record = runtime.record_for(unit.entity_id)
    manager = BattleManager(event_bus=EventBus())

    manager._execute_morale(
        _context(runtime, elapsed_s=0.0),
        {"blue": [unit]},
        {"blue": []},
        TIMESTAMP,
    )

    assert runtime.record_for(unit.entity_id) is before_record
    assert unit.status is UnitStatus.ACTIVE
    assert rng.bit_generator.state == before_rng


def test_battle_rally_commits_through_runtime_before_ordinary_check() -> None:
    unit = _unit("blue-routed", state=MoraleState.ROUTED)
    runtime, _rout, bus, _rng = _runtime(
        [unit],
        [MoraleState.ROUTED],
        seed=4,
        morale_config=_no_change_config(),
        rout_config=RoutConfig(rally_base_chance=0.95),
    )
    events: list[object] = []
    bus.subscribe(MoraleStateChangeEvent, events.append)
    manager = BattleManager(event_bus=bus)

    manager._execute_morale(
        _context(runtime, elapsed_s=100.0),
        {"blue": [unit]},
        {"blue": []},
        TIMESTAMP,
    )

    record = runtime.record_for(unit.entity_id)
    assert record.current_state is MoraleState.SHAKEN
    assert record.last_check_time_s == 100.0
    assert record.generation == 1
    assert unit.status is UnitStatus.ACTIVE
    assert [event.cause for event in events] == [MoraleTransitionCause.RALLY]


def test_zero_cooldown_rally_is_not_rechecked_in_the_same_tick() -> None:
    unit = _unit("blue-zero-cooldown", state=MoraleState.ROUTED)
    runtime, _rout, bus, rng = _runtime(
        [unit],
        [MoraleState.ROUTED],
        seed=4,
        morale_config=_no_change_config(transition_cooldown_s=0.0),
        rout_config=RoutConfig(rally_base_chance=0.95),
    )
    expected_rng = np.random.default_rng(4)
    expected_rng.random()
    events: list[Event] = []
    bus.subscribe(Event, events.append)
    manager = BattleManager(event_bus=bus)

    manager._execute_morale(
        _context(runtime, elapsed_s=100.0),
        {"blue": [unit]},
        {"blue": []},
        TIMESTAMP,
    )

    record = runtime.record_for(unit.entity_id)
    assert record.current_state is MoraleState.SHAKEN
    assert record.last_transition_time_s == 100.0
    assert record.last_check_time_s == 100.0
    assert record.generation == 1
    assert unit.status is UnitStatus.ACTIVE
    assert [type(event) for event in events] == [
        MoraleStateChangeEvent,
        RallyEvent,
    ]
    assert events[0].cause is MoraleTransitionCause.RALLY
    assert rng.bit_generator.state == expected_rng.bit_generator.state


def test_zero_cooldown_failed_rally_does_not_recheck_same_tick_melee_rout(
) -> None:
    unit = _unit("blue-same-tick-melee")
    runtime, _rout, bus, rng = _runtime(
        [unit],
        [MoraleState.STEADY],
        seed=5,
        morale_config=_no_change_config(transition_cooldown_s=0.0),
        rout_config=RoutConfig(
            rally_base_chance=0.0,
            rally_friendly_bonus=0.0,
            rally_leader_bonus=0.0,
        ),
    )
    runtime.force_transition(
        unit.entity_id,
        MoraleState.ROUTED,
        cause=MoraleTransitionCause.MELEE_ROUT,
        timestamp=TIMESTAMP,
        current_time_s=100.0,
    )
    expected_rng = np.random.default_rng(5)
    expected_rng.random()
    events: list[Event] = []
    bus.subscribe(Event, events.append)
    manager = BattleManager(event_bus=bus)

    manager._execute_morale(
        _context(runtime, elapsed_s=100.0),
        {"blue": [unit]},
        {"blue": []},
        TIMESTAMP,
    )

    record = runtime.record_for(unit.entity_id)
    assert record.current_state is MoraleState.ROUTED
    assert record.last_transition_time_s == 100.0
    assert record.last_check_time_s == 100.0
    assert record.generation == 1
    assert unit.status is UnitStatus.ROUTING
    assert rng.bit_generator.state == expected_rng.bit_generator.state
    assert events == []


def test_battle_cascade_commits_authoritative_state_and_status() -> None:
    source = _unit("source", state=MoraleState.ROUTED)
    candidate = _unit(
        "candidate",
        state=MoraleState.SHAKEN,
        easting=100.0,
    )
    runtime, _rout, bus, _rng = _runtime(
        [source, candidate],
        [MoraleState.ROUTED, MoraleState.SHAKEN],
        morale_config=_no_change_config(),
        rout_config=RoutConfig(
            rally_base_chance=0.0,
            rally_friendly_bonus=0.0,
            rally_leader_bonus=0.0,
            cascade_radius_m=500.0,
            cascade_base_chance=1.0,
            cascade_shaken_susceptibility=2.0,
        ),
    )
    events: list[MoraleStateChangeEvent] = []
    bus.subscribe(MoraleStateChangeEvent, events.append)
    manager = BattleManager(event_bus=bus)

    manager._execute_morale(
        _context(runtime, elapsed_s=100.0),
        {"blue": [source, candidate]},
        {"blue": []},
        TIMESTAMP,
    )

    assert runtime.states[candidate.entity_id] is MoraleState.ROUTED
    assert candidate.status is UnitStatus.ROUTING
    assert events[-1].unit_id == candidate.entity_id
    assert events[-1].cause is MoraleTransitionCause.ROUT_CASCADE
    assert events[-1].logical_time_s == 100.0


def test_melee_result_routes_via_runtime_transaction() -> None:
    attacker = _unit("attacker")
    defender = _unit("defender")
    runtime, _rout, bus, _rng = _runtime(
        [attacker, defender],
        [MoraleState.STEADY, MoraleState.STEADY],
    )
    events: list[MoraleStateChangeEvent] = []
    bus.subscribe(MoraleStateChangeEvent, events.append)
    melee_result = SimpleNamespace(
        attacker_casualties=0,
        defender_casualties=0,
        attacker_routed=False,
        defender_routed=True,
    )

    _apply_melee_result(
        melee_result,
        attacker,
        defender,
        [],
        runtime,
        timestamp=TIMESTAMP,
        current_time_s=42.0,
    )

    record = runtime.record_for(defender.entity_id)
    assert record.current_state is MoraleState.ROUTED
    assert record.last_transition_time_s == 42.0
    assert record.last_check_time_s == 42.0
    assert record.generation == 1
    assert defender.status is UnitStatus.ROUTING
    assert [event.cause for event in events] == [
        MoraleTransitionCause.MELEE_ROUT,
    ]


def test_melee_rout_without_runtime_rejects_before_partial_side_effects() -> None:
    attacker = _unit("attacker")
    defender = _unit("defender")
    bus = EventBus()
    events: list[Event] = []
    bus.subscribe(Event, events.append)
    pending: list[tuple[Unit, UnitStatus, str]] = []
    melee_result = SimpleNamespace(
        attacker_casualties=1,
        defender_casualties=1,
        attacker_routed=False,
        defender_routed=True,
    )

    with pytest.raises(RuntimeError, match="requires a morale runtime"):
        _apply_melee_result(
            melee_result,
            attacker,
            defender,
            pending,
            None,
            event_bus=bus,
            timestamp=TIMESTAMP,
            current_time_s=42.0,
        )

    assert events == []
    assert pending == []
