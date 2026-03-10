"""Phase 52: Environmental Continuity — night gradation, weather→ballistics,
terrain comms LOS, SIGINT fusion.

~32 tests across 4 substeps.
"""

from __future__ import annotations

import math
from types import SimpleNamespace
from typing import NamedTuple
from unittest.mock import MagicMock

import numpy as np
import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_rng(seed: int = 42) -> np.random.Generator:
    return np.random.default_rng(seed)


# ═══════════════════════════════════════════════════════════════════════════
# 52a — Night Gradation
# ═══════════════════════════════════════════════════════════════════════════


class _FakeIllum(NamedTuple):
    """Minimal illumination stand-in matching IlluminationLevel API."""
    is_day: bool
    twilight_stage: str | None


class TestNightGradation:
    """Verify continuous twilight modifiers replace binary day/night."""

    def test_day_modifier(self):
        from stochastic_warfare.simulation.battle import _compute_night_modifiers

        vis, therm = _compute_night_modifiers(_FakeIllum(is_day=True, twilight_stage=None))
        assert vis == 1.0
        assert therm == 1.0

    def test_civil_twilight(self):
        from stochastic_warfare.simulation.battle import _compute_night_modifiers

        vis, therm = _compute_night_modifiers(_FakeIllum(is_day=False, twilight_stage="civil"))
        assert vis == pytest.approx(0.8)
        assert therm == pytest.approx(0.8)  # max(0.8, 0.8)

    def test_nautical_twilight(self):
        from stochastic_warfare.simulation.battle import _compute_night_modifiers

        vis, therm = _compute_night_modifiers(_FakeIllum(is_day=False, twilight_stage="nautical"))
        assert vis == pytest.approx(0.5)
        assert therm == pytest.approx(0.8)  # floor

    def test_astronomical_twilight(self):
        from stochastic_warfare.simulation.battle import _compute_night_modifiers

        vis, therm = _compute_night_modifiers(_FakeIllum(is_day=False, twilight_stage="astronomical"))
        assert vis == pytest.approx(0.3)
        assert therm == pytest.approx(0.8)  # floor

    def test_full_night(self):
        from stochastic_warfare.simulation.battle import _compute_night_modifiers

        vis, therm = _compute_night_modifiers(_FakeIllum(is_day=False, twilight_stage=None))
        assert vis == pytest.approx(0.2)
        assert therm == pytest.approx(0.8)  # floor

    def test_thermal_at_full_night_uses_floor(self):
        from stochastic_warfare.simulation.battle import _compute_night_modifiers

        vis, therm = _compute_night_modifiers(
            _FakeIllum(is_day=False, twilight_stage=None), night_thermal_floor=0.8,
        )
        assert therm == pytest.approx(0.8)

    def test_thermal_floor_custom(self):
        from stochastic_warfare.simulation.battle import _compute_night_modifiers

        vis, therm = _compute_night_modifiers(
            _FakeIllum(is_day=False, twilight_stage="nautical"), night_thermal_floor=0.6,
        )
        # visual=0.5, thermal=max(0.6, 0.5)=0.6
        assert therm == pytest.approx(0.6)

    def test_civil_twilight_thermal_at_floor(self):
        from stochastic_warfare.simulation.battle import _compute_night_modifiers

        vis, therm = _compute_night_modifiers(
            _FakeIllum(is_day=False, twilight_stage="civil"), night_thermal_floor=0.8,
        )
        # visual=0.8, thermal=max(0.8, 0.8)=0.8
        assert therm == pytest.approx(0.8)


# ═══════════════════════════════════════════════════════════════════════════
# 52b — Weather Effects on Ballistics and Sensors
# ═══════════════════════════════════════════════════════════════════════════


