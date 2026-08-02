# Block 11 Scenario Data Gap Audit

Cross-scenario inventory of units, weapons, sensors, and devices required vs. available. Produced Phase 98 from four parallel `/research-military` OOB briefs. Authoring priorities below drive Phase 99–102 data work.

## Existing inventory snapshot

**Modern units (data/units/):**
- Air defense: de_shorad, iron_beam, patriot, s300pmu, sa11_buk, sa6_gainful
- Air fixed-wing: a4_skyhawk, b52h, c17, ea18g, f16c, j10a, mig29a, mq9, sea_harrier, su27s, super_etendard
- Air rotary-wing: ah64d, mi24v
- Armor: challenger2, leopard2a6, m1a1_abrams, m1a2, shot_kal, t55a, t62, t72m, t90a
- Artillery: m109a6
- Infantry: bmp1, bmp2, btr80, insurgent_squad, iraqi_republican_guard, javelin_team, kornet_team, m3a2_bradley, us_rifle_squad
- Naval amphibious: lhd1
- Naval subsurface: kilo636, ssn688
- Naval surface: ddg51, ddg_helios, sovremenny, type22_frigate, type42_destroyer
- SOF: sf_oda, ranger_platoon
- Support: engineer_squad, hemtt

**Modern weapons (data/weapons/):**
- Guns: m256_120mm, m240_762mm, m2hb_50cal, m61a1_vulcan, mk45_5inch, m4_556mm, m134_minigun, l7_105mm, d10t_100mm, 2a46m_125mm, 2a28_grom_73mm, u5ts_115mm, m242_bushmaster, 2a42_30mm, mk12_20mm
- Artillery: m284_155mm, m252_81mm_mortar, m270_mlrs, m142_himars
- Missiles: aim120_amraam, aim9x_sidewinder, agm114_hellfire, mim104_pac3, rgm84_harpoon, bgm109_tomahawk, fim92_stinger, sm2_standard, at3_sagger, sea_dart, am39_exocet, tow2_atgm, javelin_clm, kornet_9m133, asroc_rur5, agm88_harm, r77, r73, igla_9k38, sa6_3m9
- Torpedoes: mk48_adcap, mk46_lightweight, mk54_torpedo
- Defense: mk15_phalanx, mk41_vls
- IED: command_wire_ied, pressure_plate_ied, vbied, remote_ied
- DEW: de_shorad_50kw, helios_60kw, iron_beam_100kw, glws_dazzler, phaser_hpm
- Rockets/rifles: rpg7, ak47
- Bombs: bomb_rack_generic

**Historical-era weapons reusable**: `data/eras/ww2/weapons/naval/16in50_naval.yaml` is directly applicable to USS Missouri/Wisconsin 16"/50 Mark 7 rifle.

**Sensors (data/sensors/):**
- mk1_eyeball, thermal_sight, nvg, active_ir_sight, aaq33_sniper, laser_warning_receiver, esm_suite, uv_maws, apg68_radar, apq94_radar, apy1_radar, air_search_radar, ground_search_radar, 1s91_straight_flush, passive_sonar, active_sonar, sqr19_towed_array, beam_riding_tracker

---

## Per-scenario gap matrix

Legend:
- **E** — exists, use as-is
- **A** — exists close, needs minor adaptation or override
- **N** — new authoring required
- **R** — reuse from existing file (overlap with another scenario)

### Debecka Pass 2003 (Phase 99)

