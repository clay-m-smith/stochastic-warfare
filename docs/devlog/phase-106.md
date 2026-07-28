# Phase 106 - API Execution Integrity

**Status:** Complete

**Started:** 2026-07-28
**Completed:** 2026-07-28

## Why this phase exists

Earlier phases declared API configuration overrides and graceful background
shutdown complete using structural merge tests and an unrelated sleeping task.
The Block 12 audit found that the engine reloads the unchanged scenario and that
accepted work can race database teardown or survive shutdown with a permanent
`running` row.

## Requirements

The authoritative contracts are REM-002 and REM-003 in
[`docs/remediation-backlog.md`](../remediation-backlog.md).

Acceptance criteria:

1. A bare, schema-valid partial calibration overlay is validated before enqueue,
   merged over existing scenario calibration, and used by the real
   `ScenarioLoader` and every API-side config consumer.
2. Same-seed API controls prove an outcome-affecting override, deterministic
   repetition, empty/no-overlay equivalence, nested sibling preservation, and
   concurrent isolation without modifying YAML.
3. Invalid, dead, or wrong-namespace fields return 422 before any durable row or
   task is created.
4. App lifespan owns the exact configured database and manager and cleans them
   up in `finally`.
5. Shutdown stops acceptance, cooperatively stops real run and batch workers,
   persists `cancelled`, retrieves task results, clears bookkeeping, and keeps
   SQLite open until terminal persistence is complete.
6. Execution failure, exceptional lifespan exit, post-shutdown submission, and
   active-run deletion preserve explicit atomic lifecycle behavior.

## Non-goals

- This phase does not repair reinforcement, morale, disabled-module, logistics,
  equipment-map, ASAT, time-on-target, or analysis-helper gaps assigned to
  Phases 107-112.
- It does not add arbitrary root scenario patching or a new public cancellation
  protocol.
- It does not change combat equations, weapon performance, calibration values,
  database pooling, or process topology.

## Production traces

### Override path

`POST /api/runs` -> `RunSubmitRequest` -> scenario resolution ->
`RunManager.submit()` -> durable pending row -> `_execute_run()` ->
`_run_sync()` -> `ScenarioLoader` -> `SimulationContext`/engine -> SQLite ->
`GET /api/runs/{id}` and event/frame endpoints.

### Lifecycle path

`create_app(settings)` -> FastAPI lifespan -> one `Database` -> one
`RunManager` -> submitted run/batch task -> executor worker -> terminal SQLite
update -> subscriber/bookkeeping cleanup -> manager shutdown -> database close.

## Red evidence

- Baseline and `roe_level=WEAPONS_HOLD` production runs were
  byte-for-byte identical because `_run_sync()` merges one dictionary and
  `ScenarioLoader` reopens another.
- `test_submit_run` and `test_submit_batch` pass while emitting an un-retrieved
  closed-database `ProgrammingError` during fixture teardown.
- Forced zero-grace shutdown cancels the asyncio wrapper but not the executor
  worker, removes its cancellation flag, and leaves the row permanently
  `running`.

The initial dedicated regression run had 15 failures. Adversarial follow-up
also reproduced settings split-brain, caller-cancelled shutdown abandoning a
thread, un-retrieved terminal-persistence exceptions, terminal-sentinel loss on
a full queue, startup database leakage, and a shared-connection rollback race.

## Implementation

### Effective run configuration

- `RunSubmitRequest.config_overrides` is now a strict, sparse
  `CalibrationSchema`, not a free-form root-scenario patch.
- `load_campaign_scenario_config()` validates the scenario and overlay before a
  row exists, normalizes canonical and legacy calibration fields together,
  deep-merges mappings, replaces scalars/lists, and rejects dead fields,
  coercible wrong types, unsupported enum values, and unknown scenario sides.
- `RunManager` passes one prevalidated effective config into `ScenarioLoader`.
  Loader construction deep-copies it, and API terrain, victory, timing, frame,
  and summary consumers read the same context config.
- The canonical sparse overlay is persisted while the source YAML remains
  byte-for-byte unchanged.
- `target_selection_mode: nearest` now executes as the documented alias for
  `closest`; unsupported modes fail validation instead of silently selecting
  threat scoring.

### Lifespan and execution ownership

- The app lifespan owns the exact factory settings, initialized `Database`, and
  `RunManager`; startup, normal exit, and exceptional exit all close resources
  in dependency order.
