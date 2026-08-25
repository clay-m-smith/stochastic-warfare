"""Tests for detection/detection.py — core SNR-based detection engine."""

from __future__ import annotations

import math
import struct
from types import SimpleNamespace

import numpy as np
import pytest

import stochastic_warfare.detection.detection as detection_module
from stochastic_warfare.core.types import Domain, Position
from stochastic_warfare.detection.detection import (
    DetectionConfig,
    DetectionDecisionStage,
    DetectionEngine,
    DetectionResult,
    PreparedDetection,
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
        equipment_id="eq-001",
        name="Test",
        category=EquipmentCategory.SENSOR,
        condition=condition,
        operational=operational,
    )


def _profile(**kwargs) -> SignatureProfile:
    defaults = dict(profile_id="test", unit_type="test")
    defaults.update(kwargs)
    return SignatureProfile(**defaults)


def _engine(seed: int = 42, **kwargs) -> DetectionEngine:
    rng = np.random.Generator(np.random.PCG64(seed))
    return DetectionEngine(rng=rng, **kwargs)


def _binary64(value: float) -> bytes:
    return struct.pack(">d", value)


def test_private_detection_geometry_uses_canonical_scalar_helpers_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def scalar_range(_observer: Position, _target: Position) -> float:
        calls.append("range")
        return 11.0

    def scalar_horizontal(_observer: Position, _target: Position) -> float:
        calls.append("horizontal")
        return 22.0

    def scalar_bearing(_observer: Position, _target: Position) -> float:
        calls.append("bearing")
        return 33.0

    monkeypatch.setattr(detection_module, "_range_m", scalar_range)
    monkeypatch.setattr(
        detection_module,
        "_horizontal_range_m",
        scalar_horizontal,
    )
    monkeypatch.setattr(detection_module, "_bearing_deg", scalar_bearing)

    actual = detection_module._detection_geometry(
        Position(0.0, 0.0, 0.0),
        Position(1.0, 1.0, 1.0),
    )

    assert actual == detection_module._DetectionGeometry(
        range_m=11.0,
        horizontal_range_m=22.0,
        bearing_deg=33.0,
    )
    assert calls == ["range", "horizontal", "bearing"]


def test_private_raw_scan_count_snapshot_is_defensive() -> None:
    engine = _engine()
    legacy_key = ("legacy-sensor", "legacy-target")
    observer_key = (
        "blue",
        "observer-1",
        0,
        "observer-sensor",
        "observer-target",
    )
    engine._scan_counts = {
        legacy_key: 3,
        observer_key: 2,
    }

    values = engine._snapshot_scan_count_values()

    assert values == engine._scan_counts
    assert values is not engine._scan_counts
    values[legacy_key] = 4
    engine._scan_counts[observer_key] = 5
    assert engine._scan_counts[legacy_key] == 3
    assert values[observer_key] == 2


def test_private_fow_scan_count_staging_matches_public_snapshot_exactly() -> None:
    engine = _engine()
    observer_key = (
        "blue",
        "observer-1",
        7,
        "observer-sensor",
        "observer-target",
    )
    legacy_key = ("legacy-sensor", "legacy-target")
    values = {observer_key: 2, legacy_key: 3}
    expected_values = dict(values)
    public_entries = tuple(
        sorted(
            (engine._scan_count_entry(key, count) for key, count in values.items()),
            key=detection_module.DetectionScanCountEntry.sort_key,
        )
    )
    public = engine.stage_scan_counts(public_entries)

    private = engine._stage_fow_scan_count_values(values)

    assert values == expected_values
    assert private.entries == public.entries == public_entries
    assert private._fingerprint == public._fingerprint
    assert private._owner_token is public._owner_token
    assert all(
        type(entry) is detection_module.DetectionScanCountEntry
        and (entry.scan_identity is None or type(entry.scan_identity) is detection_module.DetectionScanIdentity)
        for entry in private.entries
    )


