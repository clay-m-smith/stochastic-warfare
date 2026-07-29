# Phase 111 - Time-on-Target Execution

**Status:** Complete

**Started:** 2026-07-29

**Finished:** 2026-07-29

## Why this phase exists

`IndirectFireEngine` contains Phase 27 component helpers for time-on-target
planning and execution, but the production scenario schema cannot declare a
mission and `SimulationEngine` never calls either helper. The plan drops real
battery positions; execution substitutes `Position(0, 0, 0)`, repeats every
due battery on every call, silently skips missing weapons, consumes no live
ammunition, changes no target, emits no mission result, and checkpoints only
the shared RNG state.

Phase 111 owns REM-012 under the durable contract in
[`docs/specs/time-on-target-execution.md`](../specs/time-on-target-execution.md).

## Start gate

Phase 110 passed `$postmortem`, was committed as
`3c095867d8ef888afd784863e256062d2140d266`, and was pushed before Phase 111
began. Its remote GitHub workflows subsequently completed successfully:

```text
Tests                 success  8m34s
Lint                  success  27s
Deploy Documentation  success  33s
Benchmarks            success  36s
```

The required Phase 111 synchronization gate was then repeated:

```text
git pull --ff-only origin main
# Already up to date.

git status --short --branch
# ## main...origin/main

git rev-parse HEAD
git rev-parse origin/main
# 3c095867d8ef888afd784863e256062d2140d266
# 3c095867d8ef888afd784863e256062d2140d266
```

`CODEX.md`, `AGENTS.md`, Block 12, REM-012, the Phase 110 devlog, relevant
implementation/tests/architecture, and the selected skill instructions were
read before production changes.

The host provides 32 logical CPUs and 62 GiB RAM, with 58 GiB available and
7.8 GiB swap available at the phase baseline. Independent commands can run in
parallel; individual pytest invocations remain serial unless the repository
provides a supported parallel runner.

## Specification and design gate

`$spec` defined the typed production contract. `$design-review`,
`$research-military`, and `$research-models` were then invoked because the
phase adds a scheduled runtime/checkpoint boundary and replaces an unsupported
time-of-flight calculation.

Official Army and Marine Corps gunnery doctrine consistently defines
time-on-target around a common impact time and individually computed/reported
battery times of flight. It also requires accurate firing-unit/target
locations, exact weapon/ammunition data, finite ammunition, coordinated
execution, and explicit reporting when planned fire does not occur.

No authoritative source supports the component helper's
`2 * range / muzzle_velocity` estimate or independent Normal planning jitter
with `sigma=2 s`. The existing general ballistics helper also lacks a
validated artillery charge/elevation solution and uses unsourced drag and
velocity fallbacks. Phase 111 therefore accepts a typed battery-specific
fire-control hang time, validates a physical lower bound against real range
and catalog speed, and schedules
`fire_time = impact_time - time_of_flight`. It does not claim automatic
firing-table fidelity.

The first independent design and test reviews returned `NEEDS REVISION`.
Production edits remained paused. They identified:

- a forbidden combat-to-simulation dependency if the engine consumed
  `RuntimeLoadouts` directly;
- ambiguous attachment identity without the Phase 109 source-equipment index;
- false lethal treatment of smoke, illumination, and zero-radius ammunition;
- incomplete preservation of ordinary terrain/cumulative effect inputs;
- missing movement/domain/aggregate-inventory and rejection-precedence rules;
- contradictory disabled-plan chronology and unreconciled duplicate COMBAT
  RNG/live checkpoint authorities; and
- inaccurate coarse-tick semantics that could observe future displacement at
  an earlier scheduled fire time.

The specification now uses one typed simulation-layer resolver that emits
lower-layer plans, requires the exact source-equipment attachment, accepts only
positive-radius lethal ammunition, preserves the complete aggregate assessment
inputs, freezes runtime/event/outcome semantics, uses dormant disabled state,
and reconciles live checkpoint authorities. A second review rejected
multi-round instantaneous fire and full-tick milestone splitting: the revised
boundary permits one simultaneous initial round per represented system and
requires a fixed whole-second cadence with every fire/impact time aligned.
The runtime/design re-review then returned `APPROVED`, with no remaining
medium/high design blockers.

The independent test-integrity re-review accepted the fixed-cadence revision
but identified three remaining checkpoint/rate-accounting ambiguities before
red tests could be encoded:

- cooldown needed to account for the number of simultaneous rounds against the
  Phase 109 aggregate rate of fire;
- fresh `WeaponInstance` state uses `-inf` for never fired, which needed a
  canonical finite-safe indirect checkpoint representation; and
- a pending milestone equal to checkpoint elapsed time is already due and
  could otherwise be forged for duplicate processing.

It also requested exact target-effect precedence and status serialization,
horizontal-versus-three-dimensional range semantics, and unambiguous
attribution for heterogeneous unit status events. The contract now defines
all six points. The final adversarial test-integrity re-review returned
`APPROVED`, with no remaining medium/high design or testability blockers. It
requires the focused suite to exercise quantity-aware cooldown with a
composite attachment and more than one round because the multiplier-one M109
positive fixture cannot prove that rule. These approvals freeze the
implementation contract; they do not count as implementation or phase-closure
evidence.

## Production trace at phase start

| Stage | Phase-start evidence |
|---|---|
| Declared | Component dataclasses and two loose tunables exist; no scenario mission schema exists |
| Loaded | `ScenarioLoader` constructs an empty/default indirect-fire engine without mission or live-loadout inputs |
| Wired | Ordinary battle fire-for-effect calls `fire_mission()`; no production caller reaches either time-on-target helper |
| Enabled | No gate or declared mission reaches runtime |
| Exercised | Existing tests call the engine directly |
| Outcome-affecting | Component execution draws impact points only; it consumes no live ammunition and changes no unit |
| Persisted/exposed | Engine state is RNG-only; `ArtilleryFireEvent` has no mission identity, schedule, side, firing position, or terminal result |

Source tracing also established:

- `TOTFirePlan` stores no mission identity, live attachment, firing position,
  ammunition, round count, or lifecycle state;
- `compute_tot_plan()` silently truncates batteries, ignores its ammunition
  argument, substitutes 300 m/s, and draws fresh jitter on each call;
- `execute_tot_mission()` uses the origin as every firing point, silently skips
  a missing definition, and fires every due battery again on every invocation;
- direct `fire_mission()` takes definitions rather than the Phase 109 live
  `WeaponAttachment` and does not consume ammunition/cooldown/maintenance;
- `SimulationEngine.step()` has no time-on-target boundary; and
- generic recorder and API event paths are already capable of exposing a new
  typed event whose payload includes `attacker_side`.

The ordinary battle indirect-fire route appears not to consume the selected
live magazine. That adjacent Class V authority gap is not concealed as
REM-012 completion and remains outside Phase 111's scheduled-mission repair.

## Baseline evidence

Python commands use `UV_CACHE_DIR=/tmp/phase111-uv`.

### Existing component green

