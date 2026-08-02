# Development Phases - Block 14

**Phase range:** 128 through 130

**Status:** Planned follow-up handoff; no Block 14 phase has started

Block 14 owns three integrity deficits surfaced while implementing Phase 115.
They are not part of REM-028 or the Phase 115 capability claim. Each phase must
follow the repository's full specification, production-red, implementation,
validation, documentation, postmortem, and single-commit workflow before its
remediation item can close.

## Phase 128 - Player-Safe Targeting Exposure Authorization

Status: **Not started**. REM-041 remains queued.

Authenticate the caller for player-facing run-frame reads and derive the
authorized side and exposure scope from that identity. Make the ordinary
player-facing default side-safe, reject privilege escalation and cross-side
requests before reading stored targeting evidence, and preserve an explicitly
authorized operator/evaluator path. The existing `SIDE_FOW` projection is a
structurally safe payload transformation, but a caller-supplied `scope` or
`side` query parameter is not authorization.

Exit criteria: REM-041 is closed with declared, loaded, wired, enabled,
realistic production-exercised, observable denial/allowance, and persisted
audit evidence for unauthenticated, player, cross-side, and privileged callers.
Frontend defaults and direct API use must both be safe; client-side filtering
does not qualify.

## Phase 129 - Authored Weapon-Mount and Director Topology

Status: **Not started**. REM-042 remains queued.

Extend equipment data with exact weapon-mount/director associations and load
that topology through the single production loadout boundary. A sensor may
direct only its authored weapon or mount group, even when another attachment
on the same unit has an otherwise compatible modeled role. Validate initial,
reinforcement, and checkpoint reconstruction paths without inferring topology
from names, list position, or generic role compatibility.

Exit criteria: REM-042 is closed with complete catalog coverage or explicit
unsupported data, deterministic canonical bindings, mixed-loadout rejection,
production engagement effects, recorder/API exposure where required, and exact
fresh/in-place checkpoint continuation.

## Phase 130 - Availability-Aware Threat Selection

Status: **Not started**. REM-043 remains queued.

Define a typed target-selection contract that incorporates current weapon,
ammunition, sensing, fire-control, and target-domain availability before threat
ranking. Preserve deterministic ordering and explicit no-solution outcomes;
do not use a high ground-truth threat score to select a target that the shooter
cannot currently service, and do not change physical performance or scenario
calibration to force a preferred choice.

Exit criteria: REM-043 is closed with declared selection semantics, loaded and
wired policy, realistic multi-target production controls, observable movement
and engagement differences, exact RNG/order discipline, exposed decision
provenance, and fresh/in-place checkpoint continuation.