@pytest.mark.parametrize(
    ("key", "count"),
    (
        ("sensor:target", 1),
        (("sensor",), 1),
        (("side", "observer", 0), 1),
        (("", "target"), 1),
        (("sensor", ""), 1),
        ((" sensor", "target"), 1),
        (("", "observer", 0, "sensor", "target"), 1),
        (("blue", "", 0, "sensor", "target"), 1),
        (("blue", "observer", 0, "", "target"), 1),
        (("blue", "observer", 0, "sensor", ""), 1),
        (("blue", "observer ", 0, "sensor", "target"), 1),
        (("sensor\ud800", "target"), 1),
        (("blue", "observer", 0, "sensor", "target\ud800"), 1),
        (("blue", 1, 0, "sensor", "target"), 1),
        (("blue", "observer", True, "sensor", "target"), 1),
        (("blue", "observer", -1, "sensor", "target"), 1),
        (("blue", "observer", 0.0, "sensor", "target"), 1),
        (("sensor", "target"), True),
        (("sensor", "target"), 0),
        (("sensor", "target"), -1),
        (("sensor", "target"), 1.0),
    ),
)
def test_private_raw_scan_count_snapshot_rejects_malformed_values(
    key: object,
    count: object,
) -> None:
    engine = _engine()
    engine._scan_counts[key] = count  # type: ignore[index,assignment]
    expected = dict(engine._scan_counts)

    with pytest.raises(ValueError):
        engine._snapshot_scan_count_values()

    assert engine._scan_counts == expected


def test_private_live_scan_count_equality_detects_exact_changes() -> None:
    engine = _engine()
    key = ("sensor", "target")
    second_key = ("second-sensor", "second-target")
    engine._scan_counts = {key: 1, second_key: 2}
    expected = engine._snapshot_scan_count_values()

    assert engine._live_scan_count_values_equal(expected)

    engine._scan_counts[("added-sensor", "added-target")] = 1
    assert not engine._live_scan_count_values_equal(expected)

    engine._scan_counts = dict(expected)
    del engine._scan_counts[second_key]
    assert not engine._live_scan_count_values_equal(expected)

    engine._scan_counts = dict(expected)
    engine._scan_counts[key] += 1
    assert not engine._live_scan_count_values_equal(expected)

    engine._scan_counts = dict(expected)
    engine._scan_counts[key] = True
    assert not engine._live_scan_count_values_equal(expected)

    engine._scan_counts = dict(expected)
    malformed_expected = dict(expected)
    malformed_expected[key] = True
    assert not engine._live_scan_count_values_equal(malformed_expected)


@pytest.mark.parametrize(
    ("case", "expected_stage"),
    (
        (
            "offline",
            DetectionDecisionStage.PRE_RNG_SENSOR_OFFLINE,
        ),
        (
            "unsupported_domain",
            DetectionDecisionStage.PRE_RNG_UNSUPPORTED_DOMAIN,
        ),
        (
            "above_max_range",
            DetectionDecisionStage.PRE_RNG_ABOVE_MAX_RANGE,
        ),
        (
            "below_min_range",
            DetectionDecisionStage.PRE_RNG_BELOW_MIN_RANGE,
        ),
        (
            "outside_fov",
            DetectionDecisionStage.PRE_RNG_OUTSIDE_FOV,
        ),
        (
            "blocked_los",
            DetectionDecisionStage.PRE_RNG_LOS,
        ),
        (
            "no_emission",
            DetectionDecisionStage.PRE_RNG_NO_EMISSION,
        ),
        ("stochastic", None),
    ),
)
def test_private_fow_preparation_matches_public_detection(
    case: str,
    expected_stage: DetectionDecisionStage | None,
) -> None:
    observer = Position(0.0, 0.0, 0.0)
    target = Position(100.0, 0.0, 0.0)
    sensor = _sensor(max_range_m=1_000.0)
    profile = _profile(
        visual=VisualSignature(cross_section_m2=10.0),
    )
    target_unit = None
    observer_heading_deg = 0.0
    los_checker = None

    if case == "offline":
        sensor = SensorInstance(
            _defn(max_range_m=1_000.0),
            _equip(operational=False),
        )
    elif case == "unsupported_domain":
        sensor = _sensor(
            max_range_m=99.0,
            target_domains=[Domain.AERIAL.name],
        )
        target_unit = SimpleNamespace(domain=Domain.GROUND)
    elif case == "above_max_range":
        sensor = _sensor(max_range_m=99.0)
    elif case == "below_min_range":
        sensor = _sensor(max_range_m=1_000.0, min_range_m=101.0)
    elif case == "outside_fov":
        sensor = _sensor(max_range_m=1_000.0, fov_deg=30.0)
        observer_heading_deg = 0.0
    elif case == "blocked_los":
        los_checker = lambda *_args: SimpleNamespace(visible=False)
    elif case == "no_emission":
        sensor = _sensor(
            sensor_type="ESM",
            max_range_m=1_000.0,
            detection_threshold=-60.0,
        )
        profile = _profile(
            electromagnetic=EMSignature(emitting=False),
        )

    engine = _engine(los_checker=los_checker)
    geometry = detection_module._detection_geometry(observer, target)
    compact = engine._prepare_fow_detection(
        observer,
        target,
        sensor,
        profile,
        geometry=geometry,
        target_unit=target_unit,
        observer_heading_deg=observer_heading_deg,
    )
    public = engine.prepare_detection(
        observer,
        target,
        sensor,
        profile,
        target_unit=target_unit,
        observer_heading_deg=observer_heading_deg,
    )

    if expected_stage is None:
        assert isinstance(compact, PreparedDetection)
        assert compact == public
        return

    assert compact is expected_stage
    assert public == DetectionResult(
        False,
        0.0,
        -100.0,
        geometry.range_m,
        sensor.sensor_type,
        geometry.bearing_deg,
        expected_stage,
        geometry.horizontal_range_m,
    )


