"""Phase 112 production movement-diagnostics integration proofs."""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import pytest

from scripts.evaluate_scenarios import (
    ScenarioResult,
    print_summary,
    run_scenario,
)
from stochastic_warfare.core.types import Position
from stochastic_warfare.simulation.battle import BattleContext
from stochastic_warfare.simulation.engine import SimulationEngine
from stochastic_warfare.simulation.movement_diagnostics import (
    MovementReason,
    MovementStage,
)
from stochastic_warfare.simulation.runtime import (
    AnalysisVariant,
    SimulationRuntimeFactory,
)
from stochastic_warfare.simulation.scenario import (
    CampaignScenarioConfig,
    load_campaign_scenario_config,
)
from stochastic_warfare.validation.movement_diagnostics import (
    evaluate_movement_diagnostics,
)
from tests.conftest import make_versionless_legacy_morale_checkpoint


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
EASTING_PATH = DATA_DIR / "scenarios" / "73_easting" / "scenario.yaml"
CAMPAIGN_PATH = DATA_DIR / "scenarios" / "test_campaign" / "scenario.yaml"
REINFORCEMENT_PATH = DATA_DIR / "scenarios" / "test_campaign_reinforce" / "scenario.yaml"
RUNTIME_MAX_TICKS = 1_000_000


def _easting_engine(*, seed: int = 42) -> SimulationEngine:
    prepared = SimulationRuntimeFactory().prepare(
        EASTING_PATH,
        DATA_DIR,
        (AnalysisVariant(variant_id="phase112-movement-easting"),),
    )
    return prepared.build(
        "phase112-movement-easting",
        seed=seed,
        max_ticks=RUNTIME_MAX_TICKS,
        strict_mode=True,
    ).engine


def _prepare_tactical_control(
    *,
    fuel_remaining: float,
) -> tuple[SimulationEngine, list, object]:
    engine = _easting_engine()
    context = engine._ctx
    context.cal_flat = {
        **context.cal_flat,
        "defensive_sides": [],
    }
    movers = context.units_by_side["blue"][:5]
    target = context.units_by_side["red"][0]
    for index, unit in enumerate(movers):
        object.__setattr__(
            unit,
            "position",
            Position(0.0, index * 50.0, 0.0),
        )
        object.__setattr__(unit, "speed", unit.max_speed)
        object.__setattr__(unit, "fuel_remaining", fuel_remaining)
    object.__setattr__(
        target,
        "position",
        Position(20_000.0, 100.0, 0.0),
    )
    return engine, movers, target


def test_catalog_vehicles_expose_resource_block_and_fueled_control_moves() -> None:
    """Real live fuel state must drive manager and evaluator diagnostics."""
    blocked_engine, blocked_movers, blocked_target = _prepare_tactical_control(fuel_remaining=0.0)
    blocked_before = {unit.entity_id: unit.position for unit in blocked_movers}
    blocked_rng_before = copy.deepcopy(
        blocked_engine._ctx.rng_manager.get_state(),
    )
    blocked_engine._battle._execute_movement(
        blocked_engine._ctx,
        {"blue": blocked_movers},
        {"blue": [blocked_target]},
        60.0,
    )
    assert {unit.entity_id: unit.position for unit in blocked_movers} == blocked_before
    assert blocked_engine._ctx.rng_manager.get_state() == blocked_rng_before

    blocked = evaluate_movement_diagnostics(
        blocked_engine._ctx.movement_diagnostics,
        {"blue": blocked_movers, "red": [blocked_target]},
        context=blocked_engine._ctx,
    )
    individual = {f"UNIT_MOVEMENT_BLOCKED({unit.entity_id})" for unit in blocked_movers}
    assert individual <= set(blocked.issues)
    assert "MANY_MOVEMENT_BLOCKED(5/5)" in blocked.issues
    assert all(unit.resource_blocked for unit in blocked.units if unit.unit_id in blocked_before)
    assert not any(issue.startswith("MANY_STUCK_UNITS") for issue in blocked.issues)
    for unit in blocked_movers:
        summary = blocked_engine._ctx.movement_diagnostics.get_unit(
            unit.entity_id,
        )
        assert summary.reason_count(MovementReason.RESOURCE_BLOCKED) == 1
        assert summary.reason_count(MovementReason.ZERO_PROGRESS) == 0
        assert summary.expected_progress_count == 0

    fueled_engine, fueled_movers, fueled_target = _prepare_tactical_control(fuel_remaining=1.0)
    fueled_before = {unit.entity_id: unit.position for unit in fueled_movers}
    fueled_rng_before = copy.deepcopy(
        fueled_engine._ctx.rng_manager.get_state(),
    )
    fueled_engine._battle._execute_movement(
        fueled_engine._ctx,
        {"blue": fueled_movers},
        {"blue": [fueled_target]},
        60.0,
    )
    assert all(unit.position != fueled_before[unit.entity_id] for unit in fueled_movers)
    assert fueled_engine._ctx.rng_manager.get_state() == fueled_rng_before
    fueled = evaluate_movement_diagnostics(
        fueled_engine._ctx.movement_diagnostics,
        {"blue": fueled_movers, "red": [fueled_target]},
        context=fueled_engine._ctx,
    )
    assert not any("MOVEMENT_BLOCKED" in issue for issue in fueled.issues)
    assert not any(unit.resource_blocked for unit in fueled.units if unit.unit_id in fueled_before)
    assert not any(issue.startswith("MANY_STUCK_UNITS") for issue in fueled.issues)
    for unit in fueled_movers:
        summary = fueled_engine._ctx.movement_diagnostics.get_unit(
            unit.entity_id,
        )
        assert summary.reason_count(MovementReason.MOVED) == 1
        assert summary.positive_progress_count == 1


