"""Phase 60 Step 0: ObscurantsEngine instantiation + CalibrationSchema + engine.py wiring."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

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


class TestObscurantsEngineInstantiation:
    """ObscurantsEngine is created and assigned to context."""

    def test_obscurants_engine_in_scenario_loader_result(self) -> None:
        """Structural: scenario.py result dict includes obscurants_engine key."""
        import ast
        from pathlib import Path

        src = Path("stochastic_warfare/simulation/scenario.py").read_text()
        tree = ast.parse(src)
        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value == "obscurants_engine":
                found = True
                break
        assert found, "obscurants_engine key missing from scenario.py result dict"

    def test_todo_comment_removed(self) -> None:
        """The TODO comment about ObscurantsEngine not implemented is removed."""
        from pathlib import Path

        src = Path("stochastic_warfare/simulation/scenario.py").read_text()
        assert "TODO: ObscurantsEngine not implemented" not in src

    def test_engine_update_calls_obscurants(self) -> None:
        """Structural: engine.py calls obscurants_engine.update(dt)."""
        from pathlib import Path

        src = Path("stochastic_warfare/simulation/engine.py").read_text()
        assert "obscurants_engine.update(dt)" in src
        assert "obscurants_engine.update(clock)" not in src


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
        engine.update(60.0)  # Should not raise

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
