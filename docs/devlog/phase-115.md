# Phase 115 - Sensing-Aware Tactical Standoff

**Status:** Complete

**Started:** 2026-08-01

**Completed:** 2026-08-02

## Why this phase exists

REM-028 records a production movement branch that can stop an advancing unit
at 80 percent of a live weapon's catalog maximum without a usable observation,
current owner-side contact, effective-range/fire-control solution, or ensuing
engagement. Phase 115 owns the replacement contract in
[`sensing-aware-tactical-standoff.md`](../specs/sensing-aware-tactical-standoff.md).

## Start gate

Phase 114 passed `$postmortem`, was committed and pushed as
`f057923e3b13aabe2f0994e03063e6692ceef0ce`, and all five hosted workflows for
that exact commit completed successfully before Phase 115 began.

Hosted `Tests` run `30719385031` completed in 22 minutes 44 seconds with all
six jobs and every evidence upload successful:

- terrain dependency profile: 97 selected / 97 passed in 7.34 seconds, zero
  failures, errors, skips, warnings, xfails, or xpasses;
- standard: 11,445 collected and passed in 1,311.31 seconds, 175 deselected,
  zero failures/errors/skips/xfails/xpasses, and six classified warnings (one
  empty-data chart legend, four unrendered matplotlib animations, and one
  `datetime.utcnow()` deprecation);
- frontend: 83 files / 440 tests passed in 32.00 seconds;
- E2E: 41 selected / 41 passed in 119.08 seconds with no warnings or skips;
- API: 242 selected / 242 passed in 238.43 seconds with no warnings or skips;
- exact partition audit: 11,903 pairwise-disjoint nodes = 11,445 standard +
  109 slow-only + 62 benchmark-only + 4 slow-benchmark + 242 API + 41 E2E,
  with zero collection warnings.

The uploaded standard artifact was ID `8824603560`, 597,395 bytes, SHA-256
`ab55f6a3086b72461d358ed9ab481c252954456d85cb2d28330f7242a9c2e97a`.
The partition-audit artifact was ID `8824385450`, 302,111 bytes, SHA-256
`adeb14a0b34eb6cd9cf596b6162844a572548646027402d6ffc9b076408888d5`.
All Python jobs reported advisory uv cache-service failures and the hosted
runner reported the announced Node 20-to-24 action-runtime transition; tests,
audits, and artifact uploads were unaffected.

Hosted auxiliary evidence for the same commit:

- Lint run `30719385060`: repository-wide Ruff passed; frontend ESLint had
  zero errors and four existing warnings;
- Documentation run `30719385033`: strict MkDocs and deployment passed;
- Docker Build run `30719385058`: immutable production build/smoke passed;
- Paired production benchmarks run `30719385046`: 61 policy/contract tests
  passed and the clean-commit 73 Easting paired verdict passed. The paired
  artifact SHA-256 was
  `dc8eae808828bfd7796fba13c01f7e261b151ac0a9af992bf934b0faaa4a2742`;
  clean-tree verification SHA-256 was
  `ea7169b2144aa67879476b83d6d1372b0d94c1388e0d9052ebbd46ce9482994d`.

The synchronized Phase 115 start state was:

```text
git status --short --branch
# ## main...origin/main

git rev-parse HEAD
git rev-parse origin/main
# f057923e3b13aabe2f0994e03063e6692ceef0ce
# f057923e3b13aabe2f0994e03063e6692ceef0ce

git pull --ff-only origin main
# From https://github.com/clay-m-smith/stochastic-warfare
#  * branch            main       -> FETCH_HEAD
# Already up to date.
```

`CODEX.md`, `AGENTS.md`, Block 13, REM-028, the Phase 114 closure evidence,
the movement/detection/loadout/checkpoint architecture and tests, and the
applicable `$spec`, `$research-military`, and `$design-review` instructions
were read before implementation.

## Machine envelope

```text
nproc
# 32

lscpu | rg 'Model name|Socket\(s\)|Core\(s\) per socket|Thread\(s\) per core|^CPU\(s\):'
# CPU(s): 32
# Model name: AMD RYZEN AI MAX+ 395 w/ Radeon 8060S
# Thread(s) per core: 2
# Core(s) per socket: 16
# Socket(s): 1

free -h
# Mem: 62 GiB / 67,187,146,752 bytes total;
#      47 GiB / 50,536,620,032 bytes available at the final check
# Swap: 7.8 GiB total with negligible use

taskset -pc $$
# current affinity list: 0-31
```

The memory envelope is safe for the repository's disjoint validation
partitions. Pytest itself remains serial because the repository has no
validated xdist contract. Unrelated user training processes remain out of
scope and will not be stopped or modified; local timing will be qualified if
contention is present, with the clean hosted paired gate retained as the
authoritative regression result.

## Specification, research, and design gate

`$spec` traced the current split behavior: movement chooses the nearest
ground-truth enemy and returns `0.8 * max_range_m` from live domain/ammunition
state, while engagement separately applies visibility, sensing, environment,
contact-like, and weapon selection rules. The evaluator independently
recomputes the same legacy range, so changing only `BattleManager` would leave
public diagnostics stale.

The provisional contract introduces one default-on strict calibration flag,
immutable mapping-owned weapon/sensor role bindings, and one typed targeting
picture resolved after FOW and before movement. Movement and engagement must
consume that same picture. Explicitly disabling automatic standoff yields a
zero authorized range rather than restoring the defective catalog maximum.
The contract also retains REM-029 honestly: Phase 115 persists/exposes its own
decisions and proves exact no-FOW continuation, but does not claim fresh
continuation from ordinary nonempty `SideWorldView.contacts` that format 114
deliberately discards.

Tier 1 doctrine supports the range relationship but not a new numeric tuning
constant. USMC MCTP 3-01C page 1-6 distinguishes maximum, effective, and
visible/usable direct-fire range; FM 3-21.8 paragraph 2-63 requires detection,
identification, and location sufficient for weapon employment; Navy direct-
fire doctrine and official search-versus-integrated-weapon-system descriptions
support preserving a distinct fire-control role. Exact citations and
limitations are in the specification. No source result is implementation
evidence.

Independent read-only traces identified design blockers that the formal
`$design-review` must resolve before implementation:

- environment-dependent acquisition must have one owner and no duplicate
  DETECTION draw;
- live mapping roles currently disappear into parallel resolution metadata;
- WW1 binoculars, naval rangefinders, and artillery sights are incorrectly
  collapsed into one observation role;
- FOW currently omits several real environment inputs and cannot restore its
  ordinary contacts;
- indirect/offboard weapons need explicit non-fallback policy; and
- no-contact force closure must not be mislabeled as a target contact.

The formal design verdict and any resulting specification revisions will be
recorded here. Its first verdict was **NEEDS REVISION (design-only)**, before
any production implementation began. The six blocking findings were:

1. `get_effective_range()` silently synthesizes the same unsourced 80-percent
   multiplier when the authored field is absent;
2. target-level FOW reporting-sensor IDs do not prove which unit/attachment
   made the detection;
3. FOW currently records epoch seconds while checkpoint validation compares
   scenario elapsed seconds;
4. fire-control compatibility was described but not exhaustive over every
   weapon and sensor modeled-role enum;
5. a restored positive FOW decision could not remain consumable after REM-029
   intentionally discarded the contact; and
6. the failure baseline and publication transaction were not declared.

The revised contract addresses each blocker with authored-versus-legacy range
provenance, an observer/attachment detection witness emitted by the existing
canonical draw, exact scenario-elapsed contact time, total enum policy tables,
historical/non-consumable restored FOW decisions, and a post-FOW atomic picture
boundary. Re-review accepted those corrections and found two further
architecture blockers: FOW would still update once per active battle rather
than once per engine interval, and generic sensor roles lacked a total allowed-
shooter-domain/FOW-direct-visual policy. The next revision moves environment,
concealment, and FOW preparation ahead of the engine's canonical battle loop;
keys every RNG-free decision by `(engine_tick, battle_id, shooter_id)` so open
REM-035 membership cannot overwrite one unit's evidence; enumerates allowed
shooter domains for all 38 sensor roles; and permits FOW `DIRECT_VISUAL` only
from a same-shooter current visual witness without another draw.

The same review rejected name-derived promotion of the five WW1 optical items.
The contract now cites equipment-specific primary-manual/USNI/ZEISS/NavWeaps
and museum evidence for the Barr & Stroud, Zeiss, No. 7, and panoramic-sight
role classes while retaining the 3,000 m cap as an explicitly non-historical
functional analogue. Any mapping implementation must carry those sources;
Field Binoculars remains observation-only.

The final design pass found three narrower policy gaps: air-to-ground sensor
roles were referenced imprecisely; an artillery sight role could have directed
an unrelated organic weapon on a mixed loadout; and the phrase “combat always
obeys” could have pulled indirect, bomb, torpedo, ASW, grenade, or melee paths
under the wrong owner. The contract now names every air-to-ground role and
reserves bombsights; requires each sensor mapping to publish allowed weapon
roles and the builder to resolve exact compatible weapon source indexes (with
No. 7/Panoramic restricted to `FIELD_ARTILLERY`); and scopes the shared gate to
ordinary direct engagement while explicitly preserving every separate action
owner. Mixed-loadout and excluded-role production controls were added to the
proof plan. The original reviewer completed a delta re-review and returned
**APPROVED** with no remaining design blocker. Its nonblocking implementation
note requires duplicate-name/role and reordered initial, reinforcement, and
checkpoint controls so source identity cannot pass by list-position
coincidence. This approval opens behavioral production-red work only; it is not
implementation or phase-completion evidence.

The exact read-only catalog inventory at the phase base found 244 source weapon
YAML definitions: 97 explicitly author `effective_range_m` and 147 omit it.
There are 242 distinct IDs because two IDs are intentional cross-era
duplicates. The production mapping registry contains 272 weapon records over
205 target IDs; 96 targets have authored ranges and 109 use the legacy fallback.
All 109 fallback targets have positive maximum range, so an unqualified call to
`get_effective_range()` turns every one into a positive 80-percent value.
`m240_762mm` and `m2hb_50cal` each map under three roles, proving role must be
attachment-owned. All 35 role enums are now classified, including currently
unmapped `AUTOMATIC_GRENADE_LAUNCHER`. The inventory command exited 0 without
warnings; its complete deterministic script and per-role counts will be kept
with final validation evidence.

