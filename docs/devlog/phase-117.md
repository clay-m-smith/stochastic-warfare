# Phase 117 - Historical Outcome-Envelope Integrity

**Status:** Complete

**Remediation:** REM-030

## Objective

Replace catalog winner tables, unqualified `documented_outcomes`, and
legacy-runner comparisons presented as historical accuracy with one typed,
source-backed, held-out production backtest and disposition contract. This
phase will not tune physical performance or manufacture a historical pass.

## Start state

- Phase 116 is committed and synchronized at
  `9a74d5ca7f9f3c8f6d023c5dd3d31862497f5435`.
- `git pull --ff-only origin main` reported `Already up to date`.
- `git status --short --branch` reported clean `## main...origin/main`, and
  local/origin HEAD both resolved to the exact Phase 116 commit.
- The Phase 116 hosted push is fully green: the standard partition passed
  11,953/11,953 with six known warnings in 1,624.50 seconds; exact partition,
  frontend, terrain, API, E2E, Ruff/ESLint, documentation, production
  benchmark, and Docker jobs all passed.

## Specification and research

The Phase 117 specification is
[Historical Outcome-Envelope Integrity](../specs/historical-outcome-envelope-integrity.md).
The `$spec`, `$backtest`, `$research-military`, `$research-models`, and
`$design-review` routes apply.

Authoritative source review found:

- U.S. Army *ARMOR*, October--December 2015, p. 98 records 28 Iraqi
  tanks plus 16 personnel carriers destroyed, no American losses, and a
  23-minute Eagle Troop action at 73 Easting.
- U.S. Army Special Operations History Office *Veritas*, vol. 1, no. 1,
  p. 84 records a two-and-a-half-hour Debecka crossroads fight and five
  T-55s, three APCs, and eight cargo vehicles destroyed. This conflicts with
  the shipped four-hour/modal-ten proxy and leaves it unsupported.
- GAO's DoD VV&A summaries require intended-use validation, documented
  evidence/limitations, and suitable data rather than metadata presence.
- NIST's exact binomial interval supplies the study's finite-sample coverage
  calculation. The corrected specification applies it to one joint per-run
  outcome rather than combining independent per-metric bounds.

The design review rejected winner-only gating and required a revised direction:
winner is diagnostic, while source-scoped loss and duration metrics form one
joint gate for the real 73 Easting study. The follow-up review also rejected
post-run scoped extraction, independent marginal bounds, an ambiguous terminal
boundary, mixed plan/error semantics, and a scenario-level validation badge.
The corrected contract uses a factory-owned per-session backtest runner, an
exact 1,380-second source-synchronous cutoff with explicit right-censoring, one
joint binomial success per seed, an exact pre-run-rejection/runtime-`ERROR`
split, and claim-level public dispositions with conservative aggregation.
Fresh SciPy evaluation of the exact rule gave lower bounds 0.860891659332 for
20/20 joint successes and 0.783893835793 for 19/20, so the frozen 0.80 policy
requires all 20 runs to match the complete joint envelope.
The bootstrap study plan is based on the clean Phase 116 design base
`9a74d5ca7f9f3c8f6d023c5dd3d31862497f5435`. Its initial canonical digest was
`8d80b6748d8f50890954178618db7faaf8ea9b7c8b2557c2c13d9d74887e0fd6`.
Postmortem review then found that its single exact-44 Iraqi vehicle gate could
accept the wrong tank/personnel-carrier composition. A production-red
regression proved the defect, and the unaccepted bootstrap plan was corrected
to separate exact 28-tank and 16-personnel-carrier gates. Its corrected digest
is `3e70e8de01f565c586a4598b8758c1564e8b0bd0d952fbfbcc24a7c14094c400`.
The pre-correction artifact is invalidated and the complete held-out study is
rerun against the corrected plan before closure; no accepted evidence is
retroactively redefined.
Because the plan and implementation share Phase 117's one-commit transition,
its `predeclaration_revision` is explicitly null and it is ineligible for
validation promotion.
Zero retained validated scenarios is non-vacuous only with pass/fail evaluator
controls, exact claim digests, a real durable failed artifact, and public
removal of unqualified legacy metadata.

The Army outcome source also informed the shipped 73 Easting metadata. The
study therefore declares source reuse and is ineligible for
`production_validated` even if it were to pass; held-out RNG seeds cannot make
reused historical evidence independent. A separate non-modern production
control will prove that the new route retains era identity without absorbing
REM-040's legacy conversion repair.

## Baseline inventory

Read-only inventory commands and code tracing found:

- 31 shipped scenario YAML files contain `documented_outcomes`;
- the collections contain 83 metrics and 54 unique metric names;
- source-quality counts are 19 tier-0, 41 tier-1, and 23 tier-2 entries;
- tolerance counts are 1 at 1.3x, 2 at 1.4x, 7 at 1.5x, 19 at 2x,
  53 at 3x, and 1 at 5x;
- 27/31 collections have root `sources` lists, totaling 86 strings;
- six collections are synthetic/future analytical cases rather than observed
  historical engagements;
- the production analysis vocabulary directly supports only 2/83 legacy
  metric names (`exchange_ratio` in two scenarios); and
- no production historical-verdict schema or artifact exists.

Exactly 19 Python test files mention `documented_outcomes`; nine call
`compare_to_historical`. Four shipped suites use the simplified legacy runner,
three factory-backed suites perform current metric projection only, and two
use synthetic comparator fixtures. No shipped comparison asserts the legacy
boolean verdict. The canonical 46-scenario seed-42 evaluator is already
correctly labeled current-engine regression only.

The strongest public contradiction is the frontend's five “golden” scenarios,
described as historically calibrated and regression-tested against historical
outcome envelopes. The detail endpoint also returns raw legacy outcome
metadata, while the UI reads the nonexistent field `metric` instead of the
authored `name`.

## Production red proof

Before implementation, this fresh factory-owned command exercised the first
held-out seed at the exact 1,380-second observation cutoff:

```bash
.venv/bin/python -c "from stochastic_warfare.tools._run_helpers import run_scenario_batch; r=run_scenario_batch('data/scenarios/73_easting/scenario.yaml', {}, 1, 11700, 276, metric_names=['blue_destroyed','red_destroyed','win_blue','ticks_executed'], data_dir='data'); q=r.runs[0]; print({'metrics':r.metrics_dict(),'duration_s':q.duration_s,'condition_type':q.condition_type,'winning_side':q.winning_side,'game_over':q.game_over,'seed':q.seed,'code_commit':r.code_revision.commit,'dirty':r.code_revision.dirty,'worktree_fingerprint':r.code_revision.worktree_fingerprint,'source_fingerprint':r.source_fingerprint,'config_fingerprint':r.config_fingerprint})"
```

It completed in approximately 5 seconds under the user's accepted shared-core
contention and reported seed 11700, 276 ticks, 1,380 seconds,
`condition_type=max_ticks`, `winning_side=draw`, 0 blue destroyed, 0 red
destroyed, and no blue win. The source requires exactly 28 scoped Iraqi tanks,
16 scoped Iraqi personnel carriers, zero scoped American vehicles, and a
natural 1,380-second completion. Thus the fresh production run already misses
the joint outcome on both Iraqi component losses and censored duration; it is
not a no-crash or winner-only inference. Provenance bound the
run to Phase 116 commit `9a74d5ca7f9f3c8f6d023c5dd3d31862497f5435`,
dirty worktree fingerprint
`b66f62aab705457ae9cba20db95c31dfacb211fe19b13e071807314454a6e924`,
source fingerprint
`328467cd1f200cf2f0157da917ab20b9e9bbc43fb7ee985f5d4472d2df3cd3e5`,
and config fingerprint
`5edee0f800115415b0d6652999acdd23552f6fcc839af2ba7db68e86fd644728`.

