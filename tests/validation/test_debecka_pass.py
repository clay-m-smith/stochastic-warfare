"""Current-engine regression guard — Battle of Debecka Pass (2003).

This suite protects reproducible software behavior; it is not a historical
or predictive validation.  Fresh Phase 112 production runs do not satisfy
the source-backed casualty or duration envelope.  REM-030 owns the future
typed historical-envelope contract and its held-out production validation.

Current regression envelope:
- Blue wins at least 8 of 10 iterations.
- Mean red destroyed is 5–30 units.
- Mean blue destroyed is at most 55 units.
- Mean duration is at least 15 ticks.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from stochastic_warfare.entities.base import UnitStatus
from stochastic_warfare.simulation.engine import EngineConfig, SimulationEngine
from stochastic_warfare.simulation.recorder import SimulationRecorder
from stochastic_warfare.simulation.scenario import (
    ScenarioLoader,
    VictoryConditionConfig,
)
from stochastic_warfare.simulation.victory import VictoryEvaluator

SCENARIO_PATH = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "debecka_pass" / "scenario.yaml"
DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _run_one(seed: int, max_ticks: int = 3000) -> dict:
    """Run one iteration of Debecka Pass and return summary metrics."""
    with open(SCENARIO_PATH) as f:
        scn = yaml.safe_load(f)
    conditions = [VictoryConditionConfig(**vc) for vc in scn["victory_conditions"]]

    loader = ScenarioLoader(str(DATA_DIR))
    ctx = loader.load(SCENARIO_PATH, seed=seed)
    victory_eval = VictoryEvaluator(
        objectives=[],
        conditions=conditions,
        event_bus=ctx.event_bus,
        max_duration_s=21600.0,
    )
    recorder = SimulationRecorder(ctx.event_bus)
    engine = SimulationEngine(
        ctx,
        config=EngineConfig(max_ticks=max_ticks),
        victory_evaluator=victory_eval,
        recorder=recorder,
    )
    recorder.start()
    while not engine.step():
        pass

    blue_d = sum(1 for u in ctx.units_by_side["blue"] if u.status == UnitStatus.DESTROYED)
    red_d = sum(1 for u in ctx.units_by_side["red"] if u.status == UnitStatus.DESTROYED)
    victory = getattr(engine, "_last_victory", None)
    winner = (getattr(victory, "winning_side", "") or "").lower()
    ticks = ctx.clock.tick_count
    return {
        "blue_destroyed": blue_d,
        "red_destroyed": red_d,
        "winner": winner,
        "ticks": ticks,
        "events": recorder.events,
    }


@pytest.fixture(scope="module")
def mc_results() -> list[dict]:
    """Run a 10-iteration Monte Carlo and cache for the module."""
    return [_run_one(seed=42 + i) for i in range(10)]


# ---------------------------------------------------------------------------
# Envelope assertions
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestDebeckaEnvelope:
    """Envelope assertions — 10-iteration Monte Carlo."""

    def test_winner_envelope(self, mc_results: list[dict]) -> None:
        """Coalition should win ≥ 8/10 iterations (historical: decisive)."""
        blue_wins = sum(1 for r in mc_results if "blue" in r["winner"])
        assert blue_wins >= 8, (
            f"Expected blue ≥ 8/10 wins, got {blue_wins}/10"
        )

    def test_red_casualty_envelope(self, mc_results: list[dict]) -> None:
        """Iraqi losses: engine envelope 5–30 (historical ~10, wider
        because engine resolves battle earlier than 4-hour historical)."""
        avg_red = sum(r["red_destroyed"] for r in mc_results) / 10
        assert 5 <= avg_red <= 30, (
            f"Iraqi losses outside engine envelope: {avg_red:.1f} "
            f"(historical ~10, envelope 5–30)"
        )

    def test_blue_casualty_ceiling(self, mc_results: list[dict]) -> None:
        """Coalition losses: engine envelope ≤ 55 (historical 0 direct-
        combat KIA; engine resolves per-squad attrition at finer
        granularity than historical accounting, and longer run time
        with threshold=0.7 accumulates more exposure to Iraqi fires.
        See devlog for the full miss analysis — this is the primary
        calibration gap for Phase 99)."""
        avg_blue = sum(r["blue_destroyed"] for r in mc_results) / 10
        assert avg_blue <= 55, (
            f"Coalition losses exceed engine envelope: {avg_blue:.1f} "
            f"(historical 0, ceiling 55)"
        )

    def test_duration_envelope(self, mc_results: list[dict]) -> None:
        """Scenario should run ≥ 15 ticks (historical ~2,880 ticks at
        5s tick duration for 4h engagement; with working Javelin and
        bomb delivery, the engine collapses Iraqi force via initial
        volley within ~20 ticks — the historical 4-hour duration
        captures pauses and multiple engagement cycles that aren't
        currently modeled, see devlog gap #4)."""
        avg_ticks = sum(r["ticks"] for r in mc_results) / 10
        assert avg_ticks >= 15, (
            f"Scenario resolves too quickly: {avg_ticks:.0f} ticks average"
        )


# ---------------------------------------------------------------------------
# Key-dynamic assertions (smoke — single seed)
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestDebeckaKeyDynamics:
    """Single-iteration dynamic checks."""

    def test_scenario_loads_and_runs(self) -> None:
        """Sanity: scenario YAML loads and produces a running simulation."""
        result = _run_one(seed=42, max_ticks=500)
        assert result["ticks"] > 0, "No ticks executed"
        assert result["winner"], "No victory determined"

    def test_engagements_occur(self) -> None:
        """The scenario must produce engagement events (not a walkover)."""
        result = _run_one(seed=42)
        engagements = [
            e for e in result["events"] if e.event_type == "EngagementEvent"
        ]
        assert len(engagements) >= 10, (
            f"Only {len(engagements)} engagements — scenario not exercising combat"
        )

    def test_cas_bomb_delivery(self) -> None:
        """Aircraft CAS platforms (F-14B, F/A-18C, B-52H) must deliver
        bombs via bomb_rack_generic — confirms Gap 3 fix (Phase 99)
        where aircraft ordnance stations are now mapped to a weapon
        and emit EngagementEvents for bomb delivery."""
        result = _run_one(seed=42)
        bomb_events = [
            e for e in result["events"]
            if e.event_type == "EngagementEvent"
            and e.data.get("weapon_id") == "bomb_rack_generic"
        ]
        assert len(bomb_events) >= 1, (
            "No bomb delivery events — CAS ordnance weapon mapping may be broken"
        )

    def test_javelin_engages(self) -> None:
        """Javelin teams must fire at least once — confirms Gap 2 fix
        (Phase 99) where dismounted infantry guided-weapon launchers are
        exempt from seeker FOV constraint (gunner rotates to acquire)."""
        result = _run_one(seed=42)
        jav_events = [
            e for e in result["events"]
            if e.event_type == "EngagementEvent"
            and e.data.get("weapon_id") == "javelin_clm"
        ]
        assert len(jav_events) >= 1, (
            "No Javelin engagements — seeker FOV exemption may be broken"
        )
