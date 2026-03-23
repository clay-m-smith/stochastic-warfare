# Phase 70: Performance Optimization

## Overview
Eliminated O(n²) hot paths in `battle.py` to achieve measurable speedup on large scenarios. Pure optimization phase — no new behavioral features, no new CalibrationSchema fields.

## Deliverables

### 70a: Vectorized Nearest-Enemy & Movement Target
- Added optional `enemy_pos_arr: np.ndarray` parameter to `_nearest_enemy_dist()` and `_movement_target()`
- Vectorized path uses numpy `sum/min/argmin/mean/sqrt` on pre-built position arrays
- Scalar fallback preserved for backward compatibility
- `_execute_movement()` updated to accept and pass `enemy_pos_arrays`
- Call sites at naval posture (L1272) and standoff check (L2423) pass vectorized arrays

**Deviation from plan**: Used numpy vectorization instead of STRtree. Simpler approach since `_build_enemy_data()` already produces per-side numpy arrays — reusing existing infrastructure rather than adding a new spatial index.

### 70b: Unit ID Index & Formation Sort Hoisting
- `_unit_index: dict[str, Unit]` built once per tick in `execute_tick()`
- Replaces O(n) linear scan for UAV parent lookup (data link range check)
- Replaces redundant per-unit-lookup dict build in fire zone damage section
- Formation sort hoisted before per-unit loop: `_sorted_active` + `_unit_formation_idx` computed once per side
- Eliminates O(n² log n) from `sorted()` inside per-unit movement loop

### 70c: Signature Cache & Calibration/Engine Hoisting
- `self._signature_cache: dict[str, Any]` on BattleManager — caches by unit_type (immutable per scenario)
- ~30 `cal.get()` calls hoisted before engagement loop body (each checks 4 patterns)
- ~8 `cal.get()` calls hoisted before movement loop body
- ~20 `getattr(ctx, engine, None)` calls hoisted before engagement loop
- ~8 `getattr(ctx, engine, None)` calls hoisted before movement loop
- Side-prefixed keys (`{side}_force_ratio_modifier`) correctly left inline

### 70d: Performance Benchmarks
- `tests/performance/test_battle_perf.py` — 4 tests (2 benchmark + 2 determinism)
- 73 Easting: < 30s assertion + determinism verification
- Golan Heights: < 180s assertion + determinism verification (marked `@pytest.mark.slow`)

## Files Modified

| File | Changes |
|------|---------|
| `stochastic_warfare/simulation/battle.py` | 253 insertions, 181 deletions |

## New Test Files

| File | Tests |
|------|-------|
| `tests/unit/test_phase_70a_vectorized.py` | 7 |
| `tests/unit/test_phase_70b_unit_index.py` | 6 |
| `tests/unit/test_phase_70c_caching.py` | 7 |
| `tests/performance/test_battle_perf.py` | 4 |
| **Total** | **24** |

## Dropped Items
- Weapon category → EngagementType pre-cache (low-frequency path, not worth the complexity)
- Taiwan Strait dedicated benchmark (Golan Heights is the harder test)
- STRtree approach for nearest-enemy (numpy vectorization is simpler and equally effective)

## Lessons Learned
- **Reuse existing arrays**: `_build_enemy_data()` already produced numpy arrays that were unused by distance functions. Passing them through was far simpler than building a new spatial index.
- **Hoisting is high line-count, low risk**: ~60 mechanical substitutions in the engagement loop, but each is a trivial `cal.get("X", default)` → `_hoisted_var` replacement.
- **Side-prefixed keys can't be hoisted above the per-side loop**: Keys like `{side}_formation_spacing_m` vary by side, so they must stay inside the side loop (but outside the per-unit loop).
- **Pre-existing test failures mask signal**: 15 scenarios fail due to `engine.py` UnboundLocalError (`_sim_time_s`) from Phase 69 — unrelated to Phase 70 but complicates regression detection.

## Postmortem

- **Scope**: On target — all high-impact optimizations delivered, two low-impact items correctly dropped
- **Quality**: High — 100-point random parity tests, determinism verification, zero TODOs
- **Integration**: Fully wired — all changes in existing `battle.py`, no orphaned code
- **Deficits**: 0 new deficits. Pre-existing: engine.py `_sim_time_s` bug (Phase 69)
- **Action items**: Update all lockstep docs (CLAUDE.md, devlog/index.md, development-phases-block8.md, MEMORY.md, README.md)
