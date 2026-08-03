# Validation and Documentation Trust

**Status:** Verified - Phase 112 complete

**Owners:** REM-013, REM-014, REM-017, REM-022, REM-023, REM-024,
REM-025, REM-026, and REM-027

**Preserved closure:** REM-015

> **Subsequent status:** Phase 116 promoted the clean Phase 115 73 Easting
> endpoint to the ordinary version-4 paired gate and implemented exact nonempty
> ordinary-contact continuation; its accepted postmortem closed REM-029.
> Phase 112's empty-world-view Space ISR fixtures and the historical future-work
> statements below remain scoped evidence rather than current limitations.

## Purpose and scope

Phase 112 makes repository validation claims fail closed. A green command,
scenario evaluation, analysis result, benchmark result, or documentation build
must not conceal an excluded suite, a structural-only assertion, an invalid
roster, an unsupported metric, a missing commander profile, a dropped unit, a
legitimate movement hold, a stale performance workload, a broken fragment
target, or an untyped checkpoint report.

The affected production and delivery boundaries are:

1. pytest collection, local suite commands, and GitHub Actions;
2. behavioral-test evidence classification;
3. sensitivity, comparison, doctrine, MCP, and HTTP analysis runs;
4. commander-profile loading and assignment;
5. unit-definition and initial-force construction;
6. movement diagnostic production and scenario evaluation;
7. scenario performance comparison and its stored artifacts;
8. Space ISR report generation, delayed delivery, intelligence fusion, and
   checkpoint continuation; and
9. MkDocs link validation and public capability/status claims.

This is one integrity phase, not a collection of cosmetic cleanups. Each
workstream must reject invalid input at its authoritative boundary and must
have fresh production-path evidence before its remediation item closes.

## Requirements

### Explicit Python suite contract

One locked superset collection environment installs the `dev`, `api`, and
`terrain` extras and divides all collected tests into six disjoint
partitions:

- `standard`: backend tests that are neither `slow` nor `benchmark`, excluding
  the `tests/api` and `tests/e2e` path boundaries;
- `slow-only`: backend tests marked `slow and not benchmark`, explicitly
  excluding `tests/api` and `tests/e2e`;
- `benchmark-only`: backend tests marked `benchmark and not slow`, explicitly
  excluding `tests/api` and `tests/e2e`;
- `slow-benchmark`: backend tests marked both `slow and benchmark`, explicitly
  excluding `tests/api` and `tests/e2e`; and
- the explicit `tests/api` and `tests/e2e` path suites.

The first three marker expressions after `standard` are intentionally listed
separately so marker overlap is visible rather than double-counted. The
standard, three marker, API, and E2E node-ID sets must form the exact union of
all tests collected in the locked superset environment. A repository audit
derives and compares the node-ID sets; it may report current counts but may not
encode a count as the coverage oracle.

At the Phase 112 start revision the superset evidence is 10,978 standard,
314 slow-only, 16 benchmark-only, 18 slow-benchmark, 205 API, and 41 E2E
nodes, for an exact 11,572-node union. These counts are recorded baseline
facts, not fixed acceptance values.

`terrain` is an environment/dependency boundary, not a phantom pytest marker.
The zero-selecting `terrain` marker and default exclusion are removed. A clean
terrain job installs `uv sync --locked --extra dev --extra terrain` and runs
exactly:

- `tests/unit/test_phase_15a_pipeline_heightmap.py`;
- `tests/unit/test_phase_15b_classification_infrastructure.py`;
- `tests/unit/test_phase_15c_bathymetry.py`; and
- `tests/unit/test_phase_15d_integration.py`.

Those tests may overlap the standard node-ID set; their separate claim is that
optional terrain dependencies are installed and the import-skipped paths are
actually exercised. At the phase start these four files collect 62 nodes, but
that count is reported evidence rather than a permanent oracle.

CI enforces this cadence:

- repository-wide Ruff, standard backend, complete API path, complete E2E
  path, terrain dependency profile, and strict documentation on every pull
  request and push to `main`;
- the refactored `slow-only`, `benchmark-only`, and `slow-benchmark`
  partitions on a declared weekly schedule and manual dispatch, sharded with
  measured job timeouts that do not conceal a timeout as a skip; and
- the routine 73 Easting benchmark workflow on every pull request and push,
  using the ordinary paired performance gate when its workload identity is
  stable and the strict non-timing transition path during a reviewed workload
  handoff; the paired Golan gate remains available only through an explicit
  long-running manual dispatch.

Every job prints its exact collection/pass/skip/deselect/warning counts and
the command used. Machine-readable results and benchmark data upload under
`if: always()` so failed evidence is retained. No job treats "no tests
collected", a missing scenario, missing optional dependency, or a missing
performance reference as success.
Workflow concurrency may cancel stale runs, but no required partition is
conditionally omitted within a completed run.

Developer documentation names each command, dependency profile, overlap, and
cadence. Repository-wide Python lint remains:

`ruff check stochastic_warfare api tests scripts`

Narrow changed-file lint is useful during implementation but cannot support
the Phase 112 Ruff claim.

### Behavioral evidence classification

A test is structural when its strongest oracle is a source/AST search, import,
signature or constructor check, mock-call existence, log/no-crash observation,
or shape-only assertion that does not demonstrate the named behavior.
Structural checks remain useful diagnostics but cannot support a capability,
integration, production-wiring, outcome, closure, or phase-exit claim.

The repository defines a `structural` marker and maintains two
machine-checked current-state ledgers:

1. every collected test whose body has no direct behavioral oracle; and
2. every structural or weak-oracle test, whether or not it contains an
   `assert`, including source/AST/string searches, mock-call existence,
   import/constructor/signature checks, shape-only checks, and non-null
   assertions.

The syntactic weak-oracle scan is a review queue, not an authority that may
silently label a test structural. Every heuristic candidate is partitioned
exactly once between the reviewed weak-oracle ledger and a separate reviewed
behavioral-oracle exclusion ledger. An exclusion names the stronger
production behavior and explains why the syntactic hit is secondary. Only
entries explicitly classified `structural_only` receive the marker. The
generator preserves reviewed classifications, strongest-oracle descriptions,
and rationales; it fails on a new, stale, overlapping, or unreviewed candidate
instead of overwriting review text.

Each ledger entry is classified as exactly one of:

- `helper_assertion`: a traced helper or fixture contains the real oracle;
- `exception_contract`: `pytest.raises`, `pytest.warns`, or an explicit
  fail-if-not-raised sentinel is the oracle;
- `invariant_only`: successful completion is the explicitly named
  non-behavioral structural invariant; a no-raise contract becomes behavioral
  only when it also has an observable postcondition and a failing negative
  control;
- `structural_only`: the test is marked `structural` and named/documented as a
  structural diagnostic.

The phase-start AST triage identifies 105 tests with no direct signal. That is
a review queue and reported baseline, not a permanent count oracle or a claim
that tests outside it are behavioral.

The ledgers record exact collected node IDs, classification, strongest oracle,
and short rationale. Collection fails if an inventoried node ID disappears
without review or a new heuristic match is unclassified. A separate historical
Phase 112 remediation ledger records renamed, removed, and
`repaired_behavioral` phase-start nodes with their final behavioral proof.
Once repaired, a test does not remain falsely listed as a current no-oracle
test. The audit traces helper assertions; the string `assert` inside a called
helper is not sufficient by itself.

Tests whose names or docstrings claim integration, wiring, consumption,
execution, production behavior, outcome, closure, or exit evidence must either
be repaired with a production behavioral oracle or renamed and marked
structural. At minimum, Phase 112 reviews and repairs or honestly reclassifies
the following current high-risk tests:

- `tests/api/test_concurrency.py::test_batch_semaphore_limits_concurrency`;
- `tests/integration/test_phase1_integration.py::TestFullTerrainStack::`
  `test_coordinate_consistency`;
- `tests/unit/test_phase_12a_c2_depth.py::TestNetworkDegradation::`
  `test_mid_load_increases_latency`;
- `tests/unit/test_phase_17c_isr_ew.py::TestISROverpass::test_timing_gap`;
- `tests/unit/test_phase50_combat_fidelity.py::TestAirPosture::`
  `test_on_station_aircraft_engages`;
- `tests/unit/test_phase_27c_naval.py::TestNavalGun::test_event_published`;
- `tests/unit/test_phase_64d_stratagem_activation.py::`
  `TestStratagemConcentration::test_activate_stratagem_called`;
- `tests/unit/test_phase78_structural.py::TestFatigueTemperatureStress::`
  `test_parameter_accepted`;
- `tests/unit/test_phase87_morale_jit.py::TestMoraleEngineIntegration::`
  `test_check_transition_uses_kernel`;
- `tests/unit/test_phase87_morale_jit.py::TestMoraleEngineIntegration::`
  `test_continuous_mode_uses_kernel`;
- `tests/unit/test_simulation_engine.py::TestStrategicTick::`
  `test_strategic_runs_campaign_update`; and
- `tests/unit/test_simulation_engine.py::TestEdgeCases::`
  `test_multiple_battles_simultaneously`.

Existing structural clusters, including calibration coverage, Phases 60-67,
Phase 78, the structural audit, deficit closure, and Block 8 exit checks, are
audited under the same rule. Phase 112 does not delete useful structural
checks merely to reduce the inventory.

### Strict analysis execution and metrics

One typed analysis-run boundary owns scenario loading for sensitivity,
comparison, doctrine comparison, MCP tools, and HTTP analysis endpoints. It
accepts:

- an exact scenario path and explicit or safely inferred data root;
- a strictly positive iteration count;
- a non-negative strict-integer base seed and the exact sequence
  `base_seed + iteration_index`;
- a strictly positive maximum tick count;
- one typed sparse `CalibrationSchema` patch per requested variant; and
- a non-empty, duplicate-free ordered metric list.

Numeric configuration rejects booleans, strings, NaN, and infinity. Sweep
values are finite, non-empty, and duplicate-free. Sweep and comparison require
at least two iterations so sample standard deviation is observed rather than
fabricated as zero. Comparison `alpha` is a strict finite float in `(0, 1)`.
Unknown calibration keys, empty result vectors, partial runs, and missing
scenario data fail before an authoritative result is returned.

One simulation-layer `SimulationRuntimeFactory` is the authoritative runtime
construction boundary for every consumer that claims production
`SimulationEngine` execution, including analysis, API run management, MCP,
campaign validation, and benchmarks. The deliberately simplified
`validation.scenario_runner` remains a non-production diagnostic and cannot
support production behavior evidence.

`SimulationRuntimeFactory.prepare(path, data_root, variants)` reads and
validates the source YAML exactly once per analysis request. Each strict
`AnalysisVariant` contains one sparse calibration patch and an optional
`DoctrineAnalysisVariant`. The call returns an immutable `PreparedScenario`
containing the source configuration/fingerprint and independently validated
effective typed configurations. Each sparse variant is applied through
`load_campaign_scenario_config(..., calibration_overrides=...)` against the
same source; variants never reread, shallow-merge, or cumulatively mutate a
prior variant.

