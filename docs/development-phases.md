# Stochastic Warfare — Development Phases

## Philosophy
Build the nuts and bolts first. Every phase produces runnable, testable code. Validation via basic Python visualization (matplotlib) throughout. No UI work until the engine is solid.

---

## Phase 0: Project Scaffolding
**Goal**: Establish the project skeleton, tooling, and foundational infrastructure.

- Python package structure (`stochastic_warfare/`)
- Build system (`pyproject.toml`, dependency management)
- Testing framework (pytest)
- Logging framework
- Central RNG manager (seeded numpy Generators, per-subsystem stream forking)
- Coordinate system utilities (geodetic ↔ UTM ↔ ENU via pyproj)
- Base classes / interfaces for simulation entities
- Configuration loading (YAML → pydantic models)
- Simulation clock and tick management
- Basic checkpoint/serialization scaffolding

**Exit Criteria**: Can instantiate the simulation framework, create a seeded RNG, load a YAML config, tick a clock, and serialize/restore state. All tests pass.

---

## Phase 1: Terrain & Spatial Foundation
**Goal**: Build the world the simulation operates in.

- Heightmap / DEM loading and representation (numpy 2D arrays)
- Terrain classification layers (land cover, trafficability, concealment)
- Multi-scale spatial models:
  - Graph-based strategic map (nodes + edges via networkx)
  - Gridded operational/tactical map (hex or raster cells referencing terrain data)
  - Continuous coordinate space for unit-level
- Line-of-sight computation from elevation data
- Terrain-based movement cost calculation
- Basic terrain visualization (matplotlib: elevation heatmaps, LOS plots)

**Exit Criteria**: Can load terrain, compute LOS between two points, calculate movement costs across terrain, and visualize the result. Multi-scale representations are interoperable.

---

## Phase 2: Units & Movement
**Goal**: Put things on the map and make them move.

- Unit base classes (ground, aerial, naval placeholder)
- Unit class hierarchy: armor, infantry, artillery, rotary-wing, fixed-wing (modern era)
- YAML-driven unit type definitions with pydantic validation
- Movement engine:
  - Terrain-dependent speed calculation
  - Stochastic deviation in movement (planned vs actual path)
  - Fatigue accumulation model
  - Formation movement
- Pathfinding (A* or similar, terrain-aware)
- Aerial movement model (altitude, 2.5D terrain interaction)
- Unit state management and serialization
- Visualization: unit positions on terrain, movement paths, formation display

**Exit Criteria**: Can place units on terrain, issue move orders, watch them traverse terrain with realistic speeds and stochastic deviation. Fatigue accumulates. Aerial units move in 2.5D. All state serializable and reproducible from seed.

---

## Phase 3: Detection & Intelligence
**Goal**: Units become aware of each other through realistic sensor models.

