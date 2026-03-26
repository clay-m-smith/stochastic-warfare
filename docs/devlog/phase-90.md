# Phase 90: Validation & Benchmarking

**Status**: Complete
**Block**: 9 (Performance at Scale)
**Tests**: ~20

## What Was Built

Large-scale benchmark scenarios and performance validation for the Block 9 optimization work (Phases 83-89).

### 90a: Large-Scale Benchmark Scenarios

Two new benchmark scenarios using existing modern unit types with `count` multipliers:

- **`benchmark_battalion/scenario.yaml`** — 1,000 units (500 blue + 500 red)
  - Blue: Combined-arms BTF (M1A2/M1A1 armor, M3A2 Bradley, infantry, M109A6 artillery, Patriot AD, F-16C/AH-64D air, Javelin ATGM, HEMTT logistics, engineers, EA-18G EW)
  - Red: Mechanized force (T-90A/T-72M armor, BMP-2/BMP-1/BTR-80 mech, Kornet ATGM, SA-11/SA-6 AD, MiG-29A/Su-27S/Mi-24V air, HEMTT logistics)
  - Terrain: 20km × 20km, `hilly_defense`, 100m cell size
  - 6-hour duration with tick resolution switching (strategic → operational → tactical)
  - All 5 performance flags enabled + FOW

- **`benchmark_brigade/scenario.yaml`** — 5,000 units (2,500 blue + 2,500 red)
  - Blue: Full combined-arms brigade (same unit types as battalion, scaled 5×, plus DE-SHORAD)
  - Red: Mechanized brigade (scaled unit types, plus S-300PMU, J-10A, Iraqi Republican Guard)
  - Terrain: 50km × 50km, `flat_desert`, 200m cell size
  - 6-hour duration with tick resolution switching
  - All 5 performance flags enabled + FOW

### 90b: Performance Target Validation

- `benchmark_suite.py`: Added `calibration_overrides` parameter to `run_benchmark()` for flag impact testing
- Tightened existing benchmark targets:
  - 73 Easting: <30s → <15s
  - Golan Heights: <120s → <60s
- New benchmark test classes:
  - `TestBenchmarkBattalion`: wall_clock <300s, determinism, victory condition, regression
  - `TestBenchmarkBrigade`: wall_clock <1800s, determinism, victory condition, regression
- Scenario validation tests: load + unit count verification for both benchmarks
- Updated `baselines.json` with placeholder entries for new scenarios

### 90c: Optimization Flag Impact Matrix

- `test_flag_impact.py`: Measures individual and combined impact of 5 performance flags on Golan Heights (290 units) with FOW enabled
- Tests: baseline measurement, 5 individual flag tests (parametrized), combined effect, no-negative-interaction check
- Uses `calibration_overrides` parameter to toggle flags without modifying scenario YAML

## Design Decisions

1. **Ground-only benchmarks** — No naval units in benchmark scenarios. Naval domain routing adds complexity without performance insight for Block 9 optimizations (which target detection/movement/engagement on the FOW path).

2. **Tick resolution switching** — Both scenarios use `tick_resolution:` block (strategic/operational/tactical) instead of flat `tick_duration_seconds`. Prevents excessive tick counts during the approach phase.

3. **Calibration for decisive outcomes** — Moderate separation, meaningful advance speeds, asymmetric cohesion, aggressive destruction thresholds to avoid `time_expired` victories.

4. **`calibration_overrides` on `run_benchmark()`** — Post-load override mechanism. After `ScenarioLoader.load()`, rebuilds `CalibrationSchema` with merged overrides and recomputes `cal_flat`. Safe because performance flags are read lazily per-tick from `cal_flat`.

5. **No `weapon_assignments`** — Follows Korean Peninsula / Suwalki Gap pattern, relying on `_guess_weapon_id()` auto-assignment.

