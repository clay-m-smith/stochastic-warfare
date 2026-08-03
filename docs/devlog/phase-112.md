# Phase 112 - Validation and Documentation Trust

> **Phase 117 historical-claim supersession (2026-08-02):** This archived page
> preserves implementation history. Its historical-winner, outcome, casualty,
> duration, calibration, plausibility, envelope, and tolerance statements are
> not accepted historical validation. Any engine figures below are regression
> history only, not predictive evidence or calibration authority; the typed
> claim ledger and accepted production artifacts, if any, are authoritative.


**Status:** Complete

**Started:** 2026-07-29

**Completed:** 2026-07-30

## Why this phase exists

Phase 112 closes the integrity gaps in test-suite accounting, behavioral
evidence, analysis execution, commander/unit validation, movement diagnostics,
benchmark policy, Space ISR report state, and documentation links. The phase
owns REM-013, REM-014, REM-017, REM-022, REM-023, REM-024, REM-025, REM-026,
and REM-027 while preserving the Phase 105 REM-015 documentation baseline.

The accepted implementation contract is
[`validation-and-documentation-trust.md`](../specs/validation-and-documentation-trust.md).
The contract explicitly leaves REM-016, REM-018 through REM-021, and the newly
recorded REM-028/029 outside this phase rather than treating them as closure
evidence.

## Start gate

Phase 111 passed `$postmortem`, was committed as
`0460ac70be86784bcc6e359ae4202f4bcb938c60`, and was pushed before Phase 112
implementation began. The synchronization gate was repeated after the
design-only files were present:

```text
git pull --ff-only origin main
# From https://github.com/clay-m-smith/stochastic-warfare
#  * branch            main       -> FETCH_HEAD
# Already up to date.

git rev-parse HEAD
git rev-parse origin/main
# 0460ac70be86784bcc6e359ae4202f4bcb938c60
# 0460ac70be86784bcc6e359ae4202f4bcb938c60

git status --short --branch
# ## main...origin/main
#  M docs/remediation-backlog.md
# ?? docs/development-phases-block13.md
# ?? docs/specs/validation-and-documentation-trust.md
```

Those three paths were the intentional Phase 112 specification/backlog/
follow-up-roadmap work. No unrelated user change was present.

`CODEX.md`, `AGENTS.md`, Block 12, the Phase 108 evidence requested by the
owner, the current remediation backlog, the preceding phase devlogs, and the
applicable skill instructions were read before production implementation.
Phase 109 through Phase 111 evidence was also audited because it defines the
current Ruff, equipment, checkpoint, Space, and scheduled-fire boundaries that
Phase 112 must preserve.

All Python commands use `UV_CACHE_DIR=/tmp/sw-uv-cache`.

## Machine envelope

```text
nproc
# 32

lscpu
# AMD RYZEN AI MAX+ 395 w/ Radeon 8060S
# 1 socket, 16 physical cores, 2 threads per core, 32 online logical CPUs

free -h
# Mem: 62 GiB total, 4.7 GiB used, 40 GiB free, 57 GiB available
# Swap: 7.8 GiB total, 6.1 MiB used

uv --version
# uv 0.11.11 (x86_64-unknown-linux-gnu)

uv run --no-sync python --version
# Python 3.12.10

uv run --no-sync pytest --version
# pytest 9.0.2
```

`pytest --help` exposes no xdist `--numprocesses`/`--dist` option. Independent
isolated commands can use the host concurrently, but each pytest process
remains serial unless the repository adds and validates a parallel runner.
The available-memory envelope is ample for the declared independent suites;
memory safety is not used to waive any suite.

## Specification and design gate

`$spec` froze the Phase 112 production contract before implementation.
`$design-review`, `$research-models`, and `$research-military` were applied
because the phase changes statistical claims, military commander
classification, historical unit data, benchmark evidence, and Space imagery
fusion.

The initial independent reviews returned `NEEDS REVISION`. Production edits
remained paused while the contract was corrected. Material revisions included:

- one runtime-owned analysis factory/session boundary and strict metric/vector
  provenance instead of false authoritative zeroes;
- exact commander activation/merge/assignment and eager roster construction
  semantics;
- bounded movement dispositions that distinguish intentional standoff,
  production resource blocking, and injected invariant failures;
- a paired same-host benchmark policy closed over the effective loader input
  and recorder event stream;
- a typed, transactional Space ISR report/receipt/association boundary with
  exact temporal and checkpoint invariants;
- explicit `imint_fusion_constellation_ids` so broad Space enablement does not
  turn unsupported Keyhole/Lacrosse data into a fusion claim;
- sourced WorldView-2/WorldView-3 proof values, conservative CE90 conversion,
  real loader-built `Unit` targets, and rejection of the old implicit
  strength-one target proxy;
- generated long-delay, age-boundary, stale-reactivation, and same-epoch
  ordering proofs with exact production times; and
- planned REM-028/029 handoff to Block 13 without beginning those phases.

The final movement review, benchmark/Space review, ISR review, and Space
data/runtime review each returned `APPROVED` with no material blocker. These
were design approvals only. They neither establish implementation behavior nor
authorize phase completion. The specification status then moved from
`Proposed` to `Accepted design`.

## Baseline and production red evidence

Baseline collection is in progress. Results below must describe the
phase-start production behavior and are not closure evidence.

### Repository-wide Python lint

The exact Python command used by the remote lint workflow is green at the
Phase 112 start revision:

```text
UV_CACHE_DIR=/tmp/sw-uv-cache uv run --no-sync ruff check \
  stochastic_warfare/ api/ tests/ scripts/
# All checks passed!
```

This confirms that the owner's previously reported remote Python lint failure
remains repaired locally. The failed remote run was GitHub Actions run
`30421215404` at Phase 108 commit `70e72f5`; its exact Ruff command reported
six duplicate-key `F601` findings in the legacy scenario-runner mappings and
two placeholder-free `F541` strings. The three subsequent main-branch lint
runs at `f5a5a2d`, `3c09586`, and the Phase 111 start commit `0460ac7` all
completed successfully. The Phase 109 mapping replacement therefore already
closed the reported incident; Phase 112 preserves and enforces the same
repository-wide command. This is not evidence for the other remediation
items.

### Suite collection and terrain profile

Collection commands used the phase superset environment and disabled both the
repository addopts and pytest cache:

```text
PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-uv-cache \
  uv run --no-sync python -m pytest --collect-only -q \
  -p no:cacheprovider --override-ini=addopts=
# 11,572 collected; exit 0

# Same prefix, plus:
-m 'not slow and not benchmark' --ignore=tests/api --ignore=tests/e2e
# 10,978 collected from 11,326 backend nodes; 348 deselected; exit 0

-m 'slow and not benchmark' --ignore=tests/api --ignore=tests/e2e
# 314 collected; 11,012 deselected; exit 0

-m 'benchmark and not slow' --ignore=tests/api --ignore=tests/e2e
# 16 collected; 11,310 deselected; exit 0

-m 'slow and benchmark' --ignore=tests/api --ignore=tests/e2e
# 18 collected; 11,308 deselected; exit 0

tests/api
# 205 collected; exit 0

tests/e2e
# 41 collected; exit 0
```

