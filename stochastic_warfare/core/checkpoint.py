"""Checkpoint serialization for deterministic save/restore.

Modules register state-provider callables.  A checkpoint captures the
full state of the clock, RNG manager, and every registered module into a
single ``bytes`` blob serialized as JSON.  A custom encoder/decoder pair
handles numpy types (arrays, scalars) that appear in bit-generator state
dicts.  Legacy pickle checkpoints (version 1) are transparently loaded
via a fallback path.
"""

from __future__ import annotations

import json
import pickle  # legacy checkpoint fallback only
from pathlib import Path
from typing import Any, Callable

import numpy as np

from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId

logger = get_logger(__name__)

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


def _numpy_object_hook(dct: dict) -> Any:  # noqa: ANN401
    """Reconstruct numpy arrays from the ``__ndarray__`` marker."""
    if "__ndarray__" in dct and "__dtype__" in dct:
        return np.array(dct["__ndarray__"], dtype=np.dtype(dct["__dtype__"]))
    return dct


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
            "modules": {
                mod.value: provider()
                for mod, provider in self._providers.items()
            },
        }
        return json.dumps(payload, cls=NumpyEncoder).encode("utf-8")

    def restore_checkpoint(self, data: bytes) -> dict:
        """Deserialize checkpoint data and return the full state dict.

        Tries JSON first (version 2+).  Falls back to pickle for legacy
        version-1 checkpoints.

        The caller is responsible for calling ``clock.set_state``,
        ``rng.set_state``, and restoring individual module states.
        """
        try:
            return json.loads(data.decode("utf-8"), object_hook=_numpy_object_hook)
        except (UnicodeDecodeError, json.JSONDecodeError):
            logger.info("JSON decode failed; falling back to legacy pickle checkpoint")
            return pickle.loads(data)  # noqa: S301

    def save_to_file(self, path: Path, data: bytes) -> None:
        """Write checkpoint bytes to disk."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def load_from_file(self, path: Path) -> bytes:
        """Read checkpoint bytes from disk."""
        return path.read_bytes()
