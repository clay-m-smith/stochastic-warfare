"""Doctrine school comparison tool.

Runs a scenario with different doctrinal schools and compares outcomes.
Each school is tested over N iterations to produce win rate, casualty,
and duration statistics.
"""

from __future__ import annotations

import copy
import statistics
from dataclasses import dataclass, field
from typing import Any

from stochastic_warfare.tools._run_helpers import run_scenario_batch


@dataclass
class DoctrineCompareConfig:
    """Configuration for a doctrine comparison run."""

    scenario_path: str
    side_to_vary: str = "blue"
    schools: list[str] = field(default_factory=list)
    num_iterations: int = 10
    base_seed: int = 42
    max_ticks: int = 100


@dataclass
class SchoolResult:
    """Per-school aggregate results."""

    school_id: str
    display_name: str = ""
    win_rate: float = 0.0
    mean_blue_destroyed: float = 0.0
    mean_red_destroyed: float = 0.0
    mean_duration_ticks: float = 0.0
    std_blue_destroyed: float = 0.0
    std_red_destroyed: float = 0.0
    std_duration_ticks: float = 0.0


@dataclass
class DoctrineCompareResult:
    """Full doctrine comparison result."""

    scenario: str
    side_to_vary: str
    num_iterations: int
    results: list[SchoolResult] = field(default_factory=list)


def _load_scenario_yaml(path: str) -> dict[str, Any]:
    """Load scenario YAML as a dict."""
    import yaml
    from pathlib import Path

    with Path(path).open() as f:
        return yaml.safe_load(f)


def run_doctrine_comparison(config: DoctrineCompareConfig) -> DoctrineCompareResult:
    """Run doctrine comparison across multiple schools.

    For each school, modifies the scenario's school_config to assign the
    school to the specified side, then runs N iterations collecting
    win rate, casualty, and duration metrics.
    """
    import tempfile
    from pathlib import Path

    import yaml

    base_config = _load_scenario_yaml(config.scenario_path)
    win_metric = f"win_{config.side_to_vary}"
    metric_names = ["blue_destroyed", "red_destroyed", "ticks_executed", win_metric]

    school_results: list[SchoolResult] = []

    for school_id in config.schools:
        # Deep copy base config and set school for the varied side
        modified = copy.deepcopy(base_config)
        sc = modified.setdefault("school_config", {})
        sc[f"{config.side_to_vary}_school"] = school_id

        # Write temp YAML and run batch
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, dir=tempfile.gettempdir()
        ) as tmp:
            yaml.dump(modified, tmp, default_flow_style=False)
            tmp_path = Path(tmp.name)

        try:
            metrics = run_scenario_batch(
                scenario_path=str(tmp_path),
                overrides={},
                num_iterations=config.num_iterations,
                base_seed=config.base_seed,
                max_ticks=config.max_ticks,
                metric_names=metric_names,
            )
        finally:
            try:
                tmp_path.unlink()
            except OSError:
                pass

        # Aggregate results
        blue_d = metrics.get("blue_destroyed", [])
        red_d = metrics.get("red_destroyed", [])
        ticks = metrics.get("ticks_executed", [])
        wins = metrics.get(win_metric, [])

        def _std(vals: list[float]) -> float:
            return statistics.stdev(vals) if len(vals) > 1 else 0.0

        school_results.append(SchoolResult(
            school_id=school_id,
            win_rate=statistics.mean(wins) if wins else 0.0,
            mean_blue_destroyed=statistics.mean(blue_d) if blue_d else 0.0,
            mean_red_destroyed=statistics.mean(red_d) if red_d else 0.0,
            mean_duration_ticks=statistics.mean(ticks) if ticks else 0.0,
            std_blue_destroyed=_std(blue_d),
            std_red_destroyed=_std(red_d),
            std_duration_ticks=_std(ticks),
        ))

    return DoctrineCompareResult(
        scenario=config.scenario_path,
        side_to_vary=config.side_to_vary,
        num_iterations=config.num_iterations,
        results=school_results,
    )
