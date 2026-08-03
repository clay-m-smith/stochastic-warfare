"""Legacy direct-construction diagnostics — Battle of Khafji (1991).

These tests bypass ``SimulationRuntimeFactory`` and the typed historical-study
runner. They are unsupported as historical validation and are not authoritative
factory-backed current-engine regression evidence. Their Phase 100 numeric
thresholds remain only as legacy drift ranges. Several documented engine gaps
constrain the direct runs (see ``docs/devlog/phase-100.md``):

- Naval gunfire (USS Missouri 16"/50) does not currently emit
  EngagementEvents when routed through ``_route_naval_engagement``'s
  shore-bombardment path.
- Iraqi artillery weapons (D-30, BM-21, 2S1, 2S3, FROG-7) are authored
  but no Iraqi artillery unit carries them in its equipment list.
- Phase 109 gives the Iraqi SA-7 teams and A-10 AGM-65 stores exact typed
  runtime loadouts. Long-range Maverick employment can therefore precede the
  A-10's GAU-8 range in the default run.

Full 10-iteration MC is prohibitively slow at the full-OOB Khafji
scale (~35 min per iteration × 10 = 5.8 hours). Tests run a 3-iteration
MC instead. Its winner, loss, and duration assertions are not compared to a
source-equivalent population or event boundary.
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
# Legacy three-seed drift guards (@slow)
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestKhafjiLegacyDiagnostic:
    """Retain Phase 100 direct-run ranges without a historical verdict."""

    def test_blue_win_count_guard(self, mc_results: list[dict]) -> None:
        """Retain the legacy three-seed blue-winner floor."""
        blue_wins = sum(1 for r in mc_results if "blue" in r["winner"])
        assert blue_wins >= 2, f"Legacy blue-win guard expected ≥ 2/3, got {blue_wins}/3"

    def test_red_destroyed_range_guard(self, mc_results: list[dict]) -> None:
        """Retain the legacy mean-red-loss range."""
        avg_red = sum(r["red_destroyed"] for r in mc_results) / 3
        assert 5 <= avg_red <= 60, f"Mean red losses {avg_red:.1f} outside legacy range [5, 60]"

    def test_blue_destroyed_ceiling_guard(self, mc_results: list[dict]) -> None:
        """Retain the legacy mean-blue-loss ceiling."""
        avg_blue = sum(r["blue_destroyed"] for r in mc_results) / 3
        assert avg_blue <= 25, f"Mean blue losses {avg_blue:.1f} exceed legacy ceiling 25"

    def test_tick_progress_guard(self, mc_results: list[dict]) -> None:
        """Retain the legacy mean-duration floor."""
        avg_ticks = sum(r["ticks"] for r in mc_results) / 3
        assert avg_ticks >= 500, f"Mean duration {avg_ticks:.0f} ticks below legacy floor 500"


# ---------------------------------------------------------------------------
# Key-dynamic assertions (single seed, smoke-level)
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestKhafjiKeyDynamics:
    """Legacy direct-run/component smoke checks, not validation evidence."""

    def test_scenario_loads_and_runs(self, mc_results: list[dict]) -> None:
        """Sanity: scenario YAML loads and produces a running simulation."""
        result = mc_results[0]
        assert result["ticks"] > 0, "No ticks executed"
        assert result["winner"], "No victory determined"

    def test_engagements_occur(self, mc_results: list[dict]) -> None:
        """Must produce engagement events — not a walkover."""
        result = mc_results[0]
        engagements = [e for e in result["events"] if e.event_type == "EngagementEvent"]
        assert len(engagements) >= 100, f"Only {len(engagements)} engagements — scenario not combat-active"

    def test_cas_aircraft_engage(self) -> None:
        """The scenario's exact A-10 GAU-8 attachment fires in a controlled
        loaded-component engagement.

        Phase 109's exact Maverick mapping lets the default force engage from
        standoff, so a GAU-8 event is no longer guaranteed before victory.
        This diagnostic retains the loaded aircraft, target, visual sensor,
        direct battle routing, event publication, and live ammunition state.
        """
        ctx = ScenarioLoader(DATA_DIR).load(SCENARIO_PATH, seed=42)
        attacker = next(unit for unit in ctx.units_by_side["blue"] if unit.unit_type == "a10a")
        target = next(unit for unit in ctx.units_by_side["red"] if unit.domain.name == "GROUND")
        gau8 = next(
            attachment
            for attachment in ctx.unit_weapons[attacker.entity_id]
            if attachment.weapon.weapon_id == "gau8_30mm"
        )
        ammo_id = gau8.ammunition[0].ammo_id
        rounds_before = gau8.weapon.ammo_state.available(ammo_id)

        attacker.position = Position(0.0, 0.0, 0.0)
        attacker.speed = 0.0
        target.position = Position(1_000.0, 0.0, 0.0)
        target.speed = 0.0
        ctx.units_by_side = {"blue": [attacker], "red": [target]}
        ctx.unit_weapons[attacker.entity_id] = (gau8,)

        events: list[EngagementEvent] = []
        ctx.event_bus.subscribe(EngagementEvent, events.append)
        BattleManager(ctx.event_bus)._execute_engagements(
            ctx,
            {"blue": [attacker]},
            {"blue": [target]},
            {"blue": np.asarray([(1_000.0, 0.0)], dtype=np.float64)},
            1.0,
            ctx.clock.current_time,
        )

        assert [(event.attacker_id, event.target_id, event.weapon_id) for event in events] == [
            (attacker.entity_id, target.entity_id, "gau8_30mm")
        ]
        assert gau8.weapon.ammo_state.available(ammo_id) < rounds_before
