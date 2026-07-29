# Phase 109 - Equipment Mapping Integrity

**Status:** Complete

**Started:** 2026-07-28

**Completed:** 2026-07-28

## Why this phase exists

Production loadout construction is nominally exposed from
`simulation.scenario`, but it delegates to private helpers and name maps in the
simplified validation runner. Python dictionary literals silently overwrite
duplicate names; missing mappings, missing targets, and missing ammunition are
silently skipped; and unrelated equipment can acquire a fake combat
capability.

Phase 109 closes REM-010 with one strict typed registry and one
runtime-owned loadout builder. The durable contract is
[`docs/specs/equipment-mapping.md`](../specs/equipment-mapping.md).

## Authoritative contract

The specification and REM-010 require:

1. duplicate mapping declarations and duplicate scenario assignment keys fail
   before last-write-wins behavior;
2. exact/variant, constrained functional-analogue, and explicit unsupported
   dispositions are distinct;
3. mapping targets, ammunition, weapon categories, sensor types, domains, era
   gates, and scenario overrides are validated through the effective
   catalogs;
4. launcher/weapon attachments, carried stores, and non-runtime equipment are
   distinct, so a launcher-plus-round pair does not create two full launchers;
5. initial units, reinforcements, and checkpoint reconstruction use one
   injected typed production builder;
6. declared unsupported or invalid weapon/sensor equipment fails rather than
   disappearing from a live loadout;
7. the 22 tracked mapping occurrences and two no-sensor warnings are resolved
   without invented combat capability;
8. deterministic ordering, exact equipment links, atomicity, and checkpoint
   continuation remain intact; and
9. relevant data validation and repository-wide Ruff are green.

The repository owner additionally asked Phase 109 to clear the remote Python
lint failure. Its six mapping-key findings are REM-010 scope. The two
no-placeholder f-string findings are a narrowly pulled-forward part of
REM-013; REM-013 remains open for its broader CI/coverage-trust contract.

## Non-goals

- No physical weapon/sensor tuning or historical calibration.
- No new EW, mine-detection, breaching, navigation, carrier, or UAV-spotting
  subsystem.
- No Phase 110 work.
- REM-016, REM-020/021, REM-022/023, and the remaining REM-013 contract stay
  independently visible.

## Production trace at phase start

Initial loading, reinforcement registration, and fresh checkpoint
reconstruction all reach `simulation.scenario.build_unit_loadouts()`. That
untyped function calls private `ScenarioRunner._assign_weapons()` and
`_assign_sensors()` methods. The helpers own the maps and silently continue on
unmapped names, missing definitions, and missing ammunition.

The production consumer chain is:

`unit/scenario YAML -> ScenarioLoader -> private validation helper ->
SimulationContext.unit_weapons/unit_sensors -> battle/detection ->
checkpoint/recorder/API`

The formal red baseline and pre-implementation scenario outcomes were captured
from the clean phase-start revision before production implementation.

## Verification plan

- Dedicated Phase 109 red/green tests for registry, builder, semantic
  validation, sensor policy, production outcomes, failure atomicity, and
  checkpoint continuation.
- Existing Phase 103/107 loadout, era-gate, checkpoint, scenario-loader, and
  API-frame selections.
- Full data validation across every unit and scenario.
- Pre/post scenario evaluation for affected representative scenarios using
  identical seeds and recorded semantic rows.
- Same-seed, no-RNG-draw, deterministic ordering, hash-seed where useful, and
  fresh-restore continuation proofs.
- Repository-wide Ruff including `scripts/`, default backend suite, strict
  MkDocs, and `git diff --check`.
- `$research-military` and `$design-review` before implementation.
- `$validate-conventions`, `$audit-determinism`, `$validate-data`,
  `$evaluate-scenarios`, and `$simplify` after implementation.
- `$update-docs`, `$cross-doc-audit`, then `$postmortem`, followed by the one
  Phase 109 commit. The commit may be pushed under the owner's later explicit
  authorization so the repaired remote lint workflow can be verified.

## Reconnaissance findings and disposition

Read-only reconnaissance reported two adjacent defects:

- invalid `french_old_guard` crew skill is broadly caught and logged as a
  missing unit while two scenario validations continue; and
- the API ammunition-percentage frame consumer appears to treat typed weapon
  attachment tuples as direct `WeaponInstance` objects.

The crew-skill defect was reproduced and recorded as REM-024 for Phase 112.
The API finding was reproduced in a production frame test and repaired within
Phase 109 because the new typed attachment shape otherwise broke an existing
public boundary. Neither was accepted on source-search or no-crash evidence.

## Start gate and machine envelope

The phase started from the requested clean revision:

```text
git pull --ff-only origin main
git status --short
git rev-parse HEAD
# 70e72f5a2b18aa0981d9b4313406b994ae9a5dd6
# clean worktree; main synchronized with origin/main
```

`CODEX.md`, `AGENTS.md`, the Block 12 phase plan, REM-010, Phase 108's devlog,
and the applicable repository skills were read before edits. The host exposed
32 logical CPUs and approximately 62 GiB RAM, with approximately 58 GiB
available during validation. Independent suites and scenario evaluations were
run concurrently where isolation allowed; `pytest-xdist` was not installed,
so each pytest invocation itself remained serial.

All Python commands below used
`UV_CACHE_DIR=/tmp/phase109-uv` to keep the dependency cache inside the writable
temporary boundary.

## Baseline and production red evidence

### Static baseline

