"""Tests for Phase 11c: Movement & Logistics Fidelity.

Changes tested:
  10. Fuel gating on movement (movement/engine.py)
  11. Stochastic engineering times (logistics/engineering.py)
  12. Wave attack modeling (simulation/battle.py)
  13. Stochastic reinforcement arrivals (simulation/campaign.py + scenario.py)
"""

from __future__ import annotations

import types
from datetime import datetime, timezone

import numpy as np
import pytest

from tests.conftest import make_rng

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position
from stochastic_warfare.logistics.engineering import (
    EngineeringConfig,
    EngineeringEngine,
    EngineeringTask,
)
from stochastic_warfare.movement.engine import MovementConfig, MovementEngine, MovementResult
from stochastic_warfare.simulation.battle import BattleContext, BattleManager
from stochastic_warfare.simulation.campaign import CampaignManager, ReinforcementEntry
from stochastic_warfare.simulation.scenario import ReinforcementConfig


# ── helpers ──────────────────────────────────────────────────────────


def _bus() -> EventBus:
    return EventBus()


def _pos(e: float = 0.0, n: float = 0.0, alt: float = 0.0) -> Position:
    return Position(easting=e, northing=n, altitude=alt)


def _mock_unit(
    pos: Position | None = None,
    max_speed: float = 10.0,
    status: int = 0,
    entity_id: str = "u1",
    side: str = "blue",
    speed: float = 10.0,
    personnel: list | None = None,
    equipment: list | None = None,
) -> types.SimpleNamespace:
    """Minimal mock unit for movement/battle tests."""
    from stochastic_warfare.entities.base import UnitStatus
    return types.SimpleNamespace(
        position=pos or _pos(0, 0),
        max_speed=max_speed,
        status=UnitStatus(status),
        entity_id=entity_id,
        side=side,
        speed=speed,
        personnel=personnel,
        equipment=equipment,
        armor_front=0.0,
    )


# =====================================================================
# 10. Fuel gating on movement
# =====================================================================


class TestFuelGating:
    """Fuel gating -- movement limited by available fuel."""

    def test_full_fuel_moves_normally(self) -> None:
        """Unlimited fuel should not restrict movement."""
        eng = MovementEngine(rng=make_rng())
        unit = _mock_unit(pos=_pos(0, 0), max_speed=10.0)
        result = eng.move_unit(unit, _pos(1000, 0), dt=10.0, fuel_available=float("inf"))
        assert result.distance_moved > 0
        assert result.distance_moved == pytest.approx(100.0, abs=10.0)

    def test_zero_fuel_stops(self) -> None:
        """Zero fuel should prevent movement."""
        eng = MovementEngine(rng=make_rng())
        unit = _mock_unit(pos=_pos(0, 0), max_speed=10.0)
        result = eng.move_unit(unit, _pos(1000, 0), dt=10.0, fuel_available=0.0)
        assert result.distance_moved == 0.0
        assert result.new_position.easting == 0.0

    def test_partial_fuel_clamps_distance(self) -> None:
        """Limited fuel should clamp distance to fuel/rate."""
        eng = MovementEngine(config=MovementConfig(noise_std=0.0))
        unit = _mock_unit(pos=_pos(0, 0), max_speed=10.0)
        # fuel_rate = 0.0001/m for max_speed > 5.0
        # fuel_available = 0.005 -> max distance = 0.005/0.0001 = 50m
        result = eng.move_unit(unit, _pos(1000, 0), dt=10.0, fuel_available=0.005)
        assert result.distance_moved <= 50.1  # slight tolerance
        assert result.distance_moved > 0.0

    def test_no_fuel_consumption_infantry(self) -> None:
        """Infantry (max_speed <= 5) should consume no fuel."""
        eng = MovementEngine(config=MovementConfig(noise_std=0.0))
        unit = _mock_unit(pos=_pos(0, 0), max_speed=1.3)
        result = eng.move_unit(unit, _pos(1000, 0), dt=10.0, fuel_available=0.001)
        # Infantry fuel_rate = 0, so fuel gating does not clamp
        assert result.distance_moved > 0
        assert result.fuel_consumed == 0.0

    def test_default_fuel_is_infinite(self) -> None:
        """Default fuel_available should be infinity (backward-compatible)."""
        eng = MovementEngine(rng=make_rng())
        unit = _mock_unit(pos=_pos(0, 0), max_speed=10.0)
        result = eng.move_unit(unit, _pos(1000, 0), dt=10.0)
        assert result.distance_moved > 0

    def test_fuel_consumed_returned(self) -> None:
        """Fuel consumed should be returned in result."""
        eng = MovementEngine(config=MovementConfig(noise_std=0.0))
        unit = _mock_unit(pos=_pos(0, 0), max_speed=10.0)
        result = eng.move_unit(unit, _pos(1000, 0), dt=10.0, fuel_available=float("inf"))
        # dist ~ 100m, fuel_rate = 0.0001 -> fuel ~ 0.01
        assert result.fuel_consumed > 0
        assert result.fuel_consumed == pytest.approx(result.distance_moved * 0.0001, abs=0.001)

    def test_negative_fuel_treated_as_zero(self) -> None:
        """Negative fuel should be treated as no fuel."""
        eng = MovementEngine(rng=make_rng())
        unit = _mock_unit(pos=_pos(0, 0), max_speed=10.0)
        result = eng.move_unit(unit, _pos(1000, 0), dt=10.0, fuel_available=-1.0)
        assert result.distance_moved == 0.0