- Submission preflights configuration, creates the durable pending row, and
  registers a cooperatively cancellable worker under one lifecycle lock.
- Shutdown stops acceptance, signals run and batch workers with thread-safe
  events, treats its timeout as a warning threshold, and waits for actual
  executor completion. Cancellation of the shutdown caller is deferred until
  cleanup finishes.
- Run/batch completion, failure, and cancellation persist distinct terminal
  states before subscriber notification and bookkeeping cleanup. Active DELETE
  cancels and awaits its task before removing the row.
- Background task callbacks retrieve otherwise escaping exceptions. Bounded
  subscriber queues always retain a terminal sentinel.
- SQLite writes serialize each statement with its commit or rollback, so a
  missing-row failure cannot roll back another coroutine's valid update.

## Determinism and scenario evaluation

The same-seed API proof compares all stored result, event, snapshot, terrain,
and frame payloads. Omitted, empty, and explicit-default overlays are
identical; repeated `WEAPONS_HOLD` runs are identical; and `closest` and
`nearest` are identical aliases. `WEAPONS_HOLD` produces no engagements and
leaves all ten test units active, while the control produces engagements and
disabled units.

No RNG stream allocation, draw placement, iteration order, or mutable
checkpoint state changed. The determinism verdict is **DETERMINISTIC** for the
same seed, effective configuration, code, and data revision. Checkpoint and
stream-isolation proof are N/A because the overlay is immutable input applied
before context construction.

Activating the previously ignored `nearest` alias can change outcomes.
Production-harness runs compared archived phase-start revision `7c702d7`
against the Phase 106 worktree for `calibration_air_ground`, seeds 42--44:

| Seed | Prior winner / condition / ticks / engagements | Current winner / condition / ticks / engagements | Classification |
|---:|---|---|---|
| 42 | blue / `force_destroyed` / 49 / 69 | blue / `time_expired` / 1,440 / 40 | **EXPECTED CHANGE** |
| 43 | blue / `force_destroyed` / 48 / 63 | blue / `force_destroyed` / 62 / 48 | **EXPECTED CHANGE** |
| 44 | blue / `force_destroyed` / 48 / 78 | blue / `force_destroyed` / 62 / 53 | **EXPECTED CHANGE** |

All six runs succeeded and reported no evaluator diagnostics. This classifies
the change against the declared target-selection contract only; it makes no
historical-fidelity claim. The evaluator excludes internal `test_campaign*`
and benchmark scenarios, so the real API A/B test separately covers the public
override path.

## Verification

- Initial red:
  `uv run python -m pytest tests/api/test_phase_106_api_integrity.py -q
  --tb=short -o addopts=` -> 15 failed.
- Dedicated Phase 106 suite: 24 passed.
- Net-new Phase 106 tests: 25 (24 dedicated integrity tests plus one additional
  focused overlay regression).
- Dedicated plus focused overlay selection: 33 passed.
- Calibration/scenario/battle selection: 211 passed.
- Complete API suite with default exclusions disabled: 200 passed.
- API E2E scenario smoke: 41 passed.
- Default Python suite: 10,168 passed, 21 skipped, 346 deselected, and 6 known
  warnings in 231.23 seconds.
- Focused Ruff over every changed Python file: passed.
- Repository-wide Ruff remains blocked by eight unchanged baseline findings:
  six duplicate equipment-map keys assigned to REM-010/Phase 109 and two
  assertion-string findings outside this phase.
- `git diff --check`: passed (line-ending notices only).
- Strict MkDocs: passed; only the established unnavlisted article/template and
  old devlog-anchor informational notices remain.

## Residual boundaries

- Cooperative thread shutdown cannot impose a hard deadline on a permanently
  blocked or non-cooperative engine step. A bounded hard stop requires a future
  move to killable worker processes; the current contract waits rather than
  abandoning owned work.
- A fatal SQLite terminal-write failure cannot manufacture a durable terminal
  row. It now remains visible as a retrieved and logged background exception.
- This phase does not claim broader stochastic fidelity from one API A/B or
  three fixed scenario seeds.

## Postmortem

**Verdict:** Passed on 2026-07-28.

- **Scope:** On target. REM-002 and REM-003 are delivered. Adversarial findings
  about settings identity, startup failure, shutdown cancellation, bounded
  queues, missing-row transactions, semantic enum validation, and frontend
  request typing were resolved as necessary parts of the same integrity
  contract.
- **Quality:** High. The simplify review returned ready after its in-scope
  fixes; focused Ruff, frontend build/lint, and the relevant behavioral suites
  are green.