There were no collection warnings. The six node-ID sets are pairwise disjoint
and their union is the exact 11,572-node superset: missing 0, extra 0. These
fresh counts agree with the specification but remain evidence rather than a
hard-coded acceptance oracle.

The phase-start `terrain` marker is a false partition:

```text
# Same collection prefix:
-m terrain --ignore=tests/api --ignore=tests/e2e
# 0 collected from 11,326; 11,326 deselected; exit 5
```

The four intended optional-dependency files collect 62 nodes, all of which
also belong to the standard set:

```text
tests/unit/test_phase_15a_pipeline_heightmap.py
tests/unit/test_phase_15b_classification_infrastructure.py
tests/unit/test_phase_15c_bathymetry.py
tests/unit/test_phase_15d_integration.py
# 62 collected; exit 0; standard overlap 62/62
```

Running those files in the current non-terrain environment does not exercise
the optional paths:

```text
# Same environment, --no-sync and --override-ini=addopts=:
tests/unit/test_phase_15a_pipeline_heightmap.py \
tests/unit/test_phase_15b_classification_infrastructure.py \
tests/unit/test_phase_15c_bathymetry.py \
tests/unit/test_phase_15d_integration.py
# 42 passed, 21 skipped in 0.58 s; exit 0
# rasterio=False; xarray=False
```

The 21 summary skips comprise 20 collected test-node `importorskip` outcomes
and one module-collection skip at
`test_phase_15a_pipeline_heightmap.py:193`, explaining the 62 collected node
IDs versus 63 reported outcome items. No terrain extra is installed in this
environment.

### Structural-evidence red

The phase-start repository has neither a registered `structural` marker nor
decorated structural tests:

```text
# Full superset collection with:
-m structural
# 0 selected, 11,572 deselected; exit 5
```

An AST triage scans 10,063 source test definitions. Its exact direct-signal
predicate is an AST `assert`, a call whose leaf name is
`raises`/`warns`/`fail`, or a call leaf beginning with `assert`. It finds 105
source definitions without a direct signal, expanding through parametrization
to 138 collected node IDs: 133 standard, one slow+benchmark, four API, and
zero in the other partitions.

The 13 declared phase-start structural-cluster files contain 139 collected
IDs, all standard. Only one overlaps the no-direct set, so the two diagnostic
sets have a 276-node union. The 139 known-cluster count is a floor, not a
complete weak-oracle inventory. Both required current-state ledgers and the
historical remediation ledger are absent.

The separate declared structural/weak heuristic matches a collected node when
its test definition is in one of those 13 clusters, calls a
source/signature/import helper (`getsource`, `getsourcelines`, `read_text`,
`read_bytes`, `parse`, `signature`, `getmembers`, `getattr_static`, or
`import_module`), or uses mock call/await assertions or counters. Over the
11,572-node superset it reports:

```text
named structural clusters       139
source/signature/import          227
mock-call/await                  118
structural/weak union            437
no-direct-signal expansion       138
combined initial heuristic union 574
```

There are 47 cluster/source overlaps and no other structural-category overlap.
The structural/weak and no-direct sets overlap at one Phase 78 parameter test.
The 574-node union is an initial review queue, not a claim that every
shape/count/non-null weak oracle has already been found.

All 12 high-risk nodes named by the specification collect successfully:
`test_batch_semaphore_limits_concurrency` belongs to API, and the other 11
belong to standard. All 12 are in the no-direct-signal set, so none may support
a behavioral claim until repaired or honestly reclassified.

Their phase-start strongest behavior is:

- the API semaphore test defines concurrency counters/lock but never updates or
  asserts them;
- terrain coordinate consistency discards four lookups and does not exercise
  the complete stack;
- C2 mid-load latency computes an unused baseline and makes only no-crash
  calls;
- ISR timing-gap discards both report results;
- air-posture supplies empty weapons and observes only no exception;
- naval `event_published` neither retains the result nor observes the bus;
- stratagem activation, fatigue temperature, and both morale JIT tests are
  no-crash calls with no state/result/kernel oracle;
- strategic tick does not observe a campaign update; and
- simultaneous-battle stepping inserts two contexts but observes neither
  battle.

These are false or weak behavioral names, not production evidence.

### Workflow-cadence red

The current workflows expose these exact gaps:

- `test.yml` triggers on every branch push and pull requests to `main`, syncs
  `dev+api`, and runs only
  `uv run python -m pytest --tb=short -q`; current addopts reduce that to the
  10,978-node standard partition while ignoring API/E2E and excluding all
  slow/benchmark/terrain tests.
- `lint.yml` has the same triggers, syncs `dev`, and runs the correct
  repository Ruff command.
- `docs.yml` runs only on `main` pushes touching `docs/**`/`mkdocs.yml` plus
  manual dispatch; it has no pull-request validation and couples strict build
  to deployment.
- `benchmark.yml` runs on `main` pushes, pull requests, and manual dispatch,
  with a 30-minute job timeout. It runs the 73 Easting class and infrastructure
  tests; Golan is gated by a manual Boolean. It has no weekly schedule.
- `build.yml` runs only for pull requests to `main`.

Across all current workflows there are zero cron schedules, zero explicit
API/E2E/terrain jobs, zero slow-only/benchmark-only/slow-benchmark jobs, zero
`--locked` dependency syncs, zero terrain-extra syncs, zero artifact uploads,
and zero `if: always()` evidence-retention steps.

### Documentation baseline and fragment red

```text
UV_CACHE_DIR=/tmp/sw-uv-cache uv run --no-sync mkdocs build --strict \
  --site-dir /tmp/sw-phase112-mkdocs-current
# exit 0
```

REM-015 is therefore green at phase start. The command nevertheless reports
seven broken page-plus-fragment targets as informational diagnostics because
anchor validation is not enabled. Those targets affect 49 historical links
across the three malformed slug forms declared in the specification.

MkDocs also reports six navigation omissions at the current design-only
worktree: the new Block 13 roadmap, Phase 112 devlog, Phase 112 specification,
and the three intentionally excluded scenario template/audit pages. Phase 112
must add the first three and retain only the three documented exclusions.

### Analysis false-green behavior

The real phase-start analysis runner accepts ineffective input and manufactures
authoritative-looking zeroes. A production `run_sweep` over the real
`test_campaign` scenario used seed 42, `max_ticks=1`, one iteration,
`advance_speed` values 1 and 999, and requested `unsupported_metric`:

```text
# exit 0
# value 1:   raw [0.0], mean/min/max/std 0.0
# value 999: raw [0.0], mean/min/max/std 0.0
```

`CalibrationSchema` accepts `advance_speed` at the loose patch boundary and
then drops it (`present_after_validation=false`). `run_comparison` over the
same variants/metric also exits zero and returns raw A/B `[0.0]`, means 0,
Mann-Whitney U 0, p-value 1, and effect 0. An empty sweep returns
authoritative `points=[]`; `num_iterations=0` comparison returns empty vectors,
zero means/U/effect, and p-value 1.

Real `ScenarioLoader`/analysis runs also accept semantically empty forces. A
temporary blue-4/red-0 configuration returns active vectors `[4, 0]`; a
blue-0/red-0 configuration returns all four active/destroyed metrics as
`[0.0]`. The older unknown-unit partial-roster route is no longer reproducible:
the Phase 109 runtime loadout boundary now raises `EquipmentMappingError`.
Phase 112 records that repaired fact rather than claiming a current red that
does not exist.

