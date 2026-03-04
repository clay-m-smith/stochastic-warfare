# Phase 12: Deep Systems Rework

## Summary

Phase 12 resolves 16 MODERATE deficits from the Post-MVP Refinement Index and adds 2 new domains (civilian population, strategic air campaigns/IADS) through 6 sub-phases (12a–12f). All changes follow the backward-compatibility pattern: `enable_*` config flags defaulting to `False`, new parameters with MVP-preserving defaults.

**Test count**: 259 tests (30 + 53 + 22 + 66 + 41 + 47) across 6 test files. Total: 4,077 tests passing (up from 3,818).

**New modules**: 12 new source files (1 in c2/, 1 in logistics/, 7 in population/, 3 in combat/).
**Modified modules**: ~25 existing source files across c2/, logistics/, combat/, morale/, detection/, terrain/, core/.
**No new dependencies.**

## What Was Built

### 12d: Morale & Psychology Depth (30 tests)
1. **Continuous-time Markov morale** (`morale/state.py`): Added `use_continuous_time: bool = False` to `MoraleConfig`. New `compute_continuous_transition_probs(params, dt)` method using `P = 1 - exp(-λ·dt)` for tick-rate-independent transitions. `check_transition()` gained `dt: float = 1.0` parameter; when continuous-time enabled, uses rates instead of probabilities. Also enforced `transition_cooldown_s` which was declared but never checked.
2. **Enhanced PSYOP** (`morale/psychology.py`, `morale/events.py`): New `apply_psyop_enhanced()` method with message_type × target_susceptibility × delivery_method scoring. Added `PsyopAppliedEvent` to events.py, published on EventBus. Config: `message_type_multipliers`, `delivery_method_multipliers`, `training_resistance_weight`. Original `apply_psyop()` preserved unchanged.

### 12a: C2 Depth (53 tests)
1. **Multi-hop message propagation** (`c2/communications.py`): Added `enable_multi_hop: bool = False`, `max_relay_hops: int = 5` to config. Injects optional `hierarchy: HierarchyTree` for relay path finding (LCA algorithm). `_find_relay_path()` returns chain; each hop has independent P(success) and additive delay.
2. **Terrain-based comms LOS** (`c2/communications.py`): Injects optional `los_engine: LOSEngine`. New `_los_factor()` returns 0.0 when `requires_los=True` and terrain blocks LOS; 1.0 otherwise. VHF/UHF/data_link require LOS; HF/satellite/wire unaffected.
3. **Network degradation model** (`c2/communications.py`): Added `enable_network_degradation: bool = False`, congestion params. Tracks per-band bandwidth utilization. `_congestion_factor()`: <50% load = no effect; 50-90% = latency increase; >90% = message loss. Load decays via `exp(-rate * dt)`.
4. **Arbitrary polyline FSCL** (`c2/coordination.py`): Replace east-west midpoint with Shapely `LineString`. `set_fscl()` gained `waypoints: list[Position] | None` for polyline. `is_beyond_fscl()` uses cross-product side-of-line test. Added `FireType.MISSILE` to FSCL gating.
5. **JTAC/FAC observer model** (`c2/coordination.py`): New `JTACObservation` dataclass, `register_jtac()`, `check_cas_feasibility()`. JTAC must have LOS to target; reports position with Gaussian error inversely proportional to range.
6. **JIPTL generation** (`c2/coordination.py`): New `TargetNomination`, `TargetAllocation` dataclasses, `JIPTLConfig`. `submit_target_nomination()`, `generate_jiptl(available_shooters)` → prioritized allocation via greedy assignment.
7. **Network-centric COP** (`detection/fog_of_war.py`): New `DataLinkConfig` with `enable_cop_sharing: bool = False`. `set_data_link_networks()` registers Link 16/FBCB2 memberships. After sensor sweep in `update()`, share contacts laterally among data-linked units with track quality degradation.
8. **Joint Task Force command** (`c2/joint_ops.py`, NEW): `ServiceBranch` enum, `ComponentCommand` enum, `CoalitionCaveat` config. `JointOpsEngine`: register units by service, assign liaisons, register coalition caveats. `get_coordination_modifiers()`: same service = 1.0; cross-service = ×1.5 delay, ×2.0 misinterpret; liaison reduces by 50%. `check_caveat_compliance()` per-nation mission/area restrictions.
9. **ATO planning cycle** (`c2/orders/air_orders.py`): New `ATOPlanningEngine` class with `register_aircraft()`, `submit_request()`, `generate_ato()`. Priority: DCA/CAP first → JIPTL strikes → CAS → remaining. Sortie limits per aircraft, turnaround times, CAS reserve fraction.

