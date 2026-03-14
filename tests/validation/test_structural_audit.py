"""Phase 58a: Structural verification tests.

Regression guardrails that verify key combat integration wiring.
Each test reads source files and asserts that critical code paths exist.
Pattern follows tests/validation/test_deficit_closure.py.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "stochastic_warfare"


class TestAirEngineWiring:
    """Verify air combat engines are instantiated and routed."""

    def test_air_engines_on_context(self):
        """scenario.py creates air_combat_engine, air_ground_engine, air_defense_engine."""
        scenario_py = SRC_DIR / "simulation" / "scenario.py"
        text = scenario_py.read_text(encoding="utf-8")
        assert "air_combat_engine" in text, (
            "air_combat_engine not found in scenario.py — air combat engine not wired"
        )
        assert "air_ground_engine" in text, (
            "air_ground_engine not found in scenario.py — air-ground engine not wired"
        )
        assert "air_defense_engine" in text, (
            "air_defense_engine not found in scenario.py — air defense engine not wired"
        )

    def test_air_engagement_types_routed(self):
        """battle.py routes AIR_TO_AIR or has _route_air_engagement."""
        battle_py = SRC_DIR / "simulation" / "battle.py"
        text = battle_py.read_text(encoding="utf-8")
        assert "_route_air_engagement" in text or "AIR_TO_AIR" in text, (
            "No air engagement routing found in battle.py"
        )


class TestDamageDetailConsumption:
    """Verify DamageResult fields are consumed, not discarded."""

    def test_damage_detail_consumed(self):
        """battle.py references .casualties and .systems_damaged from damage results."""
        battle_py = SRC_DIR / "simulation" / "battle.py"
        text = battle_py.read_text(encoding="utf-8")
        assert ".casualties" in text, (
            "DamageResult.casualties not consumed in battle.py"
        )
        assert ".systems_damaged" in text or "degrade_equipment" in text, (
            "DamageResult.systems_damaged not consumed in battle.py"
        )


class TestPostureCalibration:
    """Verify posture protection is configurable via CalibrationSchema."""

    def test_posture_protection_in_calibration(self):
        """calibration.py has posture_blast_protection or posture_frag_protection fields."""
        cal_py = SRC_DIR / "simulation" / "calibration.py"
        text = cal_py.read_text(encoding="utf-8")
        assert "posture_blast_protection" in text, (
            "posture_blast_protection not found in CalibrationSchema"
        )
        assert "posture_frag_protection" in text, (
            "posture_frag_protection not found in CalibrationSchema"
        )


class TestFuelGate:
    """Verify ground units track fuel and battle.py consumes it."""

    def test_ground_unit_fuel_field(self):
        """ground.py has fuel_remaining field."""
        ground_py = SRC_DIR / "entities" / "unit_classes" / "ground.py"
        text = ground_py.read_text(encoding="utf-8")
        assert "fuel_remaining" in text, (
            "fuel_remaining not found in ground.py — GroundUnit has no fuel tracking"
        )

    def test_battle_fuel_consumption(self):
        """battle.py consumes fuel during ground movement (not just aerial fuel check)."""
        battle_py = SRC_DIR / "simulation" / "battle.py"
        text = battle_py.read_text(encoding="utf-8")
        assert "Phase 58e" in text, (
            "Ground fuel consumption (Phase 58e) not found in battle.py"
        )