class TestWeatherEffects:
    """Cross-wind penalty and rain radar attenuation."""

    def test_zero_wind_no_penalty(self):
        from stochastic_warfare.simulation.battle import _compute_crosswind_penalty

        assert _compute_crosswind_penalty(0.0, 0.0, 0.0, 0.0, 100.0, 0.0) == 1.0

    def test_strong_crosswind_penalty(self):
        from stochastic_warfare.simulation.battle import _compute_crosswind_penalty

        # 10 m/s pure crosswind (wind from east, engagement heading north)
        # heading = atan2(0, 100) = 0, crosswind = |10*cos(0) - 0*sin(0)| = 10
        p = _compute_crosswind_penalty(10.0, 0.0, 0.0, 0.0, 0.0, 100.0)
        assert p == pytest.approx(0.7)  # max penalty at 10 m/s

    def test_headwind_minimal_penalty(self):
        from stochastic_warfare.simulation.battle import _compute_crosswind_penalty

        # Wind purely along engagement axis (wind_n, heading north)
        # heading = atan2(0, 100) = 0, crosswind = |0*cos(0) - 10*sin(0)| = 0
        p = _compute_crosswind_penalty(0.0, 10.0, 0.0, 0.0, 0.0, 100.0)
        assert p == pytest.approx(1.0)

    def test_wind_from_weather_conditions(self):
        """Verify wind decomposition from meteorological convention."""
        # From-direction = 0 (from north) → wind blows south
        # wind_e = -speed * sin(0) = 0, wind_n = -speed * cos(0) = -speed
        speed = 10.0
        direction = 0.0  # from north
        wind_e = -speed * math.sin(direction)
        wind_n = -speed * math.cos(direction)
        assert wind_e == pytest.approx(0.0, abs=1e-10)
        assert wind_n == pytest.approx(-10.0)

    def test_zero_precipitation_no_attenuation(self):
        from stochastic_warfare.simulation.battle import _compute_rain_detection_factor

        assert _compute_rain_detection_factor(0.0, 20.0) == 1.0

    def test_heavy_rain_significant_attenuation(self):
        from stochastic_warfare.simulation.battle import _compute_rain_detection_factor

        # 15 mm/hr at 20 km: specific_atten = 0.01 * 15^1.28 ≈ 0.34 dB/km
        # total = 0.34 * 20 ≈ 6.8 dB, factor = 10^(-6.8/40) ≈ 0.67
        f = _compute_rain_detection_factor(15.0, 20.0)
        assert 0.5 < f < 0.8  # significant but not total

    def test_light_rain_small_attenuation(self):
        from stochastic_warfare.simulation.battle import _compute_rain_detection_factor

        f = _compute_rain_detection_factor(2.0, 10.0)
        assert 0.9 < f < 1.0  # small attenuation

    def test_rain_minimum_floor(self):
        from stochastic_warfare.simulation.battle import _compute_rain_detection_factor

        # Extreme rain + extreme range → should be clamped to 0.1
        f = _compute_rain_detection_factor(200.0, 100.0)
        assert f == pytest.approx(0.1)

    def test_crosswind_same_position_no_penalty(self):
        from stochastic_warfare.simulation.battle import _compute_crosswind_penalty

        # Attacker and target at same position → 1.0
        p = _compute_crosswind_penalty(10.0, 5.0, 50.0, 50.0, 50.0, 50.0)
        assert p == 1.0

    def test_custom_wind_scale(self):
        from stochastic_warfare.simulation.battle import _compute_crosswind_penalty

        # scale=0.01 → 10 m/s crosswind = 10% penalty (0.9)
        p = _compute_crosswind_penalty(10.0, 0.0, 0.0, 0.0, 0.0, 100.0, scale=0.01)
        assert p == pytest.approx(0.9)


# ═══════════════════════════════════════════════════════════════════════════
# 52c — Terrain-Based Comms LOS
# ═══════════════════════════════════════════════════════════════════════════


