# Stochastic Warfare -- Block 11 Development Phases (98--102)

## Philosophy

Block 11 is the **golden scenarios block**. The engine has ~60 domain engines and a UI capable of visualizing their output, but the existing scenario library is too narrow to exercise engine breadth. Block 11 builds four historically-grounded modern-era scenarios, each calibrated to reproduce a documented outcome envelope and each walked through the UI with an explicit depth checklist.

**Design principle**: Zero new engine capabilities. Every scenario uses existing systems. Missing unit/weapon YAML is authored from real-world data.

**Exit criteria**:
1. Four scenario YAMLs (Debecka Pass, Khafji, Fallujah Phase Line Fran, Bint Jbeil) loadable and runnable
2. Each scenario's 10-iteration MC matches historical winner in ≥70% of iterations
3. Each scenario exercises its targeted engine cluster per the coverage matrix in `brainstorm-block11.md`
4. Four regression tests in `tests/validation/` with bounded envelope assertions
5. Four devlog entries with completed UI walkthrough depth checklists
6. All new unit/weapon YAMLs have cited real-world sources
7. No regressions on existing 40+ scenarios
8. All existing tests pass

**Cross-document alignment**: This document must stay synchronized with `brainstorm-block11.md` (design thinking), `devlog/index.md` (phase status + new deficits), and `specs/project-structure.md` if new module files are added. Run `/cross-doc-audit` after any structural change.

---

## Phase 98: Shared Prework — Gap Audit, Calibration Conventions, Depth Framework

**Status**: Pending.

**Goal**: Build the shared infrastructure all four scenarios will consume — a gap audit of missing units/weapons, a calibration target template, and a depth checklist framework. This phase produces no scenario YAML; it produces the scaffolding that makes scenario authoring mechanical.

**Dependencies**: Block 10 complete (Phase 97). UI functional.

### 98a: Unit/Weapon/Sensor Gap Audit

Compare each scenario's required OOB against existing data. Produce an explicit gap list per scenario.

- **Preliminary research** (one pass per scenario, light touch):
  - Debecka Pass: required OOB from Wong (CSI), USASOC historical accounts
  - Khafji: required OOB from USMC Gazette, USAF Gulf War studies
  - Fallujah: required OOB from USMC History Division (Estes, *U.S. Marines in Iraq*)
  - Bint Jbeil: required OOB from Harel & Issacharoff *34 Days*, Matthews (CSI) *We Were Caught Unprepared*
- **Gap inventory** (one document):
  - `docs/scenarios/gap-audit.md` — table of required units/weapons/sensors per scenario, existing-or-missing status, authoring priority
- **Naming conventions**:
  - Unit type IDs follow existing modern-era pattern: `{nation}_{role}_{variant}` (e.g., `us_sf_odb_team`, `iraqi_t55_mech`)
  - Weapon IDs follow: `{designation}_{caliber_or_model}` (e.g., `javelin_cmdl`, `bb_64_16in`)
  - Sensor IDs follow: `{nation}_{role}_{type}` (existing pattern)

### 98b: Calibration Target Template

Define the envelope-based target structure used by every scenario's regression test.

- **`docs/scenarios/calibration-template.md`** (new) -- Documents:
  - How to define a target envelope (winner rate, duration percentiles, casualty percentiles)
  - Permitted vs. forbidden calibration overrides (from brainstorm)
  - Citation format for historical figures
- **`stochastic_warfare/tools/envelope_check.py`** (new) -- Helper functions:
  - `check_winner_envelope(results: dict, expected_winner: str, min_rate: float = 0.7) -> tuple[bool, str]`
  - `check_duration_envelope(results: dict, historical_s: float, tolerance: float = 0.5) -> tuple[bool, str]`
  - `check_casualty_envelope(results: dict, side: str, historical: int, tolerance: float = 0.4) -> tuple[bool, str]`
  - `count_destructions_by_weapon(scenario_path: str, weapon_id: str, seed: int) -> int`
  - Used by all four regression tests — keeps assertions consistent

### 98c: Depth Checklist Framework

Formalize the UI walkthrough checklist so each scenario's verification is reproducible.

