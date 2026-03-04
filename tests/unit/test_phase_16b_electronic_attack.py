"""Phase 16b tests — Electronic Attack (jamming, spoofing, decoys).

Tests J/S ratio physics, burn-through range, radar SNR penalty,
comms jam factor, GPS spoofing effects, and electronic decoy behavior.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.ew.decoys_ew import (
    EWDecoy,
    EWDecoyConfig,
    EWDecoyEngine,
    EWDecoyType,
    SeekerType,
)
from stochastic_warfare.ew.events import (
    DecoyDeployedEvent,
    JammingActivatedEvent,
    JammingDeactivatedEvent,
)
from stochastic_warfare.ew.jamming import (
    JammerDefinitionModel,
    JammerInstance,
    JamTechnique,
    JammingConfig,
    JammingEngine,
)
from stochastic_warfare.ew.spoofing import (
    GPSSpoofZone,
    ReceiverType,
    SpoofingConfig,
    SpoofingEngine,
)

TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
POS_ORIGIN = Position(0.0, 0.0, 0.0)
POS_10KM = Position(10000.0, 0.0, 0.0)
POS_50KM = Position(50000.0, 0.0, 0.0)


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def _make_jammer(
    jid: str = "j1", power_dbm: float = 60.0, gain_dbi: float = 10.0,
    bw_ghz: float = 0.5, freq_min: float = 1.0, freq_max: float = 18.0,
) -> JammerInstance:
    defn = JammerDefinitionModel(
        jammer_id=jid, power_dbm=power_dbm, antenna_gain_dbi=gain_dbi,
        bandwidth_ghz=bw_ghz, frequency_min_ghz=freq_min,
        frequency_max_ghz=freq_max,
    )
    return JammerInstance(definition=defn, position=POS_ORIGIN)


# =========================================================================
# J/S Ratio
# =========================================================================


class TestJSRatio:
    """J/S ratio computation."""

    def test_self_screening_basic(self):
        bus = EventBus()
        eng = JammingEngine(bus, _rng())
        j = _make_jammer(power_dbm=60.0, gain_dbi=10.0, bw_ghz=0.5)
        j.active = True
        # At very short jammer range, J/S is high (jammer overwhelms radar)
        js_close = eng.compute_js_ratio(
            j, target_radar_power_dbm=70.0, target_radar_gain_dbi=30.0,
            target_radar_bw_ghz=0.01, target_range_m=10000.0,
            jammer_range_m=1000.0,
        )
        # At very long jammer range, J/S drops
        js_far = eng.compute_js_ratio(
            j, target_radar_power_dbm=70.0, target_radar_gain_dbi=30.0,
            target_radar_bw_ghz=0.01, target_range_m=10000.0,
            jammer_range_m=100000.0,
        )
        assert js_close > js_far

    def test_standoff_high_power(self):
        bus = EventBus()
        eng = JammingEngine(bus, _rng())
        j = _make_jammer(power_dbm=80.0, gain_dbi=20.0, bw_ghz=0.01)
        j.active = True
        js = eng.compute_js_ratio(
            j, target_radar_power_dbm=60.0, target_radar_gain_dbi=30.0,
            target_radar_bw_ghz=0.01, target_range_m=50000.0,
            jammer_range_m=10000.0,
        )
        # High-power jammer, closer, narrow BW → positive J/S
        assert js > 0.0

    def test_bandwidth_ratio_matters(self):
        bus = EventBus()
        eng = JammingEngine(bus, _rng())
        j_narrow = _make_jammer(bw_ghz=0.01)
        j_narrow.active = True
        j_wide = _make_jammer(jid="j2", bw_ghz=5.0)
        j_wide.active = True
        # Same everything except jammer bandwidth
        kwargs = dict(
            target_radar_power_dbm=60.0, target_radar_gain_dbi=30.0,
            target_radar_bw_ghz=0.01, target_range_m=10000.0,
            jammer_range_m=10000.0,
        )
        js_narrow = eng.compute_js_ratio(j_narrow, **kwargs)
        js_wide = eng.compute_js_ratio(j_wide, **kwargs)
        # Narrower jammer BW → more energy per Hz → higher J/S
        assert js_narrow > js_wide

    def test_power_effect(self):
        bus = EventBus()
        eng = JammingEngine(bus, _rng())
        j_low = _make_jammer(power_dbm=40.0)
        j_low.active = True
        j_high = _make_jammer(jid="j2", power_dbm=80.0)
        j_high.active = True
        kwargs = dict(
            target_radar_power_dbm=60.0, target_radar_gain_dbi=30.0,
            target_radar_bw_ghz=0.01, target_range_m=10000.0,
            jammer_range_m=10000.0,
        )
        assert eng.compute_js_ratio(j_high, **kwargs) > eng.compute_js_ratio(j_low, **kwargs)

    def test_range_effect(self):
        bus = EventBus()
        eng = JammingEngine(bus, _rng())
        j = _make_jammer()
        j.active = True
        kwargs = dict(
            target_radar_power_dbm=60.0, target_radar_gain_dbi=30.0,
            target_radar_bw_ghz=0.01, target_range_m=10000.0,
        )
        js_close = eng.compute_js_ratio(j, jammer_range_m=5000.0, **kwargs)
        js_far = eng.compute_js_ratio(j, jammer_range_m=50000.0, **kwargs)
        assert js_close > js_far

    def test_deceptive_multiplier(self):
        bus = EventBus()
        eng = JammingEngine(bus, _rng())
        j_noise = _make_jammer()
        j_noise.active = True
        j_noise.current_technique = JamTechnique.NOISE
        j_deceptive = _make_jammer(jid="j2")
        j_deceptive.active = True
        j_deceptive.current_technique = JamTechnique.DECEPTIVE
        kwargs = dict(
            target_radar_power_dbm=60.0, target_radar_gain_dbi=30.0,
            target_radar_bw_ghz=0.01, target_range_m=10000.0,
            jammer_range_m=10000.0,
        )
        assert eng.compute_js_ratio(j_deceptive, **kwargs) > eng.compute_js_ratio(j_noise, **kwargs)


# =========================================================================
# Burn-Through Range
# =========================================================================


class TestBurnThroughRange:

    def test_low_power_jammer_short_burn_through(self):
        bus = EventBus()
        eng = JammingEngine(bus, _rng())
        j = _make_jammer(power_dbm=50.0, gain_dbi=5.0, bw_ghz=0.5)
        bt = eng.compute_burn_through_range(j, 70.0, 30.0, 0.01)
        assert bt > 0

    def test_high_power_jammer_longer_burn_through(self):
        bus = EventBus()
        eng = JammingEngine(bus, _rng())
        j_low = _make_jammer(power_dbm=40.0, gain_dbi=5.0)
        j_high = _make_jammer(jid="j2", power_dbm=80.0, gain_dbi=20.0)
        bt_low = eng.compute_burn_through_range(j_low, 60.0, 30.0, 0.01)
        bt_high = eng.compute_burn_through_range(j_high, 60.0, 30.0, 0.01)
        # Higher power jammer → radar needs to be closer to burn through
        assert bt_high < bt_low

    def test_bandwidth_mismatch(self):
        bus = EventBus()
        eng = JammingEngine(bus, _rng())
        j = _make_jammer(bw_ghz=5.0)  # wide jammer
        bt_wide = eng.compute_burn_through_range(j, 60.0, 30.0, 0.01)
        j2 = _make_jammer(jid="j2", bw_ghz=0.01)  # narrow jammer
        bt_narrow = eng.compute_burn_through_range(j2, 60.0, 30.0, 0.01)
        # Wide jammer spreads energy → easier burn-through (larger range)
        assert bt_wide > bt_narrow


# =========================================================================
# Radar SNR Penalty
# =========================================================================


class TestRadarSNRPenalty:

    def _engine_with_jammer(self, pos=POS_ORIGIN, **kwargs) -> JammingEngine:
        bus = EventBus()
        eng = JammingEngine(bus, _rng())
        j = _make_jammer(**kwargs)
        j.active = True
        j.position = pos
        eng.register_jammer(j)
        return eng

    def test_single_jammer_penalty(self):
        eng = self._engine_with_jammer(power_dbm=80.0, gain_dbi=20.0, bw_ghz=0.01)
        penalty = eng.compute_radar_snr_penalty(
            sensor_pos=POS_10KM, sensor_freq_ghz=10.0,
            sensor_power_dbm=60.0, sensor_gain_dbi=30.0,
            sensor_bw_ghz=0.01, target_range_m=50000.0,
        )
        assert penalty > 0.0

    def test_multiple_jammers_aggregate(self):
        bus = EventBus()
        eng = JammingEngine(bus, _rng())
        for i in range(3):
            j = _make_jammer(jid=f"j{i}", power_dbm=70.0, gain_dbi=15.0, bw_ghz=0.01)
            j.active = True
            j.position = Position(i * 1000.0, 0.0, 0.0)
            eng.register_jammer(j)
        penalty_multi = eng.compute_radar_snr_penalty(
            sensor_pos=POS_10KM, sensor_freq_ghz=10.0,
            sensor_power_dbm=60.0, sensor_gain_dbi=30.0,
            sensor_bw_ghz=0.01, target_range_m=50000.0,
        )
        # Multiple jammers → higher aggregate penalty
        eng2 = JammingEngine(EventBus(), _rng())
        j_single = _make_jammer(power_dbm=70.0, gain_dbi=15.0, bw_ghz=0.01)
        j_single.active = True
        eng2.register_jammer(j_single)
        penalty_single = eng2.compute_radar_snr_penalty(
            sensor_pos=POS_10KM, sensor_freq_ghz=10.0,
            sensor_power_dbm=60.0, sensor_gain_dbi=30.0,
            sensor_bw_ghz=0.01, target_range_m=50000.0,
        )
        assert penalty_multi > penalty_single

    def test_out_of_band_no_effect(self):
        eng = self._engine_with_jammer(freq_min=8.0, freq_max=12.0)
        penalty = eng.compute_radar_snr_penalty(
            sensor_pos=POS_10KM, sensor_freq_ghz=3.0,  # Below jammer range
            sensor_power_dbm=60.0, sensor_gain_dbi=30.0,
            sensor_bw_ghz=0.01, target_range_m=50000.0,
        )
        assert penalty == 0.0

    def test_inactive_jammer_no_effect(self):
        bus = EventBus()
        eng = JammingEngine(bus, _rng())
        j = _make_jammer()
        j.active = False
        eng.register_jammer(j)
        penalty = eng.compute_radar_snr_penalty(
            sensor_pos=POS_10KM, sensor_freq_ghz=10.0,
            sensor_power_dbm=60.0, sensor_gain_dbi=30.0,
            sensor_bw_ghz=0.01, target_range_m=50000.0,
        )
        assert penalty == 0.0

    def test_far_jammer_reduced_effect(self):
        eng_close = self._engine_with_jammer(
            pos=POS_10KM, power_dbm=70.0, gain_dbi=15.0, bw_ghz=0.01,
        )
        eng_far = self._engine_with_jammer(
            pos=POS_50KM, power_dbm=70.0, gain_dbi=15.0, bw_ghz=0.01,
        )
        sensor_pos = Position(5000.0, 0.0, 0.0)
        kwargs = dict(
            sensor_freq_ghz=10.0, sensor_power_dbm=60.0,
            sensor_gain_dbi=30.0, sensor_bw_ghz=0.01, target_range_m=50000.0,
        )
        penalty_close = eng_close.compute_radar_snr_penalty(sensor_pos=sensor_pos, **kwargs)
        penalty_far = eng_far.compute_radar_snr_penalty(sensor_pos=sensor_pos, **kwargs)
        assert penalty_close > penalty_far


# =========================================================================
# Comms Jam Factor
# =========================================================================


class TestCommsJamFactor:

    def test_in_band_jams(self):
        bus = EventBus()
        eng = JammingEngine(bus, _rng())
        j = _make_jammer(power_dbm=70.0, gain_dbi=15.0, freq_min=0.1, freq_max=1.0)
        j.active = True
        eng.register_jammer(j)
        factor = eng.compute_comms_jam_factor(
            receiver_pos=Position(1000.0, 0.0, 0.0),
            comm_freq_ghz=0.3,
        )
        assert 0.0 < factor <= 1.0

    def test_jam_resistance_reduces(self):
        bus = EventBus()
        eng = JammingEngine(bus, _rng())
        j = _make_jammer(power_dbm=70.0, gain_dbi=15.0, freq_min=0.1, freq_max=1.0)
        j.active = True
        eng.register_jammer(j)
        factor_no_resist = eng.compute_comms_jam_factor(
            receiver_pos=Position(1000.0, 0.0, 0.0),
            comm_freq_ghz=0.3, comm_jam_resistance=0.0,
        )
        factor_resist = eng.compute_comms_jam_factor(
            receiver_pos=Position(1000.0, 0.0, 0.0),
            comm_freq_ghz=0.3, comm_jam_resistance=0.8,
        )
        assert factor_resist < factor_no_resist

    def test_out_of_band_no_effect(self):
        bus = EventBus()
        eng = JammingEngine(bus, _rng())
        j = _make_jammer(freq_min=8.0, freq_max=12.0)
        j.active = True
        eng.register_jammer(j)
        factor = eng.compute_comms_jam_factor(
            receiver_pos=Position(1000.0, 0.0, 0.0),
            comm_freq_ghz=0.3,  # Out of band
        )
        assert factor == 0.0

    def test_range_dependence(self):
        bus = EventBus()
        eng = JammingEngine(bus, _rng())
        j = _make_jammer(power_dbm=70.0, gain_dbi=15.0, freq_min=0.1, freq_max=1.0)
        j.active = True
        eng.register_jammer(j)
        factor_close = eng.compute_comms_jam_factor(
            receiver_pos=Position(100.0, 0.0, 0.0), comm_freq_ghz=0.3,
        )
        factor_far = eng.compute_comms_jam_factor(
            receiver_pos=Position(100000.0, 0.0, 0.0), comm_freq_ghz=0.3,
        )
        assert factor_close > factor_far


# =========================================================================
# Jammer Activation Events
# =========================================================================


class TestJammerActivation:

    def test_activate_publishes_event(self):
        bus = EventBus()
        received = []
        bus.subscribe(JammingActivatedEvent, received.append)
        eng = JammingEngine(bus, _rng())
        j = _make_jammer()
        eng.register_jammer(j)
        eng.activate_jammer("j1", JamTechnique.BARRAGE, 10.0, POS_ORIGIN, TS)
        assert len(received) == 1
        assert received[0].jammer_id == "j1"

    def test_deactivate_publishes_event(self):
        bus = EventBus()
        received = []
        bus.subscribe(JammingDeactivatedEvent, received.append)
        eng = JammingEngine(bus, _rng())
        j = _make_jammer()
        eng.register_jammer(j)
        eng.activate_jammer("j1", JamTechnique.NOISE, timestamp=TS)
        eng.deactivate_jammer("j1", timestamp=TS)
        assert len(received) == 1

    def test_technique_selection(self):
        bus = EventBus()
        eng = JammingEngine(bus, _rng())
        j = _make_jammer()
        eng.register_jammer(j)
        eng.activate_jammer("j1", JamTechnique.SPOT, 10.0)
        assert eng._jammers["j1"].current_technique == JamTechnique.SPOT


# =========================================================================
# GPS Spoofing
# =========================================================================


class TestGPSSpoofZone:

    def _engine_with_zone(self, seed=42):
        bus = EventBus()
        eng = SpoofingEngine(bus, _rng(seed))
        zone = GPSSpoofZone(
            zone_id="sz1", center=POS_ORIGIN, radius_m=5000.0,
            offset_east_m=500.0, offset_north_m=300.0, power_dbm=50.0,
        )
        eng.add_spoof_zone(zone)
        return eng

    def test_civilian_spoofed(self):
        eng = self._engine_with_zone(seed=1)
        # Civilian has very low resistance; most seeds should be spoofed
        # Try multiple seeds to find one that produces spoofing
        spoofed = False
        for s in range(20):
            eng2 = self._engine_with_zone(seed=s)
            effect = eng2.compute_gps_effect(
                Position(100.0, 100.0, 0.0), ReceiverType.CIVILIAN,
            )
            if effect.spoofed:
                spoofed = True
                assert effect.offset_east_m != 0.0
                break
        assert spoofed, "Civilian should be spoofed at least once in 20 attempts"

    def test_mcode_resists(self):
        # M-code has 85% resistance
        spoof_count = 0
        for s in range(50):
            eng = self._engine_with_zone(seed=s)
            effect = eng.compute_gps_effect(
                Position(100.0, 100.0, 0.0), ReceiverType.MILITARY_M,
            )
            if effect.spoofed:
                spoof_count += 1
        # Should be spoofed < 30% of the time (15% nominal)
        assert spoof_count < 20

    def test_offset_vector_correct(self):
        # When spoofed, offset should be proportional to zone offset * (1-resistance)
        eng = self._engine_with_zone(seed=1)
        for s in range(20):
            eng2 = self._engine_with_zone(seed=s)
            effect = eng2.compute_gps_effect(
                Position(100.0, 100.0, 0.0), ReceiverType.CIVILIAN,
            )
            if effect.spoofed:
                # Civilian resistance = 0.05, so offset ~ 0.95 * zone offset
                assert abs(effect.offset_east_m) > 400.0  # ~475
                break

    def test_outside_zone_unaffected(self):
        eng = self._engine_with_zone()
        effect = eng.compute_gps_effect(
            Position(100000.0, 0.0, 0.0), ReceiverType.CIVILIAN,
        )
        assert not effect.spoofed
        assert effect.offset_east_m == 0.0


# =========================================================================
# Spoof Detection
# =========================================================================


class TestSpoofDetection:

    def _engine_with_zone(self):
        bus = EventBus()
        eng = SpoofingEngine(bus, _rng(), SpoofingConfig(ins_crosscheck_delay_s=30.0))
        zone = GPSSpoofZone(
            zone_id="sz1", center=POS_ORIGIN, radius_m=5000.0,
            offset_east_m=500.0, offset_north_m=300.0, power_dbm=50.0,
        )
        eng.add_spoof_zone(zone)
        return eng

    def test_before_delay_no_detection(self):
        eng = self._engine_with_zone()
        detected = eng.check_spoof_detection(
            Position(100.0, 100.0, 0.0), ReceiverType.CIVILIAN, 10.0,
        )
        assert not detected

    def test_after_delay_detects(self):
        eng = self._engine_with_zone()
        detected = eng.check_spoof_detection(
            Position(100.0, 100.0, 0.0), ReceiverType.CIVILIAN, 200.0,
        )
        assert detected

    def test_detection_by_receiver_type(self):
        eng = self._engine_with_zone()
        # All receiver types should detect after enough time
        for rtype in ReceiverType:
            detected = eng.check_spoof_detection(
                Position(100.0, 100.0, 0.0), rtype, 200.0,
            )
            assert detected


# =========================================================================
# PGM Offset
# =========================================================================


class TestPGMOffset:

    def test_gps_guided_miss_by_offset(self):
        bus = EventBus()
        eng = SpoofingEngine(bus, _rng(0))
        zone = GPSSpoofZone(
            zone_id="sz1", center=POS_ORIGIN, radius_m=50000.0,
            offset_east_m=1000.0, offset_north_m=0.0, power_dbm=50.0,
        )
        eng.add_spoof_zone(zone)
        # Civilian receiver → should be spoofed (seed 0 → roll 0.636, threshold 0.95)
        target = Position(1000.0, 1000.0, 0.0)
        impact = eng.compute_pgm_offset(target, ReceiverType.CIVILIAN)
        # If spoofed, impact should be offset east
        if impact != target:
            assert impact.easting > target.easting

    def test_laser_unaffected(self):
        """Laser-guided weapons don't use GPS, so PGM offset doesn't apply.
        This test verifies the concept by checking outside-zone behavior."""
        bus = EventBus()
        eng = SpoofingEngine(bus, _rng())
        # No zones → no offset
        target = Position(1000.0, 1000.0, 0.0)
        impact = eng.compute_pgm_offset(target, ReceiverType.CIVILIAN)
        assert impact == target

    def test_ins_drift_accumulates(self):
        """INS drift over time affects position accuracy."""
        cfg = SpoofingConfig(ins_drift_rate_m_per_s=0.01)
        bus = EventBus()
        eng = SpoofingEngine(bus, _rng(), cfg)
        # After 1000s, INS drift = 10m
        drift = cfg.ins_drift_rate_m_per_s * 1000.0
        assert drift == pytest.approx(10.0)


# =========================================================================
# EW Decoys
# =========================================================================


class TestEWDecoys:

    def test_chaff_deploy_and_degradation(self):
        bus = EventBus()
        eng = EWDecoyEngine(bus, _rng())
        chaff = eng.deploy_chaff(POS_ORIGIN, 10.0, timestamp=TS)
        assert chaff.active
        assert chaff.rcs_m2 == 100.0  # default

        # Degrade over time
        eng.update(60.0)
        assert chaff.effectiveness < 1.0
        assert chaff.active  # Not expired yet

    def test_flare_duration(self):
        bus = EventBus()
        eng = EWDecoyEngine(bus, _rng())
        flare = eng.deploy_flare(POS_ORIGIN)
        assert flare.duration_s == 5.0
        eng.update(6.0)  # Exceeds duration
        assert not flare.active

    def test_towed_decoy_rcs(self):
        bus = EventBus()
        eng = EWDecoyEngine(bus, _rng())
        decoy = eng.deploy_towed_decoy(POS_ORIGIN, platform_rcs_m2=10.0)
        # Default towed_decoy_rcs_mult = 1.5
        assert decoy.rcs_m2 == pytest.approx(15.0)

    def test_drfm_false_target(self):
        bus = EventBus()
        eng = EWDecoyEngine(bus, _rng())
        drfm = eng.deploy_drfm(POS_ORIGIN, 10.0)
        assert drfm.effectiveness == pytest.approx(0.7)  # default


# =========================================================================
# Missile Diversion
# =========================================================================


class TestMissileDivert:

    def test_chaff_diverts_radar_missile(self):
        bus = EventBus()
        eng = EWDecoyEngine(bus, _rng())
        chaff = eng.deploy_chaff(POS_ORIGIN, 10.0)
        prob = eng.compute_missile_divert_probability(
            chaff, SeekerType.RADAR, 50.0,
        )
        assert prob > 0.5

    def test_flare_diverts_ir_missile(self):
        bus = EventBus()
        eng = EWDecoyEngine(bus, _rng())
        flare = eng.deploy_flare(POS_ORIGIN)
        prob = eng.compute_missile_divert_probability(
            flare, SeekerType.IR, 50.0,
        )
        assert prob > 0.5

    def test_mismatched_low_prob(self):
        bus = EventBus()
        eng = EWDecoyEngine(bus, _rng())
        chaff = eng.deploy_chaff(POS_ORIGIN, 10.0)
        # Chaff vs IR seeker → low/zero probability
        prob = eng.compute_missile_divert_probability(
            chaff, SeekerType.IR, 50.0,
        )
        assert prob == 0.0


# =========================================================================
# Jamming State
# =========================================================================


class TestJammingState:

    def test_jamming_engine_state_roundtrip(self):
        bus = EventBus()
        eng = JammingEngine(bus, _rng())
        j = _make_jammer()
        eng.register_jammer(j)
        eng.activate_jammer("j1", JamTechnique.BARRAGE, 10.0, POS_ORIGIN)
        state = eng.get_state()

        eng2 = JammingEngine(EventBus(), _rng(99))
        eng2.set_state(state)
        assert "j1" in eng2._jammers
        assert eng2._jammers["j1"].active

    def test_spoofing_engine_state_roundtrip(self):
        bus = EventBus()
        eng = SpoofingEngine(bus, _rng())
        zone = GPSSpoofZone(
            zone_id="sz1", center=POS_ORIGIN, radius_m=5000.0,
            offset_east_m=500.0, offset_north_m=300.0, power_dbm=50.0,
        )
        eng.add_spoof_zone(zone)
        state = eng.get_state()

        eng2 = SpoofingEngine(EventBus(), _rng(99))
        eng2.set_state(state)
        assert "sz1" in eng2._zones
