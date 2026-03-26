"""Phase 83: Structured benchmark suite with baseline tracking and regression detection.

Provides ``BenchmarkResult``, ``BenchmarkBaseline``, and ``run_benchmark()`` for
reproducible scenario performance measurement. Used by ``test_benchmarks.py`` and
the CI workflow for regression detection.
"""

from __future__ import annotations

import cProfile
import json
import os
import pstats
import subprocess
import time
import tracemalloc
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

import pytest


DATA_DIR = Path(__file__).resolve().parents[2] / "data"
SCENARIOS_DIR = DATA_DIR / "scenarios"


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BenchmarkResult:
    """Structured result from a single benchmark run."""

    scenario_name: str
    unit_count: int
    wall_clock_s: float
    ticks_executed: int
    ticks_per_second: float
    peak_memory_mb: float
    hotspots: list[tuple[str, float, int]] = field(default_factory=list)
    seed: int = 42
    winner: str | None = None
    commit: str = "unknown"


@dataclass(frozen=True)
class BaselineEntry:
    """Stored baseline for regression comparison."""

    wall_clock_s: float
    ticks_executed: int
    peak_memory_mb: float
    commit: str
    timestamp: str


# ---------------------------------------------------------------------------
# Baseline management
# ---------------------------------------------------------------------------


class BenchmarkBaseline:
    """Load, save, and compare benchmark baselines from a JSON file."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (Path(__file__).parent / "baselines.json")

    def load(self) -> dict[str, BaselineEntry]:
        """Read baselines from JSON, skipping ``_meta`` keys."""
        if not self._path.exists():
            return {}
        with open(self._path) as f:
            raw = json.load(f)
        entries: dict[str, BaselineEntry] = {}
        for key, val in raw.items():
            if key.startswith("_"):
                continue
            entries[key] = BaselineEntry(
                wall_clock_s=val["wall_clock_s"],
                ticks_executed=val["ticks_executed"],
                peak_memory_mb=val["peak_memory_mb"],
                commit=val.get("commit", "unknown"),
                timestamp=val.get("timestamp", ""),
            )
        return entries

    def save(self, baselines: dict[str, BaselineEntry]) -> None:
        """Write baselines to JSON with indent=2."""
        data: dict[str, object] = {
            "_meta": {
                "format_version": 1,
                "description": "Performance benchmark baselines for regression detection.",
            },
        }
        for name, entry in sorted(baselines.items()):
            data[name] = {
                "wall_clock_s": entry.wall_clock_s,
                "ticks_executed": entry.ticks_executed,
                "peak_memory_mb": entry.peak_memory_mb,
                "commit": entry.commit,
                "timestamp": entry.timestamp,
            }
        with open(self._path, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")

    def update(self, scenario_name: str, result: BenchmarkResult) -> None:
        """Upsert a baseline entry from a benchmark result."""
        baselines = self.load()
        baselines[scenario_name] = BaselineEntry(
            wall_clock_s=result.wall_clock_s,
            ticks_executed=result.ticks_executed,
            peak_memory_mb=result.peak_memory_mb,
            commit=result.commit,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self.save(baselines)

    def check_regression(
        self,
        scenario_name: str,
        result: BenchmarkResult,
        margin: float = 0.2,
    ) -> tuple[bool, str]:
        """Check if result regressed beyond margin vs baseline.

        Returns
        -------
        (is_regression, message)
            ``True`` if ``result.wall_clock_s > baseline * (1 + margin)``.
        """
        baselines = self.load()
        if scenario_name not in baselines:
            return False, f"No baseline for {scenario_name} — skipping regression check"
        baseline = baselines[scenario_name]
        threshold = baseline.wall_clock_s * (1 + margin)
        if result.wall_clock_s > threshold:
            return True, (
                f"REGRESSION: {scenario_name} took {result.wall_clock_s:.2f}s "
                f"(baseline {baseline.wall_clock_s:.2f}s, threshold {threshold:.2f}s, "
                f"+{((result.wall_clock_s / baseline.wall_clock_s) - 1) * 100:.1f}%)"
            )
        return False, (
            f"OK: {scenario_name} took {result.wall_clock_s:.2f}s "
            f"(baseline {baseline.wall_clock_s:.2f}s, margin {margin * 100:.0f}%)"
        )


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------


def _get_commit_hash() -> str:
    """Get short commit hash, falling back to $GITHUB_SHA or 'unknown'."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    sha = os.environ.get("GITHUB_SHA", "")
    return sha[:7] if sha else "unknown"


