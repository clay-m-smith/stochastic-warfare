# Phase 116 - Fog-of-War Contact Continuation

**Status:** Complete

**Started:** 2026-08-02

## Why this phase exists

REM-029 records that `FogOfWarManager.get_state()` serializes nonempty
`SideWorldView.contacts`, while `set_state()` restores only view update times.
Phase 116 owns the exact roster-backed ordinary-contact continuation contract in
[`fog-of-war-contact-continuation.md`](../specs/fog-of-war-contact-continuation.md).

## Start gate

Phase 115 passed postmortem and was committed as
`7a632c0f52a9d254ca7e43a14c20ead058384b8b`. Its hosted API oracle then exposed
one stale pre-Phase-115 cadence expectation; the production behavior was
causally replayed, the oracle was corrected, and corrective commit
`271ec49ceb508bdd050e2d5c3072ac91456cca7c` passed all hosted workflows. Exact
Phase 115 closure and corrective evidence remains in
[`phase-115.md`](phase-115.md).

Phase 116 began from a clean synchronized tree:

```text
git status --short --branch
# ## main...origin/main

git rev-parse HEAD
git rev-parse origin/main
# 271ec49ceb508bdd050e2d5c3072ac91456cca7c
# 271ec49ceb508bdd050e2d5c3072ac91456cca7c

git pull --ff-only origin main
# From https://github.com/clay-m-smith/stochastic-warfare
#  * branch            main       -> FETCH_HEAD
# Already up to date.
```

`CODEX.md`, `AGENTS.md`, Block 13, REM-029, the Phase 115 devlog, checkpoint
specification, architecture, FOW/fusion/estimator/context/engine code, and the
applicable `$spec` and `$design-review` instructions were read before
production edits.

## Clean Phase 115 handoff evidence

Before changing the benchmark contract or production state, the clean final
Phase 115 endpoint reproduced its strict non-timing transition:

```text
.venv/bin/python scripts/run_paired_benchmark.py transition \
  --scenario 73_easting \
  --artifact /tmp/sw-phase116-73-transition-handoff.json \
  --worker-timeout-seconds 300
# 73_easting: transition_qualified; timing=not_applicable;
# artifact_sha256=f8dfbbae89aaa868789b838967ea9f164ecfcbe7ce013b8632ee0db98a398ac9

.venv/bin/python scripts/run_paired_benchmark.py verify-final \
  --artifact /tmp/sw-phase116-73-transition-handoff.json \
  --verification /tmp/sw-phase116-73-transition-handoff-final-tree.json \
  --worker-timeout-seconds 300
# 73_easting: final-tree transition_qualified;
# final_commit=271ec49ceb508bdd050e2d5c3072ac91456cca7c;
# verification_sha256=83efa588b33d2d11a640a1e7d0c82b7a8f2f018833740e65de19996a5687b1aa
```

The closure intentionally contains no duration, pair, ratio, or performance
decision. It preserves the Phase 115 handoff and is not counted as the Phase
116 ordinary benchmark pass.

## Specification and design gate

The unchanged state trace found that the FOW envelope and view keys are strict,
but every nested contact is an unchecked `deepcopy`. Commit restores the FOW
and fusion RNG mirrors, commits fusion, then creates or updates only serialized
view timestamps. It neither restores contacts nor removes target-runtime-only
views and contacts.

Production supplies the decisive alias invariant: a live
`ContactRecord.track` is the exact `Track` object owned by the corresponding
`IntelFusionEngine` side/track map. Phase 116 must cross-validate the duplicate
serialized nested-track state, then bind the restored contact to the staged
fusion object. An equal detached track would split later estimator and contact
behavior.

The initial design also identified three explicit boundaries rather than
claiming them implicitly: observer witnesses are same-update/bounded (the first
draft incorrectly assumed they could remain non-durable); the data-link
`share_cop()` helper has no production caller; and active deception/signature
state is not present in the current FOW checkpoint envelope. Roster-backed
ordinary contacts are the accepted Phase 116 target; an unprovable non-roster
contact must fail explicitly and the adjacent deception persistence gap must
be tracked separately.

The first checkpoint integration review found one contract contradiction:
Phase 115 deliberately rewrites restored FOW decisions as historical because
their supporting contacts disappear, but REM-029 requires immediate
whole-context equality after those contacts become durable. The first draft
proposed preserving consumability from contacts alone. Formal review rejected
that proxy because `FOW_OBSERVER_WITNESS` decisions require observer-local
same-interval evidence that `ContactRecord` does not contain. Format 116 will
therefore persist and strictly rehydrate the bounded current witness cache,
then cross-validate each consumable FOW decision/revalidation against the exact
witness, contact, fusion, roster, and loadout topology. The next normal engine
step replaces that cache and interval before movement or fire. Retaining the
old rewrite or accepting contacts as witness substitutes would conceal known
state loss and is rejected.

`$design-review` initially rejected the contact-only witness proxy and then
requested four fail-closed clarifications. The approved contract now requires
typed current-witness persistence, exact fusion-track alias reconstruction,
strict contact/lifecycle/covariance/chronology validation, complete RNG owner
and generator identity, atomic staged restore, explicit format-116
compatibility behavior, and pristine boundaries for omitted deception and
COP/data-link state. Its corruption matrix covers every witness field, sensor
provenance, production roster/attachment checks, targeting-decision
consumability, RNG mismatches, omitted-state violations, and retry atomicity.
The final `$design-review` verdict was `APPROVED`, with no remaining
architecture or contract blocker. This was design-only evidence, not
implementation or behavioral completion.

## Benchmark promotion gate

The checked-in 73 Easting entry was promoted to an ordinary version-4 paired
gate with clean reference commit `271ec49ceb508bdd050e2d5c3072ac91456cca7c`.
The promoted reference input and semantic envelope exactly equal the prior
transition candidate. Modern reference revisions now execute through
`SimulationRuntimeFactory`; the historical adapter remains restricted to its
exact legacy commit `0460ac70be86784bcc6e359ae4202f4bcb938c60`.
The active gate necessarily sets `transition_contract: null`; the complete
Phase 115 transition contract remains immutable in commit `271ec49` and its
external artifacts above. Neither is rewritten or counted as paired timing
evidence.

