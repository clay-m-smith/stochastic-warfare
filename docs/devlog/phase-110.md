# Phase 110 - ASAT Production Integration

**Status:** Complete

**Started:** 2026-07-29

**Completed:** 2026-07-29

## Why this phase exists

The production campaign loop calls
`SimulationEngine._attempt_asat_engagements()`, but the method only writes a
debug message. `ScenarioLoader` instantiates empty space engines without
loading any of the 9 constellation or 3 ASAT weapon catalog files, and the
advertised ASAT scenario does not enable space at all. Existing green tests
construct subsystem objects directly, use mocks, or call
`degrade_constellation()` instead of exercising an ASAT action.

Phase 110 closes REM-011 under the durable contract in
[`docs/specs/asat-production-integration.md`](../specs/asat-production-integration.md).

## Authoritative contract

The phase will:

1. replace the untyped space scenario block with strict catalog selections,
   finite ASAT asset declarations, and scheduled exact-target orders;
2. load selected constellation and weapon definitions through the real
   `ScenarioLoader`;
3. execute supported direct-ascent kinetic orders once at a deterministic
   logical tick boundary;
4. enforce asset ownership, finite rounds, per-asset cooldown, enemy target,
   active target, and altitude range;
5. change satellite state through `ConstellationManager` and expose the
   attempt plus constellation transition through recorder/API events;
6. preserve catalog topology, satellite, asset, order, debris, and RNG state
   across fresh checkpoint continuation;
7. make `enable_asat` a real disabled control with no hidden calibration gate
   and no ASAT RNG consumption; and
8. validate all 9 constellation and 3 ASAT catalog files in the repository
   data validator.

The shipped validation scenario will target a catalog-backed LEO satellite.
It will not inflate an authored weapon's range to preserve the false historical
claim that the same weapons can attack GPS at approximately 20,200 km.

## Non-goals

- No automatic or AI target selection.
- No tactical unit or live Class V attachment for strategic ASAT assets.
- No production support claim for co-orbital or laser ASAT types.
- No historical calibration or high-fidelity debris model.
- No Phase 111 work.

## Design and research gate

`$spec`, `$design-review`, `$research-military`, `$research-models`, and
`$scenario` were invoked before production edits.

The initial design review approved a dedicated typed space-domain action queue
with notes. The subsequent adversarial specification review returned
`NEEDS REVISION` and implementation remained paused. It required the contract
to freeze the dependency-neutral configuration boundary, exact
`SpaceEngine -> ASATEngine` tick ordering, whole-context checkpoint preflight,
removal of unsafe direct-fire APIs, manager-owned cascade kills, validation
ranges, event/rejection vocabulary, schedule cardinality, catalog load scope,
and exact scenario migrations. The specification incorporated every finding;
the re-review returned `APPROVED` with no remaining implementation blocker.
This design approval is not implementation or closure evidence.

Official USSF planning guidance supports explicit target/weapon pairing and
observable measures. NIST supplies the Rayleigh radial-error CDF used by the
kinetic model. NASA breakup evidence supports an observable debris consequence
but does not calibrate the repository's simple Poisson abstraction. Full source
classification, links, assumptions, and limitations are in the specification.

## Production trace at phase start

| Stage | Phase-start evidence |
|---|---|
| Declared | `space_config` is an untyped dictionary; component models exist, but no ASAT asset/order schema exists |
| Loaded | Three ASAT and nine constellation YAMLs exist but production loads none |
| Wired | `SimulationEngine` calls a logging-only placeholder; no production caller reaches `ASATEngine.engage()` |
| Enabled | `enable_space` can instantiate an empty suite; `enable_space_effects` gates the placeholder, so enabled ASAT remains a no-op |
| Exercised | Existing tests call components directly, use mocks, or check method presence |
| Outcome-affecting | No production ASAT action changes a satellite |
| Persisted/exposed | Space component state and generic events have delegation paths, but no production action/order/event exists |

Fresh real-loader probes established:

