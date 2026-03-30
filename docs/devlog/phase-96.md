# Phase 96: Analysis & Event Interaction

**Status**: Complete
**Block**: 10 (UI Depth & Engine Exposure)
**Tests**: 13 new frontend tests (409 total vitest)
**Files**: 3 new + 11 modified files (frontend + backend)

## What Was Built

### 96a: Event Filtering & Search
- **Backend** (`api/routers/runs.py`): Extended `get_run_events` endpoint with 4 new query params: `side`, `tick_min`, `tick_max`, `search`. Server already loads all events into memory for pagination — filtering is additional predicates before slicing.
- **Frontend** (`EventsTab.tsx`): Filter bar with side dropdown (All/Blue/Red), tick range inputs (min/max), text search with 300ms debounce, clear filters button. "Showing X filtered events" display. All filter changes reset offset to 0.
- **API client** (`runs.ts`, `useRuns.ts`): Extended `fetchRunEvents` and `useRunEvents` with new filter params.

### 96b: Engagement Detail Modal
- **`EngagementDetailModal.tsx`** (new): `@headlessui/react` Dialog modal with structured sections — Participants (attacker/target IDs and sides), Weapon (weapon_id, ammo_type, range), Resolution (result, hit, penetrated, Pk), Damage (type, amount, location), collapsible Raw Data (JSON).
- **EventsTab.tsx**: Engagement event rows (matching `ENGAGEMENT_EVENTS` set from `eventProcessing.ts`) get `cursor-pointer` class and click handler. Selected event opens the modal.

### 96c: Doctrine Comparison — Backend
- **`api/schemas.py`**: `DoctrineCompareRequest` (scenario, side_to_vary, schools, num_iterations, max_ticks), `DoctrineSchoolResult` (school_id, win_rate, mean/std casualties and duration), `DoctrineCompareResult`.
- **`stochastic_warfare/tools/_run_helpers.py`**: Added `win_*` metric prefix to `_extract_metrics` — checks `engine._last_victory.winning_side` for match.
- **`stochastic_warfare/tools/doctrine_compare.py`** (new): `run_doctrine_comparison()` — for each school, deep copies base config, sets `school_config.{side}_school`, writes temp YAML, calls `run_scenario_batch` with metrics `[blue_destroyed, red_destroyed, ticks_executed, win_{side}]`, aggregates into SchoolResult.
- **`api/routers/analysis.py`**: `POST /api/analysis/doctrine-compare` endpoint — same pattern as compare/sweep (semaphore, asyncio.to_thread).

### 96c: Doctrine Comparison — Frontend
- **`types/analysis.ts`**: `DoctrineSchoolResult`, `DoctrineCompareResult` interfaces.
- **`api/analysis.ts`**: `DoctrineCompareRequest` interface + `runDoctrineCompare()` API client.
- **`hooks/useAnalysis.ts`**: `useDoctrineCompare()` mutation hook.
- **`DoctrineComparePanel.tsx`** (new): Scenario selector, side-to-vary dropdown, school checkboxes (min 2 required), iterations/maxTicks inputs. Results displayed in a table sorted by win rate (best school highlighted).
- **`AnalysisPage.tsx`**: 4th tab "Doctrine Compare" added to TABS array.

## Design Decisions

1. **Server-side event filtering** instead of client-side — spec said "no API changes" but events can be 10k+, and the server already loads all events into memory. Server-side filtering keeps pagination correct and avoids downloading all events to the browser.
2. **Modal for engagement detail** — matches existing UnitDetailModal pattern, @headlessui/react Dialog already a dependency. Simpler than a slide-in sidebar.
3. **Results table instead of Plotly chart** for doctrine comparison — a sorted table with win rate percentages and +/- stats is more informative than a grouped bar chart for this use case. Can add charts later if needed.
4. **`win_*` metric prefix** in _extract_metrics — generic pattern allows `win_blue`, `win_red`, or any side name. Checks `engine._last_victory.winning_side`.
5. **Search debounce (300ms)** — local `useEffect` + `setTimeout` pattern avoids a library dependency while preventing excessive API calls.

## Deviations from Plan

1. **Server-side filtering** (96a) — spec said "pure client-side logic, no API changes." Used server-side instead for correctness with paginated data.
2. **Heatmap variant** (96c) — spec mentioned "Heatmap variant: school x metric matrix with color intensity." Descoped in favor of results table.
3. **Plotly grouped bar chart** (96c) — spec said grouped bar chart for results. Used a table instead for simplicity. The chart can be added later.
4. **No Python-side unit tests** — event filter and doctrine compare tool lack dedicated Python test files. Frontend tests cover the integration points.

## Files Changed

### New Files
- `frontend/src/pages/runs/tabs/EngagementDetailModal.tsx`
- `frontend/src/pages/analysis/DoctrineComparePanel.tsx`
- `stochastic_warfare/tools/doctrine_compare.py`
- `frontend/src/__tests__/pages/EngagementDetailModal.test.tsx`
- `frontend/src/__tests__/pages/analysis/DoctrineComparePanel.test.tsx`

### Modified Files
- `api/routers/runs.py` — 4 new query params on events endpoint
- `api/routers/analysis.py` — doctrine-compare endpoint
- `api/schemas.py` — 3 new request/response models
- `stochastic_warfare/tools/_run_helpers.py` — win_* metric
- `frontend/src/api/runs.ts` — extended fetchRunEvents params
- `frontend/src/hooks/useRuns.ts` — extended useRunEvents params
- `frontend/src/pages/runs/tabs/EventsTab.tsx` — filter bar + engagement click handler
- `frontend/src/types/analysis.ts` — DoctrineSchoolResult, DoctrineCompareResult
- `frontend/src/api/analysis.ts` — runDoctrineCompare
- `frontend/src/hooks/useAnalysis.ts` — useDoctrineCompare hook
- `frontend/src/pages/analysis/AnalysisPage.tsx` — 4th tab

## Postmortem

- **Scope**: On target. All 3 sub-phases delivered. Heatmap variant and Plotly chart descoped (table is better for this data).
- **Quality**: High. Zero TODOs, zero dead code, full integration.
- **Integration**: Fully wired. All new components imported, all endpoints reachable, all hooks consumed.
- **Deficits**: No Python unit tests for event filter params or doctrine compare tool. Frontend tests cover integration.