The typed API request models accept and serialize an empty `advance_speed`
sweep and a comparison with the dead override. Live ASGI/direct route probes
did not return: the ASGI probe was terminated after more than 90 seconds and
two direct async route probes after more than 10 seconds. They provide no
endpoint false-green claim; current source only confirms delegation to the
false-green core.

MCP behavior is directly reproducible:

```text
_tool_run_monte_carlo("test_campaign", num_iterations=0, max_ticks=1)
# exit 0; success-like result with num_iterations=0 and metrics={}

_tool_modify_parameter(
  "test_campaign", "advance_speed", 999, seed=42, max_ticks=1
)
# exit 0
# baseline == modified:
# 1 tick / 5 s, blue 4 active, red 6 active, 0 destroyed, max_ticks draw
```

The reported run ID is ephemeral and is not phase evidence.

### Commander-profile red

Fresh production loading reproduced exactly 77 swallowed profile warnings and
zero commander assignments:

```text
Suwalki Gap
# authored/loaded 24 blue + 15 red
# 39 warnings: joint_commander x24, conventional_commander x15
# CommanderEngine assignments: {}

Korean Peninsula
# authored/loaded 16 blue + 22 red
# 38 warnings: joint_commander x16, conventional_commander x22
# CommanderEngine assignments: {}
```

Both focused data validators exit zero. Seed-42 evaluator runs also report
successful scenarios with no integrity issue:

```text
Suwalki Gap
# 10 ticks, 9 casualties, 127 engagements, moved 6/39

Korean Peninsula
# 144 ticks, 16 casualties, 89 engagements, moved 20/38
```

A real catalog/load audit finds 13 available profiles and exactly six
unresolved authored side references. All five affected scenarios load with no
commander engine:

```text
Khafji red                 attritional_defender   (140 loaded units)
Debecka Pass red           attritional_defender   (28 loaded units)
Fallujah Phase Line red    attritional_defender   (135 loaded units)
Bint Jbeil red             attritional_defender   (99 loaded units)
INS Hanit blue             defensive_posture      (1 loaded unit)
INS Hanit red              opportunistic_strike   (2 loaded units)
```

The accepted replacements are `aggressive_armor` for Khafji/Debecka red,
`insurgent_leader` for Fallujah/Bint Jbeil red, `naval_surface` for INS Hanit
blue, and `insurgent_leader` for INS Hanit red.

A detached archive of exact phase-start commit `0460ac70be86` (verified
`uv.lock` SHA-256
`bbc6b45cfc270d08baa09d3d568a6b84d0f936a6ee9c874cb49c9d8813c5ad39`)
also captured the semantic baselines needed to review the enabled commander
path. Each scenario used this command shape, with the scenario ID and output
path varied:

```text
PYTHONPATH=/tmp/sw-phase112-baseline-0460ac \
  /home/csmith/projects/stochastic-warfare/.venv/bin/python \
  scripts/evaluate_scenarios.py --scenario <id> \
  --output /tmp/sw-phase112-baseline-<id>.json --no-details --seed 42
```

| Scenario | Winner/condition | Ticks | Casualties | Engagements | Moved/still | Events |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Khafji | blue/force_destroyed | 716 | 57 | 758 | 238/3 | 1,729 |
| Debecka Pass | blue/force_destroyed | 175 | 51 | 4,057 | 83/1 | 8,218 |
| Fallujah Phase Line Fran | blue/force_destroyed | 115 | 68 | 1,643 | 256/77 | 3,543 |
| Bint Jbeil 2006 | blue/force_destroyed | 19 | 82 | 515 | 204/45 | 1,209 |
| INS Hanit 2006 | blue/time_expired | 1,440 | 2 | 14 | 2/1 | 43 |
| Suwalki Gap | blue/force_destroyed | 10 | 9 | 127 | 6/33 | 332 |
| Korean Peninsula | blue/force_destroyed | 144 | 16 | 89 | 20/18 | 287 |

All seven baseline evaluator commands exited zero. Wall time ranged from
1.64 seconds (INS Hanit) to 60.79 seconds (Khafji); these are outcome
provenance facts, not performance claims. Current-tree comparisons remain a
final verification gate after commander/OODA, movement, and Space integration
stabilize.

### Unit-definition and exact-roster red

The complete REM-024 failure chain is behavioral:

```text
UnitLoader.load_definition(data/units/infantry/french_old_guard.yaml)
# accepts crew skill literal EXPERT

SkillLevel members
# UNTRAINED, BASIC, TRAINED, EXPERIENCED, VETERAN, ELITE

create_unit(...)
# KeyError('EXPERT')
```

The production loader broadly catches that constructor error and logs the
misleading warning
`Unit type 'french_old_guard' not found in loader — skipping`.

```text
Austerlitz
# authored French 10 + coalition 9 = 19
# loaded 9 + 9 = 18; Old Guard 0
# focused validator exit 0 with one skip warning
# evaluator seed 42: OK/no issues
# 264 ticks, 4 casualties, 90 engagements, moved 9/18, stuck 9/18

Waterloo
# authored French 11 + British 9 = 20
# loaded 10 + 9 = 19; Old Guard 0
# focused validator exit 0 with one skip warning
# evaluator seed 42: OK/no issues
# 347 ticks, 5 casualties, 152 engagements, moved 10/19, stuck 9/19
```

The focused validator commands take approximately 0.97/0.94 seconds and the
evaluators 0.7/0.8 seconds. This proves eager definition acceptance,
constructor `KeyError`, broad skip, reduced roster, and false-green
validator/evaluator status through the real production chain.

### Movement-diagnostic red

```text
time env UV_CACHE_DIR=/tmp/sw-uv-cache uv run python \
  scripts/evaluate_scenarios.py --scenario cambrai \
  --output /tmp/phase112-cambrai-red.json --seed 42
# exit 0
# evaluator: 0.7 s; shell real 1.209 s, user 6.698 s, sys 0.040 s
# 433 ticks / 2,165 logical seconds
# British force_destroyed win
# 2 casualties, 14 evaluator engagement events, 34 total events
# moved 3/10
# WARN MANY_STUCK_UNITS (4/7)
```

The exact four unmoved units are Mark IV IDs ending `0003` through `0006`;
each remains at x=1,500 and its respective y=2,350/2,650/2,950/3,250. Their
best weapon range is 6,675 m, and the production 0.8 standoff factor yields
5,340 m against the scenario's 3,000 m visibility.

A separate real loader/engine recorder probe reproduces the same
433-tick/2,165-second result and 34 events. The 12 actual `EngagementEvent`
records are all Lee-Enfield infantry fire. Tank fire count is 0, tank-target
count is 0, and all four tanks remain active and unchanged with weapon ranges
6,675/800 m. The current evaluator therefore labels intentional blind
standoff as stuck movement without proving an engagement.

### Benchmark-policy red

A fresh 73 Easting warm-up and three timed `run_benchmark(..., profile=False)`
runs produced:

```text
warm-up: 1.497862363 s
timed:   1.497888765, 1.483927603, 1.491660642 s
median:  1.491660642 s
shell real: 7.876 s
```