The pre-implementation runner can report only whole-side generic metrics and
cannot yet issue scoped receipts, validate the plan/ledger, compute the joint
bound, or persist a self-validating artifact. Frozen red tests for those
missing boundaries and the legacy/API/frontend fail-open behavior follow.

## Implementation evidence

Phase 117 introduces one strict historical-validation package under
`stochastic_warfare.validation.historical_backtest`. The implementation is
split by responsibility rather than by test fixture:

- `claims.py` owns the typed claim ledger, source scanner, scenario summaries,
  accepted-evidence verification, and conservative aggregation;
- `studies.py` owns strict source, lineage, seed-interval, metric, acceptance,
  predeclaration, and study-plan models;
- `runner.py` accepts only one factory-prepared production scenario, builds a
  fresh runtime session for every held-out seed, observes the synchronized
  source boundary, and emits complete typed receipts;
- `evaluator.py` computes one exact joint binomial result from the ordered
  per-run gating vector;
- `artifacts.py` owns typed completed/`ERROR` evidence, canonical digests,
  receipt recomputation, atomic write, and reload validation; and
- `scripts/run_historical_backtest.py` is the bounded command boundary that
  loads the canonical ledger/plan, calls `SimulationRuntimeFactory.prepare`,
  and runs the study. Phase 117 originally published below `docs/evidence/`;
  the current repository policy writes generated output below the ignored
  `artifacts/evidence/phase-117/` tree and retains full publications off main.

The plan and claim schemas share one stable lowercase ID contract. Seed
interval counts and overlaps use arithmetic rather than constructing unbounded
sets, and a plan may request at most 1,000 held-out production runs. Unknown
fields, duplicate YAML keys and IDs, booleans in numeric fields, non-finite
values, ambiguous units, unsupported extractors, winner-only gating, seed
lineage overlap, impossible statistical policies, nonempty analysis patches,
symlinked inputs/outputs, and preparation identity drift all reject. Errors
before valid execution publish nothing; failures after execution begins
produce a typed `ERROR` artifact rather than a false historical `FAIL`.

The runtime path has a closed extractor vocabulary for exact side/unit-type
status counts, natural-terminal duration with right-censoring, winner
diagnostics, and explicitly scoped exchange ratio. It exposes the production
terminal-cause vocabulary, effective era and era-contract digests, authored
and loaded typed rosters, exact assignment/loadout identities, and one
observation receipt per seed. The runner never constructs a context, engine,
unit, force, or loadout. `load_effective_unit_loader()` is shared by
`ScenarioLoader` and study scope validation so the non-modern control audits
the same base-plus-era catalog boundary instead of reimplementing loadouts.

The durable artifact recomputes vectors, per-metric membership, joint
successes, lower bound, verdict, terminal/censoring evidence, claim bindings,
and its self-digest on reload. Acceptance is a separate, stricter operation:
it requires a clean completed `PASS`, independent evidence lineage, immutable
predeclaration ancestry, exact claim/metric binding, committed plan and
artifact content, no relevant code/dependency drift, and fresh factory
preparation with matching production identities. A result from one scenario
cannot promote another scenario's claim.

Scanner version 2 audits seven explicit source groups: two API Python paths,
three public frontend paths, four frontend test paths, 38 Python test paths,
101 public-document paths, 34 scenario-YAML paths, and 12 workflow-skill paths.
It recognizes separator variants and camel-case status tokens, rejects
generated `*.d.ts` declarations from its TypeScript source contract, and
binds every candidate file either to exact claim IDs or to an explicit
reviewed-nonclaim rationale. Reviews are deliberately file-level rather than
occurrence-level; semantic locators and the manual cross-document audit remain
part of closure evidence.

The current ledger contains 233 claims: 214 `unsupported`, 19
`current_engine_regression_only`, and zero `production_validated`. Its surface
inventory is:

| Surface | Claims |
|---|---:|
| Public documentation | 154 across 66 paths |
| Scenario `documented_outcomes` collections | 31 collections / 83 metrics |
| Python `documented_outcomes` tests | 19 |
| Python historical-claim tests | 6 |
| Scenario historical prose | 3 |
| Current-engine regression snapshot | 1 |
| Duplicated regression tables | 3 |
| API claim surfaces | 4 |
| Frontend claim surfaces | 11 |
| Frontend historical-claim test | 1 |

The 196 candidate-file reviews consist of 134 claim-bound reviews and 62
explicit exclusions. Full ledger/data validation currently reports zero
uninventoried collections, missing collections, unreviewed candidates, stale
reviews, source-digest mismatches, source-rule mismatches, binding errors,
obsolete boolean historical APIs, or claim-content digest mismatches. The
ledger and all source-review digests will be frozen again after the final
status documentation edits.

Legacy `envelope_check.py` and its structural-only suite are removed. The
compatibility `HistoricalDataLoader` and Monte Carlo comparison code now
reject duplicate metrics, booleans masquerading as numbers, missing/empty /
partial/non-finite vectors, and empty reports. They expose diagnostics but no
boolean historical-validation verdict. Five older scenario suites now assert
current production regression semantics without presenting direct helper
construction or legacy comparison as historical evidence.

The scenario API owns a single cached immutable application-ledger load and
returns claim-level disposition, limitation, intended use, metric/event scope,
regression-evidence flag, and accepted references. Its conservative aggregate
cannot widen an individual claim. Scenario detail removes raw
`documented_outcomes` and source lists from the authoritative public config;
unknown or externally rooted scenarios receive a synthetic unsupported result
without leaking an absolute path. The React list/detail pages and TypeScript
schema consume that exact claim-level contract and no longer present the five
regression references as historically calibrated “golden” scenarios.

The corrected 73 Easting plan executed all seeds 11700--11719. Every run
observed zero destroyed scoped Iraqi tanks against the exact 28 required, zero
destroyed scoped Iraqi personnel carriers against the exact 16 required, zero
destroyed scoped American vehicles against the exact zero required, and the
1,380-second cutoff without a natural terminal. The complete joint result is
therefore 0/20 with lower confidence bound 0.0. Terminal diagnostics are 16
draws and four red wins, all with the production
`max_ticks` condition. The artifact is a completed `FAIL`, not an `ERROR` and
not accepted evidence; `study_failed`, dirty candidate execution, reused
source evidence, and the one-commit bootstrap's missing immutable
predeclaration independently prevent promotion. The result changes the public
claim only by making its unsupported status explicit. It does not tune the
scenario or identify the first production fidelity defect.

| Capability stage | Production evidence | Result |
|---|---|---|
| Declared | strict ledger, source, plan, extractor, acceptance, receipt, and artifact schemas | Yes |
| Loaded | canonical 243-claim ledger and both 73 Easting / Agincourt plans load through public strict loaders | Yes |
| Wired | CLI and accepted-evidence verification reach `SimulationRuntimeFactory`, prepared scenario, runner, evaluator, writer, and reload validator | Yes |
| Enabled | explicit plan opt-in; missing/unknown claims remain unsupported and no historical feature toggle exists | Yes / N/A toggle |
| Exercised | 20 fresh 73 Easting sessions plus a non-modern Agincourt production control | Yes |
| Outcome-affecting | gating-boundary mutations change the verdict; winner-only diagnostics cannot rescue a failed gate | Yes |
| Persisted/exposed | reload-validated failed JSON artifact plus claim-level API/frontend projection | Yes |

Checkpoint persistence is N/A for the backtest owner: it owns no mutable
simulation state and creates complete fresh runtime sessions. Runtime
checkpoint behavior is unchanged and retains its ordinary regression gates.

