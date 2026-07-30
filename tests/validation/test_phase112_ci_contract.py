"""Structural repository checks for the Phase 112 CI partition contract."""

from __future__ import annotations

import ast
import json
import subprocess
from itertools import combinations
from pathlib import Path

import pytest
import yaml

import scripts.run_pytest_partition as partition_runner
from scripts.run_pytest_partition import (
    AUDITED_PARTITIONS,
    BENCHMARK_POLICY_TEST_FILES,
    PARTITION_SPECS,
    TERRAIN_TEST_FILES,
    _junit_evidence_error,
    _pytest_command,
    _validated_exit_code,
    _write_node_id_argfile,
    run_partition,
    select_shard,
)
from scripts.validate_docs_links import (
    _has_expected_missing_anchor_diagnostic,
)
from scripts.validate_test_evidence import (
    TestDefinition as _EvidenceTestDefinition,
    _definitions_from_tree,
    _has_direct_signal,
    _has_explicit_structural_marker,
    _invariant_contract_violations,
    _is_shape_or_nonnull_assertion,
    _refresh_derivation_command,
)
from scripts.validate_test_partitions import validate_partition_sets


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_ROOT = ROOT / ".github" / "workflows"


def _workflow(name: str) -> dict[str, object]:
    return yaml.load(
        (WORKFLOW_ROOT / name).read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )


def _workflow_text(name: str) -> str:
    return (WORKFLOW_ROOT / name).read_text(encoding="utf-8")


def test_partition_selectors_encode_the_exact_disjoint_contract() -> None:
    assert AUDITED_PARTITIONS == (
        "standard",
        "slow-only",
        "benchmark-only",
        "slow-benchmark",
        "api",
        "e2e",
    )
    assert PARTITION_SPECS["standard"].marker_expression == ("not slow and not benchmark")
    assert PARTITION_SPECS["slow-only"].marker_expression == ("slow and not benchmark")
    assert PARTITION_SPECS["benchmark-only"].marker_expression == ("benchmark and not slow")
    assert PARTITION_SPECS["slow-benchmark"].marker_expression == ("slow and benchmark")
    for name in AUDITED_PARTITIONS[:4]:
        assert PARTITION_SPECS[name].ignored_paths == ("tests/api", "tests/e2e")
    assert PARTITION_SPECS["api"].paths == ("tests/api",)
    assert PARTITION_SPECS["e2e"].paths == ("tests/e2e",)
    assert PARTITION_SPECS["terrain"].paths == TERRAIN_TEST_FILES
    assert TERRAIN_TEST_FILES == (
        "tests/unit/test_phase_15a_pipeline_heightmap.py",
        "tests/unit/test_phase_15b_classification_infrastructure.py",
        "tests/unit/test_phase_15c_bathymetry.py",
        "tests/unit/test_phase_15d_integration.py",
    )
    assert BENCHMARK_POLICY_TEST_FILES == (
        "tests/benchmarks/test_benchmarks.py",
        "tests/benchmarks/test_flag_impact.py",
    )
    assert PARTITION_SPECS["benchmark-policy"].paths == (BENCHMARK_POLICY_TEST_FILES)
    assert "benchmark-policy" not in AUDITED_PARTITIONS


