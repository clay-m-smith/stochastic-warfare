# Stochastic Warfare -- Block 4 Development Phases (37--39)

## Philosophy

Block 4 tightens the product. No new engine subsystems, no new simulation domains. Three priorities: (1) fix broken integration points that will surface during real use, (2) bring the tactical map and charts up to the quality level designed in Block 3, (3) package the application for single-command startup.

**Cross-document alignment**: This document must stay synchronized with `brainstorm-block4.md` (design thinking), `devlog/index.md` (deficit inventory), and `specs/project-structure.md` (module definitions). Run `/cross-doc-audit` after any structural change.

**Engine changes are surgical**: Block 4 modifies `stochastic_warfare/` only to wire existing but disconnected subsystems (DEW battle loop integration, reinforcement events). No new engines, no new data models, no architectural changes.

---

## Phase 37: Integration Fixes & End-to-End Validation — COMPLETE

**Goal**: Fix the three broken integration points that will surface during real use (config_overrides silently ignored, DEW completely unwired, reinforcement charts wrong), then smoke-test every scenario through the web UI pipeline.

**Status**: Complete. 70 new tests (24 Python unit + 41 E2E parametrized + 5 frontend vitest). 6 modified + 6 new files. 5 deficits resolved, 2 new deficits logged. Focused implementation: 3 core bugs + E2E smoke test. Deferred items: terrain-types-from-data (→39d), ADUnitType.DEW routing, scenario dew_config YAML.

**Dependencies**: Block 3 complete (Phases 31--36).

### 37a: Critical Bug Fixes

Fix the bugs that make existing features silently wrong.

#### config_overrides Not Applied

**Problem**: `api/run_manager.py:_run_sync()` receives `config_overrides` as a parameter (line 125) but never applies it. The YAML is loaded from disk (line 140--141), `loader.load()` is called (line 144), and the overrides are completely ignored. The scenario editor's calibration sliders have no effect on the simulation.

- **`api/run_manager.py`** (modified) -- In `_run_sync()`, after loading the scenario YAML dict but before calling `loader.load()`:
  - Parse the YAML into a dict
  - Deep-merge `config_overrides` into the dict (overrides win on conflict)
  - Write the merged dict to a temp YAML file
  - Pass the temp file to `loader.load()`
  - Alternative: extend `ScenarioLoader.load()` to accept an `overrides: dict` parameter and apply them after YAML parse but before pydantic validation
- **`api/routers/runs.py`** (modified) -- Ensure `POST /api/runs/from-config` passes config_overrides correctly through the submit chain

#### Force Time Series Ignores Reinforcements

**Problem**: `frontend/src/lib/eventProcessing.ts:buildForceTimeSeries()` builds force strength over time by walking destruction events and decrementing from initial totals. When reinforcements arrive in campaign scenarios, the counts never go back up -- the chart shows a monotonically decreasing line even though forces are growing.

- **`stochastic_warfare/simulation/campaign.py`** (modified) -- After spawning reinforcement units (line ~168--173), publish a `ReinforcementArrivedEvent` to the event bus with `side`, `unit_count`, and `tick` data. Currently logs the arrival but emits no event.
- **`stochastic_warfare/core/events.py`** or **`simulation/events.py`** (modified) -- Add `ReinforcementArrivedEvent` dataclass with `side: str`, `unit_count: int`, `unit_types: list[str]`.
- **`frontend/src/lib/eventProcessing.ts`** (modified) -- Add reinforcement event handling:
  - Define `REINFORCEMENT_EVENTS` set alongside existing `DESTRUCTION_EVENTS`
  - When processing a reinforcement event, increment `activeCounts[side]` by `unit_count`
  - Push a new time point after increment

#### Terrain Types from Data

**Problem**: `GET /api/meta/terrain-types` returns a hardcoded list instead of deriving from actual terrain configs or data.

- **`api/routers/meta.py`** (modified) -- Derive terrain types from `TerrainType` enum or scan scenario data, instead of returning a static list.

**Tests** (~15):
- config_overrides: submit run with overrides, verify they affect simulation output (e.g., modified `hit_probability_modifier` changes results)
- config_overrides: from-config endpoint passes overrides correctly
- Reinforcement event: campaign scenario emits reinforcement event with correct side/count
- Force time series: with reinforcement events, counts go up after arrival tick
- Terrain types: endpoint returns values matching actual enum/data

