---
name: profile
description: Measure and explain performance in the production simulation path with reproducible before-and-after evidence. Use when a scenario or test is slow, a performance regression is suspected, an optimization is planned, or a phase changes performance-sensitive loops, allocation, spatial queries, or parallel execution.
---

# Profile Performance

Profile the requested production target and provide measured recommendations.
Treat profiling as read-only diagnostics unless the user has also authorized an
optimization. Do not create a new benchmark script or add instrumentation to
production code merely because no convenient benchmark exists.

## Define a Reproducible Baseline

Record:

- production scenario, test, or entry point;
- phase-start revision and working tree state;
- Python and dependency environment;
- operating system and relevant hardware;
- seed, scenario data revision, engine configuration, and enabled features;
- warm-up policy, repetitions, and summary statistic.

Use the same environment, seed set, configuration, and workload before and
after a change. A single wall-clock observation is not a reliable regression
measurement.

## Choose a Production Target

Prefer the narrowest existing benchmark that exercises the affected production
path:

- `scripts/evaluate_scenarios.py --scenario <scenario-id>`;
- `tests/benchmarks/benchmark_suite.py`;
- `tests/benchmarks/test_benchmarks.py`;
- `tests/performance/test_battle_perf.py`;
- `tests/validation/test_campaign_performance.py`.

Check markers and run excluded `slow` or `benchmark` tests explicitly as
documented in `CODEX.md`.

Do not use the archived `scripts/archive/smoke_all.py`. Do not substitute the
simplified `ScenarioRunner` when the performance claim concerns
`SimulationEngine`, API execution, or another production path.

## Capture a Call Profile

For a production scenario on this Windows workspace, write profiling output
outside the repository:

```powershell
uv run python -m cProfile -o C:\tmp\stochastic-warfare-profile.prof scripts/evaluate_scenarios.py --scenario <scenario-id> --no-details --seed <seed>
uv run python -c "import pstats; pstats.Stats(r'C:\tmp\stochastic-warfare-profile.prof').strip_dirs().sort_stats('cumulative').print_stats(20)"
```

For tests, select an existing valid node and profile it without truncating or
hiding command failures. Confirm the node exists before running it.

Keep any manual timing harness in a temporary file outside the repository.
Never leave `time.perf_counter()` instrumentation or `print()` calls in
simulation-core source.

## Analyze

For each material hotspot, report:

- function and file;
- call count, total time, cumulative time, and percentage of measured runtime;
- whether cost is algorithmic, Python overhead, allocation, redundant work,
  I/O, synchronization, or measurement noise;
- evidence that the function is on the affected production path;
- estimated upper bound and implementation risk.

Treat vectorization, caching, spatial indexing, batching, pre-sorting, and
parallelism as hypotheses. They can change ordering, stochastic consumption,
memory behavior, or results and require measurement plus correctness evidence.

## Compare Before and After

1. Repeat the same benchmark enough times to characterize noise.
2. Compare a robust statistic and dispersion, not only the best run.
3. Run focused correctness tests.
4. Compare ordered events, final state, and outcomes for deterministic work.
5. Run `$audit-determinism` if ordering, RNG use, caching, or parallelism
   changed.
6. Run scenario or Monte Carlo comparisons when stochastic outcomes can change.
7. Run relevant slow and benchmark suites explicitly.

Do not weaken a predeclared performance threshold after it fails without the
owner's approval and a documented rationale.

## Report

Provide:

- target and reproducibility context;
- exact commands and repetitions;
- before/after timing table with dispersion;
- top measured hotspots;
- prioritized recommendations with expected benefit and risk;
- correctness and determinism checks;
- exclusions and residual uncertainty.

Do not claim an optimization succeeded from code shape, a synthetic
microbenchmark, or one faster observation.
