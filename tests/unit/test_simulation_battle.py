"""Tests for the tactical battle manager (simulation.battle).

Uses shared fixtures from conftest.py: rng, event_bus, sim_clock, rng_manager.
"""

from __future__ import annotations


import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.simulation.battle import (
    BattleConfig,
    BattleContext,
    BattleManager,
    BattleResult,
)

from tests.conftest import POS_ORIGIN, TS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_unit(
    eid: str,
    pos: Position,
    side: str = "blue",
    status: UnitStatus = UnitStatus.ACTIVE,
    speed: float = 0.0,
) -> Unit:
    """Create a unit with the given properties."""
    u = Unit(entity_id=eid, position=pos)
    object.__setattr__(u, "side", side)
    object.__setattr__(u, "status", status)
    object.__setattr__(u, "speed", speed)
    return u


def _units_by_side(
    blue_positions: list[Position],
    red_positions: list[Position],
) -> dict[str, list[Unit]]:
    """Create units_by_side from position lists."""
    blue = [_make_unit(f"blue_{i:04d}", p, "blue") for i, p in enumerate(blue_positions)]
    red = [_make_unit(f"red_{i:04d}", p, "red") for i, p in enumerate(red_positions)]
    return {"blue": blue, "red": red}


# ---------------------------------------------------------------------------
# BattleConfig
# ---------------------------------------------------------------------------


class TestBattleConfig:
    """BattleConfig pydantic model."""

    def test_defaults(self) -> None:
        c = BattleConfig()
        assert c.engagement_range_m == 10000.0
        assert c.morale_check_interval == 12
        assert c.destruction_threshold == 0.5

    def test_custom_values(self) -> None:
        c = BattleConfig(engagement_range_m=5000, morale_check_interval=6)
        assert c.engagement_range_m == 5000.0


# ---------------------------------------------------------------------------
# BattleContext
# ---------------------------------------------------------------------------


class TestBattleContext:
    """BattleContext dataclass."""

    def test_creation(self) -> None:
        b = BattleContext(
            battle_id="battle_0001",
            start_tick=0,
            start_time=TS,
            involved_sides=["blue", "red"],
        )
        assert b.battle_id == "battle_0001"
        assert b.active is True
        assert b.ticks_executed == 0

    def test_unit_ids_tracking(self) -> None:
        b = BattleContext(
            battle_id="b1", start_tick=0, start_time=TS,
            involved_sides=["blue", "red"],
            unit_ids={"u1", "u2"},
        )
        assert "u1" in b.unit_ids


# ---------------------------------------------------------------------------
# BattleResult
# ---------------------------------------------------------------------------


class TestBattleResult:
    """BattleResult frozen dataclass."""

    def test_creation(self) -> None:
        r = BattleResult(battle_id="b1", duration_ticks=100, terminated_by="force_destroyed")
        assert r.battle_id == "b1"
        assert r.duration_ticks == 100

    def test_frozen(self) -> None:
        r = BattleResult(battle_id="b1", duration_ticks=100, terminated_by="test")
        with pytest.raises(AttributeError):
            r.battle_id = "b2"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Engagement detection
# ---------------------------------------------------------------------------


class TestEngagementDetection:
    """BattleManager.detect_engagement."""

    def test_forces_in_range_detected(self, event_bus: EventBus) -> None:
        mgr = BattleManager(event_bus, BattleConfig(engagement_range_m=5000))
        units = _units_by_side(
            [Position(1000, 5000, 0)],
            [Position(4000, 5000, 0)],
        )
        battles = mgr.detect_engagement(units)
        assert len(battles) == 1

    def test_forces_out_of_range_not_detected(self, event_bus: EventBus) -> None:
        mgr = BattleManager(event_bus, BattleConfig(engagement_range_m=1000))
        units = _units_by_side(
            [Position(0, 0, 0)],
            [Position(5000, 5000, 0)],
        )
        battles = mgr.detect_engagement(units)
        assert len(battles) == 0

    def test_no_duplicate_battles(self, event_bus: EventBus) -> None:
        mgr = BattleManager(event_bus, BattleConfig(engagement_range_m=10000))
        units = _units_by_side(
            [Position(0, 0, 0)],
            [Position(1000, 0, 0)],
        )
        battles1 = mgr.detect_engagement(units)
        battles2 = mgr.detect_engagement(units)
        assert len(battles1) == 1
        assert len(battles2) == 0  # Already tracked

    def test_custom_engagement_range(self, event_bus: EventBus) -> None:
        mgr = BattleManager(event_bus)
        units = _units_by_side(
            [Position(0, 0, 0)],
            [Position(500, 0, 0)],
        )
        battles = mgr.detect_engagement(units, engagement_range_m=100)
        assert len(battles) == 0

    def test_destroyed_units_ignored(self, event_bus: EventBus) -> None:
        mgr = BattleManager(event_bus, BattleConfig(engagement_range_m=5000))
        blue = [_make_unit("b1", Position(0, 0, 0), "blue", UnitStatus.DESTROYED)]
        red = [_make_unit("r1", Position(1000, 0, 0), "red")]
        battles = mgr.detect_engagement({"blue": blue, "red": red})
        assert len(battles) == 0

    def test_empty_side_no_battle(self, event_bus: EventBus) -> None:
        mgr = BattleManager(event_bus)
        battles = mgr.detect_engagement({"blue": [], "red": []})
        assert len(battles) == 0

    def test_multiple_units_closest_pair_used(self, event_bus: EventBus) -> None:
        mgr = BattleManager(event_bus, BattleConfig(engagement_range_m=2000))
        units = _units_by_side(
            [Position(0, 0, 0), Position(0, 1000, 0)],
            [Position(1500, 0, 0), Position(10000, 0, 0)],
        )
        battles = mgr.detect_engagement(units)
        assert len(battles) == 1

    def test_active_battles_property(self, event_bus: EventBus) -> None:
        mgr = BattleManager(event_bus, BattleConfig(engagement_range_m=10000))
        units = _units_by_side([Position(0, 0, 0)], [Position(1000, 0, 0)])
        mgr.detect_engagement(units)
        assert len(mgr.active_battles) == 1


