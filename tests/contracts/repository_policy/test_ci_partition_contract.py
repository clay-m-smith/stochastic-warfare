"""Structural repository checks for the Phase 112 CI partition contract."""

from __future__ import annotations

import ast
import json
import os
import py_compile
import subprocess
import sys
from itertools import combinations
from pathlib import Path

import pytest
import yaml

import scripts.run_pytest_partition as partition_runner
from scripts.generate_extended_test_matrix import (
    EXTENDED_PARTITION_POLICIES,
    build_extended_matrix,
)
from scripts.run_pytest_partition import (
    AUDITED_PARTITIONS,
    BENCHMARK_POLICY_TEST_FILES,
    PARTITION_SPECS,
    TERRAIN_TEST_FILES,
    _junit_evidence_error,
    _pytest_command,
    _validated_exit_code,
    _write_node_id_argfile,
    load_audit_manifest,
    repository_revision,
    run_partition,
    select_shard,
    validate_audit_manifest_payload,
)
from scripts.validate_docs_links import (
    _has_expected_missing_anchor_diagnostic,
)
from scripts.validate_test_evidence import (
    TestDefinition as _EvidenceTestDefinition,
    _definitions_from_tree,
    _has_direct_signal,
    _invariant_contract_violations,
    _is_shape_or_nonnull_assertion,
    _validate_source_annotations,
    definition_id_from_node_id,
)
from scripts.validate_test_partitions import (
    build_audit_payload,
    validate_partition_sets,
)

pytestmark = pytest.mark.test_evidence("structural_only")


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_ROOT = ROOT / ".github" / "workflows"
TEST_REVISION = {
    "commit": "a" * 40,
    "dirty": False,
    "worktree_fingerprint": "b" * 64,
}
PYTEST_CONFIG_CASES = (
    (
        "pytest.toml",
        '[pytest]\npython_files = ["impossible_pattern_*.py"]\n',
    ),
    (
        ".pytest.toml",
        '[pytest]\npython_files = ["impossible_pattern_*.py"]\n',
    ),
    ("pytest.ini", "[pytest]\npython_files = impossible_pattern_*.py\n"),
    (".pytest.ini", "[pytest]\npython_files = impossible_pattern_*.py\n"),
    (
        "pyproject.toml",
        "[tool.pytest.ini_options]\n"
        'python_files = ["impossible_pattern_*.py"]\n',
    ),
    ("tox.ini", "[pytest]\npython_files = impossible_pattern_*.py\n"),
    ("setup.cfg", "[tool:pytest]\npython_files = impossible_pattern_*.py\n"),
)


def _workflow(name: str) -> dict[str, object]:
    return yaml.load(
        (WORKFLOW_ROOT / name).read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )


def _workflow_text(name: str) -> str:
    return (WORKFLOW_ROOT / name).read_text(encoding="utf-8")


def _synthetic_audit_payload(
    partitions: dict[str, tuple[str, ...]] | None = None,
    revision: dict[str, object] | None = None,
) -> dict[str, object]:
    selected = partitions or {
        name: (f"tests/{name}.py::test_member",)
        for name in AUDITED_PARTITIONS
    }
    superset = tuple(sorted(node_id for nodes in selected.values() for node_id in nodes))
    return build_audit_payload(
        superset,
        selected,
        revision=TEST_REVISION if revision is None else revision,
    )


def _git(repo: Path, *arguments: str) -> bytes:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    return completed.stdout


def _initialize_partition_revision_repo(
    tmp_path: Path,
) -> tuple[Path, dict[str, Path]]:
    repo = tmp_path / "partition-revision-repo"
    files = {
        ".gitattributes": "*.py text eol=lf\n",
        ".gitignore": (
            "/conftest.py\n"
            "/pytest.toml\n"
            "/.pytest.toml\n"
            "/pytest.ini\n"
            "/.pytest.ini\n"
            "/pyproject.toml\n"
            "/tox.ini\n"
            "/setup.cfg\n"
            "/pydantic.py\n"
            "/pydantic/\n"
            "/helpers/plugin.py\n"
            "/selection.flag\n"
            "/ignored_root\n"
            "/evil.egg-info/\n"
            "/build/\n"
            "/data/terrain_cache/\n"
            "__pycache__/\n"
            ".pytest_cache/\n"
        ),
        "README.md": "# Partition revision fixture\n",
        "api/__init__.py": "\n",
        "api/main.py": "APP = 'fixture'\n",
        "data/scenario.yaml": "name: fixture\n",
        "scripts/runner.py": "VALUE = 'runner'\n",
        "stochastic_warfare/__init__.py": "\n",
        "stochastic_warfare/runtime.py": "VALUE = 'runtime'\n",
        "tests/__init__.py": "\n",
        "tests/artifact_support.py": '"""Fixture plugin."""\n',
        "tests/test_sample.py": (
            "def test_sample() -> None:\n"
            "    assert True\n"
        ),
    }
    paths: dict[str, Path] = {}
    for relative, content in files.items():
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        paths[relative] = path
    _git(repo, "init", "--quiet")
    _git(repo, "config", "user.name", "Partition Revision Test")
    _git(
        repo,
        "config",
        "user.email",
        "partition-revision@example.invalid",
    )
    _git(repo, "config", "core.autocrlf", "false")
    _git(repo, "add", ".")
    _git(repo, "commit", "--quiet", "-m", "partition revision fixture")
    return repo, paths


def _collect_fixture_nodes(
    repo: Path,
    *,
    environment: dict[str, str] | None = None,
) -> tuple[int, tuple[str, ...]]:
    completed = subprocess.run(
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
            "tests",
        ],
        cwd=repo,
        check=False,
        capture_output=True,
        env=environment,
        text=True,
    )
    node_ids = tuple(
        line
        for line in completed.stdout.splitlines()
        if line.startswith("tests/") and "::" in line
    )
    return completed.returncode, node_ids


