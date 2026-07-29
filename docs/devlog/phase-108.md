# Phase 108 - Logistics Runtime Wiring

**Status:** Complete

**Started:** 2026-07-28
**Completed:** 2026-07-28

## Why this phase exists

Earlier phases built logistics primitives and direct subsystem tests, while the
production scenario path only constructed empty managers. Scenario depots do
not create stock or topology; the campaign loop does not advance or transfer
supply; and its idle-consumption hook computes with fabricated defaults,
discards the result, and swallows failures.

Phase 108 closes REM-008 and REM-009 with explicit data, one production cadence,
observable inventory/delivery effects, and exact checkpoint continuation.

## Authoritative contract

REM-008 and REM-009 in
[`docs/remediation-backlog.md`](../remediation-backlog.md) define the detailed
schema, runtime, ordering, compatibility, persistence, and non-goal contracts.

Acceptance criteria:

1. Strict enabled logistics loads explicit catalog-backed depot stock, unit
   inventories/maxima, nodes, and direct route templates through
   `ScenarioLoader`.
2. Omitted/disabled logistics leaves legacy depot-only scenarios inert and
   invents no stock, capacity, rate, depot type, or connectivity.
3. Initial and arriving units receive independent profile-derived inventory and
   topology through one atomic registration boundary.
4. Every engine resolution advances one fixed logical cadence without dropped
   or duplicated time.
5. Each boundary updates network state, performs deterministic mass- and
   throughput-constrained resupply, then debits exact eligible idle demand.
6. Connected/disconnected controls produce exact inventory, flow, event,
   supply-state, and `supply_exhausted` outcome differences.
7. Logistics adds no RNG draw; same-seed state, event order, checkpoint bytes,
   and restored continuation are exact and hash-seed independent.
8. Version 108 preserves complete stockpile, network, runtime cadence, and
   dynamic topology while corrupt or incompatible state rejects atomically.

## Non-goals

- No combat or march consumption; that remains REM-020.
- No synchronization between stockpile items, live magazines, or entity fuel;
  that remains REM-021.
- No stochastic spoilage activation.
- No transport mission, convoy, in-transit queue, escort, or cargo-loss model.
- No road discovery, multi-echelon network, min-cost flow, or fair allocation
  claim.
- No historical calibration, force-composition change, physical weapon tuning,
  or invented military stock parameter.

## Production traces

### Configuration and topology

Scenario YAML -> `CampaignScenarioConfig.logistics` plus side depots -> strict
structural/catalog validation -> `ScenarioLoader` -> staged stockpile and
network state -> injected `LogisticsRuntime` -> `SimulationContext`.

### Runtime cadence

`SimulationEngine.step()` at any resolution -> current environment -> fixed
logical cadence -> node/route synchronization -> network update -> depot
resupply -> eligible idle consumption -> supply state -> victory, recorder/API,
and checkpoint.

### Dynamic registration

Due reinforcement -> staged unit/loadout/morale construction -> matching
logistics profile -> independent inventory, node, and routes -> atomic wave
commit -> arrival event.

## Baseline evidence

At phase-start revision
`ad8fdb83bed7200e8c19e925e0975d46d75c25eb`:

- `test_campaign_logistics` declares three depots but a production load creates
  zero runtime depots, unit inventories, nodes, or routes.
- Network update handles blockade route penalties only; it never calls the
  network update or delivers supplies.
- Idle and combat hooks compute demand with fabricated defaults, discard it,
  and swallow failures.
- Existing Phase 6 integration tests manually compose the subsystems and do not
  prove production wiring.
- The logistics fixture begins tactical because its default force separation is
  14.8 km, below the 15 km engagement threshold.

### Initial red evidence

Before production implementation:

```powershell
uv run python -m pytest tests/unit/test_phase_108_logistics_wiring.py `
  -q --tb=short -o addopts=
