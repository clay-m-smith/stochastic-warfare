"""Phase 112 typed movement-diagnostics state and evaluator tests."""

from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError
from datetime import datetime
from types import SimpleNamespace

import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.entities.unit_classes.air_defense import (
    AirDefenseUnit,
)
from stochastic_warfare.simulation.battle import BattleContext, BattleManager
from stochastic_warfare.simulation.movement_diagnostics import (
    MOVEMENT_OBSERVATION_LIMIT,
    MovementDecision,
    MovementDiagnostics,
    MovementReason,
    MovementStage,
)
from stochastic_warfare.validation.movement_diagnostics import (
    evaluate_movement_diagnostics,
)


def _decision(
    unit_id: str,
    side: str,
    reason: MovementReason,
    *,
    start: float = 0.0,
    attempted_m: float = 0.0,
    achieved_m: float = 0.0,
) -> MovementDecision:
    return MovementDecision(
        unit_id=unit_id,
        side=side,
        reason=reason,
        attempted_m=attempted_m,
        pre_position=Position(start, 0.0, 0.0),
        post_position=Position(start + achieved_m, 0.0, 0.0),
    )


def _unit(
    unit_id: str,
    side: str,
    easting: float,
) -> Unit:
    return Unit(
        entity_id=unit_id,
        position=Position(easting, 0.0, 0.0),
        side=side,
        unit_type="phase112_vehicle",
        speed=10.0,
        max_speed=10.0,
    )


def test_registration_is_transactional_idempotent_and_side_bound() -> None:
    diagnostics = MovementDiagnostics({"u1": "blue"})
    before = diagnostics.get_state()

    diagnostics.register_units({"u1": "blue"})
    assert diagnostics.get_state() == before

    with pytest.raises(ValueError, match="surrounding whitespace"):
        diagnostics.register_units({
            "u2": "red",
            " bad ": "blue",
        })
    assert diagnostics.get_state() == before

    with pytest.raises(ValueError, match="already registered"):
        diagnostics.register_units({"u1": "red"})
    assert diagnostics.get_state() == before


def test_batch_order_is_canonical_and_observations_are_immutable() -> None:
    diagnostics = MovementDiagnostics({
        "zulu": "blue",
        "alpha": "blue",
    })
    observations = diagnostics.record_batch(
        engine_tick=7,
        stage=MovementStage.TACTICAL,
        battle_id="battle_0001",
        decisions=(
            _decision(
                "zulu",
                "blue",
                MovementReason.MOVED,
                attempted_m=10.0,
                achieved_m=10.0,
            ),
            _decision(
                "alpha",
                "blue",
                MovementReason.ZERO_PROGRESS,
                attempted_m=10.0,
            ),
        ),
    )

    assert [observation.unit_id for observation in observations] == [
        "alpha",
        "zulu",
    ]
    assert [observation.ordinal for observation in observations] == [0, 1]
    with pytest.raises(FrozenInstanceError):
        observations[0].attempted_m = 5.0  # type: ignore[misc]

    alpha = diagnostics.get_unit("alpha")
    assert alpha.expected_progress_count == 1
    assert alpha.zero_progress_count == 1
    assert alpha.positive_progress_count == 0
    assert alpha.reason_count(MovementReason.ZERO_PROGRESS) == 1

    zulu = diagnostics.get_unit("zulu")
    assert zulu.expected_progress_count == 1
    assert zulu.zero_progress_count == 0
    assert zulu.positive_progress_count == 1
    assert zulu.total_attempted_m == pytest.approx(10.0)
    assert zulu.total_achieved_m == pytest.approx(10.0)


def test_batch_rejects_duplicate_or_wrong_side_without_mutation() -> None:
    diagnostics = MovementDiagnostics({"u1": "blue"})
    before = diagnostics.get_state()

    with pytest.raises(ValueError, match="more than once"):
        diagnostics.record_batch(
            engine_tick=1,
            stage=MovementStage.STRATEGIC,
            battle_id="",
            decisions=(
                _decision("u1", "blue", MovementReason.NO_TARGET),
                _decision("u1", "blue", MovementReason.NO_TARGET),
            ),
        )
    assert diagnostics.get_state() == before

    with pytest.raises(ValueError, match="registered unit topology"):
        diagnostics.record_batch(
            engine_tick=1,
            stage=MovementStage.STRATEGIC,
            battle_id="",
            decisions=(
                _decision("u1", "red", MovementReason.NO_TARGET),
            ),
        )
    assert diagnostics.get_state() == before


