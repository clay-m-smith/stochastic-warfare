"""Current-engine Fallujah Phase Line Fran regression checks.

The suite proves that the scenario loads its authored force, pre-emplaced IEDs,
and scripted-action declarations and that unit references in those declarations
resolve. The declared seed-42 runtime checks its current terminal, casualty,
combat-activity, and IED outcomes. It is current-engine regression evidence,
not historical validation.

The runtime currently terminates before the first scripted action at H+7. The
schema and reference checks below therefore do not prove scripted-action
dispatch or effects.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import yaml

from stochastic_warfare.combat.events import EngagementEvent
from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.base import UnitStatus
from stochastic_warfare.simulation.battle import BattleManager
from stochastic_warfare.simulation.engine import EngineConfig, SimulationEngine
from stochastic_warfare.simulation.recorder import SimulationRecorder
from stochastic_warfare.simulation.scenario import (
    ScenarioLoader,
    VictoryConditionConfig,
)
from stochastic_warfare.simulation.victory import VictoryEvaluator

SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data" / "scenarios" / "fallujah_phase_line_fran" / "scenario.yaml"
)
DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _run_one(seed: int, max_ticks: int = 2000) -> dict:
    """Run one iteration of Fallujah and return summary metrics."""
    with open(SCENARIO_PATH) as f:
        scn = yaml.safe_load(f)
    conditions = [VictoryConditionConfig(**vc) for vc in scn["victory_conditions"]]

    loader = ScenarioLoader(str(DATA_DIR))
    ctx = loader.load(SCENARIO_PATH, seed=seed)
    victory_eval = VictoryEvaluator(
        objectives=[],
        conditions=conditions,
        event_bus=ctx.event_bus,
        max_duration_s=432000.0,
    )
    recorder = SimulationRecorder(ctx.event_bus)
    engine = SimulationEngine(
        ctx,
        config=EngineConfig(max_ticks=max_ticks),
        victory_evaluator=victory_eval,
        recorder=recorder,
    )
    result = engine.run()

    blue_d = sum(1 for u in ctx.units_by_side["blue"] if u.status == UnitStatus.DESTROYED)
    red_d = sum(1 for u in ctx.units_by_side["red"] if u.status == UnitStatus.DESTROYED)
    victory = result.victory_result
    winner = victory.winning_side.lower()
    condition_type = victory.condition_type
    ticks = result.ticks_executed
    emplaced_count = len(getattr(ctx, "initial_ied_obstacle_ids", []) or [])
    return {
        "blue_destroyed": blue_d,
        "red_destroyed": red_d,
        "winner": winner,
        "condition_type": condition_type,
        "ticks": ticks,
        "max_ticks": max_ticks,
        "tick_duration_s": ctx.clock.tick_duration.total_seconds(),
        "events": recorder.events,
        "emplaced_ied_count": emplaced_count,
        "elapsed_s": result.duration_s,
    }


# ---------------------------------------------------------------------------
# Load-time assertions (fast — no simulation run)
# ---------------------------------------------------------------------------


class TestFallujahScenarioLoad:
    """Assert Phase 101 infrastructure loads without running a sim."""

    def test_scenario_loads(self) -> None:
        """Scenario YAML must load + validate schema."""
        loader = ScenarioLoader(str(DATA_DIR))
        ctx = loader.load(SCENARIO_PATH, seed=42)
        assert ctx.config.name.startswith("Fallujah"), (
            f"Wrong scenario loaded: {ctx.config.name}"
        )

    def test_force_scale(self) -> None:
        """Force scale matches Al-Fajr assault — 280-340 units total."""
        loader = ScenarioLoader(str(DATA_DIR))
        ctx = loader.load(SCENARIO_PATH, seed=42)
        blue = len(ctx.units_by_side.get("blue", []))
        red = len(ctx.units_by_side.get("red", []))
        total = blue + red
        assert 280 <= total <= 340, (
            f"Force scale {total} outside Al-Fajr envelope [280, 340]"
        )

    def test_initial_ieds_emplaced(self) -> None:
        """20 pre-emplaced IEDs/HBIEDs must register as obstacles at load."""
        loader = ScenarioLoader(str(DATA_DIR))
        ctx = loader.load(SCENARIO_PATH, seed=42)
        assert len(ctx.initial_ied_obstacle_ids) == 20, (
            f"Expected 20 IEDs, got {len(ctx.initial_ied_obstacle_ids)}"
        )

    def test_scripted_events_loaded(self) -> None:
        """Eleven scripted actions must parse; this is not dispatch proof."""
        loader = ScenarioLoader(str(DATA_DIR))
        ctx = loader.load(SCENARIO_PATH, seed=42)
        assert len(ctx.scripted_events) == 11, (
            f"Expected 11 scripted events, got {len(ctx.scripted_events)}"
        )

    def test_scripted_event_targets_exist(self) -> None:
        """Authored unit references must resolve; this is not dispatch proof."""
        loader = ScenarioLoader(str(DATA_DIR))
        ctx = loader.load(SCENARIO_PATH, seed=42)
        all_ids = set()
        for units in ctx.units_by_side.values():
            for u in units:
                all_ids.add(u.entity_id)
        missing = []
        for ev in ctx.scripted_events:
            p = ev.params or {}
            for key in ("unit_id", "target_unit_id"):
                uid = p.get(key)
                if uid and uid not in all_ids:
                    missing.append((ev.event_type, key, uid))
        assert not missing, f"Dangling scripted-event refs: {missing}"

    def test_unconventional_engine_present(self) -> None:
        """UnconventionalWarfareEngine must be available for HBIED paths."""
        loader = ScenarioLoader(str(DATA_DIR))
        ctx = loader.load(SCENARIO_PATH, seed=42)
        assert ctx.unconventional_engine is not None
        assert ctx.incendiary_engine is not None


# ---------------------------------------------------------------------------
# Runtime assertions (@slow)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def run_result() -> dict:
    """Run the declared seed-42 current-engine regression once."""
    return _run_one(seed=42, max_ticks=2000)


@pytest.mark.slow
class TestFallujahRuntimeEnvelope:
    """Current-engine terminal assertions for one declared seed."""

    def test_winner_envelope(self, run_result: dict) -> None:
        """Retain the declared seed's current-engine blue winner."""
        winner = run_result["winner"]
        assert "blue" in winner, f"Expected blue winner, got {winner!r}"

    def test_red_casualty_envelope(self, run_result: dict) -> None:
        """Retain the broad current-engine red-loss regression floor."""
        red_d = run_result["red_destroyed"]
        assert red_d >= 20, (
            f"Insurgent losses {red_d} below engine envelope (expect ≥ 20)"
        )

    def test_blue_casualty_ceiling(self, run_result: dict) -> None:
        """Retain the broad current-engine blue-loss regression ceiling."""
        blue_d = run_result["blue_destroyed"]
        assert blue_d <= 50, (
            f"Coalition losses {blue_d} exceed engine envelope"
        )

    def test_force_destroyed_terminal_progression(self, run_result: dict) -> None:
        """Terminate semantically before the cap on an exact tactical clock."""
        ticks = run_result["ticks"]
        max_ticks = run_result["max_ticks"]
        tick_duration_s = run_result["tick_duration_s"]

        assert run_result["condition_type"] == "force_destroyed"
        assert 0 < ticks < max_ticks, (
            f"Expected a pre-cap terminal, got {ticks}/{max_ticks} ticks"
        )
        assert tick_duration_s == 5.0
        assert run_result["elapsed_s"] == ticks * tick_duration_s


