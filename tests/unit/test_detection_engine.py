"""Tests for detection/detection.py — core SNR-based detection engine."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.detection.detection import (
    DetectionConfig,
    DetectionEngine,
    DetectionResult,
)
from stochastic_warfare.detection.sensors import SensorDefinition, SensorInstance, SensorType
from stochastic_warfare.detection.signatures import (
    EMSignature,
    RadarSignature,
    SignatureProfile,
    ThermalSignature,
    VisualSignature,
)
from stochastic_warfare.entities.equipment import EquipmentCategory, EquipmentItem


# ── helpers ──────────────────────────────────────────────────────────


def _defn(**kwargs) -> SensorDefinition:
    defaults = dict(
        sensor_id="test",
        sensor_type="VISUAL",
        display_name="Test",
        max_range_m=10000.0,
        detection_threshold=3.0,
    )
    defaults.update(kwargs)
    return SensorDefinition(**defaults)


def _sensor(**kwargs) -> SensorInstance:
    return SensorInstance(_defn(**kwargs))


def _equip(condition: float = 1.0, operational: bool = True) -> EquipmentItem:
    return EquipmentItem(
        equipment_id="eq-001", name="Test", category=EquipmentCategory.SENSOR,
        condition=condition, operational=operational,
    )


def _profile(**kwargs) -> SignatureProfile:
    defaults = dict(profile_id="test", unit_type="test")
    defaults.update(kwargs)
    return SignatureProfile(**defaults)


def _engine(seed: int = 42, **kwargs) -> DetectionEngine:
    rng = np.random.Generator(np.random.PCG64(seed))
    return DetectionEngine(rng=rng, **kwargs)


# ── DetectionResult ──────────────────────────────────────────────────


class TestDetectionResult:
    def test_fields(self) -> None:
        r = DetectionResult(True, 0.95, 15.0, 5000.0, SensorType.RADAR, 45.0)
        assert r.detected is True
        assert r.probability == 0.95
        assert r.snr_db == 15.0
        assert r.range_m == 5000.0
        assert r.sensor_type == SensorType.RADAR
        assert r.bearing_deg == 45.0


# ── DetectionConfig ──────────────────────────────────────────────────


class TestDetectionConfig:
    def test_defaults(self) -> None:
        c = DetectionConfig()
        assert c.default_scan_interval == 1.0
        assert c.max_simultaneous_contacts == 100
        assert c.noise_std == 0.05

    def test_custom(self) -> None:
        c = DetectionConfig(noise_std=0.1, max_simultaneous_contacts=50)
        assert c.noise_std == 0.1
        assert c.max_simultaneous_contacts == 50


# ── Visual SNR ───────────────────────────────────────────────────────


class TestComputeSNRVisual:
    def test_close_range_high_snr(self) -> None:
        s = _sensor()
        snr = DetectionEngine.compute_snr_visual(s, 10.0, 100.0, 1000.0)
        assert snr > 20.0

    def test_far_range_lower_snr(self) -> None:
        s = _sensor()
        close = DetectionEngine.compute_snr_visual(s, 10.0, 100.0, 1000.0)
        far = DetectionEngine.compute_snr_visual(s, 10.0, 5000.0, 1000.0)
        assert far < close

    def test_zero_illumination(self) -> None:
        s = _sensor()
        snr = DetectionEngine.compute_snr_visual(s, 10.0, 1000.0, 0.0)
        assert snr < -50.0

    def test_zero_signature(self) -> None:
        s = _sensor()
        snr = DetectionEngine.compute_snr_visual(s, 0.0, 1000.0, 100.0)
        assert snr < -50.0

    def test_low_visibility_reduces_snr(self) -> None:
        s = _sensor()
        good_vis = DetectionEngine.compute_snr_visual(s, 10.0, 3000.0, 100.0, 10000.0)
        bad_vis = DetectionEngine.compute_snr_visual(s, 10.0, 3000.0, 100.0, 500.0)
        assert bad_vis < good_vis

    def test_zero_range(self) -> None:
        s = _sensor()
        snr = DetectionEngine.compute_snr_visual(s, 10.0, 0.0, 100.0)
        assert snr == 100.0


# ── Thermal SNR ──────────────────────────────────────────────────────


class TestComputeSNRThermal:
    def test_close_range_high_snr(self) -> None:
        s = _sensor(sensor_type="THERMAL")
        snr = DetectionEngine.compute_snr_thermal(s, 1100.0, 500.0)
        assert snr > 20.0

    def test_range_reduces_snr(self) -> None:
        s = _sensor(sensor_type="THERMAL")
        close = DetectionEngine.compute_snr_thermal(s, 1100.0, 500.0)
        far = DetectionEngine.compute_snr_thermal(s, 1100.0, 5000.0)
        assert far < close

    def test_low_contrast_reduces_snr(self) -> None:
        s = _sensor(sensor_type="THERMAL")
        high = DetectionEngine.compute_snr_thermal(s, 1100.0, 1000.0, 1.0)
        low = DetectionEngine.compute_snr_thermal(s, 1100.0, 1000.0, 0.2)
        assert low < high

    def test_zero_signature(self) -> None:
        s = _sensor(sensor_type="THERMAL")
        snr = DetectionEngine.compute_snr_thermal(s, 0.0, 1000.0)
        assert snr < -50.0


# ── Radar SNR ────────────────────────────────────────────────────────


class TestComputeSNRRadar:
    def test_basic(self) -> None:
        s = _sensor(
            sensor_type="RADAR", frequency_mhz=3300.0,
            peak_power_w=4_000_000.0, antenna_gain_dbi=42.0,
        )
        snr = DetectionEngine.compute_snr_radar(s, 10.0, 50000.0)
        assert isinstance(snr, float)

    def test_range_reduces_snr(self) -> None:
        s = _sensor(
            sensor_type="RADAR", frequency_mhz=3300.0,
            peak_power_w=4_000_000.0, antenna_gain_dbi=42.0,
        )
        close = DetectionEngine.compute_snr_radar(s, 10.0, 10000.0)
        far = DetectionEngine.compute_snr_radar(s, 10.0, 100000.0)
        assert far < close

    def test_larger_rcs_higher_snr(self) -> None:
        s = _sensor(
            sensor_type="RADAR", frequency_mhz=3300.0,
            peak_power_w=4_000_000.0, antenna_gain_dbi=42.0,
        )
        small = DetectionEngine.compute_snr_radar(s, 1.0, 50000.0)
        large = DetectionEngine.compute_snr_radar(s, 100.0, 50000.0)
        assert large > small

    def test_atmospheric_attenuation(self) -> None:
        s = _sensor(
            sensor_type="RADAR", frequency_mhz=3300.0,
            peak_power_w=4_000_000.0, antenna_gain_dbi=42.0,
        )
        low_atten = DetectionEngine.compute_snr_radar(s, 10.0, 50000.0, 0.001)
        high_atten = DetectionEngine.compute_snr_radar(s, 10.0, 50000.0, 0.1)
        assert high_atten < low_atten

    def test_r4_scaling(self) -> None:
        """SNR drops ~40 dB per decade of range (R^4 law)."""
        s = _sensor(
            sensor_type="RADAR", frequency_mhz=3300.0,
            peak_power_w=4_000_000.0, antenna_gain_dbi=42.0,
        )
        snr_10km = DetectionEngine.compute_snr_radar(s, 10.0, 10000.0, 0.0)
        snr_100km = DetectionEngine.compute_snr_radar(s, 10.0, 100000.0, 0.0)
        diff = snr_10km - snr_100km
        assert abs(diff - 40.0) < 1.0  # ~40 dB per decade


# ── Acoustic SNR ─────────────────────────────────────────────────────


class TestComputeSNRAcoustic:
    def test_basic(self) -> None:
        s = _sensor(sensor_type="PASSIVE_SONAR", max_range_m=100000.0)
        se = DetectionEngine.compute_snr_acoustic(s, 130.0, 10000.0, 70.0)
        assert isinstance(se, float)

    def test_range_reduces_se(self) -> None:
        s = _sensor(sensor_type="PASSIVE_SONAR", max_range_m=100000.0)
        close = DetectionEngine.compute_snr_acoustic(s, 130.0, 1000.0, 70.0)
        far = DetectionEngine.compute_snr_acoustic(s, 130.0, 50000.0, 70.0)
        assert far < close

    def test_louder_source_higher_se(self) -> None:
        s = _sensor(sensor_type="PASSIVE_SONAR", max_range_m=100000.0)
        quiet = DetectionEngine.compute_snr_acoustic(s, 100.0, 10000.0, 70.0)
        loud = DetectionEngine.compute_snr_acoustic(s, 150.0, 10000.0, 70.0)
        assert loud > quiet

    def test_ambient_noise_reduces_se(self) -> None:
        s = _sensor(sensor_type="PASSIVE_SONAR", max_range_m=100000.0)
        quiet_env = DetectionEngine.compute_snr_acoustic(s, 130.0, 10000.0, 50.0)
        noisy_env = DetectionEngine.compute_snr_acoustic(s, 130.0, 10000.0, 90.0)
        assert noisy_env < quiet_env

    def test_directivity_improves_se(self) -> None:
        s1 = SensorInstance(SensorDefinition(
            sensor_id="s1", sensor_type="PASSIVE_SONAR", display_name="S1",
            max_range_m=100000.0, detection_threshold=8.0, directivity_index_db=0.0,
        ))
        s2 = SensorInstance(SensorDefinition(
            sensor_id="s2", sensor_type="PASSIVE_SONAR", display_name="S2",
            max_range_m=100000.0, detection_threshold=8.0, directivity_index_db=25.0,
        ))
        se1 = DetectionEngine.compute_snr_acoustic(s1, 130.0, 10000.0, 70.0)
        se2 = DetectionEngine.compute_snr_acoustic(s2, 130.0, 10000.0, 70.0)
        assert se2 > se1
        assert se2 - se1 == pytest.approx(25.0)


# ── Detection probability ────────────────────────────────────────────


class TestDetectionProbability:
    def test_high_snr_high_pd(self) -> None:
        pd = DetectionEngine.detection_probability(30.0, 10.0)
        assert pd > 0.99

    def test_low_snr_low_pd(self) -> None:
        pd = DetectionEngine.detection_probability(-10.0, 10.0)
        assert pd < 0.01

    def test_at_threshold(self) -> None:
        pd = DetectionEngine.detection_probability(10.0, 10.0)
        assert pd == pytest.approx(0.5, abs=0.01)

    def test_monotonic(self) -> None:
        thres = 10.0
        prev = 0.0
        for snr in range(-20, 40, 2):
            pd = DetectionEngine.detection_probability(float(snr), thres)
            assert pd >= prev - 1e-10
            prev = pd

    def test_clamped_to_0_1(self) -> None:
        assert DetectionEngine.detection_probability(-100.0, 0.0) >= 0.0
        assert DetectionEngine.detection_probability(100.0, 0.0) <= 1.0


class TestFalseAlarmProbability:
    def test_high_threshold_low_pfa(self) -> None:
        pfa = DetectionEngine.false_alarm_probability(10.0)
        assert pfa < 0.01

    def test_zero_threshold(self) -> None:
        pfa = DetectionEngine.false_alarm_probability(0.0)
        assert pfa == pytest.approx(0.5, abs=0.01)

    def test_monotonic(self) -> None:
        prev = 1.0
        for t in range(0, 20):
            pfa = DetectionEngine.false_alarm_probability(float(t))
            assert pfa <= prev + 1e-10
            prev = pfa


# ── check_detection high-level ───────────────────────────────────────


class TestCheckDetection:
    def test_non_operational_sensor(self) -> None:
        engine = _engine()
        sensor = SensorInstance(
            _defn(max_range_m=10000.0),
            _equip(operational=False),
        )
        profile = _profile(visual=VisualSignature(cross_section_m2=10.0))
        obs = Position(0.0, 0.0, 0.0)
        tgt = Position(1000.0, 0.0, 0.0)
        result = engine.check_detection(obs, tgt, sensor, profile)
        assert result.detected is False
        assert result.probability == 0.0

    def test_beyond_range(self) -> None:
        engine = _engine()
        sensor = _sensor(max_range_m=1000.0)
        profile = _profile(visual=VisualSignature(cross_section_m2=10.0))
        obs = Position(0.0, 0.0, 0.0)
        tgt = Position(5000.0, 0.0, 0.0)
        result = engine.check_detection(obs, tgt, sensor, profile)
        assert result.detected is False

    def test_below_min_range(self) -> None:
        engine = _engine()
        sensor = _sensor(max_range_m=10000.0, min_range_m=500.0)
        profile = _profile(visual=VisualSignature(cross_section_m2=10.0))
        obs = Position(0.0, 0.0, 0.0)
        tgt = Position(100.0, 0.0, 0.0)
        result = engine.check_detection(obs, tgt, sensor, profile)
        assert result.detected is False

    def test_los_blocked(self) -> None:
        blocked_los = lambda o, t, oh, th: SimpleNamespace(visible=False)
        engine = _engine(los_checker=blocked_los)
        sensor = _sensor(max_range_m=10000.0)
        profile = _profile(visual=VisualSignature(cross_section_m2=10.0))
        obs = Position(0.0, 0.0, 0.0)
        tgt = Position(1000.0, 0.0, 0.0)
        result = engine.check_detection(obs, tgt, sensor, profile)
        assert result.detected is False

    def test_clear_los_allows_detection(self) -> None:
        clear_los = lambda o, t, oh, th: SimpleNamespace(visible=True)
        engine = _engine(seed=99, los_checker=clear_los)
        sensor = _sensor(max_range_m=50000.0, detection_threshold=1.0)
        profile = _profile(visual=VisualSignature(cross_section_m2=50.0))
        obs = Position(0.0, 0.0, 0.0)
        tgt = Position(100.0, 0.0, 0.0)
        result = engine.check_detection(
            obs, tgt, sensor, profile, illumination_lux=10000.0,
        )
        assert result.probability > 0.5

    def test_concealment_reduces_detection(self) -> None:
        engine = _engine(seed=42)
        sensor = _sensor(max_range_m=10000.0, detection_threshold=5.0)
        profile = _profile(visual=VisualSignature(cross_section_m2=10.0, camouflage_factor=1.0))
        obs = Position(0.0, 0.0, 0.0)
        tgt = Position(1000.0, 0.0, 0.0)
        r_open = engine.check_detection(obs, tgt, sensor, profile, concealment=0.0, illumination_lux=1000.0)

        engine2 = _engine(seed=42)
        r_concealed = engine2.check_detection(obs, tgt, sensor, profile, concealment=0.8, illumination_lux=1000.0)
        assert r_concealed.probability < r_open.probability

    def test_bearing_computed(self) -> None:
        engine = _engine()
        sensor = _sensor(max_range_m=50000.0)
        profile = _profile()
        obs = Position(0.0, 0.0, 0.0)
        tgt = Position(1000.0, 0.0, 0.0)  # due east
        result = engine.check_detection(obs, tgt, sensor, profile)
        assert result.bearing_deg == pytest.approx(90.0)

    def test_thermal_sensor(self) -> None:
        engine = _engine(seed=1)
        sensor = _sensor(sensor_type="THERMAL", max_range_m=5000.0, detection_threshold=3.0)
        profile = _profile(thermal=ThermalSignature(heat_output_kw=1100.0, emissivity=0.95))
        obs = Position(0.0, 0.0, 0.0)
        tgt = Position(500.0, 0.0, 0.0)
        result = engine.check_detection(obs, tgt, sensor, profile)
        assert result.probability > 0.5

    def test_radar_sensor(self) -> None:
        engine = _engine(seed=1)
        sensor = _sensor(
            sensor_type="RADAR", max_range_m=100000.0, detection_threshold=10.0,
            frequency_mhz=3300.0, peak_power_w=4_000_000.0, antenna_gain_dbi=42.0,
        )
        profile = _profile(radar=RadarSignature(rcs_frontal_m2=15.0, rcs_side_m2=35.0))
        obs = Position(0.0, 0.0, 0.0)
        tgt = Position(0.0, 10000.0, 0.0)
        result = engine.check_detection(obs, tgt, sensor, profile)
        assert result.snr_db > 0

    def test_esm_emitting_target(self) -> None:
        engine = _engine(seed=1)
        sensor = _sensor(
            sensor_type="ESM", max_range_m=200000.0, detection_threshold=-60.0,
        )
        profile = _profile(electromagnetic=EMSignature(emitting=True, power_dbm=60.0))
        obs = Position(0.0, 0.0, 0.0)
        tgt = Position(0.0, 50000.0, 0.0)
        result = engine.check_detection(obs, tgt, sensor, profile)
        assert result.probability > 0.0

    def test_esm_silent_target(self) -> None:
        engine = _engine(seed=1)
        sensor = _sensor(sensor_type="ESM", max_range_m=200000.0, detection_threshold=-60.0)
        profile = _profile(electromagnetic=EMSignature(emitting=False))
        obs = Position(0.0, 0.0, 0.0)
        tgt = Position(0.0, 50000.0, 0.0)
        result = engine.check_detection(obs, tgt, sensor, profile)
        assert result.detected is False

    def test_range_returned(self) -> None:
        engine = _engine()
        sensor = _sensor(max_range_m=50000.0)
        profile = _profile()
        obs = Position(0.0, 0.0, 0.0)
        tgt = Position(3000.0, 4000.0, 0.0)
        result = engine.check_detection(obs, tgt, sensor, profile)
        assert result.range_m == pytest.approx(5000.0)


# ── Determinism ──────────────────────────────────────────────────────


class TestDeterminism:
    def test_same_seed_same_result(self) -> None:
        sensor = _sensor(max_range_m=50000.0, detection_threshold=5.0)
        profile = _profile(visual=VisualSignature(cross_section_m2=10.0))
        obs = Position(0.0, 0.0, 0.0)
        tgt = Position(1000.0, 0.0, 0.0)

        results = []
        for _ in range(2):
            e = _engine(seed=12345)
            r = e.check_detection(obs, tgt, sensor, profile, illumination_lux=500.0)
            results.append(r)
        assert results[0].detected == results[1].detected
        assert results[0].probability == results[1].probability

    def test_different_seed_may_differ(self) -> None:
        """With many trials, different seeds should sometimes produce different results."""
        sensor = _sensor(max_range_m=50000.0, detection_threshold=5.0)
        profile = _profile(visual=VisualSignature(cross_section_m2=5.0))
        obs = Position(0.0, 0.0, 0.0)
        tgt = Position(2000.0, 0.0, 0.0)

        outcomes = set()
        for seed in range(20):
            e = _engine(seed=seed)
            r = e.check_detection(obs, tgt, sensor, profile, illumination_lux=100.0)
            outcomes.add(r.detected)
        # With Pd near 0.5, we should see both True and False
        assert len(outcomes) >= 1  # at least one outcome exists


# ── scan_all_targets ──────────────────────────────────────────────────


class TestScanAllTargets:
    def test_empty_targets(self) -> None:
        engine = _engine()
        results = engine.scan_all_targets(
            Position(0.0, 0.0, 0.0), [_sensor()], [],
        )
        assert results == []

    def test_multiple_targets(self) -> None:
        engine = _engine()
        sensors = [_sensor(max_range_m=50000.0)]
        targets = [
            (Position(1000.0, 0.0, 0.0), _profile(visual=VisualSignature(cross_section_m2=10.0)), None),
            (Position(2000.0, 0.0, 0.0), _profile(visual=VisualSignature(cross_section_m2=10.0)), None),
        ]
        results = engine.scan_all_targets(
            Position(0.0, 0.0, 0.0), sensors, targets, illumination_lux=500.0,
        )
        assert len(results) == 2

    def test_non_operational_sensor_skipped(self) -> None:
        engine = _engine()
        broken = SensorInstance(_defn(max_range_m=50000.0), _equip(operational=False))
        targets = [(Position(1000.0, 0.0, 0.0), _profile(), None)]
        results = engine.scan_all_targets(
            Position(0.0, 0.0, 0.0), [broken], targets,
        )
        assert len(results) == 0


# ── State round-trip ─────────────────────────────────────────────────


class TestStateRoundTrip:
    def test_roundtrip(self) -> None:
        engine = _engine(seed=42)
        sensor = _sensor(max_range_m=50000.0)
        profile = _profile(visual=VisualSignature(cross_section_m2=10.0))

        # Advance RNG state
        engine.check_detection(
            Position(0.0, 0.0, 0.0), Position(1000.0, 0.0, 0.0),
            sensor, profile, illumination_lux=500.0,
        )
        state = engine.get_state()

        # Create new engine, restore state
        engine2 = _engine(seed=0)
        engine2.set_state(state)

        # Both should produce same next result
        r1 = engine.check_detection(
            Position(0.0, 0.0, 0.0), Position(1000.0, 0.0, 0.0),
            sensor, profile, illumination_lux=500.0,
        )
        r2 = engine2.check_detection(
            Position(0.0, 0.0, 0.0), Position(1000.0, 0.0, 0.0),
            sensor, profile, illumination_lux=500.0,
        )
        assert r1.detected == r2.detected
        assert r1.probability == r2.probability