def test_shards_are_deterministic_disjoint_and_exact(
    tmp_path: Path,
) -> None:
    module_sizes = {
        "tests/a.py": 5,
        "tests/b.py": 4,
        "tests/c.py": 4,
        "tests/d.py": 2,
        "tests/e.py": 2,
    }
    source = tuple(
        f"{module_id}::test_case[{index:02d}]"
        for module_id, node_count in module_sizes.items()
        for index in range(node_count)
    )
    first = [
        select_shard(source, shard_index=index, shard_count=4)
        for index in range(4)
    ]
    second = [
        select_shard(
            tuple(reversed(source)),
            shard_index=index,
            shard_count=4,
        )
        for index in range(4)
    ]
    plan = partition_runner._plan_shards(source, shard_count=4)

    assert first == second == list(plan.shards)
    assert plan.strategy == "module-affine-lpt"
    assert plan.module_ids == tuple(module_sizes)
    assert plan.split_module_ids == ()
    assert [len(shard) for shard in first] == [5, 4, 4, 4]
    assert {
        node_id.partition("::")[0] for node_id in first[0]
    } == {"tests/a.py"}
    assert {
        node_id.partition("::")[0] for node_id in first[1]
    } == {"tests/b.py"}
    assert {
        node_id.partition("::")[0] for node_id in first[2]
    } == {"tests/c.py"}
    assert {
        node_id.partition("::")[0] for node_id in first[3]
    } == {"tests/d.py", "tests/e.py"}
    assert all(first)
    for left, right in combinations(first, 2):
        assert set(left).isdisjoint(right)
    assert set().union(*(set(shard) for shard in first)) == set(source)
    module_owners: dict[str, set[int]] = {}
    for index, shard in enumerate(first):
        for node_id in shard:
            module_owners.setdefault(
                node_id.partition("::")[0],
                set(),
            ).add(index)
    assert all(len(owners) == 1 for owners in module_owners.values())

    fallback_source = tuple(
        f"tests/example.py::test_case[{index:02d}]"
        for index in range(17)
    )
    fallback = partition_runner._plan_shards(
        fallback_source,
        shard_count=4,
    )
    assert fallback.strategy == "balanced-node-fallback"
    assert fallback.module_ids == ("tests/example.py",)
    assert fallback.split_module_ids == ("tests/example.py",)
    assert [len(shard) for shard in fallback.shards] == [5, 4, 4, 4]
    assert fallback.shards == (
        fallback_source[:5],
        fallback_source[5:9],
        fallback_source[9:13],
        fallback_source[13:],
    )
    assert all(fallback.shards)

    for node_count, shard_count in (
        (0, 1),
        (0, 4),
        (1, 1),
        (1, 4),
        (3, 5),
        (4, 4),
        (5, 4),
        (17, 4),
    ):
        nodes = tuple(
            f"tests/table.py::test_case[{index:02d}]"
            for index in range(node_count)
        )
        shards = [
            select_shard(
                tuple(reversed(nodes)),
                shard_index=index,
                shard_count=shard_count,
            )
            for index in range(shard_count)
        ]
        lengths = [len(shard) for shard in shards]
        assert tuple(node for shard in shards for node in shard) == nodes
        assert sum(lengths) == node_count
        assert max(lengths) - min(lengths) <= 1
        assert all(tuple(sorted(shard)) == shard for shard in shards)
        for left, right in combinations(shards, 2):
            assert set(left).isdisjoint(right)
        if (node_count, shard_count) == (3, 5):
            assert lengths == [1, 1, 1, 0, 0]

    with pytest.raises(ValueError, match="positive"):
        select_shard(source, shard_index=0, shard_count=0)
    with pytest.raises(ValueError, match="shard_index"):
        select_shard(source, shard_index=-1, shard_count=4)
    with pytest.raises(ValueError, match="shard_index"):
        select_shard(source, shard_index=4, shard_count=4)
    with pytest.raises(ValueError, match="unique"):
        select_shard(
            (source[0], source[0]),
            shard_index=0,
            shard_count=1,
        )
    with pytest.raises(
        partition_runner.PartitionCollectionError,
        match="duplicate",
    ):
        partition_runner._node_id_lines(
            "tests/example.py::test_dup\n"
            "tests/example.py::test_dup",
        )

    large_shard = tuple(f"tests/example.py::test_case[long parameter {index:05d}]" for index in range(10_000))
    argument_path = tmp_path / "selection.args"
    _write_node_id_argfile(argument_path, large_shard)
    assert tuple(argument_path.read_text(encoding="utf-8").splitlines()) == (large_shard)
    command = _pytest_command(f"@{argument_path.resolve()}")
    assert len(command) == 8
    assert len(command[-1]) < 512
    for index, invalid in enumerate(
        (
            "other/example.py::test_case",
            "tests/example.py",
            "tests/example.py::test_case\n--collect-only",
            "tests/example.py::test_case\r--collect-only",
        ),
    ):
        invalid_path = tmp_path / f"bad-{index}.args"
        with pytest.raises(
            partition_runner.PartitionCollectionError,
            match="invalid pytest node ID",
        ):
            _write_node_id_argfile(invalid_path, (invalid,))
        assert not invalid_path.exists()


