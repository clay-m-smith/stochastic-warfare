# Phase 37 — Integration Fixes & E2E Validation

**Status**: Complete
**Block**: 4 (Tightening)
**Tests**: 70 new (24 Python unit + 41 E2E parametrized + 5 frontend vitest)
**Files**: 6 modified + 6 new

## Summary

Phase 37 fixes three critical integration bugs that surface during real web UI use and adds an E2E smoke test across all 41 scenarios. Zero new engine subsystems — purely wiring and fixing existing code.

## What Was Built

### 37a: Bug Fixes (6 modified files)

**Bug 1 — config_overrides never applied** (`api/run_manager.py`):
- `_run_sync()` received `config_overrides` but never merged them into the YAML dict
- Added `_apply_overrides()` static method for recursive deep merge (nested dicts merge, scalars replace, lists replace)
- Called after `yaml.safe_load()` and before `ScenarioLoader.load()`

**Bug 2 — Reinforcement events not published** (`stochastic_warfare/simulation/campaign.py` + `frontend/src/lib/eventProcessing.ts`):
- `check_reinforcements()` logged arrivals but published no event — frontend force charts never increased
- Added `ReinforcementArrivedEvent` frozen dataclass (side, unit_count, unit_types) in campaign.py
- Published via EventBus with safe `getattr(ctx, "clock", None)` fallback for backward compat with SimpleNamespace test mocks
- Frontend `buildForceTimeSeries()` now handles both destruction and reinforcement events in a single sorted pass

**Bug 3 — DEW battle loop wiring** (`stochastic_warfare/simulation/battle.py` + `stochastic_warfare/combat/engagement.py`):
- `_execute_engagements()` called `execute_engagement()` directly — DEW weapons used ballistic physics instead of Beer-Lambert
- Changed to call `route_engagement()` which dispatches to DEW engine for `DIRECTED_ENERGY` weapons
- Detects DEW via `parsed_category() == WeaponCategory.DIRECTED_ENERGY` + `beam_power_kw > 0` (laser) vs `== 0` (HPM)
- Updated `route_engagement()` to propagate `HitResult` from DEW engine results (was missing — needed for damage chain)
- DEW hits in battle loop result in destruction (thermal/EMP kill)

### 37b: Tests (4 new test files, 29 tests)

| File | Tests | Covers |
|------|-------|--------|
| `tests/api/test_config_overrides.py` | 8 | `_apply_overrides` deep merge (flat, nested, list, empty, type changes) |
| `tests/unit/test_reinforcement_events.py` | 8 | ReinforcementArrivedEvent publishing (arrival, source, waves, no-clock fallback) |
| `tests/unit/test_dew_battle_wiring.py` | 8 | DEW routing via route_engagement, HitResult propagation, category detection |
| `frontend/src/__tests__/lib/eventProcessing.reinforcement.test.ts` | 5 | Force chart reinforcement handling (increment, mixed, unknown side, defaults) |

### 37c: E2E Smoke Test (1 new test file, 41 parametrized tests)

- `tests/e2e/test_scenario_smoke.py` — all 41 scenarios submitted via API
- 33 scenarios complete successfully within 20 ticks
- 8 scenarios xfail due to legacy YAML format (missing campaign schema fields: sides, terrain, date)
- Registered `e2e` marker in `pyproject.toml`, excluded from default test runs

## Design Decisions

1. **Event placed in campaign.py, not separate events file**: `ReinforcementArrivedEvent` lives alongside the code that publishes it. Avoids creating a new file for a single dataclass.

2. **`getattr(ctx, "clock", None)` for backward compat**: Existing tests use `SimpleNamespace` mocks without `clock`. Safe attribute access prevents `AttributeError` without requiring test updates. Follows Phase 25 pattern.

3. **HitResult propagation in route_engagement()**: The DEW wrapping in `route_engagement()` previously didn't populate `hit_result`. This meant the battle loop damage chain (which checks `result.hit_result.hit`) would never trigger for DEW. Fixed by creating a `HitResult` from `dew_result.pk` and `dew_result.hit`.