```text
UV_CACHE_DIR=/tmp/phase111-uv uv run python -m pytest -q --tb=short \
  -o addopts= \
  tests/unit/combat/test_indirect_fire.py::TestTOTPlan \
  tests/unit/test_phase_27b_engagement.py::TestTOTSync
# 11 passed in 0.10s
```

All 11 tests are direct component tests. They do not load mission
configuration, step `SimulationEngine`, resolve live attachments, consume a
magazine, change a target, record a terminal result, exercise an API, or
restore a fresh checkpoint.

### Repository Python lint baseline

The exact remote Python lint command is clean locally:

```text
UV_CACHE_DIR=/tmp/phase111-uv uv run ruff check \
  stochastic_warfare/ api/ tests/ scripts/
# All checks passed!
```

### Data baseline

```text
UV_CACHE_DIR=/tmp/phase111-uv uv run python \
  scripts/validate_scenario_data.py
# 184 unit YAML files
# modern: 102 units, 394 occurrences, 244 distinct keys,
#   101 sensor-required, 1 intentionally sensorless
# ancient_medieval: 20 units, 67 occurrences, 34 distinct keys
# napoleonic: 21 units, 57 occurrences, 27 distinct keys
# ww1: 16 units, 57 occurrences, 47 distinct keys
# ww2: 25 units, 104 occurrences, 93 distinct keys
# full registry: 442/442 covered; 0 unmapped; 0 stale
# 9 constellation definitions; 3 ASAT weapon definitions
# 51 scenario YAML files
# 0 errors, 0 validator warnings, 1 explicit sensorless classification
# PASSED
```

The command exits zero but emits 2 missing-unit loader log messages for
`french_old_guard` and 77 failed commander-profile assignment log messages.
These are not counted as validator warnings; the validation-trust/profile
deficits remain assigned to Phase 112 rather than being hidden in this phase.

## Production red proof

After both adversarial contract reviews approved, the first durable red test
added the shipped
`data/scenarios/time_on_target_validation/scenario.yaml` fixture. It declares
two exact M109A6 attachments at real positions, one enemy HEMTT and target
point, M982 ammunition, 60/55-second predicted flight times, 60/65-second fire
times, one round per battery, a 120-second common impact, and a fixed
five-second cadence. The test loads that YAML through `ScenarioLoader`, steps
the real `SimulationEngine` 25 times, and observes live magazines, maintenance,
cooldown, target state, artillery events, and the terminal recorder event.

```text
UV_CACHE_DIR=/tmp/phase111-uv uv run pytest -q --tb=short \
  -o addopts= \
  tests/integration/test_phase_111_time_on_target_production.py
# 1 failed in 0.84s
# expected one TimeOnTargetMissionEvent; production recorded zero
```

The scenario loaded and completed the requested engine ticks. The failure is
therefore the missing production execution path, not a collection error,
constructor probe, mock, or no-crash assertion.

## Implementation

### Typed declaration and resolution boundary

`CampaignScenarioConfig.indirect_fire` now owns a strict
`IndirectFireScenarioConfig`. Nested models reject unknown fields, coercible
booleans/numbers, empty or padded identifiers, duplicate mission/battery IDs,
more than six batteries, non-positive or fractional firing times, off-cadence
milestones, and impacts after scenario duration. A targeted root-key guard
normalizes separators/case, recognizes unambiguous compact TOT feature names,
and applies bounded near-match checks to reject misspelled or misplaced
indirect-fire fields without pretending every legacy scenario metadata key is
strict. Permanent controls cover `indrect_fire`, `timeOnTargetMissions`,
`time_on_targte_missions`, `totPlan`, `enableTimeOnTarget`,
`enableIndirectFire`, malformed `enable_time_*`, `enable_tot`, `enableTot`,
and `totEnabled`, while all nine shipped root extensions plus unrelated
`indirect_*`/`total*` metadata remain accepted.

`TimeOnTargetMissionResolver` is the sole production construction boundary. It
runs after the Phase 109 `RuntimeLoadoutBuilder` and resolves:

- the exact initial target and attacker side;
- each exact battery unit, source-equipment index, retained source object,
  runtime system multiplier, live `WeaponInstance`, and unique ammunition
  definition;
- real initial firing and target ENU positions;
- one authored whole-second impact and each derived whole-second fire time;
  and
- aggregate ammunition and quantity-aware cooldown commitments across every
  mission sharing an attachment.

Resolution rejects unknown/ambiguous/friendly/inactive references, mixed
battery sides, unsupported weapon categories or target domains,
smoke/illumination/zero-radius ammunition, incompatible rounds, terrain/range
violations, a time of flight below the three-dimensional catalog-speed lower
bound, rounds above the exact system multiplier, aggregate ammunition
overbooking, and conflicting attachment schedules. Authored time of flight is
therefore an explicit fire-control input, not an invented firing-table claim.

### Scheduled production execution

`SimulationEngine.step()` invokes `IndirectFireEngine.update_time_on_target()`
after already-committed scripted events and before movement/detection/autonomous
battle. Fixed-cadence milestones sort by
`(scheduled_time, fire-before-impact, mission declaration, battery declaration)`
and reject a skipped clock boundary rather than evaluating old fire times
against later state.

At each battery fire, the engine snapshots the real unit/equipment/resource
preconditions and applies the fixed rejection precedence:

```text
battery_inactive -> battery_moving -> battery_displaced ->
weapon_inoperable -> insufficient_ammunition -> weapon_cooldown
```

A valid fire consumes the exact live magazine once, increments total and
maintenance rounds, records the exact scheduled cooldown time, generates
impacts through the existing indirect-fire dispersion path, then publishes
`AmmoExpendedEvent` before `ArtilleryFireEvent`. Rejections draw no COMBAT RNG
and mutate no resource.

At the common impact, the public pure `assess_indirect_fire_impacts()` boundary
preserves ordinary cumulative-hit, terrain, casualty, and threshold inputs.
The scheduled mission resolves the live target position/status at impact,
commits any `UnitDisabledEvent`/`UnitDestroyedEvent`, and publishes one typed
`TimeOnTargetMissionEvent` containing exact attachment identity, planned and
actual positions, schedule, battery outcomes/reasons, impact counts, mission
outcome, and target before/after state. Observer failures are collected and
logged only after state commits, so they neither roll back nor make the mission
retryable.

Every planned exact attachment is reserved from ordinary `BattleManager`
selection until the last mission using it completes. Unrelated attachments
remain selectable, and release occurs at the common impact boundary.
`TOTFirePlan`, `compute_tot_plan()`, and `execute_tot_mission()` were removed;
there is no second private or stateless production path.

### Persistence and exposure

Checkpoint schema 111 persists the immutable plan fingerprint, enabled/dormant
gate, every mission/battery lifecycle, impact positions, resource and
precondition history, target transition, terminal result, and the exact COMBAT
RNG mirror. `SimulationContext.set_state()` stages that state against the
checkpoint clock, staged RNG manager, exact staged live weapon states, unit
statuses, and immutable runtime topology before committing any context-owned
state.