Before any FOW production edit, the focused policy profile passed:

```text
.venv/bin/python scripts/run_pytest_partition.py benchmark-policy \
  --manifest /tmp/sw-phase116-benchmark-policy-manifest.json \
  --junit /tmp/sw-phase116-benchmark-policy-junit.xml \
  --forbid-skips --timeout-seconds 600
# 87 collected; 87 passed; 0 failed; 0 errors; 0 skipped; 0 warnings
# elapsed: 21.58 s
```

The documentation/benchmark-only dirty candidate then passed the real
same-host ordinary gate:

```text
.venv/bin/python scripts/run_paired_benchmark.py \
  --scenario 73_easting \
  --artifact /tmp/sw-phase116-73-promotion-preproduction.json \
  --allow-dirty-candidate --worker-timeout-seconds 300
# 73_easting: pass;
# artifact_sha256=164a9d088cb4441c1e644c4fc67be5a56af160c060970c0e254323155b5146a6
```

The policy used one warm-up per revision, three timed `AB/BA/AB` pairs,
`SimulationEngine.run`, a maximum median slowdown ratio of `1.20`, and a
maximum relative sample range of `0.20`. Reference/candidate warm-ups were
`2.9332764390` / `2.7601974000` seconds. Pair durations (reference,
candidate) were `(2.7095580250, 2.7137306740)`, `(2.7146097350,
2.7122247760)`, and `(2.7506838190, 2.7327838831)` seconds. Ratios were
`1.0015399740`, `0.9991214358`, and `0.9934925505`; median ratio was
`0.9991214358`. Reference and candidate relative ranges were `0.0151497998`
and `0.0075759570`. The decision was `pass`: paired timing and dispersion
satisfied policy.

Every run used commit `271ec49`, runtime-input fingerprint
`3ef1e72ff1ebdb099a6e89cc6917540f49d774593816c439bfe9e96d6d87f879`,
scenario hash `328467cd1f200cf2f0157da917ab20b9e9bbc43fb7ee985f5d4472d2df3cd3e5`,
lock hash `bbc6b45cfc270d08baa09d3d568a6b84d0f936a6ee9c874cb49c9d8813c5ad39`,
and the declared semantic envelope: 71 units, 360 ticks / 1,800 seconds,
blue `time_expired` win, active counts blue 21/red 50, one event with digest
`2784db62737dac1df07bb13e64cadb9b6b6f0d3e48cee291efcfc0d51cb8e798`,
and roster/loadout digest
`1344d0fdffe8cf42cd5329a4cbc808398a449f47c14c95fb17807f671f3a32a2`.
There were no errors or warnings.

This local timing result is explicitly contention-qualified at the user's
direction: it ran while other work could share the machine. The artifact
records the available hardware as an AMD Ryzen AI MAX+ 395, 16 physical / 32
logical cores, and 67,187,146,752 bytes of RAM. The wide margin still passed;
the required post-commit clean final-tree and hosted gates remain pending.

A first final-dirty-tree attempt was also run while four long production
scenario workers were active:

```text
UV_CACHE_DIR=/tmp/sw-phase116-final-benchmark-uv-cache uv run --no-sync python \
  scripts/run_paired_benchmark.py --scenario 73_easting \
  --artifact /tmp/sw-phase116-73-easting-final-precommit.json \
  --allow-dirty-candidate --worker-timeout-seconds 300
# status=inconclusive; exit 1; errors=[]
# artifact_sha256=fcaf8146eec6bdd3096df914d95faab7e9dbd255ca18cdf74aa884191359f314
```

Reference/candidate warm-ups were 6.5090798410 / 8.7965686030 seconds.
Pair durations were `(9.5441235220, 11.0220585230)`, `(6.6674290570,
6.2263840530)`, and `(9.6030074350, 11.7326970830)` seconds; ratios were
`1.1548528786`, `0.9338508141`, and `1.2217731958`, with median
`1.1548528786`. The reference/candidate relative ranges were
`0.3075796715` / `0.4995721097`, both above the declared `0.20` dispersion
limit. Every reference/candidate semantic envelope and runtime-input
fingerprint remained exact. At the owner's direction this is retained as an
explicit contention-qualified, semantically clean result, not relabeled a
performance pass.

A second post-review run used the repaired production tree after the long
scenario workers had released their processes:

```text
.venv/bin/python scripts/run_paired_benchmark.py \
  --scenario 73_easting \
  --artifact /tmp/sw-phase116-73-easting-postreview-prestatus.json \
  --allow-dirty-candidate --worker-timeout-seconds 300
# status=inconclusive; exit 1; errors=[]
# artifact_sha256=fe80753f603bbe54cdc3070ac6eb37aafb8d88d88083071d08f70ec59aaa2723
# file_sha256=733303ade37fc0016497dcff8efa37a46d3f9f224038e7a3e936c4f49636950f
```

Reference/candidate warm-ups were `7.6959104140` / `5.9719250920` seconds.
Pair durations were `(9.3884463500, 7.0794758980)`, `(5.5280210930,
10.1357085720)`, and `(6.6611829210, 7.8443723520)` seconds; ratios were
`0.7540625609`, `1.8335148151`, and `1.1776245218`, with median
`1.1776245218`. The reference/candidate relative ranges were
`0.5795404965` / `0.3896083124`, again above the declared `0.20` dispersion
limit. All three semantic envelopes remained exact and `errors` remained
empty. The owner explicitly accepted the contended result as qualified
evidence until the machine is wholly free; it is therefore recorded as an
inconclusive timing sample, not a performance pass. The pre-production
ordinary-pair promotion remains the passing timing gate, and hosted post-push
execution remains the independent final control.

## Baseline and production red evidence

After the design and promoted benchmark gates, the unchanged production path
was built from the existing three-side Phase 115 scenario through
`PreparedScenario.build(..., strict_mode=True, record_events=True)`. All three
sides were configured defensive so movement could not erase the geometry;
runtime weapon ammunition was exhausted so battles remained live without
casualty termination. With seed `91115`, the red observer facing south, and
three real `RuntimeSession.step()` calls, the checkpoint at tick 3 / 15 seconds
contained four CONFIRMED ordinary contacts, four current observer witnesses,
and 397,659 bytes.

