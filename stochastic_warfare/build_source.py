"""Pure source-revision classification shared by isolated build hooks."""

from __future__ import annotations

from collections.abc import Mapping
import fnmatch
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
from typing import Any


SOURCE_REVISION_ENV = "SOURCE_REVISION"
SOURCE_REVISION_FILENAME = "SOURCE_REVISION"
SOURCE_MANIFEST_FILENAME = "SOURCE_MANIFEST.json"
SOURCE_MANIFEST_SCHEMA_VERSION = 1
SDIST_SOURCE_ROOT_FILES = (
    "LICENSE.md",
    "README.md",
    "build_hooks.py",
    "pyproject.toml",
)
SDIST_GENERATED_INPUT_FILES = ("PKG-INFO", "setup.cfg")
PYTHON_SOURCE_ROOTS = ("api", "stochastic_warfare")
PROHIBITED_CHECKOUT_BUILD_FILES = ("MANIFEST.in", "setup.cfg", "setup.py")
ARTIFACT_INPUT_PATHS = (
    "LICENSE.md",
    "README.md",
    "api",
    "build_hooks.py",
    "data",
    "pyproject.toml",
    "stochastic_warfare",
)
_DEFAULT_LICENSE_PATTERNS = (
    "AUTHORS*",
    "COPYING*",
    "LICEN[CS]E*",
    "NOTICE*",
)
_EXPECTED_LICENSE_FILES = frozenset({"LICENSE.md"})
_REVISION_PATTERN = re.compile(r"[0-9a-f]{40}\Z")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


def _validate_revision(value: str, *, source: str) -> str:
    revision = value.strip()
    if _REVISION_PATTERN.fullmatch(revision) is None:
        raise RuntimeError(
            f"{source} must contain exactly 40 lowercase hexadecimal characters",
        )
    return revision


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _normalized_relative_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise RuntimeError("sdist input manifest path must be relative POSIX")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise RuntimeError("sdist input manifest path must be relative POSIX")
    return value


def _read_regular_file(root: Path, relative: str) -> bytes:
    path = root.joinpath(*PurePosixPath(relative).parts)
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise RuntimeError(
            f"required build input is unavailable: {relative!r}",
        ) from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise RuntimeError(
            f"sdist input must be a regular non-symlink file: {relative!r}",
        )
    return path.read_bytes()


def _lexical_absolute_path(value: str | os.PathLike[str]) -> Path:
    """Return an absolute path without dereferencing a lexical symlink."""
    return Path(os.path.abspath(os.fspath(value)))


def _require_regular_directory(path: Path, *, label: str) -> None:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise RuntimeError(f"{label} is unavailable: {path}") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise RuntimeError(
            f"{label} must be a regular non-symlink directory: {path}",
        )


def _checked_checkout_relative_path(path: Path, root: Path) -> str:
    relative = path.relative_to(root).as_posix()
    if (
        not relative
        or "\\" in relative
        or "\n" in relative
        or "\r" in relative
    ):
        raise RuntimeError(
            f"build input path is not a supported relative POSIX path: {relative!r}",
        )
    return relative


def _walk_regular_tree(
    project_root: Path,
    root_name: str,
    *,
    excluded_directories: frozenset[str] = frozenset(),
) -> list[tuple[str, Path]]:
    """Return regular files below one lexical, non-symlink source root."""
    source_root = project_root / root_name
    _require_regular_directory(source_root, label=f"build source root {root_name!r}")
    files: list[tuple[str, Path]] = []
    for directory, child_directories, filenames in os.walk(
        source_root,
        followlinks=False,
    ):
        current = Path(directory)
        retained: list[str] = []
        for child_name in sorted(child_directories):
            child = current / child_name
            relative = _checked_checkout_relative_path(child, project_root)
            try:
                metadata = child.lstat()
            except OSError as exc:
                raise RuntimeError(
                    f"cannot inspect build source directory {relative!r}",
                ) from exc
            if stat.S_ISLNK(metadata.st_mode):
                raise RuntimeError(
                    f"build source trees do not permit directory symlinks: {relative!r}",
                )
            if not stat.S_ISDIR(metadata.st_mode):
                raise RuntimeError(
                    f"build source tree contains a special directory entry: {relative!r}",
                )
            if child_name not in excluded_directories:
                retained.append(child_name)
        child_directories[:] = retained

        for filename in sorted(filenames):
            path = current / filename
            relative = _checked_checkout_relative_path(path, project_root)
            try:
                metadata = path.lstat()
            except OSError as exc:
                raise RuntimeError(
                    f"cannot inspect build source file {relative!r}",
                ) from exc
            if stat.S_ISLNK(metadata.st_mode):
                raise RuntimeError(
                    f"build source trees do not permit file symlinks: {relative!r}",
                )
            if not stat.S_ISREG(metadata.st_mode):
                raise RuntimeError(
                    f"build source tree contains a special file entry: {relative!r}",
                )
            files.append((relative, path))
    return files


