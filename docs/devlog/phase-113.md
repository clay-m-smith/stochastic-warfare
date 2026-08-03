# Phase 113 - Morale State Ownership

> **Phase 117 historical-claim supersession (2026-08-02):** This archived page
> preserves implementation history. Its historical-winner, outcome, casualty,
> duration, calibration, plausibility, envelope, and tolerance statements are
> not accepted historical validation. Any engine figures below are regression
> history only, not predictive evidence or calibration authority; the typed
> claim ledger and accepted production artifacts, if any, are authoritative.


**Status:** Complete

**Started:** 2026-07-31

**Completed:** 2026-08-01

## Why this phase exists

Phase 107 initializes `SimulationContext.morale_states` and
`MoraleStateMachine` consistently, but production then permits either to
change independently. Rally, melee, cascade, aggregation, dynamic registration,
and direct restore can therefore expose one value to battle/victory/API while
the next stochastic transition and machine checkpoint use another. Phase 113
owns REM-019 under the accepted durable contract in
[`morale-state-ownership.md`](../specs/morale-state-ownership.md).

## Start gate

Phase 112 passed `$postmortem`, was committed and pushed as
`2ff438ae732f359112a6bcf16a386557821bc75b`. After Phase 113 started, the user
reported a remote Python-lint failure. Once network access was restored,
`gh run view 30421215404 --log-failed` identified the exact failure at the
original `70e72f5a2b18aa0981d9b4313406b994ae9a5dd6` handoff: six Ruff `F601`
duplicate mapping keys and two `F541` placeholder-free f-strings. Those
findings were already removed in the intervening remediation phases; hosted
Lint run `30579052446` passed at the Phase 113 base commit, and the synchronized
base also passes repository-wide Ruff locally. Phase 113 still requires a fresh
local pass and its own post-push remote result rather than generalizing either
older run.

The Phase 113 synchronization gate was repeated before changes:

```text
git status --short --branch
# ## main...origin/main

git rev-parse HEAD
git rev-parse origin/main
# 2ff438ae732f359112a6bcf16a386557821bc75b
# 2ff438ae732f359112a6bcf16a386557821bc75b

git pull --ff-only origin main
# From https://github.com/clay-m-smith/stochastic-warfare
#  * branch            main       -> FETCH_HEAD
# Already up to date.
```

`CODEX.md`, `AGENTS.md`, Blocks 12 and 13, the complete ranked backlog and
detailed REM-019 entry, the Phase 112 start/remaining-deficit/postmortem
evidence, the checkpoint contract, architecture/public morale consumers, and
the applicable `$spec` and `$design-review` instructions were read before
implementation.

## Machine envelope

```text
nproc
# 32

lscpu | rg 'Model name|Socket|Core\(s\) per socket|Thread\(s\) per core|^CPU\(s\):'
# CPU(s): 32
# Model name: AMD RYZEN AI MAX+ 395 w/ Radeon 8060S
# Thread(s) per core: 2
# Core(s) per socket: 16
# Socket(s): 1

free -h
# Mem: 62 GiB total, 6.0 GiB used, 33 GiB free, 56 GiB available
# Swap: 7.8 GiB total, 6.0 MiB used

uv --version
# uv 0.11.11 (x86_64-unknown-linux-gnu)

uv run --no-sync python --version
# failed before Python startup because the sandboxed default UV cache under
# /home/csmith/.cache/uv is read-only

UV_CACHE_DIR=/tmp/sw-uv-cache uv run --no-sync python --version
# Python 3.12.10

UV_CACHE_DIR=/tmp/sw-uv-cache uv run --no-sync pytest --version
# pytest 9.0.2
```

The 32 logical CPUs and 56 GiB available memory are sufficient for independent
partition commands. Pytest itself remains serial because the repository does
not provide a validated parallel runner; suite accounting will not be weakened
to manufacture speed.

## Specification and design gate

`$spec` traced every production morale read/write and proposed one typed
runtime-owned boundary, a read-only context projection, strict logical-time
transitions, one RNG checkpoint authority, complete aggregation records, and a
version-113 single-owner checkpoint.

The first three independent design-only reviews did not accept that draft. Two
returned `NEEDS REVISION`; the third was only conditionally acceptable. Their
blocking findings were:

- no single atomic coordinator for store, `Unit.status`, rout, and synchronous
  event observation;
- mutable record escape and ambiguous store-versus-machine mutation ownership;
- contradictory negative-sentinel, cooldown, and insertion-order rules;
- incomplete aggregation archive, proxy-history, and checkpoint-topology
  semantics;
- an overbroad positive disaggregation claim conflicting with open REM-016;
- insufficiently exact forced-transition pairs, status precedence, event
  order, and subscriber-failure/RNG behavior; and
- a misleading ordinary-battle baseline claim even though that path currently
  mirrors a successful machine transition into the context map.

The revised contract responds by making `MoraleRuntime` the sole semantic
coordinator over a private immutable-record store and stateless stochastic
machine; using optional logical times and a generation guard; specifying exact
transition causes, status precedence, transaction/event order, and draw
behavior; making the store own complete suspended aggregate records; narrowing
positive disaggregation evidence to an empty-loadout base-unit fixture; and
classifying direct-machine divergence as a public-bypass red while separately
testing production battle's zero-time cooldown defect.

The first re-review still returned three `NEEDS REVISION` verdicts. It confirmed
that the original ownership, atomic observation, immutability, aggregation,
ordering, and REM-016 blockers were resolved, but identified four remaining
contract defects: pre-notification rollback did not rewind an already consumed
MORALE draw; normal Phase 112 records serialize an inert per-record cooldown of
`0.0`, not the effective config default; legacy records cannot reconstruct
prior no-change check history; and morale routing lacks the threat direction
and additional scatter draw required to create a `RoutState`. The second
revision now requires pre-event RNG rollback, validates and discards the
canonical legacy `0.0` mirror, defines a bounded new record-generation epoch
and fail-closed started continuous-time migration, and explicitly preserves
production's morale/status-only routing while removing an existing route on
rally or surrender. It also defines current `morale_runtime=null` topology for
empty minimal contexts and corrects repository identifiers. A second
independent re-review returned two `APPROVED` verdicts and one remaining
cascade-selection blocker. The contract was still not implementation or
completion evidence.

The final design pass added the remaining cascade transaction: each routing
source retains configured-side/unit order, candidates are evaluated by sorted
ID, exactly one MORALE draw is consumed per in-radius `SHAKEN`/`BROKEN`
candidate, applying selected transitions consumes no extra draw, and every
selected target for one source commits as a batch or rolls back with all draws
before notification. All three independent reviewers then returned
`APPROVED`. This accepts the implementation contract only; no behavioral or
completion claim follows from the review.

The trace also surfaced two adjacent state-integrity hazards that the design
must resolve or record explicitly:

- production morale checks currently omit `current_time_s` and `dt`, so the
  first transition records logical time zero and later checks can remain in
  cooldown indefinitely; and
- `RNGManager`, `MoraleStateMachine`, and `RoutEngine` serialize independent
  copies of the same injected MORALE generator, allowing one owner commit to
  overwrite another unless equality is validated or the mirrors are removed.

## Baseline and production red evidence

The accepted-design baseline was run before production implementation:

```text
UV_CACHE_DIR=/tmp/sw-uv-cache uv run --no-sync ruff check .
# All checks passed!

UV_CACHE_DIR=/tmp/sw-uv-cache uv run --no-sync pytest -q \
  tests/unit/test_morale_state.py \
  tests/unit/test_morale_rout.py \
  tests/unit/simulation/test_aggregation.py \
  tests/unit/test_phase85_aggregation.py \
  tests/unit/test_phase_107_scenario_wiring.py
# 158 passed in 24.62s
```