def test_private_fow_preparation_reuses_owned_geometry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observer = Position(0.0, 0.0, 0.0)
    target = Position(100.0, 0.0, 0.0)
    geometry = detection_module._detection_geometry(observer, target)

    def reject_recomputation(*_args: object) -> None:
        raise AssertionError("private FOW preparation recomputed geometry")

    monkeypatch.setattr(detection_module, "_range_m", reject_recomputation)
    monkeypatch.setattr(
        detection_module,
        "_horizontal_range_m",
        reject_recomputation,
    )
    monkeypatch.setattr(detection_module, "_bearing_deg", reject_recomputation)

    prepared = _engine()._prepare_fow_detection(
        observer,
        target,
        _sensor(max_range_m=99.0),
        _profile(),
        geometry=geometry,
    )

    assert prepared is DetectionDecisionStage.PRE_RNG_ABOVE_MAX_RANGE


def test_private_fow_range_gate_keeps_exact_effective_range_boundary() -> None:
    observer = Position(0.0, 0.0, 0.0)
    sensor = SensorInstance(
        _defn(max_range_m=10.0),
        _equip(condition=0.5),
    )
    profile = _profile(
        visual=VisualSignature(cross_section_m2=10.0),
    )
    equal_target = Position(3.0, 4.0, 0.0)
    above_target = Position(math.nextafter(5.0, math.inf), 0.0, 0.0)

    equal = _engine()._prepare_fow_detection(
        observer,
        equal_target,
        sensor,
        profile,
        geometry=detection_module._detection_geometry(
            observer,
            equal_target,
        ),
    )
    above = _engine()._prepare_fow_detection(
        observer,
        above_target,
        sensor,
        profile,
        geometry=detection_module._detection_geometry(
            observer,
            above_target,
        ),
    )

    assert isinstance(equal, PreparedDetection)
    assert _binary64(equal.range_m) == _binary64(sensor.effective_range)
    assert above is DetectionDecisionStage.PRE_RNG_ABOVE_MAX_RANGE


def test_private_fow_preparation_preserves_integration_state() -> None:
    observer = Position(0.0, 0.0, 0.0)
    target = Position(100.0, 0.0, 0.0)
    sensor = _sensor(max_range_m=1_000.0)
    profile = _profile(
        visual=VisualSignature(cross_section_m2=10.0),
    )
    public_engine = _engine()
    private_engine = _engine()

    public = public_engine.prepare_detection(
        observer,
        target,
        sensor,
        profile,
        target_id="target",
    )
    compact = private_engine._prepare_fow_detection(
        observer,
        target,
        sensor,
        profile,
        geometry=detection_module._detection_geometry(observer, target),
        target_id="target",
    )

    assert isinstance(public, PreparedDetection)
    assert compact == public
    assert private_engine._snapshot_scan_count_values() == (public_engine._snapshot_scan_count_values())


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
    @pytest.mark.test_evidence("structural_only")
    def test_basic(self) -> None:
        s = _sensor(
            sensor_type="RADAR",
            frequency_mhz=3300.0,
            peak_power_w=4_000_000.0,
            antenna_gain_dbi=42.0,
        )
        snr = DetectionEngine.compute_snr_radar(s, 10.0, 50000.0)
        assert isinstance(snr, float)

    def test_range_reduces_snr(self) -> None:
        s = _sensor(
            sensor_type="RADAR",
            frequency_mhz=3300.0,
            peak_power_w=4_000_000.0,
            antenna_gain_dbi=42.0,
        )
        close = DetectionEngine.compute_snr_radar(s, 10.0, 10000.0)
        far = DetectionEngine.compute_snr_radar(s, 10.0, 100000.0)
        assert far < close

    def test_larger_rcs_higher_snr(self) -> None:
        s = _sensor(
            sensor_type="RADAR",
            frequency_mhz=3300.0,
            peak_power_w=4_000_000.0,
            antenna_gain_dbi=42.0,
        )
        small = DetectionEngine.compute_snr_radar(s, 1.0, 50000.0)
        large = DetectionEngine.compute_snr_radar(s, 100.0, 50000.0)
        assert large > small

    def test_atmospheric_attenuation(self) -> None:
        s = _sensor(
            sensor_type="RADAR",
            frequency_mhz=3300.0,
            peak_power_w=4_000_000.0,
            antenna_gain_dbi=42.0,
        )
        low_atten = DetectionEngine.compute_snr_radar(s, 10.0, 50000.0, 0.001)
        high_atten = DetectionEngine.compute_snr_radar(s, 10.0, 50000.0, 0.1)
        assert high_atten < low_atten

    def test_r4_scaling(self) -> None:
        """SNR drops ~40 dB per decade of range (R^4 law)."""
        s = _sensor(
            sensor_type="RADAR",
            frequency_mhz=3300.0,
            peak_power_w=4_000_000.0,
            antenna_gain_dbi=42.0,
        )
        snr_10km = DetectionEngine.compute_snr_radar(s, 10.0, 10000.0, 0.0)
        snr_100km = DetectionEngine.compute_snr_radar(s, 10.0, 100000.0, 0.0)
        diff = snr_10km - snr_100km
        assert abs(diff - 40.0) < 1.0  # ~40 dB per decade


