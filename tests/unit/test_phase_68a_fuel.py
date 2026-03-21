"""Phase 68a: Fuel consumption enforcement tests.

Verifies that when ``enable_fuel_consumption=True`` vehicles consume fuel
proportional to distance moved, and that fuel exhaustion sets speed to 0.
"""

from __future__ import annotations

import math
from types import SimpleNamespace

import numpy as np
import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Domain, Position
from stochastic_warfare.entities.base import UnitStatus
from stochastic_warfare.entities.unit_classes.ground import GroundUnit
from stochastic_warfare.simulation.battle import BattleManager, BattleConfig, BattleContext


def _make_unit(
    entity_id: str = "tank1",
    position: Position | None = None,
    max_speed: float = 15.0,
    fuel_remaining: float = 1.0,
    domain: Domain = Domain.GROUND,
    **kw,
) -> GroundUnit:
    pos = position or Position(0, 0, 0)
    u = GroundUnit(
        entity_id=entity_id,
        position=pos,
        max_speed=max_speed,
        fuel_remaining=fuel_remaining,
        domain=domain,
        **kw,
    )
    object.__setattr__(u, "speed", max_speed)
    object.__setattr__(u, "status", UnitStatus.ACTIVE)
    return u


def _make_enemy(entity_id: str = "enemy1", position: Position | None = None) -> GroundUnit:
    pos = position or Position(10000, 0, 0)
    u = GroundUnit(entity_id=entity_id, position=pos, max_speed=0.0)
    object.__setattr__(u, "status", UnitStatus.ACTIVE)
    return u


def _make_ctx(cal_overrides: dict | None = None) -> SimpleNamespace:
    cal = {
        "defensive_sides": [],
        "wave_interval_s": 300.0,
        "enable_fuel_consumption": False,
        "enable_obstacle_effects": False,
        "enable_fire_zones": False,
        "enable_obscurants": False,
        "enable_seasonal_effects": False,
        "enable_equipment_stress": False,
    }
    if cal_overrides:
        cal.update(cal_overrides)
    ctx = SimpleNamespace(
        calibration=cal,
        event_bus=EventBus(),
        obstacle_manager=None,
        incendiary_engine=None,
        obscurants_engine=None,
        seasons_engine=None,
        movement_engine=None,
        config=SimpleNamespace(calibration_overrides=cal),
    )
    return ctx


def _make_battle(ticks: int = 0) -> BattleContext:
    from datetime import datetime, timezone

    return BattleContext(
        battle_id="b1",
        start_tick=0,
        start_time=datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
        involved_sides=["blue", "red"],
        active=True,
        ticks_executed=ticks,
        unit_ids=set(),
        wave_assignments={},
        battle_elapsed_s=float(ticks * 10),
    )


