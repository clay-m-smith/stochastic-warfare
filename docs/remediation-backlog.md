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
| REM-018 | P1 | 114 | Era overrides | `physics_overrides` and `tick_resolution_overrides` were persisted without a production consumer at the audit baseline | **Closed** | Yes | Yes | Yes | Yes | Yes | Yes | Yes | [Phase 114](devlog/phase-114.md#postmortem) |
| REM-019 | P1 | 113 | Morale state | `SimulationContext.morale_states` and `MoraleStateMachine` are independently mutable and can diverge after rout or aggregation paths | **Closed** | Yes | Yes | Yes | N/A | Yes | Yes | Yes | [Phase 113](devlog/phase-113.md#postmortem) |
| REM-020 | P1 | TBD | Logistics | March/combat consumption is computed with fabricated defaults and discarded | Queued | Yes | Yes | - | - | - | - | - | Typed activity demand changes real inventory once per logical interval |
| REM-021 | P1 | TBD | Logistics | Abstract Class III/V inventory is independent of live entity fuel and weapon magazines | Queued | Yes | Yes | - | - | - | - | Yes | One explicit authority or conservative synchronization contract |
| REM-022 | P2 | 112 | Documentation navigation | Strict MkDocs succeeds while seven historical devlog-index fragment links target missing anchors | **Closed** | Yes | N/A | Yes | N/A | Yes | N/A | N/A | [Phase 112](devlog/phase-112.md#postmortem) |
| REM-023 | P1 | 112 | Scenario data trust | Missing commander profile references warn once per unit while scenario evaluation still reports OK | **Closed** | Yes | Yes | Yes | N/A | Yes | Yes | N/A | [Phase 112](devlog/phase-112.md#postmortem) |
| REM-024 | P1 | 112 | Unit data trust | Invalid crew-skill enums are hidden by a broad `KeyError` catch and silently drop historical units | **Closed** | Yes | Yes | Yes | N/A | Yes | Yes | N/A | [Phase 112](devlog/phase-112.md#postmortem) |
| REM-025 | P2 | 112 | Scenario diagnostics | `MANY_STUCK_UNITS` treats legitimate corrected weapon-range standoff as a movement failure | **Closed** | Yes | N/A | Yes | N/A | Yes | Yes | N/A | [Phase 112](devlog/phase-112.md#postmortem) |
| REM-026 | P1 | 112 | Benchmark trust | A hard 60-second Golan assertion contradicts the checked-in 500-second baseline and fails code that is faster than that baseline | **Closed** | Yes | N/A | Yes | N/A | Yes | Yes | Yes | [Phase 112](devlog/phase-112.md#postmortem) |
| REM-027 | P2 | 112 | Space ISR state | Buffered ISR checkpoint reports use generic JSON normalization rather than a typed semantic rehydration boundary | **Closed** | Yes | Yes | Yes | N/A | Yes | Yes | Yes | [Phase 112](devlog/phase-112.md#postmortem) |
| REM-028 | P1 | 115 | Sensing/combat | Tactical movement can hold at catalog weapon range beyond usable sensing range | **Closed** | Yes | Yes | Yes | Yes | Yes | Yes | Yes | [Phase 115](devlog/phase-115.md#postmortem) |
| REM-029 | P1 | 116 | Fog-of-war state | At the Phase 116 baseline, ordinary contacts serialized but were discarded by `FogOfWarManager.set_state()` | **Closed** | Yes | Yes | Yes | Yes | Yes | Yes | Yes | [Phase 116](devlog/phase-116.md#postmortem) |
| REM-030 | P1 | 117 | Historical validation | At the Phase 112 baseline, catalog winner tables, legacy comparisons, and public docs claimed historical validation without a production, provenance-bearing, held-out outcome-envelope contract; fresh Debecka production exposed incompatible casualty units and a duration miss | **Closed** | Yes | Yes | Yes | N/A | Yes | Yes | Yes | [Phase 117](devlog/phase-117.md#postmortem) |
| REM-031 | P1 | 118 | Performance semantics | At the Phase 112 baseline, Block 9 claimed five performance flags preserve scenario outcomes, but its regression executed only authored configurations, excluded the only two all-flag scenarios, and had no same-input disabled controls | **Closed** | Yes | Yes | Yes | Yes | Yes | Yes | Yes | [Phase 118 postmortem](devlog/phase-118.md#postmortem) |
| REM-032 | P1 | 119 | Guerrilla concealment | Populated-area blend probability was mapped to morale-owned `ROUTING`, while the production context exposes no matching population query or concealed-unit owner | Queued | Yes | Yes | - | - | - | - | - | Typed non-morale concealment changes targetability and persists/exposes its lifecycle |
| REM-033 | P1 | 120 | Surrender/POW state | A public rout helper emitted `SurrenderEvent` and a synthetic POW count without changing authoritative morale/status; no production captor or prisoner lifecycle consumes it | Queued | Yes | Yes | - | N/A | - | - | - | Typed runtime surrender creates captor-owned prisoners and persists/exposes the complete lifecycle |
| REM-034 | P1 | 121 | Event time | Aggregate combat and auto-resolve publish exposed events with `datetime.min` instead of authoritative simulation time | Queued | Yes | Yes | - | N/A | - | - | Yes | Production aggregate/auto-resolve events use exact logical clock time and persist/replay |
| REM-035 | P1 | 122 | Battle topology | One close pair creates one side-pair battle containing every active unit on both sides and prevents a second concurrent battle for that side pair | Queued | Yes | Yes | - | N/A | Yes | Yes | - | Spatially correct, deterministic multi-battle membership with exact continuation |
| REM-036 | P1 | 123 | C2 topology | Catalog communications and standalone C2 engines have no production-loaded, unit-bound communications topology | Queued | Yes | - | - | - | - | - | - | Loaded communications change production order delivery and persist/expose the live topology |
| REM-037 | P1 | 124 | CBRN action | CBRN configuration constructs a nuclear sub-engine, but no typed scheduled chemical/biological/radiological/nuclear action reaches it | Queued | Yes | Yes | - | - | - | - | - | Scheduled action uses real delivery/target topology and changes production effects |
| REM-038 | P1 | 125 | Medical lifecycle | Production does not create medical facilities or admit battle casualties automatically | Queued | Yes | - | - | - | - | - | - | Battle casualty enters a loaded care/evacuation lifecycle and persists/exposes its disposition |
| REM-039 | P1 | 126 | Maintenance lifecycle | Loaded maintenance configuration does not register live loadout equipment or start repairs from real spare-parts logistics | Queued | Yes | Yes | - | - | - | - | - | Runtime equipment breakdown consumes spares and completes an automatic production repair lifecycle |
| REM-040 | P2 | 127 | Validation era | The validation-only `HistoricalCampaign` conversion has no era field and silently returns a modern scenario config | Queued | - | - | - | N/A | Yes | - | - | Validation campaign preserves exact era identity through the authoritative runtime factory |
| REM-041 | P1 | 128 | API authorization | Stored frame targeting supports a side-safe projection, but the route has no caller authorization and defaults to privileged evidence | Queued | Yes | Yes | Yes | - | Yes | Yes | Yes | Authenticated caller-derived scope/side with player-safe defaults and cross-side denial |
| REM-042 | P1 | 129 | Equipment topology | Role-compatible sensors can direct any compatible weapon on the same unit because authored mount/director associations do not exist | Queued | - | - | - | N/A | Yes | Yes | - | Authored exact mount/director bindings across initial, reinforcement, and checkpoint loadouts |
| REM-043 | P2 | 130 | Target selection | Threat ranking does not have an explicit availability-aware selection contract across current weapon/sensor/fire-control solutions | Queued | Yes | Yes | Yes | N/A | Yes | Yes | Yes | Multi-target production comparison with deterministic serviceable-threat selection |
| REM-044 | P1 | 131 | Detection estimation | FOW fusion still uses unsourced generic isotropic range uncertainty despite Phase 118's detached prediction and correlation-safe transaction | Queued | Yes | - | Yes | N/A | Yes | Yes | Yes | Sourced per-sensor range/bearing/correlation covariance and provenance integrated into the existing transaction |
| REM-045 | P1 | 132 | Scripted scenario actions | Phase 101 scripted events use an untyped parameter bag, silently consume failed/no-op actions, bypass position/casualty lifecycle owners, and do not checkpoint or expose exact-once state | Queued | Yes | Yes | Yes | N/A | - | - | - | Typed due-action owner with fail-closed effects, exact-once continuation, and public lifecycle evidence |
| REM-046 | P1 | 133 | Deception state | Active/inactive decoys and their complete signature/degradation/ID topology are not safely checkpointed | Queued | Yes | Yes | Yes | - | Yes | Yes | - | Exact production decoy lifecycle continuation with one DETECTION RNG authority |
| REM-047 | P1 | 134 | Historical engagement fidelity | The frozen 73 Easting production study records zero scoped Iraqi armored losses and no natural terminal in all 20 source-synchronous runs | Queued | Yes | Yes | Yes | N/A | Yes | Yes | Yes | Locate and correct the first production causal divergence without changing the frozen loss/duration envelope or tuning physical parameters to force a pass |
| REM-048 | P1 | 135 | Packaged historical evidence | The local packaged-loader boundary and configured no-`.git` image smoke cover the current zero-accepted ledger, but hosted image evidence is pending and a future accepted artifact cannot be verified because repository acceptance requires Git while the canonical artifact is excluded from the image | Queued | Yes | Yes | Yes | N/A | - | Yes | - | Build-time repository attestation plus tamper-evident no-`.git` receipt and a real nonempty accepted-claim API smoke |
| REM-049 | P1 | 136 | Web UI semantic integrity | Replay/export/editor/analysis surfaces retain incomplete or misleading boundaries after Phase 117 corrected status decoding, canonical scenario fields, and invalid one-click defaults | Queued | Yes | Yes | - | N/A | Yes | Yes | - | Complete export and causal replay/query projection plus explicit catalog-backed editor and analysis inputs |
| REM-050 | P1 | 137 | Optional-suite configuration | Production discards authored escalation tuning, DEW enable-like keys are ignored while presence enables defaults, and no scenario combines a DEW config with a DEW-capable unit | Queued | - | Yes | - | - | Yes | - | - | Strict consumed Escalation/DEW configuration plus enabled/disabled production behavior and a real catalog DEW engagement |
| REM-051 | P1 | 138 | Detection scan lifecycle | Resolving one battle reaches through the context to reset the shared detection engine's scan history globally, so an unrelated concurrent battle can lose integration-gain state | Queued | Yes | Yes | Yes | N/A | Yes | Yes | - | Typed battle-scoped scan-history lifecycle with multi-battle and checkpoint-continuation proof |
| REM-052 | P2 | 139 | FOW update ownership | The public legacy `FogOfWarManager.update()` path duplicates the transactional detection, culling, cadence, indexed-RNG, and fusion algorithm owned by `update_with_receipt()` | Queued | Yes | Yes | - | N/A | Yes | Yes | - | One typed production update implementation or an explicit unsupported legacy boundary with parity/failure proof |
| REM-053 | P2 | 140 | Checkpoint capture | Checkpoint validation repeatedly serializes and restages FOW, detection, and RNG state before the final capture, multiplying work and consistency surfaces | Queued | Yes | Yes | Yes | N/A | Yes | Yes | - | One immutable preflight snapshot graph with exact bytes, atomic failure, continuation, and separately measured profile evidence |
| REM-054 | P1 | 141 | Performance approximation | Frozen v7 scan scheduling failed 13/16 pairs and Suwalki LOD failed 4/16, so current production rejects both controls rather than accepting unbounded fidelity loss | Queued | Yes | Yes | Yes | N/A | Yes | Yes | Yes | Sourced redesign, current rejection red, fresh disjoint paired evidence, and accepted independently verified re-enablement artifact |
| REM-055 | P1 | 142 | FOW runtime cost | Phase 118's atomic FOW transaction preserves semantics but increased the matched ten-tick production median from 47.035449 s to 59.220597 s (+25.906%) | Queued | Yes | Yes | Yes | N/A | Yes | Yes | - | Preserve every integrity invariant while recovering the measured gross regression with persistent matched profile evidence |

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

- Phase 107 preserved the then-current equipment-name mapping semantics.
  Duplicate and semantically wrong mappings were deferred to REM-010 and
  closed by completed Phase 109.
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
physics/tick override metadata was deferred to REM-018 and closed by completed
Phase 114.

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
  remains REM-020/021. Analysis and broader validation trust were deferred to
  and closed by completed Phase 112.

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
independent restore gap was then REM-029; Phase 116 subsequently implements
that separate repair and is completing its closure gates. Aggregation remains
bounded by REM-016.

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

### Phase 114 Jutland evidence

The final seed-42 production replay adds a second catalog-backed reproduction.
Jutland completed after 569 ticks and 7,620 logical seconds with a British
`force_destroyed` result, 10 casualties, and 15 engagement events. All five
active British Iron Duke battleships finished with
`ENGINE_WEAPON_STANDOFF` after 537 of 569 movement decisions at a catalog
best-weapon range of 21,780 m; all three active Invincible battlecruisers did
the same after 561 decisions at 21,700 m. Their loaded Barr & Stroud
rangefinder maps to the 3,000 m WW1 visual sensor while scenario visibility is
8,000 m. The recorded weapon-fire topology contains QF 4-inch destroyer fire
and one naval engagement, but no capital-gun engagement.

That exact current-engine observation strengthens the blind-standoff red; it
does not establish the correct targeting prerequisite, validate Jutland
historically, or authorize extending the rangefinder. Phase 114 changes era
cadence ownership only and leaves the movement branch unchanged.

### Phase 115 closure evidence

Phase 115 now loads one strict default-on targeting owner through the
authoritative runtime factory. Each tactical interval publishes immutable
tick/battle/shooter decisions after one canonical FOW update. Automatic
movement standoff and ordinary direct engagement consume the same exact
contact, weapon, sensing/fire-control, range, and post-movement revalidation
evidence. Explicitly disabling automatic standoff authorizes `0.0 m`; raw
catalog maximum never returns as a fallback. Exact role/source bindings cover
initial, reinforcement, and checkpoint reconstruction.

Cambrai seeds 42--44 move all four Mark IVs that formerly blind-held outside
their 3,000 m usable optical envelope. Jutland seeds 42--44 move all 29 units
and reach capital-weapon engagement instead of stopping capital ships solely
at 21.7 km. Salamis proves the corrected ancient-projectile naval role and
rejects an aerial control. Format-115 no-FOW continuation is exact; restored
FOW decisions are historical/non-consumable, and REM-029 remains explicit.
Movement diagnostics, evaluator/replay, paired privileged/side-FOW API frames,
and frontend schemas expose the decision evidence.

The accepted implementation matrix is `D=Yes, L=Yes, W=Yes, E=Yes, X=Yes,
O=Yes, P=Yes`. The final standard partition passed 11,743/11,743 nodes; data,
determinism, scenario, frontend, static, documentation, and focused real
database/API persistence gates passed. Owner-qualified slow/API/E2E contention
results and Debecka's REM-030 signal remain disclosed rather than being called
passes. The final frozen-tree 73 Easting version-4 transition verified all
29/29 approvals with `transition_qualified`, identical approved semantic
state, and timing explicitly `not_applicable` because the workload identity
changes. At Phase 115 closure, Phase 116 still had to promote the clean endpoint
before ordinary paired gating resumed; that handoff was not a performance pass.

Phase 116 subsequently completed that promotion against clean commit
`271ec49ceb508bdd050e2d5c3072ac91456cca7c`; the paragraph above remains the
historical Phase 115 handoff requirement.

**Status:** **Closed** by the accepted Phase 115 postmortem.

## REM-029 - Ordinary fog-of-war contacts are discarded on restore

### Reproduction and required proof

At the Phase 116 baseline, `FogOfWarManager.get_state()` serialized each
`SideWorldView.contacts` entry, but `set_state()` restored only last-update
times and left every ordinary contact absent. REM-027 could prove typed Space-report queue and
intelligence-fusion track continuation only with ordinary world views
explicitly empty; it could not support a whole-fog-of-war continuation claim.

Phase 116 implements staged validation of exact side ownership, contact IDs,
`ContactInfo`, nested track state, update times, topology, and DETECTION RNG
authority before mutation. A nonempty-contact fresh-runtime continuation must
preserve decay, update, common-operating-picture behavior, subsequent events,
and whole-context checkpoint equality.

### Phase 116 closure evidence

Format 116 restores the complete strict
`world_views/current_detection_witnesses/rng_state/intel_fusion` envelope
through one typed context-owned plan. Factory-built enabled and disabled
sessions prove exact contact-to-fusion aliases, current witness and targeting
consumability, outcome-affecting movement/engagement use, decay/coast/loss and
redetection, current event/recorder continuation, dynamic registration,
replacement, corruption/retry atomicity, and whole-checkpoint equality. The
210-node focused suite, 11,953-node standard partition, determinism, data,
scenario, benchmark-policy, Ruff, documentation, cross-document, and
postmortem gates passed or carry the exact owner-approved contention
qualification recorded in the [Phase 116 devlog](devlog/phase-116.md#postmortem).

**Status:** **Closed** by the accepted Phase 116 postmortem. REM-036 retains
custom/populated COP/data-link state, and REM-046 / Phase 133 retains complete
active-deception checkpoint state; neither reopens roster-backed ordinary
contact continuation.

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

### Phase 114 current-engine trajectory signals

Phase 114 corrected interval cadence so work discovered during one interval
selects the next interval instead of relabeling the completed interval. In the
final 46-scenario seed-42 production replay, 31 rows retained their exact
semantic result, 12 changed by the expected one-boundary cadence correction,
and Jutland, Khafji, and Taiwan Strait produced deterministic downstream
cascades. Seeds 42 through 44 produced:

| Scenario | Phase 113 ticks/casualties | Phase 114 ticks/casualties | Phase 114 terminal |
| --- | --- | --- | --- |
| Jutland 42 / 43 / 44 | 373/21; 397/21; 469/24 | 569/10; 437/6; 713/8 | British / `force_destroyed` in all three |
| Khafji 42 / 43 / 44 | 721/90; 683/78; 676/60 | 728/77; 668/79; 680/60 | Blue / `force_destroyed` in all three |
| Taiwan Strait 42 / 43 / 44 | 8/15; 7/14; 8/14 | 61/15; 61/17; 157/21 | Blue / `force_destroyed` in all three |

All nine final-tree replays matched the accepted candidate and had empty issue
arrays. Those observations are regression/fidelity inventory signals only.
They are not source-backed outcome envelopes, a held-out historical study, a
calibration verdict, or authority to tune physical parameters. Phase 117
retains the complete catalog and public-claim disposition.

### Phase 115 current-engine trajectory signals

The REM-028 shared-targeting repair supplies two further deterministic signals
without turning either into calibration authority.

Debecka seeds 42 through 51 changed from the Phase 114 current-engine result of
10 blue wins, mean 32.5 destroyed blue records, mean 15.6 destroyed red
records, and mean 137.9 ticks to 4 blue wins, means 42.5 and 6.7 destroyed
records, and mean 1,887.5 ticks. Every current seed still records five bomb and
six Javelin engagements. The principal removed path is legacy aircraft-cannon
ground fire that lacked compatible director evidence: Phase 114 recorded 1,315
M61A1 ground engagements across the ten seeds, while the current runs record
about 25. For example, the F-14's aerial-only AN/AWG-9 cannot direct its M61 at
a ground target and now records `FIRE_CONTROL_TARGET_DOMAIN_UNSUPPORTED`; the
multi-domain F/A-18 APG-73 retains limited valid ground-gun use.

The strict `enable_sensing_aware_standoff=false` control improves the current
result only to 7/10 blue wins, with means 43.1 destroyed blue records, 8.8
destroyed red records, and 1,137.6 ticks. That isolates standoff as a
downstream exposure/morale contributor, not the cause of the removed invalid
fire. The remaining nonterminal runs expose an authored-horizon contradiction:
the scenario duration is four hours while its blue `time_expired` condition is
due at six hours. A typed in-memory six-hour control with a 4,500-tick safety
cap reached 10/10 blue labels, but six were the unconditional authored fallback
at exactly 4,320 ticks / 21,600 seconds after every blue unit was already
destroyed or surrendered. The unchanged regression harness also caps at 3,000
ticks and cannot reach that fallback. Changing the horizon, cap, or winner
threshold would therefore manufacture a pass rather than validate policy.

Fallujah seed 42 changed from the Phase 112 artifact's blue
`force_destroyed` result at 115 ticks / 575 seconds, 1,643 evaluator
engagements, 256 moved and 77 unmoved units, 830.7 m mean travel, and 3,543
events to the final Phase 115 blue `force_destroyed` result at 40 ticks / 200
seconds, 70 casualties, 297 evaluator engagements (221 direct engagement
events), all 333 units moving at least once, 1,060.7 m mean travel, 2,282
events, and eight pre-emplaced IED detonations. An explicit standoff-disabled
control ends at 38 ticks, so the default-on flag is not an early-termination
accelerator. The current regression ends before the first authored scripted
action at H+7; loading 11 declarations and resolving their references does not
prove dispatch or effects. REM-045 / Phase 132 owns that independent runtime
integrity gap.

These are deterministic current-engine semantic deltas produced by correcting
shared targeting authority. They are not source-backed historical duration or
casualty envelopes, held-out validation, calibration verdicts, or authority to
tune weapons, morale, victory policy, or scenario parameters. Phase 117 must
classify them with the rest of the catalog-wide evidence.

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

### Phase 112 baseline evidence-matrix rationale

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

**Phase 112 handoff status:** Queued for Phase 117. Phase 112 relabeled false tests as
current-engine regression and recorded the deficit, but did not close
REM-030.

### Phase 117 implementation and closure evidence

Phase 117 replaces that unowned claim surface with one strict repository
ledger and factory-owned backtest boundary. Scanner version 2 enumerates 196
candidate files across API Python, public and test frontend source, Python
tests, public Markdown, scenario YAML, and repository workflow skills. The
ledger binds 134 of those files to exact claim IDs and records 62 explicit
reviewed nonclaims. Reviews are whole-file/digest based rather than
occurrence-level, so semantic locators and a manual cross-document audit remain
mandatory.

The current inventory contains 233 claims: 214 unsupported, 19
current-engine-regression-only, and zero production-validated. It covers all
31 shipped `documented_outcomes` collections / 83 metrics, three scenario
prose claims, 25 Python claim-test surfaces, one frontend claim-test surface,
154 documentation claims across 66 paths, 11 frontend claim surfaces, four API
claim surfaces, three duplicated regression tables, and the canonical
46-scenario snapshot. Full source/data validation reports no uninventoried or
missing collections, unreviewed candidates, stale reviews, source/rule/binding
errors, obsolete boolean verdict APIs, or content-digest mismatch.

The strict study plan declares source provenance and lineage, exact metric
units/scopes/event boundary, arithmetic training/held-out seed intervals, a
maximum of 1,000 production runs, and one joint acceptance policy. Execution
uses `SimulationRuntimeFactory` preparation and one fresh production session
per seed. Complete/`ERROR` artifacts persist raw vectors, exact production
identities, terminal/censoring evidence, unit-level observation receipts,
recomputed statistics/verdict, claim bindings, and a self-digest. Acceptance
then adds clean Git ancestry, immutable predeclaration, independent evidence,
exact metric binding, no relevant code/dependency drift, and fresh production
identity checks. Scenario APIs and the frontend expose the resulting
claim-level classification and remove legacy outcome metadata from the public
config.

The corrected 73 Easting study executed seeds 11700--11719 through that
boundary. All 20 runs recorded zero of the required 28 scoped Iraqi tank
losses, zero of the required 16 scoped Iraqi personnel-carrier losses, the
required zero American scoped-vehicle losses, and a cutoff-censored rather
than natural 1,380-second duration. Joint success is 0/20 and the one-sided
lower bound is 0.0; diagnostics are 16 draws and four red wins. The retained
artifact is therefore a completed `FAIL`, not a manufactured pass or an
engine-wide predictive invalidation. Source reuse and the phase's one-commit
bootstrap independently prevent promotion even under a hypothetical pass.

The resulting matrix is `D=Yes, L=Yes, W=Yes, E=N/A, X=Yes, O=Yes, P=Yes`.
Declaration is the strict ledger/plan/artifact schema; loading and wiring are
the canonical ledger, plan, factory, runner, evaluator, and reload boundary;
exercise/outcome evidence is the real 20-seed failed study and adversarial
verdict controls; persistence/exposure is the durable artifact plus exact
claim-level API/frontend result. `E` is N/A because historical conformity is
not a simulation feature switch; explicit plan/no-plan and promotion-eligible /
ineligible controls are the relevant negatives.

**Status:** Closed in Phase 117 after accepted documentation,
cross-document, postmortem, and final ledger/artifact gates. The retained
production study remains a truthful `FAIL`; closure classifies the claim
surface correctly and does not promote a scenario.

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
persisted semantic verdict was added in Phase 112; REM-031 therefore remained
open at that baseline.

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

### Phase 118 qualified-negative closure evidence

Phase 118 replaced the blanket Block 9 promise with a typed five-entry
classification and support registry, production-owned execution receipts, and
strict paired artifacts. Detection culling, SoA selection, and parallel
per-side detection are `supported_exact_validated`. Native scan scheduling and
sensing-only LOD remain model-fidelity approximations, but their production
support disposition is `unsupported_failed_semantic_validation`.

The retained v6 study reached 96 pairs / 396 attempts under explicit external
contention and ended terminal `ERROR`. After the owner approved Option A, the
schema-2 `phase118-performance-semantics-v7` plan froze 16 fresh seeds
disjoint from every diagnostic exclusion, 96 pairs / 396 attempts, and plan
SHA-256
`5ffb74205281d8913b618fc607f47bf4cdccc0f2741bd812cc82989761c1b41d`.
The one authoritative execution completed and independently reloaded as an
eligible `EXTERNALLY_CONTENDED` `FAIL` at manifest artifact SHA-256
`bf9e00ce4a7774af29b5657c49bbbe4481b407a966d9922e48970022f5c6ad86`.
Culling, SoA, and parallel detection passed 16/16. Scan scheduling passed 3/16
and failed 13/16. Calibration LOD passed 16/16; Suwalki LOD passed 12/16 and
failed 4/16; its three accepted complete-case recovery checks passed with
candidate totals 74, 37, and 185. Both v6 and v7 archives are immutable
negative evidence. The raw study, frozen plan, one-off executor/verifiers, and
terminal bytes are intentionally off main at
`branch=evidence/full; path=docs/evidence/phase-118/v6-terminal/`,
`branch=evidence/full; path=docs/evidence/phase-118/v7-terminal/`,
`branch=evidence/full; path=data/validation/performance_semantics/phase118.yaml`,
and
`branch=evidence/full; path=docs/evidence/phase-118/runtime-manifest-handoff.json`.

The typed handoff binds the immutable 1,408-entry execution snapshot to the
reviewed 1,408-entry retirement snapshot through exactly fifteen old/new
runtime-path identities.
Their manifest SHA-256 values are respectively
`2f10ab7c7a2b409067c90f92616609e921750fa7641c4d3165f90b53fa21e9a8`
and `0a6b32a48fd7ea764d6522eb7ebccdc32c803663aed295c916ba47240668bf07`;
the handoff self-digest is
`b505edc418f87ffdf659bed52b502cef043df472c8a04696d0fda8d99d4e746d`.
The archived verifier can reproduce the exact v7 `FAIL` and handoff; it cannot
execute the observed inputs or make a speed claim.

On 2026-08-22 the owner approved qualified-negative closure. Production now
rejects `enable_scan_scheduling=true`, `enable_lod=true`, and every non-default
LOD interval/hysteresis value through the shared scenario, API, analysis,
runtime, manual-context/manager, receipt, and checkpoint boundary. The two
measurement-only benchmark scenarios explicitly keep those fields false.
Historical receipt/artifact decoding remains permissive so the terminal bytes
stay verifiable. `GET /api/meta/performance-flags` exposes the canonical
classification, support disposition, evidence identity, and per-flag verdict.
The `E` matrix cell means enabled/disabled production proof for the three
supported flags plus explicit fail-closed positive-input proof for the two
retired controls; it does not award positive enablement to a failed feature.

The causal diagnosis and any future redesign are assigned to REM-054 / Phase
141. REM-044 remains the source-backed sensor-covariance prerequisite, and the
tentative-track initiation/aging deficit must be specified rather than tuned
from observed seeds. No budget, source, pair, combat/catalog/scenario input, or
v7 verdict was changed to obtain closure.

**Status:** **Closed** by the accepted Phase 118 postmortem. Detection culling,
SoA selection, and parallel detection retain exact support; scan scheduling and
LOD remain explicit unsupported terminal failures. The matched profile's
measured runtime regression is separately queued as REM-055 / Phase 142. No
documentation may describe the flags as historically calibrated, universally
equivalent, or faster on the basis of this phase.

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

### Phase 115 version-4 workload-transition extension

Phase 115 intentionally changes the effective 73 Easting workload through the
new default-on sensing-aware-standoff flag and corrected VVS-2 role/domain
data. The version-3 gate correctly rejects before timing because the reference
and candidate runtime-input fingerprints and derived loadout digest differ.
Policy version 4 therefore adds a separate non-timing transition contract over
the unchanged version-3 runtime-input normalization. It requires one exact
production closure per endpoint, complete classified RFC-6901 differences,
authoritative predecessor and tree identities, and zero timed pairs or
performance decisions. `transition_qualified` is not a pass and cannot be
used to claim speed.

Phase 116 promoted the clean Phase 115 endpoint to an ordinary paired reference
before production edits. The temporary reviewed handoff therefore completed
without comparing unequal workloads or weakening the 1.20/0.20 gate. It does
not reopen REM-026.

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

### Phase 114 implementation evidence

**Matrix:** `D=Yes, L=Yes, W=Yes, E=Yes, X=Yes, O=Yes, P=Yes`.

Phase 114 replaces both arbitrary dictionaries with frozen, extra-forbidden
typed declarations. The supported physics keys are the three medical
treatment durations and maintenance repair duration; the supported cadence
keys are strategic, operational, and tactical seconds. Strict finite-positive,
type, microsecond, duration, calendar-horizon, registry, and conflict checks
fail before runtime RNG construction. The former `c2_delay_multiplier` and
`cbrn_nuclear_enabled` keys now reject explicitly because their production
prerequisites remain REM-036 and REM-037 rather than being proxied.

One frozen `EraRuntimeContract` is resolved by
`SimulationRuntimeFactory`/`PreparedScenario` or the direct lower loader and
then exclusively supplies `SimulationClock`, `SimulationEngine`, medical,
maintenance, runtime loadout, and API-frame cadence consumers. Natural
strategic, operational, and tactical intervals use one preselected resolution
and duration. Same-seed declared/omitted controls change all three medical
completion endpoints and maintenance repair completion, while omission
preserves the destination defaults. Maintenance now advances exactly once per
logical interval rather than once in both campaign and engine owners.

Checkpoint format 114 persists and compares the exact effective contract,
source cadence, execution horizon, selected registry identity, clock,
resolution, and frozen consumer configuration before mutation. Fresh and
in-place active treatment/repair continuation is exact. The effective contract
also changes the exposed runtime fingerprint and is exercised through the
real API run manager. Final focused evidence passed 93 non-API tests and one
API production behavior proof; the exact 11,903-node Python union, full data
validation, and final 46-scenario replay are recorded in the Phase 114 devlog.

Phase 114 is **Complete** and REM-018 is **Closed**. Documentation,
`$cross-doc-audit`, and `$postmortem` pass. The owner accepted the performance
result only as contention-qualified evidence, preserved the original
thresholds, made no uncontended-pass claim, and deferred clean confirmation
until all cores are free.

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

## REM-035 - Battle membership collapses each side pair into one topology

### Phase 114 finding and nonclaim

`BattleManager.detect_engagement()` declares and loads the authored runtime
roster, computes the minimum distance between two sides, and creates a battle
when any opposing pair is within engagement range. The created
`BattleContext.unit_ids`, however, contains every active unit on both sides,
including spatially remote units. Its duplicate guard is only the unordered
side pair, so a second spatially distinct battle between the same sides cannot
exist concurrently.

The natural-resolution Phase 114 proofs legitimately exercise one unit per
side and show that a loaded active battle changes cadence and domain execution.
They do not prove realistic multi-unit battle membership. The 46-scenario
replay and the deterministic Jutland/Khafji/Taiwan cascades establish that the
current topology is production reached and outcome-affecting; they do not
validate its spatial grouping or historical fidelity.

**Matrix:** `D=Yes, L=Yes, W=-, E=N/A, X=Yes, O=Yes, P=-`. `E` is N/A because
correct battle membership is a mandatory runtime invariant, not an optional
mode.

### Required proof

- Define one typed battle-membership identity based on deterministic spatial,
  command, and participation rules rather than global side membership.
- Permit multiple simultaneous battles between the same sides without placing
  one unit in conflicting active battles.
- Route resolution, movement, combat, logistics activity, aggregation, and
  victory reads through the exact membership.
- Prove deterministic creation, merge/split/termination behavior and exact
  fresh/in-place checkpoint continuation through realistic multi-cluster
  production scenarios.

**Status:** Queued for Phase 122. Phase 114 records the precondition but does
not broaden REM-018 into a battle-topology rewrite.

## REM-036 - Production C2 lacks a loaded communications topology

### Phase 114 finding and nonclaim

Communication catalogs, `CommType`, courier/visual-signaling engines, and C2
delay APIs are declared, but the production scenario boundary does not load
communications equipment onto exact units, HQs, relays, or links. The battle
path can catch a propagation failure, and isolated `compute_delay()` or
courier calls can produce numbers, but neither establishes a live network or
an order-delivery outcome. The former era `c2_delay_multiplier` was therefore
dead metadata; Phase 114 removes it from shipped presets and rejects it rather
than multiplying an absent topology.

**Matrix:** `D=Yes, L=-, W=-, E=-, X=-, O=-, P=-`.

### Required proof

- Define typed communications assignments and link/relay topology with exact
  unit, side, HQ, equipment, range, latency, reliability, and availability
  identities.
- Load and validate that topology through the authoritative scenario/runtime
  factory and reject missing, wrong-owner, duplicate, or impossible links.
- Wire order issue, propagation, acknowledgement, degradation, interception,
  and failure through the production C2 path without a catch-and-continue
  capability claim.
- Prove enabled/disabled, connected/disconnected, degraded, and destroyed-link
  outcome differences plus exact event/API and checkpoint continuation.

**Status:** Queued for Phase 123. Phase 114 makes unsupported era C2 metadata
an explicit error; it does not claim production communications.

## REM-037 - CBRN has no typed scheduled action boundary

### Phase 114 finding and nonclaim

`CampaignScenarioConfig.cbrn_config` and the CBRN suite are declared and
loaded, and an enabled suite constructs `NuclearEffectsEngine` unconditionally.
No typed scheduled chemical, biological, radiological, or nuclear action
selects a real owner, weapon/delivery system, target, yield/agent, release
time, or authorization and calls that engine from the production loop. A
direct `detonate_nuclear()` invocation proves an effects API, not a scheduled
warfare capability. The former `cbrn_nuclear_enabled` era key could neither
enable nor disable an action and now rejects explicitly.

**Matrix:** `D=Yes, L=Yes, W=-, E=-, X=-, O=-, P=-`.

### Required proof

- Define strict scheduled CBRN action declarations with exact owner, delivery
  asset/weapon, target, logical time, agent or nuclear yield, authorization,
  and capability-gate identities.
- Validate the complete live topology before runtime mutation or CBRN RNG use
  and reject unsupported era, ownership, inventory, target, or timing input.
- Execute actions from the production session loop and prove enabled/disabled,
  available/unavailable, and successful/failed outcome differences without a
  dummy launcher, target, or detonation.
- Persist pending/executed actions, affected inventories and environments,
  events, recorder/API exposure, and exact deterministic continuation.

**Status:** Queued for Phase 124. Phase 114 neither schedules a CBRN action nor
claims that construction of the nuclear sub-engine enables nuclear use.

## REM-038 - Medical treatment lacks an automatic casualty lifecycle

### Phase 114 finding and nonclaim

Typed medical facilities, casualties, treatment queues, and treatment-duration
configuration exist. Phase 114 proves the era construction boundary by
registering a real facility and admitting a real casualty through the public
medical API, then advancing only through `RuntimeSession.step()`. Production
scenario loading and battle resolution do not create facility topology,
convert combat casualties into medical records, select or move them to care,
or consume Class VIII resources. The duration proof is therefore not an
automatic battlefield medical lifecycle claim.

**Matrix:** `D=Yes, L=-, W=-, E=-, X=-, O=-, P=-`.

### Required proof

- Define and load exact medical facility, capacity, staffing, supply,
  evacuation, triage, and casualty-origin topology.
- Commit a battle casualty once into the authoritative personnel and medical
  lifecycles without duplicating deaths, wounded strength, or available crew.
- Wire triage, movement, admission, treatment, return-to-duty, evacuation, and
  failure/resource constraints through production logical time.
- Prove realistic enabled/disabled and resource/capacity controls, observable
  unit/crew outcomes, and exact event/API and checkpoint continuation.

**Status:** Queued for Phase 125. Phase 114 wires supported treatment duration
overrides only after explicit public setup.

## REM-039 - Maintenance lacks automatic registration and spares-driven repair

### Phase 114 finding and nonclaim

Maintenance configuration and the engine are declared and loaded, and Phase
114 makes the all-resolution engine loop its sole once-per-interval update
owner. The behavioral proof explicitly registers synthetic equipment through
the public API, reaches breakdown during a production step, and calls
`start_repair()` with a literal available-parts amount. Runtime loadout
construction does not register each live weapon, sensor, propulsion, or other
equipment instance with maintenance, and the Class IX/spares network does not
authorize, consume, delay, or start its repair.

**Matrix:** `D=Yes, L=Yes, W=-, E=-, X=-, O=-, P=-`.

### Required proof

- Register exact runtime-owned loadout instances automatically and reject
  duplicate, proxy, missing-owner, or topology-divergent maintenance records.
- Establish one condition/readiness authority between live equipment and the
  maintenance record, including dynamic reinforcement and aggregation paths.
- Route diagnosis, repair priority, start, parts reservation/consumption,
  completion, cancellation, and failure through real Class IX inventory and
  logistics reachability.
- Prove breakdown-to-repair enabled/disabled and parts-available/unavailable
  outcome differences plus exact events, recorder/API exposure, rollback,
  RNG accounting, and checkpoint continuation.

**Status:** Queued for Phase 126. REM-020 and REM-021 retain their broader
activity-demand and inventory-authority scope; Phase 114 does not absorb them.

## REM-040 - Validation campaign conversion silently loses era identity

### Phase 114 finding and nonclaim

The validation-only `HistoricalCampaign` model mirrors only a subset of
`CampaignScenarioConfig` and has no `era` field.
`CampaignDataLoader.to_scenario_config()` therefore constructs a config whose
era silently defaults to `modern`, even if the source campaign is intended for
another era. Existing validation campaign flows exercise that conversion, but
Phase 114 does not add a second era-resolution rule to a legacy validation
model or claim an outcome effect without a controlled non-modern campaign.

**Matrix:** `D=-, L=-, W=-, E=N/A, X=Yes, O=-, P=-`. `E` is N/A because exact
source identity must survive every conversion; silently changing era is never
a supported toggle.

### Required proof

- Add strict normalized era identity and every required production source
  field to the validation boundary, or replace its duplicated scenario model
  with an explicit typed projection that cannot silently omit new fields.
- Resolve the era only through `SimulationRuntimeFactory`, not through a
  validation-owned registry lookup or modern fallback.
- Prove a non-modern campaign loads the expected gates, equipment/catalog
  selection, effective era contract, fingerprint, and outcome relative to an
  explicit modern control.
- Reject absent/unknown/mismatched identity and persist the exact projection
  provenance in validation artifacts and checkpoint continuation where used.

**Status:** Queued for Phase 127. This is a validation-only propagation gap;
it does not weaken Phase 114's authoritative production factory contract.

## REM-041 - Player-facing targeting exposure lacks caller authorization

### Phase 115 finding and nonclaim

Phase 115 stores both a privileged targeting projection and a structurally
side-safe `SIDE_FOW` projection. The frame route validates the requested scope
and side combination and the frontend has typed support for either projection.
The route does not authenticate a caller, derive a permitted side, or require
an explicit operator privilege, however. Its omitted-query default is
`PRIVILEGED_ENGINE`, and the current tactical map uses that default. A
caller-supplied `scope=SIDE_FOW&side=...` is a payload choice, not an
authorization boundary; client-side filtering is not access control. The
current FOW toggle filters only the main enemy-marker draw loop: movement
trails, engagement arcs, hit testing, a stale selected-unit sidebar, and its
sensor circle can still disclose hidden activity.

**Matrix:** `D=Yes, L=Yes, W=Yes, E=-, X=Yes, O=Yes, P=Yes`. These `Yes`
entries describe the paired projection machinery only. They do not prove the
missing caller authorization or a safe default.

### Phase 118 exposure hardening

Phase 118 adds exact nullable observer-track support to the privileged stored
decision and cross-binds it through one atomic decoder to the root roster,
complete side-view set, and target-to-opaque-track associations before either
API scope or replay returns. `SIDE_FOW` retains only the distinct support
contact source and opaque track; it omits target/attachment identity,
chronology, covariance, and the nested support record. This closes a stored-
evidence integrity gap, but does not authenticate the caller, change the
privileged default, or make the frontend player-safe.

### Required proof

- Define caller identities, player-to-side grants, and an explicit privileged
  operator/evaluator grant in one server-owned authorization contract.
- Derive scope and side from that contract or strictly validate any requested
  narrowing against it before stored frame evidence is read.
- Make ordinary player and frontend defaults side-safe; reject unauthenticated,
  cross-side, and privilege-escalating requests without leaking target,
  attachment, or roster existence.
- Feed the authorized side projection into every map overlay and interaction,
  clear or rederive selected state as frames/sides change, and prove that
  trails, arcs, hit testing, sidebars, and sensor overlays cannot cross the
  caller's visibility boundary.
- Prove allowed and denied production API calls, audit records, frontend use,
  legacy-data behavior, and persistence boundaries. A response filter or UI
  toggle alone is insufficient.

**Status:** Queued for Phase 128 in Block 14. Phases 115 and 118 prove the
projection and stored-decoder structure, not caller authorization.

## REM-042 - Compatible roles do not encode physical mount/director topology

### Phase 115 finding and nonclaim

Phase 115 replaces name and collection-position inference with canonical exact
source indexes and total weapon-role/sensor-role/domain policy. That policy
prevents unrelated role classes, such as an artillery sight directing an
organic direct-fire weapon. Within a compatible role class, a sensor mapping
currently publishes every compatible weapon source index on the same unit.
The catalogs do not author which rangefinder, fire-control system, or director
serves which physical weapon or mount group, so a mixed platform can still
cross-bind two otherwise compatible attachments.

**Matrix:** `D=-, L=-, W=-, E=N/A, X=Yes, O=Yes, P=-`. `E` is N/A because
physical topology is mandatory data, not an optional fidelity mode. Phase 115
production decisions expose the exact current cross-binding result, which is
the evidence for `X` and `O`, not proof of the missing topology.

### Required proof

- Author stable weapon/mount/director association IDs or an equally explicit
  topology for every affected catalog entry; classify genuinely unsupported
  combinations instead of guessing.
- Validate uniqueness, ownership, target-domain and role compatibility, and
  complete references before constructing a runtime loadout.
- Resolve exact associations through the same initial, reinforcement, and
  checkpoint loadout builder without names or list-position coincidence.
- Prove mixed compatible-loadout engagement selection and rejection, exposed
  provenance, deterministic ordering, and exact fresh/in-place continuation.

**Status:** Queued for Phase 129 in Block 14. Phase 115's total role policy is
an upper bound and does not claim physical mount topology.

## REM-043 - Threat selection lacks an availability-aware contract

### Phase 115 finding and nonclaim

The tactical targeting runtime validates candidates and persists an exact
decision, and the current target-selection mode can rank hostile candidates by
threat. Phase 115 does not define a complete policy for comparing current
serviceability across weapon, ammunition, sensing, fire-control, and target
domain before ranking multiple threats. Its single selected decision therefore
must not be described as an availability-aware threat optimizer.

**Matrix:** `D=Yes, L=Yes, W=Yes, E=N/A, X=Yes, O=Yes, P=Yes`. This is the
existing deterministic selection and decision-evidence matrix. `E` is N/A
because correct selection semantics are not a feature toggle; the missing
availability-aware contract remains open.

### Required proof

- Declare deterministic ordering and scoring for serviceable, temporarily
  unavailable, and unsupported target/weapon/sensor combinations.
- Decide and document whether selection ranks only complete current solutions
  or represents unavailable threats without authorizing movement or fire.
- Prove production multi-target cases where threat and serviceability conflict,
  including no-solution, ammunition, degraded sensor, fire-control, domain,
  tie, and reordered-roster controls.
- Persist/expose the score inputs and selected disposition, preserve RNG stream
  authority and checkpoint continuation, and do not retune physical data to
  force a preferred target.

**Status:** Queued for Phase 130 in Block 14. Phase 115 closes blind catalog-
range standoff without absorbing this selection-policy follow-up.

## REM-044 - Sensor fusion lacks sourced covariance provenance

### Phase 115 finding and Phase 118 narrowing

Stable side-local FOW track reuse exposed two pre-existing estimator
assumptions. `submit_sensor_detection()` derives one isotropic position
uncertainty as five percent of reported range, without sensor-specific range
or bearing error data; at zero range that became zero covariance and made the
next conventional innovation inverse singular. Phase 115 requires finite,
strictly positive report uncertainty and applies the subsystem's generic
one-metre numerical minimum. It also bounds a gated replacement to one current
fusion track and preserves a monotonic, never-reused public ordinal.

That repair does not turn the generic minimum into historical sensor accuracy.
Phase 118 now reconstructs horizontal ENU position from detector-emitted
horizontal range and bearing while retaining slant range as the generic
uncertainty input. It predicts existing tracks on detached state, validates a
complete same-side/same-target/same-epoch report group, selects one canonical
best-variance representative so correlated duplicates are not treated as
independent measurements, and atomically commits the accepted update or
replacement. Its bounded seven-role radar support preserves the resulting
fusion generation through cadence deferral and exposes exact projection/
covariance evidence to privileged consumers.

The remaining deficit is narrower and still material: uncertainty remains an
unsourced isotropic five-percent-of-slant-range model with a numerical floor.
The catalogs do not provide per-sensor range/bearing error, correlation,
operating envelope, or source provenance. Phase 118 therefore makes no claim
of historical sensor accuracy.

**Matrix:** `D=Yes, L=-, W=Yes, E=N/A, X=Yes, O=Yes, P=Yes`. Existing report,
track, covariance, detached prediction/grouping, support, and gating types
support `D/W`; Phase 115 zero-range controls and Phase 118 non-coplanar,
same-epoch, loss/redetection, targeting, checkpoint, and exposure controls
support `X/O/P`. `E` is N/A because correct measurement covariance is mandatory
data/model provenance, not a fidelity toggle. Sensor-specific covariance and
its source provenance are still not loaded.

### Required proof

- Author or explicitly classify range and bearing error models, units,
  operating envelopes, correlations, and sources for every applicable sensor
  class; do not infer accuracy from display names or tune it to scenario
  outcomes.
- Convert range/bearing errors and current geometry into a finite positive
  semidefinite position covariance, with a declared treatment for genuinely
  exact/noise-free observations rather than a hidden matrix fudge.
- Integrate the sourced covariance into the existing detached prediction,
  complete-group validation, canonical representative selection, and atomic
  update/replacement transaction without weakening timestamp, alias, or
  rollback invariants.
- Prove stationary, crossing, accelerating, zero/short-range, gated, stale,
  reordered, parallel, and checkpoint-resume behavior through the production
  FOW path with exact RNG/process-noise ownership.
- Persist and expose the required covariance/prediction provenance in
  privileged evidence and a non-leaking side-safe projection.

**Status:** Queued for Phase 131 in Block 15. Phase 118 closes the generic
detached prediction, correlation-safe grouping, and support/persistence
boundaries without claiming sensor-specific estimation fidelity.

## REM-045 - Scripted scenario actions lack a typed exact-once runtime owner

### Phase 115 finding and nonclaim

Phase 101 added `ScriptedEventConfig(time_s, event_type, params)` and four
Fallujah handlers. The outer model validates the event-type string, but the
per-type payload remains `dict[str, Any]`; required fields, exact target kinds,
units, bounds, and cross-references are not represented by a discriminated
typed contract. `CampaignManager.check_scripted_events()` catches every
handler exception and adds the ordinal to `_fired_scripted_events` anyway.
Missing unconventional/incendiary owners, unresolved IEDs or units, and other
handler no-ops return normally and are also counted as fired. The relocation
handler assigns `Unit.position` directly and the casualty handler pops the
personnel list, bypassing authoritative movement, casualty/status, event, and
dependent-owner lifecycles.

The fired set is created dynamically on `SimulationContext`; it is absent from
`CampaignManager.get_state()`, format-115 context state, recorder/API evidence,
and fresh restore. There is therefore no exact schedule identity, pending /
attempted / committed / failed disposition, effect receipt, or exactly-once
checkpoint continuation. Phase 101's own test-quality review acknowledged that
no test exercised WP, relocation, or casualty dispatch. Phase 115's final
Fallujah production run terminates after 40 ticks / 200 seconds, before the
first scripted action at H+7, so its clean terminal and combat checks do not
repair that proof gap.

This deficit does not invalidate the loaded Fallujah catalog, pre-emplaced-IED
path, or current-engine combat regression. It does supersede Phase 101 claims
that every scripted historical moment has proven honest production causality
or that declaration/reference checks establish execution. Phase 132 is scoped
to the four existing action families; it must not grow an unbounded scripting
language or invent new scenario events while repairing them.

### Required proof

- Replace the string-plus-bag payload with a strict discriminated union for
  HBIED detonation, WP fire-zone creation, unit relocation, and casualty
  application. Reject malformed values, unknown targets, missing owner
  topology, duplicate schedule identity, and noncanonical ordering before
  runtime publication.
- Route relocation and casualties through authoritative production lifecycle
  owners. A due action must commit its complete effect and receipt once or fail
  explicitly without being marked complete; no missing owner/target or caught
  exception may become a successful no-op.
- Persist and validate schedule identity, action ordinals, dispositions,
  logical due/commit time, and effect evidence. Prove exact pending and
  post-commit continuation in fresh and in-place runtimes, including failure
  rollback and retry policy, without a duplicate effect.
- Exercise all four families through the public scenario runtime far enough to
  observe authoritative outcome changes and recorder/evaluator/API lifecycle
  evidence. Direct private dispatch, constructor/load success, source search,
  a log line, or membership in a fired set is not behavioral proof.

### Evidence-matrix rationale

- `D`, `L`, and `W` are **Yes** only for the existing generic declaration,
  loader list, and engine tick hook; they do not satisfy the typed-effect
  contract.
- `E` is **N/A** because integrity of an authored due action is mandatory, not
  an optional feature mode.
- `X`, `O`, and `P` remain unproven: the current production regression never
  reaches an authored action, no authoritative effect comparison exists, and
  exact-once lifecycle state is neither checkpointed nor publicly exposed.

**Status:** Queued for Phase 132 in Block 16. Phase 115 records the production
red and truthful nonclaim but does not implement or close scripted actions.

## REM-046 - Active deception state is not checkpoint-complete

### Phase 116 finding and nonclaim

`FogOfWarManager` owns a live `DeceptionEngine`, and the production battle path
can deploy, count, and degrade decoys. The current `Decoy.get_state()` payload,
however, omits its `SignatureProfile`; restore constructs an empty substitute
signature. `DeceptionEngine.get_state()` also serializes a duplicate DETECTION
RNG mirror while `RNGManager` is the authoritative stream owner. Nesting that
existing dictionary inside format 116 would therefore accept semantically
incomplete decoys and a commit-order RNG authority instead of exact state.

Phase 116 implements roster-backed ordinary-contact continuation while failing closed:
checkpoint capture rejects active or inactive retained decoys and a nonzero
decoy counter, and restore requires the target deception owner to be pristine.
Those guards prove the unsupported boundary; they do not persist deception or
claim that every deployed decoy is wired into normal fog-of-war scans.
Custom or populated common-operating-picture/data-link state remains the
separate REM-036 boundary.

**Matrix:** `D=Yes, L=Yes, W=Yes, E=-, X=Yes, O=Yes, P=-`. Typed decoys and the
runtime owner establish declaration/loading/wiring. The production battle path
and Phase 116 non-pristine capture/restore controls establish exercised and
outcome-relevant state. Paired enabled/disabled behavior and complete exact
persistence/exposure remain unproven.

### Required proof

- Persist and strictly validate canonical decoy IDs, monotonic counter,
  positions, types, complete immutable signature profiles, effectiveness,
  degradation, active disposition, deployment time, and every behavior-bearing
  field; do not reconstruct an empty proxy signature.
- Keep `RNGManager` as the single DETECTION authority and cross-validate any
  required mirror before mutation. Stage the full owner transaction so corrupt,
  foreign, or mutated state leaves clock, RNG, FOW, fusion, targeting, recorder,
  and decoys unchanged and permits a valid retry.
- Prove production deployment, degradation/inactivation, assessment effects,
  any supported decoy/contact association, next-ID allocation, and enabled /
  disabled controls across fresh and in-place continuation.
- Either prove active decoys reach normal production fog-of-war scans and alter
  detection/contact outcomes, or retain that wiring as an explicit unsupported
  boundary. Direct helper calls, state-key searches, constructor ownership,
  mocks, logs, and no-crash runs are not behavioral completion evidence.

**Status:** Queued for Phase 133 in Block 17. This follow-up was surfaced while
Phase 116 repaired ordinary contacts and does not reopen REM-029.

## REM-047 - 73 Easting misses the source-synchronous engagement signature

### Phase 117 finding and nonclaim

The corrected Phase 117 study observes the shipped 73 Easting scenario at the
source's 1,380-second Eagle Troop boundary across held-out seeds 11700 through
11719. All 20 production runs recorded zero destroyed scoped Iraqi tanks
against the exact 28-tank range and zero destroyed scoped Iraqi personnel
carriers against the exact 16-carrier range. All 20 retained the
source-consistent zero destroyed American vehicles and reached the study
cutoff without a natural terminal result. The complete joint outcome therefore
succeeded in 0/20 runs, with an exact lower confidence bound of 0.0; the
diagnostic terminal labels were 16 draws and four red wins.

This persisted `FAIL` is valid evidence that the current authored scenario and
production behavior do not reproduce the frozen source-scoped signature. It
does not identify the first causal defect, prove that one subsystem is solely
responsible, or authorize post-result changes to the study. Phase 117 closed
REM-030 by publishing this truthful unsupported classification and retaining
the complete failure artifact. REM-047 is a separate fidelity remediation and
does not require Phase 117 to manufacture a passing historical claim.

**Matrix:** `D=Yes, L=Yes, W=Yes, E=N/A, X=Yes, O=Yes, P=Yes`. These entries
describe the strict study declaration, loaded production scenario, exercised
detection-to-terminal path, observable miss, and persisted failure evidence;
they do not assert that the missing source-synchronous fidelity is correct.
`E` is N/A because causal integrity and fidelity are not an optional runtime
toggle.

### Required proof

- Record a deterministic, source-synchronous causal trace from deployment and
  visibility through detection, contact/fusion, targeting and fire-control,
  movement/standoff, engagement, hit/damage, authoritative destruction, and
  victory/termination. Identify the first unsupported or incorrect transition
  before changing production behavior.
- Distinguish scenario-scope or force-representation errors from detection,
  targeting, engagement/effects, destruction-accounting, and event-boundary
  defects. Correct only source- and model-backed causes through their
  authoritative production owners; a proxy event, scripted casualty, or
  validation-only override is not a repair.
- Preserve the frozen 20-seed interval; separate exact loss gates for 28 Iraqi
  tanks, 16 Iraqi personnel carriers, and zero American scoped vehicles; the
  exact 1,380-second natural-duration gate; observation semantics; and the
  joint acceptance rule. Do not recombine the Iraqi components, widen a
  casualty or duration range, select favorable seeds, relax right-censoring,
  change a victory threshold merely to hit 23 minutes, or tune physical weapon,
  sensor, morale, or damage parameters to force agreement.
- Make any natural action boundary arise from typed production objectives and
  state transitions with authoritative logical time. An unconditional timer,
  fabricated terminal cause, or study-cutoff relabel is not a natural result.
- Prove realistic enabled/disabled or causal negative controls where
  applicable, exact same-seed replay, and fresh/in-place continuation for every
  changed state owner. Re-run affected catalog scenarios and explain every
  semantic delta rather than treating a 73 Easting match as permission for
  unrelated regressions.
- Re-run the unchanged frozen study through `SimulationRuntimeFactory` and
  retain complete receipts and a reload-validated artifact. REM-047 closes
  only with a production-causal result satisfying the complete frozen joint
  gate and all applicable phase reviews; if the investigation instead finds an
  unrepresentable or differently scoped historical claim, retain or split the
  numbered deficit rather than redefining success.

**Status:** Queued for Phase 134 in Block 18. A future pass of this reused-source
study would not by itself promote the claim to `production_validated`; Phase
117's independence and intended-use restrictions remain in force.

## REM-048 - Packaged accepted evidence lacks a no-Git attestation boundary

### Phase 117 finding and current safe behavior

The repository `HistoricalClaimLedgerLoader` verifies accepted evidence by
checking Git ancestry, reading the execution ledger at the artifact's commit,
checking code/dependency drift, reloading the committed plan, and freshly
preparing the production scenario. The production Docker image intentionally
contains neither `.git` nor `docs/`; accepted artifacts are currently retained
under `docs/evidence/`. Therefore a future nonempty `accepted_evidence` entry
cannot pass the same loader inside that image.

The Phase 117 local packaged-loader control remains truthful and useful: the
current ledger has zero `production_validated` claims, so the packaged loader
audits every scenario claim it can publish and exposes 73 Easting as
unsupported with current-engine regression evidence. A hosted no-`.git` image
smoke is configured. The Phase 117 push prerequisite is satisfied at
`84cf4c4`, but no successful hosted result is recorded in the repository, so
that smoke remains unverified pending a successful workflow run. Neither the
local control nor that zero-accepted smoke exercises or establishes packaged
accepted-evidence support. Silently bypassing Git verification,
copying an artifact without an attestation, or treating the build's source
revision string as the entire proof would weaken the repository contract.

**Matrix:** `D=Yes, L=Yes, W=Yes, E=N/A, X=-, O=Yes, P=-`. The accepted
reference and verification schemas are declared, loaded, and reached by the
packaged API, and the missing Git/evidence boundary fails closed observably.
Real nonempty package execution and durable package-bound proof are absent.
`E` is N/A because accepted evidence is a disposition, not a runtime feature
toggle.

### Required proof

- At image build time, run the complete repository/Git accepted-evidence
  verification before `.git` is discarded. Produce a strict canonical receipt
  that binds the accepted claims to the exact source revision and source
  manifest, execution and current ledgers, plans, artifacts, source
  references, metric bindings, and production-input identities.
- Package every evidence input required for independent runtime verification
  at one canonical non-documentation boundary. Reject aliases, symlinks,
  missing or extra files, digest drift, wrong revisions, stale receipts, and a
  receipt copied from another image.
- Keep repository and packaged verification semantically equivalent. A
  no-`.git` runtime may verify the build-time receipt, but may not skip ancestry
  or committed-content proof unless that proof is explicitly represented and
  bound by the receipt.
- Prove fail-closed tamper controls for the source manifest/revision, ledger and
  claim content, plan, artifact, source bindings, receipt, and API data-root
  identity.
- Exercise a genuine clean, independently predeclared, source-backed
  production `PASS` through repository acceptance, image construction, and a
  real no-`.git` API response with the identical claim-level disposition.
  Synthetic fixtures remain useful negative controls but cannot alone close
  the production capability claim.

**Status:** Queued for Phase 135 in Block 19. It does not reopen REM-030:
Phase 117's catalog has no accepted claims and its packaged zero-accepted path
fails closed correctly.

## REM-049 - Web UI replay, export, editor, and analysis semantics are incomplete

### Phase 117 finding and bounded corrections

Phase 117's exhaustive cross-document audit found production UI behavior that
did not match the public guide. The phase corrects the bounded data-integrity
failures immediately: API/list/detail/editor code now uses canonical
`school_config`, `base_elevation_m`, and `visibility_m`; both scenario badge
surfaces retain all six typed flags; run submission reaches the returned run;
the terrain editor offers only the five production `TerrainConfig` values;
the map decodes the exact five `UnitStatus` integers and treats only status 2
as destroyed; and one-click Space creation fails explicitly instead of
inventing a semantically unrelated constellation proxy. The late closure audit
also found that school and commander selectors wrote ignored or rejected proxy
fields. Phase 117 makes `school_config` strict, removes the two shipped
empty-registry proxy declarations, and disables both selectors with explicit
unsupported guidance rather than presenting incomplete catalogs as runnable.

The remaining surface is broader than the Phase 117 historical-evidence
contract. Chart clicks write `?tick`, but the map does not consume it and tab
changes discard it. Engagement arcs use an absolute ten-tick window and can
appear before their event. Event CSV export reads at most the first 10,000
events even though the server can retain 50,000. Selected-unit state is a
stale captured object rather than a derivation from the current frame. A
fullscreen route and keyboard shortcuts exist without the documented
affordances. Analysis panels hard-code parts of seed, metric, alpha, or policy
topology rather than exposing the broader controls previously described. The
Phase 117 guide states these limits instead of calling them complete. FOW
authorization and complete side filtering remain separately owned by REM-041.

**Matrix:** `D=Yes, L=Yes, W=-, E=N/A, X=Yes, O=Yes, P=-`. Current typed API
and UI models load and expose enough production state to reproduce the defects
and show their visible consequences. End-to-end semantic wiring and durable
complete export/replay evidence are not present. `E` is N/A because this is an
integrity boundary, not an optional fidelity switch.

### Required proof

- Define one replay cursor contract across stored ticks, interpolated display
  frames, URL state, charts, embedded map, and the fullscreen route. Consume
  incoming cursor state, preserve it across tab changes, and prevent future
  events from rendering before their logical time.
- Export every retained event through bounded pagination/streaming with an
  explicit schema, stable order, count receipt, and truncation failure rather
  than silently calling a prefix complete.
- Derive selected-unit and overlay state from the current authorized frame;
  prove status, trails, arcs, sensor/sidebar data, and hide/show controls stay
  semantically correct through replay and interpolation. REM-041 remains the
  authorization owner for opposing-player views.
- Add catalog-backed Space selection (including ownership and exact
  constellation IDs) before re-enabling one-click creation. Reject unsupported
  subsystem defaults rather than emitting schema-valid or invalid proxies.
- Add a complete era-aware commander catalog and a production-owned exact-unit
  or typed side-policy doctrine editor. Preserve all-side commander validity,
  bind each selection to the canonical source/runtime field, and prove the
  resulting initial and arriving assignment provenance. Do not reintroduce
  `side_defaults`, `{side}_school`, or another proxy authority.
- Either expose the analysis inputs the UI claims to compare or label and bind
  every fixed seed, metric, alpha, assignment, and policy choice in requests,
  results, and reproduction evidence.
- Prove the real API/browser production paths with focused behavioral tests,
  full frontend lint/typecheck/tests, and exact cross-document review.

**Status:** Queued for Phase 136 in Block 19. Phase 117 fixes the bounded
status/schema/navigation defects and public nonclaims; it does not claim this
larger replay/export/editor/analysis capability complete.

## REM-050 - Escalation and DEW scenario configuration is not behaviorally authoritative

### Phase 117 finding and bounded correction

The postmortem audit compared authored optional-suite data with the loaded
runtime. `_create_escalation_engines(..., esc_cfg)` receives but never reads
`esc_cfg`: Taiwan's authored thresholds, hysteresis `0.65`, and 14,400-second
cooldown load as the ladder defaults, including hysteresis `0.7` and a
3,600-second cooldown. Srebrenica's 1,800-second and Hybrid Gray Zone's
7,200-second cooldowns likewise become 3,600 seconds. Those values are loaded
source data, not wired behavior.

DEW is presence-enabled. Taiwan was the only catalog scenario with
`dew_config`, but its `enable_dew` key was ignored by `DEWConfig`; the non-null
block merely constructed a default engine. No Taiwan unit carries a DEW
weapon, while the benchmark scenario that carries a DEW-capable unit has no
`dew_config`, so scenario presence does not prove a production DEW engagement.

Phase 117 removes the editor's ignored `enable_escalation`/`enable_dew`
markers, removes Taiwan's ignored `enable_dew` key, and documents the current
presence/default behavior. It does not invent tuning semantics or a proxy DEW
platform late in a historical-evidence phase.

**Matrix:** `D=-, L=Yes, W=-, E=-, X=Yes, O=-, P=-`. Escalation mappings and
DEW presence are loaded and their divergence is reproducible, but the authored
escalation values are not a typed runtime authority and no configured catalog
scenario proves a DEW-caused outcome. Exposure of block presence is not
behavioral configuration evidence.

### Required proof

- Define strict typed source models for Escalation and DEW, reject unknown or
  enable-like proxy fields, and state one unambiguous absent/disabled/enabled
  contract.
- Feed every supported escalation field into the production ladder and related
  engines at construction; prove at least two distinct valid configurations
  produce the declared runtime state and an observable difference.
- Add a defensible catalog scenario or fixture with both a typed DEW config and
  a real DEW-capable unit/loadout. Exercise a production engagement, event,
  resource/cooldown state, and enabled/disabled control without proxy units.
- Preserve exact configuration and live suite state across API execution,
  provenance, checkpoint continuation, and scenario evaluation. Reject dead
  authored fields in data validation.

**Status:** Queued for Phase 137 in Block 19. REM-049 owns editor/catalog UX;
REM-050 owns the production runtime and scenario-data authority those controls
must eventually target.

## REM-051 - Battle resolution resets unrelated detection scan history

### Phase 118 finding

`SimulationEngine` currently resolves a completed battle and then reaches
through `SimulationContext.fog_of_war` to the shared detection engine's private
scan-count reset. That reset is global rather than scoped to the resolved
battle, reporting side, observer, sensor, or target identity. In a context with
multiple concurrent battles, resolving one battle can therefore erase the
integration-gain history still owned by another battle. Phase 118 does not
paper over that lifecycle defect while replacing the FOW update transaction.

**Matrix:** `D=Yes, L=Yes, W=Yes, E=N/A, X=Yes, O=Yes, P=-`. Scan history and
the reset path exist and are reached by production battle resolution; a scoped
persisted lifecycle owner and multi-battle continuation proof are absent.

### Required proof

- Define one typed owner for scan-history creation, update, expiration, and
  removal, keyed by the complete semantic detection identity.
- Route battle resolution through an explicit scoped lifecycle operation; do
  not reach through FOW to a private global reset.
- Prove resolving one of two concurrent battles cannot alter the other
  battle's integration gain, detections, RNG transcript, or event outcome.
- Preserve the exact scoped history through fresh and in-place checkpoint
  continuation, battle split/merge/termination, and absent/stale identities.

**Status:** Queued for Phase 138 in Block 20.

## REM-052 - Fog-of-war update algorithms have duplicate owners

### Phase 118 finding

The receipt-bearing production route stages each side through
`FogOfWarManager.update_with_receipt()`, but the older public `update()` method
still contains a second implementation of detection selection, scan cadence,
randomness, track fusion, and world-view publication. Keeping both algorithms
invites semantic drift and permits future callers to bypass the transactional
receipt/indexed-RNG boundary. Phase 118 validates the new production route but
does not claim that duplicated legacy behavior is a second supported owner.

**Matrix:** `D=Yes, L=Yes, W=-, E=N/A, X=Yes, O=Yes, P=-`. Both entry points
are declared and the legacy path is directly exercisable; one canonical
implementation or an explicit unsupported adapter contract is absent.

### Required proof

- Choose one typed implementation owner for detection, cadence, culling,
  indexed randomness, fusion, mutation, and receipts.
- Make every supported caller use that owner, or make the legacy boundary fail
  explicitly with migration guidance; do not preserve a silent proxy path.
- Prove supported-call parity, failure atomicity, deterministic ordering, RNG
  authority, and checkpoint continuation with realistic side/contact state.
- Remove tests that award behavioral credit to the duplicate algorithm after
  the canonical boundary is established.

**Status:** Queued for Phase 139 in Block 20.

## REM-053 - Checkpoint capture repeatedly restages mutable FOW state

### Phase 118 finding

The format-118 checkpoint boundary validates active/poisoned FOW and indexed
RNG state strictly, but its preflight and final capture paths repeatedly call
serialization/restaging for the same mutable owners. Repeated capture expands
the consistency surface and adds avoidable work before the authoritative
snapshot is emitted. It is not a semantic failure in the accepted format-118
bytes, so Phase 118 records it separately instead of weakening the checkpoint
gate or calling an unmeasured refactor a speed improvement.

**Matrix:** `D=Yes, L=Yes, W=Yes, E=N/A, X=Yes, O=Yes, P=-`. The repeated
production captures and resulting bytes are observable; a single immutable
snapshot graph and dedicated profile evidence are absent.

### Required proof

- Capture FOW, detection, conventional/indexed RNG, and dependent receipt state
  once into an immutable typed snapshot used by validation and encoding.
- Reject active, poisoned, incomplete, or mutually inconsistent owners before
  publishing any bytes, without recapturing a changed live state.
- Prove byte-stable fresh/in-place continuation and exact failure atomicity
  across ordinary contacts, active allocations, legacy completeness, and
  receipt/transcript topology.
- Measure the production checkpoint path separately before and after; keep
  timing evidence distinct from correctness evidence.

**Status:** Queued for Phase 140 in Block 20.

## REM-054 - Performance approximations failed frozen semantic validation

### Phase 118 finding and current boundary

The complete schema-2 v7 study is valid negative evidence. Native scan
scheduling passed only 3/16 paired cases and failed 13/16, including one
deterministic winner reversal. The Suwalki sensing-only LOD case passed 12/16
and failed 4/16 on its predeclared covariance limit even though all three
complete-case recovery-work checks passed. Exact repeats, resumed attempts,
checkpoint projections, indexed detection decisions, branch receipts, shard
topology, and independent manifest reload rule out missing evidence or an
execution-order artifact.

The scan result primarily reflects first-acquisition latency, fewer temporal
measurements, valid current-witness/deferred-support asymmetry, sequential
combat-RNG amplification after a real cadence delta, and a position-sensitive
ordered-event metric. The four LOD misses share one causal pattern: unarmed
EA-18G ESM observers make only the first period-five observation and are
destroyed before the next due scan, leaving a high-covariance tentative
contact. Those effects are not authority to widen a budget or tune a sensor.
Phase 118 therefore preserves both flags as model-fidelity approximations but
sets their production support disposition to
`unsupported_failed_semantic_validation` and rejects positive activation and
non-default LOD tuning explicitly.

**Matrix:** `D=Yes, L=Yes, W=Yes, E=N/A, X=Yes, O=Yes, P=Yes`. The failed
controls, causal deltas, strict production rejection, immutable archive, and
public status are declared, loaded, wired, exercised, observable, and
persisted/exposed. Positive enablement is intentionally N/A until this
remediation succeeds.

### Required proof

- Begin from the current production red: scenario YAML, API run/analysis,
  runtime factory, manual context/manager, receipt, and checkpoint boundaries
  must continue to reject each unsupported positive or non-default input.
- Specify and source a revised model before implementation. Resolve or bound
  tentative-track initiation/aging, native-ready miss versus deferred support,
  sensing-aware witness promotion, event alignment, and REM-044's sourced
  sensor-specific range/bearing/correlation covariance and provenance.
- Freeze a new plan/schema identity and fresh input set disjoint from every
  burned v3--v7 seed before execution. Preserve exact source, branch, attempt,
  deadline, pair-union, checkpoint, RNG, and publication obligations.
- Prove every supported input boundary, disabled control, branch exercise,
  outcome effect, deterministic repeat, fresh-runtime continuation, API status,
  and artifact reload through production owners. A mock, constructor call,
  source search, receipt-only delta, or no-crash run is insufficient.
- Do not widen a threshold, delete a failed pair, change combat/catalog/scenario
  inputs, reinterpret the terminal v7 result, or calibrate physical values to
  force acceptance. Re-enablement requires an accepted new artifact and the
  full numbered-phase documentation/postmortem/commit sequence.

**Status:** Queued for Phase 141 in Block 21. Creating this follow-up does not
start Phase 141 or weaken Phase 118's explicit-unsupported current boundary.

## REM-055 - Transactional FOW integrity adds material production runtime cost

### Phase 118 finding and current boundary

The required `$profile` route compared the Phase 118 start revision
`84cf4c4461a7d4a9f17c2578ea323a0a21d5bbe8` with the final simulation tree on
the same production `SimulationRuntimeFactory` workload: `benchmark_battalion`,
seed 42, ten ticks, strict mode, event recording, detection culling/SoA/parallel
detection enabled, and scan scheduling/LOD disabled. After one discarded
warm-up per revision, the phase-start median was 47.035449 seconds across
46.974269--47.341247 seconds; the Phase 118 median was 59.220597 seconds across
58.758202--59.259692 seconds. The ratio is 1.259063 (+12.185148 seconds,
+25.906%), while both revisions produced the identical ten-tick, 50-second,
blue `max_ticks` result.

One matched cProfile run recorded 436,345,008 calls and 116.744514 seconds in
the phase-start `SimulationEngine.run()` versus 497,301,086 calls and
138.727831 seconds in the Phase 118 tree. The enclosing
`BattleManager._update_interval_fog_of_war()` cumulative cost grew from
5.794983 to 23.733829 seconds: 17.938846 seconds, or 81.60% of the instrumented
run delta. Its overlapping descendants include repeated deep copies, canonical
plan/cadence/scan-count serialization and hashing, scan-count restaging,
atomic fusion preparation, indexed-RNG issuance, observer-support lookup,
spatial queries, and per-interval worker lifecycle. Cumulative descendants
overlap and are hypotheses for isolation, not additive savings estimates.

These costs protect real Phase 118 guarantees: all-side failure atomicity,
schedule-independent stochastic identity, content-bound tamper detection,
correlation-safe fusion, exact receipts, and checkpoint continuation. Removing
those checks to recover time would reopen REM-031. The frozen Phase 118
contract declared no speed threshold, every semantic deadline completed, and
the profile supports no universal throughput or speed claim. The regression is
therefore tracked separately rather than hidden or used to relabel the valid
semantic evidence.

**Matrix:** `D=Yes, L=Yes, W=Yes, E=N/A, X=Yes, O=Yes, P=-`. The production
cost is declared, loaded, wired, exercised, and outcome-measured. Enable/disable
behavior is not applicable to a runtime-cost defect. A persistent accepted
before/after optimization receipt does not yet exist.

### Required proof

- Freeze the production target, source identities, environment, warm-up and
  repetition policy, semantic projection, peak-memory measurement, and an
  owner-approved performance threshold before changing the hot path.
- Isolate deep-copy, fingerprint/serialization, scan-state staging,
  correlation-safe fusion, indexed RNG, spatial-query, and worker-lifecycle
  costs. Do not add cumulative profile descendants or infer savings from code
  shape.
- Remove only redundant work. Preserve atomic publication, mutation/tamper
  rejection, indexed transcript identity, canonical ordering, observer-support
  semantics, exact receipts, and checkpoint continuation.
- Prove identical ordered events, final state, exposed receipts, stochastic
  authority, and fresh-runtime continuation on the matched workload, then run
  the applicable scenario, determinism, slow, benchmark, data, convention,
  simplify, documentation, and postmortem gates.
- Persist reproducible before/after timing distributions, call profiles,
  memory results, source/environment identities, exclusions, and residual
  uncertainty. Do not call a shared-host or single-workload result a universal
  speedup.

**Status:** Queued for Phase 142 in Block 21. Phase 142 has not started, and
this follow-up does not weaken Phase 118's qualified-negative semantic closure.
