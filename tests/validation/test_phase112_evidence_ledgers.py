"""Machine-check the Phase 112 current and historical evidence ledgers."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REVIEWED_BEHAVIORAL = (
    ROOT
    / "tests"
    / "validation"
    / "evidence_ledgers"
    / "reviewed_behavioral_oracles.json"
)


def test_evidence_ledgers_match_fresh_collection() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/validate_test_evidence.py"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["no_direct_oracles"] > 0
    assert payload["reviewed_behavioral_oracles"] > 0
    assert payload["weak_oracles"] > 0
    assert payload["structural_nodes"] > 0


def test_strong_behavioral_oracles_are_not_auto_marked_structural() -> None:
    reviewed = json.loads(REVIEWED_BEHAVIORAL.read_text(encoding="utf-8"))
    reviewed_ids = {
        entry["node_id"]
        for entry in reviewed["entries"]
    }
    expected = {
        (
            "tests/api/test_phase_106_api_integrity.py::"
            "test_api_override_changes_outcome_and_is_deterministic"
        ),
        (
            "tests/api/test_phase_106_api_integrity.py::"
            "test_loader_applies_sparse_calibration_patch_without_mutating_source"
        ),
    }
    assert expected <= reviewed_ids

    collection = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            "-o",
            "addopts=",
            "-m",
            "structural",
            "tests/api/test_phase_106_api_integrity.py",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert not expected.intersection(collection.stdout.splitlines())
