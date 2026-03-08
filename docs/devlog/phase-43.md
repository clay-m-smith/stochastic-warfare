# Phase 43: Domain-Specific Resolution

**Status**: Complete
**Tests**: 45
**Files changed**: 2 modified (`simulation/battle.py`, `simulation/scenario.py`) + 1 new test file

## Summary

Wired existing aggregate combat engines into the battle loop via era-aware and domain-specific engagement routing. All 6+ aggregate engines (volley fire, archery, melee, indirect fire, naval surface/subsurface/gunnery/gunfire support/mine) were already instantiated on `SimulationContext` for their respective eras; Phase 43 routes engagements to them instead of the generic `route_engagement()` direct-fire path.

## Sub-phases

### 43a: Era-Aware Engagement Routing (core routing dispatcher)

Routes pre-modern engagements to aggregate fire models BEFORE the existing `route_engagement()` call:

- **Napoleonic**: `RIFLE`/`CANNON` at range > 10m -> `VolleyFireEngine.fire_volley()` with personnel count and formation firepower fraction. Close range or `MELEE` -> `MeleeEngine.resolve_melee_round()`.
- **Ancient/Medieval**: `RIFLE` (longbow/crossbow/javelin) at range -> `ArcheryEngine.fire_volley()`. `MELEE` or close range -> `MeleeEngine.resolve_melee_round()`.
- **WW1**: `RIFLE` (bolt-action) -> `VolleyFireEngine.fire_volley()` with `is_rifle=True`. `MACHINE_GUN` falls through to standard direct fire. `MELEE` or close range -> `MeleeEngine`.
- **Modern/WW2**: No aggregate routing, falls through to existing `route_engagement()`.

Helper functions: `_get_formation_firepower()`, `_infer_melee_type()`, `_infer_missile_type()`, `_apply_aggregate_casualties()`, `_apply_melee_result()`.

Aggregate casualty mapping: `>=60% -> DESTROYED`, `>=30% -> DISABLED`, `<30% -> no status change` (matches existing `BattleConfig` thresholds).

### 43b: Indirect Fire Routing (all eras)

Routes `HOWITZER`, `MORTAR`, `ARTILLERY` category weapons to `IndirectFireEngine.fire_mission()` instead of direct-fire Pk:

- `IndirectFireEngine` instantiated unconditionally in `_create_engines()` (not era-gated).
- CEP-based area effect: impacts within 50m lethal radius count as near-hits, each contributing 15% casualty fraction.
- Applies to all eras (modern mortars, WW1 field guns, medieval catapults with `HOWITZER` category).

### 43c: Naval Domain Routing (all eras, highest priority)

Routes naval engagements to 5 specialized engines based on weapon category:

- `TORPEDO_TUBE` -> `NavalSubsurfaceEngine.torpedo_engagement()` (Pk + damage fraction)
- `MISSILE_LAUNCHER` -> `NavalSurfaceEngine.salvo_exchange()` (Hughes salvo model)
- `NAVAL_GUN` -> `NavalGunneryEngine.fire_salvo()` (bracket convergence, WW1/WW2) or `NavalSurfaceEngine.naval_gun_engagement()` (modern fallback)
- `NAVAL_GUN`/`CANNON` vs `GROUND` target -> `NavalGunfireSupportEngine.shore_bombardment()`

Naval routing takes priority (checked before era routing) since naval combat mechanics are domain-specific, not era-specific. Returns `(handled, status)` tuple to distinguish "routed but missed" from "not a naval weapon".

4 new naval engine fields + `IndirectFireEngine` field added to `SimulationContext`. All instantiated unconditionally in `_create_engines()`. Added to `get_state()`/`set_state()` engine lists.

Also added `VolleyFireEngine` + `MeleeEngine` to WW1 era engine creation, and `MeleeEngine` to Ancient era engine creation (previously missing).

## Key Design Decisions