def test_ring_is_bounded_and_cumulative_counters_are_not_truncated() -> None:
    diagnostics = MovementDiagnostics({"u1": "blue"})
    observation_count = MOVEMENT_OBSERVATION_LIMIT + 6
    for tick in range(observation_count):
        diagnostics.record_batch(
            engine_tick=tick,
            stage=MovementStage.STRATEGIC,
            battle_id="",
            decisions=(
                _decision(
                    "u1",
                    "blue",
                    MovementReason.MOVED,
                    start=float(tick),
                    attempted_m=1.0,
                    achieved_m=1.0,
                ),
            ),
        )

    summary = diagnostics.get_unit("u1")
    assert summary.decision_count == observation_count
    assert len(summary.recent_observations) == MOVEMENT_OBSERVATION_LIMIT
    assert summary.dropped_observation_count == 6
    assert summary.reason_count(MovementReason.MOVED) == observation_count
    assert summary.total_attempted_m == pytest.approx(observation_count)
    assert summary.total_achieved_m == pytest.approx(observation_count)
    assert summary.recent_observations[0].engine_tick == 6


def test_public_summary_is_an_immutable_point_in_time_snapshot() -> None:
    diagnostics = MovementDiagnostics({"u1": "blue"})
    diagnostics.record_batch(
        engine_tick=1,
        stage=MovementStage.STRATEGIC,
        battle_id="",
        decisions=(
            _decision("u1", "blue", MovementReason.NO_TARGET),
        ),
    )
    first = diagnostics.get_unit("u1")

    diagnostics.record_batch(
        engine_tick=2,
        stage=MovementStage.STRATEGIC,
        battle_id="",
        decisions=(
            _decision(
                "u1",
                "blue",
                MovementReason.MOVED,
                attempted_m=1.0,
                achieved_m=1.0,
            ),
        ),
    )
    second = diagnostics.get_unit("u1")

    assert first.decision_count == 1
    assert first.reason_count(MovementReason.NO_TARGET) == 1
    assert first.reason_count(MovementReason.MOVED) == 0
    assert [item.engine_tick for item in first.recent_observations] == [1]
    assert second.decision_count == 2
    assert second.reason_count(MovementReason.MOVED) == 1
    assert [item.engine_tick for item in second.recent_observations] == [1, 2]


def test_state_round_trip_preserves_exact_typed_state() -> None:
    source = MovementDiagnostics({"u1": "blue", "u2": "red"})
    source.record_batch(
        engine_tick=3,
        stage=MovementStage.OPERATIONAL,
        battle_id="",
        decisions=(
            _decision(
                "u1",
                "blue",
                MovementReason.MOVED,
                attempted_m=5.0,
                achieved_m=5.0,
            ),
            _decision(
                "u2",
                "red",
                MovementReason.DEFENSIVE_HOLD,
            ),
        ),
    )
    state = source.get_state()

    restored = MovementDiagnostics({"u1": "blue", "u2": "red"})
    restored.set_state(
        state,
        expected_unit_sides={"u1": "blue", "u2": "red"},
    )

    assert restored.get_state() == state
    assert restored.summaries() == source.summaries()

    source_continuation = source.record_batch(
        engine_tick=3,
        stage=MovementStage.TACTICAL,
        battle_id="battle_0001",
        decisions=(
            _decision("u2", "red", MovementReason.NO_TARGET),
            _decision("u1", "blue", MovementReason.NO_TARGET),
        ),
    )
    restored_continuation = restored.record_batch(
        engine_tick=3,
        stage=MovementStage.TACTICAL,
        battle_id="battle_0001",
        decisions=(
            _decision("u2", "red", MovementReason.NO_TARGET),
            _decision("u1", "blue", MovementReason.NO_TARGET),
        ),
    )

    assert source_continuation == restored_continuation
    assert [
        observation.ordinal
        for observation in restored_continuation
    ] == [2, 3]
    assert restored.get_state() == source.get_state()


