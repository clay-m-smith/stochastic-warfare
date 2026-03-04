# Stochastic Warfare — Claude Code Instructions

## Project Overview
High-fidelity, high-resolution wargame simulator. Multi-scale (campaign → battlefield → battle → unit level) with stochastic/signal-processing-inspired models (Markov chains, Monte Carlo, Kalman filters, noise models, queueing theory). Headless Python engine first; matplotlib for validation; full UI deferred. Modern era (Cold War–present) as prototype. Maritime warfare fully integrated, not deferred.

**Current status**: Phase 20 complete (WW2 Era) + all prior phases. 5,244 tests passing. MVP complete (phases 0-10). Post-MVP Phases 11-20 delivered — Phase 11: 15 deficit fixes across ~20 source files. Phase 12: 16 deficits resolved + 2 new domains (civilian population, strategic air campaigns/IADS) across 12 new + ~25 modified source files. Phase 13: Performance optimization (STRtree, Kalman cache, LOS cache, viewshed vectorization, auto-resolve, force aggregation, Numba JIT, A* precompute, MC parallelism) across 2 new + ~10 modified source files. Phase 14: Developer tooling (MCP server, analysis utilities, visualization, 7 Claude skills) across 12 new source files + 7 skill files. Phase 15: Real-world terrain pipeline (SRTM elevation, Copernicus land cover, OSM infrastructure, GEBCO bathymetry) across 5 new source files + 1 modified + 1 download script. Phase 16: Electronic Warfare (EA/EP/ES — J/S ratio, GPS spoofing, ECCM, SIGINT) across 8 new source files + 5 modified + 14 YAML + 2 scenarios. Phase 17: Space & Satellite (orbital mechanics, GPS dependency, space ISR, early warning, SATCOM, ASAT warfare) across 9 new source files + 7 modified + 12 YAML + 3 scenarios. Phase 18: CBRN (Pasquill-Gifford dispersal, contamination grids, MOPP protection, probit casualties, nuclear blast/thermal/radiation/EMP/fallout) across 10 new source files + 6 modified + 15 YAML + 2 scenarios. Phase 19: Doctrinal AI Schools (9 named schools as Strategy-pattern classes — Clausewitz, Maneuver, Attrition, AirLand Battle, Air Power, Sun Tzu, Deep Battle, Mahanian, Corbettian — with assessment weight overrides, decision score adjustments, OODA multipliers, COA weight overrides, opponent modeling) across 10 new source files + 6 modified + 9 YAML. Phase 20: WW2 Era (era framework — Era enum, EraConfig, module gating, era-aware YAML loading; WW2 data package — 15 units, 8 weapons, 13 ammo, 4 sensors, 15 signatures, 4 doctrines, 3 commanders, 3 scenarios; engine extensions — naval gunnery bracket firing, convoy/wolf pack, strategic bombing CEP) across 4 new source files + 2 modified + ~60 YAML.

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
`numpy`, `scipy`, `pydantic`, `pyproj`, `shapely`, `networkx` (+ `pytest`, `pytest-cov`, `matplotlib` for dev). Optional: `numba` (perf), `mcp[cli]` (mcp), `rasterio`/`xarray` (terrain).

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
| `/scenario` | Interactive scenario creation/editing walkthrough |
| `/compare` | Run two configs and summarize with statistical comparison |
| `/what-if` | Quick parameter sensitivity from natural language questions |
| `/timeline` | Generate battle narrative from simulation run |
| `/orbat` | Interactive order of battle builder |
| `/calibrate` | Auto-tune calibration overrides to match historical data |
| `/postmortem` | Structured retrospective after completing a phase — catches integration gaps, deficits, test quality issues |

## Documentation Map
| Document | Purpose |
|----------|---------|
| `docs/brainstorm.md` | Architecture decisions, domain decomposition, rationale |
| `docs/brainstorm-post-mvp.md` | Post-MVP design thinking (deficits, EW, Space, CBRN, eras, tooling, unconventional warfare, strategic air campaigns/IADS) |
| `docs/development-phases.md` | MVP phase roadmap (0–10), module-to-phase index |
| `docs/development-phases-post-mvp.md` | Post-MVP phase roadmap (11–24), deficit-to-phase mapping |
| `docs/specs/project-structure.md` | Full package tree, module decomposition, dependency graph |
| `docs/devlog/` | Per-phase implementation logs (`index.md` tracks status) |
| `docs/skills-and-hooks.md` | Dev infrastructure documentation |
| `docs/specs/` | Per-module specifications (written before implementation) |
| `README.md` | Project overview, setup, architecture summary, status |

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

### Post-MVP Phases (11-20) — All Complete

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

### Phase 20 Detail (Most Recent)

4 new source files + 2 modified + ~60 YAML data files:
- **20a Era Framework** (56 tests): `core/era.py` (Era enum, EraConfig, `get_era_config()` factory), `simulation/scenario.py` (+`era` field, era-aware `_create_loaders()`, era_config in context/state). 15 WW2 units, 8 weapons, 13 ammo, 4 sensors, 15 signatures.
- **20b Engine Extensions** (53 tests): `combat/naval_gunnery.py` (bracket convergence, fire control, 2D Gaussian dispersion), `movement/convoy.py` (wolf pack, depth charge, straggler mechanics), `combat/strategic_bombing.py` (CEP area damage, Norden altitude scaling, flak Pk, escort effectiveness).
- **20c Doctrine & Commanders**: 4 doctrine + 3 commander YAML files.
- **20d Validation Scenarios** (28 tests): Kursk, Midway, Normandy Bocage.

Era framework pattern: disabled modules stay `None` on SimulationContext (existing None-check pattern). WW2 disables EW, Space, CBRN, GPS, thermal sights, data links, PGMs. Era-specific YAML loaded from `data/eras/{era}/` on top of base data. Backward-compatible via `era: "modern"` default. No new dependencies.
