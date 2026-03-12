"""Phase 57c: Deficit closure verification.

Structural tests that key deficits resolved in Block 6 (Phases 49-56)
have working code paths.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "stochastic_warfare"
DATA_DIR = PROJECT_ROOT / "data"


class TestDEWDeficitClosure:
    """DEW (Directed Energy Weapons) deficit closure."""

    def test_dew_disable_path_exists(self):
        """Verify dew_disable_threshold is consumed in battle.py (Phase 51c fix)."""
        battle_py = SRC_DIR / "simulation" / "battle.py"
        text = battle_py.read_text(encoding="utf-8")
        assert "dew_disable_threshold" in text, (
            "dew_disable_threshold not found in battle.py — Phase 51c deficit not resolved"
        )

    def test_dew_config_scenario_exists(self):
        """At least one scenario YAML has dew_config."""
        found = False
        for path in DATA_DIR.rglob("scenario.yaml"):
            with open(path) as f:
                data = yaml.safe_load(f) or {}
            if "dew_config" in data:
                found = True
                break
        assert found, "No scenario YAML references dew_config"


class TestNavalDeficitClosure:
    """Naval combat deficit closure."""

    def test_naval_engagement_routing_exists(self):
        """Verify naval engagement routing method exists in battle.py (Phase 51a fix)."""
        battle_py = SRC_DIR / "simulation" / "battle.py"
        text = battle_py.read_text(encoding="utf-8")
        assert "_route_naval_engagement" in text, (
            "_route_naval_engagement not found in battle.py — naval routing deficit not resolved"
        )

    def test_depth_charge_routing_exists(self):
        """DEPTH_CHARGE engagement type exists (Phase 51a)."""
        battle_py = SRC_DIR / "simulation" / "battle.py"
        text = battle_py.read_text(encoding="utf-8")
        assert "DEPTH_CHARGE" in text, (
            "DEPTH_CHARGE routing not found in battle.py"
        )


class TestFireRateDeficitClosure:
    """Fire rate limiting deficit closure."""

    def test_fire_rate_cooldown_exists(self):
        """Verify fire rate limiting code path exists (Phase 11a fix)."""
        # Check combat or battle files for cooldown mechanism
        found = False
        for path in list(SRC_DIR.rglob("*.py")):
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                continue
            if "cooldown" in text.lower() and ("fire" in text.lower() or "weapon" in text.lower()):
                found = True
                break
        assert found, "No fire rate cooldown mechanism found in source code"


class TestScenarioResolutionDeficitClosure:
    """Resolution and stalling deficit closure."""

    def test_closing_range_guard_exists(self):
        """Verify closing range guard exists (Phase 55a fix)."""
        # Check for _forces_within_closing_range or closing_range in battle/engine
        found = False
        for filename in ("battle.py", "engine.py"):
            path = SRC_DIR / "simulation" / filename
            if path.exists():
                text = path.read_text(encoding="utf-8")
                if "closing_range" in text:
                    found = True
                    break
        assert found, "Closing range guard not found — Phase 55a deficit not resolved"

    def test_calibration_schema_typed(self):
        """CalibrationSchema is a pydantic model, not a free-form dict (Phase 49a)."""
        from stochastic_warfare.simulation.calibration import CalibrationSchema
        from pydantic import BaseModel
        assert issubclass(CalibrationSchema, BaseModel), (
            "CalibrationSchema should be a pydantic BaseModel"
        )
        # extra="forbid" should reject unknown keys
        schema = CalibrationSchema()
        with pytest.raises(Exception):
            CalibrationSchema.model_validate({"nonexistent_key_xyz": 42})