@pytest.mark.parametrize(
    "corruption",
    (
        "global_total",
        "reason_sum",
        "progress_counter",
        "ring_counter",
        "distance",
        "topology",
        "canonical_order",
        "consistent_side_rewrite",
        "ordinal_offset",
    ),
)
def test_malformed_state_rejects_atomically(corruption: str) -> None:
    source = MovementDiagnostics({"u1": "blue", "u2": "blue"})
    source.record_batch(
        engine_tick=4,
        stage=MovementStage.TACTICAL,
        battle_id="battle_0001",
        decisions=(
            _decision(
                "u1",
                "blue",
                MovementReason.MOVED,
                attempted_m=4.0,
                achieved_m=4.0,
            ),
            _decision(
                "u2",
                "blue",
                MovementReason.ZERO_PROGRESS,
                attempted_m=4.0,
            ),
        ),
    )
    invalid = copy.deepcopy(source.get_state())

    if corruption == "global_total":
        invalid["total_observation_count"] += 1
    elif corruption == "reason_sum":
        invalid["units"]["u1"]["reason_counts"]["MOVED"] += 1
    elif corruption == "progress_counter":
        invalid["units"]["u1"]["positive_progress_count"] = 0
    elif corruption == "ring_counter":
        invalid["units"]["u1"]["dropped_observation_count"] = 1
    elif corruption == "distance":
        invalid["units"]["u1"]["recent_observations"][0][
            "achieved_m"
        ] = 3.0
    elif corruption == "topology":
        invalid["units"]["extra"] = copy.deepcopy(
            invalid["units"]["u1"],
        )
    elif corruption == "canonical_order":
        invalid["units"]["u2"]["recent_observations"][0]["ordinal"] = 0
        invalid["units"]["u2"]["final_order"]["ordinal"] = 0
    elif corruption == "consistent_side_rewrite":
        invalid["units"]["u1"]["side"] = "red"
        invalid["units"]["u1"]["recent_observations"][0]["side"] = "red"
        invalid["units"]["u1"]["final_order"]["side"] = "red"
        if invalid["last_order"]["unit_id"] == "u1":
            invalid["last_order"]["side"] = "red"
    elif corruption == "ordinal_offset":
        for unit_state in invalid["units"].values():
            for observation in unit_state["recent_observations"]:
                observation["ordinal"] += 10
            unit_state["final_order"]["ordinal"] += 10
        invalid["last_order"]["ordinal"] += 10
        invalid["next_ordinal"] += 10

    target = MovementDiagnostics({"u1": "blue", "u2": "blue"})
    target.record_batch(
        engine_tick=1,
        stage=MovementStage.STRATEGIC,
        battle_id="",
        decisions=(
            _decision("u1", "blue", MovementReason.NO_TARGET),
            _decision("u2", "blue", MovementReason.NO_TARGET),
        ),
    )
    before = target.get_state()
    with pytest.raises(ValueError):
        target.set_state(
            invalid,
            expected_unit_sides={"u1": "blue", "u2": "blue"},
        )
    assert target.get_state() == before


