"""Ballistic trajectory computation with drag, wind, Coriolis, and dispersion.

Uses RK4 numerical integration for trajectory propagation.  Supports both
direct-fire (flat trajectory) and indirect-fire (high-angle) engagements.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.combat.ammunition import AmmoDefinition, WeaponDefinition
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.numba_utils import optional_jit
from stochastic_warfare.core.types import STANDARD_GRAVITY, Position

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class BallisticsConfig(BaseModel):
    """Tunable parameters for the ballistics engine."""

    enable_drag: bool = True
    enable_mach_drag: bool = True
    enable_wind: bool = True
    enable_coriolis: bool = True
    air_density_sea_level: float = 1.225  # kg/m^3
    temperature_c: float = 21.0
    integration_step_s: float = 0.01
    max_flight_time_s: float = 300.0
    earth_rotation_rad_s: float = 7.2921e-5


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class TrajectoryPoint:
    """Single point along a trajectory."""

    time_s: float
    position: Position
    velocity: tuple[float, float, float]  # (vx, vy, vz) m/s


@dataclass
class TrajectoryResult:
    """Full trajectory from launch to impact/termination."""

    points: list[TrajectoryPoint] = field(default_factory=list)
    impact_position: Position = Position(0.0, 0.0, 0.0)
    impact_velocity: float = 0.0
    impact_angle_deg: float = 0.0
    time_of_flight_s: float = 0.0
    max_altitude_m: float = 0.0


@dataclass
class ImpactResult:
    """Impact point with dispersion applied."""

    impact_position: Position
    impact_velocity: float
    impact_angle_deg: float
    time_of_flight_s: float
    cep_m: float  # circular error probable at this range


# ---------------------------------------------------------------------------
# Mach-dependent drag helpers
# ---------------------------------------------------------------------------


@optional_jit
def _speed_of_sound(temp_c: float) -> float:
    """Speed of sound in air at given temperature (Celsius)."""
    return 331.3 * math.sqrt(1.0 + temp_c / 273.15)


@optional_jit
def _mach_drag_multiplier(mach: float) -> float:
    """Piecewise Mach-dependent drag multiplier.

    - Subsonic (M < 0.8): 1.0 (no correction)
    - Transonic (0.8 <= M <= 1.2): linear rise from 1.0 to 2.0
    - Supersonic (M > 1.2): 2.0 * (1.2/M)^0.5 (falling)
    """
    if mach < 0.8:
        return 1.0
    elif mach <= 1.2:
        return 1.0 + 2.5 * (mach - 0.8)
    else:
        return 2.0 * (1.2 / mach) ** 0.5


@optional_jit
def _derivs_kernel(
    px: float, py: float, pz: float,
    vvx: float, vvy: float, vvz: float,
    enable_drag: int, enable_mach_drag: int,
    enable_wind: int, enable_coriolis: int,
    drag_coeff: float, mass_kg: float, area: float,
    rho0: float, scale_height: float, speed_of_sound: float,
    wind_e: float, wind_n: float,
    lat_rad: float, omega: float, g: float,
) -> tuple[float, float, float, float, float, float]:
    """Compute derivatives for RK4 trajectory integration.

    Returns (dpx, dpy, dpz, dvx, dvy, dvz) — position and velocity
    derivatives at the given state.
    """
    # Velocity relative to air
    if enable_wind:
        vax = vvx - wind_e
        vay = vvy - wind_n
        vaz = vvz
    else:
        vax = vvx
        vay = vvy
        vaz = vvz

    # Drag acceleration
    dax = 0.0
    day = 0.0
    daz = 0.0
    if enable_drag:
        spd = math.sqrt(vax * vax + vay * vay + vaz * vaz)
        if spd > 1e-6:
            rho = rho0 * math.exp(-pz / scale_height)
            effective_cd = drag_coeff
            if enable_mach_drag:
                mach = spd / speed_of_sound if speed_of_sound > 0 else 0.0
                effective_cd = drag_coeff * _mach_drag_multiplier(mach)
            drag_force = 0.5 * effective_cd * rho * spd * spd * area
            drag_accel = drag_force / mass_kg
            dax = -drag_accel * vax / spd
            day = -drag_accel * vay / spd
            daz = -drag_accel * vaz / spd

    # Coriolis acceleration
    cax = 0.0
    cay = 0.0
    caz = 0.0
    if enable_coriolis:
        sin_lat = math.sin(lat_rad)
        cos_lat = math.cos(lat_rad)
        cax = 2.0 * omega * (vvy * sin_lat - vvz * cos_lat)
        cay = -2.0 * omega * vvx * sin_lat
        caz = 2.0 * omega * vvx * cos_lat

    ax = dax + cax
    ay = day + cay
    az = daz + caz - g

    return vvx, vvy, vvz, ax, ay, az


@optional_jit
def _rk4_trajectory_kernel(
    x: float, y: float, z: float,
    vx: float, vy: float, vz: float,
    dt: float, max_t: float, fire_alt: float,
    enable_drag: int, enable_mach_drag: int,
    enable_wind: int, enable_coriolis: int,
    drag_coeff: float, mass_kg: float, area: float,
    rho0: float, scale_height: float, speed_of_sound: float,
    wind_e: float, wind_n: float,
    lat_rad: float, omega: float, g: float,
) -> tuple[float, float, float, float, float, float, float, float, float]:
    """Pure-numerical RK4 trajectory kernel.

    Returns (final_x, final_y, final_z, final_vx, final_vy, final_vz,
             tof, max_alt, impact_angle_deg).
    """
    max_alt = z
    t = 0.0

    while t < max_t:
        # k1
        dp1x, dp1y, dp1z, dv1x, dv1y, dv1z = _derivs_kernel(
            x, y, z, vx, vy, vz,
            enable_drag, enable_mach_drag, enable_wind, enable_coriolis,
            drag_coeff, mass_kg, area,
            rho0, scale_height, speed_of_sound,
            wind_e, wind_n, lat_rad, omega, g,
        )
        # k2
        dp2x, dp2y, dp2z, dv2x, dv2y, dv2z = _derivs_kernel(
            x + 0.5 * dt * dp1x, y + 0.5 * dt * dp1y, z + 0.5 * dt * dp1z,
            vx + 0.5 * dt * dv1x, vy + 0.5 * dt * dv1y, vz + 0.5 * dt * dv1z,
            enable_drag, enable_mach_drag, enable_wind, enable_coriolis,
            drag_coeff, mass_kg, area,
            rho0, scale_height, speed_of_sound,
            wind_e, wind_n, lat_rad, omega, g,
        )
        # k3
        dp3x, dp3y, dp3z, dv3x, dv3y, dv3z = _derivs_kernel(
            x + 0.5 * dt * dp2x, y + 0.5 * dt * dp2y, z + 0.5 * dt * dp2z,
            vx + 0.5 * dt * dv2x, vy + 0.5 * dt * dv2y, vz + 0.5 * dt * dv2z,
            enable_drag, enable_mach_drag, enable_wind, enable_coriolis,
            drag_coeff, mass_kg, area,
            rho0, scale_height, speed_of_sound,
            wind_e, wind_n, lat_rad, omega, g,
        )
        # k4
        dp4x, dp4y, dp4z, dv4x, dv4y, dv4z = _derivs_kernel(
            x + dt * dp3x, y + dt * dp3y, z + dt * dp3z,
            vx + dt * dv3x, vy + dt * dv3y, vz + dt * dv3z,
            enable_drag, enable_mach_drag, enable_wind, enable_coriolis,
            drag_coeff, mass_kg, area,
            rho0, scale_height, speed_of_sound,
            wind_e, wind_n, lat_rad, omega, g,
        )

        x += dt / 6.0 * (dp1x + 2 * dp2x + 2 * dp3x + dp4x)
        y += dt / 6.0 * (dp1y + 2 * dp2y + 2 * dp3y + dp4y)
        z += dt / 6.0 * (dp1z + 2 * dp2z + 2 * dp3z + dp4z)
        vx += dt / 6.0 * (dv1x + 2 * dv2x + 2 * dv3x + dv4x)
        vy += dt / 6.0 * (dv1y + 2 * dv2y + 2 * dv3y + dv4y)
        vz += dt / 6.0 * (dv1z + 2 * dv2z + 2 * dv3z + dv4z)
        t += dt

        if z > max_alt:
            max_alt = z

        # Impact: below starting altitude after ascending
        if z <= fire_alt and t > dt * 2:
            break

    speed = math.sqrt(vx * vx + vy * vy + vz * vz)
    v_horiz = math.sqrt(vx * vx + vy * vy)
    if v_horiz > 0:
        impact_angle = math.degrees(math.atan2(-vz, v_horiz))
    else:
        impact_angle = 90.0

    return (x, y, z, vx, vy, vz, t, max_alt, abs(impact_angle))


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class BallisticsEngine:
    """Ballistic trajectory computation with physics-based models.

    Parameters
    ----------
    rng:
        PRNG generator for dispersion calculations.
    config:
        Tunable ballistics parameters.
    """

    def __init__(
        self,
        rng: np.random.Generator,
        config: BallisticsConfig | None = None,
    ) -> None:
        self._rng = rng
        self._config = config or BallisticsConfig()

    def _air_density(
        self, altitude_m: float, rho0_override: float | None = None,
    ) -> float:
        """ISA air density model — decreases with altitude.

        Parameters
        ----------
        altitude_m:
            Altitude in metres above sea level.
        rho0_override:
            If provided, override sea-level density (e.g. from weather).
        """
        rho0 = rho0_override if rho0_override is not None else self._config.air_density_sea_level
        # Simplified exponential model
        scale_height = 8500.0  # meters
        return rho0 * math.exp(-altitude_m / scale_height)

    def _drag_acceleration(
        self,
        velocity: tuple[float, float, float],
        drag_coeff: float,
        mass_kg: float,
        diameter_mm: float,
        altitude_m: float,
        air_temp_c: float | None = None,
    ) -> tuple[float, float, float]:
        """Compute drag deceleration vector."""
        if not self._config.enable_drag:
            return (0.0, 0.0, 0.0)

        vx, vy, vz = velocity
        speed = math.sqrt(vx * vx + vy * vy + vz * vz)
        if speed < 1e-6:
            return (0.0, 0.0, 0.0)

        rho = self._air_density(altitude_m)
        # Mach-dependent drag coefficient
        effective_cd = drag_coeff
        if self._config.enable_mach_drag:
            temp = air_temp_c if air_temp_c is not None else self._config.temperature_c
            sos = _speed_of_sound(temp)
            mach = speed / sos if sos > 0 else 0.0
            effective_cd = drag_coeff * _mach_drag_multiplier(mach)
        radius_m = diameter_mm / 2000.0
        area = math.pi * radius_m * radius_m
        drag_force = 0.5 * effective_cd * rho * speed * speed * area

        # Drag opposes velocity direction
        drag_accel = drag_force / mass_kg
        return (
            -drag_accel * vx / speed,
            -drag_accel * vy / speed,
            -drag_accel * vz / speed,
        )

    def _coriolis_acceleration(
        self,
        velocity: tuple[float, float, float],
        latitude_rad: float,
    ) -> tuple[float, float, float]:
        """Coriolis acceleration from Earth rotation."""
        if not self._config.enable_coriolis:
            return (0.0, 0.0, 0.0)

        omega = self._config.earth_rotation_rad_s
        vx, vy, vz = velocity
        sin_lat = math.sin(latitude_rad)
        cos_lat = math.cos(latitude_rad)

        # Coriolis = -2 * omega × v (simplified for ENU frame)
        ax = 2.0 * omega * (vy * sin_lat - vz * cos_lat)
        ay = -2.0 * omega * vx * sin_lat
        az = 2.0 * omega * vx * cos_lat
        return (ax, ay, az)

    def compute_trajectory(
        self,
        weapon: WeaponDefinition,
        ammo: AmmoDefinition,
        fire_pos: Position,
        elevation_deg: float,
        azimuth_deg: float,
        conditions: dict[str, Any] | None = None,
    ) -> TrajectoryResult:
        """Propagate trajectory using RK4 integration.

        Parameters
        ----------
        weapon:
            Weapon system definition (provides muzzle velocity).
        ammo:
            Ammunition definition (provides mass, drag, diameter).
        fire_pos:
            Launch position in ENU meters.
        elevation_deg:
            Barrel elevation angle (degrees above horizontal).
        azimuth_deg:
            Barrel azimuth (degrees clockwise from north).
        conditions:
            Optional dict with keys: wind_e, wind_n (m/s),
            temperature_c, latitude_rad.
        """
        conditions = conditions or {}
        dt = self._config.integration_step_s
        max_t = self._config.max_flight_time_s

        # Muzzle velocity adjusted for propellant temperature
        temp_c = conditions.get("temperature_c", self._config.temperature_c)
        mv = weapon.muzzle_velocity_mps
        if ammo.max_speed_mps > 0:
            mv = max(mv, ammo.max_speed_mps)
        # Phase 59c: propellant temperature coefficient (MIL-STD-1474)
        mv *= 1.0 + 0.001 * (temp_c - 21.0)

        el_rad = math.radians(elevation_deg)
        az_rad = math.radians(azimuth_deg)

        # Initial velocity in ENU (x=east, y=north, z=up)
        v_horiz = mv * math.cos(el_rad)
        vx = v_horiz * math.sin(az_rad)
        vy = v_horiz * math.cos(az_rad)
        vz = mv * math.sin(el_rad)

        # State: position (x, y, z) and velocity (vx, vy, vz)
        x, y, z = fire_pos.easting, fire_pos.northing, fire_pos.altitude
        wind_e = conditions.get("wind_e", 0.0)
        wind_n = conditions.get("wind_n", 0.0)
        lat_rad = conditions.get("latitude_rad", 0.7)  # ~40° default

        # Use JIT kernel for fast path (impact data only)
        radius_m = ammo.diameter_mm / 2000.0
        area = math.pi * radius_m * radius_m
        sos = _speed_of_sound(temp_c)
        # Phase 59c: allow weather-derived air density override
        rho0 = conditions.get(
            "air_density_sea_level", self._config.air_density_sea_level,
        )

        # Phase 66b: propulsion reduces effective drag for powered munitions
        _eff_drag = ammo.drag_coefficient
        _propulsion = getattr(ammo, "propulsion", "none")
        if _propulsion and _propulsion != "none":
            _prop_factors = {"rocket": 0.3, "turbojet": 0.2, "ramjet": 0.15}
            _eff_drag *= _prop_factors.get(_propulsion, 0.5)

        fx, fy, fz, fvx, fvy, fvz, tof, max_alt, impact_angle = _rk4_trajectory_kernel(
            x, y, z, vx, vy, vz,
            dt, max_t, fire_pos.altitude,
            int(self._config.enable_drag), int(self._config.enable_mach_drag),
            int(self._config.enable_wind), int(self._config.enable_coriolis),
            _eff_drag, ammo.mass_kg, area,
            rho0, 8500.0, sos,
            wind_e, wind_n,
            lat_rad, self._config.earth_rotation_rad_s, STANDARD_GRAVITY,
        )

        result = TrajectoryResult()
        result.points.append(TrajectoryPoint(0.0, fire_pos, (vx, vy, vz)))
        result.points.append(
            TrajectoryPoint(tof, Position(fx, fy, max(fz, 0.0)), (fvx, fvy, fvz))
        )
        result.impact_position = Position(fx, fy, max(fz, 0.0))
        result.impact_velocity = math.sqrt(fvx * fvx + fvy * fvy + fvz * fvz)
        result.impact_angle_deg = impact_angle
        result.time_of_flight_s = tof
        result.max_altitude_m = max_alt

        return result

    def apply_dispersion(
        self,
        aim_point: Position,
        accuracy_mrad: float,
        range_m: float,
    ) -> Position:
        """Apply Gaussian dispersion to an aim point.

        Parameters
        ----------
        aim_point:
            Intended impact point.
        accuracy_mrad:
            Weapon accuracy in milliradians (1 sigma).
        range_m:
            Engagement range (dispersion scales with range).
        """
        if accuracy_mrad <= 0:
            return aim_point

        # Standard deviation in meters at this range
        sigma_m = accuracy_mrad * 0.001 * range_m
        offset_e = self._rng.normal(0.0, sigma_m)
        offset_n = self._rng.normal(0.0, sigma_m)

        return Position(
            aim_point.easting + offset_e,
            aim_point.northing + offset_n,
            aim_point.altitude,
        )

    def compute_impact_point(
        self,
        weapon: WeaponDefinition,
        ammo: AmmoDefinition,
        fire_pos: Position,
        target_pos: Position,
        conditions: dict[str, Any] | None = None,
    ) -> ImpactResult:
        """Compute impact point for a direct-fire engagement.

        Solves for elevation angle to hit *target_pos*, then applies
        dispersion.
        """
        dx = target_pos.easting - fire_pos.easting
        dy = target_pos.northing - fire_pos.northing
        dz = target_pos.altitude - fire_pos.altitude
        range_horiz = math.sqrt(dx * dx + dy * dy)
        azimuth_deg = math.degrees(math.atan2(dx, dy)) % 360.0

        # Solve for elevation using flat-fire approximation
        mv = weapon.muzzle_velocity_mps
        if mv <= 0:
            mv = ammo.max_speed_mps if ammo.max_speed_mps > 0 else 500.0

        # Approximate elevation for flat trajectory
        if range_horiz < 1.0:
            el_deg = 45.0 if dz > 0 else 0.0
        else:
            # First-order: tan(el) ≈ (dz/range) + (g*range)/(2*v^2)
            el_rad = math.atan2(dz, range_horiz) + (
                STANDARD_GRAVITY * range_horiz / (2.0 * mv * mv)
            )
            el_deg = math.degrees(el_rad)

        traj = self.compute_trajectory(
            weapon, ammo, fire_pos, el_deg, azimuth_deg, conditions,
        )

        # Apply dispersion
        dispersed = self.apply_dispersion(
            traj.impact_position,
            weapon.base_accuracy_mrad,
            range_horiz,
        )

        # CEP ≈ 1.1774 * sigma (for 2D Gaussian)
        sigma_m = weapon.base_accuracy_mrad * 0.001 * range_horiz
        cep = 1.1774 * sigma_m if sigma_m > 0 else 0.0

        return ImpactResult(
            impact_position=dispersed,
            impact_velocity=traj.impact_velocity,
            impact_angle_deg=traj.impact_angle_deg,
            time_of_flight_s=traj.time_of_flight_s,
            cep_m=cep,
        )

    def compute_time_of_flight(
        self,
        weapon: WeaponDefinition,
        ammo: AmmoDefinition,
        range_m: float,
        elevation_deg: float = 0.0,
    ) -> float:
        """Estimate time of flight for a given range and elevation.

        Uses simplified calculation (no full trajectory integration).
        """
        mv = weapon.muzzle_velocity_mps
        if mv <= 0:
            mv = ammo.max_speed_mps if ammo.max_speed_mps > 0 else 500.0

        el_rad = math.radians(elevation_deg)
        v_horiz = mv * math.cos(el_rad)
        if v_horiz < 1.0:
            return range_m / 500.0  # fallback

        # Simple estimate: range / horizontal velocity
        # Add drag correction: multiply by factor > 1
        drag_factor = 1.0 + 0.5 * ammo.drag_coefficient * range_m / 10000.0
        return range_m / v_horiz * drag_factor

    def get_state(self) -> dict[str, Any]:
        return {"rng_state": self._rng.bit_generator.state}

    def set_state(self, state: dict[str, Any]) -> None:
        self._rng.bit_generator.state = state["rng_state"]