def _campaign_engine(
    *,
    seed: int,
    red_easting: float = 500_000.0,
) -> SimulationEngine:
    raw = load_campaign_scenario_config(CAMPAIGN_PATH).model_dump(
        mode="python",
    )
    for side in raw["sides"]:
        easting = 0.0 if side["side"] == "blue" else red_easting
        positioned_units: list[dict] = []
        unit_index = 0
        for entry in side["units"]:
            for _ in range(entry["count"]):
                positioned = copy.deepcopy(entry)
                positioned["count"] = 1
                positioned["position"] = [
                    easting,
                    unit_index * 50.0,
                    0.0,
                ]
                positioned_units.append(positioned)
                unit_index += 1
        side["units"] = positioned_units
    config = CampaignScenarioConfig.model_validate(raw)
    prepared = SimulationRuntimeFactory().prepare_config(
        config,
        DATA_DIR,
        (AnalysisVariant(variant_id="phase112-movement-campaign"),),
        source_label=str(CAMPAIGN_PATH.resolve()),
    )
    return prepared.build(
        "phase112-movement-campaign",
        seed=seed,
        max_ticks=RUNTIME_MAX_TICKS,
        strict_mode=True,
    ).engine


def test_campaign_manager_records_each_roster_unit_once() -> None:
    """The loader-to-engine campaign path must use the shared diagnostics."""
    engine = _campaign_engine(seed=42)
    context = engine._ctx
    unit_count = sum(len(units) for units in context.units_by_side.values())

    assert engine.step() is False
    diagnostics = context.movement_diagnostics
    assert diagnostics.total_observation_count == unit_count
    for summary in diagnostics.summaries():
        assert summary.decision_count == 1
        assert len(summary.recent_observations) == 1
        observation = summary.recent_observations[0]
        assert observation.stage is MovementStage.STRATEGIC
        assert observation.engine_tick == 1
        assert observation.unit_id == summary.unit_id
        assert observation.side == summary.side


def test_operational_to_tactical_paths_bind_one_stage_per_interval() -> None:
    engine = _campaign_engine(seed=42, red_easting=20_000.0)
    assert engine.step() is False

    for summary in engine._ctx.movement_diagnostics.summaries():
        assert summary.decision_count == 1
        assert [observation.stage for observation in summary.recent_observations] == [
            MovementStage.OPERATIONAL,
        ]
        assert {observation.engine_tick for observation in summary.recent_observations} == {1}

    executed = 1
    while executed < 12:
        assert engine.step() is False
        executed += 1
        if all(
            summary.recent_observations[-1].stage
            is MovementStage.TACTICAL
            for summary in engine._ctx.movement_diagnostics.summaries()
        ):
            break
    else:
        pytest.fail("campaign never reached a tactical interval")

    for summary in engine._ctx.movement_diagnostics.summaries():
        assert summary.decision_count == executed
        assert summary.recent_observations[0].stage is MovementStage.OPERATIONAL
        assert summary.recent_observations[-1].stage is MovementStage.TACTICAL
        assert {
            observation.engine_tick
            for observation in summary.recent_observations
        } == set(range(1, executed + 1))


def _two_battle_engine(
    battle_order: tuple[str, str],
) -> SimulationEngine:
    engine = _campaign_engine(seed=112, red_easting=20_000.0)
    context = engine._ctx
    unit_ids = {unit.entity_id for unit in context.all_units()}
    battles = {
        battle_id: BattleContext(
            battle_id=battle_id,
            start_tick=0,
            start_time=context.clock.current_time,
            involved_sides=["blue", "red"],
            unit_ids=set(unit_ids),
        )
        for battle_id in ("battle_0001", "battle_0002")
    }
    engine.battle_manager._battles = {battle_id: battles[battle_id] for battle_id in battle_order}
    engine.battle_manager._next_battle_id = 3
    return engine


