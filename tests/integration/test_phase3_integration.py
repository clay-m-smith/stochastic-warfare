"""Phase 3 integration tests — full detection pipeline, end-to-end scenarios."""

from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from stochastic_warfare.core.types import Domain, Position, Side
from stochastic_warfare.detection.deception import Decoy, DeceptionEngine, DeceptionType
from stochastic_warfare.detection.detection import DetectionEngine
from stochastic_warfare.detection.estimation import (
    EstimationConfig,
    StateEstimator,
    TrackStatus,
)
from stochastic_warfare.detection.fog_of_war import FogOfWarManager, SideWorldView
from stochastic_warfare.detection.identification import (
    ContactInfo,
    ContactLevel,
    IdentificationEngine,
)
from stochastic_warfare.detection.intel_fusion import IntelFusionEngine, IntelReport, IntelSource
from stochastic_warfare.detection.sensors import (
    SensorDefinition,
    SensorInstance,
    SensorLoader,
    SensorSuite,
    SensorType,
)
from stochastic_warfare.detection.signatures import (
    SignatureLoader,
    SignatureProfile,
    SignatureResolver,
    VisualSignature,
    ThermalSignature,
    RadarSignature,
    AcousticSignature,
    EMSignature,
)
from stochastic_warfare.detection.sonar import SonarEngine
from stochastic_warfare.detection.underwater_detection import UnderwaterDetectionEngine

SIG_DIR = Path(__file__).resolve().parents[2] / "data" / "signatures"
SENSOR_DIR = Path(__file__).resolve().parents[2] / "data" / "sensors"


# ---------------------------------------------------------------------------
# 1. Full detection pipeline — sensor + signature + environment → detection
# ---------------------------------------------------------------------------


class TestFullPipeline:
    def test_sensor_plus_signature_to_detection(self) -> None:
        """Load real YAML data, compute SNR, get detection result."""
        sig_loader = SignatureLoader(SIG_DIR)
        sig_loader.load_all()
        profile = sig_loader.get_profile("m1a2")

        sensor_loader = SensorLoader(SENSOR_DIR)
        sensor_loader.load_all()
        defn = sensor_loader.get_definition("thermal_sight")
        sensor = SensorInstance(defn)

        engine = DetectionEngine(rng=np.random.Generator(np.random.PCG64(42)))
        result = engine.check_detection(
            Position(0.0, 0.0, 0.0), Position(1000.0, 0.0, 0.0),
            sensor, profile, illumination_lux=100.0, thermal_contrast=1.0,
        )
        assert result.range_m == pytest.approx(1000.0)
        assert isinstance(result.probability, float)


# ---------------------------------------------------------------------------
# 2. Visual detection — day vs night
# ---------------------------------------------------------------------------


class TestVisualDayNight:
    def test_day_better_than_night(self) -> None:
        rng1 = np.random.Generator(np.random.PCG64(42))
        rng2 = np.random.Generator(np.random.PCG64(42))
        sensor = SensorInstance(SensorDefinition(
            sensor_id="eye", sensor_type="VISUAL", display_name="Eye",
            max_range_m=10000.0, detection_threshold=3.0,
        ))
        profile = SignatureProfile(
            profile_id="t", unit_type="t",
            visual=VisualSignature(cross_section_m2=8.0, camouflage_factor=1.0),
        )
        engine_day = DetectionEngine(rng=rng1)
        engine_night = DetectionEngine(rng=rng2)

        r_day = engine_day.check_detection(
            Position(0, 0, 0), Position(2000, 0, 0), sensor, profile,
            illumination_lux=10000.0,
        )
        r_night = engine_night.check_detection(
            Position(0, 0, 0), Position(2000, 0, 0), sensor, profile,
            illumination_lux=0.01,
        )
        assert r_day.snr_db > r_night.snr_db


# ---------------------------------------------------------------------------
# 3. Thermal detection — crossover degrades detection
# ---------------------------------------------------------------------------


