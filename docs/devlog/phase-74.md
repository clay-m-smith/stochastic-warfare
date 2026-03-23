# Phase 74: Combat Engine Unit Tests

**Status**: Complete
**Date**: 2026-03-23
**Block**: 8 (Consequence Enforcement & Scenario Expansion)

## Summary

Pure test-addition phase — 472 new unit tests across 32 test files covering all 33 combat engine source files. Zero source code changes. Created `tests/unit/combat/` directory with shared `conftest.py` providing combat-specific factory functions.

## Substeps

### 74a: Core Combat Engine Tests (106 tests, 6 files)
- `test_damage.py` — DamageEngine, IncendiaryDamageEngine, UXOEngine (penetration, blast, fire zones, UXO encounter)
- `test_engagement.py` — EngagementEngine (kill chain orchestration, routing, fratricide abort)
- `test_ammunition.py` — WeaponDefinition, AmmoDefinition, WeaponInstance, AmmoState (domain inference, cooldown, barrel wear)
- `test_ballistics.py` — BallisticsEngine (RK4 trajectory, drag, wind deflection, dispersion)
- `test_hit_probability.py` — HitProbabilityEngine (modifier stacking, guided Pk, moderate_condition_floor)
- `test_suppression.py` — SuppressionEngine (fire volume, decay, spreading, pinned effects)

### 74b: Domain Combat Engine Tests (129 tests, 8 files)
- `test_air_combat.py` — AirCombatEngine (BVR/WVR/guns, countermeasures, energy state)
- `test_air_defense.py` — AirDefenseEngine (threat evaluation, engagement envelope, SLS)
- `test_air_ground.py` — AirGroundEngine (CAS danger-close, SEAD, delivery accuracy, JTAC)
- `test_naval_surface.py` — NavalSurfaceEngine (salvo, point defense, ship damage, naval gun, flooding)
- `test_naval_subsurface.py` — NavalSubsurfaceEngine (torpedo, ASROC, depth charges, NIXIE CM)
- `test_missiles.py` — MissileEngine (launch, flight profiles, flight update, active tracking)
- `test_missile_defense.py` — MissileDefenseEngine (BMD layered, cruise, CRAM, discrimination)
- `test_directed_energy.py` — DEWEngine (Beer-Lambert transmittance, laser/HPM Pk)

### 74c: Historical & Unconventional Tests (154 tests, 11 files)
- `test_melee.py` — MeleeEngine (pre-contact morale, reach, cavalry terrain, frontage, flanking)
- `test_archery.py` — ArcheryEngine (volley fire, armor reduction, ammo tracking)
- `test_volley_fire.py` — VolleyFireEngine (range Phit, rifle multiplier, smoke, canister)
- `test_barrage.py` — BarrageEngine (creeping/standing, drift, observer correction, expiry)
- `test_siege.py` — SiegeEngine (phases, wall damage, starvation, assault, sally, relief)
- `test_naval_gunnery.py` — NavalGunneryEngine (bracket, convergence, straddle, hit probability)
- `test_naval_mine.py` — MineWarfareEngine (mine types, encounter, sweeping, persistence)
- `test_unconventional.py` — UnconventionalWarfareEngine (IED, guerrilla, human shields)
- `test_fratricide.py` — FratricideEngine (risk levels, modifiers, deconfliction)
- `test_gas_warfare.py` — GasWarfareEngine (wind check, delivery, MOPP)
- `test_carrier_ops.py` — CarrierOpsEngine (sortie rate, launch, recovery, CAP, recovery window)

### 74d: Additional Engine Tests (83 tests, 7 files)
- `test_naval_gunfire_support.py` — NavalGunfireSupportEngine (CEP scaling, spotter, coordination)
- `test_amphibious_assault.py` — AmphibiousAssaultEngine (approach attrition, beach combat, sea state)
- `test_strategic_bombing.py` — StrategicBombingEngine (CEP, flak, escort, regeneration)
- `test_iads.py` — IadsEngine (sector health, SEAD damage, air track processing)
- `test_strategic_targeting.py` — StrategicTargetingEngine (TPL, strike damage, BDA, regeneration)
- `test_air_campaign.py` — AirCampaignEngine (fleet, pilots, fatigue, weather, attrition)
- `test_indirect_fire.py` — IndirectFireEngine (fire missions, rocket salvo, counterbattery, TOT)

## Files Changed

| Action | Count | Details |
|--------|-------|---------|
| New test files | 32 | `tests/unit/combat/test_*.py` |
| New support files | 2 | `tests/unit/combat/__init__.py`, `tests/unit/combat/conftest.py` |
| Source changes | 0 | Pure test addition |

**34 new files total. Zero source changes.**

## Patterns Used

- **Factory functions in conftest.py**: `_rng()`, `_make_ap()`, `_make_he()`, `_make_heat()`, `_make_gun()`, `_make_weapon_instance()`, `_make_unit()` — avoid YAML loaders and full entity graphs
- **Real lightweight instances**: All sub-engine dependencies (BallisticsEngine, DamageEngine, etc.) are created as real instances, not mocks
- **State roundtrip in every engine**: `get_state() → set_state()` → verify RNG produces identical next draw
- **Seed variation per test class**: Each `_make_engine()` helper accepts `seed` parameter for deterministic but varied tests
- **Statistical assertions for stochastic tests**: Run N trials and assert rate bounds rather than single-trial equality

