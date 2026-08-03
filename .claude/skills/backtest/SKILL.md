---
name: backtest
description: "Design or execute a source-backed historical validation of Stochastic Warfare output against a predeclared engagement outcome envelope. Use when testing simulation fidelity against real events or defining historical regression criteria; keep backtesting separate from calibration and generic software regression."
---

# Historical Backtest

Read `CODEX.md`, the relevant specification and remediation entry, the strict
claim ledger, and the proposed study plan. The Block 11
`docs/scenarios/calibration-template.md` is superseded development history, not
a required input or current validation contract.

Use only this typed production route:

```text
HistoricalClaimLedgerLoader -> HistoricalStudyLoader
  -> SimulationRuntimeFactory.prepare -> PreparedScenario
  -> HistoricalBacktestRunner -> atomic artifact write
  -> load_historical_artifact (reload validation)
```

Never use `stochastic_warfare/validation/scenario_runner.py`, direct
context/engine construction, legacy `documented_outcomes`, Block 11 envelope
helpers, or an unvalidated output file as proof of production historical
behavior.

## Separate Validation from Calibration

Freeze the historical claims, metrics, uncertainty, tolerances, and acceptance
rules before observing the candidate simulation results. Use a backtest to
measure fidelity. Use calibration, if separately authorized, only after the
backtest contract is fixed.

Do not widen a missed envelope, change seeds, remove a metric, or redefine the
historical population without owner approval and a documented modeling
rationale. A failed frozen contract remains `FAIL`; a later materially changed
contract is a new, independently justified and immutably predeclared study, not
a repair of the result.

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
duration. For each metric, bind the exact source assertion and source IDs to an
inclusive range, source unit, historical event boundary, and conflict notes.
Declare whether each validation source is independent, reused, or of unknown
relationship to scenario authoring and calibration.

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

Declare the study under `data/validation/historical_studies/`, bind every
accepted claim metric explicitly to a gating metric, and execute it through
`scripts/run_historical_backtest.py`. Each extractor declaration must name its
closed extractor ID, exact side/status/unit-type and roster scope where
applicable, runtime unit, lossless conversion, and source-synchronous event
boundary. Censoring must remain explicit; a study cutoff is not a natural
terminal outcome.

Use relevant test helpers only as diagnostics where their contracts fit.
Before interpreting outcomes, assert exact typed roster and unit identity,
loadouts, catalog, doctrine, assignments, effective era, source/config,
code/data, execution-ledger digest and claim bindings, plan digest, ordered
held-out seeds, and runtime provenance.

For a promotion-capable study, commit the complete plan before held-out
execution and record its immutable ancestor revision. The frozen committed
contract must match the executed plan exactly. A dirty run or a plan first
declared alongside/after its observed outputs can be useful failure evidence,
but cannot promote a claim.

## Execute and Diagnose

1. Validate the claim ledger, study plan, scenario, and data.
2. Run a deterministic seed smoke test through the factory-owned backtest
   runner.
3. Verify the run reaches the modeled behavior rather than timing out before
   contact.
4. Run the complete predeclared held-out sample and atomically publish a
   reload-validated artifact.
5. Compare distributions and historical uncertainty without calling a
   non-significant result proof of equivalence.
6. Attribute divergence to historical uncertainty, scenario mapping, model
   deficiency, or calibration only when evidence distinguishes them.
7. Record failed backtests as useful findings and add a remediation item when
   they expose a production gap.

Interpret artifact status exactly:

- `PASS` is a completed study whose joint gating rule passed. It is not by
  itself a `production_validated` claim.
- `FAIL` is a completed study whose joint gating rule missed. Preserve it and
  classify the affected historical claim as unsupported.
- `ERROR` is an execution, extraction, provenance, or evidence-construction
  failure. It contains no study verdict and cannot be described as a failed
  historical outcome.

Reload the persisted artifact through `load_historical_artifact`; the in-memory
result, command exit without a crash, or JSON presence alone is not evidence.

## Promote Deliberately

Promotion is a separate ledger transition. Accept only a reload-valid,
promotion-eligible `PASS` from a clean revision whose immutable predeclaration,
execution revision, source/config/data/catalog/doctrine/loadout/roster/
assignment identities, execution-ledger path and digest, claim bindings, and
artifact digest match the accepted tree. Bind every accepted claim metric to
one exact gating metric with identical intended use, unit, extractor, source,
and event scope. Diagnostic metrics cannot satisfy a claim. Reused or unknown
validation-source lineage, a dirty revision, a failed study, an error artifact,
or relevant post-execution drift prevents promotion.

## Report

Report sources, frozen envelope, exact configuration, seeds, commands, raw or
retained result location, statistics, pass/fail by metric, sensitivity to
assumptions, production-path evidence, artifact status and digest, promotion
eligibility/reasons, ledger disposition, and limitations. Never tune and
validate on the same sample while describing it as independent historical
validation.
