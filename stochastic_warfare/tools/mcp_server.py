"""MCP server for Claude Code integration.

Provides 7 tools for running scenarios, querying results, Monte Carlo
analysis, and parameter comparison — all via stdio transport.

Requires ``mcp[cli]>=1.2.0`` (install via ``uv sync --extra mcp``).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.tools.result_store import ResultStore, StoredResult
from stochastic_warfare.tools.serializers import make_error, make_success, serialize_to_dict

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_STORE_SIZE = 20
_MAX_STORED_EVENTS = 500
_MAX_QUERY_EVENTS = 100

# Global result store (lives for server lifetime)
_store = ResultStore(max_size=_MAX_STORE_SIZE)

# Project root detection
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DATA_DIR = _PROJECT_ROOT / "data"
_SCENARIOS_DIR = _DATA_DIR / "scenarios"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_scenario_path(name: str) -> Path | None:
    """Find scenario YAML by name."""
    candidate = _SCENARIOS_DIR / name / "scenario.yaml"
    if candidate.exists():
        return candidate
    return None


def _run_single(
    scenario_path: Path, seed: int, max_ticks: int,
) -> tuple[dict[str, Any], Any, Any]:
    """Run a single scenario synchronously. Returns (summary, recorder, ctx)."""
    from stochastic_warfare.entities.base import UnitStatus
    from stochastic_warfare.simulation.engine import EngineConfig, SimulationEngine
    from stochastic_warfare.simulation.recorder import SimulationRecorder
    from stochastic_warfare.simulation.scenario import ScenarioLoader
    from stochastic_warfare.simulation.victory import VictoryEvaluator, ObjectiveState
    from stochastic_warfare.core.types import Position
    import yaml

    with open(scenario_path) as f:
        config_dict = yaml.safe_load(f)

    loader = ScenarioLoader(_DATA_DIR)
    ctx = loader.load(scenario_path, seed=seed)

    # Build victory evaluator
    objectives = []
    for obj_cfg in config_dict.get("objectives", []):
        pos_list = obj_cfg.get("position", [0.0, 0.0])
        objectives.append(ObjectiveState(
            objective_id=obj_cfg["objective_id"],
            position=Position(easting=pos_list[0], northing=pos_list[1]),
            radius_m=obj_cfg.get("radius_m", 500.0),
        ))

    from stochastic_warfare.simulation.scenario import VictoryConditionConfig
    conditions = [VictoryConditionConfig(**vc) for vc in config_dict.get("victory_conditions", [])]
    max_dur = config_dict.get("duration_hours", 24) * 3600.0

    victory_eval = VictoryEvaluator(
        objectives=objectives,
        conditions=conditions,
        event_bus=ctx.event_bus,
        max_duration_s=max_dur,
    )

    recorder = SimulationRecorder(ctx.event_bus)
    engine = SimulationEngine(
        ctx,
        config=EngineConfig(max_ticks=max_ticks),
        victory_evaluator=victory_eval,
        recorder=recorder,
    )
    run_result = engine.run()

    # Build summary
    side_summaries = {}
    for side, units in ctx.units_by_side.items():
        active = sum(1 for u in units if u.status == UnitStatus.ACTIVE)
        destroyed = sum(1 for u in units if u.status == UnitStatus.DESTROYED)
        side_summaries[side] = {
            "total": len(units),
            "active": active,
            "destroyed": destroyed,
        }

    summary = {
        "scenario": config_dict.get("name", scenario_path.stem),
        "seed": seed,
        "ticks_executed": run_result.ticks_executed,
        "duration_s": run_result.duration_s,
        "victory": serialize_to_dict(run_result.victory_result),
        "sides": side_summaries,
    }

    return summary, recorder, ctx


# ---------------------------------------------------------------------------
# Tool implementations (sync, wrapped by async handlers)
# ---------------------------------------------------------------------------


def _tool_run_scenario(scenario_name: str, seed: int = 42, max_ticks: int = 1000) -> str:
    path = _find_scenario_path(scenario_name)
    if path is None:
        return make_error("ScenarioNotFound", f"Scenario '{scenario_name}' not found")

    try:
        summary, recorder, ctx = _run_single(path, seed, max_ticks)
    except Exception as e:
        return make_error("SimulationError", str(e))

    run_id = ResultStore.generate_id()
    stored = StoredResult(
        run_id=run_id,
        scenario_name=scenario_name,
        seed=seed,
        summary=summary,
        recorder_events=[serialize_to_dict(e) for e in recorder.events[:_MAX_STORED_EVENTS]],
        recorder_snapshots=[{"tick": s.tick} for s in recorder.snapshots],
    )
    _store.store(stored)
    summary["run_id"] = run_id
    return make_success(summary)


def _tool_query_state(run_id: str, tick: int | None = None, query_type: str = "summary") -> str:
    result = _store.get(run_id)
    if result is None:
        # Try latest
        if run_id == "latest":
            result = _store.latest()
        if result is None:
            return make_error("RunNotFound", f"Run '{run_id}' not found")

    if query_type == "summary":
        return make_success(result.summary)

    elif query_type == "units":
        sides = result.summary.get("sides", {})
        return make_success({"sides": sides})

    elif query_type == "events":
        events = result.recorder_events
        if tick is not None:
            events = [e for e in events if e.get("tick") == tick]
        return make_success({"events": events[:_MAX_QUERY_EVENTS]})

    elif query_type == "snapshots":
        return make_success({"snapshots": result.recorder_snapshots})

    return make_error("InvalidParameter", f"Unknown query_type: {query_type}")


def _tool_run_monte_carlo(
    scenario_name: str,
    num_iterations: int = 20,
    base_seed: int = 42,
    max_ticks: int = 100,
) -> str:
    path = _find_scenario_path(scenario_name)
    if path is None:
        return make_error("ScenarioNotFound", f"Scenario '{scenario_name}' not found")

    import numpy as np

    all_metrics: dict[str, list[float]] = {}

    for i in range(num_iterations):
        seed = base_seed + i
        try:
            summary, _, _ = _run_single(path, seed, max_ticks)
        except Exception as e:
            logger.warning("MC iteration %d failed: %s", i, e)
            continue

        # Extract numeric metrics from sides
        for side, data in summary.get("sides", {}).items():
            for key in ("destroyed", "active", "total"):
                metric_name = f"{side}_{key}"
                all_metrics.setdefault(metric_name, []).append(float(data.get(key, 0)))

    # Compute statistics
    stats: dict[str, Any] = {}
    for metric_name, values in all_metrics.items():
        arr = np.array(values)
        stats[metric_name] = {
            "mean": float(np.mean(arr)),
            "median": float(np.median(arr)),
            "std": float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0,
            "min": float(np.min(arr)),
            "max": float(np.max(arr)),
            "p5": float(np.percentile(arr, 5)),
            "p95": float(np.percentile(arr, 95)),
            "n": len(values),
        }

    run_id = ResultStore.generate_id()
    stored = StoredResult(
        run_id=run_id,
        scenario_name=scenario_name,
        seed=base_seed,
        summary={"type": "monte_carlo", "num_iterations": num_iterations, "metrics": stats},
    )
    _store.store(stored)

    return make_success({
        "run_id": run_id,
        "num_iterations": num_iterations,
        "metrics": stats,
    })


def _tool_compare_results(run_id_a: str, run_id_b: str) -> str:
    a = _store.get(run_id_a)
    b = _store.get(run_id_b)
    if a is None:
        return make_error("RunNotFound", f"Run '{run_id_a}' not found")
    if b is None:
        return make_error("RunNotFound", f"Run '{run_id_b}' not found")

    comparison: dict[str, Any] = {
        "run_a": {"run_id": a.run_id, "scenario": a.scenario_name, "seed": a.seed},
        "run_b": {"run_id": b.run_id, "scenario": b.scenario_name, "seed": b.seed},
        "differences": {},
    }

    # Compare side summaries
    sides_a = a.summary.get("sides", {})
    sides_b = b.summary.get("sides", {})
    for side in sorted(dict.fromkeys(list(sides_a) + list(sides_b))):
        sa = sides_a.get(side, {})
        sb = sides_b.get(side, {})
        diff: dict[str, Any] = {}
        for key in ("destroyed", "active", "total"):
            va = sa.get(key, 0)
            vb = sb.get(key, 0)
            diff[key] = {"a": va, "b": vb, "delta": vb - va}
        comparison["differences"][side] = diff

    return make_success(comparison)


def _tool_list_scenarios() -> str:
    scenarios = []
    if _SCENARIOS_DIR.exists():
        for d in sorted(_SCENARIOS_DIR.iterdir()):
            yaml_path = d / "scenario.yaml"
            if yaml_path.exists():
                import yaml
                try:
                    with open(yaml_path) as f:
                        cfg = yaml.safe_load(f)
                    scenarios.append({
                        "name": d.name,
                        "display_name": cfg.get("name", d.name),
                        "duration_hours": cfg.get("duration_hours", 0),
                        "sides": [s.get("side", "?") for s in cfg.get("sides", [])],
                    })
                except Exception:
                    scenarios.append({"name": d.name, "error": "failed to parse"})
    return make_success({"scenarios": scenarios})


def _tool_list_units(category: str | None = None, domain: str | None = None) -> str:
    import yaml

    units_dir = _DATA_DIR / "units"
    units = []
    if units_dir.exists():
        for yaml_file in sorted(units_dir.rglob("*.yaml")):
            try:
                with open(yaml_file) as f:
                    defn = yaml.safe_load(f)
                unit_domain = defn.get("domain", "")
                if domain and unit_domain != domain:
                    continue
                cat = yaml_file.parent.name if yaml_file.parent != units_dir else ""
                if category and cat != category:
                    continue
                units.append({
                    "unit_type": defn.get("unit_type", yaml_file.stem),
                    "display_name": defn.get("display_name", ""),
                    "domain": unit_domain,
                    "category": cat,
                    "max_speed": defn.get("max_speed", 0),
                    "crew_size": len(defn.get("crew", [])),
                })
            except Exception:
                pass
    return make_success({"units": units})


def _tool_modify_parameter(
    scenario_name: str,
    parameter_path: str,
    value: float,
    seed: int = 42,
    max_ticks: int = 1000,
) -> str:
    path = _find_scenario_path(scenario_name)
    if path is None:
        return make_error("ScenarioNotFound", f"Scenario '{scenario_name}' not found")

    import tempfile
    import yaml

    with open(path) as f:
        config = yaml.safe_load(f)

    # Run baseline
    try:
        baseline_summary, _, _ = _run_single(path, seed, max_ticks)
    except Exception as e:
        return make_error("SimulationError", f"Baseline failed: {e}")

    # Apply modification
    modified = dict(config)
    cal = dict(modified.get("calibration_overrides", {}))
    cal[parameter_path] = value
    modified["calibration_overrides"] = cal

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, dir=tempfile.gettempdir()
    ) as tmp:
        yaml.dump(modified, tmp, default_flow_style=False)
        tmp_path = Path(tmp.name)

    try:
        mod_summary, _, _ = _run_single(tmp_path, seed, max_ticks)
    except Exception as e:
        return make_error("SimulationError", f"Modified run failed: {e}")
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass

    return make_success({
        "baseline": baseline_summary,
        "modified": mod_summary,
        "parameter": parameter_path,
        "value": value,
    })


# ---------------------------------------------------------------------------
# MCP server setup
# ---------------------------------------------------------------------------


def _create_server() -> Any:
    """Create and configure the MCP server with all tools and resources."""
    from mcp.server.fastmcp import FastMCP
    from stochastic_warfare.tools.mcp_resources import register_resources

    mcp = FastMCP("stochastic-warfare")
    register_resources(mcp, _store)

    @mcp.tool()
    async def run_scenario(scenario_name: str, seed: int = 42, max_ticks: int = 1000) -> str:
        """Run a wargame scenario and return summary results.

        Args:
            scenario_name: Name of scenario directory (e.g., 'test_campaign', '73_easting')
            seed: PRNG seed for reproducibility
            max_ticks: Maximum simulation ticks
        """
        return await asyncio.to_thread(_tool_run_scenario, scenario_name, seed, max_ticks)

    @mcp.tool()
    async def query_state(run_id: str, tick: int | None = None, query_type: str = "summary") -> str:
        """Query a previous simulation run's state.

        Args:
            run_id: Run ID from a previous run_scenario call, or 'latest'
            tick: Optional tick number to filter events
            query_type: One of 'summary', 'units', 'events', 'snapshots'
        """
        return _tool_query_state(run_id, tick, query_type)

    @mcp.tool()
    async def run_monte_carlo(
        scenario_name: str,
        num_iterations: int = 20,
        base_seed: int = 42,
        max_ticks: int = 100,
    ) -> str:
        """Run Monte Carlo analysis of a scenario.

        Args:
            scenario_name: Name of scenario directory
            num_iterations: Number of iterations to run
            base_seed: Starting seed (each iteration uses base_seed + i)
            max_ticks: Maximum ticks per iteration
        """
        return await asyncio.to_thread(
            _tool_run_monte_carlo, scenario_name, num_iterations, base_seed, max_ticks
        )

    @mcp.tool()
    async def compare_results(run_id_a: str, run_id_b: str) -> str:
        """Compare two cached simulation runs side-by-side.

        Args:
            run_id_a: First run ID
            run_id_b: Second run ID
        """
        return _tool_compare_results(run_id_a, run_id_b)

    @mcp.tool()
    async def list_scenarios() -> str:
        """List all available scenarios with descriptions."""
        return _tool_list_scenarios()

    @mcp.tool()
    async def list_units(category: str | None = None, domain: str | None = None) -> str:
        """List available unit definitions.

        Args:
            category: Optional filter by unit category directory
            domain: Optional filter by domain (ground/aerial/naval/submarine)
        """
        return _tool_list_units(category, domain)

    @mcp.tool()
    async def modify_parameter(
        scenario_name: str,
        parameter_path: str,
        value: float,
        seed: int = 42,
        max_ticks: int = 1000,
    ) -> str:
        """Run baseline + modified scenario and compare results.

        Args:
            scenario_name: Name of scenario directory
            parameter_path: Calibration override key (e.g., 'hit_probability_modifier')
            value: New value for the parameter
            seed: PRNG seed for both runs
            max_ticks: Maximum ticks per run
        """
        return await asyncio.to_thread(
            _tool_modify_parameter, scenario_name, parameter_path, value, seed, max_ticks
        )

    return mcp


def main() -> None:
    """Entry point for the MCP server (stdio transport)."""
    mcp = _create_server()
    mcp.run()


if __name__ == "__main__":
    main()
