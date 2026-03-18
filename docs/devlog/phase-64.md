# Phase 64: C2 Friction & Command Delay

**Status**: Complete
**Tests**: 60 new (6 test files)
**Source files modified**: 4 (zero new source files)

## Overview

Wires four dormant C2 engines into the simulation loop: OrderPropagationEngine, PlanningProcessEngine, ATOPlanningEngine, and StratagemEngine. All behavioral changes are gated by `enable_c2_friction=False` (default from Phase 63). This is Block 7, Phase 7 of 10.

## Implementation

### Step 0: CalibrationSchema Infrastructure (10 tests)

Added 5 new fields to `CalibrationSchema`:
- `planning_available_time_s: float = 7200.0` — planning budget (2hr default)
- `stratagem_concentration_bonus: float = 0.08` — +8% ATTACK decision score
- `stratagem_deception_bonus: float = 0.10` — +10% ATTACK decision score
- `order_propagation_delay_sigma: float = 0.4` — log-normal sigma for delay variation
- `order_misinterpretation_base: float = 0.05` — base misinterpretation probability

All values chosen for realistic defaults; zero behavioral change when `enable_c2_friction=False`.

### 64a: Order Propagation Wiring (11 tests)

**None guards in `propagation.py`** — 3 guards added for `self._command`:
- Authority check skipped when command is None
- Staff effectiveness computation skipped when command is None
- Sender degradation status check skipped when command is None

**battle.py DECIDE handler** — when `enable_c2_friction=True`:
- Creates FRAGO Order, calls `propagate_order()`, logs delay/misinterpretation
- Calibration-to-config forwarding: `order_propagation_delay_sigma` and `order_misinterpretation_base` from CalibrationSchema to PropagationConfig
- Propagation failure causes DECIDE skip (`continue`)

### 64b: Planning Process Wiring (12 tests)

**engine.py** — planning `update()` per strategic tick:
- Auto-advance via `advance_phase()`
- `complete_planning()` called when ISSUING_ORDERS phase reached

**battle.py** — DECIDE gate:
- If planning status is not IDLE or COMPLETE, skip DECIDE
- If IDLE, initiate planning with configurable `planning_available_time_s`
- Method selection: echelon 5 (Company) with 7200s selects RAPID planning

### 64c: ATO Management Wiring (9 tests)

**engine.py** — lazy aircraft registration every strategic tick:
- AIR domain units registered automatically
- Sortie availability logging when `enable_c2_friction` active

**battle.py** — ATO sortie gate in `_route_air_engagement()`:
- `get_available_sorties() <= 0` causes air engagement skip
- Returns `(True, None)` — engagement handled but no result

### 64d: Stratagem Activation Wiring (10 tests)

**Ordering fix** — moved stratagem evaluation BEFORE `decide()` so bonuses flow into `school_adjustments`. Phase 53c placement had stratagems evaluated after decide(), rendering bonuses ineffective.

**Three stratagem types wired**:
- Concentration: compute enemy center of mass, plan + activate, +8% ATTACK bonus via `stratagem_concentration_bonus`
- Deception: feint/main split, plan + activate, +10% ATTACK bonus via `stratagem_deception_bonus`
- Economy of force: last 2 units when 5+ available

### Step S: Structural Verification (8 tests)

Source-level string assertions for all Phase 64 wiring points.

## Files Modified

| File | Changes |
|------|---------|
| `stochastic_warfare/simulation/calibration.py` | 5 new fields (delay sigma, misinterp base, planning time, stratagem bonuses) |
| `stochastic_warfare/c2/orders/propagation.py` | 3 None guards for `_command` in `propagate_order()` |
| `stochastic_warfare/simulation/battle.py` | `_get_unit_position()` helper, order propagation call, planning gate + initiation, stratagem plan+activate with decision score boost (reordered before decide()), ATO sortie gate in air routing |
| `stochastic_warfare/simulation/engine.py` | Planning `update()` + auto-advance per tick, ATO lazy aircraft registration + sortie logging |

## Test Files