- Detection model (signal-in-noise / SNR-based probability of detection)
- Sensor types: visual, thermal, radar, acoustic (parameterized via YAML)
- Terrain and weather effects on detection (concealment, masking)
- Kalman filter-based state estimation (each side's belief about enemy positions)
- Information decay over time (stale intelligence degrades)
- Fog of war as a first-class mechanic (units act on belief state, not ground truth)
- Reconnaissance units with enhanced detection capabilities
- Visualization: detection probability maps, belief state vs ground truth overlay

**Exit Criteria**: Units detect each other probabilistically based on range, terrain, sensor type, and signature. Each side maintains a noisy, decaying belief state. Detection is reproducible from seed.

---

## Phase 4: Combat Resolution
**Goal**: Units engage and the simulation resolves outcomes.

- Probability-of-hit model (range, weapon, skill, target signature, terrain, conditions)
- Damage and lethality model (weapon effects, armor penetration)
- Suppression mechanics (fire volume → suppression state → degraded effectiveness)
- Morale model:
  - Markov chain state transitions (steady, shaken, broken, routed)
  - Stress/fatigue as random walk with drift
  - Cohesion effects (nearby friendly units, leadership)
  - Rally mechanics
- Ammunition consumption tracking
- Combined arms interaction bonuses/penalties
- Engagement sequencing within a tick (event-driven resolution)
- Visualization: engagement outcomes, suppression zones, morale state heatmaps

**Exit Criteria**: Two forces can engage. Hits, damage, suppression, and morale effects resolve stochastically. Combined arms matter. Units rout when morale breaks. Ammo is consumed. All reproducible from seed.

---

## Phase 5: Command & Control
**Goal**: Orders flow through a chain of command with realistic delays and degradation.

- Command hierarchy structure (army → corps → division → brigade → battalion → company)
- Order propagation with time delays
- Communication reliability model (noise/degradation in C2 links)
- OODA loop implementation:
  - Observe: fed by detection/intel system
  - Orient: situational awareness based on belief state
  - Decide: AI decision-making (rule-based initially)
  - Act: order generation and propagation
- Leadership influence radius (morale, cohesion bonuses)
- C2 disruption effects (what happens when a HQ is destroyed)
- Visualization: command hierarchy tree, order propagation timeline, C2 link status

**Exit Criteria**: Orders propagate through chain of command with delays. C2 disruption degrades unit effectiveness. AI can make basic tactical decisions via OODA cycle. Reproducible.

---

## Phase 6: Logistics & Supply
**Goal**: Armies need beans, bullets, and fuel.

- Supply chain as network flow (networkx graph)
- Supply types: ammunition, fuel, food/water, medical, spare parts
- Consumption models per unit type (configurable via YAML)
- Supply depot and forward staging area mechanics
- Transport units (truck convoys, airlift)
- Route-dependent supply throughput (road quality, terrain, distance)
- Supply disruption (interdiction, route destruction, weather)
- Queueing model for supply bottlenecks (medical evacuation, repair depots)
- Effects of supply shortage on unit effectiveness (no ammo → can't fire, no fuel → can't move)
- Visualization: supply network graph, stockpile levels, flow rates, bottleneck identification

**Exit Criteria**: Units consume supplies. Supply flows through a network from depots to front-line units. Interdiction disrupts supply. Units degrade when supplies run out. Reproducible.

---

## Phase 7: Multi-Scale Integration
**Goal**: All systems work together across strategic, operational, tactical, and unit scales.

- Campaign-level tick loop driving operational/tactical sub-simulations
- Strategic map (graph) ↔ tactical map (grid/continuous) transitions
- Force aggregation/disaggregation across scales
- Full scenario loading: terrain + forces + objectives + supply network + intel state
- Campaign-level AI (strategic decision-making)
- Victory conditions and scenario outcome evaluation
- Full checkpoint/replay system validation
- Comprehensive multi-scale visualization

**Exit Criteria**: Can define and run a complete multi-day campaign scenario with full tactical resolution of all engagements, logistics flowing, intel updating, and C2 functioning. Campaign can be checkpointed, restored, and replayed identically from seed.

---

## Phase 8: Validation & Backtesting
**Goal**: Prove the simulation produces realistic results.

- Select historical engagements for backtesting (modern era: 73 Easting, Golan Heights, etc.)
- Build scenario packs from historical data
- Run Monte Carlo validation campaigns
- Compare against historical outcomes (casualty rates, durations, territorial outcomes)
- Identify and document model deficiencies
- Calibrate parameters based on backtest results
- Performance profiling and optimization

**Exit Criteria**: Simulation produces statistically plausible outcomes for at least 2-3 historical scenarios. Model deficiencies are documented. Performance is acceptable for campaign-length runs.

---

## Future Phases (Post-MVP)
These are explicitly deferred until the core engine is validated:
- Full UI (separate language/framework)
- Naval units and naval warfare
- Electronic warfare
- Cyber operations
- Nuclear/WMD modeling
- Multi-player / networked simulation
- Earlier era support (WW2, Napoleonic, etc.)
- Doctrinal AI commanders (Clausewitzian, Sun Tzu, maneuverist, etc.)
- Modding and scenario editor tools
- Performance optimization (Cython, GPU acceleration)
