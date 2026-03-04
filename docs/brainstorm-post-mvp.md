# Stochastic Warfare — Post-MVP Brainstorm

Thematic exploration of post-MVP development directions. All 10 MVP phases (0–10) are complete with 3,782 tests passing. This document captures design thinking, rationale, and research directions for Phases 11–24 across 13 thematic areas. Implementation roadmap is in `development-phases-post-mvp.md`.

**Cross-document alignment**: This document should stay synchronized with `development-phases-post-mvp.md` (phase assignments), `brainstorm.md` (original architecture decisions), and `devlog/index.md` (deficit inventory).

---

## 1. Deficit Remediation Philosophy

### Principle: Fix What Matters for Realism, Not Completeness

The MVP logged 73 deficit items across Phases 0–10 (see `devlog/index.md`). Not all are equal. Remediation should be prioritized by **impact on simulation fidelity** — does fixing this change outcomes in validated scenarios? — not by engineering elegance.

### Categorized Inventory

**MAJOR — Changes Outcomes** (fix in Phases 11–12):

| Deficit | Origin | Impact |
|---------|--------|--------|
| No fire rate limiting | Phase 7 | Units fire once per tick regardless of ROF. Inflates DPS at tactical resolution. |
| No wave attack modeling | Phase 7 | All units advance simultaneously. Prevents echeloned assault tactics. |
| Campaign AI coarseness | Phase 10 | OODA timing at echelon scales may not produce posture changes in short runs. |
| No fuel gating on movement | Phase 6 | Units move indefinitely without fuel. Eliminates culmination point. |
| Environment→combat coupling partial | Phase 4 | air_combat, air_defense, naval_surface, indirect_fire lack env coupling. Weather has no effect on half the combat domains. |

**MODERATE — Improves Fidelity** (fix in Phases 11–12):

| Deficit | Origin | Impact |
|---------|--------|--------|
| Ballistic drag simplified (no Mach-dependent Cd) | Phase 4 | Affects long-range engagements where projectile decelerates through transonic. |
| DeMarre penetration (no obliquity/composite/reactive) | Phase 4 | Overpredicts penetration on angled/modern armor. |
| Single-scan detection (no dwell/integration) | Phase 3 | Radar/sonar don't benefit from extended observation. |
| No sensor FOV filtering | Phase 3 | Sensors detect in 360° regardless of heading. |
| Passive sonar bearing is placeholder | Phase 3 | Random bearing, not geometric. Sonar tracking unrealistic. |
| No multi-hop C2 propagation | Phase 5 | Messages teleport from issuer to recipient. No relay chain. |
| No terrain-based comms LOS | Phase 5 | Radio works through mountains. |
| No multi-echelon supply chain | Phase 6 | Direct depot-to-unit. No intermediate supply points. |
| No supply optimization | Phase 6 | Nearest-depot pull only. No intelligent allocation. |
| Simplified transport vulnerability | Phase 6 | No escort effects on convoy survival. |
| Air combat lacks energy-maneuverability | Phase 4 | No detailed flight dynamics. Air combat is probability-only. |
| Naval damage control abstracted | Phase 4 | No compartment flooding model. |

**MINOR — Cosmetic or Edge-Case** (fix opportunistically):

| Deficit | Origin | Impact |
|---------|--------|--------|
| Checkpoint pickle fragility | Phase 0 | Format may break across Python versions. |
| Track association needs nearest-neighbor gating | Phase 3 | Currently assigns by ID, not geometry. |
| HEAT penetration range-independent | Phase 4 | Shaped charge physics are range-independent; this is actually correct. Keep as-is. |
| Morale Markov discrete-time | Phase 4 | Continuous-time adds complexity with marginal gain at current tick rates. |
| Carrier ops deck management abstracted | Phase 4 | Individual spot tracking is future scope. |
| Brigade decision hardcodes echelon_level=9 | Phase 8 | Cosmetic — no behavioral impact. |
| Simplified FSCL geometry | Phase 5 | East-west line vs arbitrary polyline. Adequate for most scenarios. |
| Various logistics edge cases | Phase 6 | Captured supply, local water, ammo production, VLS reloading. |

### Remediation Strategy

1. **Phase 11 (Core Fidelity Fixes)**: All MAJOR items + highest-impact MODERATE items. These are surgical fixes to existing modules — no new architecture.
2. **Phase 12 (Deep Systems Rework)**: Remaining MODERATE items that require deeper refactoring (multi-hop C2, multi-echelon logistics, energy-maneuverability air combat).
3. **MINOR items**: Fix in-line when touching the affected module for other reasons. No dedicated phase.

---

## 2. Performance Optimization Strategy

### Current State

Phase 10 profiling established baselines. Key observations:
- Single-threaded simulation loop (required for deterministic PRNG replay)
- Per-tick LOS cache implemented (Phase 9) but cleared each tick
- Vectorized LOS raycasting and nearest-enemy already done (Phase 7 optimizations)
- STRtree for infrastructure spatial queries still deferred
- Viewshed vectorization deferred
- Kalman F/Q matrix caching for fixed dt deferred

### Optimization Tiers

**Tier 1: Algorithmic (Phase 13a)** — Pure Python, no new dependencies:
- **STRtree spatial indexing**: Replace brute-force infrastructure queries in terrain/los.py with Shapely STRtree. Already a dependency. Expected: 10-50x speedup for LOS with buildings.
- **Kalman F/Q caching**: State transition and process noise matrices are constant for fixed dt. Cache and reuse. Expected: 2-3x speedup for estimation.py.
- **Viewshed vectorization**: Batch multiple observer LOS checks using numpy. Currently one ray at a time.
- **Force aggregation/disaggregation**: Allow corps/division-level entities to be simulated as aggregates at strategic resolution, expanding to individual units only in tactical battles. Reduces entity count 10-100x for campaign scale.
- **Auto-resolve for distant battles**: Lanchester-based quick resolution for engagements far from player focus, without running full tactical loop.
- **Multi-tick LOS cache**: Only invalidate LOS entries for cells where units moved, not entire cache.

**Tier 2: Compiled Extensions (Phase 13b)** — New dependencies (Numba):
- **Numba JIT for inner loops**: Ballistic trajectory integration (RK4), DDA raycasting, pathfinding cell cost. These are tight numerical loops ideal for JIT.
- **Numba for Monte Carlo**: Each MC iteration's inner simulation loop is JIT-compilable.
- Decision: Numba over Cython — no compilation step, no .pyx files, better numpy integration. Numba `@njit` decorates existing functions without rewrite.
- Constraint: Must maintain pure-Python fallback for platforms without LLVM. Use `try: from numba import njit except: njit = lambda f: f` pattern.

**Tier 3: Parallelism (Phase 13c)** — Architecture changes:
- **ProcessPoolExecutor for Monte Carlo**: Already implemented (Phase 7). Extend to campaign MC.
- **Thread-pool for independent side computations**: Detection, morale, logistics for each side are independent within a tick. Could parallelize.
- Constraint: PRNG determinism requires careful stream partitioning. Each thread gets its own `Generator` from `RNGManager`.
- Decision: NOT pursuing GPU/CUDA — simulation logic is too branchy for SIMD. Numba + multiprocessing is the right level.

### Performance Targets

| Metric | MVP Baseline | Phase 13 Target |
|--------|-------------|-----------------|
| Tactical tick (50 units) | ~10ms | ~2ms |
| Campaign tick (200 units) | ~50ms | ~10ms |
| 73 Easting full run | ~2s | ~0.5s |
| Golan Heights campaign | ~15s | ~3s |
| MC 100-iteration (4 cores) | ~120s | ~25s |

---

## 3. Real-World Terrain & Data Pipeline

### Motivation

All MVP validation uses synthetic terrain (programmatic heightmaps). Real-world terrain is essential for:
- Historical scenario fidelity (actual 73 Easting battlefield topography)
- User-created scenarios on real geography
- Validation against known terrain effects on historical battles

### Data Sources

| Source | Data | Resolution | Format | License |
|--------|------|-----------|--------|---------|
| SRTM (NASA) | Elevation | 30m (global), 1-arcsec | GeoTIFF/HGT | Public domain |
| ASTER GDEM | Elevation | 30m (global) | GeoTIFF | Free for research |
| OpenStreetMap | Roads, buildings, rivers, land use | Vector | PBF/XML | ODbL |
| Natural Earth | Coastlines, borders, admin areas | 1:10m–1:110m | Shapefile | Public domain |
| GEBCO | Bathymetry | 15-arcsec (~450m) | NetCDF | Free |
| Copernicus Land | Land cover classification | 100m | GeoTIFF | Free |

### Pipeline Architecture

```
GeoTIFF/HGT → rasterio → numpy array → terrain/heightmap.py
OSM PBF → osmium → shapely geometries → terrain/infrastructure.py
GEBCO NetCDF → xarray → numpy array → terrain/bathymetry.py
Copernicus → rasterio → classification enum → terrain/classification.py
```

### New Dependencies

- `rasterio` — GeoTIFF/HGT reading (GDAL wrapper, but pip-installable)
- `osmium` (or `osmnx`) — OpenStreetMap data extraction
- `xarray` — NetCDF reading for bathymetry

### Design Decisions

1. **Tile-based loading**: Don't load entire world. Load tiles covering scenario bounding box + buffer.
2. **Resolution matching**: Resample source data to match simulation grid resolution. Bilinear for elevation, nearest-neighbor for classification.
3. **Cache processed tiles**: Store processed numpy arrays as `.npz` to avoid re-parsing raw data on every scenario load.
4. **Offline-first**: All data must be pre-downloaded. No network calls during simulation. Provide download scripts.
5. **Fallback to synthetic**: If no real data available for a region, fall back to procedural generation with warning.
6. **Infrastructure as logistical assets**: The original brainstorm notes that infrastructure networks "function as terrain features AND logistical assets." When real-world road/rail data is loaded, the supply network should incorporate actual infrastructure quality — paved roads increase transport speed, rail lines provide high-capacity routes, bridge destruction cuts routes. This bridges terrain (Phase 15) and logistics (Phase 12b).

### Modules

- `terrain/data_pipeline.py` — coordinate-based tile fetcher, format converters, cache management
- `terrain/real_heightmap.py` — SRTM/ASTER → heightmap grid with projection handling
- `terrain/real_classification.py` — Copernicus/OSM → classification grid
- `terrain/real_infrastructure.py` — OSM → road/building/bridge Shapely geometries
- `terrain/real_bathymetry.py` — GEBCO → bathymetry grid

---

## 4. Electronic Warfare Domain

### Scope

