# Checkpoint State Contract

## Status

Phase 105 contract, adopted 2026-07-28.

## Purpose

A checkpoint is a deterministic branch point. Restoring it must reproduce the
mutable simulation state at time `T`, and continuing from it must produce the
same subsequent state and events as the uninterrupted seeded run.

The restore target must be a structurally compatible runtime built from the same
validated effective scenario configuration and repository/data-catalog
revision. Checkpoint restore replaces mutable state; it does not rebuild engine
topology or reinterpret a different scenario.

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
7. remove weapon/sensor map entries for units that could not be safely reused.

The checkpoint's effective scenario configuration must match the runtime
configuration. Weapon and sensor instance counts, ordering, and identities must
match for every non-empty serialized loadout. An incompatible runtime fails
before context-owned clock, RNG, force, morale, or loadout state is committed.

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

## RNG and derived state

RNG streams restore before engine continuation. Reconstructing force objects
must not consume a stream. Calibration's flattened, side-dependent view is
regenerated after force restoration.

## Compatibility

- Checkpoints containing `units_by_side` and `morale_states` use exact
  replacement semantics, including an explicitly empty mapping.
- Older checkpoints that omit either section leave that corresponding runtime
  state unchanged.
- Older unit snapshots without `unit_class` infer the class from its unique
  subclass field. A snapshot with no subclass field restores as `Unit`.
- Unknown explicit discriminators fail; they never silently downgrade to
  `Unit`.
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
7. relevant existing checkpoint, scenario, engine, and entity regression suites.

## Tracked boundaries

Checkpoint-only units can reconstruct their entity and equipment state, but
production weapon/sensor definitions and attachment topology remain
scenario-derived. Runtime instance state is serialized, while restoring a
non-empty loadout requires the compatible runtime to have constructed matching
instances. Fully registering loadouts for dynamic reinforcement units is
REM-005.

Aggregation/disaggregation also owns constituent reconstruction and attachment
restoration. Its current base-unit reconstruction gap is tracked separately and
must be closed before checkpoint equivalence is claimed across an aggregation
boundary.

Checkpoint files do not currently embed hashes for external unit, weapon,
ammunition, sensor, or era definitions. Cross-revision migration and catalog
fingerprinting belong to a future versioned checkpoint-format phase.
