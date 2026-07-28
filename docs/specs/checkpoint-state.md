# Checkpoint State Contract

## Status

Phase 105 contract, extended through Phase 107 on 2026-07-28.

## Purpose

A checkpoint is a deterministic branch point. Restoring it must reproduce the
mutable simulation state at time `T`, and continuing from it must produce the
same subsequent state and events as the uninterrupted seeded run.

The restore target must be a structurally compatible runtime built from the same
validated effective scenario configuration and repository/data-catalog
revision. Checkpoint restore replaces mutable state; it does not rebuild engine
topology or reinterpret a different scenario.

`SimulationEngine` writes checkpoint format version `107`. Any explicit version
other than `107` is rejected before runtime mutation. An absent version selects
the bounded legacy-migration path described below; an explicitly present
`null` value is malformed, not legacy.

For version `107`, top-level engine keys and context-state keys must exactly
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

## Compatibility

- Current engine checkpoints contain `checkpoint_version: 107`; an unknown,
  malformed, boolean, older explicit, or newer explicit version is rejected.
- Current reinforcement wave ordinals and both morale-store enum values use
  non-boolean integers. Current wave side, configured arrival time, and full
  typed configuration must agree with the target schedule.
- Versionless engine checkpoints are treated as pre-107 only for bounded morale
  and reinforcement-ID migration. Existing morale entries are still validated;
  missing active-unit entries are reconstructed from the checkpoint roster and
  the runtime's validated side configuration. A disagreement between present
  context and machine morale is never repaired silently.
- Legacy reinforcement entries without the current wave ordinal/config payload
  retain legacy IDs for units that already arrived. A pending legacy wave uses
  current stable IDs when it arrives, after which its next checkpoint is fully
  current.
- Direct `SimulationContext.set_state()` calls containing `units_by_side` or
  `morale_states` use exact replacement semantics, including an explicitly
  empty mapping. Direct legacy context calls that omit either section leave
  that corresponding runtime state unchanged. `SimulationEngine` additionally
  requires `units_by_side` for its campaign/roster preflight and both morale
  keys for version 107.
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
10. relevant existing checkpoint, scenario, engine, and entity regression
    suites.

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

Checkpoint files do not currently embed hashes for external unit, weapon,
ammunition, sensor, or era definitions. Cross-revision migration and catalog
fingerprinting belong to a future versioned checkpoint-format phase.
