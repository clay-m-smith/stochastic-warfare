# Phase 2: Entities, Organization & Movement

## Summary

Phase 2 defines what simulation entities ARE (personnel, equipment, unit types), how they're organized (military hierarchy, task organization), and how they move across all domains (ground, aerial, naval, submarine, amphibious, airborne). This is the largest phase by module count (28 source modules + 13 YAML data files) and the first to introduce YAML-loaded data definitions.

**Test count**: 424 new tests (74 entity foundation + 81 unit classes + 39 loader/capabilities + 74 organization + 58 core movement + 79 specialized movement + 23 integration) = **791 total** (367 existing + 424 new).

## What Was Built

### Step 1: Entity Foundation (4 files)
- **core/types.py**: Added `Domain` (IntEnum: GROUND/AERIAL/NAVAL/SUBMARINE/AMPHIBIOUS) and `Side` (str Enum: BLUE/RED/NEUTRAL/CIVILIAN)
- **entities/personnel.py**: `CrewMember` dataclass with role, skill, injury, fatigue; `PersonnelManager` static methods for casualties, effectiveness, experience gain
- **entities/equipment.py**: `EquipmentItem` dataclass with condition, reliability, temperature range; `EquipmentManager` for degradation, breakdown, environment stress
- **entities/events.py**: Frozen dataclass events (`UnitCreatedEvent`, `UnitDestroyedEvent`, `PersonnelCasualtyEvent`, `EquipmentBreakdownEvent`)
- **entities/base.py**: Expanded with `UnitStatus` enum and `Unit` class extending `Entity` with personnel, equipment, domain, status

### Step 2: Unit Class Definitions (5 files)
- **ground.py**: `GroundUnit` with `GroundUnitType`, `Posture`, armor values, mounted state
- **aerial.py**: `AerialUnit` with `AerialUnitType`, `FlightState`, fuel, service ceiling, UAV data link
- **air_defense.py**: `AirDefenseUnit` with `ADUnitType`, `RadarState`, engagement envelope, `can_engage()` method
- **naval.py**: `NavalUnit` with `NavalUnitType`, hull integrity, draft, displacement, submarine depth/noise; auto-detects domain from type
- **support.py**: `SupportUnit` with `SupportUnitType`, cargo capacity

### Step 3: YAML Loader & Capabilities (2 modules + 11 YAML files)
- **loader.py**: `UnitDefinition` pydantic model, `UnitLoader` factory class — load YAML definitions, create appropriate Unit subclasses
- **capabilities.py**: `CombatPowerCalculator` — assess unit combat power from personnel strength, equipment readiness, training, fatigue, leadership
- 11 YAML unit definition files covering armor, infantry, artillery, fixed-wing, rotary-wing, UAV, air defense, surface combatant, submarine, amphibious ship, and logistics truck

### Step 4: Organization System (7 files + 2 YAML)
- **echelons.py**: `EchelonLevel` (INDIVIDUAL through THEATER), standard definitions with span of control
- **hierarchy.py**: `HierarchyTree` adjacency-list tree with CRUD, chain of command, recursive subordinates
- **task_org.py**: `TaskOrgManager` — dynamic command relationship overlays (OPCON, TACON, etc.)
- **staff.py**: `StaffCapabilities` — S1–S6 staff section effectiveness modeling
- **orbat.py**: `OrbatLoader` — build hierarchy from YAML TO&E definitions
- **special_org.py**: `SpecialOrgManager` — SOF, irregular, coalition traits
- **events.py**: `OrgAttachEvent`, `OrgDetachEvent`

### Step 5: Core Movement (5 files)
- **engine.py**: `MovementEngine` — terrain-aware speed computation (terrain × slope × road × weather × fatigue × night), stochastic noise, move-toward-target
- **pathfinding.py**: `Pathfinder` — A* with 8-connectivity, terrain cost, threat avoidance
- **fatigue.py**: `FatigueManager` — physical/mental fatigue, sleep debt, altitude penalty, speed/accuracy modifiers
- **formation.py**: `FormationManager` — 10 formation types (COLUMN through FILE), position computation, coherence, frontage
- **events.py**: `UnitMovedEvent`, `FormationChangedEvent`, `FatigueChangedEvent`

### Step 6: Specialized Movement (6 files)
- **obstacles.py**: `ObstacleInteraction` — assess/bypass/breach/clear/cross, minefield transit risk
- **mount_dismount.py**: `MountDismountManager` — state machine for mount/dismount transitions
- **naval_movement.py**: `NavalMovementEngine` — sea state speed reduction, fuel cubic law, draft check
- **submarine_movement.py**: `SubmarineMovementEngine` — speed-noise curve (20log10), depth bands, snorkel exposure
- **amphibious_movement.py**: `AmphibiousMovementEngine` — 6-phase operation (LOADING→INLAND), beach assessment
- **airborne.py**: `AirborneMovementEngine` — Gaussian drop scatter, DZ assessment, helicopter insertion

### Step 7: Integration Tests & Visualization
- 23 integration tests covering full entity stack, organization, movement, pathfinding, naval, submarine, amphibious, airborne, deterministic replay, checkpoint/restore
- Visualization script with unit positions, movement paths, formations, org hierarchy

## Design Decisions

1. **Composition over inheritance**: Entity → Unit → domain-specific (GroundUnit, etc.). Personnel and equipment are composed as lists, not inherited.
2. **Dataclass MRO**: Entity has required fields (entity_id, position); Unit adds fields with defaults — maintains backward compatibility.
3. **Domain auto-detection**: NavalUnit.__post_init__ sets domain based on naval_type (SSN→SUBMARINE, LHD→AMPHIBIOUS, etc.).
4. **YAML unit definitions**: Data-driven design — adding new unit types = adding YAML, no code changes. Pydantic validates at load time.
5. **Task org overlay**: Separate from organic hierarchy — queries check overlay first, fall back to organic tree.
6. **Movement constructor injection**: MovementEngine receives terrain/environment modules as constructor parameters. No tight coupling.
7. **Cubic fuel law**: Naval fuel ∝ v³t — standard naval engineering relationship.
8. **Speed-noise curve**: Submarine noise = base + 20·log₁₀(speed/quiet_speed) — standard acoustic relationship.
9. **A* with heapq**: No new dependencies. Grid-based with configurable resolution and threat avoidance.
10. **Stochastic speed**: Gaussian noise on movement speed, controlled by config.noise_std, deterministic from seed.

## Deviations from Plan

- Test count slightly below plan estimate (~520 planned, ~424 achieved) but all exit criteria met
- Visualization is a standalone script rather than part of the test suite

## Lessons Learned

- **Dataclass inheritance ordering**: Python requires all fields without defaults before fields with defaults across the entire MRO chain. Entity's required fields (entity_id, position) must come first.
- **`__post_init__` for domain forcing**: Domain-specific subclasses use `__post_init__` to override domain regardless of what was passed, ensuring consistency.
- **SimpleNamespace for mock objects**: Test mocks for terrain/environment modules use `types.SimpleNamespace` to avoid importing heavy Phase 1 modules in unit tests.
- **Pydantic validation at YAML load**: Catches errors early — bad unit definitions fail fast with clear messages.

## File Count Summary

| Category | Files |
|----------|-------|
| Source modules (new) | 28 |
| Source modules (expanded) | 2 (core/types.py, entities/base.py) |
| YAML data files | 13 |
| Test files | 14 (new) + 1 (expanded) |
| Visualization | 1 |
| **Total** | **59** |
