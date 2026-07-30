# Units & Equipment

This page documents the unit data model, weapon and ammunition schemas, and catalogs of available equipment across all eras.

---

## Unit Data Model

Units are defined in YAML files and validated by pydantic. The engine defines behaviors; YAML parameterizes instances.

### Unit YAML Schema

```yaml
unit_type: m1a2
domain: ground                      # ground | aerial | naval | submarine | amphibious
display_name: "M1A2 Abrams MBT"
ground_type: ARMOR
max_speed: 18.0                    # meters per second
training_level: 0.9
armor_front: 600.0                 # mm RHA equivalent
armor_side: 200.0
armor_type: COMPOSITE
crew:
  - role: COMMANDER
    count: 1
    skill: TRAINED
  - role: GUNNER
    count: 1
    skill: TRAINED
  - role: LOADER
    count: 1
    skill: BASIC
  - role: DRIVER
    count: 1
    skill: TRAINED
sensor_policy: required
equipment:
  - name: "M256 120mm Smoothbore"
    category: WEAPON
    weight_kg: 1800.0
    reliability: 0.95
  - name: "AN/VVS-2 Commander Viewer"
    category: SENSOR
    weight_kg: 45.0
    reliability: 0.90
```

### Key Fields

| Field | Type | Description |
|-------|------|-------------|
| `unit_type` | `str` | Unique identifier used in scenario references |
| `display_name` | `str` | Human-readable name |
| `domain` | `str` | One of `ground`, `aerial`, `naval`, `submarine`, or `amphibious` |
| `max_speed` | `float` | Maximum speed in meters per second |
| `crew` | `list[object]` | Crew rows with `role`, positive `count`, and `skill` enum name |
| `equipment` | `list[object]` | Named equipment rows with category, mass, reliability, and optional environmental limits |
| `training_level` | `float` | Crew/unit proficiency (0.0–1.0). Scales effective skill via `base_skill * (0.5 + 0.5 * training_level)`. Typical values: Elite 0.9, Veteran 0.8, Regular 0.7, Green 0.6, Conscript 0.5, Poor 0.3–0.4 |
| `ground_type`, `aerial_type`, `naval_type`, `ad_type`, `support_type` | `str \| null` | Domain/subclass discriminator used by the unit factory |
| `armor_front`, `armor_side` | `float` | Ground-unit armor thickness in mm RHA equivalent |
| `armor_type` | `str` | Armor material enum name |
| `sensor_policy` | `str` | Requires authored sensor equipment by default; `intentionally_none` forbids sensors |
| `sensor_policy_reason` | `str` | Required justification when `sensor_policy` is `intentionally_none`; forbidden otherwise |
| Other domain fields | numeric | Aerial ceiling/data-link range; naval draft, displacement, fuel, depth, and noise; air-defense altitude/range/missile/reload values; or support cargo capacity |

### Runtime Equipment Resolution

`WEAPON` and `SENSOR` names are exact, case-sensitive catalog keys. During
scenario loading, one typed runtime registry resolves each row as a live
attachment, carried ammunition store, or explicit non-runtime item. Unknown,
unsupported, duplicate, stale-override, or semantically incompatible entries
fail loading instead of disappearing from a unit. Explicit source-system
counts are retained in the runtime topology and affect live cadence,
ammunition, events, and checkpoint compatibility. See the
[equipment-mapping contract](../specs/equipment-mapping.md) for the complete
rules and accepted non-runtime boundaries.

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
| `peshmerga_irregular` | KDP Peshmerga Irregular | infantry | 1.2 | AKM + PKM + RPG-7 |
| `iraqi_1st_mech_dismount` | Iraqi 1st Mech Inf Dismount (2003) | infantry | 2.2 | AKM + PKM + RPG-7 |
| `iraqi_mtlb` | MT-LB (Iraqi) | infantry | 17.0 | PKT 7.62mm |
| `saudi_sang_squad` | Saudi SANG Infantry Section | infantry | 1.3 | AKMS + PKM + RPG-7 |
| `saudi_v150` | V-150 Commando (TOW) Armored Car | infantry | 25.0 | M901 TOW-2 + M240 coax |
| `qatari_amx30b2` | AMX-30B2 MBT (Qatari) | armor | 18.0 | F1 105mm + 20mm coax |
| `us_lav25` | LAV-25 Light Armored Vehicle | infantry | 27.0 | M242 25mm + M240 coax |
| `us_lav_at` | LAV-AT Anti-Tank Vehicle | armor | 27.0 | BGM-71 TOW-2 |
| `iraqi_brdm2` | BRDM-2 Armored Scout | recon | 25.0 | KPVT 14.5mm + PKT 7.62mm |
| `us_marine_recon_team` | USMC Marine Recon Stay-Behind Team | sof | 1.5 | M16A2 + M249 + M40/M82 snipers |
| `civilian_noncombatant` | Civilian Noncombatant | civilian | 1.4 | None |
| `engineer_squad` | Engineer Squad | support | 1.4 | Small arms |
| `m109_paladin` | M109A6 Paladin | artillery | 16.0 | M284 155mm |
| `mlrs` | M270 MLRS | artillery | 17.9 | M26 rockets |
| `mortar_team` | 81mm Mortar Team | artillery | 1.4 | M252 81mm |
| `iraqi_d30_battery` | Iraqi D-30 122mm Towed Battery | artillery | 8.0 | 6× D-30 122mm howitzer |
| `iraqi_bm21_grad` | Iraqi BM-21 Grad MRL | artillery | 15.0 | 4× BM-21 122mm MRL (40 tubes each) |

### Air Domain