### 37b: DEW Battle Loop Wiring

Wire the Directed Energy Weapons engine into the simulation tick loop. The DEW engine, engagement routing, data files (5 weapons, 5 ammo, 3 units, 5 signatures, 2 sensors), and tests all exist from Phase 28.5 -- the only gap is that `battle.py` never calls the routing dispatcher.

**Root cause**: `battle.py:_execute_engagements()` (line ~810) calls `ctx.engagement_engine.execute_engagement()` directly for all engagements. This pre-dates Phase 27's `route_engagement()` dispatcher. DEW weapons fire but are treated as `DIRECT_FIRE` (ballistic physics instead of Beer-Lambert laser transmittance).

#### Battle Loop Integration

- **`stochastic_warfare/simulation/battle.py`** (modified) -- In `_execute_engagements()`:
  - Before calling `execute_engagement()`, check `wpn_inst.definition.category`
  - If `category == "DIRECTED_ENERGY"`: determine `EngagementType.DEW_LASER` or `DEW_HPM` based on weapon attributes (presence of `beam_power_kw` vs HPM fields)
  - Call `ctx.engagement_engine.route_engagement()` with the determined type, passing `dew_engine=ctx.dew_engine`
  - For non-DEW categories: continue calling `execute_engagement()` as before (backward compatible)
  - Handle the `EngagementResult` from `route_engagement()` the same way as from `execute_engagement()`

#### DEW Event Subscription

- **`stochastic_warfare/simulation/battle.py`** or **`simulation/recorder.py`** (modified) -- Subscribe to `DEWEngagementEvent` for recording. Currently published by `DEWEngine` but zero subscribers exist.

#### Air Defense DEW Routing

- **`stochastic_warfare/combat/air_defense.py`** (modified) -- Handle `ADUnitType.DEW` in air defense engagement logic. DEW AD units should route through `route_engagement()` with `EngagementType.DEW_LASER` instead of the standard missile/gun AD path.

#### Scenario YAML with DEW

- **`data/scenarios/taiwan_strait/scenario.yaml`** (modified) -- Add `dew_config: { enable_laser: true }` and include a DEW-equipped unit (e.g., `de_shorad_50kw`) on one side to exercise the DEW pipeline in an existing scenario.
- **`data/scenarios/suwalki_gap/scenario.yaml`** (modified) -- Add `dew_config` as a second scenario exercising DEW.

**Resolves deficits**: All 5 Phase 28.5 items (DEWEngagementEvent subscribers, dew_engine tick loop, no scenario references dew_config, ADUnitType.DEW routing, route_engagement not called from battle.py).

**Tests** (~20):
- DEW weapon fires through `route_engagement()` in battle loop (not `execute_engagement()`)
- DEW engagement produces `DEWEngagementResult` with laser transmittance physics
- `DEWEngagementEvent` is recorded by `SimulationRecorder`
- AD unit with `ADUnitType.DEW` routes correctly
- Scenario with `dew_config` loads and runs without error
- Non-DEW engagements still work (backward compatibility)

### 37c: End-to-End Smoke Test

Run every scenario through the full web UI pipeline and fix whatever breaks.

- **Parametrized pytest** over all 41 scenarios (27 modern + 14 era):
  - `POST /api/runs` with each scenario
  - Verify run completes with status `completed` (not `failed`)
  - Verify `terrain_json` and `frames_json` are captured (map data available)
  - Verify events are recorded (non-empty event list)
  - Verify force data is present (sides with unit counts)
- **Scenario editor smoke test**:
  - For a representative subset (~5 scenarios across eras), verify `POST /api/scenarios/validate` returns `valid: true`
  - Verify clone-and-tweak flow: load scenario, modify a field, validate, submit via `POST /api/runs/from-config`
- **Fix any scenario-specific issues** that surface (missing signatures, invalid configs, wiring gaps)

**Tests** (~20):
- Parametrized scenario completion test (41 scenarios, each a separate test case)
- Editor validation test for 5 representative scenarios
- Clone-and-run test for at least 2 scenarios

### Exit Criteria
- config_overrides from scenario editor actually affect simulation behavior
- Force strength charts correctly show reinforcement arrivals (counts go up)
- DEW engagements use Beer-Lambert laser physics, not ballistic fallback
- All 41 scenarios complete successfully through the API
- All 5 Phase 28.5 DEW deficits resolved
- All existing ~7,705 tests pass unchanged

