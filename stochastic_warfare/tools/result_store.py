"""In-memory LRU cache of simulation run results.

Stores run results (engine results, recorders, final state) so that
subsequent tool calls (e.g. ``query_state``, ``compare_results``) can
reference previous runs by ``run_id``.
"""

from __future__ import annotations

import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StoredResult:
    """A cached simulation result."""

    run_id: str
    scenario_name: str
    seed: int
    summary: dict[str, Any]
    recorder_events: list[Any] = field(default_factory=list)
    recorder_snapshots: list[Any] = field(default_factory=list)
    mc_result: Any = None  # MonteCarloResult when applicable


class ResultStore:
    """LRU cache for simulation run results.

    Parameters
    ----------
    max_size:
        Maximum number of results to keep. Oldest evicted first.
    """

    def __init__(self, max_size: int = 20) -> None:
        self._max_size = max_size
        self._results: OrderedDict[str, StoredResult] = OrderedDict()

    def store(self, result: StoredResult) -> str:
        """Store a result, returning its run_id. Evicts oldest if at capacity."""
        run_id = result.run_id
        if run_id in self._results:
            self._results.move_to_end(run_id)
        else:
            if len(self._results) >= self._max_size:
                self._results.popitem(last=False)
            self._results[run_id] = result
        return run_id

    def get(self, run_id: str) -> StoredResult | None:
        """Retrieve a result by run_id, or None if not found."""
        result = self._results.get(run_id)
        if result is not None:
            self._results.move_to_end(run_id)
        return result

    def latest(self) -> StoredResult | None:
        """Return the most recently stored result, or None if empty."""
        if not self._results:
            return None
        key = next(reversed(self._results))
        return self._results[key]

    def list_runs(self) -> list[dict[str, Any]]:
        """Return summaries of all cached runs (newest first)."""
        return [
            {
                "run_id": r.run_id,
                "scenario_name": r.scenario_name,
                "seed": r.seed,
            }
            for r in reversed(self._results.values())
        ]

    def clear(self) -> None:
        """Remove all cached results."""
        self._results.clear()

    def __len__(self) -> int:
        return len(self._results)

    @staticmethod
    def generate_id() -> str:
        """Generate a unique run ID."""
        return uuid.uuid4().hex[:12]