- `space_asat_escalation`: `space_config=None`, no space engine, zero ASAT
  events;
- `taiwan_strait` and `korean_peninsula`: a space engine exists, but it has
  zero satellites and zero ASAT weapons; and
- the current ASAT sequence test directly reduces a constellation count
  without using a weapon, asset, order, or production engine tick.

## Verification plan

- Encode a production red test for catalog loading, a due order, satellite
  state/event change, disabled control, strict failures, and fresh checkpoint
  continuation.
- Run the existing Phase 17/54/65/107 space selections as regression controls.
- Extend and run file-specific plus catalog-wide data validation.
- Evaluate the ASAT scenario at fixed seeds and preserve its phase-start row.
- Run `$validate-conventions`, `$audit-determinism`, `$validate-data`,
  `$evaluate-scenarios`, and `$simplify`.
- Run focused, API/E2E, default backend, repository-wide Ruff, strict MkDocs,
  and diff/whitespace checks.
- Finish with `$update-docs`, `$cross-doc-audit`, and `$postmortem`, then one
  coherent Phase 110 commit. Phase 111 must not start first.

## Start gate and machine envelope

The phase starts from clean synchronized `main` at:

```text
f5a5a2d1b0a69cd38bc4345753b1cf889076b78d
```

`CODEX.md`, `AGENTS.md`, Block 12, REM-011, the Phase 109 devlog, the
applicable implementation, tests, catalogs, scenarios, architecture, and
selected skill instructions were read before production changes.

The host exposes 32 logical CPUs and 62 GiB RAM, with 58 GiB available at the
phase baseline:

```text
nproc
# 32
free -h
# Mem: 62 GiB total, 58 GiB available
# Swap: 7.8 GiB total, 7.8 GiB available
```

Independent read-only baselines were run concurrently. Each pytest invocation
remains serial because `pytest-xdist` is not installed. Python commands use
`UV_CACHE_DIR=/tmp/phase110-uv`.

## Baseline and production red evidence

### Remote lint concern

The owner's reported remote Python lint failure is not reproducible at the
Phase 110 start. Phase 109's repair is present on synchronized `main`:

```text
UV_CACHE_DIR=/tmp/phase110-uv uv run ruff check \
  stochastic_warfare/ api/ tests/ scripts/
# All checks passed!
```

The final phase gate will repeat the same repository-wide command after all
Phase 110 changes.

### Existing green component/structural suite

```text
UV_CACHE_DIR=/tmp/phase110-uv uv run pytest -q --tb=short -o addopts= \
  tests/unit/test_phase_17a_orbits_constellations.py \
  tests/unit/test_phase_17b_gps.py \
  tests/unit/test_phase_17c_isr_ew.py \
  tests/unit/test_phase_17d_satcom_asat.py \
  tests/unit/test_phase_17e_integration.py \
  tests/unit/test_phase_17f_validation.py \
  tests/unit/test_phase_25a_scenario_wiring.py \
  tests/unit/test_phase54_era_wiring.py \
  tests/unit/test_phase_65_infra.py \
  tests/unit/test_phase_65_structural.py \
  tests/unit/test_phase_65a_space_isr_ew.py \
  tests/unit/test_phase_65b_asat_sigint.py \
  tests/unit/test_phase_65c_eccm.py \
  tests/unit/test_phase_107_era_gates.py \
  tests/unit/test_phase_107_scenario_wiring.py
# 409 passed in 29.99s
```

These 409 green tests are not REM-011 closure evidence. Their ASAT coverage is
direct-component, raw-data, mock, source-shape, or no-crash evidence.

### Real loader/tick probe

A fresh seed-42 `ScenarioLoader`, recorder, and one
`SimulationEngine.step()` reported:

| Scenario | Space engine | Satellites | ASAT weapons | ASAT events | SPACE RNG changed |
|---|---:|---:|---:|---:|---:|
| `space_asat_escalation` | no | 0 | 0 | 0 | no |
| `taiwan_strait` | yes | 0 | 0 | 0 | no |
| `korean_peninsula` | yes | 0 | 0 | 0 | no |

