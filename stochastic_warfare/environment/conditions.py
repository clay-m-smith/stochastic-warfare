"""Conditions facade: composites all environment sub-engines into domain queries.

This module is a pure aggregator with no internal state.  It queries
sub-engines and assembles composite results for land, air, maritime,
acoustic, and electromagnetic conditions.
"""

from __future__ import annotations

from typing import NamedTuple


from stochastic_warfare.core.types import Meters, Position
from stochastic_warfare.environment.electromagnetic import EMEnvironment, FrequencyBand
from stochastic_warfare.environment.obscurants import ObscurantsEngine
from stochastic_warfare.environment.seasons import GroundState, SeasonsEngine
from stochastic_warfare.environment.sea_state import SeaStateEngine
from stochastic_warfare.environment.time_of_day import TimeOfDayEngine
from stochastic_warfare.environment.underwater_acoustics import (
    SoundVelocityProfile,
    UnderwaterAcousticsEngine,
)
from stochastic_warfare.environment.weather import WeatherEngine, WindVector


# ---------------------------------------------------------------------------
# Composite condition types
# ---------------------------------------------------------------------------


class LandConditions(NamedTuple):
    """Ground-level environmental conditions."""

    visibility: Meters
    trafficability: float  # 0–1
    concealment_modifier: float  # 0–1
    wind: WindVector
    temperature: float  # °C
    precipitation: bool
    ground_state: GroundState
    illumination_lux: float
    nvg_effectiveness: float
    thermal_contrast: float


class AirConditions(NamedTuple):
    """Aviation environmental conditions."""

    visibility: Meters
    cloud_ceiling: Meters
    wind: WindVector
    temperature_at_altitude: float  # °C
    icing_risk: float  # 0–1
    density_altitude: float  # metres
    gps_accuracy: Meters


class MaritimeConditions(NamedTuple):
    """Sea-surface environmental conditions."""

    sea_state_beaufort: int
    wave_height: Meters
    tide_height: Meters
    tidal_current: tuple[float, float]  # (speed, direction)
    sst: float  # °C
    visibility: Meters
    wind: WindVector


class AcousticConditions(NamedTuple):
    """Underwater acoustic conditions."""

    svp: SoundVelocityProfile
    ambient_noise_db: float
    thermocline_depth: float | None
    convergence_zone_ranges: list[Meters]


class EMConditions(NamedTuple):
    """Electromagnetic propagation conditions."""

    hf_quality: float
    radar_refraction: float
    ducting: bool
    gps_accuracy: Meters
    atmospheric_attenuation_db_per_km: float


# ---------------------------------------------------------------------------
# ConditionsEngine
# ---------------------------------------------------------------------------