```text
UV_CACHE_DIR=/tmp/phase109-uv uv run ruff check stochastic_warfare/ api/ tests/ scripts/
# 8 errors:
# - 6 F601 duplicate dictionary keys in the equipment maps
# - 2 F541 no-placeholder f-strings in validation tests

UV_CACHE_DIR=/tmp/phase109-uv uv run python scripts/validate_scenario_data.py
# 184 unit YAML files
# 22 mapping-error occurrences
# 2 unclassified no-sensor warnings
# 51 scenario YAML files
```

The six overwritten names included the AIM-7M, AIM-9L, KPVT, M203, CSRL, and
mine-detection entries. The production consequences were not cosmetic:

- the B-52H CSRL resolved to a Stinger launcher;
- EA-18G jamming equipment resolved to a Vulcan/rifle-ammunition proxy;
- SA-6 could load without its authored fire-control radar; and
- missing targets/ammunition were skipped by private validation-runner helpers.

### Behavioral red proofs

The implementation was driven by failing production or exact-boundary tests,
including late adversarial/simplify findings:

| Red control | Phase-start or pre-fix result |
|---|---|
| Duplicate `weapon_assignments` through `HistoricalDataLoader` and `CampaignDataLoader` | Two expected exceptions were not raised |
| Duplicate assignments through `_run_helpers` and `doctrine_compare` | Two expected exceptions were not raised |
| Exact target-role history separated by a functional analogue | Conflicting final exact role was accepted |
| Type 42 Sea Dart against an aerial target | Naval route consumed 3 missiles as an anti-ship salvo instead of one SAM |
| Two ready SA-6 batteries under a one-engager side cap | First battery's cooldown-only dispatch consumed the cap; second live-ammo delta was zero |
| Iowa nine-gun main battery | Production gunnery received `num_guns=1` and consumed one shell |
| Kilo six-tube battery | Production subsurface engine received one call and consumed one torpedo |
| Four Mk 7 depth-charge throwers over multiple ticks | Engine calls were `[24, 24, 24, 24, 24]`, not `[4, 4, 4]` |
| Two-rpm aggregate Harpoon battery over multiple ticks | Salvos were `[2, 2, 2]`, not `[1, 1, 1]` |
| Jutland Iron Duke ten-gun fallback over 60 seconds | Twelve one-round calls, not two ten-round salvos |
| Iowa nine-gun shore-fire route over 60 seconds | Twelve one-round calls, not two nine-round salvos |

The last four reds were especially important: runtime construction already
scaled rate of fire by physical-system multiplicity, while specialized routes
also reused that rate as salvo quantity or discretized it a second time. Those
tests prevented a structurally tidy but physically incorrect mapping
implementation from closing.

## Implementation

### One typed mapping authority

`simulation/equipment_mappings.py` now declares an ordered immutable record
sequence rather than overwrite-prone dictionary literals. Registry
construction rejects duplicate category/name keys before building lookup
indexes, including identical duplicate values. It also retains exact
target-role history across intervening functional analogues, so declaration
order cannot hide a conflict.

The final registry census is:

```text
records 442
types {'SensorAttachmentMapping': 129,
       'SensorNonRuntimeMapping': 15,
       'WeaponAttachmentMapping': 272,
       'WeaponNonRuntimeMapping': 17,
       'WeaponStoreMapping': 9}
references {'exact': 243, 'functional_analogue': 145,
            'n/a': 32, 'variant': 22}
dispositions {'attachment': 401, 'non_runtime': 32, 'store': 9}
```

Every supported record validates its effective catalog target, typed role,
category/type, complete compatible-ammunition set, guidance/caliber constraints,
and target/detection domains. Functional analogues carry a same-role
rationale/source and, where needed, one of 52 equipment-specific reviewed
sensor-source overrides. Store records resolve ammunition and require a
compatible attachment on the same unit without creating another launcher or
magazine. Non-runtime records preserve the authored item and an explicit
boundary reason without inventing capability.

### Strict input boundary

`core/strict_yaml.py` supplies the shared duplicate-key-rejecting loader.
Scenario YAML, historical/campaign validation data, scenario batch helpers,
and doctrine comparison all consume it before a Python mapping can overwrite
`weapon_assignments`. Scenario-local overrides then pass through the same
registry/catalog/semantic validation as built-in records. Unknown, stale, or
conflicting reachable overrides fail preflight.

### Runtime-owned construction

`simulation/loadouts.py` owns immutable typed resolution, attachment, builder,
and result structures. `ScenarioLoader` creates one `RuntimeLoadoutBuilder`
after loading the effective global/era catalogs and before force
construction. That exact object serves:

1. initial units;
2. atomic reinforcement admission; and
3. checkpoint-only fresh unit reconstruction.

The validation runner and static validator consume this boundary; production
no longer imports private validation-runner assignment helpers. Every input
unit ID receives explicit weapon/sensor tuples and ordered resolution rows,
including empty tuples. Each live instance links to its exact owning
`EquipmentItem`, and construction reads neither RNG nor wall clock.

Checkpoint schema 109 stores the canonical builder fingerprint and transparent
per-unit resolution topology. Restore checks effective configuration,
fingerprint, equipment identity/order, store/non-runtime decisions, and
source/target/runtime system counts before mutating clock, RNG, roster, or live
state. The API ammunition percentage consumer now reads typed attachments and
is covered by a production frame test.

### Data and semantic repair

The 22 phase-start mapping occurrences now resolve through exact definitions,
reviewed same-role variants/analogues, or honest non-runtime categories.
Notable corrections include:

- exact modern aircraft guns, missiles, racks, and targeting/fire-control
  sensors instead of unrelated proxies;
- exact historical small arms, naval batteries, ammunition, torpedoes, and
  air-defense definitions across all four historical eras;
- launcher/store separation for Javelin and Harpoon-style authored pairs;
- four exact radar definitions where generic sensor targets did not preserve
  the authored role;
