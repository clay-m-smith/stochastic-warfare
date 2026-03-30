# Stochastic Warfare — Claude Code Instructions

## Project Overview
High-fidelity, high-resolution wargame simulator. Multi-scale (campaign → battlefield → battle → unit level) with stochastic/signal-processing-inspired models (Markov chains, Monte Carlo, Kalman filters, noise models, queueing theory). Headless Python engine first; matplotlib for validation; full UI deferred. Modern era (Cold War–present) as prototype. Maritime warfare fully integrated, not deferred.

**Current status**: Phase 95 complete — Block 10 IN PROGRESS (92–97). ~10,718 tests (~10,322 Python + 396 frontend vitest). 95 phases delivered across 10 blocks. Blocks 1–9 COMPLETE.

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
| `/cross-doc-audit` | Verify alignment across all docs (MVP + post-MVP + user-facing, 19 checks) |
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
| `docs/development-phases-block5.md` | Block 5 phase roadmap (40–48), battle loop wiring + deficit resolution |
| `docs/brainstorm-block6.md` | Block 6 design thinking (final tightening, deficit inventory, dead engine audit) |
| `docs/development-phases-block6.md` | Block 6 phase roadmap (49–57), calibration hardening + combat polish + engine wiring |
| `docs/brainstorm-block7.md` | Block 7 design thinking (build-then-defer-wiring audit, environmental params, unreachable engines) |
| `docs/development-phases-block7.md` | Block 7 phase roadmap (58–67), structural verification + environment wiring + engine integration |
| `docs/brainstorm-block8.md` | Block 8 design thinking (consequence enforcement, scenario expansion) |
| `docs/development-phases-block8.md` | Block 8 phase roadmap (68–82), consequence enforcement + scenario expansion |
| `docs/brainstorm-block9.md` | Block 9 design thinking (performance at scale, 9 themes) |
| `docs/development-phases-block9.md` | Block 9 phase roadmap (83–91), performance at scale |
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

All phase details are in `docs/devlog/` (one file per phase). Per-phase tables in `docs/development-phases*.md`.

| Block | Phases | Focus | Tests |
|-------|--------|-------|-------|
| MVP (1) | 0–10 | Core engine: terrain, entities, movement, detection, combat, morale, C2, logistics, simulation, validation | 3,737 |
| Post-MVP | 11–24 | Fidelity fixes, performance, tooling, terrain pipeline, EW, Space, CBRN, doctrinal AI, 4 historical eras, unconventional warfare | 2,588 |
| Block 2 | 25–30 | Engine wiring, polish, combat completeness, data packages (modern + historical), DEW, scenario library | 982 |
| Block 3 | 31–36 | MkDocs site, FastAPI + SQLite, React frontend, Plotly charts, tactical map, scenario editor | 334 |
| Block 4 | 37–39 | Integration fixes, map/chart enhancements, dark mode, Docker, single-command startup | 127 |
| Block 5 | 40–48 | Battle loop wiring, combat depth, domain routing, environmental integration, recalibration, deficit resolution | 374 |
| Block 6 | 49–57 | CalibrationSchema, combat polish, naval completeness, C2/AI wiring, era engines, validation, zero-deficit audit | 390 |
| Block 7 | 58–67 | Structural verification, environment wiring (atmosphere/maritime/CBRN/human factors), feedback loops, 21 enable_* flags | ~594 |
| Block 8 | 68–82 | Consequence enforcement, C2 depth, perf optimization, missile/carrier ops, test coverage, CI/CD, accessibility | ~1,291 |
| Block 9 | 83–91 | Profiling, spatial culling, LOD, Numba JIT, SoA data layer, per-side parallelism, benchmarking | ~279 |
| **Block 10** | **92–97** | **UI depth: analytics endpoints, dashboard charts, map overlays, calibration editor, event filtering, data catalogs** | **100+** |

### Block 10 Detail (Current)

| Phase | Status | Focus |
|-------|--------|-------|
| 92 | Complete | API analytics endpoints (5) + enriched MapUnitFrame (7 fields) + metadata endpoints (4) |
| 93 | Complete | 4 Plotly chart components + analytics summary card + TanStack Query hooks |
| 94 | Complete | 5 map overlay toggles + engagement flash + enhanced sidebar + map legend |
| 95 | Complete | Per-side calibration (4 sliders), morale (5) + rout cascade (2) sliders, doctrine/commander pickers, victory weights editor |
| 96 | Not started | Event filtering/search, engagement detail panel, doctrine comparison analysis |
| 97 | Not started | Weapon/doctrine catalog pages, regression validation, documentation lockstep |
