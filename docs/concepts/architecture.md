# Architecture Overview

This page explains the core architecture of Stochastic Warfare -- how the engine is structured, how simulation runs execute, and how optional subsystems integrate.

## Module Dependency Chain

The engine is composed of 12 top-level modules with a strict one-way dependency graph:

```
core -> coordinates -> terrain -> environment -> entities -> movement
  -> detection -> combat -> morale -> c2 -> logistics -> simulation
```

| Module | Purpose |
|--------|---------|
| **core** | Types, logging, PRNG management, clock, event bus, config, checkpointing |
| **coordinates** | Geodetic/UTM/ENU transforms, magnetic declination |
| **terrain** | Heightmap generation, terrain classification, bathymetry, LOS raycasting, infrastructure |
| **environment** | Weather (Markov), astronomy (Meeus), sea state, acoustics, EM propagation |
| **entities** | Unit definitions, equipment, organization hierarchy, task organization |
| **movement** | A* pathfinding, fatigue, formations, naval/air/amphibious/submarine movement |
| **detection** | Unified SNR sensors, Kalman tracking, sonar, intel fusion, fog of war |
| **combat** | Ballistics (RK4), DeMarre penetration, missiles, naval salvo, air combat, IADS, DEW |
| **morale** | Continuous-time Markov state transitions, cohesion, stress, psychology, rout |
| **c2** | Command authority, communications (Bernoulli), EMCON, ROE, orders, mission command |
| **logistics** | NATO supply classes, deterministic scenario topology/resupply, networkx routing, Poisson maintenance, M/M/c medical, engineering |
| **simulation** | Scenario loading, battle/campaign managers, master engine, recording, metrics |

**Key rule**: Dependencies flow downward only. Terrain never imports environment. Environment may read terrain (one-way). This prevents circular dependencies and makes the system testable in isolation.

### Additional Domain Modules

Beyond the core 12, specialized domain modules provide optional capabilities:

| Module | Purpose | Phase |
|--------|---------|-------|
| **ai** | OODA FSM, commander personalities, doctrine templates, MDMP planning | 8 |
| **planning** | Mission analysis, COA generation, wargaming, estimates | 8 |
| **validation** | Historical data, Monte Carlo harness, campaign validation | 7, 10 |
| **population** | Civilian regions, displacement, collateral, insurgency | 12, 24 |
| **ew** | Electronic warfare: jamming, spoofing, ECCM, SIGINT, decoys | 16 |
| **space** | Orbital mechanics, GPS, SATCOM, space ISR, early warning, ASAT | 17 |
| **cbrn** | Chemical/biological/radiological/nuclear effects and protection | 18 |
| **escalation** | Escalation ladder, political pressure, war termination | 24 |
| **tools** | MCP server, analysis utilities, visualization | 14 |

## Simulation Loop

The engine uses a **hybrid tick-based + event-driven** architecture:

- **Outer loop**: Advances discrete ticks at variable resolution depending on scale
- **Inner loop**: Events fire within ticks for fine-grained interactions

### Scale Resolution

| Scale | Tick Resolution | Manager | When Active |
|-------|----------------|---------|-------------|
| Strategic | 3,600s (1 hour) | `CampaignManager` | Between battles |
| Operational | 300s (5 min) | `CampaignManager` | Approaching contact |
| Tactical | 5s | `BattleManager` | Active engagement |

The engine automatically switches resolution based on battle state. When forces come into contact, resolution drops from strategic to tactical. When battles resolve, it scales back up.

### Tick Processing Order

At the engine boundary, each tick follows a fixed order:

1. **Reinforcements** -- admit due waves atomically at their logical arrival
   time.
2. **Environment** -- advance weather, time of day, and seasonal state.
3. **Logistics** -- cross any fixed logical cadence boundaries, update direct
   routes, resupply, then apply eligible idle demand. This call occurs at every
   engine resolution.
4. **Resolution-specific work** -- select the current resolution, then execute
   strategic/operational campaign work or active tactical battles. Detection,
   AI/C2, movement, combat, and morale are sequenced inside those managers.
5. **Logistics activity latch** -- remember movement and battle participation
   so a unit is not charged the idle rate at the next cadence boundary.
6. **Victory** -- evaluate conditions against the committed force, morale, and
   supply state.
7. **Recorder** -- record the tick and any configured snapshot.

The Phase 108 logistics path models direct aggregate resupply and stationary,
non-battle idle demand only. March/combat demand and synchronization with live
fuel tanks or weapon magazines remain explicit remediation boundaries.

### Engagement Gate Sequence

Within combat, each potential engagement passes through a series of gates before resolving. If any gate rejects, the engagement is skipped. This gate sequence was wired in Phases 40--47 (Block 5: Core Combat Fidelity), connecting 40+ previously disconnected subsystems into the battle loop. Source-backed historical scenarios use separately declared outcome envelopes; synthetic, test, calibration, and benchmark scenarios are not historical validation claims.

