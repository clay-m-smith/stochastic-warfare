# Phase 27: Combat System Completeness

## Summary

Phase 27 fills missing cross-domain engagement paths, enhances the engagement engine with burst fire and submunition scatter, completes naval combat mechanics, and resolves 4 named deficits. 139 new tests (6,698 total). 12 source files modified, 4 new test files.

## What Was Built

### 27d: Selective Fidelity Items (30 tests)
- **Observer correction** (`combat/barrage.py`): `has_observer` + `observer_quality` on BarrageZone. Drift reduced by `correction_factor * quality` each update. Without observer, behavior identical to prior random walk.
- **Cavalry terrain effects** (`combat/melee.py`): `compute_cavalry_terrain_modifier()` — slope penalty per degree, soft ground penalty, obstacle abort threshold, uphill casualty bonus. Integrated into `resolve_melee_round()`.
- **Frontage constraint** (`combat/melee.py`): `compute_frontage_constraint()` — limits engaged strengths based on available frontage, reserves contribute at `second_rank_effectiveness`.
- **Gas mask don time** (`combat/gas_warfare.py`): `compute_exposure_during_don()` (linear ramp), `get_effective_mopp_level()` (MOPP level + protection factor with ramp).

### 27a: Cross-Domain Engagement Paths (31 tests)
- **Engagement router** (`combat/engagement.py`): 3 new `EngagementType` values (COASTAL_DEFENSE, AIR_LAUNCHED_ASHM, ATGM_VS_ROTARY). `route_engagement()` dispatcher, `_resolve_atgm_vs_rotary()` with altitude check, range decay, wire-guidance bonus.
- **Air-launched ASHM** (`combat/air_ground.py`): `AirGroundMission.ASHM = 5`, `execute_ashm()` launch-only method, 200km max range.
- **EW air combat integration** (`combat/air_combat.py`): `compute_ew_countermeasure_reduction()`, optional `ew_decoy_engine`/`jamming_engine` params on `resolve_air_engagement()`. Gated by `enable_ew_countermeasures` config.
- **EW air defense integration** (`combat/air_defense.py`): Optional EW engines on `fire_interceptor()`, gated by `enable_ew_countermeasures` config.

### 27b: Engagement Engine Enhancements (47 tests)
- **Burst fire** (`combat/engagement.py`): `execute_burst_engagement()` — N rounds as binomial trial, single cooldown, damage per hit. `BurstEngagementResult`. Gated by `enable_burst_fire` (disabled = single shot).
- **Submunition scatter** (`combat/damage.py`): `resolve_submunition_damage()` — scatter submunitions via rng.normal, check lethal radius per target, accumulate damage, create UXO field for duds.
- **Multi-spectral CM** (`combat/air_combat.py`): `apply_countermeasures_multi()` — multiplicative stacking. Supports chaff, flare, dircm.
- **TOT synchronization** (`combat/indirect_fire.py`): `TOTFirePlan` dataclass, `compute_tot_plan()`, `execute_tot_mission()`. Closer batteries fire later (shorter ToF).
- **CAS designation** (`combat/air_ground.py`): `compute_cas_designation()` — JTAC delay enforcement, laser bonus, talk-on latency ramp, comm quality.

### 27c: Naval Combat Completion (31 tests)
- **Naval gun** (`combat/naval_surface.py`): `naval_gun_engagement()` — radar-directed Pk per round, range/sea state/FC quality factors.
- **ASROC + depth charges** (`combat/naval_subsurface.py`): `asroc_engagement()` (rocket delivery → torpedo), `depth_charge_attack()` (pattern scatter).
- **Torpedo countermeasures** (`combat/naval_subsurface.py`): `resolve_torpedo_countermeasures()` — layered NIXIE → acoustic CM → evasion.
- **CAP management** (`combat/carrier_ops.py`): `create_cap_station()`, `update_cap_stations()`, `schedule_recovery_window()`.

## Design Decisions

1. **Implementation order**: 27d → 27a → 27c → 27b. Smallest/self-contained first, shared-file modifications last.
2. **Backward compatibility**: All new config fields have defaults matching prior behavior. New optional params on existing methods. `enable_*` flags gate new features.
3. **Designation delay gate**: CAS designation returns zero bonus before `jtac_designation_delay_s` — hard gate, not gradual ramp. Talk-on latency is the gradual ramp after the delay.
4. **Burst fire disabled = 1 round**: When `enable_burst_fire=False`, burst_size forced to 1 regardless of weapon definition, ensuring backward-compatible single-shot behavior.
5. **Submunition scatter sigma**: Proportional to `blast_radius_m * sigma_fraction`, not lethal_radius. This gives realistic scatter patterns for artillery-delivered submunitions.

## Deviations from Plan

- Test count: 139 actual vs ~165 estimated. Some planned tests were redundant with implementation (e.g., backward compat tests overlap with config default tests).
- Some 27b features (burst fire, multi-CM, CAS designation) implemented alongside 27a since they share source files (`engagement.py`, `air_combat.py`, `air_ground.py`).

## Issues & Fixes

1. **WeaponInstance import**: Located in `combat/ammunition.py`, not `entities/weapons.py`.
2. **EngagementEngine constructor**: Requires `hit_engine`, `suppression_engine`, `fratricide_engine` (not `hit_probability`/`suppression`).
3. **compatible_ammo required for fire()**: Test weapons need `compatible_ammo=[ammo_id]` for `WeaponInstance.fire()` to succeed.
4. **Naval gun test had `rng=` kwarg**: Method doesn't accept it — moved rng to engine constructor.

## Deficits Resolved

| Deficit | Description | Resolution |
|---------|-------------|------------|
| 2.10 | No frontage/depth in melee | `compute_frontage_constraint()` limits engaged strengths |
| 2.11 | Cavalry charge ignores terrain | `compute_cavalry_terrain_modifier()` with slope/soft ground/obstacles |
| 2.12 | Barrage drift no observer correction | Observer correction reduces drift proportionally |
| 2.13 | Gas mask don time not modeled | `compute_exposure_during_don()` linear ramp |

## Files Modified

| File | Changes |
|------|---------|
| `combat/engagement.py` | 3 enum values, route_engagement(), _resolve_atgm_vs_rotary(), execute_burst_engagement(), BurstEngagementResult, 4 config fields |
| `combat/air_ground.py` | ASHM enum+method+dataclass, CAS designation method+dataclass, 4 config fields |
| `combat/air_combat.py` | EW integration, multi-CM stacking, 2 config fields |
| `combat/air_defense.py` | EW integration, 1 config field |
| `combat/damage.py` | resolve_submunition_damage(), 2 config fields |
| `combat/indirect_fire.py` | TOTFirePlan, compute_tot_plan(), execute_tot_mission(), 2 config fields |
| `combat/naval_surface.py` | naval_gun_engagement(), NavalGunResult, 5 config fields |
| `combat/naval_subsurface.py` | asroc_engagement(), depth_charge_attack(), resolve_torpedo_countermeasures(), 3 dataclasses, 9 config fields |
| `combat/carrier_ops.py` | create_cap_station(), update_cap_stations(), schedule_recovery_window(), 2 dataclasses, 4 config fields |
| `combat/barrage.py` | Observer correction (2 config + 2 zone fields + update logic) |
| `combat/melee.py` | compute_cavalry_terrain_modifier(), compute_frontage_constraint(), 7 config fields |
| `combat/gas_warfare.py` | compute_exposure_during_don(), get_effective_mopp_level() |
