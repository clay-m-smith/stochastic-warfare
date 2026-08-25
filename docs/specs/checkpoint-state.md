# Checkpoint State Contract

## Status

Current through the Phase 118 performance-semantic implementation and the
2026-08-23 tiered modular-monolith consolidation. The current engine format is
118. The immutable schema-2
`phase118-performance-semantics-v7` study completed all 96 pairs / 396 attempts
and independently reloaded as an eligible terminal `FAIL` under
`EXTERNALLY_CONTENDED`; its manifest artifact SHA-256 is
`bf9e00ce4a7774af29b5657c49bbbe4481b407a966d9922e48970022f5c6ad86`.
The accepted qualified-negative postmortem closed Phase 118 / REM-031. The
semantic evidence supports no speed claim; REM-055 / Phase 142 owns the
separately measured transactional-FOW runtime regression.

### Consolidation closure note

The tiered modular-monolith consolidation preserves format 118 while moving
context persistence behind `simulation.context_checkpoint`. One frozen
`ContextCheckpointSnapshot` is the context-level product. Each participant has
a typed disposition: atomic checkpoint owner, bounded legacy clone owner, or
explicitly stateless. Planning remains non-mutating and commit remains
all-or-nothing; the `scenario` compatibility facade delegates to the focused
configuration, runtime-context, checkpoint, and loader owners.

Authored calibration is compiled once into recursively immutable
`ResolvedCalibration`; checkpoint comparison cannot adopt mutable
`ctx.cal_flat` input. Initial, reinforcement, and restore loadouts reuse the
same retained builder and registry identity. Strict execution remains the
authority for checkpoint creation and restore. An explicitly degraded runtime,
or one with suppressed runtime/recorder/event failures, cannot create or
restore an authoritative checkpoint.

The consolidation also shares one current targeting/FOW snapshot across its
tick consumers. The accepted consolidation postmortem closes REM-053 on this
verified boundary; it does not change checkpoint format 118. Planned Phase 140
is retired before start.

Dedicated matched checkpoint-capture evidence used five interleaved blocks per
revision, each with two warmups and seven measured captures (35 observations
per revision). The consolidation-base median was 11.288641 ms and the current
median was 4.506367 ms, a 0.399195 ratio, while restored state, continuation,
replay, recorder output, and RNG state remained exact. This is a workload-
specific measurement of this checkpoint path, not a universal speed claim.
The closure is valid only for a revision whose final exact frozen-revision
release gate is green.

## Purpose

A checkpoint is a deterministic branch point. Restoring it must reproduce the
mutable simulation state at time `T`, and continuing from it must produce the
same subsequent state and events as the uninterrupted seeded run.

The restore target must be a structurally compatible runtime built from the same
validated effective scenario configuration and repository/data-catalog
revision. Checkpoint restore replaces mutable state; it does not rebuild engine
topology or reinterpret a different scenario.

`SimulationEngine` writes checkpoint format version `118`. Any explicit version
other than `118`, including `116`, is rejected before runtime mutation. An
absent version selects the bounded legacy-migration path described below; an
explicitly present `null` value is malformed, not legacy.

For version `118`, top-level engine keys and context-state keys must exactly
match the compatible target runtime. Missing or extra keys fail before
mutation. Serialized scenario and reinforcement configurations use type-aware
JSON equality, so booleans cannot masquerade as integers and integers cannot
masquerade as floats.

Every current JSON checkpoint capture rejects `NaN` and positive or negative
infinity, including values nested in NumPy arrays. The shared decoder accepts
only exact two-key NumPy markers with scalar or rectangular arrays and canonical
boolean, signed-integer, unsigned-integer, or floating dtypes. Boolean leaves
must be JSON booleans; integer leaves must be JSON integers excluding booleans
and fit the declared dtype; floating leaves must be finite JSON numbers
excluding booleans and fit the declared dtype. Marker coercion, strings,
fractional integer leaves, and out-of-range values reject before any engine
state is staged.

## Force state

`SimulationContext.get_state()` serializes force sides in iteration order and
units in processing order. Each unit state includes:

- stable `entity_id`;
- stable `unit_class` discriminator;
- owning side and domain;
- position, status, motion, training, and weight;
- personnel state and ordering;
- equipment state and ordering;
- all concrete subclass fields.

Scenario-derived runtime instances are serialized separately:

- weapon identity, ammunition/missile state, rounds since maintenance,
  equipment condition, and last-fire cooldown time;
- sensor identity and linked equipment condition.

The accepted unit-class discriminators are `Unit`, `GroundUnit`, `AerialUnit`,
`NavalUnit`, `AirDefenseUnit`, and `SupportUnit`. Restore uses a fixed allowlist;
it never imports a class named by checkpoint data.

Restore must:

1. validate the full force and morale payload before committing either;
2. reject duplicate entity, personnel, or equipment IDs;
3. reject an unknown class or a unit whose declared side disagrees with its
   containing side;
4. reuse live unit, personnel, and equipment objects when stable IDs and
   concrete types match;
5. reconstruct missing units without drawing from any RNG stream;
6. remove runtime-only units and preserve serialized side/unit ordering;
7. discard stale weapon/sensor objects for units that could not be safely
   reused while preserving serialized empty map entries exactly;
8. rebuild scenario-defined loadout topology for a checkpoint-only
   reinforcement without consuming RNG, then restore its exact mutable
   attachment state.

Current and bounded versionless restore apply the same semantic reuse
preflight before mutating an existing same-ID unit: exact concrete class,
unit type, domain, ordered equipment IDs, names, and categories must agree.
Legacy migration does not permit a same-type object to be mutated first and
rejected later by its retained live loadout bindings.

The checkpoint's effective scenario configuration must match the runtime
configuration. Weapon and sensor instance counts, ordering, and identities must
match for every non-empty serialized loadout. An empty serialized loadout needs
no prebuilt runtime instance, including when the unit is reconstructed. An
incompatible runtime fails before context-owned clock, RNG, force, morale, or
loadout state is committed.

Stable-object reuse is required because weapon, sensor, and subsystem instances
can hold references to a unit's equipment.

## Era runtime and clock cadence

Current context state contains exactly one `era_runtime_contract` with the
selected registry ID, era label, effective strategic/operational/tactical
durations, all three medical treatment durations, and maintenance repair
duration. It is behavior, not a copy of the sparse metadata that produced it.

The target runtime separately captures the exact scenario-side cadence source
(`era`, all three authored tick values, and optional uniform shorthand), the
isolated selected `EraConfig`, and the scenario start/duration horizon. Before
mutation, restore strictly parses the checkpoint contract and requires exact
agreement with those captured identities and the frozen medical, maintenance,
and loadout consumers. The saved engine resolution must map to the saved clock
duration under that same contract, the saved clock start must equal the
scenario start, and current time cannot exceed the executable horizon.

Missing, extra, malformed, type-aliased, or different era contract data fails
atomically. A versionless checkpoint cannot contain the era-contract key and may
restore only into a target whose captured era declares no physics or cadence
override. It cannot infer historical behavior from a current registry entry.
Active non-default medical treatment and maintenance repair state remains
owned by those engines and must continue at the exact contract-defined
endpoint after fresh or in-place restore.

## Morale state

A non-empty production runtime has exactly one semantic morale owner:
`MoraleRuntime`. `SimulationContext.morale_states` is the runtime's stable,
read-only `Mapping[str, MoraleState]` compatibility projection; it is not a
second checkpoint store. `MoraleStateMachine` selects stochastic transitions
but owns no current unit state.

Current context state contains exactly one `morale_runtime` key. Its value is a
strict envelope with exact `active_records` and `suspended_archives` keys, or
`null` only for a deliberately minimal context whose roster, active routes, and
aggregation topology are all empty. Current format 118 contains no separate
`morale_states` or `morale_machine` current-state copy.

Each active record preserves typed current state, optional finite non-negative
last-transition and last-admitted-check times, and a strict non-negative
generation. Canonical serialization sorts unit and aggregate IDs. Suspended
archives preserve each aggregate proxy's complete baseline record and every
constituent's complete record. Disaggregation rejects an evolved proxy before
the existing lossy reconstruction path can mutate the roster; an unchanged
supported proxy restores the archived records exactly. General subclass and
attachment reconstruction remains REM-016.

`MoraleRuntime` coordinates ordinary stochastic changes, rally, melee rout, and
rout-cascade changes with `Unit.status`, applicable active-route removal, and
ordered events. `STEADY`, `SHAKEN`, and `BROKEN` require `ACTIVE`; `ROUTED`
requires `ROUTING`; and `SURRENDERED` requires `SURRENDERED`, while `DISABLED`
and `DESTROYED` take precedence. A transition into `ROUTED` does not synthesize
a direction-bearing `RoutState`; an existing lower-level route is retained only
while semantically compatible and is removed on rally or surrender.

