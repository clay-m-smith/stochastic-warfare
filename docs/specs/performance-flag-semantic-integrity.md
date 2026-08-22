# Performance-Flag Semantic Integrity

**Status:** Complete. The owner-approved qualified-negative disposition,
cross-document audit, and accepted postmortem closed Phase 118 / REM-031.

**Owner:** Phase 118 / REM-031 (closed)

## Evidence disposition

The frozen schema-2 study identity is
`phase118-performance-semantics-v7`, with canonical plan SHA-256
`5ffb74205281d8913b618fc607f47bf4cdccc0f2741bd812cc82989761c1b41d`.
It completed all 96 pairs / 396 attempts once under the declared
`EXTERNALLY_CONTENDED` qualification. Independent strict reload reproduced
manifest artifact SHA-256
`bf9e00ce4a7774af29b5657c49bbbe4481b407a966d9922e48970022f5c6ad86`
and the eligible aggregate `FAIL`.

Detection culling, SoA selection, and parallel detection each passed 16/16.
Scan scheduling passed 3/16 and failed 13/16, including one winner reversal.
Calibration LOD passed 16/16; Suwalki LOD passed 12/16 and failed 4/16 on the
frozen covariance budget. The three owner-approved complete-case Suwalki
recovery totals passed at 74, 37, and 185. These are semantic results only; the
study contained no speed threshold and supports no performance claim.

The predecessor v6 study completed the same 96-pair / 396-attempt topology but
remained terminal `ERROR`, artifact SHA-256
`eb8e12f147c14ee4e83e7f5e80e4b1e50aa2bfe847d5e5e681b2462f7850051a`.
It was never reinterpreted as a verdict. V7 corrected only the approved
schema/proof topology with fresh inputs; it did not widen a semantic budget,
change a source, or tune simulation data after observing a miss.

Raw study inputs, implementation, terminal artifacts, checksums, and the exact
execution-to-retirement handoff are intentionally absent from main:

- `branch=evidence/full; path=docs/evidence/phase-118/v6-terminal/`
- `branch=evidence/full; path=docs/evidence/phase-118/v7-terminal/`
- `branch=evidence/full; path=docs/evidence/phase-118/runtime-manifest-handoff.json`
- `branch=evidence/full; path=data/validation/performance_semantics/phase118.yaml`

The handoff binds execution snapshot SHA-256
`2f10ab7c7a2b409067c90f92616609e921750fa7641c4d3165f90b53fa21e9a8`
to reviewed retirement snapshot SHA-256
`0a6b32a48fd7ea764d6522eb7ebccdc32c803663aed295c916ba47240668bf07`
through fifteen content-addressed modifications; its self-digest is
`b505edc418f87ffdf659bed52b502cef043df472c8a04696d0fda8d99d4e746d`.

Those retained bytes are development evidence, not production runtime inputs.
All observed v4--v7 seeds remain burned diagnostics. A future acceptance study
requires a new numbered remediation, a new plan identity, and fresh untouched
inputs. Main retains the production contract, behavioral regressions, support
registry, failure behavior, and the immutable evidence identities needed to
explain the disposition.

On 2026-08-22 the owner accepted the v7 Option A proof topology: exactly the
three period-five same-identity Suwalki recovery-work totals aggregate across
the complete predeclared sixteen-pair case, while every other branch and
semantic requirement remains per pair. The observed v7 misses remain `FAIL`;
this decision did not convert them to `PASS`.

## Purpose and authority

Phase 118 replaces Block 9's one-sided authored-configuration checks with one
typed, paired production contract for these five calibration controls:

- `enable_detection_culling`;
- `enable_scan_scheduling`;
- `enable_lod`;
- `enable_soa`; and
- `enable_parallel_detection`.

The contract distinguishes execution optimizations from model-fidelity
approximations before any paired candidate result is inspected. It does not
infer semantic equivalence from a matching winner, a no-crash run, a source
search, or failure to find a statistically significant difference.

The production path governed by this contract is:

```text
SimulationRuntimeFactory.prepare -> PreparedScenario.build
  -> RuntimeSession.step/checkpoint/restore
  -> SimulationEngine -> BattleManager -> FogOfWarManager
  -> typed performance receipts -> recorder/API/checkpoint surfaces
```

`SimulationRuntimeFactory` remains the only scenario/runtime construction
authority. Validation may select sparse typed variants, but it may not mutate a
constructed context, replace a production subsystem, mock a branch, patch a
combat parameter, or call a private helper as behavioral evidence.

## Predeclared flag classification

One production-owned, immutable registry shall classify every governed flag
exactly once. The registry order shown here is canonical across production, API, checkpoint,
and retained evidence projections.

| Flag | Classification | Required meaning |
|---|---|---|
| `enable_detection_culling` | semantics-preserving execution optimization | The STRtree may omit only target checks that the canonical detection engine would reject before mutable scan state or an RNG draw. |
| `enable_scan_scheduling` | model-fidelity approximation | Sensors with an authored interval greater than one intentionally omit detection opportunities on off-ticks. |
| `enable_lod` | model-fidelity approximation | Nearby and distant sensor attachments intentionally scan less often. Engagement, morale, movement, damage, and every other state owner remain full-rate. |
| `enable_soa` | semantics-preserving execution optimization | A read-only array snapshot may select in-range targets, but authoritative unit state, target order, and admitted work must remain unchanged. |
| `enable_parallel_detection` | semantics-preserving execution optimization | Only dispatch may differ. Side results, all authoritative state, event order, RNG continuation, and checkpoint continuation must be identical. |

## Post-v7 production support disposition

Semantic classification and production support are orthogonal typed fields.
The v7 result does not reclassify either approximation as an execution
optimization and does not weaken any frozen budget. The final production
registry shall expose this exact disposition, bound to plan
`phase118-performance-semantics-v7` and manifest artifact SHA-256
`bf9e00ce4a7774af29b5657c49bbbe4481b407a966d9922e48970022f5c6ad86`:

| Flag | Support disposition | Retained v7 shard verdict |
|---|---|---|
| `enable_detection_culling` | `supported_exact_validated` | `PASS` |
| `enable_scan_scheduling` | `unsupported_failed_semantic_validation` | `FAIL` |
| `enable_lod` | `unsupported_failed_semantic_validation` | `FAIL` |
| `enable_soa` | `supported_exact_validated` | `PASS` |
| `enable_parallel_detection` | `supported_exact_validated` | `PASS` |

