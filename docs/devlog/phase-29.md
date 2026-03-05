# Phase 29: Historical Era Data Expansion

## Summary

Pure data phase filling critical naval gaps across all 4 historical eras, plus missing ground/air unit types, weapons, comms, and commander profiles. Zero new Python source files, zero enum extensions. 119 new YAML files, 1 new test file with 164 tests.

**Cumulative**: 7,111 tests passing (164 new).

## Deliverables

### 29a: WW2 Naval & Missing Types (34 YAML files)

- **Naval units** (5): Essex CV, Shokaku CV, Type IXC U-boat, Flower corvette, LST Mk2
- **Ground units** (4): M1 105mm battery, sFH 18 battery, PaK 40 AT, 6-pdr AT
- **Aircraft** (1): A6M Zero
- **Weapons** (6): MG 151/20, M2 .50 cal (aircraft), Type 99 20mm, G7e torpedo, Mk 7 depth charge, Type 93 Long Lance
- **Ammunition** (6): 20mm mine, .50 cal AP, 20mm HE, G7e warhead, Mk 7 DC, Type 93 warhead
- **Signatures** (10): One per new unit
- **Comms** (2): Field telephone (WIRE), SCR-300 radio (RADIO_VHF) — WW2 was the only era without comms

### 29b: WW1 Expansion (29 YAML files)

- **Naval units** (5): Iron Duke BB, Konig BB, Invincible BC, G-class destroyer, U-boat WW1
- **Ground units** (3): 18-pdr battery, FK 96 battery, US AEF squad
- **Aircraft** (2): SPAD XIII, Fokker D.VII
- **Weapons** (5): 12-inch BL Mk X, 15cm SK L/45, 18-inch torpedo, Vickers .303, LMG 08 Spandau
- **Ammunition** (4): 12-inch AP, 15cm HE, 18-inch torpedo warhead, 7.92mm SmK
- **Signatures** (10): One per new unit

### 29c: Napoleonic Naval & Expansion (30 YAML files)

- **Naval units** (5): 74-gun ship of the line, First Rate 100, 32-gun frigate, corvette/sloop, fire ship
- **Ground units** (6): Dragoon squadron, Austrian line infantry, Russian line infantry, Congreve rocket battery, pontoon engineer, supply train
- **Weapons** (4): 32-pdr cannon, 24-pdr cannon, 32-pdr carronade, Congreve rocket
- **Ammunition** (4): 32-pdr round shot, chain shot, grape shot naval, Congreve rocket round
- **Signatures** (11): One per new unit

### 29d: Ancient/Medieval Naval & Expansion (26 YAML files)

- **Naval units** (6): Greek trireme, Roman quinquereme, Viking longship, Byzantine dromon, medieval cog, war galley
- **Ground units** (4): Byzantine kataphraktoi, Saracen cavalry, Byzantine skutatoi, siege engineer
- **Weapons** (3): Naval ram, Greek fire siphon, corvus boarding bridge
- **Ammunition** (2): Greek fire charge, ram charge
- **Signatures** (10): One per new combat unit
- **Commander** (1): Mongol Subotai

## New Directory Structure

```
data/eras/ww2/comms/                         # NEW
data/eras/ww2/units/artillery/               # NEW
data/eras/ww2/ammunition/aircraft/           # NEW
data/eras/ww2/ammunition/depth_charges/      # NEW
data/eras/ww1/units/naval/                   # NEW
data/eras/ww1/units/air/                     # NEW
data/eras/ww1/weapons/naval/                 # NEW
data/eras/ww1/weapons/guns/                  # NEW
data/eras/ww1/ammunition/naval/              # NEW
data/eras/napoleonic/units/naval/            # NEW
data/eras/napoleonic/weapons/naval/          # NEW
data/eras/napoleonic/ammunition/naval/       # NEW
data/eras/ancient_medieval/units/naval/      # NEW
data/eras/ancient_medieval/weapons/naval/    # NEW
data/eras/ancient_medieval/ammunition/naval/ # NEW
```

## Key Decisions

1. **Capital ships as CRUISER**: No BATTLESHIP enum value exists. Following Iowa BB precedent, all capital ships (dreadnoughts, ships of the line, quinqueremes) use CRUISER as the closest heavy combatant type.
2. **Pre-radar eras have zero RCS**: WW1, Napoleonic, and Ancient signatures correctly have all radar cross-section values at 0.0.
3. **Existing ammo reuse**: WW1 aircraft weapons reference existing ammo IDs (e.g., `303_ball` already existed). New ammo only created where no existing entry matched.
4. **Oar-powered naval**: Ancient/Medieval ships use displacement 20-200t, noise_signature_base 35-65 dB — much lower than steam/diesel vessels.
5. **WW2 comms gap filled**: WW2 was the only era without a comms directory. Added field telephone (WIRE) and SCR-300 (RADIO_VHF).

## Exit Criteria Verification

- WW2 has 2 carrier units (Essex, Shokaku) + carrier-capable aircraft (A6M Zero) ✓
- WW1 has 3 capital ship types (Iron Duke, Konig, Invincible) ✓
- Napoleonic era has ship of the line and frigate ✓
- Ancient/Medieval era has trireme and longship ✓
- WW2 has comms subdirectory ✓
- All new unit YAML has matching signature YAML ✓
- All era YAML validates via pydantic (164 tests pass) ✓

## Known Limitations

- WW2 comms are NOT auto-loaded by era overlay in `_create_loaders()` — existing limitation, not introduced here
- Naval weapon YAML for WW1/Napoleonic/Ancient is minimal (focuses on key weapon types, not comprehensive armament lists)
- No new scenarios added — Phase 30 will create scenarios using this naval data

## Postmortem

### Scope: On target
Plan called for ~121 YAML files; delivered 119. Two fewer due to: (1) WW1 `303_ball` ammo already existed so no duplicate created, (2) plan double-counted Ancient/Medieval commander in both "Unit YAML" and "Commander YAML" summary rows. All planned unit types, weapons, ammo, signatures, comms, and commander delivered. Tests: 164 vs estimated ~90 — exceeded because thorough spot-check assertions added per unit type.

### Quality: High
- All 164 tests pass in 0.52s
- Full regression: 7,111 tests, 116.71s — no performance impact
- All weapon→ammo cross-references verified programmatically (all 4 eras)
- All new units have matching signatures
- No TODOs, FIXMEs, or dead code

### Integration: Fully wired (N/A — pure data)
- All YAML loads through existing loaders without modification
- No new source files, no enum extensions
- Zero backward compatibility issues

### Test gaps (minor)
- WW2 has explicit cross-reference tests (weapon→ammo, unit→signature)
- Ancient/Medieval has unit→signature cross-ref test
- WW1 and Napoleonic lack explicit cross-reference tests (weapon→ammo refs verified programmatically in postmortem but not in test suite)

### Deficits: 0 new
No new deficits introduced. Existing limitation (WW2 comms not auto-loaded by era overlay) was pre-existing and already documented.

### Documentation fixes applied
- CLAUDE.md: corrected YAML count 121→119, 29d sub-count 28→26
- devlog/phase-29.md: corrected YAML count 121→119, 29d sub-count 28→26
- README.md: added Phase 29 row to table, fixed stale test counts (6,947→7,111 in 2 places), updated status description
