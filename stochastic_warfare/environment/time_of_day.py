"""Illumination, thermal environment, and NVG effectiveness models.

Combines solar and lunar position with weather to produce ambient light
levels, thermal contrast, and NVG performance estimates.
"""

from __future__ import annotations

import math
from typing import NamedTuple

from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.environment.astronomy import AstronomyEngine
from stochastic_warfare.environment.weather import WeatherEngine


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


class IlluminationLevel(NamedTuple):
    """Ambient light conditions at a location."""

    ambient_lux: float
    solar_contribution: float
    lunar_contribution: float
    artificial_contribution: float
    is_day: bool
    twilight_stage: str | None  # "civil", "nautical", "astronomical", or None


class ThermalEnvironment(NamedTuple):
    """Thermal imaging conditions."""

    thermal_contrast: float  # 0–1 (1 = high contrast)
    background_temperature: float  # °C
    crossover_in_hours: float  # hours until next thermal crossover


# ---------------------------------------------------------------------------
# TimeOfDayEngine
# ---------------------------------------------------------------------------


class TimeOfDayEngine:
    """Derives illumination and thermal conditions from astronomy + weather.

    Parameters
    ----------
    astronomy:
        Astronomy engine for solar/lunar positions.
    weather:
        Weather engine for cloud cover and temperature.
    clock:
        Simulation clock.
    """

    def __init__(
        self,
        astronomy: AstronomyEngine,
        weather: WeatherEngine,
        clock: SimulationClock,
    ) -> None:
        self._astronomy = astronomy
        self._weather = weather
        self._clock = clock

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def illumination_at(self, lat: float, lon: float) -> IlluminationLevel:
        """Compute illumination conditions at *lat/lon*."""
        solar = self._astronomy.solar_position(lat, lon)
        lunar = self._astronomy.lunar_position(lat, lon)
        phase = self._astronomy.lunar_phase()
        cloud = self._weather.current.cloud_cover

        # Solar contribution (lux)
        if solar.elevation > 0:
            # Rough model: 100k lux at zenith, scaled by sin(elevation)
            solar_lux = 100_000.0 * math.sin(solar.elevation) * (1 - 0.7 * cloud)
            is_day = True
            twilight = None
        else:
            solar_lux = 0.0
            is_day = False
            el_deg = math.degrees(solar.elevation)
            if el_deg > -6:
                twilight = "civil"
                solar_lux = 3.0 * (1 + el_deg / 6) * (1 - 0.5 * cloud)
            elif el_deg > -12:
                twilight = "nautical"
                solar_lux = 0.01
            elif el_deg > -18:
                twilight = "astronomical"
                solar_lux = 0.001
            else:
                twilight = None

        # Lunar contribution
        if lunar.elevation > 0:
            lunar_lux = (
                0.25 * phase.illumination_fraction
                * math.sin(max(0, lunar.elevation))
                * (1 - 0.8 * cloud)
            )
        else:
            lunar_lux = 0.0

        ambient = max(0.001, solar_lux + lunar_lux)

        return IlluminationLevel(
            ambient_lux=ambient,
            solar_contribution=solar_lux,
            lunar_contribution=lunar_lux,
            artificial_contribution=0.0,
            is_day=is_day,
            twilight_stage=twilight,
        )

    def thermal_environment(self, lat: float, lon: float) -> ThermalEnvironment:
        """Thermal imaging conditions at *lat/lon*."""
        temp = self._weather.current.temperature
        solar = self._astronomy.solar_position(lat, lon)

        # Thermal contrast: high during day (sun heating), low near crossover
        # Crossover occurs ~30 min after sunrise/sunset
        el_deg = math.degrees(solar.elevation)
        if el_deg > 10:
            contrast = min(1.0, el_deg / 45.0)
        elif el_deg < -10:
            contrast = 0.6  # radiative cooling provides contrast at night
        else:
            # Near crossover
            contrast = max(0.1, abs(el_deg) / 10.0 * 0.5)

        # Estimate hours to next crossover (rough)
        if -5 < el_deg < 5:
            crossover = 0.0
        elif el_deg > 0:
            # Estimate hours to sunset
            day_len = self._astronomy.day_length_hours(lat, lon)
            local_hour = (self._clock.hour_utc + lon / 15.0) % 24.0
            crossover = max(0, (12 + day_len / 2) - local_hour)
        else:
            # Estimate hours to sunrise
            day_len = self._astronomy.day_length_hours(lat, lon)
            local_hour = (self._clock.hour_utc + lon / 15.0) % 24.0
            crossover = max(0, (12 - day_len / 2) - local_hour)
            if crossover < 0:
                crossover += 24.0

        return ThermalEnvironment(
            thermal_contrast=contrast,
            background_temperature=temp,
            crossover_in_hours=crossover,
        )

    def nvg_effectiveness(self, lat: float, lon: float) -> float:
        """NVG effectiveness (0–1) based on ambient light and fog."""
        illum = self.illumination_at(lat, lon)
        lux = illum.ambient_lux

        # Sigmoid response to log(lux)
        # NVGs need some starlight/moonlight to amplify (> ~0.001 lux)
        # Peak effectiveness ~0.01–1.0 lux, saturation above
        if lux <= 0.0001:
            base = 0.05
        else:
            x = math.log10(lux) + 2  # shift so 0.01 lux → x=0
            base = 1.0 / (1.0 + math.exp(-2 * x))

        # Fog degrades NVG
        vis = self._weather.current.visibility
        fog_factor = min(1.0, vis / 5000.0)

        return base * fog_factor

    def shadow_azimuth(self, lat: float, lon: float) -> float | None:
        """Direction of shadows (opposite of solar azimuth), or None at night."""
        solar = self._astronomy.solar_position(lat, lon)
        if solar.elevation <= 0:
            return None
        return (solar.azimuth + math.pi) % (2 * math.pi)

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        return {}  # stateless — derives from sub-engines

    def set_state(self, state: dict) -> None:
        pass