class TestCommsTerrainLOS:
    """Terrain LOS for communications with diffraction model."""

    def _make_engine(self, los_engine=None):
        from stochastic_warfare.c2.communications import (
            CommunicationsEngine,
            CommEquipmentLoader,
        )

        eb = EventBus()
        rng = _make_rng()
        return CommunicationsEngine(
            event_bus=eb, rng=rng,
            equipment_loader=CommEquipmentLoader(),
            los_engine=los_engine,
        )

    def _make_equip(self, comm_type: str = "RADIO_VHF", requires_los: bool = True):
        from stochastic_warfare.c2.communications import CommEquipmentDefinition

        return CommEquipmentDefinition(
            comm_id="test",
            comm_type=comm_type,
            display_name="Test",
            max_range_m=50000.0,
            bandwidth_bps=9600.0,
            base_latency_s=0.1,
            base_reliability=0.95,
            intercept_risk=0.3,
            jam_resistance=0.0,
            requires_los=requires_los,
        )

    def test_los_clear_factor_1(self):
        los = MagicMock()
        los.check_los.return_value = SimpleNamespace(visible=True, blocked_at=None, blocked_by=None, grazing_distance=10.0)
        engine = self._make_engine(los_engine=los)
        equip = self._make_equip("RADIO_VHF", requires_los=True)
        f = engine._los_factor(equip, Position(0, 0, 0), Position(1000, 0, 0))
        assert f == 1.0

    def test_los_blocked_factor_025(self):
        los = MagicMock()
        los.check_los.return_value = SimpleNamespace(visible=False, blocked_at=Position(500, 0, 0), blocked_by="terrain", grazing_distance=0.0)
        engine = self._make_engine(los_engine=los)
        equip = self._make_equip("RADIO_VHF", requires_los=True)
        f = engine._los_factor(equip, Position(0, 0, 0), Position(1000, 0, 0))
        assert f == pytest.approx(0.25)

    def test_hf_exempt_from_los(self):
        los = MagicMock()
        los.check_los.return_value = SimpleNamespace(visible=False, blocked_at=Position(500, 0, 0), blocked_by="terrain", grazing_distance=0.0)
        engine = self._make_engine(los_engine=los)
        equip = self._make_equip("RADIO_HF", requires_los=True)
        f = engine._los_factor(equip, Position(0, 0, 0), Position(1000, 0, 0))
        assert f == 1.0
        los.check_los.assert_not_called()

    def test_satellite_exempt_from_los(self):
        los = MagicMock()
        engine = self._make_engine(los_engine=los)
        equip = self._make_equip("SATELLITE", requires_los=True)
        f = engine._los_factor(equip, Position(0, 0, 0), Position(1000, 0, 0))
        assert f == 1.0
        los.check_los.assert_not_called()

    def test_uhf_blocked_los(self):
        los = MagicMock()
        los.check_los.return_value = SimpleNamespace(visible=False, blocked_at=Position(500, 0, 0), blocked_by="terrain", grazing_distance=0.0)
        engine = self._make_engine(los_engine=los)
        equip = self._make_equip("RADIO_UHF", requires_los=True)
        f = engine._los_factor(equip, Position(0, 0, 0), Position(1000, 0, 0))
        assert f == pytest.approx(0.25)

    def test_no_los_engine_returns_1(self):
        engine = self._make_engine(los_engine=None)
        equip = self._make_equip("RADIO_VHF", requires_los=True)
        f = engine._los_factor(equip, Position(0, 0, 0), Position(1000, 0, 0))
        assert f == 1.0

    def test_visible_field_accessed_not_has_los(self):
        """Verify we access result.visible, not result.has_los (bug fix)."""
        los = MagicMock()
        # Simulate LOSResult NamedTuple — only has `visible`, not `has_los`
        result = SimpleNamespace(visible=True)
        los.check_los.return_value = result
        engine = self._make_engine(los_engine=los)
        equip = self._make_equip("RADIO_VHF", requires_los=True)
        f = engine._los_factor(equip, Position(0, 0, 0), Position(1000, 0, 0))
        assert f == 1.0

    def test_requires_los_false_bypasses(self):
        los = MagicMock()
        engine = self._make_engine(los_engine=los)
        equip = self._make_equip("RADIO_VHF", requires_los=False)
        f = engine._los_factor(equip, Position(0, 0, 0), Position(1000, 0, 0))
        assert f == 1.0
        los.check_los.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# 52d — Space SIGINT + EW SIGINT Fusion