- EW jammers, GPS/INS, countermine/breaching equipment, protective structures,
  flight decks/bomb-bay structure, and other noncombat items retained as
  non-runtime rather than fake guns or surveillance sensors;
- `civilian_noncombatant` explicitly classified
  `intentionally_none` with no invented sensor; and
- `insurgent_squad` given an authored visual-observation sensor.

Barak-1 and RIM-116 no longer advertise `NAVAL` as an incoming-missile domain:
runtime `Domain.NAVAL` means ships, not sea-skimming threats. RIM-116 is typed
as an air-defense missile rather than generic close-in gun defense. Sea Dart
and other shipboard SAMs route to the air-defense path before naval
anti-surface dispatch.

### Physical system counts and live routing

Explicit attachment counts are validated as source-system count, target
definition count, and one positive integral runtime multiplier. The builder
scales cadence, magazine capacity, and barrel life once and records the counts
in topology/fingerprints.

Specialized live routes now use
`burst_size * runtime_system_multiplier` as synchronized salvo quantity and
multiply the already scaled cooldown by `runtime_system_multiplier`. This
preserves each physical system's base cadence without squaring multiplicity or
mistaking rounds-per-minute for rounds-per-salvo. Production multi-tick tests
prove:

- four depth-charge throwers deliver three four-charge patterns at 0, 10, and
  20 seconds, consuming 12;
- a two-rpm aggregate Harpoon battery launches one missile at 0, 30, and
  60 seconds, consuming 3;
- Iron Duke's ten-gun battery delivers two ten-round salvos in the first
  minute through the reachable WWI fallback; and
- Iowa's nine-gun battery delivers two nine-round shore-fire salvos in the
  first minute.

The same live-ammunition delta, rather than attempted dispatch, now decides
whether a routed engagement consumes a side engagement cap or ATO sortie.
Composite torpedo tubes make one deterministic engine call per fired torpedo
and aggregate hit damage; composite naval guns pass the physical gun count.
All routes publish exact aggregate `AmmoExpendedEvent` quantities and generic
engagement exposure.

### Performance-sensitive integration

Corrected, longer-range loadouts increased the number of units reaching the
LOD classification path. The implementation groups positions by LOD state
instead of rebuilding the same structures per unit. A fixed
`benchmark_battalion`, seed-42, 20-tick workload produced closure repetitions
`3.657349`, `3.625118`, and `3.677497` seconds (median `3.657349`) versus a
pre-optimization median `9.697430`, approximately 2.65x faster with identical
semantic end states. Matched ten-tick `cProfile` captures reduced
`_classify_lod_tiers` from 29.170 seconds cumulative to 0.308 seconds; a final
20-tick closure capture reported 55,066,878 calls and 0.620 seconds cumulative
in that function. Threading waits became the largest cost. This is a
same-machine implementation result, not a cross-machine performance guarantee.

The phase used `/tmp/phase109_profile_workload.py` with SHA-256
`34cf23ba426d82445252731bac90bbffac0a4f1b2713f89c67d1576c5dfa5df2`.
It loads `benchmark_battalion`, runs `SimulationEngine` for the requested tick
count, prints each elapsed time plus a sorted semantic status tuple, and
checks equality across repetitions. Exact performance commands were:

```text
# Run at the pre-optimization source state, then again at the final source state.
UV_CACHE_DIR=/tmp/phase109-uv uv run python /tmp/phase109_profile_workload.py --scenario benchmark_battalion --seed 42 --ticks 20 --repetitions 3

# Run at the corresponding pre- and post-optimization source states.
UV_CACHE_DIR=/tmp/phase109-uv uv run python -m cProfile -o /tmp/phase109-preopt-battalion.prof /tmp/phase109_profile_workload.py --scenario benchmark_battalion --seed 42 --ticks 10 --repetitions 1
UV_CACHE_DIR=/tmp/phase109-uv uv run python -m cProfile -o /tmp/phase109-postopt-battalion.prof /tmp/phase109_profile_workload.py --scenario benchmark_battalion --seed 42 --ticks 10 --repetitions 1

UV_CACHE_DIR=/tmp/phase109-uv uv run python -c 'import pstats
for path in ("/tmp/phase109-preopt-battalion.prof","/tmp/phase109-postopt-battalion.prof"):
 stats=pstats.Stats(path)
 print(path,stats.total_calls)
 stats.sort_stats("cumulative").print_stats("_classify_lod_tiers")'

# Fresh closure wall-clock and 20-tick profile commands.
UV_CACHE_DIR=/tmp/phase109-uv uv run python /tmp/phase109_profile_workload.py --scenario benchmark_battalion --seed 42 --ticks 20 --repetitions 3
UV_CACHE_DIR=/tmp/phase109-uv uv run python -m cProfile -o /tmp/phase109-closure.prof /tmp/phase109_profile_workload.py --scenario benchmark_battalion --seed 42 --ticks 20 --repetitions 1
UV_CACHE_DIR=/tmp/phase109-uv uv run python -c 'import pstats
stats=pstats.Stats("/tmp/phase109-closure.prof")
print(stats.total_calls)
stats.sort_stats("cumulative").print_stats("_classify_lod_tiers")'
```

## Production capability evidence

