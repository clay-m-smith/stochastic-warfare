"""Phase 16c tests — Electronic Protection (ECCM).

Tests frequency hopping, spread spectrum, sidelobe blanking, adaptive nulling,
combined ECCM techniques, and suite registration/state.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.ew.eccm import ECCMEngine, ECCMSuite, ECCMTechnique
from stochastic_warfare.ew.events import ECCMActivatedEvent

TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def _make_suite(**kwargs) -> ECCMSuite:
    defaults = dict(
        suite_id="s1", unit_id="u1", techniques=[],
        hop_bandwidth_ghz=0.0, hop_rate_hz=0.0,
        spread_bandwidth_ghz=0.0, signal_bandwidth_ghz=0.001,
        processing_gain_db=0.0, sidelobe_ratio_db=25.0,
        null_depth_db=30.0, num_elements=8, max_nulls=3, active=True,
    )
    defaults.update(kwargs)
    return ECCMSuite(**defaults)


# =========================================================================
# Frequency Hopping
# =========================================================================


class TestFreqHopReduction:

    def test_wider_hop_large_reduction(self):
        eng = ECCMEngine(EventBus())
        suite = _make_suite(
            techniques=[ECCMTechnique.FREQUENCY_HOP],
            hop_bandwidth_ghz=2.0,
        )
        # Jammer BW 0.1 GHz, hop BW 2.0 → ratio=20 → ~13 dB
        reduction = eng.compute_jam_reduction(suite, jammer_bw_ghz=0.1)
        assert reduction == pytest.approx(13.01, abs=0.1)

    def test_narrower_hop_small_reduction(self):
        eng = ECCMEngine(EventBus())
        suite = _make_suite(
            techniques=[ECCMTechnique.FREQUENCY_HOP],
            hop_bandwidth_ghz=0.2,
        )
        # Jammer BW 0.1, hop BW 0.2 → ratio=2 → ~3 dB
        reduction = eng.compute_jam_reduction(suite, jammer_bw_ghz=0.1)
        assert reduction == pytest.approx(3.01, abs=0.1)

    def test_zero_hop_bw_zero_reduction(self):
        eng = ECCMEngine(EventBus())
        suite = _make_suite(
            techniques=[ECCMTechnique.FREQUENCY_HOP],
            hop_bandwidth_ghz=0.0,
        )
        reduction = eng.compute_jam_reduction(suite, jammer_bw_ghz=0.1)
        assert reduction == 0.0

    def test_jammer_wider_than_hop_no_reduction(self):
        eng = ECCMEngine(EventBus())
        suite = _make_suite(
            techniques=[ECCMTechnique.FREQUENCY_HOP],
            hop_bandwidth_ghz=0.1,
        )
        # Jammer BW wider than hop BW → no benefit
        reduction = eng.compute_jam_reduction(suite, jammer_bw_ghz=1.0)
        assert reduction == 0.0


# =========================================================================
# Spread Spectrum
# =========================================================================


class TestSpreadSpectrum:

    def test_gain_proportional_to_spread(self):
        eng = ECCMEngine(EventBus())
        suite = _make_suite(
            techniques=[ECCMTechnique.SPREAD_SPECTRUM],
            spread_bandwidth_ghz=1.0, signal_bandwidth_ghz=0.001,
        )
        # Ratio = 1000 → 30 dB
        reduction = eng.compute_jam_reduction(suite)
        assert reduction == pytest.approx(30.0, abs=0.1)

    def test_no_spread_no_gain(self):
        eng = ECCMEngine(EventBus())
        suite = _make_suite(
            techniques=[ECCMTechnique.SPREAD_SPECTRUM],
            spread_bandwidth_ghz=0.0,
        )
        reduction = eng.compute_jam_reduction(suite)
        assert reduction == 0.0

    def test_large_spread(self):
        eng = ECCMEngine(EventBus())
        suite = _make_suite(
            techniques=[ECCMTechnique.SPREAD_SPECTRUM],
            spread_bandwidth_ghz=10.0, signal_bandwidth_ghz=0.001,
        )
        # Ratio = 10000 → 40 dB
        reduction = eng.compute_jam_reduction(suite)
        assert reduction == pytest.approx(40.0, abs=0.1)


# =========================================================================
# Sidelobe Blanking
# =========================================================================


class TestSidelobeBlanking:

    def test_sidelobe_energy_reduced(self):
        eng = ECCMEngine(EventBus())
        suite = _make_suite(
            techniques=[ECCMTechnique.SIDELOBE_BLANKING],
            sidelobe_ratio_db=25.0,
        )
        reduction = eng.compute_jam_reduction(suite, js_ratio_db=10.0)
        assert reduction == pytest.approx(25.0)

    def test_low_js_not_reduced(self):
        eng = ECCMEngine(EventBus())
        suite = _make_suite(
            techniques=[ECCMTechnique.SIDELOBE_BLANKING],
            sidelobe_ratio_db=25.0,
        )
        # J/S <= 0 → blanking not triggered
        reduction = eng.compute_jam_reduction(suite, js_ratio_db=-5.0)
        assert reduction == 0.0

    def test_ratio_effect(self):
        eng = ECCMEngine(EventBus())
        s_high = _make_suite(
            suite_id="s1", techniques=[ECCMTechnique.SIDELOBE_BLANKING],
            sidelobe_ratio_db=30.0,
        )
        s_low = _make_suite(
            suite_id="s2", techniques=[ECCMTechnique.SIDELOBE_BLANKING],
            sidelobe_ratio_db=15.0,
        )
        r_high = eng.compute_jam_reduction(s_high, js_ratio_db=10.0)
        r_low = eng.compute_jam_reduction(s_low, js_ratio_db=10.0)
        assert r_high > r_low


# =========================================================================
# Adaptive Nulling
# =========================================================================


class TestAdaptiveNulling:

    def test_null_in_direction(self):
        eng = ECCMEngine(EventBus())
        suite = _make_suite(
            techniques=[ECCMTechnique.ADAPTIVE_NULLING],
            null_depth_db=30.0, num_elements=8, max_nulls=3,
        )
        reduction = eng.compute_jam_reduction(suite, jammer_direction_deg=45.0)
        assert reduction == pytest.approx(30.0)

    def test_no_direction_no_null(self):
        eng = ECCMEngine(EventBus())
        suite = _make_suite(
            techniques=[ECCMTechnique.ADAPTIVE_NULLING],
            null_depth_db=30.0, num_elements=8, max_nulls=3,
        )
        reduction = eng.compute_jam_reduction(suite, jammer_direction_deg=None)
        assert reduction == 0.0

    def test_few_elements_limited(self):
        eng = ECCMEngine(EventBus())
        suite = _make_suite(
            techniques=[ECCMTechnique.ADAPTIVE_NULLING],
            null_depth_db=30.0, num_elements=1, max_nulls=3,
        )
        # Only 1 element → can't form null
        reduction = eng.compute_jam_reduction(suite, jammer_direction_deg=45.0)
        assert reduction == 0.0


# =========================================================================
# Combined ECCM
# =========================================================================


class TestCombinedECCM:

    def test_multiple_techniques_additive(self):
        eng = ECCMEngine(EventBus())
        suite = _make_suite(
            techniques=[ECCMTechnique.FREQUENCY_HOP, ECCMTechnique.SPREAD_SPECTRUM],
            hop_bandwidth_ghz=2.0,
            spread_bandwidth_ghz=1.0, signal_bandwidth_ghz=0.001,
        )
        reduction = eng.compute_jam_reduction(suite, jammer_bw_ghz=0.1)
        # ~13 (hop) + ~30 (spread) ≈ 43
        assert reduction > 40.0

    def test_no_techniques_zero(self):
        eng = ECCMEngine(EventBus())
        suite = _make_suite(techniques=[])
        reduction = eng.compute_jam_reduction(suite, jammer_bw_ghz=0.1)
        assert reduction == 0.0

    def test_all_combined(self):
        eng = ECCMEngine(EventBus())
        suite = _make_suite(
            techniques=[
                ECCMTechnique.FREQUENCY_HOP,
                ECCMTechnique.SPREAD_SPECTRUM,
                ECCMTechnique.SIDELOBE_BLANKING,
                ECCMTechnique.ADAPTIVE_NULLING,
            ],
            hop_bandwidth_ghz=2.0,
            spread_bandwidth_ghz=1.0, signal_bandwidth_ghz=0.001,
            sidelobe_ratio_db=25.0, null_depth_db=30.0,
            num_elements=8, max_nulls=3,
        )
        reduction = eng.compute_jam_reduction(
            suite, jammer_bw_ghz=0.1, js_ratio_db=10.0,
            jammer_direction_deg=45.0,
        )
        # All four contribute
        assert reduction > 90.0


# =========================================================================
# Registration & Events
# =========================================================================


class TestECCMRegistration:

    def test_register_suite(self):
        eng = ECCMEngine(EventBus())
        suite = _make_suite()
        eng.register_suite(suite)
        found = eng.get_suite_for_unit("u1")
        assert found is not None
        assert found.suite_id == "s1"

    def test_activation_event(self):
        bus = EventBus()
        received = []
        bus.subscribe(ECCMActivatedEvent, received.append)
        eng = ECCMEngine(bus)
        suite = _make_suite(techniques=[ECCMTechnique.FREQUENCY_HOP])
        eng.register_suite(suite)
        eng.activate_suite("s1", timestamp=TS)
        assert len(received) == 1
        assert received[0].unit_id == "u1"


# =========================================================================
# State Persistence
# =========================================================================


class TestECCMState:

    def test_state_roundtrip(self):
        eng = ECCMEngine(EventBus())
        suite = _make_suite(
            techniques=[ECCMTechnique.FREQUENCY_HOP, ECCMTechnique.SPREAD_SPECTRUM],
            hop_bandwidth_ghz=2.0, spread_bandwidth_ghz=1.0,
        )
        eng.register_suite(suite)
        state = eng.get_state()

        eng2 = ECCMEngine(EventBus())
        eng2.set_state(state)
        found = eng2.get_suite_for_unit("u1")
        assert found is not None
        assert ECCMTechnique.FREQUENCY_HOP in found.techniques

    def test_inactive_suite_no_reduction(self):
        eng = ECCMEngine(EventBus())
        suite = _make_suite(
            techniques=[ECCMTechnique.FREQUENCY_HOP],
            hop_bandwidth_ghz=2.0, active=False,
        )
        reduction = eng.compute_jam_reduction(suite, jammer_bw_ghz=0.1)
        assert reduction == 0.0
