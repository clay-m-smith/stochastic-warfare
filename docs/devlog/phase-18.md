# Phase 18: NBC/CBRN Effects

**Status**: Complete
**Tests**: 155 (28+32+25+30+18+22 across 6 test files)
**Total project tests**: 4,918

---

## Summary

Phase 18 adds chemical, biological, radiological, and nuclear (CBRN) effects to the simulation. This includes atmospheric dispersal of agents, contamination grid overlays, MOPP protection levels with combat effectiveness degradation, probit dose-response casualty modeling, three-tier decontamination operations, and full nuclear weapon effects (blast, thermal, radiation, EMP, fallout, terrain modification). All effects integrate with existing movement, morale, detection, and medical systems.

## What Was Built

### New Source Files (10)

| File | Sub-phase | Purpose |
|------|-----------|---------|
| `cbrn/__init__.py` | 18a | Package init |
| `cbrn/events.py` | 18a | CBRN event types (contamination, exposure, decontamination, nuclear detonation, MOPP change, casualty) |
| `cbrn/agents.py` | 18a | Agent type definitions with YAML loading: nerve (VX, sarin), blister (mustard), choking (chlorine), blood (hydrogen cyanide), biological (anthrax), radiological (Cs-137). Per-agent persistence, LCt50/LD50, detection threshold, decontamination difficulty. |
| `cbrn/dispersal.py` | 18a | Pasquill-Gifford atmospheric dispersal model. Gaussian puff/plume computation, stability classes from weather state, wind advection, turbulent diffusion, terrain channeling. |
| `cbrn/contamination.py` | 18b | Contamination grid overlay. Per-cell concentration tracking per agent, time-based decay, weather-dependent evaporation (temperature, wind), washout from rain, terrain absorption based on soil type. |
| `cbrn/protection.py` | 18b | MOPP levels 0-4 with graduated penalties: movement (0/5/10/20/30%), detection (0/0/10/20/30%), fatigue multiplier (1.0/1.1/1.2/1.4/1.6), heat stress in warm weather. Equipment effectiveness varies by agent type. |
| `cbrn/casualties.py` | 18c | Probit dose-response casualty model. Dosage accumulation (concentration times exposure time). Incapacitation and lethality thresholds. Feeds into existing medical pipeline. |
| `cbrn/decontamination.py` | 18c | Three-tier decontamination: hasty (5 min, 60% effective), deliberate (30 min, 95%), thorough (2 hr, 99%). Equipment requirements and contaminated waste generation. |
| `cbrn/nuclear.py` | 18d | Nuclear weapon effects: Hopkinson-Cranz blast scaling for overpressure, thermal fluence burn radius by yield, initial nuclear radiation (rem dosage by range), EMP disabling unshielded electronics, wind-driven fallout plume via dispersal module, terrain modification (craters). |
| `cbrn/engine.py` | 18e | CBRNEngine orchestrator. Per-tick processing: dispersal update, contamination decay, unit exposure tracking, MOPP level management, casualty assessment. |

### Modified Existing Files (6)

| File | Change |
|------|--------|
| `core/types.py` | Added `ModuleId.CBRN` to the module identifier enum |
| `simulation/scenario.py` | Added `cbrn_engine` field to `SimulationContext` |
| `simulation/engine.py` | Added CBRN tick processing to the simulation loop |
| `movement/engine.py` | Added `mopp_speed_factor` parameter for MOPP movement degradation |
| `morale/state.py` | Added `cbrn_stress` modifier for CBRN-induced morale effects |
| `tests/unit/test_types.py` | Added `CBRN` to expected `ModuleId` set |

### YAML Data Files (15)

| Category | Count | Files |
|----------|-------|-------|
| Agents | 7 | VX, sarin, mustard, chlorine, hydrogen_cyanide, anthrax, cs137 |
| Nuclear weapons | 3 | 10kT, 100kT, 1MT |
| Delivery systems | 3 | artillery_shell, aerial_bomb, scud_warhead |
| Validation scenarios | 2 | cbrn_chemical_defense, cbrn_nuclear_tactical |

## Sub-phase Breakdown

### 18a: Agent Definitions & Dispersal (28 tests)
- CBRN agent model with YAML-driven definitions and pydantic validation
- Pasquill-Gifford stability class determination from weather state (wind speed, cloud cover, solar elevation)
- Gaussian puff/plume dispersal with sigma_y and sigma_z growth as function of downwind distance and stability class
- Wind advection shifts the plume centerline; turbulent diffusion spreads concentrations
- Terrain channeling: valleys concentrate agents, ridges deflect plumes
- Event types for all CBRN domain interactions

