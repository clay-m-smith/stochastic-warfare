# Phase 3: Detection & Intelligence

## Summary

Phase 3 implements the detection and intelligence layer — the fog of war. Units become aware of each other through realistic sensor models across all domains (visual, thermal, radar, acoustic, EM). Detection uses a unified SNR-based framework where signal strength depends on target signature and range, noise depends on environmental conditions, and detection probability follows from the complementary error function. Each side maintains an independent, noisy, decaying belief state via Kalman filtering.

**Test count**: 296 new tests → 1,087 total (791 Phase 0–2 + 296 Phase 3). Post-Phase 4 backfill added 38 tests targeting C2-facing interfaces (track lifecycle, multi-sensor fusion, side isolation, Kalman edge cases, identification recovery) → 334 Phase 3 tests total.

## What Was Built

### Source Modules (12 files under `stochastic_warfare/detection/`)

| Module | Purpose | Key Classes |
|--------|---------|-------------|
| `__init__.py` | Package init | — |
| `signatures.py` | Target signature profiles & effective computation | `SignatureProfile`, `SignatureResolver`, `SignatureLoader` |
| `events.py` | Detection-layer EventBus events | `DetectionEvent`, `ClassificationEvent`, `IdentificationEvent`, `ContactLostEvent`, `SubmarineContactEvent`, `DeceptionEvent` |
| `sensors.py` | Sensor definitions, loading, runtime instances | `SensorDefinition`, `SensorInstance`, `SensorSuite`, `SensorLoader` |
| `detection.py` | Core SNR-based detection engine | `DetectionEngine`, `DetectionResult`, `DetectionConfig` |
| `identification.py` | Detection → Classification → Identification pipeline | `IdentificationEngine`, `ContactLevel`, `ContactInfo` |
| `sonar.py` | Active/passive sonar models | `SonarEngine`, `SonarResult` |
| `underwater_detection.py` | Multi-method submarine detection | `UnderwaterDetectionEngine`, `UnderwaterDetectionResult` |
| `estimation.py` | Kalman filter state estimation | `StateEstimator`, `Track`, `TrackState`, `TrackStatus` |
| `intel_fusion.py` | Multi-source intelligence fusion | `IntelFusionEngine`, `IntelReport`, `SatellitePass` |
| `deception.py` | Decoys, camouflage, feints | `DeceptionEngine`, `Decoy`, `DeceptionType` |
| `fog_of_war.py` | Per-side world view management | `FogOfWarManager`, `SideWorldView`, `ContactRecord` |

### YAML Data Files (19 files)

- **11 signature profiles** (`data/signatures/`): m1a2, us_rifle_squad, m109a6, f16c, mq9, ah64d, patriot, ddg51, ssn688, lhd1, hemtt
- **8 sensor definitions** (`data/sensors/`): mk1_eyeball, thermal_sight, ground_search_radar, air_search_radar, passive_sonar, active_sonar, esm_suite, nvg

### Test Files (12 files)

- 11 unit test files + 1 integration test file
- Integration tests cover: full pipeline, day/night visual, thermal contrast, R⁴ radar law, sonar speed-noise, CZ detection, identification pipeline, Kalman convergence, information decay, multi-source fusion, deception, fog-of-war asymmetry, underwater detection, deterministic replay, checkpoint/restore

### Visualization

- `scripts/visualize/detection_viz.py`: Pd vs range curves, belief vs truth convergence, ROC curves

## Design Decisions

1. **Unified SNR framework**: All sensor types use the same detection probability computation: Pd = 0.5 * erfc(-(SNR - threshold) / √2). Only the SNR computation physics differ between visual, thermal, radar, acoustic, and ESM.

2. **YAML-driven signatures and sensors**: Follows the same loader pattern established in Phase 2 (`UnitLoader`). Pydantic validates at load time. Factory dispatch via sensor type.

3. **Kalman filter for state estimation**: 4-state [x, y, vx, vy] constant-velocity model with process noise. Prediction grows uncertainty; measurement updates shrink it. Track lifecycle: TENTATIVE → CONFIRMED → COASTING → LOST.

4. **Signature-sensor separation**: Signatures (what a target looks like) and sensors (what an observer sees with) are independent data models. A sensor queries a target's appropriate signature domain.

5. **Environment coupling via constructor injection**: Detection modules receive environment engines as constructor parameters — same DI pattern as Phase 2 movement modules. Tests use `SimpleNamespace` mocks.

