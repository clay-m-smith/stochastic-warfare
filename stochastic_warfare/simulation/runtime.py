"""Typed construction boundary for production simulation runtimes.

The boundary in this module deliberately owns the pieces that used to be
reimplemented by analysis, API, MCP, validation, and benchmark consumers:
source configuration preparation, effective calibration variants, roster
preflight, victory construction, and fresh ``SimulationEngine`` sessions.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
import stat
import subprocess
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Sequence

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from stochastic_warfare.build_identity import (
    BUILD_IDENTITY_RELATIVE_PATH,
    BuildIdentityError,
    load_verified_build_identity,
)
from stochastic_warfare.core.strict_yaml import load_yaml_unique
from stochastic_warfare.core.types import Position
from stochastic_warfare.core.era import EraConfig, get_era_config
from stochastic_warfare.simulation.battle import BattleConfig
from stochastic_warfare.simulation.calibration import CalibrationSchema
from stochastic_warfare.core.indexed_rng import FOWIndexedIntervalRecord
from stochastic_warfare.simulation.campaign import CampaignConfig
from stochastic_warfare.simulation.engine import (
    EngineConfig,
    RuntimeExecutionMode,
    SimulationEngine,
    SimulationRunResult,
    SuppressedRuntimeFailure,
)
from stochastic_warfare.simulation.era_runtime import EraRuntimeContract
from stochastic_warfare.simulation.performance_flags import (
    PerformanceExecutionReceipt,
)
from stochastic_warfare.simulation.recorder import SimulationRecorder
from stochastic_warfare.simulation.scenario import (
    CampaignScenarioConfig,
    DoctrineSideAssignment,
    ScenarioLoader,
    SimulationContext,
    load_campaign_scenario_config,
    parse_campaign_scenario_config,
    parse_scenario_start_time,
)
from stochastic_warfare.simulation.victory import (
    ObjectiveState,
    VictoryEvaluator,
)


class AnalysisInputError(ValueError):
    """User-authored analysis input is invalid before execution."""


def _json_value(value: Any) -> Any:
    """Return one strict canonical-JSON-compatible public value."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _json_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _json_value(nested) for key, nested in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(nested) for nested in value]
    if isinstance(value, (set, frozenset)):
        return [_json_value(nested) for nested in sorted(value, key=str)]
    if isinstance(value, Path):
        return value.as_posix()
    return value


def _canonical_digest(value: Any) -> str:
    """Return a deterministic SHA-256 for one public typed value."""
    encoded = json.dumps(
        _json_value(value),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class CodeRevision:
    """Exact repository identity without inventing cleanliness."""

    commit: str
    dirty: bool
    worktree_fingerprint: str


@dataclass(frozen=True)
class UnitCommandAssignment:
    """One exact runtime unit's profile and doctrinal-school assignment."""

    unit_id: str
    side: str
    commander_profile_id: str | None
    doctrine_school_id: str | None


@dataclass(frozen=True)
class RuntimeProvenance:
    """Production-derived static and arrival-aware runtime provenance."""

    code_revision: CodeRevision
    data_revision: str
    data_file_count: int
    catalog_revision: str
    doctrine_catalog_fingerprint: str
    doctrine_assignment_fingerprint: str
    loaded_roster_loadout_fingerprint: str
    final_roster_loadout_fingerprint: str
    initial_unit_assignments: tuple[UnitCommandAssignment, ...]
    arriving_unit_assignments: tuple[UnitCommandAssignment, ...]
    execution_mode: RuntimeExecutionMode = RuntimeExecutionMode.STRICT
    suppressed_failures: tuple[SuppressedRuntimeFailure, ...] = ()

    @property
    def authoritative(self) -> bool:
        """Whether this provenance is eligible for acceptance evidence."""
        return (
            self.execution_mode is RuntimeExecutionMode.STRICT
            and not self.suppressed_failures
        )


def _run_git(
    repo: Path,
    *arguments: str,
    input_payload: bytes | None = None,
) -> bytes:
    return subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=True,
        capture_output=True,
        input=input_payload,
    ).stdout


_RUNTIME_SOURCE_ROOTS = ("api", "stochastic_warfare")
_RUNTIME_STARTUP_MODULE_NAMES = ("sitecustomize", "usercustomize")
_ROOT_RUNTIME_MODULE_SUFFIXES = (".py", ".pyc", ".so", ".pyd")
_ALLOWED_CHECKOUT_ROOT_PACKAGES = frozenset(
    {"api", "stochastic_warfare", "tests"},
)
_ALLOWED_CHECKOUT_ROOT_MODULES = frozenset(
    {"build_hooks.py"},
)
_ROOT_IMPORT_MODULE_PATHSPECS = (
    ":(top,glob)*.py",
    ":(top,glob)*.pyc",
    ":(top,glob)*.so",
    ":(top,glob)*.pyd",
)
_ROOT_IMPORT_PACKAGE_PATHSPECS = (
    ":(top,glob)*/__init__.py",
    ":(top,glob)*/__init__.pyc",
    ":(top,glob)*/__init__*.so",
    ":(top,glob)*/__init__*.pyd",
)
_RUNTIME_STARTUP_PATHSPECS = tuple(
    f":(top,glob)**/{module_name}{suffix_pattern}"
    for module_name in _RUNTIME_STARTUP_MODULE_NAMES
    for suffix_pattern in (".py", ".pyc", "*.so", "*.pyd")
)
_RUNTIME_STARTUP_PACKAGE_PATHSPECS = tuple(
    f":(top,glob)**/{module_name}/__init__{suffix_pattern}"
    for module_name in _RUNTIME_STARTUP_MODULE_NAMES
    for suffix_pattern in (".py", ".pyc", "*.so", "*.pyd")
)
_RUNTIME_SCRIPT_PATHSPECS = tuple(
    f":(top,glob)scripts/**/*{suffix}"
    for suffix in _ROOT_RUNTIME_MODULE_SUFFIXES
)
_RUNTIME_TRACKED_PATHSPECS = (
    *_RUNTIME_SOURCE_ROOTS,
    *_ROOT_IMPORT_MODULE_PATHSPECS,
    *_RUNTIME_STARTUP_PATHSPECS,
    *_RUNTIME_STARTUP_PACKAGE_PATHSPECS,
    *_RUNTIME_SCRIPT_PATHSPECS,
)
_RUNTIME_IGNORED_PATHSPECS = (
    *_RUNTIME_TRACKED_PATHSPECS,
    *_ROOT_IMPORT_PACKAGE_PATHSPECS,
)
_CHECKOUT_IMPORT_POLICY_PATHSPECS = (
    *_ROOT_IMPORT_MODULE_PATHSPECS,
    *_ROOT_IMPORT_PACKAGE_PATHSPECS,
)
_REGULAR_GIT_MODES = frozenset({"100644", "100755"})


