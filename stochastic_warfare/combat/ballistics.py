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
from stochastic_warfare.core.types import EARTH_MEAN_RADIUS, STANDARD_GRAVITY, Position

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class BallisticsConfig(BaseModel):
    """Tunable parameters for the ballistics engine."""

    enable_drag: bool = True
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

    def _air_density(self, altitude_m: float) -> float:
        """ISA air density model — decreases with altitude."""
        rho0 = self._config.air_density_sea_level
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
    ) -> tuple[float, float, float]:
        """Compute drag deceleration vector."""
        if not self._config.enable_drag:
            return (0.0, 0.0, 0.0)

        vx, vy, vz = velocity
        speed = math.sqrt(vx * vx + vy * vy + vz * vz)
        if speed < 1e-6:
            return (0.0, 0.0, 0.0)

        rho = self._air_density(altitude_m)
        radius_m = diameter_mm / 2000.0
        area = math.pi * radius_m * radius_m
        drag_force = 0.5 * drag_coeff * rho * speed * speed * area

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
        mv *= 1.0 + 0.0005 * (temp_c - 21.0)

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

        result = TrajectoryResult()
        result.points.append(
            TrajectoryPoint(0.0, Position(x, y, z), (vx, vy, vz))
        )
        max_alt = z
        t = 0.0

        while t < max_t:
            # RK4 integration step
            def derivs(
                pos: tuple[float, float, float],
                vel: tuple[float, float, float],
            ) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
                # Velocity relative to air (wind effect)
                if self._config.enable_wind:
                    v_air = (vel[0] - wind_e, vel[1] - wind_n, vel[2])
                else:
                    v_air = vel

                drag = self._drag_acceleration(
                    v_air, ammo.drag_coefficient, ammo.mass_kg,
                    ammo.diameter_mm, pos[2],
                )
                cor = self._coriolis_acceleration(vel, lat_rad)

                ax = drag[0] + cor[0]
                ay = drag[1] + cor[1]
                az_accel = drag[2] + cor[2] - STANDARD_GRAVITY

                return vel, (ax, ay, az_accel)

            # k1
            dp1, dv1 = derivs((x, y, z), (vx, vy, vz))
            # k2
            p2 = (x + 0.5 * dt * dp1[0], y + 0.5 * dt * dp1[1], z + 0.5 * dt * dp1[2])
            v2 = (vx + 0.5 * dt * dv1[0], vy + 0.5 * dt * dv1[1], vz + 0.5 * dt * dv1[2])
            dp2, dv2 = derivs(p2, v2)
            # k3
            p3 = (x + 0.5 * dt * dp2[0], y + 0.5 * dt * dp2[1], z + 0.5 * dt * dp2[2])
            v3 = (vx + 0.5 * dt * dv2[0], vy + 0.5 * dt * dv2[1], vz + 0.5 * dt * dv2[2])
            dp3, dv3 = derivs(p3, v3)
            # k4
            p4 = (x + dt * dp3[0], y + dt * dp3[1], z + dt * dp3[2])
            v4 = (vx + dt * dv3[0], vy + dt * dv3[1], vz + dt * dv3[2])
            dp4, dv4 = derivs(p4, v4)

            x += dt / 6.0 * (dp1[0] + 2 * dp2[0] + 2 * dp3[0] + dp4[0])
            y += dt / 6.0 * (dp1[1] + 2 * dp2[1] + 2 * dp3[1] + dp4[1])
            z += dt / 6.0 * (dp1[2] + 2 * dp2[2] + 2 * dp3[2] + dp4[2])
            vx += dt / 6.0 * (dv1[0] + 2 * dv2[0] + 2 * dv3[0] + dv4[0])
            vy += dt / 6.0 * (dv1[1] + 2 * dv2[1] + 2 * dv3[1] + dv4[1])
            vz += dt / 6.0 * (dv1[2] + 2 * dv2[2] + 2 * dv3[2] + dv4[2])
            t += dt

            max_alt = max(max_alt, z)

            # Record trajectory point at impact or periodically
            # Impact detection: below starting altitude after ascending
            if z <= fire_pos.altitude and t > dt * 2:
                result.points.append(
                    TrajectoryPoint(t, Position(x, y, max(z, 0.0)), (vx, vy, vz))
                )
                break

        speed = math.sqrt(vx * vx + vy * vy + vz * vz)
        v_horiz_final = math.sqrt(vx * vx + vy * vy)
        impact_angle = math.degrees(math.atan2(-vz, v_horiz_final)) if v_horiz_final > 0 else 90.0

        result.impact_position = Position(x, y, max(z, 0.0))
        result.impact_velocity = speed
        result.impact_angle_deg = abs(impact_angle)
        result.time_of_flight_s = t
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
