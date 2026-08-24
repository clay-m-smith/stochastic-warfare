"""MCP server for Claude Code integration.

Provides 7 tools for running scenarios, querying results, Monte Carlo
analysis, and parameter comparison — all via stdio transport.

Requires ``mcp[cli]>=1.2.0`` (install via ``uv sync --extra mcp``).
"""

from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from pydantic import BeforeValidator, Field, StrictInt

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.application_paths import ApplicationPaths
from stochastic_warfare.scenario_names import validate_scenario_name
from stochastic_warfare.simulation.calibration import CalibrationSchema
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


@lru_cache(maxsize=1)
def _application_paths() -> ApplicationPaths:
    """Resolve the exact MCP resource owner once per server process."""
    return ApplicationPaths.discover()


def _strict_finite_float(value: Any) -> float:
    """Reject transport coercion before a production helper is invoked."""
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
    ):
        raise ValueError("value must be a strict finite float")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError("value must be a strict finite float") from exc
    if not math.isfinite(number):
        raise ValueError("value must be a strict finite float")
    return number


NonNegativeStrictInt = Annotated[StrictInt, Field(ge=0)]
PositiveStrictInt = Annotated[StrictInt, Field(ge=1)]
StrictFiniteFloat = Annotated[
    float,
    BeforeValidator(_strict_finite_float),
]
ScenarioName = Annotated[
    str,
    BeforeValidator(validate_scenario_name),
]


def _validated_calibration_patch(
    value: dict[str, Any] | None,
) -> CalibrationSchema:
    """Cross the strict runtime-owned calibration boundary before dispatch."""
    from stochastic_warfare.simulation.runtime import AnalysisVariant

    return AnalysisVariant(
        variant_id="mcp-transport-validation",
        calibration_patch=value or {},
    ).calibration_patch


_MCP_TOP_LEVEL_SCALAR_CALIBRATION_FIELDS = frozenset(
    {
        "altitude_sickness_rate",
        "altitude_sickness_threshold_m",
        "c2_min_effectiveness",
        "cbrn_arrhenius_ea",
        "cbrn_inversion_multiplier",
        "cbrn_uv_degradation_rate",
        "cbrn_washout_coefficient",
        "cloud_ceiling_min_attack_m",
        "cold_casualty_base_rate",
        "degraded_equipment_threshold",
        "destruction_threshold",
        "dew_disable_threshold",
        "disable_threshold",
        "drone_provocation_prob",
        "engagement_concealment_threshold",
        "fire_damage_per_tick",
        "formation_spacing_m",
        "gas_casualty_floor",
        "gas_protection_scaling",
        "guerrilla_disengage_threshold",
        "heat_casualty_base_rate",
        "hit_probability_modifier",
        "human_shield_pk_reduction",
        "iads_degradation_rate",
        "icing_maneuver_penalty",
        "icing_power_penalty",
        "icing_radar_penalty_db",
        "jammer_coverage_mult",
        "misinterpretation_radius_m",
        "morale_degrade_rate_modifier",
        "mopp_comms_factor_4",
        "mopp_fov_reduction_4",
        "mopp_reload_factor_4",
        "night_thermal_floor",
        "observation_decay_rate",
        "order_misinterpretation_base",
        "order_propagation_delay_sigma",
        "planning_available_time_s",
        "rain_attenuation_factor",
        "retreat_distance_m",
        "rout_cascade_base_chance",
        "rout_cascade_radius_m",
        "rout_cascade_shaken_susceptibility",
        "sam_suppression_modifier",
        "sead_arm_effectiveness",
        "sead_effectiveness",
        "sigint_detection_bonus",
        "stealth_detection_penalty",
        "stratagem_concentration_bonus",
        "stratagem_deception_bonus",
        "target_size_modifier",
        "thermal_contrast",
        "visibility_m",
        "wave_interval_s",
        "wind_accuracy_penalty_scale",
        "wind_bvr_missile_speed_mps",
    },
)
_MCP_MORALE_SCALAR_CALIBRATION_FIELDS = frozenset(
    {
        "base_degrade_rate",
        "base_recover_rate",
        "casualty_weight",
        "cohesion_weight",
        "degrade_rate_modifier",
        "force_ratio_weight",
        "leadership_weight",
        "suppression_weight",
        "transition_cooldown_s",
    },
)