class TestThermalContrast:
    def test_high_contrast_better(self) -> None:
        sensor = SensorInstance(SensorDefinition(
            sensor_id="th", sensor_type="THERMAL", display_name="Thermal",
            max_range_m=5000.0, detection_threshold=3.0,
        ))
        profile = SignatureProfile(
            profile_id="t", unit_type="t",
            thermal=ThermalSignature(heat_output_kw=500.0, emissivity=0.95),
        )
        snr_hi = DetectionEngine.compute_snr_thermal(sensor, 500.0 * 0.95, 2000.0, 1.0)
        snr_lo = DetectionEngine.compute_snr_thermal(sensor, 500.0 * 0.95, 2000.0, 0.1)
        assert snr_hi > snr_lo


# ---------------------------------------------------------------------------
# 4. Radar detection — R⁴ law
# ---------------------------------------------------------------------------


class TestRadarR4:
    def test_r4_law(self) -> None:
        sensor = SensorInstance(SensorDefinition(
            sensor_id="r", sensor_type="RADAR", display_name="Radar",
            max_range_m=200000.0, detection_threshold=10.0,
            frequency_mhz=3300.0, peak_power_w=4_000_000.0, antenna_gain_dbi=42.0,
        ))
        snr_10 = DetectionEngine.compute_snr_radar(sensor, 10.0, 10000.0, 0.0)
        snr_100 = DetectionEngine.compute_snr_radar(sensor, 10.0, 100000.0, 0.0)
        assert abs((snr_10 - snr_100) - 40.0) < 1.0  # R⁴ = 40 dB/decade


# ---------------------------------------------------------------------------
# 5. Sonar passive — speed-noise tradeoff
# ---------------------------------------------------------------------------


class TestSonarSpeedNoise:
    def test_fast_sub_easier_to_detect(self) -> None:
        engine = SonarEngine(rng=np.random.Generator(np.random.PCG64(42)))
        sensor = SensorInstance(SensorDefinition(
            sensor_id="ps", sensor_type="PASSIVE_SONAR", display_name="Passive",
            max_range_m=100000.0, detection_threshold=8.0, directivity_index_db=25.0,
        ))
        # Slow sub
        slow_noise = UnderwaterDetectionEngine.speed_noise_tradeoff(110.0, 5.0)
        # Fast sub
        fast_noise = UnderwaterDetectionEngine.speed_noise_tradeoff(110.0, 25.0)
        assert fast_noise > slow_noise


# ---------------------------------------------------------------------------
# 6. Sonar active — CZ detection
# ---------------------------------------------------------------------------


class TestSonarCZ:
    def test_cz_detection(self) -> None:
        assert SonarEngine.convergence_zone_check(55000.0) is True
        assert SonarEngine.convergence_zone_check(30000.0) is False


# ---------------------------------------------------------------------------
# 7. Identification pipeline — SNR drives classification level
# ---------------------------------------------------------------------------


class TestIdentificationPipeline:
    def test_snr_drives_level(self) -> None:
        ident = IdentificationEngine(np.random.Generator(np.random.PCG64(42)))
        from stochastic_warfare.detection.detection import DetectionResult

        # Low SNR → DETECTED
        det_low = DetectionResult(True, 0.6, 11.0, 5000.0, SensorType.RADAR, 0.0)
        ci_low = ident.classify_from_detection(det_low, threshold_db=10.0)
        assert ci_low.level == ContactLevel.DETECTED

        # Very high SNR → at least CLASSIFIED
        det_high = DetectionResult(True, 0.99, 50.0, 5000.0, SensorType.RADAR, 0.0)
        ident2 = IdentificationEngine(np.random.Generator(np.random.PCG64(42)))
        ci_high = ident2.classify_from_detection(det_high, threshold_db=10.0)
        assert ci_high.level >= ContactLevel.CLASSIFIED


# ---------------------------------------------------------------------------
# 8. Kalman filter convergence
# ---------------------------------------------------------------------------


