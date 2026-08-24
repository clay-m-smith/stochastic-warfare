"""Durable repository-delivery and documentation-trust contracts.

These checks are structural delivery invariants, not simulation-behavior
evidence.
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
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


@pytest.mark.test_evidence("structural_only")
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
        "tests/unit/terrain/*",
        "mkdocs build --strict",
        "ruff check stochastic_warfare/ api/ tests/ scripts/",
        "actions/upload-artifact@",
        "if: always()",
    ):
        assert required in text, f"missing repository workflow contract: {required}"


@pytest.mark.test_evidence("structural_only")
def test_source_local_evidence_annotations_are_machine_checked() -> None:
    evidence_root = ROOT / "tests" / "validation" / "evidence_ledgers"
    conftest = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    validator = (ROOT / "scripts" / "validate_test_evidence.py").read_text(
        encoding="utf-8",
    )

    assert not list(evidence_root.glob("*.json"))
    assert "evidence_ledgers" not in conftest
    assert "phase_start_commit" not in conftest
    assert 'EVIDENCE_MARKER = "test_evidence"' in validator
    assert "_validate_source_annotations" in validator


@pytest.mark.test_evidence("structural_only")
def test_docs_config_keeps_current_engineering_navigation_compact() -> None:
    config = yaml.safe_load((ROOT / "mkdocs.yml").read_text(encoding="utf-8"))

    assert config["validation"]["links"]["anchors"] == "warn"
    engineering = next(
        entry["Engineering"]
        for entry in config["nav"]
        if "Engineering" in entry
    )
    assert tuple(next(iter(entry)) for entry in engineering) == (
        "Consolidation Contract",
        "Current Roadmap",
        "Future Roadmaps",
        "Remediation Backlog",
        "Phase History",
    )

    rendered = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    for page in (
        "specs/tiered-modular-monolith.md",
        "development-phases-block13.md",
        "devlog/index.md",
        "specs/validation-and-documentation-trust.md",
    ):
        assert page in rendered
    assert "devlog/phase-" not in rendered

    malformed = (
        "known-limitations--deferred-items",
        "deferrals-planned--deferred",
        "known-limitations--deferrals",
    )
    devlog_index = (ROOT / "docs" / "devlog" / "index.md").read_text(
        encoding="utf-8"
    )
    assert not any(fragment in devlog_index for fragment in malformed)


@pytest.mark.test_evidence("structural_only")
def test_current_validation_never_imports_legacy_namespace() -> None:
    violations: list[str] = []
    validation_root = ROOT / "stochastic_warfare" / "validation"
    for path in sorted(validation_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = tuple(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                modules = (node.module or "",)
            else:
                continue
            if any(
                module == "stochastic_warfare.legacy"
                or module.startswith("stochastic_warfare.legacy.")
                for module in modules
            ):
                relative = path.relative_to(ROOT).as_posix()
                violations.append(f"{relative}:{node.lineno}")

    assert violations == []