def _python_build_inputs(project_root: Path) -> set[str]:
    inputs: set[str] = set()
    for root_name in PYTHON_SOURCE_ROOTS:
        for relative, path in _walk_regular_tree(project_root, root_name):
            if path.suffix != ".py":
                continue
            relative_path = PurePosixPath(relative)
            package_parts = relative_path.parts[:-1]
            if (
                path.name.startswith(".")
                or any(
                    part == "__pycache__"
                    or part.startswith(".")
                    or not part.isidentifier()
                    for part in package_parts
                )
            ):
                raise RuntimeError(
                    "Python build input is outside the explicit regular-package "
                    f"layout: {relative!r}",
                )
            inputs.add(relative)

    for relative in sorted(inputs):
        parts = PurePosixPath(relative).parts
        for depth in range(1, len(parts)):
            package_init = PurePosixPath(*parts[:depth], "__init__.py").as_posix()
            if package_init not in inputs:
                raise RuntimeError(
                    "Python build input is below a non-package directory: "
                    f"{relative!r} lacks {package_init!r}",
                )
    return inputs


def _catalog_build_inputs(project_root: Path) -> set[str]:
    inputs = {
        relative
        for relative, path in _walk_regular_tree(
            project_root,
            "data",
            excluded_directories=frozenset({"terrain_cache"}),
        )
        if path.suffix == ".yaml"
    }
    if not inputs:
        raise RuntimeError("catalog build input tree contains no YAML resources")
    return inputs


def validated_checkout_build_inputs(project_root: Path) -> tuple[str, ...]:
    """Return the exact regular checkout inputs accepted by setuptools hooks."""
    root = _lexical_absolute_path(project_root)
    _require_regular_directory(root, label="project root")

    prohibited = tuple(
        name
        for name in PROHIBITED_CHECKOUT_BUILD_FILES
        if _entry_exists(root / name)
    )
    if prohibited:
        raise RuntimeError(
            "checkout contains prohibited legacy build configuration: "
            + ", ".join(prohibited),
        )

    observed_licenses = {
        child.name
        for child in root.iterdir()
        if any(
            fnmatch.fnmatchcase(child.name, pattern)
            for pattern in _DEFAULT_LICENSE_PATTERNS
        )
    }
    if observed_licenses != _EXPECTED_LICENSE_FILES:
        raise RuntimeError(
            "checkout license inputs must be exactly LICENSE.md; observed "
            + ", ".join(sorted(observed_licenses)),
        )

    inputs = set(SDIST_SOURCE_ROOT_FILES)
    for relative in SDIST_SOURCE_ROOT_FILES:
        _read_regular_file(root, relative)
    inputs.update(_python_build_inputs(root))
    inputs.update(_catalog_build_inputs(root))
    return tuple(sorted(inputs))


def prepare_clean_wheel_build_root(
    project_root: Path,
    build_root: Path,
) -> Path:
    """Validate and clear one in-checkout wheel staging directory."""
    project = _lexical_absolute_path(project_root)
    raw_output = Path(build_root)
    output = _lexical_absolute_path(
        raw_output if raw_output.is_absolute() else project / raw_output,
    )
    _require_regular_directory(project, label="project root")
    trusted_parent = project / "build"
    if output == trusted_parent or not output.is_relative_to(trusted_parent):
        raise RuntimeError(
            "wheel build root must be a child of the checkout build directory",
        )

    current = project
    for component in output.relative_to(project).parts:
        current /= component
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            break
        except OSError as exc:
            raise RuntimeError(
                f"cannot inspect wheel build output component: {current}",
            ) from exc
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise RuntimeError(
                "wheel build output components must be regular non-symlink "
                f"directories: {current}",
            )

    try:
        output.lstat()
    except FileNotFoundError:
        pass
    else:
        shutil.rmtree(output)
    return output


def _entry_exists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise RuntimeError(
            f"cannot inspect source receipt marker {path.name!r}",
        ) from exc
    return True


def has_sdist_source_receipt_markers(project_root: Path) -> bool:
    """Return whether either lexical sdist source-receipt marker exists."""
    root = Path(project_root)
    return any(
        _entry_exists(root / name)
        for name in (SOURCE_REVISION_FILENAME, SOURCE_MANIFEST_FILENAME)
    )