This also rechecks the Python-lint failure reported from the earlier remote
push: the current synchronized Phase 112 baseline has no Ruff finding.

The accepted five-defect red module was then run against unchanged production:

```text
UV_CACHE_DIR=/tmp/sw-uv-cache uv run --no-sync pytest -q \
  tests/integration/test_phase113_morale_ownership.py
# 5 failed in 5.56s
```

All five failures are behavioral and deterministic at seed 113:

1. a real first-wave reinforcement transitions to `SHAKEN` through the public
   machine while the public context projection remains `STEADY`;
2. a real cascade changes `blue_m1a2_0001` to context `ROUTED` while the
   machine remains `SHAKEN`, and fresh production restore rejects the stores'
   disagreement;
3. loaded aggregation creates roster/context proxy `agg_0000` while the
   machine retains the four red constituents, and fresh restore rejects those
   stale IDs;
4. all six Goose Green red machine records reach `ROUTED`, but production
   `morale_collapsed` victory remains false because it reads the stale context
   projection; and
5. after an ordinary `STEADY -> SHAKEN` check records time `0.0`, a second
   battle check at 31 seconds consumes no MORALE draw and stays blocked, while
   the explicit elapsed-time control consumes the next draw and returns
   `STEADY`.

Focused Ruff for the red module passed. No production implementation had begun
when these results were captured.

## Implementation

### One authoritative runtime

`MoraleRuntime` now owns a private `MoraleStateStore`, immutable
`MoraleStateRecord` values, the stateless transition selector, the shared
MORALE generator, and the coordinated rout engine. `SimulationContext` retains
one stable read-only `Mapping[str, MoraleState]` compatibility view. Initial
units and reinforcements use `MoraleRegistration`; no production consumer can
write an independent enum map.

The coordinator implements typed stochastic, rally, melee-rout, and
rout-cascade transactions. It validates complete state/status/rout plans before
draws or mutation, records logical check and transition times, increments a
generation on every admitted check, publishes only after the authoritative
record and status commit, rewinds state/status/rout/RNG on pre-notification
failure, and retains committed state while collecting subscriber failures.
`RNGManager` is the only checkpoint owner of the MORALE stream.

The production battle loop supplies elapsed scenario time, uses the same
runtime for ordinary transitions, rally, melee rout, and cascade, and reads the
stable projection for firing and victory. API map frames, campaign final state,
analytics events, aggregation, and checkpointing consume that same owner.

### Aggregation, registration, and restore integrity

The morale store suspends complete constituent records during aggregation and
creates the proxy from the canonical worst constituent record. An unchanged
proxy restores the archive exactly for the accepted base-unit boundary;
any state, time, or generation evolution rejects before disaggregation.
Prepare/commit boundaries now revalidate constituent/proxy/restored-unit IDs,
bindings, statuses, collisions, and archive topology before their first pop.
REM-016 still owns general subclass, attachment, and supply reconstruction.

Dynamic registration derives side morale and required statuses without
mutating caller-owned units during preflight. Status application occurs inside
the existing all-owner transaction and restores the rejected input objects on
late failure. Both commander preflight and commit-failure controls retain the
rejected objects, retry, and compare the final checkpoint with a no-failure
control.

`SimulationEngine` now writes checkpoint version 113 with one
`morale_runtime` envelope. Active immutable records and suspended archives are
staged together with exact roster/status/rout topology. Current restore
preserves runtime/store/view/generator identities; explicit versions other than
113 reject. The bounded versionless migration requires agreeing legacy stores
and RNG mirrors, validates the dead `0.0` cooldown mirror, rejects an already
started continuous-time history and an active legacy aggregate proxy, and
never resolves disagreement by precedence.

`RoutEngineStatePlan` no longer nests mutable `RoutState` instances. It carries
frozen scalar snapshots, rejects noncanonical or duplicate forged plans, builds
the complete replacement before mutating the live mapping, and preserves the
mapping and injected RNG identities. `RoutConfig` is now strict and immutable;
the battle loop uses its public accessor. The private store was removed from
the module export list.

### Melee and guerrilla semantics

A factory-built `ancient_medieval` runtime now proves a real pike engagement
through `RuntimeSession.run_to_completion()`. At seed 1, one tactical tick
emits one pike `EngagementEvent`, one 12-person `DamageEvent`, and one
`STEADY -> ROUTED` `MoraleStateChangeEvent` with cause `melee_rout`; the red
record is generation 1 at logical second 1 and the unit status is `ROUTING`.
The matched typed `WEAPONS_HOLD` variant emits none of those events and remains
`STEADY`/`ACTIVE`. Fresh restore and same-seed replay reproduce context,
recorder, and terminal result exactly. This production proof also exposed and
removed three melee `datetime.min` placeholders: engagement and damage events
now carry the authoritative tick timestamp.

The Phase 68 populated-area blend branch no longer writes the semantically
unrelated morale-owned `ROUTING` status. A positive value reaching the battle
guard raises `UnsupportedGuerrillaBlendError` before position, status, morale,
event, COMBAT-RNG, or MORALE-RNG mutation. That proof is a direct fail-closed
fault detector: the factory context exposes `population_manager`, while the
battle lookup lacks its density-query contract and cannot currently recognize
a populated area. The factory-loaded zero result retains deterministic physical
retreat. REM-032/Phase 119 owns the real lookup and typed concealment lifecycle.

The final ownership audit also reproduced the public
`RoutEngine.process_surrender()` bypass: it consumed MORALE RNG, removed a
route, and emitted `SurrenderEvent`/a synthetic POW count while leaving the
authoritative record `ROUTED` and the unit `ROUTING`. The helper now rejects
before every mutation. A matched runtime proof shows stochastic
`ROUTED -> SURRENDERED` commits record, status, route removal, and caused event
together. Captor provenance and the production prisoner/logistics lifecycle
remain explicitly queued as REM-033/Phase 120 rather than being fabricated.

### Benchmark contract extension

The benchmark policy is version 3. `BenchmarkWorkload` binds the named
workload and its exact typed calibration patch into the production-loaded input
fingerprint. Routine 73 Easting uses only the
`morale_neutral_control_plane` workload: all seven morale-pressure weights are
zero but all 2,130 admitted runtime checks, record updates, and MORALE draws
still execute. A default-versus-neutral test proves the patch is loaded and
outcome-affecting. The neutral name is an exact biconditional with
`73_easting`; an arbitrary future scenario cannot inherit it.

This is performance evidence for the control-plane workload only. Default
Phase 113 73 Easting separately produces 118 morale changes, two rallies, and
three routed blue units; the neutral workload is not evidence for default
morale or historical fidelity.

## Verification

### Additional production red and repair evidence

The final simplify pass found defects beyond the original five-red suite. They
were first reproduced without weakening the accepted contract:

```text
# Restore substitution and visualization API: 2 failed in 0.83 s
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync pytest -q \
  tests/unit/test_morale_runtime.py::TestRuntimeState::\
test_commit_revalidates_substituted_unit_before_mutation \
  tests/unit/test_morale_state.py::\
test_morale_visualization_uses_current_stateless_selector

# Reserved benchmark workload on an arbitrary scenario: 1 failed in 0.21 s
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync pytest -o addopts= -q \
  tests/benchmarks/test_benchmarks.py::TestPairedPolicy::\
test_morale_neutral_workload_rejects_every_non_73_scenario

# Mutable route plan, strict config, and stale aggregate transactions:
# 5 failed in 0.23 s
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync pytest -q \
  tests/unit/test_morale_rout.py::TestRoutConfig::\
test_is_strict_and_immutable \
  tests/unit/test_morale_rout.py::TestRoutEngineState::\
test_staged_routes_are_immutable_and_detached \
  tests/unit/test_morale_rout.py::TestRoutEngineState::\
test_commit_rejects_forged_duplicate_plan_atomically \
  tests/unit/test_morale_runtime.py::TestAggregationTransactions

# Retained reinforcement objects after preflight/commit failure:
# 2 failed in 2.55 s
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync pytest -q \
  tests/integration/test_phase112_commander_unit_integrity.py::\
test_dynamic_commander_commit_failure_rolls_back_and_retries_exactly \
  tests/integration/test_phase112_commander_unit_integrity.py::\
test_dynamic_commander_preflight_failure_preserves_rejected_unit_statuses

# Factory-loaded melee exposure and persistence proof: 1 failed in 1.73 s
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync pytest -q \
  tests/integration/test_phase113_morale_ownership.py::\
test_loaded_melee_rout_is_enabled_exposed_and_persisted
# Failure: engagement timestamp was datetime.min.
```

The final re-review found five further owner-boundary defects. Exact red nodes
were added before their production repairs:

```text
# Legacy surrender bypass: 1 failed in 0.15 s
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync pytest -q \
  tests/unit/test_morale_runtime.py::TestRuntimeTransitions::\
test_legacy_surrender_bypass_rejects_without_owner_mutation

# Forged runtime, route, and aggregation plans: 3 failed in 0.28 s
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync pytest -q \
  tests/unit/test_morale_runtime.py::TestRuntimeState::\
test_commit_rejects_forged_duplicate_records_atomically \
  tests/unit/test_morale_rout.py::TestRoutEngineState::\
test_commit_rejects_forged_nonfinite_snapshot_atomically \
  tests/unit/test_morale_runtime.py::TestAggregationTransactions::\
test_commit_rejects_forged_proxy_archive_disagreement_atomically

# Terminal proxy admission: 1 failed in 0.18 s
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync pytest -q \
  tests/unit/test_morale_runtime.py::TestAggregationTransactions::\
test_prepare_rejects_terminal_proxy_without_mutation

# Terminal restored constituent: 1 failed in 0.18 s
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync pytest -q \
  tests/unit/test_morale_runtime.py::TestAggregationTransactions::\
test_prepare_disaggregation_rejects_terminal_restored_unit

# Evolved terminal proxy resurrection: 1 failed in 0.23 s
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync pytest -q \
  tests/unit/test_morale_runtime.py::TestAggregationTransactions::\
test_prepare_disaggregation_rejects_terminal_proxy

# Accepted-but-inert surrender_threshold: 1 failed in 0.18 s
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync pytest -q \
  tests/unit/test_morale_rout.py::TestRoutConfig::test_is_strict_and_immutable

# Missing-runtime melee emitted partial effects before rejecting:
# 1 failed in 0.40 s
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync pytest -q \
  tests/unit/test_phase113_battle_runtime.py::\
test_melee_rout_without_runtime_rejects_before_partial_side_effects

# Successful rally was admitted twice with a valid zero-second cooldown:
# 1 failed in 0.61 s
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync pytest -q \
  tests/unit/test_phase113_battle_runtime.py::\
test_zero_cooldown_rally_is_not_rechecked_in_the_same_tick

# A failed rally after a same-tick melee rout exposed the general defect:
# 1 failed in 0.63 s
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync pytest -q \
  tests/unit/test_phase113_battle_runtime.py::\
test_zero_cooldown_failed_rally_does_not_recheck_same_tick_melee_rout
```

The first zero-cooldown repair tracked successful rally IDs locally. The
`$simplify` delta review rejected that incomplete fix because a same-tick
forced melee rout followed by a failed rally still reached `dt == 0`. The
final scheduler consults the immutable authoritative record instead: any unit
whose `last_check_time_s` already equals the current logical time is not
admitted a second time. Strict positive-`dt` validation remains in the runtime.

The same review also found that the positive guerrilla guard test injected an
unrelated RNG while asserting the context COMBAT stream and subscribed only to
morale events. The repaired direct guard injects and checks the exact COMBAT
stream and observes the base `Event` type. A separate factory-built
`coin_campaign` control enters `_execute_engagements`, proves the current
factory has no compatible population query, takes the zero-blend physical
retreat, and preserves record identity, status, all events, and exact COMBAT
and MORALE RNG states.

After repair, the complete six-file Phase 113 production selection passed:

```text
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync pytest -q \
  tests/unit/test_morale_runtime.py \
  tests/unit/test_morale_rout.py \
  tests/unit/test_phase113_battle_runtime.py \
  tests/unit/test_phase_68g_guerrilla_retreat.py \
  tests/integration/test_phase113_aggregation.py \
  tests/integration/test_phase113_morale_ownership.py
# 91 passed in 10.03 s; 0 warnings; 0 skips
```

The exact adversarial owner-boundary subset was independently repeated after
the final fix and simplify re-review:

```text
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync pytest -q \
  tests/unit/test_morale_runtime.py::TestRuntimeState \
  tests/unit/test_morale_runtime.py::TestAggregationTransactions \
  tests/unit/test_morale_rout.py::TestRoutConfig \
  tests/unit/test_morale_rout.py::TestRoutEngineState \
  tests/unit/test_morale_rout.py::TestProcessSurrender \
  tests/unit/test_phase113_battle_runtime.py
# 29 passed in 0.43 s; 0 warnings; 0 skips

env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync pytest -o addopts= -q \
  tests/benchmarks/test_phase13_determinism.py \
  tests/unit/test_phase_105_checkpoint_integrity.py
# 34 passed in 1.63 s; 0 warnings; 0 skips

env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  PYTHONPATH=/tmp PYTEST_PLUGINS=sw_uvloop_pytest \
  uv run --no-sync pytest -o addopts= -q \
  tests/api/test_phase113_morale_exposure.py
# 2 passed in 2.13 s; 0 warnings; 0 skips
```

The typed benchmark workload has an exact production-path draw-budget proof:

```text
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync pytest -o addopts= -q \
  tests/benchmarks/test_benchmarks.py::TestProductionWorker::\
test_morale_neutral_workload_executes_exact_runtime_draw_budget
# 1 passed in 2.94 s; 0 warnings; 0 skips
```

That node factory-loads the typed neutral 73 Easting workload, executes 360
production ticks, and proves 71 final records at generation 30, hence exactly
2,130 admitted record updates. It also compares the final MORALE state with a
fresh generator advanced by exactly 2,130 draws.

Fresh static and collection-integrity commands after the broad-run fixture
repairs were:

```text
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync ruff check .
# All checks passed!

git diff --check
# no output; exit 0

env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync python scripts/validate_test_evidence.py
# no-direct-oracle 85; reviewed behavioral-oracle 87; structural 918;
# weak-oracle 1,005; exit 0

env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync python scripts/validate_test_partitions.py \
  --output /tmp/sw-phase113-final/partition-audit/manifest.json
# exact pairwise-disjoint union; 11,824 nodes; 0 collection warnings

sha256sum /tmp/sw-phase113-final/partition-audit/manifest.json
# eefcdd5bc68ae03a71759ff01d754d2a58847af781468003f06d5bddbf38c2e3
```

The collection artifact records this exact union:

