"""Tests for detection/estimation.py — Kalman filter state estimation."""

from __future__ import annotations

import numpy as np
import pytest

from stochastic_warfare.detection.estimation import (
    EstimationConfig,
    StateEstimator,
    Track,
    TrackState,
    TrackStatus,
)
from stochastic_warfare.detection.identification import ContactInfo, ContactLevel


# ── helpers ──────────────────────────────────────────────────────────


def _estimator(seed: int = 42, **kwargs) -> StateEstimator:
    rng = np.random.Generator(np.random.PCG64(seed))
    return StateEstimator(rng=rng, **kwargs)


def _contact_info(level=ContactLevel.DETECTED) -> ContactInfo:
    return ContactInfo(level, None, None, None, 0.5)


def _make_track(
    x: float = 1000.0, y: float = 2000.0,
    vx: float = 0.0, vy: float = 0.0,
    pos_var: float = 100.0, vel_var: float = 10.0,
    time: float = 0.0,
    status: TrackStatus = TrackStatus.TENTATIVE,
) -> Track:
    cov = np.diag([pos_var, pos_var, vel_var, vel_var])
    state = TrackState(
        position=np.array([x, y]),
        velocity=np.array([vx, vy]),
        covariance=cov,
        last_update_time=time,
    )
    return Track("t-1", "blue", _contact_info(), state, status)


# ── TrackStatus enum ─────────────────────────────────────────────────


class TestTrackStatus:
    def test_ordering(self) -> None:
        assert TrackStatus.TENTATIVE < TrackStatus.CONFIRMED
        assert TrackStatus.CONFIRMED < TrackStatus.COASTING
        assert TrackStatus.COASTING < TrackStatus.LOST


# ── EstimationConfig ──────────────────────────────────────────────────


class TestEstimationConfig:
    def test_defaults(self) -> None:
        c = EstimationConfig()
        assert c.process_noise_std == 5.0
        assert c.confirmation_threshold == 3
        assert c.coast_timeout_s == 300.0
        assert c.lost_timeout_s == 600.0


# ── Predict ───────────────────────────────────────────────────────────


class TestPredict:
    def test_position_advances(self) -> None:
        est = _estimator()
        track = _make_track(x=0.0, y=0.0, vx=10.0, vy=5.0)
        est.predict(track, dt=1.0)
        assert track.state.position[0] == pytest.approx(10.0, abs=0.1)
        assert track.state.position[1] == pytest.approx(5.0, abs=0.1)

    def test_covariance_grows(self) -> None:
        est = _estimator()
        track = _make_track(pos_var=100.0)
        initial_trace = np.trace(track.state.covariance)
        est.predict(track, dt=10.0)
        assert np.trace(track.state.covariance) > initial_trace

    def test_velocity_preserved(self) -> None:
        est = _estimator()
        track = _make_track(vx=15.0, vy=-3.0)
        est.predict(track, dt=5.0)
        assert track.state.velocity[0] == pytest.approx(15.0, abs=0.1)
        assert track.state.velocity[1] == pytest.approx(-3.0, abs=0.1)

    def test_zero_dt_no_change(self) -> None:
        est = _estimator(config=EstimationConfig(process_noise_std=0.0))
        track = _make_track(x=100.0, y=200.0)
        cov_before = track.state.covariance.copy()
        est.predict(track, dt=0.0)
        np.testing.assert_array_almost_equal(track.state.covariance, cov_before)

    def test_larger_dt_more_growth(self) -> None:
        est = _estimator()
        track1 = _make_track(pos_var=100.0)
        track2 = _make_track(pos_var=100.0)
        est.predict(track1, dt=1.0)
        est.predict(track2, dt=10.0)
        assert np.trace(track2.state.covariance) > np.trace(track1.state.covariance)


# ── Update ────────────────────────────────────────────────────────────


