# Fog-of-War Contact Continuation

**Status:** Accepted and complete in Phase 116

**Owner:** Phase 116 / REM-029

## Purpose and production boundary

At the Phase 116 baseline, `FogOfWarManager.get_state()` serialized every
ordinary `SideWorldView.contacts` record, but its restore path treated those
payloads as opaque and committed only each view's last-update time. A fresh
runtime therefore retained the fusion tracks while losing the side-owned
target association, classification history, sensor provenance, and contact
chronology that movement, targeting exposure, and later detection updates
consume.

Phase 116 makes the existing fog-of-war owner restore its complete nonempty,
roster-backed ordinary contact picture. The production boundary is:

```text
SimulationRuntimeFactory -> PreparedScenario.build -> RuntimeSession
  -> SimulationEngine checkpoint/restore
  -> SimulationContext staged owner registry
  -> FogOfWarManager stage/commit
```

Standalone `FogOfWarManager.set_state()` must obey the same internal state and
RNG invariants. Constructor calls, source inspection, an empty contact map, an
equal-but-detached `Track`, or a no-crash continuation do not establish this
capability.

This is a persistence repair, not a new detection, identification, covariance,
or targeting model. No configuration flag is appropriate: a current-format
checkpoint either represents the authoritative state exactly or rejects.

## Mandatory Phase 115 benchmark handoff

Before any fog-of-war production code changes, Phase 116 must promote the clean
Phase 115 endpoint at
`271ec49ceb508bdd050e2d5c3072ac91456cca7c` from the version-4
`transition_qualified` handoff to the ordinary version-4 paired 73 Easting
gate. Promotion copies the transition candidate's exact runtime-input identity
and semantic envelope into the ordinary reference fields. It retains the
morale-neutral workload, one warm-up per revision, three `AB/BA/AB` timed
pairs, the 1.20 median-slowdown threshold, the 0.20 relative-range threshold,
and `SimulationEngine.run` timing scope.

The promoted reference label must execute that clean revision through
`SimulationRuntimeFactory`. The bounded historical adapter remains available
only for its exact legacy commit; changing its constant or running modern code
through obsolete wiring is prohibited. The checked-in Phase 115 transition
contract and external `transition_qualified` artifacts remain historical
non-timing evidence and must not be rewritten as a performance result.

The handoff gate is proven on the documentation/benchmark-only candidate tree
before the production repair begins. Because the repository requires one
coherent commit per numbered phase, the reviewed promotion and the completed
Phase 116 repair share the final Phase 116 commit; the clean Phase 115 commit
remains the non-self-referential reference. After that commit, final-tree and
hosted ordinary comparisons must reproduce the same gate.

## Owned state and serialized topology

Format 116 retains one fog-of-war envelope with exactly:

```text
fog_of_war
  world_views: side -> SideWorldView state
  current_detection_witnesses: side -> ordered witness list
  rng_state: DETECTION stream mirror
  intel_fusion: IntelFusionEngine state
```

Each world view has exactly `side`, `contacts`, and `last_update_time`. Each
contact-map value has exactly:

```text
contact_id
track
contact_info
first_detected_time
last_sensor_contact_time
reporting_sensors
```

The nested track retains the existing exact keys `track_id`, `side`,
`contact_info`, `state`, `status`, `hits`, and `misses`. Its estimator state has
two-element position and velocity vectors, a 4-by-4 covariance matrix, and
`last_update_time`.

The duplicate nested track representation is an integrity cross-check, not a
second runtime owner. In a live picture,
`ContactRecord.track is IntelFusionEngine.get_tracks(side)[track_id]`. Restore
must compare the serialized contact track with the already staged fusion track
and bind the contact to that exact staged object. Constructing an equal second
`Track` would split future updates and is invalid.

Current-format restore has replacement semantics. It replaces the complete
`_world_views` map, including explicit empty views, and removes target-runtime
views or contacts absent from the checkpoint.