| Partition | Collected nodes |
|---|---:|
| standard | 11,367 |
| slow-only | 109 |
| benchmark-only | 62 |
| slow-benchmark | 4 |
| API | 241 |
| E2E | 41 |

Authoritative execution of that union, the overlapping terrain and benchmark
policy profiles, and the final benchmark comparison passed as recorded below.
Documentation controls are repeated after the final status transition.

Documentation controls at the same freeze passed:

```text
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync python scripts/validate_docs_links.py \
  > /tmp/sw-phase113-final/docs/fragment-control.json
# exit 0; valid fixture exits 0; invalid fixture exits 1 with a diagnostic

sha256sum /tmp/sw-phase113-final/docs/fragment-control.json
# d1324e93e4f059a7e665c35014c67c27d6bd429dc51600b46fc860e9c8d4167f

env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync mkdocs build --strict \
  --site-dir /tmp/sw-phase113-final/docs/site
# built in 4.66 s; exit 0; three intentionally unnavigated scenario-template
# pages; one informational Material-for-MkDocs/MkDocs-2 compatibility banner
```

### Rejected and qualified broad-run diagnostics

Early attempts ran provenance-sensitive partitions concurrently. They are not
acceptance evidence: concurrent repository artifacts changed the fingerprint
seen by other workers. The rejected results were standard 11,344 passed/5
failed/6 warnings in 827.41 seconds, API 236 passed/5 failed, E2E 38 passed/3
failed, and slow-benchmark 3 passed/1 failed. Their artifacts were moved under
`/tmp/phase113-rejected-partition-evidence`; all authoritative reruns are
sequential and write outside the repository.

A first standalone standard attempt then reported 11,334 passed/15 failed/6
warnings in 553.04 seconds. The 15 failures exposed real Phase 113 fixture and
evidence-ledger assumptions; after repair, their combined 78-node selection
passed in 3.27 seconds. A later fresh standard attempt was terminated by the
2,700-second wrapper at only 33% while the host sustained 60–85% CPU and load
averages of 19–24; it emitted no pytest failure and is recorded only as an
operational timeout.

The host's default selector loop also prevented local completion of API and
E2E runs: the API wrapper reached its 1,800-second limit and E2E reached 900
seconds without a pytest result.

After the user changed the network driver, the default API policy was retried
on the near-final tree before the last review repairs:

```text
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync python scripts/run_pytest_partition.py api \
  --manifest /tmp/sw-phase113-final/api-default/manifest.json \
  --junit /tmp/sw-phase113-final/api-default/junit.xml \
  --forbid-skips --timeout-seconds 2700
# collection: 241 selected, 0 deselected, 0 warnings
# manually terminated after approximately 900 s with no pytest output,
# no JUnit file, and no result.json; diagnostic only, not acceptance evidence
```

The network change restored remote access but did not remove this local
default-selector symptom. The explicitly qualified final-tree commands were:

```text
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  PYTHONPATH=/tmp PYTEST_PLUGINS=sw_uvloop_pytest \
  uv run --no-sync python scripts/run_pytest_partition.py api \
  --manifest /tmp/sw-phase113-final/api-qualified/manifest.json \
  --junit /tmp/sw-phase113-final/api-qualified/junit.xml \
  --forbid-skips --timeout-seconds 2700
# 241 passed in 143.08 s; 0 warnings; 0 skips

env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  PYTHONPATH=/tmp PYTEST_PLUGINS=sw_uvloop_pytest \
  uv run --no-sync python scripts/run_pytest_partition.py e2e \
  --manifest /tmp/sw-phase113-final/e2e-qualified/manifest.json \
  --junit /tmp/sw-phase113-final/e2e-qualified/junit.xml \
  --forbid-skips --timeout-seconds 2700
# 41 passed in 76.30 s; 0 warnings; 0 skips
```

The qualification plugin is `/tmp/sw_uvloop_pytest.py`, SHA-256
`c4a925f0677c4722348ecb014e36595854aaf7ca476e17ed62ed6c58fddeb46a`.
It changes only the session event-loop policy. Remote default-policy CI is
required after push; the local uvloop result is not silently generalized.

### Final broad execution evidence

Every provenance-sensitive run was sequential and wrote to a unique
`/tmp/sw-phase113-final` directory. The runner command for each deterministic
shard was the following exact form, with `PARTITION`, `N`, `COUNT`, and the
matching directory values resolved in the tables below:

```text
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync python scripts/run_pytest_partition.py PARTITION \
  --manifest /tmp/sw-phase113-final/DIRECTORY/manifest.json \
  --junit /tmp/sw-phase113-final/DIRECTORY/junit.xml \
  --shard-index N --shard-count COUNT --forbid-skips \
  --timeout-seconds 2700
```

The concrete substitutions were exact and complete:

| Partition | Directory value(s) | `N` | `COUNT` |
|---|---|---|---:|
| standard | `standard-shard-00` through `standard-shard-15` | 0 through 15 | 16 |
| slow-only | `slow-only-shard-0` through `slow-only-shard-3` | 0 through 3 | 4 |
| benchmark-only | `benchmark-only-shard-0` through `benchmark-only-shard-2` | 0 through 2 | 3 |
| slow-benchmark | `slow-benchmark` | 0 | 1 |

API and E2E use the fully expanded qualified commands above. The two
overlapping profiles used the unsharded runner defaults:

```text
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync python scripts/run_pytest_partition.py terrain \
  --manifest /tmp/sw-phase113-final/terrain/manifest.json \
  --junit /tmp/sw-phase113-final/terrain/junit.xml \
  --forbid-skips --timeout-seconds 2700
# 97 passed in 2.91 s

env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync python scripts/run_pytest_partition.py benchmark-policy \
  --manifest /tmp/sw-phase113-final/benchmark-policy/manifest.json \
  --junit /tmp/sw-phase113-final/benchmark-policy/junit.xml \
  --forbid-skips --timeout-seconds 2700
# 61 passed in 19.14 s

sha256sum \
  /tmp/sw-phase113-final/terrain/{manifest.json,junit.xml,result.json} \
  /tmp/sw-phase113-final/benchmark-policy/{manifest.json,junit.xml,result.json}
# terrain manifest: 4a476e569e95872c37fa668dc9d7abeeb413d06fc0dedfc4e38ada7edea8f43f
# terrain JUnit: fc277b061110f0ea8374b941a6ea6694ca7bede37180f9eb58016369ac83d550
# terrain result: 44011bc93844195a3b573cfd9c2d8c49a274dd87d15750a06a7f04afb397ba95
# benchmark manifest: 217edf4bda618a40a603ef05d352d6bb0cfb3ef191107bb8e9707f4d9bd13cab
# benchmark JUnit: a7605d3369fcd1f85e680db0325fdea63df1899253ace2962e6f6aea25b12bec
# benchmark result: 8dce1d5c5e3c829c739da01aa7606cda7292650e48c1417a7b9ddc810d3fcdbf
```

Those two profiles overlap the six-partition union and are intentionally not
included in `full-execution-audit.json`.

The complete non-standard union and two overlapping policy profiles passed:

| Selection | Shards | Passed | Durations (s) | Warnings/skips |
|---|---:|---:|---|---:|
| slow-only | 4 | 109 | 282.18, 449.31, 154.06, 1,148.93 | 0/0 |
| benchmark-only | 3 | 62 | 4.33, 0.76, 0.08 | 0/0 |
| slow-benchmark | 1 | 4 | 12.51 | 0/0 |
| API, qualified | 1 | 241 | 143.08 | 0/0 |
| E2E, qualified | 1 | 41 | 76.30 | 0/0 |
| terrain policy profile | 1 | 97 | 2.91 | 0/0 |
| benchmark policy profile | 1 | 61 | 19.14 | 0/0 |

