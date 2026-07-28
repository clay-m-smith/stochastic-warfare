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
| REM-008 | P0 | 108 | Logistics | Scenario depots do not initialize stock or a supply network | Queued | Yes | Yes | - | N/A | - | - | - | Depot-backed resupply through production loop |
| REM-009 | P0 | 108 | Logistics | Supply-network updates and idle consumption are not applied by the production loop | Queued | Yes | Yes | - | N/A | - | - | - | Controlled inventory delta over engine ticks |
| REM-010 | P0 | 109 | Equipment data | Loadout mapping has duplicate/wrong keys, 22 unmapped catalog entries, and validation-layer ownership | Queued | Yes | Yes | Yes | N/A | - | - | - | Central typed mapping, clean data validation, and Ruff |
| REM-011 | P1 | 110 | Space combat | The production ASAT hook is an explicit placeholder | Queued | Yes | Yes | - | - | - | - | - | Enabled/disabled satellite outcome test |
| REM-012 | P1 | 111 | Indirect fire | Time-on-target uses dummy coordinates, has no executed state, and has no production caller | Queued | Yes | Yes | - | - | - | - | - | Scheduled mission executes once at its real target |
| REM-013 | P1 | 112 | Validation trust | Default CI hides excluded suites and does not maintain a green repository-wide lint baseline | Queued | Yes | N/A | Yes | N/A | - | N/A | N/A | Explicit CI suites, clean lint, and documented boundaries |
| REM-014 | P1 | 112 | Test quality | Structural and no-assert tests can support false completion claims | Queued | Yes | N/A | Yes | N/A | - | - | N/A | Audit critical contracts and add behavioral assertions |
| REM-015 | P2 | 112 | Documentation | Strict documentation build was not part of the verified baseline | **Closed early** | Yes | N/A | Yes | N/A | Yes | N/A | N/A | [Phase 105 verification](devlog/phase-105.md#final-broader-verification) |
| REM-016 | P1 | TBD | Aggregation | Disaggregation recreates every constituent as base `Unit` and does not restore captured weapon, sensor, or supply attachments | Queued | Yes | Yes | Yes | N/A | - | - | - | Subclass/loadout round trip across aggregation |
| REM-017 | P0 | 112 | Analysis tooling | Scenario batches can accept empty invalid rosters and silently turn unsupported metrics into zero | Queued | Yes | Yes | Yes | N/A | Yes | Yes | N/A | Real-unit batch run, unknown-metric rejection, and outcome-affecting sweep/comparison |
| REM-018 | P1 | 114 | Era overrides | `physics_overrides` and `tick_resolution_overrides` are declared and documented but have no production consumer | Queued | Yes | Yes | - | N/A | - | - | Yes | Typed override changes its production engine/clock behavior |
| REM-019 | P1 | 113 | Morale state | `SimulationContext.morale_states` and `MoraleStateMachine` are independently mutable and can diverge after rout or aggregation paths | Queued | Yes | Yes | Yes | N/A | - | - | Yes | One authoritative state survives transition, cascade, aggregation, and checkpoint |

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