The Korean load also repeated the known missing-commander warnings assigned to
REM-023/Phase 112; Phase 110 does not hide or absorb that independent deficit.

### Scenario/data baseline

```text
UV_CACHE_DIR=/tmp/phase110-uv uv run python \
  scripts/validate_scenario_data.py \
  --file data/scenarios/space_asat_escalation/scenario.yaml
# exit 0; no output despite the absent space configuration

UV_CACHE_DIR=/tmp/phase110-uv uv run python \
  scripts/evaluate_scenarios.py \
  --scenario space_asat_escalation \
  --output /tmp/phase110-space-asat-baseline.json \
  --no-details --seed 42
# OK; 32 ticks; 8 casualties; 52 engagements; 16/16 moved;
# 0/16 stuck; zero reported issues; 0.6s
```

The evaluator row contains no space state or ASAT event diagnostic and
therefore cannot contradict the production red.

### Encoded production red

The first Phase 110 test uses the shipped scenario, real loader, engine,
recorder, enabled/disabled controls, and strict top-level schema:

```text
UV_CACHE_DIR=/tmp/phase110-uv uv run pytest -q --tb=short -o addopts= \
  tests/integration/test_phase_110_asat_production.py
# 3 failed in 0.78s
```

The exact failures were:

1. the shipped ASAT scenario loaded `space_engine=None`;
2. it had no `space_config` in which an enabled/disabled ASAT control could
   exist; and
3. the scenario schema silently ignored misspelled `enable_assat` instead of
   raising `ValidationError`.

Implementation starts only after this declared production red and the
independent specification review.

Implementation details, focused and broader validation, conditional reviews,
documentation audit, postmortem, and final status transition will be recorded
below as the phase progresses.

## Implementation

### Typed catalog and scenario boundary

`space/config.py` now owns strict dependency-neutral models for constellation
definitions, orbital elements, ASAT weapon definitions, finite assets,
scheduled exact-target orders, and the complete `SpaceConfig`. Unknown fields,
duplicate IDs, booleans used as numbers, non-finite values, invalid enum/type
schemas, inconsistent constellation topology, and values outside the
propagator/Poisson numerical domains fail explicitly.

`CampaignScenarioConfig.space_config` is typed instead of
`dict[str, Any]`. Scenario duration is now a strict finite positive number, so
NaN, infinity, booleans, and numeric strings cannot bypass the rule that an
order must become due within the scenario. Omitted space theater coordinates
derive from the scenario latitude/longitude.

`space/catalog.py` loads every file under both space catalog directories with
the duplicate-key-rejecting YAML loader and a canonical sorted traversal. It
rejects duplicate semantic IDs, unknown constellation/weapon/asset/side/target
references, friendly targets, unsupported production types, impossible
altitude envelopes, and inconsistent generated satellite IDs before a
`SimulationContext` is published. Multiple unique assets may share one
immutable weapon definition without overwriting inventory or cooldown; a
behavioral two-asset test proves both launch, maintain independent state, and
restore independently.

### Runtime execution and observation

`ScenarioLoader` resolves selected catalog definitions and constructs the
complete constellation, GPS, ISR, early-warning, SATCOM, and ASAT runtime with
the injected `ModuleId.SPACE` stream and scenario clock.

`SpaceEngine.update()` is the sole production action boundary:

1. propagate selected satellites to the logical tick end;
2. age and resolve pre-existing debris;
3. execute newly due orders in
   `(execute_at_s, declaration_index)` order; and
4. update GPS, ISR, early-warning, and SATCOM consumers from the resulting
   constellation state.

`ASATEngine` owns immutable definitions plus mutable unique assets, orders,
inventory, cooldown, results, and debris from construction. The old
`register_weapon()` and caller-supplied-side `engage()` bypasses and the
unconsumed laser-dazzle dictionary are gone. Production accepts
`DIRECT_ASCENT_KKV` only and fails co-orbital/laser assets during resolution.
Pre-launch rejection consumes no round and no RNG. An accepted launch consumes
one round and starts cooldown even on a miss.

