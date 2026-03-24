"""Supply consumption modeling — environment-coupled rates per unit.

Consumption rates depend on activity level (idle/march/combat/defense),
environmental conditions (temperature, ground state), and unit composition
(personnel count, equipment types).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.logistics.supply_classes import SupplyClass

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums & config
# ---------------------------------------------------------------------------


class ActivityLevel(enum.IntEnum):
    """Unit activity affecting consumption rates."""

    IDLE = 0
    DEFENSE = 1
    MARCH = 2
    COMBAT = 3


class GroundState(enum.IntEnum):
    """Ground surface condition affecting vehicle fuel consumption."""

    DRY = 0
    WET = 1
    MUD = 2
    SNOW = 3
    ICE = 4


class ConsumptionConfig(BaseModel):
    """Tuning parameters for consumption rates."""

    # Class I — food & water (per person per hour)
    base_food_per_person_per_hour: float = 0.104  # ~2.5 kg/day
    base_water_per_person_per_hour: float = 0.167  # ~4 L/day temperate
    hot_weather_water_multiplier: float = 2.5  # desert: ~10 L/day
    hot_weather_threshold_c: float = 35.0

    # Class III — fuel
    idle_fuel_multiplier: float = 0.1
    march_fuel_multiplier: float = 1.0
    combat_fuel_multiplier: float = 1.5
    defense_fuel_multiplier: float = 0.3
    cold_fuel_heating_multiplier: float = 1.5
    cold_weather_threshold_c: float = -10.0
    mud_fuel_multiplier: float = 1.8
    snow_fuel_multiplier: float = 1.4

    # Class V — ammunition
    combat_ammo_multiplier: float = 3.0
    defense_ammo_multiplier: float = 1.0
    march_ammo_multiplier: float = 0.0
    idle_ammo_multiplier: float = 0.0

    # Class VIII — medical
    combat_medical_multiplier: float = 5.0
    base_medical_per_person_per_hour: float = 0.001

    # Naval — cubic fuel law
    naval_fuel_exponent: float = 3.0


# ---------------------------------------------------------------------------
# Environment conditions (passed as parameter — DI pattern)
# ---------------------------------------------------------------------------


@dataclass
class EnvironmentConditions:
    """Snapshot of environmental conditions affecting logistics."""

    temperature_c: float = 20.0
    ground_state: int = 0  # GroundState value
    sea_state: int = 2
    visibility_m: float = 10000.0
    wind_speed_mps: float = 5.0
    wind_direction_rad: float = 0.0


# ---------------------------------------------------------------------------
# Consumption result
# ---------------------------------------------------------------------------


@dataclass
class ConsumptionResult:
    """Itemized consumption for one unit over one time step."""

    food_kg: float = 0.0
    water_liters: float = 0.0
    fuel_liters: float = 0.0
    ammo_units: float = 0.0
    medical_units: float = 0.0

    def as_dict(self) -> dict[int, dict[str, float]]:
        """Return consumption keyed by supply class and default item ID."""
        result: dict[int, dict[str, float]] = {}
        if self.food_kg > 0:
            result[int(SupplyClass.CLASS_I)] = {"ration_mre": self.food_kg}
        if self.water_liters > 0:
            result.setdefault(int(SupplyClass.CLASS_I), {})["water_potable"] = (
                self.water_liters
            )
        if self.fuel_liters > 0:
            result[int(SupplyClass.CLASS_III)] = {"fuel_diesel": self.fuel_liters}
        if self.ammo_units > 0:
            result[int(SupplyClass.CLASS_V)] = {"ammo_generic": self.ammo_units}
        if self.medical_units > 0:
            result[int(SupplyClass.CLASS_VIII)] = {
                "medical_kit_basic": self.medical_units
            }
        return result


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ConsumptionEngine:
    """Compute per-unit supply consumption rates.

    Parameters
    ----------
    event_bus : EventBus
        For future event publishing.
    rng : numpy.random.Generator
        Deterministic PRNG stream.
    config : ConsumptionConfig | None
        Tuning parameters.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: ConsumptionConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or ConsumptionConfig()

    def compute_consumption(
        self,
        personnel_count: int,
        equipment_count: int,
        base_fuel_rate_per_hour: float,
        activity: int,
        dt_hours: float,
        env: EnvironmentConditions | None = None,
    ) -> ConsumptionResult:
        """Compute consumption for a unit over *dt_hours*.

        Parameters
        ----------
        personnel_count:
            Number of active personnel.
        equipment_count:
            Number of major equipment items (vehicles, aircraft, etc.).
        base_fuel_rate_per_hour:
            Base fuel consumption in liters/hour for the unit's equipment.
        activity:
            ``ActivityLevel`` value.
        dt_hours:
            Time step in hours.
        env:
            Environmental conditions snapshot.
        """
        if env is None:
            env = EnvironmentConditions()
        cfg = self._config

        # -- Class I: food --
        food = cfg.base_food_per_person_per_hour * personnel_count * dt_hours

        # -- Class I: water (temperature-coupled) --
        water_mult = 1.0
        if env.temperature_c >= cfg.hot_weather_threshold_c:
            water_mult = cfg.hot_weather_water_multiplier
        water = cfg.base_water_per_person_per_hour * personnel_count * dt_hours * water_mult

        # -- Class III: fuel (activity + ground state + cold) --
        activity_mult = {
            int(ActivityLevel.IDLE): cfg.idle_fuel_multiplier,
            int(ActivityLevel.DEFENSE): cfg.defense_fuel_multiplier,
            int(ActivityLevel.MARCH): cfg.march_fuel_multiplier,
            int(ActivityLevel.COMBAT): cfg.combat_fuel_multiplier,
        }.get(activity, cfg.idle_fuel_multiplier)

        ground_mult = 1.0
        if env.ground_state == int(GroundState.MUD):
            ground_mult = cfg.mud_fuel_multiplier
        elif env.ground_state == int(GroundState.SNOW):
            ground_mult = cfg.snow_fuel_multiplier

        cold_mult = 1.0
        if env.temperature_c <= cfg.cold_weather_threshold_c:
            cold_mult = cfg.cold_fuel_heating_multiplier

        fuel = base_fuel_rate_per_hour * activity_mult * ground_mult * cold_mult * dt_hours

        # -- Class V: ammo (activity-driven) --
        ammo_mult = {
            int(ActivityLevel.IDLE): cfg.idle_ammo_multiplier,
            int(ActivityLevel.DEFENSE): cfg.defense_ammo_multiplier,
            int(ActivityLevel.MARCH): cfg.march_ammo_multiplier,
            int(ActivityLevel.COMBAT): cfg.combat_ammo_multiplier,
        }.get(activity, cfg.idle_ammo_multiplier)
        # Base rate: 1 unit per equipment per hour when active
        ammo = equipment_count * ammo_mult * dt_hours

        # -- Class VIII: medical --
        medical_mult = 1.0
        if activity == int(ActivityLevel.COMBAT):
            medical_mult = cfg.combat_medical_multiplier
        medical = cfg.base_medical_per_person_per_hour * personnel_count * dt_hours * medical_mult

        return ConsumptionResult(
            food_kg=food,
            water_liters=water,
            fuel_liters=fuel,
            ammo_units=ammo,
            medical_units=medical,
        )

    def fuel_consumption_naval(
        self,
        speed_mps: float,
        dt_hours: float,
        max_speed_mps: float,
        fuel_capacity_liters: float,
        design_endurance_hours: float,
    ) -> float:
        """Compute naval fuel consumption using cubic speed law.

        Fuel rate proportional to ``(speed / max_speed)^3``.

        Returns liters consumed in *dt_hours*.
        """
        if max_speed_mps <= 0 or design_endurance_hours <= 0:
            return 0.0
        # At max speed, full capacity consumed in design_endurance_hours
        max_rate = fuel_capacity_liters / design_endurance_hours
        speed_fraction = min(speed_mps / max_speed_mps, 1.0)
        exponent = self._config.naval_fuel_exponent
        rate = max_rate * (speed_fraction ** exponent)
        return rate * dt_hours

    def get_state(self) -> dict:
        """Serialize for checkpoint."""
        return {}

    def set_state(self, state: dict) -> None:
        """Restore from checkpoint."""
        pass