### 12b: Logistics Depth (22 tests)
1. **Multi-echelon supply network + infrastructure coupling** (`logistics/supply_network.py`): `SupplyNode` gained `echelon_level`, `infrastructure_id`, `throughput_tons_per_hour`. `SupplyRoute` gained `current_flow_tons_per_hour`, `infrastructure_ids`. Config flags: `enable_capacity_constraints`, `enable_infrastructure_coupling`, `enable_min_cost_flow`. New methods: `sync_infrastructure()`, `find_supply_route_capacity_aware()`, `find_alternate_route()`, `sever_route()`, `compute_network_redundancy()`.
2. **Supply regeneration** (`logistics/production.py`, NEW): `ProductionFacilityConfig` pydantic model, `ProductionEngine` with `register_facility()`, `update()`. Production = rate × condition × dt.
3. **Transport escort effects** (`logistics/transport.py`): `update()` gained `escort_strength: float = 1.0`, `threat_level: float = 0.0`. Per-tick interdiction roll.
4. **Erlang medical service** (`logistics/medical.py`): Added `erlang_shape_k: int = 1` to config. Treatment time: `rng.gamma(k, mean/k)` when k > 1.
5. **Fuel gating wiring** (`simulation/battle.py`): Movement execution queries `ctx.stockpile_manager` for Class III (fuel) and passes `fuel_available` to movement.

### 12c: Combat Depth (66 tests)
1. **Air combat energy-maneuverability** (`combat/air_combat.py`): New `EnergyState` dataclass with `specific_energy = h + v²/2g`. Added `energy_advantage_weight: float = 0.0` to config. `resolve_air_engagement()` gained optional `attacker_energy`/`defender_energy`. Energy advantage modifies Pk: WVR/GUNS full effect, BVR ×0.3 effect, clamped ±0.3.
2. **Naval compartment flooding** (`combat/naval_surface.py`): New `CompartmentConfig` and flooding model. `ShipDamageState` gained `compartment_flooding: list[float]`, `capsized: bool`. Methods: `initialize_compartments()`, `apply_compartment_damage()`, `progressive_flooding()`, `counter_flood()`, `check_capsize()`. `enable_compartment_model: bool = False` preserves MVP.
3. **Submarine geometric evasion + patrol operations** (`combat/naval_subsurface.py`): `SubmarineState`, `GeometricEvasionResult` dataclasses for bearing rate model with thermocline crossing bonus. `PatrolArea`, `PatrolResult`, `SubmarinePatrolConfig` for patrol operations with saturating exponential area coverage and Poisson contact detection.
4. **Mine ship-signature + MCM operations** (`combat/naval_mine.py`): `ShipMineSignature` dataclass for per-type trigger probability matching. `MCMMode` enum, geographic sweep bounding. `update_mine_persistence()` for battery decay. `compute_minefield_density()` for spatial query.
5. **Amphibious operations depth** (`combat/amphibious_assault.py`): `LandingCraft` dataclass, `compute_throughput()`, `check_tidal_window()`, `execute_wave_with_craft()`. `enable_landing_craft_model: bool = False` preserves MVP.

### 12e: Civilian Population & COIN (41 tests)
1. **ModuleId additions** (`core/types.py`): Added `POPULATION` and `AIR_CAMPAIGN` to ModuleId enum.
2. **Package init** (`population/__init__.py`): New package.
3. **Events** (`population/events.py`): `DisplacementEvent`, `CollateralDamageEvent`, `DispositionChangeEvent`, `HumintTipEvent` frozen dataclasses.
4. **Civilian entity manager** (`population/civilians.py`): `CivilianDisposition` IntEnum, `CivilianRegion` dataclass, `CivilianManager` with spatial queries, displacement tracking, collateral tracking, state persistence.
5. **Refugee displacement** (`population/displacement.py`): `DisplacementConfig`, `DisplacementEngine` driving displacement from combat zones with distance falloff. Transport penalty computation.
6. **Collateral damage tracking** (`population/collateral.py`): `CollateralConfig`, `CollateralEngine` with cumulative tracking and escalation threshold.
7. **Civilian HUMINT** (`population/humint.py`): `HumintConfig`, `CivilianHumintEngine` with Poisson tip generation. FRIENDLY pop reports enemies to "blue", HOSTILE warns "red".
8. **Population disposition dynamics** (`population/influence.py`): `InfluenceConfig`, `InfluenceEngine` with Markov chain transitions driven by collateral damage/aid/psyop.
9. **ROE escalation triggers** (`c2/roe.py`): New `evaluate_escalation()` method. Collateral exceeds threshold → automatic ROE tightening (FREE→TIGHT→HOLD).

### 12f: Strategic Air Campaigns & IADS (47 tests)
1. **IADS model** (`combat/iads.py`, NEW): `IadsSector` dataclass with radar handoff chain. `IadsConfig` with handoff timing and autonomous_effectiveness_mult. `IadsEngine`: register_sector(), process_air_track() (radar handoff with timing penalties), compute_sector_health() (radar × SAM × command compound), apply_sead_damage() with stochastic variation.
2. **Air campaign management** (`combat/air_campaign.py`, NEW): `CampaignPhase` IntEnum (AIR_SUPERIORITY → SEAD → INTERDICTION → CAS). `PilotState` fatigue tracking. `AirCampaignEngine`: sortie capacity, pilot fatigue with performance degradation, weather day cancellation, fleet attrition/regeneration.
3. **Strategic targeting** (`combat/strategic_targeting.py`, NEW): `StrategicTarget` with health/repair_rate. `TargetEffectChain` mapping target_type → operational effect. `StrategicTargetingEngine`: TPL generation, strike with cascade to infrastructure/supply, BDA cycle with lognormal overestimate bias (historical ×3), target regeneration.
4. **Strategic infrastructure nodes** (`terrain/infrastructure.py`): Added `HealthState` IntEnum, `PowerPlant`, `Factory`, `Port`, `SupplyDepot` models. Extended `InfrastructureManager` with new collections and `get_feature_condition()` method.

