# Stochastic Warfare — Claude Code Instructions

## Project Overview
High-fidelity, high-resolution wargame simulator. Multi-scale (campaign → battlefield → battle → unit level) with stochastic/signal-processing-inspired models (Markov chains, Monte Carlo, Kalman filters, noise models, queueing theory). Headless Python engine first; matplotlib for validation; full UI deferred. Modern era (Cold War–present) as prototype. Maritime warfare fully integrated, not deferred.

**Current status**: Phase 44 complete (Environmental & Subsystem Integration — Block 5 partial) + all prior phases. ~8,039 tests passing (~7,767 Python + 272 frontend vitest). Block 1 COMPLETE (0–24). Block 2 COMPLETE (25–30). Block 3 COMPLETE (31–36, full web application). Block 4 COMPLETE (37–39). Block 5 IN PROGRESS (40–44 of 47). MVP complete (phases 0-10). Post-MVP Phases 11-23 delivered — Phase 11: 15 deficit fixes across ~20 source files. Phase 12: 16 deficits resolved + 2 new domains (civilian population, strategic air campaigns/IADS) across 12 new + ~25 modified source files. Phase 13: Performance optimization (STRtree, Kalman cache, LOS cache, viewshed vectorization, auto-resolve, force aggregation, Numba JIT, A* precompute, MC parallelism) across 2 new + ~10 modified source files. Phase 14: Developer tooling (MCP server, analysis utilities, visualization, 7 Claude skills) across 12 new source files + 7 skill files. Phase 15: Real-world terrain pipeline (SRTM elevation, Copernicus land cover, OSM infrastructure, GEBCO bathymetry) across 5 new source files + 1 modified + 1 download script. Phase 16: Electronic Warfare (EA/EP/ES — J/S ratio, GPS spoofing, ECCM, SIGINT) across 8 new source files + 5 modified + 14 YAML + 2 scenarios. Phase 17: Space & Satellite (orbital mechanics, GPS dependency, space ISR, early warning, SATCOM, ASAT warfare) across 9 new source files + 7 modified + 12 YAML + 3 scenarios. Phase 18: CBRN (Pasquill-Gifford dispersal, contamination grids, MOPP protection, probit casualties, nuclear blast/thermal/radiation/EMP/fallout) across 10 new source files + 6 modified + 15 YAML + 2 scenarios. Phase 19: Doctrinal AI Schools (9 named schools as Strategy-pattern classes — Clausewitz, Maneuver, Attrition, AirLand Battle, Air Power, Sun Tzu, Deep Battle, Mahanian, Corbettian — with assessment weight overrides, decision score adjustments, OODA multipliers, COA weight overrides, opponent modeling) across 10 new source files + 6 modified + 9 YAML. Phase 20: WW2 Era (era framework — Era enum, EraConfig, module gating, era-aware YAML loading; WW2 data package — 15 units, 8 weapons, 13 ammo, 4 sensors, 15 signatures, 4 doctrines, 3 commanders, 3 scenarios; engine extensions — naval gunnery bracket firing, convoy/wolf pack, strategic bombing CEP) across 4 new source files + 2 modified + ~60 YAML. Phase 21: WW1 Era (WW1 era config + data package — 6 units, 8 weapons, 10 ammo, 5 sensors, 6 signatures, 3 doctrines, 3 commanders, 2 comms, 2 scenarios; engine extensions — trench system STRtree overlay, creeping barrage aggregate model, gas warfare CBRN adapter) across 3 new source files + 4 modified + ~45 YAML. Phase 22: Napoleonic Era (Napoleonic era config + data package — 10 units, 9 weapons, 9 ammo, 3 sensors, 10 signatures, 3 doctrines, 3 commanders, 2 comms, 2 scenarios; engine extensions — volley fire aggregate model, melee combat, cavalry charge state machine, Napoleonic formations, courier C2, foraging logistics) across 6 new source files + 2 modified + ~53 YAML. Phase 23: Ancient & Medieval Era (Ancient/Medieval era config + data package — 7 units, 13 weapons, 8 ammo, 3 sensors, 7 signatures, 3 doctrines, 3 commanders, 2 comms, 3 scenarios; engine extensions — massed archery aggregate model, ancient formations, siege state machine, oar-powered naval, visual signals C2, melee extension with reach/flanking) across 5 new source files + 4 modified + ~49 YAML.