6. **No new dependencies**: All modules built with existing numpy, scipy (erfc), pydantic, pyyaml.

## Deviations from Plan

- Test count came to 296 vs the planned ~455. The plan overestimated per-module test counts. All key behaviors are covered. Additional tests can be added incrementally.
- The plan specified `~55` tests per step but many steps needed fewer tests to fully cover the API surface.

## Key Physics

- **Visual**: SNR ∝ (cross_section × illumination × exp(-extinction×range)) / range²
- **Thermal**: SNR ∝ (heat_output × emissivity × contrast) / (range² × IR_attenuation)
- **Radar**: Standard radar range equation: SNR = (Pt·Gt²·λ²·σ) / ((4π)³·R⁴·kTB) − atmospheric loss
- **Acoustic**: Signal Excess = SL − TL − (NL − DI). Active sonar: 2×TL (two-way).
- **Speed-noise curve**: base + 20·log₁₀(v/v_quiet) — standard engineering relationship from Phase 2.
- **MAD**: Pd = exp(−range/200) — exponential dropoff, effective only under ~500m.
- **Detection Pd**: 0.5 × erfc(−(SNR−threshold)/√2) — Gaussian noise model, monotonic.
- **Misclassification**: Sigmoid P(wrong) = 1/(1+exp(k(SNR−midpoint))), decreasing with SNR.

## Known Limitations / Post-MVP Refinements

These are deliberate simplifications made during initial implementation. All are functional but could benefit from refinement after MVP is complete.

1. **Test coverage gap vs plan**: 296 tests initially, backfilled to 334 post-Phase 4 (vs planned ~455). The backfill targeted C2-facing APIs: FoW track lifecycle (contact persistence, removal, confidence progression), multi-sensor same target (deduplication, reporting_sensors), world view consistency, re-detection after gap, Kalman edge cases (full TENTATIVE→CONFIRMED→COASTING→LOST lifecycle, re-update resetting coast timer, velocity estimation, covariance growth bounds), intel fusion (multi-source conflict resolution, side isolation, track management), and identification (misclassification recovery, extreme SNR, threshold boundary). Remaining gap is sensor FOV gating, multi-target saturation, and integration gain — worth a dedicated pass post-MVP.

2. **Track-to-target association in `fog_of_war.py`**: Currently associates contacts by unit ID (direct lookup). A real tracker would use nearest-neighbor gating on predicted position — required once combat starts generating many simultaneous contacts where the observer *doesn't know* the target's ID. Straightforward to add (Mahalanobis distance gating on track covariance) but not needed until multi-unit engagements are running.

3. **Environment data threading**: `DetectionEngine.check_detection()` takes environmental conditions as explicit parameters (illumination_lux, thermal_contrast, visibility_m, etc.) rather than querying `ConditionsEngine` internally. This keeps unit tests lightweight (no Phase 1 dependencies) but means the *caller* (fog_of_war update cycle, or the future simulation loop) is responsible for querying the environment and passing values through. If this becomes a maintenance burden, consider an adapter that wraps `ConditionsEngine` + `DetectionEngine` together.

4. **Sonar bearing in passive detection**: The passive sonar model generates a random bearing rather than computing the true bearing to target and adding noise. The signal excess calculation is correct, but the bearing output is placeholder. Needs the actual observer→target geometry threaded through when sonar is used in real scenarios.

5. **No sensor FOV filtering**: `check_detection()` doesn't gate on the sensor's `fov_deg` relative to the observer's heading. All sensors currently scan 360°. Adding FOV filtering requires knowing the sensor's mounting direction relative to the unit's heading — straightforward but deferred.

6. **Single-scan detection model**: Each `check_detection()` call is a single independent Bernoulli trial. Real sensors accumulate signal over multiple scans (integration gain). The current model is correct for instantaneous detection but doesn't model dwell time or scan-to-scan integration. The Kalman filter partially compensates (multiple detections improve the track), but true integration gain would improve Pd at the sensor level.

## Lessons Learned

- The SNR-based framework unifies all sensor physics under a single Pd computation, making it easy to add new sensor types.
- Kalman filter convergence tests need multiple observations to demonstrate convergence — a single update isn't sufficient.
- Passive sonar is bearing-only (no range) — this is a fundamental physical limitation that affects track quality.
- Decoy effectiveness degradation needs a configurable rate — different decoy types have very different lifetimes.
- The fog-of-war update cycle is the natural integration point where all detection subsystems come together.
