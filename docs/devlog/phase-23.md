# Phase 23: Ancient & Medieval Era

**Status**: Complete
**Tests**: 321 new (5,980 total)
**Duration**: Single session

## Overview

Pre-gunpowder warfare dominated by melee combat, formations, and morale. Follows the Phase 20-22 era framework pattern: data package + standalone engine modules. Battles decided by morale collapse and rout cascade, not attrition to zero.

## Sub-phases

### 23a: Era Config + Data (~167 tests)

**Source modifications (3 files):**
- `core/era.py` — Added `ANCIENT_MEDIEVAL_ERA_CONFIG` (disabled_modules: ew/space/cbrn/gps/thermal_sights/data_links/pgm, VISUAL-only sensors, c2_delay_multiplier=12.0)
- `simulation/scenario.py` — Added 5 SimulationContext fields (`archery_engine`, `siege_engine`, `formation_ancient_engine`, `naval_oar_engine`, `visual_signals_engine`) + state persistence + `open_field` terrain type
- `validation/historical_data.py` + `scenario_runner.py` — Added `open_field` terrain type

**YAML data (49 files in `data/eras/ancient_medieval/`):**
- 7 units: roman_legionary_cohort, greek_hoplite_phalanx, english_longbowman, norman_knight_conroi, swiss_pike_block, mongol_horse_archer, viking_huscarl
- 13 weapons: gladius, pilum, sarissa, longbow, crossbow, lance_medieval, sword_medieval, mace, pike, catapult, trebuchet, ballista, battering_ram
- 8 ammo: arrow_longbow, bolt_crossbow, pilum_javelin, stone_catapult, stone_trebuchet, bolt_ballista, composite_arrow, sling_stone
- 3 sensors: mounted_scout_ancient (3km/180°), watchtower (10km/360°), ship_lookout (5km/360°)
- 7 signatures: one per unit, zeroed thermal/radar/EM
- 3 doctrines: roman_legion (OFFENSIVE), english_defensive (DEFENSIVE), steppe_nomad (OFFENSIVE)
- 3 commanders: hannibal_barca, henry_v, william_conqueror
- 2 comms: battle_horn (500m, no LOS), banner_signal (1000m, LOS)

### 23b: Engine Extensions (~112 tests)

**5 new source files:**

1. `combat/archery.py` (~300 lines) — Massed archery aggregate model. Binomial casualties from per-missile-type Phit range tables (longbow, crossbow, composite, javelin, sling). Armor reduction (NONE/LIGHT/MAIL/PLATE). Formation vulnerability modifier. Per-unit ammo tracking (24 arrows/archer, depletes per volley).

2. `movement/formation_ancient.py` (~350 lines) — 7 formation types (PHALANX/SHIELD_WALL/PIKE_BLOCK/WEDGE/SKIRMISH/TESTUDO/COLUMN). Melee power, defense, speed, archery/cavalry/flanking vulnerability modifiers. Worst-of-both during transitions. Same pattern as `formation_napoleonic.py`.

3. `combat/siege.py` (~350 lines) — Campaign-scale state machine (ENCIRCLEMENT→BOMBARDMENT→BREACH→ASSAULT→FALLEN/RELIEF/ABANDONED). Daily resolution. Wall HP (trebuchet 50/day, ram 30, catapult 20, mine 40). Breach at 30% remaining. Starvation after food_days depleted. Sally sorties (Bernoulli). Relief force mechanics.

4. `movement/naval_oar.py` (~220 lines) — Fatigue-based rowing (cruise 2.5/battle 4.0/ramming 6.0 m/s). Exhaustion threshold (0.8) halves speed. Recovery at rest. Ram damage = base + speed_factor × approach_speed. Boarding transition to melee.

5. `c2/visual_signals.py` (~290 lines) — Synchronous presence-based C2. Banner (1000m, LOS, instant, fidelity 0.7). Horn (500m, no LOS, instant, fidelity 0.5). Runner (async, 3 m/s, fidelity 1.0). Fire beacon (10km, LOS, binary only). Reliability per type.

**1 extended source file:**

