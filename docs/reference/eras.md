# Eras

Stochastic Warfare supports 5 historical eras, each with different available technologies, unit types, and combat mechanics. The era framework gates module availability and loads era-specific data.

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

- **Enabled modules** -- which subsystems are available (e.g., no radar before WW2)
- **Available sensor types** -- what sensor modalities exist (e.g., visual only in Ancient)
- **C2 delay multiplier** -- how slow command propagation is (courier >> radio)
- **Era-specific engine extensions** -- custom combat models for the period

Setting `era` in a scenario YAML automatically applies these constraints.

---

## Modern Era (Cold War -- Present)

The default era with full access to all subsystems.

### Enabled Modules

All modules enabled: EW, Space, CBRN, directed energy, full sensor suite, digital C2.

### Available Sensor Types

Visual, thermal/IR, radar, acoustic, sonar, UV MAWS, laser warning, SIGINT.

### C2 Delay

Baseline (1.0x multiplier). Digital communications, Link 16, SATCOM.

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

27+ modern scenarios including 73 Easting, Falklands Naval, Golan Heights, Taiwan Strait, Korean Peninsula, Suwalki Gap, and more.

---

## WW2 Era (1939--1945)

### Enabled Modules

Most modules enabled. No EW (electronic warfare), no space, no directed energy. CBRN limited (no nuclear in most scenarios). Radar available but primitive.

### Available Sensor Types

Visual, radar, passive sonar, active sonar (no thermal/IR targeting, no GPS).

### C2 Delay

Baseline (1.0x multiplier). Radio communications available but less reliable. No digital data links.

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

Stalingrad 1942 (urban combat), Midway 1942 (carrier battle), plus additional WW2 engagements.

---

## WW1 Era (1914--1918)

### Enabled Modules

Limited modules. No EW, no space, no CBRN (except gas warfare via adapter), no directed energy. Basic visual detection only. Very slow C2.

### Available Sensor Types

Visual only. No radar, no thermal, no acoustic sensors.

### C2 Delay

5.0x multiplier. Telephone/telegraph to HQ, runners and couriers forward. Significant communication friction.

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

Jutland 1916 (dreadnought fleet action), Somme 1916, Cambrai 1917.

---

## Napoleonic Era (1792--1815)

### Enabled Modules

Minimal modules. No electronic anything. Visual detection only. Courier-based C2 with extreme delays. Foraging-based logistics.

### Available Sensor Types

Visual only. Detection range limited by terrain and weather.

### C2 Delay

8.0x multiplier. Courier on horseback. Orders take hours to propagate. Fog of war is extreme.

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

Orders delivered by mounted courier:

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

Trafalgar 1805 (naval), Austerlitz 1805, Waterloo 1815.

---

## Ancient & Medieval Era (3000 BC -- 1500 AD)

### Enabled Modules

Minimal modules. Visual detection only. Visual signals C2 (flags, trumpets). No logistics automation.

### Available Sensor Types

Visual only. Very short detection ranges.

### C2 Delay

12.0x multiplier. Visual signals (flags, horns, drums) for nearby units. Messengers on foot for distant commands. Extremely limited command span.

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

Command and control via visual/audible signals:

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

Salamis 480 BC (naval), Cannae 216 BC, Hastings 1066, Agincourt 1415.

---

## Creating Era-Specific Scenarios

To create a scenario for a specific era, set the `era` field in the scenario YAML:

```yaml
name: "Battle of Austerlitz"
era: napoleonic
duration_s: 28800  # 8 hours
terrain:
  width: 8000
  height: 6000
  cell_size: 100
  terrain_type: rolling_hills
sides:
  - name: french
    units:
      - unit_type: french_ligne
        count: 12
        # ...
```

The `ScenarioLoader` will:

1. Apply the era's `EraConfig` (disable unavailable modules, set C2 delays)
2. Load unit definitions from `data/eras/napoleonic/units/` instead of `data/units/`
3. Wire era-specific engines (volley fire, melee, cavalry, formations, courier, foraging)