---

## Phase 38: Map & Chart Enhancements — COMPLETE

**Goal**: Bring the tactical map and charts up to the quality level designed in the Block 3 brainstorm. Add FOW toggle, detection circles, elevation shading, cross-chart tick sync, and dark mode.

**Status**: Complete. 35 new tests (13 Python + 22 frontend vitest). 6 new + 57 modified = 63 files. 1 deficit resolved, 2 new cosmetic deficits logged. Descoped: `LAND_COVER_COLORS_DARK` palette, Plotly dark template, engagement arc age model (fade handled in rendering). Already done: destroyed X marker (Phase 35).

**Dependencies**: Phase 37 (bugs must be fixed before polish).

### 38a: FOW Toggle

Add a "Fog of War" view mode to the tactical map. When active, only show units that the selected side has detected.

- **Backend: Frame capture extension**
  - **`api/run_manager.py`** (modified) -- Extend `_capture_frame()` to include per-side detected unit IDs. For each frame, query the detection engine's `FogOfWarManager` (if available) to get each side's known contacts.
  - **`api/schemas.py`** (modified) -- Add `detected_by: dict[str, list[str]]` field to `MapUnitFrame` (mapping side -> list of unit IDs that side has detected). Optional field, defaults to empty dict for backward compat.

- **Frontend: FOW rendering**
  - **`frontend/src/components/map/MapControls.tsx`** (modified) -- Add "FOW" toggle and side selector dropdown (blue/red/all)
  - **`frontend/src/components/map/TacticalMap.tsx`** (modified) -- When FOW is active, filter rendered units to only those in the selected side's `detected_by` list. Undetected units are hidden entirely (not shown as question marks -- simpler and cleaner).
  - **`frontend/src/types/map.ts`** (modified) -- Add `detected_by` field to `MapUnitFrame` interface

**Tests** (~8):
- Frame capture includes detected_by data when FogOfWarManager exists
- Frame capture has empty detected_by when no fog of war (backward compat)
- FOW toggle filters units correctly in TacticalMap
- Side selector switches between blue/red/all views
- MapControls renders FOW toggle

### 38b: Map Visual Enhancements

Improve the tactical map's visual fidelity.

#### Elevation Shading

- **`frontend/src/components/map/TacticalMap.tsx`** (modified) -- In the terrain rendering pass, apply brightness modulation based on heightmap data from `TerrainResponse`. Higher elevation cells are slightly brighter, lower cells slightly darker. Use a linear scale from the terrain's min to max elevation.
- **`frontend/src/lib/terrain.ts`** (modified) -- Add `applyElevationShading(baseColor: string, elevation: number, minElev: number, maxElev: number): string` utility.

#### Detection Circles

- **`frontend/src/components/map/TacticalMap.tsx`** (modified) -- When a unit is selected and the "Detection Ranges" toggle is on, draw a semi-transparent circle at the unit's position with radius equal to the unit's primary sensor range. Sensor range data comes from unit definition (available in frame data or fetched from unit catalog API).
- **`frontend/src/components/map/MapControls.tsx`** (modified) -- Add "Detection Ranges" toggle.

#### Engagement Fade

- **`frontend/src/components/map/TacticalMap.tsx`** (modified) -- Engagement arcs now fade over 10 frames instead of instant appear/disappear. Each arc's opacity decays linearly from 1.0 to 0.0 over its lifetime. The `engagementArcs` data structure tracks age per arc.
- **`frontend/src/lib/engagementProcessing.ts`** (modified) -- Add `age` field to engagement arc data. Increment age each frame, remove arcs past max age.

#### Destroyed Unit Rendering

- **`frontend/src/lib/unitRendering.ts`** (modified) -- Destroyed units render with a red X overlay instead of just reduced opacity. More visually distinct.

**Tests** (~8):
- Elevation shading produces lighter color for higher elevation
- Detection circle drawn at correct world position and radius
- Engagement arcs age and fade over time
- Destroyed units render with X marker
- Toggles in MapControls control visibility of detection ranges

### 38c: Cross-Chart Tick Sync

Extend the tick sync marker line (currently only on `ForceStrengthChart`) to all chart types.

