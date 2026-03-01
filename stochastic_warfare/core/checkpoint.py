"""Checkpoint serialization for deterministic save/restore.

Modules register state-provider callables.  A checkpoint captures the
full state of the clock, RNG manager, and every registered module into a
single ``bytes`` blob (pickle for now — simplest format that handles
numpy bit-generator state dicts natively).
"""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Callable

from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId

_CHECKPOINT_VERSION = 1


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
            "clock": clock.get_state(),
            "rng": rng.get_state(),
            "modules": {
                mod.value: provider()
                for mod, provider in self._providers.items()
            },
        }
        return pickle.dumps(payload)

    def restore_checkpoint(self, data: bytes) -> dict:
        """Deserialize checkpoint data and return the full state dict.

        The caller is responsible for calling ``clock.set_state``,
        ``rng.set_state``, and restoring individual module states.
        """
        return pickle.loads(data)  # noqa: S301

    def save_to_file(self, path: Path, data: bytes) -> None:
        """Write checkpoint bytes to disk."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def load_from_file(self, path: Path) -> bytes:
        """Read checkpoint bytes from disk."""
        return path.read_bytes()
