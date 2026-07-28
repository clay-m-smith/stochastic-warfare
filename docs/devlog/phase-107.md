# Phase 107 - Scenario Configuration Wiring

**Status:** Complete

**Started:** 2026-07-28

**Completed:** 2026-07-28

## Why this phase exists

The post-Phase-104 audit found four production gaps hidden by schema-only tests,
manual test setup, or metadata assertions: loaded reinforcement schedules never
reach the engine, arriving units have no live loadout, side initial morale is
discarded, and era feature gates are not consulted.

## Authoritative contract

REM-004 through REM-007 in
[`docs/remediation-backlog.md`](../remediation-backlog.md) define the detailed
requirements, persistence boundaries, and non-goals.

Acceptance criteria:

1. The production engine registers a scenario schedule exactly once and admits
   due waves at every resolution using stable, collision-free ordering.
2. A wave commits atomically with the same live weapon, ammunition, sensor, and
   side-morale construction as an initial unit, then can affect a real battle.
3. Dynamic units and attachments survive fresh-runtime checkpoint continuation
   exactly and do not arrive twice.
4. Initial morale is validated against the runtime enum, seeds both morale
   stores, reaches public state, and changes a controlled morale outcome.
5. Era and feature names are strict; whole-suite and capability gates prevent
   contradictory or forbidden runtime objects through the production loader.
6. Same-seed runs preserve schedule ordering, RNG stream discipline, complete
   state, and ordered events.

## Non-goals

- No scenario calibration, force-composition, timing, or weapon-performance
  tuning.
- No change from the existing ordered log-normal reinforcement timing model to
  a Poisson process.
- No semantic cleanup of equipment-name mappings; that is Phase 109.
- No logistics initialization, ASAT integration, time-on-target execution, or
  aggregation constituent repair.
- No fabricated morale-transition event for an initial condition.

## Production traces

### Reinforcement path

Scenario YAML -> `CampaignScenarioConfig.reinforcements` ->
`ScenarioLoader` -> `SimulationContext.config` -> `SimulationEngine` ->
`CampaignManager` schedule -> logical-time due check -> atomic dynamic-unit
registration -> campaign roster -> `BattleManager` -> event/checkpoint output.

### Morale path

Scenario side -> validated runtime morale name -> initial/dynamic unit
registration -> `SimulationContext.morale_states` plus
`MoraleStateMachine` -> battle/auto-resolve/victory -> checkpoint/API frame.

### Era-gate path

Scenario `era` -> strict registered `EraConfig` -> one effective context gate ->
optional suite construction and loadout validation -> engine None-checks,
battle consumers, checkpoint state, and era metadata API.

## Baseline evidence

- A loaded `test_campaign` declares a reinforcement wave while a newly
  constructed engine has zero registered entries and adds no units.
- Manually spawned M1A2 reinforcements contain equipment but have neither a
  weapon-map nor sensor-map entry.
- Two blue M1A2 waves produce duplicate entity IDs.
- Goose Green declares red `SHAKEN`; the context initializes all units steady
  and the morale machine initializes none.
- `disabled_modules` is assigned to an unused local variable; unknown module
  and era names are accepted, and all capability gates are dead metadata.

The dedicated baseline produced:

- `tests/unit/test_phase_107_scenario_wiring.py`: 14 failures, covering
  automatic scheduling at three resolutions, stable IDs/loadouts, validation
  and atomic rollback, initial and reinforcement morale, morale victory, and
  fresh dynamic-loadout checkpoint continuation.
- `tests/unit/test_phase_107_era_gates.py`: 15 failures and 6 negative-control
  passes, covering strict names, registry isolation, optional-suite precedence,
  GPS child gating, loadout capability rejection, sensor allowlists, and
  effective-gate checkpoint compatibility.

Both files passed focused Ruff. All 29 failures reproduced a declared Phase 107
requirement before the corresponding production implementation began.

### Phase-start scenario baseline