Kinetic probability uses the declared Rayleigh radial-error CDF with stable
tail arithmetic. A hit and any canonical debris-cascade kill route through
`ConstellationManager.deactivate_satellite()`. The manager publishes
`ConstellationDegradedEvent` before the ASAT engine publishes the complete
`ASATEngagementEvent`; subscriber failures occur after committed mutation and
cannot duplicate the order. The generic API event endpoint exposes and
side-filters the exact action.

The former `SimulationEngine._attempt_asat_engagements()` logging hook is
removed. The master loop passes logical elapsed time and scenario timestamp to
the runtime-owned `SpaceEngine`; `enable_asat` is the only ASAT execution gate.

### Persistence and integrity

Checkpoint schema 110 persists the selected catalog fingerprint, exact
satellite orbital/active state, asset topology/inventory/cooldown,
pending/completed order partition and results, debris, service history, and
the existing SPACE RNG stream.

Restore stages the entire space graph before any context clock, RNG, roster,
morale, loadout, logistics, or engine state commits. It validates:

- catalog, satellite, asset, and order topology;
- manager time against the checkpoint clock and action history against tick
  count;
- result/outcome/rejection/inventory/cooldown consistency;
- disabled-ASAT pristine state;
- debris count bounds and completed-hit conservation;
- chronological constellation counts and active target state;
- GPS/SATCOM prior-value caches against an isolated staged constellation view;
  and
- ISR satellite references and future overpass times.

Adversarial transplants and corrupt numeric state therefore raise a normalized
validation error and leave checkpoint bytes unchanged. Fresh restore before
and after the action reproduces event order, hit/debris, inventory, satellite
state, RNG state, and continued checkpoint bytes.

### Data and scenario migration

All nine constellation files now explicitly author `true_anomaly_deg`.
`space_asat_escalation` is a hypothetical 12-hour validation scenario with
3,600-second tick resolutions, selected `keyhole_optical`, one red Nudol asset
and round, and an exact order against `keyhole_optical_p0_s0` at 7,200 seconds.
No weapon range was inflated to attack GPS.

Taiwan Strait and Korean Peninsula remain ASAT-disabled and explicitly select
seven blue-owned service constellations. These are hypothetical availability
assumptions, not historical ORBAT claims. The repository data validator now
always validates the complete 9-definition constellation and 3-definition
weapon catalogs and scenario references; `--space-only` and single-space-file
routes use the same production `SpaceCatalog`.

## Production capability evidence

| Stage | Evidence |
|---|---|
| Declared | Strict `SpaceConfig`, immutable definitions, unique finite assets, exact-target scheduled orders, supported-type enum, outcomes/reasons, and event schema |
| Loaded | `ScenarioLoader` reads the complete duplicate-safe catalogs, resolves every reference/side/envelope, and materializes selected definitions before context publication |
| Wired | Master campaign tick passes logical time to `SpaceEngine`, which orders propagation/debris/actions before real GPS/ISR/EW/SATCOM consumers |
| Enabled | Identical `enable_asat=true/false` worlds prove one execution gate; disabled controls preserve satellite, inventory, order, event, and SPACE RNG state |
| Exercised | Shipped seed-42/110/111 runs execute `red_keyhole_strike_1` exactly once with real `red_nudol_1`/`nudol_asat`; strict reference/type/range/inventory/timing/observer controls fail or report exactly |
| Outcome-affecting | Each enabled run deactivates `keyhole_optical_p0_s0`, changes active count 4 to 3, consumes the only round, and exposes the change to a real same-tick SATCOM consumer test; manager-owned debris cascade behavior is separately exercised |
| Persisted/exposed | Schema-110 fresh continuation is exact; corrupt whole-context restore is atomic; recorder and production API expose exact action/side/target/result/count fields |

## Red-to-green and adversarial review