| Item | Status | Notes |
|------|--------|-------|
| **Units** | | |
| US SF ODA team (3rd SFG / 10th SFG) | A | Adapt `sf_oda.yaml`; verify 12-man ODA with GMV HMMWV + Javelin + Mk19 + M2 ring mounts |
| Peshmerga irregular infantry (KDP) | N | New. Similar structure to `insurgent_squad` but lighter ATGM capability |
| Iraqi T-55 mechanized battalion | A | Use existing `t55a.yaml` |
| Iraqi MT-LB APC | N | New. 7.62mm PKT turret, 2+11 crew |
| Iraqi ZSU-57-2 SPAAG | N | New. Twin 57mm S-68 in direct-fire role (used against Debecka SF per research) |
| Iraqi 34th Inf Div dismounts | A | Reuse `iraqi_republican_guard` with lowered training; 34th was NOT Republican Guard, use a regular-army variant |
| F-14D Tomcat (USN CAS) | N | New. LANTIRN pod, GBU-16 Paveway II |
| F/A-18C Hornet (USN CAS) | N | New. GBU-31 JDAM, GBU-12, AGM-65 Maverick |
| B-52H Stratofortress | E | `b52h.yaml` exists |
| **Weapons** | | |
| Javelin FGM-148 ATGM | E | `javelin_clm.yaml` exists (note spelling: clm not cmdl) |
| M2 .50 HMG | E | `m2hb_50cal.yaml` |
| Mk19 40mm AGL | N | New |
| M240B 7.62mm | E | `m240_762mm.yaml` |
| M4A1 carbine | E | `m4_556mm.yaml` |
| M224 60mm mortar | N | New. Lighter than M252 81mm |
| T-55 100mm (D-10T) | E | `d10t_100mm.yaml` |
| MT-LB 7.62mm PKT | E | `m240_762mm.yaml` analogue — or may reuse a generic 7.62 |
| ZSU-57-2 57mm S-68 | N | New |
| GBU-31 JDAM (2000lb) | N | New. Free-fall GPS-guided bomb |
| GBU-16 Paveway II (1000lb) | N | New. Laser-guided |
| AKM / PKM / RPG-7 (Iraqi dismounts) | E | Reuse `ak47.yaml` + `rpg7.yaml` (or add akm variant) |
| **Sensors** | | |
| Javelin CLU (day/thermal) | A | May embed in `javelin_clm.yaml` weapon definition |
| AN/PEQ-1 SOFLAM (laser designator) | N | New, TACP-carried |
| T-55/MT-LB optical sights | E | `mk1_eyeball.yaml` adequate for modeling |
| T-55 active IR night sight (TPN-1) | E | `active_ir_sight.yaml` |

### Khafji 1991 (Phase 100)

| Item | Status | Notes |
|------|--------|-------|
| **Units** | | |
| Saudi SANG V-150 Commando | N | New. 90mm / 20mm / TOW variants |
| Qatari AMX-30B2 MBT | N | New. 105mm F1 gun |
| USMC LAV-25 | N | New. 25mm Bushmaster chain gun |
| USMC LAV-AT (TOW variant) | N | New. Or model as LAV-25 with swap loadout |
| USMC 1st Recon Bn team | A | Reuse `sf_oda` or author light recon variant |
| USMC 11th Marines 155mm (M198) | A | Use `m109a6` as placeholder or author M198 tow variant |
| USMC AH-1W Cobra | N | New. TOW + Hellfire + 20mm M197 |
| USAF A-10A Thunderbolt II | N | New. GAU-8 30mm + Mavericks |
| USAF AV-8B Harrier II | N | New. Rockeye CBU + GAU-12 25mm |
| USAF F-15E Strike Eagle | N | New. LANTIRN, Mk 82, CBU-87, GBU-12 |
| USN F/A-18C/D | R | Same as Debecka — author once |
| USAF AC-130H Spectre (+ Spirit 03) | N | New. 105mm + 40mm + 25mm, FLIR + LLLTV |
| USMC OV-10A/D Bronco | N | New. FAC aircraft; Zuni rockets |
| USAF B-52G Stratofortress | A | Close to `b52h`; may reuse |
| USS Missouri BB-63 (Iowa-class) | N | New. **Correction**: research confirms Missouri on station during main battle 29 Jan–1 Feb, not Wisconsin. Either model Missouri or extend scenario to Feb 6+ for Wisconsin. |
| Iraqi T-72M1 (3rd Armored Div) | A | Existing `t72m.yaml` may be close enough |
| Iraqi T-62 | E | `t62.yaml` |
| Iraqi T-55 | E | `t55a.yaml` |
| Iraqi BMP-1 | E | `bmp1.yaml` |
| Iraqi BRDM-2 recon | N | New. 4x4 armored scout car |
| Iraqi MT-LB | R | Same as Debecka |
| Iraqi BTR-60/BTR-80 | A | Existing `btr80.yaml`; add BTR-60 if needed |
| **Weapons** | | |
| LAV-25 M242 25mm Bushmaster | E | `m242_bushmaster.yaml` |
| AH-1W TOW + Hellfire + M197 | A | Reuse `tow2_atgm`, `agm114_hellfire`; new `m197_20mm` |
| A-10 GAU-8 30mm Avenger | N | New. 30mm gatling, anti-armor |
| A-10 AGM-65 Maverick (B/D/G) | N | New. Ground-attack missile |
| AV-8B Mk 20 Rockeye CBU | N | New. Cluster bomb |
| AV-8B GAU-12 25mm | N | New |
| AC-130H/U 25mm GAU-12 | A | Same as AV-8B 25mm? or separate |
| AC-130H/U 40mm Bofors L/60 | N | New |
| AC-130H/U 105mm M102 howitzer | N | New |
| 16"/50 Mk 7 HC (Missouri) | R | **Reuse `data/eras/ww2/weapons/naval/16in50_naval.yaml`** |
| 5"/38 DP (Missouri secondary) | R | Reuse `data/eras/ww2/weapons/naval/5in38_naval.yaml` |
| Iraqi D-30 122mm howitzer | N | New. Towed, widely deployed |
| Iraqi 2S1 Gvozdika 122mm SP | N | New |
| Iraqi 2S3 Akatsiya 152mm SP | N | New |
| Iraqi BM-21 Grad 122mm MRL | N | New |
| Iraqi T-72M1 125mm (2A46) | E | `2a46m_125mm.yaml` |
| Iraqi BMP-1 73mm (2A28 Grom) | E | `2a28_grom_73mm.yaml` |
| Iraqi AT-3 Sagger (9M14) | E | `at3_sagger.yaml` |
| SAM: SA-7 Grail MANPADS | A | Similar to `igla_9k38`; may suffice |
| SAM: SA-6 (killed Spirit 03) | E | `sa6_3m9.yaml` |
| **Sensors** | | |
| LAV M36E1 1st-gen thermal | E | `thermal_sight.yaml` |
| AC-130H AAQ-17 FLIR | A | Adapt `aaq33_sniper` or author AC-130 FLIR |
| AC-130H ASQ-145 beacon tracker | N | Optional — may not be modeled at current fidelity |
| MULE AN/TVQ-2 laser designator | N | New. Used by recon teams calling PGMs |
| JSTARS GMTI radar (E-8A) | N | Optional — scope question. May simulate via enhanced surveillance range |
| T-72/T-62/T-55 TPN night sights | E | `active_ir_sight.yaml` |