Production code and data were recorded at phase-start revision
`540adf60520859b1a8d79112a2455c47f4f73582`. The evaluator matched each
requested scenario exactly and completed seeds 42, 43, and 44:

| Scenario | Seed | Winner / condition | Ticks | Casualties | Engagements | Diagnostics |
|---|---:|---|---:|---:|---:|---|
| `falklands_goose_green` | 42 | blue / `force_destroyed` | 6,113 | 2 | 50 | None |
| `falklands_goose_green` | 43 | blue / `force_destroyed` | 6,110 | 3 | 33 | None |
| `falklands_goose_green` | 44 | blue / `force_destroyed` | 6,110 | 3 | 33 | `CENTROID_COLLAPSE_red` |
| `golan_campaign` | 42 | blue / `force_destroyed` | 184 | 85 | 559 | None |
| `golan_campaign` | 43 | blue / `force_destroyed` | 182 | 84 | 556 | None |
| `golan_campaign` | 44 | blue / `force_destroyed` | 192 | 88 | 627 | None |

Command pattern:

```powershell
uv run python scripts/evaluate_scenarios.py --scenario <scenario> `
  --output C:\tmp\phase107-baseline-<scenario>-s<seed>.json `
  --no-details --seed <seed>
```

At the phase-start revision, the evaluator manually registered reinforcements
and therefore masked REM-004; these results are semantic phase-start evidence
only. Focused production-engine tests must prove automatic registration. The
evaluator also bypasses API execution and reads recorder internals, so neither
boundary is inferred from these results.

## Verification plan

- Dedicated Phase 107 red/green production tests.
- Existing scenario, campaign, engine, morale, era, checkpoint, API-frame, and
  historical-era selections.
- Production scenario evaluation for reinforcement campaigns and Goose Green,
  classified against stored phase-start evidence.
- Determinism audit covering same-seed replay, arrival ordering, stochastic
  schedule state, and before/after-arrival checkpoint continuation.
- Data validation for every built-in era/scenario catalog touched by the gate.
- Conventions, simplify, strict documentation, cross-document, and postmortem
  gates before the phase commit.

## Resolved implementation decisions

- `build_unit_loadouts()` is the one scenario-runtime entry point for initial,
  arriving, and checkpoint-reconstructed units. It currently delegates catalog
  name resolution to the existing private validation-runner helpers; moving
  that ownership into a production module is explicitly assigned to
  REM-010/Phase 109.
- Campaign state and force topology are staged and cross-checked before context
  restore can mutate the clock, RNG, roster, morale, or live loadouts.
- Optional suite flags and era ceilings are evaluated before allocating the
  suite's RNG stream.
- Reinforcement `overrides` remain an untyped dictionary in the legacy model.
  Phase 107 rejects every non-empty value at schema and runtime boundaries
  rather than claiming support for fields with no defined merge semantics.
- Battle discovery requires a caller-supplied logical `timestamp`; removing the
  wall-clock fallback is an intentional internal API change required for exact
  event replay.

## What changed

### Strict scenario and era inputs

- `ReinforcementUnitConfig`, `ReinforcementConfig`, and `SideConfig` reject
  unknown fields.
- Reinforcement counts, times, timing spread, and positions are validated
  before engine construction; referenced sides and unit types must exist.
- `morale_initial` accepts exactly `STEADY`, `SHAKEN`, `BROKEN`, `ROUTED`, or
  `SURRENDERED`. The historical validation schema and frontend editor type use
  the same vocabulary.
- Scenario eras must resolve through the registry. `EraConfig` rejects unknown
  fields and disabled-feature names, returns isolated copies, and serializes
  unordered sets canonically.

### Automatic atomic reinforcements

- `SimulationEngine` installs the loaded schedule once during construction and
  checks it before each engine tick at strategic, operational, and tactical
  resolution.
