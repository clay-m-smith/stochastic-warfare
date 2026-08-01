# Remediation Backlog

This is the auditable source of truth for implementation gaps surfaced after the
Phase 104 review. Historical phase status remains unchanged; closing an item
here requires new production-path evidence.

Audit baseline: 2026-07-28 at `68acd4b`

## Evidence legend

- `D`: declared in a typed schema or interface
- `L`: loaded into the production runtime
- `W`: wired into the production execution path
- `E`: enabled and disabled behavior verified
- `X`: exercised under realistic production-path preconditions
- `O`: shown to change an observable outcome
- `P`: persisted or exposed through every required boundary

`-` means not yet proven. `N/A` requires a written reason in the issue record.

## Ranked issues

| ID | Priority | Phase | Area | Behavioral gap | Status | D | L | W | E | X | O | P | Next proof |
|---|---:|---:|---|---|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|---|
| REM-001 | P0 | 105 | Checkpointing | Exact fresh restore, including empty production loadout entries | **Closed** | Yes | N/A | Yes | N/A | Yes | Yes | Yes | [Phase 105 follow-up](devlog/phase-105.md#reclosure-evidence) |
| REM-002 | P0 | 106 | API execution | `config_overrides` are merged for validation but the run reloads the unchanged scenario file | **Closed** | Yes | Yes | Yes | N/A | Yes | Yes | Yes | [Phase 106](devlog/phase-106.md#postmortem) |
| REM-003 | P0 | 106 | API lifecycle | Background run teardown can use a closed database session | **Closed** | Yes | N/A | Yes | N/A | Yes | N/A | Yes | [Phase 106](devlog/phase-106.md#postmortem) |
| REM-004 | P0 | 107 | Reinforcements | Scenario reinforcements are not registered automatically with `CampaignManager` | **Closed** | Yes | Yes | Yes | N/A | Yes | Yes | Yes | [Phase 107](devlog/phase-107.md#postmortem) |
| REM-005 | P0 | 107 | Reinforcements | Arriving units do not receive their defined weapons and sensors | **Closed** | Yes | Yes | Yes | N/A | Yes | Yes | Yes | [Phase 107](devlog/phase-107.md#postmortem) |
| REM-006 | P1 | 107 | Morale | Side `morale_initial` is ignored; all units start steady | **Closed** | Yes | Yes | Yes | N/A | Yes | Yes | Yes | [Phase 107](devlog/phase-107.md#postmortem) |
| REM-007 | P1 | 107 | Feature gates | Era `disabled_modules` selected by the scenario is loaded but does not gate runtime capabilities | **Closed** | Yes | Yes | Yes | Yes | Yes | Yes | Yes | [Phase 107](devlog/phase-107.md#postmortem) |
| REM-008 | P0 | 108 | Logistics | Scenario depots do not initialize stock or a supply network | **Closed** | Yes | Yes | Yes | Yes | Yes | Yes | Yes | [Phase 108](devlog/phase-108.md#postmortem) |
| REM-009 | P0 | 108 | Logistics | Supply-network updates and idle consumption are not applied by the production loop | **Closed** | Yes | Yes | Yes | Yes | Yes | Yes | Yes | [Phase 108](devlog/phase-108.md#postmortem) |
| REM-010 | P0 | 109 | Equipment data | Loadout mapping has duplicate/wrong keys, 22 unmapped catalog entries, and validation-layer ownership | **Closed** | Yes | Yes | Yes | N/A | Yes | Yes | Yes | [Phase 109](devlog/phase-109.md#postmortem) |
| REM-011 | P1 | 110 | Space combat | The production ASAT hook is an explicit placeholder | **Closed** | Yes | Yes | Yes | Yes | Yes | Yes | Yes | [Phase 110](devlog/phase-110.md#postmortem) |
| REM-012 | P1 | 111 | Indirect fire | Time-on-target uses dummy coordinates, has no executed state, and has no production caller | **Closed** | Yes | Yes | Yes | Yes | Yes | Yes | Yes | [Phase 111](devlog/phase-111.md#postmortem) |
| REM-013 | P1 | 112 | Validation trust | Default CI hides excluded suites; Phase 109 established a green full Python Ruff baseline, but CI does not yet enforce the complete suite contract | **Closed** | Yes | N/A | Yes | N/A | Yes | N/A | Yes | [Phase 112](devlog/phase-112.md#postmortem) |
| REM-014 | P1 | 112 | Test quality | Structural and no-assert tests can support false completion claims | **Closed** | Yes | N/A | Yes | N/A | Yes | Yes | N/A | [Phase 112](devlog/phase-112.md#postmortem) |
| REM-015 | P2 | 112 | Documentation | Strict documentation build was not part of the verified baseline | **Closed early** | Yes | N/A | Yes | N/A | Yes | N/A | N/A | [Phase 105 verification](devlog/phase-105.md#final-broader-verification) |
| REM-016 | P1 | TBD | Aggregation | Disaggregation recreates every constituent as base `Unit` and does not restore captured weapon, sensor, or supply attachments | Queued | Yes | Yes | Yes | N/A | - | - | - | Subclass/loadout round trip across aggregation |
| REM-017 | P0 | 112 | Analysis tooling | Scenario batches can accept empty invalid rosters and silently turn unsupported metrics into zero | **Closed** | Yes | Yes | Yes | N/A | Yes | Yes | Yes | [Phase 112](devlog/phase-112.md#postmortem) |
| REM-018 | P1 | 114 | Era overrides | `physics_overrides` and `tick_resolution_overrides` are declared and documented but have no production consumer | Queued | Yes | Yes | - | N/A | - | - | Yes | Typed override changes its production engine/clock behavior |
| REM-019 | P1 | 113 | Morale state | `SimulationContext.morale_states` and `MoraleStateMachine` are independently mutable and can diverge after rout or aggregation paths | **Closed** | Yes | Yes | Yes | N/A | Yes | Yes | Yes | [Phase 113](devlog/phase-113.md#postmortem) |
| REM-020 | P1 | TBD | Logistics | March/combat consumption is computed with fabricated defaults and discarded | Queued | Yes | Yes | - | - | - | - | - | Typed activity demand changes real inventory once per logical interval |
| REM-021 | P1 | TBD | Logistics | Abstract Class III/V inventory is independent of live entity fuel and weapon magazines | Queued | Yes | Yes | - | - | - | - | Yes | One explicit authority or conservative synchronization contract |
| REM-022 | P2 | 112 | Documentation navigation | Strict MkDocs succeeds while seven historical devlog-index fragment links target missing anchors | **Closed** | Yes | N/A | Yes | N/A | Yes | N/A | N/A | [Phase 112](devlog/phase-112.md#postmortem) |
| REM-023 | P1 | 112 | Scenario data trust | Missing commander profile references warn once per unit while scenario evaluation still reports OK | **Closed** | Yes | Yes | Yes | N/A | Yes | Yes | N/A | [Phase 112](devlog/phase-112.md#postmortem) |
| REM-024 | P1 | 112 | Unit data trust | Invalid crew-skill enums are hidden by a broad `KeyError` catch and silently drop historical units | **Closed** | Yes | Yes | Yes | N/A | Yes | Yes | N/A | [Phase 112](devlog/phase-112.md#postmortem) |
| REM-025 | P2 | 112 | Scenario diagnostics | `MANY_STUCK_UNITS` treats legitimate corrected weapon-range standoff as a movement failure | **Closed** | Yes | N/A | Yes | N/A | Yes | Yes | N/A | [Phase 112](devlog/phase-112.md#postmortem) |
| REM-026 | P1 | 112 | Benchmark trust | A hard 60-second Golan assertion contradicts the checked-in 500-second baseline and fails code that is faster than that baseline | **Closed** | Yes | N/A | Yes | N/A | Yes | Yes | Yes | [Phase 112](devlog/phase-112.md#postmortem) |
| REM-027 | P2 | 112 | Space ISR state | Buffered ISR checkpoint reports use generic JSON normalization rather than a typed semantic rehydration boundary | **Closed** | Yes | Yes | Yes | N/A | Yes | Yes | Yes | [Phase 112](devlog/phase-112.md#postmortem) |
| REM-028 | P1 | 115 | Sensing/combat | Tactical movement can hold at catalog weapon range beyond usable sensing range | Queued | - | Yes | Yes | - | Yes | Yes | - | Sensing-aware standoff enabled/disabled production comparison |
| REM-029 | P1 | 116 | Fog-of-war state | Ordinary contacts serialize but are discarded by `FogOfWarManager.set_state()` | Queued | Yes | Yes | Yes | N/A | Yes | Yes | - | Nonempty-contact fresh continuation with exact COP behavior |
| REM-030 | P1 | 117 | Historical validation | At the Phase 112 baseline, catalog winner tables, legacy comparisons, and public docs claimed historical validation without a production, provenance-bearing, held-out outcome-envelope contract; fresh Debecka production exposed incompatible casualty units and a duration miss | Queued | Yes | - | - | N/A | Yes | Yes | - | Per-claim validated/regression-only/unsupported disposition plus typed held-out production-envelope artifacts |
| REM-031 | P1 | 118 | Performance semantics | At the Phase 112 baseline, Block 9 claimed five performance flags preserve scenario outcomes, but its regression executed only authored configurations, excluded the only two all-flag scenarios, and had no same-input disabled controls | Queued | Yes | Yes | Yes | - | - | - | - | Per-flag semantic classification and common-seed production off/on evidence with persisted provenance |
| REM-032 | P1 | 119 | Guerrilla concealment | Populated-area blend probability was mapped to morale-owned `ROUTING`, while the production context exposes no matching population query or concealed-unit owner | Queued | Yes | Yes | - | - | - | - | - | Typed non-morale concealment changes targetability and persists/exposes its lifecycle |
| REM-033 | P1 | 120 | Surrender/POW state | A public rout helper emitted `SurrenderEvent` and a synthetic POW count without changing authoritative morale/status; no production captor or prisoner lifecycle consumes it | Queued | Yes | Yes | - | N/A | - | - | - | Typed runtime surrender creates captor-owned prisoners and persists/exposes the complete lifecycle |
| REM-034 | P1 | 121 | Event time | Aggregate combat and auto-resolve publish exposed events with `datetime.min` instead of authoritative simulation time | Queued | Yes | Yes | - | N/A | - | - | Yes | Production aggregate/auto-resolve events use exact logical clock time and persist/replay |

## REM-001 - Exact checkpoint restoration

### Requirements

- A checkpoint must capture and restore every unit's concrete class, side,
  ordering, and mutable entity state.
- Restore morale as `MoraleState` values, not untyped integers.
- Restore each weapon instance's ammunition, maintenance-round count, equipment
  condition, and fire cooldown, plus sensor runtime condition.
- Reuse existing unit, crew, and equipment objects when stable IDs and concrete
  types match so live weapon, sensor, and engine references remain valid.
- Reconstruct checkpoint units missing from a fresh runtime without consuming
  an RNG stream.
- Remove runtime-only units that are absent from the checkpoint.
- Reject duplicate entity IDs, unknown unit-class discriminators, and malformed
  morale values before committing a partial force/morale restore.
- Reject a different effective scenario configuration or incompatible
  weapon/sensor topology before mutating context-owned runtime state.
- A legacy checkpoint without unit/morale sections must leave the runtime roster
  untouched. Legacy unit snapshots without a class discriminator must use
  deterministic field-based inference.
- Restoring and continuing must produce the same state as uninterrupted
  continuation from the same checkpoint.

### Non-goals

- This phase does not repair reinforcement registration or loadout assignment;
  those are REM-004 and REM-005.
- This phase does not invent serialization for subsystem fields whose own
  `get_state()` implementation omits mutable state. Such findings become
  separate backlog items.
- Checkpoint schema migration/version negotiation remains outside this phase.

### Production trace

`SimulationEngine.get_state()` delegates to `SimulationContext.get_state()`,
which writes units and morale. `SimulationEngine.set_state()` delegates back to
`SimulationContext.set_state()`, which currently restores neither.

### Failing proof

The initial behavioral suite produced 7 failures and 1 compatibility-control
pass. Adversarial review then proved weapon branches could diverge while their
serialized engine states still compared equal, because loadout runtime state was
absent.

### Verification

Initially closed by 19 Phase 105 behavioral tests covering exact entity, morale,
weapon/sensor, configuration, corruption, atomic-rejection, legacy, bytes,
continuation, and fully loaded production-scenario behavior. See
[`phase-105.md`](devlog/phase-105.md) for exact commands and broader results.

Reopened during the Codex skill-port forward test. A production-shaped
checkpoint with `unit_weapon_states={"u": []}` and
`unit_sensor_states={"u": []}` rejects reconstruction of checkpoint-only unit
`u` as an incompatible extra topology. The contract permits fresh
reconstruction for an empty loadout; only non-empty serialized loadouts require
compatible prebuilt runtime instances.

Reclosed on 2026-07-28 after the restore path accepted and exactly preserved
empty checkpoint loadout entries, ignored and pruned stale loadouts belonging
to non-reusable same-ID units, and continued rejecting non-empty reconstructed
weapon or sensor state before mutation. The final behavioral suite has 23
tests; the checkpoint-wide selection passed 108 tests with 1 skipped, and the
fresh default suite passed 10,168 tests. A repeated adversarial postmortem found
no remaining medium- or high-severity issue in the repair.

### Residual boundaries

- Restore requires the same repository/data-catalog revision. Checkpoints do not
  embed hashes of external unit, weapon, ammunition, sensor, or era definitions.
- Aggregation constituent reconstruction remains REM-016.

## REM-002 - API overrides do not reach the loaded scenario

### Requirements

- `RunSubmitRequest.config_overrides` is a partial `CalibrationSchema` overlay,
  not an unrestricted top-level scenario patch.
- Normalize the scenario's existing calibration and the submitted partial
  overlay to the structured schema, recursively merge mappings, replace
  scalars/lists, and let submitted values win.
- Validate both the partial overlay and the complete effective
  `CampaignScenarioConfig` before committing a run row or scheduling work.
- Reject unknown, dead, malformed, or top-level scenario keys with HTTP 422.
- Pass one isolated effective configuration to `ScenarioLoader`, terrain/frame
  capture, victory setup, duration/tick calculations, and summary generation.
- Preserve the source YAML byte-for-byte. Concurrent runs must not share or
  mutate effective configuration state.
- An empty overlay must be behaviorally identical to omitting the field.
- Persist and expose the submitted overlay through run detail while ensuring
  the stored result belongs to that effective configuration.

### Production trace and failing proof

At the Phase 106 starting revision, `POST /api/runs` validated
`RunSubmitRequest`, resolved the scenario, called `RunManager.submit()`, created
a SQLite row, and scheduled `_execute_run()`. `_run_sync()` merged the request
into an in-memory root YAML mapping, then called `ScenarioLoader.load(path)`,
which reopened the unchanged file. Engine context, calibration, forces, and
battle behavior therefore ignored the request while API-side terrain, victory,
timing, and summary code could see a different unvalidated root mapping.

A same-seed production control using `test_campaign` and
`roe_level=WEAPONS_HOLD` produced the same 108 events as the baseline through
the current API execution path. Loading an otherwise identical effective YAML
produced zero engagement events and left all ten units active, proving the
parameter is wired when it actually reaches `ScenarioLoader`.

### Verification

Verified on 2026-07-28. A same-seed real API A/B produces engagements and disabled
units under the baseline and zero engagements with all ten units active under
`WEAPONS_HOLD`. Repeated effective configurations compare equal across every
stored result, event, snapshot, terrain, and frame payload; omitted, empty, and
explicit-default overlays also match.

Loader and API tests prove non-default nested sibling preservation, mapping
merge/list replacement, canonical-plus-legacy normalization, isolated
concurrent configs, canonical overlay exposure, and byte-identical source YAML.
Unknown, dead, wrong-namespace, coercible wrong-type, unsupported semantic, and
unknown-side inputs return 422 before a row or task exists.

The accepted `nearest` target-selection alias now reaches the real closest
selection branch. Three archived-baseline/current production scenario pairs
showed expected semantic changes with no evaluator diagnostics; see
[Phase 106](devlog/phase-106.md#determinism-and-scenario-evaluation). This is
contract evidence, not a historical-fidelity claim.

`Enabled` is N/A because this is immutable run input, not an optional subsystem.
Checkpoint persistence is N/A because the effective configuration is fixed
before context construction; SQLite/API persistence remains required.

## REM-003 - Background execution can outlive database ownership

### Requirements

- One FastAPI lifespan owns one initialized `Database` and one `RunManager`,
  using the exact settings supplied to `create_app()`.
- A 202 response means the durable `pending` row exists and the manager accepted
  responsibility for the task.
- The manager must stop accepting work when shutdown begins and shutdown must be
  idempotent.
- On normal or exceptional lifespan exit, signal every run and batch
  cooperatively, wait for the actual worker to stop, persist one terminal state,
  notify subscribers, clear bookkeeping, and only then close the database.
- Valid transitions are `pending -> running -> completed|failed|cancelled` and
  `pending -> cancelled`. Cancellation is not failure.
- A completed row and all result/event/snapshot/terrain/frame payloads commit in
  one database transaction. Failed rows include the completion time and error.
- The shutdown timeout is a cooperative grace threshold, not permission to
  abandon an executor thread or close its database. A hard bounded stop would
  require a future move to killable worker processes.
- Background exceptions must be retrieved. Missing-row status updates must fail
  explicitly instead of silently discarding terminal state.
- Deleting an active run must cancel and await its task before removing the row.

### Production trace and failing proof

At the Phase 106 starting revision, the app normally called
`RunManager.shutdown()` before `Database.close()`, but lifespan cleanup was not
protected by `finally` and ignored settings passed to `create_app()`. API
fixtures closed the database without shutting down the manager. A submit-only
API test therefore passed while emitting an un-retrieved
`sqlite3.ProgrammingError: Cannot operate on a closed database`; batch
submission reproduced the same false green.

Forced `shutdown(timeout=0)` cancels only the asyncio wrapper around
`run_in_executor`. The worker thread continues, its shared cancellation flag is
removed, and the durable row remains `running` permanently. Cooperative
cancellation is also recorded as `failed`, and active deletion can remove a row
while its task still owns it.

### Verification

Verified on 2026-07-28. Real-router run and batch submissions followed by
immediate lifespan exit persist `cancelled` before SQLite closes. Controlled
workers prove that zero-grace and caller-cancelled shutdown both wait for the
actual executor thread. Normal, exceptional, and startup-failure lifespan paths
preserve resource ownership and exact factory settings.

Failure tests prove `failed`, completion time, exact error, terminal subscriber
notification even when a queue is full, and empty bookkeeping. Task callbacks
retrieve unpersistable background exceptions. Submission after shutdown is
rejected without a row, active deletion cancels and awaits, and missing-row
updates fail explicitly. Serialized SQLite write transactions prevent a failed
concurrent update from rolling back a valid run or batch update.

`Loaded`, `Enabled`, and simulation `Outcome` are N/A for resource ownership.
Production exercise and SQLite/API persistence are mandatory.

### Residual boundary

The thread-based executor cannot safely hard-kill a permanently blocked worker.
The grace timeout therefore warns and continues waiting; a bounded hard stop
would require process isolation. A fatal SQLite write failure is surfaced and
retrieved but cannot create a durable terminal row.

## REM-004 - Scenario reinforcements are not registered automatically

### Requirements

- `SimulationEngine` owns exactly one registration of
  `ctx.config.reinforcements`; callers must not resample or reset the schedule.
- A wave becomes due on the first engine tick whose logical elapsed time is at
  least its fixed or sampled arrival time, including tactical ticks.
- Empty schedules consume no RNG and publish no event. Stochastic arrival keeps
  the existing ordered log-normal multiplier and `CORE` stream contract.
- Wave order and unit declaration order are stable. Entity IDs include the
  schedule ordinal and within-wave ordinal so repeated same-side/type waves
  cannot collide.
- A whole wave is staged and committed atomically. Invalid sides, unit types,
  counts, timing spread, positions, duplicate IDs, or runtime construction must
  not leave a partial roster or publish a successful arrival event.
- A successful wave is added once and publishes one
  `ReinforcementArrivedEvent` after the complete runtime registration succeeds.
- Before- and after-arrival checkpoints restore the exact sampled schedule,
  roster, attachment state, and no-repeat behavior.

### Production trace and failing proof

`ScenarioLoader` parses `CampaignScenarioConfig.reinforcements`, but
`SimulationEngine.__init__()` constructs a `CampaignManager` with an empty
private schedule. Production API, MCP, validation, and batch paths never call
`set_reinforcements()`. Historical tests and `scripts/evaluate_scenarios.py`
manually call it, masking the gap.

A real `test_campaign` load declares one wave, registers zero, and remains at
four blue units after three strategic ticks. The three-wave reinforcement
fixture also assigns the same IDs to both blue M1A2 waves because the local
unit index restarts for every wave.

### Non-goals

- Do not replace the configured schedule with a Poisson process or change the
  log-normal `arrival_sigma` model.
- Do not tune scenario timing or force composition.
- Broader dynamic aggregation reconstruction remains REM-016.

### Closure evidence

Phase 107 made `SimulationEngine` the sole schedule owner, checked due waves on
every engine tick, assigned ordinal-stable IDs, and committed each wave only
after full runtime registration. Before/after-arrival checkpoint tests cover
sampled timing, arrival flags, exact roster topology, retry/no-repeat behavior,
and legacy/current ID migration. Same-seed event and checkpoint bytes are
identical.

## REM-005 - Reinforcements do not receive runtime attachments

### Requirements

- Initial and reinforcement units use one production loadout builder and the
  same scenario calibration/equipment mapping.
- Every arriving unit receives its sorted live weapon/ammunition and sensor
  instances, with each instance linked to that unit's equipment object, before
  the wave is visible or its event is published.
- Dynamic loadout maps have independent keys for every stable reinforcement ID.
- A reinforcement must be able to detect or engage through the normal
  production battle path; constructor presence alone is insufficient proof.
- Fresh-runtime checkpoint restore must deterministically rebuild compatible
  dynamic loadout topology without an RNG draw, then restore exact mutable
  weapon, ammunition, sensor, and equipment state.
- Unsupported or mismatched dynamic topology fails before checkpoint mutation.

### Production trace and failing proof

`ScenarioLoader._build_all_forces()` calls the validation runner's weapon and
sensor assignment helpers for initial units. `CampaignManager` later calls only
`UnitLoader.create_unit()`, so a diagnostic pair of arriving M1A2s contains
weapon and sensor equipment but has no `ctx.unit_weapons` or
`ctx.unit_sensors` entries. The Phase 105 restore path consequently rejects a
checkpoint-only reinforcement with a non-empty loadout.

### Non-goals

- Phase 107 preserves the current equipment-name mapping semantics. Duplicate
  or semantically wrong mappings remain REM-010/Phase 109.
- Logistics, command hierarchy, and every optional engine's dynamic unit
  registry are not implied by this loadout repair.

### Closure evidence

Initial and dynamic units now pass through one production loadout entry point.
Two same-type waves receive independent keys and exact linked weapon,
ammunition, sensor, and equipment state. A dynamically arrived M1A2 detects,
fires, and consumes ammunition through the normal production battle path.
Fresh-runtime restore rebuilds its declared topology without RNG and rejects a
missing or mismatched attachment key before mutation.

## REM-006 - Side initial morale is ignored

### Requirements

- `morale_initial` accepts exactly the runtime states `STEADY`, `SHAKEN`,
  `BROKEN`, `ROUTED`, and `SURRENDERED`; the default is `STEADY` and invalid,
  stale, or case-mismatched names fail scenario validation.
- Initial and reinforcement units receive typed `MoraleState` values from
  their side declaration in both `SimulationContext.morale_states` and
  `MoraleStateMachine`, without an RNG draw or fabricated transition event.
- Initial `ROUTED` and `SURRENDERED` morale synchronizes the corresponding unit
  status; other initial states remain active.
- The first morale update must begin from the configured state rather than
  lazily replacing it with `STEADY`.
- Contrasting same-seed production controls must show the configured state at
  load, through checkpoint continuation, and in a morale-dependent outcome.

### Production trace and failing proof

`SideConfig.morale_initial` is an unrestricted string copied into an otherwise
unused `ForceDefinition`. `ScenarioLoader.load()` then hard-codes every unit to
`MoraleState.STEADY`, while the independently serialized morale machine starts
empty and lazily creates another steady state.

The production Goose Green scenario declares six red units `SHAKEN`; all
twelve loaded units are currently steady and the machine contains no unit
states.

### Non-goals

- This phase does not tune morale transition probabilities or historical
  calibration.
- Initial-state registration does not invent analytics transition events.

### Closure evidence

Scenario validation accepts exactly the five runtime names and initializes both
morale stores for initial and dynamic units without an RNG draw or transition
event. Routed/surrendered status synchronization, Goose Green's declared
`SHAKEN` state, a controlled morale-collapse outcome, current-checkpoint strict
topology, and bounded versionless migration are covered by behavioral tests.
The remaining two-store ownership risk after later cascade/aggregation writes
is recorded separately as REM-019.

## REM-007 - Era feature gates are dead metadata

### Requirements

- The scenario `era` must resolve to a registered era. Unknown era names and
  unknown disabled-feature names fail validation instead of falling back to
  modern behavior or being ignored.
- The supported gate keys are exactly `ew`, `space`, `cbrn`, `gps`,
  `thermal_sights`, `data_links`, and `pgm`. The last four are capability
  gates, not whole engine suites.
- Registry lookups return an isolated effective era configuration. The same
  effective gate is exposed on the context and compared during checkpoint
  restore.
- Whole-suite precedence is explicit: missing or `enable_*=false` configuration
  creates no suite; enabled configuration creates it only when the era permits
  it; an enabled block that contradicts the era fails scenario loading.
- `space` removes the full space suite; `gps` removes its GPS child and must
  never improve guided accuracy through a nominal fallback.
- `thermal_sights`, `data_links`, and `pgm` reject forbidden production
  loadouts. `available_sensor_types` is enforced at the same boundary.
- Gates apply before optional engine RNG streams are allocated and before a
  forbidden runtime object is committed.
- Enabled/disabled production controls must prove observable engine, loadout,
  event, state, or outcome behavior. Set membership or source inspection is
  insufficient.

### Production trace and failing proof

`ScenarioLoader.load()` retrieves `era_config.disabled_modules` into a local
`disabled` variable and never reads it again. Optional EW, space, and CBRN
construction depends only on a config block, while the sensor allowlist and
four capability keys have no production consumer. `EraConfig` accepts
`{"bogus"}`, an unknown scenario era silently resolves to modern, and a
top-level scenario `disabled_modules` key is not part of the schema.

### Non-goals

- Phase 107 does not add new disabled-feature names or redesign historical era
  physics.
- Era-specific combat models and data corrections remain separate work.
- Feature rejection does not silently substitute an unrelated weapon, sensor,
  or navigation model.

### Closure evidence

Era and feature names are strict and registry lookups are isolated. Missing,
false, enabled, and era-forbidden EW/space/CBRN controls prove suite
construction behavior; GPS-child, thermal, data-link, PGM, and sensor-allowlist
controls prove capability rejection. The effective era contract is canonical
in checkpoints and a mismatch fails before mutation. Declared but unconsumed
physics/tick override metadata remains REM-018.

## REM-008 - Scenario logistics do not initialize runtime topology

### Requirements

- `CampaignScenarioConfig` has one strict, typed, opt-in `logistics` contract
  containing `enabled`, a positive finite update interval, unit profiles, and
  direct route templates. Omission and `enabled: false` are equivalent.
- Each unit profile is uniquely selected by `(side, unit_type)` and declares
  independent initial inventory, maximum inventory, and positive item-native
  idle-consumption rates. Duplicate supply-class/item pairs are rejected.
- Each supply entry uses an exact `SupplyClass` name, catalog `item_id`, and
  positive finite quantity. The class must match the catalog definition;
  initial inventory cannot exceed maximum inventory, and every consumption
  item must have an explicit maximum.
- Enabled logistics requires every initial and reinforcement unit type to have
  exactly one same-side profile. No missing profile, maximum, item, rate, stock,
  or connectivity is inferred.
- `DepotConfig` is strict. IDs are non-empty and globally unique; positions are
  two or three finite ENU coordinates; capacity and throughput are positive and
  finite; condition is in `[0, 1]`. Enabled depots require an exact
  `DepotType` and explicit inventory (which may intentionally be empty).
- Depot initial inventory is resolved through the effective data root's supply
  catalog and its weight must not exceed depot capacity.
- Each strict route template has a unique ID, side, same-side depot, non-empty
  unit-type list, exact `TransportMode`, positive finite transport speed and
  tonnage capacity, and condition in `[0, 1]`. Parallel templates that would
  overwrite the same directed depot/unit edge are rejected.
- `ScenarioLoader` preflights structural, catalog, reference, mass, and topology
  errors before runtime mutation. It then installs exact depot stock, one depot
  node per depot, one independent inventory and unit node per live profiled
  unit, and stable expanded direct routes.
- Initial and arriving units share one staged registration boundary. A
  reinforcement logistics error leaves the wave pending, the roster/loadouts/
  morale/topology unchanged, and publishes no arrival or delivery event.
- Runtime identifiers derive only from declared IDs and stable entity IDs.
  State-affecting iteration and tie-breaking are explicit and sorted.
- Resupply uses only reachable same-side declared routes and catalog-backed
  stock. Candidate depots are ordered by transit time then depot ID; active
  units are allocated greedily by side/entity ID and items by supply class/item
  ID. Phase 108 does not claim proportional fairness or optimization.
- Transfers are limited by item mass, update duration, depot stock, depot
  throughput/condition, and every route's remaining capacity/condition.
  Depot debit, unit credit, route flow, and one item-specific typed event
  journal entry are assembled in the same rollback-safe boundary. Observer
  notification occurs once after state/cadence commit; all observers are
  attempted before any subscriber error propagates.
- Delivery events contain the logical timestamp, depot, recipient, route,
  supply class, item ID, item-native quantity, and transport mode. Generic
  recorder/API event exposure is required; a new inventory-summary endpoint is
  not.
- Existing depot-only scenarios remain valid and inert. Capacity and
  throughput metadata alone do not invent mixed stock, depot type, unit
  capacity, or connectivity.

### Production trace and failing proof

`scenario YAML -> CampaignScenarioConfig.logistics plus side depots ->
ScenarioLoader validation -> StockpileManager and SupplyNetworkEngine ->
LogisticsRuntime -> SimulationEngine -> inventory, supply state, victory,
recorder/API event, and checkpoint`

At the Phase 108 starting revision, `DepotConfig` carries only identity,
position, capacity, and throughput. The production loader creates empty
logistics engines but never consumes a side's depot declarations. A real load
of `test_campaign_logistics` therefore reports three configured depots and zero
runtime depots, unit inventories, nodes, or routes. Phase 6 tests manually
construct and invoke every subsystem, so they are not production-wiring proof.

The initial behavioral proof must load an enabled configuration through
`ScenarioLoader` and fail on the absent exact topology, transfer, delivery
event, reinforcement registration, and fresh checkpoint continuation. A
depot-only legacy scenario is the disabled control.

### Persistence and compatibility

- Engine checkpoint format advances from 107 to 108. Explicit older, newer,
  malformed, boolean, or null versions reject before mutation.
- Versionless compatibility remains bounded to logistics-disabled
  configurations. An enabled runtime cannot reconstruct elapsed inventory
  history or topology from a legacy checkpoint.
- Stockpile state preserves every depot field/inventory, unit inventory and
  maximum, and its existing spoilage accumulator. Supply-class JSON keys
  normalize back to integers.
- Network state preserves complete node and route fields, including echelon,
  infrastructure, throughput, current flow, and infrastructure links.
- The logistics runtime preserves cadence remainder, per-unit accounting time,
  and boundary positions used to distinguish idle from movement.
- Current state must agree with the scenario-derived depot/profile/route
  contract and restored roster. Logistics state is fully staged before the
  clock, RNG, roster, managers, recorder, or events mutate.

### Non-goals

- No implicit stock, road discovery, cross-side connection, multi-echelon or
  min-cost flow, or fair-share allocator.
- No `TransportEngine` mission, convoy, in-transit queue, delay, escort, or
  cargo-loss model. Transit time selects a direct source but delivery is an
  aggregate cadence operation.
- No stochastic spoilage activation and no new logistics RNG draw.
- No march/combat consumption or synchronization with weapon magazines or
  entity fuel. Those independent gaps are REM-020 and REM-021.
- No historical calibration or military-stock assertion. The enabled fixture
  is a synthetic behavioral test, not a fidelity claim.

### Closure evidence

Phase 108 added the strict root schema and made `ScenarioLoader` the single
owner of depot, unit-inventory, node, and expanded direct-route construction.
The enabled production fixture proves exact catalog-backed topology, bounded
same-side delivery, generic delivery-event provenance, atomic initial and
reinforcement registration, and exact fresh-runtime checkpoint continuation.
Omitted, explicitly disabled, disconnected, wrong-side, invalid-catalog, mass,
duplicate, and topology controls establish the negative contract. See the
[Phase 108 postmortem](devlog/phase-108.md#postmortem).

## REM-009 - Logistics updates and idle consumption are absent from the loop

### Requirements

- A dedicated injected `LogisticsRuntime` owns cadence, routing, transfer, and
  idle consumption. `SimulationEngine.step()` calls it once after the current
  environment update and before resolution-specific campaign/battle work at
  strategic, operational, and tactical resolution.
- Logical tick duration accumulates against the configured fixed interval.
  Every crossed boundary processes in chronological order; the exact remainder
  is retained. Boundary events use logical simulation time.
- Each boundary synchronizes linked unit-node/route geometry, semantically maps
  seasonal ground state, resets route flows, advances `SupplyNetworkEngine`,
  applies existing blockade effects, resupplies, then consumes.
- Seasonal enum integers are never cast across unrelated enums. Dry maps to
  dry, wet to wet, thawing/saturated to mud, snow-covered to snow, and frozen
  to ice.
- Resupply precedes consumption, preserving the intended existing campaign
  ordering. A profile with no reachable route still consumes; a connected
  stocked profile first receives bounded stock.
- Idle demand is exactly the profile quantity per hour multiplied by the
  unit's eligible logical time. No personnel/equipment fallback, hard-coded
  fuel rate, default item, or swallowed exception is permitted.
- Only registered active units that remained stationary across the interval
  and are not active-battle participants receive the Phase 108 idle rate.
  Moving and battle units are explicit controls until REM-020 defines activity
  demand.
- Reinforcements begin accounting at their logical registration time, so a
  boundary cannot charge them for time before arrival.
- Consumption mutates `StockpileManager` through a public API and therefore
  changes supply state, shortage/depletion events, snapshots, and
  `supply_exhausted` evaluation.
- Allocation, inventory, route state, cadence, and the typed event journal
  commit atomically per boundary. Journal observers run post-commit exactly
  once; every observer is attempted and failures propagate with context rather
  than being ignored or causing a committed boundary to replay.
- Enabled logistics consumes no RNG. Omitted/disabled logistics takes an O(1)
  engine gate and performs no graph or inventory traversal.
- `CampaignConfig.enable_supply_network=false` disables degradation/resupply
  while retaining configured consumption; this is the disconnected network
  control, not a whole-logistics switch.
- `supply_exhausted` honors its condition-local `params.threshold`, matching
  other parameterized victory conditions.

### Production trace and failing proof

`SimulationEngine.step() at any resolution -> environment -> LogisticsRuntime
logical boundary -> network update -> deterministic depot pull -> idle debit ->
StockpileManager -> supply state / victory / recorder / checkpoint`

At phase start, campaign supply update applies blockade penalties only and
never advances the network or transfers stock. Idle consumption computes with
fabricated defaults, discards its result, and catches every exception. Battle
code separately computes and discards combat demand for all context units.
Consequently a production tick cannot change inventory through either claimed
path, and tactical elapsed time never reaches campaign consumption.

The red proof must show absent debit, refill, route update, event, all-resolution
equivalence, deterministic ordering, and checkpoint continuation through a real
`ScenarioLoader -> SimulationEngine` run. Sub-interval, disabled, moving,
battle, and disconnected controls distinguish actual cadence behavior.

### Required outcome and persistence proof

- Equal elapsed time at strategic, operational, and tactical resolution yields
  equal inventory, route state, flow, and ordered logistics events.
- A connected/disconnected same-seed pair diverges only as intended: connected
  units remain supplied longer while disconnected units consume and can
  trigger real `supply_exhausted` victory.
- A checkpoint immediately before a boundary restores into a fresh runtime and
  continues with exact stock, maxima, routes, cadence, ordered events, supply
  states, outcome, and RNG state.
- Independent hash seeds produce identical canonical checkpoint bytes and
  greedy allocation/event order.
- Representative legacy depot scenarios remain semantically unchanged.

### Non-goals

- No march/combat demand, live fuel/ammunition synchronization, stochastic
  spoilage, or convoy advancement.
- No historical scenario tuning, force-composition change, weapon-performance
  change, or victory-threshold adjustment merely to force an outcome.

### Closure evidence

The engine now calls the injected logistics runtime once after environment
update and before resolution-specific work. Fixed cadence boundaries update
route state, apply deterministic bounded resupply, then debit exact eligible
idle demand. Strategic, operational, tactical, sub-interval, moving,
active-battle, disconnected-network, reinforcement-proration, condition,
throughput, event-failure, and checkpoint controls are behavioral tests.
Connected and disconnected production runs change real inventory, supply
state, events, and `supply_exhausted` outcomes as declared, while six legacy
scenario rows remain identical to their phase-start baselines. See the
[Phase 108 postmortem](devlog/phase-108.md#postmortem).

## REM-010 - Equipment mappings and runtime loadout ownership are unsafe

### Requirements

- One immutable typed registry owns weapon and sensor name resolution.
  Ordered mapping records reject duplicate category/name keys before an index
  is built; identical duplicate values are still errors.
- Each record is exact/variant, a constrained same-role functional analogue,
  or explicitly unsupported with a reason. Mapping presence alone is not
  semantic validity. Weapon records also distinguish live attachments from
  carried stores and non-runtime equipment.
- Supported targets exist in the effective catalog. Weapon category,
  guidance/ammunition/domain constraints, compatible ammunition, sensor type,
  and detection-domain constraints agree with the record.
- Noncombat equipment is categorized honestly rather than mapped to a weapon
  or surveillance proxy. An unsupported declared weapon/sensor fails
  production loading explicitly.
- Launcher/munition pairs create one launcher rather than two complete
  launchers with independent full magazines. Store records resolve compatible
  ammunition without constructing a second live attachment.
- Scenario `weapon_assignments` use the same target and semantic validation.
  Duplicate, stale, unknown, or conflicting assignments reject before runtime
  mutation.
- A typed runtime-owned builder is constructed once per effective scenario and
  used for initial units, reinforcements, and checkpoint reconstruction.
  Production no longer imports private validation-runner mapping/assignment
  helpers.
- Every unit gets exact keyed weapon/sensor output, stable ordering,
  independent live instances, and links to its own `EquipmentItem`. Missing
  mapping, target, ammunition, semantic agreement, or era permission raises
  with unit/equipment context instead of silently skipping.
- Construction consumes no RNG. Reinforcement and checkpoint failures remain
  atomic, and fresh restore continues with exact attachment identity, state,
  ordering, events, and RNG state.
- Resolve all 22 phase-start mapping-error occurrences. Classify both
  no-sensor units through a typed policy: the civilian remains explicitly
  sensorless, while the armed insurgent receives explicit visual observation.
- Full relevant data validation has no REM-010 error or unclassified warning,
  and repository-wide Python Ruff is green.

### Production trace and failing proof

`unit/scenario YAML -> ScenarioLoader -> validation-layer private mapping
helpers -> SimulationContext loadout maps -> battle/detection ->
checkpoint/recorder/API`

At the Phase 109 start, the production wrapper is typed as `Any` and calls
`ScenarioRunner._assign_weapons()`/`_assign_sensors()`. Those helpers silently
continue on missing mappings, missing target definitions, missing ammunition,
and missing sensors. Six duplicate dictionary literals overwrite earlier
values. In production this gives the B-52H CSRL rotary launcher a Stinger,
gives an EA-18G jamming pod a Vulcan with rifle ammunition, and lets an SA-6
load without its authored fire-control radar.

The static validator reports 22 mapping-error occurrences across 184 unit
files plus two no-sensor warnings, but it checks only source-name membership.
Its scenario load check uses aggregate armed/sensored counts, so a correctly
loaded peer hides an incomplete unit.

### Required proof

- Duplicate registry and scenario-assignment declarations reject before
  overwrite; wrong-category/domain, unknown-target, missing-ammunition, and
  unsupported controls reject atomically. Launcher-plus-store controls prove
  exact attachment and magazine topology.
- Exact per-unit production checks prove the corrected 22 occurrences and both
  sensor-policy decisions.
- A corrected sensor or weapon changes controlled production detection,
  firing/ammunition, event, or battle state; former jammer/structure/utility
  proxies cannot act as fake weapons or sensors.
- Initial, reinforcement, and fresh-restore paths use the same injected
  builder. Dynamic live fire and checkpoint continuation preserve exact
  objects, ordering, mutable state, event order, and RNG state.
- Representative affected scenarios are compared against pre-implementation
  rows with identical seeds; every outcome difference is explained.

### Phase 109 closure evidence

The Phase 109 implementation replaces the private validation-runner maps with
an ordered 442-record typed registry and one scenario-owned
`RuntimeLoadoutBuilder`. All 184 unit files and 51 scenario files now traverse
that production boundary. The final validator reports 442/442 authored keys
covered by 442 registry keys, zero unmapped or stale entries, zero errors,
zero warnings, and one explicitly sensorless classification. The formerly
sensorless insurgent has visual observation; the civilian remains explicitly
sensorless. Former jammer, navigation, engineering, flight-deck, and
munition-store proxies cannot create unrelated live attachments.

Strict duplicate-key loading covers scenarios, historical/campaign data, and
batch helpers. Initial units, reinforcements, and fresh restore use the same
builder; checkpoint schema 109 verifies its canonical fingerprint and ordered
per-unit resolution topology before mutation. Production detection, live
ammunition, events, API ammunition exposure, composite-system cadence, and
deterministic continuation tests provide outcome and persistence evidence.
Repository-wide Python Ruff, including `scripts/`, is green. The authoritative
commands, scenario rows, exclusions, and review findings are recorded in the
[Phase 109 devlog](devlog/phase-109.md).

### Non-goals

- No physical performance tuning, historical calibration, force-composition
  change, or unrelated scenario outcome adjustment.
- No new EW, mine-detection, breaching, navigation, carrier, or UAV-spotting
  mechanic.
- Aggregation reconstruction remains REM-016. Live Class III/V authority
  remains REM-020/021. Analysis and broader validation trust remain Phase 112.

The durable detailed contract is
[`docs/specs/equipment-mapping.md`](specs/equipment-mapping.md).

## REM-011 - ASAT is not integrated into the production runtime

### Reproduction and cause

The real `ScenarioLoader` does not load any file from
`data/space/constellations/` or `data/space/asat_weapons/`. It creates an empty
`ConstellationManager` and `ASATEngine`. The campaign tick subsequently calls
`_attempt_asat_engagements()`, which only logs that an ASAT engine exists.
There is no production caller of `ASATEngine.engage()`.

The advertised `space_asat_escalation` scenario has no `space_config` and its
test directly deactivates six satellites. The claimed GPS target is also
outside every authored weapon's altitude envelope. Component registration can
silently overwrite weapon ownership by definition ID, callers can fire an
opponent's weapon or attack a friendly satellite, rounds are infinite, and no
typed action state exists to checkpoint. Laser dazzle changes only an internal
dictionary that no production consumer reads.

### Requirements

- Replace the untyped space scenario block with strict explicit constellation,
  asset, and scheduled exact-target order declarations.
- Strictly load selected production catalogs and reject duplicate IDs, unknown
  or friendly references, unsupported weapon types, and impossible altitude
  envelopes.
- Distinguish immutable weapon definitions from unique mutable assets with
  owner, finite rounds, and per-asset cooldown.
- Execute due direct-ascent kinetic orders once in deterministic logical-time
  order, after orbit propagation and before same-tick downstream space
  consumers.
- Make `enable_asat` a real execution gate. A disabled control must leave the
  target, asset state, action state, and ASAT RNG draws unchanged.
- Route a hit through constellation-owned mutation and expose exact action,
  asset, side, target, outcome, inventory, and before/after constellation state
  through recorder/API events.
- Persist and validate catalog topology, satellite state, asset state,
  pending/completed actions, debris, and exact continuation.
- Validate every shipped constellation and ASAT weapon catalog file through
  the repository data validator.

### Required proof

A fixed-seed production `ScenarioLoader -> SimulationEngine` run must execute a
real catalog-backed order against a reachable enemy LEO satellite exactly once,
change its active/constellation state, consume finite asset state, and expose
the result. The same declared world and action plan with `enable_asat: false`
must preserve the target and consume no ASAT RNG. Strict negative controls,
same-seed replay, fresh checkpoint continuation, recorder/API exposure,
catalog-wide validation, scenario evaluation, and relevant regression suites
must also pass.

The durable contract is
[`docs/specs/asat-production-integration.md`](specs/asat-production-integration.md).

### Closure evidence

Phase 110 replaces the logging hook and direct-fire bypasses with
`ScenarioLoader -> SpaceEngine -> ASATEngine` scheduled execution. The loader
strictly validates all 9 constellation and 3 ASAT weapon files, resolves
selected definitions, and constructs unique side-owned assets with finite
rounds/cooldowns plus exact-target orders. The shipped seed-42/110/111
production runs execute the due Nudol order exactly once, change
`keyhole_optical_p0_s0` and its constellation from 4 to 3 active satellites,
consume the asset round, expose ordered degradation/engagement events, and
advance only the SPACE RNG stream. Identical disabled controls preserve
target, inventory, order, and RNG state.

Checkpoint schema 110 validates catalog and runtime topology, clock-aligned
satellite/service/ASAT state, order/result chronology, inventory, debris, and
RNG continuation before whole-context mutation. Fresh before/after-action
restore, hash-seed replay, recorder/API exposure, scenario evaluation, data
validation, and relevant legacy/default/API/E2E suites are recorded in the
[Phase 110 devlog](devlog/phase-110.md). The required postmortem accepted the
scope, quality, integration, validation, and explicitly tracked follow-ups;
REM-011 is closed.

### Non-goals and follow-up

Production supports direct-ascent kinetic actions only. Co-orbital,
laser-dazzle, and laser-destruct assets fail explicitly; there is no autonomous
target selection, tactical launcher/Class V ownership, historical calibration,
or high-fidelity breakup model. REM-027 tracks a lower-priority legacy Space
ISR buffered-report typing/rehydration gap independently of REM-011.

## REM-012 - Time-on-target has no production execution path

### Reproduction and cause

The Phase 27 component path accepted definitions rather than exact live
attachments, discarded real firing positions, substituted the ENU origin,
recomputed jittered firing times, silently skipped missing weapons, consumed no
ammunition, changed no target, and repeated due batteries on every call.
Neither the scenario schema nor `SimulationEngine.step()` supplied a production
caller, and indirect-fire checkpoint state contained only a shared RNG mirror.

### Requirements and required proof

- Declare strict target, common impact time, exact source-equipment attachment,
  weapon, ammunition, battery-specific time of flight, and rounds.
- Resolve the declarations only after production runtime loadouts exist; reject
  unknown, ambiguous, friendly, inactive, unsupported, out-of-range,
  physically impossible, overbooked, off-cadence, or cooldown-conflicting
  plans before context publication.
- Execute each aligned battery fire and common impact exactly once through the
  production loop, with explicit runtime rejection precedence and no RNG or
  resource mutation on rejection.
- Consume the authoritative live magazine, cooldown, and maintenance state;
  reserve every planned exact attachment from autonomous battle selection
  until its final using mission completes.
- Change the real target under a fixed-seed enabled control while the identical
  disabled control remains inert.
- Persist exact lifecycle, impacts, resource/precondition history, target
  transition, terminal result, and COMBAT RNG reconciliation atomically.
- Expose a typed complete terminal result through the recorder and real HTTP
  API, with same-seed replay and fresh checkpoint continuation.

### Closure evidence

Phase 111 replaces the three stateless helper APIs with
`CampaignScenarioConfig -> TimeOnTargetMissionResolver ->
IndirectFireEngine -> SimulationEngine.step()`. The shipped validation scenario
resolves two exact M109A6/M284/M982 attachments at real positions, fires at 60
and 65 seconds, processes one common 120-second impact, consumes one live round
and maintenance count from each attachment, records exact cooldown times, and
changes the real HEMTT from active to disabled. Disabled, empty, moved,
inactive, inoperable, depleted, cooldown, partial, missed, already-inactive,
extra-tick, observer-failure, and ordinary-fire controls establish the negative
and compatibility boundaries.

Checkpoint schema 111 validates plan topology, milestone chronology, exact
resource and target transitions, staged authority reconciliation, shared
attachment reservation, causally chained public live-resource bridges, and
atomic fresh restore before fire, after a reserved pre-fire mutation, between
fire and impact, during a shared-attachment plan, after completion, and for a
disabled populated plan. A legal public fire between scheduled fire and impact
survives exact continuation through release and fresh terminal restore. It
rejects invalid never-fired sentinel forms, boolean scalar aliases,
reload/counter/time contradictions, terminal-target regression, and a forged
three-round quantity-cooldown history. Same-tick follow-on fire is permanently
ordered before the earlier mission's impact/status/terminal events.
Recorder/API retrieval exposes the typed terminal battery results. The
complete command evidence, data counts, deterministic hashes, scenario
outcomes, warnings, and exclusions are recorded in the
[Phase 111 devlog](devlog/phase-111.md). The required postmortem accepted
Phase 111 with no new deficit or closure blocker; REM-012 is closed.

### Non-goals and follow-up

Authored whole-second time of flight is a fire-control input, not an automatic
firing-table solution or calibration. Rocket TOT, smoke/illumination effects,
forward-observer/C2 clearance, moving-target prediction, and a richer terminal
effects model remain unsupported. Ordinary indirect fire still does not own a
live Class V consumption path. Planned-attachment reload restore is rejected
until typed resupply provenance exists; live Class V synchronization remains
REM-021 rather than being claimed by REM-012.

## REM-013 - CI and local commands concealed excluded Python suites

### Phase 112 closure evidence

**Matrix:** `D=Yes, L=N/A, W=Yes, E=N/A, X=Yes, O=N/A, P=Yes`.

Phase 112 defines one locked-superset collection contract and divides its
node IDs into six explicit, pairwise-disjoint selections: standard,
slow-only, benchmark-only, slow-benchmark, API, and E2E. The exact-union audit
compares node IDs rather than trusting fixed counts. Terrain is separately
exercised as a dependency profile against its four owned files; it is no
longer represented by a zero-selecting marker.

The executable partition runner selects exact manifest node IDs and rejects an
empty selection, collection failure or timeout, operational timeout, skip,
missing outcome summary, or incomplete node accounting. Its timeout negative
controls retain the result, manifest, and selection without fabricating JUnit
counts that do not exist. Completed pytest executions also emit JUnit.
Module-affine deterministic sharding keeps a test module on one worker
whenever the number of modules permits it and reports any explicit fallback
split.

Pull-request and main workflows execute repository-wide Ruff, standard, API,
E2E, terrain, strict documentation, and paired 73 Easting gates.
Weekly/manual workflows own the sharded marker partitions, and the long Golan
pair remains an explicit manual gate. Artifact upload steps run after failure,
so a timeout cannot be presented as an omitted or successful suite. Fresh
local execution of the exact partitions, the terrain dependency profile, and
the runner's failure controls exercises this delivery contract; the exact
commands, counts, timeouts, warnings, and retained artifacts belong in the
Phase 112 devlog.

`L` and `E` are N/A because suite selection is delivery infrastructure, not
scenario data or a simulation feature gate. `O` is N/A because running the
complete validation contract does not itself change a simulation outcome.
`P` is Yes because the exact selection and result evidence is retained by the
local/CI artifact contract. The Phase 112 postmortem accepted this evidence
and the ranked row is closed.

## REM-014 - Structural tests supported behavioral completion claims

### Phase 112 closure evidence

**Matrix:** `D=Yes, L=N/A, W=Yes, E=N/A, X=Yes, O=Yes, P=N/A`.

Phase 112 adds a machine-checked current inventory for tests with no direct
oracle and for syntactic weak-oracle candidates. Every weak candidate has one
reviewed disposition: structural-only evidence is marked
`pytest.mark.structural`, while an excluded behavioral candidate records the
stronger observable oracle that makes the syntactic signal secondary. A
separate historical remediation ledger records the exact phase-start nodes
that were removed, honestly renamed, or repaired. New, stale, overlapping, or
unreviewed node IDs fail validation rather than being regenerated as an
automatic judgment.

The named high-risk phase-start tests were not accepted on imports, mocks,
logs, constructors, or no-crash execution. Their replacements observe real
effects at the applicable boundary: bounded API concurrency, terrain
coordinate agreement, C2 latency, delayed ISR delivery, armed air-posture
engagement, naval result/event publication, activated stratagem state,
temperature/fatigue and morale-mode behavior, campaign update state, and two
simultaneously advanced battles. The remaining structural clusters are
explicit diagnostics and cannot support a capability or phase-exit claim.
Truthful current-engine snapshots and legacy-runner regressions also replace
historical or semantic-equivalence labels that their oracles did not prove.

`L` and `E` are N/A because evidence classification is not loaded scenario
state or an optional runtime behavior. `O` is Yes because each repaired
behavioral node now fails when its named observable effect is absent. `P` is
N/A because this remediation governs repository evidence, not a simulation
checkpoint or public runtime result. The Phase 112 postmortem accepted this
evidence and the ranked row is closed.

## REM-027 - Space ISR buffered checkpoint reports are not typed

`SpaceISREngine` stores buffered reports as dictionaries containing a
`Position` tuple. The Phase 110 whole-space boundary safely normalizes generic
JSON, but it does not provide a typed report schema or reconstruct `Position`
on restore. An adversarial Taiwan Strait restore with an unknown-satellite,
future-timestamp report was inert and cleared on the next tick with identical
engine, SPACE RNG, and fog-of-war state, so it does not invalidate REM-011.
Nevertheless, future consumers should not depend on silent generic
normalization.

`E` is N/A because report typing and checkpoint rehydration are an always-on
state-integrity boundary, not an optional feature with enabled and disabled
modes.

Phase 112 must introduce a typed report state, reject malformed/unknown
references and impossible times, rehydrate positions explicitly, and prove
that a reachable buffered report produces identical fusion state across fresh
checkpoint continuation.

### Phase 112 closure evidence

**Matrix:** `D=Yes, L=Yes, W=Yes, E=N/A, X=Yes, O=Yes, P=Yes`.

Phase 112 replaces generic buffered dictionaries with strict
`SpaceISRReport`, `IntelDeliveryReceipt`, and `IMINTTrackAssociation` records.
The scenario selects exact IMINT-capable constellations, and the loader rejects
unknown, wrong-owner, wrong-target-side, unsupported-resolution, or
non-IMINT selections before context publication. Report generation validates
the real satellite and target topology, records an explicit `Position`,
observation/availability times, owner, target, source, and uncertainty, and
queues reports in canonical causal order.

A reachable catalog-backed optical pass now generates an owner-scoped delayed
report against a real runtime unit. Delivery changes that owner's fusion
track, receipt ledger, and association state only after the processing delay;
the other side remains unchanged. Lifecycle controls prove exact stale-track
reactivation and age-gated behavior. Batch preflight, report delivery, and
fusion commit failures reject atomically or preserve prior committed reports
with an exact retry, rather than dropping or double-delivering the failed
report.

Checkpoint schema 112 persists the typed queue, delivery receipts,
associations, fusion track, lifecycle state, and relevant SPACE/DETECTION
authority. Fresh restore before and after delivery continues byte-exactly.
Malformed references, ordering, times, positions, proxy mappings, cross-state
receipts, associations, and forged fusion state reject before mutation. The
proof deliberately keeps ordinary fog-of-war contacts empty because their
independent restore gap remains REM-029; aggregation remains bounded by
REM-016.

`E` is N/A because typed report integrity and rehydration are mandatory
whenever the configured Space ISR path is present, not an optional typing
mode. The Phase 112 postmortem accepted this evidence and the ranked row is
closed.

## REM-028 - Weapon standoff can exceed usable sensing range

### Reproduction and required proof

The corrected Cambrai Mark IV primary armament gives the production movement
boundary a 6,675 m modeled weapon range. At seed 42 the tanks hold at roughly
5,340 m even though the applicable visibility/sensing range is 3,000 m and no
tank detection, fire, or engagement event occurs. Phase 112 must classify the
actual `ENGINE_WEAPON_STANDOFF` branch accurately under REM-025, but that
diagnostic repair does not make the underlying blind standoff
outcome-affecting behavior valid.

A future phase must define whether tactical standoff requires a live
owner-side contact, sensor/visibility reach, fire-control solution, or another
typed targeting condition. It must prove enabled/disabled movement and combat
outcomes without extending a sensor, inventing a target, or silently reverting
to unrestricted catalog maximum range.

**Status:** Queued for Phase 115 in the planned next remediation block.

## REM-029 - Ordinary fog-of-war contacts are discarded on restore

### Reproduction and required proof

`FogOfWarManager.get_state()` serializes each `SideWorldView.contacts` entry,
but `set_state()` restores only last-update times and leaves every ordinary
contact absent. REM-027 can prove typed Space-report queue and
intelligence-fusion track continuation only with ordinary world views
explicitly empty; it cannot support a whole-fog-of-war continuation claim.

A future phase must stage and validate exact side ownership, contact IDs,
`ContactInfo`, nested track state, update times, topology, and DETECTION RNG
authority before mutation. A nonempty-contact fresh-runtime continuation must
preserve decay, update, common-operating-picture behavior, subsequent events,
and whole-context checkpoint equality.

**Status:** Queued for Phase 116 in the planned next remediation block.

## REM-030 - Catalog-wide historical outcome claims lack production validation

### Reproduction and required proof

The gap is catalog-wide, not limited to one scenario. Thirty-one shipped
scenario YAML files declare `documented_outcomes`. At the Phase 112 baseline,
`tests/validation/test_historical_accuracy.py` labeled 34 winner rows and eight
draw rows as historical accuracy, and called a winner frequency of at least
80 percent across ten seeds statistical validation. Phase 67 and Phase 91
tests imported or repeated those rows. Older Phase 7 validation tests used a
separate legacy `ScenarioRunner`; several proved only that a comparison object
existed, not that the declared tolerances passed. Metadata presence, a static
winner row, multiple seeds from the same calibrated inputs, and a legacy
runner are not production historical-validation evidence.

Debecka Pass is the concrete production red, not the limit of this issue.
Fresh Phase 112 production runs for seeds 42 through 51 won for blue in all ten
runs. The captured summary counted an average of 33.7 destroyed blue unit
records and 20 destroyed red unit records, but the declared casualty metrics
are explicitly measured in vehicles. That incompatible unit/extractor
boundary prevents an authoritative casualty verdict; treating the totals as
the legacy numeric comparison would also put them outside the stored blue
ceiling and red range. Runs terminated after an average of 191.8 five-second
ticks, about 959 seconds, while the declared duration range is about
10,286--20,160 seconds. Those seeds were not a predeclared held-out set, so the
result proves a current contract/mismatch red and a false public claim; it does
not constitute a replacement validation study. The same slow-suite audit also
found obsolete seed-42 winner/condition rows for 73 Easting, Bekaa Valley,
Trafalgar, Bint Jbeil, and Eastern Front 1943.

### Phase 112 truthful disposition

Phase 112 removed the blanket historical-accuracy oracle without manufacturing
a pass. The production evaluator now runs once for declared seed 42 and records
an exact 46-scenario current-engine terminal snapshot. Its module, class, and
test documentation explicitly state that a changed winner/condition row is a
regression-review signal, not historical validation. Phase 67 retains only its
catalog-lineage inventory and does not rerun the evaluator.

The Golan and Falklands campaign suites now share bounded production samples,
compare exact same-seed semantic state, and label documented-outcome handling
as metric projection rather than a passing historical verdict. Redundant
50-seed campaign loops and the Golan and Falklands legacy runners' count-only
1,000-run loops were removed; the remaining 73 Easting legacy convergence
check is explicitly not historical evidence. Public roadmap, model, scenario,
and historical devlog claims carry REM-030 supersession notices.

This truthful relabel/removal is a Phase 112 integrity repair, not REM-030
closure. No production, source-backed, predeclared held-out envelope or public
verdict artifact was added.

### Phase 113 current-engine regression signals

Phase 113's morale-ownership repair intentionally changed live morale timing,
status synchronization, cascade, and victory reads. Fresh production evidence
therefore adds four regression/fidelity signals to the Phase 117 inventory:

- Default 73 Easting at seed 42 terminates blue/`time_expired` after 360 ticks
  and 1,800 seconds with 18 blue `ACTIVE`, 3 blue `ROUTING`, and all 50 red
  units `ACTIVE`. It records 118 morale-state changes, two rallies, and one
  victory event. The explicit morale-neutral benchmark workload instead ends
  with all 21 blue units active while preserving the 50 active red units and
  the same terminal winner, condition, ticks, and logical duration. This is a
  controlled morale outcome effect and benchmark-control distinction, not a
  historical-fidelity verdict.
- The existing 20-seed Waterloo current-engine sweep shifts from the Phase 112
  baseline's 20 British wins to 18 British and 2 French wins. Repeatability
  does not establish that either distribution is historically predictive.
- Trafalgar seed 42 shifts from the Phase 112 revision's
  British/`time_expired` result at 5,760 ticks and 28,800 seconds, with 51
  `ACTIVE` and 2 `DISABLED` units, to a deterministic
  Franco-Spanish/`morale_collapsed` result at 372 ticks and 1,860 seconds, with
  44 `ACTIVE`, 2 `DISABLED`, 2 `ROUTING`, and 5 `SURRENDERED` units. Two fresh
  Phase 113 replays produced the same complete semantic digest.
- `calibration_arctic` seed 42 shifts from red/`force_destroyed` at 723 ticks
  and 7,230 seconds, with 5 `ACTIVE` and 3 `DESTROYED` units, to a deterministic
  blue/`force_destroyed` result at 468 ticks and 4,680 seconds, with 6 `ACTIVE`
  and 2 red `SURRENDERED` units. Two fresh Phase 113 replays again produced the
  same complete semantic digest.

These are exact current-engine regression observations caused by repairing an
integrity defect. They neither validate the outcomes against historical
sources nor authorize tuning to restore the previous snapshots. Phase 117
remains responsible for source-backed, provenance-bearing dispositions and
held-out outcome-envelope evidence.

Phase 117 must inventory every test, scenario field, and public statement that
claims historical accuracy and give each one an explicit disposition:

- production-validated against a typed, source-backed outcome envelope;
- current-engine regression only; or
- unsupported or not yet validated.

Closure does not require manufacturing a passing envelope for every scenario.
It requires removing the blanket claim, validating only those scenarios for
which defensible evidence exists, and labeling the rest honestly. Every
validated envelope must carry the scenario and input fingerprints, event
boundaries, exact metric extractor and units, source and source-quality
provenance, justified ranges or tolerances, calibration/training inputs
separate from predeclared held-out seeds, raw production vectors, and a
persisted verdict. Missing metrics and envelope misses must fail explicitly.
Winner-only agreement, same-data calibration, constructor or loader success,
and `len(report) > 0` are not completion evidence. Physical weapon performance
must not be tuned merely to force a historical pass.

### Evidence-matrix rationale

- `D` is **Yes** because typed `HistoricalMetric` and
  `HistoricalEngagement` metadata exist, although they do not yet provide the
  required production/provenance/held-out contract.
- `L` and `W` are unproven because documented outcomes are not loaded and
  evaluated at the authoritative `SimulationRuntimeFactory` boundary.
- `E` is **N/A** because historical conformity is not an optional feature
  switch. The relevant control is predeclared calibration/training evidence
  versus independent held-out validation.
- `X` and `O` are **Yes** only for the concrete production red and its
  observable mismatch, not for a passing catalog-wide validation claim.
- `P` remains unproven because no authoritative provenance-bearing verdict
  artifact is persisted or exposed.

**Status:** Queued for Phase 117. Phase 112 relabeled false tests as
current-engine regression and recorded the deficit, but did not close
REM-030.

## REM-031 - Performance flags lack semantic-integrity evidence

### Reproduction and required proof

Phase 91 planned to run every scenario with the Block 9 performance flags off
and on and compare winner, victory type, ticks, and casualties. At the Phase
112 baseline, `tests/validation/test_block9_regression.py` instead called
`evaluate_scenarios.py` with a seed and the scenario's authored configuration;
it supplied no paired variant or calibration override. The only scenarios
that authored all five current flags -- `enable_detection_culling`,
`enable_scan_scheduling`, `enable_lod`, `enable_soa`, and
`enable_parallel_detection` -- are `benchmark_battalion` and
`benchmark_brigade`, while evaluator discovery explicitly excludes
`benchmark_*`. Detection culling defaulted to enabled but also had no
same-input disabled control. The old test therefore proved neither
performance-flag preservation nor flag-caused historical accuracy.

The baseline slow tests compounded that semantic gap with an unbounded
execution shape. The Phase 67 and historical-accuracy Monte Carlo fixtures
each launched the full 46-scenario evaluator for ten seeds and then discarded
results outside their selected rows. One fresh Phase 112 evaluator artifact
recorded 751.04 seconds across the 46 scenarios; ten serial passes would have
required about 7,510 seconds before other partition nodes, beyond the declared
4,800-second job timeout. Running the entire evaluator twice to compare only
73 Easting winner and ticks was similarly a repeatability check for the
current authored configuration, not an enabled/disabled flag comparison.

### Phase 112 truthful disposition

Phase 112 removed the repeated full-evaluator fixtures and the unsupported
semantic-preservation/performance labels. The Phase 67 module now records only
its catalog lineage and proves that none of those ten scenarios authors the
four opt-in Block 9 flags. The Block 9 module now checks only the typed boolean
schema/default/rejection boundary and the exact catalog fact that
`benchmark_battalion` and `benchmark_brigade` author all four opt-in flags
while both are evaluator exclusions. It explicitly disclaims outcome
neutrality, historical accuracy, determinism, and benchmark validation.

The ordinary seed-42 evaluator snapshot is bounded current-engine regression,
not flag evidence. These truthful labels and bounded fixtures make the suite
operable without claiming that any of the five controls preserves semantics.
No common-seed disabled/enabled production pair, isolated flag effect, or
persisted semantic verdict was added; REM-031 therefore remains open.

Phase 118 must classify each flag before testing it as either a
semantics-preserving execution optimization or an explicit model-fidelity
approximation. It must then:

- run same-revision, same-data, same-config, common-seed off/on pairs through
  `SimulationRuntimeFactory` and prove that the intended branch executes;
- predeclare the terminal-state, event, detection/contact, RNG, and checkpoint
  semantics applicable to that flag rather than using winner agreement alone;
- require exact preservation only for flags whose declared contract is
  semantics-preserving;
- rename or document approximation controls as model controls and enforce a
  justified, predeclared paired semantic-error budget rather than promising
  blanket exact equivalence;
- prove deterministic repetition and fresh-checkpoint continuation on each
  side of the pair;
- store raw vectors, runtime/config/data/loadout/doctrine fingerprints,
  semantic digests, and the per-flag verdict in bounded, sharded artifacts; and
- keep performance timing evidence separate from semantic evidence and never
  recalibrate combat parameters to erase a flag delta.

### Evidence-matrix rationale

- `D`, `L`, and `W` are **Yes** because the five flags are typed
  `CalibrationSchema` fields, load into the effective calibration, and have
  production consumers.
- `E` is unproven because no same-input enabled/disabled production pair
  exists.
- `X` is unproven because the only all-flag scenario declarations are excluded
  from the cited evaluator and Phase 91 descoped their production Monte Carlo
  run to schema-level evidence.
- `O` is unproven because current output drift was not isolated to a flag.
- `P` is unproven because no paired semantic artifact or public verdict exists.
  No evidence cell is `N/A`: controls, realistic exercise, observable verdict,
  and persisted provenance are all required for this integrity claim.

**Status:** Queued for Phase 118. Phase 112 removed the false current labels,
but no documentation may describe the Block 9 flags as historically validated
or semantically equivalent until the required controlled evidence exists.

## REM-020 - March and combat logistics demand is not applied

### Reproduction and required proof

The campaign hook guesses march from `Unit.speed`, even though strategic
movement does not maintain that field. The battle hook computes combat demand
for all context units once per active battle, can skip it through LOD, uses
fabricated personnel/equipment/fuel defaults, emits an uncataloged
`ammo_generic`, discards the result, and swallows exceptions.

Replace this with one typed activity owner that charges each eligible unit once
per logical interval using catalog-backed demand and real battle/movement
participation. Multi-battle, LOD, resolution-transition, environment, and
checkpoint controls must prove no dropped or duplicated consumption.

## REM-021 - Abstract supplies and live fuel/ammunition have split authority

### Reproduction and required proof

`StockpileManager` Class III/V quantities feed abstract supply state and
victory, while movement fuel gates read entity fuel and engagement gates read
live weapon magazines. Delivery to one store does not replenish the other, and
API fuel/ammunition percentages expose only live stores.

Establish an explicit authority or conservative synchronization contract.
Consumption, delivery, firing, movement, checkpoint restore, recorder/API
exposure, and aggregation must not create or lose resources or report
contradictory readiness.

## REM-017 - Analysis tools can manufacture false-green results

### Reproduction

A one-iteration `run_sweep()` against
`data/scenarios/test_campaign/scenario.yaml` completed successfully while
logging that all ten scenario units were unknown. It returned zero destroyed
units for both sides instead of rejecting an invalid run.

### Cause

- The batch does not reject a scenario whose declared roster loads as zero
  units.
- `_extract_metrics()` returns `0.0` for unknown metrics.
- Existing sensitivity/comparison tests cover result structures and statistics,
  not real `run_sweep()`, `run_comparison()`, or production-loaded forces.

### Required proof

- Reject missing declared units, empty invalid runs, and unsupported metric
  names.
- Exercise sensitivity and comparison through real `ScenarioLoader` and
  `SimulationEngine` runs.
- Show that a controlled override changes an intended metric and that invalid
  configuration cannot produce an authoritative-looking zero result.

Until REM-017 closes, `$calibrate`, `$compare`, and `$what-if` must preflight a
real loaded roster and stop rather than report unverified results.

Phase 107 repaired the first independent defect: batch loading now derives the
data root from the `scenarios` ancestor and requires an explicit `data_dir` for
other layouts. The complete 200-test API suite covers that compatibility
repair. At the Phase 112 baseline, empty-roster rejection, metric validation,
and real outcome-changing sweep/comparison proof remained open.

### Phase 112 closure evidence

**Matrix:** `D=Yes, L=Yes, W=Yes, E=N/A, X=Yes, O=Yes, P=Yes`.

Phase 112 establishes `SimulationRuntimeFactory -> PreparedScenario ->
RuntimeSession` as the authoritative construction boundary for analysis,
campaign validation, API run management, MCP, and benchmarks.
`AnalysisRunner` validates an exact nonempty metric list, strict iteration and
seed values, finite typed variants, exact side IDs, and authored-versus-loaded
roster cardinality before returning an authoritative batch. Each seed and
variant receives a fresh production session. Unknown metrics, dead/unknown
calibration keys, missing definitions, empty or changed rosters, partial
vectors, nonfinite values, incomplete runs, and changed code/data identity
reject instead of becoming zero.

A supported calibration sweep changes a metric derived from completed
production runs. Same-seed A/B and doctrine variants expose complete raw
vectors and public terminal records; comparison uses paired differences,
positive/negative/tied counts, the exact sign test, Holm-adjusted family
significance, and explicit superiority. Doctrine assignments take effect
before initial and reinforcement registration and change exercised OODA or
decision behavior. Python, MCP, FastAPI, and frontend consumers use the same
typed payload rather than recomputing statistics from a second runner.

Every result carries source/effective-configuration, code, data, catalog,
loadout, doctrine, roster, seed, metric, and terminal-run provenance. Durable
API batch storage retains raw vectors, statistics, and provenance across a
database reopen. An iteration-two failure or accepted cancellation publishes
no partial metrics, raw vectors, terrain/frame result, or false completed
state. `E` is N/A because strict analysis integrity is mandatory for every
accepted request; controlled variants are outcome controls, not an
enable/disable switch for validation. The Phase 112 postmortem accepted this
evidence and the ranked row is closed.

## REM-022 - Historical devlog fragment links do not resolve

### Reproduction and required proof

The Phase 108 strict MkDocs build exits successfully but reports missing
fragment targets from `docs/devlog/index.md` into phases 58, 59, 60, 61, 62,
64, and 66. The build's success therefore proves site generation, not complete
historical fragment navigation.

Phase 112 must repair each target or update the index to the heading that
actually owns the limitation, then run a link-resolution check that fails on a
missing fragment. Pages intentionally omitted from the navigation tree are not
part of this item.

### Phase 112 closure evidence

**Matrix:** `D=Yes, L=N/A, W=Yes, E=N/A, X=Yes, O=N/A, P=N/A`.

Phase 112 repairs all 49 affected links across the seven malformed historical
fragment targets and enables MkDocs anchor validation under the repository's
strict build. A real full-site build resolves the corrected fragments with
zero broken-fragment diagnostics. An isolated documentation validator also
proves the failure path: a generated missing-fragment target fails while the
corresponding valid-fragment control passes. This distinguishes link
resolution from mere successful page generation.

`L` is N/A because documentation links are not loaded simulation input. `E` is
N/A because current-link validity has no supported disabled mode. `O` and `P`
are N/A because this item governs navigable documentation, not simulation
outcomes or runtime state. The Phase 112 postmortem accepted this evidence and
the ranked row is closed.

## REM-023 - Missing commander profiles do not fail scenario validation

### Reproduction and required proof

`suwalki_gap` declares side-default profiles `joint_commander` and
`conventional_commander`, but neither ID exists under
`data/commander_profiles`. `ScenarioLoader` catches each failed assignment and
logs a warning for every affected unit; the production evaluator still reports
the scenario as OK with no issue code.

Phase 112 must validate commander profile references before runtime mutation,
correct the scenario to catalog-backed profiles or add independently justified
definitions, and make a missing reference a validator/evaluator failure rather
than a warning-only success. Negative and corrected production-load controls
must prove the boundary.

### Phase 112 closure evidence

**Matrix:** `D=Yes, L=Yes, W=Yes, E=N/A, X=Yes, O=Yes, P=N/A`.

`SideConfig.commander_profile` is now the canonical side-default reference,
with one strict typed tuning/assignment model for per-unit exceptions.
Production loading merges the global and applicable era profile catalogs with
duplicate rejection, validates every side and exact initial/future unit
assignment before construction, and rejects partial profile declarations,
feature-shaped empty configuration, unknown schools, and malformed tuning.
All 74 shipped commander references resolve.

The six unresolved side references now select existing catalog roles:
Khafji/Debecka red use `aggressive_armor`; Fallujah/Bint Jbeil red and INS
Hanit red use `insurgent_leader`; INS Hanit blue uses `naval_surface`.
Suwalki Gap and Korean Peninsula remove the stale second side-default
authority. Corrected production scenarios assign every initial and arriving
unit. Unknown/duplicate/whitespace references reject before unit or RNG
mutation; a failed dynamic assignment rolls back and retries exactly.

An exact-profile control changes production OODA duration and recorded decision
state relative to the same scenario with another profile, so assignment is
behavioral rather than constructor evidence. Fresh checkpoint continuation
preserves commander, school, decision, and C2 RNG state, with explicit
unsupported rejection for aggregation-owned proxy IDs under REM-016. `E` is
N/A because reference validity is mandatory, not an optional validation mode.
`P` is N/A for this missing-reference remediation; the checkpoint proof
supports continuation but no new public exposure is required to reject invalid
scenario data. The Phase 112 postmortem accepted this evidence and the ranked
row is closed.

## REM-024 - Invalid crew skill silently drops historical units

### Reproduction and required proof

The Phase 109 era validation exposed a separate false-green path in the
historical scenario force builder. French Old Guard data declares crew skill
`EXPERT`, which is not a runtime `CrewSkill` member. `UnitLoader.create_unit()`
therefore raises `KeyError`, but `build_forces()` catches that broad exception
as though the unit definition were merely absent. Austerlitz requests ten
French units and constructs nine; Waterloo requests eleven and constructs ten,
while scenario evaluation can continue without identifying the dropped unit.

Phase 112 must validate crew-skill enum values while loading unit definitions,
narrow missing-definition handling so construction and enum errors propagate,
correct or independently extend the affected data contract, and make roster
cardinality part of scenario validation. Negative unit-load and corrected
production-scenario controls must prove that an invalid crew skill cannot
silently reduce a force.

### Phase 112 closure evidence

**Matrix:** `D=Yes, L=Yes, W=Yes, E=N/A, X=Yes, O=Yes, P=N/A`.

`UnitLoader` now validates crew role/skill, domain, equipment category, and
domain-specific subtype enums eagerly. Only a dedicated missing-definition
exception represents an absent unit; constructor, enum, equipment, and
override failures retain their context and propagate. One strict
`InitialUnitConfig`/`UnitInstanceOverrides` schema and the simulation-owned
`RuntimeForceBuilder` preflight every definition, count, position, override,
subtype, and deterministic unit ID before the first ENTITIES RNG draw, then
require exact per-side and total cardinality before publication.

The French Old Guard's unsupported `EXPERT` value is corrected to the existing
`ELITE` proficiency. Production Austerlitz and Waterloo runs construct the
authored 10/9 and 11/9 side rosters, retain the exact Old Guard unit and elite
crew, reach their declared current terminal results, and preserve the complete
roster. Catalog-wide data validation also applies every shipped typed override
through the runtime boundary. Invalid enum, incompatible override, malformed
specification, and constructor controls reject before RNG or partial roster
mutation.

`E` is N/A because valid typed unit data and exact roster construction are
mandatory. `P` is N/A because the item closes an eager load/construction
false-green rather than adding a new public or checkpoint field. The Phase 112
postmortem accepted this evidence and the ranked row is closed.

## REM-025 - Corrected standoff is reported as stuck movement

### Reproduction and required proof

Phase 109 corrected the Cambrai Mark IV's primary armament from an unrelated
800 m Lewis-gun proxy to its exact 6-pounder definition with a 6,675 m modeled
range. At seed 42 the production evaluator then reports
`MANY_STUCK_UNITS(4/7)`, even though the affected units have moved and are
holding a valid weapon-range standoff rather than failing movement.

Phase 112 must distinguish true no-progress movement defects from intentional
standoff, objective holding, destroyed/disabled state, and other legitimate
tactical behavior. A corrected Cambrai control must retain its semantic
outcome without the false diagnostic, while a deliberately immobile,
out-of-position unit still raises an issue.

### Phase 112 closure evidence

**Matrix:** `D=Yes, L=N/A, W=Yes, E=N/A, X=Yes, O=Yes, P=N/A`.

One simulation-owned `MovementDiagnostics` component now receives exact
strategic, operational, and tactical movement decisions. Typed observations
record unit/side, logical tick, stage and deterministic ordinal, attempted and
achieved distance, pre/post positions, and the production reason. Bounded
recent history is separate from cumulative counters, and registration/batch
commit is canonical, transactional, and side-bound. A production manager must
record every considered unit exactly once; a fault-injected claimed commit
without displacement is rejected rather than presented as ordinary movement.

The evaluator consumes these dispositions instead of inferring intent from
raw whole-run displacement. Cambrai retains its seed-42 British
`force_destroyed` outcome, 433 ticks, casualties and engagement/event
semantics while each unmoved Mark IV is reported as
`ENGINE_WEAPON_STANDOFF`, not `MANY_STUCK_UNITS`. Explicit fuel-blocked and
zero-commit controls remain real semantic deficits. Reinforcement controls use
all 13 constructed units as the denominator and preserve each construction
position.

Schema 112 validates and continues bounded movement history and cumulative
state exactly across fresh restore. `L` is N/A because diagnostics are a
runtime-owned observer rather than scenario-loaded configuration. `E` is N/A
because truthful classification is always on when movement runs. `O` is Yes
because the public evaluator disposition changes from a false stuck issue to
the exact production reason without changing battle behavior. `P` is N/A for
the REM-025 diagnostic correction; REM-028 separately owns the
outcome-affecting blind-standoff behavior. The Phase 112 postmortem accepted
this evidence and the ranked row is closed.

## REM-026 - Benchmark wall-clock assertion contradicts its baseline

### Reproduction and required proof

The Phase 109 slow-suite audit measured the current Golan workload at
140.744792 seconds on the same machine where the phase-start revision took
214.77246345 seconds. The test nevertheless fails a hard 60-second assertion,
while the checked-in benchmark baseline permits 500 seconds. This makes a
material speedup fail and does not provide portable regression evidence.

Phase 112 must establish one reproducible benchmark contract with declared
hardware/environment metadata, warm-up and repetition policy, semantic outcome
checks, and a threshold derived from an authoritative baseline or a
hardware-normalized comparison. The hard assertion and stored baseline may
not disagree.

### Phase 112 closure evidence

**Matrix:** `D=Yes, L=N/A, W=Yes, E=N/A, X=Yes, O=Yes, P=Yes`.

The version-2 benchmark policy removes every absolute wall-clock pass
threshold. Gating workloads declare an exact reference commit and runtime
input identity, one warm-up per revision, three alternating same-host timed
pairs, a maximum 1.20 median slowdown ratio, a maximum 0.20 relative sample
range, and a complete semantic envelope. 73 Easting is the routine gate;
Golan Heights is an explicit long-running manual gate. Unbaselined battalion,
brigade, and flag-impact workloads are labeled measurement-only and cannot
authorize a regression verdict.

The harness executes the actual reference revision through its bounded
historical adapter and the candidate through `SimulationRuntimeFactory`; it
does not import candidate runtime code as the reference. Each worker verifies
revision ownership, scenario/dependency identity, roster/loadout topology,
winner, victory type, logical duration, ticks, status counts, event count, and
event digest before timing can pass. Missing reference data, dirty or changed
runtime inputs, noisy samples, semantic drift, worker failure, and an
unverifiable final revision fail closed.

The paired artifact retains hardware/environment metadata, alternating order,
all raw samples, medians/ranges/ratio, semantic and input identities, dirty
state, policy verdict, and an integrity digest. Measurement tests retain only
positive raw timing plus exact terminal semantics; the contradictory
60-second Golan assertion and legacy 500-second absolute baseline no longer
decide acceptance. `L` and `E` are N/A because the benchmark policy is
external validation infrastructure, not scenario-loaded or enabled simulation
behavior. The Phase 112 postmortem accepted this evidence and the ranked row
is closed.

### Phase 113 version-3 extension

Phase 113 extends, but does not rewrite or reopen, the accepted Phase 112
version-2 closure. Policy version 3 adds a typed `BenchmarkWorkload` to the
stored baseline and paired artifact, so reference and candidate workers must
load the same explicit workload as well as the same scenario and source/data
identity. The routine 73 Easting gate now declares a morale-neutral typed
control-plane calibration patch. A production comparison proves that this
override is actually loaded and outcome-affecting: the default workload ends
with three blue units routing, while the neutral control ends with all 21 blue
units active.

That control isolates Phase 113's runtime overhead from its intentional morale
semantic change; it is not evidence that default morale behavior is neutral or
historically accurate. The earlier CPU-30-pinned pre-final artifact was
superseded after simplify changed the runtime tree. The final dirty-tree
capture passed the unchanged 1.20 slowdown and 0.20 sample-range gates with
ratios 1.101958711, 1.099634464, and 1.099029460; median 1.099634464;
candidate range 0.010757612; and reference range 0.008635696 while matching the
complete declared terminal envelope. Its artifact-declared SHA-256 is
`817a9dec5ca2984e87e70e42d941b9d16297836cf9fd9fded79f6660ad7d870e`
and its raw file SHA-256 is
`cac10f3a045ca2cf3f025ae9f18579c579ee360928d93ce114808a8725a52a03`.
The command used `--allow-dirty-candidate`; final clean committed-tree
verification binds that comparison to the final Phase 113 commit as recorded
in the Phase 113 devlog and external handoff. This extends the evidence bridge;
it does not reopen REM-026.

## REM-018 - Era override metadata has no production consumer

### Reproduction and cause

`ScenarioLoader` exposes the selected `EraConfig`, but neither
`physics_overrides` nor `tick_resolution_overrides` is applied while building
the clock or domain engines. Current public era documentation historically
described C2 delays and tick changes as effective behavior even though only the
seven Phase 107 capability gates and sensor allowlist are enforced.

### Required proof

- Replace arbitrary override dictionaries with explicit supported keys and
  typed value constraints, or reject unsupported keys.
- Apply each supported override at the single production construction boundary.
- Prove an enabled value changes the intended clock or engine behavior and that
  omission preserves the baseline.
- Persist and compare the effective override contract during checkpoint restore.

## REM-019 - Morale has two independently mutable stores

### Reproduction and cause

Phase 107 initializes `SimulationContext.morale_states` and
`MoraleStateMachine` consistently, but later code can write either store
independently. In particular, rout-cascade and aggregation paths update the
context mapping without updating the machine's internal `UnitMoraleState`.
Subsequent machine transitions can therefore start from a stale state.

### Required proof

- Establish one authoritative owner for current morale and route all reads,
  transitions, rout cascades, aggregation, and dynamic registration through it.
- Keep unit status synchronization explicit for routed and surrendered states.
- Prove transition, cascade, aggregation/disaggregation, and checkpoint
  continuation cannot produce divergent morale views.

`E` is N/A because authoritative morale ownership is mandatory whenever a
production runtime has registered units; there is no supported enabled/disabled
feature gate under which divergent ownership would be acceptable.

### Phase 113 closure evidence

The accepted implementation introduces one `MoraleRuntime` over a private
immutable-record store. The production loader registers initial and dynamic
units through it; battle, rally, melee rout, ordered cascade batches,
aggregation archives, victory evaluation, recorder/API projections, and
campaign final-state serialization read or mutate only its stable read-only
projection. Format 113 checkpoints persist the active records and suspended
archives once, with `RNGManager` as the only MORALE-stream persistence owner;
bounded versionless migration rejects ambiguous started continuous-time state
instead of guessing its missing check history.

Focused evidence exercises exact transition/status/event transactions,
pre-notification rollback and draw restoration, deterministic cascade order,
reinforcement rollback, aggregation suspension and unchanged-proxy restore,
evolved-proxy rejection, fresh and in-place checkpoint continuation, and a
production `morale_collapsed` victory difference. Positive guerrilla blending
now fails explicitly before retreat, status, morale, events, or COMBAT/MORALE
RNG mutation rather than being misrepresented as `ROUTING`; REM-032 retains
the unsupported concealment lifecycle.

The exact 11,824-node broad union passed with zero failures/errors/skips and six
declared warnings. Local API/E2E plus one FastMCP standard node use the declared
uvloop qualification, with hosted CI as the authoritative default-policy
control. The corrected documentation audit and Phase 113 postmortem passed.
The clean committed-tree verifier binds the accepted paired comparison to the
final phase commit using exact runtime-manifest, input, semantic-envelope, and
fresh-reproduction equality; its external evidence is recorded in the Phase
113 devlog and handoff. REM-019 is **Closed**.

## REM-032 - Guerrilla blending has no semantic runtime owner

### Reproduction and cause

Phase 68 described populated-area guerrilla blending as optional live routing,
but the production branch used a COMBAT-stream draw to write
`UnitStatus.ROUTING` without a corresponding morale transition. That proxy
conflates concealment/disappearance into a population with morale collapse and
violates REM-019's status/state invariant. The branch also queries the absent
`SimulationContext.population_engine` name while the loader exposes a
`population_manager` whose API does not provide the assumed density lookup.
The prior tests proved only enum existence and a zero-probability condition;
they did not execute a production-loaded blend outcome.

Phase 113 removes the invalid proxy. A direct positive blend result fails
explicitly before retreat, status, morale, events, or either affected RNG
stream can mutate; a zero result retains deterministic retreat behavior. This
is an honest unsupported boundary, not completion of concealment behavior.

### Required proof

- Define one typed, non-morale concealed/disengaged state owner and its
  lifecycle, including re-emergence or terminal disposition.
- Resolve populated-area membership through the production-loaded population
  boundary instead of an absent context attribute or a fabricated density.
- Apply concealment to detection, targetability, active-enemy selection,
  movement, victory/roster accounting, and events without inventing a morale
  route.
- Prove enabled/disabled and success/failure controls through a realistic
  production scenario, with deterministic stream allocation and exact
  checkpoint continuation plus recorder/API exposure.

**Status:** Queued for Phase 119. Phase 113 removes the false morale proxy but
does not implement or close the concealment capability.

## REM-033 - Surrender and POW handling have no production transaction

### Reproduction and cause

The Phase 113 final ownership audit reproduced a public semantic bypass in
`RoutEngine.process_surrender()`. A direct call consumed the shared MORALE
stream, removed an active route, published `SurrenderEvent`, and returned a
synthetic prisoner count while the authoritative `MoraleRuntime` record stayed
`ROUTED` and the bound unit stayed `ROUTING`. No production caller invokes that
helper, no production boundary supplies capturing-unit/side provenance, and no
simulation runtime constructs or subscribes a `PrisonerEngine` to the morale
event. The documented combat-to-logistics event path therefore did not exist.

Phase 113 removes the divergent result type and makes the legacy helper reject
before RNG, route, event, record, or status mutation. Normal stochastic
`ROUTED -> SURRENDERED` transitions remain production-supported through
`MoraleRuntime`: the immutable record and `Unit.status` commit together, an
existing route is removed, and the caused morale event is exposed. That state
transition does not fabricate a captor, prisoner count, or logistics handoff.

### Required proof

- Define one typed surrender transaction with exact surrendering unit,
  capturing unit/side provenance, personnel disposition, escape semantics, and
  event ordering; do not infer a captor from an arbitrary opposing side.
- Wire the transaction through the production battle/campaign decision path
  and one runtime-owned prisoner lifecycle rather than independent morale and
  logistics mutations.
- Prove realistic enabled preconditions plus no-captor, inactive-unit,
  duplicate-processing, and subscriber/commit-failure controls with exact RNG
  accounting and rollback semantics.
- Persist and expose surrendered personnel, prisoner groups, captor ownership,
  resource costs, transfers/releases, and their recorder/API representation
  through exact fresh and in-place continuation.

`E` is N/A because surrender integrity is not a feature-flag toggle: every
accepted surrender must use the authoritative transaction.

**Status:** Queued for Phase 120. Phase 113 closes the divergent public bypass
but does not claim production POW generation or logistics handling.

## REM-034 - Production combat events use sentinel timestamps

### Reproduction and cause

The final Phase 113 adversarial postmortem corrected an earlier review
classification. `RoutEngine.initiate_rout()` has no production caller, but the
separately noted aggregate casualty helper is production reached from the
Napoleonic volley, ancient archery, and WW1 volley branches in
`BattleManager._execute_engagements()`. When an aggregate casualty is positive,
the helper publishes `EngagementEvent` and `DamageEvent` with
`timestamp=datetime.min` because its boundary accepts no authoritative
timestamp. `BattleManager.auto_resolve()` likewise publishes
`UnitDestroyedEvent` with `datetime.min`, and `SimulationEngine` calls that path
for live battle resolution.

These events flow through the ordinary event bus and can be persisted by the
recorder and exposed by API/timeline consumers. A sentinel source timestamp is
therefore a production event-integrity deficit, not a non-production caveat or
valid completion witness. Phase 113 did not introduce or depend on these
paths; its melee-event repair supplies exact logical time and remains valid.

### Required proof

- Add one required typed authoritative timestamp to aggregate casualty and
  auto-resolve production boundaries; do not use wall-clock time or a sentinel
  fallback.
- Thread `SimulationContext.clock.current_time` from every production caller
  and reject an absent, naive, or non-authoritative value before publishing or
  mutating an exposed result.
- Execute production-loaded aggregate-volley and auto-resolve controls and
  prove every engagement, damage, destruction, recorder, API, and timeline
  timestamp equals the triggering logical simulation time.
- Prove deterministic replay and checkpoint continuation preserve the exact
  event order and timestamps without adding an RNG or clock mirror.

`E` is N/A because correct event time is mandatory whenever either production
path emits an event; there is no supported enabled/disabled correctness mode.

**Status:** Queued for Phase 121. Phase 113 records the production reachability
and corrects its documentation but does not broaden REM-019 into a combat-event
timestamp implementation.