EW is the deliberate use of the electromagnetic spectrum to attack, protect, or exploit. Three pillars:
- **Electronic Attack (EA)**: Jamming, spoofing, directed energy
- **Electronic Protection (EP)**: ECCM, frequency hopping, LPI radar
- **Electronic Support (ES)**: SIGINT, ELINT, COMINT, direction-finding

### Existing Interface Points

The MVP already has hooks for EW:
- `detection/detection.py` — `jam_factor` parameter in SNR calculation
- `c2/communications.py` — `jamming_active` / `jam_resistance` on CommEquipmentDefinition
- `environment/electromagnetic.py` — RF propagation model
- `c2/naval_c2.py` — EMCON states (OPEN/MINIMIZE/SILENT)
- `detection/sensors.py` — ESM sensor type already defined

### New Modules

- `ew/spectrum.py` — Electromagnetic spectrum manager: frequency bands, allocation, conflict detection
- `ew/emitters.py` — Emitter registry: track all active emitters (radars, radios, jammers) with frequency/power/location
- `ew/jamming.py` — Jamming models: noise, barrage, spot, sweep, deceptive. J/S ratio calculation. Effect on sensor SNR and comms reliability.
- `ew/eccm.py` — Electronic counter-countermeasures: frequency hopping, spread spectrum, sidelobe blanking, adaptive nulling
- `ew/sigint.py` — Signal intelligence: intercept probability, geolocation (TDOA, AOA), traffic analysis
- `ew/decoys_ew.py` — Electronic decoys: chaff, flares (expanded from detection/deception.py), towed decoys, DRFM
- `ew/cyber.py` — Cyber-electromagnetic activities: network intrusion probability, data corruption, deferred to future scope

### Key Physics

- **Jammer-to-Signal (J/S) ratio**: `J/S = P_j·G_j·R_t⁴ / (P_t·G_t·R_j²·B_t/B_j)` — determines whether jammer overwhelms receiver
- **Burn-through range**: Range at which target signal exceeds jammer: `R_bt = R_j · √(P_t·G_t·B_j / (P_j·G_j·B_t))`
- **Intercept probability**: `P_int = f(dwell_time, bandwidth_overlap, receiver_sensitivity)`
- **Direction-finding accuracy**: Cramér-Rao bound on bearing estimate from antenna array geometry

### Design Principle

EW should modulate existing systems, not replace them. Jamming reduces detection `Pd`, comms `P(success)`, and missile guidance accuracy — all through existing parameters. No parallel combat resolution for EW.

### Validation Scenarios

- **Bekaa Valley 1982**: Israeli SEAD against Syrian SAM network. Textbook EW operation — drones provoke radar emissions, SIGINT geolocates SAMs, ARMs suppress radars, strike aircraft exploit gaps. Validates the full EA/EP/ES chain.
- **Gulf War 1991 (EW aspect)**: Coalition EW campaign against Iraqi IADS. GPS jamming, radar jamming, HARM strikes. Validates large-scale SEAD.

---

## 5. Civilian Population & COIN Effects

### Motivation

The original `brainstorm.md` explicitly scopes civilian population: *"density and disposition (friendly/neutral/hostile) — affects ROE, logistics, intelligence, morale."* The terrain module already has `population.py` with population density grids, and the ROE system (Phase 5) and morale system (Phase 4) both have hooks that go unused without deeper civilian modeling. Modern-era fidelity — particularly for COIN, urban operations, and politically constrained warfare — requires civilian interaction.

### Existing Interface Points

- `terrain/population.py` — Population density grid (people per cell)
- `c2/roe.py` — ROE enforcement (WEAPONS_HOLD/TIGHT/FREE) already exists
- `morale/stress.py` — Stress modifiers (civilian casualties as a stressor)
- `morale/psychology.py` — PSYOP model (civilian target audience)
- `logistics/supply_network.py` — Supply routes through populated areas
- `detection/intel_fusion.py` — HUMINT source type already defined

### New Modules

- `population/civilians.py` — Civilian entity manager: density by cell, disposition (friendly/neutral/hostile/mixed), displacement tracking. Civilians are not combat entities — they are a terrain-like overlay affecting other systems.
- `population/displacement.py` — Refugee movement: combat drives displacement along road networks, refugees block LOCs and slow military movement, refugee camps as logistics burden.
- `population/collateral.py` — Collateral damage tracking: civilian casualties from indirect fire, air strikes, CBRN. Feeds into ROE escalation and strategic-level political constraints.
- `population/humint.py` — Civilian intelligence: friendly population provides HUMINT tips (detection events), hostile population provides early warning to enemy. Disposition modulates intel flow.
- `population/influence.py` — Population disposition dynamics: military actions (collateral damage, aid, PSYOP, presence patrols) shift disposition over time. Markov chain with transition rates driven by events.

### Key Mechanics

- **ROE escalation**: Collateral damage triggers ROE tightening (WEAPONS_FREE → WEAPONS_TIGHT → WEAPONS_HOLD). Political pressure modeled as a threshold.
- **HUMINT generation**: Friendly population in an area generates detection events for enemy units (with noise/delay). Hostile population warns enemy of friendly movement.
- **LOC blockage**: Refugee columns on roads reduce supply throughput and military movement speed.
- **Morale impact**: Own-side civilian casualties increase stress; protecting civilians provides morale benefit.
- **Disposition drift**: A Markov model where disposition transitions depend on: own-force behavior (aid +, collateral damage −), enemy behavior, PSYOP, time since last contact.

### Design Principle

Civilian population is a **modifier layer**, not a separate combat system. It affects ROE constraints, intel flow, logistics throughput, and morale — all through existing parameters. No civilian combat resolution.

---

## 6. NBC/CBRN Effects

### Scope

Chemical, Biological, Radiological, and Nuclear effects on the battlefield. Focus on:
- Contamination zones (creation, persistence, drift)
- Protection equipment effects on unit performance (MOPP levels)
- Casualty generation from exposure
- Decontamination operations
- Terrain denial

### Existing Interface Points

- `environment/weather.py` — wind speed/direction for dispersal modeling
- `environment/obscurants.py` — smoke/dust drift model (reusable for chemical cloud)
- `terrain/classification.py` — terrain absorption/persistence
- `morale/stress.py` — stress modifiers for CBRN exposure
- `logistics/medical.py` — casualty treatment pipeline
- `movement/engine.py` — movement speed modifiers

### New Modules

- `cbrn/agents.py` — Agent definitions: nerve (VX, sarin), blister (mustard), choking (chlorine), blood (cyanide), biological (anthrax, plague), radiological (fallout). Persistence, lethality, detection threshold per agent.
- `cbrn/dispersal.py` — Gaussian puff/plume model for atmospheric dispersion. Wind-driven advection, turbulent diffusion. Terrain channeling effects.
- `cbrn/contamination.py` — Contamination zone manager: grid overlay tracking concentration per cell, decay over time, weather-dependent evaporation/washout.
- `cbrn/protection.py` — MOPP levels (0–4): movement penalty, detection penalty (reduced FOV in mask), fatigue acceleration, heat stress. Equipment effectiveness vs agent type.
- `cbrn/casualties.py` — Dose-response models: dosage = concentration × time. LD50/LCt50 tables. Incapacitation vs lethality timelines.
- `cbrn/decontamination.py` — Decon operations: time, equipment, thoroughness. Partial vs full decon.
- `cbrn/nuclear.py` — Nuclear effects: blast overpressure (Hopkinson-Cranz scaling), thermal radiation, initial nuclear radiation, EMP, fallout. Casualty radii by yield.

### Key Physics

- **Gaussian dispersion**: `C(x,y,z) = Q/(2πσyσzu) · exp(-y²/2σy²) · exp(-z²/2σz²)` — Pasquill-Gifford stability classes determine σy, σz
- **Nuclear blast**: `ΔP = f(R/W^(1/3))` — scaled distance, Hopkinson-Cranz law
- **Dose-response**: Probit model `Y = a + b·ln(D)` where D is dosage (Ct or Gy)
- **MOPP degradation**: Performance multipliers — MOPP-4 reduces combat effectiveness to ~60%, movement to ~70%, extends task times by 1.5x

### Design Principle

CBRN is a terrain modifier + casualty generator + performance degrader. Contamination zones are overlaid on the terrain grid. Units in contaminated cells take casualties based on protection level. No separate CBRN combat resolution — effects feed into existing damage, morale, and movement systems.

### Validation Scenarios

- **Halabja 1988 (doctrinal exercise analog)**: Chemical attack on a defended position. Validates dispersal model, MOPP response, casualty generation, and terrain denial. Use as a synthetic scenario based on documented agent types and meteorological conditions.
- **Nuclear doctrinal exercise**: Tactical nuclear weapon employment against a massed formation. Validates blast radii, EMP effects, fallout plume. Use standardized yield/range tables from FM 3-11 for comparison.

---

## 7. Doctrinal AI Schools

### Motivation

Phase 8 implemented a generic AI framework with YAML-driven commander personalities and doctrine templates. The brainstorm noted a future direction: **named doctrinal schools** where AI commanders operate according to fundamentally different theories of warfare, enabling comparative analysis.

### Schools

| School | Key Thinker | Core Principle | Decision Bias |
|--------|-------------|----------------|---------------|
| Clausewitzian | Clausewitz | Seek decisive battle at center of gravity | Concentrate force, accept attrition for decisive engagement |
| Sun Tzu (Indirect) | Sun Tzu | Win without fighting; deception + intel | Avoid strength, exploit weakness, prefer maneuver and deception |
| Maneuverist | Liddell Hart, Boyd | Tempo, dislocation, surfaces & gaps | Prioritize speed, bypass strongpoints, attack C2 and logistics |
| Attrition | Firepower school | Destroy enemy combat power systematically | Seek favorable exchange ratios, massed fires, deliberate operations |
| Soviet/Deep Battle | Tukhachevsky | Simultaneous deep operations | Echeloned attack, operational-depth strikes, reserves for exploitation |
| Maritime (Mahanian) | Mahan | Sea control through fleet engagement | Concentrate naval force, seek decisive fleet action |
| Maritime (Corbettian) | Corbett | Sea control through denial and limited war | Fleet-in-being, commerce raiding, selective engagement |
| AirLand Battle | Starry, DePuy | Simultaneous deep/close/rear operations | Deep fires + close fight synchronization, sensor-to-shooter, initiative to subordinates |
| Air Power | Douhet, Warden | Command of the air, strategic paralysis | Air superiority first, strategic targeting (Five Rings), interdiction over ground maneuver |

### Architecture

Build on existing Phase 8 infrastructure:
- `c2/ai/doctrine.py` already loads YAML doctrine templates with action filtering
- `c2/ai/commander.py` already has personality parameters
- `c2/ai/assessment.py` already has 7-factor weighted situation assessment
- `c2/ai/decisions.py` already has echelon-specific decision functions