## Baseline and production red evidence

The accepted contract opened this gate. The first timing-wrapper attempt used
`/usr/bin/time`, which is not installed in the execution image and exited 127
without starting pytest:

```text
/usr/bin/time -p env PYTHONDONTWRITEBYTECODE=1 \
  UV_CACHE_DIR=/tmp/sw-phase115-focused-uv-cache uv run --no-sync pytest ...
# /bin/bash: line 1: /usr/bin/time: No such file or directory
```

The exact corrected unchanged baseline was:

```text
time -p env PYTHONDONTWRITEBYTECODE=1 \
  UV_CACHE_DIR=/tmp/sw-phase115-focused-uv-cache \
  uv run --no-sync pytest -q \
  tests/unit/simulation/test_battle_pure_functions.py \
  tests/integration/test_phase_109_battle_sensor_domains.py \
  tests/integration/test_phase112_runtime_red.py \
  tests/integration/test_phase112_movement_diagnostics.py \
  tests/unit/test_phase112_movement_diagnostics.py \
  tests/validation/test_phase112_evaluator_contract.py \
  tests/integration/test_phase_109_weapon_multiplicity.py \
  tests/validation/test_phase_30_scenarios.py
# 427 passed in 78.58s (0:01:18)
# real 79.09
# user 96.39
# sys 5.07
```

Exit was 0 with zero warnings, failures, errors, skips, xfails, or xpasses.
This proves the phase-start affected contract is internally green; it does not
prove REM-028 is corrected. Catalog-backed Cambrai/Jutland evaluator captures
and the new behavioral red are running separately.

Cambrai seed 42 used the production evaluator exactly as follows:

```text
env PYTHONDONTWRITEBYTECODE=1 \
  UV_CACHE_DIR=/tmp/sw-phase115-cambrai-uv-cache \
  uv run --no-sync python scripts/evaluate_scenarios.py \
  --scenario cambrai --seed 42 \
  --output /tmp/sw-phase115-cambrai-42-red.json
# Found 1 scenarios to evaluate
# [1/1] Running cambrai... OK (156 ticks, 2 casualties, 0.8s)
# TOTALS: 1 scenarios — 1 OK, 0 with issues
```

Exit was 0 in 1.312 tool seconds with no warning or error. The 15,918-byte
artifact SHA-256 is
`517a1a913f38a3bf4665b8e77ab141bc220890c02fa11abeae2ed0fbe881043d`.
It records 780 logical seconds, British `force_destroyed` victory, 190 events,
two German surrenders, zero engagements/weapon-fire/damage/destruction events,
three movers, and seven unmoved units. The four Mark IVs remain exactly at
their initial positions for all 156 observations, each classified
`ENGINE_WEAPON_STANDOFF`; the three British infantry units move exactly
1,169.8 m each.

Each Mark IV's initial nearest enemy is 3,500.357, 3,500.357, 3,517.456, or
3,559.846 m away, outside its sole operational `binoculars_ww1` visual sensor
and scenario visibility, both 3,000 m. Its QF 6-pounder authors physical maximum
6,675 m and effective range 1,000 m, yet production movement authorizes
`0.8 * 6,675 = 5,340 m` from ground-truth distance. All four therefore hold
blind from tick 1. Their QF ammunition remains exactly 207 AP + 207 HE and the
Lewis gun 47 rounds, with both weapons at zero rounds fired. This is the exact
catalog-backed behavioral red for REM-028, not merely a source assertion.

Jutland seed 42 used:

```text
env PYTHONDONTWRITEBYTECODE=1 \
  UV_CACHE_DIR=/tmp/sw-phase115-jutland-uv-cache \
  uv run --no-sync python scripts/evaluate_scenarios.py \
  --scenario jutland --seed 42 \
  --output /tmp/sw-phase115-jutland-42-red.json
# [1/1] Running jutland... OK (569 ticks, 10 casualties, 2.0s)
# 29/29 moved; 0/29 unmoved; 15 engagements; no issues
```

Exit was 0 in 2.574 tool seconds with no warning/stderr. The 45,215-byte
artifact SHA-256 is
`f9d172002fee770aa39a773bc003ceb76acafc66b98b23fad2777ec741d64516`.
It records 7,620 logical seconds, British `force_destroyed` victory, 188 events,
10 non-active German units, 15 weapon-fire events, 14 ammo-expended events,
14 ordinary engagement events, and one naval engagement. No damage,
destruction, sunk, killed, or downed event was recorded.

All 13 capital ships entered engine standoff. Five Iron Dukes each move for 32
ticks then hold 537 times at a best catalog range of 21,780 m; three Invincibles
each move for 8 then hold 561 times at 21,700 m; the five Königs total 205
`MOVED`, 2,064 `ENGINE_WEAPON_STANDOFF`, and 576 `INACTIVE`. Capital totals are
6,432 blind holds, 389 moves, and 576 inactive decisions. The only identified
engagement weapon is `qf_4in_mk_iv` in 14 destroyer engagements; every combat-
attributed unit and the single naval engagement are G-class destroyers. No
Iron Duke, Invincible, König, or capital gun appears. Nearest final opposing-
capital separation is 23,961.250 m.

The production factory separately loads each surface ship with one condition-
1.0 `binoculars_ww1` visual instance at exactly 3,000 m; the Barr & Stroud and
Zeiss items both currently appear as `WW1 Field Binoculars`. Scenario visibility
is 8,000 m. Whole-run reasons are 2,365 `MOVED`, 12,641
`ENGINE_WEAPON_STANDOFF`, 1,385 `INACTIVE`, and 110 `RESOURCE_BLOCKED`, with
all other reasons zero. This is the second catalog-backed red: 21.7 km movement
authority despite only a 3 km mapped optical envelope and no capital fire.

The retained behavioral red is
`tests/integration/test_phase115_sensing_standoff_red.py`. It uses
`SimulationRuntimeFactory.prepare_config -> PreparedScenario.build ->
RuntimeSession.step` with a catalog Mark IV and German target at exactly 5,000
m initial separation. It first proves the loaded 6,675 m physical gun range,
1,000 m authored effective range, and 3,000 m binocular envelope, then requires
the tank to advance because the target is outside a current usable solution.
Fresh reproduction:

```text
env PYTHONDONTWRITEBYTECODE=1 \
  UV_CACHE_DIR=/tmp/sw-phase115-red-verify-uv-cache \
  uv run --no-sync pytest -q \
  tests/integration/test_phase115_sensing_standoff_red.py
# FAILED ...::test_mark_iv_advances_outside_current_sensing_and_effective_envelope
# AssertionError: ENGINE_WEAPON_STANDOFF is not MOVED
# 1 failed in 1.12s
```

This is an expected pre-implementation exit 1 and fails on production behavior
at engine tick 1/battle `battle_0000`; it is not an import, missing-field,
mock, constructor, or private-helper red. A disabled-flag red is intentionally
deferred until the strict field exists, because schema absence would not prove
runtime wiring.

## Production implementation

Phase 115 replaces the legacy movement-only calculation with one runtime-owned
transaction rather than adding another validation helper:

- `CalibrationSchema.enable_sensing_aware_standoff` is a strict, default-on
  boolean. Explicit `false` authorizes exactly zero automatic tactical
  standoff and never restores the 80-percent catalog fallback.
- `TacticalTargetingRuntime` owns a `TargetingInterval`, immutable
  `TacticalTargetingPicture` values, per-shooter decisions, and post-movement
  engagement revalidations. `SimulationContext`, `SimulationEngine`, and
  `BattleManager` retain the exact same owner object and reject replacement.
- the engine calls `BattleManager.prepare_tactical_interval()` once before the
  canonical active-battle loop. It updates environment-dependent concealment
  and FOW once, stages all complete RNG-free pictures, and then publishes the
  interval before any movement or autonomous combat;
- movement and ordinary direct engagement consume the same decision keyed by
  `(engine_tick, battle_id, shooter_id)`. The decision distinguishes physical
  maximum range, authored versus legacy-derived effective-range evidence,
  local sensing, scenario/weather visibility, contact and observer witness,
  exact fire-control source, disposition, and authorized standoff. Engagement
  revalidation records an explicit failure rather than switching to hidden
  ground-truth evidence;
- optical direct visual requires a current same-shooter visual witness. Search,
  observation-only, incompatible-domain, stale, unavailable, depleted, and
  unsupported-role cases are typed non-authorizing results. Sensor/environment
  range, altitude, LOS, visibility, and observer modifiers use finite
  saturating arithmetic and one per-interval evidence cache;
- the Phase 109 loadout boundary now carries canonical exact source indexes,
  total modeled roles, allowed domains, and exact compatible weapon indexes
  through initial, reinforcement, and checkpoint construction. The builder
  remains the only production construction owner;
- routed field artillery, mortar, rocket artillery, bomb, torpedo, and ASW
  action owners remain unchanged. Grenade and melee can retain close direct
  engagement but contribute zero automatic standoff;
- checkpoint format 115 persists the strict targeting owner, interval,
  memberships, pictures, decisions, revalidations, enablement, default
  visibility, and exact loadout bindings. Restore stages cross-owner
  clock/battle/roster/loadout/diagnostic invariants before mutation. No-FOW
  continuation is exact; a restored FOW-backed decision is historical and
  non-consumable because REM-029 still owns ordinary nonempty-contact restore;
  and
- movement diagnostics, the scenario evaluator, replay, stored API frames, and
  frontend schemas consume the same decision evidence. Stored frames carry
  paired exact `PRIVILEGED_ENGINE` and opaque `SIDE_FOW` projections.

This implementation is production code exercised through
`SimulationRuntimeFactory -> PreparedScenario.build -> RuntimeSession.step`;
no capability row below relies on an import, constructor, mock, source search,
log line, or no-crash run.

## Production defect found during catalog evaluation

The first complete-catalog attempt reached Salamis and failed strictly:

```text
ValueError: fire-control source is incompatible with weapon role
```

The mapping profile correctly narrows the shared ancient projectile/melee
roles to a naval target, but decision validation had consulted only each
role's default ground profile. The repair adds the total
`weapon_role_supports_target_domain()` policy over the already validated role
profiles and makes `fire_control_source_is_compatible()` consume it. The exact
attached weapon definition remains the final target-domain gate, so this does
not widen authored weapon capability.