- Ordered log-normal timing remains on the `CORE` stream. Unit creation remains
  on `ENTITIES`; failed sampling or wave registration restores the applicable
  RNG state.
- Entity IDs include the stable wave ordinal and within-wave ordinal. Two
  same-side, same-type waves cannot collide.
- A due wave stages its full roster, live loadouts, morale, and machine state,
  then commits all maps before publishing one arrival event. Any failure leaves
  the wave pending and the live runtime unchanged.
- The evaluation harness no longer installs a private schedule, so it cannot
  mask a missing production registration.

### Exact live loadouts

- Initial units, arriving units, and reconstructed checkpoint units use the
  same production loadout entry point.
- Every dynamic weapon and sensor is linked to the arriving unit's own
  equipment object. Weapon/ammunition and sensor maps preserve an independent
  key for every stable entity ID.
- A real dynamically arrived M1A2 detects and fires through
  `BattleManager`, consuming ammunition; constructor or map presence is not the
  acceptance proof.

### Typed initial morale

- Scenario loading seeds both `SimulationContext.morale_states` and
  `MoraleStateMachine` without RNG or a fabricated transition.
- Dynamic registration uses the same side-derived value. Initial
  `ROUTED`/`SURRENDERED` values synchronize unit status.
- `UnitMoraleState` and machine checkpoint restore validate finite numeric
  state and stage the full replacement before mutation.

### Effective era gates

- EW, space, and CBRN suites require both an explicit true enable flag and era
  permission. Missing and false controls leave the suite absent; contradictory
  explicit enablement fails loading.
- The GPS capability gate removes the GPS child without removing the permitted
  rest of the space suite.
- Thermal sight, PGM, data-link, and sensor-type constraints are enforced at
  loadout construction before a forbidden runtime object is committed.
- The complete effective era configuration is checkpointed and compared on
  restore.

### Dynamic checkpoint continuation

- Engine checkpoints carry format version `107`. Unsupported explicit versions
  (including explicit `null`) fail before mutation; only a checkpoint with no
  version key enters bounded legacy migration.
- Version 107 requires exact engine/context key topology and type-aware
  configuration equality. Missing, extra, boolean-as-integer, null, and
  incompatible-runtime shapes fail before Phase 107 state can mutate.
- Current campaign state contains the exact wave config, stable ordinal,
  sampled arrival time, arrived state, and any temporary legacy-ID mode.
- Campaign arrival flags are checked in both directions against exact side/type
  roster topology, including constituents captured inside an aggregate.
- Fresh restore rebuilds dynamic loadout topology without an RNG draw and then
  applies exact mutable equipment, weapon, ammunition, sensor, and morale
  state.
- Current production checkpoints require both morale keys and complete,
  agreeing context/machine topology. Minimal engine runtimes without a machine
  write the engine-format key as `null` while direct context snapshots retain
  legacy omission behavior. Versionless checkpoints may backfill only missing
  entries from the validated roster/side configuration; present invalid or
  divergent values still fail.

### Analysis helper compatibility

Strict reinforcement validation exposed a separate false-green analysis defect:
`run_scenario_batch()` inferred `data/scenarios` instead of the repository data
root, so unit catalogs were empty. The helper now walks to the `scenarios`
ancestor and uses its parent, while nonstandard layouts must pass `data_dir`.
This closes only that independent slice of REM-017; empty-roster and
unsupported-metric rejection remain Phase 112.

## Adversarial and simplify review

The reviews found and drove fixes for:

- duplicate same-type wave IDs and partial-wave/RNG mutation;
- dynamic loadout and morale topology omitted from fresh restore;
- schedule/roster arrival flags that could disagree;
- non-empty reinforcement overrides that were parsed but not defined;
- two morale stores that could be missing or disagree inside a claimed current
  checkpoint;
- explicit v107 campaign entries that could still use the legacy shape;
- explicit `null`, omitted/extra keys, and bool/number coercion that could
  masquerade as valid current-format checkpoint state;