The standard partition's unsharded 2,700-second operational timeout at 33%
contained no pytest failure. Deterministic module-affine LPT planning then
produced 16 non-empty shards, no split modules, and node counts
`711, 711, 711, 711, 711, 710, 710, 710, 710, 710, 711, 710, 710,
711, 710, 710`.

Broad execution found three genuine stale-test/evidence assumptions rather
than production failures:

- shard 8 first failed 1/710 because a Phase 85 LOD test supplied a
  `SimpleNamespace` instead of the typed `MoraleRuntime`. Its red run was
  `1 failed, 709 passed, 4 warnings in 41.29 s`. The test now registers real
  units through the runtime and proves generations `1` and `0`; its node and
  six-test file passed in 0.38 seconds;
- shard 9 first failed seven Phase 56 STRtree tests because their mock rout
  object lacked the production `config` boundary. All seven now execute the
  real `RoutEngine`/`MoraleRuntime` transaction and prove committed rally or
  cascade states/statuses. The class passed 7/7 and the file 35/35; and
- shard 10 then correctly failed its evidence-ledger self-test because those
  seven behavioral tests were stale in the weak-oracle ledger. Removing their
  structural dispositions produced the final 918 structural and 1,005 weak
  counts; the validator self-tests passed 2/2.

Those repairs changed only the Phase 85 test in standard shard 8, the Phase 56
test in standard shard 9, and the weak-oracle ledger exercised by standard
shard 10. Production, data, and every source selected by the previously
completed slow/API/E2E/scenario/profile runs remained byte-identical. The exact
three affected standard shards were rerun after repair; the current-tree
collection audit also proves that no node ID moved or disappeared. The final
standard evidence is:

| Shard index | Nodes passed | Duration (s) | Declared warnings |
|---:|---:|---:|---:|
| 0 | 711 | 49.59 | 0 |
| 1 | 711 | 43.28 | 0 |
| 2 | 711 | 29.82 | 0 |
| 3 | 711 | 14.86 | 0 |
| 4 | 711 | 59.81 | 1 |
| 5 | 710 | 8.02 | 0 |
| 6 | 710 | 10.13 | 0 |
| 7 | 710 | 76.90 | 0 |
| 8 | 710 | 41.95 | 4 |
| 9 | 710 | 7.98 | 0 |
| 10 | 711 | 48.57 | 0 |
| 11 | 710 | 27.38 | 1 |
| 12 | 710 | 5.20 | 0 |
| 13 | 711 | 55.55 | 0 |
| 14 | 710 | 3.73 | 0 |
| 15 | 710 | 22.54 + 9.12 + 43.12 | 0 |

Shard 4's warning is Matplotlib's empty-legend warning from
`TestForceStrengthChart.test_empty_data`; shard 8's four warnings are the
declared deleted-without-rendering animation warnings from the replay tests;
and shard 11's warning is the pre-existing `datetime.utcnow()` deprecation in
the Phase 64 planning process. There were no unclassified warnings and no
skips.

Standard shard 15 reproduced the local selector hang at exactly
`test_fastmcp_dispatch_executes_and_exposes_production_results`: its default
16-way run timed out after 2,700 seconds at roughly 40%. The frozen 710-node
selection was therefore executed as 326 default-policy nodes, that one node
under the declared uvloop qualification, and 383 default-policy nodes. The
three JUnit files record 326, 1, and 383 passes with zero failures, errors, or
skips. The composite audit proves a 710-node exact, pairwise-disjoint union:

```text
cp /tmp/sw-phase113-final/standard-shard-15/selection.args \
  /tmp/sw-phase113-final/standard-shard-15-split-a/selection.args
sed -i '327,$d' \
  /tmp/sw-phase113-final/standard-shard-15-split-a/selection.args

cp /tmp/sw-phase113-final/standard-shard-15/selection.args \
  /tmp/sw-phase113-final/standard-shard-15-qualified/selection.args
sed -i '1,326d;328,$d' \
  /tmp/sw-phase113-final/standard-shard-15-qualified/selection.args

cp /tmp/sw-phase113-final/standard-shard-15/selection.args \
  /tmp/sw-phase113-final/standard-shard-15-split-b/selection.args
sed -i '1,327d' \
  /tmp/sw-phase113-final/standard-shard-15-split-b/selection.args

timeout 2700s env PYTHONDONTWRITEBYTECODE=1 \
  UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync pytest -p no:cacheprovider -o addopts= \
  --tb=short -q \
  --junitxml=/tmp/sw-phase113-final/standard-shard-15-split-a/junit.xml \
  @/tmp/sw-phase113-final/standard-shard-15-split-a/selection.args
# 326 passed in 22.54 s

env PYTHONDONTWRITEBYTECODE=1 \
  UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  PYTHONPATH=/tmp PYTEST_PLUGINS=sw_uvloop_pytest \
  uv run --no-sync pytest -p no:cacheprovider -o addopts= \
  --tb=short -q \
  --junitxml=/tmp/sw-phase113-final/standard-shard-15-qualified/junit.xml \
  @/tmp/sw-phase113-final/standard-shard-15-qualified/selection.args
# 1 passed in 9.12 s

timeout 2700s env PYTHONDONTWRITEBYTECODE=1 \
  UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync pytest -p no:cacheprovider -o addopts= \
  --tb=short -q \
  --junitxml=/tmp/sw-phase113-final/standard-shard-15-split-b/junit.xml \
  @/tmp/sw-phase113-final/standard-shard-15-split-b/selection.args
# 383 passed in 43.12 s

sha256sum \
  /tmp/sw-phase113-final/standard-shard-15-composite-audit.json \
  /tmp/sw-phase113-final/standard-16-shard-audit.json
# 0ccfaea59728e67bfeabfc7a656d3f1e55f13f21f2347905014e654d1e08c60b
# b3024a1e9582c9ea015d023e803d6c55f672971b9a0fc1a423ba0fcfe07f203f
```

The final current-tree collection audit still reports 11,824 nodes, zero
collection warnings, six pairwise-disjoint partitions, and SHA-256
`eefcdd5bc68ae03a71759ff01d754d2a58847af781468003f06d5bddbf38c2e3`.
The execution audit checks every shard manifest, JUnit terminal count,
selection union, and skip policy against that collection:

```text
sha256sum /tmp/sw-phase113-final/full-execution-audit.json
# 0d58c61c6e2ff768ab93873b8eee1b290a8bd3ae118515b45c2b2ddb4fc6d128
# aggregate: 11,824 passed; 0 failed/errors/skips; 6 warnings
```

The JSON audit outputs were generated from the raw manifests/results/JUnit
files with inline Python and then independently replay-checked with this exact
command. It verifies every disjoint union and terminal JUnit count rather than
trusting only the derived JSON summaries:

