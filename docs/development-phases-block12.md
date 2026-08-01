# Block 12: Integrity Remediation

Block 12 converts the post-Phase-104 audit findings into verified production
behavior. It does not reopen every historical modeling choice. It repairs
specific claims where the declared, loaded, wired, exercised, outcome-affecting,
or persisted stages are missing.

The live issue inventory and evidence matrix are in
[`remediation-backlog.md`](remediation-backlog.md).

Block status: **Complete**. Phases 105 through 114 are complete. Phase 114
passed validation, documentation audit, cross-document audit, and postmortem;
its owner-approved performance qualification remains explicit and is not an
uncontended wall-clock-pass claim.

## Phase 105 - Checkpoint State Integrity

Status: **Complete** (reclosed 2026-07-28 after the Codex skill-port
postmortem and follow-up repair).

Restore the original Phase 72 behavioral contract.

- Restore exact unit roster, concrete class, ordering, mutable entity state,
  typed morale, and live weapon/sensor state.
- Preserve stable object references during in-place restore.
- Support fresh-runtime restoration without consuming RNG.
- Preserve compatible legacy checkpoints and reject corrupt state.
- Prove exact restoration and deterministic continuation through
  `SimulationEngine`.

Exit criteria: REM-001 has passing production-path behavioral evidence and no
unreported checkpoint limitation was introduced.

## Phase 106 - API Execution Integrity

Status: **Complete** (2026-07-28).

- Apply `config_overrides` to the scenario actually used by a run.
- Prove an override changes the intended production outcome.
- Make background task/database ownership safe through task completion and
  teardown.

Exit criteria: REM-002 and REM-003 are closed with API boundary tests.

Delivered behavior includes strict sparse calibration overlays, one effective
config shared by loader and API consumers, cooperative run/batch cancellation,
cancellation-safe lifespan teardown, serialized SQLite writes, and explicit
terminal persistence/notification. See
[`phase-106.md`](devlog/phase-106.md) for the red reproductions, deterministic
API A/B, scenario evaluation, and residual thread-executor boundary.

## Phase 107 - Scenario Configuration Wiring

Status: **Complete** (2026-07-28).

- Register scenario reinforcements automatically.
- Assign arriving units their defined weapons and sensors.
- Honor side initial morale.
- Make `disabled_modules` an effective, validated production gate.

Exit criteria: REM-004 through REM-007 have enabled, disabled, and
outcome-affecting controls where applicable.

Delivered behavior includes automatic all-resolution reinforcement scheduling,
atomic dynamic registration with live loadouts and typed side morale, strict
era/capability gates, deterministic logical-time events, and exact dynamic
checkpoint continuation. See
[`phase-107.md`](devlog/phase-107.md) for the production battle proof,
determinism audit, scenario evaluation, and residual boundaries.

## Phase 108 - Logistics Runtime Wiring

Status: **Complete** (2026-07-28).

- Initialize scenario depots, stock, nodes, and routes.
- Advance supply-network state from the production loop.
- Apply configured idle consumption at the correct simulation resolution.

Exit criteria: REM-008 and REM-009 show controlled inventory and resupply
effects through production ticks.

Delivered behavior includes a strict opt-in logistics schema, loader-owned
depot/unit/route topology, deterministic mass- and throughput-bounded direct
resupply, fixed-cadence idle consumption at every engine resolution, atomic
reinforcement admission, generic delivery-event exposure, and exact version
108 checkpoint continuation. Legacy depot-only scenarios remain inert. See
[`phase-108.md`](devlog/phase-108.md) for the production proof, determinism and
performance audits, scenario comparisons, and residual activity/live-store
boundaries.

## Phase 109 - Equipment Mapping Integrity

Status: **Complete** (2026-07-28).

- Remove duplicate-key overwrite behavior.
- Replace unrelated proxy mappings with semantically correct data or explicit
  unsupported errors.
- Move production loadout construction out of private validation-runner helpers
  and give the runtime one typed ownership boundary.
