"""Electronic decoys — chaff, flares, towed decoys, DRFM repeaters.

Extends the base deception framework (``detection/deception.py``) with
EW-specific decoy types that interact with missile seekers and radar systems.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.ew.events import DecoyDeployedEvent

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums & configuration
# ---------------------------------------------------------------------------


class EWDecoyType(enum.IntEnum):
    """Electronic decoy classification."""

    CHAFF = 0
    FLARE = 1
    TOWED_DECOY = 2
    DRFM = 3


class SeekerType(enum.IntEnum):
    """Missile seeker classification."""

    RADAR = 0
    IR = 1
    ELECTRO_OPTICAL = 2
    ANTI_RADIATION = 3


class EWDecoyConfig(BaseModel):
    """Tunable parameters for electronic decoys."""

    chaff_rcs_m2: float = 100.0
    chaff_duration_s: float = 120.0
    chaff_degradation_rate: float = 0.008
    flare_ir_output_kw: float = 5000.0
    flare_duration_s: float = 5.0
    flare_degradation_rate: float = 0.2
    towed_decoy_rcs_mult: float = 1.5
    towed_decoy_duration_s: float = 600.0
    drfm_false_target_effectiveness: float = 0.7
    drfm_duration_s: float = 300.0
    decoy_seeker_effectiveness: dict[int, dict[int, float]] = {
        0: {0: 0.7, 3: 0.3},       # CHAFF: RADAR=0.7, ANTI_RAD=0.3
        1: {1: 0.8, 2: 0.2},       # FLARE: IR=0.8, EO=0.2
        2: {0: 0.8},               # TOWED_DECOY: RADAR=0.8
        3: {0: 0.6, 3: 0.5},       # DRFM: RADAR=0.6, ANTI_RAD=0.5
    }


# ---------------------------------------------------------------------------
# EW Decoy
# ---------------------------------------------------------------------------


@dataclass
class EWDecoy:
    """An active electronic decoy."""

    decoy_id: str
    decoy_type: EWDecoyType
    position: Position
    frequency_ghz: float
    rcs_m2: float
    effectiveness: float
    active: bool = True
    deploy_time_s: float = 0.0
    duration_s: float = 120.0
    elapsed_s: float = 0.0


# ---------------------------------------------------------------------------
# Decoy engine
# ---------------------------------------------------------------------------


class EWDecoyEngine:
    """Electronic decoy deployment and management engine.

    Parameters
    ----------
    event_bus : EventBus
        For publishing decoy events.
    rng : np.random.Generator
        PRNG stream.
    config : EWDecoyConfig, optional
        Tunable parameters.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: EWDecoyConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or EWDecoyConfig()
        self._decoys: dict[str, EWDecoy] = {}
        self._next_id: int = 0

    def _gen_id(self) -> str:
        self._next_id += 1
        return f"ew_decoy_{self._next_id}"

    # ------------------------------------------------------------------
    # Deployment
    # ------------------------------------------------------------------

    def deploy_chaff(
        self, position: Position, frequency_ghz: float = 10.0,
        timestamp: Any = None, unit_id: str = "",
    ) -> EWDecoy:
        """Deploy a chaff cloud."""
        cfg = self._config
        decoy = EWDecoy(
            decoy_id=self._gen_id(),
            decoy_type=EWDecoyType.CHAFF,
            position=position,
            frequency_ghz=frequency_ghz,
            rcs_m2=cfg.chaff_rcs_m2,
            effectiveness=1.0,
            duration_s=cfg.chaff_duration_s,
        )
        self._decoys[decoy.decoy_id] = decoy
        if timestamp is not None:
            self._event_bus.publish(DecoyDeployedEvent(
                timestamp=timestamp, source=ModuleId.EW,
                unit_id=unit_id, decoy_type=int(EWDecoyType.CHAFF),
                position=position,
            ))
        return decoy

    def deploy_flare(
        self, position: Position, timestamp: Any = None, unit_id: str = "",
    ) -> EWDecoy:
        """Deploy an IR flare."""
        cfg = self._config
        decoy = EWDecoy(
            decoy_id=self._gen_id(),
            decoy_type=EWDecoyType.FLARE,
            position=position,
            frequency_ghz=0.0,  # IR, not RF
            rcs_m2=0.0,
            effectiveness=1.0,
            duration_s=cfg.flare_duration_s,
        )
        self._decoys[decoy.decoy_id] = decoy
        if timestamp is not None:
            self._event_bus.publish(DecoyDeployedEvent(
                timestamp=timestamp, source=ModuleId.EW,
                unit_id=unit_id, decoy_type=int(EWDecoyType.FLARE),
                position=position,
            ))
        return decoy

    def deploy_towed_decoy(
        self, position: Position, frequency_ghz: float = 10.0,
        platform_rcs_m2: float = 10.0,
        timestamp: Any = None, unit_id: str = "",
    ) -> EWDecoy:
        """Deploy a towed radar decoy."""
        cfg = self._config
        decoy = EWDecoy(
            decoy_id=self._gen_id(),
            decoy_type=EWDecoyType.TOWED_DECOY,
            position=position,
            frequency_ghz=frequency_ghz,
            rcs_m2=platform_rcs_m2 * cfg.towed_decoy_rcs_mult,
            effectiveness=1.0,
            duration_s=cfg.towed_decoy_duration_s,
        )
        self._decoys[decoy.decoy_id] = decoy
        if timestamp is not None:
            self._event_bus.publish(DecoyDeployedEvent(
                timestamp=timestamp, source=ModuleId.EW,
                unit_id=unit_id, decoy_type=int(EWDecoyType.TOWED_DECOY),
                position=position,
            ))
        return decoy

    def deploy_drfm(
        self, position: Position, frequency_ghz: float = 10.0,
        timestamp: Any = None, unit_id: str = "",
    ) -> EWDecoy:
        """Deploy a DRFM (Digital RF Memory) repeater jammer/decoy."""
        cfg = self._config
        decoy = EWDecoy(
            decoy_id=self._gen_id(),
            decoy_type=EWDecoyType.DRFM,
            position=position,
            frequency_ghz=frequency_ghz,
            rcs_m2=0.0,
            effectiveness=cfg.drfm_false_target_effectiveness,
            duration_s=cfg.drfm_duration_s,
        )
        self._decoys[decoy.decoy_id] = decoy
        if timestamp is not None:
            self._event_bus.publish(DecoyDeployedEvent(
                timestamp=timestamp, source=ModuleId.EW,
                unit_id=unit_id, decoy_type=int(EWDecoyType.DRFM),
                position=position,
            ))
        return decoy

    # ------------------------------------------------------------------
    # Missile diversion
    # ------------------------------------------------------------------

    def compute_missile_divert_probability(
        self, decoy: EWDecoy, missile_seeker_type: SeekerType, range_m: float,
    ) -> float:
        """Compute probability that a decoy diverts an incoming missile.

        Depends on decoy type vs missile seeker match:
        - CHAFF effective against RADAR seekers
        - FLARE effective against IR seekers
        - TOWED_DECOY effective against RADAR seekers
        - DRFM effective against RADAR and ANTI_RADIATION seekers
        """
        if not decoy.active or decoy.effectiveness <= 0:
            return 0.0

        # Type-seeker match matrix (configurable via EWDecoyConfig)
        matrix = self._config.decoy_seeker_effectiveness
        match_effectiveness = matrix.get(int(decoy.decoy_type), {}).get(int(missile_seeker_type), 0.0)

        if match_effectiveness <= 0:
            return 0.0

        # Range factor: closer decoys are more effective
        range_factor = 1.0
        if range_m > 100.0:
            range_factor = 100.0 / range_m

        return min(1.0, match_effectiveness * decoy.effectiveness * range_factor)

    # ------------------------------------------------------------------
    # Update (degradation)
    # ------------------------------------------------------------------

    def update(self, dt: float) -> None:
        """Advance time: degrade and expire active decoys."""
        expired: list[str] = []
        cfg = self._config
        for did, d in self._decoys.items():
            if not d.active:
                continue
            d.elapsed_s += dt

            # Duration expiry
            if d.elapsed_s >= d.duration_s:
                d.active = False
                d.effectiveness = 0.0
                expired.append(did)
                continue

            # Type-specific degradation
            if d.decoy_type == EWDecoyType.CHAFF:
                d.effectiveness = max(0.0, d.effectiveness - cfg.chaff_degradation_rate * dt)
            elif d.decoy_type == EWDecoyType.FLARE:
                d.effectiveness = max(0.0, d.effectiveness - cfg.flare_degradation_rate * dt)

            if d.effectiveness <= 0:
                d.active = False

    def active_decoys(self) -> list[EWDecoy]:
        """Return all currently active decoys."""
        return [d for d in self._decoys.values() if d.active]

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def get_state(self) -> dict[str, Any]:
        return {
            "rng_state": self._rng.bit_generator.state,
            "next_id": self._next_id,
            "decoys": {
                did: {
                    "decoy_id": d.decoy_id,
                    "decoy_type": int(d.decoy_type),
                    "position": tuple(d.position),
                    "frequency_ghz": d.frequency_ghz,
                    "rcs_m2": d.rcs_m2,
                    "effectiveness": d.effectiveness,
                    "active": d.active,
                    "deploy_time_s": d.deploy_time_s,
                    "duration_s": d.duration_s,
                    "elapsed_s": d.elapsed_s,
                }
                for did, d in self._decoys.items()
            },
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self._rng.bit_generator.state = state["rng_state"]
        self._next_id = state.get("next_id", 0)
        self._decoys.clear()
        for did, ddata in state.get("decoys", {}).items():
            self._decoys[did] = EWDecoy(
                decoy_id=ddata["decoy_id"],
                decoy_type=EWDecoyType(ddata["decoy_type"]),
                position=Position(*ddata["position"]),
                frequency_ghz=ddata["frequency_ghz"],
                rcs_m2=ddata["rcs_m2"],
                effectiveness=ddata["effectiveness"],
                active=ddata["active"],
                deploy_time_s=ddata["deploy_time_s"],
                duration_s=ddata["duration_s"],
                elapsed_s=ddata["elapsed_s"],
            )