def _unisolated_fixture_environment(
    *,
    plugin_autoload: bool,
) -> dict[str, str]:
    environment = os.environ.copy()
    for variable in (
        "PYTHONHOME",
        "PYTHONPATH",
        "PYTHONPYCACHEPREFIX",
        "PYTEST_ADDOPTS",
        "PYTEST_PLUGINS",
    ):
        environment.pop(variable, None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONHASHSEED"] = "0"
    environment["PYTHONNOUSERSITE"] = "1"
    if plugin_autoload:
        environment.pop("PYTEST_DISABLE_PLUGIN_AUTOLOAD", None)
    else:
        environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    return environment


def _validate_synthetic_evidence(source: str) -> tuple[set[str], int, int, int]:
    definitions = _definitions_from_tree(
        "tests/example.py",
        ast.parse(source),
    )
    values = list(definitions.values())
    return _validate_source_annotations(
        no_direct=[item for item in values if not item.direct_signal],
        weak=[item for item in values if item.weak_reasons],
        definitions=definitions,
        collected_definition_ids={item.definition_id for item in values},
    )


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
        "tests/unit/terrain/test_heightmap_pipeline.py",
        "tests/unit/terrain/test_classification_infrastructure.py",
        "tests/unit/terrain/test_bathymetry_pipeline.py",
        "tests/unit/terrain/test_pipeline_integration.py",
    )
    assert BENCHMARK_POLICY_TEST_FILES == (
        "tests/benchmarks/test_benchmarks.py",
        "tests/benchmarks/test_flag_impact.py",
    )
    assert PARTITION_SPECS["benchmark-policy"].paths == (BENCHMARK_POLICY_TEST_FILES)
    assert "benchmark-policy" not in AUDITED_PARTITIONS


@pytest.mark.test_evidence("behavioral_oracle")
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
    assert len(command) == 12
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


@pytest.mark.test_evidence("behavioral_oracle")
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


@pytest.mark.test_evidence("behavioral_oracle")
def test_revision_bound_audit_manifest_fails_closed_on_drift() -> None:
    payload = _synthetic_audit_payload()
    validated = validate_audit_manifest_payload(
        payload,
        current_revision=TEST_REVISION,
        manifest_sha256="c" * 64,
    )
    assert validated.revision == TEST_REVISION
    assert set(validated.partitions) == set(AUDITED_PARTITIONS)

    revision_drift = json.loads(json.dumps(payload))
    with pytest.raises(
        partition_runner.PartitionCollectionError,
        match="revision does not match",
    ):
        validate_audit_manifest_payload(
            revision_drift,
            current_revision={**TEST_REVISION, "commit": "d" * 40},
        )

    selector_drift = json.loads(json.dumps(payload))
    selector_drift["partitions"]["api"]["selector"]["paths"] = ["tests"]
    with pytest.raises(
        partition_runner.PartitionCollectionError,
        match="selector has drifted",
    ):
        validate_audit_manifest_payload(
            selector_drift,
            current_revision=TEST_REVISION,
        )

    digest_drift = json.loads(json.dumps(payload))
    digest_drift["partitions"]["api"]["node_ids_sha256"] = "0" * 64
    with pytest.raises(
        partition_runner.PartitionCollectionError,
        match="node_ids_sha256 is inconsistent",
    ):
        validate_audit_manifest_payload(
            digest_drift,
            current_revision=TEST_REVISION,
        )

    overlapping = {
        name: (f"tests/{name}.py::test_member",)
        for name in AUDITED_PARTITIONS
    }
    overlapping["api"] = overlapping["standard"]
    overlap_payload = build_audit_payload(
        tuple(sorted(set().union(*map(set, overlapping.values())))),
        overlapping,
        revision=TEST_REVISION,
    )
    with pytest.raises(
        partition_runner.PartitionCollectionError,
        match="overlap",
    ):
        validate_audit_manifest_payload(
            overlap_payload,
            current_revision=TEST_REVISION,
        )


@pytest.mark.test_evidence("behavioral_oracle")
def test_repository_revision_clean_checkout_is_stable(tmp_path: Path) -> None:
    repo, _files = _initialize_partition_revision_repo(tmp_path)

    first = repository_revision(repo)
    second = repository_revision(repo)

    assert first == second
    assert first["commit"] == _git(repo, "rev-parse", "HEAD").decode().strip()
    assert first["dirty"] is False
    assert len(str(first["worktree_fingerprint"])) == 64


@pytest.mark.test_evidence("behavioral_oracle")
@pytest.mark.parametrize(
    "index_flag",
    ("--assume-unchanged", "--skip-worktree"),
)
def test_repository_revision_rejects_hidden_index_flags(
    tmp_path: Path,
    index_flag: str,
) -> None:
    repo, files = _initialize_partition_revision_repo(tmp_path)
    relative = "tests/test_sample.py"
    _git(repo, "update-index", index_flag, "--", relative)
    files[relative].write_text(
        "def test_hidden_change() -> None:\n    assert False\n",
        encoding="utf-8",
    )

    assert _git(
        repo,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    ) == b""
    with pytest.raises(
        partition_runner.PartitionCollectionError,
        match="unsupported Git index flags",
    ):
        repository_revision(repo)


@pytest.mark.test_evidence("behavioral_oracle")
def test_repository_revision_rejects_hidden_mode_change(tmp_path: Path) -> None:
    repo, files = _initialize_partition_revision_repo(tmp_path)
    relative = "tests/test_sample.py"
    _git(repo, "config", "core.fileMode", "false")
    files[relative].chmod(0o755)

    assert _git(
        repo,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    ) == b""
    with pytest.raises(
        partition_runner.PartitionCollectionError,
        match="worktree modes differ from HEAD",
    ):
        repository_revision(repo)


