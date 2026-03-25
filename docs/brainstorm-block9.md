# Block 9: Performance at Scale

## Motivation

Blocks 1-8 delivered 82 phases of simulation capability: 19 engine modules, 44 validated scenarios, 5 historical eras, a web UI, and ~10,187 tests. The engine produces historically validated results for scenarios up to ~300 units (Golan Heights benchmark: 120s).

However, real-world operational scenarios routinely involve thousands of units. A brigade-level engagement (3,000-5,000 troops) with equipment is beyond the engine's current performance envelope. The tick loop is single-threaded, detection scales quadratically, and there is no level-of-detail system. **Performance at scale is the prerequisite for any future development** — more scenarios, larger campaigns, real-time visualization, and interactive play all depend on the engine handling 1,000+ units at reasonable speed.

### Current Performance Profile

| Scenario | Units | Duration | Wall Clock | Ticks/sec |
|----------|-------|----------|------------|-----------|
| 73 Easting | ~30 | 30 min | <30s | ~50 |
| Golan Heights | ~290 | 18 hr | ~120s | ~100 |
| 1,000 units (projected) | 1,000 | 6 hr | **~45 min** | ~8 |
| 5,000 units (projected) | 5,000 | 6 hr | **~18 hr** | <1 |

The projections assume O(n²) scaling from the dominant FOW detection loop, which is the single biggest bottleneck (estimated 2-7 seconds per tick at 1,000 units vs ~50ms at 290 units).

### Performance Budget

For the engine to support interactive-speed simulation at scale:

| Scale | Target | Tick Rate | Notes |
|-------|--------|-----------|-------|
| 1,000 units | <5 min for 6h scenario | ~15 ticks/s | Battalion-level engagement |
| 5,000 units | <30 min for 6h scenario | ~12 ticks/s | Brigade-level engagement |
| 10,000 units | <2 hr for 6h scenario | ~3 ticks/s | Division-level, acceptable for batch |

---

## Theme 1: Spatial Culling for Detection

**Problem**: FOW detection is O(n_own × n_enemy × n_sensors) per tick. Every sensor on every unit checks every enemy — even enemies 100km away when the sensor has a 5km max range. This is the single largest bottleneck, consuming an estimated 70-80% of tick time at 1,000+ units.

**Solution**: Spatial indexing with range-based culling.

### Approach A: STRtree Per-Tick Range Query

Build a Shapely STRtree of all unit positions once per tick. For each sensor, query only units within `max_range_m`. STRtree build is O(n log n), each query is O(log n + k) where k is the number of results.

**Expected improvement**: At 1,000 units with average sensor range covering 10% of enemies, detection goes from 500K checks to ~50K — a 10x reduction.

**Concerns**: STRtree rebuild cost per tick (~1ms for 1,000 points). Tree is immutable in Shapely 2.x — must rebuild, not update. Acceptable for now but limits future per-tick mutation patterns.

### Approach B: Fixed Grid Spatial Hash

Divide the terrain into cells (e.g., 1km × 1km). Assign units to cells. For sensor range queries, check only units in cells overlapping the sensor's range circle.

**Expected improvement**: Similar to STRtree but with O(1) insertion/removal per unit per tick (no rebuild). Better for scenarios with frequent position updates.

**Concerns**: Cell size tuning (too large = poor culling, too small = many empty cells). Irregular terrain boundaries. Memory for large maps with fine cells.

### Approach C: Dual Structure (STRtree + Grid)

Use grid for quick neighbor lookups during movement/engagement, STRtree for one-time per-tick detection sweeps. Each serves its optimal use case.

### Recommendation

Start with **Approach A** (STRtree per-tick). It's the simplest change — we already have STRtree infrastructure at 6 locations, and the FOW detection loop is a well-defined injection point. Measure. If rebuild cost is problematic at 5,000+ units, add grid spatial hash as a second tier.

---

