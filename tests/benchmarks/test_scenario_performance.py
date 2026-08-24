"""Production-scenario performance measurements and semantic replay tests."""

from __future__ import annotations

import math
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.benchmark

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
SCENARIOS_DIR = DATA_DIR / "scenarios"


def _run_scenario(scenario_name: str, seed: int = 42) -> dict:
    """Run a production-owned session and return timing plus exact outcome."""
    from stochastic_warfare.entities.base import UnitStatus
    from stochastic_warfare.simulation.engine import EngineConfig
    from stochastic_warfare.simulation.runtime import (
        AnalysisVariant,
        SimulationRuntimeFactory,
    )

    scenario_path = SCENARIOS_DIR / scenario_name / "scenario.yaml"
    if not scenario_path.exists():
        pytest.fail(f"required scenario {scenario_name} is missing: {scenario_path}")

    variant_id = "performance"
    prepared = SimulationRuntimeFactory().prepare(
        scenario_path,
        DATA_DIR,
        [AnalysisVariant(variant_id=variant_id)],
    )
    session = prepared.build(
        variant_id,
        seed=seed,
        max_ticks=20_000,
        record_events=True,
        engine_config=EngineConfig(
            max_ticks=20_000,
            snapshot_interval_ticks=0,
        ),
    )

    start = time.perf_counter()
    run_result = session.run_to_completion()
    elapsed = time.perf_counter() - start
    if run_result.ticks_executed != session.context.clock.tick_count:
        raise RuntimeError("Runtime result tick count does not match the production clock")
    if run_result.duration_s != session.context.clock.elapsed.total_seconds():
        raise RuntimeError("Runtime result duration does not match the production clock")
    if run_result.victory_result.tick != run_result.ticks_executed:
        raise RuntimeError("Terminal victory tick does not match the runtime result")

    # Casualty counts per side
    casualties = {}
    for side, units in session.context.units_by_side.items():
        casualties[side] = sum(
            1 for u in units if u.status in (UnitStatus.DESTROYED, UnitStatus.DISABLED, UnitStatus.SURRENDERED)
        )

    return {
        "elapsed_s": elapsed,
        "winner": run_result.victory_result.winning_side,
        "condition_type": run_result.victory_result.condition_type,
        "duration_s": run_result.duration_s,
        "casualties": casualties,
        "ticks": run_result.ticks_executed,
    }


# ---------------------------------------------------------------------------
# Performance benchmarks
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def golan_replay_pair() -> tuple[dict, dict]:
    """Run the two independent samples needed for measurement and replay."""
    return (
        _run_scenario("golan_heights", seed=42),
        _run_scenario("golan_heights", seed=42),
    )


@pytest.mark.slow
class TestGolanMeasurement:
    """Golan production workload measurement and semantic replay."""

    def test_golan_heights_measurement_only(
        self,
        golan_replay_pair: tuple[dict, dict],
    ) -> None:
        """Expose one positive raw duration without a regression decision."""
        result = golan_replay_pair[0]
        assert math.isfinite(result["elapsed_s"])
        assert result["elapsed_s"] > 0.0
        assert result["winner"] == "blue"
        assert result["condition_type"] == "time_expired"
        assert result["duration_s"] == 64_800.0
        assert result["ticks"] == 6480

    def test_determinism_golan_heights(
        self,
        golan_replay_pair: tuple[dict, dict],
    ) -> None:
        """Two identical-seed runs produce same winner + casualties."""
        r1, r2 = golan_replay_pair
        assert _semantic_result(r1) == _semantic_result(r2)


class TestEastingMeasurement:
    """73 Easting measurement-only sample plus semantic determinism."""

    def test_73_easting_measurement_only(self) -> None:
        """Expose one positive raw duration without a regression decision."""
        result = _run_scenario("73_easting")
        assert math.isfinite(result["elapsed_s"])
        assert result["elapsed_s"] > 0.0
        assert result["winner"] == "blue"
        assert result["condition_type"] == "time_expired"
        assert result["duration_s"] == 1_800.0
        assert result["ticks"] == 360

    def test_determinism_73_easting(self) -> None:
        """Two identical-seed runs produce same winner + casualties."""
        r1 = _run_scenario("73_easting", seed=42)
        r2 = _run_scenario("73_easting", seed=42)
        assert _semantic_result(r1) == _semantic_result(r2)


def _semantic_result(result: dict) -> tuple:
    """Return all deterministic public outcome fields from a timed sample."""
    return (
        result["winner"],
        result["condition_type"],
        result["duration_s"],
        result["casualties"],
        result["ticks"],
    )