@pytest.mark.test_evidence("behavioral_oracle")
def test_repository_revision_rejects_raw_filtered_byte_change(
    tmp_path: Path,
) -> None:
    repo, files = _initialize_partition_revision_repo(tmp_path)
    relative = "tests/test_sample.py"
    source = files[relative]
    source.write_bytes(source.read_bytes().replace(b"\n", b"\r\n"))
    _git(repo, "add", "--renormalize", "--", relative)

    assert b"\r\n" in source.read_bytes()
    assert _git(
        repo,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    ) == b""
    with pytest.raises(
        partition_runner.PartitionCollectionError,
        match="input bytes differ from HEAD",
    ):
        repository_revision(repo)


@pytest.mark.test_evidence("behavioral_oracle")
def test_dirty_repository_revision_binds_raw_filtered_bytes(
    tmp_path: Path,
) -> None:
    repo, files = _initialize_partition_revision_repo(tmp_path)
    unrelated = repo / "notes.txt"
    unrelated.write_text("constant dirty state\n", encoding="utf-8")
    before = repository_revision(repo)

    relative = "tests/test_sample.py"
    source = files[relative]
    source.write_bytes(source.read_bytes().replace(b"\n", b"\r\n"))
    _git(repo, "add", "--renormalize", "--", relative)
    assert _git(
        repo,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    ) == b"?? notes.txt\0"

    after = repository_revision(repo)

    assert before["dirty"] is after["dirty"] is True
    assert before["commit"] == after["commit"]
    assert before["worktree_fingerprint"] != after["worktree_fingerprint"]


@pytest.mark.test_evidence("behavioral_oracle")
@pytest.mark.parametrize(
    ("relative", "content"),
    (
        ("conftest.py", 'collect_ignore = ["tests/test_sample.py"]\n'),
        ("pydantic.py", "SHADOW = True\n"),
        ("pydantic/__init__.py", "SHADOW = True\n"),
    ),
)
def test_repository_revision_rejects_ignored_collection_inputs(
    tmp_path: Path,
    relative: str,
    content: str,
) -> None:
    repo, _files = _initialize_partition_revision_repo(tmp_path)
    ignored = repo / relative
    ignored.parent.mkdir(parents=True, exist_ok=True)
    ignored.write_text(content, encoding="utf-8")

    assert _git(
        repo,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    ) == b""
    with pytest.raises(
        partition_runner.PartitionCollectionError,
        match="ignored file can alter partition collection",
    ):
        repository_revision(repo)


@pytest.mark.test_evidence("behavioral_oracle")
@pytest.mark.parametrize(
    ("relative", "content"),
    PYTEST_CONFIG_CASES,
)
def test_repository_revision_rejects_ignored_pytest_configs_that_change_collection(
    tmp_path: Path,
    relative: str,
    content: str,
) -> None:
    repo, _files = _initialize_partition_revision_repo(tmp_path)
    baseline_returncode, baseline_nodes = _collect_fixture_nodes(repo)
    (repo / relative).write_text(content, encoding="utf-8")
    changed_returncode, changed_nodes = _collect_fixture_nodes(repo)

    assert partition_runner._ROOT_PYTEST_CONFIG_PATHS == tuple(
        case[0] for case in PYTEST_CONFIG_CASES
    )
    assert (baseline_returncode, baseline_nodes) == (
        0,
        ("tests/test_sample.py::test_sample",),
    )
    assert (changed_returncode, changed_nodes) == (5, ())
    assert _git(
        repo,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    ) == b""
    with pytest.raises(
        partition_runner.PartitionCollectionError,
        match="ignored pytest configuration can alter partition collection",
    ):
        repository_revision(repo)


@pytest.mark.test_evidence("behavioral_oracle")
def test_repository_revision_rejects_ignored_namespace_plugin(
    tmp_path: Path,
) -> None:
    repo, _files = _initialize_partition_revision_repo(tmp_path)
    conftest = repo / "tests/conftest.py"
    conftest.write_text(
        'pytest_plugins = ["helpers.plugin"]\n',
        encoding="utf-8",
    )
    _git(repo, "add", "--", "tests/conftest.py")
    _git(repo, "commit", "--quiet", "-m", "load namespace plugin")
    plugin = repo / "helpers/plugin.py"
    plugin.parent.mkdir()
    plugin.write_text("VALUE = 'no-op plugin'\n", encoding="utf-8")
    baseline_returncode, baseline_nodes = _collect_fixture_nodes(repo)

    plugin.write_text(
        "def pytest_collection_modifyitems(items: list[object]) -> None:\n"
        "    items.clear()\n",
        encoding="utf-8",
    )
    changed_returncode, changed_nodes = _collect_fixture_nodes(repo)

    assert (baseline_returncode, baseline_nodes) == (
        0,
        ("tests/test_sample.py::test_sample",),
    )
    assert (changed_returncode, changed_nodes) == (5, ())
    assert _git(
        repo,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    ) == b""
    with pytest.raises(
        partition_runner.PartitionCollectionError,
        match="ignored file can alter partition collection",
    ):
        repository_revision(repo)


@pytest.mark.test_evidence("behavioral_oracle")
def test_repository_revision_rejects_arbitrary_ignored_collection_input(
    tmp_path: Path,
) -> None:
    repo, _files = _initialize_partition_revision_repo(tmp_path)
    conftest = repo / "conftest.py"
    conftest.write_text(
        "from pathlib import Path\n\n"
        'FLAG = Path(__file__).with_name("selection.flag")\n'
        "collect_ignore = (\n"
        '    ["tests/test_sample.py"]\n'
        '    if FLAG.read_text(encoding="utf-8").strip() == "ignore"\n'
        "    else []\n"
        ")\n",
        encoding="utf-8",
    )
    _git(repo, "add", "--force", "--", "conftest.py")
    _git(repo, "commit", "--quiet", "-m", "read ignored collection flag")
    flag = repo / "selection.flag"
    flag.write_text("include\n", encoding="utf-8")
    baseline_returncode, baseline_nodes = _collect_fixture_nodes(repo)

    flag.write_text("ignore\n", encoding="utf-8")
    changed_returncode, changed_nodes = _collect_fixture_nodes(repo)

    assert (baseline_returncode, baseline_nodes) == (
        0,
        ("tests/test_sample.py::test_sample",),
    )
    assert (changed_returncode, changed_nodes) == (5, ())
    assert _git(
        repo,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    ) == b""
    with pytest.raises(
        partition_runner.PartitionCollectionError,
        match="ignored file can alter partition collection",
    ):
        repository_revision(repo)


