"""Central RNG manager — single source of all simulation randomness.

Deterministic replay depends on every stochastic call drawing from the
correct per-module stream, all derived from a single master seed via
``numpy.random.SeedSequence.spawn``.
"""

from __future__ import annotations

import numpy as np

from stochastic_warfare.core.types import ModuleId


class RNGManager:
    """Owns and distributes per-module PRNG streams.

    Parameters
    ----------
    master_seed:
        The seed that determines the entire simulation's random trajectory.
    """

    def __init__(self, master_seed: int) -> None:
        self._master_seed = master_seed
        self._streams: dict[ModuleId, np.random.Generator] = {}
        self._initialize(master_seed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_stream(self, module: ModuleId) -> np.random.Generator:
        """Return the PRNG stream for *module*.

        Raises ``KeyError`` if *module* is not a valid ``ModuleId``.
        """
        return self._streams[module]

    def get_state(self) -> dict:
        """Capture the full PRNG state of every stream (for checkpointing)."""
        return {
            "master_seed": self._master_seed,
            "streams": {
                mod.value: gen.bit_generator.state
                for mod, gen in self._streams.items()
            },
        }

    def set_state(self, state: dict) -> None:
        """Restore all streams from a state dict produced by :meth:`get_state`."""
        self._master_seed = state["master_seed"]
        for mod in ModuleId:
            bg_state = state["streams"][mod.value]
            self._streams[mod].bit_generator.state = bg_state

    def reset(self, master_seed: int) -> None:
        """Re-initialize every stream from a new master seed."""
        self._master_seed = master_seed
        self._streams.clear()
        self._initialize(master_seed)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _initialize(self, master_seed: int) -> None:
        """Spawn one child ``SeedSequence`` per ``ModuleId``."""
        root = np.random.SeedSequence(master_seed)
        children = root.spawn(len(ModuleId))
        for module, child_seq in zip(ModuleId, children, strict=True):
            self._streams[module] = np.random.Generator(
                np.random.PCG64(child_seq)
            )