- **`frontend/src/pages/runs/tabs/ChartsTab.tsx`** (modified) -- Pass `tickMarker` prop to all chart components, not just `ForceStrengthChart`
- **`frontend/src/components/charts/EngagementTimelineChart.tsx`** (modified) -- Accept `tickMarker` prop, render vertical reference line at the specified tick
- **`frontend/src/components/charts/MoraleChart.tsx`** (modified) -- Accept `tickMarker` prop, render vertical reference line
- **`frontend/src/components/charts/EventActivityChart.tsx`** (modified) -- Accept `tickMarker` prop, render vertical reference line
- **Bidirectional sync** -- Clicking on any chart point sets `?tick=N` in URL params, which the map reads. Currently map -> chart is one-way; add chart -> map direction.

**Tests** (~6):
- Each chart component renders tick marker line when prop provided
- Each chart component hides marker when prop is undefined
- Click on chart data point updates URL tick param

### 38d: Dark Mode

Add a dark color scheme with persistent preference.

- **`frontend/src/hooks/useTheme.ts`** (new) -- `useTheme()` hook returning `{ theme: 'light' | 'dark', toggleTheme: () => void }`. Persists to `localStorage`. Applies `class="dark"` to `<html>` element.
- **`frontend/tailwind.config.js`** (modified) -- Enable `darkMode: 'class'`
- **`frontend/src/components/Layout.tsx`** (modified) -- Apply dark background/text classes. Add theme toggle button in sidebar footer.
- **`frontend/src/components/Sidebar.tsx`** (modified) -- Dark variant styling
- **`frontend/src/components/map/TacticalMap.tsx`** (modified) -- Dark palette for terrain colors (darker base, brighter unit markers for contrast)
- **`frontend/src/lib/terrain.ts`** (modified) -- Add `LAND_COVER_COLORS_DARK` variant with darker terrain palette
- **All page components** (modified) -- Add `dark:` Tailwind class variants for backgrounds, borders, text colors
- **Chart components** (modified) -- Pass Plotly `template: 'plotly_dark'` layout when dark mode is active

**Tests** (~8):
- `useTheme` hook toggles between light/dark
- `useTheme` persists preference to localStorage
- Layout applies dark class to html element
- Dark terrain colors are distinct from light colors
- Theme toggle renders in sidebar

### Exit Criteria
- FOW toggle hides undetected units on the map
- Elevation shading shows terrain relief
- Detection circles appear around selected units
- Engagement arcs fade over time
- All 4 chart types show tick sync marker from map playback
- Clicking a chart point updates the map playback position
- Dark mode toggles and persists across sessions
- All existing tests pass unchanged

---

## Phase 39: Quality, Performance & Packaging — COMPLETE

**Goal**: Close remaining test coverage gaps, optimize performance for large runs, and package the application for single-command startup.

**Status**: Complete. 22 new tests (6 Python + 16 vitest). 13 new + 14 modified files. 7 deficits resolved. Single-command startup via `uv run python -m api`. Docker packaging. Virtualized event list.

**Dependencies**: Phase 37 (integration fixes), Phase 38 is independent and can be parallelized.

### 39a: Test Coverage Gaps

Close the documented test gaps from Phases 34--36.

- **`frontend/src/__tests__/hooks/useBatchProgress.test.ts`** (new) -- Dedicated tests for the batch progress WebSocket hook: connection, message parsing, completion, error states
- **`frontend/src/__tests__/hooks/useViewportControls.test.ts`** (new) -- Dedicated tests for zoom, pan, fit-to-extent, zoom-at-cursor
- **`frontend/src/__tests__/pages/RunDetailPage.error.test.tsx`** (new) -- Tests for cancelled and error run states: error message display, retry button, cancelled status badge
- **`frontend/src/types/analysis.ts`** (new) -- TypeScript interfaces for compare/sweep API responses replacing `Record<string, unknown>`:
  - `CompareResult`: per-metric means, medians, Mann-Whitney U, p-value, effect size
  - `SweepResult`: parameter values, per-value metric statistics
- **`frontend/src/api/analysis.ts`** (modified) -- Use typed response interfaces instead of `Record<string, unknown>`
- **`frontend/src/lib/eventProcessing.ts`** (modified) -- Replace hardcoded morale state name strings and event type strings with exported constants

**Tests** (~12):
- useBatchProgress: connect, receive iteration updates, handle completion, handle error (~4)
- useViewportControls: zoom in/out, pan, fit-to-extent, zoom-at-cursor (~4)
- RunDetailPage error states: failed run display, cancelled run display (~2)
- Typed analysis responses: type checking validates (~2)

