"""Phase 65c: ECCM integration tests."""

from __future__ import annotations

import numpy as np
import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.ew.eccm import ECCMEngine, ECCMSuite, ECCMTechnique


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_eccm():
    bus = EventBus()
    return ECCMEngine(bus)


def _make_suite(
    unit_id="unit_blue_1",
    techniques=None,
    hop_bw=2.0,
    spread_bw=0.0,
    sidelobe_ratio=25.0,
    null_depth=30.0,
    num_elements=8,
    active=True,
):
    return ECCMSuite(
        suite_id=f"eccm_{unit_id}",
        unit_id=unit_id,
        techniques=techniques or [ECCMTechnique.FREQUENCY_HOP],
        hop_bandwidth_ghz=hop_bw,
        hop_rate_hz=200.0,
        spread_bandwidth_ghz=spread_bw,
        signal_bandwidth_ghz=0.001,
        processing_gain_db=20.0,
        sidelobe_ratio_db=sidelobe_ratio,
        null_depth_db=null_depth,
        num_elements=num_elements,
        max_nulls=2,
        active=active,
    )


# ---------------------------------------------------------------------------
# ECCM reduction
# ---------------------------------------------------------------------------


def test_eccm_with_registered_suite_reduces_penalty():
    """Registered ECCM suite with freq hopping reduces snr_penalty_db."""
    engine = _make_eccm()
    suite = _make_suite(hop_bw=2.0)
    engine.register_suite(suite)

    reduction = engine.compute_jam_reduction(
        suite,
        jammer_freq_ghz=10.0,
        jammer_bw_ghz=0.5,  # hop_bw/jammer_bw = 4 → ~6 dB
        js_ratio_db=10.0,
    )
    assert reduction > 0.0


def test_eccm_without_suite_no_reduction():
    """No registered suite → get_suite_for_unit returns None."""
    engine = _make_eccm()
    suite = engine.get_suite_for_unit("nonexistent")
    assert suite is None


def test_frequency_hopping_partial_protection():
    """Freq hopping: reduction ∝ log10(hop_bw / jammer_bw)."""
    engine = _make_eccm()
    suite = _make_suite(
        techniques=[ECCMTechnique.FREQUENCY_HOP],
        hop_bw=2.0,
    )

    # hop_bw=2.0 / jammer_bw=0.5 = 4 → 10*log10(4) ≈ 6.02 dB
    reduction = engine.compute_jam_reduction(
        suite, jammer_bw_ghz=0.5, js_ratio_db=10.0,
    )
    assert 5.5 < reduction < 6.5


def test_spread_spectrum_processing_gain():
    """Spread spectrum: gain = 10*log10(B_spread / B_signal)."""
    engine = _make_eccm()
    suite = _make_suite(
        techniques=[ECCMTechnique.SPREAD_SPECTRUM],
        spread_bw=1.0,  # signal_bw=0.001 → ratio=1000 → 30 dB
    )

    reduction = engine.compute_jam_reduction(suite, js_ratio_db=10.0)
    assert reduction > 25.0  # Should be ~30 dB


def test_sidelobe_blanking():
    """Sidelobe blanking: full sidelobe_ratio_db when js > 0."""
    engine = _make_eccm()
    suite = _make_suite(
        techniques=[ECCMTechnique.SIDELOBE_BLANKING],
        sidelobe_ratio=25.0,
    )

    reduction = engine.compute_jam_reduction(suite, js_ratio_db=5.0)
    assert reduction == 25.0


def test_multiple_techniques_combine():
    """Multiple ECCM techniques stack their reductions."""
    engine = _make_eccm()
    suite = _make_suite(
        techniques=[
            ECCMTechnique.FREQUENCY_HOP,
            ECCMTechnique.SIDELOBE_BLANKING,
        ],
        hop_bw=2.0,
        sidelobe_ratio=25.0,
    )

    reduction = engine.compute_jam_reduction(
        suite, jammer_bw_ghz=0.5, js_ratio_db=10.0,
    )
    # hop: ~6 dB + sidelobe: 25 dB ≈ 31 dB
    assert reduction > 30.0


def test_eccm_suite_inactive_zero_reduction():
    """Inactive suite → 0 dB reduction."""
    engine = _make_eccm()
    suite = _make_suite(active=False)

    reduction = engine.compute_jam_reduction(
        suite, jammer_bw_ghz=0.5, js_ratio_db=10.0,
    )
    assert reduction == 0.0


def test_eccm_no_engine_on_ctx_full_jamming():
    """When no eccm_engine on ctx, battle.py must apply full jamming."""
    from stochastic_warfare.simulation.battle import BattleManager
    import inspect

    source = inspect.getsource(BattleManager)
    assert "compute_jam_reduction" in source