Every run used seed 42 at `0460ac7`, loaded 71 units, produced blue as winner,
and ran 360 ticks. The stored reference instead records 8.0 s, 185 ticks, and
commit `c76d63e`; every current `check_regression` call nevertheless returns
`False`/`OK` because it compares only wall time. A separate evaluator run exits
zero in 2.404 s at 360 ticks/1,800 logical seconds, with blue `time_expired`,
0 casualties, 0 engagements, 30 events, moved 21/71, and warnings for zero
casualties, zero engagements, and 50/71 stuck.

The accepted specification already records the fresh start-revision Golan
sample, 129.517695006 s for 290 units, blue winner, and 6,480 ticks; it was not
duplicated during this baseline. The current baseline logic calls that sample
`OK` against `500 * 1.2`, while the hard 60-second and legacy 120-second gates
both fail. Current source contains the 60-second benchmark assertion,
120-second battle/campaign assertions and structural enforcement, and the
500-second stored reference.

### Space ISR production red

The shipped scenario named `space_isr_gap` contains no Space runtime:

```text
time env UV_CACHE_DIR=/tmp/sw-uv-cache uv run python \
  scripts/evaluate_scenarios.py --scenario space_isr_gap \
  --output /tmp/phase112-space-isr-gap-red.json --seed 42
# exit 0; evaluator OK
# 33 ticks, 8 casualties, 99 engagement events, moved 12/12
# evaluator wall 0.4 s
# shell real 0.955 s, user 6.451 s, sys 0.046 s
```

A real loader probe reports `enable_space_effects=False`,
`space_config=False`, `space_engine=False`, `ew_engine=False`, and
`sigint_engine=False`; only the always-owned FOW fusion object exists. The
named validation scenario is therefore a short ordinary combat scenario, yet
the evaluator returns false-green `OK`.

Taiwan Strait loads 32 units with Space, EW, SIGINT, and
`enable_space_effects=true`. Korean Peninsula loads 38 units with Space and
the flag enabled but no EW/SIGINT. Both load Keyhole optical (0.3 m) and
Lacrosse SAR (1.0 m). The current target-size helper returns `vehicle` for
every sampled real `Unit`, including a DDG-51 with 281 personnel, an SSN with
129, and a Bradley with five, because it reads nonexistent attributes and
defaults to strength one.

At Taiwan logical time 120 s, a real red Sovremenny with 344 personnel is
classified `vehicle` and produces no visible 1.0 m Lacrosse report. A
`SimpleNamespace` proxy with the same ID/position and `strength=344` is
classified `battalion` and produces one. An arbitrary unloaded
`not_in_loaded_roster` target at `Position(123,456)` with strength 10 also
produces a generic dictionary report. The buffer contains both reports. This
is adversarial subsystem evidence of the proxy defect, not capability proof.

Natural production generation exposes the wiring failures:

- Korean at logical 6,240 s generates 22 Keyhole reports for its red units.
  Each has delay 300 s and observation time 6,240. With no EW/SIGINT engine,
  normal `_fuse_sigint()` leaves all 22 buffered and creates zero owner or
  opponent tracks.
- Taiwan at logical 8,880 s generates 16 Keyhole reports with availability
  9,180 s. Calling production fusion immediately at 8,880 clears the buffer
  from 16 to 0, creates 16 blue and 16 red tracks, and gives blue
  `track-0001` and red `track-0017` identical position/time. Delivery is 300 s
  early and the same owner imagery leaks to the opponent.

Current source labels every Space report `IntelSource.SIGINT`, uses image
resolution as position uncertainty, reuses the same report list for every
side, and swallows fusion errors.

The full production checkpoint accepts a deliberately impossible buffered
dictionary: extra key, unknown target/satellite, non-imaging GPS
constellation, negative resolution/delay, sensor type `none`, future
observation `1e12`, and `Position(1,2,3)`. A fresh Taiwan runtime restores it
without error, rehydrates the `Position` as a plain list, and then silently
clears the buffer while creating no track. The current ISR state boundary
validates only generic JSON shape.

Existing focused tests remain green over these defects:

```text
time env UV_CACHE_DIR=/tmp/sw-uv-cache uv run --no-sync pytest -q \
  -o addopts= \
  tests/unit/test_phase_17c_isr_ew.py \
  tests/unit/test_phase_65_infra.py \
  tests/unit/test_phase_65a_space_isr_ew.py \
  tests/unit/simulation/test_engine_sigint_victory.py
# 52 passed in 0.44 s; exit 0
# shell real 0.764 s, user 6.223 s, sys 0.055 s
```

Those tests include source searches and manually buffered dictionaries. Their
green result is not REM-027 evidence.

### Focused production-red tests

Three new focused files froze the required production failures before their
implementations changed:

```text
PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-uv-cache \
  uv run --no-sync python -m pytest \
  tests/unit/test_phase112_analysis_red.py \
  -q --tb=short -o addopts=
# 2 failed, 1 passed in 4.18 s; exit 1
# unknown metric and authored empty roster both returned without raising
# the real six-run outcome-effect control passed

PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-uv-cache \
  uv run --no-sync python -m pytest \
  tests/validation/test_phase112_commander_unit_red.py \
  -q --tb=short -o addopts=
# 3 failed in 1.12 s; exit 1
# missing profile and EXPERT skill returned without raising
# Austerlitz loaded 18/19 units and no Old Guard

PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-uv-cache \
  uv run --no-sync python -m pytest \
  tests/integration/test_phase112_runtime_red.py \
  -q --tb=short -o addopts=
# 5 failed in 2.38 s; exit 1
# Cambrai remained MANY_STUCK_UNITS(4/7)
# fuel blocking had no persisted semantic reason
# malformed Space report state restored
# space_isr_gap had no Space engine
# the legacy unpaired Golan verifier authorized a pass
```

These are production-path reds, not source-search acceptance tests. Their
positive controls use the real scenario loader/engine or evaluator. The final
verification must rerun the same nodes green and retain their exact semantic
outcomes.

### Executable delivery-contract red

After the reconnaissance above froze the baseline, Phase 112 added a focused
delivery-contract test without changing production or workflow behavior:

```text
PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-uv-cache \
  uv run --no-sync python -m pytest -q -o addopts= \
  tests/validation/test_phase112_delivery_contract_red.py
# 4 failed in 0.07 s; exit 1
```

The four failures are exact accepted-contract reds:

1. `pyproject.toml` has no `structural` marker and still treats terrain/API/E2E
   markers as hidden default exclusions;
2. no workflow has a schedule and the complete partition/evidence-artifact
   contract is absent;
3. both current evidence ledgers, the historical remediation ledger, and their
   machine checker are absent; and
4. `mkdocs.yml` has no anchor-validation severity or Phase 112/Block 13
   navigation.

This test labels its workflow and file assertions as structural delivery
invariants. It is not simulation-behavior or remote-CI evidence.

### Baseline exclusions and inconclusive probes

- The full standard/API/E2E/slow/benchmark execution partitions were not run
  before implementation; collection sets were the suite-accounting baseline.
- The terrain files were not run with newly installed terrain extras; their
  current 21 skips are the red evidence.
- The 129.517695006-second Golan sample already recorded by the accepted
  start-revision specification was not repeated.
- GitHub-hosted workflows cannot run against the uncommitted tree and are not
  claimed.
- The docs anchor-warning negative/config branch was not applied during
  reconnaissance; current strict-build diagnostics establish the red link set.
