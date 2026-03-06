# Phase 35 — Tactical Map & Spatial Visualization

## Summary

Built a 2D tactical map with post-hoc replay for completed simulation runs. The pipeline captures terrain and unit position data during run execution, stores it in the database, serves it via two new API endpoints, and renders it on an HTML5 Canvas with playback controls, overlays, and chart synchronization.

**Backend**: 4 modified API files + 1 new test file (13 tests). Two new nullable DB columns (`terrain_json`, `frames_json`), terrain/frame capture in `RunManager._run_sync()`, and `GET /terrain` + `GET /frames` endpoints.

**Frontend**: 15 new source files + 10 new test files (58 tests) + 3 modified files. Canvas-based `TacticalMap` component with terrain rendering, unit markers (domain-specific shapes), engagement arcs, movement trails, playback controls, map legend, unit detail sidebar, and viewport zoom/pan. Integrated as a new tab in `RunDetailPage` and as a standalone fullscreen route.

## What Was Built

### 35a: API Data Pipeline
- **`api/database.py`** — `terrain_json TEXT` and `frames_json TEXT` nullable columns with `ALTER TABLE` migration
- **`api/run_manager.py`** — `_capture_terrain()` extracts heightmap/classification/objectives; `_capture_frame()` captures unit positions at dynamic intervals (`max(1, max_ticks // 500)`)
- **`api/schemas.py`** — 5 new pydantic models: `MapUnitFrame`, `ReplayFrame`, `FramesResponse`, `ObjectiveInfo`, `TerrainResponse`
- **`api/routers/runs.py`** — `GET /runs/{id}/terrain` and `GET /runs/{id}/frames` with `start_tick`/`end_tick` filtering

### 35b: Canvas Map Renderer + Types
- **`types/map.ts`** — 7 TypeScript interfaces mirroring API models
- **`api/map.ts`** — `fetchRunTerrain()` and `fetchRunFrames()` fetch wrappers
- **`hooks/useMap.ts`** — TanStack Query hooks with `staleTime: Infinity`
- **`lib/terrain.ts`** — 15 land cover colors/names, `worldToScreen()`/`screenToWorld()` transforms with Y-flip, `getVisibleCellRange()` for viewport culling
- **`lib/unitRendering.ts`** — `drawUnit()` with domain shapes (rect/triangle/diamond/circle), status modifiers, `hitTestUnit()` for click detection
- **`components/map/useViewportControls.ts`** — zoom-at-cursor, pan, `fitToExtent()`
- **`components/map/TacticalMap.tsx`** — Main orchestrator: ResizeObserver, offscreen terrain canvas, layered render (terrain → objectives → trails → engagements → units)

### 35c: Overlays, Legend & Selection
- **`components/map/MapControls.tsx`** — Toggle bar (labels, destroyed, engagements, trails), Fit button, world coordinate display
- **`components/map/MapLegend.tsx`** — Terrain colors, side colors, domain shape icons
- **`components/map/UnitDetailSidebar.tsx`** — Selected unit panel with full metadata
- **`lib/engagementProcessing.ts`** — `buildEngagementArcs()` matches events to nearest frame

### 35d: Playback Controls & Integration
- **`hooks/usePlayback.ts`** — rAF-based animation loop, play/pause/step/seek, 4 speed options (1x/2x/5x/10x)
- **`components/map/PlaybackControls.tsx`** — Transport buttons, timeline scrubber, speed selector, tick info
- **`pages/runs/tabs/MapTab.tsx`** — Integrated tab with empty state for pre-Phase-35 runs
- **`pages/map/FullscreenMapPage.tsx`** — Standalone `/map/:runId` route
- **Chart sync** — MapTab writes `?tick=N` to URL params; ChartsTab reads it and draws vertical reference line on ForceStrengthChart via `layoutOverrides`

## Design Decisions

1. **Lightweight frames, not full snapshots** — ~80 bytes/unit (compact keys `d`, `s`, `h`, `t`) vs 100KB+ for full `ctx.get_state()`. Targets ~500 frames per run regardless of length.
2. **Single Canvas, no extra deps** — Pure HTML5 Canvas with offscreen terrain cache. No Pixi.js/Konva/Leaflet. Keeps bundle small.
3. **Y-axis flip** — Canvas Y↓ vs ENU northing↑. All rendering through `worldToScreen()` with consistent flip.
4. **Nullable columns for backward compat** — Pre-Phase-35 runs show "Map data not available" empty state. No migration pain.
5. **`getattr()` safe access** — Terrain capture uses `getattr(ctx, "heightmap", None)` pattern to handle scenarios where terrain objects may not be present.
6. **Chart sync via URL params** — `?tick=N` shared between MapTab and ChartsTab. No global store needed; URL is the source of truth.
7. **Dynamic frame interval** — `max(1, max_ticks // 500)` targets ~500 frames regardless of run length. Not configurable yet.

## Deviations from Plan

None significant. All planned items delivered. Deferred items (detection circles, FOW toggle, elevation shading, engagement fade animation) were pre-planned deferrals from the Phase 35 design doc.

## Issues & Fixes

1. **TypeScript strict null checks** — `extent[0]` returns `number | undefined` with strict mode. Fixed with non-null assertions (`extent[0]!`) after length guard.
2. **`getVisibleCellRange` inverted bounds** — `screenToWorld(0,0)` gives min-X/max-Y, not max-X/max-Y. Fixed by using `Math.min/max` on both corners rather than assuming positions.
3. **UnitDetailSidebar duplicate text** — Unit type appears in both header and Type row. Test fixed to use `getAllByText` instead of `getByText`.
4. **Canvas mock in vitest** — `HTMLCanvasElement.prototype.getContext` must be re-mocked after `vi.restoreAllMocks()` in `beforeEach`.

## Known Limitations

- Frame data uses compact keys in storage but API expands to full names — slight redundancy
- `terrain_json` and `frames_json` stored as TEXT blobs — no indexing, large runs may produce 2MB+ frames
- `useViewportControls` hook has no dedicated test file (exercised indirectly via TacticalMap)
- Only `ForceStrengthChart` shows the tick sync marker line — other charts don't
- Frame capture interval is not configurable
- No keyboard shortcuts for playback (deferred to Phase 36)

## Lessons Learned

- **Off-screen canvas for terrain caching** is essential — re-rendering terrain cells every frame would be too slow. Only re-render when transform changes.
- **Canvas mock strategy in vitest**: Mock `getContext` to return a stub with all needed method names. Use property setters for style properties (`set fillStyle(_v: string) {}`).
- **`getVisibleCellRange` math**: Never assume screen corners map to specific world corners — use `Math.min/max` on both to get correct world bounds regardless of transform.
- **URL params as state**: `?tick=N` for cross-tab sync is simpler than any state management solution and survives page refreshes.
- **`@staticmethod` for capture helpers**: Both `_capture_terrain` and `_capture_frame` have no `self` dependency, making them testable without instantiating `RunManager`.

## Postmortem

- **Scope**: On target — all planned items delivered, deferred items were pre-planned
- **Quality**: High — 71 new tests (13 Python + 58 vitest), clean TypeScript, no dead code, no TODOs
- **Integration**: Fully wired — backend→DB→API→frontend→canvas pipeline, chart sync
- **Deficits**: 6 new items (all LOW, 1 deferred to Phase 36)
- **Action items**: Documentation lockstep update (CLAUDE.md, README.md, MEMORY.md, devlog/index.md, development-phases-block3.md, docs/index.md, docs/reference/api.md, mkdocs.yml)
