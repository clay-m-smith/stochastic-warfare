---
name: what-if
description: "Run guarded parameter sensitivity analysis for a specific Stochastic Warfare scenario and explain how outcomes respond across a defensible range. Use for explicit what-if or sensitivity questions about a schema-valid, wired parameter; do not silently default to a generic scenario or infer effects from unexercised runs."
---

# What-If Analysis

Read `CODEX.md`, the relevant scenario contract, phase material, and remediation
backlog.

## Hard Preflight — REM-017

Before executing a sweep, read REM-017 in `docs/remediation-backlog.md`.

If REM-017 is not closed with behavioral evidence that the shared batch helper:

- loads the exact expected force roster and loadouts through `ScenarioLoader`;
- applies the swept value to runtime state;
- demonstrates a controlled outcome effect;
- rejects unknown metrics and invalid or empty scenario loads;

stop. Do not run, plot, or interpret a sweep. Report that what-if analysis is
blocked by REM-017 and identify the missing evidence. Do not accept skipped-unit
warnings, zero-filled results, a short no-contact run, structural tests, the
simplified scenario runner, or an ad hoc unverified harness as a workaround.

Resume only after the remediation is closed and reverified.

## Define the Question

1. Require an explicit scenario or infer one unambiguously from the current
   task; never silently use `test_campaign`.
2. Identify the decision, parameter, baseline, metrics, horizon, and sides
   affected.
3. Validate the parameter and values against the current typed schema.
4. Prove the parameter is loaded, wired, enabled, and outcome-affecting.
5. Bound the range with sources, schema constraints, or documented scenario
   plausibility. Include the current baseline.
6. Predeclare seeds, iterations, horizon, and uncertainty summaries.

## Run a Meaningful Sweep

1. Assert expected units, subclasses, weapons, sensors, and side counts loaded.
2. Confirm the run reaches contact or the behavior of interest before the
   horizon.
3. Use the same paired seed sequence across sweep points when analyzing
   per-seed changes; otherwise use independent samples intentionally.
4. Retain raw seed-level results.
5. Report mean or median, dispersion, confidence intervals, baseline delta, and
   outcome frequency as applicable.
6. Identify thresholds or non-monotonic regions only when the observations
   support them. Do not label a sparse curve linear, exponential, or causal
   without model evidence.
7. Distinguish sensitivity from historical validity and practical military
   significance.

## Visualize and Report

Create a plot only when it materially clarifies the relationship. Save it to an
explicit user-requested artifact path or a temporary/output location, not an
untracked repository path.

Report the exact scenario, revision, parameter, values, baseline, metrics,
horizon, seeds, commands, load preflight, statistics, observed relationship,
uncertainty, and limitations. Never predetermine the direction of the result or
change production configuration during exploratory analysis.
