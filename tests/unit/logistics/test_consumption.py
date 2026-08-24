"""Tests for logistics/consumption.py -- environment-coupled consumption rates."""

from __future__ import annotations

import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.logistics.consumption import (
    ActivityLevel,
    ConsumptionConfig,
    ConsumptionEngine,
    ConsumptionResult,
    EnvironmentConditions,
    GroundState,
)
from stochastic_warfare.logistics.supply_classes import SupplyClass


def _make_engine(seed: int = 42, config: ConsumptionConfig | None = None) -> ConsumptionEngine:
    bus = EventBus()
    rng = RNGManager(seed).get_stream(ModuleId.LOGISTICS)
    return ConsumptionEngine(event_bus=bus, rng=rng, config=config)


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestEnums:
    def test_activity_levels(self) -> None:
        assert ActivityLevel.IDLE == 0
        assert ActivityLevel.COMBAT == 3

    def test_ground_states(self) -> None:
        assert GroundState.DRY == 0
        assert GroundState.MUD == 2
        assert GroundState.ICE == 4


# ---------------------------------------------------------------------------
# Basic consumption
# ---------------------------------------------------------------------------


class TestBasicConsumption:
    def test_food_scales_with_personnel(self) -> None:
        engine = _make_engine()
        r1 = engine.compute_consumption(10, 0, 0.0, int(ActivityLevel.IDLE), 1.0)
        r2 = engine.compute_consumption(20, 0, 0.0, int(ActivityLevel.IDLE), 1.0)
        assert r2.food_kg == pytest.approx(r1.food_kg * 2)

    def test_food_scales_with_time(self) -> None:
        engine = _make_engine()
        r1 = engine.compute_consumption(10, 0, 0.0, int(ActivityLevel.IDLE), 1.0)
        r2 = engine.compute_consumption(10, 0, 0.0, int(ActivityLevel.IDLE), 2.0)
        assert r2.food_kg == pytest.approx(r1.food_kg * 2)

    def test_water_base_rate(self) -> None:
        engine = _make_engine()
        cfg = ConsumptionConfig()
        r = engine.compute_consumption(1, 0, 0.0, int(ActivityLevel.IDLE), 1.0)
        assert r.water_liters == pytest.approx(cfg.base_water_per_person_per_hour)

    def test_fuel_idle_minimal(self) -> None:
        engine = _make_engine()
        r = engine.compute_consumption(0, 1, 100.0, int(ActivityLevel.IDLE), 1.0)
        # Idle multiplier is 0.1 → 100 * 0.1 = 10
        assert r.fuel_liters == pytest.approx(10.0)

    def test_fuel_march_full_rate(self) -> None:
        engine = _make_engine()
        r = engine.compute_consumption(0, 1, 100.0, int(ActivityLevel.MARCH), 1.0)
        # March multiplier is 1.0 → 100
        assert r.fuel_liters == pytest.approx(100.0)

    def test_fuel_combat_elevated(self) -> None:
        engine = _make_engine()
        r = engine.compute_consumption(0, 1, 100.0, int(ActivityLevel.COMBAT), 1.0)
        # Combat multiplier is 1.5 → 150
        assert r.fuel_liters == pytest.approx(150.0)

    def test_ammo_zero_when_idle(self) -> None:
        engine = _make_engine()
        r = engine.compute_consumption(10, 5, 0.0, int(ActivityLevel.IDLE), 1.0)
        assert r.ammo_units == 0.0

    def test_ammo_consumed_in_combat(self) -> None:
        engine = _make_engine()
        r = engine.compute_consumption(10, 5, 0.0, int(ActivityLevel.COMBAT), 1.0)
        # 5 equipment * 3.0 multiplier * 1 hour = 15
        assert r.ammo_units == pytest.approx(15.0)

    def test_medical_base_rate(self) -> None:
        engine = _make_engine()
        cfg = ConsumptionConfig()
        r = engine.compute_consumption(100, 0, 0.0, int(ActivityLevel.IDLE), 1.0)
        expected = cfg.base_medical_per_person_per_hour * 100 * 1.0
        assert r.medical_units == pytest.approx(expected)

    def test_medical_elevated_in_combat(self) -> None:
        engine = _make_engine()
        r_idle = engine.compute_consumption(100, 0, 0.0, int(ActivityLevel.IDLE), 1.0)
        r_combat = engine.compute_consumption(100, 0, 0.0, int(ActivityLevel.COMBAT), 1.0)
        assert r_combat.medical_units == pytest.approx(r_idle.medical_units * 5.0)

    def test_zero_personnel_zero_food(self) -> None:
        engine = _make_engine()
        r = engine.compute_consumption(0, 0, 0.0, int(ActivityLevel.IDLE), 1.0)
        assert r.food_kg == 0.0
        assert r.water_liters == 0.0