`PreparedScenario.build(variant, seed, max_ticks, recorder=None)` deep-copies
and revalidates the selected `CampaignScenarioConfig`, supplies that exact
typed configuration to `ScenarioLoader`, and returns a fresh `RuntimeSession`
containing the context, production `VictoryEvaluator`, and
`SimulationEngine`. Every iteration calls `build`; no mutable context, engine,
evaluator, recorder, subsystem, or RNG is reused across seeds or variants.
Consumers may own batch orchestration and recording, but they do not write a
temporary YAML file, silently filter keys, or independently reinterpret
objectives and victory conditions.

`RuntimeSession.run_to_completion()` returns the immutable public
`SimulationRunResult`. Progress/cancellation consumers instead call `step()`
and, only after `step()` reports an authored or engine terminal condition,
`finalize()`. `finalize()` returns the same result contract as
`run_to_completion`; cancellation, local loop exhaustion, and failure produce
no authoritative result. No consumer reads `_last_victory` or another private
engine field.

The loaded initial roster must match the exact authored per-side cardinality
and contain unique unit IDs. Every requested metric is resolved against the
exact loaded side IDs before the first iteration:

- `<exact-side>_active`;
- `<exact-side>_destroyed`;
- `win_<exact-side>`;
- `ticks_executed`; and
- `exchange_ratio` only when the scenario has exact `blue` and `red` sides,
  defined as red destroyed divided by `max(1, blue destroyed)`.

Prefix matching, substring winner matching, implicit blue/red aliases, and an
unknown-to-zero fallback are forbidden. Win metrics use the public
`SimulationRunResult.victory_result`, not a private engine attribute. Every
metric vector has exactly the requested iteration count, contains only finite
values, and is accessed by an exact key. Sweep statistics and plots reject a
missing vector instead of inserting `[0.0]` or plotting a zero.

The result exposes scenario/config fingerprints, data root, ordered metrics,
base seed, exact seed sequence, maximum ticks, authored and loaded per-side
rosters, per-run completion/victory metadata, and raw metric vectors. This
provenance flows unchanged through Python, MCP, and HTTP serializers.

Because A and B use the same ordered seeds, comparison is paired. For each
metric and seed, define:

`d_i = metric_b_i - metric_a_i`

Phase 112 uses the two-sided exact paired sign test of Dixon and Mood. Define
`N_total` as all seed pairs and `N_nonzero` as positive plus negative
differences. Ties are exposed and excluded from the binomial trial count.
The null is that non-zero signs are balanced, not equality of means. Positive
and negative counts are tested against `p = 0.5`; when `N_nonzero == 0`, the
exact p-value is `1.0`. When more than one metric is requested, Holm's
step-down procedure orders by `(raw_p_value, original_metric_index)`, computes
monotone adjusted p-values capped at one, and controls family-wise error at the
request's `alpha`.

Results expose `N_total`, `N_nonzero`, positive, negative, and tied counts,
mean and median paired difference, paired superiority
`(positive + 0.5 * ties) / N_total`, raw and Holm-adjusted p-values, alpha, and
family-wise significance. This choice makes no normality or
symmetric-magnitude assumption and remains valid for discrete casualty
counts, at the acknowledged cost of lower power because it ignores non-zero
magnitudes in the hypothesis test. The current unpaired Mann-Whitney statistic
and rank-biserial field are removed from the paired claim.

A public terminal result with `condition_type="max_ticks"` is complete and its
force-advantage winner may populate win metrics. Reaching a local consumer
loop limit without that public terminal result is censored and rejects win
metrics. The result preserves the exact condition type so a force-advantage
decision at the tick boundary is not confused with an authored victory
condition.

FastAPI passes its resolved `data_dir` into the boundary. Missing scenarios
remain HTTP 404; typed request, metric, override, roster, and analysis
validation errors are HTTP 422; an unexpected runtime failure is not relabeled
as a valid zero result. API requests and responses expose metrics and base
seed. Both `/api/analysis/*` and the web UI's primary `/api/runs/batch`
consumer use the same runner, retain exact raw vectors/provenance, and do not
keep a second Monte Carlo implementation. MCP `run_scenario`,
`run_monte_carlo`, and `modify_parameter` use the same boundary; Monte Carlo
requires every requested iteration to succeed and cannot swallow failed runs
into a partial success. Scalar modification is limited to explicitly declared
compatible `CalibrationSchema` fields and validates nested paths without
stringly typed traversal.

The core runner adds no analysis state to a simulation checkpoint. API batch
storage nevertheless persists the exact serialized raw vectors, statistics,
fingerprints, and provenance in its existing durable result store; Python and
MCP return the same payload without silently dropping fields.

Doctrine comparison supplies a separate typed `DoctrineAnalysisVariant` in
addition to the calibration patch. Its public representation is an ordered
non-empty tuple/list of strict `DoctrineSideAssignment(side, school_id)`
records, not a mapping whose duplicate keys could be overwritten before
validation. Side IDs must be unique within a variant; multiple different sides
may deliberately share one school. The comparison requires at least two
variants over the same non-empty set of exact scenario side IDs and at least
two distinct catalog-backed school assignments across those variants.
Unmapped sides retain their production commander-derived assignment.
Unknown/duplicate sides, unknown schools, and variants with different
mapped-side sets reject.

Source-scenario school configuration is a separate strict
`SchoolScenarioConfig` whose only field is exact `unit_assignments`. Unknown
fields reject; `enable_schools`, `blue`/`red`, and
`blue_school`/`red_school` are not alternate side-policy authorities. A
scenario may therefore bind known stable initial/future unit IDs exactly, while
side-wide experiments remain typed analysis variants. The scenario editor does
not offer school selection until it can construct one of those production
contracts without a proxy.

The runtime session installs the variant as the highest-precedence typed
school-assignment policy before context publication. Initial registration and
every reinforcement registration consult that same policy; mutation after
initial loading is insufficient. The source YAML SHA-256, canonical effective
typed-configuration SHA-256 per variant, resolved catalog/data revision,
doctrine catalog/assignment digest, loaded roster/loadout-topology digest,
initial and arriving per-unit assignments, and code revision participate in
result provenance. Source YAML is never modified.

The frontend comparison types, client, table, and charts migrate with the
response contract. They label the result as paired, display direction,
positive/negative/tied seed counts, paired difference, superiority, raw and
adjusted p-values, and family-wise significance. No UI continues to label the
removed Mann-Whitney statistic or rank-biserial value as current evidence.

### Commander-profile authority

`SideConfig.commander_profile` is the canonical side-default personality
reference. Commander activation follows one truth table:

- all side profiles blank and `commander_config` omitted: no commander engine;
- some but not all side profiles populated: reject;
- every side profile populated: create one commander engine, with optional
  tuning and per-unit overrides; and
- any present `commander_config`, including `{}`, while side profiles are
  blank: reject as a feature-shaped dead or ambiguous declaration.

An enabled scenario loads the global commander-profile catalog plus the
applicable era commander catalog, validates every reference, and assigns every
initial unit before returning `SimulationContext`.

`commander_config` becomes a strict typed tuning/override model. It contains
`CommanderConfig` fields and optional exact per-unit assignments, but no
second `side_defaults` authority. Per-unit assignments override the canonical
side profile and are not contradictions merely because the profile differs.
`ooda_speed_base_mult` is a finite strict float greater than zero;
`noise_sigma` is finite and non-negative; and `risk_threshold_base` is finite
in `[0, 1]`. Booleans, strings, NaN, infinity, and unknown fields reject.
Empty/untrimmed IDs, unknown sides, unknown initial or future unit IDs, unknown
profiles, and duplicate profile IDs reject atomically. Strict unique-key YAML
loading rejects duplicate assignment keys. A public catalog merge API rejects
duplicate profile IDs within or across global and era directories even when
the definitions are equal; insertion order never wins.

Scenario load derives every stable future reinforcement ID from wave ordinal,
side, unit type, and index. A per-unit override may name a validated future ID
but does not appear in runtime assignment state before arrival.
`register_dynamic_units()` owns one staged arrival plan covering roster,
loadouts, morale, logistics, commander profile, and doctrine school. It
validates the complete plan before the first commit, applies the canonical side
profile and then any exact per-unit override, and publishes the arrival only
after every component commits. Any failure rolls every component and the
ENTITIES/C2 state back so the wave remains retryable.

If an assigned personality declares `school_id`, the scenario must have a
loaded registry containing that school; otherwise loading rejects. Explicit
typed doctrine-analysis variants have the documented higher precedence.
Initial and dynamic assignment failures are explicit load/arrival failures,
not warning storms, and cannot leave a partially assigned roster.

The six currently unresolved side references are corrected to existing
catalog roles without inventing traits:

- Khafji red and Debecka Pass red: `aggressive_armor`;
- Fallujah Phase Line Fran red and Bint Jbeil red: `insurgent_leader`;
- INS Hanit blue: `naval_surface`; and
- INS Hanit red: `insurgent_leader`.

Suwalki Gap and Korean Peninsula remove stale
`commander_config.side_defaults`; their already-declared canonical side
profiles remain `joint_campaign`/`aggressive_armor` and
`cautious_infantry`/`aggressive_armor`, respectively.

The correction selects among existing modeled archetypes. It does not assert
that their numeric traits are historically calibrated. Enabling previously
dead canonical profiles consumes the existing C2 RNG and can affect OODA and
decision behavior; representative and full scenario results must therefore be
compared with the phase-start baselines and every difference explained.

Commander assignment state belongs to `CommanderEngine`; school assignments
belong to `SchoolRegistry`; decision state and the C2 RNG remain their existing
separate owners. Each provides staged state validation against the exact
arrived-unit topology and loaded profile/school catalogs. Whole-context restore
validates every staged component, including map-key/unit-ID agreement and
future-versus-arrived topology, before any roster, clock, assignment, school,
decision, or RNG mutation. A fresh-runtime restore must retain exact
unit-to-profile and school assignments, C2 RNG state, decision state, and
continuation behavior, including a reinforcement that arrives after the
checkpoint.

Phase 112 assignment/checkpoint support is bounded to the production default
`AggregationConfig(enable_aggregation=False)`. Force aggregation is not
selectable through the typed scenario schema; a programmatically enabled
aggregation state with proxy or archived constituent IDs causes an explicit
unsupported checkpoint/diagnostic error rather than a false whole-context
claim. Phase 112 does not assign commander profiles or movement histories to
`agg_NNNN` proxies. REM-016 retains ownership of aggregate/disaggregate
subtype/loadout reconstruction and its corresponding commander/diagnostic
lifecycle.

### Eager unit-definition and exact-roster validation

`CrewEntry.role` and `CrewEntry.skill` validate and canonicalize during
`UnitLoader.load_definition()`, before any crew RNG draw. `CREW` remains the
documented alias for `CrewRole.GENERIC`; every other role must exactly match a
`CrewRole` member. Skill must exactly match a `SkillLevel` member after
case-normalization. Empty values and arbitrary strings fail with field,
unit-file, supplied-value, and allowed-value context.