## Design Decisions

1. **Backward-compatibility pattern maintained**: All 12 sub-phases use `enable_*` config flags or default parameter values that preserve MVP behavior. No existing test needed modification except `tests/unit/test_types.py` (added new ModuleId members to expected set).
2. **Population as overlay, not entities**: Civilian population is a terrain-like overlay modulating other systems (detection via HUMINT, logistics via displacement, ROE via collateral), not combat entities in the engagement loop.
3. **IADS as compound health**: Sector effectiveness computed as product of radar coverage × SAM availability × command connectivity — destruction of any component degrades the whole.
4. **BDA overestimate bias**: Historical tendency to overestimate bomb damage (documented ×3 bias) modeled as lognormal distribution centered above true damage.
5. **CivilianDisposition IntEnum**: FRIENDLY=0, NEUTRAL=1, HOSTILE=2. Note: FRIENDLY=0 is falsy — use `is None` checks, not `or` fallbacks.

## Issues & Fixes

1. **NavalGunfireSupportEngine constructor**: Test helper `_make_amphibious_engine` passed wrong keyword argument (`naval_surface_engine=` instead of `indirect_fire_engine=`). Fixed by using `SimpleNamespace` mock.
2. **CivilianDisposition.FRIENDLY falsy**: `disposition or default` always returned default because FRIENDLY=0 is falsy. Fixed with `disposition if disposition is not None else default`.
3. **ModuleId test assertion**: Adding POPULATION and AIR_CAMPAIGN broke `test_types.py::test_all_members` with hardcoded expected set. Fixed by adding new members.

## Known Limitations / Post-MVP Refinements

- No YAML data files for population profiles, IADS sectors, or aircraft availability (structural only)
- COP sharing is lateral within data-link networks only — no hierarchical fusion
- JIPTL uses greedy allocation, not optimal assignment
- Air campaign not wired to ATO planning engine (structural connection deferred)
- No mine warfare campaign-level coordination (mine-laying + MCM are per-operation)
- Patrol operations use simplified Poisson model, not full ASW coordination
- Landing craft model does not include casualty evacuation via ship
- Insurgency dynamics not yet implemented (deferred to Phase 24)
- Supply regeneration production rates are per-facility, not network-optimized

## Lessons Learned

1. **IntEnum zero values are falsy**: Python truthiness means `IntEnum(0)` is falsy. Always use `is None` checks when an enum's first member is 0.
2. **Background agent verification**: Always verify background agent outputs before writing tests that depend on their changes.
3. **Test infrastructure mocks**: `SimpleNamespace` mocks are effective for avoiding heavy dependency chains in test helpers (e.g., mocking the indirect_fire_engine for amphibious tests).
4. **Sub-phase ordering matters**: Implementing 12d (smallest) first builds confidence; 12f (most dependencies) last ensures all foundations are in place.
5. **Parallel implementation effective**: Using background agents for independent combat sub-items (12c-1 through 12c-5) saved significant time.

## Deficits Resolved

| Deficit | Origin | Resolution |
|---------|--------|------------|
| Submarine evasion simplified | Phase 4 | 12c — geometric evasion with bearing rate model |
| Mine trigger lacks ship signature | Phase 4 | 12c — ShipMineSignature per-type trigger matching |
| Naval damage control abstracted | Phase 4 | 12c — compartment flooding model with capsize |
| Air combat lacks energy-maneuverability | Phase 4 | 12c — EnergyState with specific energy advantage |
| Morale Markov discrete-time | Phase 4 | 12d — continuous-time Markov with P = 1 - exp(-λ·dt) |
| PSYOP simplified effectiveness | Phase 4 | 12d — enhanced PSYOP with message×susceptibility×delivery |
| No multi-hop C2 propagation | Phase 5 | 12a — relay chain via hierarchy LCA with per-hop P and delay |
| No terrain-based comms LOS | Phase 5 | 12a — LOSEngine integration for VHF/UHF |
| Simplified FSCL | Phase 5 | 12a — Shapely LineString polyline FSCL |
| No ATO planning cycle | Phase 5 | 12a — ATOPlanningEngine with sortie allocation |
| No JTAC/FAC observer | Phase 5 | 12a — JTAC LOS + position error model |
| No supply optimization solver | Phase 6 | 12b — min-cost flow via networkx |
| No multi-echelon supply chain | Phase 6 | 12b — echelon_level + throughput constraints |
| Simplified transport vulnerability | Phase 6 | 12b — escort effects on convoy survival |
| Medical M/M/c approximate | Phase 6 | 12b — Erlang-k service distribution |
| Fuel gating not wired to stockpile | Phase 11 | 12b — battle.py queries stockpile for Class III |
