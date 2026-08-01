# Phase 114 - Era Override Execution

**Status:** Complete

**Started:** 2026-08-01

**Completed:** 2026-08-01

## Why this phase exists

REM-018 records executable-looking `physics_overrides` and
`tick_resolution_overrides` whose values are persisted but do not construct
the production clock or intended domain engines. Phase 114 replaces those
arbitrary dictionaries with the accepted typed contract in
[`era-override-execution.md`](../specs/era-override-execution.md), applies only
values with behavioral production proof, and rejects the rest explicitly.

## Start gate

Phase 113 passed `$postmortem`, was committed and pushed as
`4c660d1f5c31eb21a7c920af24a8647a7024d6e2`, and completed every requested
hosted workflow before Phase 114 production implementation began. Hosted
evidence for that exact commit includes:

- repository-wide Python Ruff: `All checks passed!`;
- standard: 11,367 passed, zero failures/errors/skips and six classified
  warnings in 1,044.80 seconds, including the default-policy FastMCP node;
- API: 241 passed with zero warnings/skips in 243.37 seconds;
- E2E: 41 passed with zero warnings/skips in 116.49 seconds;
- exact pairwise-disjoint 11,824-node six-partition union;
- frontend: 440 passed across 83 files;
- strict documentation, Docker, and 73 Easting paired gates: passed.

The Phase 114 synchronized start state was:

```text
git status --short --branch
# ## main...origin/main

git rev-parse HEAD
git rev-parse origin/main
# 4c660d1f5c31eb21a7c920af24a8647a7024d6e2
# 4c660d1f5c31eb21a7c920af24a8647a7024d6e2
```

`CODEX.md`, `AGENTS.md`, Block 12, REM-018, the Phase 113 closure evidence,
the current era reference, clock/engine/checkpoint architecture, production
runtime factory, scenario loader, legacy override tests, and `$spec` and
`$design-review` instructions were read before implementation.

## Machine envelope

```text
nproc
# 32

lscpu | sed -n '1,22p'
# Model name: AMD RYZEN AI MAX+ 395 w/ Radeon 8060S
# 1 socket, 16 physical cores, 2 threads per core, 32 online logical CPUs

free -h
# Mem: 62 GiB total, 8.6 GiB used, 27 GiB free, 53 GiB available
# Swap: 7.8 GiB total, 6.0 MiB used
```

The available envelope is safe for independent partition commands. Pytest
processes remain serial because the repository does not carry a validated
xdist runner; broad verification may run the repository's disjoint partition
processes concurrently without weakening exact accounting.

## Specification and design gate

`$spec` traced the authoritative
`SimulationRuntimeFactory -> PreparedScenario.build -> ScenarioLoader ->
SimulationEngine` path and established one frozen effective
`EraRuntimeContract` resolved before RNG/clock construction. The contract
owns the selected registry identity, three effective tick durations, three
medical treatment durations, and maintenance repair duration. Format 114 must
persist and compare it before mutation.

The trace rejected the tempting broad implementation:

- `c2_delay_multiplier` has no production communications catalog/unit
  topology; battle catches the resulting propagation failure;
- scheduled CBRN nuclear declarations have no production consumer, while a
  nuclear sub-engine is always constructed for an enabled CBRN suite;
- the shipped historical physics values have no traceable military source;
- the current medical reader ignores the explicitly supplied `era_config`;
- `repair_time_hours` is routed into `EngineeringConfig`, which has no such
  field, instead of `MaintenanceConfig`; and
- maintenance currently advances in both `CampaignManager` and
  `SimulationEngine` on strategic ticks.

The accepted contract therefore supports only the three medical duration
keys, maintenance repair duration, and the three tick-resolution keys. Shipped
presets will omit the unsourced physics numbers. C2/nuclear keys are explicit
validation errors until their missing production prerequisites are completed
under numbered follow-ups. Medical and maintenance proofs use public setup on
a loader-created runtime followed only by `SimulationEngine.step()`; they do
not claim automatic casualty admission, facility construction, equipment
registration, or spare-parts repair initiation.

The design also freezes the isolated era config and effective contract in each
prepared factory variant, includes both in `config_fingerprint`, injects them
into the lower loader, and makes the all-resolution `SimulationEngine` cadence
the sole maintenance update owner. This prevents later custom-registry
replacement and strategic double advancement from invalidating the claimed
behavior.

The independent adversarial `$design-review` verdict was **NEEDS REVISION**.
It found four blocking gaps in the provisional contract: scenario config
revalidation still consulted the mutable registry after preparation; the tick
loop advanced with the old cadence and then executed work under a newly named
resolution; mutable clock/medical/maintenance consumers could diverge from a
frozen checkpoint contract; and lower-loader-only behavior was weaker than the
authoritative factory-to-session production path.

The specification was revised to require syntax-only era identity validation,
registry resolution at exactly the factory-preparation and direct-loader
boundaries, one pre-bound resolution and `dt` per complete interval,
nonreplaceable captured identities with frozen consumer configs and drift
checks, and behavioral acceptance through
`SimulationRuntimeFactory -> PreparedScenario.build -> RuntimeSession.step`.
It also clarifies exactly-once maintenance as a deliberate state/RNG correction,
endpoint-quantized completion, engine-owned checkpoint resolution checks, and
active treatment/repair continuation evidence.

The adversarial re-review verdict is **APPROVED WITH NOTES**. It confirmed that
all four contract blockers and every requested clarification are resolved.
Implementation review must still prove semantic snapshot equivalence for
mutable nested era sets, source defaults from their actual simulation-layer
owners, and retain the honest lifecycle/C2/CBRN non-goals. This is design-only
approval, not Phase 114 completion evidence.

## Baseline and production red evidence

The unchanged focused baseline passed before any production implementation:

```text
UV_CACHE_DIR=/tmp/sw-phase114-uv-cache uv run --no-sync pytest -q \
  tests/unit/test_phase_20a_era_framework.py \
  tests/unit/test_phase56_performance_logistics.py \
  tests/unit/test_phase_107_era_gates.py
# 115 passed in 7.09s
```

