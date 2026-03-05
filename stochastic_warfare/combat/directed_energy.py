"""Directed energy weapon physics — laser and HPM engagement models.

Implements Beer-Lambert atmospheric transmittance for laser beams,
dwell-time-based laser Pk, inverse-square HPM Pk, and engagement
orchestration for both DEW types.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.combat.ammunition import AmmoDefinition, WeaponDefinition, WeaponInstance
from stochastic_warfare.combat.events import DEWEngagementEvent
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position

logger = get_logger(__name__)


class DEWType(enum.IntEnum):
    """Directed energy weapon classification."""

    LASER = 0
    HPM = 1


class DEWConfig(BaseModel):
    """Tunable parameters for directed energy weapon engagements."""

    # Atmospheric extinction
    base_extinction_per_km: float = 0.2
    humidity_extinction_coeff: float = 0.5
    precipitation_extinction_coeff: float = 0.02
    fog_extinction_per_km: float = 10.0
    min_transmittance: float = 0.01

    # Thermal damage
    default_target_thermal_mass_kj: float = 50.0
    armored_target_thermal_mass_kj: float = 5000.0
    dew_fire_probability: float = 0.3

    # HPM
    hpm_reference_range_m: float = 300.0
    hpm_shielding_reduction: float = 0.3
    hpm_base_pk: float = 0.9

    # Engagement
    cooldown_multiplier: float = 1.5


@dataclass
class DEWEngagementResult:
    """Outcome of a directed energy engagement."""

    engaged: bool
    attacker_id: str = ""
    target_id: str = ""
    weapon_id: str = ""
    hit: bool = False
    pk: float = 0.0
    damage_type: str = ""
    transmittance: float = 1.0
    power_on_target_kw: float = 0.0
    dwell_time_s: float = 0.0
    range_m: float = 0.0
    aborted_reason: str = ""


class DEWEngine:
    """Directed energy weapon engagement engine.

    Parameters
    ----------
    event_bus:
        For publishing DEW engagement events.
    rng:
        PRNG generator for stochastic effects.
    config:
        Tunable DEW parameters.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: DEWConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or DEWConfig()

    @staticmethod
    def _compute_aperture_factor(
        beam_divergence_mrad: float,
        max_range_m: float,
        range_m: float,
    ) -> float:
        """Fraction of beam energy intercepted by target aperture."""
        if beam_divergence_mrad <= 0 or range_m <= 0:
            return 1.0
        spot_radius = beam_divergence_mrad * 0.001 * range_m
        aperture_diameter_m = max_range_m * beam_divergence_mrad * 0.001
        if aperture_diameter_m <= 0 or spot_radius <= 0:
            return 1.0
        ratio = aperture_diameter_m / (2.0 * spot_radius)
        return min(1.0, ratio * ratio)

    def compute_atmospheric_transmittance(
        self,
        range_m: float,
        humidity: float = 0.5,
        precipitation_rate: float = 0.0,
        visibility: float = 10000.0,
    ) -> float:
        """Beer-Lambert atmospheric transmission for laser beam.

        Parameters
        ----------
        range_m:
            Slant range in meters.
        humidity:
            Relative humidity 0-1.
        precipitation_rate:
            Precipitation rate in mm/hr.
        visibility:
            Atmospheric visibility in meters.

        Returns
        -------
        Transmittance factor 0-1.
        """
        cfg = self._config
        range_km = range_m / 1000.0

        extinction = cfg.base_extinction_per_km
        extinction += cfg.humidity_extinction_coeff * humidity
        extinction += cfg.precipitation_extinction_coeff * precipitation_rate

        if visibility < 1000.0:
            extinction += cfg.fog_extinction_per_km

        transmittance = math.exp(-extinction * range_km)
        return max(0.0, min(1.0, transmittance))

    def compute_laser_pk(
        self,
        weapon: WeaponDefinition,
        range_m: float,
        transmittance: float,
        target_thermal_mass_kj: float,
    ) -> float:
        """Probability of kill for laser engagement.

        Parameters
        ----------
        weapon:
            Weapon definition with beam_power_kw, dwell_time_s, beam_divergence_mrad.
        range_m:
            Slant range in meters.
        transmittance:
            Atmospheric transmittance factor.
        target_thermal_mass_kj:
            Target thermal mass in kJ (energy needed for kill).

        Returns
        -------
        Pk clamped to [0.0, 0.99].
        """
        if weapon.beam_power_kw <= 0 or target_thermal_mass_kj <= 0:
            return 0.0

        aperture_factor = self._compute_aperture_factor(
            weapon.beam_divergence_mrad, weapon.max_range_m, range_m,
        )
        power_on_target = weapon.beam_power_kw * transmittance * aperture_factor
        energy_delivered = power_on_target * weapon.dwell_time_s

        if energy_delivered <= 0:
            return 0.0

        pk = 1.0 - math.exp(-energy_delivered / target_thermal_mass_kj)
        return max(0.0, min(0.99, pk))

    def compute_hpm_pk(
        self,
        weapon: WeaponDefinition,
        range_m: float,
        target_is_shielded: bool = False,
    ) -> float:
        """Probability of electronic kill for HPM engagement.

        Parameters
        ----------
        weapon:
            Weapon definition with beam_power_kw (used for HPM base Pk).
        range_m:
            Range to target in meters.
        target_is_shielded:
            Whether target has EM hardening.

        Returns
        -------
        Pk clamped to [0.0, 0.99].
        """
        cfg = self._config

        if range_m <= 0:
            range_m = 1.0

        if weapon.max_range_m > 0 and range_m > weapon.max_range_m:
            return 0.0

        base_pk = cfg.hpm_base_pk

        power_density_ratio = (cfg.hpm_reference_range_m / range_m) ** 2
        shielding_factor = cfg.hpm_shielding_reduction if target_is_shielded else 1.0

        pk = base_pk * power_density_ratio * shielding_factor
        return max(0.0, min(0.99, pk))

    def execute_laser_engagement(
        self,
        attacker_id: str,
        target_id: str,
        shooter_pos: Position,
        target_pos: Position,
        weapon: WeaponInstance,
        ammo_id: str,
        ammo_def: AmmoDefinition,
        *,
        humidity: float = 0.5,
        precipitation_rate: float = 0.0,
        visibility: float = 10000.0,
        target_thermal_mass_kj: float = 50.0,
        current_time_s: float = 0.0,
        timestamp: Any = None,
    ) -> DEWEngagementResult:
        """Full laser engagement: range -> transmittance -> abort check -> Pk -> roll -> event.

        Parameters
        ----------
        attacker_id:
            Attacking unit ID.
        target_id:
            Target unit ID.
        shooter_pos:
            Attacker position.
        target_pos:
            Target position.
        weapon:
            Weapon instance (for ammo consumption).
        ammo_id:
            Ammo type to consume.
        ammo_def:
            Ammo definition.
        humidity:
            Relative humidity 0-1.
        precipitation_rate:
            Precipitation in mm/hr.
        visibility:
            Visibility in meters.
        target_thermal_mass_kj:
            Target thermal mass in kJ.
        current_time_s:
            Current simulation time.
        timestamp:
            Event timestamp.
        """
        dx = target_pos.easting - shooter_pos.easting
        dy = target_pos.northing - shooter_pos.northing
        dz = target_pos.altitude - shooter_pos.altitude
        range_m = math.sqrt(dx * dx + dy * dy + dz * dz)

        result = DEWEngagementResult(
            engaged=False,
            attacker_id=attacker_id,
            target_id=target_id,
            weapon_id=weapon.weapon_id,
            range_m=range_m,
        )

        # Range check
        wdef = weapon.definition
        if wdef.max_range_m > 0 and range_m > wdef.max_range_m:
            result.aborted_reason = "out_of_range"
            return result

        # Atmospheric transmittance
        transmittance = self.compute_atmospheric_transmittance(
            range_m, humidity, precipitation_rate, visibility,
        )
        result.transmittance = transmittance

        if transmittance < self._config.min_transmittance:
            result.aborted_reason = "low_transmittance"
            return result

        # Ammo consumption (one charge per engagement)
        if not weapon.fire(ammo_id):
            result.aborted_reason = "no_ammo"
            return result

        weapon.record_fire(current_time_s)
        result.engaged = True
        result.dwell_time_s = wdef.dwell_time_s

        # Compute Pk
        pk = self.compute_laser_pk(wdef, range_m, transmittance, target_thermal_mass_kj)
        result.pk = pk

        # Power on target for reporting
        aperture_factor = self._compute_aperture_factor(
            wdef.beam_divergence_mrad, wdef.max_range_m, range_m,
        )
        result.power_on_target_kw = wdef.beam_power_kw * transmittance * aperture_factor

        # Roll
        hit = float(self._rng.random()) < pk
        result.hit = hit
        result.damage_type = "THERMAL_ENERGY"

        # Publish event
        if timestamp is not None:
            self._event_bus.publish(DEWEngagementEvent(
                timestamp=timestamp,
                source=ModuleId.COMBAT,
                attacker_id=attacker_id,
                target_id=target_id,
                weapon_id=weapon.weapon_id,
                dew_type="LASER",
                result="hit" if hit else "miss",
                transmittance=transmittance,
                power_on_target_kw=result.power_on_target_kw,
            ))

        return result

    def execute_hpm_engagement(
        self,
        attacker_id: str,
        shooter_pos: Position,
        weapon: WeaponInstance,
        ammo_id: str,
        ammo_def: AmmoDefinition,
        targets: list[tuple[str, Position, bool]],
        *,
        current_time_s: float = 0.0,
        timestamp: Any = None,
    ) -> list[DEWEngagementResult]:
        """HPM area-effect engagement. Each target within max_range gets independent Pk roll.

        Parameters
        ----------
        attacker_id:
            Attacking unit ID.
        shooter_pos:
            Attacker position.
        weapon:
            Weapon instance.
        ammo_id:
            Ammo type to consume.
        ammo_def:
            Ammo definition.
        targets:
            List of (target_id, position, is_shielded) tuples.
        current_time_s:
            Current simulation time.
        timestamp:
            Event timestamp.
        """
        # Consume one charge for entire burst
        if not weapon.fire(ammo_id):
            return [DEWEngagementResult(
                engaged=False, attacker_id=attacker_id,
                aborted_reason="no_ammo",
            )]

        weapon.record_fire(current_time_s)

        wdef = weapon.definition
        results: list[DEWEngagementResult] = []

        for target_id, target_pos, is_shielded in targets:
            dx = target_pos.easting - shooter_pos.easting
            dy = target_pos.northing - shooter_pos.northing
            dz = target_pos.altitude - shooter_pos.altitude
            range_m = math.sqrt(dx * dx + dy * dy + dz * dz)

            res = DEWEngagementResult(
                engaged=True,
                attacker_id=attacker_id,
                target_id=target_id,
                weapon_id=weapon.weapon_id,
                range_m=range_m,
                damage_type="ELECTRONIC",
            )

            if wdef.max_range_m > 0 and range_m > wdef.max_range_m:
                res.engaged = False
                res.aborted_reason = "out_of_range"
                results.append(res)
                continue

            pk = self.compute_hpm_pk(wdef, range_m, is_shielded)
            res.pk = pk

            hit = float(self._rng.random()) < pk
            res.hit = hit

            if timestamp is not None:
                self._event_bus.publish(DEWEngagementEvent(
                    timestamp=timestamp,
                    source=ModuleId.COMBAT,
                    attacker_id=attacker_id,
                    target_id=target_id,
                    weapon_id=weapon.weapon_id,
                    dew_type="HPM",
                    result="hit" if hit else "miss",
                ))

            results.append(res)

        return results

    def get_state(self) -> dict[str, Any]:
        """Serialize engine state for checkpointing."""
        return {"rng_state": self._rng.bit_generator.state}

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore engine state from a checkpoint."""
        self._rng.bit_generator.state = state["rng_state"]
