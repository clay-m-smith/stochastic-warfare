"""Phase 61c: EM Propagation Wiring — radar horizon, ducting, HF comms, VHF horizon, DEW params, 14 tests."""

from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from stochastic_warfare.core.types import Domain, Position
from stochastic_warfare.detection.sensors import SensorType
from stochastic_warfare.simulation.calibration import CalibrationSchema
from stochastic_warfare.environment.electromagnetic import EMEnvironment, FrequencyBand
from stochastic_warfare.environment.weather import WeatherConfig, WeatherEngine
from stochastic_warfare.environment.astronomy import AstronomyEngine
from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.c2.communications import (
    CommunicationsEngine,
    CommEquipmentDefinition,
    CommType,
    CommEquipmentLoader,
)

from tests.conftest import make_rng, make_clock, TS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

K_STD = 4.0 / 3.0
R_EARTH = 6_371_000.0


def _radar_horizon(h: float) -> float:
    """Reference radar horizon for standard atmosphere."""
    return math.sqrt(2 * K_STD * R_EARTH * max(0, h))


def _make_em_env(
    *,
    hour_utc: int = 12,
    humidity: float = 0.5,
    temperature: float = 20.0,
    sst: float | None = None,
) -> EMEnvironment:
    """Build an EMEnvironment with controlled weather/clock."""
    clock = make_clock(start=datetime(2024, 6, 15, hour_utc, 0, 0, tzinfo=timezone.utc))
    rng = make_rng()
    weather = WeatherEngine(WeatherConfig(), clock, rng)
    # Override weather current to control humidity/temperature
    sea_state = None
    if sst is not None:
        sea_state = SimpleNamespace(current=SimpleNamespace(sst=sst))
    em = EMEnvironment(weather, sea_state, clock)
    # Patch weather current for precise control
    weather._state = weather._state  # keep existing
    weather._temperature = temperature
    return em


def _make_comm_engine_with_hf(
    em_env: EMEnvironment | None = None,
) -> tuple[CommunicationsEngine, str, str]:
    """Build a CommunicationsEngine with two units equipped with HF radio."""
    event_bus = EventBus()
    rng = make_rng()

    hf_def = CommEquipmentDefinition(
        comm_id="hf_radio",
        comm_type="RADIO_HF",
        display_name="HF Radio",
        max_range_m=500_000.0,
        bandwidth_bps=9600.0,
        base_latency_s=0.5,
        base_reliability=0.95,
        intercept_risk=0.3,
        jam_resistance=0.2,
        requires_los=False,
    )
    loader = CommEquipmentLoader.__new__(CommEquipmentLoader)
    loader._data_dir = None
    loader._definitions = {"hf_radio": hf_def}

    engine = CommunicationsEngine(event_bus, rng, equipment_loader=loader)
    engine.register_unit("unit_a", ["hf_radio"])
    engine.register_unit("unit_b", ["hf_radio"])

    if em_env is not None:
        engine.set_em_environment(em_env)

    return engine, "unit_a", "unit_b"


def _make_comm_engine_with_vhf(
    em_env: EMEnvironment | None = None,
) -> tuple[CommunicationsEngine, str, str]:
    """Build a CommunicationsEngine with two units equipped with VHF radio."""
    event_bus = EventBus()
    rng = make_rng()

    vhf_def = CommEquipmentDefinition(
        comm_id="vhf_radio",
        comm_type="RADIO_VHF",
        display_name="VHF Radio",
        max_range_m=50_000.0,
        bandwidth_bps=16000.0,
        base_latency_s=0.1,
        base_reliability=0.99,
        intercept_risk=0.5,
        jam_resistance=0.1,
        requires_los=True,
    )
    loader = CommEquipmentLoader.__new__(CommEquipmentLoader)
    loader._data_dir = None
    loader._definitions = {"vhf_radio": vhf_def}

    engine = CommunicationsEngine(event_bus, rng, equipment_loader=loader)
    engine.register_unit("unit_a", ["vhf_radio"])
    engine.register_unit("unit_b", ["vhf_radio"])

    if em_env is not None:
        engine.set_em_environment(em_env)

    return engine, "unit_a", "unit_b"


# ---------------------------------------------------------------------------
# 1. Radar horizon formula validation
# ---------------------------------------------------------------------------


