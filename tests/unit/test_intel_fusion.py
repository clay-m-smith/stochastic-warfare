"""Tests for detection/intel_fusion.py — multi-source intelligence fusion."""

from __future__ import annotations

import math

import numpy as np
import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.detection.detection import DetectionResult
from stochastic_warfare.detection.estimation import (
    EstimationConfig,
    StateEstimator,
    TrackStatus,
)
from stochastic_warfare.detection.identification import ContactInfo, ContactLevel
from stochastic_warfare.detection.intel_fusion import (
    IntelFusionEngine,
    IntelReport,
    IntelSource,
    SatellitePass,
)
from stochastic_warfare.detection.sensors import SensorType


# ── helpers ──────────────────────────────────────────────────────────


def _engine(seed: int = 42) -> IntelFusionEngine:
    rng = np.random.Generator(np.random.PCG64(seed))
    est = StateEstimator(rng=np.random.Generator(np.random.PCG64(seed + 100)))
    return IntelFusionEngine(state_estimator=est, rng=rng)


def _report(
    x: float = 1000.0, y: float = 2000.0,
    reliability: float = 0.8,
    source: IntelSource = IntelSource.SENSOR,
    time: float = 0.0,
    uncertainty: float = 100.0,
) -> IntelReport:
    return IntelReport(
        source=source,
        timestamp=time,
        reliability=reliability,
        target_position=Position(x, y, 0.0),
        position_uncertainty_m=uncertainty,
    )


# ── IntelSource enum ──────────────────────────────────────────────────


class TestIntelSource:
    def test_values(self) -> None:
        assert IntelSource.SENSOR == 0
        assert IntelSource.SIGINT == 1
        assert IntelSource.HUMINT == 2
        assert IntelSource.IMINT == 3
        assert IntelSource.COMINT == 4


# ── IntelReport ───────────────────────────────────────────────────────


class TestIntelReport:
    def test_creation(self) -> None:
        r = _report()
        assert r.source == IntelSource.SENSOR
        assert r.reliability == 0.8
        assert r.target_position == Position(1000.0, 2000.0, 0.0)

    def test_no_position(self) -> None:
        r = IntelReport(source=IntelSource.HUMINT, timestamp=0.0, reliability=0.5)
        assert r.target_position is None


# ── submit_report ─────────────────────────────────────────────────────


class TestSubmitReport:
    def test_creates_track(self) -> None:
        engine = _engine()
        tid = engine.submit_report("blue", _report())
        assert tid is not None
        tracks = engine.get_tracks("blue")
        assert tid in tracks

    def test_no_position_returns_none(self) -> None:
        engine = _engine()
        r = IntelReport(source=IntelSource.HUMINT, timestamp=0.0, reliability=0.5)
        tid = engine.submit_report("blue", r)
        assert tid is None

    def test_reliability_scales_noise(self) -> None:
        """Low reliability should produce a track with larger uncertainty."""
        e1 = _engine(seed=1)
        e2 = _engine(seed=2)
        tid_hi = e1.submit_report("blue", _report(reliability=0.9, uncertainty=100.0))
        tid_lo = e2.submit_report("blue", _report(reliability=0.1, uncertainty=100.0))
        track_hi = e1.get_tracks("blue")[tid_hi]
        track_lo = e2.get_tracks("blue")[tid_lo]
        assert track_lo.position_uncertainty > track_hi.position_uncertainty

    def test_update_existing_track(self) -> None:
        engine = _engine()
        tid = engine.submit_report("blue", _report(x=1000.0))
        # Submit again with same contact_id
        engine.submit_report("blue", _report(x=1010.0), contact_id=tid)
        tracks = engine.get_tracks("blue")
        assert len(tracks) == 1
        assert tracks[tid].hits == 2

    def test_multiple_reports_multiple_tracks(self) -> None:
        engine = _engine()
        engine.submit_report("blue", _report(x=1000.0))
        engine.submit_report("blue", _report(x=5000.0))
        assert len(engine.get_tracks("blue")) == 2


# ── submit_sensor_detection ──────────────────────────────────────────


class TestSubmitSensorDetection:
    def test_creates_track(self) -> None:
        engine = _engine()
        det = DetectionResult(True, 0.9, 20.0, 5000.0, SensorType.RADAR, 45.0)
        ci = ContactInfo(ContactLevel.DETECTED, None, None, None, 0.5)
        tid = engine.submit_sensor_detection(
            "blue", det, ci, Position(0.0, 0.0, 0.0),
        )
        assert tid is not None

    def test_not_detected_returns_none(self) -> None:
        engine = _engine()
        det = DetectionResult(False, 0.1, -5.0, 5000.0, SensorType.RADAR, 45.0)
        ci = ContactInfo(ContactLevel.UNKNOWN, None, None, None, 0.0)
        tid = engine.submit_sensor_detection(
            "blue", det, ci, Position(0.0, 0.0, 0.0),
        )
        assert tid is None


