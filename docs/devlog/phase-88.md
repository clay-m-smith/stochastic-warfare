# Phase 88: SoA Data Layer

**Status**: Complete
**Block**: 9 (Performance at Scale)
**Tests**: 43

## What Was Built

Structure-of-Arrays (SoA) data layer for hot-path unit data. `UnitArrays` provides contiguous NumPy arrays for positions, health, fuel, morale, and operational status — enabling vectorized distance computation, range checks, and batch operations.

### 88a: UnitArrays Core
- New `stochastic_warfare/simulation/unit_arrays.py` — `UnitArrays` class with 8 SoA fields
- `from_units()` classmethod builds arrays from `units_by_side` dict
- Fields: positions `(n,2)`, health `(n,)`, fuel `(n,)`, morale_state `(n,)`, side_indices `(n,)`, operational `(n,)`, max_range `(n,)`, unit_ids
- Filtering: `side_mask()`, `enemy_mask()`, `get_enemy_positions()`, `get_active_enemy_indices()`
- Distance: `distance_matrix()` via `scipy.spatial.distance.cdist`
- Position sync-back: `sync_positions_to_units()` (preserves altitude)
- Wired into `battle.py` `execute_tick()` behind `enable_soa: bool = False` CalibrationSchema flag
- When enabled, overrides `enemy_pos_arrays` with SoA-derived versions — all downstream consumers (LOD, movement, engagement) get SoA data transparently
- UnitArrays rebuilt after movement phase (positions stale after movement)

### 88b: SoA Detection Integration
- `FogOfWarManager.update()` accepts optional `unit_arrays` parameter
- When SoA available and STRtree not used, vectorized numpy range check filters targets: `np.sqrt(np.sum(diffs * diffs, axis=1))` replaces per-target Python distance loop
- STRtree remains primary culling mechanism; numpy range check is alternative path
- Battle.py passes `_unit_arrays` to FOW update call

### 88c: SoA Morale & Engagement Integration
- Morale arrays pre-extracted from UnitArrays for batch consumption
- Health arrays available for pre-computed stress factors
- `get_side_positions()` provides contiguous position arrays for engagement STRtree
- `distance_matrix()` for pairwise engagement distance computation

## Design Decisions

1. **UnitArrays is a read-mostly snapshot** — built at tick start, consumed during phases, discarded. Unit objects remain source of truth. Avoids sync-bug risk from dual-representation.

2. **Movement NOT vectorized** — movement loop has 15+ conditional branches per unit (posture, weather, obstacles, fuel, fire zones). Vectorizing would require restructuring the entire movement phase. SoA provides position arrays to existing vectorized helpers (`_movement_target`, `_nearest_enemy_dist` from Phase 70).

3. **`_build_enemy_data()` still runs** — SoA overrides `enemy_pos_arrays` dict after construction, giving all existing consumers SoA-derived data without downstream changes.

4. **STRtree coexists with SoA** — complementary, not competing. STRtree handles spatial culling; SoA provides contiguous arrays for numpy operations.

5. **`enable_soa=False` default** — zero behavioral change when disabled. Opt-in for performance testing.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `stochastic_warfare/simulation/unit_arrays.py` | New | ~220 |
| `stochastic_warfare/simulation/battle.py` | Modified | +20 |
| `stochastic_warfare/simulation/calibration.py` | Modified | +3 |
| `stochastic_warfare/detection/fog_of_war.py` | Modified | +18 |
| `tests/unit/test_phase88_unit_arrays.py` | New | 26 tests |
| `tests/unit/test_phase88_detection_soa.py` | New | 7 tests |
| `tests/unit/test_phase88_integration.py` | New | 10 tests |

## Performance Notes

- Distance matrix (500×500 units): vectorized cdist >10x faster than Python loop
- Numpy range check avoids per-target Position→float extraction overhead
- UnitArrays construction is O(n) — lightweight for typical battle sizes (10-200 units)
- Main performance gains expected when Phase 89 (per-side parallelism) consumes SoA data

## Known Limitations

