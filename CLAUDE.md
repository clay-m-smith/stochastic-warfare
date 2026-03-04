# Stochastic Warfare — Claude Code Instructions

## Project Overview
High-fidelity, high-resolution wargame simulator. Multi-scale (campaign → battlefield → battle → unit level) with stochastic/signal-processing-inspired models (Markov chains, Monte Carlo, Kalman filters, noise models, queueing theory). Headless Python engine first; matplotlib for validation; full UI deferred. Modern era (Cold War–present) as prototype. Maritime warfare fully integrated, not deferred.

**Current status**: Phase 13 complete (Performance Optimization) + postmortem cleanup. 4,247 tests passing. MVP complete (phases 0-10). Post-MVP Phases 11-13 delivered — Phase 11: 15 deficit fixes across ~20 source files. Phase 12: 16 deficits resolved + 2 new domains (civilian population, strategic air campaigns/IADS) across 12 new + ~25 modified source files. Phase 13: Performance optimization (STRtree, Kalman cache, LOS cache, viewshed vectorization, auto-resolve, force aggregation, Numba JIT, A* precompute, MC parallelism) across 2 new + ~10 modified source files. Postmortem: wired aggregation engine + selective LOS invalidation into simulation loop.

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

### Phase 6: Logistics & Supply (336 tests)
14 new source modules + 11 YAML data files:
- **Logistics** (13 modules): events, supply_classes, consumption, stockpile, supply_network, transport, maintenance, engineering, medical, prisoners, naval_logistics, naval_basing, disruption
- **YAML data** (11 files): 5 supply item definitions (18 items across Class I/III/IV/VIII/IX), 4 transport profiles (truck, C-130, rail, sealift), 2 medical facility definitions (aid station, field hospital)
- **Modified** (1 file): entities/capabilities.py — added `supply_state_override` parameter

Key features: NATO supply classification (9 classes), environment-coupled consumption rates, networkx supply network with pull-based routing, log-normal transport delays, Poisson equipment breakdown model, M/M/c medical priority queue with overwhelm dynamics, engineering terrain modification, POW handling, naval UNREP/port ops/LOTS/sealift, interdiction/blockade/sabotage disruption, combat power degrades with supply depletion, deterministic replay from seed.

No new dependencies.

### Phase 7: Engagement Validation (188 tests)
5 new source modules + ~30 YAML data files + 3 scenario packs:
- **Validation** (5 modules): historical_data, metrics, scenario_runner, monte_carlo, `__init__`
- **YAML data** (~30 files): 10 unit definitions (m1a1, t72m, shot_kal, t55a, t62, bmp1, m3a2_bradley, type42_destroyer, type22_frigate, sea_harrier, super_etendard), 9 weapon/ammo definitions, 1 sensor (active_ir_sight), 4 signature profiles, 3 scenario packs (73_easting, falklands_naval, golan_heights)

Key features: Historical engagement data loader (YAML), lightweight scenario runner with pre-scripted behavior, Monte Carlo harness with statistical comparison, deferred damage resolution (simultaneous fire), weather-independent sensor handling (thermal/radar bypass visibility), per-scenario calibration overrides, 3 validated historical engagements (73 Easting, Falklands Naval, Golan Heights), validation infrastructure reusable for Phase 10.

No new dependencies.

### Phase 8: AI & Planning (575 tests)
14 new source modules + 16 YAML data files:
- **AI** (7 modules): ooda, commander, doctrine, assessment, decisions, adaptation, stratagems
- **Planning** (5 modules): process, mission_analysis, coa, estimates, phases
- **Events** (12 new): 6 AI events + 6 planning events added to c2/events.py
- **YAML data** (16 files): 6 commander profiles (aggressive_armor, cautious_infantry, balanced_default, naval_surface, air_superiority, sof_operator), 10 doctrine templates (us/3, russian/2, nato/1, generic/4)