Focused policy controls accept `ANCIENT_PROJECTILE` and `MELEE` against NAVAL
targets and reject the same roles against AERIAL targets. A strict factory/run
Salamis regression observes a live NAVAL-to-NAVAL
`ANCIENT_PROJECTILE`/`DIRECT_VISUAL` decision and 65 recorded `javelin`
weapon-fire events:

```text
env PYTHONDONTWRITEBYTECODE=1 \
  UV_CACHE_DIR=/tmp/sw-phase115-salamis-uv-cache \
  uv run --no-sync pytest -q \
  tests/integration/test_phase115_sensing_standoff_red.py \
  -k salamis
# 1 passed in 5.37s

env PYTHONDONTWRITEBYTECODE=1 \
  UV_CACHE_DIR=/tmp/sw-phase115-salamis-uv-cache \
  uv run --no-sync python scripts/evaluate_scenarios.py \
  --scenario salamis --seed 42 \
  --output /tmp/sw-phase115-salamis-42-final.json --no-details
# OK (53 ticks, 4 casualties)
# 26/26 moved; 69 engagement records; 65 javelin weapon-fire events
# TOTALS: 1 scenarios — 1 OK, 0 with issues
```

The first version of the regression incorrectly treated recorder snapshots as
live `EngagementEvent` objects. That was a test-only failure; the assertion now
uses the public recorded `event_type` and `data["weapon_id"]` fields.

## Closure defects found and repaired

Fresh production integration found three additional integrity defects before
the implementation was frozen. None was waived as unrelated merely because it
predated the Phase 115 targeting owner.

First, the real Phase 109 EA-18G negative control repeatedly submitted a
coincident sensor detection to an existing fusion track. The legacy
`range_m * 0.05` uncertainty became exactly zero, so the next conventional
innovation covariance was singular. `$research-models` reviewed Kalman's 1960
paper, NASA's discrete/Joseph-form equations, and Yaz and Yaz's treatment of
noise-free measurements. The production boundary now rejects direct reports
with zero, negative, or non-finite uncertainty and adapts sensor detections
with `max(range_m * 0.05, 1.0)`. The one-metre value is explicitly a generic
numerical/model lower bound, not sourced sensor accuracy. Direct-zero and
repeated-coincident controls prove rejection versus stable reuse of
`fow-track-0001`, two hits, and finite positive covariance. The original
EA-18G production negative is green again. REM-044 / Phase 131 separately owns
sourced range/bearing covariance and a detached atomic predict/update
transaction; Phase 115 does not silently add estimator prediction or claim
historical sensor error.

Second, stable FOW reuse exposed a non-atomic gated replacement path. The
repair creates and installs the next side-local ordinal under the fusion lock,
advances its checkpointed counter, and only then removes the predecessor. A
failed create leaves the predecessor, counter, and live `SideWorldView`
contact unchanged; it cannot leave an orphan tentative track. Root-only
`side_fow_associations` bind privileged target IDs to opaque side-local tracks,
while one typed stored-SIDE_FOW decoder serves API and replay. Missing or
same-side-rebound associations fail closed, and neither the association nor a
privileged target ID appears in side-safe payloads or frontend state.

The exact synchronous transaction/exposure selection was:

```text
uv run --no-sync pytest -q \
  tests/unit/test_intel_fusion.py \
  tests/unit/test_phase115_fow_witness.py \
  tests/unit/simulation/test_targeting_exposure.py \
  tests/unit/test_phase115_replay_scope.py \
  tests/api/test_phase115_targeting_exposure.py \
  -m 'not asyncio'
# 92 passed, 4 deselected in 1.13s

uv run --no-sync pytest -q \
  tests/api/test_phase115_targeting_exposure.py::\
test_router_returns_paired_scopes_without_recomputation
# 1 passed in 0.04s
```

Four FastMCP/client-fixture async nodes remain excluded from that selection
because the hosted `asyncio.to_thread` fixture can stall after the direct
router has completed. The direct async production router node above passed;
the exclusion is environment qualification, not an API capability waiver.

Third, the new targeting topology made the legacy optional aggregation owner
unsafe. The accepted narrow REM-016 compatibility boundary supports only
exact base `Unit` instances with no equipment, supplies, unsupported
roster-indexed owners, or nonempty runtime loadouts. It now atomically updates
the typed loadout and targeting registries, preserves constituent order,
validates exact configuration/owner identity, and restores active archives
only when aggregation is enabled. Absent, disabled, forged, subclass-forged,
configuration-mismatched, duplicate-roster, wrong-side-bucket, and versionless
same-ID semantic-drift controls all reject before clock, RNG, live object, or
checkpoint mutation. This is not closure of REM-016's broader subtype/loadout
reconstruction scope.

The final read-only production review then found two closure blockers rather
than accepting the earlier deterministic and aggregation selections at face
value. First, configurable FOW managers with an `IdentificationEngine` routed
side-local detection draws through the supplied per-side RNG but still drew
misclassification from the identification engine's shared stream. The exact
RNG-owner red was:

```text
.venv/bin/pytest -q \
  tests/unit/test_phase115_fow_witness.py::\
test_side_local_rng_owns_detection_and_identification_draws
# 1 failed in 0.28s: the shared identification RNG advanced
```

`IdentificationEngine.classify_from_detection()` now accepts and validates an
optional caller-owned generator, and `FogOfWarManager.update()` passes the same
side-local stream used by the canonical detection draw. Ordinary callers with
no override retain the engine's checkpointed stream. This removes the shared
parallel mutation without adding or deleting a stochastic decision.

Second, the narrow REM-016 aggregation preflight used `isinstance()` for the
targeting owner and then invoked virtual stage/replace/commit methods. A
subclass could therefore bypass the claimed exact-owner transaction. The
forged-owner red failed with the subclass's injected post-mutation
`RuntimeError` instead of rejecting at preflight:

```text
.venv/bin/pytest -q \
  tests/integration/test_phase113_aggregation.py::\
test_targeting_runtime_subclass_rejects_before_every_owner_mutation
# 1 failed in 0.56s
```

The preflight now requires `type(owner) is TacticalTargetingRuntime`. The
combined repair selection passed 76 tests in 2.40 seconds:

```text
.venv/bin/pytest -q \
  tests/integration/test_phase113_aggregation.py \
  tests/unit/test_phase115_fow_witness.py \
  tests/unit/test_identification.py \
  tests/unit/test_phase89_parallel_detection.py
# 76 passed in 2.40s
```

Both commands exited with the stated red/green status and emitted no warnings,
skips, xfails, or xpasses. The existing late-mapping-failure aggregation
control continues to prove rollback of exact production owners; the forged
subclass is now rejected before any owner mutation.

The same review then rejected the coordinator's claimed multi-battle atomic
publication. It prepared the new interval and published one picture at a time,
so a fault while resolving battle two left battle one's picture and the new
published prefix committed. The two-battle production red proved the partial
state directly:

```text
.venv/bin/pytest -q \
  tests/integration/test_phase115_targeting_controls.py::\
test_multibattle_picture_fault_rejects_without_publishing_a_prefix
# 1 failed in 1.60s: prepared interval and battle-atomic-0 remained published
```

`TacticalTargetingRuntime.stage_interval()` now validates immutable interval
topology without mutation. The coordinator resolves every battle picture
against that staged value, and `publish_interval()` validates the complete
canonical tuple before one swap of interval, picture set, published IDs, and
revalidation ledger. A later simplification review removed the incremental
`prepare_interval()` / `publish_picture()` interface and the battle-local
compatibility publisher entirely: direct fixtures now use the same complete
transaction, and direct battle execution rejects an absent prepublished
picture before changing battle counters. The exact red passed in 1.50 seconds,
and all 49 targeting-runtime unit controls passed in 0.34 seconds. After the
runtime registration topology joined that same immutable snapshot, the
source-current reruns passed the exact red in 1.51 seconds and all 49 controls
in 0.36 seconds. Incomplete, forged, prefix, and reversed publications reject
with exact state equality.

An immediate combined runtime/integration selection reached 66 passes before
one provenance guard rejected because the benchmark agent changed the dirty
worktree between `PreparedScenario.prepare()` and `build()`; it reported
`1 failed, 66 passed in 23.25s`. That concurrent-edit result is not counted as
a behavioral failure or a suite pass. The source-frozen rerun below owns the
final disposition.

The next read-only review found that stored `SIDE_FOW` values were only
key/track-associated with privileged evidence. An internally coherent public
standoff or jointly changed decision/outcome logical time therefore decoded
successfully. It also found that a side decision retained the all-sides picture
ordinal and disclosed how many hidden opposing shooters sorted before it. The
behavioral reds were:

```text
.venv/bin/pytest -q \
  tests/api/test_phase115_targeting_exposure.py::\
test_stored_side_projection_rejects_semantic_drift_from_privileged_evidence
# 2 failed in 0.07s: both corruptions were accepted

.venv/bin/pytest -q \
  tests/unit/simulation/test_targeting_exposure.py::\
test_side_picture_ordinals_do_not_reveal_hidden_opposing_shooters
# 1 failed in 0.30s: the red-side projection retained global ordinal 1
```

The bundle now derives the complete expected side decision and outcome from
the privileged record plus its root-only association and requires exact object
equality. Public decision ordinals restart at zero per battle and viewer side,
with contiguous canonical validation. The same commands passed 2 tests in
0.02 seconds and 1 test in 0.25 seconds respectively; the complete exposure
unit file passed 23 tests in 0.28 seconds with no warnings.

The aggregation compatibility fence was also an incomplete enumeration. A
real populated `RoeEngine._unit_levels` survived a roster replacement, and the
same defect class applied to CBRN, planning, detection, adaptation, ECCM,
SIGINT, carrier, indirect-fire, missile, and further context owners. The red
was:

```text
.venv/bin/pytest -q \
  tests/integration/test_phase113_aggregation.py::\
test_aggregation_rejects_populated_roe_owner_before_mutation
# 1 failed in 0.55s: aggregation completed instead of rejecting
```

Production `SimulationContext._checkpoint_engines()` is now the authoritative
fail-closed registry: only the explicitly coordinated aggregation,
morale/rout, tactical-targeting, and empty-loadout topology may pass. Minimal
fixtures conservatively inspect all `*_engine` attributes plus the legacy
non-engine owner names. The exact red passed in 0.47 seconds, the complete
aggregation integration file passed 13 tests in 1.57 seconds, and the combined
aggregation/exposure unit selection passed 36 tests in 1.54 seconds.

