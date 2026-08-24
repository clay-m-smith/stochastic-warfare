"""Collect and run one explicit repository pytest partition.

The runner deliberately clears repository ``addopts`` so each invocation is
defined only by the named partition below.  Collection is written to a
deterministic JSON manifest before execution, allowing CI to retain the exact
selected node IDs even when pytest fails or reaches its operational timeout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import stat
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path, PurePosixPath
from typing import Mapping, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
COLLECTION_TIMEOUT_SECONDS = 300
AUDIT_MANIFEST_SCHEMA_VERSION = 2

TERRAIN_TEST_FILES = (
    "tests/unit/terrain/test_heightmap_pipeline.py",
    "tests/unit/terrain/test_classification_infrastructure.py",
    "tests/unit/terrain/test_bathymetry_pipeline.py",
    "tests/unit/terrain/test_pipeline_integration.py",
)

BENCHMARK_POLICY_TEST_FILES = (
    "tests/benchmarks/test_benchmarks.py",
    "tests/benchmarks/test_flag_impact.py",
)


@dataclass(frozen=True)
class PartitionSpec:
    """The authoritative pytest selector for one disjoint suite partition."""

    paths: tuple[str, ...]
    marker_expression: str | None = None
    ignored_paths: tuple[str, ...] = ()

    def pytest_arguments(self) -> tuple[str, ...]:
        arguments = list(self.paths)
        arguments.extend(f"--ignore={path}" for path in self.ignored_paths)
        if self.marker_expression is not None:
            arguments.extend(("-m", self.marker_expression))
        return tuple(arguments)


_BACKEND_IGNORES = ("tests/api", "tests/e2e")
PARTITION_SPECS: dict[str, PartitionSpec] = {
    "standard": PartitionSpec(
        paths=("tests",),
        marker_expression="not slow and not benchmark",
        ignored_paths=_BACKEND_IGNORES,
    ),
    "slow-only": PartitionSpec(
        paths=("tests",),
        marker_expression="slow and not benchmark",
        ignored_paths=_BACKEND_IGNORES,
    ),
    "benchmark-only": PartitionSpec(
        paths=("tests",),
        marker_expression="benchmark and not slow",
        ignored_paths=_BACKEND_IGNORES,
    ),
    "slow-benchmark": PartitionSpec(
        paths=("tests",),
        marker_expression="slow and benchmark",
        ignored_paths=_BACKEND_IGNORES,
    ),
    "api": PartitionSpec(paths=("tests/api",)),
    "e2e": PartitionSpec(paths=("tests/e2e",)),
    "terrain": PartitionSpec(paths=TERRAIN_TEST_FILES),
    # This focused CI profile intentionally overlaps the audited benchmark
    # partitions.  Like ``terrain``, it is a dependency/policy boundary and
    # therefore is not a seventh member of the exact disjoint suite union.
    "benchmark-policy": PartitionSpec(paths=BENCHMARK_POLICY_TEST_FILES),
}

AUDITED_PARTITIONS = (
    "standard",
    "slow-only",
    "benchmark-only",
    "slow-benchmark",
    "api",
    "e2e",
)


class PartitionCollectionError(RuntimeError):
    """Raised when pytest cannot provide a trustworthy non-empty collection."""


@dataclass(frozen=True)
class ShardPlan:
    """Deterministic assignment and audit metadata for every requested shard."""

    strategy: str
    module_ids: tuple[str, ...]
    split_module_ids: tuple[str, ...]
    shards: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class ValidatedAuditManifest:
    """A revision-bound, internally consistent exact partition collection."""

    revision: Mapping[str, object]
    superset: tuple[str, ...]
    partitions: Mapping[str, tuple[str, ...]]
    manifest_sha256: str


def _pytest_command(*arguments: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "pytest",
        "-p",
        "pytest_asyncio.plugin",
        "-p",
        "tests.artifact_support",
        "-p",
        "no:cacheprovider",
        "-o",
        "addopts=",
        *arguments,
    ]


def _command_text(command: Sequence[str]) -> str:
    return shlex.join(command)


def _is_node_id_line(line: str) -> bool:
    return (line.startswith("tests/") or line.startswith("tests\\")) and "::" in line


def _node_id_lines(output: str) -> tuple[str, ...]:
    node_ids = tuple(line.strip() for line in output.splitlines() if _is_node_id_line(line))
    duplicates = sorted(node_id for node_id, count in Counter(node_ids).items() if count > 1)
    if duplicates:
        raise PartitionCollectionError(f"pytest collection emitted duplicate node IDs: {duplicates[:5]}")
    return tuple(sorted(node_ids))


def _collection_summary(output: str) -> str:
    summaries = [line.strip() for line in output.splitlines() if "test collected" in line or "tests collected" in line]
    return summaries[-1] if summaries else "pytest emitted no collection summary"


_SUMMARY_COUNT_PATTERN = re.compile(
    r"(?P<count>\d+) (?P<label>passed|failed|errors?|skipped|"
    r"xfailed|xpassed|warnings?|deselected)"
)


def _result_counts(output: str) -> dict[str, int | bool]:
    counts: dict[str, int | bool] = {
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "xfailed": 0,
        "xpassed": 0,
        "warnings": 0,
        "deselected": 0,
        "summary_found": False,
    }
    summary_lines = [
        line.strip() for line in output.splitlines() if " in " in line and _SUMMARY_COUNT_PATTERN.search(line)
    ]
    if not summary_lines:
        return counts
    counts["summary_found"] = True
    for match in _SUMMARY_COUNT_PATTERN.finditer(summary_lines[-1]):
        label = match.group("label")
        if label in {"error", "errors"}:
            label = "errors"
        elif label in {"warning", "warnings"}:
            label = "warnings"
        counts[label] = int(match.group("count"))
    return counts


def _collection_counts(output: str, *, selected_count: int) -> dict[str, int]:
    summary = _collection_summary(output)
    deselected_match = re.search(r"(\d+) deselected", summary)
    warning_match = re.search(r"(\d+) warnings?", summary)
    return {
        "selected": selected_count,
        "deselected": int(deselected_match.group(1)) if deselected_match else 0,
        "warnings": int(warning_match.group(1)) if warning_match else 0,
    }


def _timeout_output(error: subprocess.TimeoutExpired) -> str:
    """Return decoded stdout/stderr retained by a timed-out subprocess."""
    chunks: list[str] = []
    for partial in (error.stdout, error.stderr):
        if isinstance(partial, bytes):
            chunks.append(partial.decode("utf-8", errors="replace"))
        elif partial:
            chunks.append(partial)
    return "\n".join(chunk.rstrip("\n") for chunk in chunks)


def collect_node_ids(
    selector_arguments: Sequence[str],
    *,
    root: Path = REPOSITORY_ROOT,
) -> tuple[str, ...]:
    """Collect sorted node IDs for an explicit selector or fail closed."""

    command = _pytest_command("--collect-only", "-q", *selector_arguments)
    print(f"COLLECT_COMMAND={_command_text(command)}", flush=True)
    try:
        with tempfile.TemporaryDirectory(
            prefix="stochastic-warfare-pycache-",
        ) as pycache_prefix:
            completed = subprocess.run(
                command,
                cwd=root,
                check=False,
                timeout=COLLECTION_TIMEOUT_SECONDS,
                capture_output=True,
                text=True,
                env=_subprocess_environment(pycache_prefix),
            )
    except subprocess.TimeoutExpired as error:
        partial_output = _timeout_output(error)
        if partial_output:
            print(partial_output, flush=True)
        raise PartitionCollectionError(
            "pytest collection timed out after "
            f"{COLLECTION_TIMEOUT_SECONDS} seconds: "
            f"{_command_text(command)}",
        ) from error
    except OSError as error:
        raise PartitionCollectionError(
            f"pytest collection could not launch: {_command_text(command)}: "
            f"{error}",
        ) from error
    combined_output = f"{completed.stdout}\n{completed.stderr}".strip()
    node_ids = _node_id_lines(combined_output)
    diagnostics = [line for line in combined_output.splitlines() if not _is_node_id_line(line)]
    if diagnostics:
        print("COLLECT_DIAGNOSTICS_BEGIN", flush=True)
        print("\n".join(diagnostics), flush=True)
        print("COLLECT_DIAGNOSTICS_END", flush=True)
    print(f"COLLECT_SUMMARY={_collection_summary(combined_output)}", flush=True)
    print(f"COLLECTED_NODE_COUNT={len(node_ids)}", flush=True)
    print(
        "COLLECTION_COUNTS="
        f"{json.dumps(_collection_counts(combined_output, selected_count=len(node_ids)), sort_keys=True)}",
        flush=True,
    )

    if completed.returncode != 0:
        raise PartitionCollectionError(
            f"pytest collection failed with exit code {completed.returncode}: {_command_text(command)}"
        )
    if not node_ids:
        raise PartitionCollectionError(f"pytest selector collected no tests: {_command_text(command)}")
    return node_ids


def collect_partition_node_ids(
    partition: str,
    *,
    root: Path = REPOSITORY_ROOT,
) -> tuple[str, ...]:
    """Collect one named partition using its exact authoritative selector."""

    try:
        specification = PARTITION_SPECS[partition]
    except KeyError as error:
        raise PartitionCollectionError(f"unknown pytest partition: {partition}") from error
    return collect_node_ids(specification.pytest_arguments(), root=root)


def _module_id(node_id: str) -> str:
    """Return the pytest collection module/file portion of a node ID."""

    return node_id.partition("::")[0]


def _plan_shards(
    node_ids: Sequence[str],
    *,
    shard_count: int,
) -> ShardPlan:
    """Assign all nodes with deterministic module-affine LPT balancing.

    Modules are ordered by descending node count and then module ID, and each
    whole module is assigned to the least-loaded shard (with shard index as the
    stable tie breaker).  When there are fewer modules than requested shards,
    whole-module affinity cannot produce non-empty shards, so the explicit
    ``balanced-node-fallback`` strategy uses contiguous node slices.  The
    generic runner still rejects any empty selected shard after planning.
    """

    if shard_count <= 0:
        raise ValueError("shard_count must be positive")
    ordered = tuple(sorted(node_ids))
    if len(set(ordered)) != len(ordered):
        raise ValueError("node_ids must be unique")

    grouped: dict[str, list[str]] = defaultdict(list)
    for node_id in ordered:
        grouped[_module_id(node_id)].append(node_id)
    module_ids = tuple(sorted(grouped))

    if len(module_ids) < shard_count:
        base_size, larger_shards = divmod(len(ordered), shard_count)
        shards: list[tuple[str, ...]] = []
        start = 0
        for index in range(shard_count):
            size = base_size + (1 if index < larger_shards else 0)
            shards.append(ordered[start : start + size])
            start += size
        module_shards: dict[str, set[int]] = defaultdict(set)
        for index, shard in enumerate(shards):
            for node_id in shard:
                module_shards[_module_id(node_id)].add(index)
        split_module_ids = tuple(
            sorted(
                module_id
                for module_id, assigned_shards in module_shards.items()
                if len(assigned_shards) > 1
            )
        )
        return ShardPlan(
            strategy="balanced-node-fallback",
            module_ids=module_ids,
            split_module_ids=split_module_ids,
            shards=tuple(shards),
        )

    shard_nodes: list[list[str]] = [[] for _ in range(shard_count)]
    shard_loads = [0] * shard_count
    ordered_groups = sorted(
        grouped.items(),
        key=lambda item: (-len(item[1]), item[0]),
    )
    for _module, nodes in ordered_groups:
        target = min(
            range(shard_count),
            key=lambda index: (shard_loads[index], index),
        )
        shard_nodes[target].extend(nodes)
        shard_loads[target] += len(nodes)
    return ShardPlan(
        strategy="module-affine-lpt",
        module_ids=module_ids,
        split_module_ids=(),
        shards=tuple(tuple(sorted(shard)) for shard in shard_nodes),
    )


def select_shard(
    node_ids: Sequence[str],
    *,
    shard_index: int,
    shard_count: int,
) -> tuple[str, ...]:
    """Select one shard from the deterministic, audit-visible shard plan."""

    if shard_count <= 0:
        raise ValueError("shard_count must be positive")
    if shard_index < 0 or shard_index >= shard_count:
        raise ValueError(f"shard_index must be in [0, {shard_count - 1}], got {shard_index}")
    plan = _plan_shards(node_ids, shard_count=shard_count)
    return plan.shards[shard_index]


def _node_id_digest(node_ids: Sequence[str]) -> str:
    serialized = "\n".join(node_ids).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _git_output(
    root: Path,
    *arguments: str,
    input_payload: bytes | None = None,
    allow_no_match: bool = False,
) -> bytes:
    command = ("git", "-C", str(root), *arguments)
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            input=input_payload,
        )
    except OSError as error:
        raise PartitionCollectionError(
            f"cannot capture partition-manifest revision: {_command_text(command)}: {error}",
        ) from error
    if completed.returncode != 0 and not (
        allow_no_match and completed.returncode == 1
    ):
        diagnostic = completed.stderr.decode("utf-8", errors="replace").strip()
        raise PartitionCollectionError(
            "cannot capture partition-manifest revision: "
            f"{_command_text(command)}: {diagnostic or 'Git failed'}",
        )
    return completed.stdout


_REGULAR_GIT_MODES = frozenset({"100644", "100755"})
_ROOT_PYTEST_CONFIG_PATHS = (
    "pytest.toml",
    ".pytest.toml",
    "pytest.ini",
    ".pytest.ini",
    "pyproject.toml",
    "tox.ini",
    "setup.cfg",
)
_ROOT_PYTEST_CONFIGS = frozenset(_ROOT_PYTEST_CONFIG_PATHS)
_IGNORED_OUTPUT_EXCLUDE_PATHSPECS = (
    ":(exclude,top,glob)**/__pycache__/**",
    ":(exclude,top,glob)**/.mypy_cache/**",
    ":(exclude,top,glob)**/.pytest_cache/**",
    ":(exclude,top,glob)**/.ruff_cache/**",
    ":(exclude,top,glob)**/node_modules/**",
    ":(exclude,top,glob)**/*.egg-info/**",
    ":(exclude,top,glob).venv/**",
    ":(exclude,top,glob)artifacts/**",
    ":(exclude,top,glob)build/**",
    ":(exclude,top,glob)dist/**",
    ":(exclude,top,glob)site/**",
    ":(exclude,top,glob)data/terrain_cache/**",
    ":(exclude,top,glob)docs/articles/**",
    ":(exclude,top,glob)docs/evidence/**",
    ":(exclude,top,glob)frontend/dist/**",
    ":(exclude,top,glob)scripts/visualize/output/**",
    ":(exclude,top,glob)scripts/evaluation_results*.json",
    ":(exclude,top,glob)scripts/evaluation_stderr*.log",
    ":(exclude,top,literal)scripts/falk_test.json",
)


def _decode_git_path(payload: bytes) -> str:
    """Decode one canonical repository-relative path emitted by Git."""
    try:
        relative = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise PartitionCollectionError(
            "Git returned a non-UTF-8 partition input path",
        ) from error
    path = PurePosixPath(relative)
    if (
        not relative
        or "\\" in relative
        or "\n" in relative
        or "\r" in relative
        or "\t" in relative
        or path.is_absolute()
        or path.as_posix() != relative
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise PartitionCollectionError(
            f"Git returned an unsafe partition input path: {relative!r}",
        )
    return relative


def _head_entries(
    repository: Path,
    commit: str,
) -> dict[str, tuple[str, str]]:
    """Return exact regular path, mode, and blob identities from ``commit``."""
    entries: dict[str, tuple[str, str]] = {}
    output = _git_output(repository, "ls-tree", "-r", "-z", commit, "--")
    for record in output.split(b"\0"):
        if not record:
            continue
        try:
            metadata, raw_path = record.split(b"\t", 1)
            mode, object_type, object_id = metadata.decode("ascii").split()
        except (UnicodeDecodeError, ValueError) as error:
            raise PartitionCollectionError(
                "Git returned a malformed partition HEAD entry",
            ) from error
        relative = _decode_git_path(raw_path)
        if mode not in _REGULAR_GIT_MODES or object_type != "blob":
            raise PartitionCollectionError(
                "partition inputs require regular tracked blobs: "
                f"{relative!r}",
            )
        if relative in entries:
            raise PartitionCollectionError(
                f"Git returned duplicate partition HEAD path {relative!r}",
            )
        entries[relative] = (mode, object_id)
    return entries


def _index_entries(repository: Path) -> dict[str, tuple[str, str, str]]:
    """Return flag, mode, and blob identity for every stage-zero index path."""
    entries: dict[str, tuple[str, str, str]] = {}
    output = _git_output(repository, "ls-files", "--stage", "-v", "-z")
    for record in output.split(b"\0"):
        if not record:
            continue
        try:
            raw_flag, remainder = record.split(b" ", 1)
            metadata, raw_path = remainder.split(b"\t", 1)
            mode, object_id, stage = metadata.decode("ascii").split()
            flag = raw_flag.decode("ascii")
        except (UnicodeDecodeError, ValueError) as error:
            raise PartitionCollectionError(
                "Git returned a malformed partition index entry",
            ) from error
        relative = _decode_git_path(raw_path)
        if len(flag) != 1 or stage != "0":
            raise PartitionCollectionError(
                "partition revision requires a stage-zero Git index",
            )
        if mode not in _REGULAR_GIT_MODES:
            raise PartitionCollectionError(
                "partition inputs require regular index blobs: "
                f"{relative!r}",
            )
        if relative in entries:
            raise PartitionCollectionError(
                f"Git returned duplicate partition index path {relative!r}",
            )
        entries[relative] = (flag, mode, object_id)
    return entries


def _reject_nonstandard_index_flags(
    index: Mapping[str, tuple[str, str, str]],
) -> None:
    unsupported = sorted(
        (flag, relative)
        for relative, (flag, _mode, _object_id) in index.items()
        if flag != "H"
    )
    if unsupported:
        raise PartitionCollectionError(
            "partition inputs use unsupported Git index flags: "
            f"{unsupported[:5]!r}",
        )


def _untracked_paths(repository: Path) -> tuple[str, ...]:
    """Return exact nonignored, nontracked paths in canonical order."""
    output = _git_output(
        repository,
        "ls-files",
        "--others",
        "--exclude-standard",
        "-z",
    )
    paths = tuple(
        sorted(
            _decode_git_path(raw_path)
            for raw_path in output.split(b"\0")
            if raw_path
        ),
    )
    if len(paths) != len(set(paths)):
        raise PartitionCollectionError(
            "Git returned duplicate untracked partition input paths",
        )
    return paths


def _is_generated_collection_output(relative: str) -> bool:
    """Return whether one ignored path is an explicit generated/cache output."""
    parts = PurePosixPath(relative).parts
    if any(
        part in {
            "__pycache__",
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
            "node_modules",
        }
        or part.endswith(".egg-info")
        for part in parts
    ):
        return True
    if parts and parts[0] in {
        ".venv",
        "artifacts",
        "build",
        "dist",
        "site",
    }:
        return True
    if len(parts) > 1 and parts[:2] in {
        ("data", "terrain_cache"),
        ("docs", "articles"),
        ("docs", "evidence"),
        ("frontend", "dist"),
    }:
        return True
    if len(parts) > 2 and parts[:3] == ("scripts", "visualize", "output"):
        return True
    if len(parts) == 2 and parts[0] == "scripts":
        filename = parts[1]
        return (
            (filename.startswith("evaluation_results") and filename.endswith(".json"))
            or (filename.startswith("evaluation_stderr") and filename.endswith(".log"))
            or filename == "falk_test.json"
        )
    return False


def _git_path_is_ignored(repository: Path, relative: str) -> bool:
    payload = relative.encode("utf-8") + b"\0"
    output = _git_output(
        repository,
        "check-ignore",
        "--no-index",
        "-z",
        "--stdin",
        input_payload=payload,
        allow_no_match=True,
    )
    if output not in {b"", payload}:
        raise PartitionCollectionError(
            "Git returned a malformed ignored partition path",
        )
    return bool(output)


def _raise_ignored_collection_input(relative: str) -> None:
    label = (
        "pytest configuration"
        if relative in _ROOT_PYTEST_CONFIGS
        else "file"
    )
    raise PartitionCollectionError(
        f"ignored {label} can alter partition collection: {relative!r}",
    )


def _reject_ignored_collection_inputs(repository: Path) -> None:
    """Reject every ignored checkout input outside explicit output roots."""
    collapsed = _git_output(
        repository,
        "ls-files",
        "--others",
        "--ignored",
        "--exclude-standard",
        "--directory",
        "-z",
    )
    for raw_path in (item for item in collapsed.split(b"\0") if item):
        relative = _decode_git_path(raw_path.rstrip(b"/"))
        path = repository.joinpath(*PurePosixPath(relative).parts)
        try:
            metadata = path.lstat()
        except OSError as error:
            raise PartitionCollectionError(
                f"cannot inspect ignored partition input {relative!r}",
            ) from error
        if stat.S_ISLNK(metadata.st_mode):
            raise PartitionCollectionError(
                "ignored partition inputs do not permit symlinks: "
                f"{relative!r}",
            )
        if not (
            stat.S_ISREG(metadata.st_mode)
            or stat.S_ISDIR(metadata.st_mode)
        ):
            raise PartitionCollectionError(
                "ignored partition input must be a regular file or directory: "
                f"{relative!r}",
            )
        if _is_generated_collection_output(relative):
            continue
        if stat.S_ISREG(metadata.st_mode) or _git_path_is_ignored(
            repository,
            relative,
        ):
            _raise_ignored_collection_input(relative)

    detailed = _git_output(
        repository,
        "ls-files",
        "--others",
        "--ignored",
        "--exclude-standard",
        "-z",
        "--",
        ".",
        *_IGNORED_OUTPUT_EXCLUDE_PATHSPECS,
    )
    for raw_path in (item for item in detailed.split(b"\0") if item):
        relative = _decode_git_path(raw_path)
        path = repository.joinpath(*PurePosixPath(relative).parts)
        try:
            metadata = path.lstat()
        except OSError as error:
            raise PartitionCollectionError(
                f"cannot inspect ignored partition input {relative!r}",
            ) from error
        if stat.S_ISLNK(metadata.st_mode):
            raise PartitionCollectionError(
                "ignored partition inputs do not permit symlinks: "
                f"{relative!r}",
            )
        if not stat.S_ISREG(metadata.st_mode):
            raise PartitionCollectionError(
                "ignored partition input must be a regular file: "
                f"{relative!r}",
            )
        if _is_generated_collection_output(relative):
            raise PartitionCollectionError(
                "ignored-output pathspecs do not match the output policy: "
                f"{relative!r}",
            )
        _raise_ignored_collection_input(relative)


def _checkout_entry(repository: Path, relative: str) -> dict[str, object]:
    """Capture one raw regular file without following filesystem indirection."""
    path = repository.joinpath(*PurePosixPath(relative).parts)
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return {"kind": "missing", "path": relative}
    except OSError as error:
        raise PartitionCollectionError(
            f"cannot inspect partition input {relative!r}",
        ) from error
    if stat.S_ISLNK(metadata.st_mode):
        raise PartitionCollectionError(
            f"partition inputs do not permit symlinks: {relative!r}",
        )
    if not stat.S_ISREG(metadata.st_mode):
        raise PartitionCollectionError(
            f"partition input must be a regular file: {relative!r}",
        )

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise PartitionCollectionError(
            f"cannot open partition input {relative!r}",
        ) from error
    digest = hashlib.sha256()
    size = 0
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_dev != metadata.st_dev
            or opened.st_ino != metadata.st_ino
        ):
            raise PartitionCollectionError(
                f"partition input changed during capture: {relative!r}",
            )
        while payload := os.read(descriptor, 1024 * 1024):
            digest.update(payload)
            size += len(payload)
        final = os.fstat(descriptor)
        if (
            final.st_dev != opened.st_dev
            or final.st_ino != opened.st_ino
            or final.st_mode != opened.st_mode
            or final.st_size != opened.st_size
            or final.st_mtime_ns != opened.st_mtime_ns
            or final.st_ctime_ns != opened.st_ctime_ns
            or size != final.st_size
        ):
            raise PartitionCollectionError(
                f"partition input changed during capture: {relative!r}",
            )
    finally:
        os.close(descriptor)
    mode = "100755" if opened.st_mode & 0o111 else "100644"
    return {
        "kind": "regular",
        "mode": mode,
        "path": relative,
        "sha256": digest.hexdigest(),
        "size": size,
    }


def _checkout_manifest(
    repository: Path,
    head: Mapping[str, tuple[str, str]],
    index: Mapping[str, tuple[str, str, str]],
    untracked: Sequence[str],
) -> tuple[tuple[dict[str, object], ...], str]:
    """Capture the exact current raw checkout union used by collection."""
    paths = sorted(set(head) | set(index) | set(untracked))
    entries = tuple(_checkout_entry(repository, relative) for relative in paths)
    return entries, _canonical_digest(entries)


def _verify_clean_checkout(
    repository: Path,
    head: Mapping[str, tuple[str, str]],
    index: Mapping[str, tuple[str, str, str]],
    manifest: Sequence[Mapping[str, object]],
) -> None:
    """Bind a nominally clean checkout to exact HEAD paths, modes, and bytes."""
    if set(index) != set(head):
        missing = sorted(set(head) - set(index))
        added = sorted(set(index) - set(head))
        raise PartitionCollectionError(
            "clean partition index paths differ from HEAD: "
            f"missing={missing[:5]!r}, added={added[:5]!r}",
        )
    mismatched_index = sorted(
        relative
        for relative, (_flag, mode, object_id) in index.items()
        if (mode, object_id) != head[relative]
    )
    if mismatched_index:
        raise PartitionCollectionError(
            "clean partition index differs from HEAD: "
            f"{mismatched_index[:5]!r}",
        )

    current = {str(entry["path"]): entry for entry in manifest}
    if set(current) != set(head):
        raise PartitionCollectionError(
            "clean partition worktree paths differ from HEAD",
        )
    mismatched_modes = sorted(
        relative
        for relative, (mode, _object_id) in head.items()
        if current[relative].get("kind") != "regular"
        or current[relative].get("mode") != mode
    )
    if mismatched_modes:
        raise PartitionCollectionError(
            "clean partition worktree modes differ from HEAD: "
            f"{mismatched_modes[:5]!r}",
        )

    ordered_paths = tuple(sorted(head))
    hash_input = ("\n".join(ordered_paths) + "\n").encode("utf-8")
    hash_output = _git_output(
        repository,
        "hash-object",
        "--no-filters",
        "--stdin-paths",
        input_payload=hash_input,
    )
    try:
        current_hashes = hash_output.decode("ascii").splitlines()
    except UnicodeDecodeError as error:
        raise PartitionCollectionError(
            "Git returned invalid raw partition input hashes",
        ) from error
    if len(current_hashes) != len(ordered_paths):
        raise PartitionCollectionError(
            "Git did not hash every clean partition input",
        )
    mismatched_bytes = [
        relative
        for relative, object_id in zip(
            ordered_paths,
            current_hashes,
            strict=True,
        )
        if object_id != head[relative][1]
    ]
    if mismatched_bytes:
        raise PartitionCollectionError(
            "clean partition input bytes differ from HEAD: "
            f"{mismatched_bytes[:5]!r}",
        )


def repository_revision(root: Path = REPOSITORY_ROOT) -> dict[str, object]:
    """Return a content-sensitive Git identity for manifest reuse.

    CI normally produces the compact clean-worktree identity.  Dirty local
    audits remain usable, but are bound to the exact tracked diff and raw
    nonignored checkout manifest so a later runner cannot silently reuse stale
    node IDs.  Ignored collection inputs and filesystem indirection fail
    closed.
    """

    repository = Path(
        _git_output(root, "rev-parse", "--show-toplevel")
        .decode("utf-8")
        .strip(),
    ).resolve()
    commit = _git_output(repository, "rev-parse", "HEAD").decode("ascii").strip()
    if len(commit) != 40 or any(character not in "0123456789abcdef" for character in commit):
        raise PartitionCollectionError("Git returned an invalid partition-manifest commit")

    head = _head_entries(repository, commit)
    index = _index_entries(repository)
    _reject_nonstandard_index_flags(index)
    _reject_ignored_collection_inputs(repository)
    status = _git_output(
        repository,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    )
    untracked_paths = _untracked_paths(repository)
    manifest, manifest_sha256 = _checkout_manifest(
        repository,
        head,
        index,
        untracked_paths,
    )
    dirty = bool(status)
    if not dirty:
        _verify_clean_checkout(repository, head, index, manifest)
        fingerprint = _canonical_digest({"commit": commit, "dirty": False})
    else:
        tracked_diff = _git_output(
            repository,
            "diff",
            "--binary",
            "--full-index",
            "HEAD",
            "--",
        )
        manifest_by_path = {
            str(entry["path"]): entry
            for entry in manifest
        }
        untracked = [
            manifest_by_path[relative]
            for relative in untracked_paths
        ]
        fingerprint = _canonical_digest(
            {
                "checkout_manifest_sha256": manifest_sha256,
                "commit": commit,
                "dirty": True,
                "status_sha256": hashlib.sha256(status).hexdigest(),
                "tracked_diff_sha256": hashlib.sha256(tracked_diff).hexdigest(),
                "untracked": untracked,
            },
        )

    final_commit = _git_output(repository, "rev-parse", "HEAD").decode("ascii").strip()
    if final_commit != commit:
        raise PartitionCollectionError(
            "Git HEAD changed during partition revision capture",
        )
    final_index = _index_entries(repository)
    _reject_nonstandard_index_flags(final_index)
    if final_index != index:
        raise PartitionCollectionError(
            "Git index changed during partition revision capture",
        )
    final_status = _git_output(
        repository,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    )
    if final_status != status:
        raise PartitionCollectionError(
            "Git status changed during partition revision capture",
        )
    final_untracked_paths = _untracked_paths(repository)
    if final_untracked_paths != untracked_paths:
        raise PartitionCollectionError(
            "untracked paths changed during partition revision capture",
        )
    _final_manifest, final_manifest_sha256 = _checkout_manifest(
        repository,
        head,
        final_index,
        final_untracked_paths,
    )
    if final_manifest_sha256 != manifest_sha256:
        raise PartitionCollectionError(
            "checkout bytes changed during partition revision capture",
        )
    _reject_ignored_collection_inputs(repository)
    return {
        "commit": commit,
        "dirty": dirty,
        "worktree_fingerprint": fingerprint,
    }


def partition_selector_payload(partition: str) -> dict[str, object]:
    """Return the JSON selector contract for one named partition."""

    specification = PARTITION_SPECS[partition]
    return {
        "paths": list(specification.paths),
        "ignored_paths": list(specification.ignored_paths),
        "marker_expression": specification.marker_expression,
    }


def validate_partition_sets(
    superset: Sequence[str],
    partitions: Mapping[str, Sequence[str]],
) -> None:
    """Reject empty, overlapping, missing, or extra partition node-ID sets."""

    superset_set = set(superset)
    errors: list[str] = []
    for name in AUDITED_PARTITIONS:
        node_ids = set(partitions.get(name, ()))
        if not node_ids:
            errors.append(f"partition {name!r} is empty")
        outside = sorted(node_ids - superset_set)
        if outside:
            errors.append(
                f"partition {name!r} contains {len(outside)} nodes outside "
                f"superset; first={outside[0]!r}",
            )

    for left, right in combinations(AUDITED_PARTITIONS, 2):
        overlap = sorted(
            set(partitions.get(left, ())) & set(partitions.get(right, ())),
        )
        if overlap:
            errors.append(
                f"partitions {left!r} and {right!r} overlap on "
                f"{len(overlap)} nodes; first={overlap[0]!r}",
            )

    union: set[str] = set()
    for name in AUDITED_PARTITIONS:
        union.update(partitions.get(name, ()))
    missing = sorted(superset_set - union)
    extra = sorted(union - superset_set)
    if missing:
        errors.append(
            f"partition union misses {len(missing)} superset nodes; "
            f"first={missing[0]!r}",
        )
    if extra:
        errors.append(
            f"partition union contains {len(extra)} extra nodes; first={extra[0]!r}",
        )
    if errors:
        raise ValueError("\n".join(errors))


def _manifest_nodes(value: object, *, label: str) -> tuple[str, ...]:
    if not isinstance(value, Mapping):
        raise PartitionCollectionError(f"audit manifest {label} must be an object")
    raw_nodes = value.get("node_ids")
    if not isinstance(raw_nodes, list) or not all(isinstance(item, str) for item in raw_nodes):
        raise PartitionCollectionError(f"audit manifest {label}.node_ids must be a string list")
    node_ids = tuple(raw_nodes)
    if not node_ids:
        raise PartitionCollectionError(f"audit manifest {label} is empty")
    if node_ids != tuple(sorted(node_ids)) or len(set(node_ids)) != len(node_ids):
        raise PartitionCollectionError(
            f"audit manifest {label}.node_ids must be sorted and unique",
        )
    if any(not _is_node_id_line(node_id) for node_id in node_ids):
        raise PartitionCollectionError(f"audit manifest {label} contains an invalid node ID")
    count = value.get("count")
    if type(count) is not int or count != len(node_ids):
        raise PartitionCollectionError(f"audit manifest {label}.count is inconsistent")
    if value.get("node_ids_sha256") != _node_id_digest(node_ids):
        raise PartitionCollectionError(
            f"audit manifest {label}.node_ids_sha256 is inconsistent",
        )
    return node_ids


def validate_audit_manifest_payload(
    payload: object,
    *,
    current_revision: Mapping[str, object],
    manifest_sha256: str = "",
) -> ValidatedAuditManifest:
    """Validate all immutable collection evidence before any node is reused."""

    if not isinstance(payload, Mapping):
        raise PartitionCollectionError("audit manifest root must be an object")
    if payload.get("schema_version") != AUDIT_MANIFEST_SCHEMA_VERSION:
        raise PartitionCollectionError(
            "audit manifest schema_version must be "
            f"{AUDIT_MANIFEST_SCHEMA_VERSION}",
        )
    revision = payload.get("revision")
    if not isinstance(revision, Mapping) or dict(revision) != dict(current_revision):
        raise PartitionCollectionError(
            "audit manifest revision does not match the current worktree",
        )
    if payload.get("exact_union") is not True or payload.get("pairwise_disjoint") is not True:
        raise PartitionCollectionError(
            "audit manifest does not attest an exact pairwise-disjoint union",
        )

    superset = _manifest_nodes(payload.get("superset"), label="superset")
    raw_partitions = payload.get("partitions")
    if not isinstance(raw_partitions, Mapping):
        raise PartitionCollectionError("audit manifest partitions must be an object")
    if set(raw_partitions) != set(AUDITED_PARTITIONS):
        raise PartitionCollectionError(
            "audit manifest partitions do not match the authoritative partition set",
        )

    partitions: dict[str, tuple[str, ...]] = {}
    for name in AUDITED_PARTITIONS:
        record = raw_partitions[name]
        if not isinstance(record, Mapping):
            raise PartitionCollectionError(
                f"audit manifest partition {name!r} must be an object",
            )
        if record.get("selector") != partition_selector_payload(name):
            raise PartitionCollectionError(
                f"audit manifest partition {name!r} selector has drifted",
            )
        partitions[name] = _manifest_nodes(record, label=f"partitions.{name}")
    try:
        validate_partition_sets(superset, partitions)
    except ValueError as error:
        raise PartitionCollectionError(
            f"audit manifest partition contract is invalid: {error}",
        ) from error

    return ValidatedAuditManifest(
        revision=dict(revision),
        superset=superset,
        partitions=partitions,
        manifest_sha256=manifest_sha256,
    )


def load_audit_manifest(
    path: Path,
    *,
    root: Path = REPOSITORY_ROOT,
) -> ValidatedAuditManifest:
    """Load a partition audit only when it matches the current revision."""

    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PartitionCollectionError(f"cannot read audit manifest {path}: {error}") from error
    return validate_audit_manifest_payload(
        payload,
        current_revision=repository_revision(root),
        manifest_sha256=hashlib.sha256(raw).hexdigest(),
    )


def _sharding_evidence(
    plan: ShardPlan,
    *,
    shard_index: int,
) -> dict[str, object]:
    selected_module_ids = tuple(
        sorted({_module_id(node_id) for node_id in plan.shards[shard_index]})
    )
    return {
        "strategy": plan.strategy,
        "module_count": len(plan.module_ids),
        "module_ids": list(plan.module_ids),
        "split_module_ids": list(plan.split_module_ids),
        "selected_module_count": len(selected_module_ids),
        "selected_module_ids": list(selected_module_ids),
    }


def _write_manifest(
    path: Path,
    *,
    partition: str,
    all_node_ids: Sequence[str],
    selected_node_ids: Sequence[str],
    shard_index: int,
    shard_count: int,
    timeout_seconds: int | None,
    forbid_skips: bool,
    shard_plan: ShardPlan,
    collection_source: Mapping[str, object],
) -> None:
    specification = PARTITION_SPECS[partition]
    payload = {
        "schema_version": 2,
        "partition": partition,
        "selector": {
            "paths": list(specification.paths),
            "ignored_paths": list(specification.ignored_paths),
            "marker_expression": specification.marker_expression,
        },
        "all_node_count": len(all_node_ids),
        "all_node_ids_sha256": _node_id_digest(all_node_ids),
        "all_node_ids": list(all_node_ids),
        "sharding": _sharding_evidence(
            shard_plan,
            shard_index=shard_index,
        ),
        "shard": {
            "index": shard_index,
            "count": shard_count,
            "selected_node_count": len(selected_node_ids),
            "selected_node_ids_sha256": _node_id_digest(selected_node_ids),
            "selected_node_ids": list(selected_node_ids),
        },
        "collection_timeout_seconds": COLLECTION_TIMEOUT_SECONDS,
        "operational_timeout_seconds": timeout_seconds,
        "forbid_skips": forbid_skips,
        "collection_source": dict(collection_source),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_result(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"schema_version": 1, **payload}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_node_id_argfile(path: Path, node_ids: Sequence[str]) -> None:
    """Persist exact shard node IDs without expanding the process argv."""

    if not node_ids:
        raise PartitionCollectionError("pytest shard argument file cannot be empty")
    for node_id in node_ids:
        if not _is_node_id_line(node_id) or "\n" in node_id or "\r" in node_id:
            raise PartitionCollectionError(f"invalid pytest node ID for argument file: {node_id!r}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(f"{node_id}\n" for node_id in node_ids),
        encoding="utf-8",
    )


def _subprocess_environment(pycache_prefix: str) -> dict[str, str]:
    environment = os.environ.copy()
    for variable in (
        "PYTHONHOME",
        "PYTHONPATH",
        "PYTEST_ADDOPTS",
        "PYTEST_PLUGINS",
    ):
        environment.pop(variable, None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONHASHSEED"] = "0"
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PYTHONPYCACHEPREFIX"] = pycache_prefix
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    return environment


def _validated_exit_code(
    *,
    pytest_exit_code: int,
    counts: dict[str, int | bool],
    selected_count: int,
    forbid_skips: bool,
) -> tuple[int, str | None]:
    """Fail closed when a nominally green run lacks complete evidence."""

    if pytest_exit_code != 0:
        return pytest_exit_code, None
    if counts["summary_found"] is not True:
        return 4, "pytest returned success without a parseable outcome summary"
    if int(counts["failed"]) > 0 or int(counts["errors"]) > 0:
        return (
            4,
            "pytest returned success while its outcome summary reported "
            f"failed={counts['failed']} errors={counts['errors']}",
        )

    terminal_total = sum(
        int(counts[name])
        for name in (
            "passed",
            "failed",
            "errors",
            "skipped",
            "xfailed",
            "xpassed",
        )
    )
    if terminal_total != selected_count:
        return (
            4,
            "pytest success did not account for every selected node: "
            f"outcomes={terminal_total} selected={selected_count}",
        )
    if forbid_skips and int(counts["skipped"]) > 0:
        return (
            4,
            f"partition forbids skipped nodes: skipped={counts['skipped']}",
        )
    return 0, None


def _junit_evidence_error(
    path: Path,
    *,
    selected_count: int,
    forbid_skips: bool,
) -> str | None:
    """Return a fail-closed diagnostic for missing or inconsistent JUnit."""

    if not path.is_file() or path.stat().st_size == 0:
        return "pytest did not produce a non-empty JUnit artifact"
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as error:
        return f"pytest JUnit artifact is unreadable: {error}"

    suites = [root] if root.tag.endswith("testsuite") else list(root)
    suites = [suite for suite in suites if suite.tag.endswith("testsuite")]
    if not suites:
        return "pytest JUnit artifact contains no test suites"

    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in suites:
        for name in totals:
            raw_value = suite.attrib.get(name)
            if raw_value is None:
                return f"pytest JUnit suite is missing {name!r}"
            try:
                value = int(raw_value)
            except ValueError:
                return f"pytest JUnit suite has invalid {name!r}: {raw_value!r}"
            if value < 0:
                return f"pytest JUnit suite has negative {name!r}"
            totals[name] += value

    if totals["tests"] != selected_count:
        return (
            f"pytest JUnit does not account for every selected node: tests={totals['tests']} selected={selected_count}"
        )
    if totals["failures"] > 0 or totals["errors"] > 0:
        return f"pytest JUnit reports unsuccessful outcomes: failures={totals['failures']} errors={totals['errors']}"
    if forbid_skips and totals["skipped"] > 0:
        return f"partition forbids skipped JUnit outcomes: skipped={totals['skipped']}"
    return None


def run_partition(
    partition: str,
    *,
    manifest_path: Path,
    junit_path: Path,
    shard_index: int,
    shard_count: int,
    timeout_seconds: int | None,
    forbid_skips: bool,
    audit_manifest_path: Path | None = None,
    root: Path = REPOSITORY_ROOT,
) -> int:
    """Select, manifest, and execute one partition or deterministic shard."""

    result_path = manifest_path.with_name("result.json")
    argument_path = manifest_path.with_name("selection.args")
    if (
        audit_manifest_path is not None
        and audit_manifest_path.resolve() == manifest_path.resolve()
    ):
        raise PartitionCollectionError(
            "audit manifest and execution manifest must be different files",
        )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    junit_path.parent.mkdir(parents=True, exist_ok=True)
    # No evidence file from an earlier invocation may survive a failed
    # collection and appear to describe this run.
    manifest_path.unlink(missing_ok=True)
    result_path.unlink(missing_ok=True)
    argument_path.unlink(missing_ok=True)
    junit_path.unlink(missing_ok=True)

    if audit_manifest_path is None:
        all_node_ids = collect_partition_node_ids(partition, root=root)
        collection_source: Mapping[str, object] = {
            "kind": "fresh_pytest_collection",
        }
    else:
        if partition not in AUDITED_PARTITIONS:
            raise PartitionCollectionError(
                f"partition {partition!r} is not present in the exact audit manifest",
            )
        audit_manifest = load_audit_manifest(audit_manifest_path, root=root)
        all_node_ids = audit_manifest.partitions[partition]
        collection_source = {
            "kind": "revision_bound_audit_manifest",
            "manifest_sha256": audit_manifest.manifest_sha256,
            "revision": dict(audit_manifest.revision),
        }
    if shard_count <= 0:
        raise ValueError("shard_count must be positive")
    if shard_index < 0 or shard_index >= shard_count:
        raise ValueError(f"shard_index must be in [0, {shard_count - 1}], got {shard_index}")
    shard_plan = _plan_shards(all_node_ids, shard_count=shard_count)
    selected_node_ids = shard_plan.shards[shard_index]
    if not selected_node_ids:
        raise PartitionCollectionError(f"{partition} shard {shard_index + 1}/{shard_count} is empty")

    _write_manifest(
        manifest_path,
        partition=partition,
        all_node_ids=all_node_ids,
        selected_node_ids=selected_node_ids,
        shard_index=shard_index,
        shard_count=shard_count,
        timeout_seconds=timeout_seconds,
        forbid_skips=forbid_skips,
        shard_plan=shard_plan,
        collection_source=collection_source,
    )
    _write_node_id_argfile(argument_path, selected_node_ids)
    execution_selector = (f"@{argument_path.resolve()}",)
    command = _pytest_command(
        "--tb=short",
        "-q",
        f"--junitxml={junit_path}",
        *execution_selector,
    )
    print(f"RUN_COMMAND={_command_text(command)}", flush=True)
    print(
        f"RUN_SELECTION={partition} shard={shard_index + 1}/{shard_count} nodes={len(selected_node_ids)}",
        flush=True,
    )

    try:
        with tempfile.TemporaryDirectory(
            prefix="stochastic-warfare-pycache-",
        ) as pycache_prefix:
            completed = subprocess.run(
                command,
                cwd=root,
                check=False,
                timeout=timeout_seconds,
                env=_subprocess_environment(pycache_prefix),
                capture_output=True,
                text=True,
            )
    except subprocess.TimeoutExpired as error:
        partial_output = _timeout_output(error)
        if partial_output:
            print(partial_output, end="" if partial_output.endswith("\n") else "\n")
        print(
            f"PYTEST_TIMEOUT partition={partition} shard={shard_index + 1}/{shard_count} seconds={timeout_seconds}",
            file=sys.stderr,
            flush=True,
        )
        _write_result(
            result_path,
            {
                "partition": partition,
                "shard_index": shard_index,
                "shard_count": shard_count,
                "status": "timeout",
                "timeout_seconds": timeout_seconds,
                "exit_code": 124,
                "sharding": _sharding_evidence(
                    shard_plan,
                    shard_index=shard_index,
                ),
            },
        )
        return 124
    except OSError as error:
        print(
            f"PYTEST_LAUNCH_ERROR partition={partition} shard={shard_index + 1}/{shard_count}: {error}",
            file=sys.stderr,
            flush=True,
        )
        _write_result(
            result_path,
            {
                "partition": partition,
                "shard_index": shard_index,
                "shard_count": shard_count,
                "status": "launch_error",
                "error": str(error),
                "exit_code": 3,
                "sharding": _sharding_evidence(
                    shard_plan,
                    shard_index=shard_index,
                ),
            },
        )
        return 3

    pytest_output = f"{completed.stdout}\n{completed.stderr}".strip()
    if pytest_output:
        print(pytest_output, flush=True)
    counts = _result_counts(pytest_output)
    counts["collected"] = len(selected_node_ids)
    counts["pytest_exit_code"] = completed.returncode
    exit_code, evidence_error = _validated_exit_code(
        pytest_exit_code=completed.returncode,
        counts=counts,
        selected_count=len(selected_node_ids),
        forbid_skips=forbid_skips,
    )
    junit_error = _junit_evidence_error(
        junit_path,
        selected_count=len(selected_node_ids),
        forbid_skips=forbid_skips,
    )
    if junit_error is not None:
        evidence_error = junit_error if evidence_error is None else f"{evidence_error}; {junit_error}"
        if exit_code == 0:
            exit_code = 4
    counts["exit_code"] = exit_code
    if evidence_error is not None:
        print(f"PYTEST_EVIDENCE_ERROR={evidence_error}", file=sys.stderr)
    print(f"PYTEST_COUNTS={json.dumps(counts, sort_keys=True)}", flush=True)
    print(f"PYTEST_EXIT_CODE={exit_code}", flush=True)
    _write_result(
        result_path,
        {
            "partition": partition,
            "shard_index": shard_index,
            "shard_count": shard_count,
            "status": "passed" if exit_code == 0 else "failed",
            "counts": counts,
            "error": evidence_error,
            "exit_code": exit_code,
            "sharding": _sharding_evidence(
                shard_plan,
                shard_index=shard_index,
            ),
        },
    )
    return exit_code


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("partition", choices=tuple(PARTITION_SPECS))
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument(
        "--audit-manifest",
        type=Path,
        help=(
            "Reuse one revision-bound exact collection audit instead of "
            "recollecting this partition."
        ),
    )
    parser.add_argument("--junit", required=True, type=Path)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        help="Operational containment timeout; not performance evidence.",
    )
    parser.add_argument(
        "--forbid-skips",
        action="store_true",
        help="Fail when any selected node reports a skipped outcome.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    if arguments.timeout_seconds is not None and arguments.timeout_seconds <= 0:
        _parser().error("--timeout-seconds must be positive")
    try:
        return run_partition(
            arguments.partition,
            manifest_path=arguments.manifest,
            junit_path=arguments.junit,
            shard_index=arguments.shard_index,
            shard_count=arguments.shard_count,
            timeout_seconds=arguments.timeout_seconds,
            forbid_skips=arguments.forbid_skips,
            audit_manifest_path=arguments.audit_manifest,
        )
    except (PartitionCollectionError, ValueError) as error:
        print(f"PARTITION_ERROR={error}", file=sys.stderr)
        _write_result(
            arguments.manifest.with_name("result.json"),
            {
                "partition": arguments.partition,
                "shard_index": arguments.shard_index,
                "shard_count": arguments.shard_count,
                "status": "collection_error",
                "collection_timeout_seconds": (
                    COLLECTION_TIMEOUT_SECONDS
                ),
                "error": str(error),
                "exit_code": 3,
            },
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