### 39b: Performance

Optimize for large simulation runs (10K+ events, 1000+ ticks).

- **Frame capture interval configurable**:
  - **`api/schemas.py`** (modified) -- Add `frame_interval` field to `RunSubmitRequest` (default: auto)
  - **`api/run_manager.py`** (modified) -- Use `frame_interval` from request when provided, falling back to `max(1, max_ticks // 500)` auto-calculation

- **Virtualized event list**:
  - **`frontend/package.json`** (modified) -- Add `@tanstack/react-virtual` dependency
  - **`frontend/src/pages/runs/tabs/EventsTab.tsx`** (modified) -- Replace flat list with virtualized list for runs with >500 events. Only render visible rows + buffer.

- **Lazy event loading**:
  - **`frontend/src/hooks/useRunEvents.ts`** (modified) -- Fetch events in pages (200 per page) instead of all at once. Infinite scroll triggers next page fetch.

**Tests** (~6):
- Frame interval: custom interval produces fewer/more frames
- Virtualized list: renders only visible items (not all 10K)
- Lazy loading: fetches first page, loads more on scroll trigger

### 39c: Startup & Packaging

Make the application runnable with a single command.

- **Production frontend build served by API**:
  - **`api/main.py`** (modified) -- Mount `frontend/dist/` as static files at `/` when the directory exists. Serve `index.html` for all non-API routes (SPA fallback). API routes (`/api/*`) take precedence.
  - **`frontend/vite.config.ts`** (modified) -- Set `build.outDir` to `../api/static` or keep `dist/` and configure API to find it.

- **`__main__.py` entry point**:
  - **`api/__main__.py`** (new) -- Enables `uv run python -m api` to start the full application. Imports `uvicorn`, runs `api.main:app` on configured host/port. Prints startup banner with URL.

- **Development startup script**:
  - **`scripts/dev.sh`** (new) -- Launches API server and frontend dev server in parallel. Traps SIGINT to kill both. Usage: `./scripts/dev.sh`
  - **`scripts/dev.ps1`** (new) -- PowerShell equivalent for Windows.

- **Docker**:
  - **`Dockerfile`** (new) -- Multi-stage build:
    - Stage 1: Node.js, `npm ci && npm run build` in `frontend/`
    - Stage 2: Python 3.12, `uv sync --extra api`, copy built frontend + Python source
    - Entrypoint: `uv run python -m api`
    - Exposes port 8000
  - **`.dockerignore`** (new) -- Exclude `.venv`, `node_modules`, `__pycache__`, `.git`, test files

- **README.md** (modified) -- Add "Quick Start (Web UI)" section:
  ```
  # One command (production)
  cd frontend && npm run build && cd ..
  uv run python -m api
  # Open http://localhost:8000

  # Docker
  docker build -t stochastic-warfare .
  docker run -p 8000:8000 stochastic-warfare
  ```

**Tests** (~4):
- `api/__main__.py` imports correctly and app is importable
- Static file serving: when `frontend/dist/` exists, serves `index.html` at `/`
- SPA fallback: non-API routes return `index.html`
- API routes still take precedence over static files

### 39d: Minor Polish

Small quality-of-life improvements.

- **Config diff view**:
  - **`frontend/src/pages/editor/ConfigDiff.tsx`** (new) -- Side-by-side comparison of original vs modified config in the scenario editor. Highlights changed fields. Shown in a collapsible panel below the YAML preview.

- **Better error display for failed runs**:
  - **`frontend/src/pages/runs/RunDetailPage.tsx`** (modified) -- When a run has status `failed`, show the Python traceback from `error_message` in a formatted code block, not just "Run failed".

- **`GET /api/meta/terrain-types` from data**:
  - Already addressed in 37a if not done there, or verify it's working.

**Tests** (~4):
- ConfigDiff highlights changed fields
- ConfigDiff shows no changes when config unchanged
- Failed run displays traceback in code block
- Failed run shows retry option

### Exit Criteria
- All documented test gaps from Phases 34--36 are closed
- Event list performs well with 10K+ events (virtualized)
- `uv run python -m api` serves the full application on one port
- `docker build && docker run` works end-to-end
- Config diff shows what changed in the editor
- Failed runs show meaningful error details
- All existing tests pass unchanged

