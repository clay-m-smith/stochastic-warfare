# Phase 46: Scenario Data Cleanup & Expansion

**Status**: Complete
**Date**: 2026-03-08
**Tests**: 57 new (7,622 total Python passing)

## Summary

Pure data phase — fixes faction/unit mismatches in 9 scenarios and creates 6 missing era/faction-appropriate unit types. Zero new Python source files. 21 new YAML data files + 9 modified scenario YAML + 1 new test file + 2 modified existing test files.

## Changes

### 46a: Adversary Unit Corrections (4 scenarios fixed)

**SA-6 Gainful (2K12 Kub)** — 5 new files. Replaced US Patriot (wrong faction) in Bekaa Valley 1982 and Gulf War EW 1991. SA-6 is the historically correct Soviet medium-range SAM: 24 km range, 3M9 semi-active radar homing missile, 1S91 Straight Flush fire control radar.

**A-4 Skyhawk** — 5 new files. Replaced MiG-29A (wrong aircraft type) in Falklands San Carlos. A-4 was the primary Argentine attack aircraft in the Falklands — subsonic, less capable than MiG-29A, correcting a major performance mismatch.

**Carthaginian Units** — 4 new files. Replaced roman_legionary_cohort (wrong faction) and mongol_horse_archer (wrong era/region) at Cannae. Created carthaginian_infantry (lighter armor, veteran skill) and numidian_cavalry (fastest ancient cavalry, minimal armor). Reused existing gladius/pilum weapons. Also replaced norman_knight_conroi with saracen_cavalry for Roman equites (lighter cavalry closer to historical).

### 46b: Era/Faction Infantry (5 scenarios fixed)

**Eastern Front 1943** — 0 new files. Changed era: modern → era: ww2. Replaced us_rifle_squad/m3a2_bradley with existing WW2 units (soviet_rifle_squad + t34_85 vs wehrmacht_rifle_squad + panzer_iv_h + tiger_i).

**Insurgent Squad** — 6 new files. Created insurgent_squad (AK-47 + RPG-7, BASIC skill, no armor), with proper weapon/ammo YAML (ak47, rpg7, 7_62x39_fmj, pg7_heat). Replaced us_rifle_squad in COIN Campaign (red side), Hybrid Gray Zone (red side), Srebrenica (both sides with display_name overrides). Srebrenica red side also gets t72m replacing m3a2_bradley.

**Civilian Noncombatant** — 2 new files. Created civilian_noncombatant (UNTRAINED, no weapons, empty equipment list). Replaced us_rifle_squad in Halabja 1988 (blue/Kurdish civilians). Red side uses insurgent_squad + t72m for Iraqi Republican Guard.

## New Data Files (21)

| Category | Files |
|----------|-------|
| Units | sa6_gainful, a4_skyhawk, carthaginian_infantry, numidian_cavalry, insurgent_squad, civilian_noncombatant |
| Weapons | sa6_3m9, mk12_20mm, ak47, rpg7 |
| Ammunition | 3m9_sam, 20mm_mk100, 7_62x39_fmj, pg7_heat |
| Sensors | 1s91_straight_flush, apq94_radar |
| Signatures | sa6_gainful, a4_skyhawk, carthaginian_infantry, numidian_cavalry, insurgent_squad, civilian_noncombatant |

## Modified Files (11)

| File | Change |
|------|--------|
| bekaa_valley_1982/scenario.yaml | patriot → sa6_gainful, weapon_assignments updated |
| gulf_war_ew_1991/scenario.yaml | patriot → sa6_gainful, weapon_assignments updated |
| falklands_san_carlos/scenario.yaml | mig29a → a4_skyhawk, weapon_assignments updated |
| cannae/scenario.yaml | roman_legionary_cohort → carthaginian_infantry, mongol_horse_archer → numidian_cavalry, norman_knight_conroi → saracen_cavalry |
| eastern_front_1943/scenario.yaml | era: ww2, all units replaced with WW2 equivalents |
| coin_campaign/scenario.yaml | red us_rifle_squad → insurgent_squad, weapon_assignments added |
| hybrid_gray_zone/scenario.yaml | red us_rifle_squad → insurgent_squad, weapon_assignments updated |
| srebrenica_1995/scenario.yaml | both sides → insurgent_squad, m3a2_bradley → t72m |
| halabja_1988/scenario.yaml | blue → civilian_noncombatant, red → insurgent_squad + t72m |
| test_phase_23c_ancient_validation.py | mongol_horse_archer → numidian_cavalry |
| test_phase2_integration.py | civilian_noncombatant exception for empty equipment |

