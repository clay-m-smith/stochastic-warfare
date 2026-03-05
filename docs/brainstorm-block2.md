# Stochastic Warfare — Block 2 Brainstorm

## Context

Phases 0–24 (Block 1) built the complete engine: 12 core modules, 4 historical eras, 5 new domain subsystems (EW, Space, CBRN, Doctrinal Schools, Escalation/Unconventional), tooling, real-world terrain, and performance optimization. 6,325 tests. All planned phases complete.

Block 2 addresses three priorities:
1. **Core completeness** — fix wiring gaps, PRNG discipline violations, hardcoded constants, and broken integration paths that prevent the engine from running as a fully connected system
2. **Combat interaction completeness** — fill missing cross-domain engagement paths, burst fire, submunition scatter, and other thin combat mechanics
3. **Data population** — expand YAML data packages for all eras to enable rich scenario authoring without writing new code

## Why Block 2

Block 1 built engines that are individually well-tested but structurally disconnected. The ScenarioLoader cannot auto-wire 10+ post-MVP engine types. The OODA DECIDE path in battle.py is broken (assessment=None). Commander personalities exist but aren't on SimulationContext. EW engines aren't in the tick loop. Era engines require manual caller-side wiring. These are not feature gaps — they're integration gaps that prevent the engine from functioning as a complete system.

Similarly, combat has excellent depth in individual domains (ground direct fire, naval salvo, air combat) but thin-to-missing cross-domain paths (ground-to-naval, air-launched ASuW, ATGM vs helicopter). The engagement engine doesn't model burst fire. DPICM submunitions don't scatter. EW doesn't affect air combat.

The data situation mirrors this: modern units cover key platforms but lack adversary air forces (no MiG-29, Su-27, J-20), complete signatures, and organization files. Historical eras lack naval forces entirely (no Jutland dreadnoughts, Trafalgar ships of the line, Salamis triremes). Two modern organization TO&E files exist out of dozens needed.

Block 2 turns individually excellent subsystems into a connected, data-rich, runnable whole.

---

## Priority 1: Core Engine Completeness

### 1.1 ScenarioLoader Auto-Wiring

**The problem**: Every post-MVP engine (Phases 16–24) exists as a standalone, well-tested module. None of them are instantiated by ScenarioLoader when loading a scenario YAML. Running a scenario from YAML alone gives no access to EW, Space, CBRN, doctrinal schools, era engines, or escalation systems.

**The solution**: Extend `CampaignScenarioConfig` to parse configuration blocks for each subsystem. Extend `ScenarioLoader.load()` to instantiate and wire engines onto SimulationContext when config blocks are present. Null/absent blocks → engine not instantiated (existing backward-compatible pattern).

**Subsystems to wire** (in order of structural priority):
1. EWEngine, ECCMEngine, SIGINTEngine (Phase 16) — `ew_config` block
2. SpaceEngine, GPSDependencyEngine, SATCOMEngine (Phase 17) — `space_config` block
3. CBRNEngine, DisperseEngine, ContaminationEngine (Phase 18) — `cbrn_config` block
4. SchoolRegistry + CommanderEngine (Phase 19) — `schools` / `commander_config` blocks
5. Era engines (Phases 20–23) — gated by `era` field in scenario config
6. Escalation engines (Phase 24) — `escalation_config` block (partially wired already)
7. IncendiaryDamageEngine, UXOEngine, UnconventionalWarfareEngine, SOFOpsEngine, InsurgencyEngine (Phase 24) — gated by `escalation_config`

### 1.2 Battle Loop OODA Fix

**The problem**: `battle.py` `_process_ooda_completions()` passes `assessment=None` to `decide()`. This means:
- Phase 8 COA wargaming never receives situation data
- Phase 19 doctrinal school weight overrides are never applied
- Phase 19 stratagem affinity hooks are never called
- If `decide()` tries to access `assessment.force_ratio`, it crashes

**The solution**: Build a real `AssessmentResult` from current battle state (friendly/enemy positions, force ratios, threat axes, supply state) and pass it to `decide()`. Wire `get_coa_score_weight_overrides()` and `get_stratagem_affinity()` into the COA scoring path.

### 1.3 CommanderEngine on SimulationContext

**The problem**: CommanderEngine exists, commander YAML profiles are loaded, but the engine is not a field on SimulationContext. The battle loop passes `personality=None` everywhere.

**The solution**: Add `commander_engine` field to SimulationContext. ScenarioLoader assigns personalities from scenario YAML. Battle loop queries `commander_engine.get_personality(unit_id)` instead of passing None.

