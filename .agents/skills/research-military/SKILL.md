---
name: research-military
description: "Research authoritative military doctrine, history, operational evidence, and relevant strategic or ethical theory for Stochastic Warfare. Use when a task introduces or changes military behavior, historical claims, doctrine, scenario assumptions, or military parameters that need traceable sources; do not use for routine implementation whose contract is already sourced."
---

# Military Research

Read `CODEX.md`, the relevant specification, phase material, and remediation
entry before researching. Treat research as input to a design or implementation,
not as proof that runtime behavior exists.

## Define the Question

1. State the concrete modeling decision or historical claim to resolve.
2. Identify the required scale, era, force, environment, units, and uncertainty.
3. Trace the current production model enough to know which claims and parameters
   need evidence.
4. Separate descriptive questions about observed behavior from prescriptive
   doctrine, legal rules, ethical frameworks, and theorist interpretations.

## Source Discipline

Classify every cited source and link to the source itself.

### Tier 1 — Primary or Authoritative

- Official doctrine, field manuals, technical manuals, after-action reports, and
  government technical reports
- Official military histories and archival records
- NATO standards and equivalent allied publications
- Original theorist, legal, philosophical, or ethical texts
- FFRDC research when its evidence and methods are inspectable

### Tier 2 — Academic or Peer-Reviewed

- Peer-reviewed military history, operations research, psychology, sociology,
  political science, and defense-modeling research
- Established academic monographs and textbooks
- Academic-press critical editions or translations

### Tier 3 — Supplementary Reference

- Jane's, IISS, RUSI, CRS, and established military-history publishers
- Well-sourced secondary analysis used to locate or corroborate stronger sources

Use Tier 3 only as supplementary context. Do not base a numerical simulation
parameter solely on Tier 3 evidence. Treat search indexes as discovery tools, not
sources, and identify preprints as non-peer-reviewed.

Exclude unsourced claims, personal blogs, forums, gaming references, social
media, commentary videos, and sources without a verifiable citation chain.

## Research Workflow

1. Prefer the closest primary evidence for the exact era and phenomenon.
2. Seek dissenting findings and non-Western perspectives where material.
3. Distinguish observed distributions from doctrine, anecdotes, and normative
   theory.
4. Record page, table, figure, or section locations for material claims.
5. Reconcile conflicting definitions, populations, time windows, and units.
6. Translate evidence into candidate mechanics only when the evidence supports
   that translation.
7. State parameter units, plausible ranges, uncertainty, correlation, boundary
   conditions, and what the evidence cannot establish.
8. If implementation is in scope, place citations and material assumptions in
   the relevant specification, model documentation, or scenario data.

## Output

For each material finding, report:

- claim or finding;
- full citation and direct link;
- source tier and evidence type;
- relevant page or section;
- applicability and limitations;
- conflicting evidence;
- modeling implication, including units and uncertainty where applicable.

Conclude with the recommended synthesis, rejected alternatives, unresolved
research gaps, and the exact decisions that still require owner judgment. Never
turn a theorist namecheck or a sourced constant into an implementation-complete
claim.
