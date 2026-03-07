# Phase 39: Quality, Performance & Packaging

## Summary

Final phase of Block 4 and the entire project roadmap. Closed test coverage gaps from Phases 34-36, virtualized event lists for large runs, typed analysis responses, and packaged the application for single-command startup via `uv run python -m api` and Docker.

**Tests**: 22 new (6 Python + 16 vitest), ~7,833 total (~7,561 Python + 272 vitest)

## What Was Built

### 39a: Test Coverage Gaps

- **`useBatchProgress` tests** (4 tests): null batchId, connect/open, parse messages, cleanup on unmount
- **`useViewportControls` tests** (4 tests): initial defaults, zoom in/out, fitToExtent computation
- **RunDetailPage error states** (2 tests): cancelled badge, multi-line traceback in `<pre>` block
- **Typed analysis responses**: `frontend/src/types/analysis.ts` with `CompareResult`, `SweepResult`, `MetricComparison`, `MetricStat`, `SweepPoint`
- **API analysis functions**: `runCompare()` and `runSweep()` return typed results instead of `Record<string, unknown>`
- **`useAnalysis` hooks**: Updated mutation types from `Record<string, unknown>` to typed results
- **`ComparisonCharts`**: Rewrote to use `result.metrics` array with grouped bar chart (mean ± std error bars) and statistical table (p-value, effect size, significance highlighting). Previous implementation was broken — accessed non-existent `result.a`/`result.b` fields.
- **`SweepPanel`**: Fixed data extraction from `Object.entries(sweep.data)` (iterated SweepResult fields) to `sweep.data.points.map(...)` (iterates sweep data points)
- **Event type constants**: Exported `DESTRUCTION_EVENTS`, `REINFORCEMENT_EVENTS`, `ENGAGEMENT_EVENTS`, `MORALE_EVENTS` from `eventProcessing.ts`
- **RunDetailPage**: Error messages wrapped in `<pre>` for traceback formatting

### 39b: Performance

- **Configurable frame capture interval**: `RunSubmitRequest.frame_interval` field (default `None` = auto ~500 frames). Passed through `submit()` -> `_execute_run()` -> `_run_sync()`.
- **Virtualized event list**: `@tanstack/react-virtual` for `EventsTab` — renders only visible rows in a scrollable container. Pagination still works for data fetching. Fixed header stays above scroll area.

### 39c: Startup & Packaging

- **`api/__main__.py`**: Enables `uv run python -m api` single-command startup
- **Static file serving**: `create_app()` detects `frontend/dist/` and mounts `/assets` + SPA fallback catch-all route. API routes take precedence (registered first).
- **Dev scripts**: `scripts/dev.sh` (bash) and `scripts/dev.ps1` (PowerShell) start both API and frontend dev servers with cleanup on exit
- **Docker**: Multi-stage `Dockerfile` (Node 22 alpine frontend build + Python 3.12 slim + uv). `.dockerignore` excludes dev files.
- **README Quick Start**: Added development, production, and Docker startup instructions

### 39d: Minor Polish

- **Terrain types from enum**: `GET /api/meta/terrain-types` returns `LandCover` enum member names instead of hardcoded list
- **ConfigDiff component**: Recursive diff view in scenario editor showing `field: oldValue -> newValue` entries. Collapsible Headless UI `Disclosure` panel.

## Design Decisions

1. **Virtualizer in jsdom**: `@tanstack/react-virtual` requires non-zero scroll element dimensions. Tests mock `HTMLElement.prototype.offsetHeight/scrollHeight` for the virtualizer to render items.
2. **SPA fallback ordering**: API routers are included before the catch-all `/{full_path:path}` route, ensuring `/api/*` always takes precedence.
3. **Frame interval passthrough**: Added as optional parameter through 4 layers: schema -> router -> manager.submit -> _execute_run -> _run_sync. No breaking changes (default None preserves existing auto-calculation).

## Files Changed

| Action | File | Sub-phase |
|--------|------|-----------|
| NEW | `frontend/src/__tests__/hooks/useBatchProgress.test.ts` | 39a |
| NEW | `frontend/src/__tests__/hooks/useViewportControls.test.ts` | 39a |
| NEW | `frontend/src/__tests__/pages/RunDetailPage.error.test.tsx` | 39a |
| NEW | `frontend/src/types/analysis.ts` | 39a |
| NEW | `frontend/src/__tests__/tabs/EventsTab.test.tsx` | 39b |
| NEW | `frontend/src/__tests__/pages/editor/ConfigDiff.test.tsx` | 39d |
| NEW | `frontend/src/pages/editor/ConfigDiff.tsx` | 39d |
| NEW | `api/__main__.py` | 39c |
| NEW | `scripts/dev.sh` | 39c |
| NEW | `scripts/dev.ps1` | 39c |
| NEW | `Dockerfile` | 39c |
| NEW | `.dockerignore` | 39c |
| NEW | `tests/api/test_phase_39_packaging.py` | 39b/39c/39d |
| MODIFY | `frontend/src/api/analysis.ts` | 39a |
| MODIFY | `frontend/src/hooks/useAnalysis.ts` | 39a |
| MODIFY | `frontend/src/lib/eventProcessing.ts` | 39a |
| MODIFY | `frontend/src/pages/runs/RunDetailPage.tsx` | 39a |
| MODIFY | `frontend/src/components/charts/ComparisonCharts.tsx` | 39a |
| MODIFY | `frontend/src/pages/analysis/SweepPanel.tsx` | 39a |
| MODIFY | `frontend/src/pages/runs/tabs/EventsTab.tsx` | 39b |
| MODIFY | `frontend/src/__tests__/pages/EventsTab.test.tsx` | 39b |
| MODIFY | `frontend/package.json` + lock | 39b |
| MODIFY | `api/schemas.py` | 39b |
| MODIFY | `api/run_manager.py` | 39b |
| MODIFY | `api/routers/runs.py` | 39b |
| MODIFY | `api/main.py` | 39c |
| MODIFY | `api/routers/meta.py` | 39d |
| MODIFY | `frontend/src/pages/editor/ScenarioEditorPage.tsx` | 39d |
| MODIFY | `README.md` | 39c |