## Python & Package Management
**Requires Python >=3.12** (pinned to 3.12.10 via `.python-version`).

**Use `uv` exclusively.** Never use bare `pip install`. Always use `uv add`, `uv sync`, etc. Direct `pip` may target system Python instead of the project venv.

Setup from scratch:
```bash
uv sync --extra dev    # creates .venv, installs all deps including pytest/matplotlib
```

Use `uv run` to execute all Python commands — this automatically uses the correct venv without manual activation:
```bash
uv run python -m pytest --tb=short -q
```

Do NOT use `source .venv/Scripts/activate` — use `uv run` instead.

## Running Tests
```bash
uv run python -m pytest --tb=short -q          # default: excludes @pytest.mark.slow
uv run python -m pytest -m slow --tb=short -q   # 1000-run MC validation only
```

## Architecture

### 12 Modules (strict dependency graph)
`core` → `coordinates` → `terrain` → `environment` → `entities` → `movement` → `detection` → `combat` → `morale` → `c2` → `logistics` → `simulation`

Dependencies flow downward. Terrain never imports environment. Environment may read terrain (one-way). Entities are data, modules are behavior (ECS-like separation).

### Simulation Loop
Hybrid — tick-based outer loop (variable resolution per scale) + event-driven within ticks.

### Spatial Model
Layered hybrid — graph (strategic), grid (operational/tactical), continuous (unit-level). All raster grids share: Grid[0,0] = SW corner, row increases northward, col increases eastward.

### Key Dependencies
`numpy`, `scipy`, `pydantic`, `pyproj`, `shapely`, `networkx` (+ `pytest`, `pytest-cov`, `matplotlib`, `httpx`, `pytest-asyncio` for dev). Optional: `numba` (perf), `mcp[cli]` (mcp), `rasterio`/`xarray` (terrain), `mkdocs-material` (docs), `fastapi`/`uvicorn`/`aiosqlite`/`pydantic-settings` (api).

## Project Conventions
- **PRNG discipline**: No `np.random` module-level calls. All randomness via `RNGManager.get_stream(ModuleId)` → `np.random.Generator`. No bare `random` module.
- **Deterministic iteration**: No `set()` or unordered dict driving simulation logic.
- **State protocol**: All stateful classes implement `get_state() -> dict` and `set_state(dict) -> None`.
- **Coordinate system**: ENU meters internally. Geodetic only for import/export/display. `pyproj` for transforms.
- **Dependencies flow downward**: terrain modules never import environment; environment may read terrain.
- **Entities are data, modules are behavior** (ECS-like separation).
- **No global singletons**: RNGManager, EventBus, Clock are explicitly instantiated and passed.
- **Config**: pydantic BaseModel for all configuration classes.
- **Unit definitions**: Data-driven YAML configs validated by pydantic. Engine defines behaviors, YAML parameterizes instances.
- **Logging**: `from stochastic_warfare.core.logging import get_logger; logger = get_logger(__name__)` — no bare `print()` in sim core.
- **Type hints**: Required on all public API functions.

## Frontend (Phase 33+)
- **Stack**: Vite + React 18 + TypeScript 5.7 + Tailwind v3 + TanStack Query v5 + React Router v6 + Plotly.js
- **Package manager**: npm (not pnpm). Lives in `frontend/` at repo root.
- **Dev server**: `cd frontend && npm run dev` — Vite at localhost:5173, proxies `/api` to localhost:8000
- **Tests**: `npm test` — vitest + RTL + jsdom. All tests mock `fetch`, no API server required.
- **Build**: `npm run build` — TypeScript check + Vite production bundle
- **API client**: Hand-written typed fetch wrappers in `src/api/`. Types mirror `api/schemas.py`.
- **State management**: TanStack Query only. No Redux/Zustand. UI state via local state or URL search params.
- **Charts**: Plotly.js via `react-plotly.js` + `plotly.js-dist-min`. Lazy-loaded via `React.lazy`. Mock `PlotlyChart` wrapper in tests.

