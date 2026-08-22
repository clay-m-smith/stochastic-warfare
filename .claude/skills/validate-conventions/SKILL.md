---
name: validate-conventions
description: Review changed Python against Stochastic Warfare's simulation conventions and production architecture. Use after modifying simulation-core code, public APIs, typed configuration, state serialization, coordinates, logging, or deterministic execution, and before a phase commit.
---

# Validate Conventions

Review the requested Python target or the current phase's changed Python files.
Treat this as a read-only review unless the task also authorizes implementation.
Use `CODEX.md` as the canonical rule set and inspect the real production path
before classifying findings.

## Establish Scope

1. Record `git status --short`.
2. Identify the phase-start revision and the changed or newly created Python
   files in scope. Do not assume `HEAD~1` represents the current phase.
3. Preserve unrelated and user-owned changes.
4. Default the package scope to `stochastic_warfare/`, `api/`, and affected
   tests. Scan the entire repository only when requested.

## Review Rules

### Randomness

- Production stochastic decisions must use `RNGManager`-owned authority: an
  injected `numpy.random.Generator` from
  `RNGManager.get_stream(ModuleId.<SUBSYSTEM>)`, or the typed indexed
  allocation/commit boundary for order-independent FOW decisions.
- Flag Python `random`, legacy/global `np.random` draws, hidden generator
  construction, direct indexed-owner construction, incorrect stream or
  decision-domain selection, reused indexed identities, and unintended stream
  sharing.
- Allow central RNG initialization and purpose-built test/tool generators when
  they do not bypass the production contract.

### Deterministic State and Events

- Trace iteration that affects state, draw order, event order, serialization, or
  outcomes.
- Do not flag mapping iteration merely because it is a mapping. Establish
  whether its construction and required order are deterministic.
- Check stable tie-breakers and serialized ordering.

### Coordinates and Time

- Simulation math uses ENU meters.
- Geodetic values are valid only at import, export, conversion, and display
  boundaries.
- Simulation behavior uses the logical clock. Wall-clock timing is valid only
  in profiling, logging metadata, and non-simulation boundaries.

Variable-name searches identify candidates, not violations.

### Architecture and State

- Preserve the dependency direction and keep entities as state rather than
  subsystem engines.
- Construct and inject stateful dependencies; do not introduce global engine
  instances.
- Public APIs require parameter and return type hints.
- Configuration and data inputs use typed Pydantic models and reject unsupported
  input explicitly.
- Every affected stateful component serializes and restores all mutable state.
- Optional features require verified enabled and disabled behavior.

### Logging

Simulation-core code uses
`stochastic_warfare.core.logging.get_logger`. Bare `print()` is acceptable only
at CLI, script, and test-utility boundaries.

## Inspect and Verify

Use `rg` to find candidates, then read surrounding control flow. For example:

```powershell
rg -n "import random|from random|RandomState|default_rng|np\.random" stochastic_warfare api
rg -n "time\.time|datetime\.now|print\(" stochastic_warfare api
rg -n "latitude|longitude|for .* in .*set|\.items\(\)" stochastic_warfare
```

Run Ruff on the changed Python paths:

```powershell
uv run ruff check <changed-python-paths>
```

Run focused behavioral tests for every confirmed concern. Static checks,
imports, constructors, source searches, mocks, and no-crash runs cannot prove
that a feature is loaded, wired, enabled, exercised, or outcome-affecting.
Tests of `stochastic_warfare/validation/scenario_runner.py` do not prove the
production engine path.

## Report

Group results by file and report:

- severity: `CRITICAL`, `WARNING`, or `CLEAN`;
- exact line and rule;
- `CONFIRMED` or `CANDIDATE`;
- why production behavior is affected;
- recommended fix and behavioral evidence;
- commands run, results, exclusions, and limitations.

Do not silently edit findings during a review-only request. During an authorized
phase implementation, correct only in-scope issues, rerun affected checks, and
place legitimate scope expansions in the remediation backlog.
