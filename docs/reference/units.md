# Units & Equipment

This page documents the unit data model, weapon and ammunition schemas, and catalogs of available equipment across all eras.

---

## Unit Data Model

Units are defined in YAML files and validated by pydantic. The engine defines behaviors; YAML parameterizes instances.

### Unit YAML Schema

```yaml
unit_type: "m1a2_abrams"           # unique identifier
display_name: "M1A2 Abrams"        # human-readable name
domain: ground                      # ground | air | naval_surface | naval_subsurface | ...
category: armor                     # armor | infantry | artillery | air_defense | ...
crew: 4
speed_m_s: 18.0                     # maximum speed in m/s
armor_mm: 600                       # effective armor thickness (mm RHA equivalent)
armor_type: composite               # rha | composite | reactive | spaced | none
health: 100.0
signature_profile: m1a2_sig         # reference to signature YAML
equipment:
  weapons:
    - weapon_type: m256_120mm       # reference to weapon YAML
      mount: turret
  sensors:
    - sensor_type: commanders_sight
      mount: turret
  comms:
    - comms_type: sincgars
```

### Key Fields

| Field | Type | Description |
|-------|------|-------------|
| `unit_type` | `str` | Unique identifier used in scenario references |
| `display_name` | `str` | Human-readable name |
| `domain` | `str` | Operational domain |
| `category` | `str` | Unit category within domain |
| `crew` | `int` | Number of crew members |
| `speed_m_s` | `float` | Maximum speed (meters/second) |
| `armor_mm` | `float` | Effective armor thickness |
| `armor_type` | `str` | Armor material type |
| `health` | `float` | Hit points |
| `signature_profile` | `str` | Reference to signature definition |
| `equipment` | `dict` | Weapons, sensors, comms references |

---

## Modern Units

### Ground Domain

| Unit Type | Display Name | Category | Speed (m/s) | Key Weapon |
|-----------|-------------|----------|-------------|------------|
| `m1a2_abrams` | M1A2 Abrams | armor | 18.0 | M256 120mm |
| `t72b3` | T-72B3 | armor | 16.7 | 2A46M 125mm |
| `t90a` | T-90A | armor | 16.7 | 2A46M-5 125mm |
| `leopard_2a6` | Leopard 2A6 | armor | 19.4 | Rh-120 L/55 |
| `challenger_2` | Challenger 2 | armor | 16.5 | L30A1 120mm |
| `m2a3_bradley` | M2A3 Bradley | infantry | 18.3 | M242 25mm + TOW |
| `bmp2` | BMP-2 | infantry | 18.0 | 2A42 30mm |
| `btr80` | BTR-80 | infantry | 22.2 | KPVT 14.5mm |
| `rifle_squad` | Rifle Squad | infantry | 1.5 | Small arms |
| `insurgent_squad` | Insurgent Squad | infantry | 1.1 | AK-47 + RPG-7 |
| `javelin_team` | Javelin ATGM Team | infantry | 1.5 | FGM-148 Javelin |
| `kornet_team` | Kornet ATGM Team | infantry | 1.5 | 9M133 Kornet |
| `civilian_noncombatant` | Civilian Noncombatant | civilian | 1.4 | None |
| `engineer_squad` | Engineer Squad | support | 1.4 | Small arms |
| `m109_paladin` | M109A6 Paladin | artillery | 16.0 | M284 155mm |
| `mlrs` | M270 MLRS | artillery | 17.9 | M26 rockets |
| `mortar_team` | 81mm Mortar Team | artillery | 1.4 | M252 81mm |

### Air Domain

| Unit Type | Display Name | Category | Speed (m/s) | Key Weapon |
|-----------|-------------|----------|-------------|------------|
| `f16c` | F-16C Fighting Falcon | fixed_wing | 590 | AIM-120 AMRAAM |
| `a10c` | A-10C Thunderbolt II | fixed_wing | 210 | GAU-8 30mm |
| `su27s` | Su-27S Flanker | fixed_wing | 680 | R-27/R-73 |
| `mig29a` | MiG-29A Fulcrum | fixed_wing | 650 | R-73/R-77 |
| `j10a` | J-10A | fixed_wing | 620 | PL-12 |
| `b52h` | B-52H Stratofortress | fixed_wing | 260 | AGM-86 ALCM |
| `a4_skyhawk` | A-4 Skyhawk | fixed_wing | 300 | Mk 12 20mm |
| `ea18g` | EA-18G Growler | fixed_wing | 530 | AGM-88 HARM |
| `ah64d` | AH-64D Apache | rotary_wing | 80 | AGM-114 Hellfire |
| `uh60` | UH-60 Black Hawk | rotary_wing | 76 | Door guns |
| `mi24v` | Mi-24V Hind | rotary_wing | 83 | AT-6 Spiral |
| `c17` | C-17 Globemaster III | transport | 260 | None |

