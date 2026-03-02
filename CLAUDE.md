# Stochastic Warfare — Claude Code Instructions

## Project Overview
High-fidelity, high-resolution wargame simulator. Multi-scale (campaign → battlefield → battle → unit level) with stochastic/signal-processing-inspired models (Markov chains, Monte Carlo, Kalman filters, noise models, queueing theory). Headless Python engine first; matplotlib for validation; full UI deferred. Modern era (Cold War–present) as prototype. Maritime warfare fully integrated, not deferred.

**Current status**: Phase 5 complete (C2 infrastructure). 2,115 tests passing. Next: Phase 6 (Logistics & Supply).

## Package Management
**Use `uv` exclusively.** Never use bare `pip install`. Always use `uv add`, `uv sync`, etc. Direct `pip` may target system Python instead of the project venv.

Use `uv run` to execute all Python commands — this automatically uses the correct venv without manual activation:
```bash
uv run python -m pytest --tb=short -q
```

Do NOT use `source .venv/Scripts/activate` — use `uv run` instead.

## Running Tests
```bash
uv run python -m pytest --tb=short -q
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
- Development phases defined in `docs/development-phases.md` (Phase 0–10 + future)
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

### Phase 2: Entities, Organization & Movement (424 tests)
28 new source modules + 13 YAML data files:
- **Entities** (12 modules): base (expanded with Unit), personnel, equipment, events, loader, capabilities, unit_classes/ (ground, aerial, air_defense, naval, support)
- **Organization** (7 modules): echelons, hierarchy, task_org, staff, orbat, special_org, events
- **Movement** (11 modules): engine, pathfinding, fatigue, formation, events, obstacles, mount_dismount, naval_movement, submarine_movement, amphibious_movement, airborne
- **YAML data** (13 files): 11 unit definitions (m1a2, us_rifle_squad, m109a6, f16c, mq9, ah64d, patriot, ddg51, ssn688, lhd1, hemtt) + 2 TO&E definitions (infantry_platoon, tank_company)

Key features: YAML-driven unit factory, military hierarchy with task-org overlay, A* pathfinding with threat avoidance, cubic fuel law, submarine speed-noise curve, airborne drop scatter, formation geometry (10 types), combat power assessment.

No new dependencies.

### Phase 3: Detection & Intelligence (296 tests)
12 new source modules + 19 YAML data files:
- **Detection** (12 modules): signatures, events, sensors, detection, identification, sonar, underwater_detection, estimation, intel_fusion, deception, fog_of_war
- **YAML data** (19 files): 11 signature profiles (m1a2, us_rifle_squad, m109a6, f16c, mq9, ah64d, patriot, ddg51, ssn688, lhd1, hemtt) + 8 sensor definitions (mk1_eyeball, thermal_sight, ground_search_radar, air_search_radar, passive_sonar, active_sonar, esm_suite, nvg)

Key features: Unified SNR-based detection probability (erfc), YAML-driven signatures and sensors, radar range equation (R^4 law), passive/active sonar with convergence zone detection, 4-state Kalman filter state estimation with track lifecycle, multi-source intel fusion (SENSOR/SIGINT/HUMINT/IMINT), decoy deployment and degradation, per-side fog-of-war with independent world views, deterministic replay from seed.

No new dependencies.

### Phase 4: Combat Resolution & Morale (634 tests)
28 new source modules + 47 YAML data files:
- **Combat** (19 modules): ammunition, ballistics, hit_probability, damage, suppression, fratricide, engagement, indirect_fire, missiles, air_combat, air_ground, air_defense, missile_defense, naval_surface, naval_subsurface, naval_mine, naval_gunfire_support, amphibious_assault, carrier_ops
- **Morale** (6 modules): state, cohesion, stress, experience, psychology, rout
- **Support** (3 modules)
- **YAML data** (47 files): 24 weapon definitions + 23 ammunition definitions

Key features: RK4 ballistic trajectories, DeMarre penetration, Wayne Hughes salvo model, Markov morale transitions, kill chain timing, fratricide driven by detection confidence, YAML-driven weapons/ammunition, all domains covered (land, air, sea, subsurface), deterministic replay from seed.

No new dependencies.

### Phase 5: C2 Infrastructure (345 tests)
17 new source modules + 8 YAML data files:
- **C2** (8 modules): events, command, communications, naval_c2, roe, coordination, mission_command
- **Orders** (9 modules): types, individual, tactical, operational, strategic, naval_orders, air_orders, propagation, execution
- **YAML data** (8 files): 8 communication equipment definitions (SINCGARS VHF, Harris HF, FBCB2, Link 16, Link 11, SATCOM UHF, VLF receiver, field wire)

Key features: 4-state command authority (succession with log-normal delays), stochastic comms reliability (Bernoulli per message), EMCON states blocking emitters, jamming with resistance, log-normal propagation delays scaling with echelon, order misinterpretation probability, ROE enforcement (WEAPONS_HOLD/TIGHT/FREE), fire support coordination (FSCL/NFA/RFA/FFA), Auftragstaktik vs Befehlstaktik initiative, naval task force hierarchy (TF/TG/TU/TE), tactical data links, submarine VLF/SATCOM constraints, ATO/ACO/CAS structures, deterministic replay from seed.

No new dependencies.
