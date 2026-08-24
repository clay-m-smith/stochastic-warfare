"""Phase 16a tests — Spectrum Manager, Emitter Registry, EW Events.

Tests frequency allocation, conflict detection, bandwidth overlap,
emitter registration/lifecycle, and event bus integration.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.environment.electromagnetic import FrequencyBand
from stochastic_warfare.ew.emitters import (
    Emitter,
    EmitterRegistry,
    EmitterType,
    WaveformType,
)
from stochastic_warfare.ew.events import (
    EmitterDetectedEvent,
    JammingActivatedEvent,
    SIGINTReportEvent,
)
from stochastic_warfare.ew.spectrum import FrequencyAllocation, SpectrumManager

TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
POS = Position(0.0, 0.0, 0.0)
POS2 = Position(1000.0, 0.0, 0.0)


# =========================================================================
# Spectrum Allocation
# =========================================================================


class TestSpectrumAllocation:
    """Allocation, deallocation, and query by band/range."""

    def test_allocate_and_query_by_band(self):
        sm = SpectrumManager()
        a = FrequencyAllocation(
            emitter_id="r1", center_frequency_ghz=10.0,
            bandwidth_ghz=0.1, band=FrequencyBand.SHF,
        )
        sm.allocate(a)
        results = sm.get_allocations_in_band(FrequencyBand.SHF)
        assert len(results) == 1
        assert results[0].emitter_id == "r1"

    def test_deallocate_removes(self):
        sm = SpectrumManager()
        a = FrequencyAllocation(
            emitter_id="r1", center_frequency_ghz=10.0,
            bandwidth_ghz=0.1, band=FrequencyBand.SHF,
        )
        sm.allocate(a)
        sm.deallocate("r1")
        assert sm.get_allocations_in_band(FrequencyBand.SHF) == []

    def test_query_by_range(self):
        sm = SpectrumManager()
        sm.allocate(FrequencyAllocation(
            emitter_id="r1", center_frequency_ghz=10.0,
            bandwidth_ghz=0.1, band=FrequencyBand.SHF,
        ))
        sm.allocate(FrequencyAllocation(
            emitter_id="r2", center_frequency_ghz=3.5,
            bandwidth_ghz=0.2, band=FrequencyBand.SHF,
        ))
        # Query 9-11 GHz should only find r1
        results = sm.get_allocations_in_range(9.0, 11.0)
        assert len(results) == 1
        assert results[0].emitter_id == "r1"

    def test_query_by_band_filters_other_bands(self):
        sm = SpectrumManager()
        sm.allocate(FrequencyAllocation(
            emitter_id="hf1", center_frequency_ghz=0.01,
            bandwidth_ghz=0.001, band=FrequencyBand.HF,
        ))
        sm.allocate(FrequencyAllocation(
            emitter_id="shf1", center_frequency_ghz=10.0,
            bandwidth_ghz=0.1, band=FrequencyBand.SHF,
        ))
        assert len(sm.get_allocations_in_band(FrequencyBand.HF)) == 1
        assert len(sm.get_allocations_in_band(FrequencyBand.SHF)) == 1
        assert len(sm.get_allocations_in_band(FrequencyBand.EHF)) == 0

    def test_conflict_detection(self):
        sm = SpectrumManager()
        sm.allocate(FrequencyAllocation(
            emitter_id="r1", center_frequency_ghz=10.0,
            bandwidth_ghz=0.2, band=FrequencyBand.SHF,
        ))
        # Overlapping allocation
        new_alloc = FrequencyAllocation(
            emitter_id="r2", center_frequency_ghz=10.05,
            bandwidth_ghz=0.2, band=FrequencyBand.SHF,
        )
        conflicts = sm.check_conflict(new_alloc)
        assert len(conflicts) == 1
        assert conflicts[0].emitter_id == "r1"


# =========================================================================
# Bandwidth Overlap
# =========================================================================


class TestBandwidthOverlap:
    """Fractional bandwidth overlap computation."""

    def test_full_overlap(self):
        # Same frequency & bandwidth → 100%
        result = SpectrumManager.bandwidth_overlap(10.0, 0.1, 10.0, 0.1)
        assert result == pytest.approx(1.0)

    def test_partial_overlap(self):
        # 50% overlap
        result = SpectrumManager.bandwidth_overlap(10.0, 0.2, 10.1, 0.2)
        assert 0.0 < result < 1.0

    def test_no_overlap(self):
        # Completely separated
        result = SpectrumManager.bandwidth_overlap(10.0, 0.1, 20.0, 0.1)
        assert result == 0.0


# =========================================================================
# Emitter Registry
# =========================================================================


def _make_emitter(eid: str = "e1", unit_id: str = "u1",
                  freq: float = 10.0, active: bool = True,
                  etype: EmitterType = EmitterType.RADAR,
                  side: str = "blue") -> Emitter:
    return Emitter(
        emitter_id=eid, unit_id=unit_id, emitter_type=etype,
        position=POS, frequency_ghz=freq, bandwidth_ghz=0.1,
        power_dbm=60.0, antenna_gain_dbi=30.0,
        waveform=WaveformType.PULSED, active=active, side=side,
    )


class TestEmitterRegistry:
    """Registration, lifecycle, and queries."""

    def test_register_and_query(self):
        reg = EmitterRegistry()
        reg.register_emitter(_make_emitter("e1"))
        assert len(reg.get_active_emitters()) == 1

    def test_deregister(self):
        reg = EmitterRegistry()
        reg.register_emitter(_make_emitter("e1"))
        reg.deregister_emitter("e1")
        assert len(reg.get_active_emitters()) == 0

    def test_activate_deactivate(self):
        reg = EmitterRegistry()
        reg.register_emitter(_make_emitter("e1", active=False))
        assert len(reg.get_active_emitters()) == 0
        reg.activate("e1")
        assert len(reg.get_active_emitters()) == 1
        reg.deactivate("e1")
        assert len(reg.get_active_emitters()) == 0

    def test_position_update(self):
        reg = EmitterRegistry()
        reg.register_emitter(_make_emitter("e1"))
        reg.update_position("e1", POS2)
        e = reg.get_emitter("e1")
        assert e is not None
        assert e.position == POS2

    def test_query_by_type(self):
        reg = EmitterRegistry()
        reg.register_emitter(_make_emitter("e1", etype=EmitterType.RADAR))
        reg.register_emitter(_make_emitter("e2", etype=EmitterType.RADIO))
        results = reg.get_active_emitters(emitter_type=EmitterType.RADAR)
        assert len(results) == 1
        assert results[0].emitter_id == "e1"

    def test_query_by_freq_range(self):
        reg = EmitterRegistry()
        reg.register_emitter(_make_emitter("e1", freq=10.0))
        reg.register_emitter(_make_emitter("e2", freq=3.0))
        results = reg.get_active_emitters(freq_range=(9.0, 11.0))
        assert len(results) == 1
        assert results[0].emitter_id == "e1"

    def test_query_by_side(self):
        reg = EmitterRegistry()
        reg.register_emitter(_make_emitter("e1", side="blue"))
        reg.register_emitter(_make_emitter("e2", side="red"))
        results = reg.get_active_emitters(side="red")
        assert len(results) == 1
        assert results[0].emitter_id == "e2"


# =========================================================================
# State Persistence
# =========================================================================


class TestEmitterRegistryState:
    """get_state / set_state round-trip."""

    def test_emitter_state_roundtrip(self):
        e = _make_emitter("e1")
        state = e.get_state()
        e2 = Emitter.from_state(state)
        assert e2.emitter_id == e.emitter_id
        assert e2.frequency_ghz == e.frequency_ghz
        assert e2.position == e.position

    def test_registry_state_roundtrip(self):
        reg = EmitterRegistry()
        reg.register_emitter(_make_emitter("e1"))
        reg.register_emitter(_make_emitter("e2", freq=5.0))
        state = reg.get_state()

        reg2 = EmitterRegistry()
        reg2.set_state(state)
        assert len(reg2.get_active_emitters()) == 2


class TestSpectrumState:
    """get_state / set_state round-trip for spectrum manager."""

    def test_spectrum_state_roundtrip(self):
        sm = SpectrumManager()
        sm.allocate(FrequencyAllocation(
            emitter_id="r1", center_frequency_ghz=10.0,
            bandwidth_ghz=0.1, band=FrequencyBand.SHF,
        ))
        state = sm.get_state()

        sm2 = SpectrumManager()
        sm2.set_state(state)
        assert len(sm2.get_allocations_in_band(FrequencyBand.SHF)) == 1


# =========================================================================
# Events
# =========================================================================


class TestEWEvents:
    """EventBus integration for EW events."""

    def test_jamming_event_published(self):
        bus = EventBus()
        received = []
        bus.subscribe(JammingActivatedEvent, received.append)
        event = JammingActivatedEvent(
            timestamp=TS, source=ModuleId.EW,
            jammer_id="j1", target_area_center=POS,
            radius_m=5000.0, jam_type=0,
        )
        bus.publish(event)
        assert len(received) == 1
        assert received[0].jammer_id == "j1"

    def test_emitter_detected_event(self):
        bus = EventBus()
        received = []
        bus.subscribe(EmitterDetectedEvent, received.append)
        event = EmitterDetectedEvent(
            timestamp=TS, source=ModuleId.EW,
            detector_id="s1", emitter_id="e1",
            estimated_position=POS, uncertainty_m=500.0,
            freq_ghz=10.0, power_dbm=60.0,
        )
        bus.publish(event)
        assert len(received) == 1
        assert received[0].detector_id == "s1"

    def test_sigint_report_event(self):
        bus = EventBus()
        received = []
        bus.subscribe(SIGINTReportEvent, received.append)
        event = SIGINTReportEvent(
            timestamp=TS, source=ModuleId.EW,
            collector_id="c1", emitter_id="e1",
            intel_type=0, confidence=0.8,
        )
        bus.publish(event)
        assert len(received) == 1


# =========================================================================
# ModuleId.EW exists
# =========================================================================


class TestModuleIdEW:
    def test_ew_module_id_exists(self):
        assert ModuleId.EW == "ew"