---

## File Inventory

### Phase 37 (~10 modified + ~3 new)

| Action | File | Sub-phase |
|--------|------|-----------|
| MODIFY | `api/run_manager.py` -- apply config_overrides | 37a |
| MODIFY | `api/routers/runs.py` -- from-config overrides pass-through | 37a |
| MODIFY | `api/routers/meta.py` -- terrain types from data | 37a |
| MODIFY | `stochastic_warfare/simulation/campaign.py` -- reinforcement event | 37a |
| NEW | `stochastic_warfare/simulation/events.py` or modify `core/events.py` -- ReinforcementArrivedEvent | 37a |
| MODIFY | `frontend/src/lib/eventProcessing.ts` -- handle reinforcement events | 37a |
| MODIFY | `stochastic_warfare/simulation/battle.py` -- route_engagement for DEW | 37b |
| MODIFY | `stochastic_warfare/combat/air_defense.py` -- ADUnitType.DEW handling | 37b |
| MODIFY | `data/scenarios/taiwan_strait/scenario.yaml` -- add dew_config | 37b |
| MODIFY | `data/scenarios/suwalki_gap/scenario.yaml` -- add dew_config | 37b |
| NEW | `tests/api/test_phase_37_integration.py` | 37a/37c |
| NEW | `tests/unit/test_phase_37_dew_wiring.py` | 37b |

### Phase 38 (~15 modified + ~3 new)

| Action | File | Sub-phase |
|--------|------|-----------|
| MODIFY | `api/run_manager.py` -- FOW data in frame capture | 38a |
| MODIFY | `api/schemas.py` -- detected_by field | 38a |
| MODIFY | `frontend/src/types/map.ts` -- detected_by field | 38a |
| MODIFY | `frontend/src/components/map/MapControls.tsx` -- FOW toggle, detection toggle | 38a/38b |
| MODIFY | `frontend/src/components/map/TacticalMap.tsx` -- FOW filter, elevation, detection circles, engagement fade | 38a/38b |
| MODIFY | `frontend/src/lib/terrain.ts` -- elevation shading, dark palette | 38b/38d |
| MODIFY | `frontend/src/lib/engagementProcessing.ts` -- arc age/fade | 38b |
| MODIFY | `frontend/src/lib/unitRendering.ts` -- destroyed X marker | 38b |
| MODIFY | `frontend/src/pages/runs/tabs/ChartsTab.tsx` -- tick marker to all charts | 38c |
| MODIFY | `frontend/src/components/charts/EngagementTimelineChart.tsx` -- tick marker | 38c |
| MODIFY | `frontend/src/components/charts/MoraleChart.tsx` -- tick marker | 38c |
| MODIFY | `frontend/src/components/charts/EventActivityChart.tsx` -- tick marker | 38c |
| NEW | `frontend/src/hooks/useTheme.ts` | 38d |
| MODIFY | `frontend/tailwind.config.js` -- darkMode class | 38d |
| MODIFY | `frontend/src/components/Layout.tsx` -- dark mode classes, toggle | 38d |
| MODIFY | `frontend/src/components/Sidebar.tsx` -- dark mode classes | 38d |
| MODIFY | All page/component files -- add `dark:` class variants | 38d |

### Phase 39 (~10 modified + ~8 new)

| Action | File | Sub-phase |
|--------|------|-----------|
| NEW | `frontend/src/__tests__/hooks/useBatchProgress.test.ts` | 39a |
| NEW | `frontend/src/__tests__/hooks/useViewportControls.test.ts` | 39a |
| NEW | `frontend/src/__tests__/pages/RunDetailPage.error.test.tsx` | 39a |
| NEW | `frontend/src/types/analysis.ts` | 39a |
| MODIFY | `frontend/src/api/analysis.ts` -- typed responses | 39a |
| MODIFY | `frontend/src/lib/eventProcessing.ts` -- extract constants | 39a |
| MODIFY | `api/schemas.py` -- frame_interval field | 39b |
| MODIFY | `api/run_manager.py` -- configurable frame interval | 39b |
| MODIFY | `frontend/src/pages/runs/tabs/EventsTab.tsx` -- virtualized list | 39b |
| MODIFY | `frontend/src/hooks/useRunEvents.ts` -- paginated fetch | 39b |
| MODIFY | `api/main.py` -- static file serving + SPA fallback | 39c |
| NEW | `api/__main__.py` -- entry point | 39c |
| NEW | `scripts/dev.sh` -- dev startup script | 39c |
| NEW | `scripts/dev.ps1` -- Windows dev startup | 39c |
| NEW | `Dockerfile` | 39c |
| NEW | `.dockerignore` | 39c |
| MODIFY | `README.md` -- Quick Start section | 39c |
| NEW | `frontend/src/pages/editor/ConfigDiff.tsx` | 39d |
| MODIFY | `frontend/src/pages/runs/RunDetailPage.tsx` -- error display | 39d |

