"""Phase 73 authored-calibration and current-terminal lineage checks.

These structural checks preserve Phase 73's YAML and documentation contracts.
The imported seed-42 terminal classifications are current-engine regression
state, not historical or predictive validation.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.validation.historical.test_accuracy import (
    CURRENT_ENGINE_TERMINAL_SNAPSHOT,
)

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
DOCS_DIR = Path(__file__).resolve().parents[3] / "docs"

PHASE_73_CURRENT_TERMINALS = {
    "agincourt": ("english", "force_destroyed"),
    "cannae": ("carthaginian", "force_destroyed"),
    "salamis": ("greek", "force_destroyed"),
    "midway": ("usn", "force_destroyed"),
}

SOMME_SCENARIO = "somme_july1"


def _load_scenario(name: str) -> dict:
    """Find and load a scenario YAML by directory name."""
    for path in DATA_DIR.rglob("scenario.yaml"):
        if path.parent.name == name:
            with open(path) as f:
                return yaml.safe_load(f)
    pytest.fail(f"Scenario {name} not found")


class TestSommeVictoryCondition:
    """Somme authoring and current terminal classification."""

    def test_somme_force_destroyed_has_target_side(self):
        data = _load_scenario(SOMME_SCENARIO)
        for vc in data["victory_conditions"]:
            if vc["type"] == "force_destroyed":
                assert "target_side" in vc.get("params", {}), (
                    "Somme force_destroyed must specify target_side to prevent "
                    "generic annihilation triggering on British attackers"
                )

    def test_somme_current_terminal_snapshot(self):
        assert CURRENT_ENGINE_TERMINAL_SNAPSHOT[SOMME_SCENARIO] == (
            "german",
            "time_expired",
        )


class TestPhase73ForceDestroyedAuthoring:
    """Phase 73 force-destruction authoring has an explicit scope."""

    @pytest.mark.parametrize("scenario", sorted(PHASE_73_CURRENT_TERMINALS))
    def test_force_destroyed_has_target_side(self, scenario):
        data = _load_scenario(scenario)
        for vc in data["victory_conditions"]:
            if vc["type"] == "force_destroyed":
                params = vc.get("params", {})
                has_target = "target_side" in params or "count_disabled" in params
                assert has_target, (
                    f"{scenario}: force_destroyed should have target_side or "
                    f"count_disabled to define its scope"
                )


class TestCurrentTerminalLineage:
    """Phase 73 rows match the declared current-engine snapshot."""

    @pytest.mark.parametrize(
        ("scenario", "expected"),
        sorted(PHASE_73_CURRENT_TERMINALS.items()),
    )
    def test_current_terminal_snapshot(
        self,
        scenario: str,
        expected: tuple[str, str],
    ) -> None:
        assert CURRENT_ENGINE_TERMINAL_SNAPSHOT[scenario] == expected

    def test_phase73_rows_currently_end_by_force_destruction(self) -> None:
        assert {
            condition
            for _, condition in PHASE_73_CURRENT_TERMINALS.values()
        } == {
            "force_destroyed",
        }


class TestCalibrationComments:
    """Scenarios with force_ratio_modifier should have calibration comments."""

    @pytest.mark.test_evidence("structural_only")
    @pytest.mark.parametrize(
        "scenario",
        sorted(set(PHASE_73_CURRENT_TERMINALS) | {SOMME_SCENARIO}),
    )
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


@pytest.mark.test_evidence("structural_only")
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