# ── Satellite coverage ────────────────────────────────────────────────


class TestSatelliteCoverage:
    def test_in_coverage(self) -> None:
        engine = _engine()
        sp = SatellitePass(
            start_time=0.0, end_time=600.0,
            coverage_center_x=5000.0, coverage_center_y=5000.0,
            coverage_radius_m=50000.0,
            resolution_m=1.0, revisit_interval_s=3600.0,
        )
        engine.add_satellite_pass("blue", sp)
        assert engine.check_satellite_coverage("blue", 5000.0, 5000.0, 300.0) is True

    def test_out_of_time(self) -> None:
        engine = _engine()
        sp = SatellitePass(
            start_time=0.0, end_time=600.0,
            coverage_center_x=5000.0, coverage_center_y=5000.0,
            coverage_radius_m=50000.0,
            resolution_m=1.0, revisit_interval_s=3600.0,
        )
        engine.add_satellite_pass("blue", sp)
        assert engine.check_satellite_coverage("blue", 5000.0, 5000.0, 700.0) is False

    def test_out_of_area(self) -> None:
        engine = _engine()
        sp = SatellitePass(
            start_time=0.0, end_time=600.0,
            coverage_center_x=5000.0, coverage_center_y=5000.0,
            coverage_radius_m=1000.0,
            resolution_m=1.0, revisit_interval_s=3600.0,
        )
        engine.add_satellite_pass("blue", sp)
        assert engine.check_satellite_coverage("blue", 100000.0, 100000.0, 300.0) is False


# ── SIGINT report ─────────────────────────────────────────────────────


class TestSIGINTReport:
    def test_generation(self) -> None:
        engine = _engine()
        report = engine.generate_sigint_report(
            Position(5000.0, 6000.0, 0.0), 60.0, 100.0,
        )
        assert report.source == IntelSource.SIGINT
        assert report.target_position is not None
        assert report.reliability == 0.7

    def test_position_noisy(self) -> None:
        engine = _engine()
        pos = Position(5000.0, 6000.0, 0.0)
        report = engine.generate_sigint_report(pos, 60.0, 100.0)
        dx = abs(report.target_position.easting - pos.easting)
        dy = abs(report.target_position.northing - pos.northing)
        # Should be noisy but in general neighborhood
        assert dx < 10000.0 or dy < 10000.0  # very generous bound


# ── fuse_reports ──────────────────────────────────────────────────────


class TestFuseReports:
    def test_multiple_reports(self) -> None:
        engine = _engine()
        reports = [
            _report(x=1000.0, y=2000.0, time=0.0),
            _report(x=3000.0, y=4000.0, time=1.0),
        ]
        tids = engine.fuse_reports("blue", reports)
        assert len(tids) == 2

    def test_multi_source_improves_estimate(self) -> None:
        """Multiple high-reliability reports on same contact should reduce uncertainty."""
        engine = _engine()
        tid = engine.submit_report("blue", _report(x=1000.0, reliability=0.9, uncertainty=200.0))
        track = engine.get_tracks("blue")[tid]
        unc_1 = track.position_uncertainty

        for _ in range(5):
            engine.submit_report(
                "blue", _report(x=1005.0, reliability=0.9, uncertainty=200.0),
                contact_id=tid,
            )
        unc_n = track.position_uncertainty
        assert unc_n < unc_1


# ── State round-trip ──────────────────────────────────────────────────


class TestStateRoundTrip:
    def test_roundtrip(self) -> None:
        engine = _engine(seed=42)
        engine.submit_report("blue", _report(x=1000.0))
        engine.submit_report("red", _report(x=5000.0))
        state = engine.get_state()

        engine2 = _engine(seed=0)
        engine2.set_state(state)

        assert len(engine2.get_tracks("blue")) == 1
        assert len(engine2.get_tracks("red")) == 1
        assert engine2._track_counter == 2


# ── Multi-source fusion ──────────────────────────────────────────────


