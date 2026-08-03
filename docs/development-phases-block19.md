# Development Phases - Block 19

**Phase range:** 135--137

**Status:** Planned follow-up handoff; Phase 135 is the first phase in this block
and has not started

Block 19 owns the package-bound accepted-evidence attestation deficit surfaced
by Phase 117's no-`.git` Docker review. Phase 117 locally proves that the
packaged loader with zero accepted claims loads the strict ledger and exposes
the catalog conservatively; its hosted no-`.git` image smoke is configured and
pending the phase push. Neither result proves that a future
`production_validated` claim can survive packaging: repository acceptance
currently depends on Git ancestry, committed ledger content, the study plan,
and an artifact retained beneath `docs/`, while the image intentionally ships
neither `.git` nor `docs/`.

Phase 117's exhaustive web audit also corrected bounded canonical-field,
status-decoding, terrain-enum, and run-navigation defects while exposing a
larger replay/export/editor/analysis semantic boundary. Phase 136 owns that
separate follow-up after Phase 135; REM-041 / Phase 128 remains the owner for
player authorization and complete side-safe FOW projection.

The same closure audit found that authored escalation tuning is discarded and
that DEW is presence-enabled without a configured catalog scenario exercising
a DEW-capable loadout. Phase 137 owns that runtime/data authority separately
from Phase 136's editor UX.

## Phase 135 - Package-Bound Accepted Historical Evidence

Status: **Not started**. REM-048 remains queued.

Define one build-time attestation boundary that verifies every accepted claim
with the full repository/Git contract before packaging and emits only the
minimum immutable receipt and evidence inputs needed by the no-`.git` runtime.
The runtime must bind the receipt to the image source revision and source
manifest, exact ledger and claim digests, plan and artifact digests, source
references, metric bindings, and production-input identities. It must reject
missing, extra, stale, symlinked, or modified evidence rather than skipping
the unavailable Git checks or trusting a build argument alone.

Exit criteria: a clean, independently predeclared, source-backed production
`PASS` is accepted through the repository loader, packaged with a build-time
receipt, and exposed with the identical claim-level disposition by a real
no-`.git` API image. Tamper controls must cover the source revision/manifest,
ledger, claim, plan, artifact, source binding, and receipt. A fixture-only
receipt or an image that merely preserves the current zero-accepted
unsupported result is not behavioral completion evidence.

## Phase 136 - Web UI Semantic Integrity

Status: **Not started**. REM-049 remains queued.

Define one explicit replay cursor across production ticks, interpolated frames,
chart markers, embedded/fullscreen maps, and URL/tab state. Make engagement
overlays causal, derive selection from the current frame, and keep every
overlay semantically aligned. Replace prefix-only event CSV with a complete,
ordered, count-receipted export or an explicit truncation failure. Add
catalog-backed Space configuration selection before enabling editor creation.
Add a complete era-aware commander picker and a production-owned exact-unit or
typed side-policy doctrine editor without legacy proxy fields. Bind every
fixed or selectable analysis input to requests, results, and reproduction
evidence. REM-041's authenticated side-safe projection remains a separate
prerequisite for any opposing-player map claim.

Exit criteria: a real retained event set larger than one page exports exactly
once and reloads with the same count/order; chart, map, fullscreen, and URL
cursors agree across tab changes without future-event leakage; selected-unit
and status overlays follow the current frame; an editor-created Space config
uses explicit compatible catalog IDs and passes the production loader;
commander and doctrine choices cover the applicable catalogs, pass the loader,
and appear in exact initial/arrival provenance; and analysis results expose all
choice/fixed-input provenance. Focused browser/API tests, full frontend
lint/typecheck/tests, and a cross-document audit must be green. A UI mock,
query-string write without a consumer, first-page CSV, or schema-valid proxy
default is not completion evidence.

## Phase 137 - Escalation and DEW Configuration Integrity

Status: **Not started**. REM-050 remains queued.

Replace free-form/dead optional-suite data with strict typed production
configuration. Consume supported escalation thresholds, hysteresis, cooldown,
and related settings at their runtime owners; reject unknown or enable-like
proxy fields. Define explicit DEW presence/enabled semantics and add a
defensible scenario or production fixture in which a configured DEW-capable
unit executes a real engagement.

Exit criteria: two distinct valid escalation configurations load exact runtime
state and cause the declared observable difference; invalid/unknown fields
fail before construction; one configured catalog DEW loadout produces an exact
engagement/event/resource outcome while an explicit disabled/absent control
does not; and both suites preserve configuration and live state through API
execution, provenance, checkpoint continuation, data validation, and scenario
evaluation. Engine construction, block-presence badges, or a proxy platform do
not establish completion.