```

The dedicated suite collected 14 tests: the legacy-disabled inert control
passed and 13 tests failed. The failures reproduce missing strict typed
configuration and catalog checks, absent loader-created runtime topology,
absent production resupply/idle consumption, and incomplete JSON-safe
stockpile/network checkpoint restoration. Constructors, mocks, source
searches, and direct subsystem calls are not counted as red production
evidence.

### Phase-start scenario baseline

The production evaluator completed seeds 42, 43, and 44 at the clean starting
revision:

| Scenario | Seed | Winner / condition | Ticks | Casualties | Engagements | Diagnostics |
|---|---:|---|---:|---:|---:|---|
| `suwalki_gap` | 42 | blue / `force_destroyed` | 12 | 9 | 153 | None |
| `suwalki_gap` | 43 | blue / `force_destroyed` | 16 | 8 | 200 | None |
| `suwalki_gap` | 44 | blue / `force_destroyed` | 12 | 8 | 152 | None |
| `falklands_goose_green` | 42 | blue / `force_destroyed` | 6,113 | 2 | 50 | None |
| `falklands_goose_green` | 43 | blue / `force_destroyed` | 6,110 | 3 | 33 | None |
| `falklands_goose_green` | 44 | blue / `force_destroyed` | 6,110 | 3 | 33 | `CENTROID_COLLAPSE_red` |

Both are legacy depot scenarios without enabled logistics and are predeclared
to remain semantically unchanged. A three-seed `taiwan_strait` attempt exceeded
the 180-second command budget without a completed artifact and is not claimed.
The diagnostics column records evaluator issue codes, not log warnings. Current
Suwalki loads warn that the declared `joint_commander` and
`conventional_commander` profiles are missing while still reporting OK; that
independent scenario-data trust gap is now REM-023.

## Resolved design decisions

- A dedicated logistics-domain runtime owns cadence and allocation;
  `SimulationEngine` only sequences its one all-resolution call.
- Activation is explicit at the scenario root; depot metadata alone is inert.
- Profiles use stable `(side, unit_type)` keys shared by initial and dynamic
  units.
- Inventories and rates use catalog item-native quantities and exact supply
  classes; no consumption fallback enters production.
- Explicit templates expand only direct same-side connectivity. Transit time
  selects a source; delivery remains an aggregate cadence abstraction.
- Stable greedy allocation replaces an unstated fairness assumption.
- Resupply precedes consumption. Moving and battle units are controls until
  activity demand is implemented under REM-020.
- Heavy work occurs only on fixed logical boundaries and adds no RNG draw.
- Checkpoint format advances to 108; versionless compatibility is limited to
  disabled logistics.
- Strictness applies to new logistics/depot models, not unrelated legacy root
  metadata.

## Design review

**Verdict:** Approved with required constraints.

The proposed injected logistics-domain runtime preserves module dependency
direction and keeps orchestration in `SimulationEngine`. Configuration is
typed, ENU-only, explicit, disabled by default, deterministic, and
checkpointed. Synthetic fixture rates establish software behavior only; they
are not military or historical claims. The review does not establish
implementation completeness or authorize phase-complete status.

## Verification plan

- Dedicated Phase 108 red/green production tests.
- Existing loader, engine, logistics, reinforcement, victory, recorder/API,
  and checkpoint selections.
- Strategic/operational/tactical equal-time and resolution-transition checks.
- Connected/disconnected, omitted/disabled, idle/moving/battle, route-condition,
  and shared-throughput controls.
- Same-seed, no-RNG-draw, hash-seed, event-order, and fresh-restore proofs.
- Data validation for the synthetic enabled fixture.
- Evaluator comparison against the six stored legacy rows above.
- Reproducible disabled/enabled timing and call profiling.
- Scoped Ruff, relevant excluded suites, default backend, strict MkDocs, and
  `git diff --check`.
- `$validate-conventions`, `$audit-determinism`, `$validate-data`, `$profile`,
  `$evaluate-scenarios`, and `$simplify`.
- `$update-docs`, `$cross-doc-audit`, then `$postmortem`, followed by one Phase
  108 commit.

## Implementation

### Strict configuration and loader ownership

- Added strict `LogisticsConfig`, `UnitLogisticsProfileConfig`,
  `SupplyQuantityConfig`, and `RouteTemplateConfig` models. Exact enum names,
  finite positive values, duplicate rejection, catalog class agreement,
  inventory maxima, depot mass, same-side references, and direct-edge
  collisions fail during scenario preflight.
- Extended strict depot configuration with explicit type, condition, and
  catalog-backed inventory for enabled logistics. Depot-only legacy scenarios
  remain valid because omission/`enabled: false` is inert.
- Made `ScenarioLoader` construct the stockpile, supply graph, and
  `LogisticsRuntime`, then atomically initialize declared depots and every
  profiled live unit. Each maximum item is materialized even when its initial
  stock is zero, so topology is exact rather than inferred from nonzero state.
- Shared the same owner-bound stage/commit boundary with reinforcement
  admission. A logistics failure leaves the pending wave, roster, loadouts,
  morale, topology, and events unchanged.

### Production cadence and outcomes

- `SimulationEngine.step()` checks the enabled runtime once after environment
  update and before resolution-specific campaign/battle work. Complete fixed
  quanta are processed chronologically at strategic, operational, and tactical
  resolution; positive sub-interval remainder is retained exactly.
- Each boundary synchronizes unit-node geometry, maps the seasonal ground
  state semantically, starts a new route-flow interval, updates the supply
  network, applies blockades, performs direct deterministic resupply, then
  debits eligible idle demand.
- Allocation is stable by side, entity, supply class/item, transit time, and
  depot ID. Delivery is bounded by item mass, elapsed duration, depot stock,
  depot throughput/condition, and route capacity/condition.
- Active-battle, moved, and inactive units remain disqualified for the entire
  open interval. Arriving units are charged only from logical registration
  time. The disconnected-network control retains configured consumption but
  skips degradation and resupply.
- Stockpile delivery/consumption and boundary notifications now use typed
  event journals. State commits once; every observer is attempted, and
  subscriber failures then propagate without replaying the committed boundary.
- `supply_exhausted` now honors its condition-local threshold, so controlled
  connected/disconnected production runs change a real victory outcome.

### Persistence and hardening

- Advanced engine checkpoint format to 108. Logistics state includes cadence,
  eligibility/accounting/activity maps, boundary positions, depot/unit
  inventories and maxima, spoilage accumulators, nodes, routes,
  infrastructure, conditions, and current flow.
- Enabled restore validates exact scenario/catalog/roster/topology envelopes
  before any runtime state mutates. Registration and restore plans are private,
  runtime-owned, and SHA-256 fingerprinted, so foreign or mutated plans reject.
- Disabled logistics serializes canonical empty managers and zero cadence and
  remains an O(1) production gate. Versionless checkpoints are accepted only
  for logistics-disabled runtimes.
- Supply-network restore now rejects invalid enum, geometry, and topology
  values; stockpile depletion emits exactly once. The obsolete campaign-only
  blockade/consumption branches were removed so the injected runtime is the
  single production owner.

## Adversarial and simplify review

Independent production-path review found and drove fixes for zero-stock
topology loss, incorrect cadence/accounting boundaries, coarse-tick
movement/battle eligibility, atomic observer failure behavior, mutable staged
plans, incomplete enum/geometry validation, and disabled-runtime checkpoint
chronology. The final core/runtime/checkpoint verdicts were ready with no
medium- or high-severity blocker.

The simplify review's initial verdict was ready after in-scope fixes. It drove
removal of the dead campaign blockade path and obsolete topology-seeding test
helper, replacement of repeated route search with direct inbound-route scans,
owner-bound staged-plan mutation/fingerprint verification, and shared EventBus
handler
iteration. After those changes its current 226-test focused logistics selection passed
and no required work remained. It recorded two nonblocking internal
opportunities: `LogisticsRuntime.stage_state()` is large and tightly coupled to
manager state schemas, and stationary route geometry is recomputed at each
boundary. A future manager-owned stage/commit refactor and cached stationary
geometry could reduce complexity and cost without changing the Phase 108
contract.

## Residual boundaries

REM-020 and REM-021 keep activity demand and live-store synchronization visible.
Transport missions, spoilage, optimization, and historically sourced scenario
stocks remain outside Phase 108. The synthetic fixture quantities establish
software behavior only and are not a military calibration claim.

The evaluator's `started_tactical` diagnostic compares the string form of an
integer-backed resolution enum and is not reliable evidence. Direct production
inspection proves the completed fixture has a 24 km minimum force separation
and starts at `STRATEGIC`; the broader analysis-tool trust boundary remains
REM-017.

## Determinism, scenario evaluation, and performance

- The maintained
  `test_canonical_output_is_independent_of_python_hash_seed` subprocess proof
  runs the same two-unit, two-step production payload at scenario seed 11,108
  under `PYTHONHASHSEED=1` and `2`. Both produce checkpoint SHA-256
  `d17598b81310bc3b37f361a2396d67a0efe75da7a7f912a4a1d927253e713ee0`
  and ordered-event SHA-256
  `e054c659d5073809ff9caaae14be72ae5342d82a01e504022edef2d27fa6af1f`.
  Same-seed tests also prove the enabled update consumes no RNG.
- The completed enabled fixture starts strategically with 24 km minimum
  separation and completes successfully as draw/`time_expired`: 86 ticks,
  259,565 simulated seconds, 8 casualties, 44 engagements, no diagnostics, and
  0.62 seconds wall time in the final proof run.
- All six predeclared legacy rows in the phase-start table reproduced exactly,
  including winner, condition, ticks, casualties, engagements, and diagnostic.
  This proves depot metadata did not activate logistics implicitly. REM-023
  separately records warning-only missing commander references.
- The final enabled production-fixture timing used one warm-up followed by five
  repetitions on Windows 11 build 26200, Python 3.12.10, an Intel i7-13620H
  (10 cores/16 logical processors), and 31.7 GiB RAM. Relevant runtime
  dependencies were NumPy 2.4.2, NetworkX 3.6.1, and Pydantic 2.12.5. The
  measured closure worktree was based on phase-start revision
  `ad8fdb83bed7200e8c19e925e0975d46d75c25eb`. The median was 0.4776 seconds,
  with a 0.4554-0.4862 second range. All five runs reproduced
  draw/`time_expired`, 86 ticks, 8 casualties, 44 engagements, and no
  diagnostics.
- A maintained logistics E2E run profiled through `pytest` recorded 20
  `LogisticsRuntime.update()` calls at 0.005398 seconds cumulative, including 6
  `_run_quantum()` calls at 0.004069 seconds, 6 `_resupply()` calls at 0.001074
  seconds, and 6 `_consume_idle()` calls at 0.000322 seconds. Pytest and event
  loop startup dominate the 4.504-second whole-process profile; the listed
  runtime rows isolate the production logistics path.
- The disabled-path control used one warm-up and five fresh Phase 73 Easting
  production benchmark repetitions. Its median was 6.6855 seconds, with a
  6.6704-6.8936 second range; every run reproduced blue/185 ticks/seed 42 and
  passed `BenchmarkBaseline.check_regression()` against the checked-in
  8.00-second baseline and 20% margin.
- Enabled logistics did not exist at the phase-start revision, so there is no
  same-workload enabled before/after comparison and no optimization claim.
  These measurements establish current cost and protect the disabled path, but
  they do not predict scaling for large enabled force structures or dense
  route graphs. Disabled updates remain O(1); manager-owned restore staging and
  stationary-geometry caching remain possible future profiling targets.

Exact performance commands:

```powershell
uv run python -c "import statistics,time; from pathlib import Path; from scripts.evaluate_scenarios import run_scenario; p=Path('data/scenarios/test_campaign_logistics/scenario.yaml'); d=Path('data'); run_scenario(p,d,seed=42); runs=[(lambda t0,r:(time.perf_counter()-t0,r))(time.perf_counter(),run_scenario(p,d,seed=42)) for _ in range(5)]; xs=[x for x,_ in runs]; print(xs,statistics.median(xs),min(xs),max(xs)); print([(r.victory_side,r.victory_condition,r.ticks_executed,r.total_casualties,r.engagement_events,r.issues) for _,r in runs])"
# [0.4804322, 0.4554136, 0.4729152, 0.4862334, 0.4776091]
# median 0.4776091; range 0.4554136-0.4862334
# all outcomes: draw, time_expired, 86 ticks, 8 casualties, 44 engagements, []

