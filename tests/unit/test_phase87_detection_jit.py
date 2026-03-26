"""Phase 87a: Detection SNR JIT kernel tests.

Validates that JIT-extracted kernels produce identical results to the
original DetectionEngine static methods, including edge cases.
"""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from stochastic_warfare.detection.detection import (
    DetectionEngine,
    _detection_probability_kernel,
    _snr_acoustic_kernel,
    _snr_radar_kernel,
    _snr_thermal_kernel,
    _snr_visual_kernel,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sensor(sensor_type="VISUAL", **kwargs):
    """Minimal sensor mock for static method calls."""
    defn = SimpleNamespace(
        peak_power_w=kwargs.get("peak_power_w", 1000.0),
        antenna_gain_dbi=kwargs.get("antenna_gain_dbi", 30.0),
        frequency_mhz=kwargs.get("frequency_mhz", 3000.0),
        directivity_index_db=kwargs.get("directivity_index_db", 10.0),
        source_level_db=kwargs.get("source_level_db", 200.0),
    )
    return SimpleNamespace(definition=defn, sensor_type=sensor_type)


# ---------------------------------------------------------------------------
# 87a: Visual SNR kernel
# ---------------------------------------------------------------------------


class TestSNRVisualKernel:
    def test_matches_method_typical(self):
        sensor = _make_sensor()
        sig, rng, lux, vis = 5.0, 2000.0, 100.0, 10000.0
        expected = DetectionEngine.compute_snr_visual(sensor, sig, rng, lux, vis)
        actual = _snr_visual_kernel(sig, rng, lux, vis)
        assert actual == pytest.approx(expected, abs=1e-10)

    def test_zero_range(self):
        assert _snr_visual_kernel(5.0, 0.0, 100.0, 10000.0) == 100.0

    def test_zero_signature(self):
        assert _snr_visual_kernel(0.0, 1000.0, 100.0, 10000.0) == -100.0

    def test_low_visibility(self):
        sensor = _make_sensor()
        sig, rng, lux, vis = 5.0, 1000.0, 100.0, 100.0
        expected = DetectionEngine.compute_snr_visual(sensor, sig, rng, lux, vis)
        actual = _snr_visual_kernel(sig, rng, lux, vis)
        assert actual == pytest.approx(expected, abs=1e-10)


# ---------------------------------------------------------------------------
# 87a: Thermal SNR kernel
# ---------------------------------------------------------------------------


class TestSNRThermalKernel:
    def test_matches_method_typical(self):
        sensor = _make_sensor()
        sig, rng, tc = 3.0, 1500.0, 2.0
        expected = DetectionEngine.compute_snr_thermal(sensor, sig, rng, tc)
        actual = _snr_thermal_kernel(sig, rng, tc)
        assert actual == pytest.approx(expected, abs=1e-10)

    def test_zero_range(self):
        assert _snr_thermal_kernel(3.0, 0.0, 1.0) == 100.0

    def test_zero_signature(self):
        assert _snr_thermal_kernel(0.0, 1000.0, 1.0) == -100.0


# ---------------------------------------------------------------------------
# 87a: Radar SNR kernel
# ---------------------------------------------------------------------------


class TestSNRRadarKernel:
    def test_matches_method_typical(self):
        sensor = _make_sensor(peak_power_w=5000.0, antenna_gain_dbi=35.0, frequency_mhz=9000.0)
        rcs, rng, atten = 10.0, 20000.0, 0.01
        expected = DetectionEngine.compute_snr_radar(sensor, rcs, rng, atten)
        actual = _snr_radar_kernel(5000.0, 35.0, 9000.0, rcs, rng, atten)
        assert actual == pytest.approx(expected, abs=1e-10)

    def test_zero_range(self):
        assert _snr_radar_kernel(1000.0, 30.0, 3000.0, 5.0, 0.0, 0.01) == 100.0

    def test_sensor_defaults(self):
        """When sensor fields are None, method defaults to 1000/0/3000."""
        sensor = _make_sensor(peak_power_w=None, antenna_gain_dbi=None, frequency_mhz=None)
        expected = DetectionEngine.compute_snr_radar(sensor, 5.0, 10000.0, 0.01)
        actual = _snr_radar_kernel(1000.0, 0.0, 3000.0, 5.0, 10000.0, 0.01)
        assert actual == pytest.approx(expected, abs=1e-10)


# ---------------------------------------------------------------------------
# 87a: Acoustic SNR kernel
# ---------------------------------------------------------------------------


class TestSNRAcousticKernel:
    def test_matches_method_no_override(self):
        sensor = _make_sensor(directivity_index_db=12.0)
        sl, rng, nl = 160.0, 5000.0, 70.0
        expected = DetectionEngine.compute_snr_acoustic(sensor, sl, rng, nl, None)
        actual = _snr_acoustic_kernel(sl, rng, nl, 12.0, -1.0)
        assert actual == pytest.approx(expected, abs=1e-10)

    def test_matches_method_with_override(self):
        sensor = _make_sensor(directivity_index_db=12.0)
        sl, rng, nl, tl = 160.0, 5000.0, 70.0, 80.0
        expected = DetectionEngine.compute_snr_acoustic(sensor, sl, rng, nl, tl)
        actual = _snr_acoustic_kernel(sl, rng, nl, 12.0, tl)
        assert actual == pytest.approx(expected, abs=1e-10)

    def test_zero_range(self):
        assert _snr_acoustic_kernel(160.0, 0.0, 70.0, 10.0, -1.0) == 100.0


# ---------------------------------------------------------------------------
# 87a: Detection probability kernel
# ---------------------------------------------------------------------------


class TestDetectionProbabilityKernel:
    def test_matches_method(self):
        for snr, thresh in [(10.0, 5.0), (5.0, 5.0), (0.0, 5.0), (-10.0, 5.0), (20.0, 10.0)]:
            expected = DetectionEngine.detection_probability(snr, thresh)
            actual = _detection_probability_kernel(snr, thresh)
            assert actual == pytest.approx(expected, abs=1e-10), f"Mismatch at SNR={snr}, thresh={thresh}"

    def test_high_snr_near_one(self):
        pd = _detection_probability_kernel(50.0, 5.0)
        assert pd == pytest.approx(1.0, abs=1e-6)

    def test_low_snr_near_zero(self):
        pd = _detection_probability_kernel(-50.0, 5.0)
        assert pd == pytest.approx(0.0, abs=1e-6)

    def test_math_erfc_vs_scipy_erfc(self):
        """Verify math.erfc matches scipy.special.erfc for typical inputs."""
        from scipy.special import erfc as scipy_erfc
        for x in [-3.0, -1.0, 0.0, 1.0, 3.0, 5.0]:
            assert math.erfc(x) == pytest.approx(float(scipy_erfc(x)), abs=1e-15)
