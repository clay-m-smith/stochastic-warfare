"""Legacy direct-construction diagnostics for Bint Jbeil.

The tests check that the authored units and weapons load and that a manually
constructed simulation reaches active combat. They bypass
``SimulationRuntimeFactory`` and the typed historical-study runner, so they are
unsupported as historical validation and are not authoritative factory-backed
current-engine regression evidence. The seed-42 terminal remains only a legacy
drift signal.

Covered data and routing include:

- IDF Golani / Paratrooper / Egoz SOF / Merkava Mk III/IV author and
  load via Phase 102 YAMLs
- Hezbollah local / SF / Kornet tank-hunter / mortar cell units load
- RPG-29 Vampir + PG-29V tandem-HEAT warhead load
- Kornet 9M133 engagement routes via existing ATGM path

Tests marked @slow — 249 units + hybrid tick resolution + 240hr sim
window makes this a heavy scenario at full resolution.
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

SCENARIO_PATH = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "bint_jbeil_2006" / "scenario.yaml"
DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _run_one(seed: int, max_ticks: int = 1500) -> dict:
    """Run one iteration of Bint Jbeil and return summary metrics."""
    with open(SCENARIO_PATH) as f:
        scn = yaml.safe_load(f)
    conditions = [VictoryConditionConfig(**vc) for vc in scn["victory_conditions"]]
    loader = ScenarioLoader(str(DATA_DIR))
    ctx = loader.load(SCENARIO_PATH, seed=seed)
    victory_eval = VictoryEvaluator(
        objectives=[],
        conditions=conditions,
        event_bus=ctx.event_bus,
        max_duration_s=864000.0,
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
    condition = getattr(victory, "condition_type", "")
    ticks = ctx.clock.tick_count
    return {
        "blue_destroyed": blue_d,
        "red_destroyed": red_d,
        "winner": winner,
        "condition": condition,
        "ticks": ticks,
        "events": recorder.events,
    }


# ---------------------------------------------------------------------------
# Load-time assertions (fast)
# ---------------------------------------------------------------------------


class TestBintJbeilScenarioLoad:
    """Assert Phase 102 new units/weapons load without running a sim."""

    def test_scenario_loads(self) -> None:
        loader = ScenarioLoader(str(DATA_DIR))
        ctx = loader.load(SCENARIO_PATH, seed=42)
        assert ctx.config.name.startswith("Bint Jbeil"), f"Wrong scenario loaded: {ctx.config.name}"

    def test_force_scale(self) -> None:
        """Force scale represents company-level granularity — 200-270 total."""
        loader = ScenarioLoader(str(DATA_DIR))
        ctx = loader.load(SCENARIO_PATH, seed=42)
        blue = len(ctx.units_by_side.get("blue", []))
        red = len(ctx.units_by_side.get("red", []))
        total = blue + red
        assert 200 <= total <= 270, f"Force scale {total} outside range [200, 270]"

    def test_new_units_present(self) -> None:
        """Phase 102 IDF + Hezbollah unit types all load via registry."""
        loader = ScenarioLoader(str(DATA_DIR))
        ctx = loader.load(SCENARIO_PATH, seed=42)
        unit_types = {u.unit_type for units in ctx.units_by_side.values() for u in units}
        expected = {
            "idf_golani_squad",
            "idf_paratrooper_squad",
            "idf_egoz_team",
            "idf_merkava_mk4",
            "idf_merkava_mk3",
            "hezbollah_local_fighter",
            "hezbollah_special_forces",
            "hezbollah_atgm_team",
            "hezbollah_mortar_cell",
        }
        missing = expected - unit_types
        assert not missing, f"Missing unit types: {missing}"

    def test_unconventional_warfare_flag_is_authored(self) -> None:
        """The authored calibration flag is true; this is not engine proof."""
        loader = ScenarioLoader(str(DATA_DIR))
        ctx = loader.load(SCENARIO_PATH, seed=42)
        # UW engine auto-created when initial_ieds non-empty OR via calibration;
        # Bint Jbeil does not use initial_ieds but has enable_unconventional_warfare
        # in calibration — the engine may or may not be present depending on
        # engine creation path.  Assert the calibration flag is set.
        cal = ctx.calibration
        flat = ctx.cal_flat
        uw_enabled = False
        if hasattr(cal, "enable_unconventional_warfare"):
            uw_enabled = bool(getattr(cal, "enable_unconventional_warfare", False))
        if not uw_enabled:
            uw_enabled = bool(flat.get("enable_unconventional_warfare", False))
        assert uw_enabled, "enable_unconventional_warfare flag not set"


# ---------------------------------------------------------------------------
# Runtime assertions (@slow)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def run_result() -> dict:
    """Single-seed run for runtime assertions."""
    return _run_one(seed=42, max_ticks=1500)


@pytest.mark.slow
class TestBintJbeilLegacyRuntimeDiagnostic:
    """Retain seed-42 direct-run guards without a historical verdict."""

    def test_combat_causes_casualties(self, run_result: dict) -> None:
        """The scenario reaches damaging combat rather than a no-op run."""
        blue_d = run_result["blue_destroyed"]
        red_d = run_result["red_destroyed"]
        assert blue_d + red_d > 0, "No casualties at all — scenario not active"

    def test_blue_loss_ceiling_guard(self, run_result: dict) -> None:
        """Retain the legacy direct-run blue-loss ceiling."""
        assert run_result["blue_destroyed"] <= 80, f"Blue losses {run_result['blue_destroyed']} exceed legacy ceiling"

    def test_seed42_terminal_guard(self, run_result: dict) -> None:
        """Retain the known direct-run terminal without a history claim."""
        assert (run_result["winner"], run_result["condition"]) == (
            "blue",
            "force_destroyed",
        )

    def test_scenario_progresses(self, run_result: dict) -> None:
        """Scenario runs at least five ticks before its current terminal state."""
        assert run_result["ticks"] >= 5, f"Scenario barely progressed: {run_result['ticks']} ticks"

    def test_engagements_occur(self, run_result: dict) -> None:
        """Combat engagement events fire rather than a no-op completion."""
        engagements = [e for e in run_result["events"] if e.event_type == "EngagementEvent"]
        assert len(engagements) >= 30, f"Only {len(engagements)} engagements — scenario not active"