The same eager boundary validates every other enum currently deferred to unit
construction: domain, equipment category, and the domain-appropriate ground,
aerial, naval, air-defense, or support subtype. A data-definition error must
not survive typed loading merely because a later constructor would raise
`KeyError`.

The French Old Guard commander skill changes from unsupported `EXPERT` to the
existing highest proficiency tier, `ELITE`. No new skill tier or performance
parameter is introduced. The source unit's `training_level: 0.9`, veteran
crew, and elite Guard role remain otherwise unchanged.

`UnitLoader` raises a dedicated missing-definition exception only when the
requested unit type has no loaded definition. Force construction may catch
only that exception if a caller explicitly supports optional definitions;
production scenario construction does not skip it. Crew, equipment, subtype,
override, and constructor failures propagate with context.

Initial per-unit overrides use one strict typed `UnitInstanceOverrides` model.
The shipped contract supports finite `training_level` in `[0, 1]`,
non-negative finite `armor_front` for compatible ground units, finite
`heading` in radians, and non-empty trimmed `display_name`. `display_name`
maps deliberately to the runtime `Unit.name` field; the current shipped
display-name declarations must no longer disappear behind `hasattr`. Unknown
override attributes, incompatible-domain attributes, booleans-as-numbers, and
non-finite values reject before construction. Phase 112 records the exact
count and outcome of every shipped override during data validation.

`SideConfig.units` becomes `list[InitialUnitConfig]`, where
`InitialUnitConfig` is strict with unknown fields forbidden and contains an
exact non-empty `unit_type`, positive non-boolean `count`, an optional finite
two- or three-dimensional `position`, and typed `UnitInstanceOverrides`.
Raw `dict[str, Any]` unit entries do not survive the production configuration
boundary for later reparsing.

One typed `RuntimeForceBuilder` under the production `simulation` boundary
owns initial force construction. `ScenarioLoader` calls it; the simplified
validation runner and static validator are consumers and may not own a second
builder. Before the first ENTITIES RNG draw, it preflights the complete roster:
non-empty unit types, positive non-boolean counts, finite two- or
three-dimensional positions, the strict typed override model, every referenced
definition, and deterministic unique IDs. It then constructs every requested
unit and asserts exact per-side and total cardinality before publication. An
ENTITIES RNG snapshot makes a construction failure atomic.

Subtype validation follows the existing factory precedence rather than
requiring exactly one optional discriminator. A support unit may legitimately
carry both its mobility `ground_type` and authoritative `support_type`; the
domain plus selected concrete unit class determines which discriminator is
required and which compatible secondary metadata may coexist. Any failure
leaves no reduced force or partially published context. Static unit validation
consumes enough of this production boundary to expose deferred
enum/constructor errors without presenting a successful catalog count.

### Semantic movement diagnostics

Raw movement and semantic eligibility are separate outputs. The evaluator
continues to report exact start/end position and whole-run displacement for
every constructed unit.

One simulation-owned `MovementDiagnostics` component is injected into both
`CampaignManager` strategic/operational movement and `BattleManager` tactical
movement. Every time either manager considers a unit, it emits one immutable
`MovementObservation` and atomically updates that unit's cumulative diagnostic
state. The observation contains:

- exact unit ID, logical engine tick, movement stage/resolution, and a
  deterministic within-tick ordinal;
- the exact production decision reason;
- finite non-negative `attempted_m` and `achieved_m`; and
- the pre/post ENU positions used to verify achieved distance.

An attempted distance greater than `1e-9 m` is an expected-progress decision.
An achieved distance no greater than `1e-9 m` is zero progress for that
decision. The component counts movement decisions, not engine ticks: a
strategic-to-tactical transition or multiple active battles may legitimately
produce more than one ordered observation for a unit in one engine tick.
Ordering is `(engine_tick, stage_order, battle_id, side, unit_id)`.
Initial and dynamic units register with zeroed cumulative state. No-enemy or
inactive side-level skips record one explicit reason for each affected active
roster member. Aggregation-enabled proxy/constituent lifecycle is outside this
phase's explicitly disabled aggregation boundary and is not presented as
supported diagnostic state.

Production decision reasons distinguish at least:

- `MOVED`;
- `INACTIVE`;
- `DEFENSIVE_HOLD`;
- `AUTHORED_HOLD`;
- `EMPLACED_HOLD`;
- `RESERVE_OR_UNRELEASED`;
- `ENGINE_WEAPON_STANDOFF`;
- `RESOURCE_BLOCKED`;
- `NO_TARGET`;
- `ZERO_PROGRESS`.

`ENGINE_WEAPON_STANDOFF` is emitted by the exact tactical branch and uses the
same public production helper, live ammunition, equipment condition, and
target-domain compatibility as tactical movement. It is not reconstructed
from an unrestricted catalog maximum. Phase 112 does not invent an
`OWNED_OBJECTIVE_HOLD` reason: objective control is not currently a production
movement gate. Objective-based holding would be a separate outcome-affecting
feature.

`ZERO_PROGRESS` is valid only when the production boundary requested more than
`1e-9 m` but the committed position changed by no more than `1e-9 m`.
Any achieved distance above epsilon is `MOVED`; the existing ten-metre
whole-run display threshold is presentation only and cannot relabel a
successful tactical increment as limited or zero. Every supported no-attempt
branch uses its exact hold/block/no-target reason, never `ZERO_PROGRESS`.

For each unit the cumulative state stores exact reason counts, total attempted
and achieved metres, expected-progress count, zero-progress count,
positive-progress count, final reason/order, and a 64-observation diagnostic
ring with an exact dropped-observation count. Space is therefore
`O(units * reasons)` plus a fixed sample, not
`O(units * movement passes)`. The evaluator consumes the exact cumulative
counters rather than inferring behavior from only the final branch or relying
on the bounded sample.

The evaluator exposes raw whole-run displacement, all reason counts, totals,
decision counts, truncation metadata, and a final summary disposition. A unit
is stuck eligible only if it has at least one expected-progress decision,
every such decision achieved zero progress, and its positive-progress count is
zero. Separately, an active mobile unit is blocked eligible when an enemy
remains beyond usable standoff, every relevant movement decision was
`RESOURCE_BLOCKED`, and it made no positive progress; legitimate hold,
standoff, inactive, reserve, and no-target decisions are excluded.
`MANY_STUCK_UNITS` retains the aggregate rule of more than half zero-progress
among more than four expected-progress-eligible units. `UNIT_MOVEMENT_BLOCKED`
and `MANY_MOVEMENT_BLOCKED` expose the individual and corresponding
more-than-half-among-more-than-four resource-blocked conditions without
mislabeling them as engine zero-commit faults.

The cumulative diagnostic state and bounded sample are schema-112 checkpoint
state so a resumed evaluator cannot forget pre-checkpoint counts. Restore
stages exact active IDs, enums, monotone logical ordering, finite
positions/distances/totals, distance consistency, sample bounds, dropped
counts, and counter invariants before mutation. Instrumentation does not alter
positions, events, victory, manager ordering, or any RNG stream.

For Cambrai seed 42, raw movement remains three of ten units moved and seven
did not. The four Mark IVs must be exposed as
`ENGINE_WEAPON_STANDOFF`, and the false `MANY_STUCK_UNITS(4/7)` must disappear.
The report must not claim that a standoff-classified unit detected, fired at,
or engaged a target without the corresponding production events.

The current production movement rule can hold a unit at weapon standoff beyond
its detection/visibility range. Phase 112 records that separate behavior as
REM-028; it does not change movement, detection, or weapon performance under
REM-025.

The zero-commit invariant negative control uses an injected final movement
committer: five active, mobile, non-defensive units receive positive production
movement attempts while the injected committer returns the unchanged
position. The ordinary production committer remains the default and moves the
identical units. This exercises manager -> diagnostic observation -> evaluator
issue handling; a direct tracker call or mock-only assertion is insufficient.
Because the injection cannot be selected by scenario data or production
defaults, it is fault-detector evidence only, not evidence that ordinary
production currently reaches a legitimate zero-commit movement condition.
Phase 112 claims production classification for real holds/standoff and an
enforced invariant for an otherwise unreachable commit fault.

The decisive production negative control loads a real tactical scenario with
five active, mobile catalog-backed vehicles and exact opposing targets beyond
usable standoff. Their valid live unit state is fuel-depleted before the
production step; the ordinary BattleManager fuel gate must leave them
unchanged, record `RESOURCE_BLOCKED`, and emit individual
`UNIT_MOVEMENT_BLOCKED` plus aggregate `MANY_MOVEMENT_BLOCKED`. The identical
fully fueled control moves and emits neither issue. Direct calls to
`MovementDiagnostics`, a fake movement result, or the injected committer do
not satisfy this production blocked-unit proof.

### Phase 112 version-2 reproducible paired performance contract (historical)

For the Phase 112 closure, `baselines.json` advanced to a strict typed
version-2 contract. A gating entry contained:

- one full authoritative reference commit, initially
  `0460ac70be86784bcc6e359ae4202f4bcb938c60`;
- exact scenario-file SHA-256, dependency-lock SHA-256, and effective-runtime
  input fingerprint;
- seed `42`;
- a typed semantic envelope;
- one untimed warm-up per revision;
- three timed candidate/reference pairs;
- alternating `reference,candidate`, `candidate,reference`,
  `reference,candidate` order;
- timing scope exactly `SimulationEngine.run()` with profiling disabled;
- maximum median paired slowdown ratio `1.20`; and
- maximum per-revision relative sample range
  `(max - min) / median` of `0.20`.

The effective-runtime input fingerprint is a SHA-256 over canonical UTF-8
JSON with sorted object keys, no insignificant whitespace, explicit `null`,
ordered arrays, and non-finite numbers rejected. It includes:

- the complete effective typed scenario configuration after defaults and
  calibration overrides, serialized with Pydantic JSON-mode values;
- exact ordered side, unit ID, definition ID, position, instance override,
  reinforcement, objective, victory-condition, feature-flag, doctrine-school,
  and commander-profile values;
- the resolved typed definitions and source SHA-256 values for every
  loader-consumed transitive source/value, including units, equipment,
  weapons, ammunition, sensors, detection signatures, commander profiles, era
  overlays, doctrine schools, and any enabled external terrain, environment,
  space, or logistics input;
- seed, maximum ticks, and every effective feature/calibration override; and
- the candidate-owned comparison-policy/normalization version.

The artifact exposes the constituent source paths/hashes, canonical manifest,
and composite digest.
Absolute paths, dictionary insertion order, timestamps, and other volatile
host data do not participate. A scenario-file hash or roster/loadout ID list
alone is insufficient because a referenced catalog value can change runtime
work without changing either.

Code, loader, checkpoint, and result-schema revisions remain explicit artifact
metadata but are not equality-critical inputs: the reference is schema 111 and
the candidate advances to schema 112 by design. For that Phase 112 comparison,
one candidate-owned version-2 normalizer projects both revisions into the same
effective-value and semantic contracts. A normalized value difference fails;
an intentional schema-version label difference alone does not.