The strict calibration fields remain present so old or hostile input receives
one explicit error rather than being ignored or silently renamed. A production
value of `true` for either unsupported control shall fail at the shared typed
calibration boundary. This rejection applies equally to scenario YAML, API run
and analysis requests, sparse runtime variants, direct runtime preparation,
and any current checkpoint restore before live state mutates. Explicitly
authored non-default LOD interval or hysteresis tuning is also rejected while
LOD is unsupported; schema-default values remain decodable but inert. Manually
constructed contexts and managers shall not bypass the runtime-owned guard.

The two shipped measurement-only benchmark scenarios shall stop activating the
unsupported controls. The immutable schema-2 v7 artifact is retained off main
at `branch=evidence/full; path=docs/evidence/phase-118/v7-terminal/`. It is
not a current runtime input and must not be resumed, reaggregated, relabelled,
or promoted. Any future re-enablement requires a separately numbered
remediation, a revised specification, production red proof, fresh inputs
disjoint from every burned set, and accepted new evidence. Documentation or a
warning alone is not a supported implementation.

`GET /api/meta/performance-flags` shall expose the same canonical five-entry
registry, classification, support disposition, required meaning, v7 plan and
manifest identity, and retained per-flag shard verdict. The route is a typed
support-status projection, not a copy of the raw semantic artifacts. Python
and API projections must be exact and duplicate-free; frontend duplication is
not required because no current UI consumes this configuration surface.

The culling selector must use a conservative geometric envelope. For each
observer it must admit every target whose canonical 2-D Euclidean distance is
less than or exactly equal to the maximum effective range of any operational
attached sensor; extra candidates are permitted because the production
`DetectionEngine` remains the final per-sensor range/domain authority. A
polygonal circle that is inscribed inside that closed range is forbidden. The
production implementation shall query an exact closed-distance predicate or a
closed axis-aligned square envelope, restore canonical target order, and let
the ordinary detection boundary reject conservative false positives without
an extra draw. Focused tests place targets at cardinal and inter-vertex
diagonal boundary bearings, plus the adjacent representable distances just
inside and outside range, and require exact culling-off/on detection state and
RNG continuation.

`enable_scan_scheduling` and `enable_lod` shall be described as unsupported
model controls, not transparent speedups, in public configuration
documentation. Existing field names remain decodable only to deliver the
explicit unsupported error; Phase 118 does not silently rename or ignore
scenario YAML. Any future reclassification or re-enablement requires a new
numbered phase, a revised specification, and new evidence.

## Corrected cadence, estimation, and RNG design

The cadence, LOD, observer-support, and evaluator design below is the retained
production contract exercised by v7. It explains the observed failures but is
not a claim that the two failed approximation controls remain activatable.
Current production rejects their activation and non-default LOD tuning at the
shared support boundary described above.

### Stateful, non-starving sensing cadence

LOD shall no longer gate engagement initiation or morale. The baseline's bare
engagement `continue` discarded cooldown-eligible fire, ammunition, events,
damage, and suppression rather than approximating elapsed work. Morale was
already called only every 12 battle ticks; composing that with LOD intervals
of 5 or 20 reduced it to an accidental least-common-multiple cadence, while
the default discrete-time morale model ignored accumulated elapsed time.
Neither behavior is a defensible LOD approximation. Engagement, morale,
movement, damage, and every other non-sensing owner remain at their ordinary
production cadence.

One typed, checkpointed `TacticalCadenceScheduler` shall own scan readiness.
Its exact attachment identity is
`(reporting_side, observer_unit_id, source_equipment_index, sensor_id,
modeled_role)`. Its native phase group is the typed key
`(reporting_side, sensor_id, modeled_role, native_period)`. The catalog sensor
ID is bound through the production runtime's exact catalog/loadout
fingerprints and checkpoint preflight. Display names, observer positions,
target sets, probabilities, operational state, LOD tier/period, and RNG values
never enter the group or phase assignment. Opposing sides therefore never
share a phase group.

The scheduler stores the schema, committed tactical-interval ordinal, the
monotonic `complete_from_tick_zero` evidence bit, a complete native-phase
assignment registry, last committed admission, native assignment ordinal and
phase residue, native-sensor next-due interval and pending-ready bit, LOD
next-due interval and pending-ready bit, and current applied LOD period.
`BattleManager` remains the sole authority for unit tier, hysteresis, pending
demotion, and witness-driven promotion; the scheduler receives a staged
immutable tier map and its period mirror must cross-validate against that map.
The native period is the authored `scan_interval_ticks` when scan scheduling
is enabled and 1 otherwise. The LOD period is 1 for ACTIVE, the strict nearby
period for NEARBY, and the strict distant period for DISTANT.

The global FOW tactical ordinal starts at zero and advances only after one
complete all-side FOW interval commits successfully. Phase assignments are
part of that same transaction. For each group, attachments first encountered
in one complete-roster transaction are ordered by the full
`TacticalAttachmentIdentity.sort_key()`. The assignment ordinal is the number
of earlier committed assignments in that group and the immutable native phase
residue is `assignment_ordinal % native_period`. A failed or aborted interval
commits no assignment and consumes no group ordinal. Assignment records remain
in the canonical registry after an attachment leaves the active roster. A
reappearing exact identity reuses its record; canonically ordered
reinforcements receive later group ordinals and never rephase incumbents. For
every committed assignment prefix, per-residue assignment counts differ by at
most one. Period one always has residue zero. In the frozen calibration source,
each side's two equivalent period-two attachments therefore receive residues
zero and one.

Every new or returning attachment is still first-ready: both readiness bits
start set and the initial sweep remains immediate. After an admission at
ordinal `n`, native `next_due` is the least representable integer `d > n` such
that `d % native_period == native_phase_residue`. The initial first-ready
state uses the same formula for its future native deadline. Thereafter, when
`ordinal >= next_due`, the corresponding bit becomes set and the deadline
advances by the smallest positive whole multiple of its period that makes it
greater than the current ordinal. A set bit remains set until consumed. A scan
executes only when both independent readiness bits are set, then consumes both
bits without resetting either deadline. An unrepresentable next deadline
rejects the complete transaction; it never saturates or changes residue.

Native period is immutable for a runtime. On an LOD period change at ordinal
`n`, let `a` be the last admission ordinal. Existing pending readiness always
survives. For a promotion (`new < old`), set
`next_due = min(old_next_due, max(n + 1, a + new))`; for a demotion
(`new > old`), set `next_due = max(old_next_due, a + new)`. A missing `a` is
treated as `n` (only malformed or reconstructed state can reach that case
because new attachments are immediately ready). Apply the period-change
formula before current-ordinal deadline accrual. These formulas, strict
integer bounds, and canonical attachment order are checkpoint invariants.