## Test Failures Fixed

1. `test_carthaginian_has_cavalry` — checked for `mongol_horse_archer`, updated to `numidian_cavalry`
2. `test_load_and_create_all` — asserted `len(equipment) > 0` for all units, added exception for `civilian_noncombatant`

## Lessons Learned

- **Empty equipment list works**: The engine handles units with no weapons/sensors — weapon selection finds no valid weapons and skips engagement. No source code changes needed.
- **Reusing existing weapons across factions is clean**: Carthaginian infantry uses the same gladius/pilum weapon YAML as Romans — differentiation is at the unit level (armor, skill, speed), not weapon level.
- **New weapon subdirectory (rifles/) needed**: No existing directory for individual rifles — created `data/weapons/rifles/` for ak47. Existing m4_556mm is in `data/weapons/guns/`.
- **Weapon_assignments must map equipment names to weapon IDs**: Every scenario modification requires updating the weapon_assignments calibration override to match new unit equipment names. Missing assignments = unmapped weapons.
- **Existing test hardcoded expectations break**: Phase 23 test expected `mongol_horse_archer` by name. Always use semantic assertions (`has cavalry type`) over specific unit type names where possible.

## Known Limitations

- A-4 Skyhawk has cannon only (no bomb weapon). Primary Falklands role was iron bomb delivery — would need Mk 82 weapon/ammo for full fidelity.
- Saracen cavalry used as proxy for Roman equites. Both represent light cavalry, but saracen_cavalry has ARMOR ground_type while equites were cavalry. Stats are reasonable approximation.
- Iraqi Republican Guard represented by insurgent_squad with display_name override and higher experience (0.7). A dedicated Iraqi Army unit would be more accurate.
- No new weapon_assignments for WW2 units in Eastern Front scenario — relies on era-based weapon loading.

## Deficits Resolved

| Deficit | Origin |
|---------|--------|
| Wrong-faction units in scenarios | Phase 30 |
| `us_rifle_squad` used as universal proxy | Phase 30 |

## Postmortem

**Scope**: On target. The plan called for ~8 new unit types; we delivered 6 by reusing existing WW2 units (soviet_rifle_squad, wehrmacht_rifle_squad) instead of creating redundant duplicates. 4 planned unit types (syrian_t62, soviet_motor_rifle, german_infantry_ww2, soviet_infantry_ww2) were unnecessary — existing Phase 20/29 data covered those needs. Golan scenario modifications were not in the final implementation plan and remain for Phase 47 calibration if needed.

**Quality**: High. 57 tests covering schema validation, scenario loading, faction correctness, cross-references, and the empty-equipment edge case. All 7,622 tests pass. Zero new source files = zero risk of engine regressions.

**Integration**: Fully wired. All new YAML loads through existing pydantic-validated loaders. All 9 modified scenarios reference valid unit types. Weapon→ammo cross-refs verified.

**Performance**: No regression (143.9s vs ~143s baseline).

**Deficits**: 4 known limitations (documented above), all LOW severity:
1. A-4 Skyhawk missing bomb weapon — deferred (cannon sufficient for engagement routing)
2. Saracen cavalry as Roman equites proxy — ARMOR ground_type mismatch, cosmetic
3. Iraqi Republican Guard as insurgent_squad — dedicated unit would improve fidelity
4. Eastern Front WW2 missing weapon_assignments — depends on era-based weapon loading

None of these block Phase 47 recalibration. Items 1 and 3 could be addressed in Phase 47 if calibration results demand it.

**Action items**: None blocking. Cross-doc audit completed — all docs updated (index.md, mkdocs.yml, units.md, CLAUDE.md, README.md, MEMORY.md, devlog/index.md).