# ---------------------------------------------------------------------------
# Environmental coupling
# ---------------------------------------------------------------------------


class TestEnvironmentalEffects:
    def test_hot_weather_increases_water(self) -> None:
        engine = _make_engine()
        env_hot = EnvironmentConditions(temperature_c=40.0)
        env_normal = EnvironmentConditions(temperature_c=20.0)
        r_hot = engine.compute_consumption(10, 0, 0.0, int(ActivityLevel.IDLE), 1.0, env_hot)
        r_normal = engine.compute_consumption(10, 0, 0.0, int(ActivityLevel.IDLE), 1.0, env_normal)
        assert r_hot.water_liters == pytest.approx(r_normal.water_liters * 2.5)

    def test_cold_weather_increases_fuel(self) -> None:
        engine = _make_engine()
        env_cold = EnvironmentConditions(temperature_c=-15.0)
        env_normal = EnvironmentConditions(temperature_c=20.0)
        r_cold = engine.compute_consumption(0, 1, 100.0, int(ActivityLevel.MARCH), 1.0, env_cold)
        r_normal = engine.compute_consumption(0, 1, 100.0, int(ActivityLevel.MARCH), 1.0, env_normal)
        assert r_cold.fuel_liters == pytest.approx(r_normal.fuel_liters * 1.5)

    def test_mud_increases_fuel(self) -> None:
        engine = _make_engine()
        env_mud = EnvironmentConditions(ground_state=int(GroundState.MUD))
        env_dry = EnvironmentConditions(ground_state=int(GroundState.DRY))
        r_mud = engine.compute_consumption(0, 1, 100.0, int(ActivityLevel.MARCH), 1.0, env_mud)
        r_dry = engine.compute_consumption(0, 1, 100.0, int(ActivityLevel.MARCH), 1.0, env_dry)
        assert r_mud.fuel_liters == pytest.approx(r_dry.fuel_liters * 1.8)

    def test_snow_increases_fuel(self) -> None:
        engine = _make_engine()
        env_snow = EnvironmentConditions(ground_state=int(GroundState.SNOW))
        env_dry = EnvironmentConditions(ground_state=int(GroundState.DRY))
        r_snow = engine.compute_consumption(0, 1, 100.0, int(ActivityLevel.MARCH), 1.0, env_snow)
        r_dry = engine.compute_consumption(0, 1, 100.0, int(ActivityLevel.MARCH), 1.0, env_dry)
        assert r_snow.fuel_liters == pytest.approx(r_dry.fuel_liters * 1.4)

    def test_combined_cold_and_mud(self) -> None:
        engine = _make_engine()
        env = EnvironmentConditions(temperature_c=-15.0, ground_state=int(GroundState.MUD))
        r = engine.compute_consumption(0, 1, 100.0, int(ActivityLevel.MARCH), 1.0, env)
        # 100 * 1.0 (march) * 1.8 (mud) * 1.5 (cold) = 270
        assert r.fuel_liters == pytest.approx(270.0)

    def test_default_env_when_none(self) -> None:
        engine = _make_engine()
        # Should not raise
        r = engine.compute_consumption(10, 1, 50.0, int(ActivityLevel.IDLE), 1.0)
        assert r.food_kg > 0


# ---------------------------------------------------------------------------
# Naval fuel consumption
# ---------------------------------------------------------------------------