Thus an interval-2 sensor and interval-20 LOD observer execute at a bounded
cadence instead of depending on two modulo residues that may never coincide.
For a continuously operational side-local group of two equivalent
period-two sensors, both are first-ready, then exactly one is native-ready on
each interval in alternating residue order. Each attachment retains one scan
per two intervals while the group supplies one scheduled opportunity per
interval rather than a synchronized blind interval.
A shorter-period transition never delays the prior deadline. A
witness-driven promotion to ACTIVE (period one) makes the LOD readiness bit
accrue by the next production interval unless it is already pending; a general
DISTANT-to-NEARBY transition follows the exact formula above and is not
promised next-interval admission. Demotion changes future deadlines but never
erases readiness already accrued. Operational-state changes and LOD
transitions never alter phase. An offline sensor continues advancing deadlines
and retains at most one pending native and one pending LOD opportunity, so
returning online permits one immediate scan but never a backlog burst. A real
admitted sweep consumes readiness even when target selection finds zero
targets. Removed active attachment states are pruned only as part of a
successful complete-roster transaction, while their immutable assignment
records remain available for exact reappearance and reinforcement continuation.

One outer `TacticalObservationPlan` stages the BattleManager LOD
tier/hysteresis/promotion maps, target-concealment decay, targeting tier
snapshot, complete-roster cadence plan, and every FOW side plan. Current
witnesses may add promotions to the staged next-interval LOD state only after
all side scans succeed. Prevalidated commits are non-throwing swaps across the
owners. A failed side therefore commits no classification, concealment,
cadence, scan-count, contact, witness, fusion, receipt, or transcript mutation.
Checkpoint capture rejects an active or poisoned transaction. The schedule
never derives phase from a display name, position, target, probability, or RNG
value, and a skipped opportunity remains an absent observation rather than a
fabricated aggregate detection roll.

The checkpoint registry is canonical and carries its exact SHA-256. Restore
validates unique attachment identities and group ordinals; contiguous ordinals
from zero within every group; residue equal to assignment ordinal modulo native
period; active-state/registry agreement; native deadline residue and
chronology; group/period agreement with typed runtime loadouts; canonical
ordering; and the registry digest before any publication. Versionless
nonzero-history restore with scan scheduling remains rejected, and no migration
may invent phase history. The formal artifacts retain complete typed boundary
checkpoints as identity-bearing cadence snapshots rather than relying only on
aggregate deferral totals. Focused production evidence must additionally show
the exact first-ready/alternating sequence, per-attachment long-run rate,
period-one control behavior, absence of fabricated observations, and
fresh-runtime checkpoint continuation.

