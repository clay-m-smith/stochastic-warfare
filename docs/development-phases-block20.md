# Development Phases - Block 20

**Phase range:** 138--140

**Status:** Planned follow-up handoff; Phase 138 is the first phase in this
block and has not started

Block 20 owns three production-state and duplication deficits surfaced while
Phase 118 consolidated performance-flag semantics. The terminal v7 study is
already complete and retained as immutable qualified negative evidence; these
phases neither reinterpret that `FAIL` nor reopen Phase 118's support decision.
They follow the numbered remediation sequence and may not start before every
earlier phase prerequisite has passed its own postmortem and coherent commit.
Block 21 separately owns any future scan-scheduling or LOD re-enablement.

## Phase 138 - Detection Scan-State Lifecycle Integrity

Status: **Not started**. REM-051 (P1) remains queued.

Replace the battle-resolution reach-through that discovers
`FogOfWarManager._detection` and globally calls `reset_scan_counts()`. One
typed public owner must define the lifecycle of integration-gain scan state by
its exact sensor/observer/target identity and prune only state made invalid by
the completed battle or departed topology. Resolving one battle must not erase
counts used by a spatially or topologically unrelated active battle, and an
absent or wrong owner must fail explicitly rather than being silently skipped
through `getattr()`/`hasattr()`.

Exit criteria: with at least two simultaneous production battles, accumulate
nonzero scan state in both, resolve one battle through the ordinary
`SimulationEngine` loop, and prove that only the explicitly retired identities
are removed exactly once while the surviving battle's counts, subsequent
detection probability/state, events, and RNG continuation remain identical to
an unresolved control. Prove the no-FOW/empty-state path, duplicate resolution,
reinforcement/reappearance policy, and invalid-owner rollback. Persist and
restore the exact surviving/pruned topology through a fresh runtime and obtain
identical continuation. The engine must use a typed public transaction; a
private reach-through, global clear, mocked reset call, or key-existence check
is not completion evidence.

## Phase 139 - Fog-of-War Update Boundary Consolidation

Status: **Not started**. REM-052 (P2) remains queued.

Eliminate the independently maintained legacy body behind
`FogOfWarManager.update()`. Every supported FOW cycle must route through one
typed transaction that shares production attachment identity, cadence,
conservative selection, indexed RNG, estimation, contact/fusion, witness,
receipt, ordering, and atomic publication semantics. If the old untyped call
shape cannot satisfy those invariants, it must reject explicitly instead of
running the legacy modulo scheduler, polygonal culling, shared-stream draws,
or partial in-place mutation.

Exit criteria: production factory runs and every retained public standalone
consumer reach the same canonical update owner. Enabled and disabled controls
for culling, scheduling, SoA, and dispatch prove exact declared branch work;
typed legacy-compatible inputs, if any remain supported, produce the same
world view, fusion/contact lifecycle, witnesses, detector decisions, receipt,
RNG transcript, and checkpoint continuation as the canonical boundary.
Malformed, incomplete, duplicate-side, failed-side, old untyped, and
wrong-owner inputs reject without partial state or RNG consumption. Remove the
second algorithm rather than hiding it behind an adapter that still computes
different behavior; source deduplication alone is not behavioral evidence.

## Phase 140 - Single-Snapshot FOW Checkpoint Integrity

Status: **Not started**. REM-053 (P2) remains queued.

Replace repeated `FogOfWarManager.get_state()` serialization during one
`SimulationContext` checkpoint capture with one typed, immutable owner-issued
snapshot. Reuse that exact snapshot for targeting, cadence, detection-scan,
RNG, roster/loadout, and context-state cross-validation and for the final
checkpoint payload. No validator may silently recapture a later view of the
same mutable graph, and validation must not publish or mutate live state.

Exit criteria: a realistic factory-built FOW runtime with nonempty contacts,
witnesses, fusion tracks, cadence assignments, indexed transcript, and scan
counts captures exactly one owner snapshot per checkpoint operation and binds
every cross-owner validation result and emitted FOW payload to its digest.
Adversarial mutation or an active/poisoned FOW transaction between acquisition
and publication must reject atomically rather than mix epochs. Fresh-runtime
restore must reproduce the complete snapshot and then continue with exact
events, contacts, receipts, RNG decisions, and terminal state relative to an
uninterrupted control. Empty/disabled FOW and explicit legacy migration paths
must remain correct. Any performance improvement must be measured separately;
a call counter, source search, or faster serialization without behavioral and
continuation proof is not completion evidence.
