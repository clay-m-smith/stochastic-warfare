---
name: audit-determinism
description: Audit simulation reproducibility, RNG stream discipline, deterministic ordering, and checkpoint continuation. Use when Codex changes stochastic logic, event ordering, iteration that affects state, RNG allocation, checkpoint state, or deterministic parallel execution, and before completing a stochastic simulation phase.
---

# Audit Determinism

Audit the requested target or the current phase's affected stochastic production
path. Treat the audit as read-only unless the user has also authorized
implementation. Read the relevant specification and `CODEX.md` invariants before
classifying findings.

Comparable behavioral evidence must use
`SimulationRuntimeFactory.prepare / prepare_config -> PreparedScenario.build ->
RuntimeSession` with fresh sessions for each replay. Direct
`ScenarioLoader`/`SimulationEngine` construction and the separate simplified
`stochastic_warfare/validation/scenario_runner.py` may support diagnostics, but
do not establish determinism in the production runtime path.

## Establish Scope

1. Derive the target from the user request and current phase diff.
2. Identify the production entry point, affected subsystem, mutable state, event
   queues, and stochastic dependencies.
3. Expand to the whole simulation core only when explicitly requested or when
   the target cannot be audited safely in isolation.
4. Record the seed, scenario/configuration, phase-start revision, and working
   tree state used for behavioral checks.

## Trace Randomness

For every stochastic decision in scope:

1. Identify its `RNGManager`-owned authority.
2. For conventional draws, trace the injected `numpy.random.Generator` to
   `RNGManager.get_stream(ModuleId.<SUBSYSTEM>)` and confirm the module ID.
3. For indexed decisions, trace the typed allocation/commit lifecycle through
   `RNGManager`, verify the stable semantic identity and decision domain, and
   prove that worker completion order cannot change values or transcript order.
4. Confirm stateful subsystems do not share a conventional generator or reuse
   an indexed identity accidentally.
5. Flag Python `random`, module-level `np.random` draws, `RandomState`, hidden
   generator construction, direct production construction of indexed RNG
   owners, or an unseeded generator in simulation logic.

Direct generator construction is expected inside the central RNG implementation
and may be appropriate in isolated tests or tooling. It is not evidence that
production simulation logic follows the injected-stream contract.

Useful candidate searches include:

```powershell
rg -n "import random|from random|RandomState|default_rng|np\.random|Generator" stochastic_warfare tests
rg -n "get_stream|ModuleId|bit_generator|rng" stochastic_warfare
```

Search results are candidates. Trace control and data flow before reporting a
violation.

## Audit Ordering and External Inputs

Check whether repeated runs with identical inputs consume randomness and mutate
state in the same order:

- Trace set, mapping, filesystem, database, and event-queue iteration before
  draws, state changes, or event publication.
- Check tie-breaking, sorting keys, early exits, retries, and exception paths.
- Check use of wall-clock time, process IDs, object identity, randomized hashes,
  filesystem order, and race-dependent results in simulation logic.
- Check floating-point reductions whose order can vary.
- Check parallel work for deterministic seed assignment, isolated state, stable
  result ordering, and deterministic reduction.

A conditional branch consuming a different number of draws for a different
simulation state is not automatically a defect. It is a defect when identical
initial state and inputs can take different paths, when unrelated behavior
perturbs a shared stream, or when a documented common-random-number comparison
contract is broken.

Outer Monte Carlo parallelism is not automatically a violation. It must assign
seeds independently of scheduling and combine results deterministically.

## Audit Stream Stability

- Prove that adding or consuming draws in subsystem A does not perturb subsystem
  B.
- Inspect `stochastic_warfare/core/rng.py` and
  `stochastic_warfare/core/types.py::ModuleId` when stream allocation changes.
- The current manager derives child streams in `ModuleId` enumeration order.
  Treat changes to that allocation order as a compatibility risk requiring
  explicit tests; do not claim keyed allocation is already guaranteed.

## Audit Persistence

For every affected mutable or stochastic component:

- Verify complete `get_state()` and `set_state()` coverage.
- Verify `RNGManager` state is captured and restored.
- Include clocks, queues, unit/subsystem state, victory, recorder, and enabled
  optional systems where applicable.
- Reject incompatible or corrupt state atomically when required by the contract.

Key presence and round-trip serialization alone are structural evidence.

## Require Behavioral Evidence

Use focused tests appropriate to the target and include:

1. Two fresh production-path runs with the same seed, configuration, and data,
   comparing complete relevant state, ordered events, and outcomes.
2. A checkpoint continuation test that compares restored execution against an
   uninterrupted control.
3. A stream-isolation test when stream ownership or stochastic call placement
   changed.
4. A disabled or negative control when it distinguishes genuine deterministic
   wiring from unconditional behavior.

Run the relevant excluded suites explicitly as described in `CODEX.md`. Do not
describe source searches, mocked calls, key checks, or a simplified-runner test
as replay proof.

## Report

For each finding, provide:

- file and line;
- affected RNG stream or ordering source;
- status: `CONFIRMED`, `NEEDS BEHAVIORAL TEST`, or `CLEAN`;
- concrete replay consequence;
- evidence command and result;
- required fix or test.

End with `DETERMINISTIC`, `NON-DETERMINISTIC`, or
`CONDITIONALLY DETERMINISTIC`, plus explicit assumptions, unrun suites, and
residual limitations. If an authorized phase fix changes code, rerun the
focused, replay, checkpoint, and relevant boundary checks before completion.