This green baseline is not REM-018 evidence. Existing tests accept arbitrary
`max_mach` metadata or inspect preset dictionaries, while a production load
with declared tick, treatment, and repair values retains the default clock and
engine behavior.

The accepted production red suite then produced 15 failures and one incidental
pass:

```text
UV_CACHE_DIR=/tmp/sw-phase114-uv-cache uv run --no-sync pytest -q \
  tests/integration/test_phase114_era_override_execution.py
# 15 failed, 1 passed in 1.46s
```

The failures prove:

- all seven sampled unknown, unsupported, non-strict, nonpositive, and NaN
  physics declarations were accepted;
- five of six invalid tick declarations were accepted (the current
  `dict[str, float]` happened to reject explicit `None` structurally);
- a declared 17-second tactical override advanced the production clock by the
  authored five seconds;
- a declared one-hour minor-treatment override retained the two-hour default,
  leaving the casualty in treatment after the second one-hour engine step;
  and
- the checkpoint remained version 113 with no effective runtime contract.

The red proof uses a loader-created context and real `SimulationEngine.step()`;
it does not substitute config-field inspection for the two behavioral
failures.

## Implementation

Phase 114 now resolves one strict effective contract before any runtime RNG,
clock, terrain, force, or domain engine exists. The production changes are:

- `EraPhysicsOverrides` and `EraTickResolutionOverrides` are frozen Pydantic
  models with `extra="forbid"`, strict finite positive floats, exact
  microsecond cadence representation, and explicit rejection of the former
  C2/nuclear keys. Registry writes revalidate and isolate caller-owned input.
- `EraRuntimeContract`, `EraRuntimeSource`, and
  `EraExecutionHorizonSource` materialize the effective destination defaults,
  sparse era overlays, exact authored cadence inputs, selected registry
  identity, and executable calendar horizon. `SimulationRuntimeFactory`
  captures the isolated era config and contract per prepared variant before
  source/data/runtime construction, and includes both in the exposed config
  fingerprint. Direct `ScenarioLoader` use resolves the same contract at its
  lower production boundary before constructing `RNGManager`.
- `PreparedScenario.build()` revalidates captured inputs without consulting
  the mutable registry and injects the captured era config and contract into
  the loader. Replacing a custom registry entry after preparation cannot
  change a repeated build; a new preparation observes the replacement.
- `SimulationClock`, `SimulationEngine`, `MedicalEngine`,
  `MaintenanceEngine`, `RuntimeLoadoutBuilder`, and API frame-interval
  selection consume the same typed contract. Medical and maintenance configs
  are frozen before engine construction. `repair_time_hours` no longer passes
  through the unrelated engineering config.
- `SimulationEngine` selects one resolution and `dt` before each interval and
  binds that cadence to the clock, managers, subsystems, events, and
  checkpoint. Work discovered inside an interval may select the next interval
  but cannot relabel the completed one. The engine is now the sole
  maintenance-update owner at strategic, operational, and tactical cadence;
  the former campaign duplicate was removed.
- The context captures immutable era/config/cadence/horizon identities and
  checks exact medical, maintenance, loadout, clock, and engine agreement
  before each step and state operation. The checks reject drift rather than
  silently rebuilding from mutable metadata.
- Engine checkpoint format `114` persists exactly one effective
  `era_runtime_contract`. Restore stages the strict contract and the current
  resolution/clock agreement before any owner commits. Format 113 rejects;
  versionless compatibility is bounded to an override-free target and cannot
  infer declared era behavior. Active non-default treatment and repair state
  continues exactly through fresh and in-place restore.
- The built-in era presets retain capability gates and sensor policies but
  omit their unsourced historical physics numbers. No replacement historical
  value was invented.

The implementation also repaired legacy tests that manually assembled
contexts with impossible clock/config pairings or no era boundary. Those
fixtures now supply a real typed contract or align their real clock to their
authored scenario; production did not gain a permissive fallback for test
doubles.

### Atomic interval correction found by broad validation

The first standard shard-4 attempt exposed a genuine production atomicity
defect in
`test_non_strict_master_loop_propagates_malformed_real_target_immediately`.
A malformed non-finite Space ISR target could influence resolution selection
before `SpaceEngine.preflight_update()` rejected it, so a failed public step
changed the checkpoint's resolution from operational to strategic.

The repair separates mutation-free `_select_resolution()` from
`_set_resolution()`. `step()` stages the next resolution and prospective
contract `dt`, gives that value to Space preflight, and commits the resolution
and clock duration only after preflight succeeds. The original byte-identical
checkpoint assertion was retained; no stale expected state was normalized.
Valid intervals retain the accepted next-interval transition semantics.

## Focused verification

The final Phase 114 production selection contains 94 collected tests: 93
non-API integration/clock tests and one API behavior proof.

```text
PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase114-uv-cache \
uv run --no-sync pytest -q \
  tests/integration/test_phase114_era_override_execution.py \
  tests/integration/test_phase114_factory_runtime_behavior.py \
  tests/integration/test_phase114_checkpoint_and_transitions.py \
  tests/unit/test_clock.py
# 93 passed in 54.21s
```

The tests prove strict declarations and failure cases, registry isolation,
pre-RNG calendar-horizon rejection, sparse overlay/default behavior, natural
strategic/operational/tactical cadence, next-interval transitions, all three
medical severities, exactly-once maintenance and repair completion, prepared
registry isolation and fingerprints, exact format-114 topology, bounded
versionless behavior, active treatment/repair restoration, and atomic corrupt
checkpoint rejection.

The final API proof ran on the host because the sandbox's current async SQLite
thread wakeup is defective:

```text
PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase114-uv-cache \
uv run --no-sync pytest -q tests/api/test_phase114_era_runtime_api.py
# 1 passed in 4.98s
```

Two behaviorally identical inline configs differ only by their captured custom
era. A one-second strategic contract completes after five ticks and emits
frames at ticks 2, 4, and 5; a two-second contract completes after three ticks
and emits frames at ticks 1, 2, and 3. Their exposed config fingerprints
differ. The proof uses `RunManager -> SimulationRuntimeFactory ->
PreparedScenario -> RuntimeSession`, real background execution, SQLite
persistence, result JSON, and frames JSON.