# =====================================================================
# 11. Stochastic engineering times
# =====================================================================


class TestStochasticEngineering:
    """Stochastic variation on engineering task durations."""

    def test_sigma_zero_deterministic(self) -> None:
        """duration_sigma=0 should produce exact base duration."""
        config = EngineeringConfig(duration_sigma=0.0)
        eng = EngineeringEngine(_bus(), make_rng(), config=config)
        hours = eng.assess_task(EngineeringTask.BUILD_BRIDGE)
        assert hours == 8.0

    def test_sigma_positive_varies(self) -> None:
        """duration_sigma > 0 should produce varied durations across calls."""
        config = EngineeringConfig(duration_sigma=0.3)
        eng = EngineeringEngine(_bus(), make_rng(42), config=config)
        durations = [eng.assess_task(EngineeringTask.BUILD_BRIDGE) for _ in range(20)]
        # All should be close to 8h but not identical
        unique_values = set(durations)
        assert len(unique_values) == 20  # All different with RNG

    def test_lognormal_distribution_shape(self) -> None:
        """With sigma > 0, durations should be log-normally distributed."""
        config = EngineeringConfig(duration_sigma=0.3)
        eng = EngineeringEngine(_bus(), make_rng(42), config=config)
        durations = [eng.assess_task(EngineeringTask.BUILD_BRIDGE) for _ in range(1000)]
        # Mean should be near 8h * exp(sigma^2/2) ~ 8.37
        mean_dur = np.mean(durations)
        expected_mean = 8.0 * np.exp(0.3 ** 2 / 2)
        assert mean_dur == pytest.approx(expected_mean, rel=0.1)

    def test_default_sigma_is_zero(self) -> None:
        """Default duration_sigma should be 0 (MVP behavior)."""
        config = EngineeringConfig()
        assert config.duration_sigma == 0.0


# =====================================================================
# 12. Wave attack modeling
# =====================================================================