Finally, targetless decisions stored `visibility_bound_m=0.0` and restore
validated live visibility only inside the target-present branch. Coherently
changing every stored copy by one metre was accepted:

```text
.venv/bin/pytest -q \
  tests/integration/test_phase115_targeting_checkpoint.py::\
test_targetless_picture_visibility_corruption_rejects_atomically
# 1 failed in 2.34s: DID NOT RAISE
```

The production targetless decision now records the actual interval visibility,
reusing the already resolved value on the no-contact path. Restore compares a
checkpoint-current latest picture, including a targetless one, with the staged
environment. An older retained latest picture and retained movement history
preserve the visibility recorded for their own interval while still undergoing
schema, topology, attachment, catalog, and internal optical-bound validation;
they do not claim the checkpoint-current environment. The exact red passed in
2.28 seconds; the then-complete Phase 115 targeting-checkpoint file passed 50
tests in 60.98 seconds with no warnings, skips, xfails, or xpasses.

A later Debecka slow-partition replay exercised exactly that distinction. Its
latest picture was captured at tick 687 / 3,435 seconds under 10,000 m
visibility and retained through a checkpoint at tick 1,500 / 7,500 seconds
after heavy rain reduced current visibility to 2,000 m. Comparing the older
picture to current weather incorrectly rejected seven checkpoint/snapshot
nodes. `_targeting_interval_is_current()` now fails closed on tick/time
half-matches and applies the live/staged weather comparison only when both
coordinates identify the checkpoint-current interval. A new fresh-restore
control retains a tick-1 / 5-second 3,000 m picture across a tick-2 / 305-second
200 m fog checkpoint and proves exact history and next-step continuation. The
focused current/historical controls passed 4 tests in 5.91 seconds, and the
complete checkpoint module passed 51 tests in 48.07 seconds with no warnings,
skips, xfails, or xpasses. The exact Debecka engagement snapshot node passed in
43.80 seconds.

Catalog evaluation also proved that the INS Hanit vignette's C-802 battery had
only a search-radar proxy and therefore could not legitimately fire. Its unit
now carries a separately named `Coastal Missile Targeting Network`, modeled as
a generic `FIRE_CONTROL_RADAR` compatible only with
`ANTI_SHIP_MISSILE`. ONI, USNI, and NAVSEA sources support the system/network
and search-versus-fire-control distinction; the retained 60 km/360-degree
parameters remain an explicit functional analogue, not a historical accuracy
claim. The final seed-42 vignette artifact
`/tmp/sw-phase115-hanit-current.json` (SHA-256
`39f4931a325a0a6d5f46af49720264f1d92268b3f43e3ff66a7b7ba106468435`)
records 1,440
ticks / 7,200 logical seconds, blue `time_expired`, all 3 units moving, four
C-802 engagement records, zero casualties, and the explicit
`ZERO_CASUALTIES` plus `ENGAGEMENTS_BUT_NO_DAMAGE` warnings. It is a current
engine integrity result, not a historical outcome envelope.

## Focused behavioral validation

The initial complete non-API Phase 115 selection before the closure defects
above were found was:

```text
env PYTHONDONTWRITEBYTECODE=1 \
  UV_CACHE_DIR=/tmp/sw-phase115-focused-final-uv-cache \
  uv run --no-sync pytest -q \
  tests/unit/simulation/test_tactical_targeting.py \
  tests/unit/simulation/test_targeting_exposure.py \
  tests/unit/test_phase115_fow_witness.py \
  tests/unit/test_phase115_loadout_bindings.py \
  tests/unit/test_phase115_movement_targeting_diagnostics.py \
  tests/unit/test_phase115_replay_scope.py \
  tests/integration/test_phase115_engagement_owner_arbitration.py \
  tests/integration/test_phase115_sensing_standoff_red.py \
  tests/integration/test_phase115_targeting_checkpoint.py \
  tests/integration/test_phase115_targeting_controls.py
# 229 passed in 179.18s
```

Exit was 0 with zero failures, errors, skips, warnings, xfails, or xpasses.
It remains baseline evidence but is not the final source-frozen count. This
selection covers strict value invariants, total role/domain matrices,
environment and LOS bounds, FOW witness ownership/single-draw behavior,
default-on/off behavior, exact initial/reinforcement/checkpoint bindings,
reordered and duplicate-role loadouts, movement/engagement same-decision
ownership, routed-owner controls, post-movement revalidation, API-safe
projections, replay, and format-115 atomic continuation.

The affected baseline selection was repeated on the then-current repaired
source:

```text
env PYTHONDONTWRITEBYTECODE=1 \
  UV_CACHE_DIR=/tmp/sw-phase115-affected-final-uv-cache \
  uv run --no-sync pytest -q \
  tests/unit/simulation/test_battle_pure_functions.py \
  tests/integration/test_phase_109_battle_sensor_domains.py \
  tests/integration/test_phase112_runtime_red.py \
  tests/integration/test_phase112_movement_diagnostics.py \
  tests/unit/test_phase112_movement_diagnostics.py \
  tests/validation/test_phase112_evaluator_contract.py \
  tests/integration/test_phase_109_weapon_multiplicity.py \
  tests/validation/test_phase_30_scenarios.py
# 419 passed in 170.75s
```

Exit was 0 with zero failures, errors, skips, warnings, xfails, or xpasses.
The changed count from the 427-test phase baseline follows the deliberately
revised parameterization/contract in these files; collection completed
normally.

## Data and static validation

An intermediate production mapping/loadout gate passed 96 tests in 53.44
seconds. The then-current full data validator reported:

```text
env PYTHONDONTWRITEBYTECODE=1 \
  UV_CACHE_DIR=/tmp/sw-phase115-data-final-uv-cache \
  uv run --no-sync python scripts/validate_scenario_data.py
# 184 unit YAML definitions
# modern: 102 units / 394 authored equipment occurrences / 244 keys /
#         101 sensor-required / 1 intentionally sensorless
# ancient: 20 units / 67 occurrences / 34 keys
# Napoleonic: 21 units / 57 occurrences / 27 keys
# WW1: 16 units / 57 occurrences / 47 keys
# WW2: 25 units / 104 occurrences / 93 keys
# 442/442 registry coverage; 0 unmapped; 0 stale
# 1 explicit sensorless classification:
#   modern/civilian_noncombatant = intentionally_none
# 11 constellations; 3 ASAT systems; 52 scenarios
# 8,388/8,388 initial units
# 70 authored groups -> 1,128 units
# 1,128/1,128 units and 1,131/1,131 field applications
# 0 errors, 0 warnings, 1 classification
# PASSED
```

That intermediate full scenario-data module passed `272 passed in 28.22s`; its 52
catalog scenario parameters each loaded through the production
`ScenarioLoader`. The two former no-sensor warnings remain explicitly
resolved: the civilian is deliberately sensorless and the insurgent squad has
an authored visual sensor. No sensor or fire-control capability is invented by
the targeting runtime.

After the historical-visibility repair, the source-frozen `$validate-data`
rerun retained those exact catalog totals and passed with zero errors and zero
warnings. Its focused changed-unit validator exited 0 without diagnostics;
the 52 production `ScenarioFullLoad` cases passed in 33.01 seconds; and the
mapping, loadout, and Hanit selection passed 115 tests in 40.83 seconds. The
single emitted classification remains
`modern/civilian_noncombatant = intentionally_none`; it is not a warning.

The final evidence-ledger validator passed against a fresh unfiltered
collection in 15.60 seconds. It reported 92 no-direct-oracle entries, 88
reviewed behavioral exclusions, 918 structural nodes, and 1,006 weak-oracle
review entries. New Phase 115 tests are therefore classified rather than
hidden outside the Phase 112 trust boundary.

The remote Python lint failure reported by the owner was run `30421215404` on
the original Block-12 start commit `70e72f5`. Its log contained six `F601`
duplicate mapping keys in the private validation runner and two `F541`
placeholder-free f-strings. Phases 109 and 112 removed those duplicate/proxy
paths and repaired the tests; subsequent remote Lint runs on every phase commit
through the Phase 115 base `f057923` passed. The current local execution of the
complete hosted-CI selection is also clean:

```text
env UV_CACHE_DIR=/tmp/sw-phase115-ruff-final-uv-cache \
  uv run --no-sync ruff check stochastic_warfare/ api/ tests/ scripts/
# All checks passed!

env UV_CACHE_DIR=/tmp/sw-phase115-compile-final-uv-cache \
  uv run --no-sync python -m compileall -q \
  stochastic_warfare api scripts tests
# exit 0

git diff --check
# exit 0
```

The focused duplicate-key `F601` check also passed. Ruff formatted the new
Phase 115 Python modules and tests before these commands.

The exposed frontend contract required the full frontend route:

```text
cd frontend
npm test
# 84 files passed; 447 tests passed; 2.90s

npm run lint
# exit 0; 0 errors; 4 existing warnings

npm run build
# exit 0; TypeScript clean; 420 modules transformed; 19.72s
```

The four ESLint warnings are the existing `react-hooks/exhaustive-deps`
classifications at `TacticalMap.tsx:350,355`, `TerrainPreview.tsx:14`, and
`MapTab.tsx:35`. Build emitted the existing stale-Browserslist and large-chunk
advisories; its largest reported bundles were `index` 577.82 kB and
`react-plotly` 4,875.37 kB. A repeat test run used only to classify stderr
produced 74 React Router future-flag advisories, 10 React `act()` harness
warnings, and four nonfatal jsdom navigation diagnostics; all 84 files / 447
tests still passed in 2.64 seconds. There were no frontend test, lint, or build
errors, and the build's ignored `dist/` output did not change Git status.

## Determinism and production scenario outcomes

`$audit-determinism` found no new RNG owner, unordered state-affecting
traversal, or checkpoint-continuation defect. The targeting picture consumes
the canonical FOW answer and no RNG itself. The same seven exact controls were
run under two hash seeds:

```text
PYTHONHASHSEED=1 .venv/bin/pytest -q \
  tests/unit/test_phase115_fow_witness.py::\
test_three_side_catalog_sensor_parallel_matches_sequential_exactly \
  tests/unit/test_phase115_fow_witness.py::\
test_gated_moving_contacts_are_bounded_and_parallel_deterministic \
  tests/integration/test_phase115_targeting_checkpoint.py::\
test_format_115_no_fow_fresh_continuation_is_exact \
  tests/integration/test_phase115_targeting_checkpoint.py::\
test_environment_extended_sonar_checkpoint_and_continuation_are_exact \
  tests/integration/test_phase115_targeting_checkpoint.py::\
test_schema_valid_extended_thermal_checkpoint_and_continuation_are_exact \
  tests/integration/test_phase115_targeting_checkpoint.py::\
test_valid_older_ring_restore_continues_deterministically \
  tests/integration/test_phase115_targeting_checkpoint.py::\
test_reinforcement_topology_fresh_restore_and_continuation_are_exact
# 7 passed in 9.18s

# The identical node list under PYTHONHASHSEED=777:
# 7 passed in 8.80s
```

They include three independently built same-seed parallel-detection sessions,
no-FOW checkpoint continuation, sonar/thermal range-extension continuation,
older-ring contact behavior, and reinforcement topology/history. Exact command
paths are shown above; both runs exited 0 with no failures or warnings.

The subsequently added historical-visibility continuation node was also run
alone under `PYTHONHASHSEED=1` and `PYTHONHASHSEED=777`:

```text
PYTHONHASHSEED=1 .venv/bin/pytest -q \
  tests/integration/test_phase115_targeting_checkpoint.py::\
test_historical_targeting_keeps_its_own_visibility_across_restore
# 1 passed in 2.36s

PYTHONHASHSEED=777 .venv/bin/pytest -q \
  tests/integration/test_phase115_targeting_checkpoint.py::\
test_historical_targeting_keeps_its_own_visibility_across_restore
# 1 passed in 2.43s
```

The final combined FOW/identification/parallel/aggregation selection passed 80
tests in 2.32 seconds, and six focused single-draw, ordering, public-ordinal,
and repeated-run controls passed in 4.48 seconds. Direct production probes
under hash seeds 1 and 777 produced the identical semantic SHA-256
`42cac728f7f59cb09446295156633cc86df28bd5eab53a3a1ef33f64f43c0836`.
All final determinism commands had zero failures, errors, warnings, skips,
xfails, or xpasses; ordinary nonempty FOW contact continuation remains the
explicit REM-029 exclusion.

Cambrai and Jutland seeds 42 through 44 were evaluated through the production
factory. They are current-engine integrity regressions, not historical
validation:

| Scenario/seed | Final ticks | Casualties | Engagements | Moved / unmoved | Issues |
|---|---:|---:|---:|---:|---|
| Cambrai 42 | 156 | 2 | 0 | 7 / 3 | none |
| Cambrai 43 | 168 | 3 | 0 | 7 / 3 | none |
| Cambrai 44 | 216 | 2 | 0 | 7 / 3 | none |
| Jutland 42 | 461 | 10 | 26 | 29 / 0 | none |
| Jutland 43 | 353 | 10 | 24 | 29 / 0 | none |
| Jutland 44 | 257 | 10 | 24 | 29 / 0 | none |

The four Cambrai Mark IVs no longer hold blind at 5,340 m: all four advance,
raising movement from 3/10 to 7/10 without changing seed-42 terminal duration
or casualties. Jutland's 13 capital ships no longer stop solely at a 21.7 km
catalog gun range; all 29 units move and capital engagements become reachable.
Compared with the baseline, seeds 42/43/44 change from
`569/10/15`, `437/6/14`, and `713/8/16` ticks/casualties/engagements to the
values above. That semantic delta is expected from REM-028 and is not a
calibration verdict.

Repeated seed-42 Cambrai and Jutland runs were written independently under
`/tmp`; canonical `jq` comparisons after deleting only `duration_wall_s`
returned `true` with exit 0 for both scenarios.

The production evaluator then completed all 46 discovered non-benchmark
catalog scenarios at seed 42. The pre-cull artifact
`/tmp/sw-phase115-all-scenarios-42-final.json` and post-cull artifact
`/tmp/sw-phase115-all-scenarios-42-post-cull.json` have SHA-256
`ecdb43ccbdd94f0236ea4f93327a2bcc568bd9e248a78b6935a3b783a91faf04`
and
`ced1ceb26d782bc51cdbd8c0548e3fce00dd4eef8795ad0e532cf60ec6bc67c1`
respectively; their complete records are exactly equal after removing only
`duration_wall_s`. Seven scenarios retain explicitly reported evaluator
issues rather than being relabeled green:

```text
.venv/bin/python scripts/evaluate_scenarios.py --seed 42 --no-details \
  --output /tmp/sw-phase115-all-scenarios-42-post-cull.json
# 46 scenarios completed; exit 0; 39 without issues, 7 with declared issues
```

The evaluator deliberately excludes the two performance fixtures
`benchmark_battalion` and `benchmark_brigade` plus the four internal fixtures
`test_campaign`, `test_campaign_logistics`, `test_campaign_multi`, and
`test_campaign_reinforce`. All six remain covered by loader/schema tests; no
excluded scenario is counted as an evaluator pass.

- `normandy_bocage`, `falklands_campaign`, and `falklands_naval` have zero
  casualties/engagements;
- `calibration_arctic` reports a red centroid-collapse diagnostic;
- `ins_hanit_2006` has zero casualties despite the now-reachable C-802
  engagements;
- `space_isr_gap` has zero engagements and no movement; and
- `time_on_target_validation` reports no movement.

Those are current diagnostic dispositions, not historical-validation or
calibration verdicts. The two complete runs took 7,568.92 and 3,980.39 wall
seconds under unrelated machine load; those durations are
contention-qualified observations only.

After the final FOW transaction repair, the seven FOW-enabled catalog
scenarios were rerun with at most four evaluator processes. Bekaa Valley,
calibration air-ground, calibration urban-CBRN, Gulf War EW, Korean Peninsula,
Suwalki Gap, and Taiwan Strait all exited 0 with empty issue/error lists. Each
full result matched its entry in the post-cull 46-scenario artifact exactly
after deleting only `duration_wall_s` (7/7 unchanged). Their artifact SHA-256
values and outcomes are:

| Scenario | Ticks / logical s | Winner / condition | Casualties | Engagements | Moved / total | SHA-256 |
|---|---:|---|---:|---:|---:|---|
| `bekaa_valley_1982` | 46 / 230 | blue / force destroyed | 8 | 48 | 46 / 65 | `bea9f1bbc807a4eecedc4054ce7744f69b60f5dc71e618629f5410463f6b94bc` |
| `calibration_air_ground` | 120 / 600 | red / force destroyed | 10 | 14 | 14 / 16 | `cab5c64fefd1120678c5eaf77919ffacebd9605686bde98fbf5e4344d7870686` |
| `calibration_urban_cbrn` | 82 / 820 | red / force destroyed | 3 | 32 | 14 / 14 | `63798735dc1b4badb575c108a71bd69824b8c49dfbe41b72616caf9085e8918a` |
| `gulf_war_ew_1991` | 4,320 / 21,600 | blue / time expired | 24 | 163 | 80 / 104 | `aff4248c905f3224d0f383badf6949cdbb217de449e7da1445d1c43524ffe255` |
| `korean_peninsula` | 1,275 / 6,375 | blue / force destroyed | 19 | 71 | 20 / 38 | `8959a49f3e934c15e21da04d9ed2a32a8f016e94844d2a8abd173f39ddf55128` |
| `suwalki_gap` | 51 / 255 | red / force destroyed | 16 | 65 | 13 / 39 | `161c6dfe8c347d95fd6bddbd1cfc9cffdb93d882dec64f4073d4d94df7bda572` |
| `taiwan_strait` | 49 / 3,840 | blue / force destroyed | 11 | 24 | 14 / 32 | `9766bbde103aba5a42a58c4018fbd03398f38c3468ff4353814a2462d020c312` |

The digests in the same order are also retained as a copy-friendly block:

```text
bea9f1bbc807a4eecedc4054ce7744f69b60f5dc71e618629f5410463f6b94bc
cab5c64fefd1120678c5eaf77919ffacebd9605686bde98fbf5e4344d7870686
63798735dc1b4badb575c108a71bd69824b8c49dfbe41b72616caf9085e8918a
aff4248c905f3224d0f383badf6949cdbb217de449e7da1445d1c43524ffe255
8959a49f3e934c15e21da04d9ed2a32a8f016e94844d2a8abd173f39ddf55128
161c6dfe8c347d95fd6bddbd1cfc9cffdb93d882dec64f4073d4d94df7bda572
9766bbde103aba5a42a58c4018fbd03398f38c3468ff4353814a2462d020c312
```

The first attempt used unavailable `/usr/bin/time` and exited 127 before
Python started or an artifact was created. The successful commands used Bash
`time -p`; their 2.11--24.48 second wall observations are not performance
claims.

### Fallujah and Debecka slow-regression disposition

Fallujah's old slow test contained an unsourced `ticks >= 50` proxy. The final
test instead consumes public `SimulationEngine.run()` /
`SimulationRunResult`, requires a blue `force_destroyed` terminal strictly
before its 2,000-tick safety cap, and proves exact five-second elapsed time.
It retains the current winner, broad casualty, at-least-50 direct-engagement,
and pre-emplaced-IED outcome guards:

```text
.venv/bin/pytest -q tests/validation/test_fallujah_phase_line_fran.py
# 13 passed in 100.24s
```

Exit was 0 with no failures, errors, skips, warnings, xfails, or xpasses. Seed
42 ends blue / `force_destroyed` at 40 ticks / 200 seconds with one destroyed
blue and 69 destroyed red unit records, 221 direct engagement events, and eight
IED detonations. The complete evaluator record in
`/tmp/sw-phase115-all-scenarios-42-post-cull.json` has SHA-256
`ced1ceb26d782bc51cdbd8c0548e3fce00dd4eef8795ad0e532cf60ec6bc67c1`:
70 casualties, 297 combined evaluator engagements, 333 moved / 0 unmoved,
1,060.7 m mean movement, 2,282 events, and no issue. The Phase 112 artifact
`/tmp/sw-phase112-baseline-fallujah_phase_line_fran.json` is 1,158 bytes with
SHA-256 `9cb242c71ded0212da35ef84df4a5d25b58c6c3230ff3f19b05349159f2858a5`;
it records the same blue / `force_destroyed` threshold at 115 ticks / 575
seconds, 68 casualties, 1,643 evaluator engagements, 256 moved / 77 unmoved,
830.7 m mean movement, and 3,543 events. An otherwise identical typed
`enable_sensing_aware_standoff=false` production control ends even earlier at
38 ticks, so the new default-on standoff branch is not the terminal
accelerator. This is a deterministic current-engine semantic delta, not a
source-backed historical-duration/casualty envelope, held-out validation,
calibration verdict, or authority to tune physical parameters.