uv run python -m cProfile -o C:\tmp\phase108-enabled-final.prof -m pytest tests/e2e/test_scenario_smoke.py -k test_campaign_logistics -q --tb=short -o "addopts="
# 1 passed, 40 deselected in 3.83s

uv run python -c "import pstats; s=pstats.Stats(r'C:\tmp\phase108-enabled-final.prof'); rows=[(v[3],v[2],v[1],k) for k,v in s.stats.items() if k[0].replace('\\','/').endswith('logistics/runtime.py')]; print('cum_s self_s calls function'); [print(f'{ct:.6f} {tt:.6f} {nc} {k[2]}:{k[1]}') for ct,tt,nc,k in sorted(rows,reverse=True)[:25]]"
# update: 20 calls / 0.005398s cumulative
# _run_quantum: 6 / 0.004069s; _resupply: 6 / 0.001074s
# _consume_idle: 6 / 0.000322s

uv run python -c "import statistics; from tests.benchmarks.benchmark_suite import BenchmarkBaseline,SCENARIOS_DIR,run_benchmark; p=SCENARIOS_DIR/'73_easting'/'scenario.yaml'; run_benchmark(p,profile=False); rs=[run_benchmark(p,profile=False) for _ in range(5)]; xs=[r.wall_clock_s for r in rs]; b=BenchmarkBaseline(); print('samples',xs); print('median',statistics.median(xs),'min',min(xs),'max',max(xs)); print('checks',[b.check_regression('73_easting',r) for r in rs]); print('outcomes',[(r.winner,r.ticks_executed,r.seed) for r in rs])"
# median 6.6855434s; range 6.6704336-6.8936195s
# every check: False/OK; every outcome: blue, 185 ticks, seed 42
```

## Verification evidence

Closure commands and results:

```powershell
uv run python -m pytest tests/unit/test_phase_108_logistics_wiring.py -q --tb=short -o "addopts="
# 115 passed in 81.73s

