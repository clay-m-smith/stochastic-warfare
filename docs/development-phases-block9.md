# Stochastic Warfare -- Block 9 Development Phases (83--91)

## Philosophy

Block 9 is the **performance at scale block**. The engine produces historically validated results for scenarios up to ~300 units (Golan Heights: 120s). Real-world operational scenarios involve thousands of units. The tick loop is single-threaded, detection scales quadratically, and there is no level-of-detail system. Every future development direction — more scenarios, larger campaigns, real-time visualization, interactive play — depends on the engine handling 1,000+ units at reasonable speed.

This block measures first, then attacks the dominant O(n²) bottleneck (FOW detection), reduces effective unit count via LOD and aggregation, optimizes engagement selection and calibration lookups, expands JIT compilation, introduces SoA data for vectorization, adds per-side parallelism, and validates everything at scale.

**Performance targets**:

| Scale | Target | Current (projected) |
|-------|--------|---------------------|
| 1,000 units, 6h scenario | <5 min | ~45 min |
| 5,000 units, 6h scenario | <30 min | ~18 hr |
| 10,000 units, 6h scenario | <2 hr | infeasible |

**Exit criteria**:
1. Golan Heights (290 units) under 60s (from 120s)
2. New 1,000-unit benchmark scenario completes in <5 min
3. New 5,000-unit benchmark scenario completes in <30 min
4. All 44 existing scenarios produce correct winners (recalibrated if needed)
5. Deterministic reproducibility preserved (same seed = same result)
6. Profiling CI catches regressions (>20% slowdown fails build)
7. All existing tests pass (no behavioral regressions)

**Cross-document alignment**: This document must stay synchronized with `brainstorm-block9.md` (design thinking), `devlog/index.md` (phase status), and `specs/project-structure.md` (module definitions). Run `/cross-doc-audit` after any structural change.

**No new simulation capabilities**: Block 9 makes existing capabilities faster. No new combat models, eras, or subsystems. All changes are internal optimizations gated behind `enable_*` flags where they affect behavior.

---

## Phase 83: Profiling Infrastructure

**Status**: Complete.

**Goal**: Establish measurement infrastructure before optimizing. Automated benchmarks, baseline tracking, regression detection, flame graph generation.

**Dependencies**: Block 8 complete (Phase 82).

### 83a: Benchmark Suite

Formalize the existing ad-hoc performance tests into a structured benchmark suite with JSON baseline tracking.

- **`tests/benchmarks/benchmark_suite.py`** (new) -- Structured benchmark runner:
  - `BenchmarkResult` dataclass: scenario name, unit count, wall_clock_s, ticks_executed, ticks_per_second, peak_memory_mb, hotspots (top 20 by cumulative time)
  - `BenchmarkBaseline` class: loads/saves JSON baselines (`tests/benchmarks/baselines.json`)
  - `run_benchmark(scenario_path, seed=42) -> BenchmarkResult`: cProfile + tracemalloc wrapper
  - Regression check: `result.wall_clock_s > baseline * 1.2` → FAIL
- **`tests/benchmarks/baselines.json`** (new) -- Baseline results per scenario:
  - `73_easting`: wall_clock_s, ticks, memory
  - `golan_heights`: wall_clock_s, ticks, memory
  - Format: `{"scenario": {"wall_clock_s": float, "ticks_executed": int, "peak_memory_mb": float, "commit": str}}`
- **`tests/benchmarks/test_benchmarks.py`** (new) -- Parametrized benchmark tests:
  - `@pytest.mark.benchmark` marker (excluded by default, run via `pytest -m benchmark`)
  - 73 Easting benchmark (<30s assertion + baseline comparison)
  - Golan Heights benchmark (<120s assertion + baseline comparison)
  - Determinism verification (same seed = same winner + casualties)

**Tests** (~6):
- Benchmark suite runs and produces BenchmarkResult
- Baseline JSON loads/saves correctly
- Regression detection triggers on >20% slowdown
- Determinism check verifies identical results across runs

### 83b: Profiling Tooling

Extend the existing `/profile` skill with flame graph support and structured hotspot reporting.

- **`stochastic_warfare/tools/profiling.py`** (modified) -- Add:
  - `generate_hotspot_report(result: BenchmarkResult) -> str`: Formatted top-20 hotspots with % of total time
  - `save_flame_graph(scenario_path, output_path)`: Optional `py-spy` integration (requires `py-spy` installed)
  - `compare_profiles(before: BenchmarkResult, after: BenchmarkResult) -> str`: Side-by-side comparison

**Tests** (~4):
- Hotspot report formatting
- Profile comparison output
- Flame graph path generation (no assertion on py-spy availability)

### 83c: CI Benchmark Workflow

