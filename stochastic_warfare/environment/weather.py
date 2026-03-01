"""Stochastic weather model driven by Markov chains.

Weather state transitions are evaluated at configurable intervals.
Temperature follows a diurnal sinusoidal cycle.  Wind uses an
Ornstein-Uhlenbeck mean-reverting process.  The model conditions on
climate zone, latitude, and month — it does NOT import the seasons module.
"""

from __future__ import annotations

import enum
import math
from typing import NamedTuple

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.types import Meters


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class WeatherState(enum.IntEnum):
    """Discrete weather state for Markov transitions."""

    CLEAR = 0
    PARTLY_CLOUDY = 1
    OVERCAST = 2
    LIGHT_RAIN = 3
    HEAVY_RAIN = 4
    SNOW = 5
    FOG = 6
    STORM = 7


class ClimateZone(enum.IntEnum):
    """Climate classification."""

    TROPICAL = 0
    SUBTROPICAL = 1
    TEMPERATE = 2
    CONTINENTAL = 3
    SUBARCTIC = 4
    ARCTIC = 5
    ARID = 6
    SEMI_ARID = 7
    MEDITERRANEAN = 8
    MONSOON = 9


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


class WindVector(NamedTuple):
    """Wind measurement."""

    speed: float  # m/s
    direction: float  # radians, from-direction (0=north wind blows from north)
    gust: float  # m/s peak gust


class WeatherConditions(NamedTuple):
    """Composite weather snapshot."""

    state: WeatherState
    temperature: float  # °C
    wind: WindVector
    cloud_cover: float  # 0–1
    cloud_ceiling: float  # metres AGL
    humidity: float  # 0–1
    pressure: float  # hPa
    precipitation_rate: float  # mm/hr
    visibility: float  # metres


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class WeatherConfig(BaseModel):
    """Weather engine parameters."""

    climate_zone: ClimateZone = ClimateZone.TEMPERATE
    latitude: float = 45.0
    initial_state: WeatherState = WeatherState.CLEAR
    initial_temperature: float = 20.0
    transition_interval_seconds: float = 3600.0


# ---------------------------------------------------------------------------
# Transition matrices (simplified)
# ---------------------------------------------------------------------------

# Default temperate transition matrix (summer-ish)
_TEMPERATE_TRANSITIONS = np.array([
    # CLEAR  PC    OVC   LR    HR    SNOW  FOG   STORM
    [0.60, 0.25, 0.08, 0.03, 0.01, 0.00, 0.02, 0.01],  # CLEAR
    [0.20, 0.40, 0.25, 0.08, 0.02, 0.00, 0.03, 0.02],  # PARTLY_CLOUDY
    [0.05, 0.20, 0.35, 0.20, 0.10, 0.02, 0.05, 0.03],  # OVERCAST
    [0.05, 0.10, 0.20, 0.35, 0.15, 0.03, 0.05, 0.07],  # LIGHT_RAIN
    [0.02, 0.05, 0.15, 0.20, 0.30, 0.05, 0.03, 0.20],  # HEAVY_RAIN
    [0.02, 0.05, 0.15, 0.10, 0.05, 0.50, 0.08, 0.05],  # SNOW
    [0.15, 0.20, 0.20, 0.10, 0.02, 0.03, 0.28, 0.02],  # FOG
    [0.05, 0.10, 0.25, 0.15, 0.20, 0.03, 0.02, 0.20],  # STORM
], dtype=np.float64)

