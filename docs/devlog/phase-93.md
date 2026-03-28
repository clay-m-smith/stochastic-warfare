# Phase 93: Results Dashboard Depth

**Status**: Complete
**Block**: 10 (UI Depth & Engine Exposure)
**Tests**: 14 (frontend vitest)

## What Was Built

Frontend components consuming the Phase 92 analytics endpoints. Four new Plotly chart components, an analytics summary card on the ResultsTab, TanStack Query hooks, and TypeScript types. Transforms the run results page from "what happened" to "why it happened."

### 93a: API Client & Types

- `frontend/src/types/analytics.ts` — TypeScript interfaces mirroring Phase 92 Pydantic response models (CasualtyAnalytics, SuppressionAnalytics, MoraleAnalytics, EngagementAnalytics, AnalyticsSummary)
- `frontend/src/api/analytics.ts` — 5 fetch functions using `apiGet<T>()` pattern with URLSearchParams for query params
- `frontend/src/hooks/useAnalytics.ts` — 5 TanStack Query hooks with `staleTime: 30_000` (analytics don't change for completed runs)

### 93b: Casualty & Engagement Charts

- `CasualtyBreakdownChart.tsx` — Stacked bar chart: casualties by weapon/cause, grouped by side. Uses `getSideColor()` for side-aware coloring. Collapsible data summary table.
- `EngagementSummaryChart.tsx` — Horizontal bar chart: engagement types ranked by count with hit rate annotations. Dynamic height based on type count.

### 93c: Suppression & Morale Charts

- `SuppressionChart.tsx` — Line chart with fill showing suppressed unit count over time. Peak annotation with arrow. Rout cascade count below chart.
- `MoraleDistributionChart.tsx` — Stacked area chart showing morale state distribution (steady/shaken/broken/routed/surrendered) over time. 5 color-coded traces with 50% opacity fills.

### 93d: Analytics Summary Card

ResultsTab enhanced with `useAnalyticsSummary` hook. Shows 6 StatCards: Total Engagements, Hit Rate, Total Casualties, Dominant Weapon, Peak Suppressed, Rout Cascades. Only fetches when run status is "completed". Loading spinner during fetch, silent fallback on error.

### 93e: ChartsTab Wiring

All 4 new charts wired into ChartsTab below existing charts. Uses single `useAnalyticsSummary` fetch to avoid 4 separate API calls. Charts receive `layoutOverrides` and `onClick` for cross-chart tick sync.

### Unplanned: TS Test Fixes

Fixed 6 existing test files with incomplete mock data (missing `SideForces.disabled` field and `MetricStats.n` field). These caused `tsc --noEmit` to fail.

## Design Decisions

1. **Single analytics fetch** — ChartsTab uses `useAnalyticsSummary` (one API call) rather than 4 individual hooks, reducing network requests.
2. **Conditional analytics fetch** — ResultsTab only fetches analytics when `run.status === 'completed'`, avoiding 409 errors for pending/running runs.
3. **PlotlyChart wrapper pattern** — All new charts follow the established pattern: accept `layoutOverrides` + `onClick` props, use `dataSummary` for collapsible data tables.
4. **Dynamic height** — EngagementSummaryChart height scales with number of engagement types: `Math.max(200, 50 + types.length * 30)`.
5. **Morale colors** — Steady=#22c55e (green), Shaken=#eab308 (yellow), Broken=#f97316 (orange), Routed=#ef4444 (red), Surrendered=#6b7280 (gray). Uses `fillcolor` with 50% opacity hex suffix.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `frontend/src/types/analytics.ts` | New | ~60 |
| `frontend/src/api/analytics.ts` | New | ~45 |
| `frontend/src/hooks/useAnalytics.ts` | New | ~55 |
| `frontend/src/components/charts/CasualtyBreakdownChart.tsx` | New | ~70 |
| `frontend/src/components/charts/EngagementSummaryChart.tsx` | New | ~65 |
| `frontend/src/components/charts/SuppressionChart.tsx` | New | ~65 |
| `frontend/src/components/charts/MoraleDistributionChart.tsx` | New | ~70 |
| `frontend/src/pages/runs/tabs/ChartsTab.tsx` | Modified | +15 |
| `frontend/src/pages/runs/tabs/ResultsTab.tsx` | Modified | +30 |
| `frontend/src/__tests__/api/analytics.test.ts` | New | ~85 |
| `frontend/src/__tests__/components/charts/CasualtyBreakdownChart.test.tsx` | New | ~30 |
| `frontend/src/__tests__/components/charts/EngagementSummaryChart.test.tsx` | New | ~30 |
| `frontend/src/__tests__/components/charts/SuppressionChart.test.tsx` | New | ~35 |
| `frontend/src/__tests__/components/charts/MoraleDistributionChart.test.tsx` | New | ~30 |
| 6 existing test files | Modified | +`disabled: 0` / +`n: 10` |

## Known Limitations

- Group-by toggle not implemented for CasualtyBreakdownChart (planned in spec, deferred — API supports it, UI doesn't expose it yet)
- Morale distribution timeline only shows ticks where MoraleStateChangeEvent occurred — frontend should interpolate for smooth visualization

---

## Postmortem

### 1. Delivered vs Planned

| Item | Planned | Delivered | Notes |
|------|---------|-----------|-------|
| 93a: Types + API client + hooks | 3 files | 3 files | Exact match |
| 93b: Casualty + Engagement charts | 2 charts | 2 charts | Exact match (group-by toggle deferred) |
| 93c: Suppression + Morale charts | 2 charts | 2 charts | Exact match |
| 93d: Analytics summary card | ResultsTab mod | ResultsTab mod | Exact match |
| 93e: ChartsTab wiring | ChartsTab mod | ChartsTab mod | Exact match |
| Tests | ~17 | 14 (8 new + 6 fixes) | Slightly under — fewer tests, but all components covered |
| TS test fixes | Not planned | 6 files | Fixed missing `disabled`/`n` fields in mock data |

**Verdict**: On target. All planned deliverables shipped plus unplanned TS fix cleanup.

### 2. Integration Audit

| Check | Status |
|-------|--------|
| analytics.ts API client imported by hooks | PASS |
| useAnalytics hooks imported by ChartsTab + ResultsTab | PASS |
| All 4 chart components imported and rendered in ChartsTab | PASS |
| Analytics summary card renders in ResultsTab | PASS |
| TypeScript types imported by API client, hooks, and charts | PASS |
| No dead/orphaned files | PASS |

### 3. Test Quality

- API client tests: mock fetch, verify URL construction and response parsing
- Chart tests: mock PlotlyChart, verify rendering and empty states
- All tests follow existing patterns (vi.mock, renderWithProviders, screen queries)
- No slow tests — all mock-based

### 4. API Surface

- All new exports are functions (no classes, no global state)
- Full TypeScript types on all props interfaces
- No bare `print()`/`console.log()`

### 5. Deficit Discovery

- D93.1 (Low): Group-by toggle for CasualtyBreakdownChart not implemented — API supports `group_by` param but UI hardcodes default

### 6. Performance Sanity

- Frontend tests: 330 passed in 14.39s (was 316 in ~similar time)
- `tsc --noEmit`: 0 errors (was 9 errors before fixes)
- `npm run build`: successful, 29.93s

### 7. Summary

- **Scope**: On target
- **Quality**: High — clean TS, all tests pass, build succeeds
- **Integration**: Fully wired
- **Deficits**: 1 low (group-by toggle deferred)
- **Action items**: Lockstep documentation update
