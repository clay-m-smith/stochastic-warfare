# Stochastic Warfare

![Python](https://img.shields.io/badge/python-%3E%3D3.12-blue)
![Tests](https://img.shields.io/badge/tests-9%2C294_passing-brightgreen)
![Phase](https://img.shields.io/badge/phase-72_Block--8--IN_PROGRESS-orange)

High-fidelity, high-resolution wargame simulator built as a headless Python engine. Models warfare across multiple scales — from individual unit engagements up through tactical battles, operational battlefields, and multi-day strategic campaigns — with stochastic and signal-processing-inspired models throughout.

The simulator covers the modern era (Cold War to present) as its prototype period and treats maritime warfare as a fully integrated domain alongside land and air operations, not a deferred add-on. Validated against historical engagements (73 Easting, Falklands Naval, Golan Heights) at both engagement and campaign levels.

Core mathematical models include Markov chains (morale state transitions, weather), Monte Carlo methods (engagement and campaign outcome analysis), Kalman filters (enemy state estimation from noisy sensor data), Poisson processes (equipment breakdown, reinforcement arrivals), queueing theory (medical evacuation, supply bottlenecks), and SNR-based detection theory (unified across visual, thermal, radar, and acoustic sensors).

## Getting Started

### Prerequisites

- **Python >= 3.12** (pinned to 3.12.10 via `.python-version`)
- **[uv](https://docs.astral.sh/uv/)** — used exclusively for package management (never bare `pip`)

### Setup

```bash
uv sync --extra dev    # creates .venv, installs all deps including pytest/matplotlib
```

### Running Tests

```bash
uv run python -m pytest --tb=short -q           # standard suite (excludes @pytest.mark.slow)
uv run python -m pytest -m slow --tb=short -q   # 1000-run Monte Carlo validation only
```

All commands use `uv run` to ensure the correct venv is used without manual activation.

## Quick Start (Web UI)

**Development mode** (two terminals):
```bash
bash scripts/dev.sh   # or .\scripts\dev.ps1 on Windows
# Open http://localhost:5173
```

**Production mode** (single command):
```bash
cd frontend && npm run build && cd ..
uv run python -m api
# Open http://localhost:8000
```

**Docker**:
```bash
docker build -t stochastic-warfare .
docker run -p 8000:8000 stochastic-warfare
```

## Architecture

### Module Dependency Chain

The engine is composed of 12 top-level modules with a strict one-way dependency graph:

```
core → coordinates → terrain → environment → entities → movement → detection → combat → morale → c2 → logistics → simulation
```

Dependencies flow downward only. Terrain never imports environment; environment may read terrain. Entities hold data while modules implement behavior (ECS-like separation).

### Simulation Loop

Hybrid tick-based + event-driven. The outer loop advances discrete ticks at variable resolution depending on scale:

| Scale | Tick Resolution | Manager |
|-------|----------------|---------|
| Strategic | 3,600s (1 hour) | `CampaignManager` |
| Operational | 300s (5 min) | `CampaignManager` |
| Tactical | 5s | `BattleManager` |

Events fire within ticks for fine-grained interactions (damage application, morale cascades, order propagation).

### Spatial Model

Layered hybrid across scales:

- **Graph** (strategic) — networkx supply networks, LOC routing
- **Grid** (operational/tactical) — raster terrain, LOS raycasting, pathfinding
- **Continuous** (unit-level) — ENU meter coordinates, precise engagement geometry

All raster grids share the convention: `Grid[0,0]` = SW corner, row increases northward, col increases eastward.

### Key Stochastic Models

| Model | Module | Purpose |
|-------|--------|---------|
| Markov chains | `morale/state`, `environment/weather` | State transitions (morale 5-state, weather evolution) |
| Monte Carlo | `validation/monte_carlo` | Engagement and campaign outcome distributions |
| Kalman filter | `detection/estimation` | 4-state enemy position/velocity tracking |
| Poisson processes | `logistics/maintenance` | Equipment breakdown (`1 - exp(-dt/MTBF)`) |
| Queueing theory (M/M/c) | `logistics/medical` | Priority-based medical evacuation |
| SNR detection (erfc) | `detection/detection` | Unified Pd across all sensor types |
| Lanchester attrition | `ai/coa` | Analytical COA wargaming |
| Wayne Hughes salvo | `combat/naval_surface` | Missile exchange with leaker dynamics |
| Boyd OODA | `ai/ooda` | Commander decision cycle as FSM |
| Log-normal delays | `c2/communications`, `logistics/transport` | Clausewitzian friction in C2 and supply |
| Beer-Lambert law | `combat/directed_energy` | Laser atmospheric transmittance for DEW |

For full architectural rationale, see [`docs/brainstorm.md`](docs/brainstorm.md).

## Project Structure

```
api/                      # REST API service layer (13 source files) [Phase 32]
  routers/                # FastAPI route handlers (scenarios, units, runs, analysis, meta)

frontend/                 # React frontend (Vite + TypeScript + Tailwind) [Phase 33]
  src/
    api/                  # Typed API client
    components/           # Shared components (Layout, Badge, Card, etc.)
    hooks/                # TanStack Query hooks
    pages/                # Scenario browser, unit catalog, runs, analysis
    lib/                  # Utility functions (format, era, domain)
    types/                # TypeScript interfaces mirroring api/schemas.py

stochastic_warfare/       # simulation engine (19 modules, ~226 source files)
  core/                   # types, logging, RNG, clock, events, config, checkpoint
  coordinates/            # geodetic/UTM/ENU transforms, magnetic declination
  terrain/                # heightmap, classification, bathymetry, LOS, infrastructure
  environment/            # weather, astronomy, sea state, acoustics, EM propagation
  entities/               # unit definitions, equipment, organization, hierarchy
  movement/               # pathfinding, fatigue, formations, naval/air/amphibious
  detection/              # sensors, signatures, sonar, estimation, fog of war
  combat/                 # ballistics, damage, missiles, naval, air combat, IADS, strategic targeting
  morale/                 # state transitions, cohesion, stress, psychology, rout
  c2/                     # command, communications, ROE, orders, joint ops, mission command
  logistics/              # supply, transport, maintenance, medical, engineering, production
  population/             # civilian regions, displacement, collateral, HUMINT, influence, insurgency
  escalation/             # escalation ladder, political pressure, consequences, war termination
  simulation/             # scenario loading, battle/campaign managers, engine
  validation/             # historical data, Monte Carlo, campaign validation
  ai/                     # OODA, commander AI, doctrine, assessment, decisions, doctrinal schools
  planning/               # MDMP, mission analysis, COA generation, estimates
  ew/                     # electronic warfare: jamming, spoofing, ECCM, SIGINT, decoys
  space/                  # space & satellite: GPS, SATCOM, ISR, early warning, ASAT
  cbrn/                   # CBRN effects: agents, dispersal, contamination, protection, nuclear
  tools/                  # MCP server, analysis (narrative, tempo, comparison, sensitivity), visualization

data/                     # ~735 YAML data files
  units/                  # 46 unit definitions (ground, air, naval, support)
  weapons/                # 51 weapon definitions (guns, artillery, missiles, torpedoes)
  ammunition/             # 63 ammunition definitions
  sensors/                # 16 sensor definitions
  signatures/             # 48 signature profiles
  comms/                  # 8 communication equipment definitions
  ew/                     # 12 EW equipment definitions (jammers, ECCM suites, SIGINT collectors)
  space/                  # 12 space definitions (9 constellations, 3 ASAT weapons)
  cbrn/                   # 16 CBRN definitions (agents, nuclear weapons, delivery systems)
  organizations/          # 9 TO&E definitions
  commanders/             # 13 commander personality profiles
  doctrine/               # 21 doctrine templates (US, Russian, NATO, PLA, IDF, generic, unconventional)
  schools/                # 9 doctrinal school definitions (Clausewitzian, Maneuverist, etc.)
  supply/                 # 5 supply item definitions
  transport/              # 4 transport profiles
  medical/                # 2 medical facility definitions
  eras/                    # Era-specific data packages (WW2, WW1, Napoleonic, Ancient/Medieval)
  scenarios/              # 27 modern scenarios (engagement, campaign, EW, space, CBRN, escalation, joint) + 5 test

tests/                    # ~9,295 engine+API+frontend tests across ~350 test files
docs/                     # specs, brainstorm, devlog, development phases
```

For the full package tree and module decomposition, see [`docs/specs/project-structure.md`](docs/specs/project-structure.md).

## Development Status

All 11 MVP phases (0-10) are complete. Post-MVP Phases 11-24 are complete (deep systems rework + performance optimization + developer tooling + real-world terrain + electronic warfare + space & satellite domain + CBRN effects + doctrinal AI schools + WW2 era + WW1 era + Napoleonic era + Ancient & Medieval era + unconventional & prohibited warfare). Block 2 Phases 25-30 complete (Engine Wiring & Integration Sprint + Core Polish & Configuration + Combat System Completeness + Modern Era Data Package + Directed Energy Weapons + Historical Era Data Expansion + Scenario & Campaign Library). Block 3 complete (Phases 31-36: Documentation Site + API + Frontend + Charts + Tactical Map + Scenario Tweaker). Block 4 complete (Phases 37-39: Integration Fixes + E2E Validation + Map & Chart Enhancements + Quality, Performance & Packaging). Block 5 complete (Phases 40-48: Battle Loop Foundation + Combat Depth + Tactical Behavior + Domain-Specific Resolution + Environmental & Subsystem Integration + Mathematical Model Audit + Scenario Data Cleanup + Full Recalibration + Deficit Resolution). Block 6 complete (Phases 49-57: Calibration Schema Hardening + Combat Fidelity Polish + Naval Combat Completeness + Environmental Continuity + C2 & AI Completeness + Era-Specific & Domain Sub-Engine Wiring + Resolution & Scenario Migration + Performance & Logistics + Full Validation & Regression). Block 7 COMPLETE (Phases 58-67: Structural Verification + Environment Wiring + Engine Integration + Integration Validation & Recalibration). Block 8 IN PROGRESS (Phase 68+: Consequence Enforcement + Scenario Expansion). 73 phases delivered across 8 blocks.

| Phase | Focus | Tests | Status |
|-------|-------|-------|--------|
| 0 | Project Scaffolding | 97 | Complete |
| 1 | Terrain & Environment Foundation | 270 | Complete |
| 2 | Entity System & Movement | 424 | Complete |
| 3 | Detection & Intelligence | 296 | Complete |
| 4 | Combat Resolution & Morale | 634 | Complete |
| 5 | C2 Infrastructure | 345 | Complete |
| 6 | Logistics & Supply | 336 | Complete |
| 7 | Engagement Validation | 188 | Complete |
| 8 | AI & Planning | 575 | Complete |
| 9 | Simulation Orchestration | 372 | Complete |
| 10 | Campaign Validation | 196 | Complete |
| 11 | Core Fidelity Fixes | 109 | Complete |
| 12 | Deep Systems Rework | 259 | Complete |
| 13 | Performance Optimization | 170 | Complete |
| 14 | Tooling & Developer Experience | 125 | Complete |
| 15 | Real-World Terrain & Data Pipeline | 97 | Complete |
| 16 | Electronic Warfare | 143 | Complete |
| 17 | Space & Satellite Domain | 149 | Complete |
| 18 | CBRN Effects | 155 | Complete |
| 19 | Doctrinal AI Schools | 189 | Complete |
| 20 | WW2 Era | 137 | Complete |
| 21 | WW1 Era | 182 | Complete |
| 22 | Napoleonic Era | 233 | Complete |
| 23 | Ancient & Medieval Era | 321 | Complete |
| 24 | Unconventional & Prohibited Warfare | 345 | Complete |
| 25 | Engine Wiring & Integration (Block 2) | 152 | Complete |
| 26 | Core Polish & Configuration (Block 2) | 82 | Complete |
| 27 | Combat System Completeness (Block 2) | 139 | Complete |
| 28 | Modern Era Data Package (Block 2) | 137 | Complete |
| 28.5 | Directed Energy Weapons (Block 2) | 112 | Complete |
| 29 | Historical Era Data Expansion (Block 2) | 164 | Complete |
| 30 | Scenario & Campaign Library (Block 2) | 196 | Complete |
| 31 | Documentation Site (Block 3) | 0 | Complete |
| 32 | API & Service Foundation (Block 3) | 77 | Complete |
| 33 | Frontend Foundation & Scenario Browser (Block 3) | 62 | Complete |
| 34 | Run Results & Analysis Dashboard (Block 3) | 65 | Complete |
| 35 | Tactical Map & Spatial Visualization (Block 3) | 71 | Complete |
| 36 | Scenario Tweaker & Polish (Block 3) | 59 | Complete |
| 37 | Integration Fixes & E2E Validation (Block 4) | 70 | Complete |
| 38 | Map & Chart Enhancements (Block 4) | 35 | Complete |
| 39 | Quality, Performance & Packaging (Block 4) | 22 | Complete |
| 40 | Battle Loop Foundation (Block 5) | 47 | **Complete** |
| 41 | Combat Depth (Block 5) | 51 | **Complete** |
| 42 | Tactical Behavior (Block 5) | 26 | **Complete** |
| 43 | Domain-Specific Resolution (Block 5) | 45 | **Complete** |
| 44 | Environmental & Subsystem Integration (Block 5) | 37 | **Complete** |
| 45 | Mathematical Model Audit & Hardening (Block 5) | 21 | **Complete** |
| 46 | Scenario Data Cleanup & Expansion (Block 5) | 57 | **Complete** |
| 47 | Full Recalibration & Validation (Block 5) | 38 | **Complete** |
| 48 | Block 5 Deficit Resolution (Block 5) | 34 | **Complete** |
| 49 | Calibration Schema Hardening (Block 6) | 51 | **Complete** |
| 50 | Combat Fidelity Polish (Block 6) | 40 | **Complete** |
| 51 | Naval Combat Completeness (Block 6) | 37 | **Complete** |
| 52 | Environmental Continuity (Block 6) | 32 | **Complete** |
| 53 | C2 & AI Completeness (Block 6) | 44 | **Complete** |
| 54 | Era-Specific & Domain Sub-Engine Wiring (Block 6) | 53 | **Complete** |
| 55 | Resolution & Scenario Migration (Block 6) | 43 | **Complete** |
| 56 | Performance & Logistics (Block 6) | 39 | **Complete** |
| 57 | Full Validation & Regression (Block 6) | 51 | **Complete** |
| 58 | Structural Verification & Core Combat Wiring (Block 7) | 60 | **Complete** |
| 59 | Atmospheric & Ground Environment Wiring (Block 7) | 48 | **Complete** |
| 60 | Obscurants, Fire, & Visual Environment (Block 7) | 53 | **Complete** |
| 61 | Maritime, Acoustic, & EM Environment (Block 7) | 71 | **Complete** |
| 62 | Human Factors, CBRN, & Air Combat Environment (Block 7) | 85 | **Complete** |
| 63 | Cross-Module Feedback Loops (Block 7) | 74 | **Complete** |
| 64 | C2 Friction & Command Delay (Block 7) | 60 | **Complete** |
| 65 | Space & EW Sub-Engine Activation (Block 7) | 43 | **Complete** |
| 66 | Unconventional, Naval, & Cleanup (Block 7) | 50 | **Complete** |
| 67 | Integration Validation & Recalibration (Block 7) | ~30 | **Complete** |
| 68 | Consequence Enforcement (Block 8) | 67 | **Complete** |
| 69 | C2 Depth (Block 8) | 41 | **Complete** |
| 70 | Performance Optimization (Block 8) | 24 | **Complete** |
| 71 | Missile & Carrier Ops Completion (Block 8) | 46 | **Complete** |
| 72 | Checkpoint & State Completeness (Block 8) | 139 | **Complete** |
| 73 | Historical Scenario Correctness (Block 8) | ~22 | **Complete** |
| | **Total** | **~9,316** | |

For the full phase roadmap, see [`docs/development-phases.md`](docs/development-phases.md) (MVP), [`docs/development-phases-post-mvp.md`](docs/development-phases-post-mvp.md) (post-MVP), [`docs/development-phases-block4.md`](docs/development-phases-block4.md) (Block 4), [`docs/development-phases-block5.md`](docs/development-phases-block5.md) (Block 5), [`docs/development-phases-block6.md`](docs/development-phases-block6.md) (Block 6), [`docs/development-phases-block7.md`](docs/development-phases-block7.md) (Block 7), and [`docs/development-phases-block8.md`](docs/development-phases-block8.md) (Block 8). For per-phase implementation logs, see [`docs/devlog/`](docs/devlog/).

## Key Dependencies

| Package | Purpose |
|---------|---------|
| `numpy` | Array math, PRNG (`np.random.Generator`), vectorized operations |
| `scipy` | Statistical distributions, special functions (erfc), integration |
| `pydantic` | Configuration validation, YAML schema enforcement |
| `pyproj` | Geodetic/UTM/ENU coordinate transforms |
| `pyyaml` | YAML data file loading (units, weapons, scenarios) |
| `shapely` | Vector geometry (roads, rivers, coastlines, obstacles) |
| `networkx` | Supply network graphs, strategic map routing |

Optional: `numba` (JIT acceleration, `--extra perf`), `rasterio`/`xarray` (real terrain, `--extra terrain`), `mcp[cli]` (MCP server, `--extra mcp`), `mkdocs-material` (docs site, `--extra docs`), `fastapi`/`uvicorn`/`aiosqlite` (REST API, `--extra api`). Dev: `pytest`, `pytest-cov`, `matplotlib`, `httpx`, `pytest-asyncio`

## REST API

The project includes a FastAPI-based REST API for running simulations, browsing scenarios/units, and accessing results programmatically.

```bash
uv sync --extra api              # install API dependencies
uv run uvicorn api.main:app      # start the API server
# OpenAPI docs at http://localhost:8000/api/docs
```

Key endpoints: `GET /api/scenarios`, `GET /api/units`, `POST /api/runs` (submit simulation), `GET /api/runs/{id}` (poll results), `WS /api/runs/{id}/progress` (live progress), `POST /api/runs/batch` (Monte Carlo), `POST /api/analysis/compare` (A/B comparison).

## Frontend Development

The React frontend lives in `frontend/` and connects to the API via Vite's dev proxy. See the [Web UI Guide](docs/guide/web-ui.md) for a full walkthrough of the web application.

```bash
# Terminal 1: API server
uv sync --extra api
uv run uvicorn api.main:app --reload

# Terminal 2: Frontend dev server
cd frontend && npm install && npm run dev
# Open http://localhost:5173
```

Frontend commands:
- `npm run dev` — Vite dev server at localhost:5173
- `npm run build` — Production build (TypeScript + Vite)
- `npm test` — Run vitest tests (272 tests, no API server required)
- `npm run lint` — ESLint

## Documentation

**Documentation site**: [clay-m-smith.github.io/stochastic-warfare](https://clay-m-smith.github.io/stochastic-warfare) -- full docs with getting started guide, web UI guide, scenario library, architecture overview, mathematical models, API reference, and era reference.

| Document | Purpose |
|----------|---------|
| [`docs/brainstorm.md`](docs/brainstorm.md) | Architecture decisions, domain decomposition, rationale |
| [`docs/development-phases.md`](docs/development-phases.md) | Phase roadmap (0–10 + future), module-to-phase index |
| [`docs/development-phases-block3.md`](docs/development-phases-block3.md) | Block 3 UX/UI phase roadmap (31–36) |
| [`docs/specs/project-structure.md`](docs/specs/project-structure.md) | Full package tree, module decomposition, dependency graph |
| [`docs/devlog/`](docs/devlog/) | Per-phase implementation logs (`index.md` tracks status) |
| [`docs/skills-and-hooks.md`](docs/skills-and-hooks.md) | Dev infrastructure (Claude skills, hooks, research tiers) |
| [`docs/specs/`](docs/specs/) | Per-module specifications (written before implementation) |
| [`CLAUDE.md`](CLAUDE.md) | Full project conventions and coding standards |

## License

This project is licensed under the [PolyForm Noncommercial License 1.0.0](LICENSE.md). You are free to use, modify, and share the software for personal, academic, and research purposes. Commercial and institutional use requires a separate license — contact **claymsmith1@gmail.com** for inquiries.

## Contributing

This project does not accept external contributions. See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

### Key Conventions

For reference, the engine follows these conventions (see [`CLAUDE.md`](CLAUDE.md) for the complete list):

- **PRNG discipline** — all randomness via `RNGManager.get_stream(ModuleId)` returning `np.random.Generator`. No bare `random` module, no `np.random` module-level calls.
- **Deterministic iteration** — no `set()` or unordered dict driving simulation logic.
- **ECS separation** — entities hold data, modules implement behavior.
- **Package management** — `uv` exclusively. Never bare `pip install`.
- **Coordinate system** — ENU meters internally. Geodetic only for import/export/display.
- **Logging** — `from stochastic_warfare.core.logging import get_logger` — no bare `print()` in sim core.
- **Config** — pydantic `BaseModel` for all configuration classes.
- **Unit definitions** — data-driven YAML validated by pydantic. Engine defines behaviors, YAML parameterizes instances.