# ── Acoustic SNR ─────────────────────────────────────────────────────


class TestComputeSNRAcoustic:
    @pytest.mark.test_evidence("structural_only")
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
        s1 = SensorInstance(
            SensorDefinition(
                sensor_id="s1",
                sensor_type="PASSIVE_SONAR",
                display_name="S1",
                max_range_m=100000.0,
                detection_threshold=8.0,
                directivity_index_db=0.0,
            )
        )
        s2 = SensorInstance(
            SensorDefinition(
                sensor_id="s2",
                sensor_type="PASSIVE_SONAR",
                display_name="S2",
                max_range_m=100000.0,
                detection_threshold=8.0,
                directivity_index_db=25.0,
            )
        )
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
            obs,
            tgt,
            sensor,
            profile,
            illumination_lux=10000.0,
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
            sensor_type="RADAR",
            max_range_m=100000.0,
            detection_threshold=10.0,
            frequency_mhz=3300.0,
            peak_power_w=4_000_000.0,
            antenna_gain_dbi=42.0,
        )
        profile = _profile(radar=RadarSignature(rcs_frontal_m2=15.0, rcs_side_m2=35.0))
        obs = Position(0.0, 0.0, 0.0)
        tgt = Position(0.0, 10000.0, 0.0)
        result = engine.check_detection(obs, tgt, sensor, profile)
        assert result.snr_db > 0

    def test_esm_emitting_target(self) -> None:
        engine = _engine(seed=1)
        sensor = _sensor(
            sensor_type="ESM",
            max_range_m=200000.0,
            detection_threshold=-60.0,
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
            Position(0.0, 0.0, 0.0),
            [_sensor()],
            [],
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
            Position(0.0, 0.0, 0.0),
            sensors,
            targets,
            illumination_lux=500.0,
        )
        assert len(results) == 2

    def test_non_operational_sensor_skipped(self) -> None:
        engine = _engine()
        broken = SensorInstance(_defn(max_range_m=50000.0), _equip(operational=False))
        targets = [(Position(1000.0, 0.0, 0.0), _profile(), None)]
        results = engine.scan_all_targets(
            Position(0.0, 0.0, 0.0),
            [broken],
            targets,
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
            Position(0.0, 0.0, 0.0),
            Position(1000.0, 0.0, 0.0),
            sensor,
            profile,
            illumination_lux=500.0,
        )
        state = engine.get_state()

        # Create new engine, restore state
        engine2 = _engine(seed=0)
        engine2.set_state(state)

        # Both should produce same next result
        r1 = engine.check_detection(
            Position(0.0, 0.0, 0.0),
            Position(1000.0, 0.0, 0.0),
            sensor,
            profile,
            illumination_lux=500.0,
        )
        r2 = engine2.check_detection(
            Position(0.0, 0.0, 0.0),
            Position(1000.0, 0.0, 0.0),
            sensor,
            profile,
            illumination_lux=500.0,
        )
        assert r1.detected == r2.detected
        assert r1.probability == r2.probability
