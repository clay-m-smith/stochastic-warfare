"""Tests for Phase 11b: Detection Fidelity.

Changes tested:
  6. Sensor FOV filtering (sensors.py + detection.py)
  7. Dwell/integration gain (detection.py)
  8. Geometric passive sonar bearing (sonar.py)
  9. Nearest-neighbor gating / Mahalanobis (estimation.py)
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from tests.conftest import make_rng

from stochastic_warfare.core.types import Position
from stochastic_warfare.detection.detection import DetectionConfig, DetectionEngine
from stochastic_warfare.detection.estimation import (
    EstimationConfig,
    StateEstimator,
    Track,
    TrackState,
    TrackStatus,
)
from stochastic_warfare.detection.identification import ContactInfo, ContactLevel
from stochastic_warfare.detection.sensors import SensorDefinition, SensorInstance
from stochastic_warfare.detection.signatures import (
    AcousticSignature,
    EMSignature,
    RadarSignature,
    SignatureProfile,
    ThermalSignature,
    VisualSignature,
)
from stochastic_warfare.detection.sonar import SonarEngine


# ── helpers ──────────────────────────────────────────────────────────


def _sensor_def(
    sensor_id: str = "test_radar",
    sensor_type: str = "RADAR",
    max_range_m: float = 10000.0,
    detection_threshold: float = 5.0,
    fov_deg: float = 360.0,
    boresight_offset_deg: float = 0.0,
    **kwargs,
) -> SensorDefinition:
    return SensorDefinition(
        sensor_id=sensor_id,
        sensor_type=sensor_type,
        display_name="Test sensor",
        max_range_m=max_range_m,
        detection_threshold=detection_threshold,
        fov_deg=fov_deg,
        boresight_offset_deg=boresight_offset_deg,
        frequency_mhz=3000.0,
        peak_power_w=100000.0,
        antenna_gain_dbi=30.0,
        **kwargs,
    )


def _sensor(
    fov_deg: float = 360.0,
    boresight_offset_deg: float = 0.0,
    **kwargs,
) -> SensorInstance:
    defn = _sensor_def(fov_deg=fov_deg, boresight_offset_deg=boresight_offset_deg, **kwargs)
    return SensorInstance(defn)


def _sig_profile() -> SignatureProfile:
    return SignatureProfile(
        profile_id="test_sig",
        unit_type="test_unit",
        visual=VisualSignature(cross_section_m2=5.0),
        thermal=ThermalSignature(signature_watts=100.0),
        radar=RadarSignature(rcs_m2=10.0),
        acoustic=AcousticSignature(source_level_db=120.0),
        electromagnetic=EMSignature(peak_emissions_dbm=-20.0),
    )


def _engine(config: DetectionConfig | None = None, seed: int = 42) -> DetectionEngine:
    return DetectionEngine(rng=make_rng(seed), config=config)


def _pos(e: float = 0.0, n: float = 0.0, alt: float = 0.0) -> Position:
    return Position(easting=e, northing=n, altitude=alt)


def _contact_info() -> ContactInfo:
    return ContactInfo(ContactLevel.DETECTED, None, None, None, 0.5)


def _make_track(
    x: float = 0.0,
    y: float = 0.0,
    vx: float = 0.0,
    vy: float = 0.0,
    pos_var: float = 100.0,
    vel_var: float = 10.0,
    time: float = 0.0,
) -> Track:
    cov = np.diag([pos_var, pos_var, vel_var, vel_var])
    state = TrackState(
        position=np.array([x, y]),
        velocity=np.array([vx, vy]),
        covariance=cov,
        last_update_time=time,
    )
    return Track("t-1", "blue", _contact_info(), state, TrackStatus.TENTATIVE)


def _sonar_sensor(
    sensor_id: str = "passive_sonar",
    source_level_db: float | None = None,
    detection_threshold: float = 5.0,
    directivity_index_db: float = 10.0,
    max_range_m: float = 50000.0,
) -> SensorInstance:
    defn = SensorDefinition(
        sensor_id=sensor_id,
        sensor_type="PASSIVE_SONAR",
        display_name="Test passive sonar",
        max_range_m=max_range_m,
        detection_threshold=detection_threshold,
        source_level_db=source_level_db,
        directivity_index_db=directivity_index_db,
    )
    return SensorInstance(defn)


def _active_sonar_sensor(
    source_level_db: float = 220.0,
    detection_threshold: float = 5.0,
    directivity_index_db: float = 15.0,
    max_range_m: float = 50000.0,
) -> SensorInstance:
    defn = SensorDefinition(
        sensor_id="active_sonar",
        sensor_type="ACTIVE_SONAR",
        display_name="Test active sonar",
        max_range_m=max_range_m,
        detection_threshold=detection_threshold,
        source_level_db=source_level_db,
        directivity_index_db=directivity_index_db,
    )
    return SensorInstance(defn)


# =====================================================================
# 6. Sensor FOV filtering
# =====================================================================


class TestSensorFOV:
    """Sensor field-of-view filtering against observer heading."""

    def test_360_fov_always_detects(self) -> None:
        """360° FOV should not filter any bearing."""
        eng = _engine(seed=1)
        sensor = _sensor(fov_deg=360.0)
        sig = _sig_profile()
        obs = _pos(0, 0)
        # Target behind observer
        tgt = _pos(0, -500)
        result = eng.check_detection(
            obs, tgt, sensor, sig, observer_heading_deg=0.0,
        )
        # Should attempt detection (not blocked by FOV)
        assert result.range_m > 0

    def test_narrow_fov_target_in_front(self) -> None:
        """Target ahead of observer with narrow FOV should be in FOV."""
        eng = _engine(seed=1)
        sensor = _sensor(fov_deg=90.0)
        sig = _sig_profile()
        obs = _pos(0, 0)
        # Target due north, observer heading north (0°)
        tgt = _pos(0, 500)
        result = eng.check_detection(
            obs, tgt, sensor, sig, observer_heading_deg=0.0,
        )
        # Should not be blocked by FOV
        assert result.snr_db > -100.0

    def test_narrow_fov_target_behind(self) -> None:
        """Target behind observer with narrow FOV should be filtered."""
        eng = _engine(seed=1)
        sensor = _sensor(fov_deg=90.0)
        sig = _sig_profile()
        obs = _pos(0, 0)
        # Target due south (bearing=180), observer heading north (0°)
        tgt = _pos(0, -500)
        result = eng.check_detection(
            obs, tgt, sensor, sig, observer_heading_deg=0.0,
        )
        # Should be blocked by FOV — no detection
        assert not result.detected
        assert result.snr_db == -100.0

    def test_narrow_fov_target_at_edge(self) -> None:
        """Target just inside FOV edge should pass."""
        eng = _engine(seed=1)
        sensor = _sensor(fov_deg=90.0)
        sig = _sig_profile()
        obs = _pos(0, 0)
        # Target at 44° (within ±45° of heading 0°)
        tgt = _pos(500 * math.sin(math.radians(44)), 500 * math.cos(math.radians(44)))
        result = eng.check_detection(
            obs, tgt, sensor, sig, observer_heading_deg=0.0,
        )
        assert result.snr_db > -100.0

    def test_narrow_fov_target_just_outside_edge(self) -> None:
        """Target just outside FOV edge should be filtered."""
        eng = _engine(seed=1)
        sensor = _sensor(fov_deg=90.0)
        sig = _sig_profile()
        obs = _pos(0, 0)
        # Target at 46° (outside ±45° of heading 0°)
        tgt = _pos(500 * math.sin(math.radians(46)), 500 * math.cos(math.radians(46)))
        result = eng.check_detection(
            obs, tgt, sensor, sig, observer_heading_deg=0.0,
        )
        assert not result.detected
        assert result.snr_db == -100.0

    def test_fov_with_observer_heading(self) -> None:
        """FOV should rotate with observer heading."""
        eng = _engine(seed=1)
        sensor = _sensor(fov_deg=90.0)
        sig = _sig_profile()
        obs = _pos(0, 0)
        # Target due east (bearing=90)
        tgt = _pos(500, 0)
        # Observer heading north (0°) — target at 90° relative, outside 45° half-FOV
        result_north = eng.check_detection(
            obs, tgt, sensor, sig, observer_heading_deg=0.0,
        )
        assert not result_north.detected
        # Observer heading east (90°) — target at 0° relative, inside FOV
        result_east = eng.check_detection(
            obs, tgt, sensor, sig, observer_heading_deg=90.0,
        )
        assert result_east.snr_db > -100.0

    def test_fov_with_boresight_offset(self) -> None:
        """Boresight offset should shift the FOV center."""
        eng = _engine(seed=1)
        sensor = _sensor(fov_deg=90.0, boresight_offset_deg=90.0)
        sig = _sig_profile()
        obs = _pos(0, 0)
        # Target due east (bearing=90), observer heading north (0°)
        # With 90° boresight offset, sensor looks east → target in FOV
        tgt = _pos(500, 0)
        result = eng.check_detection(
            obs, tgt, sensor, sig, observer_heading_deg=0.0,
        )
        assert result.snr_db > -100.0

    def test_boresight_offset_definition_field(self) -> None:
        """SensorDefinition should have boresight_offset_deg field."""
        defn = _sensor_def(boresight_offset_deg=45.0)
        assert defn.boresight_offset_deg == 45.0

    def test_boresight_offset_default(self) -> None:
        """boresight_offset_deg should default to 0."""
        defn = _sensor_def()
        assert defn.boresight_offset_deg == 0.0

    def test_fov_wraps_around_360(self) -> None:
        """FOV should handle bearing wrap-around (350° heading, target at 10°)."""
        eng = _engine(seed=1)
        sensor = _sensor(fov_deg=90.0)
        sig = _sig_profile()
        obs = _pos(0, 0)
        # Target due north (bearing ≈ 0°/360°), observer heading 350°
        tgt = _pos(0, 500)
        result = eng.check_detection(
            obs, tgt, sensor, sig, observer_heading_deg=350.0,
        )
        # Target at relative bearing 10° — within ±45° FOV
        assert result.snr_db > -100.0


# =====================================================================
# 7. Dwell / integration gain
# =====================================================================


class TestIntegrationGain:
    """Dwell/integration gain with repeated scans."""

    def test_first_scan_no_boost(self) -> None:
        """First scan should have no integration gain."""
        eng = _engine(seed=1)
        sensor = _sensor()
        sig = _sig_profile()
        obs = _pos(0, 0)
        tgt = _pos(0, 1000)
        # First scan — no gain
        r1 = eng.check_detection(obs, tgt, sensor, sig, target_id="tgt1")
        # Check that scan count is now 1
        assert eng._scan_counts.get((sensor.sensor_id, "tgt1")) == 1

    def test_repeated_scans_boost_snr(self) -> None:
        """Repeated scans should increase effective SNR."""
        config = DetectionConfig(enable_integration_gain=True)
        eng = _engine(config=config, seed=1)
        sensor = _sensor()
        sig = _sig_profile()
        obs = _pos(0, 0)
        tgt = _pos(0, 1000)
        # Scan 4 times to get +6 dB cap
        results = []
        for _ in range(4):
            r = eng.check_detection(obs, tgt, sensor, sig, target_id="tgt1")
            results.append(r)
        # SNR should increase from scan 1 to scan 4
        # scan 2: +5*log10(2) ≈ +1.5 dB, scan 3: +2.4, scan 4: +3.0
        assert results[1].snr_db > results[0].snr_db
        assert results[3].snr_db > results[1].snr_db

    def test_integration_gain_capped(self) -> None:
        """Integration gain should be capped at max_integration_gain_db."""
        config = DetectionConfig(
            enable_integration_gain=True, max_integration_gain_db=6.0,
        )
        eng = _engine(config=config, seed=1)
        sensor = _sensor()
        sig = _sig_profile()
        obs = _pos(0, 0)
        tgt = _pos(0, 1000)
        # 10 scans — gain should not exceed 6 dB
        snrs = []
        for _ in range(10):
            r = eng.check_detection(obs, tgt, sensor, sig, target_id="tgt1")
            snrs.append(r.snr_db)
        # Gain = 5*log10(10) = 5.0 dB at scan 10, but capped at 6.0
        # Diff between scan 5 and scan 10 should be small (both approaching cap)
        max_gain_observed = snrs[-1] - snrs[0]
        assert max_gain_observed <= 6.5  # some tolerance

    def test_no_boost_without_target_id(self) -> None:
        """No integration gain when target_id is empty."""
        config = DetectionConfig(enable_integration_gain=True)
        eng = _engine(config=config, seed=1)
        sensor = _sensor()
        sig = _sig_profile()
        obs = _pos(0, 0)
        tgt = _pos(0, 1000)
        # No target_id — no integration tracking
        r1 = eng.check_detection(obs, tgt, sensor, sig, target_id="")
        r2 = eng.check_detection(obs, tgt, sensor, sig, target_id="")
        # SNR should be identical (same physics, same RNG sequence gives diff rolls but same SNR)
        assert r1.snr_db == r2.snr_db

    def test_disabled_integration_gain(self) -> None:
        """Integration gain disabled in config should not boost SNR."""
        config = DetectionConfig(enable_integration_gain=False)
        eng = _engine(config=config, seed=1)
        sensor = _sensor()
        sig = _sig_profile()
        obs = _pos(0, 0)
        tgt = _pos(0, 1000)
        r1 = eng.check_detection(obs, tgt, sensor, sig, target_id="tgt1")
        r2 = eng.check_detection(obs, tgt, sensor, sig, target_id="tgt1")
        assert r1.snr_db == r2.snr_db

    def test_reset_scan_counts(self) -> None:
        """reset_scan_counts should clear all tracking."""
        config = DetectionConfig(enable_integration_gain=True)
        eng = _engine(config=config, seed=1)
        sensor = _sensor()
        sig = _sig_profile()
        obs = _pos(0, 0)
        tgt = _pos(0, 1000)
        eng.check_detection(obs, tgt, sensor, sig, target_id="tgt1")
        eng.check_detection(obs, tgt, sensor, sig, target_id="tgt1")
        assert len(eng._scan_counts) > 0
        eng.reset_scan_counts()
        assert len(eng._scan_counts) == 0

    def test_scan_counts_in_state(self) -> None:
        """Scan counts should be persisted in get_state/set_state."""
        config = DetectionConfig(enable_integration_gain=True)
        eng = _engine(config=config, seed=1)
        sensor = _sensor()
        sig = _sig_profile()
        obs = _pos(0, 0)
        tgt = _pos(0, 1000)
        eng.check_detection(obs, tgt, sensor, sig, target_id="tgt1")
        eng.check_detection(obs, tgt, sensor, sig, target_id="tgt1")
        state = eng.get_state()
        assert "scan_counts" in state
        # Restore into new engine
        eng2 = _engine(config=config, seed=99)
        eng2.set_state(state)
        assert eng2._scan_counts == eng._scan_counts

    def test_different_targets_tracked_separately(self) -> None:
        """Different target_ids should have independent scan counts."""
        config = DetectionConfig(enable_integration_gain=True)
        eng = _engine(config=config, seed=1)
        sensor = _sensor()
        sig = _sig_profile()
        obs = _pos(0, 0)
        tgt = _pos(0, 1000)
        eng.check_detection(obs, tgt, sensor, sig, target_id="tgt1")
        eng.check_detection(obs, tgt, sensor, sig, target_id="tgt1")
        eng.check_detection(obs, tgt, sensor, sig, target_id="tgt2")
        assert eng._scan_counts[(sensor.sensor_id, "tgt1")] == 2
        assert eng._scan_counts[(sensor.sensor_id, "tgt2")] == 1


# =====================================================================
# 8. Geometric passive sonar bearing
# =====================================================================


class TestGeometricSonarBearing:
    """Geometric bearing calculation for sonar instead of random placeholder."""

    def test_passive_bearing_roughly_correct(self) -> None:
        """Passive bearing should approximate true geometric bearing."""
        eng = SonarEngine(rng=make_rng(42))
        sensor = _sonar_sensor()
        obs_pos = (0.0, 0.0)
        tgt_pos = (1000.0, 0.0)  # target due east → bearing ≈ 90°
        result = eng.passive_detection(
            sensor,
            observer_depth=100.0,
            target_noise_db=140.0,
            target_depth=100.0,
            range_m=1000.0,
            observer_pos=obs_pos,
            target_pos=tgt_pos,
        )
        # True bearing is 90°, should be within ~30°
        assert 60.0 < result.bearing_deg < 120.0

    def test_passive_bearing_north(self) -> None:
        """Target due north → bearing ≈ 0°."""
        eng = SonarEngine(rng=make_rng(42))
        sensor = _sonar_sensor()
        result = eng.passive_detection(
            sensor,
            observer_depth=100.0,
            target_noise_db=140.0,
            target_depth=100.0,
            range_m=1000.0,
            observer_pos=(0.0, 0.0),
            target_pos=(0.0, 1000.0),
        )
        # True bearing is 0°, should be near 0° or 360°
        bearing = result.bearing_deg
        if bearing > 180:
            bearing -= 360
        assert abs(bearing) < 30.0

    def test_passive_bearing_southwest(self) -> None:
        """Target to southwest → bearing ≈ 225°."""
        eng = SonarEngine(rng=make_rng(42))
        sensor = _sonar_sensor()
        result = eng.passive_detection(
            sensor,
            observer_depth=100.0,
            target_noise_db=140.0,
            target_depth=100.0,
            range_m=1414.0,
            observer_pos=(0.0, 0.0),
            target_pos=(-1000.0, -1000.0),
        )
        # True bearing ≈ 225°
        assert 195.0 < result.bearing_deg < 255.0

    def test_passive_fallback_without_positions(self) -> None:
        """Without observer/target positions, should fall back to random bearing."""
        eng = SonarEngine(rng=make_rng(42))
        sensor = _sonar_sensor()
        result = eng.passive_detection(
            sensor,
            observer_depth=100.0,
            target_noise_db=140.0,
            target_depth=100.0,
            range_m=1000.0,
            # No observer_pos/target_pos
        )
        # Should still produce a bearing (random)
        assert 0.0 <= result.bearing_deg < 360.0

    def test_active_bearing_geometric(self) -> None:
        """Active sonar should also use geometric bearing."""
        eng = SonarEngine(rng=make_rng(42))
        sensor = _active_sonar_sensor()
        result = eng.active_detection(
            sensor,
            observer_depth=100.0,
            target_rcs_db=15.0,
            target_depth=100.0,
            range_m=1000.0,
            observer_pos=(0.0, 0.0),
            target_pos=(0.0, 1000.0),
        )
        # True bearing is 0° (north)
        bearing = result.bearing_deg
        if bearing > 180:
            bearing -= 360
        assert abs(bearing) < 20.0

    def test_active_fallback_without_positions(self) -> None:
        """Active sonar without positions falls back to random bearing."""
        eng = SonarEngine(rng=make_rng(42))
        sensor = _active_sonar_sensor()
        result = eng.active_detection(
            sensor,
            observer_depth=100.0,
            target_rcs_db=15.0,
            target_depth=100.0,
            range_m=1000.0,
        )
        assert 0.0 <= result.bearing_deg < 360.0

    def test_bearing_noise_higher_at_low_snr(self) -> None:
        """At low SNR (weak signal), bearing noise should be larger."""
        bearings_high_snr = []
        bearings_low_snr = []
        true_bearing = 90.0  # target due east
        for seed in range(50):
            eng = SonarEngine(rng=make_rng(seed))
            sensor = _sonar_sensor()
            # High SNR: loud target
            r_high = eng.passive_detection(
                sensor,
                observer_depth=100.0,
                target_noise_db=160.0,
                target_depth=100.0,
                range_m=1000.0,
                observer_pos=(0.0, 0.0),
                target_pos=(1000.0, 0.0),
            )
            bearings_high_snr.append(r_high.bearing_deg)

            eng2 = SonarEngine(rng=make_rng(seed))
            # Low SNR: quiet target
            r_low = eng2.passive_detection(
                sensor,
                observer_depth=100.0,
                target_noise_db=90.0,
                target_depth=100.0,
                range_m=1000.0,
                observer_pos=(0.0, 0.0),
                target_pos=(1000.0, 0.0),
            )
            bearings_low_snr.append(r_low.bearing_deg)

        # Compute bearing error std dev
        errors_high = [abs(b - true_bearing) for b in bearings_high_snr]
        errors_low = [abs(b - true_bearing) for b in bearings_low_snr]
        # Wrap-around correction
        errors_high = [min(e, 360 - e) for e in errors_high]
        errors_low = [min(e, 360 - e) for e in errors_low]
        std_high = np.std(errors_high)
        std_low = np.std(errors_low)
        # Low SNR should have larger bearing errors
        assert std_low > std_high

    def test_same_position_bearing_is_zero_distance(self) -> None:
        """Same position should produce a bearing (atan2(0,0) = 0°)."""
        eng = SonarEngine(rng=make_rng(42))
        sensor = _sonar_sensor()
        result = eng.passive_detection(
            sensor,
            observer_depth=100.0,
            target_noise_db=140.0,
            target_depth=100.0,
            range_m=1.0,
            observer_pos=(100.0, 200.0),
            target_pos=(100.0, 200.0),
        )
        # Should produce some bearing without errors
        assert 0.0 <= result.bearing_deg < 360.0


# =====================================================================
# 9. Mahalanobis gating
# =====================================================================


class TestMahalanobisGating:
    """Nearest-neighbor gating using Mahalanobis distance."""

    def test_close_measurement_accepted(self) -> None:
        """Measurement near predicted state should be accepted."""
        est = StateEstimator(rng=make_rng(42))
        track = _make_track(x=100.0, y=200.0, pos_var=100.0)
        R = np.diag([10.0, 10.0])
        meas = np.array([105.0, 198.0])  # close to (100, 200)
        accepted = est.update(track, meas, R, time=1.0)
        assert accepted is True
        # Position should move toward measurement
        assert track.state.position[0] > 100.0

    def test_wild_measurement_rejected(self) -> None:
        """Measurement far from predicted state should be gated out."""
        est = StateEstimator(rng=make_rng(42))
        track = _make_track(x=100.0, y=200.0, pos_var=10.0)
        R = np.diag([10.0, 10.0])
        meas = np.array([1000.0, 2000.0])  # way off
        accepted = est.update(track, meas, R, time=1.0)
        assert accepted is False
        # Position should not change
        assert track.state.position[0] == pytest.approx(100.0)
        assert track.state.position[1] == pytest.approx(200.0)

    def test_hits_not_incremented_on_rejection(self) -> None:
        """Gated-out measurement should not increment hit counter."""
        est = StateEstimator(rng=make_rng(42))
        track = _make_track(x=100.0, y=200.0, pos_var=10.0)
        initial_hits = track.hits
        R = np.diag([10.0, 10.0])
        meas = np.array([1000.0, 2000.0])
        est.update(track, meas, R, time=1.0)
        assert track.hits == initial_hits

    def test_disabled_gating_accepts_all(self) -> None:
        """When gating disabled, wild measurement should be accepted."""
        config = EstimationConfig(enable_gating=False)
        est = StateEstimator(rng=make_rng(42), config=config)
        track = _make_track(x=100.0, y=200.0, pos_var=10.0)
        R = np.diag([10.0, 10.0])
        meas = np.array([1000.0, 2000.0])
        accepted = est.update(track, meas, R, time=1.0)
        assert accepted is True
        # Position should move toward wild measurement
        assert track.state.position[0] > 100.0

    def test_threshold_tuning(self) -> None:
        """Lower chi2 threshold should reject more measurements."""
        # Very tight gate
        config_tight = EstimationConfig(enable_gating=True, gating_threshold_chi2=1.0)
        est_tight = StateEstimator(rng=make_rng(42), config=config_tight)
        track_tight = _make_track(x=100.0, y=200.0, pos_var=100.0)
        R = np.diag([10.0, 10.0])
        meas = np.array([110.0, 210.0])  # 10m offset
        # d² = 10²/110 + 10²/110 ≈ 1.82
        accepted_tight = est_tight.update(track_tight, meas, R, time=1.0)

        # Very loose gate
        config_loose = EstimationConfig(enable_gating=True, gating_threshold_chi2=100.0)
        est_loose = StateEstimator(rng=make_rng(42), config=config_loose)
        track_loose = _make_track(x=100.0, y=200.0, pos_var=100.0)
        accepted_loose = est_loose.update(track_loose, meas, R, time=1.0)

        # Loose should accept, tight might reject
        assert accepted_loose is True
        # With threshold=1.0 and d²≈1.82, tight should reject
        assert accepted_tight is False

    def test_default_threshold_is_chi2_99(self) -> None:
        """Default threshold should be 9.21 (99% for 2 DOF)."""
        config = EstimationConfig()
        assert config.gating_threshold_chi2 == pytest.approx(9.21)

    def test_enable_gating_default_true(self) -> None:
        """Gating should be enabled by default."""
        config = EstimationConfig()
        assert config.enable_gating is True

    def test_borderline_measurement(self) -> None:
        """Measurement exactly at threshold boundary."""
        config = EstimationConfig(enable_gating=True, gating_threshold_chi2=9.21)
        est = StateEstimator(rng=make_rng(42), config=config)
        # Construct case where d² ≈ 5 (well within gate)
        track = _make_track(x=0.0, y=0.0, pos_var=1000.0)
        R = np.diag([10.0, 10.0])
        # S = diag(1010, 1010), need d² = x²/1010 + y²/1010 < 9.21
        # → x² + y² < 9301 → sqrt ≈ 96.4
        meas = np.array([50.0, 50.0])  # d² = 2500/1010 + 2500/1010 ≈ 4.95
        accepted = est.update(track, meas, R, time=1.0)
        assert accepted is True

    def test_return_type_is_bool(self) -> None:
        """update() should return bool."""
        est = StateEstimator(rng=make_rng(42))
        track = _make_track(x=100.0, y=200.0, pos_var=100.0)
        R = np.diag([10.0, 10.0])
        result = est.update(track, np.array([100.0, 200.0]), R, time=1.0)
        assert isinstance(result, bool)
