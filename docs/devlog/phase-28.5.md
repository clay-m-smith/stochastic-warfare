# Phase 28.5: Directed Energy Weapons

**Status**: Complete
**Tests**: 112 new (6,947 cumulative)
**Date**: 2026-03-05

## Summary

Mini-phase adding directed energy weapons (DEW) — high-energy lasers (HEL) and high-power microwave (HPM) — to the modern era simulator. DEW fills a critical gap in counter-UAS/RAM and counter-swarm modeling.

## Deliverables

### 28.5a: Core DEW Engine + Enum Extensions (57 tests)

**New file**: `stochastic_warfare/combat/directed_energy.py`
- `DEWType` enum (LASER, HPM)
- `DEWConfig` pydantic model (atmospheric extinction, thermal damage, HPM, engagement params)
- `DEWEngagementResult` dataclass
- `DEWEngine` class with:
  - `compute_atmospheric_transmittance()` — Beer-Lambert atmospheric transmission
  - `compute_laser_pk()` — dwell-time + transmittance-based exponential damage model
  - `compute_hpm_pk()` — inverse-square power density model
  - `execute_laser_engagement()` — full kill chain (range, transmittance abort, Pk, roll, event)
  - `execute_hpm_engagement()` — area-effect multi-target engagement
  - `get_state()`/`set_state()` for checkpointing

**Modified files**:
- `combat/ammunition.py` — `WeaponCategory.DIRECTED_ENERGY = 12`, `AmmoType.DIRECTED_ENERGY = 14`, 4 new WeaponDefinition fields (`beam_power_kw`, `beam_wavelength_nm`, `dwell_time_s`, `beam_divergence_mrad`)
- `combat/damage.py` — `DamageType.THERMAL_ENERGY = 5`, `DamageType.ELECTRONIC = 6`
- `combat/events.py` — `DEWEngagementEvent` frozen dataclass

### 28.5b: Engagement Routing & Scenario Wiring (20 tests)

**Modified files**:
- `combat/engagement.py` — `EngagementType.DEW_LASER = 12`, `EngagementType.DEW_HPM = 13`, `dew_engine` kwarg on `route_engagement()`, routing cases for both types
- `entities/unit_classes/air_defense.py` — `ADUnitType.DEW = 8`
- `simulation/scenario.py` — `dew_engine` field on `SimulationContext`, `dew_config` field on `CampaignScenarioConfig`, `_create_dew_engine()` factory method, state persistence wiring

**Backward-compat fix**: `test_air_defense_unit.py` — `len(ADUnitType) == 8` -> `>= 8`

### 28.5c: YAML Data Files + Data Loading Tests (38 tests)

**New YAML files** (20 total):

| Category | Count | Key Items |
|----------|-------|-----------|
| Weapons (`data/weapons/dew/`) | 5 | DE-SHORAD 50kW, HELIOS 60kW, Iron Beam 100kW, GLWS Dazzler, PHASER HPM |
| Ammunition (`data/ammunition/dew/`) | 5 | 50/60/100kW charges, dazzler charge, HPM pulse |
| Units | 3 | DE-SHORAD (Stryker), Iron Beam, DDG with HELIOS |
| Signatures | 5 | All DEW units + PHASER HPM + GLWS dazzler |
| Sensors | 2 | Laser Warning Receiver, Beam Riding Tracker |

## Design Decisions

1. **Energy as pseudo-ammunition**: DEW reuses existing ammo pipeline. `magazine_capacity` = total engagements before cooldown/recharge.
2. **Single source file**: All DEW physics in `combat/directed_energy.py` — no separate beam_propagation.py.
3. **HPM in combat, not EW**: HPM destroys electronics permanently (combat function). Jamming degrades temporarily (EW function).
4. **Weather as parameters**: DEW functions accept humidity/visibility/precipitation as floats, not engine references. Callers extract weather.
5. **Single `WeaponCategory.DIRECTED_ENERGY`**: `beam_wavelength_nm > 0` distinguishes laser vs HPM.