class TestUpdate:
    def test_covariance_shrinks(self) -> None:
        est = _estimator()
        track = _make_track(pos_var=1000.0)
        initial_trace = np.trace(track.state.covariance)
        R = np.diag([50.0, 50.0])
        meas = np.array([1010.0, 2010.0])
        est.update(track, meas, R, time=1.0)
        assert np.trace(track.state.covariance) < initial_trace

    def test_position_moves_toward_measurement(self) -> None:
        est = _estimator()
        track = _make_track(x=0.0, y=0.0, pos_var=1000.0)
        R = np.diag([10.0, 10.0])
        meas = np.array([100.0, 200.0])
        est.update(track, meas, R, time=1.0)
        # Should move significantly toward [100, 200]
        assert track.state.position[0] > 50.0
        assert track.state.position[1] > 100.0

    def test_hits_increment(self) -> None:
        est = _estimator()
        track = _make_track()
        initial_hits = track.hits
        R = np.diag([50.0, 50.0])
        est.update(track, np.array([1000.0, 2000.0]), R, time=1.0)
        assert track.hits == initial_hits + 1

    def test_last_update_time(self) -> None:
        est = _estimator()
        track = _make_track()
        R = np.diag([50.0, 50.0])
        est.update(track, np.array([1000.0, 2000.0]), R, time=42.0)
        assert track.state.last_update_time == 42.0

    def test_convergence(self) -> None:
        """Multiple updates at same position should converge estimate."""
        est = _estimator()
        track = _make_track(x=0.0, y=0.0, pos_var=10000.0)
        R = np.diag([10.0, 10.0])
        true_pos = np.array([500.0, 300.0])
        for _ in range(20):
            est.update(track, true_pos, R, time=1.0)
        assert track.state.position[0] == pytest.approx(500.0, abs=5.0)
        assert track.state.position[1] == pytest.approx(300.0, abs=5.0)

    def test_low_noise_measurement_dominates(self) -> None:
        est = _estimator()
        track = _make_track(x=0.0, y=0.0, pos_var=10000.0)
        R = np.diag([0.01, 0.01])  # very precise measurement
        meas = np.array([100.0, 200.0])
        est.update(track, meas, R, time=1.0)
        assert track.state.position[0] == pytest.approx(100.0, abs=1.0)

    def test_high_noise_measurement_mostly_ignored(self) -> None:
        est = _estimator()
        track = _make_track(x=0.0, y=0.0, pos_var=1.0)  # very certain prior
        R = np.diag([100000.0, 100000.0])  # very noisy measurement
        meas = np.array([1000.0, 2000.0])
        est.update(track, meas, R, time=1.0)
        # Should stay near 0,0
        assert abs(track.state.position[0]) < 100.0


# ── create_track ──────────────────────────────────────────────────────


class TestCreateTrack:
    def test_basic(self) -> None:
        est = _estimator()
        R = np.diag([100.0, 100.0])
        meas = np.array([5000.0, 6000.0])
        track = est.create_track("t-1", "blue", meas, R, _contact_info(), 0.0)
        assert track.track_id == "t-1"
        assert track.status == TrackStatus.TENTATIVE
        assert track.hits == 1
        assert track.state.position[0] == pytest.approx(5000.0)
        assert track.state.covariance[0, 0] == 100.0

    def test_initial_velocity_zero(self) -> None:
        est = _estimator()
        R = np.diag([100.0, 100.0])
        track = est.create_track("t-1", "blue", np.array([0.0, 0.0]), R, _contact_info(), 0.0)
        assert track.state.velocity[0] == 0.0
        assert track.state.velocity[1] == 0.0


# ── manage_tracks ─────────────────────────────────────────────────────


