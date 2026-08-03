---
name: postmortem
description: "Gate closure of a numbered implementation phase. Use after implementation, tests, review, and documentation updates but before marking the phase complete or creating its required commit."
---

# Run the Phase Postmortem

Follow `CODEX.md`. Use this review to decide whether a numbered phase is
actually complete, not to rationalize a green status.

## Reconstruct the Contract

Read the applicable roadmap, phase devlog, remediation entries, specifications,
original acceptance criteria, final production diff, and test diff. List:

- planned work delivered;
- planned work dropped, deferred, or changed;
- unplanned behavior added;
- accepted non-goals and assumptions.

Do not rely on the devlog's completion label as evidence.

## Audit Integration and Outcomes

For every changed capability, evaluate the applicable declared, loaded, wired,
enabled, exercised, outcome-affecting, and persisted/exposed stages. Require
production-path evidence and negative or disabled controls where applicable.

Inspect direct callers and runtime ownership, but treat imports, constructor
calls, config presence, event publication, mocks, source searches, and no-crash
runs as structural diagnostics only. Verify event subscribers, checkpoint
state, API exposure, or UI behavior only when the contract requires them.

## Review Test Quality

- Confirm that each fixed defect or changed behavior has a regression test that
  would fail without the implementation.
- Prefer realistic state transitions and outcomes over attribute assertions.
- Verify deterministic replay and checkpoint continuation for mutable or
  stochastic changes.
- Run scenario comparison, Monte Carlo, backtest, or performance evidence when
  the phase can change those outcomes.
- Run every relevant API, frontend, data, documentation, slow, terrain, E2E, or
  benchmark boundary explicitly.
- Record exact commands, pass/skip/deselect counts, timing, warnings, and suites
  not run. Do not treat the default Python suite as all coverage or use
  collection output as a passing count.

Rerun focused behavioral tests after any review-driven fix.

## Review Implementation and Documentation

Inspect the final diff for:

- stubs, placeholders, dummy values, unconditional success, swallowed
  exceptions, and log-only wiring;
- incomplete serialization, nondeterministic iteration, wall-clock use, or
  unsupported fallback behavior;
- public API, type, logging, dependency-direction, and data-semantic problems;
- TODOs, FIXMEs, performance regressions, and unexplained scope changes;
- missing specification, architecture, API, data, user-guide, devlog,
  remediation, status, or navigation updates;
- unrelated or user-owned changes.

Use an independent adversarial review for a material phase, then reproduce and
verify its findings from source and commands.

## Resolve the Verdict

Record:

- **Scope**: on target, under, or over;
- **Quality**: high, medium, or needs work;
- **Integration**: fully proven or gaps found;
- **New deficits**: identifiers, evidence, priority, and planned phase;
- **Validation**: exact results and exclusions;
- **Action items**: required before closure or explicitly deferred.

Add real deficits to `docs/remediation-backlog.md` and assign them to a roadmap
phase. If any applicable completion stage or required validation is missing,
reopen the phase, implement or track the finding honestly, rerun the affected
evidence, and repeat the postmortem.

When all gates pass, append the postmortem to the phase devlog, inspect
`git status --short`, `git diff --check`, and the complete phase diff, then
create one coherent commit containing only that phase's work. Do not include
unrelated files and do not push.