def test_partition_audit_rejects_overlap_and_missing_nodes() -> None:
    valid = {name: (f"tests/{name}.py::test_member",) for name in AUDITED_PARTITIONS}
    superset = tuple(node_id for nodes in valid.values() for node_id in nodes)
    validate_partition_sets(superset, valid)

    overlapping = dict(valid)
    overlapping["api"] = valid["api"] + valid["standard"]
    with pytest.raises(ValueError, match="overlap"):
        validate_partition_sets(superset, overlapping)

    missing = dict(valid)
    missing["e2e"] = ()
    with pytest.raises(ValueError, match="empty"):
        validate_partition_sets(superset, missing)


def test_partition_result_validation_rejects_skips_and_missing_outcomes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete = {
        "passed": 3,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "xfailed": 0,
        "xpassed": 0,
        "warnings": 0,
        "deselected": 0,
        "summary_found": True,
    }
    assert _validated_exit_code(
        pytest_exit_code=0,
        counts=complete,
        selected_count=3,
        forbid_skips=True,
    ) == (0, None)

    skipped = {**complete, "passed": 2, "skipped": 1}
    code, message = _validated_exit_code(
        pytest_exit_code=0,
        counts=skipped,
        selected_count=3,
        forbid_skips=True,
    )
    assert code == 4
    assert message is not None and "forbids skipped" in message

    incomplete = {**complete, "passed": 2}
    code, message = _validated_exit_code(
        pytest_exit_code=0,
        counts=incomplete,
        selected_count=3,
        forbid_skips=False,
    )
    assert code == 4
    assert message is not None and "every selected node" in message

    falsely_green = {**complete, "passed": 2, "failed": 1}
    code, message = _validated_exit_code(
        pytest_exit_code=0,
        counts=falsely_green,
        selected_count=3,
        forbid_skips=False,
    )
    assert code == 4
    assert message is not None and "reported failed=1 errors=0" in message

    junit_path = tmp_path / "junit.xml"
    junit_path.write_text(
        '<testsuites><testsuite tests="3" failures="0" errors="0" skipped="0"/></testsuites>',
        encoding="utf-8",
    )
    assert (
        _junit_evidence_error(
            junit_path,
            selected_count=3,
            forbid_skips=True,
        )
        is None
    )
    assert "every selected node" in (
        _junit_evidence_error(
            junit_path,
            selected_count=4,
            forbid_skips=True,
        )
        or ""
    )
    assert "non-empty JUnit" in (
        _junit_evidence_error(
            tmp_path / "missing.xml",
            selected_count=3,
            forbid_skips=True,
        )
        or ""
    )

    junit_path.write_text(
        '<testsuites><testsuite tests="3" failures="1" errors="0" skipped="0"/></testsuites>',
        encoding="utf-8",
    )
    assert "unsuccessful outcomes" in (
        _junit_evidence_error(
            junit_path,
            selected_count=3,
            forbid_skips=False,
        )
        or ""
    )

    stale_junit = tmp_path / "stale-junit.xml"
    stale_junit.write_text(
        '<testsuites><testsuite tests="1" failures="0" errors="0" skipped="0"/></testsuites>',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        partition_runner,
        "collect_partition_node_ids",
        lambda _partition, *, root: ("tests/example.py::test_case",),
    )
    monkeypatch.setattr(
        partition_runner.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="1 passed in 0.01s",
            stderr="",
        ),
    )
    assert (
        run_partition(
            "api",
            manifest_path=tmp_path / "manifest.json",
            junit_path=stale_junit,
            shard_index=0,
            shard_count=1,
            timeout_seconds=30,
            forbid_skips=True,
            root=tmp_path,
        )
        == 4
    )
    result = json.loads(
        (tmp_path / "result.json").read_text(encoding="utf-8"),
    )
    assert result["status"] == "failed"
    assert "non-empty JUnit" in result["error"]
    assert not stale_junit.exists()

    timeout_dir = tmp_path / "execution-timeout"
    timeout_manifest = timeout_dir / "manifest.json"
    timeout_junit = timeout_dir / "junit.xml"

    def time_out(
        command: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        assert kwargs["timeout"] == 30
        raise subprocess.TimeoutExpired(
            command,
            30,
            output="partial execution output",
        )

    monkeypatch.setattr(partition_runner.subprocess, "run", time_out)
    assert (
        run_partition(
            "api",
            manifest_path=timeout_manifest,
            junit_path=timeout_junit,
            shard_index=0,
            shard_count=1,
            timeout_seconds=30,
            forbid_skips=True,
            root=tmp_path,
        )
        == 124
    )
    timeout_result = json.loads(
        (timeout_dir / "result.json").read_text(encoding="utf-8"),
    )
    assert timeout_result["status"] == "timeout"
    assert timeout_result["exit_code"] == 124
    assert "counts" not in timeout_result
    assert timeout_manifest.is_file()
    assert (timeout_dir / "selection.args").is_file()
    assert not timeout_junit.exists()
    assert timeout_result["sharding"] == {
        "module_count": 1,
        "module_ids": ["tests/example.py"],
        "selected_module_count": 1,
        "selected_module_ids": ["tests/example.py"],
        "split_module_ids": [],
        "strategy": "module-affine-lpt",
    }


def test_unsharded_partition_executes_exact_manifest_node_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The execution command must be bound to the manifest even without sharding."""
    selected = (
        "tests/example.py::test_first",
        "tests/example.py::test_second",
    )
    monkeypatch.setattr(
        partition_runner,
        "collect_partition_node_ids",
        lambda _partition, *, root: selected,
    )
    commands: list[list[str]] = []

    def execute(
        command: list[str],
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        junit_argument = next(argument for argument in command if argument.startswith("--junitxml="))
        Path(junit_argument.removeprefix("--junitxml=")).write_text(
            '<testsuites><testsuite tests="2" failures="0" errors="0" skipped="0"/></testsuites>',
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout="2 passed in 0.01s",
            stderr="",
        )

    monkeypatch.setattr(partition_runner.subprocess, "run", execute)
    manifest_path = tmp_path / "manifest.json"
    junit_path = tmp_path / "junit.xml"

    assert (
        run_partition(
            "api",
            manifest_path=manifest_path,
            junit_path=junit_path,
            shard_index=0,
            shard_count=1,
            timeout_seconds=30,
            forbid_skips=True,
            root=tmp_path,
        )
        == 0
    )
    argument_path = tmp_path / "selection.args"
    assert (
        tuple(
            argument_path.read_text(encoding="utf-8").splitlines(),
        )
        == selected
    )
    assert commands == [
        _pytest_command(
            "--tb=short",
            "-q",
            f"--junitxml={junit_path}",
            f"@{argument_path.resolve()}",
        ),
    ]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["collection_timeout_seconds"] == 300
    assert manifest["shard"]["selected_node_ids"] == list(selected)
    assert manifest["sharding"] == {
        "module_count": 1,
        "module_ids": ["tests/example.py"],
        "selected_module_count": 1,
        "selected_module_ids": ["tests/example.py"],
        "split_module_ids": [],
        "strategy": "module-affine-lpt",
    }
    result = json.loads(
        (tmp_path / "result.json").read_text(encoding="utf-8"),
    )
    assert result["status"] == "passed"

    empty_dir = tmp_path / "empty"
    empty_manifest = empty_dir / "manifest.json"
    empty_junit = empty_dir / "junit.xml"
    assert (
        partition_runner.main(
            [
                "api",
                "--manifest",
                str(empty_manifest),
                "--junit",
                str(empty_junit),
                "--shard-index",
                "2",
                "--shard-count",
                "3",
                "--forbid-skips",
                "--timeout-seconds",
                "30",
            ],
        )
        == 3
    )
    empty_result = json.loads(
        (empty_dir / "result.json").read_text(encoding="utf-8"),
    )
    assert empty_result["status"] == "collection_error"
    assert "api shard 3/3 is empty" in empty_result["error"]
    assert not empty_manifest.exists()
    assert not empty_junit.exists()
    assert not (empty_dir / "selection.args").exists()
    assert len(commands) == 1


def test_collection_timeout_writes_failure_result_and_removes_stale_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bounded collection failure must retain current machine-readable evidence."""
    manifest_path = tmp_path / "manifest.json"
    junit_path = tmp_path / "junit.xml"
    argument_path = tmp_path / "selection.args"
    for path in (manifest_path, junit_path, argument_path):
        path.write_text("stale", encoding="utf-8")

    def time_out(
        command: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        assert kwargs["timeout"] == partition_runner.COLLECTION_TIMEOUT_SECONDS
        raise subprocess.TimeoutExpired(
            command,
            partition_runner.COLLECTION_TIMEOUT_SECONDS,
            output="partial collection output",
        )

    monkeypatch.setattr(partition_runner.subprocess, "run", time_out)
    exit_code = partition_runner.main(
        [
            "api",
            "--manifest",
            str(manifest_path),
            "--junit",
            str(junit_path),
            "--timeout-seconds",
            "30",
        ]
    )

    assert exit_code == 3
    assert not manifest_path.exists()
    assert not junit_path.exists()
    assert not argument_path.exists()
    result = json.loads(
        (tmp_path / "result.json").read_text(encoding="utf-8"),
    )
    assert result["status"] == "collection_error"
    assert result["collection_timeout_seconds"] == 300
    assert "collection timed out after 300 seconds" in result["error"]


def test_weak_shape_classifier_requires_the_whole_assertion_to_be_weak() -> None:
    weak = ast.parse(
        "assert isinstance(result, Result) and result.payload is not None",
    ).body[0]
    mixed = ast.parse(
        "assert isinstance(result, Result) and result.status == 'complete'",
    ).body[0]
    exact_null = ast.parse("assert result is None").body[0]

    assert isinstance(weak, ast.Assert)
    assert isinstance(mixed, ast.Assert)
    assert isinstance(exact_null, ast.Assert)
    assert _is_shape_or_nonnull_assertion(weak.test)
    assert not _is_shape_or_nonnull_assertion(mixed.test)
    assert not _is_shape_or_nonnull_assertion(exact_null.test)

    allowed_node = ast.parse(
        "def test_missing_unit_no_error():\n    pass",
    ).body[0]
    unnamed_invariant_node = ast.parse(
        "def test_update_delegates():\n    pass",
    ).body[0]
    behavioral_claim_node = ast.parse(
        "def test_missing_engine_no_error():\n    pass",
    ).body[0]
    assert isinstance(allowed_node, ast.FunctionDef)
    assert isinstance(unnamed_invariant_node, ast.FunctionDef)
    assert isinstance(behavioral_claim_node, ast.FunctionDef)

    def evidence_definition(
        node: ast.FunctionDef,
        *,
        qualified_name: str,
    ) -> _EvidenceTestDefinition:
        return _EvidenceTestDefinition(
            path="tests/example.py",
            qualified_name=qualified_name,
            node=node,
            module_definitions={},
            class_definitions={},
            local_definitions={},
        )

    assert not _invariant_contract_violations(
        evidence_definition(
            allowed_node,
            qualified_name="TestEdgeCases::test_missing_unit_no_error",
        ),
    )
    assert _invariant_contract_violations(
        evidence_definition(
            unnamed_invariant_node,
            qualified_name="TestEngine::test_update_delegates",
        ),
    ) == ("does not explicitly name a no-raise, no-error, no-crash, or no-op invariant",)
    assert _invariant_contract_violations(
        evidence_definition(
            behavioral_claim_node,
            qualified_name=("TestProductionWiring::test_missing_engine_no_error"),
        ),
    ) == ("name/docstring claims behavioral evidence (wiring, production)",)

    exact_structural = ast.parse(
        "@pytest.mark.structural\ndef test_structural_contract():\n    assert runtime.state == expected\n",
    ).body[0]
    called_structural = ast.parse(
        "@pytest.mark.structural()\ndef test_structural_contract():\n    assert runtime.state == expected\n",
    ).body[0]
    unrelated_structural = ast.parse(
        "@custom.mark.structural\ndef test_behavioral_contract():\n    assert runtime.state == expected\n",
    ).body[0]
    assert isinstance(exact_structural, ast.FunctionDef)
    assert isinstance(called_structural, ast.FunctionDef)
    assert isinstance(unrelated_structural, ast.FunctionDef)
    assert _has_explicit_structural_marker(exact_structural)
    assert _has_explicit_structural_marker(called_structural)
    assert not _has_explicit_structural_marker(unrelated_structural)

    structural_class_tree = ast.parse(
        "@pytest.mark.structural\n"
        "class TestRegistry:\n"
        "    @pytest.mark.parametrize('owner', ['clock'])\n"
        "    def test_owner(self, owner):\n"
        "        assert owner in {'clock'}\n",
    )
    structural_class = structural_class_tree.body[0]
    assert isinstance(structural_class, ast.ClassDef)
    assert _has_explicit_structural_marker(structural_class)
    indexed = _definitions_from_tree(
        "tests/example.py",
        structural_class_tree,
    )
    inherited = indexed[
        ("tests/example.py", "TestRegistry::test_owner")
    ]
    assert inherited.enclosing_structural
    assert inherited.weak_reasons == ("explicit structural marker",)


def test_helper_trace_uses_executable_lexical_scope() -> None:
    module_helper = ast.parse(
        "def check():\n    assert False",
    ).body[0]
    class_helper = ast.parse(
        "def check(self):\n    return None",
    ).body[0]
    test_node = ast.parse(
        "def test_case(self):\n    def local_check():\n        assert True\n    self.check()\n    local_check()",
    ).body[0]

    assert isinstance(module_helper, ast.FunctionDef)
    assert isinstance(class_helper, ast.FunctionDef)
    assert isinstance(test_node, ast.FunctionDef)
    assert not _has_direct_signal(test_node)
    definition = _EvidenceTestDefinition(
        path="tests/example.py",
        qualified_name="TestCase::test_case",
        node=test_node,
        module_definitions={"check": module_helper},
        class_definitions={"check": class_helper},
        local_definitions={"local_check": test_node.body[0]},
    )
    assert definition.called_helpers_with_signal == ("local_check",)


def test_evidence_metadata_refresh_preserves_reviewed_disposition(
    tmp_path: Path,
) -> None:
    ledger_path = tmp_path / "weak_oracles.json"
    entry = {
        "classification": "structural_only",
        "node_id": "tests/example.py::test_shape_only",
        "rationale": "reviewed rationale",
        "strongest_oracle": "shape-only assertion",
    }
    ledger_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "weak_oracles",
                "derivation_command": "old command",
                "entries": [entry],
            }
        ),
        encoding="utf-8",
    )

    _refresh_derivation_command(ledger_path, "fresh command")

    refreshed = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert refreshed["derivation_command"] == "fresh command"
    assert refreshed["entries"] == [entry]


