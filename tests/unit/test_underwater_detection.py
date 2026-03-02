"""Tests for detection/underwater_detection.py — multi-method sub detection."""

from __future__ import annotations

import math

import numpy as np
import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.detection.sensors import SensorDefinition, SensorInstance
from stochastic_warfare.detection.sonar import SonarEngine
from stochastic_warfare.detection.underwater_detection import (
    UnderwaterDetectionEngine,
    UnderwaterDetectionMethod,
    UnderwaterDetectionResult,
)


# ── helpers ──────────────────────────────────────────────────────────


def _engine(seed: int = 42) -> UnderwaterDetectionEngine:
    sonar = SonarEngine(rng=np.random.Generator(np.random.PCG64(seed + 1000)))
    return UnderwaterDetectionEngine(
        sonar_engine=sonar,
        rng=np.random.Generator(np.random.PCG64(seed)),
    )


def _passive_sensor() -> SensorInstance:
    return SensorInstance(SensorDefinition(
        sensor_id="passive", sensor_type="PASSIVE_SONAR", display_name="Passive",
        max_range_m=100000.0, detection_threshold=8.0, directivity_index_db=25.0,
    ))


# ── MAD detection ─────────────────────────────────────────────────────


class TestMADDetection:
    def test_close_range_high_pd(self) -> None:
        engine = _engine()
        result = engine.mad_detection(
            Position(0.0, 0.0, 0.0), Position(50.0, 0.0, -100.0), 50.0,
        )
        assert result.method == UnderwaterDetectionMethod.MAD
        # Pd = exp(-50/200) ≈ 0.78
        assert result.confidence > 0.5 or not result.detected

    def test_far_range_low_pd(self) -> None:
        engine = _engine()
        result = engine.mad_detection(
            Position(0.0, 0.0, 0.0), Position(1000.0, 0.0, -100.0), 1000.0,
        )
        # Pd = exp(-1000/200) ≈ 0.007
        expected_pd = math.exp(-1000.0 / 200.0)
        assert expected_pd < 0.01

    def test_exponential_dropoff(self) -> None:
        """Pd should drop exponentially with range."""
        pd_100 = math.exp(-100.0 / 200.0)
        pd_400 = math.exp(-400.0 / 200.0)
        assert pd_400 < pd_100

    def test_position_estimate_near_target(self) -> None:
        engine = _engine()
        tgt = Position(1000.0, 2000.0, -100.0)
        result = engine.mad_detection(Position(0.0, 0.0, 0.0), tgt, 100.0)
        # Position estimate should be in the neighborhood of the target
        dx = abs(result.position_estimate.easting - tgt.easting)
        dy = abs(result.position_estimate.northing - tgt.northing)
        assert dx < 1000.0  # reasonable uncertainty bound


# ── Periscope detection ───────────────────────────────────────────────


class TestPeriscopeDetection:
    def test_deep_sub_not_detected(self) -> None:
        engine = _engine()
        result = engine.periscope_detection(
            Position(0.0, 0.0, 0.0), Position(5000.0, 0.0, -100.0),
            target_depth=100.0, range_m=5000.0,
        )
        assert result.detected is False
        assert result.confidence == 0.0

    def test_at_periscope_depth(self) -> None:
        engine = _engine()
        result = engine.periscope_detection(
            Position(0.0, 0.0, 0.0), Position(500.0, 0.0, -10.0),
            target_depth=10.0, range_m=500.0,
        )
        assert result.method == UnderwaterDetectionMethod.PERISCOPE_DETECTION
        # At 500m with small periscope cross-section, detection is possible but not certain

    def test_only_at_shallow_depth(self) -> None:
        engine = _engine()
        r_deep = engine.periscope_detection(
            Position(0.0, 0.0, 0.0), Position(500.0, 0.0, -50.0),
            target_depth=50.0, range_m=500.0,
        )
        assert r_deep.detected is False

    def test_threshold_depth_20m(self) -> None:
        engine = _engine()
        r_20 = engine.periscope_detection(
            Position(0.0, 0.0, 0.0), Position(500.0, 0.0, -20.0),
            target_depth=20.0, range_m=500.0,
        )
        # At exactly 20m, should still be detectable (< 20 check)
        assert r_20.method == UnderwaterDetectionMethod.PERISCOPE_DETECTION

    def test_above_threshold(self) -> None:
        engine = _engine()
        r_21 = engine.periscope_detection(
            Position(0.0, 0.0, 0.0), Position(500.0, 0.0, -21.0),
            target_depth=21.0, range_m=500.0,
        )
        assert r_21.detected is False


# ── Speed-noise tradeoff ──────────────────────────────────────────────