Restore stages and validates the complete envelope before mutation: active
roster/object topology, aggregate archives, record types and times against the
checkpoint clock, morale/status compatibility, stable owner bindings, and the
shared MORALE generator identity. Fresh and in-place continuation preserve
records, statuses, routes, events, victory behavior, the stable read-only view,
and in-place owner identities.

Initial and dynamic units register through the same runtime boundary using each
side's validated `morale_initial`. Unknown states, foreign or duplicate IDs,
missing active records, malformed archives, impossible times, and incompatible
status combinations are corrupt checkpoint data and fail before commit.

## Aggregation state

An aggregation checkpoint is one strict envelope containing the exact
`AggregationConfig`, monotonic next aggregate ordinal, and canonical active
aggregate archives. Each archive remains detached from public state/property
reads and retains the side, domain, original roster indexes, complete supported
base-unit snapshots, and derived proxy summary needed for exact reconstruction.
Candidate selection is canonical by side, unit type, and unit ID; equivalent
side-map insertion orders cannot change aggregate IDs or transition order.

An active aggregate may restore only into a present `AggregationEngine` whose
configuration exactly equals the persisted configuration and whose
`enable_aggregation` field is true. A missing, disabled, or differently
configured owner rejects before clock, RNG, roster, equipment, morale, or any
other context state mutates. An unchanged supported proxy and its morale
archive must therefore always retain a live owner capable of executing the
future disaggregation transition.

The supported compatibility transaction is deliberately fail-closed. It
coordinates only the exact aggregation, morale/rout, targeting-registration,
and empty runtime-loadout owners. Every other non-null owner in the
authoritative context checkpoint registry rejects before aggregation,
disaggregation, capture, or restore; compatibility fixtures conservatively
reject every unrecognized `*_engine` as well. This prevents CBRN, planning,
ROE, detection, EW, carrier, indirect-fire, missile, or future per-unit state
from retaining constituent IDs while an unregistered aggregate proxy enters
the roster. General owner-state propagation remains REM-016.

## RNG and derived state

RNG streams restore before engine continuation. `RNGManager` is the sole
checkpoint authority for the MORALE generator. `MoraleRuntime`,
`MoraleStateMachine`, and `RoutEngine` receive that exact generator object and
serialize no current-format RNG mirror. Legacy machine and rout mirrors must
match the authoritative stream before migration discards them. Reconstructing
force objects must not consume a stream. Calibration's flattened,
side-dependent view is regenerated after force restoration.

## Commander, school, and OODA state

When commander behavior is enabled, the current checkpoint contains the exact
unit-to-profile assignments, commander configuration and mutable state,
doctrinal-school catalog/assignments, and OODA commander phase state. Restore
validates those owners against the complete checkpoint roster, including
already arrived reinforcements, and rejects a missing, extra, unknown, or
side-incompatible assignment before mutation.

Commander behavior requires valid canonical profiles for every scenario side
or for none. Initial/future per-unit overrides and school assignments are
preflighted against the full planned roster and catalogs. Fresh-runtime
continuation must preserve assignment identity and subsequent decision/OODA
behavior. Commander/school restore across an enabled aggregation-proxy topology
remains unsupported under REM-016.

## Movement-diagnostics state

The scenario-owned `MovementDiagnostics` persists exact registered
unit-to-side topology, canonical last ordering key and next ordinal, cumulative
reason/distance/progress counters, total observation count, and each unit's
bounded recent observation window plus dropped count. Typed reasons include
weapon standoff, resource blocked, and zero progress.

Restore stages and validates all units, sides, finite distances, order,
reason-specific invariants, aggregate counters, and the fixed observation
bound before committing. The diagnostics are observational: they do not select
movement, consume RNG, or write positions. Versionless state may omit this
owner only at tick zero before either the checkpoint or target diagnostics has
observations.

## Tactical-targeting and fog-of-war state

