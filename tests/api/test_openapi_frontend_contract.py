"""Fail-closed contracts for generated frontend OpenAPI transport types."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

import pytest

from scripts.generate_openapi_types import (
    DEFAULT_OUTPUT,
    OpenApiTypeGenerationError,
    check_generated_types,
    load_application_openapi,
    openapi_sha256,
    render_types,
)


def _synthetic_document() -> dict[str, Any]:
    return {
        "openapi": "3.1.0",
        "info": {"title": "Contract", "version": "1"},
        "paths": {
            "/api/widgets": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "array",
                                        "items": {
                                            "$ref": "#/components/schemas/Widget",
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
        "components": {
            "schemas": {
                "Widget": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["id"],
                    "properties": {
                        "id": {"type": "string"},
                        "label": {"type": "string"},
                    },
                },
            },
        },
    }


def test_tracked_types_match_complete_production_openapi() -> None:
    document = load_application_openapi()
    expected = render_types(document)

    current, message = check_generated_types(expected, DEFAULT_OUTPUT)

    assert current, message
    assert f"OpenAPI SHA-256: {openapi_sha256(document)}" in expected
    assert all(path.startswith("/api/") for path in document["paths"])


def test_missing_and_stale_generated_contracts_fail_closed(
    tmp_path: Path,
) -> None:
    expected = render_types(_synthetic_document())
    missing = tmp_path / "missing.generated.ts"

    current, message = check_generated_types(expected, missing)
    assert current is False
    assert "missing" in message

    stale = tmp_path / "stale.generated.ts"
    stale.write_text(expected.replace("Widget", "StaleWidget"), encoding="utf-8")
    current, message = check_generated_types(expected, stale)
    assert current is False
    assert "stale" in message


def _remove_schema(document: dict[str, Any]) -> None:
    document["components"]["schemas"]["Replacement"] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {},
    }
    del document["components"]["schemas"]["Widget"]


def _add_property(document: dict[str, Any]) -> None:
    document["components"]["schemas"]["Widget"]["properties"]["enabled"] = {
        "type": "boolean",
    }


def _change_property_type(document: dict[str, Any]) -> None:
    document["components"]["schemas"]["Widget"]["properties"]["id"] = {
        "type": "number",
    }


def _change_requiredness(document: dict[str, Any]) -> None:
    document["components"]["schemas"]["Widget"]["required"] = ["label"]


@pytest.mark.parametrize(
    ("mutate", "changed_fragment"),
    (
        (_add_property, '"enabled"?: boolean'),
        (_change_property_type, '"id": number'),
        (_change_requiredness, '"id"?: string'),
    ),
    ids=("extra", "type", "requiredness"),
)
def test_schema_shape_drift_rejects_the_previous_generated_contract(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], None],
    changed_fragment: str,
) -> None:
    baseline = _synthetic_document()
    tracked = tmp_path / "openapi.generated.ts"
    tracked.write_text(render_types(baseline), encoding="utf-8")
    changed = deepcopy(baseline)
    mutate(changed)
    regenerated = render_types(changed)

    current, message = check_generated_types(regenerated, tracked)

    assert current is False
    assert "stale" in message
    assert changed_fragment in regenerated


def test_missing_referenced_schema_rejects_generation() -> None:
    document = _synthetic_document()
    _remove_schema(document)

    with pytest.raises(
        OpenApiTypeGenerationError,
        match="missing component schemas: Widget",
    ):
        render_types(document)


def test_generation_is_independent_of_mapping_insertion_order() -> None:
    baseline = _synthetic_document()
    reordered = {
        key: baseline[key]
        for key in reversed(tuple(baseline))
    }

    assert render_types(reordered) == render_types(baseline)