## Focused validation

The historical-contract candidate passed 221 focused nodes together after the
bounded-interval, boolean-coercion, single-audit, cache, and acceptance fixes:

```text
.venv/bin/python -m pytest -q \
  tests/unit/test_phase117_historical_acceptance.py \
  tests/unit/test_phase117_historical_adversarial.py \
  tests/unit/test_phase117_historical_artifacts.py \
  tests/unit/test_phase117_historical_integrity.py \
  tests/unit/test_phase117_historical_runtime.py \
  tests/unit/test_historical_data.py \
  tests/unit/test_monte_carlo.py
# 221 passed in 80.19s; 0 failed/errors/skipped/warnings
```

A later independent simplify review found that study IDs were less strict than
accepted-evidence claim IDs. The shared stable-ID repair and its malformed-plan
control then passed the affected 12/12 nodes in 1.29s. Because that 12-node run
overlaps the 221-node set, it is not added to the count. The post-document
freeze reruns the resulting 222-node focused selection once and records its
authoritative count below.

The first 222-node freeze attempt deliberately retained a real integrity red:
217 passed and five failed in 80.12s after a one-line specification reflow was
made following ledger regeneration. Every failure named the same exact
`docs/specs/historical-outcome-envelope-integrity.md` source-review and claim
digest mismatch; no runner/evaluator behavior failed. This is expected
fail-closed behavior, not accepted green evidence. The specification locator,
review digest, claim digest, and ledger self-digest are refreshed before the
authoritative rerun.

After that mechanical refresh, the exact same selection passed:

```text
UV_CACHE_DIR=/tmp/sw-phase117-final-uv-cache uv run --no-sync python \
  -m pytest -p no:cacheprovider -o addopts= -q \
  tests/unit/test_phase117_historical_acceptance.py \
  tests/unit/test_phase117_historical_adversarial.py \
  tests/unit/test_phase117_historical_artifacts.py \
  tests/unit/test_phase117_historical_integrity.py \
  tests/unit/test_phase117_historical_runtime.py \
  tests/unit/test_historical_data.py \
  tests/unit/test_monte_carlo.py
# 222 passed in 97.86s; 0 failed/errors/skipped/warnings
```

Postmortem added three more focused nodes after that freeze: unstable claim-ID
rejection, final held-out-run source-drift rejection, and canonical rejection
of the dot path. The split 28-tank / 16-personnel-carrier contract strengthened
an existing plan node, and its duration-control indexing repair did not add a
node. The then-current selection passed freshly with the same seven-file
boundary:

```text
.venv/bin/python -m pytest -q \
  tests/unit/test_phase117_historical_integrity.py \
  tests/unit/test_phase117_historical_artifacts.py \
  tests/unit/test_phase117_historical_runtime.py \
  tests/unit/test_phase117_historical_acceptance.py \
  tests/unit/test_phase117_historical_adversarial.py \
  tests/unit/test_historical_data.py \
  tests/unit/test_monte_carlo.py
# 225 passed in 101.37s; 0 failures/errors/skips; no warnings displayed
```

The final scanner-bound inventory update deliberately produced one additional
red: the exact-ledger test expected 99 public-document candidates while the
reviewed Phase 38/39 supersession notices made the live value 101. It failed
1/1 at that assertion in 12.04s. After updating the exact expected inventory to
101 public documents, 12 workflow paths, and 59 exclusions and refreshing the
test file's own review digest, the complete seven-file selection passed again:

```text
UV_CACHE_DIR=/tmp/sw-phase117-final-uv-cache uv run --no-sync python \
  -m pytest -p no:cacheprovider -o addopts= -q \
  tests/unit/test_phase117_historical_acceptance.py \
  tests/unit/test_phase117_historical_adversarial.py \
  tests/unit/test_phase117_historical_artifacts.py \
  tests/unit/test_phase117_historical_integrity.py \
  tests/unit/test_phase117_historical_runtime.py \
  tests/unit/test_historical_data.py \
  tests/unit/test_monte_carlo.py
# 226 passed in 82.50s; 0 failures/errors/skips; no warnings displayed
```

The final 196-candidate refresh intentionally triggered the same exact-count
guard once more: 225 nodes passed and
`test_strict_claim_ledger_audits_the_exact_repository_inventory` failed in
82.81s because it still expected 101 public-document candidates while the two
newly reviewed correction records make the exact value 103. Its paired
reviewed-nonclaim expectation was updated from 59 to 61 at the same boundary.
This one-failure run is retained as a fail-closed red, not added to the passing
total. After correcting the two exact expectations and regenerating the
source-bound ledger, the identical seven-file selection passed 226/226 in
74.27s with no failures, errors, skips, or displayed warnings.

The seed-interval and legacy numeric coercion matrix passed 79/79 in 1.98s.
The existing historical-data and Monte Carlo compatibility suites passed
86/86 in 1.14s. Two runtime/checkpoint regression controls passed in 4.28s.
`$audit-determinism` returned **DETERMINISTIC** and
`$validate-conventions` returned **CLEAN**: the phase adds no RNG draw, stream,
ordering, checkpoint, coordinate, or mutable simulation-state behavior.
Wall-clock time appears only in artifact creation metadata and does not affect
the simulation result or acceptance calculation.

Postmortem's source-to-runtime audit then found that two shipped
`school_config` proxy shapes assigned zero units and that the editor emitted
unsupported School and commander shapes. The strict repair rejects the four
proxy families, retains exact per-unit School assignments, removes the two
no-op catalog blocks, and makes School/commander creation explicitly
unavailable instead of substituting side-wide proxy state. The current focused
boundary is green:

```text
.venv/bin/python -m pytest -q \
  tests/unit/test_phase_25a_scenario_wiring.py \
  tests/unit/test_phase55_resolution_scenarios.py \
  tests/validation/test_phase_30_scenarios.py \
  tests/unit/test_phase48_deficit_fixes.py
# 437 passed in 39.05s; 0 failures/errors/skips/warnings

.venv/bin/python -m pytest -q \
  tests/unit/test_phase112_doctrine_compare.py \
  tests/unit/test_phase112_analysis_consumers.py \
  tests/integration/test_phase112_commander_unit_integrity.py \
  tests/unit/test_phase_25d_commander_wiring.py
# 117 passed in 137.08s; 0 failures/errors

cd frontend && npm test -- --run \
  src/__tests__/pages/editor/ConfigToggles.test.tsx \
  src/__tests__/pages/editor/DoctrinePicker.test.tsx \
  src/__tests__/pages/editor/CommanderPicker.test.tsx \
  src/__tests__/pages/CalibrationSliders.test.tsx \
  src/__tests__/hooks/useScenarioEditor.test.ts
# 5 files / 36 tests passed in 1.40s; 0 warnings/errors
```

The fresh async transport attempts did not complete under the qualified host
condition and are not counted. Exact parser, loader, factory/runtime, reducer,
and direct-route results are retained; hosted API validation remains a
separate post-push gate.

The same audit surfaced a separate optional-suite authority defect. A fresh
factory-built runtime comparison produced these exact authored/runtime values:

| Scenario | Authored escalation | Runtime escalation | DEW runtime |
|---|---|---|---|
| Taiwan Strait | thresholds `[0,.2,.35,.45,.6,.75,.85,.92,.95,.97,.99]`; hysteresis `.65`; cooldown `14,400s` | default thresholds `[0,.15,.25,.35,.5,.6,.7,.8,.85,.9,.95]`; hysteresis `.7`; cooldown `3,600s` | engine present from `dew_config: {}`, but zero directed-energy loadouts |
| Srebrenica 1995 | thresholds `[0,.05,.1,.2,.3,.4,.5,.6,.7,.8,.9]`; hysteresis `.7`; cooldown `1,800s` | the same default thresholds; hysteresis `.7`; cooldown `3,600s` | absent |
| Hybrid Gray Zone | default threshold values; hysteresis `.7`; cooldown `7,200s` | default thresholds; hysteresis `.7`; cooldown `3,600s` | absent |