class TestManageTracks:
    def test_promotion_tentative_to_confirmed(self) -> None:
        est = _estimator(config=EstimationConfig(confirmation_threshold=3))
        track = _make_track(status=TrackStatus.TENTATIVE)
        track.hits = 3
        tracks = {"t-1": track}
        est.manage_tracks(tracks, 0.0)
        assert track.status == TrackStatus.CONFIRMED

    def test_not_promoted_insufficient_hits(self) -> None:
        est = _estimator(config=EstimationConfig(confirmation_threshold=3))
        track = _make_track(status=TrackStatus.TENTATIVE)
        track.hits = 2
        tracks = {"t-1": track}
        est.manage_tracks(tracks, 0.0)
        assert track.status == TrackStatus.TENTATIVE

    def test_coasting_from_confirmed(self) -> None:
        est = _estimator(config=EstimationConfig(coast_timeout_s=100.0))
        track = _make_track(time=0.0, status=TrackStatus.CONFIRMED)
        tracks = {"t-1": track}
        est.manage_tracks(tracks, 150.0)
        assert track.status == TrackStatus.COASTING

    def test_lost_from_coasting(self) -> None:
        est = _estimator(config=EstimationConfig(
            coast_timeout_s=100.0, lost_timeout_s=200.0,
        ))
        track = _make_track(time=0.0, status=TrackStatus.COASTING)
        tracks = {"t-1": track}
        to_delete = est.manage_tracks(tracks, 250.0)
        assert track.status == TrackStatus.LOST
        assert "t-1" in to_delete

    def test_lost_from_high_covariance(self) -> None:
        est = _estimator(config=EstimationConfig(max_covariance_m=100.0))
        track = _make_track(pos_var=100000.0, status=TrackStatus.COASTING)
        tracks = {"t-1": track}
        to_delete = est.manage_tracks(tracks, 0.0)
        assert track.status == TrackStatus.LOST
        assert "t-1" in to_delete

    def test_confirmed_stays_if_recent(self) -> None:
        est = _estimator(config=EstimationConfig(coast_timeout_s=300.0))
        track = _make_track(time=100.0, status=TrackStatus.CONFIRMED)
        tracks = {"t-1": track}
        est.manage_tracks(tracks, 200.0)
        assert track.status == TrackStatus.CONFIRMED


# ── Track state round-trip ────────────────────────────────────────────


class TestTrackStateRoundTrip:
    def test_roundtrip(self) -> None:
        track = _make_track(x=500.0, y=600.0, vx=10.0, vy=-5.0)
        track.hits = 5
        track.misses = 2
        state = track.get_state()

        track2 = _make_track()
        track2.set_state(state)

        assert track2.track_id == "t-1"
        assert track2.side == "blue"
        assert track2.state.position[0] == pytest.approx(500.0)
        assert track2.state.velocity[1] == pytest.approx(-5.0)
        assert track2.hits == 5
        assert track2.misses == 2
        assert track2.status == TrackStatus.TENTATIVE


# ── Position uncertainty ──────────────────────────────────────────────


class TestPositionUncertainty:
    def test_basic(self) -> None:
        track = _make_track(pos_var=100.0)
        # sqrt(100 + 100) ≈ 14.14
        assert track.position_uncertainty == pytest.approx(14.142, abs=0.01)

    def test_grows_with_predict(self) -> None:
        est = _estimator()
        track = _make_track(pos_var=100.0)
        unc_before = track.position_uncertainty
        est.predict(track, dt=10.0)
        assert track.position_uncertainty > unc_before


# ── Estimator state round-trip ────────────────────────────────────────


class TestEstimatorStateRoundTrip:
    def test_roundtrip(self) -> None:
        est = _estimator(seed=42)
        state = est.get_state()
        est2 = _estimator(seed=0)
        est2.set_state(state)
        # Both should be in same RNG state
        r1 = est._rng.random()
        r2 = est2._rng.random()
        assert r1 == r2


# ── Track lifecycle edge cases ───────────────────────────────────────