- **`docs/scenarios/depth-checklist-template.md`** (new) -- Template with:
  - Results tab checks (Dominant Weapon, Hit Rate, Total Engagements, Peak Suppressed, Rout Cascades)
  - Charts tab checks (all 8 charts show non-trivial data)
  - Map tab checks (all 5 overlay toggles, engagement flash, 7 sidebar fields, legend)
  - Analysis tab checks (filters, engagement detail modal, doctrine compare)
  - Scenario-specific expected observations
- Each scenario phase (99–102) copies this template into its devlog entry, pre-filled with expected observations, then checks items off during the walkthrough.

### 98d: Calibration Scenarios Registration

The `CALIBRATION_SCENARIOS` registry (Phase 90) is how validation batch runs discover scenarios. Block 11 scenarios register here after their regression tests pass.

- **`stochastic_warfare/validation/calibration_scenarios.py`** (modified) -- Add entries for:
  - `debecka_pass_2003`
  - `khafji_1991`
  - `fallujah_phase_line_fran_2004`
  - `bint_jbeil_2006`
  - Each entry is stub until its scenario phase completes; then the phase updates the entry with actual parameters.

**Tests** (~8):
- `envelope_check` helpers produce correct pass/fail given synthetic results
- `count_destructions_by_weapon` correctly tallies a synthetic event stream
- Gap audit doc is loadable as structured data (if we format it as YAML or machine-readable table)

**Deliverables summary**:
- Gap audit doc
- Calibration template doc
- Depth checklist template doc
- Envelope check helper module + tests
- Calibration scenarios registry stubs

---

## Phase 99: Debecka Pass (Iraq, April 6, 2003)

**Status**: Pending.

**Goal**: First golden scenario. Demonstrates the scenario-authoring pipeline end-to-end on the simplest case. 31 US Special Forces + ~80 Peshmerga defenders engage an Iraqi mechanized battalion advance. Javelin ATGM employment is the defining tactical event; CAS support from F-14D, F-15E, A-10, F-16 layers multi-service joint fires.

**Dependencies**: Phase 98 complete.

**Historical outcome** (from Wong, *A Different Kind of War*, Combat Studies Institute 2011, and USASOC 3rd SFG AAR):
- Winner: Blue (US/Peshmerga) — Iraqi force repulsed, withdrew
- Duration: ~6 hours main engagement
- Iraqi casualties: estimated 20–30 vehicles destroyed (of ~40 committed), ~100–200 dismounts
- US casualties: 0 KIA (1 Navy A-10 pilot KIA earlier in war from a different incident) — *one friendly-fire JDAM strike wounded multiple team members and killed several Peshmerga; this is a key historical event we do not attempt to reproduce probabilistically*
- Key dynamic: Javelin ATGMs from ~3000m destroyed T-55s and MT-LBs before the Iraqi force could close; CAS finished survivors

### 99a: Research (`/research-military`)

Produce `docs/scenarios/debecka_pass.md` with:
- Full OOB (US ODB team composition, Peshmerga strength estimate, Iraqi 34th Bde mech battalion)
- Terrain description (plains north of Kirkuk, ridgeline, exposed road)
- Weather (early April, clear, ~15°C)
- Time of day (mid-day attack)
- Commander profile (US team aggressive/defensive, Iraqi scripted advance)
- Doctrine school assignment (US: combined_arms, Iraqi: mass_maneuver or similar)
- Historical ROE (US: WEAPONS_FREE; Iraqi: scripted advance with organic fires)
- Envelope parameters (from historical outcome above)

### 99b: Data Authoring

Author units/weapons identified in Phase 98's gap audit. Expected:

- **`data/units/infantry/us_sf_odb_team.yaml`** (new) -- 12-man SF team, M4A1/M240/MK19, Javelin, man-portable
- **`data/units/infantry/peshmerga_infantry.yaml`** (new) -- Irregular infantry, AK-series, RPG-7, low training
- **`data/units/armor/iraqi_t55_mech.yaml`** (new or reuse/rename) -- T-55 main gun tank with 100mm
- **`data/units/armor/iraqi_bmp1_mech.yaml`** (new or confirm existing `bmp1.yaml` adequate)
- **`data/units/armor/iraqi_mtlb.yaml`** (new) -- MT-LB APC
- **`data/weapons/javelin_cmdl.yaml`** (confirm existing or author) -- FGM-148 Javelin, top-attack ATGM
- **`data/weapons/bb_pintle_mk19.yaml`** (confirm existing)
- **`data/units/air/us_f14d.yaml`** (new) -- F-14D CAS sortie (LANTIRN pod)
- **`data/units/air/us_a10c.yaml`** (confirm existing)