- Live ASGI/direct API analysis probes were terminated after exceeding 90/10
  seconds and yielded no behavioral endpoint result. They are not counted as
  API false-green evidence.
- The old unknown-unit partial-roster route now fails in the Phase 109 loadout
  preflight and is explicitly excluded from current-red claims.

## Implementation

The implementation is complete and remains in the pre-status-transition state
until the documentation audit and `$postmortem` pass.

### REM-013 - explicit validation delivery

- `scripts/run_pytest_partition.py` owns one fail-closed boundary for the
  standard, slow-only, benchmark-only, slow-benchmark, API, E2E, terrain, and
  benchmark-policy profiles. It records deterministic node manifests, JUnit,
  exact outcome counts, module-affine shards, and typed timeout/error results.
  Missing summaries, empty required selections, skips, partial accounting, and
  timeouts cannot be reported as green.
- `scripts/validate_test_partitions.py` proves the six authoritative Python
  partitions are pairwise disjoint and exactly cover the superset. Terrain is
  an explicit installed-dependency profile rather than a phantom marker.
- Pull-request and main workflows run repository Ruff, standard, full API,
  E2E, terrain, strict docs, paired 73 Easting, and the production-image
  smoke. Weekly/manual delivery owns the expensive marker shards; paired
  Golan is an explicit manual gate. Artifacts upload under `if: always()`.
- While simplifying the delivery path, a production defect was found:
  `SimulationRuntimeFactory` previously required `.git`, although Docker
  excluded it. `stochastic_warfare/build_identity.py` now generates and
  verifies a strict immutable package identity. Git remains authoritative in
  a worktree; an established worktree never falls back after a later Git
  failure. The Docker build requires `SOURCE_REVISION`, generates the identity
  after locked dependency sync, excludes `.git`, runs with `--no-sync`, and
  executes a real prepare/build/tick smoke in CI.
- The first source-frozen execution attempt exposed a second production
  provenance defect: the concurrently executed terrain profile refreshed the
  ignored derived file
  `data/terrain_cache/srtm_b2bf1625727e7435.npz`, causing API analysis
  preparation and construction to see different 1,083-file data digests.
  The API partition therefore failed honestly at 238/239, and the remaining
  stale long runs were interrupted. The authored-data revision now excludes
  only the known `terrain_cache/` derived-output directory (alongside the
  already excluded API store); ignored authored data remains fingerprinted
  and mutation-rejected. A production prepare/build regression changes a
  generated cache between those boundaries and succeeds, while the existing
  ignored-authored-data negative still fails closed.

### REM-014 - behavioral evidence classification

- `scripts/validate_test_evidence.py` derives exact collected node IDs for the
  no-direct and weak-oracle review queues, checks every reviewed disposition,
  and requires the `structural` marker to equal the reviewed
  `structural_only` set. A historical remediation ledger records every named
  Phase 112 red node as repaired, renamed, or removed with its stronger proof.
- The named high-risk tests now assert production outcomes, typed rejection,
  exact state, deterministic events, or negative controls. Imports,
  constructor calls, mocks, source searches, logs, and no-crash runs are not
  used as behavioral closure evidence.
- The Golan and Falklands campaign fixtures share production results instead
  of rerunning identical scenarios, same-seed replay compares exact terminal
  unit/morale/event state, and current recorder/OODA limits are asserted
  honestly rather than labeled historical or AI-quality validation.
- A final slow-partition red exposed a legacy Golan 1,000-iteration test that
  asserted only the configured iteration count. The exact shard timed out
  after 4,200 seconds and 22 completed nodes. That vacuous Golan node and the
  equivalent Falklands count-only node were removed. Two identical 73 Easting
  1,000-iteration computations were consolidated into one test retaining both
  the exact count and the non-tautological confidence-interval convergence
  oracle. The resulting 109-node slow partition is included in the final
  source-frozen closure rerun below.

### REM-017 - one runtime-owned analysis boundary

- `SimulationRuntimeFactory` and its typed session/result boundary now own
  production scenario loading, calibration, force construction, engine
  execution, event capture, metric/vector derivation, provenance, and failure
  classification for sensitivity, comparison, doctrine comparison, MCP, and
  HTTP consumers.
- Unknown metrics, invalid overrides, missing units, empty rosters, failed
  iterations, incomplete batches, and absent vectors fail explicitly rather
  than becoming authoritative zeroes. Every completed statistic is derived
  from its stored raw vector and provenance. Real overrides change real
  production outcomes through each consumer and survive API/database
  round-trips.
- Accepted run/batch cancellation is a publication barrier: no completion,
  frame, terrain, raw vector, metric, or provenance can appear after
  cancellation wins.

### REM-023 and REM-024 - commander and roster integrity

- One canonical commander catalog resolves all 74 shipped references.
  Production construction eagerly covers 1,750 initial and 89 arriving
  commander-bearing units, registers commanders with the OODA engine, applies
  exact assignment/merge rules, and carries assignments through arrival and
  checkpoint restore. Behavioral tests observe commander-dependent decisions
  and outcomes rather than assignment shape alone.
- Unit enums and equipment/loadout construction are validated before any
  roster is published. Initial and arriving force construction is
  transactional: an invalid authored unit fails the scenario instead of
  silently reducing it. The production loader, runtime factory, API, and
  checkpoint boundaries share the typed construction path.

### REM-025 - semantic movement diagnostics

- Runtime-owned diagnostics classify authored intent, eligible movers,
  committed movement, resource blocking, and injected invariant violations.
  Intentional hold/standoff units are not called stuck, while a production
  fuel-depletion control exposes `RESOURCE_BLOCKED`.
- A zero-displacement commit is a hard invariant error. Its injected negative
  control is recorded as a detector proof, not as an ordinary production
  capability.
- Cambrai's four stationary tanks are correctly classified as weapon-range
  standoff. The distinct detection/visibility mismatch remains REM-028 rather
  than being hidden by movement labels.

### REM-022 - documentation-link enforcement

- Forty-nine malformed historical fragment references were repaired.
  `mkdocs.yml` enables anchor diagnostics and strict builds fail on a broken
  fragment.
- `scripts/validate_docs_links.py` owns an isolated invalid-fragment negative
  and a valid-fragment control, so a green real-site build is not the only
  evidence for the failure path.

### REM-026 - paired performance evidence

- The version-2 benchmark policy requires one warm-up per revision, three
  alternating same-host pairs, an authoritative checked-in baseline, exact
  runtime-input and semantic envelopes, median candidate/reference ratio no
  greater than 1.20, and relative range no greater than 0.20 for each
  revision.
- The historical adapter executes the actual reference engine and data at
  `0460ac70be86784bcc6e359ae4202f4bcb938c60`; it does not import candidate
  production construction into the reference. Dirty candidate identity, the
  complete runtime-affecting manifest, raw samples, environment, effective
  inputs, roster/loadout digest, event digest, and an artifact integrity
  digest are recorded.
- Missing, noisy, semantically stale, placeholder, or interrupted artifacts
  fail closed. Battalion, brigade, and flag-impact measurements remain
  `measurement_only` until separately promoted with authoritative baselines.

### REM-027 - typed Space ISR state

- Preflight validates the explicit imagery-fusion constellation selection.
  WorldView-2/3 reference optical constellations provide sourced proof values;
  unsupported broad Keyhole/Lacrosse proxies are not silently claimed.