| File | Tests |
|------|-------|
| `tests/unit/test_phase_64_infra.py` | 10 |
| `tests/unit/test_phase_64a_order_propagation.py` | 11 |
| `tests/unit/test_phase_64b_planning_process.py` | 12 |
| `tests/unit/test_phase_64c_ato_management.py` | 9 |
| `tests/unit/test_phase_64d_stratagem_activation.py` | 10 |
| `tests/unit/test_phase_64_structural.py` | 8 |

## Design Decisions

1. **Reused `enable_c2_friction` flag** from Phase 63 as master gate for all Phase 64 changes. One flag controls all C2 friction behavior.
2. **`command_engine=None` guard** rather than full CommandEngine instantiation — avoids heavy HierarchyTree + TaskOrgManager dependencies.
3. **Planning auto-advance** without sub-module result injection — timer delay is the key friction; content fidelity deferred.
4. **Stratagem before decide()** — moved stratagem evaluation from after decide() (Phase 53c placement) to before, so bonuses flow into school_adjustments.
5. **Order delay logged, not queued** — no deferred delivery infrastructure; delay value computed but execution proceeds immediately.

## Deviations from Plan

- Plan specified `ato_registration_done` as an internal flag on CalibrationSchema — correctly omitted. Kept as instance-level tracking via engine re-registration each strategic tick instead.
- Postmortem discovered and fixed: stratagem bonus applied after decide() (ordering bug), None position handling in enemy centroid calculation.

## Deferrals

1. **CommandEngine full hierarchy wiring** — authority check skipped when `command_engine=None` (Medium)
2. **Order delay enforcement queue** — delay computed and logged but not enforced; orders execute immediately (High)
3. **Misinterpretation parameter modification** — `was_misinterpreted` logged but order params unchanged (Medium)
4. **Planning result injection** — MDMP auto-advances without COA development or wargaming results (Medium)
5. **ATO entry consumption** — sorties_today never incremented after air engagement; sortie gate never triggers (Medium)
6. **Stratagem duration and expiry** — active stratagems never expire (Medium)
7. **Deception effect on enemy AI** — no false force disposition injected into FOW (Medium)
8. **`echelon_level=5` hardcoded** for all units; should look up actual echelon (Low)
9. **`mission_type=0` (ATTACK) hardcoded** for all orders (Low)
10. **Economy-of-force and feint unit selection** by list position, not tactical criteria (Low)
11. **`_prop_cfg` private attribute mutation** from battle.py for calibration forwarding (Low)

## Postmortem

### Scope: On target (60 tests vs planned ~60)

All 4 planned subsections delivered plus infrastructure and structural verification. No scope creep, no unplanned reductions. One ordering bug (stratagem before decide) discovered and fixed during postmortem.

### Quality: High

- All 60 Phase 64 tests pass
- Calibration coverage test caught `order_propagation_delay_sigma` and `order_misinterpretation_base` as unconsumed — fixed immediately with consumer wiring
- Postmortem caught stratagem ordering bug (bonuses applied after decide consumed school_adjustments)

### Integration: Fully wired

- All 4 engines connected to simulation loop (order propagation, planning, ATO, stratagem)
- All 5 new CalibrationSchema fields consumed
- Master `enable_c2_friction` flag gates all behavioral changes
- Zero new source files — all changes in existing modules

### Deficits: 11 deferrals (see above)

D2 (order delay queue) and D5 (ATO sortie consumption) are the most impactful deferrals. Both represent infrastructure that is structurally wired but not functionally complete — delays are computed but not enforced, sorties are tracked but not consumed.

### Lessons Learned

- **Postmortem catches ordering bugs**: stratagem bonus applied after `decide()` consumed `school_adjustments` — zero gameplay effect until fixed. Always verify data flow ordering, not just data flow existence.
- **None position guard pattern**: `getattr(e, "position", Position(0,0,0))` returns `None` when attribute exists but is `None`. Use `(getattr(e, "position", None) or Position(0,0,0))` instead.
- **Calibration coverage test is invaluable**: immediately caught `order_propagation_delay_sigma` and `order_misinterpretation_base` as unconsumed fields, forcing consumer wiring before commit.
- **Events as observability, not control flow**: All 4 C2 events (PlanningStarted/Completed, ATOGenerated, StratagemActivated) are published but have no production subscribers. This is the project's event architecture pattern — events feed the recorder/narrative, not the control loop.
