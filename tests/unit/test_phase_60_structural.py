"""Phase 60: Structural verification tests — code-level checks."""

from __future__ import annotations

from pathlib import Path

import pytest


class TestPhase60Structural:
    """Verify all Phase 60 wiring is present at the source level."""

    def test_obscurants_engine_instantiated_in_scenario(self) -> None:
        """ObscurantsEngine is imported and created in scenario.py."""
        src = Path("stochastic_warfare/simulation/scenario.py").read_text()
        assert "from stochastic_warfare.environment.obscurants import ObscurantsEngine" in src
        assert "ObscurantsEngine(" in src

    def test_obscurants_update_in_engine(self) -> None:
        """engine.py calls obscurants_engine.update(dt)."""
        src = Path("stochastic_warfare/simulation/engine.py").read_text()
        assert "obscurants_engine.update(dt)" in src

    def test_opacity_at_in_battle_detection(self) -> None:
        """battle.py queries opacity_at() in the detection loop."""
        src = Path("stochastic_warfare/simulation/battle.py").read_text()
        assert "opacity_at(best_target.position)" in src

    def test_fire_zone_creation_in_battle(self) -> None:
        """battle.py creates fire zones from fire_started."""
        src = Path("stochastic_warfare/simulation/battle.py").read_text()
        assert "create_fire_zone(" in src
        assert "enable_fire_zones" in src

    def test_thermal_crossover_in_battle(self) -> None:
        """battle.py computes thermal_dt_contrast and applies it."""
        src = Path("stochastic_warfare/simulation/battle.py").read_text()
        assert "thermal_dt_contrast" in src
        assert "thermal_environment(" in src

    def test_nvg_detection_in_battle(self) -> None:
        """battle.py applies NVG detection recovery."""
        src = Path("stochastic_warfare/simulation/battle.py").read_text()
        assert "nvg_effectiveness(" in src
        assert "SensorType.NVG" in src

    def test_dust_trail_in_battle(self) -> None:
        """battle.py spawns dust trail from vehicle movement."""
        src = Path("stochastic_warfare/simulation/battle.py").read_text()
        assert "add_dust(u.position" in src

    def test_fire_zone_movement_block_in_battle(self) -> None:
        """battle.py checks fire zones before allowing movement."""
        src = Path("stochastic_warfare/simulation/battle.py").read_text()
        assert "fire zones block movement" in src.lower() or "fire zone" in src.lower()
        # Fire zone radius check
        assert "current_radius_m" in src

    def test_fire_zone_damage_logging_in_battle(self) -> None:
        """battle.py logs units in fire zones after damage step."""
        src = Path("stochastic_warfare/simulation/battle.py").read_text()
        assert "units_in_fire(" in src
        assert "Unit %s in fire zone" in src

    def test_all_four_calibration_flags_exist(self) -> None:
        """CalibrationSchema has all 4 Phase 60 flags."""
        from stochastic_warfare.simulation.calibration import CalibrationSchema

        cal = CalibrationSchema()
        for flag in ("enable_obscurants", "enable_fire_zones",
                     "enable_thermal_crossover", "enable_nvg_detection"):
            assert flag in CalibrationSchema.model_fields, f"Missing {flag}"
            assert cal.get(flag, None) is False, f"{flag} should default to False"