| Stage | Evidence |
|---|---|
| Declared | Frozen discriminated mapping records; typed sensor policy, attachment/store/non-runtime outcomes, builder inputs/results, count topology, and explicit errors |
| Loaded | `ScenarioLoader` loads effective catalogs and preflights all reachable initial/reinforcement definitions and overrides before unit publication |
| Wired | One retained builder serves initial force, reinforcement, and fresh restore; battle/detection consume its exact typed outputs |
| Enabled | N/A: authored loadouts are mandatory, not optional; era gates and unsupported records are exercised negative controls |
| Exercised | Exact units fire/detect with corrected attachments; duplicate/unknown/missing/semantic/era/store/policy controls fail atomically |
| Outcome-affecting | Corrected sensors alter detection; corrected weapons alter live ammo/events/battle state; former jammers/structures cannot act; composite counts alter engine calls and expenditure |
| Persisted/exposed | Schema-109 fingerprint/topology and live state survive exact deterministic continuation; API frames expose ammunition from typed attachments |

## Determinism and scenario evaluation

Builder construction under hash seeds 1 and 777 reproduced builder fingerprint
`7c99c1c977609df535f07dce302bb864aeec1642247c03c046d516d1fcb2009a`
and topology SHA-256
`38145d61cc12def891a9633ad11fe8d5397159ed21601276c37cd9b185cf8805`,
with 21 topology entries, 69 count rows, and maximum runtime multiplier 46.
Rebuilding left RNG and clock state unchanged. Maintained continuation tests
prove exact ordered events/state after fresh restore.

The exact independent-process probe, invoked once with `PYTHONHASHSEED=1` and
once with `PYTHONHASHSEED=777`, was:

```text
PYTHONHASHSEED=1 UV_CACHE_DIR=/tmp/phase109-uv uv run python -c 'import hashlib,json
from pathlib import Path
from stochastic_warfare.simulation.scenario import ScenarioLoader
ctx=ScenarioLoader(Path("data")).load(Path("data/eras/ww2/scenarios/midway/scenario.yaml"),seed=42)
topology={unit_id:[resolution.topology() for resolution in resolutions] for unit_id,resolutions in sorted(ctx.equipment_resolutions.items())}
rows=[row for resolutions in topology.values() for row in resolutions if row.get("runtime_system_multiplier") is not None]
payload=json.dumps(topology,sort_keys=True,separators=(",",":"))
print(ctx.loadout_builder.fingerprint())
print(hashlib.sha256(payload.encode()).hexdigest())
print(len(topology),len(rows),max(row["runtime_system_multiplier"] for row in rows))'

PYTHONHASHSEED=777 UV_CACHE_DIR=/tmp/phase109-uv uv run python -c 'import hashlib,json
from pathlib import Path
from stochastic_warfare.simulation.scenario import ScenarioLoader
ctx=ScenarioLoader(Path("data")).load(Path("data/eras/ww2/scenarios/midway/scenario.yaml"),seed=42)
topology={unit_id:[resolution.topology() for resolution in resolutions] for unit_id,resolutions in sorted(ctx.equipment_resolutions.items())}
rows=[row for resolutions in topology.values() for row in resolutions if row.get("runtime_system_multiplier") is not None]
payload=json.dumps(topology,sort_keys=True,separators=(",",":"))
print(ctx.loadout_builder.fingerprint())
print(hashlib.sha256(payload.encode()).hexdigest())
print(len(topology),len(rows),max(row["runtime_system_multiplier"] for row in rows))'
```

The predeclared evaluator manifest was run first from the clean phase-start
copy at `/tmp/phase109-baseline-tree.tjvdCJ`, then from the repository
worktree. Each `(scenario, seed)` pair expanded to the exact invocation shown
inside this executable manifest:

```text
phase109_runs=(
  debecka_pass:42 debecka_pass:43 debecka_pass:44
  fallujah_phase_line_fran:42 fallujah_phase_line_fran:43 fallujah_phase_line_fran:44
  gulf_war_ew_1991:42 gulf_war_ew_1991:43 gulf_war_ew_1991:44
  khafji:42 khafji:43 khafji:44
  korean_peninsula:42 korean_peninsula:43 korean_peninsula:44
  suwalki_gap:42 suwalki_gap:43 suwalki_gap:44
  cambrai:42 eastern_front_1943:42 falklands_san_carlos:42
  jutland:42 midway:42 salamis:42 somme_july1:42 trafalgar:42
)
for state in baseline current; do
  if [ "${state}" = baseline ]; then
    phase109_root=/tmp/phase109-baseline-tree.tjvdCJ
  else
    phase109_root=/home/csmith/projects/stochastic-warfare
  fi
  for run in "${phase109_runs[@]}"; do
    scenario="${run%:*}"
    seed="${run#*:}"
    (
      cd "${phase109_root}"
      UV_CACHE_DIR=/tmp/phase109-uv uv run python scripts/evaluate_scenarios.py --scenario "${scenario}" --seed "${seed}" --no-details --output "/tmp/phase109-${state}-${scenario}-${seed}.json"
    )
  done
done
```

The early Salamis baseline artifact used the equivalent explicit path
`/tmp/phase109-baseline-salamis-s42.json`. The phase-start Taiwan Strait probe
used:

```text
UV_CACHE_DIR=/tmp/phase109-uv uv run python scripts/evaluate_scenarios.py --scenario taiwan_strait --seed 42 --no-details --output /tmp/phase109-baseline-taiwan_strait-42.json
```

It was interrupted with Ctrl-C and exit 130 and is excluded from the
before/after table rather than presented as a baseline.

The predeclared production comparison used the same scenario IDs and seeds on
the clean phase-start tree and final worktree. Tuple fields below are
`winner/condition/ticks/casualties/engagements`; an empty final issue field
means no evaluator diagnostic.

