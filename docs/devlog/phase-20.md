# Phase 20: WW2 Era

## Summary

Phase 20 introduces the era framework and the first historical era expansion: World War II. The era framework allows the simulation engine to load era-specific YAML data (units, weapons, ammunition, sensors, signatures, doctrines, commanders) from `data/eras/{era}/` directories, and optionally instantiate era-specific engine extensions. Three new engine modules cover WW2-specific combat domains: naval gunnery (bracket firing and fire control), convoy/anti-submarine warfare (wolf packs and depth charges), and strategic bombing (CEP area damage, flak, fighter escort).

**Key metric**: 137 new tests, 5,244 total (up from 5,107). 4 new source files + 3 modified + ~60 YAML data files. No new dependencies.

## What Was Built

### 20a: Era Framework + WW2 Unit Data (56 tests)
- `core/era.py` — `Era` enum (MODERN, WW2), `EraConfig` pydantic model (pre-defined configs for MODERN/WW2), `get_era_config()` factory, `register_era_config()` for custom eras
- `simulation/scenario.py` (modified) — `era` field on `CampaignScenarioConfig`, `era_config`/`naval_gunnery_engine`/`convoy_engine`/`strategic_bombing_engine` fields on `SimulationContext`, era-aware `_create_loaders()` loading from `data/eras/{era}/`, `era_config` in `get_state()`
- `simulation/engine.py` (no changes needed) — existing None-check pattern handles engine gating for era-specific engines
- **15 WW2 unit YAMLs**: 5 armor (Sherman M4A3, T-34/85, Tiger I, Panther, Panzer IV H), 3 infantry (US/Wehrmacht/Soviet rifle squads), 4 air (Bf 109G, P-51D, Spitfire IX, B-17G), 3 naval (Type VIIC U-boat, Fletcher DD, Iowa BB)
- **8 weapon YAMLs**: 75mm M3, 88mm KwK 36, 85mm ZIS-S-53, M2 .50 cal, MG 42, Mk 14 torpedo, 5"/38 naval, 16"/50 naval
- **13 ammo YAMLs**: AP/HE variants per caliber + torpedo + naval rounds
- **4 sensor YAMLs**: Mk I Eyeball WW2, SCR-584 radar, Type 271 naval radar, WW2 hydrophone
- **15 signature YAMLs**: one per unit, zeroed thermal signatures (no IR detection in WW2)

### 20b: Engine Extensions (53 tests)
- `combat/naval_gunnery.py` — `NavalGunneryConfig` pydantic model, `BracketState` tracker, `NavalGunneryEngine` with bracket firing, fire control quality, 2D Gaussian dispersion, straddle mechanics
- `movement/convoy.py` — `ConvoyConfig` pydantic model, `ConvoyState`, `ConvoyEngine` with convoy formation, speed limiting to slowest ship, straggler probability, wolf pack attack modeling, depth charge patterns
- `combat/strategic_bombing.py` — `StrategicBombingConfig` pydantic model, `BomberStreamState`, `TargetDamageState`, `StrategicBombingEngine` with CEP-based area damage, Norden bombsight altitude scaling, flak Poisson Pk, fighter escort modeling, bomber defensive fire, target regeneration

### 20c: Doctrine & Commanders (YAML only)
- **4 doctrine YAMLs**: blitzkrieg, soviet_deep_ops, british_deliberate, us_combined_arms_ww2
- **3 commander profiles**: aggressive_patton, methodical_montgomery, operational_zhukov

### 20d: Validation Scenarios (28 tests)
- **Kursk/Prokhorovka**: Eastern Front armored engagement using WW2 unit/weapon data
- **Midway**: Naval carrier battle using WW2 naval units and naval gunnery engine
- **Normandy Bocage**: Combined arms infantry/armor scenario in close terrain
- Each scenario uses `era: ww2` field and WW2-specific unit/weapon/ammo references
- Backward compatibility with all existing modern scenarios verified

## Design Decisions

1. **Era framework uses existing None-check pattern**: Disabled modules simply stay `None` on `SimulationContext`. No runtime branching in the hot path. Era-specific engines (naval_gunnery, convoy, strategic_bombing) are instantiated only when `era_config` enables them.

2. **Era-specific YAML loaded from `data/eras/{era}/`**: Distinct IDs prevent conflicts with base `data/` directory. WW2 Sherman is `sherman_m4a3`, not `m1a2`. No name collisions, no fallback resolution complexity.

3. **Engine core is era-agnostic**: The strategy pattern means eras are data packages (YAML) plus targeted engine extensions (Python modules). The simulation loop, detection pipeline, AI decision-making, and logistics all work unchanged across eras.

4. **Zeroed thermal signatures for WW2**: WW2 predates practical IR detection. Setting thermal signatures to zero in YAML effectively disables thermal sensors without code changes.

5. **Naval gunnery bracket firing**: WW2 naval gunnery is fundamentally different from modern guided missile combat (Phase 4 `naval_surface.py`). Bracket firing with straddle mechanics, fire control quality degradation, and 2D Gaussian dispersion captures the statistical nature of WW2 naval combat.

6. **Convoy system as movement extension**: Wolf pack attacks and convoy defense are movement-phase phenomena (formation, speed constraints, straggler detection) with embedded combat resolution (depth charges, torpedo attacks). Placing in `movement/convoy.py` reflects this dual nature.

7. **Strategic bombing CEP model**: Area bombing effectiveness modeled via CEP (circular error probable) with Norden bombsight altitude scaling. This is a different abstraction than the precision strike model used for modern munitions.

## Deviations from Plan

