# Phase 100: Khafji (1991) — Second Block 11 Golden Scenario

**Status**: Complete (scenario, engine fixes, regression); UI walkthrough pending manual verification.
**Block**: 11 (Golden Scenarios & End-to-End Engine Validation through UI).

## Summary

Phase 100 delivers the second Block 11 golden scenario: **Battle of Khafji, 29 January – 1 February 1991**. Iraqi III Corps' multi-axis mechanized thrust into Khafji, Saudi Arabia — the first major ground engagement of Desert Storm. Full OOB (~230 units across coalition + Iraqi forces) with hybrid strategic+tactical tick resolution, USS Missouri on the NGFS gun line, and emergent Spirit 03 AC-130H loss as an intended behavioral target.

This phase built at considerably larger scale than Debecka (101 blue + 132 red = 233 units vs. Debecka's 84 total) and exposed a new class of engine-fidelity gaps. Three structural issues were fixed (16"/50 era-availability + target-domain override); several remain as accepted limitations documented for future-block work.

## Research

Two-pass research:
- **Phase 98 OOB brief** — unit/weapon/sensor identifiers (Iraqi III Corps, Coalition TF Abu Bakr)
- **Phase 100 deep research** (this phase) — terrain, environment, commander profiles, doctrine assignments, outcome envelope, naval-gunfire specifics, Spirit 03 emergent-behavior requirements, hybrid tick recommendations

Key corrections from Phase 98:
- **USS Missouri (BB-63) was on station during the main battle**, not Wisconsin (as initially claimed before Phase 98 reconciliation). Wisconsin's first Khafji-area fire mission was 8 Feb.
- Spirit 03 lost **31 Jan 0635L to SA-7 Strela-2 MANPADS** (not SA-6 or SA-14 as some period sources suggested)
- III Corps offensive involved **~2,000 personnel in several hundred AFVs**, with ~100-200 destroyed in the immediate Khafji battle area and ~600 when counting follow-on interdiction

## Data Authored

37 new YAML files via 4 parallel authoring agents:

### Ground units (7)
- `saudi_v150.yaml` — SANG V-150 Commando with TOW variant
- `qatari_amx30b2.yaml` — Qatari AMX-30B2 MBT
- `us_lav25.yaml` — USMC LAV-25
- `us_lav_at.yaml` — USMC LAV-AT (TOW variant)
- `iraqi_brdm2.yaml` — Iraqi BRDM-2 scout
- `saudi_sang_squad.yaml` — SANG dismounted infantry
- `us_marine_recon_team.yaml` — USMC Recon stay-behind team (Ingraham/Lentz profiles)

### Fixed-wing aircraft (5)
- `a10a.yaml` — A-10A Thunderbolt II (primary daylight CAS)
- `av8b.yaml` — AV-8B Harrier II
- `ac130h.yaml` — AC-130H Spectre gunship (Spirit 03 context)
- `f15e.yaml` — F-15E Strike Eagle (LANTIRN)
- `ov10a.yaml` — OV-10A Bronco (FAC)

### Naval + rotary (2)
- `iowa_bb.yaml` — Iowa-class battleship unit (Missouri/Wisconsin)
- `ah1w.yaml` — USMC AH-1W SuperCobra

### Weapons + ammunition (23)
- Guns (6): `gau8_30mm`, `gau12_25mm`, `ac130_105mm`, `ac130_40mm_bofors`, `m197_20mm`, `mk38_5in38`
- Missiles (2): `agm65_maverick`, `sa7_strela2`
- Rockets (1): `frog7_launcher` (9K52 Luna-M TEL)
- Artillery (4): `d30_122mm`, `bm21_grad`, `2s1_gvozdika`, `2s3_akatsiya`
- Ammunition (10): AGM-65/SA-7/FROG-7 warheads, D-30/105mm/40mm HE, GAU-8 APFSDS, GAU-12 APDS, Rockeye CBU, 5"/38 HC

### Leveraged existing
- F/A-18C, F-14B (Phase 99)
- B-52H, F-16C, AH-64D (Block 2/3)
- 16in50_naval weapon + 16in_ap_mk8 / 16in_hc_he ammo (**copied from `data/eras/ww2/` to main `data/weapons/naval/` and `data/ammunition/naval/`** so modern-era scenarios can load them — see Gap section)

All files carry source-citation comment blocks (Tier 1/2/3) per Phase 98 calibration-template conventions.

## Scenario YAML

`data/scenarios/khafji/scenario.yaml`:

- **Date**: 1991-01-29T20:00:00+03:00 (Iraqi border-crossing hour)
- **Duration**: 72 hours
- **Tick resolution (hybrid)**: `strategic_s: 1800`, `operational_s: 300`, `tactical_s: 5` — engine auto-switches based on active battles and closing-range detection
- **Location**: 28.43°N, 48.50°E (Khafji town)
- **Weather**: patchy fog + smoke from Kuwaiti oil fires; visibility 8km; 12°C; humidity 0.55
- **Terrain**: 60×50 km flat desert
- **Blue forces**: 101 units — SANG + Qatari + USMC LAR + SF ODAs + Marine Recon + 11th Marines artillery + full CAS stack (4× A-10, 4× F/A-18C, 2× F-14B, 2× F-15E, 2× F-16C, 2× AV-8B, 3× AC-130H, 2× OV-10A, 2× B-52H, 4× AH-1W) + USS Missouri (BB-63)
- **Red forces**: 132 units — Iraqi III Corps (3rd AD Salahuddin T-72s + 5th Mech + 1st Mech elements) with armor, IFVs, MT-LBs, dismounts, BRDM-2 recon, ZSU-57-2 AA
- **Coalition CEV**: 2.0 (air dominance + SOF + prepared defense); cohesion 0.85
- **Iraqi CEV**: 0.5 (conscript + post-air-campaign degradation); cohesion 0.45 (brittle baseline)
- **Rout cascade**: `rout_cascade_radius_m: 500`, `rout_cascade_base_chance: 0.35`, `rout_cascade_shaken_susceptibility: 0.7` (aggressive for Iraqi mass-surrender dynamic)
- **Victory conditions**: `force_destroyed` (target_side=red, threshold=0.4), `morale_collapsed` (target_side=red), `time_expired` fallback to blue at 72h

## Engine Fixes

### Fix 1: 16"/50 Mk 7 cross-era availability

**Symptom**: USS Missouri's main battery didn't appear in its `unit_weapons` list despite being in equipment + `weapon_assignments`.

**Root cause**: `16in50_naval.yaml` lived in `data/eras/ww2/weapons/naval/`. `ScenarioLoader` only loads era-specific weapons when the scenario's era is non-modern. Khafji is modern → era weapons never loaded → 16"/50 unavailable.

**Fix**: copied `16in50_naval.yaml` + its two ammo rounds (`16in_ap_mk8.yaml`, `16in_hc_he.yaml`) to the main `data/weapons/naval/` and `data/ammunition/naval/` trees. Iowa-class BBs served across WW2 → Korea → Vietnam → Desert Storm; the weapon is genuinely cross-era and belongs in the main tree.

### Fix 2: Naval gun target-domain override for shore bombardment

**Symptom**: Even after Fix 1, the 16"/50 wouldn't target ground units.

**Root cause**: `WeaponCategory.NAVAL_GUN` defaults to `target_domains: {"NAVAL"}` — prevents ship-to-shore fires.

**Fix**: added `target_domains: [NAVAL, GROUND]` explicit override to `16in50_naval.yaml`, and `[NAVAL, GROUND, AERIAL]` to `mk38_5in38.yaml` (dual-purpose gun used at both surface and shore targets; also engaged air targets historically). The `WeaponDefinition.effective_target_domains()` method already supports explicit `target_domains` override; we just needed to use it.

## Engine gaps

Four gaps were surfaced by this phase. **Three resolved in a follow-up fix commit**; one (AGM-65) partially addressed and still under investigation; performance (Gap 5) remains an accepted limitation.

### Gap 1: Naval-gunfire routing doesn't emit EngagementEvents — RESOLVED

**Symptom**: Even with 16"/50 loaded and target_domains including GROUND, Missouri didn't register any engagements in the event stream.

**Root cause**: `_route_naval_engagement()` in `battle.py` routes `NAVAL_GUN` category weapons through `naval_gunnery_engine` or `naval_surface_engine` (both ship-to-ship oriented). If those engines handle the engagement (return `(True, status)`), the result gets appended to `pending_damage` with the naval weapon_id — but no `EngagementEvent` is published. The shore-bombardment fallback (lines 615-632) only fires if the ship-to-ship routes return no engine, AND it uses `naval_gunfire_support_engine` which may not be wired in all scenarios.

**Fix applied**: added `_publish_naval_engagement_event()` helper in `battle.py`; `_route_naval_engagement()` now publishes `EngagementEvent` for every NAVAL_GUN routing path (shore bombardment, ship-to-ship gunnery, fallback modern naval gun engagement). Verified in-scenario: USS Missouri fires 16"/50 at 61 engagements in 400 ticks at the coastal-road Iraqi column. Also fixed a subtle ordering bug: the shore-bombardment block was after the ship-to-ship block, so `naval_gunnery_engine` would intercept BB vs ground engagements before the NGSE code path could run. Re-ordered so ground targets always try NGSE first.

### Gap 2: Iraqi artillery weapons authored but no Iraqi artillery unit carries them — RESOLVED

Authored D-30, BM-21, 2S1, 2S3, FROG-7 weapons — but no `iraqi_artillery_battery` unit was authored. Iraqi indirect fire doesn't occur in the scenario. Pattern: weapons exist, no equipment → no wiring.

**Fix applied**: authored `iraqi_d30_battery.yaml` (6-gun D-30 towed howitzer battery, 43 crew, ARTILLERY_TOWED) and `iraqi_bm21_grad.yaml` (4-launcher BM-21 Grad MRL battery, ROCKET_ARTILLERY). Added to Khafji scenario OOB. Indirect fire can now engage via the engine's existing `_INDIRECT_FIRE_CATEGORIES` routing path.

### Gap 3: SA-7 MANPADS not in Iraqi equipment — RESOLVED

The user explicitly requested Spirit 03 as emergent behavior. Required dependency: Iraqi MANPADS present in Red force. SA-7 weapon is authored but no Iraqi unit carries it. Emergent behavior cannot occur.

**Fix applied**: authored `iraqi_sa7_team.yaml` (2-man LIGHT_INFANTRY MANPADS team, max_speed 1.1 m/s, training 0.35, two-weapon pattern matching `javelin_team` — "9K32 Strela-2 MANPADS" launcher + "SA-7 Missile Round" both mapped to `sa7_strela2` weapon). Added 6 teams to Iraqi OOB. Scenario now carries the ingredients for emergent Spirit 03-class losses: AC-130H operating at 2,100 m MSL + SA-7 max altitude 2,300 m + daylight exposure past sunrise. Engine gaps on aircraft altitude/aspect-dependent PK and time-of-day IR modifier (flagged in Phase 100 research brief section K) remain deferred — the emergent behavior is now *possible* but its frequency is driven by whatever PK the current engine assigns.

### Gap 4: AGM-65 Maverick authored but not firing — PARTIALLY RESOLVED

A-10 and AV-8B carry AGM-65 historically — primary anti-armor munition at Khafji. Aircraft equipment uses generic "Wing/Fuselage Ordnance Stations" mapped to `bomb_rack_generic` (compatible only with dumb bombs + LGB + JDAM). AGM-65 is a `MISSILE_LAUNCHER` category weapon that doesn't fit the bomb_rack pattern.

**Root cause (partial)**: A-10 equipment already lists "AGM-65 Maverick"; `_WEAPON_NAME_MAP` maps it to `agm65_maverick`; `unit_weapons` loads it with correct range and ammo. However **weapon-level `traverse_deg` constraint** was filtering it out — AGM-65 has `traverse_deg: 30.0` (forward-cone mount), and aircraft default heading = 0° (north). Targets south of the aircraft fail the 15° half-cone check (180° bearing diff). Same pattern as Phase 99's `seeker_fov_deg` bug, different constraint field.

**Partial fix applied**: added AERIAL + LIGHT_INFANTRY exemption to the `traverse_deg` check in `battle.py` (analogous to the Phase 99 seeker-FOV exemption). Aircraft can maneuver to face targets; shoulder-fired launchers rotate bodily. Regression tests (9,354) pass with no regressions.

**Status after fix**: AGM-65 still shows 0 engagements in a 400-tick verification run despite the traverse exemption. Further investigation needed — possibly rate-of-fire cadence (10 rpm = 1 shot per 6s; tactical tick = 5s, so AGM-65 is cooldown-gated every other tick) combined with GAU-8 being preferred by the tie-breaking in weapon selection. Filed as a follow-on investigation; commit documents partial fix + open question.

### Gap 5: Performance at full-OOB scale

233-unit scenario runs at ~1.4 sec per tactical tick on current hardware. A 1500-tick run takes ~35 minutes. 10-iteration MC would take ~5.8 hours — prohibitive. Phase 100 regression uses a 3-iteration MC with wider envelope tolerances as a pragmatic response.

**Root cause**: per-tick cost is dominated by aircraft engagement loop (GAU-8 fires almost every tick across 4 A-10s) and STRtree rebuild for 233 units.

**Future fix candidates**: scoping back aircraft count to reduce per-tick engagements; engagement-loop caching; or using operational ticks (300s) during air-CAS-only periods.

## Calibration Journey

Four iterations:

1. **Initial (threshold 0.6, red_start_y=40000)**: Red formation stacks ~6,600m deep → leading tanks at y=33,700 while trailing units sprawl to ~40,300. Coalition at y=17,500–22,500. Formations don't overlap, but Iraqi approach drive consumes all the compute budget; aircraft fire GAU-8 heavily before Iraqi closes. After 500 ticks only 2 kills.
2. **Iter 2 (Iraqis closer — y=25000)**: Formation overlap — Red units spawn *inside* Blue positions at y=18,400–31,600. Blue loses 28 units to 19 red destroyed in 1000 ticks. Winner: 'red' via max_ticks.
3. **Iter 3 (red_start_y=32000 + formation_spacing 100m + threshold 0.4)**: Blue wins via force_destroyed; Red destroyed=36 (27% of 132). Blue destroyed=12. Duration 1444 ticks. Naval guns still silent.
4. **Iter 4 (16"/50 cross-era fix + target_domains override)**: Missouri's 16"/50 + 5"/38 now load, but routing through `_route_naval_engagement` silently consumes the engagement without emitting an EngagementEvent (Gap 1). Blue still wins 3/3 across seeds 42-44; metrics consistent (~11 blue_d, ~26 red_d avg).

Final calibration is iter 4. Naval gunfire emergence is deferred to a future engine-fix phase.

## Test Results

- **New regression test**: `tests/validation/test_khafji.py` — 7 tests, all pass under `@pytest.mark.slow` (3-iter MC + 3 single-seed dynamics)
- **Registered in `HISTORICAL_WINNERS`**: `"khafji": "blue"`
- **Coverage assertion**: passes (tested inline post-registration)

## UI walkthrough (pending manual verification)

Depth checklist expected observations:
- **Results tab**: Dominant Weapon likely `gau8_30mm` (A-10 cannon), no `javelin_clm` (none present), no naval gunfire (Gap 1). Total engagements > 4000.
- **Charts tab**: Force Strength shows Iraqi decline; Casualties by Weapon dominated by GAU-8 + M61A1 Vulcan + m240/m242; bombs appear (`bomb_rack_generic`). Naval guns absent.
- **Map tab**: Iraqi armor column advancing south from y=32000; Coalition SANG + Qatari + TF Shepherd at y=17500-22500 arranged east-west; Missouri offshore position (actually co-located with Blue cluster due to no separate naval spawn — visual anomaly).
- **Analysis tab**: engagement detail modal shows GAU-8 strafing runs, bomb drops, T-72/T-55 main gun exchanges.

## Files touched

New:
- `data/scenarios/khafji/scenario.yaml`
- `data/units/armor/saudi_v150.yaml`
- `data/units/armor/qatari_amx30b2.yaml`
- `data/units/armor/us_lav25.yaml`
- `data/units/armor/us_lav_at.yaml`
- `data/units/armor/iraqi_brdm2.yaml`
- `data/units/infantry/saudi_sang_squad.yaml`
- `data/units/sof/us_marine_recon_team.yaml`
- `data/units/air_fixed_wing/a10a.yaml`
- `data/units/air_fixed_wing/av8b.yaml`
- `data/units/air_fixed_wing/ac130h.yaml`
- `data/units/air_fixed_wing/f15e.yaml`
- `data/units/air_fixed_wing/ov10a.yaml`
- `data/units/naval_surface/iowa_bb.yaml`
- `data/units/air_rotary_wing/ah1w.yaml`
- `data/weapons/guns/gau8_30mm.yaml`
- `data/weapons/guns/gau12_25mm.yaml`
- `data/weapons/guns/ac130_105mm.yaml`
- `data/weapons/guns/ac130_40mm_bofors.yaml`
- `data/weapons/guns/m197_20mm.yaml`
- `data/weapons/guns/mk38_5in38.yaml`
- `data/weapons/missiles/agm65_maverick.yaml`
- `data/weapons/missiles/sa7_strela2.yaml`
- `data/weapons/rockets/frog7_launcher.yaml`
- `data/weapons/artillery/d30_122mm.yaml`
- `data/weapons/artillery/bm21_grad.yaml`
- `data/weapons/artillery/2s1_gvozdika.yaml`
- `data/weapons/artillery/2s3_akatsiya.yaml`
- `data/ammunition/missiles/agm65_warhead.yaml`
- `data/ammunition/missiles/sa7_warhead.yaml`
- `data/ammunition/rocket/frog7_warhead.yaml`
- `data/ammunition/rounds/d30_122mm_he.yaml`
- `data/ammunition/rounds/ac130_105mm_he.yaml`
- `data/ammunition/rounds/ac130_40mm_he.yaml`
- `data/ammunition/rounds/gau8_apfsds.yaml`
- `data/ammunition/rounds/gau12_apds.yaml`
- `data/ammunition/rounds/mk20_rockeye.yaml`
- `data/ammunition/rounds/mk38_5in38_hc.yaml`
- `data/weapons/naval/16in50_naval.yaml` (copied from ww2 era)
- `data/ammunition/naval/16in_ap_mk8.yaml` (copied from ww2 era)
- `data/ammunition/naval/16in_hc_he.yaml` (copied from ww2 era)
- `tests/validation/test_khafji.py`
- `docs/devlog/phase-100.md`

Modified:
- `data/eras/ww2/weapons/naval/16in50_naval.yaml` (added `target_domains: [NAVAL, GROUND]`)
- `data/weapons/guns/mk38_5in38.yaml` (added `target_domains: [NAVAL, GROUND, AERIAL]`)
- `stochastic_warfare/validation/scenario_runner.py` (Phase 100 weapon + sensor name mappings)
- `tests/validation/test_historical_accuracy.py` (registered khafji in HISTORICAL_WINNERS)

## Next phase

Phase 101: Fallujah Phase Line Fran (2004). Urban combat + IEDs + booby-trapped structures + AC-130 gunship (reuses AC-130H from this phase) + M1A2 SEP + M2A3 Bradley + engineer assets. Most complex scenario yet on the UW / urban-terrain axis.