The production benchmark control contains 50 loaded `de_shorad` units with an
exact `de_shorad_50kw` directed-energy loadout, but has no `dew_config`, so its
runtime DEW engine is absent. Phase 117 removes ignored enable-like editor/data
keys and records this truth; it does not claim an engagement capability.
REM-050 / Phase 137 owns strict consumed Escalation/DEW configuration and a
real scenario combining a DEW engine with capable units and behavioral
engagement evidence.

## Conditional and broader validation

The full historical inventory/data gate passed from the write-frozen
pre-status tree with the exact counts below. The historical-only portion is
rerun after final status edits so its review digests name the committed
candidate rather than this intermediate document tree:

```text
.venv/bin/python scripts/validate_scenario_data.py
# historical claims: 31 collections / 83 metrics; 25 Python claim-test
# surfaces; 1 frontend claim-test surface; 164 documentation claims across
# 67 paths; candidate paths 2 + 3 + 4 + 38 + 103 + 34 + 12;
# 135 claim-bound reviews + 61 reviewed nonclaims; all 9 deficit families zero
# data: 184 unit YAML files; 442/442 catalog keys; 8,388/8,388 initial units;
# 70 override groups -> 1,128/1,128 units and 1,131/1,131 applications;
# 11 constellations; 3 ASAT systems; 52 scenarios; 0 errors; 0 warnings;
# 1 explicitly classified intentionally sensorless unit
# PASSED; 0 errors, 0 warnings, 1 explicit sensorless classification;
# provisional all-repair freeze wall time 45.87s

.venv/bin/python -m pytest -q \
  tests/validation/test_phase_30_scenarios.py::TestScenarioFullLoad
# 52 passed in 37.42s
```

The one sensorless classification is the existing
`modern/civilian_noncombatant`; it is not a Phase 117 warning or silent
mapping omission. A packaged-loader control also loaded the same strict
catalog ledger without repository-only documentation/test sources and exposed
73 Easting as unsupported, with current-engine regression evidence and no
accepted IDs. Docker was not locally available. The hosted workflow contains
the real no-`.git` image smoke, so no current page calls that image result
passed before the post-push workflow actually supplies it.

The complete 46-scenario seed-42 factory evaluator finished under the user's
accepted shared-core qualification:

```text
.venv/bin/python scripts/evaluate_scenarios.py \
  --output /tmp/sw-phase117-all-scenarios-42.json --no-details --seed 42
# 46/46 completed; 39 OK; 7 WARN; 0 ERROR
# raw artifact SHA-256 40dde05e...; semantic SHA-256 6eb02276...
# elapsed wall time 7,948.60s
```

All 46 normalized semantic rows exactly match the Phase 116 baseline
(baseline semantic SHA-256 `6eb02276...`). The seven retained warnings are the
declared current-regression signals already owned by their scenarios; the six
explicit evaluator exclusions remain `benchmark_battalion`,
`benchmark_brigade`, `test_campaign`, `test_campaign_logistics`,
`test_campaign_multi`, and `test_campaign_reinforce`. Phase 117 changes claim
classification and validation execution, not simulation outcomes. This
evaluator predates the later strict School schema and Bekaa/Suwalki/Taiwan
data repairs, so it is retained only as qualified broad evidence. The current
437-node production controls establish that the removed School proxies
assigned zero units and that Taiwan's ignored-key removal preserves the same
presence-default DEW runtime; current strict data validation and the final
catalog projection cover those changed sources.

Frontend validation is green on the current production source:

```text
cd frontend && npm test
# 86 files; 451 tests passed; Vitest 4.86s

cd frontend && npm run lint
# exit 0; 0 warnings; 0 errors

cd frontend && npm run build
# 422 modules transformed; built in 49.90s
```

The frontend test diagnostics are 70 React Router future notices, ten React
`act(...)` notices, and four jsdom navigation-not-implemented notices. Three
hook dependency patterns in phase-touched files and one adjacent map-tab
pattern were simplified after the earlier four-warning lint run; focused
coverage passed 11/11 and the current ESLint run has no warning or error. The
production build reports a six-month-old `caniuse-lite` database and large
chunks of 580.52 kB and 4,875.37 kB; these are advisories, not hidden failures.

An isolated eight-shard standard run passed 12,072/12,072, the API partition
passed 267/267, and the terrain profile passed 97/97 before the final scanner
and stable-ID controls were added. They remain useful pre-final regression
evidence but are not mislabeled as final-freeze results. A first attempted
eight-shard invocation incorrectly shared one manifest under `/tmp`; its
apparently green outputs are excluded because the shards could overwrite one
another's selection. Only per-shard isolated manifest/JUnit directories are
eligible for final evidence.

The fresh post-hardening collection audit is exact and warning-free:

```text
.venv/bin/python scripts/validate_test_partitions.py \
  --output /tmp/sw-phase117-independent-partitions.json
# exact union: true; pairwise disjoint: true; collection warnings: 0
# 12,605 = standard 12,092 + slow-only 110 + benchmark-only 88 +
#          slow-benchmark 5 + API 269 + E2E 41
# fresh postmortem collection; exact union/disjoint and zero warnings
```

An isolated current benchmark-policy run covers all 12 runtime-closure nodes
and the corrected slow-benchmark oracle:

```text
.venv/bin/python scripts/run_pytest_partition.py benchmark-policy \
  --manifest /tmp/sw-phase117-final/benchmark-policy/manifest.json \
  --junit /tmp/sw-phase117-final/benchmark-policy/junit.xml \
  --forbid-skips --timeout-seconds 600
# 88 passed in 49.03s; 0 failures/errors/skips/warnings; real 51.18s
```

The first fresh standard execution correctly failed one evidence-quality gate
after 12,084 other nodes passed: shard 3 reported 1,510 passes and
`test_evidence_ledgers_match_fresh_collection` failed because three new
scanner-v2 adversarial controls had no reviewed disposition. Independent
review classified all three as genuine fail-closed behavioral oracles: both
full/packaged loaders reject appended scenario prose, scenario review rejects
an omitted compatible prose binding, and the version-2 loader rejects a
checksum-correct version-1 scanner ledger. No weak or structural completion
credit was assigned.

After adding those exact entries, the three controls passed in 1.18s,
`scripts/validate_test_evidence.py` reported 228 no-direct, 103 reviewed
behavioral, 1,020 weak, and 917 structural nodes, and the dedicated evidence
ledger suite passed 2/2 in 44.04s. The complete formerly failing shard then
passed 1,511/1,511 in 162.43s.

The pre-postmortem standard gate used eight isolated parent directories; every
shard independently collected the same warning-free 12,085-node universe:

```text
UV_CACHE_DIR=/tmp/sw-phase117-final-uv-cache uv run --no-sync python \
  scripts/run_pytest_partition.py standard \
  --shard-index I --shard-count 8 \
  --manifest /tmp/sw-phase117-final/standard-I/manifest.json \
  --junit /tmp/sw-phase117-final/standard-I/junit.xml \
  --forbid-skips --timeout-seconds 2700
# I = 0..7; shard 3 uses the repaired rerun directory
```

