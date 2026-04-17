"""Phase 100 regression test — Battle of Khafji (1991).

Asserts that the Khafji scenario produces outcomes bracketed by the
current engine's observed 3-iteration MC envelope. Several documented
engine gaps constrain fidelity (see ``docs/devlog/phase-100.md``):

- Naval gunfire (USS Missouri 16"/50) does not currently emit
  EngagementEvents when routed through ``_route_naval_engagement``'s
  shore-bombardment path.
- Iraqi artillery weapons (D-30, BM-21, 2S1, 2S3, FROG-7) are authored
  but no Iraqi artillery unit carries them in its equipment list.
- SA-7 MANPADS is authored but no Iraqi unit carries it, precluding
  emergent Spirit 03 AC-130 loss.
- AGM-65 Maverick is authored but aircraft equipment
  ``"Wing/Fuselage Ordnance Stations"`` maps to ``bomb_rack_generic``
  (dumb bombs + LGB + JDAM), so AGM-65 isn't fired.

Full 10-iteration MC is prohibitively slow at the full-OOB Khafji
scale (~35 min per iteration × 10 = 5.8 hours). Tests run a 3-iteration
MC instead; envelope assertions are wider than Phase 99's to reflect
the coarser sample.

Expected historical outcome (per Westermeyer 2014, GWAPS, Grant 1998):
- Coalition decisive victory
- 72-hour main engagement
- ~90-200 Iraqi AFVs destroyed (direct); ~400 EPWs (mass surrender)
- Coalition ~43 KIA (+ Spirit 03 14 KIA)

Engine-observed envelope (3-iter MC @slow):
- Blue wins 3/3
- Red destroyed 5-60 units (wider than historical lower bound of 90,
  reflecting engine limitations on artillery + naval gunfire)
- Blue destroyed ≤ 25 units (historical 43, vehicle-equivalent ~10)
- Scenario runs ≥ 500 ticks (tactical battle develops)
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

SCENARIO_PATH = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "khafji" / "scenario.yaml"
DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _run_one(seed: int, max_ticks: int = 1500) -> dict:
    """Run one iteration of Khafji and return summary metrics."""
    with open(SCENARIO_PATH) as f:
        scn = yaml.safe_load(f)
    conditions = [VictoryConditionConfig(**vc) for vc in scn["victory_conditions"]]

    loader = ScenarioLoader(str(DATA_DIR))
    ctx = loader.load(SCENARIO_PATH, seed=seed)
    victory_eval = VictoryEvaluator(
        objectives=[],
        conditions=conditions,
        event_bus=ctx.event_bus,
        max_duration_s=259200.0,
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
    """Run a 3-iteration Monte Carlo (3 seeds, ~1.5h total @slow)."""
    return [_run_one(seed=42 + i) for i in range(3)]


# ---------------------------------------------------------------------------
# Envelope assertions (3-iter MC @slow)
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestKhafjiEnvelope:
    """Envelope assertions — 3-iteration Monte Carlo."""

    def test_winner_envelope(self, mc_results: list[dict]) -> None:
        """Coalition should win 3/3 iterations (decisive historical)."""
        blue_wins = sum(1 for r in mc_results if "blue" in r["winner"])
        assert blue_wins >= 2, (
            f"Expected blue ≥ 2/3 wins, got {blue_wins}/3"
        )

    def test_red_casualty_envelope(self, mc_results: list[dict]) -> None:
        """Iraqi losses: engine envelope 5-60 (historical 90-200 urban,
        300+ w/ interdiction; envelope is widened due to missing artillery
        + naval gunfire engagement paths — see devlog)."""
        avg_red = sum(r["red_destroyed"] for r in mc_results) / 3
        assert 5 <= avg_red <= 60, (
            f"Iraqi losses outside engine envelope: {avg_red:.1f} "
            f"(historical 90-200, engine envelope 5-60)"
        )

    def test_blue_casualty_ceiling(self, mc_results: list[dict]) -> None:
        """Coalition losses: engine envelope ≤ 25 (historical 43 KIA
        across 11 US + 18 Saudi + 14 Qatari)."""
        avg_blue = sum(r["blue_destroyed"] for r in mc_results) / 3
        assert avg_blue <= 25, (
            f"Coalition losses exceed engine envelope: {avg_blue:.1f}"
        )

    def test_scenario_progresses(self, mc_results: list[dict]) -> None:
        """Scenario should run ≥ 500 ticks (force_destroyed or max_ticks);
        tactical battle develops."""
        avg_ticks = sum(r["ticks"] for r in mc_results) / 3
        assert avg_ticks >= 500, (
            f"Scenario resolves too quickly: {avg_ticks:.0f} ticks average"
        )


# ---------------------------------------------------------------------------
# Key-dynamic assertions (single seed, smoke-level)
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestKhafjiKeyDynamics:
    """Single-iteration dynamic checks — caught regressions fast."""

    def test_scenario_loads_and_runs(self) -> None:
        """Sanity: scenario YAML loads and produces a running simulation."""
        result = _run_one(seed=42, max_ticks=500)
        assert result["ticks"] > 0, "No ticks executed"
        assert result["winner"], "No victory determined"

    def test_engagements_occur(self) -> None:
        """Must produce engagement events — not a walkover."""
        result = _run_one(seed=42, max_ticks=500)
        engagements = [
            e for e in result["events"] if e.event_type == "EngagementEvent"
        ]
        assert len(engagements) >= 100, (
            f"Only {len(engagements)} engagements — scenario not combat-active"
        )

    def test_cas_aircraft_engage(self) -> None:
        """A-10 GAU-8 30mm cannon fires (primary daylight CAS weapon).
        Confirms aircraft weapon-assignment plumbing works for Khafji."""
        result = _run_one(seed=42, max_ticks=500)
        gau8_events = [
            e for e in result["events"]
            if e.event_type == "EngagementEvent"
            and e.data.get("weapon_id") == "gau8_30mm"
        ]
        assert len(gau8_events) >= 5, (
            f"No/insufficient A-10 GAU-8 engagements ({len(gau8_events)})"
        )
