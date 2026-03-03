"""Performance profiling for campaign validation runs.

Wraps :class:`CampaignRunner` with ``cProfile`` and ``tracemalloc`` to
measure wall-clock time, realtime ratio, ticks per second, peak memory,
and top hotspots.
"""

from __future__ import annotations

import cProfile
import pstats
import time
import tracemalloc
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import Any

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.validation.campaign_data import HistoricalCampaign
from stochastic_warfare.validation.campaign_runner import CampaignRunner, CampaignRunResult

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


@dataclass
class PerformanceResult:
    """Performance profiling result for a campaign run."""

    wall_clock_s: float
    sim_duration_s: float
    realtime_ratio: float
    ticks_executed: int
    ticks_per_second: float
    peak_memory_mb: float
    hotspots: list[tuple[str, float, int]] = field(default_factory=list)
    """Top hotspots: (function_name, cumulative_time, call_count)."""


# ---------------------------------------------------------------------------
# Profiler
# ---------------------------------------------------------------------------


class PerformanceProfiler:
    """Profile campaign runs for performance analysis.

    Parameters
    ----------
    runner:
        Campaign runner to profile.
    """

    def __init__(self, runner: CampaignRunner) -> None:
        self._runner = runner

    def profile_campaign(
        self,
        campaign: HistoricalCampaign,
        seed: int = 42,
        top_n: int = 20,
    ) -> PerformanceResult:
        """Profile a campaign run and return performance metrics.

        Parameters
        ----------
        campaign:
            Campaign scenario to run.
        seed:
            PRNG seed for reproducibility.
        top_n:
            Number of top hotspots to include in results.

        Returns
        -------
        PerformanceResult
            Performance metrics including wall-clock time, realtime ratio,
            and cProfile hotspots.
        """
        # Start memory tracking
        tracemalloc.start()

        # Profile the run
        profiler = cProfile.Profile()

        t0 = time.perf_counter()
        profiler.enable()
        result = self._runner.run(campaign, seed=seed)
        profiler.disable()
        t1 = time.perf_counter()

        # Get memory peak
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        wall_clock = t1 - t0
        sim_duration = result.duration_simulated_s
        ticks = result.ticks_executed

        realtime_ratio = sim_duration / wall_clock if wall_clock > 0 else 0.0
        ticks_per_sec = ticks / wall_clock if wall_clock > 0 else 0.0
        peak_mb = peak_bytes / (1024 * 1024)

        # Extract hotspots
        hotspots = self._extract_hotspots(profiler, top_n)

        return PerformanceResult(
            wall_clock_s=wall_clock,
            sim_duration_s=sim_duration,
            realtime_ratio=realtime_ratio,
            ticks_executed=ticks,
            ticks_per_second=ticks_per_sec,
            peak_memory_mb=peak_mb,
            hotspots=hotspots,
        )

    @staticmethod
    def _extract_hotspots(
        profiler: cProfile.Profile,
        top_n: int,
    ) -> list[tuple[str, float, int]]:
        """Extract top N hotspots from cProfile stats."""
        stats = pstats.Stats(profiler, stream=StringIO())
        stats.sort_stats("cumulative")

        hotspots: list[tuple[str, float, int]] = []
        for (filename, lineno, name), (cc, nc, tt, ct, callers) in sorted(
            stats.stats.items(),
            key=lambda x: x[1][3],  # cumulative time
            reverse=True,
        )[:top_n]:
            func_name = f"{filename}:{lineno}({name})"
            hotspots.append((func_name, ct, nc))

        return hotspots

    @staticmethod
    def report(result: PerformanceResult) -> str:
        """Format a performance result as a human-readable report."""
        lines = [
            "Campaign Performance Report",
            "=" * 40,
            f"  Wall-clock time:   {result.wall_clock_s:.2f}s",
            f"  Simulated time:    {result.sim_duration_s:.0f}s ({result.sim_duration_s / 3600:.1f}h)",
            f"  Realtime ratio:    {result.realtime_ratio:.1f}x",
            f"  Ticks executed:    {result.ticks_executed}",
            f"  Ticks/second:      {result.ticks_per_second:.1f}",
            f"  Peak memory:       {result.peak_memory_mb:.1f} MB",
            "",
            "Top Hotspots:",
            "-" * 40,
        ]

        for func_name, cum_time, calls in result.hotspots[:10]:
            # Truncate long function names
            short_name = func_name
            if len(short_name) > 60:
                short_name = "..." + short_name[-57:]
            lines.append(f"  {cum_time:8.3f}s  {calls:8d}  {short_name}")

        return "\n".join(lines)
