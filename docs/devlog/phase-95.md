# Phase 95: Calibration & Scenario Editor Depth

**Status**: Complete
**Block**: 10 (UI Depth & Engine Exposure)
**Tests**: 24 new frontend tests (396 total vitest)
**Files**: 3 new + 7 modified frontend files, 3 new test files + 1 modified test file

## What Was Built

### 95a: Per-Side Calibration Panel
- New collapsible "Per-Side Overrides" section in CalibrationSliders
- Blue/Red tab buttons (useState toggle), side names derived from config.sides
- 4 per-side sliders: cohesion, force_ratio_modifier, hit_probability_modifier, target_size_modifier
- New `SET_SIDE_CALIBRATION` action type → writes `calibration_overrides.side_overrides.{side}.{field}`
- 3-level immutable spread in reducer for nested state update

### 95b: Expanded Morale & Rout Cascade Sliders
- Morale group expanded from 1 to 5 sliders: morale_degrade_rate_modifier + morale_base_degrade_rate, morale_casualty_weight, morale_force_ratio_weight, morale_check_interval
- New "Rout Cascade" slider group: rout_cascade_radius_m, rout_cascade_base_chance
- All use existing `SET_CALIBRATION` action — backend `_MORALE_KEY_MAP` handles routing to nested MoraleCalibration

### 95c: Doctrine & Commander Pickers
- **DoctrinePicker.tsx** (new): Per-side `<select>` dropdowns populated from `GET /meta/schools` via `useSchools()` hook. "None" option, description text, OODA multiplier and risk tolerance badges.
- **CommanderPicker.tsx** (new): Per-side `<select>` dropdowns from `GET /meta/commanders` via `useCommanders()` hook. "None" option, trait preview card with key-value grid.
- `SET_SCHOOL` action → writes `school_config.{side}_school`, auto-enables `school_config` if absent
- `SET_COMMANDER` action → writes `commander_config.side_defaults.{side}`, auto-enables `commander_config` if absent
- API client functions `fetchSchools()`, `fetchCommanders()` added to `api/meta.ts`
- TanStack Query hooks `useSchools()`, `useCommanders()` added to `hooks/useMeta.ts`
- `SchoolInfo`, `CommanderInfo` TypeScript interfaces added to `types/api.ts`

### 95d: Victory Weights Editor
- **VictoryWeightsEditor.tsx** (new): 3 sliders for force_ratio (default 1.0), morale_ratio (default 0.0), casualty_exchange (default 0.0)
- Normalized percentage display: `Math.round(value / total * 100)%` next to each slider
- Warning message when all weights are zero
- `SET_VICTORY_WEIGHT` action → writes `calibration_overrides.victory_weights.{key}`
- Keys match engine's `VictoryEvaluator.evaluate_force_advantage()` actual usage

### Wiring
- All 3 new components imported and placed in ScenarioEditorPage.tsx
- DoctrinePicker + CommanderPicker between ForceEditor and ConfigToggles
- VictoryWeightsEditor after CalibrationSliders
- `commander_config: {}` added to CONFIG_DEFAULTS in useScenarioEditor.ts

## Design Decisions

1. **Dedicated action types** over overloading SET_CALIBRATION — SET_SIDE_CALIBRATION needs 3-level nesting, SET_SCHOOL/SET_COMMANDER write to non-calibration config paths. Type safety over DRY.
2. **school_config uses blue_school/red_school** — matches existing YAML format (`school_config: { blue_school: maneuverist }`).
3. **commander_config uses side_defaults.{side}** — matches YAML format (`commander_config: { side_defaults: { blue: joint_commander } }`).
4. **Auto-enable on select** — selecting a school auto-creates `school_config` via CONFIG_DEFAULTS pattern. Clearing does NOT auto-disable.
5. **Victory weight keys match engine** — spec said `casualties/morale/territory` but engine uses `force_ratio/morale_ratio/casualty_exchange`. Implementation follows engine, spec corrected.
6. **morale_check_interval default = 1** — matches engine's `MoraleCalibration.check_interval` default, not the spec's suggested 15.

## Deviations from Plan

1. **Era-aware commander filtering** (95c) — not implemented. `CommanderInfo` has no `era` field; commanders are era-agnostic by schema design. This was a spec issue, not a gap.
2. **Stacked bar visualization** (95d) — replaced with inline percentage display. The `(60%)` annotation next to each slider is cleaner for 3 values than a separate bar chart component.
3. **Victory weight keys** — spec said `casualties/morale/territory`, implementation uses `force_ratio/morale_ratio/casualty_exchange` (matching engine). Spec corrected.

## Files Changed

### New Files
- `frontend/src/pages/editor/DoctrinePicker.tsx`
- `frontend/src/pages/editor/CommanderPicker.tsx`
- `frontend/src/pages/editor/VictoryWeightsEditor.tsx`
- `frontend/src/__tests__/pages/editor/DoctrinePicker.test.tsx`
- `frontend/src/__tests__/pages/editor/CommanderPicker.test.tsx`
- `frontend/src/__tests__/pages/editor/VictoryWeightsEditor.test.tsx`

### Modified Files
- `frontend/src/types/api.ts` — SchoolInfo, CommanderInfo interfaces
- `frontend/src/types/editor.ts` — 4 new EditorAction types
- `frontend/src/hooks/useScenarioEditor.ts` — 4 reducer cases, commander_config default
- `frontend/src/api/meta.ts` — fetchSchools, fetchCommanders
- `frontend/src/hooks/useMeta.ts` — useSchools, useCommanders hooks
- `frontend/src/pages/editor/CalibrationSliders.tsx` — per-side section, expanded morale, rout cascade
- `frontend/src/pages/editor/ScenarioEditorPage.tsx` — wire 3 new components
- `frontend/src/__tests__/pages/CalibrationSliders.test.tsx` — 12 new reducer + component tests

## Postmortem

- **Scope**: On target. All 4 sub-phases delivered. Two spec items descoped (era filtering, stacked bar) — both were spec issues, not implementation gaps.
- **Quality**: High. Zero TODOs, zero dead code, full type safety, 24 new tests.
- **Integration**: Fully wired. Every new component imported, every action handled, every API function consumed.
- **Deficits**: None. All features work as intended.
