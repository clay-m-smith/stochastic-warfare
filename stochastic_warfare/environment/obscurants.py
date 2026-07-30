"""Obscurants model: smoke, dust, and fog.

Each obscurant cloud is tracked as a centre + radius + density that drifts
with wind, expands over time, and decays exponentially.  Different obscurant
types block different spectral bands.
"""

from __future__ import annotations

import enum
import math
from typing import Any, NamedTuple

import numpy as np

from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.types import Meters, Position
from stochastic_warfare.environment.weather import WeatherEngine
from stochastic_warfare.environment.time_of_day import TimeOfDayEngine


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class ObscurantType(enum.IntEnum):
    """Obscurant categories."""

    SMOKE = 0
    SMOKE_MULTISPECTRAL = 1
    DUST = 2
    FOG_RADIATION = 3
    FOG_ADVECTION = 4
    FOG_SEA = 5


class SpectralBlocking(NamedTuple):
    """Opacity across spectral bands (0–1 each)."""

    visual: float
    thermal: float
    radar: float


# Spectral blocking by type at full density
_SPECTRAL_TABLE: dict[ObscurantType, SpectralBlocking] = {
    ObscurantType.SMOKE: SpectralBlocking(0.9, 0.1, 0.0),
    ObscurantType.SMOKE_MULTISPECTRAL: SpectralBlocking(0.9, 0.8, 0.3),
    ObscurantType.DUST: SpectralBlocking(0.7, 0.5, 0.3),
    ObscurantType.FOG_RADIATION: SpectralBlocking(0.9, 0.6, 0.0),
    ObscurantType.FOG_ADVECTION: SpectralBlocking(0.9, 0.6, 0.0),
    ObscurantType.FOG_SEA: SpectralBlocking(0.9, 0.6, 0.0),
}


def _cloud_prefix(cloud_type: ObscurantType) -> str:
    if cloud_type in {
        ObscurantType.SMOKE,
        ObscurantType.SMOKE_MULTISPECTRAL,
    }:
        return "smoke"
    if cloud_type is ObscurantType.DUST:
        return "dust"
    return "fog"


# ---------------------------------------------------------------------------
# Internal cloud representation
# ---------------------------------------------------------------------------


class _Cloud:
    """Internal representation of a single obscurant cloud."""

    def __init__(
        self,
        cloud_id: str,
        cloud_type: ObscurantType,
        center_e: float,
        center_n: float,
        radius: float,
        density: float,
    ) -> None:
        self.cloud_id = cloud_id
        self.cloud_type = cloud_type
        self.center_e = center_e
        self.center_n = center_n
        self.radius = radius
        self.density = density
        self.age_seconds = 0.0


# ---------------------------------------------------------------------------
# ObscurantsEngine
# ---------------------------------------------------------------------------


