# Stochastic Warfare — Brainstorm & Domain Decomposition

## Simulation Scales (Layered Architecture)

### 1. Campaign Level (Strategic)
- Theater-wide resource allocation, supply lines, reinforcement scheduling
- Attrition models over time (Lanchester models as a starting point?)
- Strategic decision trees / game-theoretic opponent modeling
- Terrain and geography at macro scale (regions, fronts, LOCs)

### 2. Battlefield Level (Operational)
- Force disposition and maneuver across a battlefield
- Combined arms interactions
- Objective control, flanking, envelopment
- Fog of war / information asymmetry modeling

### 3. Battle Level (Tactical)
- Engagement resolution between formations
- Fire-and-maneuver sequencing
- Morale, suppression, cohesion effects
- Cover, concealment, line-of-sight

### 4. Unit Level (Individual/Squad)
- Individual or small-group behavior
- Weapon accuracy, rate of fire, ammunition
- Fatigue, injury, skill levels
- Micro-terrain interaction

---

## Stochastic & Signal Processing Models (Core Engine Ideas)

### Random Process Models
- **Markov Chains**: State transitions for unit morale, readiness, engagement status
- **Poisson Processes**: Event arrivals (reinforcements, supply deliveries, random encounters)
- **Gaussian/Shot Noise**: Weapon accuracy, dispersion patterns, sensor noise
- **Brownian Motion / Random Walks**: Unit drift in movement under uncertainty
- **Queueing Theory**: Supply chain bottlenecks, medical evacuation, repair depots

### Signal Processing Analogies
- **Kalman Filtering**: Intelligence estimation — tracking enemy positions with noisy observations
- **Monte Carlo Methods**: Outcome probability estimation for engagements
- **Spectral Analysis**: Analyzing periodicity in operational tempo
- **Convolution**: Modeling cascading effects (suppression spreading through a formation)
- **Matched Filtering / Detection Theory**: Reconnaissance and detection modeling (SNR-based detection probability)

### Optimization
- **Linear/Nonlinear Programming**: Optimal resource allocation (ammo, fuel, troops)
- **Stochastic Optimization**: Decision-making under uncertainty
- **Graph Theory / Network Flow**: Supply line optimization, movement planning
- **Game Theory**: Adversarial decision modeling

---

## Key Domain Systems to Model

### Combat Resolution
- Probability-of-hit models (range, weapon, skill, conditions)
- Damage / lethality models
- Suppression and morale effects
- Armor penetration / protection

### Movement & Maneuver
- Terrain-dependent movement rates
- Formation movement with stochastic deviation
- Pathfinding under uncertainty (fog of war)
- Fatigue accumulation

### Logistics & Supply
- Supply chain as a network flow problem
- Consumption rates (ammo, fuel, food, medical)
- Stockpile management and forward staging
- Disruption modeling (interdiction, weather)

### Command & Control (C2)
- Order propagation delays
- Communication reliability (noise model)
- Decision-making AI for autonomous units
- Chain of command and delegation

### Intelligence & Reconnaissance
- Detection as a signal-in-noise problem
- Information decay over time
- Fog of war implementation
- Deception and counter-intelligence

### Terrain & Environment
- Hex grid vs continuous space vs hybrid
- Elevation, vegetation, urban, water
- Weather effects on movement/combat/visibility
- Day/night cycle
- Urban/suburban/rural spectrum: density, building types, infrastructure quality
- Infrastructure networks: roads, bridges, rail, utilities — function as terrain features AND logistical assets
- Civilian population: density and disposition (friendly/neutral/hostile) — affects ROE, logistics, intelligence, morale

### Morale & Human Factors
- Unit cohesion as a state variable
- Stress/fatigue accumulation (random walk with drift)
- Rout/rally mechanics
- Leadership influence radius

---

---

## Military Theorist Foundations

### Purpose
- Ground modeling decisions in established military theory — not just engineering intuition
- Validate that simulation dynamics capture the right phenomena
- Future feature potential: AI commanders operating according to doctrinal schools

### Key Thinkers & Their Relevance to the Engine