## Theme 2: Sensor Scan Scheduling

**Problem**: Every sensor on every unit scans every tick. In reality, radar rotates (scan interval 2-12s), visual observation has attention limits, and sonar requires integration time. Scanning everything every tick wastes computation and is physically unrealistic.

**Solution**: Stagger sensor scans across ticks based on sensor type and scan interval.

### Design

Each sensor gets a `scan_interval_ticks` (from YAML or computed from `scan_rate_hz` and tick resolution). On any given tick, only sensors whose `(current_tick % scan_interval)` matches actually scan. Results persist from the last scan until the next.

**Expected improvement**: If average scan interval is 3 ticks, detection checks drop by ~67% on any given tick. Combined with spatial culling (Theme 1), the compound effect could be 20-30x reduction.

**Trade-off**: Introduces scan latency. A target entering range may not be detected for 1-2 ticks. This is physically realistic and could enhance gameplay (faster-scanning sensors become more valuable).

**Implementation**: Add `scan_interval_ticks` to sensor YAML schema (default 1 = every tick for backward compatibility). Modify FOW detection loop to check `tick % interval == 0` before invoking `check_detection()`.

---

## Theme 3: Level-of-Detail (LOD) for Distant Units

**Problem**: The engine resolves every unit at full fidelity regardless of distance from the action. A supply truck 50km behind the lines gets the same per-tick treatment as a tank in active engagement.

**Solution**: Variable resolution based on engagement proximity.

### Design

Classify units each tick into resolution tiers:

| Tier | Criteria | Update Frequency | Fidelity |
|------|----------|-----------------|----------|
| **Active** | In engagement or within 2× max weapon range of enemy | Every tick | Full (all systems) |
| **Nearby** | Within detection range but not engaged | Every 5 ticks | Reduced (movement + detection only, skip morale/logistics) |
| **Distant** | Beyond any sensor range of any enemy | Every 20 ticks | Minimal (movement only, aggregate supply consumption) |

**Expected improvement**: In a 1,000-unit scenario, typically ~100 units are actively engaged, ~200 are nearby, and ~700 are distant. Full per-tick processing drops from 1,000 to ~100 + 40 + 35 = ~175 effective units — a ~6x reduction.

**Concerns**: Tier transitions need hysteresis to prevent units flickering between tiers. Detection range calculation for tier assignment is itself O(n²) unless spatially culled (dependency on Theme 1). Units that suddenly become relevant (e.g., ambush) need immediate promotion to Active tier.

**Existing infrastructure**: The `auto_resolve` system (Phase 13) already uses Lanchester attrition for minor battles. LOD extends this concept to individual units within a battle.

---

## Theme 4: Engagement Selection Optimization

**Problem**: Threat-scored target selection iterates all enemies per attacker. With `target_selection_mode: threat` (the default), each attacker computes a score for every enemy, making engagement selection O(n × m).

**Solution**: Pre-filter candidates before scoring.

### Approach A: Range-Limited Candidate Set

Only score enemies within the attacker's maximum weapon range. Use the spatial index from Theme 1 to retrieve candidates.

**Expected improvement**: Typical weapon range covers 5-15% of the battlefield. Scoring drops from m to ~0.1m candidates per attacker.

### Approach B: Top-K Nearest Pre-Filter

Score only the K nearest enemies (e.g., K=10). For most engagements, the optimal target is among the 10 closest enemies.

**Risk**: Misses high-value distant targets (e.g., artillery at max range). Mitigated by including units that are targeting the attacker regardless of distance.

### Recommendation

**Approach A** — range-limited candidate set from spatial index. No tuning parameter (K), no risk of missing valid targets. Natural integration with Theme 1 spatial culling.

---

## Theme 5: Tick Loop Parallelism

**Problem**: The entire tick loop runs in a single Python thread. Movement, detection, engagement, morale, and logistics all execute sequentially even though many operations are independent per unit.

