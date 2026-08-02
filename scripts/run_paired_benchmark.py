#!/usr/bin/env python
"""Run the strict version-4 gate or workload-transition benchmark harness."""

from __future__ import annotations

from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tests.benchmarks.benchmark_suite import main


if __name__ == "__main__":
    arguments = sys.argv[1:]
    command = arguments if arguments[:1] in (["transition"], ["verify-final"]) else ["compare", *arguments]
    raise SystemExit(main(command))