New/modified modules:
- `c2/ai/schools/` — Package for school implementations
- `c2/ai/schools/clausewitzian.py` — CoG identification, decisive point selection, culmination awareness
- `c2/ai/schools/sun_tzu.py` — Intel-first assessment, deception planning, indirect approach preference
- `c2/ai/schools/maneuverist.py` — Tempo-driven OODA acceleration, gap exploitation, C2 targeting
- `c2/ai/schools/attrition.py` — Exchange ratio optimization, fire superiority, deliberate attack preference
- `c2/ai/schools/deep_battle.py` — Echeloned assault planning, operational-depth targeting, reserve management
- `c2/ai/schools/maritime.py` — Mahanian concentration vs Corbettian denial, fleet-in-being logic
- `c2/ai/schools/airland_battle.py` — Simultaneous deep/close/rear operations, sensor-to-shooter kill chain emphasis, aggressive initiative delegation, fire support coordination (FSCL-forward fires), deep strike synchronized with close fight
- `c2/ai/schools/air_power.py` — Five Rings targeting (leadership → organics → infrastructure → population → fielded forces), air superiority as prerequisite, strategic paralysis through parallel attack, interdiction preference over close support

Each school overrides:
1. **Assessment weighting** — Which of the 7 factors matter most (e.g., Sun Tzu weights intel 3x)
2. **COA generation** — Which action types are preferred/avoided
3. **Risk tolerance** — Modulates the Lanchester wargaming softmax temperature
4. **Decision triggers** — When to attack, defend, withdraw (school-specific thresholds)
5. **Stratagem affinity** — Which stratagems the school favors

### YAML Data

Each school has a YAML config:
```yaml
school: clausewitzian
display_name: "Clausewitzian (Decisive Battle)"
assessment_weights:
  force_ratio: 2.0      # double weight on force correlation
  intel_quality: 0.5     # less emphasis on perfect intel
  terrain_advantage: 1.0
preferred_actions: [ATTACK, CONCENTRATE, ENVELOP]
avoided_actions: [WITHDRAW, DELAY]
risk_tolerance: 0.7      # higher risk acceptance for decisive action
culmination_sensitivity: 0.8  # strong awareness of culmination point
stratagem_affinity: [FEINT, DEMONSTRATION]
```

9 school YAML configs total: clausewitzian, maneuverist, attrition, sun_tzu, deep_battle, maritime_mahanian, maritime_corbettian, airland_battle, air_power.

### Modern & Post-Classical Schools

Phase 19 implements 9 schools rooted in classical and Cold War-era doctrine. Three more recent theoretical developments extend beyond the conventional doctrinal spectrum and bridge toward Phase 24 (Unconventional Warfare):

#### Generational Warfare (Lind et al.)

William S. Lind and co-authors introduced the "Generations of Warfare" framework in *Marine Corps Gazette* (1989), mapping Western warfare evolution through four generations:

| Generation | Era | Core Logic | Decision Driver |
|------------|-----|-----------|-----------------|
| 1GW | Post-Westphalia–1860 | Line & column, massed fire | Formation discipline |
| 2GW | 1860–1918 | Firepower, attrition (Fr. *bataille conduite*) | Force ratio, fire superiority |
| 3GW | 1918–present (conventional) | Maneuver, tempo, Auftragstaktik | OODA speed, bypass, C2 collapse |
| 4GW | Emerging | Non-state, legitimacy contest, moral level | Political will, population disposition, information |

4GW argues the state loses its monopoly on war. The adversary may have no center-of-gravity in the Clausewitzian sense — the target is state *legitimacy* itself. Blurs war/peace, combatant/civilian, military/political. Fought primarily at Boyd's "moral level."

**5GW** (speculative — Abbott, *Handbook of 5GW*, 2010): Warfare through manipulation of context so subtle the target may not realize it is under attack. Cognitive manipulation, algorithmic influence, exploitation of systemic vulnerabilities. The "superempowered individual" concept (Barnett) — single actors achieving strategic effect through leverage of technology or network position.

**Modeling relevance**: 4GW maps to a doctrinal school that weights `population_disposition`, `political_will`, and `information_effects` far above `force_ratio`. Force ratio assessment weight near-zero. Seeks no decisive engagement. Planning horizon 5–10× baseline. 5GW mechanisms (information manipulation, systemic attacks) are individual capabilities rather than a unified school — they modulate existing assessment/decision functions.

**Key sources**: Lind et al., "The Changing Face of War" (*MCG* 1989, Tier 2). Lind, "Understanding Fourth Generation War" (*Military Review* 2004, Tier 1). Hammes, *The Sling and the Stone* (2004, Tier 3). Echevarria, *Fourth-Generation War and Other Myths* (SSI 2005, Tier 1 — argues 4GW is relabeled insurgency, not a new generation). Hoffman, "Hybrid Warfare and Challenges" (*JFQ* 2009, Tier 1 — hybrid warfare as more analytically useful framework than generational model).

#### Unrestricted Warfare (Qiao Liang & Wang Xiangsui)

*Unrestricted Warfare* (超限战, PLA Literature Press, 1999) by two PLA Air Force colonels argues any domain of human activity can become a weapon. Identifies 24 warfare types across three categories:

- **Military**: Atomic, conventional, biochemical, ecological, space, electronic, guerrilla, terrorist
- **Trans-military**: Diplomatic, network (cyber), intelligence, psychological, smuggling, drug, technological, virtual (deterrence)
- **Non-military**: Financial, trade, resource, economic aid, regulatory (legal/lawfare), sanction, media, ideological

Core principles: **Omnidirectionality** (attack from any domain), **Synchrony** (simultaneous multi-domain action for multiplicative effect), **Limited objectives** (cumulative strategic effect from many limited actions), **Unlimited means** (any tool legitimate), **Asymmetry** (avoid adversary strengths — if they dominate military, attack through finance).

Closely related: PLA "Three Warfares" (三战, formally adopted 2003) — psychological warfare (心理战), media warfare (舆论战), legal warfare/lawfare (法律战). Gerasimov's "New Generation Warfare" (2013) — 4:1 non-military-to-military ratio, phased escalation, reflexive control (рефлексивное управление — manipulating adversary decision-making, not just degrading it).

**Modeling relevance**: An "Unrestricted Warfare" school would dramatically expand the action space beyond kinetic options. Multi-domain synergy multiplier when N domains active simultaneously. Cost-benefit asymmetry inverts classical force ratio calculations ($1M cyber operation ≈ $1B conventional strike in strategic effect). Victory through cumulative erosion of systemic resilience, not decisive battle.

**Key sources**: Qiao & Wang, *Unrestricted Warfare* (1999, Tier 1 — original PLA publication). Gerasimov, "Value of Science Is in the Foresight" (*Voyenno-Promyshlennyy Kurier* 2013, Tier 1). Thomas, "Russia's Reflexive Control Theory" (*JSMS* 2004, Tier 2). Cheng, *Cyber Dragon* (Praeger 2017, Tier 2). Mattis & Brazil, *Chinese Communist Espionage* (NIP 2019, Tier 1 — Three Warfares formal doctrine).

#### Relationship to Existing Schools & Phase 24

These modern theories inherit from classical schools but add new action domains and victory conditions:

| Modern Theory | Classical Root | Extension |
|---------------|---------------|-----------|
| 4GW | Mao (people's war), Sun Tzu (asymmetry) | + information domain, legitimacy as CoG, non-state actors |
| Unrestricted Warfare | Sun Tzu (indirect), Clausewitz (war = politics) | + 24 warfare types, multi-domain synchrony, systemic targeting |
| Gerasimov Hybrid | Soviet deep battle (operational depth) | + phased non-military escalation, reflexive control, 4:1 non-kinetic ratio |

These schools are **not implementable in Phase 19** because they require non-kinetic action domains (information, cyber, economic, legal) that don't yet exist in the engine. They are natural candidates for **Phase 24** (Unconventional Warfare), which already plans escalation modeling, population-centric operations, and political pressure mechanics. A future "19+" sub-phase could add 4GW/Unrestricted Warfare/Gerasimov Hybrid schools once Phase 24's non-kinetic infrastructure is in place.

### Game-Theoretic Opponent Modeling

The original brainstorm identified game theory as a modeling tool for adversarial decision-making. Currently each AI commander decides independently with no model of the opponent's likely decisions. Deeper schools (particularly Sun Tzu and Maneuverist) should incorporate opponent modeling:

- **Simple opponent model**: Each school maintains a belief about the opponent's school/personality. Sun Tzu school explicitly models "what would the opponent do?" before deciding.
- **Minimax-lite**: For key decisions (attack/defend/withdraw), evaluate own outcome under opponent's best response. Not full game tree — just one-step lookahead using the Lanchester wargaming already in COA analysis.
- **Deception planning**: Sun Tzu school generates COAs designed to manipulate the opponent's assessment (feints to draw reserves, demonstrations to fix forces).

This is architecturally lightweight — it extends `c2/ai/assessment.py` with an opponent belief state and adds a `predict_opponent_action()` method that schools can override.

### OODA Cross-Reference

Phase 11d introduces tactical OODA acceleration (×0.5 at tactical tick rate). Phase 19's Maneuverist school applies its own OODA multiplier (×0.7). These must stack multiplicatively: a Maneuverist commander at tactical resolution gets `0.5 × 0.7 = 0.35` of base OODA time, reflecting both the resolution advantage and the doctrinal emphasis on tempo.

### Validation Approach

Run the same scenario (e.g., Golan Heights) with different doctrinal schools commanding each side. Compare outcomes:
- Does Clausewitzian AI seek the main body while Sun Tzu AI avoids it?
- Does Maneuverist AI produce faster OODA cycles than Attrition AI?
- Does Soviet Deep Battle AI echelon its attacks?
- Does AirLand Battle AI synchronize deep fires with close fight?
- Does Air Power AI prioritize air superiority before committing ground forces?
- Does Sun Tzu AI use deception to manipulate opponent decisions?

---

## 8. Developer Tooling & UX

### MCP Server

Expose simulation capabilities as an MCP (Model Context Protocol) server, enabling Claude and other LLM tools to:
- **Run scenarios**: "Run 73 Easting with these force modifications and show results"
- **Query simulation state**: "What is the force ratio at tick 500?"
- **Analyze results**: "Compare exchange ratios across 100 Monte Carlo runs"
- **Modify parameters**: "Set M1A2 thermal detection range to 4500m and re-run"

Architecture:
- `tools/mcp_server.py` — MCP server wrapping simulation engine
- Tools: `run_scenario`, `query_state`, `run_monte_carlo`, `compare_results`, `list_scenarios`, `list_units`
- Resources: scenario YAML files, unit definitions, simulation results

### Claude Skills Expansion

Extend existing skill set:
- `/scenario` — Create/edit scenario YAML interactively
- `/compare` — Run two configurations and compare outcomes
- `/what-if` — Quick parameter sensitivity analysis
- `/timeline` — Generate tick-by-tick narrative of a battle
- `/orbat` — Build/edit order of battle interactively
- `/calibrate` — Auto-tune calibration overrides to match historical data

### Visualization

matplotlib is available for dev. Post-MVP visualization priorities:
- **Animated battle replay**: Frame-per-tick showing unit positions, engagements, detections
- **Force strength timeline**: Stacked area chart of combat power over campaign
- **Engagement network**: Graph showing who engaged whom, with outcomes
- **Supply network visualization**: networkx graph with flow quantities
- **Terrain overlay**: heightmap + unit positions + LOS cones

### Analysis Tools

- `tools/sensitivity.py` — Parameter sweep: vary one parameter, hold others constant, plot outcome distribution
- `tools/comparison.py` — A/B scenario comparison with statistical significance tests
- `tools/narrative.py` — Natural language generation from recorder events (tick-by-tick battle narrative)
- `tools/tempo_analysis.py` — Operational tempo analysis: FFT of engagement frequency over time to identify periodicity, tempo comparison between sides, OODA cycle timing distributions. The original brainstorm identified spectral analysis of operational tempo as a post-run analysis tool — this implements it.

---

## 9. Historical Era Expansion

### Philosophy

The engine is era-agnostic by design — YAML-driven unit definitions, weapon physics, and doctrine templates mean a new era is primarily a **data package** plus targeted engine extensions. The core loop (detect → decide → move → engage → assess) is universal.

### WW2 Era (Phase 20)

**What changes from modern era**:
- No precision guided munitions — all ballistic
- Radar is new/rare — visual detection dominates
- Radio is unreliable — greater C2 friction
- No thermal sights — night fighting is blind
- Aircraft are slower, lower, more vulnerable to AAA
- Submarines use torpedoes, not missiles; sonar is primitive
- Naval gunnery dominates (no anti-ship missiles until late war)

**New YAML data**: Sherman, T-34, Tiger, Panther, Bf-109, P-51, Spitfire, U-boat Type VII, Fletcher DD, Iowa BB, etc.
**Engine extensions**: Propeller aircraft flight model, naval gunnery fire control (pre-computer), formation sailing, convoy escort mechanics, strategic bombing.
**Validation scenarios**: Kursk, Normandy, Midway, Battle of the Atlantic (campaign).

### WW1 Era (Phase 21)

**What changes**:
- Static trench warfare — terrain is king
- No maneuver at operational level (until 1918)
- Artillery dominates — indirect fire is primary killer
- Primitive aircraft — recon only initially, then fighters/bombers
- Chemical weapons — mustard gas, chlorine, phosgene (requires CBRN module from Phase 18)
- No radio below division — wire/messenger/runner C2
- Naval: dreadnoughts, submarines emerging, mines critical

**New YAML data**: Lee-Enfield, Maxim MG, 18-pounder, Mark IV tank, Fokker Dr.I, SPAD XIII, HMS Dreadnought, U-boat.
**Engine extensions**: Trench system terrain type, creeping barrage model, gas dispersal (via CBRN), wire obstacles, sapping/mining, naval line-of-battle.
**Validation scenarios**: Somme, Verdun, Jutland, Cambrai.

### Napoleonic Era (Phase 22)

**What changes**:
- No electronic detection — visual only, line-of-sight
- Black powder weapons — short range, slow reload, volley fire
- Formation is critical — line, column, square, skirmish
- Cavalry is a major arm — charges, pursuit, screening
- Artillery is direct-fire at short range, smoothbore
- C2 is courier/ADC — hours of delay, massive friction
- Logistics: forage, living off the land
- Morale/cohesion is paramount — rout cascades decide battles

**New YAML data**: Line infantry, light infantry, grenadiers, cavalry (light/heavy/lancer), horse artillery, foot artillery, Napoleon's Guard.
**Engine extensions**: Volley fire model, cavalry charge mechanics, square formation (anti-cavalry), melee combat, foraging logistics, courier C2 with interception risk.
**Validation scenarios**: Austerlitz, Waterloo, Borodino.

### Ancient & Medieval Era (Phase 23)

**What changes**:
- Melee combat dominates — weapons are contact-range
- Formation and morale determine everything
- No gunpowder — bows/crossbows are only ranged weapons
- Siege warfare is primary operational art
- C2 is visual/audible — banners, horns, runners (hundreds of meters)
- Logistics: pillage, foraging, seasonal campaigns
- Detection: scouts on horseback, no technology
- Naval: oar-powered galleys, boarding actions

**New YAML data**: Legionary, hoplite, longbowman, knight, pike block, catapult, trireme, longship.
**Engine extensions**: Melee combat model (frontage, depth, weapon reach), shield wall / phalanx formation, siege mechanics (walls, rams, siege towers), cavalry charge impact, morale-dominant combat resolution, seasonal campaign constraints.
**Validation scenarios**: Cannae, Agincourt, Hastings, Thermopylae.

### Era Extension Architecture

Each era is a self-contained data package:
```
data/eras/
  modern/          # existing data (default)
  ww2/
    units/
    weapons/
    ammunition/
    sensors/
    signatures/
    doctrine/
    commanders/
    scenarios/
  ww1/
  napoleonic/
  ancient_medieval/
```

Engine extensions are additive — new combat models (melee, volley fire) sit alongside existing ones. The engagement module dispatches based on weapon type. Era-specific modules:
- `combat/melee.py` — Contact-range combat (Napoleonic bayonet, medieval)
- `combat/volley_fire.py` — Massed musket/bow fire
- `combat/siege.py` — Siege mechanics (walls, breaching, mining)
- `movement/cavalry.py` — Charge mechanics, pursuit, fatigue
- `movement/naval_oar.py` — Galley propulsion, ramming
- `logistics/foraging.py` — Living off the land, pillage
- `c2/courier.py` — Physical messenger model with interception

---

## 12. Unconventional & Prohibited Warfare

### Scope & Motivation

A high-fidelity wargame simulator that models only convention-compliant warfare is historically incomplete. From the Eastern Front's mutual escalation spiral (1941–45), to Halabja's chemical attack on civilians (1988), to Srebrenica's protected zone violation (1995), to the IED campaigns of Iraq and Afghanistan (2003–2021) — a significant fraction of historically significant conflicts involve **deliberate violations** of the laws of armed conflict, employment of prohibited weapons, unconventional/irregular warfare tactics, or escalatory dynamics that drive belligerents beyond their initial ROE constraints.

Currently the engine models "what happens" mechanically (combat resolution, morale, logistics) but lacks two critical dimensions:
1. **"Why" — Escalation dynamics**: What drives a commander from conventional warfare to employing chemical weapons, targeting civilians, or using prohibited methods? The answer is desperation — some function of casualties sustained, supply crisis, morale collapse, and stalemate duration.
2. **"What follows" — Consequence cascading**: War crimes and prohibited weapon employment are not "free" options with purely tactical effects. They cascade through the political dimension (international condemnation, sanctions, coalition fracture), the moral dimension (own-force guilt/trauma, enemy morale hardening), the population dimension (civilian hostility, insurgency recruitment), and the operational dimension (ROE tightening/loosening, allied support changes).

Without these dynamics, the simulator cannot model:
- Why Iraq employed chemical weapons at Halabja (desperation in the Iran-Iraq War)
- Why the Eastern Front spiraled into mutual atrocity (escalation-retaliation dynamics)
- How IED campaigns in Afghanistan shaped coalition ROE and strategy
- Why COIN doctrine emphasizes population protection (collateral → hostility → insurgency feedback loop)
- How war crimes affect coalition cohesion (Abu Ghraib → allied political pressure)

### Existing Interface Points

The MVP already has substantial hooks that an escalation/unconventional warfare system would modulate:

| System | Hook | Current State | Phase 24 Extension |
|--------|------|---------------|-------------------|
| ROE | `c2/roe.py` | `RoeLevel` (HOLD/TIGHT/FREE), `TargetCategory` (incl. PROTECTED_SITE), `RoeViolationEvent` with severity | Treaty compliance gate, prohibited weapon check, political pressure→ROE modulation |
| Morale | `morale/psychology.py`, `morale/stress.py` | PSYOP effects, stress random walk, surrender probability | War crimes guilt/trauma, enemy hardening from atrocity |
| Special Org | `entities/organization/special_org.py` | `OrgType.SOF`, `OrgType.IRREGULAR` with traits | `OrgType.INSURGENT`, `OrgType.MILITIA`, `OrgType.PMC` |
| Disruption | `logistics/disruption.py` | Sabotage (with `population_hostility` param), blockade, interdiction | Insurgent cell operations as disruption source, scorched earth |
| Prisoners | `logistics/prisoners.py` | Capture, processing, evacuation, supply consumption | Treatment tracking (standard/mistreated/tortured), interrogation model |
| Engagement | `combat/engagement.py` | Full kill chain, ROE check | Pre-engagement prohibited weapon gate, civilian proximity check |
| Damage | `combat/damage.py` | `DamageType.INCENDIARY` exists (unused), DPICM submunitions modeled | Activate INCENDIARY path with fire spread, UXO persistence for cluster munitions |
| Obstacles | `movement/obstacles.py` | `ObstacleType.MINEFIELD` | `ObstacleType.IED`, `ObstacleType.BOOBY_TRAP` |
| AI Decisions | `c2/ai/decisions.py` | 5 echelon-specific action enums, ROE gates | Escalation action types gated by personality + desperation |
| AI Adaptation | `c2/ai/adaptation.py` | 7 triggers (casualties, force ratio, supply, morale, opportunity, surprise, C2) | `MILITARY_STALEMATE` and `POLITICAL_PRESSURE` triggers |
| Commander | `c2/ai/commander.py` | Personality traits (aggression, caution, flexibility, initiative, experience, risk_acceptance) | `doctrine_violation_tolerance`, `collateral_tolerance`, `escalation_awareness` |
| Stratagems | `c2/ai/stratagems.py` | 6 types (DECEPTION through DEMONSTRATION) | `SABOTAGE_CAMPAIGN`, `TERROR`, `SCORCHED_EARTH` |
| Assessment | `c2/ai/assessment.py` | 7-factor weighted situation assessment | Desperation index computation |
| Civilian Pop | Phase 12e planned | Displacement, collateral, HUMINT, influence | Radicalization→recruitment→insurgency pipeline |
| CBRN | Phase 18 planned | Agent effects, contamination, casualties | Offensive employment decision logic, chemical/nuclear escalation |

### Escalation & Consequence Model

The core new system. Three interdependent layers:

#### Escalation Ladder (0–10 Scale)

A discrete state machine modeling the progression from conventional warfare to the most extreme measures:

| Level | Name | Description | Example |
|-------|------|-------------|---------|
| 0 | Conventional | Full compliance with LOAC and treaties | Standard NATO/Warsaw Pact engagement |
| 1 | ROE Relaxation | Loosened engagement criteria, reduced positive ID requirements | Coalition in heavy contact, WEAPONS_FREE authorized |
| 2 | Collateral Acceptance | Civilian casualties accepted as proportional to military necessity | Siege warfare, urban operations with known civilian presence |
| 3 | ROE Violations | Deliberate targeting outside ROE, disproportionate force | Retaliatory strikes on civilian infrastructure |
| 4 | Prohibited Methods | Perfidy, human shields, execution of prisoners | Misuse of protected emblems, hostage-taking |
| 5 | Chemical Employment | Tear gas escalating to nerve/blister agents | Iraq-Iran War chemical escalation, Halabja |
| 6 | Biological Employment | Weaponized biological agents | Historical: Japanese Unit 731, Soviet Biopreparat |
| 7 | Tactical Nuclear | Low-yield nuclear weapons against military targets | NATO Able Archer-era doctrine, Soviet OMG nuclear support |
| 8 | Theater Nuclear | Multiple nuclear strikes within theater | European theater nuclear exchange scenarios |
| 9 | Strategic Nuclear (Limited) | Counter-force targeting, limited strategic exchange | SIOP options, controlled escalation doctrine |
| 10 | Strategic Nuclear (General) | Full counter-value exchange | MAD scenario, general nuclear war |

**Transition mechanics**: Each escalation level has an **entry threshold** that depends on a composite **desperation index**:

```
desperation = w_cas × (casualties_sustained / initial_strength)
            + w_sup × (1 - supply_state)
            + w_mor × (1 - avg_morale_score)
            + w_sta × stalemate_duration_normalized
            + w_pol × political_pressure_from_below
```

Where:
- `w_cas, w_sup, w_mor, w_sta, w_pol` are configurable weights (YAML)
- `stalemate_duration_normalized` measures how long the front has been static relative to campaign duration
- `political_pressure_from_below` captures domestic political pressure to "do something" (distinct from international pressure modeled in the political layer)

Commander personality modulates willingness to escalate:
- `doctrine_violation_tolerance` (0.0–1.0): threshold multiplier — high tolerance means escalation at lower desperation
- `escalation_awareness` (0.0–1.0): awareness of consequences — high awareness inhibits escalation
- Historical example: Saddam Hussein — high `doctrine_violation_tolerance` (0.9), low `escalation_awareness` (0.2)

#### Political Pressure Model

International and domestic political dynamics modeled as two coupled 0–1 parameters:

**International pressure** (`P_int`):
```
dP_int/dt = k_crime × war_crime_rate
          + k_collateral × civilian_casualty_rate
          + k_prohibited × prohibited_weapon_events
          + k_media × (media_visibility × atrocity_severity)
          - k_decay × P_int  # pressure decays without new events
```

**Domestic pressure** (`P_dom`):
```
dP_dom/dt = k_own_cas × own_casualty_rate
          + k_stalemate × stalemate_indicator
          + k_propaganda × (enemy_psyop_effectiveness - own_narrative_control)
          - k_threat × perceived_existential_threat  # existential threat suppresses domestic dissent
```

**Political pressure effects** (modulate existing systems):

| Pressure Threshold | Effect |
|-------------------|--------|
| `P_int > 0.3` | Allied supply constraints (sanctions begin — reduce supply throughput) |
| `P_int > 0.5` | Coalition fracture risk (per-ally defection probability, removes units + support) |
| `P_int > 0.7` | Forced ROE tightening (international community mandates WEAPONS_HOLD) |
| `P_int > 0.9` | War termination pressure (victory conditions shift — time pressure to negotiate) |
| `P_dom > 0.3` | ROE loosening authorized (domestic pressure to "win" overrides restraint) |
| `P_dom > 0.5` | Escalation authorized (political leadership authorizes next escalation level) |
| `P_dom > 0.7` | Conscription/mobilization (force generation event, but morale of conscripts lower) |
| `P_dom > 0.9` | Leadership change risk (probability of regime change, new commander personality) |

Note the tension: **international pressure constrains** while **domestic pressure enables** escalation. A belligerent losing badly faces both simultaneously — constrained externally but pressured internally. This creates the realistic dilemma that drives historical escalation decisions.

#### Consequence Cascading

War crimes and prohibited weapon use trigger multi-domain consequences:

| Event | Own-Force Effect | Enemy Effect | Population Effect | Political Effect |
|-------|-----------------|--------------|-------------------|-----------------|
| Civilian massacre | Morale penalty (guilt/PTSD stress), unit cohesion degradation | Morale hardening (+resolve), recruitment surge | Disposition shifts hostile, displacement spike | `P_int` surge, coalition strain |
| Chemical weapon use | Morale penalty (guilt), MOPP degradation if own troops exposed | Morale fear/panic initially, then hardening (justified anger) | Mass displacement, hostile disposition | `P_int` massive spike, potential intervention |
| Prohibited weapon (cluster, AP mine) | None immediate; long-term UXO risk to own forces | Effective suppression but UXO denial persists | UXO civilian casualties feed hostility | `P_int` moderate increase |
| Prisoner mistreatment | Morale penalty if discovered internally | Enemy fights harder (no surrender incentive) | Hostile shift | `P_int` surge if documented |
| Scorched earth | Supply denial to enemy | Supply denial to self (can't advance into destroyed area) | Mass displacement, total hostility | `P_int` moderate increase |
| Infrastructure targeting | Logistics disruption | Same for enemy | Economic collapse, hostility | `P_int` proportional to civilian impact |
| Perfidy (false flag) | Trust erosion if discovered, allied distrust | Confusion initially, distrust of all signals later | Displacement, suspicion | `P_int` severe if documented |

**Feedback loops** (the critical dynamics):

1. **Escalation spiral**: Side A commits atrocity → Side B morale hardens + demands retaliation → Side B escalates → Side A retaliates further. The Eastern Front's mutual descent into total war.
2. **COIN feedback**: Collateral damage → civilian hostility → insurgency recruitment → more IEDs → more aggressive response → more collateral damage. The Afghanistan cycle.
3. **Coalition fracture**: War crimes → international pressure → ally defection → weakened force → more desperation → more escalation. The dynamic that constrains democracies differently from authoritarian regimes.
4. **Deterrence through consequences**: High `escalation_awareness` commanders factor in consequence costs, producing restraint. Nuclear deterrence works through this mechanism.

### Prohibited Weapons & Methods

Data-driven extensions to the existing weapon/ammo framework:

#### Treaty Compliance Framework

Add `prohibited_under_treaties: list[str]` to `AmmoDefinition`:

```yaml
# Example: cluster munition
ammo_id: mk20_rockeye
display_name: "Mk 20 Rockeye Cluster Bomb"
ammo_type: CLUSTER
damage_type: FRAGMENTATION
submunition_count: 247
submunition_lethal_radius_m: 3.0
uxo_rate: 0.05  # 5% failure rate → persistent hazard
prohibited_under_treaties:
  - "Convention on Cluster Munitions (2008)"
compliance_check: true  # engagement engine checks ROE + treaty
```

The engagement engine performs a pre-fire compliance check:
1. Is the ammo flagged `compliance_check: true`?
2. Does the unit's ROE + escalation level permit prohibited weapons?
3. If not, select alternative ammo or abort engagement.
4. If yes, log `ProhibitedWeaponEmployedEvent` → triggers consequence cascade.

#### Weapon Categories

| Category | Existing State | Phase 24 Extension |
|----------|---------------|-------------------|
| **Cluster munitions** | DPICM submunitions modeled in `indirect_fire.py` | Add `AmmoType.CLUSTER`, UXO persistence (area denial after attack), civilian UXO casualty generation feeding collateral/political models |
| **Anti-personnel mines** | `ObstacleType.MINEFIELD` exists | Add `ObstacleType.AP_MINE_PERSISTENT` (not clearable by vehicle, long persistence), hostile-population-planted mines (insurgency mechanic), Ottawa Treaty compliance flag |
| **Incendiary weapons** | `DamageType.INCENDIARY` in enum (unused) | Activate incendiary damage path: fire spread model (wind-driven, terrain-fuel-dependent), structure ignition, burn casualty generation, smoke obscurant side-effect. Protocol III compliance flag. |
| **Expanding/fragmenting ammo** | Not modeled | New `AmmoType.EXPANDING` with higher wound severity multiplier (Hague Convention compliance flag). Primarily relevant for small arms in COIN/urban scenarios. |
| **Chemical weapons** | Phase 18 CBRN effects (contamination, dispersal, casualties) | Phase 24 adds the **decision logic** — when does an AI commander authorize chemical employment? Wires Phase 18 agent effects into the escalation ladder (Level 5). Offensive delivery systems (artillery shell, aerial bomb, SCUD warhead — all Phase 18 YAML data). |
| **Biological weapons** | Phase 18 CBRN effects (biological agents) | Offensive employment decision logic (Level 6). Delayed effect makes attribution difficult — lower immediate political cost but higher eventual cost. |
| **Nuclear weapons** | Phase 18 nuclear effects (blast, thermal, radiation, EMP, fallout) | Offensive employment decision logic (Levels 7–10). Escalation ladder controls authorization. Yield selection (tactical 0.1–10 kT vs strategic 100 kT–MT). |
| **Booby traps** | Not modeled | New `ObstacleType.BOOBY_TRAP` — concealed in structures/terrain, triggered by entry. Lower lethality than mines, higher psychological impact (stress modifier). |
| **White phosphorus** | Not modeled | Dual-use: legal as obscurant/illumination, prohibited as anti-personnel incendiary when used against civilian areas. Compliance depends on employment context, not the weapon itself. Modeled as an incendiary with obscurant secondary effect. |

#### Fire Spread Model (for Incendiary Weapons)

Incendiary weapons create fire events that spread based on:
- **Wind**: Fire spreads downwind at rate proportional to wind speed
- **Terrain fuel**: `TerrainClassification` provides fuel load (forest > grassland > urban > desert > water)
- **Moisture**: Weather humidity/rain suppress spread rate
- **Structures**: Urban structures catch fire, producing structural collapse hazard + smoke

Fire spread uses a simplified cellular automaton on the terrain grid:
```
P(cell ignites in dt) = Σ(adjacent_fire_cells) × fuel_load × wind_factor × (1 - moisture_factor)
```

Fire persists for duration based on fuel load, then transitions to "burned" terrain (reduced concealment, denied area).

### Unconventional Warfare Mechanics

New capabilities for irregular, asymmetric, and hybrid conflict:

#### IED / Booby Trap System

IEDs are the signature weapon of asymmetric warfare. They represent the most lethal threat in modern COIN operations (>60% of coalition casualties in Iraq/Afghanistan).

**IED characteristics**:
- **Placement**: Hostile population cells generate IED placement events. Probability scales with `population_hostility × cell_traffic × insurgent_cell_presence`. Roads and chokepoints have highest probability.
- **Types**: command-wire (requires operator nearby), pressure-plate (triggered by vehicle weight), remote-detonated (radio — can be jammed by Phase 16 EW), vehicle-borne (VBIED — large blast radius, civilian vehicle camouflage)
- **Detection**: Engineering units with route clearance capability. Detection probability from sensor type (visual inspection, mine roller, ground-penetrating radar if available). Speed-detection tradeoff: slower movement = higher detection probability.
- **Effects**: Blast damage (existing damage model) + psychological/morale effects (stress spike to entire unit, not just casualties). Route denial if IEDs suspected but uncleared.
- **Counter-IED**: Route clearance patrols, counter-IED teams (SOF + engineering), population engagement (HUMINT tips from friendly civilians reveal IED locations), EW jamming of remote detonators.

#### Guerrilla & Insurgency Tactics

**Hit-and-run doctrine**:
- Guerrilla units (`OrgType.INSURGENT`) have a special doctrine template: engage only when local superiority exists, disengage immediately after inflicting casualties, use terrain for escape routes, avoid decisive engagement
- **Disappear into population**: After engagement, guerrilla units can "blend" with civilian population if in populated area. Detection probability drops to near-zero. Requires HUMINT or prolonged presence to locate.
- **Ambush-focused**: Guerrilla doctrine heavily weights ambush stratagems. Site selection considers terrain (chokepoints, dead ground) and intelligence (pattern-of-life analysis of enemy movement)

**Insurgency dynamics** (builds on Phase 12e civilian population):

The insurgency pipeline is a multi-stage Markov chain:

```
Civilian Population (neutral) → Sympathizer → Active Supporter → Insurgent Cell Member → Armed Combatant
```

Transition rates driven by:
- **Radicalization factors**: Collateral damage from military operations (+), economic deprivation (+), religious/ethnic grievance (+), family member killed (+)
- **De-radicalization factors**: Economic opportunity (−), governance quality (−), military protection of population (−), PSYOP/influence operations (−)
- **Cell formation**: When sufficient active supporters exist in an area, insurgent cells form. Cells have capabilities: sabotage, IED emplacement, ambush, intelligence gathering for enemy, assassination/HVT targeting
- **Cell activation**: Cells transition from dormant (intelligence gathering) to active (operations) based on orders, opportunity, or trigger events (e.g., military raid on sympathizer area)

#### Non-State Actor Types

| Actor | Loyalty Model | Economics | Capabilities |
|-------|-------------|-----------|-------------|
| **PMC (Private Military Company)** | Contract-based loyalty — degrades below payment threshold, defects if employer loses. No ideological commitment. | Requires payment (Class V supply: cash). No payment → desertion. High pay → enhanced performance. | Professional-grade equipment and training. Limited heavy weapons. Specialized capabilities (VIP protection, infrastructure security, training). |
| **Militia** | Tribal/ethnic/religious loyalty — fights for territory/identity, not chain of command. Unreliable for offensive operations outside home territory. | Looting/taxation of local economy. Self-sustaining in home territory. Degrades rapidly when displaced. | Light infantry weapons. Local terrain knowledge bonus. Poor discipline, high fratricide risk. |
| **Criminal Armed Groups** | Opportunistic — fights whoever threatens their economic interests. Will change sides for better deal. | Criminal economy (smuggling, drugs, protection rackets). Can be co-opted with economic incentives. | Light-medium weapons (sometimes heavy, via black market). Good local intelligence network. |
| **Insurgent Cells** | Ideological commitment — high morale even under pressure. Difficult to deter through conventional means. | External sponsorship (state or diaspora funding) + local taxation/extortion. | IEDs, small arms, suicide attacks. Asymmetric capabilities. Intelligence via population network. |

#### SOF / Special Operations

Expanding the existing `sof_operator` commander profile and `OrgType.SOF`:

- **Behind-lines infiltration**: SOF units can penetrate enemy rear areas via special insertion methods (HALO, submarine, overland covert). Detection probability heavily reduced (signature management).
- **HVT targeting / leadership decapitation**: SOF can target specific enemy commanders. Success → `CommandAuthorityEvent.DESTROYED` for target's command chain. Succession mechanics already exist — SOF exploit them.
- **Direct action**: Surgical strikes on high-value targets (C2 nodes, logistics hubs, air defense radars). Small force, high impact, disproportionate to unit size.
- **Unconventional warfare**: SOF working through indigenous forces — train, equip, advise local militia/insurgents. Force multiplication effect (SOF team enables battalion-equivalent irregular force).
- **Sabotage campaigns**: Targeted infrastructure destruction tied to logistics disruption. Bridge destruction severs supply routes. Power grid attacks degrade C2/radar. Fuel depot destruction creates supply crisis.

#### Prohibited Methods of Warfare

| Method | Mechanism | Detection | Consequences |
|--------|-----------|-----------|--------------|
| **Perfidy** | Unit displays protected emblem (Red Cross, white flag) while hostile. Enemy forces in engagement range before detecting deception. | Detection event when engagement occurs from "protected" unit. Probability-based: `P(detect) = experience × intel_quality`. | Once detected: all future legitimate protected activities doubted. Friendly fire on actual medical/surrender increases. Enemy morale hardens. |
| **Human shields** | Civilian presence exploited to prevent engagement. Unit positions in civilian-dense area. | Always known (civilian population overlay). | Enemy force with ROE enforcement faces WEAPONS_HOLD. Only WEAPONS_FREE escalation level overrides. Engagement through shields → massive civilian casualties → political/consequence cascade. |
| **Scorched earth** | Deliberate destruction of infrastructure, agriculture, and resources as denial tactic. | Observable via terrain state change (infrastructure destroyed, fields burned). | Denied area for both sides. Civilian mass displacement. Long-term economic damage. Political pressure proportional to civilian impact. |
| **Hostage-taking** | Capture of civilians/prisoners used as bargaining leverage. | Known to captor side, suspected by other side via intel. | Constrains enemy operations (rescue attempt risk). Political pressure. Own-force morale impact if ordered to participate. |
| **Collective punishment** | Military action targeting civilian population as retaliation for insurgent activity. | Observable via collateral damage events. | Massive civilian hostility increase. Insurgency recruitment surge. International condemnation. Counterproductive to COIN objectives. |
| **Interrogation under duress** | Stress-based model on prisoner groups. Enhanced interrogation → faster intelligence extraction but unreliable (high noise). | Internal to capturing force. Leak probability based on unit discipline/media presence. | Yields HUMINT with delay + noise (stress-based: high stress → faster yield, lower reliability). Own-force morale penalty if widespread. Political consequences if documented. |

### Design Principles

1. **Modulation pattern**: Escalation modulates existing ROE, morale, AI decision, and political systems — no parallel combat resolution engine. Chemical weapons use the Phase 18 CBRN dispersal/casualty system. IEDs use the existing damage model. Guerrilla ambushes use the existing engagement system. The new code is primarily **decision logic** (when to escalate, what consequences follow) and **data** (prohibited weapon flags, doctrine templates, personality traits).

2. **All sides can violate**: Escalation is not hard-coded as "enemy does war crimes." Any AI commander can escalate based on personality traits + desperation index. A democratic coalition can commit war crimes under enough pressure (Abu Ghraib). An authoritarian regime may exercise more restraint than expected if escalation awareness is high (Soviet restraint in some Cold War scenarios).

3. **Consequences are systemic, not token**: War crimes aren't a "bad action" that gets logged and forgotten. They cascade through morale (guilt, hardening), politics (international/domestic pressure), population (hostility, insurgency), and operations (ROE changes, coalition integrity). The feedback loops create emergent dynamics — the Eastern Front escalation spiral emerges from the model, it's not scripted.

4. **YAML-driven configurability**: All thresholds, personality traits, escalation ladder weights, political pressure parameters, and consequence magnitudes are YAML-configurable. This allows:
   - Scenario-specific calibration (Halabja scenario has different escalation thresholds than modern COIN)
   - Sensitivity analysis (what if escalation awareness is higher? what if international pressure response is faster?)
   - Era-specific behavior (WW2 Eastern Front has different political constraints than 2003 Iraq)

5. **Optional by default**: `escalation_config: null` in scenario YAML → conventional warfare only. No EscalationEngine instantiated, no political pressure tracking, no prohibited weapon checks beyond existing ROE. All existing scenarios work unchanged. This is critical — most validated scenarios (73 Easting, Golan Heights) are conventional engagements.

6. **Builds on prerequisite phases**:
   - **Phase 12e (required)**: Civilian population model provides the population-hostility-insurgency pipeline foundation
   - **Phase 18 (required)**: CBRN effects provide the weapon effects for chemical/biological/nuclear escalation
   - **Phase 19 (benefits from)**: Doctrinal schools provide school-specific escalation tendencies (e.g., Soviet Deep Battle doctrine's attitude toward civilian collateral differs from Western Maneuverist)

7. **Ethical framing**: The simulator models these dynamics for analytical purposes — understanding **why** escalation happens, **what** consequences follow, and **how** different policies/doctrines/personalities affect outcomes. The purpose is the same as modeling any other aspect of warfare: enabling better understanding to inform better decisions. This is consistent with the project's research source inclusion of Walzer (*Just and Unjust Wars*), Grotius, and Thucydides.

### Validation Scenarios

Four scenarios spanning different escalation dynamics:

#### Halabja 1988 (Chemical Escalation)
- **Historical context**: Iraqi chemical attack on Kurdish town during Iran-Iraq War. Mustard gas and nerve agents killed ~5,000 civilians. Driven by Iraqi desperation against Kurdish insurgency + Iran-Iraq War stalemate.
- **What it validates**: Chemical weapon employment decision logic (high `doctrine_violation_tolerance` + high desperation → Level 5 escalation). CBRN dispersal/casualty effects (Phase 18). Political consequence model (international condemnation, but limited response due to Cold War dynamics — `P_int` rise but no intervention).
- **Calibration**: Escalation should occur when desperation index exceeds commander threshold. Casualties should match order-of-magnitude historical data. Political pressure should rise but not trigger intervention (historical accuracy).

#### Srebrenica 1995 (ROE Failure & Protected Zone Violation)
- **Historical context**: Bosnian Serb forces overran UN-designated safe area. Dutch UNPROFOR battalion unable to protect ~8,000 Bosniak civilians/prisoners. Multiple systemic failures: inadequate force, restrictive ROE, lack of air support, command paralysis.
- **What it validates**: Escalation from Level 0 to Level 4 (prohibited methods — execution of prisoners). ROE constraint modeling (Dutch forces constrained to WEAPONS_HOLD). Command succession under C2 paralysis. Political consequence cascade (international pressure surge → NATO intervention → Dayton Accords). Own-force morale trauma (Dutch veterans' PTSD).
- **Calibration**: Dutch forces should be unable to prevent atrocity given their ROE and force size. Political pressure should spike to intervention threshold. Enemy morale hardening should reflect Bosnian resistance stiffening post-Srebrenica.

#### Eastern Front WW2 (Mutual Escalation Spiral)
- **Historical context**: 1941–1945 German-Soviet conflict. Both sides escalated from conventional warfare to systematic atrocity. Commissar Order, Hunger Plan, scorched earth (both sides), partisan warfare, reprisal killings, siege warfare (Leningrad, Stalingrad).
- **What it validates**: Escalation spiral dynamics — both sides escalate in response to each other. Scorched earth mechanics (German retreat destroys infrastructure → Soviet supply crisis → Soviet scorched earth on advance). Partisan/guerrilla warfare behind lines. Population hostility→partisan recruitment→sabotage→reprisal cycle. Existential threat suppresses domestic pressure (both sides fought on despite horrific casualties because perceived existential threat overrode dissent).
- **Calibration**: Escalation should be mutual and progressive. Partisan activity should scale with population hostility. Scorched earth should produce measurable logistics degradation. `perceived_existential_threat` parameter should suppress `P_dom` (both sides fought to the end).

#### Modern COIN (IED Campaign & Population Dynamics)
- **Historical context**: Composite scenario based on Iraq/Afghanistan counterinsurgency operations (2003–2021). IED campaigns, population engagement, hearts-and-minds vs kinetic approaches, coalition ROE constraints, insurgency recruitment dynamics.
- **What it validates**: IED emplacement and detection model. Guerrilla hit-and-run doctrine. Insurgency recruitment pipeline (collateral → hostility → recruitment → IED). COIN approach comparison: aggressive kinetic (high collateral → more insurgents) vs population-centric (lower collateral → reduced recruitment but slower). Coalition ROE constraints under political pressure. Counter-IED operations (route clearance, HUMINT tips from friendly population).
- **Calibration**: Kinetic approach should produce higher short-term enemy casualties but increasing insurgent recruitment. Population-centric approach should produce lower immediate results but declining insurgency over time. This is the central thesis of FM 3-24 Counterinsurgency.

### Cross-Phase Dependencies

```
Phase 12e (Civilian Population) ──→ Phase 24 (Unconventional & Prohibited Warfare)
                                        ↑
Phase 18 (CBRN Effects) ────────────────┘
                                        ↑ (benefits from)
Phase 19 (Doctrinal AI Schools) ────────┘
Phase 16 (EW) ──────────────────────────┘ (counter-IED jamming)
```

Phase 24 is architecturally a **modulation layer** on top of existing combat, morale, C2, and logistics systems, plus the civilian population (12e) and CBRN (18) systems. It adds decision logic, consequence computation, and data — not a new combat resolution path.

---

## 13. Strategic Air Campaigns, IADS & Operational Gaps

### Motivation

The MVP models air combat at the engagement level — individual aircraft engage individual targets via `air_combat.py`, `air_ground.py`, and `air_defense.py`. But modern air warfare is fundamentally a **campaign-level** activity. The 1991 Gulf War air campaign lasted 38 days and systematically dismantled Iraqi IADS, infrastructure, and fielded forces through a coordinated sequence of thousands of sorties. The simulation currently cannot model this — each engagement is isolated, air defense systems operate independently, and there is no mechanism for strategic targeting to cascade into operational effects.

Three interconnected gaps define this area:

### Integrated Air Defense Systems (IADS)

**The problem**: Individual SAM batteries firing independently are far less effective than a coordinated IADS. The 1982 Bekaa Valley engagement demonstrated this — Israel destroyed 17 Syrian SAM batteries in a single afternoon by exploiting the gaps between independently operating systems. A properly integrated IADS with shared radar data, handoff protocols, and coordinated engagement zones would have been far harder to suppress.

**The model**: IADS as a command-and-control overlay on existing air defense units:
- **Layered engagement zones**: Long-range SAMs (SA-5/S-200) provide area denial. Medium-range SAMs (SA-6/SA-11) cover gaps. Short-range AAA/MANPADS provide point defense. Each layer has an engagement envelope (altitude × range).
- **Radar network**: Early warning radars (long range, low resolution) → acquisition radars (medium range, track-quality) → engagement radars (fire-control). Radar handoff passes tracks down the chain. Destroying an early warning radar creates a coverage gap that multiple SAM batteries lose visibility into.
- **IADS command node**: The sector operations center coordinates engagement. Its destruction degrades coordination — SAMs revert to autonomous mode (reduced effectiveness due to shorter detection range from engagement radar only, no pre-cueing from early warning).
- **SEAD degradation**: Each successful ARM strike or physical strike on an IADS component reduces the sector's overall effectiveness. IADS health is a compound metric of radar coverage × SAM availability × command connectivity. Degraded IADS → safer airspace for subsequent strikes.

This directly supports Phase 16's Bekaa Valley validation scenario and Phase 19's AirLand Battle doctrinal school (simultaneous deep/close/rear with SEAD as prerequisite).

### Strategic Targeting & Target-Effect Chains

**The problem**: Currently, combat damage applies only to military units. Destroying a bridge has no effect on logistics. Destroying a power plant has no effect on C2. This disconnects air power from its primary modern role: creating operational effects through strategic targeting.

**The model**: Target-effect chains connecting infrastructure damage to operational consequences:

| Target Type | Immediate Effect | Operational Cascade |
|-------------|-----------------|-------------------|
| Bridge | Structure destroyed | Supply route severed → logistics reroute (Phase 12b) or supply failure |
| Airfield | Runway cratered | Enemy sortie rate reduced proportional to runway capacity loss |
| Power plant | Generation lost | C2 degradation in area (backup generators provide partial capability) |
| Fuel depot | Stored fuel destroyed | Supply crisis for units drawing from that depot |
| Ammo depot | Stored ammo destroyed | Ammunition shortage for nearby units |
| C2 node | HQ destroyed | Command succession cascade (existing Phase 5 mechanics) |
| Factory | Production halted | Supply regeneration rate reduced (Phase 12b production.py) |
| Port | Throughput reduced | Sealift capacity reduced, naval logistics degraded |
| Radar site | Coverage lost | IADS degradation (above) |

**Bomb Damage Assessment (BDA)**: Real air campaigns suffer from inaccurate damage assessment — the historical tendency is to overestimate damage (Gulf War BDA overestimated Iraqi vehicle kills by ~3x). The BDA cycle: strike → assessment sortie or ISR pass → damage estimate with noise (assessed damage = actual damage × assessment_accuracy × lognormal_noise) → re-strike decision if assessed damage < threshold. Inaccurate BDA wastes sorties on already-destroyed targets or prematurely moves on from damaged-but-functional targets.

**Target regeneration**: Damaged targets repair over time. Bridge repair takes days (faster with engineering units). Runway repair takes hours (crater repair teams). Factory rebuild takes weeks. This creates the sustained-campaign dynamic where air power must maintain pressure, not just strike once.

### Air Campaign Management

**The problem**: Aircraft are treated as infinitely available. In reality, sortie rate is constrained by aircraft availability (maintenance reduces fleet by ~20-30%), pilot fatigue (crew rest requirements limit missions/pilot/day), weapons loadout (rearming takes time), and weather (poor weather cancels or degrades sorties).

**The model**:
- **Daily sortie capacity** = available_aircraft × max_sorties_per_aircraft_per_day × mission_capable_rate
- **Pilot fatigue**: Pilots have a maximum sortie rate (typically 1-2/day for combat missions). Exceeding limits degrades performance (hit probability, decision quality). Extended campaigns accumulate fatigue.
- **Weather days**: Sorties cancelled proportional to weather severity. All-weather aircraft (F-15E with LANTIRN, B-2 with JDAM) less affected than fair-weather only.
- **Campaign phasing**: Doctrine determines phase sequence. Warden/USAF doctrine: air superiority → SEAD → strategic targeting → interdiction → CAS. AirLand Battle: simultaneous deep/close. Soviet: air superiority focused on fighter sweep + ground support. Phase 19 doctrinal schools drive campaign phase selection.
- **Attrition dynamics**: Combat losses permanently reduce fleet size. Depot-level repair returns damaged aircraft over time. Replacement aircraft arrive from production (connects to Phase 12b supply regeneration if factories are strategic targets).

### Network-Centric Warfare Extensions

Beyond air campaigns, the audit identified that network-centric warfare — lateral data sharing via tactical data links — is a gap across all domains. Phase 12a addresses this through shared situational awareness (Common Operational Picture via Link 16/FBCB2), network degradation modeling, and joint operations coordination. The key insight: **modern military effectiveness comes from information sharing, not just individual platform capability**. A networked force where every unit shares sensor data is qualitatively different from one where each unit sees only its own sensors. The COP aggregation in Phase 12a is the foundation; IADS integration in Phase 12f is the first domain-specific application (air defense as a sensor network).

### Design Principles

1. **Infrastructure as dual-use entities**: Bridges, power plants, etc. are already terrain features (Phase 1 `terrain/infrastructure.py`). Phase 12f adds health state and damage effects without changing their spatial representation. They remain terrain objects that can also be targeted.
2. **Cascading effects via existing systems**: Bridge destruction feeds into logistics supply network (Phase 12b). C2 node destruction feeds into command succession (Phase 5). No new parallel systems.
3. **Campaign level, not tactical**: Air campaign management operates at operational/strategic tick rate, not per-engagement. Sortie allocation is a planning decision, not a combat resolution detail.
4. **Doctrine-driven**: Campaign phasing and target prioritization are driven by doctrinal school (Phase 19) and commander personality (Phase 8), not hard-coded sequences.

---

## Research Sources

Following the project's tiered source policy:

### Tier 1 (Primary — peer-reviewed, official)
- FM 3-0 Operations, FM 3-90 Tactics, FM 3-09 Fire Support (US Army field manuals)
- FM 3-24 Counterinsurgency (Petraeus/Mattis COIN doctrine — population-centric warfare, insurgency dynamics)
- FM 3-05.130 Army Special Operations Forces Unconventional Warfare (SOF/UW doctrine)
- JP 3-22 Foreign Internal Defense (working through indigenous forces)
- ATP 3-12.3 Electronic Warfare (EW doctrine)
- FM 3-11 CBRN Operations
- JP 3-14 Space Operations (US Joint Publication — space force enhancement, space control, ASAT)
- GPS SPS Performance Standard (GPS ICD-200) — accuracy specifications, DOP definitions
- DoD Law of War Manual (2015, updated 2023) — LOAC compliance framework, proportionality, distinction
- Dupuy, T.N. — *Understanding War* (QJM combat model)
- Hughes, W.P. — *Fleet Tactics and Naval Operations*

### Tier 2 (Secondary — authoritative books, established models)
- Clausewitz, *On War*; Sun Tzu, *The Art of War*; Liddell Hart, *Strategy*
- Boyd, J. — OODA loop papers and briefings
- Lanchester, F.W. — *Aircraft in Warfare* (attrition models)
- Biddle, S. — *Military Power: Explaining Victory and Defeat in Modern Battle*
- Vego, M. — *Joint Operational Warfare*
- Bate, R.R., Mueller, D.D., White, J.E. — *Fundamentals of Astrodynamics* (Keplerian orbits, J2 perturbation)
- Walzer, M. — *Just and Unjust Wars* (just war theory, proportionality, civilian protection — already in brainstorm.md Tier 2)
- Kilcullen, D. — *The Accidental Guerrilla* (modern insurgency dynamics, accidental guerrilla syndrome, COIN population dynamics)
- Kalyvas, S.N. — *The Logic of Violence in Civil War* (violence in civil wars, selective vs indiscriminate violence, civilian collaboration dynamics)
- Galula, D. — *Counterinsurgency Warfare: Theory and Practice* (classic COIN theory, population control, insurgency stages)
- Kahn, H. — *On Escalation: Metaphors and Scenarios* (escalation ladder concept, nuclear escalation theory, threshold dynamics)
- Schelling, T.C. — *Arms and Influence* (coercive diplomacy, escalation dynamics, commitment theory)

### Tier 3 (Tertiary — technical references)
- Pasquill-Gifford atmospheric stability classes (CBRN dispersal)
- Hopkinson-Cranz blast scaling (nuclear effects)
- Cramér-Rao bound (EW direction-finding accuracy)
- McCormick, B.W. — *Aerodynamics, Aeronautics, and Flight Mechanics* (Mach-dependent drag)
- Warden, J.A. — *The Air Campaign* (Five Rings strategic targeting)
- DePuy, W.E. / Starry, D.A. — AirLand Battle doctrine (FM 100-5, 1982/1986 editions)
- Kaplan, E.D. & Hegarty, C.J. — *Understanding GPS/GNSS* (DOP, accuracy models, INS/GPS integration)
- Vallado, D.A. — *Fundamentals of Astrodynamics and Applications* (orbital mechanics, SGP4/TLE reference)
- ICRC IHL Database — International Humanitarian Law treaties and customary law references (treaty compliance modeling)
- Convention on Cluster Munitions (2008), Ottawa Treaty (1997), Chemical Weapons Convention (1993) — treaty text for compliance flags
- Grotius, H. — *De Jure Belli ac Pacis* (foundational law of war — already in brainstorm.md ethics tier)
- Long, A. — *The Soul of Armies* (organizational culture and atrocity, explains why some armies violate LOAC more than others)

---

## 10. Space / Satellite Domain

### Scope & Motivation

Modern warfare is deeply dependent on space-based assets across all four warfighting functions:
- **Intelligence**: Satellite imagery (IMINT), signals intelligence (SIGINT) from orbit, missile launch early warning
- **Navigation**: GPS/GLONASS enabling precision-guided munitions, coordinated maneuver, and accurate indirect fire
- **Communications**: SATCOM for beyond-line-of-sight C2, submarine VLF relay, data link backbone
- **Force protection**: Missile early warning satellites providing time to react to ballistic threats

The MVP treats space as implicit background infrastructure — SATCOM exists as a comm type, precision-guided munitions assume GPS availability, and early warning is abstracted. For a modern-era prototype, this is a significant gap: **degrading or denying space assets fundamentally changes combat outcomes** (GPS denial alone can increase munition CEP by 10-100x).

### Existing Interface Points

The MVP already has hooks that a space domain would modulate:
- `detection/intel_fusion.py` — `IntelSourceType.IMINT` exists but has no satellite-linked source
- `environment/electromagnetic.py` — `gps_accuracy` parameter (currently static)
- `c2/communications.py` — SATCOM comm type in equipment definitions
- `combat/ammunition.py` — `GuidanceType.GPS` on precision munitions
- `combat/missiles.py` — CEP parameter (currently fixed per weapon)
- `combat/missile_defense.py` — Early warning time parameter (currently fixed)

### New Modules (9)

- `space/__init__.py` — Package init
- `space/orbits.py` — Simplified Keplerian orbit propagation: period `T = 2π√(a³/μ)`, ground track computation, J2 nodal precession for sun-synchronous orbits. NOT full SGP4/TLE — sufficient fidelity for "when does this satellite see the theater?" at campaign timescales.
- `space/constellations.py` — Constellation manager: GPS (24-slot MEO), GLONASS (24-slot MEO), imaging (LEO sun-synchronous), SIGINT (LEO/HEO), early warning (GEO/HEO Molniya), SATCOM (GEO). Track coverage windows (revisit time, dwell time over theater bounding box).
- `space/gps.py` — GPS accuracy model: visible satellite count → DOP (dilution of precision) → position error. INS drift model for GPS-denied: `σ(t) = σ₀ + drift_rate × t`. Wire into `environment/electromagnetic.py` `gps_accuracy` and `combat/missiles.py` CEP.
- `space/isr.py` — Space-based ISR: imaging satellites generate detection events during overpass. Resolution determines minimum detectable unit size. Revisit time from orbital period + ground track drift. Cloud cover blocks optical (not SAR). Feeds into `detection/intel_fusion.py`.
- `space/early_warning.py` — Missile early warning: GEO/HEO IR satellites detect missile launches. Detection time from satellite coverage + processing delay. Wire into `combat/missile_defense.py` early warning time parameter.
- `space/satcom.py` — SATCOM dependency model: satellite coverage windows determine when SATCOM is available. Capacity limits (bandwidth per theater). Degradation feeds into `c2/communications.py` reliability for SATCOM equipment.
- `space/asat.py` — Anti-satellite warfare: direct-ascent kinetic kill (Pk from intercept geometry), co-orbital rendezvous, ground-based laser dazzling (temporary vs permanent blinding). Debris generation (Poisson model for collision cascade risk). Satellite loss → constellation degradation → cascading effects on GPS/ISR/SATCOM/early warning.
- `space/events.py` — Space domain events: SatelliteOverpassEvent, GPSDegradedEvent, SATCOMWindowEvent, ASATEngagementEvent, ConstellationDegradedEvent.

### Key Physics

- **Keplerian period**: `T = 2π√(a³/μ)` where μ = 3.986×10¹⁴ m³/s² (Earth). LEO ~90min, MEO ~12hr, GEO ~24hr.
- **Ground track drift**: `Δλ = -(T_orbit/T_earth) × 360°` per orbit. Combined with inclination determines revisit geometry.
- **J2 nodal precession**: `dΩ/dt = -3/2 × J2 × (R_e/a)² × n × cos(i)` — needed for sun-synchronous orbit maintenance.
- **GPS DOP**: Position error = `DOP × σ_range`. DOP depends on satellite geometry (GDOP, PDOP, HDOP, VDOP). Fewer visible satellites → worse geometry → higher DOP.
- **INS drift**: Without GPS correction, position error grows as `σ₀ + drift_rate × t` (linear for tactical INS, ~1 nmi/hr for aviation-grade).
- **ASAT engagement**: Pk from intercept geometry (closing velocity, guidance accuracy, warhead lethal radius). Direct-ascent from ground; co-orbital requires orbit matching maneuver.
- **Debris cascade**: Poisson model — each ASAT kill generates N debris fragments, each with collision probability per orbit for other satellites in similar altitude band.

### Design Principles

1. **Modulation, not duplication**: Space modulates existing parameters (GPS accuracy → CEP, SATCOM availability → comms reliability, ISR overpass → intel events, early warning → reaction time). No parallel systems.
2. **Simplified orbital mechanics**: Keplerian with J2 perturbation, not SGP4/TLE. Sufficient for campaign-scale "when is satellite overhead?" — not precision orbit determination.
3. **Optional by default**: If `space_engine is None`, all systems use current default values. Full backward compatibility with existing scenarios.
4. **No new dependencies**: Orbital math uses existing numpy/scipy (Kepler equation solver via Newton-Raphson).
5. **EW forward-compatible**: GPS jamming/spoofing inputs work with manual configuration now or Phase 16 EW module wiring later. SATCOM jamming similarly.
6. **Campaign-scale resolution**: Satellite overpasses computed at strategic tick rate (3600s), not tactical. Constellation state updated once per strategic tick.

### Validation Approach

- **GPS denial scenario**: Compare PGM accuracy (CEP) with full GPS vs degraded (3 satellites) vs denied (INS-only). Validate against published CEP tables for JDAM (GPS-aided: 13m, INS-only: 30m+).
- **ISR coverage gap exploitation**: Red force moves during imaging satellite gap. Validate that overpass timing matches simplified orbital prediction within ±5 minutes.
- **ASAT escalation scenario**: Kinetic ASAT degrades GPS constellation from 24 to 18 satellites. Validate cascading DOP increase and PGM accuracy degradation.

---

## 11. Deferred Domains & Future Considerations

Items identified during the post-MVP review that don't have dedicated phases but should be tracked.

### SOF / Unconventional Warfare

A `sof_operator` commander profile exists (Phase 8) but no SOF-specific capabilities: behind-lines infiltration, HVT targeting, unconventional warfare (working through indigenous forces), sabotage of infrastructure/logistics, force multiplication effects. **Now addressed in Phase 24** (Unconventional & Prohibited Warfare) — see Section 12 below for design thinking and `development-phases-post-mvp.md` Phase 24c for implementation plan.

### Amphibious Warfare Depth

`combat/amphibious_assault.py` and `movement/amphibious_movement.py` exist but are simplified. Deeper modeling (mine clearance before landing, naval gunfire support coordination with beach assault, combat engineering on beachhead, shore-to-ship defense) would improve Falklands scenario fidelity. Could be folded into Phase 12c (Combat Depth) or addressed when expanding Falklands scenarios.
