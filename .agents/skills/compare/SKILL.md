---
name: compare
description: "Compare two Stochastic Warfare scenario configurations with reproducible production runs and statistically appropriate effect analysis. Use for same-revision A/B override comparisons or parameter impact checks; require stored baseline artifacts before claiming a before/after code-revision comparison."
---

# Configuration Comparison

Read `CODEX.md`, the relevant scenario contract, phase material, and remediation
backlog.

## Hard Preflight — REM-017

Before executing a comparison, read REM-017 in
`docs/remediation-backlog.md`.

If REM-017 is not closed with behavioral evidence that the shared batch helper:

- loads the exact expected force roster and loadouts through `ScenarioLoader`;
- applies both configurations to runtime state;
- detects a controlled outcome difference;
- rejects unknown metrics and invalid or empty scenario loads;

stop. Do not run or interpret the comparison. Report that comparison is blocked
by REM-017 and identify the missing evidence. Do not accept skipped-unit
warnings, all-zero metrics, structural tests, the simplified scenario runner, or
an ad hoc unverified harness as a workaround.

Resume only after the remediation is closed and reverified.

## Define the Comparison

1. Identify the scenario, code and data revision, configuration A,
   configuration B, labels, metrics, horizon, and decision the comparison must
   inform.
2. Scope the standard workflow to two configurations on the same code revision.
   For code-version comparison, require reproducible stored baseline results or
   an explicitly authorized isolated baseline environment; two override
   dictionaries do not compare code revisions.
3. Validate both configurations against current typed schemas.
4. Validate every metric against a supported extractor and fail on unknown
   names.
5. Predeclare run count, seeds, practical effect threshold, alpha where used,
   and treatment of multiple metrics.

## Verify the Production Inputs

Before interpreting results:

- assert the expected units, subclasses, weapons, sensors, and side counts
  loaded;
- prove the differing values reached runtime state;
- prove the simulation reached the behavior of interest;
- retain an exact input and seed record.

## Choose Statistics Consistently

- When A and B use the same seed for each pair, analyze per-seed paired
  differences with an appropriate paired method.
- When samples are independent, use independent-sample methods such as
  Mann-Whitney only when their assumptions fit.
- Report means or medians, dispersion, effect size, confidence interval, and raw
  seed-level direction.
- Do not call `p > alpha` equivalence or absence of effect. Use a predeclared
  equivalence margin and an appropriate equivalence method when equivalence is
  the question.
- Distinguish statistical significance from military or practical importance.

## Report

Report exact revisions, scenario, configurations, metrics, horizon, seeds,
commands, load preflight, summary statistics, effect sizes, uncertainty,
significance or equivalence interpretation, production-path evidence, and
limitations.

Do not mutate scenario data during a read-only comparison. If comparison
surfaces a defect, reproduce it behaviorally and route it through the phase and
remediation workflow in `CODEX.md`.