An explicit empty view is owner state, not ordinary-contact evidence. It is
valid when fog of war is disabled and is created by the public
`get_world_view()` inspection path used by Space ISR controls. Disabled-mode
capture and restore reject nonempty contacts, witnesses, `fow-track-*` IDs, or
FOW counters, but do not reject an otherwise valid empty view.

Format 116 also persists the immutable observer-detection witnesses supporting
the current FOW targeting interval. Each witness retains its reporting side,
observer, target, source-equipment index, sensor ID and modeled role, logical
time, successful detection flag, probability, SNR, exact range, sensor type,
and bearing. The side map and each witness list are canonical. These witnesses
remain bounded same-update evidence: the next update replaces them, and they
are not a general contact-history archive.

## Validation contract

All validation completes before any live clock, RNG, fusion, view, contact, or
track mutation. A valid current-format payload satisfies every applicable
invariant below.

### Side and contact topology

- A world-view map key is a nonempty trimmed declared side and equals its
  serialized `side`.
- A contact map key is a nonempty trimmed identifier and equals
  `contact_id`.
- In a production context, an ordinary contact names one exact staged roster
  unit on a different declared side. Friendly, foreign, missing, or
  side-mismatched unit targets reject.
- Each live ordinary contact uses one canonical side-local `fow-track-NNNN`
  identifier. No two contacts in one side view reference the same track.
- The side-local FOW counter equals the greatest issued FOW ordinal. A counter
  behind or ahead of that ordinal, or a counter without an issued FOW track,
  rejects so the next public track allocation cannot diverge after restore.
- The referenced track exists in the staged fusion map for the reporting side;
  its serialized state is exactly equal to the contact's nested track state,
  and its `side` agrees with the view owner.
- Extra historical LOST fusion tracks and non-ordinary fusion tracks remain
  fusion-owned and need not appear in `SideWorldView.contacts`.

Standalone restore can validate internal ownership without a scenario roster.
The production context supplies the authoritative staged unit-to-side map and
therefore applies the stronger roster and hostility checks.

### Current observer witnesses

- A witness side key equals every enclosed witness side. Lists use the existing
  canonical witness sort key and contain no duplicate observer/target/source-
  equipment/sensor identities.
- `detected` is exactly `true`; identifiers are nonempty and trimmed; source
  indexes are non-negative non-boolean integers; probability is finite in
  `[0, 1]`; and SNR, range, and bearing are finite, with range non-negative and
  bearing in `[0, 360)`.
- In production, observer and target both exist in the staged roster; observer
  belongs to the reporting side and target belongs to a different side. The
  exact source index, sensor ID, and modeled role resolve to one live sensor
  attachment on that observer, and `sensor_type` equals that attachment's
  modeled sensor type.
- The reporting-side world view contains the target contact, the witness time
  equals that view's last-update time and does not exceed checkpoint time, and
  the contact's reporting-sensor list contains the witness sensor ID.
- Every reporting-sensor ID on every ordinary contact resolves to at least one
  reporting-side staged sensor attachment, including an older contact that has
  no witness in the current interval. A sensor ID string by itself is not
  provenance.
- Every consumable decision with `FOW_OBSERVER_WITNESS` has one exact staged
  witness matching side, observer/shooter, target, source index, sensor ID,
  modeled role, logical time, and range. Contact records cannot stand in for
  this observer-local evidence.

### Contact information and track state

- Both contact-info dictionaries have their exact key topology. Contact levels
  and track statuses are strict non-boolean integer enums.
- Confidence is finite and within `[0, 1]`. Estimates are `null` or nonempty
  trimmed strings; levels below `CLASSIFIED` cannot retain domain, type, or
  specific estimates, and levels below `IDENTIFIED` cannot retain a specific
  estimate. A live ordinary contact cannot be `UNKNOWN`.
