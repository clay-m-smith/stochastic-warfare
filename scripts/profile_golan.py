"""Profile the Golan Heights 4-day campaign for hotspot analysis.

Outputs wall-clock time, ticks/second, top 20 hotspots, and peak memory.
Used to guide targeted optimization in future phases.

Usage::

    uv run python scripts/profile_golan.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

DATA_DIR = PROJECT_ROOT / "data"
GOLAN_YAML = DATA_DIR / "scenarios" / "golan_campaign" / "scenario.yaml"


def main() -> None:
    from stochastic_warfare.validation.campaign_data import CampaignDataLoader
    from stochastic_warfare.validation.campaign_runner import (
        CampaignRunner,
        CampaignRunnerConfig,
    )
    from stochastic_warfare.validation.performance import PerformanceProfiler

    if not GOLAN_YAML.exists():
        print(f"ERROR: Golan campaign YAML not found at {GOLAN_YAML}")
        sys.exit(1)

    print("Loading Golan Heights campaign...")
    campaign = CampaignDataLoader().load(GOLAN_YAML)

    runner = CampaignRunner(CampaignRunnerConfig(
        data_dir=str(DATA_DIR),
    ))

    profiler = PerformanceProfiler(runner)

    print("Profiling campaign (this may take several minutes)...")
    result = profiler.profile_campaign(campaign, seed=42, top_n=20)

    print()
    print(PerformanceProfiler.report(result))


if __name__ == "__main__":
    main()