**Solution**: Selective parallelism for independent phases.

### Approach A: Per-Phase Thread Pool

Use `concurrent.futures.ThreadPoolExecutor` to parallelize within phases. For example, movement of unit A is independent of movement of unit B — dispatch all movements in parallel.

**Problem**: Python's GIL prevents true CPU parallelism for Python code. NumPy operations release the GIL, but pure Python logic (conditionals, dict lookups) doesn't benefit.

### Approach B: Per-Phase Process Pool

Use `ProcessPoolExecutor` for CPU-bound phases. Each worker gets a subset of units.

**Problem**: Serialization overhead for transferring unit state between processes. Large SimulationContext can't be shared efficiently. PRNG streams must be carefully partitioned to maintain determinism.

### Approach C: Numba Parallel Loops

Expand Numba JIT coverage to the hot inner loops (detection SNR, engagement resolution, morale state machine). Use `numba.prange` for automatic parallelism.

**Problem**: Numba can't JIT arbitrary Python objects. Would require restructuring data into Structure-of-Arrays (SoA) format — positions, health, ammo all as separate numpy arrays rather than object attributes.

### Approach D: Cython / C Extension Module

Write the critical inner loops (detection sweep, engagement resolution) in Cython or C. Interface via ctypes or Cython extension.

**Problem**: Build complexity, platform portability (Windows/Linux/Mac), maintenance burden.

### Approach E: Per-Side Parallelism

Run blue-side and red-side processing in parallel threads. Each side's detection/movement is independent until engagement resolution.

**Problem**: Engagement resolution requires both sides. Order of resolution affects outcomes (first-mover advantage). Determinism harder to guarantee with thread scheduling.

### Recommendation

**Short-term**: Approach C (expand Numba) for the detection hot path. The LOS kernel and ballistics already use it successfully. Detection SNR computation is pure math — ideal for JIT.

**Medium-term**: Approach E (per-side parallelism) for detection and movement phases. Engagement resolution remains sequential for determinism.

**Long-term**: If Numba coverage reaches 80%+ of hot path, consider Approach C with `prange` for automatic SIMD + threading.

**Avoid**: Process pool (B) due to serialization cost and PRNG complexity. Cython (D) due to build/maintenance burden.

---

## Theme 6: Data Structure Modernization

**Problem**: Units are Python objects with attribute access. The tick loop iterates lists of objects, accessing `.position.easting`, `.health`, `.morale_state` etc. This is cache-unfriendly and prevents vectorization.

**Solution**: Structure-of-Arrays (SoA) for hot-path data.

### Design

Maintain a parallel SoA representation alongside the existing Unit objects:

```python
class UnitArrays:
    """NumPy SoA for hot-path data. Synced with Unit objects each tick."""
    positions: np.ndarray      # (n, 2) float64 — easting, northing
    health: np.ndarray         # (n,) float64
    ammo: np.ndarray           # (n,) float64
    fuel: np.ndarray           # (n,) float64
    morale_state: np.ndarray   # (n,) int8 — enum ordinal
    side: np.ndarray           # (n,) int8 — 0=blue, 1=red
    operational: np.ndarray    # (n,) bool
    max_range: np.ndarray      # (n,) float64 — best weapon range
```

Hot-path operations (distance computation, range checks, health thresholds) operate on arrays. Results are synced back to Unit objects for engine consumption.

**Expected improvement**: NumPy operations on contiguous arrays are 10-100x faster than iterating Python objects. Cache locality improves dramatically. Opens the door to Numba `prange` parallelism.

**Concerns**: Two representations of the same data creates sync bugs. Must establish clear sync points (start-of-tick: objects → arrays, end-of-tick: arrays → objects). Existing code that reads unit attributes during the tick would need to read from the correct source.

**Incremental approach**: Start with positions-only SoA (already partially done via `enemy_pos_arrays` in Phase 70). Extend to health/ammo/fuel. Leave complex state (orders, equipment lists) on objects.

