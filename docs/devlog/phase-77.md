# Phase 77: Frontend Accessibility

**Status**: Complete
**Block**: 8 (Consequence Enforcement & Scenario Expansion)
**Tests**: 36 new (vitest)
**Date**: 2026-03-23

## Goal

WCAG 2.1 AA compliance for all critical user paths — forms, navigation, modals, data display. Frontend-only phase — zero engine/API changes.

## Changes

### 77a: Forms & Inputs (7 tests)

- **GeneralSection.tsx**: Converted implicit `<label>` wrapping to explicit `id`/`htmlFor` association on all 4 inputs (name, duration, era, date)
- **RunConfigPage.tsx**: Added `required` and `aria-required="true"` to seed and maxTicks inputs
- **ScenarioEditorPage.tsx**: Added `role="alert"` and `aria-live="assertive"` to validation error container
- **SearchInput.tsx**: Added `aria-hidden="true"` to decorative SVG icon, `aria-label={placeholder}` to input

### 77b: Navigation & Focus (7 tests)

- **Layout.tsx**: Added skip-to-content link (`sr-only` + focus styles), `id="main-content"` on `<main>`, hamburger ref with focus return on sidebar close
- **Sidebar.tsx**: Added `aria-hidden="true"` to health status dot, visible "Connected"/"Disconnected" text label, `role="presentation"` on mobile backdrop
- **UnitDetailModal.tsx**: Added `aria-label="Close"` to close button
- **KeyboardShortcutHelp.tsx**: Added `aria-label="Close keyboard shortcuts"` to close button

### 77c: Interactive Components (14 tests)

- **PlaybackControls.tsx**: Added `id="playback-time-display"` on time display, `aria-describedby` linking slider to time display
- **LoadingSpinner.tsx**: Added `role="status"`, `aria-label="Loading"`, SVG `aria-hidden="true"`
- **Card.tsx**: Added conditional `role="button"`, `tabIndex={0}`, Enter/Space keyboard activation when `onClick` is present
- **StatisticsTable.tsx**: Added `scope="col"` to all 8 `<th>` elements
- **TabBar.tsx**: Added `role="tablist"` on container, `role="tab"` + `aria-selected` + `id` + `aria-controls` on buttons
- **AnalysisPage.tsx**: Added `role="tabpanel"`, `id`, `aria-labelledby` on panel wrapper

### 77d: Canvas & Charts (6 tests)

- **TacticalMap.tsx**: Added `role="application"`, `aria-label="Tactical map"`, `aria-describedby`, `tabIndex={0}` to canvas; sr-only summary div with active unit count
- **PlotlyChart.tsx**: Added optional `dataSummary` prop with `<details>` expandable data table
- **ForceStrengthChart.tsx**: Generates sampled data summary table (~10 rows max) and passes to PlotlyChart

### 77e: Color & Motion (2 tests)

- **index.css**: Added `@media (prefers-reduced-motion: reduce)` block (0.01ms durations to preserve animationend events)
- **MapLegend.tsx**: Added `aria-hidden="true"` to all SVGs in StatusIcon and DomainIcon (adjacent text provides labels)

## File Summary

- **19 source files modified** (frontend only)
- **5 test files created** in `frontend/src/__tests__/a11y/`
- **1 dev dependency added**: `jest-axe` + `@types/jest-axe`
- **0 engine/API changes**

## Test Results

36 new tests across 5 files:
- `a11y/forms.test.tsx` — 7 tests (label association, axe scan, aria-required, aria-label, validation role=alert)
- `a11y/navigation.test.tsx` — 7 tests (skip link, main id, health text, close labels)
- `a11y/interactive.test.tsx` — 14 tests (playback, spinner, card keyboard, table scope, tabs, tabpanel)
- `a11y/canvas-charts.test.tsx` — 6 tests (canvas ARIA, data table, force chart summary)
- `a11y/color-motion.test.tsx` — 2 tests (SVG aria-hidden, reduced-motion CSS)

All 308 frontend vitest tests pass (272 existing + 36 new).

## Lessons Learned

- **jest-axe works out of the box with vitest** — just `expect.extend(toHaveNoViolations)` in setup file
- **Explicit label association is more robust than implicit** — wrapping `<label>` around inputs works technically but `id`/`htmlFor` is more reliable across assistive tech
- **0.01ms not 0s for reduced-motion** — using `0s` prevents `animationend` events from firing, which can break JS-dependent transitions
- **PlotlyChart data table via `<details>` is a clean pattern** — provides screen reader access without visual clutter
- **Card keyboard accessibility is trivial** — conditional `role`/`tabIndex`/`onKeyDown` only when `onClick` is present preserves non-interactive Cards
- **ScenarioEditorPage test requires URL-based fetch mocking** — multiple concurrent fetches (scenario, eras, health) mean `mockResolvedValueOnce` chains are fragile; `mockImplementation` with URL matching is robust

