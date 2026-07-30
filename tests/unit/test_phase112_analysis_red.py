"""Phase 112 production-path red proofs for REM-017."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from stochastic_warfare.simulation.engine import (
    SimulationEngine,
    SimulationRunResult,
)
from stochastic_warfare.simulation.runtime import AnalysisVariant
from stochastic_warfare.tools._run_helpers import run_scenario_batch
from stochastic_warfare.tools.comparison import (
    ComparisonConfig,
    run_comparison,
)
from stochastic_warfare.tools.sensitivity import SweepConfig, run_sweep


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SCENARIO_PATH = _PROJECT_ROOT / "data/scenarios/test_campaign/scenario.yaml"


def test_sweep_rejects_an_unknown_metric_before_running() -> None:
    """An unsupported metric must not become an authoritative zero vector."""
    config = SweepConfig(
        scenario_path=str(_SCENARIO_PATH),
        parameter_name="hit_probability_modifier",
        values=[1.0],
        metric_names=["unsupported_metric"],
        iterations_per_point=2,
        base_seed=42,
        max_ticks=1,
    )

    with pytest.raises(ValueError, match="unsupported_metric"):
        run_sweep(config)


def test_dead_calibration_key_rejects_at_every_python_analysis_boundary() -> None:
    """Retired data cannot collapse into an authoritative empty patch."""
    with pytest.raises(
        ValueError,
        match="unsupported dead calibration.*advance_speed",
    ):
        AnalysisVariant(
            variant_id="dead-key",
            calibration_patch={"advance_speed": 999.0},
        )

    with pytest.raises(
        ValueError,
        match="unsupported dead calibration.*advance_speed",
    ):
        run_sweep(
            SweepConfig(
                scenario_path=str(_SCENARIO_PATH),
                parameter_name="advance_speed",
                values=[1.0, 999.0],
                iterations_per_point=2,
                max_ticks=1,
            ),
        )

    with pytest.raises(
        ValueError,
        match="unsupported dead calibration.*advance_speed",
    ):
        run_comparison(
            ComparisonConfig(
                scenario_path=str(_SCENARIO_PATH),
                overrides_a={"advance_speed": 1.0},
                overrides_b={"advance_speed": 999.0},
                num_iterations=2,
                max_ticks=1,
            ),
        )


def test_batch_rejects_an_authored_empty_roster(tmp_path: Path) -> None:
    """A schema-valid but force-empty scenario must fail before simulation."""
    config = yaml.safe_load(_SCENARIO_PATH.read_text(encoding="utf-8"))
    for side in config["sides"]:
        side["units"] = []

    scenario_path = tmp_path / "empty-roster.yaml"
    scenario_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    with pytest.raises(ValueError, match=r"(?i)(empty|roster|units)"):
        run_scenario_batch(
            scenario_path=str(scenario_path),
            overrides={},
            num_iterations=2,
            base_seed=42,
            max_ticks=1,
            metric_names=["blue_active", "red_active"],
            data_dir=_PROJECT_ROOT / "data",
        )


def test_supported_sweep_changes_a_metric_from_real_run_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A typed calibration change must affect completed production runs."""
    completed_runs: list[SimulationRunResult] = []
    original_run = SimulationEngine.run

    def record_real_result(engine: SimulationEngine) -> SimulationRunResult:
        result = original_run(engine)
        completed_runs.append(result)
        return result

    monkeypatch.setattr(SimulationEngine, "run", record_real_result)
    result = run_sweep(
        SweepConfig(
            scenario_path=str(_SCENARIO_PATH),
            parameter_name="hit_probability_modifier",
            values=[0.0, 10.0],
            metric_names=["blue_destroyed", "red_destroyed"],
            iterations_per_point=3,
            base_seed=42,
            max_ticks=200,
        )
    )

    vectors_by_value: dict[float, dict[str, list[float]]] = {
        point.parameter_value: {
            metric.metric: metric.values
            for metric in point.metric_results
        }
        for point in result.points
    }

    assert len(completed_runs) == 6
    assert all(run.ticks_executed > 0 for run in completed_runs)
    assert all(run.victory_result.game_over for run in completed_runs)
    assert any(
        vectors_by_value[0.0][metric] != vectors_by_value[10.0][metric]
        for metric in ("blue_destroyed", "red_destroyed")
    )