def test_truncated_same_tick_ring_preserves_valid_ordinal_offset() -> None:
    """A dropped same-tick prefix makes its retained ordinal offset valid."""
    source = MovementDiagnostics({"u1": "blue", "u2": "blue"})
    for _ in range(MOVEMENT_OBSERVATION_LIMIT + 1):
        source.record_batch(
            engine_tick=7,
            stage=MovementStage.STRATEGIC,
            battle_id="",
            decisions=(
                _decision("u1", "blue", MovementReason.NO_TARGET),
            ),
        )
    source.record_batch(
        engine_tick=7,
        stage=MovementStage.STRATEGIC,
        battle_id="",
        decisions=(
            _decision("u2", "blue", MovementReason.NO_TARGET),
        ),
    )
    state = source.get_state()
    assert state["units"]["u1"]["dropped_observation_count"] == 1
    assert (
        state["units"]["u1"]["recent_observations"][0]["ordinal"]
        == 1
    )

    restored = MovementDiagnostics({"u1": "blue", "u2": "blue"})
    restored.set_state(
        state,
        expected_unit_sides={"u1": "blue", "u2": "blue"},
    )
    assert restored.get_state() == state

    source_continuation = source.record_batch(
        engine_tick=7,
        stage=MovementStage.STRATEGIC,
        battle_id="",
        decisions=(
            _decision("u2", "blue", MovementReason.NO_TARGET),
        ),
    )
    restored_continuation = restored.record_batch(
        engine_tick=7,
        stage=MovementStage.STRATEGIC,
        battle_id="",
        decisions=(
            _decision("u2", "blue", MovementReason.NO_TARGET),
        ),
    )
    assert source_continuation == restored_continuation
    assert source_continuation[0].ordinal == MOVEMENT_OBSERVATION_LIMIT + 2
    assert restored.get_state() == source.get_state()


def _fault_detection_run(
    *,
    broken_committer: bool,
) -> tuple[list[Unit], Unit, MovementDiagnostics]:
    movers = [
        _unit(f"blue_{index}", "blue", float(index * 20))
        for index in range(5)
    ]
    target = _unit("red_target", "red", 20_000.0)
    topology = {
        unit.entity_id: unit.side
        for unit in [*movers, target]
    }
    diagnostics = MovementDiagnostics(topology)
    ctx = SimpleNamespace(
        cal_flat={"defensive_sides": []},
        movement_diagnostics=diagnostics,
        unit_weapons={},
        clock=SimpleNamespace(tick_count=1),
    )
    committer = (
        (lambda unit, proposed: unit.position)
        if broken_committer
        else None
    )
    manager = BattleManager(
        EventBus(),
        movement_diagnostics=diagnostics,
        movement_committer=committer,
    )
    manager._execute_movement(
        ctx,
        {"blue": movers},
        {"blue": [target]},
        1.0,
    )
    return movers, target, diagnostics


def test_injected_final_committer_is_a_fault_detector_not_a_default() -> None:
    broken_movers, broken_target, broken_diagnostics = (
        _fault_detection_run(broken_committer=True)
    )
    broken = evaluate_movement_diagnostics(
        broken_diagnostics,
        {"blue": broken_movers, "red": [broken_target]},
        context=SimpleNamespace(unit_weapons={}),
    )

    assert all(
        unit.movement_disposition == MovementReason.ZERO_PROGRESS.value
        for unit in broken.units
        if unit.unit_id.startswith("blue_")
    )
    assert all(
        unit.stuck
        for unit in broken.units
        if unit.unit_id.startswith("blue_")
    )
    assert "MANY_STUCK_UNITS(5/5)" in broken.issues
    assert all(unit.position.easting < 100.0 for unit in broken_movers)

    normal_movers, normal_target, normal_diagnostics = (
        _fault_detection_run(broken_committer=False)
    )
    normal = evaluate_movement_diagnostics(
        normal_diagnostics,
        {"blue": normal_movers, "red": [normal_target]},
        context=SimpleNamespace(unit_weapons={}),
    )
    assert all(
        unit.movement_disposition == MovementReason.MOVED.value
        for unit in normal.units
        if unit.unit_id.startswith("blue_")
    )
    assert not any(
        unit.stuck
        for unit in normal.units
        if unit.unit_id.startswith("blue_")
    )
    assert not any(
        issue.startswith("MANY_STUCK_UNITS")
        for issue in normal.issues
    )
    assert all(
        unit.position.easting > float(index * 20)
        for index, unit in enumerate(normal_movers)
    )


def test_evaluator_rejects_whitespace_side_identity() -> None:
    diagnostics = MovementDiagnostics()
    with pytest.raises(ValueError, match="surrounding whitespace"):
        evaluate_movement_diagnostics(
            diagnostics,
            {" blue": []},
            context=SimpleNamespace(unit_weapons={}),
        )


