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
| REM-002 | P0 | 106 | API execution | `config_overrides` are merged for validation but the run reloads the unchanged scenario file | Queued | Yes | - | - | N/A | - | - | - | API run with an outcome-affecting override |
| REM-003 | P0 | 106 | API lifecycle | Background run teardown can use a closed database session | Queued | Yes | N/A | Yes | N/A | - | - | - | API task lifecycle regression without teardown exceptions |
| REM-004 | P0 | 107 | Reinforcements | Scenario reinforcements are not registered automatically with `CampaignManager` | Queued | Yes | Yes | - | N/A | - | - | - | Production engine arrival test |
| REM-005 | P0 | 107 | Reinforcements | Arriving units do not receive their defined weapons and sensors | Queued | Yes | Yes | - | N/A | - | - | - | Armed reinforcement participates after arrival |
| REM-006 | P1 | 107 | Morale | Side `morale_initial` is ignored; all units start steady | Queued | Yes | Yes | - | N/A | - | - | - | Contrasting scenario initialization test |
| REM-007 | P1 | 107 | Feature gates | Scenario `disabled_modules` is loaded but does not disable runtime modules | Queued | Yes | Yes | - | - | - | - | - | Enabled/disabled production controls |
| REM-008 | P0 | 108 | Logistics | Scenario depots do not initialize stock or a supply network | Queued | Yes | Yes | - | N/A | - | - | - | Depot-backed resupply through production loop |
| REM-009 | P0 | 108 | Logistics | Supply-network updates and idle consumption are not applied by the production loop | Queued | Yes | Yes | - | N/A | - | - | - | Controlled inventory delta over engine ticks |
| REM-010 | P0 | 109 | Equipment data | Duplicate weapon-map keys silently replace AIM-7M and CSRL mappings with unrelated weapons | Queued | Yes | Yes | Yes | N/A | - | - | - | Unique semantic mapping validation and Ruff |
| REM-011 | P1 | 110 | Space combat | The production ASAT hook is an explicit placeholder | Queued | Yes | Yes | - | - | - | - | - | Enabled/disabled satellite outcome test |
| REM-012 | P1 | 111 | Indirect fire | Time-on-target uses dummy coordinates, has no executed state, and has no production caller | Queued | Yes | Yes | - | - | - | - | - | Scheduled mission executes once at its real target |
| REM-013 | P1 | 112 | Validation trust | Default CI excludes API, E2E, slow, terrain, and benchmark suites without making the gap prominent | Queued | Yes | N/A | Yes | N/A | - | N/A | N/A | CI jobs and documented coverage boundaries |
| REM-014 | P1 | 112 | Test quality | Structural and no-assert tests can support false completion claims | Queued | Yes | N/A | Yes | N/A | - | - | N/A | Audit critical contracts and add behavioral assertions |
| REM-015 | P2 | 112 | Documentation | Strict documentation build was not part of the verified baseline | **Closed early** | Yes | N/A | Yes | N/A | Yes | N/A | N/A | [Phase 105 verification](devlog/phase-105.md#final-broader-verification) |
| REM-016 | P1 | TBD | Aggregation | Disaggregation recreates every constituent as base `Unit` and does not restore captured weapon, sensor, or supply attachments | Queued | Yes | Yes | Yes | N/A | - | - | - | Subclass/loadout round trip across aggregation |
| REM-017 | P0 | 112 | Analysis tooling | Scenario batch helpers infer the wrong data root, can run with zero loaded units, and silently turn unsupported metrics into zero | Queued | Yes | - | Yes | N/A | Yes | Yes | N/A | Real-unit batch run, unknown-metric rejection, and outcome-affecting sweep/comparison |

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
- Dynamic reinforcement loadout construction remains REM-004/REM-005.
- Aggregation constituent reconstruction remains REM-016.

## REM-017 - Analysis tools can manufacture false-green results

### Reproduction

A one-iteration `run_sweep()` against
`data/scenarios/test_campaign/scenario.yaml` completed successfully while
logging that all ten scenario units were unknown. It returned zero destroyed
units for both sides instead of rejecting an invalid run.

### Cause

- `run_scenario_batch()` infers the loader root as
  `scenario_path.parent.parent`, which resolves to `data/scenarios` for the
  normal repository layout; `ScenarioLoader` requires `data`.
- The batch does not reject a scenario whose declared roster loads as zero
  units.
- `_extract_metrics()` returns `0.0` for unknown metrics.
- Existing sensitivity/comparison tests cover result structures and statistics,
  not real `run_sweep()`, `run_comparison()`, or production-loaded forces.

### Required proof

- Resolve or explicitly require the correct data root for every supported
  scenario layout.
- Reject missing declared units, empty invalid runs, and unsupported metric
  names.
- Exercise sensitivity and comparison through real `ScenarioLoader` and
  `SimulationEngine` runs.
- Show that a controlled override changes an intended metric and that invalid
  configuration cannot produce an authoritative-looking zero result.

Until REM-017 closes, `$calibrate`, `$compare`, and `$what-if` must preflight a
real loaded roster and stop rather than report unverified results.