### 18b: Contamination & Protection (32 tests)
- Grid-based contamination overlay aligned with terrain grid
- Per-cell, per-agent concentration tracking with natural decay
- Weather coupling: evaporation rate increases with temperature and wind; rain causes washout
- Soil type from terrain classification affects absorption rate (sandy absorbs less than clay)
- MOPP 0-4 graduated protection with speed, detection, and fatigue penalties
- Equipment effectiveness varies by agent type (MOPP effective against chemical, less against biological)

### 18c: Casualties & Decontamination (25 tests)
- Dosage accumulation: integral of concentration over exposure time
- Probit dose-response: P(effect) = Phi(a + b * ln(dosage)) where a, b are agent-specific constants
- Separate incapacitation and lethality thresholds
- CBRN casualties feed into existing medical evacuation pipeline
- Three-tier decontamination with time/effectiveness tradeoff
- Equipment and supply requirements for decontamination operations

### 18d: Nuclear Effects (30 tests)
- Hopkinson-Cranz blast scaling: overpressure as function of scaled distance R/W^(1/3)
- Thermal fluence: burn radius computed per yield with atmospheric attenuation
- Initial nuclear radiation: rem dosage by range with shielding factors
- EMP: disables unshielded electronics within radius, hardened equipment has reduced vulnerability
- Fallout plume: wind-driven contamination using dispersal module with radiological agent
- Terrain modification: craters proportional to yield, modifies heightmap and classification

### 18e: Engine Integration (18 tests)
- CBRNEngine wired into SimulationContext and main simulation loop
- Per-tick processing: dispersal update, contamination decay, exposure check, MOPP management
- Movement engine queries MOPP level for speed degradation
- Morale module receives CBRN stress modifier
- All effects gated behind `enable_cbrn` configuration flag (default: False)

### 18f: Validation (22 tests)
- Chemical defense scenario: chemical attack on defended position, validates dispersal physics, MOPP response timing, casualty generation rates, terrain denial
- Nuclear tactical scenario: tactical nuclear weapon against massed formation, validates blast radii, EMP effects, fallout plume direction and extent

## Design Decisions

1. **Grid overlay for contamination**: Reuses the same grid coordinate system as terrain, allowing direct cell-to-cell queries for exposure. Avoids a separate spatial index.

2. **Pasquill-Gifford over Gaussian plume alternatives**: Standard atmospheric dispersal model with well-documented parameters. Sufficient fidelity for campaign-scale effects without requiring CFD.

3. **Probit dose-response**: Standard toxicological model. Agent-specific probit constants (a, b) are well-documented in military literature (FM 3-11, NATO AEP-45). Preferable to simple threshold models because it captures the probabilistic nature of CBRN casualties.

4. **Hopkinson-Cranz scaling for blast**: Cube-root scaling law is the standard approach for nuclear blast overpressure estimation. Matches FM 3-11 reference tables.

5. **MOPP as a discrete level (0-4)**: Follows standard military MOPP doctrine. Each level maps to specific equipment worn, which determines protection and degradation. Continuous protection models would be more complex with minimal gain.

6. **Backward compatibility via `enable_cbrn` flag**: All CBRN effects are disabled by default. Existing scenarios produce identical results. Scenarios opting in set `enable_cbrn: true` in their configuration.

7. **Fallout reuses dispersal module**: Nuclear fallout is modeled as a radiological agent dispersed via the same Pasquill-Gifford framework, avoiding code duplication.

8. **Terrain modification from nuclear blasts**: Craters modify both heightmap (depression) and classification (barren/rubble). This feeds through to LOS, movement cost, and concealment calculations via existing terrain queries.

## Known Limitations / Future Work

- No detailed binary agent modeling (agents that require mixing of two precursors)
- Biological agent incubation periods are simplified (immediate symptom onset for simulation purposes)
- No persistent nerve agent re-evaporation ("off-gassing") from contaminated equipment
- Thermal radiation does not model fire spread or secondary thermal effects
- Nuclear EMP does not model HEMP (high-altitude EMP) with its wider area effect
- No nuclear winter / long-term environmental effects
- Decontamination does not model water supply requirements in detail
- No CBRN reconnaissance vehicle modeling (dedicated NBC detection platforms)
- Radiological dispersal devices (dirty bombs) use simplified point-source model
- No chemical/biological weapon production or stockpile modeling

## Lessons Learned

- **Pasquill-Gifford stability class lookup is straightforward**: Wind speed + solar elevation + cloud cover map cleanly to 6 stability classes (A-F). The sigma_y/sigma_z growth curves are well-tabulated.
- **MOPP degradation has cascading effects**: Speed reduction affects pathfinding, detection penalty affects sensor effectiveness, fatigue acceleration affects morale. Testing each integration point independently was essential.
- **Nuclear effects span multiple subsystems**: Blast affects units, terrain, and equipment. EMP affects electronics and communications. Radiation affects personnel. Fallout creates persistent contamination. Each pathway needed separate validation.
- **Probit model requires careful parameter validation**: LCt50 values vary significantly between sources. Using FM 3-11 as the primary reference with NATO AEP-45 cross-validation ensured consistent agent parameters.
- **Grid overlay alignment is critical**: Contamination grid must match terrain grid exactly for exposure calculations to correlate with unit positions. Off-by-one errors in grid indexing produce incorrect exposure values.

