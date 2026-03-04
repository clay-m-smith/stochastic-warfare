# Phase 13: Performance Optimization — Devlog

**Status**: Complete (+ postmortem cleanup)
**Tests**: 142 (+ 7 benchmark, + 11 determinism, + 28 postmortem = 188 total phase tests)
**Total Suite**: 4,247 tests passing (up from 4,077)
**New Source Files**: 2 (`core/numba_utils.py`, `simulation/aggregation.py`)
**Modified Source Files**: ~10 (`terrain/infrastructure.py`, `terrain/los.py`, `detection/estimation.py`, `combat/ballistics.py`, `movement/pathfinding.py`, `simulation/battle.py`, `simulation/engine.py`, `simulation/scenario.py`, `validation/monte_carlo.py`, `pyproject.toml`)
**New Scripts**: `scripts/profile_golan.py` (Golan campaign profiling)

---

## Overview

Phase 13 delivers performance optimization across three tracks: algorithmic improvements (13a), compiled extensions (13b), and parallelism enhancement (13c). All changes are backward-compatible via `enable_*` config flags and safe defaults. The optional `numba` dependency (`uv sync --extra perf`) enables JIT compilation for hot paths; without it, pure-Python fallbacks are used.

---

## Sub-phase Summary

### 13a-1: Benchmark Infrastructure (7 benchmark tests)
- Added `benchmark` marker to `pyproject.toml`, excluded from default test runs
- Created `tests/benchmarks/test_phase13_benchmarks.py` with baseline measurements for spatial queries, Kalman predict, LOS checks, pathfinding, RK4 trajectory, MC import, and viewshed

### 13a-2: STRtree Spatial Indexing (14 tests)
- Rewrote `terrain/infrastructure.py` to use `shapely.STRtree` for all spatial queries
- Built 3 STRtree indices: `_road_tree`, `_building_tree`, `_airfield_tree`
- Rewrote `roads_near()`, `nearest_road()`, `buildings_at()`, `buildings_near()`, `airfields_near()` to use STRtree queries
- Post-filter for condition > 0 (damaged features)

### 13a-3: Kalman F/Q Matrix Caching (6 tests)
- Added `_cached_dt`, `_cached_F`, `_cached_Q` fields to `StateEstimator`
- `predict()` reuses cached matrices when dt matches (eliminates ~2499 redundant matrix constructions per tick)

### 13a-4: Multi-tick LOS Cache (11 tests)
- Added `invalidate_cells(dirty_cells)` to `LOSEngine`
- Selectively removes cache entries involving moved-unit grid cells
- More efficient than full `clear_los_cache()` when few units moved
- Added `los_cache_size` property for monitoring

### 13a-5: Viewshed Vectorization (8 tests)
- `visible_area()` uses numpy broadcasting for distance computation
- Skips out-of-range cells before running per-cell LOS checks
- Benefits from per-tick LOS cache

### 13a-6: Auto-Resolve for Minor Battles (17 tests)
- Added `auto_resolve()` to `BattleManager` with simplified Lanchester attrition
- 10 time steps, exponent 0.5, morale and supply modifiers
- `auto_resolve_enabled` and `auto_resolve_max_units` config flags
- `AutoResolveResult` dataclass with winner, side_losses, duration

### 13a-7: Force Aggregation/Disaggregation (27 tests)
- New `simulation/aggregation.py` (~350 lines)
- `AggregationEngine` manages complete lifecycle: snapshot → aggregate → disaggregate
- `UnitSnapshot` captures all subsystem state (unit, morale, weapons, sensors, supply)
- `AggregateUnit` represents composite formation with constituent snapshots
- `check_aggregation_candidates()` finds eligible groups (distance from battle, minimum size)
- `check_disaggregation_triggers()` finds aggregates needing breakup (approaching battle)
- State persistence via `get_state()`/`set_state()`
- Deterministic aggregate IDs

### 13b-1: Numba Utils Infrastructure (5 tests)
- New `core/numba_utils.py` with `NUMBA_AVAILABLE` flag and `@optional_jit` decorator
- Falls back to identity decorator when Numba not installed
- Supports both `@optional_jit` and `@optional_jit(cache=False)` patterns

### 13b-2: Numba JIT for RK4 Trajectory (18 tests)
- Extracted `_derivs_kernel()` and `_rk4_trajectory_kernel()` as JIT functions
- `compute_trajectory()` delegates to kernel, returns 2-point trajectory (start + impact)
- `@optional_jit` on `_speed_of_sound()` and `_mach_drag_multiplier()`
- Boolean config flags converted to int for JIT compatibility

### 13b-3: Numba JIT for DDA Raycasting (8 tests)
- `_los_terrain_kernel()` JIT function for terrain-only LOS ray march
- Inline bilinear interpolation and earth curvature correction
- `_check_los_terrain_jit()` method on LOSEngine

### 13b-4: A* Difficulty Grid Pre-computation (11 tests)
- `_compute_difficulty_grid()` pre-computes cell difficulty into numpy array
- `find_path()` uses array lookup (O(1)) instead of per-cell dict cache
- Bounding box + 10-cell margin with fallback for out-of-bounds cells