The post-atomicity review reran the complete three-module integration proof and
the exact malformed-Space-target node:

```text
PYTHONDONTWRITEBYTECODE=1 \
UV_CACHE_DIR=/tmp/sw-phase114-integrity-uv-cache \
uv run --no-sync pytest -q \
  tests/integration/test_phase114_checkpoint_and_transitions.py \
  tests/integration/test_phase114_era_override_execution.py \
  tests/integration/test_phase114_factory_runtime_behavior.py \
  tests/integration/test_phase112_space_isr_integrity.py::test_non_strict_master_loop_propagates_malformed_real_target_immediately
# 77 passed in 58.34s
```

No focused run had a skip or warning.

## Conditional reviews

### `$design-review`

The provisional design's initial **NEEDS REVISION** and corrected **APPROVED
WITH NOTES** verdicts are recorded under the specification gate above. The
implemented tree preserves all four corrected obligations. No unsourced
military parameter or new stochastic model was introduced, so
`$research-military` and `$research-models` are N/A.

### `$audit-determinism`

Final verdict: **DETERMINISTIC**. The final review found no new RNG owner,
module-level draw, Python `random`, wall-clock simulation input, unordered
outcome iteration, or checkpoint RNG mirror. Era resolution fails before
`RNGManager` construction. One staged cadence and `dt` govern each interval,
and format-114 restore validates all owners before mutation.

```text
uv run --no-sync pytest -q tests/unit/test_rng.py
# 10 passed in 0.21s

# Explicit isolation probe after 10,000 LOGISTICS draws:
# logistics_draws=10000
# non_logistics_streams_unchanged=15
# total_non_logistics=15
```

Maintenance's deliberate exactly-once correction changes later draws within
the shared LOGISTICS stream relative to Phase 113. All other 15 streams remain
isolated, and same-tree replay/continuation is exact; cross-revision trajectory
identity is not claimed.

### `$validate-conventions`

Final verdict: **PASS**. The changed runtime boundary is typed, clock and
timestamps remain UTC logical time, coordinates remain ENU, configs and the
contract are frozen, state ownership is not duplicated, and logging uses the
repository logger. Changed-production Ruff and `git diff --check` pass. API
`datetime.now()` calls remain run-management metadata, not simulation time.

### `$validate-data`

No YAML catalog value changed, but era schema and loader behavior make the
full data route applicable. The validator completed with zero errors and zero
warnings:

```text
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase114-uv-cache \
  uv run --no-sync python scripts/validate_scenario_data.py
# 184 unit YAML definitions; all 5 eras; 442/442 mapping coverage;
# 52 scenario YAML files loaded; 8,388/8,388 initial instances;
# 70 groups -> 1,128 units and 1,131/1,131 field applications;
# 0 errors, 0 warnings, 1 explicit sensorless classification; exit 0

env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase114-uv-cache \
  uv run --no-sync pytest \
  tests/validation/test_phase_30_scenarios.py::TestScenarioFullLoad \
  -q --tb=short -o addopts=
# 52 passed in 53.23s
```

- 184 unit YAML definitions;
- all five built-in eras;
- 442/442 equipment mappings;
- 52 scenarios;
- 8,388/8,388 initial-unit instances;
- 70 reachable unit groups, expanding to 1,128 units and 1,131 equipment
  fields; and
- one explicitly `intentionally_none` civilian sensor policy.

The production full-load selection passed 52/52. No catalog mapping, sensor,
or historical physics value was invented to satisfy the gate.

### `$evaluate-scenarios`

The final post-atomic seed-42 production replay discovered all 46 scenarios:

```text
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase114-uv-cache \
uv run --no-sync python scripts/evaluate_scenarios.py \
  --output /tmp/sw-phase114-post-atomic-scenarios.4CKdGR/all-seed42.json \
  --no-details --seed 42
# 46 discovered; 44 OK; 2 classified warnings
```

The only warnings are unchanged and explicitly classified:

- `space_isr_gap`: `ZERO_ENGAGEMENTS`, `NO_MOVEMENT`;
- `time_on_target_validation`: `NO_MOVEMENT`.

The artifact raw SHA-256 is
`5041b2b0debae3bfbb5746c89eebf54f42b4ba016d80ddeef229c228bb6ed05f`.
After removing only wall duration and absolute scenario path, its canonical
semantic SHA-256 is
`6c9d09dd07dcd99b35109bf262d35f38a240102aa8966079c772d7944b536480`,
byte-equivalent to the accepted post-implementation candidate.

Thirty-one rows are semantically unchanged from Phase 113. Twelve rows have
the expected one-boundary cadence correction: `cbrn_chemical_defense`,
`cbrn_nuclear_tactical`, `coin_campaign`, `falklands_campaign`,
`falklands_naval`, `halabja_1988`, `hybrid_gray_zone`, `kursk`, `midway`,
`somme_july1`, `space_gps_denial`, and `srebrenica_1995`. Three rows have
deterministic downstream cascades and were replayed at seeds 42--44:

```text
# Jutland seeds 43 and 44
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase114-uv-cache \
  uv run --no-sync python scripts/evaluate_scenarios.py --scenario jutland \
  --output /tmp/sw-phase114-post-atomic-scenarios.4CKdGR/jutland-seed43.json \
  --no-details --seed 43
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase114-uv-cache \
  uv run --no-sync python scripts/evaluate_scenarios.py --scenario jutland \
  --output /tmp/sw-phase114-post-atomic-scenarios.4CKdGR/jutland-seed44.json \
  --no-details --seed 44

# Khafji seeds 43 and 44; these ran strictly sequentially
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase114-uv-cache \
  uv run --no-sync python scripts/evaluate_scenarios.py --scenario khafji \
  --output /tmp/sw-phase114-post-atomic-scenarios.4CKdGR/khafji-seed43.json \
  --no-details --seed 43
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase114-uv-cache \
  uv run --no-sync python scripts/evaluate_scenarios.py --scenario khafji \
  --output /tmp/sw-phase114-post-atomic-scenarios.4CKdGR/khafji-seed44.json \
  --no-details --seed 44

# Taiwan Strait seeds 43 and 44
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase114-uv-cache \
  uv run --no-sync python scripts/evaluate_scenarios.py \
  --scenario taiwan_strait \
  --output /tmp/sw-phase114-post-atomic-scenarios.4CKdGR/taiwan-strait-seed43.json \
  --no-details --seed 43
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase114-uv-cache \
  uv run --no-sync python scripts/evaluate_scenarios.py \
  --scenario taiwan_strait \
  --output /tmp/sw-phase114-post-atomic-scenarios.4CKdGR/taiwan-strait-seed44.json \
  --no-details --seed 44
```

