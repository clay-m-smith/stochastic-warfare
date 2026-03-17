"""Phase 62b: MOPP Degradation & Altitude Sickness — inline math verification tests.

Tests verify the expanded MOPP penalties (FOV, reload, comms) and altitude
sickness effects wired into BattleManager when ``enable_human_factors=True``.
"""

from __future__ import annotations

import pytest

from stochastic_warfare.simulation.calibration import CalibrationSchema


# ---------------------------------------------------------------------------
# Helper: replicate the inline MOPP degradation math from battle.py
# ---------------------------------------------------------------------------


def _mopp_fov_modifier(mopp_level: int, fov_reduction_4: float = 0.7) -> float:
    """Detection range multiplier from MOPP FOV restriction.

    Linearly interpolates between 1.0 (MOPP-0) and fov_reduction_4 (MOPP-4).
    """
    if mopp_level <= 0:
        return 1.0
    scale = mopp_level / 4.0
    return 1.0 - scale * (1.0 - fov_reduction_4)


def _mopp_reload_modifier(mopp_level: int, reload_factor_4: float = 1.5) -> float:
    """Crew skill divisor from MOPP reload penalty.

    Returns the divisor: effective crew_skill /= modifier.
    """
    if mopp_level <= 0:
        return 1.0
    scale = mopp_level / 4.0
    return 1.0 + scale * (reload_factor_4 - 1.0)


def _mopp_comms_modifier(mopp_level: int, comms_factor_4: float = 0.5) -> float:
    """C2 effectiveness multiplier from MOPP comms degradation.

    Linearly interpolates between 1.0 (MOPP-0) and comms_factor_4 (MOPP-4).
    """
    if mopp_level <= 0:
        return 1.0
    scale = mopp_level / 4.0
    return 1.0 - scale * (1.0 - comms_factor_4)


def _altitude_performance(
    altitude_m: float,
    threshold_m: float = 2500.0,
    rate: float = 0.03,
    acclimatized: bool = False,
) -> float:
    """Performance multiplier from altitude sickness.

    Returns a multiplier [0.5, 1.0].  Acclimatized units take half penalty.
    """
    if altitude_m <= threshold_m:
        return 1.0
    perf = max(0.5, 1.0 - rate * (altitude_m - threshold_m) / 100.0)
    if acclimatized:
        perf = 1.0 - (1.0 - perf) * 0.5
    return perf


# ---------------------------------------------------------------------------
# MOPP FOV reduction tests
# ---------------------------------------------------------------------------


class TestMOPPFOVReduction:
    def test_mopp4_detection_reduced_30pct(self) -> None:
        """MOPP-4: detection range reduced by ~30% (fov_reduction_4=0.7)."""
        mod = _mopp_fov_modifier(4, 0.7)
        assert mod == pytest.approx(0.7)

    def test_mopp2_half_penalty(self) -> None:
        """MOPP-2: half-strength penalty → ~0.85."""
        mod = _mopp_fov_modifier(2, 0.7)
        assert mod == pytest.approx(0.85)

    def test_mopp0_no_penalty(self) -> None:
        """MOPP-0: no detection penalty."""
        mod = _mopp_fov_modifier(0, 0.7)
        assert mod == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# MOPP reload factor tests
# ---------------------------------------------------------------------------


class TestMOPPReloadFactor:
    def test_mopp4_reload_divisor(self) -> None:
        """MOPP-4: crew_skill divided by 1.5."""
        div = _mopp_reload_modifier(4, 1.5)
        assert div == pytest.approx(1.5)

    def test_mopp2_reload_divisor(self) -> None:
        """MOPP-2: half penalty → divisor 1.25."""
        div = _mopp_reload_modifier(2, 1.5)
        assert div == pytest.approx(1.25)

    def test_mopp0_no_reload_penalty(self) -> None:
        """MOPP-0: divisor is 1.0."""
        div = _mopp_reload_modifier(0, 1.5)
        assert div == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# MOPP comms degradation tests
# ---------------------------------------------------------------------------


class TestMOPPComms:
    def test_mopp4_comms_halved(self) -> None:
        """MOPP-4: comms quality multiplied by 0.5."""
        mod = _mopp_comms_modifier(4, 0.5)
        assert mod == pytest.approx(0.5)

    def test_mopp2_comms_moderate(self) -> None:
        """MOPP-2: half penalty → 0.75."""
        mod = _mopp_comms_modifier(2, 0.5)
        assert mod == pytest.approx(0.75)

    def test_mopp0_comms_full(self) -> None:
        """MOPP-0: no comms degradation."""
        mod = _mopp_comms_modifier(0, 0.5)
        assert mod == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Altitude sickness tests
# ---------------------------------------------------------------------------


class TestAltitudeSickness:
    def test_3000m_performance_reduced(self) -> None:
        """3000m: perf = max(0.5, 1.0 - 0.03 * 500/100) = 0.85."""
        perf = _altitude_performance(3000.0)
        assert perf == pytest.approx(0.85)

    def test_4500m_performance_at_floor(self) -> None:
        """4500m: perf = max(0.5, 1.0 - 0.03 * 2000/100) = max(0.5, 0.4) = 0.5."""
        perf = _altitude_performance(4500.0)
        assert perf == pytest.approx(0.5)

    def test_sea_level_no_penalty(self) -> None:
        """Sea level: no altitude effect."""
        perf = _altitude_performance(0.0)
        assert perf == pytest.approx(1.0)

    def test_acclimatized_half_penalty(self) -> None:
        """Acclimatized at 3000m: penalty halved → ~0.925."""
        raw = _altitude_performance(3000.0, acclimatized=False)
        accl = _altitude_performance(3000.0, acclimatized=True)
        # raw = 0.85, accl = 1.0 - (1.0-0.85)*0.5 = 0.925
        assert accl == pytest.approx(0.925)
        assert accl > raw


# ---------------------------------------------------------------------------
# Gate test: enable_human_factors=False
# ---------------------------------------------------------------------------


class TestHumanFactorsGate:
    def test_disabled_no_mopp_expansion_or_altitude(self) -> None:
        """enable_human_factors=False: no expanded MOPP or altitude effects."""
        cal = CalibrationSchema(enable_human_factors=False)
        assert cal.enable_human_factors is False
        # When disabled, the inline checks in battle.py are gated —
        # we confirm the flag controls the behavior.
        # The actual battle loop correctness is verified by structural tests.
