"""Strict YAML loading helpers for production configuration and catalogs."""

from __future__ import annotations

from collections.abc import Hashable
from typing import Any, TextIO

import yaml


class DuplicateKeyError(ValueError):
    """Raised when a YAML mapping repeats a key."""


class _UniqueKeyLoader(yaml.SafeLoader):
    """Safe loader that rejects duplicate mapping keys before overwrite."""


def _construct_unique_mapping(
    loader: _UniqueKeyLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, Hashable):
            raise ValueError(
                f"Unhashable YAML mapping key at {key_node.start_mark}",
            )
        if key in mapping:
            raise DuplicateKeyError(
                f"Duplicate YAML mapping key {key!r} at "
                f"{key_node.start_mark}",
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def load_yaml_unique(stream: str | TextIO) -> Any:
    """Safely parse YAML and reject every duplicate mapping key."""
    return yaml.load(stream, Loader=_UniqueKeyLoader)