class TestKalmanConvergence:
    def test_multiple_observations_converge(self) -> None:
        est = StateEstimator(rng=np.random.Generator(np.random.PCG64(42)))
        R = np.diag([100.0, 100.0])
        meas = np.array([5000.0, 6000.0])
        track = est.create_track("t-1", "blue", meas, R,
                                  ContactInfo(ContactLevel.DETECTED, None, None, None, 0.5), 0.0)
        for i in range(30):
            est.predict(track, dt=1.0)
            est.update(track, np.array([5000.0, 6000.0]) + np.random.randn(2) * 5.0,
                       R, time=float(i + 1))
        assert track.state.position[0] == pytest.approx(5000.0, abs=20.0)
        assert track.state.position[1] == pytest.approx(6000.0, abs=20.0)
        assert track.position_uncertainty < 50.0


# ---------------------------------------------------------------------------
# 9. Information decay
# ---------------------------------------------------------------------------


class TestInformationDecay:
    def test_uncertainty_grows_without_updates(self) -> None:
        est = StateEstimator(rng=np.random.Generator(np.random.PCG64(42)))
        R = np.diag([50.0, 50.0])
        track = est.create_track("t-1", "blue", np.array([1000.0, 2000.0]), R,
                                  ContactInfo(ContactLevel.DETECTED, None, None, None, 0.5), 0.0)
        unc_0 = track.position_uncertainty
        for _ in range(10):
            est.predict(track, dt=60.0)
        assert track.position_uncertainty > unc_0 * 5


# ---------------------------------------------------------------------------
# 10. Intel fusion — multi-source improves track quality
# ---------------------------------------------------------------------------


class TestIntelFusionIntegration:
    def test_multi_source_fusion(self) -> None:
        est = StateEstimator()
        engine = IntelFusionEngine(state_estimator=est, rng=np.random.default_rng(42))
        tid = engine.submit_report("blue", IntelReport(
            source=IntelSource.SENSOR, timestamp=0.0, reliability=0.8,
            target_position=Position(5000.0, 6000.0, 0.0), position_uncertainty_m=200.0,
        ))
        track = engine.get_tracks("blue")[tid]
        unc_1 = track.position_uncertainty
        for i in range(5):
            engine.submit_report("blue", IntelReport(
                source=IntelSource.IMINT, timestamp=float(i + 1), reliability=0.9,
                target_position=Position(5005.0, 6005.0, 0.0), position_uncertainty_m=100.0,
            ), contact_id=tid)
        assert track.position_uncertainty < unc_1


# ---------------------------------------------------------------------------
# 11. Deception — decoys create false tracks
# ---------------------------------------------------------------------------


class TestDeceptionIntegration:
    def test_decoy_effectiveness_degrades(self) -> None:
        engine = DeceptionEngine(rng=np.random.default_rng(42))
        decoy = engine.deploy_decoy(
            Position(0, 0, 0), DeceptionType.DECOY_RADAR,
            degradation_rate=0.05,
        )
        assert decoy.effectiveness == 1.0
        engine.update_decoys(dt=10.0)
        assert decoy.effectiveness == pytest.approx(0.5)
        engine.update_decoys(dt=10.0)
        assert decoy.active is False


# ---------------------------------------------------------------------------
# 12. Fog of war asymmetry
# ---------------------------------------------------------------------------


class TestFogOfWarAsymmetry:
    def test_two_sides_independent(self) -> None:
        fow = FogOfWarManager(
            detection_engine=DetectionEngine(rng=np.random.default_rng(42)),
            identification_engine=IdentificationEngine(np.random.default_rng(43)),
            state_estimator=StateEstimator(),
            intel_fusion=IntelFusionEngine(StateEstimator()),
        )
        blue_wv = fow.get_world_view("blue")
        red_wv = fow.get_world_view("red")
        assert blue_wv.side == "blue"
        assert red_wv.side == "red"
        assert blue_wv is not red_wv


# ---------------------------------------------------------------------------
# 13. Underwater detection — MAD + periscope integration
# ---------------------------------------------------------------------------


