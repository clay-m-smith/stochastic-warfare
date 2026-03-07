# Phase 38: Map & Chart Enhancements

## Summary

Frontend-focused polish phase bringing the tactical map and charts up to the quality level designed in the Block 3 brainstorm. Four sub-phases: FOW toggle (38a), map visual enhancements (38b), cross-chart tick sync (38c), and dark mode (38d). Two small backend extensions for FOW detection data and elevation/sensor-range capture. No engine changes.

**Tests**: 35 new (13 Python + 22 frontend vitest). Total: ~7,811 (7,289 Python passing + 23 skipped + 241 deselected slow + 258 frontend vitest).

**Files**: 6 new + 57 modified = 63 total files changed.

## What Was Built

### 38a: FOW Toggle

**Backend** (`api/run_manager.py`):
- Extended `_capture_frame()` to include per-side detected unit IDs from `FogOfWarManager.get_world_view(side).contacts`
- Uses abbreviated key `"det"` in stored frame data for storage efficiency
- Safe access via `getattr(ctx, "fog_of_war", None)` for backward compat

**Backend** (`api/schemas.py`, `api/routers/runs.py`):
- Added `detected: dict[str, list[str]]` to `ReplayFrame` schema
- Maps abbreviated `"det"` key to full `detected` field in API response

**Frontend**:
- `MapControls.tsx` — FOW toggle + side selector dropdown. Disabled when no detection data (backward compat with old runs)
- `TacticalMap.tsx` — When FOW active, builds `detectedSet` from `currentFrameData.detected[fowSide]` and hides enemy units not in set
- `types/map.ts` — Added `detected?: Record<string, string[]>` to `ReplayFrame`

### 38b: Map Visual Enhancements

**Backend** (`api/run_manager.py`):
- Extended `_capture_frame()` to extract max sensor range per unit from `ctx.unit_sensors` → `effective_range`
- Extended `_capture_terrain()` to include elevation data from `heightmap._data.tolist()`

**Backend** (`api/schemas.py`, `api/routers/runs.py`):
- Added `sensor_range: float = 0.0` to `MapUnitFrame`
- Added `elevation: list[list[float]]` to `TerrainResponse`

**Frontend**:
- `terrain.ts` — New `applyElevationShading()` utility: brightness modulation 0.8x–1.2x based on normalized elevation
- `TacticalMap.tsx` — Elevation shading applied per terrain cell in render loop; sensor circle drawn as dashed semi-transparent circle for selected unit when "Sensors" toggle on; engagement fade with 10-tick linear opacity decay
- `MapControls.tsx` — Added "Sensors" toggle
- `types/map.ts` — Added `sensor_range?: number` to `MapUnitFrame`, `elevation?: number[][]` to `TerrainData`

**Skipped** (already done):
- Destroyed X marker — already existed in `unitRendering.ts` lines 63-73

**Simplified** (vs plan):
- Engagement fade implemented purely in rendering (TacticalMap opacity calculation) — no changes to `engagementProcessing.ts` data model. Simpler approach avoids arc age tracking.

### 38c: Cross-Chart Tick Sync

- `PlotlyChart.tsx` — Added `onClick` prop passed to `<Plot>`
- `EngagementTimeline.tsx`, `EventActivityChart.tsx`, `MoraleChart.tsx` — Added `layoutOverrides` and `onClick` props
- `ForceStrengthChart.tsx` — Added `onClick` prop (already had `layoutOverrides`)
- `ChartsTab.tsx` — `tickOverrides = { shapes: tickMarkerShapes }` + `handleChartClick` callback passed to ALL 4 charts. Click extracts `point.x` and sets `?tick=N` via `setSearchParams`

### 38d: Dark Mode

**Infrastructure**:
- NEW `frontend/src/hooks/useTheme.ts` — `useTheme()` hook with localStorage persistence (`sw-theme` key), `prefers-color-scheme` fallback, applies `dark` class to `<html>`
- `frontend/tailwind.config.js` — Added `darkMode: 'class'`
- `frontend/index.html` — Added `dark:bg-gray-900 dark:text-gray-100` to `<body>`

**Shell**:
- `Layout.tsx` — Calls `useTheme()`, passes theme/toggle to Sidebar, adds dark background
- `Sidebar.tsx` — Theme toggle button in footer, dark: class variants

**Components** (mechanical `dark:` class additions):
- 11 shared components: Card, EmptyState, ErrorMessage, PageHeader, ProgressBar, SearchInput, Select, StatCard, TabBar, ExportMenu, ConfirmDialog
- 4 map components: MapControls, PlaybackControls, MapLegend, UnitDetailSidebar
- 28 page components across analysis, editor, runs, scenarios, units

## Design Decisions

1. **FOW as per-frame detection data**: Detection stored at frame level (`detected: { "blue": ["r1", "r2"] }`) rather than per-unit field. Detection is a property of the observing side, not the observed unit.

2. **Abbreviated storage keys**: Frame data uses `"det"`, `"sr"` etc. for compact JSON storage. API endpoint maps to full names for clean external interface.