| Shard | Final result | Warnings |
|---:|---|---:|
| 0 | 1,511 passed in 373.94s | 1 `datetime.utcnow()` deprecation |
| 1 | 1,511 passed in 291.05s | 0 |
| 2 | 1,511 passed in 178.95s | 0 |
| 3 rerun | 1,511 passed in 162.43s | 0 |
| 4 | 1,511 passed in 83.65s | 0 |
| 5 | 1,510 passed in 266.26s | 1 empty-chart legend + 4 unrendered animations |
| 6 | 1,510 passed in 172.69s | 0 |
| 7 | 1,510 passed in 198.77s | 0 |

That pre-postmortem total is **12,085/12,085 passed**, with zero failures,
errors, skips, xfails, or xpasses and exactly six classified pre-existing
warnings. The earlier 1,510-pass/one-failure shard remains the red proof and is
not added to the passing total. Postmortem added three standard nodes: unstable
claim-ID rejection, final-run source-drift rejection, and canonical rejection
of the dot path. Each red-to-green control and the complete 225-node Phase 117
focused gate pass freshly. The closure run must execute the current 12,092-node
standard universe before this older full-partition evidence can be called
final.

That authoritative closure run is now complete. Attempts overlapping the final
documentation/API-test formatting edits are excluded: shards 2 and 3 exposed
stale claim digests and worktree-identity drift exactly as the fail-closed
contract requires. After the write freeze, shard 2 found one further genuine
red in the separate test-evidence ledger: the new API/simulation drift
parameter branches lacked separate reviewed entries, two provider-parity tests
lacked structural dispositions, and the prior unparameterized drift ID was
stale. The repair split the two behavioral branches and classified both
provider tests as `structural_only`; it did not award production capability
credit to byte/text checks.

```text
.venv/bin/python scripts/validate_test_evidence.py
# no-direct=228; reviewed behavioral=104; weak=1,023; structural=919

.venv/bin/python -m pytest -q \
  'tests/unit/test_phase117_historical_acceptance.py::test_rejects_relevant_code_drift_after_execution[api-source]' \
  'tests/unit/test_phase117_historical_acceptance.py::test_rejects_relevant_code_drift_after_execution[simulation-source]' \
  tests/unit/test_repository_skills.py::test_claude_edit_hooks_express_current_rng_and_sensor_contract \
  tests/unit/test_repository_skills.py::test_claude_routes_exactly_mirror_canonical_repository_skills
# 4 passed in 10.78s

UV_CACHE_DIR=/tmp/sw-phase117-final-uv-cache uv run --no-sync python \
  scripts/run_pytest_partition.py standard \
  --shard-index I --shard-count 8 \
  --manifest /tmp/sw-phase117-closure-standard-I/manifest.json \
  --junit /tmp/sw-phase117-closure-standard-I/junit.xml \
  --forbid-skips --timeout-seconds 2700
# I = 0..7; only the latest valid result for each isolated shard is retained
```

| Shard | Authoritative result | Warnings |
|---:|---|---:|
| 0 | 1,512 passed in 253.09s | 1 empty-chart legend |
| 1 | 1,512 passed in 287.61s | 0 |
| 2 repaired rerun | 1,512 passed in 173.76s | 0 |
| 3 frozen rerun | 1,512 passed in 183.66s | 0 |
| 4 | 1,511 passed in 35.61s | 1 `datetime.utcnow()` deprecation |
| 5 | 1,511 passed in 276.32s | 4 unrendered Matplotlib animations |
| 6 | 1,511 passed in 172.00s | 0 |
| 7 | 1,511 passed in 347.26s | 0 |

The exact aggregate is **12,092/12,092 passed** with zero failures, errors,
skips, xfails, or xpasses and six classified warnings. Cumulative shard time
was 1,729.31s. Every shard collected 12,092 selected of 12,295 considered
nodes, with 203 deselected and zero collection warnings. The manifests contain
12,092 unique selected IDs over indexes 0--7, split as four shards of 1,512 and
four of 1,511; their complete-universe digest is
`14d522108beb9ae3fe46f8c71c039c82dd6689b56827a56bd328cebc69c5b31d`.

That aggregate predates the late strict School schema, editor narrowing, and
three scenario-data edits. It is retained as broad Phase 117 evidence, not
misrepresented as the final current-tree universe. A final current-tree
standard run superseded that qualification after the status transition and
before this record-only devlog addition:

```text
.venv/bin/python scripts/validate_test_partitions.py \
  --output /tmp/sw-phase117-final-poststatus-partitions.json
# superset=12,619; standard=12,101; slow=110; benchmark=88;
# slow-benchmark=5; API=274; E2E=41; exact union=true;
# all marker partitions pairwise disjoint=true; collection warnings=0

.venv/bin/python scripts/run_pytest_partition.py standard \
  --shard-index I --shard-count 8 \
  --manifest /tmp/sw-phase117-poststatus-standard-I/manifest.json \
  --junit /tmp/sw-phase117-poststatus-standard-I/junit.xml \
  --forbid-skips --timeout-seconds 2700
# I = 0..7
```

| Shard | Final current-tree result | Warnings |
|---:|---|---:|
| 0 | 1,513 passed in 368.76s | 0 |
| 1 | 1,513 passed in 261.65s | 0 |
| 2 | 1,513 passed in 322.29s | 0 |
| 3 | 1,513 passed in 115.62s | 0 |
| 4 | 1,513 passed in 39.26s | 1 `datetime.utcnow()` deprecation |
| 5 | 1,512 passed in 296.55s | 1 empty-chart legend |
| 6 | 1,512 passed in 152.77s | 4 unrendered Matplotlib animations |
| 7 | 1,512 passed in 233.60s | 0 |

The exact current-tree aggregate is **12,101/12,101 passed** with zero
failures, errors, skips, xfails, or xpasses and six classified warnings.
Cumulative JUnit test time was 1,790.420s. Every shard independently collected
12,101 selected of 12,304 considered nodes with 203 deselected and zero
collection warnings. The selected manifests contain 12,101 unique IDs, are
pairwise disjoint, and reproduce the complete standard universe exactly: five
shards contain 1,513 nodes and three contain 1,512. The complete-universe
SHA-256 is
`6457dfec6ef362942d7832593f098ccf3db0a7f0e885809eaa34765cc5d8e920`.
The final identity-focused scanner, ledger, artifact, documentation, public
projection, and lint gates are rerun after this evidence-only edit. Hosted CI
must still collect and pass the committed tree.

The long marker runs are explicitly qualified rather than papered over. Slow
shard 1 passed 28/28 in 338.68s. Slow shard 2 produced 26 passes and one stale
Debecka expectation failure in 1,950.48s; that oracle was repaired later.
Slow shards 0 and 3 each reached their 4,200-second containment limit before a
summary (17 dots plus four error indicators for shard 0; ten dots for shard 3),
and E2E reached 2,700 seconds without completing. Their unavailable counts are
not zero and none is called a pass. The user accepted these as shared-core
qualified results pending a future wholly free host. The machine reports 32
logical CPUs and 62 GiB RAM with roughly 40--42 GiB available; observed load
averages around 15--24 show CPU contention rather than memory exhaustion.

One API-focused process collected the current API/scenario selection but then
produced no test output. Independent probes reproduced the host issue with a
minimal `aiosqlite.connect(':memory:')` and with interpreter shutdown after
`asyncio.to_thread()`, while direct synchronous Phase 117 route calls completed
in 1.59s after a 0.49s scan and 2.63s ledger load. The process remains alive at
the owner's direction and is non-authoritative because candidate files changed
after it started. It is a qualified host/runtime observation, not an API pass.
The final matrix runs the non-async runtime closure separately and relies on a
fresh completed API partition or hosted CI for the async boundary.