@pytest.mark.test_evidence("behavioral_oracle")
@pytest.mark.parametrize("entry_kind", ("directory", "symlink"))
def test_repository_revision_rejects_ignored_nongenerated_roots(
    tmp_path: Path,
    entry_kind: str,
) -> None:
    repo, _files = _initialize_partition_revision_repo(tmp_path)
    ignored_root = repo / "ignored_root"
    if entry_kind == "directory":
        ignored_root.mkdir()
        (ignored_root / "selection.flag").write_text(
            "arbitrary ignored input\n",
            encoding="utf-8",
        )
    else:
        ignored_root.symlink_to("tests", target_is_directory=True)

    assert _git(
        repo,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    ) == b""
    with pytest.raises(
        partition_runner.PartitionCollectionError,
        match=(
            "ignored file can alter partition collection"
            if entry_kind == "directory"
            else "ignored partition inputs do not permit symlinks"
        ),
    ):
        repository_revision(repo)


@pytest.mark.test_evidence("behavioral_oracle")
def test_repository_revision_allows_explicit_ignored_generated_outputs(
    tmp_path: Path,
) -> None:
    repo, _files = _initialize_partition_revision_repo(tmp_path)
    generated = {
        "build/conftest.py": "collect_ignore = ['tests']\n",
        "data/terrain_cache/generated.yaml": "generated: true\n",
        "tests/__pycache__/test_sample.pyc": "generated bytecode\n",
        ".pytest_cache/conftest.py": "generated cache\n",
    }
    for relative, content in generated.items():
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    assert _git(
        repo,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    ) == b""
    assert repository_revision(repo)["dirty"] is False


@pytest.mark.test_evidence("behavioral_oracle")
def test_pytest_subprocess_environment_is_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for variable in (
        "PYTHONHOME",
        "PYTHONPATH",
        "PYTEST_ADDOPTS",
        "PYTEST_PLUGINS",
    ):
        monkeypatch.setenv(variable, "attacker-controlled")
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "0")
    monkeypatch.setenv("PYTHONHASHSEED", "random")
    monkeypatch.setenv("PYTHONNOUSERSITE", "0")
    monkeypatch.setenv("PYTHONPYCACHEPREFIX", "/attacker/cache")
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "0")
    pycache_prefix = tmp_path / "empty-pycache"
    pycache_prefix.mkdir()

    environment = partition_runner._subprocess_environment(
        str(pycache_prefix),
    )
    command = _pytest_command("--collect-only", "tests")

    assert all(
        variable not in environment
        for variable in (
            "PYTHONHOME",
            "PYTHONPATH",
            "PYTEST_ADDOPTS",
            "PYTEST_PLUGINS",
        )
    )
    assert environment["PYTHONDONTWRITEBYTECODE"] == "1"
    assert environment["PYTHONHASHSEED"] == "0"
    assert environment["PYTHONNOUSERSITE"] == "1"
    assert environment["PYTHONPYCACHEPREFIX"] == str(pycache_prefix)
    assert environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert command.count("pytest_asyncio.plugin") == 1
    assert command.count("tests.artifact_support") == 1


@pytest.mark.test_evidence("behavioral_oracle")
def test_collection_ignores_forged_timestamp_bytecode(tmp_path: Path) -> None:
    repo, _files = _initialize_partition_revision_repo(tmp_path)
    helper = repo / "helper.py"
    original_source = b"VALUE = 'include'\n"
    alternate_source = b"VALUE = 'ignore!'\n"
    assert len(original_source) == len(alternate_source)
    helper.write_bytes(original_source)
    conftest = repo / "conftest.py"
    conftest.write_text(
        "from helper import VALUE\n\n"
        "collect_ignore = (\n"
        '    ["tests/test_sample.py"] if VALUE == "ignore!" else []\n'
        ")\n",
        encoding="utf-8",
    )
    _git(repo, "add", "--", "helper.py")
    _git(repo, "add", "--force", "--", "conftest.py")
    _git(repo, "commit", "--quiet", "-m", "load collection helper")
    clean_revision = repository_revision(repo)
    source_metadata = helper.stat()

    helper.write_bytes(alternate_source)
    os.utime(
        helper,
        ns=(source_metadata.st_atime_ns, source_metadata.st_mtime_ns),
    )
    pycache = repo / "__pycache__"
    pycache.mkdir()
    bytecode = pycache / f"helper.{sys.implementation.cache_tag}.pyc"
    py_compile.compile(
        str(helper),
        cfile=str(bytecode),
        doraise=True,
        invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP,
    )
    helper.write_bytes(original_source)
    os.utime(
        helper,
        ns=(source_metadata.st_atime_ns, source_metadata.st_mtime_ns),
    )

    assert bytecode.is_file()
    assert _git(
        repo,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    ) == b""
    assert repository_revision(repo) == clean_revision
    unsafe_returncode, unsafe_nodes = _collect_fixture_nodes(
        repo,
        environment=_unisolated_fixture_environment(
            plugin_autoload=False,
        ),
    )
    safe_nodes = partition_runner.collect_node_ids(("tests",), root=repo)

    assert (unsafe_returncode, unsafe_nodes) == (5, ())
    assert safe_nodes == ("tests/test_sample.py::test_sample",)


