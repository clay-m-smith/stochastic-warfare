# Stochastic Warfare — Claude Code Instructions

## Project Overview
High-fidelity, high-resolution wargame simulator. Multi-scale (campaign → battlefield → battle → unit level) with stochastic/signal-processing-inspired models (Markov chains, Monte Carlo, Kalman filters, noise models, queueing theory). Headless Python engine first; matplotlib for validation; full UI deferred. Modern era (Cold War–present) as prototype. Maritime warfare fully integrated, not deferred.

**Current status**: Phase 1 complete (terrain + environment). 367 tests passing. Next: Phase 2 (Entities, Organization & Movement).

## Package Management
**Use `uv` exclusively.** Never use bare `pip install`. Always use `uv pip install`, `uv add`, `uv sync`, etc. Direct `pip` may target system Python instead of the project venv.

Before running any Python commands:
```bash
source .venv/Scripts/activate
```

## Running Tests
```bash
source .venv/Scripts/activate && python -m pytest --tb=short -q
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
`numpy`, `scipy`, `pydantic`, `pyproj`, `shapely`, `networkx` (+ `pytest`, `pytest-cov`, `matplotlib` for dev)

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

## Development Process
- Development phases defined in `docs/development-phases.md` (Phase 0–8 + future)
- Devlog: `docs/devlog/` — one markdown file per phase, living documents. Update the relevant phase log when completing work.
- Run `/cross-doc-audit` after completing phases or changing architecture
- Run `/validate-conventions` after writing simulation core code
- All design docs are **living documents** — propagate implementation decisions back to all affected docs via `/update-docs`

## Available Skills
| Skill | Purpose |
|-------|---------|
| `/research-military` | Military doctrine, historical data, theorist/philosopher writings (tiered sources) |
| `/research-models` | Mathematical, stochastic, signal processing modeling approaches (tiered sources) |
| `/validate-conventions` | Check code against PRNG, determinism, coordinate, logging conventions |
| `/update-docs` | Propagate design decisions to brainstorm, specs, memory |
| `/spec` | Draft/update module specification before implementation |
| `/backtest` | Structure validation against historical engagement data |
| `/audit-determinism` | Deep PRNG discipline audit — trace all stochastic paths |
| `/design-review` | Review module design against military theory and architecture |
| `/cross-doc-audit` | Verify alignment across development-phases, project-structure, brainstorm, devlog |
| `/simplify` | Review changed code for reuse, quality, and efficiency |

## Documentation Map
| Document | Purpose |
|----------|---------|
| `docs/brainstorm.md` | Architecture decisions, domain decomposition, rationale |
| `docs/development-phases.md` | Phase roadmap (0–8), module-to-phase index |
| `docs/specs/project-structure.md` | Full package tree, module decomposition, dependency graph |
| `docs/devlog/` | Per-phase implementation logs (`index.md` tracks status) |
| `docs/skills-and-hooks.md` | Dev infrastructure documentation |
| `docs/specs/` | Per-module specifications (written before implementation) |

## Completed Phases

### Phase 0: Project Scaffolding (97 tests)
Core infrastructure: types, logging, RNG manager, calendar-aware clock (Meeus Julian date), event bus, YAML config loading, checkpoint/restore, coordinate transforms (geodetic/UTM/ENU), spatial utilities, base entity stub.

### Phase 1: Terrain, Environment & Spatial Foundation (270 tests)
20 modules total:
- **Terrain** (10 modules): heightmap, classification, bathymetry, infrastructure, obstacles, population, hydrography, maritime_geography, los, strategic_map
- **Environment** (9 modules): astronomy, weather, seasons, time_of_day, sea_state, obscurants, underwater_acoustics, electromagnetic, conditions
- **Coordinates** (1 module): magnetic

Key physics: Meeus astronomical algorithms, Markov weather chains, Pierson-Moskowitz wave spectrum, Mackenzie sound velocity, acoustic propagation, RF propagation, DDA raycasting LOS with Earth curvature correction.

Dependencies added: `shapely>=2.0`, `networkx>=3.0`
