"""GPS spoofing engine — position offset attacks on GPS-dependent systems.

Unlike jamming (which denies GPS entirely), spoofing provides false position
data. Civilian receivers are highly vulnerable; military M-code receivers
resist most spoofing. INS cross-checks detect spoofing after a delay.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass
from typing import Any, NamedTuple

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.ew.events import GPSSpoofingDetectedEvent

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums & configuration
# ---------------------------------------------------------------------------


class ReceiverType(enum.IntEnum):
    """GPS receiver classification."""

    CIVILIAN = 0
    MILITARY_P = 1  # P(Y)-code
    MILITARY_M = 2  # M-code (most resistant)


class SpoofingConfig(BaseModel):
    """Tunable parameters for GPS spoofing."""

    civilian_spoof_resistance: float = 0.05
    military_p_spoof_resistance: float = 0.4
    military_m_spoof_resistance: float = 0.85
    ins_crosscheck_delay_s: float = 30.0
    ins_drift_rate_m_per_s: float = 0.01
    gps_jam_noise_m: float = 50.0


# ---------------------------------------------------------------------------
# Spoof zone
# ---------------------------------------------------------------------------


@dataclass
class GPSSpoofZone:
    """An active GPS spoofing zone."""

    zone_id: str
    center: Position
    radius_m: float
    offset_east_m: float
    offset_north_m: float
    power_dbm: float
    active: bool = True


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


class GPSEffect(NamedTuple):
    """Result of GPS spoofing effect computation."""

    accuracy_m: float
    offset_east_m: float
    offset_north_m: float
    spoofed: bool


# ---------------------------------------------------------------------------
# Spoofing engine
# ---------------------------------------------------------------------------


class SpoofingEngine:
    """GPS spoofing engine.

    Parameters
    ----------
    event_bus : EventBus
        For publishing spoofing detection events.
    rng : np.random.Generator
        PRNG stream.
    config : SpoofingConfig, optional
        Tunable parameters.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: SpoofingConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or SpoofingConfig()
        self._zones: dict[str, GPSSpoofZone] = {}

    # ------------------------------------------------------------------
    # Zone management
    # ------------------------------------------------------------------

    def add_spoof_zone(self, zone: GPSSpoofZone) -> None:
        """Register a GPS spoofing zone."""
        self._zones[zone.zone_id] = zone

    def remove_spoof_zone(self, zone_id: str) -> None:
        """Remove a GPS spoofing zone."""
        self._zones.pop(zone_id, None)

    # ------------------------------------------------------------------
    # GPS effect computation
    # ------------------------------------------------------------------

    def _in_zone(self, pos: Position, zone: GPSSpoofZone) -> bool:
        dx = pos.easting - zone.center.easting
        dy = pos.northing - zone.center.northing
        return math.sqrt(dx * dx + dy * dy) <= zone.radius_m

    def _spoof_resistance(self, receiver_type: ReceiverType) -> float:
        cfg = self._config
        if receiver_type == ReceiverType.CIVILIAN:
            return cfg.civilian_spoof_resistance
        elif receiver_type == ReceiverType.MILITARY_P:
            return cfg.military_p_spoof_resistance
        else:
            return cfg.military_m_spoof_resistance

    def compute_gps_effect(
        self,
        receiver_pos: Position,
        receiver_type: ReceiverType,
        time_in_zone_s: float = 0.0,
    ) -> GPSEffect:
        """Compute the GPS effect on a receiver at a given position.

        Returns accuracy degradation and any spoofing offset applied.
        """
        cfg = self._config
        base_accuracy = 5.0

        # Find the strongest active spoof zone affecting this position
        best_zone: GPSSpoofZone | None = None
        for zone in self._zones.values():
            if not zone.active:
                continue
            if self._in_zone(receiver_pos, zone):
                if best_zone is None or zone.power_dbm > best_zone.power_dbm:
                    best_zone = zone

        if best_zone is None:
            return GPSEffect(base_accuracy, 0.0, 0.0, False)

        resistance = self._spoof_resistance(receiver_type)

        # Spoofing probability: inverse of resistance
        spoof_prob = 1.0 - resistance
        roll = float(self._rng.random())
        if roll >= spoof_prob:
            # Resisted spoofing, but still gets some noise
            return GPSEffect(
                base_accuracy + cfg.gps_jam_noise_m * (1.0 - resistance),
                0.0, 0.0, False,
            )

        # Spoofed: apply offset
        offset_e = best_zone.offset_east_m * (1.0 - resistance)
        offset_n = best_zone.offset_north_m * (1.0 - resistance)
        accuracy = base_accuracy + math.sqrt(offset_e ** 2 + offset_n ** 2)

        return GPSEffect(accuracy, offset_e, offset_n, True)

    def check_spoof_detection(
        self,
        receiver_pos: Position,
        receiver_type: ReceiverType,
        time_in_zone_s: float,
        timestamp: Any = None,
    ) -> bool:
        """Check if a unit detects it is being spoofed (via INS cross-check).

        Detection occurs after ``ins_crosscheck_delay_s`` when INS drift
        diverges from GPS-reported position.
        """
        cfg = self._config
        if time_in_zone_s < cfg.ins_crosscheck_delay_s:
            return False

        # After delay, detection probability increases with time
        excess_time = time_in_zone_s - cfg.ins_crosscheck_delay_s
        # INS drift accumulates; large drift → easier detection
        ins_drift_m = cfg.ins_drift_rate_m_per_s * excess_time
        # Detect when drift vs offset creates detectable mismatch
        # Simple threshold: detection when drift itself is noticeable (>1m)
        detected = ins_drift_m > 1.0 or excess_time > 60.0

        if detected and timestamp is not None:
            # Find which zone
            for zone in self._zones.values():
                if zone.active and self._in_zone(receiver_pos, zone):
                    self._event_bus.publish(GPSSpoofingDetectedEvent(
                        timestamp=timestamp, source=ModuleId.EW,
                        unit_id="", detection_delay_s=time_in_zone_s,
                    ))
                    break

        return detected

    def compute_pgm_offset(
        self,
        target_pos: Position,
        receiver_type: ReceiverType,
        time_in_zone_s: float = 0.0,
    ) -> Position:
        """Compute the offset applied to a GPS-guided PGM's target.

        Returns the actual impact position after spoofing offset.
        Non-GPS weapons (laser, INS) are unaffected.
        """
        effect = self.compute_gps_effect(target_pos, receiver_type, time_in_zone_s)
        if not effect.spoofed:
            return target_pos
        return Position(
            target_pos.easting + effect.offset_east_m,
            target_pos.northing + effect.offset_north_m,
            target_pos.altitude,
        )

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def get_state(self) -> dict[str, Any]:
        return {
            "rng_state": self._rng.bit_generator.state,
            "zones": {
                zid: {
                    "zone_id": z.zone_id,
                    "center": tuple(z.center),
                    "radius_m": z.radius_m,
                    "offset_east_m": z.offset_east_m,
                    "offset_north_m": z.offset_north_m,
                    "power_dbm": z.power_dbm,
                    "active": z.active,
                }
                for zid, z in self._zones.items()
            },
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self._rng.bit_generator.state = state["rng_state"]
        self._zones.clear()
        for zid, zdata in state.get("zones", {}).items():
            self._zones[zid] = GPSSpoofZone(
                zone_id=zdata["zone_id"],
                center=Position(*zdata["center"]),
                radius_m=zdata["radius_m"],
                offset_east_m=zdata["offset_east_m"],
                offset_north_m=zdata["offset_north_m"],
                power_dbm=zdata["power_dbm"],
                active=zdata["active"],
            )