---

## Theme 7: CalibrationSchema Optimization

**Problem**: 125+ CalibrationSchema fields with ~100 `cal.get()` calls per tick in battle.py. Each call traverses pydantic model attribute access. While many were hoisted in Phase 70, side-prefixed keys (e.g., `{side}_force_ratio_modifier`) can't be hoisted past the side loop.

**Solution**: Pre-compute a flat lookup dict at scenario load time.

### Design

At `ScenarioLoader.load()` time, expand all CalibrationSchema fields into a flat `dict[str, Any]` including side-prefixed variants:

```python
cal_flat = {
    "hit_probability_modifier_blue": 1.2,
    "hit_probability_modifier_red": 0.8,
    "enable_fuel_consumption": True,
    "morale_base_degrade_rate": 0.01,
    ...
}
```

Replace `cal.get("key", default)` with `cal_flat["key"]` — a single dict lookup vs pydantic attribute traversal.

**Expected improvement**: Modest (5-10% of tick time). The main benefit is eliminating pydantic's `__getattr__` overhead for ~100 accesses per tick.

**Incremental**: Can coexist with existing CalibrationSchema (flat dict generated from schema at init time).

---

## Theme 8: Profiling Infrastructure

**Problem**: Performance optimization without profiling data is guesswork. The existing `PerformanceProfiler` (Phase 13) uses `cProfile` + `tracemalloc`, but there's no automated profiling pipeline and no historical baseline tracking.

**Solution**: Structured profiling with regression detection.

### Design

1. **Automated profile runs**: CI workflow that runs the Golan Heights benchmark and records wall clock, per-function hotspots, and memory peak
2. **Historical baselines**: JSON file tracking benchmark results per commit hash
3. **Regression alerts**: CI fails if benchmark exceeds previous best + 20% margin
4. **Flame graph generation**: Optional `py-spy` integration for visual profiling
5. **Per-phase profiling**: `/profile` skill generates hotspot report for any scenario

**Value**: Every optimization can be measured. Regressions are caught before merge. Developers know exactly where time is spent.

---

## Theme 9: Aggregation Activation

**Problem**: Phase 13 built a `ForceAggregationEngine` that snapshots individual units into composites for high-level processing, then disaggregates on contact. It's been disabled (`enable_aggregation=False`) since Phase 13 because disaggregated units lose their orders.

**Solution**: Fix the order-preservation issue and activate aggregation.

### Design

When aggregating, preserve each unit's current order in a `_pre_aggregation_orders` dict. On disaggregation, restore orders. Units that were idle before aggregation remain idle after.

**Expected improvement**: In a 5,000-unit scenario where 80% of units are in rear areas, aggregation reduces the active unit count from 5,000 to ~1,000 aggregates + ~1,000 active individuals = ~2,000 effective units.

**Interaction with LOD (Theme 3)**: LOD and aggregation are complementary. LOD reduces update frequency for distant units. Aggregation reduces the number of entities entirely. A distant aggregate of 50 trucks becomes one entity updated every 20 ticks — the compound effect is dramatic.

---

## Priority Assessment

| Theme | Impact | Effort | Risk | Priority |
|-------|--------|--------|------|----------|
| 1. Spatial culling (detection) | **Very High** | Low | Low | **P0** |
| 2. Sensor scan scheduling | High | Low | Low | **P0** |
| 3. LOD for distant units | High | Medium | Medium | **P1** |
| 4. Engagement selection opt. | Medium | Low | Low | **P1** |
| 5. Tick loop parallelism | Very High | High | High | **P2** |
| 6. SoA data structures | Very High | Very High | High | **P2** |
| 7. CalibrationSchema opt. | Low | Low | Low | **P2** |
| 8. Profiling infrastructure | Medium | Low | None | **P0** |
| 9. Aggregation activation | High | Medium | Medium | **P1** |

