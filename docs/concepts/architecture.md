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
| **c2.ai** | OODA FSM, commander personalities, doctrine templates | 8 |
| **c2.planning** | Mission analysis, COA generation, wargaming, estimates | 8 |
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
4. **Scheduled indirect fire** -- after the legacy scripted-event check,
   process aligned time-on-target fire and impact milestones before movement,
   detection, or autonomous combat. The ordering is fixed, but it does not
   prove that a due scripted action committed: REM-045 / Phase 132 owns that
   typed, fail-closed, exact-once lifecycle. Successful time-on-target fires
   debit the exact live attachment's ammunition, cooldown, and maintenance-
   round state; the common impact can change the exact target's status.
5. **Resolution-specific work** -- select the current resolution, then execute
   strategic/operational campaign work or active tactical battles. For a
   tactical interval, `BattleManager.prepare_tactical_interval()` advances
   concealment/FOW once and atomically publishes immutable per-battle targeting
   pictures before any battle moves or fires. AI/C2, movement, combat, and
   morale then consume that prepared interval inside the managers.
6. **Logistics activity latch** -- remember movement and battle participation
   so a unit is not charged the idle rate at the next cadence boundary.
7. **Victory** -- evaluate conditions against the committed force, morale, and
   supply state.
8. **Recorder** -- record the tick and any configured snapshot.

The Phase 108 logistics path models direct aggregate resupply and stationary,
non-battle idle demand only. March/combat demand and synchronization with live
fuel tanks or weapon magazines remain explicit remediation boundaries.

### Engagement Gate Sequence

Within combat, each potential engagement passes through a series of gates before resolving. If any gate rejects, the engagement is skipped. This gate sequence was wired in Phases 40--47 (Block 5: Core Combat Fidelity), connecting 40+ previously disconnected subsystems into the battle loop. Source-backed historical scenarios use separately declared outcome envelopes; synthetic, test, calibration, and benchmark scenarios are not historical validation claims.

1. **Shared targeting decision** -- ordinary direct engagement must consume the
   same current owner-side contact, exact weapon, sensing/fire-control source,
   and range decision used by automatic movement standoff. Search-only,
   incompatible, unavailable, stale, or unsupported evidence fails explicitly.
2. **Domain filtering** -- the exact attached weapon definition must target the defender's domain (ground, air, naval)
3. **Posture/status check** -- ROUTED/SURRENDERED units skip; morale accuracy multiplier applied
4. **Suppression check** -- heavily suppressed units may skip engagement
5. **Fire-on-move check** -- `requires_deployed` weapons skip if attacker is moving
6. **Terrain cover/concealment** -- cover reduces hit probability; concealment reduces detection range
7. **Detection quality** -- sensor-derived `id_confidence` modulates engagement effectiveness
8. **Training level** -- unit quality multiplies hit probability
9. **ROE gate** -- `RoeEngine.check_engagement_authorized()` blocks engagements below the current ROE level's confidence threshold (WEAPONS_HOLD blocks all non-self-defense; WEAPONS_TIGHT requires high `id_confidence`)
10. **Post-movement revalidation** -- the selected target, weapon, ammunition,
    contact, and fire-control evidence must still be usable; failure records a
    typed outcome rather than selecting a hidden replacement.
11. **Hold-fire discipline** -- if enabled via `behavior_rules`, defensive units wait until targets are within effective range (default 80% of max range)
12. **Engagement resolution** -- ballistics, penetration, and damage applied

`MoraleRuntime` owns ordinary transitions and the related status, route, event,
and MORALE-stream transaction. After a transition, a **rout cascade** may force
nearby `SHAKEN`/`BROKEN` units to `ROUTED` in canonical candidate order. A
**rally check** can move an eligible `ROUTED` unit to `SHAKEN`; melee rout and
cascade are typed forced causes. These paths use logical scenario time and
commit through the same runtime rather than writing a parallel morale map.
Transition into `ROUTED` does not invent the threat direction and extra scatter
draw needed for a direction-bearing `RoutState`; an existing route is removed
on rally or surrender.

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

- **Entities** hold data (position, health, ammunition, status, equipment)
- **Modules** implement behavior (movement algorithms, detection math, combat resolution)
- Entities are passed to modules as arguments; modules return results or modify entity state