def _mcp_scalar_calibration_patch(
    parameter_path: str,
    value: float,
) -> dict[str, Any]:
    """Resolve one explicitly supported scalar path without generic traversal."""
    if (
        not isinstance(parameter_path, str)
        or not parameter_path
        or parameter_path != parameter_path.strip()
    ):
        raise ValueError(
            "parameter_path must be a non-empty trimmed calibration path",
        )
    if parameter_path in _MCP_TOP_LEVEL_SCALAR_CALIBRATION_FIELDS:
        patch: dict[str, Any] = {parameter_path: value}
    elif parameter_path.startswith("morale."):
        nested_field = parameter_path.removeprefix("morale.")
        if nested_field not in _MCP_MORALE_SCALAR_CALIBRATION_FIELDS:
            raise ValueError(
                f"unsupported scalar calibration path: {parameter_path!r}",
            )
        patch = {"morale": {nested_field: value}}
    else:
        raise ValueError(
            f"unsupported scalar calibration path: {parameter_path!r}",
        )
    _validated_calibration_patch(patch)
    return patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_scenario_path(name: str) -> Path | None:
    """Find scenario YAML by name."""
    try:
        name = validate_scenario_name(name)
    except ValueError:
        return None
    candidate = _application_paths().scenario_root / name / "scenario.yaml"
    if candidate.exists():
        return candidate
    return None


def _run_single(
    scenario_path: Path,
    seed: int,
    max_ticks: int,
    calibration_patch: CalibrationSchema | dict[str, Any] | None = None,
) -> tuple[dict[str, Any], Any, Any]:
    """Run a single scenario synchronously. Returns (summary, recorder, ctx)."""
    from stochastic_warfare.simulation.runtime import (
        AnalysisVariant,
        SimulationRuntimeFactory,
    )

    variant = AnalysisVariant(
        variant_id="mcp",
        calibration_patch=calibration_patch or {},
    )
    prepared = SimulationRuntimeFactory().prepare(
        scenario_path,
        _application_paths().catalog_root,
        (variant,),
    )
    return _run_prepared(
        prepared,
        variant.variant_id,
        seed=seed,
        max_ticks=max_ticks,
    )


def _run_prepared(
    prepared: Any,
    variant_id: str,
    *,
    seed: int,
    max_ticks: int,
) -> tuple[dict[str, Any], Any, Any]:
    """Execute one already prepared MCP variant with event recording."""
    from stochastic_warfare.entities.base import UnitStatus

    session = prepared.build(
        variant_id,
        seed=seed,
        max_ticks=max_ticks,
        record_events=True,
    )
    ctx = session.context
    run_result = session.run_to_completion()
    recorder = session.recorder
    if recorder is None:
        raise RuntimeError("MCP runtime did not create its recorder")

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
        "scenario": prepared.source_config.name,
        "scenario_path": str(prepared.scenario_path),
        "seed": seed,
        "max_ticks": max_ticks,
        "ticks_executed": run_result.ticks_executed,
        "duration_s": run_result.duration_s,
        "victory": serialize_to_dict(run_result.victory_result),
        "sides": side_summaries,
        "source_fingerprint": prepared.source_fingerprint,
        "config_fingerprint": session.config_fingerprint,
        "data_root": str(prepared.data_root),
        "authored_roster": prepared.authored_roster,
        "loaded_roster": session.loaded_roster,
        "provenance": serialize_to_dict(session.provenance()),
    }

    return summary, recorder, ctx


# ---------------------------------------------------------------------------
# Tool implementations (sync, wrapped by async handlers)
# ---------------------------------------------------------------------------