### 13c-1: MC Parallelism Enhancement (6 tests)
- Both `MonteCarloHarness` and `CampaignMonteCarloHarness` use `submit()` + `as_completed()`
- Results sorted by seed for deterministic ordering

### 13c-2: Integration Benchmarks + Determinism Tests (11 determinism tests)
- LOS cache: selective invalidation matches full clear
- Kalman cache: cached predict identical to uncached
- RK4 trajectory: deterministic across runs
- Aggregation: round-trip preserves unit state
- Auto-resolve: deterministic given same PRNG
- Viewshed: deterministic and matches individual LOS checks

---

## Implementation Decisions

1. **STRtree `buildings_at()` uses `predicate='covered_by'`** not `'contains'` — Shapely 2.0 STRtree has inverted semantics for this predicate direction.

2. **RK4 kernel returns 2-point trajectory** — Numba can't create Python objects, so the fast path returns only impact data. Full trajectory recording (for visualization) would require a separate slow path.

3. **A* uses pre-computed numpy grid instead of Numba JIT** — A* involves heapq and dicts which Numba doesn't support well. Pre-computing difficulty into a numpy array eliminates the per-cell method call overhead (the actual bottleneck) while keeping A* logic in pure Python.

4. **Force aggregation captures all subsystem state** — `UnitSnapshot` stores unit state, morale, weapons, sensors, and supply inventory. This ensures disaggregation fully restores the original unit across all simulation systems.

5. **Auto-resolve adapted from COA wargaming** — The Lanchester attrition model in `battle.py` is adapted from `c2/planning/coa.py::wargame_coa()`, using the same exponent and attrition math.

---

## Known Limitations

- **Numba not installed by default** — JIT kernels only activate with `uv sync --extra perf`. Without Numba, all code paths use pure-Python fallbacks with identical behavior.
- **Auto-resolve is simplified** — Uses aggregate combat power, not per-unit engagement. Suitable for minor/distant battles, not main battles.
- **Aggregation does not handle orders** — Active orders are lost on aggregation. Disaggregated units await new orders.
- **Thread-pool per-side parallelism not implemented** — The plan included per-side thread-pool parallelism within ticks, but this was deferred as it requires careful PRNG stream partitioning and the risk of non-determinism outweighs the benefit for current scenario scales.

---

## Postmortem Cleanup (28 tests)

Benchmarking revealed that two major features — force aggregation and selective LOS invalidation — were implemented but **not wired** into the simulation loop. Auto-resolve was already wired. The postmortem wires the remaining features and adds profiling infrastructure.

### Changes

1. **`simulation/scenario.py`** — Added `aggregation_engine: Any = None` field to `SimulationContext`. Included in `get_state()`/`set_state()` engine lists. Instantiated `AggregationEngine` in `ScenarioLoader._create_engines()`.

2. **`simulation/engine.py`** — Wired aggregation into strategic tick: between `update_strategic()` and `detect_engagements()`, runs `check_disaggregation_triggers()` → `disaggregate()`, then `check_aggregation_candidates()` → `aggregate()`. Added `_compute_battle_positions()` helper (computes centroids from active battle unit_ids). Added `enable_selective_los_invalidation` config flag to `EngineConfig`. Replaced monolithic LOS cache clear with dirty-cell tracking: `_snapshot_unit_cells()` before/after movement, `invalidate_cells()` for changed cells.

3. **`scripts/profile_golan.py`** — New profiling script using `PerformanceProfiler` for the Golan Heights campaign.

### Known Limitations

- **Aggregation still disabled by default** — `AggregationConfig.enable_aggregation = False`. Explicit opt-in required via scenario config.
- **Selective LOS disabled by default** — `EngineConfig.enable_selective_los_invalidation = False`. Full clear remains the safe default.
- **Aggregation does not preserve active orders** — Disaggregated units await new orders (unchanged from Phase 13a-7).

---

## Test Files

| File | Tests | Focus |
|------|-------|-------|
| `test_phase13_benchmarks.py` | 7 | Performance baselines |
| `test_phase_13a2_strtree.py` | 14 | STRtree spatial indexing |
| `test_phase_13a3_kalman_cache.py` | 6 | Kalman F/Q caching |
| `test_phase_13a4_los_cache.py` | 11 | Selective LOS invalidation |
| `test_phase_13a5_viewshed.py` | 8 | Viewshed vectorization |
| `test_phase_13a6_auto_resolve.py` | 17 | Auto-resolve |
| `test_phase_13a7_aggregation.py` | 27 | Force aggregation/disaggregation |
| `test_phase_13b1_numba_utils.py` | 5 | Numba utils infrastructure |
| `test_phase_13b2_numba_rk4.py` | 18 | RK4 JIT kernel |
| `test_phase_13b3_numba_dda.py` | 8 | DDA raycasting JIT |
| `test_phase_13b4_astar_precompute.py` | 11 | A* difficulty grid |
| `test_phase_13c1_mc_parallel.py` | 6 | MC parallelism |
| `test_phase13_determinism.py` | 11 | Determinism verification |
| `test_phase_13_postmortem.py` | 28 | Aggregation wiring, selective LOS wiring, integration |