def _extract_hotspots(
    profiler: cProfile.Profile,
    top_n: int,
) -> list[tuple[str, float, int]]:
    """Extract top N hotspots from cProfile stats by cumulative time."""
    stats = pstats.Stats(profiler, stream=StringIO())
    stats.sort_stats("cumulative")

    hotspots: list[tuple[str, float, int]] = []
    for (filename, lineno, name), (_cc, nc, _tt, ct, _callers) in sorted(
        stats.stats.items(),
        key=lambda x: x[1][3],  # cumulative time
        reverse=True,
    )[:top_n]:
        func_name = f"{filename}:{lineno}({name})"
        hotspots.append((func_name, ct, nc))

    return hotspots


def run_benchmark(
    scenario_path: Path,
    seed: int = 42,
    profile: bool = True,
    top_n_hotspots: int = 20,
    calibration_overrides: dict[str, object] | None = None,
) -> BenchmarkResult:
    """Run a scenario benchmark with optional profiling.

    Parameters
    ----------
    scenario_path:
        Path to scenario.yaml file.
    seed:
        PRNG seed for deterministic runs.
    profile:
        If True, wrap with cProfile + tracemalloc (adds ~30-50% overhead).
        If False, use only wall clock (faster, for regression-only checks).
    top_n_hotspots:
        Number of hotspots to extract from cProfile stats.
    calibration_overrides:
        Optional dict of CalibrationSchema fields to override after loading.
        Used by flag impact tests to toggle individual performance flags.

    Returns
    -------
    BenchmarkResult
        Structured benchmark result with timing, memory, and hotspot data.
    """
    from stochastic_warfare.core.types import Position
    from stochastic_warfare.entities.base import UnitStatus
    from stochastic_warfare.simulation.calibration import CalibrationSchema
    from stochastic_warfare.simulation.engine import EngineConfig, SimulationEngine
    from stochastic_warfare.simulation.recorder import SimulationRecorder
    from stochastic_warfare.simulation.scenario import ScenarioLoader
    from stochastic_warfare.simulation.victory import VictoryEvaluator

    if not scenario_path.exists():
        pytest.skip(f"Scenario not found at {scenario_path}")

    # Load scenario
    loader = ScenarioLoader(DATA_DIR)
    ctx = loader.load(scenario_path, seed=seed)

    # Apply calibration overrides if provided (Phase 90 — flag impact tests)
    if calibration_overrides:
        existing = (
            ctx.calibration.model_dump()
            if isinstance(ctx.calibration, CalibrationSchema)
            else dict(ctx.calibration)
        )
        merged = {**existing, **calibration_overrides}
        ctx.calibration = CalibrationSchema(
            **{k: v for k, v in merged.items() if k in CalibrationSchema.model_fields}
        )
        side_names = list(ctx.units_by_side.keys())
        ctx.cal_flat = ctx.calibration.to_flat_dict(side_names)

    recorder = SimulationRecorder(ctx.event_bus)

    # Build victory evaluator
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

    # Count units
    unit_count = sum(len(u) for u in ctx.units_by_side.values())

    # Commit hash
    commit = _get_commit_hash()

    # Run with or without profiling
    hotspots: list[tuple[str, float, int]] = []
    peak_memory_mb = 0.0

    if profile:
        tracemalloc.start()
        profiler = cProfile.Profile()
        t0 = time.perf_counter()
        profiler.enable()
        run_result = engine.run()
        profiler.disable()
        elapsed = time.perf_counter() - t0
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_memory_mb = peak_bytes / (1024 * 1024)
        hotspots = _extract_hotspots(profiler, top_n_hotspots)
    else:
        t0 = time.perf_counter()
        run_result = engine.run()
        elapsed = time.perf_counter() - t0

    # Extract winner
    winner = None
    if run_result.victory_result:
        winner = run_result.victory_result.winning_side

    ticks = run_result.ticks_executed
    ticks_per_sec = ticks / elapsed if elapsed > 0 else 0.0

    scenario_name = scenario_path.parent.name

    return BenchmarkResult(
        scenario_name=scenario_name,
        unit_count=unit_count,
        wall_clock_s=elapsed,
        ticks_executed=ticks,
        ticks_per_second=ticks_per_sec,
        peak_memory_mb=peak_memory_mb,
        hotspots=hotspots,
        seed=seed,
        winner=winner,
        commit=commit,
    )
