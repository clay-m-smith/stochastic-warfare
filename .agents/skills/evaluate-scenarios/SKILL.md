---
name: evaluate-scenarios
description: Run production-engine scenario regressions and compare semantic outcomes against an explicit provenance-recorded baseline. Use after changes to battle flow, engagement resolution, movement, detection, morale, logistics, victory, calibration, scenario data, or any feature that can alter simulated outcomes.
---

# Evaluate Scenarios

Use `scripts/evaluate_scenarios.py` as a production-engine regression harness.
It loads scenarios with `ScenarioLoader` and runs `SimulationEngine`, but it is
not the API execution path and does not by itself prove complete production
wiring or stochastic fidelity.

## Establish Applicability and Provenance

1. Identify the changed behavior and scenarios capable of exercising it.
2. Select an explicit prior baseline; never infer one only from the highest
   filename or newest timestamp.
3. Record the command, seed or seed set, phase-start/current revision, working
   tree state, scenario/configuration, data-catalog revision, enabled features,
   and evaluator exclusions.
4. Predeclare scenario-specific metrics and tolerances from the phase contract
   or cited historical evidence.

Existing `scripts/evaluation_results*.json` files are ignored local artifacts
and do not contain complete provenance. Treat them as comparison inputs only
after verifying how they were produced.

## Run Focused Evaluation First

Write current results outside the repository while iterating:

```powershell
uv run python scripts/evaluate_scenarios.py --scenario <scenario-id> --output C:\tmp\scenario-evaluation-current.json --no-details --seed <seed>
```

Confirm the requested scenario matched and the command succeeded. Investigate
all load/run errors, stalls, zero-activity diagnostics, and unexpected
conditions before broadening the run.

## Run the Relevant Broad Set

When the phase can affect multiple scenarios:

```powershell
uv run python scripts/evaluate_scenarios.py --output C:\tmp\scenario-evaluation-current.json --no-details --seed <seed>
```

The evaluator excludes internal `test_campaign*` and `benchmark_*` scenarios.
Report those exclusions and run separate tests when they matter.

The harness manually constructs victory evaluation and registers reinforcement
configuration. Its reinforcement setup can mask a failure in another production
entry point. It also reads recorder internals for diagnostics. Supplement it
with focused `SimulationEngine`, checkpoint, API, and end-to-end tests whenever
the completion matrix requires those boundaries.

## Compare Semantic Results

For every affected scenario compare:

- success or error;
- winning side and victory condition;
- ordered material events and resolution behavior;
- ticks and simulated duration;
- force state and casualties;
- movement and engagement diagnostics;
- newly introduced, resolved, or changed diagnostic issues.

Do not treat absolute local paths or wall-clock duration in result JSON as
semantic outcome differences. Do not use a universal casualty threshold.
Apply the predeclared scenario-specific tolerance and explain every material
change.

Classify each result as:

- `EXPECTED IMPROVEMENT`, supported by a requirement or cited historical
  source;
- `EXPECTED CHANGE`, supported by the phase contract;
- `REGRESSION`, contradicting the contract or losing prior behavior;
- `NEEDS INVESTIGATION`, when evidence is insufficient;
- `UNCHANGED`.

Never label an outcome historically more accurate from intuition alone.

## Add Stochastic Evidence

A single fixed seed is useful for regression and replay diagnosis, not for
distributional fidelity.

When changes can alter stochastic outcomes:

1. Repeat the comparison over a predeclared seed set.
2. Use the project's Monte Carlo or comparison tooling where applicable.
3. Report effect sizes, uncertainty, and original tolerances.
4. Use `$audit-determinism` for RNG, ordering, cache, checkpoint, or parallel
   changes.

Do not adjust thresholds after seeing a miss without explicit approval and a
documented modeling rationale.

## Review Before Promotion

Do not rename, overwrite, delete, or promote a baseline merely because the
script exits successfully. First:

1. investigate all regressions and unexplained changes;
2. complete focused production-path and relevant boundary tests;
3. record exact evidence and limitations in the phase devlog when phase scope
   authorizes documentation changes;
4. choose a new local baseline name only after the results are accepted.

## Report

Provide a table with scenario, baseline/current winner and condition, material
metric deltas, diagnostic changes, and classification. Then report:

- improvements and expected changes;
- regressions and stalls;
- unchanged scenarios;
- seed/provenance details;
- exact commands and results;
- evaluator exclusions and missing production boundaries;
- whether baseline promotion is justified.

Passing this harness is scenario-regression evidence, not proof that every
declared field is loaded, wired, enabled, persisted, exposed, or exercised
through the API.