A fresh compatible runtime with different seed `116999` accepted that
checkpoint but restored zero ordinary contacts and zero witnesses. Immediate
checkpoint bytes and tactical-targeting state differed. The source exposed
these four privileged side/target/track associations:

```text
blue  -> red_iron_duke_bb_0000   -> fow-track-0001
green -> red_iron_duke_bb_0000   -> fow-track-0001
red   -> blue_iron_duke_bb_0000  -> fow-track-0001
red   -> green_iron_duke_bb_0000 -> fow-track-0002
```

The restored runtime's same production exposure call instead raised
`ValueError: targeting decision target is absent from the side world view`.
One further real step retained the four original source track IDs, while the
broken restore allocated blue/green `fow-track-0002` and red
`fow-track-0003`/`0004`; whole checkpoints remained unequal. This is behavioral
red evidence: the missing contact association changes the production fusion
update and public targeting exposure, rather than merely omitting a serialized
key. The reproducer completed in 2.2 seconds with no warnings.

## Implementation

Format 116 advances the engine version and gives `FogOfWarManager` one strict
runtime-owned checkpoint boundary. Its exact envelope is
`world_views/current_detection_witnesses/rng_state/intel_fusion`. World views,
contacts, nested contact/track information, current observer witnesses, and
fusion state serialize canonically. Capture validates that every live
`ContactRecord.track` is the exact side-local fusion-owned object; a detached
but state-equal track is rejected.

Staging now validates the complete envelope before mutation: exact keys and
container types; declared/hostile roster sides; contact IDs and canonical
`fow-track-NNNN` identities; contact level/classification; finite vectors,
positive-semidefinite covariance, lifecycle counters/status, and chronology;
nonempty reporting-sensor attachment provenance; every witness field and exact
current targeting-decision match; exact greatest-issued FOW counters; and
agreement among the context, detection, FOW, fusion, estimator,
identification, deception, and authoritative DETECTION RNG owners. Replacement
semantics remove target-runtime-only views, contacts, and witness sides while
retaining explicitly allocated empty views.

The staged publication plan is typed, exact-owner-bound, content-fingerprinted,
and independently bound to its raw runtime type/shape/alias graph. Its public
properties return defensive copies. Commit rejects a subclassed, foreign, or
mutated plan, deep-copies the view/witness/RNG/fusion publication as one alias-
preserving composite, and verifies both fingerprints again against that exact
publication copy before publishing fusion, contact-to-track identity, RNG
state, and witnesses. This prevents equal serialized values from hiding
list/tuple changes, enum-to-integer substitutions, NumPy dtype/shape changes,
detached tracks, or receipt-ledger alias loss. Rejected capture, staging, or
commit leaves clock, RNG, fusion, views, witnesses, targeting, events, and
recorder state unchanged and a valid retry succeeds.

`SimulationContext` constructs one typed sensor-binding projection from the
authoritative runtime loadouts and cross-validates every retained consumable
FOW decision, including a stale retained interval, against its exact contact,
fusion track, witness, source index, sensor/model role, and logical epoch. The
production restore path rejects a missing or detached detection/FOW owner or
RNG generator before commit. `TacticalTargetingRuntime` preserves exact
current-interval consumability for format 116 instead of applying Phase 115's
historical/non-consumable rewrite. FOW enablement is bound to the effective
calibration: disabled runtimes reject actual ordinary state but permit public
empty views and non-FOW Space tracks. Dynamic unit registration may invalidate
the targeting interval while durable contacts/witnesses remain; that supported
between-interval topology checkpoints and continues exactly.

Compatibility is fail-closed. Explicit format 115 and every other explicit
non-current version reject. Bounded versionless two- and three-key legacy FOW
state can retain only its proven empty topology and pristine target fusion;
nonempty contacts or witnesses cannot acquire format-116 meaning. Capture and
restore also reject omitted non-pristine active/inactive deception state
(REM-046 / Phase 133) and custom/populated COP/data-link state (REM-036) rather
than silently discarding either owner. Versionless fusion also rejects any FOW
track/counter history, including LOST-only history, before publication.

The Phase 116 production diff is limited to the FOW owner, context restore
wiring, targeting compatibility, and engine version. Benchmark changes promote
73 Easting from its Phase 115 non-timing handoff to the ordinary version-4
paired policy. New unit and integration modules contain 210 Phase 116 nodes;
existing version-oracle fixtures were advanced to the exact format-116 policy.

| Capability stage | Production evidence | Result |
|---|---|---|
| Declared | strict typed format-116 envelope, restore plan, sensor bindings, compatibility and rejection contract | Yes |
| Loaded | `PreparedScenario.build()` constructs real detection/FOW/fusion owners and catalog loadouts | Yes |
| Wired | context stages FOW against roster, clock, targeting, detection, fusion, loadouts, and `RNGManager` before publication | Yes |
| Enabled | mandatory current-format behavior plus an explicit FOW-disabled control | Yes |
| Exercised | four nonempty ordinary contacts and four observer witnesses cross fresh and in-place restore | Yes |
| Outcome-affecting | the restored current contact authorizes the real shared movement/engagement decision; the unchanged red cannot expose or consume it | Yes |
| Persisted/exposed | immediate and continued whole-checkpoint bytes, fusion alias, targeting state, privileged/side-safe exposure, recorder, and events agree | Yes |

## Focused validation

The final Phase 116 modules passed together after the independent production
review fixes:

```text
UV_CACHE_DIR=/tmp/sw-phase116-uv-cache uv run --no-sync pytest -q \
  tests/unit/test_phase116_fow_contact_state.py \
  tests/integration/test_phase116_fow_contact_checkpoint.py
# 210 passed in 91.97s; 0 failed/errors/skipped/warnings
```