- `simulation/engine.py` required no modifications — the existing None-check pattern for optional engines (established in Phases 16-18) handled era-specific engine gating without changes.
- No new dependencies required — all WW2 physics models (Gaussian dispersion, Poisson flak, bracket firing) use existing numpy/scipy capabilities.

## Issues & Fixes

- **Era-aware loader path resolution**: `_create_loaders()` needed to search `data/eras/{era}/` directories first, then fall back to base `data/` for shared assets (e.g., terrain data). Resolved by having era-specific loaders only load from era directory with distinct IDs.
- **Thermal signature zeroing**: Initial approach of omitting thermal fields caused validation errors in pydantic models. Setting to 0.0 explicitly is cleaner and works with existing detection pipeline (SNR=-inf for zero signature effectively disables detection).

## Known Limitations

- No era-specific detection model changes (WW2 radar performance approximated via sensor YAML parameters, not physics model changes)
- No era-specific C2 model (WW2 communications limitations approximated via comm equipment YAML, not structural changes)
- Convoy engine does not model individual escort positions (abstract effectiveness parameter)
- Strategic bombing target regeneration is linear (no industrial interdependency graph)
- No era-specific morale model (WW2 morale dynamics use same Markov chain as modern)
- Fighter escort in strategic bombing is a probability modifier, not a full air combat sub-simulation
- Only 3 validation scenarios — no Pacific theater island hopping or Eastern Front winter warfare
- No era-specific logistics (WW2 supply constraints approximated via YAML consumption rates)

## Lessons Learned

- **None-check gating pattern pays off across phases**: The pattern established in Phase 16 (EW), refined in Phases 17-18 (Space, CBRN), and continued here means era-specific engines require zero engine.py modifications. New optional subsystems just need a field on SimulationContext.
- **Era-specific data directories avoid naming conflicts**: The `data/eras/{era}/` convention is simpler and more maintainable than prefixing IDs or using namespace resolution. Each era is a self-contained data package.
- **YAML-driven eras scale well**: Adding a new era is primarily a YAML authoring task. Only domains that fundamentally differ (e.g., WW2 naval gunnery vs modern missile combat) need new Python engine modules.
- **Zeroed signatures are effective feature flags**: Setting WW2 thermal signatures to 0.0 disables IR detection without conditional code. The SNR math naturally produces no-detection results.
- **Historical validation scenarios catch data errors quickly**: Kursk scenario immediately revealed a missing ammo YAML reference and an incorrect weapon range value.

## Postmortem

### 1. Delivered vs Planned
- **Scope**: On target. All planned items shipped (4 source files, ~60 YAML, 3 modified files, 3 scenarios).
- **Test count**: 137 tests delivered. Total suite: 5,244 tests.
- **No items dropped or deferred**. No unplanned features added.

### 2. Integration Audit
- **Era framework wiring solid**: `era` field on `CampaignScenarioConfig` flows through to `SimulationContext.era_config`. Era-aware loaders correctly load from `data/eras/ww2/`.
- **Checkpoint/restore**: `era_config` in SimulationContext `get_state()`/`set_state()`.
- **Engine gating works**: `naval_gunnery_engine`, `convoy_engine`, `strategic_bombing_engine` are `None` for modern scenarios. No runtime cost.
- **All 5,107 existing tests pass unchanged**: Full backward compatibility confirmed.
- **No new event types** (era-specific engines use existing event infrastructure).

### 3. Test Quality Review
- **Overall rating**: 7/10
- **Strengths**: Comprehensive YAML loading tests for all ~60 data files, historical plausibility checks in validation scenarios, backward compatibility verification, era framework unit tests cover registration and factory patterns.
- **Gaps**: Convoy wolf pack attack tested at unit level but not through full campaign loop; strategic bombing target regeneration tested in isolation but not multi-tick campaign integration; no cross-era comparison tests (modern vs WW2 same terrain).

### 4. API Surface Check
- **Quality**: Good. All public functions have type hints. `get_logger(__name__)` throughout. DI pattern followed. Pydantic for all config models. Consistent with Phase 16-19 patterns.
- **Era enum is extensible**: `register_era_config()` allows future eras (WW1, Napoleonic, Ancient) without modifying `core/era.py`.

### 5. New Deficits (added to devlog/index.md)
1. Convoy engine does not model individual escort positions (abstract effectiveness parameter)
2. Strategic bombing target regeneration is linear (no industrial interdependency graph)
3. Fighter escort in strategic bombing is probability modifier, not full air combat sub-simulation
4. ScenarioLoader doesn't auto-wire era-specific engines from YAML (extends existing EW/Space/CBRN/Schools gap)

### 6. Documentation Freshness
- **CLAUDE.md**: To be updated with Phase 20 status + completed phase section.
- **development-phases-post-mvp.md**: Phase 20 to be marked COMPLETE with all sub-phases.
- **devlog/index.md**: Phase 20 status updated to Complete with link, new deficits added.
- **project-structure.md**: era.py and era-specific modules to be added to source tree.
- **README.md**: Test count (5,244), phase badge (20), status table to be updated.
- **MEMORY.md**: Current status and lessons learned to be updated.

### 7. Performance
- Full suite: **5,244 passed**. Phase 20 tests alone add minimal overhead (~0.6s). No performance regression from era framework or new engine modules.

### 8. Summary
- **Scope**: On target
- **Quality**: Good (7/10 tests, good API surface)
- **Integration**: Fully wired — era framework, era-aware loaders, and era-specific engines all functional
- **Deficits**: 4 new items (convoy abstraction, linear regeneration, escort simplification, auto-wiring gap)
- **Backward compatibility**: All 5,107 existing tests pass unchanged