Current morale records are the deliberate exception to treating every
simulation value as entity-local data: one `MoraleRuntime` owns immutable
per-unit records and exposes a stable read-only mapping to battle, victory,
recording, API, and analysis consumers.

This means you can test combat resolution without a terrain engine, or test detection without a movement engine.

## Engine Wiring

Production consumers enter through one typed runtime-owned boundary:

```text
scenario YAML or typed config
  -> SimulationRuntimeFactory.prepare() / prepare_config()
  -> PreparedScenario.build()
  -> RuntimeSession.step() / run_to_completion() / finalize()
```

Preparation reads a YAML source once (or directly copies a typed
`CampaignScenarioConfig`), applies strict independent variants, and captures
source, code/worktree, data, authored-roster identity, the isolated selected
`EraConfig`, and one fully effective `EraRuntimeContract`. Era resolution and
calendar-horizon validation happen before runtime RNG construction. `build()` then
constructs a fresh session and verifies exact loaded side/cardinality,
duplicate-free IDs, loadout topology, commander/doctrine assignments, and
catalog provenance, while injecting the captured era contract without a later
registry lookup. `RuntimeSession.step()` returns `True` at terminal;
`run_to_completion()` and `finalize()` require a public terminal outcome.
Provenance exposes source/config fingerprints, exact seeds and rosters, code
and data revisions, catalog/doctrine/loadout fingerprints, and initial plus
arriving assignments.

### Source identity in checkouts and immutable images

Runtime source identity is Git-first. When preparation starts inside a Git
worktree, the resolver records `HEAD`, a dirty flag, and a content-sensitive
worktree fingerprint. A clean tree is identified by its commit; a dirty tree
also incorporates Git status, the tracked binary diff, and the path, mode,
size, and content of every untracked file. Symlinks and non-regular worktree
entries are rejected. If a `.git` control marker exists but Git is unavailable
or cannot verify the worktree, preparation fails rather than falling back to a
packaged identity.

The production Docker image deliberately omits `.git`. Its build requires an
explicit `SOURCE_REVISION` containing exactly 40 lowercase hexadecimal
characters. Builders must use a clean checkout so that this supplied
attribution names the staged source. After the locked Python environment is
installed, `stochastic_warfare.build_identity` writes the exact-schema
`stochastic_warfare/_build_identity.json`. That identity binds the supplied
commit to a canonical manifest digest over every regular file beneath
`stochastic_warfare/` and `api/`, plus `pyproject.toml` and `uv.lock`. Each
manifest entry contains the relative path, normalized executable mode, byte
size, and SHA-256 digest; generated identity and interpreter-cache files are
excluded. Missing directories or files, symlinks, special files, duplicate
identity keys, malformed values, and non-finite JSON are rejected.

When no Git worktree exists, runtime preparation loads the generated identity
and recomputes the complete application-source manifest. Missing or malformed
identity data and any packaged-source tampering fail before a
`PreparedScenario` can be used. A verified image reports the supplied commit,
`dirty=False`, and a fingerprint derived from the immutable-build kind, commit,
and source-manifest digest. Scenario and catalog inputs are outside this
application manifest and retain their separate runtime data and catalog
revisions.

`.github/workflows/build.yml` exercises this path on pull requests to `main`,
pushes to `main`, and manual dispatches. It builds with `GITHUB_SHA`, asserts
that `/app/.git` is absent, runs a bounded scenario through
`SimulationRuntimeFactory -> RuntimeSession`, and checks the expected commit
and clean immutable-image identity.

`ScenarioLoader` is the lower-level engine-wiring boundary used by that
factory. Given a scenario YAML or prevalidated effective config, it:

1. Parses the YAML into a `CampaignScenarioConfig` (pydantic-validated), or
   deep-copies a prevalidated effective config supplied by an orchestrator
2. Creates terrain, environment, and weather engines
3. Loads unit equipment, then preflights every reachable initial and
   reinforcement unit through the ordered typed equipment registry and one
   scenario-owned `RuntimeLoadoutBuilder`. Duplicate YAML keys, unmapped or
   unsupported weapon/sensor entries, catalog/semantic mismatches, and
   contradictory sensor policy fail before context publication.
4. Creates detection, combat, movement, one authoritative `MoraleRuntime`, C2,
   and logistics engines
   and, when `logistics.enabled` is true, materializes declared depot stock,
   unit inventories, supply nodes, and expanded direct routes