The 183 unit nodes cover exact envelopes, fresh/in-place replacement, fusion
object identity, owner/content/structure-fingerprint plan integrity, canonical
order, every contact/witness scalar and topology family,
covariance/lifecycle/chronology,
reporting-sensor provenance, RNG mirrors/owners, bounded legacy shapes, and
REM-036/REM-046 rejection. The 27 production integration nodes use
factory-built `RuntimeSession` instances and prove:

- four CONFIRMED contacts and four exact current witnesses restore immediately
  into a different-seed fresh runtime with identical targeting/exposure and
  byte-identical whole checkpoint;
- a normal next step refreshes the same four contact associations and remains
  checkpoint-identical;
- the shared targeting decision holds the real unit for
  `ENGINE_WEAPON_STANDOFF`, revalidates, and reaches the ordinary engagement
  consumer after restore;
- uninterrupted/restored branches remain exact at 20 seconds, COASTING at
  320/325 seconds, LOST/removed at 620/625 seconds, and redetected at 630
  seconds with never-reused track ordinals, matching event order and recorder
  state;
- FOW-disabled, current-owner/RNG identity, missing-owner, versionless,
  state-equal detached-track, non-pristine deception/COP, and atomic valid-
  retry controls all behave as declared;
- disabled Space ISR retains non-FOW imagery tracks/receipts and explicitly
  empty ordinary views, while disabled ordinary-state injection rejects; and
- FOW-enabled dynamic registration preserves contacts/witnesses across the
  intentionally unprepared targeting boundary, then restores and continues
  byte-exactly.

Independent simplify/conventions review found and drove fixes for a stale
retained interval without its witness, a detached internal RNG child, a missing
current owner, a target-only legacy fusion leak, a detached-equal live contact
alias, and a mutable/forgeable restore plan. After those repairs, the exact
restore-plan/capture selection passed 8 nodes with 167 deselected in 0.49s; the
two production integration witnesses passed in 5.49s; and the owner-identity
matrix passed 8 nodes in 20.82s. The final `$simplify` verdict was
**READY AFTER IN-SCOPE FIXES** with no residual finding, and
`$validate-conventions` returned **CLEAN**.

The final independent production review then reproduced six additional
failures rather than accepting value-equal or no-crash evidence:

- disabled configuration accepted injected enabled contacts, and enabled
  capture could omit its live FOW owner;
- a coasting contact could retain an empty/unknown reporting-sensor list;
- an ahead FOW counter changed the next public ordinal;
- versionless LOST FOW history could reach a late post-publication rejection;
- the value-only plan digest erased behavior-affecting container, enum, array,
  model, and alias types; and
- dynamic registration and disabled Space ISR empty-view inspection hit two
  overbroad context guards after otherwise valid production work.

The recorded red/green selections were:

```text
.venv/bin/pytest -q \
  tests/unit/test_phase116_fow_contact_state.py::test_mutated_restore_plan_rejects_without_mutation_and_allows_retry
# red: 4 failed, 6 passed in 0.97s
# green with defensive-copy/foreign-plan controls: 12 passed in 0.73s

.venv/bin/pytest -q \
  tests/integration/test_phase116_fow_contact_checkpoint.py::test_fow_contacts_survive_dynamic_registration_and_restore
# red: 1 failed in 3.39s; late ValueError after registration publication
# green: 1 passed in 3.01s

.venv/bin/pytest -q \
  tests/integration/test_phase112_space_isr_integrity.py::test_long_delay_delivery_is_owner_scoped_and_checkpoint_exact
# red: 1 failed in 4.63s after public empty-view allocation

.venv/bin/pytest -q \
  tests/integration/test_phase116_fow_contact_checkpoint.py::test_fow_disabled_explicit_empty_views_restore_exactly \
  tests/integration/test_phase112_space_isr_integrity.py::test_long_delay_delivery_is_owner_scoped_and_checkpoint_exact
# green: 2 passed in 11.58s
```

The disabled-state/missing-owner red was three failures and its exact repaired
selection passed 3/3 in 5.36s. The versionless LOST-history red failed 2/2 and
the repaired selection passed 2/2 in 3.77s. The final production-corruption
loop, coasting provenance lifecycle, ahead-counter unit case, and disabled
injection controls all pass in the 210-node module run. The independent final
verdict was **no remaining blocker** and **DETERMINISTIC**; it was not used as
a substitute for the fresh broad, documentation, or postmortem gates.

## Conditional reviews and broader validation

### Determinism, conventions, data, and scenario gates

`$audit-determinism` returned **DETERMINISTIC** with no finding. Its fresh
module command was:

```text
UV_CACHE_DIR=/tmp/sw-phase116-uv-cache uv run --no-sync pytest -q \
  tests/unit/test_phase116_fow_contact_state.py \
  tests/integration/test_phase116_fow_contact_checkpoint.py
# 210 passed in 91.97s; 0 failed/errors/skipped/warnings
```

The final independent parallel-factory/RNG/replay selection passed 23 nodes in
48.39s:

```text
UV_CACHE_DIR=/tmp/sw-phase116-audit-final-uv-cache uv run --no-sync pytest -q \
  tests/integration/test_phase115_targeting_controls.py::test_three_side_parallel_factory_interval_repeats_exactly \
  tests/integration/test_phase115_targeting_controls.py::test_overlapping_fow_pictures_consume_one_detection_draw \
  tests/unit/test_phase115_fow_witness.py::test_side_local_rng_owns_detection_and_identification_draws \
  tests/unit/test_phase115_fow_witness.py::test_witness_emission_consumes_no_second_detection_draw \
  tests/unit/test_phase115_fow_witness.py::test_parallel_side_updates_publish_canonical_witness_order \
  tests/unit/test_phase89_parallel_detection.py::TestRNGStreamForking \
  tests/unit/test_rng.py::TestDeterminism \
  tests/integration/test_phase116_fow_contact_checkpoint.py::test_nonempty_current_fow_checkpoint_restores_exactly_in_fresh_runtime \
  tests/integration/test_phase116_fow_contact_checkpoint.py::test_contacts_continue_through_coast_loss_redetection_and_events \
  tests/integration/test_phase116_fow_contact_checkpoint.py::test_factory_runtime_rejects_detached_fow_owner_and_rng_identity \
  tests/integration/test_phase116_fow_contact_checkpoint.py::test_fow_disabled_runtime_stays_empty_and_uses_local_observations \
  tests/integration/test_phase116_fow_contact_checkpoint.py::test_fow_contacts_survive_dynamic_registration_and_restore
# 23 passed in 48.39s
```