def _tool_run_scenario(
    scenario_name: str,
    seed: int = 42,
    max_ticks: int = 1000,
    calibration_patch: CalibrationSchema | dict[str, Any] | None = None,
) -> str:
    path = _find_scenario_path(scenario_name)
    if path is None:
        return make_error("ScenarioNotFound", f"Scenario '{scenario_name}' not found")

    try:
        summary, recorder, ctx = _run_single(
            path,
            seed,
            max_ticks,
            calibration_patch,
        )
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
    calibration_patch: CalibrationSchema | dict[str, Any] | None = None,
) -> str:
    path = _find_scenario_path(scenario_name)
    if path is None:
        return make_error("ScenarioNotFound", f"Scenario '{scenario_name}' not found")

    from stochastic_warfare.simulation.runtime import (
        AnalysisVariant,
        SimulationRuntimeFactory,
    )
    from stochastic_warfare.tools._run_helpers import AnalysisRunner

    try:
        variant = AnalysisVariant(
            variant_id="mcp-monte-carlo",
            calibration_patch=calibration_patch or {},
        )
        prepared = SimulationRuntimeFactory().prepare(
            path,
            _application_paths().catalog_root,
            (variant,),
        )
        runner = AnalysisRunner(
            prepared,
            [
                metric
                for side in prepared.side_ids
                for metric in (
                    f"{side}_active",
                    f"{side}_destroyed",
                )
            ],
        )
        batch = runner.run_variant(
            variant.variant_id,
            num_iterations=num_iterations,
            base_seed=base_seed,
            max_ticks=max_ticks,
        )
    except Exception as exc:
        return make_error("SimulationError", str(exc))
    all_metrics = batch.metrics_dict()
    stats = batch.statistics_dict()

    run_id = ResultStore.generate_id()
    stored = StoredResult(
        run_id=run_id,
        scenario_name=scenario_name,
        seed=base_seed,
        summary={
            "type": "monte_carlo",
            "scenario_path": str(prepared.scenario_path),
            "num_iterations": num_iterations,
            "base_seed": base_seed,
            "max_ticks": max_ticks,
            "seeds": batch.seeds,
            "metrics": stats,
            "raw_metrics": all_metrics,
            "source_fingerprint": prepared.source_fingerprint,
            "config_fingerprint": batch.config_fingerprint,
            "authored_roster": batch.authored_roster,
            "loaded_roster": batch.loaded_roster,
            "provenance": batch.provenance_dict(),
        },
    )
    _store.store(stored)

    return make_success(
        {
            "run_id": run_id,
            "scenario_path": str(prepared.scenario_path),
            "num_iterations": num_iterations,
            "base_seed": base_seed,
            "max_ticks": max_ticks,
            "seeds": batch.seeds,
            "metrics": stats,
            "raw_metrics": all_metrics,
            "source_fingerprint": prepared.source_fingerprint,
            "config_fingerprint": batch.config_fingerprint,
            "authored_roster": batch.authored_roster,
            "loaded_roster": batch.loaded_roster,
            "provenance": batch.provenance_dict(),
        }
    )


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
    scenarios_dir = _application_paths().scenario_root
    if scenarios_dir.exists():
        for d in sorted(scenarios_dir.iterdir()):
            yaml_path = d / "scenario.yaml"
            if yaml_path.exists():
                import yaml

                try:
                    with open(yaml_path) as f:
                        cfg = yaml.safe_load(f)
                    scenarios.append(
                        {
                            "name": d.name,
                            "display_name": cfg.get("name", d.name),
                            "duration_hours": cfg.get("duration_hours", 0),
                            "sides": [s.get("side", "?") for s in cfg.get("sides", [])],
                        }
                    )
                except Exception:
                    scenarios.append({"name": d.name, "error": "failed to parse"})
    return make_success({"scenarios": scenarios})


