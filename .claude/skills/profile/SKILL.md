# Performance Profiling

Identify and analyze performance hotspots in the simulation. Produces actionable optimization recommendations with before/after measurement.

## Trigger
Run this analysis:
- When a scenario runs slower than expected
- Before and after performance optimization work
- At the start of integration-heavy phases (Phase 9, 10)
- When the user reports slow tests or scenario execution

## How to Profile

### Quick Profile (default)
Run the target scenario or test with cProfile and summarize the top 20 hotspots:

```bash
uv run python -m cProfile -s cumulative -m pytest tests/validation/test_golan_heights.py::TestGolanHeightsScenario::test_single_run -q 2>&1 | head -40
```

Or for a specific script:
```bash
uv run python -m cProfile -s cumulative scripts/smoke_all.py 2>&1 | head -40
```

### Targeted Profile
For a specific function or module, use line_profiler-style timing via manual instrumentation:

```python
import time
start = time.perf_counter()
# ... code block ...
elapsed = time.perf_counter() - start
print(f"Block took {elapsed:.3f}s")
```

### Benchmark Script
Run `scripts/benchmark.py` (if it exists) for standardized measurements:
```bash
uv run python scripts/benchmark.py
```

## Analysis Checklist

### 1. Identify Hot Functions
From the cProfile output, identify functions that:
- Consume >5% of total time
- Are called >10,000 times
- Have a high `tottime/ncalls` ratio (expensive per call)

### 2. Classify Each Hotspot

| Category | Description | Typical Fix |
|----------|-------------|-------------|
| **Algorithmic** | O(n²) or worse where O(n log n) is possible | Better data structure (KDTree, cache, index) |
| **Python overhead** | Per-call function overhead dominates | Vectorize with numpy, batch operations |
| **Allocation** | Object creation in inner loops | Pre-allocate, reuse, use arrays |
| **Redundant** | Same computation repeated unnecessarily | Cache results, hoist invariants |
| **I/O** | File or network operations in hot path | Lazy load, pre-cache |

### 3. Estimate Impact
For each hotspot, estimate:
- **Current cost**: % of total runtime
- **Theoretical speedup**: how much faster the optimized version could be
- **Implementation effort**: trivial / moderate / significant

### 4. Cross-Reference with Known Issues
Check `docs/devlog/` for previously identified performance items. Check `docs/development-phases.md` for deferred optimization tasks.

## Output Format

```
## Profile Summary

**Target**: [what was profiled]
**Total runtime**: [seconds]
**Test count**: [if applicable]

## Top Hotspots

| Rank | Function | File:Line | Calls | Total Time | % | Category |
|------|----------|-----------|-------|------------|---|----------|
| 1 | ... | ... | ... | ... | ... | ... |

## Recommendations

### Priority 1 (fix now)
...

### Priority 2 (fix during Phase N)
...

### Priority 3 (post-MVP)
...
```

## Benchmark Script Template

If `scripts/benchmark.py` doesn't exist, create it with this structure:

```python
"""Benchmark suite for scenario runner performance."""
import time
from stochastic_warfare.validation.scenario_runner import ScenarioRunner, ScenarioRunnerConfig
from stochastic_warfare.validation.historical_data import HistoricalDataLoader

def bench_scenario(name: str, seed: int = 42) -> float:
    loader = HistoricalDataLoader()
    engagement = loader.load(f"data/scenarios/{name}/scenario.yaml")
    runner = ScenarioRunner(ScenarioRunnerConfig())
    start = time.perf_counter()
    runner.run(engagement, seed=seed)
    return time.perf_counter() - start

if __name__ == "__main__":
    scenarios = ["73_easting", "falklands_naval", "golan_heights"]
    for name in scenarios:
        elapsed = bench_scenario(name)
        print(f"{name:20s}: {elapsed:.2f}s")
```

## Important Notes

- Always measure BEFORE and AFTER optimization — gut feelings about performance are often wrong
- Profile on the actual scenario (validation tests), not synthetic micro-benchmarks
- Small functions called millions of times matter more than large functions called once
- numpy vectorization typically gives 10-100x speedup over Python loops
- KDTree/spatial indexing gives O(log n) vs O(n) — most impactful for large unit counts
- On Windows, `ProcessPoolExecutor` has higher overhead than on Linux (spawn vs fork)
- Monte Carlo parallelization via `max_workers` config is already available
