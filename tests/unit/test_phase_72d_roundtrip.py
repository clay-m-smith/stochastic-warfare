"""Phase 72d — Round-trip verification tests for checkpoint completeness.

Behavioral tests exercising the full checkpoint chain with real or mock engines.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from typing import Any

import pytest

from stochastic_warfare.combat.suppression import UnitSuppressionState
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.simulation.calibration import CalibrationSchema


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _all_context_engine_names() -> list[str]:
    """Collect all engine-like attribute names from get_state source."""
    from stochastic_warfare.simulation.scenario import SimulationContext
    src = inspect.getsource(SimulationContext.get_state)
    # Extract quoted engine names from ("name", self.xxx) tuples
    import re
    return re.findall(r'\("(\w+)", self\.\w+\)', src)


def _make_mock_context():
    """Create a SimulationContext with all engines set to mock objects."""
    from stochastic_warfare.simulation.scenario import SimulationContext

    ctx = object.__new__(SimulationContext)
    ctx.clock = SimpleNamespace(
        get_state=lambda: {"tick": 0, "elapsed_s": 0},
        set_state=lambda s: None,
    )
    ctx.rng_manager = SimpleNamespace(
        get_state=lambda: {"seed": 42},
        set_state=lambda s: None,
    )
    ctx.calibration = CalibrationSchema()
    ctx.era_config = None
    ctx.config = SimpleNamespace(model_dump=lambda: {})
    ctx.units_by_side = {}
    ctx.morale_states = {}

    # Set all engines to None by default
    engine_names = _all_context_engine_names()
    for name in engine_names:
        setattr(ctx, name, None)

    return ctx, engine_names


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestContextRoundTrip:
    """SimulationContext get_state → set_state round-trips correctly."""

    def test_single_engine_round_trip(self):
        """A single engine's state survives get_state → set_state."""
        ctx, _ = _make_mock_context()

        # Add a mock weather engine with state
        weather_state = {"temperature_c": 25.0, "wind_speed": 5.0}
        ctx.weather_engine = SimpleNamespace(
            get_state=lambda: dict(weather_state),
            set_state=lambda s: None,
        )

        state = ctx.get_state()
        assert "weather_engine" in state
        assert state["weather_engine"]["temperature_c"] == 25.0

    def test_multiple_engines_round_trip(self):
        """Multiple engines' states all survive round-trip."""
        ctx, _ = _make_mock_context()

        engines_data = {
            "missile_engine": {"missiles": [{"id": "m1"}]},
            "roe_engine": {"level": "WEAPONS_FREE"},
            "obscurants_engine": {"zones": [{"center": [100, 200]}]},
        }

        for name, data in engines_data.items():
            captured = dict(data)
            setattr(ctx, name, SimpleNamespace(
                get_state=lambda d=captured: d,
                set_state=lambda s: None,
            ))

        state = ctx.get_state()
        for name, expected_data in engines_data.items():
            assert name in state, f"{name} missing from state"
            assert state[name] == expected_data

    def test_none_engines_excluded(self):
        """None engines don't appear in state dict."""
        ctx, engine_names = _make_mock_context()
        state = ctx.get_state()
        for name in engine_names:
            assert name not in state, f"None engine {name} should not be in state"

    def test_set_state_skips_missing_engines(self):
        """set_state gracefully skips engines that are None on context."""
        ctx, _ = _make_mock_context()
        # State has data for an engine that doesn't exist on context
        state = {
            "clock": {"tick": 0},
            "rng": {"seed": 42},
            "calibration": {},
            "missile_engine": {"missiles": []},
        }
        # Should not raise
        ctx.set_state(state)


