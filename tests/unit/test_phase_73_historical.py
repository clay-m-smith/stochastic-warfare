"""Phase 73: Structural tests for historical scenario correctness.

Validates that scenario YAMLs follow calibration patterns established in
working scenarios (Austerlitz, Hastings, Trafalgar) and that documentation
reflects the calibration methodology.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DOCS_DIR = Path(__file__).resolve().parents[2] / "docs"
TESTS_DIR = Path(__file__).resolve().parents[2] / "tests"

# Scenarios that must resolve decisively (not time_expired)
PHASE_73_DECISIVE = {"agincourt", "cannae", "salamis", "midway"}

# Somme must NOT be in decisive list (German defensive victory = time_expired)
SOMME_SCENARIO = "somme_july1"


def _load_scenario(name: str) -> dict:
    """Find and load a scenario YAML by directory name."""
    for path in DATA_DIR.rglob("scenario.yaml"):
        if path.parent.name == name:
            with open(path) as f:
                return yaml.safe_load(f)
    pytest.fail(f"Scenario {name} not found")


def _load_test_file() -> str:
    """Load the historical accuracy test file as text."""
    path = TESTS_DIR / "validation" / "test_historical_accuracy.py"
    return path.read_text()


class TestSommeVictoryCondition:
    """Somme force_destroyed must have target_side restriction."""

    def test_somme_force_destroyed_has_target_side(self):
        data = _load_scenario(SOMME_SCENARIO)
        for vc in data["victory_conditions"]:
            if vc["type"] == "force_destroyed":
                assert "target_side" in vc.get("params", {}), (
                    "Somme force_destroyed must specify target_side to prevent "
                    "generic annihilation triggering on British attackers"
                )

    def test_somme_not_in_decisive_combat_scenarios(self):
        source = _load_test_file()
        # Check that somme_july1 is NOT in the DECISIVE_COMBAT_SCENARIOS set
        assert "somme_july1" not in source.split("DECISIVE_COMBAT_SCENARIOS")[1].split("}")[0], (
            "somme_july1 should not be in DECISIVE_COMBAT_SCENARIOS — "
            "German defensive victory is correctly time_expired"
        )


class TestDecisiveScenariosHaveTargetSide:
    """All Phase 73 decisive scenarios should have target_side or count_disabled."""

    @pytest.mark.parametrize("scenario", sorted(PHASE_73_DECISIVE))
    def test_force_destroyed_has_target_side(self, scenario):
        data = _load_scenario(scenario)
        for vc in data["victory_conditions"]:
            if vc["type"] == "force_destroyed":
                params = vc.get("params", {})
                has_target = "target_side" in params or "count_disabled" in params
                assert has_target, (
                    f"{scenario}: force_destroyed should have target_side or "
                    f"count_disabled for decisive outcome"
                )


class TestDecisiveScenariosInTestSuite:
    """Phase 73 decisive scenarios must be registered in DECISIVE_COMBAT_SCENARIOS."""

    @pytest.mark.parametrize("scenario", sorted(PHASE_73_DECISIVE))
    def test_in_decisive_combat_scenarios(self, scenario):
        source = _load_test_file()
        block = source.split("DECISIVE_COMBAT_SCENARIOS")[1].split("}")[0]
        assert scenario in block, (
            f"{scenario} must be in DECISIVE_COMBAT_SCENARIOS in "
            f"test_historical_accuracy.py"
        )


class TestCalibrationComments:
    """Scenarios with force_ratio_modifier should have calibration comments."""

    @pytest.mark.parametrize("scenario", sorted(PHASE_73_DECISIVE | {SOMME_SCENARIO}))
    def test_has_calibration_comment(self, scenario):
        """Scenario YAML has a calibration rationale comment near force_ratio_modifier."""
        for path in DATA_DIR.rglob("scenario.yaml"):
            if path.parent.name == scenario:
                text = path.read_text()
                if "force_ratio_modifier" in text:
                    # Check for comment lines (# ...) near calibration overrides
                    has_comment = any(
                        "#" in line and any(kw in line.lower() for kw in [
                            "cev", "dupuy", "calibrat", "historically", "reflects",
                            "raised", "reduced",
                        ])
                        for line in text.splitlines()
                    )
                    assert has_comment, (
                        f"{scenario}: force_ratio_modifier present but no "
                        f"calibration rationale comment found"
                    )
                return
        pytest.fail(f"Scenario {scenario} not found")


class TestCalibrationDocumentation:
    """docs/concepts/models.md should document calibration methodology."""

    def test_models_md_has_calibration_section(self):
        models_md = DOCS_DIR / "concepts" / "models.md"
        assert models_md.exists(), "docs/concepts/models.md must exist"
        text = models_md.read_text()
        assert "Calibration Methodology" in text, (
            "docs/concepts/models.md must contain a 'Calibration Methodology' section"
        )

    def test_models_md_mentions_dupuy(self):
        models_md = DOCS_DIR / "concepts" / "models.md"
        text = models_md.read_text()
        assert "Dupuy" in text, (
            "Calibration methodology section should reference Dupuy's CEV concept"
        )

    def test_models_md_mentions_force_ratio_modifier(self):
        models_md = DOCS_DIR / "concepts" / "models.md"
        text = models_md.read_text()
        assert "force_ratio_modifier" in text, (
            "Calibration methodology section should explain force_ratio_modifier"
        )
