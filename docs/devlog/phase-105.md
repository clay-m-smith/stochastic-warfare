# Phase 105 - Checkpoint State Integrity

**Status:** Complete

**Started:** 2026-07-28

**Completed:** 2026-07-28

## Why this phase exists

Phase 72 specified checkpoint/restore equivalence, including unit state, morale,
RNG, and continued outcomes. Its devlog records that the planned heavy
round-trip test was replaced by structural and mocked checks while the phase was
still marked complete.

The post-Phase-104 audit found the resulting production defect:
`SimulationContext.get_state()` serializes units and morale, but
`SimulationContext.set_state()` restores neither. Existing integration coverage
only proves clock/resolution restoration and does not exercise this contract.

## Requirements

The authoritative working requirements are REM-001 in
[`docs/remediation-backlog.md`](../remediation-backlog.md).

Acceptance criteria:

1. An in-place restore reproduces checkpoint unit and typed morale state exactly
   without breaking linked unit, crew, equipment, weapon, or sensor references.
2. Weapon ammunition, maintenance count, cooldown, and sensor condition restore
   through the bytes checkpoint path.
3. A fresh runtime with a different roster reconstructs the checkpoint roster
   and concrete unit subclasses without advancing RNG.
4. Runtime-only units are removed; stable matching objects retain identity.
5. Duplicate IDs, unknown/ambiguous subclasses, invalid morale, configuration
   mismatch, and loadout mismatch fail before context state is committed.
6. Older checkpoints without force/morale/loadout sections retain the existing runtime
   roster, and class-less unit snapshots restore by deterministic inference.
7. A production `SimulationEngine` run continued after fresh restore matches an
   uninterrupted control run.
8. A fully loaded scenario restores real weapon state and continues identically.

## Non-goals

- Reinforcement registration and reinforcement loadout assignment remain Phase
  107 work.
- This phase will not mark unrelated subsystem state complete merely because
  its engine exposes `get_state()` and `set_state()`.
- A versioned checkpoint migration framework is deferred.

## Evidence

### Red

- Initial command:
  `uv run python -m pytest tests/unit/test_phase_105_checkpoint_integrity.py -q --tb=short`
- Result before implementation: **7 failed, 1 passed**.
- Failures proved missing entity/morale restoration, roster reconstruction,
  corruption handling, and fresh-engine continuation.
- Independent adversarial review then found a deeper false green: a real weapon
  resumed with 10 rounds instead of the checkpoint's 7, yet both serialized
  branches compared equal because weapon state was not captured.
- A fully loaded production scenario exposed non-JSON era sets and intermittent
  ordering from `BattleContext.unit_ids`; both were repaired and regression
  tested.

### Green

- Phase 105 behavioral suite: **19 passed in 1.70s**.
- Covers every concrete unit class, stable nested references, typed morale,
  weapon ammo/maintenance/cooldown, sensor condition, JSON-canonical
  configuration, exact loadout topology, linked-equipment consistency, legacy
  payloads, atomic rejection, engine cadence consistency, deterministic
  continuation, and a real `ScenarioLoader` scenario.
- The loaded-scenario round trip was repeated five times to exercise stable
  battle serialization: **5/5 passed**.

### Broader verification

- All checkpoint-selected tests, with default exclusions disabled:
  **103 passed, 1 skipped**.
- Entity, concrete-unit, ammunition, and detection regressions:
  **189 passed**.
- Full default Python suite from the final source state:
  **10,123 passed, 21 skipped, 346 deselected** in 4m03s.
- Focused Ruff over every touched Python file: **passed**.
- Strict MkDocs build with the docs extra: **passed**.
- `git diff --check`: **passed**; Git emitted only repository line-ending
  conversion notices.
- Repository-wide Ruff remains blocked by the previously audited baseline:
  six duplicate literal mapping keys (REM-010) and two redundant f-strings.

## Implementation notes

- `Unit.get_state()` now emits a fixed class discriminator.
- Restore resolves only the six supported concrete classes, with safe legacy
  field inference and ambiguity rejection.
- Existing unit, personnel, and equipment objects are reused by stable ID,
  preserving live subsystem references.
- Context restore stages and validates configuration, clock/RNG, force, morale,
  and weapon/sensor state before committing.
- Weapon ammunition, missile state, maintenance count, equipment state, and fire
  cooldown now survive bytes checkpoints.
- Engine resolution and logical-clock cadence must agree before restore.
- Battle unit IDs serialize in sorted order.
- Era configuration uses JSON-mode dumping, so fully loaded contexts are
  checkpointable.

## Residual limitations

- A restore target must use the same repository/data-catalog revision; external
  definition hashes are not embedded in the checkpoint.
- Dynamic reinforcement registration and loadouts remain REM-004/REM-005.
- Aggregation still reconstructs constituents as base units and discards
  attachments; this common-mode defect is REM-016.
- API, E2E, slow, terrain, and benchmark suites were not required for this
  core checkpoint boundary and remain outside the default suite as documented.