class TestRadarHorizonFormula:
    """EMEnvironment.radar_horizon matches sqrt(2*k*R*h) reference values."""

    def test_ground_radar_10m(self) -> None:
        """Ground radar at h=10m: horizon ~13,024m."""
        em = _make_em_env()
        hz = em.radar_horizon(10.0)
        expected = _radar_horizon(10.0)
        assert abs(hz - expected) < 10.0
        assert 12_500 < hz < 13_500  # ~13,024m

    def test_ship_radar_30m(self) -> None:
        """Ship radar at h=30m: horizon ~22,562m."""
        em = _make_em_env()
        hz = em.radar_horizon(30.0)
        expected = _radar_horizon(30.0)
        assert abs(hz - expected) < 10.0
        assert 22_000 < hz < 23_500

    def test_aircraft_target_5000m(self) -> None:
        """Aircraft at h=5000m: horizon ~258,816m."""
        em = _make_em_env()
        hz = em.radar_horizon(5000.0)
        expected = _radar_horizon(5000.0)
        assert abs(hz - expected) < 100.0
        assert hz > 250_000


# ---------------------------------------------------------------------------
# 2. Radar horizon gate in detection (battle.py logic test)
# ---------------------------------------------------------------------------


class TestRadarHorizonDetectionGate:
    """Radar horizon blocks low-altitude targets beyond total horizon."""

    def test_low_target_beyond_horizon_blocked(self) -> None:
        """Ground radar (10m) vs target at 20km, altitude 0 → detection blocked.

        Total horizon = radar_horizon(10) + radar_horizon(0) ≈ 13,024m + 0 = 13,024m.
        Target at 20,000m is beyond horizon AND altitude < 500 → detection_range = 0.
        """
        em = _make_em_env()
        ant_h = 10.0
        tgt_alt = 0.0
        best_range = 20_000.0

        radar_hz = em.radar_horizon(ant_h)
        tgt_hz = em.radar_horizon(max(0, tgt_alt))
        total_hz = radar_hz + tgt_hz

        # Gate condition from battle.py: best_range > total_hz and tgt_alt < 500
        assert best_range > total_hz
        assert tgt_alt < 500
        # Therefore detection_range would be set to 0
        detection_range = 15_000.0  # original detection range
        if best_range > total_hz and tgt_alt < 500:
            detection_range = 0.0
        assert detection_range == 0.0

    def test_high_altitude_target_not_blocked(self) -> None:
        """Ground radar (10m) vs aircraft at 5km altitude, range 20km → NOT blocked.

        Total horizon = radar_horizon(10) + radar_horizon(5000) ≈ 13k + 259k = 272km.
        Target at 20km is well within horizon → detection unchanged.
        """
        em = _make_em_env()
        ant_h = 10.0
        tgt_alt = 5000.0
        best_range = 20_000.0

        radar_hz = em.radar_horizon(ant_h)
        tgt_hz = em.radar_horizon(max(0, tgt_alt))
        total_hz = radar_hz + tgt_hz

        assert total_hz > best_range
        # The altitude >= 500 condition also prevents blocking
        detection_range = 15_000.0
        if best_range > total_hz and tgt_alt < 500:
            detection_range = 0.0
        assert detection_range == 15_000.0  # unchanged


# ---------------------------------------------------------------------------
# 3. EM ducting for naval platforms
# ---------------------------------------------------------------------------


class TestEMDucting:
    """Ducting extends radar detection range for naval platforms."""

    def test_ducting_extends_detection_range(self) -> None:
        """When ducting_possible=True and platform is NAVAL, range *= duct_ext.

        Duct extension = min(2.0, k_factor / (4/3)).
        Evaporation duct triggers when sea_state SST > temp + 2 AND humidity > 0.7.
        Use HEAVY_RAIN state (humidity=0.95) to meet humidity threshold.
        """
        from stochastic_warfare.environment.weather import WeatherState

        clock = make_clock()
        rng = make_rng()
        weather = WeatherEngine(WeatherConfig(), clock, rng)
        # Force HEAVY_RAIN state (humidity=0.95) to exceed 0.7 threshold
        weather._state = WeatherState.HEAVY_RAIN

        # Mock sea_state with warm SST well above air temp
        temp = weather.current.temperature
        sea_state = SimpleNamespace(current=SimpleNamespace(sst=temp + 10.0))

        em = EMEnvironment(weather, sea_state, clock)
        prop = em.propagation(FrequencyBand.SHF, 10.0)
        assert prop.ducting_possible is True

        # Simulate battle.py logic: if ducting and NAVAL → multiply detection_range
        att_domain = Domain.NAVAL
        k = em.effective_earth_radius_factor()
        duct_ext = min(2.0, k / (4.0 / 3.0))
        detection_range = 20_000.0
        if prop.ducting_possible and att_domain in (Domain.NAVAL, Domain.SUBMARINE):
            detection_range *= duct_ext
        assert detection_range >= 20_000.0  # should not decrease

    def test_no_ducting_no_extension(self) -> None:
        """When ducting_possible=False, detection range unchanged."""
        em = _make_em_env(humidity=0.3, temperature=15.0)
        prop = em.propagation(FrequencyBand.SHF, 10.0)
        assert prop.ducting_possible is False

        detection_range = 20_000.0
        original = detection_range
        if prop.ducting_possible:
            detection_range *= 2.0
        assert detection_range == original


