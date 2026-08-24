# Development Phases - Block 13

**Phase range:** 115 through 127

**Status:** Active; Phases 115--118 are complete and Phase 119 has not started

Block 13 owns integrity deficits discovered while specifying and validating
Phases 112 through 114. It is not part of those implementations or the Block
12 completion claim. Each phase must follow the repository's full
specification, production-red, implementation, validation, documentation,
postmortem, and single-commit workflow before its remediation item can close.

## Phase 115 - Sensing-Aware Tactical Standoff

Status: **Complete**. REM-028 is closed with accepted production, data,
determinism, scenario, exposure, qualified broad-run, documentation, and
postmortem evidence. Phases 116--118 are complete and Phase 119 has not
started.

Replace unrestricted catalog-range movement holding with a typed targeting
precondition that distinguishes physical weapon reach from owner-side sensing,
visibility, fire control, and live contact state. Preserve explicit authored
holds and prove enabled/disabled movement and combat outcomes without extending
a sensor or inventing a target.

Exit criteria: REM-028 is closed with declared, loaded, wired, enabled,
production-exercised, outcome-affecting, and checkpoint/exposure evidence.

## Phase 116 - Fog-of-War Contact Continuation

Status: **Complete**. REM-029 is closed with accepted specification, benchmark
promotion, production, determinism, data, scenario, qualified broad-run,
documentation, cross-document, and postmortem evidence. Phases 117--118 are
complete and Phase 119 has not started.

Before Phase 116 changes production state, promote the clean Phase 115
73 Easting transition endpoint to an ordinary version-4 paired reference and
prove the exact promoted workload/semantic gate. The reviewed promotion is a
baseline handoff from Phase 115's non-timing `transition_qualified` evidence;
it must not rewrite that evidence as a performance pass.

Restore complete nonempty `SideWorldView` contact state through the
fog-of-war-owned checkpoint boundary. Validate side/contact topology,
`ContactInfo`, nested track state, logical update times, and DETECTION RNG
authority before mutation.

Exit criteria: REM-029 is closed with exact fresh-runtime continuation through
decay, detection updates, common-operating-picture behavior, subsequent
events, and whole-context checkpoint equality.

## Phase 117 - Historical Outcome-Envelope Integrity

Status: **Complete**. REM-030 is closed.

Replace catalog-wide winner tables and legacy-runner comparisons presented as
historical accuracy with one typed, provenance-bearing production validation
contract. Inventory every scenario, test, and public historical-outcome claim
and classify it as production-validated, current-engine regression only, or
explicitly unsupported. Debecka Pass is the concrete production red that
surfaced the issue, not the phase's only scenario.

Phase 113 supplied additional current-engine regression signals for this
inventory: default 73 Easting now exposes routed blue units while its explicit
morale-neutral benchmark control does not; the existing Waterloo 20-seed sweep
shifted from 20 British wins to 18 British and 2 French wins; and seed-42
Trafalgar and `calibration_arctic` changed terminal winner, duration, and force
status composition. These deterministic observations identify fidelity review
work; they are not historical-validation verdicts or calibration authority.
Phase 117 closed REM-030 against this inventory after accepted cross-document
and postmortem review. The retained study remains a truthful production
`FAIL`; no claim was promoted.

Phase 115 adds two more inventory signals. Debecka changes from the Phase 114
10/10 blue current-engine regression to 4/10 after the shared targeting owner
correctly removes most F-14/M61 ground fire without a ground-compatible
director; disabling automatic standoff recovers only 7/10. Its four-hour
scenario horizon also precedes its authored six-hour blue fallback, while a
six-hour control awards that fallback after all blue units are already
non-active in six seeds. Fallujah seed 42 changes from 115 ticks / 575 seconds
to 40 ticks / 200 seconds while retaining blue `force_destroyed`, combat, and
pre-emplaced IED outcomes. It ends before the first scripted action at H+7,
which separately surfaced REM-045 / Phase 132. These are deterministic
current-engine semantic signals, not historical validation, a calibration
verdict, or authority to tune physical performance, victory policy, or
scenario parameters.

For every claim retained as validated, predeclare exact metric definitions and
units, event boundaries, source provenance and quality, justified ranges or
tolerances, scenario/input fingerprints, calibration or training inputs, and
an independent held-out seed set. Execute the held-out study through
`SimulationRuntimeFactory`, retain raw vectors and verdict artifacts, and fail
closed on missing metrics or envelope misses. Winner-only agreement, multiple
seeds from calibrated inputs, metadata presence, and a successful legacy
runner do not qualify. A scenario without defensible evidence must be labeled
unsupported rather than calibrated until it passes, and physical weapon
performance may not be changed merely to force an outcome into range.