### 1.4 Tick Loop Engine Integration

**The problem**: Several engines define update/step methods but are never called from the main tick loop.

**Engines to integrate**:
- EW engines (jamming state, ECCM processing, SIGINT collection)
- MOPP speed factor (query CBRN contamination state → pass to movement engine)
- Air campaign → ATO planning cycle
- Insurgency engine with real collateral/aid data from ongoing simulation

### 1.5 Error Handling

**The problem**: `simulation/engine.py` has a bare `except Exception: pass` that silently swallows environment engine errors. Failures are invisible.

**The solution**: Replace with specific exception handling. Log errors with `logger.error()`. Optionally raise in strict mode, continue with warning in lenient mode (configurable).

---

## Priority 2: Combat Interaction Completeness

### 2.1 Cross-Domain Engagement Paths

**Missing paths** (identified from domain interaction matrix):

| Path | What's Missing | Solution |
|------|---------------|----------|
| Ground → Naval (coastal defense) | No coastal ASHM flight path | Route coastal defense missiles through existing `missiles.py` with naval target resolution |
| Air → Naval (ASuW) | Air-launched ASHMs use naval salvo model but no flight profile | Wire `air_ground.py` to launch ASHMs via `missiles.py` with terminal resolution in `naval_surface.py` |
| ATGM → Helicopter | Wire-guided ATGMs can't engage hovering helicopters | Extend `air_defense.py` or `engagement.py` to accept ATGM engagements against low-altitude rotary targets |
| EW → Air combat | `air_combat.py` has string-based CM, not wired to EW J/S model | Integrate EW engine output (jamming effectiveness) into air combat CM evaluation |

### 2.2 Engagement Engine Enhancements

| Enhancement | Current State | Target |
|------------|--------------|--------|
| Burst fire | `burst_size` defined on WeaponDefinition but never read | Fire N rounds per engagement, accumulate hit probability |
| DPICM scatter | Falls through to generic blast/frag | Spatial scatter of submunitions with individual lethal radii, auto-create UXO field |
| Multi-spectral CM | Single countermeasure type per engagement | Allow chaff + flare + DIRCM simultaneously, each reducing Pk against appropriate seekers |
| TOT synchronization | Multiple batteries fire independently | Coordinate time-on-target across batteries for simultaneous impact |
| CAS designation | Target position passed directly | JTAC designation lag, laser spot timing, talk-on sequence, C2 clearance latency |

### 2.3 Naval Combat Completion

- Modern naval gun engagement path (Mk45 vs surface target — fire control model, not WW2 bracket)
- ASW weapon path (ASROC, lightweight torpedo deployment from surface ships)
- Torpedo countermeasures (NIXIE towed decoy, acoustic CM)
- Carrier air operations detail (sortie generation rate, deck cycle, CAP station)

### 2.4 Fidelity Items (Selective)

From the deficit inventory, these combat fidelity items are worth addressing:
- Barrage drift with observer correction (not just random walk)
- Cavalry charge terrain effects (slope, soft ground)
- Melee frontage/depth constraints (narrow pass limitation)
- Gas mask don time delay

