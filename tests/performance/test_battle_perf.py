"""Phase 70d: Performance verification tests.

Benchmark tests for battle simulation performance and determinism.
Slow tests (golan_heights benchmark) are marked @pytest.mark.slow.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
SCENARIOS_DIR = DATA_DIR / "scenarios"


def _run_scenario(scenario_name: str, seed: int = 42) -> dict:
    """Run a scenario via SimulationEngine.run() and return timing + outcome."""
    from stochastic_warfare.simulation.scenario import ScenarioLoader
    from stochastic_warfare.simulation.engine import SimulationEngine, EngineConfig
    from stochastic_warfare.simulation.recorder import SimulationRecorder
    from stochastic_warfare.simulation.victory import VictoryEvaluator
    from stochastic_warfare.entities.base import UnitStatus
    from stochastic_warfare.core.types import Position

    scenario_path = SCENARIOS_DIR / scenario_name / "scenario.yaml"
    if not scenario_path.exists():
        pytest.skip(f"Scenario {scenario_name} not found at {scenario_path}")

    loader = ScenarioLoader(DATA_DIR)
    ctx = loader.load(scenario_path, seed=seed)

    recorder = SimulationRecorder(ctx.event_bus)

    # Build victory evaluator from scenario config
    victory_eval = None
    cfg = ctx.config
    if hasattr(cfg, "victory_conditions") and cfg.victory_conditions:
        from stochastic_warfare.simulation.victory import ObjectiveState

        objectives = []
        if hasattr(cfg, "objectives") and cfg.objectives:
            for obj in cfg.objectives:
                pos = obj.position if hasattr(obj, "position") else [0, 0]
                objectives.append(
                    ObjectiveState(
                        objective_id=obj.objective_id,
                        position=Position(
                            easting=pos[0] if len(pos) > 0 else 0,
                            northing=pos[1] if len(pos) > 1 else 0,
                        ),
                        radius_m=obj.radius_m,
                    )
                )
        victory_eval = VictoryEvaluator(
            objectives=objectives,
            conditions=cfg.victory_conditions,
            event_bus=ctx.event_bus,
            max_duration_s=cfg.duration_hours * 3600.0,
        )

    engine_cfg = EngineConfig(max_ticks=20000, snapshot_interval_ticks=0)
    engine = SimulationEngine(
        ctx,
        config=engine_cfg,
        victory_evaluator=victory_eval,
        recorder=recorder,
    )

    start = time.perf_counter()
    run_result = engine.run()
    elapsed = time.perf_counter() - start

    # Extract winner from run result
    winner = None
    if run_result.victory_result:
        winner = run_result.victory_result.winning_side

    # Casualty counts per side
    casualties = {}
    for side, units in ctx.units_by_side.items():
        casualties[side] = sum(
            1
            for u in units
            if u.status in (UnitStatus.DESTROYED, UnitStatus.DISABLED, UnitStatus.SURRENDERED)
        )

    return {
        "elapsed_s": elapsed,
        "winner": winner,
        "casualties": casualties,
        "ticks": run_result.ticks_executed,
    }


# ---------------------------------------------------------------------------
# Performance benchmarks
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestGolanBenchmark:
    """Golan Heights scenario performance benchmark."""

    def test_golan_heights_benchmark(self) -> None:
        """Golan Heights (290 units, 18hr) completes in < 180s."""
        result = _run_scenario("golan_heights")
        assert result["elapsed_s"] < 180.0, (
            f"Golan Heights took {result['elapsed_s']:.1f}s (limit: 180s)"
        )

    def test_determinism_golan_heights(self) -> None:
        """Two identical-seed runs produce same winner + casualties."""
        r1 = _run_scenario("golan_heights", seed=42)
        r2 = _run_scenario("golan_heights", seed=42)
        assert r1["winner"] == r2["winner"], (
            f"Winner diverged: {r1['winner']} vs {r2['winner']}"
        )
        assert r1["casualties"] == r2["casualties"], (
            f"Casualties diverged: {r1['casualties']} vs {r2['casualties']}"
        )


class TestEastingBenchmark:
    """73 Easting scenario performance + determinism."""

    def test_73_easting_benchmark(self) -> None:
        """73 Easting (small scenario) completes in < 30s."""
        result = _run_scenario("73_easting")
        assert result["elapsed_s"] < 30.0, (
            f"73 Easting took {result['elapsed_s']:.1f}s (limit: 30s)"
        )

    def test_determinism_73_easting(self) -> None:
        """Two identical-seed runs produce same winner + casualties."""
        r1 = _run_scenario("73_easting", seed=42)
        r2 = _run_scenario("73_easting", seed=42)
        assert r1["winner"] == r2["winner"], (
            f"Winner diverged: {r1['winner']} vs {r2['winner']}"
        )
        assert r1["casualties"] == r2["casualties"], (
            f"Casualties diverged: {r1['casualties']} vs {r2['casualties']}"
        )
