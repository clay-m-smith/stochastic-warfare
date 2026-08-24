"""Phase 60 Step 0: ObscurantsEngine instantiation + CalibrationSchema + engine.py wiring."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.simulation.calibration import CalibrationSchema


class TestCalibrationSchemaPhase60:
    """New calibration fields accepted without error."""

    def test_enable_obscurants_default_false(self) -> None:
        cal = CalibrationSchema()
        assert cal.get("enable_obscurants", None) is False

    def test_enable_fire_zones_default_false(self) -> None:
        cal = CalibrationSchema()
        assert cal.get("enable_fire_zones", None) is False

    def test_enable_thermal_crossover_default_false(self) -> None:
        cal = CalibrationSchema()
        assert cal.get("enable_thermal_crossover", None) is False

    def test_enable_nvg_detection_default_false(self) -> None:
        cal = CalibrationSchema()
        assert cal.get("enable_nvg_detection", None) is False


class TestObscurantsEngineUpdate:
    """ObscurantsEngine.update() accepts dt_seconds float."""

    def test_update_accepts_float(self) -> None:
        from stochastic_warfare.environment.obscurants import ObscurantsEngine

        weather = MagicMock()
        weather.current.wind.speed = 5.0
        weather.current.wind.direction = 0.0
        weather.current.visibility = 10000.0
        weather.current.state.name = "CLEAR"
        weather.current.humidity = 0.5

        tod = MagicMock()
        clock = MagicMock()
        import numpy as np

        rng = np.random.default_rng(42)

        engine = ObscurantsEngine(weather, tod, clock, rng)
        cloud_id = engine.deploy_smoke(
            Position(100.0, 200.0, 0.0),
            50.0,
        )
        engine.update(60.0)
        cloud = engine._clouds[cloud_id]
        assert cloud.age_seconds == 60.0
        assert cloud.center_e == pytest.approx(100.0)
        assert cloud.center_n == pytest.approx(500.0)
        assert cloud.radius > 50.0
        assert 0.0 < cloud.density < 1.0

    def test_opacity_zero_when_no_clouds(self) -> None:
        """No deployed clouds → zero opacity at any position (backward compat)."""
        from stochastic_warfare.environment.obscurants import ObscurantsEngine
        from stochastic_warfare.core.types import Position

        weather = MagicMock()
        weather.current.wind.speed = 0.0
        weather.current.wind.direction = 0.0
        weather.current.visibility = 10000.0
        weather.current.state.name = "CLEAR"

        tod = MagicMock()
        clock = MagicMock()
        import numpy as np

        rng = np.random.default_rng(42)

        engine = ObscurantsEngine(weather, tod, clock, rng)
        opacity = engine.opacity_at(Position(1000.0, 1000.0, 0.0))
        assert opacity.visual == 0.0
        assert opacity.thermal == 0.0
        assert opacity.radar == 0.0