@pytest.mark.test_evidence("behavioral_oracle")
def test_collection_disables_ignored_egg_info_plugins(tmp_path: Path) -> None:
    repo, _files = _initialize_partition_revision_repo(tmp_path)
    plugin = repo / "evil_plugin.py"
    plugin.write_text(
        "def pytest_collection_modifyitems(items: list[object]) -> None:\n"
        "    items.clear()\n",
        encoding="utf-8",
    )
    _git(repo, "add", "--", "evil_plugin.py")
    _git(repo, "commit", "--quiet", "-m", "track dormant pytest plugin")
    clean_revision = repository_revision(repo)
    egg_info = repo / "evil.egg-info"
    egg_info.mkdir()
    (egg_info / "PKG-INFO").write_text(
        "Metadata-Version: 2.1\n"
        "Name: evil\n"
        "Version: 1.0\n",
        encoding="utf-8",
    )
    (egg_info / "entry_points.txt").write_text(
        "[pytest11]\n"
        "evil = evil_plugin\n",
        encoding="utf-8",
    )

    assert _git(
        repo,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    ) == b""
    assert repository_revision(repo) == clean_revision
    unsafe_returncode, unsafe_nodes = _collect_fixture_nodes(
        repo,
        environment=_unisolated_fixture_environment(
            plugin_autoload=True,
        ),
    )
    safe_nodes = partition_runner.collect_node_ids(("tests",), root=repo)

    assert (unsafe_returncode, unsafe_nodes) == (5, ())
    assert safe_nodes == ("tests/test_sample.py::test_sample",)


@pytest.mark.test_evidence("behavioral_oracle")
def test_repository_revision_rejects_tracked_symlink(tmp_path: Path) -> None:
    repo, _files = _initialize_partition_revision_repo(tmp_path)
    link = repo / "tests/test_link.py"
    link.symlink_to("test_sample.py")
    _git(repo, "add", "--", "tests/test_link.py")
    _git(repo, "commit", "--quiet", "-m", "track collection symlink")

    with pytest.raises(
        partition_runner.PartitionCollectionError,
        match="regular tracked blobs",
    ):
        repository_revision(repo)


@pytest.mark.test_evidence("behavioral_oracle")
def test_repository_revision_rejects_untracked_symlink(tmp_path: Path) -> None:
    repo, _files = _initialize_partition_revision_repo(tmp_path)
    (repo / "shadow.py").symlink_to("tests/test_sample.py")

    with pytest.raises(
        partition_runner.PartitionCollectionError,
        match="do not permit symlinks",
    ):
        repository_revision(repo)


@pytest.mark.test_evidence("behavioral_oracle")
def test_dirty_repository_revision_preserves_rename_and_deletion(
    tmp_path: Path,
) -> None:
    repo, files = _initialize_partition_revision_repo(tmp_path)
    clean = repository_revision(repo)
    files["tests/test_sample.py"].rename(repo / "tests/test_renamed.py")
    files["scripts/runner.py"].unlink()

    first = repository_revision(repo)
    second = repository_revision(repo)

    assert first == second
    assert first["dirty"] is True
    assert first["commit"] == clean["commit"]
    assert first["worktree_fingerprint"] != clean["worktree_fingerprint"]


