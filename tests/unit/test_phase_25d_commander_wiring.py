"""Phase 25d — CommanderEngine wiring tests.

Tests side-level and per-unit commander profile assignment, plus
commander OODA speed multiplier integration in the battle loop.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest

from stochastic_warfare.c2.ai.ooda import OODAConfig, OODALoopEngine, OODAPhase
from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.entities.base import Unit
from stochastic_warfare.entities.organization.echelons import EchelonLevel
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
            RNGManager(42),
            EventBus(),
            cfg,
            c2_rng,
        )
        assert result.get("commander_engine") is None

    def test_commander_with_custom_config(self) -> None:
        from pathlib import Path
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = Path("data")
        c2_rng = RNGManager(42).get_stream(ModuleId.C2)
        result = loader._create_commander_engine(
            c2_rng,
            {
                "ooda_speed_base_mult": 2.0,
            },
        )
        assert result["commander_engine"]._config.ooda_speed_base_mult == 2.0

    def test_commander_side_defaults_rejected_from_config(self) -> None:
        from pathlib import Path
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = Path("data")
        c2_rng = RNGManager(42).get_stream(ModuleId.C2)
        with pytest.raises(ValueError, match="side_defaults"):
            loader._create_commander_engine(
                c2_rng,
                {
                    "side_defaults": {"blue": "balanced_default"},
                    "assignments": {"unit_1": "aggressive_armor"},
                },
            )

    def test_commander_assignments_stripped(self) -> None:
        from pathlib import Path
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = Path("data")
        c2_rng = RNGManager(42).get_stream(ModuleId.C2)
        result = loader._create_commander_engine(
            c2_rng,
            {
                "assignments": {"unit_1": "aggressive_armor"},
            },
        )
        assert result["commander_engine"] is not None


# =========================================================================
# 3. Side-level and per-unit assignments
# =========================================================================


class TestCommanderAssignments:
    """Production scenario loading wires exact commander assignments."""

    def test_side_profile_assigns_all_units(self) -> None:
        from pathlib import Path
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        ctx = ScenarioLoader(Path("data")).load(
            Path("data/scenarios/test_campaign/scenario.yaml"),
            seed=42,
        )
        engine = ctx.commander_engine
        assert engine is not None

        all_units = ctx.all_units()
        assignments = engine.assignments()
        assert set(assignments) == {unit.entity_id for unit in all_units}
        assert all(
            assignments[unit.entity_id] == ("aggressive_armor" if unit.side == "blue" else "cautious_infantry")
            for unit in all_units
        )

    def test_per_unit_override(self) -> None:
        from pathlib import Path
        from stochastic_warfare.simulation.scenario import (
            ScenarioLoader,
            load_campaign_scenario_config,
        )

        scenario_path = Path("data/scenarios/test_campaign/scenario.yaml")
        raw = load_campaign_scenario_config(scenario_path).model_dump(
            mode="python",
        )
        raw["commander_config"] = {
            "assignments": {
                "blue_m1a2_0000": "balanced_default",
            },
        }
        cfg = CampaignScenarioConfig.model_validate(raw)
        ctx = ScenarioLoader(Path("data")).load(
            scenario_path,
            seed=42,
            scenario_config=cfg,
        )

        assert ctx.commander_engine is not None
        personality = ctx.commander_engine.get_personality(
            "blue_m1a2_0000",
        )
        assert personality is not None
        assert personality.profile_id == "balanced_default"
        assert ctx.commander_engine.assignments()["blue_m1a2_0001"] == "aggressive_armor"

    def test_no_commander_engine_is_noop(self) -> None:
        cfg = _minimal_config()
        ctx = _make_ctx(config=cfg, commander_engine=None)

        assert ctx.commander_engine is None

    def test_invalid_profile_rejected_before_force_construction(self) -> None:
        from pathlib import Path
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        cfg = _minimal_config(
            sides=[
                {
                    **_MINIMAL_SIDES[0],
                    "commander_profile": "nonexistent_profile",
                },
                {
                    **_MINIMAL_SIDES[1],
                    "commander_profile": "cautious_infantry",
                },
            ],
        )
        with pytest.raises(ValueError, match="nonexistent_profile"):
            ScenarioLoader(Path("data")).load(
                Path("data/scenarios/test_scenario/scenario.yaml"),
                scenario_config=cfg,
            )


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

    def test_no_commander_advances_real_ooda_cycle(self) -> None:
        from stochastic_warfare.simulation.battle import BattleManager

        bm = BattleManager(EventBus())
        ooda = OODALoopEngine(
            EventBus(),
            RNGManager(42).get_stream(ModuleId.C2),
            OODAConfig(timing_sigma=0.0, tactical_acceleration=1.0),
        )
        ooda.register_commander("u1", int(EchelonLevel.PLATOON))
        ooda.start_phase(
            "u1",
            OODAPhase.ACT,
            ts=TS,
            publish_event=False,
        )

        ctx = _make_ctx(
            ooda_engine=ooda,
            commander_engine=None,
            school_registry=None,
            assessor=None,
            decision_engine=None,
            units_by_side={"blue": [_make_unit("u1")], "red": []},
        )
        completions = [("u1", OODAPhase.ACT)]
        bm._process_ooda_completions(ctx, completions, TS)

        assert ooda.get_phase("u1") is OODAPhase.OBSERVE
        assert ooda.get_cycle_count("u1") == 1
        state = ooda.get_state()["commanders"]["u1"]
        assert state["phase_timer"] == 30.0
        assert state["phase_duration"] == 30.0