- Typed, owner-scoped imagery reports use resolvable loader-built targets,
  delayed transactional delivery, deterministic same-epoch ordering, exact
  age-boundary/stale-reactivation semantics, and atomic receipt/track
  association. Failed fusion cannot publish a partial receipt or track.
- Pending reports, receipts, associations, and fusion tracks continue exactly
  through checkpoint restore. This proof uses an explicitly empty ordinary
  fog-of-war topology. Restoration of nonempty ordinary contacts remains
  REM-029, and direct Space ISR injection into ordinary fog-of-war contacts
  remains unsupported.

## Verification

### Exact Python partition proof

The final collection command was:

```text
PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-uv-cache \
  .venv/bin/python scripts/validate_test_partitions.py \
  --output /tmp/sw-phase112-final/partition-audit-v9.json
```

It collected 11,752 nodes with zero collection warnings. The six sets are
pairwise disjoint and their union is exact:

| Partition | Nodes | Execution result | Warnings | Skips |
|---|---:|---|---:|---:|
| standard | 11,299 | 11,299 passed in 784.97 s | 6 | 0 |
| slow-only | 109 | 28 + 27 + 27 + 27 passed | 0 | 0 |
| benchmark-only | 60 | 50 + 7 + 3 passed | 0 | 0 |
| slow-benchmark | 4 | 4 passed in 11.91 s | 0 | 0 |
| API | 239 | 239 passed in 158.64 s | 0 | 0 |
| E2E | 41 | 41 passed in 83.43 s | 0 | 0 |

The slow shard times were 412.71, 680.51, 194.30, and 1,138.53 seconds.
The benchmark-only shard times were 0.83, 0.80, and 0.13 seconds. The standard
warnings are exactly one empty-chart Matplotlib legend warning, four
unrendered-animation warnings, and one `datetime.utcnow()` deprecation
warning. No xfail, xpass, error, failure, or skip occurred.

The exact-union artifact SHA-256 is
`b33f1365fd78be7a7cc0ad66f9f05609408468c50beaedc0b024f1f93ea4e249`.
The standard manifest/JUnit SHA-256 values are
`d002dab880305ea6aa9eea0c1d43ef2c02d3ffd6825c6c804a0fffce48bbf624`
and
`3ed3420033ad0ef49a63ef0a938e3a40a0c5116cae59babc0f41641808bb35b3`.
The API manifest/JUnit values are
`ed5cb4f907b66b56a943f69931080e72a2838d018623f11bc53cfa2c9e53b8b0`
and
`c493b1989765914e5f24fcfd5bb236690ee1cda2477efb9fb6686d6d3a10de1f`.

Every execution used the fail-closed runner form:

```text
.venv/bin/python scripts/run_pytest_partition.py <partition> \
  --manifest <artifact-dir>/manifest.json \
  --junit <artifact-dir>/junit.xml \
  --forbid-skips --timeout-seconds <declared-seconds>
```

Slow and benchmark shards additionally used `--shard-index` and
`--shard-count`. Final slow sharding was module-affine with no split module.
The dependency-installed terrain profile is separate overlap evidence:
97 selected, 97 passed in 4.28 seconds, zero warnings/skips.

The local API run used the temporary `/tmp/sw_uvloop_pytest.py` policy:

```text
PYTHONPATH=/tmp PYTEST_PLUGINS=sw_uvloop_pytest \
  .venv/bin/python scripts/run_pytest_partition.py api ...
```

This qualification is deliberate. On this host, the default selector loop
still hangs during `asyncio.to_thread()` shutdown after the network-driver
change; a 15-second minimal control timed out after printing `before-run`.
Ordinary threads and uvloop complete. The post-push default-policy API
workflow is required remote evidence and is not preclaimed here.

### Focused, lint, data, scenario, frontend, and docs proof

Key focused results were:

- analysis consumers/API/runtime/identity: 114 passed in 51.92 seconds;
- build identity and runtime packaging: 19 passed, 47 deselected in
  0.83 seconds;
- Phase 79 packaging contracts: 34 passed in 0.09 seconds;
- campaign truthfulness and replay: 41 passed in 8.30 seconds;
- final legacy 73 Easting/Golan standard profile: 38 passed, 1 slow
  deselected in 35.67 seconds;
- optimized movement diagnostics: 23 unit tests in 0.38 seconds, 12
  integration tests in 13.44 seconds, 5 evaluator/replay/checkpoint tests in
  7.80 seconds, and 31 runtime-ownership/red tests in 38.97 seconds.

Repository-wide Python lint is clean:

```text
UV_CACHE_DIR=/tmp/sw-uv-cache uv run --no-sync ruff check \
  stochastic_warfare/ api/ tests/ scripts/
# All checks passed!
```

This is the same scope that failed remotely at Phase 108 commit `70e72f5`
with six `F601` duplicate-key findings and two `F541` strings. Phase 109
removed those faults; Phase 112 preserves the full green command. A fresh
post-push lint workflow remains required.

The evidence validator is green with 85 no-direct-oracle nodes,
87 reviewed behavioral exclusions, 926 structural nodes, and 1,013 reviewed
weak-oracle nodes:

```text
PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-uv-cache \
  .venv/bin/python scripts/validate_test_evidence.py
```

Data validation:

```text
PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-uv-cache \
  .venv/bin/python scripts/validate_scenario_data.py
```

- 184 YAML files and all 442 catalog equipment entries validated;
- 0 unmapped and 0 stale equipment mappings;
- 11 constellations and 3 ASAT systems validated;
- 52 scenario YAML files, 8,388/8,388 authored initial units, and 70
  organization groups expanding to 1,128/1,128 units and 1,131/1,131 field
  applications validated;
- 0 errors, 0 warnings, and 1 explicitly declared sensorless civilian entry.

Production scenario evaluation:

```text
PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-uv-cache \
  .venv/bin/python scripts/evaluate_scenarios.py \
  --output /tmp/sw-phase112-final/scenarios-v4/evaluator.json
```

All 46 shipped scenarios completed successfully. Forty-three had no
diagnostic issue. The three declared, non-hidden results were:

- `73_easting`: 360 ticks, 0 casualties, 0 engagement events, 21/71 units
  moved, `ZERO_CASUALTIES` and `ZERO_ENGAGEMENTS`;
- `space_isr_gap`: 360 ticks, 0 casualties/engagements, 0/12 moved,
  `ZERO_ENGAGEMENTS` and `NO_MOVEMENT`; all units are authored
  `DEFENSIVE_HOLD`, while typed ISR behavior is proven separately;
- `time_on_target_validation`: 720 ticks, 1 casualty, 0 engagement events,
  0/3 moved, `NO_MOVEMENT`; the target is destroyed through indirect fire
  while both sides are authored to hold.

The scenario artifact SHA-256 is
`87c4299ed1b870b98796def62920757839a2815d0c1b53dcdfdc1ec924ecfef2`.

Frontend verification:

- `npm test`: 83 files and 440 tests passed in 3.16 seconds; existing React
  diagnostics were warnings only;
- `npm run lint`: 0 errors and 4 explicit warnings (TacticalMap dependency and
  unused-disable warnings, TerrainPreview dependency warning, MapTab rawFrames
  warning);