- Resolve the 22 currently unmapped catalog entries and explicitly classify the
  two no-sensor warnings.
- Add uniqueness and semantic validation for equipment lookup maps.

Exit criteria: REM-010 is closed and the relevant Ruff checks pass.

Delivered behavior includes an ordered typed registry, strict duplicate-key
YAML boundaries, one runtime-owned loadout builder for
initial/reinforcement/restore paths, complete built-in catalog coverage,
explicit sensor policy, semantic target/ammunition/domain checks, checkpointed
topology/fingerprint compatibility, and production-tested composite weapon
cadence. See
[`phase-109.md`](devlog/phase-109.md) for the red proofs, scenario outcomes,
validation counts, and residual trust items.

## Phase 110 - ASAT Production Integration

**Status: Complete.**

Replace the placeholder hook with a gated production path that uses real
satellite and weapon state and persists its effects.

Exit criteria: REM-011 has enabled/disabled controls and an observable satellite
outcome.

Delivered behavior includes strict typed constellation/weapon catalogs,
scenario-owned finite ASAT assets and exact-target orders, deterministic
logical-time execution, manager-owned satellite/debris transitions, same-tick
space-service effects, recorder/API exposure, and schema-110 whole-runtime
checkpoint continuation. Direct-ascent kinetic intercepts are the only
supported production ASAT type; co-orbital and laser definitions fail
explicitly. See
[`phase-110.md`](devlog/phase-110.md) for production controls, scenario rows,
validation counts, and accepted limits.

## Phase 111 - Time-on-Target Execution

Status: **Complete** (2026-07-29).

Carry real mission target and timing data into the indirect-fire engine, execute
each mission exactly once, and expose its result.

Exit criteria: REM-012 is closed with scheduled and negative controls through
the production loop.

Delivered behavior includes a strict nested scenario schema, one
runtime-loadout resolver for exact source attachments, fixed-cadence
battery-specific fire scheduling, live ammunition/cooldown/maintenance
mutation, exact target effects, reservation from ordinary battle selection,
typed terminal recorder/API events, and atomic schema-111 checkpoint
continuation. See [`phase-111.md`](devlog/phase-111.md) for production,
negative, deterministic, scenario, persistence, and accepted postmortem
evidence. REM-012 is closed.

## Phase 112 - Validation and Documentation Trust

Status: **Complete** (2026-07-30).

- Make excluded Python suites explicit in CI and developer documentation.
- Preserve and enforce the green repository-wide Python Ruff baseline that
  Phase 109 established after removing the six mapping-table duplicate-key
  errors and the two no-placeholder f-string findings.
- Audit critical structural/no-assert tests and replace false behavioral claims.
- Repair analysis batch loading and metric validation so sensitivity,
  comparison, and calibration cannot emit false-green zero results.
- Preserve the passing strict documentation baseline established during Phase
  105 and make its coverage routine.
- Repair historical devlog fragment links that the strict build currently
  reports only as informational diagnostics.
- Reject missing commander-profile references that currently warn per unit
  while the evaluator reports a successful scenario.
- Replace generic Space ISR report checkpoint dictionaries with a typed,
  semantically validated state/rehydration boundary.
- Validate crew-skill enums eagerly and stop historical force construction from
  treating arbitrary `KeyError` failures as absent unit definitions.
- Make scenario diagnostics distinguish legitimate corrected weapon-range
  standoff from truly stuck units.
- Reconcile hard wall-clock benchmark assertions with the authoritative stored
  baseline and declared hardware/repetition policy.
- Reconcile public capability and status claims with the remediation evidence.
- Replace catalog tests that call current winner rows historical validation
  with bounded, honestly named current-engine regression and repeatability
  evidence.
- Remove the unsupported Block 9 claim that one-sided authored-configuration
  runs prove performance-flag semantic preservation.

