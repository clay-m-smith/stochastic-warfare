"""Phase 112 red proofs for repository delivery and documentation trust.

These checks intentionally describe the accepted Phase 112 contract.  They are
structural delivery invariants, not simulation-behavior evidence.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"


def _workflow_documents() -> dict[str, object]:
    return {
        path.name: yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        for path in sorted(WORKFLOWS.glob("*.yml"))
    }


def _workflow_text() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(WORKFLOWS.glob("*.yml"))
    )


def test_pytest_contract_has_real_partitions_and_structural_marker() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    pytest_config = config["tool"]["pytest"]["ini_options"]
    markers = pytest_config["markers"]
    addopts = pytest_config["addopts"]

    assert any(marker.startswith("structural:") for marker in markers)
    assert not any(marker.startswith("terrain:") for marker in markers)
    assert "not terrain" not in addopts
    assert "not api" not in addopts
    assert "not e2e" not in addopts


def test_workflows_expose_every_required_partition_and_evidence_artifact() -> None:
    documents = _workflow_documents()
    text = _workflow_text()

    assert any("schedule" in document["on"] for document in documents.values())
    assert "--locked" in text
    for required in (
        "tests/api",
        "tests/e2e",
        "slow and not benchmark",
        "benchmark and not slow",
        "slow and benchmark",
        "--extra terrain",
        "test_phase_15a_pipeline_heightmap.py",
        "mkdocs build --strict",
        "ruff check stochastic_warfare/ api/ tests/ scripts/",
        "actions/upload-artifact@",
        "if: always()",
    ):
        assert required in text, f"missing Phase 112 workflow contract: {required}"


def test_structural_evidence_ledgers_are_machine_checked() -> None:
    evidence_root = ROOT / "tests" / "validation" / "evidence_ledgers"

    assert (evidence_root / "no_direct_oracles.json").is_file()
    assert (evidence_root / "weak_oracles.json").is_file()
    assert (evidence_root / "reviewed_behavioral_oracles.json").is_file()
    assert (evidence_root / "phase112_remediations.json").is_file()
    assert (ROOT / "scripts" / "validate_test_evidence.py").is_file()


def test_real_docs_config_enforces_anchors_and_navigates_phase112() -> None:
    config = yaml.safe_load((ROOT / "mkdocs.yml").read_text(encoding="utf-8"))

    assert config["validation"]["links"]["anchors"] == "warn"
    rendered = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    for page in (
        "development-phases-block13.md",
        "devlog/phase-112.md",
        "specs/validation-and-documentation-trust.md",
    ):
        assert page in rendered

    malformed = (
        "known-limitations--deferred-items",
        "deferrals-planned--deferred",
        "known-limitations--deferrals",
    )
    devlog_index = (ROOT / "docs" / "devlog" / "index.md").read_text(
        encoding="utf-8"
    )
    assert not any(fragment in devlog_index for fragment in malformed)