The run ends before the first of 11 authored scripted actions at H+7. Loading
their declarations and resolving references does not prove dispatch or
effects. Inspection also found the generic parameter bag, caught/no-op actions
marked fired, direct position/personnel mutation, and absent checkpoint/API
lifecycle now recorded as REM-045 / Phase 132.

Debecka is the one final slow-partition behavioral red. The exact current
default probe used ten production `_run_one()` workers:

```bash
.venv/bin/python - <<'PY'
from concurrent.futures import ProcessPoolExecutor, as_completed
from collections import Counter
import json

def run(seed):
    from tests.validation.test_debecka_pass import _run_one
    result = _run_one(seed)
    weapons = Counter(
        str(event.data.get("weapon_id"))
        for event in result["events"]
        if event.event_type == "EngagementEvent" and event.data.get("weapon_id")
    )
    return {
        "seed": seed,
        "winner": result["winner"],
        "blue_destroyed": result["blue_destroyed"],
        "red_destroyed": result["red_destroyed"],
        "ticks": result["ticks"],
        "engagements": sum(
            event.event_type == "EngagementEvent"
            for event in result["events"]
        ),
        "bomb_rack_generic": weapons["bomb_rack_generic"],
        "javelin_clm": weapons["javelin_clm"],
        "weapon_counts": dict(sorted(weapons.items())),
    }

results = []
with ProcessPoolExecutor(max_workers=10) as pool:
    futures = {pool.submit(run, seed): seed for seed in range(42, 52)}
    for future in as_completed(futures):
        item = future.result()
        results.append(item)
        print(json.dumps(item, sort_keys=True), flush=True)
results.sort(key=lambda item: item["seed"])
print("SUMMARY " + json.dumps({
    "blue_wins": sum(item["winner"] == "blue" for item in results),
    "red_wins": sum(item["winner"] == "red" for item in results),
    "mean_blue_destroyed": sum(item["blue_destroyed"] for item in results) / 10,
    "mean_red_destroyed": sum(item["red_destroyed"] for item in results) / 10,
    "mean_ticks": sum(item["ticks"] for item in results) / 10,
    "total_bomb_rack_generic": sum(item["bomb_rack_generic"] for item in results),
    "total_javelin_clm": sum(item["javelin_clm"] for item in results),
}, sort_keys=True), flush=True)
PY
```

It completed in about 61 contention-qualified wall seconds: blue won seeds
48--51 only (4/10), mean destroyed record counts were 42.5 blue / 6.7 red,
mean duration was 1,887.5 ticks, and every seed retained five bomb plus six
Javelin engagements. The explicit-off probe used the same seed/process wrapper
but loaded through `ScenarioLoader.load(...,
calibration_overrides={"enable_sensing_aware_standoff": False})`, then the
same `SimulationEngine(max_ticks=3000)` and public production owners. It
completed in about 49 contention-qualified seconds and produced 7/10 blue
wins, means 43.1 blue / 8.8 red destroyed records, and 1,137.6 ticks. Thus the
new standoff branch contributes exposure/morale cascades but does not explain
the primary result shift.

For a clean prior-revision comparison, the exact base was archived and run
outside the dirty worktree:

```text
mktemp -d /tmp/sw-phase114-debecka.XXXXXX
# /tmp/sw-phase114-debecka.J8EZKV
git archive --format=tar \
  --output=/tmp/sw-phase114-debecka.J8EZKV/source.tar f057923
tar -xf /tmp/sw-phase114-debecka.J8EZKV/source.tar \
  -C /tmp/sw-phase114-debecka.J8EZKV
cd /tmp/sw-phase114-debecka.J8EZKV
/home/csmith/projects/stochastic-warfare/.venv/bin/python - <<'PY'
# The complete default 42--51 probe above, unchanged.
PY
```

The retained 19,179,520-byte archive SHA-256 is
`d34d55d6a8d2ad88ec2941e061b0288a01a6b8e805635f546dadc114b0bd2af0`.
That revision produced 10/10 blue wins, means 32.5 blue / 15.6 red destroyed
records, and 137.9 ticks. It recorded 1,315 M61A1 ground engagements across
the ten seeds; the current on/off runs record about 25/24. In seed 42 alone,
Phase 114's two F-14s contributed 34 and 31 M61 ground engagements. Phase 115
correctly records `FIRE_CONTROL_TARGET_DOMAIN_UNSUPPORTED` because their
AN/AWG-9 role is aerial-only; the F/A-18's multi-domain APG-73 retains its
limited compatible ground-gun path. This is an intended shared-targeting
integrity effect, not target starvation.

The remaining long runs expose a scenario-policy contradiction. Debecka's
runtime horizon is four hours, but its authored blue fallback is due at six
hours. A read-only typed control changed only `duration_hours: 4 -> 6` in an
in-memory `CampaignScenarioConfig` and raised the safety cap solely to 4,500 so
21,600 seconds was reachable. It completed in about 63.5 contention-qualified
seconds: blue labels were 10/10, comprising four `force_destroyed` results and
six `time_expired` results at exactly tick 4,320 / 21,600 seconds. In every
fallback seed all 56 blue units were already destroyed or surrendered. The
unchanged test's 3,000-tick cap also cannot reach that fallback. Changing the
scenario horizon, test cap, or winner floor would therefore manufacture a pass
around an unvalidated policy. REM-030 / Phase 117 owns the outcome-envelope and
victory-policy disposition; Phase 115 leaves both files unchanged.

## Production hot-loop profile

`$profile` first exposed an unacceptable targeting-loop expansion rather than
accepting a no-crash run. After the interval cache, the remaining dominant
cost was exact targeting work for catalog pairs that could not possibly be in
weapon range. The final conservative range pre-cull rejects only when finite
ENU separation exceeds every serviceable compatible weapon's saturating
environmental bound; it performs no detection draw and cannot authorize a
target.

On the same production 73 Easting worker, the exact pre-cull targeting
measurement was 163.658 seconds and the post-cull measurement was 2.7595
seconds (approximately 59 times lower); the complete post-cull worker wall
observation was 4.847 seconds. Full normalized runtime input and semantic
output were exact across that optimization.

The final production cProfile records 69.35 million calls and 17.704 seconds
total, versus 271.59 million calls and 268.551 seconds in the directly
comparable pre-cull capture. `SimulationEngine.run()` fell from 261.099 to
11.551 seconds. The range-cull path performed about 756,000 checks / 4.339
seconds cumulative, while rejected pairs performed zero targeting opacity,
environment, or LOS work. These values were collected under concurrent user
load and are therefore contention-qualified measurements, not a clean speedup
or absolute performance pass. The accepted evidence is the exact semantic
identity, conservative bound, and removal of impossible expensive work.

## Reviews and open follow-ups

`$validate-conventions` accepted the strict typed schema, owner identity,
logical-clock, finite arithmetic, ENU range, API projection, and staged
checkpoint boundaries with no high- or medium-severity finding.
`$validate-data` accepted the total mapping/domain contract and zero-warning
catalog result. `$evaluate-scenarios` accepted the focused repaired scenarios;
the final complete-catalog disposition remains in the closure section below.

The first `$simplify` pass returned **NOT READY**. It identified the
non-atomic FOW replacement/association path, overly permissive aggregation
restore ownership, exact-roster registration gaps, and avoidable hot-loop
work. Those findings produced the transaction, strict owner/configuration,
registration, and conservative pre-cull repairs above. A source-frozen
follow-up re-review returned **CLEAN** for those findings. It also accepted the
small total `weapon_role_supports_target_domain()` helper; exact
weapon-definition domain validation still prevents policy widening. This
follow-up result supersedes the pre-repair review rather than erasing it.

The final independent `$simplify` review after the historical-visibility
repair found no production blocker. Its one medium documentation finding was
the overbroad claim that older retained pictures were compared with current
weather; the checkpoint specification and this devlog now distinguish
checkpoint-current from historical intervals explicitly. Its low nonblocking
note observed that currentness is checked at both the engine membership and
scenario restore boundaries; the two policies agree and serve different
cross-owner validations, so no late unification was justified.

Five independent deficits are deliberately not hidden inside REM-028:

- REM-041 / Phase 128: `SIDE_FOW` is a structurally safe projection, but the
  API has no caller authentication/authorization and defaults to privileged
  evidence. A caller-supplied scope is not authorization and client filtering
  is not player safety.
- REM-042 / Phase 129: exact compatible source indexes do not replace authored
  physical mount/director associations. Otherwise-compatible same-unit
  attachments can still cross-bind.
- REM-043 / Phase 130: current deterministic threat selection is not yet a
  complete availability-aware threat-ranking contract.
- REM-044 / Phase 131: fusion still uses a generic isotropic uncertainty
  model and does not stage elapsed-time prediction plus measurement update as
  one atomic transaction. Phase 115's one-metre minimum prevents a singular
  conventional update but is not sourced sensor covariance.
- REM-045 / Phase 132: Phase 101 scripted actions use a string plus untyped
  parameter bag, consume exceptions and missing-owner/target no-ops as fired,
  bypass movement/casualty lifecycle owners, and do not persist or expose their
  exact-once lifecycle. The current Fallujah run ends before the first due
  action, so declaration/reference loading is not dispatch/effect proof.

REM-016, REM-020, REM-021, REM-029, REM-030, REM-035, and REM-036 retain their
documented independent scope.

## REM-028 capability matrix at closure

| Gate | Evidence | Result |
|---|---|---|
| Declared | strict `CalibrationSchema` flag; typed interval, picture, decision, revalidation, role, disposition, binding, checkpoint, and exposure schemas | Yes |
| Loaded | factory-loaded default/on/off variants; exact initial, reinforcement, and checkpoint loadout roles; malformed configuration/data rejection | Yes |
| Wired | one identity-bound runtime prepared once per tactical interval; movement and ordinary direct engagement consume the same decision | Yes |
| Enabled | default-on authorization, explicit-off zero standoff, and unchanged explicit/routed-owner controls | Yes |
| Exercised | factory/session Mark IV, Jutland capital, Salamis, mixed-role/domain, FOW, reinforcement, and checkpoint production paths | Yes |
| Outcome-affecting | Cambrai positions/reasons and Jutland movement/fire/engagement/ammunition topology change without sensor extension or invented target | Yes |
| Persisted/exposed | format-115 no-FOW exact continuation; historical/non-consumable restored FOW decision; diagnostic/evaluator/replay/API/frontend privileged and side-FOW evidence | Yes, with REM-029 and REM-041 explicitly bounded |