class ObscurantsEngine:
    """Manages obscurant clouds with drift, dispersion, and dissipation.

    Parameters
    ----------
    weather:
        Weather engine (wind for drift, humidity for fog).
    time_of_day:
        Time-of-day engine (illumination for fog formation).
    clock:
        Simulation clock.
    rng:
        Numpy random generator.
    """

    def __init__(
        self,
        weather: WeatherEngine,
        time_of_day: TimeOfDayEngine,
        clock: SimulationClock,
        rng: np.random.Generator,
    ) -> None:
        self._weather = weather
        self._time_of_day = time_of_day
        self._clock = clock
        self._rng = rng
        self._clouds: dict[str, _Cloud] = {}
        self._next_cloud_sequence = 1

    def _allocate_cloud_id(self, prefix: str) -> str:
        cloud_id = f"{prefix}_{self._next_cloud_sequence:08d}"
        self._next_cloud_sequence += 1
        return cloud_id

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def deploy_smoke(
        self, center: Position, radius: Meters, multispectral: bool = False
    ) -> str:
        """Deploy a smoke cloud.  Returns the cloud ID."""
        ctype = (
            ObscurantType.SMOKE_MULTISPECTRAL if multispectral
            else ObscurantType.SMOKE
        )
        cid = self._allocate_cloud_id("smoke")
        self._clouds[cid] = _Cloud(
            cid, ctype, center.easting, center.northing, radius, 1.0
        )
        return cid

    def add_dust(self, center: Position, radius: Meters) -> str:
        """Add a dust cloud.  Returns the cloud ID."""
        cid = self._allocate_cloud_id("dust")
        self._clouds[cid] = _Cloud(
            cid, ObscurantType.DUST, center.easting, center.northing, radius, 1.0
        )
        return cid

    def update(self, dt_seconds: float) -> None:
        """Advance all clouds: drift, expand, decay.  Handle fog."""
        wind = self._weather.current.wind
        wx = self._weather.current

        to_remove: list[str] = []
        for cid in sorted(self._clouds):
            cloud = self._clouds[cid]
            cloud.age_seconds += dt_seconds

            # Drift with wind
            dt_hours = dt_seconds / 3600.0
            cloud.center_e += wind.speed * math.sin(wind.direction) * dt_seconds
            cloud.center_n += wind.speed * math.cos(wind.direction) * dt_seconds

            # Expand: r(t) = r0 + k * sqrt(t)
            k = 2.0  # dispersion coefficient
            cloud.radius += k * math.sqrt(dt_seconds) * 0.1

            # Decay density exponentially
            half_life = 1800.0  # 30 minutes for smoke/dust
            if cloud.cloud_type in (ObscurantType.FOG_RADIATION,
                                     ObscurantType.FOG_ADVECTION,
                                     ObscurantType.FOG_SEA):
                half_life = 7200.0  # fog persists longer

            decay = 0.5 ** (dt_seconds / half_life)
            cloud.density *= decay

            if cloud.density < 0.01:
                to_remove.append(cid)

        for cid in to_remove:
            del self._clouds[cid]

        # Natural fog formation
        if wx.state.name == "FOG" and not any(
            c.cloud_type in (ObscurantType.FOG_RADIATION,
                              ObscurantType.FOG_ADVECTION,
                              ObscurantType.FOG_SEA)
            for c in self._clouds.values()
        ):
            # Create a large fog patch
            cid = self._allocate_cloud_id("fog")
            self._clouds[cid] = _Cloud(
                cid, ObscurantType.FOG_RADIATION, 0.0, 0.0, 50000.0, 0.8
            )

    def opacity_at(self, pos: Position) -> SpectralBlocking:
        """Composite spectral opacity at *pos*."""
        visual = 0.0
        thermal = 0.0
        radar = 0.0

        for cloud_id in sorted(self._clouds):
            cloud = self._clouds[cloud_id]
            dist = math.sqrt(
                (pos.easting - cloud.center_e) ** 2
                + (pos.northing - cloud.center_n) ** 2
            )
            if dist > cloud.radius:
                continue

            # Linear falloff from center to edge
            fraction = max(0, 1.0 - dist / cloud.radius) if cloud.radius > 0 else 1.0
            effective_density = cloud.density * fraction

            spec = _SPECTRAL_TABLE[cloud.cloud_type]
            visual = min(1.0, visual + spec.visual * effective_density)
            thermal = min(1.0, thermal + spec.thermal * effective_density)
            radar = min(1.0, radar + spec.radar * effective_density)

        return SpectralBlocking(visual, thermal, radar)

    def visibility_at(self, pos: Position) -> Meters:
        """Effective visibility at *pos* (metres)."""
        base_vis = self._weather.current.visibility
        opacity = self.opacity_at(pos)
        if opacity.visual >= 1.0:
            return 10.0  # minimum
        return base_vis * (1.0 - opacity.visual)

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        return {
            "next_cloud_sequence": self._next_cloud_sequence,
            "clouds": [
                {
                    "cloud_id": c.cloud_id,
                    "cloud_type": int(c.cloud_type),
                    "center_e": c.center_e,
                    "center_n": c.center_n,
                    "radius": c.radius,
                    "density": c.density,
                    "age_seconds": c.age_seconds,
                }
                for c in sorted(
                    self._clouds.values(),
                    key=lambda cloud: cloud.cloud_id,
                )
            ]
        }

    def stage_state(self, state: dict[str, Any]) -> dict[str, Any]:
        """Validate a complete deterministic cloud snapshot."""
        if not isinstance(state, dict):
            raise ValueError("Obscurants state must be a mapping")
        expected_keys = {"clouds", "next_cloud_sequence"}
        if set(state) != expected_keys:
            raise ValueError(
                "Obscurants state keys must be exactly "
                f"{sorted(expected_keys)!r}",
            )
        next_sequence = state["next_cloud_sequence"]
        if (
            isinstance(next_sequence, bool)
            or not isinstance(next_sequence, int)
            or next_sequence <= 0
        ):
            raise ValueError(
                "next_cloud_sequence must be a positive integer",
            )
        raw_clouds = state["clouds"]
        if not isinstance(raw_clouds, list):
            raise ValueError("Obscurants clouds must be a list")
        cloud_keys = {
            "cloud_id",
            "cloud_type",
            "center_e",
            "center_n",
            "radius",
            "density",
            "age_seconds",
        }
        clouds: dict[str, _Cloud] = {}
        maximum_sequence = 0
        prior_id = ""
        for cd in raw_clouds:
            if not isinstance(cd, dict) or set(cd) != cloud_keys:
                raise ValueError("Obscurant cloud state has invalid keys")
            cloud_id = cd["cloud_id"]
            if (
                not isinstance(cloud_id, str)
                or not cloud_id
                or cloud_id != cloud_id.strip()
            ):
                raise ValueError(
                    "Obscurant cloud_id must be a non-empty trimmed string",
                )
            if cloud_id in clouds:
                raise ValueError(
                    f"Duplicate obscurant cloud_id {cloud_id!r}",
                )
            if cloud_id <= prior_id:
                raise ValueError(
                    "Obscurant clouds must be canonically ordered by ID",
                )
            prior_id = cloud_id
            raw_type = cd["cloud_type"]
            if isinstance(raw_type, bool) or not isinstance(raw_type, int):
                raise ValueError(
                    "Obscurant cloud_type must be an integer enum",
                )
            try:
                cloud_type = ObscurantType(raw_type)
            except ValueError as exc:
                raise ValueError("Unknown obscurant cloud_type") from exc
            prefix, separator, suffix = cloud_id.rpartition("_")
            expected_prefix = _cloud_prefix(cloud_type)
            if (
                separator != "_"
                or prefix != expected_prefix
                or len(suffix) != 8
                or not suffix.isdigit()
                or int(suffix) <= 0
                or cloud_id
                != f"{expected_prefix}_{int(suffix):08d}"
            ):
                raise ValueError(
                    "Obscurant cloud_id must match its type and use an "
                    "eight-digit positive sequence",
                )
            numbers: dict[str, float] = {}
            for field_name in (
                "center_e",
                "center_n",
                "radius",
                "density",
                "age_seconds",
            ):
                value = cd[field_name]
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(float(value))
                ):
                    raise ValueError(
                        f"Obscurant {field_name} must be finite",
                    )
                numbers[field_name] = float(value)
            if numbers["radius"] < 0.0:
                raise ValueError("Obscurant radius must be non-negative")
            if not 0.0 <= numbers["density"] <= 1.0:
                raise ValueError("Obscurant density must be in [0, 1]")
            if numbers["age_seconds"] < 0.0:
                raise ValueError(
                    "Obscurant age_seconds must be non-negative",
                )
            cloud = _Cloud(
                cloud_id,
                cloud_type,
                numbers["center_e"],
                numbers["center_n"],
                numbers["radius"],
                numbers["density"],
            )
            cloud.age_seconds = numbers["age_seconds"]
            clouds[cloud_id] = cloud
            maximum_sequence = max(maximum_sequence, int(suffix))
        if next_sequence <= maximum_sequence:
            raise ValueError(
                "next_cloud_sequence must exceed every issued cloud ID",
            )
        return {
            "clouds": clouds,
            "next_cloud_sequence": next_sequence,
        }

    def commit_state(self, staged_state: dict[str, Any]) -> None:
        """Commit a non-throwing plan returned by :meth:`stage_state`."""
        self._clouds = dict(staged_state["clouds"])
        self._next_cloud_sequence = staged_state["next_cloud_sequence"]

    def set_state(self, state: dict) -> None:
        if isinstance(state, dict) and set(state) == {"clouds"}:
            # Explicit versionless migration for pre-schema-112 snapshots.
            migrated_clouds: list[dict[str, Any]] = []
            for sequence, cloud in enumerate(
                sorted(
                    state["clouds"],
                    key=lambda item: item["cloud_id"],
                ),
                start=1,
            ):
                migrated = dict(cloud)
                cloud_type = ObscurantType(migrated["cloud_type"])
                migrated["cloud_id"] = (
                    f"{_cloud_prefix(cloud_type)}_{sequence:08d}"
                )
                migrated_clouds.append(migrated)
            state = {
                "clouds": sorted(
                    migrated_clouds,
                    key=lambda cloud: cloud["cloud_id"],
                ),
                "next_cloud_sequence": len(migrated_clouds) + 1,
            }
        self.commit_state(self.stage_state(state))