## Testing
- **Shared fixtures**: `tests/conftest.py` provides `rng`, `event_bus`, `sim_clock`, `rng_manager` fixtures + `make_rng()`, `make_clock()`, `make_stream()` helpers. Use for all new test files (Phase 8+).
- Existing test files have their own local helpers — no need to migrate.

## Development Process
- **MVP phases** (0–10): defined in `docs/development-phases.md`. All complete.
- **Post-MVP phases** (11–24): defined in `docs/development-phases-post-mvp.md`. Design thinking in `docs/brainstorm-post-mvp.md`.
- Devlog: `docs/devlog/` — one markdown file per phase, living documents. Update the relevant phase log when completing work.
- Run `/cross-doc-audit` after completing phases or changing architecture
- Run `/validate-conventions` after writing simulation core code
- All design docs are **living documents** — propagate implementation decisions back to all affected docs via `/update-docs`
- **Post-MVP lockstep**: When completing Phase 11+, update ALL of: CLAUDE.md, project-structure.md, `development-phases-post-mvp.md` (phase status + module index), `devlog/index.md` (phase status + refinement entries), phase devlog, README.md, MEMORY.md. New deficits must be added to both devlog index AND deficit-to-phase mapping.

## Available Skills
| Skill | Purpose |
|-------|---------|
| `/research-military` | Military doctrine, historical data, theorist/philosopher writings (tiered sources) |
| `/research-models` | Mathematical, stochastic, signal processing modeling approaches (tiered sources) |
| `/validate-conventions` | Check code against PRNG, determinism, coordinate, logging conventions |
| `/update-docs` | Propagate design decisions to brainstorm, specs, memory (MVP + post-MVP) |
| `/spec` | Draft/update module specification before implementation |
| `/backtest` | Structure validation against historical engagement data |
| `/audit-determinism` | Deep PRNG discipline audit — trace all stochastic paths |
| `/design-review` | Review module design against military theory and architecture |
| `/cross-doc-audit` | Verify alignment across all docs (MVP + post-MVP, 13 checks) |
| `/simplify` | Review changed code for reuse, quality, and efficiency |
| `/profile` | Performance profiling — cProfile analysis, hotspot identification, benchmarking |
| `/scenario` | Interactive scenario creation/editing walkthrough (with mandatory equipment mapping validation) |
| `/validate-data` | Validate unit/scenario YAML data integrity — equipment maps, sensor presence, unit type refs |
| `/compare` | Run two configs and summarize with statistical comparison |
| `/what-if` | Quick parameter sensitivity from natural language questions |
| `/timeline` | Generate battle narrative from simulation run |
| `/orbat` | Interactive order of battle builder |
| `/calibrate` | Auto-tune calibration overrides to match historical data |
| `/postmortem` | Structured retrospective after completing a phase — catches integration gaps, deficits, test quality issues |
| `/evaluate-scenarios` | Run all scenarios, compare against baseline, report improvements/regressions |

