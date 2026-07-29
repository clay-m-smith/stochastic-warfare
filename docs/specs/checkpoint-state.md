# Checkpoint State Contract

## Status

Phase 105 contract, extended through Phase 111 on 2026-07-29.

## Purpose

A checkpoint is a deterministic branch point. Restoring it must reproduce the
mutable simulation state at time `T`, and continuing from it must produce the
same subsequent state and events as the uninterrupted seeded run.

The restore target must be a structurally compatible runtime built from the same
validated effective scenario configuration and repository/data-catalog
revision. Checkpoint restore replaces mutable state; it does not rebuild engine
topology or reinterpret a different scenario.

`SimulationEngine` writes checkpoint format version `111`. Any explicit version
other than `111` is rejected before runtime mutation. An absent version selects
the bounded legacy-migration path described below; an explicitly present
`null` value is malformed, not legacy.

For version `111`, top-level engine keys and context-state keys must exactly
match the compatible target runtime. Missing or extra keys fail before
mutation. Serialized scenario and reinforcement configurations use type-aware
JSON equality, so booleans cannot masquerade as integers and integers cannot
masquerade as floats.

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

The checkpoint's effective scenario configuration must match the runtime
configuration. Weapon and sensor instance counts, ordering, and identities must
match for every non-empty serialized loadout. An empty serialized loadout needs
no prebuilt runtime instance, including when the unit is reconstructed. An
incompatible runtime fails before context-owned clock, RNG, force, morale, or
loadout state is committed.

Stable-object reuse is required because weapon, sensor, and subsystem instances
can hold references to a unit's equipment.

## Morale state

The context morale map is distinct from `MoraleStateMachine` internal state.
Both must round-trip:

- `SimulationContext.morale_states` restores exact keys as typed
  `MoraleState` values.
- `MoraleStateMachine` restores its transition state through its own
  `get_state()` and `set_state()`.

Unknown morale names or values are corrupt checkpoint data and must fail.
For a current engine checkpoint, both context keys are required. In a
production `ScenarioLoader` runtime, both stores must contain the expected
active-unit topology and agree on every current state before either is mutated.
A deliberately minimal engine runtime without a morale machine serializes the
engine checkpoint's `morale_machine` key as `null`; a direct context snapshot
keeps its legacy omission behavior. Aggregation proxies are excluded from
state-machine topology because their constituents remain the simulated morale
owners.

Initial and dynamic units are seeded from their side's validated
`morale_initial`. The two-store design itself remains a tracked ownership
boundary: later rout-cascade and aggregation writes can still diverge until
REM-019 is closed.

## RNG and derived state

RNG streams restore before engine continuation. Reconstructing force objects
must not consume a stream. Calibration's flattened, side-dependent view is
regenerated after force restoration.

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

The detailed production/action contract is
[ASAT Production Integration](asat-production-integration.md). The legacy
generic buffered Space ISR report representation remains tracked by REM-027
until Phase 112 gives it a typed semantic rehydration boundary.

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

- Current engine checkpoints contain `checkpoint_version: 111`; an unknown,
  malformed, boolean, older explicit, or newer explicit version is rejected.
- Current reinforcement wave ordinals and both morale-store enum values use
  non-boolean integers. Current wave side, configured arrival time, and full
  typed configuration must agree with the target schedule.
- Versionless engine checkpoints are treated as pre-108 only for bounded morale
  and reinforcement-ID migration, and only when logistics is disabled, space
  is not enabled, and no time-on-target mission is declared.
  Existing morale entries are still validated; missing active-unit entries are
  reconstructed from the checkpoint roster and the runtime's validated side
  configuration. A disagreement between present context and machine morale is
  never repaired silently.
- Legacy reinforcement entries without the current wave ordinal/config payload
  retain legacy IDs for units that already arrived. A pending legacy wave uses
  current stable IDs when it arrives, after which its next checkpoint is fully
  current.
- Direct `SimulationContext.set_state()` calls containing `units_by_side` or
  `morale_states` use exact replacement semantics, including an explicitly
  empty mapping. Direct legacy context calls that omit either section leave
  that corresponding runtime state unchanged. `SimulationEngine` additionally
  requires `units_by_side` for its campaign/roster preflight and both morale
  keys for version 111.
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
   dual-morale topology mismatches;
10. exact enabled-logistics restoration immediately before a cadence boundary
    into a fresh compatible runtime, followed by equivalent stock, route flow,
    event order, supply state, victory, and RNG continuation;
11. rejection of incomplete, corrupt, scenario-incompatible, foreign-plan, and
    mutated-plan logistics state without partial mutation;
12. hash-seed-independent canonical checkpoint bytes and logistics event order;
13. ordered mapping-registry/runtime-loadout topology and exact mutable
    weapon/sensor continuation;
14. complete space/ASAT action, service, inventory, satellite, debris, RNG, and
    before/after-action fresh continuation;
15. time-on-target continuation before fire, after a causal reserved pre-fire
    mutation, between fire and impact, during a shared-attachment plan, after
    completion/release, and for a disabled populated plan, plus atomic
    sentinel/lifecycle/resource/quantity-cooldown/target/RNG controls; and
16. relevant existing checkpoint, scenario, engine, entity, logistics, space,
    and indirect-fire regression suites.

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

The mapping registry and subsystem topology carry compatibility fingerprints,
but checkpoint files do not embed full content hashes for every external unit,
weapon, ammunition, sensor, era, or space catalog definition. Cross-revision
migration and complete catalog-content fingerprinting remain future
checkpoint-format work.