All files cite sources per brainstorm's data authoring discipline.

Run `/validate-data` after authoring pass.

### 99c: Scenario YAML

- **`data/scenarios/debecka_pass/scenario.yaml`** (new):
  - `duration_hours: 6`, `tick_duration_seconds: 5.0`
  - Lat/lon: ~35.5°N, 43.8°E
  - Weather: clear, 15°C, wind 3 m/s
  - Terrain: plains with ridgeline overlay
  - Blue: 1× SF ODB team, 4× Peshmerga platoons at ridgeline
  - Red: 10× T-55, 6× BMP-1, 4× MT-LB, 12× dismount platoons
  - CAS: 2× F-14D sorties, 4× A-10 sorties available via ATO
  - Objectives: ridgeline defense, road block
  - Victory conditions: force_destroyed (70%), or time_expired
- `calibration_overrides` block: minimal — rely on `enable_all_modern` and scenario-specific ROE/commander only

### 99d: Calibration Loop

Run 10-iteration MC. Measure vs. envelope. Iterate.

- Expected first-pass issues: Javelin might not dominate if range/Pk defaults don't reflect top-attack geometry; Iraqi mech might close too fast without terrain channeling
- Permitted adjustments: commander CEV, ROE, weather visibility_m if it affects detection unrealistically
- Forbidden: tuning Javelin Pk above documented range

Document calibration iterations in devlog.

### 99e: Regression Test

- **`tests/validation/test_debecka_pass.py`** (new) -- Uses envelope helpers from Phase 98:
  - `test_debecka_pass_winner_envelope` (blue wins ≥7/10)
  - `test_debecka_pass_casualty_envelope` (Iraqi losses 15–40, SF losses ≤3)
  - `test_debecka_pass_javelin_dominance` (Javelin ≥50% of Iraqi armor kills)
  - `test_debecka_pass_cas_activation` (at least 1 CAS engagement per run)
- Marker: `@pytest.mark.slow` if runtime > 10s

### 99f: UI Walkthrough

- Spin up API + frontend
- Run scenario from Scenario Browser → Run page
- Walk Results / Charts / Map / Analysis tabs per depth checklist
- Document checklist results in `docs/devlog/phase-99.md`
- File frontend-rendering issues found as follow-up items (do not block phase completion unless scenario unrunnable)

**Tests** (~8 new + regression):
- Scenario YAML loads without errors
- 4 regression tests (envelope, casualties, Javelin, CAS)
- 3 data authoring tests (unit defs have required fields, weapon ranges plausible, ammo compatible)

---

## Phase 100: Khafji (Saudi Arabia, January 29 – February 1, 1991)

**Status**: Pending.

**Goal**: Second golden scenario. Expands to multi-domain with naval gunfire support. Iraqi 3rd Armored Division and 5th Mechanized Division make a cross-border thrust into Khafji, meet Saudi Task Force Abu Bakr + USMC Marine Reconnaissance + Qatari armor + coalition CAS. First major ground engagement of the Gulf War and a textbook morale cascade as Iraqi units surrender en masse.

**Dependencies**: Phase 99 complete (template validated).

**Historical outcome** (from Grant & Atkinson *Crusade*, USMC Historical Publication *With the 1st Marine Division in Desert Shield and Desert Storm*, USAF Gulf War Air Power Survey Vol II):
- Winner: Coalition (Blue)
- Duration: ~72 hours main engagement, ~36 hours decisive phase
- Iraqi casualties: ~2000 KIA, ~400 captured, ~100 tanks/APCs destroyed (mostly by air)
- Coalition casualties: 43 KIA (11 US Marines, 18 Saudis, 14 Qataris from reports; inc. friendly fire)
- Naval: USS Wisconsin fired 11× 16" shells at Iraqi artillery positions — first BB gunfire since Korea
- Key dynamics: air power dominated; Iraqi morale collapsed after initial advance stalled; large-scale surrenders

### 100a: Research

`docs/scenarios/khafji.md` with OOB, phases of battle (night advance, coalition counter, air interdiction, surrender cascade), terrain (urban Khafji + desert approach corridor), Wisconsin fire mission details.

### 100b: Data Authoring

Expected gaps:

- **`data/units/naval/us_iowa_class_bb.yaml`** (new) -- USS Wisconsin, 16"/50 guns, Tomahawk launchers
- **`data/weapons/bb_mk7_16in.yaml`** (new) -- 16" naval rifle, AP + HC rounds
- **`data/units/armor/saudi_v150_apc.yaml`** (new) -- Saudi V-150 Commando (Cadillac Gage)
- **`data/units/armor/qatari_amx30.yaml`** (new) -- Qatari AMX-30B
- **`data/units/air/us_ac130h.yaml`** (new) -- AC-130H Spectre (first employment in Gulf War)
- **`data/weapons/ac130_105mm_gun.yaml`** (new)
- Existing unit reuse: Iraqi T-62, T-55, BMP-1, MTLB, dismounts

### 100c: Scenario YAML

- Duration: 72 hours (campaign-scale for approach, tactical for town fight)
- Uses `tick_resolution` hybrid (strategic for approach, tactical for Khafji proper)
- Multi-phase objectives: defend town, interdict approach, eliminate pocketed units
- `enable_naval_engagement_routing` and `enable_cas_routing` flags on
- Victory weights favor holding Khafji + Iraqi force destruction

### 100d: Calibration

Expected issue: Iraqi morale cascade must fire. If it doesn't, use `morale_degrade_mod` and `cohesion` overrides within documented ranges. If Wisconsin's fire mission doesn't meaningfully shape outcome, investigate whether naval gunfire routing triggers at the engagement ranges involved (+20 km).

### 100e: Regression Test

- `test_khafji_coalition_wins` (Coalition ≥7/10)
- `test_khafji_iraqi_morale_cascade` (rout_cascades ≥2 per run)
- `test_khafji_wisconsin_engagement` (at least 1 naval_gunfire event per run)
- `test_khafji_cas_dominance` (air engagements > ground direct fire engagements)

### 100f: UI Walkthrough

Depth checklist per template, scenario-specific observations for naval engagement event type, multi-phase timeline, surrender cascades.

---

## Phase 101: Fallujah Phase Line Fran (Iraq, November 9–13, 2004)

**Status**: Pending.

**Goal**: Third golden scenario. Urban combat showcase with unconventional warfare elements. 3rd Battalion, 5th Marines + 2nd Battalion, 7th Cavalry sector advance from Phase Line Fran to Phase Line Jena during Operation Al-Fajr. Heavy IED emplacement, booby-trapped structures, AC-130 gunship support, M1A2 + AAV + LAV-25 combined arms, Iraqi National Guard blocking force.

**Dependencies**: Phase 100 complete.

**Historical outcome** (from Estes, *U.S. Marines in Iraq: Anthology and Annotated Bibliography*; Bing West, *No True Glory*; 1st MARDIV Lessons Learned):
- Winner: Coalition (Blue)
- Sector: 3/5 Marines + 2/7 Cav took their phase line objectives
- Duration: ~4 days for Phase Line Fran sector
- Coalition casualties: ~95 KIA and ~560 WIA across entire Al-Fajr operation; scaled to Phase Line Fran sector: ~15 KIA, ~90 WIA estimated
- Insurgent casualties: ~1200 KIA estimated across operation; sector: ~200–300
- Key dynamics: IEDs accounted for ~30% of Marine casualties; AC-130 employment at night; booby-trapped buildings; methodical house-clearance

### 101a: Research

`docs/scenarios/fallujah_phase_line_fran.md` with sector OOB, phase lines, IED density estimates, house-clearance tempo.

### 101b: Data Authoring

Expected gaps:

- **`data/units/infantry/us_marine_rifle_squad_urban.yaml`** (new variant) -- 13-man squad, M16A4, M249, M203, shotgun breacher
- **`data/units/armor/us_m1a2_tusk.yaml`** (confirm or new) -- TUSK-equipped M1A2 for urban
- **`data/units/armor/us_lav25.yaml`** (confirm existing)
- **`data/units/armor/us_aavp7.yaml`** (confirm or new)
- **`data/units/air/us_ac130u.yaml`** (new) -- AC-130U Spooky with 25mm, 40mm, 105mm
- **`data/units/infantry/iraqi_insurgent_urban.yaml`** (new variant) -- AK, RPG-7, SVD, IEDs
- **IED device definitions** -- tied to existing `unconventional_engine` with documented density/yield patterns
- **Booby-trap building templates** -- fire zone/obscurant interactions

