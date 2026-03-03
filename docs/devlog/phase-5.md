# Phase 5: Command & Control Infrastructure

**Status**: Complete
**Date**: 2026-03-01

---

## Summary

Phase 5 implements the C2 plumbing — orders flow through the chain of command with realistic delays, degradation, and constraints. This is the first phase where units can receive, misinterpret, and execute (or fail to execute) orders. C2 disruption creates real friction: succession delays, communications loss, misinterpreted orders. No AI decision-making (Phase 8) — this phase provides the mechanism, not the brain.

**Test count**: 345 new tests -> 2,115 total (1,770 Phase 0-4 + 345 Phase 5).

## What Was Built

### Step 1: Foundation Types (2 modules)

**`c2/events.py`** — 13 frozen dataclass events covering command status changes, succession, communications, order lifecycle, ROE violations, coordination measures, and initiative actions. All inherit from `Event` with `source=ModuleId.C2`.

**`c2/orders/types.py`** — Base order hierarchy. Enums: `OrderType` (OPORD/FRAGO/WARNO), `OrderPriority` (ROUTINE → FLASH), `OrderStatus` (9-state lifecycle), `MissionType` (18 standard missions). Frozen `Order` base class with 6 subclasses: `IndividualOrder`, `TacticalOrder`, `OperationalOrder`, `StrategicOrder`, `NavalOrder`, `AirOrder`. Mutable `OrderExecutionRecord` tracks lifecycle separately (DD-1: immutable orders + mutable execution tracker).

### Step 2: Command Authority (1 module)

**`c2/command.py`** — 4-state command authority machine: `FULLY_OPERATIONAL → DEGRADED → DISRUPTED → DESTROYED`. Succession on commander loss: finds successor via hierarchy (first child → sibling), log-normal delay, publishes `SuccessionEvent`. Comms loss degrades status; restoration recovers. Authority checks respect OPCON/TACON (grant authority) vs ADCON (does not). Temporal dynamics: succession timer and recovery timer with proper remainder tracking to prevent single-update timing errors.

### Step 3: Communications (1 module + 8 YAML)

**`c2/communications.py`** — Channel reliability as Bernoulli trial: `P(success) = base × env × range × jam × emcon`. EMCON states (RADIATE/MINIMIZE/SILENT): SILENT blocks all emitters, MINIMIZE degrades VHF/HF/UHF. Jamming zones with per-equipment jam resistance. Range factor: linear degradation in final 20% of max range. Messenger latency is distance-based (walking speed).

**8 YAML equipment files**: SINCGARS VHF, Harris HF, FBCB2 data terminal, Link 16, Link 11, SATCOM UHF, VLF receiver, WF-16 field wire. Follows same pydantic-validated loader pattern as sensors/weapons.

### Step 4: Naval C2 (1 module)

**`c2/naval_c2.py`** — Task force hierarchy (TF/TG/TU/TE). Tactical data links (Link 11, Link 16) with participant limits and shared contact picture. Submarine communications: VLF/ELF one-way, SATCOM requires periscope depth. Flagship loss triggers flag transfer with configurable delay.

### Step 5: Orders System (7 modules)

**`c2/orders/individual.py`** — Individual/fire team orders with near-instant propagation (~0.5s). 10 `IndividualAction` types (MOVE_TO, ENGAGE, TAKE_COVER, etc.).

**`c2/orders/tactical.py`** — Squad through battalion. Planning time scales: squad 1min → battalion 2hr. 12 `TacticalMission` types. Includes formation and route waypoints.

**`c2/orders/operational.py`** — Brigade through corps. Planning time scales: brigade 12hr → corps 48hr. 12 `OperationalMission` types. Main effort, supporting efforts, reserve designations.

**`c2/orders/strategic.py`** — Theater/campaign level. Planning time ~7 days. 8 `StrategicMission` types with political constraints.

**`c2/orders/naval_orders.py`** — 12 `NavalMissionType` types (FORMATION_MOVEMENT, ASW_PROSECUTION, STRIKE, CONVOY_ESCORT, BLOCKADE, etc.). Formation ID and engagement envelope fields.

**`c2/orders/air_orders.py`** — 12 `AirMissionType` types (CAS, CAP, STRIKE, SEAD, etc.). ATO structure (`AtoEntry`), ACO measures (`AirspaceControlMeasure`, 9 types), CAS request flow. Airspace deconfliction check function (geometric: position + altitude + time window).

**`c2/orders/propagation.py`** — The heart of C2 friction. Each hop: `delay = base_time(echelon) × type_mult × priority_mult × staff_mult × lognormal`. Misinterpretation: `P = base × (1 + (1-staff_eff)) × (1 + (1-comms_quality))`. FRAGO is 33% of OPORD delay, WARNO is 10%. FLASH priority cuts to 25%.

**`c2/orders/execution.py`** — Full lifecycle tracking: DRAFT → ISSUED → IN_TRANSIT → RECEIVED → ACKNOWLEDGED → EXECUTING → COMPLETED/FAILED/SUPERSEDED. Order expiry, supersession, deviation tracking.