def _tool_list_units(category: str | None = None, domain: str | None = None) -> str:
    import yaml

    units_dir = _application_paths().catalog_root / "units"
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
                units.append(
                    {
                        "unit_type": defn.get("unit_type", yaml_file.stem),
                        "display_name": defn.get("display_name", ""),
                        "domain": unit_domain,
                        "category": cat,
                        "max_speed": defn.get("max_speed", 0),
                        "crew_size": len(defn.get("crew", [])),
                    }
                )
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

    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        return make_error(
            "InvalidParameter",
            "value must be a finite integer or float",
        )
    value = float(value)
    from stochastic_warfare.simulation.runtime import (
        AnalysisVariant,
        SimulationRuntimeFactory,
    )

    try:
        calibration_patch = _mcp_scalar_calibration_patch(
            parameter_path,
            value,
        )
        variants = (
            AnalysisVariant(variant_id="baseline"),
            AnalysisVariant(
                variant_id="modified",
                calibration_patch=calibration_patch,
            ),
        )
        prepared = SimulationRuntimeFactory().prepare(
            path,
            _application_paths().catalog_root,
            variants,
        )
        baseline_summary, _, _ = _run_prepared(
            prepared,
            "baseline",
            seed=seed,
            max_ticks=max_ticks,
        )
        mod_summary, _, _ = _run_prepared(
            prepared,
            "modified",
            seed=seed,
            max_ticks=max_ticks,
        )
    except Exception as e:
        return make_error("SimulationError", str(e))

    return make_success(
        {
            "baseline": baseline_summary,
            "modified": mod_summary,
            "parameter": parameter_path,
            "value": value,
        }
    )


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
    async def run_scenario(
        scenario_name: ScenarioName,
        seed: NonNegativeStrictInt = 42,
        max_ticks: PositiveStrictInt = 1000,
        calibration_patch: dict[str, Any] | None = None,
    ) -> str:
        """Run a wargame scenario and return summary results.

        Args:
            scenario_name: Name of scenario directory (e.g., 'test_campaign', '73_easting')
            seed: PRNG seed for reproducibility
            max_ticks: Maximum simulation ticks
            calibration_patch: Strict sparse calibration overlay
        """
        strict_patch = _validated_calibration_patch(
            calibration_patch,
        )
        # The stdio server owns one deterministic request sequence.  Keep the
        # simulation and its process-local result-store publication in that
        # request instead of detaching it onto an unowned executor thread.
        return _tool_run_scenario(
            scenario_name,
            seed,
            max_ticks,
            strict_patch,
        )

    @mcp.tool()
    async def query_state(
        run_id: str,
        tick: NonNegativeStrictInt | None = None,
        query_type: str = "summary",
    ) -> str:
        """Query a previous simulation run's state.

        Args:
            run_id: Run ID from a previous run_scenario call, or 'latest'
            tick: Optional tick number to filter events
            query_type: One of 'summary', 'units', 'events', 'snapshots'
        """
        return _tool_query_state(run_id, tick, query_type)

    @mcp.tool()
    async def run_monte_carlo(
        scenario_name: ScenarioName,
        num_iterations: PositiveStrictInt = 20,
        base_seed: NonNegativeStrictInt = 42,
        max_ticks: PositiveStrictInt = 100,
        calibration_patch: dict[str, Any] | None = None,
    ) -> str:
        """Run Monte Carlo analysis of a scenario.

        Args:
            scenario_name: Name of scenario directory
            num_iterations: Number of iterations to run
            base_seed: Starting seed (each iteration uses base_seed + i)
            max_ticks: Maximum ticks per iteration
            calibration_patch: Strict sparse calibration overlay
        """
        strict_patch = _validated_calibration_patch(
            calibration_patch,
        )
        return _tool_run_monte_carlo(
            scenario_name,
            num_iterations,
            base_seed,
            max_ticks,
            strict_patch,
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
        scenario_name: ScenarioName,
        parameter_path: str,
        value: StrictFiniteFloat,
        seed: NonNegativeStrictInt = 42,
        max_ticks: PositiveStrictInt = 1000,
    ) -> str:
        """Run baseline + modified scenario and compare results.

        Args:
            scenario_name: Name of scenario directory
            parameter_path: Declared scalar calibration path, including
                supported nested paths such as 'morale.base_degrade_rate'
            value: New value for the parameter
            seed: PRNG seed for both runs
            max_ticks: Maximum ticks per run
        """
        _mcp_scalar_calibration_patch(parameter_path, value)
        return _tool_modify_parameter(
            scenario_name,
            parameter_path,
            value,
            seed,
            max_ticks,
        )

    return mcp


def main() -> None:
    """Entry point for the MCP server (stdio transport)."""
    mcp = _create_server()
    mcp.run()


if __name__ == "__main__":
    main()