6. `combat/melee.py` — Added 3 MeleeType values (PIKE_PUSH=4, SHIELD_WALL=5, MOUNTED_CHARGE=6). Added reach_advantage_modifier (1.3, round 1 only), flanking_casualty_multiplier (2.5), pike_push_attrition_rate (0.01), shield_wall_defense_bonus (0.5), mounted_charge_casualty_rate (0.04). Backward compatible — existing Napoleonic types unchanged.

### 23c: Validation Scenarios (~42 tests)

3 scenarios in `data/eras/ancient_medieval/scenarios/`:

1. **Cannae** (216 BC) — 4km×3km open_field. Carthaginian (2 infantry, 2 cavalry, Hannibal, steppe_nomad) vs Roman (4 legionary cohorts, 1 cavalry, roman_legion). Historical: 85% Roman / 8% Carthaginian casualties.

2. **Agincourt** (1415) — 2km×1km open_field. English (4 longbowman, 1 men-at-arms, Henry V, english_defensive) vs French (3 knight conrois, 1 crossbow, offensive). Historical: 50% French / 5% English casualties.

3. **Hastings** (1066) — 2km×1km hilly_defense. Saxon (3 huscarl warbands, defensive) vs Norman (2 knight conrois, 1 infantry, 1 archers, William, combined arms). Historical: 50% Saxon / 30% Norman casualties.

## Key Design Decisions

1. **Archery as aggregate model** — Same Binomial pattern as Napoleonic volley fire, without smoke. Phit from per-missile-type range tables. Arrow supply finite and critical.

2. **Melee extension, not replacement** — Existing Napoleonic types (BAYONET_CHARGE, CAVALRY_CHARGE, etc.) unchanged. New types add reach advantage and flanking mechanics specific to ancient warfare.

3. **Separate formation_ancient.py** — 7 formation types are mechanically distinct from Napoleonic formations. Separate module is cleaner than overloading formation_napoleonic.py.

4. **Siege as daily state machine** — Campaign-scale, not tick-level. Appropriate abstraction for weeks-to-months sieges.

5. **Visual signals vs courier delivery** — Ancient C2 is synchronous presence-based (banner/horn = instant if in range) vs Napoleonic asynchronous delivery (courier carries a message over time).

6. **Ammo per-archer tracking** — `_ammo[unit_id]` tracks volleys remaining per archer (starts at 24). Each volley costs 1 arrow per archer regardless of n_archers. All archers fire if ammo remains.

## Lessons Learned

- **Ammo semantics matter**: Initial implementation tracked total arrows (24) not per-archer arrows — resulted in only 24 out of 100 archers firing. Fixed to track volleys remaining per archer.
- **YAML unit count vs entry count**: Scenario YAML has `count: 4` on a single entry, not 4 entries. Tests checking `len(entries) >= 4` fail; must check `sum(count)`.
- **Era engine wiring is by design**: Phase 20-22 Napoleonic engines are also not wired into `_create_engines()`. Era expansion phases deliver standalone modules; full simulation-loop wiring is separate work.

## Postmortem

### Scope: On target
All planned items delivered. 49 YAML files (plan: ~49). 5 new + 4 modified source files. 321 tests (plan: ~245). Exceeded test target by 31%.

### Quality: High
- Zero TODOs/FIXMEs in new code
- All values configurable via pydantic Config classes
- All modules follow DI pattern, get_logger, type hints, state protocol
- PRNG discipline: all randomness via injected `np.random.Generator`

### Integration: Standalone by design
Same pattern as Phases 20-22. Era engines exist as standalone modules with context fields. Not wired into simulation loop `_create_engines()`. This is the established era framework pattern — full loop integration is out of scope for era expansion phases.

### Deficits: 0 new
No new deficits discovered. All known limitations are design choices:
- Siege state machine is campaign-scale (daily), not tick-level
- Ram damage is linear (base + factor × speed), not nonlinear
- Visual signal fidelity is per-type constant, not distance-dependent
- Melee reach advantage applies round 1 only (historical accuracy)

### Test Performance
Phase 23 tests: 321 tests in 4.1s. Full suite: 5,980 tests in 100s. No degradation from Phase 22 baseline.