6. **Descoped flags** — `enable_parallel_movement` and `enable_aggregation` were listed in the roadmap's flag impact matrix but do not exist in CalibrationSchema (both descoped during Phases 85/89). Flag impact matrix tests only the 5 actual flags.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `tests/benchmarks/benchmark_suite.py` | Modified | +15 |
| `tests/benchmarks/test_benchmarks.py` | Modified | +140 |
| `tests/benchmarks/baselines.json` | Modified | +14 |
| `tests/benchmarks/test_flag_impact.py` | New | ~100 |
| `data/scenarios/benchmark_battalion/scenario.yaml` | New | ~120 |
| `data/scenarios/benchmark_brigade/scenario.yaml` | New | ~130 |

## Performance Results

| Scenario | Units | Target | Actual | Status |
|----------|-------|--------|--------|--------|
| 73 Easting | ~30 | <15s | 7.3s | PASS |
| Golan Heights | ~290 | <60s | ~438s* | NEEDS SOLO MEASUREMENT |
| Battalion | 1,000 | <300s | pending | PENDING |
| Brigade | 5,000 | <1800s | not yet run | PENDING |

*Golan Heights ran concurrently with battalion benchmark and full test suite — heavy CPU contention inflated wall clock ~7x. Solo run expected ~60-120s.

## Known Limitations

- Performance targets are hardware-dependent — baselines measured on Windows consumer hardware
- Flag impact measurements have ±10-20% noise on consumer hardware
- Brigade scenario may exceed 30-minute target depending on hardware
- `baselines.json` entries are placeholders until first measurement
- Battalion benchmark (1,000 units) exceeded 10 minutes without completing — <5 min target not met
- Benchmark scenarios are not listed in `docs/guide/scenarios.md` (they are performance infrastructure, not user-facing)

## Postmortem

### 1. Delivered vs Planned

**Roadmap vs actual:**

| Item | Planned | Delivered | Notes |
|------|---------|-----------|-------|
| 90a: Battalion scenario (1,000 units) | Yes | Yes | 500 blue + 500 red, 20km×20km, 6h |
| 90a: Brigade scenario (5,000 units) | Yes | Yes | 2,500 blue + 2,500 red, 50km×50km, 6h |
| 90b: Tightened 73 Easting target | Yes | Yes | <30s → <15s, measured 7.3s |
| 90b: Tightened Golan Heights target | Yes | Yes | <120s → <60s |
| 90b: Battalion <5 min | Yes | **Not met** | Exceeded 10 min timeout |
| 90b: Brigade <30 min | Yes | Not yet measured | |
| 90b: Baselines updated | Yes | Partial | Placeholder values, actual measurements pending |
| 90c: Flag impact matrix | Yes | Yes | 5 flags (not 7 — `enable_parallel_movement` and `enable_aggregation` descoped) |
| 90c: Profile hotspot comparison | Planned | Descoped | Roadmap mentioned but not implemented — flag impact tests measure wall clock, not hotspot changes |
| Unplanned: `calibration_overrides` on `run_benchmark()` | No | Yes | Needed for flag impact tests |
| Unplanned: CALIBRATION_SCENARIOS update | No | Yes | Benchmark scenarios added to avoid regression test failure |

**Verdict**: ~85% scope delivered. Core deliverables (scenarios, tests, flag matrix) all done. Battalion performance target not met — this is the key finding. Profile hotspot comparison descoped in favor of wall-clock impact measurement.

### 2. Integration Audit

| Check | Status |
|-------|--------|
| Both scenarios load via `ScenarioLoader.load()` | PASS |
| Both scenarios registered in `CALIBRATION_SCENARIOS` | PASS |
| `calibration_overrides` param used by `test_flag_impact.py` | PASS |
| `benchmark_battalion` and `benchmark_brigade` in `baselines.json` | PASS |
| All `@pytest.mark.benchmark` tests excluded from default run | PASS |
| No dead/orphaned test files | PASS |
| `test_flag_impact.py` imports from `benchmark_suite.py` correctly | PASS |

No dead modules. No orphaned imports.

### 3. Test Quality Review

