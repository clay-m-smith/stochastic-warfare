"""Tests for detection/sonar.py — active and passive sonar models."""

from __future__ import annotations


import numpy as np
import pytest

from stochastic_warfare.detection.sensors import SensorDefinition, SensorInstance
from stochastic_warfare.detection.sonar import (
    SonarEngine,
    SonarMode,
    SonarType,
)


# ── helpers ──────────────────────────────────────────────────────────


def _engine(seed: int = 42) -> SonarEngine:
    return SonarEngine(rng=np.random.Generator(np.random.PCG64(seed)))


def _passive_sensor(**kwargs) -> SensorInstance:
    defaults = dict(
        sensor_id="passive", sensor_type="PASSIVE_SONAR", display_name="Passive",
        max_range_m=100000.0, detection_threshold=8.0, directivity_index_db=25.0,
    )
    defaults.update(kwargs)
    return SensorInstance(SensorDefinition(**defaults))


def _active_sensor(**kwargs) -> SensorInstance:
    defaults = dict(
        sensor_id="active", sensor_type="ACTIVE_SONAR", display_name="Active",
        max_range_m=50000.0, detection_threshold=6.0,
        source_level_db=235.0, directivity_index_db=20.0,
    )
    defaults.update(kwargs)
    return SensorInstance(SensorDefinition(**defaults))


# ── Enums ─────────────────────────────────────────────────────────────


class TestEnums:
    def test_sonar_mode(self) -> None:
        assert SonarMode.ACTIVE == 0
        assert SonarMode.PASSIVE == 1

    def test_sonar_type(self) -> None:
        assert SonarType.HULL_MOUNTED == 0
        assert SonarType.TOWED_ARRAY == 1
        assert SonarType.SONOBUOY == 2
        assert SonarType.DIPPING == 3


# ── Passive sonar ─────────────────────────────────────────────────────


class TestPassiveDetection:
    def test_loud_target_detected(self) -> None:
        engine = _engine()
        sensor = _passive_sensor()
        result = engine.passive_detection(
            sensor, observer_depth=100.0, target_noise_db=140.0,
            target_depth=200.0, range_m=10000.0, ambient_noise_db=70.0,
        )
        assert result.signal_excess_db > 0
        # Loud target should be detected
        assert result.detected is True

    def test_quiet_target_not_detected(self) -> None:
        engine = _engine()
        sensor = _passive_sensor(detection_threshold=20.0)
        result = engine.passive_detection(
            sensor, observer_depth=100.0, target_noise_db=80.0,
            target_depth=200.0, range_m=50000.0, ambient_noise_db=90.0,
        )
        # Very quiet target at range in noisy env
        assert result.signal_excess_db < 20.0

    def test_range_reduces_se(self) -> None:
        engine1 = _engine(seed=1)
        engine2 = _engine(seed=2)
        sensor = _passive_sensor()
        r_close = engine1.passive_detection(
            sensor, 100.0, 130.0, 200.0, 1000.0, 70.0,
        )
        r_far = engine2.passive_detection(
            sensor, 100.0, 130.0, 200.0, 50000.0, 70.0,
        )
        assert r_far.signal_excess_db < r_close.signal_excess_db

    def test_passive_no_range_estimate(self) -> None:
        engine = _engine()
        sensor = _passive_sensor()
        result = engine.passive_detection(
            sensor, 100.0, 140.0, 200.0, 10000.0, 70.0,
        )
        assert result.range_estimate == -1.0

    def test_bearing_returned(self) -> None:
        engine = _engine()
        sensor = _passive_sensor()
        result = engine.passive_detection(
            sensor, 100.0, 140.0, 200.0, 10000.0, 70.0,
        )
        assert 0.0 <= result.bearing_deg < 360.0

    def test_hull_mounted_bearing_uncertainty(self) -> None:
        engine = _engine()
        sensor = _passive_sensor()
        result = engine.passive_detection(
            sensor, 100.0, 140.0, 200.0, 10000.0, 70.0,
            sonar_type=SonarType.HULL_MOUNTED,
        )
        assert result.bearing_uncertainty_deg == 3.0

    def test_towed_array_better_bearing(self) -> None:
        engine = _engine()
        sensor = _passive_sensor()
        result = engine.passive_detection(
            sensor, 100.0, 140.0, 200.0, 10000.0, 70.0,
            sonar_type=SonarType.TOWED_ARRAY,
        )
        assert result.bearing_uncertainty_deg == 1.0

    def test_ambient_noise_reduces_se(self) -> None:
        engine1 = _engine(seed=1)
        engine2 = _engine(seed=2)
        sensor = _passive_sensor()
        r_quiet = engine1.passive_detection(
            sensor, 100.0, 130.0, 200.0, 10000.0, 50.0,
        )
        r_noisy = engine2.passive_detection(
            sensor, 100.0, 130.0, 200.0, 10000.0, 90.0,
        )
        assert r_noisy.signal_excess_db < r_quiet.signal_excess_db

    def test_contact_strength(self) -> None:
        engine = _engine()
        sensor = _passive_sensor()
        result = engine.passive_detection(
            sensor, 100.0, 180.0, 200.0, 1000.0, 50.0,
        )
        assert result.contact_strength in ("weak", "moderate", "strong")