A provisional real-study rerun likewise caught an in-flight source edit. It
completed one seed, then published a typed `ERROR` at
`runtime_construction` with
`historical_runtime_construction_failed` when the dirty worktree fingerprint
changed before the second session. The command exited 2 after 22.87s. That
artifact is excluded from historical outcome evidence; it demonstrates the
identity-drift guard and is replaced only from a write-frozen tree.

The write-frozen replacement then completed all 20 production sessions in
144.98s and persisted a reload-valid `FAIL`:

```text
UV_CACHE_DIR=/tmp/sw-phase117-final-uv-cache uv run --no-sync python \
  scripts/run_historical_backtest.py \
  --output artifacts/evidence/phase-117/73-easting-phase117.json
# status=FAIL; runs=20; joint_successes=0; lower_confidence_bound=0.0;
# promotion_eligible=false; artifact payload SHA-256 cb33583c...;
# file SHA-256 ba367f39...; 887,834 bytes
```

That pre-status artifact binds the then-current strict ledger and preserves the
expected eligibility reasons `study_failed`, `dirty_revision`,
`validation_source_reused`, and `plan_not_immutably_predeclared`. The final
status-only ledger refresh reruns the same study once more rather than leaving
the retained file bound to an intermediate documentation digest.

Two later write-frozen candidates repeated the identical 0/20 outcome after
intermediate ledger updates: payload `4132f4a5...` in 116.04s, then payload
`5ef94ed...` in 127.443s (file `7f7d59a...`, 887,834 bytes) against execution
ledger `64879a64...`. Each was reload-valid when written; subsequent
cross-document repairs deliberately made each provisional. Neither stale
identity is presented as the retained closure artifact. The closure tree runs
the command above after its last reviewed-document digest refresh; the linked
artifact is then the authoritative full identity and preserves the same exact
20-run vectors, `FAIL`, 0/20 joint successes, 0.0 lower bound, and four
eligibility reasons.

Repository-wide Python lint is green, including the eight F601/F541 failures
reported by remote CI at the original handoff:

```text
.venv/bin/ruff check .
# All checks passed!

git diff --check
# exit 0
```

The final changed/new-Python format probe initially found one file:
`tests/api/test_scenarios.py`. It was mechanically formatted, its reviewed
source digest is refreshed, and its direct live projection remains green. The
exact rerun was:

```text
mapfile -t phase_py_files < <({ git diff --name-only --diff-filter=ACMR;
  git ls-files --others --exclude-standard; } | sort -u | rg '\.py$' |
  rg -v '^(stochastic_warfare/entities/loader.py|stochastic_warfare/simulation/engine.py|stochastic_warfare/simulation/runtime.py|stochastic_warfare/simulation/scenario.py|stochastic_warfare/tools/_run_helpers.py|tests/benchmarks/test_benchmarks.py|tests/unit/test_phase48_deficit_fixes.py|tests/unit/test_phase55_resolution_scenarios.py|tests/unit/test_phase_25a_scenario_wiring.py|tests/validation/test_phase_30_scenarios.py)$')
.venv/bin/ruff format --check "${phase_py_files[@]}"
# checked_files=33; 33 files already formatted
```

The exact command also excludes four phase-touched legacy test files:
`test_phase_25a_scenario_wiring.py`, `test_phase48_deficit_fixes.py`,
`test_phase55_resolution_scenarios.py`, and `test_phase_30_scenarios.py`.
Together with the six large legacy files (`entities/loader.py`,
`simulation/engine.py`, `simulation/runtime.py`, `simulation/scenario.py`,
`tools/_run_helpers.py`, and `tests/benchmarks/test_benchmarks.py`), all ten
were already unformatted at Phase 116. Reformatting their unrelated existing
lines is excluded;
format checking is not the hosted lint gate, while the complete relevant Ruff
lint command above is green. Repository-wide `ruff format --check .` likewise
reports 650 legacy unformatted files outside this phase. One exploratory Ruff
command included `frontend/src/types/api.ts` and produced 784 Python-parser
errors; that was a misrouted command, not Python or TypeScript lint evidence.
The file is covered by the green frontend ESLint/build results.

## Simplify review

`$simplify` returned **READY AFTER IN-SCOPE FIXES**. It required bounded seed
arithmetic and the 1,000-run cap, one verified ledger audit per load, a
zero-argument canonical API cache, pre-parse boolean rejection, and the shared
stable-ID validator. Those fixes and focused controls are present. A second
look found no unresolved HIGH or MEDIUM issue. Optional LOW duplication in
SHA validators/runner assembly and the legacy mutable comparison list did not
justify late production churn.

## Documentation and cross-document audit

`$update-docs` synchronized the specification, public status pages, roadmaps,
remediation matrix, API/scenario/model guides, workflow skills, historical
supersession notices, and this evidence record. REM-047 / Phase 134 retains the
separate 73 Easting source-synchronous fidelity investigation; REM-048 / Phase
135 retains package-bound acceptance attestation. Neither is silently absorbed
into REM-030.

Documentation validation retained its own sequencing red. The first strict
build ran while the prior artifact had been moved to `/tmp` for replacement
and correctly failed exactly five links to the temporarily absent JSON file.
After the new reload-valid artifact was present, both gates passed:

```text
UV_CACHE_DIR=/tmp/sw-phase117-final-uv-cache uv run --no-sync python \
  scripts/validate_docs_links.py
# {"invalid_diagnostic": true, "invalid_exit_code": 1,
#  "valid_exit_code": 0}; real 1.07s

UV_CACHE_DIR=/tmp/sw-phase117-final-uv-cache uv run --no-sync \
  mkdocs build --strict \
  --site-dir /tmp/sw-phase117-final/site-prepostmortem
# exit 0; Documentation built in 7.91s; real 8.45s
```

The strict build emitted the Material/MkDocs-2.0 compatibility advisory and
listed the same three intentional unnav pages:
`scenarios/calibration-template.md`,
`scenarios/depth-checklist-template.md`, and `scenarios/gap-audit.md`. It
reported no link, fragment, navigation, or build error after the artifact was
restored.

The first independent `$cross-doc-audit` found seven real documentation
defects rather than accepting structural consistency as sufficient:

- architecture and API documentation described the configured no-`.git`
  image smoke as already proved locally;
- the API claim-field list omitted claim-level
  `current_engine_regression_evidence`;
- the web guide still described five Block 11 regression references although
  the typed production projection currently groups 34 of 52 scenarios;
- Block 13 contained two stale queued/next statements for active Phase 117;
- README, docs index, and CLAUDE reused the partition-audit manifest as a test
  runner output path even though the runner owns and replaces its manifest;
- the scenario guide's 38-modern / 14-era total omitted the two internal
  benchmark fixtures from its rows, and the README roadmap stopped at Block
  17; and
- the project-structure tree duplicated `frontend/src/types/api.ts`, while
  the REM-048 summary overclaimed the pending hosted image boundary.

`$update-docs` repaired those findings. Production projection through the
canonical loader independently counted 52 scenarios, all 52 aggregate
`unsupported`, 34 with current-engine regression evidence, and zero accepted
claim IDs. That pre-postmortem scanner snapshot retained 191 candidates and
reviews (135 claim-bound plus 56 exclusions) and 243 claims. Later UI/data/doc
repairs first expanded the inventory to 194 candidates; the later strict
School/commander records expanded it again to the final 196. Both earlier
identities and their artifacts are explicitly superseded. An independent strict ledger load had
confirmed all nine audit-deficit families empty only for that earlier tree.

The pre-postmortem cross-document result was **PASS** across all ten required
areas at its then-current evidence freeze:

| Area | Result | Evidence |
|---|---|---|
| Roadmap/devlog alignment | PASS | Phase 117 consistently active through closure; Phase 118 unstarted |
| Remediation traceability | PASS | REM-030 closure is phase-gated; REM-040/047/048 remain explicit owners |
| Contract accuracy | PASS | strict typed ledger/study/artifact as then implemented; aggregate loss gate later superseded by postmortem |
| Production evidence | PASS | then-retained 20-session artifact bound that ledger and remained a truthful `FAIL` |
| Architecture accuracy | PASS | factory/runtime ownership and configured/pending image boundary are explicit |
| API accuracy | PASS | Python, TypeScript, reference fields, stripping, and 52-scenario projection agree |
| Data/catalog accuracy | SUPERSEDED | This earlier path-category count incorrectly reported 38 modern + 14 era and a 191-file scanner; typed current classification is 37 modern + 15 historical and the final inventory is 196 |
| Public status accuracy | PASS | zero accepted scenarios, qualified incomplete runs, and future deficits disclosed |
| Navigation/links | PASS | link validator and strict MkDocs build pass with only declared advisories |
| Provider-context alignment | PASS | CODEX, CLAUDE, README, and public entry points use the same boundaries |

Those post-repair commands were:

```text
.venv/bin/python scripts/validate_scenario_data.py --historical-claims-only
# exit 0 in 15.292s; 31 collections / 83 metrics; 25 Python + 1 frontend
# claim-test surfaces; 164 documentation claims / 67 paths; 191/191 reviews;
# all nine deficit families zero

.venv/bin/python scripts/validate_docs_links.py
# {"invalid_diagnostic": true, "invalid_exit_code": 1,
#  "valid_exit_code": 0}; exit 0 in 0.648s

.venv/bin/mkdocs build --strict \
  --site-dir /tmp/sw-phase117-final/site-crossdoc
# exit 0; Documentation built in 8.25s; real 8.720s
```

These are retained as an invalidated intermediate snapshot, not final closure
evidence; the later typed-era and editor-integrity repairs changed reviewed
sources and required a complete identity refresh.

MkDocs retained only the Material/MkDocs-2.0 advisory and the same three
intentional unnav pages. That audit's initial production-evidence failure was
the expected stale intermediate artifact/ledger identity; its then-current
write-frozen regeneration closed that blocker. Postmortem subsequently added
strict-ID, final-run identity, component-gate, and dot-path repairs and found
the stale standard count documented above. Those reviewed changes deliberately
invalidate this earlier freeze; the corrected ledger/artifact, current 12,092
standard execution, and all ten cross-document areas must pass again before
the final `$postmortem` verdict.

### Postmortem-reopened exhaustive Web UI audit

The final independent audit did not accept the earlier documentation-only
PASS. It compared the live API, React components, production schemas, old
Phase 38/39 claims, and the public guide and found three bounded exposed-data
defects plus a broader UI semantic boundary:

- the scenario API and badges used retired `schools_config`, the detail page
  read retired `base_elevation` / `visibility_km`, and the editor also wrote
  retired `base_elevation`;
- the list/detail badge surfaces discarded typed Space/DEW state, the terrain
  editor offered nine schema-invalid values, and successful run submission
  navigated to a history query the list did not consume;
- map rendering decoded the five production `UnitStatus` integers as an
  unrelated six-state table and treated Surrendered and Routing as Destroyed;
  one-click Space creation emitted `{enable_space: true}` even though the
  production schema requires explicit catalog constellation IDs; and
- the doctrine picker wrote ignored `school_config.{side}_school` values, the
  School toggle wrote ignored `enable_schools`, and the commander picker wrote
  rejected `commander_config.side_defaults` while its catalog omitted 13
  era-specific profiles; and
- chart/map cursor flow, complete event export, causal engagement replay,
  current-frame selection, fullscreen/help affordances, and analysis input
  controls were narrower than prior public claims. The client FOW toggle also
  filters markers only; REM-041 already owns complete authorized side-safe
  projection.

Production fixes now use only canonical scenario keys, retain all six typed
badge flags, redirect to the returned run, expose exactly the five terrain
enum values, decode exact status values and classify only status 2 as
Destroyed, and disable absent Space creation with an explicit unsupported
message rather than choosing a proxy constellation. The school configuration
is now a strict `SchoolScenarioConfig` accepting only exact
`unit_assignments`; Bekaa Valley and Suwalki Gap remove no-op declarations that
assigned 0/65 and 0/39 units. School and commander selectors are explicitly
unavailable instead of emitting proxy state or hiding era-specific selections.
The guide and Phase 30/38/39/54/55/95/96 records state the remaining limits.
REM-049 / Phase 136 in Block 19 owns the larger non-FOW
replay/export/editor/analysis boundary, including complete catalog-backed
School, commander, and Space editing.

The new frontend red proofs failed as intended:

```text
npm test -- --run \
  src/__tests__/pages/ScenarioDetailPage.test.tsx \
  src/__tests__/pages/ScenarioListPage.test.tsx \
  src/__tests__/pages/editor/TerrainSection.test.tsx
# exit 1; 4 failed / 14 passed across 3 files

npm test -- --run \
  src/__tests__/pages/RunConfigPage.test.tsx \
  src/__tests__/pages/editor/TerrainSection.test.tsx
# exit 1; 2 failed / 5 passed across 2 files

npm test -- --run \
  src/__tests__/components/map/UnitDetailSidebar.test.tsx \
  src/__tests__/lib/unitRendering.overlay.test.ts \
  src/__tests__/hooks/useScenarioEditor.test.ts \
  src/__tests__/pages/editor/ConfigToggles.test.tsx
# exit 1; 7 failed / 40 passed across 4 files
```

After implementation, the combined status/editor/navigation regression was
green:

```text
npm test -- --run \
  src/__tests__/pages/RunConfigPage.test.tsx \
  src/__tests__/pages/editor/TerrainSection.test.tsx \
  src/__tests__/pages/editor/TerrainPreview.test.tsx \
  src/__tests__/components/map/UnitDetailSidebar.test.tsx \
  src/__tests__/lib/unitRendering.overlay.test.ts \
  src/__tests__/hooks/useScenarioEditor.test.ts \
  src/__tests__/pages/editor/ConfigToggles.test.tsx \
  src/__tests__/components/map/TacticalMap.test.tsx
# exit 0; 62 passed across 8 files; 921 ms Vitest duration
```

The live-catalog API classification test and direct route result at this
snapshot expected two School scenarios, one DEW scenario, and four Space
scenarios. The later school-integrity repair invalidated both results: Bekaa
Valley and Suwalki Gap had assigned zero units, so their proxy declarations
were removed. The old School set `{bekaa_valley_1982, suwalki_gap}` and its
6.8-second route result are superseded, not current projection evidence.

The corrected frozen route/API contract requires all 52 scenario summaries to
remain `unsupported`, 34 to expose current-engine regression evidence, zero to
expose an accepted claim ID, and exact optional-subsystem sets School `{}`,
DEW `{taiwan_strait}`, and Space
`{korean_peninsula, space_asat_escalation, space_isr_gap, taiwan_strait}`. The
final direct route and hosted/transport checks must establish that result; the
owner-approved silently running pre-repair async process remains qualified and
cannot satisfy the corrected contract. Fresh collection contains 269 API
nodes; the earlier 267/267 result remains historical rather than current.

The completed direct route check after the all-repair ledger refresh reported
52 scenarios, dispositions `{unsupported: 52}`, 34 current-engine regression
summaries, zero accepted claim IDs, eras `{modern: 37, ww2: 5, ww1: 3,
napoleonic: 3, ancient_medieval: 4}`, School `{}`, DEW `{taiwan_strait}`, and
the four Space scenarios above. The final pre-transition rerun completed in
4.97s. The exact command was:

```text
.venv/bin/python -c 'import asyncio
from collections import Counter
from api.config import ApiSettings
from api.routers.scenarios import list_scenarios
rows=asyncio.run(list_scenarios(ApiSettings(data_dir="data")))
print({"scenarios":len(rows),"dispositions":dict(sorted(Counter(row.historical_validation.aggregate_disposition.value for row in rows).items())),"current_engine_regression":sum(row.historical_validation.current_engine_regression_evidence for row in rows),"accepted_claim_ids":sum(len(row.historical_validation.accepted_claim_ids) for row in rows),"eras":dict(sorted(Counter(row.era for row in rows).items())),"schools":sorted(row.name for row in rows if row.has_schools),"dew":sorted(row.name for row in rows if row.has_dew),"space":sorted(row.name for row in rows if row.has_space)})'
```

The independent exhaustive pre-freeze `$cross-doc-audit` then returned the
following current-tree disposition. It did not promote stale evidence to a
pass:

| Area | Result before freeze | Evidence / remaining gate |
|---|---|---|
| Roadmap/devlog alignment | PASS | Phase 117 remains in progress; Phase 118 is unstarted; Phase 135 is only the first phase in Block 19 |
| Remediation traceability | PASS | REM-030 remains phase-gated; REM-040/041/047/048/049/050 have explicit owners and proof obligations |
| Contract accuracy | PASS | split 28/16 gates, strict stable IDs, dot-path rejection, final-run identity, and API-source acceptance drift are present |
| Production evidence | PENDING FREEZE | retained artifact and ledger are intentionally invalidated by the reviewed repairs |
| Architecture accuracy | PASS | factory/session ownership and the pending image boundary remain accurate |
| API/Web accuracy | CONDITIONAL | all 35 audited mismatches are fixed, narrowed, or assigned; live async route completion remains qualified |
| Data/catalog accuracy | PENDING REFRESH | the authoritative scanner inventory is 196 candidate files |
| Public status accuracy | PASS | current in-progress status and zero accepted claims are explicit; recheck follows transition |
| Navigation/links | PASS | link validation and strict documentation build pass |
| Provider-context alignment | PASS | 20/20 provider parity and 44/44 repository-skill controls pass |

Fresh closure-adjacent document/provider commands reported:

```text
.venv/bin/python scripts/validate_docs_links.py
# exit 0; invalid-fixture diagnostic and valid-tree checks both behaved as required

.venv/bin/mkdocs build --strict \
  --site-dir /tmp/sw-phase117-final/site-crossdoc-current
# exit 0; Documentation built in 7.17s

.venv/bin/python -m pytest -q tests/unit/test_repository_skills.py
# 44 passed
```

The strict build retained only the Material/MkDocs-2.0 compatibility advisory
and the three declared unnav pages. The ledger refresh, retained 20-session
artifact, live projection check, and final status re-audit close the three
non-PASS cells; they remain phase blockers at this snapshot.

The subsequent frozen-tree rerun closed those three cells but found one new
Area 7 blocker instead of overlooking it: the canonical typed catalog counts
37 Modern, 5 WW2, 3 WW1, 3 Napoleonic, and 4 Ancient/Medieval scenarios, while
the scenario guide claimed 38 Modern / 14 historical and placed typed-WW2
`eastern_front_1943` in its Modern table. The era reference also omitted that
scenario from its WW2 list. The guide now reports 37 Modern / 15 historical,
moves Eastern Front 1943 into the five-entry WW2 table, and synchronizes the
era reference. The later School/commander and optional-config repairs also
changed reviewed sources, so the ledger, retained artifact, and Area 7 review
must be refreshed once more after the complete semantic freeze. Every earlier
identity is excluded.

## Postmortem

Formal `$postmortem` verdict: **ACCEPT**.

The independent review found the phase over its original REM-030 boundary but
justifiably so: the required exhaustive audit exposed real School, commander,
API/UI, and scenario-data false-authority defects. Phase 117 fixes only the
bounded corruptions; REM-049 and REM-050 own the larger editor/replay and
Escalation/DEW continuations. No stub, proxy, structural-only success,
unconditional verdict, or swallowed failure received completion credit.

The historical claim is integrated at every applicable stage: strict typed
ledger/plan/artifact declarations; source-audited loading; factory-prepared
fresh sessions; explicit CLI and acceptance boundaries; 20 production seeds
plus adversarial controls; split 28-tank, 16-carrier, zero-US, and natural-time
gates that determine the joint 0/20 result; and an atomic reload-valid artifact
plus conservative claim-level API/frontend exposure. The retained result is a
production `FAIL`, not historical validation, and all 52 scenario aggregates
remain unsupported with zero accepted claims.

The accepted pre-transition freeze bound ledger `1038209d...`, study plan
`3e70e8de...`, artifact payload `1dfc4d73...`, and artifact file
`058de80b...` (917,974 bytes). It passed the 196-candidate scanner with 135
claim-bound reviews, 61 exclusions, and all nine deficit families empty; the
226-node historical suite; 437 School/parser/runtime controls; 117 canonical
School/commander controls; 451 frontend tests plus lint/build; the exact
52/34/0 live projection; Ruff, diff, docs, provider, and repository-skill
gates. The late async transport process, slow/E2E containment results, and
hosted no-`.git` image are explicitly qualified rather than called passes.

The later repository-wide evidence-storage policy removes the raw JSON from
the main tree without changing this verdict. Its retained locator is
`branch=evidence/full; immutable_ref=ebcb888a59d4259ccc1e9149cc0a7364f2a65853; path=docs/evidence/phase-117/73-easting-phase117.json`;
the retained bytes are 917,974 bytes with raw SHA-256
`4216ab05cf56c0246dc21f93f0f0dbed8367ac53ac88700fdfa54023699a9a89`
and embedded artifact SHA-256
`57bfe7d89575e721d9cee30c213505c760da3cede642624c7ed7532051e524f4`.
New local runs write to `artifacts/evidence/phase-117/` and main validation
does not require this branch to be fetched. This storage move neither promotes
nor reinterprets the retained `FAIL`.

The postmortem authorized this status transition and one coherent Phase 117
commit after the status-only documentation changes are rebound into the final
ledger, the same 20-run failed artifact is persisted again, and the exact
scanner/binding/docs/public-status gates pass. Any semantic change would
reopen the gate.

## Remaining deficits

- REM-040 / Phase 127 retains the legacy `HistoricalCampaign` era-propagation
  defect. Phase 117 will not use that conversion path.
- A failed backtest supports an explicit unsupported disposition; it is not a
  predictive invalidation of the engine for every intended use.
- No scenario is currently eligible for `production_validated` status.
- REM-047 / Phase 134 owns the first causal production divergence behind the
  frozen 73 Easting source-synchronous miss. Phase 117 does not widen the
  envelope or tune physical performance to hide it.
- Local evidence proves the packaged loader only for the current zero-accepted
  ledger; the configured hosted no-`.git` image smoke remains pending until
  post-push CI. REM-048 / Phase 135 owns build-time attestation and a
  package-bound receipt before a future accepted claim can be exposed from
  that image.
- REM-049 / Phase 136 owns complete ordered Web event export, causal replay and
  cursor synchronization, current-frame selection, catalog-backed Space
  editor creation, catalog-backed School and commander creation, and fully
  bound analysis inputs. Phase 117 fixes the bounded corruptions and removes
  false present-tense claims, but does not call that broader surface complete.
- REM-050 / Phase 137 owns strict consumed Escalation/DEW configuration,
  enabled/disabled production behavior, and a catalog scenario that combines
  a DEW engine with DEW-capable units and records a real engagement outcome.
  Phase 117 only removes ignored enable-like keys and documents the current
  presence/default boundary.
