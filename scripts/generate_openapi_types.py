#!/usr/bin/env python3
"""Generate deterministic frontend transport types from FastAPI OpenAPI.

The generated TypeScript is intentionally dependency-free: FastAPI/Pydantic
remain the schema authority, while this small renderer covers the JSON Schema
vocabulary emitted by this application.  ``--check`` is the CI drift gate and
never rewrites the tracked frontend contract.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPOSITORY_ROOT / "frontend/src/types/openapi.generated.ts"
_HTTP_METHODS = (
    "delete",
    "get",
    "head",
    "options",
    "patch",
    "post",
    "put",
    "trace",
)
_IDENTIFIER = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")


class OpenApiTypeGenerationError(ValueError):
    """The OpenAPI document contains an unsupported or malformed shape."""


def canonical_openapi_bytes(document: Mapping[str, Any]) -> bytes:
    """Return the exact order-independent OpenAPI identity used by the gate."""
    return (
        json.dumps(
            document,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def openapi_sha256(document: Mapping[str, Any]) -> str:
    """Return the canonical digest of the complete OpenAPI document."""
    return hashlib.sha256(canonical_openapi_bytes(document)).hexdigest()


def load_application_openapi() -> dict[str, Any]:
    """Build the production FastAPI route graph without entering its lifespan."""
    from api.main import create_app

    document = create_app().openapi()
    if not isinstance(document, dict):
        raise OpenApiTypeGenerationError("FastAPI returned a non-object OpenAPI document")
    return document


def _quoted(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _indent(value: str, spaces: int = 2) -> str:
    prefix = " " * spaces
    return "\n".join(prefix + line for line in value.splitlines())


def _literal(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return _quoted(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return json.dumps(value, allow_nan=False)
    raise OpenApiTypeGenerationError(
        f"unsupported JSON Schema literal {value!r}",
    )


def _union(members: Sequence[str]) -> str:
    unique = tuple(dict.fromkeys(members))
    if not unique:
        return "never"
    if len(unique) == 1:
        return unique[0]
    return " | ".join(
        f"({member})" if "\n" in member else member
        for member in unique
    )


def _intersection(members: Sequence[str]) -> str:
    unique = tuple(dict.fromkeys(members))
    if not unique:
        return "unknown"
    if len(unique) == 1:
        return unique[0]
    return " & ".join(
        f"({member})" if "\n" in member else member
        for member in unique
    )


def _reference_schema_name(reference: str) -> str:
    prefix = "#/components/schemas/"
    if not reference.startswith(prefix):
        raise OpenApiTypeGenerationError(
            f"only local component-schema references are supported: {reference!r}",
        )
    encoded_name = reference.removeprefix(prefix)
    return encoded_name.replace("~1", "/").replace("~0", "~")


def _reference_type(reference: str) -> str:
    name = _reference_schema_name(reference)
    return f"OpenApiComponents[\"schemas\"][{_quoted(name)}]"


def _referenced_schema_names(value: Any) -> set[str]:
    names: set[str] = set()
    if isinstance(value, Mapping):
        reference = value.get("$ref")
        if reference is not None:
            if not isinstance(reference, str):
                raise OpenApiTypeGenerationError("schema $ref must be a string")
            names.add(_reference_schema_name(reference))
        for nested in value.values():
            names.update(_referenced_schema_names(nested))
    elif isinstance(value, list):
        for nested in value:
            names.update(_referenced_schema_names(nested))
    return names


def _required_properties(
    schema: Mapping[str, Any],
    properties: Mapping[str, Any],
) -> set[str]:
    value = schema.get("required", [])
    if not isinstance(value, list) or not all(
        isinstance(item, str) for item in value
    ):
        raise OpenApiTypeGenerationError(
            "schema required must be an array of strings",
        )
    required = set(value)
    unknown = required.difference(properties)
    if unknown:
        raise OpenApiTypeGenerationError(
            "schema requires unknown properties: "
            + ", ".join(sorted(unknown)),
        )
    return required


def render_schema(schema: Mapping[str, Any] | None) -> str:
    """Render one OpenAPI 3.1 / JSON Schema node as a TypeScript type."""
    if schema is None:
        return "unknown"
    if not isinstance(schema, Mapping):
        raise OpenApiTypeGenerationError(
            f"schema must be an object, got {type(schema).__name__}",
        )

    reference = schema.get("$ref")
    if reference is not None:
        if not isinstance(reference, str):
            raise OpenApiTypeGenerationError("schema $ref must be a string")
        base = _reference_type(reference)
        siblings = {
            key: value
            for key, value in schema.items()
            if key not in {"$ref", "default", "description", "title"}
        }
        return _intersection((base, render_schema(siblings))) if siblings else base

    if "const" in schema:
        return _literal(schema["const"])

    enum_values = schema.get("enum")
    if enum_values is not None:
        if not isinstance(enum_values, list):
            raise OpenApiTypeGenerationError("schema enum must be an array")
        return _union(tuple(_literal(value) for value in enum_values))

    for union_key in ("anyOf", "oneOf"):
        alternatives = schema.get(union_key)
        if alternatives is not None:
            if not isinstance(alternatives, list):
                raise OpenApiTypeGenerationError(
                    f"schema {union_key} must be an array",
                )
            return _union(tuple(render_schema(item) for item in alternatives))

    all_of = schema.get("allOf")
    if all_of is not None:
        if not isinstance(all_of, list):
            raise OpenApiTypeGenerationError("schema allOf must be an array")
        return _intersection(tuple(render_schema(item) for item in all_of))

    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        return _union(
            tuple(render_schema({**schema, "type": item}) for item in schema_type),
        )

    prefix_items = schema.get("prefixItems")
    if prefix_items is not None:
        if not isinstance(prefix_items, list):
            raise OpenApiTypeGenerationError("schema prefixItems must be an array")
        return "[" + ", ".join(render_schema(item) for item in prefix_items) + "]"

    if schema_type == "array" or "items" in schema:
        return f"Array<{render_schema(schema.get('items'))}>"

    properties = schema.get("properties")
    is_object = (
        schema_type == "object"
        or properties is not None
        or "additionalProperties" in schema
    )
    if is_object:
        if properties is None:
            properties = {}
        if not isinstance(properties, Mapping):
            raise OpenApiTypeGenerationError("schema properties must be an object")
        required = _required_properties(schema, properties)

        lines = ["{"]
        for name in sorted(properties):
            property_schema = properties[name]
            if not isinstance(name, str):
                raise OpenApiTypeGenerationError("schema property names must be strings")
            suffix = "" if name in required else "?"
            rendered = render_schema(property_schema)
            lines.append(
                f"  {_quoted(name)}{suffix}: " + _indent(rendered, 2).lstrip() + ";",
            )
        lines.append("}")
        object_type = "\n".join(lines)

        additional = schema.get("additionalProperties", None)
        if additional is False:
            return object_type
        # OpenAPI object schemas do not need an index signature merely because
        # JSON Schema permits undeclared keys.  TypeScript remains structurally
        # assignable, while an index signature would erase known property types
        # under ``keyof``/``Omit``.  Emit one only when the document explicitly
        # declares an additional-properties transport shape.
        if additional is None:
            return object_type if properties else "{ [key: string]: unknown }"
        if additional is True:
            additional_type = "unknown"
        elif isinstance(additional, Mapping):
            additional_type = render_schema(additional)
        else:
            raise OpenApiTypeGenerationError(
                "schema additionalProperties must be a boolean or object",
            )
        index_type = "{ [key: string]: " + additional_type + " }"
        if properties:
            return _intersection((object_type, index_type))
        return index_type

    primitive = {
        "boolean": "boolean",
        "integer": "number",
        "null": "null",
        "number": "number",
        "string": "string",
    }.get(schema_type)
    if primitive is not None:
        return primitive
    if schema_type is None:
        return "unknown"
    raise OpenApiTypeGenerationError(
        f"unsupported JSON Schema type {schema_type!r}",
    )


def _render_named_properties(
    values: Sequence[tuple[str, str, bool]],
) -> str:
    lines = ["{"]
    for name, type_name, required in sorted(values):
        optional = "" if required else "?"
        lines.append(
            f"  {_quoted(name)}{optional}: " + _indent(type_name, 2).lstrip() + ";",
        )
    lines.append("}")
    return "\n".join(lines)


def _render_parameters(
    path_parameters: Sequence[Mapping[str, Any]],
    operation_parameters: Sequence[Mapping[str, Any]],
) -> str:
    by_location: dict[str, list[tuple[str, str, bool]]] = {}
    combined: dict[tuple[str, str], Mapping[str, Any]] = {}
    for parameter in (*path_parameters, *operation_parameters):
        name = parameter.get("name")
        location = parameter.get("in")
        if not isinstance(name, str) or not isinstance(location, str):
            raise OpenApiTypeGenerationError(
                "OpenAPI parameters require string name and in fields",
            )
        combined[(location, name)] = parameter
    for (location, name), parameter in sorted(combined.items()):
        parameter_schema = parameter.get("schema")
        by_location.setdefault(location, []).append(
            (
                name,
                render_schema(parameter_schema),
                bool(parameter.get("required", False)),
            ),
        )
    if not by_location:
        return "never"
    return _render_named_properties(
        tuple(
            (
                location,
                _render_named_properties(tuple(values)),
                True,
            )
            for location, values in by_location.items()
        ),
    )


def _render_content(content: Any) -> str:
    if content is None:
        return "never"
    if not isinstance(content, Mapping):
        raise OpenApiTypeGenerationError("OpenAPI content must be an object")
    values: list[tuple[str, str, bool]] = []
    for media_type, media in content.items():
        if not isinstance(media_type, str) or not isinstance(media, Mapping):
            raise OpenApiTypeGenerationError("OpenAPI media entries are malformed")
        values.append((media_type, render_schema(media.get("schema")), True))
    return _render_named_properties(tuple(values))


def _render_operation(
    operation: Mapping[str, Any],
    path_parameters: Sequence[Mapping[str, Any]],
) -> str:
    operation_parameters = operation.get("parameters", [])
    if not isinstance(operation_parameters, list):
        raise OpenApiTypeGenerationError("operation parameters must be an array")
    request_body = operation.get("requestBody")
    request_type = "never"
    request_required = False
    if request_body is not None:
        if not isinstance(request_body, Mapping):
            raise OpenApiTypeGenerationError("operation requestBody must be an object")
        request_type = _render_content(request_body.get("content"))
        request_required = bool(request_body.get("required", False))

    responses = operation.get("responses")
    if not isinstance(responses, Mapping) or not responses:
        raise OpenApiTypeGenerationError("operation responses must be a non-empty object")
    response_values: list[tuple[str, str, bool]] = []
    for status, response in responses.items():
        if not isinstance(status, str) or not isinstance(response, Mapping):
            raise OpenApiTypeGenerationError("OpenAPI response entries are malformed")
        response_values.append(
            (status, _render_content(response.get("content")), True),
        )

    parameters_type = _render_parameters(
        path_parameters,
        operation_parameters,
    )
    return _render_named_properties(
        (
            (
                "parameters",
                parameters_type,
                parameters_type != "never",
            ),
            ("requestBody", request_type, request_required),
            ("responses", _render_named_properties(tuple(response_values)), True),
        ),
    )


def render_types(document: Mapping[str, Any]) -> str:
    """Render the tracked TypeScript transport contract."""
    components = document.get("components", {})
    if not isinstance(components, Mapping):
        raise OpenApiTypeGenerationError("OpenAPI components must be an object")
    schemas = components.get("schemas", {})
    if not isinstance(schemas, Mapping) or not schemas:
        raise OpenApiTypeGenerationError(
            "OpenAPI components.schemas must be a non-empty object",
        )
    paths = document.get("paths")
    if not isinstance(paths, Mapping) or not paths:
        raise OpenApiTypeGenerationError("OpenAPI paths must be a non-empty object")
    missing_references = _referenced_schema_names(document).difference(schemas)
    if missing_references:
        raise OpenApiTypeGenerationError(
            "OpenAPI references missing component schemas: "
            + ", ".join(sorted(missing_references)),
        )

    digest = openapi_sha256(document)
    lines = [
        "/**",
        " * Generated from the production FastAPI OpenAPI document.",
        " * Do not edit by hand. Run:",
        " *   uv run --no-sync python scripts/generate_openapi_types.py",
        f" * OpenAPI SHA-256: {digest}",
        " */",
        "",
        "export interface OpenApiComponents {",
        "  \"schemas\": {",
    ]
    for name in sorted(schemas):
        if not isinstance(name, str):
            raise OpenApiTypeGenerationError("component schema names must be strings")
        rendered = render_schema(schemas[name])
        lines.append(
            f"    {_quoted(name)}: " + _indent(rendered, 4).lstrip() + ";",
        )
    lines.extend(
        (
            "  };",
            "}",
            "",
            "export type OpenApiSchema<",
            "  Name extends keyof OpenApiComponents[\"schemas\"],",
            "> = OpenApiComponents[\"schemas\"][Name]",
            "",
            "/** Response view after FastAPI serializes declared defaults. */",
            "export type OpenApiMaterializedSchema<",
            "  Name extends keyof OpenApiComponents[\"schemas\"],",
            "> = Required<OpenApiSchema<Name>>",
            "",
            "export interface OpenApiPaths {",
        ),
    )

    for path in sorted(paths):
        path_item = paths[path]
        if not isinstance(path, str) or not isinstance(path_item, Mapping):
            raise OpenApiTypeGenerationError("OpenAPI path entries are malformed")
        raw_path_parameters = path_item.get("parameters", [])
        if not isinstance(raw_path_parameters, list):
            raise OpenApiTypeGenerationError("path parameters must be an array")
        methods = [method for method in _HTTP_METHODS if method in path_item]
        method_values: list[tuple[str, str, bool]] = []
        for method in methods:
            operation = path_item[method]
            if not isinstance(operation, Mapping):
                raise OpenApiTypeGenerationError("OpenAPI operation must be an object")
            method_values.append(
                (
                    method,
                    _render_operation(operation, raw_path_parameters),
                    True,
                ),
            )
        lines.append(
            f"  {_quoted(path)}: "
            + _indent(_render_named_properties(tuple(method_values)), 2).lstrip()
            + ";",
        )
    lines.extend(("}", ""))

    for name in sorted(schemas):
        if _IDENTIFIER.fullmatch(name):
            lines.append(
                f"export type {name} = OpenApiComponents[\"schemas\"][{_quoted(name)}]",
            )
    lines.append("")
    return "\n".join(lines)


def check_generated_types(expected: str, output: Path) -> tuple[bool, str]:
    """Compare generated content without mutating the tracked contract."""
    if not output.is_file():
        return False, f"generated OpenAPI transport types are missing: {output}"
    actual = output.read_text(encoding="utf-8")
    if actual != expected:
        return (
            False,
            "generated OpenAPI transport types are stale: "
            f"{output}; run scripts/generate_openapi_types.py",
        )
    return True, f"OpenAPI transport types are current: {output}"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when the tracked TypeScript output differs; do not write",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="generated TypeScript destination",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    output = args.output.resolve()
    expected = render_types(load_application_openapi())
    if args.check:
        current, message = check_generated_types(expected, output)
        stream = sys.stdout if current else sys.stderr
        print(message, file=stream)
        return 0 if current else 1
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(expected, encoding="utf-8")
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