The encoded production red changed from 3 failures to the final 49-test
Phase 110 suite. Independent adversarial review remained active through the
implementation and found defects that ordinary shape tests missed:

- future action state transplanted to an earlier clock;
- malformed and semantically forged GPS/SATCOM service state;
- impossible asset-depletion results and pre-first-tick completed orders;
- completed history transplanted into an ASAT-disabled runtime;
- missing completed-hit debris, unbounded debris integers, and forged
  same-constellation count chains;
- Poisson means and semimajor axes outside the runtime numerical domain;
- unstable extreme Rayleigh arithmetic;
- partial asset mutation before a failing stochastic calculation; and
- future ISR overpass state that could suppress real reports.

Each material finding received a production/state regression and atomic
rejection or stable computation. The final adversarial verdict is
**APPROVED**. Its fresh non-API Phase 110 run reported 44 passing tests before
the later simplify regressions; the final coordinating run reports 49.

`$simplify` returned **READY AFTER IN-SCOPE FIXES** after three medium findings
were corrected:

1. strict finite scenario duration now protects the order horizon;
2. two assets sharing one definition now have behavioral
   inventory/cooldown/checkpoint proof; and
3. future ISR overpass history is rejected atomically.

The large ASAT/checkpoint validators encode distinct reachability and atomicity
invariants; extraction would add mutable coupling without removing policy.
No tick-path performance issue is material at the configured catalog/order
sizes.

The review also identified a lower-priority legacy Space ISR limitation:
buffered reports are generic dictionaries and checkpoint normalization does
not provide a typed `Position` rehydration boundary. A production Taiwan probe
with a malformed future/unknown report was inert, cleared on the next tick,
and left engine, SPACE RNG, and fog-of-war state equal. It is not REM-011
closure evidence or a hidden ASAT deficit; REM-027 assigns a typed report
round-trip/negative-control fix to Phase 112.

## Convention and determinism reviews

`$validate-conventions` is **APPROVED** and `$audit-determinism` is
**DETERMINISTIC / APPROVED**, with no critical or warning findings.

Static review found no Python `random`, module-level `np.random`, wall-clock,
or bare-print candidate in changed production paths. The only ASAT draws are
through the loader-injected `RNGManager.get_stream(ModuleId.SPACE)`. Due orders
sort by schedule/declaration; debris bands sort numerically; cascade targets
sort by satellite ID; pending sets are membership-only and serialize through
configuration order.

An independent seed-42 production isolation probe reported 16 total streams,
no difference across the 15 non-SPACE streams, an expected SPACE difference
for enabled ASAT, and atomic `ValueError` rejection for numeric overflow.
Rejected, not-yet-due, inactive, out-of-range, and disabled paths consume no
draw. Same-seed, fresh-continuation, and `PYTHONHASHSEED=1/987654` proofs are
green.

The shared SPACE stream is intentional under the Phase 110 contract. A future
stochastic space-service addition must preserve the fixed orchestration order
or declare a finer stream-allocation contract.

## Data validation

The final production validator command was:

```text
UV_CACHE_DIR=/tmp/phase110-uv uv run python scripts/validate_scenario_data.py
```

It exited 0 and reported:

- 184 unit YAML files;
- modern: 102 units, 394 authored occurrences, 244 distinct keys,
  101 sensor-required, 1 intentionally sensorless;
- ancient/medieval: 20 units, 67 occurrences, 34 keys, 20 sensor-required;
- Napoleonic: 21 units, 57 occurrences, 27 keys, 21 sensor-required;
- WWI: 16 units, 57 occurrences, 47 keys, 16 sensor-required;
- WWII: 25 units, 104 occurrences, 93 keys, 25 sensor-required;
- 442/442 registry coverage, 0 unmapped, 0 stale;
- 9 constellation definitions and 3 ASAT weapon definitions;
- 51 scenario YAML files and 51 production `ScenarioLoader` loads; and
- summary: 0 errors, 0 warnings, 1 explicit sensorless classification.