Exit criteria: REM-030 is closed with an auditable disposition for every
catalog/public claim and fresh production, held-out, persisted evidence for
each scenario still described as historically validated. No regression-only
or same-data calibrated result is described as historical or predictive
validation.

Phase 117 locally proves conservative packaged-loader exposure of the current
zero-accepted ledger. Its Phase 117 push prerequisite is satisfied at
`84cf4c4`, but no successful hosted no-`.git` image result is recorded in the
repository; that smoke remains unverified pending a successful workflow run.
Package-bound attestation for a future nonempty accepted claim is separately
assigned to REM-048 / Phase 135 and does not permit this phase to imply that
unexercised capability.

## Phase 118 - Performance-Flag Semantic Integrity

Status: **Complete**. The owner-approved v7 study is a complete, independently
reload-verified eligible `FAIL`; the accepted qualified-negative postmortem
closed REM-031 while preserving that result and the explicit unsupported
production disposition below.

Replace Block 9's one-sided authored-configuration checks with a typed, paired
production contract for `enable_detection_culling`,
`enable_scan_scheduling`, `enable_lod`, `enable_soa`, and
`enable_parallel_detection`. Classify each flag before measurement as either a
semantics-preserving execution optimization or an explicit model-fidelity
approximation; do not assume that one contract applies to all five.

Execute same-revision, same-data, same-config, common-seed off/on pairs through
`SimulationRuntimeFactory`, prove that each intended branch executes, and
repeat both sides deterministically. A semantics-preserving flag must retain
its predeclared terminal-state, event, RNG-authority, and fresh-checkpoint
continuation contract. An approximation control must be named and documented
as such and satisfy a justified, predeclared paired semantic-error budget;
winner-only agreement is insufficient. Persist raw vectors, complete runtime
and data fingerprints, semantic digests, and a per-flag verdict in bounded,
sharded artifacts. Performance timing remains a separate claim, and combat
parameters may not be recalibrated to conceal a semantic delta.

The implemented contract classifies detection culling, SoA selection, and
parallel per-side detection as semantics-preserving execution optimizations.
Native scan scheduling and sensing-only LOD remain model-fidelity
approximations, but they are no longer supported production controls. The
shared calibration/runtime/checkpoint boundary now rejects either flag when
true and rejects non-default LOD tuning; false/default compatibility values
remain accepted. Runtime-owned typed receipts expose the exact supported flag
values and controlled work, while `RNGManager` owns a persisted
identity-addressed FOW transcript so parallel completion order cannot select a
different stochastic decision. `GET /api/meta/performance-flags` projects the
same canonical support registry and retained evidence identity.

The retained v6 diagnostic exhausted its terminal budget at 96 pairs / 396
attempts under explicit external-contention qualification and ended `ERROR`.
On 2026-08-22 the owner approved Option A for the v7 proof topology. The frozen
schema-2 v7 plan used 16 fresh held-out seeds disjoint from all diagnostic
exclusions, 96 pairs / 396 attempts, and plan SHA-256
`5ffb74205281d8913b618fc607f47bf4cdccc0f2741bd812cc82989761c1b41d`.
Its one authoritative execution published a complete `EXTERNALLY_CONTENDED`
eligible `FAIL`, independently reproduced at manifest artifact SHA-256
`bf9e00ce4a7774af29b5657c49bbbe4481b407a966d9922e48970022f5c6ad86`.
Culling, SoA, and parallel detection passed 16/16. Scan scheduling passed 3/16
and failed 13/16. Calibration LOD passed 16/16; Suwalki LOD passed 12/16 and
failed 4/16, while all three accepted case-level recovery totals passed at 74,
37, and 185. No failed shard was relabelled, no budget was widened, and no
speed conclusion follows.