# ---------------------------------------------------------------------------
# Battle termination
# ---------------------------------------------------------------------------


class TestBattleTermination:
    """BattleManager.check_battle_termination."""

    def test_active_battle_not_terminated(self, event_bus: EventBus) -> None:
        mgr = BattleManager(event_bus)
        battle = BattleContext(
            battle_id="b1", start_tick=0, start_time=TS,
            involved_sides=["blue", "red"],
        )
        units = _units_by_side([Position(0, 0, 0)], [Position(1000, 0, 0)])
        assert mgr.check_battle_termination(battle, units) is False

    def test_no_active_units_terminates(self, event_bus: EventBus) -> None:
        mgr = BattleManager(event_bus)
        battle = BattleContext(
            battle_id="b1", start_tick=0, start_time=TS,
            involved_sides=["blue", "red"],
        )
        blue = [_make_unit("b1", Position(0, 0, 0), "blue")]
        red = [_make_unit("r1", Position(1000, 0, 0), "red", UnitStatus.DESTROYED)]
        assert mgr.check_battle_termination(battle, {"blue": blue, "red": red}) is True

    def test_max_ticks_terminates(self, event_bus: EventBus) -> None:
        mgr = BattleManager(event_bus, BattleConfig(max_ticks_per_battle=10))
        battle = BattleContext(
            battle_id="b1", start_tick=0, start_time=TS,
            involved_sides=["blue", "red"],
        )
        battle.ticks_executed = 10
        units = _units_by_side([Position(0, 0, 0)], [Position(1000, 0, 0)])
        assert mgr.check_battle_termination(battle, units) is True

    def test_disengaged_terminates(self, event_bus: EventBus) -> None:
        mgr = BattleManager(event_bus, BattleConfig(engagement_range_m=1000))
        battle = BattleContext(
            battle_id="b1", start_tick=0, start_time=TS,
            involved_sides=["blue", "red"],
        )
        # Forces far apart (> 2x engagement range)
        units = _units_by_side([Position(0, 0, 0)], [Position(50000, 0, 0)])
        assert mgr.check_battle_termination(battle, units) is True

    def test_inactive_battle_returns_true(self, event_bus: EventBus) -> None:
        mgr = BattleManager(event_bus)
        battle = BattleContext(
            battle_id="b1", start_tick=0, start_time=TS,
            involved_sides=["blue", "red"],
            active=False,
        )
        units = _units_by_side([Position(0, 0, 0)], [Position(1000, 0, 0)])
        assert mgr.check_battle_termination(battle, units) is True

    def test_missing_side_terminates(self, event_bus: EventBus) -> None:
        mgr = BattleManager(event_bus)
        battle = BattleContext(
            battle_id="b1", start_tick=0, start_time=TS,
            involved_sides=["blue", "red"],
        )
        units = {"blue": [_make_unit("b1", Position(0, 0, 0), "blue")]}
        assert mgr.check_battle_termination(battle, units) is True


# ---------------------------------------------------------------------------
# Battle resolution
# ---------------------------------------------------------------------------


