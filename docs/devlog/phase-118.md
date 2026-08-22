# Phase 118 - Performance-Flag Semantic Integrity

**Status:** Complete

**Remediation:** REM-031

**Started:** 2026-08-03

**Completed:** 2026-08-22

## Objective

Replace Block 9's one-sided performance-flag checks with a typed,
same-revision, same-data production comparison for all five governed flags.
Classify each flag before observing results, prove that its real production
branch executes, preserve deterministic and checkpoint continuation behavior,
and fail closed when semantic support is absent.

Performance timing was deliberately outside the semantic verdict. No study
result below establishes a speedup.

## Start gate

Phase 118 began from the synchronized Phase 117 commit
`84cf4c4461a7d4a9f17c2578ea323a0a21d5bbe8` after reading the repository
guidance, Block 13 roadmap, REM-031, affected production path, checkpoint
contract, and applicable workflow skills. The governing contract is
[Performance-Flag Semantic Integrity](../specs/performance-flag-semantic-integrity.md).

## Contract and classifications

The immutable production registry classifies the five flags:

| Flag | Classification | Required meaning |
|---|---|---|
| `enable_detection_culling` | Semantics-preserving execution optimization | Conservative selection may prune only work rejected before mutable scan state or an RNG decision. |
| `enable_scan_scheduling` | Model-fidelity approximation | Authored intervals intentionally omit off-interval sensing opportunities. |
| `enable_lod` | Model-fidelity approximation | Only sensing cadence may change; engagement, morale, movement, damage, and all other state owners remain full-rate. |
| `enable_soa` | Semantics-preserving execution optimization | Read-only array selection may change admitted work, not authoritative state or ordering. |
| `enable_parallel_detection` | Semantics-preserving execution optimization | Dispatch alone may differ; state, event order, indexed decisions, and continuation remain exact. |

On 2026-08-22 the owner approved Option A for the v7 Suwalki proof topology.
Exactly three period-five same-identity recovery-work totals aggregate over the
complete frozen sixteen-pair case. Every other branch, semantic budget, source,
seed, attempt, projection, and failure condition remains per pair. Missing,
forged, incomplete, or false aggregate evidence is `ERROR`, never a favorable
omission.

## What validation uncovered

The early validation failures were substantive, not flaky gates:

- sequential and threaded FOW used different random-number topology, so
  dispatch mode and omitted opportunities shifted later draws;
- scan scheduling's modulo phase could synchronize equal sensors into a blind
  interval and interact with LOD to starve work;
- legacy culling geometry could exclude valid closed-range boundary points;
- LOD skipped engagement work and compounded morale cadence instead of changing
  sensing alone;
- repeated same-epoch reports were treated as independent Kalman measurements,
  spuriously shrinking covariance and incrementing hits;
- a deferred fire-control radar discarded exact observer support even while
  its fused track remained valid; and
- checkpoints could not prove complete cadence, indexed-decision, receipt, and
  observer-support continuation.

Factory-backed production red controls reproduced the RNG/semantic mismatch,
the native-deferral `NO_CONTACT` regression, and the correlated-fusion double
update before the accepted implementation.

## Why terminal evidence took several attempts

The evidence lineage is retained as historical context because it explains the
long validation stage:

| Revision | Result | Reason |
|---|---|---|
| v1-v2 drafts | Rejected before acceptance | Diagnostic seeds disproved winner-exact and grouped-terminal assumptions; skipped opportunities also phase-shifted RNG. |
| v3 | Semantic misses, then `ERROR` | Native scheduling produced real covariance/state/event misses; aggregate publication later exceeded its capacity. |
| v4 | `ERROR` | Strict format-118 JSON correctly rejected an internal positive-infinity assessment value, and repeated semantic publication work exhausted the manifest window. |
| v5 | `ERROR` | All pair workers completed, but five full shard audits were incorrectly charged to one manifest-only deadline. |
| v6 | Terminal `ERROR` | All 96 pairs / 396 attempts published, but Suwalki recovery proof was lossy at terminal state and could not distinguish retired identities from missing work. |
| v7 | Eligible `FAIL` | The owner-approved complete-case recovery proof closed the evidence-integrity gap; scan scheduling and Suwalki LOD then missed their frozen budgets. |

