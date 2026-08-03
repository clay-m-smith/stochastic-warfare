---
name: design-review
description: "Review a Stochastic Warfare subsystem or proposed design against current architecture, sourced military or mathematical foundations, production wiring, and observable behavior. Use for an explicit design review or before implementing a materially new simulation subsystem; do not treat this review as code acceptance or phase completion."
---

# Design Review

Read `CODEX.md` completely. Then read the current specification, relevant
architecture pages, remediation entry, phase material, implementation, and
behavioral tests. Treat `docs/brainstorm*.md` as historical design input, not
current authority when it conflicts with later specifications or production
behavior.

## Review the Contract

1. Restate the design's inputs, outputs, state, dependencies, configuration,
   enablement, persistence, and failure behavior.
2. Identify non-goals and scale or fidelity boundaries.
3. List unresolved choices rather than silently choosing the easiest behavior.

## Review Architecture and Wiring

Check only applicable items:

- dependency direction and separation of entity state from engine behavior;
- real production path from typed scenario input through `SimulationEngine`;
- hybrid clock/event semantics and logical-time use;
- ENU internal coordinates and boundary-only geodetic formats;
- explicit stateful dependency injection;
- deterministic iteration and project RNG stream discipline;
- complete checkpoint state for every affected mutable component;
- typed, data-driven configuration with explicit rejection;
- enabled and disabled behavior;
- recorder, API, or UI exposure where required;
- performance and multi-scale behavior, including current LOD or aggregation
  contracts rather than obsolete blanket fidelity claims.

## Review Domain Foundations

Use only theory and evidence relevant to the mechanism. Invoke military or model
research when a material claim lacks a source. Do not treat a named theorist as
evidence that a behavior is modeled.

For each claimed foundation:

1. cite the source and distinguish doctrine, theory, empirical data, and ethical
   constraints;
2. identify the concrete mechanic that expresses it;
3. define the observable outcome or emergent behavior expected;
4. identify counterexamples, degenerate cases, and conflicting frameworks.

## Trace Completion Evidence

Assess each applicable `CODEX.md` stage:

- Declared
- Loaded
- Wired
- Enabled
- Exercised
- Outcome-affecting
- Persisted or exposed

Use production-path behavior and tests as evidence. Imports, constructors,
attribute checks, source searches, log messages, and no-crash runs are
structural evidence only.

## Report

Produce:

1. reviewed contract and sources;
2. architecture findings with severity and file/line evidence;
3. domain-foundation findings and conflicts;
4. completion-matrix evidence and gaps;
5. emergent behaviors the design can and cannot produce;
6. prioritized recommendations and required tests;
7. residual assumptions and tracked limitations;
8. a design-only verdict: `APPROVED`, `APPROVED WITH NOTES`, or
   `NEEDS REVISION`.

Explicitly state that the verdict does not establish implementation completeness
or authorize a phase-complete status.