class TestUnderwaterIntegration:
    def test_mad_and_periscope(self) -> None:
        sonar = SonarEngine(rng=np.random.default_rng(42))
        uw = UnderwaterDetectionEngine(sonar_engine=sonar, rng=np.random.default_rng(43))

        # MAD: aircraft at close range
        results = uw.detect_submarine(
            observer_pos=Position(0, 0, 100.0),
            target_pos=Position(200, 0, -100),
            target_depth=100.0, target_speed=5.0,
            target_noise_db=120.0, range_m=200.0,
            is_aircraft=True,
        )
        methods = {r.method for r in results}
        from stochastic_warfare.detection.underwater_detection import UnderwaterDetectionMethod
        assert UnderwaterDetectionMethod.MAD in methods

        # Periscope: shallow sub
        results2 = uw.detect_submarine(
            observer_pos=Position(0, 0, 0),
            target_pos=Position(500, 0, -10),
            target_depth=10.0, target_speed=3.0,
            target_noise_db=100.0, range_m=500.0,
        )
        methods2 = {r.method for r in results2}
        assert UnderwaterDetectionMethod.PERISCOPE_DETECTION in methods2


# ---------------------------------------------------------------------------
# 14. Deterministic replay
# ---------------------------------------------------------------------------


class TestDeterministicReplay:
    def test_same_seed_identical_outcomes(self) -> None:
        def run(seed):
            rng = np.random.Generator(np.random.PCG64(seed))
            engine = DetectionEngine(rng=rng)
            sensor = SensorInstance(SensorDefinition(
                sensor_id="eye", sensor_type="VISUAL", display_name="Eye",
                max_range_m=10000.0, detection_threshold=3.0,
            ))
            profile = SignatureProfile(
                profile_id="t", unit_type="t",
                visual=VisualSignature(cross_section_m2=10.0),
            )
            results = []
            for i in range(10):
                r = engine.check_detection(
                    Position(0, 0, 0), Position(float(i * 500 + 500), 0, 0),
                    sensor, profile, illumination_lux=500.0,
                )
                results.append((r.detected, r.probability, r.snr_db))
            return results

        r1 = run(12345)
        r2 = run(12345)
        assert r1 == r2


# ---------------------------------------------------------------------------
# 15. Checkpoint/restore — full Phase 3 state round-trip
# ---------------------------------------------------------------------------


class TestCheckpointRestore:
    def test_detection_engine_roundtrip(self) -> None:
        engine = DetectionEngine(rng=np.random.Generator(np.random.PCG64(42)))
        sensor = SensorInstance(SensorDefinition(
            sensor_id="eye", sensor_type="VISUAL", display_name="Eye",
            max_range_m=10000.0, detection_threshold=3.0,
        ))
        profile = SignatureProfile(profile_id="t", unit_type="t")
        engine.check_detection(Position(0, 0, 0), Position(1000, 0, 0), sensor, profile)
        state = engine.get_state()

        engine2 = DetectionEngine(rng=np.random.Generator(np.random.PCG64(0)))
        engine2.set_state(state)

        r1 = engine.check_detection(Position(0, 0, 0), Position(500, 0, 0), sensor, profile)
        r2 = engine2.check_detection(Position(0, 0, 0), Position(500, 0, 0), sensor, profile)
        assert r1.detected == r2.detected

    def test_estimator_roundtrip(self) -> None:
        est = StateEstimator(rng=np.random.Generator(np.random.PCG64(42)))
        state = est.get_state()
        est2 = StateEstimator(rng=np.random.Generator(np.random.PCG64(0)))
        est2.set_state(state)
        assert est._rng.random() == est2._rng.random()

    def test_intel_fusion_roundtrip(self) -> None:
        engine = IntelFusionEngine(rng=np.random.default_rng(42))
        engine.submit_report("blue", IntelReport(
            source=IntelSource.SENSOR, timestamp=0.0, reliability=0.8,
            target_position=Position(1000, 2000, 0), position_uncertainty_m=100.0,
        ))
        state = engine.get_state()
        engine2 = IntelFusionEngine(rng=np.random.default_rng(0))
        engine2.set_state(state)
        assert len(engine2.get_tracks("blue")) == 1

    def test_yaml_loaders(self) -> None:
        """All YAML data files load and validate."""
        sig_loader = SignatureLoader(SIG_DIR)
        sig_loader.load_all()
        assert len(sig_loader.available_profiles()) == 11

        sensor_loader = SensorLoader(SENSOR_DIR)
        sensor_loader.load_all()
        assert len(sensor_loader.available_sensors()) == 8
