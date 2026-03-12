"""Tests for core/checkpoint.py — state serialization."""

import json
import pickle  # legacy checkpoint tests only
from datetime import datetime, timedelta, timezone

import numpy as np

from stochastic_warfare.core.checkpoint import (
    CheckpointManager,
    NumpyEncoder,
    _numpy_object_hook,
)
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

        assert restored["version"] == 2
        assert restored["format"] == "json"
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
        assert state["version"] == 2
        assert state["rng"]["master_seed"] == 42


class TestJsonRoundTrip:
    """Verify JSON serialization handles numpy types and round-trips correctly."""

    def test_json_format_used(self) -> None:
        """Checkpoint bytes are valid UTF-8 JSON, not pickle."""
        clock = _make_clock()
        rng = RNGManager(42)
        mgr = CheckpointManager()

        data = mgr.create_checkpoint(clock, rng)
        # Should be valid JSON
        parsed = json.loads(data.decode("utf-8"))
        assert parsed["format"] == "json"
        assert parsed["version"] == 2

    def test_numpy_array_round_trip(self) -> None:
        """ndarray survives JSON encode/decode via NumpyEncoder + object_hook."""
        arr = np.array([1.0, 2.0, 3.0], dtype=np.float64)
        encoded = json.dumps({"data": arr}, cls=NumpyEncoder)
        decoded = json.loads(encoded, object_hook=_numpy_object_hook)
        np.testing.assert_array_equal(decoded["data"], arr)
        assert decoded["data"].dtype == arr.dtype

    def test_numpy_integer_encoded(self) -> None:
        val = np.int64(42)
        encoded = json.dumps({"v": val}, cls=NumpyEncoder)
        assert json.loads(encoded)["v"] == 42

    def test_numpy_floating_encoded(self) -> None:
        val = np.float32(3.14)
        encoded = json.dumps({"v": val}, cls=NumpyEncoder)
        assert abs(json.loads(encoded)["v"] - 3.14) < 0.01

    def test_numpy_bool_encoded(self) -> None:
        val = np.bool_(True)
        encoded = json.dumps({"v": val}, cls=NumpyEncoder)
        assert json.loads(encoded)["v"] is True

    def test_module_state_with_numpy(self) -> None:
        """Module state containing numpy arrays round-trips through checkpoint."""
        clock = _make_clock()
        rng = RNGManager(42)
        mgr = CheckpointManager()

        state_with_numpy = {
            "positions": np.array([[1.0, 2.0], [3.0, 4.0]]),
            "count": np.int64(5),
            "active": np.bool_(True),
        }
        mgr.register(ModuleId.ENTITIES, lambda: state_with_numpy)

        data = mgr.create_checkpoint(clock, rng)
        restored = mgr.restore_checkpoint(data)

        mod_state = restored["modules"]["entities"]
        np.testing.assert_array_equal(
            mod_state["positions"], state_with_numpy["positions"]
        )
        assert mod_state["count"] == 5
        assert mod_state["active"] is True

    def test_full_round_trip_with_prng_restore(self) -> None:
        """Full checkpoint→restore cycle preserves PRNG continuity via JSON."""
        clock = _make_clock()
        rng = RNGManager(99)
        mgr = CheckpointManager()

        # Advance PRNG to a non-trivial state
        rng.get_stream(ModuleId.COMBAT).random(200)

        data = mgr.create_checkpoint(clock, rng)

        # Generate values after checkpoint
        expected = rng.get_stream(ModuleId.COMBAT).random(10)

        # Restore from JSON checkpoint
        state = mgr.restore_checkpoint(data)
        rng.set_state(state["rng"])
        actual = rng.get_stream(ModuleId.COMBAT).random(10)

        np.testing.assert_array_equal(actual, expected)


class TestLegacyPickleFallback:
    """Verify that old pickle-format checkpoints still load."""

    def test_legacy_pickle_checkpoint_loads(self) -> None:
        """A version-1 pickle checkpoint is transparently deserialized."""
        # Build a legacy (pickle) checkpoint payload manually
        legacy_payload = {
            "version": 1,
            "clock": {"tick_count": 3, "tick_duration_seconds": 10.0},
            "rng": {"master_seed": 7},
            "modules": {},
        }
        legacy_data = pickle.dumps(legacy_payload)

        mgr = CheckpointManager()
        restored = mgr.restore_checkpoint(legacy_data)

        assert restored["version"] == 1
        assert restored["rng"]["master_seed"] == 7
        assert restored["clock"]["tick_count"] == 3

    def test_legacy_pickle_with_numpy(self) -> None:
        """Legacy pickle checkpoint containing numpy arrays still loads."""
        legacy_payload = {
            "version": 1,
            "clock": {"tick_count": 0},
            "rng": {"master_seed": 1},
            "modules": {
                "combat": {"values": np.array([10, 20, 30])},
            },
        }
        legacy_data = pickle.dumps(legacy_payload)

        mgr = CheckpointManager()
        restored = mgr.restore_checkpoint(legacy_data)

        np.testing.assert_array_equal(
            restored["modules"]["combat"]["values"], [10, 20, 30]
        )

    def test_legacy_file_round_trip(self, tmp_path) -> None:
        """Legacy pickle checkpoint saved to file loads correctly."""
        legacy_payload = {
            "version": 1,
            "clock": {"tick_count": 5},
            "rng": {"master_seed": 42},
            "modules": {},
        }
        legacy_data = pickle.dumps(legacy_payload)

        mgr = CheckpointManager()
        path = tmp_path / "legacy.bin"
        mgr.save_to_file(path, legacy_data)

        loaded = mgr.load_from_file(path)
        restored = mgr.restore_checkpoint(loaded)
        assert restored["version"] == 1
        assert restored["rng"]["master_seed"] == 42