The semantic envelope contains exact unit count, ordered roster/loadout
fingerprint, winner, victory condition type, ticks, logical duration,
per-side status counts, and a canonical event-type/outcome digest. Reference
and candidate must match the stored envelope and each other before timing can
pass. A faster semantically different workload is a failure.

Every warm-up and timed run uses the same strict `SimulationRecorder`
configuration inside the measured `SimulationEngine.run()` scope; that
configuration participates in the effective-input fingerprint. The event
digest is SHA-256 over canonical JSON of the complete ordered public
`(tick, logical timestamp, event_type, source, full normalized data)` stream.
Enums use stable values, dataclasses and positions use their complete public
fields, keys are sorted, and non-finite/unserializable values reject. Wall
timestamps, object identities, and log text are excluded. Recorder
serialization fallback to `{}`, capacity drops, and truncated event streams
are errors rather than weak digests.

Each pair produces `candidate_seconds / reference_seconds`; the median of the
three ratios must be no greater than `1.20`. Excess sample spread is
`INCONCLUSIVE` and fails the gate. Missing/malformed/non-finite policy data,
an unavailable reference, dirty reference, unmanifested candidate change,
scenario or lock mismatch, semantic mismatch, zero/negative duration, or
missing sample is an error. There is no
absolute `<15`, `<30`, `<60`, `<120`, `<300`, `<500`, or `<1800` second pass
threshold. A single candidate/reference timing ratio, including the current
10% and 15% flag-impact margins, is not a gate.

Reference and candidate run serially on the same host, CPU affinity, runner
image, dependency lock, and environment. Every JSON artifact records raw
warm-up/timed samples; OS, kernel, architecture, CPU model, physical/logical
core counts and affinity; total RAM; Python implementation/version; NumPy,
NetworkX, Pydantic, and relevant dependency versions; lock and scenario
hashes; runner image/labels; threading variables; full commits; dirty state;
and semantic results. Unprofiled peak memory is `null`, never fabricated as
zero.

The candidate-owned harness checks out the stored reference with full git
history, validates identical lock files, executes both trees as subprocesses,
and always emits/uploads the comparison artifact. It does not update the
reference automatically. Reference promotion requires a clean passing
comparison, reviewed semantic envelope, artifact digest, rationale, and one
intentional baseline commit.

The reference worktree must be clean. Before the required Phase 112 commit,
the candidate may contain the phase diff only when the harness records a
complete path/mode/content manifest for the runtime-affecting source/input
closure: Python, lock/configuration, scenario/catalog data, and any new
importable or loader-consumed file. It rejects unmanifested or ignored
runtime-affecting code/data and separately records full git status. Mutable
benchmark artifacts, devlog evidence, and postmortem documentation are not
part of performance identity. The final phase commit tree must reproduce the
runtime-affecting manifest exactly before its precommit comparison is accepted.
Post-commit clean reruns, including remote CI, supplement this identity proof.
An unexplained runtime-affecting dirty path, final-tree manifest mismatch, or
dirty reference state is an error.

All current authoritative-looking wall-clock checks migrate explicitly:

- `tests/performance/test_battle_perf.py` no longer gates Golan at 120 seconds
  or 73 Easting at 30 seconds;
- `tests/validation/test_campaign_performance.py` no longer gates Golan at
  120 seconds or Falklands at 60 seconds;
- `tests/validation/test_block8_exit.py` no longer treats a source search for
  a 120-second literal as performance evidence; and
- `tests/benchmarks/test_benchmarks.py` no longer gates at 15, 60, 300, or
  1,800 seconds or compares against stale unpaired baseline values;
- `tests/benchmarks/test_flag_impact.py` exposes raw measurements only until
  each flag comparison has its own compatible paired reference and effective
  configuration fingerprint. It cannot claim that a flag is faster, not
  slower, or interaction-safe from one timing pair.

No collected test, validation exit check, or workflow may make a performance
or regression claim from an absolute wall-clock upper/lower bound or an
unpaired single-run timing comparison. Strict-positive finite sample
validation remains mandatory but carries no speed/capability claim. Every
regression claim uses the typed paired policy; every other timing run is
explicitly `measurement_only`. Measured CI safety timeouts may fail an
incomplete job and preserve its partial artifact, but they are operational
containment rather than performance-regression evidence.

At Phase 112 closure, the routine 73 Easting gate used the version-2 paired
harness. The full paired Golan run is a standalone manual harness, not a
pytest node in the scheduled `slow-benchmark` partition. Existing Golan and
Falklands pytest nodes are either semantic/profile tests with no regression
claim or typed
`measurement_only` consumers that refuse a pass/fail regression result.
Consequently the weekly partition cannot accidentally execute the manual
Golan gate. Weekly marker jobs are sharded by deterministic collected node-ID
manifests, use explicit per-shard timeouts derived from fresh Phase 112
measurements with recorded headroom, fail an empty shard, and publish partial
artifacts under `if: always()`. Full battalion and brigade measurements are
manual; weekly coverage retains their fast schema/load/unit-count checks.
Phase 112 records the pre/post number of full Golan, battalion, and brigade
engine invocations, measured shard runtimes, chosen timeouts, and headroom.

73 Easting is described as its observed movement/control-plane workload, not
as combat-throughput evidence: the Phase 112 start revision has 71 units,
blue `time_expired`, 360 ticks, 1,800 logical seconds, zero casualties, and
zero engagements. Golan is the long production workload. Battalion and
brigade become typed `measurement_only`/unbaselined entries; schema, load, and
unit-count checks remain, but any regression claim against them raises until
a real paired reference is promoted. Missing scenarios and unknown benchmark
overrides fail explicitly rather than skip or filter.

The start-revision 73 Easting warm-up was 1.4871 s; timed samples were
1.472391218, 1.491125374, and 1.483391515 s (median 1.483391515 s). Its stored
185-tick envelope is stale against the observed 360 ticks. The single
diagnostic Golan sample was 129.517695006 s with 290 units, blue winner, and
6,480 ticks; it is baseline red evidence, not a paired pass. Start hashes are
`bbc6b45cfc270d08baa09d3d568a6b84d0f936a6ee9c874cb49c9d8813c5ad39`
for `uv.lock`,
`328467cd1f200cf2f0157da917ab20b9e9bbc43fb7ee985f5d4472d2df3cd3e5`
for 73 Easting, and
`699b75819d271ddf61a8d0bce309d44f64335fd1af6cd7d0b1c6da39128b8868`
for Golan.

### Phase 113 version-3 typed workload predecessor

During Phase 113, the baseline and artifact contract advanced to version
3. Each version-3 entry carried a strict `BenchmarkWorkload` with a named workload
and typed sparse `BenchmarkCalibrationPatch`; unknown fields, missing workload
identity, and a workload-name/patch mismatch reject. The workload and exact
effective calibration participate in the reference/candidate input
fingerprint and semantic comparison.

The routine 73 Easting gate is specifically
`morale_neutral_control_plane`. Its typed morale patch sets the base degrade
and recovery rates plus casualty, suppression, leadership, cohesion, and force
ratio weights to exactly zero through the production configuration boundary.
Only 73 Easting may select this workload. Every other version-3 entry uses the
typed `default` workload, and a morale-neutral patch on another entry rejects.

This control preserves a stable movement/control-plane performance workload
across the intentional Phase 113 morale-ownership change. Its checked-in
semantic envelope remains 71 units, all 21 blue and 50 red units `ACTIVE`, blue
`time_expired`, 360 ticks, 1,800 logical seconds, and one recorded victory
event. It is not evidence for default 73 Easting morale behavior, combat
throughput, historical fidelity, or Phase 113 acceptance. The version-2 timing
and baseline-red measurements above remain labeled historical Phase 112
evidence rather than being rewritten as version-3 results.

### Phase 115 version-4 workload-transition qualification

Phase 115 intentionally changes the effective 73 Easting control-plane
workload while correcting equipment roles and enabling sensing-aware tactical
standoff. The version-3 gate correctly rejects that candidate before timing:
the scenario and dependency-lock identities remain exact, but the effective
configuration, VVS-2 target-domain data, all 21 blue loadout role bindings,
and the derived roster/loadout digest no longer equal the stored reference.
Running paired timing samples across those different workloads would not be a
performance-regression comparison.

The checked-in benchmark contract therefore advances to strict format and
policy version 4 while retaining runtime-input normalization version 3. The
ordinary `gate` and `measurement_only` policies retain their existing
meanings. A separate `transition_qualified` policy carries no timing
threshold, order, pair count, timing scope, ratio, or performance decision.
The ordinary `compare` command must reject it before launching a worker. A
dedicated transition command executes exactly one production closure for the
reference and one for the candidate; it can emit only
`transition_qualified`, `transition_rejected`, or `error`.

One typed transition contract contains the exact reference and candidate
runtime-input identities, exact reference and candidate semantic envelopes,
verified version-3 predecessor lineage, and a path-sorted, duplicate-free list
of every approved effective-input, derived runtime-input, and semantic
difference. Each approval
records its surface, canonical RFC-6901 JSON Pointer, add/remove/replace
operation, exact canonical before/after value digests, a closed classification,
non-empty authorities, and rationale. Values use canonical JSON: sorted object
keys, compact separators, explicit `null`, and no NaN or infinity. A transition
digests a presence envelope—`{"present":false}` for absence or
`{"present":true,"value":...}` for presence—so a missing path is never
equivalent to a present JSON `null`. A transition
rejects an added, removed, changed, stale, duplicated, reclassified, or
unapproved value. A scenario, dependency lock, seed, maximum tick count,
recorder configuration, or resolved source-list difference is never
transition-qualified.

The candidate-owned worker runs both endpoints. Every closure remains bound to
its exact tree identity. The harness recomputes the complete runtime-input and
semantic diffs and compares them to the checked-in contract before emitting
its result. A separately typed, atomically written, digest-bearing transition
artifact contains both complete runtime manifests and semantic envelopes, the
exact classified differences, predecessor/baseline and tree identities,
environment metadata, and an explicit `not_applicable` timing assessment. A
closure and transition artifact expose no duration, timing sample, pair,
ratio, or `PerformanceDecision`; operational timeouts and contention notes are
not regression evidence. Neither the CLI, artifact validator, final-tree
verifier, workflow, test, devlog, nor postmortem may rename a qualified
transition to `pass` or infer a speed claim from it.

The Phase 115 73 Easting transition is limited to three loaded
`enable_sensing_aware_standoff: true` views, the catalog VVS-2 domain expansion
from ground-only to ground/aerial/naval/amphibious, the exact 21 blue VVS-2
loadout bindings from `ground_night_sight` to `night_vision`, the derived
runtime-input fingerprint, and the derived roster/loadout digest. Unit count,
winner, victory condition, ticks, logical duration, status counts, event count,
event digest, scenario bytes, lock bytes, and all resolved source bytes remain
exact. This is integrity-transition evidence, not historical validation,
default-workload evidence, combat-throughput evidence, or a performance pass.

