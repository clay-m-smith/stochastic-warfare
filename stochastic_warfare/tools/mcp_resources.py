"""MCP resource providers for scenario configs, unit definitions, and results.

These are registered as MCP resources so Claude can read them directly
without needing to use a tool call.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.tools.result_store import ResultStore
from stochastic_warfare.tools.serializers import serialize

logger = get_logger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DATA_DIR = _PROJECT_ROOT / "data"


def get_scenario_config(name: str) -> str:
    """Return scenario YAML content as string.

    Resource URI: ``scenario://{name}/config``
    """
    path = _DATA_DIR / "scenarios" / name / "scenario.yaml"
    if not path.exists():
        return serialize({"error": True, "message": f"Scenario '{name}' not found"})
    return path.read_text(encoding="utf-8")


def get_unit_definition(category: str, unit_type: str) -> str:
    """Return unit definition YAML content.

    Resource URI: ``unit://{category}/{type}``
    """
    path = _DATA_DIR / "units" / category / f"{unit_type}.yaml"
    if not path.exists():
        return serialize({"error": True, "message": f"Unit '{category}/{unit_type}' not found"})
    return path.read_text(encoding="utf-8")


def get_cached_result(run_id: str, store: ResultStore) -> str:
    """Return cached result JSON.

    Resource URI: ``result://{run_id}``
    """
    result = store.get(run_id)
    if result is None:
        return serialize({"error": True, "message": f"Run '{run_id}' not found"})
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