class TestWaveAttackModeling:
    """Wave attack gating -- units advance in waves."""

    def _make_battle_ctx(
        self, wave_assignments: dict | None = None
    ) -> BattleContext:
        return BattleContext(
            battle_id="test_battle",
            start_tick=0,
            start_time=datetime.now(timezone.utc),
            involved_sides=["blue", "red"],
            wave_assignments=wave_assignments or {},
            battle_elapsed_s=0.0,
        )

    def _make_sim_ctx(self, cal: dict | None = None) -> types.SimpleNamespace:
        return types.SimpleNamespace(
            calibration=cal or {},
        )

    def test_wave_zero_moves_immediately(self) -> None:
        """Wave 0 units should move from tick 0."""
        battle = self._make_battle_ctx(wave_assignments={"u1": 0})
        battle.battle_elapsed_s = 0.0
        bm = BattleManager(_bus())
        ctx = self._make_sim_ctx()

        u1 = _mock_unit(pos=_pos(0, 0), entity_id="u1", speed=10.0)
        enemies = [_mock_unit(pos=_pos(1000, 0), entity_id="e1", side="red")]
        units_by_side = {"blue": [u1], "red": enemies}
        active_enemies = {"blue": enemies, "red": [u1]}

        bm._execute_movement(ctx, units_by_side, active_enemies, dt=5.0, battle=battle)
        assert u1.position.easting > 0.0

    def test_wave_one_delayed(self) -> None:
        """Wave 1 units should not move until wave_interval has elapsed."""
        battle = self._make_battle_ctx(wave_assignments={"u1": 1})
        battle.battle_elapsed_s = 100.0  # only 100s, wave_interval defaults to 300
        bm = BattleManager(_bus())
        ctx = self._make_sim_ctx()

        u1 = _mock_unit(pos=_pos(0, 0), entity_id="u1", speed=10.0)
        enemies = [_mock_unit(pos=_pos(1000, 0), entity_id="e1", side="red")]
        units_by_side = {"blue": [u1], "red": enemies}
        active_enemies = {"blue": enemies, "red": [u1]}

        bm._execute_movement(ctx, units_by_side, active_enemies, dt=5.0, battle=battle)
        assert u1.position.easting == 0.0  # Still held

    def test_wave_one_released_after_interval(self) -> None:
        """Wave 1 should move after 1 x wave_interval_s."""
        battle = self._make_battle_ctx(wave_assignments={"u1": 1})
        battle.battle_elapsed_s = 350.0  # > 1*300
        bm = BattleManager(_bus())
        ctx = self._make_sim_ctx()

        u1 = _mock_unit(pos=_pos(0, 0), entity_id="u1", speed=10.0)
        enemies = [_mock_unit(pos=_pos(1000, 0), entity_id="e1", side="red")]
        units_by_side = {"blue": [u1], "red": enemies}
        active_enemies = {"blue": enemies, "red": [u1]}

        bm._execute_movement(ctx, units_by_side, active_enemies, dt=5.0, battle=battle)
        assert u1.position.easting > 0.0

    def test_wave_negative_one_held(self) -> None:
        """Wave -1 (reserve) units should never move."""
        battle = self._make_battle_ctx(wave_assignments={"u1": -1})
        battle.battle_elapsed_s = 10000.0  # Long time
        bm = BattleManager(_bus())
        ctx = self._make_sim_ctx()

        u1 = _mock_unit(pos=_pos(0, 0), entity_id="u1", speed=10.0)
        enemies = [_mock_unit(pos=_pos(1000, 0), entity_id="e1", side="red")]
        units_by_side = {"blue": [u1], "red": enemies}
        active_enemies = {"blue": enemies, "red": [u1]}

        bm._execute_movement(ctx, units_by_side, active_enemies, dt=5.0, battle=battle)
        assert u1.position.easting == 0.0

    def test_unassigned_defaults_to_wave_zero(self) -> None:
        """Units not in wave_assignments should default to wave 0 (immediate)."""
        battle = self._make_battle_ctx(wave_assignments={})
        battle.battle_elapsed_s = 0.0
        bm = BattleManager(_bus())
        ctx = self._make_sim_ctx()

        u1 = _mock_unit(pos=_pos(0, 0), entity_id="u1", speed=10.0)
        enemies = [_mock_unit(pos=_pos(1000, 0), entity_id="e1", side="red")]
        units_by_side = {"blue": [u1], "red": enemies}
        active_enemies = {"blue": enemies, "red": [u1]}

        bm._execute_movement(ctx, units_by_side, active_enemies, dt=5.0, battle=battle)
        assert u1.position.easting > 0.0

    def test_battle_elapsed_tracking(self) -> None:
        """battle_elapsed_s should increment each tick."""
        battle = self._make_battle_ctx()
        assert battle.battle_elapsed_s == 0.0
        battle.battle_elapsed_s += 5.0
        assert battle.battle_elapsed_s == 5.0
        battle.battle_elapsed_s += 5.0
        assert battle.battle_elapsed_s == 10.0

    def test_custom_wave_interval(self) -> None:
        """Custom wave_interval_s from calibration should be used."""
        battle = self._make_battle_ctx(wave_assignments={"u1": 1})
        battle.battle_elapsed_s = 50.0
        bm = BattleManager(_bus())
        # Custom wave interval of 40s -- wave 1 released at 40s
        ctx = self._make_sim_ctx(cal={"wave_interval_s": 40.0})

        u1 = _mock_unit(pos=_pos(0, 0), entity_id="u1", speed=10.0)
        enemies = [_mock_unit(pos=_pos(1000, 0), entity_id="e1", side="red")]
        units_by_side = {"blue": [u1], "red": enemies}
        active_enemies = {"blue": enemies, "red": [u1]}

        bm._execute_movement(ctx, units_by_side, active_enemies, dt=5.0, battle=battle)
        assert u1.position.easting > 0.0  # Should be released