Format 118 contains one strict `tactical_targeting` envelope owned by the exact
`TacticalTargetingRuntime` bound to the context, engine, and battle manager. It
persists the default-on enablement value, default visibility bound, registered
unit/side topology, current interval tick and elapsed time, published battle
IDs, immutable per-battle pictures and decisions, and post-movement engagement
revalidation outcomes. Live interval, published IDs, pictures, and
revalidations occupy one immutable runtime snapshot so complete multi-battle
publication cannot expose a prefix. Every `SimulationEngine`, including one with an empty
roster, requires this owner so an engine-produced current checkpoint cannot
omit the envelope and then fail its own restore contract. Decisions retain
exact target, weapon, ammunition,
source-equipment, sensing/contact/fire-control, range provenance, disposition,
authorized standoff, and consumability evidence.

Restore stages that envelope and cross-validates its tick/time against the
checkpoint clock, its battle IDs and shooter memberships against staged active
battles, its unit/side references against the restored roster, its exact source
indexes against runtime loadout topology, its default visibility against the
captured scenario environment, and every checkpoint-current latest decision's
recorded visibility (including targetless decisions) against that same staged
environment. An older retained latest picture and retained movement history
preserve the visibility recorded for their own interval; they remain subject to
schema, topology, attachment, catalog, and internal optical-bound validation,
but do not claim the checkpoint-current environment and therefore pass no live
visibility value. Restore also cross-validates the associated movement
diagnostics. A
missing active-battle picture, foreign target, reordered binding, impossible
range, forged authorization, or owner-identity divergence rejects before
mutation.

Before every engine step, the authoritative roster registration check walks
the exact `units_by_side` buckets without collapsing IDs. It rejects duplicate
entity IDs and any unit whose declared side disagrees with its containing
bucket, then compares the canonical unit/side map with targeting registration.
This guard runs before clock advancement, RNG consumption, position changes,
or recorder/event mutation.

With FOW disabled, fresh restore and continuation preserve exact decisions,
positions, movement diagnostics, revalidation, ammunition, events, and full
checkpoint bytes. With FOW enabled, format 118 preserves a current decision's
exact consumability only when the separately staged fog owner proves its
reporting-side contact, fusion track, and either an observer-local current
witness or one bounded observer-track support, together with the interval
epoch, cadence, and loadout/sensor provenance. A support must retain the exact
attachment/target identity, one of the seven allowed radar fire-control roles,
the same live fusion generation, its observation and next-native-deadline
chronology, and a finite positive-semidefinite projected covariance. A missing
or inconsistent association rejects; restore does not rewrite a current
decision as historical or infer witness/support evidence from a side-wide
contact.

This support topology remains authoritative for immutable format-118 evidence
and the dormant scan-deferral algorithm, but current supported production
cannot create a non-null observer-track support: scan scheduling and LOD
activation are rejected after the terminal semantic `FAIL`. REM-054 / Phase
141 owns restoring a supported production-reachable emission path.

The format-118 `fog_of_war` envelope contains exactly `world_views`,
`current_detection_witnesses`, `observer_track_supports`, `rng_state`,
`intel_fusion`, `scan_counts`, and `cadence`. It restores the complete roster-
backed ordinary-contact map with replacement semantics,
including explicit empty views and removal of target-runtime-only state. Every
live `ContactRecord.track` is rebound to the exact staged fusion-owned `Track`
object after the duplicate serialized track representation agrees exactly;
an equal detached object is invalid. Contact levels, classifications, vectors,
covariance, lifecycle counters/status, sensor provenance, chronology, canonical
ordering, roster hostility, and side-local monotonic track IDs are validated
before publication. Reporting-sensor provenance is nonempty, and each FOW
counter equals the greatest issued side-local ordinal so continuation cannot
silently skip or reuse the next ID.

The bounded current witness cache preserves the exact observer, target, source
equipment index, sensor/model role/type, interval time, detection result,
probability, SNR, range, and bearing needed by a consumable current targeting
decision. The next normal update replaces this cache; it is not an unbounded
history. The separate bounded support map retains only a successful radar
attachment measurement and its deterministic estimator projection while that
attachment is cadence-deferred. Support clears on loss, track replacement,
invalid attachment/roster topology, or the next native deadline; reinforcement
and reappearance may create only a newly valid record bound to the current
fusion generation. Checkpoint continuation preserves the exact remaining
deadline and projection, never extends it. FOW, fusion, detection, estimators,
identification, deception, and the context must share the authoritative
`RNGManager` DETECTION generator and all serialized mirrors must agree before
mutation.

