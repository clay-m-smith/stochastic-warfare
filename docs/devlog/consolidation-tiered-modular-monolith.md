# Tiered Modular-Monolith Consolidation

**Status:** Complete (subject to the [release condition](#release-condition))

**Contract:** [Tiered Modular Monolith Consolidation](../specs/tiered-modular-monolith.md)

**Started:** 2026-08-22

**Completed:** 2026-08-23

**Current update:** 2026-08-23

## Scope and status

This engineering program reorganized the repository around durable product
ownership while retaining one deterministic source revision. It is not a new
numbered phase and does not rewrite completed phase history. Phases 0--118
remain complete; Phase 119 has not started. The accepted postmortem closes
REM-052 and REM-053 and retires their planned Phases 139 and 140 before start.
REM-055 remains open, queued for Phase 142.

## Current implementation

- Strict runtime execution is now the default across factory, CLI, API,
  analysis, evaluation, and recorder/event paths. Explicit degraded mode emits
  ordered typed suppressed-failure evidence and cannot create authoritative
  results, provenance, or checkpoints.
- Deferred OODA decisions, position misinterpretation, and first/multi-vessel
  tidal-current handling use their production owners without changing RNG or
  event sequencing.
- Wind affects BVR eligibility only through the closing-axis component;
  crosswind has no signed range contribution. The sonar candidate prefilter is
  conservative through the largest supported positive acoustic multiplier
  (surface duct 3x and convergence zone 2x, combined bound 6x); the existing
  acoustic resolver remains the exact gate.
- Active tests are owned by durable domains/capabilities. Source-local evidence
  annotations and compact typed receipts replace exact expanded-node ledgers.
- One revision-bound partition manifest drives the standard, slow-only,
  benchmark-only, slow-benchmark, API, and E2E shards. PR/main runs ordinary partitions and
  policy checks; daily extended CI routes the generated slow/benchmark matrix;
  73 Easting paired work is nightly or explicit dispatch; Golan is manual.
- Current docs and claim scanning distinguish living current truth from
  immutable phase/devlog history. Large generated evidence remains ignored or
  on the separately retained full-evidence branch.
- `ApplicationPaths` owns checkout, packaged, and external resources plus
  separate mutable state paths. Catalog names are location-independent;
  explicit relative scenario paths intentionally resolve from the invocation
  working directory.
- The wheel/sdist use exact regular-file allowlists and reject implicit,
  ignored, symlinked, stale-build, or Git-hidden inputs. The wheel contains the
  product CLI and YAML catalog, excludes the frontend/history/evidence, and
  supports verified no-Git source identity. Checkout runtime provenance binds
  clean and dirty raw import/script closures, including the complete dirty
  index, and publishes only after equal stable captures. Packaged identity uses
  the same double-verification boundary. API and MCP dependencies remain
  optional extras.
- FastAPI's production OpenAPI document generates the tracked TypeScript
  transport aliases; handwritten validators retain semantic responsibility.
- MCP resources expose normalized path-free IDs, reject symlinks and catalog
  escape, and use a bounded process-local result store. Legacy scenario-runner,
  Monte Carlo, historical-data, and pickle compatibility are quarantined from
  authoritative paths.
- Scenario and loadout compatibility facades now delegate to focused config,
  context, checkpoint, loader, contract, registry, attachment, and builder
  owners. Effective calibration is recursively immutable, and checkpoint
  participants have explicit atomic, legacy-clone, or stateless dispositions.
- `BattleManager` injects OODA, movement, engagement, and checkpoint executors.
  Their frozen least-privilege runtime views contain no `SimulationContext` or
  `Any`; live unit identities and named mutable domain owners are exposed only
  where authorized.
- The legacy FOW update path now fails explicitly and one current targeting/FOW
  snapshot is reused. The accepted postmortem closes REM-052 and REM-053 on
  those verified boundaries without changing checkpoint format 118.
- `.agents/skills/` is the canonical workflow source; `.claude/skills/` is a
  validated generated regular-file projection.

## Test and CI inventory

The release-candidate partition audit collects **12,893** pairwise-disjoint
Python tests:

| Partition | Nodes |
|---|---:|
| standard | 12,265 |
| slow-only | 108 |
| benchmark-only | 128 |
| slow-benchmark | 7 |
| API | 344 |
| E2E | 41 |

These counts are a dated consolidation receipt, not a permanent coverage
oracle. CI acceptance is relational: the partitions must be disjoint, their
union must equal the locked superset, and each shard must consume the same
revision-bound audit manifest.

Preliminary pass-A execution evidence from before the final provenance
hardening is green across fresh-collection and revision-bound receipts:
standard 12,261/12,261, slow-only 108/108, benchmark-only 128/128,
slow-benchmark 7/7, API 344/344, and E2E 41/41. The four added standard
provenance controls pass their focused and full-consumer gates. The
intentionally overlapping benchmark-policy and terrain profiles also passed
129/129 and 97/97, respectively. The slow-only receipt includes the corrected
Falklands AI-event oracle, which now verifies the production recorder
projection rather than expecting an empty event set. These runs span fresh
collections plus the pre-fix and post-fix revision manifests. The released
tree must also satisfy the single-revision condition below.

## Performance evidence

The completed Phase 118 REM-055 evidence is unchanged. On the matched
ten-tick `benchmark_battalion` workload, its median moved from 47.035449 s to
59.220597 s (1.259063x, +12.185148 s, +25.906%). The matched profiles recorded
436,345,008 calls / 116.744514 s versus 497,301,086 calls / 138.727831 s;
transactional FOW cumulative time moved from 5.794983 s to 23.733829 s, a
17.938846 s contribution equal to 81.60% of that instrumented delta. This is a
qualified workload-specific regression, not a universal throughput claim.

The matched R16 executor-boundary sample recorded:

| Statistic | Consolidated boundary | Comparison boundary | Ratio |
|---|---:|---:|---:|
| median | 0.010538683 s | 0.010371553 s | 1.016x |
| mean | 0.010285734 s | 0.010440483 s | 0.985x |

The ranges overlap. This supports no speedup or slowdown claim.

A separate matched profile isolated the consolidation's checkpoint-capture
path for REM-053. It used five interleaved blocks per revision, each with two
warmups and seven measured captures (35 observations per revision). The
consolidation-base median was 11.288641 ms and the current median was
4.506367 ms, a 0.399195 ratio. The same run proved exact restored state,
continuation, replay, recorder output, and RNG state. This is dedicated
checkpoint-path evidence, not a universal runtime-speed claim. The accepted
postmortem closes REM-053 subject to the transactional release gate below.

The canonical paired 73 Easting production comparison also completed. Its
reference median was 2.757796 s and candidate median was 3.144280 s; the median
of paired ratios was 1.136065, below the predeclared 1.20 benchmark-policy
limit. The candidate was nevertheless 13.61% slower by that paired ratio. The
comparison preserved the semantic projection exactly, but it ran with FOW
disabled and therefore neither demonstrates recovery of the transactional-FOW
regression nor closes REM-055. That remediation remains queued for Phase 142.

## Scenario regression evidence

The seed-42 production evaluation completed all 46 scenarios in the
evaluator's maintained inventory. That inventory excludes four test-campaign
fixtures and the two benchmark workloads from the 52 scenario YAML files.
Winners, messages, ticks, durations, force state, casualties, combat metrics,
and tactical issues were exact against the retained baseline. Thirty-five rows
were entirely exact; ten differed only in newly exposed recorder events; and
Taiwan differed in recorder projection plus a tiny movement delta. The same
seven scenarios retained the same structured warning set. This is a broad
software-regression receipt only: no baseline was promoted, no historical
outcome envelope was evaluated, and no historical-validation claim follows.

## Release condition

The Complete status and the REM-052/REM-053 closures are valid only for a
frozen revision whose final release gate binds the partition, migration, claim,
provenance, and build receipts to that revision and passes every required
closure check. Any failure revokes these status transitions and forbids the
consolidation commit; a green gate permits the coherent commit.

## Postmortem

**Date:** 2026-08-23

**Verdict**

- **Scope:** On target. The program repaired the identified safety defects,
  moved active verification to durable ownership, hardened application and
  evidence boundaries, and split the planned coordinators without changing
  the accepted simulation model or checkpoint format.
- **Quality:** High. Strict failure authority, least-privilege executor views,
  deterministic state ownership, fail-closed provenance/build rules, and
  behavioral replacement evidence are present; no placeholder or proxy is
  accepted as closure proof.
- **Integration:** Fully proven by the recorded pass-A production-path,
  continuation, scenario, API, E2E, slow, benchmark, terrain, packaging, and
  interface evidence. The release-binding condition above is mandatory.
- **New deficits:** None. REM-055 is a pre-existing, independently owned
  transactional-FOW performance deficit and remains open for Phase 142.

**Validation**

- The release-candidate audited Python union contains 12,893 nodes: standard
  12,265, slow-only 108, benchmark-only 128, slow-benchmark 7, API 344, and
  E2E 41.
  Earlier pass-A execution is green for every partition at its recorded
  revision; the final provenance controls pass focused and full-consumer
  verification. The overlapping benchmark-policy and terrain profiles passed
  129/129 and 97/97.
- The seed-42 production evaluator completed 46/46 maintained scenarios with
  exact winners and semantic outcomes: 35 exact rows, ten recorder-only
  differences, and one Taiwan recorder-plus-tiny-movement difference. The
  warning set was unchanged. No baseline was promoted.
- The dedicated checkpoint profile recorded 11.288641 ms at the consolidation
  base versus 4.506367 ms current, a 0.399195 ratio, while preserving exact
  restored state, continuation, replay, recorder output, and RNG state. This
  is checkpoint-path evidence, not a universal speed claim.
- Canonical paired 73 Easting recorded a 1.136065 median paired ratio, below
  the 1.20 policy limit, while the candidate remained 13.61% slower. Its
  semantic projection was exact, but FOW was disabled, so this does not close
  REM-055.

**Exclusions and action**

The manual Golan comparison was not run. No held-out study, calibration, or
historical outcome-envelope promotion was performed, and none is claimed. The
postmortem authorizes REM-052 and REM-053 closure and retirement of Phases 139
and 140 before start under the frozen-revision release condition above. A
failure reopens the program and both remediations with no commit; a fully green
gate permits the verified consolidation commit.

Raw manifests, run artifacts, profiles, and expanded test-node inventories are
deliberately not copied into this log.