The process also emitted 79 already-tracked logger diagnostics that are not
validator warnings: 77 missing commander-profile assignments owned by
REM-023/Phase 112 (38 Korean Peninsula and 39 Taiwan Strait), plus 2
`french_old_guard` skips owned by REM-024/Phase 112. They remain visible and
were not reclassified as green.

The independent full-load boundary also passed:

```text
UV_CACHE_DIR=/tmp/phase110-uv uv run pytest -q --tb=short -o addopts= \
  tests/validation/test_phase_30_scenarios.py::TestScenarioFullLoad
# 51 passed in 23.46s
```

## Scenario evaluation

The predeclared scenarios and seeds were
`space_asat_escalation`, `taiwan_strait`, and `korean_peninsula` at 42, 110,
and 111. Current artifacts are
`/tmp/phase110-final-<scenario>-seed<seed>.json`. The clean phase-start commit
was archived at `/tmp/phase110-baseline-f5a5a2d`; matching baseline artifacts
are `/tmp/phase110-baseline-<scenario>-seed<seed>.json`.

Each current row used:

```text
UV_CACHE_DIR=/tmp/phase110-uv uv run python scripts/evaluate_scenarios.py \
  --scenario <scenario> --seed <seed> --no-details \
  --output /tmp/phase110-final-<scenario>-seed<seed>.json
```

All nine current runs and all nine phase-start runs exited 0 with
`success=true`, empty error/issue fields, and no stall.

| Scenario | Seed | Phase-start -> final tuple | Classification |
|---|---:|---|---|
| ASAT escalation | 42 | draw/time-expired; 32 ticks, 43,595 s, 8 casualties, 52 engagements, 16 moved/0 stuck -> 12, 43,200 s, 8, 74, 12/4 | Expected contract change |
| ASAT escalation | 110 | draw/time-expired; 33, 43,600 s, 8, 55, 16/0 -> 12, 43,200 s, 8, 58, 12/4 | Expected contract change |
| ASAT escalation | 111 | draw/time-expired; 34, 43,605 s, 8, 59, 16/0 -> 12, 43,200 s, 8, 64, 12/4 | Expected contract change |
| Taiwan Strait | 42 | blue/force-destroyed; 8 ticks, 15 casualties, 136 engagements, 14/18 | Semantically unchanged |
| Taiwan Strait | 110 | blue/force-destroyed; 7, 14, 125, 14/18 | Semantically unchanged |
| Taiwan Strait | 111 | blue/force-destroyed; 7, 14, 130, 14/18 | Semantically unchanged |
| Korean Peninsula | 42 | blue/force-destroyed; 144, 16, 89, 20/18; +7 overpass events | Battle outcome unchanged; expected space exposure |
| Korean Peninsula | 110 | blue/force-destroyed; 145, 17, 98, 20/18; +8 overpass events | Battle outcome unchanged; expected space exposure |
| Korean Peninsula | 111 | blue/force-destroyed; 144, 16, 89, 20/18; +7 overpass events | Battle outcome unchanged; expected space exposure |

The ASAT tick/movement/engagement differences follow the declared
3,600-second resolution migration and real space action; they are not
presented as historical improvement. Taiwan is semantically identical after
excluding path/wall time. Korean battle fields are identical; only the
7/8/7 selected-constellation `SatelliteOverpassEvent`s are new. Each Korean
invocation emits the same 38 REM-023 profile diagnostics (16 blue, 22 red).

The real loader/two-tick enabled/disabled probe at all three seeds additionally
proved:

- no action on tick one;
- tick-two event order
  `ConstellationDegradedEvent -> ASATEngagementEvent`;
- exact asset/weapon/target
  `red_nudol_1` / `nudol_asat` / `keyhole_optical_p0_s0`;
- Pk `0.9996645373720975`, hits at all three seeds, active count 4 to 3,
  inventory 1 to 0, and pending to completed;