The raw study, frozen plan, one-off executor/verifiers, and immutable terminal
bytes are intentionally off main. Their durable locators are
`branch=evidence/full; path=docs/evidence/phase-118/v6-terminal/`,
`branch=evidence/full; path=docs/evidence/phase-118/v7-terminal/`,
`branch=evidence/full; path=data/validation/performance_semantics/phase118.yaml`,
and
`branch=evidence/full; path=docs/evidence/phase-118/runtime-manifest-handoff.json`.
The typed handoff reconstructs the immutable 1,408-entry execution snapshot
into the reviewed 1,408-entry qualified-negative retirement snapshot through
exactly fifteen content-addressed modifications: execution SHA-256
`2f10ab7c7a2b409067c90f92616609e921750fa7641c4d3165f90b53fa21e9a8`,
retirement SHA-256
`0a6b32a48fd7ea764d6522eb7ebccdc32c803663aed295c916ba47240668bf07`,
and handoff SHA-256
`b505edc418f87ffdf659bed52b502cef043df472c8a04696d0fda8d99d4e746d`.
The archived validation machinery can reload the v7 `FAIL` and handoff but
cannot turn the qualified-negative result into a speed claim.

The required matched production profile separately found a material local
runtime regression: the phase-start ten-tick `benchmark_battalion` median was
47.035449 seconds and the Phase 118 median was 59.220597 seconds, a 1.259063
ratio (+25.906%), with identical results and less than 0.85% dispersion in
each group. cProfile enclosed 81.60% of the instrumented delta beneath the new
transactional FOW update. Phase 118 retains those integrity checks and makes
no speed claim; REM-055 / Phase 142 owns a semantics-preserving optimization
with persistent timing, call, and memory proof.

Exit criteria: REM-031 is closed with declared, loaded, wired, realistic
production-exercised, outcome, and persisted/exposed evidence for all five
entries. The three supported controls require enabled/disabled proof; the two
failed controls require explicit rejection at every current production input
and restore boundary. Every required validation job must fit its declared
timeout without discarding unexamined catalog runs.

Phase 118 also surfaced five separately scoped follow-ups. REM-051 / Phase 138
still owns the planned battle-scoped detection scan-history lifecycle. The
2026-08-23 tiered modular-monolith consolidation closed REM-052 and REM-053 and
retired their planned Phases 139 and 140 before start after establishing one
FOW update owner and one checkpoint snapshot boundary. Block 20 preserves
those planned bodies as historical handoff context.
REM-054 / Phase 141 in Block 21 owns any future scan-scheduling or LOD
re-enablement, including the track-lifecycle and sourced-covariance
prerequisites exposed by the terminal v7 study. REM-055 / Phase 142 in the
same block owns the measured transactional-FOW runtime regression. None
weakens REM-031's current qualified-negative proof obligations, and creating
those roadmap entries does not start the later phases.

## Phase 119 - Guerrilla Concealment State Integrity

Status: **Not started**. REM-032 remains queued.

Replace the historical populated-area `blend_probability -> ROUTING` proxy
with a typed non-morale concealment/disengagement owner. Resolve populated-area
membership through the production population boundary, define success and
re-emergence lifecycle, and wire the state into detection, targetability,
movement, active-force and victory accounting, events, recorder/API exposure,
and checkpoint continuation. Do not represent concealment as morale collapse
or remove a unit without an explicit lifecycle.

Exit criteria: REM-032 is closed with declared, loaded, wired,
enabled/disabled, realistic production-exercised, outcome-affecting, and
persisted/exposed evidence. The Phase 113 explicit unsupported error remains
until the complete replacement is verified in this phase.

## Phase 120 - Surrender and POW Lifecycle Integrity

Status: **Not started**. REM-033 remains queued.

Replace the rejected rout-owned surrender helper with one typed production
transaction that commits authoritative morale/status/route state together with
captor provenance and a prisoner lifecycle. Wire exact surrendered personnel
into logistics handling, resource costs, transfers/releases, events,
recorder/API exposure, and checkpoint continuation. Do not fabricate a captor,
an escape count, or a logistics handoff from an isolated subsystem call.

Exit criteria: REM-033 is closed with declared, loaded, wired, realistic
production-exercised, outcome-affecting, and persisted/exposed evidence for
the complete surrender-to-prisoner lifecycle, including deterministic failure,
rollback, duplicate-processing, and continuation controls.

## Phase 121 - Production Event-Time Integrity

Status: **Not started**. REM-034 remains queued.

Replace `datetime.min` sentinels in production aggregate casualty and
auto-resolve events with one explicit authoritative simulation timestamp.
Thread the logical clock through every live caller, reject absent or invalid
time before publishing, and preserve exact event order without introducing a
wall-clock fallback or second clock owner.

Exit criteria: REM-034 is closed with declared, loaded, wired, realistic
production-exercised, outcome-affecting, and persisted/exposed evidence for
aggregate engagement/damage and auto-resolve destruction timestamps, including
recorder/API/timeline output and deterministic checkpoint continuation.