### Recommended Phase Ordering

**Phase 83: Profiling Infrastructure** — Measure before optimizing. Automated benchmarks, baselines, regression detection.

**Phase 84: Spatial Culling & Scan Scheduling** — Address the #1 bottleneck (FOW detection) with STRtree range culling + sensor scan intervals. Target: 10-30x detection speedup.

**Phase 85: LOD & Aggregation** — Reduce effective unit count. Tier-based update frequency + aggregation activation. Target: 5-6x tick reduction for 1,000+ unit scenarios.

**Phase 86: Engagement & Calibration Optimization** — Range-limited candidate sets for threat scoring + flat CalibrationSchema dict.

**Phase 87: Expanded Numba JIT** — JIT-compile detection SNR, engagement resolution, morale state machine. Target: 5-10x speedup on JIT-able paths.

**Phase 88: SoA Data Layer** — Structure-of-Arrays for positions, health, ammo, fuel. Prerequisite for vectorized bulk operations and `prange` parallelism.

**Phase 89: Per-Side Parallelism** — Thread-based parallelism for detection and movement phases. Requires SoA + deterministic thread scheduling.

**Phase 90: Validation & Benchmarking** — 1,000-unit and 5,000-unit benchmark scenarios. Regression suite. Performance profiling CI.

**Phase 91: Scenario Recalibration & Regression** — Full recalibration pass across all 44 scenarios. Spatial culling changes detection timing (scan scheduling introduces 1-2 tick latency), LOD changes update frequency for distant units, and aggregation alters force composition during rear-area processing. Each of these can shift engagement outcomes — particularly for scenarios where detection timing or force ratios at contact are decisive (73 Easting thermal advantage, Golan Heights defensive timing, Falklands missile exchange windows). MC validation at 10+ seeds per scenario, recalibrate thresholds/CEV where needed, verify all 13 decisive scenarios still produce correct winners. Also validates that large-scale benchmark scenarios (1K/5K units) produce militarily plausible outcomes, not just performance targets.

### Expected Outcome

If all themes are delivered:
- 1,000 units: **45 min → <5 min** (9x improvement from culling+LOD+scan scheduling)
- 5,000 units: **18 hr → <30 min** (36x improvement from culling+LOD+aggregation+JIT)
- 10,000 units: feasible for batch runs (~2 hr)
- All 44 existing scenarios produce identical or recalibrated-correct outcomes

---

## Constraints & Non-Goals

**Must preserve**:
- Deterministic reproducibility (same seed = same result)
- Backward compatibility (existing scenarios produce correct results — identical where possible, recalibrated where structural changes alter timing)
- `enable_*` flag pattern for opt-in behaviors
- Existing test suite passes without modification (recalibration phase adjusts scenario YAMLs and test thresholds as needed)

**Non-goals for this block**:
- GPU acceleration (CUDA/OpenCL) — too much infrastructure for current project scope
- Distributed simulation (multiple machines) — single-machine focus
- Real-time rendering optimization — frontend performance is a separate concern
- New simulation capabilities — this block is purely about making existing capabilities faster

---

## Research References

| Topic | Source | Relevance |
|-------|--------|-----------|
| Spatial hashing for games | Ericson, *Real-Time Collision Detection* (2005) | Grid-based spatial partitioning, sweep-and-prune |
| Military simulation LOD | OneSAF/ONESAF technical documentation | Variable resolution for constructive simulation |
| Entity Component System perf | Data-Oriented Design (Richard Fabian, 2018) | SoA vs AoS cache performance |
| Numba parallel patterns | Numba docs: `prange`, `@vectorize`, `@guvectorize` | Python-level parallelism without GIL |
| Agent-based model scaling | MASON simulation framework | Spatial indexing for large agent populations |
| STRtree vs R-tree performance | Shapely 2.0 benchmarks | Query performance at different scales |