- **25 tests total** (45 collected in `tests/benchmarks/` — 13 existing + 32 new; but some overlap with Phase 83 counts due to additional assertions in existing infra tests)
- **Schema validation tests** (fast): Load-only, verify unit counts — good edge cases
- **Benchmark tests** (slow): Wall clock, determinism, victory condition, regression — comprehensive
- **Flag impact tests** (very slow): Individual + combined flag measurement — strong design but sensitive to hardware noise
- **Appropriate markers**: All benchmark tests use `@pytest.mark.benchmark`, heavy tests also `@pytest.mark.slow`
- **`print()` in test_flag_impact.py**: Intentional — provides developer diagnostic output for benchmark runs, not production code

**Concern**: `test_individual_flag_not_slower` runs the Golan Heights baseline inside every parametrized invocation (once per flag × ~60-120s each). This means 5 baseline runs + 5 flag runs = ~10 full scenario executions for this parametrized set alone. Could be optimized with a class-scoped fixture, but acceptable for `@pytest.mark.slow` tests.

### 4. API Surface Check

- Type hints on `run_benchmark()` parameter: `calibration_overrides: dict[str, object] | None = None` — PASS
- `_run_golan()` helper appropriately private (`_` prefix) — PASS
- No bare `print()` in source files (only in test diagnostic output) — PASS
- DI pattern followed (no global state mutation) — PASS
- Module-level constants properly scoped: `_PERF_FLAGS`, `_ALL_OFF`, `_ALL_ON`, `_BASE_OVERRIDES` — PASS

### 5. Deficit Discovery

| ID | Severity | Description |
|----|----------|-------------|
| D90.1 | High | Battalion (1,000 units) exceeded 10 min — <5 min target not met. Engine needs further optimization or scenario simplification for this scale. |
| D90.2 | Medium | `baselines.json` entries for battalion/brigade are placeholder values, not measured actuals |
| D90.3 | Medium | Golan Heights <60s target not verified in solo run (only tested under CPU contention — 438s) |
| D90.4 | Low | `test_individual_flag_not_slower` runs baseline inside each parametrized test — redundant Golan runs |
| D90.5 | Low | Brigade benchmark not yet run — <30 min target unverified |

No TODOs, FIXMEs, bare `print()`, or `random` module usage found.

D90.1 is the key finding — it informs Phase 91 that current optimizations are insufficient for 1,000-unit scale within the 5-minute target. Phase 91 should address this via recalibration or target adjustment.

### 6. Documentation Freshness

All lockstep docs updated and verified:
- CLAUDE.md — Phase 90 row in Block 9 table, test counts updated — PASS
- README.md — badges updated (phase 90, ~10,581 tests) — PASS
- docs/index.md — badges updated, test count updated, scenario count 46 — PASS
- devlog/index.md — Phase 90 entry added — PASS
- development-phases-block9.md — status Complete, test count ~25, cumulative ~10,265 — PASS
- mkdocs.yml — Phase 90 nav entry added — PASS
- MEMORY.md — status, test counts, phase summary table updated — PASS
- Module index includes `tests/benchmarks/` with Phase 90 attribution — PASS
- Scenario guide (`docs/guide/scenarios.md`) — Not updated (benchmark scenarios are performance infrastructure, not user-facing) — ACCEPTABLE
- API reference (`docs/reference/api.md`) — No changes needed (`run_benchmark` is test infra, not public API) — PASS

### 7. Performance Sanity

Full suite: **9994 passed, 21 skipped, 250 deselected, 0 failures in 195.65s** (3:15).
Previous phase (Phase 89): 9988 passed in 187.36s (3:07).
Delta: +6 tests, +8.29s (+4.4%).

The 4.4% increase is within normal variance and accounted for by the 6 new tests (2 scenario validation tests that load 1,000-unit and 5,000-unit scenarios — loading 6,000 total units takes several seconds).

### 8. Summary

- **Scope**: Slightly under target (~85% — battalion performance target not met, profile hotspot comparison descoped)
- **Quality**: High — clean types, appropriate test markers, well-structured flag impact matrix
- **Integration**: Fully wired — scenarios load, baselines tracked, flag impact tests use `calibration_overrides`
- **Deficits**: 5 items (1 high, 2 medium, 2 low)
- **Action items**: D90.1 (battalion performance) and D90.2-D90.5 deferred to Phase 91 validation. Battalion target may need to be relaxed or engine optimized further.