### 101c: Scenario YAML

- Duration: 96 hours
- Urban terrain with block-by-block objectives
- `enable_unconventional_warfare: true`, `enable_fire_zones: true`, `enable_obscurants: true`
- IED density parameter in `calibration_overrides` — documented from USMC Lessons Learned
- Victory conditions: all phase lines reached, insurgent resistance degraded

### 101d: Calibration

- Expected issue: IED employment under moving units requires `enable_ied_trigger` from Phase 66 to actually resolve; verify events fire
- Expected issue: AC-130 sortie pattern — CAS queue must support night-only availability
- Forbidden: reducing IED density to "win faster"

### 101e: Regression Test

- `test_fallujah_coalition_wins` (Coalition ≥7/10)
- `test_fallujah_ied_casualties` (IED events ≥10 per run)
- `test_fallujah_ac130_employment` (AC-130 engagement events present)
- `test_fallujah_urban_terrain_effect` (engagement outcomes show urban modifier applied)

### 101f: UI Walkthrough

Depth checklist includes IED events filterable in Analysis tab, fire zone overlay visible on map (if implemented), urban terrain modifier shown in engagement detail modal.

---

## Phase 102: Bint Jbeil + INS Hanit Vignette + Block 11 Validation (Lebanon, July-August 2006)

**Status**: Pending.

**Goal**: Fourth golden scenario — the "hardest" one modeling-wise. ATGM-heavy defense against MBT (Kornet vs. Merkava Mk IV), limited EW, urban terrain, Israeli reserve mobilization morale effects. Paired with INS Hanit Harpoon/C-802 Noor missile strike as a naval vignette scenario — technically separate but loaded as the same Block 11 case study for naval missile engagement.

**Dependencies**: Phase 101 complete.

**Historical outcome — Bint Jbeil** (from Harel & Issacharoff *34 Days*; Matthews CSI *We Were Caught Unprepared*; Cordesman CSIS):
- Winner: Contested; operationally, IDF held ground but suffered heavy casualties and did not clear the town decisively within the battle period
- Duration: ~10 days intermittent combat
- IDF casualties: 8 KIA in single July 26 ambush; ~15 total for battle period
- Hezbollah casualties: disputed; IDF claimed ~30-40, independent estimates vary
- Key dynamics: Kornet and RPG-29 engagements penetrated Merkava armor in several cases; IDF reserve mobilization introduced training/readiness gaps

**Historical outcome — INS Hanit** (ONI reports, Karon *The Six-Day War and the Invention of Mass Media*):
- Date: July 14, 2006
- Missile: C-802 Noor (2 launched, 1 hit Hanit, 1 struck Cambodian freighter)
- Hanit survival: yes, but 4 KIA, ship returned to port under own power
- Key dynamic: ship's AEGIS equivalent defenses were reportedly off or misconfigured

### 102a: Research

`docs/scenarios/bint_jbeil.md` + `docs/scenarios/ins_hanit.md` with OOB, geography (Bint Jbeil town layout; Mediterranean engagement geometry), engagement sequence.

Political sensitivity: follow guardrails from brainstorm (tactical framing, source discipline, neutral language).

### 102b: Data Authoring

Expected gaps:

- **`data/units/armor/idf_merkava_mk4.yaml`** (new) -- Merkava Mk IV, 120mm smoothbore, Trophy APS (if modeled; else disabled)
- **`data/units/infantry/idf_golani_squad.yaml`** (new) -- Golani Brigade rifle squad
- **`data/units/infantry/hezbollah_fighter_squad.yaml`** (new) -- Hezbollah small unit with Kornet/RPG-29/AK
- **`data/weapons/at14_kornet.yaml`** (new) -- 9M133 Kornet-E ATGM
- **`data/weapons/rpg29_vampir.yaml`** (new) -- RPG-29 with tandem HEAT
- **`data/units/naval/idf_saar5.yaml`** (new) -- Sa'ar 5 corvette (INS Hanit)
- **`data/weapons/c802_noor.yaml`** (new) -- C-802 Noor anti-ship missile
- **`data/units/infantry/hezbollah_atgm_team.yaml`** (new)

### 102c: Scenario YAML

