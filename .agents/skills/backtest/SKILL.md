---
name: backtest
description: "Design or execute a source-backed historical validation of Stochastic Warfare output against a predeclared engagement outcome envelope. Use when testing simulation fidelity against real events or defining historical regression criteria; keep backtesting separate from calibration and generic software regression."
---

# Historical Backtest

Read `CODEX.md`, the relevant specification and remediation entry, and
`docs/scenarios/calibration-template.md`. Use the real
`ScenarioLoader -> SimulationContext -> SimulationEngine` path; never use
`stochastic_warfare/validation/scenario_runner.py` as proof of production
behavior.

## Separate Validation from Calibration

Freeze the historical claims, metrics, uncertainty, tolerances, and acceptance
rules before observing the candidate simulation results. Use a backtest to
measure fidelity. Use calibration, if separately authorized, only after the
backtest contract is fixed.

Do not widen a missed envelope, change seeds, remove a metric, or redefine the
historical population without owner approval and a documented modeling
rationale.

## Source the Historical Record

Use the source discipline in the repository research skills:

- Tier 1 authoritative or primary sources for central outcome and parameter
  claims;
- Tier 2 peer-reviewed or academic sources where primary evidence is
  unavailable;
- Tier 3 only for supplementary context or corroboration.

Record full citations, direct links, page or section, definitions, contested
figures, and confidence. Reconcile differences such as KIA versus total
casualties, committed versus present force, and engagement versus campaign
duration.

## Define the Backtest

Specify:

1. engagement scope, historical timeline, forces, terrain, weather, posture,
   intelligence state, objectives, and known limitations;
2. exact scenario mapping to data-driven units, weapons, sensors, and
   calibration;
3. each metric's historical value or range, source, extraction path, tolerance,
   rationale, and diagnostic meaning;
4. winner, duration, casualties, equipment losses, ammunition, movement,
   territorial control, and key dynamics where data permits;
5. predeclared seeds, run count, simulation horizon, summary statistics,
   confidence intervals, and acceptance rules;
6. code revision, data revision, scenario hash or exact input, and commands
   needed to reproduce the run.

Use `stochastic_warfare/tools/envelope_check.py` and relevant
`tests/validation/` helpers where their contracts fit. Do not use the
REM-017-affected batch route unless that remediation is closed with behavioral
evidence. Assert that expected units and loadouts were loaded before interpreting
outcomes.

## Execute and Diagnose

1. Validate scenario data.
2. Run a deterministic seed smoke test through production.
3. Verify the run reaches the modeled behavior rather than timing out before
   contact.
4. Run the predeclared Monte Carlo sample.
5. Compare distributions and historical uncertainty without calling a
   non-significant result proof of equivalence.
6. Attribute divergence to historical uncertainty, scenario mapping, model
   deficiency, or calibration only when evidence distinguishes them.
7. Record failed backtests as useful findings and add a remediation item when
   they expose a production gap.

## Report

Report sources, frozen envelope, exact configuration, seeds, commands, raw or
retained result location, statistics, pass/fail by metric, sensitivity to
assumptions, production-path evidence, and limitations. Never tune and validate
on the same sample while describing it as independent historical validation.