def test_manager_records_exact_non_attempt_branch_reasons_once() -> None:
    inactive = _unit("inactive", "blue", 0.0)
    object.__setattr__(inactive, "status", UnitStatus.DESTROYED)
    emplaced = AirDefenseUnit(
        entity_id="emplaced",
        position=Position(10.0, 0.0, 0.0),
        side="blue",
        speed=10.0,
        max_speed=10.0,
    )
    reserve = _unit("reserve", "blue", 20.0)
    target = _unit("target", "red", 20_000.0)
    diagnostics = MovementDiagnostics({
        unit.entity_id: unit.side
        for unit in (inactive, emplaced, reserve, target)
    })
    context = SimpleNamespace(
        cal_flat={"defensive_sides": []},
        movement_diagnostics=diagnostics,
        unit_weapons={},
        clock=SimpleNamespace(tick_count=1),
    )
    battle = BattleContext(
        battle_id="battle_0001",
        start_tick=0,
        start_time=datetime(2026, 1, 1),
        involved_sides=["blue", "red"],
        wave_assignments={"reserve": -1},
    )

    BattleManager(
        EventBus(),
        movement_diagnostics=diagnostics,
    )._execute_movement(
        context,
        {"blue": [inactive, emplaced, reserve]},
        {"blue": [target]},
        1.0,
        battle,
    )

    expected = {
        "inactive": MovementReason.INACTIVE,
        "emplaced": MovementReason.EMPLACED_HOLD,
        "reserve": MovementReason.RESERVE_OR_UNRELEASED,
    }
    for unit_id, reason in expected.items():
        summary = diagnostics.get_unit(unit_id)
        assert summary.decision_count == 1
        assert summary.final_reason is reason
        assert summary.total_attempted_m == 0.0
        assert summary.total_achieved_m == 0.0


@pytest.mark.parametrize(
    ("calibration", "behavior_rules", "enemies", "expected_reason"),
    (
        (
            {"defensive_sides": []},
            {},
            False,
            MovementReason.NO_TARGET,
        ),
        (
            {"defensive_sides": []},
            {"blue": {"hold_position": True}},
            True,
            MovementReason.AUTHORED_HOLD,
        ),
        (
            {"defensive_sides": ["blue"]},
            {},
            True,
            MovementReason.DEFENSIVE_HOLD,
        ),
    ),
)
def test_manager_records_side_level_hold_reason(
    calibration: dict,
    behavior_rules: dict,
    enemies: bool,
    expected_reason: MovementReason,
) -> None:
    mover = _unit("mover", "blue", 0.0)
    target = _unit("target", "red", 20_000.0)
    diagnostics = MovementDiagnostics({
        "mover": "blue",
        "target": "red",
    })
    context = SimpleNamespace(
        cal_flat=calibration,
        movement_diagnostics=diagnostics,
        unit_weapons={},
        clock=SimpleNamespace(tick_count=1),
    )

    BattleManager(
        EventBus(),
        movement_diagnostics=diagnostics,
    )._execute_movement(
        context,
        {"blue": [mover]},
        {"blue": [target]} if enemies else {"blue": []},
        1.0,
        behavior_rules=behavior_rules,
    )

    summary = diagnostics.get_unit("mover")
    assert summary.decision_count == 1
    assert summary.final_reason is expected_reason


def test_manager_rejects_two_diagnostic_owners_before_movement() -> None:
    mover = _unit("mover", "blue", 0.0)
    target = _unit("target", "red", 20_000.0)
    injected = MovementDiagnostics({"mover": "blue", "target": "red"})
    context_owner = MovementDiagnostics({"mover": "blue", "target": "red"})
    context = SimpleNamespace(
        cal_flat={"defensive_sides": []},
        movement_diagnostics=context_owner,
        unit_weapons={},
        clock=SimpleNamespace(tick_count=1),
    )
    before = mover.position

    with pytest.raises(RuntimeError, match="share one owner"):
        BattleManager(
            EventBus(),
            movement_diagnostics=injected,
        )._execute_movement(
            context,
            {"blue": [mover]},
            {"blue": [target]},
            1.0,
        )

    assert mover.position == before
    assert injected.total_observation_count == 0
    assert context_owner.total_observation_count == 0
