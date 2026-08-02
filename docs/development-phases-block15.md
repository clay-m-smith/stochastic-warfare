# Development Phases - Block 15

**Phase range:** 131

**Status:** Planned follow-up handoff; Phase 131 has not started

Block 15 owns the estimator-fidelity deficit surfaced while repairing stable
FOW track reuse in Phase 115. It is independent of REM-028's tactical-standoff
claim. Phase 131 must follow the full specification, model-research,
production-red, implementation, validation, documentation, postmortem, and
single-commit workflow before REM-044 can close.

## Phase 131 - Sensor Measurement Covariance and Predictive Tracking

Status: **Not started**. REM-044 remains queued.

Replace the generic isotropic `max(5% of range, 1 m)` fusion uncertainty with
typed, provenance-bearing range/bearing measurement-error models for each
applicable sensor class. Convert those errors into a position covariance in
the current observation geometry, and execute elapsed-time prediction plus
measurement update on detached track state before one atomic commit. Define
timestamp monotonicity, process-noise ownership, gating, identity replacement,
and checkpoint continuation without adding a second detection draw.

The Phase 115 one-metre minimum is a declared numerical lower bound that keeps
the conventional Kalman innovation covariance nonsingular; it is not sourced
historical sensor accuracy. Removing it without a complete noise-free or
constrained estimator is not an acceptable implementation.

Exit criteria: REM-044 is closed with complete catalog coverage or explicit
unsupported classifications; source/provenance and units for every covariance
input; declared, loaded, wired, and production-exercised predict/update
semantics; realistic stationary and moving-contact outcome controls; bounded
gated replacement with no orphan state; deterministic parallel execution;
and exact in-place/fresh checkpoint and privileged/side-safe exposure evidence.
