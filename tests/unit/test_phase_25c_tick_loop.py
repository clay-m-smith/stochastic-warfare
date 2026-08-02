"""Phase 25c — Tick loop integration tests.

Tests strict_mode, EW update wiring, MOPP speed factor, insurgency
real data, and error-handling improvements.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest

from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.simulation.battle import BattleManager
from stochastic_warfare.simulation.engine import SimulationEngine, EngineConfig
from stochastic_warfare.simulation.scenario import (
    CampaignScenarioConfig,
    SimulationContext,
)
from stochastic_warfare.simulation.tactical_targeting import (
    TacticalTargetingRuntime,
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
    units_by_side = overrides.pop("units_by_side", {})
    unit_sides = {
        unit.entity_id: side
        for side, side_units in units_by_side.items()
        for unit in side_units
    }
    empty_loadouts = {
        unit_id: ()
        for unit_id in sorted(unit_sides)
    }
    return SimulationContext(
        config=config,
        clock=SimulationClock(start=TS, tick_duration=timedelta(seconds=10)),
        rng_manager=RNGManager(42),
        event_bus=EventBus(),
        units_by_side=units_by_side,
        unit_weapons=dict(empty_loadouts),
        unit_sensor_attachments=dict(empty_loadouts),
        unit_sensors=dict(empty_loadouts),
        equipment_resolutions=dict(empty_loadouts),
        tactical_targeting=TacticalTargetingRuntime(
            sensing_aware_standoff_enabled=(
                config.calibration_overrides.enable_sensing_aware_standoff
            ),
            unit_sides=unit_sides,
        ),
        calibration=config.calibration_overrides,
        **overrides,
    )


# =========================================================================
# 1. Strict mode
# =========================================================================


class TestStrictMode:
    """strict_mode=True re-raises exceptions; False logs and continues."""

    def test_strict_mode_default_false(self) -> None:
        ctx = _make_ctx(
            units_by_side={"blue": [], "red": []},
        )
        engine = SimulationEngine(ctx, EngineConfig(max_ticks=1))
        assert engine._strict_mode is False

    def test_strict_mode_true(self) -> None:
        ctx = _make_ctx(
            units_by_side={"blue": [], "red": []},
        )
        engine = SimulationEngine(ctx, EngineConfig(max_ticks=1), strict_mode=True)
        assert engine._strict_mode is True

    @pytest.mark.structural
    def test_non_strict_weather_error_does_not_raise_structural_diagnostic(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Structural diagnostic: a non-strict weather error does not raise."""
        caplog.set_level(logging.ERROR)
        mock_weather = MagicMock()
        mock_weather.update.side_effect = RuntimeError("boom")
        ctx = _make_ctx(
            weather_engine=mock_weather,
            units_by_side={"blue": [], "red": []},
        )
        engine = SimulationEngine(ctx, EngineConfig(max_ticks=1))
        engine._update_environment(10.0)
        mock_weather.update.assert_called_once_with(10.0)
        assert any(record.getMessage() == "Weather engine update failed" for record in caplog.records)

    def test_strict_mode_true_raises_weather_error(self) -> None:
        mock_weather = MagicMock()
        mock_weather.update.side_effect = RuntimeError("boom")
        ctx = _make_ctx(
            weather_engine=mock_weather,
            units_by_side={"blue": [], "red": []},
        )
        engine = SimulationEngine(ctx, EngineConfig(max_ticks=1), strict_mode=True)
        with pytest.raises(RuntimeError, match="boom"):
            engine._update_environment(10.0)

    @pytest.mark.structural
    def test_non_strict_space_error_does_not_raise_structural_diagnostic(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Structural diagnostic: a non-strict space error does not raise."""
        caplog.set_level(logging.ERROR)
        mock_space = MagicMock()
        mock_space.update.side_effect = RuntimeError("space boom")
        ctx = _make_ctx(
            space_engine=mock_space,
            units_by_side={"blue": [], "red": []},
        )
        engine = SimulationEngine(ctx, EngineConfig(max_ticks=1))
        engine._update_environment(10.0)
        assert mock_space.update.call_count == 1
        assert any(record.getMessage() == "Space engine update failed" for record in caplog.records)

    def test_strict_mode_true_raises_space_error(self) -> None:
        mock_space = MagicMock()
        mock_space.update.side_effect = RuntimeError("space boom")
        ctx = _make_ctx(
            space_engine=mock_space,
            units_by_side={"blue": [], "red": []},
        )
        engine = SimulationEngine(ctx, EngineConfig(max_ticks=1), strict_mode=True)
        with pytest.raises(RuntimeError, match="space boom"):
            engine._update_environment(10.0)


# =========================================================================
# 2. EW update
# =========================================================================


class TestEWUpdate:
    """EW engines updated when present, skipped when None."""

    def test_ew_update_called_when_present(self) -> None:
        mock_ew = MagicMock()
        ctx = _make_ctx(
            ew_engine=mock_ew,
            units_by_side={"blue": [], "red": []},
        )
        engine = SimulationEngine(ctx, EngineConfig(max_ticks=1))
        engine._update_ew(10.0)
        mock_ew.update.assert_called_once_with(10.0)

    @pytest.mark.structural
    def test_absent_ew_engine_does_not_raise_structural_diagnostic(
        self,
    ) -> None:
        """Structural diagnostic: an absent EW engine does not raise."""
        ctx = _make_ctx(
            ew_engine=None,
            units_by_side={"blue": [], "red": []},
        )
        engine = SimulationEngine(ctx, EngineConfig(max_ticks=1))
        engine._update_ew(10.0)

    def test_ew_decoy_update_called(self) -> None:
        mock_decoy = MagicMock()
        ctx = _make_ctx(
            ew_decoy_engine=mock_decoy,
            units_by_side={"blue": [], "red": []},
        )
        engine = SimulationEngine(ctx, EngineConfig(max_ticks=1))
        engine._update_ew(10.0)
        mock_decoy.update.assert_called_once_with(10.0)

    @pytest.mark.structural
    def test_absent_ew_decoy_engine_does_not_raise_structural_diagnostic(
        self,
    ) -> None:
        """Structural diagnostic: an absent EW decoy engine does not raise."""
        ctx = _make_ctx(
            ew_decoy_engine=None,
            units_by_side={"blue": [], "red": []},
        )
        engine = SimulationEngine(ctx, EngineConfig(max_ticks=1))
        engine._update_ew(10.0)

    @pytest.mark.structural
    def test_ew_error_emits_structural_diagnostic_without_raising(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Structural diagnostic: an EW error is logged without raising."""
        caplog.set_level(logging.ERROR)
        mock_ew = MagicMock()
        mock_ew.update.side_effect = RuntimeError("ew boom")
        ctx = _make_ctx(
            ew_engine=mock_ew,
            units_by_side={"blue": [], "red": []},
        )
        engine = SimulationEngine(ctx, EngineConfig(max_ticks=1))
        engine._update_ew(10.0)
        mock_ew.update.assert_called_once_with(10.0)
        assert any(record.getMessage() == "EW jamming engine update failed" for record in caplog.records)

    def test_ew_error_raised_strict(self) -> None:
        mock_ew = MagicMock()
        mock_ew.update.side_effect = RuntimeError("ew boom")
        ctx = _make_ctx(
            ew_engine=mock_ew,
            units_by_side={"blue": [], "red": []},
        )
        engine = SimulationEngine(ctx, EngineConfig(max_ticks=1), strict_mode=True)
        with pytest.raises(RuntimeError, match="ew boom"):
            engine._update_ew(10.0)

    def test_ew_update_in_environment_phase(self) -> None:
        """_update_ew is called within _update_environment."""
        mock_ew = MagicMock()
        ctx = _make_ctx(
            ew_engine=mock_ew,
            units_by_side={"blue": [], "red": []},
        )
        engine = SimulationEngine(ctx, EngineConfig(max_ticks=1))
        engine._update_environment(10.0)
        mock_ew.update.assert_called_once_with(10.0)

    @pytest.mark.structural
    def test_ew_without_update_method_does_not_raise_structural_diagnostic(
        self,
    ) -> None:
        """Structural diagnostic: EW without update does not raise."""
        mock_ew = MagicMock(spec=[])  # no update method
        ctx = _make_ctx(
            ew_engine=mock_ew,
            units_by_side={"blue": [], "red": []},
        )
        engine = SimulationEngine(ctx, EngineConfig(max_ticks=1))
        engine._update_ew(10.0)


# =========================================================================
# 3. MOPP speed factor
# =========================================================================


class TestMOPPSpeed:
    """MOPP protection degrades movement speed."""

    def test_mopp_0_no_penalty(self) -> None:
        from stochastic_warfare.cbrn.protection import ProtectionEngine

        factor = ProtectionEngine.get_mopp_speed_factor(0)
        assert factor == 1.0

    def test_mopp_4_penalty(self) -> None:
        from stochastic_warfare.cbrn.protection import ProtectionEngine

        factor = ProtectionEngine.get_mopp_speed_factor(4)
        assert factor < 1.0  # Typically 0.7

    def test_mopp_slows_movement(self) -> None:
        """Units in MOPP move slower in battle."""
        bm = BattleManager(EventBus())

        u1 = _make_unit("u1", "blue")
        object.__setattr__(u1, "position", Position(0.0, 0.0, 0.0))
        e1 = _make_unit("e1", "red")
        object.__setattr__(e1, "position", Position(1000.0, 0.0, 0.0))

        mock_cbrn = MagicMock()
        mock_cbrn._mopp_levels = {"u1": 4}

        ctx = _make_ctx(
            cbrn_engine=mock_cbrn,
            units_by_side={"blue": [u1], "red": [e1]},
        )

        active_enemies = {"blue": [e1], "red": [u1]}
        bm._execute_movement(ctx, ctx.units_by_side, active_enemies, 10.0)

        # u1 should have moved, but less than u.speed * dt = 5 * 10 = 50
        dist_moved = u1.position.easting
        from stochastic_warfare.cbrn.protection import ProtectionEngine

        mopp4_factor = ProtectionEngine.get_mopp_speed_factor(4)
        expected = u1.speed * 10.0 * mopp4_factor
        assert abs(dist_moved - expected) < 0.01

    def test_no_cbrn_no_penalty(self) -> None:
        """Without CBRN engine, no speed penalty."""
        bm = BattleManager(EventBus())

        u1 = _make_unit("u1", "blue")
        object.__setattr__(u1, "position", Position(0.0, 0.0, 0.0))
        e1 = _make_unit("e1", "red")
        object.__setattr__(e1, "position", Position(1000.0, 0.0, 0.0))

        ctx = _make_ctx(
            cbrn_engine=None,
            units_by_side={"blue": [u1], "red": [e1]},
        )

        active_enemies = {"blue": [e1], "red": [u1]}
        bm._execute_movement(ctx, ctx.units_by_side, active_enemies, 10.0)

        expected = u1.speed * 10.0  # 50m
        assert abs(u1.position.easting - expected) < 0.01

    def test_mopp_0_no_penalty_in_movement(self) -> None:
        """MOPP level 0 should not reduce speed."""
        bm = BattleManager(EventBus())

        u1 = _make_unit("u1", "blue")
        object.__setattr__(u1, "position", Position(0.0, 0.0, 0.0))
        e1 = _make_unit("e1", "red")
        object.__setattr__(e1, "position", Position(1000.0, 0.0, 0.0))

        mock_cbrn = MagicMock()
        mock_cbrn._mopp_levels = {"u1": 0}

        ctx = _make_ctx(
            cbrn_engine=mock_cbrn,
            units_by_side={"blue": [u1], "red": [e1]},
        )

        active_enemies = {"blue": [e1], "red": [u1]}
        bm._execute_movement(ctx, ctx.units_by_side, active_enemies, 10.0)

        expected = u1.speed * 10.0  # 50m — no penalty
        assert abs(u1.position.easting - expected) < 0.01

    def test_mopp_missing_unit_no_penalty(self) -> None:
        """Units not in _mopp_levels dict get no penalty."""
        bm = BattleManager(EventBus())

        u1 = _make_unit("u1", "blue")
        object.__setattr__(u1, "position", Position(0.0, 0.0, 0.0))
        e1 = _make_unit("e1", "red")
        object.__setattr__(e1, "position", Position(1000.0, 0.0, 0.0))

        mock_cbrn = MagicMock()
        mock_cbrn._mopp_levels = {}  # u1 not in dict

        ctx = _make_ctx(
            cbrn_engine=mock_cbrn,
            units_by_side={"blue": [u1], "red": [e1]},
        )

        active_enemies = {"blue": [e1], "red": [u1]}
        bm._execute_movement(ctx, ctx.units_by_side, active_enemies, 10.0)

        expected = u1.speed * 10.0
        assert abs(u1.position.easting - expected) < 0.01

    def test_cbrn_no_mopp_levels_attr(self) -> None:
        """If CBRN engine has no _mopp_levels attr, treat as no penalty."""
        bm = BattleManager(EventBus())

        u1 = _make_unit("u1", "blue")
        object.__setattr__(u1, "position", Position(0.0, 0.0, 0.0))
        e1 = _make_unit("e1", "red")
        object.__setattr__(e1, "position", Position(1000.0, 0.0, 0.0))

        mock_cbrn = MagicMock(spec=[])  # no _mopp_levels attr

        ctx = _make_ctx(
            cbrn_engine=mock_cbrn,
            units_by_side={"blue": [u1], "red": [e1]},
        )

        active_enemies = {"blue": [e1], "red": [u1]}
        bm._execute_movement(ctx, ctx.units_by_side, active_enemies, 10.0)

        expected = u1.speed * 10.0
        assert abs(u1.position.easting - expected) < 0.01


# =========================================================================
# 4. Insurgency real data
# =========================================================================


class TestInsurgencyRealData:
    """Insurgency update receives real military presence data."""

    def test_military_presence_from_units(self) -> None:
        mock_insurgency = MagicMock()
        u1 = _make_unit("u1", "blue")
        u2 = _make_unit("u2", "blue")
        e1 = _make_unit("e1", "red")

        ctx = _make_ctx(
            escalation_engine=MagicMock(),
            insurgency_engine=mock_insurgency,
            units_by_side={"blue": [u1, u2], "red": [e1]},
        )
        engine = SimulationEngine(ctx, EngineConfig(max_ticks=1))
        engine._update_escalation(3600.0)

        call_args = mock_insurgency.update_radicalization.call_args
        mil_presence = call_args[1]["military_presence_by_region"]
        assert mil_presence["blue"] == 2.0
        assert mil_presence["red"] == 1.0

    def test_destroyed_units_excluded(self) -> None:
        mock_insurgency = MagicMock()
        u1 = _make_unit("u1", "blue")
        u2 = _make_unit("u2", "blue")
        object.__setattr__(u2, "status", UnitStatus.DESTROYED)

        ctx = _make_ctx(
            escalation_engine=MagicMock(),
            insurgency_engine=mock_insurgency,
            units_by_side={"blue": [u1, u2], "red": []},
        )
        engine = SimulationEngine(ctx, EngineConfig(max_ticks=1))
        engine._update_escalation(3600.0)

        call_args = mock_insurgency.update_radicalization.call_args
        mil_presence = call_args[1]["military_presence_by_region"]
        assert mil_presence["blue"] == 1.0

    def test_collateral_from_consequence_engine(self) -> None:
        mock_insurgency = MagicMock()
        mock_consequence = MagicMock()
        mock_consequence.get_collateral_by_region.return_value = {"region_a": 0.3}

        ctx = _make_ctx(
            escalation_engine=MagicMock(),
            insurgency_engine=mock_insurgency,
            consequence_engine=mock_consequence,
            units_by_side={"blue": [], "red": []},
        )
        engine = SimulationEngine(ctx, EngineConfig(max_ticks=1))
        engine._update_escalation(3600.0)

        call_args = mock_insurgency.update_radicalization.call_args
        collateral = call_args[1]["collateral_by_region"]
        assert collateral == {"region_a": 0.3}

    def test_no_consequence_engine_empty_collateral(self) -> None:
        mock_insurgency = MagicMock()

        ctx = _make_ctx(
            escalation_engine=MagicMock(),
            insurgency_engine=mock_insurgency,
            consequence_engine=None,
            units_by_side={"blue": [], "red": []},
        )
        engine = SimulationEngine(ctx, EngineConfig(max_ticks=1))
        engine._update_escalation(3600.0)

        call_args = mock_insurgency.update_radicalization.call_args
        collateral = call_args[1]["collateral_by_region"]
        assert collateral == {}

    def test_consequence_error_empty_collateral(self) -> None:
        mock_insurgency = MagicMock()
        mock_consequence = MagicMock()
        mock_consequence.get_collateral_by_region.side_effect = RuntimeError("err")

        ctx = _make_ctx(
            escalation_engine=MagicMock(),
            insurgency_engine=mock_insurgency,
            consequence_engine=mock_consequence,
            units_by_side={"blue": [], "red": []},
        )
        engine = SimulationEngine(ctx, EngineConfig(max_ticks=1))
        engine._update_escalation(3600.0)

        call_args = mock_insurgency.update_radicalization.call_args
        collateral = call_args[1]["collateral_by_region"]
        assert collateral == {}

    def test_insurgency_dt_hours(self) -> None:
        mock_insurgency = MagicMock()
        ctx = _make_ctx(
            escalation_engine=MagicMock(),
            insurgency_engine=mock_insurgency,
            units_by_side={"blue": [], "red": []},
        )
        engine = SimulationEngine(ctx, EngineConfig(max_ticks=1))
        engine._update_escalation(1800.0)  # 0.5 hours

        call_args = mock_insurgency.update_radicalization.call_args
        assert abs(call_args[1]["dt_hours"] - 0.5) < 0.01


# =========================================================================
# 5. Error handling
# =========================================================================


class TestErrorHandling:
    """No bare except:pass — errors logged or re-raised."""

    @pytest.mark.structural
    def test_cbrn_error_emits_structural_diagnostic_without_raising(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Structural diagnostic: a CBRN error is logged without raising."""
        caplog.set_level(logging.ERROR)
        mock_cbrn = MagicMock()
        mock_cbrn.update.side_effect = RuntimeError("cbrn")
        ctx = _make_ctx(
            cbrn_engine=mock_cbrn,
            units_by_side={"blue": [], "red": []},
        )
        engine = SimulationEngine(ctx, EngineConfig(max_ticks=1))
        engine._update_environment(10.0)
        assert mock_cbrn.update.call_count == 1
        assert any(record.getMessage() == "CBRN engine update failed" for record in caplog.records)

    def test_cbrn_error_raised_strict(self) -> None:
        mock_cbrn = MagicMock()
        mock_cbrn.update.side_effect = RuntimeError("cbrn strict")
        ctx = _make_ctx(
            cbrn_engine=mock_cbrn,
            units_by_side={"blue": [], "red": []},
        )
        engine = SimulationEngine(ctx, EngineConfig(max_ticks=1), strict_mode=True)
        with pytest.raises(RuntimeError, match="cbrn strict"):
            engine._update_environment(10.0)

    def test_time_of_day_not_called_in_update(self) -> None:
        """TimeOfDayEngine is query-only — no per-tick update call."""
        mock_tod = MagicMock()
        mock_tod.update.side_effect = RuntimeError("tod")
        ctx = _make_ctx(
            time_of_day_engine=mock_tod,
            units_by_side={"blue": [], "red": []},
        )
        engine = SimulationEngine(ctx, EngineConfig(max_ticks=1), strict_mode=True)
        # Should not raise — TimeOfDayEngine.update is never called
        engine._update_environment(10.0)
        mock_tod.update.assert_not_called()

    @pytest.mark.structural
    def test_multiple_environment_errors_do_not_raise_structural_diagnostic(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Structural diagnostic: multiple environment errors do not raise."""
        caplog.set_level(logging.ERROR)
        mock_weather = MagicMock()
        mock_weather.update.side_effect = RuntimeError("weather")
        mock_sea = MagicMock()
        mock_sea.update.side_effect = RuntimeError("sea")

        ctx = _make_ctx(
            weather_engine=mock_weather,
            sea_state_engine=mock_sea,
            units_by_side={"blue": [], "red": []},
        )
        engine = SimulationEngine(ctx, EngineConfig(max_ticks=1))
        engine._update_environment(10.0)
        mock_weather.update.assert_called_once_with(10.0)
        mock_sea.update.assert_called_once_with(10.0)
        messages = {record.getMessage() for record in caplog.records}
        assert "Weather engine update failed" in messages
        assert "Sea state engine update failed" in messages


# =========================================================================
# 6. Backward compat
# =========================================================================


class TestBackwardCompat:
    """No optional engines → identical behavior."""

    @pytest.mark.structural
    def test_absent_optional_environment_engines_do_not_raise_structural_diagnostic(
        self,
    ) -> None:
        """Structural diagnostic: absent optional engines do not raise."""
        ctx = _make_ctx(
            ew_engine=None,
            ew_decoy_engine=None,
            cbrn_engine=None,
            space_engine=None,
            units_by_side={"blue": [], "red": []},
        )
        engine = SimulationEngine(ctx, EngineConfig(max_ticks=1))
        engine._update_environment(10.0)

    def test_no_escalation_engines(self) -> None:
        ctx = _make_ctx(
            escalation_engine=None,
            insurgency_engine=None,
            units_by_side={"blue": [], "red": []},
        )
        engine = SimulationEngine(ctx, EngineConfig(max_ticks=1))
        # _update_escalation is only called when escalation_engine is not None
        # So this just tests the engine can be created
        assert engine._strict_mode is False

    def test_default_engine_creates_normally(self) -> None:
        ctx = _make_ctx(
            units_by_side={"blue": [], "red": []},
        )
        engine = SimulationEngine(ctx, EngineConfig(max_ticks=1))
        assert engine._strict_mode is False
        assert engine._ctx is ctx
