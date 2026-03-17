# Phase 61: Maritime, Acoustic, & EM Environment

**Block 7** — Final Engine Hardening
**Status**: Complete
**Tests**: 71 new (8,344 total Python passing)

## Overview

Wires three clusters of environmental subsystems whose outputs were computed but never consumed by the simulation loop: sea state effects on ship operations, underwater acoustic layers on sonar detection, and electromagnetic propagation on radar/comms/DEW.

## Deliverables

### Step 0: Infrastructure

- **`stochastic_warfare/simulation/calibration.py`** — 3 new boolean fields: `enable_sea_state_ops`, `enable_acoustic_layers`, `enable_em_propagation` (all default False)
- **`stochastic_warfare/simulation/scenario.py`** — UnderwaterAcousticsEngine, EMEnvironment (populates `conditions_engine`), and CarrierOpsEngine instantiated on SimulationContext; state persistence (get_state/set_state); EM environment wired to CommunicationsEngine
- **`stochastic_warfare/simulation/engine.py`** — UnderwaterAcousticsEngine.update(dt) call in tick loop

### 61a: Sea State → Ship Operations (19 tests)

- **`stochastic_warfare/simulation/battle.py`** (movement section):
  - Small craft speed penalty: −20% per Beaufort above 3 (displacement < 1000t or max_speed < 15)
  - Tidal current adjustment: effective_speed += current_speed × cos(current_dir − heading)
- **`stochastic_warfare/simulation/battle.py`** (engagement section):
  - Wave period resonance: if |wave_period − hull_natural_period| < 10%, crew_skill × (1/1.5)
  - Swell direction: crew_skill × (1.0 − sin²(wave_dir − heading) × 0.5)

### 61b: Acoustic Layer → Sonar Detection (19 tests)

- **`stochastic_warfare/simulation/battle.py`** (detection section):
  - Thermocline: target below, observer above → detection_range × 0.1 (~20 dB loss)
  - Surface duct: both in duct → × 3.0 (+10 dB gain); target below duct → × 0.06 (+15 dB loss)
  - Convergence zones at 55km intervals: CZ spike × 2.0; acoustic shadow between CZs × 0.05

### 61c: EM Propagation → Radar/Comms/DEW (16 tests)

- **`stochastic_warfare/simulation/battle.py`** (detection section):
  - Radar horizon gate: 4/3 Earth model, antenna height derived from domain (ground ~10m, ship ~30m, aircraft = altitude)
  - EM ducting: maritime platforms with ducting → radar range extended (capped at 2.0×)
- **`stochastic_warfare/simulation/battle.py`** (engagement section):
  - DEW humidity/precipitation_rate extracted from WeatherEngine and forwarded through route_engagement
- **`stochastic_warfare/combat/engagement.py`** — `humidity` and `precipitation_rate` optional params added to `route_engagement()`, forwarded to `execute_laser_engagement()`
- **`stochastic_warfare/c2/communications.py`**:
  - `set_em_environment()` method for EM environment injection
  - HF radio: reliability × hf_propagation_quality() (day ~0.3, night ~0.8)
  - VHF/UHF: beyond radio horizon → reliability × 0.1

### Structural Verification (8 tests)

Source-level pattern checks confirming all wiring present across 4 source files.

## Files Modified (6)

| File | Changes |
|------|---------|
| `stochastic_warfare/simulation/calibration.py` | 3 new boolean fields |
| `stochastic_warfare/simulation/scenario.py` | 3 engine instantiations, state persistence, EM→comms wiring |
| `stochastic_warfare/simulation/engine.py` | UnderwaterAcousticsEngine.update(dt) |
| `stochastic_warfare/simulation/battle.py` | Sea state ops, acoustic layers, radar horizon, ducting, DEW params |
| `stochastic_warfare/combat/engagement.py` | humidity/precipitation_rate forwarding |
| `stochastic_warfare/c2/communications.py` | set_em_environment(), HF quality, radio horizon |

## New Test Files (5)

| File | Tests |
|------|-------|
| `tests/unit/test_phase_61_infra.py` | 9 |
| `tests/unit/test_phase_61a_sea_state_ops.py` | 19 |
| `tests/unit/test_phase_61b_acoustic_layers.py` | 19 |
| `tests/unit/test_phase_61c_em_propagation.py` | 16 |
| `tests/unit/test_phase_61_structural.py` | 8 |

## Deferrals (Planned → Deferred)

