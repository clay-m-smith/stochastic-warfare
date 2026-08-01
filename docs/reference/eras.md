# Eras

Stochastic Warfare supports one modern era package and four historical-era
packages, each with different available technologies, unit types, and combat
mechanics. The era framework gates module availability and loads era-specific
data.

## Era Framework

### Era Enum

| Value | Period | Data Directory |
|-------|--------|---------------|
| `MODERN` | Cold War -- present | `data/` (base) |
| `WW2` | 1939 -- 1945 | `data/eras/ww2/` |
| `WW1` | 1914 -- 1918 | `data/eras/ww1/` |
| `NAPOLEONIC` | 1792 -- 1815 | `data/eras/napoleonic/` |
| `ANCIENT_MEDIEVAL` | 3000 BC -- 1500 AD | `data/eras/ancient_medieval/` |

### EraConfig

Each era defines an `EraConfig` that specifies:

- **Disabled capabilities** -- exactly `ew`, `space`, `cbrn`, `gps`,
  `thermal_sights`, `data_links`, and `pgm`
- **Available sensor types** -- an enforced allowlist of sensor modalities
- **Physics and tick overrides** -- strict sparse declarations consumed by one
  effective production runtime contract
- **Era-specific engine extensions** -- custom combat models for the period

Setting `era` in a scenario YAML selects a registered configuration. Unknown
eras are rejected. The production loader enforces suite gates and rejects
unit loadouts that require forbidden sensors, guidance, or data links.

