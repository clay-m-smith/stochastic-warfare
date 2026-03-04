"""Electronic Attack — jamming engine.

Computes J/S (jammer-to-signal) ratio, burn-through range, radar SNR penalty,
and communications jam factor. All physics follow standard EW equations from
Schleher and Adamy.

Key equations:
- J/S = P_j·G_j / (P_t·G_t) · (R_t/R_j)² · (B_t/B_j)  [self-screening]
- J/S = P_j·G_j / (P_t·G_t²·σ) · (4π)·R_t⁴/R_j² · (B_t/B_j)·λ²  [stand-off]
- Burn-through: R_bt = R_j · √(P_t·G_t·B_j / (P_j·G_j·B_t))
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.ew.events import JammingActivatedEvent, JammingDeactivatedEvent

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums & configuration
# ---------------------------------------------------------------------------


class JamTechnique(enum.IntEnum):
    """Jamming technique classification."""

    NOISE = 0
    BARRAGE = 1
    SPOT = 2
    SWEEP = 3
    DECEPTIVE = 4


class JammingConfig(BaseModel):
    """Tunable parameters for the jamming engine."""

    enable_ew: bool = False
    js_threshold_db: float = 0.0
    deceptive_false_target_prob: float = 0.3
    deceptive_js_multiplier: float = 1.5


# ---------------------------------------------------------------------------
# Jammer definition (YAML-loadable) & instance (runtime)
# ---------------------------------------------------------------------------


class JammerDefinitionModel(BaseModel):
    """Jammer platform definition loaded from YAML."""

    jammer_id: str
    display_name: str = ""
    platform_type: str = "ground"
    frequency_min_ghz: float = 1.0
    frequency_max_ghz: float = 18.0
    power_dbm: float = 60.0
    antenna_gain_dbi: float = 10.0
    bandwidth_ghz: float = 0.5
    techniques: list[int] = [0]  # JamTechnique values
    max_simultaneous_targets: int = 1


@dataclass
class JammerInstance:
    """Runtime state of a jammer."""

    definition: JammerDefinitionModel
    position: Position
    active: bool = False
    current_technique: JamTechnique = JamTechnique.NOISE
    target_frequency_ghz: float = 0.0
    target_position: Position | None = None
    jammer_id: str = ""

    def __post_init__(self) -> None:
        if not self.jammer_id:
            self.jammer_id = self.definition.jammer_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _range_m(a: Position, b: Position) -> float:
    dx = b.easting - a.easting
    dy = b.northing - a.northing
    dz = b.altitude - a.altitude
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _dbm_to_watts(dbm: float) -> float:
    return 10.0 ** ((dbm - 30.0) / 10.0)


def _dbi_to_linear(dbi: float) -> float:
    return 10.0 ** (dbi / 10.0)


# ---------------------------------------------------------------------------
# Jamming engine
# ---------------------------------------------------------------------------


class JammingEngine:
    """Electronic Attack engine computing J/S ratios and derived effects.

    Parameters
    ----------
    event_bus : EventBus
        For publishing jamming activation/deactivation events.
    rng : np.random.Generator
        PRNG stream for stochastic effects.
    config : JammingConfig, optional
        Tunable parameters.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: JammingConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or JammingConfig()
        self._jammers: dict[str, JammerInstance] = {}

    # ------------------------------------------------------------------
    # Jammer management
    # ------------------------------------------------------------------

    def register_jammer(self, jammer: JammerInstance) -> None:
        """Register a jammer in the engine."""
        self._jammers[jammer.jammer_id] = jammer

    def activate_jammer(
        self,
        jammer_id: str,
        technique: JamTechnique,
        target_freq_ghz: float = 0.0,
        target_pos: Position | None = None,
        timestamp: Any = None,
    ) -> None:
        """Activate a jammer with a specific technique."""
        j = self._jammers.get(jammer_id)
        if j is None:
            return
        j.active = True
        j.current_technique = technique
        j.target_frequency_ghz = target_freq_ghz
        j.target_position = target_pos

        if timestamp is not None:
            self._event_bus.publish(JammingActivatedEvent(
                timestamp=timestamp, source=ModuleId.EW,
                jammer_id=jammer_id,
                target_area_center=target_pos or j.position,
                radius_m=50000.0,
                jam_type=int(technique),
            ))

    def deactivate_jammer(
        self,
        jammer_id: str,
        timestamp: Any = None,
    ) -> None:
        """Deactivate a jammer."""
        j = self._jammers.get(jammer_id)
        if j is None:
            return
        j.active = False

        if timestamp is not None:
            self._event_bus.publish(JammingDeactivatedEvent(
                timestamp=timestamp, source=ModuleId.EW,
                jammer_id=jammer_id,
            ))

    # ------------------------------------------------------------------
    # J/S ratio physics
    # ------------------------------------------------------------------

    def compute_js_ratio(
        self,
        jammer: JammerInstance,
        target_radar_power_dbm: float,
        target_radar_gain_dbi: float,
        target_radar_bw_ghz: float,
        target_range_m: float,
        jammer_range_m: float,
    ) -> float:
        """Compute J/S ratio in dB (stand-off jamming geometry).

        J/S = P_j + G_j - P_t - G_t + 40·log10(R_t) - 20·log10(R_j)
              + 10·log10(B_t/B_j)

        Parameters
        ----------
        target_range_m : float
            Range from target radar to the target being protected.
        jammer_range_m : float
            Range from jammer to the target radar.
        """
        defn = jammer.definition
        js_db = (
            defn.power_dbm + defn.antenna_gain_dbi
            - target_radar_power_dbm - target_radar_gain_dbi
        )

        if target_range_m > 0:
            js_db += 40.0 * math.log10(target_range_m)
        if jammer_range_m > 0:
            js_db -= 20.0 * math.log10(jammer_range_m)

        if target_radar_bw_ghz > 0 and defn.bandwidth_ghz > 0:
            js_db += 10.0 * math.log10(target_radar_bw_ghz / defn.bandwidth_ghz)

        # Deceptive jamming multiplier
        if jammer.current_technique == JamTechnique.DECEPTIVE:
            js_db += 10.0 * math.log10(self._config.deceptive_js_multiplier)

        return js_db

    def compute_burn_through_range(
        self,
        jammer: JammerInstance,
        target_radar_power_dbm: float,
        target_radar_gain_dbi: float,
        target_radar_bw_ghz: float,
    ) -> float:
        """Compute burn-through range in meters.

        R_bt = R_j · √(P_t·G_t·B_j / (P_j·G_j·B_t))

        Returns the range at which the target radar can detect through jamming.
        Assumes jammer_range_m = 1.0 for scaling.
        """
        defn = jammer.definition
        p_t = _dbm_to_watts(target_radar_power_dbm)
        g_t = _dbi_to_linear(target_radar_gain_dbi)
        p_j = _dbm_to_watts(defn.power_dbm)
        g_j = _dbi_to_linear(defn.antenna_gain_dbi)

        b_t = max(target_radar_bw_ghz, 1e-9)
        b_j = max(defn.bandwidth_ghz, 1e-9)

        ratio = (p_t * g_t * b_j) / max(p_j * g_j * b_t, 1e-30)
        return math.sqrt(ratio)

    # ------------------------------------------------------------------
    # Aggregate effects on detection & comms
    # ------------------------------------------------------------------

    def compute_radar_snr_penalty(
        self,
        sensor_pos: Position,
        sensor_freq_ghz: float,
        sensor_power_dbm: float,
        sensor_gain_dbi: float,
        sensor_bw_ghz: float,
        target_range_m: float,
    ) -> float:
        """Compute aggregate SNR penalty (dB, non-negative) from all active jammers.

        Sums J/S contributions from all active jammers whose frequency coverage
        overlaps with the sensor frequency.
        """
        total_js_linear = 0.0
        for j in self._jammers.values():
            if not j.active:
                continue
            defn = j.definition
            # Check frequency coverage
            if sensor_freq_ghz < defn.frequency_min_ghz:
                continue
            if sensor_freq_ghz > defn.frequency_max_ghz:
                continue

            jammer_range = _range_m(j.position, sensor_pos)
            if jammer_range <= 0:
                jammer_range = 1.0

            js_db = self.compute_js_ratio(
                j, sensor_power_dbm, sensor_gain_dbi,
                sensor_bw_ghz, target_range_m, jammer_range,
            )
            if js_db > self._config.js_threshold_db:
                total_js_linear += 10.0 ** (js_db / 10.0)

        if total_js_linear <= 0:
            return 0.0
        return max(0.0, 10.0 * math.log10(total_js_linear))

    def compute_comms_jam_factor(
        self,
        receiver_pos: Position,
        comm_freq_ghz: float,
        comm_jam_resistance: float = 0.0,
    ) -> float:
        """Compute communications jamming factor (0.0 = no jam, 1.0 = fully jammed).

        Parameters
        ----------
        comm_jam_resistance : float
            Platform jam resistance [0, 1]. Higher values resist more.
        """
        max_effect = 0.0
        for j in self._jammers.values():
            if not j.active:
                continue
            defn = j.definition
            if comm_freq_ghz < defn.frequency_min_ghz:
                continue
            if comm_freq_ghz > defn.frequency_max_ghz:
                continue

            jammer_range = _range_m(j.position, receiver_pos)
            if jammer_range <= 0:
                jammer_range = 1.0

            # J/S against comms: power advantage over range
            js_db = (
                defn.power_dbm + defn.antenna_gain_dbi
                - 20.0 * math.log10(jammer_range)
            )
            # Convert to a 0-1 factor via sigmoid-like function
            # At J/S=0 dB → factor ~0.5, at +20 dB → ~0.99, at -20 dB → ~0.01
            factor = 1.0 / (1.0 + 10.0 ** (-js_db / 20.0))
            # Apply jam resistance
            factor *= (1.0 - comm_jam_resistance)
            max_effect = max(max_effect, factor)

        return min(1.0, max_effect)

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def get_state(self) -> dict[str, Any]:
        return {
            "rng_state": self._rng.bit_generator.state,
            "jammers": {
                jid: {
                    "definition": j.definition.model_dump(),
                    "position": tuple(j.position),
                    "active": j.active,
                    "current_technique": int(j.current_technique),
                    "target_frequency_ghz": j.target_frequency_ghz,
                    "target_position": tuple(j.target_position) if j.target_position else None,
                }
                for jid, j in self._jammers.items()
            },
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self._rng.bit_generator.state = state["rng_state"]
        self._jammers.clear()
        for jid, jdata in state.get("jammers", {}).items():
            defn = JammerDefinitionModel(**jdata["definition"])
            tp = Position(*jdata["target_position"]) if jdata.get("target_position") else None
            inst = JammerInstance(
                definition=defn,
                position=Position(*jdata["position"]),
                active=jdata["active"],
                current_technique=JamTechnique(jdata["current_technique"]),
                target_frequency_ghz=jdata["target_frequency_ghz"],
                target_position=tp,
                jammer_id=jid,
            )
            self._jammers[jid] = inst