Lower priority (adequate at campaign scale, won't fix):
- Fire zone cellular automaton (center+radius is adequate)
- Biological incubation periods
- RDD distributed source model
- Strategic bombing industrial interdependency

---

## Priority 3: Data Population

### 3.1 Modern Era Gaps

**Units needed**:
- Adversary air: MiG-29, Su-27/Su-30, J-20 (minimum viable OPFOR air)
- Adversary ground: BTR-80, BMP-2 (complement existing T-72M)
- Adversary naval: Sovremenny DDG, Kilo SSK
- Adversary air defense: SA-6/SA-11/S-300 (tiered IADS)
- Allied/NATO: Leopard 2, Challenger 2, Warrior IFV, Leclerc
- Strategic bomber: B-52H, Tu-95MS
- Transport: C-17, IL-76
- Attack helicopter: Mi-24V (complement AH-64D)
- Artillery: MLRS/HIMARS unit definition (weapon exists, no unit)
- ATGM team, engineer unit, EW aircraft (EA-18G)

**Signatures**: Fill gaps — bmp1, m3a2_bradley, sea_harrier, type22_frigate, t55a, t62 + all new units

**Ammunition**: 30mm M789 HEDP, Mk-82/Mk-84 unguided bombs, mortar-specific rounds, ASROC, lightweight torpedo, depth charge

**Sensors**: SAR, fire control radar (separate from search), maritime patrol radar, UV missile approach warning, ground acoustic array

**Organizations**: Full TO&E files for US battalion task force, Russian BTG, Chinese combined arms brigade, UK battlegroup, plus generic templates

**Doctrine**: PLA doctrine, IDF doctrine, airborne/air assault, amphibious, naval warfare operational templates

**Escalation**: Additional threshold presets (peer-competitor, conventional-only, NATO Article 5)

### 3.2 Historical Era Gaps

**Naval for all pre-modern eras** (historically decisive — currently zero naval units):

| Era | Ships Needed | Battles to Enable |
|-----|-------------|------------------|
| WW2 | CV (Essex/Shokaku), CVE, DE (escort), LST landing craft | Midway (proper), Leyte Gulf, D-Day |
| WW1 | Dreadnought (Iron Duke, König), battlecruiser (Invincible), destroyer, submarine (U-boat) | Jutland, U-boat campaign |
| Napoleonic | Ship of the line (74-gun), frigate, corvette, fire ship | Trafalgar, Nile |
| Ancient/Medieval | Trireme, quinquereme, dromon, longship, cog, galley | Salamis, Actium, Lepanto |

**Other gaps per era**:
- WW2: Artillery unit (M1 105mm, sFH 18), AT gun, carrier air wing, comms subdirectory, Japanese land units
- WW1: Artillery battery unit, AEF units, air units (SPAD, Fokker), naval is the big gap
- Napoleonic: Dragoon cavalry, Austrian/Russian/Prussian infantry, rocket artillery (Congreve), engineer/pontoon, supply train
- Ancient/Medieval: Byzantine units, Islamic/Saracen units, dedicated siege engineer unit, Mongol commander

### 3.3 Scenario Library

**Modern scenarios needed**:
- Taiwan Strait contingency (joint, naval-air focus, escalation dynamics)
- Korean Peninsula (combined arms, mountainous terrain, massed artillery)
- Baltic/Suwalki Gap (NATO vs Russia, mixed terrain, EW heavy)
- Hybrid warfare (Gerasimov-style gray zone, information + conventional)
- Arctic scenario (extreme environment, logistics focus)

**Historical scenario expansion**:
- Jutland 1916 (WW1 naval — requires WW1 naval units)
- Trafalgar 1805 (Napoleonic naval — requires Napoleonic naval units)
- Salamis 480 BC (Ancient naval — requires triremes)
- Stalingrad 1942 (WW2 urban, logistics crisis)
- Gettysburg analogue (US Civil War concepts applicable to Napoleonic framework)

---

## Phase Structure

Six phases, grouped by the three priorities:

| Phase | Focus | Priority |
|-------|-------|----------|
| 25 | Engine Wiring & Integration | Core completeness |
| 26 | Core Polish & Configuration | Core completeness |
| 27 | Combat System Completeness | Combat interactions |
| 28 | Modern Era Data Package | Data population |
| 29 | Historical Era Data Expansion | Data population |
| 30 | Scenario & Campaign Library | Data population + validation |

**Implementation order**: 25 → 26 → 27 → 28 → 29 → 30. Sequential — each phase builds on the previous. Phase 25 (wiring) unlocks everything else. Phase 27 (combat) should precede data expansion so new engagement paths exist before we write YAML for them. Phases 28–30 are data-heavy and can potentially be parallelized with each other.

---

## What Does NOT Change

- No new Python dependencies
- No architectural rewrites — all work extends existing patterns
- No new module types — wiring and data for existing modules
- Simulation loop stays single-threaded (deterministic replay)
- All additions backward-compatible (null/absent config → engine not instantiated)
- Existing tests unaffected unless they have hardcoded enum counts (update as needed)

---

## Success Criteria for Block 2

1. **A scenario YAML alone can instantiate a fully-wired simulation** — no manual caller-side engine construction required for any subsystem
2. **Zero PRNG discipline violations** — no fallback RNG seeds anywhere in the codebase
3. **Every combat domain pair has an engagement path** — ground↔naval, air↔naval, ATGM↔helicopter, EW↔air combat all wired
4. **Modern OPFOR air capability exists** — at least 3 adversary fighter/attack aircraft
5. **Every historical era has naval units** — even if minimal (2–3 ship types per era)
6. **At least 3 new modern scenarios** covering different domains (joint, naval-air, hybrid)
7. **Full test regression passes** — all existing 6,325+ tests plus new tests for each phase