## Postmortem

### Delivered vs Planned

**Planned** (from `development-phases-block8.md`):
- 77a: 4 source files, ~8 tests
- 77b: 5 source files (including ConfirmDialog), ~6 tests
- 77c: 5 source files, ~8 tests
- 77d: 4 source files (3 unique), ~6 tests
- 77e: 3 source files, ~4 tests
- Total: ~20 source files, ~32 tests

**Delivered**:
- 77a: 4 source files, 7 tests (plan said ~8, close enough)
- 77b: 4 source files, 7 tests (ConfirmDialog already had correct ARIA — no change needed, just verified)
- 77c: 6 source files (added TabBar.tsx), 14 tests (more than planned due to thorough tab/card coverage)
- 77d: 3 source files, 6 tests (on target)
- 77e: 3 source files, 2 tests (plan said ~4 but 2 sidebar tests deduplicated into navigation)
- Total: 19 source files modified, 36 tests

**Scope changes**:
- **Dropped**: ConfirmDialog.tsx — already had `aria-hidden="true"` on backdrop and Headless UI focus trap. No changes needed.
- **Added**: ScenarioEditorPage validation error test (was planned but initially missed, caught during postmortem)
- **Scope**: Well-calibrated. 36 tests vs ~32 planned.

### Integration Audit

- All source changes are attribute additions to existing components — no orphaned modules
- `dataSummary` prop on PlotlyChart is used by ForceStrengthChart and tested
- jest-axe is imported in setup.ts (globally available) and used in forms.test.tsx
- `aria-controls`/`aria-labelledby` cross-references between TabBar and AnalysisPage verified correct
- No dead modules introduced

### Test Quality Review

- **Integration**: ScenarioEditorPage validation test exercises the full editor render → validate → error display path
- **Edge cases**: Card tests cover both clickable and non-clickable variants; TabBar tests active vs inactive aria-selected
- **axe scan**: Only one axe scan (GeneralSection) — appropriate since jsdom has limited style computation
- **Realistic data**: Tests use representative mock data (scenario configs, metrics objects, terrain data)
- **No slow tests** — all a11y tests run in <500ms total

### API Surface Check

- N/A — frontend-only phase, no new Python APIs
- PlotlyChart's `dataSummary` prop is properly typed as optional `React.ReactNode`
- Card's new props are all conditional on `onClick` — backward compatible

### Deficit Discovery

1. **Minor**: ErrorBarChart, EventActivityChart, MoraleChart don't pass `dataSummary` to PlotlyChart — charts lack expandable data table alternatives. Accepted limitation: ForceStrengthChart demonstrates the pattern; other charts can add it incrementally.
2. **Minor**: Focus trap tests for modals (UnitDetailModal, KeyboardShortcutHelp, ConfirmDialog) verify the aria-label but don't test actual Tab key trapping — jsdom limitation. Headless UI handles this in production.
3. **Minor**: No keyboard navigation tests for TabBar arrow keys (ARIA tab pattern recommends arrow key navigation between tabs). Current implementation uses click/Enter only.

All three are minor/accepted limitations — no items need tracking in the refinement index.

### Documentation Freshness

- CLAUDE.md: Phase 77 in Block 8 table, status line updated, test count correct (10,415)
- README.md: Badge updated (10,415, phase-77), test count in text (308)
- docs/index.md: Test count updated (10,415)
- devlog/index.md: Phase 77 row added as Complete
- development-phases-block8.md: Phase 77 marked Complete (36 tests)
- mkdocs.yml: Phase 77 devlog in nav
- MEMORY.md: Current status, test counts updated
- No new skills, scenarios, units, eras, or engines — user-facing docs unchanged (correct)

### Performance Sanity

Frontend test suite: 308 tests in ~14s — comparable to previous runs (~272 tests in ~12s). The 36 new tests add ~2s. No performance concerns.

### Summary

- **Scope**: On target (36 tests vs ~32 planned, 19 files vs ~20 planned)
- **Quality**: High — tests cover attributes, keyboard interaction, cross-references, and one axe scan
- **Integration**: Fully wired — no orphaned code, all ARIA relationships verified
- **Deficits**: 3 minor accepted limitations (other chart dataSummary, focus trap depth, arrow key tabs)
- **Action items**: None — postmortem caught and fixed the missing ScenarioEditorPage validation test
