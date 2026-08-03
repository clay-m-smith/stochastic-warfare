"""Shared strict serialization helpers for production historical backtests."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict

from stochastic_warfare.core.strict_yaml import load_yaml_unique


_STABLE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class StrictFrozenModel(BaseModel):
    """Immutable, extra-forbidding base for persisted backtest contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)


def require_trimmed(value: Any, *, field_name: str) -> str:
    """Return one non-empty trimmed string or reject."""
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field_name} must be a non-empty trimmed string")
    return value


def require_stable_id(value: Any, *, field_name: str) -> str:
    """Return one lowercase stable identifier or reject."""
    text = require_trimmed(value, field_name=field_name)
    if _STABLE_ID_PATTERN.fullmatch(text) is None:
        raise ValueError(
            f"{field_name} must contain only lowercase letters, digits, periods, underscores, and hyphens",
        )
    return text


def require_relative_posix_path(value: Any, *, field_name: str) -> str:
    """Reject ambiguous, absolute, traversing, or platform-specific paths."""
    text = require_trimmed(value, field_name=field_name)
    if "\\" in text:
        raise ValueError(f"{field_name} must use POSIX separators")
    path = PurePosixPath(text)
    if (
        not path.parts
        or text != path.as_posix()
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError(
            f"{field_name} must be a repository-relative POSIX path",
        )
    return path.as_posix()


def require_no_symlink_path(path: Path, *, field_name: str) -> Path:
    """Reject an existing symlink in the lexical path before resolution.

    Walking the authored components is essential: resolving first would erase
    the alias that this boundary is intended to reject. Missing components are
    permitted so callers can validate a publication target before creating its
    parent directories.
    """
    candidate = Path(path)
    absolute = candidate if candidate.is_absolute() else Path.cwd() / candidate
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.is_symlink():
            raise ValueError(f"{field_name} must not traverse a symlink")
    return candidate


def resolve_repository_path(
    repository_root: Path,
    relative_path: str,
    *,
    field_name: str,
    require_file: bool = True,
) -> Path:
    """Resolve one declared path without permitting symlink escape."""
    normalized = require_relative_posix_path(
        relative_path,
        field_name=field_name,
    )
    root = repository_root.resolve(strict=True)
    candidate = root.joinpath(*PurePosixPath(normalized).parts)
    require_no_symlink_path(candidate, field_name=field_name)
    if require_file and not candidate.is_file():
        raise ValueError(f"{field_name} does not identify a file: {normalized!r}")
    resolved = candidate.resolve(strict=require_file)
    if not resolved.is_relative_to(root):
        raise ValueError(f"{field_name} escapes the repository root")
    return candidate


def canonical_value(value: Any) -> Any:
    """Convert a model payload to finite, JSON-safe canonical primitives."""
    if isinstance(value, BaseModel):
        return canonical_value(
            value.model_dump(mode="json", exclude_none=False),
        )
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("canonical payload contains a non-finite number")
        return value
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("canonical payload mapping keys must be strings")
        return {key: canonical_value(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [canonical_value(item) for item in value]
    raise TypeError(
        f"canonical payload contains unsupported type {type(value).__name__}",
    )


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize canonical primitives while preserving authored list order."""
    return json.dumps(
        canonical_value(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    """Return the SHA-256 digest of the canonical JSON representation."""
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def load_unique_mapping(path: Path) -> dict[str, Any]:
    """Load a YAML mapping through the repository duplicate-key boundary."""
    with path.open(encoding="utf-8") as stream:
        value = load_yaml_unique(stream)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain one YAML mapping")
    return value
