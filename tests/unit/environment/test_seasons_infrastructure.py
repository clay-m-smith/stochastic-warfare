"""Phase 59 Step 0: SeasonsEngine instantiation + CalibrationSchema + engine.py fix."""

from __future__ import annotations

from stochastic_warfare.simulation.calibration import CalibrationSchema


class TestCalibrationSchemaPhase59:
    """New calibration fields accepted without error."""

    def test_enable_seasonal_effects_default_false(self) -> None:
        cal = CalibrationSchema()
        assert cal.get("enable_seasonal_effects", None) is False

    def test_enable_equipment_stress_default_false(self) -> None:
        cal = CalibrationSchema()
        assert cal.get("enable_equipment_stress", None) is False

    def test_enable_obstacle_effects_default_false(self) -> None:
        cal = CalibrationSchema()
        assert cal.get("enable_obstacle_effects", None) is False


class TestSeasonsEngineUpdate:
    """SeasonsEngine.update() accepts dt_seconds float."""

    def test_update_accepts_float(self) -> None:
        from unittest.mock import MagicMock

        from stochastic_warfare.environment.seasons import SeasonsConfig, SeasonsEngine

        clock = MagicMock()
        weather = MagicMock()
        weather.current.temperature = 20.0
        weather.current.precipitation_rate = 0.0
        weather.current.humidity = 0.5
        weather.current.state = 0  # CLEAR
        weather.current.wind.speed = 5.0

        astronomy = MagicMock()
        astronomy.day_length_hours.return_value = 12.0

        engine = SeasonsEngine(SeasonsConfig(latitude=45.0), clock, weather, astronomy)
        # Should not raise — accepts float, not SimulationClock
        engine.update(60.0)
        cond = engine.current
        assert cond.ground_trafficability > 0
