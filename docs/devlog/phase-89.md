# Phase 89: Per-Side Parallelism

**Status**: Complete
**Block**: 9 (Performance at Scale)
**Tests**: 21

## What Was Built

Thread-based per-side parallelism for FOW detection. When `enable_parallel_detection=True`, each side's detection sweep runs in a separate thread via `ThreadPoolExecutor`, enabling true parallelism during GIL-free numpy/STRtree/Numba operations.

### 89a: Per-Side Detection Threading
- `CalibrationSchema` field: `enable_parallel_detection: bool = False`
- `DetectionEngine.check_detection()` accepts optional `rng: np.random.Generator | None = None` parameter — uses provided RNG instead of internal `self._rng` for detection roll
- `FogOfWarManager.update()` accepts optional `rng` parameter, flows through to `check_detection()`
- `battle.py` `execute_tick()` refactored:
  - Per-side FOW input data (own_data, enemy_data) pre-built sequentially before dispatch
  - When `enable_parallel_detection=True` and >= 2 sides: fork detection RNG via `integers()` draw, create per-side `PCG64` generators, submit per-side `FOW.update()` to `ThreadPoolExecutor(max_workers=min(n_sides, 4))`
  - When disabled: sequential loop (identical to previous behavior)

### 89b: Movement Parallelism — Descoped
- GIL prevents true parallelism for Python-heavy movement loop (15+ conditional branches per unit)
- Vectorized helpers (`_nearest_enemy_dist`, `_movement_target`) are numpy but called per-unit — threading overhead exceeds benefit
- Same rationale as Phase 88's movement vectorization descope

### 89c: Sequential Engagement Verification
- Engagement resolution confirmed sequential — no ThreadPoolExecutor in `_execute_engagements()`
- First-mover effects require deterministic engagement order

## Design Decisions

1. **RNG forking via `integers()` draw** — draw `n_sides` seeds from the detection stream, create independent per-side generators. Deterministic: same master seed → same per-side seeds. Results differ from sequential mode (different RNG sequences) — expected and acceptable.

2. **`rng` parameter injection** — explicit parameter passed through `FOW.update()` → `DetectionEngine.check_detection()`. Matches project DI conventions (no singletons, no thread-local storage).

3. **ThreadPoolExecutor per-tick** — `with` context manager creates/destroys pool each tick. ~1ms overhead vs 10-100ms tick time at scale. Avoids lifecycle management complexity.

4. **Thread safety analysis** — each side writes to different `_world_views[side]` key; `_scan_counts` entries keyed by `(sensor_id, target_id)` don't overlap between sides; `_intel_fusion` tracks are per-side; STRtree built locally inside `update()`. Only shared RNG is bypassed by explicit `rng` parameter.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `stochastic_warfare/simulation/calibration.py` | Modified | +3 |
| `stochastic_warfare/detection/detection.py` | Modified | +3 |
| `stochastic_warfare/detection/fog_of_war.py` | Modified | +2 |
| `stochastic_warfare/simulation/battle.py` | Modified | +30 |
| `tests/validation/test_phase_67_structural.py` | Modified | +1 |
| `tests/unit/test_phase89_parallel_detection.py` | New | 15 tests |
| `tests/unit/test_phase89_sequential_engagement.py` | New | 6 tests |

## Performance Notes

- Expected speedup: ~1.3-1.5x for detection at 1000+ units (GIL-free fraction: STRtree queries, numpy distance ops, Numba SNR kernels)
- Modest at <100 units due to Python overhead dominance
- ThreadPoolExecutor overhead (~1ms per tick) negligible at scale
- Movement parallelism descoped — GIL limits benefit for Python-heavy loop

## Known Limitations

- Parallel results differ from sequential (different RNG sequences) — Phase 91 handles recalibration
- ThreadPoolExecutor created/destroyed each tick — could optimize to persistent pool if profiling shows overhead
- Only detection phase parallelized — movement remains sequential due to GIL
- `enable_parallel_detection=False` default — opt-in for performance testing
- `max_workers` capped at 4 (hardcoded) — reasonable for most systems but not configurable

## Postmortem

### 1. Delivered vs Planned

~80% of planned scope delivered. Core detection threading (89a) fully delivered. Movement threading (89b) descoped due to GIL — same rationale as Phase 88's movement vectorization descope. Sequential engagement verification (89c) confirmed. 21 tests vs ~18 estimated.

### 2. Integration Audit

| Check | Status |
|-------|--------|
| `enable_parallel_detection` in CalibrationSchema | PASS |
| `enable_parallel_detection` consumed in battle.py | PASS |
| `rng` param in `DetectionEngine.check_detection()` | PASS |
| `rng` param in `FogOfWarManager.update()` | PASS |
| `rng` flows through to `check_detection()` call | PASS |
| `concurrent.futures` imported in battle.py | PASS |
| `enable_parallel_detection` in `_DEFERRED_FLAGS` | PASS |
| `to_flat_dict()` includes new flag | PASS |

No dead modules. No orphaned imports.

### 3. Test Quality Review

- **21 tests** across 2 files — strong coverage of RNG forking, determinism, parity, cross-contamination, backward compat, structural
- Good edge cases: three-faction, guaranteed detection, out-of-range
- RNG independence tests (draw order doesn't affect values) are particularly strong
- **Gap**: No end-to-end test calling `BattleManager.execute_tick()` with `enable_parallel_detection=True` on a real scenario. Relies on Phase 90 validation.

### 4. API Surface Check

- Type hints on all new parameters — PASS (`rng: np.random.Generator | None = None`)
- DI pattern followed (explicit params, no singletons, no thread-local) — PASS
- No new public functions — all changes to existing APIs — PASS
- No bare `print()` — PASS

### 5. Deficit Discovery

| ID | Severity | Description |
|----|----------|-------------|
| D89.1 | Medium | No end-to-end `execute_tick()` test with parallel detection enabled |
| D89.2 | Low | `max_workers` hardcoded to 4, not configurable via CalibrationSchema |

No TODOs, FIXMEs, bare `print()`, or `random` module usage found.

### 6. Documentation Freshness

All lockstep docs updated and verified accurate:
- CLAUDE.md, README.md, docs/index.md, devlog/index.md, development-phases-block9.md, mkdocs.yml, MEMORY.md — all PASS

### 7. Performance Sanity

Full suite: 187.36s (3:07). No regression from Phase 88 (188.65s). `enable_parallel_detection=False` default means zero runtime impact on existing scenarios.

### 8. Summary

- **Scope**: Slightly under target (~80% — movement threading descoped)
- **Quality**: High — clean types, DI pattern, minimal changes
- **Integration**: Fully wired — CalibrationSchema, battle loop, FOW, DetectionEngine
- **Deficits**: 2 items (1 medium, 1 low)
- **Action items**: D89.1 (end-to-end test) deferred to Phase 90 validation. D89.2 (max_workers) accepted as-is.
