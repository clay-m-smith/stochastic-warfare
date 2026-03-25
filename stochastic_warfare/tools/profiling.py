"""Phase 83: Profiling tooling — hotspot reports, profile comparison, flame graphs.

Provides structured output from benchmark results for analysis and optimization
guidance. Used by the ``/profile`` skill and benchmark CI.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tests.benchmarks.benchmark_suite import BenchmarkResult


def generate_hotspot_report(result: BenchmarkResult, top_n: int = 20) -> str:
    """Format a BenchmarkResult as a human-readable hotspot report.

    Parameters
    ----------
    result:
        Benchmark result containing hotspot data.
    top_n:
        Number of top hotspots to include.

    Returns
    -------
    str
        Formatted report with header and hotspot table.
    """
    lines = [
        f"Benchmark Report: {result.scenario_name}",
        "=" * 60,
        f"  Wall clock:    {result.wall_clock_s:.2f}s",
        f"  Ticks:         {result.ticks_executed}",
        f"  Ticks/second:  {result.ticks_per_second:.1f}",
        f"  Peak memory:   {result.peak_memory_mb:.1f} MB",
        f"  Unit count:    {result.unit_count}",
        f"  Seed:          {result.seed}",
        f"  Winner:        {result.winner or 'N/A'}",
        f"  Commit:        {result.commit}",
        "",
    ]

    if result.hotspots:
        total_time = result.wall_clock_s if result.wall_clock_s > 0 else 1.0
        lines.append("Top Hotspots:")
        lines.append(f"{'Rank':>4}  {'Cumulative':>10}  {'%':>6}  {'Calls':>10}  Function")
        lines.append("-" * 80)
        for i, (func_name, cum_time, call_count) in enumerate(result.hotspots[:top_n], 1):
            pct = (cum_time / total_time) * 100
            short_name = func_name if len(func_name) <= 50 else "..." + func_name[-47:]
            lines.append(f"{i:>4}  {cum_time:>10.3f}s  {pct:>5.1f}%  {call_count:>10}  {short_name}")
    else:
        lines.append("(No hotspot data — run with profile=True)")

    return "\n".join(lines)


def compare_profiles(before: BenchmarkResult, after: BenchmarkResult) -> str:
    """Generate a side-by-side comparison of two benchmark results.

    Parameters
    ----------
    before:
        Baseline benchmark result.
    after:
        New benchmark result to compare.

    Returns
    -------
    str
        Formatted comparison table with deltas and indicators.
    """
    lines = [
        f"Profile Comparison: {before.scenario_name} vs {after.scenario_name}",
        "=" * 70,
        f"{'Metric':<20}  {'Before':>12}  {'After':>12}  {'Delta':>12}  {'Change':>8}",
        "-" * 70,
    ]

    metrics = [
        ("wall_clock_s", "Wall clock (s)", False),    # lower is better
        ("ticks_executed", "Ticks", None),             # neutral
        ("ticks_per_second", "Ticks/second", True),    # higher is better
        ("peak_memory_mb", "Peak memory (MB)", False),  # lower is better
    ]

    for attr, label, higher_is_better in metrics:
        val_before = getattr(before, attr)
        val_after = getattr(after, attr)
        delta = val_after - val_before
        pct = ((val_after / val_before) - 1) * 100 if val_before != 0 else 0.0

        if higher_is_better is None:
            indicator = ""
        elif higher_is_better:
            indicator = "FASTER" if delta > 0 else ("SLOWER" if delta < 0 else "")
        else:
            indicator = "FASTER" if delta < 0 else ("SLOWER" if delta > 0 else "")

        if isinstance(val_before, int):
            lines.append(f"{label:<20}  {val_before:>12}  {val_after:>12}  {delta:>+12}  {indicator:>8}")
        else:
            lines.append(f"{label:<20}  {val_before:>12.2f}  {val_after:>12.2f}  {delta:>+12.2f}  {indicator:>8}")

    return "\n".join(lines)


def save_flame_graph(
    scenario_path: Path,
    output_path: Path,
    seed: int = 42,
    duration_s: int = 30,
) -> Path | None:
    """Generate a flame graph SVG via py-spy.

    Parameters
    ----------
    scenario_path:
        Path to scenario.yaml to benchmark.
    output_path:
        Path for the output SVG file.
    seed:
        PRNG seed.
    duration_s:
        Maximum recording duration in seconds.

    Returns
    -------
    Path | None
        The output path on success, or None if py-spy is not available.
    """
    if shutil.which("py-spy") is None:
        return None

    # Write a temporary script that runs the benchmark
    script_content = f"""\
import sys
sys.path.insert(0, r"{Path(__file__).resolve().parents[2]}")
from pathlib import Path
from tests.benchmarks.benchmark_suite import run_benchmark
run_benchmark(Path(r"{scenario_path}"), seed={seed}, profile=False)
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp:
        tmp.write(script_content)
        tmp_path = tmp.name

    try:
        subprocess.run(
            [
                "py-spy",
                "record",
                "-o",
                str(output_path),
                "--duration",
                str(duration_s),
                "--",
                sys.executable,
                tmp_path,
            ],
            timeout=duration_s + 30,
            check=True,
        )
        return output_path
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None
    finally:
        Path(tmp_path).unlink(missing_ok=True)