5. Wires optional subsystems from explicit enable flags after applying the
   selected era's capability gates:
   - `ew_config.enable_ew: true` -> creates EW engines (jamming, spoofing, ECCM, SIGINT)
   - `space_config.enable_space: true` -> strictly loads all space catalogs,
     materializes the explicitly selected constellations, and creates GPS,
     SATCOM, ISR, early-warning, and ASAT engines. Optional direct-ascent ASAT
     execution uses finite side-owned assets and scheduled exact-target orders;
     unsupported ASAT types fail during loading.
   - `cbrn_config.enable_cbrn: true` -> creates CBRN engines (dispersal, contamination, protection)
   - `school_config` present -> creates doctrinal school registry
   - `escalation_config` present -> creates escalation engine
   - `dew_config` present -> creates directed energy weapon engine
   - `era` specified -> loads era-specific data and engines
6. Creates always-on behavioral engines: ROE engine (default WEAPONS_FREE) and
   the rout planner coordinated by `MoraleRuntime`
7. Registers every initial unit once with `MoraleRuntime` from its side's
   validated `morale_initial`; `SimulationContext.morale_states` is the
   runtime's stable read-only `Mapping[str, MoraleState]`, not another owner
8. Returns a `SimulationContext` with everything wired together

`RuntimeForceBuilder` owns typed initial-force construction. It validates exact
unit enums, counts, positions, supported per-instance overrides, deterministic
IDs, loaded runtime domains, and final roster cardinality before publication.
Construction stages the force and RNG outcome so a failed build cannot consume
the caller's unit RNG stream.

Commander declaration is all-side or absent. Behavior is active only when
every side supplies a valid catalog profile; all omitted with no
`commander_config` creates no commander engine. Partial profiles, or any
`commander_config` with blank side profiles, reject. Exact initial and future
per-unit commander overrides and `school_config.unit_assignments` are validated
eagerly against the planned roster, profile catalog, and school catalog. The
resulting commander, school, and OODA assignments are runtime behavior, not
metadata; they survive reinforcement registration and checkpoint continuation.

The retained loadout builder creates every initial, arriving, and
checkpoint-reconstructed weapon/sensor attachment. Its immutable fingerprint
and per-unit resolution topology are part of checkpoint compatibility, while
live weapon, ammunition, sensor, and linked-equipment state remain the mutable
checkpoint payload. The detailed contract is
[Equipment Mapping and Runtime Loadouts](../specs/equipment-mapping.md).

One `TacticalTargetingRuntime` is also constructed at this boundary and bound
by identity to the context, engine, and battle manager. It owns a single
post-FOW `TargetingInterval` and immutable pictures keyed by exact tick, battle,
and shooter. Canonical loadout bindings connect every decision to exact source
equipment indexes; movement and ordinary direct engagement cannot construct a
parallel answer. Its default-on strict calibration gate may disable automatic
standoff, in which case the authorized range is exactly zero rather than the
former catalog-maximum fallback. Routed indirect fire, bomb, torpedo, ASW,
grenade, and melee ownership remains separate. The complete contract is
[Sensing-Aware Tactical Standoff](../specs/sensing-aware-tactical-standoff.md).

Ordinary FOW detection reuses one monotonically allocated side-local opaque
track while measurements remain within the estimator gate. A gated
replacement creates the next track and advances its ordinal before removing
the predecessor; failure leaves the predecessor, counter, and live contact
unchanged. Stored root-only target-to-track associations cross-bind privileged
targeting evidence to the side-safe ordinal and are validated by one shared
API/replay decoder without entering the side payload. Sensor-derived fusion
uncertainty is finite and strictly positive, with a generic one-metre minimum
at zero range. That minimum is numerical safety, not sensor accuracy;
sensor-specific covariance and atomic elapsed-time prediction remain REM-044.
Parallel FOW dispatch owns one RNG stream per side for both detection and any
configured stochastic identification; classification cannot draw from a
shared identification-engine stream.

Declared time-on-target missions pass through one simulation-layer resolver
after initial loadouts exist. It binds each declaration to the exact initial
unit and `(source_equipment_index, weapon_id)` attachment, validates the
weapon/ammunition/domain/range/timing contract, and passes immutable lower-layer
plans to `IndirectFireEngine`. The engine executes those plans once on the
fixed scenario cadence, reserves only the planned attachments from autonomous
fire until all their missions complete, and publishes one typed terminal event
per mission through the recorder and generic run-events API.