No built-in or custom `EraConfig` supports a C2 delay multiplier. The former
`c2_delay_multiplier` field rejects explicitly: communications catalogs and
standalone courier/signaling components do not establish a production-loaded,
unit/HQ-bound communications topology. That capability remains
[REM-036](../remediation-backlog.md#rem-036-production-c2-lacks-a-loaded-communications-topology).

The component descriptions below identify available models and data; they are
not blanket claims that every component has a complete production lifecycle.
Construction, importability, or isolated tests alone do not prove production
wiring or outcome effects.

!!! warning "Historical-validation status"

    A historical name, source citation, `documented_outcomes` field, successful
    load, or current-engine regression result does not by itself validate a
    scenario against history. Earlier blanket Phase 47 claims are superseded
    by [REM-030](../remediation-backlog.md#rem-030-catalog-wide-historical-outcome-claims-lack-production-validation).
    Each scenario must have a provenance-bearing, held-out production
    outcome-envelope verdict before it is described as historically validated;
    otherwise its historical-validation status is unsupported.

---

## Modern Era (Cold War -- Present)

The default era with full access to all subsystems.

### Enabled Modules

The built-in config has no disabled era capabilities. EW, Space, CBRN, GPS,
thermal sights, data links, and PGM are permitted when the scenario and live
equipment satisfy their own configuration and topology requirements.

### Available Sensor Types

The allowlist is empty, which means every catalog sensor type is permitted.

### Communications Status

Modern communications data and components exist, but automatic production
assignment and link topology remain REM-036. No era multiplier is applied.

### Key Unit Categories

| Domain | Examples | Count |
|--------|----------|-------|
| Armor | M1A2 Abrams, T-72B3, T-90A, Leopard 2A6, Challenger 2 | 5+ |
| Infantry | Rifle squad, mechanized, Javelin team, Kornet team | 4+ |
| Artillery | M109 Paladin, MLRS/HIMARS, mortar team | 3+ |
| Fixed-Wing Air | F-16C, A-10C, Su-27S, MiG-29A, J-10A, B-52H, EA-18G | 7+ |
| Rotary-Wing | AH-64D Apache, UH-60 Black Hawk, Mi-24V | 3+ |
| Air Defense | Patriot, S-300PMU, SA-11 Buk, MANPADS | 4+ |
| Naval Surface | Arleigh Burke DDG, Sovremenny DDG, Ticonderoga CG | 3+ |
| Naval Subsurface | Los Angeles SSN, Kilo-636 SSK | 2+ |
| Support | Engineers, logistics, HQ, medical, C-17 | 5+ |

### Available Doctrines

US FM 3-0, Russian Deep Operations, NATO Procedures, PLA Active Defense, IDF Preemptive Strike, Airborne, Amphibious, Naval Sea Control.

### Available Scenarios

The modern catalog includes 73 Easting, Falklands Naval, Golan Heights,
Taiwan Strait, Korean Peninsula, Suwalki Gap, and three calibration exercise
scenarios (arctic, urban CBRN, and air-ground). It mixes historical,
hypothetical, calibration, benchmark, and validation scenarios; availability
is not a historical-validation claim.

---

## WW2 Era (1939--1945)

### Enabled Modules

The built-in config disables exactly EW, Space, CBRN, GPS, thermal sights,
data links, and PGM. Other behavior still requires explicit scenario and
equipment support; the era gate does not itself enable a subsystem.

### Available Sensor Types

Exactly `VISUAL`, `RADAR`, `PASSIVE_SONAR`, and `ACTIVE_SONAR`.

### Communications Status

WW2 communications data or isolated components are not an automatically
loaded production network. No era multiplier is applied; REM-036 owns that
topology.

### Era-Specific Mechanics

**Naval Gunnery Bracket Firing**

WW2 naval guns use bracket firing -- observing fall of shot and adjusting. The engine models:

- Initial salvo spread based on fire control quality
- Bracket adjustment (long/short alternation to find range)
- Convergence to target over successive salvos
- Fire control radar bonus for equipped ships

**Convoy / Wolf Pack**

Submarine warfare modeled as:

- Convoy formations with escort positions
- Wolf pack tactics (multiple submarines coordinating attacks)
- Escort effectiveness based on numbers and sonar quality
- Night surface attacks vs submerged daylight attacks

**Strategic Bombing CEP**

High-altitude bombing with circular error probable (CEP):

- Unguided bombs with large CEP (hundreds of meters)
- Target area coverage using Gaussian scatter
- Fighter escort modifying bomber attrition
- Target regeneration over time (industrial recovery)

### Key Units

| Domain | Examples |
|--------|----------|
| Armor | Tiger I, Panther, Sherman M4A3, Panzer IV, T-34/85 |
| Infantry | US/Soviet/Wehrmacht rifle squads |
| Air | P-51D Mustang, Bf 109G, B-17G, A6M Zero, Spitfire |
| Naval | Essex CV, Bismarck BB, Fletcher DD, Type VII U-boat, Shokaku CV |
| Artillery | 105mm howitzer, Katyusha, Nebelwerfer |

### Available Scenarios

Kursk 1943 (largest tank battle), Normandy Bocage 1944 (hedgerow fighting),
Stalingrad 1942 (urban combat), and Midway 1942 (carrier battle). Their
availability and current-engine regression coverage are not historical
outcome-envelope verdicts.

---

## WW1 Era (1914--1918)

### Enabled Modules

The built-in config disables exactly EW, Space, GPS, thermal sights, data
links, and PGM, leaving CBRN enabled at the era gate for WW1
chemical-warfare scenarios. Runtime use still requires an explicitly enabled,
schema-valid CBRN suite.

### Available Sensor Types

Exactly `VISUAL` and `PASSIVE_SONAR`.

### Communications Status

WW1 telephone, messenger, and signaling data do not establish a live
production communications network. No era multiplier is applied; REM-036
owns unit/HQ assignment, propagation, and failure behavior.

### Era-Specific Mechanics

**Trench System Overlay**

Trenches modeled as spatial overlays using Shapely LineString geometries:

- STRtree for fast spatial queries
- Trench segments provide cover and concealment bonuses
- Wire obstacles slow movement
- Communication trenches enable covered movement between positions
- No-man's-land exposure zones

**Creeping Barrage**

Aggregate fire model for massed artillery:

- Fire density measured in rounds per hectare
- Barrage line advances at configurable rate
- Random walk drift with observer correction
- Casualties proportional to troop density in beaten zone

**Volley Fire & Melee**

WW1 bolt-action rifles route to the volley fire aggregate model (coordinated fire), while close-quarters combat uses the melee engine for bayonet charges and trench raids. Machine guns use the standard direct-fire model for sustained suppressive fire.

**Gas Warfare**

Chemical weapons via CBRN adapter:

- Wind direction/speed gating (gas blows back in wrong wind)
- Pasquill-Gifford dispersal model (shared with modern CBRN)
- Gas mask don time enforcement (delay before protection)
- Persistent vs non-persistent agents

### Key Units

| Domain | Examples |
|--------|----------|
| Infantry | British/German/French rifle squads |
| Artillery | 18-pounder, 15cm howitzer |
| Air | SPAD XIII, Fokker Dr.I, SE.5a |
| Naval | HMS Dreadnought, SMS Konig, HMS Iron Duke |

### Available Scenarios

Somme July 1 1916 (first day of the Somme), Cambrai 1917 (first mass tank
assault), and Jutland 1916 (dreadnought fleet action). Their availability and
current-engine regression coverage are not historical outcome-envelope
verdicts.

---

## Napoleonic Era (1792--1815)

### Enabled Modules

The built-in config disables exactly EW, Space, CBRN, GPS, thermal sights,
data links, and PGM. Period-specific combat and logistics components remain
subject to their own production wiring and scenario configuration.

### Available Sensor Types

Exactly `VISUAL`; actual detection is additionally constrained by loaded
sensor data, terrain, and weather.

### Communications Status

The standalone courier model does not establish a loaded production
communications topology. No era multiplier is applied; REM-036 owns its
future unit/HQ integration.

### Era-Specific Mechanics

**Volley Fire**

Aggregate model using binomial trials:

- Musket accuracy varies by range (effective only within ~100m)
- Formation affects volley effectiveness (line > column for firepower)
- Rate of fire: ~3 rounds per minute for trained troops
- Smoke accumulation degrades accuracy over sustained fire

**Melee Combat**

Close-quarters combat model:

- Bayonet charges, saber engagements
- Morale is the primary determinant (most melee resolved by one side breaking)
- Formation effects (square is devastating to cavalry)
- Reach advantage for longer weapons

**Cavalry Charge State Machine**

Multi-phase cavalry engagement:

1. **Approach** -- accelerating toward enemy, taking fire
2. **Contact** -- melee if defenders hold, rout if they break
3. **Pursuit** -- chasing broken enemy (most casualties here)
4. **Rally** -- reforming after charge (vulnerable period)

Pre-contact morale is the key mechanic -- most charges decided before physical contact.

**Napoleonic Formations**

Rock-paper-scissors formation system:

| Formation | Strong Against | Weak Against | Best For |
|-----------|---------------|--------------|----------|
| LINE | Column (firepower) | Cavalry (flanks exposed) | Defensive fire |
| COLUMN | Rapid movement | Line (narrow frontage) | Assault |
| SQUARE | Cavalry (all-round defense) | Artillery (dense target) | Anti-cavalry |
| SKIRMISH | All (hard to hit) | Cavalry (no mass) | Screening |

Transitioning between formations takes time and creates vulnerability.

**Courier C2**

The standalone `CourierEngine` component models orders delivered by mounted
courier:

- Travel time proportional to distance
- Risk of interception or courier loss
- Message delay = distance / courier_speed + lognormal noise
- Initiative doctrine: commanders act on last received orders

**Foraging Logistics**

Supply through local foraging:

- Daily foraging radius around unit position
- Region exhaustion over time (devastated areas produce nothing)
- Ambush risk during foraging operations
- Strategic implications of supply lines vs living off the land

### Key Units

| Domain | Examples |
|--------|----------|
| Infantry | French ligne, British line, Austrian grenadier, Prussian musketeer |
| Cavalry | French cuirassier, British light dragoon, Cossack, lancer |
| Artillery | 6-pounder, 12-pounder, howitzer |
| Naval | Ship of the line (1st/3rd rate), frigate |

### Available Scenarios

Austerlitz 1805, Waterloo 1815, and Trafalgar 1805. Their availability and
current-engine regression coverage are not historical outcome-envelope
verdicts.

---

## Ancient & Medieval Era (3000 BC -- 1500 AD)

### Enabled Modules

The built-in config disables exactly EW, Space, CBRN, GPS, thermal sights,
data links, and PGM. Period-specific combat and signaling components remain
subject to their own production wiring.

### Available Sensor Types

Exactly `VISUAL`; range comes from the loaded sensor definition and live
environment rather than the era label.

### Communications Status

The standalone visual-signaling model does not establish loaded unit/HQ link
topology. No era multiplier is applied; REM-036 owns its future production
integration.

### Era-Specific Mechanics

**Massed Archery**

Aggregate volley model for massed bowmen:

- Arrows per volley tracked per archer (typically 24 arrows total)
- Effective range varies by bow type (longbow > short bow)
- Formation density affects casualties
- Shield wall and armor reduce effectiveness
- Arrow supply exhaustion is a key constraint

**Ancient Formations**

7 formation types with distinct mechanics:

| Formation | Type | Effect |
|-----------|------|--------|
| PHALANX | Dense spear wall | Devastating frontal defense, vulnerable to flanks |
| SHIELD_WALL | Overlapping shields | Strong defense, slow movement |
| WEDGE | Triangular assault | Penetration bonus on charge |
| TESTUDO | Roman turtle | Near-immune to missiles, very slow |
| SKIRMISH_LINE | Dispersed | Hard to hit, weak in melee |
| SQUARE | All-round defense | Anti-cavalry, slow |
| OPEN_ORDER | Flexible spacing | Balanced, standard |

**Siege State Machine**

Campaign-scale daily resolution for sieges lasting weeks to months:

1. **Approach** -- moving siege equipment into position
2. **Investment** -- surrounding the fortification
3. **Bombardment** -- siege engines degrading walls
4. **Assault** -- storming breaches (high casualties)
5. **Resolution** -- surrender, relief, or starvation

### Melee Extensions

- **Reach advantage** -- longer weapons (pikes, spears) get first strike
- **Flanking bonus** -- attacks from side or rear multiply damage
- **Charge momentum** -- cavalry and wedge formations gain impact bonus

**Oar-Powered Naval**

Ancient/medieval naval combat:

- Ram attacks (primary weapon for triremes)
- Boarding actions (melee combat on deck)
- Oar speed vs sail speed tradeoffs
- Ram damage proportional to relative velocity

**Visual Signals C2**

The standalone `VisualSignalEngine` component models command and control via
visual/audible signals:

- Flags, standards, horns, drums
- Signal range limited by terrain and weather
- Misinterpretation probability increases with distance
- Commander must be visible to troops for morale effects

### Key Units

| Domain | Examples |
|--------|----------|
| Infantry | Hoplite, Roman legionary, Viking huscarl, English longbowman |
| Cavalry | Companion cavalry, cataphract, knight, horse archer |
| Siege | Trebuchet, battering ram, siege tower |
| Naval | Trireme, quinquereme, longship, cog |

### Available Scenarios

Cannae 216 BC, Salamis 480 BC, Hastings 1066, and Agincourt 1415. Their
availability and current-engine regression coverage are not historical
outcome-envelope verdicts.

---

## Creating Era-Specific Scenarios

To create a scenario for a specific era, set the `era` field in the scenario YAML:

```yaml
name: "Custom Napoleonic Engagement"
date: "1805-12-02T06:00:00Z"
duration_hours: 8.0
era: napoleonic
tick_resolution:
  strategic_s: 3600
  operational_s: 300
  tactical_s: 5
terrain:
  width_m: 8000
  height_m: 6000
  cell_size_m: 100
  base_elevation_m: 0
  terrain_type: hilly_defense
sides:
  - side: french
    units:
      - unit_type: french_line_infantry
        count: 12
  - side: coalition
    units:
      - unit_type: british_line_infantry
        count: 12
objectives:
  - objective_id: pratzen_heights
    position: [4000, 3000]
    radius_m: 500
    type: key_terrain
victory_conditions:
  - type: force_destroyed
    side: ""
    params:
      threshold: 0.7
```

In the authoritative production flow, `SimulationRuntimeFactory` resolves and
captures the named era before `PreparedScenario.build()` supplies the paired
`EraConfig` and effective contract to `ScenarioLoader`; the loader verifies
that pair without consulting the live registry. An explicit direct
`ScenarioLoader.load()` instead omits both captured objects and resolves the
registry at that lower boundary. In either flow, the loader will:

1. Enforce the selected era's capability and sensor gates.
2. Load definitions from the base catalogs and overlay definitions from
   `data/eras/napoleonic/`.
3. Construct the selected period engine set (volley fire, melee, cavalry,
   formations, courier, and foraging). Construction alone does not establish
   each component's complete production lifecycle; communications topology
   remains REM-036.

The selected registered era also participates in one effective runtime
contract resolved before RNG, clock, terrain, or engine construction.
`tick_resolution_overrides` may sparsely override `strategic_s`,
`operational_s`, and `tactical_s`. `physics_overrides` supports only
`treatment_hours_minor`, `treatment_hours_serious`,
`treatment_hours_critical`, and maintenance-owned `repair_time_hours`. Every
declared value is a strict finite positive float; cadence values must be exact
at microsecond precision and executable through the scenario's calendar
horizon. Unknown fields, numeric strings, booleans, nulls, non-finite values,
and the former unsupported C2/nuclear keys fail validation.

Sparse omission preserves the scenario cadence and medical/maintenance owner
defaults. The uniform `tick_duration_seconds` shorthand cannot be combined
with an era tick override. Built-in era presets currently declare no physics
or cadence numbers because their earlier values lacked traceable sources; the
typed contract is exercised by explicit custom-era controls, not presented as
historical calibration.

The effective values construct `SimulationClock`, `SimulationEngine`,
`MedicalEngine`, and `MaintenanceEngine`, contribute to runtime/API config
fingerprints, and persist in checkpoint format 114. Automatic casualty
admission, medical-facility topology, equipment registration and repair-spares
initiation, communications topology, and scheduled nuclear employment remain
separate remediations. See the
[Era Override Execution contract](../specs/era-override-execution.md).