### Air Defense

| Unit Type | Display Name | Category | Key Weapon |
|-----------|-------------|----------|------------|
| `patriot` | MIM-104 Patriot | air_defense | PAC-3 missile |
| `s300pmu` | S-300PMU | air_defense | 48N6 missile |
| `sa6_gainful` | SA-6 Gainful (2K12 Kub) | air_defense | 3M9 missile |
| `sa11_buk` | SA-11 Buk | air_defense | 9M38 missile |
| `manpads` | MANPADS Team | air_defense | Stinger/Igla |

### Naval Domain

| Unit Type | Display Name | Category | Key Weapon |
|-----------|-------------|----------|------------|
| `arleigh_burke` | Arleigh Burke DDG | surface | SM-2/Harpoon/Mk 45 |
| `sovremenny` | Sovremenny DDG | surface | SS-N-22 Sunburn |
| `ticonderoga` | Ticonderoga CG | surface | SM-2/Tomahawk |
| `los_angeles` | Los Angeles SSN | subsurface | Mk 48 torpedo |
| `kilo_636` | Kilo-636 SSK | subsurface | 53-65 torpedo |

---

## Historical Units by Era

### WW2

| Domain | Units |
|--------|-------|
| Armor | Tiger I, Panther, Sherman M4A3, Panzer IV, T-34/85 |
| Infantry | US rifle squad, Soviet rifle squad, Wehrmacht rifle squad |
| Air | P-51D Mustang, Bf 109G, B-17G Flying Fortress, A6M Zero, Spitfire Mk IX |
| Naval | Essex CV, Bismarck BB, Fletcher DD, Type VII U-boat, Shokaku CV |
| Artillery | 105mm howitzer, Katyusha BM-13, Nebelwerfer 41 |

### WW1

| Domain | Units |
|--------|-------|
| Infantry | British rifle section, German Stosstruppen, French poilu squad |
| Artillery | QF 18-pounder, 15cm sFH 13 |
| Air | SPAD XIII, Fokker Dr.I, SE.5a |
| Naval | HMS Dreadnought, SMS Konig, HMS Iron Duke |

### Napoleonic

| Domain | Units |
|--------|-------|
| Infantry | French ligne, British line infantry, Austrian grenadier, Prussian musketeer, Russian jager |
| Cavalry | French cuirassier, British light dragoon, Cossack irregular, Polish lancer |
| Artillery | French 6-pounder, British 9-pounder, Austrian 12-pounder |
| Naval | 1st rate ship of the line, 3rd rate ship of the line, frigate |

### Ancient & Medieval

| Domain | Units |
|--------|-------|
| Infantry | Greek hoplite, Roman legionary, Carthaginian infantry, Viking huscarl, English longbowman |
| Cavalry | Companion cavalry, cataphract, Numidian cavalry, medieval knight, Mongol horse archer |
| Siege | Trebuchet, battering ram, siege tower |
| Naval | Greek trireme, Roman quinquereme, Viking longship, medieval cog |

---

## Weapon Data Model

### Weapon YAML Schema

```yaml
weapon_type: "m256_120mm"
display_name: "M256 120mm Smoothbore"
caliber_mm: 120
range_m: 4000
rate_of_fire_rpm: 6.0
guidance: none                      # none | command | semi_active | active | ir | gps
domain: ground
ammunition_types:
  - m829a3_apfsds
  - m830a1_heat
  - m1028_canister
```

### Key Fields

| Field | Type | Description |
|-------|------|-------------|
| `weapon_type` | `str` | Unique identifier |
| `caliber_mm` | `float` | Bore diameter |
| `range_m` | `float` | Maximum effective range |
| `rate_of_fire_rpm` | `float` | Rounds per minute |
| `guidance` | `str` | Guidance type |
| `ammunition_types` | `list[str]` | Compatible ammo types |

