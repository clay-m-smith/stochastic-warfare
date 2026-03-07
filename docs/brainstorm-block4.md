# Stochastic Warfare -- Block 4 Brainstorm

## Context

Blocks 1--3 (Phases 0--36) built the complete simulation engine, 5 historical eras, ~700 YAML data files, a REST API, a full React web application, and a documentation site. ~7,705 tests passing. 41 scenarios (27 modern + 14 historical). Zero TODOs/FIXMEs in the codebase.

Block 3 delivered the web application. Block 4 is the first opportunity to use it in anger and fix what surfaces. The goal: make the product reliable, polished, and self-contained enough that someone can clone, install, and run a full simulation through the browser without friction.

---

## Current Inventory

### What Works
- **Engine**: 19 modules + sub-packages, multi-domain (land/air/naval/sub/space/EW/CBRN), 5 eras, full campaign + battle management
- **API**: 25 REST endpoints + 2 WebSocket, async run execution, SQLite persistence, batch MC, analysis
- **Frontend**: Scenario browser, unit catalog, run submission, live WebSocket progress, 5 interactive chart types, battle narrative, tactical map with playback, scenario editor (clone-and-tweak), export (JSON/CSV/YAML/print), keyboard shortcuts
- **Docs**: MkDocs site live at GitHub Pages, 8 user-facing guides
- **Data**: 41 scenarios, 46+ unit types, 51 weapons, 63 ammo types, 16 sensors, 21 doctrines, 13 commanders
- **Tests**: 7,474 Python + 231 vitest = 7,705 total, zero TODOs

### What's Broken / Unwired

**DEW (Directed Energy Weapons) -- completely unwired** (5 deficits from Phase 28.5):
- `DEWEngagementEvent` published but zero subscribers
- `dew_engine` wired in `ScenarioLoader` but never called in `battle.py` tick loop
- No scenario YAML references `dew_config` (engine exists but is never exercised)
- `ADUnitType.DEW` exists but not handled in air defense engagement routing
- `route_engagement()` not called from `battle.py` -- DEW routing untested in loop

**config_overrides not applied** (Phase 32):
- API accepts `config_overrides` dict and stores it in the DB, but it's never injected into `CampaignScenarioConfig` before `ScenarioLoader.load()`. The calibration overrides from the scenario editor aren't actually applied.

**Force time series reconstruction ignores reinforcements** (Phase 34):
- `eventProcessing.ts` builds the force strength chart by walking destruction events and decrementing from initial totals. Reinforcement arrivals never increment the count back up.

### What's Deferred but Impactful

**Map enhancements** (Phase 35 deferrals):
- FOW toggle: show only one side's known contacts vs omniscient view
- Detection circles: sensor range visualization
- Elevation shading: terrain relief on the map
- Engagement fade: arcs fade over time instead of appearing/disappearing

**Chart sync** (Phase 35):
- Only `ForceStrengthChart` shows the tick sync marker line from map playback. The other 3 chart types don't.

**UI polish** (Phase 36 deferrals):
- Dark mode
- Config diff view (show changes from original scenario)
- Scenario save to server filesystem
- Virtualized lists for large event logs

**Hardcoded strings** (Phase 34):
- Morale state names and event type strings in `eventProcessing.ts` -- fragile if engine adds new types
- Analysis API responses are untyped `Record<string, unknown>` -- compare/sweep return free-form dicts

---

## Gap Analysis: What Matters for First Real Use

When someone runs the web UI for the first time, they will:

1. **Browse scenarios** -- works well, all 41 scenarios load
2. **Run a scenario** -- works, WebSocket progress streams correctly
3. **View results** -- charts render, narrative generates, map plays back
4. **Clone and tweak** -- editor loads, but **calibration overrides don't actually apply** (config_overrides bug)
5. **Run a DEW scenario** -- **impossible**, no scenario exercises DEW and the engine doesn't call the DEW engine in the tick loop
6. **Look at force charts for a campaign with reinforcements** -- **force counts will be wrong** (never go back up)