- Position, velocity, covariance, and every logical time are finite. Shape is
  exact. A float64 covariance must have non-negative diagonal entries, satisfy
  `numpy.allclose(P, P.T, rtol=1e-12, atol=1e-9)`, and have no eigenvalue below
  `-1e-10 * max(1.0, max(abs(P)))` after symmetrization. Validation does not
  round, repair, or replace the stored matrix.
- Hits are positive non-boolean integers and misses are non-negative
  non-boolean integers. At the completed world-view epoch, `TENTATIVE`
  requires hits below the estimator confirmation threshold; `CONFIRMED`
  requires hits at or above that threshold and age no greater than the coast
  timeout; and `COASTING` requires confirmed hit history, age no greater than
  the lost timeout, and position uncertainty no greater than the estimator
  maximum. `COASTING` cannot require age above the coast timeout because the
  current production estimator does not reset a reacquired coasting track to
  `CONFIRMED`; that lower-age status is therefore reachable state, not license
  to infer or repair history. An ordinary contact can never be `STALE` or
  `LOST`.
- `reporting_sensors` is nonempty, preserves its deterministic first-report
  order, and contains unique, nonempty, trimmed sensor IDs. It may not use
  sorting during restore to conceal a changed order. A coasting contact with
  no current witness still retains at least one real reporting attachment.

### Logical chronology

For each ordinary contact:

```text
0 <= first_detected_time
   <= last_sensor_contact_time
   == nested track last_update_time
   <= world-view last_update_time
   <= checkpoint elapsed time
```

The view and track limits apply when a checkpoint time is supplied. No epoch or
wall-clock value is inferred, repaired, clamped, or substituted.

### DETECTION RNG authority

`RNGManager` remains the only persisted random owner. In a production runtime,
`FogOfWarManager._detection` is the exact context-owned `DetectionEngine`, not
an equal private substitute whose behavior is absent from the context
checkpoint. The context's DETECTION generator, that detection engine,
`FogOfWarManager`, both state estimators, `IntelFusionEngine`,
`DeceptionEngine`, and the optional `IdentificationEngine` must retain the
declared shared generator identity wherever those owners consume this stream.
Capture and restore preflight validate both owner identity and live generator
identity before serialization or mutation.

The serialized fog manager and fusion RNG mirrors must always equal each other.
During whole-context restore, both must also equal the staged `RNGManager`
DETECTION state and the separately staged detection-engine mirror. An
internally inconsistent standalone payload rejects instead of allowing the
last committer to win.

## Staging and commit behavior

`FogOfWarManager.stage_state()` performs strict envelope parsing, stages fusion
first, validates and constructs typed world views against those staged fusion
objects, stages the current witness cache, validates internal and authoritative
RNG mirrors, and returns a non-mutating plan. It must not call the lazy live
`get_world_view()` accessor.

The returned plan is bound to the exact manager owner and to two independent
digests captured at staging: normalized content and raw runtime
type/shape/alias structure. The latter retains container class, enum class,
`TrackState`, NumPy array dtype/shape/flags, Pydantic model type, contact-to-
fusion track identity, and delivery-receipt ledger aliases. Equal JSON cannot
therefore conceal a list/tuple substitution, `TrackStatus` changed to a plain
integer, a different array dtype/subclass, a detached equal track, or a
detached receipt index.

`commit_state()` rejects a foreign, subclassed, or mutated plan before live
publication. It deep-copies the four staged owners as one alias-preserving
composite, rechecks both digests against that exact publication copy, and is a
non-throwing publication step for a successfully staged, unchanged plan:

1. commit the staged fusion state;
2. publish an exact replacement world-view map whose contacts reference the
   fusion-owned staged tracks;
3. restore the one DETECTION RNG state without allocating or drawing; and
4. publish the exact bounded current-witness map under its lock.

The whole `SimulationContext` continues to stage every owner before committing
any owner. Corrupt contact state therefore cannot partially restore roster,
clock, RNG, battle, targeting, recorder, fusion, or fog state. A valid retry
after a rejected payload must succeed and continue identically.