Key features: Boyd OODA cycle as pure timer/FSM with echelon-scaled log-normal timing, YAML-driven commander personalities (aggression, caution, flexibility, initiative, experience, decision_speed) modulating OODA speed/noise/risk, YAML-driven doctrine templates (US/Russian/NATO/generic) with action filtering, 7-factor weighted situation assessment (force ratio/terrain/supply/morale/intel/environment/C2), 5 echelon-specific decision functions (individual through corps+), MDMP state machine (INTUITIVE/DIRECTIVE/RAPID/MDMP with speed multipliers and 1/3-2/3 rule), mission analysis extracting specified/implied/essential tasks with staff-quality-gated discovery, Lanchester-attrition COA wargaming with personality-biased softmax selection, condition-based operational phasing with branches and sequels, 5 running estimates (personnel/intel/ops/logistics/comms) with periodic update and significant-change events, 7-trigger plan adaptation (casualties/force ratio/supply/morale/opportunity/surprise/C2), 6 echelon+experience-gated stratagem types, deterministic replay from seed.

No new dependencies.

### Phase 9: Simulation Orchestration (372 tests)
8 new source modules + 4 YAML scenario files:
- **Simulation** (7 modules): scenario, victory, recorder, metrics, battle, campaign, engine
- **YAML data** (4 files): 4 test campaign scenarios (test_campaign, test_campaign_multi, test_campaign_reinforce, test_campaign_logistics)

Key features: Master simulation engine with tick resolution switching (STRATEGIC 3600s / OPERATIONAL 300s / TACTICAL 5s), campaign scenario YAML loader wiring all 11 domain modules into SimulationContext, VictoryEvaluator with 5 condition types (territory_control, force_destroyed, time_expired, morale_collapsed, supply_exhausted), BattleManager with full tactical loop (detection → AI → orders → movement → engagement → deferred damage → morale → supply), CampaignManager for strategic ticks (reinforcements → supply network → strategic AI → maintenance → engagement detection), SimulationRecorder subscribing to Event base class via MRO dispatch, CampaignMetrics for post-run analysis (force strength/supply/objective time series, engagement outcomes, campaign summary), per-tick LOS result caching, pathfinding threat cost caching, checkpoint/restore across all engines, deterministic replay from seed.

No new dependencies.

### Phase 10: Campaign Validation (196 tests)
5 new source modules + 2 modified + 2 YAML campaign scenarios:
- **Validation** (5 modules): campaign_data, campaign_runner, campaign_metrics, ai_validation, performance
- **Modified** (2 files): monte_carlo.py (+ CampaignMonteCarloHarness), __init__.py (updated docstring)
- **YAML data** (2 files): Golan Heights 4-day campaign, Falklands San Carlos 5-day campaign

Key features: Campaign-level historical data model (HistoricalCampaign wraps CampaignScenarioConfig + documented_outcomes + ai_expectations), CampaignRunner wrapping ScenarioLoader + SimulationEngine for single-call campaign execution, CampaignValidationMetrics extracting flat metric dicts (units destroyed, exchange ratio, duration, territory control, ships sunk), CampaignMonteCarloHarness extending MC infrastructure for campaign-level N-iteration runs with process-parallel support, AIDecisionValidator extracting AI events from recorder and matching against expected postures (attack/defend/withdraw/culminate) with configurable tolerance (strict/moderate/loose), PerformanceProfiler wrapping cProfile + tracemalloc for wall-clock time, realtime ratio, ticks/second, peak memory, and top hotspots, 2 validated historical campaigns (Golan Heights land + Falklands naval), model deficiency report with severity ratings, deterministic replay from seed.

No new dependencies.