- **Integration:** Fully proven through the real router, durable SQLite rows,
  `ScenarioLoader`, `SimulationContext`, production battle loop, recorder/API
  payloads, executor workers, and FastAPI lifespan.
- **New deficits:** None. REM-013's broader default-suite exclusion disclosure
  remains assigned to Phase 112 and was not created by this phase.
- **Action items before closure:** None.

### Contract reconciliation

All planned work was delivered. The override is a strict sparse calibration
patch, one effective config reaches every run consumer, invalid requests fail
before enqueue, and run/batch work cannot outlive database ownership. No
planned item was dropped. The unplanned hardening listed in the scope verdict
was added because adversarial reproductions showed it was required to satisfy
the original atomicity and ownership contract.

Accepted non-goals remain unchanged: no arbitrary root-scenario patching, hard
thread termination, combat-equation or calibration-value change, database
pool, or new public cancellation protocol. The non-killable thread and fatal
terminal-write boundaries are disclosed above rather than papered over.

### Completion evidence matrix

| Capability | Declared | Loaded | Wired | Enabled | Exercised | Outcome | Persisted/exposed |
|---|---|---|---|---|---|---|---|
| REM-002 effective override | Yes | Yes | Yes | N/A -- immutable run input | Yes | Yes | Yes |
| REM-003 lifecycle ownership | Yes | N/A -- resource ownership | Yes | N/A -- not optional | Yes | N/A -- lifecycle contract | Yes |
| Frontend request contract | Yes | N/A -- compile-time boundary | Yes | N/A | Yes -- production build | N/A | Yes -- API client type |

### Final validation

- `uv run python -m pytest tests/api/test_phase_106_api_integrity.py
  tests/api/test_config_overrides.py -q --tb=short -o addopts=`:
  **33 passed in 5.89s**.
- `uv run python -m pytest
  tests/unit/simulation/test_calibration_schema.py
  tests/unit/test_phase49_calibration_schema.py
  tests/unit/test_phase86_calibration_flat.py
  tests/unit/test_simulation_scenario.py
  tests/unit/test_phase41_combat_depth.py
  tests/unit/test_phase84_engagement_culling.py -q --tb=short -o addopts=`:
  **211 passed in 5.00s**.
- `uv run python -m pytest tests/api -q --tb=short -o addopts=`:
  **200 passed in 29.50s**.
- `uv run python -m pytest tests/e2e/test_scenario_smoke.py -m e2e -q
  --tb=short -o addopts=`: **41 passed in 37.39s**.
- `uv run python -m pytest --tb=short -q`: **10,168 passed, 21
  skipped, 346 deselected in 231.23s**, with six known warnings (one empty
  legend, four Matplotlib animation-lifetime warnings, and one
  `datetime.utcnow` deprecation).
- From `frontend/`, `npm test`: **418 passed in 23.48s**; `npm run build`:
  passed with the established large-chunk advisory; `npm run lint`: zero
  errors and four unchanged React-hook warnings. A schema-key parity check
  reported **108 backend / 108 frontend** fields.
- Focused `uv run ruff check` over every changed Python file: passed.
  `uv run ruff check stochastic_warfare api tests` still reports eight
  unchanged baseline findings: six F601 duplicate keys in
  `validation/scenario_runner.py` (REM-010/Phase 109) and two F541 assertion
  strings in the Fallujah and INS Hanit validation tests.
- `uv run --extra docs mkdocs build --strict`: passed in **3.67s** with only
  established informational navigation/old-anchor notices.
- `git diff --check`: passed; line-ending conversion notices only.
- The production scenario evaluator was run at archived phase-start revision
  `7c702d7` and the final worktree with
  `uv run python scripts/evaluate_scenarios.py --scenario
  calibration_air_ground --no-details`, repeated for seeds 42, 43, and 44.
  All six runs succeeded; the result table above is classified
  **EXPECTED CHANGE**.

The independent adversarial acceptance review found no remaining blocker after
its reproductions were fixed. The final cross-document audit passed all
Phase 106 areas; the only provider-context drift is the already tracked
REM-013/Phase 112 exclusion-language issue.

Explicit slow, terrain, benchmark, historical backtest, profiling, and
non-smoke E2E suites were not run: this phase changes no data, historical
envelope, quantitative model, or performance-sensitive algorithm. The complete
API suite and affected API E2E smoke were enabled explicitly because the
default suite excludes them.