The validator independently recomputes rejection precedence, resource deltas,
terminal assessment/event content, milestone chronology, and shared-attachment
history. A causally valid aggregate public live-fire bridge may occur before,
between, or after scheduled lifecycle transitions, including while the exact
attachment remains reserved from ordinary battle selection. Its ammunition
topology cannot change or increase, ammunition depletion must equal total and
maintenance counter growth, last-fire time must be finite/advancing and satisfy
quantity-aware cooldown, and it must lie after the preceding processed
milestone and no later than checkpoint elapsed. More exactly, the latest
preceding resource-bearing processed milestone is the lower bound even after
release because impact processing does not sample the live weapon. The next
scheduled milestone observes real depletion/cooldown and records the
deterministic rejection or fire. Future, before-observation, nonadvancing,
counter-inconsistent, reload, unspent-fired, target-regression, topology, or
RNG contradictions reject atomically.

The generic recorder and `/api/runs/{run_id}/events` boundary expose the new
terminal event, including the existing `side` filter through
`attacker_side`. No bespoke endpoint or log-only completion path was added.

### Validation scenario

`data/scenarios/time_on_target_validation/scenario.yaml` is a synthetic
production regression, not a historical calibration. It contains two
catalog-backed M109A6 units and one HEMTT target. Exact M284/M982 batteries fire
at 60 and 65 seconds from `[1000, 9000, 0]` and `[4000, 11000, 0]`, then resolve
one common impact at 120 seconds against `[22000, 10000, 0]`.

## Focused verification

The final consolidated schema, production, and checkpoint command is:

```text
UV_CACHE_DIR=/tmp/phase111-uv uv run python -m pytest -q --tb=short \
  -o addopts= \
  tests/unit/test_phase_111_time_on_target_schema.py \
  tests/integration/test_phase_111_time_on_target_production.py \
  tests/integration/test_phase_111_time_on_target_checkpoint.py
# 162 passed in 44.33s
```

Those 162 cases include 97 strict schema/resolution/runtime-composite cases, 15
production behavior cases, and 50 checkpoint cases. They prove the complete
declared/loaded/wired/enabled/exercised/outcome/persisted matrix, including:

- two distinct real fire times, one common impact, one terminal event, exact
  event order, and no duplicate effects across extra ticks;
- M982 inventory `39 -> 38` on each attachment, total/maintenance counters
  `0 -> 1`, and last-fire times exactly `60.0`/`65.0`;
- target `ACTIVE -> DISABLED` in the enabled seed-42 run and no change in
  populated-disabled or omitted/empty controls;
- impact points
  `(22028.4482755155, 10013.74887723078, 0)` and
  `(21969.60867857095, 9975.755081740439, 0)`;
- exact runtime rejection reason/precedence, partial outcome, moved-target
  miss, already-inactive target, throwing observer, ordinary cumulative/terrain
  compatibility, exact attachment reservation, shared-plan release, exact
  same-tick follow-on-fire-before-impact order and status-event attribution,
  ambiguity rejection for duplicated source attachments/ammunition, and a real
  four-system quantity-aware cooldown boundary;
- fresh continuation before fire, between fire and impact, after completion,
  after a causal reserved pre-fire mutation, in the middle of a shared
  attachment plan, after released/disabled-plan external fire, after a legal
  reserved fire between scheduled fire and impact followed by completion, and
  after authored times for a dormant populated plan; and
- atomic rejection of malformed topology, ordering, timing, lifecycle,
  resource/weapon null or non-finite sentinel boundaries, resources,
  whole-checkpoint quantity cooldown, target regression, RNG, version, future,
  before-observed-milestone, reload/counter mismatch, and shared nonadvancing
  histories.

The dedicated real HTTP boundary initially ran separately:

```text
UV_CACHE_DIR=/tmp/phase111-uv uv run pytest -q --tb=short -o addopts= \
  tests/api/test_phase_111_time_on_target_api.py
# 3 passed in 1.35s
```

It submits the shipped plan through `POST /api/runs/from-config`, waits for the
production run, retrieves the exact complete event with blue/red side controls,
rejects a nested typo with 422 before submission, and records an unresolved
battery reference as a failed background run rather than a false success.

Relevant compatibility selections were also green:

```text
UV_CACHE_DIR=/tmp/phase111-uv uv run pytest -q --tb=short -o addopts= \
  tests/unit/combat/test_indirect_fire.py \
  tests/unit/test_phase_27b_engagement.py \
  tests/unit/test_phase43_domain_resolution.py \
  tests/unit/test_phase48_deficit_fixes.py \
  tests/unit/test_phase_68e_fire_damage.py
# 151 passed in 1.97s

UV_CACHE_DIR=/tmp/phase111-uv uv run pytest -q --tb=short -o addopts= \
  tests/unit/test_simulation_engine.py \
  tests/unit/test_simulation_scenario.py \
  tests/unit/test_phase_107_scenario_wiring.py
# 219 passed in 27.47s
```

## Conditional reviews

### Determinism

`$audit-determinism` returned **CONDITIONALLY DETERMINISTIC - no Phase 111
blocker**.

```text
UV_CACHE_DIR=/tmp/phase111-uv uv run pytest -q --tb=short -o addopts= \
  tests/integration/test_phase_111_time_on_target_production.py::test_same_seed_fresh_runs_match_complete_state_and_ordered_events
# 1 passed in 1.53s

UV_CACHE_DIR=/tmp/phase111-uv uv run pytest -q --tb=short -o addopts= \
  tests/integration/test_phase_111_time_on_target_checkpoint.py::test_fresh_runtime_continuation_is_exact_at_every_tot_lifecycle
# 3 passed in 2.26s
```

The populated-disabled control plus all seven runtime rejection parameters
passed eight same-seed RNG controls:

```text
UV_CACHE_DIR=/tmp/phase111-uv uv run python -m pytest -q --tb=short \
  -o addopts= \
  tests/integration/test_phase_111_time_on_target_production.py::test_disabled_populated_and_empty_controls_are_inert \
  tests/integration/test_phase_111_time_on_target_production.py::test_runtime_rejections_are_terminal_ordered_and_rng_free
# 8 passed in 3.14s
```

The exact production checkpoint probe was invoked once with each hash seed:

```text
PYTHONHASHSEED=1 UV_CACHE_DIR=/tmp/phase111-uv uv run python -c \
  'import hashlib,json; from pathlib import Path; from stochastic_warfare.simulation.engine import SimulationEngine; from stochastic_warfare.simulation.recorder import SimulationRecorder; from stochastic_warfare.simulation.scenario import ScenarioLoader; p=Path("data/scenarios/time_on_target_validation/scenario.yaml"); c=ScenarioLoader(Path("data")).load(p,seed=42); r=SimulationRecorder(c.event_bus); r.start(); e=SimulationEngine(c,recorder=r,strict_mode=True); [e.step() for _ in range(30)]; raw=e.checkpoint(); canonical=json.dumps(json.loads(raw),sort_keys=True,separators=(",",":")).encode(); print(len(raw),hashlib.sha256(raw).hexdigest(),hashlib.sha256(canonical).hexdigest(),len(r.events))'

PYTHONHASHSEED=987654 UV_CACHE_DIR=/tmp/phase111-uv uv run python -c \
  'import hashlib,json; from pathlib import Path; from stochastic_warfare.simulation.engine import SimulationEngine; from stochastic_warfare.simulation.recorder import SimulationRecorder; from stochastic_warfare.simulation.scenario import ScenarioLoader; p=Path("data/scenarios/time_on_target_validation/scenario.yaml"); c=ScenarioLoader(Path("data")).load(p,seed=42); r=SimulationRecorder(c.event_bus); r.start(); e=SimulationEngine(c,recorder=r,strict_mode=True); [e.step() for _ in range(30)]; raw=e.checkpoint(); canonical=json.dumps(json.loads(raw),sort_keys=True,separators=(",",":")).encode(); print(len(raw),hashlib.sha256(raw).hexdigest(),hashlib.sha256(canonical).hexdigest(),len(r.events))'
# Both:
# 36154 69ace91994e8c13d9738aa69726c8dcd91538fff804c094e922b8542a9f21f33
# 429ead4d08b391289f0f55ed7105b8c6485a1e56ede55202905efc1e22ad7f11 6
```

Thus the two processes produced byte-identical 36,154-byte checkpoints, the
same raw and canonical semantic SHA-256 values, and the same six ordered
events. The exact stream/isolation and different-seed probe was:

```text
UV_CACHE_DIR=/tmp/phase111-uv uv run python -c 'import copy,json
from pathlib import Path
from stochastic_warfare.simulation.engine import SimulationEngine
from stochastic_warfare.simulation.scenario import CampaignScenarioConfig,ScenarioLoader,load_campaign_scenario_config
p=Path("data/scenarios/time_on_target_validation/scenario.yaml")
def run(seed,enabled):
 payload=load_campaign_scenario_config(p).model_dump(mode="python")
 payload["indirect_fire"]["enable_time_on_target"]=enabled
 ctx=ScenarioLoader(Path("data")).load(p,seed=seed,scenario_config=CampaignScenarioConfig.model_validate(payload))
 before=copy.deepcopy(ctx.rng_manager.get_state()["streams"])
 engine=SimulationEngine(ctx,strict_mode=True)
 [engine.step() for _ in range(30)]
 after=copy.deepcopy(ctx.rng_manager.get_state()["streams"])
 state=ctx.indirect_fire_engine.get_state()
 impacts=[impact["position"] for mission in state.get("missions",[]) for battery in mission["batteries"] for impact in battery["impacts"]]
 return before,after,impacts
enabled_before,enabled_after,impacts42=run(42,True)
disabled_before,disabled_after,_=run(42,False)
_,_,impacts43=run(43,True)
print(json.dumps({"stream_count":len(enabled_before),"initial_states_equal":enabled_before==disabled_before,"enabled_changed":[name for name in enabled_before if enabled_before[name]!=enabled_after[name]],"disabled_changed":[name for name in disabled_before if disabled_before[name]!=disabled_after[name]],"enabled_disabled_differences":[name for name in enabled_after if enabled_after[name]!=disabled_after[name]],"seed42_impacts":impacts42,"seed43_impacts":impacts43,"different_seed_impacts":impacts42!=impacts43},sort_keys=True,separators=(",",":")))'
# {"different_seed_impacts":true,"disabled_changed":["environment"],
# "enabled_changed":["combat","environment"],
# "enabled_disabled_differences":["combat"],"initial_states_equal":true,
# "seed42_impacts":[[22028.4482755155,10013.74887723078,0.0],
# [21969.60867857095,9975.755081740439,0.0]],
# "seed43_impacts":[[22014.270947206056,9978.750863225265,0.0],
# [21995.744372540084,10028.749689917713,0.0]],"stream_count":16}
```

Both runs advanced the ordinary ENVIRONMENT stream. Enabled versus disabled
changed only COMBAT between their final states, leaving the other 15 streams
identical. Seed 43 produced different impact points.

The limitation is explicit: time on target correctly uses the existing shared
COMBAT stream, so unrelated earlier COMBAT draws can perturb later dispersion.
There is no internal parallel work or unordered state iteration. Cross-NumPy,
cross-architecture bit identity is not claimed, and enum/module ordering
remains a checkpoint compatibility boundary.

The final post-repair `$audit-determinism` verdict remained
**CONDITIONALLY DETERMINISTIC - CLEAN/no Phase 111 blocker**. Its fresh
read-only selections reported 65 production/checkpoint cases passing in 36.38
seconds; 9 same-seed, disabled/empty, and seven rejection RNG controls in 3.75
seconds; and 21 continuation plus scalar/chronology corruption cases in 13.24
seconds. It independently reproduced the two hash-seed results, 16-stream
isolation, and distinct seed-43 impacts above. Source review confirmed one
injected COMBAT generator, explicit fire-before-impact tuple ordering,
declaration-ordered resource state, stage-before-commit persistence, and no
new wall-clock, global RNG, process-identity, unordered-outcome, or parallel
path. The shared-COMBAT and cross-platform qualifications remain exactly as
stated.

### Data and scenario validation

`$validate-data` and `$scenario` are **APPROVED**. The file-only validator for
the new YAML exited zero with no output:

```text
UV_CACHE_DIR=/tmp/phase111-uv uv run python \
  scripts/validate_scenario_data.py \
  --file data/scenarios/time_on_target_validation/scenario.yaml
# exit 0; 0 errors; 0 warnings
```

The full validator command:

```text
UV_CACHE_DIR=/tmp/phase111-uv uv run python \
  scripts/validate_scenario_data.py
```

reported:

- 184 unit YAML files;
- modern: 102 units, 394 occurrences, 244 distinct keys,
  101 sensor-required and 1 intentionally sensorless;
- ancient/medieval: 20 units, 67 occurrences, 34 keys;
- Napoleonic: 21 units, 57 occurrences, 27 keys;
- WWI: 16 units, 57 occurrences, 47 keys;
- WWII: 25 units, 104 occurrences, 93 keys;
- complete 442/442 registry coverage, 0 unmapped, and 0 stale;
- 9 constellation and 3 ASAT weapon definitions;
- 52 scenario YAML files; and
- **PASSED: 0 errors, 0 validator warnings, 1 explicit sensorless
  classification**.

The process also exposed 79 already-tracked logger diagnostics that are not
validator warnings: 2 `french_old_guard` construction messages assigned to
REM-024 and 77 commander-profile assignment messages assigned to REM-023.
They remain visible for Phase 112.

```text
UV_CACHE_DIR=/tmp/phase111-uv uv run pytest -q --tb=short -o addopts= \
  tests/validation/test_phase_30_scenarios.py::TestScenarioFullLoad
# 52 passed in 18.61s
```

After the postmortem strengthened the root-key typo boundary, the entire
scenario-validation module was repeated:

```text
UV_CACHE_DIR=/tmp/phase111-uv uv run python -m pytest -q --tb=short \
  -o addopts= tests/validation/test_phase_30_scenarios.py
# 272 passed in 25.25s
```