## Documentation Map
| Document | Purpose |
|----------|---------|
| `docs/brainstorm.md` | Architecture decisions, domain decomposition, rationale |
| `docs/brainstorm-post-mvp.md` | Post-MVP design thinking (deficits, EW, Space, CBRN, eras, tooling, unconventional warfare, strategic air campaigns/IADS) |
| `docs/development-phases.md` | MVP phase roadmap (0–10), module-to-phase index |
| `docs/development-phases-post-mvp.md` | Post-MVP phase roadmap (11–24), deficit-to-phase mapping |
| `docs/development-phases-block2.md` | Block 2 phase roadmap (25–30), integration & hardening |
| `docs/brainstorm-block3.md` | Block 3 design thinking (docs site, API, UI, tactical map) |
| `docs/development-phases-block3.md` | Block 3 phase roadmap (31–36), UX/UI pivot |
| `docs/brainstorm-block4.md` | Block 4 design thinking (integration gaps, polish, packaging) |
| `docs/development-phases-block4.md` | Block 4 phase roadmap (37–39), tightening & deployment |
| `docs/brainstorm-block5.md` | Block 5 design thinking (core combat fidelity, scenario analysis) |
| `docs/development-phases-block5.md` | Block 5 phase roadmap (40–47), battle loop wiring |
| `docs/specs/project-structure.md` | Full package tree, module decomposition, dependency graph |
| `docs/devlog/` | Per-phase implementation logs (`index.md` tracks status) |
| `docs/skills-and-hooks.md` | Dev infrastructure documentation |
| `docs/specs/` | Per-module specifications (written before implementation) |
| `README.md` | Project overview, setup, architecture summary, status |
| `mkdocs.yml` | MkDocs site configuration (Phase 31) |
| `docs/index.md` | Docs site landing page (Phase 31) |
| `docs/guide/` | User-facing guides (getting started, web UI, scenarios) |
| `docs/concepts/` | Architecture overview, mathematical models (Phase 31) |
| `docs/reference/` | API reference, eras, units & equipment (Phase 31) |

## Completed Phases

All phase details are in `docs/devlog/` (one file per phase). Below is a summary for quick reference.

### MVP Phases (0-10) — All Complete

| Phase | Focus | Tests | Key Deliverables |
|-------|-------|-------|------------------|
| 0 | Project Scaffolding | 97 | Core infra: types, logging, RNG, clock, event bus, config, checkpoint, coordinate transforms |
| 1 | Terrain & Environment | 270 | 20 modules: heightmap, weather (Markov), astronomy (Meeus), sea state, LOS (DDA), acoustics, EM propagation. Deps: shapely, networkx |
| 2 | Entities & Movement | 424 | 28 modules: unit classes, hierarchy, task-org, A* pathfinding, formations, naval/sub/airborne movement. 13 YAML unit/org defs |
| 3 | Detection & Intelligence | 296 | 12 modules: unified SNR detection (erfc), Kalman tracking, sonar, intel fusion, fog of war. 19 YAML sensor/signature defs |
| 4 | Combat & Morale | 634 | 28 modules: RK4 ballistics, DeMarre penetration, Wayne Hughes salvo, Markov morale, all domains. 47 YAML weapon/ammo defs |
| 5 | C2 Infrastructure | 345 | 17 modules: command authority, comms (Bernoulli), EMCON, ROE, orders, mission command, naval C2. 8 YAML comms defs |
| 6 | Logistics & Supply | 336 | 14 modules: NATO supply classes, networkx routing, Poisson maintenance, M/M/c medical, engineering. 11 YAML defs |
| 7 | Engagement Validation | 188 | 5 modules: MC harness, deferred damage, 3 historical engagements (73 Easting, Falklands, Golan). ~30 YAML defs |
| 8 | AI & Planning | 575 | 14 modules: OODA FSM, commander personalities, doctrine templates, MDMP, Lanchester COA wargaming. 16 YAML defs |
| 9 | Simulation Orchestration | 372 | 7 modules: master engine, tick resolution switching, BattleManager, CampaignManager, recorder, metrics. 4 YAML scenarios |
| 10 | Campaign Validation | 196 | 5 modules: campaign MC, AI validation, performance profiling. 2 historical campaigns (Golan, Falklands) |

### Post-MVP Phases (11-24) — All Complete