1. **Route on raw `category` string, not `parsed_category()`**: Historical-era weapons use non-enum categories (`RIFLE`, `MELEE`, `ARTILLERY`) that throw `KeyError` from `WeaponCategory[...]`. Safe access via `getattr(wpn_inst.definition, "category", "").upper()`.

2. **Naval routing uses `(handled, status)` tuple**: Distinguishes "weapon handled by naval engine but missed" (routed, no damage) from "weapon not a naval type" (fall through to standard path). Prevents torpedo misses from cascading into direct-fire resolution.

3. **Aggregate engines instantiated unconditionally**: `IndirectFireEngine` and all 4 naval engines created for every scenario regardless of era/domain. Cost is negligible (lightweight objects). Simplifies wiring vs conditional creation.

4. **`_MELEE_RANGE_M = 10.0`**: Below this range, any weapon type in pre-modern eras routes to melee engine (bayonet, hand-to-hand). Allows ranged weapons to transition to melee at close quarters.

5. **Personnel count as aggregate model input**: `len(unit.personnel)` maps directly to `n_muskets`/`n_archers`/`attacker_strength` parameters. Verified against Napoleonic YAML data (Austrian line: 599, French: 74, cuirassiers: 119).

## Known Limitations

- **WW1 barrage not wired**: `BarrageEngine` uses zone-based create/update/query pattern (not per-engagement). WW1 `CANNON` routes to `IndirectFireEngine` instead. Full barrage integration deferred.
- **Shore bombardment reachability**: `_route_naval_engagement` checks weapon category but not whether the `CANNON` is on a naval platform vs land artillery. Fall-through to standard path handles land artillery correctly.
- **Melee weapon range filtering**: Weapons with `max_range_m` smaller than target distance are filtered out by weapon selection before reaching melee routing. Melee weapons in YAML should use `max_range_m: 0` to avoid this.
- **Naval engine constructors always called**: Creates naval engines even for land-only scenarios. No measurable performance impact.

## Test Summary (45 tests)

| Category | Count | What it verifies |
|----------|-------|-----------------|
| Volley fire routing | 8 | Napoleonic musket/cannon, WW1 rifle, WW1 MG fallthrough, modern/WW2 fallthrough, personnel count, formation fraction |
| Archery routing | 1 | Ancient bow -> archery engine |
| Melee routing | 3 | Ancient melee, Napoleonic melee, close-range forced melee |
| Aggregate casualties | 4 | Destroy/disable/light/zero thresholds |
| Melee result | 2 | Both-side casualties, rout morale state |
| Infer melee type | 5 | cavalry/bayonet/pike/sword/default |
| Infer missile type | 3 | longbow/crossbow/javelin |
| Formation firepower | 2 | Default 1.0, engine queried |
| Indirect fire routing | 4 | Howitzer/mortar routing, casualties, MG unchanged |
| Naval routing | 8 | Torpedo hit/miss/destroy/disable, missile salvo, naval gun, routing priority, land fallthrough |
| Scenario context | 5 | New field existence on SimulationContext |

## Postmortem

### 1. Delivered vs Planned

**Planned (from development-phases-block5.md)**:
- 43a: Era-aware routing (~15 tests) — Delivered (8 volley + 1 archery + 3 melee + helpers)
- 43b: Indirect fire routing (~8 tests) — Delivered (4 tests)
- 43c: Naval domain routing (~12 tests) — Delivered (8 tests + 5 context field tests)
- 43d: Simultaneous fire coordination — **Descoped**: Simultaneous volley coordination requires multi-unit aggregation within a single tick, which is architecturally distinct from per-unit engagement routing. Deferred.
- Total planned: ~35 tests. Delivered: 45 tests (overdelivered on helper/edge case coverage).

**Unplanned additions**:
- Added `VolleyFireEngine` + `MeleeEngine` to WW1 era (WW1 era only had trench/barrage/gas engines)
- Added `MeleeEngine` to Ancient era (only had ArcheryEngine)
- These were discovered during implementation — the aggregate models existed but WW1/Ancient eras were missing them
- Naval engines (5) created unconditionally in `_create_engines()` instead of conditionally — simpler than the plan's `has_naval` gating