Checkpoint restore reconciles exact live-resource observations with scheduled
lifecycle history. A lower-level public weapon transition before or between
milestones is accepted only when ammunition depletion, total/maintenance
counters, finite advancing last-fire time, quantity cooldown, and checkpoint
chronology form one causal chain; the next scheduled milestone then observes
that state. Reservation governs autonomous battle selection, not the underlying
weapon-state authority. Reload-shaped increases remain unsupported and reject.

This path accepts authored whole-second fire-control times of flight for
supported tube-artillery or mortar weapons and positive-radius lethal
ammunition. It does not infer a firing-table solution, support rocket-artillery
time on target, or treat a live magazine increase as a reload: no production
reload path currently provides persisted Class V provenance. See
[Time-on-Target Execution](../specs/time-on-target-execution.md).

Space runtime state is orchestrated by one `SpaceEngine` boundary. Each tick
propagates orbits, advances existing debris, executes newly due ASAT orders,
then updates downstream GPS/ISR/early-warning/SATCOM consumers. Selected
optical/SAR IMINT constellations generate immutable, owner-scoped
`SpaceISRReport` values when `enable_space_effects` is active; a nonempty
fusion selection without that calibration gate rejects. Delayed delivery
transactionally creates an exact
`IntelDeliveryReceipt` and one owner/target `IMINTTrackAssociation`; queued
reports, receipts, associations, cadence, and reference integrity participate
in atomic checkpoint preflight. This does not inject reports directly into
ordinary fog-of-war contacts. Exact continuation with nonempty ordinary
`SideWorldView.contacts` remains REM-029, so Space ISR checkpoint evidence uses
an explicit empty ordinary-contact topology.

The selected catalog topology, satellite state, ASAT
inventory/orders/debris, service history, and SPACE RNG stream also participate
in whole-context checkpoint preflight. The detailed ASAT contract is
[ASAT Production Integration](../specs/asat-production-integration.md).

`SimulationEngine` then installs the validated reinforcement schedule exactly
once. Due waves are checked at every resolution and are committed atomically to
the campaign roster, context force map, live loadout maps, morale state, and
commander, school, OODA, movement-diagnostics, and enabled logistics topology.
If registration fails, all staged subsystem changes roll back and the wave can
be retried deterministically.

Movement diagnostics observe the decisions already made by strategic,
operational, and tactical movement managers; they never select a destination,
consume randomness, or move a unit. Canonically ordered typed reasons include
weapon standoff, resource blocked, and zero progress. Cumulative counters and a
bounded recent-observation window are checkpointed, and the scenario evaluator
derives semantic stuck/resource-blocked populations from those counters rather
than inferring intent from final displacement.

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

The engine supports five eras—one modern and four historical—each with
different available technologies:

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
- Strict sparse tick overrides for strategic, operational, and tactical
  cadence, plus medical treatment and maintenance repair durations. One
  frozen effective `EraRuntimeContract` constructs the clock and domain
  configs, participates in runtime fingerprints, and persists in format-115
  checkpoints. Unsupported C2/nuclear keys reject instead of acting as
  metadata proxies.
- Era-specific engine extensions

Built-in eras intentionally omit the former unsourced physics numbers. This
runtime contract does not imply automatic casualty admission, maintenance
registration/repair initiation, communications equipment topology, or
scheduled nuclear employment; those remain explicit remediation items.

Era data lives in `data/eras/{era_name}/` with the same directory structure as modern data.

## Determinism & Reproducibility

Within a validated deterministic contract, a run is reproducible when code,
data/catalog content, effective configuration, seed, and execution inputs are
identical:

### PRNG Discipline

- All randomness flows through `RNGManager`, which creates per-module `np.random.Generator` streams
- Each module gets its own independent PRNG stream via `RNGManager.get_stream(ModuleId)`
- No bare `random` module or `np.random` module-level calls anywhere in the codebase
- The same seed alone is insufficient when code, data, configuration, or
  runtime topology differs
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
- **Production batch execution** with ordered raw metric vectors, exact seeds,
  and source/code/data/catalog/doctrine/loadout provenance
- **A/B and doctrine comparison** over common seeds, plus strict parameter
  sweeps