def test_required_pull_request_and_main_jobs_are_unconditional() -> None:
    test_workflow = _workflow("test.yml")
    lint_workflow = _workflow("lint.yml")
    docs_workflow = _workflow("docs.yml")
    benchmark_workflow = _workflow("benchmark.yml")

    for workflow in (
        test_workflow,
        lint_workflow,
        docs_workflow,
        benchmark_workflow,
    ):
        triggers = workflow["on"]
        assert triggers["push"]["branches"] == ["main"]
        assert triggers["pull_request"]["branches"] == ["main"]

    for workflow, required_jobs in (
        (test_workflow, ("partition-audit", "python", "terrain", "frontend")),
        (lint_workflow, ("python", "frontend")),
        (docs_workflow, ("validate",)),
        (benchmark_workflow, ("policy", "easting")),
    ):
        for job_name in required_jobs:
            assert "if" not in workflow["jobs"][job_name]

    superset_command = "uv sync --locked --extra dev --extra api --extra terrain --extra mcp"
    test_run_commands = [
        step["run"] for job in test_workflow["jobs"].values() for step in job["steps"] if "run" in step
    ]
    assert test_run_commands.count(superset_command) == 2

    test_text = _workflow_text("test.yml")
    assert "standard" in test_text
    assert "api" in test_text
    assert "e2e" in test_text
    assert "run_pytest_partition.py terrain" in test_text
    assert "validate_test_partitions.py" in test_text
    assert "uv sync --locked --extra dev --extra terrain" in test_text
    assert test_text.count("--forbid-skips") == 2

    lint_text = _workflow_text("lint.yml")
    assert "uv run --no-sync ruff check stochastic_warfare/ api/ tests/ scripts/" in lint_text

    docs_text = _workflow_text("docs.yml")
    assert "scripts/validate_docs_links.py" in docs_text
    assert "mkdocs build --strict" in docs_text
    deploy = docs_workflow["jobs"]["deploy"]
    assert deploy["needs"] == "validate"
    assert deploy["if"] == ("github.event_name == 'push' && github.ref == 'refs/heads/main'")
    assert deploy["permissions"] == {"contents": "write"}

    exact_diagnostic = (
        "WARNING - Doc file 'index.md' contains a link "
        "'target.md#missing', but the doc 'target.md' does not contain "
        "an anchor '#missing'."
    )
    assert _has_expected_missing_anchor_diagnostic(exact_diagnostic)
    assert not _has_expected_missing_anchor_diagnostic(
        "strict build failed because a required plugin is missing",
    )


