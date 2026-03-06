# Phase 34: Run Results & Analysis Dashboard

## Summary

Pure frontend phase delivering run detail pages with live WebSocket progress tracking, interactive Plotly charts from event data, battle narrative view, and Monte Carlo/comparison analysis. 65 new vitest tests, ~40 new files. Zero engine or API changes.

## What Was Built

### 34a: Run Detail + WebSocket
- **RunDetailPage** (`/runs/:runId`) — fetches run, shows status badge, metadata (seed, max_ticks, created/completed), tabbed interface for completed runs
- **RunProgressPanel** — live WebSocket tracking with ProgressBar, elapsed time, active unit counts per side, auto-invalidates query on completion
- **RunDeleteButton** — delete with ConfirmDialog confirmation, navigates back to run list
- **useWebSocket hook** — `useRunProgress(runId)` accumulates force history from WS tick messages, `useBatchProgress(batchId)` for batch iteration tracking
- **Extended API client** — `fetchRun`, `deleteRun`, `fetchRunEvents` (paginated with type filter), `fetchRunNarrative` (side/style params)
- **Extended hooks** — `useRun` (auto-refetch when pending/running), `useDeleteRun`, `useRunEvents`, `useRunNarrative`
- **RunListPage** — rows now clickable, navigate to `/runs/:runId`
- **Shared components**: ProgressBar, TabBar, ConfirmDialog, StatCard

### 34b: Interactive Charts
- **Event processing library** (`lib/eventProcessing.ts`) — pure functions: `buildForceTimeSeries`, `buildEngagementData`, `buildMoraleTimeSeries`, `buildEventCounts`
- **PlotlyChart wrapper** — lazy-loaded via `React.lazy` + `Suspense` with responsive sizing
- **ForceStrengthChart** — area chart, one trace per side (blue/red), tick vs active units
- **EngagementTimeline** — scatter plot, hits (green) vs misses (red), hover with attacker/target/weapon
- **MoraleChart** — step chart with unit selector (max 5 default, show all toggle)
- **EventActivityChart** — bar chart showing battle tempo (binned event counts)
- **ChartsTab** — fetches all events, transforms to chart data, renders in vertical stack
- **Dependencies**: `react-plotly.js` + `plotly.js-dist-min` + `@types/react-plotly.js`

### 34c: Narrative View
- **NarrativeTab** — side filter (All/Blue/Red), style toggle (Full/Summary/Timeline), whitespace-preserving narrative text, tick count display
- Re-fetches when filters change via TanStack Query caching

### 34d: Monte Carlo & Analysis
- **AnalysisPage** — replaced stub with three-tab interface: Batch MC | A/B Compare | Sensitivity Sweep
- **BatchPanel** — scenario select, iterations, base seed, max ticks; WS progress bar during execution; BatchResultsView on completion
- **BatchResultsView** — HistogramGrid (box plots per metric) + StatisticsTable
- **ComparePanel** — scenario, labels, JSON override text areas, num_iterations; ComparisonCharts (grouped bar) on completion
- **SweepPanel** — parameter name, comma-separated values; ErrorBarChart (scatter with error bars) on completion
- **Chart components**: HistogramGrid, StatisticsTable, ErrorBarChart, ComparisonCharts
- **API client**: `batch.ts` (submitBatch, fetchBatch), `analysis.ts` (runCompare, runSweep)
- **Hooks**: `useBatch.ts` (useSubmitBatch, useBatch), `useAnalysis.ts` (useCompare, useSweep)

## New Files (~45)

```
src/api/batch.ts
src/api/analysis.ts
src/hooks/useWebSocket.ts
src/hooks/useBatch.ts
src/hooks/useAnalysis.ts
src/lib/eventProcessing.ts
src/components/ProgressBar.tsx
src/components/TabBar.tsx
src/components/ConfirmDialog.tsx
src/components/StatCard.tsx
src/components/charts/PlotlyChart.tsx
src/components/charts/ForceStrengthChart.tsx
src/components/charts/EngagementTimeline.tsx
src/components/charts/MoraleChart.tsx
src/components/charts/EventActivityChart.tsx
src/components/charts/HistogramGrid.tsx
src/components/charts/StatisticsTable.tsx
src/components/charts/ErrorBarChart.tsx
src/components/charts/ComparisonCharts.tsx
src/pages/runs/RunDetailPage.tsx
src/pages/runs/RunSummaryCard.tsx
src/pages/runs/RunProgressPanel.tsx
src/pages/runs/RunDeleteButton.tsx
src/pages/runs/tabs/ResultsTab.tsx
src/pages/runs/tabs/ChartsTab.tsx
src/pages/runs/tabs/NarrativeTab.tsx
src/pages/runs/tabs/EventsTab.tsx
src/pages/analysis/BatchPanel.tsx
src/pages/analysis/BatchResultsView.tsx
src/pages/analysis/ComparePanel.tsx
src/pages/analysis/SweepPanel.tsx
src/__tests__/api/runs.test.ts
src/__tests__/api/batch.test.ts
src/__tests__/api/analysis.test.ts
src/__tests__/hooks/useWebSocket.test.ts
src/__tests__/hooks/useRun.test.ts
src/__tests__/lib/eventProcessing.test.ts
src/__tests__/pages/RunDetailPage.test.tsx
src/__tests__/pages/EventsTab.test.tsx
src/__tests__/pages/ChartsTab.test.tsx
src/__tests__/pages/NarrativeTab.test.tsx
src/__tests__/pages/AnalysisPage.test.tsx
src/__tests__/pages/BatchPanel.test.tsx
src/__tests__/components/charts/ForceStrengthChart.test.tsx
src/__tests__/components/charts/HistogramGrid.test.tsx
```

