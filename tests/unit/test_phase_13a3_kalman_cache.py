"""Phase 13a-3: Kalman F/Q matrix caching tests."""

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


def _make_track(track_id: str = "t1") -> Track:
    ci = ContactInfo(
        level=ContactLevel.DETECTED,
        domain_estimate=None,
        type_estimate=None,
        specific_estimate=None,
        confidence=0.5,
    )
    ts = TrackState(
        position=np.array([1000.0, 2000.0]),
        velocity=np.array([10.0, 5.0]),
        covariance=np.eye(4) * 100.0,
        last_update_time=0.0,
    )
    return Track(track_id=track_id, side="blue", contact_info=ci, state=ts)


class TestKalmanFQCaching:
    def test_cached_result_identical_to_uncached(self):
        """Cached prediction must produce identical result to uncached."""
        est = StateEstimator(rng=np.random.default_rng(0), config=EstimationConfig())
        # First call: computes F, Q and caches
        t1 = _make_track("t1")
        est.predict(t1, 5.0)
        # Second call: reuses cached F, Q
        t2 = _make_track("t2")
        est.predict(t2, 5.0)

        # Both should produce the same result since initial state is identical
        np.testing.assert_array_almost_equal(t1.state.position, t2.state.position)
        np.testing.assert_array_almost_equal(t1.state.velocity, t2.state.velocity)
        np.testing.assert_array_almost_equal(t1.state.covariance, t2.state.covariance)

    def test_cache_invalidation_on_dt_change(self):
        """Changing dt must recompute F and Q."""
        est = StateEstimator(rng=np.random.default_rng(0), config=EstimationConfig())
        t1 = _make_track("t1")
        est.predict(t1, 5.0)
        assert est._cached_dt == 5.0

        t2 = _make_track("t2")
        est.predict(t2, 10.0)
        assert est._cached_dt == 10.0

        # Different dt should give different results
        assert not np.allclose(t1.state.covariance, t2.state.covariance)

    def test_multiple_dt_values(self):
        """Switching between multiple dt values produces correct results."""
        est = StateEstimator(rng=np.random.default_rng(0), config=EstimationConfig())
        dts = [5.0, 10.0, 5.0, 1.0, 5.0]
        results = []
        for dt in dts:
            t = _make_track()
            est.predict(t, dt)
            results.append((t.state.position.copy(), t.state.covariance.copy()))

        # Same dt should give same result
        np.testing.assert_array_almost_equal(results[0][0], results[2][0])
        np.testing.assert_array_almost_equal(results[0][0], results[4][0])
        np.testing.assert_array_almost_equal(results[0][1], results[2][1])

    def test_cache_initial_state_none(self):
        """Cache starts as None."""
        est = StateEstimator(rng=np.random.default_rng(0), config=EstimationConfig())
        assert est._cached_dt is None
        assert est._cached_F is None
        assert est._cached_Q is None

    def test_cache_populated_after_first_predict(self):
        """Cache is populated after first predict call."""
        est = StateEstimator(rng=np.random.default_rng(0), config=EstimationConfig())
        t = _make_track()
        est.predict(t, 5.0)
        assert est._cached_dt == 5.0
        assert est._cached_F is not None
        assert est._cached_Q is not None
        assert est._cached_F.shape == (4, 4)
        assert est._cached_Q.shape == (4, 4)

    def test_cache_uses_same_object(self):
        """When dt is unchanged, the same array objects are reused."""
        est = StateEstimator(rng=np.random.default_rng(0), config=EstimationConfig())
        t1 = _make_track()
        est.predict(t1, 5.0)
        F_ref = est._cached_F
        Q_ref = est._cached_Q

        t2 = _make_track()
        est.predict(t2, 5.0)
        assert est._cached_F is F_ref
        assert est._cached_Q is Q_ref