- debris counts 488, 510, and 493; and
- disabled controls with zero ASAT events, active target/count 4, round 1,
  pending order, empty completion history, and byte-identical SPACE RNG.

`$evaluate-scenarios` is **APPROVED**. These rows are software regression
evidence, not ASAT calibration, backtest, or real-world effectiveness evidence.

## Broader verification

Final-code commands and results:

```text
UV_CACHE_DIR=/tmp/phase110-uv uv run pytest -q --tb=short -o addopts= \
  tests/unit/test_phase_110_space_data.py \
  tests/unit/test_phase_110_asat_runtime.py \
  tests/integration/test_phase_110_asat_production.py \
  tests/integration/test_phase_110_asat_checkpoint.py
# 49 passed in 15.77s

UV_CACHE_DIR=/tmp/phase110-uv uv run pytest -q --tb=short -o addopts= \
  tests/unit/test_phase_17a_orbits_constellations.py \
  tests/unit/test_phase_17b_gps.py \
  tests/unit/test_phase_17c_isr_ew.py \
  tests/unit/test_phase_17d_satcom_asat.py \
  tests/unit/test_phase_17e_integration.py \
  tests/unit/test_phase_17f_validation.py \
  tests/unit/test_phase_25a_scenario_wiring.py \
  tests/unit/test_phase54_era_wiring.py \
  tests/unit/test_phase_65_infra.py \
  tests/unit/test_phase_65_structural.py \
  tests/unit/test_phase_65a_space_isr_ew.py \
  tests/unit/test_phase_65b_asat_sigint.py \
  tests/unit/test_phase_65c_eccm.py \
  tests/unit/test_phase_107_era_gates.py \
  tests/unit/test_phase_107_scenario_wiring.py \
  tests/unit/test_phase_110_space_data.py \
  tests/unit/test_phase_110_asat_runtime.py \
  tests/integration/test_phase_110_asat_production.py \
  tests/integration/test_phase_110_asat_checkpoint.py
# 458 passed in 54.17s

UV_CACHE_DIR=/tmp/phase110-uv uv run python -m pytest --tb=short -q
# 10,804 passed, 21 skipped, 348 deselected, 6 warnings in 296.73s

UV_CACHE_DIR=/tmp/phase110-uv uv run python -m pytest tests/api \
  -q --tb=short -o addopts=
# 202 passed in 24.29s

UV_CACHE_DIR=/tmp/phase110-uv uv run python -m pytest tests/e2e \
  -q --tb=short -o addopts=
# 41 passed in 24.39s

UV_CACHE_DIR=/tmp/phase110-uv uv run ruff check \
  stochastic_warfare/ api/ tests/ scripts/
# All checks passed

UV_CACHE_DIR=/tmp/phase110-uv uv run python -m compileall -q \
  stochastic_warfare api scripts tests
# exit 0; no output

UV_CACHE_DIR=/tmp/phase110-uv uv run --extra docs mkdocs build --strict
# exit 0; documentation built in 2.50s

git diff --check
# exit 0; no output
```

The six default-suite warnings are unrelated and unchanged: one empty-chart
Matplotlib legend warning, four unrendered-animation warnings, and one
`datetime.utcnow()` deprecation warning in the Phase 64 planning process. The
21 runtime skips and 348 marker deselections are reported, not called passes.
The default configuration excludes API, E2E, slow, benchmark, and terrain
markers and ignores the API/E2E directories; API and E2E were therefore run
explicitly.

The focused API test hung inside the filesystem/network sandbox along with an
unrelated API health test because the shared FastAPI/aiosqlite lifespan did not
exit. It was interrupted with Ctrl-C (exit 130, no test result) and is not
counted. The identical focused test passed outside that sandbox in 0.80s, and
the complete outside-sandbox API suite passed as recorded above.

Slow, benchmark, and terrain suites are not applicable: Phase 110 changes no
slow-model contract, performance acceptance criterion, terrain behavior, or
optional terrain dependency. Frontend tests/lint/build were not rerun because
the generic API event/config payload remains dynamically rendered and no
frontend code or client type changed; the last verified Phase 108 frontend
baseline remains 418 tests. There is no manual validation presented as
automated evidence.

