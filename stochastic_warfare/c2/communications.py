"""Communications engine — channel reliability, EMCON, jamming, YAML-loaded equipment.

Each communication attempt is a Bernoulli trial:
``P(success) = base_reliability × env_factor × range_factor × jam_factor × emcon_factor``

Follows the same SNR-probability pattern used in the detection module, but
applied to message delivery rather than target detection.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.c2.events import (
    CommsLostEvent,
    CommsRestoredEvent,
    EmconStateChangeEvent,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class CommType(enum.IntEnum):
    """Communication equipment types."""

    RADIO_VHF = 0
    RADIO_HF = 1
    RADIO_UHF = 2
    WIRE = 3
    MESSENGER = 4
    DATA_LINK = 5
    SATELLITE = 6
    VLF = 7
    ELF = 8


class EmconState(enum.IntEnum):
    """Emission control state."""

    RADIATE = 0   # Normal operations — all emitters active
    MINIMIZE = 1  # Reduce non-essential emissions
    SILENT = 2    # No electromagnetic emissions


# Map comm_type string from YAML to CommType enum
_COMM_TYPE_MAP: dict[str, CommType] = {
    "RADIO_VHF": CommType.RADIO_VHF,
    "RADIO_HF": CommType.RADIO_HF,
    "RADIO_UHF": CommType.RADIO_UHF,
    "WIRE": CommType.WIRE,
    "MESSENGER": CommType.MESSENGER,
    "DATA_LINK": CommType.DATA_LINK,
    "SATELLITE": CommType.SATELLITE,
    "VLF": CommType.VLF,
    "ELF": CommType.ELF,
}

# Types that are electromagnetic emitters (blocked by EMCON SILENT)
_EMITTING_TYPES: set[CommType] = {
    CommType.RADIO_VHF,
    CommType.RADIO_HF,
    CommType.RADIO_UHF,
    CommType.DATA_LINK,
    CommType.SATELLITE,
}

# Types partially restricted by EMCON MINIMIZE
_MINIMIZE_RESTRICTED: set[CommType] = {
    CommType.RADIO_VHF,
    CommType.RADIO_HF,
    CommType.RADIO_UHF,
}


# ---------------------------------------------------------------------------
# YAML-loaded equipment definition
# ---------------------------------------------------------------------------


class CommEquipmentDefinition(BaseModel):
    """Communication equipment specification loaded from YAML."""

    comm_id: str
    comm_type: str  # String key → CommType via _COMM_TYPE_MAP
    display_name: str
    max_range_m: float
    bandwidth_bps: float
    base_latency_s: float
    base_reliability: float  # 0.0–1.0
    intercept_risk: float  # 0.0–1.0
    jam_resistance: float  # 0.0–1.0
    requires_los: bool

    @property
    def comm_type_enum(self) -> CommType:
        """Resolve string comm_type to enum."""
        return _COMM_TYPE_MAP[self.comm_type]


class CommEquipmentLoader:
    """Load communication equipment definitions from YAML files."""

    def __init__(self, data_dir: Path | None = None) -> None:
        if data_dir is None:
            data_dir = Path(__file__).resolve().parents[2] / "data" / "comms"
        self._data_dir = data_dir
        self._definitions: dict[str, CommEquipmentDefinition] = {}

    def load_definition(self, path: Path) -> CommEquipmentDefinition:
        """Load a single YAML file."""
        import yaml

        with open(path) as f:
            data = yaml.safe_load(f)
        defn = CommEquipmentDefinition.model_validate(data)
        self._definitions[defn.comm_id] = defn
        return defn

    def load_all(self) -> None:
        """Load all *.yaml files in the data directory."""
        for path in sorted(self._data_dir.rglob("*.yaml")):
            self.load_definition(path)

    def get_definition(self, comm_id: str) -> CommEquipmentDefinition:
        """Return definition by comm_id."""
        return self._definitions[comm_id]

    def available_equipment(self) -> list[str]:
        """Return all loaded comm_ids."""
        return sorted(self._definitions.keys())


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class CommunicationsConfig(BaseModel):
    """Tuning parameters for the communications engine."""

    env_factor_default: float = 1.0  # Environment degradation (1.0 = clear)
    messenger_speed_mps: float = 1.5  # Walking speed for messengers


# ---------------------------------------------------------------------------
# Internal state
# ---------------------------------------------------------------------------


@dataclass
class _JammingZone:
    """Active jamming affecting a geographic area."""

    center: Position
    radius_m: float
    band: CommType  # Which comm type is jammed
    strength: float  # 0.0–1.0


@dataclass
class _UnitCommsState:
    """Communication state for a single unit."""

    unit_id: str
    equipment_ids: list[str]
    emcon_state: EmconState = EmconState.RADIATE


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class CommunicationsEngine:
    """Manages communication channels, EMCON, and jamming.

    Parameters
    ----------
    event_bus : EventBus
        Publishes ``CommsLostEvent``, ``CommsRestoredEvent``, ``EmconStateChangeEvent``.
    rng : numpy.random.Generator
        Deterministic PRNG stream.
    equipment_loader : CommEquipmentLoader | None
        Pre-loaded equipment definitions. If ``None``, creates an empty loader.
    config : CommunicationsConfig | None
        Tuning parameters.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        equipment_loader: CommEquipmentLoader | None = None,
        config: CommunicationsConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._loader = equipment_loader or CommEquipmentLoader()
        self._config = config or CommunicationsConfig()
        self._units: dict[str, _UnitCommsState] = {}
        self._jamming_zones: list[_JammingZone] = []
        self._env_factor: float = self._config.env_factor_default

    # -- Registration -------------------------------------------------------

    def register_unit(self, unit_id: str, equipment_ids: list[str]) -> None:
        """Register a unit with its communication equipment."""
        self._units[unit_id] = _UnitCommsState(
            unit_id=unit_id, equipment_ids=list(equipment_ids),
        )

    # -- EMCON --------------------------------------------------------------

    def set_emcon(
        self,
        unit_id: str,
        state: EmconState,
        timestamp: "datetime | None" = None,
    ) -> None:
        """Set emission control state for a unit."""
        from datetime import datetime, timezone

        s = self._units[unit_id]
        old = s.emcon_state
        if old == state:
            return
        s.emcon_state = state
        ts = timestamp or datetime.now(tz=timezone.utc)
        self._event_bus.publish(EmconStateChangeEvent(
            timestamp=ts, source=ModuleId.C2,
            unit_id=unit_id, old_state=int(old), new_state=int(state),
        ))

    def get_emcon(self, unit_id: str) -> EmconState:
        """Return current EMCON state."""
        return self._units[unit_id].emcon_state

    # -- Environment --------------------------------------------------------

    def set_environment_factor(self, factor: float) -> None:
        """Set global environment degradation factor (0.0–1.0)."""
        self._env_factor = max(0.0, min(1.0, factor))

    # -- Jamming ------------------------------------------------------------

    def apply_jamming(
        self,
        center: Position,
        radius_m: float,
        band: CommType,
        strength: float,
    ) -> None:
        """Add a jamming zone affecting a specific comm band."""
        self._jamming_zones.append(_JammingZone(
            center=center, radius_m=radius_m, band=band, strength=strength,
        ))

    def clear_jamming(self) -> None:
        """Remove all active jamming zones."""
        self._jamming_zones.clear()

    # -- Channel queries ----------------------------------------------------

    def _get_equipment(self, unit_id: str) -> list[CommEquipmentDefinition]:
        """Return all equipment definitions for a unit."""
        s = self._units[unit_id]
        result = []
        for eid in s.equipment_ids:
            try:
                result.append(self._loader.get_definition(eid))
            except KeyError:
                pass
        return result

    def _compute_range(self, from_pos: Position, to_pos: Position) -> float:
        """Euclidean distance between two positions."""
        dx = to_pos.easting - from_pos.easting
        dy = to_pos.northing - from_pos.northing
        dz = to_pos.altitude - from_pos.altitude
        return math.sqrt(dx * dx + dy * dy + dz * dz)

    def _range_factor(self, distance: float, max_range: float) -> float:
        """Reliability degradation due to range (linear falloff in final 20%)."""
        if distance > max_range:
            return 0.0
        threshold = max_range * 0.8
        if distance <= threshold:
            return 1.0
        return 1.0 - (distance - threshold) / (max_range - threshold)

    def _emcon_factor(self, equip: CommEquipmentDefinition, emcon: EmconState) -> float:
        """EMCON effect on this equipment type."""
        ct = equip.comm_type_enum
        if emcon == EmconState.SILENT and ct in _EMITTING_TYPES:
            return 0.0  # Cannot transmit
        if emcon == EmconState.MINIMIZE and ct in _MINIMIZE_RESTRICTED:
            return 0.5  # Reduced reliability
        return 1.0

    def _jam_factor(self, equip: CommEquipmentDefinition, pos: Position) -> float:
        """Jamming effect on this equipment at this position."""
        ct = equip.comm_type_enum
        worst = 1.0
        for jz in self._jamming_zones:
            if jz.band != ct:
                continue
            dist = self._compute_range(pos, jz.center)
            if dist <= jz.radius_m:
                # Jamming effectiveness: full inside zone, reduced by resistance
                jam_effect = jz.strength * (1.0 - equip.jam_resistance)
                factor = 1.0 - jam_effect
                worst = min(worst, factor)
        return worst

    def _channel_reliability(
        self,
        equip: CommEquipmentDefinition,
        from_pos: Position,
        to_pos: Position,
        sender_emcon: EmconState,
    ) -> float:
        """Compute overall reliability for a channel."""
        distance = self._compute_range(from_pos, to_pos)
        r = equip.base_reliability
        r *= self._env_factor
        r *= self._range_factor(distance, equip.max_range_m)
        r *= self._emcon_factor(equip, sender_emcon)
        r *= self._jam_factor(equip, from_pos)
        return max(0.0, min(1.0, r))

    def _channel_latency(
        self,
        equip: CommEquipmentDefinition,
        from_pos: Position,
        to_pos: Position,
        message_size_bits: int,
    ) -> float:
        """Compute total latency for a message over this channel."""
        ct = equip.comm_type_enum
        if ct == CommType.MESSENGER:
            distance = self._compute_range(from_pos, to_pos)
            return distance / self._config.messenger_speed_mps
        # Propagation + transmission + base latency
        transmission_time = message_size_bits / equip.bandwidth_bps if equip.bandwidth_bps > 0 else 0
        return equip.base_latency_s + transmission_time

    def can_communicate(
        self,
        from_id: str,
        to_id: str,
        from_pos: Position,
        to_pos: Position,
    ) -> bool:
        """Check if any communication channel exists between two units."""
        return self.get_best_channel(from_id, to_id, from_pos, to_pos) is not None

    def get_best_channel(
        self,
        from_id: str,
        to_id: str,
        from_pos: Position,
        to_pos: Position,
    ) -> CommEquipmentDefinition | None:
        """Return the highest-reliability channel between two units."""
        sender_emcon = self._units[from_id].emcon_state
        sender_equip = self._get_equipment(from_id)
        receiver_equip = self._get_equipment(to_id)

        if not sender_equip or not receiver_equip:
            return None

        # Find compatible equipment (same comm_type)
        receiver_types = {e.comm_type_enum for e in receiver_equip}

        best: CommEquipmentDefinition | None = None
        best_reliability = -1.0

        for equip in sender_equip:
            if equip.comm_type_enum not in receiver_types:
                continue
            rel = self._channel_reliability(equip, from_pos, to_pos, sender_emcon)
            if rel > 0 and rel > best_reliability:
                best = equip
                best_reliability = rel

        return best

    def send_message(
        self,
        from_id: str,
        to_id: str,
        from_pos: Position,
        to_pos: Position,
        message_size_bits: int = 1000,
        timestamp: "datetime | None" = None,
    ) -> tuple[bool, float]:
        """Attempt to send a message. Returns (success, latency_s).

        Success is a Bernoulli trial based on channel reliability.
        """
        from datetime import datetime, timezone

        ts = timestamp or datetime.now(tz=timezone.utc)
        channel = self.get_best_channel(from_id, to_id, from_pos, to_pos)

        if channel is None:
            self._event_bus.publish(CommsLostEvent(
                timestamp=ts, source=ModuleId.C2,
                from_unit_id=from_id, to_unit_id=to_id,
                channel_type=-1, cause="no_channel",
            ))
            return False, 0.0

        sender_emcon = self._units[from_id].emcon_state
        reliability = self._channel_reliability(
            channel, from_pos, to_pos, sender_emcon,
        )
        latency = self._channel_latency(channel, from_pos, to_pos, message_size_bits)

        # Bernoulli trial
        success = bool(self._rng.random() < reliability)

        if not success:
            self._event_bus.publish(CommsLostEvent(
                timestamp=ts, source=ModuleId.C2,
                from_unit_id=from_id, to_unit_id=to_id,
                channel_type=int(channel.comm_type_enum),
                cause="reliability_failure",
            ))

        return success, latency

    # -- Update -------------------------------------------------------------

    def update(self, dt_seconds: float) -> None:
        """Advance time (placeholder for future degradation models)."""
        pass

    # -- State protocol -----------------------------------------------------

    def get_state(self) -> dict:
        """Serialize for checkpoint/restore."""
        return {
            "units": {
                uid: {
                    "unit_id": s.unit_id,
                    "equipment_ids": list(s.equipment_ids),
                    "emcon_state": int(s.emcon_state),
                }
                for uid, s in self._units.items()
            },
            "jamming_zones": [
                {
                    "center": list(jz.center),
                    "radius_m": jz.radius_m,
                    "band": int(jz.band),
                    "strength": jz.strength,
                }
                for jz in self._jamming_zones
            ],
            "env_factor": self._env_factor,
        }

    def set_state(self, state: dict) -> None:
        """Restore from checkpoint."""
        self._units.clear()
        for uid, sd in state["units"].items():
            self._units[uid] = _UnitCommsState(
                unit_id=sd["unit_id"],
                equipment_ids=sd["equipment_ids"],
                emcon_state=EmconState(sd["emcon_state"]),
            )
        self._jamming_zones = [
            _JammingZone(
                center=Position(*jd["center"]),
                radius_m=jd["radius_m"],
                band=CommType(jd["band"]),
                strength=jd["strength"],
            )
            for jd in state["jamming_zones"]
        ]
        self._env_factor = state["env_factor"]