def test_reversed_battle_map_restores_and_executes_in_canonical_order() -> None:
    control = _two_battle_engine(("battle_0001", "battle_0002"))
    checkpoint = control.checkpoint()
    reversed_state = json.loads(checkpoint.decode("utf-8"))
    serialized_battles = reversed_state["battle"]["battles"]
    reversed_state["battle"]["battles"] = {
        battle_id: serialized_battles[battle_id] for battle_id in reversed(tuple(serialized_battles))
    }

    resumed = _two_battle_engine(("battle_0002", "battle_0001"))
    resumed.set_state(reversed_state)
    assert [battle.battle_id for battle in resumed.battle_manager.active_battles] == ["battle_0001", "battle_0002"]
    assert resumed.checkpoint() == checkpoint

    assert resumed.step() == control.step()
    assert resumed.checkpoint() == control.checkpoint()
    for summary in resumed._ctx.movement_diagnostics.summaries():
        tactical_battles = [
            observation.battle_id
            for observation in summary.recent_observations
            if observation.stage is MovementStage.TACTICAL
        ]
        assert tactical_battles == ["battle_0001", "battle_0002"]


def test_schema112_movement_state_restores_and_continues_exactly() -> None:
    """Fresh whole-engine restore must retain pre-checkpoint counters."""
    control = _campaign_engine(seed=112)
    assert control.step() is False
    checkpoint = control.checkpoint()
    state_at_t = control.get_state()
    assert state_at_t["checkpoint_version"] == 116
    assert state_at_t["context"]["movement_diagnostics"] == control._ctx.movement_diagnostics.get_state()

    resumed = _campaign_engine(seed=999_112)
    resumed.restore(checkpoint)
    assert resumed.checkpoint() == checkpoint
    assert resumed._ctx.movement_diagnostics.get_state() == control._ctx.movement_diagnostics.get_state()

    assert control.step() == resumed.step()
    assert resumed.checkpoint() == control.checkpoint()


def test_schema112_movement_corruption_rejects_without_any_mutation() -> None:
    source = _campaign_engine(seed=112)
    assert source.step() is False
    invalid = copy.deepcopy(source.get_state())
    movement_state = invalid["context"]["movement_diagnostics"]
    unit_id = next(iter(movement_state["units"]))
    movement_state["units"][unit_id]["reason_counts"]["MOVED"] += 1

    target = _campaign_engine(seed=42)
    before = target.checkpoint()
    try:
        target.set_state(invalid)
    except ValueError:
        pass
    else:
        raise AssertionError("malformed movement counters were accepted")
    assert target.checkpoint() == before


def test_schema112_offset_ordinals_reject_without_any_mutation() -> None:
    """A coherent non-zero ordinal origin is impossible with full history."""
    source = _campaign_engine(seed=112)
    assert source.step() is False
    invalid = copy.deepcopy(source.get_state())
    movement_state = invalid["context"]["movement_diagnostics"]
    for unit_state in movement_state["units"].values():
        for observation in unit_state["recent_observations"]:
            observation["ordinal"] += 10
        unit_state["final_order"]["ordinal"] += 10
    movement_state["last_order"]["ordinal"] += 10
    movement_state["next_ordinal"] += 10

    target = _campaign_engine(seed=42)
    before = target.checkpoint()
    with pytest.raises(
        ValueError,
        match="complete history must use contiguous zero-based ordinals",
    ):
        target.set_state(invalid)
    assert target.checkpoint() == before


def test_elapsed_versionless_checkpoint_cannot_forget_movement_history() -> None:
    source = _campaign_engine(seed=112)
    assert source.step() is False
    invalid = make_versionless_legacy_morale_checkpoint(
        source.get_state(),
    )
    invalid["context"].pop("movement_diagnostics")

    target = _campaign_engine(seed=42)
    before = target.checkpoint()
    try:
        target.set_state(invalid)
    except ValueError as exc:
        assert "cannot omit movement diagnostics after simulation start" in str(exc)
    else:
        raise AssertionError(
            "elapsed versionless checkpoint forgot movement history",
        )
    assert target.checkpoint() == before