- aggregate constituents omitted from reinforcement-arrival validation;
- wall-clock/dummy fallbacks in battle discovery and reinforcement arrival
  events;
- compatibility regressions in minimal historical engine fixtures and API
  analysis loading.

The final simplify classification is **ready after in-scope fixes**. The shared
loadout entry point's dependency on private `ScenarioRunner` mapping helpers is
not papered over; it is part of REM-010/Phase 109.

## Residual boundaries

- Static catalog validation reports 22 unmapped equipment names and two
  no-sensor warnings. Phase 107 makes no semantic substitutions; REM-010/Phase
  109 owns centralized mapping and catalog cleanup.
- Repository-wide Ruff remains red on the six duplicate mapping keys assigned
  to REM-010 and two pre-existing no-placeholder f-strings in validation tests.
  Every Phase 107 Python file is green; the clean global lint baseline is
  tracked under REM-013/Phase 112.
- Aggregation/disaggregation still reconstructs base units without exact live
  attachment topology (REM-016).
- Later rout-cascade and aggregation paths can mutate the context and machine
  morale views independently (REM-019/Phase 113). Phase 107 guarantees their
  initialization, dynamic registration, and checkpoint agreement, not a
  completed ownership redesign.
- `physics_overrides` and `tick_resolution_overrides` remain unconsumed metadata
  (REM-018/Phase 114).
- The simplified validation runner still initializes its own runs as
  `STEADY`; authoritative `ScenarioLoader` behavior is the Phase 107 contract.

## Determinism and scenario evaluation

The `$audit-determinism` route classified the final implementation
**deterministic**:

- schedule sampling uses only `CORE`; unit construction uses only `ENTITIES`;
  both restore their stream state on a failed staged operation;
- stable declaration/wave ordering drives IDs, roster insertion, loadout maps,
  and events;
- battle creation and reinforcement events receive logical simulation time;
- same-seed full state, ordered events, checkpoint bytes, and continuation
  match;
- independent processes with `PYTHONHASHSEED=1` and `2` produced the same
  checkpoint SHA-256:
  `d020f39273253bd42a453edcdbd4750c1f61e330bfd79abeb1f81d39c1596bcf`.

The current production evaluator repeated
`falklands_goose_green` and `golan_campaign` for seeds 42--44. Winner,
condition, ticks, casualties, engagements, and diagnostics matched every
phase-start row above exactly. The `$evaluate-scenarios` classification is
**unchanged**; no baseline was promoted and no calibration or scenario data
was changed.

## Verification evidence

- Dedicated Phase 107 suite: **103 passed**.
- Final reinforcement/era/logical-time focused selection: **112 passed**.
- Checkpoint/engine compatibility selection after adversarial repairs:
  **392 passed**.
- Complete non-slow API suite: **200 passed**.
- Fresh default-selected backend suite: **10,279 passed, 21 skipped, 346
  deselected**, with no failures or errors.
- Frontend Vitest: **79 files / 418 tests passed**.
- Frontend ESLint: **0 errors, 4 pre-existing warnings**.
- Frontend production build: **passed** (419 modules; existing large-chunk
  warning).
- Scoped Ruff across every changed Python file: **passed**.
- Strict MkDocs build: **passed**; existing informational notices for
  intentionally unnaved pages and historical broken devlog anchors remain.
- `git diff --check`: **passed**; Git reports only line-ending conversion
  notices.
- Static data validation completed all 184 unit files and 51 scenario loader
  checks, then exited red with the already tracked **22 mapping errors and 2
  no-sensor warnings** assigned to REM-010/Phase 109.

Repository-wide Ruff was also run and honestly remains red on eight pre-existing
findings: six duplicate mapping keys assigned to REM-010 and two redundant
f-strings assigned to REM-013. The Phase 107 diff itself is green.