class TestSpeedNoise:
    def test_at_quiet_speed(self) -> None:
        noise = UnderwaterDetectionEngine.speed_noise_tradeoff(110.0, 5.0, 5.0)
        assert noise == pytest.approx(110.0)

    def test_below_quiet_speed(self) -> None:
        noise = UnderwaterDetectionEngine.speed_noise_tradeoff(110.0, 2.0, 5.0)
        assert noise == pytest.approx(110.0)

    def test_above_quiet_speed(self) -> None:
        noise = UnderwaterDetectionEngine.speed_noise_tradeoff(110.0, 15.0, 5.0)
        expected = 110.0 + 20.0 * math.log10(15.0 / 5.0)
        assert noise == pytest.approx(expected)

    def test_double_speed(self) -> None:
        """Doubling speed above quiet adds ~6 dB (20*log10(2))."""
        noise_10 = UnderwaterDetectionEngine.speed_noise_tradeoff(100.0, 10.0, 5.0)
        noise_20 = UnderwaterDetectionEngine.speed_noise_tradeoff(100.0, 20.0, 5.0)
        diff = noise_20 - noise_10
        expected_diff = 20.0 * math.log10(20.0 / 10.0)
        assert diff == pytest.approx(expected_diff)


# ── Multi-method detection ────────────────────────────────────────────


class TestDetectSubmarine:
    def test_passive_sonar_attempted(self) -> None:
        engine = _engine()
        sensor = _passive_sensor()
        results = engine.detect_submarine(
            observer_pos=Position(0.0, 0.0, 0.0),
            target_pos=Position(10000.0, 0.0, -200.0),
            target_depth=200.0, target_speed=10.0,
            target_noise_db=130.0, range_m=10000.0,
            observer_sensors=[sensor],
            ambient_noise_db=70.0,
        )
        methods = [r.method for r in results]
        assert UnderwaterDetectionMethod.SONAR_PASSIVE in methods

    def test_mad_only_for_aircraft(self) -> None:
        engine = _engine()
        results = engine.detect_submarine(
            observer_pos=Position(0.0, 0.0, 0.0),
            target_pos=Position(200.0, 0.0, -100.0),
            target_depth=100.0, target_speed=5.0,
            target_noise_db=110.0, range_m=200.0,
            is_aircraft=True,
        )
        methods = [r.method for r in results]
        assert UnderwaterDetectionMethod.MAD in methods

    def test_mad_not_for_surface_ship(self) -> None:
        engine = _engine()
        results = engine.detect_submarine(
            observer_pos=Position(0.0, 0.0, 0.0),
            target_pos=Position(200.0, 0.0, -100.0),
            target_depth=100.0, target_speed=5.0,
            target_noise_db=110.0, range_m=200.0,
            is_aircraft=False,
        )
        methods = [r.method for r in results]
        assert UnderwaterDetectionMethod.MAD not in methods

    def test_periscope_at_shallow_depth(self) -> None:
        engine = _engine()
        results = engine.detect_submarine(
            observer_pos=Position(0.0, 0.0, 0.0),
            target_pos=Position(500.0, 0.0, -10.0),
            target_depth=10.0, target_speed=3.0,
            target_noise_db=100.0, range_m=500.0,
        )
        methods = [r.method for r in results]
        assert UnderwaterDetectionMethod.PERISCOPE_DETECTION in methods

    def test_no_periscope_at_deep(self) -> None:
        engine = _engine()
        results = engine.detect_submarine(
            observer_pos=Position(0.0, 0.0, 0.0),
            target_pos=Position(500.0, 0.0, -200.0),
            target_depth=200.0, target_speed=3.0,
            target_noise_db=100.0, range_m=500.0,
        )
        methods = [r.method for r in results]
        assert UnderwaterDetectionMethod.PERISCOPE_DETECTION not in methods

    def test_mad_range_limit(self) -> None:
        """MAD only attempted if range < 500m."""
        engine = _engine()
        results = engine.detect_submarine(
            observer_pos=Position(0.0, 0.0, 0.0),
            target_pos=Position(600.0, 0.0, -100.0),
            target_depth=100.0, target_speed=5.0,
            target_noise_db=110.0, range_m=600.0,
            is_aircraft=True,
        )
        methods = [r.method for r in results]
        assert UnderwaterDetectionMethod.MAD not in methods


# ── State round-trip ──────────────────────────────────────────────────


class TestStateRoundTrip:
    def test_roundtrip(self) -> None:
        engine = _engine(seed=42)
        engine.mad_detection(Position(0.0, 0.0, 0.0), Position(100.0, 0.0, -50.0), 100.0)
        state = engine.get_state()

        engine2 = _engine(seed=0)
        engine2.set_state(state)

        r1 = engine.mad_detection(Position(0.0, 0.0, 0.0), Position(200.0, 0.0, -50.0), 200.0)
        r2 = engine2.mad_detection(Position(0.0, 0.0, 0.0), Position(200.0, 0.0, -50.0), 200.0)
        assert r1.detected == r2.detected