### Fallujah Phase Line Fran 2004 (Phase 101)

| Item | Status | Notes |
|------|--------|-------|
| **Units** | | |
| USMC rifle squad (urban) | A | Adapt `us_rifle_squad` with M16A4 + Benelli shotgun + SMAW |
| USMC CAAT anti-armor section | A | May reuse `javelin_team` with adaptations |
| USMC 2nd Tank Bn Co C (M1A1) | E | `m1a1_abrams.yaml` |
| Army TF 2-7 CAV M1A2 SEP | A | Adapt `m1a2` — note SEP variant has Commander's Independent Thermal Viewer (CITV) |
| Army M2A3 Bradley | A | Existing `m3a2_bradley` is M3 variant; adapt or author M2A3 |
| USMC/Army combat engineers | A | Adapt `engineer_squad` |
| USMC AH-1W Cobra | R | Same as Khafji |
| Army OH-58D Kiowa Warrior | N | New. Hellfire + .50 cal + rockets |
| AC-130U Spooky (night) | R | Same family as Khafji AC-130H |
| USMC F/A-18D (Al Asad) | R | Same as Khafji / Debecka |
| USMC AV-8B | R | Same as Khafji |
| USMC M198 155mm howitzer (11th Marines) | R | Same as Khafji |
| Army M109A6 Paladin (82nd FA) | E | `m109a6.yaml` |
| USMC/Army D9 armored bulldozer | N | New. 65-ton urban obstacle-reducer |
| USMC M1064 SP 120mm mortar | N | New (or treat as M109 with mortar loadout) |
| Iraqi insurgent cell | A | Adapt `insurgent_squad` with richer weapon mix |
| Iraqi foreign fighter cell | A | Adapt — possibly new variant |
| **Weapons** | | |
| M16A4 rifle | N | New (or adapt m4_556mm) |
| Benelli M1014 shotgun | N | New. Breaching |
| Mk153 SMAW + thermobaric NE round | N | New. Shoulder-launched multipurpose assault weapon |
| AT-4 84mm LAW | N | New. Single-shot disposable |
| M72A7 LAW | N | New |
| M40A3 7.62mm sniper rifle | N | New |
| M82A3 .50 cal SASR | N | New. Anti-materiel sniper |
| M1A2 SEP 120mm | E | `m256_120mm.yaml` |
| M2A3 Bradley 25mm | E | `m242_bushmaster.yaml` |
| M2A3 Bradley TOW-2 | E | `tow2_atgm.yaml` |
| M198 155mm towed | R | Khafji |
| M109A6 155mm | E | via unit definition |
| Javelin (for bunker-busting) | E | `javelin_clm.yaml` |
| AC-130U 40mm + 105mm + 25mm | R | Khafji |
| F/A-18D GBU-31 JDAM 2000lb | R | Debecka |
| F/A-18D GBU-12 Paveway II 500lb | N | New |
| F/A-18D GBU-38 JDAM 500lb | N | New |
| AGM-65 Maverick | R | Khafji |
| Hellfire AGM-114 | E | `agm114_hellfire.yaml` |
| Insurgent AK/AKM | E | `ak47.yaml` |
| Insurgent RPK/PKM/SVD | N | New (each or one combined) |
| Insurgent RPG-7 with PG-7V/OG-7V | E | `rpg7.yaml` |
| Insurgent RPG-7 TBG-7V thermobaric | N | New round for RPG-7 launcher |
| Insurgent SPG-9 73mm recoilless | N | New |
| Insurgent DShK 12.7mm HMG | N | New |
| Insurgent ZU-23-2 23mm AA | N | New (if needed) |
| Insurgent 60mm/82mm mortars | A | Reuse `m252_81mm_mortar` for 82mm; new 60mm or reuse generic |
| IED: roadside 155mm shell | A | Adapt `command_wire_ied`, `pressure_plate_ied` |
| IED: HBIED (booby-trapped structure) | N | New device class |
| IED: VBIED | E | `vbied.yaml` |
| IED: SVBIED (suicide VBIED) | A | Adapt `vbied.yaml` |
| **Sensors** | | |
| M1A2 SEP CITV (commander thermal) | A | Enhance `thermal_sight.yaml` attributes |
| M2A3 IBAS thermal + CIV | A | Adapt existing thermal sensor |
| AC-130 FLIR suite | R | Khafji |
| AN/PAS-13 TWS (3 variants) | A | Adapt `thermal_sight` |
| Dragon Eye small UAV | N | New. Squad-level ISR |
| RQ-2 Pioneer UAV | N | New. Fires-adjustment ISR |
| ScanEagle UAV | N | New. Contractor-operated ISR |
| LITENING / ROVER downlink | N | Optional — may abstract |