## Deficit Resolution

| Deficit | Origin | Resolved |
|---------|--------|----------|
| `useBatchProgress` no dedicated test | Phase 34 | 39a |
| RunDetailPage tests don't cover error states | Phase 34 | 39a |
| Analysis API responses untyped | Phase 34 | 39a |
| Hardcoded morale/event strings | Phase 34 | 39a |
| `useViewportControls` no dedicated test | Phase 35 | 39a |
| Frame capture interval not configurable | Phase 35 | 39b |
| `GET /api/meta/terrain-types` hardcoded | Phase 32 | 39d |

## Known Limitations

- Docker image not tested on CI (no Docker in dev environment)
- `scripts/dev.ps1` uses `Start-Process -NoNewWindow` which may not propagate signals cleanly on all Windows versions
- Virtualizer row heights are estimated at 40px — very long event data may overflow

## Lessons Learned

- `@tanstack/react-virtual` needs real DOM dimensions to determine visible range — jsdom returns 0 for all layout properties. Must mock `offsetHeight`/`scrollHeight` on `HTMLElement.prototype`.
- TypeScript interfaces with explicit fields can't be assigned to `Record<string, unknown>` — the index signature is missing. When tightening types from `Record<string, unknown>` to a concrete interface, must update all consumers in the chain (hooks, components, tests).
- SPA fallback route ordering in FastAPI: routes registered via `include_router()` take precedence over later `@app.get()` catch-all routes, so API routes naturally win.

## Postmortem

### 1. Delivered vs Planned
All planned items delivered: 39a (test gaps, typed responses, event constants), 39b (frame interval, virtualized events), 39c (\_\_main\_\_, SPA, Docker, dev scripts, README), 39d (terrain enum, ConfigDiff). Two unplanned fixes discovered and resolved during postmortem (ComparisonCharts rewrite, SweepPanel data fix). Scope well-calibrated — no items dropped or deferred.

### 2. Integration Audit
- All new files are imported/used: `types/analysis.ts` imported by `api/analysis.ts`, `useAnalysis.ts`, `ComparisonCharts.tsx`; `ConfigDiff.tsx` imported by `ScenarioEditorPage.tsx`; exported event constants available to consumers; `api/__main__.py` enables `python -m api`.
- **Pre-existing bugs found and fixed**: `ComparisonCharts` accessed non-existent `result.a`/`result.b` — rewrote to use `result.metrics` array with proper bar chart + statistical table. `SweepPanel` used `Object.entries(sweep.data)` iterating SweepResult fields — fixed to use `sweep.data.points.map(...)`.
- No dead modules. No orphaned imports.

### 3. Test Quality Review
- **Coverage**: Mix of unit (vitest component tests) and integration (Python API tests via httpx TestClient). Edge cases covered: null batchId, empty metrics, cancelled/failed states.
- **Realistic data**: Tests use scenario-representative mock data (metric names, p-values, effect sizes).
- **jsdom limitation**: Virtualizer tests require `offsetHeight`/`scrollHeight` mocks — test setup documents this clearly.
- **No implementation-detail tests**: All tests verify behavior (rendered output, API responses), not internal state.

### 4. API Surface Check
- Type hints on all new public functions. `ConfigDiff` props properly typed.
- `frame_interval` parameter properly typed as `int | None` through all layers.
- No functions that should be private but aren't.

### 5. Deficit Discovery
No new deficits introduced. 7 pre-existing deficits resolved. 2 pre-existing bugs found and fixed (ComparisonCharts, SweepPanel) that were not tracked as formal deficits.

### 6. Documentation Freshness
- CLAUDE.md: Phase 39 status updated, test counts accurate
- README.md: Badges, phase table, Quick Start section all current
- MEMORY.md: Status and phase summary table updated
- devlog/index.md: Phase 39 complete, 7 deficits marked resolved
- development-phases-block4.md: Phase 39 marked COMPLETE
- docs/index.md: Test count badge updated
- mkdocs.yml: Phase 39 devlog in nav

### 7. Performance Sanity
Python test suite: ~142s. No regression from Phase 38 (~140s). Frontend vitest: ~14s. No performance concerns.

### 8. Summary
- **Scope**: On target (all planned items + 2 bonus bug fixes)
- **Quality**: High — typed interfaces catch errors at compile time, virtualized rendering handles large datasets
- **Integration**: Fully wired — no gaps found
- **Deficits**: 0 new, 7 resolved, 2 pre-existing bugs fixed
- **Action items**: None — ready for final commit