| Phase | Focus | Tests | Key Deliverables |
|-------|-------|-------|------------------|
| 11 | Core Fidelity Fixes | 109 | 15 surgical fixes: fire rate cooldown, Mach drag, armor obliquity, FOV, Mahalanobis gating, fuel gating |
| 12 | Deep Systems Rework | 259 | 12 new files: continuous Markov morale, multi-hop C2, multi-echelon supply, energy-maneuverability, civilian population, IADS |
| 13 | Performance Optimization | 170 | STRtree, LOS cache, viewshed vectorization, Kalman cache, Numba JIT, A* precompute, MC parallelism. Opt dep: numba |
| 14 | Tooling & Dev Experience | 125 | MCP server (7 tools), analysis (narrative, tempo FFT, A/B comparison, sensitivity), visualization, 7 skills. Opt dep: mcp |
| 15 | Real-World Terrain | 97 | SRTM elevation, Copernicus land cover, OSM infrastructure, GEBCO bathymetry pipelines. Opt deps: rasterio, xarray |
| 16 | Electronic Warfare | 143 | 8 modules: J/S jamming, GPS spoofing, ECCM, SIGINT geolocation, full EA/EP/ES chain. 14 YAML + 2 scenarios |
| 17 | Space & Satellite | 149 | 9 modules: Keplerian orbits, GPS/DOP, space ISR, early warning, SATCOM, ASAT + debris cascade. 12 YAML + 3 scenarios |
| 18 | CBRN Effects | 155 | 10 modules: Pasquill-Gifford dispersal, contamination grids, MOPP, probit casualties, nuclear blast/thermal/radiation/EMP/fallout. 15 YAML + 2 scenarios |
| 19 | Doctrinal AI Schools | 189 | 10 modules: 9 Strategy-pattern schools (Clausewitz, Maneuver, Attrition, AirLand, Air Power, Sun Tzu, Deep Battle, Mahanian, Corbettian). 9 YAML |
| 20 | WW2 Era | 137 | Era framework (EraConfig, module gating, era-aware loading) + WW2 data (~60 YAML) + 3 engine extensions (naval gunnery, convoy, strategic bombing). 3 scenarios |
| 21 | WW1 Era | 182 | WW1 era config + data (~45 YAML) + 3 engine extensions (trench system, creeping barrage, gas warfare). 2 scenarios |
| 22 | Napoleonic Era | 233 | Napoleonic era config + data (~53 YAML) + 6 engine extensions (volley fire, melee, cavalry, formations, courier C2, foraging). 2 scenarios |
| 23 | Ancient & Medieval Era | 321 | Ancient/Medieval era config + data (~49 YAML) + 5 new engine extensions (archery, ancient formations, siege, naval oar, visual signals) + melee extension. 3 scenarios |
| 24 | Unconventional & Prohibited Warfare | 345 | 9 new source files: escalation/ package (ladder, political, consequences, events, war_termination), combat/unconventional.py, c2/ai/sof_ops.py, population/insurgency.py. ~18 modified + ~32 YAML + 4 scenarios |

### Block 2 Phases (25-30) — Complete

| Phase | Focus | Tests | Key Deliverables |
|-------|-------|-------|------------------|
| 25 | Engine Wiring & Integration | 152 | ScenarioLoader auto-wiring (EW, Space, CBRN, Schools, Commander, Era, Escalation), OODA DECIDE fix, tick loop integration, strict_mode |
| 26 | Core Polish & Configuration | 82 | PRNG discipline (23 engines), configurable constants (9 files), engine lifecycle (puff cleanup, scan cap, armor_type) |
| 27 | Combat System Completeness | 139 | Cross-domain routing (3 new EngagementTypes), EW air combat/defense integration, burst fire, submunition scatter, TOT sync, CAS designation, naval gun, ASROC/depth charges, torpedo CM, CAP management, observer correction, cavalry terrain, frontage constraint, gas mask don time |
| 28 | Modern Era Data Package | 137 | 95 YAML data files: 19 units (adversary/allied/specialist), 9 weapons, 16 ammo, 5 sensors, 28 signatures, 7 orgs, 5 doctrine, 3 commanders, 3 escalation configs. 8 new data dirs. Zero source changes. |
| 28.5 | Directed Energy Weapons | 112 | DEW engine (Beer-Lambert laser transmittance, laser/HPM Pk), 7 enum extensions, engagement routing, scenario wiring, 20 YAML (5 weapons, 5 ammo, 3 units, 5 signatures, 2 sensors). 1 new + 6 modified source files. |
| 29 | Historical Era Data Expansion | 164 | 119 YAML: naval units for all 4 historical eras (WW2 carriers/subs, WW1 dreadnoughts, Napoleonic ships of line, Ancient triremes/longships), plus ground/air/weapons/ammo/signatures/comms/commander. 15 new data directories. Zero source changes. |
| 30 | Scenario & Campaign Library | 196 | 10 new scenario YAML (4 modern joint, 4 historical), 3 modified scenarios (73 Easting fix, Midway carrier fix, Golan expansion), 2 new Falklands scenarios. Cross-scenario validation. 3 deficits resolved. Zero source changes. |