### Phase 11: Core Fidelity Fixes (109 tests)
15 surgical modifications across ~20 existing source files. No new modules, no new dependencies. All changes backward-compatible with default parameters preserving MVP behavior.
- **11a Combat** (36 tests): Fire rate limiting (WeaponInstance cooldown), per-side target_size_modifier, environment coupling (air_combat, air_defense, naval_surface, indirect_fire), Mach-dependent drag (piecewise Cd(M)), armor type + obliquity (ArmorType enum, ricochet at >75°)
- **11b Detection** (35 tests): Sensor FOV filtering (boresight_offset_deg), dwell/integration gain (5·log10(n_scans), capped at 6 dB), geometric sonar bearing (atan2 + SNR-dependent noise), Mahalanobis gating (chi-squared threshold 9.21)
- **11c Movement & Logistics** (23 tests): Fuel gating on movement (fuel_available param), stochastic engineering times (log-normal), wave attack modeling (wave_assignments dict), stochastic reinforcement arrivals (arrival_sigma config)
- **11d AI** (9 tests): Echelon hardcode fix (decisions.py), tactical OODA acceleration (tactical_mult stacking multiplier)

No new dependencies.

### Phase 12: Deep Systems Rework (259 tests)
12 new source files + ~25 modified across 6 sub-phases. No new dependencies. All changes backward-compatible with `enable_*` config flags.
- **12d Morale** (30 tests): Continuous-time Markov morale (`P = 1 - exp(-λ·dt)`), enhanced PSYOP (message×susceptibility×delivery), cooldown enforcement
- **12a C2** (53 tests): Multi-hop relay (hierarchy LCA), terrain comms LOS, network congestion, polyline FSCL, JTAC/FAC observer, JIPTL generation, network-centric COP (data link sharing), joint ops coordination (cross-service delays/caveats), ATO planning cycle
- **12b Logistics** (22 tests): Multi-echelon supply (capacity constraints, min-cost flow, infrastructure coupling, route severing/rerouting), supply regeneration (production.py), transport escort effects, Erlang medical service, fuel gating wired to stockpile
- **12c Combat** (66 tests): Air combat energy-maneuverability (EnergyState, specific energy), compartment flooding (progressive/counter/capsize), submarine geometric evasion + patrol ops, mine ship-signature + MCM + persistence, amphibious landing craft + tidal windows
- **12e Civilian Population** (41 tests): New `population/` package — civilian regions, displacement (combat-driven), collateral tracking, civilian HUMINT (Poisson tips), disposition dynamics (Markov influence), ROE escalation triggers
- **12f Air Campaigns/IADS** (47 tests): IADS sectors (radar handoff chain, SEAD degradation), air campaign management (sortie capacity, pilot fatigue, weather days, attrition), strategic targeting (TPL, BDA with ×3 overestimate bias, target regeneration), strategic infrastructure nodes (PowerPlant, Factory, Port, SupplyDepot)

No new dependencies.

### Phase 13: Performance Optimization (142 tests + 28 postmortem)
2 new source files + ~10 modified. Optional `numba` dependency (`uv sync --extra perf`). All changes backward-compatible with `enable_*` config flags.
- **13a Algorithmic** (99 tests): STRtree spatial indexing (infrastructure.py), multi-tick LOS cache with selective invalidation (los.py), viewshed vectorization (los.py), Kalman F/Q matrix caching (estimation.py), auto-resolve for minor battles (battle.py), force aggregation/disaggregation (aggregation.py — new), benchmark infrastructure
- **13b Compiled Extensions** (42 tests): `@optional_jit` Numba wrapper with fallback (numba_utils.py — new), RK4 trajectory JIT kernel (ballistics.py), DDA raycasting JIT kernel (los.py), A* difficulty grid pre-computation (pathfinding.py)
- **13c Parallelism** (17 tests): MC `submit()`+`as_completed()` pattern (monte_carlo.py), determinism verification suite (11 tests)
- **Postmortem** (28 tests): Wired `aggregation_engine` into `SimulationContext` + engine strategic tick (disaggregation triggers → aggregation candidates). Wired selective LOS invalidation into engine (dirty-cell tracking around movement, `enable_selective_los_invalidation` config flag). Added `_compute_battle_positions()` and `_snapshot_unit_cells()` helpers. Golan campaign profiling script (`scripts/profile_golan.py`).

Optional dependency: `numba>=0.59` (via `--extra perf`).
