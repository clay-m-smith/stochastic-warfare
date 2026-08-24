"""Legacy direct-construction diagnostics — Debecka Pass (2003).

These tests bypass ``SimulationRuntimeFactory`` and the typed historical-study
runner. They are unsupported as historical validation and are not authoritative
factory-backed current-engine regression evidence. The exact Phase 115 seeds
42–51 capture is retained only as a deterministic legacy drift signal.
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

SCENARIO_PATH = Path(__file__).resolve().parents[3] / "data" / "scenarios" / "debecka_pass" / "scenario.yaml"
DATA_DIR = Path(__file__).resolve().parents[3] / "data"


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
# Exact Phase 115 legacy capture
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestDebeckaLegacyDiagnostic:
    """Retain the exact Phase 115 direct-run capture without a verdict."""

    def test_phase115_blue_winner_capture(self, mc_results: list[dict]) -> None:
        """Retain the four captured blue-winning seeds exactly."""
        winner_seeds = tuple(42 + offset for offset, result in enumerate(mc_results) if result["winner"] == "blue")
        assert (len(winner_seeds), winner_seeds) == (
            4,
            (48, 49, 50, 51),
        )

    def test_phase115_red_destroyed_mean(self, mc_results: list[dict]) -> None:
        """Retain the captured mean of 6.7 destroyed red unit records."""
        mean_red = sum(result["red_destroyed"] for result in mc_results) / 10
        assert mean_red == pytest.approx(6.7)

    def test_phase115_blue_destroyed_mean(self, mc_results: list[dict]) -> None:
        """Retain the captured mean of 42.5 destroyed blue unit records."""
        mean_blue = sum(result["blue_destroyed"] for result in mc_results) / 10
        assert mean_blue == pytest.approx(42.5)

    def test_phase115_tick_mean(self, mc_results: list[dict]) -> None:
        """Retain the captured mean duration of 1,887.5 ticks."""
        mean_ticks = sum(result["ticks"] for result in mc_results) / 10
        assert mean_ticks == pytest.approx(1_887.5)


# ---------------------------------------------------------------------------
# Key-dynamic assertions (smoke — single seed)
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestDebeckaKeyDynamics:
    """Legacy direct-run routing smoke checks, not validation evidence."""

    def test_scenario_loads_and_runs(self) -> None:
        """Sanity: scenario YAML loads and produces a running simulation."""
        result = _run_one(seed=42, max_ticks=500)
        assert result["ticks"] > 0, "No ticks executed"
        assert result["winner"], "No victory determined"

    def test_engagements_occur(self) -> None:
        """The scenario must produce engagement events (not a walkover)."""
        result = _run_one(seed=42)
        engagements = [e for e in result["events"] if e.event_type == "EngagementEvent"]
        assert len(engagements) >= 10, f"Only {len(engagements)} engagements — scenario not exercising combat"

    def test_cas_bomb_delivery(self) -> None:
        """Retain a seed-42 bomb event as a direct-run smoke diagnostic."""
        result = _run_one(seed=42)
        bomb_events = [
            e
            for e in result["events"]
            if e.event_type == "EngagementEvent" and e.data.get("weapon_id") == "bomb_rack_generic"
        ]
        assert len(bomb_events) >= 1, "No bomb delivery events — CAS ordnance weapon mapping may be broken"

    def test_javelin_engages(self) -> None:
        """Retain a seed-42 Javelin event as a direct-run smoke diagnostic."""
        result = _run_one(seed=42)
        jav_events = [
            e
            for e in result["events"]
            if e.event_type == "EngagementEvent" and e.data.get("weapon_id") == "javelin_clm"
        ]
        assert len(jav_events) >= 1, "No Javelin engagements — seeker FOV exemption may be broken"
