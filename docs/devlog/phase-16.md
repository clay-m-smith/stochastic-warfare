# Phase 16 — Electronic Warfare

**Status**: COMPLETE
**Date**: 2026-03-04
**Tests**: 144 new (4,614 total, includes 1 postmortem fix + 1 existing test updated)

## Summary

Full Electronic Warfare (EW) domain covering Electronic Attack (EA), Electronic Protection (EP), and Electronic Support (ES). New `ew/` package with 8 source modules. EW modulates existing detection, communication, and combat systems through their existing parameter interfaces — no parallel combat resolution. All effects backward-compatible via `enable_ew` config flag defaulting to `False` and default parameter values preserving existing behavior.

## Deliverables

### 16a: Spectrum & Emitters (22 tests)
- `ew/__init__.py` — Package init
- `ew/events.py` — 7 EW event types (JammingActivated/Deactivated, EmitterDetected, ECCMActivated, GPSSpoofingDetected, DecoyDeployed, SIGINTReport)
- `ew/spectrum.py` — SpectrumManager: frequency allocation, conflict detection, bandwidth overlap computation
- `ew/emitters.py` — EmitterRegistry: centralized emitter tracking with type/freq/side queries, activation/deactivation lifecycle

### 16b: Electronic Attack (40 tests)
- `ew/jamming.py` — JammingEngine: J/S ratio computation (Schleher/Adamy), burn-through range, aggregate radar SNR penalty, comms jam factor. JamTechnique enum (NOISE/BARRAGE/SPOT/SWEEP/DECEPTIVE). YAML-driven JammerDefinitionModel.
- `ew/spoofing.py` — SpoofingEngine: GPS spoof zones, receiver-type resistance (civilian 5%, P-code 40%, M-code 85%), INS cross-check detection delay, PGM offset computation
- `ew/decoys_ew.py` — EWDecoyEngine: chaff/flare/towed decoy/DRFM deployment, missile diversion probability (type-seeker match matrix), time-based degradation

### 16c: Electronic Protection (20 tests)
- `ew/eccm.py` — ECCMEngine: 4 technique types (frequency hopping, spread spectrum, sidelobe blanking, adaptive nulling). Each provides dB reduction against jamming. Multiple techniques additive. Suite registration per unit.

### 16d: Electronic Support (25 tests)
- `ew/sigint.py` — SIGINTEngine: intercept probability (received power vs sensitivity), AOA geolocation (Cramér-Rao bound σ_θ ≈ λ/(2π·L·√SNR)), TDOA geolocation (3+ collectors, baseline-dependent), traffic analysis (Poisson rate inference)

### 16e: Integration (12 tests)
- `detection/detection.py` — Added `jam_snr_penalty_db` parameter to `check_detection()` (default 0.0)
- `environment/electromagnetic.py` — Added `set_gps_jam_degradation()`, `set_gps_spoof_offset()`, `gps_spoof_offset` property. GPS accuracy now includes EW degradation.
- `combat/air_ground.py` — Added `gps_accuracy_m` parameter to `compute_weapon_delivery_accuracy()` (default 5.0)
- `simulation/scenario.py` — Added `ew_engine` field to SimulationContext (default None)
- `core/types.py` — Added `ModuleId.EW`

### 16f: YAML Data & Validation (24 tests)
- 6 jammer YAMLs: AN/ALQ-99, AN/TLQ-32, Krasukha-4, AN/SLQ-32, AN/ALQ-131, R-330Zh
- 4 ECCM suite YAMLs: US fighter, US destroyer, Soviet SAM, Patriot
- 2 SIGINT collector YAMLs: RC-135 Rivet Joint, ground SIGINT station
- 2 validation scenarios: Bekaa Valley 1982 (Mole Cricket 19), Gulf War EW 1991 (Night One)

## Key Design Decisions

1. **J/S ratio as the core physics**: All jamming effects derived from jammer-to-signal ratio. Stand-off geometry: `J/S = P_j + G_j - P_t - G_t + 40·log10(R_t) - 20·log10(R_j) + 10·log10(B_t/B_j)`
2. **EW→detection via parameter injection**: `jam_snr_penalty_db` parameter added to `check_detection()` — zero-impact default means all existing callers unaffected
3. **ECCM as dB reduction**: Each ECCM technique provides a subtraction from effective J/S. Multiple techniques additive. Simple but captures key dynamics.
4. **GPS spoofing distinct from jamming**: Spoofing provides false position (systematic offset), jamming denies position (noise). Different receiver types have different resistance.
5. **SIGINT uses Cramér-Rao bound**: AOA accuracy scales with wavelength, aperture, and SNR — physics-based rather than arbitrary.