def test_extended_partitions_are_weekly_manual_sharded_and_bounded() -> None:
    workflow = _workflow("extended-tests.yml")
    triggers = workflow["on"]
    assert triggers["schedule"] == [{"cron": "17 6 * * 1"}]
    assert "workflow_dispatch" in triggers

    matrix = workflow["jobs"]["marker-partition"]["strategy"]["matrix"]
    configured = matrix["include"]
    expected_shards = {
        "slow-only": (4, 4200),
        "benchmark-only": (3, 2400),
        "slow-benchmark": (1, 4200),
    }
    assert len(configured) == sum(
        shard_count for shard_count, _timeout in expected_shards.values()
    )
    assert {
        (entry["partition"], int(entry["shard_index"]))
        for entry in configured
    } == {
        (partition, shard_index)
        for partition, (shard_count, _timeout) in expected_shards.items()
        for shard_index in range(shard_count)
    }
    for entry in configured:
        shard_count, timeout_seconds = expected_shards[entry["partition"]]
        assert int(entry["shard_count"]) == shard_count
        assert int(entry["timeout_seconds"]) == timeout_seconds
        assert 0 <= int(entry["shard_index"]) < shard_count

    job_timeout_seconds = (
        int(workflow["jobs"]["marker-partition"]["timeout-minutes"])
        * 60
    )
    assert (
        job_timeout_seconds
        - max(int(entry["timeout_seconds"]) for entry in configured)
        >= 1200
    )
    assert all("if" not in job for job in workflow["jobs"].values())
    superset_command = "uv sync --locked --extra dev --extra api --extra terrain --extra mcp"
    run_commands = [step["run"] for job in workflow["jobs"].values() for step in job["steps"] if "run" in step]
    assert run_commands.count(superset_command) == 2
    workflow_text = _workflow_text("extended-tests.yml")
    assert '--shard-count "${{ matrix.shard_count }}"' in workflow_text
    assert "--forbid-skips" in workflow_text


