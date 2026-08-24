"""Machine-check source-local test-evidence review metadata."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

from scripts.run_pytest_partition import (
    _pytest_command,
    _subprocess_environment,
)
from scripts.validate_test_evidence import (
    _behavioral_signal_reasons,
    _definition_index,
    _definitions_from_tree,
    _validate_durable_test_paths,
)

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_ROOT = ROOT / "tests" / "validation" / "evidence_ledgers"
VALIDATOR = ROOT / "scripts" / "validate_test_evidence.py"


def _synthetic_test_definition(source: str):
    tree = ast.parse(textwrap.dedent(source))
    definitions = _definitions_from_tree(
        "tests/unit/example/test_synthetic.py",
        tree,
    )
    assert len(definitions) == 1
    return next(iter(definitions.values()))


def test_source_local_evidence_matches_fresh_collection() -> None:
    with tempfile.TemporaryDirectory(
        prefix="stochastic-warfare-evidence-parent-pycache-",
    ) as pycache_prefix:
        hostile_environment = _subprocess_environment(pycache_prefix)
        hostile_environment.update(
            {
                "PYTEST_ADDOPTS": "--invalid-hostile-parent-option",
                "PYTEST_PLUGINS": "hostile_parent_plugin",
            },
        )
        result = subprocess.run(
            [sys.executable, str(VALIDATOR)],
            cwd=ROOT,
            env=hostile_environment,
            check=False,
            capture_output=True,
            text=True,
        )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["no_direct_definitions"] > 0
    assert payload["reviewed_behavioral_definitions"] > 0
    assert payload["weak_definitions"] > 0
    assert payload["structural_definitions"] > 0
    assert payload["structural_nodes"] > 0
    assert payload["annotation_scopes"] <= payload["annotated_definitions"]
    assert sum(payload["classification_counts"].values()) == payload[
        "annotated_definitions"
    ]


@pytest.mark.test_evidence("structural_only")
def test_collection_loads_no_external_evidence_ledgers() -> None:
    assert not list(EVIDENCE_ROOT.glob("*.json"))

    conftest = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    validator = VALIDATOR.read_text(encoding="utf-8")
    assert "evidence_ledgers" not in conftest
    assert "phase_start_commit" not in conftest
    assert "phase_start_commit" not in validator
    assert 'EVIDENCE_MARKER = "test_evidence"' in validator


def test_strong_behavioral_oracles_are_not_auto_marked_structural() -> None:
    expected = {
        (
            "tests/api/test_integrity_contract.py::"
            "test_api_override_changes_outcome_and_is_deterministic"
        ),
        (
            "tests/api/test_integrity_contract.py::"
            "test_loader_applies_sparse_calibration_patch_without_mutating_source"
        ),
    }
    definitions = _definition_index()
    for definition_id in expected:
        path, qualified_name = definition_id.split("::", 1)
        annotation = definitions[(path, qualified_name)].annotation
        assert annotation is not None
        assert annotation.classification == "behavioral_oracle"

    command = _pytest_command(
        "--collect-only",
        "-q",
        "-m",
        "structural",
        "tests/api/test_integrity_contract.py",
    )
    with tempfile.TemporaryDirectory(
        prefix="stochastic-warfare-evidence-contract-pycache-",
    ) as pycache_prefix:
        collection = subprocess.run(
            command,
            cwd=ROOT,
            env=_subprocess_environment(pycache_prefix),
            check=False,
            capture_output=True,
            text=True,
        )
    assert collection.returncode in {0, 5}, collection.stderr
    assert not expected.intersection(collection.stdout.splitlines())


def test_phase_owned_active_test_paths_are_rejected() -> None:
    with pytest.raises(ValueError, match="durable product boundary"):
        _validate_durable_test_paths(
            [
                Path("tests/unit/test_phase119_example.py"),
                Path("tests/validation/test_block14_exit.py"),
            ],
        )


def test_root_level_active_test_paths_are_rejected() -> None:
    with pytest.raises(ValueError, match="durable subsystem directory"):
        _validate_durable_test_paths(
            [
                Path("tests/unit/test_orphan.py"),
                Path("tests/integration/test_orphan.py"),
                Path("tests/validation/test_orphan.py"),
            ],
        )


def test_unsupported_top_level_active_test_paths_are_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="supported top-level test boundary",
    ) as error:
        _validate_durable_test_paths(
            [
                Path("tests/performance/test_scenario.py"),
                Path("tests/tools/test_profiling.py"),
            ],
        )

    assert "tests/performance/test_scenario.py" in str(error.value)
    assert "tests/tools/test_profiling.py" in str(error.value)


@pytest.mark.parametrize(
    "path_expression",
    [
        pytest.param("implementation.__file__", id="module-file"),
        pytest.param("Path(__file__)", id="path-current-module"),
        pytest.param("'package/implementation.py'", id="py-literal"),
        pytest.param("'package/implementation.pyi'", id="pyi-literal"),
    ],
)
def test_python_source_open_is_a_weak_source_oracle(
    path_expression: str,
) -> None:
    definition = _synthetic_test_definition(
        f"""
        def test_source_contract():
            source = open({path_expression}).read()
            assert "implementation marker" in source
        """,
    )

    assert definition.weak_reasons == (
        "source/signature/import call: open-python-source",
    )
    assert _behavioral_signal_reasons(definition) == ()


@pytest.mark.parametrize(
    "path_expression",
    [
        pytest.param("'scenario.yaml'", id="yaml"),
        pytest.param("'result.json'", id="json"),
        pytest.param("'runtime.log'", id="log"),
        pytest.param(
            "Path(__file__).with_name('scenario.yaml')",
            id="source-relative-yaml",
        ),
        pytest.param(
            "Path(__file__).parent / 'result.json'",
            id="source-relative-json",
        ),
        pytest.param(
            "Path(__file__).parent / 'runtime.log'",
            id="source-relative-log",
        ),
        pytest.param("data_path", id="dynamic-data-path"),
    ],
)
def test_ordinary_file_open_remains_a_behavioral_file_oracle(
    path_expression: str,
) -> None:
    definition = _synthetic_test_definition(
        f"""
        def test_data_contract():
            payload = open({path_expression}).read()
            assert "expected value" in payload
        """,
    )

    assert not definition.weak_reasons
    assert _behavioral_signal_reasons(definition) == (
        "runtime value assertion",
    )


@pytest.mark.test_evidence("invariant_only")
def test_domain_owned_active_test_paths_validate_without_raising() -> None:
    _validate_durable_test_paths(
        [
            Path("tests/benchmarks/test_scenario_performance.py"),
            Path("tests/unit/checkpoint/test_integrity.py"),
            Path("tests/integration/runtime/test_execution_policy.py"),
        ],
    )