| Scenario | Seed | Phase-start tuple | Final tuple / issue |
|---|---:|---|---|
| `debecka_pass` | 42 | blue/force_destroyed/67/37/540 | blue/force_destroyed/175/51/4057 |
| `debecka_pass` | 43 | blue/force_destroyed/69/37/439 | blue/force_destroyed/204/52/5308 |
| `debecka_pass` | 44 | blue/force_destroyed/71/36/516 | blue/force_destroyed/205/54/4607 |
| `fallujah_phase_line_fran` | 42 | blue/force_destroyed/156/104/4069 | blue/force_destroyed/115/68/1643 |
| `fallujah_phase_line_fran` | 43 | blue/force_destroyed/162/104/4372 | blue/force_destroyed/107/68/1262 |
| `fallujah_phase_line_fran` | 44 | blue/force_destroyed/155/108/3978 | blue/force_destroyed/114/68/1621 |
| `gulf_war_ew_1991` | 42 | blue/time_expired/4320/22/976 | blue/time_expired/4320/24/600 |
| `gulf_war_ew_1991` | 43 | blue/time_expired/4320/22/976 | blue/time_expired/4320/24/720 |
| `gulf_war_ew_1991` | 44 | blue/time_expired/4320/22/976 | blue/time_expired/4320/24/600 |
| `khafji` | 42 | blue/force_destroyed/1464/81/1377 | blue/force_destroyed/716/57/758 |
| `khafji` | 43 | blue/force_destroyed/1220/64/2998 | blue/force_destroyed/681/59/589 |
| `khafji` | 44 | blue/force_destroyed/1098/66/2839 | blue/force_destroyed/680/58/592 |
| `korean_peninsula` | 42 | blue/force_destroyed/149/15/101 | blue/force_destroyed/144/16/89 |
| `korean_peninsula` | 43 | blue/force_destroyed/145/16/94 | blue/force_destroyed/144/15/88 |
| `korean_peninsula` | 44 | blue/force_destroyed/143/16/88 | blue/force_destroyed/144/16/89 |
| `suwalki_gap` | 42 | blue/force_destroyed/12/9/153 | blue/force_destroyed/10/9/127 |
| `suwalki_gap` | 43 | blue/force_destroyed/16/8/200 | blue/force_destroyed/8/12/105 |
| `suwalki_gap` | 44 | blue/force_destroyed/12/8/152 | blue/force_destroyed/10/8/126 |
| `cambrai` | 42 | british/force_destroyed/425/2/16 | british/force_destroyed/433/2/14 / `MANY_STUCK_UNITS(4/7)` |
| `eastern_front_1943` | 42 | blue/max_ticks/20000/8/362 | red/force_destroyed/251/10/340 |
| `falklands_san_carlos` | 42 | blue/time_expired/42/8/106 | blue/force_destroyed/12/5/42 |
| `jutland` | 42 | british/time_expired/7202/20/416 | british/time_expired/603/24/253 |
| `midway` | 42 | usn/time_expired/29/10/65 | usn/force_destroyed/4/8/32 |
| `salamis` | 42 | greek/force_destroyed/52/4/73 | greek/force_destroyed/52/5/81 |
| `somme_july1` | 42 | german/time_expired/618/5/50 | german/time_expired/618/5/50 |
| `trafalgar` | 42 | british/force_destroyed/178/3/36 | british/time_expired/5760/2/5 |

The differences are expected consequences of removing invalid capability:

- Debecka, Fallujah, Khafji, Korean Peninsula, and Suwalki now use exact
  small-arms, vehicle, aircraft, air-defense, ammunition, and sensor
  envelopes rather than missing/proxy loadouts.
- Gulf War EW removes jamming/navigation structures as fake guns/sensors and
  uses exact aircraft effectors.
- Cambrai replaces an 800 m Lewis-gun proxy on the Mark IV with its exact
  6-pounder at 6,675 m. The battle outcome remains British, while the evaluator
  mislabels legitimate standoff as stuck; REM-025 owns that diagnostic.
- Eastern Front, Midway, Salamis, and Falklands expose exact era/naval/air
  weapons, sensor domains, stores, and physical counts.
- Jutland's ten-gun batteries now deliver physical salvos at base-gun cadence,
  producing earlier destruction and coarse-resolution advance to the same
  British time-expiry result.
- Trafalgar's counted batteries likewise fire physical salvos; the result
  remains British but reaches the declared time limit with two casualties.
- Somme is bit-for-bit stable on all recorded semantic fields.

Because Phase 109 intentionally removes wrong weapons and changes live ranges,
ammunition, sensors, and physical system counts, identical outcomes were not
an acceptance criterion. No row is presented as historical calibration.

After the final simplify fixes, ten affected naval/shore scenarios were run
twice at seed 42. Semantic JSON comparisons removed only `duration_wall_s` and
`scenario_path` and were empty for every pair:

```text
final_scenarios=(salamis trafalgar jutland midway falklands_san_carlos falklands_naval falklands_campaign ins_hanit_2006 taiwan_strait khafji)
for scenario in "${final_scenarios[@]}"; do
  UV_CACHE_DIR=/tmp/phase109-uv uv run python scripts/evaluate_scenarios.py --scenario "${scenario}" --seed 42 --no-details --output "/tmp/phase109-final-${scenario}-a.json"
  UV_CACHE_DIR=/tmp/phase109-uv uv run python scripts/evaluate_scenarios.py --scenario "${scenario}" --seed 42 --no-details --output "/tmp/phase109-final-${scenario}-b.json"
done

UV_CACHE_DIR=/tmp/phase109-uv uv run python -c 'import json
from pathlib import Path
names=("salamis","trafalgar","jutland","midway","falklands_san_carlos","falklands_naval","falklands_campaign","ins_hanit_2006","taiwan_strait","khafji")
def semantic(path):
 data=json.loads(path.read_text())
 for row in data:
  row.pop("duration_wall_s",None); row.pop("scenario_path",None)
 return data
for name in names:
 left=Path(f"/tmp/phase109-final-{name}-a.json")
 right=Path(f"/tmp/phase109-final-{name}-b.json")
 print(name, semantic(left)==semantic(right))'
# all ten rows printed True
```