The production scenario evaluator command was:

```text
UV_CACHE_DIR=/tmp/phase111-uv uv run python \
  scripts/evaluate_scenarios.py \
  --scenario time_on_target_validation --seed 42 --no-details \
  --output /tmp/phase111-time-on-target-evaluation.json
```

It selected one scenario, completed 720 five-second ticks/3,600 seconds in
0.43 seconds, and returned draw/time-expired. Initial active counts were blue
2/red 1; final active counts were blue 2/red 0, with one evaluator casualty,
seven events, two weapon fires, zero ordinary engagements, and zero generic
damage/destruction events. `NO_MOVEMENT` is expected because all units
explicitly use hold-position/defensive behavior. Repeating to
`/tmp/phase111-time-on-target-evaluation-replay.json` was semantically
identical excluding wall time (0.50 seconds). The evaluator's generic casualty
count treats any non-active unit as a casualty; that known analysis semantic is
part of REM-017/Phase 112, not presented as a Phase 111 historical claim.

Representative seed-42 regressions remained semantically controlled:

- Korean Peninsula: blue/force-destroyed, 144 ticks, 16 casualties,
  89 engagements, 20 moved/18 stuck, identical to the Phase 110 row;
- Somme July 1: German/time-expired, 618 ticks, 5 casualties,
  50 engagements, 5 moved/5 stuck, identical to the Phase 109 row; and
- Cambrai: British/force-destroyed, 433 ticks, 2 casualties,
  14 engagements, 3 moved/7 stuck, with the already-tracked
  `MANY_STUCK_UNITS(4/7)` REM-025 diagnostic.

The exact evaluator and artifact-projection commands were:

```text
UV_CACHE_DIR=/tmp/phase111-uv uv run python \
  scripts/evaluate_scenarios.py --scenario korean_peninsula --seed 42 \
  --no-details \
  --output /tmp/phase111-representative-korean-peninsula-seed42.json
# exit 0; OK; 144 ticks; 16 casualties; 89 engagements;
# 20/38 moved; 18/38 stuck; 0.9s wall
# 38 visible commander-profile diagnostics assigned to REM-023

UV_CACHE_DIR=/tmp/phase111-uv uv run python \
  scripts/evaluate_scenarios.py --scenario somme_july1 --seed 42 \
  --no-details \
  --output /tmp/phase111-representative-somme-july1-seed42.json
# exit 0; OK; 618 ticks; 5 casualties; 50 engagements;
# 5/10 moved; 5/10 stuck; 0.8s wall

UV_CACHE_DIR=/tmp/phase111-uv uv run python \
  scripts/evaluate_scenarios.py --scenario cambrai --seed 42 \
  --no-details \
  --output /tmp/phase111-representative-cambrai-seed42.json
# exit 0; WARN(MANY_STUCK_UNITS(4/7)); 433 ticks; 2 casualties;
# 14 engagements; 3/10 moved; 7/10 stuck; 0.7s wall

UV_CACHE_DIR=/tmp/phase111-uv uv run python -c 'import json
from pathlib import Path
for path in (Path("/tmp/phase111-representative-korean-peninsula-seed42.json"),Path("/tmp/phase111-representative-somme-july1-seed42.json"),Path("/tmp/phase111-representative-cambrai-seed42.json")):
 row=json.loads(path.read_text())[0]
 print(row["scenario_name"],row["success"],row["victory_side"],row["victory_condition"],row["ticks_executed"],row["total_casualties"],row["engagement_events"],f"{row['units_that_moved']}/{row['units_that_didnt_move']}",row["issues"])'
# korean_peninsula True blue force_destroyed 144 16 89 20/18 []
# somme_july1 True german time_expired 618 5 50 5/5 []
# cambrai True british force_destroyed 433 2 14 3/7
# ['MANY_STUCK_UNITS(4/7)']
```

The evaluator's internal scenario exclusions remain `test_campaign*` and
`benchmark_*`; these representative rows are regression observations, not
baseline promotion or historical calibration.

### Conventions and performance applicability

`$validate-conventions` returned **CLEAN**: configuration uses strict typed
models; runtime plans use frozen typed records; all times are simulation-clock
seconds; all positions are internal ENU; ordering is canonical; the only RNG
is the injected COMBAT generator; public/new annotations do not introduce
untyped `Any` boundaries; events use `datetime` and the existing event bus; and
checkpoint restore stages before mutation.

The final post-repair `$validate-conventions` rerun also returned **CLEAN**.
Fresh selections reported 5 strict checkpoint/RNG cases passing with 45
deselected in 3.64 seconds, 4 enabled/disabled/replay/order cases in 2.72
seconds, and 35 strict schema/root/numeric cases in 1.11 seconds. Repository
Ruff and exact phase diff-check were clean. The reviewer confirmed logical
clock timestamps, ENU coordinates, combat-to-simulation dependency direction,
stable ordering, typed public config/events/methods, the injected COMBAT
generator, and stage-before-commit checkpoint mutation. Its redundant
in-sandbox dedicated API attempt made no progress and was interrupted
(exit 130); it is excluded, while the separately authorized outside-sandbox
`3 passed` run is the API evidence.

`$profile` was not applicable. Phase 111 adds a bounded scan over at most six
batteries per authored mission at aligned milestones; it does not change the
large-unit spatial, movement, detection, or battle loops. The production
validation scenario completed 720 ticks in under one second, and no performance
claim or optimization is made.

## Broader verification

The first full-code default run found two documentation/test-manifest
expectation failures, not runtime failures:

```text
UV_CACHE_DIR=/tmp/phase111-uv uv run python -m pytest --tb=short -q
# 2 failed, 10,916 passed, 21 skipped, 348 deselected, 6 warnings in 329.02s
```

The Phase 108 checkpoint test still expected schema 110, and the synthetic
validation scenario was absent from the historical-regression coverage
classification. The expectation was advanced to 111; the new scenario is now
explicitly classified as a synthetic validation fixture with exact dedicated
tests and is not mislabeled as a historical calibrated result. The targeted
repair selection passed three cases in 1.84 seconds.

A pre-simplification clean run then passed 10,921 tests. After the first
`$simplify` pass added four checkpoint cases and repaired the
trailing-resource boundary, the then-current candidate run was:

```text
UV_CACHE_DIR=/tmp/phase111-uv uv run python -m pytest --tb=short -q
# 10,925 passed, 21 skipped, 348 deselected, 6 warnings in 329.33s
```

That count is retained as historical evidence, not the final baseline.
Postmortem then found a surrendered-target checkpoint regression. After its
repair and two permanent target-transition cases, another candidate run
reported:

```text
UV_CACHE_DIR=/tmp/phase111-uv uv run python -m pytest --tb=short -q
# 10,927 passed, 21 skipped, 348 deselected, 6 warnings in 329.92s
```

The run was again superseded when the same postmortem found the causal
pre-fire restore defect, malformed root-key fallbacks, and missing adversarial
persistence/order proofs. The next candidate default result was:

```text
UV_CACHE_DIR=/tmp/phase111-uv uv run python -m pytest --tb=short -q
# 10,952 passed, 21 skipped, 348 deselected, 6 warnings in 339.87s
```

The cross-document audit then found the missing preceding-milestone lower
bound for an inter-observation resource bridge. After that source repair and
permanent checkpoint case, the next candidate run was:

```text
UV_CACHE_DIR=/tmp/phase111-uv uv run python -m pytest --tb=short -q
# 10,953 passed, 21 skipped, 348 deselected, 6 warnings in 341.37s
```

The final postmortem and repeated simplify gate subsequently found the
terminal-restore and scalar-type defects described below. After both
production repairs and five additional permanent checkpoint cases, the
authoritative final-code run was:

```text
UV_CACHE_DIR=/tmp/phase111-uv uv run python -m pytest --tb=short -q
# 10,958 passed, 21 skipped, 348 deselected, 6 warnings in 345.84s
```

The six warnings are unchanged and unrelated: one empty-chart Matplotlib
legend warning, four unrendered-animation warnings, and one
`datetime.utcnow()` deprecation warning in the Phase 64 planning process.
Skips and deselections are reported rather than counted as passes. The default
configuration excludes API, E2E, slow, benchmark, and terrain markers and
ignores the API/E2E directories.

API and E2E were applicable and run explicitly outside the filesystem sandbox
so their FastAPI/aiosqlite lifespans could exit:

```text
UV_CACHE_DIR=/tmp/phase111-uv uv run python -m pytest tests/api \
  -q --tb=short -o addopts=
# 205 passed in 27.89s

UV_CACHE_DIR=/tmp/phase111-uv uv run python -m pytest tests/e2e \
  -q --tb=short -o addopts=
# 41 passed in 26.57s
```

These are the fresh post-postmortem-repair reruns. The first sandboxed E2E
attempt made no progress in 30 seconds and was
interrupted (exit 130); it is not counted as evidence. Slow, benchmark, and
terrain suites are not applicable because Phase 111 changes no Monte Carlo
acceptance envelope, benchmark contract, terrain dependency/model, or
performance target. Frontend tests/lint/build were not rerun because the
generic event/config rendering contract and frontend source are unchanged; the
last Phase 108 frontend baseline remains 418 passing tests.

The exact static checks were repeated after the postmortem repairs and
documentation refresh:

```text
UV_CACHE_DIR=/tmp/phase111-uv uv run ruff check \
  stochastic_warfare/ api/ tests/ scripts/
# All checks passed!

UV_CACHE_DIR=/tmp/phase111-uv uv run python -m compileall -q \
  stochastic_warfare api tests scripts
# exit 0; no output

git diff --check \
  3c095867d8ef888afd784863e256062d2140d266
# exit 0; no output
```

This is the exact Python Ruff command used by the remote lint workflow. It is
clean; the owner's earlier remote-lint concern is not being waived or replaced
with a narrower check.

## Simplification

`$simplify` first returned `NOT READY` after reproducing a high-severity
checkpoint defect: once a mission completed and released its attachment, one
legitimate later public `WeaponInstance.fire()` made the engine's own
checkpoint unrestorable. The first attempted repair was itself rejected by
fresh-runtime tests (`2 failed, 28 passed in 18.65s`) because it consulted the
fresh engine's current lifecycle rather than the staged lifecycle.

The first in-scope repair derived reservation from staged mission state,
accepted a monotonic trailing fire on an actually released/disabled-plan
attachment, and bounded the transition between the final using impact/release
time and checkpoint elapsed time. Completed and dormant-disabled fresh restore
and continuation passed; future, pre-release, shared-incomplete, and
nonadvancing histories rejected atomically.

Postmortem then proved that rule remained too narrow: at elapsed 55 seconds,
the exact planned M284 could legitimately consume one public `m795_he` round
and record a 55-second fire time, but its engine-generated checkpoint could not
restore while the attachment was still reserved. The old `pending_spent`
negative was therefore not corruption; it described a possible lower-level
resource transition. The next repair validated causally chained external
resource bridges before, between, or after lifecycle observations, using the
latest processed milestone while reserved and the final using impact after
release.

The final postmortem found that the impact-boundary half of that rule was also
not production-correct. The shipped runtime can legally fire the public
`WeaponInstance` at 80 seconds after its scheduled 60-second TOT fire while it
is still reserved from ordinary battle selection. A checkpoint at 80 seconds
restored and continued exactly through the 120-second impact, but the
engine-generated terminal checkpoint at 125 seconds became unrestorable
because completion retroactively changed the same transition's lower bound to
120 seconds. Impact processing takes no weapon-resource observation, so it
cannot establish that boundary. The permanent positive now proves public fire
at 80, exact reserved restore, exact continuation through release, and fresh
terminal restore. Every trailing bridge uses the latest actual
resource-bearing processed milestone instead. Ammunition increases, future or
nonadvancing time, missing fire time, counter mismatch, insufficient
quantity-aware cooldown, and reversed or before-observed shared histories
still reject.

```text
UV_CACHE_DIR=/tmp/phase111-uv uv run python -m pytest -q --tb=short \
  -o addopts= \
  tests/integration/test_phase_111_time_on_target_checkpoint.py
# 45 passed in 28.38s
```

Two repeated narrow independent adversarial reviews historically returned
**ACCEPT** before the final postmortem found the 80-second production state.
Their evidence remains useful but is not closure evidence: one combined
schema/checkpoint matrix passed 44 cases in 17.37 seconds; the later 28-case
selection passed in 17.65 seconds and custom source/fresh probes rejected
bridge times `50` and `59.999` before an observed 60-second milestone while
accepting exact causal `60`/`90` boundaries and a pre-first-milestone
50-second transition.

The repeated `$simplify` review then found the boolean scalar-alias defect
recorded under Postmortem. After its in-scope repair, `$simplify` returned
**READY AFTER IN-SCOPE FIXES** with no remaining high/medium finding:

```text
# Independent simplify selections
# 4 repaired scalar cases passed, 45 deselected in 3.53s
# 7 chronology/authority/reservation cases passed in 5.50s
# scoped Ruff: All checks passed!
# exact phase diff-check: clean
```

The final adversarial rerun returned **ACCEPT**. Its then-current complete
checkpoint module passed 49 cases in 32.18 seconds; a 12-case repaired
scalar/chronology selection passed with 38 deselected in 8.10 seconds.
Supplemental production probes accepted causal shared-attachment fires at
exact 60 and 90 seconds, rejected a forged 59.999-second bridge atomically,
and confirmed boolean/integer/float scalar inequality. The subsequently added
unconfigured COMBAT-mirror permanent proof changed no production code and the
final local checkpoint module passed all 50 cases in 31.88 seconds.

One explicit low/out-of-scope boundary remains. `WeaponInstance.reload()` has
no production caller (`rg -n '\.reload\(' stochastic_warfare` returned none),
and planned-attachment ammunition increases reject because no typed persisted
resupply provenance exists. Accepting arbitrary increases would weaken
checkpoint corruption detection. This is part of the already-open REM-021
Class V authority work, not a hidden REM-012 pass.