uv run python -m pytest tests/unit/test_phase_108_logistics_wiring.py tests/unit/test_supply_network.py tests/unit/test_phase56_performance_logistics.py tests/unit/test_logistics_events.py -q --tb=short -o "addopts="
# 226 passed in 81.40s

uv run python -m pytest tests/unit/test_simulation_scenario.py tests/unit/test_simulation_engine.py tests/unit/test_simulation_campaign.py tests/unit/test_phase_107_scenario_wiring.py tests/unit/test_logistics_events.py tests/unit/test_phase85_integration.py tests/unit/test_simulation_victory.py tests/integration/test_phase6_integration.py tests/integration/test_phase_12b_logistics_depth.py -q --tb=short -o "addopts="
# 375 passed

uv run python -m pytest -q --tb=short
# 10,428 passed, 21 skipped, 346 deselected, 6 warnings in 373.67s

uv run python -m pytest tests/api/test_runs.py -q --tb=short -o "addopts="
# 14 passed

uv run python -m pytest tests/e2e/test_scenario_smoke.py -k test_campaign_logistics -q --tb=short -o "addopts="
# 1 passed, 40 deselected

uv run python -m pytest tests/benchmarks/test_benchmarks.py::TestBenchmark73Easting -q --tb=short -o "addopts="
# 3 passed