The dirty precommit candidate snapshot must still carry a complete
path/mode/content runtime-tree manifest. After the one Phase 115 commit, the
existing clean-final-tree verifier must reproduce the candidate endpoint from
that clean commit and may report only `transition_qualified`. The next phase
must promote that clean Phase 115 commit and exact candidate endpoint to an
ordinary version-4 paired reference before it can pass its own postmortem;
promotion remains a reviewed baseline change and cannot be automatic or
self-referential. The checked-in transition contract may retain predecessor
document/entry hashes, but it must not embed its own current document/entry
hash, candidate Git identity, or candidate runtime-tree manifest; those belong
only to the external artifact.

### Typed Space ISR report delivery and checkpoint state

`SpaceISREngine` buffers immutable `SpaceISRReport` values with exactly:

- strict positive-integer `report_id`;
- `reporting_side`;
- `target_side`;
- `target_id`;
- `satellite_id`;
- `constellation_id`;
- imaging `sensor_type`;
- finite positive `resolution_m`;
- finite positive `position_sigma_m`;
- `target_position: Position`;
- finite non-negative `observed_at_s`; and
- `available_at_s`.

String identifiers are non-empty and trimmed; `report_id` rejects booleans and
is not a string identifier. It is assigned from a checkpointed monotonic
Space-ISR counter after canonical iteration of exact scenario side,
constellation, satellite, and target IDs; it is globally unique within the
simulation and stable across continuation. A report serializes with exact keys
and its ENU position as exactly three finite numbers. Restore explicitly
rehydrates `Position` and rejects duplicate report IDs,
booleans as numbers, non-finite values, unknown keys, malformed positions,
unknown or same-side reporting/target sides, unknown/mismatched satellite or
constellation references, ownership mismatch, non-imaging sensor types,
catalog sensor/resolution mismatch, an observation after checkpoint time, or
an availability time other than
`observed_at_s + configured_processing_delay_s`.

`ConstellationDefinition` adds optional `imint_position_sigma_m`: a supported
imaging-fusion constellation requires a finite positive sourced one-axis
geolocation standard deviation in metres, while non-imaging constellations
reject the field. Spatial resolution and geolocation accuracy are separate
quantities; missing accuracy data never falls back to a resolution proxy.
`SpaceISRReport.position_sigma_m` must equal its catalog value exactly.

`SpaceConfig` adds the strict, unique
`imint_fusion_constellation_ids: list[str]` selection, defaulting to empty.
Entries are trimmed identifiers and their authored order is retained. Every
selected ID must be present in `constellation_ids`, resolve to an optical or
SAR imaging definition with matching sensor type, positive resolution/swath,
and carry finite positive `imint_position_sigma_m`. A nonempty selection also
requires `CalibrationSchema.enable_space_effects: true`. The ordinary-contact
`enable_fog_of_war` flag is independent: the runtime always owns its
`FogOfWarManager`/`IntelFusionEngine`, so dedicated IMINT fusion remains valid
when ordinary contact generation is disabled. These cross-object constraints
are checked by the production `ScenarioLoader`/runtime preflight before
creating or mutating a Space engine. Selecting an imaging definition without
sourced position sigma raises `UnsupportedIMINTFusionError` at that preflight
boundary. Merely loading an unselected imaging definition continues to support
its overpass events and does not opt it into target-report generation. The
broad legacy `enable_space_effects` gate continues to govern other space
effects and does not silently enable IMINT fusion. The ordered fusion selection,
`isr_processing_delay_s`, each selected definition's complete catalog value,
and its position sigma participate in the existing resolved-Space
configuration fingerprint and checkpoint compatibility check.

The shipped classified `keyhole_optical` and `lacrosse_sar` entries remain
explicitly fusion-unsupported because no inspectable authoritative one-axis
geolocation-accuracy source is available. Taiwan Strait, Korean Peninsula,
and Space ASAT Escalation explicitly declare
`imint_fusion_constellation_ids: []`: their loaded classified imaging assets
remain overpass/ASAT topology, not an unsupported imagery-fusion claim. A
loader-negative control changes each scenario in turn to select one of those
IDs and must fail before runtime mutation.

Phase 112 instead adds supported catalog-backed
`worldview2_reference_optical` and `worldview3_reference_optical`
constellations for the production proof. Their catalog comments bind the
public NASA/Vantor values used by the model: WorldView-2 uses a 770 km
sun-synchronous orbit, 100-minute period, 0.46 m nadir panchromatic resolution,
16.4 km nadir swath, and a conservative 3.5 m CE90 geolocation bound;
WorldView-3 uses a 617 km sun-synchronous orbit, 97-minute period, 0.31 m
nadir panchromatic resolution, 13.1 km nadir swath, and the same conservative
3.5 m CE90 bound. Under the predeclared isotropic zero-mean bivariate-normal
conversion, both use
`sigma = CE90 / sqrt(2 * ln(10)) = 1.6309671062462963 m`.
The model's exact inclination, plane, anomaly, side ownership, and initial
orbital phase are documented deterministic proof-scenario assumptions rather
than attributed observations. Each definition represents its one named
satellite. The proof scenario assigns both civil/commercial reference assets
to blue solely as an authored simulation input; it makes no real-world
ownership or military-access claim.

The production resolvability boundary accepts repository `Unit` instances,
not arbitrary objects. It validates exact nonempty entity ID, side ownership,
finite `Position`, and the real `personnel` list before candidate allocation;
`_estimate_unit_size()` uses `len(target.personnel)`. It removes the current
fallback through nonexistent `personnel_count`/`strength` attributes and never
silently treats an unknown target shape as strength one. An unsupported target
type raises `UnsupportedISRTargetError` before queue/cadence/counter mutation.
Focused tests replace dummy objects with real loader-built units and include
an atomic unknown-shape negative.

The live T-72M `Unit.personnel` count follows the existing vehicle threshold.
WorldView-2's 0.46 m and WorldView-3's 0.31 m values both satisfy the current
0.5 m vehicle threshold without a test-only target attribute or false
resolution. A clearly labeled test-only resolution-negative definition above
0.5 m produces no vehicle report while leaving overpass behavior intact; it
is an invariant control, not shipped constellation data.

The existing `space_isr_gap` validation scenario becomes the long-delay
production proof rather than a synthetic unit-only harness. It retains its
loader-built four M1A2 and eight T-72M units, uses
`tick_duration_seconds: 60.0`, `roe_level: WEAPONS_HOLD`,
`enable_space_effects: true`, `enable_fog_of_war: false`, the supported
WorldView-3 reference constellation as its sole fusion selection, and
`isr_processing_delay_s: 7200.0`. The time-expired objective keeps the normal
engine loop available through 21,600 s without manufacturing combat outcomes.
For the repository's current simplified orbit epoch, the proof definition uses
the explicit scenario-reference assumptions inclination 97 degrees, RAAN 105
degrees, argument of perigee zero, and true anomaly 205 degrees. These are not
claimed as historical WorldView-3 ephemeris. They must produce no visibility
on an earlier 60-second tick, then visible observations at 14,400, 14,460, and
14,520 s. Each observation produces one report for each of the eight live
T-72M target entity IDs in canonical order. The first eight-report batch
delivers at 21,600 s and the second batch at 21,660 s, updating the same eight
tracks rather than creating more; any earlier report, missing target, or
changed schedule is a fixture failure, not accepted timing drift.

A separate loader-owned lifecycle fixture uses the same forces and theater,
60-second master cadence, both reference constellations, and 300-second
processing delay. Its WorldView-2 proof assumptions are inclination 98
degrees, RAAN 115 degrees, argument of perigee zero, and true anomaly 235
degrees; its WorldView-3 assumptions are those above. Under the current orbit
model, WorldView-3 is visible on 60-second ticks from 14,400 through 14,940 s
and 20,280 through 20,580 s; WorldView-2 is visible from 14,400 through
15,000 s and 20,340 through 20,940 s. The latest first-pass observation at
15,000 s delivers at 15,300 s with age 300; ordinary master-loop updates at
15,360, 15,600, and 15,660 s prove coasting/inclusive-lost/stale behavior. The
public runtime-owned fusion-lifecycle boundary is also called at 15,301 and
15,601 s to prove the exact one-second threshold transitions without changing
scenario cadence or injecting a report. The next generated WorldView-3
observation at 20,280 s delivers at 20,580 s and reactivates the same eight
track identities at age 300. At 20,340 s both constellations generate against
the same targets; their reports deliver at 20,640 s in canonical
constellation/satellite/report-ID order. Every positive lifecycle and
same-epoch ordering report comes from the loader-wired Space engine. Only
malformed/older invariant negatives may submit a deliberately invalid typed
value to the public boundary, and those negatives are not capability evidence.

Generation validates that the target exists and belongs to `target_side`, and
that both sides are exact loaded scenario IDs, differ, and the reporting side
owns the imaging constellation. The generator iterates loaded side IDs rather
than hard-coded blue/red aliases. A historical report does not require the
satellite still to be active or the observed target still to be active at
restore, but its satellite must remain in loaded Space topology and its target
ID/side must remain in the staged exact unit topology. A destroyed/inactive
unit therefore preserves its past report; an absent target rejects. Phase 112
does not claim report continuation across aggregation that removes constituent
target identities, and its proof scenario has aggregation disabled. The
satellite and constellation topology and both side IDs remain required.

Each Space update validates the complete canonically ordered candidate batch
before allocating the first report ID. ID allocation, queue append, and
`last_reported_at` publication commit together; any candidate failure leaves
the queue, sequence, cadence map, topology, and SPACE RNG byte-for-byte
unchanged.

Reports become ready on the first space update where elapsed time is greater
than or equal to `available_at_s`. Queue order is canonical by availability,
observation, reporting side, constellation, satellite, target identity, and
report ID. `report_id` is the acknowledgement identity; generation and restore
reject either a duplicate ID or a duplicate canonical tuple of every other
serialized report field. The engine peeks ready reports and processes them as
ordered per-report transactions. Each
transaction stages the affected fusion tracks, fusion counter, delivery
receipts, and mirrored DETECTION RNG state; it commits them together, then
acknowledges exactly that report. On failure the current report and every
subsequent report remain queued while all staged state for the failed report
rolls back. Previously committed reports remain committed and acknowledged.
An unexpected generation or fusion-integrity failure always propagates,
independent of optional debug or global diagnostic strictness.