Uniform staggering is supported as an estimation architecture by Niu,
Varshney, Mehrotra, and Mohan, "Temporally Staggered Sensors in Multi-Sensor
Target Tracking Systems," *IEEE Transactions on Aerospace and Electronic
Systems* 41(3), 2005 ([DOI](https://doi.org/10.1109/TAES.2005.1541430)). Their
linear equal-noise analysis does not prove this simulator's nonlinear,
missed-detection, multi-target outcomes or any v4 acceptance budget; the fresh
production study remains the authority for those claims.

### Correlation-safe same-epoch sensor fusion

Every detector and indexed detection/identification decision still executes in
its canonical order. Successful sensor results are then staged as typed fusion
candidates carrying their complete `FOWDecisionIdentity`, target kind and ID,
observer ENU position, `DetectionResult`, `ContactInfo`, and logical observation
time. Candidates may be grouped only by exact engine tick, reporting side,
target kind, target ID, and observation time. Sides, target generations,
target kinds, or times never coalesce.

The detector emits both three-dimensional slant `range_m` and horizontal ENU
`horizontal_range_m` with each result. The sensor adapter reconstructs the
measurement's horizontal position from the observer ENU position, horizontal
range, and bearing; it never copies the live target position into a fusion
candidate or observer-support record. The slant range remains the input to the
existing scalar effective uncertainty for candidate `i`:

```text
sigma_i = max(0.05 * range_i, 1 metre)
          / max(min(detection_probability_i, 1), 0.01)
R_i = sigma_i^2 * I_2
```

but production has no cross-covariance model that makes repeated simultaneous
updates independent. `IntelFusionEngine` shall therefore own one
correlation-safe batch boundary. It validates the complete batch before
mutation and chooses the candidate with minimum finite positive `sigma_i^2`,
breaking exact ties by the canonical encoded decision identity. It performs
one prediction, gate, Joseph update or bounded replacement, and one track-hit
increment for the group. It never retries a gated representative with a
looser candidate. All successful detections still publish their own indexed
lanes, witnesses, reporting-sensor provenance, identification evidence, and
cadence-recovery work; only duplicate positional estimator updates are
collapsed.

For the present truth-identical means and isotropic covariance family, this is
the exact trace- and determinant-minimizing covariance-intersection result. In
inverse form, covariance intersection uses
`R_ci^-1 = sum(weight_i * R_i^-1)` with non-negative weights summing to one.
Both objectives are minimized by the simplex endpoint with the smallest
`sigma_i^2`; no numerical optimizer, invented correlation coefficient, or new
measurement RNG is required. Julier and Uhlmann introduced covariance
intersection for estimates with unknown correlation
([DOI](https://doi.org/10.1109/ACC.1997.609105)); Sandia's independent analysis
documents the same inverse-covariance formulation and the need to consider
optimizer boundaries
([SAND2024-09992](https://www.osti.gov/servlets/purl/2429882)). Bellantoni and
Dodge separately establish that simultaneous correlated measurements require
an explicit correlated-measurement treatment
([NASA record](https://ntrs.nasa.gov/citations/19670051473)). These sources
justify correlation safety, not the simulator's unsourced five-percent proxy;
sensor-specific error, bias, and cross-covariance modeling remains REM-044.

The receipt records position-measurement candidates, groups, and correlated
candidates elided. Per side cycle, candidates equal detection successes,
`candidates = groups + elided`, groups equal creations plus updates plus
replacements, and positive-time predictions cannot exceed groups. A
one-candidate batch must be byte-equivalent to the prior one-report path;
permutations, sequential/threaded dispatch, unequal/equal variance selection,
later timestamps, target/side separation, gated replacement, malformed or
duplicate identity, checkpoint continuation, and candidate-only covariance
must all receive focused negative-control coverage.

### Native-cadence observer track support

`ObserverDetectionWitness` remains success-only and current-update-only. It is
never carried forward or reinterpreted as history. `FogOfWarManager` instead
owns a separate immutable, typed observer-track-support map keyed by the full
attachment identity plus hostile target ID:

```text
(reporting_side, observer_unit_id, source_equipment_index,
 sensor_id, modeled_role, target_id)
```

Each value also binds the exact fusion-track generation, sensor type, successful
observation ordinal and time, native period and phase, exclusive native due
ordinal, and a finite local position estimate/covariance derived from the real
successful measurement. It stores no live `Unit`, current ground-truth target
position, or fabricated range. The only supported policy is the closed set of
seven `LOCAL_FIRE_CONTROL` radar roles: airborne fire-control, airborne-ground
fire-control, airborne multi-domain fire-control, generic fire-control, ground
air-defense fire-control, naval fire-control, and naval air-defense
fire-control radar. Visual, NVG, thermal/IR/optical, search radar, ESM, sonar,
and every search-only attachment remain current-observation-only.

At cadence ordinal `n`, support is usable only when the exact attachment is
operational, native-deferred, still bound to the same live target/contact and
fusion-track generation, and `n` is strictly before its stored native due
ordinal. Its local estimate and covariance are projected deterministically to
the current logical time without RNG or owner mutation. It must remain finite,
symmetric, positive semidefinite, below the existing estimator maximum-
covariance limit, and conservatively inside the attachment's current
condition-dependent reach. A native-ready interval expires old support before
adjudication; only a real successful admitted detection creates a fresh value
whose exclusive expiry is the cadence plan's next native due ordinal. An
admitted stochastic miss, any pre-RNG rejection, offline/removal, target or
domain removal, unsupported role/type, cadence/topology mismatch, track loss,
or track replacement removes it. LOD-only deferral never extends authored
native support. Period-one native cadence therefore cannot coast.

Targeting exposes this authority as the distinct typed source
`FOW_OBSERVER_TRACK_SUPPORT`, never `FOW_OBSERVER_WITNESS`. Current witnesses
remain preferred. A support-backed decision binds the exact support identity,
observation/expiry chronology, fusion-track generation, projected estimate,
and uncertainty; uses the exact same live attachment for contact, sensing, and
compatible local fire control; and cannot authorize direct visual or an
unrelated director. The current target position/range may still be used by the
separate authoritative combat-physics safety gates, but it may not be copied
into or used to fabricate support evidence. Unsupported consumers fail with an
explicit disposition.

Support participates atomically in the complete FOW side transaction,
publication plan, targeting observation snapshot, disabled-FOW clear, content
and raw-structure fingerprints, and strict format-118 checkpoint state. Restore
validates canonical order and uniqueness, exact active attachment/hostile
target/cadence bindings, track generation, chronology, finite covariance, and
replacement semantics before any owner mutation. Versionless migration starts
empty and never infers support from side-wide contacts, reporting sensor IDs,
or witnesses. Focused proof must cover success/defer/use/due-failure, pre-RNG
failure, LOD-only due deferral, offline/removal, loss/redetection,
reinforcement, duplicate sensor IDs at distinct source indexes, exact RNG
draw parity, current-only optical behavior, and fresh/in-place checkpoint
continuation with corruption rejection and valid retry.

Stored targeting exposure has its own strict root discriminator,
`targeting_exposure_schema_version=118`, emitted by production capture even
when targeting and outcome lists are empty. A versioned frame requires the
complete root envelope: exact privileged scope, targeting/outcome lists,
the strict runtime-owned `fog_of_war_enabled` boolean, boolean SIDE_FOW
availability, side-view and root-only association mappings, tick, and the
authoritative unit roster. The runtime mode must exactly equal materialized
SIDE_FOW availability and every nonempty decision interval. Mode `true`
requires the complete root-side set; mode `false` requires empty side and
association envelopes. Empty decisions never make any of those fields
optional. Unknown, boolean schema versions, nonboolean modes,
missing-from-an-otherwise-versioned fields, mode/availability disagreement,
or partially deleted format state rejects before either API or replay scope
is returned.

Bounded unversioned migration is monotonic. A paired Phase 115--117 frame is
recognized only by its complete explicit privileged scope and complete
availability/view/association envelope; an empty paired frame remains readable
only when that complete envelope validates. A privileged pre-115 frame may
omit that entire envelope only when it contains at least one uniform exact
legacy decision missing only the Phase 118 nullable support key. An
unversioned empty targeting list with no paired envelope is intrinsically
indistinguishable from a stripped current frame and is explicitly unsupported
rather than downgraded. A deleted schema marker that leaves the current-only
FOW mode, or a current decision topology without the marker and mode, rejects.
The one shared decoder owns these rules for API and replay. This is semantic
consistency validation of stored data, not cryptographic authentication of a
wholly rewritten frame.

### Elapsed-time track estimation

Every ordinary sensor measurement for an existing fusion track shall first
predict a staged copy from its exact `last_update_time` to the measurement's
logical time, then apply estimator gating and update/replacement atomically.
An accepted update commits the staged state at the measurement time. A gated
FOW measurement commits only its complete replacement transaction; a rejected
non-replacement update leaves the original track untouched, so a later report
predicts once over the full interval from the last accepted state. Negative or
non-finite elapsed time or a partial rejected update fails closed. For multiple
accepted measurements at one logical time, only the first positive elapsed
interval predicts; later same-time measurements use `dt == 0` and update the
already staged epoch without another prediction. A second positive prediction
from an already advanced epoch rejects. This uses the existing production
constant-velocity estimator and process covariance; it does not invent
observations or recalibrate sensor noise. Fresh and restored cadence gaps must
produce exact prediction, covariance growth, gating, and replacement state.

This is an explicit Phase 118 dependency advance from REM-044 / Phase 131: a
generic elapsed-time prediction is required now so scan/LOD cadence does not
feed stale covariance into a measurement. REM-044 remains open for sourced
sensor-specific covariance, broader estimator-model justification, every
intelligence modality, and its own complete Phase 131 production evidence.
Phase 118 makes no sensor-covariance calibration claim.

### Identity-addressed Philox decisions

The baseline threaded path draws side seeds and uses temporary generators
while the sequential path consumes the shared root stream. A skipped scan or
LOD opportunity consequently changes every later detection variate, so a pair
measures stream phase drift in addition to the declared approximation.

Phase 118 shall use one topology for sequential, threaded, scheduled, and
unscheduled FOW execution:

1. `RNGManager` derives and persists one domain-separated 128-bit Philox key
   from the exact non-negative master seed. The derivation algorithm,
   namespace, and schema are checkpointed and rederived on restore. Indexed
   decisions do not advance the conventional `DETECTION` PCG stream.
2. At each tactical interval, enumerate the complete reporting-side set in
   ascending side-ID order and request one owner-issued `FOW_DETECTION`
   allocation bound to `(engine_tick, ordered_reporting_sides)`. The set is
   independent of flags, due attachments, targets, and dispatch mode.
3. Each potential stochastic opportunity has the typed identity
   `(schema, namespace, engine_tick, reporting_side, observer_unit_id,
   source_equipment_index, sensor_id, modeled_role, target_kind, target_id,
   opportunity_ordinal)`. `target_kind` is `UNIT` or `DECOY`; the ordinal is a
   strict unsigned integer and is zero for the current one-opportunity path.
   Probabilities, positions, and flag values never enter the identity.
4. Canonically encode all non-tick fields with domain tags, fixed-width
   unsigned integers, and length-prefixed exact UTF-8 strings. Let `D` be the
   first 192 bits of SHA-256 over those bytes and set the 256-bit Philox
   counter to `engine_tick + (D << 64)`. The interval registry maps `D` to the
   complete bytes and rejects duplicate issuance or a distinct-preimage
   collision before adjudication.
5. One Philox 4x64 block owns the opportunity. Lane 0 supplies detection,
   lane 1 supplies conditional identification, and lanes 2--3 are reserved.
   Convert an unsigned raw lane `x` to a binary64 uniform using
   `(x >> 11) * 2**-53`; do not rely on NumPy distribution transforms. The
   production detection boundary requests the block only after all pre-RNG
   checks, consumes lane 0 once, and makes lane 1 available only after a
   successful detection reaches identification.
   Each side handle reuses one side-local Philox bit generator by setting the
   requested counter and reading one raw block; focused known-answer tests must
   prove byte-exact parity with a fresh `Philox(counter=..., key=...)` object.
   The reusable reset writes the complete counter/key state and canonical
   empty cached-word/buffer state, not the counter alone. The test drives one
   reused object through multiple deliberately non-monotonic counters, compares
   every four-lane block and post-draw bit-generator state to a fresh object,
   and then revisits an earlier counter. Constructing a generator per
   opportunity is forbidden on the hot path.
6. Side handles are manager-, module-, tick-, and side-bound. Wrong ownership,
   missing/extra/duplicate/unsorted sides, lane misuse, handle reuse, an
   incomplete allocation, or a poisoned transaction rejects. Threads stage
   side deltas independently; the coordinator joins, validates, and commits in
   canonical side/counter order. A checkpointed rolling transcript digest over
   canonical `(counter, consumed_lane_mask)` entries exposes exact indexed-draw
   continuation without persisting a mutable counter cursor.

The production path accepts typed handles, never a naked generator.
Compatibility APIs for isolated subsystem callers may retain an explicit
`numpy.random.Generator`, but supplying both sources rejects and such calls are
not Phase 118 evidence. `BattleManager` may neither construct a generator nor
reach through `FogOfWarManager._rng`. Complete RNG continuation authority is
the conventional module-stream states plus the indexed algorithm/schema,
derived key, and transcript state. Phase 118 shall update the `CODEX.md` RNG
invariant accordingly.

The indexed contract deliberately covers detection and identification only.
Approximation-caused downstream targeting can still change whether existing
COMBAT or MORALE stream draws occur; those root-state deltas are retained and
budgeted as causal model effects, not described as event-synchronized common
random numbers. Exact optimization pairs must retain every module stream
exactly. No part of this design authorizes weapon, sensor, probability,
morale, doctrine, or scenario recalibration.

Counter-based generators support parallel random access by application/event
identity; see Salmon et al., "Parallel Random Numbers: As Easy as 1, 2, 3"
([SC11 paper](https://www.thesalmons.org/john/random123/papers/random123sc11.pdf))
and NumPy's direct 4x64-counter/128-bit-key `Philox` interface
([NumPy documentation](https://numpy.org/doc/stable/reference/random/bit_generators/philox.html)).
The repository claim is deliberately narrower than universal independence:
common FOW decisions receive stable raw bits regardless of dispatch or omitted
opportunities.

### Exact indexed-byte and transcript contract

All integers below are unsigned big-endian and reject booleans, overflow, or
negative values. Master seed must be a strict non-negative Python integer;
engine tick and equipment index must fit `u64`, opportunity ordinal must fit
`u32`, and every encoded text value must fit the `u32` byte-length bound.
`text(value)` is `u32(byte_length) || value.encode("utf-8")`; values must
already satisfy their typed non-empty/trimmed contract, and no Unicode
normalization is applied.

The Philox key preimage is exactly:

```text
b"stochastic-warfare/indexed-philox-key/v1\x00"
|| u32(master_seed_byte_length)
|| minimal_big_endian_master_seed_bytes
```

Zero is encoded as one zero byte. The first 16 SHA-256 bytes, interpreted as
one big-endian integer, are the 128-bit key. The persisted RNG state contains
algorithm `numpy-philox-4x64`, schema 1, the literal namespace, exact key hex,
and SHA-256 of the complete key preimage. Restore rederives and compares every
field before mutation.

The non-tick decision preimage `P` is exactly:

```text
b"stochastic-warfare/fow-decision/v1\x00"
|| u16(1)
|| text(reporting_side)
|| text(observer_unit_id)
|| u64(source_equipment_index)
|| text(sensor_id)
|| text(modeled_role)
|| u8(target_kind)          # UNIT=1, DECOY=2
|| text(target_id)
|| u32(opportunity_ordinal)
```

`D = SHA256(P)[0:24]`; the exact 32 counter bytes are
`D || u64(engine_tick)`. The registry compares complete `P` bytes, not only
their digest. Counter words supplied through NumPy state use the documented
least-significant-word-first numeric representation, and known-answer tests
must prove equality with a fresh constructor from the big-endian counter
integer.

The checkpointed transcript starts at
`SHA256(b"stochastic-warfare/fow-transcript/v1\x00")`. A successful interval
record is:

```text
b"stochastic-warfare/fow-transcript-record/v1\x00"
|| u16(1)
|| u64(engine_tick)
|| u32(reporting_side_count)
|| text(each reporting side in ascending UTF-8 byte order)
|| u64(entry_count)
|| for each entry sorted by (side UTF-8 bytes, counter bytes):
     text(side) || counter_32_bytes || u8(consumed_lane_mask)
```

The only valid masks are 1 (detection) and 3 (detection plus identification).
Fold with
`SHA256(b"stochastic-warfare/fow-transcript-fold/v1\x00" || previous_digest ||
u64(record_length) || record)`. Persist the digest, committed interval count,
committed entry count, and a monotonic `complete_from_tick_zero` evidence bit.
The evidence runner also retains each bounded raw interval record, so it can
prove equality for common identities rather than trusting only a digest.

## Production execution receipts

### FOW cycle receipt

`FogOfWarManager` shall expose a typed update boundary that returns the normal
`SideWorldView` together with one immutable `FogOfWarCycleReceipt`. The legacy
`update(...) -> SideWorldView` API may remain as a compatibility wrapper, but
the production battle coordinator shall consume the receipt-bearing boundary.

Each successful side cycle records strict non-negative integers for:

- reporting side, engine tick, observer count, target count, and attached
  sensor count;
- target opportunities before selection and candidates admitted;
- culling-tree construction, culling queries, and targets pruned;
- SoA-vector selection, vector queries, and targets pruned;
- brute-force target-selection cycles;
- admitted-attachment sensor-target opportunities passed to the detection API,
  attachment-level scheduled skips, and detection checks executed; and
- detections and published observer witnesses.

The receipt names exactly one target-selection route for each observer:
`strtree`, `soa_vector`, or `brute_force`. Counts must reconcile; for example,
admitted plus pruned targets equals the preselection opportunity count, and
each admitted sensor-target opportunity equals one detection API call.
Scheduled skips are attachment cycles and reconcile only with the cadence
attachment partition; they are never added to target-level counts. A malformed
or internally inconsistent receipt raises before it can be aggregated.

### Runtime execution receipt

`BattleManager` owns one typed monotonic accumulator and exposes an immutable
`PerformanceExecutionReceipt` through a public `RuntimeSession` method. It
aggregates committed FOW cycle receipts and adds:

- tactical intervals prepared;
- per-mode sequential side updates, parallel intervals, tasks submitted, and
  tasks joined;
- SoA pre-movement and post-movement snapshot builds and enemy-position
  projections outside the FOW selector;
- LOD ACTIVE, NEARBY, and DISTANT classifications;
- cadence attachment readiness/admission/deferral, estimator prediction and
  update/replacement, indexed RNG blocks/lanes, and transcript entries;
- full-rate LOD engagement-attacker, morale-unit, and movement processing plus
  explicit zero forbidden-deferral counts; and
- exact effective values of all five governed flags.

The persisted receipt has this exact closed integer topology beneath its
version/completeness/flag fields:

```text
/schema_version
/complete_from_tick_zero
/effective_flags/<each of the five canonical flag names>
/tactical_interval_microseconds
/tactical_intervals
/tactical_duration_microseconds
/fow/side_cycles
/fow/observers
/fow/targets
/fow/sensors
/fow/target_opportunities
/fow/selection/strtree_builds
/fow/selection/strtree_queries
/fow/selection/strtree_admitted_targets
/fow/selection/strtree_pruned_targets
/fow/selection/soa_vector_builds
/fow/selection/soa_vector_queries
/fow/selection/soa_vector_admitted_targets
/fow/selection/soa_vector_pruned_targets
/fow/selection/brute_force_cycles
/fow/selection/brute_force_admitted_targets
/fow/scan/operational_sensor_target_opportunities
/fow/scan/scheduled_attachment_skips
/fow/cadence/attachment_cycles
/fow/cadence/operational_attachment_cycles
/fow/cadence/native_ready
/fow/cadence/lod_ready
/fow/cadence/admitted
/fow/cadence/deferred_native
/fow/cadence/deferred_lod
/fow/cadence/deferred_both
/fow/cadence/offline
/fow/cadence/native_recoveries_by_period/<ordered-index>/deferral_period
/fow/cadence/native_recoveries_by_period/<ordered-index>/recovery_admissions
/fow/cadence/native_recoveries_by_period/<ordered-index>/recovery_admissions_with_indexed_work
/fow/cadence/native_recoveries_by_period/<ordered-index>/indexed_detection_blocks
/fow/cadence/lod_recoveries_by_period/<ordered-index>/deferral_period
/fow/cadence/lod_recoveries_by_period/<ordered-index>/recovery_admissions
/fow/cadence/lod_recoveries_by_period/<ordered-index>/recovery_admissions_with_indexed_work
/fow/cadence/lod_recoveries_by_period/<ordered-index>/indexed_detection_blocks
/fow/detection/api_calls
/fow/detection/pre_rng_unsupported_domain_rejections
/fow/detection/pre_rng_above_max_range_rejections
/fow/detection/pre_rng_below_min_range_rejections
/fow/detection/pre_rng_outside_fov_rejections
/fow/detection/pre_rng_los_rejections
/fow/detection/pre_rng_no_emission_rejections
/fow/detection/stochastic_draws
/fow/detection/successes
/fow/detection/published_witnesses
/fow/fusion/predictions
/fow/fusion/predicted_microseconds
/fow/fusion/creations
/fow/fusion/updates
/fow/fusion/replacements
/fow/fusion/position_measurement_candidates
/fow/fusion/position_measurement_groups
/fow/fusion/correlated_candidates_elided
/fow/indexed_rng/blocks
/fow/indexed_rng/detection_lanes
/fow/indexed_rng/identification_lanes
/fow/indexed_rng/transcript_entries
/dispatch/sequential_intervals
/dispatch/sequential_side_updates
/dispatch/parallel_intervals
/dispatch/parallel_tasks_submitted
/dispatch/parallel_tasks_joined
/soa/pre_movement_builds
/soa/pre_movement_enemy_position_projections
/soa/post_movement_builds
/soa/post_movement_enemy_position_projections
/lod/active_classifications
/lod/nearby_classifications
/lod/distant_classifications
/lod/detection/active_attachments_admitted
/lod/detection/active_attachments_deferred
/lod/detection/nearby_attachments_admitted
/lod/detection/nearby_attachments_deferred
/lod/detection/distant_attachments_admitted
/lod/detection/distant_attachments_deferred
/lod/engagement/attacker_cycles_processed
/lod/engagement/deferred
/lod/morale/unit_cycles_processed
/lod/morale/deferred
/lod/movement/active_processed
/lod/movement/nearby_processed
/lod/movement/distant_processed
/lod/movement/deferred
```

The v7 development contract uses execution-receipt schema version 2. Version 1
has neither durable cadence-recovery buckets nor correlation-safe fusion-group
counts and therefore rejects under the current strict loader; those values are
never reconstructed from a terminal cadence roster, a transcript, or a v6
artifact. The retained v6 publication remains immutable terminal evidence
under its original code revision and manifest digest.

Every side-cycle receipt satisfies these exact equations:

```text
attachment_cycles
  = operational_attachment_cycles + offline
operational_attachment_cycles
  = admitted + deferred_native + deferred_lod + deferred_both
scheduled_attachment_skips
  = deferred_native + deferred_lod + deferred_both
operational_sensor_target_opportunities = api_calls
api_calls
  = every named pre-RNG rejection + stochastic_draws
stochastic_draws = indexed_rng.blocks
                 = indexed_rng.detection_lanes
                 = indexed_rng.transcript_entries
0 <= indexed_rng.identification_lanes <= detection.successes
0 <= detection.published_witnesses <= detection.successes
detection.successes = fusion.position_measurement_candidates
fusion.position_measurement_candidates
  = fusion.position_measurement_groups
  + fusion.correlated_candidates_elided
fusion.position_measurement_groups
  = fusion.creations + fusion.updates + fusion.replacements
fusion.predictions <= fusion.position_measurement_groups
```

`native_ready` and `lod_ready` are orthogonal pre-consumption observations over
all attachment cycles and each is bounded by `attachment_cycles`; they are not
additive partitions. An offline attachment never contributes target
opportunities, API calls, or a random block. An admitted zero-target sweep
consumes cadence readiness but contributes zero target opportunities and API
calls. Each selector cycle names exactly one route even for zero targets, and
admitted plus pruned target counts equal that route's preselection count. The
six LOD tier admission/deferral counters partition operational attachment
cycles by classified tier. LOD engagement, morale, and movement `deferred`
must always be zero. Prediction count includes only strictly positive elapsed
predictions, and `predicted_microseconds` is their exact finite integer sum.
No-sensor and no-target cycles therefore reconcile without invented work.
Each native/LOD recovery list is strictly increasing by unique positive
`deferral_period`; recovery admissions with indexed work are bounded by all
recovery admissions, indexed blocks are bounded by the complete indexed-RNG
receipt, and only the exact recovered attachment can contribute its work.

The canonical `DetectionResult` gains a typed decision stage so the FOW
receipt can distinguish a call to the detection API, every existing pre-RNG
return, and an actual stochastic draw. Because domain policy currently
precedes range policy, a far target omitted by a selector would otherwise have
returned either `unsupported_domain` or `above_max_range`. Only those two
stage counters are normalizable for culling and SoA, and their combined delta
must exactly equal the detection-API-call delta. All other early-stage counts
remain exact. The complete stage counts plus stochastic draws must reconcile
to API calls. This instrumentation is observational; it may count the returned
production decision but may not repeat a check or consume a probe draw. Each
measured tactical interval
also supplies its exact finite positive `dt`; the accumulator stores integer
microseconds, binds the receipt to the effective runtime tactical cadence, and
requires cumulative duration to equal interval count times that cadence. The
archived Phase 118 study admitted only the authored 5,000 ms cadence.

Receipts are observational state. They may not select targets, consume RNG,
alter iteration, or change a simulation outcome. One nested FOW transaction
stages the complete reporting-side union and commits cadence, scan counts,
fusion, contacts, witnesses, indexed transcript, and side receipts only after
every side plan validates. Separately, a `BattleManager` receipt transaction
begins before FOW, accumulates all active-battle consumer counts, and commits
from `SimulationEngine.step()` only after the multi-battle loop succeeds. A
later battle failure poisons the receipt transaction and makes checkpoint and
continued evidence capture reject; Phase 118 does not claim whole-engine
rollback for pre-existing combat state mutations. The accumulator is included
in `BattleManager` checkpoint state, validated with exact key topology and
non-negative integer constraints, and restored atomically.

Adding the accumulator changes strict checkpoint topology. Phase 118 bumps the
engine checkpoint format from 116 to 118. An explicitly versioned format-116
checkpoint rejects rather than fabricating Phase 118 evidence. Format 118
persists three separate monotonic completeness bits: the execution receipt's,
the cadence scheduler's, and the indexed transcript's
`complete_from_tick_zero`. Their values must agree at capture and restore.
A runtime freshly constructed at tick 0 initializes all three to `true`.
For a runtime with the governed production FOW path enabled, format 118 also
requires
`cadence.committed_ordinal == receipt.tactical_intervals ==
transcript.committed_interval_count` and
`transcript.committed_entry_count ==
receipt.fow.indexed_rng.transcript_entries ==
receipt.fow.indexed_rng.blocks ==
receipt.fow.indexed_rng.detection_lanes`. When production FOW is disabled,
cadence and transcript counts must remain zero and the receipt may not claim
FOW side cycles. Capture and restore cross-validate these independently owned
values and reject before mutation on any mismatch; exact key topology alone is
insufficient.

A versionless legacy checkpoint cannot reconstruct receipt history, cadence
phase, or the indexed transcript prefix and therefore initializes all three
bits to `false`; no later execution may promote any of them. If that legacy
state has nonzero public clock history and either `enable_scan_scheduling` or
`enable_lod` is effective, restore rejects because the attachment cadence
phase cannot be reconstructed safely. When both cadence flags are false,
ordinary compatibility continuation may initialize the empty period-one
scheduler and a rederived indexed key with an empty transcript, but all three
completeness bits remain `false`; such incomplete history is not acceptance
evidence. Every newly captured format-118 checkpoint from a runtime executed
from tick 0 contains all three `true` bits and their complete state; every
format-118 descendant of a permitted versionless restore preserves all three
as `false` permanently.

Format 116 also emits non-standard JSON `-Infinity` for a never-fired
`WeaponInstance.last_fire_time_s` (34 instances in this source at the Phase 118
baseline). Format 118 encodes that state as JSON `null`; finite logical
times remain finite numbers, and live restore maps `null` back to the internal
never-fired sentinel. A versionless migration may accept negative infinity
only at the exact legacy weapon timestamp paths and converts it to the typed
sentinel before staging.

`SituationAssessment.force_ratio` separately models an unbounded positive
ratio when enemy power is zero. Format 118 encodes only that exact typed state
as JSON `null`, requires its persisted rating to be `VERY_FAVORABLE`, and maps
it back to positive infinity only after complete assessment staging succeeds.
A finite ratio remains a finite non-negative number. Negative infinity, NaN,
an unbounded marker with a different rating, and every non-finite constant at
any other format-118 or artifact path reject.

Because enabled and disabled paths intentionally produce different branch
measurements, the closed semantic projection described below normalizes only
the target case's enumerated receipt fields. It never removes the accumulator
as a whole. Same-variant repeats and checkpoint continuation still compare
complete checkpoint bytes, including the accumulator.

## Configuration and failure behavior

The five governed flags remain strict booleans in `CalibrationSchema`;
coercion, unknown fields, and inconsistent authored/typed/flattened/receipt
values reject. Detection culling defaults enabled; scan scheduling, LOD, SoA,
and parallel detection retain their declared defaults. A current production
value of `true` for scan scheduling or LOD rejects at scenario, API,
analysis-variant, runtime preparation, manager, and current-checkpoint
boundaries before work or mutation. Non-default LOD intervals also reject
while LOD is unsupported.

The LOD cadence fields remain strict positive integers:

- `lod_nearby_interval >= 1`;
- `lod_distant_interval >= 1`;
- `lod_hysteresis_ticks >= 1`; and
- `lod_distant_interval >= lod_nearby_interval`.

Defaults remain 5, 20, and 3. The schema keeps unsupported fields so old or
hostile inputs receive one explicit error rather than being ignored.

The shared format-118 checkpoint decoder is JSON-only. It rejects invalid
UTF-8, duplicate keys, non-finite constants, malformed or extra NumPy marker
fields, ragged arrays, unsupported/object dtypes, non-finite decoded arrays,
and cross-type coercion before restore mutation. Boolean arrays require JSON
booleans; integer arrays require in-range JSON integers excluding booleans;
floating arrays require finite in-range numbers excluding booleans. Current
capture uses `allow_nan=False`.

Format 118 encodes never-fired weapon timestamps as `null`, and only the typed
positive-unbounded assessment ratio may use its separate `null`
representation. Explicit format 116 rejects. The bounded versionless migration
may recognize only its documented legacy topology; it never fabricates
receipt, cadence, indexed-RNG, or observer-support history.

## Archived validation summary

The v7 study used two shipped production sources:

- `calibration_air_ground` exercised all five flags;
- `suwalki_gap` supplied an additional material NEARBY LOD case.

Each candidate changed exactly one governed flag against an all-disabled
control. Sixteen fresh held-out seeds produced 96 ordered flag/source/seed
pairs and 396 attempts, including same-variant repeats and first-seed
fresh-runtime checkpoint continuations. Exact optimizations required
normalized state, event, RNG, receipt, and continuation equality with material
branch work. Approximation cases used frozen state, contact, targeting, event,
timing, and covariance budgets. Integrity failures were `ERROR`; completed
budget or semantic misses were `FAIL`; no outcome was truncated.

V6 remained `ERROR` because its LOD recovery proof was lossy at terminal
state. V7 used the approved complete-case recovery totals and completed
eligibly. Its scan and Suwalki LOD misses are therefore real negative evidence.
The archive branch preserves the exact plan, burned seed sets, observations,
projection rules, budgets, shard schema, publication rules, and handoff. Main
does not carry or execute that retired one-off apparatus.

## Production trace and completion matrix

| Stage | Phase 118 result |
|---|---|
| Declared | Strict calibration plus one immutable five-entry registry declare classification, support disposition, required meaning, and retained v7 verdict. |
| Loaded | `SimulationRuntimeFactory` loads the three supported exact flags and the false/default form of the two retired controls; unsupported positive or non-default inputs reject. |
| Wired | `SimulationEngine -> BattleManager -> FogOfWarManager` consumes the supported flags and reconciles their production-owned receipts. |
| Enabled | Culling, SoA, and parallel detection have material off/on production evidence. Positive enablement is N/A for scan scheduling and LOD because current production intentionally rejects both. |
| Exercised | Direct production tests exercise all supported branches and the explicit rejection of both unsupported controls. The archived v7 study exercised all five controls. |
| Outcome-affecting | Supported flags alter controlled execution work while preserving exact normalized semantics. The retired approximations produced real deltas outside their frozen budgets. |
| Persisted/exposed | Format-118 checkpoints preserve coherent supported state and receipts. The API exposes the exact registry and immutable evidence identities; raw evidence remains off main on `evidence/full`. |

## Direct behavioral verification retained on main

The durable regression surface uses production code rather than the retired
study harness:

- API coverage proves the support registry and unsupported-request errors.
- Factory/runtime tests prove exact culling, SoA, and parallel work,
  deterministic indexed decisions, and checkpoint continuation.
- Cadence/LOD tests prove first-ready scheduling, non-starvation, full-rate
  non-sensing owners, and explicit unsupported activation.
- Receipt tests prove atomic reconciliation, checkpoint round trips, tamper
  rejection, and cross-owner completeness.
- Fusion and observer-support tests prove correlation-safe grouping, elapsed
  prediction, support lifecycle, stored-frame decoding, and continuation.
- Configuration tests prove scenario, API, analysis, runtime, manager, and
  checkpoint rejection of scan scheduling, LOD, and non-default LOD tuning.

Structural imports, source inspection, mocked calls, constructor checks, and
no-crash runs do not satisfy these claims.

## Performance qualification and follow-ups

The semantic study predeclared no timing threshold. External contention below
its completion deadlines did not change its semantic verdict, and neither v6
nor v7 supports a speed claim.

The separate matched production profile found a real gross regression. After
one discarded warm-up per revision, the phase-start `benchmark_battalion`
ten-tick median was 47.035449 seconds (46.974269--47.341247) and the Phase 118
median was 59.220597 seconds (58.758202--59.259692), a 1.259063 ratio
(+25.906%). Both revisions produced the same ten-tick, 50-second, blue
`max_ticks` outcome. A matched profile placed 17.938846 seconds, or 81.60% of
its 21.983317-second cumulative delta, beneath transactional FOW update.
Overlapping descendants are not additive savings estimates.

REM-054 / Phase 141 owns any future scan-scheduling or LOD re-enablement with
new predeclared evidence. REM-055 / Phase 142 owns the measured transactional
FOW cost and must preserve atomicity, mutation detection, indexed stochastic
identity, fusion, receipts, checkpoint continuation, and exact outcomes.

## Non-goals and accepted limitations

Phase 118 does not:

- prove universal equivalence over every scenario, seed, platform, CPU count,
  or operating system;
- promote measurement-only benchmark scenarios to semantic validation;
- claim that scan scheduling or LOD is calibrated, physically lossless, or
  currently supported;
- validate every interaction among the five flags;
- tune weapons, sensors, morale, doctrine, scenario geometry, or victory
  conditions to force a pass;
- make timing part of the frozen semantic verdict;
- resolve REM-054 or REM-055; or
- expose raw artifact payloads through API or frontend duplication.

Observer-track support remains structurally implemented and checkpointed, but
current supported production cannot emit non-null support because both cadence
controls that can reach it are rejected. REM-054 owns restoration of a
supported production-reachable path. The v7 scan schedule used catalog
`scan_interval_ticks`; Phase 118 does not claim a sourced physical
relationship to `scan_time_s`.
