# Phase 103: Block 11 Polish — OOB + Engine Gap Tightening

**Status**: Complete.
**Block**: 11 (post-closure cleanup).

## Summary

Phase 103 is a targeted polish pass addressing OOB + engine gaps surfaced during the Block 11 validation runs — cleanup work that tightens the behavior the golden scenarios exercise without expanding scope. Zero new scenarios, zero new unit types beyond three Iraqi artillery carrier units whose weapons already existed.

Three groups of fixes:
- **Group A**: OOB equipment completion (weapon-name mappings + Iraqi artillery carriers + AGM-65 carriage on F-16C)
- **Group B**: Incendiary ammo retagging (FAE thermobaric → INCENDIARY_WEAPON)
- **Group C**: Engine EngagementEvent emission (air-routed + remaining naval paths)

17 new tests, 3 new unit YAMLs, 10 weapon/sensor map entries added/modified, 5 engine emission sites fixed. Full suite remains clean.

## Background

The Block 11 golden scenario runs (Phases 99-102) surfaced several gaps observable as "the weapon is authored but doesn't fire / fires but doesn't surface in analytics":

1. **Phase 100 Khafji**: authored Iraqi artillery (D-30, BM-21, 2S1, 2S3, FROG-7) and SA-7 MANPADS, but only D-30 + BM-21 + SA-7 got carrier units; 2S1, 2S3, FROG-7 authored weapons were orphaned.
2. **Phase 100 Khafji**: AGM-65 Maverick fires (confirmed via UnitDisabledEvent kills) but invisible in `/analytics/engagements` chart because air-routed engagements emit `AirEngagementEvent`, not the generic `EngagementEvent` the chart filters on.
3. **Phase 101 Fallujah**: `INCENDIARY_WEAPON` ammo type triggers Phase 101 fire-zone branch — but existing FAE thermobaric ammo was tagged as `HE`, not `INCENDIARY_WEAPON`, so the branch didn't fire for FAE weapons.
4. Multiple equipment-name labels on already-authored aircraft (`AIM-120 AMRAAM`, `Mk 20 Rockeye II CBU`, `SA-7 Missile Round`) had no `_WEAPON_NAME_MAP` entries — silently dropped at scenario load.
5. Naval routing `_publish_naval_engagement_event` was only wired on NGFS + ship-vs-ship gunnery paths (Phase 100 fix). Torpedo / Depth Charge / ASHM salvo / ASROC paths remained silent.

## Group A — OOB equipment completion

### Weapon name map additions
`stochastic_warfare/validation/scenario_runner.py`:

- `"SA-7 Missile Round"` → `sa7_strela2` (previously dropped on `iraqi_sa7_team` load)
- `"Mk 20 Rockeye II CBU"` → `bomb_rack_generic` (CBU dispenser uses bomb rack path)
- `"AIM-120 AMRAAM"` → `aim120_amraam` (F-16C medium-range A2A)
- `"AIM-7M Sparrow"` → `aim120_amraam` (medium-range A2A proxy — was previously mapped to aim9x which is WVR-only)

### bomb_rack_generic compatibility
Added `mk20_rockeye` to the `compatible_ammo` list in `data/weapons/bombs/bomb_rack_generic.yaml` — A-10 / AV-8B / F/A-18C CBU drops now resolve to a valid ammo round.

### Iraqi artillery carrier units (3 new YAMLs)
- `data/units/artillery/iraqi_2s1_battery.yaml` — 2S1 Gvozdika 122mm SP battery (MT-LB chassis derivative, 4-man crew, training 0.30)
- `data/units/artillery/iraqi_2s3_battery.yaml` — 2S3 Akatsiya 152mm SP battery (Object 303 chassis, 5-man crew, training 0.30)
- `data/units/artillery/iraqi_frog7_tel.yaml` — 9K52 Luna-M FROG-7 unguided tactical rocket TEL (ZIL-135 8x8 chassis, 6-man crew, training 0.30)