## Version and compatibility policy

The engine checkpoint version advances from 115 to 116. Explicit version 115,
all other older explicit versions, unknown newer versions, booleans, and
malformed values reject; there is no implicit cross-version migration.

The bounded versionless engine path remains pre-108 compatibility only. It may
retain an empty ordinary-contact FOW topology where the existing legacy rules
permit that owner, but it cannot claim or infer Phase 116 contact/fusion
associations. Any nonempty versionless ordinary-contact payload rejects. The
direct historical two-key FOW shape cannot restore a nonempty contact because
it lacks the fusion topology needed to prove the single-track owner. The
engine/context legacy-mode flag is passed explicitly into FOW staging; both a
three-key legacy payload and the synthesized historical two-key form reject
nonempty contacts or witnesses rather than acquiring format-116 semantics.
Any retained `fow-track-*` ID or FOW counter also rejects in the versionless
route even if its live contact was already LOST; legacy history cannot change
the next format-116 track ordinal or fail only after partial publication.

The historical Phase-115 implementation rewrote targeting decisions restored
from a FOW interval as historical and non-consumable because ordinary contacts
could not be reconstructed. The format-116 engine rejects explicit format 115
rather than retaining that compatibility behavior. Format 116 preserves the
serialized consumability of the current targeting interval exactly. After
both owners stage, the context cross-validates every FOW-derived decision and
revalidation against the staged reporting-side view, target/contact
association, contact epoch, fusion track, and already validated loadout/sensor
evidence. A missing or inconsistent contact rejects before mutation.

Preserving this state includes the exact immutable same-update witnesses needed
to prove the decision; it does not redraw or replay an interval. A normal next
`SimulationEngine.step()` prepares and publishes a new interval before movement
or engagement can consume it. Direct inspection or a production-consistent
consumer at the checkpoint boundary sees the same current evidence as the
source runtime, which is required for exact immediate whole-checkpoint and
API/exposure equality.

A supported dynamic roster registration deliberately invalidates the prepared
targeting interval and latest pictures before the next step. Durable contacts
and the bounded latest witness cache remain valid during that between-interval
boundary and checkpoint exactly; because no targeting decision is retained,
there is no decision-to-witness binding to perform. The next normal step
refreshes both FOW and targeting state against the expanded roster.

## Observable continuation

A valid checkpoint at logical time `T` must restore immediately to exact whole
engine checkpoint bytes in a fresh compatible runtime with a different seed
and different pre-restore object identities. In-place restore after deliberate
mutation must produce the same state.

After `T`, uninterrupted and restored branches must remain exact through:

- a no-detection interval that advances contact age and lifecycle status;
- continued coasting and eventual loss/removal at the configured boundaries;
- a later ordinary sensor detection that updates or gate-replaces the track;
- side-safe contact/targeting exposure and privileged association checks;
- movement/direct-fire decisions that consume the newly prepared current
  picture;
- deterministic subsequent recorder/event order; and
- complete context and engine checkpoint equality.

Common-operating-picture evidence in this phase means the production side
world view and its existing side-safe projection. The dormant `share_cop()`
data-link topology has no production caller and is not relabeled as a wired
capability.

## Non-goals and tracked boundaries

- Phase 116 does not change detection probability, identification thresholds,
  estimator dynamics, measurement covariance, prediction timing, or track
  association. Sensor-specific covariance/predictive estimation remains
  REM-044 / Phase 131.
- It does not turn current observer witnesses into an unbounded history.
  Explicit old format 115 remains unsupported; current format 116 preserves
  and cross-validates only the cache supporting its bounded current interval.
- It does not create data-link membership or wire `share_cop()` into production;
  production communications topology remains REM-036 / Phase 123.
- It does not close battle-membership REM-035, aggregation REM-016, or scripted
  action REM-045.