Exit criteria: REM-013, REM-014, REM-017, REM-022, REM-023, REM-024, REM-025,
REM-026, and REM-027 are closed, REM-015 remains green, all relevant suites are
reported explicitly, and the phase postmortem identifies any newly discovered
backlog items. REM-030 and REM-031 remain explicit Phase 117/118 follow-ups;
Phase 112 must record them and stop presenting current-engine regression as
historical validation or one-sided execution as performance-flag equivalence,
but it does not claim to close either deficit.

Local closure evidence audits an exact 11,752-node disjoint Python union:
`standard` 11,299 passed with 6 warnings, `slow-only` 109 passed with no
warnings, `benchmark-only` 60 passed with no warnings, `slow-benchmark` 4
passed with no warnings, API 239 passed with no warnings, and E2E 41 passed
with no warnings. The API result is qualified by this host's local uvloop
workaround and does not establish host-default behavior until remote
default-policy CI passes. The overlapping terrain dependency profile
separately passed 97 tests. See [`phase-112.md`](devlog/phase-112.md) for the
commands, warnings, exclusions, scenario outcomes, benchmark evidence, and
remaining limitations, and [`remediation-backlog.md`](remediation-backlog.md)
for the canonical issue transitions.

## Phase 113 - Morale State Ownership

Status: **Complete** (2026-08-01).

Replace the independently mutable context and state-machine morale stores with
one authoritative runtime path. Route transitions, rout cascades, aggregation,
dynamic registration, victory reads, and checkpointing through it.

The implementation now places immutable active records and suspended aggregate
archives behind one typed `MoraleRuntime`. Initial units and reinforcements,
stochastic and forced transitions, rally, cascades, aggregation, victory,
recorder/API projections, and format-113 checkpoint continuation use that
runtime-owned boundary; `RNGManager` is the sole MORALE-stream persistence
authority. The former guerrilla `blend_probability -> ROUTING` proxy has also
been replaced by an explicit pre-mutation unsupported error, with the actual
concealment lifecycle retained by REM-032/Phase 119.

Focused production-path, deterministic-replay, checkpoint, scenario, and
benchmark-policy evidence is recorded in
[`phase-113.md`](devlog/phase-113.md). The exact 11,824-node union has passed
with zero failures/errors/skips and six declared warnings; local API/E2E plus
one FastMCP standard node use an explicit uvloop qualification, with hosted CI
as the authoritative default-policy control. The corrected documentation audit
and phase postmortem passed. The post-commit clean-tree benchmark verifier
binds the accepted comparison to the final phase commit as documented in the
devlog. REM-019 is closed.

Exit criteria: REM-019 is closed with exact transition, cascade, aggregation,
and checkpoint-continuation evidence.

## Phase 114 - Era Override Execution

Status: **Complete**.

Define the supported physics and tick-resolution override keys, reject unknown
metadata, and apply each supported value at the production construction
boundary.

The implemented boundary resolves one frozen effective `EraRuntimeContract`
before RNG and runtime construction. It supports strict sparse strategic,
operational, and tactical cadence plus minor/serious/critical treatment and
maintenance repair durations; unsupported C2 and nuclear declarations reject.
The same contract constructs the clock and domain configs, determines API
frame cadence, participates in runtime fingerprints, and persists in exact
checkpoint format 114. One cadence is bound to each complete interval, and
maintenance now has one all-resolution update owner. Built-in era presets omit
the prior unsourced physics numbers.

Focused production, API, deterministic/checkpoint, full-data, 46-scenario,
and exact 11,903-node partition evidence is recorded in
[`phase-114.md`](devlog/phase-114.md). Documentation audit, cross-document
audit, and postmortem pass. The owner accepted the dispersed timing evidence
only with an explicit contention qualification and deferred uncontended
confirmation until all cores are free; no clean wall-clock pass is claimed.
Newly exposed production prerequisites have explicit Block 13 remediation
assignments rather than proxy implementations. REM-018 is closed.

Exit criteria: REM-018 is closed with enabled/omitted controls that change the
intended production clock or engine behavior and persist exactly.