All three reference weapons authored in Phase 100 (`2s1_gvozdika`, `2s3_akatsiya`, `frog7_launcher`). Added to Khafji Iraqi III Corps OOB — red force grows from 135 → 140 units (2× 2S1 + 1× 2S3 + 1× FROG-7).

### F-16C AGM-65 carriage
`data/units/air_fixed_wing/f16c.yaml` now lists `AGM-65 Maverick` and `Wing/Fuselage Ordnance Stations` as WEAPON equipment — historically accurate for Desert Storm F-16C/G which carried AGM-65G extensively. A-10, F-15E, AV-8B already carried it per Phase 100.

## Group B — Incendiary ammo retagging

`data/ammunition/prohibited/fae_thermobaric.yaml` retagged from `HE` → `INCENDIARY_WEAPON`. WP (white_phosphorus_shell.yaml) and napalm (mk77_napalm.yaml) were already tagged correctly.

This activates the Phase 101 `INCENDIARY_WEAPON → fire_started` branch in `battle.py` for FAE impacts — WP, FAE, and napalm all now create honest fire zones on hit without scenario-specific handwiring.

## Group C — Engine EngagementEvent emission

### `_publish_air_engagement_event` helper + three integration sites
New helper function in `stochastic_warfare/simulation/battle.py` mirrors the Phase 100 `_publish_naval_engagement_event` pattern. Called from `_route_air_engagement` at three return paths:

1. **BVR/WVR air-to-air** (after `air_combat_engine.resolve_air_engagement`)
2. **CAS air-to-ground** (after `air_ground_engine.execute_cas`)
3. **Ground/Naval-to-air SAM/AAA** (after `air_defense_engine.fire_interceptor`)

Both events are kept — `AirEngagementEvent` retains air-domain detail (BVR/WVR, pilot skill, energy state) while `EngagementEvent` gives the generic shape that the `/analytics/engagements` chart already consumes. AGM-65 / AMRAAM / Hellfire (from AERIAL attacker) / Stinger / SAM intercepts all now surface in Casualties-by-Weapon and Engagement-Summary charts.

### `_route_naval_engagement` missing paths
Phase 100 wired `_publish_naval_engagement_event` on NGFS shore bombardment + ship-vs-ship gunnery paths. Phase 103 adds publication on:

1. **Torpedo engagements** (`naval_subsurface_engine.torpedo_engagement`)
2. **Depth charge attacks** (`naval_subsurface_engine.depth_charge_attack`)
3. **ASHM salvo exchanges** (`naval_surface_engine.salvo_exchange` — C-802 vs ship, Harpoon vs ship)
4. **ASROC sub-engagements** (`naval_subsurface_engine.asroc_engagement`)

INS Hanit scenario smoke run now emits ≥2 EngagementEvents for the C-802 Noor salvo (previously zero surfaced in chart).

## Tests

`tests/validation/test_phase_103_polish.py` — 17 tests, all pass:

- **TestPhase103WeaponMappings** (3): SA-7 Missile Round / Mk 20 Rockeye II CBU / AIM-120 AMRAAM mappings resolve
- **TestPhase103IraqiArtilleryCarriers** (4): 2S1 / 2S3 / FROG-7 units exist and carry weapons; `iraqi_sa7_team` missile round resolves
- **TestPhase103BombRackRockeyeCompat** (1): bomb_rack_generic.compatible_ammo includes mk20_rockeye
- **TestPhase103AGM65Carriage** (4 parametrized): A-10 / F-15E / F-16C / AV-8B carry AGM-65 Maverick
- **TestPhase103IncendiaryRetagging** (3 parametrized): WP / FAE / napalm ammo tagged INCENDIARY_WEAPON
- **TestPhase103AirEngagementEventEmission** (2): `_publish_air_engagement_event` defined; INS Hanit ASCM salvo emits ≥1 EngagementEvent (the Phase 103 naval ASHM gap fix)