# ═══════════════════════════════════════════════════════════════════════════


class TestSIGINTFusion:
    """Verify inverse-variance weighted SIGINT track fusion."""

    def _make_fusion_engine(self):
        from stochastic_warfare.detection.intel_fusion import IntelFusionEngine

        return IntelFusionEngine(rng=_make_rng())

    def _make_report(self, e: float, n: float, unc: float, ts: float = 0.0):
        from stochastic_warfare.detection.intel_fusion import IntelReport, IntelSource

        return IntelReport(
            source=IntelSource.SIGINT,
            timestamp=ts,
            reliability=0.7,
            target_position=Position(e, n, 0.0),
            position_uncertainty_m=unc,
        )

    def test_two_sources_same_emitter_fused(self):
        fusion = self._make_fusion_engine()
        sp = self._make_report(1000, 2000, 500)
        ew = self._make_report(1050, 2050, 600)
        ids = fusion.fuse_sigint_tracks("blue", [sp], [ew])
        # Should produce 1 fused track (not 2 separate)
        assert len(ids) == 1

    def test_fused_track_better_accuracy(self):
        from stochastic_warfare.detection.intel_fusion import _fuse_two_reports

        a = self._make_report(1000, 2000, 500)
        b = self._make_report(1050, 2050, 600)
        fused = _fuse_two_reports(a, b)
        assert fused.position_uncertainty_m < min(
            a.position_uncertainty_m, b.position_uncertainty_m,
        )

    def test_distant_detections_separate_tracks(self):
        fusion = self._make_fusion_engine()
        sp = self._make_report(0, 0, 500)
        ew = self._make_report(5000, 5000, 500)
        ids = fusion.fuse_sigint_tracks("blue", [sp], [ew])
        # Too far apart → 2 separate tracks
        assert len(ids) == 2

    def test_no_space_reports_ew_only(self):
        fusion = self._make_fusion_engine()
        ew = self._make_report(1000, 2000, 500)
        ids = fusion.fuse_sigint_tracks("blue", [], [ew])
        assert len(ids) == 1

    def test_no_ew_reports_space_only(self):
        fusion = self._make_fusion_engine()
        sp = self._make_report(1000, 2000, 500)
        ids = fusion.fuse_sigint_tracks("blue", [sp], [])
        assert len(ids) == 1

    def test_sigint_report_buffering(self):
        """SIGINTEngine buffers successful intercepts for fusion."""
        from stochastic_warfare.ew.sigint import SIGINTEngine, SIGINTCollector
        from stochastic_warfare.ew.emitters import Emitter, EmitterType

        eb = EventBus()
        engine = SIGINTEngine(event_bus=eb, rng=_make_rng(seed=1))
        collector = SIGINTCollector(
            collector_id="c1", unit_id="u1",
            position=Position(0, 0, 0),
            receiver_sensitivity_dbm=-90.0,
            frequency_range_ghz=(1.0, 18.0),
            bandwidth_ghz=0.1,
            df_accuracy_deg=2.0,
            side="blue",
        )
        from stochastic_warfare.ew.emitters import WaveformType

        emitter = Emitter(
            emitter_id="e1", unit_id="e_u1",
            position=Position(1000, 0, 0),
            frequency_ghz=10.0,
            bandwidth_ghz=0.1,
            power_dbm=60.0,
            antenna_gain_dbi=20.0,
            emitter_type=EmitterType.RADAR,
            waveform=WaveformType.PULSED,
        )
        # Attempt many intercepts to get at least one success
        for _ in range(50):
            engine.attempt_intercept(collector, emitter)
        reports = engine.get_recent_reports(clear=True)
        assert len(reports) >= 1
        # After clear, buffer is empty
        assert len(engine.get_recent_reports(clear=False)) == 0