1. **Domain filtering** -- attacker's weapon must target the defender's domain (ground, air, naval)
2. **Posture/status check** -- ROUTED/SURRENDERED units skip; morale accuracy multiplier applied
3. **Suppression check** -- heavily suppressed units may skip engagement
4. **Fire-on-move check** -- `requires_deployed` weapons skip if attacker is moving
5. **Terrain cover/concealment** -- cover reduces hit probability; concealment reduces detection range
6. **Detection quality** -- sensor-derived `id_confidence` modulates engagement effectiveness
7. **Training level** -- unit quality multiplies hit probability
8. **ROE gate** -- `RoeEngine.check_engagement_authorized()` blocks engagements below the current ROE level's confidence threshold (WEAPONS_HOLD blocks all non-self-defense; WEAPONS_TIGHT requires high `id_confidence`)
9. **Weapon selection** -- best weapon chosen by range, ammo, and target type
10. **Hold-fire discipline** -- if enabled via `behavior_rules`, defensive units wait until targets are within effective range (default 80% of max range)
11. **Engagement resolution** -- ballistics, penetration, and damage applied

After morale transitions, a **rout cascade** check propagates routing to nearby SHAKEN/BROKEN units. A **rally check** allows ROUTING units near friendly forces to recover.

## Spatial Model

The engine uses a **layered hybrid** spatial representation:

### Three Layers

| Layer | Type | Scale | Used For |
|-------|------|-------|----------|
| **Graph** | networkx | Strategic | Supply networks, LOC routing |
| **Grid** | NumPy raster | Operational/Tactical | Terrain, LOS raycasting, pathfinding |
| **Continuous** | Float coordinates | Unit-level | Precise engagement geometry, movement |

### Grid Convention

All raster grids share: `Grid[0,0]` = SW corner, row increases northward, col increases eastward. This matches geographic convention (south-to-north, west-to-east).

### Coordinate System

- **Internal**: ENU (East-North-Up) meters for all computation
- **External**: Geodetic (lat/lon) only for import, export, and display
- **Transforms**: `pyproj` for all coordinate conversions

## ECS-Like Separation

The engine follows an **Entity-Component-System** inspired pattern:

- **Entities** hold data (position, health, ammunition, morale state, equipment)
- **Modules** implement behavior (movement algorithms, detection math, combat resolution)
- Entities are passed to modules as arguments; modules return results or modify entity state

This means you can test combat resolution without a terrain engine, or test detection without a movement engine.

## Engine Wiring

The `ScenarioLoader` is the central factory. Given a scenario YAML file, it:

1. Parses the YAML into a `CampaignScenarioConfig` (pydantic-validated), or
   deep-copies a prevalidated effective config supplied by an orchestrator
2. Creates terrain, environment, and weather engines
3. Instantiates all units with their equipment, weapons, and sensors
4. Creates detection, combat, movement, morale, C2, and logistics engines
   and, when `logistics.enabled` is true, materializes declared depot stock,
   unit inventories, supply nodes, and expanded direct routes
5. Wires optional subsystems from explicit enable flags after applying the
   selected era's capability gates:
   - `ew_config.enable_ew: true` -> creates EW engines (jamming, spoofing, ECCM, SIGINT)
   - `space_config.enable_space: true` -> creates space engines (GPS, SATCOM, ISR, ASAT)
   - `cbrn_config.enable_cbrn: true` -> creates CBRN engines (dispersal, contamination, protection)
   - `school_config` present -> creates doctrinal school registry
   - `escalation_config` present -> creates escalation engine
   - `dew_config` present -> creates directed energy weapon engine
   - `era` specified -> loads era-specific data and engines
6. Creates always-on behavioral engines: ROE engine (default WEAPONS_FREE), rout engine
7. Seeds both morale views from each side's validated `morale_initial`
8. Returns a `SimulationContext` with everything wired together

`SimulationEngine` then installs the validated reinforcement schedule exactly
once. Due waves are checked at every resolution and are committed atomically to
the campaign roster, context force map, live loadout maps, morale state, and
enabled logistics topology.

### Null-Config Gating

Every optional subsystem follows the same pattern:

```python
if config.ew_config is not None and config.ew_config.get("enable_ew") is True:
    # Create and wire EW engines
else:
    ctx.ew_engine = None  # Disabled -- zero cost
```

The equivalent `enable_space` and `enable_cbrn` flags control their suites.
The effective registered era is checked before construction, so a scenario
cannot explicitly enable a suite forbidden by that era.

The root `logistics` block uses the same explicit gating rule. Omission or
`enabled: false` retains an injected runtime/manager shell with canonical empty
state and an O(1) disabled update gate; legacy `sides[].depots` metadata alone
never invents stock or routes. Enabled logistics is strict: every initial and
reinforcement unit type needs one same-side profile, every depot needs explicit
type, condition, and inventory, and every connection comes from a declared
direct route template.

## Era Framework

The engine supports 5 historical eras, each with different available technologies:

| Era | Period | Key Mechanics |
|-----|--------|---------------|
| **Modern** | Cold War--present | Full subsystem access |
| **WW2** | 1939--1945 | Naval gunnery, convoy/wolf pack, strategic bombing |
| **WW1** | 1914--1918 | Trench systems, creeping barrage, gas warfare |
| **Napoleonic** | 1792--1815 | Volley fire, melee, cavalry charges, formations, courier C2 |
| **Ancient/Medieval** | 3000 BC--1500 AD | Massed archery, siege machines, oar-powered naval |