def test_tick_zero_versionless_checkpoint_can_migrate_empty_diagnostics() -> None:
    source = _campaign_engine(seed=112)
    legacy = make_versionless_legacy_morale_checkpoint(
        source.get_state(),
    )
    movement_state = legacy["context"].pop("movement_diagnostics")
    assert movement_state["total_observation_count"] == 0

    target = _campaign_engine(seed=999_112)
    target.set_state(legacy)
    assert target.checkpoint() == source.checkpoint()


def test_same_seed_movement_diagnostics_replay_is_byte_exact() -> None:
    first = _campaign_engine(seed=112)
    second = _campaign_engine(seed=112)

    assert first.step() == second.step()
    assert first.step() == second.step()
    assert first.checkpoint() == second.checkpoint()


def test_human_report_keeps_raw_nonmovement_distinct_from_semantic_stuck(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The CLI must not relabel legitimate standoff as a stuck defect."""
    result = ScenarioResult(
        scenario_name="semantic-control",
        scenario_path="control/scenario.yaml",
        initial_total=1,
        units_that_didnt_move=1,
        semantic_stuck_count=0,
        semantic_stuck_population=0,
        issues=["ZERO_CASUALTIES"],
        unit_details=[
            {
                "entity_id": "blue_standoff",
                "unit_type": "tank",
                "side": "blue",
                "status": "ACTIVE",
                "distance_moved": 0.0,
                "end_pos": (0.0, 0.0),
                "weapons_count": 1,
                "best_weapon_range": 5_000.0,
                "movement_disposition": "ENGINE_WEAPON_STANDOFF",
            },
        ],
    )

    print_summary([result])
    report = capsys.readouterr().out

    assert "Unmoved" in report
    assert "Raw displacement: moved=0, unmoved=1" in report
    assert "Semantic movement: stuck=0/0, resource_blocked=0/0" in report
    assert "Active units with <10m raw displacement:" in report
    assert "disposition=ENGINE_WEAPON_STANDOFF" in report
    assert "Stuck active units" not in report


def test_evaluator_captures_every_reinforcement_construction_position() -> None:
    result = run_scenario(REINFORCEMENT_PATH, DATA_DIR, seed=112)

    assert result.success, result.error
    reinforcements = {
        detail["entity_id"]: detail for detail in result.unit_details if detail["entity_id"].startswith("reinforce_")
    }
    expected_starts = {
        "reinforce_blue_0000_m1a2_0000": (200.0, 5_000.0),
        "reinforce_blue_0000_m1a2_0001": (200.0, 5_050.0),
        "reinforce_blue_0001_m1a2_0000": (200.0, 6_000.0),
        "reinforce_blue_0001_m1a2_0001": (200.0, 6_050.0),
        "reinforce_red_0002_m1a2_0000": (9_800.0, 5_000.0),
        "reinforce_red_0002_m1a2_0001": (9_800.0, 5_050.0),
        "reinforce_red_0002_m1a2_0002": (9_800.0, 5_100.0),
    }
    assert set(reinforcements) == set(expected_starts)
    blue_ids = {
        unit_id
        for unit_id in expected_starts
        if unit_id.startswith("reinforce_blue_")
    }
    expected_blue_moved_counts = {
        "reinforce_blue_0000_m1a2_0000": 2,
        "reinforce_blue_0000_m1a2_0001": 4,
        "reinforce_blue_0001_m1a2_0000": 8,
        "reinforce_blue_0001_m1a2_0001": 9,
    }
    for unit_id, detail in reinforcements.items():
        assert tuple(detail["start_pos"]) == expected_starts[unit_id]
        assert detail["distance_moved"] == round(
            math.dist(detail["start_pos"], detail["end_pos"]),
            1,
        )
        if unit_id in blue_ids:
            assert tuple(detail["end_pos"]) != expected_starts[unit_id]
            assert detail["distance_moved"] > 1.0
            assert detail["movement_achieved_m"] > 1.0
            assert detail["movement_reason_counts"]["MOVED"] == (
                expected_blue_moved_counts[unit_id]
            )
        else:
            assert tuple(detail["end_pos"]) == expected_starts[unit_id]
            assert detail["distance_moved"] == 0.0
            assert detail["movement_achieved_m"] == 0.0
            assert detail["movement_disposition"] == "NO_TARGET"
            assert detail["movement_reason_counts"]["NO_TARGET"] == 22
            assert detail["movement_reason_counts"]["MOVED"] == 0
            assert detail["movement_reason_counts"]["RESOURCE_BLOCKED"] == 0
            assert detail["movement_reason_counts"]["ZERO_PROGRESS"] == 0

    expected_moved = sum(detail["distance_moved"] > 1.0 for detail in result.unit_details)
    assert result.units_that_moved == expected_moved
    assert result.units_that_didnt_move == (len(result.unit_details) - expected_moved)