The seed-42 rows came from the full-catalog command above; no redundant
focused seed-42 command is claimed.

| Scenario | Seed | Phase 113 ticks/casualties | Phase 114 ticks/casualties | Phase 114 terminal |
| --- | ---: | ---: | ---: | --- |
| Jutland | 42 | 373 / 21 | 569 / 10 | British / `force_destroyed` |
| Jutland | 43 | 397 / 21 | 437 / 6 | British / `force_destroyed` |
| Jutland | 44 | 469 / 24 | 713 / 8 | British / `force_destroyed` |
| Khafji | 42 | 721 / 90 | 728 / 77 | Blue / `force_destroyed` |
| Khafji | 43 | 683 / 78 | 668 / 79 | Blue / `force_destroyed` |
| Khafji | 44 | 676 / 60 | 680 / 60 | Blue / `force_destroyed` |
| Taiwan Strait | 42 | 8 / 15 | 61 / 15 | Blue / `force_destroyed` |
| Taiwan Strait | 43 | 7 / 14 | 61 / 17 | Blue / `force_destroyed` |
| Taiwan Strait | 44 | 8 / 14 | 157 / 21 | Blue / `force_destroyed` |

All nine final-tree multiseed rows exactly match the accepted candidate. Their
Phase 114 engagement counts are Jutland 15/14/16, Khafji 526/529/576, and
Taiwan Strait 183/274/221 for seeds 42/43/44. Every issues array is empty.
Khafji seeds 42--44 ran strictly sequentially, while all focused scenario
execution stayed at or below two concurrent processes. The six evaluator
exclusions are `benchmark_battalion`, `benchmark_brigade`, `test_campaign`,
`test_campaign_logistics`, `test_campaign_multi`, and
`test_campaign_reinforce`; they are benchmark/test fixtures, not omitted
catalog scenarios. These results are current-engine regression observations,
not historical validation or calibration authority. Jutland also supplies
additional evidence for the blind standoff deficit retained by REM-028; Phase
114 does not repair it.

### `$profile`

The wall-clock evidence is accepted for Phase 114 only as an explicit
**contention-qualified owner exception**. All three attempts were correctly
classified **inconclusive** because the unrelated elevated-priority training
workload produced dispersion far above the declared 20% ceiling. Their raw
artifacts are preserved and are not relabeled as clean performance passes.

The post-atomic attempt first sampled CPU 30 and its SMT sibling 14 at 80.9%
and 80.7% idle, with no training worker resident there and 45 GiB memory
available. Host-wide contention still invalidated the paired timings:

```text
taskset -c 30 env PYTHONDONTWRITEBYTECODE=1 \
UV_CACHE_DIR=/tmp/sw-phase114-profile-uv-cache \
uv run --no-sync python scripts/run_paired_benchmark.py \
  --repo-root /home/csmith/projects/stochastic-warfare \
  --scenario 73_easting \
  --artifact /tmp/sw-phase114-profile.DPZUBa/paired-73-easting-post-atomic-final.json \
  --allow-dirty-candidate --worker-timeout-seconds 900
# exit 1 / INCONCLUSIVE: dispersion exceeds 0.20
# pair ratios: 1.067443, 2.314121, 1.247470; median 1.247470
# relative ranges: reference 1.081806; candidate 0.664903
# file SHA-256:
# 12507b5d8026cc54c127f7f7432562560897ec50a6a11171c7b05382f68ef25a
```

All eight warmup/measured executions had the same workload fingerprint,
360-tick/1,800-second terminal envelope, winner/condition, 71-unit status
topology, event count/digest, and loadout digest. The first two attempts had
40.1% and 59.4% candidate dispersion; the third had 108.2% reference and 66.5%
candidate dispersion. None is a timing verdict.

An exact Phase-113-versus-current profile diagnosis found identical production
inputs, semantic envelope, and dominant call counts: 360 engine steps, 360
battle ticks, 360 engagement passes, 580,547 primary engagement-generator
iterations, 340,947 weapon-domain checks, 360 movement calls, and 360
maintenance updates. Phase 114 adds 0.992% total calls, chiefly the strict
era-binding checks; those checks consume about 1.45% of profiled engine time.
Unchanged hot functions inflated and deflated together across runs, and both
revisions independently ranged from roughly 2.1 to 4.9 seconds. An alternating
diagnostic produced a median paired ratio of 1.046 while both revisions failed
the dispersion policy. These diagnostics found no evidence of an algorithmic
Phase 114 regression, but they do not constitute a clean wall-clock gate pass.

On 2026-08-01 the owner directed that the unrelated training continue and
accepted this result as qualified closure evidence, with uncontended
confirmation deferred until the owner reports that all cores are free. This
does not weaken the declared 1.20 median-ratio or 0.20 dispersion thresholds,
and Phase 114 makes no uncontended wall-clock-pass claim. The qualification is
bounded by eight semantically identical production runs, exact call-count and
cProfile diagnosis, about 0.992% additional calls, and no identified
algorithmic regression; residual wall-clock uncertainty remains explicit.

The exact candidate profile was:

```text
taskset -c 30 env PYTHONDONTWRITEBYTECODE=1 \
UV_CACHE_DIR=/tmp/sw-phase114-profile-uv-cache \
uv run --no-sync python -m cProfile \
  -o /tmp/sw-phase114-profile.DPZUBa/73-easting.prof \
  scripts/evaluate_scenarios.py --scenario 73_easting --no-details --seed 42
# 29,234,666 calls in 8.662s under contention
# SimulationEngine.run: 5.326s
# era binding: 361 calls / 0.074s cumulative
```

The dominant time remains battle engagement work; no performance-only code
change is justified from the qualified measurements. An uncontended policy
confirmation remains an operational follow-up when the owner supplies a clean
machine window.

## Broader verification

The final partition manifest contains an exact pairwise-disjoint union of
11,903 nodes with zero collection warnings:

| Partition | Result | Warnings/skips |
| --- | ---: | --- |
| standard | 11,445 passed | 6 classified warnings / 0 skips |
| slow-only | 109 passed | 0 / 0 |
| benchmark-only | 62 passed | 0 / 0 |
| slow-benchmark | 4 passed | 0 / 0 |
| API | 242 passed | 0 / 0 |
| E2E | 41 passed | 0 / 0 |
| **Exact union** | **11,903 passed** | **6 / 0** |

The first three accepted frozen standard commands were this exact form, with
`N` and `DIR` resolved by the table:

```text
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase114-uv-cache \
  uv run --no-sync python scripts/run_pytest_partition.py standard \
  --manifest /tmp/sw-phase114-post-atomic-broad/DIR/manifest.json \
  --junit /tmp/sw-phase114-post-atomic-broad/DIR/junit.xml \
  --shard-index N --shard-count 4 --forbid-skips --timeout-seconds 2700
```

| `N` | `DIR` | Selected | Result |
| ---: | --- | ---: | --- |
| 0 | `standard-0-freeze-rerun` | 2,862 | 2,862 passed; 0 warnings |
| 1 | `standard-1-freeze-rerun` | 2,861 | 2,861 passed; 4 warnings |
| 2 | `standard-2-freeze-rerun` | 2,861 | 2,861 passed; 2 warnings |

The fourth standard shard was rerun with this fresh literal command:

```text
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase114-uv-cache \
  uv run --no-sync python scripts/run_pytest_partition.py standard \
  --manifest /tmp/sw-phase114-exact-evidence/standard-3/manifest.json \
  --junit /tmp/sw-phase114-exact-evidence/standard-3/junit.xml \
  --shard-index 3 --shard-count 4 --forbid-skips --timeout-seconds 2700
# 2,861 selected; 2,861 passed in 492.08s; 0 failures/errors/skips/warnings
```

The accepted final-tree standard executions were 2,862 in 232.08 seconds with
no warning, 2,861 in 415.24 seconds with four Matplotlib animation-lifecycle
warnings, 2,861 in 279.94 seconds with one empty-legend warning and one
`datetime.utcnow()` deprecation, and the fresh fourth shard's 2,861 in 492.08
seconds with no warning. Their six pairwise intersections, duplicate set, missing set,
and extra set are all empty. All four manifests record the same 11,445-node
collection SHA-256
`916fdc59837c2d7470349484c0db5930c4fbc92a4196aae2c0954983264e5281`;
the sorted shard union and fresh all-node list both hash to
`e53ed1c4601e72a217ae3b236d675b0336b96b684613153c57b6aff71bdbbae7`.
The fresh fourth selection SHA-256 is
`4bc3f6ec5c7401c57d65e31d77050174c24eecf7453de6577f19ee8663865fe8`,
byte-identical to the retained accepted selection.

Slow-only was rerun in four deterministic module-affine shards with these
literal commands:

```text
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase114-uv-cache \
  uv run --no-sync python scripts/run_pytest_partition.py slow-only \
  --manifest /tmp/sw-phase114-exact-evidence/slow-0/manifest.json \
  --junit /tmp/sw-phase114-exact-evidence/slow-0/junit.xml \
  --shard-index 0 --shard-count 4 --forbid-skips --timeout-seconds 2700

env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase114-uv-cache \
  uv run --no-sync python scripts/run_pytest_partition.py slow-only \
  --manifest /tmp/sw-phase114-exact-evidence/slow-1/manifest.json \
  --junit /tmp/sw-phase114-exact-evidence/slow-1/junit.xml \
  --shard-index 1 --shard-count 4 --forbid-skips --timeout-seconds 2700

env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase114-uv-cache \
  uv run --no-sync python scripts/run_pytest_partition.py slow-only \
  --manifest /tmp/sw-phase114-exact-evidence/slow-2/manifest.json \
  --junit /tmp/sw-phase114-exact-evidence/slow-2/junit.xml \
  --shard-index 2 --shard-count 4 --forbid-skips --timeout-seconds 2700

env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase114-uv-cache \
  uv run --no-sync python scripts/run_pytest_partition.py slow-only \
  --manifest /tmp/sw-phase114-exact-evidence/slow-3/manifest.json \
  --junit /tmp/sw-phase114-exact-evidence/slow-3/junit.xml \
  --shard-index 3 --shard-count 4 --forbid-skips --timeout-seconds 2700
```

The results were 28 in 1,320.279 seconds, 27 in 1,349.949 seconds, 27 in
252.657 seconds, and 27 in 2,290.260 seconds: 109/109 passed, with zero
failures, errors, skips, or warnings. Their raw `selection.args` SHA-256
values are
`dd9e76c8537153ce48500ab57c99e9ddfd277e1192ae2ddbcc61b3639c4837ac`,
`9e2cf1e8fbe0f6bce7ec78b40dfa122db31a3e83091922045b7e6c9d91667cd5`,
`3d4ffe063e4419631402fbf76d4814b874a2efebc3f8b02c832debc34848e664`,
and `a95aa8bd193a9d268a57b33399253ed751354d261140dff5d361b29c6f915787`,
each byte-identical to its retained accepted selection.

Benchmark-only and slow-benchmark were rerun with these literal commands:

```text
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase114-uv-cache \
  uv run --no-sync python scripts/run_pytest_partition.py benchmark-only \
  --manifest /tmp/sw-phase114-exact-evidence/benchmark-0/manifest.json \
  --junit /tmp/sw-phase114-exact-evidence/benchmark-0/junit.xml \
  --shard-index 0 --shard-count 3 --forbid-skips --timeout-seconds 2700

env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase114-uv-cache \
  uv run --no-sync python scripts/run_pytest_partition.py benchmark-only \
  --manifest /tmp/sw-phase114-exact-evidence/benchmark-1/manifest.json \
  --junit /tmp/sw-phase114-exact-evidence/benchmark-1/junit.xml \
  --shard-index 1 --shard-count 3 --forbid-skips --timeout-seconds 2700

env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase114-uv-cache \
  uv run --no-sync python scripts/run_pytest_partition.py benchmark-only \
  --manifest /tmp/sw-phase114-exact-evidence/benchmark-2/manifest.json \
  --junit /tmp/sw-phase114-exact-evidence/benchmark-2/junit.xml \
  --shard-index 2 --shard-count 3 --forbid-skips --timeout-seconds 2700

env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase114-uv-cache \
  uv run --no-sync python scripts/run_pytest_partition.py slow-benchmark \
  --manifest /tmp/sw-phase114-exact-evidence/slow-benchmark/manifest.json \
  --junit /tmp/sw-phase114-exact-evidence/slow-benchmark/junit.xml \
  --forbid-skips --timeout-seconds 2700
```

Benchmark-only passed 52 in 7.192 seconds, seven in 0.990 seconds, and three
in 0.194 seconds. Slow-benchmark passed four in 31.399 seconds. All 66 nodes
passed with zero failures, errors, skips, or warnings, and every fresh
selection is byte-identical to its retained accepted selection.

The accepted final-tree host API command was:

```text
uv run --no-sync python scripts/run_pytest_partition.py api \
  --manifest /tmp/sw-phase114-post-atomic-broad/api/manifest.json \
  --junit /tmp/sw-phase114-post-atomic-broad/api/junit.xml \
  --forbid-skips --timeout-seconds 2700
# collection: 242 selected, 0 deselected, 0 warnings in 0.28s
# execution: 242 passed, 0 failures/errors/skips/warnings in 249.60s
```

E2E was rerun on the host with this literal command:

```text
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase114-uv-cache \
  uv run --no-sync python scripts/run_pytest_partition.py e2e \
  --manifest /tmp/sw-phase114-exact-evidence/e2e/manifest.json \
  --junit /tmp/sw-phase114-exact-evidence/e2e/junit.xml \
  --forbid-skips --timeout-seconds 2700
# 41 selected; 41 passed in 124.520s; 0 failures/errors/skips/warnings
```

An initial identical sandbox command collected 41 nodes in 1.34 seconds and
then reproduced the qualified async/SQLite wakeup stall for about six minutes.
It was cleanly interrupted with exit 130 and rejected; the accepted unchanged
host command collected in 1.48 seconds and exited zero. Its raw
`selection.args` SHA-256
`c82a7d30310918aefaaadfe3e2036aa9731f3de3d1574d5e4504d19ce615abbe`
is byte-identical to the retained accepted selection.

The frozen standard/API acceptance tree had
strict source fingerprint
`155e59eb2c18577917a3e149fa1e80a57e112e7219cd2127bbb513875604ce01`;
its binary diff and status-list hashes remained byte-identical before and
after execution. Earlier final-tree standard attempts that overlapped
documentation writes failed only the strict source-provenance assertion (3,
8, and 1 nodes respectively), with no behavioral mismatch. They are rejected
diagnostics; the frozen reruns above cleared every node without a code change.

The sandbox qualification is explicit. Sandboxed Phase 114 API and generic
database tests stalled before schema creation; `faulthandler` showed the
`aiosqlite` worker idle in `tx.get` while the asyncio loop waited in `epoll`,
consistent with a lost cross-thread sandbox wakeup. Identical host execution
passed immediately. No database or simulation failure was hidden.

Overlapping profiles passed separately and are not double-counted in the
union. They were rerun with the following literal commands:

```text
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase114-uv-cache \
  uv run --no-sync python scripts/run_pytest_partition.py terrain \
  --manifest /tmp/sw-phase114-exact-evidence/terrain/manifest.json \
  --junit /tmp/sw-phase114-exact-evidence/terrain/junit.xml \
  --forbid-skips --timeout-seconds 2700

env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase114-uv-cache \
  uv run --no-sync python scripts/run_pytest_partition.py benchmark-policy \
  --manifest /tmp/sw-phase114-exact-evidence/benchmark-policy/manifest.json \
  --junit /tmp/sw-phase114-exact-evidence/benchmark-policy/junit.xml \
  --forbid-skips --timeout-seconds 2700
```

Terrain passed 97/97 in 6.169 seconds and benchmark policy passed 61/61 in
37.330 seconds, both with zero failures, errors, skips, or warnings. Their
fresh raw selection hashes are byte-identical to the retained accepted
selections.

Repository-wide static and evidence checks are clean:

```text
uv run --no-sync ruff check .
# All checks passed!

uv run --no-sync python -m compileall -q stochastic_warfare api scripts tests
# exit 0, no output

uv run --no-sync python scripts/validate_test_evidence.py
# no-direct 91; reviewed-behavioral 87; structural 917; weak-oracle 1004

uv run --no-sync python scripts/validate_test_partitions.py \
  --output /tmp/sw-phase114-broad/final-partition-audit.json
# 11,903 exact, pairwise-disjoint nodes; zero collection warnings

git diff --check
# clean
```

The reported hosted Python-lint failure was traced and rechecked rather than
assumed resolved:

```text
gh run list --status failure --limit 20
gh run view 30421215404 --log-failed
# Phase 108 Lint: six F601 duplicate mapping keys and two F541 test strings

gh run list --branch main --limit 8
# latest Phase 113 hosted Lint run 30703361766: success

env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase114-uv-cache \
  uv run --no-sync ruff check stochastic_warfare/ api/ tests/ scripts/
# All checks passed!
```

