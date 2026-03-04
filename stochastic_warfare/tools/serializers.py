"""JSON serialization helpers for simulation objects.

Handles numpy types, datetime, enums, Position NamedTuple, inf/nan,
and nested structures that ``json.dumps`` cannot serialize natively.
"""

from __future__ import annotations

import enum
import json
import math
from datetime import datetime
from typing import Any

import numpy as np

from stochastic_warfare.core.types import Position


def _serialize_value(obj: Any) -> Any:
    """Recursively convert a value to JSON-safe types."""
    if obj is None or isinstance(obj, (str, bool)):
        return obj
    # enum must be checked before int (IntEnum is a subclass of int)
    if isinstance(obj, enum.Enum):
        return obj.name
    if isinstance(obj, (int,)) and not isinstance(obj, (bool, np.bool_)):
        return obj
    # numpy scalar types
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        v = float(obj)
        if math.isnan(v):
            return None
        if math.isinf(v):
            return "Infinity" if v > 0 else "-Infinity"
        return v
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, float):
        if math.isnan(obj):
            return None
        if math.isinf(obj):
            return "Infinity" if obj > 0 else "-Infinity"
        return obj
    # numpy array
    if isinstance(obj, np.ndarray):
        return [_serialize_value(x) for x in obj.tolist()]
    # datetime
    if isinstance(obj, datetime):
        return obj.isoformat()
    # Position (NamedTuple)
    if isinstance(obj, Position):
        return {"easting": obj.easting, "northing": obj.northing, "altitude": obj.altitude}
    # dataclass
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _serialize_value(getattr(obj, k)) for k in obj.__dataclass_fields__}
    # pydantic BaseModel
    if hasattr(obj, "model_dump"):
        return _serialize_value(obj.model_dump())
    # dict
    if isinstance(obj, dict):
        return {str(k): _serialize_value(v) for k, v in obj.items()}
    # list / tuple
    if isinstance(obj, (list, tuple)):
        return [_serialize_value(item) for item in obj]
    # set / frozenset
    if isinstance(obj, (set, frozenset)):
        return [_serialize_value(item) for item in sorted(obj, key=str)]
    # fallback
    return str(obj)


def serialize(obj: Any) -> str:
    """Serialize a Python object to a JSON string.

    Handles numpy types, datetime, enums, Position, inf/nan, dataclasses,
    pydantic models, and arbitrarily nested dicts/lists.
    """
    return json.dumps(_serialize_value(obj), indent=2)


def serialize_to_dict(obj: Any) -> Any:
    """Convert a Python object to a JSON-safe dict/list/scalar."""
    return _serialize_value(obj)


def make_error(error_type: str, message: str) -> str:
    """Create a standardized error JSON response."""
    return serialize({"error": True, "error_type": error_type, "message": message})


def make_success(data: Any) -> str:
    """Create a standardized success JSON response."""
    return serialize(data)
