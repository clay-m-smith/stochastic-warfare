# Development Phases - Block 13

**Status:** Planned follow-up handoff; implementation has not started

Block 13 owns integrity deficits discovered while specifying and validating
Phases 112 and 113. It is not part of either implementation or the Block 12
completion claim. Each phase must follow the repository's full specification,
production-red, implementation, validation, documentation, postmortem, and
single-commit workflow before its remediation item can close.

## Phase 115 - Sensing-Aware Tactical Standoff

Replace unrestricted catalog-range movement holding with a typed targeting
precondition that distinguishes physical weapon reach from owner-side sensing,
visibility, fire control, and live contact state. Preserve explicit authored
holds and prove enabled/disabled movement and combat outcomes without extending
a sensor or inventing a target.

Exit criteria: REM-028 is closed with declared, loaded, wired, enabled,
production-exercised, outcome-affecting, and checkpoint/exposure evidence.

## Phase 116 - Fog-of-War Contact Continuation

Restore complete nonempty `SideWorldView` contact state through the
fog-of-war-owned checkpoint boundary. Validate side/contact topology,
`ContactInfo`, nested track state, logical update times, and DETECTION RNG
authority before mutation.

Exit criteria: REM-029 is closed with exact fresh-runtime continuation through
decay, detection updates, common-operating-picture behavior, subsequent
events, and whole-context checkpoint equality.

## Phase 117 - Historical Outcome-Envelope Integrity

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
