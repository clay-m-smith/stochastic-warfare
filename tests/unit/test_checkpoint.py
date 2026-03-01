"""Tests for core/checkpoint.py — state serialization."""

from datetime import datetime, timedelta, timezone

import numpy as np

from stochastic_warfare.core.checkpoint import CheckpointManager
from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId


def _make_clock() -> SimulationClock:
    return SimulationClock(
        datetime(1991, 2, 24, 4, 0, 0, tzinfo=timezone.utc),
        timedelta(seconds=10),
    )


class TestCheckpointRoundTrip:
    def test_create_and_restore(self) -> None:
        clock = _make_clock()
        rng = RNGManager(42)
        mgr = CheckpointManager()

        # Advance state
        for _ in range(5):
            clock.advance()
        rng.get_stream(ModuleId.COMBAT).random(50)

        data = mgr.create_checkpoint(clock, rng)
        restored = mgr.restore_checkpoint(data)

        assert restored["version"] == 1
        assert restored["clock"]["tick_count"] == 5
        assert restored["rng"]["master_seed"] == 42

    def test_prng_state_preserved_exactly(self) -> None:
        clock = _make_clock()
        rng = RNGManager(42)
        mgr = CheckpointManager()

        # Advance PRNG
        rng.get_stream(ModuleId.COMBAT).random(100)

        # Checkpoint
        data = mgr.create_checkpoint(clock, rng)

        # Generate "expected" values after checkpoint
        expected = rng.get_stream(ModuleId.COMBAT).random(10)

        # Restore and compare
        state = mgr.restore_checkpoint(data)
        rng.set_state(state["rng"])
        actual = rng.get_stream(ModuleId.COMBAT).random(10)
        np.testing.assert_array_equal(actual, expected)

    def test_clock_state_preserved(self) -> None:
        clock = _make_clock()
        rng = RNGManager(42)
        mgr = CheckpointManager()

        for _ in range(10):
            clock.advance()

        data = mgr.create_checkpoint(clock, rng)
        state = mgr.restore_checkpoint(data)

        new_clock = _make_clock()
        new_clock.set_state(state["clock"])
        assert new_clock.current_time == clock.current_time
        assert new_clock.tick_count == 10

    def test_module_state_included(self) -> None:
        clock = _make_clock()
        rng = RNGManager(42)
        mgr = CheckpointManager()

        dummy_state = {"health": 100, "position": [1.0, 2.0]}
        mgr.register(ModuleId.ENTITIES, lambda: dummy_state)

        data = mgr.create_checkpoint(clock, rng)
        state = mgr.restore_checkpoint(data)
        assert state["modules"]["entities"] == dummy_state


class TestFileIO:
    def test_save_and_load(self, tmp_path) -> None:
        clock = _make_clock()
        rng = RNGManager(42)
        mgr = CheckpointManager()

        data = mgr.create_checkpoint(clock, rng)
        path = tmp_path / "checkpoint.bin"
        mgr.save_to_file(path, data)

        loaded = mgr.load_from_file(path)
        state = mgr.restore_checkpoint(loaded)
        assert state["version"] == 1
        assert state["rng"]["master_seed"] == 42
