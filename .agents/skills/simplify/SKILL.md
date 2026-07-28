---
name: simplify
description: Review a completed phase diff for unnecessary duplication, complexity, coupling, inefficient patterns, weak interfaces, and brittle tests. Use after substantial implementation, before final documentation and a phase commit, or when integration failures indicate avoidable coupling.
---

# Simplify the Phase Diff

Review the current phase's changes for clarity, reuse, and maintainability
without changing verified behavior. A review request is read-only. During an
authorized implementation phase, correct only in-scope findings and rerun every
affected validation gate.

## Establish the Real Diff

1. Read `CODEX.md`, the phase requirements, and acceptance criteria.
2. Record `git status --short`.
3. Use the recorded phase-start revision plus the current working tree. Do not
   assume `HEAD~1` is the phase boundary.
4. Include in-scope untracked files and exclude unrelated user changes.
5. Review production code and its tests together.

## Review in Order

### Duplication and Existing Abstractions

- Search with `rg` for existing helpers, constants, fixtures, schemas, and
  subsystem interfaces before proposing extraction.
- Identify genuinely repeated policy or behavior, not merely similar syntax.
- Preserve intentionally independent domain implementations when consolidation
  would create coupling.

### Complexity and Responsibility

- Identify deep nesting, many branches, long imperative sequences, and methods
  that combine loading, policy, mutation, and reporting.
- Treat line, branch, and nesting counts as prompts for inspection rather than
  automatic defects.
- Prefer well-named extraction or early returns only when they make invariants
  clearer and reduce total cognitive load.
- Do not add an abstraction that is larger or less stable than the duplication
  it replaces.

### Performance Candidates

- Look for repeated work, unnecessary allocation, full scans, spatial-query
  bypasses, and costly work inside tick loops.
- Do not assume vectorization, caching, pre-sorting, or indexing is safe or
  faster.
- Route material performance claims through `$profile`.
- Preserve deterministic ordering and RNG consumption.

### Interface and State Quality

- Check public types, parameter clarity, validation, error behavior, and single
  responsibility.
- Prefer typed Pydantic models for configuration and data boundaries; do not
  force domain state objects into inappropriate models.
- Check complete mutable-state serialization and restoration.
- Check whether callers can accidentally bypass required loader, manager, or
  feature gates.

### Test Quality

- Prefer observable production-path state transitions, events, resources,
  timing, outcomes, replay, and persistence.
- Flag tests that prove only imports, construction, key presence, mocked calls,
  source strings, or no-crash behavior.
- Look for meaningful negative, disabled, empty, zero, corrupt, and boundary
  cases.
- Reuse `tests/conftest.py` fixtures when they express the same contract without
  hiding important setup.
- Tests of the simplified validation runner do not establish production engine
  wiring.

### Repository Conventions

Apply `$validate-conventions` to simulation-core Python changes and the other
applicable skill gates defined in `CODEX.md`.

## Classify and Act

For every finding, provide:

- file and line;
- category;
- severity: `HIGH`, `MEDIUM`, or `LOW`;
- concrete cost or risk;
- smallest coherent remedy;
- whether it is in phase scope.

For a review-only request, report findings without editing. During an authorized
phase:

- fix in-scope findings needed for correctness or maintainability;
- defer valid scope expansions to `docs/remediation-backlog.md`;
- leave optional churn alone;
- return to focused and relevant boundary tests after any edit.

Do not refactor solely to satisfy a heuristic, alter expected behavior, or mix
unrelated cleanup into the phase commit.

## Gate the Phase

Conclude with one of:

- `CLEAN`: no material simplification is needed;
- `READY AFTER IN-SCOPE FIXES`: fixes were made and revalidated;
- `NOT READY`: unresolved high-risk findings remain;
- `DEFERRED ITEMS RECORDED`: only legitimate out-of-scope work remains.

Report exact checks, results, exclusions, and residual limitations. Complete
documentation and the phase commit only after the final diff remains coherent.
