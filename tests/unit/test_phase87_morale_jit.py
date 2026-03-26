"""Phase 87c: Morale state machine JIT kernel tests.

Validates that JIT-extracted kernels for morale transition matrices
produce identical results to the original MoraleStateMachine methods.
"""

from __future__ import annotations

import numpy as np
import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.morale.state import (
    MoraleConfig,
    MoraleState,
    MoraleStateMachine,
    _continuous_transition_kernel,
    _transition_matrix_kernel,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _default_cfg():
    return MoraleConfig()


def _cfg_params(cfg: MoraleConfig) -> dict:
    """Extract config params as a dict for kernel calls."""
    return dict(
        base_degrade_rate=cfg.base_degrade_rate,
        casualty_weight=cfg.casualty_weight,
        suppression_weight=cfg.suppression_weight,
        force_ratio_weight=cfg.force_ratio_weight,
        base_recover_rate=cfg.base_recover_rate,
        leadership_weight=cfg.leadership_weight,
        cohesion_weight=cfg.cohesion_weight,
    )


# ---------------------------------------------------------------------------
# 87c: Discrete transition matrix kernel
# ---------------------------------------------------------------------------


class TestTransitionMatrixKernel:

    def test_matches_engine_typical(self):
        cfg = _default_cfg()
        rng = np.random.default_rng(42)
        sm = MoraleStateMachine(EventBus(), rng, config=cfg)

        params = dict(casualty_rate=0.1, suppression_level=0.3,
                      leadership_present=True, cohesion=0.7, force_ratio=0.8)
        expected = sm.compute_transition_matrix(**params, cbrn_stress=0.0)

        actual = _transition_matrix_kernel(
            0.1, 0.3, 1.0, 0.7, 0.8, 0.0, **_cfg_params(cfg),
        )
        np.testing.assert_allclose(actual, expected, atol=1e-12)

    def test_matches_engine_no_leadership(self):
        cfg = _default_cfg()
        rng = np.random.default_rng(42)
        sm = MoraleStateMachine(EventBus(), rng, config=cfg)

        expected = sm.compute_transition_matrix(
            0.2, 0.5, False, 0.4, 1.5, cbrn_stress=0.1,
        )
        actual = _transition_matrix_kernel(
            0.2, 0.5, 0.0, 0.4, 1.5, 0.1, **_cfg_params(cfg),
        )
        np.testing.assert_allclose(actual, expected, atol=1e-12)

    def test_row_stochastic(self):
        """Each row sums to 1.0."""
        matrix = _transition_matrix_kernel(
            0.15, 0.4, 1.0, 0.6, 0.9, 0.0, **_cfg_params(_default_cfg()),
        )
        for i in range(5):
            assert matrix[i].sum() == pytest.approx(1.0, abs=1e-12)

    def test_surrendered_absorbing(self):
        """SURRENDERED (row 4) stays in SURRENDERED."""
        matrix = _transition_matrix_kernel(
            0.5, 0.8, 0.0, 0.1, 0.3, 0.2, **_cfg_params(_default_cfg()),
        )
        assert matrix[4, 4] == pytest.approx(1.0)
        assert matrix[4, 3] == pytest.approx(0.0)

    def test_steady_no_recover(self):
        """STEADY (row 0) cannot improve — p_up = 0."""
        matrix = _transition_matrix_kernel(
            0.0, 0.0, 1.0, 1.0, 2.0, 0.0, **_cfg_params(_default_cfg()),
        )
        # Row 0 should have zero in column -1 (doesn't exist) and
        # no probability mass to the left
        assert matrix[0, 0] + matrix[0, 1] == pytest.approx(1.0, abs=1e-12)

    def test_determinism(self):
        """Same inputs produce identical matrices."""
        kw = dict(casualty_rate=0.1, suppression_level=0.2,
                  leadership_present_f=1.0, cohesion=0.5,
                  force_ratio=1.0, cbrn_stress=0.0,
                  **_cfg_params(_default_cfg()))
        a = _transition_matrix_kernel(**kw)
        b = _transition_matrix_kernel(**kw)
        np.testing.assert_array_equal(a, b)


# ---------------------------------------------------------------------------
# 87c: Continuous transition kernel
# ---------------------------------------------------------------------------


class TestContinuousTransitionKernel:

    def test_matches_engine(self):
        cfg = _default_cfg()
        rng = np.random.default_rng(42)
        sm = MoraleStateMachine(EventBus(), rng, config=cfg)

        expected = sm.compute_continuous_transition_probs(
            0.15, 0.3, True, 0.6, 0.9, dt=5.0,
        )
        actual = _continuous_transition_kernel(
            0.15, 0.3, 1.0, 0.6, 0.9, 5.0, **_cfg_params(cfg),
        )
        np.testing.assert_allclose(actual, expected, atol=1e-12)

    def test_row_stochastic(self):
        matrix = _continuous_transition_kernel(
            0.2, 0.4, 0.0, 0.5, 1.2, 2.0, **_cfg_params(_default_cfg()),
        )
        for i in range(5):
            assert matrix[i].sum() == pytest.approx(1.0, abs=1e-12)

    def test_dt_zero_is_identity(self):
        """With dt=0, no transitions occur — matrix is identity."""
        matrix = _continuous_transition_kernel(
            0.3, 0.5, 1.0, 0.5, 0.8, 0.0, **_cfg_params(_default_cfg()),
        )
        np.testing.assert_allclose(matrix, np.eye(5), atol=1e-12)

    def test_surrendered_absorbing(self):
        matrix = _continuous_transition_kernel(
            0.5, 0.8, 0.0, 0.1, 0.3, 1.0, **_cfg_params(_default_cfg()),
        )
        assert matrix[4, 4] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 87c: Full engine integration (kernel wired correctly)
# ---------------------------------------------------------------------------


class TestMoraleEngineIntegration:

    def test_check_transition_uses_kernel(self):
        """check_transition still works after kernel wiring."""
        cfg = _default_cfg()
        rng = np.random.default_rng(42)
        sm = MoraleStateMachine(EventBus(), rng, config=cfg)

        # Run enough transitions to verify no crash
        for _ in range(10):
            sm.check_transition(
                "u1", casualty_rate=0.3, suppression_level=0.5,
                leadership_present=False, cohesion=0.3, force_ratio=0.5,
            )

    def test_continuous_mode_uses_kernel(self):
        cfg = MoraleConfig(use_continuous_time=True)
        rng = np.random.default_rng(42)
        sm = MoraleStateMachine(EventBus(), rng, config=cfg)

        for _ in range(10):
            sm.check_transition(
                "u1", casualty_rate=0.2, suppression_level=0.4,
                leadership_present=True, cohesion=0.5, force_ratio=0.8,
                dt=5.0,
            )