The critical bugs are #4 (calibration overrides silently ignored) and #6 (wrong chart data). #5 is a feature gap -- DEW exists in the engine but isn't usable.

Beyond bugs, the biggest friction points will be:
- **No "just run it" script** -- must manually start API server in one terminal, frontend in another
- **No production build** -- no way to serve the built frontend from the API server
- **Large event logs are slow** -- no pagination or virtualization in the event list

---

## Proposed Block 4: Integration, Polish & Packaging

### Phase 37: Integration Fixes & End-to-End Validation

Fix the broken integration points that will surface during real use. Then run every scenario through the full web UI pipeline to catch any remaining issues.

**37a: Critical Bug Fixes**
- **Apply config_overrides**: In `api/run_manager.py`, merge `config_overrides` into the loaded `CampaignScenarioConfig` before creating the `SimulationContext`. This makes calibration slider changes in the scenario editor actually affect the simulation.
- **Force time series reinforcements**: Update `eventProcessing.ts` to handle reinforcement arrival events (increment force counts when units arrive).
- **Terrain types from data**: Replace hardcoded terrain type list in `GET /api/meta/terrain-types` with values derived from actual terrain configs or scenario data.

**37b: DEW Wiring**
- Wire `dew_engine` into `battle.py` tick loop (call DEW engagement evaluation during combat phase)
- Handle `ADUnitType.DEW` in air defense engagement routing
- Wire `route_engagement()` call for DEW engagement types
- Subscribe to `DEWEngagementEvent` for recording/damage application
- Create at least one scenario YAML that references `dew_config` and exercises DEW units
- Add a `dew_config` section to one existing modern scenario (e.g., Taiwan Strait or Suwalki Gap)

**37c: End-to-End Smoke Test**
- Run every scenario through `POST /api/runs` and verify it completes without error
- Verify map renders for each (terrain + frames captured)
- Verify charts render for each (force strength, engagements, morale)
- Fix any scenario-specific issues that surface (missing signatures, invalid configs, wiring gaps)
- Verify scenario editor can clone any scenario, validate, and run the clone

**Tests**: ~40-60 new (Python integration + vitest)

---

### Phase 38: Map & Chart Enhancements

Bring the tactical map and charts up to the quality level planned in the Block 3 design.

**38a: FOW Toggle**
- Add a "Fog of War" toggle to `MapControls`
- When FOW is active for a side, only show units that side has detected (requires detection event data in frames or a separate detection layer)
- Implementation: extend frame capture to include per-side detected unit IDs, filter rendering by selected side
- Omniscient view (default, current behavior) shows all units

**38b: Map Visual Enhancements**
- Detection circles: optional sensor range circles around selected units (toggleable in MapControls)
- Elevation shading: use heightmap data from terrain response to apply subtle brightness variation to terrain cells
- Engagement fade: arcs decay over 10 ticks instead of instant appear/disappear
- Better destroyed unit rendering: X marker or grayed-out icon instead of just opacity

**38c: Cross-Chart Tick Sync**
- Extend tick sync marker line to EngagementTimelineChart, MoraleChart, and EventActivityChart
- All charts read `?tick=N` from URL params and draw the vertical reference line
- Clicking on a chart point sets `?tick=N` (bidirectional sync)

**38d: Dark Mode**
- Tailwind dark mode classes throughout the frontend
- `useTheme` hook with localStorage persistence
- Toggle in sidebar footer
- Map canvas dark palette (darker terrain colors, brighter unit markers)
- Chart theme integration (Plotly dark layout)

**Tests**: ~30-40 new vitest

---

### Phase 39: Quality, Performance & Packaging

Close remaining quality gaps, optimize performance for large runs, and package the application for single-command startup.

**39a: Test Coverage Gaps**
- `useBatchProgress` dedicated test file
- `useViewportControls` dedicated test file
- RunDetailPage cancelled/error state tests
- Typed analysis API responses (define TypeScript interfaces for compare/sweep results)