## Modified Files

| File | Change |
|------|--------|
| `src/App.tsx` | Added `/runs/:runId` route |
| `src/types/api.ts` | Added ~15 new interfaces (events, narrative, forces, batch, analysis, WebSocket) |
| `src/api/runs.ts` | Added fetchRun, deleteRun, fetchRunEvents, fetchRunNarrative |
| `src/hooks/useRuns.ts` | Added useRun, useDeleteRun, useRunEvents, useRunNarrative |
| `src/pages/runs/RunListPage.tsx` | Made table rows clickable |
| `src/pages/analysis/AnalysisPage.tsx` | Replaced stub with tabbed analysis dashboard |
| `src/lib/format.ts` | Added formatSeconds, formatPercent |
| `package.json` | Added react-plotly.js, plotly.js-dist-min, @types/react-plotly.js |

## Design Decisions

1. **Plotly over Chart.js/Recharts**: Plotly provides scatter, bar, box, and error bar charts with built-in zoom/pan/hover — all needed here. `plotly.js-dist-min` is ~1MB but code-split via `React.lazy`.
2. **Force time series from events**: Since the API only provides a final snapshot (not time series), we reconstruct force strength by walking destruction events backward from totals. Works correctly for simple scenarios.
3. **PlotlyChart wrapper with lazy loading**: Chart library is large, so we wrap in `React.lazy` + `Suspense`. All chart components go through this wrapper for consistent loading states.
4. **Mock at PlotlyChart level, not react-plotly.js**: Tests mock `../../components/charts/PlotlyChart` instead of `react-plotly.js` because lazy imports defeat direct module mocking.
5. **Browser-native WebSocket**: No library needed — native WebSocket API with simple state management in hooks. One-shot (connect, stream, complete) so no reconnect logic required.
6. **Tab state in URL**: RunDetailPage stores active tab in URL search params (`?tab=results`) for deep-linking.
7. **Batch progress via polling + WS**: `useBatch` polls at 3s when status is pending/running; WS provides iteration-level granularity for the progress bar.

## Deferred Items (Known Limitations)

1. **Supply flow chart** — No supply events recorded by SimulationRecorder
2. **Engagement network graph** — Needs cytoscape.js, high complexity, marginal value
3. **MC convergence plot** — Batch API returns aggregate stats only, not per-iteration values
4. **Synchronized cursor across charts** — Nice-to-have, not essential
5. **Large event downsampling** — 50k events may be slow in Plotly; defer optimization
6. **Click event → chart highlight** — Cross-linking between narrative and charts deferred

## Lessons Learned

- **Plotly type strictness**: `title`, `xaxis.title`, `yaxis.title` are objects (`{text: string}`) not strings in Plotly's TypeScript types. Must use `{text: 'Label'}` form.
- **React.lazy defeats vi.mock**: Mocking `react-plotly.js` doesn't work when it's loaded via `React.lazy(() => import('react-plotly.js'))`. Mock the wrapper component instead.
- **`noUnusedLocals` catches test imports**: With strict TypeScript, unused test imports (like `userEvent` or `waitFor` imported but not used) cause build failures.
- **Multiple text matches in tests**: `getByText('42')` fails when seed appears in both metadata and results sections. Use more specific selectors or `getAllByText`.
- **`<label>` without `for`/`htmlFor`**: `getByLabelText` requires proper label-input association. When using plain `<label>` + `<input>` without ids, use `getByText` for label text instead.

## Test Summary

- 65 new vitest tests (127 total frontend, up from 62)
- 7,448 Python tests unchanged
- Total: 7,575 tests (7,448 Python + 127 vitest)

## Postmortem

### Delivered vs Planned
- **Scope**: On target. 6 items deferred (all documented in Deferred Items above). 5 minor items added beyond plan: `StatCard` component, `RunSummaryCard`, tab state in URL, `formatSeconds`/`formatPercent` helpers, JSON error display in ComparePanel.
- All 4 sub-phases (34a–34d) delivered as specified.

### Integration Audit
- All ~45 new files are imported by at least one other module or test. Zero orphan files.
- All new routes wired in `App.tsx`. All new hooks used by page components. All API functions covered by tests.
- Chart components go through `PlotlyChart` wrapper — lazy loading confirmed working.

### Test Quality Review
- **Strengths**: Pure function tests (`eventProcessing.test.ts`, 13 tests) cover edge cases well. API client tests verify URL construction and request/response mapping. Page tests verify rendering, tab switching, and state management.
- **Gaps**: `useBatchProgress` hook untested (D34.1). Cancelled/error run states not exercised in RunDetailPage tests (D34.2). No query-error-path tests for hooks.

### Deficits

| ID | Severity | Description | Status |
|----|----------|-------------|--------|
| D34.1 | LOW | `useBatchProgress` hook has no dedicated test file | Deferred |
| D34.2 | LOW | RunDetailPage tests don't cover cancelled/error run states | Deferred |
| D34.3 | MEDIUM | ~~ComparePanel silently swallowed JSON parse errors in override text areas~~ | **Fixed** — added `jsonError` state with user-visible error message |
| D34.4 | MEDIUM | ~~WS `onmessage` handler had no try/catch — malformed message would crash hook~~ | **Fixed** — added try/catch in both `useRunProgress` and `useBatchProgress` |
| D34.5 | LOW | Analysis API responses untyped (`Record<string, unknown>`) — compare/sweep return free-form dicts | Deferred |
| D34.6 | LOW | Hardcoded morale state names and event type strings in eventProcessing.ts | Deferred |
| D34.7 | LOW | Force time series reconstruction assumes no reinforcements (only counts destructions) | Deferred |