| Unit Type | Display Name | Category | Speed (m/s) | Key Weapon |
|-----------|-------------|----------|-------------|------------|
| `f16c` | F-16C Fighting Falcon | fixed_wing | 590 | AIM-120 AMRAAM |
| `f14b` | F-14B Tomcat (VF-32) | fixed_wing | 680 | AIM-54/LANTIRN + GBU-16 |
| `fa18c` | F/A-18C Hornet | fixed_wing | 585 | AGM-65/LITENING + GBU-31 |
| `a10a` | A-10A Thunderbolt II | fixed_wing | 210 | GAU-8 30mm + AGM-65 + CBU-87 |
| `a10c` | A-10C Thunderbolt II | fixed_wing | 210 | GAU-8 30mm |
| `av8b` | AV-8B Harrier II (VSTOL) | fixed_wing | 290 | GAU-12 25mm + Rockeye + Maverick |
| `ac130h` | AC-130H Spectre gunship | fixed_wing | 130 | 105mm + 40mm Bofors + 20mm Vulcans |
| `f15e` | F-15E Strike Eagle (LANTIRN) | fixed_wing | 735 | GBU-10/12/24/28 + AGM-65 + AIM-9 |
| `ov10a` | OV-10A Bronco (FAC) | fixed_wing | 130 | Zuni + HVAR + M60 MGs |
| `ah1w` | AH-1W SuperCobra (USMC) | rotary_wing | 80 | M197 20mm + TOW-2 + Hellfire |
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
| `zsu_57_2` | ZSU-57-2 SPAAG | air_defense | 2× 57mm S-68 (direct-fire) |
| `iraqi_sa7_team` | Iraqi SA-7 Strela-2 MANPADS Team | air_defense | 9K32 Strela-2 (IR homing) |
| `manpads` | MANPADS Team | air_defense | Stinger/Igla |

### Naval Domain

| Unit Type | Display Name | Category | Key Weapon |
|-----------|-------------|----------|------------|
| `arleigh_burke` | Arleigh Burke DDG | surface | SM-2/Harpoon/Mk 45 |
| `sovremenny` | Sovremenny DDG | surface | SS-N-22 Sunburn |
| `ticonderoga` | Ticonderoga CG | surface | SM-2/Tomahawk |
| `iowa_bb` | Iowa-class Battleship (BB-63/64) | surface | 16"/50 Mk 7 + 5"/38 + Harpoon + Tomahawk |
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
weapon_id: "m256_120mm"
display_name: "M256 120mm Smoothbore"
category: CANNON
caliber_mm: 120.0
muzzle_velocity_mps: 1750.0
max_range_m: 4000.0
rate_of_fire_rpm: 6.0
burst_size: 1
guidance: NONE
magazine_capacity: 42
target_domains:
  - GROUND
compatible_ammo:
  - m829a3_apfsds
  - m830a1_heat_mp
  - m1028_canister
```

### Key Fields

| Field | Type | Description |
|-------|------|-------------|
| `weapon_id` | `str` | Unique identifier |
| `display_name` | `str` | Human-readable weapon name |
| `category` | `str` | `WeaponCategory` enum name |
| `caliber_mm` | `float` | Bore diameter |
| `muzzle_velocity_mps` | `float` | Launch velocity |
| `max_range_m` | `float` | Maximum modeled range |
| `rate_of_fire_rpm` | `float` | Rounds per minute |
| `burst_size` | `int` | Per-system rounds in one synchronized firing action |
| `guidance` | `str` | `GuidanceType` enum name |
| `magazine_capacity` | `int` | Definition-level ammunition capacity |
| `target_domains` | `list[str]` | Domains this weapon may engage |
| `compatible_ammo` | `list[str]` | Compatible ammunition definition IDs |

---

## Ammunition Data Model

### Ammo YAML Schema

```yaml
ammo_id: m829a3_apfsds
display_name: "M829A3 APFSDS-T"
ammo_type: AP
mass_kg: 8.9
diameter_mm: 120.0
drag_coefficient: 0.15
penetration_mm_rha: 750.0
penetration_reference_range_m: 2000.0
blast_radius_m: 0.0
fragmentation_radius_m: 0.0
guidance: NONE
propulsion: none
max_speed_mps: 1750.0
unit_cost_factor: 5.0
```

### Key Fields

| Field | Type | Description |
|-------|------|-------------|
| `ammo_id` | `str` | Unique identifier |
| `display_name` | `str` | Human-readable ammunition name |
| `ammo_type` | `str` | `AmmoType` enum name |
| `mass_kg`, `diameter_mm`, `drag_coefficient` | `float` | Physical projectile properties |
| `penetration_mm_rha` | `float` | Armor penetration in mm RHA equivalent |
| `penetration_reference_range_m` | `float` | Reference range for the penetration value |
| `blast_radius_m` | `float` | Area effect radius (HE/frag) |
| `fragmentation_radius_m` | `float` | Fragmentation effect radius |
| `guidance` | `str` | `GuidanceType` enum name |
| `propulsion`, `max_speed_mps` | `str`, `float` | Propulsion mode and modeled maximum speed |
| `pk_at_reference` | `float` | Optional probability at the ammunition reference condition |

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

This behavior is optional and fail-closed. A scenario activates the commander
runtime only when every side declares a non-empty, catalog-backed
`commander_profile`. If every side leaves that field blank and
`commander_config` is omitted, no commander engine is created; partial side
coverage, or a `commander_config` with blank side profiles, is rejected.
Scenario loading validates exact initial- and future-unit profile overrides and
doctrinal-school references before roster mutation, registers the resulting
assignments with the OODA runtime, applies the same authority to reinforcement
arrivals, and includes the commander/OODA/school topology in checkpoint
continuation. The profiles below therefore describe available catalog
capabilities, not behavior automatically active in every scenario.

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
