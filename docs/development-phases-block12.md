# Block 12: Integrity Remediation

Block 12 converts the post-Phase-104 audit findings into verified production
behavior. It does not reopen every historical modeling choice. It repairs
specific claims where the declared, loaded, wired, exercised, outcome-affecting,
or persisted stages are missing.

The live issue inventory and evidence matrix are in
[`remediation-backlog.md`](remediation-backlog.md).

## Phase 105 - Checkpoint State Integrity

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

- Apply `config_overrides` to the scenario actually used by a run.
- Prove an override changes the intended production outcome.
- Make background task/database ownership safe through task completion and
  teardown.

Exit criteria: REM-002 and REM-003 are closed with API boundary tests.

## Phase 107 - Scenario Configuration Wiring

- Register scenario reinforcements automatically.
- Assign arriving units their defined weapons and sensors.
- Honor side initial morale.
- Make `disabled_modules` an effective, validated production gate.

Exit criteria: REM-004 through REM-007 have enabled, disabled, and
outcome-affecting controls where applicable.

## Phase 108 - Logistics Runtime Wiring

- Initialize scenario depots, stock, nodes, and routes.
- Advance supply-network state from the production loop.
- Apply configured idle consumption at the correct simulation resolution.

Exit criteria: REM-008 and REM-009 show controlled inventory and resupply
effects through production ticks.

## Phase 109 - Equipment Mapping Integrity

- Remove duplicate-key overwrite behavior.
- Replace unrelated proxy mappings with semantically correct data or explicit
  unsupported errors.
- Add uniqueness and semantic validation for equipment lookup maps.

Exit criteria: REM-010 is closed and the relevant Ruff checks pass.

## Phase 110 - ASAT Production Integration

Replace the placeholder hook with a gated production path that uses real
satellite and weapon state and persists its effects.

Exit criteria: REM-011 has enabled/disabled controls and an observable satellite
outcome.

## Phase 111 - Time-on-Target Execution

Carry real mission target and timing data into the indirect-fire engine, execute
each mission exactly once, and expose its result.

Exit criteria: REM-012 is closed with scheduled and negative controls through
the production loop.

## Phase 112 - Validation and Documentation Trust

- Make excluded Python suites explicit in CI and developer documentation.
- Audit critical structural/no-assert tests and replace false behavioral claims.
- Preserve the passing strict documentation baseline established during Phase
  105 and make its coverage routine.
- Reconcile public capability and status claims with the remediation evidence.

Exit criteria: REM-013 and REM-014 are closed, REM-015 remains green, all
relevant suites are reported explicitly, and the final Block 12 postmortem
identifies any newly discovered backlog items.