| Thinker | Key Concepts | Engine Relevance |
|---|---|---|
| **Sun Tzu** | Deception, intelligence, terrain taxonomy, morale | Intel/recon system, terrain classification, morale model |
| **Clausewitz** | Friction, fog of war, center of gravity, culminating point | Stochastic deviation models, fog of war mechanic, campaign-level objectives |
| **Jomini** | Interior/exterior lines, concentration of force, LOCs | Movement/maneuver, logistics network modeling |
| **Lanchester** | Mathematical combat models (square/linear laws) | Combat resolution baseline, attrition modeling |
| **Mahan** | Sea power, naval logistics, chokepoints, command of the sea | Naval warfare, SLOC control, maritime logistics, chokepoint modeling |
| **Corbett** | Maritime strategy, fleet-in-being, sea control vs sea denial | Naval campaign modeling, maritime strategy AI, blockade mechanics |
| **Gorshkov** | Soviet naval strategy, balanced fleet, sea denial | Asymmetric naval strategy, submarine warfare doctrine |
| **Wayne Hughes** | Fleet tactics, salvo model (missile exchange) | Naval surface combat resolution, anti-ship missile modeling |
| **Douhet** | Strategic air power, command of the air | Air superiority modeling, strategic bombing |
| **Liddell Hart** | Indirect approach, expanding torrent, maneuver warfare | AI maneuver doctrine, operational planning |
| **Fuller** | Mechanized warfare, combined arms | Combined arms interaction rules |
| **Boyd** | OODA loop | C2 cycle modeling: sensor → processing → decision → order propagation |
| **Warden** | Five rings (strategic targeting) | Target prioritization for strategic/air campaigns |

### Philosophers, Historians & Political Theorists

| Thinker | Key Concepts | Engine Relevance |
|---|---|---|
| **Thucydides** | Realism, state behavior, escalation dynamics | Campaign-level decision modeling, escalation mechanics |
| **Machiavelli** | Political-military nexus, fortune vs preparation | Strategic AI decision-making, contingency planning |
| **Grotius/Vattel** | Laws of war, just war theory, proportionality | ROE system, engagement constraints, civilian protection |
| **Walzer** | Just and unjust wars, civilian distinction, moral constraints | ROE modeling, civilian casualty tracking, ethical constraints on targeting |
| **Kant** | Ethical constraints on state violence | Framework for modeling political constraints on military operations |
| **Hobbes** | Security dilemma, rationale for organized force | Strategic-level modeling of conflict initiation and escalation |

### Doctrinal AI (Future Feature)
- AI commanders operating according to specific doctrinal schools
- e.g. Clausewitzian AI (seek center of gravity) vs Sun Tzu AI (deception + intel advantage) vs maneuverist AI (tempo + indirect approach)
- Enables comparative analysis of doctrinal effectiveness in simulated scenarios

---

## Technical Architecture Questions (To Discuss)
- Event-driven vs tick-based vs hybrid simulation loop?
- Spatial representation: hex grid, continuous 2D, or layered?
- Data-driven unit definitions (YAML/JSON) vs code?
- How to handle multi-scale interaction (strategic events triggering tactical battles)?
- Serialization / save-state for long campaigns?
- Headless simulation first, UI later?
- What historical era(s) to target first for prototyping?

---

## Architecture Decisions

### 1. Simulation Loop — HYBRID
- **Tick-based outer loop** at variable resolution depending on the scale being analyzed
  - Strategic/campaign layer: coarser ticks (hours/days)
  - Tactical/battle layer: finer ticks (seconds/minutes)
  - User controls the analysis scale, and tick resolution scales accordingly
- **Event-driven resolution within ticks** for discrete interactions (engagements, arrivals, detections)
- **Rationale**: Purely event-driven is too coarse even at strategic scale — logistics movements, convoy tracking, and supply chain state need continuous tracking (a convoy interdicted mid-route vs. one that arrives are fundamentally different outcomes). Hybrid lets us scale resolution up and down based on what the user is analyzing while maintaining fidelity where it matters.
- Tick-based backbone ensures nothing "falls through the cracks" between events