The final disabled empty-view and Phase 112 long-delay Space ISR controls
passed together, including eight typed non-FOW receipts and tracks through the
structure-bound restore plan:

```text
UV_CACHE_DIR=/tmp/sw-phase116-audit-final-uv-cache uv run --no-sync pytest -q \
  tests/integration/test_phase116_fow_contact_checkpoint.py::test_fow_disabled_explicit_empty_views_restore_exactly \
  tests/integration/test_phase112_space_isr_integrity.py::test_long_delay_delivery_is_owner_scoped_and_checkpoint_exact
# 2 passed in 11.58s
```

The disabled production, empty-view, injected-ordinary-state, and empty-fusion
selection passed 4/4 separately in 9.31s.

Two fresh
seed-91116 factory sessions remained whole-checkpoint and recorder-state exact
after every one of 12 real steps: tick 12 / 60 seconds, a 500,458-byte
checkpoint, one ordered event, and blue/green/red contact counts 1/1/2. Adding
97 COMBAT draws did not change detection/FOW/targeting or any non-COMBAT stream;
adding 97 DETECTION draws did not change COMBAT. Separate
`PYTHONHASHSEED=1` and `8675309` processes produced the same 500,286-byte
12-step checkpoint SHA-256:

```text
0da5eaba8b334148d0252a5b560d202cf8f21bc1c54c50627efd68374c3df16f
```

`$validate-conventions` returned **CLEAN** after the fixes listed under focused
validation. Exact runtime owner/generator identity, canonical side/contact /
witness order, staged replacement, enum/type discipline, coordinates, and
public/private exposure boundaries all matched repository conventions.

The data gate changed no YAML or catalog definition but revalidated the loadout
and sensor topology consumed by the new authoritative projection:

```text
UV_CACHE_DIR=/tmp/sw-phase116-uv-cache uv run --no-sync python \
scripts/validate_scenario_data.py
# 184 unit YAML files; 442/442 authored catalog keys covered;
# 8,388/8,388 initial units loaded; 70 override groups expanded to
# 1,128/1,128 units and 1,131/1,131 field applications; 11 constellation,
# 3 ASAT, and 52 scenario definitions checked; 0 errors; 0 warnings;
# 1 explicit intentionally-sensorless classification

UV_CACHE_DIR=/tmp/sw-phase116-uv-cache uv run --no-sync pytest -q \
  tests/validation/test_phase_30_scenarios.py::TestScenarioFullLoad
# 52 passed in 44.72s
```

The intentionally sensorless entry is `modern/civilian_noncombatant`. The
first bare `uv run` attempt exited 2 before Python because the home UV cache was
read-only; the displayed `/tmp`-cache command is the actual successful gate.

The all-scenario evaluator was launched through the production factory for all
46 discovered scenarios with seed 42:

```text
UV_CACHE_DIR=/tmp/sw-phase116-uv-cache uv run --no-sync python \
  scripts/evaluate_scenarios.py \
  --output /tmp/sw-phase116-all-scenarios-42-preclose.json \
  --no-details --seed 42
```

The long command attempted all 46 scenarios. Forty-five completed, while the
last `space_isr_gap` correctly failed its source-identity guard because this
shared dirty worktree changed between prepare and build during documentation
work. After writes paused, the exact isolated rerun completed in 3.0s:

```text
UV_CACHE_DIR=/tmp/sw-phase116-uv-cache uv run --no-sync python \
  scripts/evaluate_scenarios.py --scenario space_isr_gap \
  --output /tmp/sw-phase116-space-isr-gap-42-preclose-rerun.json \
  --no-details --seed 42
# exit 0; draw/time_expired; 360 ticks / 21,600 logical seconds;
# 0 casualties; 0 engagements; 0/12 moved;
# ZERO_ENGAGEMENTS + NO_MOVEMENT
```

The composed result is 46/46 successful with zero semantic errors. Thirty-nine
scenarios have no issue flag. Seven retain 12 declared current-regression
issues: `normandy_bocage` (zero casualties/engagements),
`calibration_arctic` (red centroid collapse), `falklands_campaign` (20,000
ticks and zero casualties/engagements), `falklands_naval` (zero
casualties/engagements), `ins_hanit_2006` (four engagements without damage),
`space_isr_gap` (zero engagements/no movement), and
`time_on_target_validation` (no movement). Eight operational fuel-exhaustion
logs for Falklands Campaign's red Super Etendards are separate from those
evaluator issue flags. The six explicit evaluator exclusions were
`benchmark_battalion`, `benchmark_brigade`, `test_campaign`,
`test_campaign_logistics`, `test_campaign_multi`, and
`test_campaign_reinforce`.

The originally declared comparison artifact,
`/tmp/sw-phase115-all-scenarios-42-final.json` (SHA-256
`ecdb43ccbdd94f0236ea4f93327a2bcc568bd9e248a78b6935a3b783a91faf04`),
proved stale only for INS Hanit: it records zero engagements, while a clean
detached `271ec49ceb508bdd050e2d5c3072ac91456cca7c` reproduction and current both
record blue `time_expired`, 1,440 ticks / 7,200 seconds, zero casualties, four
C-802 engagements/fires, and 525 events. After deleting only
`duration_wall_s` and absolute `scenario_path`, the clean/current normalized
artifacts are byte-identical (SHA-256 `cec48cb...2607c`). The stale artifact
receives no regression credit for that row.

The clean detached worktree was verified clean at exactly `271ec49`. Its
parallel evaluator produced 45 records; all 45 match current exactly under the
same two-field normalization. Clean-start Khafji remained contention-pending,
while current Khafji exactly matches the stored row (normalized SHA-256
`d44481bc...1417`): blue `morale_collapsed`, 680 ticks / 3,400 logical seconds,
99 casualties, 289 engagements, 238/241 moved, and no issues. The qualified
scenario verdict is therefore **UNCHANGED** for 45/45 available clean-start
comparisons and **UNCHANGED against the stored artifact** for Khafji; no
Phase 116 regression or stall was found, and no baseline was promoted.