# Weather-state-dependent parameters
_STATE_PARAMS: dict[WeatherState, dict] = {
    WeatherState.CLEAR: {"cloud": 0.1, "ceiling": 10000, "humidity": 0.35, "precip": 0.0, "vis": 50000, "wind_mean": 3.0},
    WeatherState.PARTLY_CLOUDY: {"cloud": 0.4, "ceiling": 5000, "humidity": 0.45, "precip": 0.0, "vis": 30000, "wind_mean": 5.0},
    WeatherState.OVERCAST: {"cloud": 0.9, "ceiling": 2000, "humidity": 0.65, "precip": 0.0, "vis": 15000, "wind_mean": 6.0},
    WeatherState.LIGHT_RAIN: {"cloud": 0.95, "ceiling": 1500, "humidity": 0.80, "precip": 2.0, "vis": 8000, "wind_mean": 7.0},
    WeatherState.HEAVY_RAIN: {"cloud": 1.0, "ceiling": 500, "humidity": 0.95, "precip": 15.0, "vis": 2000, "wind_mean": 12.0},
    WeatherState.SNOW: {"cloud": 1.0, "ceiling": 800, "humidity": 0.85, "precip": 5.0, "vis": 1000, "wind_mean": 5.0},
    WeatherState.FOG: {"cloud": 1.0, "ceiling": 100, "humidity": 0.98, "precip": 0.0, "vis": 200, "wind_mean": 1.0},
    WeatherState.STORM: {"cloud": 1.0, "ceiling": 300, "humidity": 0.90, "precip": 25.0, "vis": 1500, "wind_mean": 20.0},
}

# Monthly mean temperatures by climate zone (rough approximation)
_MONTHLY_TEMPS: dict[ClimateZone, list[float]] = {
    ClimateZone.TROPICAL: [27, 27, 28, 28, 28, 27, 27, 27, 27, 27, 27, 27],
    ClimateZone.SUBTROPICAL: [12, 14, 17, 21, 25, 28, 30, 30, 27, 22, 17, 13],
    ClimateZone.TEMPERATE: [2, 3, 7, 12, 17, 21, 23, 22, 18, 12, 7, 3],
    ClimateZone.CONTINENTAL: [-12, -8, -1, 8, 15, 20, 22, 20, 14, 6, -2, -9],
    ClimateZone.SUBARCTIC: [-25, -22, -15, -5, 5, 12, 15, 13, 7, -3, -15, -22],
    ClimateZone.ARCTIC: [-30, -28, -25, -15, -2, 5, 8, 6, 1, -10, -22, -28],
    ClimateZone.ARID: [15, 18, 22, 27, 32, 37, 40, 39, 35, 28, 21, 16],
    ClimateZone.SEMI_ARID: [8, 10, 15, 20, 25, 30, 33, 32, 28, 20, 14, 9],
    ClimateZone.MEDITERRANEAN: [10, 11, 13, 16, 20, 25, 28, 28, 24, 19, 14, 11],
    ClimateZone.MONSOON: [25, 27, 29, 31, 31, 30, 29, 29, 29, 28, 27, 25],
}

_DIURNAL_AMPLITUDE: dict[ClimateZone, float] = {
    ClimateZone.TROPICAL: 4.0, ClimateZone.SUBTROPICAL: 7.0,
    ClimateZone.TEMPERATE: 8.0, ClimateZone.CONTINENTAL: 12.0,
    ClimateZone.SUBARCTIC: 10.0, ClimateZone.ARCTIC: 5.0,
    ClimateZone.ARID: 15.0, ClimateZone.SEMI_ARID: 12.0,
    ClimateZone.MEDITERRANEAN: 8.0, ClimateZone.MONSOON: 5.0,
}


# ---------------------------------------------------------------------------
# WeatherEngine
# ---------------------------------------------------------------------------