uv run python -m pytest tests/unit/test_repository_skills.py -q --tb=short -o "addopts="
# 41 passed

uv run python scripts/validate_scenario_data.py --scenarios-only
# 51 scenario YAML files; 0 errors, 0 warnings

uv run python scripts/validate_scenario_data.py --file data/scenarios/test_campaign_logistics/scenario.yaml
# passed

foreach ($scenario in @("suwalki_gap", "falklands_goose_green")) {
  foreach ($seed in @(42, 43, 44)) {
    uv run python scripts/evaluate_scenarios.py --scenario $scenario --no-details --seed $seed
  }
}
# all six rows matched the phase-start table

uv run python -c "from pathlib import Path; from scripts.evaluate_scenarios import run_scenario; r=run_scenario(Path('data/scenarios/test_campaign_logistics/scenario.yaml'),Path('data'),seed=42); print(r.victory_side,r.victory_condition,r.ticks_executed,r.sim_duration_s,r.total_casualties,r.engagement_events,r.issues,round(r.duration_wall_s,3))"
# draw time_expired 86 259565.0 8 44 [] 0.62

# From frontend/
npm test -- --run
# 79 files, 418 tests passed

uv run mkdocs build --strict
# passed

$tracked = @(git diff --name-only -- '*.py')
$untracked = @(git ls-files --others --exclude-standard -- '*.py')
$phaseFiles = @($tracked + $untracked | Sort-Object -Unique)
uv run ruff check $phaseFiles
# passed