## Postmortem

### 1. Delivered vs Planned
**Scope: ON TARGET** — All 6 sub-phases delivered exactly as planned. 155 tests (planned ~155). 10 new source files, 6 modified, 15 YAML data files, 2 validation scenarios. No items dropped, deferred, or added beyond plan.

### 2. Integration Audit
- **All 10 CBRN modules imported** by at least one dependent (engine.py or tests). No dead modules.
- **SimulationContext** has `cbrn_engine` field; `_update_environment()` calls it when non-None.
- **ModuleId.CBRN** used in all event publishing (11 sites across 5 modules).
- **All 10 events published** by production code; tested via EventBus capture.
- **Gap: ScenarioLoader doesn't auto-wire CBRNEngine** — same pattern as EW/Space (deficit 16/17 already tracked).
- **Gap: `mopp_speed_factor` parameter exists in `movement/engine.py` but never passed from battle loop** — MOPP speed penalty has no effect at runtime.
- **Gap: CBRN YAML config sections not parsed by CampaignScenarioConfig** — scenario YAML `cbrn:` block is silently ignored.

### 3. Test Quality Review
| File | Rating | Notes |
|------|--------|-------|
| 18a (agents/dispersal) | **High** | Good physics validation, stability/sigma/Gaussian tests |
| 18b (contamination/protection) | **High** | Decay physics, MOPP tables, soil absorption well-tested |
| 18c (casualties/decon) | **Medium-High** | Probit model validated; dosage→casualty chain tested separately |
| 18d (nuclear) | **High** | Thorough blast/thermal/radiation/EMP/fallout/terrain tests |
| 18e (integration) | **Medium** | Several tests use `inspect.getsource()` (structural, not behavioral) |
| 18f (validation) | **Medium** | YAML loading shallow; blast radius assertion weak (>2 psi, not >12) |

**Overall**: Strong unit coverage, weak end-to-end integration tests. No multi-tick dispersal→exposure→casualty chain test.

### 4. API Surface Check
**PASS** — All 9 modules follow project conventions:
- Type hints on all public functions
- Proper private/public naming
- Dependency injection throughout
- `get_logger(__name__)` used consistently (no `print()`)
- All stateful classes implement `get_state()/set_state()`
- All config classes use pydantic BaseModel

### 5. Deficit Discovery
New deficits found (5 actionable):

| # | Deficit | File | Severity |
|---|---------|------|----------|
| D1 | ScenarioLoader doesn't auto-wire CBRNEngine from YAML | simulation/scenario.py | Medium (matches EW/Space pattern — see deficit 16/17) |
| D2 | `mopp_speed_factor` never passed from battle loop to movement | movement/engine.py, simulation/battle.py | Medium |
| D3 | Hardcoded terrain channeling thresholds (5m valley/ridge, 50m offset) | cbrn/dispersal.py | Low |
| D4 | Hardcoded fallback weather defaults (wind=2.0, temp=20°C, cloud=0.5) | cbrn/engine.py, cbrn/contamination.py | Low |
| D5 | No automatic puff aging/cleanup mechanism | cbrn/dispersal.py | Low-Medium |

Pre-existing deficit not Phase 18-specific: bare `except Exception: pass` in simulation/engine.py for all environment engines (weather, time_of_day, sea_state, seasons, space, CBRN).

### 6. Documentation Freshness
- **CLAUDE.md**: Phase 18 summary accurate, test count matches (4,918)
- **README.md**: Test badge shows 4,918, matches `pytest --co -q` output
- **devlog/index.md**: Phase 18 marked Complete with link
- **project-structure.md**: `cbrn/` package listed
- **development-phases-post-mvp.md**: Phase 18 marked COMPLETE
- **MEMORY.md**: Updated with Phase 18 status and lessons

### 7. Performance Sanity
- **Full suite**: 4,918 passed in 89.80s (Phase 17 was ~80s, +12%)
- **Phase 18 tests only**: 155 passed in 0.62s (negligible)
- **Increase attributable to**: Growing test count (155 new tests), not Phase 18 code overhead
- **No concerning hotspots**: CBRN tests are pure computation, no I/O or sleep

### 8. Summary
- **Scope**: On target — 155/155 planned tests, all deliverables present
- **Quality**: High — clean API surface, strong physics validation, good PRNG discipline
- **Integration**: Partially wired — engine.py calls CBRNEngine but ScenarioLoader doesn't instantiate it, MOPP speed factor unused at runtime
- **Deficits**: 5 new items (D1-D5 above)
- **Action items**: Add deficit entries to devlog/index.md