Staging produces an exact-owner-bound plan with independent content and raw
type/shape/alias fingerprints. Commit rejects a subclassed, foreign, or
mutated plan. It validates scan-count primitives, jointly deep-copies the
alias-sensitive world-view/contact, witness/support, RNG, fusion, and cadence
graph, rebuilds the detached publication, and verifies both fingerprints
again. It then separately prepares the scan-count, fusion, cadence, and
observer-support payloads before the first live mutation. Publication assigns
the validated shared RNG state once and performs only bounded owner swaps.
Disabled FOW permits explicit empty views and non-FOW Space tracks but rejects
contacts, witnesses, supports, FOW IDs, or FOW counters. A dynamic roster
change may leave durable FOW state while targeting is intentionally between
intervals; the next step refreshes both owners.
Capture and restore reject non-pristine active/inactive deception state under
REM-046 and custom/populated COP/data-link state under REM-036 because format
118 does not serialize those owners. Versionless state cannot retain even
LOST-only FOW track/counter history.

## Performance receipts, cadence, and indexed FOW randomness

Format 118 adds one strict `battle.performance_execution_receipt`, one
`fog_of_war.cadence` envelope, exact detection `scan_counts`, canonical
`fow_observer_unit_ids`, and one `context.rng.indexed_fow` owner. Together they
preserve the effective values of the five governed flags, completed tactical
intervals and duration, sensing admissions/deferrals, culling/SoA selection,
sequential or parallel dispatch, LOD sensing tiers, indexed decision counts,
and a digest-bearing canonical transcript.

Detection culling, SoA selection, and parallel detection are the three
`supported_exact_validated` flags. Scan scheduling and LOD remain
model-fidelity approximations with
`unsupported_failed_semantic_validation`. Current checkpoint capture and
restore reject either retired flag enabled and reject nondefault
`lod_nearby_interval`, `lod_distant_interval`, or `lod_hysteresis_ticks`
before mutation. Historical `EffectivePerformanceFlags.from_state` decoding
remains permissive enough to preserve recorded true values; decoding those
values does not authorize a current runtime. The raw v6
terminal `ERROR`, v7 terminal `FAIL`, frozen plan, typed retirement handoff,
and their one-off validation tooling are intentionally off main. Their durable
locators are
`branch=evidence/full; path=docs/evidence/phase-118/v6-terminal/`,
`branch=evidence/full; path=docs/evidence/phase-118/v7-terminal/`,
`branch=evidence/full; path=data/validation/performance_semantics/phase118.yaml`,
and
`branch=evidence/full; path=docs/evidence/phase-118/runtime-manifest-handoff.json`.
Archived decoding and verification preserve those results but do not authorize
a current runtime or reinterpret either study.

The indexed owner derives decisions from the master seed plus strict semantic
observer/target/sensor/interval identities. Worker completion order cannot
select a different value or publication order. A complete interval stages its
cadence, side updates, receipt delta, and indexed transcript record before the
outer battle transaction publishes any of them. Checkpoint capture rejects an
active allocation, poisoned transaction, partial side set, mismatched
completeness flag, interval/entry count disagreement, effective-flag drift, or
cadence mismatch rather than serializing a prefix.

Restore validates the receipt, cadence, observer topology, scan counts, indexed
state, contacts/fusion generations, observer supports, targeting evidence, and
effective calibration together before mutation. Authored scenario
configuration, typed calibration, flattened hot-path calibration, and the
committed execution receipt are cross-bound before capture, restore, work, or
receipt exposure. A
versionless payload cannot contain any Phase 118 evidence owner. Its bounded
default-flag migration starts zero receipt/cadence/indexed owners marked
`complete_from_tick_zero: false`; that incompleteness is monotonic in all
descendant format-118 checkpoints and cannot be promoted. A started
versionless runtime with scan scheduling or LOD enabled rejects because the
omitted cadence history cannot be reconstructed.

## Runtime loadout topology

The Phase 109 `RuntimeLoadoutBuilder` is the only owner of production weapon
and sensor attachment construction for initial units, reinforcements, and fresh
checkpoint reconstruction. Checkpoint compatibility validates the ordered
mapping-registry fingerprint plus each unit's exact resolved attachment
topology, source-equipment index/object relationship, runtime system
multiplier, weapon/sensor identity, and ammunition topology before mutable
instance state commits. A duplicate, missing, reordered, stale, or semantically
different attachment fails; it is never substituted with a proxy.

## Logistics state