### Step 6: Policy Layer (3 modules)

**`c2/roe.py`** — ROE levels (WEAPONS_HOLD/TIGHT/FREE), target categories (MILITARY_COMBATANT through PROTECTED_SITE), engagement authorization with confidence threshold and civilian proximity check. Area-based ROE overrides.

**`c2/coordination.py`** — 8 coordination measure types (FSCL, CFL, NFA, RFA, FFA, BOUNDARY, AIRSPACE_CORRIDOR, MISSILE_FLIGHT_CORRIDOR). Fire clearance checks: NFA blocks all, RFA requires coordination, FFA clears all. FSCL divides ground-coordinated (short) vs service-coordinated (beyond) fires. Movement clearance with boundary crossing detection.

**`c2/mission_command.py`** — Auftragstaktik vs Befehlstaktik. Autonomy level from C2 style + experience + c2_flexibility + comms_loss_boost. Stochastic initiative decision: `P(act) = autonomy × urgency`. Commander's intent storage. Phase 5 = "should I act?" only; Phase 8 = "what should I do?".

## Design Decisions

1. **DD-1: Immutable Orders + Mutable Execution Tracker** — Orders are frozen dataclasses; execution state tracked separately via `OrderExecutionRecord`. Same pattern as `ContactRecord` wrapping immutable detection results.

2. **DD-2: Communication Channels with Stochastic Reliability** — Bernoulli trial per message: `P(success) = base × env × range × jam × emcon`. Follows SNR probability pattern from detection.

3. **DD-3: Log-Normal Propagation Delays** — Long right tail: most orders near mean, some take much longer (Clausewitzian friction).

4. **DD-4: 4-State Command Authority Machine** — Succession with log-normal delay. During transition, disrupted effectiveness.

5. **DD-5: YAML for Comms Equipment Only** — 8 files. Order templates and ROE are scenario/doctrine-specific (deferred to Phase 8+).

6. **DD-6: Scope Control** — air_orders.py: ATO + ACO + CAS ONLY. coordination.py: data + checks ONLY. mission_command.py: "should I?" ONLY.

## Known Limitations & Deferred Items

- **No multi-hop propagation**: Current model propagates one hop (issuer → recipient). Multi-hop accumulation through full CoC deferred to integration with actual scenario setup.
- **No ATO planning cycle**: ATO structures exist but generation deferred to Phase 9/Future Phases.
- **No terrain-based LOS for comms**: `requires_los` field exists but not checked against terrain.
- **Messenger intercept/casualty**: Messenger comm type exists but has no terrain traversal or intercept risk model.
- **No frequency deconfliction**: Radio equipment can interfere but no frequency assignment model.
- **Simplified FSCL**: Modeled as east-west line (northing threshold). Real FSCL is arbitrary polyline.
- **No joint fires observer**: CAS request exists but no JTAC/FAC observer model.

## Files Created

### Source (18 files)
```
stochastic_warfare/c2/__init__.py
stochastic_warfare/c2/events.py
stochastic_warfare/c2/command.py
stochastic_warfare/c2/communications.py
stochastic_warfare/c2/naval_c2.py
stochastic_warfare/c2/roe.py
stochastic_warfare/c2/coordination.py
stochastic_warfare/c2/mission_command.py
stochastic_warfare/c2/orders/__init__.py
stochastic_warfare/c2/orders/types.py
stochastic_warfare/c2/orders/individual.py
stochastic_warfare/c2/orders/tactical.py
stochastic_warfare/c2/orders/operational.py
stochastic_warfare/c2/orders/strategic.py
stochastic_warfare/c2/orders/naval_orders.py
stochastic_warfare/c2/orders/air_orders.py
stochastic_warfare/c2/orders/propagation.py
stochastic_warfare/c2/orders/execution.py
```

### YAML data (8 files)
```
data/comms/sincgars_vhf.yaml
data/comms/harris_hf.yaml
data/comms/fbcb2_data.yaml
data/comms/link16.yaml
data/comms/link11.yaml
data/comms/satcom_uhf.yaml
data/comms/vlf_receiver.yaml
data/comms/field_wire.yaml
```

### Tests (17 files)
```
tests/unit/test_c2_events.py
tests/unit/test_c2_command.py
tests/unit/test_c2_communications.py
tests/unit/test_c2_naval.py
tests/unit/test_c2_orders_types.py
tests/unit/test_c2_orders_individual.py
tests/unit/test_c2_orders_tactical.py
tests/unit/test_c2_orders_operational.py
tests/unit/test_c2_orders_strategic.py
tests/unit/test_c2_orders_naval.py
tests/unit/test_c2_orders_air.py
tests/unit/test_c2_propagation.py
tests/unit/test_c2_execution.py
tests/unit/test_c2_roe.py
tests/unit/test_c2_coordination.py
tests/unit/test_c2_mission_command.py
tests/integration/test_phase5_integration.py
```

### Other
```
scripts/visualize/c2_viz.py
docs/devlog/phase-5.md
```