| Scenario | Final outcome | Issues |
|---|---|---|
| `salamis` | greek/force_destroyed; 52 ticks, 5 casualties, 81 engagements | None |
| `trafalgar` | british/time_expired; 5,760 ticks, 2 casualties, 5 engagements | None |
| `jutland` | british/time_expired; 603 ticks, 24 casualties, 253 engagements | None |
| `midway` | usn/force_destroyed; 4 ticks, 8 casualties, 32 engagements | None |
| `falklands_san_carlos` | blue/force_destroyed; 12 ticks, 5 casualties, 42 engagements | None |
| `falklands_naval` | blue/force_destroyed; 50 ticks, 1 casualty, 7 engagements | None |
| `falklands_campaign` | blue/force_destroyed; 46 ticks, 7 casualties, 56 engagements | None |
| `ins_hanit_2006` | blue/time_expired; 1,440 ticks, 2 casualties, 14 engagements | None |
| `taiwan_strait` | blue/force_destroyed; 8 ticks, 15 casualties, 136 engagements | None |
| `khafji` | blue/force_destroyed; 716 ticks, 57 casualties, 758 engagements | None |

The phase-start Taiwan Strait evaluator did not complete and was interrupted
with exit 130; it is not used as a before/after claim. Two final current runs
are deterministic and issue-free.

## Independent review and simplification

The military-data review constrained every functional analogue to the same
modeled role and moved unmodeled EW, navigation, engineering, protection, and
facility equipment to explicit non-runtime decisions. No weapon/sensor
performance was tuned to obtain a scenario result.

The design review kept orchestration in `simulation`, required preflight before
context publication, retained exact live object links, and made the builder
fingerprint/topology part of restore compatibility.

Adversarial review found and drove repairs for:

- strict duplicate loading in historical/campaign and tool paths;
- shipboard SAM routing;
- cooldown-only pseudo-engagement accounting;
- naval-gun and torpedo multiplicity;
- order-dependent exact target-role conflict detection; and
- live-multiplicity persistence and API exposure.

The first `$simplify` verdict was not ready because depth-charge and Harpoon
routes squared or misused cadence. Its bounded follow-up then found the
reachable Jutland fallback and matching shore-fire formula. All four received
production multi-tick red/green tests and one shared aggregate-salvo policy.
The final `$simplify` verdict is **CLEAN**; its fresh focused selection reported
41 passing tests and no concrete remaining blocker.

Convention, determinism, data, scenario, and performance reviews found no
unresolved Phase 109 blocker. They did surface three independent validation
trust items: REM-024 (hidden invalid crew skill), REM-025 (false stuck-unit
diagnostic), and REM-026 (contradictory benchmark threshold). REM-020/021
remain the explicit live-logistics follow-ups; REM-022/023 remain assigned to
Phase 112.

## Cross-document audit

The first `$cross-doc-audit` correctly failed five documentation defects:
REM-010's interim evidence matrix lagged the closure-review evidence; the
public unit/ammunition examples did not match their pydantic models; the
mapping spec conflated disposition with reference kind; several supporting
results lacked exact command provenance; and `CLAUDE.md` still advertised the
Phase 108 baseline. Those defects were corrected rather than waived.

The independent re-audit verdict is **PASS**:

| Audit surface | Result |
|---|---|
| Roadmap, devlog, README, docs-index status | PASS — all closure surfaces aligned before postmortem and now consistently mark Phase 109 complete |
| Remediation traceability | PASS — REM-010 has D/L/W/X/O/P evidence; REM-020/021 and REM-022--026 remain explicit |
| Contract accuracy | PASS — disposition and reference kind are separate typed axes |
| Production capability substance | PASS — claims trace through builder, battle/detection, checkpoint, recorder, and API |
| Exact evidence provenance | PASS — profile, hash-seed, evaluator, repeat-run, comparison, and validation commands are recorded |
| Architecture ownership | PASS — simulation owns the registry/builder and validation code is a consumer |
| API boundary | PASS — effective config and typed attachment ammunition exposure match the reference |
| Data/catalog reference | PASS — unit, weapon, and ammunition examples freshly validate against their current models and live mapping names |
| Public/provider context | PASS — README, docs landing page, and `CLAUDE.md` agree on counts and closure state |
| Navigation and links | PASS — new pages are in nav; only the seven pre-existing REM-022 fragments and three intentional omissions remain |

The re-audit also independently reproduced the 442-record census, confirmed
checkpoint schema 109 validates builder fingerprint/topology before mutation,
and compared all ten final scenario artifact pairs successfully. Its strict
MkDocs run passed in 2.49 seconds; `git diff --check` passed.

## Verification evidence

Final or final-code commands and results:

```text
UV_CACHE_DIR=/tmp/phase109-uv uv run pytest -q --tb=short tests/unit/test_phase_109*.py tests/integration/test_phase_109*.py
# 322 passed in 45.63s

UV_CACHE_DIR=/tmp/phase109-uv uv run pytest -q --tb=short -o addopts= tests/integration/test_phase_109_weapon_multiplicity.py::test_flower_depth_charge_count_preserves_live_multitick_cadence tests/integration/test_phase_109_weapon_multiplicity.py::test_harpoon_battery_rate_is_cadence_not_salvo_quantity tests/integration/test_phase_109_weapon_multiplicity.py::test_jutland_fallback_gunnery_preserves_ten_gun_cadence tests/integration/test_phase_109_weapon_multiplicity.py::test_iowa_shore_bombardment_preserves_nine_gun_cadence tests/unit/test_phase51_naval_combat.py
# 41 passed in 2.73s

UV_CACHE_DIR=/tmp/phase109-uv uv run pytest -q --tb=short -o addopts= tests/unit/test_phase43_domain_resolution.py tests/unit/test_phase51_naval_combat.py tests/unit/combat/test_naval_surface.py tests/unit/combat/test_naval_subsurface.py tests/unit/test_naval_surface.py tests/unit/test_phase_27c_naval.py
# 181 passed in 0.99s

UV_CACHE_DIR=/tmp/phase109-uv uv run python -m pytest --tb=short -q
# 10,755 passed, 21 skipped, 348 deselected, 6 warnings in 285.27s

UV_CACHE_DIR=/tmp/phase109-uv uv run pytest tests/api -q --tb=short -o addopts=
# 201 passed in 27.75s

UV_CACHE_DIR=/tmp/phase109-uv uv run pytest tests/e2e -q --tb=short -o addopts=
# 41 passed in 28.85s

UV_CACHE_DIR=/tmp/phase109-uv uv run pytest tests/validation/test_fallujah_phase_line_fran.py tests/validation/test_ins_hanit.py -q --tb=short -o addopts=
# 22 passed in 10.21s

UV_CACHE_DIR=/tmp/phase109-uv uv run pytest tests/validation/test_khafji.py -q --tb=short -o addopts=
# 7 passed in 148.51s

UV_CACHE_DIR=/tmp/phase109-uv uv run python scripts/validate_scenario_data.py
# 184 unit files; 679 authored WEAPON/SENSOR occurrences
# modern 102/394/244 distinct; ancient_medieval 20/67/34
# napoleonic 21/57/27; ww1 16/57/47; ww2 25/104/93
# 442/442 authored keys covered by 442 registry keys
# 0 unmapped, 0 stale, 51 scenarios, 0 errors, 0 warnings
# 1 explicit sensorless classification

UV_CACHE_DIR=/tmp/phase109-uv uv run python -c 'import re,yaml
from pathlib import Path
from stochastic_warfare.entities.loader import UnitDefinition
from stochastic_warfare.combat.ammunition import WeaponDefinition,AmmoDefinition
text=Path("docs/reference/units.md").read_text()
blocks=re.findall(r"```yaml\n(.*?)```",text,re.S)
for model,block in zip((UnitDefinition,WeaponDefinition,AmmoDefinition),blocks,strict=True):
 value=model.model_validate(yaml.safe_load(block))
 key=next(iter(model.model_fields))
 print(model.__name__,"OK",getattr(value,key))'
# UnitDefinition OK m1a2
# WeaponDefinition OK m256_120mm
# AmmoDefinition OK m829a3_apfsds

UV_CACHE_DIR=/tmp/phase109-uv uv run ruff check stochastic_warfare/ api/ tests/ scripts/
# All checks passed

UV_CACHE_DIR=/tmp/phase109-uv uv run --extra docs mkdocs build --strict
# exit 0; documentation built in 2.51s

git diff --check
# exit 0; no output
```

The default suite's 348 deselections come from the repository's configured
`slow`, `benchmark`, `terrain`, `api`, and `e2e` exclusions and ignored
API/E2E directories. Phase 109 separately ran its relevant slow historical
envelopes, all API tests, all E2E tests, exact data validation, and production
scenario evaluations. No frontend contract changed, so the frontend suite was
not claimed.

The six default warnings were one empty-chart legend warning, four Matplotlib
animation-deletion warnings, and one `datetime.utcnow()` deprecation. They are
unrelated to loadout construction. The validator itself returned zero
warnings; stderr also contained 79 separately classified loader/profile
diagnostics: two French Old Guard skips owned by REM-024 and 77 missing
commander-profile assignments owned by REM-023.

The strict documentation build reports the tool's MkDocs-2.0 compatibility
notice, three existing scenario-template pages intentionally outside `nav`,
and the seven historical missing fragments already enumerated by REM-022.
Phase 109's new devlog and specification are in navigation; no new missing
page or fragment was introduced.

The broad slow/benchmark sweep was not used as a green claim. It reached a
hard wall-clock Golan failure: final code took `140.744792` seconds versus
`214.77246345` seconds at the phase-start revision, but both exceed the test's
60-second assertion while the checked-in baseline is 500 seconds. REM-026
owns that contradictory trust boundary. The focused applicable slow envelopes
are recorded above and below.

The exact failing comparison commands were:

```text
UV_CACHE_DIR=/tmp/phase109-uv uv run pytest -q --tb=short -o addopts= tests/benchmarks/test_benchmarks.py::TestBenchmarkGolanHeights::test_wall_clock
# failed only the contradictory 60-second assertion; measured 140.744792s

(cd /tmp/phase109-baseline-tree.tjvdCJ && UV_CACHE_DIR=/tmp/phase109-uv uv run pytest -q --tb=short -o addopts= tests/benchmarks/test_benchmarks.py::TestBenchmarkGolanHeights::test_wall_clock)
# failed only the same assertion; measured 214.77246345s
```

The commit and authorized push occur only after this recorded postmortem and
status transition.

## Postmortem

**Verdict:** Complete. REM-010 is closed.

