"""Anti-satellite (ASAT) warfare — kinetic kill vehicles, co-orbital, lasers.

Models ASAT engagements against satellites and the resulting debris cascade.
Kinetic ASAT generates debris that raises collision risk for all satellites
in the altitude band.

Key physics:
- Kinetic Pk: Pk = 1 - exp(-(R_lethal / σ_eff)² / 2)
- σ_eff = σ × (1 + v_close / v_ref) — closing velocity increases miss distance
- Debris: N ~ Poisson(λ), collision risk P = N × A_sat / A_band × (dt / T_orbital)
"""

from __future__ import annotations

import enum
import math
from datetime import datetime, timezone
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.space.constellations import ConstellationManager, SpaceConfig
from stochastic_warfare.space.events import (
    ASATEngagementEvent,
    DebrisCascadeEvent,
)
from stochastic_warfare.space.orbits import R_EARTH

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums & models
# ---------------------------------------------------------------------------


class ASATType(enum.IntEnum):
    """Type of ASAT weapon."""

    DIRECT_ASCENT_KKV = 0
    CO_ORBITAL = 1
    GROUND_LASER_DAZZLE = 2
    GROUND_LASER_DESTRUCT = 3


class ASATWeaponDefinition(BaseModel):
    """YAML-loaded ASAT weapon definition."""

    weapon_id: str
    display_name: str = ""
    asat_type: int = 0  # ASATType value
    lethal_radius_m: float = 1.0
    guidance_sigma_m: float = 0.5
    max_altitude_km: float = 2000.0
    min_altitude_km: float = 200.0
    closing_velocity_mps: float = 10000.0
    reload_time_s: float = 3600.0
    dazzle_duration_s: float = 0.0
    dazzle_range_km: float = 0.0


class DebrisCloud:
    """Tracks an orbital debris cloud in an altitude band."""

    def __init__(self, altitude_band_km: float, debris_count: int) -> None:
        self.altitude_band_km = altitude_band_km
        self.debris_count = debris_count
        self.age_s: float = 0.0


# ---------------------------------------------------------------------------
# ASATEngine
# ---------------------------------------------------------------------------