- `npm run build`: 420 modules built in 27.73 seconds; the existing large
  chunk advisory remained non-failing.

Documentation verification:

```text
UV_CACHE_DIR=/tmp/sw-uv-cache uv run --no-sync \
  .venv/bin/python scripts/validate_docs_links.py
# invalid diagnostic observed; invalid exit 1; valid exit 0

UV_CACHE_DIR=/tmp/sw-uv-cache uv run --no-sync mkdocs build --strict \
  --site-dir /tmp/sw-phase112-final/mkdocs-pretransition
# exit 0 in 2.95 s
```

The strict build has zero broken-fragment failures and only the three
intentional navigation omissions for the calibration template, depth
checklist, and gap audit.

Python compilation and whitespace integrity are also clean:

```text
UV_CACHE_DIR=/tmp/sw-uv-cache uv run --no-sync python -m compileall -q \
  stochastic_warfare api scripts tests
# exit 0; no output

git diff --check
# exit 0; no output
```

Local Docker execution is unavailable:

```text
docker version
# /bin/bash: docker: command not found
# exit 127
```

The build-identity unit/contract proof is green locally; the no-`.git`
production-image prepare/build/tick smoke is therefore an explicit post-push
workflow requirement rather than a claimed local result.

### Paired performance proof

Both comparisons ran sequentially on the idle 32-logical-core/62-GiB host
against exact reference `0460ac70be86784bcc6e359ae4202f4bcb938c60`.
The checked-in baseline document SHA-256 is
`1789b27e5396e061ccb4fa567b1ba98d1b5e922c3af27f21b3313422b9d5e76f`.

The first fresh full Golan closure attempt was correctly red:

```text
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-uv-cache \
  uv run --no-sync python scripts/run_paired_benchmark.py \
  --repo-root /home/csmith/projects/stochastic-warfare \
  --scenario golan_heights \
  --artifact /tmp/sw-phase112-paired-golan-heights-finaldirty-v2.json \
  --allow-dirty-candidate --worker-timeout-seconds 900
```

Reference samples were 126.265228921, 126.577575139, and 127.141582792
seconds. Candidate samples were 151.740261406, 153.891827612, and
153.688049875 seconds. The ratios were 1.201758098, 1.215790613, and
1.208794530; median 1.208794530 exceeded 1.20. Reference/candidate relative
ranges were 0.6923%/1.4000%, so noise did not explain the failure. Runtime
inputs and semantic envelopes were exact. The internal/file SHA-256 values
were
`4bf37f9faf5abfb8914ddab94470e59319eee0dee464954ff8c861afad63a95e`
and
`9f30104c19f2629823a772879d7bda51ccd02502f6790a33f539349e51caa3b1`.
This artifact remains red evidence; it was not replaced or reclassified.

`$profile` pinned the exact reference and candidate 1,000-tick production
paths to CPU 30 and profiled only `SimulationEngine.run()`:

```text
python -c 'import pstats; pstats.Stats(
  "/tmp/sw-phase112-golan-reference-1000.prof"
).strip_dirs().sort_stats("cumulative").print_stats(60)'

python -c 'import pstats; pstats.Stats(
  "/tmp/sw-phase112-golan-candidate-1000.prof"
).strip_dirs().sort_stats("cumulative").print_stats(60)'

python -c 'import pstats; pstats.Stats(
  "/tmp/sw-phase112-golan-candidate-no-record-1000.prof"
).strip_dirs().sort_stats("cumulative").print_stats(60)'

python -c 'import pstats; pstats.Stats(
  "/tmp/sw-phase112-golan-candidate-optimized-1000.prof"
).strip_dirs().sort_stats("cumulative").print_stats(60)'
```

The reference used the paired harness's clean detached `0460ac70` tree.
Reference aggregate profiler time was 36.834327065 seconds over 152,772,805
calls (152,461,899 primitive). The pre-optimization candidate took
43.869110946 seconds over 173,640,336 calls (173,329,430 primitive) and
retained all 290,000 movement observations. `record_batch()` consumed
6.737003710 cumulative seconds; 580,000 position validations consumed
2.272502049 seconds. A diagnosis-only no-record monkeypatch reduced the run to
37.934893067 seconds and 154,114,806 calls, explaining 5.934217879 seconds
and 19,525,530 calls without serving as acceptance evidence.

The production correction keeps mutable accumulation private and materializes
frozen public snapshots only at read/checkpoint boundaries. It stages all
validation, sums, sorting, and orders before non-throwing mutation and retains
the exact bounded 64-entry-per-unit history/checkpoint contract. The optimized
profile took 40.250047250 seconds and 168,129,337 calls:
`record_batch()` fell to 3.125695091 cumulative seconds (-53.6041%) and
position validation to 0.586342260 seconds (-74.1984%). An unprofiled
1,000-tick control took 13.789572532 reference versus 15.787717599 candidate
seconds (ratio 1.144902611), with exact semantic digests, 290,000 cumulative
observations, 18,560 retained entries, 271,440 accounted dropped-prefix
entries, and movement-state SHA-256
`e12076cee895fdee8feb1f89fa02716bf673344a18ede50efd89a55b403d0c21`.

After the correction, both required comparisons were rerun from scratch:

```text
env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-uv-cache \
  uv run --no-sync python scripts/run_paired_benchmark.py \
  --repo-root /home/csmith/projects/stochastic-warfare \
  --scenario 73_easting \
  --artifact /tmp/sw-phase112-paired-73-easting-finaldirty-v3.json \
  --allow-dirty-candidate --worker-timeout-seconds 300

env PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/sw-uv-cache \
  uv run --no-sync python scripts/run_paired_benchmark.py \
  --repo-root /home/csmith/projects/stochastic-warfare \
  --scenario golan_heights \
  --artifact /tmp/sw-phase112-paired-golan-heights-finaldirty-v3.json \
  --allow-dirty-candidate --worker-timeout-seconds 900
```

| Scenario | Reference timed seconds | Candidate timed seconds | Ratios | Median | Reference range | Candidate range | Result |
|---|---|---|---|---:|---:|---:|---|
| 73 Easting | 1.462445, 1.454011, 1.472241 | 1.591757, 1.607940, 1.589228 | 1.088422, 1.105865, 1.079462 | 1.088422 | 1.25% | 1.18% | pass |
| Golan Heights | 127.554513, 126.575378, 127.873808 | 139.072063, 140.376036, 137.912240 | 1.090295, 1.109031, 1.078503 | 1.090295 | 1.02% | 1.77% | pass |

Both medians are at or below 1.20 and all ranges are below 0.20. Reference and
candidate semantic envelopes match exactly:

- 73 Easting: blue/time-expired, 360 ticks/1,800 seconds, 71 units,
  blue `ACTIVE=21`, red `ACTIVE=50`, 30 events, runtime fingerprint
  `060accaec0b76c043ef92fb63360286c2c84d047ac3b2ac6584919a365aadc50`,
  event digest
  `628e33c22fd86c8845f2be87e8ae82ea041d0b8a6253c5760d228de4684d2128`;
- Golan: blue/time-expired, 6,480 ticks/64,800 seconds, 290 units,
  blue `ACTIVE=40`, red `ACTIVE=127/DESTROYED=64/DISABLED=59`, 1,858 events,
  runtime fingerprint
  `c3b609e436c9370a8941eedc41ff0af48e45226f0b69e74f82a1c433c08b8909`,
  event digest
  `434df4752d8df26f1ef67aa4dda4aec9c3ce92a86e093e5f025b85895a7cb736`.