Phase 109 removed the duplicate mappings and later phases removed the two
extraneous f-string prefixes. The current command exactly matches the hosted
Python Ruff scope; no lint suppression or exclusion was added.

Fresh exact frontend commands also passed:

```text
# working directory: /home/csmith/projects/stochastic-warfare/frontend
npm test
# 83 files / 440 tests passed in 5.98s; exit 0

npm run lint
# 0 errors, 4 warnings; exit 0

npm run build
# 420 modules transformed; built in 59.83s; exit 0
```

Diagnostics were existing React Router future flags, React `act(...)`, jsdom
navigation, four hook/lint warnings, stale Browserslist data, and a
greater-than-500 kB chunk warning. They are not Python or Phase 114 failures.

## Simplification review

`$simplify` verdict: **CLEAN**. The review found no duplicate runtime owner,
avoidable proxy, dead path, or test-only production fallback. The O(1) contract
merge belongs at construction. Per-step drift validation is measurable but
small, and replacing it with cached primitive identities before the final
uncontended gate would trade correctness for an expected one-to-two-percent
ceiling. No simplification edit was justified.

The final read-only adversarial implementation review found no production,
behavioral-evidence, checkpoint, ownership, proxy, stub, or lifecycle blocker.
It found one stale module claim in `c2/courier.py`; the docstring now states
the verified boundary: the courier component exists, but production
communications topology does not yet route orders through it. REM-036 remains
the owner of that follow-up. The documentation-only correction passed:

```text
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase114-uv-cache \
  uv run --no-sync pytest -q --tb=short -o addopts= \
  tests/unit/test_phase_22b_engine_extensions.py \
  tests/unit/test_phase54_era_wiring.py \
  tests/unit/test_phase_21a_era_config_data.py \
  tests/unit/test_phase_22a_era_config_data.py \
  tests/unit/test_phase_23a_era_config_data.py \
  tests/validation/test_phase_22c_napoleonic_validation.py \
  tests/integration/test_phase114_era_override_execution.py
# 575 passed in 56.68s; 0 failures/errors/skips/warnings

env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase114-uv-cache \
  uv run --no-sync ruff check stochastic_warfare/ api/ tests/ scripts/
# All checks passed!

env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase114-uv-cache \
  uv run --no-sync python -m compileall -q stochastic_warfare api scripts tests
# exit 0, no output
```

## Documentation and cross-document audit

`$update-docs` completed its pre-status pass across the runtime, era,
checkpoint, API, scenario, phase, remediation, and historical claims. The
older Phase 20--23 and Phase 56 records remain intact with explicit
supersession notices; REM-035 through REM-040 are assigned to Phases 122
through 127 rather than hidden inside REM-018.

The final pre-status `$cross-doc-audit` independently returned **PASS** in all
ten required areas: roadmap/devlog alignment, remediation traceability,
contract accuracy, production evidence, architecture accuracy, API accuracy,
data/catalog accuracy, public status accuracy, navigation/links, and
provider-context alignment. It also matched every fresh literal partition
command to its manifest/JUnit result and verified that selections are
byte-identical to the retained exact-union evidence. Its two non-blocking
wording notes were corrected from “5 historical eras” to the accurate five
eras—one modern plus four historical. The later owner-approved performance
qualification is recorded above without changing the audit's clean-timing
interpretation. At that pre-status gate, Phase 114 and REM-018 remained open
for `$postmortem` and the explicit status transition completed below.

```text
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase114-uv-cache \
  uv run --extra docs mkdocs build --strict \
  --site-dir /tmp/sw-phase114-cross-doc-audit-final
# exit 0; independently built in 8.29s; three intentionally unnavigated scenario templates;
# one informational Material-for-MkDocs/MkDocs-2 compatibility banner

env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase114-uv-cache \
  uv run --no-sync python scripts/validate_docs_links.py
# valid fixture exit 0; invalid fixture exit 1 with a diagnostic; command exit 0

git diff --check
# clean
```

A coordinator rerun after the two cosmetic corrections used the same MkDocs
command with `--site-dir /tmp/sw-phase114-docs-site-final-crossdoc` and also
passed in 5.77 seconds; link validation, hosted-scope Ruff, and
`git diff --check` remained clean.

After the owner-approved performance qualification was recorded, the exact
strict command was rerun with
`--site-dir /tmp/sw-phase114-docs-site-owner-qualified` and passed in 5.65
seconds with the same three intentional navigation omissions and informational
banner. Link validation, hosted-scope Ruff, and `git diff --check` again passed.

The pre-status documentation and `$cross-doc-audit` gates pass. `$postmortem`
below also passes; the audited explicit transition marks Phase 114 complete
and REM-018 closed.

## Remaining deficits and exclusions

Phase 114 intentionally does not claim automatic casualty admission, medical
facility topology, equipment maintenance registration, repair/spares
initiation, production communications topology, scheduled nuclear action, or
validation-runner era propagation. These are assigned to REM-036 through
REM-040. The resolution review also records REM-035 for the battle-topology
precondition on certain unit-level production proofs.

REM-016, REM-020, REM-021, and REM-028 through REM-040 remain outside Phase
114. REM-028 owns sensing-aware standoff; REM-030 owns source-backed historical
validation. The two evaluator warnings above remain classified, not hidden.

## Postmortem

`$postmortem` verdict: **PASS**, with the owner-approved performance
qualification preserved exactly as recorded above. The subsequent explicit
status transition marks Phase 114 **Complete**, REM-018 **Closed**, and Block
12 **Complete**.