### 2. Spatial Representation — LAYERED HYBRID
- **Strategic (graph-based)**: Regions as nodes, routes/corridors as edges. Nodes carry aggregate terrain properties (mountainous, forested, road quality). Natural fit for network flow logistics and strategic movement.
- **Operational/Tactical (gridded — hex or raster)**: Cells reference heightmap and terrain classification layers. Supports LOS, fire arcs, movement cost calculations.
- **Unit level (continuous)**: Real (x, y, z) coordinates. Interpolated elevation, vector micro-terrain features (buildings, walls, treelines).
- **Aerial units**: 2.5D model — 2D heightmap + altitude as a unit property. Aircraft care about altitude-relative-to-ground (terrain masking, SAM envelopes), not full 3D voxels. Keeps it efficient.
- **Transitions**: User zooms into a region/hex to resolve at finer granularity; the system loads the appropriate spatial model for that scale.

### 2a. Coordinate System — ENU / UTM (not geodetic)
- **Internal simulation math runs in a local Cartesian frame** (ENU or UTM-projected), not geodetic (lat/lon)
- Distances in meters, Euclidean geometry, linear algebra — no spherical math overhead
- Geodetic (WGS84 lat/lon) used only for: scenario definition, real-world data import, map visualization/export
- **Projection workflow**: scenario defines geographic origin → terrain & positions projected to local Cartesian at load → all sim math in Cartesian → convert to geodetic only for display
- **UTM as baseline projection**: military standard, maps to MGRS, handles operational/campaign scale well. `pyproj` for conversions.
- **Local ENU refinement**: for tactical/unit-level precision within a UTM zone
- **Campaign-scale caveat**: continental theaters may tile multiple UTM zones or local frames with known transforms. Single-origin distortion is ~0.004% at 500km — within simulation noise for most purposes.
- 2.5D: altitude stored as a unit property (for aerial) and as heightmap values (for terrain), both in meters above reference

### 2b. Terrain Data Model
- **Elevation**: Heightmaps / Digital Elevation Models (DEMs) — 2D arrays where each cell stores elevation. Industry standard in GIS and military sim. Freely available real-world data (SRTM, ASTER) at ~30m resolution. `numpy` native.
- **Classification layers**: Stacked attribute channels per cell — land cover (forest, urban, open, marsh, water), road networks, concealment, trafficability. Multi-channel approach, like image data.
- **Micro-terrain**: Vector features (shapely polygons) for building footprints, walls, treelines at unit-level scale.
- **Derived products**: Slope, aspect, LOS, watersheds computed from elevation math. Military terrain analysis (OCOKA) maps naturally onto this.
- **Multi-scale terrain**: Strategic nodes carry aggregate terrain summaries; tactical grid cells carry full heightmap + classification; unit-level interpolates heightmap and uses vector features.
- **Libraries**: `numpy` (heightmap math, LOS raycasting), `scipy.ndimage` (terrain analysis), `rasterio` (real-world GIS import), `shapely` (vector micro-terrain)

### 7. Prototype Era — MODERN (Cold War – Present)
- Modern era exercises all subsystems: combined arms, air power, radar/sensors, guided weapons, EW, complex logistics
- Best documentation and data availability for backtesting and validation
- Building for modern complexity first means scaling back to earlier eras (WW2, Napoleonic, etc.) is a matter of removing/simplifying layers rather than adding them
- Earlier eras remain targets for future support and historical campaign validation

### 6. Development Approach — HEADLESS ENGINE FIRST
- Pure Python simulation engine with no UI dependency
- Basic Python visualization (matplotlib, simple plots) for validation and debugging during development
- Full UI is a separate future effort in another language/framework
- Engine exposes clean APIs that a UI layer can consume later
- This keeps the core testable, portable, and focused