## Documentation and cross-document audit

`$update-docs` synchronized the implementation specification, cumulative
checkpoint contract, Block 12 roadmap, remediation record, architecture and
project structure, scenario guide, API reference, devlog index/navigation,
public status pages, and legacy provider context. Phase 111 and REM-012
remained open at that gate until `$postmortem`; the accepted verdict and final
status transition are recorded below.

```text
UV_CACHE_DIR=/tmp/phase111-uv uv run --extra docs mkdocs build --strict
# exit 0; documentation built in 2.61s

git diff --check
# exit 0; no output
```

The final post-repair strict build retained the upstream Material/MkDocs 2.0
compatibility banner, three intentionally unnavigated scenario-template pages,
and seven historical fragment diagnostics already assigned to
REM-022/Phase 112. It reported no new Phase 111 link or build failure.

`$cross-doc-audit` returned **READY for postmortem** after correcting three
stale public claims: both landing-page test/phase badges still showed the Phase
110 baseline, and this devlog named `/api/runs` instead of the exercised
`/api/runs/from-config` endpoint. Its ten-area verdict was:

| Area | Verdict |
|---|---|
| Roadmap/devlog alignment | PASS |
| Remediation traceability | PASS |
| Contract accuracy | PASS |
| Production evidence | PASS |
| Architecture accuracy | PASS |
| API accuracy | PASS |
| Data/catalog accuracy | PASS |
| Public status accuracy | PASS |
| Navigation/links | PASS |
| Provider-context alignment | PASS |

That pre-postmortem auditor independently confirmed the 38 modern plus 14
historical scenario listing, the then-current 132 Phase 111 tests (129 non-API
plus 3 API), status/exclusion claims, REM ownership, event fields/filtering,
module dependency direction, and new navigation. Its strict build exited zero
in 2.53 seconds with the same known diagnostics, and `git diff --check`
remained clean. The count and contract verdict are historical: the audit must
be repeated after the postmortem repairs and the then-current 160-test
(157 non-API plus 3 API) phase inventory.

The final `$cross-doc-audit` returned **READY** after finding and driving the
inter-observation chronology repair. All ten areas passed: roadmap/devlog,
remediation traceability, contract, production evidence, architecture, API,
data/catalog, public status, navigation/links, and provider context. It
independently confirmed the 97/15/45 focused split, 160-test phase inventory,
798-test Block 12 aggregate, 10,953-test canonical result, API/E2E counts,
catalog diagnostics, REM ownership, and closure-pending status. Its fresh
strict build exited zero in 2.69 seconds with only the Material banner, three
intentional nav omissions, and seven REM-022 fragments; exact diff-check
against `3c095867` also exited zero. That verdict predates the final
postmortem's terminal-restore repair and must be repeated before closure.

The renewed final `$cross-doc-audit` returned **READY for postmortem** on the
exact repaired tree. It found one stale public-status defect: README and docs
badge URLs still encoded `10,953` while their prose and tables correctly
reported `10,958`. After both badges were fixed, all ten areas passed. Its
independent fresh evidence was:

- canonical `10,958` passed, 21 skipped, 348 deselected, 6 warnings in
  346.32 seconds;
- `97` schema in 10.57 seconds, `15` production in 7.42 seconds, and `50`
  checkpoint in 33.51 seconds (`162` focused), plus `3` dedicated API in
  1.39 seconds (`165` phase total);
- full API `205` in 26.16 seconds and E2E `41` in 24.61 seconds;
- exact CI Ruff clean;
- data validation `184` unit files, `442/442` catalog keys, `52` scenarios,
  0 errors, 0 validator warnings, and 1 explicit sensorless classification,
  plus the exact 2 REM-024 and 77 REM-023 logger diagnostics; and
- strict documentation exit zero in 2.58 seconds with only the Material
  banner, three known nav omissions, and seven REM-022 fragments; exact
  base diff-check clean.

The auditor confirmed the source/document contract that only the latest
resource-bearing processed milestone bounds a trailing live-resource bridge;
impact/release takes no observation. It also confirmed strict scalar
lifecycle/terminal/RNG comparison, the `803` Block 12 aggregate, REM-012
closure-pending status, and Phase 112 not started. Historical
`160`/`798`/`10,953` evidence is explicitly labeled superseded.

## Postmortem

The first `$postmortem` verdict was **REJECT**. Independent source- and
test-integrity reviewers found two high-severity production defects and
several material proof gaps:

- a completed `target_inactive` mission whose target was surrendered at
  impact could restore a forged active target;
- a causally valid public fire before the first scheduled milestone made the
  engine's own checkpoint unrestorable while the attachment was reserved;
- plausible root spellings such as `timeOnTargetMissions`, `indrect_fire`,
  `totPlan`, malformed `enable_time_*`, `enable_tot`, and `totEnabled` could
  silently select the disabled default, while the first repair falsely
  rejected unrelated `indirect_*` metadata; and
- permanent proof was missing for never-fired sentinel corruption, exact
  same-tick fire-before-impact ordering and disabled-event attribution,
  ambiguous attachment/ammunition resolution, shared-attachment fresh
  continuation, whole-checkpoint multi-round cooldown, and complete
  extra-tick event stability.

The subsequent cross-document audit found one more source/contract mismatch
before accepting its own gate: a resource bridge into a later recorded
milestone was bounded above by that milestone but not below by the previously
observed milestone. A forged shared history could therefore place a fire at
50 seconds after a recorded rejection at 60 seconds. The staged chain now
passes the latest processed time as the lower bound for every
inter-observation bridge; the permanent source-and-fresh corruption case
rejects atomically.

The direct pre-fire reproduction advanced the shipped runtime to 55 seconds,
consumed one `m795_he` round on
`('blue_m109a6_0000', 0, 'm284_155mm')`, recorded fire time `55.0`, and then
failed fresh restore with:

```text
Indirect-fire lifecycle disagrees with live resource history for
('blue_m109a6_0000', 0, 'm284_155mm')
```

The final `$postmortem` candidate was also **REJECTED** after producing a
distinct resource-authority failure. The runtime fired the scheduled M982
round at 60 seconds, then legally consumed one public `m795_he` round and
recorded fire time 80 while the attachment remained reserved until impact at
120. Its 80-second checkpoint restored exactly and source/resumed execution
remained exact through 125 seconds, but a fresh runtime rejected that
engine-generated terminal checkpoint because the validator retroactively
changed the external-fire lower bound from the last resource observation at
60 to release at 120. The permanent replacement test first proved the defect:

```text
UV_CACHE_DIR=/tmp/phase111-uv uv run python -m pytest -q --tb=short \
  -o addopts= \
  tests/integration/test_phase_111_time_on_target_checkpoint.py::test_reserved_external_fire_before_impact_restores_after_release
# 1 failed in 1.44s
# ValueError: External indirect-fire resource transition is impossible
```

The production correction removed the unobservable release-time bound. The
same test now proves exact reserved restore, exact source/resumed continuation,
release, and fresh terminal restore.