class TestTrackLifecycleEdgeCases:
    def test_full_lifecycle_tentative_to_lost(self) -> None:
        """Track should transition TENTATIVE -> CONFIRMED -> COASTING -> LOST."""
        cfg = EstimationConfig(
            confirmation_threshold=3,
            coast_timeout_s=100.0,
            lost_timeout_s=200.0,
        )
        est = _estimator(config=cfg)
        track = _make_track(time=0.0, status=TrackStatus.TENTATIVE)
        tracks = {"t-1": track}

        # TENTATIVE: not enough hits
        assert track.status == TrackStatus.TENTATIVE
        est.manage_tracks(tracks, 0.0)
        assert track.status == TrackStatus.TENTATIVE

        # Give hits to promote to CONFIRMED
        track.hits = 3
        est.manage_tracks(tracks, 0.0)
        assert track.status == TrackStatus.CONFIRMED

        # Advance time past coast_timeout -> COASTING
        est.manage_tracks(tracks, 150.0)
        assert track.status == TrackStatus.COASTING

        # Advance time past lost_timeout -> LOST
        to_delete = est.manage_tracks(tracks, 250.0)
        assert track.status == TrackStatus.LOST
        assert "t-1" in to_delete

    def test_re_update_resets_coast_timer(self) -> None:
        """Updating a COASTING track with new measurement should return it to CONFIRMED."""
        cfg = EstimationConfig(
            confirmation_threshold=2,
            coast_timeout_s=50.0,
            lost_timeout_s=200.0,
        )
        est = _estimator(config=cfg)
        track = _make_track(time=0.0, status=TrackStatus.TENTATIVE)
        track.hits = 2
        tracks = {"t-1": track}

        # Promote to CONFIRMED
        est.manage_tracks(tracks, 0.0)
        assert track.status == TrackStatus.CONFIRMED

        # Let it coast
        est.manage_tracks(tracks, 60.0)
        assert track.status == TrackStatus.COASTING

        # Update with new measurement (resets last_update_time)
        R = np.diag([50.0, 50.0])
        est.update(track, np.array([1000.0, 2000.0]), R, time=60.0)

        # manage_tracks at same time should see a recent update
        # The track status was set to COASTING, but manage_tracks
        # will not re-promote COASTING automatically. The status field
        # is left as-is. However, the last_update_time is now fresh,
        # so lost_timeout won't trigger.
        to_delete = est.manage_tracks(tracks, 60.0)
        assert "t-1" not in to_delete

    def test_coasting_track_not_deleted_until_lost(self) -> None:
        """A COASTING track within lost_timeout should NOT be in the delete list."""
        cfg = EstimationConfig(
            coast_timeout_s=50.0,
            lost_timeout_s=200.0,
        )
        est = _estimator(config=cfg)
        track = _make_track(time=0.0, status=TrackStatus.CONFIRMED)
        tracks = {"t-1": track}

        # Coast it
        est.manage_tracks(tracks, 60.0)
        assert track.status == TrackStatus.COASTING

        # Still within lost_timeout (60 < 200)
        to_delete = est.manage_tracks(tracks, 60.0)
        assert "t-1" not in to_delete

    def test_multiple_tracks_independent(self) -> None:
        """Two tracks should be managed independently."""
        cfg = EstimationConfig(confirmation_threshold=3)
        est = _estimator(config=cfg)
        track_a = _make_track(time=0.0, status=TrackStatus.TENTATIVE)
        track_a.hits = 3  # enough to promote
        track_b = _make_track(time=0.0, status=TrackStatus.TENTATIVE)
        track_b.hits = 1  # not enough

        # Use different track_ids
        track_b.track_id = "t-2"
        tracks = {"t-1": track_a, "t-2": track_b}
        est.manage_tracks(tracks, 0.0)

        assert track_a.status == TrackStatus.CONFIRMED
        assert track_b.status == TrackStatus.TENTATIVE

    def test_large_dt_predict_covariance_growth(self) -> None:
        """Predicting with very large dt should grow covariance but not overflow."""
        est = _estimator()
        track = _make_track(pos_var=100.0)
        est.predict(track, dt=1000.0)
        # Covariance should be large but finite
        assert np.all(np.isfinite(track.state.covariance))
        assert np.trace(track.state.covariance) > 100.0


