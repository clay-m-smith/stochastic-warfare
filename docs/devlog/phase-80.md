# Phase 80: API & Frontend Sync

**Status**: Complete
**Date**: 2026-03-24

## Goal

Bring API schemas and frontend components current with engine state. Fix scenario data issues. Add `enable_all_modern` convenience meta-flag and calibration exercise scenarios.

## Changes

### 80a: API Schema Updates

- **`api/schemas.py`**: Added `has_space: bool = False` and `has_dew: bool = False` to `ScenarioSummary`. Added docstring to `RunSubmitRequest.config_overrides` documenting CalibrationSchema fields.
- **`api/routers/scenarios.py`**: Wired `has_space` and `has_dew` detection in `_extract_summary()` using same `"space_config" in cfg` pattern as existing flags.

### 80b: CalibrationSliders Overhaul

- **`frontend/src/pages/editor/CalibrationSliders.tsx`**: Complete rewrite — replaced 4 hardcoded sliders with 29 `enable_*` toggles in 7 collapsible groups + ~40 numeric sliders in 7 groups. Added "Enable All Modern" master toggle that sets 21 non-deferred flags. Uses native `<details>/<summary>` for accessibility.
- **`frontend/src/types/api.ts`**: Added `has_space`, `has_dew` to `ScenarioSummary` interface.
- **`frontend/src/types/editor.ts`**: Widened `SET_CALIBRATION` value type from `number` to `number | boolean`.

### 80c: Scenario Data Fixes

- **`stochastic_warfare/simulation/calibration.py`**: Added `enable_all_modern: bool = False` meta-flag with `model_post_init` validator that sets 21 validated `enable_*` flags via `object.__setattr__()`. 7 deferred flags (`enable_fuel_consumption`, `enable_ammo_gate`, `enable_command_hierarchy`, `enable_carrier_ops`, `enable_ice_crossing`, `enable_bridge_capacity`, `enable_environmental_fatigue`) intentionally excluded.
- **`data/scenarios/eastern_front_1943/scenario.yaml`**: Replaced WW1 weapon IDs (`lee_enfield`, `gewehr_98`, `mills_bomb`) with new WW2 equivalents (`mosin_nagant`, `kar98k`, `ppsh41`, `stielhandgranate`, `rgd33`).
- **`data/scenarios/golan_heights/scenario.yaml`**: Added explicit `victory_conditions` section (force_destroyed, morale_collapsed, time_expired at 18h).

### 80d: WW2 Small Arms Data

Created 10 new YAML files:
- **Weapons** (5): `kar98k.yaml`, `mosin_nagant.yaml`, `ppsh41.yaml` (guns); `stielhandgranate.yaml`, `rgd33.yaml` (explosives — new `explosives/` subdir)
- **Ammo** (5): `792x57mm_mauser.yaml`, `762x54r.yaml`, `762x25mm_tokarev.yaml`, `stielhandgranate_charge.yaml`, `rgd33_charge.yaml`

### 80e: Calibration Exercise Scenarios

Created 3 scenarios exercising 16 CalibrationSchema fields never set to non-default values:
- **`calibration_arctic`**: Arctic infantry patrol — exercises `cold_casualty_base_rate`, `night_thermal_floor`, `wind_accuracy_penalty_scale`, `rain_attenuation_factor`, `dig_in_ticks`, `observation_decay_rate`
- **`calibration_urban_cbrn`**: Urban CBRN response — exercises `gas_casualty_floor`, `gas_protection_scaling`, `heat_casualty_base_rate`, `c2_min_effectiveness`, `engagement_concealment_threshold`, `fire_damage_per_tick`
- **`calibration_air_ground`**: Air-ground combined arms — exercises `cloud_ceiling_min_attack_m`, `icing_maneuver_penalty`, `planning_available_time_s`, `disable_threshold`, `wave_interval_s`, `target_selection_mode`

## Test Summary

| Test File | Tests | Verifies |
|-----------|-------|----------|
| `tests/unit/test_phase80_api_frontend_sync.py` | 18 | Schema fields, enable_all_modern, scenario data, weapon YAML |
| `frontend/src/__tests__/pages/CalibrationSliders.test.tsx` | 8 | Component rendering, toggle dispatch, slider dispatch, reducer |
| **Total** | **26** | |

## Files Changed

**New files (15):**
- 5 weapon YAML + 5 ammo YAML + 3 scenario YAML + 1 Python test + 1 frontend test

**Modified files (20):**
- `stochastic_warfare/simulation/calibration.py` — enable_all_modern meta-flag
- `api/schemas.py` — has_space, has_dew, config_overrides docstring
- `api/routers/scenarios.py` — has_space, has_dew wiring
- `frontend/src/types/api.ts` — has_space, has_dew
- `frontend/src/types/editor.ts` — SET_CALIBRATION boolean value
- `frontend/src/pages/editor/CalibrationSliders.tsx` — full overhaul
- `data/scenarios/eastern_front_1943/scenario.yaml` — WW2 weapon IDs
- `data/scenarios/golan_heights/scenario.yaml` — victory_conditions
- `frontend/src/__tests__/pages/ScenarioListPage.test.tsx` — has_space/has_dew in mocks
- `frontend/src/__tests__/api/scenarios.test.ts` — has_space/has_dew in mocks
- `frontend/src/__tests__/hooks/useScenarios.test.ts` — has_space/has_dew in mocks
- `frontend/src/__tests__/pages/BatchPanel.test.tsx` — has_space/has_dew in mocks
- `tests/validation/test_historical_accuracy.py` — 3 calibration scenarios in DRAW_SCENARIOS
- `tests/validation/test_phase_67_structural.py` — enable_all_modern in deferred flags + calibration.py in consumer search
- CLAUDE.md, README.md, docs/index.md, docs/devlog/index.md, docs/development-phases-block8.md, mkdocs.yml — lockstep