Space imagery does not require an EW suite. Optical and SAR reports enter
the public typed `IntelFusionEngine.submit_imint_report()` production boundary
as `IntelSource.IMINT`, only for
`reporting_side`; they do not pass through a mixed EW/SIGINT helper and the
opponent never receives the same report. A successful submission appends one
immutable persisted `IntelDeliveryReceipt` containing the report ID,
reporting/target sides, target/satellite/constellation IDs, sensor type,
resolution, position sigma, observed position/time, availability time,
`IMINT` source, resulting track ID, delivery time, and SHA-256 of the canonical
full report.
The receipt is the terminal delivered-report record, is exposed with fusion
diagnostics, and is the authoritative persisted proof of report source;
`Track` need not manufacture a single-source field after multisource fusion.
Its times must satisfy
`observed_at_s <= available_at_s <= delivery_time_s <= checkpoint_elapsed_s`,
in addition to the report's exact configured-delay equality. Restore rejects
a delivery before availability or after checkpoint time before any mutation.
An empty `imint_fusion_constellation_ids` selection skips report-candidate
generation and produces no target report, queue, receipt, or fusion mutation
even when other space effects are enabled. `enable_space_effects: false`
likewise produces none and cannot be paired with a nonempty fusion selection.

The dedicated adapter creates a two-dimensional IMINT measurement
`z = [easting, northing]` with
`R = diag(position_sigma_m**2, position_sigma_m**2)`. It bypasses generic
`IntelReport.reliability` scaling, creates `ContactLevel.DETECTED` with no
type/specific estimate and zero classification confidence, and asserts the
exact initial/update covariance. Sensor resolution remains only the imaging
resolvability input; it is never relabeled as geolocation uncertainty.

Temporal provenance distinguishes measurement time from knowledge time.
`TrackState.last_update_time` remains the observation epoch
`observed_at_s`; each IMINT association also persists exact
`last_observed_at_s`, `last_received_at_s`, and last report ID. Delivery time
is the current logical time at successful fusion and may be later than
`available_at_s` under a coarse tick. The estimator predicts an existing track
from its prior observation epoch to the new report's observation epoch before
applying the measurement; it never stamps a historical position as observed at
delivery.

At delivery, observation age is `delivery_time_s - observed_at_s`. Age at or
below the estimator coast threshold follows normal tentative/confirmed
promotion; age above coast and at or below lost threshold is `COASTING`; age
above lost threshold is the new explicit non-actionable `STALE` status. With
the shipped estimator defaults, exact ages 300 s and 600 s remain in the
younger categories, while 301 s is `COASTING` and 601 s is `STALE`. The
ordinary fusion lifecycle applies this same age function to associated IMINT
tracks on every update, including tentative tracks; it does not rely on the
existing non-IMINT confirmed-to-coasting transition to retain them.
At or below the coast threshold, hits below the configured confirmation count
mean `TENTATIVE` and hits at or above it mean `CONFIRMED`; above coast through
lost means `COASTING`; above lost means `STALE`. Associated IMINT status is
therefore a deterministic function of last observation age, hits, and the
loaded estimator thresholds. Covariance remains exposed but does not delete
the one bounded IMINT association.

Stale IMINT tracks remain as one bounded latest-known track per owner/target,
are excluded from ordinary FOW contacts/COP targeting, and expose their
observation/receipt ages rather than being deleted immediately. A strictly
newer report updates the same state at its observation epoch and
deterministically recomputes status; sufficiently fresh data reactivates it
without changing track identity. Distinct same-epoch reports update in
canonical constellation/satellite/report-ID order; an older observation
rejects through the same public typed submission transaction without mutating
the track, counter, receipt ledger, association, or DETECTION RNG. Non-IMINT
lifecycle/deletion behavior is unchanged.

If normal estimator gating rejects a newer or same-epoch measurement, the
typed submission reports failure and the encompassing per-report transaction
rolls back; it never acknowledges the report or records a receipt for an
unapplied measurement. The ready report remains at the queue head for explicit
operator correction rather than being silently discarded.

Fusion maintains a persisted exact
`imint_target_tracks[reporting_side][target_id] -> track_id` association. The
first report creates one track; every later report for that owner/target
updates that exact track. A missing mapped track is an integrity failure rather
than implicit new-track creation. During one visible pass, each Space engine
update produces at most one report per
`(reporting_side, satellite_id, target_id, observed_at_s)`. A persisted
`last_reported_at` map makes repeating the same logical update idempotent;
a later logical observation time produces a new report and updates the same
track.

Space-ISR checkpoint state has exact keys for `last_overpass_time`,
`last_reported_at`, `report_queue`, and `next_report_sequence`. Staged restore
validates every satellite/side/target key against exact topology, every time as
finite, non-negative, and no later than checkpoint elapsed time, canonical
queue ordering, and a strict positive next sequence. Queue report IDs and
fusion receipt report IDs are disjoint and together equal every issued integer
from one through `next_report_sequence - 1`; a receipt's canonical report
digest must recompute from its persisted report fields. The existing
overpass-hysteresis and new report-cadence maps are mutable production state,
not static topology.

`last_reported_at` is not independently trusted. For every
`(reporting_side, satellite_id, target_id)` key, it must equal the maximum
`observed_at_s` among the exact union of queued reports and delivered receipts,
and every map entry must have such an issued report. A queued report for an
already associated owner/target may not precede the latest delivered
observation; at the same epoch its canonical constellation/satellite/report-ID
order must follow the latest receipt so retry continuation cannot replay an
earlier measurement.

The fog-of-war checkpoint boundary includes its `IntelFusionEngine` track
state, counter, delivery-receipt ledger, IMINT target-track associations, and
registered satellite passes. Staged fusion restore validates every
`SatellitePass` exact field and side against loaded topology, requires finite
times/coverage/resolution/revisit values with start no later than end, and
preserves canonical per-side pass ordering. It rejects
unknown/missing keys, an invalid side map, a side-owned map containing another
side's track or receipt, map-key/track-ID disagreement, duplicate IDs, a
receipt whose resulting track is absent, non-IMINT Space receipts, invalid
status/source enum values, booleans-as-numbers, non-finite state, malformed
position/velocity vectors other than length two or covariance arrays other
than 4-by-4, invalid contact levels/confidence/hit/miss/time values, a fusion
counter inconsistent with issued track IDs, report/receipt topology
inconsistent with the Space counter, a target association whose owner/track is
missing or mismatched, and type-aware disagreement between its serialized
DETECTION RNG mirror and the authoritative `RNGManager` state.
For each IMINT owner/target association, restore derives the latest receipt by
observation epoch and canonical constellation/satellite/report-ID order. The
association's last report ID, `last_observed_at_s`, and
`last_received_at_s` must equal that receipt; its track ID must equal the
receipt's resulting track ID; and the track state's observation epoch must
equal `last_observed_at_s`. Track status must equal the configured
tentative/confirmed, coasting, or stale age function at checkpoint time,
including exact coast/lost boundaries. A type-valid disagreement in any one
of these cross-field values rejects the complete staged restore.
Space queue and fusion state validate completely before committing any
context, RNG, clock, counter, receipt, or subsystem mutation; final commit
operations are non-throwing.

Checkpoint schema advances to 112. A report delivered after fresh restore
must produce the exact same owner-side track identity, receipt source,
position, covariance, counter, receipt ledger, queue, RNG state, and subsequent
whole-context checkpoint as uninterrupted continuation. Delivery changes
intelligence-fusion state; Phase 112 does not claim direct ordinary
fog-of-war contact injection. The separate current deficit in which
`FogOfWarManager.set_state()` discards serialized ordinary contacts is recorded
as REM-029 rather than concealed by REM-027's fusion-track proof. The REM-027
continuation fixture runs normal fusion lifecycle management but has no
ordinary sensor/contact generation and asserts empty ordinary side world views
before and after restore; its whole-context equality claim is limited to that
declared topology. A failed ready report remains checkpointable at the queue
head and is retried first after restore.

### Documentation links and public claims

MkDocs configuration enables anchor validation at warning severity. Because
the build runs with `--strict`, a missing fragment is a failing build. The
seven affected page-plus-fragment targets in phases 58, 59, 60, 61, 62, 64,
and 66 use three malformed double-hyphen slug forms. They are changed to their
real one-hyphen generated anchors, repairing all 49 current references from
devlog indexes:

- Phase 58: `known-limitations--deferred-items` to
  `known-limitations-deferred-items` (3 links);
- Phases 59, 60, 61, and 62: `deferrals-planned--deferred` to
  `deferrals-planned-deferred` (5, 6, 8, and 6 links);
- Phase 64: `known-limitations--deferrals` to `deferrals` (11 links); and
- Phase 66: `known-limitations--deferrals` to
  `known-limitations-deferrals` (10 links).

An automated behavioral test creates a temporary isolated MkDocs tree,
deliberately links to a missing fragment, enables
`validation.links.anchors: warn`, invokes `mkdocs build --strict` as a
subprocess, and asserts a non-zero exit plus the missing-fragment diagnostic.
A valid-fragment control exits zero. The final real-site build then proves zero
missing-fragment diagnostics. The new Phase 112 specification and planned
Block 13 roadmap are added to `mkdocs.yml`; the three intentionally
navigation-omitted pages
`scenarios/calibration-template.md`, `scenarios/depth-checklist-template.md`,
and `scenarios/gap-audit.md` remain the only documented exclusions and are not
mislabeled as broken links.

Strict documentation builds on pull requests as well as `main` pushes.
The PR validation job has read-only repository permissions, installs with
`uv sync --locked --extra docs`, runs the missing/valid-fragment behavioral
control before the real strict build on every invocation, and uploads its
built site under `if: always()`. The control is a standalone docs-profile
script; if implemented as pytest instead, the job installs locked `dev` and
`docs` extras. Deployment has a separate `main`-only job with the minimum
write permission and consumes the already-validated site artifact or rebuilds
the exact same commit and lock.

Before the single phase commit, local execution and workflow-structure tests
are the available workflow evidence. A GitHub-hosted result for that exact
uncommitted tree is not claimed. The clean remote result after the final
commit/push is supplemental phase evidence and is recorded without pretending
it preceded postmortem.

README, architecture, scenario, analysis, API, benchmark, testing, phase,
backlog, devlog-index, and status claims are reconciled against fresh Phase
112 evidence. A claim of analysis, commander, unit-data, diagnostic,
benchmark, or ISR support cites at least one applicable behavioral production
proof. Structural tests and source searches are labeled diagnostics only.

## Interfaces and dependencies

The analysis boundary depends on the typed scenario/configuration loader,
`ScenarioLoader`, `SimulationEngine`, public run/victory results, and exact
side/roster state. Sensitivity, comparison, doctrine, MCP, and HTTP layers are
consumers; none owns a second loader.

Commander construction depends on the global and applicable era profile
catalogs, C2 RNG, scenario sides, the initial/dynamic roster, and school
registry. Unit-definition validation depends on entity enums but consumes no
RNG until all definitions and roster topology pass.

Movement dispositions are owned by the production movement boundary and
consumed by the evaluator. The evaluator does not infer engine intent from a
catalog maximum. Benchmark comparison is test/CI infrastructure but executes
the real loader and engine in isolated subprocesses.

Space ISR depends on space topology, checkpoint elapsed time, the configured
processing delay, `Position`, and fog-of-war-owned intelligence fusion. It no
longer depends accidentally on the EW suite.

## Production trace