4. **E2E xfail for legacy scenarios**: 8 scenarios use a simpler YAML format (pre-campaign schema). Rather than masking failures, they're marked `xfail` to document the gap. Schema migration is a future task.

5. **Deep merge, not temp file**: Config overrides are merged into the dict in-memory rather than writing a temp YAML file. Simpler, no file cleanup needed.

## Deviations from Plan

The implementation followed a focused plan (3 bugs + E2E) rather than the full Phase 37 doc plan. Descoped items:

| Item | Reason | Status |
|------|--------|--------|
| `api/routers/meta.py` terrain-types-from-data | Not in focused plan | Deferred to 39d |
| `air_defense.py` ADUnitType.DEW routing | Not in focused plan | Deferred |
| Scenario YAML with dew_config | Not in focused plan | Deferred |
| DEWEngagementEvent subscriber | NOT NEEDED — SimulationRecorder subscribes to base Event | Closed |
| Scenario editor E2E tests | Not in focused plan | Deferred to 39a |

## Known Limitations

1. **8 legacy-format scenarios can't run through API**: 73_easting, bekaa_valley_1982, cbrn_chemical_defense, cbrn_nuclear_tactical, falklands_naval, golan_heights, gulf_war_ew_1991, test_scenario. These use a simpler YAML format without `sides`/`terrain`/`date` fields required by `CampaignScenarioConfig`.

2. **DEW hit = always destruction**: When a DEW weapon hits, the battle loop treats it as destruction. No partial damage / disable path. Acceptable for thermal/EMP kills but could be refined.

3. **No scenario exercises DEW in E2E**: No scenario YAML includes `dew_config`, so the DEW routing path is only tested at unit level, not in full simulation runs.

## Lessons Learned

- **`ModuleId` doesn't have `SIMULATION`**: Used `ModuleId.CORE` instead. Check enum values before using them in new event classes.
- **`AmmoState` uses `rounds_by_type` dict, not positional args**: Tests must construct via `AmmoState()` then populate `rounds_by_type[ammo_id]`. Don't guess constructor signatures.
- **SimpleNamespace test mocks need all accessed fields**: When new code accesses `ctx.clock`, every test mock must include it. `getattr()` is the safety net.
- **E2E tests find real issues**: 8 of 41 scenarios actually can't load through the API. This is exactly what smoke tests are for.
- **`route_engagement()` wrapping must be complete**: When wrapping a domain-specific result (DEWEngagementResult) into a generic result (EngagementResult), all fields needed by downstream consumers must be populated. The `hit_result` gap was a real integration bug.

## Postmortem

- **Scope**: Under — focused plan was smaller than full doc plan (3 bugs + E2E vs full DEW wiring + terrain types + E2E)
- **Quality**: High — tests cover edge cases, real engines used (not just mocks), E2E finds real issues
- **Integration**: Fully wired for what was delivered. ReinforcementArrivedEvent auto-captured by SimulationRecorder.
- **Performance**: No regression (125s test suite unchanged)
- **Deficits**: 1 new (legacy scenario format). 3 deferred from original plan (terrain types, AD DEW routing, scenario dew_config). These remain in the deficit index for future phases.

### Deficit Resolution

| Deficit | Origin | Status |
|---------|--------|--------|
| route_engagement() not called from battle.py | Phase 28.5 | **Resolved** |
| config_overrides accepted but not applied | Phase 32 | **Resolved** |
| Force time series assumes no reinforcements | Phase 34 | **Resolved** |
| DEWEngagementEvent has zero subscribers | Phase 28.5 | **Closed** (recorder catches via base Event) |
| dew_engine not used in simulation tick loops | Phase 28.5 | **Resolved** (routed via battle.py) |
| No scenario YAML references dew_config | Phase 28.5 | Deferred |
| ADUnitType.DEW not handled in air defense | Phase 28.5 | Deferred |
| GET /api/meta/terrain-types hardcoded | Phase 32 | Deferred to 39d |