class TestNavalFuelConsumption:
    def test_cubic_law(self) -> None:
        engine = _make_engine()
        # At max speed, should consume full rate
        fuel = engine.fuel_consumption_naval(
            speed_mps=15.0, dt_hours=1.0,
            max_speed_mps=15.0, fuel_capacity_liters=10000.0,
            design_endurance_hours=100.0,
        )
        # rate = 10000/100 = 100 L/h at max speed, 1 hour
        assert fuel == pytest.approx(100.0)

    def test_half_speed_one_eighth_fuel(self) -> None:
        engine = _make_engine()
        fuel_full = engine.fuel_consumption_naval(
            speed_mps=20.0, dt_hours=1.0,
            max_speed_mps=20.0, fuel_capacity_liters=10000.0,
            design_endurance_hours=100.0,
        )
        fuel_half = engine.fuel_consumption_naval(
            speed_mps=10.0, dt_hours=1.0,
            max_speed_mps=20.0, fuel_capacity_liters=10000.0,
            design_endurance_hours=100.0,
        )
        assert fuel_half == pytest.approx(fuel_full * 0.125)

    def test_zero_speed_zero_fuel(self) -> None:
        engine = _make_engine()
        fuel = engine.fuel_consumption_naval(
            speed_mps=0.0, dt_hours=1.0,
            max_speed_mps=15.0, fuel_capacity_liters=10000.0,
            design_endurance_hours=100.0,
        )
        assert fuel == 0.0

    def test_zero_max_speed_returns_zero(self) -> None:
        engine = _make_engine()
        fuel = engine.fuel_consumption_naval(
            speed_mps=10.0, dt_hours=1.0,
            max_speed_mps=0.0, fuel_capacity_liters=10000.0,
            design_endurance_hours=100.0,
        )
        assert fuel == 0.0

    def test_scales_with_time(self) -> None:
        engine = _make_engine()
        fuel_1h = engine.fuel_consumption_naval(
            speed_mps=15.0, dt_hours=1.0,
            max_speed_mps=15.0, fuel_capacity_liters=10000.0,
            design_endurance_hours=100.0,
        )
        fuel_2h = engine.fuel_consumption_naval(
            speed_mps=15.0, dt_hours=2.0,
            max_speed_mps=15.0, fuel_capacity_liters=10000.0,
            design_endurance_hours=100.0,
        )
        assert fuel_2h == pytest.approx(fuel_1h * 2)


# ---------------------------------------------------------------------------
# ConsumptionResult
# ---------------------------------------------------------------------------


class TestConsumptionResult:
    def test_as_dict_class_i(self) -> None:
        r = ConsumptionResult(food_kg=10.0, water_liters=20.0)
        d = r.as_dict()
        assert int(SupplyClass.CLASS_I) in d
        assert d[int(SupplyClass.CLASS_I)]["ration_mre"] == 10.0
        assert d[int(SupplyClass.CLASS_I)]["water_potable"] == 20.0

    def test_as_dict_excludes_zeros(self) -> None:
        r = ConsumptionResult(food_kg=10.0)
        d = r.as_dict()
        assert int(SupplyClass.CLASS_III) not in d
        assert int(SupplyClass.CLASS_V) not in d

    def test_as_dict_all_classes(self) -> None:
        r = ConsumptionResult(
            food_kg=1.0, water_liters=2.0, fuel_liters=3.0,
            ammo_units=4.0, medical_units=5.0,
        )
        d = r.as_dict()
        assert len(d) == 4  # I, III, V, VIII


# ---------------------------------------------------------------------------
# State protocol
# ---------------------------------------------------------------------------


class TestStateProtocol:
    def test_get_set_state(self) -> None:
        engine = _make_engine()
        state = engine.get_state()
        engine2 = _make_engine()
        engine2.set_state(state)
        assert engine2.get_state() == state


# ---------------------------------------------------------------------------
# Custom config
# ---------------------------------------------------------------------------


class TestCustomConfig:
    def test_custom_food_rate(self) -> None:
        cfg = ConsumptionConfig(base_food_per_person_per_hour=0.2)
        engine = _make_engine(config=cfg)
        r = engine.compute_consumption(1, 0, 0.0, int(ActivityLevel.IDLE), 1.0)
        assert r.food_kg == pytest.approx(0.2)