# ── Active sonar ──────────────────────────────────────────────────────


class TestActiveDetection:
    def test_provides_range(self) -> None:
        engine = _engine()
        sensor = _active_sensor()
        result = engine.active_detection(
            sensor, observer_depth=50.0, target_rcs_db=15.0,
            target_depth=200.0, range_m=10000.0, ambient_noise_db=70.0,
        )
        assert result.range_estimate > 0

    def test_two_way_tl(self) -> None:
        """Active sonar has 2× TL compared to passive."""
        engine1 = _engine(seed=1)
        engine2 = _engine(seed=2)
        sensor = _active_sensor()
        r_close = engine1.active_detection(
            sensor, 50.0, 15.0, 200.0, 5000.0, 70.0,
        )
        r_far = engine2.active_detection(
            sensor, 50.0, 15.0, 200.0, 30000.0, 70.0,
        )
        assert r_far.signal_excess_db < r_close.signal_excess_db

    def test_better_bearing(self) -> None:
        engine = _engine()
        sensor = _active_sensor()
        result = engine.active_detection(
            sensor, 50.0, 15.0, 200.0, 10000.0, 70.0,
        )
        assert result.bearing_uncertainty_deg == 2.0

    def test_range_uncertainty(self) -> None:
        engine = _engine()
        sensor = _active_sensor()
        result = engine.active_detection(
            sensor, 50.0, 15.0, 200.0, 10000.0, 70.0,
        )
        assert result.range_uncertainty == pytest.approx(500.0)  # 5% of 10000


# ── Convergence zone ──────────────────────────────────────────────────


class TestConvergenceZone:
    def test_in_cz(self) -> None:
        assert SonarEngine.convergence_zone_check(55000.0) is True

    def test_outside_cz(self) -> None:
        assert SonarEngine.convergence_zone_check(30000.0) is False

    def test_second_cz(self) -> None:
        assert SonarEngine.convergence_zone_check(110000.0) is True

    def test_custom_cz_ranges(self) -> None:
        assert SonarEngine.convergence_zone_check(20000.0, [20000.0]) is True

    def test_edge_of_cz(self) -> None:
        # Default width = 5000, so 55000 ± 2500
        assert SonarEngine.convergence_zone_check(57499.0) is True
        assert SonarEngine.convergence_zone_check(58000.0) is False


# ── Towed array bearing ambiguity ─────────────────────────────────────


class TestTowedArrayBearing:
    def test_basic(self) -> None:
        left, right = SonarEngine.towed_array_bearing(0.0, 90.0)
        assert isinstance(left, float)
        assert isinstance(right, float)

    def test_symmetry(self) -> None:
        """Left and right bearings should be symmetric about array axis."""
        left, right = SonarEngine.towed_array_bearing(0.0, 225.0)
        # Array axis is at 180° (stern). Relative = 45°. Mirror = 180-45=135° from north.
        assert left != right


# ── State round-trip ──────────────────────────────────────────────────


class TestStateRoundTrip:
    def test_roundtrip(self) -> None:
        engine = _engine(seed=42)
        sensor = _passive_sensor()
        engine.passive_detection(sensor, 100.0, 140.0, 200.0, 10000.0, 70.0)
        state = engine.get_state()

        engine2 = _engine(seed=0)
        engine2.set_state(state)

        r1 = engine.passive_detection(sensor, 100.0, 130.0, 200.0, 20000.0, 70.0)
        r2 = engine2.passive_detection(sensor, 100.0, 130.0, 200.0, 20000.0, 70.0)
        assert r1.detected == r2.detected
        assert r1.signal_excess_db == pytest.approx(r2.signal_excess_db)
