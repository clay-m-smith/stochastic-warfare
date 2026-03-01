"""Phase 0 integration test — proves exit criteria.

1. Load a minimal scenario YAML
2. Create RNGManager from seed
3. Create SimulationClock from start time
4. Get a PRNG stream, generate values
5. Advance clock several ticks, verify calendar queries
6. Create checkpoint, advance more, restore checkpoint
7. Verify PRNG produces same values as before checkpoint
8. Verify clock is at checkpoint time
"""

from pathlib import Path

import numpy as np

from stochastic_warfare.core.checkpoint import CheckpointManager
from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.config import ScenarioConfig, load_config
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId

SCENARIO_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "data"
    / "scenarios"
    / "test_scenario"
    / "scenario.yaml"
)


def test_phase0_full_lifecycle() -> None:
    # 1. Load scenario config
    cfg = load_config(SCENARIO_PATH, ScenarioConfig)
    assert cfg.name == "Desert Storm Test"
    assert cfg.master_seed == 42

    # 2. Create RNG manager
    rng = RNGManager(cfg.master_seed)

    # 3. Create clock
    clock = SimulationClock(cfg.start_time, cfg.tick_duration)
    assert clock.year == 1991
    assert clock.month == 2

    # 4. Get a PRNG stream, generate some values
    combat_rng = rng.get_stream(ModuleId.COMBAT)
    initial_values = combat_rng.random(5)
    assert len(initial_values) == 5

    # 5. Advance clock, verify calendar queries
    for _ in range(10):
        clock.advance()
    assert clock.tick_count == 10
    assert clock.day_of_year == 55  # Feb 24
    assert clock.hour_utc > 4.0  # started at 04:00, advanced 100s

    # 6. Create checkpoint
    checkpoint_mgr = CheckpointManager()
    checkpoint_data = checkpoint_mgr.create_checkpoint(clock, rng)

    # Record expected values AFTER checkpoint
    expected_combat = rng.get_stream(ModuleId.COMBAT).random(20)
    expected_movement = rng.get_stream(ModuleId.MOVEMENT).random(20)
    checkpoint_time = clock.current_time
    checkpoint_tick = clock.tick_count

    # 7. Advance more (diverge from checkpoint)
    for _ in range(100):
        clock.advance()
    rng.get_stream(ModuleId.COMBAT).random(1000)
    rng.get_stream(ModuleId.MOVEMENT).random(1000)

    # Verify we've diverged
    assert clock.tick_count == 110

    # 8. Restore checkpoint
    state = checkpoint_mgr.restore_checkpoint(checkpoint_data)
    clock.set_state(state["clock"])
    rng.set_state(state["rng"])

    # Verify PRNG produces same values as before
    actual_combat = rng.get_stream(ModuleId.COMBAT).random(20)
    actual_movement = rng.get_stream(ModuleId.MOVEMENT).random(20)
    np.testing.assert_array_equal(actual_combat, expected_combat)
    np.testing.assert_array_equal(actual_movement, expected_movement)

    # Verify clock is at checkpoint time
    assert clock.current_time == checkpoint_time
    assert clock.tick_count == checkpoint_tick


def test_determinism_across_runs() -> None:
    """Two independent runs with the same seed must produce identical results."""
    cfg = load_config(SCENARIO_PATH, ScenarioConfig)

    results = []
    for _ in range(2):
        rng = RNGManager(cfg.master_seed)
        clock = SimulationClock(cfg.start_time, cfg.tick_duration)
        for _ in range(50):
            clock.advance()
        values = {
            mod: rng.get_stream(mod).random(100) for mod in ModuleId
        }
        results.append(values)

    for mod in ModuleId:
        np.testing.assert_array_equal(results[0][mod], results[1][mod])