Bint Jbeil: urban terrain, Hezbollah pre-prepared ATGM ambush positions, IDF armored thrust. Limited EW engagement (modest).

INS Hanit vignette: naval surface engagement, Lebanese coast, single Harpoon-class inbound missile, defender's ECM/CIWS posture documentable.

Consider: one combined scenario file with both vignettes, or two separate scenarios? Decision point during Phase 102a research.

### 102d: Calibration

- Kornet Pk vs. Merkava frontal armor: documented from Russian export marketing + IDF AAR; do not tune to force specific outcome
- Hanit's defensive posture: documented as "off" — scenario should reflect that via ECM availability/ROE

### 102e: Regression Test

- `test_bint_jbeil_kornet_penetrations` (Kornet destroys ≥1 Merkava per 2 runs)
- `test_bint_jbeil_idf_casualties_envelope` (IDF casualties in historical range)
- `test_ins_hanit_c802_hit` (C-802 hits ship in ≥50% of runs given historical ECM state)
- `test_ins_hanit_damage_envelope` (ship damaged but survives)

### 102f: UI Walkthrough

Depth checklist includes naval engagement events, ATGM kill events distinguishable from direct fire, morale effects visible on IDF reserve units.

### 102g: Block 11 Validation

- Re-run all 40+ existing scenarios — confirm zero regressions
- Run full test suite including all four golden scenario tests
- Run `/cross-doc-audit` — all docs synchronized
- Update `MEMORY.md` and `CLAUDE.md` to mark Block 11 complete
- Close block: summary in `devlog/phase-102.md` with lessons learned across all four scenarios

---

## Module Index (New Files Expected)

| Module | Phase | Purpose |
|--------|-------|---------|
| `docs/brainstorm-block11.md` | Pre-98 | Design thinking |
| `docs/development-phases-block11.md` | Pre-98 | This document |
| `docs/scenarios/gap-audit.md` | 98 | Cross-scenario unit/weapon gap inventory |
| `docs/scenarios/calibration-template.md` | 98 | Envelope definition conventions |
| `docs/scenarios/depth-checklist-template.md` | 98 | UI walkthrough template |
| `stochastic_warfare/tools/envelope_check.py` | 98 | Regression test helpers |
| `docs/scenarios/debecka_pass.md` | 99 | Research brief |
| `data/scenarios/debecka_pass/scenario.yaml` | 99 | Scenario definition |
| `tests/validation/test_debecka_pass.py` | 99 | Regression test |
| `docs/scenarios/khafji.md` | 100 | Research brief |
| `data/scenarios/khafji/scenario.yaml` | 100 | Scenario definition |
| `tests/validation/test_khafji.py` | 100 | Regression test |
| `docs/scenarios/fallujah_phase_line_fran.md` | 101 | Research brief |
| `data/scenarios/fallujah_phase_line_fran/scenario.yaml` | 101 | Scenario definition |
| `tests/validation/test_fallujah_phase_line_fran.py` | 101 | Regression test |
| `docs/scenarios/bint_jbeil.md` | 102 | Research brief |
| `docs/scenarios/ins_hanit.md` | 102 | Research brief (vignette) |
| `data/scenarios/bint_jbeil_2006/scenario.yaml` | 102 | Scenario definition |
| `data/scenarios/ins_hanit_2006/scenario.yaml` | 102 | Naval vignette |
| `tests/validation/test_bint_jbeil.py` | 102 | Regression test |
| `tests/validation/test_ins_hanit.py` | 102 | Regression test |
| (Many unit/weapon YAMLs) | 99–102 | Per gap audit |

---

## Summary Table

| Phase | Focus | Tests (est.) | Primary Engines Exercised |
|-------|-------|--------------|---------------------------|
| 98 | Shared prework | ~8 | (N/A — scaffolding) |
| 99 | Debecka Pass (2003) | ~8 | ATGM, CAS, air defense, C2, morale |
| 100 | Khafji (1991) | ~8 | Naval gunfire, multi-domain, morale cascade |
| 101 | Fallujah PL Fran (2004) | ~10 | Urban, IED/UW, AC-130, fire zones |
| 102 | Bint Jbeil + Hanit (2006) | ~12 | ATGM vs. MBT, naval missile, urban, limited EW |

**Block 11 expected total**: ~46 new tests, 4 new scenarios, ~15–25 new unit/weapon YAMLs, 6 new docs.
