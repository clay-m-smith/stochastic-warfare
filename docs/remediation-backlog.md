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
| REM-012 | P1 | 111 | Indirect fire | Time-on-target uses dummy coordinates, has no executed state, and has no production caller | Queued | Yes | Yes | - | - | - | - | - | Scheduled mission executes once at its real target |
| REM-013 | P1 | 112 | Validation trust | Default CI hides excluded suites; Phase 109 established a green full Python Ruff baseline, but CI does not yet enforce the complete suite contract | Queued | Yes | N/A | Yes | N/A | - | N/A | N/A | Explicit CI suites and documented/enforced boundaries |
| REM-014 | P1 | 112 | Test quality | Structural and no-assert tests can support false completion claims | Queued | Yes | N/A | Yes | N/A | - | - | N/A | Audit critical contracts and add behavioral assertions |
| REM-015 | P2 | 112 | Documentation | Strict documentation build was not part of the verified baseline | **Closed early** | Yes | N/A | Yes | N/A | Yes | N/A | N/A | [Phase 105 verification](devlog/phase-105.md#final-broader-verification) |
| REM-016 | P1 | TBD | Aggregation | Disaggregation recreates every constituent as base `Unit` and does not restore captured weapon, sensor, or supply attachments | Queued | Yes | Yes | Yes | N/A | - | - | - | Subclass/loadout round trip across aggregation |
| REM-017 | P0 | 112 | Analysis tooling | Scenario batches can accept empty invalid rosters and silently turn unsupported metrics into zero | Queued | Yes | Yes | Yes | N/A | Yes | Yes | N/A | Real-unit batch run, unknown-metric rejection, and outcome-affecting sweep/comparison |
| REM-018 | P1 | 114 | Era overrides | `physics_overrides` and `tick_resolution_overrides` are declared and documented but have no production consumer | Queued | Yes | Yes | - | N/A | - | - | Yes | Typed override changes its production engine/clock behavior |
| REM-019 | P1 | 113 | Morale state | `SimulationContext.morale_states` and `MoraleStateMachine` are independently mutable and can diverge after rout or aggregation paths | Queued | Yes | Yes | Yes | N/A | - | - | Yes | One authoritative state survives transition, cascade, aggregation, and checkpoint |
| REM-020 | P1 | TBD | Logistics | March/combat consumption is computed with fabricated defaults and discarded | Queued | Yes | Yes | - | - | - | - | - | Typed activity demand changes real inventory once per logical interval |
| REM-021 | P1 | TBD | Logistics | Abstract Class III/V inventory is independent of live entity fuel and weapon magazines | Queued | Yes | Yes | - | - | - | - | Yes | One explicit authority or conservative synchronization contract |
| REM-022 | P2 | 112 | Documentation navigation | Strict MkDocs succeeds while seven historical devlog-index fragment links target missing anchors | Queued | Yes | N/A | Yes | N/A | Yes | N/A | N/A | Repair fragment targets and verify link resolution |
| REM-023 | P1 | 112 | Scenario data trust | Missing commander profile references warn once per unit while scenario evaluation still reports OK | Queued | Yes | Yes | Yes | N/A | Yes | - | N/A | Strict profile-reference validation and corrected scenario data |
| REM-024 | P1 | 112 | Unit data trust | Invalid crew-skill enums are hidden by a broad `KeyError` catch and silently drop historical units | Queued | Yes | Yes | Yes | N/A | Yes | Yes | N/A | Eager enum validation and narrow missing-definition handling |
| REM-025 | P2 | 112 | Scenario diagnostics | `MANY_STUCK_UNITS` treats legitimate corrected weapon-range standoff as a movement failure | Queued | Yes | N/A | Yes | N/A | Yes | Yes | N/A | Semantic stuck-unit diagnostic with a Cambrai control |
| REM-026 | P1 | 112 | Benchmark trust | A hard 60-second Golan assertion contradicts the checked-in 500-second baseline and fails code that is faster than that baseline | Queued | Yes | N/A | Yes | N/A | Yes | Yes | Yes | Hardware-aware threshold and reproducible before/after benchmark |
| REM-027 | P2 | 112 | Space ISR state | Buffered ISR checkpoint reports use generic JSON normalization rather than a typed semantic rehydration boundary | Queued | - | Yes | Yes | N/A | Yes | - | - | Typed report round trip and malformed-report rejection through production fusion |

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
repair. REM-017 remains open because empty-roster rejection, metric validation,
and real outcome-changing sweep/comparison proof still belong to Phase 112.

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