@pytest.mark.test_evidence("behavioral_oracle")
def test_manifest_reuse_rejects_repository_revision_mismatch(
    tmp_path: Path,
) -> None:
    repo, files = _initialize_partition_revision_repo(tmp_path)
    (repo / "notes.txt").write_text(
        "constant dirty state\n",
        encoding="utf-8",
    )
    revision = repository_revision(repo)
    audit_path = tmp_path / "partition-audit.json"
    audit_path.write_text(
        json.dumps(
            _synthetic_audit_payload(revision=revision),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    relative = "tests/test_sample.py"
    source = files[relative]
    source.write_bytes(source.read_bytes().replace(b"\n", b"\r\n"))
    _git(repo, "add", "--renormalize", "--", relative)
    assert _git(
        repo,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    ) == b"?? notes.txt\0"

    current_revision = repository_revision(repo)
    assert current_revision["commit"] == revision["commit"]
    assert (
        current_revision["worktree_fingerprint"]
        != revision["worktree_fingerprint"]
    )

    with pytest.raises(
        partition_runner.PartitionCollectionError,
        match="audit manifest revision does not match",
    ):
        load_audit_manifest(audit_path, root=repo)


@pytest.mark.test_evidence("behavioral_oracle")
def test_repository_revision_rechecks_checkout_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, files = _initialize_partition_revision_repo(tmp_path)
    verify_clean_checkout = partition_runner._verify_clean_checkout

    def verify_then_mutate(*args: object, **kwargs: object) -> None:
        verify_clean_checkout(*args, **kwargs)
        files["README.md"].write_text(
            "# Changed during revision capture\n",
            encoding="utf-8",
        )

    monkeypatch.setattr(
        partition_runner,
        "_verify_clean_checkout",
        verify_then_mutate,
    )

    with pytest.raises(
        partition_runner.PartitionCollectionError,
        match="status changed during partition revision capture",
    ):
        repository_revision(repo)


@pytest.mark.test_evidence("behavioral_oracle")
def test_extended_matrix_is_generated_and_every_shard_is_non_empty() -> None:
    partitions = {
        name: (f"tests/{name}.py::test_member",)
        for name in AUDITED_PARTITIONS
    }
    partitions["slow-only"] = tuple(
        f"tests/slow_{index:02d}.py::test_member"
        for index in range(15)
    )
    partitions["benchmark-only"] = tuple(
        f"tests/benchmark_{index:02d}.py::test_member"
        for index in range(3)
    )
    matrix = build_extended_matrix(partitions)
    configured = matrix["include"]
    expected = {
        policy.partition: (policy.shard_count, policy.timeout_seconds)
        for policy in EXTENDED_PARTITION_POLICIES
    }
    assert len(configured) == sum(count for count, _timeout in expected.values())
    assert {
        (entry["partition"], entry["shard_index"])
        for entry in configured
    } == {
        (partition, shard_index)
        for partition, (shard_count, _timeout) in expected.items()
        for shard_index in range(shard_count)
    }

    partitions["slow-only"] = partitions["slow-only"][:-1]
    with pytest.raises(
        partition_runner.PartitionCollectionError,
        match="empty shards",
    ):
        build_extended_matrix(partitions)


def test_partition_entrypoints_isolate_bytecode_before_runner_imports() -> None:
    for relative in (
        "scripts/validate_test_partitions.py",
        "scripts/generate_extended_test_matrix.py",
    ):
        source = (ROOT / relative).read_text(encoding="utf-8")
        isolation = source.index("sys.pycache_prefix")
        package_import = source.index("from scripts.run_pytest_partition")
        direct_import = source.index("from run_pytest_partition")

        assert "TemporaryDirectory" in source[:isolation]
        assert isolation < package_import
        assert isolation < direct_import


@pytest.mark.test_evidence("behavioral_oracle")
def test_runner_reuses_audit_manifest_without_duplicate_collection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _synthetic_audit_payload()
    audit_path = tmp_path / "partition-audit.json"
    audit_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        partition_runner,
        "repository_revision",
        lambda _root: dict(TEST_REVISION),
    )

    def reject_collection(*_args: object, **_kwargs: object) -> tuple[str, ...]:
        raise AssertionError("partition was recollected")

    monkeypatch.setattr(
        partition_runner,
        "collect_partition_node_ids",
        reject_collection,
    )
    observed_pycache_prefixes: list[Path] = []

    def execute(
        command: list[str],
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        environment = _kwargs["env"]
        assert isinstance(environment, dict)
        assert environment["PYTHONDONTWRITEBYTECODE"] == "1"
        assert environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
        assert all(
            variable not in environment
            for variable in (
                "PYTHONHOME",
                "PYTHONPATH",
                "PYTEST_ADDOPTS",
                "PYTEST_PLUGINS",
            )
        )
        pycache_prefix = Path(environment["PYTHONPYCACHEPREFIX"])
        assert pycache_prefix.is_dir()
        assert not tuple(pycache_prefix.iterdir())
        observed_pycache_prefixes.append(pycache_prefix)
        junit_argument = next(
            argument for argument in command if argument.startswith("--junitxml=")
        )
        Path(junit_argument.removeprefix("--junitxml=")).write_text(
            '<testsuites><testsuite tests="1" failures="0" errors="0" skipped="0"/></testsuites>',
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout="1 passed in 0.01s",
            stderr="",
        )

    monkeypatch.setattr(partition_runner.subprocess, "run", execute)
    execution_manifest = tmp_path / "api" / "manifest.json"
    assert (
        run_partition(
            "api",
            manifest_path=execution_manifest,
            junit_path=tmp_path / "api" / "junit.xml",
            shard_index=0,
            shard_count=1,
            timeout_seconds=30,
            forbid_skips=True,
            audit_manifest_path=audit_path,
            root=tmp_path,
        )
        == 0
    )
    manifest = json.loads(execution_manifest.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 2
    assert manifest["collection_source"]["kind"] == (
        "revision_bound_audit_manifest"
    )
    assert manifest["collection_source"]["revision"] == TEST_REVISION
    assert manifest["shard"]["selected_node_ids"] == [
        "tests/api.py::test_member",
    ]
    assert len(observed_pycache_prefixes) == 1
    assert not observed_pycache_prefixes[0].exists()


@pytest.mark.test_evidence("behavioral_oracle")
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


@pytest.mark.test_evidence("behavioral_oracle")
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


@pytest.mark.test_evidence("behavioral_oracle")
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


@pytest.mark.test_evidence("behavioral_oracle")
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

    structural_class_tree = ast.parse(
        "@pytest.mark.test_evidence('structural_only')\n"
        "class TestRegistry:\n"
        "    @pytest.mark.parametrize('owner', ['clock'])\n"
        "    def test_owner(self, owner):\n"
        "        assert owner in {'clock'}\n"
        "\n"
        "    @pytest.mark.test_evidence('behavioral_oracle')\n"
        "    def test_runtime_contract(self):\n"
        "        assert runtime.state == expected\n",
    )
    indexed = _definitions_from_tree(
        "tests/example.py",
        structural_class_tree,
    )
    inherited = indexed[
        ("tests/example.py", "TestRegistry::test_owner")
    ]
    overridden = indexed[
        ("tests/example.py", "TestRegistry::test_runtime_contract")
    ]
    assert inherited.annotation is not None
    assert inherited.annotation.classification == "structural_only"
    assert inherited.structural_context
    assert inherited.weak_reasons == ("declared structural scope",)
    assert overridden.annotation is not None
    assert overridden.annotation.classification == "behavioral_oracle"
    assert overridden.structural_context


@pytest.mark.test_evidence("behavioral_oracle")
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


@pytest.mark.parametrize(
    ("source", "error"),
    (
        (
            "CLASSIFICATION = 'structural_only'\n"
            "@pytest.mark.test_evidence(CLASSIFICATION)\n"
            "def test_contract():\n"
            "    pass\n",
            "literal string",
        ),
        (
            "@pytest.mark.test_evidence('')\n"
            "def test_contract():\n"
            "    pass\n",
            "must not be empty",
        ),
        (
            "@pytest.mark.test_evidence('structural_only')\n"
            "@pytest.mark.test_evidence('behavioral_oracle')\n"
            "def test_contract():\n"
            "    pass\n",
            "conflicting",
        ),
        (
            "@pytest.mark.test_evidence('behavioral_oracle')\n"
            "class TestContract:\n"
            "    def test_contract(self):\n"
            "        pass\n",
            "definition-local",
        ),
        (
            "@pytest.mark.test_evidence('structural_only')\n"
            "def helper():\n"
            "    pass\n",
            "stale",
        ),
    ),
)
def test_source_local_evidence_metadata_is_fail_closed(
    source: str,
    error: str,
) -> None:
    with pytest.raises(ValueError, match=error):
        _definitions_from_tree("tests/example.py", ast.parse(source))


@pytest.mark.parametrize(
    "source",
    (
        (
            "@pytest.mark.test_evidence('behavioral_oracle')\n"
            "def test_runtime_rejection_status_is_exact():\n"
            "    fixture = scenario_path.read_text()\n"
            "    response = client.post(fixture)\n"
            "    assert response.status_code == 422\n"
        ),
        (
            "def check_rejected(result):\n"
            "    assert result.status == 'rejected'\n"
            "@pytest.mark.test_evidence('helper_assertion')\n"
            "def test_runtime_rejection_uses_shared_oracle():\n"
            "    check_rejected(runtime.run())\n"
        ),
        (
            "@pytest.mark.test_evidence('invariant_only')\n"
            "def test_missing_unit_is_a_noop():\n"
            "    runtime.update('missing')\n"
        ),
        (
            "@pytest.mark.test_evidence('structural_only')\n"
            "def test_registry_result_has_expected_shape():\n"
            "    assert result is not None\n"
        ),
    ),
)
def test_source_local_evidence_kinds_enforce_valid_semantics(source: str) -> None:
    _validate_synthetic_evidence(source)


@pytest.mark.parametrize(
    ("source", "error"),
    (
        (
            "def test_result_has_shape():\n"
            "    assert result is not None\n",
            "missing=",
        ),
        (
            "@pytest.mark.test_evidence('behavioral_oracle')\n"
            "def test_runtime_status_is_exact():\n"
            "    assert response.status_code == 422\n",
            "stale=",
        ),
        (
            "@pytest.mark.test_evidence('behavioral_oracle')\n"
            "def test_source_document_contains_job():\n"
            "    workflow = path.read_text()\n"
            "    assert 'job:' in workflow\n",
            "only source, mock, or shape evidence",
        ),
        (
            "@pytest.mark.test_evidence('behavioral_oracle')\n"
            "def test_result_shape_is_available():\n"
            "    assert result is not None\n",
            "only source, mock, or shape evidence",
        ),
        (
            "@pytest.mark.test_evidence('behavioral_oracle')\n"
            "def test_runtime_callback_is_invoked():\n"
            "    callback.assert_called_once()\n",
            "only source, mock, or shape evidence",
        ),
        (
            "@pytest.mark.test_evidence('helper_assertion')\n"
            "def test_runtime_uses_shared_oracle():\n"
            "    helper_without_assertion()\n",
            "has no called local assertion helper",
        ),
        (
            "@pytest.mark.test_evidence('invariant_only')\n"
            "def test_runtime_update_delegates():\n"
            "    runtime.update()\n",
            "does not explicitly name",
        ),
        (
            "@pytest.mark.test_evidence('structural_only')\n"
            "def test_case():\n"
            "    assert result is not None\n",
            "meaningful name or docstring",
        ),
    ),
)
def test_source_local_evidence_kinds_reject_invalid_semantics(
    source: str,
    error: str,
) -> None:
    with pytest.raises(ValueError, match=error):
        _validate_synthetic_evidence(source)


def test_parametrized_nodes_share_one_source_definition_identity() -> None:
    definition_id = "tests/example.py::TestCases::test_contract"

    assert definition_id_from_node_id(definition_id) == definition_id
    assert (
        definition_id_from_node_id(f"{definition_id}[first-case]")
        == definition_id
    )
    assert (
        definition_id_from_node_id(
            f"{definition_id}[nested-value[2]-second-case]",
        )
        == definition_id
    )
    assert (
        definition_id_from_node_id(f"{definition_id}[value::with-separator]")
        == definition_id
    )


def test_pull_request_main_and_manual_workflow_tiers_are_explicit() -> None:
    test_workflow = _workflow("test.yml")
    lint_workflow = _workflow("lint.yml")
    docs_workflow = _workflow("docs.yml")
    build_workflow = _workflow("build.yml")

    for workflow in (
        test_workflow,
        lint_workflow,
        docs_workflow,
        build_workflow,
    ):
        triggers = workflow["on"]
        assert triggers["push"]["branches"] == ["main"]
        assert triggers["pull_request"]["branches"] == ["main"]

    for workflow, required_jobs in (
        (test_workflow, ("partition-audit", "python", "terrain", "frontend")),
        (lint_workflow, ("python", "frontend")),
        (docs_workflow, ("validate",)),
        (build_workflow, ("docker",)),
    ):
        for job_name in required_jobs:
            assert "if" not in workflow["jobs"][job_name]

    dispatch = test_workflow["on"]["workflow_dispatch"]
    diagnostic_input = dispatch["inputs"]["run_phase117_diagnostic"]
    assert diagnostic_input["type"] == "boolean"
    assert diagnostic_input["default"] == "false"
    diagnostic = test_workflow["jobs"]["phase117-diagnostic"]
    assert diagnostic["if"] == (
        "github.event_name == 'workflow_dispatch' && "
        "inputs.run_phase117_diagnostic"
    )
    diagnostic_commands = "\n".join(
        step["run"] for step in diagnostic["steps"] if "run" in step
    )
    assert "scripts/run_historical_backtest.py" in diagnostic_commands
    routine_commands = "\n".join(
        step["run"]
        for name, job in test_workflow["jobs"].items()
        if name != "phase117-diagnostic"
        for step in job["steps"]
        if "run" in step
    )
    assert "scripts/run_historical_backtest.py" not in routine_commands
    assert "Run clean-revision held-out study" not in _workflow_text("test.yml")

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
    assert "scripts/validate_scenario_data.py" in test_text
    assert "--historical-claims-only" not in test_text
    assert test_workflow["jobs"]["python"]["needs"] == "partition-audit"
    python_steps = test_workflow["jobs"]["python"]["steps"]
    assert any(
        step.get("uses") == "actions/download-artifact@v4"
        for step in python_steps
    )
    assert "--audit-manifest artifacts/partition-audit/manifest.json" in test_text
    assert "uv sync --locked --extra dev --extra terrain" in test_text
    assert test_text.count("--forbid-skips") == 2
    assert "test_phase_15" not in test_text

    terrain = test_workflow["jobs"]["terrain"]
    terrain_checkout = next(
        step
        for step in terrain["steps"]
        if step.get("uses") == "actions/checkout@v4"
    )
    assert terrain_checkout["with"]["fetch-depth"] == "0"
    relevance = next(
        step
        for step in terrain["steps"]
        if step.get("id") == "terrain-relevance"
    )
    assert relevance["env"] == {
        "EVENT_NAME": "${{ github.event_name }}",
        "BASE_SHA": "${{ github.event.pull_request.base.sha }}",
        "REVISION": "${{ github.sha }}",
    }
    relevance_command = relevance["run"]
    assert 'checked_out_revision="$(git rev-parse HEAD)"' in relevance_command
    assert 'if [[ "${EVENT_NAME}" == "pull_request" ]]' in relevance_command
    assert 'git cat-file -e "${BASE_SHA}^{commit}"' in relevance_command
    assert "git diff --name-only --diff-filter=ACMRD" in relevance_command
    for surface in (
        ".github/workflows/test.yml",
        "pyproject.toml",
        "uv.lock",
        "data/*",
        "stochastic_warfare/*",
        "tests/unit/terrain/*",
    ):
        assert surface in relevance_command
    assert "run_terrain=true" in relevance_command
    assert "run_terrain=false" in relevance_command
    assert "revision=%s" in relevance_command
    assert "run=%s" in relevance_command
    assert "dorny/paths-filter" not in test_text

    conditional_steps = {
        "Install uv",
        "Install locked terrain dependencies",
        "Run explicit terrain dependency profile",
    }
    for step in terrain["steps"]:
        if step.get("name") in conditional_steps or step.get("uses") == (
            "actions/setup-python@v5"
        ):
            assert step["if"] == (
                "steps.terrain-relevance.outputs.run == 'true'"
            )
    skipped = next(
        step
        for step in terrain["steps"]
        if step.get("name") == "Record non-relevant terrain decision"
    )
    assert skipped["if"] == (
        "steps.terrain-relevance.outputs.run != 'true'"
    )

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


def test_extended_partitions_are_nightly_manual_generated_and_bounded() -> None:
    workflow = _workflow("extended-tests.yml")
    triggers = workflow["on"]
    assert triggers["schedule"] == [{"cron": "17 6 * * *"}]
    assert "workflow_dispatch" in triggers

    matrix = workflow["jobs"]["marker-partition"]["strategy"]["matrix"]
    assert matrix == "${{ fromJSON(needs.partition-audit.outputs.matrix) }}"
    partition_audit = workflow["jobs"]["partition-audit"]
    assert partition_audit["outputs"]["matrix"] == (
        "${{ steps.extended_matrix.outputs.matrix }}"
    )
    assert workflow["jobs"]["marker-partition"]["needs"] == "partition-audit"

    job_timeout_seconds = (
        int(workflow["jobs"]["marker-partition"]["timeout-minutes"])
        * 60
    )
    assert (
        job_timeout_seconds
        - max(policy.timeout_seconds for policy in EXTENDED_PARTITION_POLICIES)
        >= 1200
    )
    assert all("if" not in job for job in workflow["jobs"].values())
    marker_steps = workflow["jobs"]["marker-partition"]["steps"]
    checkout_step = next(
        step
        for step in marker_steps
        if step.get("uses") == "actions/checkout@v4"
    )
    assert checkout_step["with"]["fetch-depth"] == "0"
    assert any(
        step.get("uses") == "actions/download-artifact@v4"
        for step in marker_steps
    )
    superset_command = "uv sync --locked --extra dev --extra api --extra terrain --extra mcp"
    run_commands = [step["run"] for job in workflow["jobs"].values() for step in job["steps"] if "run" in step]
    assert run_commands.count(superset_command) == 2
    workflow_text = _workflow_text("extended-tests.yml")
    assert "scripts/generate_extended_test_matrix.py" in workflow_text
    assert "matrix:\n        include:" not in workflow_text
    assert "--audit-manifest artifacts/partition-audit/manifest.json" in workflow_text
    assert '--shard-count "${{ matrix.shard_count }}"' in workflow_text
    assert "--forbid-skips" in workflow_text


def test_benchmark_scenario_gates_have_explicit_trigger_boundaries() -> None:
    workflow = _workflow("benchmark.yml")
    triggers = workflow["on"]

    assert triggers["push"]["branches"] == ["main"]
    assert triggers["pull_request"]["branches"] == ["main"]
    assert triggers["schedule"] == [{"cron": "17 6 * * *"}]
    dispatch_inputs = triggers["workflow_dispatch"]["inputs"]
    assert dispatch_inputs["run_easting"] == {
        "description": (
            "Run the 73 Easting paired gate outside the nightly schedule"
        ),
        "type": "boolean",
        "default": "false",
    }
    assert dispatch_inputs["run_golan"]["type"] == "boolean"
    assert dispatch_inputs["run_golan"]["default"] == "false"

    jobs = workflow["jobs"]
    assert "if" not in jobs["policy"]
    assert jobs["easting"]["if"] == (
        "github.event_name == 'schedule' || "
        "(github.event_name == 'workflow_dispatch' && inputs.run_easting)"
    )
    assert jobs["golan"]["if"] == (
        "github.event_name == 'workflow_dispatch' && inputs.run_golan"
    )


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
        for step in upload_steps:
            expected_condition = (
                "always() && "
                "steps.terrain-relevance.outputs.run == 'true'"
                if step["with"].get("path") == "artifacts/terrain/"
                else "always()"
            )
            assert step.get("if") == expected_condition
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
