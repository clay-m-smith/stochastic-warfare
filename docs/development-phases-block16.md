# Development Phases - Block 16

**Phase range:** 132

**Status:** Planned follow-up handoff; Phase 132 has not started

Block 16 owns the scripted-scenario action-integrity deficit surfaced while
validating Fallujah during Phase 115. It is independent of REM-028's tactical-
standoff claim and does not reopen Phase 101's delivered scenario/catalog work.
Phase 132 must follow the full specification, production-red, implementation,
scenario/data/determinism validation, documentation, postmortem, and single-
commit workflow before REM-045 can close.

## Phase 132 - Scripted Scenario Action Integrity

Status: **Not started**. REM-045 remains queued.

Replace `event_type` plus an untyped parameter dictionary with a discriminated,
typed action union for the four existing Fallujah action families: HBIED
detonation, WP fire-zone creation, unit relocation, and casualty application.
Load and bind every action to authoritative runtime owners and exact targets
before publication. A due action must either commit its complete effect once or
fail explicitly without being marked complete; missing engines, obstacles,
units, malformed targets, and downstream owner failures may not silently
succeed. Relocation and casualties must use production lifecycle boundaries
rather than direct position assignment or roster mutation.

Persist the schedule identity, pending/completed disposition, action ordinal,
logical due/commit time, and authoritative effect evidence. Restore must reject
schedule drift and continue pending or completed actions exactly once in both
fresh and in-place runtimes. Expose enough recorder/evaluator/API evidence to
distinguish declaration, attempted execution, committed effect, and explicit
failure without treating a log or fired-set membership as the outcome.

Exit criteria: REM-045 is closed with `D/L/W/X/O/P=Yes` and `E=N/A`; typed
Fallujah actions are declared, loaded, owner-bound, production-exercised,
outcome-affecting, recorded/exposed, and exactly checkpoint-continuable. Each
of the four existing action families has a realistic due-action production
control plus missing-owner/target and rollback controls. The scenario must
exercise the public runtime lifecycle far enough to prove dispatch and effects;
schema loading, reference searches, direct private-dispatch calls, mocks,
logs, and no-crash runs do not qualify. Phase 132 does not introduce a general
scripting language or new action families.