### Bint Jbeil + INS Hanit 2006 (Phase 102)

| Item | Status | Notes |
|------|--------|-------|
| **Bint Jbeil units** | | |
| IDF Golani infantry squad | A | Adapt `us_rifle_squad` with Tavor TAR-21 / M4A1 + Negev + Galil variants |
| IDF Paratrooper squad (35th Bde) | A | Adapt Golani variant |
| IDF Egoz Recon | A | Adapt `sf_oda` or new SOF variant |
| IDF Maglan | A | Same as Egoz — group into one SOF variant |
| IDF Merkava Mk III Baz | N | New. 120mm smoothbore, LIC suite |
| IDF Merkava Mk IV | N | New. First combat use 2006, no Trophy APS yet |
| IDF Puma AEV | N | New. Heavy combat engineering vehicle |
| IDF M109A5 155mm SP | E | `m109a6.yaml` close enough |
| IDF M270 MLRS | E | `m270_mlrs.yaml` |
| IAF F-16I Sufa | A | Adapt `f16c.yaml` |
| IAF F-15I Ra'am | N | New |
| IAF AH-64A/D Saraph | E | `ah64d.yaml` |
| IAF AH-1F/S Tzefa (Cobra) | A | Similar to USMC AH-1W authored for Khafji |
| Hezbollah local garrison | A | Adapt `insurgent_squad` for village defensive role |
| Hezbollah "Special Forces" | A | Adapt — higher training than local |
| Hezbollah ATGM team ("tank hunter") | E | `kornet_team.yaml` |
| Hezbollah mortar/rocket cell | N | New |
| **Bint Jbeil weapons** | | |
| Kornet-E (9M133, AT-14) | E | `kornet_9m133.yaml` |
| Metis-M (9K115-2, AT-13) | N | New. SACLOS wire-guided ATGM |
| RPG-29 Vampir | N | New. 105mm reusable launcher, tandem HEAT |
| AT-3 Sagger (9M14) | E | `at3_sagger.yaml` |
| AT-5 Konkurs (9M113) | N | New |
| Merkava Mk III/IV 120mm (MG253) | A | Close to M256; may reuse `m256_120mm.yaml` |
| Merkava 60mm internal mortar | N | Optional — small support weapon |
| Merkava 12.7mm roof MG | E | `m2hb_50cal.yaml` analogue |
| IDF MAG 7.62mm (FN MAG) | E | `m240_762mm.yaml` analogue |
| IDF Negev 5.56mm LMG | A | Adapt `m4_556mm` |
| IDF Tavor TAR-21 | A | Adapt `m4_556mm` |
| Hezbollah AK/PKM/SVD | E | `ak47.yaml` + `rpg7.yaml` coverage; add PKM/SVD |
| GBU-28 bunker buster | N | Optional (scope question) |
| Spice EO guided bomb | N | Optional |
| **Bint Jbeil sensors** | | |
| Merkava Mk IV El-Op Knight Mark 4 FC | A | Enhance `thermal_sight` |
| Merkava Amcoram LWS-2 LWR | E | `laser_warning_receiver.yaml` |
| IDF Elbit MARS thermal (dismount) | A | Adapt existing thermal |
| IDF Searcher Mk II UAV | N | New |
| IDF Hermes 450 UAV | N | New (or one representative UAV) |
| **INS Hanit vignette — units** | | |
| INS Hanit (Sa'ar 5 corvette) | N | New. Hull 503 |
| Hezbollah coastal launcher TEL | N | New. Truck-mounted |
| Merchant ship "Moonlight" (Cambodian-flag, struck by first missile) | N | Optional — model as civilian target or ignore |
| **INS Hanit vignette — weapons** | | |
| C-802 "Noor" (Iranian YJ-83 variant) | N | New. Sea-skimming ASCM, 120km range, 165kg SAP warhead |
| Sa'ar 5 Harpoon Block 1C (RGM-84) | E | `rgm84_harpoon.yaml` |
| Sa'ar 5 Gabriel Mk II/III | N | New (or out-of-scope for this vignette) |
| Sa'ar 5 Barak-1 SAM (PD) | N | New |
| Sa'ar 5 Phalanx CIWS | E | `mk15_phalanx.yaml` |
| Sa'ar 5 76mm Oto Melara | N | New |
| Sa'ar 5 Typhoon 25mm RWS | N | New (or out-of-scope) |
| **INS Hanit vignette — sensors** | | |
| Sa'ar 5 EL/M-2218S 3D S-band radar | A | Adapt `air_search_radar` |
| Sa'ar 5 EL/M-2221 STGR fire control | A | Adapt existing radar |
| Sa'ar 5 Elisra NS-9003/9005 ESM | E | `esm_suite.yaml` |
| Sa'ar 5 Rafael Deseaver chaff/decoy | N | New (or model via ESM override) |
| Coastal missile targeting network (surveillance cueing plus battery fire control) | A | `ground_search_radar` functional analogue; explicit anti-ship fire-control role |

---

## Cross-scenario overlap (authoring optimization)

Authoring once and reusing saves effort across 15+ items:

| Shared item | Phases using |
|-------------|-------------:|
| F/A-18 Hornet family | 99 (Debecka), 100 (Khafji), 101 (Fallujah) |
| AC-130 gunship (H or U) | 100 (Khafji), 101 (Fallujah) |
| AH-1W Cobra | 100 (Khafji), 101 (Fallujah), 102 (IDF AH-1F/S as adapted) |
| MT-LB | 99 (Debecka), 100 (Khafji) |
| RPG-29 Vampir | 101 (Fallujah), 102 (Bint Jbeil) |
| ZU-23-2 | 101 (Fallujah), and possibly 100 (Khafji) |
| GBU-31 JDAM | 99 (Debecka), 101 (Fallujah) |
| GBU-12 Paveway II | 99 (Debecka — as GBU-16 cousin), 101 (Fallujah) |
| Hezbollah/insurgent AK+RPG loadout variants | 101, 102 (shared insurgent base) |
| M198 155mm towed howitzer | 100, 101 |
| AGM-65 Maverick family | 100, 101 |

**Authoring order recommendation**: draft shared items in their first-appearing scenario's phase, then reference without duplication.

---

## Authoring priority by phase

### Phase 99 (Debecka) — new authoring
- MT-LB
- ZSU-57-2 (or skip and use existing AA)
- F-14D Tomcat
- F/A-18C Hornet
- Peshmerga infantry
- Mk19 40mm AGL
- M224 60mm mortar
- SOFLAM AN/PEQ-1 sensor
- GBU-31 JDAM
- GBU-16 Paveway II
- **~10 new files**

### Phase 100 (Khafji) — new authoring (net new after Debecka)
- V-150 Commando
- AMX-30B2
- LAV-25 (+ AT variant)
- AH-1W Cobra
- A-10A Thunderbolt II
- AV-8B Harrier II
- AC-130H Spectre
- F-15E Strike Eagle
- OV-10 Bronco
- USS Missouri (Iowa-class BB — **scenario uses Missouri not Wisconsin**)
- BRDM-2
- GAU-8 30mm
- AGM-65 Maverick
- Rockeye CBU
- D-30, 2S1, 2S3, BM-21 artillery set
- AC-130 40mm/105mm weapons
- **~18 new files**

### Phase 101 (Fallujah) — new authoring (net new)
- M1A2 SEP (adaptation), M2A3 Bradley (adaptation)
- OH-58D Kiowa Warrior
- D9 bulldozer
- M16A4, Benelli shotgun, M40A3, M82A3
- Mk153 SMAW (with thermobaric variant)
- AT-4, M72A7
- RPG-29 Vampir (shared)
- SPG-9 recoilless
- DShK 12.7mm
- ZU-23-2
- RPG-7 thermobaric round (TBG-7V)
- Dragon Eye, RQ-2 Pioneer, ScanEagle UAVs
- GBU-38, GBU-12 Paveway II
- HBIED (booby-trapped structure) device class
- **~18 new files**

### Phase 102 (Bint Jbeil + Hanit) — new authoring (net new)
- Merkava Mk III
- Merkava Mk IV
- Puma AEV
- F-15I Ra'am
- Hezbollah atgm team variant (if different from kornet_team)
- Metis-M (AT-13)
- AT-5 Konkurs
- Searcher Mk II / Hermes 450 UAV
- INS Hanit (Sa'ar 5)
- C-802 "Noor" missile
- Barak-1 SAM
- Oto Melara 76mm
- Rafael Deseaver decoy
- **~13 new files**

**Total estimated new authoring**: ~60 files across Phases 99–102 (counting variants separately). Each with cited source per the conventions in `calibration-template.md`.

---

## Unresolved dependencies flagged for scenario phases

Items that may need deeper research in the respective scenario phase:

- **Debecka**: B-52H JDAM weight class — source-reported "1000-lb JDAMs" is inconsistent with standard GBU-31 (2000lb). Re-confirm in Phase 99.
- **Khafji**: Iraqi 1st Mechanized Division brigade composition — multiple sources, contested.
- **Khafji**: **Battleship selection** — Missouri (29 Jan–1 Feb main battle) vs. Wisconsin (Feb 6+ subsequent phase). Decide in Phase 100 whether to model main battle or extended timeframe.
- **Fallujah**: AC-130 daytime availability — denied/allowed is contested. Model as night-only per primary sources.
- **Fallujah**: precise 2-7 CAV tank/Bradley company composition unavailable from open sources.
- **Bint Jbeil**: Hezbollah fighter counts (60 local + 40 SF + ATGM teams) are IDF estimates, not documented.
- **Bint Jbeil**: Merkava Mk IV share of armor losses disputed across sources.
- **Hanit**: exact range at intercept and ESM/EW posture vary by source. Model "defensive suite degraded" as neutral between accounts.

---

## Living document

This audit is a **living document**. As scenario phases discover additional dependencies or reclassify items, they update this file in the same commit as the scenario data. New items get a status marker and a scenario reference.