## Test Inventory

| Substep | Files | Tests |
|---------|-------|-------|
| 74a: Core | 6 | 106 |
| 74b: Domain | 8 | 129 |
| 74c: Historical & Unconventional | 11 | 154 |
| 74d: Additional | 7 | 83 |
| **Total** | **32** | **472** |

## Lessons Learned

- **EquipmentItem field name**: `equipment_id` not `item_id`, `category` is `EquipmentCategory` enum not string
- **Wind direction is meteorological**: Gas warfare wind_dir_deg is FROM direction; gas travels at wind_dir + 180°
- **update_cap_stations returns relief-needed only**: Not all stations — just those past endurance threshold
- **compute_effects key names**: Barrage effects use `suppression_p`/`casualty_p`, not `suppression`/`casualty_rate`
- **CBRN engine required for gas delivery**: Without CBRN engine, cylinder_release/gas_bombardment safely return empty lists
- **Auto mode selection at close range**: AirCombatEngine selects WVR at 600m (within wvr_min/max range), not GUNS_ONLY

## Postmortem

### Scope: Over-delivered
Plan targeted ~243 tests across 32 files. Delivered 472 tests — nearly 2x the target. The linter hooks expanded several test files with additional edge cases and structural tests beyond the initial implementation. All planned files and engines were covered.

**Planned items not delivered**: None. All 33 combat engine files received dedicated tests.

**Unplanned additions**: `test_missile_defense.py` was not in the original 74b plan (which listed 7 files) but was added since MissileDefenseEngine is a distinct engine file. Linter hooks added ~37 extra tests across siege, barrage, naval gunnery, naval mine, unconventional, fratricide, gas warfare, and carrier ops files.

### Quality: High
- All 32 test files have state roundtrip tests
- 27+ files have explicit edge case tests
- Statistical assertions used for stochastic behavior (N-trial bounds)
- No mocking — all real lightweight engine instances
- Factory functions in shared conftest avoid YAML loaders

### Integration: Fully wired
- 1:1 mapping between combat source files and test files
- All 32 test files import from shared `conftest.py`
- Zero source changes — pure test addition

### Deficits: 1 pre-existing
- **Salamis test_narrow_terrain**: Phase 73 recalibrated Salamis terrain from 8000x4000 to 3000x2000 but didn't update the Phase 30 validation test assertion (`cfg.terrain.width_m == 8000`). Pre-existing, not introduced by Phase 74.

### Performance: No impact
- 472 new tests run in 0.85s total
- Full suite: 9,449 passed, 1 failed (pre-existing), 21 skipped in 24:57

### Action items
- [x] Fix stale test counts in devlog (435→472), CLAUDE.md, development-phases-block8.md, README.md, MEMORY.md
- [x] Fix Salamis test_narrow_terrain assertion (8000→3000, 4000→2000 — Phase 73 recalibration)

## Cross-Doc Audit

19-check audit run after postmortem. Results:

| Check | Result | Notes |
|-------|--------|-------|
| 1. Module Coverage | **PASS** | All combat source files covered by tests |
| 2. Phase Content Match | **PASS** | 32 test files match 32 combat source files (events.py excluded — not an engine) |
| 3. Dependency Ordering | **PASS** | N/A — pure test phase, no new source modules |
| 4. Exit Criteria Coverage | **PASS** | Plan said ~243 tests, delivered 472. All 33 engines tested. |
| 5. Contradictions | **PASS** | No contradictions found |
| 6. Brainstorm Traceability | **PASS** | N/A — no new features |
| 7. Devlog Completeness | **PASS** | phase-74.md exists with substep details, lessons, postmortem |
| 8. Memory Freshness | **PASS** | MEMORY.md updated with Phase 74 status and 472 test count |
| 9. README Currency | **PASS** | Badge 9,729 (Python), Phase 74 row with 472 tests, phase-74 badge |
| 10. Deficit Traceability | **PASS** | 169 items dispositioned. Salamis fix applied. |
| 11. Post-MVP Alignment | **PASS** | N/A — no post-MVP scope changes |
| 12. Post-MVP Module Coverage | **PASS** | N/A — no new modules |
| 13. Devlog Completeness (all) | **PASS** | All 75 devlogs present (0-74 + 28.5) |
| 14. User-Facing Status | **PASS** | docs/index.md: 10,023 tests, 41 scenarios, phase-74 badge |
| 15. Architecture Accuracy | **PASS** | 12-module chain, 5 eras, domain tables all present |
| 16. API Accuracy | **PASS** | N/A — no API changes |
| 17. Scenario Catalog | **PASS** | 41 scenarios (27 base + 14 era) matches docs |
| 18. Era & Unit Accuracy | **PASS** | N/A — no data changes |
| 19. MkDocs Nav | **PASS** | phase-74 devlog in nav |

**0 CRITICAL, 0 HIGH, 0 MEDIUM, 0 LOW issues remaining.** All stale counts fixed during audit.