Wall time is explicitly contention-qualified: the composed per-scenario total
was 9,303.81s, dominated by Golan Heights at 1,829.17s and Khafji at 6,297.03s.

### Static and evidence-quality gates

The complete Python lint command, including the remote-lint surface reported at
the original remediation handoff, is green:

```text
UV_CACHE_DIR=/tmp/sw-phase116-uv-cache uv run --no-sync ruff check \
  stochastic_warfare/ api/ tests/ scripts/
# All checks passed!

git diff --check 271ec49ceb508bdd050e2d5c3072ac91456cca7c
# exit 0

UV_CACHE_DIR=/tmp/sw-phase116-final-docs-uv-cache uv run --no-sync python \
  scripts/validate_docs_links.py
# {"invalid_diagnostic": true, "invalid_exit_code": 1, "valid_exit_code": 0}

UV_CACHE_DIR=/tmp/sw-phase116-final-docs-uv-cache uv run --no-sync \
  mkdocs build --strict --site-dir /tmp/sw-phase116-final-docs-site
# exit 0; Documentation built in 6.02 seconds
```

The strict build emitted only the Material/MkDocs-2.0 advisory and the three
intentional unnav pages listed above. It reported no navigation, link,
fragment, or build error.

The first authoritative standard shard 3 honestly failed one evidence-ledger
drift node: 2,984 passed / 1 failed in 330.16s. The ledger validator named 134
new/renamed Phase 116 nodes and four stale format-115 Phase 114 IDs. Each node
was reviewed against 12 behavioral contracts; 129 negative cases are explicit
helper assertions and five are lifecycle helper assertions. Four Phase 114
oracle IDs were renamed to format 116, and the hosted benchmark disposition was
updated from transition-only to paired evidence. Fresh validation then passed:

```text
UV_CACHE_DIR=/tmp/sw-phase116-uv-cache uv run --no-sync python \
  scripts/validate_test_evidence.py
# no_direct=228; reviewed_behavioral=88; weak=1006; structural=918; exit 0

UV_CACHE_DIR=/tmp/sw-phase116-uv-cache uv run --no-sync pytest -q \
  tests/validation/test_phase112_evidence_ledgers.py
# 2 passed in 40.27s
```

Rerunning the complete unchanged shard 3 then passed 2,985/2,985 in 350.85s.
This records the red and repair instead of counting the initial run as green.

```text
UV_CACHE_DIR=/tmp/sw-phase116-uv-cache uv run --no-sync python \
  scripts/run_pytest_partition.py standard \
  --manifest /tmp/sw-phase116-standard-3-rerun/manifest.json \
  --junit /tmp/sw-phase116-standard-3-rerun/junit.xml \
  --shard-index 3 --shard-count 4 --forbid-skips --timeout-seconds 900
# 2,985 passed in 350.85s; 0 failures/errors/skips/warnings
```

### Audited broad partitions

The final collection audit reports one exact, pairwise-disjoint six-partition
union with no collection warnings:

```text
UV_CACHE_DIR=/tmp/sw-phase116-uv-cache uv run --no-sync python \
  scripts/validate_test_partitions.py \
  --output /tmp/sw-phase116-partition-audit-postreview.json
# exact union: true; pairwise disjoint: true; collection warnings: 0
# 12,459 = standard 11,953 + slow-only 110 + benchmark-only 87 +
#          slow-benchmark 5 + API 263 + E2E 41
```

The final authoritative standard partition ran after every independent-review
fix as four concurrent deterministic module-affine shards of 2,989 / 2,988 /
2,988 / 2,988 nodes. The runner commands used partition-specific manifest /
JUnit paths and `--forbid-skips`; the standard shape was:

```text
for phase116_shard in 0 1 2 3; do
  UV_CACHE_DIR=/tmp/sw-phase116-uv-cache uv run --no-sync python \
    scripts/run_pytest_partition.py standard \
    --manifest "/tmp/sw-phase116-standard-final-${phase116_shard}/manifest.json" \
    --junit "/tmp/sw-phase116-standard-final-${phase116_shard}/junit.xml" \
    --shard-index "${phase116_shard}" --shard-count 4 \
    --forbid-skips --timeout-seconds 900
done
```

Final shard results were 2,989 in 392.54s with zero warnings; 2,988 in 378.84s
with one known empty-chart-legend warning; 2,988 in 497.42s with zero warnings;
and 2,988 in 392.80s with four unrendered-matplotlib-animation warnings plus
one `datetime.utcnow()` deprecation. The accepted total is
**11,953/11,953 passed**, with zero
failures, errors, skips, xfails, or xpasses and exactly six classified unrelated
warnings.

Other complete partitions/profiles are:

| Selection | Exact result |
|---|---|
| benchmark-only shard 0 | 77 passed in 7.37s; 0 warnings/skips |
| benchmark-only shard 1 | 7 passed in 0.79s; 0 warnings/skips |
| benchmark-only shard 2 | 3 passed in 0.14s; 0 warnings/skips |
| slow-benchmark | 5 passed in 33.68s; 0 warnings/skips |
| terrain dependency profile | 97 passed in 4.36s; 0 warnings/skips |
| benchmark-policy final | 87 passed in 56.56s; 0 warnings/skips |

```text
UV_CACHE_DIR=/tmp/sw-phase116-uv-cache uv run --no-sync python \
  scripts/run_pytest_partition.py benchmark-policy \
  --manifest /tmp/sw-phase116-benchmark-policy-final/manifest.json \
  --junit /tmp/sw-phase116-benchmark-policy-final/junit.xml \
  --forbid-skips --timeout-seconds 600
# 87 passed in 56.56s; 0 failures/errors/skips/warnings
```

Those results used the same runner with exact partition names, output paths,
and shard identities:

```text
# benchmark-only: shard indexes 0, 1, 2 with --shard-count 3
UV_CACHE_DIR=/tmp/sw-phase116-uv-cache uv run --no-sync python \
  scripts/run_pytest_partition.py benchmark-only \
  --manifest /tmp/sw-phase116-benchmark-0/manifest.json \
  --junit /tmp/sw-phase116-benchmark-0/junit.xml \
  --shard-index 0 --shard-count 3 --forbid-skips --timeout-seconds 900

UV_CACHE_DIR=/tmp/sw-phase116-uv-cache uv run --no-sync python \
  scripts/run_pytest_partition.py slow-benchmark \
  --manifest /tmp/sw-phase116-slow-benchmark/manifest.json \
  --junit /tmp/sw-phase116-slow-benchmark/junit.xml \
  --forbid-skips --timeout-seconds 900

UV_CACHE_DIR=/tmp/sw-phase116-uv-cache uv run --no-sync python \
  scripts/run_pytest_partition.py terrain \
  --manifest /tmp/sw-phase116-terrain/manifest.json \
  --junit /tmp/sw-phase116-terrain/junit.xml \
  --forbid-skips --timeout-seconds 900
```

API and E2E each collected their exact warning-free partition (263 and 41
nodes) but reached the user-approved 900-second operational containment limit
before a pytest summary or JUnit file. Both result artifacts report exit 124 /
`status=timeout`. They are explicitly **qualified timeouts**, not passes or
zero-failure evidence; hosted post-push runs remain the independent control.
Concurrent-run memory remained safe: the host reported 62 GiB total and 44 GiB
available with only about 6.3 MiB of swap in use; load averages around 18--21
reflect CPU contention, not memory exhaustion.

Their exact commands differed only by partition/output directory:

```text
UV_CACHE_DIR=/tmp/sw-phase116-uv-cache uv run --no-sync python \
  scripts/run_pytest_partition.py api \
  --manifest /tmp/sw-phase116-api/manifest.json \
  --junit /tmp/sw-phase116-api/junit.xml \
  --forbid-skips --timeout-seconds 900

UV_CACHE_DIR=/tmp/sw-phase116-uv-cache uv run --no-sync python \
  scripts/run_pytest_partition.py e2e \
  --manifest /tmp/sw-phase116-e2e/manifest.json \
  --junit /tmp/sw-phase116-e2e/junit.xml \
  --forbid-skips --timeout-seconds 900
```

The four slow-only shards were launched with 2,700-second containment limits.
Shard 1 passed 28/28 in 351.55s with zero warnings. Shard 2 completed 26/27 in
2,070.69s with one known failure: Debecka's legacy envelope demands at least
8/10 blue wins while the unchanged Phase 115 production result remains 4/10.
That result is the declared REM-030 / Phase 117 historical-outcome red; it is
not a Phase 116 regression and is not called a pass. Shards 0 and 3 both
reached their exact 2,700-second limit with exit 124 before a JUnit file or
pytest summary. Shard 0 had selected 28 nodes from Falklands, historical-
accuracy, and Khafji modules; shard 3 had selected 27 integration/performance /
73 Easting/Bint Jbeil/campaign-Monte-Carlo nodes. Their pass/fail/error/skip
counts are unavailable rather than zero. The accepted slow result is therefore
28 passing nodes, 26 additional passing nodes plus the known Debecka failure,
and two qualified timeouts; no incomplete shard is labeled a pass.

```text
for phase116_shard in 0 1 2 3; do
  UV_CACHE_DIR=/tmp/sw-phase116-uv-cache uv run --no-sync python \
    scripts/run_pytest_partition.py slow-only \
    --manifest "/tmp/sw-phase116-slow-${phase116_shard}/manifest.json" \
    --junit "/tmp/sw-phase116-slow-${phase116_shard}/junit.xml" \
    --shard-index "${phase116_shard}" --shard-count 4 \
    --forbid-skips --timeout-seconds 2700
done
```

## Documentation and cross-document audit

`$update-docs` synchronized the format-116 contract with checkpoint, architecture,
project-structure, API, scenario, era, and historical supersession notes. Block
13, the devlog index, remediation backlog, public status pages, and maintained
provider context are routed together. Phase 116 also records rather than hides
two omitted-owner boundaries:

- REM-036 retains custom/populated COP/data-link topology; and
- new REM-046 / Phase 133 / Block 17 owns complete active/inactive deception
  signatures, lifecycle state, next-ID allocation, production scan wiring, and
  single-authority DETECTION RNG continuation.

The first strict documentation check after the behavioral-contract edits
passed:

```text
UV_CACHE_DIR=/tmp/sw-phase116-docs-preclose-uv-cache uv run --no-sync python \
  scripts/validate_docs_links.py
# {"invalid_diagnostic": true, "invalid_exit_code": 1, "valid_exit_code": 0}

UV_CACHE_DIR=/tmp/sw-phase116-docs-preclose-uv-cache uv run --no-sync \
  mkdocs build --strict --site-dir /tmp/sw-phase116-docs-preclose-site
# exit 0; Documentation built in 6.32 seconds
```

Strict MkDocs emitted only the Material/MkDocs-2.0 advisory and the same three
intentional unnav pages: `scenarios/calibration-template.md`,
`scenarios/depth-checklist-template.md`, and `scenarios/gap-audit.md`. It
reported no link, fragment, navigation, or build error.

`$cross-doc-audit` then checked the roadmap/devlog/status surfaces,
remediation traceability, contract/architecture, production evidence, exact
test inventories, scenario and benchmark qualifications, API/data claims,
navigation, links, provider context, and final hygiene. It found and repaired
two evidence-description defects: pre-closure pages still named already-run
scenario/documentation gates as pending, and the final standard command block
named the earlier shard paths instead of the green
`/tmp/sw-phase116-standard-final-{0,1,2,3}` artifacts. The corrected JUnits
reconcile to 2,989 / 2,988 / 2,988 / 2,988 tests with zero failures, errors, or
skips. Its independent focused rerun passed 210/210 nodes in 90.78s; link
validation passed; strict MkDocs passed in 6.51s with only the advisory and
three intentional unnav pages; and `git diff --check` passed. Final verdict:
**CLEAN**, with no cross-document blocker. Post-transition status and strict
checks are recorded below after the postmortem verdict.