**Verdict**: Scope slightly over on tests (45 vs 35), slightly under on features (43d deferred). Well-calibrated overall.

### 2. Integration Audit

| Check | Status |
|-------|--------|
| New helpers used by production code | All 7 helpers called in `_execute_engagements()` |
| New ctx fields used in battle.py | All 5 via `getattr(ctx, "X", None)` |
| New engines in get_state/set_state | All 5 added to both persistence lists |
| Tests import and exercise helpers | All 7 imported and tested |
| Dead modules | None — all new code is in existing files |

No integration gaps found.

### 3. Test Quality Review

- **Integration vs unit**: Mix of both — BattleManager integration tests call `_execute_engagements()` end-to-end with mock contexts. Helper function tests are pure unit tests.
- **Realistic data**: Mock weapon definitions with realistic parameters (Brown Bess 200m range, torpedo 20km, Harpoon 130km). Personnel counts match YAML data (100 archers, 50 cavalry).
- **Edge cases**: Zero casualties, torpedo miss, land weapon in naval context (fallthrough), melee at range (forced melee), formation firepower engine missing.
- **Mock quality**: MagicMock used appropriately for engines; SimpleNamespace for lightweight ctx. One existing Phase 41 test broke due to missing `category` attribute — fixed with `getattr` safe access.

Minor gap: no test for the `ARTILLERY` category in `_INDIRECT_FIRE_CATEGORIES` (only `HOWITZER` and `MORTAR` tested). Low risk since they use the same code path.

### 4. API Surface Check

All new functions are module-private (`_` prefix). No new public API. Type hints on all function signatures. No bare `print()`. `get_logger(__name__)` already present at module level.

### 5. Deficit Discovery

| # | Deficit | Severity |
|---|---------|----------|
| 1 | `torpedo_pk=0.4`, `attacker_pk=0.7`, `defender_pd_pk=0.3` hardcoded in `_route_naval_engagement` | Medium — should read from weapon/ammo/unit data |
| 2 | `target_length_m=150.0`, `target_beam_m=20.0` hardcoded for naval gunnery | Medium — should read from target unit data |
| 3 | Lethal radius `50.0m` and casualty fraction `0.15` per impact hardcoded in `_apply_indirect_fire_result` | Low — should be configurable or read from ammo data |
| 4 | WW1 barrage engine not wired (zone-based pattern incompatible with per-engagement routing) | Low — WW1 CANNON uses IndirectFireEngine as adequate fallback |
| 5 | 43d simultaneous fire coordination deferred | Low — volley fire already models coordinated fire within a single unit |

### 6. Documentation Freshness

| Doc | Accurate? | Action |
|-----|-----------|--------|
| CLAUDE.md | Yes — updated to Phase 43, test count 8,002 | None |
| development-phases-block5.md | Yes — Phase 43 marked Complete | None |
| devlog/index.md | Yes — Phase 43 row added | None |
| devlog/phase-43.md | Yes — created with full details | None |
| README.md | Yes — Phase 43 row + count 8,002 | None |
| MEMORY.md | Yes — status + lessons + table updated | None |
| docs/index.md | Fixed — was stale at 7,957 | Updated to 8,002 |
| mkdocs.yml | Fixed — Phase 43 nav entry was missing | Added |

### 7. Performance Sanity

- Phase 42 baseline: ~137s (from Phase 42 devlog)
- Phase 43: ~138s
- Delta: +1s (~0.7%) — within noise. No performance regression.

### 8. Summary

- **Scope**: On target (43a/b/c delivered; 43d deferred as architecturally distinct)
- **Quality**: High — 45 tests, realistic data, edge cases covered, clean integration
- **Integration**: Fully wired — all helpers used, all engines instantiated, backward compat preserved
- **Deficits**: 5 new items (3 hardcoded values, 1 barrage engine deferral, 1 simultaneous fire deferral)
- **Action items**: None blocking — all deficits are low/medium severity and suitable for future phases