## Phase 122 - Battle Membership Topology Integrity

Status: **Not started**. REM-035 remains queued.

Replace the one-battle-per-side-pair/global-roster shortcut with one typed,
deterministic battle-membership owner. Build membership from explicit spatial,
command, and participation rules; support spatially distinct concurrent
battles between the same sides; and prevent one unit from entering conflicting
active battles. Route resolution, movement, combat, logistics activity,
aggregation, and victory reads through the exact topology.

Exit criteria: REM-035 is closed with declared, loaded, wired, realistic
production-exercised, outcome-affecting, and persisted/exposed evidence for
deterministic battle creation, membership, merge/split/termination behavior,
and fresh/in-place checkpoint continuation. Correct membership is mandatory,
so an enabled/disabled correctness toggle is N/A.

## Phase 123 - Production C2 Communications Topology

Status: **Not started**. REM-036 remains queued.

Load exact communications equipment and link/relay topology onto production
units, HQs, and sides. Validate ownership, capabilities, range, latency,
reliability, and availability before runtime construction, then route order
issue, propagation, acknowledgement, degradation, interception, and failure
through that live network. Do not infer communications from era or multiply a
delay on an absent path.

Exit criteria: REM-036 is closed with declared, loaded, wired,
enabled/disabled, realistic production-exercised, outcome-affecting, and
persisted/exposed evidence for connected, disconnected, degraded, and
destroyed-link order delivery, including deterministic continuation and
recorder/API exposure.

## Phase 124 - Scheduled CBRN and Nuclear Action Integrity

Status: **Not started**. REM-037 remains queued.

Define strict scheduled CBRN actions with a real owner, delivery asset and
inventory, target, logical time, agent or nuclear yield, authorization, and
era/capability gate. Execute them from the production session loop and commit
inventory, effects, events, and action lifecycle together. Construction or a
direct call to `NuclearEffectsEngine` is not scheduled-employment evidence.

Exit criteria: REM-037 is closed with declared, loaded, wired,
enabled/disabled, realistic production-exercised, outcome-affecting, and
persisted/exposed evidence for available/unavailable and successful/failed
actions, exact RNG ownership, atomic rejection, recorder/API output, and
checkpoint continuation.

## Phase 125 - Automatic Medical Lifecycle Integrity

Status: **Not started**. REM-038 remains queued.

Load medical facilities, staff, capacity, supplies, evacuation routes, and
triage policy, then commit a real battle casualty once into authoritative
personnel and medical state. Route evacuation, admission, treatment,
return-to-duty, death, and resource/capacity failures through logical time.
Public test setup of a facility and casualty remains a boundary proof, not the
automatic production lifecycle.

Exit criteria: REM-038 is closed with declared, loaded, wired,
enabled/disabled, realistic production-exercised, outcome-affecting, and
persisted/exposed evidence from battle casualty through final medical
disposition, including exact unit/crew strength, resources, events, API, and
checkpoint continuation.

## Phase 126 - Automatic Maintenance and Spares Lifecycle Integrity

Status: **Not started**. REM-039 remains queued.

Register each live loadout equipment instance automatically with one
maintenance/readiness owner, including reinforcement and aggregation paths.
Route diagnosis, repair priority, parts reservation and consumption, repair
start/completion/cancellation, and failure through real Class IX inventory and
logistics reachability. Do not pass a literal parts amount to simulate a
production logistics transaction.

Exit criteria: REM-039 is closed with declared, loaded, wired,
enabled/disabled, realistic production-exercised, outcome-affecting, and
persisted/exposed evidence for breakdown-to-repair with parts
available/unavailable, atomic rollback, exact RNG accounting, recorder/API
output, and checkpoint continuation. REM-020 and REM-021 retain their broader
activity-demand and inventory-authority scope.

## Phase 127 - Validation Era Propagation Integrity

Status: **Not started**. REM-040 remains queued.

Remove the silent modern-era fallback from the validation-only campaign
conversion. Preserve exact normalized era and every required production source
field through one typed projection, and resolve the selected era only at the
authoritative runtime factory. Prevent future production fields from being
silently dropped by a duplicated validation model.

Exit criteria: REM-040 is closed with declared, loaded, wired, realistic
production-exercised, outcome-affecting, and persisted/exposed evidence that a
non-modern validation campaign retains its gates, catalog/loadout selection,
effective era contract, fingerprint, artifact provenance, and deterministic
continuation relative to an explicit modern control. Enabled/disabled is N/A
because exact source identity is mandatory.