### Block 3 Phases (31-36) — Complete

| Phase | Focus | Tests | Key Deliverables |
|-------|-------|-------|------------------|
| 31 | Documentation Site (GitHub Pages) | 0 | MkDocs + Material theme, GitHub Actions deployment, 8 user-facing docs (getting started, scenarios, architecture, models, API, eras, units), docs/index.md landing page. Zero engine changes. |
| 32 | API & Service Foundation | 77 | FastAPI service layer (13 source files), SQLite persistence (aiosqlite), async run execution, WebSocket progress streaming, 23 REST endpoints + 2 WS endpoints, batch MC execution. `api/` package at repo root. Zero engine changes. |
| 33 | Frontend Foundation & Scenario Browser | 62 | React + TypeScript + Tailwind frontend (~50 files). Scenario browser (list+detail), unit catalog with modal, run config/list pages. Vite + TanStack Query + React Router + Headless UI. Zero engine/API changes. |
| 34 | Run Results & Analysis Dashboard | 65 | RunDetailPage with live WebSocket progress, 5 Plotly chart types (force strength, engagement, morale, tempo, comparison), narrative view, Analysis page (batch MC, A/B compare, sensitivity sweep). ~45 new files. Zero engine/API changes. |
| 35 | Tactical Map & Spatial Visualization | 71 | 2D Canvas tactical map with terrain rendering, unit markers (domain shapes), engagement arcs, movement trails, playback controls (rAF loop, 4 speeds), map legend, unit detail sidebar, chart sync via URL params. Backend: terrain/frames DB columns + 2 new API endpoints. 15 new frontend + 4 modified API + 10 test files. |
| 36 | Scenario Tweaker & Polish | 59 | Clone-and-tweak scenario editor (useReducer, 11 action types, force editor, unit picker, config toggles, calibration sliders, YAML preview, terrain preview), export (JSON/CSV/YAML/print), keyboard shortcuts, responsive sidebar, WS reconnect with exponential backoff. 3 modified API + ~20 new frontend + 11 test files. |

### Block 4 Phases (37-39)

| Phase | Focus | Tests | Key Deliverables |
|-------|-------|-------|------------------|
| 37 | Integration Fixes & E2E Validation | 70 | config_overrides deep merge, ReinforcementArrivedEvent + frontend handling, DEW battle loop routing via route_engagement, HitResult propagation, E2E smoke test (33 pass + 8 xfail legacy) |
| 38 | Map & Chart Enhancements | 35 | FOW toggle + per-side detection data, sensor range circles, elevation shading, engagement arc fade, cross-chart tick sync (all 4 charts + bidirectional click), dark mode (useTheme hook + Tailwind dark: classes on ~45 components) |
| 39 | Quality, Performance & Packaging | 22 | Test gap closure (useBatchProgress, useViewportControls, RunDetailPage error states), typed analysis responses, virtualized event list, configurable frame interval, `uv run python -m api` single-command startup, SPA static serving, Docker, dev scripts, ConfigDiff, terrain types from LandCover enum |