1. **CarrierOpsEngine full battle loop wiring** — instantiated on context but CAP management, sortie turnaround, recovery window enforcement require air sortie dispatch architecture. Structural prep only.
2. **Beaufort > 6 helicopter deck landing abort** — no helicopter-carrier recovery tracking exists yet
3. **Beaufort > 7 carrier flight ops suspension** — requires CarrierOpsEngine battle loop integration
4. **Landing craft 10% casualty risk at Beaufort > 5** — no landing craft type detection
5. **Sea spray/salt fog** — maritime atmospheric obscurant at high Beaufort, needs ObscurantsEngine integration
6. **SHF/EHF rain attenuation for comms** — comms engine doesn't track per-equipment frequency; approximate by comm_type categories later
7. **Ionospheric storm effects on HF** — needs space weather events
8. **Hull natural frequency per ship class** — hardcoded ~10s destroyers, ~12s carriers; should come from YAML data

## Design Decisions

1. **3 enable flags (not per-subsystem)**: Groups related effects. `enable_sea_state_ops` covers all Beaufort/tidal/wave. `enable_acoustic_layers` covers all sonar environment. `enable_em_propagation` covers radar horizon + comms + DEW.
2. **`conditions_engine` populated with EMEnvironment**: Was always None on SimulationContext. Now SpaceEngine (which already passes `em_environment=ctx.conditions_engine`) gets a real EM environment, and battle.py/comms can use it for radar horizon and HF quality.
3. **CarrierOpsEngine structural only**: Instantiate on context but defer full integration. CAP management needs air sortie dispatch that doesn't exist.
4. **Antenna height approximation**: No `antenna_height` field on sensors. Derived from unit domain: ground ~10m, ship ~30m, aircraft = altitude.
5. **Safe attribute access throughout**: All `getattr(ctx, "field", None)` — prevents SimpleNamespace mock breakage.
6. **DEW params through route_engagement**: Added optional params to existing signature rather than modifying battle.py call to DEW engine directly. Follows established routing pattern.
7. **Rain detection factor confirmed already wired**: Phase 52b wired `_compute_rain_detection_factor()` at battle.py:2318. Verified and skipped.

## Lessons Learned

- **conditions_engine was a latent integration gap**: Field existed on SimulationContext since early phases, SpaceEngine tried to use it, but nobody ever populated it. Phase 61 fixes this incidentally while wiring EM propagation.
- **Sonar sensor types differ from plan**: Plan referenced `HULL_MOUNTED`, `TOWED_ARRAY`, `SONOBUOY`, `DIPPING` but actual SensorType enum uses `ACTIVE_SONAR`, `PASSIVE_SONAR`, `PASSIVE_ACOUSTIC`. Always verify enum values before coding.
- **Acoustic modifier math compounds multiplicatively**: Thermocline (0.1) × shadow (0.05) = 0.005 — submarine below thermocline between CZ ranges is effectively invisible. This is physically correct but may surprise calibrators.

## Postmortem

### Scope
**On target.** 6 source files modified, 5 test files, 71 tests. Plan called for ~55 tests; delivered 71 (agents added extra edge cases). All 3 environmental clusters wired. CarrierOpsEngine structural-only is a documented deferral consistent with Phase 53/58 precedent.

### Quality
**High.** No TODOs, FIXMEs, or hacks in modified source files. All effects gated by `enable_*=False` — zero behavioral change unless opted in. 8,344 tests pass with no regressions.

### Integration
**Fully wired for gated effects.** UnderwaterAcousticsEngine on context + updated per tick. EMEnvironment populates conditions_engine (fixes SpaceEngine gap). CarrierOpsEngine on context + state persistence. CommunicationsEngine receives EM environment.

**Gaps (documented deferrals):**
- CarrierOpsEngine not in tick loop (structural only)
- Beaufort operational gates (helo abort, carrier suspension) need air sortie dispatch
- Hull natural period hardcoded rather than from YAML

### Deficits
8 new deferred items (all logged above). Key ones:
- Hull natural period should come from YAML per ship class
- CarrierOpsEngine battle loop integration (requires air sortie dispatch architecture)
- SHF/EHF comms rain attenuation (needs per-equipment frequency tracking)

### Performance
Test suite: 787.78s (13:07) — consistent with Phase 60. No performance regression.

### Action Items
- [x] All source modifications complete
- [x] All tests passing (71 phase + 8,344 total)
- [ ] Update lockstep docs (CLAUDE.md, development-phases-block7.md, devlog/index.md, README.md, MEMORY.md, project-structure.md)