| Workstream | Declared | Loaded | Wired | Enabled | Exercised | Outcome-affecting | Persisted/exposed |
|---|---|---|---|---|---|---|---|
| Suite/CI trust | Named partitions, terrain profile, cadence, evidence classes | pytest collection and workflow YAML | Every partition has an exact local/CI command | Required trigger or explicit weekly/manual trigger | Fresh node-ID union and CI/local runs | N/A: this validates behavior but is not simulation behavior | Workflow logs/artifacts and developer docs |
| Analysis | Typed run, metric, provenance, and paired-result records | Production typed scenario plus override loader | Python, doctrine, MCP, and HTTP use one boundary | Every accepted request; invalid requests fail | Real loaded roster and engine runs | Controlled override changes exact production metric | Exact Python/MCP payload and durable API batch raw vectors/statistics/provenance; no checkpoint state |
| Commander | Canonical side profile plus typed tuning/override config | Global and applicable era catalogs with duplicate rejection | Initial and reinforcement units receive exact profiles | Declaring side profiles creates the engine | OODA/decision path runs with assigned personalities | Enabled side profiles change decision timing/behavior against phase-start controls | Commander/school/C2 state checkpoints and scenario diagnostics |
| Unit data | Canonical enum-valued definition fields | UnitLoader validates before construction | Exact roster builder uses validated definitions | N/A: valid unit data is mandatory, not optional | Austerlitz and Waterloo construct every authored unit | Old Guard participates in production battle state | Exact roster/loadout checkpoint and validator/evaluator output |
| Movement diagnostics | Typed disposition and bounded cumulative reason state | Production movement inputs | Exact strategic/tactical branches record disposition | Always observational when movement runs | Cambrai plus explicit zero-commit invariant control | Evaluator classification changes without altering simulation behavior | Evaluator JSON/text and bounded schema-112 state |
| Benchmark | Version-4 paired or transition policy over version-3 normalized runtime input | Strict baseline, comparison, transition, and final-tree parsers | Candidate harness runs reference and candidate production engines with the fingerprinted workload patch | 73 Easting morale-neutral transition during Phase 115; Golan default-workload manual | One closure per endpoint and zero timing samples for transition; warm-up plus three pairs for ordinary gate | Rejects or separately qualifies workload changes without a speed claim | Digest-bearing external artifacts, full endpoint manifests, and reviewed baseline contract |
| Space ISR | Typed report, receipt, and queue/fusion state | Scenario/topology and checkpoint validation | Space update to transactional owner-side IMINT fusion | Space effects plus reachable imaging constellation | Delayed report before/after fresh restore | Ready report changes only owner fusion track/receipt state | Schema-112 report queue, receipt ledger, and FOW fusion state |
| Documentation | Anchor severity and evidence-backed claims | MkDocs parses all pages/config | PR/main workflows run strict build | Every docs-relevant PR/push | All historical fragments resolve | N/A: documentation reports behavior but does not create it | Built site artifact and committed docs |

### State and persistence

Suite inventories, benchmark policies/artifacts, and documentation are
repository or CI state, not simulation checkpoint state. Analysis adds no
running-context checkpoint state; complete provenance is returned by every
consumer and durably stored with API batch results.

Commander assignments, bounded cumulative movement diagnostics, Space ISR
report queues, intelligence-fusion tracks, and delivery receipts are mutable
runtime state and are included in schema 112. Restore stages and validates all
of them before mutating a fresh context. Existing object-identity guarantees
for units, equipment, engines, and RNG streams remain in force. The proof
excludes programmatically enabled aggregation and nonempty ordinary FOW
contacts under the explicit REM-016/REM-029 boundaries. Legacy migration
remains limited to the repository's explicit versioned paths; a generic
dictionary is not accepted as a typed Phase 112 report.

### Configuration and failures

- Every new Pydantic model rejects unknown fields.
- Validation errors name the scenario/unit/report/metric and exact invalid
  value without dumping secrets or swallowing the cause.
- Batch, commander, roster, diagnostic, benchmark, and checkpoint restoration
  are atomic at their publication boundary.
- Omitted optional analysis/commander/space configuration retains its
  documented inert behavior. Feature-shaped misspellings do not select a
  default silently.
- A warning may describe a non-fatal modeled limitation, but it cannot replace
  rejection of invalid declared data or support a green capability claim.
- Evaluator CLI exit status is non-zero when any selected scenario has
  `LOAD_OR_RUN_ERROR`; JSON still records the complete contextual failure.

## Stochastic, statistical, and military basis