### Block 5 Phases (40-44) — In Progress

| Phase | Focus | Tests | Key Deliverables |
|-------|-------|-------|------------------|
| 40 | Battle Loop Foundation | 47 | Victory bug fix (is_tie → sides_at_best), posture tracking, fire-on-move gate, domain filtering, suppression wiring, morale multipliers, terrain managers |
| 41 | Combat Depth | 51 | Terrain cover/concealment/elevation modifiers, per-unit training level, threat-based target selection, detection quality modifier |
| 42 | Tactical Behavior | 26 | ROE engine wiring (WEAPONS_FREE default), hold-fire discipline (effective_range_m), composite victory scoring (morale+casualty weights), rout cascade, rally mechanic |
| 43 | Domain-Specific Resolution | 45 | Era-aware routing (volley fire, archery, melee dispatch), indirect fire routing (IndirectFireEngine), naval domain routing (5 naval engines), aggregate casualty mapping, MeleeEngine for WW1/Ancient eras |
| 44 | Environmental & Subsystem Integration | 37 | Weather Pk table + visibility cap, night/thermal modifiers, sea state dispersion, CBRN MOPP, EW jamming, GPS CEP, readiness gate, engine update fixes (step→update), medical/engineering/population wiring. Zero new source files. |

### Phase 30 Detail

Pure data phase — 10 new scenario YAMLs + 3 modified + 1 test file (196 tests). Zero new Python source files. 10 new scenario directories.
- **30a Modern Joint** (4 scenarios): Taiwan Strait (air-naval, EW+escalation), Korean Peninsula (combined arms, CBRN), Suwalki Gap (EW+schools), Hybrid Gray Zone (SOF+escalation).
- **30b Historical** (4 scenarios): Jutland 1916 (WW1 dreadnoughts), Trafalgar 1805 (Napoleonic ships of line), Salamis 480 BC (Ancient triremes), Stalingrad 1942 (WW2 urban combat).
- **30c Existing Fixes** (3 modified + 2 new): 73 Easting calibration (visibility 800m, red engagement 1500m, thermal_contrast 1.5, added BMP-2), Midway carriers (essex_cv + shokaku_cv + a6m_zero), Golan BMP-2 expansion, Falklands San Carlos air raids, Falklands Goose Green ground.
- **30d Cross-Validation**: Parametrized tests over all ~25 scenarios — schema validation, domain config coverage, documented outcomes format.

Phase 30 pattern: Scenario library phase following Phase 28/29 data. All scenarios use campaign format (sides/objectives/victory_conditions). Exercises EW, CBRN, escalation, doctrinal schools. 3 deficits resolved (73 Easting inf, simplified OOB, Falklands Sheffield-only).

### Phase 28 Detail

Data-only phase — 95 new YAML files + 1 test file (137 tests). Zero new Python source files. 4 existing test files updated (hardcoded count assertions → `>=`).
- **28a Units** (19 files): MiG-29A, Su-27S, J-10A, BMP-2, BTR-80, T-90A, Sovremenny DDG, Kilo-636 SSK, SA-11 Buk, S-300PMU, Leopard 2A6, Challenger 2, B-52H, EA-18G, Mi-24V, C-17, Javelin team, Kornet team, Engineer squad.
- **28b Weapons/Ammo/Sensors** (30 files): AGM-88 HARM, R-77, R-73, Igla, 2A42, Javelin, Kornet, ASROC, Mk-54 torpedo. 16 ammo types (bombs, autocannon, guided, mortar, naval, missile warheads). 5 sensors (APG-68, APY-1, AAQ-33, SQR-19, UV MAWS).
- **28c Orgs/Doctrine/Commanders/Escalation** (18 files): US CABTF, Stryker Co, Paladin Bty, Russian BTG, PLA CAB, UK Armoured BG, Generic Mech Co. PLA/IDF/airborne/amphibious/naval doctrine. Joint/naval/logistics commanders. Peer/conventional/NATO escalation configs.
- **28d Signatures** (28 files): 9 missing signatures for existing units + 19 for new 28a units.