class TestBattleResolution:
    """BattleManager.resolve_battle."""

    def test_resolve_produces_result(self, event_bus: EventBus) -> None:
        mgr = BattleManager(event_bus)
        battle = BattleContext(
            battle_id="b1", start_tick=0, start_time=TS,
            involved_sides=["blue", "red"],
        )
        battle.ticks_executed = 50
        units = _units_by_side([Position(0, 0, 0)], [Position(1000, 0, 0)])
        result = mgr.resolve_battle(battle, units)
        assert result.battle_id == "b1"
        assert result.duration_ticks == 50

    def test_resolve_deactivates_battle(self, event_bus: EventBus) -> None:
        mgr = BattleManager(event_bus)
        battle = BattleContext(
            battle_id="b1", start_tick=0, start_time=TS,
            involved_sides=["blue", "red"],
        )
        units = _units_by_side([Position(0, 0, 0)], [Position(1000, 0, 0)])
        mgr.resolve_battle(battle, units)
        assert battle.active is False

    def test_resolve_counts_destroyed(self, event_bus: EventBus) -> None:
        mgr = BattleManager(event_bus)
        battle = BattleContext(
            battle_id="b1", start_tick=0, start_time=TS,
            involved_sides=["blue", "red"],
        )
        red = [
            _make_unit("r1", POS_ORIGIN, "red", UnitStatus.DESTROYED),
            _make_unit("r2", POS_ORIGIN, "red", UnitStatus.DESTROYED),
            _make_unit("r3", POS_ORIGIN, "red"),
        ]
        blue = [_make_unit("b1", POS_ORIGIN, "blue")]
        result = mgr.resolve_battle(battle, {"blue": blue, "red": red})
        assert result.units_destroyed["red"] == 2
        assert result.units_destroyed["blue"] == 0

    def test_resolve_reports_terminated_by(self, event_bus: EventBus) -> None:
        mgr = BattleManager(event_bus)
        battle = BattleContext(
            battle_id="b1", start_tick=0, start_time=TS,
            involved_sides=["blue", "red"],
        )
        red = [_make_unit("r1", POS_ORIGIN, "red", UnitStatus.DESTROYED)]
        blue = [_make_unit("b1", POS_ORIGIN, "blue")]
        result = mgr.resolve_battle(battle, {"blue": blue, "red": red})
        assert "force_destroyed" in result.terminated_by

    def test_resolve_max_ticks(self, event_bus: EventBus) -> None:
        mgr = BattleManager(event_bus, BattleConfig(max_ticks_per_battle=100))
        battle = BattleContext(
            battle_id="b1", start_tick=0, start_time=TS,
            involved_sides=["blue", "red"],
        )
        battle.ticks_executed = 100
        units = _units_by_side([POS_ORIGIN], [Position(1000, 0, 0)])
        result = mgr.resolve_battle(battle, units)
        assert result.terminated_by == "max_ticks"

    def test_resolve_disengaged(self, event_bus: EventBus) -> None:
        mgr = BattleManager(event_bus)
        battle = BattleContext(
            battle_id="b1", start_tick=0, start_time=TS,
            involved_sides=["blue", "red"],
        )
        battle.ticks_executed = 10
        units = _units_by_side([POS_ORIGIN], [Position(1000, 0, 0)])
        result = mgr.resolve_battle(battle, units)
        assert result.terminated_by == "disengaged"


# ---------------------------------------------------------------------------
# Deferred damage
# ---------------------------------------------------------------------------


class TestDeferredDamage:
    """Deferred damage application."""

    def test_worst_outcome_wins(self, event_bus: EventBus) -> None:
        mgr = BattleManager(event_bus)
        u = _make_unit("t1", POS_ORIGIN)
        pending = [
            (u, UnitStatus.DISABLED),
            (u, UnitStatus.DESTROYED),
        ]
        mgr._apply_deferred_damage(pending)
        assert u.status == UnitStatus.DESTROYED

    def test_single_damage(self, event_bus: EventBus) -> None:
        mgr = BattleManager(event_bus)
        u = _make_unit("t1", POS_ORIGIN)
        pending = [(u, UnitStatus.DISABLED)]
        mgr._apply_deferred_damage(pending)
        assert u.status == UnitStatus.DISABLED

    def test_multiple_targets(self, event_bus: EventBus) -> None:
        mgr = BattleManager(event_bus)
        u1 = _make_unit("t1", POS_ORIGIN)
        u2 = _make_unit("t2", POS_ORIGIN)
        pending = [
            (u1, UnitStatus.DESTROYED),
            (u2, UnitStatus.DISABLED),
        ]
        mgr._apply_deferred_damage(pending)
        assert u1.status == UnitStatus.DESTROYED
        assert u2.status == UnitStatus.DISABLED

    def test_empty_pending(self, event_bus: EventBus) -> None:
        mgr = BattleManager(event_bus)
        mgr._apply_deferred_damage([])  # Should not raise

    def test_no_damage_preserves_active(self, event_bus: EventBus) -> None:
        u = _make_unit("t1", POS_ORIGIN)
        BattleManager._apply_deferred_damage([])
        assert u.status == UnitStatus.ACTIVE