The repeated `$simplify` gate then returned **NOT READY** for a separate typed
checkpoint defect. Python scalar equality let `True` masquerade as integer
`1` in lifecycle and terminal round counts, and `False` masquerade as the
integer-zero `has_uint32` field in the indirect COMBAT RNG mirror. All three
source/fresh restore probes were accepted before the repair:

```text
UV_CACHE_DIR=/tmp/phase111-uv uv run python -m pytest -q --tb=short \
  -o addopts= \
  tests/integration/test_phase_111_time_on_target_checkpoint.py \
  -k 'lifecycle_bool_rounds or terminal_bool_rounds or combat_rng_bool_alias'
# 3 failed, 45 deselected in 2.34s
# Each failure: Failed: DID NOT RAISE <class 'ValueError'>
```

Scalar checkpoint equality is now type-aware, both configured and
unconfigured COMBAT-mirror comparisons use it, lifecycle round counts require
non-boolean non-negative integers, and processed times require the exact
finite float schedule representation. Five permanent source/fresh cases cover
the configured lifecycle, terminal, and RNG boolean aliases,
integer-for-float processed time, and the unconfigured RNG mirror:

```text
UV_CACHE_DIR=/tmp/phase111-uv uv run python -m pytest -q --tb=short \
  -o addopts= \
  tests/integration/test_phase_111_time_on_target_checkpoint.py \
  -k 'lifecycle_bool_rounds or lifecycle_int_processed_time or terminal_bool_rounds or combat_rng_bool_alias'
# 4 passed, 45 deselected in 2.87s

UV_CACHE_DIR=/tmp/phase111-uv uv run python -m pytest -q --tb=short \
  -o addopts= \
  tests/integration/test_phase_111_time_on_target_checkpoint.py::test_unconfigured_combat_rng_bool_alias_is_rejected_atomically
# 1 passed in 1.13s

UV_CACHE_DIR=/tmp/phase111-uv uv run python -m pytest -q --tb=short \
  -o addopts= \
  tests/integration/test_phase_111_time_on_target_checkpoint.py
# 50 passed in 31.88s
```

The initial root-key red selections reported `3 failed, 4 passed`, followed by
`1 failed, 7 passed` for `totPlan`; later independent probes reproduced the
three malformed `enable_time_*` forms and the compact enable-TOT family before
their permanent parameters were added.

The repairs now:

- preserve surrendered/destroyed terminal monotonicity while allowing a
  routing target to rally;
- reconcile only causally valid external resource bridges, including the
  reserved pre-fire and scheduled-fire-to-impact cases, using only actual
  resource observations for chronology while retaining exact
  reload/time/counter/cooldown rejection;
- reject scalar type aliases in lifecycle, terminal, and RNG-mirror
  authorities before mutation;
- recognize separator, case, compact TOT, and bounded near-match feature keys
  without broad rejection of unrelated root extensions; and
- add the missing production-path assertions and atomic fresh-runtime
  checkpoint cases.

Fresh post-repair evidence currently includes:

```text
UV_CACHE_DIR=/tmp/phase111-uv uv run python -m pytest -q --tb=short \
  -o addopts= \
  tests/unit/test_phase_111_time_on_target_schema.py \
  tests/integration/test_phase_111_time_on_target_production.py \
  tests/integration/test_phase_111_time_on_target_checkpoint.py
# 162 passed in 44.33s

UV_CACHE_DIR=/tmp/phase111-uv uv run python -m pytest -q --tb=short \
  -o addopts= tests/api/test_phase_111_time_on_target_api.py
# 3 passed in 1.24s
```

Fresh `$simplify` and adversarial reviews now accept the repaired
chronology/type boundary with no remaining high/medium finding.

The renewed final `$postmortem` verdict is **ACCEPT**:

- scope is on target, quality is high, and integration is fully proven;
- declaration, loading, wiring, enabling, exercising, outcome effect, and
  persistence/exposure all have direct production-path evidence;
- every earlier rejection finding has permanent behavioral and fresh-runtime
  coverage;
- no Phase 111-added stub, proxy, dummy value, placeholder, `TODO`/`FIXME`,
  swallowed exception, unconditional success, or fallback remains;
- the obsolete stateless time-on-target APIs are removed; and
- no new deficit or closure blocker was found.

The exact final adversarial command covering every prior rejection family was:

```text
UV_CACHE_DIR=/tmp/phase111-uv uv run python -m pytest -q --tb=short \
  -o addopts= \
  tests/unit/test_phase_111_time_on_target_schema.py \
  tests/integration/test_phase_111_time_on_target_production.py \
  tests/integration/test_phase_111_time_on_target_checkpoint.py \
  -k 'root_rejects_indirect_fire_typos or unrelated_historical_root_metadata or real_scenario_executes_two_battery or disabled_populated_and_empty or battle_reserves_only_exact_attachment or shared_attachment_releases_only_after_every_mission or runtime_rejections_are_terminal_ordered or reserved_external_fire_checkpoint_round_trip or reserved_external_fire_before_impact or surrendered_terminal_target or shared_attachment_rejects_bridge_before_observed_milestone or shared_attachment_fresh_checkpoint_continuation or quantity_aware_cooldown_is_enforced_by_whole_checkpoint or corrupt_tot_authorities or unconfigured_combat_rng_bool_alias'
# 53 passed, 109 deselected in 20.14s
```

The exact final legacy indirect-fire compatibility selection was:

```text
UV_CACHE_DIR=/tmp/phase111-uv uv run python -m pytest -q --tb=short \
  -o addopts= \
  tests/unit/combat/test_indirect_fire.py \
  tests/unit/test_phase_27b_engagement.py \
  tests/unit/test_phase43_domain_resolution.py \
  tests/unit/test_phase48_deficit_fixes.py \
  tests/unit/test_phase_68e_fire_damage.py
# 151 passed in 1.29s
```

The accepted residuals remain explicitly owned by REM-017, REM-021, REM-022,
REM-023, REM-024, and REM-025. Time on target intentionally shares the COMBAT
stream, and cross-NumPy/cross-architecture bit identity is not claimed.
Phase 111 is complete and REM-012 is closed; Phase 112 is next and has not
started.

The post-transition `$cross-doc-audit` returned **READY**. Every current public,
provider, roadmap, devlog, specification, and remediation surface agrees on
Phase 111 Complete, REM-012 Closed, Phase 112 next/not started, 165 phase tests
(`162 + 3`), 803 Block 12 tests, and the 10,958 canonical baseline. Historical
closure-pending passages above are explicitly bounded to their prior gates.

```text
UV_CACHE_DIR=/tmp/phase111-uv uv run --extra docs mkdocs build --strict
# exit 0; documentation built in 2.60s
# Material banner; 3 known nav omissions; 7 REM-022 fragments

git diff --check \
  3c095867d8ef888afd784863e256062d2140d266
# exit 0; no output
```

At the status audit, `HEAD` and `origin/main` were both
`3c095867d8ef888afd784863e256062d2140d266`; the coherent Phase 111 tree was
still uncommitted and no unrelated status entry was present.