The strict MkDocs run retains the upstream Material/MkDocs 2.0 compatibility
banner, three intentional scenario-template pages omitted from navigation, and
seven historical devlog fragment diagnostics assigned to REM-022. None is a
new Phase 110 broken link or strict-build failure.

The owner's reported remote Python lint failure was checked at both phase start
and closure. Repository-wide Ruff is clean, including `scripts/`.

## Documentation and closure gates

`$update-docs` synchronized the implementation contract, Block 12 roadmap,
remediation backlog, architecture, project structure, scenario guide, API
reference, devlog index, public status pages, provider context, and MkDocs
navigation. REM-027 records the one new low-priority legacy ISR state deficit.

`$cross-doc-audit` returned **PASS - ready for `$postmortem`** after correcting:

- the obsolete `gps_constellation` guide example to the strict
  `constellation_ids` schema;
- Taiwan Strait and Korean Peninsula guide durations from 72/48 hours to
  their authored 24/96 hours;
- a stale event filename description and a false guaranteed-cascade scenario
  description;
- the explicit Phase 110 pending status and REM-027 assignment/reason; and
- the public Phase 110 count to 50 tests: 49 focused non-API tests plus the
  production API test.

The auditor's fresh latest-tree checks reported 49 focused tests passing in
16.33 seconds, the complete data validator at 184 unit files, 442/442 mapping
coverage, 9 constellation definitions, 3 ASAT weapon definitions, 51 scenario
loads, 0 errors, and 0 validator warnings, plus green repository Ruff, strict
MkDocs in 2.59 seconds, and `git diff --check`. The final post-transition
coordinating Ruff check also passed, and strict MkDocs exited 0 in 2.53 seconds
with only the already recorded upstream banner, three intentional navigation
omissions, and seven REM-022 historical fragment diagnostics.

## Postmortem

`$postmortem` returned **ACCEPT** after an independent final production/test
diff review.

| Dimension | Verdict |
|---|---|
| Scope | On target; every REM-011 requirement was delivered, no planned item was dropped or deferred, and no Phase 111 work entered the diff |
| Quality | High; no stub, proxy, log-only handler, direct-fire bypass, silent unsupported fallback, nondeterministic ordering, or incomplete ASAT state boundary remains |
| Integration | Fully proven across declared, loaded, wired, enabled/disabled, exercised, outcome-affecting, and persisted/exposed stages |
| New deficits | REM-027 (P2) records the legacy generic ISR buffered-report checkpoint boundary for Phase 112; it is independent of REM-011 |
| Validation | Required focused, relevant regression, default, API, E2E, scenario-load/evaluation, data, Ruff, compile, determinism, convention, simplification, documentation, and cross-document gates passed with exact warnings and exclusions disclosed above |
| Action items | None before closure; REM-020/021 remain explicit logistics follow-ups, and REM-022/023/024/025/026/027 remain assigned to Phase 112 |

The independent postmortem reran the 49 non-API Phase 110 tests
(49 passed in 15.69 seconds), repository Ruff (all checks passed), strict space
catalog validation (9 constellations, 3 weapons, 0 errors, 0 warnings),
`py_compile`, and `git diff --check`. It accepted the coordinating broader
evidence of 10,804 default tests, 202 API tests, 41 E2E tests, 458 relevant
regressions, and 51 production scenario loads.

The implementation added the strict duration and orbital numerical guards,
GPS/SATCOM semantic restore validation, and adversarial ASAT history checks
needed to make the declared production/checkpoint contract safe; these are
in-scope integrity defenses, not unrelated capabilities. Accepted non-goals
remain non-kinetic/co-orbital ASAT, autonomous targeting, tactical launcher or
Class V ownership, historical calibration/backtesting, and high-fidelity
debris modeling.

Phase 110 is complete and REM-011 is closed. Phase 111 was not started before
this status transition.
