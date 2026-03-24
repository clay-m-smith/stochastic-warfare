"""Phase 16d tests — Electronic Support (SIGINT).

Tests intercept probability, AOA geolocation, TDOA geolocation,
traffic analysis, SIGINT reporting, events, and state persistence.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position
from stochastic_warfare.ew.emitters import Emitter, EmitterType, WaveformType
from stochastic_warfare.ew.events import EmitterDetectedEvent, SIGINTReportEvent
from stochastic_warfare.ew.sigint import SIGINTCollector, SIGINTEngine, SIGINTType

TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def _make_collector(
    cid: str = "c1", pos: Position = Position(0.0, 0.0, 0.0),
    sensitivity: float = -90.0, freq_range: tuple = (1.0, 18.0),
    bw: float = 0.5, aperture: float = 2.0,
) -> SIGINTCollector:
    return SIGINTCollector(
        collector_id=cid, unit_id="u1", position=pos,
        receiver_sensitivity_dbm=sensitivity,
        frequency_range_ghz=freq_range, bandwidth_ghz=bw,
        df_accuracy_deg=1.0, aperture_m=aperture,
    )


def _make_emitter(
    eid: str = "e1", pos: Position = Position(10000.0, 0.0, 0.0),
    power: float = 60.0, freq: float = 10.0, gain: float = 30.0,
) -> Emitter:
    return Emitter(
        emitter_id=eid, unit_id="eu1", emitter_type=EmitterType.RADAR,
        position=pos, frequency_ghz=freq, bandwidth_ghz=0.1,
        power_dbm=power, antenna_gain_dbi=gain,
        waveform=WaveformType.PULSED, active=True, side="red",
    )


# =========================================================================
# Intercept Probability
# =========================================================================


class TestInterceptProbability:

    def test_high_power_high_probability(self):
        eng = SIGINTEngine(EventBus(), _rng())
        collector = _make_collector(sensitivity=-90.0)
        emitter = _make_emitter(power=80.0, pos=Position(5000.0, 0.0, 0.0))
        prob = eng.compute_intercept_probability(collector, emitter)
        assert prob > 0.8

    def test_distant_low_probability(self):
        eng = SIGINTEngine(EventBus(), _rng())
        collector = _make_collector(sensitivity=-90.0)
        emitter = _make_emitter(power=40.0, pos=Position(500000.0, 0.0, 0.0))
        prob = eng.compute_intercept_probability(collector, emitter)
        assert prob < 0.3

    def test_frequency_outside_range(self):
        eng = SIGINTEngine(EventBus(), _rng())
        collector = _make_collector(freq_range=(8.0, 12.0))
        emitter = _make_emitter(freq=3.0)
        prob = eng.compute_intercept_probability(collector, emitter)
        assert prob == 0.0

    def test_sensitivity_matters(self):
        eng = SIGINTEngine(EventBus(), _rng())
        c_good = _make_collector(cid="c_good", sensitivity=-110.0)
        c_poor = _make_collector(cid="c_poor", sensitivity=-50.0)
        emitter = _make_emitter(power=50.0, pos=Position(50000.0, 0.0, 0.0))
        p_good = eng.compute_intercept_probability(c_good, emitter)
        p_poor = eng.compute_intercept_probability(c_poor, emitter)
        assert p_good > p_poor

    def test_close_emitter_certain(self):
        eng = SIGINTEngine(EventBus(), _rng())
        collector = _make_collector(sensitivity=-90.0)
        emitter = _make_emitter(power=60.0, pos=Position(100.0, 0.0, 0.0))
        prob = eng.compute_intercept_probability(collector, emitter)
        assert prob > 0.95


# =========================================================================
# AOA Geolocation
# =========================================================================


class TestAOAGeolocation:

    def test_close_emitter_accurate(self):
        eng = SIGINTEngine(EventBus(), _rng())
        collector = _make_collector(aperture=5.0)
        emitter = _make_emitter(power=80.0, pos=Position(5000.0, 0.0, 0.0))
        est_pos, uncertainty = eng.geolocate_aoa(collector, emitter)
        # Uncertainty should be reasonable
        assert uncertainty < 5000.0

    def test_far_emitter_less_accurate(self):
        eng = SIGINTEngine(EventBus(), _rng(0))
        collector = _make_collector(aperture=2.0)
        emitter_close = _make_emitter(power=60.0, pos=Position(5000.0, 0.0, 0.0))
        emitter_far = _make_emitter(eid="e2", power=60.0, pos=Position(200000.0, 0.0, 0.0))

        _, unc_close = eng.geolocate_aoa(collector, emitter_close)
        _, unc_far = eng.geolocate_aoa(collector, emitter_far)
        assert unc_far > unc_close

    def test_bearing_estimated(self):
        eng = SIGINTEngine(EventBus(), _rng())
        collector = _make_collector(pos=Position(0.0, 0.0, 0.0))
        emitter = _make_emitter(pos=Position(10000.0, 0.0, 0.0))  # Due east
        est_pos, _ = eng.geolocate_aoa(collector, emitter)
        # Estimated position should be roughly east
        assert est_pos.easting > 0

    def test_uncertainty_scales_with_snr(self):
        eng = SIGINTEngine(EventBus(), _rng(0))
        collector = _make_collector(sensitivity=-90.0)
        emitter_strong = _make_emitter(power=80.0, pos=Position(10000.0, 0.0, 0.0))
        emitter_weak = _make_emitter(eid="e2", power=30.0, pos=Position(10000.0, 0.0, 0.0))
        _, unc_strong = eng.geolocate_aoa(collector, emitter_strong)
        _, unc_weak = eng.geolocate_aoa(collector, emitter_weak)
        assert unc_strong < unc_weak


# =========================================================================
# TDOA Geolocation
# =========================================================================


class TestTDOAGeolocation:

    def test_three_collectors_triangulate(self):
        eng = SIGINTEngine(EventBus(), _rng())
        collectors = [
            _make_collector(cid="c1", pos=Position(0.0, 0.0, 0.0)),
            _make_collector(cid="c2", pos=Position(20000.0, 0.0, 0.0)),
            _make_collector(cid="c3", pos=Position(10000.0, 20000.0, 0.0)),
        ]
        emitter = _make_emitter(pos=Position(10000.0, 10000.0, 0.0))
        est_pos, uncertainty = eng.geolocate_tdoa(collectors, emitter)
        assert est_pos is not None
        assert uncertainty < float("inf")

    def test_baseline_length_matters(self):
        eng = SIGINTEngine(EventBus(), _rng(0))
        # Wide baseline
        wide = [
            _make_collector(cid="c1", pos=Position(0.0, 0.0, 0.0)),
            _make_collector(cid="c2", pos=Position(100000.0, 0.0, 0.0)),
            _make_collector(cid="c3", pos=Position(50000.0, 100000.0, 0.0)),
        ]
        # Narrow baseline
        narrow = [
            _make_collector(cid="c4", pos=Position(0.0, 0.0, 0.0)),
            _make_collector(cid="c5", pos=Position(100.0, 0.0, 0.0)),
            _make_collector(cid="c6", pos=Position(50.0, 100.0, 0.0)),
        ]
        emitter = _make_emitter(pos=Position(50000.0, 50000.0, 0.0))
        _, unc_wide = eng.geolocate_tdoa(wide, emitter)
        _, unc_narrow = eng.geolocate_tdoa(narrow, emitter)
        assert unc_wide < unc_narrow

    def test_bandwidth_precision(self):
        eng = SIGINTEngine(EventBus(), _rng(0))
        wide_bw = [
            _make_collector(cid=f"w{i}", pos=Position(i * 10000.0, 0.0, 0.0), bw=2.0)
            for i in range(3)
        ]
        narrow_bw = [
            _make_collector(cid=f"n{i}", pos=Position(i * 10000.0, 0.0, 0.0), bw=0.001)
            for i in range(3)
        ]
        emitter = _make_emitter(pos=Position(15000.0, 10000.0, 0.0))
        _, unc_wide_bw = eng.geolocate_tdoa(wide_bw, emitter)
        _, unc_narrow_bw = eng.geolocate_tdoa(narrow_bw, emitter)
        assert unc_wide_bw < unc_narrow_bw

    def test_fewer_than_three_fails(self):
        eng = SIGINTEngine(EventBus(), _rng())
        collectors = [
            _make_collector(cid="c1"),
            _make_collector(cid="c2", pos=Position(10000.0, 0.0, 0.0)),
        ]
        emitter = _make_emitter()
        est_pos, uncertainty = eng.geolocate_tdoa(collectors, emitter)
        assert est_pos is None
        assert uncertainty == float("inf")


# =========================================================================
# Traffic Analysis
# =========================================================================


class TestTrafficAnalysis:

    def test_high_volume_high_activity(self):
        eng = SIGINTEngine(EventBus(), _rng())
        collector = _make_collector()
        # 100 messages in 1 hour → high activity
        history = [float(i * 36) for i in range(100)]
        result = eng.analyze_traffic(collector, history)
        assert result["activity_level"] > 0.5
        assert result["estimated_rate"] > 50.0

    def test_below_threshold_low_activity(self):
        eng = SIGINTEngine(EventBus(), _rng())
        collector = _make_collector()
        # 2 messages in 1 hour → low activity
        history = [0.0, 3600.0]
        result = eng.analyze_traffic(collector, history)
        assert result["activity_level"] < 0.5

    def test_multi_emitter_trend(self):
        eng = SIGINTEngine(EventBus(), _rng())
        collector = _make_collector()
        # Increasing rate: 10 msgs in first hour, 50 in second
        history_first = [float(i * 360) for i in range(10)]
        history_second = [3600.0 + float(i * 72) for i in range(50)]
        result = eng.analyze_traffic(collector, history_first + history_second)
        assert result["trend"] > 0.0  # Increasing


# =========================================================================
# SIGINT Report
# =========================================================================


class TestSIGINTReport:

    def test_successful_generates_report(self):
        # Use seed that produces intercept
        found_success = False
        for seed in range(30):
            eng = SIGINTEngine(EventBus(), _rng(seed))
            collector = _make_collector(sensitivity=-110.0)
            emitter = _make_emitter(power=80.0, pos=Position(5000.0, 0.0, 0.0))
            report = eng.attempt_intercept(collector, emitter, timestamp=TS)
            if report.intercept_successful:
                assert report.estimated_position is not None
                assert report.estimated_frequency_ghz == emitter.frequency_ghz
                found_success = True
                break
        assert found_success

    def test_failed_no_position(self):
        # Very distant emitter → likely fails
        found_failure = False
        for seed in range(30):
            eng = SIGINTEngine(EventBus(), _rng(seed))
            collector = _make_collector(sensitivity=-50.0)
            emitter = _make_emitter(power=20.0, pos=Position(500000.0, 0.0, 0.0))
            report = eng.attempt_intercept(collector, emitter)
            if not report.intercept_successful:
                assert report.estimated_position is None
                assert report.estimated_frequency_ghz == 0.0
                found_failure = True
                break
        assert found_failure

    def test_sigint_type_assignment(self):
        eng = SIGINTEngine(EventBus(), _rng())
        collector = _make_collector()
        emitter = _make_emitter()
        report = eng.attempt_intercept(collector, emitter)
        assert report.sigint_type == SIGINTType.ELINT


# =========================================================================
# SIGINT Events
# =========================================================================


class TestSIGINTEvents:

    def test_intercept_publishes_emitter_event(self):
        bus = EventBus()
        emitter_events = []
        bus.subscribe(EmitterDetectedEvent, emitter_events.append)
        # Find seed that produces intercept
        for seed in range(30):
            eng = SIGINTEngine(bus, _rng(seed))
            collector = _make_collector(sensitivity=-110.0)
            emitter = _make_emitter(power=80.0, pos=Position(5000.0, 0.0, 0.0))
            report = eng.attempt_intercept(collector, emitter, timestamp=TS)
            if report.intercept_successful:
                assert len(emitter_events) > 0
                assert emitter_events[-1].emitter_id == "e1"
                return
        pytest.fail("No successful intercept in 30 seeds")

    def test_report_event_published(self):
        bus = EventBus()
        report_events = []
        bus.subscribe(SIGINTReportEvent, report_events.append)
        for seed in range(30):
            eng = SIGINTEngine(bus, _rng(seed))
            collector = _make_collector(sensitivity=-110.0)
            emitter = _make_emitter(power=80.0, pos=Position(5000.0, 0.0, 0.0))
            report = eng.attempt_intercept(collector, emitter, timestamp=TS)
            if report.intercept_successful:
                assert len(report_events) > 0
                return
        pytest.fail("No successful intercept in 30 seeds")

    def test_no_event_on_failure(self):
        bus = EventBus()
        events = []
        bus.subscribe(EmitterDetectedEvent, events.append)
        eng = SIGINTEngine(bus, _rng())
        collector = _make_collector(sensitivity=-30.0)
        emitter = _make_emitter(power=10.0, pos=Position(1000000.0, 0.0, 0.0))
        eng.attempt_intercept(collector, emitter, timestamp=TS)
        # Very weak emitter at extreme range → failure → no events
        assert len(events) == 0


# =========================================================================
# SIGINT State
# =========================================================================


class TestSIGINTState:

    def test_state_roundtrip(self):
        eng = SIGINTEngine(EventBus(), _rng())
        collector = _make_collector()
        eng.register_collector(collector)
        state = eng.get_state()

        eng2 = SIGINTEngine(EventBus(), _rng(99))
        eng2.set_state(state)
        assert "c1" in eng2._collectors

    def test_collector_registration_persists(self):
        eng = SIGINTEngine(EventBus(), _rng())
        c1 = _make_collector(cid="c1")
        c2 = _make_collector(cid="c2", pos=Position(10000.0, 0.0, 0.0))
        eng.register_collector(c1)
        eng.register_collector(c2)
        state = eng.get_state()

        eng2 = SIGINTEngine(EventBus(), _rng(99))
        eng2.set_state(state)
        assert len(eng2._collectors) == 2

    def test_rng_state_preserved(self):
        eng = SIGINTEngine(EventBus(), _rng(42))
        # Consume some RNG
        collector = _make_collector(sensitivity=-110.0)
        emitter = _make_emitter(power=80.0, pos=Position(5000.0, 0.0, 0.0))
        eng.attempt_intercept(collector, emitter)
        state = eng.get_state()

        eng2 = SIGINTEngine(EventBus(), _rng(99))
        eng2.set_state(state)
        # Should produce same sequence going forward
        r1 = float(eng._rng.random())
        r2 = float(eng2._rng.random())
        assert r1 == r2