**39b: Performance**
- Frame capture interval configurable (add to `EngineConfig` or API run request)
- Virtualized event list (`react-window` or `@tanstack/react-virtual`) for runs with 10K+ events
- Lazy-load event data (fetch pages on scroll, not all at once)

**39c: Startup & Packaging**
- **Single-command dev startup**: Script/Makefile that launches both API server and frontend dev server
- **Production build**: Vite `npm run build` output served by FastAPI as static files (mount `frontend/dist/` at `/`)
- **Single-command production**: `uv run python -m api` starts the API server serving the built frontend -- one command, one port
- **Docker**: `Dockerfile` that builds both Python and frontend, runs uvicorn serving everything on port 8000
- **README update**: Add "Quick Start (Web UI)" section with the single command

**39d: Minor Polish**
- Config diff view: show what changed from original scenario in the editor (simple before/after comparison)
- Hardcoded morale states and event types -> derive from API or use constants
- `GET /api/meta/terrain-types` from data instead of hardcoded list
- Better error messages when a run fails (show the Python traceback in the UI)

**Tests**: ~20-30 new

---

## Deferred Beyond Block 4

These are real features but not needed for the "make it work well" goal:

| Item | Why Deferred |
|------|-------------|
| Scenario save to server filesystem | Clone-and-tweak + download YAML is sufficient |
| Real PDF generation | `window.print()` with CSS works |
| Drag-and-drop unit reordering | Click-based add/remove is sufficient |
| Real-time map streaming during run | Post-hoc replay covers the core use case |
| Multi-run map overlay | Comparison charts are sufficient |
| Mobile-optimized touch controls | Desktop-first product |
| Authentication / multi-user | Single-user by design |
| SGP4/TLE orbital mechanics | Keplerian is sufficient for game-scale simulation |
| Individual carrier deck spots | Aggregate model is sufficient |
| Cooperative jamming | Single-jammer model is sufficient |
| All the Phase 6 logistics edge cases | Don't materially change outcomes |
| All the Phase 8 planning simplifications | Analytical COA wargaming is working |
| All the Phase 17 space simplifications | Statistical models are sufficient |

---

## Block 4 Summary

| Phase | Focus | Estimated Tests | Key Deliverables |
|-------|-------|----------------|-----------------|
| 37 | Integration Fixes & E2E Validation | ~50 | config_overrides applied, DEW wired, reinforcement charts fixed, all 41 scenarios smoke-tested |
| 38 | Map & Chart Enhancements | ~35 | FOW toggle, detection circles, elevation shading, cross-chart tick sync, dark mode |
| 39 | Quality, Performance & Packaging | ~25 | Test gaps closed, virtualized lists, single-command startup, Docker, production build |
| | **Total** | **~110** | |

**Principle**: Block 4 is a tightening block, not a feature block. No new engine subsystems. No new simulation domains. Fix what's broken, polish what's rough, package what's scattered. The goal is that after Block 4, someone can `docker run` or `uv run python -m api` and use the full product through a browser without any friction or surprises.

---

## Implementation Order

```
37a (bug fixes) -> 37b (DEW wiring) -> 37c (E2E smoke test)
                                            |
                                            v
                              38a/38b/38c/38d (parallel within phase)
                                            |
                                            v
                              39a/39b (parallel) -> 39c (packaging) -> 39d (polish)
```

Phase 37 must come first -- it fixes the bugs that would otherwise surface during Phase 38/39 work. Phases 38 and 39 are largely independent and could be reordered, but map enhancements (38) are more user-visible and should come before packaging (39).

---

## Verification

```bash
# After Phase 37: all scenarios run through API without error
uv run python -m pytest tests/api/ --tb=short -q
uv run python -m pytest --tb=short -q

# After Phase 38: frontend tests pass with new components
cd frontend && npm test && npm run build

# After Phase 39: single-command startup works
uv run python -m api                     # serves API + built frontend at :8000
docker build -t stochastic-warfare .     # Docker build succeeds
docker run -p 8000:8000 stochastic-warfare  # full stack in one container
```