`ScenarioLoader` injects one `LogisticsRuntime` for both enabled and disabled
configurations. The context delegates logistics persistence to that owner, so
the separately exposed stockpile and supply-network references are not
serialized a second time.

An enabled current checkpoint preserves:

- cadence remainder and the elapsed time of the last completed boundary;
- each registered unit's eligibility time, last-accounted time, open-interval
  activity disqualification, and last boundary position;
- complete depot configuration, condition, inventory, and spoilage accumulator;
- every unit inventory, configured maximum, and zero-stock item topology;
- complete supply nodes and routes, including geometry, infrastructure,
  throughput, condition, current flow, and transport fields.

Restore validates the full logistics envelope against the compatible scenario,
catalog, roster, profiles, depots, and expanded route topology. It stages both
manager states and all cadence/accounting maps before any clock, RNG, roster,
manager, recorder, or event state commits. Staging plans are runtime-owned and
content-fingerprinted; a foreign or mutated plan cannot be committed.

Disabled logistics serializes canonical empty managers and zero cadence state.
Its production update is an O(1) gate and ignores elapsed simulation time.
Versionless restore is permitted only for a logistics-disabled runtime because
an enabled runtime cannot reconstruct elapsed inventory history or topology.

## Space state

For a space-enabled runtime, one `SpaceEngine` envelope persists selected
catalog topology, constellation/satellite state, GPS/SATCOM/ISR/early-warning
state, finite ASAT asset inventory and cooldowns, pending/completed orders,
debris, service history, and the SPACE RNG stream. Restore stages the complete
envelope and validates exact catalog/action topology, satellite ownership and
state, order/result chronology, inventory, cooldown, debris, service
compatibility, and RNG agreement before committing any space owner. A
versionless checkpoint cannot restore a space-enabled runtime.

The ISR queue contains only immutable typed `SpaceISRReport` values with exact
report ID, owner/reporting side, target, satellite/constellation, optical/SAR
modality, resolution, position uncertainty, ENU observation, and observed plus
available logical times. Selected IMINT fusion constellations must be a subset
of the loaded constellation topology and must resolve to supported sourced
optical/SAR definitions.

Delayed delivery is transactional. Each delivered report has one terminal
`IntelDeliveryReceipt` carrying the exact report digest, resulting track, and
delivery time, plus one current `IMINTTrackAssociation` for the owner/target.
Restore validates report IDs and canonical queue order, cadence and
observation/availability chronology, satellite and unit references, ownership,
receipt/association digests, pending-versus-delivered lifecycle, and agreement
between Space and fusion state before committing either owner. A failed
delivery or restore leaves the queue, receipt ledger, associations, tracks,
clock, and RNG unchanged so the same operation can be retried.

This typed Space ISR contract does not directly inject reports into ordinary
fog-of-war contacts. Phase 112 proved its queue/receipt/association lifecycle
with an explicitly empty ordinary-contact topology; format 118 independently
restores nonempty roster-backed `SideWorldView.contacts` and their fusion
aliases without relabeling Space ISR as a direct FOW-injection path.

The detailed ASAT production/action contract is
[ASAT Production Integration](asat-production-integration.md).

## Time-on-target state

For every declared time-on-target plan, `IndirectFireEngine` persists the
immutable plan fingerprint, enabled/dormant state, mission and battery
lifecycle, exact processed times/reasons/impacts, resource and precondition
snapshots, target transition, terminal result, and a read-only COMBAT RNG
mirror. `SimulationContext` stages this state against the checkpoint clock,
staged live `WeaponInstance` resources, unit statuses, exact attachment
topology, and the authoritative `RNGManager` COMBAT stream.

Validation independently recomputes chronology, rejection precedence, fired
resource deltas, terminal assessment, target compatibility, shared-attachment
history, and reservation/release state. Causally ordered public live-fire
bridges are accepted before, between, or after scheduled transitions only when
ammunition/counters/cooldown are monotonic, the finite last-fire time advances
from the preceding observation, and it does not exceed checkpoint elapsed
time. The latest preceding resource-bearing processed milestone is the lower
bound even after mission release: impact processing does not sample the live
weapon and cannot retroactively disqualify a public fire that occurred while
reserved. Reservation blocks ordinary battle selection but does not invalidate
a real lower-level `WeaponInstance` transition; the next scheduled milestone
observes that resource state and records the resulting depletion/cooldown
decision. Ammunition increases remain unsupported without the typed Class V
resupply provenance tracked by REM-021. Destroyed and surrendered terminal
targets cannot resurrect; a disabled target may only remain disabled or become
destroyed, while routing may legitimately rally. A versionless checkpoint
cannot restore any runtime with a declared plan, including a disabled
populated plan.

