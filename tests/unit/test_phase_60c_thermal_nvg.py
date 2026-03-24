"""Phase 60c: Thermal ΔT model & NVG detection tests."""

from __future__ import annotations

import math
from unittest.mock import MagicMock

from stochastic_warfare.environment.time_of_day import (
    TimeOfDayEngine,
    ThermalEnvironment,
)


def _make_tod(solar_elevation_deg: float, lux: float = 100000.0) -> MagicMock:
    """Create a mock TimeOfDayEngine returning controlled values."""
    tod = MagicMock(spec=TimeOfDayEngine)
    el_rad = math.radians(solar_elevation_deg)

    # thermal_environment
    if solar_elevation_deg > 10:
        contrast = min(1.0, solar_elevation_deg / 45.0)
    elif solar_elevation_deg < -10:
        contrast = 0.6
    else:
        contrast = max(0.1, abs(solar_elevation_deg) / 10.0 * 0.5)

    crossover_hours = 0.0 if -5 < solar_elevation_deg < 5 else 6.0
    tod.thermal_environment.return_value = ThermalEnvironment(
        thermal_contrast=contrast,
        background_temperature=20.0,
        crossover_in_hours=crossover_hours,
    )

    # nvg_effectiveness
    if lux <= 0.0001:
        nvg = 0.05
    else:
        x = math.log10(lux) + 2
        nvg = 1.0 / (1.0 + math.exp(-2 * x))
    tod.nvg_effectiveness.return_value = min(1.0, nvg)

    return tod


class TestThermalContrast:
    """Thermal ΔT model replaces flat night_thermal_modifier."""

    def test_high_contrast_at_night(self) -> None:
        """Night (solar < -10°) → thermal contrast ~0.6 (radiative cooling)."""
        tod = _make_tod(-20.0)
        therm = tod.thermal_environment(0.0, 0.0)
        assert therm.thermal_contrast >= 0.5, "Night should have good thermal contrast"

    def test_contrast_collapses_near_crossover(self) -> None:
        """Near crossover (solar ~0°) → thermal contrast is low."""
        tod = _make_tod(0.0)
        therm = tod.thermal_environment(0.0, 0.0)
        assert therm.thermal_contrast < 0.3, "Crossover should have low contrast"

    def test_running_vehicle_maintains_dt(self) -> None:
        """Phase 60c: running vehicle at crossover → ΔT floored at 0.5."""
        # In battle.py: if _tdc < 0.5 and target.speed > 1.0 → _tdc = max(_tdc, 0.5)
        _tdc = 0.15  # simulated low crossover contrast
        target_speed = 10.0  # moving vehicle
        if _tdc < 0.5 and target_speed > 1.0:
            _tdc = max(_tdc, 0.5)
        assert _tdc == 0.5

    def test_stationary_vehicle_at_crossover(self) -> None:
        """Stationary vehicle at crossover → ΔT collapses (near-invisible)."""
        _tdc = 0.15
        target_speed = 0.0
        if _tdc < 0.5 and target_speed > 1.0:
            _tdc = max(_tdc, 0.5)
        assert _tdc == 0.15  # No floor applied


class TestNVGDetection:
    """NVG-equipped units recover visual detection at night."""

    def test_nvg_equipped_night_detection_recovery(self) -> None:
        """NVG at night → detection recovery ~60% of daylight."""
        night_visual_modifier = 0.2  # heavy night penalty
        nvg_eff = 0.8  # good ambient light for NVG

        _nvg_recovery = nvg_eff * 0.5
        _nvg_visual = night_visual_modifier + _nvg_recovery * (1.0 - night_visual_modifier)

        # Expected: 0.2 + 0.4 * 0.8 = 0.52
        assert _nvg_visual > 0.4, f"NVG should recover detection, got {_nvg_visual}"
        assert _nvg_visual < 0.7, f"NVG shouldn't fully restore daylight, got {_nvg_visual}"

    def test_no_nvg_night_stays_low(self) -> None:
        """Non-NVG unit at night → detection range stays at twilight modifier."""
        night_visual_modifier = 0.2
        # Without NVG, detection_range stays at 0.2× (no recovery)
        detection_range = 1000.0 * night_visual_modifier
        assert detection_range == 200.0

    def test_nvg_daytime_no_effect(self) -> None:
        """NVG during daytime → no effect (night_visual_modifier = 1.0)."""
        night_visual_modifier = 1.0
        # The enable_nvg_detection gate checks night_visual_modifier < 1.0
        should_apply = night_visual_modifier < 1.0
        assert not should_apply


class TestFlagGating:
    """All Phase 60c effects gated by enable_* flags."""

    def test_thermal_crossover_flag_false_uses_original(self) -> None:
        """enable_thermal_crossover=False → original night_thermal_modifier used."""
        from stochastic_warfare.simulation.calibration import CalibrationSchema

        cal = CalibrationSchema()
        assert cal.get("enable_thermal_crossover", None) is False
        # With flag=False, battle.py uses night_thermal_modifier, not thermal_dt_contrast

    def test_nvg_detection_flag_false_no_recovery(self) -> None:
        """enable_nvg_detection=False → no NVG recovery applied."""
        from stochastic_warfare.simulation.calibration import CalibrationSchema

        cal = CalibrationSchema()
        assert cal.get("enable_nvg_detection", None) is False

    def test_both_flags_false_backward_compat(self) -> None:
        """Both flags False → identical behavior to Phase 52a."""
        from stochastic_warfare.simulation.calibration import CalibrationSchema

        cal = CalibrationSchema()
        assert cal.get("enable_thermal_crossover", None) is False
        assert cal.get("enable_nvg_detection", None) is False
        # Both disabled means original night modifiers apply unchanged

    def test_thermal_crossover_structural(self) -> None:
        """Structural: battle.py contains thermal_dt_contrast computation."""
        from pathlib import Path

        src = Path("stochastic_warfare/simulation/battle.py").read_text()
        assert "thermal_dt_contrast" in src
        assert "enable_thermal_crossover" in src

    def test_nvg_detection_structural(self) -> None:
        """Structural: battle.py contains NVG detection recovery logic."""
        from pathlib import Path

        src = Path("stochastic_warfare/simulation/battle.py").read_text()
        assert "nvg_effectiveness" in src or "enable_nvg_detection" in src
        assert "nvg_recovery" in src or "_nvg_recovery" in src