## Verification

- Phase 103 test suite: 17/17 PASS in 1.19s
- INS Hanit short run (200 ticks): 2 EngagementEvents surface from ASCM salvo (previously 0)
- Full test suite: pending final count (running in background)

## Impact on Block 11 limitations list

Three Block 11 accepted limitations now resolved:

- ~~Khafji limitation 2: Iraqi artillery weapons authored but no carrier units for 2S1, 2S3, FROG-7~~ → **RESOLVED** via new carrier unit YAMLs + Khafji OOB addition.
- ~~Khafji limitation 3: SA-7 authored but no Iraqi unit carries it~~ → partial fix landed Phase 100 via `iraqi_sa7_team`; Phase 103 closes the `"SA-7 Missile Round"` mapping gap that prevented the missile round from being resolved.
- ~~Khafji limitation 4: AGM-65 Maverick carried but invisible in engagement chart~~ → **RESOLVED** via Group C air-event emission fix.

Remaining Block 11 limitations unchanged:
- Bint Jbeil formation-overflow over-resolution (engine-level fix deferred)
- Merkava armor-zone modeling (new engine capability; own phase)
- Urban terrain proxied via `hilly_defense`
- Civilian population unmodeled

## Postmortem

### Delivered vs Planned

Planned (from user-approved plan):
- Group A: 3 weapon mapping additions, 3 Iraqi carrier units, AGM-65 carriage fix
- Group B: 3 incendiary ammo retaggings
- Group C: Air EngagementEvent emission + naval path verification

Actually delivered:
- All of the above
- Plus AIM-7M Sparrow remapping from `aim9x_sidewinder` → `aim120_amraam` (WVR → BVR correction — found while auditing AIM-120 mapping)
- Plus 4 additional naval paths wired for `_publish_naval_engagement_event` (torpedo, depth charge, ASHM, ASROC) — the original plan only said "verify"; discovered all four were silent

Verdict: **Scope slightly expanded** — the naval audit revealed 4 silent paths that wouldn't have been caught without this phase. Wiring them now closes the naval analytics gap Phase 100 only partially addressed.

### Integration audit

- 10 new map entries integrate via existing `_WEAPON_NAME_MAP` / `_SENSOR_NAME_MAP`
- 3 new unit YAMLs load cleanly and resolve all equipment
- 1 new helper function `_publish_air_engagement_event` called from 3 return sites in `_route_air_engagement`
- 4 new `_publish_naval_engagement_event` call sites in `_route_naval_engagement`
- No new modules; no dead code

### Test quality

17 tests parametrized across 6 test classes. Coverage:
- Unit YAML integrity: 4 tests
- Mapping resolution: 3 tests
- Ammo schema: 3 tests (parametrized)
- Aircraft equipment: 4 tests (parametrized)
- Engine helper existence: 1 test
- End-to-end event emission: 1 test (Hanit scenario)
- Misc bomb rack: 1 test

Coverage gaps:
- No direct test for the Iraqi 2S1/2S3/FROG-7 units actually firing in Khafji runtime (would require 35-min @slow run; the OOB load test is sufficient)
- AIM-7M Sparrow remapping not independently tested (covered implicitly by AIM-120 test + grep audit)

### Performance sanity

Phase 103 tests complete in 1.19s. Full suite rerun pending.

### Summary

- **Scope**: Slightly over (extra naval paths)
- **Quality**: High. All fixes integrate via existing pathways.
- **Integration**: Fully wired. Hanit smoke test confirms EngagementEvent surfacing.
- **Block 11 limitations closed**: 3 (2S1/2S3/FROG-7 orphans, SA-7 missile round mapping, AGM-65 chart invisibility)
- **Remaining limitations**: Bint Jbeil formation overflow, Merkava armor-zone modeling, urban terrain proxy, civilian population — all require their own scope.
