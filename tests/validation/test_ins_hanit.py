"""Phase 102 regression test — INS Hanit C-802 strike (14 July 2006).

Naval vignette asserting that the INS Hanit scenario produces outcomes
consistent with the historical degraded-ECM hit envelope and that
Phase 102 new naval/ASCM infrastructure works end-to-end:

- Sa'ar 5 corvette (INS Hanit) loads with Barak-1 + Harpoon + Oto 76mm
  + Phalanx + EL/M radar + ESM loadout
- Hezbollah coastal TEL with C-802 Noor launcher loads
- C-802 Noor ASCM + 165kg SAP warhead load
- C-802 engages Hanit via missile routing path

Historical outcome (ONI 2006-2009, IDF Navy statements, USNI 2007):
- Sa'ar 5 HIT (not destroyed); damaged, 4 KIA, returned under power
- Second C-802 struck Cambodian merchantman ~60km offshore (not modeled
  in this vignette — Hezbollah + Hanit only)
- Key dynamic: sea-skimming ASCM defeating reduced-alert defensive
  posture (Barak/Phalanx reportedly off or in standby)

Engine-observed envelope:
- Hanit survives (not DESTROYED)
- C-802 firing + missile engagement events occur

Tests marked @slow for runtime assertions; load tests run fast.
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

SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data" / "scenarios" / "ins_hanit_2006" / "scenario.yaml"
)
DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _run_one(seed: int, max_ticks: int = 1500) -> dict:
    """Run one iteration of Hanit vignette and return summary metrics."""
    with open(SCENARIO_PATH) as f:
        scn = yaml.safe_load(f)
    conditions = [VictoryConditionConfig(**vc) for vc in scn["victory_conditions"]]
    loader = ScenarioLoader(str(DATA_DIR))
    ctx = loader.load(SCENARIO_PATH, seed=seed)
    victory_eval = VictoryEvaluator(
        objectives=[],
        conditions=conditions,
        event_bus=ctx.event_bus,
        max_duration_s=7200.0,
    )
    recorder = SimulationRecorder(ctx.event_bus)
    red_launchers = [
        attachment
        for unit in ctx.units_by_side["red"]
        for attachment in ctx.unit_weapons[unit.entity_id]
        if attachment.weapon.weapon_id == "c802_noor"
    ]
    c802_rounds_before = sum(
        attachment.weapon.ammo_state.available("c802_noor_warhead")
        for attachment in red_launchers
    )
    engine = SimulationEngine(
        ctx,
        config=EngineConfig(max_ticks=max_ticks),
        victory_evaluator=victory_eval,
        recorder=recorder,
    )
    recorder.start()
    while not engine.step():
        pass
    blue_units = ctx.units_by_side["blue"]
    hanit_status = blue_units[0].status if blue_units else None
    red_d = sum(1 for u in ctx.units_by_side["red"] if u.status == UnitStatus.DESTROYED)
    victory = getattr(engine, "_last_victory", None)
    winner = (getattr(victory, "winning_side", "") or "").lower()
    ticks = ctx.clock.tick_count
    c802_events = [
        event
        for event in recorder.events
        if event.event_type == "EngagementEvent"
        and event.data.get("attacker_id", "").startswith(
            "red_hezbollah_coastal_tel_",
        )
        and event.data.get("weapon_id") == "c802_noor"
        and event.data.get("ammo_type") == "c802_noor_warhead"
    ]
    c802_rounds_after = sum(
        attachment.weapon.ammo_state.available("c802_noor_warhead")
        for attachment in red_launchers
    )
    return {
        "hanit_status": hanit_status,
        "red_destroyed": red_d,
        "winner": winner,
        "ticks": ticks,
        "events": recorder.events,
        "c802_events": c802_events,
        "c802_rounds_before": c802_rounds_before,
        "c802_rounds_after": c802_rounds_after,
    }


# ---------------------------------------------------------------------------
# Load-time assertions (fast)
# ---------------------------------------------------------------------------


class TestInsHanitScenarioLoad:
    """Phase 102 naval/ASCM plumbing loads cleanly."""

    def test_scenario_loads(self) -> None:
        loader = ScenarioLoader(str(DATA_DIR))
        ctx = loader.load(SCENARIO_PATH, seed=42)
        assert ctx.config.name.startswith("INS Hanit"), (
            f"Wrong scenario loaded: {ctx.config.name}"
        )

    def test_force_structure(self) -> None:
        """Vignette has 1 Hanit (blue) + 2 Hezbollah TELs (red) = 3 total."""
        loader = ScenarioLoader(str(DATA_DIR))
        ctx = loader.load(SCENARIO_PATH, seed=42)
        assert len(ctx.units_by_side["blue"]) == 1
        assert len(ctx.units_by_side["red"]) == 2

    def test_hanit_unit_type(self) -> None:
        """Blue unit is Sa'ar 5 corvette."""
        loader = ScenarioLoader(str(DATA_DIR))
        ctx = loader.load(SCENARIO_PATH, seed=42)
        assert ctx.units_by_side["blue"][0].unit_type == "idf_saar5"

    def test_tel_unit_type(self) -> None:
        """Red units are Hezbollah coastal TELs."""
        loader = ScenarioLoader(str(DATA_DIR))
        ctx = loader.load(SCENARIO_PATH, seed=42)
        for u in ctx.units_by_side["red"]:
            assert u.unit_type == "hezbollah_coastal_tel"

    def test_scenario_duration(self) -> None:
        """2-hour vignette — brief engagement."""
        loader = ScenarioLoader(str(DATA_DIR))
        ctx = loader.load(SCENARIO_PATH, seed=42)
        assert ctx.config.duration_hours == 2.0


# ---------------------------------------------------------------------------
# Runtime assertions (@slow)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def run_result() -> dict:
    """Single-seed run — vignette is short so this is fast compared to other scenarios."""
    return _run_one(seed=42, max_ticks=1500)


@pytest.mark.slow
class TestInsHanitRuntime:
    """Runtime envelope assertions."""

    def test_scenario_progresses(self, run_result: dict) -> None:
        """Scenario runs — vignette completes within max_ticks."""
        assert run_result["ticks"] >= 10, (
            f"Scenario barely progressed: {run_result['ticks']} ticks"
        )

    def test_hanit_survives(self, run_result: dict) -> None:
        """Historical outcome: Hanit damaged but not destroyed."""
        status = run_result["hanit_status"]
        assert status != UnitStatus.DESTROYED, (
            "Hanit destroyed — historical outcome was damage + survival"
        )

    def test_c802_engages_hanit(self, run_result: dict) -> None:
        """The red launchers exercise the production ASCM route."""
        assert run_result["c802_events"]

    def test_c802_consumes_live_ammunition(self, run_result: dict) -> None:
        """A recorded launch must consume the launcher's live round."""
        assert (
            run_result["c802_rounds_after"]
            < run_result["c802_rounds_before"]
        )