Internal artifact integrity digests are
`6772dc25cadd847cc14679abfb9351760333775f18d59b0e7974e3eff14564c0`
and
`570c8859eea98b24b3cd7719def53c7d91b787e13ece69b0a01acd9b9069d483`.
The complete file SHA-256 values are
`491ef9acd5bbabe9cc187bfa87c6291ced4daf6b91bdccfd8573c02022b57c9b`
and
`a4bf2eb653ad52c0659475c5a80a2f12b9084279984e5c8c4e4d9d7acabd871f`.
After the coherent phase commit, `verify-final` must bind each dirty-candidate
artifact to the final clean committed runtime manifest.

## Applicable reviews

- `$validate-data` passed with the exact catalog/scenario counts above.
- `$scenario`/`$evaluate-scenarios` accepted 43 clean outcomes and retained
  all three declared diagnostics without relabeling them as passes.
- `$validate-conventions` found no unresolved ownership, typed-boundary,
  serialization, logging, or public-API violation.
- `$audit-determinism` found no new stochastic-model change. Exact same-seed
  replay, transactional ordering, checkpoint continuation, paired semantic
  digests, and module-affine deterministic manifests are green. REM-016 and
  REM-029 remain explicit state-restoration boundaries.
- `$profile` rejected the first full Golan gate, localized the excess work to
  per-tick diagnostics snapshot construction, and accepted the optimized
  implementation only after the fresh two-scenario paired gates above.
  Battalion/brigade and flag-impact results remain measurement-only.
- `$simplify` removed duplicate campaign work and vacuous Monte Carlo work,
  consolidated shared production construction, found/fixed the no-`.git`
  image identity defect, and returned CLEAN on the final frozen tree with no
  high/medium production blocker.

## Remaining deficits and exclusions

The nine Phase 112 owners are closed after accepted production-path evidence,
`$cross-doc-audit`, and `$postmortem`. The following are intentionally not
closed:

- REM-016: aggregation subtype/loadout reconstruction;
- REM-020 and REM-021: logistics registration and authority;
- REM-028: weapon-standoff versus detection/visibility mismatch;
- REM-029: restoration of nonempty ordinary fog-of-war contacts;
- REM-030: source-backed production historical outcome envelopes in
  Phase 117;
- REM-031: per-flag semantic/outcome evidence in Phase 118.

Direct Space ISR-to-ordinary-fog-of-war injection is unsupported.
Aggregation-proxy commander/diagnostic lifecycle remains outside the disabled
aggregation contract. Battalion/brigade performance is measurement-only.
Phase 113 has not begun.

## Postmortem

`$postmortem` verdict: **ACCEPT for status transition and the coherent phase
commit**. The broader goal remains active until both dirty-candidate benchmark
artifacts bind to that commit and the required pushed-revision workflows
complete.

- **Scope:** on target. All nine assigned owners—REM-013, REM-014, REM-017,
  REM-022, REM-023, REM-024, REM-025, REM-026, and REM-027—have their accepted
  production or delivery boundary and regression evidence. REM-015 remains
  green. No planned Phase 112 work was dropped.
- **Quality:** high. Invalid inputs reject before authoritative mutation;
  mutable paths stage validation transactionally; deterministic ordering,
  same-seed replay, and checkpoint continuation are explicit; analysis,
  recorder, API, and frontend consumers expose typed vectors and provenance;
  and no owner is closed by an import, constructor, mock, log, search, or
  no-crash assertion.
- **Integration:** fully proven within the declared local boundaries.
  Commander assignments affect OODA decisions and continue through restore;
  force construction cannot publish a partial roster; movement intent and
  resource blocking affect evaluator classifications and persist exactly;
  valid analysis overrides change production metrics through every consumer;
  and typed Space ISR selection, delayed delivery, fusion, receipts, tracks,
  rejection, and checkpoint continuation run through the production runtime.
  Documentation, evidence-ledger, suite-partition, and benchmark workstreams
  have explicit fail-closed negative controls.
- **Test quality:** every fixed defect has a red-producing regression or
  executable invalid control. Count-only duplicate 1,000-run campaign tests
  and repeated full-evaluator fixtures were removed; the retained 73 Easting
  1,000-run test asserts its convergence property. Structural and weak-oracle
  tests remain classified and cannot support behavioral closure claims.
- **Implementation audit:** the complete 256-file phase tree
  (210 modified, 46 added) contains no unrelated user change. Source review and
  the final `$simplify` gate found no high/medium blocker, stub, placeholder,
  dummy value, unconditional success, swallowed production error, incomplete
  serialization, nondeterministic ordering, or unsupported silent fallback.
  `git diff --check` is clean.

The final exact local validation is:

- 11,752 collection nodes with zero collection warnings and an exact disjoint
  union: standard 11,299 passed with the six declared warnings; slow 109,
  benchmark 60, slow-benchmark 4, API 239, and E2E 41 all passed with zero
  warnings/skips; the overlapping terrain profile passed 97;
- all 46 production scenarios completed: 43 clean and exactly the three
  declared diagnostic outcomes; data validation covered 184 unit YAML files,
  442/442 mappings, 11 constellations, 3 ASAT systems, 52 scenarios,
  8,388/8,388 initial units, and 1,128/1,128 expanded units with 0 errors,
  0 warnings, and 1 explicit sensorless classification;
- the evidence inventory remained 85 no-direct-oracle nodes, 87 reviewed
  behavioral exclusions, 926 structural nodes, and 1,013 reviewed weak-oracle
  nodes;
- frontend 83 files/440 tests, lint 0 errors/4 declared warnings, and the
  420-module production build passed;
- repository-wide Ruff, Python compilation, link negative/positive controls,
  strict MkDocs, and whitespace integrity passed; and
- the first full Golan comparison failed honestly at median ratio
  1.208794530, profiling located and corrected diagnostics allocation work,
  then fresh 73 Easting/Golan gates passed at 1.088421749/1.090295117 with
  exact semantic envelopes and retained artifact digests.

`$cross-doc-audit` returned **READY** across all ten audit areas after it found
and required REM-030 supersession notices on the historical Phase 10 and
Phase 73 devlogs. Its final link control passed, strict MkDocs built in 2.60
seconds with only the three declared nav omissions, and the stale-evidence
search found no v8/v3/11,751/old-pass residue.

Unplanned but in-scope integrity repairs were the immutable no-`.git` build
identity, exclusion of only derived `terrain_cache/` output from authoritative
data provenance, removal/consolidation of vacuous expensive tests, and the
profile-driven movement-diagnostics allocation correction. They preserve the
accepted public schemas and semantic outcomes.

No new postmortem deficit was found. REM-016, REM-020, REM-021, REM-028,
REM-029, REM-030, and REM-031 remain explicit. Local default-selector API
shutdown is still qualified by the recorded uvloop run, Docker is unavailable
locally, and the production image therefore has no local no-`.git` smoke
claim. Required post-commit actions are both `verify-final` bindings, push,
and remote default-policy API, repository-wide Ruff, standard/E2E/terrain,
documentation, paired 73 Easting, and no-`.git` image smoke verification.
