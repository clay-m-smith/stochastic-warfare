"""Phase 25d — CommanderEngine wiring tests.

Tests side-level and per-unit commander profile assignment, plus
commander OODA speed multiplier integration in the battle loop.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock

import numpy as np

from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.entities.base import Unit
from stochastic_warfare.simulation.scenario import (
    CampaignScenarioConfig,
    SimulationContext,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

_MINIMAL_SIDES = [
    {"side": "blue", "units": [{"unit_type": "infantry_platoon", "count": 1}]},
    {"side": "red", "units": [{"unit_type": "infantry_platoon", "count": 1}]},
]


def _minimal_config(**overrides: Any) -> CampaignScenarioConfig:
    base = {
        "name": "test",
        "date": "2024-06-15",
        "duration_hours": 1.0,
        "terrain": {"width_m": 1000, "height_m": 1000, "cell_size_m": 100},
        "sides": _MINIMAL_SIDES,
    }
    base.update(overrides)
    return CampaignScenarioConfig.model_validate(base)


def _make_unit(entity_id: str, side: str = "blue") -> Unit:
    return Unit(
        entity_id=entity_id,
        unit_type="infantry_platoon",
        side=side,
        position=Position(100.0, 100.0, 0.0),
        speed=5.0,
    )


def _make_ctx(**overrides: Any) -> SimulationContext:
    config = overrides.pop("config", _minimal_config())
    return SimulationContext(
        config=config,
        clock=SimulationClock(start=TS, tick_duration=timedelta(seconds=10)),
        rng_manager=RNGManager(42),
        event_bus=EventBus(),
        **overrides,
    )


# =========================================================================
# 1. Context field
# =========================================================================


class TestContextField:
    """Commander engine field on SimulationContext defaults to None."""

    def test_commander_engine_default_none(self) -> None:
        ctx = _make_ctx()
        assert ctx.commander_engine is None

    def test_commander_engine_settable(self) -> None:
        mock_engine = MagicMock()
        ctx = _make_ctx(commander_engine=mock_engine)
        assert ctx.commander_engine is mock_engine

    def test_commander_engine_in_get_state(self) -> None:
        mock_engine = MagicMock()
        mock_engine.get_state.return_value = {"profiles": {}}
        ctx = _make_ctx(commander_engine=mock_engine)
        state = ctx.get_state()
        assert "commander_engine" in state

    def test_commander_engine_not_in_state_when_none(self) -> None:
        ctx = _make_ctx()
        state = ctx.get_state()
        assert "commander_engine" not in state


# =========================================================================
# 2. ScenarioLoader creates commander engine
# =========================================================================


class TestScenarioLoaderCommander:
    """ScenarioLoader creates CommanderEngine from commander_config."""

    def test_commander_engine_created(self) -> None:
        from pathlib import Path
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = Path("data")
        c2_rng = RNGManager(42).get_stream(ModuleId.C2)
        result = loader._create_commander_engine(c2_rng, {})
        assert result["commander_engine"] is not None

    def test_commander_engine_has_profiles(self) -> None:
        from pathlib import Path
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = Path("data")
        c2_rng = RNGManager(42).get_stream(ModuleId.C2)
        result = loader._create_commander_engine(c2_rng, {})
        engine = result["commander_engine"]
        profiles = engine._loader.available_profiles()
        assert "balanced_default" in profiles
        assert "aggressive_armor" in profiles

    def test_commander_null_config_no_engine(self) -> None:
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = None
        cfg = _minimal_config(commander_config=None)
        c2_rng = RNGManager(42).get_stream(ModuleId.C2)
        result = loader._create_optional_engines(
            RNGManager(42), EventBus(), cfg, c2_rng,
        )
        assert result.get("commander_engine") is None

    def test_commander_with_custom_config(self) -> None:
        from pathlib import Path
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = Path("data")
        c2_rng = RNGManager(42).get_stream(ModuleId.C2)
        result = loader._create_commander_engine(c2_rng, {
            "ooda_speed_base_mult": 2.0,
        })
        assert result["commander_engine"]._config.ooda_speed_base_mult == 2.0

    def test_commander_side_defaults_stripped_from_config(self) -> None:
        from pathlib import Path
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = Path("data")
        c2_rng = RNGManager(42).get_stream(ModuleId.C2)
        # side_defaults should not go into CommanderConfig
        result = loader._create_commander_engine(c2_rng, {
            "side_defaults": {"blue": "balanced_default"},
            "assignments": {"unit_1": "aggressive_armor"},
        })
        assert result["commander_engine"] is not None

    def test_commander_assignments_stripped(self) -> None:
        from pathlib import Path
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = Path("data")
        c2_rng = RNGManager(42).get_stream(ModuleId.C2)
        result = loader._create_commander_engine(c2_rng, {
            "assignments": {"unit_1": "aggressive_armor"},
        })
        assert result["commander_engine"] is not None


# =========================================================================
# 3. Side-level and per-unit assignments
# =========================================================================


class TestCommanderAssignments:
    """_apply_commander_assignments wires profiles to units."""

    def test_side_default_assigns_all_units(self) -> None:
        from pathlib import Path
        from stochastic_warfare.c2.ai.commander import CommanderEngine, CommanderProfileLoader
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = CommanderProfileLoader(Path("data/commander_profiles"))
        loader.load_all()
        engine = CommanderEngine(loader, np.random.default_rng(42))

        u1 = _make_unit("u1", "blue")
        u2 = _make_unit("u2", "blue")
        u3 = _make_unit("u3", "red")

        cfg = _minimal_config(commander_config={
            "side_defaults": {"blue": "balanced_default"},
        })
        ctx = _make_ctx(
            config=cfg,
            commander_engine=engine,
            units_by_side={"blue": [u1, u2], "red": [u3]},
        )

        sl = ScenarioLoader.__new__(ScenarioLoader)
        sl._apply_commander_assignments(ctx, cfg)

        assert engine.get_personality("u1") is not None
        assert engine.get_personality("u2") is not None
        assert engine.get_personality("u3") is None  # red not assigned

    def test_per_unit_override(self) -> None:
        from pathlib import Path
        from stochastic_warfare.c2.ai.commander import CommanderEngine, CommanderProfileLoader
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = CommanderProfileLoader(Path("data/commander_profiles"))
        loader.load_all()
        engine = CommanderEngine(loader, np.random.default_rng(42))

        u1 = _make_unit("u1", "blue")
        cfg = _minimal_config(commander_config={
            "side_defaults": {"blue": "balanced_default"},
            "assignments": {"u1": "aggressive_armor"},
        })
        ctx = _make_ctx(
            config=cfg,
            commander_engine=engine,
            units_by_side={"blue": [u1], "red": []},
        )

        sl = ScenarioLoader.__new__(ScenarioLoader)
        sl._apply_commander_assignments(ctx, cfg)

        # Per-unit override takes precedence
        personality = engine.get_personality("u1")
        assert personality is not None
        assert personality.profile_id == "aggressive_armor"

    def test_no_commander_engine_is_noop(self) -> None:
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        cfg = _minimal_config(commander_config={"side_defaults": {"blue": "balanced_default"}})
        ctx = _make_ctx(config=cfg, commander_engine=None)

        sl = ScenarioLoader.__new__(ScenarioLoader)
        sl._apply_commander_assignments(ctx, cfg)  # Should not raise

    def test_invalid_profile_logged_not_raised(self) -> None:
        from pathlib import Path
        from stochastic_warfare.c2.ai.commander import CommanderEngine, CommanderProfileLoader
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = CommanderProfileLoader(Path("data/commander_profiles"))
        loader.load_all()
        engine = CommanderEngine(loader, np.random.default_rng(42))

        u1 = _make_unit("u1", "blue")
        cfg = _minimal_config(commander_config={
            "side_defaults": {"blue": "nonexistent_profile"},
        })
        ctx = _make_ctx(
            config=cfg,
            commander_engine=engine,
            units_by_side={"blue": [u1], "red": []},
        )

        sl = ScenarioLoader.__new__(ScenarioLoader)
        sl._apply_commander_assignments(ctx, cfg)  # Should not raise


# =========================================================================
# 4. OODA speed multiplier in battle loop
# =========================================================================


class TestOODASpeedMultiplier:
    """Commander OODA speed multiplier applied in battle loop."""

    def _make_battle_manager(self) -> Any:
        from stochastic_warfare.simulation.battle import BattleManager
        return BattleManager(EventBus())

    def test_commander_ooda_mult_applied(self) -> None:
        from stochastic_warfare.c2.ai.ooda import OODAPhase

        bm = self._make_battle_manager()

        mock_ooda = MagicMock()
        mock_ooda.tactical_acceleration = 1.0
        mock_ooda.advance_phase.return_value = OODAPhase.ORIENT
        mock_ooda.start_phase = MagicMock()

        mock_commander = MagicMock()
        mock_commander.get_ooda_speed_multiplier.return_value = 0.8

        ctx = _make_ctx(
            ooda_engine=mock_ooda,
            commander_engine=mock_commander,
            school_registry=None,
            assessor=None,
            decision_engine=None,
            units_by_side={"blue": [_make_unit("u1")], "red": []},
        )

        completions = [("u1", OODAPhase.ACT)]
        bm._process_ooda_completions(ctx, completions, TS)

        # start_phase should be called with effective_mult including commander
        call_args = mock_ooda.start_phase.call_args
        assert call_args is not None
        effective_mult = call_args[1].get("tactical_mult", call_args[0][2] if len(call_args[0]) > 2 else None)
        assert effective_mult is not None
        assert abs(effective_mult - 0.8) < 0.01

    def test_no_commander_mult_is_1(self) -> None:
        from stochastic_warfare.c2.ai.ooda import OODAPhase

        bm = self._make_battle_manager()

        mock_ooda = MagicMock()
        mock_ooda.tactical_acceleration = 1.0
        mock_ooda.advance_phase.return_value = OODAPhase.ORIENT
        mock_ooda.start_phase = MagicMock()

        ctx = _make_ctx(
            ooda_engine=mock_ooda,
            commander_engine=None,
            school_registry=None,
            assessor=None,
            decision_engine=None,
            units_by_side={"blue": [_make_unit("u1")], "red": []},
        )

        completions = [("u1", OODAPhase.ACT)]
        bm._process_ooda_completions(ctx, completions, TS)

        call_args = mock_ooda.start_phase.call_args
        assert call_args is not None
        effective_mult = call_args[1].get("tactical_mult", call_args[0][2] if len(call_args[0]) > 2 else None)
        assert abs(effective_mult - 1.0) < 0.01

    def test_commander_plus_school_mult(self) -> None:
        from stochastic_warfare.c2.ai.ooda import OODAPhase

        bm = self._make_battle_manager()

        mock_ooda = MagicMock()
        mock_ooda.tactical_acceleration = 1.0
        mock_ooda.advance_phase.return_value = OODAPhase.ORIENT
        mock_ooda.start_phase = MagicMock()

        mock_school = MagicMock()
        mock_school.get_ooda_multiplier.return_value = 0.9
        mock_school.get_assessment_weight_overrides.return_value = None

        mock_registry = MagicMock()
        mock_registry.get_for_unit.return_value = mock_school

        mock_commander = MagicMock()
        mock_commander.get_ooda_speed_multiplier.return_value = 0.8

        ctx = _make_ctx(
            ooda_engine=mock_ooda,
            commander_engine=mock_commander,
            school_registry=mock_registry,
            assessor=None,
            decision_engine=None,
            units_by_side={"blue": [_make_unit("u1")], "red": []},
        )

        completions = [("u1", OODAPhase.ACT)]
        bm._process_ooda_completions(ctx, completions, TS)

        call_args = mock_ooda.start_phase.call_args
        effective_mult = call_args[1].get("tactical_mult", call_args[0][2] if len(call_args[0]) > 2 else None)
        # Should be 1.0 * 0.9 (school) * 0.8 (commander) = 0.72
        assert abs(effective_mult - 0.72) < 0.01

    def test_commander_ooda_called_per_unit(self) -> None:
        from stochastic_warfare.c2.ai.ooda import OODAPhase

        bm = self._make_battle_manager()

        mock_ooda = MagicMock()
        mock_ooda.tactical_acceleration = 1.0
        mock_ooda.advance_phase.return_value = OODAPhase.ORIENT

        mock_commander = MagicMock()
        mock_commander.get_ooda_speed_multiplier.side_effect = [0.8, 1.2]

        ctx = _make_ctx(
            ooda_engine=mock_ooda,
            commander_engine=mock_commander,
            school_registry=None,
            assessor=None,
            decision_engine=None,
            units_by_side={"blue": [_make_unit("u1"), _make_unit("u2")], "red": []},
        )

        completions = [("u1", OODAPhase.ACT), ("u2", OODAPhase.ACT)]
        bm._process_ooda_completions(ctx, completions, TS)

        calls = mock_commander.get_ooda_speed_multiplier.call_args_list
        assert len(calls) == 2
        assert calls[0][0][0] == "u1"
        assert calls[1][0][0] == "u2"

    def test_commander_mult_on_observe_phase(self) -> None:
        """Commander mult is applied regardless of which phase completed."""
        from stochastic_warfare.c2.ai.ooda import OODAPhase

        bm = self._make_battle_manager()

        mock_ooda = MagicMock()
        mock_ooda.tactical_acceleration = 1.0
        mock_ooda.advance_phase.return_value = OODAPhase.ORIENT
        mock_ooda.start_phase = MagicMock()

        mock_commander = MagicMock()
        mock_commander.get_ooda_speed_multiplier.return_value = 0.5

        ctx = _make_ctx(
            ooda_engine=mock_ooda,
            commander_engine=mock_commander,
            school_registry=None,
            assessor=MagicMock(),
            decision_engine=None,
            units_by_side={"blue": [_make_unit("u1")], "red": []},
        )

        completions = [("u1", OODAPhase.OBSERVE)]
        bm._process_ooda_completions(ctx, completions, TS)

        call_args = mock_ooda.start_phase.call_args
        effective_mult = call_args[1].get("tactical_mult", call_args[0][2] if len(call_args[0]) > 2 else None)
        assert abs(effective_mult - 0.5) < 0.01


# =========================================================================
# 5. Backward compatibility
# =========================================================================


class TestBackwardCompat:
    """No commander_config → None everywhere."""

    def test_no_commander_config_no_engine(self) -> None:
        cfg = _minimal_config()
        assert cfg.commander_config is None

    def test_no_commander_on_context(self) -> None:
        ctx = _make_ctx()
        assert ctx.commander_engine is None

    def test_battle_loop_works_without_commander(self) -> None:
        from stochastic_warfare.c2.ai.ooda import OODAPhase
        from stochastic_warfare.simulation.battle import BattleManager

        bm = BattleManager(EventBus())
        mock_ooda = MagicMock()
        mock_ooda.tactical_acceleration = 1.0
        mock_ooda.advance_phase.return_value = OODAPhase.ORIENT

        ctx = _make_ctx(
            ooda_engine=mock_ooda,
            commander_engine=None,
            school_registry=None,
            assessor=None,
            decision_engine=None,
            units_by_side={"blue": [_make_unit("u1")], "red": []},
        )
        completions = [("u1", OODAPhase.ACT)]
        bm._process_ooda_completions(ctx, completions, TS)
        # Should not raise