Each era is defined by an `EraConfig` that specifies:

- Seven validated capability gates: EW, space, CBRN, GPS, thermal sights,
  data links, and precision-guided munitions
- An enforced sensor-type allowlist
- Declared physics and tick-resolution override metadata (not yet consumed by
  the production runtime; tracked separately in the remediation backlog)
- Era-specific engine extensions

Era data lives in `data/eras/{era_name}/` with the same directory structure as modern data.

## Determinism & Reproducibility

Every simulation run is fully reproducible given the same seed:

### PRNG Discipline

- All randomness flows through `RNGManager`, which creates per-module `np.random.Generator` streams
- Each module gets its own independent PRNG stream via `RNGManager.get_stream(ModuleId)`
- No bare `random` module or `np.random` module-level calls anywhere in the codebase
- Given the same seed, the same scenario produces identical results
- Battle discovery and reinforcement events require the caller's simulation
  clock timestamp; no wall-clock fallback participates in replay state

### Deterministic Iteration

- No `set()` or unordered dict drives simulation logic
- All iteration over collections uses sorted or ordered containers

## Web Application Layer

The engine is wrapped by a web application stack that provides interactive access without writing Python code.

### Architecture

```
Browser (React) -> Vite dev proxy -> FastAPI (api/) -> Simulation Engine (stochastic_warfare/)
                                         |
                                    SQLite (aiosqlite)
```

### API Layer (`api/`)

A FastAPI service sits alongside the engine (not inside it). It provides:

- **REST endpoints** for browsing scenarios, units, and run history
- **WebSocket streaming** for live simulation progress
- **Async run execution** via executor workers (CPU-bound simulation in a
  thread pool)
- **SQLite persistence** for run results across server restarts
- **Batch execution** for Monte Carlo statistical analysis

The application lifespan owns one settings object, database connection, and run
manager. A run is accepted only after its effective scenario config validates
and its pending row commits. Shutdown rejects new work, cooperatively signals
run and batch workers, waits for the actual executor threads and terminal
SQLite writes, then closes the database. The grace timeout reports slow
workers; it does not abandon them.

The API layer imports `stochastic_warfare` as a library. Sparse calibration
overlays are merged into an isolated effective config before
`ScenarioLoader`; source scenario YAML is not modified.

### Frontend (`frontend/`)

A React + TypeScript single-page application built with Vite:

- **TanStack Query** for API data fetching and caching
- **Plotly.js** for interactive charts (force strength, engagements, morale, tempo) with cross-chart tick sync
- **Canvas 2D** for the tactical map (terrain with elevation shading, unit positions, FOW filtering, sensor circles, engagement fade, playback)
- **React Router** for deep-linkable pages
- **Headless UI** for accessible modals, dropdowns, and menus

Key pages: Scenario Browser, Unit Catalog, Run Results (charts + narrative + map), Scenario Editor (clone-and-tweak), Analysis (Monte Carlo, A/B comparison, sensitivity sweep).

See the [Web UI Guide](../guide/web-ui.md) for usage documentation.

## Consequence Enforcement Gates

The engine uses an opt-in pattern for behavioral enforcement of resource consumption and C2 friction. Each consequence is gated behind an `enable_*` flag in `CalibrationSchema` (default `False`), so enabling a new behavior never breaks existing scenarios.

Key enforcement gates:

| Flag | Effect | Phase |
|------|--------|-------|
| `enable_fuel_consumption` | Units consume fuel proportional to distance moved; immobilized when empty | 68 |
| `enable_ammo_gate` | Engagements skipped when magazine exhausted | 68 |
| `enable_command_hierarchy` | Orders must propagate through command chain | 69 |
| `enable_missile_routing` | Missile flight resolved per-tick with defense intercept | 71 |
| `enable_carrier_ops` | Carrier CAP/sortie rate limited by sea state | 71 |
| `enable_ice_crossing` | Units on ice move at 50% speed | 78 |
| `enable_bridge_capacity` | Bridges enforce weight limits | 78 |
| `enable_environmental_fatigue` | Heat/cold stress degrades unit performance | 78 |

Additional non-flag consequences include fire zone damage (`fire_damage_per_tick`), stratagem expiry (`stratagem_duration_ticks`), guerrilla retreat distance, and order misinterpretation effects.

The `enable_all_modern` meta-flag activates all 21 non-deferred flags at once for convenience, but individual flag control is preferred in scenario YAMLs for performance (selective flags avoid ~6x overhead from unused subsystems).

## Checkpointing

All stateful classes implement the checkpoint protocol:

```python
class SomeEngine:
    def get_state(self) -> dict:
        """Serialize full internal state."""
        ...

    def set_state(self, state: dict) -> None:
        """Restore from serialized state."""
        ...
```

This enables:

- **Save/restore** mid-simulation
- **Branching** -- checkpoint, run two different decisions, compare outcomes
- **Debugging** -- reproduce any simulation state from a checkpoint + seed