## Backward Compatibility
- `JammingConfig.enable_ew = False` — EW engines not instantiated unless enabled
- `SimulationContext.ew_engine = None` — consuming code checks None before querying
- `jam_snr_penalty_db = 0.0` — detection unchanged when no EW active
- `gps_accuracy_m = 5.0` — weapon delivery unchanged when no GPS jamming
- `_gps_jam_degradation_m = 0.0` — GPS accuracy unchanged when no jamming

## Files Changed
- 8 new source files in `ew/`
- 5 modified existing files (detection, electromagnetic, air_ground, scenario, types)
- 14 YAML data files (6 jammers, 4 suites, 2 collectors, 2 scenarios)
- 6 test files (143 tests)
- 1 existing test file modified (test_types.py — added EW to ModuleId set)

## No New Dependencies
All EW physics implemented with existing numpy/scipy. No new package requirements.

## Known Limitations / Future Work
- EW engines not yet wired into simulation engine tick loop (deferred to integration phase)
- No DRFM detailed waveform modeling (simplified effectiveness parameter)
- TDOA geolocation uses simplified centroid-shift algorithm (full TDOA solver deferred)
- No cooperative jamming between multiple platforms (individual jammer aggregation only)
- Validation scenarios test component-level physics; full campaign-level EW validation deferred

## Postmortem

**Date**: 2026-03-04

### Scope: On target
Plan estimated ~135 tests, delivered 144 (including 1 postmortem fix). All 8 source files, 14 YAMLs, 2 validation scenarios delivered. One doc inaccuracy: `development-phases-post-mvp.md` claimed SATCOM/comms.py wiring that wasn't done — corrected.

### Quality: Medium — needs minor work
- **Bug found (E1, HIGH)**: `EMEnvironment.get_state()`/`set_state()` did not persist new `_gps_jam_degradation_m` and `_gps_spoof_offset` fields. Checkpoint/restore would lose GPS EW state. **Fixed**: updated state methods + added 2 tests (1 in 16e, 1 in test_electromagnetic.py).
- **Vacuous test fixed**: `test_visual_unaffected_by_jam_penalty` passed `jam_snr_penalty_db=0.0` for both clean and jammed cases. Now passes 10.0 for jammed.
- **Missing assertion fixed**: `test_no_event_on_failure` had no `assert`. Now asserts `len(events) == 0`.
- **Dead code removed**: `_BAND_RANGES` dict in `spectrum.py` was unused.
- **Import ordering fixed**: `import enum` was placed after module constant in `sigint.py`.
- **Doc inaccuracy corrected**: GPS/SATCOM note in `development-phases-post-mvp.md` overstated comms.py changes.

### Integration: Gaps found (expected — tick loop wiring deferred)
- Entire `ew/` package has **zero imports from non-EW simulation code**. All integration is through parameter hooks (`jam_snr_penalty_db`, `gps_accuracy_m`, `set_gps_jam_degradation`) that exist but are never called by the engine tick loop.
- All 7 event types are published but have no non-test subscribers (SimulationRecorder captures them via base `Event` MRO dispatch, so replay data includes them).
- `spectrum.py` is the most isolated module — no other EW module imports it.
- `enable_ew` config flag appears in scenario YAMLs but `ScenarioLoader` doesn't parse it.
- This is by design: physics engines are tested standalone; tick loop wiring is a separate integration step.

### New Deficits: 7 items (added to devlog index + deficit mapping)
Already tracked from Known Limitations (5 items). Additional findings:
- `_intercept_history` in `sigint.py` initialized but never populated or persisted
- `unit_id=""` hardcoded in `GPSSpoofingDetectedEvent` — cannot identify which unit detected spoofing
- `timestamp: Any` used in 11 method signatures instead of `datetime | None`
- `_range_m()` helper duplicated between `jamming.py` and `sigint.py`
- Burn-through range formula omits actual jammer distance (assumes R_j=1.0)
- Comms jam factor ignores desired signal transmitter power
- Several hardcoded magic numbers in jamming event radius (50km), decoy-seeker match matrix, traffic analysis sigmoid parameters

### Performance: No regression
Full test suite: ~91s (consistent with Phase 15's ~85s + 144 new fast tests).