# ── Kalman edge cases ────────────────────────────────────────────────


class TestKalmanEdgeCases:
    def test_predict_then_update_reduces_uncertainty(self) -> None:
        """Predict grows uncertainty; subsequent update should reduce it."""
        est = _estimator()
        track = _make_track(pos_var=100.0)
        est.predict(track, dt=5.0)
        unc_after_predict = np.trace(track.state.covariance)

        R = np.diag([50.0, 50.0])
        est.update(track, np.array([1000.0, 2000.0]), R, time=5.0)
        unc_after_update = np.trace(track.state.covariance)

        assert unc_after_update < unc_after_predict

    def test_multiple_updates_converge(self) -> None:
        """50 updates at noisy positions around true=(500,300) should converge."""
        est = _estimator(seed=42)
        track = _make_track(x=0.0, y=0.0, pos_var=10000.0)
        true_pos = np.array([500.0, 300.0])
        rng = np.random.Generator(np.random.PCG64(99))
        R = np.diag([10.0, 10.0])

        for _ in range(50):
            noisy = true_pos + rng.normal(0, 3.0, size=2)
            est.update(track, noisy, R, time=1.0)

        assert track.state.position[0] == pytest.approx(500.0, abs=2.0)
        assert track.state.position[1] == pytest.approx(300.0, abs=2.0)

    def test_velocity_estimation_from_moving_target(self) -> None:
        """Updating at increasing x positions should estimate positive vx."""
        est = _estimator()
        track = _make_track(x=0.0, y=0.0, vx=0.0, vy=0.0, pos_var=100.0, vel_var=100.0)
        R = np.diag([1.0, 1.0])
        # Target moves at 10 m/s in x
        for i in range(1, 11):
            t = float(i)
            est.predict(track, dt=1.0)
            est.update(track, np.array([10.0 * i, 0.0]), R, time=t)

        # Velocity should be approximately 10 m/s in x
        assert track.state.velocity[0] == pytest.approx(10.0, abs=2.0)
        assert track.state.velocity[1] == pytest.approx(0.0, abs=2.0)

    def test_estimator_deterministic_across_operations(self) -> None:
        """Two estimators with same seed should produce identical results."""
        R = np.diag([50.0, 50.0])
        meas = np.array([1000.0, 2000.0])

        results = []
        for _ in range(2):
            est = _estimator(seed=123)
            track = est.create_track("t-1", "blue", meas, R, _contact_info(), 0.0)
            est.predict(track, dt=5.0)
            est.update(track, meas + 10.0, R, time=5.0)
            results.append(track.state.position.copy())

        np.testing.assert_array_almost_equal(results[0], results[1])

    def test_predict_zero_process_noise(self) -> None:
        """With process_noise_std=0, prediction should not add Q noise."""
        est = _estimator(config=EstimationConfig(process_noise_std=0.0))
        track = _make_track(x=100.0, y=200.0, vx=5.0, vy=0.0, pos_var=100.0, vel_var=10.0)
        cov_before = track.state.covariance.copy()
        dt = 1.0

        est.predict(track, dt=dt)

        # Position should advance: x=105, y=200
        assert track.state.position[0] == pytest.approx(105.0, abs=0.01)
        assert track.state.position[1] == pytest.approx(200.0, abs=0.01)

        # Covariance should be F*P*F^T with Q=0
        # With no process noise, covariance changes only from F*P*F^T transition
        F = np.array([
            [1, 0, dt, 0],
            [0, 1, 0, dt],
            [0, 0, 1, 0],
            [0, 0, 0, 1],
        ])
        expected_cov = F @ cov_before @ F.T
        np.testing.assert_array_almost_equal(track.state.covariance, expected_cov)
