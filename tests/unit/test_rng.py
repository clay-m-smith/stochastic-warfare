"""Tests for core/rng.py — PRNG discipline and deterministic replay."""

import numpy as np

from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId


class TestRNGManagerBasics:
    def test_all_modules_have_streams(self) -> None:
        mgr = RNGManager(42)
        for mod in ModuleId:
            gen = mgr.get_stream(mod)
            assert isinstance(gen, np.random.Generator)

    def test_invalid_key_raises(self) -> None:
        mgr = RNGManager(42)
        try:
            mgr.get_stream("not_a_module")  # type: ignore[arg-type]
            assert False, "Should have raised KeyError"
        except KeyError:
            pass


class TestDeterminism:
    def test_same_seed_same_sequence(self) -> None:
        mgr1 = RNGManager(123)
        mgr2 = RNGManager(123)
        for mod in ModuleId:
            vals1 = mgr1.get_stream(mod).random(10)
            vals2 = mgr2.get_stream(mod).random(10)
            np.testing.assert_array_equal(vals1, vals2)

    def test_different_seeds_different_sequences(self) -> None:
        mgr1 = RNGManager(100)
        mgr2 = RNGManager(200)
        vals1 = mgr1.get_stream(ModuleId.COMBAT).random(10)
        vals2 = mgr2.get_stream(ModuleId.COMBAT).random(10)
        assert not np.array_equal(vals1, vals2)

    def test_different_modules_independent(self) -> None:
        mgr = RNGManager(42)
        vals_combat = mgr.get_stream(ModuleId.COMBAT).random(10)
        vals_movement = mgr.get_stream(ModuleId.MOVEMENT).random(10)
        assert not np.array_equal(vals_combat, vals_movement)


class TestStateCheckpoint:
    def test_save_restore_roundtrip(self) -> None:
        mgr = RNGManager(42)
        # Advance some streams
        mgr.get_stream(ModuleId.COMBAT).random(100)
        mgr.get_stream(ModuleId.MOVEMENT).random(50)

        # Capture state
        state = mgr.get_state()

        # Generate "expected" values
        expected = {
            mod: mgr.get_stream(mod).random(10) for mod in ModuleId
        }

        # Restore state
        mgr.set_state(state)

        # Should produce the same values again
        for mod in ModuleId:
            actual = mgr.get_stream(mod).random(10)
            np.testing.assert_array_equal(actual, expected[mod])

    def test_state_contains_master_seed(self) -> None:
        mgr = RNGManager(999)
        state = mgr.get_state()
        assert state["master_seed"] == 999

    def test_state_contains_all_modules(self) -> None:
        mgr = RNGManager(42)
        state = mgr.get_state()
        for mod in ModuleId:
            assert mod.value in state["streams"]


class TestReset:
    def test_reset_reproduces_initial(self) -> None:
        mgr = RNGManager(42)
        initial = mgr.get_stream(ModuleId.CORE).random(10)

        # Advance further
        mgr.get_stream(ModuleId.CORE).random(1000)

        # Reset to same seed
        mgr.reset(42)
        after_reset = mgr.get_stream(ModuleId.CORE).random(10)
        np.testing.assert_array_equal(initial, after_reset)

    def test_reset_new_seed(self) -> None:
        mgr = RNGManager(42)
        vals_old = mgr.get_stream(ModuleId.CORE).random(10)

        mgr.reset(99)
        vals_new = mgr.get_stream(ModuleId.CORE).random(10)
        assert not np.array_equal(vals_old, vals_new)