---

## Ammunition Data Model

### Ammo YAML Schema

```yaml
ammo_type: "m829a3_apfsds"
display_name: "M829A3 APFSDS-T"
category: ap                        # ap | heat | he | smoke | illum | guided | ...
caliber_mm: 120
muzzle_velocity_m_s: 1555
penetration_mm: 750                 # at reference range
blast_radius_m: 0
pk_direct: 0.85                     # Pk given hit (direct fire)
```

### Key Fields

| Field | Type | Description |
|-------|------|-------------|
| `ammo_type` | `str` | Unique identifier |
| `category` | `str` | Ammunition category |
| `muzzle_velocity_m_s` | `float` | Launch velocity |
| `penetration_mm` | `float` | Armor penetration capability |
| `blast_radius_m` | `float` | Area effect radius (HE/frag) |
| `pk_direct` | `float` | Kill probability given hit |

---

## Doctrine Templates

Doctrine templates define AI behavior patterns and are assigned per-side in scenario YAML.

| Doctrine | Faction | Category | Key Traits |
|----------|---------|----------|------------|
| US Attack Deliberate | US | Offensive | Mission command, combined arms |
| US Defend Area | US | Defensive | Area defense, counterattack |
| US Movement to Contact | US | Offensive | Advance to find, fix, finish |
| Russian Deep Ops | Russia | Offensive | Massed fires, correlation of forces |
| Russian Defense in Depth | Russia | Defensive | Layered defense, counterattack |
| NATO Collective Defense | NATO | Defensive | Standardized, multinational |
| PLA Active Defense | China | Defensive | Asymmetric, A2/AD focus |
| IDF Preemptive | Israel | Offensive | Speed, surprise, initiative |
| Airborne Vertical Envelopment | Generic | Offensive | Rapid deployment, hold at all costs |
| Amphibious Ship to Shore | Generic | Offensive | Phased approach, naval fire support |
| Naval Sea Control | Generic | Naval | Sea denial, force projection |
| Combined Arms Attack | Generic | Offensive | Multi-arm coordination |
| Combined Arms Defense | Generic | Defensive | Integrated defensive fires |
| Delay | Generic | Defensive | Trading space for time |
| Retrograde | Generic | Defensive | Organized withdrawal |
| Guerrilla Hit and Run | Unconventional | Insurgent | Ambush, disengage, disperse |
| Insurgency Campaign | Unconventional | Insurgent | Population-centric subversion |
| COIN Kinetic | Unconventional | COIN | Direct action, enemy-focused |
| COIN Population-Centric | Unconventional | COIN | Hearts and minds, security |
| PMC Security | Unconventional | PMC | Contractual ROE, asset protection |
| Scorched Earth Denial | Unconventional | Denial | Destroy infrastructure, deny resources |

---

## Commander Profiles

Commander personalities affect OODA cycle speed, decision quality, and risk assessment.

| Profile | Risk Tolerance | Aggression | Adaptability | Style |
|---------|---------------|------------|--------------|-------|
| Cautious Infantry | Low | Low | Medium | Deliberate planning, minimal risk |
| Aggressive Armor | High | High | High | Rapid action, accepts casualties |
| Balanced Default | Medium | Medium | High | Flexible response to situation |
| Joint Campaign | Medium | Medium | Medium | Multi-domain coordination focus |
| Naval Surface | Medium | Medium-High | High | Sea-based power projection |
| Naval Aviation | Medium-High | High | High | Carrier strike group operations |
| Air Superiority | High | High | Medium | Air dominance, DCA/OCA focus |
| SOF Operator | High | Medium | Very High | Special operations, unconventional |
| Logistics Sustainment | Low | Low | Medium | Sustainment priority, methodical advance |
| Ruthless Authoritarian | High | Very High | Low | Scorched earth, no restraint |
| Desperate Defender | Medium | Medium | High | Last stand, extreme sacrifice |
| Insurgent Leader | Medium | Medium | High | Asymmetric, population-centric |
| PMC Operator | Medium | Medium | Medium | Contractual ROE, profit-driven |

Commander personality traits modulate:

- OODA phase durations (aggressive commanders decide faster)
- Risk tolerance in COA selection
- Willingness to accept casualties
- Adaptation speed to changing situations
- Doctrinal school influence weights
