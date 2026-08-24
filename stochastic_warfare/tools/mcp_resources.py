"""MCP resource providers for scenario configs, unit definitions, and results.

These are registered as MCP resources so Claude can read them directly
without needing to use a tool call.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re
import stat
from typing import Any

from stochastic_warfare.application_paths import ApplicationPaths
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.tools.result_store import ResultStore
from stochastic_warfare.tools.serializers import serialize

logger = get_logger(__name__)

_RESOURCE_IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9_-]{0,254}")


@lru_cache(maxsize=1)
def _application_paths() -> ApplicationPaths:
    """Resolve the exact MCP resource owner once per server process."""
    return ApplicationPaths.discover()


def _validate_resource_identifier(value: str, *, field_name: str) -> str:
    """Require one exact, path-free MCP URI identifier."""
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or _RESOURCE_IDENTIFIER.fullmatch(value) is None
    ):
        raise ValueError(
            f"{field_name} must be one lowercase path-free identifier using only a-z, 0-9, '_' or '-'",
        )
    return value


def _resolve_resource_file(root: Path, *parts: str) -> Path | None:
    """Resolve one regular file below *root* without following symlinks."""
    resolved_root = root.resolve(strict=True)
    candidate = resolved_root.joinpath(*parts)
    current = resolved_root
    try:
        for part in parts:
            current = current / part
            if stat.S_ISLNK(current.lstat().st_mode):
                raise ValueError("MCP resources do not permit symlinks")
    except FileNotFoundError:
        return None

    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(resolved_root):
        raise ValueError("MCP resource escaped its configured catalog root")
    if not resolved.is_file():
        return None
    return resolved


def _resource_error(message: str) -> str:
    """Return one fail-closed MCP resource error payload."""
    return serialize({"error": True, "message": message})


def get_scenario_config(name: str) -> str:
    """Return scenario YAML content as string.

    Resource URI: ``scenario://{name}/config``
    """
    try:
        name = _validate_resource_identifier(name, field_name="scenario name")
        path = _resolve_resource_file(
            _application_paths().scenario_root,
            name,
            "scenario.yaml",
        )
    except (OSError, ValueError) as exc:
        return _resource_error(f"Invalid scenario resource: {exc}")
    if path is None:
        return _resource_error(f"Scenario '{name}' not found")
    return path.read_text(encoding="utf-8")


def get_unit_definition(category: str, unit_type: str) -> str:
    """Return unit definition YAML content.

    Resource URI: ``unit://{category}/{type}``
    """
    try:
        category = _validate_resource_identifier(
            category,
            field_name="unit category",
        )
        unit_type = _validate_resource_identifier(
            unit_type,
            field_name="unit type",
        )
        path = _resolve_resource_file(
            _application_paths().catalog_root / "units",
            category,
            f"{unit_type}.yaml",
        )
    except (OSError, ValueError) as exc:
        return _resource_error(f"Invalid unit resource: {exc}")
    if path is None:
        return _resource_error(f"Unit '{category}/{unit_type}' not found")
    return path.read_text(encoding="utf-8")


def get_cached_result(run_id: str, store: ResultStore) -> str:
    """Return cached result JSON.

    Resource URI: ``result://{run_id}``
    """
    try:
        run_id = _validate_resource_identifier(run_id, field_name="run ID")
    except ValueError as exc:
        return _resource_error(f"Invalid result resource: {exc}")
    result = store.get(run_id)
    if result is None:
        return _resource_error(f"Run '{run_id}' not found")
    return serialize(result.summary)


def register_resources(mcp: Any, store: ResultStore) -> None:
    """Register MCP resources on the server instance.

    Called during server setup to expose scenario configs, unit definitions,
    and cached results as readable resources.
    """

    @mcp.resource("scenario://{name}/config")
    async def scenario_resource(name: str) -> str:
        return get_scenario_config(name)

    @mcp.resource("unit://{category}/{unit_type}")
    async def unit_resource(category: str, unit_type: str) -> str:
        return get_unit_definition(category, unit_type)

    @mcp.resource("result://{run_id}")
    async def result_resource(run_id: str) -> str:
        return get_cached_result(run_id, store)