- SoA only consumed by detection (range check) and battle loop (enemy positions) — morale/engagement integration is structural only (pre-extracted arrays available but not yet driving batch computation)
- `sync_positions_to_units()` exists but not yet used in practice — movement still updates Unit objects directly
- `max_range` extraction requires `unit_weapons` dict — not available in all test contexts
- No Numba kernel integration yet — SoA provides the data layout; Phase 89 threading will be the consumer
- `ammo` field was in the original spec but omitted — unit ammo is per-weapon, not a single scalar; deferred until a clear consumer exists

## Postmortem

### 1. Delivered vs Planned

~60% of planned scope delivered. Core `UnitArrays` class, battle loop integration, FOW vectorized range check all delivered. Three items descoped:

- **Movement vectorization dropped** — 15+ conditional branches per unit make vectorized position updates impractical. Sound decision documented in Design Decisions.
- **Morale batch computation dropped** — Phase 87 JIT kernels already fast per-unit. Arrays pre-extracted but not driving batch computation. Structural-only integration.
- **`ammo` field omitted** — unit ammo is per-weapon (list of weapon/ammo tuples), not a single scalar. No clean SoA representation without flattening. Deferred.

`filter_by_side()` / `filter_operational()` replaced with simpler `side_mask()` / `enemy_mask()` boolean arrays — more composable. `sync_to_units()` narrowed to `sync_positions_to_units()` (position-only). Both reasonable simplifications.

### 2. Integration Audit

| Check | Status |
|-------|--------|
| `unit_arrays.py` imported by `battle.py` | PASS |
| `enable_soa` consumed in `battle.py` | PASS |
| FOW `unit_arrays` param wired | PASS |
| UnitArrays rebuilt after movement | PASS |
| `enable_soa` in `_DEFERRED_FLAGS` | PASS |
| `project-structure.md` lists `unit_arrays.py` | PASS (fixed during postmortem) |

No dead modules. No orphaned imports.

### 3. Test Quality Review

- **43 tests** across 3 files — strong coverage of core `UnitArrays` class
- Good edge cases: empty units, no personnel, destroyed units, three-faction
- Performance micro-benchmark (500-unit cdist vs loop) — fast enough, no `@pytest.mark.slow` needed
- **Gap**: Detection SoA tests verify a local reimplementation, not the actual FOW code path. No end-to-end test calling `FogOfWarManager.update()` with `unit_arrays` and `detection_culling=False`.
- Structural tests (source string search) catch integration regressions

### 4. API Surface Check

- Type hints on all public functions — PASS
- `get_logger(__name__)` used — PASS
- `__slots__` for memory efficiency — PASS
- DI pattern followed (explicit params, no singletons) — PASS
- `target_positions_array()` is public but only used internally — minor, harmless

### 5. Deficit Discovery

| ID | Severity | Description |
|----|----------|-------------|
| D88.1 | Low | `ammo` field in spec but not delivered (documented above) |
| D88.2 | Medium | No end-to-end FOW vectorized path test |
| D88.3 | Low | `target_positions_array()` public but only used internally |

No TODOs, FIXMEs, bare `print()`, or `random` module usage found.

### 6. Documentation Freshness

All lockstep docs updated and verified accurate:
- CLAUDE.md, README.md, docs/index.md, devlog/index.md, development-phases-block9.md, mkdocs.yml, MEMORY.md — all PASS
- `project-structure.md` — fixed during postmortem (was missing `unit_arrays.py`)
- Phase summary table in `development-phases-block9.md` — fixed (Phases 83-88 status/counts updated)

### 7. Performance Sanity

Full suite: 188.65s (3:08). No regression from Phase 87. `enable_soa=False` default means zero runtime impact on existing scenarios.

### 8. Summary

- **Scope**: Under target (~60% of spec) — descoped items well-justified
- **Quality**: High — clean types, slots, docstrings, conventions followed
- **Integration**: Fully wired — battle loop, FOW, CalibrationSchema
- **Deficits**: 3 items (1 medium, 2 low)
- **Action items**: D88.2 (end-to-end FOW test) deferred to Phase 89 or standalone fix. D88.4 (project-structure) fixed. D88.1 (ammo field) documented.
