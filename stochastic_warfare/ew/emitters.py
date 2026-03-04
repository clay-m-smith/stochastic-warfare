"""Emitter registry — tracks all active EM emitters across the battlespace.

Provides a centralized registry for radars, radios, jammers, data links, and
navigation emitters. Used by SIGINT, jamming, and ECCM engines to query
the electromagnetic order of battle (EOB).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import Position

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class EmitterType(enum.IntEnum):
    """Classification of electromagnetic emitter."""

    RADAR = 0
    RADIO = 1
    JAMMER = 2
    DATA_LINK = 3
    NAVIGATION = 4
    ESM_ACTIVE = 5


class WaveformType(enum.IntEnum):
    """Waveform modulation type."""

    CW = 0
    PULSED = 1
    FMCW = 2
    SPREAD_SPECTRUM = 3
    FREQUENCY_HOP = 4


# ---------------------------------------------------------------------------
# Emitter data
# ---------------------------------------------------------------------------


@dataclass
class Emitter:
    """A single electromagnetic emitter."""

    emitter_id: str
    unit_id: str
    emitter_type: EmitterType
    position: Position
    frequency_ghz: float
    bandwidth_ghz: float
    power_dbm: float
    antenna_gain_dbi: float
    waveform: WaveformType
    active: bool = True
    side: str = "blue"

    def get_state(self) -> dict[str, Any]:
        return {
            "emitter_id": self.emitter_id,
            "unit_id": self.unit_id,
            "emitter_type": int(self.emitter_type),
            "position": tuple(self.position),
            "frequency_ghz": self.frequency_ghz,
            "bandwidth_ghz": self.bandwidth_ghz,
            "power_dbm": self.power_dbm,
            "antenna_gain_dbi": self.antenna_gain_dbi,
            "waveform": int(self.waveform),
            "active": self.active,
            "side": self.side,
        }

    @classmethod
    def from_state(cls, state: dict[str, Any]) -> Emitter:
        return cls(
            emitter_id=state["emitter_id"],
            unit_id=state["unit_id"],
            emitter_type=EmitterType(state["emitter_type"]),
            position=Position(*state["position"]),
            frequency_ghz=state["frequency_ghz"],
            bandwidth_ghz=state["bandwidth_ghz"],
            power_dbm=state["power_dbm"],
            antenna_gain_dbi=state["antenna_gain_dbi"],
            waveform=WaveformType(state["waveform"]),
            active=state["active"],
            side=state["side"],
        )


# ---------------------------------------------------------------------------
# Emitter registry
# ---------------------------------------------------------------------------


class EmitterRegistry:
    """Central registry of all electromagnetic emitters in the simulation.

    Supports registration, activation/deactivation, position updates, and
    filtered queries by type, frequency range, and side.
    """

    def __init__(self) -> None:
        self._emitters: dict[str, Emitter] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_emitter(self, emitter: Emitter) -> None:
        """Add an emitter to the registry."""
        self._emitters[emitter.emitter_id] = emitter

    def deregister_emitter(self, emitter_id: str) -> None:
        """Remove an emitter from the registry."""
        self._emitters.pop(emitter_id, None)

    # ------------------------------------------------------------------
    # State control
    # ------------------------------------------------------------------

    def activate(self, emitter_id: str) -> None:
        """Activate an emitter (begin transmitting)."""
        e = self._emitters.get(emitter_id)
        if e is not None:
            e.active = True

    def deactivate(self, emitter_id: str) -> None:
        """Deactivate an emitter (cease transmitting)."""
        e = self._emitters.get(emitter_id)
        if e is not None:
            e.active = False

    def update_position(self, emitter_id: str, position: Position) -> None:
        """Update an emitter's position."""
        e = self._emitters.get(emitter_id)
        if e is not None:
            e.position = position

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_active_emitters(
        self,
        freq_range: tuple[float, float] | None = None,
        emitter_type: EmitterType | None = None,
        side: str | None = None,
    ) -> list[Emitter]:
        """Return all active emitters matching the given filters."""
        results: list[Emitter] = []
        for e in self._emitters.values():
            if not e.active:
                continue
            if emitter_type is not None and e.emitter_type != emitter_type:
                continue
            if side is not None and e.side != side:
                continue
            if freq_range is not None:
                f_lo, f_hi = freq_range
                if e.frequency_ghz < f_lo or e.frequency_ghz > f_hi:
                    continue
            results.append(e)
        return results

    def get_emitters_for_unit(self, unit_id: str) -> list[Emitter]:
        """Return all emitters (active or not) belonging to a unit."""
        return [e for e in self._emitters.values() if e.unit_id == unit_id]

    def get_emitter(self, emitter_id: str) -> Emitter | None:
        """Return a single emitter by ID, or None."""
        return self._emitters.get(emitter_id)

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def get_state(self) -> dict[str, Any]:
        return {
            "emitters": {
                eid: e.get_state() for eid, e in self._emitters.items()
            }
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self._emitters.clear()
        for eid, edata in state.get("emitters", {}).items():
            self._emitters[eid] = Emitter.from_state(edata)