Time-on-target lifecycle round counts are non-boolean non-negative integers,
processed times are canonical finite floats, and terminal-result plus COMBAT
RNG-mirror scalar comparison is type-aware. Boolean aliases for integer
counters reject before context mutation.

The detailed contract is
[Time-on-Target Execution](time-on-target-execution.md).

## Compatibility

- Current engine checkpoints contain `checkpoint_version: 118`; an unknown,
  malformed, boolean, older explicit, or newer explicit version is rejected.
  Explicit version `116` and all earlier formats do not migrate into the
  current runtime.
- Current reinforcement wave ordinals and morale-record enum/generation values
  use non-boolean integers. Current wave side, configured arrival time, and full
  typed configuration must agree with the target schedule.
- Versionless engine checkpoints are treated as pre-108 only for bounded morale
  and reinforcement-ID migration, and only when logistics is disabled, space
  is not enabled, and no time-on-target mission is declared. Present legacy
  context and machine morale entries must agree; disagreement is never repaired
  by precedence. A missing pre-108 entry uses a present valid machine record,
  then the checkpoint roster's validated side-level `morale_initial` only when
  both legacy entries are absent.
- A legacy record's dead `transition_cooldown_s` mirror must be the canonical
  finite numeric `0.0` before it is discarded. A historical negative
  transition-time sentinel becomes an unchecked generation-zero record; a
  finite non-negative transition time becomes both current record times with
  generation one. This bounded migration does not claim to reconstruct an
  unrecorded count of admitted checks.
- A started versionless runtime with continuous-time morale rejects because the
  last admitted no-change check and next elapsed `dt` cannot be reconstructed.
  Tick-zero continuous-time and deterministic discrete-time migrations retain
  the authoritative `RNGManager` state. Legacy machine and rout RNG mirrors
  must match it exactly before being discarded.
- A versionless payload with an active aggregation proxy rejects because it
  cannot reconstruct complete suspended constituent records.
- Current `morale_runtime: null` restores only between empty-runtime topologies
  with empty rosters, active routes, and aggregates. A runtime target rejects
  `null`, and an absent-runtime target rejects a runtime envelope.
- Legacy reinforcement entries without the current wave ordinal/config payload
  retain legacy IDs for units that already arrived. A pending legacy wave uses
  current stable IDs when it arrives, after which its next checkpoint is fully
  current.
- Direct current-format `SimulationContext.set_state()` calls require the
  complete `era_runtime_contract` and `morale_runtime` envelopes and apply
  exact replacement semantics.
  Legacy `morale_states`/`morale_machine` inputs are accepted only through the
  explicit bounded `allow_legacy_morale=True` path. `SimulationEngine`
  additionally requires `units_by_side` for its campaign/roster preflight and
  exactly one `era_runtime_contract`, one `morale_runtime`, one
  `tactical_targeting`, one context-owned detection owner, and one strict
  `fog_of_war` envelope for version 118.
- Older unit snapshots without `unit_class` infer the class from its unique
  subclass field. A snapshot with no subclass field restores as `Unit`.
- Unknown explicit discriminators fail; they never silently downgrade to
  `Unit`.
- Checkpoints containing `unit_weapon_states` or `unit_sensor_states` replace
  the corresponding runtime map keys exactly, including explicit empty lists.
- Older checkpoints without `unit_weapon_states` or `unit_sensor_states` retain
  the compatible runtime's existing instance state.

## Required evidence

Completion requires:

1. mutation followed by exact in-place restoration, including live nested
   references;
2. restoration into a fresh compatible runtime with a different roster;
3. all supported concrete unit classes plus legacy class inference;
4. corruption controls that show force/morale state is not partially committed;
5. a bytes checkpoint through `SimulationEngine`, followed by equivalent
   continuation and full serialized-state comparison;
6. a fully loaded production scenario with real weapon state;
7. empty checkpoint-only loadout entries, including a non-reusable same-ID
   runtime unit with stale attachments;
8. exact fresh-runtime continuation after a dynamic reinforcement arrival,
   including weapons, ammunition, sensors, morale, schedule state, and
   no-repeat behavior;