## Known Limitations

1. **No thermal blooming**: Laser beam self-heating of atmosphere not modeled (significant only for MW-class weapons)
2. **No adaptive optics**: Abstracted into `beam_divergence_mrad` parameter
3. **No power system modeling**: Electrical generation/storage abstracted as `magazine_capacity`
4. **GLWS dazzler uses same Pk framework**: Personnel dazzle modeled as low-power thermal effect
5. **HPM damage is binary**: Real HPM causes spectrum of effects (upset -> degradation -> burnout) — modeled as single Pk
6. **No beam jitter/tracking**: Pointing accuracy abstracted into `beam_divergence_mrad`

## Lessons Learned

- **Pseudo-ammo pattern works well**: Treating energy charges as zero-mass ammunition avoids any special-casing in the existing consumption pipeline. `magazine_capacity` naturally maps to engagement count.
- **Beer-Lambert is clean and testable**: Single formula with additive extinction terms. Each weather factor independently verifiable.
- **Existing test patterns are stable**: Phase 28 data loading test pattern reuses cleanly. `WeaponLoader`/`AmmoLoader`/`UnitLoader`/`SignatureLoader`/`SensorLoader` all handle new data categories without modification.
- **Enum count tests remain fragile**: One more `== N` -> `>= N` fix needed (ADUnitType). Pattern continues from Phase 24.

## File Count Summary

| Category | Count |
|----------|-------|
| New source (`combat/directed_energy.py`) | 1 |
| Modified source | 6 |
| Modified test (backward compat) | 1 |
| New YAML | 20 |
| New test files | 3 |
| **Total** | 31 |

## Postmortem

### Scope
**On target.** Plan estimated ~90 tests; delivered 115. Extra tests came from more thorough data-loading coverage (38 vs planned 20) and additional enum/field validation. No planned items dropped.

### Code Quality: A-
Two issues found and fixed during postmortem:
1. **HPM `base_pk = 0.9` hardcoded** — moved to `DEWConfig.hpm_base_pk` field (configurable, matches project convention)
2. **Aperture factor duplicated** — extracted to `DEWEngine._compute_aperture_factor()` static helper, used in both `compute_laser_pk()` and `execute_laser_engagement()`

### Test Quality
- **Duplication found**: `TestEnumExtensionsIntegration` in 28.5b duplicated 3 tests already in 28.5a `TestEnumExtensions`. Removed from 28.5b.
- Coverage is thorough for unit-level behavior. Edge cases (zero range, extreme weather, no ammo) well covered.
- Uses local helpers (`_rng()`, `_bus()`) instead of conftest fixtures — minor convention deviation, consistent with other Phase 28+ test files.

### Integration: Gaps Found (5 new deficits)
DEW is fully wired for scenario creation and engagement routing, but NOT yet integrated into the simulation tick loop:

1. **DEWEngagementEvent has zero subscribers** — events are published but nothing consumes them (no damage application, no logging subscriber)
2. **dew_engine not used in tick loops** — `simulation/engine.py` and `simulation/battle.py` don't reference `ctx.dew_engine`
3. **No scenario YAML references dew_config** — engine can be created but no scenarios exercise it end-to-end
4. **ADUnitType.DEW not handled in AD logic** — enum exists but air defense engagement code doesn't route DEW-type units to DEW engagements
5. **route_engagement() not called from battle.py** — battle manager uses `execute_engagement()` directly; DEW routing in `route_engagement()` is untested in the loop

These are the same pattern as Phases 16–23 (standalone engines, wired into scenario but not into tick loop). Resolution expected in a future integration phase.

### Action Items Completed
- [x] Extract `_compute_aperture_factor()` helper (dedup)
- [x] Move HPM base_pk to DEWConfig
- [x] Remove enum test duplication from 28.5b
- [x] Log 5 integration deficits to `docs/devlog/index.md`
