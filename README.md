# Stochastic Warfare

![Python](https://img.shields.io/badge/python-%3E%3D3.12-blue)
![Tests](https://img.shields.io/badge/tests-5%2C980_passing-brightgreen)
![Phase](https://img.shields.io/badge/phase-23_Post--MVP-blue)

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

For full architectural rationale, see [`docs/brainstorm.md`](docs/brainstorm.md).

## Project Structure

```
stochastic_warfare/       # simulation engine (18 modules, ~217 source files)
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
  population/             # civilian regions, displacement, collateral, HUMINT, influence
  simulation/             # scenario loading, battle/campaign managers, engine
  validation/             # historical data, Monte Carlo, campaign validation
  ai/                     # OODA, commander AI, doctrine, assessment, decisions, doctrinal schools
  planning/               # MDMP, mission analysis, COA generation, estimates
  ew/                     # electronic warfare: jamming, spoofing, ECCM, SIGINT, decoys
  space/                  # space & satellite: GPS, SATCOM, ISR, early warning, ASAT
  cbrn/                   # CBRN effects: agents, dispersal, contamination, protection, nuclear
  tools/                  # MCP server, analysis (narrative, tempo, comparison, sensitivity), visualization

data/                     # ~220 YAML data files
  units/                  # 21 unit definitions (ground, air, naval, support)
  weapons/                # 24 weapon definitions (guns, artillery, missiles, torpedoes)
  ammunition/             # 23 ammunition definitions
  sensors/                # 9 sensor definitions
  signatures/             # 15 signature profiles
  comms/                  # 8 communication equipment definitions
  ew/                     # 12 EW equipment definitions (jammers, ECCM suites, SIGINT collectors)
  space/                  # 12 space definitions (9 constellations, 3 ASAT weapons)
  cbrn/                   # 13 CBRN definitions (7 agents, 3 nuclear weapons, 3 delivery systems)
  organizations/          # 2 TO&E definitions
  commanders/             # 6 commander personality profiles
  doctrine/               # 10 doctrine templates (US, Russian, NATO, generic)
  schools/                # 9 doctrinal school definitions (Clausewitzian, Maneuverist, etc.)
  supply/                 # 5 supply item definitions
  transport/              # 4 transport profiles
  medical/                # 2 medical facility definitions
  eras/                    # Era-specific data packages (WW2, WW1, Napoleonic, Ancient/Medieval)
  scenarios/              # 3 engagement + 6 campaign + 2 EW + 3 space + 2 CBRN validation scenarios

tests/                    # 5,980 tests across ~190 test files
docs/                     # specs, brainstorm, devlog, development phases
```

For the full package tree and module decomposition, see [`docs/specs/project-structure.md`](docs/specs/project-structure.md).

## Development Status

All 11 MVP phases (0–10) are complete. Post-MVP Phases 11–23 are complete (deep systems rework + performance optimization + developer tooling + real-world terrain + electronic warfare + space & satellite domain + CBRN effects + doctrinal AI schools + WW2 era + WW1 era + Napoleonic era + Ancient & Medieval era).

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
| 13 | Performance Optimization | 142 | Complete |
| 14 | Tooling & Developer Experience | 125 | Complete |
| 15 | Real-World Terrain & Data Pipeline | 97 | Complete |
| 16 | Electronic Warfare | 144 | Complete |
| 17 | Space & Satellite Domain | 149 | Complete |
| 18 | CBRN Effects | 155 | Complete |
| 19 | Doctrinal AI Schools | 189 | Complete |
| 20 | WW2 Era | 137 | Complete |
| 21 | WW1 Era | 182 | Complete |
| 22 | Napoleonic Era | 233 | Complete |
| 23 | Ancient & Medieval Era | 321 | Complete |
| | **Total** | **5,980** | |

For the full phase roadmap, see [`docs/development-phases.md`](docs/development-phases.md) (MVP) and [`docs/development-phases-post-mvp.md`](docs/development-phases-post-mvp.md) (post-MVP). For per-phase implementation logs, see [`docs/devlog/`](docs/devlog/).

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

Optional: `numba` (JIT acceleration, `--extra perf`), `rasterio`/`xarray` (real terrain, `--extra terrain`), `mcp[cli]` (MCP server, `--extra mcp`). Dev: `pytest`, `pytest-cov`, `matplotlib`

## Documentation

| Document | Purpose |
|----------|---------|
| [`docs/brainstorm.md`](docs/brainstorm.md) | Architecture decisions, domain decomposition, rationale |
| [`docs/development-phases.md`](docs/development-phases.md) | Phase roadmap (0–10 + future), module-to-phase index |
| [`docs/specs/project-structure.md`](docs/specs/project-structure.md) | Full package tree, module decomposition, dependency graph |
| [`docs/devlog/`](docs/devlog/) | Per-phase implementation logs (`index.md` tracks status) |
| [`docs/skills-and-hooks.md`](docs/skills-and-hooks.md) | Dev infrastructure (Claude skills, hooks, research tiers) |
| [`docs/specs/`](docs/specs/) | Per-module specifications (written before implementation) |
| [`CLAUDE.md`](CLAUDE.md) | Full project conventions and coding standards |

## Contributing

Key conventions (see [`CLAUDE.md`](CLAUDE.md) for the complete list):

- **PRNG discipline** — all randomness via `RNGManager.get_stream(ModuleId)` returning `np.random.Generator`. No bare `random` module, no `np.random` module-level calls.
- **Deterministic iteration** — no `set()` or unordered dict driving simulation logic.
- **ECS separation** — entities hold data, modules implement behavior.
- **Package management** — `uv` exclusively. Never bare `pip install`.
- **Coordinate system** — ENU meters internally. Geodetic only for import/export/display.
- **Logging** — `from stochastic_warfare.core.logging import get_logger` — no bare `print()` in sim core.
- **Config** — pydantic `BaseModel` for all configuration classes.
- **Unit definitions** — data-driven YAML validated by pydantic. Engine defines behaviors, YAML parameterizes instances.
