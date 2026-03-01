"""Environment visualization: illumination timeline, tidal curve, weather, SVP.

Run: python scripts/visualize/environment_viz.py
Requires matplotlib (dev dependency).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np

from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.environment.astronomy import AstronomyEngine
from stochastic_warfare.environment.sea_state import SeaStateConfig, SeaStateEngine
from stochastic_warfare.environment.time_of_day import TimeOfDayEngine
from stochastic_warfare.environment.underwater_acoustics import UnderwaterAcousticsEngine
from stochastic_warfare.environment.weather import ClimateZone, WeatherConfig, WeatherEngine


def main() -> None:
    import matplotlib.pyplot as plt

    start = datetime(2020, 6, 21, 0, 0, tzinfo=timezone.utc)
    clock = SimulationClock(start, timedelta(hours=1))
    rng = RNGManager(42)
    rng_env = rng.get_stream(ModuleId.ENVIRONMENT)

    weather = WeatherEngine(
        WeatherConfig(climate_zone=ClimateZone.TEMPERATE, latitude=45.0),
        clock, rng_env,
    )
    astro = AstronomyEngine(clock)
    tod = TimeOfDayEngine(astro, weather, clock)
    sea = SeaStateEngine(SeaStateConfig(), clock, astro, weather,
                         rng.get_stream(ModuleId.TERRAIN))
    acoustics = UnderwaterAcousticsEngine(sea, clock, rng.get_stream(ModuleId.CORE))

    hours = list(range(48))
    lux_vals, tide_vals, temp_vals, wx_states = [], [], [], []

    for h in hours:
        weather.update(3600)
        sea.update(3600)
        clock.advance()

        illum = tod.illumination_at(45.0, 0.0)
        lux_vals.append(max(0.001, illum.ambient_lux))
        tide_vals.append(sea.current.tide_height)
        temp_vals.append(weather.current.temperature)
        wx_states.append(weather.current.state.name)

    # SVP at current time
    svp = acoustics.svp_at(1000.0)

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    # Illumination (log scale)
    ax = axes[0, 0]
    ax.semilogy(hours, lux_vals)
    ax.set_title("Illumination (48h)")
    ax.set_xlabel("Hour")
    ax.set_ylabel("Lux (log)")
    ax.grid(True, alpha=0.3)

    # Tidal curve
    ax = axes[0, 1]
    ax.plot(hours, tide_vals)
    ax.set_title("Tidal Height (48h)")
    ax.set_xlabel("Hour")
    ax.set_ylabel("Height (m)")
    ax.grid(True, alpha=0.3)

    # Temperature + weather state
    ax = axes[1, 0]
    ax.plot(hours, temp_vals, "r-")
    ax.set_title("Temperature + Weather State (48h)")
    ax.set_xlabel("Hour")
    ax.set_ylabel("°C")
    for i, state in enumerate(wx_states):
        if i % 4 == 0:
            ax.annotate(state, (hours[i], temp_vals[i]), fontsize=6, rotation=45)
    ax.grid(True, alpha=0.3)

    # SVP
    ax = axes[1, 1]
    ax.plot(svp.velocities, -svp.depths)
    ax.set_title("Sound Velocity Profile")
    ax.set_xlabel("Velocity (m/s)")
    ax.set_ylabel("Depth (m)")
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig("environment_viz.png", dpi=150)
    plt.show()
    print("Saved environment_viz.png")


if __name__ == "__main__":
    main()
