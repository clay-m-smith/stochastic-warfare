"""Central RNG manager — single source of all simulation randomness.

Deterministic replay depends on every stochastic call using the correct
manager-owned authority. Conventional subsystem streams derive from one master
seed via ``numpy.random.SeedSequence.spawn``; identity-addressed FOW decisions
derive from the same seed without making their values depend on dispatch order.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Sequence

import numpy as np

from stochastic_warfare.core.indexed_rng import (
    FOWIndexedAllocation,
    FOWIndexedCommitPlan,
    FOWIndexedIntervalRecord,
    IndexedFOWRNG,
    IndexedRNGLifecycleError,
    IndexedRNGValidationError,
    _strict_master_seed,
)
from stochastic_warfare.core.types import ModuleId


class RNGManager:
    """Own conventional module streams and indexed FOW decision authority.

    Parameters
    ----------
    master_seed:
        The seed that determines the entire simulation's random trajectory.
    """

    def __init__(self, master_seed: int) -> None:
        self._master_seed = _strict_master_seed(master_seed)
        self._streams: dict[ModuleId, np.random.Generator] = {}
        self._indexed_fow = IndexedFOWRNG(self._master_seed)
        self._latest_indexed_fow_interval_record: FOWIndexedIntervalRecord | None = None
        self._initialize(self._master_seed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_stream(self, module: ModuleId) -> np.random.Generator:
        """Return the PRNG stream for *module*.

        Raises ``KeyError`` if *module* is not a valid ``ModuleId``.
        """
        return self._streams[module]

    @property
    def indexed_fow_complete_from_tick_zero(self) -> bool:
        """Whether the persisted indexed transcript covers tick zero onward."""
        return self._indexed_fow.complete_from_tick_zero

    @property
    def indexed_fow_committed_interval_count(self) -> int:
        """Return the number of successfully committed FOW allocations."""
        return self._indexed_fow.committed_interval_count

    @property
    def indexed_fow_committed_entry_count(self) -> int:
        """Return the number of decisions in the committed transcript."""
        return self._indexed_fow.committed_entry_count

    @property
    def indexed_fow_transcript_digest_hex(self) -> str:
        """Return the exact current rolling-transcript digest."""
        return self._indexed_fow.transcript_digest_hex

    @property
    def latest_fow_detection_interval_record(
        self,
    ) -> FOWIndexedIntervalRecord | None:
        """Return the latest public raw interval observation, if any."""
        return self._latest_indexed_fow_interval_record

    def begin_fow_detection_interval(
        self,
        engine_tick: int,
        reporting_sides: Sequence[str],
        *,
        module: ModuleId = ModuleId.DETECTION,
    ) -> FOWIndexedAllocation:
        """Allocate one manager/module/tick/ordered-side FOW transaction."""
        allocation = self._indexed_fow.begin_interval(
            module=module,
            engine_tick=engine_tick,
            reporting_sides=reporting_sides,
        )
        return allocation

    def prepare_fow_detection_interval_commit(
        self,
        allocation: FOWIndexedAllocation,
    ) -> FOWIndexedCommitPlan:
        """Prepare one indexed transcript record without publishing it."""
        return self._indexed_fow.prepare_interval_commit(allocation)

    def validate_prepared_fow_detection_interval_commit(
        self,
        plan: FOWIndexedCommitPlan,
    ) -> None:
        """Validate a prepared indexed record for an outer transaction."""
        self._indexed_fow.validate_prepared_interval_commit(plan)

    def _commit_prevalidated_fow_detection_interval(
        self,
        plan: FOWIndexedCommitPlan,
    ) -> FOWIndexedIntervalRecord:
        """Publish a prevalidated record and its public latest observation."""
        record = self._indexed_fow._commit_prevalidated_interval(plan)
        self._latest_indexed_fow_interval_record = record
        return record

    def commit_prepared_fow_detection_interval(
        self,
        plan: FOWIndexedCommitPlan,
    ) -> FOWIndexedIntervalRecord:
        """Validate and publish a prepared indexed FOW interval."""
        self.validate_prepared_fow_detection_interval_commit(plan)
        return self._commit_prevalidated_fow_detection_interval(plan)

    def commit_fow_detection_interval(
        self,
        allocation: FOWIndexedAllocation,
    ) -> FOWIndexedIntervalRecord:
        """Commit a complete indexed FOW interval owned by this manager."""
        return self.commit_prepared_fow_detection_interval(self.prepare_fow_detection_interval_commit(allocation))

    def abort_fow_detection_interval(
        self,
        allocation: FOWIndexedAllocation,
    ) -> None:
        """Poison and abort an incomplete indexed FOW interval."""
        self._indexed_fow.abort_interval(allocation)

    def mark_indexed_fow_history_incomplete(self) -> None:
        """Permanently mark a legacy-derived indexed transcript incomplete."""
        self._indexed_fow.mark_history_incomplete()

    def get_state(self) -> dict[str, object]:
        """Capture the full PRNG state of every stream (for checkpointing)."""
        return {
            "master_seed": self._master_seed,
            "streams": {mod.value: deepcopy(gen.bit_generator.state) for mod, gen in self._streams.items()},
            "indexed_fow": self._indexed_fow.get_state(),
        }

    def set_state(self, state: dict[str, object]) -> None:
        """Strictly validate and atomically restore every RNG authority."""
        if self._indexed_fow._active is not None:
            raise IndexedRNGLifecycleError("cannot restore RNGManager during an active indexed allocation")
        if type(state) is not dict or set(state) != {
            "master_seed",
            "streams",
            "indexed_fow",
        }:
            raise IndexedRNGValidationError("RNGManager state has invalid key topology")
        master_seed = _strict_master_seed(state["master_seed"])
        stream_states = state["streams"]
        if type(stream_states) is not dict or set(stream_states) != {module.value for module in ModuleId}:
            raise IndexedRNGValidationError("RNGManager stream state has invalid module topology")

        candidate_streams = self._new_streams(master_seed)
        try:
            for module in ModuleId:
                candidate_streams[module].bit_generator.state = deepcopy(stream_states[module.value])
        except (KeyError, TypeError, ValueError) as exc:
            raise IndexedRNGValidationError("RNGManager contains an invalid conventional stream state") from exc
        candidate_indexed = IndexedFOWRNG.from_state(
            master_seed,
            state["indexed_fow"],
        )
        if not self._indexed_fow.complete_from_tick_zero and candidate_indexed.complete_from_tick_zero:
            raise IndexedRNGValidationError(
                "indexed FOW completeness cannot be promoted after a legacy restore",
            )

        prior_states = {module: deepcopy(generator.bit_generator.state) for module, generator in self._streams.items()}
        try:
            for module in ModuleId:
                self._streams[module].bit_generator.state = deepcopy(candidate_streams[module].bit_generator.state)
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
            for module, prior_state in prior_states.items():
                self._streams[module].bit_generator.state = prior_state
            raise IndexedRNGValidationError("RNGManager restore could not commit validated stream state") from exc
        self._master_seed = master_seed
        self._indexed_fow = candidate_indexed
        self._latest_indexed_fow_interval_record = None

    def reset(self, master_seed: int) -> None:
        """Re-initialize every stream from a new master seed."""
        if self._indexed_fow._active is not None:
            raise IndexedRNGLifecycleError(
                "cannot reset RNGManager during an active or prepared indexed allocation",
            )
        seed = _strict_master_seed(master_seed)
        candidates = self._new_streams(seed)
        for module in ModuleId:
            self._streams[module].bit_generator.state = deepcopy(candidates[module].bit_generator.state)
        self._master_seed = seed
        self._indexed_fow = IndexedFOWRNG(seed)
        self._latest_indexed_fow_interval_record = None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _initialize(self, master_seed: int) -> None:
        """Spawn one child ``SeedSequence`` per ``ModuleId``."""
        self._streams.update(self._new_streams(master_seed))

    @staticmethod
    def _new_streams(
        master_seed: int,
    ) -> dict[ModuleId, np.random.Generator]:
        """Build a complete conventional stream set without mutating state."""
        root = np.random.SeedSequence(master_seed)
        children = root.spawn(len(ModuleId))
        streams: dict[ModuleId, np.random.Generator] = {}
        for module, child_seq in zip(ModuleId, children, strict=True):
            streams[module] = np.random.Generator(np.random.PCG64(child_seq))
        return streams