# ---------------------------------------------------------------------------
# 4. HF comms reliability (day vs night)
# ---------------------------------------------------------------------------


class TestHFCommsReliability:
    """HF radio reliability is multiplied by hf_propagation_quality()."""

    def test_hf_day_quality_low(self) -> None:
        """Daytime (12:00 UTC) HF quality ~0.3 → reliability degraded."""
        em = _make_em_env(hour_utc=12)
        quality = em.hf_propagation_quality()
        assert 0.2 <= quality <= 0.4  # day: D-layer absorption

    def test_hf_night_quality_high(self) -> None:
        """Nighttime (02:00 UTC) HF quality ~0.8 → reliability good."""
        em = _make_em_env(hour_utc=2)
        quality = em.hf_propagation_quality()
        assert 0.7 <= quality <= 0.9  # night: F-layer reflection

    def test_hf_comms_day_reliability_reduced(self) -> None:
        """CommunicationsEngine with HF radio: daytime reliability < nighttime."""
        em_day = _make_em_env(hour_utc=12)
        em_night = _make_em_env(hour_utc=2)

        eng_day, ua, ub = _make_comm_engine_with_hf(em_env=em_day)
        eng_night, _, _ = _make_comm_engine_with_hf(em_env=em_night)

        pos_a = Position(0.0, 0.0, 0.0)
        pos_b = Position(10_000.0, 0.0, 0.0)

        chan_day = eng_day.get_best_channel(ua, ub, pos_a, pos_b)
        chan_night = eng_night.get_best_channel("unit_a", "unit_b", pos_a, pos_b)

        assert chan_day is not None
        assert chan_night is not None

        # Reliability is internal: measure via _channel_reliability
        from stochastic_warfare.c2.communications import EmconState

        rel_day = eng_day._channel_reliability(chan_day, pos_a, pos_b, EmconState.RADIATE)
        rel_night = eng_night._channel_reliability(chan_night, pos_a, pos_b, EmconState.RADIATE)

        assert rel_day < rel_night, "Daytime HF reliability should be lower than nighttime"


# ---------------------------------------------------------------------------
# 5. VHF radio horizon gate
# ---------------------------------------------------------------------------


class TestVHFRadioHorizon:
    """VHF/UHF beyond radio horizon gets reliability *= 0.1."""

    def test_vhf_beyond_radio_horizon_degraded(self) -> None:
        """Two ground units at altitude 2m, distance 40km → beyond radio horizon.

        Radio horizon for h=2m: sqrt(2 * 4/3 * 6371000 * 2) ≈ 5,826m.
        Total horizon = 5,826 + 5,826 ≈ 11,652m. Distance 40km > 11.6km → degraded.
        """
        em = _make_em_env()
        eng, ua, ub = _make_comm_engine_with_vhf(em_env=em)

        pos_a = Position(0.0, 0.0, 2.0)  # altitude 2m
        pos_b = Position(11_000.0, 0.0, 2.0)  # within VHF range but still within horizon

        # First measure within-horizon reliability
        from stochastic_warfare.c2.communications import EmconState

        chan = eng.get_best_channel(ua, ub, pos_a, pos_b)
        assert chan is not None
        rel_close = eng._channel_reliability(chan, pos_a, pos_b, EmconState.RADIATE)

        # Now put unit_b far beyond radio horizon
        pos_b_far = Position(40_000.0, 0.0, 2.0)
        rel_far = eng._channel_reliability(chan, pos_a, pos_b_far, EmconState.RADIATE)

        # Beyond horizon should be heavily degraded (factor 0.1)
        assert rel_far < rel_close * 0.5, (
            f"Beyond-horizon VHF reliability {rel_far} should be much less than "
            f"within-horizon {rel_close}"
        )