```text
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync python -c '
import json
import xml.etree.ElementTree as ET
from pathlib import Path
root = Path("/tmp/sw-phase113-final")
collection = json.loads((root / "partition-audit/manifest.json").read_text())
def selection(path):
    return set(line for line in path.read_text().splitlines() if line)
def manifest_nodes(directory):
    payload = json.loads((root / directory / "manifest.json").read_text())
    return set(payload["shard"]["selected_node_ids"])
def junit(path):
    tree = ET.parse(path).getroot()
    suites = [tree] if tree.tag.endswith("testsuite") else [item for item in tree if item.tag.endswith("testsuite")]
    return {key: sum(int(suite.attrib[key]) for suite in suites) for key in ("tests", "failures", "errors", "skipped")}
def exact(parts, expected):
    assert sum(len(part) for part in parts) == len(set().union(*parts)) == len(expected)
    assert set().union(*parts) == expected
source15 = manifest_nodes("standard-shard-15")
names15 = ("standard-shard-15-split-a", "standard-shard-15-qualified", "standard-shard-15-split-b")
parts15 = [selection(root / name / "selection.args") for name in names15]
exact(parts15, source15)
assert [junit(root / name / "junit.xml")["tests"] for name in names15] == [326, 1, 383]
standard_parts = [manifest_nodes(f"standard-shard-{index:02d}") for index in range(16)]
exact(standard_parts, set(collection["partitions"]["standard"]["node_ids"]))
for index in range(15):
    totals = junit(root / f"standard-shard-{index:02d}/junit.xml")
    assert totals == {"tests": len(standard_parts[index]), "failures": 0, "errors": 0, "skipped": 0}
runs = {"slow-only": [f"slow-only-shard-{index}" for index in range(4)], "benchmark-only": [f"benchmark-only-shard-{index}" for index in range(3)], "slow-benchmark": ["slow-benchmark"], "api": ["api-qualified"], "e2e": ["e2e-qualified"]}
for partition, directories in runs.items():
    parts = [manifest_nodes(directory) for directory in directories]
    exact(parts, set(collection["partitions"][partition]["node_ids"]))
    for directory, part in zip(directories, parts, strict=True):
        assert junit(root / directory / "junit.xml") == {"tests": len(part), "failures": 0, "errors": 0, "skipped": 0}
full = json.loads((root / "full-execution-audit.json").read_text())
assert full["aggregate_outcomes"] == {"passed": 11824, "failed": 0, "errors": 0, "skipped": 0, "warnings": 6}
print(json.dumps(full["aggregate_outcomes"], sort_keys=True))'
# {"errors": 0, "failed": 0, "passed": 11824, "skipped": 0, "warnings": 6}
```

Finally, the consolidated current-tree owner/legacy-fixture selection passed:

```text
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync pytest -q \
  tests/unit/test_morale_runtime.py tests/unit/test_morale_rout.py \
  tests/unit/test_phase113_battle_runtime.py \
  tests/unit/test_phase_68g_guerrilla_retreat.py \
  tests/unit/test_phase56_performance_logistics.py \
  tests/unit/test_phase85_integration.py \
  tests/integration/test_phase113_aggregation.py \
  tests/integration/test_phase113_morale_ownership.py
# 132 passed in 8.46 s; 0 warnings; 0 skips
```

### Scenario and semantic review

The final `$evaluate-scenarios` pass used the frozen production tree, the
checked-in data catalog, and explicit seeds. `scripts/evaluate_scenarios.py`
uses `SimulationRuntimeFactory`/`SimulationEngine`; it excludes internal
`test_campaign*` and `benchmark_*` scenarios from broad discovery, but no
requested focused scenario was excluded here.

```text
mkdir -p /tmp/sw-phase113-final/scenarios

env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync python scripts/evaluate_scenarios.py \
  --scenario 73_easting --seed 42 \
  --output /tmp/sw-phase113-final/scenarios/73-easting-default-seed42.json
# 1/1 OK; 360 ticks; 3 terminal casualties; 0 evaluator issues

env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync python scripts/evaluate_scenarios.py \
  --scenario trafalgar --seed 42 --no-details \
  --output /tmp/sw-phase113-final/scenarios/trafalgar-seed42-a.json
# 1/1 OK; 372 ticks; 9 terminal casualties; 0 evaluator issues

env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync python scripts/evaluate_scenarios.py \
  --scenario trafalgar --seed 42 --no-details \
  --output /tmp/sw-phase113-final/scenarios/trafalgar-seed42-b.json
# same semantic result; 0 evaluator issues

env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync python scripts/evaluate_scenarios.py \
  --scenario calibration_arctic --seed 42 --no-details \
  --output /tmp/sw-phase113-final/scenarios/calibration-arctic-seed42-a.json
# 1/1 OK; 468 ticks; 2 terminal casualties; 0 evaluator issues

env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync python scripts/evaluate_scenarios.py \
  --scenario calibration_arctic --seed 42 --no-details \
  --output /tmp/sw-phase113-final/scenarios/calibration-arctic-seed42-b.json
# same semantic result; 0 evaluator issues

for seed in {0..19}; do
  env PYTHONDONTWRITEBYTECODE=1 \
    UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
    uv run --no-sync python scripts/evaluate_scenarios.py \
    --scenario waterloo --seed "$seed" --no-details \
    --output "/tmp/sw-phase113-final/scenarios/waterloo-seed-${seed}.json" \
    || exit 1
done
# 20/20 successful; 18 British and 2 French; force_destroyed 20/20;
# 0 evaluator issues

sha256sum \
  /tmp/sw-phase113-final/scenarios/73-easting-default-seed42.json \
  /tmp/sw-phase113-final/scenarios/trafalgar-seed42-a.json \
  /tmp/sw-phase113-final/scenarios/trafalgar-seed42-b.json \
  /tmp/sw-phase113-final/scenarios/calibration-arctic-seed42-a.json \
  /tmp/sw-phase113-final/scenarios/calibration-arctic-seed42-b.json \
  /tmp/sw-phase113-final/scenarios/waterloo-seed-*.json \
  > /tmp/sw-phase113-final/scenarios/raw-sha256.txt

sha256sum /tmp/sw-phase113-final/scenarios/raw-sha256.txt \
  /tmp/sw-phase113-final/scenarios/summary.json
# b46d12af069c9310c2ad4bf54625ba0d249a92efee7ecc14a1c2662b121ad046  raw-sha256.txt
# 18b9c950557151cb5e4d3012940ebaff4f47b8bead066f91a558b31c5acf4d25  summary.json
```

Replay normalization drops only absolute `scenario_path` and nondeterministic
`duration_wall_s`, then hashes sorted compact JSON. The exact normalization
command reported equal digests for each pair:

```text
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync python -c \
  'import hashlib,json,pathlib
root=pathlib.Path("/tmp/sw-phase113-final/scenarios")
def digest(name):
 data=json.loads((root/name).read_text())
 for item in data:
  item.pop("scenario_path",None); item.pop("duration_wall_s",None)
 return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(",",":")).encode()).hexdigest()
for first,second in (("trafalgar-seed42-a.json","trafalgar-seed42-b.json"),("calibration-arctic-seed42-a.json","calibration-arctic-seed42-b.json")):
 left=digest(first); right=digest(second); print(first,left,second,right,"equal="+str(left==right))'
# Trafalgar: 123f8ae3810f77de36deb901ce599cedf10de521d038cba5f87a9e48d00d480c, equal=True
# calibration_arctic: a8cbe8c655ae1bb715181c39b062f08e0c4dcc6264d191535c76ddd63d107360, equal=True
```

- Default 73 Easting: 71 units; blue 18 `ACTIVE` plus 3 `ROUTING`; red 50
  `ACTIVE`; blue wins by `time_expired` after 360 ticks/1,800 seconds. The
  recorder contains 118 morale changes (114 stochastic, two rally, two
  cascade), two rally events, and one victory event. The separate neutral
  workload retains blue 21/red 50 `ACTIVE`, one victory event, and no default
  morale outcome claim.
- Waterloo seeds 0 through 19 now yield 18 British and two French winners,
  compared with 20 British at the Phase 112 snapshot. Replay is deterministic;
  this is a REM-030/Phase 117 fidelity signal, not historical validation.