## Postmortem

`$postmortem` reconstructed the contract from Block 13, REM-029, the accepted
specification, the production/test diff, the Phase 115 handoff, and the fresh
evidence above rather than relying on a completion label.

### Contract disposition

- Delivered: the clean Phase 115 endpoint is an ordinary version-4 paired
  reference; format 116 strictly restores complete roster-backed ordinary
  contacts, fusion-owned track aliases, bounded current witnesses, and the
  one authoritative DETECTION RNG topology through a typed context-owned
  boundary.
- Delivered: fresh and in-place replacement, current targeting consumability,
  later coast/loss/redetection, event/recorder continuation, dynamic roster
  registration, explicit empty views, disabled controls, bounded versionless
  compatibility, exact counter progression, and atomic corruption/retry all
  have production or owner-level behavioral proof.
- Changed from the first draft: contact-only restoration was rejected because
  it could not justify observer-specific current decisions. Format 116 instead
  persists the bounded current witness cache and rejects explicit format 115;
  it does not infer witnesses or migrate nonempty old state.
- Dropped or papered over: none. No stub, proxy state, log-only branch,
  swallowed new failure, unconditional success, or structural-only capability
  is counted as completion.
- Accepted non-goals: detection/identification mathematics, sensor covariance,
  prediction/association, custom COP/data-link wiring, active deception, and
  historical calibration remain unchanged. REM-036, REM-044, and REM-030 keep
  their existing owners; REM-046 / Phase 133 owns the newly surfaced complete
  deception checkpoint boundary.

### Capability and quality verdict

| Review | Verdict | Evidence |
|---|---|---|
| Scope | **On target** | The diff advances only the checkpoint/FOW/targeting boundary, promoted benchmark policy, tests, and truthful documentation needed by REM-029 |
| Quality | **High** | Exact schemas, typed owner-bound plans, dual value/structure fingerprints, fail-closed compatibility, canonical ordering, defensive publication, and no new TODO/FIXME/stub pattern |
| Integration | **Fully proven for REM-029** | Factory-built enabled and disabled sessions prove declared, loaded, wired, enabled, exercised, outcome-affecting, and persisted/exposed stages |
| Determinism | **Proven** | Exact 12-step same-seed checkpoints, hash-seed equality, stream-isolation controls, lifecycle continuation, and 23/23 final audit nodes |
| Data/API | **No schema change; applicable gates green** | 442/442 equipment keys, 52/52 full loads, zero data errors/warnings, unchanged REST contract |
| Documentation | **Clean** | Living/current and historical/supersession documents, navigation, REM-029/036/046 routing, strict build, link validation, and independent cross-document audit agree |

The 210-node Phase 116 suite, 11,953-node standard partition, five
slow-benchmark nodes, all 87 benchmark-policy nodes, data validation, scenario
comparison, determinism, conventions, Ruff, evidence-ledger, link, and strict
documentation checks are green as recorded above. The implementation has a
regression oracle for every fixed defect family, including production red
behavior, negative/disabled controls, stochastic continuation, exact aliases,
and valid retry after rejection.

### Qualified evidence and residual deficits

The postmortem does not turn incomplete broad work into green evidence. API
and E2E each timed out at 900 seconds after exact warning-free collection;
slow shards 0 and 3 timed out at 2,700 seconds; slow shard 2 retains the known
Debecka 4/10 REM-030 failure; Khafji's current result is exact against the
stored artifact while its clean-start rerun remained contention-pending; and
the two repaired-tree paired timing samples are semantically exact but
inconclusive on dispersion. The owner explicitly accepts those results as
contention-qualified until all cores are free. The passing pre-production
ordinary paired promotion remains timing evidence; the inconclusive samples
are not called passes. Hosted post-push partitions and benchmark execution are
the independent environment control.

REM-036 (custom/populated COP/data-link state) and REM-046 (complete active and
inactive deception/signature/lifecycle state) remain explicit unsupported
checkpoint boundaries. REM-030 owns the historical-outcome contract. These
are separately specified deficits with roadmap owners, not missing ordinary
roster-backed contact behavior and not grounds to reopen REM-029.

### Final verdict

**ACCEPTED.** Phase 116 meets its production, integrity, determinism,
documentation, and evidence obligations with the disclosed owner-approved
contention qualification. REM-029 may transition to closed. There is no
required pre-commit repair. The required next actions are the single coherent
Phase 116 commit, then the authorized push and hosted workflow inspection;
Phase 117 must not begin before that commit exists.

### Post-transition frozen-tree checks

After synchronizing every status surface to Phase 116 complete / REM-029
closed / Phase 117 next and unstarted, the final behavioral and inventory
freeze passed:

```text
UV_CACHE_DIR=/tmp/sw-phase116-final-freeze-uv-cache uv run --no-sync pytest -q \
  tests/unit/test_phase116_fow_contact_state.py \
  tests/integration/test_phase116_fow_contact_checkpoint.py
# 210 passed in 95.30s; 0 failed/errors/skipped/warnings

UV_CACHE_DIR=/tmp/sw-phase116-final-freeze-uv-cache uv run --no-sync python \
  scripts/validate_test_partitions.py \
  --output /tmp/sw-phase116-partition-audit-final-freeze.json
# exact union: true; pairwise disjoint: true; collection warnings: 0
# 12,459 = standard 11,953 + slow-only 110 + benchmark-only 87 +
#          slow-benchmark 5 + API 263 + E2E 41

UV_CACHE_DIR=/tmp/sw-phase116-final-freeze-uv-cache uv run --no-sync python \
  scripts/validate_test_evidence.py
# no_direct=228; reviewed_behavioral=88; weak=1006; structural=918; exit 0

UV_CACHE_DIR=/tmp/sw-phase116-final-freeze-uv-cache uv run --no-sync ruff check \
  stochastic_warfare/ api/ tests/ scripts/
# All checks passed!

git diff --check 271ec49ceb508bdd050e2d5c3072ac91456cca7c
# exit 0
```
