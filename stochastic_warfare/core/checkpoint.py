"""Checkpoint serialization for deterministic save/restore.

Modules register state-provider callables.  A checkpoint captures the
full state of the clock, RNG manager, and every registered module into a
single ``bytes`` blob serialized as JSON.  A custom encoder/decoder pair
handles numpy types (arrays, scalars) that appear in bit-generator state
dicts.  Unsafe legacy pickle conversion is deliberately isolated under
``stochastic_warfare.legacy`` and is never part of runtime restore.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Callable

import numpy as np

from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId

_CHECKPOINT_VERSION = 2


class NumpyEncoder(json.JSONEncoder):
    """JSON encoder that serializes numpy types."""

    def default(self, obj: Any) -> Any:  # noqa: ANN401
        if isinstance(obj, np.ndarray):
            return {"__ndarray__": obj.tolist(), "__dtype__": str(obj.dtype)}
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, np.generic):
            return obj.item()
        return super().default(obj)


class _LegacyNonFinite:
    """Path-checked placeholder used only by versionless migration."""

    __slots__ = ("token",)

    def __init__(self, token: str) -> None:
        self.token = token


def _strict_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"non-finite JSON number is unsupported: {value}")
    return parsed


def _validate_numpy_checkpoint_values(
    value: Any,  # noqa: ANN401
    *,
    dtype: np.dtype,
) -> tuple[int, ...]:
    """Validate JSON leaves and rectangular shape before NumPy conversion."""
    if isinstance(value, list):
        child_shapes = tuple(
            _validate_numpy_checkpoint_values(item, dtype=dtype)
            for item in value
        )
        if child_shapes and any(shape != child_shapes[0] for shape in child_shapes[1:]):
            raise ValueError("Malformed or ragged NumPy checkpoint array")
        return (len(value), *(child_shapes[0] if child_shapes else ()))

    if dtype.kind == "b":
        if type(value) is not bool:
            raise ValueError(
                "Boolean NumPy checkpoint arrays require JSON boolean values",
            )
        return ()

    if dtype.kind in {"i", "u"}:
        if type(value) is not int:
            raise ValueError(
                "Integer NumPy checkpoint arrays require JSON integer values",
            )
        bounds = np.iinfo(dtype)
        if not int(bounds.min) <= value <= int(bounds.max):
            raise ValueError("NumPy checkpoint integer is outside dtype bounds")
        return ()

    if type(value) not in {int, float}:
        raise ValueError(
            "Floating NumPy checkpoint arrays require JSON numeric values",
        )
    if type(value) is float and not math.isfinite(value):
        raise ValueError("NumPy checkpoint arrays must contain only finite values")
    if abs(value) > float(np.finfo(dtype).max):
        raise ValueError("NumPy checkpoint float is outside dtype bounds")
    return ()


def _strict_numpy_object(pairs: list[tuple[str, Any]]) -> Any:  # noqa: ANN401
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key!r}")
        result[key] = value

    marker_keys = {"__ndarray__", "__dtype__"}
    present_markers = marker_keys.intersection(result)
    if not present_markers:
        return result
    if set(result) != marker_keys:
        raise ValueError(
            "NumPy checkpoint marker must contain exactly '__ndarray__' and '__dtype__'",
        )

    raw_dtype = result["__dtype__"]
    raw_values = result["__ndarray__"]
    if not isinstance(raw_dtype, str) or not raw_dtype:
        raise ValueError("NumPy checkpoint dtype must be a non-empty string")
    try:
        dtype = np.dtype(raw_dtype)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Unsupported NumPy checkpoint dtype: {raw_dtype!r}") from exc
    if (
        dtype.fields is not None
        or dtype.subdtype is not None
        or dtype.hasobject
        or dtype.kind not in {"b", "i", "u", "f"}
        or str(dtype) != raw_dtype
    ):
        raise ValueError(f"Unsupported NumPy checkpoint dtype: {raw_dtype!r}")
    _validate_numpy_checkpoint_values(raw_values, dtype=dtype)
    try:
        array = np.asarray(raw_values, dtype=dtype)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Malformed or ragged NumPy checkpoint array") from exc
    if array.dtype.kind == "f" and not bool(np.isfinite(array).all()):
        raise ValueError("NumPy checkpoint arrays must contain only finite values")
    return array


def _legacy_constant(token: str) -> _LegacyNonFinite:
    return _LegacyNonFinite(token)


def _replace_legacy_weapon_sentinels(
    value: Any,  # noqa: ANN401
    *,
    path: tuple[str | int, ...] = (),
) -> tuple[Any, int]:  # noqa: ANN401
    if isinstance(value, _LegacyNonFinite):
        valid_path = (
            len(path) == 5
            and path[0:2] == ("context", "unit_weapon_states")
            and isinstance(path[2], str)
            and isinstance(path[3], int)
            and path[4] == "last_fire_time_s"
            and value.token == "-Infinity"
        )
        if not valid_path:
            raise ValueError(
                "Legacy non-finite value is outside a weapon timestamp path",
            )
        return None, 1
    if isinstance(value, dict):
        replaced: dict[str, Any] = {}
        count = 0
        for key, item in value.items():
            new_item, item_count = _replace_legacy_weapon_sentinels(
                item,
                path=(*path, key),
            )
            replaced[key] = new_item
            count += item_count
        return replaced, count
    if isinstance(value, list):
        replaced_list: list[Any] = []
        count = 0
        for index, item in enumerate(value):
            new_item, item_count = _replace_legacy_weapon_sentinels(
                item,
                path=(*path, index),
            )
            replaced_list.append(new_item)
            count += item_count
        return replaced_list, count
    return value, 0


def decode_checkpoint_json(
    data: bytes,
    *,
    allow_versionless_weapon_sentinels: bool = False,
) -> dict[str, Any]:
    """Decode one strict, finite, duplicate-free JSON checkpoint.

    This boundary is deliberately JSON-only and never invokes pickle decoding.
    The optional non-finite migration accepts only negative
    infinity at exact legacy weapon timestamp paths and only when the engine
    checkpoint has no explicit ``checkpoint_version``.
    """
    if not isinstance(data, bytes):
        raise TypeError("Checkpoint payload must be bytes")
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError("Checkpoint must be valid UTF-8 JSON") from exc

    legacy_placeholder_seen = False

    def reject_constant(token: str) -> Any:  # noqa: ANN401
        nonlocal legacy_placeholder_seen
        if allow_versionless_weapon_sentinels:
            legacy_placeholder_seen = True
            return _legacy_constant(token)
        raise ValueError(f"non-finite JSON constant is unsupported: {token}")

    try:
        decoded = json.loads(
            text,
            object_pairs_hook=_strict_numpy_object,
            parse_constant=reject_constant,
            parse_float=_strict_float,
        )
    except json.JSONDecodeError as exc:
        raise ValueError("Checkpoint must be valid JSON") from exc
    if not isinstance(decoded, dict):
        raise ValueError("Checkpoint top level must be a JSON object")

    migrated_count = 0
    if legacy_placeholder_seen:
        decoded, migrated_count = _replace_legacy_weapon_sentinels(decoded)
    if migrated_count and "checkpoint_version" in decoded:
        raise ValueError(
            "Legacy weapon sentinels are permitted only in versionless checkpoints",
        )
    return decoded


class CheckpointManager:
    """Captures and restores simulation state."""

    def __init__(self) -> None:
        self._providers: dict[ModuleId, Callable[[], dict]] = {}

    def register(
        self,
        module: ModuleId,
        state_provider: Callable[[], dict],
    ) -> None:
        """Register a callable that returns the current state of *module*."""
        self._providers[module] = state_provider

    def create_checkpoint(
        self,
        clock: SimulationClock,
        rng: RNGManager,
    ) -> bytes:
        """Snapshot the entire simulation state to ``bytes``."""
        payload = {
            "version": _CHECKPOINT_VERSION,
            "format": "json",
            "clock": clock.get_state(),
            "rng": rng.get_state(),
            "modules": {mod.value: provider() for mod, provider in self._providers.items()},
        }
        return json.dumps(payload, cls=NumpyEncoder, allow_nan=False).encode("utf-8")

    def restore_checkpoint(self, data: bytes) -> dict:
        """Deserialize checkpoint data and return the full state dict.

        Runtime restore is JSON-only.  Binary pickle payloads are rejected
        before decoding; trusted, offline conversion lives in the explicit
        ``stochastic_warfare.legacy.checkpoint_pickle`` namespace.

        The caller is responsible for calling ``clock.set_state``,
        ``rng.set_state``, and restoring individual module states.
        """
        if data.startswith(b"\x80"):
            raise ValueError(
                "Legacy pickle checkpoints are not accepted by runtime restore; "
                "use the explicit trusted offline conversion tool",
            )
        return decode_checkpoint_json(data)

    def save_to_file(self, path: Path, data: bytes) -> None:
        """Write checkpoint bytes to disk."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def load_from_file(self, path: Path) -> bytes:
        """Read checkpoint bytes from disk."""
        return path.read_bytes()