def test_every_python_evidence_upload_runs_after_failure() -> None:
    for workflow_name in (
        "test.yml",
        "extended-tests.yml",
        "benchmark.yml",
    ):
        workflow = _workflow(workflow_name)
        upload_steps = [
            step
            for job in workflow["jobs"].values()
            for step in job["steps"]
            if str(step.get("uses", "")).startswith("actions/upload-artifact@")
        ]
        assert upload_steps
        assert all(step.get("if") == "always()" for step in upload_steps)
        assert all(step["with"].get("if-no-files-found") == "error" for step in upload_steps)


def test_focused_benchmark_policy_retains_fail_closed_pytest_evidence() -> None:
    workflow = _workflow("benchmark.yml")
    policy = workflow["jobs"]["policy"]
    run_steps = [step["run"] for step in policy["steps"] if "run" in step]
    command = "\n".join(run_steps)

    assert "scripts/run_pytest_partition.py benchmark-policy" in command
    assert "--manifest artifacts/benchmark-policy/manifest.json" in command
    assert "--junit artifacts/benchmark-policy/junit.xml" in command
    assert "--forbid-skips" in command
    assert "--timeout-seconds 600" in command

    uploads = [step for step in policy["steps"] if str(step.get("uses", "")).startswith("actions/upload-artifact@")]
    assert len(uploads) == 1
    assert uploads[0]["if"] == "always()"
    assert uploads[0]["with"]["path"] == "artifacts/benchmark-policy/"
    assert uploads[0]["with"]["if-no-files-found"] == "error"


def test_frontend_tests_retain_machine_readable_results_after_failure() -> None:
    workflow = _workflow("test.yml")
    frontend = workflow["jobs"]["frontend"]
    run_steps = [step["run"] for step in frontend["steps"] if "run" in step]
    command = "\n".join(run_steps)

    assert "npm test --" in command
    assert "--reporter=default" in command
    assert "--reporter=junit" in command
    assert "--outputFile.junit=../artifacts/frontend/junit.xml" in command

    uploads = [step for step in frontend["steps"] if str(step.get("uses", "")).startswith("actions/upload-artifact@")]
    assert len(uploads) == 1
    assert uploads[0]["if"] == "always()"
    assert uploads[0]["with"]["path"] == "artifacts/frontend/"
    assert uploads[0]["with"]["if-no-files-found"] == "error"