---

## Test Targets

| Phase | Sub-phase | New Tests | Focus |
|-------|-----------|-----------|-------|
| 37a | Bug fixes | ~15 | config_overrides, reinforcements, terrain types |
| 37b | DEW wiring | ~20 | Battle loop, AD routing, DEW events, scenarios |
| 37c | E2E smoke test | ~20 | All 41 scenarios + editor validation |
| 38a | FOW toggle | ~8 | Frame data, filter rendering, side selection |
| 38b | Map visuals | ~8 | Elevation, detection circles, fade, destroyed markers |
| 38c | Chart sync | ~6 | Tick marker on all charts, bidirectional |
| 38d | Dark mode | ~8 | Theme hook, persistence, dark classes, chart template |
| 39a | Test gaps | ~12 | useBatchProgress, useViewportControls, error states |
| 39b | Performance | ~6 | Frame interval, virtualized list, lazy loading |
| 39c | Packaging | ~4 | Static serving, SPA fallback, entry point |
| 39d | Polish | ~4 | Config diff, error display |
| | **Total** | **~111** | |

---

## Implementation Order

```
37a (bug fixes) ──> 37b (DEW wiring) ──> 37c (E2E smoke test)
                                              │
                                              ▼
                                38a ──> 38b ──> 38c ──> 38d
                                              │
                                              ▼
                                39a + 39b (parallel) ──> 39c ──> 39d
```

Phase 37 is strictly sequential: fix bugs, wire DEW, then smoke-test everything. Phase 38 sub-phases are mostly sequential (FOW needs frame data before rendering, dark mode is last since it touches many files). Phase 39a and 39b are independent and can run in parallel; 39c (packaging) and 39d (polish) follow.

---

## Deficit Resolution

| Deficit | Origin | Resolved In |
|---------|--------|-------------|
| ~~DEWEngagementEvent has zero subscribers~~ | Phase 28.5 | 37 (closed — recorder catches via base Event) |
| ~~dew_engine not used in simulation tick loops~~ | Phase 28.5 | **37 ✅** |
| No scenario YAML references dew_config | Phase 28.5 | Deferred |
| ADUnitType.DEW not handled in air defense | Phase 28.5 | Deferred |
| ~~route_engagement() not called from battle.py~~ | Phase 28.5 | **37 ✅** |
| ~~config_overrides accepted but not applied~~ | Phase 32 | **37 ✅** |
| GET /api/meta/terrain-types hardcoded | Phase 32 | 39d |
| ~~Force time series assumes no reinforcements~~ | Phase 34 | **37 ✅** |
| useBatchProgress no dedicated test | Phase 34 | 39a |
| RunDetailPage tests don't cover error states | Phase 34 | 39a |
| Analysis API responses untyped | Phase 34 | 39a |
| Hardcoded morale/event strings | Phase 34 | 39a |
| useViewportControls no dedicated test | Phase 35 | 39a |
| ~~Only ForceStrengthChart shows tick sync~~ | Phase 35 | **38 ✅** |
| Frame capture interval not configurable | Phase 35 | 39b |

**Total**: 15 deficits resolved across Block 4.

---

## Verification

```bash
# Phase 37: integration fixes + DEW + E2E
uv run python -m pytest tests/ --tb=short -q
cd frontend && npm test && npm run build

# Phase 38: map/chart/dark mode
cd frontend && npm test && npm run build

# Phase 39: packaging
uv run python -m api                              # single-command startup
docker build -t stochastic-warfare .               # Docker build
docker run -p 8000:8000 stochastic-warfare         # Docker run
curl http://localhost:8000/api/health               # API responds
curl http://localhost:8000/ | head -5               # Frontend served

# Full regression
uv run python -m pytest --tb=short -q
cd frontend && npm test
```
