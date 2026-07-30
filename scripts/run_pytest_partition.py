"""Collect and run one explicit Phase 112 pytest partition.

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
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
COLLECTION_TIMEOUT_SECONDS = 300

TERRAIN_TEST_FILES = (
    "tests/unit/test_phase_15a_pipeline_heightmap.py",
    "tests/unit/test_phase_15b_classification_infrastructure.py",
    "tests/unit/test_phase_15c_bathymetry.py",
    "tests/unit/test_phase_15d_integration.py",
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


def _pytest_command(*arguments: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "pytest",
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
        completed = subprocess.run(
            command,
            cwd=root,
            check=False,
            timeout=COLLECTION_TIMEOUT_SECONDS,
            capture_output=True,
            text=True,
            env=_subprocess_environment(),
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
) -> None:
    specification = PARTITION_SPECS[partition]
    payload = {
        "schema_version": 1,
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


def _subprocess_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.setdefault("PYTHONDONTWRITEBYTECODE", "1")
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
    root: Path = REPOSITORY_ROOT,
) -> int:
    """Collect, manifest, and execute one partition or deterministic shard."""

    result_path = manifest_path.with_name("result.json")
    argument_path = manifest_path.with_name("selection.args")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    junit_path.parent.mkdir(parents=True, exist_ok=True)
    # No evidence file from an earlier invocation may survive a failed
    # collection and appear to describe this run.
    manifest_path.unlink(missing_ok=True)
    result_path.unlink(missing_ok=True)
    argument_path.unlink(missing_ok=True)
    junit_path.unlink(missing_ok=True)

    all_node_ids = collect_partition_node_ids(partition, root=root)
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
        completed = subprocess.run(
            command,
            cwd=root,
            check=False,
            timeout=timeout_seconds,
            env=_subprocess_environment(),
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