Add a GitHub Actions workflow for automated performance regression detection.

- **`.github/workflows/benchmark.yml`** (new) -- Benchmark CI:
  - Trigger: push to main, PR to main
  - Steps: checkout, uv sync, run 73 Easting benchmark, compare against baselines.json
  - Fail if >20% regression
  - Upload benchmark results as artifact
  - Golan Heights benchmark on `workflow_dispatch` only (too slow for every PR)

**Tests** (~2):
- Workflow YAML is valid
- Baseline file exists and is parseable

### Exit Criteria
- Benchmark suite runs and produces structured results
- Baseline JSON established for 73 Easting and Golan Heights
- CI workflow detects >20% regressions
- `/profile` skill generates hotspot reports

---

## Phase 84: Spatial Culling & Scan Scheduling

**Status**: Complete.

**Goal**: Address the #1 bottleneck — O(n²) FOW detection — with STRtree range culling and sensor scan intervals. Target: 10-30x detection speedup.

**Dependencies**: Phase 83 (profiling baseline established).

### 84a: STRtree Detection Culling

Build a per-tick spatial index of unit positions. Cull FOW detection loop to only check targets within sensor max range.

- **`stochastic_warfare/detection/fog_of_war.py`** (modified) -- In detection sweep:
  - At start of tick: build `STRtree` from all unit positions (one tree per side, or one global tree with side filtering)
  - For each sensor: query tree for units within `sensor.max_range_m` radius
  - Pass only matching targets to `check_detection()` instead of all enemies
  - Gate behind `enable_detection_culling: bool = True` CalibrationSchema flag (default True — safe optimization, no behavioral change for targets outside sensor range)
- **`stochastic_warfare/simulation/calibration.py`** (modified) -- Add `enable_detection_culling: bool = True`

