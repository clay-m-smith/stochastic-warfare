"""Phase 67 scenario-lineage checks.

The legacy Phase 67 list is useful as provenance for where Block 7 integration
work was first exercised.  It is not a historical winner oracle and does not
prove that later Block 9 performance flags preserve outcomes.  Those four flags
are not authored by any scenario in this list.

The production evaluator's one declared current-engine terminal snapshot lives
in :mod:`tests.validation.test_historical_accuracy`; this module deliberately
does not launch another full-catalog or Monte Carlo evaluation.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.validation.test_historical_accuracy import (
    CURRENT_ENGINE_TERMINAL_SNAPSHOT,
)

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"

PHASE_67_LINEAGE_SCENARIOS = (
    "73_easting",
    "golan_heights",
    "eastern_front_1943",
    "bekaa_valley_1982",
    "gulf_war_ew_1991",
    "korean_peninsula",
    "suwalki_gap",
    "taiwan_strait",
    "falklands_naval",
    "coin_campaign",
)

BLOCK9_OPT_IN_FLAGS = {
    "enable_scan_scheduling",
    "enable_lod",
    "enable_soa",
    "enable_parallel_detection",
}


def _scenario_path(name: str) -> Path:
    matches = [
        path
        for path in DATA_DIR.rglob("scenario.yaml")
        if path.parent.name == name
    ]
    assert len(matches) == 1, (
        f"{name}: expected one catalog scenario YAML, found {matches}"
    )
    return matches[0]


@pytest.mark.parametrize("scenario", PHASE_67_LINEAGE_SCENARIOS)
def test_phase67_lineage_is_in_current_snapshot(scenario: str) -> None:
    """The legacy lineage names remain in the catalog regression inventory."""
    assert _scenario_path(scenario).is_file()
    assert scenario in CURRENT_ENGINE_TERMINAL_SNAPSHOT


@pytest.mark.parametrize("scenario", PHASE_67_LINEAGE_SCENARIOS)
def test_phase67_lineage_does_not_author_block9_flags(
    scenario: str,
) -> None:
    """Do not misattribute later performance-flag coverage to this list."""
    data = yaml.safe_load(
        _scenario_path(scenario).read_text(encoding="utf-8")
    )
    overrides = data.get("calibration_overrides") or {}
    authored = BLOCK9_OPT_IN_FLAGS & overrides.keys()
    assert not authored, f"{scenario} unexpectedly authors {sorted(authored)}"