# =====================================================================
# 13. Stochastic reinforcement arrivals
# =====================================================================


class TestStochasticReinforcements:
    """Stochastic variation on reinforcement arrival times."""

    def test_sigma_zero_deterministic(self) -> None:
        """With sigma=0, actual arrival equals configured arrival."""
        mgr = CampaignManager(_bus(), make_rng())
        config = ReinforcementConfig(
            side="blue", arrival_time_s=3600.0,
            units=[], arrival_sigma=0.0,
        )
        mgr.set_reinforcements([config])
        entry = mgr._reinforcements[0]
        assert entry.actual_arrival_time_s == 3600.0

    def test_sigma_positive_varies(self) -> None:
        """With sigma > 0, actual arrival should differ from nominal."""
        mgr = CampaignManager(_bus(), make_rng(42))
        config = ReinforcementConfig(
            side="blue", arrival_time_s=3600.0,
            units=[], arrival_sigma=0.3,
        )
        mgr.set_reinforcements([config])
        entry = mgr._reinforcements[0]
        # Should not equal exactly 3600 (extremely unlikely with sigma=0.3)
        assert entry.actual_arrival_time_s != 3600.0
        # Should be in a reasonable range (log-normal around 3600)
        assert 1000.0 < entry.actual_arrival_time_s < 10000.0

    def test_check_uses_actual_arrival_time(self) -> None:
        """check_reinforcements should use actual_arrival_time_s, not config."""
        mgr = CampaignManager(_bus(), make_rng(42))
        config = ReinforcementConfig(
            side="blue", arrival_time_s=3600.0,
            units=[], arrival_sigma=0.0,
        )
        mgr.set_reinforcements([config])
        # Manually set actual arrival earlier than config
        mgr._reinforcements[0].actual_arrival_time_s = 100.0

        # Mock ctx
        ctx = types.SimpleNamespace(
            unit_loader=None,
            rng_manager=None,
        )
        mgr.check_reinforcements(ctx, elapsed_s=150.0)
        assert mgr._reinforcements[0].arrived is True

    def test_state_persistence(self) -> None:
        """actual_arrival_time_s should survive get_state/set_state."""
        mgr = CampaignManager(_bus(), make_rng(42))
        config = ReinforcementConfig(
            side="blue", arrival_time_s=3600.0,
            units=[], arrival_sigma=0.3,
        )
        mgr.set_reinforcements([config])
        original_actual = mgr._reinforcements[0].actual_arrival_time_s
        state = mgr.get_state()
        assert "actual_arrival_time_s" in state["reinforcements"][0]

        # Restore into a new manager
        mgr2 = CampaignManager(_bus(), make_rng(99))
        mgr2.set_reinforcements([config])  # Different RNG -> different actual
        mgr2.set_state(state)
        assert mgr2._reinforcements[0].actual_arrival_time_s == original_actual

    def test_default_sigma_is_zero(self) -> None:
        """Default arrival_sigma should be 0 (backward-compatible)."""
        config = ReinforcementConfig(
            side="blue", arrival_time_s=3600.0, units=[],
        )
        assert config.arrival_sigma == 0.0