9. atomic rejection of campaign/roster, arrival-flag, loadout, era-gate, and
   single-owner morale record/status/archive topology mismatches;
10. exact enabled-logistics restoration immediately before a cadence boundary
    into a fresh compatible runtime, followed by equivalent stock, route flow,
    event order, supply state, victory, and RNG continuation;
11. rejection of incomplete, corrupt, scenario-incompatible, foreign-plan, and
    mutated-plan logistics state without partial mutation;
12. hash-seed-independent canonical checkpoint bytes and logistics event order;
13. ordered mapping-registry/runtime-loadout topology and exact mutable
    weapon/sensor continuation;
14. complete space/ASAT action, service, inventory, satellite, debris, RNG, and
    before/after-action fresh continuation, plus typed Space ISR continuation
    before and after delayed delivery, transactional retry, owner-only
    association, and atomic corruption controls under its historically
    declared empty-ordinary-contact fixture;
15. exact commander/profile/school/OODA restoration and fresh continuation for
    initial and arriving units, including a behavior-affecting assignment
    control and atomic rejection;
16. exact bounded movement-diagnostics restoration and fresh continuation,
    including real weapon-standoff and resource-blocked controls plus an
    explicitly injected zero-progress fault detector;
17. time-on-target continuation before fire, after a causal reserved pre-fire
    mutation, between fire and impact, during a shared-attachment plan, after
    completion/release, and for a disabled populated plan, plus atomic
    sentinel/lifecycle/resource/quantity-cooldown/target/RNG controls;
18. one-runtime transition, rally, melee, cascade, dynamic-registration,
    aggregation, API/campaign exposure, and exact current/legacy morale
    continuation controls;
19. exact current format-118 era-contract topology, resolution/clock agreement,
    bounded override-free versionless handling, active treatment/repair
    continuation, and atomic rejection of captured source, horizon, consumer,
    or contract drift;
20. exact tactical-targeting owner/topology, no-FOW fresh continuation,
    movement-diagnostic agreement, and atomic clock/battle/roster/loadout/range
    corruption controls;
21. exact nonempty ordinary-contact, fusion-object alias, bounded witness and
    radar observer-support lifecycles, current-decision consumability,
    DETECTION RNG, fresh/in-place loss/redetection/reappearance continuation,
    privileged/side-safe exposure, event, and whole-checkpoint continuation,
    including atomic corruption/retry and explicit REM-036/REM-046 rejection
    controls; and
22. exact format-118 performance receipt, sensing cadence, observer topology,
    detection scan counts, indexed FOW transcript, support native deadlines and
    fusion generations, enabled-flag, sequential/parallel dispatch, fresh/in-
    place continuation, and atomic cross-owner corruption controls;
23. bounded versionless default-flag migration with monotonic incomplete
    receipt/cadence/indexed history, plus rejection of mixed Phase 118 evidence
    and unreconstructable started scan-scheduling/LOD cadence; and
24. relevant existing checkpoint, scenario, engine, entity, morale, logistics,
    space, commander, movement, and indirect-fire regression suites.

## Tracked boundaries

Production weapon/sensor definitions and attachment topology remain
scenario-derived. Runtime instance state is serialized, and Phase 107 can
deterministically reconstruct a dynamic reinforcement's declared topology from
the compatible catalog before applying that state. A changed or unsupported
topology is rejected rather than substituted.

Aggregation/disaggregation also owns constituent reconstruction and attachment
restoration. Its current base-unit reconstruction gap is tracked separately and
must be closed before checkpoint equivalence is claimed across an aggregation
boundary.

Typed Space ISR queue/receipt/association equivalence must not be generalized
into direct ordinary-contact injection. Format 118 restores roster-backed
ordinary contacts separately; active deception remains REM-046 and custom or
populated COP/data-link topology remains REM-036.

Legacy Phase 101 `_fired_scripted_events` state is not part of format 118 and
must not be inferred from elapsed time after restore. Typed schedule identity,
effect receipts, fail-closed retry/commit policy, and exact-once continuation
for the four existing scripted-action families remain REM-045 / Phase 132.

The mapping registry and subsystem topology carry compatibility fingerprints,
but checkpoint files do not embed full content hashes for every external unit,
weapon, ammunition, sensor, era, or space catalog definition. Cross-revision
migration and complete catalog-content fingerprinting remain future
checkpoint-format work.