The default suite excludes `slow`, `benchmark`, `terrain`, `api`, and `e2e`.
API was explicitly included because the scenario loader and analysis helper are
in scope. E2E was not required because no HTTP/UI workflow changed; the
frontend type, tests, lint, and production build cover the editor boundary.
Slow, benchmark, and terrain selections were not applicable because this phase
changes neither performance contracts nor terrain behavior.

## Postmortem

**Verdict:** Passed on 2026-07-28.

- **Scope:** On target. REM-004 through REM-007 are delivered. Adversarial
  findings about atomic wave admission, stable IDs, logical timestamps, exact
  dynamic topology, strict current-checkpoint shapes, and bounded legacy
  migration were resolved because they are necessary parts of the declared
  runtime-wiring contract.
- **Quality:** High. The simplify review classified the result as ready after
  its in-scope fixes. Dedicated, compatibility, API, default, frontend,
  deterministic, documentation, and scoped-lint gates are green.
- **Integration:** Proven through `ScenarioLoader`, `SimulationEngine`,
  `CampaignManager`, the production battle path, live weapon/sensor/ammunition
  objects, both morale views, recorder events, public state, and fresh-runtime
  checkpoint continuation.
- **New deficits:** REM-018 records the independently unconsumed era override
  dictionaries and REM-019 records later-path two-store morale divergence.
  Strict reinforcement loading also repaired the data-root slice of REM-017;
  its remaining analysis-trust requirements stay assigned to Phase 112.
- **Action items before closure:** None. REM-010's centralized loadout mapping,
  REM-013's global validation baseline, REM-016's aggregation reconstruction,
  and the new deficits above remain visible, independently assigned work.

### Contract reconciliation

All six acceptance criteria were delivered without tuning scenarios, force
composition, arrival distributions, morale probabilities, or physical weapon
performance. The engine owns one schedule; waves are stable and atomic; initial
and dynamic units share live loadout and typed morale construction; effective
era gates reject contradictory engines and capabilities before commitment; and
current checkpoints preserve the complete dynamic contract exactly.

No planned requirement was dropped. The shared loadout builder intentionally
preserves the current mapping semantics rather than concealing REM-010, and the
validation runner's simplified morale initialization remains distinct from the
authoritative production loader.

### Completion evidence matrix

| Capability | Declared | Loaded | Wired | Enabled | Exercised | Outcome | Persisted/exposed |
|---|---|---|---|---|---|---|---|
| REM-004 automatic reinforcement schedule | Yes | Yes | Yes | N/A -- required runtime path | Yes | Yes | Yes |
| REM-005 dynamic live loadout | Yes | Yes | Yes | N/A -- required runtime path | Yes | Yes | Yes |
| REM-006 side initial morale | Yes | Yes | Yes | N/A -- required runtime path | Yes | Yes | Yes |
| REM-007 effective era gates | Yes | Yes | Yes | Yes | Yes | Yes | Yes |

### Final validation

- The fresh default-selected backend suite passed **10,279 tests**, with 21
  skipped, 346 deselected, no failures or errors, and six established warnings.
- Phase-specific, focused, compatibility, and complete non-slow API selections
  passed **103**, **112**, **392**, and **200** tests respectively.
- Frontend tests passed **79 files / 418 tests**; production build passed; lint
  reported zero errors and four unchanged warnings.
- Same-seed complete state, event order, checkpoint bytes, and continuation
  matched. Independent hash-seed processes produced the same checkpoint digest.
- Goose Green and Golan seeds 42--44 matched the recorded phase-start semantic
  rows exactly and were classified **unchanged**.
- Scoped Ruff, strict MkDocs, and `git diff --check` passed. Repository-wide
  Ruff and static catalog validation remain honestly red only on the findings
  assigned to REM-010 and REM-013.

The independent adversarial review found no remaining current-v107 or bounded
legacy-compatibility blocker. The final cross-document audit reconciled public
counts, status, era-gate descriptions, checkpoint semantics, roadmap ranges,
and the newly recorded residuals.