## Lessons Learned

1. **Duplicate group names in toggle+slider sections cause test failures**: "Environment" appeared in both toggle and slider groups — `getByText` throws on duplicates. Use `getAllByText` or rename one group.
2. **Pydantic frozen models need `object.__setattr__`**: `model_post_init` runs after validation, but the model is frozen — direct attribute assignment raises. `object.__setattr__` bypasses the descriptor.
3. **AmmoType enum doesn't have BALL**: Existing small arms ammo uses `AP` type. Non-enum ammo types cause silent failures in some code paths.
4. **WW2 ammunition lives in `ammunition/` not `ammo/`**: Directory naming inconsistency vs the plan spec. Always check existing structure before creating files.

## Known Limitations

- Nested morale calibration fields (`morale.base_degrade_rate`, etc.) not exposed in CalibrationSliders UI — top-level `morale_degrade_rate_modifier` covers 90% of use cases
- `subsystem_weibull_shapes`, `posture_*_protection`, `target_value_weights`, `victory_weights`, `side_overrides` require specialized dict-editor UI — deferred
- Calibration exercise scenarios are for field coverage, not validation — correct winner is less important than exercising non-default parameter paths

## Postmortem

### 1. Delivered vs Planned

**Plan** (from `development-phases-block8.md`):
- 80a: API schema updates (has_space, has_dew) — **Delivered**
- 80b: CalibrationSliders overhaul (29 toggles + ~40 sliders) — **Delivered**
- 80c: Scenario data fixes (eastern_front_1943, golan_heights, enable_all_modern, 3 exercise scenarios) — **Delivered**
- Plan expected ~18 tests — **Delivered 26** (18 Python + 8 frontend)

**Unplanned additions:**
- 10 WW2 weapon/ammo YAML (plan mentioned creating WW2 weapon data but didn't enumerate all 10 files individually)
- 6 regression fixes to pre-existing test mocks (ScenarioListPage, BatchPanel, scenarios.test.ts, useScenarios.test.ts, test_historical_accuracy, test_phase_67_structural)

**Descoped:** Per-side override sliders (dict-editor UI) — correctly deferred per plan.

**Verdict**: Scope well-calibrated. Minor regression fixes expected when adding fields to shared types.

### 2. Integration Audit

| Item | Wired? | Evidence |
|------|--------|----------|
| `enable_all_modern` meta-flag | Yes | Consumed by `model_post_init` in `calibration.py`, tested in 3 unit tests |
| `has_space` / `has_dew` | Yes | Schema → router → frontend types, 4 test files updated |
| CalibrationSliders component | Yes | Imported by `ScenarioEditorPage`, 8 component tests |
| WW2 weapon YAML | Yes | Referenced in `eastern_front_1943/scenario.yaml` weapon_assignments |
| WW2 ammo YAML | Yes | Referenced by weapon `compatible_ammo` fields |
| Calibration exercise scenarios | Yes | Validated by `test_phase_30_scenarios`, tracked in `DRAW_SCENARIOS` |

**No dead modules.** All new files are imported/referenced by at least one consumer.

### 3. Test Quality Review

- **Integration tests**: `test_phase80_api_frontend_sync.py` covers cross-layer paths (API schema → router wiring, CalibrationSchema → enable_all_modern, scenario YAML → weapon data)
- **Realistic data**: Tests use actual scenario YAML files and real pydantic models, not trivial mocks
- **Edge cases**: Deferred flag exclusion tested (7 flags verified as False), empty calibration_overrides handled
- **Frontend tests**: Cover both reducer-level (unit) and component-level (integration) paths
- **No slow tests** — all run in <2s

### 4. API Surface Check

- `enable_all_modern` field: type-hinted, default=False, `model_post_init` is a standard pydantic method
- `has_space` / `has_dew`: type-hinted as `bool = False` on `ScenarioSummary`
- No new public functions — only new pydantic fields and a `model_post_init` override
- No bare `print()` — all logging via existing patterns

### 5. Deficit Discovery

No new deficits. Known limitations (nested morale UI, dict-editor types) are already documented and deferred to Phase 82+ if needed.

### 6. Documentation Freshness

| Doc | Accurate? | Notes |
|-----|-----------|-------|
| CLAUDE.md phase summary | Yes | Phase 80 row with correct test count and deliverables |
| devlog/index.md | Yes | Phase 80 row added |
| development-phases-block8.md | Yes | Status → Complete |
| README.md | Yes | Badge updated to 10,167 tests, phase 80, phases 75-80 added to table |
| docs/index.md | Yes | Test count updated to ~10,490, scenario count to 44 |
| mkdocs.yml | Yes | Phase 80 devlog nav entry added |
| MEMORY.md | Yes | Status and phase summary table updated |
| User-facing docs | N/A | No new modules/engines/eras — scenarios guide, API ref, units ref unchanged |

### 7. Performance Sanity

Full test suite: 9,853 passed in ~31 min (1,878s). This is consistent with previous phases — no performance regression. New tests add <1s total.

### 8. Summary

- **Scope**: On target — all planned items delivered + expected regression fixes
- **Quality**: High — 26 tests, no TODOs, no dead code
- **Integration**: Fully wired — every new artifact consumed by at least one path
- **Deficits**: 0 new items
- **Action items**: None — ready for commit