@pytest.mark.slow
class TestFallujahPhase101Infrastructure:
    """Current-engine combat and pre-emplaced-IED runtime checks."""

    def test_engagements_occur(self, run_result: dict) -> None:
        """Combat engagement events must fire — not a walkover."""
        engagements = [
            e for e in run_result["events"] if e.event_type == "EngagementEvent"
        ]
        assert len(engagements) >= 50, (
            f"Only {len(engagements)} engagements — scenario not active"
        )

    def test_ied_detonations_occur(self, run_result: dict) -> None:
        """Pre-emplaced HBIEDs must detonate on advancing units."""
        ied_events = [
            e for e in run_result["events"]
            if e.event_type == "IEDDetonationEvent"
        ]
        assert len(ied_events) >= 1, (
            "No IED detonations — initial_ieds pathway broken"
        )

    def test_marine_rifle_engages(self) -> None:
        """The scenario's exact M16A4 attachment fires in a controlled
        production engagement.

        The default Phase 109 outcome is CAS-dominated and destroys the
        defenders before Marine squads enter rifle range.  Isolating one
        loaded squad and one loaded defender preserves production construction,
        detection, battle routing, event publication, and live ammunition
        while removing that unrelated force-timing dependency.
        """
        ctx = ScenarioLoader(DATA_DIR).load(SCENARIO_PATH, seed=42)
        marine = next(
            unit
            for unit in ctx.units_by_side["blue"]
            if unit.unit_type == "us_marine_rifle_squad_urban"
        )
        defender = next(
            unit
            for unit in ctx.units_by_side["red"]
            if unit.unit_type == "iraqi_insurgent_urban"
        )
        m16 = next(
            attachment
            for attachment in ctx.unit_weapons[marine.entity_id]
            if attachment.weapon.weapon_id == "m16a4"
        )
        ammo_id = m16.ammunition[0].ammo_id
        rounds_before = m16.weapon.ammo_state.available(ammo_id)

        marine.position = Position(0.0, 0.0, 0.0)
        defender.position = Position(300.0, 0.0, 0.0)
        marine.speed = 0.0
        defender.speed = 0.0
        ctx.units_by_side = {"blue": [marine], "red": [defender]}
        ctx.unit_weapons[marine.entity_id] = (m16,)

        events: list[EngagementEvent] = []
        ctx.event_bus.subscribe(EngagementEvent, events.append)
        BattleManager(ctx.event_bus)._execute_engagements(
            ctx,
            {"blue": [marine]},
            {"blue": [defender]},
            {"blue": np.asarray([(300.0, 0.0)], dtype=np.float64)},
            1.0,
            ctx.clock.current_time,
        )

        assert [
            (event.attacker_id, event.target_id, event.weapon_id)
            for event in events
        ] == [(marine.entity_id, defender.entity_id, "m16a4")]
        assert m16.weapon.ammo_state.available(ammo_id) < rounds_before