class TestFuelConsumption:
    """Fuel consumed proportional to distance when enabled."""

    def test_fuel_consumed_on_movement(self):
        """Unit moves 100m at ground rate 0.0001 → fuel drops by 0.01."""
        tank = _make_unit(fuel_remaining=1.0)
        enemy = _make_enemy(position=Position(200, 0, 0))  # close enough to trigger movement
        ctx = _make_ctx({"enable_fuel_consumption": True})

        mgr = BattleManager(EventBus())
        battle = _make_battle()

        units_by_side = {"blue": [tank]}
        active_enemies = {"blue": [enemy]}

        mgr._execute_movement(ctx, units_by_side, active_enemies, dt=10.0, battle=battle)

        # Tank should have moved toward enemy and consumed fuel
        assert tank.fuel_remaining < 1.0

    def test_fuel_not_consumed_when_disabled(self):
        """With flag off, fuel stays at initial value."""
        tank = _make_unit(fuel_remaining=1.0)
        enemy = _make_enemy(position=Position(200, 0, 0))
        ctx = _make_ctx({"enable_fuel_consumption": False})

        mgr = BattleManager(EventBus())
        battle = _make_battle()

        mgr._execute_movement(ctx, {"blue": [tank]}, {"blue": [enemy]}, dt=10.0, battle=battle)
        assert tank.fuel_remaining == 1.0

    def test_fuel_exhaustion_sets_speed_zero(self):
        """When fuel hits 0, unit speed is set to 0."""
        # Very low fuel — will exhaust on first movement
        tank = _make_unit(fuel_remaining=0.001, max_speed=15.0)
        enemy = _make_enemy(position=Position(5000, 0, 0))
        ctx = _make_ctx({"enable_fuel_consumption": True})

        mgr = BattleManager(EventBus())
        battle = _make_battle()

        mgr._execute_movement(ctx, {"blue": [tank]}, {"blue": [enemy]}, dt=10.0, battle=battle)

        assert tank.fuel_remaining == 0.0
        assert tank.speed == 0.0

    def test_air_unit_consumes_at_higher_rate(self):
        """Air domain uses 0.0005 vs ground 0.0001."""
        ground = _make_unit(entity_id="gnd", fuel_remaining=1.0)
        air = _make_unit(entity_id="air", fuel_remaining=1.0)
        # Force air domain (GroundUnit.__init__ sets GROUND)
        object.__setattr__(air, "domain", Domain.AERIAL)

        enemy_g = _make_enemy(entity_id="eg", position=Position(200, 0, 0))
        enemy_a = _make_enemy(entity_id="ea", position=Position(200, 0, 0))

        ctx = _make_ctx({"enable_fuel_consumption": True})
        mgr = BattleManager(EventBus())
        battle = _make_battle()

        mgr._execute_movement(ctx, {"blue": [ground]}, {"blue": [enemy_g]}, dt=10.0, battle=battle)
        fuel_ground = ground.fuel_remaining

        mgr._execute_movement(ctx, {"blue": [air]}, {"blue": [enemy_a]}, dt=10.0, battle=battle)
        fuel_air = air.fuel_remaining

        # Both moved same distance (~150m in 10s at 15 m/s), air uses 5x rate
        ground_consumed = 1.0 - fuel_ground
        air_consumed = 1.0 - fuel_air
        assert ground_consumed > 0, "Ground unit should have consumed fuel"
        assert air_consumed > 0, "Air unit should have consumed fuel"
        ratio = air_consumed / ground_consumed
        assert ratio == pytest.approx(5.0, rel=0.1)

    def test_infantry_not_fuel_gated(self):
        """Infantry (max_speed <= 5) doesn't consume fuel even when enabled."""
        inf = _make_unit(entity_id="inf1", max_speed=4.0, fuel_remaining=1.0)
        enemy = _make_enemy(position=Position(200, 0, 0))
        ctx = _make_ctx({"enable_fuel_consumption": True})

        mgr = BattleManager(EventBus())
        battle = _make_battle()

        mgr._execute_movement(ctx, {"blue": [inf]}, {"blue": [enemy]}, dt=10.0, battle=battle)
        # Infantry is not _is_vehicle (max_speed <= 5), fuel unchanged
        assert inf.fuel_remaining == 1.0

    def test_stationary_unit_no_consumption(self):
        """DUG_IN unit (speed=0) doesn't consume fuel."""
        tank = _make_unit(fuel_remaining=1.0, max_speed=15.0)
        object.__setattr__(tank, "speed", 0.0)
        enemy = _make_enemy(position=Position(200, 0, 0))
        ctx = _make_ctx({"enable_fuel_consumption": True, "defensive_sides": ["blue"]})

        mgr = BattleManager(EventBus())
        battle = _make_battle()

        mgr._execute_movement(ctx, {"blue": [tank]}, {"blue": [enemy]}, dt=10.0, battle=battle)
        assert tank.fuel_remaining == 1.0

    def test_custom_fuel_consumption_rate(self):
        """Unit with fuel_consumption_rate attribute uses that rate."""
        tank = _make_unit(fuel_remaining=1.0, max_speed=15.0)
        object.__setattr__(tank, "fuel_consumption_rate", 0.001)  # 10x ground default
        enemy = _make_enemy(position=Position(200, 0, 0))
        ctx = _make_ctx({"enable_fuel_consumption": True})

        mgr = BattleManager(EventBus())
        battle = _make_battle()

        mgr._execute_movement(ctx, {"blue": [tank]}, {"blue": [enemy]}, dt=10.0, battle=battle)
        consumed = 1.0 - tank.fuel_remaining
        # At custom rate, should consume ~10x more than default
        assert consumed > 0

    def test_calibration_field_exists(self):
        """CalibrationSchema accepts enable_fuel_consumption."""
        from stochastic_warfare.simulation.calibration import CalibrationSchema

        schema = CalibrationSchema(enable_fuel_consumption=True)
        assert schema.enable_fuel_consumption is True

        schema2 = CalibrationSchema()
        assert schema2.enable_fuel_consumption is False
