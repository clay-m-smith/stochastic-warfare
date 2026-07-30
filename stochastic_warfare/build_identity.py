"""Fail-closed identity for immutable application packages.

Git worktrees remain the authoritative source identity during development and
benchmarking.  This module supplies the equivalent immutable identity for
production packages, such as the Docker image, that deliberately omit Git
metadata.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterator
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any


BUILD_IDENTITY_SCHEMA_VERSION = 1
BUILD_IDENTITY_RELATIVE_PATH = Path("stochastic_warfare/_build_identity.json")
APPLICATION_SOURCE_DIRECTORIES = ("stochastic_warfare", "api")
APPLICATION_SOURCE_FILES = ("pyproject.toml", "uv.lock")

_COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}\Z")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_INTERPRETER_CACHE_DIRECTORIES = frozenset({"__pycache__"})
_INTERPRETER_CACHE_SUFFIXES = (".pyc", ".pyo")


class BuildIdentityError(ValueError):
    """An immutable package identity is absent, malformed, or unverifiable."""


@dataclass(frozen=True)
class BuildIdentity:
    """Strict immutable-package identity loaded from production artifacts."""

    schema_version: int
    commit: str
    source_manifest_sha256: str


def _normalized_mode(metadata: os.stat_result) -> str:
    executable_bits = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    return "100755" if metadata.st_mode & executable_bits else "100644"


def _read_regular_file(path: Path, *, display_path: str) -> tuple[bytes, os.stat_result]:
    """Read one stable regular file without following filesystem indirection."""
    try:
        initial = path.lstat()
    except OSError as exc:
        raise BuildIdentityError(
            f"application source file cannot be inspected: {display_path!r}",
        ) from exc
    if stat.S_ISLNK(initial.st_mode):
        raise BuildIdentityError(
            f"application source manifest does not permit symlinks: {display_path!r}",
        )
    if not stat.S_ISREG(initial.st_mode):
        raise BuildIdentityError(
            f"application source entry must be a regular file: {display_path!r}",
        )

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise BuildIdentityError(
            f"application source file cannot be opened: {display_path!r}",
        ) from exc
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_dev != initial.st_dev
            or opened.st_ino != initial.st_ino
        ):
            raise BuildIdentityError(
                f"application source entry changed during capture: {display_path!r}",
            )
        chunks: list[bytes] = []
        while chunk := os.read(descriptor, 1024 * 1024):
            chunks.append(chunk)
        final = os.fstat(descriptor)
    finally:
        os.close(descriptor)

    stable_fields = (
        "st_dev",
        "st_ino",
        "st_mode",
        "st_size",
        "st_mtime_ns",
    )
    if any(getattr(opened, field) != getattr(final, field) for field in stable_fields):
        raise BuildIdentityError(
            f"application source entry changed during capture: {display_path!r}",
        )
    payload = b"".join(chunks)
    if len(payload) != final.st_size:
        raise BuildIdentityError(
            f"application source entry changed during capture: {display_path!r}",
        )
    return payload, final


def _iter_source_files(application_root: Path) -> Iterator[tuple[Path, str]]:
    """Yield every source-owned file in deterministic relative-path order."""
    paths: list[tuple[Path, str]] = []
    for relative_directory in APPLICATION_SOURCE_DIRECTORIES:
        directory = application_root / relative_directory
        try:
            metadata = directory.lstat()
        except OSError as exc:
            raise BuildIdentityError(
                f"application source directory is missing: {relative_directory!r}",
            ) from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise BuildIdentityError(
                f"application source manifest does not permit symlinks: {relative_directory!r}",
            )
        if not stat.S_ISDIR(metadata.st_mode):
            raise BuildIdentityError(
                f"application source entry must be a directory: {relative_directory!r}",
            )

        for directory_path, child_directories, filenames in os.walk(
            directory,
            followlinks=False,
        ):
            current = Path(directory_path)
            retained_directories: list[str] = []
            for child_name in sorted(child_directories):
                child = current / child_name
                relative = child.relative_to(application_root).as_posix()
                try:
                    child_metadata = child.lstat()
                except OSError as exc:
                    raise BuildIdentityError(
                        f"application source entry cannot be inspected: {relative!r}",
                    ) from exc
                if stat.S_ISLNK(child_metadata.st_mode):
                    raise BuildIdentityError(
                        f"application source manifest does not permit symlinks: {relative!r}",
                    )
                if not stat.S_ISDIR(child_metadata.st_mode):
                    raise BuildIdentityError(
                        f"application source entry must be a directory: {relative!r}",
                    )
                if child_name not in _INTERPRETER_CACHE_DIRECTORIES:
                    retained_directories.append(child_name)
            child_directories[:] = retained_directories

            for filename in sorted(filenames):
                path = current / filename
                relative = path.relative_to(application_root).as_posix()
                if Path(relative) == BUILD_IDENTITY_RELATIVE_PATH:
                    continue
                if filename.endswith(_INTERPRETER_CACHE_SUFFIXES):
                    metadata = path.lstat()
                    if stat.S_ISLNK(metadata.st_mode):
                        raise BuildIdentityError(
                            f"application source manifest does not permit symlinks: {relative!r}",
                        )
                    if not stat.S_ISREG(metadata.st_mode):
                        raise BuildIdentityError(
                            f"application source entry must be a regular file: {relative!r}",
                        )
                    continue
                paths.append((path, relative))

    for relative_file in APPLICATION_SOURCE_FILES:
        paths.append((application_root / relative_file, relative_file))
    yield from sorted(paths, key=lambda item: item[1])


def application_source_manifest(application_root: Path) -> tuple[dict[str, Any], ...]:
    """Return the exact canonical manifest for production application source."""
    root = application_root.resolve()
    manifest: list[dict[str, Any]] = []
    for path, relative in _iter_source_files(root):
        payload, metadata = _read_regular_file(path, display_path=relative)
        manifest.append(
            {
                "path": relative,
                "mode": _normalized_mode(metadata),
                "size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            },
        )
    if not manifest:
        raise BuildIdentityError("application source manifest contains no files")
    return tuple(manifest)


def application_source_manifest_sha256(application_root: Path) -> str:
    """Return a deterministic digest of the exact application-source manifest."""
    encoded = json.dumps(
        application_source_manifest(application_root),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_identity_payload(payload: Any) -> BuildIdentity:
    if not isinstance(payload, dict):
        raise BuildIdentityError("build identity must be a JSON object")
    expected_keys = {
        "schema_version",
        "commit",
        "source_manifest_sha256",
    }
    if set(payload) != expected_keys:
        raise BuildIdentityError(
            "build identity must contain exactly "
            "schema_version, commit, and source_manifest_sha256",
        )
    schema_version = payload["schema_version"]
    commit = payload["commit"]
    source_manifest_sha256 = payload["source_manifest_sha256"]
    if type(schema_version) is not int or schema_version != BUILD_IDENTITY_SCHEMA_VERSION:
        raise BuildIdentityError(
            f"build identity schema_version must equal {BUILD_IDENTITY_SCHEMA_VERSION}",
        )
    if not isinstance(commit, str) or _COMMIT_PATTERN.fullmatch(commit) is None:
        raise BuildIdentityError(
            "build identity commit must be exactly 40 lowercase hexadecimal characters",
        )
    if (
        not isinstance(source_manifest_sha256, str)
        or _SHA256_PATTERN.fullmatch(source_manifest_sha256) is None
    ):
        raise BuildIdentityError(
            "build identity source_manifest_sha256 must be exactly "
            "64 lowercase hexadecimal characters",
        )
    return BuildIdentity(
        schema_version=schema_version,
        commit=commit,
        source_manifest_sha256=source_manifest_sha256,
    )


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BuildIdentityError(
                f"build identity contains duplicate JSON key {key!r}",
            )
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise BuildIdentityError(
        f"build identity contains non-finite JSON constant {value!r}",
    )


def find_application_root(start: Path) -> Path:
    """Find the nearest ancestor containing the generated identity file."""
    candidate = start.absolute()
    if candidate.is_file():
        candidate = candidate.parent
    for root in (candidate, *candidate.parents):
        identity_path = root / BUILD_IDENTITY_RELATIVE_PATH
        try:
            identity_path.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise BuildIdentityError(
                f"build identity cannot be inspected: {identity_path}",
            ) from exc
        return root
    raise BuildIdentityError(
        f"no immutable build identity found above {start}",
    )


def load_verified_build_identity(start: Path) -> BuildIdentity:
    """Load one exact-schema identity and verify its immutable source digest."""
    application_root = find_application_root(start)
    identity_path = application_root / BUILD_IDENTITY_RELATIVE_PATH
    payload_bytes, _ = _read_regular_file(
        identity_path,
        display_path=BUILD_IDENTITY_RELATIVE_PATH.as_posix(),
    )
    try:
        payload = json.loads(
            payload_bytes.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BuildIdentityError(
            "build identity must be valid UTF-8 JSON",
        ) from exc
    identity = _validate_identity_payload(payload)
    current_manifest_sha256 = application_source_manifest_sha256(
        application_root,
    )
    if current_manifest_sha256 != identity.source_manifest_sha256:
        raise BuildIdentityError(
            "build identity source manifest does not match packaged application source",
        )
    return identity


def write_build_identity(application_root: Path, commit: str) -> Path:
    """Generate one immutable identity after application source is staged."""
    root = application_root.resolve()
    identity = _validate_identity_payload(
        {
            "schema_version": BUILD_IDENTITY_SCHEMA_VERSION,
            "commit": commit,
            "source_manifest_sha256": application_source_manifest_sha256(root),
        },
    )
    identity_path = root / BUILD_IDENTITY_RELATIVE_PATH
    try:
        existing = identity_path.lstat()
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise BuildIdentityError(
            f"build identity cannot be inspected: {identity_path}",
        ) from exc
    else:
        if stat.S_ISLNK(existing.st_mode):
            raise BuildIdentityError(
                "build identity generation does not permit a symlink target",
            )
        if not stat.S_ISREG(existing.st_mode):
            raise BuildIdentityError(
                "build identity generation target must be a regular file",
            )
    identity_path.write_text(
        json.dumps(
            {
                "schema_version": identity.schema_version,
                "commit": identity.commit,
                "source_manifest_sha256": identity.source_manifest_sha256,
            },
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return identity_path


def main() -> None:
    """Generate a staged immutable-package identity from the command line."""
    parser = argparse.ArgumentParser(
        description="Generate the immutable Stochastic Warfare build identity",
    )
    parser.add_argument("--application-root", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    arguments = parser.parse_args()
    identity_path = write_build_identity(
        arguments.application_root,
        arguments.commit,
    )
    print(identity_path)


if __name__ == "__main__":
    main()