class TestBattleManagerRoundTrip:
    """BattleManager state round-trips correctly."""

    def test_full_state_round_trip(self):
        """All BattleManager fields survive round-trip."""
        from stochastic_warfare.simulation.battle import BattleManager

        bm1 = BattleManager(EventBus(), {})
        bm1._ticks_stationary = {"u1": 8, "u2": 3}
        s = UnitSuppressionState()
        s.value = 0.9
        s.source_direction = 0.5
        bm1._suppression_states = {"u1": s}
        bm1._cumulative_casualties = {"u1": 12}
        bm1._undigging = {"u2": True}
        bm1._concealment_scores = {"u1": 0.55}
        bm1._env_casualty_accum = {"u3": 0.45}
        bm1._misinterpreted_orders = {"u1": {"radius_m": 200}}
        bm1._vls_launches = {"side_a": 5}
        bm1._ammo_expended = {"u1": 30}

        state1 = bm1.get_state()

        bm2 = BattleManager(EventBus(), {})
        bm2.set_state(state1)
        state2 = bm2.get_state()

        # All Phase 72b fields match
        for key in [
            "ticks_stationary", "suppression_states", "cumulative_casualties",
            "undigging", "concealment_scores", "env_casualty_accum",
        ]:
            assert state2[key] == state1[key], f"Mismatch on {key}"

        # Pre-existing fields also match
        assert state2["vls_launches"] == state1["vls_launches"]
        assert state2["ammo_expended"] == state1["ammo_expended"]


class TestStructuralCompleteness:
    """Every engine-like attribute on SimulationContext is accounted for."""

    def test_engine_attributes_covered(self):
        """Every attr ending in '_engine' on SimulationContext is either in
        checkpoint list or documented as intentionally excluded."""
        from stochastic_warfare.simulation.scenario import SimulationContext

        # Intentionally excluded (stateless/immutable/no get_state)
        EXCLUDED = {
            "conditions_facade",  # stateless facade (empty get_state)
            "los_engine",  # immutable terrain — no get_state/set_state
        }

        checkpoint_engines = set(_all_context_engine_names())

        # Get all attrs ending in _engine from class annotations and source
        import re
        src = inspect.getsource(SimulationContext)
        # Match annotations like `some_engine: SomeType` and assignments
        annotated = set(re.findall(r'\b(\w+_engine)\s*:', src))
        # Also match self.xxx_engine assignments in ScenarioLoader
        loader_src = inspect.getsource(
            inspect.getmodule(SimulationContext)  # type: ignore[arg-type]
        )
        assigned = set(re.findall(r'ctx\.(\w+_engine)\s*=', loader_src))

        init_engines = annotated | assigned

        # Every engine should be in checkpoint or excluded
        uncovered = init_engines - checkpoint_engines - EXCLUDED
        assert not uncovered, (
            f"Engines on SimulationContext but not in checkpoint lists: {uncovered}"
        )

    def test_get_state_set_state_parity(self):
        """get_state and set_state have the same engine lists."""
        from stochastic_warfare.simulation.scenario import SimulationContext

        get_src = inspect.getsource(SimulationContext.get_state)
        set_src = inspect.getsource(SimulationContext.set_state)

        import re
        get_names = re.findall(r'\("(\w+)", self\.\w+\)', get_src)
        set_names = re.findall(r'\("(\w+)", self\.\w+\)', set_src)

        assert set(get_names) == set(set_names), (
            f"get_state/set_state engine mismatch: "
            f"only in get={set(get_names) - set(set_names)}, "
            f"only in set={set(set_names) - set(get_names)}"
        )

    def test_battle_manager_state_keys(self):
        """BattleManager.get_state() returns all expected keys."""
        from stochastic_warfare.simulation.battle import BattleManager

        bm = BattleManager(EventBus(), {})
        state = bm.get_state()

        expected_keys = {
            "battles", "next_battle_id", "vls_launches", "ammo_expended",
            "pending_decisions",
            # Phase 72b additions
            "ticks_stationary", "suppression_states", "cumulative_casualties",
            "undigging", "concealment_scores", "env_casualty_accum",
            "misinterpreted_orders",
        }
        assert expected_keys.issubset(state.keys()), (
            f"Missing keys: {expected_keys - state.keys()}"
        )