git diff --check
# passed; line-ending notices only
```

Fresh passing gates:

| Gate | Result |
|---|---:|
| Phase 108 production behavior | 115 passed |
| Focused logistics/core review selection | 226 passed |
| Loader/engine/campaign/logistics compatibility selection | 375 passed |
| Default-selected backend suite | 10,428 passed, 21 skipped, 346 deselected |
| API run boundary | 14 passed |
| Logistics campaign E2E smoke | 1 passed, 40 deselected |
| Phase 73 easting benchmark | 3 passed |
| Scenario YAML validation | 51 files, 0 errors, 0 warnings |
| Enabled fixture validation | Passed |
| Repository skill/workflow contract | 41 passed |
| Frontend suite | 418 passed across 79 files |
| Strict MkDocs build | Passed |
| Changed-Python Ruff selection | Passed |
| `git diff --check` | Passed (line-ending notices only) |

The default backend command applies `pyproject.toml` exclusions for `slow`,
`benchmark`, `terrain`, `api`, and `e2e`, and ignores `tests/api` and
`tests/e2e`. Phase 108 separately ran its relevant API run boundary and the
logistics campaign E2E smoke plus the Phase 73 easting benchmark selection.
Slow and terrain categories were not relevant to or claimed by this phase;
REM-013 retains the repository-wide CI disclosure work.

The repository-wide Ruff run still reports the same eight phase-start findings:
six duplicate mapping keys owned by REM-010/Phase 109 and two no-placeholder
f-strings owned by REM-013/Phase 112. Full catalog validation still reports the
predeclared unmapped-equipment set owned by REM-010; the changed fixture and all
scenario YAML pass. These baseline failures were reproduced from the clean
phase-start source and are not attributed to Phase 108.

The phase, focused, current-revision default backend, frontend, skill/workflow
contract, strict documentation build, changed-Python Ruff selection, and
`git diff --check` closure gates all passed. Frontend stderr retains its known
React/jsdom test warnings; the suite exits successfully.

Strict MkDocs exits successfully but reports seven pre-existing historical
devlog-index links whose requested anchors do not exist. REM-022 records that
navigation debt for Phase 112 instead of treating a successful build as proof
that every historical fragment resolves.

## Postmortem

**Verdict:** Complete. REM-008 and REM-009 are closed.

| Dimension | Verdict |
|---|---|
| Scope | On target; all declared Phase 108 behavior delivered |
| Quality | High; independent reviews found no unresolved medium/high issue |
| Integration | Fully proven through production loader, engine, outcome, event, reinforcement, API/recorder, and checkpoint paths |
| New deficits | REM-022 and REM-023 recorded for Phase 112; neither is missing Phase 108 behavior |
| Validation | All declared focused, compatibility, default, API, E2E, benchmark, data, frontend, documentation, lint, and determinism gates passed with exclusions disclosed above |
| Action items | None before closure; REM-020/021 and the named internal refactor/performance opportunities remain explicitly deferred |

The phase began with a production red suite rather than subsystem mocks, used
one declared contract for configuration/runtime/checkpoint behavior, and
retained the legacy depot-only path as a negative control. Implementation
reached the real loader, engine, event, victory, reinforcement, recorder/API,
and checkpoint boundaries. Independent design, convention, determinism,
scenario, data, performance, simplify, documentation, and adversarial reviews
found no unresolved completion blocker.

The design review materially constrained the result: orchestration stays in
`SimulationEngine`, state and allocation live in a dedicated logistics-domain
runtime, the feature is explicitly gated and ENU-only, and the synthetic rates
are not presented as sourced military behavior. No new stochastic model or
physical performance parameter was introduced.

Deferred behavior is named rather than papered over: REM-020 owns march/combat
demand, REM-021 owns live fuel/magazine synchronization, REM-017 owns evaluator
trust, and REM-010 owns the pre-existing equipment/catalog baseline. The large
restore validator and stationary geometry recomputation are internal
refactor/optimization opportunities, not missing Phase 108 behavior.

### Completion evidence matrix

| Capability | Declared | Loaded | Wired | Enabled | Exercised | Outcome | Persisted/exposed |
|---|---|---|---|---|---|---|---|
| REM-008 typed topology and resupply | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| REM-009 all-resolution network update and idle debit | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