| Dimension | Verdict |
|---|---|
| Scope | On target; every declared Phase 109 and REM-010 behavior was delivered |
| Quality | High; the final simplify, cross-document, adversarial, and stub/fallback reviews found no unresolved blocker |
| Integration | Fully proven through strict ingestion, initial/reinforcement/restore loadouts, battle and detection outcomes, checkpoint continuation, recorder, validator, and API exposure |
| New deficits | REM-024 (P1), REM-025 (P2), and REM-026 (P1) are evidenced and assigned to Phase 112; none is missing Phase 109 behavior |
| Validation | All required focused, compatibility, default, API, E2E, applicable slow, data, documentation, lint, determinism, scenario, and performance gates passed, with the benchmark-trust failure and every exclusion/warning disclosed above |
| Action items | None before closure; REM-013, REM-016, REM-020/021, REM-022/023, and REM-024/025/026 remain explicit follow-ups |

No planned Phase 109 work was dropped, deferred, or replaced with structural
proof. The phase delivered duplicate rejection before indexing, honest
exact/variant/functional/non-runtime/store dispositions, correct target and
ammunition semantics, one typed runtime-owned builder, all 22 phase-start
mapping repairs, both no-sensor classifications, atomic reinforcement and
restore behavior, deterministic topology validation, and a green
repository-wide Ruff result.

Necessary unplanned expansion stayed adjacent to the contract: historical,
campaign, and tool YAML ingestion became strict; typed ammunition attachment
data was repaired at the API boundary; live weapon multiplicity, shipboard SAM
routing, cooldown accounting, and composite cadence were corrected where the
honest mappings exposed defects; the production LOD grouping path was
simplified for performance; two pre-existing no-placeholder f-string lint
failures were cleared; and public schema/provider documentation was corrected.
The accepted non-goals remain physical performance tuning, historical
calibration, new EW/mine/breaching/navigation/carrier/UAV mechanics,
aggregation reconstruction, and live Class III/V authority.

### Completion evidence matrix

`Enabled` is not applicable because loadout integrity is a mandatory runtime
boundary rather than an optional feature gate.

| Capability | Declared | Loaded | Wired | Enabled | Exercised | Outcome | Persisted/exposed |
|---|---|---|---|---|---|---|---|
| Strict registry, duplicate rejection, and complete catalog semantics | Yes | Yes | Yes | N/A | Yes | Yes | Yes |
| One runtime builder for initial, reinforcement, and restore paths | Yes | Yes | Yes | N/A | Yes | Yes | Yes |
| Corrected live weapon/sensor/store behavior and explicit unsupported controls | Yes | Yes | Yes | N/A | Yes | Yes | Yes |
| Exact topology, mutable attachment state, and deterministic continuation | Yes | Yes | Yes | N/A | Yes | Yes | Yes |

Each repaired defect has a regression that fails against the phase-start or
pre-fix behavior. The behavioral tests exercise real loader, battle,
detection, ammunition, reinforcement, checkpoint, recorder, and API state
transitions rather than relying on imports, mocks, constructor calls, logs, or
no-crash runs. Same-seed scenario pairs, two hash seeds, a no-RNG-construction
control, and fresh-restore continuation cover ordering and stochastic
discipline.

The fresh postmortem selection reran the highest-risk fixes:

```text
UV_CACHE_DIR=/tmp/phase109-uv uv run pytest -q --tb=short -o addopts= tests/unit/test_phase_109_equipment_mapping.py::test_registry_rejects_nonadjacent_exact_target_role_conflicts tests/unit/test_phase_109_equipment_mapping.py::test_tool_scenario_ingestion_rejects_duplicate_weapon_assignment_keys tests/integration/test_phase_109_equipment_mapping.py::test_sa6_mapped_radar_changes_production_detection_outcome tests/integration/test_phase_109_equipment_mapping.py::test_removed_ea18g_jammer_proxy_cannot_emit_weapon_engagements tests/integration/test_phase_109_equipment_mapping.py::test_reinforcements_use_the_retained_production_builder tests/integration/test_phase_109_equipment_mapping.py::test_fresh_restore_preserves_typed_loadout_and_exact_continuation tests/integration/test_phase_109_battle_sensor_domains.py::test_ship_sam_uses_air_defense_route_against_aircraft tests/integration/test_phase_109_battle_sensor_domains.py::test_cooldown_blocked_sam_does_not_consume_engager_limit tests/integration/test_phase_109_weapon_multiplicity.py::test_flower_depth_charge_count_preserves_live_multitick_cadence tests/integration/test_phase_109_weapon_multiplicity.py::test_harpoon_battery_rate_is_cadence_not_salvo_quantity tests/integration/test_phase_109_weapon_multiplicity.py::test_jutland_fallback_gunnery_preserves_ten_gun_cadence tests/integration/test_phase_109_weapon_multiplicity.py::test_iowa_shore_bombardment_preserves_nine_gun_cadence tests/api/test_frame_enrichment.py::test_capture_frame_exposes_scenario_loader_ammunition_consumption
# 14 passed in 5.22s
```

The independent final adversarial review inspected all 434 non-deleted
changed/untracked files, including 73 Python files (52 test modules) and 349
YAML files. The primary postmortem separately reviewed the two staged YAML
deletions: the mislabeled duplicate 81 mm `m720_mortar_he` was replaced by the
correctly identified M821 definition, and the duplicate Mk 20 Rockeye record
was consolidated into the retained complete definition. The complete staged
set is therefore 436 files. No review found a stub, swallowed mapping error,
permissive production fallback, duplicate constructor path, or unrelated user
change. Fresh adversarial checks reproduced 322 passing Phase 109 tests, zero
validator errors and warnings, green Ruff, and a clean `git diff --check`.
The separate cross-document re-audit passed all ten surfaces and independently
reproduced the registry census, schema examples, checkpoint contract, ten
scenario comparisons, strict documentation build, and diff check.
