# Development Phases - Block 13

**Phase range:** 115 through 127

**Status:** Active; Phases 115--116 are complete and Phase 117 is next

Block 13 owns integrity deficits discovered while specifying and validating
Phases 112 through 114. It is not part of those implementations or the Block
12 completion claim. Each phase must follow the repository's full
specification, production-red, implementation, validation, documentation,
postmortem, and single-commit workflow before its remediation item can close.

## Phase 115 - Sensing-Aware Tactical Standoff

Status: **Complete**. REM-028 is closed with accepted production, data,
determinism, scenario, exposure, qualified broad-run, documentation, and
postmortem evidence. Phase 116 is complete and Phase 117 is next.

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
documentation, cross-document, and postmortem evidence. Phase 117 is next and
remains unstarted.

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

Status: **Not started**. REM-030 remains queued.

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
REM-030 remains queued for this phase.

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

## Phase 118 - Performance-Flag Semantic Integrity

Status: **Not started**. REM-031 remains queued.

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

Exit criteria: REM-031 is closed with declared, loaded, wired,
enabled/disabled, realistic production-exercised, observable semantic-verdict,
and persisted/exposed evidence for every flag. Every required validation job
must fit its declared timeout without discarding unexamined catalog runs.

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