None of these failures authorized widening a budget, changing a source,
discarding a pair, tuning combat data, or reusing an observed seed for
acceptance. Infrastructure also contributed wall time: heavy shards ran on a
contended host, ordinary asyncio entered a host-specific selector deadlock,
and source-fingerprint changes correctly invalidated stale attempts. Those
conditions delayed evidence but did not alter the final semantic verdict.

## Production implementation

Phase 118 established one production-owned semantic boundary:

- `CalibrationSchema` retains five strict booleans and strict positive LOD
  cadence fields.
- `PERFORMANCE_FLAG_REGISTRY` owns canonical order, classification, support
  disposition, required meaning, and retained v7 verdict.
- `SimulationRuntimeFactory` remains the construction authority; typed variants
  and runtime owners cross-bind authored, typed, flattened, and receipt values.
- `TacticalCadenceScheduler` owns deterministic attachment identity,
  independent native/LOD readiness, non-starving admission, online/offline and
  reinforcement lifecycle, and checkpoint continuation.
- `RNGManager` owns identity-addressed Philox FOW decisions. Sequential and
  parallel dispatch consume the same canonical lanes without advancing the
  conventional detection stream.
- Culling uses a conservative closed envelope; SoA selection is read-only; and
  parallel detection commits only a complete canonical side union.
- LOD changes sensing cadence only. Engagement, morale, movement, damage, and
  other non-sensing work remain full-rate.
- Same-side, same-target, same-epoch fusion validates the full group, predicts
  detached state once, selects one canonical best-variance representative,
  and performs one atomic update or replacement.
- Observer-track support binds exact attachment, target, track generation,
  native expiry, estimate, and covariance without copying live truth into
  evidence.
- Performance receipts reconcile selection, cadence, detector, fusion, indexed
  RNG, dispatch, SoA, and LOD work and persist through format-118 checkpoints.
- Stored targeting frames use one strict format-118 decoder shared by API and
  replay, including bounded legacy migration and atomic failure behavior.

The shared checkpoint decoder rejects duplicate keys, non-finite JSON,
malformed NumPy markers, coercion, incomplete owner topology, and
cross-owner counter drift before mutation. Never-fired weapon timestamps and
the separately typed positive-unbounded force ratio use exact `null` encodings.

## Terminal evidence and disposition

The schema-2 v7 plan is
`phase118-performance-semantics-v7`, canonical plan SHA-256
`5ffb74205281d8913b618fc607f47bf4cdccc0f2741bd812cc82989761c1b41d`.
It completed all 96 pairs / 396 attempts once under
`EXTERNALLY_CONTENDED`. Independent strict reload reproduced manifest
artifact SHA-256
`bf9e00ce4a7774af29b5657c49bbbe4481b407a966d9922e48970022f5c6ad86`
and eligible aggregate `FAIL`.

| Case | Result |
|---|---|
| Detection culling | 16/16 `PASS` |
| SoA selection | 16/16 `PASS` |
| Parallel detection | 16/16 `PASS` |
| Scan scheduling | 3/16 `PASS`, 13/16 `FAIL`, including one winner reversal |
| Calibration LOD | 16/16 `PASS` |
| Suwalki LOD | 12/16 `PASS`, 4/16 `FAIL` on the frozen covariance budget |

The accepted complete-case Suwalki recovery totals passed at 74 recovery
admissions, 37 admissions with indexed work, and 185 indexed detection blocks.
V7's failures therefore represent eligible negative semantics, not incomplete
branch evidence.

The v6 predecessor completed the same topology but remains terminal `ERROR`,
artifact SHA-256
`eb8e12f147c14ee4e83e7f5e80e4b1e50aa2bfe847d5e5e681b2462f7850051a`.
It is not reloaded under v7 rules or described as a failed semantic verdict.

Raw study artifacts and one-off machinery are intentionally retained off main.
Each locator below is bound to immutable Git commit
`ebcb888a59d4259ccc1e9149cc0a7364f2a65853`:

- `branch=evidence/full; path=docs/evidence/phase-118/v6-terminal/`
- `branch=evidence/full; path=docs/evidence/phase-118/v7-terminal/`
- `branch=evidence/full; path=docs/evidence/phase-118/runtime-manifest-handoff.json`
- `branch=evidence/full; path=data/validation/performance_semantics/phase118.yaml`

The handoff preserves the exact 1,408-entry execution snapshot
(`2f10ab7c7a2b409067c90f92616609e921750fa7641c4d3165f90b53fa21e9a8`)
and reviewed retirement snapshot
(`0a6b32a48fd7ea764d6522eb7ebccdc32c803663aed295c916ba47240668bf07`)
through fifteen content-addressed modifications. Its self-digest is
`b505edc418f87ffdf659bed52b502cef043df472c8a04696d0fda8d99d4e746d`.
The handoff remains evidence history, not a current runtime dependency.

The owner approved qualified-negative closure:

- culling, SoA, and parallel detection are
  `supported_exact_validated`;
- scan scheduling and LOD retain their model-fidelity classification but are
  `unsupported_failed_semantic_validation`;
- current production rejects either unsupported flag enabled and rejects
  non-default LOD tuning at scenario, API, analysis, runtime, manager, receipt,
  and current-checkpoint boundaries; and
- the benchmark battalion and brigade explicitly keep both unsupported
  controls false.

`GET /api/meta/performance-flags` exposes the five-entry order,
classification, support disposition, required meaning, v7 identity, manifest
digest, and retained per-flag verdict. It does not expose raw artifacts.

## API, replay, and frontend exposure

Privileged targeting decisions contain required-nullable observer-track
support. SIDE_FOW exposes only the side-safe opaque projection. The shared
stored-frame decoder validates schema, runtime FOW mode, root roster, exact
side set, view associations, tick, decisions, and outcomes before API or replay
returns data.

Format 118 emits its schema marker and FOW mode even for empty frames. Complete
Phase 115--117 paired frames retain bounded compatibility; a bare unversioned
empty frame rejects because it cannot be distinguished from stripped current
state. New supported production runs emit no non-null observer support because
the only controls that can reach that path are currently rejected.

Frontend schema, tests, lint, and build passed during closure. Existing React,
jsdom, browserslist-age, and bundle-size advisories were classified rather than
suppressed. No frontend result supports a speed claim.

## Capability-stage status

| Stage | Closure evidence | Status |
|---|---|---|
| Declared | Strict fields and immutable registry declare classification, support, meaning, and v7 verdict. | Verified |
| Loaded | Factory/config/API/analysis load supported values and reject positive/non-default retired inputs. | Verified |
| Wired | `SimulationEngine -> BattleManager -> FogOfWarManager` reconciles supported branch work and owner bindings. | Verified |
| Enabled | Three supported flags have material off/on controls; positive scan/LOD enablement is intentionally N/A. | Verified with stated N/A |
| Exercised | The archived study exercised all five; main retains direct tests for three supported routes and two rejection routes. | Verified |
| Outcome-affecting | Supported flags change controlled work without normalized drift; retired flags caused real frozen-budget misses. | Verified without relabelling `FAIL` |
| Persisted/exposed | Receipts/checkpoints, API status, docs, and off-main immutable evidence expose the disposition. | Verified |

## Direct behavioral evidence retained on main

The lean main branch keeps the production regressions and removes only the
retired study harness. The retained direct surface includes:

- `tests/unit/test_phase118_performance_flags.py` and
  `tests/unit/test_phase118_unsupported_runtime_guard.py`;
- `tests/unit/test_phase118_indexed_rng.py`,
  `tests/unit/test_phase118_context_indexed_rng.py`, and
  `tests/integration/test_phase118_rng_culling.py`;
- `tests/unit/test_tactical_cadence.py` and
  `tests/integration/test_phase118_cadence_lod.py`;
- `tests/unit/test_phase118_correlation_safe_fusion.py`,
  `tests/unit/test_phase118_observer_track_support.py`, and
  `tests/unit/test_phase118_fow_observer_support.py`;