- Active deception objects are not ordinary roster-backed contacts. The
  current FOW envelope omits complete deception/signature state. Checkpoint
  capture therefore rejects any non-pristine deception owner (deployed active
  or inactive decoy, nonzero counter, or other retained decoy topology), not
  merely a decoy that happened to create a contact. Restore rejects non-roster
  contacts. Restore preflight also requires the target runtime's deception
  owner to be pristine, so a valid payload cannot leave uncheckpointed target-
  only decoys or counter history in place. That adjacent deficit must be
  closed by REM-046 / Phase 133 rather than hidden by accepting an unprovable
  target.
- Capture and restore preflight both require `DataLinkConfig()` defaults and
  empty `_data_link_networks` and `_unit_networks`. The envelope omits those
  values, so a custom configuration or populated map is explicitly
  unsupported and cannot survive an in-place restore. This does not convert
  dormant `share_cop()` into a checkpointed communications capability.

## Required evidence

Closure requires fresh command output for all of the following:

1. the clean Phase 115 transition handoff and then the promoted ordinary
   version-4 73 Easting gate, with exact endpoint identities, warm-ups, pairs,
   thresholds, semantic envelopes, artifact hashes, and final-tree binding;
2. an unchanged production red showing a nonempty serialized ordinary contact
   disappear on fresh restore and alter continuation;
3. strict standalone fresh and in-place state replacement, exact track-object
   aliasing, stale target-only state removal, and current-witness replacement;
4. factory-built, FOW-enabled production checkpoint continuation with exact
   immediate targeting/exposure/checkpoint equality, then through
   decay/coasting/loss, later detection/update or replacement, side-safe
   exposure, outcome-affecting targeting behavior, events, and whole-context
   equality;
5. a corruption matrix covering envelope/key topology; sides and contact IDs;
   roster membership and hostility; contact info; vectors/covariance;
   lifecycle status/counters; chronology; every reporting-sensor attachment;
   fusion associations/aliases; every witness key, type, canonical order, and
   duplicate identity; witness roster hostility, attachment, modeled role,
   sensor type, contact/reporting-sensor association, and exact targeting-
   decision match; omitted deception/COP target state; and every DETECTION RNG
   owner and mirror, with exact pre/post state equality and a valid atomic
   retry after every rejection;
6. empty-contact, FOW-disabled, bounded versionless, and Phase 112 Space ISR
   empty-ordinary-contact controls, including explicitly allocated empty views
   and a between-interval dynamic-roster checkpoint;
7. applicable determinism, conventions, scenario, benchmark-policy, Ruff,
   data, documentation, and broader partition validation; and
8. persisted/exposed evidence that is checked against the production path,
   followed by simplify, cross-document audit, and postmortem gates.

## Completion matrix

| Stage | Phase 116 obligation |
|---|---|
| Declared | Exact format-116 FOW/contact schema, version policy, chronology, topology, RNG, and failure contract |
| Loaded | Factory-built scenario creates the FOW/detection/fusion owners and real catalog sensor loadouts |
| Wired | Context checkpoint registry stages and commits the one FOW owner against roster, clock, fusion, detection, and RNG state |
| Enabled | Mandatory whenever FOW is present; no correctness opt-out |
| Exercised | Nonempty ordinary production contacts cross fresh and in-place restore plus later lifecycle updates |
| Outcome-affecting | Restored contacts change the next current targeting/movement or engagement result versus the unchanged red |
| Persisted/exposed | Exact whole checkpoint, fusion alias, recorder/event continuation, and side-safe/privileged contact evidence agree |

No row is complete until fresh behavioral results satisfy it. The design-review
verdict is design-only and cannot establish implementation or phase closure.

## Closure

Phase 116 passed the complete production, focused, determinism, data, scenario,
qualified broad-run, documentation, cross-document, and postmortem gates
recorded in the [Phase 116 devlog](../devlog/phase-116.md#postmortem). REM-029 is
closed. REM-036 and REM-046 remain explicit unsupported adjacent owners and do
not reduce or reopen the roster-backed ordinary-contact contract.