def _filesystem_sdist_inputs(root: Path) -> set[str]:
    inputs: set[str] = set()
    for directory, child_directories, filenames in os.walk(
        root,
        followlinks=False,
    ):
        current = Path(directory)
        retained: list[str] = []
        for child_name in sorted(child_directories):
            child = current / child_name
            relative = child.relative_to(root).as_posix()
            metadata = child.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                raise RuntimeError(
                    f"sdist input tree does not permit symlinks: {relative!r}",
                )
            if not stat.S_ISDIR(metadata.st_mode):
                raise RuntimeError(
                    f"sdist input tree contains a special entry: {relative!r}",
                )
            if (
                child_name != "__pycache__"
                and not child_name.endswith(".egg-info")
            ):
                retained.append(child_name)
        child_directories[:] = retained
        for filename in sorted(filenames):
            relative = (current / filename).relative_to(root).as_posix()
            if relative in {
                SOURCE_MANIFEST_FILENAME,
                SOURCE_REVISION_FILENAME,
            } or filename.endswith((".pyc", ".pyo")):
                continue
            _read_regular_file(root, relative)
            inputs.add(relative)
    return inputs


def write_sdist_input_manifest(
    release_root: Path,
    revision: str,
    relative_files: list[str],
) -> Path:
    """Bind every wheel-affecting sdist input to its source revision."""
    root = release_root.resolve()
    checked_revision = _validate_revision(revision, source="sdist revision")
    normalized = sorted(
        {_normalized_relative_path(value) for value in relative_files},
    )
    actual = _filesystem_sdist_inputs(root)
    if actual != set(normalized):
        raise RuntimeError(
            "sdist release tree differs from its explicit input allowlist",
        )
    files: list[dict[str, object]] = []
    for relative in normalized:
        payload = _read_regular_file(root, relative)
        files.append(
            {
                "path": relative,
                "size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            },
        )
    receipt: dict[str, object] = {
        "schema_version": SOURCE_MANIFEST_SCHEMA_VERSION,
        "revision": checked_revision,
        "files": files,
    }
    receipt["manifest_sha256"] = _canonical_sha256(receipt)
    destination = root / SOURCE_MANIFEST_FILENAME
    destination.write_text(
        json.dumps(
            receipt,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return destination


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RuntimeError(
                f"sdist input manifest contains duplicate key {key!r}",
            )
        result[key] = value
    return result


def verify_sdist_input_manifest(
    release_root: Path,
    revision: str,
) -> None:
    """Reject an extracted sdist whose allowlisted bytes changed."""
    root = release_root.resolve()
    try:
        raw = json.loads(
            _read_regular_file(
                root,
                SOURCE_MANIFEST_FILENAME,
            ).decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda value: (_ for _ in ()).throw(
                RuntimeError(
                    f"sdist input manifest contains constant {value!r}",
                ),
            ),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("sdist input manifest is unavailable or malformed") from exc
    if not isinstance(raw, dict) or set(raw) != {
        "schema_version",
        "revision",
        "files",
        "manifest_sha256",
    }:
        raise RuntimeError("sdist input manifest has unsupported fields")
    persisted_digest = raw.pop("manifest_sha256")
    if (
        not isinstance(persisted_digest, str)
        or _SHA256_PATTERN.fullmatch(persisted_digest) is None
        or persisted_digest != _canonical_sha256(raw)
    ):
        raise RuntimeError("sdist input manifest self-digest does not match")
    if raw["schema_version"] != SOURCE_MANIFEST_SCHEMA_VERSION:
        raise RuntimeError("sdist input manifest schema is unsupported")
    checked_revision = _validate_revision(revision, source="sdist revision")
    if raw["revision"] != checked_revision:
        raise RuntimeError("sdist input manifest revision does not match")
    raw_files = raw["files"]
    if not isinstance(raw_files, list):
        raise RuntimeError("sdist input manifest files must be an ordered list")
    observed_paths: list[str] = []
    for entry in raw_files:
        if not isinstance(entry, dict) or set(entry) != {
            "path",
            "size",
            "sha256",
        }:
            raise RuntimeError("sdist input manifest file entry is malformed")
        relative = _normalized_relative_path(entry["path"])
        size = entry["size"]
        digest = entry["sha256"]
        if type(size) is not int or size < 0:
            raise RuntimeError("sdist input manifest file size is invalid")
        if not isinstance(digest, str) or _SHA256_PATTERN.fullmatch(digest) is None:
            raise RuntimeError("sdist input manifest file digest is invalid")
        payload = _read_regular_file(root, relative)
        if len(payload) != size or hashlib.sha256(payload).hexdigest() != digest:
            raise RuntimeError(
                f"sdist input manifest mismatch for {relative!r}",
            )
        observed_paths.append(relative)
    if observed_paths != sorted(set(observed_paths)):
        raise RuntimeError("sdist input manifest paths are not sorted and unique")
    if _filesystem_sdist_inputs(root) != set(observed_paths):
        raise RuntimeError("sdist input manifest does not cover the exact input tree")


def _run_git(
    root: Path,
    arguments: tuple[str, ...],
    *,
    operation: str,
    input_payload: bytes | None = None,
) -> bytes:
    completed = subprocess.run(
        ("git", "-C", os.fspath(root), *arguments),
        check=False,
        capture_output=True,
        input=input_payload,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"cannot {operation}: {detail or 'Git command failed'}",
        )
    return completed.stdout


def _decode_git_path(payload: bytes) -> str:
    try:
        value = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError("Git build input paths must be UTF-8") from exc
    if not value or "\\" in value or "\n" in value or "\r" in value:
        raise RuntimeError(f"Git build input path is unsupported: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise RuntimeError(f"Git build input path is unsupported: {value!r}")
    return value


def _is_checkout_build_input_path(relative: str) -> bool:
    if relative in SDIST_SOURCE_ROOT_FILES:
        return True
    parts = PurePosixPath(relative).parts
    if len(parts) < 2:
        return False
    if parts[0] in PYTHON_SOURCE_ROOTS:
        return relative.endswith(".py")
    return (
        parts[0] == "data"
        and "terrain_cache" not in parts[1:-1]
        and relative.endswith(".yaml")
    )


def _is_owned_tree_path(relative: str) -> bool:
    parts = PurePosixPath(relative).parts
    if not parts:
        return False
    if parts[0] in PYTHON_SOURCE_ROOTS:
        return True
    return parts[0] == "data" and "terrain_cache" not in parts[1:]


def _head_build_inputs(
    root: Path,
    revision: str,
) -> dict[str, tuple[str, str]]:
    output = _run_git(
        root,
        (
            "ls-tree",
            "-r",
            "-z",
            revision,
            "--",
            *ARTIFACT_INPUT_PATHS,
        ),
        operation="enumerate immutable Git build inputs",
    )
    selected: dict[str, tuple[str, str]] = {}
    for record in output.split(b"\0"):
        if not record:
            continue
        try:
            metadata, raw_path = record.split(b"\t", 1)
            mode, object_type, object_id = metadata.decode("ascii").split()
        except (UnicodeDecodeError, ValueError) as exc:
            raise RuntimeError("Git build input tree entry is malformed") from exc
        relative = _decode_git_path(raw_path)
        if _is_owned_tree_path(relative) and (
            mode not in {"100644", "100755"} or object_type != "blob"
        ):
            raise RuntimeError(
                "Git build input tree contains a symlink, gitlink, or special "
                f"entry: {relative!r}",
            )
        if not _is_checkout_build_input_path(relative):
            continue
        if mode not in {"100644", "100755"} or object_type != "blob":
            raise RuntimeError(
                f"Git build input is not a regular blob: {relative!r}",
            )
        selected[relative] = (mode, object_id)
    return selected


def _verify_clean_git_build_inputs(
    root: Path,
    revision: str,
    checkout_inputs: tuple[str, ...],
) -> None:
    head_inputs = _head_build_inputs(root, revision)
    current_paths = set(checkout_inputs)
    head_paths = set(head_inputs)
    if current_paths != head_paths:
        missing = sorted(head_paths - current_paths)
        added = sorted(current_paths - head_paths)
        raise RuntimeError(
            "checkout build inputs differ from immutable Git HEAD; "
            f"missing={missing[:5]!r}, added_or_ignored={added[:5]!r}",
        )

    index_output = _run_git(
        root,
        ("ls-files", "-v", "-z", "--", *ARTIFACT_INPUT_PATHS),
        operation="inspect Git build-input index flags",
    )
    observed_index_paths: set[str] = set()
    unsupported_flags: list[tuple[str, str]] = []
    for record in index_output.split(b"\0"):
        if not record:
            continue
        if len(record) < 3 or record[1:2] != b" ":
            raise RuntimeError("Git build-input index entry is malformed")
        relative = _decode_git_path(record[2:])
        if relative not in head_paths:
            continue
        observed_index_paths.add(relative)
        flag = chr(record[0])
        if flag != "H":
            unsupported_flags.append((flag, relative))
    if observed_index_paths != head_paths:
        raise RuntimeError("Git index does not contain the exact immutable build inputs")
    if unsupported_flags:
        raise RuntimeError(
            "Git build inputs use unsupported assume-unchanged, skip-worktree, "
            f"or nonstandard index flags: {unsupported_flags[:5]!r}",
        )

    mismatched_modes: list[str] = []
    for relative in checkout_inputs:
        metadata = root.joinpath(*PurePosixPath(relative).parts).lstat()
        current_mode = "100755" if metadata.st_mode & 0o111 else "100644"
        head_mode, _object_id = head_inputs[relative]
        if current_mode != head_mode:
            mismatched_modes.append(relative)
    if mismatched_modes:
        raise RuntimeError(
            "current build-input modes differ from immutable Git HEAD: "
            f"{mismatched_modes[:5]!r}",
        )

    status = _run_git(
        root,
        (
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
            "--",
            *ARTIFACT_INPUT_PATHS,
        ),
        operation="classify source cleanliness",
    )
    if status:
        raise RuntimeError(
            "refusing to label dirty application inputs as clean Git HEAD; "
            f"a trusted build pipeline must set {SOURCE_REVISION_ENV} explicitly",
        )

    hash_input = ("\n".join(checkout_inputs) + "\n").encode("utf-8")
    hash_output = _run_git(
        root,
        ("hash-object", "--stdin-paths"),
        operation="hash current Git build inputs",
        input_payload=hash_input,
    )
    current_hashes = hash_output.decode("ascii").splitlines()
    if len(current_hashes) != len(checkout_inputs):
        raise RuntimeError("Git did not hash every current build input")
    mismatched = [
        relative
        for relative, object_id in zip(
            checkout_inputs,
            current_hashes,
            strict=True,
        )
        if object_id != head_inputs[relative][1]
    ]
    if mismatched:
        raise RuntimeError(
            "current build-input bytes differ from immutable Git HEAD: "
            f"{mismatched[:5]!r}",
        )

    if validated_checkout_build_inputs(root) != checkout_inputs:
        raise RuntimeError("checkout build inputs changed during revision validation")
    final_revision = _validate_revision(
        _run_git(
            root,
            ("rev-parse", "--verify", "HEAD"),
            operation="recheck immutable Git revision",
        ).decode("ascii"),
        source="Git HEAD",
    )
    if final_revision != revision:
        raise RuntimeError("Git HEAD changed during build-input validation")


def resolve_source_revision(
    project_root: Path,
    *,
    environment: Mapping[str, str] | None = None,
) -> str:
    """Resolve one clean or pipeline-authorized immutable source revision."""
    root = _lexical_absolute_path(project_root)
    env = os.environ if environment is None else environment
    configured = env.get(SOURCE_REVISION_ENV)
    has_revision = _entry_exists(root / SOURCE_REVISION_FILENAME)
    has_manifest = _entry_exists(root / SOURCE_MANIFEST_FILENAME)
    if has_revision or has_manifest:
        if not has_revision or not has_manifest:
            raise RuntimeError(
                "sdist source receipt requires both SOURCE_REVISION and "
                "SOURCE_MANIFEST.json",
            )
        try:
            receipt_payload = _read_regular_file(
                root,
                SOURCE_REVISION_FILENAME,
            ).decode("utf-8")
        except (OSError, UnicodeError) as exc:
            raise RuntimeError(
                "sdist source revision receipt is unavailable or malformed",
            ) from exc
        revision = _validate_revision(
            receipt_payload,
            source=SOURCE_REVISION_FILENAME,
        )
        if configured is not None:
            configured_revision = _validate_revision(
                configured,
                source=SOURCE_REVISION_ENV,
            )
            if configured_revision != revision:
                raise RuntimeError(
                    "SOURCE_REVISION does not match sdist receipt revision",
                )
        verify_sdist_input_manifest(root, revision)
        return revision

    checkout_inputs = validated_checkout_build_inputs(root)
    if configured is not None:
        return _validate_revision(configured, source=SOURCE_REVISION_ENV)

    git_root = _lexical_absolute_path(
        _run_git(
            root,
            ("rev-parse", "--show-toplevel"),
            operation="locate the owning Git worktree",
        ).decode("utf-8").strip(),
    )
    if git_root != root:
        raise RuntimeError(
            "build checkout must be the owning Git worktree root; "
            f"project={root}, git={git_root}",
        )
    revision = _validate_revision(
        _run_git(
            root,
            ("rev-parse", "--verify", "HEAD"),
            operation="resolve an immutable source revision",
        ).decode("ascii"),
        source="Git HEAD",
    )
    _verify_clean_git_build_inputs(root, revision, checkout_inputs)
    return revision