The matrix is implementation evidence rather than a status label. The broader
gates, documentation audit, and postmortem below passed before Phase 115 and
REM-028 transitioned to complete/closed.

## Final broader validation disposition

Intermediate failures and exclusions remain part of the record. Before the
final FOW/aggregation repairs, a broad integration run reported 654 passes, 9
deselections, 16 failures, and 1 error in 431.15 seconds; every failure/error
was the fail-closed provenance guard observing concurrent authorized edits
between preparation and build, so no intended corruption/continuation body ran.
A pre-transition standard attempt also timed out one shard and found a stale
evidence ledger plus the then-unreachable Hanit C-802 path. Those results were
not relabeled passes; the source-frozen evidence below supersedes them.

The untracked `artifacts/` directory created during those attempts was moved
intact and recoverably to `/tmp/sw-phase115-artifacts-preclosure` before the
provenance-sensitive reruns. No source or user data was removed. All final
runner outputs were written directly under `/tmp` and did not mutate the tree
whose identity they checked.

### Final partition audit and standard partition

```text
.venv/bin/python scripts/validate_test_partitions.py \
  --output /tmp/sw-phase115-final2-audit/manifest.json
# 12,248 total nodes; zero collection warnings
# standard 11,743; slow-only 110; benchmark-only 87;
# slow-benchmark 4; API 263; E2E 41
# exact union complete; every pairwise intersection empty
```

Exit was 0. The 2,588,586-byte audit manifest SHA-256 is
`564a60a965708a20033d8b2acd26987426fc9328e4b6493c4967f9d5c42cc89b`.
Every partition runner used its audited manifest selection, `--forbid-skips`,
the declared 2,700-second operational cap, and a JUnit identity check whenever
pytest reached a summary. The exact standard pattern was:

```text
.venv/bin/python scripts/run_pytest_partition.py standard \
  --manifest /tmp/sw-phase115-final2-standard-N/manifest.json \
  --junit /tmp/sw-phase115-final2-standard-N/junit.xml \
  --forbid-skips --timeout-seconds 2700 \
  --shard-count 4 --shard-index N
```

| Standard shard | Result | JUnit time | Warnings | Manifest / JUnit / result SHA-256 |
|---:|---:|---:|---:|---|
| 0 | 2,936 passed | 307.741s | 0 | `a434fb8a80010902eb01c45c866d6b3a23c5f2a481ebac8ed44079f808bf75ba` / `7b2369d00771fdf3d3b84bb9ca4d4e27519ad656197bd7e630834a2dac2ba722` / `f1ff1253e63dc8cff834830bcc38130bf216a67c2881a5907ae9bd723765978b` |
| 1 | 2,936 passed | 166.083s | 1 | `f50a21ed2b2512c5cfd1e3f06b31561386a88398c46b1e355d91ab0f4a9e8be7` / `c2303464e5fd57971d68f78963d42ce8ba0437bc9b8b8d8652409d04f45f5eb7` / `45b1989e44e1d5d10469a8d5921f096bd83d7a18a54446ac13ae7a60ee270b8b` |
| 2 | 2,936 passed | 206.240s | 0 | `8936ce395d8d296d548d7e142dd77de79fd82a4d326f4219c153674ee917b165` / `d55e4bc9c572ea4760af5d5609cf4f0b08d31f694d214f7b2ec9de3ebce26858` / `c4ddaf19562ecb103a8f70c9745a2252993c4fb356fc6a9fdb7cc60495a76439` |
| 3 | 2,935 passed | 260.833s | 5 | `a8bf14ceb9675ada1b20ffea4d3ccfd9a73570e50172d10f90674c3878deb3e3` / `1b5ea50ad294af93b427e94c1f3bd6925c650f3fa60d094327b1a76d2d67282b` / `57db8febe0d31507aa2305358aad55ec03ae94246ed8ec5bfec2e7cf87c1cc79` |

The authoritative standard total is **11,743 passed**, zero failures, errors,
skips, xfails, or xpasses, and six classified warnings. They are the known one
empty chart-legend warning, four unrendered matplotlib-animation warnings, and
one `datetime.utcnow()` deprecation. Each JUnit ordered/multiset identity
matched its exact manifest/selection; no node was substituted or lost.

### Other complete profiles

| Profile | Result | JUnit time | Warnings / skips |
|---|---:|---:|---:|
| benchmark-only shard 0 | 77 passed | 4.382s | 0 / 0 |
| benchmark-only shard 1 | 7 passed | 0.557s | 0 / 0 |
| benchmark-only shard 2 | 3 passed | 0.104s | 0 / 0 |
| slow-benchmark | 4 passed | 13.536s | 0 / 0 |
| terrain overlap | 97 passed | 2.406s | 0 / 0 |
| benchmark-policy overlap | 86 passed | 17.482s | 0 / 0 |

The 87 benchmark-only nodes are the exact three-shard audited partition, not a
subset. Slow-benchmark JUnit SHA-256 is
`04e4cd4ddb858e4cac780ce735e5890a3826a74105dd41d65b6f13384ccd126d`;
terrain is `a563ace592088486b2d13267901abe6a52b0b7ffb68f59d14090c5a1863fc94d`;
benchmark-policy is
`82ae78fd152ba8df4502c4f6fc51dd33521932440220ac4be5275f18bd1d104f`.
All corresponding result JSONs report `passed` and exact selection/JUnit
identity.

### Qualified slow, API, and E2E disposition

The owner explicitly accepted contended long-run results as qualified evidence
and asked that unrelated workloads remain untouched. No timeout is called a
pass.

- final slow-only shard 1 passed all 28 nodes in 142.991 seconds with zero
  warnings/skips; JUnit SHA-256 is
  `e1cb46abd9f8095bd5da9925bbeca6410d15e648a05fa6d7a575f15aea5957a9`;
- final slow-only shard 2 ran all 27 nodes in 712.847 seconds: 26 passed and the
  sole failure was Debecka's truthful 4/10 current-engine blue-winner result.
  It had zero warnings, skips, errors, xfails, or xpasses and exact JUnit
  identity; JUnit SHA-256 is
  `a16b1c48d5a1cc6326eb49efb20e9c8812b1cf99b0ff4b82393e9431d5a84ba1`.
  The REM-030 analysis and no-tuning disposition are recorded above;
- an earlier pre-visibility-fix slow shard 0 reached 17 pass glyphs and four
  Debecka checkpoint/snapshot errors before the 2,700-second cap, leaving seven
  nodes uncompleted and no JUnit. Every visibility defect was repaired and the
  complete 51-node checkpoint module, exact Debecka snapshot node, and focused
  historical/current controls passed afterward. Its timeout result SHA-256 is
  `c65b6005b6c06ea152217fa9235d1c8d5d9f28f73b0962c753e24cecb8f32c5c`;
- an earlier slow shard 3 reached 11 pass glyphs, then spent the remaining cap
  in the 1,000-run 73 Easting convergence node; 16 nodes were uncompleted, no
  failure was reported, and no JUnit was written. Its timeout result SHA-256 is
  `79a032481cc790dbaeca127690c2fc392e5c08da59ca84c83b0edc42aa18cbeb`.

The exact final API command was:

```text
.venv/bin/python scripts/run_pytest_partition.py api \
  --manifest /tmp/sw-phase115-final2-api/manifest.json \
  --junit /tmp/sw-phase115-final2-api/junit.xml \
  --forbid-skips --timeout-seconds 2700
```

Collection selected all 263 nodes from 26 modules in 0.19 seconds with zero
deselections or warnings. Execution reached the exact 2,700-second cap and
exited 124 with `status=timeout`; pytest produced neither a summary nor JUnit,
so execution pass/fail/skip counts are unavailable rather than zero. The
47,137-byte manifest SHA-256 is
`989433d39fdf2220b4ef544e1b7c661fea4bfc9b1ffd1bf2badf992b587afd06`;
the 263-line selection SHA-256 is
`8a9faf3553fb45d5bc891267d10d1bd656bf268d28b1aadbf889862336179e0a`;
the timeout result SHA-256 is
`d44a30a5c9a12371f63f9922445df5ffb413c1091aef09d4c7ee2d2b14eed39d`.

The E2E command was identical with partition/path `e2e`. It selected all 41
scenario-smoke nodes in one module and also reached the exact 2,700-second cap,
exit 124, before a pytest summary or JUnit. Its 8,335-byte manifest SHA-256 is
`0bcc09a345f1df2428f67def1029e254fbcb10c378266d3abd317230abc31062`;
the 41-line selection SHA-256 is
`c82a7d30310918aefaaadfe3e2036aa9731f3de3d1574d5e4504d19ce615abbe`;
the result SHA-256 is
`d8f270df08783f7e104ddabf88240863963bd931a3d1c2507adfc652853c0b90`.

These two timeouts are an explicit local environment qualification, not API or
E2E partition passes. Phase 115's direct production API route, complete
synchronous exposure/aggregation/checkpoint selection, frontend contract, and
46-scenario evaluator evidence passed as recorded above. The clean hosted jobs
after the phase push remain the independent environment control; a remote red
must be repaired rather than overwritten by this qualification.

### Frozen-tree version-4 paired transition

The final implementation/data/documentation evidence tree ran the strict
non-timing transition command without changing repository status:

```text
.venv/bin/python scripts/run_paired_benchmark.py transition \
  --scenario 73_easting \
  --artifact /tmp/sw-phase115-73-easting-transition-v4-final.json \
  --allow-dirty-candidate --worker-timeout-seconds 300
# 73_easting: transition_qualified; timing=not_applicable;
# artifact_sha256=ac220de0a75bc185cc0faf03a1b534286a4b8b1111c55245afeec38e6bc2dee1
```

Exit was 0 with `errors=[]` and all 29/29 declared approvals verified. The
1,243,770-byte artifact's canonical/embedded SHA-256 is
`ac220de0a75bc185cc0faf03a1b534286a4b8b1111c55245afeec38e6bc2dee1`;
its serialized-file SHA-256, which also includes the embedded self-hash field,
is `222f87fb95151ff79ec313b916c1e018587f723e67fa0f7a6edc044e9063341c`.
The clean reference is `0460ac70be86784bcc6e359ae4202f4bcb938c60`; the explicitly allowed dirty
candidate base is `f057923e3b13aabe2f0994e03063e6692ceef0ce`.