Analysis uses common random numbers: A and B receive the exact same seed at
each pair index. The paired sign test follows
[W. J. Dixon and A. M. Mood, "The Statistical Sign Test"](https://pubmed.ncbi.nlm.nih.gov/20279351/),
*Journal of the American Statistical Association* 41(236), 1946, pp. 557-566,
doi:10.1080/01621459.1946.10501898.
[NIST's paired-observation definition](https://www.itl.nist.gov/div898/handbook/prc/section3/prc311.htm)
supports analyzing `d_i` rather than treating the samples as independent, and
its [sign-test reference](https://www.itl.nist.gov/div898/software/dataplot/refman1/auxillar/signtest.htm)
supports the paired sign procedure.
[SciPy `binomtest`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.binomtest.html)
is the implementation reference for the exact two-sided `p=0.5` calculation.
Multiple-metric control follows
[Holm's sequentially rejective procedure](https://doi.org/10.2307/4615733).
The tests introduce no RNG.

Commander behavior retains the existing C2 stream and existing personality
traits. The data corrections choose an existing role, not a new calibrated
parameter:

- the Marine Corps University's
  [*Battle of al-Khafji*](https://www.usmcu.edu/Portals/218/Khafji%20Battle%20Study.pdf)
  describes the Iraqi armored attack, and the U.S. Army Special Operations
  history of
  [Debecka Crossroads](https://arsof-history.org/articles/v1n1_debecka_crossroads_page_1.html)
  records three armored counterattacks, supporting `aggressive_armor`;
- the official Marine Corps
  [*Battle for Fallujah*](https://www.usmcu.edu/portals/218/fallujah.pdf)
  identifies organized insurgent forces and their in-depth urban defense,
  supporting the existing `insurgent_leader` archetype; and
- the U.S. Army Combat Studies Institute's
  [*We Were Caught Unprepared*](https://www.armyupress.army.mil/Portals/7/combat-studies-institute/csi-books/we-were-caught-unprepared.pdf),
  pp. 45-47, records Hezbollah's organized defense at Bint Jbeil and, p. 38,
  the Hezbollah C-802 strike on INS Hanit, supporting an insurgent/non-state
  profile for Hezbollah and a naval-surface profile for the ship.

These sources support categorical force-role selection only. They do not
validate the numeric commander traits or calibrate scenario outcomes.

The Old Guard correction uses the existing `ELITE` enum as the intended tier
above `VETERAN`. The Fondation Napoléon's
[Imperial Guard history](https://www.napoleon.org/histoire-des-2-empires/articles/la-garde-imperiale-lorgueil-du-bonnet-a-poil-4-5/)
describes the Guard as an elite formation, while
[Napoleon's 1814 farewell](https://www.napoleon.org/en/history-of-the-two-empires/articles/napoleons-adieux-to-the-old-guard-at-fontainebleau-20-april-1814/)
describes long service, courage, and fidelity. This is a repository
data-repair judgment preserving the authored tier above `VETERAN`; the
evidence supports categorical veteran/elite classification, not a calibrated
numeric skill effect.

For Space IMINT, NOAA's
[geolocation-accuracy monitoring description](https://ncc.nesdis.noaa.gov/NOAA-21/NOAA21GeoError.php)
identifies ephemeris, attitude, alignment, instrument geometry, terrain, and
ground-control comparison as positional-error inputs distinct from spatial
resolution. NASA likewise assesses
[commercial satellite geolocation accuracy](https://ntrs.nasa.gov/citations/20240001672)
in pixel offsets rather than treating nominal image resolution as the complete
error model. Phase 112 therefore requires a separately sourced one-axis
position sigma and uses the standard independent isotropic measurement model
`R = diag(sigma**2, sigma**2)`; it does not infer geolocation accuracy from
ground sample distance. For the supported proof constellations, NASA's current
[commercial-imagery specification](https://science.nasa.gov/earth-science/csda/vendor-vantor/)
reports the orbit, period, nadir resolution, swath, and geolocation values
bound above for WorldView-2 and WorldView-3. The catalog uses the conservative
3.5 m CE90 bound rather than treating the published “less than” performance as
greater precision. Under the predeclared isotropic bivariate-normal
assumption, radial error is Rayleigh and
`P(R <= r) = 1 - exp(-r**2 / (2*sigma**2))`; therefore 3.5 m CE90 maps to
one-axis sigma `3.5 / sqrt(2*ln(10)) = 1.6309671062462963 m`. Keyhole and
Lacrosse fusion remain explicitly unsupported rather than borrowing that
public civil/commercial value. No geolocation noise is sampled in this phase.

Movement diagnostics consume no RNG. Space runtime retains and restores the
authoritative SPACE stream exactly, but deterministic ISR observation/report
generation currently consumes no random draw; queueing, delay eligibility,
ownership, and acknowledgement add none. Fusion preserves its existing
authoritative DETECTION stream transactionally. Benchmark timing never changes
the seed or semantic workload.

## Verification plan

### Phase-start baseline and production red proof

1. Record clean synchronization at
   `0460ac70be86784bcc6e359ae4202f4bcb938c60`.
2. Capture standard/unfiltered/marker/API/E2E collection node-ID sets, the zero
   `terrain` selection, current workflow triggers, and repository-wide Ruff.
3. Capture both current no-direct-oracle and structural/weak-oracle ledgers,
   the initial heuristic matches, and the historical-remediation ledger; then
   reproduce the named critical false or weak claims through their real
   production path.
4. Reproduce unsupported metric `0.0`, dead override acceptance, partial
   roster acceptance, and authoritative-looking sweep/comparison results.
5. Record REM-015 strict documentation success, then enable anchor warnings
   in a red test/config branch and capture all seven affected page-fragment
   targets, three malformed slug forms, and 49 affected links.
6. Reproduce 77 swallowed commander warnings and zero assignments across
   Suwalki/Korean, plus all six unresolved canonical side references.
7. Reproduce Old Guard `EXPERT` acceptance at definition load, constructor
   `KeyError`, validator exit zero, and Austerlitz 18/19 and Waterloo 19/20
   reduced rosters.
8. Record Cambrai seed-42 outcome, raw 3/10 movement, the four exact unmoved
   Mark IVs, production 5,340 m standoff, 3,000 m visibility, no tank fire,
   and false `MANY_STUCK_UNITS(4/7)`.
9. Record fresh 73 Easting warm-up/samples/semantics and Golan duration/
   semantics, including the stale 185-vs-360 tick false pass and hard
   60-vs-baseline 500 contradiction.
10. Reproduce generic Space ISR report acceptance, JSON `Position` loss,
    impossible references/times, premature clear, EW dependency, SIGINT
    mislabeling, owner/opponent track leakage, and broad
    `enable_space_effects` implicitly treating every loaded imaging
    constellation as report-capable without a typed fusion selection.

### Focused behavioral acceptance

1. Prove exact suite union, terrain installed execution, no empty partition,
   and workflow trigger/cadence parsing.
2. Run both complete current-state ledger checkers, prove no heuristic match
   is unclassified, verify the historical remediation ledger, and run every
   repaired critical behavioral test.
3. Through a real catalog-backed scenario, prove unknown metrics/overrides,
   missing units, empty/partial vectors, and malformed requests reject. Run
   controlled `hit_probability_modifier=0.0` versus `10.0` with seeds 42-44
   and prove the intended exact metric changes through sensitivity,
   comparison, doctrine comparison, Python, every `/api/analysis/*` route,
   `/api/runs/batch`, and MCP `run_scenario`, `run_monte_carlo`, and
   `modify_parameter`.
   With calibration held identical, compare two valid doctrine variants over
   common seeds and prove their intended initial and reinforcement school
   assignments plus an observable production decision/metric difference; an
   omitted-variant control must retain commander-derived assignments.
4. Prove the exact paired sign-test counts and p-value for positive, negative,
   tied, all-tied, malformed, and unequal vector controls, plus stable
   original-order tie breaking and monotone Holm adjustment across metrics.
5. Prove all six canonical side-reference corrections and that all 74 shipped
   references resolve; every applicable initial/reinforcement unit is assigned
   exactly once, unknown/duplicate profiles reject atomically, profiles affect
   production OODA/decision state, and checkpoint continuation is exact.
6. Prove invalid role/skill/category/subtype/override data fails eager loading
   and validator/evaluator status. Austerlitz must build 19/19 and Waterloo
   20/20 with Old Guard present and production-active.
7. Prove Cambrai raw movement/outcome remains semantically stable and its four
   tanks expose standoff without an engagement claim. In the invariant
   negative control, five positive production attempts with an injected
   unchanged final commit expose individual `ZERO_PROGRESS` and aggregate
   `MANY_STUCK_UNITS`; the identical default committer produces positive
   movement. Label the injection fault-detector evidence, not an ordinary
   production zero-commit capability. Separately, run five real fuel-depleted
   catalog vehicles through ordinary tactical movement and prove individual/
   aggregate resource-blocked issues, while the identical fueled control moves
   and emits neither.
8. Prove malformed/missing/performance-placeholder policies fail, semantic
   mismatch blocks a faster result, ratios at/below 1.20 pass and above fail,
   noisy samples are inconclusive, AB/BA order and warm-up exclusion are
   exact, unprofiled memory is null, and measurement-only workloads refuse a
   regression claim. Prove all named legacy absolute/unpaired gates are gone
   and bind the precommit candidate manifest exactly to the final commit tree.
9. Run fresh paired 73 Easting and manual paired Golan comparisons on the same
   host and preserve their complete JSON artifacts.

For the Phase 115 handoff only, item 9 is satisfied for 73 Easting by the
separate exact `transition_qualified` artifact and clean-final reproduction
defined above, never by paired timing across unequal inputs. Golan remains
manual and unchanged.
10. In the production loader-owned `space_isr_gap` scenario without EW, queue
    the exact eight-report blue imaging batch at 14,400 s with 7,200 s delay;
    prove no early track at 14,400 or 18,000 s, checkpoint/fresh restore typed
    equality, exact one-time blue-only delivery and eight persisted receipts
    at 21,600 s, no red mutation, exact catalog-sigma covariance,
    observation/receipt epochs,
    explicit `STALE` non-actionable status under the normal fusion lifecycle,
    no same-time duplicate, the 14,460 s observation updating the same eight
    track identities at 21,660 s rather than creating more,
    registered-satellite-pass equality, post-delivery restore,
    failure-before-acknowledgement with byte-identical retryable queue state,
    and atomic malformed-state rejection. Run the ordinary FOW/fusion lifecycle
    with ordinary sensor/contact generation absent and prove empty ordinary
    side views so REM-029 is not misrepresented. Run the exact separate
    loader-owned lifecycle fixture declared above: prove the 15,000 s
    observation at ages 300, 301, 600, and 601 s; the generated 20,280 s
    observation reactivating the same eight tracks at 20,580 s; and the
    generated 20,340 s WorldView-2/WorldView-3 same-epoch reports applying at
    20,640 s in canonical order. Also prove a transactionally rejected older
    report through the public typed production boundary and byte-identical
    state after every rejected case. Corrupt each association
    epoch/report-ID/track link and each cadence-map derivation in
    otherwise type-valid checkpoint copies, plus delivery before availability
    and delivery after checkpoint time, and prove staged restore rejects
    without mutation.
11. Prove the automated missing-fragment negative and valid-fragment controls,
    repair all seven targets/all 49 links, and run strict real docs with no
    missing-fragment diagnostic.
12. Prove affected frontend types, client parsing, tables, and charts render
    raw vectors/provenance, paired direction/counts/differences/superiority,
    raw and Holm-adjusted p-values, and family-wise significance; removed
    Mann-Whitney/rank-biserial labels must not render.

### Conditional and broad validation

Phase 112 requires `$validate-data`, `$validate-conventions`,
`$audit-determinism`, `$evaluate-scenarios`, and `$profile` because it changes
unit/scenario data, typed public/runtime boundaries, C2 and SPACE RNG-enabled
paths, scenario outcomes/diagnostics, and performance gates. Run:

- all focused Phase 112 tests;
- exact affected analysis/API/MCP, commander, unit-loader/scenario-runner,
  movement/evaluator, benchmark-infrastructure, ISR/checkpoint, and docs tests;
- all standard, API, E2E, slow-only, benchmark-only, slow-benchmark, and
  terrain-profile suites under their declared contracts;
- static data validation and production `ScenarioLoader` validation for all
  units/scenarios/eras;
- representative pre/post scenario evaluation plus the complete scenario
  evaluator;
- deterministic replay and fresh checkpoint continuation controls;
- fresh ordinary paired comparisons where workload identity is stable, or the
  strict Phase 115 73 Easting transition qualification; manual Golan remains
  separately declared;
- affected frontend behavioral tests, then `npm test`, `npm run lint`, and
  `npm run build` from `frontend/`;
- repository-wide Ruff, Python compilation, strict MkDocs, and
  `git diff --check`.

Exact Phase 112 commands, versions, counts, warnings, exclusions, wall samples,
environment metadata, scenario outcomes, artifact digests, and remaining
deficits go into `docs/devlog/phase-112.md`. Phase 115's version-4 transition
commands, classified differences, endpoint identities, artifact digests, and
explicit non-timing disposition go into `docs/devlog/phase-115.md`.

## Acceptance criteria

Phase 112 is complete only when:

1. every Python test is in an explicit standard/API/E2E/marker partition,
   terrain is a real dependency-profile run, and CI/developer documentation
   enforce the declared cadence;
2. repository-wide Ruff remains green;
3. both current-state evidence ledgers contain exact collected node IDs and
   are complete under their declared heuristics, no new match is unclassified,
   repaired nodes appear only in the historical remediation ledger with their
   behavioral proof, and no structural or weak-oracle test supports a
   behavioral capability claim;
4. analysis cannot return authoritative zeros for unknown metrics, invalid
   overrides, missing units, empty rosters, failed iterations, or absent
   vectors, and a real override changes a real metric through every consumer;
5. strict docs remain green and all current historical fragments resolve;
6. commander profiles load from one canonical side authority, all shipped
   references resolve, exact initial/dynamic assignments affect production
   behavior, and state continues across checkpoint restore;
7. invalid unit enums fail eagerly and no construction error can silently
   reduce an authored roster;
8. movement diagnostics expose exact production intent, enforce the
   zero-commit fault invariant, expose a real resource-blocked production
   negative control, and stop calling Cambrai's corrected weapon standoff a
   movement defect without claiming the injected fault as an ordinary
   production capability;
9. benchmark gates compare the same semantic workload on the same machine
   against an authoritative commit and cannot pass missing, placeholder,
   noisy, or semantically stale evidence; a reviewed unequal-workload handoff
   uses the separate non-timing transition status and cannot claim a pass;
10. Space ISR fusion has an explicit preflight-validated constellation
    selection, typed delayed owner-scoped imagery reports, real resolvable
    catalog targets, exact age-boundary/reactivation behavior, transactional
    ordering/failure semantics, and exact checkpoint continuation through
    production fusion;
11. REM-013, REM-014, REM-017, REM-022, REM-023, REM-024, REM-025, REM-026,
    and REM-027 have verified production evidence, while REM-015 remains
    green; and
12. public claims, phase status, backlog status, devlog index, and this
    specification agree after `$update-docs`, `$cross-doc-audit`, and
    `$postmortem`.

## Non-goals and accepted limitations

- REM-016 aggregation subtype/loadout reconstruction remains queued.
- REM-018 era override execution is closed by completed Phase 114. Its strict
  typed declarations, runtime wiring, declared/omitted behavioral controls,
  format-114 continuation, API fingerprint exposure, broad production
  evidence, postmortem, and explicit status transition all pass. Its timing
  result remains contention-qualified and does not claim an uncontended pass.
  REM-019 morale ownership was closed by the accepted Phase 113 production
  contract.
- REM-020 and REM-021 logistics authority remain explicit follow-ups.
- REM-028 owned the weapon-standoff versus detection/visibility mismatch and
  is closed by completed Phase 115. Phase 112 recorded it without changing
  movement or combat physics; Phase 115 supplied the accepted production,
  checkpoint/exposure, qualified broad-run, documentation, and postmortem
  evidence.
- REM-029 owns exact restoration of nonempty ordinary fog-of-war contacts,
  is assigned to planned Phase 116, and addresses what current
  `FogOfWarManager.set_state()` discards. REM-027 proves fusion
  queue/track/receipt continuation only under an explicitly empty ordinary
  world-view topology.
- Phase 117 completed the repository-wide typed claim inventory and
  fail-closed production study boundary, classifies zero claims as
  production-validated, and closed REM-030 with a truthful failed study. The
  Phase 112 relabeling did not itself establish catalog-wide validity.
- REM-031 owns per-flag semantic classification and common-seed production
  off/on evidence and remains assigned to planned Phase 118. Battalion and
  brigade runs remain `measurement_only`, not performance-regression evidence.
- Phase 112 does not recalibrate commander traits, unit skills, weapons,
  sensors, scenario outcomes, or performance workloads.
- Direct Space ISR injection into ordinary fog-of-war contacts remains
  unsupported. Aggregation-proxy commander/diagnostic lifecycle also remains
  outside the existing fusion-track and disabled-aggregation contracts.
- A weekly/manual suite cadence does not claim every expensive test runs on
  every pull request; the exact cadence is part of the exposed contract.

## Open decisions

No implementation-blocking product decision remains. Exact test module names,
workflow factoring, inventory file format, and internal type placement may be
simplified during implementation provided every requirement and observable
acceptance proof above remains intact.
