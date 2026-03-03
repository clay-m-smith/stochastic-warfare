"""Shared pytest fixtures for the stochastic-warfare test suite.

Provides commonly-needed test primitives: RNG generators, EventBus,
SimulationClock, timestamp constants, and Position helpers.

Existing test files define their own local helpers (``_rng()``, ``_TS``,
``_make_engine()``).  These fixtures are designed for use by **new** test
files — they do not replace existing helpers.

Usage in a test file::

    def test_something(rng, event_bus, sim_clock):
        engine = SomeEngine(event_bus, rng)
        ...
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId, Position

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


@pytest.fixture
def sim_clock() -> SimulationClock:
    """SimulationClock starting at the reference timestamp, 10s ticks."""
    return SimulationClock(
        start=TS,
        tick_duration=timedelta(seconds=10),
    )


@pytest.fixture
def rng_manager() -> RNGManager:
    """RNGManager seeded at 42."""
    return RNGManager(DEFAULT_SEED)


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


def make_stream(
    module: ModuleId,
    seed: int = DEFAULT_SEED,
) -> np.random.Generator:
    """Create an RNG stream for a specific module via RNGManager.

    Matches the pattern used by logistics/C2 tests::

        rng = RNGManager(seed).get_stream(ModuleId.LOGISTICS)
    """
    return RNGManager(seed).get_stream(module)