**Tests** (~12):
- Unit outside sensor range is not checked (verify reduced call count)
- Unit inside sensor range is still detected (no false negatives)
- STRtree build + query faster than brute-force at 100, 500, 1000 units
- Edge case: unit exactly at max range boundary (include, not exclude)
- Edge case: sensor with unlimited range (no culling applied)
- Determinism: identical results with and without culling for all existing scenarios
- Performance: Golan Heights tick time reduced (measure, don't assert specific %)

### 84b: Sensor Scan Scheduling

Stagger sensor scans across ticks based on scan interval. Not every sensor scans every tick.

- **`data/sensors/*.yaml`** + **`data/eras/*/sensors/*.yaml`** (modified, 33 files) -- Add `scan_interval_ticks: int` field to sensor YAML:
  - Radar: 2-4 ticks (rotating antenna, 5-12s scan period at 5s/tick)
  - Visual: 1 tick (continuous observation)
  - Thermal/IR: 1-2 ticks (near-continuous)
  - Sonar: 3-5 ticks (acoustic integration time)
  - Default: 1 (backward compatible — every tick)
- **`stochastic_warfare/detection/sensors.py`** (modified) -- Add `scan_interval_ticks` to `SensorDefinition` model (`Field(default=1, ge=1)`)
- **`stochastic_warfare/detection/fog_of_war.py`** (modified) -- In detection sweep:
  - Before scanning with a sensor: check `current_tick % sensor.scan_interval_ticks == offset`
  - `offset` derived from `hash(sensor_id) % scan_interval_ticks` to distribute scans evenly
  - Last detection result persists until next scan (no "forgetting" between scans)
  - Gate behind `enable_scan_scheduling: bool = False` CalibrationSchema flag (default False — opt-in since this changes detection timing)
- **`stochastic_warfare/simulation/calibration.py`** (modified) -- Add `enable_scan_scheduling: bool = False`

**Tests** (~10):
- Radar sensor with interval=3 only scans on ticks 0, 3, 6, 9, ...
- Visual sensor with interval=1 scans every tick (backward compat)
- Detection result persists between scans (target remains "detected" until next scan says otherwise)
- Scan offset distributes multiple radars evenly (not all on same tick)
- `enable_scan_scheduling=False` → all sensors scan every tick (backward compat)
- Performance: detection checks reduced by ~50-67% with typical sensor mix

### 84c: Engagement Candidate Culling

Use the same spatial index from 84a to pre-filter engagement targets in the battle loop.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- In `_execute_engagements()`:
  - Before threat scoring: query spatial index for enemies within attacker's `max_weapon_range_m`
  - Score only candidate set (not all enemies)
  - Reuse per-tick STRtree built in 84a (pass via context or battle manager attribute)
  - No new flag (pure optimization — scoring subset of enemies produces identical best-target selection since out-of-range enemies would score 0)

**Tests** (~8):
- Same target selected with and without culling (determinism)
- Candidate set size matches manual range filter
- Zero-candidate case: no enemies in range → skip engagement (already handled)
- Performance: threat scoring time reduced proportionally to candidate reduction

### Exit Criteria
- Golan Heights benchmark <90s (from 120s baseline — conservative 25% improvement)
- 73 Easting benchmark unchanged (small scenario, no benefit from culling)
- All 44 scenarios produce identical results (culling is transparent)
- Profiling shows detection phase dropped from ~70% to <30% of tick time

---

## Phase 85: LOD & Aggregation

**Status**: Complete.

**Goal**: Reduce effective unit count by classifying units into resolution tiers and activating the existing aggregation engine. Target: 5-6x tick reduction for 1,000+ unit scenarios.

**Dependencies**: Phase 84 (spatial index available for tier classification).

### 85a: Unit Resolution Tiers

Classify units each tick into Active/Nearby/Distant tiers with different update frequencies.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- Add LOD tier system:
  - `_classify_unit_tier(unit, enemy_positions, spatial_index) -> Tier` using spatial index from Phase 84:
    - `ACTIVE`: in engagement or within 2× max weapon range of any enemy
    - `NEARBY`: within max sensor range of any enemy but not ACTIVE
    - `DISTANT`: beyond any sensor range of any enemy
  - Tier update frequency: ACTIVE=every tick, NEARBY=every 5 ticks, DISTANT=every 20 ticks
  - On non-update ticks for NEARBY/DISTANT: skip detection, morale, logistics; run movement only
  - Hysteresis: unit must be in new tier for 3 consecutive ticks before reclassification (prevents flickering)
  - Instant promotion: any unit that takes damage or detects a new contact → immediately ACTIVE
  - Gate behind `enable_lod: bool = False` CalibrationSchema flag
- **`stochastic_warfare/simulation/calibration.py`** (modified) -- Add:
  - `enable_lod: bool = False`
  - `lod_nearby_interval: int = 5` — tick interval for NEARBY tier
  - `lod_distant_interval: int = 20` — tick interval for DISTANT tier
  - `lod_hysteresis_ticks: int = 3` — ticks before tier downgrade

**Tests** (~14):
- Unit in engagement classified as ACTIVE
- Unit far from all enemies classified as DISTANT
- DISTANT unit only updated every 20 ticks (verify skip)
- NEARBY unit only updated every 5 ticks
- Hysteresis prevents single-tick flickering
- Unit that takes damage instantly promoted to ACTIVE
- `enable_lod=False` → all units processed every tick (backward compat)
- Tier boundaries correct at 2× weapon range (ACTIVE) and sensor range (NEARBY)
- Performance: 1000-unit scenario with LOD vs without (measure improvement)

### 85b: Aggregation Activation

Fix order preservation in ForceAggregationEngine and activate it.

- **`stochastic_warfare/simulation/aggregation.py`** (modified) -- Fix disaggregation:
  - Before aggregation: snapshot each unit's current order in `_pre_aggregation_orders: dict[str, Order | None]`
  - On disaggregation: restore orders from snapshot
  - Units that were idle (no order) before aggregation remain idle after
  - Clear snapshot after successful disaggregation
- **`stochastic_warfare/simulation/engine.py`** (modified) -- Wire aggregation into campaign tick:
  - When `enable_aggregation=True`: aggregate distant units (reuse LOD tier from 85a — DISTANT units aggregate)
  - Disaggregate when aggregate enters NEARBY range
  - Existing `enable_aggregation` flag (Phase 13, default False)

**Tests** (~10):
- Aggregation preserves unit orders (snapshot/restore roundtrip)
- Idle units remain idle after disaggregation
- Aggregate moves at weighted average speed of component units
- Disaggregation triggers when aggregate enters NEARBY range (from LOD spatial index)
- Aggregate supply consumption matches sum of component unit rates
- Aggregate detection signature is sum of component signatures (larger = easier to detect)
- `enable_aggregation=False` → no aggregation (backward compat)

### 85c: LOD + Aggregation Integration

Verify the compound effect of LOD and aggregation together.

- **Tests** (~6):
- 1000-unit scenario: measure effective unit count with LOD only vs LOD+aggregation
- Distant aggregate of 50 units updated every 20 ticks (compound effect: 50 units → 1 entity × 1/20 frequency = 1000x reduction)
- Aggregation respects LOD tier transitions (disaggregate → ACTIVE, don't skip to DISTANT)
- Full scenario: results within acceptable tolerance of non-LOD results (not identical due to update frequency changes, but same winner)

### Exit Criteria
- 1000-unit benchmark with LOD+aggregation: effective processing load <200 units/tick
- Golan Heights: <80s (LOD has limited effect at 290 units since most are engaged)
- All existing scenarios correct with `enable_lod=False` (default, backward compat)
- Order preservation roundtrip verified

---

## Phase 86: Engagement & Calibration Optimization

**Status**: Complete.

**Goal**: Optimize engagement selection and CalibrationSchema access patterns. Low-effort, low-risk improvements.

**Dependencies**: Phase 84 (spatial index for candidate culling already done in 84c).

### 86a: CalibrationSchema Flat Dict

Pre-compute a flat lookup dict at scenario load time for O(1) calibration access.

- **`stochastic_warfare/simulation/calibration.py`** (modified) -- Add:
  - `CalibrationSchema.to_flat_dict(sides: list[str]) -> dict[str, Any]`: expand all fields including side-prefixed variants into flat dict
  - Side-prefixed keys: `"{side}_{field}"` for `hit_probability_modifier`, `force_ratio_modifier`, `cohesion`, `target_size_modifier`
  - Called once at scenario load time in `ScenarioLoader`
- **`stochastic_warfare/simulation/battle.py`** (modified) -- Replace `cal.get("key", default)` with `cal_flat["key"]`:
  - ~100 replacements in engagement loop, movement loop, morale loop
  - Side-prefixed keys now resolved at lookup time (`cal_flat[f"{side}_force_ratio_modifier"]`)
  - Preserve `cal.get()` API for backward compat in external callers (flat dict is internal optimization)
- **`stochastic_warfare/simulation/scenario.py`** (modified) -- Generate flat dict at load time:
  - `ctx.cal_flat = cal_schema.to_flat_dict(side_names)` on SimulationContext

**Tests** (~8):
- Flat dict contains all 125+ fields
- Side-prefixed keys generated correctly for both sides
- `cal_flat["enable_fuel_consumption"]` matches `cal.enable_fuel_consumption`
- Flat dict is immutable after creation (dict, not defaultdict)
- Performance: measure `cal_flat["key"]` vs `cal.get("key", default)` × 10K lookups
- Full scenario: identical results with flat dict vs pydantic access

### 86b: Detection Modifier Batching

Batch the 20+ detection range modifiers into a single pre-computed multiplier per unit.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- In engagement loop:
  - Pre-compute `_detection_modifier: dict[str, float]` per unit at start of tick:
    - Weather visibility factor
    - Night/thermal factor
    - Concealment factor (terrain-dependent, already per-target)
    - MOPP factor
    - Icing factor
    - Naval posture factor
    - Obscurant spectral factor
  - During engagement: multiply sensor range by pre-computed modifier instead of evaluating each check inline
  - Concealment remains per-target (depends on target position), all other modifiers are per-observer

**Tests** (~6):
- Pre-computed modifier matches inline computation for all modifier types
- Per-target concealment still computed inline (not pre-computed)
- Identical results for all existing scenarios
- Performance: engagement modifier cascade time reduced

### Exit Criteria
- CalibrationSchema flat dict generates correctly for all scenarios
- Detection modifier batching produces identical results
- Measurable tick time reduction (profile before/after)
- All existing tests pass

---

## Phase 87: Expanded Numba JIT

**Status**: Complete.

**Goal**: JIT-compile detection SNR computation, engagement resolution math, and morale state transitions. Target: 5-10x speedup on JIT-able paths.

**Dependencies**: Phase 86 (flat dict provides simple data types for Numba compatibility).

### 87a: Detection SNR Kernels

JIT-compile the SNR computation functions for all sensor types.

- **`stochastic_warfare/detection/detection.py`** (modified) -- Add `@optional_jit` to:
  - `compute_snr_visual(signal, noise, range_m, ...) -> float`
  - `compute_snr_thermal(signal, noise, range_m, ...) -> float`
  - `compute_snr_radar(rcs, power, range_m, ...) -> float`
  - `compute_snr_acoustic(sl, tl, nl, ...) -> float`
  - All are pure scalar math — ideal Numba targets
  - Ensure function signatures use only primitive types (float64, int64, bool)
- **`stochastic_warfare/detection/fog_of_war.py`** (modified) -- Add vectorized detection sweep:
  - `_batch_snr_check(observer_pos, target_positions, sensor_params, ...) -> np.ndarray[bool]`
  - Numba `@guvectorize` or `prange` over target array
  - Returns boolean mask of detected targets (replaces per-target Python loop)

**Tests** (~8):
- JIT SNR matches Python SNR for all 4 sensor types (value equality within float tolerance)
- Batch detection produces same results as per-target loop
- Performance: batch detection 5-10x faster than loop at 500+ targets
- Graceful fallback when Numba not installed

### 87b: Engagement Math Kernels

JIT-compile engagement resolution math (hit probability, penetration, damage).

- **`stochastic_warfare/combat/damage.py`** (modified) -- Add `@optional_jit` to:
  - `compute_hit_probability(range_m, accuracy, modifiers, ...) -> float`
  - `compute_penetration(velocity, caliber, armor, obliquity, ...) -> float`
  - `compute_damage_fraction(penetration, armor, ...) -> float`
- **`stochastic_warfare/combat/ballistics.py`** (already JIT) -- Verify existing RK4 kernel coverage

**Tests** (~6):
- JIT hit probability matches Python computation
- JIT penetration matches DeMarre formula
- Performance: engagement resolution 3-5x faster per engagement
- Graceful fallback

### 87c: Morale State Machine Kernel

JIT-compile the continuous-time Markov morale transition computation.

- **`stochastic_warfare/morale/state.py`** (modified) -- Add `@optional_jit` to:
  - `compute_transition_rates(current_state, stress, cohesion, ...) -> np.ndarray`
  - `_evaluate_transition(rates, dt, rng_value) -> int` — returns new state ordinal
  - Batch version: `_batch_morale_update(states, stresses, cohesions, dt, rng_values) -> np.ndarray`

**Tests** (~6):
- JIT transition matches Python transition for all 5 morale states
- Batch morale update produces same results as per-unit loop
- Performance: morale phase 3-5x faster at 500+ units
- Graceful fallback

### Exit Criteria
- All JIT kernels produce identical results to Python equivalents
- Numba available: measurable speedup on profiled paths
- Numba not available: zero behavioral change (fallback works)
- All existing tests pass with and without Numba

---

## Phase 88: SoA Data Layer

**Status**: Complete.

**Goal**: Introduce Structure-of-Arrays for hot-path unit data. Prerequisite for vectorized bulk operations and Numba `prange` parallelism.

**Dependencies**: Phase 87 (JIT kernels ready to consume array data).

### 88a: UnitArrays Core

Create the SoA data structure and sync protocol.

- **`stochastic_warfare/simulation/unit_arrays.py`** (new) -- `UnitArrays` class:
  - Fields: `positions (n,2)`, `health (n,)`, `ammo (n,)`, `fuel (n,)`, `morale_state (n,) int8`, `side (n,) int8`, `operational (n,) bool`, `max_range (n,)`, `unit_ids (n,) str array`
  - `from_units(units: list[Unit]) -> UnitArrays`: build arrays from Unit objects (start-of-tick sync)
  - `sync_to_units(units: list[Unit])`: write array values back to Unit objects (end-of-tick sync)
  - `filter_by_side(side: int) -> tuple[UnitArrays, np.ndarray]`: return filtered view + original indices
  - `filter_operational() -> tuple[UnitArrays, np.ndarray]`: exclude non-operational units
- **`stochastic_warfare/simulation/battle.py`** (modified) -- Build UnitArrays at start of `execute_tick()`:
  - Replace `enemy_pos_arrays` dict with UnitArrays (superset of existing Phase 70 position arrays)
  - Vectorized distance matrix: `cdist(blue.positions, red.positions)` (scipy) or broadcast
  - Gate behind `enable_soa: bool = False` CalibrationSchema flag

**Tests** (~12):
- Round-trip sync: Unit → UnitArrays → Unit produces identical state
- Positions array matches Unit.position.easting/northing
- Side filtering produces correct subsets
- Operational filtering excludes destroyed units
- Distance matrix matches per-pair computation
- Performance: vectorized distance 10x+ faster than Python loop at 500 units
- `enable_soa=False` → existing behavior (backward compat)

### 88b: SoA Detection Integration

Use UnitArrays in the FOW detection loop for vectorized range checks.

- **`stochastic_warfare/detection/fog_of_war.py`** (modified) -- When UnitArrays available:
  - Vectorized range check: `np.linalg.norm(observer_pos - targets.positions, axis=1) < max_range` (single numpy op)
  - Combined with STRtree culling (Phase 84): STRtree filters to ~100 candidates, then vectorized SNR across candidates
  - Integration with Numba batch kernels (Phase 87): pass array slices to JIT functions

**Tests** (~6):
- Vectorized range check matches per-target check
- SoA detection produces identical detections to non-SoA path
- Performance: detection phase with SoA + culling + JIT combined

### 88c: SoA Movement & Morale Integration

Extend UnitArrays usage to movement and morale phases.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- Movement phase:
  - Vectorized position updates: `positions += velocity * dt` for all units in one operation
  - Fuel consumption: `fuel -= distance * rate` vectorized across all units
  - Sync back to Unit objects after movement phase
- **`stochastic_warfare/simulation/battle.py`** (modified) -- Morale phase:
  - Batch morale kernel from Phase 87c consumes `morale_state` and `stress` arrays directly
  - Sync back morale states to Unit objects after morale phase

**Tests** (~8):
- Vectorized movement matches per-unit movement (position + fuel)
- Vectorized morale matches per-unit morale transitions
- Full scenario: identical results with and without SoA
- Performance: movement + morale phases measurably faster

### Exit Criteria
- UnitArrays round-trip sync verified
- SoA integrated into detection, movement, and morale phases
- All existing scenarios produce identical results with `enable_soa=False`
- Measurable speedup at 500+ units

---

## Phase 89: Per-Side Parallelism

**Status**: Not started.

**Goal**: Thread-based parallelism for detection and movement phases. Each side's detection/movement is independent until engagement resolution.

**Dependencies**: Phase 88 (SoA data layer enables independent per-side array operations).

### 89a: Per-Side Detection Threading

Run blue-side and red-side detection sweeps in parallel threads.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- In detection phase:
  - Split UnitArrays by side
  - Submit blue detection + red detection to `ThreadPoolExecutor(max_workers=2)`
  - Each thread: build side-specific STRtree, run JIT detection sweep on its own UnitArrays slice
  - GIL released during numpy/Numba operations → true parallelism for the vectorized paths
  - Join results before engagement phase
  - Gate behind `enable_parallel_detection: bool = False` CalibrationSchema flag
- **PRNG determinism**: Each side uses its own pre-spawned RNG stream (already separate via ModuleId). Thread scheduling order doesn't affect PRNG sequences because each side consumes its own stream.

**Tests** (~8):
- Parallel detection produces identical results to sequential (determinism)
- Both sides' detections complete before engagement phase begins
- PRNG streams are independent (no cross-contamination)
- Performance: detection phase ~1.5-1.8x faster (not 2x due to GIL contention on Python overhead)
- `enable_parallel_detection=False` → sequential (backward compat)
- Thread safety: no shared mutable state between detection threads

### 89b: Per-Side Movement Threading

Run blue-side and red-side movement in parallel.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- In movement phase:
  - Split UnitArrays by side
  - Submit blue movement + red movement to `ThreadPoolExecutor(max_workers=2)`
  - Each thread: apply vectorized position + fuel updates on its own UnitArrays slice
  - Join and sync back to Unit objects before detection phase
  - Gate behind `enable_parallel_movement: bool = False` CalibrationSchema flag

**Tests** (~6):
- Parallel movement produces identical results to sequential
- PRNG determinism preserved
- Performance: movement phase ~1.5x faster
- `enable_parallel_movement=False` → sequential (backward compat)

### 89c: Engagement Resolution (Sequential)

Engagement resolution remains sequential for determinism. Document why and verify.

- **Tests** (~4):
- Engagement order is deterministic (sorted by unit_id or position)
- First-mover advantage is consistent across runs with same seed
- Engagement results identical regardless of parallel detection/movement flags
- Full scenario: all 44 scenarios produce correct results with all parallel flags enabled

### Exit Criteria
- Per-side parallelism produces identical results to sequential
- PRNG determinism preserved across all parallel configurations
- Detection + movement each ~1.5x faster with parallelism
- All existing scenarios correct with parallel flags enabled

---

## Phase 90: Validation & Benchmarking

**Status**: Not started.

**Goal**: Create large-scale benchmark scenarios (1,000 and 5,000 units), validate performance targets, establish baselines for the new scale.

**Dependencies**: Phase 89 (all optimizations in place).

### 90a: Large-Scale Benchmark Scenarios

Create two new scenarios designed for performance testing at scale.

- **`data/scenarios/benchmark_battalion/scenario.yaml`** (new) -- 1,000-unit battalion engagement:
  - Blue: 500 units (mixed armor/infantry/artillery/air defense)
  - Red: 500 units (mixed armor/infantry/artillery)
  - Terrain: 20km × 20km rolling terrain
  - Duration: 6 hours
  - Calibration: `enable_detection_culling: true`, `enable_scan_scheduling: true`, `enable_lod: true`, `enable_soa: true`
  - Expected outcome: decisive combat (not time_expired)
- **`data/scenarios/benchmark_brigade/scenario.yaml`** (new) -- 5,000-unit brigade engagement:
  - Blue: 2,500 units (full combined arms brigade with logistics tail)
  - Red: 2,500 units (mechanized brigade)
  - Terrain: 50km × 50km
  - Duration: 6 hours
  - Calibration: all performance flags enabled + `enable_aggregation: true`
  - Expected outcome: decisive combat
- **Unit YAML**: Reuse existing modern unit types with `count` multipliers (no new unit definitions needed)

**Tests** (~6):
- Both scenarios load and validate against pydantic schema
- Battalion scenario completes (seed=42, any outcome acceptable for first run)
- Brigade scenario completes (seed=42, any outcome acceptable)
- Victory condition triggered (not max_ticks safety limit)

### 90b: Performance Target Validation

Run benchmarks and verify performance targets from brainstorm.

- **`tests/benchmarks/test_benchmarks.py`** (modified) -- Add:
  - Battalion benchmark: <5 min assertion (`@pytest.mark.benchmark`)
  - Brigade benchmark: <30 min assertion (`@pytest.mark.benchmark`)
  - Golan Heights regression: <60s assertion (improved from 120s baseline)
  - Profile hotspot comparison: before/after for each optimization phase
- **`tests/benchmarks/baselines.json`** (modified) -- Add battalion and brigade baselines

**Tests** (~4):
- Battalion <5 min
- Brigade <30 min
- Golan Heights <60s
- 73 Easting <15s (should be faster too)

### 90c: Optimization Flag Impact Matrix

Measure the individual and combined impact of each optimization flag.

- **`tests/benchmarks/test_flag_impact.py`** (new) -- Parametrized tests:
  - Run Golan Heights with each flag individually enabled, then all combined
  - Flags: `enable_detection_culling`, `enable_scan_scheduling`, `enable_lod`, `enable_soa`, `enable_parallel_detection`, `enable_parallel_movement`, `enable_aggregation`
  - Record wall_clock_s for each combination
  - Generate impact matrix (which flags help most, any negative interactions)

**Tests** (~8):
- Individual flag impact measured for each of 7 flags
- Combined flag impact measured
- No negative interactions (no flag makes things slower)

### Exit Criteria
- Battalion scenario <5 min
- Brigade scenario <30 min
- Golan Heights <60s
- Impact matrix shows which optimizations contribute most
- Baselines established for new scenarios

---

## Phase 91: Scenario Recalibration & Regression

**Status**: Not started.

**Goal**: Full recalibration pass across all 44+ scenarios. Verify that performance optimizations haven't shifted outcomes, recalibrate where they have, and validate large-scale scenarios produce militarily plausible results.

**Dependencies**: Phase 90 (all benchmarks established, performance targets met).

### 91a: Behavioral Impact Assessment

Run all 44 scenarios with and without performance flags to identify outcome shifts.

- **`tests/validation/test_block9_regression.py`** (new) -- For each scenario:
  - Run with all performance flags OFF (baseline behavior)
  - Run with all performance flags ON
  - Compare: winner, victory condition type, tick count, casualty counts
  - Flag any scenario where winner changes or victory type changes
  - Expected: spatial culling (84a) and engagement culling (84c) are transparent (identical results)
  - Expected: scan scheduling (84b) and LOD (85a) may shift timing-sensitive outcomes

**Tests** (~44):
- One parametrized test per scenario (44 scenarios × 2 configurations)
- Winner comparison: PASS if same, FLAG if different

### 91b: Timing-Sensitive Scenario Recalibration

For scenarios where scan scheduling or LOD shifts outcomes, recalibrate.

- **Likely candidates** (based on brainstorm analysis):
  - **73 Easting**: Thermal detection timing is decisive — scan interval changes could shift first-detection advantage
  - **Golan Heights**: Defensive timing (who detects whom first at long range) — scan scheduling may shift initial contact timing
  - **Falklands Naval**: Missile exchange windows are narrow — scan latency could change Exocet detection timing
  - **Bekaa Valley**: SEAD timing against IADS — radar scan interval directly affects engagement sequence
- **Process**: For each flagged scenario:
  - Run MC at 10+ seeds with performance flags ON
  - If correct winner rate drops below 80%: adjust `calibration_overrides` (CEV, hit modifiers, morale rates)
  - If correct winner rate is 80%+: accept (within statistical noise)
  - Document all recalibrations in devlog

**Tests** (~13 decisive + variable):
- All 13 decisive combat scenarios produce correct winner at 80%+ MC rate
- Recalibrated scenarios documented with rationale
- Non-decisive scenarios (time_expired) maintain plausible composite scores

### 91c: Large-Scale Scenario Validation

Verify battalion and brigade benchmark scenarios produce militarily plausible outcomes.

- **Process**:
  - Run MC at 5+ seeds for each benchmark scenario
  - Verify: engagements occur (not just movement), casualties are non-trivial, victory condition triggers before max_ticks
  - Verify: force ratio outcomes align with Lanchester expectations (larger/better-equipped side wins)
  - Adjust calibration if outcomes are implausible (e.g., 5000-unit battle with 0 casualties)

**Tests** (~6):
- Battalion scenario: non-zero casualties on both sides
- Battalion scenario: decisive victory (not time_expired or max_ticks)
- Brigade scenario: non-zero casualties on both sides
- Brigade scenario: decisive victory
- Both scenarios: winner consistent across 5 seeds (>60% same winner)

### 91d: Documentation & Lockstep

Update all living documents for Block 9 completion.

- **Files**: CLAUDE.md, README.md, docs/index.md, docs/devlog/index.md, mkdocs.yml, MEMORY.md
- **Phase devlog**: `docs/devlog/phase-91.md` with Block 9 retrospective
- Run `/cross-doc-audit` to verify all 19 checks pass

### Exit Criteria
- All 44 existing scenarios produce correct winners (recalibrated where needed)
- All 13 decisive scenarios at 80%+ MC correctness
- Battalion and brigade scenarios produce plausible outcomes
- All documentation updated
- Cross-doc audit passes (19/19)
- Block 9 COMPLETE

---

## Phase Summary

| Phase | Focus | Tests | Cumulative | Status |
|-------|-------|-------|------------|--------|
| 83 | Profiling Infrastructure | 13 | ~10,003 | Complete |
| 84 | Spatial Culling & Scan Scheduling | 31 | ~10,034 | Complete |
| 85 | LOD & Aggregation | 30 | ~10,064 | Complete |
| 86 | Engagement & Calibration Optimization | 19 | ~10,083 | Complete |
| 87 | Expanded Numba JIT | 40 | ~10,176 | Complete |
| 88 | SoA Data Layer | 43 | ~10,219 | Complete |
| 89 | Per-Side Parallelism | ~18 | ~10,237 | Not started |
| 90 | Validation & Benchmarking | ~18 | ~10,255 | Not started |
| 91 | Scenario Recalibration & Regression | ~63 | ~10,318 | Not started |

**Block 9 total (so far)**: 176 new tests across 6 completed phases, ~99 estimated for remaining 3.
**Cumulative**: ~10,219 Python tests + ~316 frontend vitest = ~10,535 total.

---

## Module Index: Block 9 Contributions

| Module | Phases | Changes |
|--------|--------|---------|
| `detection/fog_of_war.py` | 84, 87, 88 | STRtree culling, scan scheduling, vectorized detection, SoA integration |
| `simulation/battle.py` | 84, 85, 86, 88, 89 | Engagement culling, LOD tiers, flat cal dict, modifier batching, SoA sync, per-side threads |
| `simulation/calibration.py` | 84, 85, 86, 89 | `enable_detection_culling`, `enable_scan_scheduling`, `enable_lod`, `enable_soa`, `enable_parallel_*`, flat dict API |
| `simulation/unit_arrays.py` | 88 | New: SoA data structure with sync protocol |
| `simulation/aggregation.py` | 85 | Order preservation fix, LOD-triggered activation |
| `simulation/engine.py` | 85 | Aggregation wiring in campaign tick |
| `simulation/scenario.py` | 86 | Flat cal dict generation at load time |
| `detection/detection.py` | 87 | JIT SNR kernels (4 sensor types) |
| `combat/damage.py` | 87 | JIT hit probability, penetration, damage |
| `morale/state.py` | 87 | JIT morale transition kernel |
| `entities/equipment.py` | 84 | `scan_interval_ticks` on sensor model |
| `data/sensors/*.yaml` | 84 | `scan_interval_ticks` field (~16 files) |
| `tools/profiling.py` | 83 | Flame graph, hotspot reports, profile comparison |
| `tests/benchmarks/` | 83, 90 | Benchmark suite, baselines, flag impact matrix |
| `.github/workflows/` | 83 | benchmark.yml |
| `data/scenarios/benchmark_*/` | 90 | Battalion (1K) and brigade (5K) scenarios |

---

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| STRtree rebuild cost at 5,000+ units | Medium | Measure in Phase 84; fall back to grid spatial hash if >10ms/tick |
| Scan scheduling shifts detection timing | High | `enable_scan_scheduling=False` default; recalibrate in Phase 91 |
| LOD tier misclassification (ambush missed) | High | Instant promotion on damage/contact; hysteresis prevents over-eager downgrade |
| SoA sync bugs (two representations of same data) | High | Explicit sync points (start/end of tick); round-trip tests |
| Numba compilation overhead on first call | Low | `cache=True` on all JIT decorators; amortized over scenario |
| Per-side threading breaks determinism | High | Independent PRNG streams per side; sequential engagement resolution; extensive determinism tests |
| Aggregation order loss on disaggregation | Medium | Phase 85b explicitly snapshots/restores orders; tested |
| Large-scale scenarios produce implausible outcomes | Medium | Phase 91c validates with MC; recalibrate if needed |
| GIL limits threading benefit | Medium | Focus parallel work on numpy/Numba ops which release GIL; expect 1.5x not 2x |