def _decode_git_relative_path(payload: bytes) -> str:
    """Decode one safe repository-relative path emitted by Git."""
    relative = payload.decode("utf-8")
    path = PurePosixPath(relative)
    if (
        not relative
        or "\\" in relative
        or "\n" in relative
        or "\r" in relative
        or path.is_absolute()
        or path.as_posix() != relative
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise RuntimeError(
            f"worktree provenance received an unsupported Git path: {relative!r}",
        )
    return relative


def _is_runtime_path(relative: str) -> bool:
    parts = PurePosixPath(relative).parts
    return (
        _is_runtime_startup_path(relative)
        or _is_runtime_script_path(relative)
        or (
            len(parts) == 1
            and relative.endswith(_ROOT_RUNTIME_MODULE_SUFFIXES)
        )
        or (
            len(parts) > 1 and parts[0] in _RUNTIME_SOURCE_ROOTS
        )
    )


def _is_runtime_script_path(relative: str) -> bool:
    """Return whether direct script launch can execute or import this path."""
    parts = PurePosixPath(relative).parts
    return (
        len(parts) > 1
        and parts[0] == "scripts"
        and "__pycache__" not in parts
        and relative.endswith(_ROOT_RUNTIME_MODULE_SUFFIXES)
    )


def _is_import_package_initializer(filename: str) -> bool:
    """Return whether one filename can initialize a regular Python package."""
    return (
        filename in {"__init__.py", "__init__.pyc"}
        or (
            filename.startswith("__init__.")
            and filename.endswith((".so", ".pyd"))
        )
    )


def _is_root_import_package(relative: str) -> bool:
    parts = PurePosixPath(relative).parts
    return (
        len(parts) == 2
        and parts[0].isidentifier()
        and _is_import_package_initializer(parts[1])
    )


def _import_module_name(filename: str) -> str | None:
    """Return the Python import name represented by one module filename."""
    for suffix in _ROOT_RUNTIME_MODULE_SUFFIXES:
        if not filename.endswith(suffix):
            continue
        stem = filename[: -len(suffix)]
        if suffix in {".so", ".pyd"}:
            stem = stem.split(".", 1)[0]
        return stem if stem.isidentifier() else None
    return None


def _is_runtime_startup_path(relative: str) -> bool:
    """Return whether one path can provide Python's startup customization."""
    parts = PurePosixPath(relative).parts
    module_name = _import_module_name(parts[-1]) if parts else None
    return module_name in _RUNTIME_STARTUP_MODULE_NAMES or (
        len(parts) > 1
        and parts[-2] in _RUNTIME_STARTUP_MODULE_NAMES
        and _is_import_package_initializer(parts[-1])
    )


def _root_import_module_name(relative: str) -> str | None:
    """Return the import name for one direct checkout-root module candidate."""
    parts = PurePosixPath(relative).parts
    return _import_module_name(relative) if len(parts) == 1 else None


def _is_unknown_checkout_import_candidate(relative: str) -> bool:
    """Return whether ``relative`` introduces an unowned root import name."""
    module_name = _root_import_module_name(relative)
    if module_name is not None:
        return (
            relative not in _ALLOWED_CHECKOUT_ROOT_MODULES
            and module_name not in _RUNTIME_STARTUP_MODULE_NAMES
        )
    if not _is_root_import_package(relative):
        return False
    package_name = PurePosixPath(relative).parts[0]
    return package_name not in _ALLOWED_CHECKOUT_ROOT_PACKAGES


def _is_allowed_ignored_runtime_output(relative: str) -> bool:
    parts = PurePosixPath(relative).parts
    if "__pycache__" in parts:
        return True
    if parts and parts[0] in {".venv", "artifacts", "build"}:
        return True
    return len(parts) > 1 and parts[:2] == ("data", "terrain_cache")


def _is_ignored_runtime_source(relative: str) -> bool:
    if _is_allowed_ignored_runtime_output(relative):
        return False
    return _is_runtime_path(relative) or _is_root_import_package(relative)


def _head_tree_entries(
    repo: Path,
    commit: str,
) -> dict[str, tuple[str, str, str]]:
    """Return mode, object type, and ID for every path at ``commit``."""
    output = _run_git(repo, "ls-tree", "-r", "-z", commit, "--")
    entries: dict[str, tuple[str, str, str]] = {}
    for record in output.split(b"\0"):
        if not record:
            continue
        try:
            metadata, raw_path = record.split(b"\t", 1)
            mode, object_type, object_id = metadata.decode("ascii").split()
        except (UnicodeDecodeError, ValueError) as exc:
            raise RuntimeError(
                "worktree provenance received a malformed Git tree entry",
            ) from exc
        relative = _decode_git_relative_path(raw_path)
        if relative in entries:
            raise RuntimeError(
                f"worktree provenance received duplicate Git path {relative!r}",
            )
        entries[relative] = (mode, object_type, object_id)
    return entries


def _runtime_head_entries(
    head_tree: Mapping[str, tuple[str, str, str]],
) -> dict[str, tuple[str, str]]:
    """Return every runtime blob path, executable mode, and ID at ``commit``."""
    entries: dict[str, tuple[str, str]] = {}
    for relative, (mode, object_type, object_id) in head_tree.items():
        if not _is_runtime_path(relative):
            continue
        if mode not in _REGULAR_GIT_MODES or object_type != "blob":
            raise RuntimeError(
                "worktree provenance requires regular tracked blobs: "
                f"{relative!r}",
            )
        entries[relative] = (mode, object_id)
    if not entries:
        raise RuntimeError("worktree provenance received an empty Git tree")
    return entries


def _tracked_index_entries(
    repo: Path,
    *pathspecs: str,
) -> dict[str, tuple[str, str, str]]:
    """Return Git index flag, mode, and blob ID for every stage-zero path."""
    arguments = ["ls-files", "--stage", "-v", "-z"]
    if pathspecs:
        arguments.extend(("--", *pathspecs))
    output = _run_git(repo, *arguments)
    entries: dict[str, tuple[str, str, str]] = {}
    for record in output.split(b"\0"):
        if not record:
            continue
        try:
            flag_payload, remainder = record.split(b" ", 1)
            metadata, raw_path = remainder.split(b"\t", 1)
            mode, object_id, stage = metadata.decode("ascii").split()
        except (UnicodeDecodeError, ValueError) as exc:
            raise RuntimeError(
                "worktree provenance received a malformed Git index entry",
            ) from exc
        if len(flag_payload) != 1 or stage != "0":
            raise RuntimeError(
                "worktree provenance requires a stage-zero Git index",
            )
        relative = _decode_git_relative_path(raw_path)
        if relative in entries:
            raise RuntimeError(
                f"worktree provenance received duplicate Git path {relative!r}",
            )
        entries[relative] = (
            flag_payload.decode("ascii"),
            mode,
            object_id,
        )
    return entries


def _reject_unknown_checkout_import_candidates(
    repo: Path,
    head_tree: Mapping[str, tuple[str, str, str]],
) -> None:
    """Reject root import names outside the explicit checkout ownership set."""
    observed: dict[str, set[str]] = {}
    for relative, (mode, object_type, _object_id) in head_tree.items():
        if (
            mode in _REGULAR_GIT_MODES
            and object_type == "blob"
            and _is_unknown_checkout_import_candidate(relative)
        ):
            observed.setdefault(relative, set()).add("HEAD")

    for relative, (_flag, mode, _object_id) in _tracked_index_entries(
        repo,
        *_CHECKOUT_IMPORT_POLICY_PATHSPECS,
    ).items():
        if (
            mode in _REGULAR_GIT_MODES
            and _is_unknown_checkout_import_candidate(relative)
        ):
            observed.setdefault(relative, set()).add("index")

    output = _run_git(
        repo,
        "ls-files",
        "--others",
        "--exclude-standard",
        "-z",
        "--",
        *_CHECKOUT_IMPORT_POLICY_PATHSPECS,
    )
    for raw_relative in (item for item in output.split(b"\0") if item):
        relative = _decode_git_relative_path(raw_relative)
        if _is_unknown_checkout_import_candidate(relative):
            observed.setdefault(relative, set()).add("untracked")

    if observed:
        unsupported = [
            (relative, tuple(sorted(sources)))
            for relative, sources in sorted(observed.items())
        ]
        raise RuntimeError(
            "checkout contains unsupported root import candidates: "
            f"{unsupported[:5]!r}",
        )


def _reject_unsupported_runtime_index_flags(repo: Path) -> None:
    """Reject flags that can hide changes to importable runtime paths."""
    entries = _tracked_index_entries(
        repo,
        *_RUNTIME_TRACKED_PATHSPECS,
    )
    unsupported = sorted(
        (flag, relative)
        for relative, (flag, _mode, _object_id) in entries.items()
        if _is_runtime_path(relative) and flag != "H"
    )
    if unsupported:
        raise RuntimeError(
            "runtime code paths use unsupported Git index flags: "
            f"{unsupported[:5]!r}",
        )


def _reject_ignored_runtime_sources(repo: Path) -> None:
    """Reject ignored package inputs and root modules before attribution."""
    output = _run_git(
        repo,
        "ls-files",
        "--others",
        "--ignored",
        "--exclude-standard",
        "-z",
        "--",
        *_RUNTIME_IGNORED_PATHSPECS,
    )
    for raw_relative in sorted(item for item in output.split(b"\0") if item):
        relative = _decode_git_relative_path(raw_relative)
        if not _is_ignored_runtime_source(relative):
            continue
        path = repo.joinpath(*PurePosixPath(relative).parts)
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError(
                f"worktree provenance does not permit symlinks: {relative!r}",
            )
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(
                f"worktree provenance entry must be a regular file: {relative!r}",
            )
        raise RuntimeError(
            "worktree provenance does not permit ignored runtime source: "
            f"{relative!r}",
        )


def _verify_clean_git_attribution(
    repo: Path,
    commit: str,
    head_tree: Mapping[str, tuple[str, str, str]],
) -> None:
    """Bind a nominally clean worktree's exact paths, bytes, and modes to HEAD."""
    head_entries = _runtime_head_entries(head_tree)
    index_entries = _tracked_index_entries(
        repo,
        *_RUNTIME_TRACKED_PATHSPECS,
    )
    if set(index_entries) != set(head_entries):
        missing = sorted(set(head_entries) - set(index_entries))
        added = sorted(set(index_entries) - set(head_entries))
        raise RuntimeError(
            "clean Git index paths differ from Git HEAD: "
            f"missing={missing[:5]!r}, added={added[:5]!r}",
        )

    unsupported_flags = sorted(
        (flag, relative)
        for relative, (flag, _mode, _object_id) in index_entries.items()
        if flag != "H"
    )
    if unsupported_flags:
        raise RuntimeError(
            "clean Git index uses unsupported Git index flags: "
            f"{unsupported_flags[:5]!r}",
        )

    mismatched_index = sorted(
        relative
        for relative, (_flag, mode, object_id) in index_entries.items()
        if (mode, object_id) != head_entries[relative]
    )
    if mismatched_index:
        raise RuntimeError(
            "clean Git index differs from Git HEAD: "
            f"{mismatched_index[:5]!r}",
        )

    mismatched_modes: list[str] = []
    ordered_paths = tuple(sorted(head_entries))
    for relative in ordered_paths:
        path = repo.joinpath(*PurePosixPath(relative).parts)
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError(
                "clean tracked worktree entry is not a regular file: "
                f"{relative!r}",
            )
        current_mode = "100755" if metadata.st_mode & 0o111 else "100644"
        if current_mode != head_entries[relative][0]:
            mismatched_modes.append(relative)
    if mismatched_modes:
        raise RuntimeError(
            "clean tracked worktree modes differ from Git HEAD: "
            f"{mismatched_modes[:5]!r}",
        )

    hash_input = ("\n".join(ordered_paths) + "\n").encode("utf-8")
    hash_output = _run_git(
        repo,
        "hash-object",
        "--no-filters",
        "--stdin-paths",
        input_payload=hash_input,
    )
    current_hashes = hash_output.decode("ascii").splitlines()
    if len(current_hashes) != len(ordered_paths):
        raise RuntimeError(
            "Git did not hash every clean tracked worktree entry",
        )
    mismatched_bytes = [
        relative
        for relative, object_id in zip(
            ordered_paths,
            current_hashes,
            strict=True,
        )
        if object_id != head_entries[relative][1]
    ]
    if mismatched_bytes:
        raise RuntimeError(
            "clean tracked worktree bytes differ from Git HEAD: "
            f"{mismatched_bytes[:5]!r}",
        )

    final_status = _run_git(
        repo,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    )
    if final_status:
        raise RuntimeError(
            "Git worktree changed during clean provenance attribution",
        )
    _reject_special_worktree_entries(repo)
    _reject_unknown_checkout_import_candidates(repo, head_tree)
    _reject_ignored_runtime_sources(repo)
    if (
        _tracked_index_entries(repo, *_RUNTIME_TRACKED_PATHSPECS)
        != index_entries
    ):
        raise RuntimeError(
            "Git index changed during clean provenance attribution",
        )
    final_commit = _run_git(repo, "rev-parse", "HEAD").decode("ascii").strip()
    if final_commit != commit:
        raise RuntimeError(
            "Git HEAD changed during clean provenance attribution",
        )


def _worktree_entry_identity(
    repo: Path,
    relative: str,
) -> dict[str, Any]:
    """Identify one regular worktree file without following indirection."""
    path = repo / relative
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode):
        raise ValueError(
            f"worktree provenance does not permit symlinks: {relative!r}",
        )
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(
            f"worktree provenance entry must be a regular file: {relative!r}",
        )

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    digest = hashlib.sha256()
    size = 0
    try:
        opened_metadata = os.fstat(descriptor)
        stable_fields = (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        if not stat.S_ISREG(opened_metadata.st_mode) or any(
            getattr(opened_metadata, field) != getattr(metadata, field)
            for field in stable_fields
        ):
            raise ValueError(
                "worktree provenance entry changed during capture: "
                f"{relative!r}",
            )
        while payload := os.read(descriptor, 1024 * 1024):
            digest.update(payload)
            size += len(payload)
        final_opened_metadata = os.fstat(descriptor)
        final_path_metadata = path.lstat()
    finally:
        os.close(descriptor)
    if any(
        getattr(candidate, field) != getattr(opened_metadata, field)
        for candidate in (final_opened_metadata, final_path_metadata)
        for field in stable_fields
    ) or size != final_opened_metadata.st_size:
        raise ValueError(
            f"worktree provenance entry changed during capture: {relative!r}",
        )
    executable_bits = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    mode = "100755" if opened_metadata.st_mode & executable_bits else "100644"
    return {
        "path": relative,
        "kind": "regular",
        "mode": mode,
        "size": size,
        "sha256": digest.hexdigest(),
    }


def _runtime_worktree_manifest_sha256(
    repo: Path,
    head_tree: Mapping[str, tuple[str, str, str]],
    untracked_paths: Sequence[str],
) -> str:
    """Fingerprint raw executable inputs even when Git filters hide changes."""
    head_paths = set(_runtime_head_entries(head_tree))
    index_paths = set(
        _tracked_index_entries(repo, *_RUNTIME_TRACKED_PATHSPECS),
    )
    runtime_untracked = {
        relative
        for relative in untracked_paths
        if _is_runtime_path(relative) or _is_root_import_package(relative)
    }
    manifest: list[dict[str, Any]] = []
    for relative in sorted(head_paths | index_paths | runtime_untracked):
        path = repo.joinpath(*PurePosixPath(relative).parts)
        try:
            path.lstat()
        except FileNotFoundError:
            manifest.append(
                {
                    "path": relative,
                    "kind": "missing",
                },
            )
            continue
        manifest.append(_worktree_entry_identity(repo, relative))
    if not manifest:
        raise RuntimeError(
            "worktree provenance received an empty runtime source manifest",
        )
    return _canonical_digest(manifest)


def _capture_dirty_git_attribution(
    repo: Path,
    head_tree: Mapping[str, tuple[str, str, str]],
) -> dict[str, Any]:
    """Capture one complete, equality-comparable dirty Git attribution."""
    commit = _run_git(repo, "rev-parse", "HEAD").decode("ascii").strip()
    _reject_special_worktree_entries(repo)
    _reject_unknown_checkout_import_candidates(repo, head_tree)
    _reject_unsupported_runtime_index_flags(repo)
    _reject_ignored_runtime_sources(repo)

    status = _run_git(
        repo,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    )
    if not status:
        raise RuntimeError(
            "Git worktree changed during dirty provenance attribution",
        )
    index_manifest = [
        {
            "path": relative,
            "flag": flag,
            "mode": mode,
            "object_id": object_id,
        }
        for relative, (flag, mode, object_id) in sorted(
            _tracked_index_entries(repo).items(),
        )
    ]
    tracked_diff = _run_git(
        repo,
        "diff",
        "--binary",
        "--full-index",
        "HEAD",
        "--",
    )
    untracked_raw = _run_git(
        repo,
        "ls-files",
        "--others",
        "--exclude-standard",
        "-z",
    )
    untracked_paths = [
        _decode_git_relative_path(raw_relative)
        for raw_relative in sorted(
            item for item in untracked_raw.split(b"\0") if item
        )
    ]
    if len(untracked_paths) != len(set(untracked_paths)):
        raise RuntimeError(
            "worktree provenance received duplicate untracked paths",
        )
    untracked_manifest = [
        _worktree_entry_identity(repo, relative)
        for relative in untracked_paths
    ]
    return {
        "commit": commit,
        "index_sha256": _canonical_digest(index_manifest),
        "runtime_source_sha256": _runtime_worktree_manifest_sha256(
            repo,
            head_tree,
            untracked_paths,
        ),
        "status_sha256": hashlib.sha256(status).hexdigest(),
        "tracked_diff_sha256": hashlib.sha256(tracked_diff).hexdigest(),
        "untracked": untracked_manifest,
    }


def _reject_special_worktree_entries(repo: Path) -> None:
    """Reject filesystem entries Git cannot safely include in status output."""
    ignored_directories = {
        item.decode("utf-8").rstrip("/")
        for item in _run_git(
            repo,
            "ls-files",
            "--others",
            "--ignored",
            "--exclude-standard",
            "--directory",
            "-z",
        ).split(b"\0")
        if item
    }
    for directory, child_directories, filenames in os.walk(
        repo,
        followlinks=False,
    ):
        directory_path = Path(directory)
        relative_directory = directory_path.relative_to(repo)
        retained_directories: list[str] = []
        for child_name in child_directories:
            child_path = directory_path / child_name
            relative = (relative_directory / child_name).as_posix()
            if relative == ".git":
                continue
            metadata = child_path.lstat()
            if stat.S_ISDIR(metadata.st_mode):
                if relative not in ignored_directories:
                    retained_directories.append(child_name)
            elif stat.S_ISLNK(metadata.st_mode):
                raise ValueError(
                    f"worktree provenance does not permit symlinks: {relative!r}",
                )
            else:
                raise ValueError(
                    f"worktree provenance entry must be a directory: {relative!r}",
                )
        child_directories[:] = retained_directories

        for filename in filenames:
            path = directory_path / filename
            relative = (relative_directory / filename).as_posix()
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                raise ValueError(
                    f"worktree provenance does not permit symlinks: {relative!r}",
                )
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError(
                    f"worktree provenance entry must be a regular file: {relative!r}",
                )


def _has_git_control_marker(start: Path) -> bool:
    """Report whether ``start`` is below an explicit Git worktree marker."""
    candidate = start.absolute()
    if candidate.is_file():
        candidate = candidate.parent
    identity_root = _nearest_build_identity_root(candidate)
    try:
        start_device = candidate.stat().st_dev
    except OSError as exc:
        raise RuntimeError(
            "Authoritative analysis cannot inspect its source location",
        ) from exc
    cross_filesystems = os.environ.get(
        "GIT_DISCOVERY_ACROSS_FILESYSTEM",
        "",
    ).lower() not in {"", "0", "false", "no"}
    for directory in (candidate, *candidate.parents):
        try:
            directory_device = directory.stat().st_dev
        except OSError as exc:
            raise RuntimeError(
                "Authoritative analysis cannot inspect Git worktree ancestry",
            ) from exc
        if not cross_filesystems and directory_device != start_device:
            break
        marker = directory / ".git"
        try:
            marker.lstat()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise RuntimeError(
                "Authoritative analysis cannot inspect Git worktree metadata",
            ) from exc
        else:
            return True

        # A packaged identity defines the application-root ceiling for Git
        # marker discovery. Git wins only at that exact root, while an
        # unrelated corrupt marker in a parent deployment directory cannot
        # reclassify the verified nested package as its worktree.
        if identity_root is not None and directory.resolve() == identity_root:
            return False
    return False


def _nearest_build_identity_root(start: Path) -> Path | None:
    """Return the nearest application root containing a build identity marker."""
    candidate = start.absolute()
    if candidate.is_file():
        candidate = candidate.parent
    for directory in (candidate, *candidate.parents):
        identity_marker = directory / BUILD_IDENTITY_RELATIVE_PATH
        try:
            identity_marker.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise RuntimeError(
                "Authoritative analysis cannot inspect build identity metadata",
            ) from exc
        return directory.resolve()
    return None


def _discover_git_worktree(start: Path) -> Path | None:
    """Return the exact owning Git root or defer to packaged identity."""
    location = start.resolve()
    if location.is_file():
        location = location.parent
    identity_root = _nearest_build_identity_root(location)
    try:
        root_payload = _run_git(location, "rev-parse", "--show-toplevel")
    except FileNotFoundError as exc:
        if _has_git_control_marker(location):
            raise RuntimeError(
                "Authoritative analysis requires Git to verify this worktree",
            ) from exc
        return None
    except subprocess.CalledProcessError as exc:
        if _has_git_control_marker(location):
            raise RuntimeError(
                "Authoritative analysis cannot verify this Git worktree",
            ) from exc
        return None
    except OSError as exc:
        raise RuntimeError(
            "Authoritative analysis cannot execute Git provenance capture",
        ) from exc
    try:
        decoded_root = root_payload.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise RuntimeError(
            "Authoritative analysis received invalid Git worktree metadata",
        ) from exc
    if not decoded_root:
        raise RuntimeError(
            "Authoritative analysis received an empty Git worktree root",
        )
    root = Path(decoded_root).resolve()
    if not location.is_relative_to(root):
        raise RuntimeError(
            "Authoritative analysis received an unrelated Git worktree root",
        )
    if identity_root is None:
        return root
    if root == identity_root:
        return root
    if (
        root.is_relative_to(identity_root)
        or identity_root.is_relative_to(root)
    ):
        return None
    raise RuntimeError(
        "Authoritative analysis found inconsistent Git and build identity roots",
    )


def _resolve_git_code_revision(repo: Path) -> CodeRevision:
    """Resolve the existing content-sensitive Git worktree identity."""
    try:
        commit = _run_git(repo, "rev-parse", "HEAD").decode("ascii").strip()
        head_tree = _head_tree_entries(repo, commit)
        _reject_special_worktree_entries(repo)
        _reject_unknown_checkout_import_candidates(repo, head_tree)
        _reject_unsupported_runtime_index_flags(repo)
        _reject_ignored_runtime_sources(repo)
        status = _run_git(
            repo,
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
        )
        dirty = bool(status)
        if not dirty:
            _verify_clean_git_attribution(repo, commit, head_tree)
            worktree_fingerprint = _canonical_digest(
                {"commit": commit, "dirty": False},
            )
        else:
            initial_attribution = _capture_dirty_git_attribution(
                repo,
                head_tree,
            )
            final_attribution = _capture_dirty_git_attribution(
                repo,
                head_tree,
            )
            if (
                initial_attribution != final_attribution
                or initial_attribution["commit"] != commit
            ):
                raise RuntimeError(
                    "Git worktree changed during dirty provenance attribution",
                )
            worktree_fingerprint = _canonical_digest(
                {
                    "dirty": True,
                    **initial_attribution,
                },
            )
        return CodeRevision(
            commit=commit,
            dirty=dirty,
            worktree_fingerprint=worktree_fingerprint,
        )
    except (
        OSError,
        subprocess.CalledProcessError,
        UnicodeDecodeError,
    ) as exc:
        raise RuntimeError(
            "Authoritative analysis requires a verifiable Git code revision",
        ) from exc


def _resolve_code_revision(start: Path) -> CodeRevision:
    """Resolve strict Git provenance or a verified immutable-build identity."""
    repo = _discover_git_worktree(start)
    if repo is not None:
        return _resolve_git_code_revision(repo)

    try:
        identity = load_verified_build_identity(start)
    except (BuildIdentityError, OSError) as exc:
        raise RuntimeError(
            "Authoritative analysis requires a verifiable Git code revision "
            "or verified immutable build identity",
        ) from exc
    return CodeRevision(
        commit=identity.commit,
        dirty=False,
        worktree_fingerprint=_canonical_digest(
            {
                "kind": "immutable-build",
                "commit": identity.commit,
                "source_manifest_sha256": (
                    identity.source_manifest_sha256
                ),
            },
        ),
    )


def _runtime_code_revision() -> CodeRevision:
    """Resolve code provenance from the imported runtime, never the catalog."""
    runtime_source = Path(__file__).resolve()
    identity_root = _nearest_build_identity_root(runtime_source)
    if identity_root is not None:
        package_root = (identity_root / "stochastic_warfare").resolve()
        if not runtime_source.is_relative_to(package_root):
            raise RuntimeError(
                "Authoritative analysis imported runtime code outside the "
                "build identity package tree",
            )
    return _resolve_code_revision(runtime_source)


def _data_tree_revision(
    data_root: Path,
    *,
    excluded_relative_paths: tuple[str, ...] = (),
) -> tuple[str, int]:
    """Fingerprint authored inputs while excluding known derived runtime state."""
    runtime_outputs = {
        "api_runs.db",
        "api_runs.db-journal",
        "api_runs.db-shm",
        "api_runs.db-wal",
    }
    runtime_output_directories = {
        "terrain_cache",
        # Validation plans and claim/artifact ledgers audit production inputs;
        # they are not simulation configuration and are fingerprinted by their
        # own strict contracts.
        "validation",
    }
    excluded = runtime_outputs | set(excluded_relative_paths)
    manifest: list[dict[str, Any]] = []
    for path in sorted(
        candidate
        for candidate in data_root.rglob("*")
        if candidate.is_file()
    ):
        relative = path.relative_to(data_root).as_posix()
        if relative in excluded or any(
            relative.startswith(f"{directory}/")
            for directory in runtime_output_directories
        ):
            continue
        payload = path.read_bytes()
        manifest.append(
            {
                "path": relative,
                "size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            },
        )
    if not manifest:
        raise ValueError(f"data_root contains no files: {data_root}")
    return _canonical_digest(manifest), len(manifest)


def _definition_map(loader: Any) -> dict[str, Any]:
    definitions = loader.definitions()
    return {key: _json_value(definition) for key, definition in sorted(definitions.items())}


def _resolved_catalog_revision(context: SimulationContext) -> str:
    """Fingerprint the actual effective catalogs published by the loader."""
    signature_profiles = {
        profile_id: _json_value(context.sig_loader.get_profile(profile_id))
        for profile_id in context.sig_loader.available_profiles()
    }
    supply_items = {
        item_id: _json_value(
            context.supply_item_loader.get_definition(item_id),
        )
        for item_id in context.supply_item_loader.available_items()
    }
    school_catalog = context.school_registry.get_state()["schools"] if context.school_registry is not None else {}
    return _canonical_digest(
        {
            "units": _definition_map(context.unit_loader),
            "weapons": _definition_map(context.weapon_loader),
            "ammunition": _definition_map(context.ammo_loader),
            "sensors": _definition_map(context.sensor_loader),
            "signatures": signature_profiles,
            "supply_items": supply_items,
            "commander_profiles": _definition_map(
                context.commander_profile_loader,
            ),
            "doctrine_schools": school_catalog,
            "era": _json_value(context.era_config),
            "loadout_builder": (context.loadout_builder.fingerprint() if context.loadout_builder is not None else None),
        },
    )


def _runtime_unit_assignments(
    context: SimulationContext,
) -> tuple[UnitCommandAssignment, ...]:
    units = {
        unit.entity_id: (
            side,
            unit,
        )
        for side in sorted(context.units_by_side)
        for unit in context.units_by_side[side]
    }
    profile_assignments = dict(context.commander_engine.assignments()) if context.commander_engine is not None else {}
    if context.commander_engine is not None and (set(profile_assignments) != set(units)):
        raise RuntimeError(
            "Commander assignment topology does not match the runtime roster",
        )
    school_assignments = (
        context.school_registry.get_state()["unit_assignments"] if context.school_registry is not None else {}
    )
    unknown_school_units = set(school_assignments) - set(units)
    if unknown_school_units:
        raise RuntimeError(
            f"Doctrine assignment topology contains unknown runtime units: {sorted(unknown_school_units)!r}",
        )
    return tuple(
        UnitCommandAssignment(
            unit_id=unit_id,
            side=units[unit_id][0],
            commander_profile_id=profile_assignments.get(unit_id),
            doctrine_school_id=school_assignments.get(unit_id),
        )
        for unit_id in sorted(units)
    )


def _roster_loadout_fingerprint(context: SimulationContext) -> str:
    topology_keys = set(context.equipment_resolutions)
    unit_ids = {unit.entity_id for units in context.units_by_side.values() for unit in units}
    if topology_keys != unit_ids:
        raise RuntimeError(
            "Loadout topology does not match the exact runtime roster",
        )
    roster_loadout = [
        {
            "side": side,
            "unit_id": unit.entity_id,
            "definition_id": unit.unit_type,
            "position": list(unit.position),
            "loadout": [resolution.topology() for resolution in context.equipment_resolutions[unit.entity_id]],
        }
        for side in sorted(context.units_by_side)
        for unit in sorted(
            context.units_by_side[side],
            key=lambda candidate: candidate.entity_id,
        )
    ]
    return _canonical_digest(roster_loadout)


def _assert_finite(value: Any, *, path: str) -> None:
    """Reject non-finite numbers anywhere in an analysis-owned payload."""
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} must contain only finite numbers")
        return
    if isinstance(value, Mapping):
        for key, nested in value.items():
            _assert_finite(nested, path=f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _assert_finite(nested, path=f"{path}[{index}]")


def _strict_calibration_patch(value: Any) -> CalibrationSchema:
    """Validate a sparse calibration patch without inventing defaults."""
    if isinstance(value, CalibrationSchema):
        raw = value.to_sparse_patch(mode="python")
    elif isinstance(value, Mapping):
        raw = dict(value)
    else:
        raise ValueError("calibration_patch must be a mapping")
    _assert_finite(raw, path="calibration_patch")
    return CalibrationSchema.model_validate(raw, strict=True)


class DoctrineAnalysisVariant(BaseModel):
    """Ordered, duplicate-safe per-side school policy for one variant."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    assignments: tuple[DoctrineSideAssignment, ...] = Field(min_length=1)

    @field_validator("assignments", mode="before")
    @classmethod
    def _ordered_assignments(cls, value: Any) -> Any:
        if not isinstance(value, (list, tuple)):
            raise ValueError(
                "doctrine assignments must be an ordered list or tuple",
            )
        return value

    @model_validator(mode="after")
    def _unique_sides(self) -> DoctrineAnalysisVariant:
        sides = [assignment.side for assignment in self.assignments]
        if len(sides) != len(set(sides)):
            raise ValueError(
                f"doctrine assignment sides must be unique: {sides!r}",
            )
        return self


class AnalysisVariant(BaseModel):
    """One independently applied sparse calibration variant."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    variant_id: str
    calibration_patch: CalibrationSchema = Field(
        default_factory=CalibrationSchema,
    )
    doctrine_variant: DoctrineAnalysisVariant | None = None

    @field_validator("variant_id", mode="before")
    @classmethod
    def _valid_variant_id(cls, value: Any) -> str:
        if not isinstance(value, str) or not value or value != value.strip():
            raise ValueError("variant_id must be a non-empty trimmed string")
        return value

    @field_validator("calibration_patch", mode="before")
    @classmethod
    def _valid_patch(cls, value: Any) -> CalibrationSchema:
        return _strict_calibration_patch(value)


@dataclass(frozen=True)
class PreparedVariant:
    """One immutable effective configuration prepared from the same source."""

    variant_id: str
    config_json: str
    config_fingerprint: str
    doctrine_side_assignments: tuple[DoctrineSideAssignment, ...]
    era_config_json: str
    era_runtime_contract_json: str

    @property
    def config(self) -> CampaignScenarioConfig:
        """Return a fresh typed copy of the effective configuration."""
        return CampaignScenarioConfig.model_validate_json(self.config_json)

    @property
    def era_config(self) -> EraConfig:
        """Return the isolated era configuration frozen at preparation."""
        return EraConfig.model_validate_json(self.era_config_json)

    @property
    def era_runtime_contract(self) -> EraRuntimeContract:
        """Return the effective era behavior frozen at preparation."""
        return EraRuntimeContract.model_validate_json(
            self.era_runtime_contract_json,
        )


@dataclass(frozen=True)
class RuntimeSession:
    """Fresh production runtime for one variant/seed pair."""

    variant_id: str
    seed: int
    max_ticks: int
    context: SimulationContext
    victory_evaluator: VictoryEvaluator
    engine: SimulationEngine
    recorder: SimulationRecorder | None
    source_fingerprint: str
    config_fingerprint: str
    authored_roster: tuple[tuple[str, int], ...]
    loaded_roster: tuple[tuple[str, int], ...]
    code_revision: CodeRevision
    data_revision: str
    data_file_count: int
    catalog_revision: str
    doctrine_catalog_fingerprint: str
    loaded_roster_loadout_fingerprint: str
    initial_unit_assignments: tuple[UnitCommandAssignment, ...]

    def run_to_completion(self) -> SimulationRunResult:
        """Run the production engine and return its public terminal result."""
        result = self.engine.run()
        if not result.victory_result.game_over:
            raise RuntimeError(
                "Simulation ended without a public terminal victory result",
            )
        return result

    def step(self) -> bool:
        """Advance one production tick and report public terminal state."""
        return self.engine.step()

    def finalize(self) -> SimulationRunResult:
        """Return a result only after :meth:`step` reports termination."""
        return self.engine.finalize()

    def performance_execution_receipt(self) -> PerformanceExecutionReceipt:
        """Return committed production performance-flag execution evidence."""
        return self.engine.performance_execution_receipt()

    def fow_indexed_interval_record(
        self,
    ) -> FOWIndexedIntervalRecord | None:
        """Return the latest committed raw FOW indexed-decision record."""
        return self.context.rng_manager.latest_fow_detection_interval_record

    def provenance(self) -> RuntimeProvenance:
        """Capture exact production assignments, including arrivals so far."""
        self.engine.assert_evidence_healthy()
        current_assignments = _runtime_unit_assignments(self.context)
        current_by_id = {assignment.unit_id: assignment for assignment in current_assignments}
        initial_ids = {assignment.unit_id for assignment in self.initial_unit_assignments}
        current_initial = tuple(
            current_by_id[assignment.unit_id]
            for assignment in self.initial_unit_assignments
            if assignment.unit_id in current_by_id
        )
        if current_initial != self.initial_unit_assignments:
            raise RuntimeError(
                "Initial profile or doctrine assignments changed during runtime execution",
            )
        arriving_assignments = tuple(
            assignment for assignment in current_assignments if assignment.unit_id not in initial_ids
        )
        return RuntimeProvenance(
            code_revision=self.code_revision,
            data_revision=self.data_revision,
            data_file_count=self.data_file_count,
            catalog_revision=self.catalog_revision,
            doctrine_catalog_fingerprint=(self.doctrine_catalog_fingerprint),
            doctrine_assignment_fingerprint=_canonical_digest(
                current_assignments,
            ),
            loaded_roster_loadout_fingerprint=(self.loaded_roster_loadout_fingerprint),
            final_roster_loadout_fingerprint=(_roster_loadout_fingerprint(self.context)),
            initial_unit_assignments=self.initial_unit_assignments,
            arriving_unit_assignments=arriving_assignments,
            execution_mode=self.engine.execution_mode,
            suppressed_failures=self.engine.suppressed_failures,
        )


@dataclass(frozen=True)
class PreparedScenario:
    """Source-once scenario preparation and its independent variants."""

    scenario_path: Path
    data_root: Path
    source_config_json: str
    source_fingerprint: str
    variants: tuple[PreparedVariant, ...]
    authored_roster: tuple[tuple[str, int], ...]
    code_revision: CodeRevision
    data_revision: str
    data_file_count: int
    data_revision_exclusions: tuple[str, ...]

    @property
    def source_config(self) -> CampaignScenarioConfig:
        """Return a fresh typed copy of the validated source configuration."""
        return CampaignScenarioConfig.model_validate_json(
            self.source_config_json,
        )

    @property
    def side_ids(self) -> tuple[str, ...]:
        """Return exact authored side IDs in source order."""
        return tuple(side for side, _ in self.authored_roster)

    def variant(self, variant_id: str) -> PreparedVariant:
        """Resolve a variant by exact ID."""
        for variant in self.variants:
            if variant.variant_id == variant_id:
                return variant
        raise ValueError(f"Unknown analysis variant {variant_id!r}")

    def assert_source_identity(self, *, stage: str) -> None:
        """Reject evidence produced from sources unlike this preparation."""
        if not isinstance(stage, str) or not stage or stage != stage.strip():
            raise ValueError("source-identity stage must be a non-empty trimmed string")
        current_data_revision, current_data_file_count = _data_tree_revision(
            self.data_root,
            excluded_relative_paths=self.data_revision_exclusions,
        )
        current_code_revision = _runtime_code_revision()
        if current_data_revision != self.data_revision or current_data_file_count != self.data_file_count:
            raise RuntimeError(
                f"Prepared scenario data changed {stage}: "
                f"prepared=({self.data_revision!r}, "
                f"{self.data_file_count}), "
                f"current=({current_data_revision!r}, "
                f"{current_data_file_count})",
            )
        if current_code_revision != self.code_revision:
            raise RuntimeError(
                f"Prepared scenario code changed {stage}: "
                f"prepared={self.code_revision!r}, "
                f"current={current_code_revision!r}",
            )

    def build(
        self,
        variant: str | PreparedVariant,
        seed: int,
        max_ticks: int,
        recorder: SimulationRecorder | None = None,
        *,
        record_events: bool = False,
        recorder_factory: (Callable[[SimulationContext], SimulationRecorder] | None) = None,
        engine_config: EngineConfig | None = None,
        campaign_config: CampaignConfig | None = None,
        battle_config: BattleConfig | None = None,
        strict_mode: bool | None = None,
        execution_mode: RuntimeExecutionMode | None = None,
    ) -> RuntimeSession:
        """Construct a fresh, independently revalidated production runtime."""
        if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
            raise ValueError("seed must be a non-negative strict integer")
        if not isinstance(max_ticks, int) or isinstance(max_ticks, bool) or max_ticks <= 0:
            raise ValueError("max_ticks must be a positive strict integer")

        selected = self.variant(variant) if isinstance(variant, str) else variant
        if not any(selected is prepared_variant for prepared_variant in self.variants):
            raise ValueError(
                "PreparedVariant does not belong to this PreparedScenario",
            )

        self.assert_source_identity(stage="before runtime construction")
        effective = CampaignScenarioConfig.model_validate(
            selected.config.model_dump(mode="python"),
        )
        context = ScenarioLoader(self.data_root).load(
            self.scenario_path,
            seed=seed,
            scenario_config=effective,
            doctrine_side_assignments=(selected.doctrine_side_assignments),
            era_config=selected.era_config,
            era_runtime_contract=selected.era_runtime_contract,
        )
        loaded_side_ids = tuple(context.units_by_side)
        if loaded_side_ids != self.side_ids:
            raise RuntimeError(
                "Loaded side topology does not match authored topology: "
                f"authored={self.side_ids!r}, loaded={loaded_side_ids!r}",
            )
        loaded_roster = tuple((side, len(context.units_by_side.get(side, ()))) for side, _ in self.authored_roster)
        if loaded_roster != self.authored_roster:
            raise RuntimeError(
                "Loaded roster does not match authored roster: "
                f"authored={self.authored_roster!r}, "
                f"loaded={loaded_roster!r}",
            )
        loaded_ids = [unit.entity_id for side in self.side_ids for unit in context.units_by_side[side]]
        if len(loaded_ids) != len(set(loaded_ids)):
            raise RuntimeError("Loaded roster contains duplicate unit IDs")
        initial_unit_assignments = _runtime_unit_assignments(context)
        loaded_roster_loadout_fingerprint = _roster_loadout_fingerprint(context)
        catalog_revision = _resolved_catalog_revision(context)
        doctrine_catalog_fingerprint = _canonical_digest(
            (context.school_registry.get_state()["schools"] if context.school_registry is not None else {}),
        )

        objectives = [
            ObjectiveState(
                objective_id=objective.objective_id,
                position=Position(
                    easting=objective.position[0],
                    northing=objective.position[1],
                    altitude=(objective.position[2] if len(objective.position) == 3 else 0.0),
                ),
                radius_m=objective.radius_m,
            )
            for objective in effective.objectives
        ]
        victory_evaluator = VictoryEvaluator(
            objectives=objectives,
            conditions=list(effective.victory_conditions),
            event_bus=context.event_bus,
            max_duration_s=effective.duration_hours * 3600.0,
        )
        recorder_modes = sum(
            (
                recorder is not None,
                record_events,
                recorder_factory is not None,
            ),
        )
        if recorder_modes > 1:
            raise ValueError(
                "recorder, record_events, and recorder_factory are mutually exclusive",
            )
        runtime_recorder = (
            SimulationRecorder(context.event_bus)
            if record_events
            else (recorder_factory(context) if recorder_factory is not None else recorder)
        )
        runtime_engine_config = (
            EngineConfig.model_validate(
                engine_config.model_dump(mode="python"),
            )
            if engine_config is not None
            else EngineConfig(max_ticks=max_ticks)
        )
        if runtime_engine_config.max_ticks != max_ticks:
            raise ValueError(
                "engine_config.max_ticks must equal the runtime max_ticks",
            )
        engine = SimulationEngine(
            context,
            config=runtime_engine_config,
            campaign_config=(
                CampaignConfig.model_validate(
                    campaign_config.model_dump(mode="python"),
                )
                if campaign_config is not None
                else None
            ),
            battle_config=(
                BattleConfig.model_validate(
                    battle_config.model_dump(mode="python"),
                )
                if battle_config is not None
                else None
            ),
            victory_evaluator=victory_evaluator,
            recorder=runtime_recorder,
            strict_mode=strict_mode,
            execution_mode=execution_mode,
        )
        self.assert_source_identity(stage="during runtime construction")
        return RuntimeSession(
            variant_id=selected.variant_id,
            seed=seed,
            max_ticks=max_ticks,
            context=context,
            victory_evaluator=victory_evaluator,
            engine=engine,
            recorder=runtime_recorder,
            source_fingerprint=self.source_fingerprint,
            config_fingerprint=selected.config_fingerprint,
            authored_roster=self.authored_roster,
            loaded_roster=loaded_roster,
            code_revision=self.code_revision,
            data_revision=self.data_revision,
            data_file_count=self.data_file_count,
            catalog_revision=catalog_revision,
            doctrine_catalog_fingerprint=doctrine_catalog_fingerprint,
            loaded_roster_loadout_fingerprint=(loaded_roster_loadout_fingerprint),
            initial_unit_assignments=initial_unit_assignments,
        )


class SimulationRuntimeFactory:
    """Authoritative constructor for consumers claiming production execution."""

    @staticmethod
    def _resolve_data_root(
        scenario_path: Path,
        data_root: str | Path | None,
    ) -> Path:
        if data_root is not None:
            resolved = Path(data_root).resolve()
            if not resolved.is_dir():
                raise ValueError(
                    f"data_root is not a directory: {resolved}",
                )
            return resolved
        for parent in scenario_path.parents:
            if parent.name == "scenarios":
                if parent.parent.parent.name == "eras":
                    return parent.parent.parent.parent.resolve()
                return parent.parent.resolve()
        raise AnalysisInputError(
            "Cannot infer data_root from a scenario outside a scenarios directory; pass data_root explicitly",
        )

    def prepare(
        self,
        path: str | Path,
        data_root: str | Path | None,
        variants: Sequence[AnalysisVariant],
    ) -> PreparedScenario:
        """Read a source once and prepare independent typed variants."""
        scenario_path = Path(path).resolve()
        if not scenario_path.is_file():
            raise FileNotFoundError(scenario_path)

        source_bytes = scenario_path.read_bytes()
        try:
            source_text = source_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(
                f"Scenario source is not valid UTF-8: {scenario_path}",
            ) from exc
        try:
            raw = load_yaml_unique(io.StringIO(source_text))
            source_config = parse_campaign_scenario_config(raw)
        except (TypeError, ValueError) as exc:
            raise AnalysisInputError(
                f"Invalid scenario source {scenario_path}: {exc}",
            ) from exc
        return self._prepare_config(
            scenario_path=scenario_path,
            source_data_path=scenario_path,
            data_root=self._resolve_data_root(scenario_path, data_root),
            source_config=source_config,
            source_fingerprint=hashlib.sha256(source_bytes).hexdigest(),
            variants=variants,
        )

    def prepare_config(
        self,
        source_config: CampaignScenarioConfig,
        data_root: str | Path,
        variants: Sequence[AnalysisVariant],
        *,
        source_label: str = "<typed-config>",
    ) -> PreparedScenario:
        """Prepare a typed source without a temporary serialization path."""
        if not isinstance(source_config, CampaignScenarioConfig):
            raise TypeError(
                "source_config must be a CampaignScenarioConfig",
            )
        if not isinstance(source_label, str) or not source_label or source_label != source_label.strip():
            raise ValueError(
                "source_label must be a non-empty trimmed string",
            )
        resolved_data_root = Path(data_root).resolve()
        if not resolved_data_root.is_dir():
            raise ValueError(
                f"data_root is not a directory: {resolved_data_root}",
            )
        copied_source = CampaignScenarioConfig.model_validate(
            source_config.model_dump(mode="python"),
        )
        return self._prepare_config(
            scenario_path=Path(source_label),
            source_data_path=None,
            data_root=resolved_data_root,
            source_config=copied_source,
            source_fingerprint=_canonical_digest(
                copied_source.model_dump(mode="json"),
            ),
            variants=variants,
        )

    def _prepare_config(
        self,
        *,
        scenario_path: Path,
        source_data_path: Path | None,
        data_root: Path,
        source_config: CampaignScenarioConfig,
        source_fingerprint: str,
        variants: Sequence[AnalysisVariant],
    ) -> PreparedScenario:
        """Share strict source preparation across file and typed inputs."""
        if not variants:
            raise AnalysisInputError(
                "At least one analysis variant is required",
            )
        if any(not isinstance(variant, AnalysisVariant) for variant in variants):
            raise TypeError("variants must contain only AnalysisVariant values")
        variant_ids = [variant.variant_id for variant in variants]
        if len(variant_ids) != len(set(variant_ids)):
            raise AnalysisInputError(
                f"Analysis variant IDs must be unique: {variant_ids!r}",
            )

        effective_variants: list[
            tuple[
                AnalysisVariant,
                CampaignScenarioConfig,
                EraConfig,
                EraRuntimeContract,
            ]
        ] = []
        for variant in variants:
            patch = variant.calibration_patch.to_sparse_patch(
                mode="python",
            )
            effective = load_campaign_scenario_config(
                None,
                patch,
                source_config=source_config,
            )
            era_config = get_era_config(effective.era)
            era_runtime_contract = EraRuntimeContract.resolve(
                selected_registry_id=effective.era,
                era_config=era_config,
                strategic_s=effective.tick_resolution.strategic_s,
                operational_s=effective.tick_resolution.operational_s,
                tactical_s=effective.tick_resolution.tactical_s,
                tick_duration_seconds=effective.tick_duration_seconds,
            )
            era_runtime_contract.validate_execution_horizon(
                start=parse_scenario_start_time(effective.date),
                duration_hours=effective.duration_hours,
            )
            effective_variants.append(
                (
                    variant,
                    effective,
                    era_config,
                    era_runtime_contract,
                ),
            )

        authored_roster = tuple(
            (
                side.side,
                sum(unit.count for unit in side.units),
            )
            for side in source_config.sides
        )
        empty_sides = [side for side, authored_count in authored_roster if authored_count <= 0]
        if empty_sides:
            raise AnalysisInputError(
                f"Authored roster is empty for sides: {empty_sides!r}",
            )

        authored_sides = {side for side, _ in authored_roster}
        doctrine_variants = [variant.doctrine_variant for variant in variants if variant.doctrine_variant is not None]
        if doctrine_variants:
            from stochastic_warfare.c2.ai.schools import SchoolLoader

            school_loader = SchoolLoader(data_root / "schools")
            school_loader.load_all()
            available_schools = set(school_loader.available_schools())
            for doctrine_variant in doctrine_variants:
                if doctrine_variant is None:
                    continue
                assignment_sides = {assignment.side for assignment in doctrine_variant.assignments}
                unknown_sides = sorted(
                    assignment_sides - authored_sides,
                )
                if unknown_sides:
                    raise AnalysisInputError(
                        f"Doctrine variant references unknown scenario sides: {unknown_sides!r}",
                    )
                unknown_schools = sorted(
                    {assignment.school_id for assignment in doctrine_variant.assignments} - available_schools
                )
                if unknown_schools:
                    raise AnalysisInputError(
                        f"Doctrine variant references unknown schools: {unknown_schools!r}",
                    )

        data_revision_exclusions: tuple[str, ...] = ()
        if source_data_path is not None:
            try:
                source_relative = source_data_path.relative_to(data_root)
            except ValueError:
                pass
            else:
                data_revision_exclusions = (source_relative.as_posix(),)
        data_revision, data_file_count = _data_tree_revision(
            data_root,
            excluded_relative_paths=data_revision_exclusions,
        )
        prepared_variants: list[PreparedVariant] = []
        for (
            variant,
            effective,
            era_config,
            era_runtime_contract,
        ) in effective_variants:
            doctrine_side_assignments = (
                variant.doctrine_variant.assignments if variant.doctrine_variant is not None else ()
            )
            prepared_variants.append(
                PreparedVariant(
                    variant_id=variant.variant_id,
                    config_json=effective.model_dump_json(),
                    config_fingerprint=_canonical_digest(
                        {
                            "scenario_config": effective.model_dump(
                                mode="json",
                            ),
                            "era_config": era_config.model_dump(
                                mode="json",
                            ),
                            "era_runtime_contract": (
                                era_runtime_contract.model_dump(mode="json")
                            ),
                            "doctrine_side_assignments": (doctrine_side_assignments),
                        },
                    ),
                    doctrine_side_assignments=doctrine_side_assignments,
                    era_config_json=era_config.model_dump_json(),
                    era_runtime_contract_json=(
                        era_runtime_contract.model_dump_json()
                    ),
                ),
            )

        return PreparedScenario(
            scenario_path=scenario_path,
            data_root=data_root,
            source_config_json=source_config.model_dump_json(),
            source_fingerprint=source_fingerprint,
            variants=tuple(prepared_variants),
            authored_roster=authored_roster,
            code_revision=_runtime_code_revision(),
            data_revision=data_revision,
            data_file_count=data_file_count,
            data_revision_exclusions=data_revision_exclusions,
        )