class ASATEngine:
    """ASAT weapon engagement and debris tracking engine."""

    _V_REF: float = 7500.0  # Reference orbital velocity m/s

    def __init__(
        self,
        constellation_manager: ConstellationManager,
        config: SpaceConfig,
        event_bus: EventBus,
        rng: np.random.Generator,
        clock: Any = None,
    ) -> None:
        self._cm = constellation_manager
        self._config = config
        self._event_bus = event_bus
        self._rng = rng
        self._clock = clock
        self._weapons: dict[str, tuple[ASATWeaponDefinition, str]] = {}  # id → (def, side)
        self._last_fire_time: dict[str, float] = {}  # weapon_id → sim_time
        self._debris_clouds: list[DebrisCloud] = []
        self._dazzled_sats: dict[str, float] = {}  # sat_id → dazzle_end_time

    def _timestamp(self) -> datetime:
        """Get simulation timestamp from clock, or epoch fallback."""
        if self._clock is not None:
            return self._clock.current_time
        return datetime(2024, 1, 1, tzinfo=timezone.utc)

    def register_weapon(
        self, definition: ASATWeaponDefinition, side: str,
    ) -> None:
        """Register an ASAT weapon for a side."""
        self._weapons[definition.weapon_id] = (definition, side)

    def engage(
        self,
        weapon_id: str,
        target_satellite_id: str,
        side: str,
        sim_time_s: float,
        timestamp: Any = None,
    ) -> dict[str, Any]:
        """Engage a satellite with an ASAT weapon.

        Returns
        -------
        dict
            Result with keys: hit, pk, debris_generated, dazzle_duration_s.
        """
        if weapon_id not in self._weapons:
            return {"hit": False, "pk": 0.0, "debris_generated": 0, "error": "unknown_weapon"}

        weapon_def, _ = self._weapons[weapon_id]
        target = self._cm.get_satellite(target_satellite_id)
        if target is None or not target.is_active:
            return {"hit": False, "pk": 0.0, "debris_generated": 0, "error": "invalid_target"}

        # Check reload
        last_fire = self._last_fire_time.get(weapon_id, -1e9)
        if sim_time_s - last_fire < weapon_def.reload_time_s:
            return {"hit": False, "pk": 0.0, "debris_generated": 0, "error": "reloading"}

        # Check altitude range
        elems = target.elements
        e = elems.eccentricity
        nu_rad = target.current_true_anomaly_deg * math.pi / 180.0
        r = elems.semi_major_axis_m * (1.0 - e ** 2) / (1.0 + e * math.cos(nu_rad))
        altitude_km = (r - R_EARTH) / 1000.0

        if altitude_km < weapon_def.min_altitude_km or altitude_km > weapon_def.max_altitude_km:
            return {"hit": False, "pk": 0.0, "debris_generated": 0, "error": "out_of_range"}

        self._last_fire_time[weapon_id] = sim_time_s
        ts = timestamp if timestamp is not None else self._timestamp()

        asat_type = ASATType(weapon_def.asat_type)

        if asat_type in (ASATType.DIRECT_ASCENT_KKV, ASATType.CO_ORBITAL):
            return self._engage_kinetic(weapon_def, target, altitude_km, ts)
        elif asat_type == ASATType.GROUND_LASER_DAZZLE:
            return self._engage_laser_dazzle(weapon_def, target, sim_time_s, ts)
        elif asat_type == ASATType.GROUND_LASER_DESTRUCT:
            return self._engage_laser_destruct(weapon_def, target, altitude_km, ts)
        else:
            return {"hit": False, "pk": 0.0, "debris_generated": 0}

    def _engage_kinetic(
        self,
        weapon: ASATWeaponDefinition,
        target: Any,
        altitude_km: float,
        timestamp: Any,
    ) -> dict[str, Any]:
        """Kinetic kill vehicle engagement."""
        pk = self._compute_kinetic_pk(weapon, altitude_km)
        hit = float(self._rng.random()) < pk
        debris = 0

        if hit:
            target.is_active = False
            debris = self._generate_debris(target)
            self._debris_clouds.append(DebrisCloud(altitude_km, debris))

        self._event_bus.publish(ASATEngagementEvent(
            timestamp=timestamp,
            source=ModuleId.SPACE,
            weapon_id=weapon.weapon_id,
            target_satellite_id=target.satellite_id,
            hit=hit,
            pk=pk,
            debris_generated=debris,
        ))

        return {"hit": hit, "pk": pk, "debris_generated": debris}

    def _compute_kinetic_pk(
        self, weapon: ASATWeaponDefinition, target_altitude_km: float,
    ) -> float:
        """Compute kill probability for kinetic ASAT.

        Pk = 1 - exp(-(R_lethal / σ_eff)² / 2)
        σ_eff = σ_guidance × (1 + v_close / v_ref)
        """
        sigma_eff = weapon.guidance_sigma_m * (
            1.0 + weapon.closing_velocity_mps / self._V_REF
        )
        if sigma_eff <= 0:
            return 0.0
        ratio = weapon.lethal_radius_m / sigma_eff
        return 1.0 - math.exp(-0.5 * ratio ** 2)

    def _engage_laser_dazzle(
        self,
        weapon: ASATWeaponDefinition,
        target: Any,
        sim_time_s: float,
        timestamp: Any,
    ) -> dict[str, Any]:
        """Laser dazzle — temporarily blinds satellite sensors."""
        duration = weapon.dazzle_duration_s if weapon.dazzle_duration_s > 0 else 300.0
        self._dazzled_sats[target.satellite_id] = sim_time_s + duration

        self._event_bus.publish(ASATEngagementEvent(
            timestamp=timestamp,
            source=ModuleId.SPACE,
            weapon_id=weapon.weapon_id,
            target_satellite_id=target.satellite_id,
            hit=True,
            pk=1.0,
            debris_generated=0,
        ))

        return {"hit": True, "pk": 1.0, "debris_generated": 0, "dazzle_duration_s": duration}

    def _engage_laser_destruct(
        self,
        weapon: ASATWeaponDefinition,
        target: Any,
        altitude_km: float,
        timestamp: Any,
    ) -> dict[str, Any]:
        """High-power laser — permanently destroys satellite (no debris)."""
        # Higher altitude = lower Pk due to beam divergence
        pk = max(0.1, min(0.9, 1.0 - altitude_km / weapon.max_altitude_km))
        hit = float(self._rng.random()) < pk

        if hit:
            target.is_active = False

        self._event_bus.publish(ASATEngagementEvent(
            timestamp=timestamp,
            source=ModuleId.SPACE,
            weapon_id=weapon.weapon_id,
            target_satellite_id=target.satellite_id,
            hit=hit,
            pk=pk,
            debris_generated=0,
        ))

        return {"hit": hit, "pk": pk, "debris_generated": 0}

    def _generate_debris(self, target_sat: Any) -> int:
        """Generate debris count from a kinetic kill (Poisson distributed)."""
        mean = self._config.debris_fragment_mean
        return int(self._rng.poisson(mean))

    def update_debris(self, dt_s: float, sim_time_s: float) -> None:
        """Age debris clouds and check for cascade collisions."""
        for cloud in self._debris_clouds:
            cloud.age_s += dt_s

        # Check cascade collisions
        total_debris_by_band: dict[float, int] = {}
        for cloud in self._debris_clouds:
            band = round(cloud.altitude_band_km / 100.0) * 100.0
            total_debris_by_band[band] = total_debris_by_band.get(band, 0) + cloud.debris_count

        for band_km, count in total_debris_by_band.items():
            collision_prob = count * self._config.debris_collision_prob_per_orbit
            # Cap cascade probability
            collision_prob = min(collision_prob, 0.1)

            if collision_prob > 0.01:
                self._event_bus.publish(DebrisCascadeEvent(
                    timestamp=self._timestamp(),
                    source=ModuleId.SPACE,
                    altitude_band_km=band_km,
                    debris_count=count,
                    collision_probability_per_orbit=collision_prob,
                ))

                # Stochastic cascade: small chance of hitting another satellite
                if float(self._rng.random()) < collision_prob:
                    # Find a satellite in this band and destroy it
                    for sat in self._cm.all_satellites():
                        if not sat.is_active:
                            continue
                        a = sat.elements.semi_major_axis_m
                        alt_km = (a - R_EARTH) / 1000.0
                        if abs(alt_km - band_km) < 100.0:
                            sat.is_active = False
                            new_debris = int(self._rng.poisson(
                                self._config.debris_fragment_mean * 0.5,
                            ))
                            self._debris_clouds.append(
                                DebrisCloud(alt_km, new_debris),
                            )
                            logger.info(
                                "Debris cascade destroyed %s at %.0f km",
                                sat.satellite_id, alt_km,
                            )
                            break

    def update(self, dt_s: float, sim_time_s: float) -> None:
        """Update dazzle timers and debris."""
        # Expire dazzles
        expired = [
            sid for sid, end_time in self._dazzled_sats.items()
            if sim_time_s >= end_time
        ]
        for sid in expired:
            del self._dazzled_sats[sid]

        self.update_debris(dt_s, sim_time_s)

    def is_dazzled(self, satellite_id: str) -> bool:
        """Check if a satellite is currently dazzled."""
        return satellite_id in self._dazzled_sats

    # ── State persistence ────────────────────────────────────────────

    def get_state(self) -> dict[str, Any]:
        return {
            "last_fire_time": dict(self._last_fire_time),
            "dazzled_sats": dict(self._dazzled_sats),
            "debris_clouds": [
                {"altitude_band_km": c.altitude_band_km,
                 "debris_count": c.debris_count,
                 "age_s": c.age_s}
                for c in self._debris_clouds
            ],
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self._last_fire_time = state.get("last_fire_time", {})
        self._dazzled_sats = state.get("dazzled_sats", {})
        self._debris_clouds = [
            DebrisCloud(c["altitude_band_km"], c["debris_count"])
            for c in state.get("debris_clouds", [])
        ]
        for i, cdata in enumerate(state.get("debris_clouds", [])):
            if i < len(self._debris_clouds):
                self._debris_clouds[i].age_s = cdata.get("age_s", 0.0)