class WeatherEngine:
    """Stochastic weather simulation.

    Parameters
    ----------
    config:
        Weather parameters.
    clock:
        Simulation clock.
    rng:
        Numpy random generator (from the ENVIRONMENT stream).
    """

    def __init__(
        self,
        config: WeatherConfig,
        clock: SimulationClock,
        rng: np.random.Generator,
    ) -> None:
        self._config = config
        self._clock = clock
        self._rng = rng

        self._state = config.initial_state
        self._temperature = config.initial_temperature
        self._wind_speed = _STATE_PARAMS[self._state]["wind_mean"]
        self._wind_direction = self._rng.uniform(0, 2 * math.pi)
        self._pressure = 1013.25
        self._time_since_transition = 0.0

        self._transition_matrix = _TEMPERATE_TRANSITIONS.copy()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def current(self) -> WeatherConditions:
        """Current weather snapshot."""
        params = _STATE_PARAMS[self._state]
        return WeatherConditions(
            state=self._state,
            temperature=self._temperature,
            wind=WindVector(self._wind_speed, self._wind_direction,
                           self._wind_speed * 1.3),
            cloud_cover=params["cloud"],
            cloud_ceiling=params["ceiling"],
            humidity=params["humidity"],
            pressure=self._pressure,
            precipitation_rate=params["precip"],
            visibility=params["vis"],
        )

    def update(self, dt_seconds: float) -> None:
        """Advance weather by *dt_seconds*."""
        self._time_since_transition += dt_seconds

        # Markov transition
        if self._time_since_transition >= self._config.transition_interval_seconds:
            self._time_since_transition = 0.0
            probs = self._transition_matrix[self._state]
            self._state = WeatherState(
                self._rng.choice(len(WeatherState), p=probs)
            )

        # Diurnal temperature
        month_idx = self._clock.month - 1
        temps = _MONTHLY_TEMPS.get(self._config.climate_zone, _MONTHLY_TEMPS[ClimateZone.TEMPERATE])
        daily_mean = temps[month_idx]
        amp = _DIURNAL_AMPLITUDE.get(self._config.climate_zone, 8.0)

        # Approximate local hour from longitude
        local_hour = (self._clock.hour_utc + self._config.latitude / 15.0) % 24.0
        # Peak at 14:00 local, trough at ~06:00
        phase = 2 * math.pi * (local_hour - 14.0) / 24.0
        self._temperature = daily_mean + amp * math.cos(phase)

        # O-U wind process
        wind_mean = _STATE_PARAMS[self._state]["wind_mean"]
        theta = 0.1  # mean-reversion rate
        sigma = 1.5  # volatility
        dt_norm = min(dt_seconds / 3600.0, 1.0)
        self._wind_speed = max(0.0,
            self._wind_speed
            + theta * (wind_mean - self._wind_speed) * dt_norm
            + sigma * math.sqrt(dt_norm) * self._rng.standard_normal()
        )
        # Random walk for direction
        self._wind_direction = (
            self._wind_direction + 0.05 * self._rng.standard_normal()
        ) % (2 * math.pi)

    def temperature_at_altitude(self, altitude: Meters) -> float:
        """ISA lapse rate temperature at *altitude* metres."""
        return self._temperature - 0.0065 * altitude

    def atmospheric_density(self, altitude: Meters) -> float:
        """Atmospheric density (kg/m³) at *altitude* using ISA + ideal gas."""
        T = self.temperature_at_altitude(altitude) + 273.15
        p = self.pressure_at_altitude(altitude)
        R = 287.05  # specific gas constant for dry air
        return (p * 100) / (R * T)

    def pressure_at_altitude(self, altitude: Meters) -> float:
        """Pressure (hPa) at *altitude* using barometric formula."""
        T0 = self._temperature + 273.15
        L = 0.0065  # lapse rate K/m
        g = 9.80665
        M = 0.0289644  # molar mass dry air
        R = 8.31447
        if L * altitude >= T0:
            return 0.01  # clamp near-zero
        return self._pressure * ((T0 - L * altitude) / T0) ** (g * M / (R * L))

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        return {
            "state": int(self._state),
            "temperature": self._temperature,
            "wind_speed": self._wind_speed,
            "wind_direction": self._wind_direction,
            "pressure": self._pressure,
            "time_since_transition": self._time_since_transition,
        }

    def set_state(self, state: dict) -> None:
        self._state = WeatherState(state["state"])
        self._temperature = state["temperature"]
        self._wind_speed = state["wind_speed"]
        self._wind_direction = state["wind_direction"]
        self._pressure = state["pressure"]
        self._time_since_transition = state["time_since_transition"]
