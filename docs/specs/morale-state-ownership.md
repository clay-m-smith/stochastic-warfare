# Morale State Ownership Contract

## Status

Verified Phase 113 production contract. The corrected documentation audit and
[Phase 113 postmortem](../devlog/phase-113.md#postmortem) passed on 2026-08-01;
Phase 113 is complete and REM-019 is closed.

Phase 114 extended the engine checkpoint to format 114 by adding the effective
era runtime contract and clock/resolution validation. Phase 115 advances the
checkpoint to format 115 for tactical-targeting state, and Phase 116 advanced
it to format 116 for fog-of-war contact continuation. Phase 118's current
format 118 adds performance receipts, cadence state, observer topology, and
indexed FOW randomness. None of those changes alters or duplicates the morale
envelope below: current format 118 still
contains exactly one `morale_runtime`, and `RNGManager` remains the sole
MORALE-stream owner.

## Purpose and scope

Phase 113 closes REM-019 by replacing the independent mutable
morale copies in `SimulationContext` and `MoraleStateMachine` with one
runtime-owned semantic boundary. Every production morale mutation must update
the authoritative record, unit status, applicable rout state, events, public
projections, and checkpoint state as one ordered operation.

This contract covers initial and dynamic registration, stochastic transitions,
rally, melee rout, rout cascade, aggregation and disaggregation, victory and
API projections, deterministic continuation, and versionless checkpoint
migration. It does not claim the general aggregate-unit reconstruction or
attachment propagation work retained by REM-016.

The ownership audit also found that Phase 68 treated populated-area guerrilla
`blend_probability` as a COMBAT-stream chance to write
`UnitStatus.ROUTING` without a morale transition. Concealment by blending
into a population is not morale collapse, so Phase 113 must not preserve that
proxy through `MoraleRuntime` or silently discard it. A positive value reaching
the battle guard is an explicit unsupported error before retreat, status,
morale, event, or RNG mutation; deterministic retreat remains supported when
the result is zero. The current factory context cannot derive a populated-area
result because its `population_manager` has no matching density query, so the
positive test is a direct fail-closed fault detector rather than production
capability evidence. REM-032 owns the separate population-query, concealment,
targetability, lifecycle, persistence, and exposure model.

No military probability, transition matrix, or morale parameter changes in
this phase. Aggregate archive policy and corrupt-state rejection are integrity
rules, not new combat models.

## Ownership model

1. `SimulationContext` exposes exactly one public `MoraleRuntime`. The runtime
   privately composes a `MoraleStateStore` for state and a
   `MoraleStateMachine` for stochastic transition behavior. The state machine
   does not own current unit state.
2. The store owns every active `MoraleStateRecord` and every suspended
   aggregation archive. Callers cannot mutate the store, state machine, or
   records directly. `SimulationContext.morale_states` remains a stable,
   read-only compatibility view derived from the runtime.
3. A morale record is an immutable typed value containing:
   - `current_state: MoraleState`;
   - `last_transition_time_s: float | None`;
   - `last_check_time_s: float | None`; and
   - `generation: int`.
4. `None` means that no transition or admitted stochastic check has occurred.
   Times are finite, non-negative, no later than checkpoint elapsed time, and a
   transition time cannot exceed the last-check time. Generation is a
   non-boolean integer greater than or equal to zero.
5. The validated `MoraleConfig.transition_cooldown_s` is the sole cooldown
   setting. Records do not duplicate configuration.
6. Canonical snapshots and checkpoint entries use lexicographically sorted
   unit IDs. Insertion order is not semantic. Existing engagement target,
   rally selection, and cascade selection retain their own documented
   canonical ordering.

## Registration and lifecycle

1. Registration accepts an ordered sequence of immutable
   `MoraleRegistration` values. Empty IDs, duplicate IDs within the request,
   already active IDs, suspended constituent IDs, unknown units, invalid
   initial states, or incompatible statuses fail before mutation.
2. Initial scenario units and reinforcements register through the same runtime
   boundary. Reinforcement registration participates in the existing wave
   transaction: a later failure restores roster, loadouts, morale records,
   statuses, wave state, and stable owner/view identities in place.
3. A production `ScenarioLoader` runtime with a non-empty roster requires a
   morale runtime whose active IDs exactly match the simulated active morale
   topology. Deliberately minimal direct contexts may omit the runtime and
   expose an empty immutable compatibility view, but they gain no mutation
   path by doing so.
4. Runtime, store, compatibility-view, state-machine, and injected generator
   identities remain stable for the life of the context and across in-place
   checkpoint restore.

## Transition transaction

Every public transition uses the runtime coordinator and follows this order:

1. Resolve and prevalidate unit ownership, current record, unit status,
   transition cause, logical time, and any applicable rout plan before an RNG
   draw.
2. Capture the authoritative MORALE generator state.
3. For an admitted stochastic check, derive elapsed `dt` from the record and
   consume exactly one MORALE-stream draw through the state machine.
4. Commit the new record, status, and applicable rout removal before notifying
   observers. If an unexpected internal failure occurs before the first
   notification, roll back those owners and the generator in place. A retry
   therefore starts from the identical semantic and RNG state.
5. Publish the ordered events with collecting dispatch, then surface a grouped
   subscriber failure. A subscriber failure cannot roll back already visible
   state or rewind the consumed RNG draw.

The runtime uses the following typed causes and transition rules:

| Cause | Allowed transition |
|---|---|
| `STOCHASTIC` | Existing adjacent-state stochastic transition matrix |
| `RALLY` | `ROUTED -> SHAKEN` only |
| `MELEE_ROUT` | `STEADY`, `SHAKEN`, or `BROKEN -> ROUTED` |
| `ROUT_CASCADE` | `SHAKEN` or `BROKEN -> ROUTED` |

`SURRENDERED` is absorbing. Re-routing `ROUTED` is a no-op. A rejected,
cooldown-blocked, absorbing, or semantic no-op request consumes no draw,
changes no record/time/generation, and emits no event.

An admitted stochastic check consumes exactly one draw. It updates
`last_check_time_s` and increments generation even if the selected state does
not change; a real change also sets `last_transition_time_s`. Forced rally,
melee-rout, and cascade transitions consume no morale draw, bypass the current
cooldown, set both logical times, increment generation, and establish that
logical time as the unit's admitted semantic update. Independently of the
configured cooldown, the battle scheduler must not request a second stochastic admission
when the authoritative record's `last_check_time_s` already equals the current
logical time; this includes successful rally and earlier same-tick melee or
cascade transactions. The configured cooldown governs requests at later
logical times.

The first admitted stochastic check uses elapsed scenario time since zero.
Later checks use `current_time_s - last_check_time_s`. `dt` must be finite and
strictly positive. Battle cadence and level-of-detail scheduling may decide
when to request a check, but cannot substitute a constant tick duration or a
zero logical timestamp for elapsed time.

## Status, rout, and event consistency

The semantic morale/status projection is:

| Morale | Required active status |
|---|---|
| `STEADY`, `SHAKEN`, `BROKEN` | `ACTIVE` |
| `ROUTED` | `ROUTING` |
| `SURRENDERED` | `SURRENDERED` |

`DISABLED` and `DESTROYED` supersede retained morale and cannot be resurrected
by a morale operation. Prevalidation rejects a transition whose proposed
status effect would violate that precedence.

Rally evaluation and cascade selection are split into immutable planning and
runtime commit. A rally plan is evaluated with the injected MORALE stream;
failed preconditions consume no draw, while an eligible but unsuccessful rally
consumes its prescribed draw and mutates no state. A successful rally commits
removal of any existing `RoutState`, record, and status before publishing
`MoraleStateChangeEvent` and then `RallyEvent` at the same logical timestamp.
An injected failure before the first notification rewinds that rally draw and
all semantic owners. Melee rout and cascade use the same
record/status/event transaction.

Each routing source is processed in the existing configured-side and unit
processing order. For that source, cascade planning first prevalidates the
complete candidate snapshot, captures the MORALE generator, and then visits
candidate IDs in lexicographic order. It consumes exactly one draw for each
`SHAKEN` or `BROKEN` candidate at or inside the configured radius and no draw
for the source itself, another state, or an out-of-range candidate. Applying a
selected `ROUT_CASCADE` transition consumes no additional draw. All selected
targets for one source form one batch: their records and statuses commit before
the first batch event. Any failure before that notification restores every
target, status, and all selection draws; subscriber failures leave the batch
committed and report only after every selected target has been offered its
event in candidate order. Later routing sources observe earlier committed
batches, matching the production loop's sequential source semantics.

Phase 113 does not synthesize a `RoutState` when morale becomes `ROUTED`.
Production battle already represents those transitions with morale plus
`UnitStatus.ROUTING` and supplies neither the threat direction nor the extra
scatter draw required by `RoutEngine.initiate_rout()`. That lower-level API
remains separately usable and its existing active route is removed when the
unit rallies or becomes `SURRENDERED`; transition into `ROUTED` consumes only
the draw budget stated above.

The former public `RoutEngine.process_surrender()` partial API rejects before
RNG, route, event, record, or status mutation. Production stochastic
`ROUTED -> SURRENDERED` transitions already commit the authoritative record,
`Unit.status`, route removal, and caused morale event through `MoraleRuntime`.
Captor provenance, prisoner counts, `SurrenderEvent`, logistics processing,
and their persistence/exposure remain REM-033/Phase 120; Phase 113 does not
fabricate them.

`MoraleStateChangeEvent` carries the typed cause and logical time. Observers
therefore see the committed state when handling it. Analytics remains a
caused-transition timeline; registration does not fabricate transition
events and analytics is not claimed as a complete current-state distribution.

## RNG ownership

`RNGManager` is the sole persistence authority for the MORALE stream. The
runtime, state machine, and rout engine all receive the exact same generator
object from `RNGManager.get_stream(ModuleId.MORALE)`. None serializes an RNG
mirror in the current checkpoint.

Factory construction and restore validate generator object identity. Failed
prevalidation, no-ops, cooldown blocks, and forced-transition application do
not consume the stream. Admitted stochastic checks, eligible rally
evaluations, and eligible cascade-candidate selection consume only the draws
specified above. Continuation evidence compares exact RNG state as well as
state, status, rout, events, and outcome.

## Aggregation ownership

1. The morale store, not `AggregationEngine`, owns suspended constituent
   records. Suspending a group removes its sorted constituent IDs from active
   state and records their complete immutable records plus the exact aggregate
   proxy baseline.
2. The aggregate proxy record is the complete record of the
   lexicographically smallest constituent among those tied for the worst
   `current_state`. No synthesized timestamp, cooldown, or generation is
   introduced.
3. Aggregation commits roster topology, store suspension, aggregate proxy
   registration, and status coherently. Its rollback restores each owner in
   place.
4. Disaggregation first compares the proxy's complete record—including both
   optional times and generation—with its stored baseline. Any evolution,
   including a state that changes away and back or an admitted no-change
   stochastic check, rejects before the existing lossy disaggregation logic
   mutates the roster.
5. An unchanged proxy restores the archived constituent records exactly. The
   Phase 113 positive round-trip proof is intentionally limited to a base
   `Unit` fixture with empty attachment topology. Production-loaded evidence
   proves aggregate morale topology and evolved-proxy rejection, not general
   unit or attachment reconstruction. REM-016 remains open for that broader
   fidelity and propagation boundary.
6. That narrow round trip rejects every non-null context checkpoint owner not
   explicitly coordinated by the aggregation transaction. The production
   checkpoint registry is the authority, while minimal compatibility fixtures
   fail closed over all `*_engine` attributes. A populated ROE, CBRN, planning,
   detection, EW, indirect-fire, missile, or future owner cannot silently keep
   constituent state or synthesize default aggregate state.

## Consumers and outcome effect

Victory evaluation, battle logic, API status frames, campaign final-state
serialization, aggregation, recorder output, and checkpointing all read the
same immutable current-state projection. No consumer retains a separately
writable enum map.

Production outcome evidence must use a seeded, production-loaded scenario in
which authoritative morale transitions satisfy `morale_collapsed` and change
the terminal victory result. A matched control held at `SHAKEN` must not meet
that condition. A no-crash run, source search, event log, or constructor call
is not sufficient evidence. Firing behavior may be checked for consistency but
is not the causal acceptance proof for this ownership remediation.

## Phase 113 checkpoint format

> **Current-format note:** This section records the Phase 113 format transition
> historically. The current engine writes format 118, which preserves this
> exact morale topology, retains the independent Phase 114 era-runtime
> contract, Phase 115 tactical-targeting state, Phase 116 fog-of-war contact
> state, and Phase 118 performance-semantic owners. Explicit formats 113
> through 117 now reject as older versions.

`SimulationEngine` advances the explicit format to `113`.

1. Current context state always contains exactly one `morale_runtime` key. Its
   value is an envelope with active records and suspended aggregate archives,
   or `null` only for a deliberately minimal context with no runtime and an
   empty roster. It contains no separate `morale_states` or `morale_machine`
   current-state copy. A non-empty engine runtime cannot be checkpointed with
   `null` morale ownership.
2. `RNGManager` alone serializes MORALE generator state. `MoraleRuntime`,
   `MoraleStateMachine`, and `RoutEngine` serialize no MORALE RNG mirror.
   `RoutEngine` remains a registered state owner for active route state.
3. Restore stages and validates the complete morale envelope before mutation:
   exact active roster/store topology, aggregate proxy and suspended archive
   topology, record types/times/generations, state/status compatibility,
   factory owner and generator binding, and elapsed-time bounds.
4. Fresh and in-place continuation preserve exact records, statuses, active
   routes, event sequence, RNG continuation, victory behavior, immutable view,
   and stable in-place owner identities.
5. Any explicitly present version other than `113`, including `112`, rejects.
   Explicit `null`, booleans, malformed values, and future versions reject as
   corrupt rather than entering migration.

An absent version enters one bounded legacy migration:

- where both old context and state-machine entries are present for an active
  unit, they must agree; disagreement is rejected rather than resolved by
  precedence;
- a pre-108 payload missing one or both entries for an active unit first uses
  any present valid machine record, then the validated checkpoint roster's
  side-level `morale_initial` only when both legacy entries are absent. A
  present context/machine disagreement always rejects;
- the dead per-record `transition_cooldown_s` mirror must be a non-boolean
  finite numeric `0.0`, the canonical value produced by the legacy production
  initializer. It is discarded; the validated `MoraleConfig` is the sole
  effective cooldown authority;
- the historical negative transition-time sentinel migrates to
  `last_transition_time_s=None`, `last_check_time_s=None`, and `generation=0`.
  A finite non-negative legacy transition time migrates to both new times with
  `generation=1`. This is a new generation epoch, not a claim that the
  unrecorded count of historical checks was recovered;
- a legacy runtime whose checkpoint elapsed time is greater than zero and whose
  validated config has `use_continuous_time=True` rejects because its
  last admitted no-change check and therefore its next elapsed `dt` cannot be
  reconstructed. A tick-zero continuous-time payload may migrate using the
  never-checked record above. Discrete-time migration remains deterministic
  because the model ignores `dt` and the authoritative RNG state is preserved;
- legacy MORALE RNG mirrors in the state machine and rout engine must exactly
  match the authoritative `RNGManager` stream before they are discarded; and
- a legacy payload with an active aggregation proxy is rejected because it
  cannot reconstruct complete suspended constituent records.

For format 113, `morale_runtime=null` restores only when checkpoint and target
rosters are empty, the target also omits the runtime, and route/aggregation
state is empty. A runtime target rejects `null`; an absent-runtime target
rejects an envelope. Direct minimal contexts may expose the empty immutable
view, but a non-empty one cannot claim or emit a valid engine checkpoint.

Migration validation occurs before clock, RNG, roster, record, status, route,
recorder, or event mutation. Current and migrated restores reject foreign
units, duplicate or missing records, invalid enum/status combinations,
impossible times, boolean generations, and malformed archive topology.

## Production trace and capability evidence

`scenario YAML -> typed morale configuration -> ScenarioLoader -> one
MoraleRuntime -> battle/rally/melee/cascade/aggregation -> immutable context
view -> victory/recorder/API/checkpoint`

| Stage | Required Phase 113 evidence |
|---|---|
| Declared | Immutable record, registration, cause, plan, store, runtime, view, and checkpoint structures with explicit invariants |
| Loaded | `ScenarioLoader` constructs one factory runtime from the validated morale configuration and full planned roster |
| Wired | Initial units, reinforcements, all transition causes, aggregation, victory, API/campaign, analytics, and checkpoint use the same boundary |
| Enabled | N/A: morale ownership is mandatory in a production-loaded non-empty runtime and has no feature flag |
| Exercised | Seeded ordinary, rally, melee, cascade, reinforcement, aggregation, fresh/in-place restore, and corruption controls execute production paths |
| Outcome-affecting | A production `morale_collapsed` scenario terminates only after authoritative transitions; the SHAKEN control does not |
| Persisted/exposed | Format 113 and bounded legacy migration preserve exact records, statuses, routes, RNG, events, identity, victory, API frames, and campaign final state without duplicate owners |

## Acceptance tests

Baseline red proof must reproduce five distinct defects on the Phase 112
production surface:

1. a post-reinforcement direct state-machine mutation leaves the public
   projection stale (a public-bypass defect, not an ordinary battle-mirror
   claim);
2. a real rout cascade creates a context/machine disagreement that a fresh
   production restore rejects;
3. aggregation leaves constituent and proxy morale topology split;
4. machine-owned routed state cannot trigger production victory while the
   context copy remains shaken; and
5. ordinary battle requests morale checks at zero logical time, permanently
   interacting with cooldown after the first recorded transition.

Green proof must include:

- one factory runtime, stable immutable view, and exact MORALE generator
  identity across runtime, state machine, rout engine, and RNG manager;
- mutation attempts against records/views failing without state change;
- duplicate, unknown, and injected-late-failure registration rollback controls;
- injected pre-notification stochastic and successful-rally failures proving
  in-place owner and MORALE-generator rollback;
- unknown/no-op/cooldown/absorbing transition RNG, generation, and event
  neutrality;
- exact ordinary, rally, melee, and cascade transaction ordering and draw
  behavior at nonzero logical times;
- valid zero-second cooldown controls proving successful rally and a failed
  rally after same-tick melee rout cannot trigger a duplicate `dt == 0`
  stochastic admission;
- sorted cascade candidate draw counts, multi-target pre-notification rollback,
  and retry equivalence;
- the causal `morale_collapsed` outcome and SHAKEN control;
- production-loaded aggregate topology plus evolved-proxy rejection, including
  an away-and-back/generation control;
- exact unchanged aggregation round-trip for the narrow base-unit fixture;
- current format fresh and in-place deterministic continuation plus current,
  legacy, RNG, status, topology, timestamp, foreign-unit, null-version, and
  malformed-record rejection controls;
- exact API frame, campaign final-state, and transition-analytics projections;
- the direct positive guerrilla guard failing explicitly before position,
  status, morale, event, COMBAT-RNG, or MORALE-RNG mutation, paired with a
  factory-loaded zero-blend production-loop retreat control and no claim that
  populated-area recognition is currently wired; and
- the legacy rout-owned surrender/POW bypass rejecting without mutation,
  paired with an authoritative stochastic `SURRENDERED` record/status/route/
  event transition; and
- static exhaustive review of mutation and read call sites, backed by the
  behavioral tests rather than treated as behavior itself.

Applicable existing morale, rally, aggregation, victory, checkpoint,
reinforcement, API, campaign, and scenario suites must remain green. Full
cross-hash proof is required if implementation introduces a new unordered
state-affecting traversal. Profiling is required only if the runtime boundary
causes a material production-scenario regression.

## Non-goals and remaining deficits

- General aggregate-unit reconstruction, subclass fidelity, attachment
  preservation, and aggregate-created state propagation remain REM-016.
- Populated-area guerrilla concealment is not a morale route. Its correct
  population lookup, concealed/disengaged ownership, targeting effects,
  lifecycle, checkpoint, API, and scenario behavior remain REM-032; Phase 113
  exposes the unsupported positive result rather than fabricating or dropping
  it.
- Captor selection, prisoner counts, `SurrenderEvent`, logistics processing,
  and their checkpoint/API lifecycle remain REM-033/Phase 120. The production
  morale state can become `SURRENDERED`, but that does not imply POW handling.
- Aggregate-casualty and auto-resolve event timestamps remain
  REM-034/Phase 121. Their production `datetime.min` sentinel is tracked as an
  event-time deficit and is not Phase 113 morale-event evidence.
- Logistics resupply and expenditure linkage remain REM-020 and REM-021.
- Ordinary contact fidelity, checkpoint scope separation, and terrain/weather
  remediation remain assigned to later phases.
- This phase does not recalibrate morale probabilities, change combat doctrine,
  or infer completeness from imports, mocks, logs, or no-crash runs.
