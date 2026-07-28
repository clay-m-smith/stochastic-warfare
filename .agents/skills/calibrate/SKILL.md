---
name: calibrate
description: "Calibrate a Stochastic Warfare scenario against a predeclared, source-backed historical outcome envelope using guarded sensitivity analysis and held-out validation. Use when the user explicitly asks to tune scenario calibration parameters; never use calibration to conceal an engine gap or alter physical weapon performance to force an outcome."
---

# Scenario Calibration

Read `CODEX.md`, the relevant scenario specification, historical envelope, phase
material, and remediation backlog.

## Hard Preflight — REM-017

Before running analysis or changing scenario data, read REM-017 in
`docs/remediation-backlog.md`.

If REM-017 is not closed with behavioral evidence that the shared batch helper:

- loads the exact expected force roster and loadouts through `ScenarioLoader`;
- applies the requested override to runtime state;
- produces a controlled outcome difference for an outcome-affecting parameter;
- rejects unknown metrics and invalid or empty scenario loads;

stop. Do not run a sweep, infer parameter values, edit calibration, or report
zero-valued output as analysis. Report that calibration is blocked by REM-017
and identify the missing evidence. Do not work around this gate with structural
tests, skipped-unit warnings, a simplified runner, or an ad hoc unverified
harness.

Resume the workflow below only after that remediation is closed and reverified.

## Establish the Calibration Contract

1. Require a source-backed, predeclared historical envelope. Use `$backtest` if
   one does not exist.
2. Separate fixed physical inputs from legitimate scenario calibration.
3. Validate candidate field names and values against the current
   `CalibrationSchema`; never rely on remembered parameter names.
4. Prove each candidate parameter is loaded, wired, enabled, and
   outcome-affecting in the production path.
5. Freeze tuning seeds, held-out validation seeds, metrics, horizon, tolerances,
   and stopping criteria before tuning.

## Tune Carefully

1. Run and retain an unmodified baseline.
2. Bound each range with sources, schema constraints, or documented military
   plausibility.
3. Use a coarse sweep to measure sensitivity and interaction.
4. Use binary search only after demonstrating a monotonic relationship over the
   bounded interval.
5. When parameters interact, use an explicit multivariate design rather than
   silently fixing them one at a time.
6. Use common random numbers only with a paired analysis. Otherwise use
   independent seed sets and the corresponding statistical method.
7. Treat p-values as evidence about a specified null hypothesis, not confidence
   that the model matches history. Use effect sizes, confidence intervals, and
   the predeclared historical envelope.
8. Stop and record an engine or scenario-model gap when plausible permitted
   parameters cannot satisfy the envelope.

Never tune per-weapon physical performance to force a scenario result, weaken an
acceptance threshold after seeing a miss, validate on the tuning sample, or
describe a non-significant difference as equivalence.

## Validate and Record

1. Re-run the final candidate on held-out seeds.
2. Verify expected forces, weapons, sensors, events, and modeled interactions
   were exercised.
3. Run scenario-data validation, focused production tests, deterministic replay
   where applicable, scenario evaluation, and relevant broader suites.
4. Test disabled or baseline behavior that distinguishes a real effect from an
   unconditional result.
5. Document every changed value with its source and rationale.
6. Update the specification, phase devlog, and remediation status only after
   evidence passes.
7. Commit only as part of a completed coherent phase under `CODEX.md`.

Report exact parameters, bounds, tuning and validation seeds, commands, raw
results, statistics, envelope results, other-scenario effects, and remaining
discrepancies.