class ConditionsEngine:
    """Composites all environment sub-engines into domain-specific queries.

    Parameters
    ----------
    weather, time_of_day, seasons, obscurants:
        Required sub-engines.
    sea_state, acoustics, em:
        Optional sub-engines (None for land-only scenarios).
    """

    def __init__(
        self,
        weather: WeatherEngine,
        time_of_day: TimeOfDayEngine,
        seasons: SeasonsEngine,
        obscurants: ObscurantsEngine,
        sea_state: SeaStateEngine | None = None,
        acoustics: UnderwaterAcousticsEngine | None = None,
        em: EMEnvironment | None = None,
    ) -> None:
        self._weather = weather
        self._time_of_day = time_of_day
        self._seasons = seasons
        self._obscurants = obscurants
        self._sea_state = sea_state
        self._acoustics = acoustics
        self._em = em

    # ------------------------------------------------------------------
    # Domain queries
    # ------------------------------------------------------------------

    def land(self, pos: Position, lat: float, lon: float) -> LandConditions:
        """Ground-level conditions at *pos*."""
        wx = self._weather.current
        illum = self._time_of_day.illumination_at(lat, lon)
        te = self._time_of_day.thermal_environment(lat, lon)
        nvg = self._time_of_day.nvg_effectiveness(lat, lon)
        sc = self._seasons.current
        vis = self._obscurants.visibility_at(pos)
        opacity = self._obscurants.opacity_at(pos)

        return LandConditions(
            visibility=vis,
            trafficability=sc.ground_trafficability,
            concealment_modifier=1.0 - opacity.visual,
            wind=wx.wind,
            temperature=wx.temperature,
            precipitation=wx.precipitation_rate > 0,
            ground_state=sc.ground_state,
            illumination_lux=illum.ambient_lux,
            nvg_effectiveness=nvg,
            thermal_contrast=te.thermal_contrast,
        )

    def air(
        self, pos: Position, altitude: Meters, lat: float, lon: float
    ) -> AirConditions:
        """Aviation conditions at *altitude* above *pos*."""
        wx = self._weather.current
        temp_alt = self._weather.temperature_at_altitude(altitude)
        density = self._weather.atmospheric_density(altitude)
        pressure = self._weather.pressure_at_altitude(altitude)

        # ISA standard density at altitude
        isa_temp = 15.0 - 0.0065 * altitude
        isa_density = 1.225 * ((isa_temp + 273.15) / 288.15) ** 4.2561

        # Density altitude: altitude where ISA density matches actual
        # Approximation: DA = altitude + 120 * (temp - isa_temp)
        density_alt = altitude + 120 * (temp_alt - isa_temp)

        # Icing risk: moderate in clouds with temp 0 to -20°C
        icing = 0.0
        if -20 < temp_alt < 0 and wx.cloud_cover > 0.7:
            icing = min(1.0, wx.humidity * abs(temp_alt) / 20.0)

        gps = self._em.gps_accuracy() if self._em else 5.0

        return AirConditions(
            visibility=wx.visibility,
            cloud_ceiling=wx.cloud_ceiling,
            wind=wx.wind,
            temperature_at_altitude=temp_alt,
            icing_risk=icing,
            density_altitude=density_alt,
            gps_accuracy=gps,
        )

    def maritime(self, lat: float, lon: float) -> MaritimeConditions:
        """Sea-surface conditions."""
        if self._sea_state is None:
            raise RuntimeError("No sea state engine configured")

        wx = self._weather.current
        sea = self._sea_state.current

        return MaritimeConditions(
            sea_state_beaufort=sea.beaufort_scale,
            wave_height=sea.significant_wave_height,
            tide_height=sea.tide_height,
            tidal_current=(sea.tidal_current_speed, sea.tidal_current_direction),
            sst=sea.sst,
            visibility=wx.visibility,
            wind=wx.wind,
        )

    def acoustic(self) -> AcousticConditions:
        """Underwater acoustic conditions."""
        if self._acoustics is None:
            raise RuntimeError("No acoustics engine configured")

        cond = self._acoustics.conditions
        czs = self._acoustics.convergence_zone_ranges(100.0)

        return AcousticConditions(
            svp=cond.svp,
            ambient_noise_db=cond.ambient_noise_level,
            thermocline_depth=cond.thermocline_depth,
            convergence_zone_ranges=czs,
        )

    def electromagnetic(
        self, band: FrequencyBand | None = None
    ) -> EMConditions:
        """Electromagnetic propagation conditions."""
        if self._em is None:
            raise RuntimeError("No EM engine configured")

        hf_q = self._em.hf_propagation_quality()
        k = self._em.effective_earth_radius_factor()
        prop = self._em.propagation(
            band if band is not None else FrequencyBand.UHF, 10.0
        )
        gps = self._em.gps_accuracy()

        return EMConditions(
            hf_quality=hf_q,
            radar_refraction=k,
            ducting=prop.ducting_possible,
            gps_accuracy=gps,
            atmospheric_attenuation_db_per_km=prop.atmospheric_attenuation / 10.0,
        )

    # ------------------------------------------------------------------
    # State persistence (stateless aggregator)
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        return {}

    def set_state(self, state: dict) -> None:
        pass