# ---------------------------------------------------------------------------
# Build enemy data
# ---------------------------------------------------------------------------


class TestBuildEnemyData:
    """BattleManager._build_enemy_data."""

    def test_returns_enemies_per_side(self, event_bus: EventBus) -> None:
        units = _units_by_side([Position(0, 0, 0)], [Position(1000, 0, 0)])
        enemies, pos_arrays = BattleManager._build_enemy_data(units)
        assert len(enemies["blue"]) == 1  # One red enemy
        assert len(enemies["red"]) == 1   # One blue enemy

    def test_destroyed_excluded(self, event_bus: EventBus) -> None:
        blue = [_make_unit("b1", POS_ORIGIN, "blue")]
        red = [_make_unit("r1", POS_ORIGIN, "red", UnitStatus.DESTROYED)]
        enemies, _ = BattleManager._build_enemy_data({"blue": blue, "red": red})
        assert len(enemies["blue"]) == 0

    def test_position_arrays_shape(self, event_bus: EventBus) -> None:
        units = _units_by_side(
            [Position(0, 0, 0), Position(100, 0, 0)],
            [Position(1000, 0, 0)],
        )
        _, pos_arrays = BattleManager._build_enemy_data(units)
        assert pos_arrays["blue"].shape == (1, 2)  # 1 red enemy, 2 coords
        assert pos_arrays["red"].shape == (2, 2)   # 2 blue enemies

    def test_empty_side(self, event_bus: EventBus) -> None:
        _, pos_arrays = BattleManager._build_enemy_data({"blue": [], "red": []})
        assert pos_arrays["blue"].shape == (0, 2)


# ---------------------------------------------------------------------------
# Min distance
# ---------------------------------------------------------------------------


class TestMinDistance:
    """BattleManager._min_distance."""

    def test_adjacent_units(self) -> None:
        a = [_make_unit("a", Position(0, 0, 0))]
        b = [_make_unit("b", Position(100, 0, 0))]
        assert BattleManager._min_distance(a, b) == pytest.approx(100.0)

    def test_diagonal(self) -> None:
        a = [_make_unit("a", Position(0, 0, 0))]
        b = [_make_unit("b", Position(300, 400, 0))]
        assert BattleManager._min_distance(a, b) == pytest.approx(500.0)

    def test_empty_returns_inf(self) -> None:
        a = [_make_unit("a", Position(0, 0, 0))]
        assert BattleManager._min_distance(a, []) == float("inf")

    def test_multiple_units_finds_min(self) -> None:
        a = [_make_unit("a1", Position(0, 0, 0)), _make_unit("a2", Position(1000, 0, 0))]
        b = [_make_unit("b1", Position(500, 0, 0)), _make_unit("b2", Position(5000, 0, 0))]
        # Closest pair: a2(1000,0) to b1(500,0) = 500m
        assert BattleManager._min_distance(a, b) == pytest.approx(500.0)


# ---------------------------------------------------------------------------
# Checkpoint / restore
# ---------------------------------------------------------------------------


class TestCheckpointRestore:
    """Battle manager state persistence."""

    def test_get_state_captures_battles(self, event_bus: EventBus) -> None:
        mgr = BattleManager(event_bus)
        units = _units_by_side([POS_ORIGIN], [Position(1000, 0, 0)])
        mgr.detect_engagement(units, engagement_range_m=5000)
        state = mgr.get_state()
        assert len(state["battles"]) == 1

    def test_set_state_restores_battles(self, event_bus: EventBus) -> None:
        mgr = BattleManager(event_bus)
        units = _units_by_side([POS_ORIGIN], [Position(1000, 0, 0)])
        mgr.detect_engagement(units, engagement_range_m=5000)
        state = mgr.get_state()

        mgr2 = BattleManager(event_bus)
        mgr2.set_state(state)
        assert len(mgr2.active_battles) == 1

    def test_round_trip(self, event_bus: EventBus) -> None:
        mgr = BattleManager(event_bus)
        units = _units_by_side([POS_ORIGIN], [Position(1000, 0, 0)])
        mgr.detect_engagement(units, engagement_range_m=5000)
        state = mgr.get_state()

        mgr2 = BattleManager(event_bus)
        mgr2.set_state(state)
        state2 = mgr2.get_state()
        assert state["next_battle_id"] == state2["next_battle_id"]
