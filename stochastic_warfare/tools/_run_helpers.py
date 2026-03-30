"""Shared helper for running scenario batches.

Used by ``sensitivity.py`` and ``comparison.py`` to execute
multiple iterations of a scenario with calibration overrides.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import yaml

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.entities.base import UnitStatus
from stochastic_warfare.simulation.engine import EngineConfig, SimulationEngine
from stochastic_warfare.simulation.scenario import ScenarioLoader
from stochastic_warfare.simulation.victory import VictoryEvaluator, ObjectiveState
from stochastic_warfare.core.types import Position

logger = get_logger(__name__)


def _load_scenario_yaml(path: str) -> dict[str, Any]:
    """Load a scenario YAML file."""
    with open(path, "r") as f:
        return yaml.safe_load(f)


def _apply_overrides(config: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Apply calibration overrides to a scenario config dict."""
    config = dict(config)  # shallow copy
    cal = dict(config.get("calibration_overrides", {}))
    cal.update(overrides)
    config["calibration_overrides"] = cal
    return config


def _extract_metrics(
    engine: SimulationEngine,
    ctx: Any,
    metric_names: list[str],
) -> dict[str, float]:
    """Extract named metrics from a completed simulation context."""
    metrics: dict[str, float] = {}
    sides = sorted(ctx.units_by_side.keys())

    for name in metric_names:
        if name.endswith("_destroyed"):
            side_prefix = name.rsplit("_destroyed", 1)[0]
            for side in sides:
                if side.startswith(side_prefix):
                    destroyed = sum(
                        1 for u in ctx.units_by_side[side]
                        if u.status == UnitStatus.DESTROYED
                    )
                    metrics[name] = float(destroyed)
                    break
            else:
                metrics[name] = 0.0

        elif name.endswith("_active"):
            side_prefix = name.rsplit("_active", 1)[0]
            for side in sides:
                if side.startswith(side_prefix):
                    active = sum(
                        1 for u in ctx.units_by_side[side]
                        if u.status == UnitStatus.ACTIVE
                    )
                    metrics[name] = float(active)
                    break
            else:
                metrics[name] = 0.0

        elif name == "ticks_executed":
            metrics[name] = float(engine._tick)

        elif name.startswith("win_"):
            target_side = name[4:]
            victory = getattr(engine, "_last_victory", None)
            if victory and getattr(victory, "game_over", False):
                winning = getattr(victory, "winning_side", "") or ""
                metrics[name] = 1.0 if target_side in winning.lower() else 0.0
            else:
                metrics[name] = 0.0

        elif name == "exchange_ratio":
            # blue_destroyed / red_destroyed (avoid div by zero)
            blue_d = 0
            red_d = 0
            for side in sides:
                destroyed = sum(
                    1 for u in ctx.units_by_side[side]
                    if u.status == UnitStatus.DESTROYED
                )
                if "blue" in side:
                    blue_d = destroyed
                elif "red" in side:
                    red_d = destroyed
            metrics[name] = float(red_d) / max(1.0, float(blue_d))

        else:
            metrics[name] = 0.0

    return metrics


def run_scenario_batch(
    scenario_path: str,
    overrides: dict[str, Any],
    num_iterations: int,
    base_seed: int,
    max_ticks: int,
    metric_names: list[str],
) -> dict[str, list[float]]:
    """Run a scenario multiple times with overrides, collecting metrics.

    Parameters
    ----------
    scenario_path:
        Path to scenario YAML file.
    overrides:
        Calibration override dict to apply.
    num_iterations:
        Number of iterations to run.
    base_seed:
        Starting seed. Each iteration uses ``base_seed + i``.
    max_ticks:
        Maximum ticks per run.
    metric_names:
        Metrics to extract from each run.

    Returns
    -------
    dict[str, list[float]]
        Metric name -> list of values (one per iteration).
    """
    base_config = _load_scenario_yaml(scenario_path)
    modified = _apply_overrides(base_config, overrides)

    results: dict[str, list[float]] = {name: [] for name in metric_names}

    for i in range(num_iterations):
        seed = base_seed + i

        # Write temp YAML
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, dir=tempfile.gettempdir()
        ) as tmp:
            yaml.dump(modified, tmp, default_flow_style=False)
            tmp_path = Path(tmp.name)

        try:
            data_dir = Path(scenario_path).parent.parent
            loader = ScenarioLoader(data_dir)
            ctx = loader.load(tmp_path, seed=seed)
        finally:
            try:
                tmp_path.unlink()
            except OSError:
                pass

        # Build victory evaluator
        victory_evaluator = _build_victory_evaluator(ctx, modified)

        engine = SimulationEngine(
            ctx,
            config=EngineConfig(max_ticks=max_ticks),
            victory_evaluator=victory_evaluator,
        )
        engine.run()

        metrics = _extract_metrics(engine, ctx, metric_names)
        for name in metric_names:
            results[name].append(metrics.get(name, 0.0))

    return results


def _build_victory_evaluator(ctx: Any, config: dict[str, Any]) -> VictoryEvaluator:
    """Build a VictoryEvaluator from scenario config dict."""
    objectives = []
    for obj_cfg in config.get("objectives", []):
        pos_list = obj_cfg.get("position", [0.0, 0.0])
        pos = Position(easting=pos_list[0], northing=pos_list[1], altitude=0.0)
        objectives.append(
            ObjectiveState(
                objective_id=obj_cfg["objective_id"],
                position=pos,
                radius_m=obj_cfg.get("radius_m", 500.0),
            )
        )

    from stochastic_warfare.simulation.scenario import VictoryConditionConfig
    conditions = [
        VictoryConditionConfig(**vc)
        for vc in config.get("victory_conditions", [])
    ]

    max_duration_s = config.get("duration_hours", 24) * 3600.0

    return VictoryEvaluator(
        objectives=objectives,
        conditions=conditions,
        event_bus=ctx.event_bus,
        max_duration_s=max_duration_s,
    )