| Dimension | Verdict |
| --- | --- |
| Scope | **On target.** The phase replaces arbitrary dead metadata with strict typed declarations, resolves one effective contract before RNG/runtime construction, applies every supported value through its real production owner, rejects unsupported C2/nuclear keys, persists exact format-114 state, and proves declared/omitted behavioral controls. |
| Quality | **High.** Configs and contracts are frozen/extra-forbidden; resolution and checkpoint failures are atomic; interval cadence has one owner; no stub, placeholder, proxy, silent fallback, swallowed new exception, or test-only production path remains. |
| Integration | **Fully proven for REM-018.** Declared, loaded, wired, enabled, exercised, outcome-affecting, and persisted/exposed stages all have production-factory evidence and negative controls. REST/frontend editing is N/A; the real API runner exposes effective cadence/fingerprint behavior. |
| New deficits | REM-035 through REM-040 record the battle-topology, communications, CBRN scheduling, medical lifecycle, maintenance lifecycle, and validation-runner prerequisites found during review. They are assigned to Phases 122 through 127. REM-020/021 remain separate logistics authority work. |
| Validation | Focused production, checkpoint, API, determinism, data, 46-scenario, exact 11,903-node Python union, terrain, benchmark-policy, frontend, static/evidence, documentation, simplification, conventions, and cross-document gates pass. Timing is accepted only under the explicit owner qualification; no uncontended pass is claimed. |
| Action items | Rerun the unchanged paired benchmark when the owner reports all cores free; run hosted CI after the phase commit; execute REM-035--040 only in their assigned phases. None is concealed as Phase 114 behavior. |

### Contract reconstruction

All planned REM-018 work is delivered. Shipped unsourced historical treatment,
repair, cadence, C2, and nuclear values were removed instead of being made
outcome-affecting. C2 and nuclear declarations reject because their production
prerequisites do not exist. Automatic casualty admission/facility topology,
equipment registration/repair logistics, and validation-runner era propagation
were not silently absorbed; they remain REM-038 through REM-040. No military
parameter, scenario force composition, weapon performance, historical
calibration, or public override editor was added.

Necessary integration work exceeded the narrow metadata replacement without
broadening its capability claim: the engine now binds one resolution and `dt`
to each complete interval, stages rejecting preflight before cadence mutation,
removes duplicate campaign maintenance advancement, freezes custom-registry
inputs in prepared variants, validates executable calendar horizons, and
advances checkpoint format 113 to exact format 114. These changes are required
for the supported values to be executable and persistable rather than
structural metadata.

### Integration and test quality

The authoritative trace is
`CampaignScenarioConfig -> SimulationRuntimeFactory -> PreparedScenario ->
ScenarioLoader -> SimulationEngine -> RuntimeSession`. Direct loader use is a
separate lower-boundary control. Natural strategic, operational, and tactical
paths demonstrate different logical-time outcomes. Public medical admission
and maintenance registration/repair APIs demonstrate all three treatment
durations and repair completion against same-seed omitted controls. Prepared
registry replacement produces stable old builds, changed new builds, and
different fingerprints. The API proof executes the real run manager and
observes tick counts, duration, frame cadence, and fingerprint differences.

Format-114 tests require one exact effective contract, reject missing, extra,
malformed, mismatched, old-version, calendar, and clock/resolution state before
mutation, and prove byte-identical in-place and fresh continuation with active
treatment and repair. Determinism evidence covers same-seed replay, transition
ordering, checkpoint bytes, event/RNG continuation, hash-seed independence,
and unchanged non-logistics streams. Test helpers only adapt legacy minimal
contexts or trace real calls; they are not acceptance evidence by themselves.
No skip/xfail, weakened assertion, direct-oracle concealment, or new default
suite exclusion was introduced.

### Final postmortem commands

```text
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase114-uv-cache \
  uv run --no-sync pytest -q --tb=short -o addopts= \
  tests/integration/test_phase114_checkpoint_and_transitions.py \
  tests/integration/test_phase114_era_override_execution.py \
  tests/integration/test_phase114_factory_runtime_behavior.py
# 76 passed in 60.83s; 0 failures/errors/skips/warnings

env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase114-uv-cache \
  uv run --no-sync pytest -q --tb=short -o addopts= \
  tests/api/test_phase114_era_runtime_api.py
# host boundary: 1 passed in 6.75s; 0 failures/errors/skips/warnings

env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase114-uv-cache \
  uv run --extra docs mkdocs build --strict \
  --site-dir /tmp/sw-phase114-docs-site-owner-qualified-final
# exit 0; built in 5.82s; three intentional navigation omissions and the
# informational Material-for-MkDocs/MkDocs-2 banner

env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase114-uv-cache \
  uv run --no-sync python scripts/validate_docs_links.py
# valid=0; invalid fixture=1 with diagnostic; wrapper=0

git diff --check
# clean
```

The independent adversarial implementation review and final ten-area
`$cross-doc-audit` both report no blockers. The bounded residual uncertainty
is wall-clock timing under external contention only; the original thresholds
remain intact and uncontended confirmation is deferred by explicit owner
direction. The evidence is sufficient for the Phase 114/REM-018 status
transition.

### Status transition verification

The explicit transition updates Phase 114 to **Complete**, REM-018 to
**Closed**, and Block 12 to **Complete** across the roadmap, backlog, devlog
index, specifications, README, documentation index, and provider context.
Block 13 remains planned and Phase 115 remains not started.

```text
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase114-uv-cache \
  uv run --extra docs mkdocs build --strict \
  --site-dir /tmp/sw-phase114-docs-site-status-final-rerun
# exit 0; built in 9.50s after final status-audit corrections; three
# intentional navigation omissions and the
# informational Material-for-MkDocs/MkDocs-2 banner

env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase114-uv-cache \
  uv run --no-sync python scripts/validate_docs_links.py
# valid=0; invalid fixture=1 with diagnostic; wrapper=0

env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase114-uv-cache \
  uv run --no-sync ruff check stochastic_warfare/ api/ tests/ scripts/
# All checks passed!

git diff --check
# clean
```

The status transition does not alter the performance record: every noisy run
remains inconclusive, the original thresholds remain intact, no uncontended
pass is claimed, and clean confirmation remains deferred until the owner
reports that all cores are free.

The final post-transition `$cross-doc-audit` reports PASS across the public
badges, Block 12/Phase 114/REM-018 status, Block 13 handoff, performance
qualification, historical supersession notices, backlog, specifications, and
provider context. It found no premature Phase 115 start or remaining current
status contradiction.