Reference and candidate runtime-input fingerprints are respectively
`9d85b6f8489e961eaf3765220d2e2672e1e8955f8a9b58827a8ce0c1b9931e77`
and
`3ef1e72ff1ebdb099a6e89cc6917540f49d774593816c439bfe9e96d6d87f879`.
The complete approved semantic envelope is otherwise identical: blue /
`time_expired`, 360 ticks / 1,800 seconds, 71 units, 21 blue and 50 red
`ACTIVE`, one event, and event digest
`2784db62737dac1df07bb13e64cadb9b6b6f0d3e48cee291efcfc0d51cb8e798`.
Only the approved roster/loadout digest changes, from
`b598b36d78604a60cd16bd3313e29e7a8a677e2cb9b83417dc4b00cab778a1b3`
to
`1344d0fdffe8cf42cd5329a4cbc808398a449f47c14c95fb17807f671f3a32a2`.
Timing is explicitly `not_applicable` because workloads differ; the roughly
6.5-second command observation is not a paired speed result. Pre/post
`git status --porcelain=v1` matched byte-for-byte at 124 lines. Phase 116 must
promote the clean Phase 115 endpoint before ordinary paired gating resumes.

### Static and documentation gate before postmortem

The final repository-wide Ruff command returned `All checks passed!`; Python
`compileall -q` and `git diff --check` both exited 0. The remote lint failure
reported at the original Block 12 start remains resolved, including focused
duplicate-key `F601` coverage.

The final documentation commands were:

```text
.venv/bin/python scripts/validate_docs_links.py
# {"invalid_diagnostic": true, "invalid_exit_code": 1,
#  "valid_exit_code": 0}

env UV_CACHE_DIR=/tmp/sw-phase115-final-cross-doc2-uv-cache \
  uv run --extra docs mkdocs build --strict \
  --site-dir /tmp/sw-phase115-final-cross-doc2-site
# exit 0; Documentation built in 2.90 seconds
```

The link validator proved its invalid fixture fails and its valid graph passes.
Strict MkDocs emitted the Material-for-MkDocs warning about future MkDocs 2.0
incompatibility and exactly three known unnav pages:
`scenarios/calibration-template.md`,
`scenarios/depth-checklist-template.md`, and `scenarios/gap-audit.md`. It
reported no broken link, missing file, duplicate nav entry, or build error;
Block 16 and the Phase 115 devlog are navigated.

The initial formal `$cross-doc-audit` returned a provisional **PASS** with this
disposition:

| Area | Result | Evidence / boundary |
|---|---|---|
| Roadmap and devlog alignment | PASS | Block 13, the devlog index, and this log identify Phase 115 as the active closure phase; Phase 116 is next and unstarted |
| Remediation traceability | PASS | REM-028 alone is in the closure sequence; REM-029/030 and REM-041--045 retain explicit phase owners and nonclaims |
| Contract accuracy | PASS | strict calibration, targeting/loadout/exposure/checkpoint schemas and fail-closed restore semantics match production source; historical visibility is interval-scoped |
| Production evidence | PASS | every applicable `D/L/W/E/X/O/P` gate has behavioral evidence; Debecka, slow/API/E2E timeouts, REM-029, and REM-041 are disclosed rather than counted as passes |
| Architecture accuracy | PASS | runtime factory/context/engine/battle identity, once-per-interval preparation, shared movement/direct-fire consumption, and excluded routed owners match source |
| API accuracy | PASS | backend models/routes, stored paired projections, replay decoder, frontend discriminated types/query keys, and privileged default agree; caller authorization remains REM-041 |
| Data and catalog accuracy | PASS | 442/442 mappings, 52 loaded scenarios, 8,388 initial units, 1,128 override units, zero errors/warnings, and one intentional sensorless classification |
| Public status accuracy | PASS | public pages make no historical-validation, timing, player-authorization, nonempty-FOW continuation, mount-topology, threat-optimization, estimator-fidelity, or scripted-action completion claim |
| Navigation and links | PASS | strict build and diagnostic link validator pass; the three intentional unnav templates are named above |
| Provider-context alignment | PASS | `CODEX.md`, `AGENTS.md`, and maintained `CLAUDE.md` agree on the phase gates, evidence standard, follow-ups, and no-papering rule |

The independent postmortem subsequently found that Block 13 and the REM-028
body still said broader validation and documentation remained even though this
section recorded both as complete. That contradiction was repaired in the
status transition and checked again rather than preserving the provisional
claim. The tracked limitations are REM-016, REM-020/021, REM-029/030,
REM-035/036, and REM-041--045; none is silently absorbed into REM-028.

## Postmortem

Two independent read-only reviews reconstructed the roadmap, remediation,
specification, production, test, and documentation contracts. They found no
stub, placeholder, unconditional-success path, newly swallowed exception,
unowned runtime state, or hidden completion claim in the Phase 115 production
diff. They did find two genuine closure blockers, both resolved before the
status transition:

1. the final API partition reached its 2,700-second contention cap without a
   pytest summary or JUnit file, so it could not prove that the one real
   `RunManager`/SQLite/API persistence witness had executed; and
2. Block 13 and the REM-028 body still described broader validation and the
   documentation audit as pending after this devlog recorded them complete.

The exact production API witness was therefore rerun directly:

```text
uv run --no-sync pytest -q \
  tests/api/test_phase115_targeting_production_api.py::test_real_run_persists_exact_and_side_safe_targeting_frames \
  --strict-markers --strict-config
# pytest did not start: uv could not create a cache temporary file on the
# sandbox's read-only /home/csmith/.cache/uv mount

.venv/bin/python -m pytest -q \
  tests/api/test_phase115_targeting_production_api.py::test_real_run_persists_exact_and_side_safe_targeting_frames \
  --strict-markers --strict-config
# sandbox attempt produced no output/progress for about seven minutes and was
# interrupted with exit 130, matching the documented aiosqlite worker wakeup
# limitation; it is not counted as a test result

.venv/bin/python -m pytest -q \
  tests/api/test_phase115_targeting_production_api.py::test_real_run_persists_exact_and_side_safe_targeting_frames \
  --strict-markers --strict-config
# host execution: 1 passed in 1.44s; command wall time 2.498s; exit 0
```

That test creates the real run manager and database, executes the production
runtime, persists its frames, reopens the stored result through the API
boundary, and proves exact privileged plus side-filtered targeting evidence.
It closes the missing `P` witness; the owner-approved broad API timeout remains
a qualified regression result rather than being relabeled a pass. The stale
roadmap/remediation wording was corrected together with this status transition
and re-audited below.

| Postmortem area | Verdict | Evidence / disposition |
|---|---|---|
| Scope | On target | The shared targeting owner, typed loadout roles, movement/direct-fire consumers, format-115 state, diagnostics, API, and frontend are all required by REM-028; unrelated findings are separately owned |
| Quality | High | One immutable interval decision, strict revalidation, exact runtime identity, fail-closed schema/topology checks, and no stubs or papered-over fallbacks |
| Integration | Fully proven, with owner-qualified broad-run timing | `D/L/W/E/X/O/P` each have production behavior and negative/control evidence; the focused real database/API witness closes the sole unobserved stage |
| New deficits | Recorded, not absorbed | REM-041/P1/Phase 128, REM-042/P1/129, REM-043/P2/130, REM-044/P1/131, and REM-045/P1/132 retain exact evidence, priority, and exit criteria |
| Validation | Accepted with explicit exclusions | 11,743/11,743 standard nodes passed; complete benchmark/data/determinism/frontend/static/docs gates passed; slow/API/E2E contention limits and Debecka 4/10 are disclosed above and are not called passes |
| Action items | None before closure | Phase 116 must promote the clean Phase 115 benchmark endpoint; REM-029/030 and REM-041--045 remain queued; hosted post-push workflows remain the independent environment control |

The postmortem verdict is **PASS**. Debecka is an honest REM-030 historical and
victory-policy signal after removal of invalid F-14/M61 ground fire, not a
reason to retune REM-028. Ordinary nonempty FOW continuation remains REM-029.
The qualified API/E2E and partial slow evidence records environmental
contention without granting behavioral credit to an unexecuted node. Phase 115
is complete and REM-028 is closed; Phase 116 remains unstarted until this
single coherent phase commit exists.

### Final status and cross-document verification

The independent post-transition audit first caught that the devlog index did
not explicitly identify Phase 116 as next and unstarted, then caught an
incorrect three-hyphen fragment in the new roadmap link. Both were corrected;
the final independent verdict was **PASS** across all ten cross-document audit
areas. It confirmed Phase 115 complete, REM-028 closed, Phase 116/REM-029 next
and unstarted, the exact 12,248-node inventory, honest qualification language,
and no stale current-state contradiction. Historical Phase 113/114 statements
remain scoped historical records.

Fresh transitioned-tree commands were:

```text
.venv/bin/python scripts/validate_docs_links.py
# {"invalid_diagnostic": true, "invalid_exit_code": 1,
#  "valid_exit_code": 0}; exit 0

env UV_CACHE_DIR=/tmp/sw-phase115-post-status-uv-cache \
  uv run --no-sync mkdocs build --strict \
  --site-dir /tmp/sw-phase115-post-status-site
# exit 0; Documentation built in 2.93 seconds

.venv/bin/ruff check .
# All checks passed!; exit 0

.venv/bin/python -m compileall -q api stochastic_warfare scripts tests
# exit 0

git diff --check
# exit 0
```

Strict MkDocs retained exactly the known Material/MkDocs 2.0 advisory and the
three intentional unnav pages named above; it reported no link, fragment,
navigation, or build error. The status-language search's only apparent stale
match was this postmortem's historical description of the contradiction it
repaired. No production file changed after the accepted runtime, scenario,
determinism, data, frontend, or broad-test evidence.

After this section was appended, the link validator again returned the same
exit-0 diagnostic JSON, `git diff --check` and repository-wide Ruff again
returned exit 0, and the otherwise identical strict build using
`/tmp/sw-phase115-final-status-uv-cache` and
`/tmp/sw-phase115-final-status-site` completed in 2.88 seconds with the same
one advisory and three intentional unnav pages.
