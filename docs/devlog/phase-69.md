# Phase 69: C2 Depth

**Status**: Complete
**Block**: 8 (Consequence Enforcement & Scenario Expansion)
**Tests**: 41 new (5 test files)

## Summary

Phase 69 makes the C2 chain produce real effects: ATO limits air tempo, planning results influence AI decisions, deception injects phantom contacts, command hierarchy enforces authority, and burned zones reduce concealment.

## What Was Built

### 69e: Burned Zone Concealment
- `_compute_terrain_modifiers()` now queries `incendiary_engine.get_burned_zones()`
- Units inside a burned zone have concealment reduced by `zone.concealment_reduction`
- Multiple overlapping zones stack reductions (additive, floored at 0.0)
- Gated by presence of `incendiary_engine` (implicitly by `enable_fire_zones`)

### 69a: ATO Sortie Consumption
- `ATOPlanningEngine.record_sortie(unit_id, end_time_s)` increments `sorties_today` and sets `last_sortie_end_time_s`
- `ATOPlanningEngine.reset_daily_sorties(current_time_s)` resets all aircraft sortie counts
- `get_state()`/`set_state()` checkpoint the `_aircraft` dict
- After air engagement routing in `battle.py`, `record_sortie()` is called for the attacker
- In `engine.py`, daily reset at day boundary via `int(time / 86400)` comparison
- Gated by `enable_air_routing` flag

### 69b: Planning Result Injection
- `PlanningProcessEngine.get_planning_result(unit_id)` returns posture string if planning is COMPLETE
- `PlanningProcessEngine.consume_result(unit_id)` returns and clears the result (one-shot)
- Auto-generated COA: when `complete_planning()` is called and `selected_coa` is None, defaults to `"ATTACK"`
- In DECIDE phase: consumed result boosts matching posture in `school_adjustments` by 0.10
- Gated by `enable_c2_friction` flag

### 69c: Deception & FOW Injection
- `FogOfWarManager.deploy_decoy()`, `get_active_decoys()`, `update_decoys()` passthrough to internal `DeceptionEngine`
- Deception stratagem activation deploys `deception_phantom_count` (default 3) phantoms at random offsets near feint units
- OBSERVE phase: active decoys inflate `enemy_power` in assessment (one phantom = one additional enemy unit)
- Decoys degrade over time via `update_decoys(dt)` called each tick in the battle loop
- Gated by `enable_fog_of_war` flag

### 69d: Command Hierarchy Enforcement
- `enable_command_hierarchy` CalibrationSchema field (default `False`)
- When enabled, `scenario.py` builds `HierarchyTree` from `units_by_side`: virtual HQ per side at DIVISION echelon, each unit as COMPANY child
- `TaskOrgManager` wraps the hierarchy with default ORGANIC relationships
- `CommandEngine` instantiated and passed to `OrderPropagationEngine` (replaces `None`)
- Authority enforcement flow: `propagate_order()` → `can_issue_order()` → hierarchy check
- Self-orders pass (unit in own CoC), cross-side orders fail, HQ-to-subordinate passes

## New CalibrationSchema Fields (2)

| Field | Type | Default | Consumer |
|-------|------|---------|----------|
| `enable_command_hierarchy` | `bool` | `False` | scenario.py — CommandEngine instantiation |
| `deception_phantom_count` | `int` | `3` | battle.py — phantoms per deception stratagem |

## Files Modified

| File | Changes |
|------|---------|
| `simulation/calibration.py` | +2 fields |
| `simulation/battle.py` | 69a (sortie recording), 69b (planning result), 69c (decoy deploy + assessment), 69e (burned zone) |
| `simulation/engine.py` | 69a (daily sortie reset) |
| `simulation/scenario.py` | 69d (hierarchy building, CommandEngine instantiation, units_by_side param) |
| `c2/orders/air_orders.py` | 69a (`record_sortie`, `reset_daily_sorties`, `get_state`/`set_state`) |
| `c2/planning/process.py` | 69b (`get_planning_result`, `consume_result`, auto-COA) |
| `detection/fog_of_war.py` | 69c (`deploy_decoy`, `get_active_decoys`, `update_decoys` passthroughs) |

## Test Files (5)

| File | Tests |
|------|-------|
| `test_phase_69a_ato_sortie.py` | 7 |
| `test_phase_69b_planning_result.py` | 8 |
| `test_phase_69c_deception_fow.py` | 11 |
| `test_phase_69d_command_hierarchy.py` | 8 |
| `test_phase_69e_burned_zone.py` | 7 |
| **Total** | **41** |

## Lessons Learned

- **Turnaround check is `<` not `<=`**: `get_available_sorties()` uses `current_time - last_sortie_end_time < turnaround_time`, so at exactly turnaround time the aircraft becomes available.
- **Auto-COA on complete**: `complete_planning()` is the natural place to auto-generate a COA — it's the terminal transition and no external code calls it for the result before this point.
- **Deception is assessment inflation, not detection spoofing**: Deploying decoys through FOW and inflating `enemy_power` in assessment is simpler and more effective than trying to inject phantom contacts into the detection loop.
- **Virtual HQ pattern scales**: Creating per-side virtual HQ nodes at DIVISION echelon with all units as COMPANY children gives correct authority semantics without requiring org YAML parsing.
- **`_create_engines()` needed `units_by_side` param**: Command hierarchy building requires knowledge of the force structure, which wasn't previously passed to the engine factory method.

## Postmortem

### Scope: On target
All 5 planned substeps delivered (69a–69e). No items dropped or deferred. One unplanned item added: `update_decoys()` tick-loop wiring (caught during postmortem integration audit).

### Quality: High
- 41 tests across 5 files covering unit behavior, backward compat, edge cases
- No TODOs/FIXMEs in new code
- All public methods have type hints and docstrings

### Integration: Fully wired (after postmortem fix)
- Postmortem caught that `update_decoys(dt)` was defined but never called in the tick loop — decoys would never degrade. Fixed by adding the call in battle.py after the fire zone damage block.
- All other new methods verified called from simulation loop.
- Structural test updated: consumer check now includes `scenario.py`; `enable_command_hierarchy` deferred from scenario exercise requirement.

### Deficits: 0 new
- No new known limitations. The plan's risk notes (69c "FOW.update() still not called in full cycle") were partially addressed — decoy degradation is wired but full FOW detection cycling remains a larger future effort.

### Cross-doc audit: 3 issues found and fixed
1. README badges stale (phase-68 → phase-69, test count 9,044 → 9,085)
2. mkdocs.yml missing phase-69 devlog nav entry
3. Test counts updated from 40 → 41 across all docs after postmortem added degradation test