- `tests/unit/test_phase118_fow_receipts.py`,
  `tests/integration/test_phase118_receipt_checkpoint.py`, and
  `tests/integration/test_phase118_observer_support_continuation.py`;
- `tests/integration/test_phase118_soa_factory.py`;
- `tests/unit/test_phase118_checkpoint_decoder.py`,
  `tests/unit/test_phase118_noncoplanar_geometry.py`, and
  `tests/unit/test_phase118_calibration.py`; and
- `tests/api/test_phase118_observer_support_api.py` and
  `tests/api/test_phase118_performance_support_api.py`.

These tests assert state, branch work, RNG identity, atomicity, continuation,
API errors, and exposed data. Imports, source inspection, mocked calls,
constructors, and no-crash runs receive no behavioral completion credit.

Closure also included Ruff, strict documentation, complete data/catalog,
historical-claim, scenario, deterministic, API, frontend, E2E, slow, benchmark,
and Python partition validation. The archived full-evidence tree included its
own terminal-artifact tests; those one-off tests are not part of lean main and
their former collection counts are not presented as current main counts.

## Scenario and performance qualification

The final production scenario sweep completed 46/46 scenarios with no
failures or errors and an exact normalized match to the clean Phase 117
reference for seed 42. This is current-engine regression evidence for one seed,
not historical validation, distributional equivalence, or a speed claim.

The separate matched profile found a real gross regression on
`benchmark_battalion`. After one discarded warm-up per revision, the
phase-start ten-tick median was 47.035449 seconds and the Phase 118 median was
59.220597 seconds, ratio 1.259063 (+25.906%). Both revisions produced the same
ten-tick, 50-second, blue `max_ticks` result. A matched profile placed 81.60%
of the instrumented delta beneath transactional FOW update. Overlapping
descendants are not additive savings estimates.

The semantic study had no timing threshold, so the profile neither changes its
verdict nor creates a speed claim. REM-055 / Phase 142 owns a separate frozen
timing/call/memory optimization contract.

## Review status

The applicable specification, research, design, determinism, comparison,
data, scenario, convention, profile, simplification, documentation,
cross-document, and postmortem routes completed.

Independent review found and repaired:

- unsupported-flag bypasses across authored, typed, flattened, receipt, and
  checkpoint owners;
- missing atomic and tamper checks;
- stored-frame downgrade paths;
- terminal seed/plan execution gaps; and
- the absent required profile result.

The final cross-document audit passed all ten areas. Two independent final
postmortem reviews returned `ACCEPT`. The profile finding remained visible as
REM-055 rather than being hidden by semantic success.

## Tracked follow-ups

Phase 118 does not absorb adjacent defects:

- **REM-041 / Phase 128:** projection integrity is not caller authorization.
- **REM-044 / Phase 131:** sourced per-sensor range, bearing, correlation, and
  operating-envelope models remain absent; the current isotropic uncertainty
  proxy is not historical sensor accuracy.
- **REM-051 / Phase 138:** one battle resolution can clear unrelated detection
  scan history.
- **REM-052 / Phase 139:** the legacy FOW update retains a second scan/fusion
  implementation beside the transactional owner.
- **REM-053 / Phase 140:** checkpoint capture repeatedly stages the same mutable
  FOW graph.
- **REM-054 / Phase 141:** future scan/LOD re-enablement requires a sourced
  redesign, a new plan, fresh disjoint inputs, and accepted evidence.
- **REM-055 / Phase 142:** reduce the measured transactional FOW cost without
  weakening atomicity, tamper detection, stochastic identity, continuation, or
  semantic outcomes.

## Postmortem

Formal verdict: **ACCEPT**.

The first closure review rejected only the missing required profile gate. The
matched production profile repaired that omission, documented the +25.906%
regression, and assigned it to REM-055 without removing an integrity check or
changing a semantic threshold.

The accepted closure keeps an honest boundary: three flags have complete
supported production evidence; scan scheduling and LOD retain their eligible
`FAIL` and reject current activation. The raw v6/v7 evidence remains immutable
off main, while main retains production code, direct behavioral regressions,
support identity, API/checkpoint exposure, documentation, and tracked
limitations. Phase 118 and REM-031 are closed. Phase 119 remains not started.