Phase 28 pattern: Pure data expansion — no engine changes, no schema changes. All YAML conforms to existing pydantic models. 8 new data directories.

### Phase 27 Detail

12 source files modified + 4 new test files (139 tests):
- **27d Selective Fidelity** (30 tests): Observer correction for barrage drift, cavalry terrain effects (slope/soft ground/obstacles), frontage constraint in melee, gas mask don time enforcement. 4 deficits resolved (2.10, 2.11, 2.12, 2.13).
- **27a Cross-Domain Engagement** (31 tests): 3 new EngagementType values (COASTAL_DEFENSE, AIR_LAUNCHED_ASHM, ATGM_VS_ROTARY), `route_engagement()` dispatcher, ATGM vs rotary-wing, air-launched ASHM, EW integration into air combat and air defense (optional engines, gated by `enable_ew_countermeasures`).
- **27b Engagement Enhancements** (47 tests): Burst fire (`execute_burst_engagement()`, binomial trials, `enable_burst_fire` gate), DPICM submunition scatter (`resolve_submunition_damage()`, UXO field creation), multi-spectral CM stacking (multiplicative), TOT synchronization (`TOTFirePlan`, `compute_tot_plan()`, `execute_tot_mission()`), CAS JTAC designation (delay gate, laser bonus, talk-on ramp).
- **27c Naval Combat** (31 tests): Naval gun engagement (radar-directed Pk), ASROC (rocket delivery → torpedo), depth charges (pattern scatter), torpedo countermeasures (NIXIE → acoustic CM → evasion layers), CAP station management, recovery windows.

Phase 27 pattern: Cross-domain completeness — fills engagement gaps between existing subsystems. All changes backward-compatible (new config fields with defaults, optional params, `enable_*` flags). No new source files.

### Phase 24 Detail

9 new source files + ~18 modified + ~32 YAML data files:
- **24a Escalation Model** (75 tests): `escalation/ladder.py` (11-level state machine, desperation index, hysteresis), `escalation/political.py` (international/domestic pressure, 9 effects), `escalation/consequences.py` (war crimes cascading), `escalation/events.py` (8 event types).
- **24b Prohibited Weapons** (56 tests): 4 new AmmoType values, treaty compliance checking (CWC→5, BWC→6, CCM→4, Ottawa→4), `IncendiaryDamageEngine` (fire zones, wind expansion), `UXOEngine` (submunition failure fields). 10 YAML.
- **24c Unconventional + SOF** (59 tests): `combat/unconventional.py` (IED speed-detection tradeoff, guerrilla hit-and-run, human shields), `c2/ai/sof_ops.py` (SOF mission lifecycle: HVT, sabotage). IED/BOOBY_TRAP obstacles, INSURGENT/MILITIA/PMC org types, prisoner interrogation. 12 YAML.
- **24d AI Escalation** (62 tests): Commander traits (violation_tolerance, collateral_tolerance, escalation_awareness), escalation action enums, MILITARY_STALEMATE/POLITICAL_PRESSURE adaptation triggers, SABOTAGE/TERROR/SCORCHED_EARTH stratagems, desperation index + consequence estimation. 6 YAML.
- **24e Insurgency** (46 tests): `population/insurgency.py` (Markov radicalization pipeline, cell formation, cell operations with concealment degradation, HUMINT/SIGINT discovery). COIN dynamics.
- **24f Integration** (47 tests): `escalation/war_termination.py` (negotiated ceasefire, capitulation), engine wiring (9 new context fields), CEASEFIRE/ARMISTICE victory types. 4 validation scenarios.

Phase 24 pattern: Modulation layer on existing systems — escalation modulates ROE, morale, AI decisions. Optional via `escalation_config: null`. Chemical weapons use Phase 18 CBRN. IEDs use existing damage model. Population-driven insurgency in `population/`, not `combat/`. No new dependencies.