- Trafalgar seed 42 changed from British/`time_expired` at 5,760 ticks to
  Franco-Spanish/`morale_collapsed` at 372 ticks, with 326 morale changes,
  eight rallies, and seven British routed or surrendered. Two current replays
  have semantic digest
  `123f8ae3810f77de36deb901ce599cedf10de521d038cba5f87a9e48d00d480c`.
- `calibration_arctic` seed 42 changed from red/`force_destroyed` at 723 ticks
  to blue/`force_destroyed` at 468 ticks. Two current replays have semantic
  digest
  `a8cbe8c655ae1bb715181c39b062f08e0c4dcc6264d191535c76ddd63d107360`.

The latter two current-engine snapshot rows were changed only after exact
Phase 112/base, current, and current-replay comparisons. They guard the fixed
logical-time/status behavior; they do not assert historical correctness.

### Performance evidence

An initial unpinned three-pair 73 Easting comparison was rejected as noisy:
reference sample range was 27.94%, the host was saturated, and candidate ratios
were 1.3908, 1.2927, and 1.3986. Profiling attributed about 0.062 seconds of a
much larger noisy whole-run difference to 2,130 `MoraleRuntime` checks; generic
RNG rollback copying accounted for about 0.033 profiled seconds. Weakening draw
or rollback semantics for that small cost was rejected.

A later CPU-30 pinned pre-final comparison passed with ratios 1.163990039,
1.146401362, and 1.179465962, but final simplify repairs changed the runtime
tree after that artifact. The fresh idle-host, CPU-30 pinned comparison against
the checked-in reference passed on the final production tree:

```text
taskset -c 30 env PYTHONDONTWRITEBYTECODE=1 \
  UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync python scripts/run_paired_benchmark.py \
  --repo-root /home/csmith/projects/stochastic-warfare \
  --scenario 73_easting \
  --artifact /tmp/sw-phase113-final/paired-73-easting.json \
  --allow-dirty-candidate --worker-timeout-seconds 900
# pass; ratios 1.101958711, 1.099634464, 1.099029460
# median 1.099634464 <= 1.20
# candidate relative range 0.010757612 <= 0.20
# reference relative range 0.008635696 <= 0.20
# artifact-declared SHA-256:
# 817a9dec5ca2984e87e70e42d941b9d16297836cf9fd9fded79f6660ad7d870e

sha256sum /tmp/sw-phase113-final/paired-73-easting.json
# cac10f3a045ca2cf3f025ae9f18579c579ee360928d93ce114808a8725a52a03
```

The workload is the typed morale-neutral control plane, the timing scope is
`SimulationEngine.run`, and every semantic envelope is exact. The candidate
identity records base commit `2ff438ae732f359112a6bcf16a386557821bc75b` plus
the captured dirty runtime manifest. The environment records CPU affinity
`[30]`, 32 logical/16 physical cores, and 67,187,146,752 bytes of RAM. The
clean committed-tree identity bindings passed as recorded in the postmortem
below.

The final-tree profiling control is reproducible and separates the runtime
cost observation from the paired acceptance gate:

```text
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync python -m cProfile \
  -o /tmp/sw-phase113-final/morale-neutral-73-easting.prof \
  -m pytest -o addopts= -q \
  tests/benchmarks/test_benchmarks.py::TestProductionWorker::\
test_morale_neutral_workload_executes_exact_runtime_draw_budget
# 1 passed in 8.52 s; 0 warnings; 0 skips

env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync python -c \
  'import pstats; s=pstats.Stats("/tmp/sw-phase113-final/morale-neutral-73-easting.prof"); print([(k,v) for k,v in s.stats.items() if k[0].endswith("morale/runtime.py") and k[2] == "check_transition"])'
# 2,130 calls from BattleSimulation._execute_morale; 0.007145546 s own,
# 0.065850146 s cumulative

sha256sum /tmp/sw-phase113-final/morale-neutral-73-easting.prof
# 0b867ba60079127f4be395325287823affdd607d20a5d83fa9909c82ee193637
```

## Applicable reviews

`$design-review` accepted the final ownership and transaction contract before
implementation. `$simplify` initially returned `NOT READY`; every blocking and
closure-relevant finding—restore substitution, stale visualization,
benchmark-name loophole, mutable route plans/config, stale aggregate plans,
reinforcement status leakage, missing real melee proof, dummy melee timestamps,
legacy surrender mutation, forged owner-bound plans, terminal aggregation
resurrection, the inert surrender configuration, and partial melee effects—was
reproduced and repaired. Its delta review then rejected the first local-ID
zero-cooldown fix, required the general authoritative-record admission guard,
and verified the strengthened guerrilla RNG/event proof. The final verdict is
`READY`, with 29/29 owner-boundary tests green and no remaining high- or
medium-severity simplification finding.

`$audit-determinism` returned `PASS — DETERMINISTIC`: one injected `RNGManager`
MORALE stream,
canonical route/cascade/archive ordering, exact retry rewind, no RNG mirror in
morale/rout state, exact one-draw same-tick controls, and fresh restore/replay
equality. The scheduler's membership-free authoritative-record guard introduces
no unordered state-affecting traversal. `$validate-conventions` returned
`PASS — CLEAN`: typed strict configuration, logical simulation time, ENU
positions, injected dependencies, read-only public ownership exposure, and no
new global RNG or wall-clock simulation input. The reviews identify two
pre-existing timestamp exclusions rather than Phase 113 evidence:
`RoutEngine.initiate_rout()` retains its legacy wall-clock event timestamp but
has no production caller; `_apply_aggregate_casualties()` and auto-resolve do
have production callers and retain legacy `datetime.min` events. The latter is
therefore tracked explicitly as REM-034/Phase 121 rather than mislabeled as a
non-production limitation.

`$validate-data` is N/A because no YAML/catalog data changed. Frontend
validation is N/A because no frontend source changed. `$evaluate-scenarios`
applies and produced the outcomes above. The overlapping terrain profile passed
97/97 in 2.91 seconds, and the benchmark policy profile passed 61/61 in 19.14
seconds, both without warnings or skips. Local default-selector API/E2E and the
one FastMCP standard node remain a qualified host/tool-loop issue;
authoritative local evidence uses the declared uvloop plugin and remote CI must
confirm the default policy after push.

`$cross-doc-audit` returned `PASS` after the pre-closure corrections. Phase,
remediation, specification, architecture, API, checkpoint, validation-trust,
public-status, and devlog claims agree on the 11,824 executed nodes, six
classified warnings, uvloop-qualified local API/E2E/FastMCP boundary, benchmark
evidence, open residuals, and deliberately pending acceptance state. Fresh
link validation, strict MkDocs construction, and `git diff --check` passed; no
cross-document blocker remained before the postmortem.

## Remaining deficits and exclusions

REM-016, REM-018, REM-020, REM-021, and REM-028 through REM-034 remain open and
outside Phase 113. The aggregate-proxy evolution rejection is a declared
REM-016 boundary, not a whole-aggregation completion claim. REM-030/Phase 117
owns historical outcome-envelope validation for the scenario changes above.
REM-032/Phase 119 owns populated-area concealment; Phase 113 deliberately
guards a directly supplied positive value as unsupported rather than claiming
factory-loaded populated-area recognition or a proxy.
REM-033/Phase 120 owns captor/POW generation and logistics handling; the
authoritative `SURRENDERED` morale state is not a claim that lifecycle exists.

## Postmortem