class TestMultiSourceFusion:
    def test_sensor_and_humint_same_target(self) -> None:
        """SENSOR + HUMINT report on same contact should reduce uncertainty."""
        engine = _engine()
        tid = engine.submit_report(
            "blue", _report(x=1000.0, y=2000.0, source=IntelSource.SENSOR, uncertainty=200.0),
        )
        track = engine.get_tracks("blue")[tid]
        unc_1 = track.position_uncertainty

        # Submit HUMINT report at nearby position, same contact
        engine.submit_report(
            "blue",
            _report(x=1010.0, y=2010.0, source=IntelSource.HUMINT, uncertainty=200.0, reliability=0.6),
            contact_id=tid,
        )
        unc_2 = track.position_uncertainty
        assert unc_2 < unc_1

    def test_conflicting_positions_weighted_by_reliability(self) -> None:
        """High-reliability report should dominate track position over low-reliability."""
        engine = _engine()
        # High reliability at (1000, 2000)
        tid = engine.submit_report(
            "blue", _report(x=1000.0, y=2000.0, reliability=0.99, uncertainty=100.0),
        )
        # Low reliability at (5000, 5000) — same contact
        engine.submit_report(
            "blue", _report(x=5000.0, y=5000.0, reliability=0.01, uncertainty=100.0),
            contact_id=tid,
        )
        track = engine.get_tracks("blue")[tid]
        # Track should be much closer to (1000, 2000) than (5000, 5000)
        dx_hi = abs(track.state.position[0] - 1000.0)
        dx_lo = abs(track.state.position[0] - 5000.0)
        assert dx_hi < dx_lo

    def test_imint_report_creates_track(self) -> None:
        """An IMINT source report should create a track."""
        engine = _engine()
        tid = engine.submit_report(
            "blue", _report(x=3000.0, y=4000.0, source=IntelSource.IMINT),
        )
        assert tid is not None
        tracks = engine.get_tracks("blue")
        assert tid in tracks

    def test_comint_report_creates_track(self) -> None:
        """A COMINT source report with position should create a track."""
        engine = _engine()
        tid = engine.submit_report(
            "blue", _report(x=7000.0, y=8000.0, source=IntelSource.COMINT),
        )
        assert tid is not None
        tracks = engine.get_tracks("blue")
        assert tid in tracks


# ── Side isolation ───────────────────────────────────────────────────


class TestSideIsolation:
    def test_blue_tracks_invisible_to_red(self) -> None:
        """Tracks submitted to blue should not appear in red's tracks."""
        engine = _engine()
        engine.submit_report("blue", _report(x=1000.0, y=2000.0))
        assert len(engine.get_tracks("blue")) == 1
        assert len(engine.get_tracks("red")) == 0

    def test_independent_track_counters(self) -> None:
        """Track IDs should increment globally, giving unique IDs across sides."""
        engine = _engine()
        tid_blue = engine.submit_report("blue", _report(x=1000.0))
        tid_red = engine.submit_report("red", _report(x=5000.0))
        assert tid_blue != tid_red


# ── Track management ─────────────────────────────────────────────────


class TestTrackManagementViaFusion:
    def test_manage_tracks_promotes_to_confirmed(self) -> None:
        """Track with enough hits should be promoted to CONFIRMED."""
        cfg = EstimationConfig(confirmation_threshold=3)
        rng = np.random.Generator(np.random.PCG64(42))
        est = StateEstimator(rng=np.random.Generator(np.random.PCG64(100)), config=cfg)
        engine = IntelFusionEngine(state_estimator=est, rng=rng)

        tid = engine.submit_report("blue", _report(x=1000.0, time=0.0, uncertainty=100.0))
        # Submit more reports to accumulate hits
        engine.submit_report("blue", _report(x=1005.0, time=1.0, uncertainty=100.0), contact_id=tid)
        engine.submit_report("blue", _report(x=1010.0, time=2.0, uncertainty=100.0), contact_id=tid)

        tracks = engine.get_tracks("blue")
        assert tracks[tid].hits >= 3
        # manage_tracks should promote
        est.manage_tracks(tracks, 2.0)
        # Access internal tracks to verify status (get_tracks returns a copy)
        internal_tracks = engine._get_side_tracks("blue")
        assert internal_tracks[tid].status == TrackStatus.CONFIRMED

    def test_manage_tracks_coasts_old_track(self) -> None:
        """Track not updated for a long time should transition to COASTING or LOST."""
        cfg = EstimationConfig(
            confirmation_threshold=1,
            coast_timeout_s=50.0,
            lost_timeout_s=200.0,
        )
        rng = np.random.Generator(np.random.PCG64(42))
        est = StateEstimator(rng=np.random.Generator(np.random.PCG64(100)), config=cfg)
        engine = IntelFusionEngine(state_estimator=est, rng=rng)

        tid = engine.submit_report("blue", _report(x=1000.0, time=0.0))
        # Promote to CONFIRMED (hits >= 1)
        internal_tracks = engine._get_side_tracks("blue")
        est.manage_tracks(internal_tracks, 0.0)
        assert internal_tracks[tid].status == TrackStatus.CONFIRMED

        # Now advance time far beyond coast_timeout
        est.manage_tracks(internal_tracks, 100.0)
        assert internal_tracks[tid].status == TrackStatus.COASTING
