# Phase 33: Frontend Foundation & Scenario Browser

## Summary

Stood up the React + TypeScript frontend consuming the Phase 32 FastAPI service. Delivers scenario browser, unit catalog, run configuration, and run list pages. Pure frontend phase -- zero engine or API modifications.

**62 tests** (vitest). **~50 new files** in `frontend/`.

## What Was Built

### Frontend Scaffolding (33a)

- **Vite + React 18 + TypeScript 5.7** project in `frontend/`
- **Tailwind CSS v3** with custom era/side color tokens
- **TanStack Query v5** for all data fetching (no Redux/Zustand)
- **React Router v6** with sidebar layout + 7 routes
- **Headless UI v2** for accessible Dialog (unit detail modal)
- **Vitest + RTL** for component/hook testing with jsdom

### TypeScript API Client (33a-api)

- `types/api.ts` — All interfaces mirroring `api/schemas.py`
- `api/client.ts` — `apiGet<T>()`, `apiPost<T>()`, `apiDelete()` with `ApiError` class
- `api/scenarios.ts`, `api/units.ts`, `api/runs.ts`, `api/meta.ts` — typed fetch wrappers
- Vite proxy: `/api` -> `localhost:8000` (zero CORS issues in dev)

### TanStack Query Hooks (33a-hooks)

- `useScenarios()`, `useScenario(name)` — 5-min stale time
- `useUnits(filters?)`, `useUnit(type)` — 5-min stale time
- `useRuns(params?)`, `useSubmitRun()` — 30s stale time / mutation
- `useHealth()`, `useEras()` — health indicator, metadata

### Layout & Shared Components (33a-layout)

- `Layout` — fixed sidebar (w-64) + main content `<Outlet />`
- `Sidebar` — nav links with active styling + health indicator (green/red dot, scenario/unit count)
- 8 shared components: Badge, Card, SearchInput (debounced), Select, LoadingSpinner, ErrorMessage, EmptyState, PageHeader

### Utility Functions (33a-utils)

- `lib/format.ts` — `formatDuration(hours)`, `formatDate(iso)`, `formatNumber(n)`
- `lib/era.ts` — `eraDisplayName()`, `eraBadgeColor()`, `eraOrder()` for all 5 eras
- `lib/domain.ts` — `domainDisplayName()`, `domainBadgeColor()` for all domains

### Scenario List Page (33b)

- Responsive card grid with era badge, terrain type, duration, sides, config badges (EW/CBRN/Escalation/Schools)
- Client-side filtering: era select, sort (name/era/duration), search text
- All filters persisted in URL search params (shareable/bookmarkable)

### Scenario Detail Page (33b)

- Full config display: terrain info, weather conditions, documented outcomes table
- Force table: side-grouped with unit count and unit types
- Config badges: EW, CBRN, Escalation, Schools, Space indicators
- "Run This Scenario" button -> navigates to run config page

### Unit Catalog (33c)

- Card grid with domain badge, era badge, category, speed, crew size
- Client-side filtering: domain select, era select, search text
- Headless UI Dialog modal for unit detail (recursive key-value renderer)

### Run Configuration & Run List (33d)

- RunConfigPage: reads `?scenario=` from URL, displays scenario summary, seed + max_ticks inputs, "Start Run" button -> POST /api/runs -> navigate to runs list
- RunListPage: table of past runs with scenario, seed, status badge, created/completed dates
- AnalysisPage: stub ("Coming in Phase 34")

## Design Decisions

1. **npm** over pnpm — ships with Node.js, zero extra install, no monorepo needs
2. **Hand-written API client** — 25 endpoints, small & stable. ~150 lines of typed fetch wrappers. No OpenAPI codegen complexity.
3. **TanStack Query only** — no Zustand/Redux. All data comes from API. UI state is local component state or URL search params.
4. **Client-side filtering** — 41 scenarios, ~125 units. Trivially small datasets. Filter/search/sort in browser.
5. **URL search params for filters** — era, sort, search persist across navigation
6. **Tailwind v3** — v4 too new, ecosystem still centered on v3
7. **Feature folders** — `pages/scenarios/`, `pages/units/`, `pages/runs/`, shared components in `components/`
8. **`mutate()` over `mutateAsync()`** — prevents unhandled promise rejections in tests and production; `onSuccess` callback for navigation

## Issues & Fixes

1. **`useRef` readonly current** — React 18 types make `useRef<T>(null)` readonly. Fixed by typing as `useRef<T | null>(null)`.
2. **`unknown` not assignable to ReactNode** — Conditional rendering `{terrain.terrain_type && (...)}` returns `unknown` when truthy. Fixed by using `!= null` checks instead of truthiness.
3. **Unhandled promise rejection in tests** — `mutateAsync` throws on API errors; changed to `mutate()` with `onSuccess` callback to handle errors via TanStack Query's built-in error state.
4. **Second `fetch` mock consumed** — Test calling `apiGet` twice shared the same mock. Fixed by splitting into separate test cases.

## Known Limitations

- No responsive mobile layout (sidebar always visible, not collapsible)
- No skeleton loading states (spinner only)
- Unit detail modal renders raw key-value pairs (no formatted sections per domain/era)
- Run list is basic table (no detail page, no live tracking -- Phase 34)
- Analysis page is a stub
- No error boundary at app level
- React Router v6 future flag warnings in tests (harmless, resolved when upgrading to v7)

## Lessons Learned

- **Vite proxy eliminates CORS friction**: `/api` proxy in `vite.config.ts` means the client just uses relative URLs. Zero CORS issues in development.
- **TanStack Query as sole state manager works well**: For read-heavy API-driven UIs with small datasets, TanStack Query + URL search params + local component state is simpler than adding a state management library.
- **URL search params for filter state**: Enables shareable/bookmarkable filter URLs and persists state across navigation without a store.
- **`mutate()` > `mutateAsync()` for form handlers**: Avoids unhandled rejection issues and lets TanStack Query manage error state via `isError`/`error`.
- **Node.js must be installed natively on Windows**: Docker-based Node adds volume mount friction that slows frontend dev workflow.

## Test Summary

| File | Tests | Description |
|------|-------|-------------|
| api/client.test.ts | 8 | apiGet, apiPost, apiDelete with mock fetch |
| api/scenarios.test.ts | 3 | fetchScenarios, fetchScenario |
| hooks/useScenarios.test.ts | 3 | Query hooks with QueryClient wrapper |
| hooks/useUnits.test.ts | 3 | Unit query hooks |
| pages/ScenarioListPage.test.tsx | 8 | Rendering, filtering, sorting, search, empty/error states |
| pages/ScenarioDetailPage.test.tsx | 6 | Rendering, force table, config badges, run button |
| pages/UnitCatalogPage.test.tsx | 6 | Rendering, filtering, modal open, empty state |
| pages/RunConfigPage.test.tsx | 5 | Form rendering, defaults, submission, error |
| components/Layout.test.tsx | 3 | Sidebar nav, health status |
| lib/format.test.ts | 7 | formatDuration, formatDate edge cases |
| lib/era.test.ts | 6 | eraDisplayName, eraBadgeColor, eraOrder |
| lib/domain.test.ts | 4 | domainDisplayName, domainBadgeColor |
| **Total** | **62** | |