**Verdict:** `PASS` — Phase 113 is accepted and REM-019 is closed. The clean
committed-tree benchmark identity is bound immediately after the phase commit;
because that verifier requires a clean commit, its external artifact cannot be
created before this gate or embedded with its own commit identity.

### Contract reconstruction

- **Scope:** On target. The phase delivered one `MoraleRuntime` owner, an
  immutable read-only projection, coordinated stochastic/rally/melee/cascade
  transactions, dynamic registration, complete suspended aggregate records,
  victory/recorder/API/campaign consumers, one RNG persistence owner, and
  format-113 fresh/in-place checkpoint continuation.
- **Changed from the initial plan:** Aggregate restoration was narrowed to the
  exact empty-attachment base-`Unit` boundary because REM-016 still owns
  subclass/loadout/supply reconstruction. A typed morale-neutral benchmark
  workload was added after profiling showed that the ordinary 73 Easting
  envelope intentionally changed under the repaired morale scheduler.
- **Dropped or deferred:** No REM-019 requirement was dropped. General
  aggregate reconstruction remains REM-016, populated-area concealment remains
  REM-032/Phase 119, captor/POW lifecycle remains REM-033/Phase 120, and
  production aggregate/auto-resolve event time remains REM-034/Phase 121.
- **Unplanned behavior:** Review exposed the guerrilla
  `blend_probability -> ROUTING` proxy and the rout-owned synthetic surrender
  result. Both now fail explicitly before partial mutation; their correct
  semantic owners are recorded as REM-032 and REM-033 rather than papered over.
- **Assumptions/non-goals:** Morale ownership is mandatory for every non-empty
  production runtime and has no enable/disable switch. Phase 113 does not add a
  direction-bearing `RoutState`, change military transition probabilities, or
  claim historical calibration.

### Capability and integration audit

| Stage | Accepted evidence |
|---|---|
| Declared | Strict immutable record/registration/plan/runtime types, caused events, strict configuration, and format-113 checkpoint topology |
| Loaded | `ScenarioLoader` builds one runtime from typed scenario calibration and registers the complete initial roster; reinforcement registration uses the same boundary |
| Wired | Battle stochastic checks, rally, melee, cascade, aggregation, victory, recorder, API, campaign, and checkpoint consumers share the stable runtime projection |
| Enabled | N/A: a production-loaded non-empty roster cannot opt out of authoritative ownership |
| Exercised | Seeded factory paths cover initial/dynamic units, every transition cause, aggregation/disaggregation, corruption rejection, and fresh/in-place restore |
| Outcome-affecting | Routed Goose Green records trigger `morale_collapsed`; the otherwise matched SHAKEN control does not; loaded melee enabled/WEAPONS_HOLD controls also diverge exactly |
| Persisted/exposed | Exact records, status, route state, archives, RNG continuation, events, API frames, analytics, campaign result, and recorder state survive or expose the same owner |

The complete production and test diff was inspected for placeholders, dummy
values, unconditional success, swallowed new exceptions, TODO/FIXME markers,
wall-clock simulation ownership, mutable escape, and unrelated files. Added
broad exception handlers either restore every staged owner and re-raise or
collect subscriber failures after the semantic commit. The lower-level route
helper's legacy wall-clock exclusion, REM-034's production aggregate/
auto-resolve event-time deficit, and REM-016's pre-existing lossy attachment/
order boundary remain declared rather than used as evidence.

### Test quality and validation verdict

The five original defects have production red proof and green regressions that
assert records, status, events, draw counts, generation, rollback/retry,
topology, continuation, exposed results, and outcome differences. The final
post-review owner/legacy-fixture selection repeated at 132 passed in 8.53
seconds with zero warnings or skips. The exact pairwise-disjoint broad union
executed 11,824 nodes: 11,824 passed, zero failed/errors/skips, and six
classified warnings. Evidence-oracle validation reports 85 no-direct, 87
reviewed behavioral, 918 structural, and 1,005 weak-oracle nodes. Scenario
replays, the 97-node terrain overlap, 61-node benchmark-policy overlap,
determinism/checkpoint reviews, profiling, repository-wide Ruff, documentation
links, strict MkDocs, and `git diff --check` all pass with the exact commands,
hashes, timings, and qualifications above.

Local API/E2E plus one FastMCP standard node required the declared uvloop
plugin because this host's default selector loop did not complete. The exact
qualified nodes passed without skips; hosted default-policy CI is the required
post-push confirmation and must reopen the phase if it finds a repository
failure. This qualification is not generalized into a host-default claim.

### Independent review and action items

The first independent postmortem review returned `PASS`: the contract-to-diff
trace is complete, every material defect has behavioral regression proof,
deterministic and checkpoint continuation evidence is exact, and no unrelated
production change was found. The second initially returned `FAIL` on deficit
accounting, not REM-019 implementation: it corrected the earlier
classification of aggregate and auto-resolve `datetime.min` events as
non-production. After that production-reachable deficit was added as
REM-034/Phase 121 across the backlog, roadmap, specification, navigation, and
this devlog, the repeated adversarial postmortem returned `PASS`. REM-032 and
REM-033 remain the other deficits recorded during Phase 113; none is hidden
inside this phase's acceptance.

The REM-034 correction and final status transition were revalidated with:

```text
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync python scripts/validate_docs_links.py docs
# exit 0; valid fixture exits 0; invalid fixture exits 1 with a diagnostic

env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync mkdocs build --strict \
  --site-dir /tmp/sw-phase113-final/docs/site-status-transition
# exit 0; built in 2.77 s; three intentional unnavigated templates and the
# informational Material-for-MkDocs/MkDocs-2 compatibility banner

env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync ruff check .
# All checks passed!

git diff --check
# no output; exit 0
```

### Clean committed-tree identity binding

The verifier cannot run before a clean commit exists. The first clean phase
commit was therefore bound to the accepted comparison, this devlog alone was
amended to record the stable result, and the verifier was repeated against the
amended clean identity:

```text
taskset -c 30 env PYTHONDONTWRITEBYTECODE=1 \
  UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync python scripts/run_paired_benchmark.py verify-final \
  --repo-root /home/csmith/projects/stochastic-warfare \
  --artifact /tmp/sw-phase113-final/paired-73-easting.json \
  --verification /tmp/sw-phase113-final/paired-73-easting-pre-amend.json \
  --worker-timeout-seconds 900
# exit 0; final-tree pass; clean identity; exact runtime-manifest, runtime-input,
# and semantic-envelope equality; fresh candidate reproduction

taskset -c 30 env PYTHONDONTWRITEBYTECODE=1 \
  UV_CACHE_DIR=/tmp/sw-phase113-uv-cache \
  uv run --no-sync python scripts/run_paired_benchmark.py verify-final \
  --repo-root /home/csmith/projects/stochastic-warfare \
  --artifact /tmp/sw-phase113-final/paired-73-easting.json \
  --verification /tmp/sw-phase113-final/paired-73-easting-final-tree.json \
  --worker-timeout-seconds 900
# exit 0 after the documentation-only amend; final-tree pass; clean identity;
# exact runtime-manifest, runtime-input, and semantic-envelope equality; fresh
# candidate reproduction
```

Both reproductions retain the typed morale-neutral 73 Easting envelope: 71
units, all 21 blue and 50 red units active, blue `time_expired`, 360 ticks,
1,800 logical seconds, one event, and the exact recorded event/roster digests.
The first-to-final change is documentation-only and outside the runtime
manifest. Final commit and verification digests remain in the external
artifact and handoff because embedding either value here would mutate the
identity being named and create an endless self-reference. Push and hosted CI
follow only after the final binding passes.