3. **Engagement fade in rendering only**: Linear opacity decay (`1 - abs(tick - arc.tick) / fadeWindow`) calculated at render time. No data model changes to `engagementProcessing.ts`. Simpler than the planned arc age/lifecycle approach.

4. **No separate dark terrain palette**: Elevation shading (brightness modulation) works for both light and dark modes. The planned `LAND_COVER_COLORS_DARK` was unnecessary.

5. **No Plotly dark template**: Charts don't switch to `plotly_dark` template in dark mode. The default Plotly styling is acceptable in both modes. Minor deficit logged.

## Deviations from Plan

| Planned | Actual | Reason |
|---------|--------|--------|
| `engagementProcessing.ts` modified for arc age | No changes needed | Fade handled in rendering via opacity calculation |
| `unitRendering.ts` modified for destroyed X | Already existed | Skipped — lines 63-73 already draw red X overlay |
| `LAND_COVER_COLORS_DARK` separate palette | Not implemented | Elevation shading works for both modes |
| Plotly `plotly_dark` template in dark mode | Not implemented | Default Plotly appearance acceptable |
| ~30 tests | 35 tests | Slightly over target |
| ~60 files | 63 files | Slightly over target |

## Issues & Fixes

1. **Layout test TypeError: window.matchMedia is not a function** — `useTheme` hook calls `window.matchMedia('(prefers-color-scheme: dark)')` which doesn't exist in jsdom. Fixed by adding `Object.defineProperty(window, 'matchMedia', { writable: true, value: vi.fn().mockImplementation(...)})` in `beforeEach` of Layout.test.tsx and useTheme.test.ts.

2. **TickSync test TypeScript errors** — Wrong `RunResult` type shape (`initial`/`surviving` instead of `total`/`active`), nullable `VictoryResult`. Fixed by reading `types/api.ts` for correct interfaces.

## Known Limitations

- Plotly charts don't use `plotly_dark` template when dark mode is active (acceptable — transparent background + dark page looks fine)
- No separate dark terrain color palette (elevation shading brightness modulation works for both modes)
- FOW detection data may contain stale contacts — this is correct behavior (shows what the side believes)
- Elevation data can be 80KB+ JSON for 100×100 grids (acceptable for one-time terrain load)

## Postmortem

### 1. Delivered vs Planned

- **Scope**: Well-calibrated. 35 tests delivered vs ~30 planned. 63 files vs ~60 planned.
- **Descoped**: 3 items — `LAND_COVER_COLORS_DARK`, Plotly dark template, `engagementProcessing.ts` arc age model
- **Already done**: Destroyed X marker (existed since Phase 35)
- **Unplanned additions**: None

### 2. Integration Audit

- All new backend code (`_capture_frame` FOW/sensor extensions, `_capture_terrain` elevation) properly wired through `schemas.py` → `routers/runs.py` → frontend types
- `useTheme` hook imported by `Layout.tsx`, which passes to `Sidebar.tsx`
- All chart components (`EngagementTimeline`, `EventActivityChart`, `MoraleChart`, `ForceStrengthChart`) receive `layoutOverrides` and `onClick` from `ChartsTab`
- `PlotlyChart.tsx` passes `onClick` to underlying `<Plot>`
- FOW toggle disabled when no detection data — backward compat verified
- **No dead modules**: All 6 new files are imported/used

### 3. Test Quality Review

- **Unit tests**: `applyElevationShading` covers high/low/equal-range edge cases
- **Integration tests**: `test_phase_38_fow.py` tests backend capture + schema validation + endpoint mapping
- **Component tests**: MapControls, FOW toggle, sensor circles, tick sync, useTheme all test behavior not implementation
- **Edge cases covered**: null coordinates, missing detection data, equal min/max elevation, no tick param

### 4. API Surface Check

- All new schema fields have defaults (backward compat): `sensor_range: float = 0.0`, `detected: dict = {}`, `elevation: list = []`
- `applyElevationShading` is public (exported, tested, used by TacticalMap)
- `useTheme` returns clean `{ theme, toggleTheme }` interface

### 5. Deficit Discovery

- **Resolved**: "Only ForceStrengthChart shows tick sync" (Phase 35 deficit) — all 4 charts now sync
- **New deficits** (2):
  - Plotly charts don't use dark template in dark mode (cosmetic — acceptable appearance)
  - No separate dark terrain color palette (elevation shading covers the need)
- Both are cosmetic/low-priority. Not blocking.

### 6. Documentation Freshness

- Phase devlog: Written (this file)
- devlog/index.md: Needs update (Phase 38 → Complete, deficit resolution)
- development-phases-block4.md: Needs update (Phase 38 → COMPLETE)
- CLAUDE.md: Needs update (Phase 38 in status section)
- README.md: Needs update (test count, phase status)
- MEMORY.md: Needs update (current status)

### 7. Performance Sanity

- Python tests: 123.41s — comparable to Phase 37 (~123s). 13 new tests add negligible time.
- Frontend tests: 12.21s for 258 tests — good performance.
- No performance regression.

### 8. Summary

- **Scope**: On target
- **Quality**: High
- **Integration**: Fully wired
- **Deficits**: 1 resolved, 2 new (both cosmetic)
- **Action items**: Update lockstep documents, commit