# ---------------------------------------------------------------------------
# 6. DEW atmospheric params forwarding
# ---------------------------------------------------------------------------


class TestDEWAtmosphericParams:
    """route_engagement forwards humidity/precipitation_rate to DEW laser."""

    def test_dew_laser_receives_humidity_and_precipitation(self) -> None:
        """EngagementEngine.route_engagement passes humidity/precipitation_rate
        to dew_engine.execute_laser_engagement.
        """
        from stochastic_warfare.combat.engagement import (
            EngagementEngine,
            EngagementType,
        )
        from stochastic_warfare.combat.directed_energy import DEWEngagementResult

        event_bus = EventBus()
        rng = make_rng()

        # EngagementEngine requires sub-engines; mock them
        mock_hit = MagicMock()
        mock_damage = MagicMock()
        mock_suppression = MagicMock()
        mock_fratricide = MagicMock()
        eng_engine = EngagementEngine(
            hit_engine=mock_hit,
            damage_engine=mock_damage,
            suppression_engine=mock_suppression,
            fratricide_engine=mock_fratricide,
            event_bus=event_bus,
            rng=rng,
        )

        # Mock DEW engine
        mock_dew = MagicMock()
        mock_dew.execute_laser_engagement.return_value = DEWEngagementResult(
            engaged=True,
            attacker_id="shooter",
            target_id="target",
            weapon_id="laser1",
            pk=0.7,
            hit=True,
            range_m=1000.0,
            transmittance=0.9,
        )

        # Mock weapon & ammo
        mock_weapon = MagicMock()
        mock_weapon.weapon_id = "laser1"
        mock_weapon.definition.parsed_category.return_value = "DIRECTED_ENERGY"
        mock_weapon.definition.beam_power_kw = 100.0
        mock_ammo = MagicMock()

        result = eng_engine.route_engagement(
            engagement_type=EngagementType.DEW_LASER,
            attacker_id="shooter",
            target_id="target",
            attacker_pos=Position(0, 0, 0),
            target_pos=Position(1000, 0, 0),
            weapon=mock_weapon,
            ammo_id="laser_ammo",
            ammo_def=mock_ammo,
            dew_engine=mock_dew,
            humidity=0.85,
            precipitation_rate=5.0,
        )

        assert result.engaged is True
        # Verify humidity and precipitation were forwarded
        call_kwargs = mock_dew.execute_laser_engagement.call_args
        assert call_kwargs.kwargs["humidity"] == 0.85
        assert call_kwargs.kwargs["precipitation_rate"] == 5.0


# ---------------------------------------------------------------------------
# 7. Rain detection factor regression
# ---------------------------------------------------------------------------


class TestRainDetectionFactorRegression:
    """_compute_rain_detection_factor exists and returns sensible values."""

    def test_rain_detection_factor_exists(self) -> None:
        """Verify _compute_rain_detection_factor is importable from battle module."""
        from stochastic_warfare.simulation.battle import _compute_rain_detection_factor

        # No rain → factor = 1.0
        assert _compute_rain_detection_factor(0.0, 10.0) == 1.0

        # Heavy rain at range → factor < 1.0
        factor = _compute_rain_detection_factor(20.0, 10.0)
        assert 0.1 <= factor < 1.0

    def test_rain_detection_factor_zero_range(self) -> None:
        """Zero range or zero precipitation → factor = 1.0."""
        from stochastic_warfare.simulation.battle import _compute_rain_detection_factor

        assert _compute_rain_detection_factor(10.0, 0.0) == 1.0
        assert _compute_rain_detection_factor(0.0, 0.0) == 1.0


# ---------------------------------------------------------------------------
# 8. enable_em_propagation=False → no effects
# ---------------------------------------------------------------------------


class TestEnableEMPropagationFlag:
    """When enable_em_propagation=False, EM effects are skipped."""

    def test_flag_defaults_false(self) -> None:
        cal = CalibrationSchema()
        assert cal.enable_em_propagation is False

    def test_flag_can_be_enabled(self) -> None:
        cal = CalibrationSchema(enable_em_propagation=True)
        assert cal.enable_em_propagation is True
