# Phase 75: Simulation Core & Domain Unit Tests

**Block**: 8 (Consequence Enforcement)
**Status**: Complete
**Tests added**: 293

## Summary

Pure test-addition phase — 293 new unit tests across 15 test files covering simulation engine private methods, movement domain engines, terrain subsystems, and logistics engines. Zero source code changes. Follows the Phase 74 pattern of lightweight SimpleNamespace mocks and shared conftest factories.

## What Was Built

### 75a: Battle.py Private Method Tests (82 tests, 2 files)

- **`tests/unit/simulation/test_battle_pure_functions.py`** — 52 tests covering 15 module-level pure functions: `_compute_weather_pk_modifier`, `_compute_night_modifiers`, `_compute_crosswind_penalty`, `_compute_wbgt`, `_compute_wind_chill`, `_compute_rain_detection_factor`, `_get_unit_position`, `_get_unit_signature`, `_infer_melee_type`, `_infer_missile_type`, `_movement_target`, `_nearest_enemy_dist`, `_should_hold_position`, `_standoff_range`
- **`tests/unit/simulation/test_battle_static_methods.py`** — 30 tests covering BattleManager static methods: `_apply_deferred_damage`, `_find_unit_side`, `_get_unit_morale_level`, `_get_unit_supply_level`, `_build_assessment_summary`

### 75b: Engine.py Private Method Tests (38 tests, 3 files)

- **`tests/unit/simulation/test_engine_event_handlers.py`** — 14 tests: `_find_unit_by_id`, `_handle_return_to_duty`, `_handle_equipment_breakdown`, `_handle_maintenance_completed`
- **`tests/unit/simulation/test_engine_resolution.py`** — 14 tests: `_forces_within_closing_range`, `_update_resolution`, `_set_resolution`, `_compute_battle_positions`, `_snapshot_unit_cells`
- **`tests/unit/simulation/test_engine_sigint_victory.py`** — 10 tests: `_evaluate_victory`, `_fuse_sigint`

### 75c: Domain Module Tests (127 tests, 8 files)

- **`tests/unit/movement/test_cavalry.py`** — 22 tests: charge phases, fatigue, rally, state
- **`tests/unit/movement/test_convoy.py`** — 22 tests: formation, stragglers, wolf pack, depth charges, state
- **`tests/unit/movement/test_formation_ancient.py`** — 20 tests: 7 formation types, transitions, modifiers, state
- **`tests/unit/movement/test_formation_napoleonic.py`** — 18 tests: 4 formation types, transitions, modifiers, state
- **`tests/unit/movement/test_naval_oar.py`** — 18 tests: rowing speeds, fatigue, ramming, boarding, state
- **`tests/unit/movement/test_events.py`** — 3 tests: frozen dataclass validation
- **`tests/unit/terrain/test_trenches.py`** — 14 tests: STRtree queries, cover, movement, bombardment, state
- **`tests/unit/terrain/test_data_pipeline.py`** — 10 tests: BoundingBox, SRTM tiles, cache keys

### 75d: Supporting Simulation Module Tests (46 tests, 4 files)

- **`tests/unit/logistics/test_foraging.py`** — 14 tests: zones, capacity, operations, state
- **`tests/unit/logistics/test_production.py`** — 10 tests: facilities, condition, output, state
- **`tests/unit/simulation/test_aggregation.py`** — 10 tests: config, snapshot, aggregate, state
- **`tests/unit/simulation/test_calibration_schema.py`** — 12 tests: dead keys, morale routing, side prefix/suffix, get()

## Design Decisions

1. **SimpleNamespace mocks over real objects**: Real SimulationEngine requires too many dependencies. Private methods tested by binding the unbound method to a SimpleNamespace with only the required fields. This isolates the logic under test.

2. **Separate conftest per directory**: Each test directory gets its own `conftest.py` with domain-specific factories (cavalry engine, trench segment, etc.) following Phase 74 pattern.

3. **No duplication of existing coverage**: Functions already tested in Phase 40-72 test files (e.g., `_compute_terrain_modifiers` in test_phase41, `_score_target` in test_phase41) are NOT re-tested. Phase 75 covers only the 28+ untested functions.

4. **Aggregation requires Unit-like objects**: `AggregationEngine.aggregate()` calls `unit.get_state()`, accesses `speed`, `max_speed`, `domain` — needs richer mocks than other tests.

## File Inventory

| Type | Count | Files |
|------|-------|-------|
| `__init__.py` | 4 | simulation/, movement/, terrain/, logistics/ |
| `conftest.py` | 4 | simulation/, movement/, terrain/, logistics/ |
| Test files | 15 | 7 simulation, 6 movement, 2 terrain, 2 logistics |
| **Total** | **23** | |

## Lessons Learned

- **CalibrationSchema.get() routing is specific**: `morale_base_degrade_rate` (not `morale_degrade_rate`), side suffixes are `{side}_cohesion` (not `cohesion_{side}`), side prefixes are `target_size_modifier_{side}`.
- **Event base class requires timestamp+source**: All events inherit from `Event(timestamp, source)` — can't construct child events without these fields.
- **Cavalry charge transitions happen fast**: At 8 m/s gallop, a 100m charge covers the 50m→CHARGE threshold in 6s. To test exhaustion, need to force the charge to stay at gallop with a large distance.

## Postmortem

### Scope
**On target.** Plan called for ~293 tests; delivered 293. Correctly descoped environment/detection/morale directories (already covered by 200+ existing flat test files). Added deeper coverage of untested battle.py pure functions instead.

### Quality
**High.** All 293 tests pass. Deterministic PRNG seeding throughout. Consistent `pytest.approx()` use. Checkpoint round-trip tests on all engines with state. SimpleNamespace mock pattern keeps tests fast (0.47s for all 293).

Test quality review identified minor gaps:
- Some boundary assertions are loose (`phase in (TROT, GALLOP)` instead of exact phase)
- Empty-list edge cases missing for `_movement_target()`, equipment arrays
- Cross-modifier stacking (weather + night + wind applied together) not tested

These are test improvement opportunities for future phases, not source code deficits.

### Integration
**Fully wired.** All 4 `__init__.py`, 4 `conftest.py`, 15 test files properly discoverable. All conftest factory functions used by tests. Zero dead imports. Zero source changes.

### Deficits
**0 new deficits.** Test-only phase — no new source code, no new limitations.

### Performance
Full regression: 9,780 passed in 22 min (no change from Phase 74). Phase 75 tests alone: 0.47s.

### Documentation
All 8 lockstep docs verified: CLAUDE.md, README.md, docs/index.md, devlog/index.md, phase-75.md, development-phases-block8.md, mkdocs.yml, MEMORY.md.

### Action Items
None — phase is ready for commit.