The application lifespan owns one settings object, database connection, and run
manager. A run is accepted only after its effective scenario config validates
and its pending row commits. Shutdown rejects new work, cooperatively signals
run and batch workers, waits for the actual executor threads and terminal
SQLite writes, then closes the database. The grace timeout reports slow
workers; it does not abandon them.

The API layer imports `stochastic_warfare` as a library. Run, batch, comparison,
sweep, doctrine-comparison, MCP, and current-revision benchmark execution share
`SimulationRuntimeFactory -> PreparedScenario -> RuntimeSession`. A paired
benchmark's bounded historical reference adapter executes the actual reference
revision when that revision predates this boundary. Sparse calibration
overlays are applied to isolated typed variants; source scenario YAML is not
modified. Comparisons preserve paired counts/differences, superiority, raw
exact-sign p-values, Holm-adjusted p-values, and family-wise significance.
Unsupported metrics or incomplete/nonfinite runs fail rather than producing
plausible zeroes.

### Frontend (`frontend/`)

A React + TypeScript single-page application built with Vite:

- **TanStack Query** for API data fetching and caching
- **Plotly.js** for interactive charts (force strength, engagements, morale, tempo) with cross-chart tick sync
- **Canvas 2D** for the tactical map (terrain with elevation shading, unit positions, FOW filtering, sensor circles, engagement fade, playback)
- **React Router** for deep-linkable pages
- **Headless UI** for accessible modals, dropdowns, and menus

Key pages: Scenario Browser, Unit Catalog, Run Results (charts + narrative +
map), Scenario Editor (clone-and-tweak), Analysis (Monte Carlo, same-scenario
A/B comparison, sensitivity sweep, and doctrine comparison). Analysis views
validate and expose raw vectors and provenance instead of accepting summary-only
payloads.

See the [Web UI Guide](../guide/web-ui.md) for usage documentation.

## Consequence Enforcement Gates

The engine's legacy resource-consumption and C2-friction consequences use an
opt-in pattern. Those gates are `CalibrationSchema` `enable_*` fields that
default to `False`. Integrity gates need not be opt-in: Phase 115's strict
`enable_sensing_aware_standoff` defaults to `True`, and disabling it authorizes
zero automatic standoff rather than restoring the defective catalog-range
fallback.

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

Additional non-flag consequences include fire zone damage
(`fire_damage_per_tick`), stratagem expiry (`stratagem_duration_ticks`),
guerrilla retreat distance, and order misinterpretation effects. Deterministic
retreat remains supported when guerrilla blending is zero. A positive value
reaching the battle guard fails explicitly before position, status, morale,
events, or COMBAT/MORALE RNG state changes because the runtime has no valid
non-morale concealment owner. The loaded runtime cannot yet recognize a
populated area through its `population_manager`; the guard is not a claim that
the positive branch is production-reachable. REM-032/Phase 119 owns the lookup
and concealment replacement.

The `enable_all_modern` meta-flag activates all 21 non-deferred flags at once
for convenience. Individual flag control is preferred when a scenario does not
need every consequence. No general performance multiplier is claimed without
the controlled semantic-equivalence evidence queued under REM-031.

## Checkpointing

Checkpoint-participating runtime owners implement the checkpoint protocol:

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

The current `SimulationEngine` checkpoint schema is version 115. In addition
to exact force/loadout/logistics/time-on-target state and the single
`morale_runtime` envelope, it stores one fully effective
`era_runtime_contract` plus the tactical-targeting interval, battle
memberships, decisions, post-movement revalidations, enablement, default
visibility, and exact source bindings. The current resolution, clock duration, selected
registry identity, captured scenario cadence/horizon inputs, and frozen
medical/maintenance consumers must agree before mutation; format 114 and every
other explicit non-current version reject. There is no current-format morale
context map or state-machine copy, and `RNGManager` alone persists the MORALE
stream. Commander/OODA assignments, bounded movement diagnostics, and typed
Space ISR queues, receipts, and owner/target associations remain included.
Restore stages and validates topology, identity, chronology, mutable
resources, statuses, routes, and relevant RNG state against a fresh compatible
runtime before committing any mutation. Bounded versionless compatibility
remains subject to the stricter subsystem rules in the
[checkpoint state contract](../specs/checkpoint-state.md).
