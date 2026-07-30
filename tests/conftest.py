"""Shared pytest fixtures for the stochastic-warfare test suite.

Provides commonly-needed test primitives: RNG generators, EventBus,
SimulationClock, timestamp constants, and Position helpers.

Existing test files define their own local helpers (``_rng()``, ``_TS``,
``_make_engine()``).  These fixtures are designed for use by **new** test
files — they do not replace existing helpers.

Usage in a test file::

    def test_something(rng, event_bus):
        engine = SomeEngine(event_bus, rng)
        ...
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position

# ---------------------------------------------------------------------------
# Common constants (importable, not fixtures)
# ---------------------------------------------------------------------------

#: Frozen reference timestamp used across tests.
TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

#: Common position constants.
POS_ORIGIN = Position(0.0, 0.0, 0.0)
POS_1KM_EAST = Position(1000.0, 0.0, 0.0)
POS_5KM = Position(5000.0, 5000.0, 0.0)

#: Default seed for deterministic tests.
DEFAULT_SEED = 42

_EVIDENCE_ROOT = Path(__file__).parent / "validation" / "evidence_ledgers"
_CURRENT_EVIDENCE_LEDGERS = (
    _EVIDENCE_ROOT / "no_direct_oracles.json",
    _EVIDENCE_ROOT / "weak_oracles.json",
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Apply reviewed structural classifications to exact collected nodes."""
    structural_node_ids: set[str] = set()
    for ledger_path in _CURRENT_EVIDENCE_LEDGERS:
        if not ledger_path.is_file():
            continue
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        structural_node_ids.update(
            entry["node_id"]
            for entry in ledger["entries"]
            if entry["classification"] == "structural_only"
        )

    for item in items:
        if item.nodeid in structural_node_ids:
            item.add_marker(pytest.mark.structural)


# ---------------------------------------------------------------------------
# Fixtures — fresh instance per test
# ---------------------------------------------------------------------------


@pytest.fixture
def rng() -> np.random.Generator:
    """Deterministic numpy RNG seeded at 42."""
    return np.random.Generator(np.random.PCG64(DEFAULT_SEED))


@pytest.fixture
def event_bus() -> EventBus:
    """Fresh EventBus instance."""
    return EventBus()


# ---------------------------------------------------------------------------
# Parameterized fixtures
# ---------------------------------------------------------------------------


def make_rng(seed: int = DEFAULT_SEED) -> np.random.Generator:
    """Create a deterministic RNG with the given seed.

    Use this helper when a fixture isn't flexible enough (e.g., you
    need multiple RNGs with different seeds in one test).
    """
    return np.random.Generator(np.random.PCG64(seed))


def make_clock(
    start: datetime = TS,
    tick_s: float = 10.0,
    elapsed_s: float = 0.0,
) -> SimulationClock:
    """Create a SimulationClock, optionally pre-advanced."""
    clock = SimulationClock(
        start=start,
        tick_duration=timedelta(seconds=tick_s),
    )
    ticks = int(elapsed_s / tick_s)
    for _ in range(ticks):
        clock.advance()
    return clock