### 5. Serialization & Save-State — CHECKPOINT + DETERMINISTIC REPLAY
- **Deterministic simulation**: fixed PRNG seed + initial state + user inputs = perfectly reproducible run
- **No need for per-tick snapshots**: replay from nearest checkpoint using saved PRNG state
- **Periodic checkpoints at natural boundaries**: campaign tick boundaries, before/after tactical engagements, user-triggered saves
- Each checkpoint = full state snapshot + PRNG state at that point
- To inspect any moment: replay forward from nearest prior checkpoint (fast, small window)
- **PRNG discipline requirements**:
  - All randomness through seeded `numpy.random.Generator`, never `random.random()` or system entropy
  - **Dedicated PRNG streams per subsystem** (combat, movement, intel, morale) forked from master seed — prevents cross-subsystem sequence contamination
  - Deterministic iteration order — no unordered sets/dicts driving sim logic
  - Single-threaded simulation core (parallelism only for independent sub-sims with own PRNG forks)
  - No timing-dependent behavior in the deterministic path
- **Serialization**: `numpy.random.Generator.bit_generator.state` captures exact PRNG state as a dict. `pickle`/`msgpack` for fast state serialization; `h5py`/`zarr` if state grows large.
- **User input log**: all external decisions (orders, setting changes) timestamped and stored alongside checkpoints for full replay fidelity

### 4. Multi-scale Interaction — FULL TACTICAL RESOLUTION ALWAYS
- **Every engagement runs through the full tactical simulation layer**, regardless of what scale the user is analyzing
- Fidelity is never sacrificed — the simulation doesn't skip steps or hand-wave outcomes
- **Visibility vs fidelity**: if the user is focused on strategic/logistical analysis, tactical battles still run under the hood; the user sees aggregated results. All detailed data is retained and available for drill-down.
- **Auto-resolve as optional performance mode**: user can toggle for fast campaign previews, with the understanding that accuracy is traded for speed. Not the default.
- **Interface contract**: campaign layer provides inputs (forces, terrain, objectives, intel state) → tactical layer runs full resolution → returns outputs (casualties, ammo/fuel consumed, territory, time elapsed, unit states) → campaign layer integrates results
- **Campaign tick may spawn tactical sub-simulations**, run them, collect results, resume
- **A priori intelligence**: before contact, each side maintains an estimated belief state of the enemy (positions, strength, composition) based on available intel sources (radar, recon, SIGINT, satellites, doctrinal assumptions). This belief state drives pre-contact decisions and may be inaccurate — fog of war as a real mechanic, not a visibility toggle.
- Connects to Kalman filter model: belief state updated by noisy observations from sensor/intel assets

### 3. Unit Definitions — DATA-DRIVEN (YAML + Pydantic)
- **Engine defines broad unit classes** (armor, infantry, rotary-wing, fixed-wing, artillery, etc.) that encode behaviors and interaction rules in Python
- **YAML config files parameterize specific unit types** within those classes (M1A2 Abrams is an instance of the armor class with specific speed, protection, weapons, etc.)
- Adding new unit types or eras = adding YAML files, no code changes
- **Pydantic models** validate YAML at load time — enforces required fields, value ranges, type correctness
- Scenario packs = a folder of unit definition YAMLs + map data, portable and version-controllable
- Unit class hierarchy and detailed field specs to be designed when implementation begins
- User has additional unit-side ideas to incorporate at implementation time

### 2c. Aerial Units — Scope Confirmation
- Aerial units are in scope and essential across all simulation layers
- Strategic: airlift, strategic bombing, air superiority campaigns
- Operational: CAS, interdiction, battlefield air recon
- Tactical: close air support integration, helicopter operations
- Unit: individual aircraft behavior, weapon delivery, evasion
- Air defense networks modeled as detection/engagement envelopes in 2.5D

---

## Potential Python Libraries
- `pyproj` — coordinate system transforms (geodetic ↔ UTM ↔ ENU)
- `numpy` / `scipy` — core math, distributions, signal processing
- `networkx` — graph/network modeling (supply lines, C2)
- `simpy` — discrete event simulation
- `shapely` / `geopandas` — spatial/terrain modeling (if continuous)
- `pygame` / `pyglet` — simple 2D visualization (early prototyping)
- `pydantic` — data validation for unit/scenario definitions
- `h5py` / `zarr` — efficient state serialization for large simulations
